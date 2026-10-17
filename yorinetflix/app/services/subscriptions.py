"""
YoriNetflix — Force-subscription service.

Fail-closed by default: if the check fails, user is blocked.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

log = logging.getLogger("yorinetflix.fsub")


async def check_membership(
    bot: Bot,
    channel: str,
    user_id: int,
    fail_open: bool = False,
) -> tuple[bool, str]:
    """Check if a user is a member of the force-subscription channel.

    Returns:
        (is_member: bool, error_reason: str)
        error_reason is empty string on success, or a description of the failure.
    """
    if not channel:
        return True, ""

    try:
        member = await bot.get_chat_member(channel, user_id)
        is_member = member.status not in ("left", "kicked")
        return is_member, ""
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "chat not found" in err or "channel_private" in err:
            reason = "channel_not_found"
            log.error("FSUB channel '%s' not found or bot is not admin: %s", channel, e)
        elif "user_not_found" in err:
            reason = "user_not_found"
            log.warning("FSUB user %s not found in channel %s", user_id, channel)
        else:
            reason = "telegram_error"
            log.warning("FSUB TelegramBadRequest for %s: %s", user_id, e)
        if fail_open:
            return True, reason
        return False, reason
    except TelegramForbiddenError as e:
        reason = "bot_not_admin"
        log.error("FSUB bot lacks permission in channel '%s': %s", channel, e)
        if fail_open:
            return True, reason
        return False, reason
    except Exception as e:
        reason = "unexpected_error"
        log.exception("FSUB unexpected error for user %s: %s", user_id, e)
        if fail_open:
            return True, reason
        return False, reason