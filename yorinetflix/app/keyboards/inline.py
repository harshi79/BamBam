"""
YoriNetflix — Inline keyboard builders.

All keyboards are pure functions returning InlineKeyboardMarkup.
"""

from __future__ import annotations

from math import ceil

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.utils.text import sc
from app.utils.formatting import normalize_url, DEFAULT_PC_URL, DEFAULT_TV_URL, DEFAULT_MOBILE_URL


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sc("Generate 🍿"), callback_data="gen:0")],
        [
            InlineKeyboardButton(text=sc("Daily Reward 🎁"), callback_data="daily"),
            InlineKeyboardButton(text=sc("Profile 📊"), callback_data="profile"),
        ],
        [
            InlineKeyboardButton(text=sc("History 🕘"), callback_data="history:1"),
            InlineKeyboardButton(text=sc("Referral 🔗"), callback_data="referral"),
        ],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sc("⬅️ Menu"), callback_data="menu")]
    ])


def join_kb(force_channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sc("📢 Join Channel"), url=force_channel_url)],
        [InlineKeyboardButton(text=sc("✅ I Joined"), callback_data="check_join")],
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

    buttons = [[InlineKeyboardButton(
        text=f"🌍 {c['country']} · {c['count']}",
        callback_data=f"pick:{c['country']}"
    )] for c in page_items]

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"gen:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"gen:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text=sc("⬅️ Menu"), callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cookie_action_kb(pc_url: str, tv_url: str, mobile_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💻 PC", url=normalize_url(pc_url, DEFAULT_PC_URL)),
            InlineKeyboardButton(text="📺 TV", url=normalize_url(tv_url, DEFAULT_TV_URL)),
            InlineKeyboardButton(text="📱 Mobile", url=normalize_url(mobile_url, DEFAULT_MOBILE_URL)),
        ],
    ])


def history_nav_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"history:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"history:{page + 1}"))
    buttons = [nav] if nav else []
    buttons.append([InlineKeyboardButton(text=sc("⬅️ Menu"), callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)