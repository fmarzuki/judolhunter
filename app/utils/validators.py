"""URL and domain validation utilities."""
import re
from typing import Any
from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL."""
    if not url or not isinstance(url, str):
        return False

    url = url.strip()
    if not url:
        return False

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """Normalize URL for storage and comparison."""
    url = url.strip()

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Parse and reconstruct
    parsed = urlparse(url)

    # Remove default port
    if parsed.port in (80, 443):
        netloc = parsed.netloc.replace(f":{parsed.port}", "")
    else:
        netloc = parsed.netloc

    # Lowercase domain and scheme
    normalized = f"{parsed.scheme.lower()}://{netloc.lower()}{parsed.path}"

    # Remove fragment
    normalized = normalized.split("#")[0]

    return normalized


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    url = normalize_url(url)
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Remove www. prefix for consistency
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def is_internal_url(url: str, base_url: str) -> bool:
    """Check if URL is internal to the base URL's domain."""
    url_domain = extract_domain(url)
    base_domain = extract_domain(base_url)

    return url_domain == base_domain


def sanitize_url(url: str, allowed_schemes: tuple[str, ...] = ("http", "https")) -> str:
    """Sanitize URL by ensuring it uses an allowed scheme."""
    url = url.strip()

    if not url:
        return ""

    parsed = urlparse(url)

    if not parsed.scheme:
        # Default to https
        url = "https://" + url
        parsed = urlparse(url)

    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed")

    return normalize_url(url)


def batch_validate_urls(urls: list[str], max_count: int = 1000) -> tuple[list[str], list[str]]:
    """Validate a batch of URLs.

    Returns:
        (valid_urls, invalid_urls)
    """
    if len(urls) > max_count:
        raise ValueError(f"Maximum {max_count} URLs allowed per batch")

    valid = []
    invalid = []

    for url in urls:
        url = url.strip()
        if not url:
            continue

        if is_valid_url(url):
            valid.append(normalize_url(url))
        else:
            invalid.append(url)

    return valid, invalid


def is_suspicious_domain(domain: str) -> bool:
    """Check if domain matches known suspicious patterns."""
    suspicious_patterns = [
        r".*\.ru$",  # Russian TLD (often used for spam)
        r".*\d{3,}.*",  # Domains with multiple consecutive numbers
        r".*[a-z]{20,}",  # Very long letter sequences
    ]

    domain_lower = domain.lower()

    for pattern in suspicious_patterns:
        if re.match(pattern, domain_lower):
            return True

    return False
