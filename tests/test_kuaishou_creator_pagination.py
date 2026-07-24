import unittest
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


if __name__ == "__main__":
    unittest.main()
