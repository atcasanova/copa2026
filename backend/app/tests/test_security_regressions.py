from datetime import datetime, timedelta

from app.models import Announcement, Group, GroupMember, PasswordResetToken, User
from app.auth import verify_password


def login_headers(client, username, password="password"):
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
