# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

from __future__ import annotations

from typing import Optional

from astrbot.api import logger
from .base import BaseAPIProvider
from .hltv import HLTVAPI
from .pandascore import PandaScoreAPI


class MergedAPI(BaseAPIProvider):
    """合并数据源：PandaScore 做主力（队标/比分/赛事）+ HLTV 补充（live地图分/排名/地图池）"""

    def __init__(self, hltv: HLTVAPI, pandascore: PandaScoreAPI):
        self._hltv = hltv
        self._ps = pandascore

    async def check_connection(self) -> tuple[bool, str]:
        ps_ok, ps_msg = await self._ps.check_connection()
        hltv_ok, hltv_msg = await self._hltv.check_connection()
        parts = []
        parts.append(f"PandaScore: {'OK' if ps_ok else ps_msg}")
        parts.append(f"HLTV: {'OK' if hltv_ok else hltv_msg}")
        return ps_ok, " | ".join(parts)

    async def get_matches(self, status=None, tournament_id=None,
                          begin_at_range=None, page=1, per_page=50) -> list[dict]:
        """PandaScore 获取比赛（有队标有比分）"""
        return await self._ps.get_matches(
            status=status, tournament_id=tournament_id,
            begin_at_range=begin_at_range, page=page, per_page=per_page
        )

    async def get_match_detail(self, match_id: int) -> Optional[dict]:
        """HLTV stats（有地图池+小分），用 PandaScore 补队标"""
        detail = await self._hltv.get_match_detail(match_id)
        if detail:
            await self._fill_logos_async(detail)
            return detail
        return await self._ps.get_match_detail(match_id)

    async def get_tournaments(self, tier=None, page=1, per_page=20) -> list[dict]:
        return await self._ps.get_tournaments(tier=tier, page=page, per_page=per_page)

    async def get_match_events(self, match_id: int) -> list[dict]:
        return await self._ps.get_match_events(match_id)

    async def get_ranking(self, limit: int = 30) -> list[dict]:
        """HLTV 排名，用 PandaScore 补队标"""
        rankings = await self._hltv.get_ranking(limit=limit)
        for r in rankings:
            if not r.get("logo_url"):
                await self._fill_ranking_logo(r)
        return rankings

    async def get_live_matches(self) -> list[dict]:
        """PandaScore live（有队标有比分）+ HLTV live 补充当前地图分"""
        ps_live = await self._ps.get_matches(status="running", per_page=50)
        if ps_live:
            # 用 HLTV live 补充当前地图小分
            hltv_live = await self._hltv.get_live_matches()
            self._merge_live_scores(ps_live, hltv_live)
            return ps_live
        # fallback HLTV
        return await self._hltv.get_live_matches()

    async def close(self):
        await self._hltv.close()
        await self._ps.close()

    # ========== 内部方法 ==========

    async def _fill_logos_async(self, match: dict):
        """单场比赛补充队标"""
        for opp in match.get("opponents", []):
            team = opp.get("opponent", {})
            if not team.get("image_url") and team.get("name"):
                try:
                    data = await self._ps._request("/csgo/teams", {"search[name]": team["name"], "per_page": 1})
                    if isinstance(data, list) and data:
                        team["image_url"] = data[0].get("image_url") or ""
                except Exception:
                    pass

    async def _fill_ranking_logo(self, ranking: dict):
        """排名补充队标"""
        name = ranking.get("team_name", "")
        if not name:
            return
        try:
            data = await self._ps._request("/csgo/teams", {"search[name]": name, "per_page": 1})
            if isinstance(data, list) and data:
                ranking["logo_url"] = data[0].get("image_url") or ""
        except Exception:
            pass

    def _merge_live_scores(self, ps_matches: list[dict], hltv_matches: list[dict]):
        """将 HLTV live 的当前地图小分合并到 PandaScore 比赛数据"""
        if not hltv_matches:
            return
        # 按队名匹配
        hltv_map = {}
        for hm in hltv_matches:
            opps = hm.get("opponents", [])
            if len(opps) >= 2:
                n1 = (opps[0].get("opponent") or {}).get("name", "").lower()
                n2 = (opps[1].get("opponent") or {}).get("name", "").lower()
                key = f"{n1}|{n2}"
                hltv_map[key] = hm.get("_live_scores", {})

        for pm in ps_matches:
            opps = pm.get("opponents", [])
            if len(opps) >= 2:
                n1 = (opps[0].get("opponent") or {}).get("name", "").lower()
                n2 = (opps[1].get("opponent") or {}).get("name", "").lower()
                key = f"{n1}|{n2}"
                rev_key = f"{n2}|{n1}"
                scores = hltv_map.get(key) or hltv_map.get(rev_key)
                if scores:
                    pm["_live_scores"] = scores
