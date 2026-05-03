# tools/analysis/design_token_extractor.py

from typing import Any, Dict, List, Optional
from pathlib import Path

from agents.persona.playwright_engine import PlaywrightEngine
from monitoring.logger import get_logger

logger = get_logger(__name__)

class DesignTokenExtractor:
    """
    Extracts visual design tokens (colors, fonts, spacing) from a live page.
    Provides context to Recommender agents to ensure patches match the UI style.
    """

    def extract_tokens(self, html_path: str) -> Dict[str, Any]:
        """
        Runs token extraction on the page.
        """
        tokens = {
            "colors": {},
            "typography": {},
            "spacing": {},
            "borders": {}
        }
        
        try:
            with PlaywrightEngine(persona_id="design_token_extractor") as engine:
                engine.open(html_path)
                page = engine._page
                
                # Extract CSS variables from :root and body
                tokens["colors"] = page.evaluate("""() => {
                    const styles = window.getComputedStyle(document.documentElement);
                    const bodyStyles = window.getComputedStyle(document.body);
                    
                    const getVar = (name) => styles.getPropertyValue(name).trim() || bodyStyles.getPropertyValue(name).trim();
                    
                    // Common variable names
                    const common = [
                        '--primary', '--secondary', '--accent', '--background', '--foreground',
                        '--primary-color', '--secondary-color', '--text-color', '--bg-color',
                        '--font-main', '--font-heading'
                    ];
                    
                    const results = {};
                    common.forEach(v => {
                        const val = getVar(v);
                        if (val) results[v] = val;
                    });
                    
                    // Fallback: Get base body styles
                    results["body-bg"] = bodyStyles.backgroundColor;
                    results["body-color"] = bodyStyles.color;
                    
                    return results;
                }""")
                
                tokens["typography"] = page.evaluate("""() => {
                    const bodyStyles = window.getComputedStyle(document.body);
                    const h1Styles = window.getComputedStyle(document.querySelector('h1') || document.body);
                    
                    return {
                        "font-family": bodyStyles.fontFamily,
                        "base-size": bodyStyles.fontSize,
                        "heading-font": h1Styles.fontFamily,
                        "heading-weight": h1Styles.fontWeight
                    };
                }""")
                
                tokens["borders"] = page.evaluate("""() => {
                    const button = document.querySelector('button') || document.querySelector('a');
                    if (!button) return {};
                    const s = window.getComputedStyle(button);
                    return {
                        "button-radius": s.borderRadius,
                        "button-border": s.border
                    };
                }""")
                
                logger.info("design_tokens.extracted", path=html_path, tokens=len(tokens["colors"]) + len(tokens["typography"]))
                
        except Exception as e:
            logger.error("design_tokens.error", error=str(e), path=html_path)
            
        return tokens

def design_token_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node for design token extraction.
    """
    html_path = state.get("html_source_path")
    if not html_path:
        return {}

    extractor = DesignTokenExtractor()
    tokens = extractor.extract_tokens(html_path)
    
    return {"design_tokens": tokens}
