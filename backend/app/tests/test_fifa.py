from datetime import datetime, timezone, timedelta
import pytest
from app.fifa import sync_fifa_scores_and_live
from app.models import Match, Team, Stadium, Prediction

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

def _add_team(db, name, code):
    team = Team(name=name, fifa_code=code, group_name="A")
    db.add(team)
    return team

def _add_match(db, kickoff, team1, team2, match_id_offset=0):
    stadium = db.query(Stadium).filter(Stadium.name == "FIFA Stadium").first()
    if not stadium:
        stadium = Stadium(name="FIFA Stadium", city="City", timezone="UTC")
        db.add(stadium)
        db.flush()

    match = Match(
        round=f"Matchday {1 + match_id_offset}",
        stage="Group Stage",
        group_name="Grupo A",
        date=kickoff.strftime("%Y-%m-%d"),
        time_str="13:00 UTC",
        kickoff_time=kickoff,
        team1_name=team1,
        team2_name=team2,
        ground=stadium.name,
        status="scheduled",
    )
    db.add(match)
    return match

def test_fifa_sync_live_and_finished_logic(db_session, monkeypatch):
    # Add teams
    _add_team(db_session, "México", "MEX")
    _add_team(db_session, "África do Sul", "RSA")
    _add_team(db_session, "Brasil", "BRA")
    _add_team(db_session, "Argentina", "ARG")
    _add_team(db_session, "França", "FRA")
    _add_team(db_session, "Espanha", "ESP")

    # Match 1: live
    kickoff_live = datetime.utcnow()
    match_live = _add_match(db_session, kickoff_live, "México", "África do Sul", 0)

    # Match 2: finished
    kickoff_fin = datetime.utcnow() - timedelta(hours=3)
    match_fin = _add_match(db_session, kickoff_fin, "Brasil", "Argentina", 1)

    # Match 3: finished with extra time
    kickoff_et = datetime.utcnow() - timedelta(hours=4)
    match_et = _add_match(db_session, kickoff_et, "França", "Espanha", 2)

    db_session.commit()

    # Define fake API response
    api_payload = {
        "Results": [
            {
                "MatchStatus": 3,  # Live
                "MatchTime": "12'",
                "Date": kickoff_live.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Home": {
                    "TeamName": [{"Description": "Mexico"}],
                    "ShortClubName": "Mexico",
                    "Abbreviation": "MEX"
                },
                "Away": {
                    "TeamName": [{"Description": "South Africa"}],
                    "ShortClubName": "South Africa",
                    "Abbreviation": "RSA"
                },
                "HomeTeamScore": 1,
                "AwayTeamScore": 0,
                "ResultType": 1
            },
            {
                "MatchStatus": 0,  # Finished
                "Date": kickoff_fin.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Home": {
                    "TeamName": [{"Description": "Brazil"}],
                    "ShortClubName": "Brazil",
                    "Abbreviation": "BRA"
                },
                "Away": {
                    "TeamName": [{"Description": "Argentina"}],
                    "ShortClubName": "Argentina",
                    "Abbreviation": "ARG"
                },
                "HomeTeamScore": 2,
                "AwayTeamScore": 1,
                "ResultType": 1
            },
            {
                "MatchStatus": 0,  # Finished (but has extra time / ResultType = 3)
                "Date": kickoff_et.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Home": {
                    "TeamName": [{"Description": "France"}],
                    "ShortClubName": "France",
                    "Abbreviation": "FRA"
                },
                "Away": {
                    "TeamName": [{"Description": "Spain"}],
                    "ShortClubName": "Spain",
                    "Abbreviation": "ESP"
                },
                "HomeTeamScore": 3,
                "AwayTeamScore": 2,
                "ResultType": 3
            }
        ]
    }

    def fake_get(*args, **kwargs):
        return FakeResponse(api_payload)

    monkeypatch.setattr("app.fifa.requests.get", fake_get)

    results = sync_fifa_scores_and_live(db_session)

    assert results["live_updates"] == 1
    assert results["finished_updates"] == 1
    assert results["skipped_extra_time"] == 1

    # Refresh instances
    db_session.refresh(match_live)
    db_session.refresh(match_fin)
    db_session.refresh(match_et)

    # Check match_live properties
    assert match_live.status == "live"
    assert match_live.score_ft_team1 == 1
    assert match_live.score_ft_team2 == 0
    assert match_live.live_minute == "12'"

    # Check match_fin properties
    assert match_fin.status == "finished"
    assert match_fin.score_ft_team1 == 2
    assert match_fin.score_ft_team2 == 1

    # Check match_et properties: remained scheduled/unchanged because it went to extra time (ResultType=3)
    assert match_et.status == "scheduled"
    assert match_et.score_ft_team1 is None
