# tools/html_preprocessor.py

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preprocess_for_analysis(html: str, max_chars: int = 12_000) -> str:
    """
    Strip noise from HTML and truncate to max_chars.

    Steps (in order):
      1. Remove HTML comments
      2. Replace <script>…</script> body with a 1-line placeholder
      3. Replace <style>…</style> body with a 1-line placeholder
      4. Remove base64 data URIs from src/href attributes
      5. Truncate long attribute values (SVG path data, encoded blobs)
      6. Collapse runs of blank lines (3+ → 1)
      7. Smart-truncate to max_chars
    """
    h = html
    h = _strip_html_comments(h)
    h = _strip_script_bodies(h)
    h = _strip_style_bodies(h)
    h = _strip_svg_bodies(h)
    h = _strip_base64_uris(h)
    h = _truncate_long_attrs(h)
    h = _collapse_blank_lines(h)
    h = _strip_empty_tags(h)
    h = _smart_truncate(h, max_chars)
    return h


# Convenience alias matching the old supervisor function name
def smart_truncate_for_analysis(html: str, max_chars: int) -> str:
    return preprocess_for_analysis(html, max_chars)


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

# Pattern notes:
#   re.DOTALL  — . matches newlines (needed for multi-line blocks)
#   re.IGNORECASE — handles <SCRIPT>, <Script>, etc.

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_SCRIPT_RE  = re.compile(
    r"(<script\b[^>]*>)(.*?)(</script\s*>)",
    re.DOTALL | re.IGNORECASE,
)
_STYLE_RE   = re.compile(
    r"(<style\b[^>]*>)(.*?)(</style\s*>)",
    re.DOTALL | re.IGNORECASE,
)
_SVG_RE = re.compile(
    r"(<svg\b[^>]*>)(.*?)(</svg\s*>)",
    re.DOTALL | re.IGNORECASE,
)

# data:image/...;base64,<long string>  or  data:application/...;base64,...
_BASE64_RE  = re.compile(
    r'(src|href|poster|srcset)=(["\'])data:[^;]+;base64,[A-Za-z0-9+/=]+\2',
    re.IGNORECASE,
)

# Attribute values longer than 200 chars that are NOT aria-*, alt, title, or value
# (those are useful for accessibility analysis)
_LONG_ATTR_RE = re.compile(
    r'''(?<!\baria-)(?<!\balt=)(?<!\btitle=)(?<!\bvalue=)
        ([\w-]+=)                  # attribute name=
        (["\'])                    # opening quote
        ([^"']{201,})              # value longer than 200 chars
        \2                         # closing quote
    ''',
    re.VERBOSE | re.IGNORECASE,
)


def _strip_html_comments(html: str) -> str:
    return _COMMENT_RE.sub("", html)


def _strip_script_bodies(html: str) -> str:
    """Replace <script>…</script> body with a short placeholder."""
    def _replace(m: re.Match) -> str:
        open_tag  = m.group(1)
        body      = m.group(2)
        close_tag = m.group(3)
        if not body.strip():
            return m.group(0)  # empty script — keep as-is
        lines = body.count("\n") + 1
        return f"{open_tag}/* [{lines} lines of JS omitted] */{close_tag}"
    return _SCRIPT_RE.sub(_replace, html)


def _strip_style_bodies(html: str) -> str:
    """Replace <style>…</style> body with a short placeholder."""
    def _replace(m: re.Match) -> str:
        open_tag  = m.group(1)
        body      = m.group(2)
        close_tag = m.group(3)
        if not body.strip():
            return m.group(0)
        lines = body.count("\n") + 1
        return f"{open_tag}/* [{lines} lines of CSS omitted] */{close_tag}"
    return _STYLE_RE.sub(_replace, html)


def _strip_svg_bodies(html: str) -> str:
    """Replace <svg>…</svg> body with a short placeholder to save massive SVGs token usage."""
    def _replace(m: re.Match) -> str:
        open_tag  = m.group(1)
        close_tag = m.group(3)
        return f"{open_tag}<!-- SVG icon omitted -->{close_tag}"
    return _SVG_RE.sub(_replace, html)


def _strip_base64_uris(html: str) -> str:
    """Replace base64 data URIs with a short token."""
    return _BASE64_RE.sub(r'\1=\2[base64-data-omitted]\2', html)


def _strip_empty_tags(html: str) -> str:
    """Iteratively remove empty generic UI wrappers like <div></div> and <span></span> to save tokens."""
    pattern = re.compile(r"<(div|span)(?:\s+class=[\"'][^\"']*[\"'])?\s*>\s*</\1>", re.IGNORECASE)
    prev = None
    while html != prev:
        prev = html
        html = pattern.sub("", html)
    return html


def _truncate_long_attrs(html: str, max_val_len: int = 200) -> str:
    """
    Truncate attribute values longer than max_val_len characters,
    preserving the first 80 chars as context.
    Skips aria-*, alt, title, value — those are needed for a11y analysis.
    """
    def _replace(m: re.Match) -> str:
        attr  = m.group(1)   # e.g. "d="
        quote = m.group(2)
        val   = m.group(3)
        # Don't truncate accessibility-relevant attributes
        attr_name = attr.rstrip("=").lower()
        if attr_name in ("aria-label", "aria-labelledby", "aria-describedby",
                         "aria-description", "alt", "title", "value",
                         "placeholder", "name", "id", "class"):
            return m.group(0)
        preview = val[:80]
        return f'{attr}{quote}{preview}…[{len(val) - 80} chars omitted]{quote}'

    return _LONG_ATTR_RE.sub(_replace, html)


def _collapse_blank_lines(html: str) -> str:
    """Collapse 3+ consecutive blank lines into a single blank line."""
    return re.sub(r"\n{3,}", "\n\n", html)


def _smart_truncate(html: str, max_chars: int) -> str:
    """
    Truncate to max_chars while preserving the most useful structure.

    Priority (kept in order):
      1. Full <head> (contains meta, title, link tags — low token cost after stripping)
      2. As much of <body> as the budget allows, starting from the top
         (interactive elements appear early in most UIs)

    If the stripped HTML already fits, returns it unchanged.
    """
    if len(html) <= max_chars:
        return html

    head_end = html.find("</head>")
    if head_end > 0 and head_end < max_chars:
        head_part   = html[:head_end + 7]
        body_budget = max_chars - len(head_part) - 20
        body_start  = html.find("<body", head_end)
        if body_start > 0 and body_budget > 200:
            return (
                head_part
                + "\n"
                + html[body_start : body_start + body_budget]
                + "\n[... body truncated ...]"
            )

    return html[:max_chars] + "\n[... truncated ...]"