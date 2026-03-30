# agents/supervisor/patch_applicator.py

from __future__ import annotations

import re
from pathlib import Path

from config.settings import settings
from schemas.patch_schema import ResolvedPatch, UnifiedPatchSet, PatchType
from monitoring.logger import get_logger

logger = get_logger(__name__)

_CSS_TYPES = {"css_rule", "css_class"}
_JS_TYPES  = {"js_snippet"}


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
    
    
    for patch in unified.patches:
        logger.debug("patch_applicator.patch_contents",
                 patch_id=patch.resolved_patch_id,
                 patch_type=str(patch.patch_type),
                 has_before=bool(patch.before_snippet),
                 has_after=bool(patch.after_snippet),
                 has_css=bool(patch.css_snippet),
                 has_js=bool(patch.js_snippet),
                 before_preview=(patch.before_snippet or "")[:60],
                 after_preview=(patch.after_snippet or "")[:60],
                 css_preview=(patch.css_snippet or "")[:60],
                 js_preview=(patch.js_snippet or "")[:60])
        
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

    # Order: HTML first, then CSS, then JS, remove_element last
    patches_sorted = sorted(
        patches,
        key=lambda p: (
            3 if str(p.patch_type) == "remove_element" else
            2 if str(p.patch_type) in _JS_TYPES else
            1 if str(p.patch_type) in _CSS_TYPES else
            0,
            p.cluster_ids[0] if p.cluster_ids else "",
        ),
    )

    for patch in patches_sorted:
        pt = str(patch.patch_type) if patch else ""
        applied_css  = False
        applied_js   = False

        # ── Primary: CSS injection ─────────────────────────────────────────
        if pt in _CSS_TYPES:
            new_html, ok, reason = _inject_css(current, patch)
            if ok:
                current = new_html
                applied += 1
                applied_css = True
                logger.debug("patch_applicator.css_injected",
                             patch_id=patch.resolved_patch_id,
                             target=patch.target_element)
            else:
                skipped.append((patch.resolved_patch_id, reason))

        # ── Primary: JS injection ──────────────────────────────────────────
        elif pt in _JS_TYPES:
            new_html, ok, reason = _inject_js(current, patch)
            if ok:
                current = new_html
                applied += 1
                applied_js = True
                logger.debug("patch_applicator.js_injected",
                             patch_id=patch.resolved_patch_id,
                             target=patch.target_element)
            else:
                skipped.append((patch.resolved_patch_id, reason))

        # ── Primary: HTML snippet replacement ──────────────────────────────
        else:
            before = (patch.before_snippet or "").strip()
            after  = (patch.after_snippet  or "").strip()

            if not before or not after:
                skipped.append((patch.resolved_patch_id,
                                "empty before_snippet or after_snippet"))
            elif before == after:
                skipped.append((patch.resolved_patch_id,
                                "before_snippet == after_snippet — no change"))
            else:
                new_html, ok, reason = _apply_single_patch(current, patch)
                if ok:
                    current = new_html
                    applied += 1
                    logger.debug("patch_applicator.html_applied",
                                 patch_id=patch.resolved_patch_id,
                                 target=patch.target_element)
                else:
                    skipped.append((patch.resolved_patch_id, reason))

        # ── Companion CSS: inject css_snippet even if primary type wasn't CSS ──
        if not applied_css and (patch.css_snippet or "").strip():
            new_html, ok, reason = _inject_css(current, patch)
            if ok:
                current = new_html
                applied += 1
                logger.debug("patch_applicator.companion_css_injected",
                             patch_id=patch.resolved_patch_id,
                             target=patch.target_element)
            else:
                logger.debug("patch_applicator.companion_css_skipped",
                             patch_id=patch.resolved_patch_id,
                             reason=reason)

        # ── Companion JS: inject js_snippet even if primary type wasn't JS ──
        if not applied_js and (patch.js_snippet or "").strip():
            new_html, ok, reason = _inject_js(current, patch)
            if ok:
                current = new_html
                applied += 1
                logger.debug("patch_applicator.companion_js_injected",
                             patch_id=patch.resolved_patch_id,
                             target=patch.target_element)
            else:
                logger.debug("patch_applicator.companion_js_skipped",
                             patch_id=patch.resolved_patch_id,
                             reason=reason)

    return current, applied, skipped


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

def _inject_css(html: str, patch: ResolvedPatch) -> tuple[str, bool, str]:
    snippet = (patch.css_snippet or "").strip()

    if not snippet and patch.after_snippet:
        candidate = patch.after_snippet.strip()
        if not _looks_like_html(candidate):
            snippet = candidate
    if not snippet:
        logger.warning("patch_applicator.css_snippet_empty",
                       patch_id=patch.resolved_patch_id)
        return html, False, "css_snippet is empty"

    if _looks_like_html(snippet):
        return html, False, (
            f"css_snippet looks like HTML, not CSS — skipping to avoid corruption. "
            f"Preview: {snippet[:80]!r}"
        )

    # Deduplicate
    if _already_injected(html, snippet):
        logger.debug("patch_applicator.css_already_present",
                     patch_id=patch.resolved_patch_id)
        return html, True, ""

    comment = f"\n    /* patch:{patch.resolved_patch_id} */\n    "

    # Strategy 1: append inside last <style> block
    style_end = html.rfind("</style>")
    if style_end != -1:
        return html[:style_end] + comment + snippet + "\n" + html[style_end:], True, ""

    # Strategy 2: new <style> before </head>
    head_end = html.lower().rfind("</head>")
    if head_end != -1:
        block = f"\n<style>\n{comment}{snippet}\n</style>\n"
        return html[:head_end] + block + html[head_end:], True, ""

    # Strategy 3: prepend before <body>
    body_start = html.lower().find("<body")
    if body_start != -1:
        block = f"<style>\n{comment}{snippet}\n</style>\n"
        return html[:body_start] + block + html[body_start:], True, ""

    return html, False, "No CSS injection point found (no </style>, </head>, or <body>)"


# ---------------------------------------------------------------------------
# JS injection
# ---------------------------------------------------------------------------

def _inject_js(html: str, patch: ResolvedPatch) -> tuple[str, bool, str]:
    snippet = (patch.js_snippet or "").strip()

    if not snippet and patch.after_snippet:
        
        candidate = patch.after_snippet.strip()
        if not _looks_like_html(candidate):
         snippet = candidate

    if not snippet:
        logger.warning("patch_applicator.js_snippet_empty",
                       patch_id=patch.resolved_patch_id)
        return html, False, "js_snippet is empty"

    if _looks_like_html(snippet):
        return html, False, (
            f"js_snippet looks like HTML, not JavaScript — skipping to avoid "
            f"injecting invalid script. Preview: {snippet[:80]!r}"
        )

    # Ensure DOMContentLoaded wrapper
    if "DOMContentLoaded" not in snippet:
        snippet = (
            'document.addEventListener("DOMContentLoaded", function() {\n'
            f'  {snippet}\n'
            '});'
        )
        logger.debug("patch_applicator.js_wrapped_dom_ready",
                     patch_id=patch.resolved_patch_id)

    marker = f"/* patch:{patch.resolved_patch_id} */"

    # Deduplicate
    if marker in html:
        logger.debug("patch_applicator.js_already_present",
                     patch_id=patch.resolved_patch_id)
        return html, True, ""

    script_block = f'\n<script>\n{marker}\n{snippet}\n</script>\n'

    body_end = html.lower().rfind("</body>")
    if body_end != -1:
        return html[:body_end] + script_block + html[body_end:], True, ""

    return html + script_block, True, ""


# ---------------------------------------------------------------------------
# HTML snippet replacement
# ---------------------------------------------------------------------------

def _apply_single_patch(
    html: str,
    patch: ResolvedPatch,
) -> tuple[str, bool, str]:
    before = patch.before_snippet.strip()
    after  = patch.after_snippet.strip()

    # Strategy 1: exact match
    if before in html:
        return html.replace(before, after, 1), True, ""

    # Strategy 2: whitespace-normalised match
    if _normalise_ws(before) in _normalise_ws(html):
        pattern  = _snippet_to_regex(before)
        new_html, n = re.subn(pattern, lambda _: after, html, count=1, flags=re.DOTALL)
        if n > 0:
            return new_html, True, ""

    # Strategy 3: attribute-targeted (html_attribute only)
    if str(patch.patch_type) == "html_attribute":
        new_html, ok = _attribute_targeted_replace(html, patch)
        if ok:
            return new_html, True, ""

    return html, False, (
        f"before_snippet not found. Target: {patch.target_element!r}. "
        f"Snippet prefix: {before[:80]!r}"
    )


def _attribute_targeted_replace(html: str, patch: ResolvedPatch) -> tuple[str, bool]:
    tag = _selector_to_tag(patch.target_element)
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
        f'{k}="{v}"' if v else k for k, v in new_attrs.items()
    )
    def _inject(m: re.Match) -> str:
        return m.group(1) + attrs_str + m.group(2)
    new_html, n = tag_re.subn(_inject, html, count=1)
    return (new_html, True) if n > 0 else (html, False)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _looks_like_html(text: str) -> bool:
    """Return True if text appears to be HTML rather than CSS or JavaScript."""
    t = text.strip()
    return bool(re.match(r"^\s*<[a-zA-Z!]", t))


def _already_injected(html: str, snippet: str) -> bool:
    """Check if a normalised version of snippet is already in the HTML."""
    return _normalise_ws(snippet) in _normalise_ws(html)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _normalise_ws(text: str) -> str:
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