"""
YoriNetflix — Inventory service tests.

Tests cookie parsing (pure functions, no DB needed).
"""

from unittest.mock import AsyncMock

import pytest

from app.services import inventory
from app.services.inventory import (
    COUNTRY_KEY_LEN,
    country_key,
    parse_bulk_cookies,
    parse_cookie_text,
)


SAMPLE_COOKIE = """📁 Source: Something
🌍 Country: India (IN)
━━━━━━━━━━━━━━━━━━━━
• PC Login URL: https://www.netflix.com/account
• Phone Login URL: https://www.netflix.com/login
• TV Login URL: https://www.netflix.com/tv2
━━━━━━━━━━━━━━━━━━━━
🍪 Cookie: NetflixId=abc123def456
🔐 SecureNetflixId: sec789xyz
━━━━━━━━━━━━━━━━━━━━"""


class TestParseCookieText:
    def test_country(self):
        data = parse_cookie_text(SAMPLE_COOKIE)
        assert data["country"] == "India"

    def test_pc_url(self):
        data = parse_cookie_text(SAMPLE_COOKIE)
        assert data["pc_url"] == "https://www.netflix.com/account"

    def test_phone_url(self):
        data = parse_cookie_text(SAMPLE_COOKIE)
        assert data["phone_url"] == "https://www.netflix.com/login"

    def test_tv_url(self):
        # The parser keeps inventory text verbatim and the value is still
        # stored, but no TV button is built from it — TV sign-in is a
        # code-entry flow driven by the television itself.
        data = parse_cookie_text(SAMPLE_COOKIE)
        assert data["tv_url"] == "https://www.netflix.com/tv2"

    def test_netflix_id(self):
        data = parse_cookie_text(SAMPLE_COOKIE)
        assert data["netflix_id"] == "abc123def456"

    def test_secure_netflix_id(self):
        data = parse_cookie_text(SAMPLE_COOKIE)
        assert data["secure_netflix_id"] == "sec789xyz"

    def test_cookie_hash_is_deterministic(self):
        d1 = parse_cookie_text(SAMPLE_COOKIE)
        d2 = parse_cookie_text(SAMPLE_COOKIE)
        assert d1["cookie_hash"] == d2["cookie_hash"]

    def test_different_text_different_hash(self):
        d1 = parse_cookie_text(SAMPLE_COOKIE)
        d2 = parse_cookie_text("🌍 Country: Japan (JP)\n🍪 Cookie: NetflixId=different")
        assert d1["cookie_hash"] != d2["cookie_hash"]

    def test_missing_country_defaults_to_unknown(self):
        data = parse_cookie_text("just some text without country")
        assert data["country"] == "Unknown"

    def test_raw_text_preserved(self):
        data = parse_cookie_text(SAMPLE_COOKIE)
        assert "NetflixId=abc123def456" in data["raw_text"]

    def test_country_strips_region_code(self):
        data = parse_cookie_text("🌍 Country: United States (US)")
        assert data["country"] == "United States"


class TestParseBulkCookies:
    def test_single_cookie(self):
        results = parse_bulk_cookies(SAMPLE_COOKIE)
        assert len(results) == 1

    def test_bulk_cookies(self):
        bulk = f"{SAMPLE_COOKIE}\n\n📁 Source: Another\n{SAMPLE_COOKIE}"
        results = parse_bulk_cookies(bulk)
        assert len(results) >= 1

    def test_empty_text(self):
        results = parse_bulk_cookies("")
        assert results == []

    def test_malformed_text_returns_single(self):
        results = parse_bulk_cookies("just random text")
        assert len(results) == 1

class TestCountryKey:
    """``country_key`` is what country buttons carry as callback_data."""

    def test_is_short_hex_and_fits_telegram_callback_limit(self):
        key = country_key("🇹🇭 สาธารณรัฐประชาธิปไตยประชาชนลาว")
        assert len(key) == COUNTRY_KEY_LEN
        assert all(ch in "0123456789abcdef" for ch in key)
        assert len(f"pick:{key}".encode("utf-8")) <= 64

    def test_is_deterministic(self):
        assert country_key("India") == country_key("India")

    def test_distinct_countries_get_distinct_keys(self):
        names = ["India", "india", "India ", "Indonesia", "🇮🇳 India"]
        assert len({country_key(n) for n in names}) == len(names)


class TestResolveCountry:
    """``resolve_country`` turns a button payload back into the stocked country."""

    STOCK = [
        {"country": "India", "cnt": 3},
        {"country": "🇸🇦 المملكة العربية السعودية", "cnt": 1},
        {"country": "United Kingdom of Great Britain and Northern Ireland", "cnt": 2},
    ]

    @pytest.fixture(autouse=True)
    def _stock(self, monkeypatch):
        monkeypatch.setattr(
            inventory.inventory_repo, "get_country_stock", AsyncMock(return_value=self.STOCK)
        )

    async def test_resolves_key_to_exact_country_name(self):
        for entry in self.STOCK:
            name = entry["country"]
            assert await inventory.resolve_country(object(), country_key(name)) == name

    async def test_legacy_raw_country_name_still_resolves(self):
        """Keyboards sent before keys existed carry ``pick:<country name>``."""
        assert await inventory.resolve_country(object(), "India") == "India"

    async def test_unknown_key_or_name_resolves_to_none(self):
        assert await inventory.resolve_country(object(), "deadbeefdeadbeef") is None
        assert await inventory.resolve_country(object(), "Atlantis") is None
        assert await inventory.resolve_country(object(), "") is None

    async def test_sold_out_country_resolves_to_none(self, monkeypatch):
        monkeypatch.setattr(
            inventory.inventory_repo, "get_country_stock", AsyncMock(return_value=[])
        )
        assert await inventory.resolve_country(object(), country_key("India")) is None
