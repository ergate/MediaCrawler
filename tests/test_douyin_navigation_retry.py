# -*- coding: utf-8 -*-
from unittest.mock import AsyncMock, MagicMock

import pytest

from media_platform.douyin.core import DouYinCrawler


@pytest.mark.asyncio
async def test_user_agent_read_retries_after_navigation(monkeypatch):
    monkeypatch.setenv("MEDIACRAWLER_DY_EVALUATE_RETRIES", "2")
    monkeypatch.setenv("MEDIACRAWLER_DY_EVALUATE_RETRY_DELAY", "0")

    crawler = DouYinCrawler()
    crawler.context_page = MagicMock()
    crawler.context_page.wait_for_load_state = AsyncMock()
    crawler.context_page.evaluate = AsyncMock(
        side_effect=[
            RuntimeError("Execution context was destroyed"),
            "Mozilla/5.0 test",
        ]
    )

    assert await crawler.get_browser_user_agent() == "Mozilla/5.0 test"
    assert crawler.context_page.evaluate.await_count == 2
