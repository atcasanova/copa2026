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


def test_scheduled_football_data_sync_without_candidates_does_not_create_log(db_session, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API", "fake-token")
    monkeypatch.setenv("FOOTBALL_DATA_ENABLED", "true")

    result = sync_finished_scores_from_football_data(db_session, trigger="scheduled")

    assert result["checked_groups"] == 0
    assert result["updated_groups"] == 0
    assert result["updated_matches"] == 0
    assert db_session.query(FootballDataSyncLog).count() == 0


def test_manual_football_data_sync_without_candidates_keeps_visibility_log(db_session, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API", "fake-token")
    monkeypatch.setenv("FOOTBALL_DATA_ENABLED", "true")

    result = sync_finished_scores_from_football_data(db_session, trigger="manual")

    assert result["checked_groups"] == 0
    log = db_session.query(FootballDataSyncLog).order_by(FootballDataSyncLog.started_at.desc()).first()
    assert log is not None
    assert log.status == "success"
    assert log.details["candidate_kickoffs"] == []
    assert any("0 horário(s) candidato(s)" in event["message"] for event in log.details["events"])


def test_sync_fixtures_from_football_data(db_session, monkeypatch):
    from app.football_data import sync_fixtures_from_football_data
    monkeypatch.setenv("FOOTBALL_DATA_API", "fake-token")
    monkeypatch.setenv("FOOTBALL_DATA_ENABLED", "true")

    # Add teams
    _add_team(db_session, "Brasil", "BRA")
    _add_team(db_session, "Argentina", "ARG")
    
    p1 = Team(name="2A", group_name="Knockout Placeholder", fifa_code=None)
    p2 = Team(name="2B", group_name="Knockout Placeholder", fifa_code=None)
    db_session.add_all([p1, p2])
    db_session.commit()

    # Add knockout match
    stadium = db_session.query(Stadium).filter(Stadium.name == "FD Stadium").first()
    if not stadium:
        stadium = Stadium(name="FD Stadium", city="City", timezone="UTC")
        db_session.add(stadium)
        db_session.commit()

    kickoff = datetime.utcnow() + timedelta(days=10)
    match = Match(
        round="Round of 32",
        stage="Round of 32",
        date=kickoff.strftime("%Y-%m-%d"),
        time_str="19:00 UTC",
        kickoff_time=kickoff,
        team1_name="2A",
        team2_name="2B",
        ground=stadium.name,
        status="scheduled",
    )
    db_session.add(match)
    db_session.commit()
    db_session.refresh(match)

    def fake_get(*args, **kwargs):
        return FakeResponse({
            "matches": [
                {
                    "id": 9999,
                    "utcDate": kickoff.isoformat() + "Z",
                    "status": "SCHEDULED",
                    "stage": "LAST_32",
                    "homeTeam": {"name": "Brazil", "shortName": "Brazil", "tla": "BRA"},
                    "awayTeam": {"name": "Argentina", "shortName": "Argentina", "tla": "ARG"},
                }
            ]
        })

    monkeypatch.setattr("app.football_data.requests.get", fake_get)
    result = sync_fixtures_from_football_data(db_session)

    assert result["enabled"] is True
    assert result["updated_matches"] == 1
    
    db_session.refresh(match)
    assert match.team1_name == "Brasil"
    assert match.team2_name == "Argentina"


def test_get_knockout_setup_possible_teams(db_session, test_users, client):
    from app.models import Team, Match, Stadium
    from app.routers.admin import get_possible_teams

    # Preseed teams for Group A and Group B
    teams_data = [
        ("Brasil", "BRA", "Grupo A"),
        ("França", "FRA", "Grupo A"),
        ("Itália", "ITA", "Grupo A"),
        ("Espanha", "ESP", "Grupo A"),
        ("Argentina", "ARG", "Grupo B"),
        ("Alemanha", "GER", "Grupo B"),
        ("Inglaterra", "ENG", "Grupo B"),
        ("Holanda", "NED", "Grupo B"),
    ]
    for name, code, group in teams_data:
        db_session.add(Team(name=name, fifa_code=code, group_name=group))
        
    p1 = Team(name="2A", group_name="Knockout Placeholder", fifa_code=None)
    p2 = Team(name="2B", group_name="Knockout Placeholder", fifa_code=None)
    db_session.add_all([p1, p2])
    db_session.commit()

    stadium = Stadium(name="FD Stadium", city="City", timezone="UTC")
    db_session.add(stadium)
    db_session.commit()

    # Match ID 73 is Round of 32 between 2A and 2B
    match_73 = Match(
        id=73,
        round="Dezesseis-avos de Final",
        stage="Round of 32",
        date="2026-06-30",
        time_str="19:00 UTC",
        kickoff_time=datetime.utcnow() + timedelta(days=2),
        team1_name="2A",
        team2_name="2B",
        ground=stadium.name,
        status="scheduled",
    )
    db_session.add(match_73)
    db_session.commit()

    # Verify get_possible_teams helper
    res_t1 = get_possible_teams(db_session, "2A")
    assert len(res_t1) == 4
    assert {t["name"] for t in res_t1} == {"Brasil", "França", "Itália", "Espanha"}

    res_t2 = get_possible_teams(db_session, "2B")
    assert len(res_t2) == 4
    assert {t["name"] for t in res_t2} == {"Argentina", "Alemanha", "Inglaterra", "Holanda"}

    # Recursively check Winner of Match 73: "W73"
    res_w73 = get_possible_teams(db_session, "W73")
    assert len(res_w73) == 8
    assert {t["name"] for t in res_w73} == {
        "Brasil", "França", "Itália", "Espanha",
        "Argentina", "Alemanha", "Inglaterra", "Holanda"
    }

    # Log in as admin
    login_res = client.post(
        "/api/auth/login",
        data={"username": "score_admin_user", "password": "password"}
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Query knockout-setup endpoint
    res = client.get("/api/admin/matches/knockout-setup", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "matches" in data
    assert len(data["matches"]) == 1
    
    match_data = data["matches"][0]
    assert match_data["id"] == 73
    assert len(match_data["possible_teams1"]) == 4
    assert len(match_data["possible_teams2"]) == 4
    assert match_data["possible_teams1"][0]["name"] in {"Brasil", "França", "Itália", "Espanha"}
