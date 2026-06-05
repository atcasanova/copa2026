import pytest
from email import message_from_string
from datetime import datetime, timedelta
from app.models import User, SystemInvitation, Match, Prediction, Team, Stadium
from app.auth import get_password_hash
from app.scoring import get_rankings
from app.routers.auth import send_admin_registration_notification_email

def get_auth_headers(client, username, password="password"):
    login_data = {"username": username, "password": password}
    response = client.post("/api/auth/login", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_invitation_creation_and_listing(client, db_session, test_users):
    admin = test_users[0]
    p1 = test_users[2]
    
    admin_headers = get_auth_headers(client, admin.username)
    p1_headers = get_auth_headers(client, p1.username)
    
    # 1. Non-admin tries to invite (forbidden)
    res = client.post("/api/admin/invitations", json={"email": "newbie@test.com"}, headers=p1_headers)
    assert res.status_code == 403
    
    # 2. Admin successfully invites an email
    res = client.post("/api/admin/invitations", json={"email": "newbie@test.com"}, headers=admin_headers)
    assert res.status_code == 200
    invite = res.json()
    assert invite["email"] == "newbie@test.com"
    assert invite["is_used"] is False
    assert "code" in invite
    
    # 3. Try to invite the same email (resends/re-generates code)
    res_retry = client.post("/api/admin/invitations", json={"email": "newbie@test.com"}, headers=admin_headers)
    assert res_retry.status_code == 200
    assert res_retry.json()["code"] != invite["code"]
    
    # 4. List invitations as admin
    res_list = client.get("/api/admin/invitations", headers=admin_headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1
    assert any(x["email"] == "newbie@test.com" for x in res_list.json())

def test_invitation_check_endpoint(client, db_session, test_users):
    admin = test_users[0]
    admin_headers = get_auth_headers(client, admin.username)
    
    # Generate an invitation
    res_invite = client.post("/api/admin/invitations", json={"email": "checkme@test.com"}, headers=admin_headers)
    invite_code = res_invite.json()["code"]
    
    # Check invalid code
    res_check_invalid = client.get("/api/auth/invitations/check?code=INVALIDCODE")
    assert res_check_invalid.json()["valid"] is False
    
    # Check valid code
    res_check_valid = client.get(f"/api/auth/invitations/check?code={invite_code}")
    assert res_check_valid.json()["valid"] is True
    assert res_check_valid.json()["email"] == "checkme@test.com"

def test_invitation_registration_lock(client, db_session, test_users):
    admin = test_users[0]
    admin_headers = get_auth_headers(client, admin.username)
    
    # 1. Invite user
    res_invite = client.post("/api/admin/invitations", json={"email": "invited@test.com"}, headers=admin_headers)
    invite_code = res_invite.json()["code"]
    
    # 2. Try to register with mismatched email
    reg_mismatched = {
        "username": "invited_user",
        "email": "mismatched@test.com",
        "display_name": "Invited User",
        "password": "securepassword123"
    }
    res_mismatch = client.post(f"/api/auth/register?invite_code={invite_code}", json=reg_mismatched)
    assert res_mismatch.status_code == 400
    assert "O e-mail informado não corresponde" in res_mismatch.json()["detail"]
    
    # 3. Try to register without invite code
    reg_no_code = {
        "username": "invited_user",
        "email": "invited@test.com",
        "display_name": "Invited User",
        "password": "securepassword123"
    }
    res_no_code = client.post("/api/auth/register", json=reg_no_code)
    assert res_no_code.status_code == 400
    assert "código de convite válido" in res_no_code.json()["detail"]
    
    # 4. Register successfully with valid code and matching email
    reg_success = {
        "username": "invited_user",
        "email": "invited@test.com",
        "display_name": "Invited User",
        "password": "securepassword123"
    }
    res_success = client.post(f"/api/auth/register?invite_code={invite_code}", json=reg_success)
    assert res_success.status_code == 201
    
    # 5. Check invitation is now marked as used
    db_session.expire_all()
    invite_db = db_session.query(SystemInvitation).filter(SystemInvitation.code == invite_code).first()
    assert invite_db.is_used is True
    assert invite_db.used_by_id is not None
    
    # 6. Try to reuse the same code (should fail)
    reg_reuse = {
        "username": "invited_user_2",
        "email": "invited@test.com",
        "display_name": "Invited User 2",
        "password": "securepassword123"
    }
    res_reuse = client.post(f"/api/auth/register?invite_code={invite_code}", json=reg_reuse)
    assert res_reuse.status_code == 400

def test_hidden_registration_link_creates_active_user(client, db_session, test_users):
    admin = test_users[0]
    admin_headers = get_auth_headers(client, admin.username)

    link_res = client.get("/api/admin/registration-link", headers=admin_headers)
    assert link_res.status_code == 200
    registration_code = link_res.json()["code"]

    reg_data = {
        "username": "direct_user",
        "email": "direct@test.com",
        "display_name": "Direct User",
        "password": "securepassword123"
    }
    register_res = client.post(f"/api/auth/register?registration_code={registration_code}", json=reg_data)
    assert register_res.status_code == 201
    assert register_res.json()["is_active"] is True

    db_session.expire_all()
    user = db_session.query(User).filter(User.username == "direct_user").first()
    assert user is not None
    assert user.is_active is True

    login_res = client.post("/api/auth/login", data={"username": "direct_user", "password": "securepassword123"})
    assert login_res.status_code == 200

def test_registration_notifies_admins_by_email(client, db_session, test_users, monkeypatch):
    admin = test_users[0]
    captured = {}

    monkeypatch.setenv("ADMIN_REGISTRATION_NOTIFY_ENABLED", "true")
    monkeypatch.delenv("ADMIN_REGISTRATION_NOTIFY_TO", raising=False)
    monkeypatch.setenv("FRONTEND_URL", "https://bolao.example.com")

    def fake_send(user, recipients, registration_method):
        captured["display_name"] = user.display_name
        captured["email"] = user.email
        captured["recipients"] = recipients
        captured["registration_method"] = registration_method
        return True

    monkeypatch.setattr(
        "app.routers.auth.send_admin_registration_notification_email",
        fake_send
    )

    admin_headers = get_auth_headers(client, admin.username)
    link_res = client.get("/api/admin/registration-link", headers=admin_headers)
    registration_code = link_res.json()["code"]

    register_res = client.post(
        f"/api/auth/register?registration_code={registration_code}",
        json={
            "username": "notify_user",
            "email": "notify@test.com",
            "display_name": "Usuário Notificado",
            "password": "securepassword123"
        }
    )

    assert register_res.status_code == 201
    assert captured["display_name"] == "Usuário Notificado"
    assert captured["email"] == "notify@test.com"
    assert admin.email in captured["recipients"]
    assert len(captured["recipients"]) >= 1
    assert captured["registration_method"] == "registration_link"

def test_admin_registration_notification_email_contains_html_payment_link(test_users, monkeypatch):
    participant = test_users[2]
    captured = {}

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            pass

        def login(self, username, password):
            pass

        def sendmail(self, sender, recipients, message):
            captured["sender"] = sender
            captured["recipients"] = recipients
            captured["message"] = message

    monkeypatch.setenv("FRONTEND_URL", "https://bolao.example.com")
    monkeypatch.setattr("app.routers.auth.smtplib.SMTP", FakeSMTP)

    sent = send_admin_registration_notification_email(
        participant,
        ["admin@test.com"],
        "registration_link"
    )

    assert sent is True
    assert captured["recipients"] == ["admin@test.com"]
    parsed_message = message_from_string(captured["message"])
    html_part = next(part for part in parsed_message.walk() if part.get_content_type() == "text/html")
    html_body = html_part.get_payload(decode=True).decode(html_part.get_content_charset() or "utf-8")
    assert "https://bolao.example.com/admin?tab=payments" in html_body
    assert participant.display_name in html_body

def test_admin_exclusion_from_rankings(client, db_session, test_users):
    # Ensure system_admin is in users but not in computed rankings
    admin = test_users[0]
    p1 = test_users[2]
    
    # Run get_rankings function directly
    rankings = get_rankings(db_session)
    
    # Admin must NOT be in the ranking list
    assert not any(row["user_id"] == admin.id for row in rankings)
    # Standard participant must be in the ranking list
    assert any(row["user_id"] == p1.id for row in rankings)

def test_admin_prediction_block(client, db_session, test_users):
    admin = test_users[0]
    p1 = test_users[2]
    
    admin_headers = get_auth_headers(client, admin.username)
    p1_headers = get_auth_headers(client, p1.username)
    
    # Create a match
    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        group_name="Group A",
        date="2026-06-11",
        time_str="13:00",
        kickoff_time=datetime.utcnow() + timedelta(days=10),
        team1_name="UniqueTeamA",
        team2_name="UniqueTeamB",
        ground="UniqueStadiumName",
        status="scheduled"
    )
    if not db_session.query(Team).filter(Team.name == "UniqueTeamA").first():
        db_session.add(Team(name="UniqueTeamA", group_name="A"))
    if not db_session.query(Team).filter(Team.name == "UniqueTeamB").first():
        db_session.add(Team(name="UniqueTeamB", group_name="A"))
    if not db_session.query(Stadium).filter(Stadium.name == "UniqueStadiumName").first():
        db_session.add(Stadium(name="UniqueStadiumName", city="Rio", timezone="America/Sao_Paulo"))
        
    db_session.add(match)
    db_session.commit()
    
    # 1. Admin attempts to make prediction (fails)
    res_admin = client.post(f"/api/predictions/save?match_id={match.id}", json={"goals_team1": 2, "goals_team2": 1}, headers=admin_headers)
    assert res_admin.status_code == 400
    assert "Administradores não participam" in res_admin.json()["detail"]
    
    # 2. Admin attempts bulk save (fails)
    res_admin_bulk = client.post("/api/predictions/bulk-save", json=[{"match_id": match.id, "goals_team1": 2, "goals_team2": 1}], headers=admin_headers)
    assert res_admin_bulk.status_code == 400
