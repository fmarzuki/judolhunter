#!/usr/bin/env python3
"""Judol Hunter - Deteksi URL Tersusupi Link Judol (Judi Online).

Mensimulasikan Googlebot untuk mendeteksi halaman yang terinfeksi cloaking
dan konten judi online tersembunyi.
"""

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.69 "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

PATTERNS_FILE = Path(__file__).parent / "patterns.json"



def load_patterns() -> dict:
    """Load keyword patterns from patterns.json."""
    with open(PATTERNS_FILE, encoding="utf-8") as f:
        return json.load(f)


PATTERNS = load_patterns()


def fetch_as_googlebot(url: str, timeout: float = 15.0, verbose: bool = False) -> dict:
    """Fetch URL dengan User-Agent Googlebot.

    Returns dict with keys: status_code, html, headers, redirects, error.
    """
    return _fetch(url, GOOGLEBOT_UA, "Googlebot", timeout=timeout, verbose=verbose)


def fetch_as_browser(url: str, timeout: float = 15.0, verbose: bool = False) -> dict:
    """Fetch URL dengan User-Agent Chrome browser biasa.

    Returns dict with keys: status_code, html, headers, redirects, error.
    """
    return _fetch(url, BROWSER_UA, "Browser", timeout=timeout, verbose=verbose)


def _fetch(url: str, user_agent: str, label: str, timeout: float = 15.0, verbose: bool = False) -> dict:
    """Internal fetch helper."""
    result = {
        "status_code": None,
        "html": "",
        "headers": {},
        "redirects": [],
        "final_url": url,
        "error": None,
    }
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": user_agent},
            verify=False,
        ) as client:
            response = client.get(url)
            result["status_code"] = response.status_code
            result["html"] = response.text
            result["headers"] = dict(response.headers)
            result["final_url"] = str(response.url)
            result["redirects"] = [
                {"url": str(r.url), "status_code": r.status_code}
                for r in response.history
            ]
            if verbose:
                console.print(f"  [{label}] Status: {response.status_code}, URL: {response.url}")
    except httpx.HTTPError as e:
        result["error"] = str(e)
        if verbose:
            console.print(f"  [{label}] Error: {e}", style="red")
    return result


def detect_gambling_keywords(html: str) -> list[dict]:
    """Scan HTML untuk keyword judi/slot/togel.

    Returns list of dicts: {keyword, count, context}.
    """
    findings = []
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True).lower()

    for keyword in PATTERNS["gambling_keywords"]:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        matches = pattern.findall(text)
        if matches:
            # Ambil snippet konteks
            idx = text.find(keyword.lower())
            start = max(0, idx - 40)
            end = min(len(text), idx + len(keyword) + 40)
            context = text[start:end].strip()
            findings.append({
                "keyword": keyword,
                "count": len(matches),
                "context": f"...{context}...",
            })
    return findings


def detect_suspicious_links(html: str) -> list[dict]:
    """Cari link eksternal ke domain judi yang dikenal.

    Returns list of dicts: {url, domain, reason}.
    """
    soup = BeautifulSoup(html, "html.parser")
    findings = []
    seen = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if not href.startswith(("http://", "https://")):
            continue

        parsed = urlparse(href)
        domain = parsed.netloc.lower()
        if domain in seen:
            continue
        seen.add(domain)

        # Cek domain cocok dengan known gambling domains
        for gambling_domain in PATTERNS["known_gambling_domains"]:
            if gambling_domain in domain:
                findings.append({
                    "url": href,
                    "domain": domain,
                    "reason": f"Domain mengandung '{gambling_domain}'",
                })
                break
        else:
            # Cek URL path patterns
            full = (domain + parsed.path).lower()
            for pattern in PATTERNS["suspicious_url_patterns"]:
                if pattern in full:
                    findings.append({
                        "url": href,
                        "domain": domain,
                        "reason": f"URL mengandung pattern '{pattern}'",
                    })
                    break

    return findings


def detect_hidden_elements(html: str) -> list[dict]:
    """Deteksi elemen tersembunyi (display:none, visibility:hidden, etc.) yang berisi spam."""
    soup = BeautifulSoup(html, "html.parser")
    findings = []

    hidden_patterns = [
        re.compile(r"display\s*:\s*none", re.IGNORECASE),
        re.compile(r"visibility\s*:\s*hidden", re.IGNORECASE),
        re.compile(r"position\s*:\s*absolute.*(?:left|top)\s*:\s*-\d{4,}", re.IGNORECASE),
        re.compile(r"overflow\s*:\s*hidden.*(?:height|width)\s*:\s*[01]px", re.IGNORECASE),
        re.compile(r"text-indent\s*:\s*-\d{4,}", re.IGNORECASE),
        re.compile(r"font-size\s*:\s*0", re.IGNORECASE),
        re.compile(r"opacity\s*:\s*0(?:\.0+)?(?:;|$)", re.IGNORECASE),
    ]

    for el in soup.find_all(style=True):
        style = el.get("style", "")
        for pat in hidden_patterns:
            if pat.search(style):
                text = el.get_text(strip=True)[:200]
                if text and _text_has_gambling(text):
                    findings.append({
                        "tag": el.name,
                        "style": style[:100],
                        "text_preview": text,
                    })
                break

    return findings


def detect_meta_injection(html: str) -> list[dict]:
    """Cek meta description/keywords yang disusupi konten judol."""
    soup = BeautifulSoup(html, "html.parser")
    findings = []

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").lower()
        content = (meta.get("content") or "").lower()
        if name in ("description", "keywords", "og:description", "og:title"):
            if _text_has_gambling(content):
                findings.append({
                    "meta": name,
                    "content": content[:200],
                })

    # Cek title tag juga
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True).lower()
        if _text_has_gambling(title_text):
            findings.append({
                "meta": "title",
                "content": title_text[:200],
            })

    return findings


def _text_has_gambling(text: str) -> bool:
    """Quick check apakah teks mengandung keyword gambling."""
    text_lower = text.lower()
    for kw in PATTERNS["gambling_keywords"]:
        if kw in text_lower:
            return True
    return False


def compare_responses(bot_result: dict, user_result: dict) -> dict:
    """Bandingkan response Googlebot vs browser biasa untuk deteksi cloaking.

    Returns dict: {is_cloaking, similarity, details}.
    """
    result = {
        "is_cloaking": False,
        "similarity": 1.0,
        "details": [],
    }

    # Cek redirect berbeda
    bot_final = bot_result.get("final_url", "")
    user_final = user_result.get("final_url", "")
    if bot_final != user_final:
        result["is_cloaking"] = True
        result["details"].append(
            f"Redirect berbeda: Googlebot -> {bot_final}, Browser -> {user_final}"
        )

    # Cek status code berbeda
    if bot_result.get("status_code") != user_result.get("status_code"):
        result["details"].append(
            f"Status code berbeda: Googlebot={bot_result.get('status_code')}, "
            f"Browser={user_result.get('status_code')}"
        )

    # Bandingkan konten teks
    bot_html = bot_result.get("html", "")
    user_html = user_result.get("html", "")

    if not bot_html or not user_html:
        return result

    bot_text = BeautifulSoup(bot_html, "html.parser").get_text(separator=" ", strip=True)
    user_text = BeautifulSoup(user_html, "html.parser").get_text(separator=" ", strip=True)

    # Similarity ratio
    similarity = SequenceMatcher(None, bot_text[:5000], user_text[:5000]).ratio()
    result["similarity"] = round(similarity, 3)

    if similarity < 0.7:
        result["is_cloaking"] = True
        result["details"].append(
            f"Konten sangat berbeda (similarity: {similarity:.1%})"
        )

        # Cek apakah konten Googlebot punya gambling keywords tapi browser tidak
        bot_has_gambling = _text_has_gambling(bot_text)
        user_has_gambling = _text_has_gambling(user_text)
        if bot_has_gambling and not user_has_gambling:
            result["details"].append(
                "Konten judol hanya muncul di response Googlebot (cloaking terdeteksi)"
            )

    return result


def _extract_urls_from_html(html: str, base_url: str) -> set[str]:
    """Extract semua URL (link, script, iframe, form, img) dari HTML."""
    soup = BeautifulSoup(html, "html.parser")
    parsed_base = urlparse(base_url)
    urls = set()

    # <a href>, <area href>
    for tag in soup.find_all(["a", "area"], href=True):
        urls.add(tag["href"])

    # <script src>, <img src>, <iframe src>, <embed src>, <source src>
    for tag in soup.find_all(["script", "img", "iframe", "embed", "source", "video", "audio"], src=True):
        urls.add(tag["src"])

    # <link href> (stylesheet, dll)
    for tag in soup.find_all("link", href=True):
        urls.add(tag["href"])

    # <form action>
    for tag in soup.find_all("form", action=True):
        urls.add(tag["action"])

    # Resolve ke absolute URL dan filter internal only
    resolved = set()
    for raw in urls:
        if not raw or raw.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
            continue
        # Skip malformed URLs (mis: hhttps://, htttps://)
        if re.match(r"^h+ttps?://", raw) and not re.match(r"^https?://", raw):
            continue
        full = urljoin(base_url, raw)
        full_parsed = urlparse(full)
        if full_parsed.netloc == parsed_base.netloc:
            clean = full.split("#")[0].split("?")[0]
            resolved.add(clean)

    return resolved


def discover_paths(base_url: str, verbose: bool = False) -> list[str]:
    """Discover subpages tersusupi dari konten cloaking.

    Cara kerja:
    1. Fetch halaman sebagai Googlebot dan sebagai Browser
    2. Extract semua URL/asset dari kedua response
    3. Path yang HANYA ada di response Googlebot = kemungkinan inject
    4. Semua internal path dari response Googlebot juga di-scan
    Returns list of discovered URLs to scan.
    """
    parsed = urlparse(base_url)
    seen = {base_url.rstrip("/")}

    console.print(f"\n[bold cyan]Crawling:[/bold cyan] {base_url}")
    console.print("  Fetching as Googlebot...", style="dim")
    bot_result = fetch_as_googlebot(base_url, verbose=verbose)
    console.print("  Fetching as Browser...", style="dim")
    user_result = fetch_as_browser(base_url, verbose=verbose)

    bot_html = bot_result.get("html", "")
    user_html = user_result.get("html", "")

    if not bot_html:
        console.print("  [red]Gagal fetch sebagai Googlebot[/red]")
        return []

    # Extract semua URL dari kedua response
    bot_urls = _extract_urls_from_html(bot_html, base_url)
    user_urls = _extract_urls_from_html(user_html, base_url) if user_html else set()

    # Path yang HANYA muncul di response Googlebot (inject)
    injected_only = bot_urls - user_urls

    # Categorize
    discovered_injected = []
    discovered_shared = []

    for url in sorted(bot_urls):
        if url.rstrip("/") in seen:
            continue
        seen.add(url.rstrip("/"))

        # Filter: skip asset statis yang bukan halaman
        url_path = urlparse(url).path.lower()
        is_page = (
            url_path.endswith((".php", ".html", ".htm", ".asp", ".aspx", "/"))
            or "." not in Path(url_path).name
        )
        is_asset = url_path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".ico", ".webp", ".mp4", ".mp3"))

        if is_asset:
            continue

        if url in injected_only:
            discovered_injected.append(url)
            if verbose:
                console.print(f"    [red]⚡ INJECT:[/red] {url_path}")
        elif is_page:
            discovered_shared.append(url)
            if verbose:
                console.print(f"    [dim]   shared:[/dim] {url_path}")

    # Prioritas: injected paths duluan, lalu shared
    discovered = discovered_injected + discovered_shared

    if injected_only:
        console.print(f"  [red]⚡ {len(discovered_injected)} path hanya ada di response Googlebot (injected)[/red]")
    console.print(f"  [bold]Total {len(discovered)} subpage untuk di-scan[/bold]")
    return discovered


def scan_url(url: str, verbose: bool = False) -> dict:
    """Scan satu URL - orchestrator utama.

    Returns dict with full scan result.
    """
    console.print(f"\n[bold cyan]Scanning:[/bold cyan] {url}")

    # Dual fetch
    if verbose:
        console.print("  Fetching as Googlebot...", style="dim")
    bot_result = fetch_as_googlebot(url, verbose=verbose)

    if verbose:
        console.print("  Fetching as Browser...", style="dim")
    user_result = fetch_as_browser(url, verbose=verbose)

    scan = {
        "url": url,
        "status": "clean",
        "risk_level": "low",
        "findings": {},
        "fetch_info": {
            "googlebot": {
                "status_code": bot_result["status_code"],
                "final_url": bot_result["final_url"],
                "redirects": bot_result["redirects"],
                "error": bot_result["error"],
            },
            "browser": {
                "status_code": user_result["status_code"],
                "final_url": user_result["final_url"],
                "redirects": user_result["redirects"],
                "error": user_result["error"],
            },
        },
    }

    if bot_result["error"] and user_result["error"]:
        scan["status"] = "error"
        scan["risk_level"] = "unknown"
        _print_result(scan)
        return scan

    issues = []

    # 1. Cloaking detection
    cloaking = compare_responses(bot_result, user_result)
    scan["findings"]["cloaking"] = cloaking
    if cloaking["is_cloaking"]:
        issues.append("cloaking")

    # Gunakan response Googlebot untuk analisis (karena cloaking targetnya Googlebot)
    html = bot_result["html"] or user_result["html"] or ""

    # 2. Keyword detection
    keywords = detect_gambling_keywords(html)
    scan["findings"]["gambling_keywords"] = keywords
    if keywords:
        issues.append("gambling_keywords")

    # 3. Suspicious links
    links = detect_suspicious_links(html)
    scan["findings"]["suspicious_links"] = links
    if links:
        issues.append("suspicious_links")

    # 4. Hidden elements
    hidden = detect_hidden_elements(html)
    scan["findings"]["hidden_elements"] = hidden
    if hidden:
        issues.append("hidden_elements")

    # 5. Meta injection
    meta = detect_meta_injection(html)
    scan["findings"]["meta_injection"] = meta
    if meta:
        issues.append("meta_injection")

    # Determine risk level
    if cloaking["is_cloaking"] and keywords:
        scan["risk_level"] = "critical"
        scan["status"] = "infected"
    elif cloaking["is_cloaking"] or (keywords and len(keywords) >= 3):
        scan["risk_level"] = "high"
        scan["status"] = "suspicious"
    elif keywords or links or hidden or meta:
        scan["risk_level"] = "medium"
        scan["status"] = "suspicious"
    else:
        scan["risk_level"] = "low"
        scan["status"] = "clean"

    scan["issues"] = issues
    _print_result(scan)
    return scan


def _print_result(scan: dict) -> None:
    """Print scan result ke terminal dengan warna."""
    status = scan["status"]
    risk = scan["risk_level"]

    color_map = {
        "clean": "green",
        "suspicious": "yellow",
        "infected": "red",
        "error": "dim",
    }
    color = color_map.get(status, "white")

    risk_color_map = {
        "low": "green",
        "medium": "yellow",
        "high": "red",
        "critical": "bold red",
        "unknown": "dim",
    }
    risk_color = risk_color_map.get(risk, "white")

    console.print(
        Panel(
            f"[bold]Status:[/bold] [{color}]{status.upper()}[/{color}]  |  "
            f"[bold]Risk:[/bold] [{risk_color}]{risk.upper()}[/{risk_color}]",
            title=f"[bold]{scan['url']}[/bold]",
            border_style=color,
        )
    )

    findings = scan.get("findings", {})

    # Cloaking
    cloaking = findings.get("cloaking", {})
    if cloaking.get("is_cloaking"):
        console.print("  [red]⚠ CLOAKING TERDETEKSI[/red]")
        for detail in cloaking.get("details", []):
            console.print(f"    - {detail}")
    elif cloaking:
        console.print(f"  [green]✓[/green] Tidak ada cloaking (similarity: {cloaking.get('similarity', 'N/A')})")

    # Keywords
    keywords = findings.get("gambling_keywords", [])
    if keywords:
        console.print(f"  [red]⚠ {len(keywords)} keyword judol ditemukan:[/red]")
        for kw in keywords[:10]:
            console.print(f"    - \"{kw['keyword']}\" ({kw['count']}x)")
    else:
        console.print("  [green]✓[/green] Tidak ada keyword judol")

    # Links
    links = findings.get("suspicious_links", [])
    if links:
        console.print(f"  [red]⚠ {len(links)} link mencurigakan:[/red]")
        for link in links[:5]:
            console.print(f"    - {link['domain']} ({link['reason']})")

    # Hidden elements
    hidden = findings.get("hidden_elements", [])
    if hidden:
        console.print(f"  [yellow]⚠ {len(hidden)} elemen tersembunyi berisi spam[/yellow]")

    # Meta injection
    meta = findings.get("meta_injection", [])
    if meta:
        console.print(f"  [yellow]⚠ {len(meta)} meta tag tersusupi[/yellow]")
        for m in meta:
            console.print(f"    - <{m['meta']}>: {m['content'][:80]}...")

    # Error info
    fetch_info = scan.get("fetch_info", {})
    for label in ("googlebot", "browser"):
        err = fetch_info.get(label, {}).get("error")
        if err:
            console.print(f"  [dim]⚠ {label} error: {err}[/dim]")


def main():
    parser = argparse.ArgumentParser(
        description="Judol Hunter - Deteksi URL Tersusupi Link Judol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Contoh:\n"
            "  python googlebot.py https://example.com\n"
            "  python googlebot.py -f urls.txt\n"
            "  python googlebot.py -f urls.txt -o hasil.json\n"
            "  python googlebot.py https://example.com -v\n"
            "  python googlebot.py https://example.com --crawl\n"
        ),
    )
    parser.add_argument("url", nargs="?", help="URL yang akan di-scan")
    parser.add_argument("-f", "--file", help="File berisi daftar URL (satu per baris)")
    parser.add_argument("-o", "--output", help="Simpan hasil ke file JSON")
    parser.add_argument("-c", "--crawl", action="store_true", help="Crawl subpage untuk cari halaman tersusupi")
    parser.add_argument("-v", "--verbose", action="store_true", help="Tampilkan detail proses")

    args = parser.parse_args()

    if not args.url and not args.file:
        parser.print_help()
        sys.exit(1)

    urls = []
    if args.url:
        urls.append(args.url)
    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            console.print(f"[red]Error: File '{args.file}' tidak ditemukan[/red]")
            sys.exit(1)
        urls.extend(
            line.strip()
            for line in filepath.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if not urls:
        console.print("[red]Error: Tidak ada URL untuk di-scan[/red]")
        sys.exit(1)

    # Crawl mode: discover subpages
    if args.crawl:
        extra_urls = []
        for url in urls:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            extra_urls.extend(discover_paths(url, verbose=args.verbose))
        urls.extend(extra_urls)

    console.print(
        Panel(
            f"[bold]Judol Hunter[/bold] - Deteksi Link Judol\n"
            f"Total URL: {len(urls)}" + (" (crawl mode)" if args.crawl else ""),
            border_style="cyan",
        )
    )

    results = []
    for url in urls:
        # Pastikan URL punya scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        result = scan_url(url, verbose=args.verbose)
        results.append(result)

    # Summary
    console.print("\n")
    table = Table(title="Ringkasan Scan")
    table.add_column("URL", style="cyan", max_width=50)
    table.add_column("Status", justify="center")
    table.add_column("Risk", justify="center")
    table.add_column("Issues", justify="center")

    for r in results:
        status = r["status"]
        risk = r["risk_level"]
        color = {"clean": "green", "suspicious": "yellow", "infected": "red", "error": "dim"}.get(status, "white")
        risk_color = {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}.get(risk, "white")
        issues = ", ".join(r.get("issues", [])) or "-"
        table.add_row(
            r["url"],
            f"[{color}]{status.upper()}[/{color}]",
            f"[{risk_color}]{risk.upper()}[/{risk_color}]",
            issues,
        )

    console.print(table)

    # Export JSON
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"\n[green]Hasil disimpan ke {args.output}[/green]")


if __name__ == "__main__":
    main()
