"""Professorsack ESPN Fantasy Basketball exporter v2.1 (read-only).

Fetches all obtainable free-agent/waiver pages, current league rosters, ESPN box
scores, per-player recent games, injury fields, and 14-day NBA game schedules.
Does not perform add/drop, read ESPN proprietary trending counts, or transmit cookies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import getpass
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

APP = "professorsack-espn-exporter"  # Same keyring service as original exporter.
BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config.json"
TZ = ZoneInfo("America/Toronto")
SCORING = {"PTS": 1, "FGM": 2, "FGA": -1, "FTM": 1, "FTA": -1,
           "3PM": 1, "REB": 1, "AST": 2, "STL": 4, "BLK": 4, "TO": -2}
KEY_STATS = ("PTS", "FGM", "FGA", "FTM", "FTA", "3PM", "REB", "AST", "STL", "BLK", "TO", "MIN", "GP", "GS")


def safe(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(x) for x in value]
    return str(value)


def small_stat(line):
    if not isinstance(line, dict):
        return None
    return {k: line[k] for k in KEY_STATS if k in line and line[k] is not None}


def summarize_stats(p, year, period_to_date, recent_count=7):
    allstats = getattr(p, "stats", {}) or {}
    totals = {}
    for key in (f"{year}_total", f"{year}_projected", f"{year}_last_7", f"{year}_last_15", f"{year}_last_30"):
        src = allstats.get(key) or {}
        totals[key] = {"applied_total": src.get("applied_total"),
                       "applied_avg": src.get("applied_avg"),
                       "avg": small_stat(src.get("avg"))}
    games = []
    for key, entry in allstats.items():
        if not str(key).isdigit() or not isinstance(entry, dict):
            continue
        line = entry.get("total")
        if not isinstance(line, dict) or float(line.get("GP") or 0) <= 0:
            continue
        value = entry.get("applied_total")
        period = int(key)
        game_date = period_to_date.get(period)
        games.append({
            "scoring_period": period,
            "date": game_date,
            "fantasy_points": value,
            "stats": small_stat(line),
        })
    games.sort(key=lambda g: g["scoring_period"], reverse=True)
    return totals, games[:recent_count]


def upcoming_schedule(team_id, league, start, days):
    """The ESPN schedule is keyed by basketball scoring-period IDs.

    The raw 'date' is an epoch in milliseconds; use aware datetimes to avoid
    incorrect calendar days or daylight-saving transitions.
    """
    raw = (getattr(league, "pro_schedule", {}) or {}).get(team_id, {})
    out = []
    limit = start + timedelta(days=days)
    if not isinstance(raw, dict):
        return out
    for period, entries in raw.items():
        for game in (entries or []):
            try:
                when = datetime.fromtimestamp(float(game["date"]) / 1000, tz=timezone.utc).astimezone(TZ)
            except (TypeError, ValueError, KeyError, OverflowError):
                continue
            if not (start.date() <= when.date() < limit.date()):
                continue
            home_id = game.get("homeProTeamId")
            away_id = game.get("awayProTeamId")
            other = away_id if home_id == team_id else home_id
            out.append({
                "scoring_period": int(period), "date": when.isoformat(),
                "local_day": when.date().isoformat(), "opponent_pro_team_id": other,
                "home": home_id == team_id,
            })
    out.sort(key=lambda x: x["date"])
    # Avoid accidental duplicate games caused by ESPN schedule mappings.
    return list({(g["scoring_period"], g["date"]): g for g in out}.values())


def period_date_lookup(league):
    out = {}
    for games in (getattr(league, "pro_schedule", {}) or {}).values():
        if not isinstance(games, dict):
            continue
        for period, entries in games.items():
            if not entries:
                continue
            try:
                when = datetime.fromtimestamp(float(entries[0]["date"])/1000, tz=timezone.utc).astimezone(TZ)
                out[int(period)] = when.date().isoformat()
            except (TypeError, ValueError, KeyError, OverflowError):
                continue
    return out


def player_summary(p, year, team_id, league, start, days, period_dates, availability=None, roster_team=None):
    stats, recent = summarize_stats(p, year, period_dates)
    data = {
        "name": getattr(p, "name", None),
        "playerId": getattr(p, "playerId", None),
        "proTeam": getattr(p, "proTeam", None),
        "position": getattr(p, "position", None),
        "eligibleSlots": safe(getattr(p, "eligibleSlots", []) or []),
        "lineupSlot": getattr(p, "lineupSlot", None),
        "injuryStatus": getattr(p, "injuryStatus", None),
        "injured": getattr(p, "injured", None),
        "expected_return_date": safe(getattr(p, "expected_return_date", None)),
        "availability_status": availability or "UNKNOWN_VERIFY_IN_ESPN",
        "rostered_by": roster_team,
        "projected_avg_points": getattr(p, "projected_avg_points", None),
        "projected_total_points": getattr(p, "projected_total_points", None),
        "avg_points": getattr(p, "avg_points", None),
        "total_points": getattr(p, "total_points", None),
        "stats_summary": stats,
        "recent_games": recent,
        "upcoming_games": upcoming_schedule(team_id, league, start, days) if team_id is not None else [],
    }
    return data


def newest_performance(p):
    """Pick the latest actual game, falling back only if ESPN supplies ONE season game.

    ESPNs paginated `kona_player_info` response often has season-to-date totals
    but NO per-scoring-period logs for available players. After just one game
    those totals are a defensible breakout indicator; after two or more games
    they are NOT a valid substitute for the latest game.
    """
    games = p.get("recent_games") or []
    if games:
        return {**games[0], "source": "ESPN_GAME_LOG"}
    sums = p.get("stats_summary") or {}
    total = next((v for k, v in sums.items() if str(k).endswith("_total")), None)
    if not isinstance(total, dict):
        return None
    line = total.get("avg") or {}
    try:
        gp = float(line.get("GP") or 0)
        score = float(total.get("applied_total") or p.get("total_points") or 0)
    except (TypeError, ValueError):
        return None
    if gp != 1 or score <= 0:
        return None
    return {"scoring_period": None, "date": None, "fantasy_points": score,
            "stats": line, "source": "ONE_GAME_SEASON_TOTAL_FALLBACK"}


def breakout_candidates(players, limit=35):
    """Derived signal, not ESPN's in-app Trending/add-count ranking."""
    entries = []
    for p in players:
        game = newest_performance(p)
        if not game:
            continue
        score = float(game.get("fantasy_points") or 0)
        line = game.get("stats") or {}
        mins = float(line.get("MIN") or 0)
        steals = float(line.get("STL") or 0)
        blocks = float(line.get("BLK") or 0)
        defensive_pts = 4 * (steals + blocks)
        projected = float(p.get("projected_avg_points") or 0)
        # Impact = actual FP vs historical estimate, participation, and minutes.
        # Sort by actual fantasy production primarily; don't automatically claim sustainability.
        entries.append({
            "playerId": p.get("playerId"), "name": p.get("name"),
            "proTeam": p.get("proTeam"), "availability_status": p.get("availability_status"),
            "latest_game": game.get("date"),
            "performance_source": game.get("source", "UNKNOWN"),
            "latest_fp": score,
            "latest_minutes": mins, "preseason_projected_fp_per_game": projected,
            "over_projection_fp": round(score-projected, 1),
            "defensive_points_from_steals_and_blocks": defensive_pts,
            "defensive_share_of_fp": round(defensive_pts/score, 3) if score > 0 else None,
            "high_defensive_variance_flag": defensive_pts >= 16,
            "next_14_days_games": len(p.get("upcoming_games") or []),
        })
    return sorted(entries, key=lambda x: (x["latest_fp"], x["over_projection_fp"], x["latest_minutes"]), reverse=True)[:limit]


def fetch_free_agent_pages(league, year, size, page_size, warnings):
    """Use ESPN's official filter/pagination via espn-api request object.

    Unlike League.free_agents(), this can page beyond the first ownership-sorted
    slice and preserves ESPN's availability-status field.
    """
    from espn_api.basketball.player import Player

    records, seen = [], set()
    request_count = 0
    got_last_page = False
    offset = 0
    while offset < size:
        limit = min(page_size, size-offset)
        filters = {"players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
            "limit": limit, "offset": offset,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"},
        }}
        try:
            data = league.espn_request.league_get(
                params={"view": "kona_player_info", "scoringPeriodId": league.current_week},
                headers={"x-fantasy-filter": json.dumps(filters)},
            )
            entries = data.get("players") if isinstance(data, dict) else None
            if not isinstance(entries, list):
                raise ValueError("ESPN response did not contain a players list")
        except Exception as exc:
            warnings.append(f"Free-agent scan stopped after offset {offset}: {type(exc).__name__}: {str(exc)[:130]}")
            break
        request_count += 1
        if not entries:
            got_last_page = True
            break
        unique_before = len(seen)
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            obj = raw.get("playerPoolEntry") or raw
            inner = obj.get("player") or raw.get("player") or raw
            pid = inner.get("id") or obj.get("id") or raw.get("id")
            if pid in seen or pid is None:
                continue
            seen.add(pid)
            try:
                player = Player(raw, year)
                status = raw.get("status") or obj.get("status") or "UNKNOWN_VERIFY_IN_ESPN"
                team_id = inner.get("proTeamId") or raw.get("proTeamId")
                records.append((player, team_id, status))
            except Exception as exc:
                warnings.append(f"Failed to decode player ID {pid}: {type(exc).__name__}")
        if len(seen) == unique_before:
            warnings.append("Free-agent pagination returned duplicate page(s); scan stopped to prevent false full-coverage claim")
            break
        # ESPN may silently cap a requested page (e.g. 100 instead of 150).
        # Advance by the ACTUAL number of records returned, then probe the
        # next offset until ESPN returns an empty page.
        offset += len(entries)
    coverage = {
        "method": "ESPN kona_player_info paginated by offset; ownership-descending ordering",
        "requested_limit": size, "page_size": page_size,
        "api_requests": request_count, "unique_players_returned_before_roster_dedup": len(records),
        "reached_last_page": got_last_page,
        "complete": got_last_page,
    }
    if not got_last_page:
        warnings.append("Free-agent scan may be incomplete: reached configured limit or experienced a pagination/API issue")
    return records, coverage


def box_score_summary(league, warnings):
    """Use ESPN's scoring-period-aware box scores; avoid stale team.points_for."""
    try:
        scores = league.box_scores(matchup_period=league.currentMatchupPeriod)
        result = []
        team_names = {t.team_id: t.team_name for t in league.teams}
        for b in scores:
            result.append({
                "home_team_id": getattr(b.home_team, "team_id", b.home_team),
                "away_team_id": getattr(b.away_team, "team_id", b.away_team),
                "home_team": getattr(b.home_team, "team_name", None) or
                             team_names.get(getattr(b.home_team, "team_id", b.home_team)),
                "away_team": getattr(b.away_team, "team_name", None) or
                             team_names.get(getattr(b.away_team, "team_id", b.away_team)),
                "home_score": getattr(b, "home_score", None),
                "away_score": getattr(b, "away_score", None),
                "home_projected": getattr(b, "home_projected", None),
                "away_projected": getattr(b, "away_projected", None),
            })
        return result
    except Exception as exc:
        warnings.append(f"Current matchup box scores unavailable: {type(exc).__name__}: {str(exc)[:130]}")
        return []


def recent_league_transactions(league, warnings, count=60):
    """League add/drop activity only; NOT platform-wide ESPN Trending data."""
    if not hasattr(league, "recent_activity"):
        return []
    try:
        activities = league.recent_activity(size=count)
        items = []
        for activity in activities:
            raw_date = getattr(activity, "date", None)
            timestamp = None
            if isinstance(raw_date, (float, int)):
                # ESPN activity dates are milliseconds since epoch.
                try:
                    timestamp = datetime.fromtimestamp(raw_date / 1000, tz=timezone.utc).astimezone(TZ).isoformat()
                except (OSError, OverflowError, ValueError):
                    timestamp = None
            for team, action, player, position in getattr(activity, "actions", []) or []:
                items.append({"date": timestamp,
                              "team_name": getattr(team, "team_name", None),
                              "action": action,
                              "player": player,
                              "position": position or None})
        return items
    except Exception as exc:
        warnings.append(f"League transaction activity unavailable: {type(exc).__name__}: {str(exc)[:120]}")
        return []


def build_snapshot(league, league_id, year, now, max_free_agents=1200, page_size=150, lookahead=14, candidate_count=35):
    warnings = []
    period_dates = period_date_lookup(league)
    teamids_by_abbrev = {}
    try:
        from espn_api.basketball.constant import PRO_TEAM_MAP
        teamids_by_abbrev = {abbr: n for n, abbr in PRO_TEAM_MAP.items()}
    except ImportError:
        warnings.append("Could not load ESPN pro-team codes: upcoming schedules may be incomplete")
    rosters = {}
    teams = []
    for t in league.teams:
        players = []
        for p in t.roster:
            if p.playerId is not None:
                rosters[p.playerId] = t.team_name
            players.append(player_summary(p, year, teamids_by_abbrev.get(p.proTeam), league, now,
                                          lookahead, period_dates, availability="ONTEAM", roster_team=t.team_name))
        teams.append({
            "team_id": t.team_id, "team_name": t.team_name,
            "team_abbrev": getattr(t, "team_abbrev", None),
            "wins": getattr(t, "wins", None), "losses": getattr(t, "losses", None),
            "season_acquisitions": getattr(t, "acquisitions", None),
            "season_drops": getattr(t, "drops", None),
            "points_for": getattr(t, "points_for", None),
            "standing": getattr(t, "standing", None), "roster": players,
        })
    records, coverage = fetch_free_agent_pages(league, year, max_free_agents, page_size, warnings)
    available = []
    excluded = []
    for p, team_id, status in records:
        if p.playerId in rosters:
            excluded.append({"playerId": p.playerId, "name": p.name, "owner": rosters[p.playerId]})
            continue
        available.append(player_summary(p, year, team_id or teamids_by_abbrev.get(p.proTeam),
                                        league, now, lookahead, period_dates, availability=status))
    coverage["excluded_already_rostered"] = len(excluded)
    coverage["unique_unrostered_players"] = len(available)
    if excluded:
        warnings.append(f"Removed {len(excluded)} incorrectly returned free agents already rostered in this league")
    missing_schedules = sum(not p.get("upcoming_games") for p in available)
    missing_game_logs = sum(not p.get("recent_games") for p in available)
    if missing_schedules:
        warnings.append(f"{missing_schedules} free agents have no next-14-day ESPN schedule (could be inactive or incomplete ESPN data)")
    if missing_game_logs:
        warnings.append(f"{missing_game_logs} free-agent entries lack per-game logs; breakout candidates use ONE-GAME season totals where possible. No assumption made for 2+ games.")
    try:
        scorecards = [
            {"home_team": getattr(m.home_team, "team_name", None),
             "away_team": getattr(m.away_team, "team_name", None),
             "home_score": getattr(m, "home_final_score", None),
             "away_score": getattr(m, "away_final_score", None)}
            for m in league.scoreboard()
        ]
    except Exception as exc:
        warnings.append(f"Matchup scoreboard unavailable: {type(exc).__name__}: {str(exc)[:130]}")
        scorecards = []
    snapshot = {
        "export_format": "professorsack-v2", "exported_at": now.isoformat(),
        "season": year, "league_id": league_id, "team_name_target": "Professorsack",
        "source": "espn-api / ESPN Fantasy Basketball read-only snapshot",
        "privacy": "No SWID or espn_s2 in output; share the JSON, never the cookies",
        "scoring": SCORING,
        "league_settings": {"name": getattr(league.settings, "name", None),
                            "scoring_type": getattr(league.settings, "scoring_type", None),
                            "teams": len(teams),
                            "acquisition_limit": getattr(league.settings, "acquisition_limit", None),
                            "matchup_acquisition_limit": getattr(league.settings, "matchup_acquisition_limit", None),
                            "waiver_process_days": safe(getattr(league.settings, "waiver_process_days", None)),
                            "waiver_process_hour": getattr(league.settings, "waiver_process_hour", None)},
        "scoring_period_id": getattr(league, "scoringPeriodId", None),
        "matchup_period_id": getattr(league, "currentMatchupPeriod", None),
        "matchup_scoring_period_ids": safe((getattr(league, "matchup_ids", {}) or {}).get(
            getattr(league, "currentMatchupPeriod", None), [])),
        "expected_league_rules_verify_in_espn": {
            "active_slots": ["PG", "SG", "SF", "PF", "C", "G", "F", "UT", "UT", "UT"],
            "bench": 3, "IR": 1, "max_center_eligible": 4,
            "weekly_acquisition_limit": 7, "waiver_days": 1,
        },
        "teams": teams,
        "matchups": scorecards,
        "current_matchup_box_scores": box_score_summary(league, warnings),
        "recent_league_transactions": recent_league_transactions(league, warnings),
        "free_agents": available,
        "free_agent_scan_coverage": {**coverage,
                                     "missing_recent_game_logs": missing_game_logs,
                                     "missing_upcoming_schedules": missing_schedules},
        "excluded_rostered_from_free_agents": excluded,
        "breakout_candidates": breakout_candidates(available, candidate_count),
        "breakout_method": "Ranked by actual ESPN scoring-period games, or season total ONLY WHEN exactly one game has been played. One-game fallback dates unknown. High steals/blocks flagged. NOT ESPN Trending/add counts.",
        "analysis_notes": [
            "Only fantasy free agents or waiver players returned by ESPN are evaluated; coverage.complete must be true to claim full scan.",
            "Recent league transactions reflect YOUR league only, not ESPN-wide Trending adds.",
            "Use upcoming_games on both rostered and free agents; optimize by eligible slots, day, and 10 daily starters.",
            "Acquisition totals on teams are season totals, not necessarily remaining weekly acquisitions; check weekly acquisitions used in ESPN.",
            "Check actual ESPN Add/Claim status, waiver clearance, remaining acquisitions, injuries, and starting rotations before taking action.",
            "This export is not a live ChatGPT connection; upload a new JSON before each full review.",
        ],
        "warnings": warnings,
    }
    return safe(snapshot)


def main():
    parser = argparse.ArgumentParser(description="ESPN fantasy basketball full-pool, breakout-aware exporter v2.1 (read only)")
    parser.add_argument("--league-id", type=int)
    parser.add_argument("--year", type=int, help="ESPN season; 2027 is the 2026-27 season")
    parser.add_argument("--reset-credentials", action="store_true")
    parser.add_argument("--max-free-agents", type=int, default=1200,
                        help="Maximum combined free agents + waivers to scan (default 1200)")
    parser.add_argument("--page-size", type=int, default=150)
    parser.add_argument("--lookahead-days", type=int, default=14)
    parser.add_argument("--top-breakouts", type=int, default=35)
    args = parser.parse_args()
    if not 1 <= args.page_size <= 200 or not 1 <= args.max_free_agents <= 5000:
        parser.error("page-size must be 1-200 and max-free-agents must be 1-5000")
    try:
        import keyring
        from espn_api.basketball import League
    except ImportError:
        raise SystemExit("Missing Python dependencies. Run setup_windows.bat first.")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    league_id = args.league_id or cfg.get("league_id")
    if not league_id:
        league_id = int(input("Your ESPN fantasy league ID: ").strip())
    year = args.year or cfg.get("year", 2027)
    CONFIG.write_text(json.dumps({"league_id": league_id, "year": year}, indent=2), encoding="utf-8")
    swid = keyring.get_password(APP, "swid")
    espn_s2 = keyring.get_password(APP, "espn_s2")
    if args.reset_credentials or not swid or not espn_s2:
        print("Enter ESPN session cookies once; stored in Windows Credential Manager, not exported.")
        swid = getpass.getpass("SWID (keep braces): ").strip()
        espn_s2 = getpass.getpass("espn_s2: ").strip()
        if not swid or not espn_s2:
            raise SystemExit("Both cookie values are required")
        keyring.set_password(APP, "swid", swid)
        keyring.set_password(APP, "espn_s2", espn_s2)
    print(f"Reading season {year} league {league_id} (read-only) ...")
    try:
        league = League(league_id=int(league_id), year=year, swid=swid, espn_s2=espn_s2)
    except Exception as exc:
        raise SystemExit(f"Failed to read ESPN league ({type(exc).__name__}). Check season, league ID, and cookie expiry.") from None
    now = datetime.now(TZ)
    snapshot = build_snapshot(league, league_id, year, now,
                              max_free_agents=args.max_free_agents,
                              page_size=args.page_size,
                              lookahead=args.lookahead_days,
                              candidate_count=args.top_breakouts)
    target = BASE / f"espn_basketball_snapshot_{now.strftime('%Y%m%d_%H%M%S')}.json"
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    report = BASE / f"breakout_report_{now.strftime('%Y%m%d_%H%M%S')}.txt"
    with report.open("w", encoding="utf-8") as out:
        out.write("BREAKOUT WATCHLIST (not ESPN's Trending count; do not chase one-game stocks blindly)\n")
        out.write(f"Free-agent scan: {snapshot['free_agent_scan_coverage']}\n\n")
        for i, p in enumerate(snapshot["breakout_candidates"], 1):
            out.write(f"{i:02d}. {p['name']} ({p['proTeam']}) - latest FP {p['latest_fp']:.1f} / {p['latest_minutes']:.0f}m; ")
            out.write(f"projection {p['preseason_projected_fp_per_game']:.1f}; ")
            out.write(f"defensive FP {p['defensive_points_from_steals_and_blocks']:.0f}; ")
            out.write(f"14-day games {p['next_14_days_games']}; {p['availability_status']}; source={p['performance_source']}\n")
        out.write("\nWARNINGS:\n" + "\n".join(snapshot["warnings"]))
    print(f"JSON: {target}")
    print(f"Breakout summary: {report}")
    cov = snapshot["free_agent_scan_coverage"]
    print(f"Pool fetched: {cov['unique_unrostered_players']}; complete={cov['complete']}; duplicates excluded={cov['excluded_already_rostered']}")
    if snapshot["warnings"]:
        for msg in snapshot["warnings"]:
            print("WARNING:", msg)
    print("Upload the generated JSON to ChatGPT. Do not upload SWID/espn_s2 cookies.")


if __name__ == "__main__":
    main()
