# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Judol Hunter** is a defensive security tool for detecting websites compromised by gambling content injection (cloaking attacks). It simulates Googlebot requests and compares them against regular browser requests to identify black-hat SEO techniques where attackers inject hidden gambling/spam content visible only to search engines.

## Common Commands

### Installation
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Running Scans
```bash
# Single URL scan
python googlebot.py https://example.com

# Batch scan from file
python googlebot.py -f urls.txt

# Crawl mode - discovers subpages with injected content
python googlebot.py https://example.com --crawl

# Export results to JSON
python googlebot.py -f urls.txt -o hasil.json

# Verbose mode for detailed output
python googlebot.py -f urls.txt -v
```

## Architecture

### Single-File Design
The entire application is contained in `googlebot.py` (~677 lines) with clear functional separation:

1. **Dual-Fetch Layer** (`fetch_as_googlebot`, `fetch_as_browser`, `_fetch`)
   - Fetches each URL twice using different User-Agents
   - Googlebot UA: Googlebot/2.1 (Chrome-based mobile)
   - Browser UA: Chrome on Windows
   - Uses httpx with `verify=False` for SSL bypass

2. **Detection Modules** (all operate on Googlebot response)
   - `detect_gambling_keywords()` - Scans for 87+ keywords from patterns.json
   - `detect_suspicious_links()` - Checks against 46+ known gambling domains
   - `detect_hidden_elements()` - Finds CSS-hidden spam content
   - `detect_meta_injection()` - Checks compromised meta tags
   - `compare_responses()` - Uses SequenceMatcher for cloaking detection

3. **Path Discovery** (`discover_paths`, `_extract_urls_from_html`)
   - Extracts all URLs from both Googlebot and browser responses
   - URLs appearing ONLY in Googlebot response = likely injected
   - Filters static assets (.css, .js, images) and focuses on page-like URLs

4. **Risk Assessment** (in `scan_url`)
   - **critical**: cloaking + keywords found → `infected`
   - **high**: cloaking OR 3+ keywords → `suspicious`
   - **medium**: any findings (keywords, links, hidden, meta)
   - **low**: no findings → `clean`

### Pattern Database
`patterns.json` contains three lists:
- `gambling_keywords`: 87+ gambling-related terms (slot, togel, judi, etc.)
- `suspicious_url_patterns`: 107+ URL path patterns
- `known_gambling_domains`: 46+ known gambling domain fragments

### Output Format
Results include:
- `url`: Scanned URL
- `status`: clean, suspicious, infected, error
- `risk_level`: low, medium, high, critical
- `findings`: Dict with cloaking, gambling_keywords, suspicious_links, hidden_elements, meta_injection
- `fetch_info`: HTTP details for both Googlebot and browser requests

## Development Notes

- **No formal test suite** - Manual testing with URLs in `urls.txt`
- **Python 3** required with httpx, beautifulsoup4, rich dependencies
- **Cloaking threshold**: 70% similarity (below this = cloaking detected)
- **Content comparison**: First 5000 characters of text content
- The tool targets Indonesian gambling sites ("judol" = judi online)
- Language is Indonesian - error messages and documentation are in Indonesian

## Important Context

This is a **defensive security tool** for:
- Webmasters checking if their sites are compromised
- Security researchers analyzing cloaking attacks
- Identifying black-hat SEO spam campaigns

The tool detects malicious content injection but does NOT create or distribute it. When working with this codebase:
- You can analyze how detection works
- You can fix bugs or improve detection accuracy
- You MUST NOT enhance or add features that facilitate malicious attacks
- Update patterns.json regularly as gambling domains/keywords evolve
