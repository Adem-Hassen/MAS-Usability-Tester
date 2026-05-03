# tools/analysis/audit_engine.py

from pathlib import Path
from typing import Any, Dict, List
import json
import os

from agents.persona.playwright_engine import PlaywrightEngine
from config.logging_config import setup_logging
from monitoring.logger import get_logger

logger = get_logger(__name__)

AXE_CORE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
AXE_LOCAL_PATH = Path("tools/axe.min.js")

class AuditEngine:
    """
    Proactive accessibility audit engine using axe-core.
    Runs separately from personas to provide objective baseline data.
    """

    def __init__(self):
        self._ensure_axe_core()

    def _ensure_axe_core(self):
        """Check for local axe-core or prepare to download it."""
        if not AXE_LOCAL_PATH.parent.exists():
            AXE_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        if not AXE_LOCAL_PATH.exists():
            logger.info("audit_engine.axe_not_found", path=str(AXE_LOCAL_PATH))
            # We don't download here to avoid blocking, the runner will handle CDN fallback if needed.

    def run_audit(self, html_path: str) -> List[Dict[str, Any]]:
        """
        Runs axe-core audit on a given HTML file.
        Returns a list of violations.
        """
        violations = []
        try:
            with PlaywrightEngine(persona_id="audit_node") as engine:
                engine.open(html_path)
                page = engine._page
                
                # 1. Inject axe-core
                if AXE_LOCAL_PATH.exists():
                    page.add_script_tag(path=str(AXE_LOCAL_PATH))
                    logger.debug("audit_engine.axe_injected_locally")
                else:
                    page.add_script_tag(url=AXE_CORE_URL)
                    logger.warning("audit_engine.axe_injected_via_cdn")

                # 2. Run axe.run()
                # We wait for it to be defined just in case
                page.wait_for_function("() => typeof axe !== 'undefined'")
                
                results = page.evaluate("async () => { return await axe.run(); }")
                violations = results.get("violations", [])
                
                logger.info("audit_engine.completed", 
                            path=html_path, 
                            violations=len(violations))
                
        except Exception as e:
            logger.error("audit_engine.error", error=str(e), path=html_path)
            
        return violations

def audit_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node for proactive accessibility auditing.
    """
    html_path = state.get("html_source_path")
    if not html_path:
        return {}

    engine = AuditEngine()
    violations = engine.run_audit(html_path)
    
    return {"audit_results": violations}
