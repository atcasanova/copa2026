from datetime import datetime, timedelta

from app.models import Match, Stadium, SystemSetting, Team
from app.notifications import format_ranking_message, send_due_prediction_reminders


def login_headers(client, username, password="password"):
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _capture_whatsapp(monkeypatch):
    captured = []

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, headers, files, timeout):
        captured.append({
            "url": url,
            "headers": headers,
            "files": files,
            "timeout": timeout,
        })
        return FakeResponse()

    monkeypatch.setenv("WHATSAPP_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_NOTIFY_URL", "http://notify.test/internal/v1/send")
    monkeypatch.setenv("WHATSAPP_NOTIFY_TOKEN", "secret-token")
    monkeypatch.setenv("WHATSAPP_NOTIFY_TO", "120363407064163865@g.us")
    monkeypatch.setattr("app.notifications.requests.post", fake_post)
    return captured


def _add_match(db_session, kickoff_time=None):
    db_session.add_all([
        Team(name="Brasil", group_name="A"),
        Team(name="Canada", group_name="A"),
        Stadium(name="Reminder Stadium", city="City", timezone="America/Sao_Paulo")
    ])
    db_session.commit()

    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="18:00 UTC",
        kickoff_time=kickoff_time or datetime.utcnow() + timedelta(days=1),
        team1_name="Brasil",
        team2_name="Canada",
        ground="Reminder Stadium",
        status="scheduled"
    )
    db_session.add(match)
    db_session.commit()
    return match


def test_prediction_reminder_is_sent_once_per_kickoff(client, db_session, test_users, monkeypatch):
    captured = _capture_whatsapp(monkeypatch)
    match = _add_match(db_session, datetime.utcnow() + timedelta(minutes=151))

    sent_count = send_due_prediction_reminders(db_session)
    assert sent_count == 1
    assert len(captured) == 1
    assert "Lembrete de palpites" in captured[0]["files"]["text"][1]
    assert "Brasil x Canada" in captured[0]["files"]["text"][1]

    sent_again_count = send_due_prediction_reminders(db_session)
    assert sent_again_count == 0
    assert len(captured) == 1
    assert db_session.query(SystemSetting).filter(
        SystemSetting.key == f"whatsapp_reminder_sent:{match.kickoff_time.isoformat()}"
    ).first() is not None


def test_score_batch_sends_one_ranking_message(client, db_session, test_users, monkeypatch):
    captured = _capture_whatsapp(monkeypatch)
    admin = test_users[0]
    match = _add_match(db_session)

    headers = login_headers(client, admin.username)
    res = client.post(
        "/api/admin/matches/score-batch",
        headers=headers,
        json={
            "scores": [{
                "match_id": match.id,
                "score_ft_team1": 2,
                "score_ft_team2": 0
            }]
        }
    )

    assert res.status_code == 200
    assert res.json()[0]["status"] == "score_pending_review"
    assert len(captured) == 1
    assert "Ranking atualizado" in captured[0]["files"]["text"][1]
    assert "Top 10 geral" in captured[0]["files"]["text"][1]


def test_ranking_message_uses_medals_for_top_three():
    message = format_ranking_message([
        {"position": 1, "display_name": "Ana", "total_points": 30, "exact_scores_count": 2, "correct_results_count": 3},
        {"position": 2, "display_name": "Bruno", "total_points": 20, "exact_scores_count": 1, "correct_results_count": 2},
        {"position": 3, "display_name": "Caio", "total_points": 10, "exact_scores_count": 0, "correct_results_count": 1},
    ])

    assert "\U0001f947 *Ana*" in message
    assert "\U0001f948 *Bruno*" in message
    assert "\U0001f949 *Caio*" in message
