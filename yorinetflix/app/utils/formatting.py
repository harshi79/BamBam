"""
YoriNetflix — Message formatting builders.

Polished, consistent presentation for all user-facing messages.
Uses Telegram HTML formatting: bold, blockquote, inline code, italic.
Preserves small-caps branding for section headings.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.text import sc, sc_html, esc

DEFAULT_TV_URL = "https://www.netflix.com/tv2"
DEFAULT_PC_URL = "https://www.netflix.com/account"
DEFAULT_MOBILE_URL = "https://www.netflix.com/login"


# ── Welcome ────────────────────────────────────────────────────


def build_welcome_text() -> str:
    return (
        f"<blockquote>{sc_html('welcome to yorinetflix')}</blockquote>\n\n"
        f"{sc_html('get premium accounts')} · free, instant, no strings.\n\n"
        f"<i>tap a button below to begin.</i>"
    )


# ── Profile ────────────────────────────────────────────────────


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
    joined_str = joined_at.strftime("%Y-%m-%d") if joined_at else "—"

    if last_gen_time:
        elapsed = (now - last_gen_time).total_seconds()
        remaining = max(0, int(cooldown_seconds - elapsed))
    else:
        remaining = 0
    cd_text = f"{remaining}s" if remaining else "ready ✅"

    daily_text = f"{daily_remaining}/{daily_limit}" if daily_limit > 0 else "∞"

    return (
        f"{sc_html('your profile')}\n\n"
        f"👤 <b>{esc(full_name)}</b>\n"
        f"🆔 <code>{user_id}</code>  ·  📅 <i>{joined_str}</i>\n\n"
        f"━━━━━━━━━━━━\n\n"
        f"🍿 Generated  <b>{total_generated}</b>\n"
        f"🌍 Countries  <b>{unique_countries}</b>\n"
        f"⏳ Cooldown  <b>{cd_text}</b>\n"
        f"📊 Today  <b>{daily_text}</b>\n"
        f"💰 Points  <b>{points}</b>"
    )


# ── Account Delivery ───────────────────────────────────────────


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
        f"🎬 <b>{esc(country)}</b>",
        "",
    ]
    if info:
        parts.append(f"<blockquote>{esc(info)}</blockquote>")

    if cookie_str:
        parts.append("")
        parts.append(f"🍪 <b>Cookie</b>  <i>(tap to copy)</i>")
        parts.append(f"<blockquote><code>{esc(cookie_str)}</code></blockquote>")

    parts.extend([
        "",
        f"📦 <b>{remaining}</b> remaining for {esc(country)}",
        f"<blockquote>tap a button below to open the login page.</blockquote>",
    ])
    return "\n".join(parts)


# ── Daily Reward ───────────────────────────────────────────────


def build_daily_reward_text(points: int, balance: int, next_claim_hours: int) -> str:
    return (
        f"🎁 <b>Daily Reward</b>\n\n"
        f"💰 earned  <b>+{points}</b> points\n"
        f"📊 balance  <b>{balance}</b> points\n\n"
        f"<blockquote>next claim in ~{next_claim_hours}h</blockquote>"
    )


def build_daily_already_claimed(hours_remaining: int) -> str:
    return (
        f"⏳ <b>Already Claimed</b>\n\n"
        f"<blockquote>you've already claimed today's reward.\n"
        f"come back in ~{hours_remaining}h.</blockquote>"
    )


# ── Referral ───────────────────────────────────────────────────


def build_referral_text(
    link: str,
    referral_count: int,
    balance: int,
    reward_points: int,
) -> str:
    return (
        f"🔗 <b>Referral</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"👥 referrals  <b>{referral_count}</b>\n"
        f"💰 points  <b>{balance}</b>\n\n"
        f"<blockquote>share your link — earn <b>{reward_points} pts</b> "
        f"for each new user.</blockquote>"
    )


# ── History ────────────────────────────────────────────────────


def build_history_empty() -> str:
    return (
        f"🕘 <b>History</b>\n\n"
        f"<blockquote>no generations yet.\n"
        f"generate an account to see it here.</blockquote>"
    )


def build_history_page(
    entries: list[dict],
    page: int,
    total_pages: int,
    total: int,
) -> str:
    lines = [f"🕘 <b>History</b>\n"]
    for e in entries:
        lines.append(f"• <b>{esc(e['country'])}</b>  <i>{e['when']}</i>")
    lines.append(f"\n📄 page <b>{page}</b>/<b>{total_pages}</b>  ·  total <b>{total}</b>")
    return "\n".join(lines)


# ── Leaderboard ────────────────────────────────────────────────


def build_leaderboard(entries: list[dict]) -> str:
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = [f"🏆 <b>Top Generators</b>\n"]
    for i, e in enumerate(entries):
        lines.append(f"{medals[i]}  <b>{esc(e['name'])}</b>  —  {e['total']}")
    return "\n".join(lines)


def build_leaderboard_empty() -> str:
    return (
        f"🏆 <b>Top Generators</b>\n\n"
        f"<blockquote>no generations yet.</blockquote>"
    )


# ── Country Selection ──────────────────────────────────────────


def build_country_list_text(total: int, num_countries: int) -> str:
    return (
        f"🌍 <b>Select a Country</b>\n\n"
        f"📦 total in stock: <b>{total}</b>\n"
        f"🗂 countries: <b>{num_countries}</b>"
    )


def build_country_empty() -> str:
    return (
        f"❌ <b>Out of Stock</b>\n\n"
        f"<blockquote>no inventory available right now.\ncheck back later.</blockquote>"
    )


# ── FSUB ───────────────────────────────────────────────────────


def build_fsub_prompt() -> str:
    return (
        f"🚪 <b>Channel Required</b>\n\n"
        f"<blockquote>to use this bot, please join our channel first.</blockquote>"
    )


# ── Admin Messages ─────────────────────────────────────────────


def build_admin_help() -> str:
    return (
        f"🛠 <b>Admin Commands</b>\n\n"
        f"📋 <b>Inventory</b>\n"
        f"  /add — add inventory (.txt or text)\n"
        f"  /stock — stock breakdown\n"
        f"  /export [category] — export to file\n"
        f"  /clear_country — wipe one category\n"
        f"  /wipe CONFIRM — delete all inventory\n\n"
        f"📊 <b>Analytics</b>\n"
        f"  /stats — bot statistics\n\n"
        f"👥 <b>Users</b>\n"
        f"  /givepoints — adjust user points\n"
        f"  /ban — ban a user\n"
        f"  /unban — unban a user\n\n"
        f"📢 <b>Communication</b>\n"
        f"  /broadcast — message all users\n\n"
        f"ℹ️  /admin — this menu"
    )


def build_admin_stats(
    total_stock: int,
    total_countries: int,
    total_users: int,
    active_24h: int,
    total_gens: int,
    gens_24h: int,
    gens_7d: int,
    top_stock: list[dict],
) -> str:
    top_lines = "\n".join(
        f"  • {esc(r['country'])} — {r['count']}" for r in top_stock
    ) or "  —"

    return (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"🍿 <b>Stock</b>\n"
        f"  • accounts: <b>{total_stock}</b>\n"
        f"  • countries: <b>{total_countries}</b>\n\n"
        f"👥 <b>Users</b>\n"
        f"  • total: <b>{total_users}</b>\n"
        f"  • active (24h): <b>{active_24h}</b>\n\n"
        f"🎁 <b>Generations</b>\n"
        f"  • all time: <b>{total_gens}</b>\n"
        f"  • last 24h: <b>{gens_24h}</b>\n"
        f"  • last 7d: <b>{gens_7d}</b>\n\n"
        f"<b>Top Stock</b>\n{top_lines}"
    )


def build_stock_breakdown(entries: list[dict], total: int) -> str:
    lines = [f"📦 <b>Stock Breakdown</b>\n"]
    for r in entries:
        lines.append(f"• {esc(r['country'])} — <b>{r['count']}</b>")
    lines.append(f"\n<b>Total:</b> {total}")
    return "\n".join(lines)


def build_add_result(added: int, dupes: int) -> str:
    return (
        f"✅ added <b>{added}</b> item(s).\n"
        f"♻️ skipped <b>{dupes}</b> duplicate(s)."
    )


def build_givepoints_result(target_id: int, amount: int, new_balance: int) -> str:
    return (
        f"✅ adjusted <code>{target_id}</code> by <b>{amount:+d}</b> points.\n"
        f"💰 new balance: <b>{new_balance}</b>"
    )


def build_broadcast_progress(sent: int, failed: int, blocked: int) -> str:
    return (
        f"📤 <b>Broadcasting…</b>\n\n"
        f"✅ {sent}  ·  ❌ {failed}  ·  🚫 {blocked}"
    )


def build_broadcast_complete(sent: int, failed: int, blocked: int) -> str:
    return (
        f"✅ <b>Broadcast Complete</b>\n\n"
        f"📬 sent: <b>{sent}</b>\n"
        f"❌ failed: <b>{failed}</b>\n"
        f"🚫 blocked: <b>{blocked}</b>"
    )


# ── Shared Utilities ───────────────────────────────────────────


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
