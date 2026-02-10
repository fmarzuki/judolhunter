"""Terminal output formatting utilities."""
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def format_terminal_output(text: str, style: str = "green") -> str:
    """Format text for terminal display."""
    return f"[{style}]{text}[/{style}]"


def format_scan_result(result: dict[str, Any]) -> str:
    """Format scan result as terminal-style output."""
    from io import StringIO

    buffer = StringIO()

    # Status header
    status = result.get("status", "unknown")
    risk = result.get("risk_level", "unknown")

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

    buffer.write(f"┌─ {result['url']} ─" + "─" * 40 + "\n")
    buffer.write(f"│ Status: [{color}]{status.upper()}[/{color}]  │  Risk: [{risk_color}]{risk.upper()}[/{risk_color}]\n")
    buffer.write("└" + "─" * 80 + "\n")

    # Findings
    findings = result.get("findings", {})

    # Cloaking
    cloaking = findings.get("cloaking", {})
    if cloaking.get("is_cloaking"):
        buffer.write("⚠ CLOAKING DETECTED\n")
        for detail in cloaking.get("details", []):
            buffer.write(f"  - {detail}\n")
    elif cloaking:
        buffer.write(f"✓ No cloaking (similarity: {cloaking.get('similarity', 'N/A')})\n")

    # Keywords
    keywords = findings.get("gambling_keywords", [])
    if keywords:
        buffer.write(f"⚠ {len(keywords)} gambling keywords found:\n")
        for kw in keywords[:10]:
            buffer.write(f"  - \"{kw['keyword']}\" ({kw['count']}x)\n")

    # Links
    links = findings.get("suspicious_links", [])
    if links:
        buffer.write(f"⚠ {len(links)} suspicious links:\n")
        for link in links[:5]:
            buffer.write(f"  - {link['domain']} ({link['reason']})\n")

    return buffer.getvalue()


def format_progress_bar(
    current: int,
    total: int,
    width: int = 40,
    prefix: str = "",
) -> str:
    """Format a terminal progress bar."""
    if total == 0:
        progress = 1.0
    else:
        progress = current / total

    filled = int(width * progress)
    bar = "█" * filled + "░" * (width - filled)

    if prefix:
        return f"{prefix} [{bar}] {current}/{total} ({progress:.0%})"
    return f"[{bar}] {current}/{total} ({progress:.0%})"


def format_risk_badge(risk_level: str) -> str:
    """Format risk level as terminal-style badge."""
    colors = {
        "low": "green",
        "medium": "yellow",
        "high": "red",
        "critical": "bold red",
        "unknown": "dim",
    }
    color = colors.get(risk_level, "white")
    return f"[{color}]■[/{color}] {risk_level.upper()}"


def format_status_badge(status: str) -> str:
    """Format status as terminal-style badge."""
    colors = {
        "pending": "dim",
        "running": "cyan",
        "completed": "green",
        "failed": "red",
    }
    symbols = {
        "pending": "○",
        "running": "◉",
        "completed": "●",
        "failed": "✕",
    }
    color = colors.get(status, "white")
    symbol = symbols.get(status, "?")
    return f"[{color}]{symbol}[/{color}] {status.upper()}"
