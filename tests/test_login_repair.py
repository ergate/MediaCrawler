import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from media_platform.xhs.extractor import XiaoHongShuExtractor, extract_initial_state
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.douyin.client import DouYinClient
from media_platform.douyin.exception import DataFetchError


def test_state_parser_preserves_literal_undefined_and_script_boundaries():
    html = '<script nonce="ok">window.__INITIAL_STATE__ = {"text":"undefined \\\"hello\\\"", "missing":undefined};</script><script>{"unrelated":true}</script>'
    state = extract_initial_state(html)
    assert state['text'] == 'undefined "hello"'
    assert state['missing'] is None


def test_multiline_note_and_missing_entry():
    html = '<script>window.__INITIAL_STATE__ = {\n"note":{"noteDetailMap":{"ABC_id":{"note":{"noteId":"ABC_id","desc":"undefined"}}}}};</script>'
    extractor = XiaoHongShuExtractor()
    assert extractor.extract_note_detail_from_html('ABC_id', html)['desc'] == 'undefined'
    assert extractor.extract_note_detail_from_html('missing', html) is None
    assert extract_initial_state('<script>unrelated()</script>') is None


def test_invalid_state_is_not_silently_an_empty_success():
    with pytest.raises(json.JSONDecodeError):
        extract_initial_state('<script>window.__INITIAL_STATE__={"x":broken}</script>')


@pytest.mark.asyncio
async def test_malformed_note_is_reported_without_losing_other_notes(monkeypatch):
    import asyncio
    import config
    from tools import utils
    from var import source_creator_var
    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = MagicMock()
    crawler.xhs_client.get_note_by_id = AsyncMock(return_value=None)
    crawler.xhs_client.get_note_by_id_from_html = AsyncMock(side_effect=json.JSONDecodeError('bad', 'x', 0))
    logger = MagicMock()
    monkeypatch.setattr(utils, 'logger', logger)
    monkeypatch.setattr(config, 'CRAWLER_MAX_SLEEP_SEC', 0)
    source_creator_var.set('creator-one')
    result = await crawler.get_note_detail_async_task('note-one', 'pc_feed', 'test', asyncio.Semaphore(1))
    assert result is None
    assert '[NoteParseError]' in logger.error.call_args.args[0]
    assert 'creator-one' in logger.error.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('body,status', [('Blocked by ArgusSecurityPlugin Uifid Not Found', 200), ('blocked', 200), ('denied', 403), ('limited', 429)])
async def test_security_denial_never_retries_another_transport(monkeypatch, body, status):
    import media_platform.douyin.client as module
    client = DouYinClient(headers={}, playwright_page=MagicMock(), cookie_dict={})
    response = MagicMock(text=body, status_code=status)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=MagicMock(request=AsyncMock(return_value=response)))
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(module, 'make_async_client', lambda **kwargs: context)
    fallback = MagicMock()
    monkeypatch.setattr(client, '_request_with_requests', fallback)
    with pytest.raises(DataFetchError, match='AccessRestricted'):
        await client.request('GET', 'https://www.douyin.com/test')
    fallback.assert_not_called()


def test_http_401_is_authentication_error_not_block():
    with pytest.raises(DataFetchError, match='Login required'):
        DouYinClient._check_access_response(MagicMock(text='unauthorized', status_code=401))
