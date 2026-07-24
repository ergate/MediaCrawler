# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/kuaishou/core.py
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


import asyncio
import os
# import random  # Removed as we now use fixed config.CRAWLER_MAX_SLEEP_SEC intervals
import time
from asyncio import Task
from typing import Dict, List, Optional, Tuple

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

import config
from base.base_crawler import AbstractCrawler
from model.m_kuaishou import VideoUrlInfo, CreatorUrlInfo
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import kuaishou as kuaishou_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from tools.creator_progress import emit_creator_progress
from var import comment_tasks_var, crawler_type_var, source_creator_var, source_keyword_var

from .client import KuaiShouClient
from .exception import DataFetchError
from .help import parse_video_info_from_url, parse_creator_info_from_url
from .login import KuaishouLogin, has_kuaishou_auth_cookie


class KuaishouCrawler(AbstractCrawler):
    context_page: Page
    ks_client: KuaiShouClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self):
        self.index_url = "https://www.kuaishou.com"
        self.cookie_urls = [self.index_url]
        self.user_agent = utils.get_user_agent()
        self.cdp_manager = None
        self.ip_proxy_pool = None  # Proxy IP pool, used for automatic proxy refresh

    @staticmethod
    def metric_value_present(value) -> bool:
        if value in (None, ""):
            return False
        return str(value).strip().lower() not in {"none", "null", "undefined"}

    async def start(self):
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(
                config.IP_PROXY_POOL_COUNT, enable_validate_ip=True
            )
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(
                ip_proxy_info
            )

        async with async_playwright() as playwright:
            # Select startup mode based on configuration
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[KuaishouCrawler] Launching browser using CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[KuaishouCrawler] Launching browser using standard mode")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium, None, self.user_agent, headless=config.HEADLESS
                )
                # stealth.min.js is a js script to prevent the website from detecting the crawler.
                await self.browser_context.add_init_script(path="libs/stealth.min.js")


            self.context_page = await self.browser_context.new_page()
            try:
                await self.context_page.goto(
                    f"{self.index_url}?isHome=1",
                    wait_until="domcontentloaded",
                    timeout=int(os.environ.get("MEDIACRAWLER_KS_PAGE_TIMEOUT", "15000")),
                )
            except Exception as ex:
                utils.logger.warning(
                    f"[KuaishouCrawler.start] Kuaishou home page navigation timed out, continue with current browser session: {ex}"
                )

            # Create a client to interact with the kuaishou website.
            self.ks_client = await self.create_ks_client(httpx_proxy_format)
            if not await self.ks_client.pong():
                await self.ks_client.update_cookies(
                    browser_context=self.browser_context,
                    urls=self.cookie_urls,
                )
                if (
                    not self.ks_client.last_pong_unauthenticated
                    and await self.browser_login_state_looks_valid()
                ):
                    utils.logger.info(
                        "[KuaishouCrawler.start] Pong failed, but browser login state looks valid; continue with current session."
                    )
                else:
                    if self.ks_client.last_pong_unauthenticated:
                        utils.logger.info(
                            "[KuaishouCrawler.start] API explicitly reported no login; start interactive login."
                        )
                    login_obj = KuaishouLogin(
                        login_type=config.LOGIN_TYPE,
                        login_phone=httpx_proxy_format,
                        browser_context=self.browser_context,
                        context_page=self.context_page,
                        cookie_str=config.COOKIES,
                    )
                    await login_obj.begin()
                    await self.ks_client.update_cookies(
                        browser_context=self.browser_context,
                        urls=self.cookie_urls,
                    )

            if self.context_page.is_closed():
                raise RuntimeError("Kuaishou browser readiness check failed: page is closed")
            await self.context_page.wait_for_load_state(
                "domcontentloaded",
                timeout=int(os.environ.get("MEDIACRAWLER_BROWSER_READY_TIMEOUT", "15000")),
            )
            utils.logger.info("[BrowserReady] Kuaishou browser, page, and login flow are ready; collection may start")

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for videos and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_videos()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their videos and comments
                await self.get_creators_and_videos()
            else:
                pass

            utils.logger.info("[KuaishouCrawler.start] Kuaishou Crawler finished ...")

    async def search(self):
        utils.logger.info("[KuaishouCrawler.search] Begin search kuaishou keywords")
        requested_count = max(int(config.CRAWLER_MAX_NOTES_COUNT), 1)
        start_page = config.START_PAGE
        for keyword in config.KEYWORDS.split(","):
            search_session_id = ""
            collected_count = 0
            source_keyword_var.set(keyword)
            utils.logger.info(
                f"[KuaishouCrawler.search] Current search keyword: {keyword}"
            )
            page = 1
            while collected_count < requested_count:
                if page < start_page:
                    utils.logger.info(f"[KuaishouCrawler.search] Skip page: {page}")
                    page += 1
                    continue
                utils.logger.info(
                    f"[KuaishouCrawler.search] search kuaishou keyword: {keyword}, page: {page}"
                )
                video_id_list: List[str] = []
                videos_res = await self.ks_client.search_info_by_keyword(
                    keyword=keyword,
                    pcursor=str(page),
                    search_session_id=search_session_id,
                )
                if not videos_res:
                    utils.logger.error(
                        f"[KuaishouCrawler.search] search info by keyword:{keyword} not found data"
                    )
                    break

                vision_search_photo: Dict = videos_res.get("visionSearchPhoto")
                if vision_search_photo.get("result") != 1:
                    utils.logger.error(
                        f"[KuaishouCrawler.search] search info by keyword:{keyword} not found data "
                    )
                    break
                search_session_id = vision_search_photo.get("searchSessionId", "")
                feeds = vision_search_photo.get("feeds") or []
                remaining = requested_count - collected_count
                selected_feeds = feeds[:remaining]
                for video_detail in selected_feeds:
                    video_id = video_detail.get("photo", {}).get("id")
                    if video_id:
                        video_id_list.append(video_id)
                    await kuaishou_store.update_kuaishou_video(video_item=video_detail)
                collected_count += len(selected_feeds)

                # batch fetch video comments
                page += 1

                # Sleep after page navigation
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[KuaishouCrawler.search] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after page {page-1}")

                await self.batch_get_video_comments(video_id_list)
                if not feeds:
                    break

    async def get_specified_videos(self):
        """Get the information and comments of the specified post"""
        utils.logger.info("[KuaishouCrawler.get_specified_videos] Parsing video URLs...")
        video_ids = []
        for video_url in config.KS_SPECIFIED_ID_LIST:
            try:
                video_info = parse_video_info_from_url(video_url)
                video_ids.append(video_info.video_id)
                utils.logger.info(f"Parsed video ID: {video_info.video_id} from {video_url}")
            except ValueError as e:
                utils.logger.error(f"Failed to parse video URL: {e}")
                continue

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_video_info_task(video_id=video_id, semaphore=semaphore)
            for video_id in video_ids
        ]
        video_details = await asyncio.gather(*task_list)
        for video_detail in video_details:
            if video_detail is not None:
                await kuaishou_store.update_kuaishou_video(video_detail)
        await self.batch_get_video_comments(video_ids)

    async def get_video_info_task(
        self, video_id: str, semaphore: asyncio.Semaphore
    ) -> Optional[Dict]:
        """Get video detail task"""
        async with semaphore:
            try:
                result = await self.ks_client.get_video_info(video_id)

                # Sleep after fetching video details
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[KuaishouCrawler.get_video_info_task] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching video details {video_id}")

                utils.logger.info(
                    f"[KuaishouCrawler.get_video_info_task] Get video_id:{video_id} info result: {result} ..."
                )
                return result.get("visionVideoDetail")
            except DataFetchError as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_video_info_task] Get video detail error: {ex}"
                )
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_video_info_task] have not fund video detail video_id:{video_id}, err: {ex}"
                )
                return None
            except Exception as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_video_info_task] Skip video_id:{video_id} after detail request error: {ex}"
                )
                return None

    async def batch_get_video_comments(self, video_id_list: List[str]):
        """
        batch get video comments
        :param video_id_list:
        :return:
        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(
                f"[KuaishouCrawler.batch_get_video_comments] Crawling comment mode is not enabled"
            )
            return

        utils.logger.info(
            f"[KuaishouCrawler.batch_get_video_comments] video ids:{video_id_list}"
        )
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for video_id in video_id_list:
            task = asyncio.create_task(
                self.get_comments(video_id, semaphore), name=video_id
            )
            task_list.append(task)

        comment_tasks_var.set(task_list)
        await asyncio.gather(*task_list)

    async def get_comments(self, video_id: str, semaphore: asyncio.Semaphore):
        """
        get comment for video id
        :param video_id:
        :param semaphore:
        :return:
        """
        async with semaphore:
            try:
                utils.logger.info(
                    f"[KuaishouCrawler.get_comments] begin get video_id: {video_id} comments ..."
                )

                # Sleep before fetching comments
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[KuaishouCrawler.get_comments] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds before fetching comments for video {video_id}")

                await self.ks_client.get_video_all_comments(
                    photo_id=video_id,
                    crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                    callback=kuaishou_store.batch_update_ks_video_comments,
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
            except DataFetchError as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_comments] get video_id: {video_id} comment error: {ex}"
                )
            except Exception as e:
                utils.logger.error(
                    f"[KuaishouCrawler.get_comments] may be been blocked, err:{e}"
                )
                # use time.sleeep block main coroutine instead of asyncio.sleep and cacel running comment task
                # maybe kuaishou block our request, we will take a nap and update the cookie again
                current_running_tasks = comment_tasks_var.get()
                for task in current_running_tasks:
                    task.cancel()
                time.sleep(20)
                await self.context_page.goto(f"{self.index_url}?isHome=1")
                await self.ks_client.update_cookies(
                    browser_context=self.browser_context,
                    urls=self.cookie_urls,
                )

    async def get_comment_count_task(
        self, video_id: str, semaphore: asyncio.Semaphore
    ) -> Optional[int]:
        """Fetch only comment total without storing comment rows."""
        async with semaphore:
            try:
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                count = await self.ks_client.get_video_comment_count(video_id)
                utils.logger.info(
                    f"[KuaishouCrawler.get_comment_count_task] video_id:{video_id}, comment_count:{count}"
                )
                return count
            except Exception as ex:
                utils.logger.warning(
                    f"[KuaishouCrawler.get_comment_count_task] Skip comment count for video_id:{video_id}, error:{ex}"
                )
                return None

    async def create_ks_client(self, httpx_proxy: Optional[str]) -> KuaiShouClient:
        """Create ks client"""
        utils.logger.info(
            "[KuaishouCrawler.create_ks_client] Begin create kuaishou API client ..."
        )
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            self.browser_context,
            urls=self.cookie_urls,
        )
        ks_client_obj = KuaiShouClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": self.index_url,
                "Referer": self.index_url,
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,  # Pass proxy pool for automatic refresh
        )
        return ks_client_obj

    async def browser_login_state_looks_valid(self) -> bool:
        """Use the attached browser session as a fallback when the pong API is slow."""
        try:
            _, cookie_dict = await utils.convert_browser_context_cookies(
                self.browser_context,
                urls=self.cookie_urls,
            )
            return has_kuaishou_auth_cookie(cookie_dict)
        except Exception as ex:
            utils.logger.warning(
                f"[KuaishouCrawler.browser_login_state_looks_valid] Could not verify browser login state: {ex}"
            )
            return False

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info(
            "[KuaishouCrawler.launch_browser] Begin create browser context ..."
        )
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM
            )  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                channel="chrome",  # Use system's stable Chrome version
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy, channel="chrome")  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        Launch browser using CDP mode
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # Display browser information
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[KuaishouCrawler] CDP browser info: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(
                f"[KuaishouCrawler] CDP mode launch failed, fallback to standard mode: {e}"
            )
            # Fallback to standard mode
            chromium = playwright.chromium
            return await self.launch_browser(
                chromium, playwright_proxy, user_agent, headless
            )

    async def get_creators_and_videos(self) -> None:
        """Get creator's videos and retrieve their comment information."""
        utils.logger.info(
            "[KuaiShouCrawler.get_creators_and_videos] Begin get kuaishou creators"
        )
        creator_urls = config.KS_CREATOR_ID_LIST
        creator_timeout = max(
            10.0,
            float(os.environ.get("MEDIACRAWLER_KS_CREATOR_TIMEOUT") or "180"),
        )
        for creator_index, creator_url in enumerate(creator_urls, start=1):
            source_creator_var.set(creator_url)
            emit_creator_progress("ks", creator_index, len(creator_urls), "started", creator_url)
            try:
                await asyncio.wait_for(
                    self._collect_creator_videos(creator_url),
                    timeout=creator_timeout,
                )
            except asyncio.TimeoutError:
                utils.logger.error(
                    f"[KuaiShouCrawler.get_creators_and_videos] Creator timed out "
                    f"after {creator_timeout:g}s, skip: {creator_url}"
                )
            except Exception as e:
                utils.logger.error(
                    f"[KuaiShouCrawler.get_creators_and_videos] Creator failed, "
                    f"skip: {creator_url}, error: {e}"
                )
            finally:
                emit_creator_progress("ks", creator_index, len(creator_urls), "completed", creator_url)

    async def _collect_creator_videos(self, creator_url: str) -> None:
        """Collect one creator without affecting the shared browser session."""
        creator_info: CreatorUrlInfo = parse_creator_info_from_url(creator_url)
        utils.logger.info(
            f"[KuaiShouCrawler.get_creators_and_videos] Parse creator URL info: {creator_info}"
        )
        user_id = creator_info.user_id

        creator = await self.ks_client.get_creator_info(user_id=user_id)
        if creator:
            await kuaishou_store.save_creator(user_id, creator=creator)

        all_video_list = await self.ks_client.get_all_videos_by_creator(
            user_id=user_id,
            crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
            callback=self.fetch_creator_video_detail,
        )
        video_ids = [
            video_item.get("photo", {}).get("id") for video_item in all_video_list
        ]
        await self.batch_get_video_comments(video_ids)

    async def fetch_creator_video_detail(self, video_list: List[Dict]):
        """
        Concurrently obtain the specified post list and save the data
        """
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_video_info_task(post_item.get("photo", {}).get("id"), semaphore)
            for post_item in video_list
        ]

        list_photo_by_id = {
            post_item.get("photo", {}).get("id"): post_item.get("photo", {})
            for post_item in video_list
        }
        video_details = await asyncio.gather(*task_list)
        for video_detail in video_details:
            if video_detail is not None:
                photo_info = video_detail.get("photo", {})
                list_photo = list_photo_by_id.get(photo_info.get("id"), {})
                if (
                    not self.metric_value_present(photo_info.get("commentCount"))
                    and self.metric_value_present(list_photo.get("commentCount"))
                ):
                    photo_info["commentCount"] = list_photo.get("commentCount")
                if (
                    os.environ.get(
                        "MEDIACRAWLER_KS_COMMENT_COUNT_FALLBACK", ""
                    ).lower()
                    in {"1", "true", "yes"}
                    and not self.metric_value_present(photo_info.get("commentCount"))
                ):
                    comment_count = await self.get_comment_count_task(
                        photo_info.get("id"), semaphore
                    )
                    if comment_count is not None:
                        photo_info["commentCount"] = comment_count
                await kuaishou_store.update_kuaishou_video(video_detail)

    async def close(self):
        """Close browser context"""
        # If using CDP mode, need special handling
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[KuaishouCrawler.close] Browser context closed ...")
