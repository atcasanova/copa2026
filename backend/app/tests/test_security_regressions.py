from datetime import datetime, timedelta

from app.models import Announcement, AuditLog, Group, GroupInvitation, GroupMember, Match, PasswordResetToken, Prediction, Stadium, Team, User
from app.auth import get_password_hash, verify_password


def login_headers(client, username, password="password"):
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_notifications_summary_counts_pending_items(client, db_session, test_users):
    admin = test_users[0]
    participant = test_users[2]

    participant.payment_status = "submitted"
    db_session.add_all([
        Team(name="Time A", group_name="A"),
        Team(name="Time B", group_name="A"),
        Stadium(name="Estadio Teste", city="Brasilia", timezone="UTC"),
    ])
    db_session.flush()
    db_session.add(Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="13:00 UTC+0",
        kickoff_time=datetime(2026, 6, 11, 13, 0),
        team1_name="Time A",
        team2_name="Time B",
        ground="Estadio Teste",
        status="score_pending_review",
    ))
    db_session.commit()

    res = client.get("/api/admin/notifications/summary", headers=login_headers(client, admin.username))

    assert res.status_code == 200
    assert res.json()["pending_payment_approvals"] == 1
    assert res.json()["pending_score_reviews"] == 1
    assert res.json()["total"] == 2


def test_admin_users_are_sorted_ignoring_case_and_accents(client, db_session, test_users):
    admin = test_users[0]
    password = get_password_hash("password")
    db_session.add_all([
        User(username="sortcase_1", email="sortcase1@test.com", display_name="bruno", hashed_password=password),
        User(username="sortcase_2", email="sortcase2@test.com", display_name="Álvaro", hashed_password=password),
        User(username="sortcase_3", email="sortcase3@test.com", display_name="alberto", hashed_password=password),
        User(username="sortcase_4", email="sortcase4@test.com", display_name="Cézar", hashed_password=password),
    ])
    db_session.commit()

    res = client.get("/api/admin/users?search=sortcase", headers=login_headers(client, admin.username))

    assert res.status_code == 200
    assert [u["display_name"] for u in res.json()] == ["alberto", "Álvaro", "bruno", "Cézar"]


def test_group_owner_can_delete_group_and_member_cannot(client, db_session, test_users):
    owner = test_users[2]
    member = test_users[3]

    group = Group(
        name="Grupo para excluir",
        description="Temporario",
        owner_id=owner.id,
        invite_code="DEL12345",
        is_private=True,
    )
    db_session.add(group)
    db_session.flush()
    db_session.add_all([
        GroupMember(group_id=group.id, user_id=owner.id, role="owner", is_approved=True),
        GroupMember(group_id=group.id, user_id=member.id, role="member", is_approved=True),
        GroupInvitation(group_id=group.id, invited_by_id=owner.id, invitee_id=member.id, status="pending"),
        Announcement(title="Aviso", body="Grupo", target_type="group", target_group_id=group.id, priority="low"),
    ])
    db_session.commit()

    member_res = client.delete(f"/api/groups/{group.id}", headers=login_headers(client, member.username))
    assert member_res.status_code == 403

    owner_res = client.delete(f"/api/groups/{group.id}", headers=login_headers(client, owner.username))
    assert owner_res.status_code == 204
    assert db_session.query(Group).filter(Group.id == group.id).first() is None
    assert db_session.query(GroupMember).filter(GroupMember.group_id == group.id).count() == 0
    assert db_session.query(GroupInvitation).filter(GroupInvitation.group_id == group.id).count() == 0
    assert db_session.query(Announcement).filter(Announcement.target_group_id == group.id).count() == 0


def test_group_invite_code_is_admin_only_and_pending_members_are_not_listed(client, db_session, test_users):
    owner = test_users[2]
    member = test_users[3]

    group = Group(
        name="Grupo Privado",
        description="Segredo",
        owner_id=owner.id,
        invite_code="SECRET123",
        is_private=True
    )
    db_session.add(group)
    db_session.commit()

    db_session.add(GroupMember(group_id=group.id, user_id=owner.id, role="owner", is_approved=True))
    db_session.add(GroupMember(group_id=group.id, user_id=member.id, role="member", is_approved=False))
    db_session.commit()

    member_headers = login_headers(client, "p2_user")
    groups_res = client.get("/api/groups", headers=member_headers)
    assert groups_res.status_code == 200
    assert all(item["id"] != str(group.id) for item in groups_res.json())

    owner_headers = login_headers(client, "p1_user")
    owner_res = client.get(f"/api/groups/{group.id}", headers=owner_headers)
    assert owner_res.status_code == 200
    assert owner_res.json()["invite_code"] == "SECRET123"

    member_record = db_session.query(GroupMember).filter(
        GroupMember.group_id == group.id,
        GroupMember.user_id == member.id
    ).first()
    member_record.is_approved = True
    db_session.commit()

    approved_member_res = client.get(f"/api/groups/{group.id}", headers=member_headers)
    assert approved_member_res.status_code == 200
    assert approved_member_res.json()["invite_code"] is None


def test_out_of_scope_announcement_cannot_be_marked_read(client, db_session, test_users):
    owner = test_users[2]
    outsider = test_users[3]

    group = Group(
        name="Grupo Anuncio",
        owner_id=owner.id,
        invite_code="ANN12345",
        is_private=True
    )
    db_session.add(group)
    db_session.commit()
    db_session.add(GroupMember(group_id=group.id, user_id=owner.id, role="owner", is_approved=True))

    announcement = Announcement(
        title="Aviso reservado",
        body="Somente membros aprovados devem ver este aviso.",
        priority="high",
        target_type="group",
        target_group_id=group.id,
        publication_date=datetime.utcnow() - timedelta(minutes=1)
    )
    db_session.add(announcement)
    db_session.commit()

    outsider_headers = login_headers(client, outsider.username)
    res = client.post(f"/api/announcements/{announcement.id}/read", headers=outsider_headers)
    assert res.status_code == 404


def test_payment_proof_rejects_mismatched_mime_type(client, db_session, test_users):
    user = test_users[2]
    user.payment_status = "pending"
    db_session.commit()

    headers = login_headers(client, user.username)
    files = {
        "file": ("proof.png", b"\x89PNG\r\n\x1a\nnot-a-real-image", "application/pdf")
    }
    res = client.post(
        "/api/payments/submit-proof",
        data={"pix_key_receive": "user-pix-key"},
        files=files,
        headers=headers
    )

    assert res.status_code == 400
    assert "MIME" in res.json()["detail"]


def test_password_reset_flow(client, db_session, test_users, monkeypatch):
    captured = {}

    def fake_send_password_reset_email(email, display_name, token):
        captured["email"] = email
        captured["token"] = token
        return True

    monkeypatch.setattr(
        "app.routers.auth.send_password_reset_email",
        fake_send_password_reset_email
    )

    res = client.post("/api/auth/password-reset/request", json={"email": "p1@test.com"})
    assert res.status_code == 200
    assert captured["email"] == "p1@test.com"

    confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": captured["token"], "password": "new-password"}
    )
    assert confirm.status_code == 200

    user = db_session.query(User).filter(User.username == "p1_user").first()
    assert verify_password("new-password", user.hashed_password)

    used_tokens = db_session.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).all()
    assert len(used_tokens) == 1
    assert used_tokens[0].used_at is not None

    old_login = client.post("/api/auth/login", data={"username": "p1_user", "password": "password"})
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", data={"username": "p1_user", "password": "new-password"})
    assert new_login.status_code == 200


def test_profile_config_exposes_whatsapp_group_chat(client, test_users, monkeypatch):
    user = test_users[2]
    monkeypatch.setenv("WHATSAPP_GROUP_CHAT", "chat.whatsapp.com/FAKEINVITE")

    login_res = client.post("/api/auth/login", data={"username": user.username, "password": "password"})
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    res = client.get("/api/auth/profile-config", headers=headers)
    assert res.status_code == 200
    assert res.json()["whatsapp_group_chat"] == "https://chat.whatsapp.com/FAKEINVITE"


def test_admin_can_change_prediction_lock_hours(client, db_session, test_users):
    admin = test_users[0]
    participant = test_users[2]

    db_session.add_all([
        Team(name="Brasil", group_name="A"),
        Team(name="Canada", group_name="A"),
        Stadium(name="Stadium Lock", city="City", timezone="UTC")
    ])
    db_session.commit()

    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="18:00 UTC+0",
        kickoff_time=datetime.utcnow() + timedelta(hours=2),
        team1_name="Brasil",
        team2_name="Canada",
        ground="Stadium Lock",
        status="scheduled"
    )
    db_session.add(match)
    db_session.commit()

    participant_headers = login_headers(client, participant.username)
    blocked = client.post(
        f"/api/predictions/save?match_id={match.id}",
        headers=participant_headers,
        json={"goals_team1": 1, "goals_team2": 0}
    )
    assert blocked.status_code == 400

    admin_headers = login_headers(client, admin.username)
    update = client.put("/api/admin/settings/prediction-lock-hours?hours=1", headers=admin_headers)
    assert update.status_code == 200
    assert update.json()["hours"] == 1

    allowed = client.post(
        f"/api/predictions/save?match_id={match.id}",
        headers=participant_headers,
        json={"goals_team1": 1, "goals_team2": 0}
    )
    assert allowed.status_code == 200


def test_match_prediction_visibility_hides_scores_before_lock(client, db_session, test_users):
    viewer = test_users[2]
    participant = test_users[3]
    pending = User(
        username="pending_visibility_user",
        email="pending_visibility@test.com",
        display_name="Pendente Visibilidade",
        hashed_password=get_password_hash("password"),
        role="participant",
        payment_status="submitted",
    )

    db_session.add_all([
        pending,
        Team(name="Brasil", group_name="A"),
        Team(name="Canada", group_name="A"),
        Stadium(name="Visibility Stadium", city="City", timezone="UTC")
    ])
    db_session.commit()

    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="18:00 UTC+0",
        kickoff_time=datetime.utcnow() + timedelta(hours=5),
        team1_name="Brasil",
        team2_name="Canada",
        ground="Visibility Stadium",
        status="scheduled"
    )
    db_session.add(match)
    db_session.commit()
    db_session.add_all([
        Prediction(match_id=match.id, user_id=participant.id, goals_team1=2, goals_team2=1),
        Prediction(match_id=match.id, user_id=pending.id, goals_team1=1, goals_team2=0),
    ])
    db_session.commit()

    headers = login_headers(client, viewer.username)
    res = client.get(f"/api/predictions/match/{match.id}/visibility", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["is_locked"] is False
    assert data["is_scored"] is False
    assert data["points_summary"] == []
    assert data["total_predictions"] == 1
    assert data["total_participants"] == 2
    assert all(entry["display_name"] != pending.display_name for entry in data["entries"])
    assert data["entries"][0]["display_name"] == participant.display_name
    assert data["entries"][0]["created_at"].endswith(("+00:00", "Z"))
    assert data["entries"][0]["goals_team1"] is None
    assert data["entries"][0]["goals_team2"] is None


def test_match_prediction_visibility_shows_scores_after_lock(client, db_session, test_users):
    viewer = test_users[2]
    participant = test_users[3]

    db_session.add_all([
        Team(name="Brasil", group_name="A"),
        Team(name="Canada", group_name="A"),
        Stadium(name="Locked Visibility Stadium", city="City", timezone="UTC")
    ])
    db_session.commit()

    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="18:00 UTC+0",
        kickoff_time=datetime.utcnow() + timedelta(hours=1),
        team1_name="Brasil",
        team2_name="Canada",
        ground="Locked Visibility Stadium",
        status="scheduled"
    )
    db_session.add(match)
    db_session.commit()
    db_session.add(Prediction(match_id=match.id, user_id=participant.id, goals_team1=2, goals_team2=1))
    db_session.commit()

    headers = login_headers(client, viewer.username)
    res = client.get(f"/api/predictions/match/{match.id}/visibility", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["is_locked"] is True
    assert data["is_scored"] is False
    assert data["entries"][0]["goals_team1"] == 2
    assert data["entries"][0]["goals_team2"] == 1


def test_match_prediction_visibility_groups_by_points_after_score(client, db_session, test_users):
    viewer = test_users[2]
    participant = test_users[3]

    db_session.add_all([
        Team(name="Brasil", group_name="A"),
        Team(name="Canada", group_name="A"),
        Stadium(name="Scored Visibility Stadium", city="City", timezone="UTC")
    ])
    db_session.commit()

    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="18:00 UTC+0",
        kickoff_time=datetime.utcnow() - timedelta(hours=3),
        team1_name="Brasil",
        team2_name="Canada",
        ground="Scored Visibility Stadium",
        status="score_confirmed",
        score_ft_team1=2,
        score_ft_team2=1
    )
    db_session.add(match)
    db_session.commit()
    db_session.add_all([
        Prediction(match_id=match.id, user_id=viewer.id, goals_team1=2, goals_team2=1, points_earned=10),
        Prediction(match_id=match.id, user_id=participant.id, goals_team1=1, goals_team2=0, points_earned=6),
    ])
    db_session.commit()

    headers = login_headers(client, viewer.username)
    res = client.get(f"/api/predictions/match/{match.id}/visibility", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["is_locked"] is True
    assert data["is_scored"] is True
    assert data["points_summary"] == [
        {"points": 10, "count": 1},
        {"points": 6, "count": 1},
    ]
    assert [entry["points_earned"] for entry in data["entries"]] == [10, 6]
    assert [entry["display_name"] for entry in data["entries"]] == [viewer.display_name, participant.display_name]


def test_system_admin_can_delete_participant(client, db_session, test_users):
    admin = test_users[0]
    owner = test_users[2]
    participant = test_users[3]

    group = Group(
        name="Grupo Teste",
        owner_id=owner.id,
        invite_code="DELETE123",
        is_private=False
    )
    db_session.add(group)
    db_session.commit()
    db_session.add(GroupMember(group_id=group.id, user_id=participant.id, role="member", is_approved=True))
    db_session.commit()

    headers = login_headers(client, admin.username)
    res = client.delete(f"/api/admin/users/{participant.id}", headers=headers)

    assert res.status_code == 204
    assert db_session.query(User).filter(User.id == participant.id).first() is None
    assert db_session.query(GroupMember).filter(GroupMember.user_id == participant.id).first() is None

    audit = db_session.query(AuditLog).filter(AuditLog.action == "user_delete").first()
    assert audit is not None
    assert audit.user_id == admin.id
    assert audit.target_id == str(participant.id)


def test_system_admin_cannot_delete_self(client, db_session, test_users):
    admin = test_users[0]
    headers = login_headers(client, admin.username)

    res = client.delete(f"/api/admin/users/{admin.id}", headers=headers)

    assert res.status_code == 400
    assert "próprio usuário" in res.json()["detail"]


def test_system_admin_cannot_delete_group_owner(client, db_session, test_users):
    admin = test_users[0]
    owner = test_users[2]
    group = Group(
        name="Grupo Protegido",
        owner_id=owner.id,
        invite_code="OWNER123",
        is_private=False
    )
    db_session.add(group)
    db_session.commit()

    headers = login_headers(client, admin.username)
    res = client.delete(f"/api/admin/users/{owner.id}", headers=headers)

    assert res.status_code == 400
    assert "proprietário" in res.json()["detail"]
    assert db_session.query(User).filter(User.id == owner.id).first() is not None
