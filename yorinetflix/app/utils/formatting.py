"""
YoriNetflix — Message formatting builders.

Preserves the original bot's display style while using PostgreSQL timestamps.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.text import sc, sc_html, esc

DEFAULT_TV_URL = "https://www.netflix.com/tv2"
DEFAULT_PC_URL = "https://www.netflix.com/account"
DEFAULT_MOBILE_URL = "https://www.netflix.com/login"


def build_welcome_text() -> str:
    return sc_html(
        "🎬 <b>YoriNetflix</b>\n\n"
        "Get premium accounts — free, instant, no strings.\n"
        "Made by <a href=\"https://t.me/Yorichiiprime\">@Yorichiiprime</a>\n\n"
        "<i>Tap a button below to begin.</i>"
    )


def build_profile_text(
    full_name: str,
    user_id: int,
    joined_at: datetime | None,
    total_generated: int,
    unique_countries: int,
    last_gen_time: datetime | None,
    cooldown_seconds: int,
    points: int,
    daily_remaining: int,
    daily_limit: int,
) -> str:
    now = datetime.now(timezone.utc)
    joined_str = joined_at.strftime("%Y-%m-%d") if joined_at else "unknown"

    if last_gen_time:
        elapsed = (now - last_gen_time).total_seconds()
        remaining = max(0, int(cooldown_seconds - elapsed))
    else:
        remaining = 0
    cd_text = sc(f"{remaining}s") if remaining else sc("ready ✅")

    daily_text = f"{daily_remaining}/{daily_limit}" if daily_limit > 0 else "unlimited"

    return sc_html(
        f"📊 <b>your profile</b>\n\n"
        f"👤 <b>name:</b> {esc(full_name)}\n"
        f"🆔 <b>id:</b> <code>{user_id}</code>\n"
        f"📅 <b>joined:</b> {joined_str}\n\n"
        f"🍿 <b>total generated:</b> {total_generated}\n"
        f"🌍 <b>unique countries:</b> {unique_countries}\n"
        f"⏳ <b>cooldown:</b> {cd_text}\n"
        f"📊 <b>today:</b> {daily_text}\n"
        f"💰 <b>points:</b> {points}"
    )


def build_account_message(
    country: str,
    raw_text: str,
    netflix_id: str,
    secure_id: str,
    remaining: int,
) -> str:
    info = clean_info_block(raw_text)
    cookie_str = build_cookie_string(netflix_id, secure_id)

    parts = [
        sc_html(f"🎬 <b>{esc(country)} — Netflix Account</b>"),
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if info:
        parts.append(f"<blockquote>{esc(info)}</blockquote>")
        parts.append("")

    if cookie_str:
        parts.append(sc_html("🍪 <b>Cookie</b> <i>(tap below to copy)</i>"))
        parts.append(f"<blockquote><code>{esc(cookie_str)}</code></blockquote>")
        parts.append("")

    parts.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        sc_html(f"📦 remaining for {esc(country)}: <b>{remaining}</b>"),
        sc_html("💡 tap a button below to open the login page."),
        sc_html("📌 <i>save this message — you can reuse it anytime.</i>"),
    ])
    return "\n".join(parts)


def clean_info_block(raw_text: str) -> str:
    import re
    URL_LINE_RE = re.compile(r"^\s*[•\-]?\s*(PC|Phone|TV)\s*Login URL\s*:", re.I)
    COOKIE_LINE_RE = re.compile(r"^\s*🍪\s*Cookie\s*:", re.I)
    SECURE_LINE_RE = re.compile(r"^\s*🔐\s*SecureNetflixId\s*:", re.I)
    SEP_LINE_RE = re.compile(r"^\s*[─━\-=]{3,}\s*$")

    kept = []
    for line in raw_text.split("\n"):
        s = line.strip()
        if URL_LINE_RE.match(s):
            continue
        if COOKIE_LINE_RE.match(s):
            continue
        if SECURE_LINE_RE.match(s):
            continue
        if SEP_LINE_RE.match(s):
            continue
        kept.append(line)
    out = "\n".join(kept).strip()
    return re.sub(r"\n{3,}", "\n\n", out)


def build_cookie_string(netflix_id: str, secure_id: str) -> str:
    parts = []
    if netflix_id and netflix_id.upper() != "N/A":
        parts.append(f"NetflixId={netflix_id}")
    if secure_id and secure_id.upper() != "N/A":
        parts.append(f"SecureNetflixId={secure_id}")
    return "\n".join(parts)


def normalize_url(url: str, fallback: str) -> str:
    url = (url or "").strip()
    if not url or url.upper() == "N/A":
        return fallback
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def build_daily_reward_text(points: int, balance: int, next_claim_hours: int) -> str:
    return sc_html(
        f"🎁 <b>daily reward claimed!</b>\n\n"
        f"💰 earned: <b>+{points} points</b>\n"
        f"📊 balance: <b>{balance} points</b>\n\n"
        f"⏰ next claim in ~<b>{next_claim_hours}h</b>"
    )


def build_daily_already_claimed(hours_remaining: int) -> str:
    return sc_html(
        f"⏳ <b>already claimed today!</b>\n\n"
        f"come back in ~<b>{hours_remaining}h</b>."
    )