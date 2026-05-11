# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

from abc import ABC, abstractmethod
from typing import Optional


class BaseAPIProvider(ABC):
    """数据源抽象基类，所有 API 提供者实现此接口"""

    @abstractmethod
    async def check_connection(self) -> tuple[bool, str]:
        """检测 API 连通性，返回 (是否成功, 消息)"""
        ...

    @abstractmethod
    async def get_matches(
        self,
        status: Optional[str] = None,
        tournament_id: Optional[int] = None,
        begin_at_range: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> list[dict]:
        """
        获取比赛列表。
        status: running, not_started, finished
        begin_at_range: 日期范围字符串
        返回列表，每个元素至少包含:
          - id, name, status, begin_at
          - opponents: [{opponent: {id, name, image_url}}]
          - results: [{team_id, score}]
          - tournament: {id, name, tier, serie: {id, name, full_name}}
          - league: {id, name}
          - number_of_games
          - games: [{id, status, position, map: {name}, results: [{team_id, score}], winner: {id}}]
        """
        ...

    @abstractmethod
    async def get_match_detail(self, match_id: int) -> Optional[dict]:
        """获取单场比赛详情（含地图小分）"""
        ...

    @abstractmethod
    async def get_tournaments(
        self,
        tier: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> list[dict]:
        """获取赛事列表"""
        ...

    @abstractmethod
    async def get_match_events(self, match_id: int) -> list[dict]:
        """获取比赛击杀事件（用于五杀检测）"""
        ...

    @abstractmethod
    async def close(self):
        """关闭连接"""
        ...