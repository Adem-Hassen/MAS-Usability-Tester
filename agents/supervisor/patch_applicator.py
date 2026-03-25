# agents/supervisor/patch_applicator.py
"""
Patch Applicator — applies ResolvedPatch objects to the original HTML.

Patch type routing
──────────────────
html_attribute / html_structure / content / remove_element /
reorder_elements / inline_style
    → snippet replacement (before → after in the HTML body)

css_rule / css_class
    → css_snippet injected into an existing <style> block, or a new
      <style> block appended before </head>.  The before/after snippets
      are NOT used for matching — css_snippet is the authoritative source.

js_snippet
    → js_snippet injected as a <script> block just before </body>.
      The before/after snippets are NOT used for matching.

This distinction is critical: the LLM often returns before_snippet ==
after_snippet for CSS/JS patches (because the change is not an in-place
HTML edit but an injection), so snippet-equality must never be used to
skip a CSS/JS patch.
"""

from __future__ import annotations

import re
from pathlib import Path

from config.settings import settings
from schemas.patch_schema import ResolvedPatch, UnifiedPatchSet, PatchType
from monitoring.logger import get_logger

logger = get_logger(__name__)

# Patch types that are injected, not swapped
_CSS_TYPES = {PatchType.CSS_RULE, PatchType.CSS_CLASS,
              "css_rule", "css_class"}
_JS_TYPES  = {PatchType.JS_SNIPPET, "js_snippet"}


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def patch_applicator_node(state: dict) -> dict:
    unified: UnifiedPatchSet | None = state.get("unified_patch_set")
    html_content: str = state.get("html_content", "")

    if not unified or not unified.patches:
        logger.warning("patch_applicator.no_patches")
        return {"patched_html_content": html_content, "total_patches_applied": 0}

    logger.info("patch_applicator.start",
                total_patches=len(unified.patches),
                html_length=len(html_content))

    patched_html, applied_count, skipped = _apply_patches(html_content, unified.patches)

    logger.info("patch_applicator.complete", applied=applied_count, skipped=len(skipped))
    for patch_id, reason in skipped:
        logger.warning("patch_applicator.patch_skipped",
                       patch_id=patch_id, reason=reason)

    if settings.save_patched_html:
        _save_patched_html(patched_html, state.get("html_source_path", "unknown.html"))

    return {"patched_html_content": patched_html, "total_patches_applied": applied_count}


# ---------------------------------------------------------------------------
# Core application
# ---------------------------------------------------------------------------

def _apply_patches(
    html: str,
    patches: list[ResolvedPatch],
) -> tuple[str, int, list[tuple[str, str]]]:
    applied  = 0
    skipped: list[tuple[str, str]] = []
    current  = html

    # Sort: remove_element last, CSS/JS after HTML patches
    patches_sorted = sorted(
        patches,
        key=lambda p: (
            2 if str(p.patch_type) == "remove_element" else
            1 if str(p.patch_type) in ("css_rule", "css_class", "js_snippet") else
            0,
            p.cluster_ids[0] if p.cluster_ids else "",
        ),
    )

    for patch in patches_sorted:
        pt = str(patch.patch_type)

        # ── CSS injection ──────────────────────────────────────────────────
        if pt in ("css_rule", "css_class"):
            new_html, ok, reason = _inject_css(current, patch)
            if ok:
                current = new_html
                applied += 1
                logger.debug("patch_applicator.css_injected",
                             patch_id=patch.resolved_patch_id)
            else:
                skipped.append((patch.resolved_patch_id, reason))
            continue

        # ── JS injection ───────────────────────────────────────────────────
        if pt == "js_snippet":
            new_html, ok, reason = _inject_js(current, patch)
            if ok:
                current = new_html
                applied += 1
                logger.debug("patch_applicator.js_injected",
                             patch_id=patch.resolved_patch_id)
            else:
                skipped.append((patch.resolved_patch_id, reason))
            continue

        # ── HTML snippet replacement ────────────────────────────────────────
        # Skip if no meaningful change was proposed
        before = (patch.before_snippet or "").strip()
        after  = (patch.after_snippet  or "").strip()

        if not before or not after:
            skipped.append((patch.resolved_patch_id,
                            "empty before_snippet or after_snippet"))
            continue
        if before == after:
            skipped.append((patch.resolved_patch_id,
                            "before_snippet == after_snippet — no change"))
            continue

        new_html, ok, reason = _apply_single_patch(current, patch)
        if ok:
            current = new_html
            applied += 1
            logger.debug("patch_applicator.patch_applied",
                         patch_id=patch.resolved_patch_id,
                         target=patch.target_element,
                         patch_type=pt)
        else:
            skipped.append((patch.resolved_patch_id, reason))

    return current, applied, skipped


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

def _inject_css(html: str, patch: ResolvedPatch) -> tuple[str, bool, str]:
    """
    Inject css_snippet into the HTML.

    Priority:
      1. Append to the last existing <style> block (avoids creating a new one).
      2. Insert a new <style> block before </head>.
      3. Prepend a <style> block before <body> if </head> is absent.
    """
    snippet = (patch.css_snippet or patch.after_snippet or "").strip()
    if not snippet:
        return html, False, "css_snippet and after_snippet are both empty"

    # Deduplicate: skip if this exact rule block is already in the HTML
    # (normalise whitespace for comparison)
    norm_snippet = re.sub(r"\s+", " ", snippet)
    norm_html    = re.sub(r"\s+", " ", html)
    if norm_snippet in norm_html:
        logger.debug("patch_applicator.css_already_present",
                     patch_id=patch.resolved_patch_id)
        return html, True, ""   # already applied — count as success

    comment = f"\n    /* injected by patch {patch.resolved_patch_id} */\n    "

    # Strategy 1: append inside the last <style> block
    style_end = html.rfind("</style>")
    if style_end != -1:
        injection = comment + snippet + "\n"
        new_html  = html[:style_end] + injection + html[style_end:]
        return new_html, True, ""

    # Strategy 2: insert new <style> block before </head>
    head_end = html.lower().rfind("</head>")
    if head_end != -1:
        block    = f"\n<style>\n{comment}{snippet}\n</style>\n"
        new_html = html[:head_end] + block + html[head_end:]
        return new_html, True, ""

    # Strategy 3: prepend before <body>
    body_start = html.lower().find("<body")
    if body_start != -1:
        block    = f"<style>\n{comment}{snippet}\n</style>\n"
        new_html = html[:body_start] + block + html[body_start:]
        return new_html, True, ""

    return html, False, "Could not find injection point for CSS (no </style>, </head>, or <body>)"


# ---------------------------------------------------------------------------
# JS injection
# ---------------------------------------------------------------------------

def _inject_js(html: str, patch: ResolvedPatch) -> tuple[str, bool, str]:
    """
    Inject js_snippet as a <script> block just before </body>.

    If </body> is absent, append to end of document.
    Deduplicates by checking if a marker comment already exists.
    """
    snippet = (patch.js_snippet or patch.after_snippet or "").strip()
    if not snippet:
        return html, False, "js_snippet and after_snippet are both empty"

    marker = f"/* patch:{patch.resolved_patch_id} */"

    # Deduplicate
    if marker in html:
        logger.debug("patch_applicator.js_already_present",
                     patch_id=patch.resolved_patch_id)
        return html, True, ""

    script_block = (
        f'\n<script>\n{marker}\n'
        f'(function() {{\n'
        f'  "use strict";\n'
        f'  {snippet}\n'
        f'}})();\n'
        f'</script>\n'
    )

    body_end = html.lower().rfind("</body>")
    if body_end != -1:
        new_html = html[:body_end] + script_block + html[body_end:]
    else:
        new_html = html + script_block

    return new_html, True, ""


# ---------------------------------------------------------------------------
# HTML snippet replacement (unchanged from original — kept for non-CSS/JS)
# ---------------------------------------------------------------------------

def _apply_single_patch(
    html: str,
    patch: ResolvedPatch,
) -> tuple[str, bool, str]:
    before = patch.before_snippet.strip()
    after  = patch.after_snippet.strip()

    if before in html:
        return html.replace(before, after, 1), True, ""

    norm_before = _normalise_whitespace(before)
    if norm_before in _normalise_whitespace(html):
        pattern  = _snippet_to_regex(before)
        new_html, n = re.subn(pattern, lambda _: after, html, count=1, flags=re.DOTALL)
        if n > 0:
            return new_html, True, ""

    if str(patch.patch_type) == "html_attribute":
        new_html, ok = _attribute_targeted_replace(html, patch)
        if ok:
            return new_html, True, ""

    return html, False, (
        f"before_snippet not found in HTML (exact or normalised). "
        f"Target: {patch.target_element!r}. "
        f"Snippet prefix: {before[:80]!r}"
    )


def _attribute_targeted_replace(html: str, patch: ResolvedPatch) -> tuple[str, bool]:
    sel  = patch.target_element
    tag  = _selector_to_tag(sel)
    if not tag:
        return html, False

    tag_re = re.compile(
        rf"(<{re.escape(tag)}\b[^>]*?)(\s*/?>)",
        re.DOTALL | re.IGNORECASE,
    )
    new_attrs = _diff_attributes(patch.before_snippet, patch.after_snippet)
    if not new_attrs:
        return html, False

    attrs_str = " " + " ".join(
        f'{k}="{v}"' if v else k
        for k, v in new_attrs.items()
    )

    def _inject(m: re.Match) -> str:
        return m.group(1) + attrs_str + m.group(2)

    new_html, n = tag_re.subn(_inject, html, count=1)
    return (new_html, True) if n > 0 else (html, False)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _normalise_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _snippet_to_regex(snippet: str) -> str:
    escaped  = re.escape(snippet)
    flexible = re.sub(r"(\ |\\ |\\\n|\\\t)+", r"\\s+", escaped)
    return flexible


def _selector_to_tag(selector: str) -> str | None:
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9]*)", selector)
    return m.group(1).lower() if m else None


def _diff_attributes(before: str, after: str) -> dict[str, str]:
    def _extract(html_tag: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for m in re.finditer(r'(\w[\w-]*)=["\']([^"\']*)["\']', html_tag):
            attrs[m.group(1)] = m.group(2)
        for m in re.finditer(
            r'\b(required|disabled|checked|readonly|hidden|autofocus)\b', html_tag
        ):
            k = m.group(1)
            if k not in attrs:
                attrs[k] = ""
        return attrs

    before_attrs = _extract(before)
    after_attrs  = _extract(after)
    return {k: v for k, v in after_attrs.items() if before_attrs.get(k) != v}


def _save_patched_html(html: str, source_path: str) -> None:
    try:
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem     = Path(source_path).stem
        out_path = output_dir / f"{stem}_patched.html"
        out_path.write_text(html, encoding="utf-8")
        logger.info("patch_applicator.saved_patched_html", path=str(out_path))
    except Exception as e:
        logger.warning("patch_applicator.save_failed", error=str(e))