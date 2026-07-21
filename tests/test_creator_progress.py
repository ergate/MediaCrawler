import json
from unittest.mock import MagicMock

from tools.creator_progress import emit_creator_progress


def test_creator_progress_is_structured_log_event(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr("tools.creator_progress.utils.logger", logger)

    emit_creator_progress(
        "dy",
        2,
        151,
        "started",
        "https://www.douyin.com/user/example",
    )

    message = logger.info.call_args.args[0]
    payload = json.loads(message.split("[CreatorProgress] ", 1)[1])
    assert payload == {
        "platform": "dy",
        "index": 2,
        "total": 151,
        "status": "started",
        "source": "https://www.douyin.com/user/example",
    }
