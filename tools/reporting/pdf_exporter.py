# tools/reporting/pdf_exporter.py
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from schemas.report_schema import DiagnosticReport
from monitoring.logger import get_logger
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
logger = get_logger(__name__)
class PDFExporter:
    """
    Exports DiagnosticReport to a professional PDF format using ReportLab.
    """
    def export(self, report: DiagnosticReport, output_path: Path) -> Path:
        """
        Generates a PDF file from the report.
        """
        doc = SimpleDocTemplate(str(output_path), pagesize=LETTER)
        styles = getSampleStyleSheet()
        story = []
        # Styles
        title_style = styles['Title']
        heading_style = styles['Heading2']
        subheading_style = styles['Heading3']
        normal_style = styles['Normal']
        code_style = ParagraphStyle('Code', parent=normal_style, fontName='Courier', fontSize=8, leftIndent=20)
        # Title
        story.append(Paragraph("UI Usability & Accessibility Diagnostic Report", title_style))
        story.append(Spacer(1, 12))
        
        # Meta Info Table
        meta_data = [
            ["Report ID", report.report_id],
            ["Timestamp", report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')],
            ["Target Page", report.html_source_path],
            ["Overall Quality Score", f"{report.overall_score}/10"]
        ]
        t = Table(meta_data, colWidths=[120, 350])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 24))
        # Executive Summary
        story.append(Paragraph("Executive Summary", heading_style))
        story.append(Paragraph(report.executive_summary, normal_style))
        story.append(Spacer(1, 12))
        # Top Recommendations
        story.append(Paragraph("Top Recommendations", heading_style))
        for i, rec in enumerate(report.top_recommendations, 1):
            story.append(Paragraph(f"{i}. {rec}", normal_style))
        story.append(Spacer(1, 12))
        # Severity Breakdown Table
        story.append(Paragraph("Issue Severity Breakdown", heading_style))
        sev = report.severity_breakdown
        sev_data = [
            ["Severity", "Count"],
            ["Critical", str(sev.critical)],
            ["High", str(sev.high)],
            ["Medium", str(sev.medium)],
            ["Low", str(sev.low)],
            ["TOTAL", str(report.total_issues_found)]
        ]
        st = Table(sev_data, colWidths=[100, 100])
        st.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 1), (0, 1), colors.orangered), # Critical
            ('BACKGROUND', (0, 2), (0, 2), colors.orange),    # High
        ]))
        story.append(st)
        story.append(Spacer(1, 24))
        # Clusters
        if report.issue_clusters:
            story.append(Paragraph("Detected Issue Clusters", heading_style))
            for cluster in report.issue_clusters:
                story.append(Paragraph(f"[{cluster.dominant_severity.upper()}] {cluster.cluster_label}", subheading_style))
                story.append(Paragraph(f"<b>Summary:</b> {cluster.representative_description}", normal_style))
                story.append(Paragraph(f"<b>Affected Elements:</b> {', '.join(cluster.affected_elements)}", normal_style))
                story.append(Spacer(1, 6))
        # Remediation
        story.append(PageBreak())
        story.append(Paragraph("Remediation & Verification", heading_style))
        rem_data = [
            ["Metric", "Value"],
            ["Total Patches Applied", str(report.total_patches_applied)],
            ["Issues Resolved", str(report.issues_resolved_count)],
            ["Issues Remaining", str(report.issues_remaining_count)],
            ["Verification Passed", "YES" if report.verification_passed else "NO"]
        ]
        rt = Table(rem_data, colWidths=[200, 100])
        rt.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (1, 4), (1, 4), colors.lightgreen if report.verification_passed else colors.lightpink),
        ]))
        story.append(rt)
        story.append(Spacer(1, 24))
        # Audit Results
        if report.audit_results:
            story.append(Paragraph("Automated Accessibility Audit (axe-core)", heading_style))
            story.append(Paragraph(f"Found {len(report.audit_results)} accessibility violations.", normal_style))
            for violation in report.audit_results[:10]: # Limit for PDF length
                story.append(Paragraph(f"[{violation.get('impact', 'unknown').upper()}] {violation.get('id')}", subheading_style))
                story.append(Paragraph(violation.get('description', ''), normal_style))
                story.append(Spacer(1, 6))
        doc.build(story)
        logger.info("pdf_exporter.exported", path=str(output_path))
        return output_path