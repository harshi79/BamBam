"""
YoriNetflix — Inventory service tests.

Tests cookie parsing (pure functions, no DB needed).
"""

from app.services.inventory import parse_cookie_text, parse_bulk_cookies


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