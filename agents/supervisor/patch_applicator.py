
from __future__ import annotations

import re
from pathlib import Path

from config.settings import settings
from core.state import GraphState
from schemas.patch_schema import ResolvedPatch, UnifiedPatchSet
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def patch_applicator_node(state: GraphState) -> dict:
    """
    LangGraph node.  Applies all resolved patches to the HTML and writes the
    result to state["patched_html_content"] + state["total_patches_applied"].
    """
    unified: UnifiedPatchSet | None = state.get("unified_patch_set")
    html_content: str = state.get("html_content", "")

    if not unified or not unified.patches:
        logger.warning("patch_applicator.no_patches")
        return {
            "patched_html_content": html_content,
            "total_patches_applied": 0,
        }

    logger.info(
        "patch_applicator.start",
        total_patches=len(unified.patches),
        html_length=len(html_content),
    )

    patched_html, applied_count, skipped = _apply_patches(html_content, unified.patches)

    logger.info(
        "patch_applicator.complete",
        applied=applied_count,
        skipped=len(skipped),
    )
    if skipped:
        for patch_id, reason in skipped:
            logger.warning(
                "patch_applicator.patch_skipped",
                patch_id=patch_id,
                reason=reason,
            )

    # Optionally persist the patched HTML to disk
    if settings.save_patched_html:
        _save_patched_html(patched_html, state.get("html_source_path", "unknown.html"))

    return {
        "patched_html_content": patched_html,
        "total_patches_applied": applied_count,
    }


# ---------------------------------------------------------------------------
# Core application logic
# ---------------------------------------------------------------------------

def _apply_patches(
    html: str,
    patches: list[ResolvedPatch],
) -> tuple[str, int, list[tuple[str, str]]]:
    """
    Apply patches in order.  Returns (patched_html, applied_count, skipped_list).
    skipped_list elements are (patch_id, reason).
    """
    applied   = 0
    skipped: list[tuple[str, str]] = []
    current   = html

    # Sort: remove_element last (avoids invalidating selectors for other patches),
    # then by cluster_id for consistent ordering.
    patches_sorted = sorted(
        patches,
        key=lambda p: (
            1 if str(p.patch_type) == "remove_element" else 0,
            p.cluster_ids[0] if p.cluster_ids else "",
        ),
    )

    for patch in patches_sorted:
        if not patch.before_snippet or not patch.after_snippet:
            skipped.append((patch.resolved_patch_id, "empty before_snippet or after_snippet"))
            continue
        if patch.before_snippet == "<!-- original snippet unavailable -->":
            skipped.append((patch.resolved_patch_id, "fallback placeholder patch — skipping"))
            continue

        new_html, success, reason = _apply_single_patch(current, patch)

        if success:
            current = new_html
            applied += 1
            logger.debug(
                "patch_applicator.patch_applied",
                patch_id=patch.resolved_patch_id,
                target=patch.target_element,
                patch_type=patch.patch_type,
            )
        else:
            skipped.append((patch.resolved_patch_id, reason))

    return current, applied, skipped


def _apply_single_patch(
    html: str,
    patch: ResolvedPatch,
) -> tuple[str, bool, str]:
    """
    Apply one patch.  Returns (new_html, success, reason).

    Strategy (in order of preference):
      1. Exact string match of before_snippet → replace with after_snippet
      2. Whitespace-normalised match → replace
      3. Attribute-targeted match (for html_attribute patches) via regex
      4. Fail: return original html unchanged
    """
    before = patch.before_snippet.strip()
    after  = patch.after_snippet.strip()

    # ── Strategy 1: exact match ────────────────────────────────────────────
    if before in html:
        return html.replace(before, after, 1), True, ""

    # ── Strategy 2: whitespace-normalised match ────────────────────────────
    norm_before = _normalise_whitespace(before)
    norm_html   = _normalise_whitespace(html)

    if norm_before in norm_html:
        # We can't safely replace in the normalised version; fall back to
        # regex with \s+ substituted for whitespace runs.
        pattern = _snippet_to_regex(before)
        new_html, n = re.subn(pattern, lambda _: after, html, count=1, flags=re.DOTALL)
        if n > 0:
            return new_html, True, ""

    # ── Strategy 3: attribute-targeted regex (html_attribute only) ─────────
    if str(patch.patch_type) == "html_attribute":
        new_html, success = _attribute_targeted_replace(html, patch)
        if success:
            return new_html, True, ""

    # ── Strategy 4: failure ────────────────────────────────────────────────
    return html, False, (
        f"before_snippet not found in HTML (exact or normalised). "
        f"Target: {patch.target_element!r}. "
        f"Snippet prefix: {before[:80]!r}"
    )


def _attribute_targeted_replace(html: str, patch: ResolvedPatch) -> tuple[str, bool]:
    """
    Targeted fallback for html_attribute patches.
    Tries to find the opening tag of the target element and inject the
    new attributes from after_snippet into it.

    This handles cases where the LLM quoted the before_snippet with slightly
    different whitespace or attribute order than the actual HTML.
    """
    # Extract the tag name and a unique attribute from the target selector
    sel = patch.target_element
    tag  = _selector_to_tag(sel)
    if not tag:
        return html, False

    # Build a regex that matches the opening tag
    # e.g.  <button ... >  or  <input ...  />
    tag_re = re.compile(
        rf"(<{re.escape(tag)}\b[^>]*?)(\s*/?>)",
        re.DOTALL | re.IGNORECASE,
    )

    # Extract new attributes from after_snippet that differ from before_snippet
    new_attrs = _diff_attributes(patch.before_snippet, patch.after_snippet)
    if not new_attrs:
        return html, False

    attrs_str = " " + " ".join(f'{k}="{v}"' for k, v in new_attrs.items())

    # Apply to the first matching tag only
    def _inject(m: re.Match) -> str:
        return m.group(1) + attrs_str + m.group(2)

    new_html, n = tag_re.subn(_inject, html, count=1)
    return (new_html, True) if n > 0 else (html, False)


# ---------------------------------------------------------------------------
# HTML utility helpers
# ---------------------------------------------------------------------------

def _normalise_whitespace(text: str) -> str:
    """Collapse all whitespace runs to a single space for loose matching."""
    return re.sub(r"\s+", " ", text).strip()


def _snippet_to_regex(snippet: str) -> str:
    """
    Convert a literal HTML snippet to a regex pattern where whitespace runs
    are replaced by \\s+ to allow flexible matching.
    """
    escaped = re.escape(snippet)
    # Replace escaped whitespace with flexible whitespace matcher
    flexible = re.sub(r"(\ |\\ |\\\n|\\\t)+", r"\\s+", escaped)
    return flexible


def _selector_to_tag(selector: str) -> str | None:
    """
    Extract the HTML tag from a CSS selector.
    e.g.  "button.submit"      → "button"
          "#submit-btn"        → None  (id only — tag unknown)
          "input[type=email]"  → "input"
          ".error-msg"         → None  (class only)
    """
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9]*)", selector)
    return m.group(1).lower() if m else None


def _diff_attributes(before: str, after: str) -> dict[str, str]:
    """
    Return attributes present in after_snippet but absent or different in before_snippet.
    Simple regex-based attribute extraction — handles common cases.
    """
    def _extract_attrs(html_tag: str) -> dict[str, str]:
        attrs = {}
        for m in re.finditer(r'(\w[\w-]*)=["\']([^"\']*)["\']', html_tag):
            attrs[m.group(1)] = m.group(2)
        # Boolean attributes (no value)
        for m in re.finditer(r'\b(required|disabled|checked|readonly|hidden)\b', html_tag):
            key = m.group(1)
            if key not in attrs:
                attrs[key] = ""
        return attrs

    before_attrs = _extract_attrs(before)
    after_attrs  = _extract_attrs(after)

    diff = {}
    for key, val in after_attrs.items():
        if before_attrs.get(key) != val:
            diff[key] = val
    return diff


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _save_patched_html(html: str, source_path: str) -> None:
    """Write the patched HTML to the output directory."""
    try:
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(source_path).stem
        out_path = output_dir / f"{stem}_patched.html"
        out_path.write_text(html, encoding="utf-8")
        logger.info("patch_applicator.saved_patched_html", path=str(out_path))
    except Exception as e:
        logger.warning("patch_applicator.save_failed", error=str(e))