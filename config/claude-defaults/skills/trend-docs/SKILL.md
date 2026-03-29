---
name: trend-docs
description: >
  Read Trend Micro documentation. Searches, extracts, and returns clean content
  from docs.trendmicro.com and success.trendmicro.com KB articles.
  Products: Deep Discovery Analyzer (DDAN), Deep Discovery Inspector (DDI),
  Deep Discovery Director (DDD), Apex One, Apex Central, Vision One (V1),
  TippingPoint, InterScan Messaging Security (IMSVA), InterScan Web Security (IWSVA),
  OfficeScan, Worry-Free Business Security (WFBSS), Cloud One, Zero Trust Secure Access (ZTSA),
  Secure Access Module (SAM), Virtual Network Sensor (VNS), Cloud Email and Collaboration
  Protection (CECP), Trend Micro Control Manager (TMCM), Service Gateway, ServerProtect,
  Deep Security, Cloud App Security (CAS), Email Security, Network Defense.
keywords:
  - docs
  - documentation
  - trend
  - help
  - olh
  - knowledge
  - ddan
  - ddi
  - ddd
  - apex
  - xdr
  - ztsa
  - vns
  - sam
  - tippingpoint
  - imsva
  - iwsva
  - officescan
  - worryfreebiz
  - deepdiscovery
  - interscan
  - cloudone
  - port
  - firewall
  - gateway
  - cecp
  - tmcm
  - serverprotect
  - deepsecurity
  - cas
---

# Trend Docs Skill

Reads Trend Micro product documentation using Playwright to handle JS-rendered pages.

## CRITICAL: NEVER use WebFetch on docs.trendmicro.com

docs.trendmicro.com is a JavaScript SPA. WebFetch returns EMPTY SHELLS - no content.
ALWAYS use the Playwright executor below. There are NO exceptions to this rule.

## Source Trust Order

When multiple sources cover the same topic, trust them in this order:
1. **docs.trendmicro.com** (OLH - most up to date)
2. **success.trendmicro.com** (KBs - good for troubleshooting, workarounds)
3. **PDF guides** (admin guides, install guides, best practice guides - may be older)

## CRITICAL: Never Assume Product Equivalence

Trend Micro has dozens of distinct products. NEVER conflate them. When search results
return docs about Product A but the user asked about Product B, do NOT present Product A
info as if it answers the question. Instead:

1. Check: do the results actually match the product the user asked about?
2. If no match: re-search with different terms (product name, abbreviation, feature name)
3. If still no match: say "I couldn't find docs specifically for [product/feature]" and
   ask the user to clarify - do NOT fill in the gap with a guess

Example of what NOT to do: user asks about "Service Gateway pcap" -> results are all
about DDI packet capture -> do NOT say "Service Gateway hosts DDI" and present DDI docs.
Service Gateway and DDI are completely different products.

## Completeness Rule

When the user asks about a topic, get the COMPLETE answer. Do not stop at one page
and ask "want me to get more?". Follow references to related pages that complete the
picture. Examples:

- "what actions are available for Gmail?" -> get the actions-for-different-services page
  that covers ALL policy types (malware, spam, DLP, file blocking, web rep, virtual
  analyzer), not just the first page you find about spam
- "how does ZTSA work?" -> get the overview AND the setup pages
- "what are the API endpoints for X?" -> get the full API reference, not just the intro

Use multiple WebSearches if needed to find the right pages. The user expects a complete
answer, not a partial one with a follow-up question.

## CRITICAL: Save Files + Notify User

- **All downloaded docs and report files MUST be saved to `~/Downloads/`**
- **ALWAYS tell the user where files were saved** - include the full path in your response
- Never save to /tmp, $TEMP, or other temp directories
- The executor handles PDF saves automatically (prints `[SAVED] filename -> path`)

## Workflow

1. **WebSearch** to find relevant page URLs (search ALL of trendmicro.com, not just one subdomain):
   ```
   WebSearch: site:trendmicro.com "<query terms>"
   ```

2. **Extract content** - the executor handles BOTH HTML pages and PDFs:

   **For any trendmicro.com URL** (HTML or PDF - executor auto-detects):
   ```bash
   python ~/.claude/skills/trend-docs/executor.py --urls "URL1,URL2,URL3" --max-pages 5
   ```

   PDF URLs (.pdf) are automatically:
   - Downloaded via Playwright (handles Akamai cookie redirects that break curl)
   - Saved to ~/Downloads/
   - Text extracted with PyPDF2 and returned as markdown

   **Note:** `curl` fails on docs.trendmicro.com PDFs (Akamai CDN redirect loop, exit 47).
   The `ohc.blob.core.windows.net` PDFs work with curl but use the executor for consistency.

3. **Present findings** to the user. ALWAYS include both parts:

   **Summary** - Concise answer in your own words. Use tables, bullet points, and
   headings to organize. Don't dump raw extracted text - synthesize it.

   **Sources** - List every page you extracted from, at the end:
   ```
   Sources:
   - [Page Title (OLH)](https://docs.trendmicro.com/...)
   - [Article Title (KB)](https://success.trendmicro.com/...)
   ```
   Label each source type: OLH, KB, or PDF. This lets the user click through to verify.

   **File Saves** - If any files were downloaded/generated, list them:
   ```
   Files saved:
   - ~/Downloads/ddan_7.6_idg.pdf
   - ~/Downloads/dd-ports-reference.md
   ```

## Best Practice Guides Index

Master list of all Trend Micro product best practice guides (PDFs):
**https://success.trendmicro.com/en-US/solution/KA-0007901**

Use this page when the user asks about best practices for any Trend Micro product.
Extract with executor.py first to get PDF download links, then download and read the PDFs.

## Speed: Cache + Slug Index

The executor caches extracted pages as `.md` files in `~/.claude/skills/trend-docs/cache/`.
Cache is checked BEFORE launching a browser. Cached pages are served in <0.1s vs ~15s.

- **Cache TTL:** 30 days. Docs rarely change; stale entries re-fetched after TTL expires.
- **`--no-cache`:** Force fresh fetch, bypass cache.
- **`--topic "keyword"`:** Look up a topic in `doc-slugs.yaml` to skip WebSearch entirely.
- **`--check-cache`:** Check cached pages for content changes (launches Playwright, hashes live innerText). First run seeds hashes; subsequent runs detect changes.
- **`--check-cache --refresh`:** Auto-refresh stale pages in one pass.
- **`--check-cache --topic "X"`:** Check only pages in a specific topic bundle.

**Use `--topic` for known V1 endpoint policy pages** -- eliminates both WebSearch AND
Playwright overhead on repeat access. If the topic isn't found, it prints all known topics.

## Usage Examples

```bash
# Topic lookup (fastest -- slug index + cache, no WebSearch needed)
python ~/.claude/skills/trend-docs/executor.py --topic "anti-malware scans"
python ~/.claude/skills/trend-docs/executor.py --topic "firewall policy"
python ~/.claude/skills/trend-docs/executor.py --topic "apex web reputation"

# Batch URLs from WebSearch results (cached on first fetch)
python ~/.claude/skills/trend-docs/executor.py --urls "URL1,URL2,URL3" --max-pages 5

# Single URL
python ~/.claude/skills/trend-docs/executor.py "https://docs.trendmicro.com/en-us/documentation/article/trend-vision-one-workbench"

# Slug shorthand (OLH only)
python ~/.claude/skills/trend-docs/executor.py "trend-vision-one-workbench"

# Force fresh fetch (ignore cache)
python ~/.claude/skills/trend-docs/executor.py --no-cache --topic "endpoint security policies"

# Check if cached pages have changed (seeds hashes on first run)
python ~/.claude/skills/trend-docs/executor.py --check-cache

# Check + auto-refresh changed pages
python ~/.claude/skills/trend-docs/executor.py --check-cache --refresh

# Check only a specific topic bundle
python ~/.claude/skills/trend-docs/executor.py --check-cache --topic "sep policy"
```

## Output

Clean markdown with:
- Page title as heading
- Source URL for each page
- Content: paragraphs, tables, lists, code blocks
- Related pages (parent/sibling/child) with type labels
- Section dividers between pages
