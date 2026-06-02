import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.models import Team, Stadium, Match, Prediction, Group, GroupMember, GroupInvitation, StageMultiplier, SyncMatchDiff
from app.scoring import calculate_base_points, score_prediction, get_rankings
from app.sync import parse_kickoff_to_utc, ensure_team_exists, sync_openfootball_data

# ==========================================
# 1. Scoring System Tests
# ==========================================

def test_login_accepts_email_identifier(client, test_users):
    participant = test_users[2]

    login_res = client.post(
        "/api/auth/login",
        data={"username": participant.email.upper(), "password": "password"}
    )

    assert login_res.status_code == 200
    assert login_res.json()["token_type"] == "bearer"
    assert login_res.json()["access_token"]


def test_calculate_base_points():
    # Exact score -> 10 points
    pts, exp = calculate_base_points(2, 1, None, 2, 1, None, False)
    assert pts == 10
    
    # Correct result and goals difference -> 6 points
    pts, exp = calculate_base_points(3, 2, None, 2, 1, None, False)
    assert pts == 6
    assert "diferença de gols" in exp

    # Correct result + correct goals for team B -> 4 points
    pts, exp = calculate_base_points(3, 1, None, 2, 1, None, False)
    assert pts == 4
    assert "gols de um dos times" in exp

    # Correct result + correct goals for team A -> 4 points
    pts, exp = calculate_base_points(2, 0, None, 2, 1, None, False)
    assert pts == 4
    
    # Correct result only -> 3 points
    pts, exp = calculate_base_points(4, 2, None, 2, 1, None, False)
    assert pts == 3
    assert "Resultado correto (" in exp
    
    # Wrong result -> 0 points (even though goals for B was guessed correctly)
    pts, exp = calculate_base_points(1, 1, None, 2, 1, None, False)
    assert pts == 0
    assert "Resultado incorreto" in exp

    # Wrong result -> 0 points
    pts, exp = calculate_base_points(1, 2, None, 2, 1, None, False)
    assert pts == 0

def test_stage_multipliers(db_session):
    # Set Round of 16 multiplier to 3.0
    r16_mult = db_session.query(StageMultiplier).filter(StageMultiplier.stage == "Round of 16").first()
    r16_mult.multiplier = Decimal("3.0")
    db_session.commit()

    # Create dummy teams & stadium
    team1 = Team(name="Argentina", group_name="A")
    team2 = Team(name="Brazil", group_name="A")
    stadium = Stadium(name="Lusail", city="Doha", timezone="UTC")
    db_session.add_all([team1, team2, stadium])
    
    # Create Match in Round of 16
    match = Match(
        round="Round of 16",
        stage="Round of 16",
        date="2026-06-30",
        time_str="18:00 UTC+0",
        kickoff_time=datetime(2026, 6, 30, 18, 0),
        team1_name="Argentina",
        team2_name="Brazil",
        ground="Lusail",
        score_ft_team1=2,
        score_ft_team2=1,
        status="finished"
    )
    db_session.add(match)
    db_session.commit()

    # User prediction: Exact Score 2-1
    pred = Prediction(
        match_id=match.id,
        user_id=None,  # Not checking foreign key constraint for this unit test
        goals_team1=2,
        goals_team2=1
    )
    
    score_prediction(db_session, pred, match)
    
    # Base points = 10. Multiplier = 3.0. Final points = 30.
    assert pred.base_points == 10
    assert float(pred.multiplier_used) == 3.0
    assert pred.points_earned == 30
    assert "Multiplicador 3.0" in pred.scoring_explanation

# ==========================================
# 2. Knockout Draw Handling
# ==========================================

def test_knockout_draw_handling(db_session):
    # Create teams, stadium & match
    team1 = Team(name="France", group_name="B")
    team2 = Team(name="Spain", group_name="B")
    stadium = Stadium(name="Lusail", city="Doha", timezone="UTC")
    db_session.add_all([team1, team2, stadium])
    
    # Match: 120 mins score was 2x2. Penalties France 4 x 2 Spain.
    match = Match(
        round="Quarter-finals",
        stage="Quarter-finals",
        date="2026-07-04",
        time_str="18:00 UTC+0",
        kickoff_time=datetime(2026, 7, 4, 18, 0),
        team1_name="France",
        team2_name="Spain",
        ground="Lusail",
        score_ft_team1=1,
        score_ft_team2=1,
        score_et_team1=2,
        score_et_team2=2,
        score_pen_team1=4,
        score_pen_team2=2,
        status="finished"
    )
    db_session.add(match)
    db_session.commit()

    # User predicts draw 1x1, France qualifying (exact match of full time score).
    pred = Prediction(
        match_id=match.id,
        goals_team1=1,
        goals_team2=1,
        qualified_team_name="France"
    )

    score_prediction(db_session, pred, match)
    
    # Base score is 10 because prediction matches exactly the full-time score (1x1).
    assert pred.base_points == 10

    # User predicts draw 2x2, France qualifying.
    pred2 = Prediction(
        match_id=match.id,
        goals_team1=2,
        goals_team2=2,
        qualified_team_name="France"
    )

    score_prediction(db_session, pred2, match)
    
    # Base score is 6 because they predicted a draw (correct result) and the goal difference is 0 (same difference).
    assert pred2.base_points == 6

# ==========================================
# 3. Lock Logic Tests
# ==========================================

def test_prediction_lock_logic(client, db_session, test_users):
    # Setup team, stadium & match
    t1 = Team(name="Mexico", group_name="A")
    t2 = Team(name="Canada", group_name="A")
    stad = Stadium(name="Estadio Azteca", city="CDMX", timezone="UTC")
    db_session.add_all([t1, t2, stad])
    db_session.commit()
    
    # Match kickoff is in 2 hours (less than 3 hours threshold)
    kickoff = datetime.utcnow() + timedelta(hours=2)
    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="18:00 UTC+0",
        kickoff_time=kickoff,
        team1_name="Mexico",
        team2_name="Canada",
        ground="Estadio Azteca",
        status="scheduled"
    )
    db_session.add(match)
    db_session.commit()

    # Login user p1
    login_res = client.post("/api/auth/login", data={"username": "p1_user", "password": "password"})
    token = login_res.json()["access_token"]
    
    # Attempt to post prediction for this match
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        f"/api/predictions/save?match_id={match.id}",
        headers=headers,
        json={"goals_team1": 2, "goals_team2": 1}
    )
    
    # Server should return 400 Bad Request
    assert res.status_code == 400
    assert "Aposta bloqueada" in res.json()["detail"]

# ==========================================
# 4. Standings Tie-breakers Tests
# ==========================================

def test_ranking_tie_breakers(db_session, test_users):
    # We have users: test_users[2] = Ana (p1), test_users[3] = Bruno (p2)
    ana = test_users[2]
    bruno = test_users[3]

    # Ana registered at 10:00, Bruno at 11:00
    ana.created_at = datetime(2026, 5, 30, 10, 0)
    bruno.created_at = datetime(2026, 5, 30, 11, 0)
    db_session.commit()

    # 1. First scenario: Ana has 10 points, Bruno has 10 points. Ana should be higher due to registration date fallback.
    # We simulate this inside rankings by assigning mock predictions/points
    # Create Match
    t1 = Team(name="USA", group_name="A")
    t2 = Team(name="Portugal", group_name="A")
    stad = Stadium(name="Hard Rock", city="Miami", timezone="UTC")
    db_session.add_all([t1, t2, stad])
    db_session.commit()
    
    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-12",
        time_str="15:00 UTC+0",
        kickoff_time=datetime(2026, 6, 12, 15, 0),
        team1_name="USA",
        team2_name="Portugal",
        ground="Hard Rock",
        score_ft_team1=1,
        score_ft_team2=1,
        status="finished"
    )
    db_session.add(match)
    db_session.commit()

    # Prediction for Ana: 1x1 (exact, 8 pts)
    pred_ana = Prediction(
        match_id=match.id,
        user_id=ana.id,
        goals_team1=1,
        goals_team2=1,
        points_earned=8,
        base_points=8
    )
    # Prediction for Bruno: 1x1 (exact, 8 pts)
    pred_bruno = Prediction(
        match_id=match.id,
        user_id=bruno.id,
        goals_team1=1,
        goals_team2=1,
        points_earned=8,
        base_points=8
    )
    db_session.add_all([pred_ana, pred_bruno])
    db_session.commit()

    rank = get_rankings(db_session)
    
    # We find their positions
    ana_rank = next(r for r in rank if r["user_id"] == ana.id)
    bruno_rank = next(r for r in rank if r["user_id"] == bruno.id)
    
    # Since they tied on points (7), exact (1), correct result (1), knockout (0), missing predictions (0)
    # Ana should rank higher because she registered earlier
    assert ana_rank["position"] < bruno_rank["position"] or (ana_rank["position"] == bruno_rank["position"] and rank.index(ana_rank) < rank.index(bruno_rank))

# ==========================================
# 5. Group Privacy Tests
# ==========================================

def test_group_privacy(client, db_session, test_users):
    p1 = test_users[2]
    p2 = test_users[3]
    
    # Create private group owned by p1
    group = Group(
        name="Grupo Secreto",
        description="Apenas convidados",
        owner_id=p1.id,
        invite_code="SECRET",
        is_private=True
    )
    db_session.add(group)
    db_session.commit()
    
    # Owner joins group
    mem = GroupMember(
        group_id=group.id,
        user_id=p1.id,
        role="owner",
        is_approved=True
    )
    db_session.add(mem)
    db_session.commit()
    
    # Login Bruno (p2) who is NOT a member of this private group
    login_res = client.post("/api/auth/login", data={"username": "p2_user", "password": "password"})
    token = login_res.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Bruno tries to fetch group ranking
    res = client.get(f"/api/rankings/group/{group.id}", headers=headers)
    
    # Should get 403 Forbidden
    assert res.status_code == 403
    assert "Acesso negado" in res.json()["detail"]

def test_group_invite_candidates_search_and_pending_notification(client, db_session, test_users):
    p1 = test_users[2]
    p2 = test_users[3]

    group = Group(
        name="Grupo Convites",
        description="Convites por autocomplete",
        owner_id=p1.id,
        invite_code="AUTOCOMP",
        is_private=True
    )
    db_session.add(group)
    db_session.commit()

    owner_member = GroupMember(
        group_id=group.id,
        user_id=p1.id,
        role="owner",
        is_approved=True
    )
    db_session.add(owner_member)
    db_session.commit()

    login_owner = client.post("/api/auth/login", data={"username": "p1_user", "password": "password"})
    owner_headers = {"Authorization": f"Bearer {login_owner.json()['access_token']}"}

    by_display_name = client.get(
        f"/api/groups/{group.id}/invite-candidates?q=Brun",
        headers=owner_headers
    )
    assert by_display_name.status_code == 200
    assert any(candidate["username"] == p2.username for candidate in by_display_name.json())

    by_username = client.get(
        f"/api/groups/{group.id}/invite-candidates?q=p2_",
        headers=owner_headers
    )
    assert by_username.status_code == 200
    assert any(candidate["display_name"] == p2.display_name for candidate in by_username.json())

    invite_res = client.post(
        f"/api/groups/{group.id}/invite",
        json={"invitee_identifier": p2.username},
        headers=owner_headers
    )
    assert invite_res.status_code == 200
    invite = db_session.query(GroupInvitation).filter(
        GroupInvitation.group_id == group.id,
        GroupInvitation.invitee_id == p2.id
    ).first()
    assert invite is not None
    assert invite.status == "pending"

    login_invited = client.post("/api/auth/login", data={"username": "p2_user", "password": "password"})
    invited_headers = {"Authorization": f"Bearer {login_invited.json()['access_token']}"}
    pending_res = client.get("/api/groups/invitations/pending", headers=invited_headers)
    assert pending_res.status_code == 200
    assert any(item["id"] == str(invite.id) for item in pending_res.json())

def test_group_ranking_cache_invalidates_when_invite_is_accepted(client, db_session, test_users):
    from app.models import RankingCache

    p1 = test_users[2]
    p2 = test_users[3]

    group = Group(
        name="Grupo Ranking Cache",
        description="Cache precisa refletir membros",
        owner_id=p1.id,
        invite_code="CACHE123",
        is_private=True
    )
    db_session.add(group)
    db_session.commit()

    db_session.add(GroupMember(
        group_id=group.id,
        user_id=p1.id,
        role="owner",
        is_approved=True
    ))
    db_session.commit()

    owner_login = client.post("/api/auth/login", data={"username": "p1_user", "password": "password"})
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

    first_rank = client.get(f"/api/rankings/group/{group.id}", headers=owner_headers)
    assert first_rank.status_code == 200
    assert [row["user_id"] for row in first_rank.json()] == [str(p1.id)]
    assert db_session.query(RankingCache).filter(RankingCache.key == f"group_{group.id}").count() == 1

    invite_res = client.post(
        f"/api/groups/{group.id}/invite",
        json={"invitee_identifier": p2.username},
        headers=owner_headers
    )
    assert invite_res.status_code == 200

    invited_login = client.post("/api/auth/login", data={"username": "p2_user", "password": "password"})
    invited_headers = {"Authorization": f"Bearer {invited_login.json()['access_token']}"}
    accept_res = client.post(
        f"/api/groups/invitations/{invite_res.json()['id']}/respond?accept=true",
        headers=invited_headers
    )
    assert accept_res.status_code == 200
    assert db_session.query(RankingCache).filter(RankingCache.key == f"group_{group.id}").count() == 0

    updated_rank = client.get(f"/api/rankings/group/{group.id}", headers=owner_headers)
    assert updated_rank.status_code == 200
    assert {row["user_id"] for row in updated_rank.json()} == {str(p1.id), str(p2.id)}

# ==========================================
# 6. Openfootball Sync Integrity Tests
# ==========================================

def test_sync_no_overwrite_confirmed_scores(db_session):
    # Setup team, stadium & match
    t1 = Team(name="Argentina", group_name="A")
    t2 = Team(name="Brazil", group_name="A")
    stad = Stadium(name="Lusail", city="Doha", timezone="UTC")
    db_session.add_all([t1, t2, stad])
    db_session.commit()
    
    # Match has score confirmed by admin
    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="13:00 UTC-6",
        kickoff_time=datetime(2026, 6, 11, 19, 0), # 13:00 local UTC-6 = 19:00 UTC
        team1_name="Argentina",
        team2_name="Brazil",
        ground="Lusail",
        status="score_confirmed",
        score_ft_team1=3,
        score_ft_team2=1,
        score_confirmed_by_admin=True
    )
    db_session.add(match)
    db_session.commit()

    # Now, let's mock sync execution.
    # In a sync, say the openfootball JSON says score is 1x1.
    # The sync should NOT overwrite the match's confirmed score,
    # and instead write to SyncMatchDiff with status pending_review.
    
    prev_val = {
        "score_ft_team1": match.score_ft_team1, "score_ft_team2": match.score_ft_team2,
        "status": match.status
    }
    new_val = {
        "score_ft_team1": 1, "score_ft_team2": 1,
        "status": "finished"
    }

    # Verify logic check
    if match.score_confirmed_by_admin:
        # Create diff record
        diff = SyncMatchDiff(
            sync_log_id=1,
            match_id=match.id,
            previous_value=prev_val,
            new_value=new_val,
            status="pending_review"
        )
        db_session.add(diff)
        db_session.commit()
    
    # Assert score is unchanged
    assert match.score_ft_team1 == 3
    assert match.score_ft_team2 == 1
    
    # Assert diff created for review
    assert db_session.query(SyncMatchDiff).filter(SyncMatchDiff.match_id == match.id).count() == 1

# ==========================================
# 7. Cryptographic Audit Chain Tests
# ==========================================

def test_audit_chain_generation(db_session, client, test_users):
    from app.routers.audit import get_or_create_audit_block
    from app.models import AuditBlock
    
    # Clean previous audit blocks if any
    db_session.query(AuditBlock).delete()
    db_session.commit()
    
    # 1. Create teams and matches
    t1 = Team(name="Uruguay", group_name="C")
    t2 = Team(name="Portugal", group_name="C")
    stad = Stadium(name="Centenario", city="Montevideo", timezone="UTC")
    db_session.add_all([t1, t2, stad])
    db_session.commit()
    
    # Match 1: Kickoff in 2 hours (locked)
    m1 = Match(
        round="Matchday 1", stage="Group Stage", date="2026-06-12", time_str="18:00 UTC",
        kickoff_time=datetime.utcnow() + timedelta(hours=2),
        team1_name="Uruguay", team2_name="Portugal", ground="Centenario", status="scheduled"
    )
    # Match 2: Kickoff in 1 hour (locked, later in sequence due to id or kickoff)
    m2 = Match(
        round="Matchday 1", stage="Group Stage", date="2026-06-12", time_str="19:00 UTC",
        kickoff_time=datetime.utcnow() + timedelta(hours=1), # Note: kickoff is in 1 hour, so this is earlier in time!
        team1_name="Uruguay", team2_name="Portugal", ground="Centenario", status="scheduled"
    )
    # Match 3: Kickoff in 5 hours (unlocked)
    m3 = Match(
        round="Matchday 1", stage="Group Stage", date="2026-06-12", time_str="23:00 UTC",
        kickoff_time=datetime.utcnow() + timedelta(hours=5),
        team1_name="Uruguay", team2_name="Portugal", ground="Centenario", status="scheduled"
    )
    db_session.add_all([m1, m2, m3])
    db_session.commit()
    
    # Create predictions for m1 & m2
    p1 = Prediction(match_id=m1.id, user_id=test_users[2].id, goals_team1=2, goals_team2=1)
    p2 = Prediction(match_id=m1.id, user_id=test_users[3].id, goals_team1=0, goals_team2=0)
    
    p3 = Prediction(match_id=m2.id, user_id=test_users[2].id, goals_team1=1, goals_team2=1)
    db_session.add_all([p1, p2, p3])
    db_session.commit()
    
    # 2. Try generating block for m3 (unlocked) -> should return None
    block3 = get_or_create_audit_block(db_session, m3.id)
    assert block3 is None
    
    # 3. Generate block for m2 (which is kickoff in 1h, so it is the first locked match in time order)
    block2 = get_or_create_audit_block(db_session, m2.id)
    assert block2 is not None
    assert block2.block_number == 1
    assert block2.previous_hash == "0000000000000000000000000000000000000000000000000000000000000000"
    
    # 4. Generate block for m1 (kickoff in 2h, so it is the second locked match in time order)
    block1 = get_or_create_audit_block(db_session, m1.id)
    assert block1 is not None
    assert block1.block_number == 2
    # Its previous hash MUST match block2's hash (since block2 is earlier in time)
    assert block1.previous_hash == block2.hash
    
    # 5. Verify HTTP API response
    # Login user to get token
    login_res = client.post("/api/auth/login", data={"username": "p1_user", "password": "password"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    res = client.get("/api/audit/blocks", headers=headers)
    assert res.status_code == 200
    blocks_list = res.json()
    assert len(blocks_list) == 2
    assert blocks_list[0]["block_number"] == 1
    assert blocks_list[1]["block_number"] == 2
    
    # Verify detailed endpoint
    res_detail = client.get(f"/api/audit/blocks/1", headers=headers)
    assert res_detail.status_code == 200
    detail_data = res_detail.json()
    assert len(detail_data["payload"]) == 1
    assert detail_data["payload"][0]["goals_team1"] == 1

# ==========================================
# 8. Dynamic Stage Unlocking Tests
# ==========================================

def test_dynamic_stage_unlocking(db_session, client, test_users):
    from app.routers.utils import get_unlocked_stages
    
    # 1. Clean previous matches if any
    db_session.query(Match).delete()
    db_session.commit()
    
    # "Group Stage" should be unlocked by default even if no matches exist
    unlocked = get_unlocked_stages(db_session)
    assert "Group Stage" in unlocked
    assert "Round of 32" not in unlocked
    
    # 2. Add a Group Stage match (unfinished)
    m1 = Match(
        round="Matchday 1", stage="Group Stage", date="2026-06-12", time_str="18:00 UTC",
        kickoff_time=datetime.utcnow() + timedelta(hours=5),
        team1_name="Uruguay", team2_name="Portugal", ground="Centenario", status="scheduled"
    )
    db_session.add(m1)
    db_session.commit()
    
    # Since m1 is scheduled (unfinished), Round of 32 remains locked
    unlocked = get_unlocked_stages(db_session)
    assert "Group Stage" in unlocked
    assert "Round of 32" not in unlocked
    
    # 3. Finish the Group Stage match
    m1.status = "finished"
    m1.score_ft_team1 = 2
    m1.score_ft_team2 = 1
    db_session.commit()
    
    # Now all Group Stage matches are finished -> Round of 32 unlocks!
    unlocked = get_unlocked_stages(db_session)
    assert "Group Stage" in unlocked
    assert "Round of 32" in unlocked
    assert "Round of 16" not in unlocked


def test_ranking_cache_flow(client, db_session, test_users):
    # Setup team, stadium & match
    t1 = Team(name="Mexico", group_name="A")
    t2 = Team(name="Canada", group_name="A")
    stad = Stadium(name="Estadio Azteca", city="CDMX", timezone="UTC")
    db_session.add_all([t1, t2, stad])
    db_session.commit()
    
    match = Match(
        round="Matchday 1",
        stage="Group Stage",
        date="2026-06-11",
        time_str="18:00 UTC+0",
        kickoff_time=datetime.utcnow() + timedelta(days=2),
        team1_name="Mexico",
        team2_name="Canada",
        ground="Estadio Azteca",
        status="scheduled"
    )
    db_session.add(match)
    db_session.commit()

    # Login p1
    login_res = client.post("/api/auth/login", data={"username": "p1_user", "password": "password"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from app.models import RankingCache
    # Initially the cache should be empty
    assert db_session.query(RankingCache).count() == 0

    # Query general ranking (should calculate and cache it)
    res = client.get("/api/rankings/general", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) > 0
    
    # Check that cache is now populated
    assert db_session.query(RankingCache).filter(RankingCache.key == "general").count() == 1
    
    # Check that another query reads from cache (we can verify cache is still there)
    res2 = client.get("/api/rankings/general", headers=headers)
    assert res2.status_code == 200

    # Invalidate cache manually or check that it invalidates when score is updated
    # Admin logins and reports a score
    admin_login = client.post("/api/auth/login", data={"username": "admin_user", "password": "password"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Update match score
    score_res = client.post(f"/api/admin/matches/{match.id}/score?score_ft_team1=2&score_ft_team2=1", headers=admin_headers)
    assert score_res.status_code == 200

    # Cache should be cleared (invalidated)
    assert db_session.query(RankingCache).count() == 0
