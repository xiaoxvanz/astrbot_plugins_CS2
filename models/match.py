# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Team:
    id: int
    name: str
    acronym: str = ""
    image_url: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "Team":
        return cls(
            id=data.get("id", 0),
            name=data.get("name", "Unknown"),
            acronym=data.get("acronym", ""),
            image_url=data.get("image_url", ""),
        )


@dataclass
class MapScore:
    map_name: str
    team1_score: int = 0
    team2_score: int = 0
    winner: Optional[str] = None

    @classmethod
    def from_api(cls, game: dict, team1_id: int, team2_id: int) -> "MapScore":
        scores = {}
        for result in game.get("results", []):
            scores[result.get("team_id")] = result.get("score", 0)
        winner_id = (game.get("winner") or {}).get("id")
        winner_name = None
        if winner_id == team1_id:
            winner_name = "team1"
        elif winner_id == team2_id:
            winner_name = "team2"
        return cls(
            map_name=game.get("map", {}).get("name", f"Map {game.get('position', '?')}"),
            team1_score=scores.get(team1_id, 0),
            team2_score=scores.get(team2_id, 0),
            winner=winner_name,
        )


@dataclass
class Match:
    id: int
    name: str
    status: str
    team1: Optional[Team] = None
    team2: Optional[Team] = None
    team1_score: int = 0
    team2_score: int = 0
    tournament_name: str = ""
    league_name: str = ""
    begin_at: str = ""
    number_of_games: int = 0
    maps: list[MapScore] = field(default_factory=list)
    match_type: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "Match":
        opponents = data.get("opponents", [])
        team1 = Team.from_api(opponents[0]["opponent"]) if len(opponents) > 0 else None
        team2 = Team.from_api(opponents[1]["opponent"]) if len(opponents) > 1 else None

        results = data.get("results", [])
        t1_score = 0
        t2_score = 0
        for r in results:
            if team1 and r.get("team_id") == team1.id:
                t1_score = r.get("score", 0)
            elif team2 and r.get("team_id") == team2.id:
                t2_score = r.get("score", 0)

        maps = []
        for game in data.get("games", []):
            if team1 and team2:
                maps.append(MapScore.from_api(game, team1.id, team2.id))

        tournament = data.get("tournament", {})
        league = data.get("league", {})

        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            status=data.get("status", ""),
            team1=team1,
            team2=team2,
            team1_score=t1_score,
            team2_score=t2_score,
            tournament_name=tournament.get("name", ""),
            league_name=league.get("name", ""),
            begin_at=data.get("begin_at", ""),
            number_of_games=data.get("number_of_games", 0),
            maps=maps,
            match_type=data.get("match_type", ""),
        )


@dataclass
class Tournament:
    id: int
    name: str
    slug: str = ""
    tier: str = ""
    begin_at: str = ""
    end_at: str = ""
    prizepool: str = ""
    league_name: str = ""
    serie_name: str = ""
    matches_count: int = 0

    @classmethod
    def from_api(cls, data: dict) -> "Tournament":
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            slug=data.get("slug", ""),
            tier=data.get("tier", ""),
            begin_at=data.get("begin_at", ""),
            end_at=data.get("end_at", ""),
            prizepool=data.get("prizepool", ""),
            league_name=data.get("league", {}).get("name", ""),
            serie_name=data.get("serie", {}).get("full_name", ""),
            matches_count=data.get("matches_count", 0),
        )