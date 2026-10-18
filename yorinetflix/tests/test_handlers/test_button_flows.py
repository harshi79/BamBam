"""
YoriNetflix — Inline button flow tests.

Real aiogram ``Update`` objects are pushed through the dispatcher with a
recording bot session and a faked database pool, so these assert on the exact
Telegram methods the bot would send.

They are regression tests for what users experienced as "buttons not working":

* ``/referral`` crashed with ``Bad Request: can't parse entities: Unsupported
  start tag "coroutine"`` because ``get_referral_link`` was never awaited, and
  the coroutine's repr was injected into the HTML message.
* Buttons on the video welcome screen (and on deleted/inaccessible messages)
  did nothing at all, because ``edit_text`` failed and the error was swallowed.
* Unmatched callback data was never acknowledged, leaving the button spinning.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageCaption,
    EditMessageText,
    GetMe,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    InaccessibleMessage,
    Message,
    Update,
    User,
    Video,
)

from app.config import Settings
from app.handlers import generation, history, register_all, rewards
from app.middleware.throttle import ThrottleMiddleware

# Telegram only accepts this set of HTML entities; anything else makes the
# whole sendMessage/editMessageText call fail with "can't parse entities".
SUPPORTED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "span", "tg-spoiler", "a", "code", "pre", "blockquote",
}

USER_ID = 7
BOT_USERNAME = "yorinetflix_bot"


# ── Recording bot session ─────────────────────────────────────


class RecordingSession(BaseSession):
    """Captures every Telegram method instead of performing an HTTP request."""

    def __init__(self, *, fail_text_edits: str | None = None):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.fail_text_edits = fail_text_edits

    async def close(self) -> None:  # pragma: no cover - never called in tests
        return None

    async def stream_content(  # pragma: no cover - never called in tests
        self,
        url: str,
        headers: dict | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ):
        yield b""

    async def make_request(
        self, bot: Bot, method: TelegramMethod, timeout: int | None = None
    ) -> Any:
        self.calls.append(method)
        if self.fail_text_edits and isinstance(method, EditMessageText):
            raise TelegramBadRequest(method=method, message=self.fail_text_edits)
        return _result_for(method)

    # ── assertions ────────────────────────────────────────────
    def of_type(self, *types):
        return [c for c in self.calls if isinstance(c, types)]

    @property
    def edited_texts(self) -> list[str]:
        return [c.text for c in self.of_type(EditMessageText)]

    @property
    def sent_texts(self) -> list[str]:
        return [c.text for c in self.of_type(SendMessage)]

    @property
    def answered(self) -> bool:
        return bool(self.of_type(AnswerCallbackQuery))


def _result_for(method: TelegramMethod) -> Any:
    if isinstance(method, GetMe):
        return User(id=999, is_bot=True, first_name="YoriNetflix", username=BOT_USERNAME)
    if isinstance(method, (SendMessage, EditMessageText, EditMessageCaption)):
        text = getattr(method, "text", None) or getattr(method, "caption", None) or ""
        return _message(text=text, message_id=500)
    return True


# ── Faked database ────────────────────────────────────────────


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Connection:
    def transaction(self):
        return _Transaction()

    async def fetchrow(self, *args, **kwargs):
        return None

    async def fetch(self, *args, **kwargs):
        return []

    async def execute(self, *args, **kwargs):
        return "SELECT 0"


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self):
        self.conn = _Connection()

    def acquire(self):
        return _Acquire(self.conn)


# ── Builders ──────────────────────────────────────────────────


def _chat(chat_id: int = USER_ID) -> Chat:
    return Chat(id=chat_id, type="private")


def _message(text: str = "menu", message_id: int = 11, caption: str | None = None) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=_chat(),
        text=None if caption else text,
        caption=caption,
        video=(
            Video(file_id="vid", file_unique_id="vid", width=640, height=360, duration=10)
            if caption else None
        ),
    )


def _callback_update(data: str, message=None, update_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=f"cb-{update_id}",
            from_user=User(id=USER_ID, is_bot=False, first_name="Tester"),
            chat_instance="ci-1",
            data=data,
            message=message if message is not None else _message(),
        ),
    )


def _message_update(text: str, update_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=_chat(),
            text=text,
            from_user=User(id=USER_ID, is_bot=False, first_name="Tester"),
        ),
    )


def _assert_supported_html(text: str) -> None:
    """Every tag Telegram receives must be one it understands."""
    for raw in re.findall(r"</?[^>]+>", text):
        name = raw.strip("<>/ ").split(" ")[0].split(">")[0]
        assert name in SUPPORTED_TAGS, f"unsupported start tag {name!r} in {text!r}"


@pytest.fixture
def bot_env(monkeypatch, valid_env):
    """Settings + a bot with a recording session + a faked database pool."""
    settings = Settings()
    session = RecordingSession()
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    pool = _Pool()

    # Every handler module resolves the pool through its own import.
    for module in (rewards, history, generation):
        monkeypatch.setattr(module, "get_pool", lambda: pool)

    monkeypatch.setattr(rewards, "get_referral_stats", AsyncMock(
        return_value={"referral_count": 3}
    ))
    monkeypatch.setattr(rewards.user_repo, "get_points", AsyncMock(return_value=42))
    monkeypatch.setattr(rewards.user_repo, "upsert", AsyncMock(return_value=None))
    monkeypatch.setattr(rewards.user_repo, "add_points", AsyncMock(return_value=None))
    monkeypatch.setattr(rewards.rewards_repo, "try_claim_daily", AsyncMock(return_value=True))
    monkeypatch.setattr(rewards.rewards_repo, "add_transaction", AsyncMock(return_value=None))
    monkeypatch.setattr(history.history_repo, "get_user_history", AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(generation.inventory, "get_country_stock", AsyncMock(return_value=[]))

    return settings, bot, session


# ── Referral button (the production crash) ────────────────────


class TestReferralButton:
    async def test_callback_sends_real_link(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("referral"))

        assert session.edited_texts, "the referral screen should be edited in place"
        text = session.edited_texts[0]
        assert f"https://t.me/{BOT_USERNAME}?start=ref_{USER_ID}" in text
        assert "coroutine" not in text
        _assert_supported_html(text)

    async def test_command_sends_real_link(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        await dp.feed_update(bot, _message_update("/referral"))

        assert session.sent_texts, "the /referral command should answer with a message"
        text = session.sent_texts[0]
        assert f"https://t.me/{BOT_USERNAME}?start=ref_{USER_ID}" in text
        assert "coroutine" not in text
        _assert_supported_html(text)

    async def test_button_is_acknowledged(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("referral"))

        assert session.answered, "an unacknowledged callback leaves the button spinning"

    async def test_works_on_video_welcome(self, bot_env, monkeypatch):
        """The welcome screen is a video: edit_text is impossible, so the
        caption is edited instead of the press being dropped."""
        settings, bot, session = bot_env
        monkeypatch.setattr(session, "fail_text_edits", "there is no text in the message")
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("referral", message=_message(caption="welcome")))

        captions = session.of_type(EditMessageCaption)
        assert captions, "media messages must fall back to a caption edit"
        assert f"https://t.me/{BOT_USERNAME}?start=ref_{USER_ID}" in captions[0].caption
        assert "coroutine" not in captions[0].caption

    async def test_works_on_inaccessible_message(self, bot_env):
        """Deleted/old messages still deliver the content as a new message."""
        settings, bot, session = bot_env
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        inaccessible = InaccessibleMessage(chat=_chat(), message_id=0)
        await dp.feed_update(bot, _callback_update("referral", message=inaccessible))

        assert session.sent_texts, "an inaccessible message should fall back to a new one"
        assert f"https://t.me/{BOT_USERNAME}?start=ref_{USER_ID}" in session.sent_texts[0]

    async def test_bot_identity_is_not_refetched_per_press(self, bot_env):
        """The bot username never changes: a live getMe per press only added
        latency (~500ms updates in production logs)."""
        settings, bot, session = bot_env
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("referral", update_id=1))
        await dp.feed_update(bot, _callback_update("referral", update_id=2))

        assert len(session.edited_texts) == 2
        assert len(session.of_type(GetMe)) <= 1, "getMe should be served from cache"


# ── Daily button ──────────────────────────────────────────────


class TestDailyButton:
    async def test_claimed_reward(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("daily"))

        assert session.answered
        assert session.edited_texts
        assert "42" in session.edited_texts[0]
        _assert_supported_html(session.edited_texts[0])

    async def test_command_path(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        rewards.register(dp, bot, settings)

        await dp.feed_update(bot, _message_update("/daily"))

        assert session.sent_texts
        _assert_supported_html(session.sent_texts[0])


# ── Navigation, pagination and unknown callbacks ──────────────


class TestNavigationButtons:
    async def test_menu_button(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        register_all(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("menu"))

        assert session.answered
        assert session.edited_texts, "the menu button must repaint the screen"
        _assert_supported_html(session.edited_texts[0])

    async def test_unknown_callback_is_answered(self, bot_env):
        """Stale keyboards must never leave a button spinning."""
        settings, bot, session = bot_env
        dp = Dispatcher()
        register_all(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("some:stale:data"))

        assert session.answered

    async def test_noop_button(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        register_all(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("noop"))

        assert session.answered
        assert not session.edited_texts

    async def test_malformed_history_page_does_not_crash(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        history.register(dp)

        await dp.feed_update(bot, _callback_update("history:not-a-number"))

        assert session.answered
        assert session.edited_texts, "history should fall back to page 1"

    async def test_malformed_gen_page_does_not_crash(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        generation.register(dp, settings)

        await dp.feed_update(bot, _callback_update("gen:"))

        assert session.answered
        assert session.edited_texts


class TestThrottledButtons:
    async def test_throttled_callback_is_still_answered(self, bot_env):
        settings, bot, session = bot_env
        dp = Dispatcher()
        dp.callback_query.middleware(ThrottleMiddleware(rate=5.0))
        register_all(dp, bot, settings)

        await dp.feed_update(bot, _callback_update("menu", update_id=1))
        await dp.feed_update(bot, _callback_update("menu", update_id=2))

        # First press handled, second throttled — both acknowledged.
        assert len(session.of_type(AnswerCallbackQuery)) == 2
