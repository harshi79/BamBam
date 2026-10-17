"""
YoriNetflix — Text utility tests.

Tests the small-caps transformer (sc, sc_html) and HTML escaping (esc).
"""

from __future__ import annotations

from app.utils.text import sc, sc_html, esc


class TestSmallCaps:
    """Test the sc() function."""

    def test_basic_lowercase(self):
        """Simple lowercase text should be converted to small caps."""
        result = sc("hello")
        assert result == "ʜᴇʟʟᴏ"

    def test_uppercase_preserved(self):
        """Uppercase letters are not in the mapping — left as-is."""
        result = sc("HELLO")
        assert result == "HELLO"

    def test_numbers_preserved(self):
        """Short numbers (fewer than 4 digits) are left as-is."""
        result = sc("test 123")
        assert "123" in result

    def test_empty_string(self):
        assert sc("") == ""

    def test_none_input(self):
        """None should return empty string."""
        assert sc(None) == ""

    def test_urls_preserved(self):
        """URLs should not be transformed."""
        result = sc("visit https://example.com today")
        assert "https://example.com" in result
        assert "today" not in result or "ᴛᴏᴅᴀʏ" in result

    def test_html_tags_preserved(self):
        """HTML tags should pass through unchanged."""
        result = sc("<b>hello</b>")
        assert "<b>" in result
        assert "</b>" in result
        assert "ʜᴇʟʟᴏ" in result

    def test_html_entities_preserved(self):
        """HTML entities like &amp; should not be transformed."""
        result = sc("a &amp; b")
        assert "&amp;" in result

    def test_long_numbers_preserved(self):
        """Numbers with 4+ digits (IDs, timestamps) should not transform."""
        result = sc("user 123456789")
        assert "123456789" in result

    def test_mixed_content(self):
        """Mix of protected and transformable content."""
        result = sc("go to https://t.me/test now")
        assert "https://t.me/test" in result

    def test_punctuation_preserved(self):
        """Punctuation should pass through unchanged."""
        result = sc("hello!")
        assert "!" in result


class TestSmallCapsHtml:
    """Test the sc_html() function."""

    def test_basic_html(self):
        """Simple HTML with text should transform text, preserve tags."""
        result = sc_html("<b>hello</b>")
        assert "<b>" in result
        assert "</b>" in result
        assert "ʜᴇʟʟᴏ" in result

    def test_blockquote_preserved(self):
        """<blockquote> tags should be preserved."""
        result = sc_html("<blockquote>content</blockquote>")
        assert "<blockquote>" in result
        assert "</blockquote>" in result

    def test_empty_string(self):
        assert sc_html("") == ""

    def test_none_input(self):
        assert sc_html(None) == ""

    def test_no_html(self):
        """Plain text without HTML should still be transformed."""
        result = sc_html("hello world")
        assert "ʜᴇʟʟᴏ" in result
        assert "ᴡᴏʀʟᴅ" in result

    def test_multiple_tags(self):
        """Multiple HTML tags should all be preserved."""
        result = sc_html("<b><i>bold italic</i></b>")
        assert "<b>" in result
        assert "<i>" in result
        assert "</i>" in result
        assert "</b>" in result

    def test_link_tag(self):
        """<a href> tags should be preserved."""
        result = sc_html('<a href="https://t.me/test">link</a>')
        assert "https://t.me/test" in result
        assert "ʟɪɴᴋ" in result

    def test_complex_message(self):
        """Realistic bot message with mixed HTML."""
        text = '🎬 <b>Netflix Account</b>\n📦 remaining: <b>5</b>'
        result = sc_html(text)
        assert "<b>" in result
        assert "5" in result


class TestEsc:
    """Test the esc() function."""

    def test_plain_text(self):
        assert esc("hello") == "hello"

    def test_html_chars_escaped(self):
        assert esc("<script>") == "&lt;script&gt;"

    def test_ampersand(self):
        assert esc("a & b") == "a &amp; b"

    def test_quotes_not_escaped(self):
        """quote=False — double quotes should NOT be escaped."""
        assert esc('"hello"') == '"hello"'

    def test_none_input(self):
        assert esc(None) == ""

    def test_empty_string(self):
        assert esc("") == ""

    def test_combined_special_chars(self):
        result = esc('<b>"test" & value</b>')
        assert "&lt;" in result
        assert "&amp;" in result
        assert '"' in result  # not escaped

    def test_already_escaped(self):
        """Double-escaping should produce &amp;lt; etc."""
        result = esc("&lt;")
        assert result == "&amp;lt;"