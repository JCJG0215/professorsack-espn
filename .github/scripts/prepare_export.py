"""Validate today's matching export pair and prepare stable filenames."""
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "prepared"
TORONTO = ZoneInfo("America/Toronto")
PATTERN = re.compile(r"^espn_basketball_snapshot_(\d{8}_\d{6})\.json$")


def main():
    now = datetime.now(timezone.utc)
    candidates = []
    for snap in ROOT.rglob("espn_basketball_snapshot_*.json"):
        match = PATTERN.fullmatch(snap.name)
        if not match or OUTPUT in snap.parents:
            continue
        suffix = match.group(1)
        report = snap.with_name(f"breakout_report_{suffix}.txt")
        if not report.is_file():
            continue
        try:
            payload = json.loads(snap.read_text(encoding="utf-8"))
            timestamp = datetime.fromisoformat(payload["exported_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("exported_at must have timezone")
            if payload.get("team_name_target") != "Professorsack":
                raise ValueError("wrong ESPN team")
            if timestamp.astimezone(TORONTO).date() != now.astimezone(TORONTO).date():
                raise ValueError("not today's Toronto export")
            if not timedelta(minutes=-5) <= now - timestamp.astimezone(timezone.utc) <= timedelta(minutes=90):
                raise ValueError("export not freshly produced")
            stamp = datetime.strptime(suffix, "%Y%m%d_%H%M%S").replace(tzinfo=TORONTO)
            if abs((timestamp - stamp).total_seconds()) > 120:
                raise ValueError("filename and JSON timestamp disagree")
            candidates.append((timestamp, snap, report, suffix))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Ignoring stale/invalid file {snap.name}: {exc}")
    if not candidates:
        raise SystemExit("No fresh matching JSON/TXT export; refusing upload.")
    timestamp, snap, report, suffix = max(candidates, key=lambda x: x[0])
    OUTPUT.mkdir(exist_ok=True)
    shutil.copyfile(snap, OUTPUT / "professorsack_latest.json")
    content = report.read_text(encoding="utf-8-sig", errors="replace")
    (OUTPUT / "professorsack_breakout_latest.txt").write_text(
        f"EXPORT_RUN_ID: {suffix}\nJSON_EXPORTED_AT: {timestamp.isoformat()}\n" + content,
        encoding="utf-8",
    )
    # Analytics is optional: never block the known-working ESPN export.
    prepared = OUTPUT / "professorsack_latest.json"
    try:
        subprocess.run([sys.executable, str(ROOT / "fantasy_analytics.py"),
                        str(prepared), "--self-test"], check=True, timeout=150,
                       env={k: v for k, v in __import__("os").environ.items()
                            if k not in {"ESPN_S2", "ESPN_SWID", "RCLONE_CONFIG_TEXT", "RCLONE_CONFIG"}})
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"Optional analytics unavailable: {type(exc).__name__}; publishing original ESPN export.")
    print(f"Prepared fresh matching export: {suffix}; no credentials printed.")


if __name__ == "__main__":
    main()
