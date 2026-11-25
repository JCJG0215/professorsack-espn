"""Offline season and history safety tests."""
import unittest
from season_analytics import qualification,playoff_calendar
from forecast_history import digest,evaluate

class SeasonTests(unittest.TestCase):
    def test_missing_settings(self):
        self.assertEqual(qualification({}, {})["status"],"unavailable")
        self.assertEqual(playoff_calendar({}, {}, None, None)["status"],"unavailable")
    def test_qualification(self):
        teams=[{"team_id":1,"team_name":"Professorsack","division_id":1,"wins":2,"losses":0,"points_for":300},
               {"team_id":2,"team_name":"Other","division_id":1,"wins":0,"losses":2,"points_for":200}]
        matches=[{"period":p,"home":{"team_id":1,"score":150},"away":{"team_id":2,"score":100},"winner":"HOME"} for p in (1,2)]
        matches.append({"period":3,"home":{"team_id":1},"away":{"team_id":2},"winner":"UNDECIDED"})
        s={"teams":teams,"team_name_target":"Professorsack","matchup_period_id":3,
           "league_settings":{"regular_season_matchups":3,"playoff_team_count":1},"season_matchups":matches}
        r=qualification(s,{},iterations=200)
        self.assertEqual(r["status"],"scenario_only")
        self.assertEqual(r["qualification_fraction"],1)
        s["season_matchups"].pop()
        self.assertEqual(qualification(s,{})["status"],"unavailable")
    def test_history(self):
        data={"exported_at":"2026-11-25T05:17:30-05:00","teams":[],
              "analytics":{"player_profiles":{"1":{"logs":[{"date":"2026-11-24","fp":32}]}},
                           "matchup":{}}}
        prior={"date":"2026-11-24","pregame_assumption":True,
               "predictions":[{"id":"1","predicted_fp":30},{"id":"2","predicted_fp":12}]}
        r=evaluate(data,prior)
        self.assertEqual(r["samples"],1)
        self.assertEqual(r["mae_fp"],2)
        self.assertEqual(r["bias_fp"],-2)
        self.assertEqual(r["unmatched_or_dnp"],1)
        self.assertEqual(digest(data)["date"],"2026-11-25")

if __name__=="__main__":
    unittest.main()
