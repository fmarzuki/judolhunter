#!/usr/bin/env python3
"""Judol Hunter - Deteksi URL Tersusupi Link Judol (Judi Online).

Mensimulasikan Googlebot untuk mendeteksi halaman yang terinfeksi cloaking
dan konten judi online tersembunyi.
"""

import argparse
import base64
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


def _extract_urls_from_js(script_content: str) -> list[str]:
    """Ekstrak URL http(s) dari konten inline <script>.

    Menangkap pola umum injeksi: window.location, document.write, variable assignment.
    """
    url_pattern = re.compile(r'https?://[^\s"\'<>\)\]\}\\]+')
    urls = url_pattern.findall(script_content)
    # Bersihkan trailing punctuation
    cleaned = []
    for u in urls:
        u = u.rstrip(".,;:!?")
        if len(u) > 10:
            cleaned.append(u)
    return cleaned


def _decode_obfuscated_urls(script_content: str) -> list[str]:
    """Decode URL dari pola obfuscation base64 (atob) di inline script."""
    urls = []
    # Cari pola atob("...") atau atob('...')
    atob_pattern = re.compile(r"""atob\s*\(\s*["']([A-Za-z0-9+/=]+)["']\s*\)""")
    for match in atob_pattern.finditer(script_content):
        encoded = match.group(1)
        try:
            decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
            # Ekstrak URL dari hasil decode
            found = re.findall(r'https?://[^\s"\'<>\)\]\}\\]+', decoded)
            urls.extend(found)
        except Exception:
            pass

    # Cari juga string base64 panjang yang di-assign ke variable
    b64_var_pattern = re.compile(r"""=\s*["']([A-Za-z0-9+/=]{20,})["']""")
    for match in b64_var_pattern.finditer(script_content):
        encoded = match.group(1)
        try:
            decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
            found = re.findall(r'https?://[^\s"\'<>\)\]\}\\]+', decoded)
            urls.extend(found)
        except Exception:
            pass

    return urls


def detect_suspicious_links(html: str, base_url: str = "") -> list[dict]:
    """Cari link eksternal ke domain judi dari berbagai sumber HTML.

    Scan: <a>, <iframe>, <embed>, <object>, <script src>, <form action>,
    <meta http-equiv="refresh">, data-href/data-url/data-src, inline JS URLs,
    dan base64 obfuscation.

    Returns list of dicts: {url, domain, reason, source}.
    """
    soup = BeautifulSoup(html, "html.parser")
    findings = []
    seen_urls = set()
    base_domain = urlparse(base_url).netloc.lower() if base_url else ""

    # Gambling keyword fragments untuk matching di URL/domain
    _gambling_url_keywords = re.compile(
        r"slot|togel|judi|casino|poker|gacor|maxwin|toto|mahjong|scatter|bonus.*member|rtp.*slot|freebet",
        re.IGNORECASE,
    )

    def _check_url(url: str, source: str) -> bool:
        """Cek satu URL apakah mencurigakan dan tambahkan ke findings.

        Returns True jika URL di-flag sebagai suspicious.
        """
        if not url or not url.startswith(("http://", "https://")):
            return False

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return False

        # Filter link internal (same-domain)
        if base_domain and domain == base_domain:
            return False

        # Deduplicate by full URL
        if url in seen_urls:
            return False
        seen_urls.add(url)

        # Cek domain cocok dengan known gambling domains
        for gambling_domain in PATTERNS["known_gambling_domains"]:
            if gambling_domain in domain:
                findings.append({
                    "url": url,
                    "domain": domain,
                    "reason": f"Domain mengandung '{gambling_domain}'",
                    "source": source,
                })
                return True

        # Cek URL path patterns
        full = (domain + parsed.path).lower()
        for pattern in PATTERNS["suspicious_url_patterns"]:
            if pattern in full:
                findings.append({
                    "url": url,
                    "domain": domain,
                    "reason": f"URL mengandung pattern '{pattern}'",
                    "source": source,
                })
                return True

        # Cek gambling keywords di domain+path (catch-all untuk domain baru)
        if _gambling_url_keywords.search(full):
            matched = _gambling_url_keywords.search(full).group(0)
            findings.append({
                "url": url,
                "domain": domain,
                "reason": f"URL mengandung keyword '{matched}'",
                "source": source,
            })
            return True

        return False

    # === Fase 1: Deteksi unconditional (selalu flag jika external) ===

    # 1. <link rel="amphtml"/"canonical"> pointing to external domains
    #    External amphtml/canonical = sangat mencurigakan (sering dipakai redirector judol)
    for tag in soup.find_all("link", href=True):
        rel = " ".join(tag.get("rel", []))
        if rel in ("amphtml", "canonical"):
            href = tag["href"]
            parsed = urlparse(href)
            link_domain = parsed.netloc.lower()
            if base_domain and link_domain and link_domain != base_domain:
                if href not in seen_urls:
                    seen_urls.add(href)
                    findings.append({
                        "url": href,
                        "domain": link_domain,
                        "reason": f"External <link rel={rel}> (kemungkinan redirector judol)",
                        "source": f"<link rel={rel}>",
                    })

    # === Fase 2: Deteksi pattern-based (flag jika cocok gambling patterns) ===

    # 2. <a href>, <area href>
    for tag in soup.find_all(["a", "area"], href=True):
        _check_url(tag["href"], f"<{tag.name} href>")

    # 3. <iframe src>, <embed src>, <object data>
    for tag in soup.find_all("iframe", src=True):
        _check_url(tag["src"], "<iframe src>")
    for tag in soup.find_all("embed", src=True):
        _check_url(tag["src"], "<embed src>")
    for tag in soup.find_all("object", data=True):
        _check_url(tag["data"], "<object data>")

    # 4. <script src>
    for tag in soup.find_all("script", src=True):
        _check_url(tag["src"], "<script src>")

    # 5. <form action>
    for tag in soup.find_all("form", action=True):
        _check_url(tag["action"], "<form action>")

    # 6. <meta http-equiv="refresh" content="...;url=...">
    for meta in soup.find_all("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)}):
        content = meta.get("content", "")
        match = re.search(r"url\s*=\s*['\"]?\s*(https?://[^\s'\"]+)", content, re.I)
        if match:
            _check_url(match.group(1), "<meta refresh>")

    # 7. data-href, data-url, data-src pada semua elemen
    for attr_name in ("data-href", "data-url", "data-src"):
        for tag in soup.find_all(attrs={attr_name: True}):
            _check_url(tag[attr_name], f"<{tag.name} {attr_name}>")

    # 8. Inline <script> — extract URLs dan decode obfuscation
    for tag in soup.find_all("script", src=False):
        script_text = tag.string or ""
        if not script_text.strip():
            continue
        # Skip JSON-LD (handled separately below)
        if tag.get("type") == "application/ld+json":
            continue
        # URL langsung di JS
        for url in _extract_urls_from_js(script_text):
            _check_url(url, "<script> inline JS")
        # Base64 / atob obfuscation
        for url in _decode_obfuscated_urls(script_text):
            _check_url(url, "<script> obfuscated (base64)")

    # 9. JSON-LD (<script type="application/ld+json">) — extract all URLs
    _safe_ld_domains = {"schema.org", "w3.org", "www.w3.org"}
    for tag in soup.find_all("script", type="application/ld+json"):
        ld_text = tag.string or ""
        if not ld_text.strip():
            continue
        for url in re.findall(r'https?://[^\s"\'<>\\]+', ld_text):
            url = url.rstrip(".,;:!?")
            ld_domain = urlparse(url).netloc.lower()
            if ld_domain in _safe_ld_domains:
                continue
            _check_url(url, "<script> JSON-LD")

    # 10. <img src> dari domain external
    for tag in soup.find_all("img", src=True):
        src = tag["src"]
        if src.startswith(("http://", "https://")):
            _check_url(src, "<img src>")

    # 11. Anchor text berisi domain judol (internal links yang teks-nya menyebut domain gambling)
    #     Pola umum injeksi: <a href="internal">SULTAN188z.space -5k-</a>
    #     Domain di anchor text pada link internal yang sudah terinfeksi = pasti judol
    _domain_like = re.compile(
        r'\b([a-zA-Z0-9][\w-]*\d+[\w-]*\.(?:com|net|org|online|site|space|fun|art|link|cc|id|info|cloud|dev))\b',
        re.IGNORECASE,
    )
    seen_anchor_domains = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        parsed_href = urlparse(href)
        href_domain = parsed_href.netloc.lower()
        # Hanya proses link internal yang anchor text-nya mencurigakan
        if base_domain and href_domain == base_domain:
            anchor_text = tag.get_text(strip=True)
            if not anchor_text:
                continue
            for m in _domain_like.finditer(anchor_text):
                domain_in_text = m.group(1).lower()
                if domain_in_text == base_domain or domain_in_text in seen_anchor_domains:
                    continue
                seen_anchor_domains.add(domain_in_text)
                fake_url = f"https://{domain_in_text}"
                if fake_url not in seen_urls:
                    seen_urls.add(fake_url)
                    findings.append({
                        "url": fake_url,
                        "domain": domain_in_text,
                        "reason": f"Domain judol disebut di anchor text: '{anchor_text[:60]}'",
                        "source": "<a> anchor text",
                    })

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
    links = detect_suspicious_links(html, base_url=url)
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
        # Pisahkan: link dengan URL asli vs domain dari anchor text
        real_links = [l for l in links if l.get("source") != "<a> anchor text"]
        anchor_domains = [l for l in links if l.get("source") == "<a> anchor text"]

        console.print(f"  [red]⚠ {len(links)} link/domain judol ditemukan:[/red]")

        if real_links:
            console.print(f"    [bold]URL eksternal mencurigakan ({len(real_links)}):[/bold]")
            for link in real_links[:10]:
                source = link.get("source", "")
                source_info = f" [dim]via {source}[/dim]" if source else ""
                console.print(f"      - [bold]{link['url']}[/bold]{source_info}")
                console.print(f"        {link['reason']}")
            if len(real_links) > 10:
                console.print(f"      [dim]... dan {len(real_links) - 10} lainnya[/dim]")

        if anchor_domains:
            console.print(f"    [bold]Domain judol dari anchor text ({len(anchor_domains)}):[/bold]")
            for link in anchor_domains[:15]:
                console.print(f"      - [bold]{link['domain']}[/bold]")
            if len(anchor_domains) > 15:
                console.print(f"      [dim]... dan {len(anchor_domains) - 15} lainnya[/dim]")

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
