"""Archive a small read-only forecast and evaluate prior-day player predictions."""
from __future__ import annotations
import argparse
import json
from datetime import datetime,timedelta
from pathlib import Path
import statistics

def write_json(path,value):
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding="utf-8")
    tmp.replace(path)

def digest(data):
    a=data["analytics"]
    stamp=datetime.fromisoformat(data["exported_at"])
    day=stamp.date().isoformat()
    profiles=a.get("player_profiles",{})
    players=[]
    seen=set()
    for team in data.get("teams",[]):
        for p in team.get("roster",[]):
            pid=str(p.get("playerId"))
            prof=profiles.get(pid,{})
            if pid in seen or prof.get("mean") is None: continue
            if not any(g.get("local_day")==day for g in p.get("upcoming_games",[])): continue
            if p.get("injuryStatus") not in ("ACTIVE","DAY_TO_DAY","DTD","QUESTIONABLE","PROBABLE"): continue
            if p.get("lineupSlot")=="IR": continue
            seen.add(pid)
            players.append({"id":pid,"name":p["name"],"predicted_fp":prof["mean"],
                            "source":prof.get("source"),"status":p.get("injuryStatus")})
    return {"exported_at":data["exported_at"],"date":day,"model":a.get("version"),
            "pregame_assumption":stamp.hour<12,"predictions":players,
            "matchup":{k:a.get("matchup",{}).get(k) for k in ("opponent","score","our_remaining_fp","opponent_remaining_fp","conditional_simulation")},
            "nba_data":a.get("nba_data"),"evaluation":a.get("prior_day_forecast_evaluation")}

def evaluate(data,previous):
    expected=(datetime.fromisoformat(data["exported_at"]).date()-timedelta(days=1)).isoformat()
    if previous.get("date")!=expected or not previous.get("pregame_assumption"):
        return {"status":"unavailable","reason":"Missing or non-pregame prior-day forecast"}
    a=data["analytics"]
    profiles=a.get("player_profiles",{})
    errors=[]; signed=[]; missing=0
    for p in previous.get("predictions",[]):
        prof=profiles.get(str(p["id"]),{})
        games=[x for x in prof.get("logs",[]) if x.get("date")==expected]
        if len(games)!=1:
            missing+=1; continue
        error=p["predicted_fp"]-games[0]["fp"]
        errors.append(abs(error)); signed.append(error)
    if not errors:
        return {"status":"unavailable","forecast_date":expected,"unmatched_or_dnp":missing,"reason":"No matching independent NBA game logs"}
    return {"status":"evaluated","forecast_date":expected,"samples":len(errors),"unmatched_or_dnp":missing,
            "mae_fp":round(statistics.mean(errors),2),"bias_fp":round(statistics.mean(signed),2),
            "limits":"Pregame assumption before noon; played games only; DNPs and unmatched logs excluded; not an evaluation of transaction decisions."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--snapshot",required=True,type=Path)
    ap.add_argument("--previous",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    data=json.loads(args.snapshot.read_text(encoding="utf-8"))
    if not isinstance(data.get("analytics"),dict):
        print("No analytics available; skip forecast history.")
        return
    try:
        prior=json.loads(args.previous.read_text(encoding="utf-8"))
        evaluation=evaluate(data,prior)
    except (OSError,ValueError,KeyError,TypeError):
        evaluation={"status":"unavailable","reason":"Previous daily forecast absent or invalid"}
    data["analytics"]["prior_day_forecast_evaluation"]=evaluation
    write_json(args.output,digest(data))
    write_json(args.snapshot,data)
    print("Forecast history evaluation:",evaluation["status"])

if __name__=="__main__":
    main()
