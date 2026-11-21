# Professorsack — Fantasy review decision protocol (v2)

**League**: 2026–27 ESPN, 9 teams, H2H Points, daily locks. Active PG, SG, SF, PF, C, G, F and 3×UTIL; three bench; one IR; max four center-eligible players; seven adds per matchup week; one-day waivers. **Custom scoring**: PTS 1; FGM 2; FGA -1; FTM 1; FTA -1; 3PM 1; REB 1; AST 2; STL 4; BLK 4; TO -2.

## Must-check sequence before recommending “no changes”

1. **Freshness and coverage**: Check export timestamp, `free_agent_scan_coverage.complete`, number of available players, ESPN error warnings, and whether the export is newer than the previous analysis. Never claim exhaustive coverage if capped, failed or stale.
2. **League legitimacy**: Cross-reference player IDs against every roster. Separate `FREEAGENT` (immediate add), `WAIVERS` (claim) and unknown. Verify disputed names against ESPN UI before urging a transaction.
3. **Every plausible breakout**: Rank the obtainable free-agent/waiver pool by most recent fantasy points, improvement over projection, minutes, role and previous 7/15/30-day production—not just preseason FP/game. Check high-performing names missing from the exported pool via public box scores and explicitly say when fantasy availability is unverified.
4. **Don't chase unsustainable explosions**: Show minutes, games started, shot volume, rebounds, assists, steals and blocks. Quantify fantasy points from steals/blocks, and ask whether production relied on a temporary injury or new starting role. Regression risk must be discussed.
5. **Current matchup**: Read actual current box scores (if supported), opponent, score, injury designations, pending games and locked players. Don't sum bench games as usable production or assume that team-level standing points equal today's matchup score.
6. **Schedule**: Compare candidate's next 7–14 days. Optimize projected usable starts for every day and eligible PG/SG/SF/PF/C/G/F/UTIL position, including any day exceeding 10 starters or positional bottlenecks. Deduct points of displaced starters. Consider total starts, not simply number of NBA games.
7. **Opportunity cost**: Include the 7-add weekly cap, waiver claim timing, whether the player can be added in time, max four C-eligible roster players, injury/IR options, and the likelihood of losing a high-upside player permanently. Prefer a flexible streaming slot rather than losing a strong long-term asset.
8. **Compare candidates**: Estimate *net additional usable fantasy points* this matchup and next week for the best realistic options. Keep uncertainty explicit. A player with one big game isn't automatically better than a player with stable 30+ FP minutes.
9. **Actionable output**: Present a best move, timing, who to drop (if anyone), priority, projected net gains, long-term/streamer classification, and reasons **not** to make an impulsive move. If recommending no move, identify strongest alternatives considered and reasons rejected.
10. **Evidence labels**: Distinguish facts derived from ESPN snapshot, independently confirmed NBA reports and assumptions. If data is incomplete, identify what was not checked instead of claiming exhaustive analysis.

## Source limits

- The exporter does **not** expose ESPN's app-wide *Trending* count / add rate. `breakout_candidates` are calculated from **actual recent ESPN game stats**. `recent_league_transactions` covers only this league, not all ESPN users.
- The exporter currently uses ESPN league data and ESPN's NBA team scheduling metadata, not a second provider's forecasts. Supplement analyses with up-to-date trustworthy external news where possible.
- The exporter is read-only. It cannot place waivers, trades or lineup changes.
- Snapshots aren't live. ChatGPT's daily review automation cannot access new local JSON until it is uploaded.
- Public breaking injury reports and role news can change after an export. Verify before an irreversible move.
