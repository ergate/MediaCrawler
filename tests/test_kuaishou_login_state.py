# -*- coding: utf-8 -*-
from unittest.mock import AsyncMock, MagicMock

import pytest

from media_platform.kuaishou.client import KuaiShouClient
from media_platform.kuaishou.exception import DataFetchError
from media_platform.kuaishou.login import has_kuaishou_auth_cookie


def test_anonymous_device_cookie_is_not_login_state():
    assert not has_kuaishou_auth_cookie({"did": "web_device_id"})
    assert has_kuaishou_auth_cookie({"passToken": "token"})


@pytest.mark.asyncio
async def test_pong_records_explicit_unauthenticated_response():
    client = KuaiShouClient(
        headers={},
        playwright_page=MagicMock(),
        cookie_dict={},
    )
    client.post = AsyncMock(
        side_effect=DataFetchError(
            [{"message": "No Login", "extensions": {"code": "UNAUTHENTICATED"}}]
        )
    )

    assert not await client.pong()
    assert client.last_pong_unauthenticated
