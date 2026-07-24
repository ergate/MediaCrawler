import os
import unittest
from unittest.mock import AsyncMock, patch

from media_platform.douyin.client import DouYinClient
from media_platform.xhs.client import XiaoHongShuClient


class CreatorHistoryPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_douyin_stops_after_first_page_containing_older_work(self) -> None:
        client = object.__new__(DouYinClient)
        recent = {"aweme_id": "recent", "create_time": 200}
        older = {"aweme_id": "older", "create_time": 99}
        client.get_user_aweme_posts = AsyncMock(
            side_effect=[
                {"has_more": 1, "max_cursor": "next", "aweme_list": [recent]},
                {"has_more": 1, "max_cursor": "later", "aweme_list": [older]},
            ]
        )
        callback = AsyncMock()

        with patch.dict(os.environ, {"MEDIACRAWLER_MIN_PUBLISH_TS": "100"}, clear=False):
            result = await client.get_all_user_aweme_posts(
                "creator",
                callback=callback,
                max_count=500,
            )

        self.assertEqual(result, [recent])
        self.assertEqual(client.get_user_aweme_posts.await_count, 2)
        self.assertEqual(callback.await_args_list[0].args[0], [recent])
        self.assertEqual(callback.await_args_list[1].args[0], [])

    async def test_xhs_stops_after_first_page_containing_older_work(self) -> None:
        client = object.__new__(XiaoHongShuClient)
        recent = {"note_id": "recent", "time": 200}
        older = {"note_id": "older", "time": 99}
        client.get_notes_by_creator = AsyncMock(
            side_effect=[
                {"has_more": True, "cursor": "next", "notes": [recent]},
                {"has_more": True, "cursor": "later", "notes": [older]},
            ]
        )
        callback = AsyncMock()

        with (
            patch.dict(os.environ, {"MEDIACRAWLER_MIN_PUBLISH_TS": "100"}, clear=False),
            patch("media_platform.xhs.client.config.CRAWLER_MAX_NOTES_COUNT", 500),
            patch("media_platform.xhs.client.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.get_all_notes_by_creator(
                "creator",
                crawl_interval=0,
                callback=callback,
            )

        self.assertEqual(result, [recent])
        self.assertEqual(client.get_notes_by_creator.await_count, 2)
        self.assertEqual(callback.await_args_list[0].args[0], [recent])
        self.assertEqual(callback.await_args_list[1].args[0], [])


if __name__ == "__main__":
    unittest.main()
