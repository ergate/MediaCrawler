import unittest
import os
from unittest.mock import AsyncMock, patch

from media_platform.kuaishou.client import KuaiShouClient


class KuaishouCreatorPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_stops_immediately_when_creator_feed_is_empty(self) -> None:
        client = object.__new__(KuaiShouClient)
        client.get_video_by_creater = AsyncMock(
            return_value={
                "visionProfilePhotoList": {
                    "pcursor": "",
                    "feeds": [],
                }
            }
        )

        result = await client.get_all_videos_by_creator("creator-1", crawl_interval=0)

        self.assertEqual(result, [])
        client.get_video_by_creater.assert_awaited_once_with("creator-1", "")

    async def test_stops_when_creator_cursor_does_not_advance(self) -> None:
        client = object.__new__(KuaiShouClient)
        feed = {"photo": {"id": "photo-1", "timestamp": 1_750_000_000_000}}
        client.get_video_by_creater = AsyncMock(
            return_value={
                "visionProfilePhotoList": {
                    "pcursor": "",
                    "feeds": [feed],
                }
            }
        )
        callback = AsyncMock()

        with (
            patch("media_platform.kuaishou.client.config.CRAWLER_MAX_NOTES_COUNT", 5),
            patch("media_platform.kuaishou.client.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.get_all_videos_by_creator(
                "creator-1",
                crawl_interval=0,
                callback=callback,
            )

        self.assertEqual(result, [feed])
        client.get_video_by_creater.assert_awaited_once_with("creator-1", "")
        callback.assert_awaited_once_with([feed])

    async def test_stops_after_page_containing_work_before_topic_start(self) -> None:
        client = object.__new__(KuaiShouClient)
        recent = {"photo": {"id": "recent", "timestamp": 200_000}}
        older = {"photo": {"id": "older", "timestamp": 99}}
        client.get_video_by_creater = AsyncMock(
            side_effect=[
                {"visionProfilePhotoList": {"pcursor": "next", "feeds": [recent]}},
                {"visionProfilePhotoList": {"pcursor": "later", "feeds": [older]}},
            ]
        )
        callback = AsyncMock()

        with (
            patch.dict(os.environ, {"MEDIACRAWLER_MIN_PUBLISH_TS": "100"}, clear=False),
            patch("media_platform.kuaishou.client.config.CRAWLER_MAX_NOTES_COUNT", 500),
            patch("media_platform.kuaishou.client.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.get_all_videos_by_creator(
                "creator-1",
                crawl_interval=0,
                callback=callback,
            )

        self.assertEqual(result, [recent])
        self.assertEqual(client.get_video_by_creater.await_count, 2)
        callback.assert_awaited_once_with([recent])


if __name__ == "__main__":
    unittest.main()
