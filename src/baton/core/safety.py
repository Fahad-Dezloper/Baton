"""Text that came from one session and will be shown to another: redact, flatten, bound."""

from __future__ import annotations

import re

_SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)\b([A-Za-z0-9_]*(?:secret|token|passw(?:or)?d|api[_-]?key|private[_-]?key)[A-Za-z0-9_]*)\s*[:=]\s*\S+"),
]


def redact(text: str) -> str:
    out = str(text)
    for i, pat in enumerate(_SECRETS):
        out = pat.sub(lambda m: (m.group(1) + "=[redacted]") if i == len(_SECRETS) - 1 else "[redacted]", out)
    return out


def scrub(text: object, limit: int = 0) -> str:
    """Redact secrets, collapse whitespace (no forged lines), neutralise our own marker, clip."""
    out = " ".join(redact(str(text)).split())
    out = out.replace("[baton]", "(baton)")
    if limit and len(out) > limit:
        out = out[: limit - 3] + "..."
    return out
