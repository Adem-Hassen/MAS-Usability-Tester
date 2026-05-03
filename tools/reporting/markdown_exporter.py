# tools/reporting/markdown_exporter.py
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from schemas.report_schema import DiagnosticReport
from monitoring.logger import get_logger
logger = get_logger(__name__)
class MarkdownExporter:
    """
    Exports DiagnosticReport to a human-readable Markdown format.
    """
    def export(self, report: DiagnosticReport, output_path: Path) -> Path:
        """
        Generates a Markdown file from the report.
        """
        lines = []
        lines.append(f"# UI Usability & Accessibility Diagnostic Report")
        lines.append(f"**Report ID:** `{report.report_id}`")
        lines.append(f"**Timestamp:** {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"**Target Page:** `{report.html_source_path}`")
        lines.append(f"**Overall Quality Score:** `{report.overall_score}/10`")
        lines.append("")
        lines.append(f"## Executive Summary")
        lines.append(report.executive_summary)
        lines.append("")
        lines.append(f"## Top Recommendations")
        for i, rec in enumerate(report.top_recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")
        lines.append(f"## Issue Summary")
        lines.append(f"- **Total Issues Found:** {report.total_issues_found}")
        lines.append(f"- **Severity Breakdown:**")
        lines.append(f"  - Critical: {report.severity_breakdown.critical}")
        lines.append(f"  - High: {report.severity_breakdown.high}")
        lines.append(f"  - Medium: {report.severity_breakdown.medium}")
        lines.append(f"  - Low: {report.severity_breakdown.low}")
        lines.append("")
        if report.issue_clusters:
            lines.append(f"### Detected Issue Clusters")
            for cluster in report.issue_clusters:
                lines.append(f"#### [{cluster.dominant_severity.upper()}] {cluster.cluster_label}")
                lines.append(f"- **Summary:** {cluster.representative_description}")
                lines.append(f"- **Affected Elements:** `{', '.join(cluster.affected_elements)}`")
                lines.append("- **Individual Issues:**")
                for issue in cluster.issues:
                    lines.append(f"  - {issue.title} (ID: `{issue.issue_id}`)")
                lines.append("")
        if report.audit_results:
            lines.append(f"## Automated Audit Results (axe-core)")
            lines.append(f"Found {len(report.audit_results)} accessibility violations.")
            for violation in report.audit_results:
                lines.append(f"### [{violation.get('impact', 'unknown').upper()}] {violation.get('id')}")
                lines.append(f"- **Description:** {violation.get('description')}")
                lines.append(f"- **Help:** {violation.get('help')} [Link]({violation.get('helpUrl')})")
                lines.append("- **Nodes:**")
                for node in violation.get('nodes', [])[:5]: # Limit to first 5
                    lines.append(f"  - `{node.get('target')}`")
            lines.append("")
        lines.append(f"## Remediation Summary")
        lines.append(f"- **Total Patches Applied:** {report.total_patches_applied}")
        lines.append(f"- **Issues Resolved:** {report.issues_resolved_count}")
        lines.append(f"- **Issues Remaining:** {report.issues_remaining_count}")
        lines.append(f"- **Regressions Introduced:** {report.regressions_introduced}")
        lines.append(f"- **Verification Passed:** {'✅ YES' if report.verification_passed else '❌ NO'}")
        lines.append("")
        if report.unified_patch_set and report.unified_patch_set.patches:
            lines.append(f"### Applied Patches")
            for patch in report.unified_patch_set.patches:
                lines.append(f"#### Patch: `{patch.patch_id}`")
                lines.append(f"- **Type:** `{patch.patch_type}`")
                lines.append(f"- **Target:** `{patch.target_element}`")
                lines.append(f"- **Rationale:** {patch.rationale}")
                if patch.css_snippet:
                    lines.append("```css\n" + patch.css_snippet + "\n```")
                if patch.js_snippet:
                    lines.append("```javascript\n" + patch.js_snippet + "\n```")
            lines.append("")
        content = "\n".join(lines)
        output_path.write_text(content, encoding="utf-8")
        logger.info("markdown_exporter.exported", path=str(output_path))
        return output_path