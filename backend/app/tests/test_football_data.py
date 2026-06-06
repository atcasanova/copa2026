from datetime import datetime, timedelta

from app.football_data import sync_finished_scores_from_football_data
from app.models import FootballDataSyncLog, Match, Prediction, Stadium, Team


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
    stadium = db.query(Stadium).filter(Stadium.name == "FD Stadium").first()
    if not stadium:
        stadium = Stadium(name="FD Stadium", city="City", timezone="UTC")
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


def _api_match(match, home_name, away_name, status="FINISHED", home_score=2, away_score=0):
    return {
        "id": 9000 + match.id,
        "utcDate": match.kickoff_time.isoformat() + "Z",
        "status": status,
        "homeTeam": {"name": home_name, "shortName": home_name, "tla": match.team1.fifa_code},
        "awayTeam": {"name": away_name, "shortName": away_name, "tla": match.team2.fifa_code},
        "score": {
            "duration": "REGULAR",
            "fullTime": {"homeTeam": home_score, "awayTeam": away_score},
        },
    }


def test_football_data_updates_group_only_when_all_same_kickoff_are_finished(db_session, test_users, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API", "fake-token")
    monkeypatch.setenv("FOOTBALL_DATA_ENABLED", "true")

    _add_team(db_session, "Brasil", "BRA")
    _add_team(db_session, "Argentina", "ARG")
    _add_team(db_session, "Canadá", "CAN")
    _add_team(db_session, "México", "MEX")
    kickoff = datetime.utcnow() - timedelta(hours=3)
    match1 = _add_match(db_session, kickoff, "Brasil", "Argentina")
    match2 = _add_match(db_session, kickoff, "Canadá", "México", 1)
    db_session.commit()
    db_session.refresh(match1)
    db_session.refresh(match2)

    participant = test_users[2]
    db_session.add(Prediction(match_id=match1.id, user_id=participant.id, goals_team1=2, goals_team2=0))
    db_session.commit()

    def fake_get(*args, **kwargs):
        return FakeResponse({
            "matches": [
                _api_match(match1, "Brazil", "Argentina", home_score=2, away_score=0),
                _api_match(match2, "Canada", "Mexico", home_score=1, away_score=1),
            ]
        })

    monkeypatch.setattr("app.football_data.requests.get", fake_get)
    result = sync_finished_scores_from_football_data(db_session)

    assert result["checked_groups"] == 1
    assert result["updated_groups"] == 1
    assert result["updated_matches"] == 2
    db_session.refresh(match1)
    db_session.refresh(match2)
    assert match1.status == "score_confirmed"
    assert match1.score_ft_team1 == 2
    assert match1.score_ft_team2 == 0
    assert match2.status == "score_confirmed"
    assert match2.score_ft_team1 == 1
    assert match2.score_ft_team2 == 1

    log = db_session.query(FootballDataSyncLog).order_by(FootballDataSyncLog.started_at.desc()).first()
    assert log is not None
    assert log.status == "success"
    assert log.updated_matches == 2
    assert any("API retornou" in event["message"] for event in log.details["events"])
    assert any(event.get("checks") for event in log.details["events"])


def test_football_data_waits_when_one_same_kickoff_match_is_not_finished(db_session, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API", "fake-token")
    monkeypatch.setenv("FOOTBALL_DATA_ENABLED", "true")

    _add_team(db_session, "Brasil", "BRA")
    _add_team(db_session, "Argentina", "ARG")
    _add_team(db_session, "Canadá", "CAN")
    _add_team(db_session, "México", "MEX")
    kickoff = datetime.utcnow() - timedelta(hours=3)
    match1 = _add_match(db_session, kickoff, "Brasil", "Argentina")
    match2 = _add_match(db_session, kickoff, "Canadá", "México", 1)
    db_session.commit()
    db_session.refresh(match1)
    db_session.refresh(match2)

    def fake_get(*args, **kwargs):
        return FakeResponse({
            "matches": [
                _api_match(match1, "Brazil", "Argentina", home_score=2, away_score=0),
                _api_match(match2, "Canada", "Mexico", status="IN_PLAY", home_score=1, away_score=1),
            ]
        })

    monkeypatch.setattr("app.football_data.requests.get", fake_get)
    result = sync_finished_scores_from_football_data(db_session)

    assert result["checked_groups"] == 1
    assert result["updated_groups"] == 0
    assert result["updated_matches"] == 0
    db_session.refresh(match1)
    db_session.refresh(match2)
    assert match1.status == "scheduled"
    assert match1.score_ft_team1 is None
    assert match2.status == "scheduled"
    assert match2.score_ft_team1 is None

    log = db_session.query(FootballDataSyncLog).order_by(FootballDataSyncLog.started_at.desc()).first()
    assert log is not None
    assert log.status == "warning"
    assert log.updated_matches == 0
    assert any("Nenhum placar foi aplicado" in event["message"] for event in log.details["events"])
