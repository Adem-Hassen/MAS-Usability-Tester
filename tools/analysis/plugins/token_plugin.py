# tools/analysis/plugins/token_plugin.py

from tools.analysis.plugin_base import AnalysisPlugin, plugin_registry
from core.state import PageContext

class TokenPlugin(AnalysisPlugin):
    @property
    def plugin_id(self) -> str:
        return "design_token_extractor"

    def run(self, ctx: PageContext) -> PageContext:
        from core.graph import _run_design_tokens
        return _run_design_tokens(ctx)

plugin_registry.register(TokenPlugin())
