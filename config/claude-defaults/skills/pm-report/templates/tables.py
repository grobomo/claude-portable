"""
Table builders for PM reports.
Coverage tables, comparison tables, source reference tables.
"""

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Table, TableStyle, Paragraph
from .styles import C


# Reusable cell styles for word-wrapping inside table cells
_cell_style = ParagraphStyle("_cell", fontSize=8, leading=10, spaceAfter=0)
_cell_bold = ParagraphStyle("_cellBold", parent=_cell_style, fontName="Helvetica-Bold")
_cell_header = ParagraphStyle("_cellHdr", parent=_cell_bold, textColor=colors.white)


def _wrap_row(row, bold_first=False):
    """Wrap plain strings in Paragraph objects so text wraps inside cells."""
    out = []
    for i, cell in enumerate(row):
        if isinstance(cell, str):
            style = _cell_bold if (i == 0 and bold_first) else _cell_style
            out.append(Paragraph(cell, style))
        else:
            out.append(cell)
    return out


def _wrap_header(row):
    """Wrap header strings in white-bold Paragraphs."""
    return [Paragraph(str(c), _cell_header) if isinstance(c, str) else c for c in row]


def coverage_table(data, col_widths=None):
    """
    Build a colored coverage table.

    data: list of rows, each row = [section_name, ops_count, coverage_level, notes]
    coverage_level should be one of: FULL, HIGH, MEDIUM, LOW, NONE

    Returns a Table flowable.
    """
    header = ["Section", "Operations", "Coverage", "Notes"]
    table_data = [_wrap_header(header)] + [_wrap_row(r, bold_first=True) for r in data]

    if col_widths is None:
        col_widths = [2.2*inch, 0.8*inch, 1.0*inch, 3.0*inch]

    t = Table(table_data, colWidths=col_widths)

    base_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C.BLUE_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(C.BORDER_LIGHT)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(C.BG_ROW_ALT)]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]

    # Color the coverage column by level
    coverage_colors = {
        "FULL": C.GREEN,
        "HIGH": C.GREEN,
        "MEDIUM": C.YELLOW,
        "LOW": C.RED,
        "NONE": C.RED,
    }
    for i, row in enumerate(data, start=1):
        level = row[2].upper() if len(row) > 2 else ""
        color = coverage_colors.get(level)
        if color:
            base_style.append(("TEXTCOLOR", (2, i), (2, i), colors.HexColor(color)))
        if level in ("LOW", "NONE"):
            base_style.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))

    t.setStyle(TableStyle(base_style))
    return t


def comparison_table(headers, data, col_widths=None):
    """
    Build a side-by-side comparison table.

    headers: list of column headers
    data: list of rows
    """
    table_data = [_wrap_header(headers)] + [_wrap_row(r) for r in data]

    if col_widths is None:
        total = 7.0 * inch
        col_widths = [total / len(headers)] * len(headers)

    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C.GRAY_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(C.BORDER_LIGHT)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(C.BG_ROW_ALT)]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def bridge_table(data, col_widths=None):
    """
    Build a "how we bridge the gap" table.

    data: list of rows = [gap_area, module, api_used, browser_fills]
    """
    header = ["Gap Area", "Module", "API Used", "Browser Fills"]
    table_data = [header] + data

    if col_widths is None:
        col_widths = [1.2*inch, 1.3*inch, 1.6*inch, 2.4*inch]

    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C.BLUE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(C.BORDER_LIGHT)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(C.BG_BLUE)]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def source_table(doc_refs):
    """
    Build a source documentation reference table.

    doc_refs: list of (label, url, scope_description)
    """
    table_data = [_wrap_header(["Source", "URL", "Scope"])]
    _url_style = ParagraphStyle("_url", fontSize=7, leading=9, textColor=colors.HexColor(C.BLUE))
    _src_style = ParagraphStyle("_src", fontSize=7, leading=9)
    for label, url, scope in doc_refs:
        table_data.append([
            Paragraph(label, _src_style),
            Paragraph(url, _url_style),
            Paragraph(scope, _src_style),
        ])

    t = Table(table_data, colWidths=[1.5*inch, 3.2*inch, 2.0*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(C.GRAY_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(C.BORDER_LIGHT)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(C.BG_ROW_ALT)]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t
