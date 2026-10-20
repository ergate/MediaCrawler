# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/extractor.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import json
import re
from typing import Dict, Optional

import humps
from parsel import Selector
from tools import utils


def extract_initial_state(html: str) -> Optional[Dict]:
    for script in Selector(text=html).xpath('//script/text()').getall():
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*', script)
        if not match:
            continue
        state = script[match.end():].lstrip()
        # Preserve quoted text; only JavaScript's bare undefined becomes null.
        state = re.sub(
            r'"(?:\\.|[^"\\])*"|(?<![\w$])undefined(?![\w$])',
            lambda token: 'null' if token.group(0) == 'undefined' else token.group(0),
            state,
        )
        try:
            value, _ = json.JSONDecoder().raw_decode(state)
        except json.JSONDecodeError as exc:
            # Keep syntax/position evidence without note text, cookies or tokens.
            masked = re.sub(r'"(?:\\.|[^"\\])*"', lambda token: '"' + 'x' * (len(token.group()) - 2) + '"', state)
            masked = re.sub(r'[\w$]', 'x', masked)
            literal = re.match(r'[A-Za-z_$][\w$]*', state[exc.pos:])
            literal = literal.group() if literal else ""
            literal = literal if literal in {"undefined", "void", "NaN", "Infinity", "new"} else "other"
            utils.logger.error("[XhsResponseDiagnostic] " + json.dumps({
                "stage": "html-initial-state", "error": "JSONDecodeError",
                "position": exc.pos, "line": exc.lineno, "column": exc.colno,
                "length": len(state), "literalAtError": literal,
                "syntax": masked[max(0, exc.pos - 30):exc.pos + 50],
            }))
            raise
        return value if isinstance(value, dict) else None
    return None


class XiaoHongShuExtractor:
    def __init__(self):
        pass

    def extract_note_detail_from_html(self, note_id: str, html: str) -> Optional[Dict]:
        """Extract note details from HTML

        Args:
            html (str): HTML string

        Returns:
            Dict: Note details dictionary
        """
        if "noteDetailMap" not in html:
            # Either a CAPTCHA appeared or the note doesn't exist
            return None

        state = extract_initial_state(html)
        if state:
            note = state.get("note") or {}
            entry = (note.get("noteDetailMap") or {}).get(note_id) or {}
            return humps.decamelize(entry["note"]) if entry.get("note") else None
        return None

    def extract_creator_info_from_html(self, html: str) -> Optional[Dict]:
        """Extract user information from HTML

        Args:
            html (str): HTML string

        Returns:
            Dict: User information dictionary
        """
        info = extract_initial_state(html)
        return (info.get("user") or {}).get("userPageData") if info else None
