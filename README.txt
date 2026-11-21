Version 2.1 fixes two bugs found in the October 22, 2026 real ESPN export:
- Free-agent breakout report was empty despite many players having played because ESPN returned season totals but omitted individual game logs. For ONE-game season totals only, the exporter uses the season line as a tagged fallback (date unknown); for 2+ games it never presents a season total as a single performance.
- Matchup box-score fields contained Team object strings instead of resolved names/IDs.

IMPORTANT: ESPN proprietary Trending counts and per-game historical free-agent logs are still not guaranteed available. Recheck live roster and waiver status in ESPN.

PROFESSORSACK ESPN FANTASY BASKETBALL EXPORTER -- VERSION 2.0

WHAT'S NEW
- Pages through all obtainable ESPN league free agents + waiver players,
  rather than only the top 100 ownership-sorted players. Default cap 1200.
- Excludes players already rostered by any team in your league (ESPN sometimes
  returns stale/ambiguous entries, so each player ID is cross-checked).
- Exports 14-day NBA team schedules for available players AND rostered players.
- Includes each player's most recent 7 NBA box scores with fantasy points,
  minutes, FG attempts, steals, blocks, and other league-relevant stats.
- Adds ranked breakout_candidates and a human-readable breakout_report TXT.
- Captures actual current ESPN matchup box scores where ESPN supplies them.
- Includes your league's recent add/drop transaction activity (where supported).
- Includes coverage stats and warnings. Will not silently call a capped/failed
  scan a complete free-agent search.

HOW TO INSTALL (WINDOWS)
1. Install Python 3.11 or newer, if needed (Python launcher command: py -3).
2. Unzip this folder anywhere on your PC.
3. Double-click setup_windows.bat (requires internet on first setup).
4. Double-click export_windows.bat.
5. If this is your FIRST installation, enter ESPN league ID, SWID, espn_s2.
   To find cookies, use your own ESPN logged-in Chrome/Edge window:
   F12 > Application > Cookies > ESPN domain. Your SWID usually has braces.
   Do NOT share the cookies with ChatGPT or anyone else.
6. Upload the newest espn_basketball_snapshot_*.json file to ChatGPT.
   You can also inspect breakout_report_*.txt without uploading it.

EXISTING INSTALL / PREVIOUS CREDENTIALS
- If v2 is extracted to a new folder, league ID may need to be entered again.
- Credentials use the SAME keyring entry as the original exporter, so existing
  saved cookies should work on the same Windows user profile automatically.
- Cookies are stored in Windows Credential Manager, not JSON.
- If cookies expire: py -3 export_espn.py --reset-credentials

ADVANCED / LIMITS
  py -3 export_espn.py --max-free-agents 2000 --page-size 150 --lookahead-days 14
  py -3 export_espn.py --year 2028

Default 1200 is an upper bound. If ESPN stops early or ignores pagination, the
JSON reports coverage.complete=false. Scan may generate a few MB of JSON and
require several ESPN read requests. No transactions/add-drops occur.

The watchlist is DERIVED from recent game performance, not from ESPN's own
proprietary Trending add counts or transaction activity. A high FP total inflated
by steals/blocks is flagged; a breakout is not a forward projection. The data
cannot predict injuries or perfectly resolve waiver status and future day-by-day
lineups. Check the ESPN Add/Claim button, your pending claims, weekly remaining
moves, and your scheduled lineup when making transactions.

ChatGPT's daily scheduled review DOES NOT automatically receive files created
on your PC. Upload each fresh JSON yourself before a full league-specific review.

READ-ONLY: no ESPN transactions, no uploading cookies, no background uploading.
