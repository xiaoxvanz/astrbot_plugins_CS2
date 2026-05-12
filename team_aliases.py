# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

# CS2 战队中文昵称映射
# key: 中文昵称（小写）, value: 英文队名关键词

TEAM_ALIASES = {
    # 欧洲
    "猎鹰": "falcons",
    "法尔孔": "falcons",
    "绿龙": "spirit",
    "小蜜蜂": "vitality",
    "蜜蜂": "vitality",
    "红星": "gambit",
    "银河战舰": "faze",
    "肥仔": "faze",
    "老鼠": "mouz",
    "小蜜蜂": "vitality",
    "navi": "natus vincere",
    "娜维": "natus vincere",
    "天生赢家": "natus vincere",
    "简单男孩": "s1mple",
    "液体": "liquid",
    "水队": "liquid",
    "寒冰": "liquid",
    "nip": "ninjas in pyjamas",
    "忍者": "ninjas in pyjamas",
    "fnatic": "fnatic",
    "黑豹": "fnatic",
    "a队": "astralis",
    "星星": "astralis",
    "g2": "g2",
    "绅士": "g2",
    "c9": "cloud9",
    "云九": "cloud9",
    "ence": "ence",
    "heroic": "heroic",
    "丹麦熊": "heroic",
    "big": "big",
    "复杂": "complexity",
    "og": "og",
    "furia": "furia",
    "毛子队": "furia",
    "imperial": "imperial",
    "帝国": "imperial",
    "pain": "pain",
    "9z": "9z",
    "mibr": "mibr",
    "vp": "virtus.pro",
    "virtuspro": "virtus.pro",
    "熊": "virtus.pro",
    "极光": "aurora",
    "gl": "gamerlegion",
    "玩家联盟": "gamerlegion",
    "monte": "monte",
    "蒙特": "monte",
    "saw": "saw",
    "betboom": "betboom",
    "bb": "betboom",
    "parivision": "parivision",

    # 亚洲
    "天禄": "tyloo",
    "tyloo": "tyloo",
    "lynn vision": "lynn vision",
    "lynn": "lynn vision",
    "林肯": "lynn vision",
    "ra": "rare atom",
    "稀有原子": "rare atom",
    "wings up": "wings up",
    "起飞": "wings up",
    "ig": "invictus gaming",
    "不可战胜": "invictus gaming",
    "vg": "vg",
    "dk": "dks",
    "five star": "5star",
    "五星": "5star",
    "mongolz": "mongolz",
    "蒙古": "mongolz",
    "flyquest": "flyquest",
    "苍蝇": "flyquest",
}


def match_team_name(query: str, team_name: str) -> bool:
    """匹配队名，支持中文昵称和英文名"""
    q = query.lower().strip()
    t = team_name.lower().strip()

    # 直接英文名匹配
    if q in t or t in q:
        return True

    # 中文昵称匹配
    alias_target = TEAM_ALIASES.get(q, "")
    if alias_target and (alias_target in t or t in alias_target):
        return True

    return False
