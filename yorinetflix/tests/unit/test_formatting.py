"""
YoriNetflix — Formatting utility tests.
"""

from datetime import datetime, timezone

from app.utils import formatting
from app.utils.formatting import (
    DEFAULT_MOBILE_URL,
    DEFAULT_PC_URL,
    build_account_message,
    build_cookie_string,
    build_daily_already_claimed,
    build_daily_reward_text,
    build_history_page,
    build_profile_text,
    build_welcome_text,
    clean_info_block,
    normalize_url,
    strip_credential_params,
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

    def test_auto_login_token_is_stripped(self):
        """A URL that signs its opener into someone else's account must never
        reach a button — buttons are shared, cached and logged by Telegram."""
        result = normalize_url(
            "https://www.netflix.com/account?nftoken=NFSECRET123&locale=en-US",
            DEFAULT_PC_URL,
        )
        assert result == "https://www.netflix.com/account?locale=en-US"

    def test_credential_param_name_is_case_insensitive(self):
        assert (
            normalize_url("https://www.netflix.com/login?NFToken=abc", DEFAULT_MOBILE_URL)
            == "https://www.netflix.com/login"
        )

    def test_token_only_url_falls_back_to_official_page(self):
        """Stripping must not leave a bare domain root behind."""
        assert (
            normalize_url("https://www.netflix.com/?nftoken=NFSECRET", DEFAULT_PC_URL)
            == DEFAULT_PC_URL
        )

    def test_fragment_attached_to_a_token_is_dropped_too(self):
        assert (
            normalize_url(
                "https://www.netflix.com/account?nftoken=abc#state", DEFAULT_PC_URL
            )
            == "https://www.netflix.com/account"
        )

    def test_harmless_fragment_is_kept(self):
        assert (
            normalize_url("https://www.netflix.com/login?locale=en#top", DEFAULT_MOBILE_URL)
            == "https://www.netflix.com/login?locale=en#top"
        )


class TestSignInDefaults:
    """The default routes are plain public pages — never credential carriers."""

    def test_only_pc_and_mobile_routes_exist(self):
        # The TV route is gone on purpose: TV sign-in is a code-entry flow
        # driven by the television, so no destination is defined for it here.
        defaults = {
            name for name in dir(formatting) if name.startswith("DEFAULT_")
        }
        assert defaults == {"DEFAULT_PC_URL", "DEFAULT_MOBILE_URL"}
        assert DEFAULT_PC_URL == "https://www.netflix.com/account"
        assert DEFAULT_MOBILE_URL == "https://www.netflix.com/login"

    def test_defaults_carry_no_credentials(self):
        for url in (DEFAULT_PC_URL, DEFAULT_MOBILE_URL):
            assert "?" not in url
            assert "nftoken" not in url
            assert strip_credential_params(url) == url

    def test_strip_keeps_harmless_params_and_path(self):
        url = "https://www.netflix.com/account?serverState=abc&locale=en-GB"
        assert strip_credential_params(url) == url

    def test_strip_without_query_string_is_a_no_op(self):
        assert strip_credential_params("https://www.netflix.com/account") == (
            "https://www.netflix.com/account"
        )


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
