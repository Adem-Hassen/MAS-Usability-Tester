# agents/persona/playwright_engine.py
"""
Playwright Engine.

Manages one isolated Chromium browser context per persona.
Exposes three operations used by the Perceive → Decide → Act loop:

  open(sandbox_path)   — launch browser, load sandboxed HTML
  get_page_state()     — return DOMState snapshot of what is visible
  execute_action(...)  — run one action, return ActionResult
  close()              — tear down context and browser

Design:
  - One BrowserContext per persona = fully isolated cookies, storage, JS heap.
    Parallel personas cannot interfere with each other.
  - Page state uses a compact structured summary (not raw HTML) to keep
    LLM decision prompts small. The LLM sees visible elements + text.
  - execute_action() never raises. All Playwright errors are caught and
    returned in ActionResult.success=False so the agent loop handles them.
  - Screenshots taken after every action (base64 PNG) for debug traces.
  - JS alerts are auto-dismissed and captured so they don't block the loop.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import (
    Browser, BrowserContext, Page, Playwright, sync_playwright,
    TimeoutError as PlaywrightTimeout, Error as PlaywrightError,
)

from config.settings import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VisibleElement:
    tag: str
    selector: str
    text: str
    input_type: Optional[str] = None
    is_focused: bool = False
    is_disabled: bool = False
    bounding_box: Optional[dict] = None
    aria_role: Optional[str] = None
    aria_label: Optional[str] = None


@dataclass
class DOMState:
    """
    Compact structured snapshot of the current page state.
    Passed to the persona LLM at each decision step.
    """
    url: str
    page_title: str
    visible_text: str
    interactive_elements: list
    focused_element_selector: Optional[str]
    scroll_position: dict
    page_height: int
    viewport_height: int
    has_modal: bool
    alert_text: Optional[str]
    # Sections hidden by CSS (display:none) but present in DOM.
    # Common in JS tab/SPA UIs where sections swap visibility on nav click.
    # Each entry: {id, label, activate_via, contains}
    hidden_sections: list

    @property
    def scroll_pct(self) -> int:
        """How far down the page the user has scrolled (0-100)."""
        if self.page_height <= self.viewport_height:
            return 100
        scrollable = self.page_height - self.viewport_height
        return min(100, int(self.scroll_position["y"] / scrollable * 100))

    def to_prompt_string(self) -> str:
        lines = [
            f"URL: {self.url}",
            f"Title: {self.page_title}",
            f"Scroll: {self.scroll_position['y']}px / {self.page_height}px total "
            f"({self.scroll_pct}% down)",
        ]
        if self.alert_text:
            lines.append(f"⚠ ALERT DIALOG: {self.alert_text}")
        if self.has_modal:
            lines.append("⚠ A modal/dialog is currently open")

        if self.visible_text.strip():
            text = self.visible_text[:1500]
            if len(self.visible_text) > 1500:
                text += " ... [truncated]"
            lines.append(f"\nVISIBLE TEXT:\n{text}")

        if self.interactive_elements:
            lines.append(f"\nINTERACTIVE ELEMENTS ({len(self.interactive_elements)}):")
            for el in self.interactive_elements:
                label     = (el.aria_label or el.text or "")[:60].strip()
                type_hint = f" [{el.input_type}]" if el.input_type else ""
                role_hint = f" role={el.aria_role}" if el.aria_role else ""
                disabled  = " DISABLED" if el.is_disabled else ""
                focused   = " FOCUSED" if el.is_focused else ""
                lines.append(
                    f"  <{el.tag}{type_hint}>{role_hint}{disabled}{focused}\n"
                    f"    selector: {el.selector}\n"
                    f"    label:    {label or '(none)'}"
                )
        else:
            lines.append("\nNo interactive elements visible.")

        # Always show hidden sections — critical for JS-tab / SPA UIs
        if self.hidden_sections:
            lines.append(
                f"\nHIDDEN SECTIONS ({len(self.hidden_sections)}) "
                f"— exist in DOM but not yet visible (display:none).\n"
                f"  ↳ Scrolling will NOT reveal them. Click the nav link to activate."
            )
            for hs in self.hidden_sections:
                lines.append(
                    f"  #{hs['id']}  label={hs['label']!r}  "
                    f"activate_via={hs['activate_via']!r}  "
                    f"contains: {hs['contains']}"
                )

        return "\n".join(lines)


@dataclass
class ActionResult:
    success: bool
    action_type: str
    target_selector: Optional[str]
    value: Optional[str]
    error_message: Optional[str] = None
    element_html: Optional[str] = None
    screenshot_b64: Optional[str] = None
    new_url: Optional[str] = None
    elapsed_ms: int = 0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PlaywrightEngine:
    """
    One isolated Chromium browser context for one persona.

    Use as a context manager:
        with PlaywrightEngine(persona_id) as engine:
            engine.open(sandbox_path)
            state  = engine.get_page_state()
            result = engine.execute_action("click", "#submit")
    """

    def __init__(self, persona_id: str):
        self.persona_id = persona_id
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._pending_alert: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self, sandbox_path: str, storage_seed: Optional[dict] = None) -> None:
        """
        Launch browser, seed storage, and load the sandbox page.

        Args:
            sandbox_path:  Path to the sandboxed HTML file (absolute or file://).
            storage_seed:  Optional dict with keys:
                             "localStorage"   → {key: value, ...}
                             "sessionStorage" → {key: value, ...}
                           Injected via Playwright init script so they are available
                           before any page JS runs — preventing auth-guard redirects.
        """
        action_ms = int(settings.persona_action_timeout_seconds * 1000)
        nav_ms    = int(settings.persona_page_load_timeout_seconds * 1000)

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=settings.persona_headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="America/New_York",
        )
        self._context.set_default_timeout(action_ms)
        self._context.set_default_navigation_timeout(nav_ms)

        # Seed localStorage / sessionStorage BEFORE page JS runs.
        # This prevents auth guards from redirecting to a missing login page.
        if storage_seed:
            import json as _json
            ls  = storage_seed.get("localStorage",   {})
            ss  = storage_seed.get("sessionStorage", {})
            if ls or ss:
                script = f"""
                (function() {{
                    const ls = {_json.dumps(ls)};
                    const ss = {_json.dumps(ss)};
                    for (const [k, v] of Object.entries(ls)) {{ localStorage.setItem(k, v); }}
                    for (const [k, v] of Object.entries(ss)) {{ sessionStorage.setItem(k, v); }}
                }})();
                """
                self._context.add_init_script(script)
                logger.debug(
                    "browser.storage_seeded",
                    persona_id=self.persona_id,
                    localStorage_keys=list(ls.keys()),
                    sessionStorage_keys=list(ss.keys()),
                )

        self._page = self._context.new_page()
        self._page.on("dialog", self._handle_dialog)

        url = sandbox_path if sandbox_path.startswith("file://") else f"file://{sandbox_path}"
        self._page.goto(url, wait_until="domcontentloaded")

        # Post-load check: if the page redirected to an error/missing page,
        # log a warning so the agent knows the page didn't load correctly.
        final_url   = self._page.url
        page_title  = self._page.title()
        elem_count  = self._page.evaluate("() => document.querySelectorAll('a,button,input,select,textarea').length")
        if elem_count == 0 and final_url != url:
            logger.warning(
                "browser.page_redirected_to_error",
                persona_id=self.persona_id,
                original_url=url,
                final_url=final_url,
                hint="Page redirected (possibly auth guard). Consider passing storage_seed to open().",
            )

        logger.info("browser.opened", persona_id=self.persona_id,
                    title=page_title, url=final_url, interactive_elements=elem_count)

    def close(self) -> None:
        try:
            if self._context:    self._context.close()
            if self._browser:    self._browser.close()
            if self._playwright: self._playwright.stop()
        except Exception as e:
            logger.warning("browser.close_error", persona_id=self.persona_id, error=str(e))
        finally:
            self._page = self._context = self._browser = self._playwright = None
        logger.debug("browser.closed", persona_id=self.persona_id)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # Perceive
    # ------------------------------------------------------------------

    def get_page_state(self) -> DOMState:
        """Structured snapshot of current visible page — called before every LLM step."""
        assert self._page, "Call open() first."
        page = self._page

        scroll      = page.evaluate("() => ({x: window.scrollX, y: window.scrollY})")
        page_height = page.evaluate("() => document.documentElement.scrollHeight")
        viewport    = page.viewport_size or {"width": 1280, "height": 720}

        has_modal = page.evaluate("""() => {
            const sel = '[role="dialog"],[role="alertdialog"],.modal,.dialog,[aria-modal="true"]';
            return Array.from(document.querySelectorAll(sel)).some(el => {
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            });
        }""")

        visible_text = page.evaluate("""() => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let text = '', node;
            while ((node = walker.nextNode())) {
                const p = node.parentElement;
                if (!p) continue;
                const s = window.getComputedStyle(p);
                if (s.display === 'none' || s.visibility === 'hidden') continue;
                const t = node.textContent.trim();
                if (t) text += t + ' ';
            }
            return text.trim();
        }""")

        focused_sel = page.evaluate("""() => {
            const el = document.activeElement;
            if (!el || el === document.body) return null;
            return el.id ? '#' + el.id : el.tagName.toLowerCase();
        }""")

        hidden_sections = self._extract_hidden_sections()

        return DOMState(
            url=page.url,
            page_title=page.title(),
            visible_text=visible_text,
            interactive_elements=self._extract_interactive_elements(),
            focused_element_selector=focused_sel,
            scroll_position=scroll,
            page_height=page_height,
            viewport_height=viewport["height"],
            has_modal=has_modal,
            alert_text=self._pending_alert,
            hidden_sections=hidden_sections,
        )

    def _extract_hidden_sections(self) -> list:
        """
        Find elements that are hidden via display:none but exist in the DOM.
        For each one, try to find the nav/button that would reveal it.
        Returns a list of dicts: {id, label, activate_via, contains}.
        """
        return self._page.evaluate("""() => {
            const results = [];
            const hidden = document.querySelectorAll(
                '[id]:not([id=""])' 
            );
            for (const el of hidden) {
                const style = window.getComputedStyle(el);
                if (style.display !== 'none') continue;

                // Skip tiny utility elements (scripts, templates, etc.)
                const tag = el.tagName.toLowerCase();
                if (['script','style','template','meta','link'].includes(tag)) continue;
                const rect = el.getBoundingClientRect();
                // Hidden sections have 0 height — but we still want them
                const textContent = el.textContent.trim().slice(0, 80);
                if (!textContent) continue;

                // Find a nav link or button that references this id
                const id = el.id;
                let activateVia = null;
                const candidates = [
                    ...document.querySelectorAll(
                        `a[href="#${id}"], a[data-section="${id}"], ` +
                        `button[data-section="${id}"], [data-target="#${id}"], ` +
                        `[aria-controls="${id}"], [href="#${id}"]`
                    )
                ];
                if (candidates.length > 0) {
                    const c = candidates[0];
                    if (c.id)        activateVia = '#' + c.id;
                    else if (c.name) activateVia = c.tagName.toLowerCase() + '[name="' + c.name + '"]';
                    else {
                        const cls = c.className.trim().split(/\\s+/)[0];
                        activateVia = cls
                            ? c.tagName.toLowerCase() + '.' + cls
                            : c.tagName.toLowerCase();
                    }
                }

                // What does this section contain?
                const inputs = el.querySelectorAll('input,textarea,select,button');
                const inputDesc = inputs.length
                    ? Array.from(inputs).slice(0,4).map(i =>
                        (i.placeholder || i.type || i.tagName.toLowerCase())
                      ).join(', ')
                    : 'text content only';

                results.push({
                    id,
                    label: el.querySelector('h1,h2,h3,h4,legend')?.textContent?.trim()
                           || el.getAttribute('aria-label')
                           || id,
                    activate_via: activateVia,
                    contains: inputDesc,
                });
                if (results.length >= 10) break;
            }
            return results;
        }""")

    def _extract_interactive_elements(self) -> list:
        raw = self._page.evaluate("""() => {
            const SELECTORS = [
                'a[href]','button:not([disabled])','input','select','textarea',
                '[role="button"]','[role="link"]','[role="checkbox"]',
                '[role="radio"]','[role="menuitem"]',
                '[tabindex]:not([tabindex="-1"])'
            ];
            const seen = new Set(), out = [];
            for (const sel of SELECTORS) {
                for (const el of document.querySelectorAll(sel)) {
                    if (seen.has(el)) continue;
                    seen.add(el);
                    const rect = el.getBoundingClientRect();
                    const s    = window.getComputedStyle(el);
                    if (s.display==='none'||s.visibility==='hidden'||
                        s.opacity==='0'||rect.width===0) continue;

                    let selector = el.tagName.toLowerCase();
                    if      (el.id)          selector = '#' + el.id;
                    else if (el.name)        selector = el.tagName.toLowerCase()+'[name="'+el.name+'"]';
                    else if (el.className) {
                        const cls = el.className.trim().split(/\\s+/)[0];
                        if (cls) selector = el.tagName.toLowerCase()+'.'+cls;
                    }
                    out.push({
                        tag:       el.tagName.toLowerCase(),
                        selector:  selector,
                        text:      (el.innerText||el.value||el.placeholder||'').trim().slice(0,80),
                        inputType: el.type||null,
                        disabled:  el.disabled||el.getAttribute('aria-disabled')==='true',
                        focused:   el===document.activeElement,
                        ariaRole:  el.getAttribute('role'),
                        ariaLabel: el.getAttribute('aria-label'),
                        bbox: {x:Math.round(rect.x), y:Math.round(rect.y),
                               w:Math.round(rect.width), h:Math.round(rect.height)},
                    });
                    if (out.length >= 50) return out;
                }
            }
            return out;
        }""")
        return [
            VisibleElement(
                tag=r["tag"], selector=r["selector"], text=r["text"] or "",
                input_type=r.get("inputType"), is_focused=r.get("focused", False),
                is_disabled=r.get("disabled", False), bounding_box=r.get("bbox"),
                aria_role=r.get("ariaRole"), aria_label=r.get("ariaLabel"),
            )
            for r in (raw or [])
        ]

    # ------------------------------------------------------------------
    # Act
    # ------------------------------------------------------------------

    def execute_action(
        self,
        action_type: str,
        target_selector: Optional[str] = None,
        value: Optional[str] = None,
    ) -> ActionResult:
        """Execute one action. Never raises — errors returned in ActionResult."""
        assert self._page, "Call open() first."
        start        = time.time()
        element_html = self._get_element_html(target_selector) if target_selector else None
        self._pending_alert = None

        try:
            if   action_type == "click":            r = self._do_click(target_selector)
            elif action_type == "type":             r = self._do_type(target_selector, value)
            elif action_type == "scroll":           r = self._do_scroll(value)
            elif action_type == "navigate":         r = self._do_navigate(value)
            elif action_type in ("observe","hover"):r = self._do_observe_hover(action_type, target_selector)
            else:
                r = ActionResult(False, action_type, target_selector, value,
                                 error_message=f"Unknown action_type: '{action_type}'")

            r.element_html   = element_html
            r.new_url        = self._page.url
            r.elapsed_ms     = int((time.time() - start) * 1000)
            r.screenshot_b64 = self._take_screenshot()

            log = logger.info if r.success else logger.warning
            log("action.executed", persona_id=self.persona_id,
                action=action_type, selector=target_selector,
                success=r.success, elapsed_ms=r.elapsed_ms, error=r.error_message)
            return r

        except Exception as e:
            logger.warning("action.crash", persona_id=self.persona_id,
                           action=action_type, error=str(e))
            return ActionResult(
                False, action_type, target_selector, value,
                error_message=str(e), element_html=element_html,
                elapsed_ms=int((time.time() - start) * 1000),
                screenshot_b64=self._take_screenshot(),
                new_url=self._page.url if self._page else None,
            )

    def _do_click(self, selector):
        if not selector:
            return ActionResult(False, "click", selector, None,
                                error_message="click requires target_selector")
        try:
            self._page.click(selector)
            return ActionResult(True, "click", selector, None)
        except (PlaywrightTimeout, PlaywrightError) as e:
            return ActionResult(False, "click", selector, None, error_message=str(e))

    def _do_type(self, selector, value):
        if not selector:
            return ActionResult(False, "type", selector, value,
                                error_message="type requires target_selector")
        try:
            self._page.click(selector)
            self._page.fill(selector, value or "")
            return ActionResult(True, "type", selector, value)
        except (PlaywrightTimeout, PlaywrightError) as e:
            return ActionResult(False, "type", selector, value, error_message=str(e))

    def _do_scroll(self, direction):
        delta = -300 if direction == "up" else 300
        self._page.evaluate(f"window.scrollBy(0, {delta})")
        return ActionResult(True, "scroll", None, direction)

    def _do_navigate(self, url):
        if not url:
            return ActionResult(False, "navigate", None, url,
                                error_message="navigate requires a URL in value")

        # Block navigation to external URLs — the sandbox is a local file.
        # External URLs always fail and waste a step; redirect the agent instead.
        current = self._page.url or ""
        is_external = url.startswith("http://") or url.startswith("https://")
        is_same_origin = current.startswith("file://")
        if is_external and is_same_origin:
            logger.info(
                "action.navigate_blocked",
                persona_id=self.persona_id,
                url=url,
                reason="external URL blocked in sandbox — use click on nav links instead",
            )
            return ActionResult(
                False, "navigate", None, url,
                error_message=(
                    f"Navigation to external URL blocked: {url!r}. "
                    "This is a local sandbox — use click on nav/menu links to change sections."
                ),
            )
        try:
            self._page.goto(url, wait_until="domcontentloaded")
            return ActionResult(True, "navigate", None, url)
        except (PlaywrightTimeout, PlaywrightError) as e:
            return ActionResult(False, "navigate", None, url, error_message=str(e))

    def _do_observe_hover(self, action_type, selector):
        if selector:
            try:
                self._page.hover(selector)
            except Exception:
                pass
        return ActionResult(True, action_type, selector, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_element_html(self, selector: str) -> Optional[str]:
        try:
            return self._page.eval_on_selector(selector, "el => el.outerHTML")
        except Exception:
            return None

    def _take_screenshot(self) -> Optional[str]:
        try:
            return base64.b64encode(
                self._page.screenshot(type="png", full_page=False)
            ).decode("utf-8")
        except Exception:
            return None

    def _handle_dialog(self, dialog) -> None:
        self._pending_alert = dialog.message
        logger.debug("browser.dialog", persona_id=self.persona_id,
                     type=dialog.type, message=dialog.message[:100])
        dialog.dismiss()