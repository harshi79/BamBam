"""
YoriNetflix — Text transformation utilities.

Small-caps Unicode transformer, HTML-aware variant, and HTML escaping.
Preserves protected tokens (URLs, HTML tags, entities, IDs) during
transformation.

These are pure functions with no side effects and no external dependencies.
"""

from __future__ import annotations

import html
import re

# ── Small-caps mapping ─────────────────────────────────────────

_SMALL_CAPS_MAP: dict[str, str] = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
    "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
    "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
    "s": "ꜱ", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
}

# Protected token patterns — anything matched here is left untouched.
# Order matters: more specific patterns first, most generic last.
_PROTECTED_TOKENS = re.compile(
    r"("
    r"https?://\S+"          # full URLs
    r"|t\.me/\S+"            # telegram links
    r"|<[^>]+>"              # HTML tags
    r"|&#\d+;"               # numeric HTML entities
    r"|&[a-zA-Z]+;"          # named HTML entities (&amp; &lt; &gt; etc.)
    r"|NetflixId=\S+"        # Netflix ID key-value
    r"|SecureNetflixId=\S+"  # SecureNetflixId key-value
    r"|cookie_hash=\S+"      # cookie hash key-value
    r"|\d{4,}"               # long numeric runs (IDs, timestamps)
    r")"
)


def sc(text: str) -> str:
    """Convert lowercase letters to Unicode small caps, leaving protected
    tokens (URLs, HTML tags, entities, IDs) untouched.

    Args:
        text: Input string to transform.

    Returns:
        Transformed string with small-caps letters.
    """
    if not text:
        return ""

    parts: list[str] = []
    last = 0
    for m in _PROTECTED_TOKENS.finditer(text):
        parts.append(text[last:m.start()])   # even index: transformable text
        parts.append(m.group(0))             # odd index: protected token
        last = m.end()
    parts.append(text[last:])                # trailing text

    out: list[str] = []
    for idx, chunk in enumerate(parts):
        if idx % 2 == 1:
            out.append(chunk)  # protected — leave as-is
        else:
            out.append("".join(_SMALL_CAPS_MAP.get(c, c) for c in chunk))
    return "".join(out)


def sc_html(text: str) -> str:
    """Small-caps transform that skips HTML tags and protected tokens.

    Splits on HTML tags first, then applies small-caps to non-tag pieces.

    Args:
        text: Input string that may contain HTML tags.

    Returns:
        Transformed string with HTML tags preserved.
    """
    if not text:
        return ""
    pieces = re.split(r"(<[^>]+>)", text)
    out: list[str] = []
    for piece in pieces:
        if piece.startswith("<") and piece.endswith(">"):
            out.append(piece)
        else:
            out.append(sc(piece))
    return "".join(out)


def esc(text: str | None) -> str:
    """HTML-escape a string for safe embedding in Telegram HTML messages.

    Args:
        text: Input string (may be None).

    Returns:
        HTML-escaped string. None becomes empty string.
    """
    return html.escape(text or "", quote=False)