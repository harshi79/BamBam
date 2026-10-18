"""
YoriNetflix — Throttle middleware.

Prevents spam by rate-limiting per-user actions.
Uses a bounded dict with periodic cleanup to avoid memory leaks.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.utils.messaging import safe_answer


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate: float, max_entries: int = 10000):
        self.rate = rate
        self.max_entries = max_entries
        self.last: OrderedDict[int, float] = OrderedDict()

    def _cleanup(self):
        """Evict oldest entries if we exceed max_entries."""
        while len(self.last) > self.max_entries:
            self.last.popitem(last=False)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        now = time.monotonic()
        last = self.last.get(user.id, 0)
        if now - last < self.rate:
            if isinstance(event, Message):
                return None
            if isinstance(event, CallbackQuery):
                # Still acknowledge the press, otherwise the dropped button
                # keeps spinning and looks broken to the user.
                await safe_answer(event, "Please wait a moment before trying again.")
                return None

        self.last[user.id] = now
        self.last.move_to_end(user.id)
        self._cleanup()
        return await handler(event, data)
