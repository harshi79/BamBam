"""
YoriNetflix — Keyboard builder tests.
"""

from app.keyboards.inline import (
    back_to_menu_kb,
    cookie_action_kb,
    country_list_kb,
    history_nav_kb,
    join_kb,
    main_menu_kb,
)
from app.services.inventory import country_key

# Telegram rejects the whole keyboard (BUTTON_DATA_INVALID) if any single
# button's callback_data is longer than this many bytes.
TELEGRAM_CALLBACK_DATA_LIMIT = 64

# Country names as cookie checkers really emit them: long official names,
# flag emojis (8 bytes each) and non-Latin scripts (2–4 bytes per character).
AWKWARD_COUNTRY_NAMES = [
    "United Kingdom of Great Britain and Northern Ireland",
    "🇸🇦 المملكة العربية السعودية",
    "🇹🇭 สาธารณรัฐประชาธิปไตยประชาชนลาว",
    "United States (US) | 🏙 City: New York | ⏰ TZ: America/New_York",
    "Côte d'Ivoire",
]


def _all_texts(kb):
    return [b.text for row in kb.inline_keyboard for b in row]


def _pick_buttons(kb):
    return [
        b for row in kb.inline_keyboard for b in row
        if b.callback_data and b.callback_data.startswith("pick:")
    ]


class TestMainMenuKb:
    def test_has_generate_button(self):
        texts = _all_texts(main_menu_kb())
        assert any("Gᴇɴᴇʀᴀᴛᴇ" in t or "Generate" in t for t in texts)

    def test_has_profile_button(self):
        texts = _all_texts(main_menu_kb())
        assert any("Pʀᴏꜰɪʟᴇ" in t or "Profile" in t for t in texts)

    def test_has_daily_button(self):
        texts = _all_texts(main_menu_kb())
        assert any("Dᴀɪʟʏ" in t or "Daily" in t for t in texts)

    def test_has_referral_button(self):
        texts = _all_texts(main_menu_kb())
        assert any("Rᴇꜰᴇʀʀᴀʟ" in t or "Referral" in t for t in texts)

    def test_button_count(self):
        kb = main_menu_kb()
        assert len(kb.inline_keyboard) == 3  # gen, daily+profile, history+referral

    def test_callback_contract_is_unchanged(self):
        kb = main_menu_kb()
        callbacks = [
            button.callback_data
            for row in kb.inline_keyboard
            for button in row
            if button.callback_data
        ]
        assert callbacks == ["gen:0", "daily", "profile", "history:1", "referral"]

    def test_labels_use_symbols_instead_of_classic_emojis(self):
        labels = _all_texts(main_menu_kb())
        classic_emojis = ("🍿", "🎁", "📊", "🕘", "🔗")
        assert all(emoji not in label for emoji in classic_emojis for label in labels)


class TestBackToMenuKb:
    def test_has_menu_button(self):
        kb = back_to_menu_kb()
        assert len(kb.inline_keyboard) == 1
        text = kb.inline_keyboard[0][0].text
        assert "Menu" in text or "⬅️" in text


class TestJoinKb:
    def test_has_join_and_verify(self):
        kb = join_kb("https://t.me/test")
        texts = _all_texts(kb)
        assert any("Jᴏɪɴ" in t or "Join" in t for t in texts)
        assert any("Jᴏɪɴᴇᴅ" in t or "Joined" in t for t in texts)


class TestCountryListKb:
    def test_single_page(self):
        countries = [{"country": "India", "count": 5}, {"country": "Japan", "count": 3}]
        kb = country_list_kb(countries, 1, 12)
        texts = _all_texts(kb)
        assert any("India" in t or "Iɴᴅɪᴀ" in t for t in texts)

    def test_pagination(self):
        countries = [{"country": f"C{i}", "count": 1} for i in range(25)]
        kb = country_list_kb(countries, 1, 12)
        all_cb = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
        assert any("gen:2" in cb for cb in all_cb)

    def test_empty_countries(self):
        kb = country_list_kb([], 1, 12)
        assert len(kb.inline_keyboard) >= 1

    def test_one_button_per_country_with_name_and_count(self):
        countries = [{"country": name, "count": i + 1} for i, name in enumerate(AWKWARD_COUNTRY_NAMES)]
        kb = country_list_kb(countries, 1, 12)
        texts = [b.text for b in _pick_buttons(kb)]
        assert len(texts) == len(AWKWARD_COUNTRY_NAMES)
        for i, name in enumerate(AWKWARD_COUNTRY_NAMES):
            assert name in texts[i] and str(i + 1) in texts[i]

    def test_callback_data_fits_telegram_limit_for_any_country_name(self):
        """Regression: long / emoji / non-Latin country names used to be
        embedded verbatim in callback_data, blowing Telegram's 64-byte cap and
        making the whole country page fail to render."""
        countries = [{"country": name, "count": 1} for name in AWKWARD_COUNTRY_NAMES]
        kb = country_list_kb(countries, 1, 12)
        buttons = _pick_buttons(kb)
        assert len(buttons) == len(AWKWARD_COUNTRY_NAMES)
        for button in buttons:
            size = len(button.callback_data.encode("utf-8"))
            assert size <= TELEGRAM_CALLBACK_DATA_LIMIT, (button.text, size)

    def test_pick_payload_is_the_country_key(self):
        countries = [{"country": name, "count": 1} for name in AWKWARD_COUNTRY_NAMES]
        kb = country_list_kb(countries, 1, 12)
        payloads = [b.callback_data for b in _pick_buttons(kb)]
        assert payloads == [f"pick:{country_key(name)}" for name in AWKWARD_COUNTRY_NAMES]
        # Distinct countries must never share a button payload.
        assert len(set(payloads)) == len(payloads)


class TestCookieActionKb:
    def test_has_three_buttons(self):
        kb = cookie_action_kb("https://pc.com", "https://tv.com", "https://m.com")
        assert len(kb.inline_keyboard[0]) == 3

    def test_uses_fallbacks(self):
        kb = cookie_action_kb("", "", "")
        urls = [b.url for b in kb.inline_keyboard[0]]
        assert all("netflix.com" in u for u in urls)


class TestHistoryNavKb:
    def test_first_page_no_back(self):
        kb = history_nav_kb(1, 3)
        cbs = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
        assert not any("history:0" in cb for cb in cbs)
        assert any("history:2" in cb for cb in cbs)

    def test_last_page_no_forward(self):
        kb = history_nav_kb(3, 3)
        cbs = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
        assert any("history:2" in cb for cb in cbs)
        assert not any("history:4" in cb for cb in cbs)
