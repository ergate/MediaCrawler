import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from media_platform.kuaishou.core import KuaishouCrawler


class KuaishouCreatorIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_creator_failure_does_not_restart_or_block_remaining_creators(self) -> None:
        crawler = object.__new__(KuaishouCrawler)
        crawler._collect_creator_videos = AsyncMock(
            side_effect=[asyncio.TimeoutError(), None]
        )
        creators = ["https://kuaishou.example/stalled", "https://kuaishou.example/next"]

        with (
            patch("media_platform.kuaishou.core.config.KS_CREATOR_ID_LIST", creators),
            patch("media_platform.kuaishou.core.emit_creator_progress") as emit_progress,
            patch.dict(os.environ, {"MEDIACRAWLER_KS_CREATOR_TIMEOUT": "10"}, clear=False),
        ):
            await crawler.get_creators_and_videos()

        self.assertEqual(
            [call.args[0] for call in crawler._collect_creator_videos.await_args_list],
            creators,
        )
        self.assertEqual(
            [call.args[3] for call in emit_progress.call_args_list],
            ["started", "completed", "started", "completed"],
        )


if __name__ == "__main__":
    unittest.main()
