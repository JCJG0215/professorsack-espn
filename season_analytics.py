"""Season/playoff projections from verified ESPN settings and NBA calendar.

All qualification forecasts are conditional scenarios, not calibrated odds.
Never assume a playoff bracket or dates if ESPN doesn't provide them.
"""
from collections import defaultdict
from datetime import date, timedelta
import random
import statistics

def qualification(snapshot, matchup, iterations=3000):
    s=snapshot.get("league_settings",{})
    teams=snapshot.get("teams",[])
    current=snapshot.get("matchup_period_id")
    last=s.get("regular_season_matchups")
    qualifiers=s.get("playoff_team_count")
    if not all(isinstance(x,int) and x>0 for x in (current,last,qualifiers)) or current>last or not teams or qualifiers>len(teams):
        return {"status":"unavailable","reason":"Missing or invalid regular season/playoff settings, or regular season has ended"}
    ids={t.get("team_id"):t for t in teams}
    if None in ids or len(ids)!=len(teams):
        return {"status":"unavailable","reason":"Team IDs incomplete"}
    divisions={t.get("division_id") for t in teams}
    if None in divisions or len(divisions)!=1:
        return {"status":"unavailable","reason":"Division/seed qualification rules are not verified"}
    own=next((i for i,t in ids.items() if t["team_name"]==snapshot.get("team_name_target")),None)
    if own is None:
        return {"status":"unavailable","reason":"Target missing"}
    played=defaultdict(list)
    future=defaultdict(list)
    seen=set()
    for m in snapshot.get("season_matchups",[]):
        p=m.get("period")
        a,b=m.get("home",{}),m.get("away",{})
        h,v=a.get("team_id"),b.get("team_id")
        if not isinstance(p,int) or p>last or h not in ids or v not in ids or h==v:
            continue
        key=(p,min(h,v),max(h,v))
        if key in seen: continue
        seen.add(key)
        if p<current:
            if m.get("winner") not in ("HOME","AWAY","TIE"):
                continue
            x,y=a.get("score"),b.get("score")
            if not isinstance(x,(int,float)) or not isinstance(y,(int,float)):
                continue
            played[h].append(x); played[v].append(y)
        else:
            future[p].append((h,v))
    # In a 9-team league, four games and one bye per ordinary matchup.
    for p in range(current,last+1):
        f=future.get(p,[])
        unique={x for pair in f for x in pair}
        if len(f)!=len(teams)//2 or len(unique)!=2*len(f):
            return {"status":"unavailable","reason":f"Regular season schedule incomplete or irregular in matchup {p}"}
    combined=[x for vals in played.values() for x in vals]
    if len(combined)<len(teams)*2 or any(len(played[i])<2 for i in ids):
        return {"status":"unavailable","reason":"Insufficient completed matchup scores"}
    if any(not isinstance(t.get(k),(int,float)) for t in teams for k in ("wins","losses","points_for")):
        return {"status":"unavailable","reason":"Standings incomplete"}
    center=statistics.mean(combined)
    strength={i:(sum(played[i])+3*center)/(len(played[i])+3) for i in ids}
    pooled=statistics.stdev(combined) if len(combined)>1 else center*.15
    sd={i:max(center*.08, .6*statistics.stdev(played[i])+.4*pooled) for i in ids}
    current_sim=matchup.get("conditional_simulation") or {}
    prob=current_sim.get("conditional_win_fraction")
    opp_name=matchup.get("opponent")
    opp=next((i for i,t in ids.items() if t["team_name"]==opp_name),None)
    rng=random.Random(2027)
    qualified=0; by_outcome={"win":[0,0],"loss":[0,0],"bye":[0,0]}
    wins_dist=[]
    for _ in range(iterations):
        records={i:[t["wins"]+.5*(t.get("ties") or 0),t["points_for"]] for i,t in ids.items()}
        outcome="bye"
        for p in range(current,last+1):
            for h,v in future[p]:
                x=max(0,rng.gauss(strength[h],sd[h]))
                y=max(0,rng.gauss(strength[v],sd[v]))
                if p==current and own in (h,v) and opp in (h,v) and isinstance(prob,(int,float)):
                    won=rng.random()<prob
                    if (x>y)!=(won if h==own else not won):
                        x,y=max(x,y),min(x,y)
                        if not (won if h==own else not won): x,y=y,x
                records[h][0]+=1 if x>y else .5 if x==y else 0
                records[v][0]+=1 if y>x else .5 if x==y else 0
                records[h][1]+=x; records[v][1]+=y
                if p==current and own in (h,v):
                    outcome="win" if (h==own and x>y) or (v==own and y>x) else "loss"
        order=sorted(ids,key=lambda i:(records[i][0],records[i][1]),reverse=True)
        ok=own in order[:qualifiers]
        qualified+=ok; by_outcome[outcome][0]+=ok; by_outcome[outcome][1]+=1
        wins_dist.append(records[own][0])
    wins_dist.sort()
    return {"status":"scenario_only","playoff_teams":qualifiers,"regular_season_matchups":last,
            "remaining_matchup_periods":last-current+1,
            "qualification_fraction":round(qualified/iterations,4),
            "conditional_on_current_matchup":{k:{"qualify_fraction":round(a/b,4),"samples":b} for k,(a,b) in by_outcome.items() if b},
            "final_wins_p10_p50_p90":[wins_dist[int(iterations*q)] for q in (.1,.5,.9)],
            "iterations":iterations,
            "assumptions":"Historical matchup scoring shrunk to league mean; equal matchup lengths assumed, no future roster/injury/stream changes; current matchup uses conditional simulation if present; one division, wins then points-for proxy for tiebreak; not calibrated."}

def playoff_calendar(snapshot, profiles, optimize, best):
    s=snapshot.get("league_settings",{})
    count=s.get("regular_season_matchups")
    periods=s.get("matchup_periods")
    calendar=snapshot.get("nba_team_calendar") or {}
    pd=snapshot.get("scoring_period_dates") or {}
    if not isinstance(count,int) or not isinstance(periods,dict) or not calendar:
        return {"status":"unavailable","reason":"Playoff period/calendar fields missing"}
    # ESPN scoring period is a day in this league; establish consistent date anchor.
    offsets=[]
    for k,v in pd.items():
        try: offsets.append(date.fromisoformat(v).toordinal()-int(k))
        except (ValueError,TypeError): pass
    if not offsets or len(set(offsets))!=1:
        return {"status":"unavailable","reason":"Cannot establish consistent scoring-period date mapping"}
    anchor=offsets[0]
    known=set()
    for games in calendar.values():
        known.update(g.get("scoring_period") for g in games)
    last=max((x for x in known if isinstance(x,int)),default=0)
    own=next(t for t in snapshot["teams"] if t["team_name"]==snapshot["team_name_target"])
    def player(p):
        # Hypothetical healthy roster, not a prediction of return.
        return {**p,"injuryStatus":"ACTIVE","lineupSlot":"BE","upcoming_games":calendar.get(p.get("proTeam"),[])}
    roster=[player(p) for p in own["roster"] if p.get("lineupSlot")!="IR" and p.get("playerId") in profiles]
    rounds=[]
    for key,val in periods.items():
        try: i=int(key)
        except (ValueError,TypeError): continue
        if i<=count or not isinstance(val,list) or len(val)!=2: continue
        a,b=val
        if not isinstance(a,int) or not isinstance(b,int) or b<a or b-a>31: continue
        start=date.fromordinal(anchor+a).isoformat(); end=date.fromordinal(anchor+b).isoformat()
        # Do not silently assign zero games when future calendar absent.
        row={"matchup_period":i,"start":start,"end":end}
        if b>last:
            row["status"]="schedule_not_available"
        else:
            days=[date.fromordinal(anchor+k).isoformat() for k in range(a,b+1)]
            row["status"]="conditional_on_calendar_and_health"
            row["roster_games"]=[{"name":p["name"],"games":sum(any(g.get("local_day")==d for g in p["upcoming_games"]) for d in days)} for p in roster]
            row["usable_starts_if_healthy"]=sum(best(optimize(roster,d,profiles))["starts"] for d in days)
        rounds.append(row)
    return {"status":"available" if rounds else "unavailable","rounds":sorted(rounds,key=lambda x:x["matchup_period"]),
            "playoff_teams":s.get("playoff_team_count"),"matchup_length_setting":s.get("playoff_matchup_period_length"),
            "latest_known_scoring_period":last,
            "assumptions":"Only calendar entries provided by ESPN; no future bracket opponents assumed. Healthy hypothetical active roster excluding current IR; actual rest/injury status and schedule coverage must be rechecked."}

def backtest(players, logs, profile, year):
    """Walk-forward validation on games with >=5 earlier observations.
    Disable ESPN prior to avoid leaking current aggregate stats into history.
    """
    errors=[]; baseline=[]; signed=[]
    for p in players:
        name=p.get("name","")
        # Logs have normalized names, profile handles the name normalization;
        # caller passes the logs matched by ID.
        g=logs.get(p.get("playerId"),[])
        if len(g)<8: continue
        for j in range(min(4,len(g)-5)):
            past=g[j+1:]
            from fantasy_analytics import norm
            f=profile({"name":name},{norm(name):past},year)
            if f["mean"] is None: continue
            actual=g[j]["fp"]
            errors.append(abs(f["mean"]-actual))
            baseline.append(abs(statistics.mean(x["fp"] for x in past[:10])-actual))
            signed.append(f["mean"]-actual)
    if not errors: return {"status":"unavailable","reason":"No sufficient fresh matched NBA logs"}
    return {"status":"walk_forward","samples":len(errors),
            "model_mae":round(statistics.mean(errors),2),
            "last_10_mean_mae":round(statistics.mean(baseline),2),
            "model_bias":round(statistics.mean(signed),2),
            "assumptions":"Played games only; excludes ESPN prior and DNPs; not a live production backtest or win-probability calibration."}
