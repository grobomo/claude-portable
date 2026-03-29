#!/usr/bin/env python3
"""
PM Report Generator -- builds evidence-based PDF reports for PM audiences.

This is the engine. Claude assembles reports by calling these building blocks.
Each report is a script that imports from templates/ and calls generator.build().

Usage:
    # Direct (for testing the engine itself)
    python generator.py --demo

    # From Claude (typical usage)
    Claude writes a report-specific script that imports these modules and builds a PDF.
"""

import os
import sys
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Spacer

# Add templates to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from templates.styles import build_styles
from templates.cover import (
    cover_page, table_of_contents, section_header, sub_header,
    priority_header, body_text, page_break, spacer, horizontal_rule, footer_text
)
from templates.evidence import (
    screenshot, evidence_block, doc_link, metric_block,
    missing_list, working_list, bullet_list, impact_statement
)
from templates.tables import (
    coverage_table, comparison_table, bridge_table, source_table
)
from templates.charts import bar_chart, score_card
from templates.recommendations import (
    tiered_recommendations, action_items, next_steps
)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------
class PMReport:
    """
    PM Report builder. Provides all building blocks as methods.

    Usage:
        report = PMReport("My Analysis", "Subtitle here")
        report.add_cover(details=["detail 1", "detail 2"])
        report.add_toc(["1. Section One", "2. Section Two"])
        report.section("1. Section One")
        report.text("Here is the analysis...")
        report.add_evidence("test endpoint", "GET /api/test", "200 OK", "working")
        report.build()  # returns path to PDF
    """

    def __init__(self, title, subtitle, output_dir=None, filename_prefix=None):
        self.title = title
        self.subtitle = subtitle
        self.styles = build_styles()
        self.story = []

        if output_dir is None:
            # Default to project reports/ directory
            # Skill lives at .claude/skills/pm-report/ -- go up 3 levels to project root
            skill_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(skill_dir)))
            output_dir = os.path.join(project_root, "reports")
        os.makedirs(output_dir, exist_ok=True)

        if filename_prefix is None:
            # Sanitize title into filename
            filename_prefix = title.lower().replace(" ", "_")[:40]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = os.path.join(output_dir, f"{filename_prefix}_{timestamp}.pdf")

    # -- Structural --

    def add_cover(self, details=None, footer_lines=None):
        cover_page(self.story, self.styles, self.title, self.subtitle, details, footer_lines)

    def add_toc(self, items):
        table_of_contents(self.story, self.styles, items)

    def section(self, title):
        section_header(self.story, self.styles, title)

    def subsection(self, title):
        sub_header(self.story, self.styles, title)

    def priority(self, title):
        priority_header(self.story, self.styles, title)

    def text(self, content):
        body_text(self.story, self.styles, content)

    def break_page(self):
        page_break(self.story)

    def space(self, height=8):
        spacer(self.story, height)

    def rule(self):
        horizontal_rule(self.story)

    def footer(self, text):
        footer_text(self.story, self.styles, text)

    # -- Evidence --

    def add_screenshot(self, path, caption, width=6.5*inch):
        screenshot(self.story, self.styles, path, caption, width)

    def add_evidence(self, title, endpoint, result, status="working"):
        evidence_block(self.story, self.styles, title, endpoint, result, status)

    def add_doc_link(self, label, url):
        doc_link(self.story, self.styles, label, url)

    def add_metric(self, name, value, target, status="ok"):
        metric_block(self.story, self.styles, name, value, target, status)

    def add_missing(self, items):
        missing_list(self.story, self.styles, items)

    def add_working(self, items):
        working_list(self.story, self.styles, items)

    def add_bullets(self, items):
        bullet_list(self.story, self.styles, items)

    def add_impact(self, text):
        impact_statement(self.story, self.styles, text)

    # -- Tables --

    def add_coverage_table(self, data, col_widths=None):
        self.story.append(coverage_table(data, col_widths))

    def add_comparison_table(self, headers, data, col_widths=None):
        self.story.append(comparison_table(headers, data, col_widths))

    def add_bridge_table(self, data, col_widths=None):
        self.story.append(bridge_table(data, col_widths))

    def add_source_table(self, doc_refs):
        self.story.append(source_table(doc_refs))

    # -- Charts --

    def add_bar_chart(self, items, col_widths=None):
        self.story.append(bar_chart(items, col_widths))

    def add_score_card(self, items, col_widths=None):
        self.story.append(score_card(items, col_widths))

    # -- Recommendations --

    def add_recommendations(self, tiers):
        tiered_recommendations(self.story, self.styles, tiers)

    def add_action_items(self, items):
        action_items(self.story, self.styles, items)

    def add_next_steps(self, steps):
        next_steps(self.story, self.styles, steps)

    # -- Build --

    def build(self, review=True):
        """Build the PDF, optionally run QA review, and return the output path."""
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=letter,
            topMargin=0.6*inch,
            bottomMargin=0.6*inch,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch,
        )
        doc.build(self.story)
        print(f"PDF generated: {self.output_path}")

        if review:
            self._review_report()

        return self.output_path

    def _review_report(self):
        """Run claude -p to QA the generated PDF for accuracy, formatting, and data leaks."""
        import subprocess
        import shutil

        if not shutil.which("claude"):
            print("[REVIEW] claude CLI not found -- skipping QA review")
            return

        prompt = (
            "Review this PDF report for quality. Check ALL of the following and report "
            "PASS or FAIL for each:\n\n"
            "1. SENSITIVE DATA: Any customer names, real person names (other than the "
            "report author), internal hostnames, IP addresses, AWS account IDs, API keys, "
            "tokens, or credentials that should not be shared externally?\n"
            "2. ACCURACY: Are claims supported by evidence shown? Any contradictions "
            "between sections? Any obviously wrong data?\n"
            "3. FORMATTING: Are tables aligned? Screenshots captioned? Sections in logical "
            "order? TOC matches actual sections?\n"
            "4. AUDIENCE: Is this useful for the target audience? Does it lead with impact, "
            "not jargon? Are recommendations actionable?\n"
            "5. COMPLETENESS: Any sections that are empty, say 'TODO', or have placeholder "
            "text? Any promised evidence that's missing?\n\n"
            "Output format:\n"
            "SENSITIVE DATA: PASS/FAIL (details if FAIL)\n"
            "ACCURACY: PASS/FAIL (details if FAIL)\n"
            "FORMATTING: PASS/FAIL (details if FAIL)\n"
            "AUDIENCE: PASS/FAIL (details if FAIL)\n"
            "COMPLETENESS: PASS/FAIL (details if FAIL)\n"
            "OVERALL: PASS/FAIL\n"
            "ISSUES: (list any issues found, or 'None')"
        )

        print(f"[REVIEW] Running QA review on {os.path.basename(self.output_path)}...")
        try:
            env = os.environ.copy()
            env.pop("CLAUDECODE", None)
            env.pop("CLAUDE_CODE", None)
            result = subprocess.run(
                ["claude", "-p", prompt, self.output_path],
                capture_output=True, text=True, timeout=120, env=env
            )
            review_text = result.stdout.strip()
            if review_text:
                review_path = self.output_path.replace(".pdf", "_review.txt")
                with open(review_path, "w") as f:
                    f.write(review_text)
                print(f"[REVIEW] QA report saved: {review_path}")

                for line in review_text.split("\n"):
                    if any(k in line for k in ["OVERALL:", "ISSUES:", "SENSITIVE DATA:", "FAIL"]):
                        print(f"[REVIEW] {line.strip()}")

                if "OVERALL: FAIL" in review_text:
                    print("[REVIEW] ** REPORT FAILED QA -- review issues before sharing **")
            else:
                print("[REVIEW] No output from reviewer (stderr: " + result.stderr[:200] + ")")
        except subprocess.TimeoutExpired:
            print("[REVIEW] Review timed out after 120s -- skipping")
        except Exception as e:
            print(f"[REVIEW] Review error: {e}")


# ---------------------------------------------------------------------------
# Demo report (for testing)
# ---------------------------------------------------------------------------
def demo():
    """Generate a demo report to verify the engine works."""
    r = PMReport("Demo Product", "Technical Analysis Report", filename_prefix="pm_report_demo")

    r.add_cover(
        details=[
            "Sample analysis with all report components",
            "Generated by pm-report skill engine",
        ],
        footer_lines=[
            "This is a demo report to verify the PM report engine.",
            "All components are functional and rendering correctly.",
        ]
    )

    r.add_toc([
        "1. Executive Summary",
        "2. Coverage Overview",
        "3. Priority Findings",
        "4. Evidence",
        "5. Recommendations",
        "6. Sources",
    ])

    # Executive Summary
    r.section("1. Executive Summary")
    r.text(
        "This demo report shows all available PM report components. "
        "Each section demonstrates a building block that can be used in real reports."
    )
    r.add_bullets([
        "Coverage tables with colored status indicators",
        "ASCII bar charts for visual comparison",
        "Evidence blocks (working vs gap)",
        "Screenshot embedding with captions",
        "Tiered recommendations for PM audiences",
        "Source documentation reference tables",
    ])

    r.break_page()

    # Coverage
    r.section("2. Coverage Overview")
    r.add_coverage_table([
        ["Feature A", "10+", "HIGH", "Full CRUD available"],
        ["Feature B", "5", "MEDIUM", "Read-only, no write API"],
        ["Feature C", "1", "LOW", "Single endpoint, no config"],
        ["Feature D", "0", "NONE", "Zero API coverage"],
    ])

    r.space(16)
    r.subsection("Visual Coverage")
    r.add_bar_chart([
        ("Feature A", "90%", 18, "#2e7d32"),
        ("Feature B", "50%", 10, "#f9a825"),
        ("Feature C", "15%", 3, "#c62828"),
        ("Feature D", "0%", 0, "#880e4f"),
    ])

    r.space(16)
    r.subsection("Score Card")
    r.add_score_card([
        ("API Authentication", "Bearer token working", "pass"),
        ("Rate Limiting", "50 req/min (target: 100)", "warn"),
        ("Error Handling", "500 errors on bulk operations", "fail"),
        ("Pagination", "Cursor-based, auto-follow", "pass"),
    ])

    r.break_page()

    # Findings
    r.section("3. Priority Findings")
    r.priority("3.1  Feature D -- Zero API Coverage")
    r.text("<b>Console Path:</b> Settings > Feature D > Configuration")
    r.text("<b>Available APIs:</b> None (0 operations)")
    r.add_missing([
        "No create/read/update/delete for configurations",
        "No policy management endpoint",
        "No status query endpoint",
    ])
    r.space(6)
    r.add_impact(
        "Every customer using Feature D must configure it through the console manually. "
        "No programmatic access means no automation, no Infrastructure-as-Code, no multi-tenant management."
    )

    r.break_page()

    # Evidence
    r.section("4. Evidence")
    r.subsection("Working APIs")
    r.add_evidence(
        "list_items (working)",
        "GET /v3.0/items?top=10",
        "Returned 10 items with full metadata. Pagination working via nextLink.",
        "working"
    )
    r.add_doc_link("API Reference: Items", "https://docs.example.com/api/items")

    r.space(8)
    r.subsection("Gap APIs")
    r.add_evidence(
        "Feature D config (missing)",
        "NONE",
        "No API endpoint exists. All configuration requires manual console interaction.",
        "gap"
    )

    r.space(8)
    r.subsection("Metrics")
    r.add_metric("Response Time (P95)", "245ms", "<500ms", "ok")
    r.add_metric("Error Rate", "3.2%", "<1%", "fail")
    r.add_metric("Uptime", "99.8%", "99.9%", "warn")

    r.break_page()

    # Recommendations
    r.section("5. Recommendations")
    r.add_recommendations([
        ("Tier 1: Ship First", "Blocks most customers daily", [
            ("Feature D API", "Zero coverage affects every deployment"),
            ("Bulk Operations", "500 errors on batch requests"),
        ]),
        ("Tier 2: High Demand", "Blocks specific workflows", [
            ("Feature C Policy CRUD", "Single endpoint insufficient for policy management"),
        ]),
        ("Tier 3: Growing Need", "Future-facing improvements", [
            ("Feature B Write API", "Currently read-only, write needed for automation"),
        ]),
    ])

    r.space(12)
    r.add_next_steps([
        ("This week", "Share report with PM team for review"),
        ("Next sprint", "Prioritize Tier 1 gaps in backlog"),
        ("Q2 2026", "Ship Feature D API and bulk operation fixes"),
    ])

    r.break_page()

    # Sources
    r.section("6. Source Documentation")
    r.add_source_table([
        ("API Reference", "https://docs.example.com/api/v3", "Complete API documentation"),
        ("Product Docs", "https://docs.example.com/product", "Full product documentation"),
        ("Release Notes", "https://docs.example.com/releases", "Version history and changes"),
    ])

    r.space(20)
    r.rule()
    r.space(8)
    r.footer(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Demo Report")

    return r.build()


if __name__ == "__main__":
    if "--demo" in sys.argv:
        path = demo()
        print(f"Demo report: {path}")
    else:
        print("PM Report Engine")
        print("  --demo    Generate a demo report to test all components")
        print()
        print("For real reports, Claude writes a script that imports PMReport")
        print("and assembles the sections based on gathered evidence.")
