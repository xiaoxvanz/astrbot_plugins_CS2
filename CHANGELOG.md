# Changelog

## v0.1.1 (2026-05-12)

### New Features
- **合并数据源** — PandaScore 做主力（队标+比分），HLTV 补充（live地图分+排名+地图池）
- **中文队名搜索** — 支持 40+ 中文昵称（猎鹰、绿龙、小蜜蜂、天禄等）
- **简化命令** — `/cs2 1` 看第1场详情，`/cs2 猎鹰` 搜索队伍
- **HLTV 比赛详情** — 通过 `/matches/stats/{id}` 获取地图池和每张地图比分
- **排名队标** — HLTV 排名页面从 PandaScore 补充队伍 LOGO
- **帮助菜单** — `/cs2 菜单` 显示所有命令

### Bug Fixes
- 修复排名端点路径（连字符 vs 下划线）
- 修复排名队标 `await` 缺失
- 修复命令匹配把帮助关键词当队名搜索
- 修复 `null` 值导致 "None" 显示
- 修复 HLTV live 端点队标字段名
- 修复 Major 命令无数据时 fallback 到 HLTV 搜索

### Other
- 新增 `team_aliases.py` 中文昵称映射
- 新增 `api/merged.py` 合并数据源
- 新增 `api/base.py` 数据源抽象接口
- 新增 `templates/ranking.html` 排名模板
- 新增 CHANGELOG.md
- 更新 README.md

## v0.2.0 (2026-05-12)

### New Features
- HLTV API 数据源支持
- 双数据源切换（PandaScore / HLTV）
- HLTV 世界排名（`/cs2 rank`）
- Live 地图小分
- 比赛提醒和赛后推送
- 白底配色主题
- 三种标题样式（center / horizontal / split）
- API 连通检测
- 北京时间

### Bug Fixes
- 修复 HLTV 比赛被赛事等级过滤误杀
- 修复 `bj_date` 变量名不匹配
- 修复赛后推送图片未发送
- 修复 `_get_round_map` 返回值错误
- 修复 `opponents` 空列表 IndexError
- 修复 Python 3.9 兼容性

## v0.1.0 (2026-05-10)

### Initial Release
- PandaScore API 数据源
- 今日比赛、正在进行、即将开始、最近结束
- 比赛详情（大分 + 地图小分）
- 赛事列表、Major 赛事
- 五杀自动推送框架
- 电竞风格图片渲染
