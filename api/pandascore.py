# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

import asyncio
from typing import Optional

import aiohttp

from astrbot.api import logger
from ..cache.memory import MemoryCache
from .base import BaseAPIProvider


class PandaScoreAPI(BaseAPIProvider):
    BASE_URL = "https://api.pandascore.co"
    MAX_RETRIES = 3

    def __init__(self, token: str):
        self._token = token
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache = MemoryCache()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                }
            )
        return self._session

    async def _request(self, endpoint: str, params: dict = None) -> Optional[list | dict]:
        cache_key = f"{endpoint}:{params}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}{endpoint}"
        session = await self._get_session()

        for attempt in range(self.MAX_RETRIES):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._cache.set(cache_key, data)
                        return data
                    elif resp.status == 403:
                        logger.warning(f"[CS2] API 403 无权限: {endpoint} (可能需要更高计划)")
                        return None
                    elif resp.status == 429:
                        wait = int(resp.headers.get("Retry-After", 5))
                        logger.warning(f"[CS2] API 限速，等待 {wait}s")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"[CS2] API 错误 {resp.status}: {url}")
                        return None
            except asyncio.TimeoutError:
                logger.warning(f"[CS2] API 超时 (尝试 {attempt + 1}/{self.MAX_RETRIES})")
            except Exception as e:
                logger.error(f"[CS2] API 请求异常: {e}")
                return None

        return None

    # ========== 比赛 ==========

    async def get_matches(
        self,
        status: Optional[str] = None,
        tournament_id: Optional[int] = None,
        begin_at_range: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> list[dict]:
        """
        获取 CS2 比赛列表。
        status: running, not_started, finished
        begin_at_range: "start,end" 格式的日期范围，如 "2024-01-01T00:00:00Z,2024-01-01T23:59:59Z"
        """
        params = {"page": page, "per_page": per_page, "sort": "begin_at"}
        if status:
            params["filter[status]"] = status
        if tournament_id:
            params["filter[tournament_id]"] = tournament_id
        if begin_at_range:
            params["range[begin_at]"] = begin_at_range

        data = await self._request("/csgo/matches", params)
        return data if isinstance(data, list) else []

    async def get_match_detail(self, match_id: int) -> Optional[dict]:
        """获取单场比赛详情"""
        data = await self._request(f"/csgo/matches/{match_id}")
        return data if isinstance(data, dict) else None

    # ========== 赛事 ==========

    async def get_tournaments(
        self,
        tier: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> list[dict]:
        """获取赛事列表。tier: s, a, b, major 等"""
        params = {"page": page, "per_page": per_page, "sort": "-begin_at"}
        if tier:
            params["filter[tier]"] = tier
        data = await self._request("/csgo/tournaments", params)
        return data if isinstance(data, list) else []

    # ========== 击杀事件 (需要 Pro Live Plan) ==========

    async def get_match_events(self, match_id: int) -> list[dict]:
        """
        获取比赛的击杀事件。
        注意: 需要 PandaScore Pro Live Plan。
        事件结构: { "type": "kill", "payload": { "killer": {...}, "killed": {...}, "round_number": N } }
        """
        # 先获取比赛详情拿到 games 列表
        match = await self.get_match_detail(match_id)
        if not match:
            return []

        all_events = []
        for game in match.get("games", []):
            game_id = game.get("id")
            if not game_id:
                continue
            events = await self._request(f"/csgo/games/{game_id}/events")
            if isinstance(events, list):
                all_events.extend(events)

        return all_events

    # ========== 实时比赛 ==========

    async def get_live_matches(self) -> list[dict]:
        """获取所有支持实时数据的比赛"""
        data = await self._request("/lives")
        if isinstance(data, list):
            return data
        return []

    async def check_connection(self) -> tuple[bool, str]:
        """检测 API 连通性，返回 (是否成功, 消息)"""
        if not self._token:
            return False, "未配置 PandaScore API Token"
        data = await self._request("/csgo/tournaments", {"per_page": 1})
        if data is None:
            return False, "API 请求失败，请检查 Token 是否正确"
        if isinstance(data, list):
            return True, f"API 连接成功"
        return False, f"API 返回异常: {type(data)}"

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()