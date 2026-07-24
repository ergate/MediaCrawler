import unittest
from unittest.mock import AsyncMock, patch

from media_platform.kuaishou.core import KuaishouCrawler


class KuaishouCreatorFeedFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_saves_profile_feed_when_video_detail_request_fails(self) -> None:
        crawler = object.__new__(KuaishouCrawler)
        crawler.get_video_info_task = AsyncMock(return_value=None)
        profile_feed = {
            "photo": {
                "id": "photo-1",
                "caption": "主页列表中的作品",
                "timestamp": 1_750_000_000_000,
                "realLikeCount": 12,
            },
            "author": {"id": "creator-1", "name": "账号"},
        }

        with (
            patch(
                "media_platform.kuaishou.core.kuaishou_store.update_kuaishou_video",
                new_callable=AsyncMock,
            ) as save_video,
            patch.dict(
                "os.environ",
                {"MEDIACRAWLER_KS_COMMENT_COUNT_FALLBACK": "false"},
                clear=False,
            ),
        ):
            await crawler.fetch_creator_video_detail([profile_feed])

        save_video.assert_awaited_once_with(profile_feed)


if __name__ == "__main__":
    unittest.main()
