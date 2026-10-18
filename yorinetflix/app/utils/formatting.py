"""
YoriNetflix — message formatting builders.

A refined, text-first identity for Telegram: small-caps section headings,
quiet geometric accents, generous spacing, and Telegram-supported HTML only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.utils.text import esc, sc, sc_html

# Sign-in destinations.  These are the plain, public Netflix pages: they carry
# no credentials, so whoever opens them signs in as themselves.  There is no TV
# destination — TV sign-in is an activation-code flow driven by the television,
# and no auto-login token is ever generated, stored, or embedded here.
DEFAULT_PC_URL = "https://www.netflix.com/account"
DEFAULT_MOBILE_URL = "https://www.netflix.com/login"

# Query parameters that carry credentials.  Netflix's auto-login token
# (``nftoken``) and friends sign whoever opens the link straight into an
# account, with no password prompt.  A button URL is shared, cached and logged
# by Telegram, so such a parameter must never survive into a button.
CREDENTIAL_QUERY_PARAMS = frozenset({
    "nftoken",
    "nf_token",
    "token",
    "authtoken",
    "auth_token",
    "access_token",
    "accesstoken",
    "idtoken",
    "id_token",
    "session",
    "sessionid",
    "session_id",
    "sid",
    "password",
    "pass",
    "pwd",
    "netflixid",
    "securenetflixid",
})

_RULE = "┄┄┄┄┄┄┄┄┄┄┄"


def _heading(title: str) -> str:
    """Render a consistent small-caps screen title."""
    return f"<b>◇ {sc_html(title)}</b>"


def _section(title: str) -> str:
    """Render a small-caps section label."""
    return f"<b>{sc_html(title)}</b>"


# ── Welcome ────────────────────────────────────────────────────


def build_welcome_text() -> str:
    return (
        f"<b>✦ {sc_html('yorinetflix')}</b>\n"
        f"<blockquote>{sc_html('welcome to the premium account desk')}</blockquote>\n\n"
        f"{sc_html('premium accounts · free · instant · no strings')}\n\n"
        f"<i>Choose a destination below to begin.</i>"
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
    cd_text = f"{remaining}s" if remaining else sc("ready")

    daily_text = f"{daily_remaining}/{daily_limit}" if daily_limit > 0 else "∞"

    return (
        f"{_heading('Your profile')}\n\n"
        f"<blockquote><b>{esc(full_name)}</b>\n"
        f"<code>{user_id}</code>  ·  {sc_html('member since')} "
        f"<i>{joined_str}</i></blockquote>\n\n"
        f"{_RULE}\n"
        f"{_section('Account overview')}\n"
        f"·  {sc_html('Generated')}  <b>{total_generated}</b>\n"
        f"·  {sc_html('Countries')}  <b>{unique_countries}</b>\n"
        f"·  {sc_html('Cooldown')}  <b>{cd_text}</b>\n"
        f"·  {sc_html('Today')}  <b>{daily_text}</b>\n"
        f"·  {sc_html('Points')}  <b>{points}</b>"
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
        f"<b>◇ {esc(country)}</b>  ·  {sc_html('Netflix access')}",
        _RULE,
    ]
    if info:
        parts.extend(["", f"<blockquote>{esc(info)}</blockquote>"])

    if cookie_str:
        parts.extend([
            "",
            f"{_section('Cookie')}  <i>{sc_html('tap to copy')}</i>",
            f"<blockquote><code>{esc(cookie_str)}</code></blockquote>",
        ])

    parts.extend([
        "",
        _RULE,
        f"<b>{remaining}</b> {sc_html('remaining')}  ·  {esc(country)}",
        f"<i>{sc_html('Use a route below to open sign-in.')}</i>",
    ])
    return "\n".join(parts)


# ── Daily Reward ───────────────────────────────────────────────


def build_daily_reward_text(points: int, balance: int, next_claim_hours: int) -> str:
    return (
        f"{_heading('Daily reward')}\n\n"
        f"<blockquote>+<b>{points}</b> {sc_html('points credited')}</blockquote>\n\n"
        f"{_section('New balance')}  <code>{balance}</code> {sc_html('points')}\n"
        f"{_RULE}\n"
        f"<i>Next claim in approximately {next_claim_hours} hours.</i>"
    )


def build_daily_already_claimed(hours_remaining: int) -> str:
    return (
        f"{_heading('Already claimed')}\n\n"
        f"<blockquote>You have already claimed today's reward.\n"
        f"Come back in approximately {hours_remaining} hours.</blockquote>"
    )


# ── Referral ───────────────────────────────────────────────────


def build_referral_text(
    link: str,
    referral_count: int,
    balance: int,
    reward_points: int,
) -> str:
    return (
        f"{_heading('Your referral link')}\n\n"
        f"<blockquote><code>{esc(link)}</code></blockquote>\n\n"
        f"{_RULE}\n"
        f"{sc_html('Successful referrals')}  <b>{referral_count}</b>\n"
        f"{sc_html('Points balance')}  <b>{balance}</b>\n\n"
        f"<i>Share your link and earn <b>{reward_points} pts</b> "
        f"for each new user.</i>"
    )


# ── History ────────────────────────────────────────────────────


def build_history_empty() -> str:
    return (
        f"{_heading('Generation history')}\n\n"
        f"<blockquote>No generations yet.\nYour first account will appear here.</blockquote>"
    )


def build_history_page(
    entries: list[dict],
    page: int,
    total_pages: int,
    total: int,
) -> str:
    first_index = (page - 1) * 10 + 1
    lines = [
        _heading('Generation history'),
        f"<i>{sc_html('Most recent first')}</i>",
        "",
    ]
    for index, entry in enumerate(entries, start=first_index):
        lines.append(
            f"<code>{index:02d}</code>  <b>{esc(entry['country'])}</b>"
            f"  ·  <i>{esc(entry['when'])}</i>"
        )
    lines.extend([
        "",
        _RULE,
        f"<code>{page:02d} / {total_pages:02d}</code>  ·  "
        f"{sc_html('Entries')}  <b>{total}</b>",
    ])
    return "\n".join(lines)


# ── Leaderboard ────────────────────────────────────────────────


def build_leaderboard(entries: list[dict]) -> str:
    lines = [
        _heading('Top generators'),
        f"<i>{sc_html('All-time ranking')}</i>",
        "",
    ]
    for rank, entry in enumerate(entries, start=1):
        lines.append(
            f"<code>{rank:02d}</code>  <b>{esc(entry['name'])}</b>"
            f"  ·  <b>{entry['total']}</b> {sc_html('generations')}"
        )
    return "\n".join(lines)


def build_leaderboard_empty() -> str:
    return (
        f"{_heading('Top generators')}\n\n"
        f"<blockquote>No generations have been recorded yet.</blockquote>"
    )


# ── Country Selection ──────────────────────────────────────────


def build_country_list_text(total: int, num_countries: int) -> str:
    return (
        f"{_heading('Select a country')}\n\n"
        f"<blockquote>Choose a country to browse available stock.</blockquote>\n\n"
        f"<code>{total}</code> {sc_html('accounts in stock')}  ·  "
        f"<code>{num_countries}</code> {sc_html('countries')}"
    )


def build_country_empty() -> str:
    return (
        f"{_heading('Inventory unavailable')}\n\n"
        f"<blockquote>There are no accounts available at the moment.\n"
        f"Please check back later.</blockquote>"
    )


# ── Force Subscription ─────────────────────────────────────────


def build_fsub_prompt() -> str:
    return (
        f"{_heading('Channel access required')}\n\n"
        f"<blockquote>Join our channel to use the account desk, then verify below.</blockquote>"
    )


# ── Admin Messages ─────────────────────────────────────────────


def build_admin_only() -> str:
    return (
        f"{_heading('Admin access only')}\n"
        f"This control is reserved for administrators."
    )


def build_admin_help() -> str:
    return (
        f"{_heading('Admin console')}\n"
        f"<i>{sc_html('Operations · authorized access')}</i>\n\n"
        f"{_section('Inventory')}\n"
        f"<code>/add</code>  Add inventory (.txt or text)\n"
        f"<code>/stock</code>  View the stock breakdown\n"
        f"<code>/export [category]</code>  Export inventory\n"
        f"<code>/clear_country</code>  Remove one category\n"
        f"<code>/wipe CONFIRM</code>  Delete all inventory\n\n"
        f"{_section('Analytics')}\n"
        f"<code>/stats</code>  View bot statistics\n\n"
        f"{_section('Users')}\n"
        f"<code>/givepoints</code>  Adjust a points balance\n"
        f"<code>/ban</code> · <code>/unban</code>  Manage access\n\n"
        f"{_section('Communication')}\n"
        f"<code>/broadcast</code>  Message all users\n\n"
        f"<i><code>/admin</code> opens this console.</i>"
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
        f"·  {esc(row['country'])}  <b>{row['count']}</b>" for row in top_stock
    ) or "·  —"

    return (
        f"{_heading('Bot overview')}\n\n"
        f"{_section('Inventory')}\n"
        f"·  {sc_html('Accounts')}  <b>{total_stock}</b>\n"
        f"·  {sc_html('Countries')}  <b>{total_countries}</b>\n\n"
        f"{_RULE}\n"
        f"{_section('Community')}\n"
        f"·  {sc_html('Users')}  <b>{total_users}</b>\n"
        f"·  {sc_html('Active · 24h')}  <b>{active_24h}</b>\n\n"
        f"{_RULE}\n"
        f"{_section('Generations')}\n"
        f"·  {sc_html('All time')}  <b>{total_gens}</b>\n"
        f"·  {sc_html('Last 24h')}  <b>{gens_24h}</b>\n"
        f"·  {sc_html('Last 7d')}  <b>{gens_7d}</b>\n\n"
        f"{_section('Top stock')}\n{top_lines}"
    )


def build_stock_breakdown(entries: list[dict], total: int) -> str:
    lines = [
        _heading('Stock overview'),
        f"<i>{len(entries)} {sc_html('countries')}  ·  {total} {sc_html('accounts')}</i>",
        _RULE,
    ]
    for row in entries:
        lines.append(f"{esc(row['country'])}  ·  <b>{row['count']}</b>")
    lines.extend([_RULE, f"{_section('Total')}  <b>{total}</b>"])
    return "\n".join(lines)


def build_add_result(added: int, dupes: int) -> str:
    return (
        f"{_heading('Inventory updated')}\n\n"
        f"{sc_html('Added')}  <b>{added}</b> {sc_html('items')}\n"
        f"{sc_html('Duplicates skipped')}  <b>{dupes}</b>"
    )


def build_givepoints_result(target_id: int, amount: int, new_balance: int) -> str:
    return (
        f"{_heading('Points adjusted')}\n\n"
        f"<code>{target_id}</code>  ·  {amount:+d} {sc_html('points')}\n"
        f"{_section('New balance')}  <b>{new_balance}</b>"
    )


def build_broadcast_progress(sent: int, failed: int, blocked: int) -> str:
    return (
        f"{_heading('Broadcast in progress')}\n\n"
        f"{sc_html('Sent')}  <b>{sent}</b>  ·  "
        f"{sc_html('Failed')}  <b>{failed}</b>  ·  "
        f"{sc_html('Blocked')}  <b>{blocked}</b>"
    )


def build_broadcast_complete(sent: int, failed: int, blocked: int) -> str:
    return (
        f"{_heading('Broadcast complete')}\n\n"
        f"{sc_html('Delivered')}  <b>{sent}</b>\n"
        f"{sc_html('Failed')}  <b>{failed}</b>\n"
        f"{sc_html('Blocked')}  <b>{blocked}</b>"
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


def strip_credential_params(url: str) -> str:
    """Remove credential-bearing query parameters from a URL.

    Netflix auto-login tokens (``nftoken``) and similar session parameters are
    dropped, along with any fragment that accompanied them.  Harmless
    parameters and the path are left untouched, so ordinary sign-in and
    activation links pass through unchanged.
    """
    if "?" not in url:
        return url

    base, _, rest = url.partition("?")
    query, _, fragment = rest.partition("#")

    kept = []
    dropped = False
    for pair in query.split("&"):
        if not pair:
            continue
        name = pair.split("=", 1)[0].strip().lower()
        if name in CREDENTIAL_QUERY_PARAMS:
            dropped = True
            continue
        kept.append(pair)

    cleaned = base + ("?" + "&".join(kept) if kept else "")
    if fragment and not dropped:
        cleaned += "#" + fragment
    return cleaned


def normalize_url(url: str, fallback: str) -> str:
    """Return a button-safe sign-in URL.

    Uses ``fallback`` when the inventory carried no usable URL, adds the scheme
    when it is missing, and strips credential-bearing query parameters so a
    button can never hand out a pre-authenticated session.  When stripping
    leaves nothing but a bare host, the official fallback page is used instead.
    """
    url = (url or "").strip()
    if not url or url.upper() == "N/A":
        return strip_credential_params(fallback)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    cleaned = strip_credential_params(url)
    if cleaned != url and urlsplit(cleaned).path in ("", "/"):
        # The URL was only a credential carrier — send the person to the
        # official page for that route instead of a bare domain root.
        return strip_credential_params(fallback)
    return cleaned
