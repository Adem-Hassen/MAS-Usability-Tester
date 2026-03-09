# agents/persona/html_sandbox.py

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Optional

from schemas.persona_schema import PersonaProfile
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_sandbox(
    html_content: str,
    persona: PersonaProfile,
    html_source_path: str,
) -> tuple[str, str]:
    """
    Build a sandboxed HTML file tailored to a persona's task.

    Args:
        html_content:     Full raw HTML of the UI.
        persona:          The persona whose task determines what to include.
        html_source_path: Original file path — used to resolve relative assets.

    Returns:
        (sandbox_path, sandbox_html)
          sandbox_path — absolute path to the temp .html file to load in Playwright
          sandbox_html — the HTML string (for logging/debugging)
    """
    sandboxed = _build_sandboxed_html(html_content, persona, html_source_path)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=f"__{persona.persona_id}.html",
        prefix="ui_eval_sandbox__",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(sandboxed)
    tmp.flush()
    tmp.close()

    logger.debug(
        "sandbox.built",
        persona_id=persona.persona_id,
        original_chars=len(html_content),
        sandboxed_chars=len(sandboxed),
        reduction_pct=round((1 - len(sandboxed) / max(len(html_content), 1)) * 100, 1),
        path=tmp.name,
    )

    return tmp.name, sandboxed


def cleanup_sandbox(sandbox_path: str) -> None:
    """
    Delete the sandbox temp file.
    Always call this after the persona's browser context closes.
    """
    try:
        Path(sandbox_path).unlink(missing_ok=True)
        logger.debug("sandbox.cleaned", path=sandbox_path)
    except Exception as e:
        logger.warning("sandbox.cleanup_failed", path=sandbox_path, error=str(e))


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build_sandboxed_html(
    html_content: str,
    persona: PersonaProfile,
    html_source_path: str,
) -> str:
    head = _extract_head(html_content)
    body = _extract_body(html_content)

    base_dir = str(Path(html_source_path).parent.resolve())
    head = _rewrite_relative_urls(head, base_dir)
    body = _rewrite_relative_urls(body, base_dir)

    relevant_body = _extract_relevant_sections(body, persona)

    sandbox_comment = (
        f"<!-- UI-EVAL SANDBOX | persona={persona.persona_id} "
        f"| goal={persona.task_goal[:80]} "
        f"| entry={persona.entry_point or 'top'} -->"
    )

    return (
        f"<!DOCTYPE html>\n"
        f"<html lang=\"en\">\n"
        f"{head}\n"
        f"<body>\n"
        f"{sandbox_comment}\n"
        f"{relevant_body}\n"
        f"</body>\n"
        f"</html>"
    )


# ---------------------------------------------------------------------------
# Relevance detection
# ---------------------------------------------------------------------------

def _extract_relevant_sections(body_html: str, persona: PersonaProfile) -> str:
    """
    Return only the body sections relevant to the persona's task.

    For small pages (< 3 KB) or when no sections can be identified,
    returns the full body as a safe fallback.
    """
    # Small pages: always return full body — nothing to trim
    if len(body_html) < 3000:
        return body_html

    sections = _split_body_into_sections(body_html)
    if len(sections) <= 1:
        return body_html

    keywords = _task_keywords(persona)
    relevant = [s for s in sections if _is_relevant(s, persona.entry_point, keywords)]

    if not relevant:
        logger.debug(
            "sandbox.fallback_full_body",
            persona_id=persona.persona_id,
            reason="no sections matched relevance criteria",
        )
        return body_html

    logger.debug(
        "sandbox.sections_selected",
        persona_id=persona.persona_id,
        total=len(sections),
        selected=len(relevant),
    )
    return "\n".join(relevant)


def _task_keywords(persona: PersonaProfile) -> set[str]:
    """
    Extract meaningful lowercase keywords from the persona's task definition.
    Used for section relevance scoring.
    """
    text = " ".join([
        persona.task_goal,
        persona.task_context,
        " ".join(persona.success_criteria),
        persona.entry_point or "",
    ])
    stopwords = {
        "the", "a", "an", "to", "and", "or", "is", "in", "on", "at",
        "it", "be", "of", "for", "with", "this", "that", "my", "me",
        "i", "you", "we", "by", "as", "are", "can", "will", "after",
        "when", "their", "they", "from", "has", "have", "was", "were",
    }
    words = {
        w.lower()
        for w in re.split(r"[^a-zA-Z0-9#._-]+", text)
        if len(w) > 2
    }
    return words - stopwords


def _is_relevant(
    section_html: str,
    entry_point: Optional[str],
    keywords: set[str],
) -> bool:
    """
    Return True if this HTML section should be included in the sandbox.

    Inclusion rules (any one match = include):
      1. Contains a structural landmark (form, nav, main, header, footer)
      2. Contains the persona's entry_point element
      3. Text content overlaps with task keywords
    """
    lower = section_html.lower()

    # Rule 1: structural landmarks — almost always task-relevant
    landmarks = [
        "<form", "<nav", "<main", "<header", "<footer",
        "role=\"main\"", "role=\"navigation\"", "role=\"banner\"",
        "role=\"form\"", "role=\"search\"",
    ]
    if any(tag in lower for tag in landmarks):
        return True

    # Rule 2: entry_point selector match
    if entry_point:
        id_m    = re.search(r"#([\w-]+)", entry_point)
        cls_m   = re.search(r"\.([\w-]+)", entry_point)
        tag_m   = re.match(r"^([a-z]+[\w-]*)", entry_point)

        if id_m and (f'id="{id_m.group(1)}"' in lower or f"id='{id_m.group(1)}'" in lower):
            return True
        if cls_m and cls_m.group(1) in lower:
            return True
        if tag_m and f"<{tag_m.group(1)}" in lower:
            return True

    # Rule 3: keyword overlap in visible text
    text_only = re.sub(r"<[^>]+>", " ", section_html).lower()
    word_set  = set(re.split(r"[^a-zA-Z0-9]+", text_only))
    if keywords & word_set:
        return True

    return False


def _split_body_into_sections(body_html: str) -> list[str]:
    """
    Split body HTML into top-level block sections for relevance scoring.
    Splits on opening tags of major block elements.
    Returns the full body as a single-element list if no splits are found.
    """
    block_pattern = r"(?i)(?=<(div|section|article|nav|main|header|footer|form|aside)\b)"
    parts = re.split(block_pattern, body_html)

    # re.split with a lookahead leaves the tag name as alternating captures — filter those out
    sections = [p.strip() for p in parts if p.strip() and not re.fullmatch(r"[a-zA-Z]+", p.strip())]

    return sections if sections else [body_html]


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _extract_head(html: str) -> str:
    """Extract the full <head>...</head> block, or return a minimal fallback."""
    m = re.search(r"<head[^>]*>(.*?)</head>", html, re.DOTALL | re.IGNORECASE)
    return f"<head>{m.group(1)}</head>" if m else "<head><meta charset='UTF-8'></head>"


def _extract_body(html: str) -> str:
    """Extract the content inside <body>...</body>."""
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else html


def _rewrite_relative_urls(html: str, base_dir: str) -> str:
    """
    Rewrite relative src= and href= attribute values to absolute file:// URLs.
    This ensures CSS, JS, and images load correctly when the sandbox HTML
    is served from /tmp instead of the original directory.
    """
    base_uri = f"file://{base_dir}/"

    def replace(m: re.Match) -> str:
        attr, quote, url = m.group(1), m.group(2), m.group(3)
        # Leave already-absolute URLs untouched
        if url.startswith(("http://", "https://", "file://", "//", "#", "data:", "javascript:")):
            return m.group(0)
        return f"{attr}={quote}{base_uri}{url}{quote}"

    return re.sub(
        r'(src|href)=(["\'])(?!http|https|file://|//|#|data:|javascript:)(.*?)\2',
        replace,
        html,
        flags=re.IGNORECASE,
    )