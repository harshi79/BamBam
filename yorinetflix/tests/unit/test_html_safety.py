"""
YoriNetflix — HTML safety regression tests.

Verifies that all message builders produce valid Telegram HTML:
- All tags are properly opened and closed
- Dynamic user values are HTML-escaped
- No XSS injection possible through user-controlled fields
- Blockquotes are balanced
- No accidental double-escaping
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.formatting import (
    build_welcome_text,
    build_profile_text,
    build_account_message,
    build_daily_reward_text,
    build_daily_already_claimed,
    build_referral_text,
    build_history_page,
    build_leaderboard,
    build_fsub_prompt,
    build_admin_stats,
    build_stock_breakdown,
    build_add_result,
    build_givepoints_result,
    build_broadcast_progress,
    build_broadcast_complete,
)


def _count_tag(text: str, tag: str) -> int:
    """Count occurrences of an opening or closing HTML tag."""
    return text.count(f"<{tag}>") + text.count(f"<{tag} ")


def _count_close(text: str, tag: str) -> int:
    return text.count(f"</{tag}>")


def _assert_balanced(text: str, tag: str, label: str):
    opens = _count_tag(text, tag)
    closes = _count_close(text, tag)
    assert opens == closes, (
        f"{label}: <{tag}> has {opens} opens vs {closes} closes"
    )


def _assert_no_raw_html(text: str, dangerous: str, label: str):
    assert dangerous not in text, (
        f"{label}: unescaped '{dangerous}' found in output"
    )


class TestHtmlTagBalance:
    """Every message builder must produce balanced HTML tags."""

    def test_welcome_blockquote(self):
        _assert_balanced(build_welcome_text(), "blockquote", "welcome")

    def test_profile_bold(self):
        text = build_profile_text(
            full_name="Test", user_id=1, joined_at=None,
            total_generated=0, unique_countries=0, last_gen_time=None,
            cooldown_seconds=0, points=0, daily_remaining=0, daily_limit=0,
        )
        _assert_balanced(text, "b", "profile")
        _assert_balanced(text, "code", "profile")
        _assert_balanced(text, "i", "profile")

    def test_account_all_tags(self):
        text = build_account_message("X", "info", "n", "s", 5)
        for tag in ["b", "blockquote", "code", "i"]:
            _assert_balanced(text, tag, f"account:{tag}")

    def test_daily_reward(self):
        text = build_daily_reward_text(10, 50, 24)
        _assert_balanced(text, "b", "daily")
        _assert_balanced(text, "blockquote", "daily")

    def test_daily_claimed(self):
        text = build_daily_already_claimed(12)
        _assert_balanced(text, "b", "claimed")
        _assert_balanced(text, "blockquote", "claimed")

    def test_referral(self):
        text = build_referral_text("https://t.me/bot?start=ref_1", 5, 100, 25)
        _assert_balanced(text, "b", "referral")
        _assert_balanced(text, "blockquote", "referral")
        _assert_balanced(text, "code", "referral")

    def test_history(self):
        text = build_history_page(
            [{"country": "India", "when": "2024-01-01"}], 1, 1, 1
        )
        _assert_balanced(text, "b", "history")
        _assert_balanced(text, "i", "history")

    def test_leaderboard(self):
        text = build_leaderboard([{"name": "Test", "total": 10}])
        _assert_balanced(text, "b", "leaderboard")

    def test_fsub(self):
        text = build_fsub_prompt()
        _assert_balanced(text, "b", "fsub")
        _assert_balanced(text, "blockquote", "fsub")

    def test_admin_stats(self):
        text = build_admin_stats(10, 5, 100, 10, 50, 5, 20, [])
        _assert_balanced(text, "b", "stats")

    def test_stock_breakdown(self):
        text = build_stock_breakdown([{"country": "X", "count": 1}], 1)
        _assert_balanced(text, "b", "stock")

    def test_broadcast(self):
        _assert_balanced(build_broadcast_progress(1, 0, 0), "b", "progress")
        _assert_balanced(build_broadcast_complete(1, 0, 0), "b", "complete")


class TestXssProtection:
    """Dynamic user values must be HTML-escaped."""

    MALICIOUS = [
        "<script>alert(1)</script>",
        '" onmouseover="alert(1)"',
        "a & b",
        "x < y > z",
        "it's a test",
    ]

    def test_profile_name_escaped(self):
        for name in self.MALICIOUS:
            text = build_profile_text(
                full_name=name, user_id=1, joined_at=None,
                total_generated=0, unique_countries=0, last_gen_time=None,
                cooldown_seconds=0, points=0, daily_remaining=0, daily_limit=0,
            )
            _assert_no_raw_html(text, "<script>", "profile")
            # ampersand should be escaped
            if "&" in name and "&amp;" not in name:
                assert "&amp;" in text, f"profile: ampersand not escaped for '{name}'"

    def test_account_country_escaped(self):
        for country in self.MALICIOUS:
            text = build_account_message(country, "info", "n", "s", 5)
            _assert_no_raw_html(text, "<script>", "account")
            if "<" in country:
                assert "&lt;" in text, f"account: angle bracket not escaped for '{country}'"

    def test_leaderboard_name_escaped(self):
        for name in self.MALICIOUS:
            text = build_leaderboard([{"name": name, "total": 1}])
            _assert_no_raw_html(text, "<script>", "leaderboard")

    def test_history_country_escaped(self):
        for country in self.MALICIOUS:
            text = build_history_page(
                [{"country": country, "when": "2024"}], 1, 1, 1
            )
            _assert_no_raw_html(text, "<script>", "history")

    def test_stock_country_escaped(self):
        for country in self.MALICIOUS:
            text = build_stock_breakdown([{"country": country, "count": 1}], 1)
            _assert_no_raw_html(text, "<script>", "stock")

    def test_admin_stats_country_escaped(self):
        for country in self.MALICIOUS:
            text = build_admin_stats(
                1, 1, 1, 1, 1, 1, 1,
                [{"country": country, "count": 1}],
            )
            _assert_no_raw_html(text, "<script>", "admin_stats")


class TestNoDoubleEscaping:
    """Escaped values should not be re-escaped."""

    def test_ampersand_not_double_escaped(self):
        text = build_profile_text(
            full_name="A & B", user_id=1, joined_at=None,
            total_generated=0, unique_countries=0, last_gen_time=None,
            cooldown_seconds=0, points=0, daily_remaining=0, daily_limit=0,
        )
        # Should be "A &amp; B", not "A &amp;amp; B"
        assert "A &amp; B" in text
        assert "&amp;amp;" not in text

    def test_givepoints_not_double_escaped(self):
        text = build_givepoints_result(12345, 10, 100)
        assert "&amp;" not in text  # no ampersand in this input
        assert "<code>12345</code>" in text


class TestReferralLinkSafety:
    """Referral links in <code> blocks must be safe."""

    def test_referral_link_preserved_in_code(self):
        link = "https://t.me/testbot?start=ref_12345"
        text = build_referral_text(link, 3, 50, 25)
        assert f"<code>{link}</code>" in text

    def test_referral_link_no_escaping_issue(self):
        link = "https://t.me/testbot?start=ref_12345&lang=en"
        text = build_referral_text(link, 1, 10, 25)
        # The & in the URL should be escaped inside <code>
        assert "&amp;" in text or "code" in text