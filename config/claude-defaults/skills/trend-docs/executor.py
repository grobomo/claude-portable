#!/usr/bin/env python3
"""
Trend Docs Executor - Playwright extractor for docs.trendmicro.com (JS SPA).
WebFetch returns empty shells on these sites. Playwright is the ONLY way to read them.
Usage: python executor.py --urls "URL1,URL2" or python executor.py "slug-name"
Workflow: WebSearch finds URLs -> this script extracts them -> Claude summarizes.
~25s/page (5s browser launch + 20s SPA hydration). Parallel tabs for multi-page.

PDF support: Detects .pdf URLs, downloads via Playwright (handles Akamai cookie
redirects that break curl with exit code 47), saves to ~/Downloads, extracts text
with PyPDF2.

Lessons learned:
- "networkidle" adds 10-15s for trackers; use "domcontentloaded" + selector wait
- Blind sleep loops (2s+3s+5s) waste 10s/page; wait for .main-content instead
- OLH uses .main-content, KB uses main.article-page - different extractors
- Pipe chars in table cells replaced with / to avoid breaking markdown tables
- One 2s retry if content <100 chars catches slow hydration edge cases
- docs.trendmicro.com PDFs use Akamai CDN that sets ew-request cookie + redirect
  loop; curl fails with exit 47 (max redirects). Playwright handles cookies natively.
- ohc.blob.core.windows.net PDFs work with curl (direct Azure blob, no Akamai)
"""

import sys
import os
import re
import argparse
import logging
import io
import time
import hashlib
import json
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def ensure_playwright():
    """Auto-install playwright + chromium if missing."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        import subprocess
        print("[trend-docs] Installing playwright...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        print("[trend-docs] Installing chromium browser...")
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        from playwright.sync_api import sync_playwright
        return sync_playwright

sync_playwright = ensure_playwright()

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("trend-docs")

# ============ Constants ============

OLH_BASE = "https://docs.trendmicro.com/en-us/documentation/article/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BROWSER_ARGS = [
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--no-first-run",
    "--disable-sync",
]


# ============ Cache ============

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_MAX_AGE = 2592000  # 30 days (docs rarely change)
SLUG_INDEX_PATH = Path(__file__).parent / "doc-slugs.yaml"


def url_to_cache_key(url):
    """Convert URL to cache filename. Uses slug for OLH, hash for others."""
    if "docs.trendmicro.com" in url and "/article/" in url:
        slug = url.rstrip("/").split("/")[-1].split("#")[0].split("?")[0]
        return slug + ".md"
    return hashlib.md5(url.encode()).hexdigest()[:16] + ".md"


def cache_get(url):
    """Return cached content if fresh, else None."""
    key = url_to_cache_key(url)
    path = CACHE_DIR / key
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < CACHE_MAX_AGE:
            content = path.read_text(encoding="utf-8")
            log.info(f"  [cache HIT] {key} ({age:.0f}s old)")
            return content
        else:
            log.info(f"  [cache STALE] {key} ({age:.0f}s old, max {CACHE_MAX_AGE}s)")
    return None


def cache_put(url, content):
    """Write content to cache, with content hash sidecar for freshness checks."""
    key = url_to_cache_key(url)
    path = CACHE_DIR / key
    path.write_text(content, encoding="utf-8")
    h = hashlib.md5(content.encode("utf-8")).hexdigest()
    (CACHE_DIR / (key + ".hash")).write_text(h, encoding="utf-8")
    log.info(f"  [cache WRITE] {key} ({len(content)} chars, hash={h[:8]})")


def check_cache_freshness(topics=None, refresh=False):
    """Check cached pages for content changes. Launches one Playwright session,
    navigates to each cached URL, hashes the rendered innerText, compares to stored hash.
    If refresh=True, re-extracts pages that changed."""
    from playwright.sync_api import sync_playwright

    # Collect cached pages to check
    cache_files = sorted(CACHE_DIR.glob("*.md"))
    if not cache_files:
        print("No cached pages found.")
        return

    # If topics specified, filter to those topic bundles
    if topics:
        index = load_slug_index()
        target_keys = set()
        for t in topics:
            urls = resolve_topic(t)
            if urls:
                for u in urls:
                    target_keys.add(url_to_cache_key(u))
        cache_files = [f for f in cache_files if f.name in target_keys]

    if not cache_files:
        print("No cached pages match the specified topics.")
        return

    # Build URL list from cache files (extract Source: URL from each .md)
    # Uses .ihash (innerText hash) sidecar -- separate from .hash (markdown hash)
    pages_to_check = []
    for cf in cache_files:
        ihash_path = CACHE_DIR / (cf.name + ".ihash")
        stored_ihash = ihash_path.read_text(encoding="utf-8").strip() if ihash_path.exists() else None
        # Extract source URL from cached markdown (line 2: "Source: https://...")
        source_url = None
        for line in cf.read_text(encoding="utf-8").splitlines()[:5]:
            if line.startswith("Source: http"):
                source_url = line[8:].strip()
                break
        if source_url and is_olh(source_url):
            pages_to_check.append((cf.name, source_url, stored_ihash))

    if not pages_to_check:
        print("No OLH pages with source URLs found in cache.")
        return

    print(f"Checking {len(pages_to_check)} cached page(s) for changes...")

    # Hash scope: main content + related-pages sidebar + page title/meta.
    # Excludes nav chrome, footer, user menu (session-specific = false positives).
    HASH_JS = """() => {
        let parts = [];
        // Page title (catches renames)
        parts.push(document.title || "");
        // Meta description (catches summary edits)
        const meta = document.querySelector('meta[name="description"]');
        if (meta) parts.push(meta.getAttribute("content") || "");
        // Main content body (the article text)
        const main = document.querySelector(".main-content");
        if (main) parts.push(main.innerText.trim());
        // Related pages sidebar (catches new/removed child/sibling pages)
        const menu = document.querySelector(".article-menu");
        if (menu) parts.push(menu.innerText.trim());
        return parts.join("\\n---\\n");
    }"""

    changed = []
    unchanged = []
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(user_agent=UA, java_script_enabled=True)

        for name, url, stored_ihash in pages_to_check:
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    page.wait_for_selector(".main-content", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(500)

                text = page.evaluate(HASH_JS)
                page.close()

                if not text or len(text) < 50:
                    errors.append((name, "empty content"))
                    continue

                live_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
                ihash_path = CACHE_DIR / (name + ".ihash")

                if stored_ihash and live_hash == stored_ihash:
                    unchanged.append(name)
                    log.info(f"  [OK] {name} unchanged")
                elif stored_ihash:
                    changed.append((name, url))
                    log.info(f"  [CHANGED] {name} (stored={stored_ihash[:8]} live={live_hash[:8]})")
                    # Update ihash to current live content
                    ihash_path.write_text(live_hash, encoding="utf-8")
                else:
                    # First check -- seed the ihash from live content
                    ihash_path.write_text(live_hash, encoding="utf-8")
                    unchanged.append(name)
                    log.info(f"  [SEEDED] {name} (first check, hash={live_hash[:8]})")
            except Exception as e:
                errors.append((name, str(e)))
                log.info(f"  [ERROR] {name}: {e}")

        # Refresh changed pages if requested
        if refresh and changed:
            print(f"\nRefreshing {len(changed)} changed page(s)...")
            for name, url in changed:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                result = wait_and_extract(page, url)
                page.close()
                if result["content"] and len(result["content"]) > 100:
                    section = "# " + result["title"] + "\nSource: " + url + "\n\n" + result["content"]
                    cache_put(url, section)
                    print(f"  [REFRESHED] {name}")

        browser.close()

    # Summary
    print(f"\n{'='*50}")
    print(f"Cache check: {len(pages_to_check)} pages")
    print(f"  Unchanged: {len(unchanged)}")
    print(f"  Changed:   {len(changed)}")
    print(f"  Errors:    {len(errors)}")
    if changed and not refresh:
        print(f"\nStale pages (re-run with --refresh to update):")
        for name, url in changed:
            print(f"  {name}")
    if errors:
        print(f"\nErrors:")
        for name, err in errors:
            print(f"  {name}: {err}")


def load_slug_index():
    """Load doc-slugs.yaml topic->slug mapping. Returns dict or empty."""
    if not SLUG_INDEX_PATH.exists():
        return {}
    try:
        import yaml
        with open(SLUG_INDEX_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return data
    except ImportError:
        # Fallback: simple key: value parsing
        index = {}
        for line in SLUG_INDEX_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                k, v = line.split(":", 1)
                index[k.strip()] = v.strip().strip('"').strip("'")
        return index
    except Exception:
        return {}


def resolve_topic(topic):
    """Look up a topic keyword in the slug index. Returns list of URLs or None.
    Supports both single slugs (string) and bundles (list of slugs)."""
    index = load_slug_index()
    topic_lower = topic.lower().strip()

    def slugs_to_urls(val):
        """Convert a slug string or list of slugs to list of URLs."""
        if isinstance(val, list):
            return [OLH_BASE + s if not s.startswith("http") else s for s in val]
        return [OLH_BASE + val if not val.startswith("http") else val]

    # Exact match
    if topic_lower in index:
        return slugs_to_urls(index[topic_lower])
    # Partial match
    for key, val in index.items():
        if topic_lower in key or key in topic_lower:
            log.info(f"  [slug-index] '{topic}' matched '{key}'")
            return slugs_to_urls(val)
    return None


# ============ Helpers ============

def is_url(text):
    return text.startswith("http://") or text.startswith("https://")


def is_slug(text):
    return re.match(r"^[a-z0-9-]+$", text) and len(text) > 10


def is_olh(url):
    return "docs.trendmicro.com" in url


def is_pdf(url):
    return url.lower().rstrip("/").endswith(".pdf")


def get_downloads_dir():
    """Get ~/Downloads, create if missing."""
    dl = Path.home() / "Downloads"
    dl.mkdir(exist_ok=True)
    return dl


def ensure_pypdf2():
    """Auto-install PyPDF2 if missing."""
    try:
        import PyPDF2
        return PyPDF2
    except ImportError:
        import subprocess
        log.info("[trend-docs] Installing PyPDF2...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2", "-q"])
        import PyPDF2
        return PyPDF2


# ============ Content Extraction JS ============

OLH_EXTRACT_JS = """() => {
    const res = {content: "", title: document.title, related: []};
    const main = document.querySelector(".main-content");
    if (!main) { res.content = document.body.textContent.trim().substring(0, 5000); return res; }
    const clone = main.cloneNode(true);
    const menu = clone.querySelector(".article-menu");
    if (menu) menu.remove();

    function toMd(node) {
        if (!node) return "";
        if (node.nodeType === 3) return node.textContent;
        if (node.nodeType !== 1) return "";
        const tag = node.tagName;
        const kids = Array.from(node.childNodes).map(c => toMd(c)).join("");
        if (/^H[1-6]$/.test(tag)) return "\\n" + "#".repeat(parseInt(tag[1])) + " " + kids.trim() + "\\n\\n";
        if (tag === "P") return kids.trim() + "\\n\\n";
        if (tag === "LI") return "- " + kids.trim() + "\\n";
        if (tag === "UL" || tag === "OL") return "\\n" + kids + "\\n";
        if (tag === "PRE" || tag === "CODE") return "```\\n" + node.textContent.trim() + "\\n```\\n\\n";
        if (tag === "BR") return "\\n";
        if (tag === "A" && node.href) return "[" + kids.trim() + "](" + node.href + ")";
        if (tag === "STRONG" || tag === "B") return "**" + kids.trim() + "**";
        if (tag === "EM" || tag === "I") return "*" + kids.trim() + "*";
        if (tag === "TABLE") {
            const rows = node.querySelectorAll("tr");
            if (rows.length === 0) return kids;
            let md = "\\n";
            rows.forEach((row, i) => {
                const cells = Array.from(row.querySelectorAll("th, td"));
                md += "| " + cells.map(c => c.textContent.trim().replace(/\\|/g, "/")).join(" | ") + " |\\n";
                if (i === 0) md += "| " + cells.map(() => "---").join(" | ") + " |\\n";
            });
            return md + "\\n";
        }
        if (["THEAD","TBODY","TFOOT","TR","TH","TD"].includes(tag)) return "";
        return kids;
    }

    res.content = toMd(clone).replace(/\\n{3,}/g, "\\n\\n").trim();

    // Related pages from sidebar menu
    const menuEl = document.querySelector(".article-menu");
    if (menuEl) {
        const currentSlug = window.location.pathname.split("/").pop();
        const allLinks = menuEl.querySelectorAll("a.item-link");
        let currentLi = null;
        for (const link of allLinks) {
            const href = link.getAttribute("href") || "";
            if (href === currentSlug || href.endsWith("/" + currentSlug)) { currentLi = link.closest("li"); break; }
        }
        if (currentLi) {
            const childGroup = currentLi.querySelector(":scope > .menu-group > ul");
            if (childGroup) {
                childGroup.querySelectorAll(":scope > li > .menu-item > a.item-link").forEach(a => {
                    res.related.push({title: a.textContent.trim(), slug: a.getAttribute("href"), type: "child"});
                });
            }
            const parentUl = currentLi.parentElement;
            if (parentUl) {
                parentUl.querySelectorAll(":scope > li > .menu-item > a.item-link").forEach(a => {
                    const slug = a.getAttribute("href");
                    if (slug !== currentSlug) res.related.push({title: a.textContent.trim(), slug: slug, type: "sibling"});
                });
            }
            const parentLi = currentLi.parentElement ? currentLi.parentElement.closest("li") : null;
            if (parentLi) {
                const pl = parentLi.querySelector(":scope > .menu-item > a.item-link");
                if (pl) res.related.push({title: pl.textContent.trim(), slug: pl.getAttribute("href"), type: "parent"});
            }
        }
    }
    return res;
}"""


KB_EXTRACT_JS = """() => {
    const res = {content: "", title: document.title, related: []};
    const main = document.querySelector("main.article-page, main");
    if (!main) { res.content = document.body.textContent.trim().substring(0, 5000); return res; }
    function toMd(node) {
        if (!node) return "";
        if (node.nodeType === 3) return node.textContent;
        if (node.nodeType !== 1) return "";
        const tag = node.tagName;
        if (["NAV","HEADER","FOOTER","SCRIPT","STYLE","NOSCRIPT"].includes(tag)) return "";
        const kids = Array.from(node.childNodes).map(c => toMd(c)).join("");
        if (/^H[1-6]$/.test(tag)) return "\\n" + "#".repeat(parseInt(tag[1])) + " " + kids.trim() + "\\n\\n";
        if (tag === "P") return kids.trim() + "\\n\\n";
        if (tag === "LI") return "- " + kids.trim() + "\\n";
        if (tag === "UL" || tag === "OL") return "\\n" + kids + "\\n";
        if (tag === "PRE" || tag === "CODE") return "```\\n" + node.textContent.trim() + "\\n```\\n\\n";
        if (tag === "BR") return "\\n";
        if (tag === "A" && node.href) return "[" + kids.trim() + "](" + node.href + ")";
        if (tag === "STRONG" || tag === "B") return "**" + kids.trim() + "**";
        if (tag === "TABLE") {
            const rows = node.querySelectorAll("tr");
            let md = "\\n";
            rows.forEach((row, i) => {
                const cells = Array.from(row.querySelectorAll("th, td"));
                md += "| " + cells.map(c => c.textContent.trim().replace(/\\|/g, "/")).join(" | ") + " |\\n";
                if (i === 0) md += "| " + cells.map(() => "---").join(" | ") + " |\\n";
            });
            return md + "\\n";
        }
        if (["THEAD","TBODY","TFOOT","TR","TH","TD"].includes(tag)) return "";
        return kids;
    }
    res.content = toMd(main).replace(/\\n{3,}/g, "\\n\\n").trim();
    return res;
}"""


# ============ Extraction ============

def extract_page(page_obj, url):
    """Extract content from a loaded Playwright page."""
    js = OLH_EXTRACT_JS if is_olh(url) else KB_EXTRACT_JS
    try:
        result = page_obj.evaluate(js)
        result["url"] = url
        return result
    except Exception as e:
        return {"content": f"Error extracting: {e}", "title": url, "url": url, "related": []}


def wait_and_extract(page_obj, url):
    """Wait for content to render on an already-navigating page, then extract."""
    content_sel = ".main-content" if is_olh(url) else "main.article-page, main"
    try:
        page_obj.wait_for_selector(content_sel, timeout=10000)
    except Exception:
        pass
    page_obj.wait_for_timeout(500)
    result = extract_page(page_obj, url)
    # Retry once if SPA shell not rendered
    if not result["content"] or len(result["content"]) < 100 or "window[" in result["content"][:200]:
        page_obj.wait_for_timeout(2000)
        result = extract_page(page_obj, url)
    return result


# ============ PDF Download + Extract ============

def download_pdf_playwright(url, context):
    """Download PDF via Playwright (handles Akamai cookie redirects that break curl).
    Saves to ~/Downloads, returns (local_path, filename) or (None, error_msg)."""
    downloads_dir = get_downloads_dir()
    filename = url.split("/")[-1].split("?")[0]
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    save_path = downloads_dir / filename

    try:
        page = context.new_page()
        # Intercept the download triggered by navigating to a PDF URL
        with page.expect_download(timeout=30000) as dl_info:
            page.goto(url, timeout=30000)
        download = dl_info.value
        download.save_as(str(save_path))
        page.close()
        return str(save_path), filename
    except Exception:
        # Fallback: some PDFs render in-browser instead of downloading.
        # Try a direct request via Playwright's API context.
        try:
            page.close()
        except Exception:
            pass
        try:
            api_ctx = context.request
            resp = api_ctx.get(url)
            if resp.status == 200 and len(resp.body()) > 1000:
                save_path.write_bytes(resp.body())
                return str(save_path), filename
        except Exception as e2:
            return None, f"Download failed: {e2}"
    return None, "Download failed: unknown error"


def extract_pdf_text(pdf_path, pages=None):
    """Extract text from PDF using PyPDF2. Returns markdown string."""
    PyPDF2 = ensure_pypdf2()
    try:
        reader = PyPDF2.PdfReader(pdf_path)
        total = len(reader.pages)
        # Parse page range like "1-5" or "3" or None (all)
        if pages:
            parts = pages.split("-")
            start = int(parts[0]) - 1
            end = int(parts[1]) if len(parts) > 1 else start + 1
        else:
            start, end = 0, min(total, 20)  # Cap at 20 pages by default

        texts = []
        for i in range(start, min(end, total)):
            text = reader.pages[i].extract_text()
            if text and text.strip():
                texts.append(f"--- Page {i+1} ---\n{text.strip()}")

        filename = Path(pdf_path).name
        header = f"# {filename}\nSource: {pdf_path}\nPages: {start+1}-{min(end, total)} of {total}\n\n"
        return header + "\n\n".join(texts) if texts else header + "(No extractable text)"
    except Exception as e:
        return f"# PDF Extract Error\n{e}"


# ============ Main ============

def run_batch(urls, max_pages=10, use_cache=True):
    """Extract multiple URLs in parallel tabs within a single browser."""
    urls = [u.strip() for u in urls if u.strip()][:max_pages]
    if not urls:
        print("No URLs provided.")
        return

    # Separate PDF URLs from HTML URLs
    pdf_urls = [u for u in urls if is_pdf(u)]
    html_urls = [u for u in urls if not is_pdf(u)]

    output_sections = []
    t0 = time.time()
    cache_hits = 0

    # Check cache for HTML URLs first
    uncached_html = []
    if use_cache:
        for url in html_urls:
            cached = cache_get(url)
            if cached:
                output_sections.append(cached)
                cache_hits += 1
            else:
                uncached_html.append(url)
    else:
        uncached_html = html_urls

    # Only launch browser if we have uncached HTML or PDF URLs
    if uncached_html or pdf_urls:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = browser.new_context(user_agent=UA, java_script_enabled=True,
                                           accept_downloads=True)

            # Handle PDF downloads first
            for i, url in enumerate(pdf_urls):
                log.info(f"[pdf {i+1}] downloading {url}")
                path, info = download_pdf_playwright(url, context)
                if path:
                    log.info(f"  [pdf {i+1}] saved: {path}")
                    text = extract_pdf_text(path)
                    if text:
                        output_sections.append(text)
                    print(f"[SAVED] {info} -> {path}")
                else:
                    log.info(f"  [pdf {i+1}] FAILED: {info}")

            # Open uncached HTML pages in parallel tabs
            tabs = []
            for i, url in enumerate(uncached_html):
                log.info(f"[tab {i+1}] loading {url}")
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                tabs.append((page, url))

            # Extract from each tab
            for i, (page, url) in enumerate(tabs):
                try:
                    result = wait_and_extract(page, url)
                    title = result.get("title", url)
                    body = result.get("content", "")
                    if "Article unavailable" in title or "window[" in body[:200]:
                        log.info(f"  [{i+1}] SKIP: dead/broken ({title[:40]})")
                    elif body and len(body) > 50:
                        section = "# " + title + "\nSource: " + url + "\n\n" + body
                        output_sections.append(section)
                        if use_cache:
                            cache_put(url, section)
                    else:
                        log.info(f"  [{i+1}] SKIP: too little content")
                except Exception as e:
                    log.info(f"  [{i+1}] ERROR: {e}")

            context.close()
            browser.close()
    elif cache_hits:
        log.info(f"[cache] All {cache_hits} pages served from cache, no browser needed")

    elapsed = time.time() - t0

    if not output_sections:
        print("No relevant content found.")
    else:
        print("\n\n---\n\n".join(output_sections))

    log.info(f"\n[done] {len(urls)} pages ({len(pdf_urls)} PDF, {len(html_urls)} HTML, {cache_hits} cached), {len(output_sections)} returned, {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Extract Trend Micro documentation pages")
    parser.add_argument("query", nargs="?", default=None, help="Direct URL or article slug")
    parser.add_argument("--urls", "-u", default=None, help="Comma-separated URLs (batch mode)")
    parser.add_argument("--max-pages", "-m", type=int, default=10, help="Max pages to fetch (default 10)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress messages")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache, force fresh fetch")
    parser.add_argument("--topic", "-t", default=None, help="Topic keyword to look up in slug index")
    parser.add_argument("--check-cache", action="store_true", help="Check cached pages for content changes (launches browser)")
    parser.add_argument("--refresh", action="store_true", help="With --check-cache: auto-refresh stale pages")
    args = parser.parse_args()
    if args.quiet:
        log.setLevel(logging.WARNING)

    use_cache = not args.no_cache

    # --check-cache mode: verify cached pages are still current
    if args.check_cache:
        topics = [args.topic] if args.topic else None
        check_cache_freshness(topics=topics, refresh=args.refresh)
        return

    # --topic mode: resolve topic to URL(s) via slug index (supports bundles)
    if args.topic:
        urls = resolve_topic(args.topic)
        if urls:
            log.info(f"[topic] '{args.topic}' -> {len(urls)} page(s)")
            run_batch(urls, args.max_pages, use_cache=use_cache)
        else:
            print(f"Topic '{args.topic}' not found in slug index. Known topics:")
            index = load_slug_index()
            for key in sorted(index.keys()):
                print(f"  {key}: {index[key]}")
            sys.exit(1)
    elif args.urls:
        url_list = [u.strip() for u in args.urls.split(",") if u.strip()]
        run_batch(url_list, args.max_pages, use_cache=use_cache)
    elif args.query:
        if is_url(args.query):
            run_batch([args.query], args.max_pages, use_cache=use_cache)
        elif is_slug(args.query):
            run_batch([OLH_BASE + args.query], args.max_pages, use_cache=use_cache)
        else:
            parser.error("Query must be a URL or slug. Use WebSearch for discovery, then pass URLs here.")
    else:
        parser.error("Either a URL/slug, --urls, or --topic is required")


if __name__ == "__main__":
    main()
