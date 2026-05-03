# tools/analysis/plugins/audit_plugin.py

from tools.analysis.plugin_base import AnalysisPlugin, plugin_registry
from tools.analysis.audit_engine import AuditEngine
from core.state import PageContext

class AuditPlugin(AnalysisPlugin):
    @property
    def plugin_id(self) -> str:
        return "axe_core_audit"

    def run(self, ctx: PageContext) -> PageContext:
        # Reusing the existing node logic but wrapped as a plugin
        from core.graph import _run_audit
        return _run_audit(ctx)

plugin_registry.register(AuditPlugin())
