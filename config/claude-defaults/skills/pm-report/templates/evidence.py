"""
Evidence block builders for PM reports.
Renders API results, screenshots, CLI output, metrics, and doc links.
"""

import os
from reportlab.platypus import Paragraph, Spacer, Image
from reportlab.lib.units import inch


def screenshot(story, styles, path, caption, width=6.5*inch):
    """Embed a screenshot with caption. Skips gracefully if file missing."""
    if path and os.path.exists(path):
        img = Image(path, width=width, height=width * 0.56)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Paragraph(f"<i>{caption}</i>", styles["Caption"]))
    else:
        story.append(Paragraph(f"[Screenshot not available: {path}]", styles["SmallGray"]))


def evidence_block(story, styles, title, endpoint, result, status="working"):
    """
    Render an API/CLI evidence block.
    status: "working" (green) or "gap" (red)
    """
    style_key = "ApiOk" if status == "working" else "ApiGap"
    tag = "[OK]" if status == "working" else "[GAP]"
    story.append(Paragraph(f"<b>{tag} {title}</b>", styles["Body"]))
    story.append(Paragraph(f"Endpoint: {endpoint}", styles[style_key]))
    story.append(Paragraph(f"Result: {result}", styles["Body"]))


def doc_link(story, styles, label, url):
    """Render a source documentation link."""
    if url:
        story.append(Paragraph(
            f'<b>Source:</b> <a href="{url}" color="#1565c0">{label}</a>  --  {url}',
            styles["DocLink"]
        ))


def metric_block(story, styles, name, value, target, status="ok"):
    """
    Render a metric/benchmark result.
    status: "ok" (meeting target), "warn" (approaching), "fail" (below target)
    """
    style_key = {
        "ok": "ApiOk",
        "warn": "Body",
        "fail": "ApiGap",
    }.get(status, "Body")

    tag_map = {"ok": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]"}
    tag = tag_map.get(status, "[--]")

    story.append(Paragraph(f"<b>{tag} {name}</b>", styles["Body"]))
    story.append(Paragraph(f"Value: {value}  |  Target: {target}", styles[style_key]))


def missing_list(story, styles, items):
    """Render a list of missing features/APIs in red blocks."""
    for item in items:
        story.append(Paragraph(f"  X  {item}", styles["ApiGap"]))


def working_list(story, styles, items):
    """Render a list of working features/APIs in green blocks."""
    for item in items:
        story.append(Paragraph(f"  +  {item}", styles["ApiOk"]))


def bullet_list(story, styles, items):
    """Render a simple bullet list."""
    for item in items:
        story.append(Paragraph(f"  *  {item}", styles["Body"]))


def impact_statement(story, styles, text):
    """Render a bold impact statement."""
    story.append(Paragraph(f"<b>Impact:</b> {text}", styles["Body"]))
