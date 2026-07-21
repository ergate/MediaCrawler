# -*- coding: utf-8 -*-
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from tools.cdp_browser import CDPBrowserManager


@pytest.mark.asyncio
async def test_existing_browser_uses_discovered_websocket_url(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", True)
    monkeypatch.setattr(config, "BROWSER_LAUNCH_TIMEOUT", 60)

    manager = CDPBrowserManager()
    manager.debug_port = 9222
    manager._get_browser_websocket_url = AsyncMock(  # type: ignore[method-assign]
        return_value="ws://127.0.0.1:9222/devtools/browser/generated-id"
    )

    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.contexts = []

    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)

    await manager._connect_via_cdp(playwright)

    manager._get_browser_websocket_url.assert_awaited_once_with(9222)
    playwright.chromium.connect_over_cdp.assert_awaited_once_with(
        "ws://127.0.0.1:9222/devtools/browser/generated-id",
        timeout=60000,
    )


@pytest.mark.asyncio
async def test_existing_browser_falls_back_to_direct_websocket_url(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", True)
    monkeypatch.setattr(config, "BROWSER_LAUNCH_TIMEOUT", 60)

    manager = CDPBrowserManager()
    manager.debug_port = 9222
    manager._get_browser_websocket_url = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("json/version unavailable")
    )

    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.contexts = []

    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)

    await manager._connect_via_cdp(playwright)

    manager._get_browser_websocket_url.assert_awaited_once_with(9222)
    playwright.chromium.connect_over_cdp.assert_awaited_once_with(
        "ws://127.0.0.1:9222/devtools/browser",
        timeout=60000,
    )


@pytest.mark.asyncio
async def test_launched_browser_uses_discovered_websocket_url(monkeypatch):
    monkeypatch.setattr(config, "CDP_CONNECT_EXISTING", False)

    manager = CDPBrowserManager()
    manager.debug_port = 9223
    manager._get_browser_websocket_url = AsyncMock(  # type: ignore[method-assign]
        return_value="ws://localhost:9223/devtools/browser/generated-id"
    )

    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.contexts = []

    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)

    await manager._connect_via_cdp(playwright)

    manager._get_browser_websocket_url.assert_awaited_once_with(9223)
    playwright.chromium.connect_over_cdp.assert_awaited_once_with(
        "ws://localhost:9223/devtools/browser/generated-id"
    )


@pytest.mark.asyncio
async def test_websocket_discovery_ignores_environment_proxy(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "webSocketDebuggerUrl": (
                    "ws://127.0.0.1:9222/devtools/browser/generated-id"
                )
            }

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, timeout):
            captured["url"] = url
            captured["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr("tools.cdp_browser.httpx.AsyncClient", FakeClient)

    manager = CDPBrowserManager()
    ws_url = await manager._get_browser_websocket_url(9222)

    assert captured["client_kwargs"] == {"trust_env": False}
    assert captured["url"] == "http://127.0.0.1:9222/json/version"
    assert ws_url.endswith("/generated-id")
