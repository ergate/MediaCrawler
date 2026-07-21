# -*- coding: utf-8 -*-
from unittest.mock import AsyncMock, MagicMock

import pytest

from media_platform.douyin.client import DouYinClient
from media_platform.douyin.login import DouYinLogin, has_douyin_auth_cookie


def make_login(page):
    return DouYinLogin(
        login_type="qrcode",
        browser_context=MagicMock(),
        context_page=page,
    )


@pytest.mark.asyncio
async def test_popup_does_not_click_when_new_login_panel_is_visible():
    page = MagicMock()
    login = make_login(page)
    login.visible_login_surface = AsyncMock(return_value="new login panel")

    await login.popup_login_dialog()

    page.locator.assert_not_called()


@pytest.mark.asyncio
async def test_qrcode_login_waits_for_second_verification(monkeypatch):
    monkeypatch.setenv("MEDIACRAWLER_DY_MANUAL_VERIFY_TIMEOUT", "1000")
    page = MagicMock()
    page.wait_for_selector = AsyncMock()
    login = make_login(page)
    login.visible_login_surface = AsyncMock(return_value="second verification")

    await login.login_by_qrcode()

    page.wait_for_selector.assert_awaited_once_with(
        "#uc-second-verify",
        state="hidden",
        timeout=1000,
    )


def test_stale_markers_are_not_douyin_login_state():
    assert not has_douyin_auth_cookie({"LOGIN_STATUS": "1"})
    assert has_douyin_auth_cookie({"sessionid_ss": "real-session"})


@pytest.mark.asyncio
async def test_pong_rejects_stale_local_storage_login_marker():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value={"HasUserLogin": "1"})
    browser_context = MagicMock()
    browser_context.cookies = AsyncMock(
        return_value=[{"name": "LOGIN_STATUS", "value": "1"}]
    )
    client = DouYinClient(
        headers={},
        playwright_page=page,
        cookie_dict={},
    )

    assert not await client.pong(browser_context)


@pytest.mark.asyncio
async def test_pong_accepts_real_session_cookie():
    page = MagicMock()
    browser_context = MagicMock()
    browser_context.cookies = AsyncMock(
        return_value=[{"name": "sessionid", "value": "real-session"}]
    )
    client = DouYinClient(
        headers={},
        playwright_page=page,
        cookie_dict={},
    )

    assert await client.pong(browser_context)
    page.evaluate.assert_not_called()
