import json

from tools import utils


def emit_creator_progress(
    platform: str,
    index: int,
    total: int,
    status: str,
    source: str,
) -> None:
    payload = {
        "platform": platform,
        "index": index,
        "total": total,
        "status": status,
        "source": source,
    }
    utils.logger.info(
        f"[CreatorProgress] {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )
