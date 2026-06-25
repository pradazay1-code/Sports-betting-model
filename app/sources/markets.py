"""Map sportsbook market labels -> canonical market keys.

Canonical names match the keys in app.config.MARKETS.
First-match-wins on lowercased substring.
"""

from __future__ import annotations

NBA_PATTERNS: list[tuple[str, str]] = [
    ("points + rebounds + assists", "player_pra"),
    ("pts+rebs+asts", "player_pra"),
    ("pra", "player_pra"),
    ("3-pt made", "player_threes"),
    ("threes made", "player_threes"),
    ("3-pointers", "player_threes"),
    ("points", "player_points"),
    ("rebounds", "player_rebounds"),
    ("assists", "player_assists"),
    ("steals", "player_steals"),
    ("blocks", "player_blocks"),
]

MLB_PATTERNS: list[tuple[str, str]] = [
    ("total bases", "batter_total_bases"),
    ("rbis", "batter_rbis"),
    ("runs scored", "batter_runs"),
    ("strikeouts thrown", "pitcher_strikeouts"),
    ("pitcher strikeouts", "pitcher_strikeouts"),
    ("hitter strikeouts", "batter_strikeouts"),
    ("strikeouts", "batter_strikeouts"),
    ("outs recorded", "pitcher_outs"),
    ("earned runs", "pitcher_earned_runs"),
    ("hits", "batter_hits"),
]

NHL_PATTERNS: list[tuple[str, str]] = [
    ("shots on goal", "player_shots_on_goal"),
    ("sog", "player_shots_on_goal"),
    ("saves", "goalie_saves"),
    ("points", "player_points"),
    ("goals", "player_goals"),
    ("assists", "player_assists"),
]

NFL_PATTERNS: list[tuple[str, str]] = [
    ("pass completions", "player_pass_completions"),
    ("completions", "player_pass_completions"),
    ("pass attempts", "player_pass_attempts"),
    ("passing yards", "player_pass_yards"),
    ("pass yards", "player_pass_yards"),
    ("passing tds", "player_pass_tds"),
    ("passing touchdowns", "player_pass_tds"),
    ("interceptions thrown", "player_interceptions"),
    ("interceptions", "player_interceptions"),
    ("rushing yards", "player_rush_yards"),
    ("rush yards", "player_rush_yards"),
    ("rushing attempts", "player_rush_attempts"),
    ("carries", "player_rush_attempts"),
    ("receiving yards", "player_rec_yards"),
    ("rec yards", "player_rec_yards"),
    ("receptions", "player_receptions"),
]

SOCCER_PATTERNS: list[tuple[str, str]] = [
    ("shots on target", "player_shots_on_target"),
    ("shots on goal", "player_shots_on_target"),
    ("total shots", "player_shots"),
    ("shots", "player_shots"),
    ("goals", "player_goals"),
    ("assists", "player_assists"),
    ("passes", "player_passes"),
    ("tackles", "player_tackles"),
    ("saves", "goalie_saves"),
]

PATTERNS = {
    "NBA": NBA_PATTERNS,
    "MLB": MLB_PATTERNS,
    "NHL": NHL_PATTERNS,
    "NFL": NFL_PATTERNS,
    "EPL": SOCCER_PATTERNS,
}


def map_market(sport: str, label: str | None) -> str | None:
    if not label:
        return None
    n = label.lower()
    for needle, market in PATTERNS.get(sport, []):
        if needle in n:
            return market
    return None
