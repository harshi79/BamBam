"""
YoriNetflix — Safe messaging helper tests.

These cover the inline-button behaviours users actually feel: every press is
acknowledged, an edit that Telegram refuses is recovered from instead of
silently dropped, and nothing raises out of a handler.

aiogram types are frozen pydantic models, so shortcuts are patched on the
class (``patch.object(Message, "edit_text", …)``) rather than per instance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    CallbackQuery,
    Chat,
    InaccessibleMessage,
    Message,
    User,
)

from app.utils.messaging import (
    ack,
    parse_page,
    respond,
    safe_answer,
    safe_edit,
    send_new,
)

# ── Builders ──────────────────────────────────────────────────


def _chat(chat_id: int = 42) -> Chat:
    return Chat(id=chat_id, type="private")


def _user() -> User:
    return User(id=7, is_bot=False, first_name="Tester")


def _message(**kwargs) -> Message:
    kwargs.setdefault("message_id", 11)
    kwargs.setdefault("date", datetime.now(timezone.utc))
    kwargs.setdefault("chat", _chat())
    return Message(**kwargs)


def _callback(message=None, data: str = "menu") -> CallbackQuery:
    return CallbackQuery(
        id="cb-1",
        from_user=_user(),
        chat_instance="ci-1",
        data=data,
        message=message,
    )


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=None, message=message)


def _forbidden(message: str = "bot was blocked by the user") -> TelegramForbiddenError:
    return TelegramForbiddenError(method=None, message=message)


def _fake_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=_message())
    return bot


# ── safe_answer ───────────────────────────────────────────────


class TestSafeAnswer:
    async def test_answers_callback(self):
        with patch.object(CallbackQuery, "answer", AsyncMock(return_value=True)) as answer:
            assert await safe_answer(_callback(), "hi", True) is True
        answer.assert_awaited_once_with("hi", show_alert=True)

    async def test_swallows_bad_request(self):
        with patch.object(
            CallbackQuery, "answer", AsyncMock(side_effect=_bad_request("query is too old"))
        ):
            assert await safe_answer(_callback()) is False

    async def test_swallows_forbidden(self):
        with patch.object(CallbackQuery, "answer", AsyncMock(side_effect=_forbidden())):
            assert await safe_answer(_callback()) is False

    async def test_none_callback(self):
        assert await safe_answer(None) is False


# ── safe_edit ─────────────────────────────────────────────────


class TestSafeEdit:
    async def test_edits_in_place(self):
        edit = AsyncMock(return_value=_message())
        with patch.object(Message, "edit_text", edit):
            assert await safe_edit(_callback(message=_message(text="old")), "new") is True
        edit.assert_awaited_once()
        assert edit.await_args.args[0] == "new"

    async def test_not_modified_counts_as_success(self):
        edit = AsyncMock(side_effect=_bad_request("message is not modified"))
        bot = _fake_bot()
        with patch.object(Message, "edit_text", edit):
            result = await safe_edit(
                _callback(message=_message(text="same")), "same", None, bot=bot
            )
        assert result is True
        bot.send_message.assert_not_awaited()

    async def test_video_welcome_falls_back_to_caption(self):
        """The video welcome screen has no text — the caption is edited so the
        button still visibly does something instead of dying silently."""
        edit = AsyncMock(side_effect=_bad_request("there is no text in the message"))
        caption = AsyncMock(return_value=_message())
        bot = _fake_bot()
        with patch.object(Message, "edit_text", edit), patch.object(
            Message, "edit_caption", caption
        ):
            result = await safe_edit(
                _callback(message=_message(caption="welcome")), "menu", None, bot=bot
            )
        assert result is True
        caption.assert_awaited_once()
        assert caption.await_args.kwargs["caption"] == "menu"
        bot.send_message.assert_not_awaited()

    async def test_long_text_on_media_sends_new_message(self):
        edit = AsyncMock(side_effect=_bad_request("there is no text in the message"))
        caption = AsyncMock(return_value=_message())
        bot = _fake_bot()
        long_text = "x" * 2000  # over Telegram's 1024-character caption limit
        with patch.object(Message, "edit_text", edit), patch.object(
            Message, "edit_caption", caption
        ):
            result = await safe_edit(
                _callback(message=_message(caption="welcome")), long_text, None, bot=bot
            )
        assert result is True
        caption.assert_not_awaited()
        bot.send_message.assert_awaited_once()
        assert bot.send_message.await_args.args[0] == 42

    async def test_deleted_message_sends_new_one(self):
        edit = AsyncMock(side_effect=_bad_request("message to edit not found"))
        bot = _fake_bot()
        with patch.object(Message, "edit_text", edit):
            result = await safe_edit(
                _callback(message=_message(text="old")), "new", None, bot=bot
            )
        assert result is True
        bot.send_message.assert_awaited_once()

    async def test_inaccessible_message_sends_new_one(self):
        inaccessible = InaccessibleMessage(chat=_chat(), message_id=0)
        bot = _fake_bot()
        assert not hasattr(inaccessible, "edit_text")

        assert await safe_edit(_callback(message=inaccessible), "new", None, bot=bot) is True
        bot.send_message.assert_awaited_once()

    async def test_no_message_and_no_chat_reports_failure(self):
        bot = _fake_bot()
        assert await safe_edit(_callback(message=None), "new", None, bot=bot) is False
        bot.send_message.assert_not_awaited()

    async def test_blocked_user_does_not_raise(self):
        edit = AsyncMock(side_effect=_forbidden())
        bot = _fake_bot()
        bot.send_message = AsyncMock(side_effect=_forbidden())
        with patch.object(Message, "edit_text", edit):
            result = await safe_edit(
                _callback(message=_message(text="old")), "new", None, bot=bot
            )
        assert result is False

    async def test_accepts_plain_message(self):
        edit = AsyncMock(return_value=_message())
        with patch.object(Message, "edit_text", edit):
            assert await safe_edit(_message(text="old"), "new") is True
        edit.assert_awaited_once()

    async def test_unexpected_error_is_recovered_not_raised(self):
        edit = AsyncMock(side_effect=RuntimeError("boom"))
        bot = _fake_bot()
        with patch.object(Message, "edit_text", edit):
            result = await safe_edit(
                _callback(message=_message(text="old")), "new", None, bot=bot
            )
        assert result is True
        bot.send_message.assert_awaited_once()


# ── respond / send_new / ack ──────────────────────────────────


class TestRespond:
    async def test_callback_edits(self):
        edit = AsyncMock(return_value=_message())
        with patch.object(Message, "edit_text", edit):
            assert await respond(_callback(message=_message(text="old")), "new") is True
        edit.assert_awaited_once()

    async def test_message_answers(self):
        answer = AsyncMock(return_value=_message())
        with patch.object(Message, "answer", answer):
            assert await respond(_message(text="/daily"), "new") is True
        answer.assert_awaited_once()

    async def test_message_failure_does_not_raise(self):
        answer = AsyncMock(side_effect=_bad_request("chat not found"))
        with patch.object(Message, "answer", answer):
            assert await respond(_message(text="/daily"), "new") is False


class TestSendNew:
    async def test_uses_bot_when_available(self):
        bot = _fake_bot()
        assert await send_new(_callback(message=_message()), "hi", None, bot) is True
        bot.send_message.assert_awaited_once()

    async def test_falls_back_to_message_answer(self):
        answer = AsyncMock(return_value=_message())
        with patch.object(Message, "answer", answer):
            assert await send_new(_message(text="old"), "hi") is True
        answer.assert_awaited_once()


class TestAck:
    async def test_acks_callback(self):
        with patch.object(CallbackQuery, "answer", AsyncMock(return_value=True)) as answer:
            assert await ack(_callback()) is True
        answer.assert_awaited_once()

    async def test_message_is_noop(self):
        assert await ack(_message()) is False


# ── parse_page ────────────────────────────────────────────────


class TestParsePage:
    @pytest.mark.parametrize(
        "data,expected",
        [
            ("gen:2", 2),
            ("history:10", 10),
            ("gen:0", 1),
            ("gen:-3", 1),
            ("gen:", 1),
            ("gen:abc", 1),
            ("gen", 1),
            ("", 1),
            (None, 1),
            ("gen: 4 ", 4),
        ],
    )
    def test_parses_pages(self, data, expected):
        assert parse_page(data) == expected

    def test_custom_default(self):
        assert parse_page("gen:zzz", default=3) == 3
