# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional, Union

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
                    elif resp.status == 404:
                        logger.warning(f"[HLTV] 端点不存在: {endpoint}")
                        return None
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
        return False, "HLTV API 返回异常"

    # ========== 比赛 ==========

    async def get_matches(self, status=None, tournament_id=None,
                          begin_at_range=None, page=1, per_page=50) -> list[dict]:
        data = await self._request("/matches/today/")
        if not data or not isinstance(data, dict):
            return []

        raw_matches = data.get("matches", [])
        matches = []
        for m in raw_matches:
            match = self._normalize_match(m)
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
        """获取比赛详情（含地图池和地图小分）"""
        # 先尝试 stats 端点（有地图池和每张地图比分）
        stats = await self._request(f"/matches/stats/{match_id}")
        if stats and isinstance(stats, dict):
            return self._normalize_match_stats(stats, match_id)

        # fallback: 从今日比赛中查找
        data = await self._request("/matches/today/")
        if not data or not isinstance(data, dict):
            return None
        for m in data.get("matches", []):
            if str(m.get("matchId")) == str(match_id):
                return self._normalize_match(m)
        return None

    def _normalize_match_stats(self, stats: dict, match_id: int) -> dict:
        """将 /matches/stats/{id} 数据转为统一格式"""
        info = stats.get("stats", {}).get("match_info", {})
        team1 = info.get("team1", {})
        team2 = info.get("team2", {})
        event = info.get("event", {})

        # 地图池
        map_pool = stats.get("stats", {}).get("map_pool", [])

        # 每张地图比分
        maps = []
        for ms in stats.get("stats", {}).get("map_stats", []):
            t1s = ms.get("team1_score", {}).get("score")
            t2s = ms.get("team2_score", {}).get("score")
            maps.append({
                "map_name": ms.get("map_name", "Unknown"),
                "team1_score": int(t1s) if t1s and t1s.isdigit() else 0,
                "team2_score": int(t2s) if t2s and t2s.isdigit() else 0,
            })

        return {
            "id": match_id,
            "name": f"{team1.get('name', 'TBD')} vs {team2.get('name', 'TBD')}",
            "status": "live" if stats.get("is_live") else "finished",
            "begin_at": "",
            "number_of_games": len(map_pool) or len(maps),
            "opponents": [
                {"opponent": {"id": team1.get("id"), "name": team1.get("name", "TBD"), "image_url": ""}},
                {"opponent": {"id": team2.get("id"), "name": team2.get("name", "TBD"), "image_url": ""}},
            ],
            "results": [
                {"team_id": team1.get("id"), "score": int(team1.get("score", 0)) if str(team1.get("score", "0")).isdigit() else 0},
                {"team_id": team2.get("id"), "score": int(team2.get("score", 0)) if str(team2.get("score", "0")).isdigit() else 0},
            ],
            "tournament": {
                "id": event.get("id"),
                "name": event.get("name", ""),
                "tier": "",
                "serie": {"id": event.get("id"), "name": event.get("name", ""), "full_name": event.get("name", "")},
                "league": {"id": event.get("id"), "name": event.get("name", "")},
            },
            "league": {"id": event.get("id"), "name": event.get("name", "")},
            "serie": {"id": event.get("id"), "name": event.get("name", ""), "full_name": event.get("name", "")},
            "games": [],
            "map_pool": map_pool,
            "map_details": maps,
        }

    # ========== 赛事 ==========

    async def get_tournaments(self, tier=None, page=1, per_page=20) -> list[dict]:
        # HLTV API 没有赛事列表端点，返回空
        return []

    async def search_events(self, query: str) -> list[dict]:
        """搜索赛事"""
        data = await self._request(f"/events/search/{query}")
        if not data or not isinstance(data, dict):
            return []
        results = data.get("results", [])
        return results if isinstance(results, list) else []

    # ========== 击杀事件 ==========

    async def get_match_events(self, match_id: int) -> list[dict]:
        return []

    # ========== 排名 ==========

    async def get_ranking(self, limit: int = 30) -> list[dict]:
        data = await self._request(f"/ranking/stats/start-placement/1/end-placement/{limit}")
        if not data or not isinstance(data, dict):
            return []
        ranking = data.get("rankingStats", [])
        date = data.get("rankingDate", "")
        result = []
        for r in ranking:
            result.append({
                "placement": r.get("placement", 0),
                "team_name": r.get("teamName", ""),
                "team_id": r.get("teamId", ""),
                "points": r.get("hltvPoints", 0),
                "logo_url": r.get("logoUrl") or "",
                "ranking_date": date,
            })
        return result[:limit]

    # ========== Live ==========

    async def get_live_matches(self) -> list[dict]:
        data = await self._request("/matches/live")
        if not data or not isinstance(data, dict):
            return []
        raw = data.get("liveMatchs", [])
        matches = []
        for m in raw:
            team_a = m.get("teamA") or "TBD"
            team_b = m.get("teamB") or "TBD"
            logo_a = m.get("teamALogo") or ""
            logo_b = m.get("teamBLogo") or ""
            t1_map = m.get("teamAMapScore") or 0
            t2_map = m.get("teamBMapScore") or 0
            t1_cur = m.get("teamACurrentMapScore") or 0
            t2_cur = m.get("teamBCurrentMapScore") or 0

            match_type = m.get("matchType") or ""
            number_of_games = 0
            if match_type:
                g = re.search(r"(\d+)", match_type)
                if g:
                    number_of_games = int(g.group(1))

            matches.append({
                "id": m.get("matchId"),
                "name": f"{team_a} vs {team_b}",
                "status": "running",
                "begin_at": "",
                "number_of_games": number_of_games,
                "opponents": [
                    {"opponent": {"id": m.get("teamAId"), "name": team_a, "image_url": logo_a}},
                    {"opponent": {"id": m.get("teamBId"), "name": team_b, "image_url": logo_b}},
                ],
                "results": [
                    {"team_id": m.get("teamAId"), "score": t1_map},
                    {"team_id": m.get("teamBId"), "score": t2_map},
                ],
                "tournament": {
                    "id": m.get("tournamentId"),
                    "name": m.get("tournamentName") or "",
                    "tier": "",
                    "serie": {"id": m.get("tournamentId"), "name": m.get("tournamentName") or "", "full_name": m.get("tournamentName") or ""},
                    "league": {"id": m.get("tournamentId"), "name": m.get("tournamentName") or ""},
                },
                "league": {"id": m.get("tournamentId"), "name": m.get("tournamentName") or ""},
                "serie": {"id": m.get("tournamentId"), "name": m.get("tournamentName") or "", "full_name": m.get("tournamentName") or ""},
                "games": [],
                "_live_scores": {
                    "team1_current": t1_cur,
                    "team2_current": t2_cur,
                },
            })
        return matches

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ========== 数据标准化 ==========

    def _normalize_match(self, raw: dict) -> dict:
        ts = raw.get("matchTimestamp", 0)
        begin_at = ""
        if ts:
            begin_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

        status_map = {"scheduled": "not_started", "live": "running", "ended": "finished"}
        raw_status = raw.get("matchStatus") or ""
        status = status_map.get(raw_status, raw_status)

        match_type = raw.get("matchType") or ""
        number_of_games = 0
        if match_type:
            m = re.search(r"(\d+)", match_type)
            if m:
                number_of_games = int(m.group(1))

        team1 = raw.get("team1Name") or "TBD"
        team2 = raw.get("team2Name") or "TBD"
        logo1 = raw.get("team1Logo") or ""
        logo2 = raw.get("team2Logo") or ""

        t1_score = raw.get("team1Score")
        t2_score = raw.get("team2Score")
        results = []
        if t1_score is not None and t2_score is not None:
            results = [
                {"team_id": raw.get("team1Id"), "score": t1_score},
                {"team_id": raw.get("team2Id"), "score": t2_score},
            ]

        return {
            "id": raw.get("matchId"),
            "name": f"{team1} vs {team2}",
            "status": status,
            "begin_at": begin_at,
            "number_of_games": number_of_games,
            "opponents": [
                {"opponent": {"id": raw.get("team1Id"), "name": team1, "image_url": logo1}},
                {"opponent": {"id": raw.get("team2Id"), "name": team2, "image_url": logo2}},
            ],
            "results": results,
            "tournament": {
                "id": raw.get("tournamentId"),
                "name": raw.get("tournamentName") or "",
                "tier": "",
                "serie": {"id": raw.get("tournamentId"), "name": raw.get("tournamentName") or "", "full_name": raw.get("tournamentName") or ""},
                "league": {"id": raw.get("tournamentId"), "name": raw.get("tournamentName") or ""},
            },
            "league": {"id": raw.get("tournamentId"), "name": raw.get("tournamentName") or ""},
            "serie": {"id": raw.get("tournamentId"), "name": raw.get("tournamentName") or "", "full_name": raw.get("tournamentName") or ""},
            "games": [],
        }
