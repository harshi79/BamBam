"""
YoriNetflix — Safe Telegram messaging helpers.

Inline buttons have to feel instant and must never silently do nothing.
Every callback handler needs the same two operations, and both of them hit
Telegram error paths that are *normal* in production:

* ``safe_answer`` — acknowledges the callback so Telegram stops the
  "loading" spinner on the button the user pressed.  Acknowledging a
  callback twice, or too late, is an expected error and is ignored.

* ``safe_edit``   — updates the message in place.  When an in-place text
  edit is impossible it degrades gracefully instead of dropping the press:
  caption edit for media messages (the video welcome screen), a fresh
  message for deleted/inaccessible messages, and a no-op when Telegram
  reports "message is not modified".

Nothing in this module raises for an expected Telegram failure, so a button
press can never take the whole update down.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from aiogram.exceptions import AiogramError, TelegramAPIError
from aiogram.types import CallbackQuery, InaccessibleMessage, Message

log = logging.getLogger("yorinetflix.messaging")

# Telegram's reply when the new text and markup are byte-identical to the
# current message.  Nothing to do — this is a success, not a failure.
_NOT_MODIFIED = "message is not modified"

# Telegram's replies when the target message cannot be text-edited at all:
# media messages (video/photo welcome), deleted messages, old channel posts.
_NOT_EDITABLE = (
    "there is no text in the message",
    "no text in the message",
    "message to edit not found",
    "message can't be edited",
    "message identifier is not valid",
    "reply message not found",
)

# Telegram captions are capped at 1024 characters (text allows 4096).
_CAPTION_LIMIT = 1024

MessageLike = Union[Message, InaccessibleMessage, None]
EventLike = Union[CallbackQuery, Message, InaccessibleMessage]


def _message_of(event: EventLike) -> MessageLike:
    """Resolve the message behind an event (callback query or message)."""
    if isinstance(event, CallbackQuery):
        return event.message
    if isinstance(event, (Message, InaccessibleMessage)):
        return event
    return getattr(event, "message", None)


def _bot_of(event: EventLike, message: MessageLike):
    """Best-effort bot lookup: explicit > event context > message context."""
    for holder in (event, message):
        bot = getattr(holder, "bot", None)
        if bot is not None:
            return bot
    return None


async def safe_answer(
    callback: Optional[CallbackQuery],
    text: str = "",
    alert: bool = False,
) -> bool:
    """Acknowledge a callback query so the pressed button stops spinning.

    Returns True when Telegram accepted the acknowledgement.  Failures are
    logged and swallowed — a stale or duplicate answer must never crash the
    handler that triggered it.
    """
    if callback is None:
        return False
    try:
        await callback.answer(text, show_alert=alert)
        return True
    except AiogramError as e:
        log.debug("callback answer ignored: %s", e)
        return False
    except Exception as e:  # pragma: no cover - defensive
        log.warning("callback answer failed: %s", e)
        return False


async def safe_edit(
    event: EventLike,
    text: str,
    reply_markup: Any = None,
    bot: Any = None,
) -> bool:
    """Update a message in place, with graceful fallbacks.

    Accepts either a ``CallbackQuery`` (its message is edited) or a
    ``Message``.  Returns True when the user can see the new content, i.e.
    the message was edited, its caption was edited, Telegram reported it was
    already identical, or a fresh message was sent as a fallback.
    """
    message = _message_of(event)
    bot = bot or _bot_of(event, message)

    if message is None:
        return await _send_new(bot, None, text, reply_markup)

    # Deleted or too-old messages cannot be edited at all (aiogram gives us
    # an InaccessibleMessage without the edit_text shortcut).
    if not hasattr(message, "edit_text"):
        return await _send_fallback(message, text, reply_markup, bot)

    try:
        await message.edit_text(
            text, reply_markup=reply_markup, disable_web_page_preview=True
        )
        return True
    except TelegramAPIError as e:
        err = str(e).lower()
        if _NOT_MODIFIED in err:
            # Same content — the user already sees exactly this.
            return True
        if not any(marker in err for marker in _NOT_EDITABLE):
            log.warning("message edit failed (%s) — using fallback delivery", e)
        return await _edit_caption_or_send(message, text, reply_markup, bot)
    except AiogramError as e:  # pragma: no cover - defensive
        log.warning("message edit failed (%s) — using fallback delivery", e)
        return await _edit_caption_or_send(message, text, reply_markup, bot)
    except Exception as e:  # pragma: no cover - defensive
        log.warning("message edit failed (%r) — using fallback delivery", e)
        return await _edit_caption_or_send(message, text, reply_markup, bot)


async def respond(
    event: EventLike,
    text: str,
    reply_markup: Any = None,
    bot: Any = None,
) -> bool:
    """Deliver ``text`` from a handler that accepts Message *or* CallbackQuery.

    Callbacks are answered in place (editing the existing message, with the
    ``safe_edit`` fallbacks); plain messages get a fresh reply.
    """
    if isinstance(event, CallbackQuery):
        return await safe_edit(event, text, reply_markup, bot=bot)
    if isinstance(event, Message):
        try:
            await event.answer(
                text, reply_markup=reply_markup, disable_web_page_preview=True
            )
            return True
        except Exception as e:
            log.warning("message reply failed: %s", e)
            return False
    return False


async def ack(event: EventLike) -> bool:
    """Acknowledge an event early, before any slow database work.

    Telegram keeps the pressed button in a "loading" state until the callback
    is answered, so read-only navigation flows ack first and update the
    message afterwards.  No-op for plain messages.
    """
    if isinstance(event, CallbackQuery):
        return await safe_answer(event)
    return False


async def send_new(
    event: EventLike,
    text: str,
    reply_markup: Any = None,
    bot: Any = None,
) -> bool:
    """Send a brand-new message into the chat behind ``event``.

    Used where the content must not replace the current screen (delivered
    accounts, one-off results).  Works for deleted/inaccessible messages too,
    because only the chat is needed.  Returns True when it was delivered.
    """
    message = _message_of(event)
    bot = bot or _bot_of(event, message)
    return await _send_new(bot, message, text, reply_markup)


async def _edit_caption_or_send(
    message: MessageLike,
    text: str,
    reply_markup: Any,
    bot: Any,
) -> bool:
    """Media messages keep their media: edit the caption, else send anew."""
    if (
        getattr(message, "caption", None) is not None
        and len(text) <= _CAPTION_LIMIT
    ):
        try:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
            return True
        except TelegramAPIError as e:
            if _NOT_MODIFIED in str(e).lower():
                return True
            log.debug("caption edit failed (%s) — sending a fresh message", e)
        except Exception as e:  # pragma: no cover - defensive
            log.debug("caption edit failed (%r) — sending a fresh message", e)
    return await _send_fallback(message, text, reply_markup, bot)


async def _send_fallback(
    message: MessageLike,
    text: str,
    reply_markup: Any,
    bot: Any,
) -> bool:
    """Last resort: deliver the content as a brand-new message."""
    return await _send_new(bot, message, text, reply_markup)


async def _send_new(bot: Any, message: MessageLike, text: str, reply_markup: Any) -> bool:
    chat = getattr(message, "chat", None)
    try:
        if bot is not None and chat is not None:
            await bot.send_message(
                chat.id,
                text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            return True
        if message is not None:
            await message.answer(
                text, reply_markup=reply_markup, disable_web_page_preview=True
            )
            return True
    except Exception as e:
        log.warning("fallback message delivery failed: %s", e)
    log.warning("no way to deliver message content (chat unavailable)")
    return False


def parse_page(data: Optional[str], default: int = 1) -> int:
    """Parse the page number out of a pagination callback such as "gen:2".

    Callback data lives in old messages forever, so it can be truncated,
    stale or hand-edited.  Anything unusable falls back to ``default``
    instead of raising ``ValueError`` and leaving the button spinning.
    """
    if not data:
        return max(1, default)
    _, _, raw = data.partition(":")
    try:
        page = int(raw.strip())
    except (TypeError, ValueError):
        return max(1, default)
    return page if page >= 1 else max(1, default)
