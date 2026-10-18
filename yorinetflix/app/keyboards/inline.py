"""
YoriNetflix — inline keyboard builders.

Compact, typographic navigation with stable callback payloads.
"""

from __future__ import annotations

from math import ceil

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.inventory import country_key
from app.utils.formatting import DEFAULT_MOBILE_URL, DEFAULT_PC_URL, normalize_url


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✦ Gᴇɴᴇʀᴀᴛᴇ", callback_data="gen:0")],
        [
            InlineKeyboardButton(text="◷ Dᴀɪʟʏ", callback_data="daily"),
            InlineKeyboardButton(text="◉ Pʀᴏꜰɪʟᴇ", callback_data="profile"),
        ],
        [
            InlineKeyboardButton(text="≡ Hɪꜱᴛᴏʀʏ", callback_data="history:1"),
            InlineKeyboardButton(text="↗ Rᴇꜰᴇʀʀᴀʟ", callback_data="referral"),
        ],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Menu", callback_data="menu")]
    ])


def join_kb(force_channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↗ Join Channel", url=force_channel_url)],
        [InlineKeyboardButton(text="✓ Joined · Verify", callback_data="check_join")],
    ])


def country_list_kb(
    countries: list[dict],
    page: int,
    page_size: int,
) -> InlineKeyboardMarkup:
    total = len(countries)
    total_pages = max(1, ceil(total / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    page_items = countries[start:start + page_size]

    # Telegram limits callback_data to 64 bytes; the country name itself can
    # be longer than that, so the button carries a short key instead.
    buttons = [[InlineKeyboardButton(
        text=f"◇ {c['country']}  ·  {c['count']}",
        callback_data=f"pick:{country_key(c['country'])}"
    )] for c in page_items]

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="‹", callback_data=f"gen:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"· {page} / {total_pages} ·", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="›", callback_data=f"gen:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="‹ Menu", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cookie_action_kb(pc_url: str, tv_url: str, mobile_url: str) -> InlineKeyboardMarkup:
    """PC and Mobile sign-in routes.

    There is deliberately no TV route: TV sign-in is an activation-code flow
    driven by the television itself, so a button here could only ever be a
    pre-authenticated link.  ``tv_url`` is still accepted (callers pass the
    stored inventory value) but is not rendered.
    """
    del tv_url  # accepted for call-site compatibility; no TV button is built
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="↗ Pᴄ", url=normalize_url(pc_url, DEFAULT_PC_URL)),
            InlineKeyboardButton(text="↗ Mᴏʙɪʟᴇ", url=normalize_url(mobile_url, DEFAULT_MOBILE_URL)),
        ],
    ])


def history_nav_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="‹", callback_data=f"history:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="›", callback_data=f"history:{page + 1}"))
    buttons = [nav] if nav else []
    buttons.append([InlineKeyboardButton(text="‹ Menu", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
