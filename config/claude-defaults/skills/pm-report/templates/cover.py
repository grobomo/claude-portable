"""
Cover page and structural page builders for PM reports.
"""

from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, PageBreak, HRFlowable


def cover_page(story, styles, title, subtitle, details=None, footer_lines=None):
    """
    Build a cover page.

    title: main title (e.g., "Trend Micro Vision One")
    subtitle: subtitle (e.g., "API Gap Analysis Report")
    details: list of detail lines (e.g., ["280 APIs vs 17 sections", "Date: March 2, 2026"])
    footer_lines: list of small gray lines at bottom
    """
    story.append(Spacer(1, 1.5*inch))
    story.append(Paragraph(title, styles["CoverTitle"]))
    story.append(Paragraph(subtitle, styles["CoverTitle"]))
    story.append(Spacer(1, 0.3*inch))
    story.append(HRFlowable(width="60%", thickness=2, color=colors.HexColor("#0d47a1")))
    story.append(Spacer(1, 0.3*inch))

    if details:
        for line in details:
            story.append(Paragraph(line, styles["CoverSubtitle"]))

    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", styles["CoverSubtitle"]))

    if footer_lines:
        story.append(Spacer(1, 1*inch))
        for line in footer_lines:
            story.append(Paragraph(line, styles["SmallGray"]))

    story.append(PageBreak())


def table_of_contents(story, styles, items):
    """
    Build a table of contents page.

    items: list of section title strings
    """
    story.append(Paragraph("Table of Contents", styles["SectionHeader"]))
    for item in items:
        story.append(Paragraph(item, styles["Body"]))
    story.append(PageBreak())


def section_header(story, styles, title):
    """Add a numbered section header."""
    story.append(Paragraph(title, styles["SectionHeader"]))


def sub_header(story, styles, title):
    """Add a sub-section header."""
    story.append(Paragraph(title, styles["SubHeader"]))


def priority_header(story, styles, title):
    """Add a priority-level header (red)."""
    story.append(Paragraph(title, styles["PriorityHeader"]))


def body_text(story, styles, text):
    """Add body text."""
    story.append(Paragraph(text, styles["Body"]))


def page_break(story):
    """Insert a page break."""
    story.append(PageBreak())


def spacer(story, height=8):
    """Insert vertical space."""
    story.append(Spacer(1, height))


def horizontal_rule(story):
    """Insert a horizontal line."""
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))


def footer_text(story, styles, text):
    """Add small gray footer text."""
    story.append(Paragraph(text, styles["SmallGray"]))
