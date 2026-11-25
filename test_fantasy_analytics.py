"""Synthetic end-to-end analytics tests, no network or credentials."""
import unittest
from fantasy_analytics import analyze, assignment, best, insertion_cache, add_to_dp, profile, simulate

DAY="2026-11-25"
THU="2026-11-26"
FRI="2026-11-27"
SUN="2026-11-29"

def player(pid,name,points,days,slots=("PG","G","UT"),status="ACTIVE",owner="ONTEAM"):
    return {"playerId":pid,"name":name,"position":slots[0],"eligibleSlots":list(slots),
            "lineupSlot":"BE" if owner=="ONTEAM" else "",
            "injuryStatus":status,"availability_status":owner,
            "avg_points":points,"projected_avg_points":points,
            "stats_summary":{"2027_total":{"applied_avg":points,"avg":{"GP":15,"MIN":30}},
                             "2027_projected":{"applied_avg":points,"avg":{"MIN":30}},
                             "2027_last_15":{"applied_avg":points,"avg":{"MIN":30}}},
            "upcoming_games":[{"local_day":d} for d in days]}

class AnalyticsTest(unittest.TestCase):
    def test_assignment_congestion_and_ir(self):
        p=[player(i,str(i),i+20,[DAY],("PG","G","UT")) for i in range(1,9)]
        p[0]["lineupSlot"]="IR"
        profiles={x["playerId"]:{"mean":x["avg_points"]} for x in p}
        result=best(assignment(p,DAY,profiles))
        self.assertEqual(result["starts"],5)
        self.assertEqual(result["points"],sum(range(24,29)))
        self.assertEqual(len({x["id"] for x in result["lineup"]}),5)
        d=assignment(p[:-1],DAY,profiles)
        self.assertEqual(add_to_dp(insertion_cache(d),p[-1],DAY,profiles),result)
    def test_end_to_end(self):
        core=player(1,"Core",40,[DAY,FRI,SUN])
        streamer=player(2,"Stream",20,[FRI],("PF","F","UT"))
        injured=player(3,"Injured",42,[DAY,FRI],"PF F UT".split(),"OUT")
        opponent=player(4,"Rival",36,[DAY,FRI,SUN])
        replacement=player(5,"Upgrade",28,[DAY,FRI,SUN],("PF","F","UT"),owner="FREEAGENT")
        waiver=player(6,"Waiver",50,[DAY,FRI,SUN],owner="WAIVERS")
        next_player=player(7,"Sunday",30,[SUN],("PF","F","UT"),owner="FREEAGENT")
        s={"exported_at":"2026-11-25T05:17:30-05:00","season":2027,"team_name_target":"Professorsack",
           "teams":[{"team_name":"Professorsack","roster":[core,streamer,injured]},
                    {"team_name":"Other","roster":[opponent]}],
           "free_agents":[replacement,waiver,core,next_player,replacement],
           "current_matchup_box_scores":[{"home_team":"Professorsack","away_team":"Other",
                                           "home_score":100,"away_score":105}],
           "recent_league_transactions":[{"team_name":"Professorsack","date":"2026-11-23T10:00:00-05:00",
                                           "action":"FA ADDED","player":"Stream"}]}
        r=analyze(s,{},{"status":"offline"})
        self.assertEqual(r["coverage"]["deduplicated_unrostered"],3)
        self.assertEqual(r["acquisitions"]["assumed_remaining_upper_bound"],6)
        self.assertEqual(r["matchup"]["our_remaining_fp"],140)
        self.assertEqual(r["matchup"]["opponent_remaining_fp"],108)
        self.assertEqual(r["top_immediate_moves"][0]["add"],"Upgrade")
        self.assertEqual(r["top_immediate_moves"][0]["drop"],"Stream")
        self.assertEqual(r["top_immediate_moves"][0]["net_points"],64)
        self.assertEqual(r["top_immediate_moves"][0]["net_starts"],2)
        self.assertNotIn("Waiver",[m["add"] for m in r["top_immediate_moves"]])
        self.assertGreaterEqual(r["one_slot_streaming_plan"]["incremental_points"],64)
        self.assertGreater(r["matchup"]["conditional_simulation"]["conditional_win_fraction"],.5)
    def test_rate(self):
        p=player(1,"Player",30,[DAY])
        logs={"player":[{"minutes":30,"fp":30,"stocks_fp":4} for _ in range(10)]}
        result=profile(p,logs,2027)
        self.assertAlmostEqual(result["mean"],30)
        self.assertEqual(result["recent_games"],10)
    def test_missing_scores(self):
        self.assertIsNone(simulate([],[],{},None))

if __name__=="__main__":
    unittest.main()
