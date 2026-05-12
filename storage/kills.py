# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

from pathlib import Path
from typing import Optional

import aiosqlite

from astrbot.api import logger


class KillStorage:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(data_dir / "cs2_kills.db")
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS kill_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                round_number INTEGER,
                killer_name TEXT,
                killer_team TEXT,
                victim_name TEXT,
                victim_team TEXT,
                weapon TEXT,
                is_headshot BOOLEAN DEFAULT 0,
                event_time TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_kills_match ON kill_events(match_id);
            CREATE INDEX IF NOT EXISTS idx_kills_round ON kill_events(match_id, round_number);

            CREATE TABLE IF NOT EXISTS ace_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                player_name TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                map_name TEXT,
                alerted BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(match_id, player_name, round_number)
            );
        """)
        await self._db.commit()

    async def store_kills(self, match_id: int, events: list[dict]):
        """
        存储击杀事件。
        PandaScore 事件结构:
        {
            "type": "kill",
            "payload": {
                "killer": { "id", "name", "team_id", "team_name", "weapon": {...} },
                "killed": { "id", "name", "team_id", "team_name" },
                "round_number": 5,
                "elapsed_round_time": 45
            }
        }
        """
        if not events:
            return

        existing = set()
        async with self._db.execute(
            "SELECT round_number, killer_name, victim_name FROM kill_events WHERE match_id = ?",
            (match_id,),
        ) as cursor:
            async for row in cursor:
                existing.add((row[0], row[1], row[2]))

        new_rows = []
        for event in events:
            if event.get("type") != "kill":
                continue
            payload = event.get("payload", {})
            killer = payload.get("killer", {})
            killed = payload.get("killed", {})
            round_num = payload.get("round_number", 0)
            killer_name = killer.get("name", "")
            victim_name = killed.get("name", "")
            key = (round_num, killer_name, victim_name)
            if key in existing:
                continue
            weapon = killer.get("weapon", {})
            new_rows.append((
                match_id,
                round_num,
                killer_name,
                killer.get("team_name", ""),
                victim_name,
                killed.get("team_name", ""),
                weapon.get("name", "") if isinstance(weapon, dict) else "",
                payload.get("headshot", False),
                str(payload.get("elapsed_round_time", "")),
            ))

        if new_rows:
            await self._db.executemany(
                """INSERT INTO kill_events
                   (match_id, round_number, killer_name, killer_team,
                    victim_name, victim_team, weapon, is_headshot, event_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                new_rows,
            )
            await self._db.commit()

    async def detect_ace(self, match_id: int) -> list[dict]:
        aces = []
        async with self._db.execute(
            """SELECT killer_name, round_number, COUNT(*) as kills
               FROM kill_events
               WHERE match_id = ?
               GROUP BY killer_name, round_number
               HAVING kills >= 5""",
            (match_id,),
        ) as cursor:
            async for row in cursor:
                player_name, round_number, kill_count = row
                async with self._db.execute(
                    "SELECT id FROM ace_alerts WHERE match_id = ? AND player_name = ? AND round_number = ?",
                    (match_id, player_name, round_number),
                ) as ace_cursor:
                    existing = await ace_cursor.fetchone()
                    if not existing:
                        await self._db.execute(
                            """INSERT INTO ace_alerts (match_id, player_name, round_number)
                               VALUES (?, ?, ?)""",
                            (match_id, player_name, round_number),
                        )
                        await self._db.commit()

                        team_name = await self._get_round_team(match_id, round_number)
                        aces.append({
                            "match_id": match_id,
                            "player_name": player_name,
                            "round_number": round_number,
                            "kill_count": kill_count,
                            "map_name": "Unknown",
                            "team_name": team_name or "Unknown",
                        })
        return aces

    async def _get_round_team(self, match_id: int, round_number: int) -> Optional[str]:
        async with self._db.execute(
            "SELECT DISTINCT killer_team FROM kill_events WHERE match_id = ? AND round_number = ? LIMIT 1",
            (match_id, round_number),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def is_alerted(self, ace: dict) -> bool:
        async with self._db.execute(
            "SELECT alerted FROM ace_alerts WHERE match_id = ? AND player_name = ? AND round_number = ?",
            (ace["match_id"], ace["player_name"], ace["round_number"]),
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None and row[0] == 1

    async def mark_alerted(self, ace: dict):
        await self._db.execute(
            "UPDATE ace_alerts SET alerted = 1 WHERE match_id = ? AND player_name = ? AND round_number = ?",
            (ace["match_id"], ace["player_name"], ace["round_number"]),
        )
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()