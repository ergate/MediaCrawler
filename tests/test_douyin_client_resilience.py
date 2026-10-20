# -*- coding: utf-8 -*-
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests

import config
from media_platform.douyin.client import DouYinClient
from media_platform.douyin.core import DouYinCrawler
from media_platform.douyin.exception import DataFetchError


def _client(page=None):
    return DouYinClient(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/150.0.7871.129 Safari/537.36"
            ),
            "Cookie": "sessionid=test",
            "Origin": "https://www.douyin.com/",
            "Referer": "https://www.douyin.com/",
        },
        playwright_page=page or MagicMock(),
        cookie_dict={"msToken": "cookie-token"},
    )


class _Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def json(self):
        import json

        return json.loads(self.text)


class _AsyncClientContext:
    def __init__(self, response):
        self.client = MagicMock()
        self.client.request = AsyncMock(return_value=response)

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_empty_httpx_response_retries_with_requests(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        "media_platform.douyin.client.make_async_client",
        lambda **_kwargs: _AsyncClientContext(_Response("")),
    )
    fallback = MagicMock(return_value=_Response('{"aweme_list": [{"aweme_id": "1"}]}'))
    monkeypatch.setattr(client, "_request_with_requests", fallback)

    result = await client.request("GET", "https://www.douyin.com/test", params={})

    assert result["aweme_list"][0]["aweme_id"] == "1"
    fallback.assert_called_once()


@pytest.mark.asyncio
async def test_request_signature_uses_active_windows_browser(monkeypatch):
    page = MagicMock()
    page.evaluate = AsyncMock(
        side_effect=[
            {"xmst": "storage-token", "webid": "browser-webid"},
            {
                "userAgent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/150.0.7871.129 Safari/537.36"
                ),
                "language": "zh-CN",
                "platform": "Win32",
                "hardwareConcurrency": 16,
                "deviceMemory": 8,
                "screenWidth": 1920,
                "screenHeight": 1080,
            },
        ]
    )
    client = _client(page)
    signer = AsyncMock(return_value="signed-value")
    monkeypatch.setattr("media_platform.douyin.client.get_a_bogus", signer)
    params = {"sec_user_id": "sec-user"}

    await client._DouYinClient__process_req_params(  # type: ignore[attr-defined]
        "/aweme/v1/web/user/profile/other/",
        params,
        client.headers,
    )

    assert params["browser_platform"] == "Win32"
    assert params["browser_version"] == "150.0.7871.129"
    assert params["os_name"] == "Windows"
    assert params["webid"] == "browser-webid"
    assert params["msToken"] == "storage-token"
    assert params["a_bogus"] == "signed-value"


@pytest.mark.asyncio
async def test_requests_fallback_failure_is_data_fetch_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        "media_platform.douyin.client.make_async_client",
        lambda **_kwargs: _AsyncClientContext(_Response("")),
    )
    monkeypatch.setattr(
        client,
        "_request_with_requests",
        MagicMock(side_effect=requests.ConnectionError("connection reset")),
    )

    with pytest.raises(DataFetchError, match="requests transport failed"):
        await client.request("GET", "https://www.douyin.com/test", params={})


@pytest.mark.asyncio
async def test_creator_requests_use_creator_referer():
    client = _client()
    client.get = AsyncMock(return_value={})

    await client.get_user_info("sec-user")
    await client.get_user_aweme_posts("sec-user")

    for call in client.get.await_args_list:
        assert call.kwargs["headers"]["Referer"] == "https://www.douyin.com/user/sec-user"


@pytest.mark.asyncio
async def test_creator_posts_respect_max_count():
    client = _client()
    client.get_user_aweme_posts = AsyncMock(
        return_value={
            "has_more": 1,
            "max_cursor": "next",
            "aweme_list": [{"aweme_id": str(index)} for index in range(18)],
        }
    )
    callback = AsyncMock()

    result = await client.get_all_user_aweme_posts("sec-user", callback, max_count=5)

    assert len(result) == 5
    assert len(callback.await_args.args[0]) == 5
    client.get_user_aweme_posts.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_failure_still_collects_creator_posts(monkeypatch):
    crawler = DouYinCrawler()
    crawler.context_page = MagicMock()
    crawler.context_page.goto = AsyncMock()
    crawler.browser_context = MagicMock()
    crawler.dy_client = MagicMock()
    crawler.dy_client.update_cookies = AsyncMock()
    crawler.dy_client.get_user_info = AsyncMock(side_effect=DataFetchError("empty response"))
    crawler.dy_client.get_all_user_aweme_posts = AsyncMock(return_value=[])
    crawler.batch_get_note_comments = AsyncMock()
    monkeypatch.setattr(
        config,
        "DY_CREATOR_ID_LIST",
        ["https://www.douyin.com/user/MS4wLjABAAAA-test"],
    )
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 5)

    await crawler.get_creators_and_videos()

    crawler.context_page.goto.assert_awaited_once()
    crawler.dy_client.update_cookies.assert_awaited_once()
    crawler.dy_client.get_all_user_aweme_posts.assert_awaited_once_with(
        sec_user_id="MS4wLjABAAAA-test",
        callback=crawler.fetch_creator_video_detail,
        max_count=5,
    )
