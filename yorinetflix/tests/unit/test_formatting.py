"""
YoriNetflix — Formatting utility tests.
"""

from datetime import datetime, timezone

from app.utils.formatting import (
    build_account_message,
    build_cookie_string,
    build_daily_already_claimed,
    build_daily_reward_text,
    build_history_page,
    build_profile_text,
    build_welcome_text,
    clean_info_block,
    normalize_url,
)


class TestWelcomeText:
    def test_contains_branding(self):
        text = build_welcome_text()
        # Branding appears as small-caps "yorinetflix" in the blockquote
        assert "ʏᴏʀɪɴᴇᴛꜰʟɪx" in text or "YoriNetflix" in text or "yorinetflix" in text.lower()

    def test_contains_welcome(self):
        text = build_welcome_text()
        assert "welcome" in text or "ᴡᴇʟᴄᴏᴍᴇ" in text

    def test_uses_small_caps_branding_and_clean_symbols(self):
        text = build_welcome_text()
        assert "✦ ʏᴏʀɪɴᴇᴛꜰʟɪx" in text
        assert "🍿" not in text and "🎬" not in text


class TestProfileText:
    def test_contains_user_info(self):
        text = build_profile_text(
            full_name="Test User", user_id=123,
            joined_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            total_generated=5, unique_countries=3,
            last_gen_time=None, cooldown_seconds=120, points=50,
            daily_remaining=3, daily_limit=5,
        )
        # sc_html converts to small-caps — check for Unicode versions
        assert "123" in text
        assert "2024-01-01" in text
        assert "5" in text
        assert "50" in text

    def test_ready_cooldown(self):
        text = build_profile_text(
            full_name="T", user_id=1,
            joined_at=None, total_generated=0, unique_countries=0,
            last_gen_time=None, cooldown_seconds=120, points=0,
            daily_remaining=5, daily_limit=5,
        )
        assert "ʀᴇᴀᴅʏ" in text or "ready" in text.lower()


class TestAccountMessage:
    def test_contains_country(self):
        text = build_account_message("India", "some raw text", "n1", "s1", 5)
        # sc_html converts to small-caps Unicode
        assert "India" in text or "Iɴᴅɪᴀ" in text

    def test_contains_cookie_string(self):
        text = build_account_message("India", "text", "abc", "xyz", 5)
        # Cookie values are in <code> blocks, not transformed by sc
        assert "NetflixId=abc" in text
        assert "SecureNetflixId=xyz" in text

    def test_empty_cookie_ids(self):
        text = build_account_message("India", "text", "", "", 5)
        assert "NetflixId" not in text

    def test_remaining_count(self):
        text = build_account_message("India", "text", "n1", "s1", 42)
        assert "42" in text


class TestBuildCookieString:
    def test_both_ids(self):
        result = build_cookie_string("abc", "xyz")
        assert "NetflixId=abc" in result
        assert "SecureNetflixId=xyz" in result

    def test_na_ids_excluded(self):
        result = build_cookie_string("N/A", "N/A")
        assert result == ""

    def test_empty_ids(self):
        result = build_cookie_string("", "")
        assert result == ""


class TestNormalizeUrl:
    def test_valid_url_unchanged(self):
        assert normalize_url("https://example.com", "fallback") == "https://example.com"

    def test_empty_uses_fallback(self):
        assert normalize_url("", "https://fallback.com") == "https://fallback.com"

    def test_na_uses_fallback(self):
        assert normalize_url("N/A", "https://fallback.com") == "https://fallback.com"

    def test_no_scheme_adds_https(self):
        result = normalize_url("example.com/path", "fallback")
        assert result == "https://example.com/path"


class TestCleanInfoBlock:
    def test_strips_cookie_line(self):
        text = "Some info\n🍪 Cookie: NetflixId=abc\nMore info"
        result = clean_info_block(text)
        assert "NetflixId" not in result
        assert "Some info" in result

    def test_strips_secure_line(self):
        text = "Info\n🔐 SecureNetflixId: xyz\nEnd"
        result = clean_info_block(text)
        assert "SecureNetflixId" not in result

    def test_strips_url_lines(self):
        text = "Info\n• PC Login URL: https://x.com\nEnd"
        result = clean_info_block(text)
        assert "Login URL" not in result

    def test_strips_separator_lines(self):
        text = "Info\n━━━━━━━━━━\nEnd"
        result = clean_info_block(text)
        assert "━━━━" not in result


class TestDailyRewardText:
    def test_claimed_text(self):
        text = build_daily_reward_text(10, 50, 24)
        assert "10" in text
        assert "50" in text

    def test_already_claimed_text(self):
        text = build_daily_already_claimed(12)
        assert "12" in text


class TestHistoryFormatting:
    def test_second_page_keeps_absolute_entry_numbers(self):
        text = build_history_page(
            [{"country": "Japan", "when": "2024-01-01 12:00 UTC"}],
            page=2,
            total_pages=2,
            total=11,
        )
        assert "<code>11</code>" in text
