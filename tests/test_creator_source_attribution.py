from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from store.douyin._store_impl import DouyinJsonlStoreImplement
from store.kuaishou._store_impl import KuaishouJsonlStoreImplement
from store.xhs._store_impl import XhsJsonlStoreImplement
from var import source_creator_var


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("store_class", "writer_attribute"),
    [
        (DouyinJsonlStoreImplement, "file_writer"),
        (XhsJsonlStoreImplement, "writer"),
        (KuaishouJsonlStoreImplement, "writer"),
    ],
)
async def test_jsonl_content_keeps_original_creator_reference(store_class, writer_attribute: str) -> None:
    writer = MagicMock()
    writer.write_to_jsonl = AsyncMock()
    store = object.__new__(store_class)
    setattr(store, writer_attribute, writer)
    token = source_creator_var.set("https://creator.example/original")
    try:
        await store.store_content({"content_id": "content-1"})
    finally:
        source_creator_var.reset(token)

    saved_item = writer.write_to_jsonl.await_args.kwargs["item"]
    assert saved_item["source_creator"] == "https://creator.example/original"
    assert saved_item["content_id"] == "content-1"
