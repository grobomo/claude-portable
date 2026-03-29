"""
Shared styles and color palette for PM reports.
All reports use these same visual semantics for consistency.
"""

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ---------------------------------------------------------------------------
# Color palette -- consistent semantic meaning across all reports
# ---------------------------------------------------------------------------
class C:
    """Color constants with semantic names."""
    # Status colors
    GREEN = "#2e7d32"       # Working, covered, meeting target
    GREEN_LIGHT = "#388e3c" # Good but not perfect
    YELLOW = "#f9a825"      # Partial, medium, approaching limit
    ORANGE = "#ef6c00"      # Low coverage, below target
    RED = "#b71c1c"         # Gap, missing, broken, critical
    RED_DARK = "#880e4f"    # Zero / worst case

    # UI colors
    BLUE_DARK = "#0d47a1"   # Headers, section titles
    BLUE = "#1565c0"        # Subheaders, links
    GRAY_DARK = "#37474f"   # Table headers (neutral)
    GRAY_MED = "#555555"    # Subtitle text
    GRAY = "#666666"        # Captions
    GRAY_LIGHT = "#888888"  # Metadata, timestamps
    GRAY_VERY_LIGHT = "#999999"  # Footer

    # Backgrounds
    BG_GREEN = "#f0f8f0"
    BG_RED = "#fff0f0"
    BG_BLUE = "#f0f4ff"
    BG_ROW_ALT = "#f5f5f5"
    BORDER_GREEN = "#ccddcc"
    BORDER_RED = "#ddcccc"
    BORDER_LIGHT = "#cccccc"
    BORDER_VERY_LIGHT = "#dddddd"

    TITLE_COLOR = "#1a1a2e"


def build_styles():
    """Create the full stylesheet for PM reports."""
    styles = getSampleStyleSheet()

    defs = [
        ("CoverTitle", "Title", dict(
            fontSize=28, textColor=colors.HexColor(C.TITLE_COLOR),
            spaceAfter=12, alignment=TA_CENTER)),

        ("CoverSubtitle", "Normal", dict(
            fontSize=14, textColor=colors.HexColor(C.GRAY_MED),
            alignment=TA_CENTER, spaceAfter=6)),

        ("SectionHeader", "Heading1", dict(
            fontSize=18, textColor=colors.HexColor(C.BLUE_DARK),
            spaceBefore=20, spaceAfter=10,
            borderWidth=1, borderColor=colors.HexColor(C.BLUE_DARK), borderPadding=4)),

        ("SubHeader", "Heading2", dict(
            fontSize=14, textColor=colors.HexColor(C.BLUE),
            spaceBefore=14, spaceAfter=6)),

        ("PriorityHeader", "Heading2", dict(
            fontSize=15, textColor=colors.HexColor(C.RED),
            spaceBefore=16, spaceAfter=8)),

        ("Body", "Normal", dict(
            fontSize=10, leading=14, spaceAfter=6)),

        ("SmallGray", "Normal", dict(
            fontSize=8, textColor=colors.HexColor(C.GRAY_LIGHT),
            alignment=TA_CENTER)),

        ("ApiOk", "Code", dict(
            fontSize=9, textColor=colors.HexColor("#006400"),
            backColor=colors.HexColor(C.BG_GREEN),
            borderWidth=0.5, borderColor=colors.HexColor(C.BORDER_GREEN),
            borderPadding=4, spaceAfter=4)),

        ("ApiGap", "Code", dict(
            fontSize=9, textColor=colors.HexColor("#8b0000"),
            backColor=colors.HexColor(C.BG_RED),
            borderWidth=0.5, borderColor=colors.HexColor(C.BORDER_RED),
            borderPadding=4, spaceAfter=4)),

        ("DocLink", "Normal", dict(
            fontSize=9, textColor=colors.HexColor(C.BLUE), spaceAfter=2)),

        ("Caption", "Normal", dict(
            fontSize=8, textColor=colors.HexColor(C.GRAY),
            alignment=TA_CENTER, spaceAfter=8, spaceBefore=2)),

        ("Footer", "Normal", dict(
            fontSize=8, textColor=colors.HexColor(C.GRAY_VERY_LIGHT),
            alignment=TA_RIGHT)),

        ("PMBullet", "Normal", dict(
            fontSize=10, leading=14, spaceAfter=3,
            leftIndent=18, bulletIndent=6)),
    ]

    for name, parent, kwargs in defs:
        styles.add(ParagraphStyle(name=name, parent=styles[parent], **kwargs))

    return styles
