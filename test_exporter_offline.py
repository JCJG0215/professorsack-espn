"""Offline tests, no credentials and no ESPN network calls. Run: py -3 test_exporter_offline.py"""
from datetime import datetime, timezone
import json
import sys
import types
from types import SimpleNamespace as Obj

import export_espn as ex

# Stub Player for predictable ESPN payload tests (not a substitute for live API testing).
class FakePlayer:
    def __init__(self, raw, year):
        data = raw['playerPoolEntry']['player']
        self.playerId = data['id']
        self.name = data['fullName']
        self.proTeam = data['proTeam']
        self.position = 'C'
        self.eligibleSlots = ['C','UT','BE']
        self.lineupSlot = ''
        self.injured = False
        self.injuryStatus = 'ACTIVE'
        self.projected_avg_points = data.get('proj', 20)
        self.projected_total_points = 1300
        self.avg_points = data.get('fp', 0)
        self.total_points = data.get('fp', 0)
        self.stats = {
          '2027_projected': {'applied_total':1300, 'applied_avg':self.projected_avg_points},
          '2': {'applied_total': data.get('fp', 0), 'total': {'GP':1, 'MIN':32, 'STL':3, 'BLK':0,'PTS':19}},
        }

module = types.ModuleType('espn_api')
mod2 = types.ModuleType('espn_api.basketball')
mod3 = types.ModuleType('espn_api.basketball.player')
mod4 = types.ModuleType('espn_api.basketball.constant')
mod3.Player = FakePlayer
mod4.PRO_TEAM_MAP = {1:'CHA',2:'LAL'}
sys.modules.update({'espn_api':module,'espn_api.basketball':mod2,
                    'espn_api.basketball.player':mod3,
                    'espn_api.basketball.constant':mod4})

raw = [{'playerPoolEntry':{'player': {'id':i, 'fullName':name, 'proTeam':abbr, 'proTeamId':team, 'fp':fp, 'proj':proj}},'status':status}
       for i,name,abbr,team,fp,proj,status in [
           (1,'Roster player','CHA',1,38,39,'FREEAGENT'),
           (2,'Jaxson Hayes','LAL',2,44,18,'FREEAGENT'),
           (3,'Moussa Diabate','CHA',1,46,24,'WAIVERS'),
           (4,'Unknown player','CHA',1,11,13,'FREEAGENT'),
           (5,'Another player','LAL',2,18,15,'FREEAGENT'),
        ]]

class Req:
    def __init__(self): self.calls = []
    def league_get(self,params,headers):
        f=json.loads(headers['x-fantasy-filter'])['players']
        self.calls.append((f['offset'],f['limit']))
        # Mock ESPN silently capping pages at 2 even when limit is 4.
        return {'players':raw[f['offset']: f['offset']+min(f['limit'],2)]}

now=datetime(2026,10,22,0,30,tzinfo=ex.TZ)
ms=int(datetime(2026,10,23,19,tzinfo=timezone.utc).timestamp()*1000)
team = Obj(team_id=1,team_name='Professorsack',team_abbrev='PCK',wins=0,losses=0,points_for=0,standing=7,
           roster=[FakePlayer(raw[0],2027)])
league=Obj(teams=[team],settings=Obj(name='My 2027 League',scoring_type='H2H_POINTS',acquisition_limit=7),
           pro_schedule={1:{'4':[{'date':ms,'homeProTeamId':1,'awayProTeamId':2}]},2:{'4':[{'date':ms,'homeProTeamId':1,'awayProTeamId':2}]}},
           current_week=2,scoringPeriodId=2,currentMatchupPeriod=1,matchup_ids={1:['1','2','3']},espn_request=Req())
league.scoreboard=lambda: []
league.box_scores=lambda matchup_period=None: []

snapshot=ex.build_snapshot(league,123,2027,now, max_free_agents=20,page_size=4,lookahead=14)
assert snapshot['free_agent_scan_coverage']['complete'] is True, snapshot['warnings']
assert snapshot['free_agent_scan_coverage']['unique_players_returned_before_roster_dedup'] == 5
assert snapshot['free_agent_scan_coverage']['excluded_already_rostered']==1
assert snapshot['free_agent_scan_coverage']['unique_unrostered_players']==4
assert [p['name'] for p in snapshot['breakout_candidates'][:2]] == ['Moussa Diabate','Jaxson Hayes']
assert any(x['name']=='Jaxson Hayes' and len(x['upcoming_games']) == 1 for x in snapshot['free_agents'])
assert snapshot['free_agent_scan_coverage']['api_requests'] == 4, snapshot['free_agent_scan_coverage']
assert all('espn_s2' not in json.dumps(p) for p in snapshot['free_agents'])
print('PASS: silent page cap, complete paginated scan, dedup roster, watchlist, schedule and no cookies')

# The real paginated FA response often has total-season stats, but no period logs.
fallback = {"name":"Moussa Diabate", "playerId":123, "projected_avg_points":24,
            "total_points":46, "recent_games":[], "upcoming_games":[],
            "stats_summary":{"2027_total":{"applied_total":46,
              "avg":{"GP":1,"MIN":34,"STL":5,"BLK":0}}}}
bo = ex.breakout_candidates([fallback])
assert len(bo)==1 and bo[0]["latest_fp"]==46
assert bo[0]["latest_minutes"]==34 and bo[0]["high_defensive_variance_flag"]
assert bo[0]["performance_source"]=="ONE_GAME_SEASON_TOTAL_FALLBACK"
fallback["stats_summary"]["2027_total"]["avg"]["GP"]=2
assert ex.breakout_candidates([fallback])==[], "Do not present multi-game season totals as one game"
print('PASS: missing per-game log uses one-game season total without misleading dates')
