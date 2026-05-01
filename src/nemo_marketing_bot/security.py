"""Security helpers: URL validation, content guardrails, prompt-injection isolation.

These functions are the single defensive layer between untrusted inputs (RSS
feeds, LLM output, user-supplied URLs in `schedule.yaml`) and the publishers.
Keep them small and dependency-free so they can be unit-tested without network.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL validation (SSRF defence)
# ---------------------------------------------------------------------------

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

# Hostnames that are inherently dangerous (cloud metadata, loopback aliases).
HOST_DENYLIST = frozenset(
    {
        "localhost",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "metadata",
    }
)


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF / scheme validation."""


def assert_safe_url(url: str, *, label: str = "url") -> str:
    """Validate that `url` is an external http(s) URL we can fetch safely.

    Rejects: non-http schemes, missing host, private/loopback/link-local IPs,
    cloud metadata hosts, and bare IPs in the denied ranges.

    NOTE: This does best-effort DNS resolution to catch hostnames pointing at
    private space. It cannot defend against DNS rebinding — for that, the
    fetch layer should re-resolve and pin the IP. For our use case (RSS polls
    every N minutes against well-known hosts) this is sufficient.
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError(f"{label}: empty URL")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise UnsafeURLError(f"{label}: scheme '{parsed.scheme}' not allowed (use http/https)")
    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeURLError(f"{label}: missing host")
    if host in HOST_DENYLIST:
        raise UnsafeURLError(f"{label}: host '{host}' is denied")

    # If the host is a literal IP, validate directly.
    try:
        ip = ipaddress.ip_address(host)
        _assert_public_ip(ip, label=label, host=host)
        return url

    except ValueError:
        pass  # not an IP literal — resolve below

    # Resolve and check every returned address.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as err:
        raise UnsafeURLError(f"{label}: DNS resolution failed for '{host}': {err}") from err
    seen: set[str] = set()
    for family, _type, _proto, _canon, sockaddr in infos:
        addr = sockaddr[0]
        if addr in seen:
            continue
        seen.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        _assert_public_ip(ip, label=label, host=host)
    return url


def _assert_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, label: str, host: str) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise UnsafeURLError(f"{label}: host '{host}' resolves to non-public address {ip}")


# ---------------------------------------------------------------------------
# Image URL allowlist (Instagram publisher)
# ---------------------------------------------------------------------------


def is_allowed_image_host(url: str, allowed_hosts: frozenset[str]) -> bool:
    """True if `url` is an https URL whose host is in the allowlist.

    Accepts exact host match OR subdomain match (e.g. allowing "example.com"
    permits "cdn.example.com"). Empty allowlist => always False.
    """
    if not allowed_hosts or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme.lower() != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    for allowed in allowed_hosts:
        a = allowed.lower().strip()
        if not a:
            continue
        if host == a or host.endswith("." + a):
            return True
    return False


# ---------------------------------------------------------------------------
# Prompt-injection isolation for untrusted text
# ---------------------------------------------------------------------------

# Strip common prompt-injection markers / instruction phrases. We do NOT try to
# scrub semantically — the real defence is wrapping in <UNTRUSTED> tags and
# instructing the system prompt to ignore meta-instructions inside them. This
# is just a courtesy clean to reduce noise.
_INJECTION_PATTERNS = (
    re.compile(r"(?i)\bignore\s+(all\s+)?(previous|above|prior)\s+instructions\b"),
    re.compile(r"(?i)\bsystem\s*:\s*"),
    re.compile(r"(?i)\bdisregard\s+(the\s+)?(above|prior|previous)\b"),
    re.compile(r"<\|.*?\|>"),  # chat template markers
)


def sanitize_untrusted_text(text: str, *, max_chars: int = 2000) -> str:
    """Return a length-capped, lightly-cleaned copy of untrusted text.

    Use this on RSS summaries, article bodies, and any string that came from
    outside our codebase before embedding it in an LLM prompt.
    """
    if not text:
        return ""
    cleaned = text
    for pat in _INJECTION_PATTERNS:
        cleaned = pat.sub("[redacted]", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "…"
    return cleaned


def wrap_untrusted(text: str, tag: str = "UNTRUSTED_INPUT") -> str:
    """Wrap text in tags so the LLM can be told to treat it as data, not instructions."""
    safe = sanitize_untrusted_text(text)
    # Prevent the tag itself from being smuggled inside the payload.
    safe = safe.replace(f"</{tag}>", f"</ {tag}>").replace(f"<{tag}>", f"< {tag}>")
    return f"<{tag}>\n{safe}\n</{tag}>"


# ---------------------------------------------------------------------------
# Pre-publish content safety check
# ---------------------------------------------------------------------------


@dataclass
class SafetyReport:
    ok: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.issues.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


# Words that almost always indicate a low-quality / non-compliant marketing post
# for a brand that wants to avoid hype and unverifiable claims.
DEFAULT_FORBIDDEN_PHRASES = frozenset(
    {
        "guaranteed",
        "guarantee results",
        "100% safe",
        "risk-free",
        "best in the world",
        "click here now",
        "limited time only",
        "act now",
    }
)

# Text patterns that indicate repost/quote-post behavior. We hard-fail these
# because managed accounts must publish only original posts.
REPOST_MARKER_PATTERNS = (
    re.compile(r"(?im)^\s*rt\s+@\w+"),
    re.compile(r"(?im)^\s*repost\s*[:\-]"),
    re.compile(r"(?im)^\s*quote\s*(post|tweet)?\s*[:\-]"),
    re.compile(r"(?im)^\s*qt\s*[:\-]"),
)


def check_post_safety(
    text: str,
    *,
    platform: str,
    image_url: str | None = None,
    image_allowlist: frozenset[str] = frozenset(),
    forbidden_phrases: frozenset[str] = DEFAULT_FORBIDDEN_PHRASES,
    max_chars: dict[str, int] | None = None,
) -> SafetyReport:
    """Run pre-publish guardrails. Returns a SafetyReport with ok=True/False."""
    report = SafetyReport(ok=True)
    limits = max_chars or {"x": 280, "bluesky": 300, "linkedin": 3000, "instagram": 2200}

    # 1) Length
    cap = limits.get(platform)
    if cap and len(text) > cap:
        report.fail(f"text exceeds {platform} limit of {cap} chars (got {len(text)})")

    # 2) Forbidden phrases
    lower = text.lower()
    for phrase in forbidden_phrases:
        if phrase in lower:
            report.fail(f"contains forbidden phrase: {phrase!r}")

    # 3) Suspicious patterns
    if re.search(r"<script\b", text, re.IGNORECASE):
        report.fail("contains <script> tag")
    for marker in REPOST_MARKER_PATTERNS:
        if marker.search(text):
            report.fail("repost/quote-post markers are not allowed")
            break
    if text.count("http://") + text.count("https://") > 3:
        report.warn("more than 3 URLs in a single post")

    # 4) Instagram image URL must be in the allowlist
    if platform == "instagram":
        if not image_url:
            report.fail("instagram requires image_url")
        elif not is_allowed_image_host(image_url, image_allowlist):
            report.fail(
                f"instagram image_url host not in allowlist: {urlparse(image_url).hostname}"
            )

    return report
