"""Tests for public and private force-subscription channel checks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.subscriptions import check_membership


@pytest.mark.asyncio
async def test_private_channel_id_is_passed_to_telegram_as_integer():
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
    )

    is_member, error = await check_membership(bot, "-1003932303159", 12345)

    assert (is_member, error) == (True, "")
    bot.get_chat_member.assert_awaited_once_with(-1003932303159, 12345)


@pytest.mark.asyncio
async def test_public_channel_username_is_left_unchanged():
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
    )

    is_member, error = await check_membership(bot, "mychannel", 12345)

    assert (is_member, error) == (True, "")
    bot.get_chat_member.assert_awaited_once_with("mychannel", 12345)


@pytest.mark.asyncio
async def test_restricted_user_only_passes_when_still_a_member():
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(status="restricted", is_member=False),
        ),
    )

    is_member, error = await check_membership(bot, "-1003932303159", 12345)

    assert (is_member, error) == (False, "")
