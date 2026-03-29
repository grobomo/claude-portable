"""
Recommendation section builders for PM reports.
Tiered action items in PM-friendly format.
"""

from reportlab.platypus import Paragraph, Spacer


def tiered_recommendations(story, styles, tiers):
    """
    Build tiered recommendation sections.

    tiers: list of (tier_title, tier_description, items)
    where items = list of (title, rationale)

    Example:
    [
        ("Tier 1: Ship First", "Blocks automation for most customers", [
            ("ZTSA Policy CRUD", "Every ZTSA customer does policy work daily"),
            ("Endpoint Policy CRUD", "Table stakes for enterprise security"),
        ]),
        ("Tier 2: High Demand", "Blocks specific workflows", [...]),
        ("Tier 3: Growing Need", "Future-facing", [...]),
    ]
    """
    counter = 1
    for tier_title, tier_desc, items in tiers:
        story.append(Paragraph(
            f"<b>{tier_title}</b> ({tier_desc})",
            styles["SubHeader"]
        ))
        for title, rationale in items:
            story.append(Paragraph(
                f"  {counter}. <b>{title}</b> -- {rationale}",
                styles["Body"]
            ))
            counter += 1
        story.append(Spacer(1, 6))


def action_items(story, styles, items):
    """
    Simple numbered action item list.

    items: list of (action_title, description)
    """
    for i, (title, desc) in enumerate(items, 1):
        story.append(Paragraph(f"  {i}. <b>{title}</b> -- {desc}", styles["Body"]))


def next_steps(story, styles, steps):
    """
    "What happens next" section with timeline hints.

    steps: list of (timeframe, action)
    Example: [("This week", "Share report with PM team"), ("Next sprint", "Prioritize Tier 1 gaps")]
    """
    story.append(Paragraph("<b>Next Steps:</b>", styles["SubHeader"]))
    for timeframe, action in steps:
        story.append(Paragraph(f"  *  <b>{timeframe}:</b> {action}", styles["Body"]))
