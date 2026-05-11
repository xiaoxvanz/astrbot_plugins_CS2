# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

import asyncio
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from astrbot.api import logger
from ..cache.memory import MemoryCache
from .base import BaseAPIProvider


class HLTVAPI(BaseAPIProvider):
    """HLTV 数据源（通过 hltv-api 服务）"""

    MAX_RETRIES = 3

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache = MemoryCache()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, endpoint: str) -> Optional[dict | list]:
        cache_key = f"hltv:{endpoint}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{self._base_url}{endpoint}"
        session = await self._get_session()

        for attempt in range(self.MAX_RETRIES):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._cache.set(cache_key, data)
                        return data
                    elif resp.status == 429:
                        logger.warning(f"[HLTV] 限速，等待 5s")
                        await asyncio.sleep(5)
                    else:
                        logger.error(f"[HLTV] API 错误 {resp.status}: {url}")
                        return None
            except asyncio.TimeoutError:
                logger.warning(f"[HLTV] 超时 (尝试 {attempt + 1}/{self.MAX_RETRIES})")
            except Exception as e:
                logger.error(f"[HLTV] 请求异常: {e}")
                return None
        return None

    async def check_connection(self) -> tuple[bool, str]:
        if not self._base_url:
            return False, "未配置 HLTV API 地址"
        data = await self._request("/matches/today/")
        if data is None:
            return False, f"HLTV API 连接失败: {self._base_url}"
        if isinstance(data, dict) and "matches" in data:
            count = data.get("matchCount", 0)
            return True, f"HLTV API 连接成功, 今日 {count} 场比赛"
        return False, f"HLTV API 返回异常"

    async def get_matches(
        self,
        status: Optional[str] = None,
        tournament_id: Optional[int] = None,
        begin_at_range: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> list[dict]:
        # 获取今日比赛
        data = await self._request("/matches/today/")
        if not data or not isinstance(data, dict):
            return []

        raw_matches = data.get("matches", [])
        matches = []
        for m in raw_matches:
            match = self._normalize_match(m)
            # 按 status 过滤
            if status:
                hltv_status = match.get("status", "")
                if status == "running" and hltv_status != "live":
                    continue
                if status == "not_started" and hltv_status != "scheduled":
                    continue
                if status == "finished" and hltv_status != "ended":
                    continue
            matches.append(match)

        return matches[:per_page]

    async def get_match_detail(self, match_id: int) -> Optional[dict]:
        # HLTV API 没有单独的 match detail 端点
        # 从今日比赛中查找
        data = await self._request("/matches/today/")
        if not data or not isinstance(data, dict):
            return None
        for m in data.get("matches", []):
            if str(m.get("matchId")) == str(match_id):
                return self._normalize_match(m)
        return None

    async def get_tournaments(
        self,
        tier: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> list[dict]:
        # 从今日比赛中提取去重的赛事列表
        data = await self._request("/matches/today/")
        if not data or not isinstance(data, dict):
            return []

        seen = set()
        tournaments = []
        for m in data.get("matches", []):
            tid = m.get("tournamentId", "")
            if tid and tid not in seen:
                seen.add(tid)
                tournaments.append({
                    "id": tid,
                    "name": m.get("tournamentName", ""),
                    "image_url": m.get("tournamentLogo", ""),
                })
        return tournaments[:per_page]

    async def get_match_events(self, match_id: int) -> list[dict]:
        # HLTV API 没有击杀事件端点
        return []

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _normalize_match(self, raw: dict) -> dict:
        """将 HLTV 数据格式转为统一格式"""
        # 时间戳转换
        ts = raw.get("matchTimestamp", 0)
        begin_at = ""
        if ts:
            begin_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

        # 状态映射
        status_map = {"scheduled": "not_started", "live": "running", "ended": "finished"}
        raw_status = raw.get("matchStatus", "")
        status = status_map.get(raw_status, raw_status)

        # BO 类型
        match_type = raw.get("matchType", "")
        number_of_games = 0
        if match_type:
            import re
            m = re.search(r"(\d+)", match_type)
            if m:
                number_of_games = int(m.group(1))

        return {
            "id": raw.get("matchId"),
            "name": f"{raw.get('team1Name', 'TBD')} vs {raw.get('team2Name', 'TBD')}",
            "status": status,
            "begin_at": begin_at,
            "number_of_games": number_of_games,
            "opponents": [
                {
                    "opponent": {
                        "id": raw.get("team1Id"),
                        "name": raw.get("team1Name", "TBD"),
                        "image_url": raw.get("team1Logo", ""),
                    }
                },
                {
                    "opponent": {
                        "id": raw.get("team2Id"),
                        "name": raw.get("team2Name", "TBD"),
                        "image_url": raw.get("team2Logo", ""),
                    }
                },
            ],
            "results": [
                {"team_id": raw.get("team1Id"), "score": raw.get("team1Score", 0)},
                {"team_id": raw.get("team2Id"), "score": raw.get("team2Score", 0)},
            ],
            "tournament": {
                "id": raw.get("tournamentId"),
                "name": raw.get("tournamentName", ""),
                "tier": "",
                "serie": {
                    "id": raw.get("tournamentId"),
                    "name": raw.get("tournamentName", ""),
                    "full_name": raw.get("tournamentName", ""),
                },
                "league": {
                    "id": raw.get("tournamentId"),
                    "name": raw.get("tournamentName", ""),
                },
            },
            "league": {
                "id": raw.get("tournamentId"),
                "name": raw.get("tournamentName", ""),
            },
            "serie": {
                "id": raw.get("tournamentId"),
                "name": raw.get("tournamentName", ""),
                "full_name": raw.get("tournamentName", ""),
            },
            "games": [],
            "_source": "hltv",
            "_raw": raw,
        }