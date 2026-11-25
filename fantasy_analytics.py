"""Read-only fantasy analytics. No ESPN credentials or transactions.
NBA logs supplement, never replace, ESPN roster and availability.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import statistics
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SLOTS = ("PG", "SG", "SF", "PF", "C", "G", "F", "UT", "UT", "UT")
UNAVAILABLE = {"OUT", "SUSPENSION", "SUSPENDED", "INACTIVE", "DOUBTFUL"}
ACTIVE = {"ACTIVE", "DAY_TO_DAY", "DTD", "QUESTIONABLE", "PROBABLE"}
STAT_MAP = {"3PM": "FG3M"}
def num(x, default=0.0):
    try:
        n = float(x)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c.lower() for c in s if c.isalnum() and not unicodedata.combining(c))

def fp(row, scoring):
    return sum(num(row.get(STAT_MAP.get(k,k))) * num(v) for k,v in scoring.items())

def days_between(start, end):
    return [(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1)]

def fetch_logs(snapshot):
    """Try nba_api, then the same public NBA endpoint using requests. No private headers."""
    season = int(snapshot["season"])
    label = f"{season-1}-{str(season)[-2:]}"
    cutoff = datetime.fromisoformat(snapshot["exported_at"]).date()
    attempts = []
    rows = None
    source = None
    try:
        from nba_api.stats.endpoints import leaguegamelog
        response = leaguegamelog.LeagueGameLog(season=label, season_type_all_star="Regular Season",
                                               player_or_team_abbreviation="P", timeout=20)
        data = response.get_normalized_dict()["LeagueGameLog"]
        rows = data
        source = "nba_api LeagueGameLog"
    except Exception as exc:
        attempts.append(type(exc).__name__)
    if not rows:
        try:
            import requests
            response = requests.get("https://stats.nba.com/stats/leaguegamelog",
                params={"Counter":0,"Direction":"DESC","LeagueID":"00","PlayerOrTeam":"P",
                        "Season":label,"SeasonType":"Regular Season","Sorter":"DATE"},
                headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.nba.com/",
                         "Origin":"https://www.nba.com","Accept":"application/json"},
                timeout=(8,20))
            response.raise_for_status()
            result = response.json()["resultSets"][0]
            rows = [dict(zip(result["headers"], r)) for r in result["rowSet"]]
            source = "NBA stats LeagueGameLog HTTP"
        except Exception as exc:
            attempts.append(type(exc).__name__)
    if not rows:
        return {}, {"status":"unavailable","attempt_errors":attempts}
    groups = defaultdict(dict)
    latest = None
    for r in rows:
        try:
            day = datetime.fromisoformat(str(r["GAME_DATE"])[:10]).date()
            if day >= cutoff or day < cutoff-timedelta(days=150) or num(r.get("MIN"))<=0:
                continue
            key = norm(r["PLAYER_NAME"])
            pid = str(r["PLAYER_ID"])
            game = str(r["GAME_ID"])
        except (KeyError,ValueError,TypeError):
            continue
        if not key or not all(STAT_MAP.get(k,k) in r and r[STAT_MAP.get(k,k)] is not None for k in snapshot["scoring"]):
            continue
        latest = max(latest or day, day)
        groups[key].setdefault(pid,{})[game] = {
            "date":day.isoformat(),"fp":round(fp(r,snapshot["scoring"]),2),
            "minutes":num(r["MIN"]),"stocks_fp":sum(num(r.get(k))*num(snapshot["scoring"].get(k)) for k in ("STL","BLK")),
            "stats":{k:num(r.get(STAT_MAP.get(k,k))) for k in snapshot["scoring"]},
            "nba_team":r.get("TEAM_ABBREVIATION"),"nba_player_id":pid}
    if latest is None or (cutoff-latest).days>4:
        return {}, {"status":"stale_or_empty","source":source,"latest_game":str(latest),"attempt_errors":attempts}
    # Exact normalized full name, unique NBA identity only; do not fuzzy-match.
    logs = {name:sorted(next(iter(ids.values())).values(),key=lambda x:x["date"],reverse=True)[:30]
            for name,ids in groups.items() if len(ids)==1}
    return logs, {"status":"ok","source":source,"latest_game":str(latest),"matched_name_pool":len(logs),
                  "ambiguous_names":sum(len(ids)>1 for ids in groups.values()),"attempt_errors":attempts}

def profile(p, logs, year):
    """Recency-weighted minutes and rate, shrink small samples to ESPN prior.
    Defensive scoring shrunk toward longer sample; no extrapolation from DNPs.
    """
    g = logs.get(norm(p.get("name")), [])
    summary = p.get("stats_summary") or {}
    def stat(suffix):
        return summary.get(f"{year}_{suffix}") or {}
    season = stat("total")
    projected = stat("projected")
    prior = num(p.get("projected_avg_points"),-1)
    actual = num(p.get("avg_points"),-1)
    prior_min = num((projected.get("avg") or {}).get("MIN"))
    season_min = num((season.get("avg") or {}).get("MIN"))
    recent_min = num((stat("last_15").get("avg") or {}).get("MIN"))
    recent = num(stat("last_15").get("applied_avg"),-1)
    gp = num((season.get("avg") or {}).get("GP"))
    if g:
        short = g[:8]
        weights = [0.85**i for i in range(len(short))]
        total_w = sum(weights)
        minutes = sum(w*x["minutes"] for w,x in zip(weights,short))/total_w
        # Rate across minutes, not arithmetic mean of game rates.
        mins = sum(w*x["minutes"] for w,x in zip(weights,short))
        nonstocks = sum(w*(x["fp"]-x["stocks_fp"]) for w,x in zip(weights,short))/mins
        recent_stocks = sum(w*x["stocks_fp"] for w,x in zip(weights,short))/mins
        long_stocks = sum(x["stocks_fp"] for x in g)/sum(x["minutes"] for x in g)
        rate = nonstocks + 0.5*recent_stocks + 0.5*long_stocks
        strength = len(short)/(len(short)+5)
        if prior>=0 and prior_min>0:
            rate = strength*rate+(1-strength)*prior/prior_min
            minutes = strength*minutes+(1-strength)*prior_min
        mean = max(0,rate*minutes)
        spread = statistics.stdev(x["fp"] for x in g) if len(g)>=3 else 12.0
        source = "NBA logs + ESPN prior" if prior>=0 and prior_min>0 else "NBA logs"
        short_mean = statistics.mean(x["fp"] for x in g[:5])
        long_mean = statistics.mean(x["fp"] for x in g)
        return {"mean":round(mean,2),"sd":round(max(7,spread),2),"minutes":round(minutes,2),
                "last5":round(short_mean,2),"last20":round(statistics.mean(x["fp"] for x in g[:20]),2),
                "long_mean":round(long_mean,2),"recent_games":len(g),"minutes_last5":round(statistics.mean(x["minutes"] for x in g[:5]),2),
                "stocks_last5":round(statistics.mean(x["stocks_fp"] for x in g[:5]),2),
                "source":source,"logs":g[:20]}
    # ESPN aggregate fallback: no claim of game-log coverage.
    values = [(actual,min(0.5,gp/30)),(recent,0.25),(prior,0.5)]
    values = [(v,w) for v,w in values if v>=0 and w>0]
    mean = sum(v*w for v,w in values)/sum(w for _,w in values) if values else None
    return {"mean":round(mean,2) if mean is not None else None,"sd":12.0,
            "minutes":recent_min or season_min or prior_min or None,
            "source":"ESPN aggregates; variance assumed","recent_games":0,"logs":[]}

def scheduled(p, day):
    return any(g.get("local_day")==day for g in p.get("upcoming_games",[]))

def available(p):
    return p.get("lineupSlot")!="IR" and p.get("injuryStatus") in ACTIVE

def mask_slots(p):
    return [i for i,s in enumerate(SLOTS) if s in (p.get("eligibleSlots") or [])]

def assignment(players, day, profiles):
    """Exact maximum-weight assignment of unique players to active slots."""
    dp={0:(0.0,[])}
    seen=set()
    for p in players:
        pid=p.get("playerId")
        if pid is None or pid in seen or not available(p) or not scheduled(p,day):
            continue
        seen.add(pid)
        f=profiles[pid]
        value=f["mean"]
        if value is None:
            continue
        new=dp.copy()
        for mask,(score,line) in dp.items():
            for i in mask_slots(p):
                bit=1<<i
                if mask&bit: continue
                key=mask|bit
                candidate=(score+value,line+[{"id":pid,"name":p["name"],"slot":SLOTS[i],"fp":value,
                                               "status":p["injuryStatus"]}])
                if key not in new or (candidate[0],len(candidate[1]))>(new[key][0],len(new[key][1])):
                    new[key]=candidate
        dp=new
    return dp

def best(dp):
    score,line=max(dp.values(),key=lambda x:(x[0],len(x[1])))
    return {"points":round(score,2),"starts":len(line),"lineup":line}

def insertion_cache(dp):
    """Precompute the best existing assignment that leaves each slot open."""
    base=best(dp)
    open_slots=[None]*len(SLOTS)
    for mask,(score,line) in dp.items():
        for i in range(len(SLOTS)):
            if mask&(1<<i): continue
            old=open_slots[i]
            if old is None or (score,len(line))>(old[0],len(old[1])):
                open_slots[i]=(score,line)
    return base,open_slots

def add_to_dp(cache,p,day,profiles):
    base,open_slots=cache
    if not available(p) or not scheduled(p,day) or profiles[p["playerId"]]["mean"] is None:
        return base
    value=profiles[p["playerId"]]["mean"]
    score,line=base["points"],base["lineup"]
    for i in mask_slots(p):
        if open_slots[i] is None: continue
        v,l=open_slots[i]
        if v+value>score+1e-7 or (abs(v+value-score)<1e-7 and len(l)+1>len(line)):
            score=v+value
            line=l+[{"id":p["playerId"],"name":p["name"],"slot":SLOTS[i],"fp":value,"status":p["injuryStatus"]}]
    return {"points":round(score,2),"starts":len(line),"lineup":line}

def simulate(ours,theirs,profiles,scores,seed=1740867329,n=3000):
    """Conditional illustrative Monte Carlo; not a calibrated win probability.
    Normal per-game scores and assumed DTD participation. Fixed optimized lineups.
    """
    if scores is None: return None
    rng=random.Random(seed)
    wins=ties=0
    margins=[]
    def draw(days):
        total=0
        for d in days:
            for p in d["lineup"]:
                chance={"DAY_TO_DAY":.65,"DTD":.65,"QUESTIONABLE":.5,"PROBABLE":.9}.get(p["status"],1)
                if rng.random()<=chance:
                    total+=rng.gauss(p["fp"],profiles[p["id"]]["sd"])
        return total
    for _ in range(n):
        m=scores[0]+draw(ours)-scores[1]-draw(theirs)
        wins+=m>0
        ties+=m==0
        margins.append(m)
    margins.sort()
    return {"conditional_win_fraction":round(wins/n,4),"tie_fraction":ties/n,
            "margin_p10":round(margins[int(n*.1)],1),"margin_p50":round(margins[n//2],1),
            "margin_p90":round(margins[int(n*.9)],1),"iterations":n,
            "limits":"Not calibrated. Fixed lineups; independent normal scores; OUT excluded; DTD .65, questionable .5, probable .9 assumed; no opponent adds, return dates, substitutions, or correlated injuries."}

def count_centers(roster):
    return sum("C" in (p.get("eligibleSlots") or []) for p in roster)

def beam_plan(roster,drop,pool,profiles,week,budget):
    """Bounded beam search on one roster slot. Conditional future availability.
    No re-adds (waiver exposure); one acquisition per day; no acquisition on zero-gain day.
    """
    if not week or budget<=0: return None
    other=[p for p in roster if p["playerId"]!=drop["playerId"]]
    pool=[p for p in pool if count_centers(other+[p])<=4]
    opts={p["playerId"]:p for p in [drop]+pool}
    hold=drop["playerId"]
    daily=[]
    for day in week:
        dp=insertion_cache(assignment(other,day,profiles))
        vals={pid:add_to_dp(dp,p,day,profiles) for pid,p in opts.items()}
        top=sorted((pid for pid in vals if pid!=hold),key=lambda pid:vals[pid]["points"],reverse=True)[:25]
        daily.append((vals,top))
    # score, current, adds, used players, planned moves, starts
    beam=[(0.0,hold,0,frozenset([hold]),[],0)]
    for day,(vals,top) in zip(week,daily):
        nxt=[]
        for score,cur,adds,used,moves,starts in beam:
            v=vals[cur]
            nxt.append((score+v["points"],cur,adds,used,moves,starts+v["starts"]))
            if adds>=budget: continue
            for pid in top:
                q=vals[pid]
                if pid in used or q["points"]<=v["points"]+1e-7: continue
                nxt.append((score+q["points"],pid,adds+1,used|{pid},
                            moves+[{"day":day,"drop":opts[cur]["name"],"add":opts[pid]["name"],
                                    "same_day_increment":round(q["points"]-v["points"],2)}],starts+q["starts"]))
        nxt.sort(key=lambda x:(x[0],-x[2]),reverse=True)
        unique={}
        for x in nxt:
            key=(x[1],x[2],x[3])
            if key not in unique: unique[key]=x
            if len(unique)>=60: break
        beam=list(unique.values())
    score,_,adds,_,moves,starts=beam[0]
    baseline=sum(vals[hold]["points"] for vals,_ in daily)
    base_starts=sum(vals[hold]["starts"] for vals,_ in daily)
    return {"starting_drop":drop["name"],"moves":moves,"adds":adds,"incremental_points":round(score-baseline,2),
            "incremental_starts":starts-base_starts,"method":"Bounded beam search; future FA status and lineup health conditional; not an exhaustive global optimizer."}

def analyze(snapshot, logs, log_status):
    stamp=datetime.fromisoformat(snapshot["exported_at"])
    today=stamp.date()
    # Morning snapshot only; after tipoff current score may already include games.
    include_today=stamp.hour<12
    start=today if include_today else today+timedelta(days=1)
    end=today+timedelta(days=6-today.weekday())
    week=days_between(start,end) if start<=end else []
    nextweek=days_between(end+timedelta(days=1),end+timedelta(days=7))
    teams=snapshot["teams"]
    own=next(t for t in teams if t["team_name"]==snapshot["team_name_target"])
    roster=own["roster"]
    owned={p.get("playerId") for t in teams for p in t["roster"]}
    raw={p["playerId"]:p for p in snapshot.get("free_agents",[]) if p.get("playerId") is not None and p["playerId"] not in owned}
    all_players=list(raw.values())+[p for t in teams for p in t["roster"]]
    name_ids=defaultdict(set)
    for p in all_players:
        name_ids[norm(p.get("name"))].add(p.get("playerId"))
    logs={k:v for k,v in logs.items() if len(name_ids[k])==1}
    profiles={p["playerId"]:profile(p,logs,snapshot["season"]) for p in all_players}
    pool=[p for p in raw.values() if p.get("availability_status")=="FREEAGENT" and available(p) and profiles[p["playerId"]]["mean"] is not None]
    schedule_days={g["local_day"] for p in list(raw.values())+[p for t in teams for p in t["roster"]] for g in p.get("upcoming_games",[]) if g.get("local_day")}
    last_schedule=max(schedule_days,default="")
    nextweek=[d for d in nextweek if d<=last_schedule]
    schedule_complete=bool(last_schedule and (not week or last_schedule>=week[-1]))
    current_score=None
    opponent=None
    score_source=None
    for source in ("current_matchup_box_scores","matchups"):
        for m in snapshot.get(source,[]):
            if own["team_name"] not in (m.get("home_team"),m.get("away_team")): continue
            home=m.get("home_team")==own["team_name"]
            name=m.get("away_team" if home else "home_team")
            opponent=next((t for t in teams if t["team_name"]==name),None)
            a=m.get("home_score" if home else "away_score")
            b=m.get("away_score" if home else "home_score")
            if isinstance(a,(int,float)) and isinstance(b,(int,float)) and opponent:
                current_score=(a,b)
                score_source=source
                break
        if current_score is not None: break
    baseline=[{"day":d,**best(assignment(roster,d,profiles))} for d in week]
    oppdays=[{"day":d,**best(assignment(opponent["roster"],d,profiles))} for d in week] if opponent else []
    base_total=sum(x["points"] for x in baseline)
    # Lower bound: activity history may be truncated, and raw rules may conflict.
    monday=today-timedelta(days=today.weekday())
    adds=set()
    for t in snapshot.get("recent_league_transactions",[]):
        try:
            if t["team_name"]==own["team_name"] and "ADD" in str(t["action"]).upper() and datetime.fromisoformat(t["date"]).date()>=monday:
                adds.add((t["date"],str(t.get("player"))))
        except (TypeError,ValueError,KeyError):
            continue
    assumed_budget=max(0,7-len(adds))
    def compact(p):
        f=profiles[p["playerId"]]
        return {"id":p["playerId"],"name":p["name"],"status":p.get("availability_status"),
                "injury":p.get("injuryStatus"),"position":p.get("eligibleSlots"),
                "games_this_week":[d for d in week if scheduled(p,d)],
                "games_next_week_covered":[d for d in nextweek if scheduled(p,d)],
                **{k:v for k,v in f.items() if k!="logs"}}
    ranked=sorted(raw.values(),key=lambda p:profiles[p["playerId"]]["mean"] if profiles[p["playerId"]]["mean"] is not None else -1,reverse=True)
    breakouts=sorted([p for p in pool if profiles[p["playerId"]]["recent_games"]>=5],
       key=lambda p:profiles[p["playerId"]]["last5"]-profiles[p["playerId"]]["long_mean"],reverse=True)
    # All free agents screened for each replaceable non-IR roster spot.
    moves=[]
    drops=[p for p in roster if p.get("lineupSlot")!="IR" and profiles[p["playerId"]]["mean"] is not None and profiles[p["playerId"]]["mean"]<35]
    for drop in drops:
        rest=[p for p in roster if p["playerId"]!=drop["playerId"]]
        dps=[insertion_cache(assignment(rest,d,profiles)) for d in week+nextweek]
        nextbase=sum(best(assignment(roster,d,profiles))["points"] for d in nextweek)
        for p in pool:
            if count_centers(rest+[p])>4: continue
            result=[add_to_dp(dp,p,d,profiles) for dp,d in zip(dps,week+nextweek)]
            w=result[:len(week)]
            delta=sum(x["points"] for x in w)-base_total
            delta_starts=sum(x["starts"] for x in w)-sum(x["starts"] for x in baseline)
            next_delta=sum(x["points"] for x in result[len(week):])-nextbase
            moves.append({"drop":drop["name"],"add":p["name"],"add_id":p["playerId"],"drop_id":drop["playerId"],
                          "net_points":round(delta,2),"net_starts":delta_starts,
                          "next_week_covered_net_points":round(next_delta,2),
                          "drop_projected_fp":profiles[drop["playerId"]]["mean"],"add_projected_fp":profiles[p["playerId"]]["mean"]})
    moves.sort(key=lambda m:m["net_points"],reverse=True)
    ros=sorted(moves,key=lambda m:(m["add_projected_fp"]-m["drop_projected_fp"],m["net_points"]),reverse=True)
    plan=None
    if drops and schedule_complete and assumed_budget>0:
        lowest=min(drops,key=lambda p:(p.get("injuryStatus") not in ACTIVE,profiles[p["playerId"]]["mean"]))
        plan=beam_plan(roster,lowest,pool,profiles,week,assumed_budget)
    matchup_forecast=None
    if current_score and schedule_complete and include_today:
        matchup_forecast=simulate(baseline,oppdays,profiles,current_score)
        if moves and assumed_budget>0:
            m=moves[0]
            changed=[p for p in roster if p["playerId"]!=m["drop_id"]]+[raw[m["add_id"]]]
            changed_days=[best(assignment(changed,d,profiles)) for d in week]
            matchup_forecast["best_single_move_conditional_simulation"]=simulate(changed_days,oppdays,profiles,current_score)
    result={"version":"1.1","exported_at":snapshot["exported_at"],"nba_data":log_status,
            "coverage":{"deduplicated_unrostered":len(raw),"immediate_healthy_candidates":len(pool),
                        "nba_log_matched":sum(profiles[p]["recent_games"]>0 for p in profiles),
                        "profile_count":len(profiles),"last_schedule_day":last_schedule,
                        "week_complete_by_last_date":schedule_complete,"next_week_covered_days":nextweek},
            "matchup":{"opponent":opponent["team_name"] if opponent else None,"score":current_score,"score_source":score_source,
                       "ours":baseline,"opponent_days":oppdays,"conditional_simulation":matchup_forecast,
                       "our_remaining_fp":round(base_total,2),"opponent_remaining_fp":round(sum(x["points"] for x in oppdays),2)},
            "acquisitions":{"observed_adds_lower_bound":len(adds),"assumed_remaining_upper_bound":assumed_budget,
                            "warning":"Verify ESPN actual acquisitions/waivers; activity may be truncated and settings conflict."},
            "roster_profiles":[compact(p) for p in roster],
            "top_available_by_sustainable_model":[compact(p) for p in ranked[:40]],
            "top_breakouts":[compact(p) for p in breakouts[:25]],
            "top_immediate_moves":moves[:30],"top_model_upgrades":ros[:30],"one_slot_streaming_plan":plan,
            "player_profiles":{str(k):v for k,v in profiles.items()},
            "limitations":["No automatic transactions; availability is snapshot only.",
                           "Daily optimization assumes unlocked future lineups, excludes IR and current OUT players across horizon.",
                           "Before noon Toronto assumed no games started; check tipoff and score before use. Later snapshots omit today; no win simulation.",
                           "Week is Monday-Sunday per user rules, not verified ESPN playoff round.",
                           "Missing schedule is unknown, not evidence of no game; last-date coverage is necessary but not sufficient.",
                           "Season qualification and walk-forward model results are conditional, not calibrated win probabilities.",
                           "Waiver candidates are watchlist only, not immediate streaming options. Protect high-upside players even if model below 35."]}
    try:
        from season_analytics import qualification, playoff_calendar, backtest
        result["season_qualification"]=qualification(snapshot,result["matchup"])
        result["playoff_calendar"]=playoff_calendar(snapshot,profiles,assignment,best)
        result["walk_forward_backtest"]=backtest(all_players,{p["playerId"]:logs.get(norm(p.get("name")),[]) for p in all_players},profile,snapshot["season"])
    except Exception as exc:
        result["season_analytics_status"]={"status":"unavailable","error_type":type(exc).__name__}
    return result

def self_test():
    day="2026-11-25"
    def p(pid,slots,status="ACTIVE"):
        return {"playerId":pid,"name":str(pid),"eligibleSlots":slots,"injuryStatus":status,"upcoming_games":[{"local_day":day}]}
    a,b,c=p(1,["PG","G","UT"]),p(2,["PF","F","UT"]),p(3,["PF","F","UT"],"OUT")
    profiles={1:{"mean":30},2:{"mean":25},3:{"mean":100}}
    dp=assignment([a,a,b,c],day,profiles)
    assert best(dp)["points"]==55 and best(dp)["starts"]==2
    assert add_to_dp(insertion_cache(assignment([a],day,profiles)),b,day,profiles)["points"]==55
    assert fp({"PTS":20,"FGM":8,"FGA":15,"FG3M":2},{"PTS":1,"FGM":2,"FGA":-1,"3PM":1})==23
    assert norm("Nikola Jokić")==norm("Nikola Jokic")
    print("Analytics self-tests passed.")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("snapshot",nargs="?")
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--offline",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        self_test()
        if not args.snapshot: return
    path=Path(args.snapshot)
    data=json.loads(path.read_text(encoding="utf-8"))
    logs,status=({},{"status":"offline"}) if args.offline else fetch_logs(data)
    data["analytics"]=analyze(data,logs,status)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding="utf-8")
    temp.replace(path)
    print("Analytics completed; NBA log status:",status["status"])

if __name__=="__main__":
    main()
