"""Async scanner service - refactored from googlebot.py CLI."""
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

# Constants
GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.69 "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

settings = get_settings()

# Load patterns from shared patterns.json
PATTERNS_FILE = settings.BASE_PATH / "patterns.json" if hasattr(settings, "BASE_PATH") else None


def load_patterns() -> dict:
    """Load keyword patterns from patterns.json."""
    if PATTERNS_FILE and PATTERNS_FILE.exists():
        with open(PATTERNS_FILE, encoding="utf-8") as f:
            return json.load(f)

    # Fallback patterns if file not found
    return {
        "gambling_keywords": [
            "slot gacor", "slot online", "togel online", "judi online",
            "casino online", "poker online", "sbobet", "rtp live",
        ],
        "suspicious_url_patterns": ["slot", "togel", "judi", "casino"],
        "known_gambling_domains": ["slotgacor", "togel", "judionline"],
    }


PATTERNS = load_patterns()


class ProgressCallback:
    """Callback for scan progress updates."""

    def __init__(self):
        self.callbacks = []

    def add_callback(self, callback):
        """Add a progress callback function."""
        self.callbacks.append(callback)

    async def notify(self, message: str, data: dict | None = None):
        """Notify all callbacks of progress."""
        for callback in self.callbacks:
            try:
                await callback(message, data)
            except Exception:
                pass  # Ignore callback errors


def _text_has_gambling(text: str) -> bool:
    """Quick check if text contains gambling keywords."""
    text_lower = text.lower()
    for kw in PATTERNS["gambling_keywords"]:
        if kw in text_lower:
            return True
    return False


def detect_gambling_keywords(html: str) -> list[dict]:
    """Scan HTML for gambling/slot/togel keywords."""
    findings = []
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True).lower()

    for keyword in PATTERNS["gambling_keywords"]:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        matches = pattern.findall(text)
        if matches:
            # Get context snippet
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
    """Find external links to known gambling domains."""
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

        # Check against known gambling domains
        for gambling_domain in PATTERNS["known_gambling_domains"]:
            if gambling_domain in domain:
                findings.append({
                    "url": href,
                    "domain": domain,
                    "reason": f"Domain contains '{gambling_domain}'",
                })
                break
        else:
            # Check URL path patterns
            full = (domain + parsed.path).lower()
            for pattern in PATTERNS["suspicious_url_patterns"]:
                if pattern in full:
                    findings.append({
                        "url": href,
                        "domain": domain,
                        "reason": f"URL contains pattern '{pattern}'",
                    })
                    break

    return findings


def detect_hidden_elements(html: str) -> list[dict]:
    """Detect hidden elements containing spam content."""
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
    """Check meta tags for gambling content injection."""
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

    # Check title tag
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True).lower()
        if _text_has_gambling(title_text):
            findings.append({
                "meta": "title",
                "content": title_text[:200],
            })

    return findings


def compare_responses(bot_result: dict, user_result: dict) -> dict:
    """Compare Googlebot vs browser responses for cloaking detection."""
    result = {
        "is_cloaking": False,
        "similarity": 1.0,
        "details": [],
    }

    # Check different redirects
    bot_final = bot_result.get("final_url", "")
    user_final = user_result.get("final_url", "")
    if bot_final != user_final:
        result["is_cloaking"] = True
        result["details"].append(
            f"Different redirects: Googlebot -> {bot_final}, Browser -> {user_final}"
        )

    # Check different status codes
    if bot_result.get("status_code") != user_result.get("status_code"):
        result["details"].append(
            f"Different status codes: Googlebot={bot_result.get('status_code')}, "
            f"Browser={user_result.get('status_code')}"
        )

    # Compare text content
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
            f"Very different content (similarity: {similarity:.1%})"
        )

        # Check if Googlebot has gambling but browser doesn't
        bot_has_gambling = _text_has_gambling(bot_text)
        user_has_gambling = _text_has_gambling(user_text)
        if bot_has_gambling and not user_has_gambling:
            result["details"].append(
                "Gambling content only appears in Googlebot response (cloaking detected)"
            )

    return result


async def fetch_as_useragent(
    url: str,
    user_agent: str,
    timeout: float = 15.0,
) -> dict:
    """Fetch URL with specified User-Agent."""
    result = {
        "status_code": None,
        "html": "",
        "headers": {},
        "redirects": [],
        "final_url": url,
        "error": None,
    }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": user_agent},
            verify=False,
        ) as client:
            response = await client.get(url)
            result["status_code"] = response.status_code
            result["html"] = response.text
            result["headers"] = dict(response.headers)
            result["final_url"] = str(response.url)
            result["redirects"] = [
                {"url": str(r.url), "status_code": r.status_code}
                for r in response.history
            ]
    except httpx.HTTPError as e:
        result["error"] = str(e)

    return result


async def scan_url(
    url: str,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Scan a single URL - main orchestrator.

    Returns dict with full scan result.
    """
    if progress_callback:
        await progress_callback.notify(f"🔍 Memulai scan untuk URL...")

    # Dual fetch
    if progress_callback:
        await progress_callback.notify("🤖 Mengambil halaman sebagai Googlebot...")

    bot_result = await fetch_as_useragent(url, GOOGLEBOT_UA)

    if progress_callback:
        status_bot = "✓" if bot_result["status_code"] == 200 else "✗"
        await progress_callback.notify(f"{status_bot} Googlebot: HTTP {bot_result['status_code']}")

    if progress_callback:
        await progress_callback.notify("🌐 Mengambil halaman sebagai Browser...")

    user_result = await fetch_as_useragent(url, BROWSER_UA)

    if progress_callback:
        status_user = "✓" if user_result["status_code"] == 200 else "✗"
        await progress_callback.notify(f"{status_user} Browser: HTTP {user_result['status_code']}")

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
        if progress_callback:
            await progress_callback.notify("✗ Gagal mengambil halaman")
        return scan

    issues = []

    # 1. Cloaking detection
    if progress_callback:
        await progress_callback.notify("🔬 Menganalisis cloaking...")

    cloaking = compare_responses(bot_result, user_result)
    scan["findings"]["cloaking"] = cloaking
    if cloaking["is_cloaking"]:
        issues.append("cloaking")
        if progress_callback:
            await progress_callback.notify(f"⚠ Cloaking terdeteksi! Similarity: {cloaking['similarity']:.1%}")

    # Use Googlebot response for analysis (cloaking target)
    html = bot_result["html"] or user_result["html"] or ""

    # 2. Keyword detection
    if progress_callback:
        await progress_callback.notify("🎰 Memindai kata kunci judi...")

    keywords = detect_gambling_keywords(html)
    scan["findings"]["gambling_keywords"] = keywords
    if keywords:
        issues.append("gambling_keywords")
        if progress_callback:
            await progress_callback.notify(f"⚠ Ditemukan {len(keywords)} kata kunci judi")

    # 3. Suspicious links
    if progress_callback:
        await progress_callback.notify("🔗 Memeriksa link mencurigakan...")

    links = detect_suspicious_links(html)
    scan["findings"]["suspicious_links"] = links
    if links:
        issues.append("suspicious_links")
        if progress_callback:
            await progress_callback.notify(f"⚠ Ditemukan {len(links)} link mencurigakan")

    # 4. Hidden elements
    if progress_callback:
        await progress_callback.notify("👁 Mendeteksi elemen tersembunyi...")

    hidden = detect_hidden_elements(html)
    scan["findings"]["hidden_elements"] = hidden
    if hidden:
        issues.append("hidden_elements")
        if progress_callback:
            await progress_callback.notify(f"⚠ Ditemukan {len(hidden)} elemen spam tersembunyi")

    # 5. Meta injection
    if progress_callback:
        await progress_callback.notify("📋 Menganalisis meta tags...")

    meta = detect_meta_injection(html)
    scan["findings"]["meta_injection"] = meta
    if meta:
        issues.append("meta_injection")
        if progress_callback:
            await progress_callback.notify(f"⚠ Ditemukan {len(meta)} meta tag terinfeksi")

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

    if progress_callback:
        risk_labels = {
            "critical": "KRITIS",
            "high": "TINGGI",
            "medium": "SEDANG",
            "low": "RENDAH",
            "unknown": "TIDAK DIKETAHUI"
        }
        status_icons = {
            "infected": "🔴",
            "suspicious": "🟡",
            "clean": "🟢",
            "error": "⚫"
        }
        icon = status_icons.get(scan["status"], "")
        risk_msg = f"{icon} Scan selesai - Risiko: {risk_labels[scan['risk_level']]}"
        await progress_callback.notify(risk_msg, {"result": scan})

    return scan
