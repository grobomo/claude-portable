"""
Visual chart builders for PM reports.
Bar charts, coverage charts rendered as styled tables.
"""

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Table, TableStyle, Paragraph
from .styles import C


# Cell styles for word-wrapping
_cell = ParagraphStyle("_chartCell", fontSize=9, leading=11, spaceAfter=0)
_cell_bold = ParagraphStyle("_chartBold", parent=_cell, fontName="Helvetica-Bold")
_cell_hdr = ParagraphStyle("_chartHdr", parent=_cell_bold, textColor=colors.white)


def bar_chart(items, col_widths=None):
    """
    Build an ASCII bar chart as a styled table.

    items: list of (label, percentage_str, bar_length_0_to_20, hex_color)
    Example: [("Container Security", "100%", 20, "#2e7d32"), ...]

    Returns a Table flowable.
    """
    table_data = [[Paragraph("Area", _cell_hdr), Paragraph("Coverage", _cell_hdr), Paragraph("Visual", _cell_hdr)]]
    for label, pct, blocks, color in items:
        bar_str = "=" * blocks + "." * (20 - blocks)
        table_data.append([Paragraph(label, _cell), pct, bar_str])

    if col_widths is None:
        col_widths = [1.8*inch, 0.7*inch, 4.0*inch]

    t = Table(table_data, colWidths=col_widths)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (2, 1), (2, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(C.BORDER_VERY_LIGHT)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]

    for i, (_, _, _, color) in enumerate(items, start=1):
        style_cmds.append(("TEXTCOLOR", (2, i), (2, i), colors.HexColor(color)))

    t.setStyle(TableStyle(style_cmds))
    return t


def score_card(items, col_widths=None):
    """
    Build a score card table with colored pass/warn/fail indicators.

    items: list of (check_name, result, status)
    status: "pass", "warn", "fail"
    """
    status_symbols = {"pass": "[OK]", "warn": "[!!]", "fail": "[XX]"}
    status_colors = {"pass": C.GREEN, "warn": C.YELLOW, "fail": C.RED}

    table_data = [[Paragraph("Check", _cell_hdr), Paragraph("Result", _cell_hdr), Paragraph("Status", _cell_hdr)]]
    for name, result, status in items:
        table_data.append([
            Paragraph(name, _cell_bold),
            Paragraph(result, _cell),
            status_symbols.get(status, "[--]"),
        ])

    if col_widths is None:
        col_widths = [2.5*inch, 3.5*inch, 0.8*inch]

    t = Table(table_data, colWidths=col_widths)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C.GRAY_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (2, 1), (2, -1), "Courier-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(C.BORDER_LIGHT)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(C.BG_ROW_ALT)]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]

    for i, (_, _, status) in enumerate(items, start=1):
        color = status_colors.get(status, C.GRAY)
        style_cmds.append(("TEXTCOLOR", (2, i), (2, i), colors.HexColor(color)))

    t.setStyle(TableStyle(style_cmds))
    return t
