import pytest
from app.models import User, PixConfig, Match, Team, Stadium
from app.auth import get_password_hash
import io
from PIL import Image

def get_auth_headers(client, username, password="password"):
    login_data = {"username": username, "password": password}
    response = client.post("/api/auth/login", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_pix_config_flow(client, db_session, test_users):
    admin = test_users[0]
    p1 = test_users[2]
    
    admin_headers = get_auth_headers(client, admin.username)
    p1_headers = get_auth_headers(client, p1.username)
    
    # 1. Update config as admin
    config_data = {
        "pix_key": "pix@chave.com",
        "merchant_name": "Bolao Merchant",
        "merchant_city": "Sao Paulo",
        "entry_fee": 50.00
    }
    res = client.post("/api/payments/admin/config", json=config_data, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["pix_key"] == "pix@chave.com"
    assert res.json()["entry_fee"] == 50.00
    
    # 2. Try update as normal user (forbidden)
    res_forbidden = client.post("/api/payments/admin/config", json=config_data, headers=p1_headers)
    assert res_forbidden.status_code == 403
    
    # 3. Read config as normal user
    res_get = client.get("/api/payments/config", headers=p1_headers)
    assert res_get.status_code == 200
    assert res_get.json()["pix_key"] == "pix@chave.com"
    # Ensure copia e cola is calculated and contains Pix identifiers
    copia_cola = res_get.json()["copia_e_cola"]
    assert copia_cola != ""
    assert "br.gov.bcb.pix" in copia_cola
    assert "BOLAO MERCHANT" in copia_cola

def test_proof_upload_validation(client, db_session, test_users):
    admin = test_users[0]
    p1 = test_users[2]
    
    # Explicitly set p1 to pending to test the upload flow
    p1.payment_status = "pending"
    db_session.commit()
    
    p1_headers = get_auth_headers(client, p1.username)
    
    # Pre-configure Pix Config
    config = db_session.query(PixConfig).filter(PixConfig.id == 1).first()
    if not config:
        config = PixConfig(id=1)
        db_session.add(config)
    config.pix_key = "some@key.com"
    config.merchant_name = "Name"
    config.merchant_city = "City"
    config.entry_fee = 25.00
    db_session.commit()
    
    # Test 1: Upload text file (invalid extension)
    files = {"file": ("test.txt", b"dummy content text", "text/plain")}
    data = {"pix_key_receive": "my_pix_key"}
    res = client.post("/api/payments/submit-proof", data=data, files=files, headers=p1_headers)
    assert res.status_code == 400
    assert "Apenas arquivos PNG, JPG, JPEG e PDF" in res.json()["detail"]
    
    # Test 2: Upload file with JPG extension but incorrect magic bytes
    files = {"file": ("test.jpg", b"not-a-jpg-magic-header", "image/jpeg")}
    res = client.post("/api/payments/submit-proof", data=data, files=files, headers=p1_headers)
    assert res.status_code == 400
    assert "magic bytes" in res.json()["detail"]
    
    # Test 3: Upload file with valid PNG header but exceeding 1MB
    large_payload = b"\x89PNG\r\n\x1a\n" + b"x" * 1024 * 1024 # slightly above 1MB
    files = {"file": ("test.png", large_payload, "image/png")}
    res = client.post("/api/payments/submit-proof", data=data, files=files, headers=p1_headers)
    assert res.status_code == 400
    assert "excede o limite de 1MB" in res.json()["detail"]
    
    # Test 4: Valid JPEG upload
    jpeg_buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(jpeg_buffer, format="JPEG")
    valid_jpeg = jpeg_buffer.getvalue()
    files = {"file": ("proof.jpg", valid_jpeg, "image/jpeg")}
    res = client.post("/api/payments/submit-proof", data=data, files=files, headers=p1_headers)
    assert res.status_code == 200
    assert res.json()["payment_status"] == "submitted"
    assert res.json()["pix_key_receive"] == "my_pix_key"
    
    # Refresh DB session and verify user status
    db_session.refresh(p1)
    assert p1.payment_status == "submitted"
    assert p1.pix_key_receive == "my_pix_key"
    assert p1.payment_proof_filename.startswith("proof_")

def test_predictions_payment_locking(client, db_session, test_users):
    admin = test_users[0]
    p1 = test_users[2]
    
    # Explicitly set p1 to pending to test the block
    p1.payment_status = "pending"
    db_session.commit()
    
    admin_headers = get_auth_headers(client, admin.username)
    p1_headers = get_auth_headers(client, p1.username)
    
    # Setup team, stadium, match
    t1 = Team(name="Brasil", group_name="A")
    t2 = Team(name="Argentina", group_name="A")
    st = Stadium(name="Stadium", city="City", timezone="America/Sao_Paulo")
    db_session.add_all([t1, t2, st])
    db_session.commit()
    
    from datetime import datetime, timedelta
    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        group_name="Group A",
        date="2026-06-12",
        time_str="15:00 UTC",
        kickoff_time=datetime.utcnow() + timedelta(days=2), # 2 days in future (unlocked)
        team1_name="Brasil",
        team2_name="Argentina",
        ground="Stadium",
        status="scheduled"
    )
    db_session.add(match)
    db_session.commit()
    
    # Test 1: User p1 (payment_status="pending") tries to save prediction (forbidden)
    pred_data = {"goals_team1": 2, "goals_team2": 1}
    res = client.post(f"/api/predictions/save?match_id={match.id}", json=pred_data, headers=p1_headers)
    assert res.status_code == 403
    assert "comprovante" in res.json()["detail"].lower() or "pagamento" in res.json()["detail"].lower()
    
    # Test 2: Admin tries to save prediction (forbidden as admins do not participate)
    res_admin = client.post(f"/api/predictions/save?match_id={match.id}", json=pred_data, headers=admin_headers)
    assert res_admin.status_code == 400
    
    # Test 3: Set user payment_status to approved and try again
    p1.payment_status = "approved"
    db_session.commit()
    
    res_approved = client.post(f"/api/predictions/save?match_id={match.id}", json=pred_data, headers=p1_headers)
    assert res_approved.status_code == 200

def test_admin_approve_reject_flow(client, db_session, test_users):
    admin = test_users[0]
    p1 = test_users[2]
    
    admin_headers = get_auth_headers(client, admin.username)
    p1_headers = get_auth_headers(client, p1.username)
    
    # Setup submitted proof status
    p1.payment_status = "submitted"
    p1.payment_proof_filename = "proof_test.png"
    db_session.commit()
    
    # 1. Admin rejects payment
    res_reject = client.post(f"/api/payments/admin/reject/{p1.id}", data={"reason": "Comprovante cortado"}, headers=admin_headers)
    assert res_reject.status_code == 200
    assert res_reject.json()["payment_status"] == "rejected"
    assert res_reject.json()["payment_rejected_reason"] == "Comprovante cortado"
    
    db_session.refresh(p1)
    assert p1.payment_status == "rejected"
    
    # 2. Admin approves payment
    res_approve = client.post(f"/api/payments/admin/approve/{p1.id}", headers=admin_headers)
    assert res_approve.status_code == 200
    assert res_approve.json()["payment_status"] == "approved"
    assert res_approve.json()["payment_rejected_reason"] is None
    
    db_session.refresh(p1)
    assert p1.payment_status == "approved"


def test_payment_approval_sends_notification(client, db_session, test_users, monkeypatch):
    admin = test_users[0]
    p1 = test_users[2]
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, headers, files, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["files"] = files
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("WHATSAPP_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_NOTIFY_URL", "http://notify.test/internal/v1/send")
    monkeypatch.setenv("WHATSAPP_NOTIFY_TOKEN", "secret-token")
    monkeypatch.setenv("WHATSAPP_NOTIFY_TO", "120363407064163865@g.us")
    monkeypatch.setattr("app.notifications.requests.post", fake_post)

    p1.payment_status = "submitted"
    p1.display_name = "Ana  Teste"
    db_session.commit()

    admin_headers = get_auth_headers(client, admin.username)
    res = client.post(f"/api/payments/admin/approve/{p1.id}", headers=admin_headers)

    assert res.status_code == 200
    assert captured["url"] == "http://notify.test/internal/v1/send"
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}
    assert captured["files"]["to"] == (None, "120363407064163865@g.us")
    assert captured["files"]["text"] == (None, "\U0001f4b0 Pagamento de Ana Teste foi aprovado!")
    assert captured["files"]["sendAs"] == (None, "text")
    assert captured["timeout"] == 5.0
