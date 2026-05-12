# CS2 赛事查询插件

AstrBot 插件，查询 CS2 赛事信息。支持 PandaScore 和 HLTV 双数据源，中文队名搜索。

![预览](assets/preview.png)

## 功能

- **今日比赛** — `/cs2` 按赛事分组展示，带序号
- **快速查看详情** — `/cs2 1` 查看第1场比赛详情
- **中文搜索** — `/cs2 猎鹰`、`/cs2 小蜜蜂`、`/cs2 天禄` 等 40+ 昵称
- **实时比分** — `/cs2 live` 正在进行的比赛
- **比赛详情** — 地图池 + 每张地图比分
- **HLTV 排名** — `/cs2 rank` Top30 队伍排名
- **Major 赛事** — `/cs2 major` 快速查看
- **比赛提醒** — 关注队伍开赛前自动推送
- **赛后推送** — 关注队伍比赛结束自动推送
- **北京时间** — 所有时间自动转 UTC+8
- **三种标题样式** — 设置中可选 center / horizontal / split

## 命令

| 命令 | 说明 |
|------|------|
| `/cs2` | 今日比赛（带序号） |
| `/cs2 1` | 第1场比赛详情 |
| `/cs2 猎鹰` | 搜索队伍（支持中文昵称） |
| `/cs2 live` | 正在进行的比赛 |
| `/cs2 upcoming` | 即将开始 |
| `/cs2 recent` | 最近结束 |
| `/cs2 major` | Major 赛事 |
| `/cs2 rank` | HLTV 世界排名 |
| `/cs2 菜单` | 显示帮助 |

## 数据源

| 模式 | 比赛列表 | 队标 | 比分 | 地图池 | 排名 |
|------|---------|------|------|--------|------|
| **merged**（默认） | PandaScore | PandaScore | PandaScore | HLTV stats | HLTV |
| **hltv** | HLTV | 可能null | 仅live | HLTV stats | HLTV |
| **pandascore** | PandaScore | PandaScore | 403 | 403 | ❌ |

## 安装

1. 下载插件压缩包
2. 解压到 AstrBot 的 `data/plugins/` 目录
3. 在 WebUI 插件管理页重载插件（依赖自动安装）

### 数据源配置

**merged 模式（推荐）：**
- PandaScore Token — 获取比赛列表、队标、比分
- HLTV API 地址 — 获取地图池、排名、live 地图小分

**HLTV API 部署：**
```bash
git clone https://github.com/eupeutro/hltv-api.git
cd hltv-api
docker compose up -d --build
```

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `data_source` | 选择 | merged | merged / hltv / pandascore |
| `pandascore_token` | string | — | PandaScore API Token |
| `hltv_api_url` | string | http://localhost:8000 | HLTV API 地址 |
| `header_style` | 选择 | center | 标题样式 |
| `min_tier` | 选择 | a | 最低赛事等级（仅PandaScore） |
| `match_reminder_enabled` | 开关 | false | 比赛提醒 |
| `match_reminder_minutes` | 数字 | 15 | 提前提醒分钟数 |
| `post_match_push_enabled` | 开关 | false | 赛后推送 |
| `followed_teams` | 列表 | [] | 关注队伍 |
| `ace_push_enabled` | 开关 | true | 五杀推送 |
| `ace_poll_interval` | 数字 | 1800 | 五杀轮询间隔 |
| `push_groups` | 列表 | [] | 推送目标群 |

## 中文昵称

支持 40+ 常见 CS2 战队中文昵称：

| 昵称 | 队伍 |
|------|------|
| 猎鹰/法尔孔 | Falcons |
| 绿龙 | Spirit |
| 小蜜蜂 | Vitality |
| 天禄 | TYLOO |
| 液体 | Liquid |
| A队 | Astralis |
| VP | Virtus.pro |
| 蒙古人 | MongolZ |

## 许可

[AGPL-3.0](LICENSE)
