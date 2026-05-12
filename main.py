# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

import asyncio
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .api import PandaScoreAPI, HLTVAPI, MergedAPI, BaseAPIProvider
from .storage.kills import KillStorage
from .team_aliases import match_team_name

BJT = timezone(timedelta(hours=8))
TIER_ORDER = {"s": 0, "a": 1, "b": 2}
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def utc_to_bj(utc_str: str) -> str:
    if not utc_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        return dt.astimezone(BJT).strftime("%H:%M")
    except Exception:
        return ""


def utc_to_bj_full(utc_str: str) -> str:
    if not utc_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        return dt.astimezone(BJT).strftime("%m-%d %H:%M")
    except Exception:
        return ""


def tier_pass(tier: str, min_tier: str) -> bool:
    if min_tier == "all":
        return True
    if not tier:
        return True  # HLTV 不提供等级，默认通过
    t = TIER_ORDER.get(tier, 99)
    m = TIER_ORDER.get(min_tier, 99)
    return t <= m


def group_matches_by_tournament(matches: list[dict], min_tier: str) -> OrderedDict:
    groups = OrderedDict()
    for m in matches:
        t = m.get("tournament", {})
        tier = t.get("tier", "")
        if not tier_pass(tier, min_tier):
            continue

        league = m.get("league") or t.get("league") or {}
        serie = t.get("serie") or m.get("serie") or {}
        league_name = league.get("name", "")
        serie_name = serie.get("full_name", "") or serie.get("name", "")

        if league_name and serie_name and not serie_name.startswith(league_name):
            display_name = f"{league_name} {serie_name}"
        else:
            display_name = serie_name or league_name or t.get("name", "Unknown")

        serie_id = serie.get("id", 0) or t.get("id", 0)
        if serie_id not in groups:
            groups[serie_id] = {
                "name": display_name,
                "tier": tier,
                "matches": [],
            }
        m["bj_time"] = utc_to_bj(m.get("begin_at", ""))
        m["bj_full"] = utc_to_bj_full(m.get("begin_at", ""))
        groups[serie_id]["matches"].append(m)
    return groups


class CS2Plugin(Star):
    _plugin_name = "astrbot_plugin_cs2"

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = Path(get_astrbot_plugin_data_path()) / self._plugin_name
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_dir = Path(__file__).parent

        self.min_tier = self.config.get("min_tier", "a")
        self._header_style = self.config.get("header_style", "center")
        self._push_groups = self.config.get("push_groups", [])
        self._template_cache: dict[str, str] = {}

        # 比赛提醒 & 赛后推送
        self._reminder_enabled = self.config.get("match_reminder_enabled", False)
        self._reminder_minutes = self.config.get("match_reminder_minutes", 15)
        self._post_match_enabled = self.config.get("post_match_push_enabled", False)
        self._followed_teams = self.config.get("followed_teams", [])
        self._notified_matches: set[str] = set()  # 已推送的比赛 ID
        self._finished_matches: set[str] = set()   # 已推送结束的比赛 ID

        # 五杀监控
        self._ace_enabled = self.config.get("ace_push_enabled", True)
        self._poll_interval = self.config.get("ace_poll_interval", 1800)

        # 缓存最近的比赛列表（用于 /cs2 1 快速查看）
        self._last_matches: list[dict] = []

        # 初始化数据源
        self.api: BaseAPIProvider = self._init_api()

        # 击杀存储
        self.storage = KillStorage(self.data_dir)
        self._ace_task = None
        self._match_task = None

    def _init_api(self) -> BaseAPIProvider:
        source = self.config.get("data_source", "pandascore")
        hltv_url = self.config.get("hltv_api_url", "http://localhost:8000")
        ps_token = self.config.get("pandascore_token", "")

        if source == "hltv":
            logger.info(f"[CS2] 数据源: HLTV API ({hltv_url})")
            return HLTVAPI(hltv_url)
        elif source == "merged":
            logger.info(f"[CS2] 数据源: 合并模式 (HLTV + PandaScore)")
            return MergedAPI(HLTVAPI(hltv_url), PandaScoreAPI(ps_token))
        else:
            logger.info("[CS2] 数据源: PandaScore")
            return PandaScoreAPI(ps_token)

    async def initialize(self):
        await self.storage.init()

        ok, msg = await self.api.check_connection()
        if ok:
            logger.info(f"[CS2] {msg}")
        else:
            logger.warning(f"[CS2] {msg} — 请检查配置")

        if self._ace_enabled and ok:
            self._ace_task = asyncio.create_task(self._ace_monitor_loop())
            logger.info("[CS2] 五杀监控已启动")

        if (self._reminder_enabled or self._post_match_enabled) and ok:
            self._match_task = asyncio.create_task(self._match_monitor_loop())
            logger.info("[CS2] 比赛监控已启动")

    async def terminate(self):
        if self._ace_task:
            self._ace_task.cancel()
        if self._match_task:
            self._match_task.cancel()
        await self.api.close()
        await self.storage.close()
        logger.info("[CS2] 插件已卸载")

    def _load_template(self, name: str) -> str:
        if name not in self._template_cache:
            tpl_path = self.plugin_dir / name
            if not tpl_path.exists():
                logger.error(f"[CS2] 模板不存在: {tpl_path}")
                return f"<div>模板 {name} 不存在</div>"
            self._template_cache[name] = tpl_path.read_text(encoding="utf-8")
        return self._template_cache[name]

    async def _render(self, template_name: str, data: dict) -> str:
        html_content = self._load_template(template_name)
        return await self.html_render(
            html_content, data, options={"type": "png", "full_page": True}
        )

    def _build_template_data(self, groups: dict, title: str, subtitle: str) -> dict:
        now_bj = datetime.now(BJT)
        weekday = WEEKDAYS[now_bj.weekday()]
        return {
            "groups": groups,
            "title": title,
            "subtitle": subtitle,
            "header_style": self._header_style,
            "date_str": now_bj.strftime("%m-%d"),
            "date_full": now_bj.strftime("%Y年%m月%d日"),
            "weekday": weekday,
        }

    def _today_range(self) -> str:
        now_bj = datetime.now(BJT)
        start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)
        return (
            f"{start.astimezone(timezone.utc).isoformat()},"
            f"{end.astimezone(timezone.utc).isoformat()}"
        )

    # ========== 主命令 ==========

    @filter.command("cs2")
    async def cs2(self, event: AstrMessageEvent):
        """CS2 赛事查询 | /cs2 [序号|队名|live|upcoming|recent|major|rank]"""
        parts = event.message_str.strip().split()
        if len(parts) <= 1:
            async for r in self._handle_today(event):
                yield r
            return

        arg = parts[1].lower()

        # /cs2 <数字> → 查看第 N 场比赛详情
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(self._last_matches):
                match = self._last_matches[idx]
                async for r in self._handle_match_detail(event, match["id"]):
                    yield r
            else:
                yield event.plain_result(f"序号无效，当前列表共 {len(self._last_matches)} 场")
            return

        # 帮助关键词
        if arg in ("help", "菜单", "帮助", "?", "？"):
            yield event.plain_result(
                "CS2 赛事查询：\n"
                "/cs2 - 今日比赛\n"
                "/cs2 1 - 第1场比赛详情\n"
                "/cs2 猎鹰 - 搜索队伍（支持中文昵称）\n"
                "/cs2 live - 正在进行\n"
                "/cs2 upcoming - 即将开始\n"
                "/cs2 recent - 最近结束\n"
                "/cs2 major - Major 赛事\n"
                "/cs2 rank - HLTV 世界排名"
            )
            return

        # 固定子命令
        handlers = {
            "live": self._handle_live,
            "today": self._handle_today,
            "upcoming": self._handle_upcoming,
            "recent": self._handle_recent,
            "major": self._handle_major,
            "rank": self._handle_ranking,
            "ranking": self._handle_ranking,
        }
        handler = handlers.get(arg)
        if handler:
            async for r in handler(event):
                yield r
            return

        # /cs2 <队名关键词> → 搜索该队比赛
        query = " ".join(parts[1:]).lower()
        async for r in self._handle_search_by_team(event, query):
            yield r

    # ========== 子命令 ==========

    async def _handle_today(self, event: AstrMessageEvent):
        date_range = self._today_range()
        matches = await self.api.get_matches(begin_at_range=date_range, per_page=100)
        # 缓存比赛列表用于 /cs2 <序号> 快速查看
        self._last_matches = matches
        groups = group_matches_by_tournament(matches, self.min_tier)
        # 给每场比赛编号
        idx = 1
        for g in groups.values():
            for m in g["matches"]:
                m["_index"] = idx
                idx += 1
        total = sum(len(g["matches"]) for g in groups.values())
        logger.info(f"[CS2] 今日比赛: {total} 场, {len(groups)} 个赛事")
        if not groups:
            yield event.plain_result("今天没有 CS2 大赛")
            return
        url = await self._render(
            "templates/match_list.html",
            self._build_template_data(groups, "CS2 ESPORTS", "今日比赛 | 回复序号查看详情"),
        )
        yield event.image_result(url)

    async def _handle_live(self, event: AstrMessageEvent):
        # 优先使用 live 端点（含地图小分）
        matches = await self.api.get_live_matches()
        if not matches:
            matches = await self.api.get_matches(status="running", per_page=100)
        groups = group_matches_by_tournament(matches, self.min_tier)
        total = sum(len(g["matches"]) for g in groups.values())
        logger.info(f"[CS2] live: {total} 场")
        if not groups:
            yield event.plain_result("当前没有正在进行的 CS2 比赛")
            return
        url = await self._render(
            "templates/match_list.html",
            self._build_template_data(groups, "CS2 ESPORTS", "正在进行的比赛"),
        )
        yield event.image_result(url)

    async def _handle_upcoming(self, event: AstrMessageEvent):
        matches = await self.api.get_matches(status="not_started", per_page=50)
        groups = group_matches_by_tournament(matches, self.min_tier)
        total = sum(len(g["matches"]) for g in groups.values())
        logger.info(f"[CS2] upcoming: {total} 场")
        if not groups:
            yield event.plain_result("暂无即将开始的 CS2 比赛")
            return
        url = await self._render(
            "templates/match_list.html",
            self._build_template_data(groups, "CS2 ESPORTS", "即将开始的比赛"),
        )
        yield event.image_result(url)

    async def _handle_recent(self, event: AstrMessageEvent):
        matches = await self.api.get_matches(status="finished", per_page=50)
        groups = group_matches_by_tournament(matches, self.min_tier)
        total = sum(len(g["matches"]) for g in groups.values())
        logger.info(f"[CS2] recent: {total} 场")
        if not groups:
            yield event.plain_result("暂无最近结束的 CS2 比赛")
            return
        url = await self._render(
            "templates/match_list.html",
            self._build_template_data(groups, "CS2 ESPORTS", "最近结束的比赛"),
        )
        yield event.image_result(url)

    async def _handle_search_by_team(self, event: AstrMessageEvent, query: str):
        """按队伍名搜索比赛（支持中文昵称）"""
        matches = await self.api.get_matches(per_page=100)
        found = []
        for m in matches:
            for opp in m.get("opponents", []):
                name = (opp.get("opponent") or {}).get("name", "")
                if match_team_name(query, name):
                    found.append(m)
                    break
        if not found:
            yield event.plain_result(f"未找到包含 \"{query}\" 的比赛")
            return
        self._last_matches = found
        groups = group_matches_by_tournament(found, "all")
        idx = 1
        for g in groups.values():
            for m in g["matches"]:
                m["_index"] = idx
                idx += 1
        url = await self._render(
            "templates/match_list.html",
            self._build_template_data(groups, "CS2 ESPORTS", f"搜索: {query}"),
        )
        yield event.image_result(url)

    async def _handle_match_detail(self, event: AstrMessageEvent, match_id: int):
        match = await self.api.get_match_detail(match_id)
        if not match:
            yield event.plain_result(f"未找到比赛 ID: {match_id}")
            return
        match["bj_time"] = utc_to_bj(match.get("begin_at", ""))
        match["bj_date"] = utc_to_bj_full(match.get("begin_at", ""))
        url = await self._render("templates/match_detail.html", {"match": match})
        yield event.image_result(url)

    async def _handle_major(self, event: AstrMessageEvent):
        tournaments = await self.api.get_tournaments(tier="s", per_page=20)
        if not tournaments:
            tournaments = await self.api.get_tournaments(tier="a", per_page=20)
        # HLTV fallback: 搜索 Major 赛事
        if not tournaments and hasattr(self.api, '_hltv'):
            results = await self.api._hltv.search_events("Major")
            if results:
                tournaments = []
                for r in results[:20]:
                    tournaments.append({
                        "id": r.get("id"),
                        "name": r.get("name", ""),
                        "tier": "",
                        "begin_at": "",
                        "end_at": "",
                        "prizepool": r.get("prizePool", ""),
                        "league": {"name": r.get("eventLocation", "")},
                        "serie": {"full_name": r.get("name", "")},
                    })
        logger.info(f"[CS2] major: {len(tournaments)} 个赛事")
        if not tournaments:
            yield event.plain_result("暂无 Major 赛事信息")
            return
        for t in tournaments:
            t["bj_date"] = utc_to_bj_full(t.get("begin_at", ""))
        url = await self._render(
            "templates/tournament.html",
            {"tournaments": tournaments, "title": "MAJOR", "subtitle": "CS2 Major 赛事"},
        )
        yield event.image_result(url)

    async def _handle_ranking(self, event: AstrMessageEvent):
        rankings = await self.api.get_ranking(limit=30)
        logger.info(f"[CS2] ranking: {len(rankings)} 支队伍")
        if not rankings:
            yield event.plain_result("暂无排名数据（仅 HLTV 数据源支持）")
            return
        url = await self._render(
            "templates/ranking.html",
            {"rankings": rankings, "title": "HLTV RANKING", "subtitle": "世界排名"},
        )
        yield event.image_result(url)

    # ========== 比赛提醒 & 赛后推送 ==========

    def _is_followed(self, match: dict) -> bool:
        """判断比赛是否涉及关注的队伍"""
        if not self._followed_teams:
            return True  # 没设关注列表则推送所有
        for opp in match.get("opponents", []):
            name = (opp.get("opponent") or {}).get("name", "")
            if name and any(ft.lower() in name.lower() for ft in self._followed_teams):
                return True
        return False

    async def _match_monitor_loop(self):
        """每5分钟检查一次：比赛提醒 + 赛后推送"""
        while True:
            try:
                await asyncio.sleep(300)
                await self._check_match_reminders()
                await self._check_post_match()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[CS2] 比赛监控异常: {e}")

    async def _check_match_reminders(self):
        """检查即将开始的比赛，发送提醒"""
        if not self._reminder_enabled:
            return
        matches = await self.api.get_matches(status="not_started", per_page=50)
        now = datetime.now(timezone.utc)
        for m in matches:
            mid = str(m.get("id", ""))
            if mid in self._notified_matches:
                continue
            begin_str = m.get("begin_at", "")
            if not begin_str:
                continue
            try:
                begin_dt = datetime.fromisoformat(begin_str.replace("Z", "+00:00"))
            except Exception:
                continue
            diff = (begin_dt - now).total_seconds() / 60
            if 0 < diff <= self._reminder_minutes and self._is_followed(m):
                self._notified_matches.add(mid)
                await self._push_match_notification(m, "reminder")

    async def _check_post_match(self):
        """检查刚结束的比赛，推送结果"""
        if not self._post_match_enabled:
            return
        matches = await self.api.get_matches(status="finished", per_page=20)
        for m in matches:
            mid = str(m.get("id", ""))
            if mid in self._finished_matches:
                continue
            if self._is_followed(m):
                self._finished_matches.add(mid)
                await self._push_match_notification(m, "finished")

    async def _push_match_notification(self, match: dict, kind: str):
        """推送比赛通知"""
        opps = match.get("opponents", [])
        t1 = (opps[0].get("opponent") or {}).get("name", "TBD") if len(opps) > 0 else "TBD"
        t2 = (opps[1].get("opponent") or {}).get("name", "TBD") if len(opps) > 1 else "TBD"
        results = match.get("results", [])
        s1 = results[0].get("score", 0) if len(results) > 0 else 0
        s2 = results[1].get("score", 0) if len(results) > 1 else 0
        tournament = (match.get("tournament") or {}).get("name", "")
        bj_time = utc_to_bj(match.get("begin_at", ""))

        if kind == "reminder":
            text = f"比赛提醒 | {tournament}\n{t1} vs {t2}\n开赛时间: {bj_time} (北京时间)"
            for group_id in self._push_groups:
                if group_id:
                    try:
                        await self.context.send_message(group_id, [text])
                    except Exception as e:
                        logger.error(f"[CS2] 推送到群 {group_id} 失败: {e}")
        else:
            # 赛后推送：发送图片
            try:
                groups = group_matches_by_tournament([match], "all")
                url = await self._render(
                    "templates/match_list.html",
                    self._build_template_data(groups, "CS2 ESPORTS", "比赛结果"),
                )
                for group_id in self._push_groups:
                    if group_id:
                        try:
                            await self.context.send_message(group_id, [text, url])
                        except Exception as e:
                            logger.error(f"[CS2] 推送到群 {group_id} 失败: {e}")
            except Exception as e:
                logger.error(f"[CS2] 渲染赛后图片失败: {e}")
                text = f"比赛结束 | {tournament}\n{t1} {s1} : {s2} {t2}"
                for group_id in self._push_groups:
                    if group_id:
                        try:
                            await self.context.send_message(group_id, [text])
                        except Exception as ex:
                            logger.error(f"[CS2] 推送到群 {group_id} 失败: {ex}")

    # ========== 五杀监控 ==========

    async def _ace_monitor_loop(self):
        while True:
            try:
                await asyncio.sleep(self._poll_interval)
                await self._check_ongoing_matches()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[CS2] 五杀监控异常: {e}")

    async def _check_ongoing_matches(self):
        matches = await self.api.get_matches(status="running")
        for match in matches:
            try:
                events = await self.api.get_match_events(match["id"])
                if not events:
                    continue
                await self.storage.store_kills(match["id"], events)
                aces = await self.storage.detect_ace(match["id"])
                for ace in aces:
                    if not await self.storage.is_alerted(ace):
                        await self._push_ace_notification(ace, match)
            except Exception as e:
                logger.error(f"[CS2] 处理比赛 {match.get('id')} 异常: {e}")

    async def _push_ace_notification(self, ace: dict, match: dict):
        url = await self._render("templates/ace_notify.html", {"ace": ace, "match": match})
        await self.storage.mark_alerted(ace)
        text = f"五杀！{ace['player_name']} 在 {ace['map_name']} 第 {ace['round_number']} 回合完成五杀！"
        target_groups = self._push_groups or [ace.get("group_id")]
        for group_id in target_groups:
            if group_id:
                try:
                    await self.context.send_message(group_id, [text])
                except Exception as e:
                    logger.error(f"[CS2] 推送到群 {group_id} 失败: {e}")