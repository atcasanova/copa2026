from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import io
import csv
import secrets
import os
from fastapi.responses import StreamingResponse

from ..db import get_db
from ..models import User, Match, Prediction, StageMultiplier, MultiplierHistory, Announcement, AuditLog, SyncLog, SyncMatchDiff, Team, Stadium, SystemInvitation, SystemSetting, Group, GroupInvitation, PasswordResetToken, FootballDataSyncLog
from ..schemas import (
    MatchResponse, StageMultiplierResponse, StageMultiplierUpdate, MultiplierHistoryResponse,
    AnnouncementCreate, AnnouncementResponse, UserResponse, AuditLogResponse, SyncLogResponse, SyncMatchDiffResponse,
    SystemInvitationCreate, SystemInvitationResponse, MatchScoreBatchUpdate, MatchScoreUpdate,
    FootballDataSyncLogResponse, MatchDefineTeams
)
from ..auth import require_system_admin, require_score_admin, require_participant
from ..scoring import (
    recalculate_match_predictions, recalculate_all_predictions_and_rankings,
    DEFAULT_MULTIPLIERS, invalidate_ranking_cache,
    capture_ranking_snapshot, capture_ranking_update_snapshot,
    should_publish_ranking_update_for_matches
)
from ..sync import seed_initial_data, sync_openfootball_data
from ..settings import get_prediction_lock_hours, set_prediction_lock_hours, MAX_PREDICTION_LOCK_HOURS
from ..notifications import send_general_ranking_notification
from ..football_data import sync_finished_scores_from_football_data
from .utils import user_name_sort_key

def sanitize_csv_value(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    val_str = str(val)
    if val_str and val_str[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + val_str
    return val_str

def get_or_create_hidden_registration_setting(db: Session) -> SystemSetting:
    setting = db.query(SystemSetting).filter(SystemSetting.key == "hidden_registration_code").first()
    if setting:
        return setting

    setting = SystemSetting(
        key="hidden_registration_code",
        value=secrets.token_urlsafe(32)
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting

router = APIRouter(prefix="/api/admin", tags=["Administration"])

# ==========================================
# 1. Match Management (Score Admin / System Admin)
# ==========================================

def _set_match_score(db: Session, match: Match, score: MatchScoreUpdate, current_user: User) -> Match:
    old_val = {
        "score_ft_team1": match.score_ft_team1, "score_ft_team2": match.score_ft_team2,
        "score_et_team1": match.score_et_team1, "score_et_team2": match.score_et_team2,
        "score_pen_team1": match.score_pen_team1, "score_pen_team2": match.score_pen_team2,
        "status": match.status
    }

    match.score_ft_team1 = score.score_ft_team1
    match.score_ft_team2 = score.score_ft_team2
    match.score_et_team1 = score.score_et_team1
    match.score_et_team2 = score.score_et_team2
    match.score_pen_team1 = score.score_pen_team1
    match.score_pen_team2 = score.score_pen_team2
    match.status = "score_pending_review"

    db.flush()

    new_val = {
        "score_ft_team1": match.score_ft_team1, "score_ft_team2": match.score_ft_team2,
        "score_et_team1": match.score_et_team1, "score_et_team2": match.score_et_team2,
        "score_pen_team1": match.score_pen_team1, "score_pen_team2": match.score_pen_team2,
        "status": match.status
    }

    audit = AuditLog(
        user_id=current_user.id,
        action="match_score_insert",
        target_type="match",
        target_id=str(match.id),
        old_value=old_val,
        new_value=new_val
    )
    db.add(audit)
    return match


def _publish_ranking_update_if_ready(db: Session, matches: list[Match]) -> bool:
    if not should_publish_ranking_update_for_matches(db, matches):
        return False
    kickoff_time = matches[0].kickoff_time if matches else None
    capture_ranking_snapshot(db)
    capture_ranking_update_snapshot(db, kickoff_time=kickoff_time)
    send_general_ranking_notification(db)
    return True

@router.post("/matches/{match_id}/score", response_model=MatchResponse)
def update_match_score(
    match_id: int,
    score_ft_team1: int = Query(..., ge=0),
    score_ft_team2: int = Query(..., ge=0),
    score_et_team1: Optional[int] = Query(None, ge=0),
    score_et_team2: Optional[int] = Query(None, ge=0),
    score_pen_team1: Optional[int] = Query(None, ge=0),
    score_pen_team2: Optional[int] = Query(None, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    score = MatchScoreUpdate(
        match_id=match_id,
        score_ft_team1=score_ft_team1,
        score_ft_team2=score_ft_team2,
        score_et_team1=score_et_team1,
        score_et_team2=score_et_team2,
        score_pen_team1=score_pen_team1,
        score_pen_team2=score_pen_team2
    )
    _set_match_score(db, match, score, current_user)
    db.commit()
    db.refresh(match)

    # Recalculate predictions
    recalculate_match_predictions(db, match.id)
    _publish_ranking_update_if_ready(db, [match])

    return match

@router.post("/matches/score-batch", response_model=List[MatchResponse])
def update_match_scores_batch(
    payload: MatchScoreBatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    matches_by_id = {
        match.id: match
        for match in db.query(Match).filter(Match.id.in_([score.match_id for score in payload.scores])).all()
    }
    missing_ids = [score.match_id for score in payload.scores if score.match_id not in matches_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Partida(s) não encontrada(s): {', '.join(map(str, missing_ids))}.")

    updated_matches = []
    for score in payload.scores:
        updated_matches.append(_set_match_score(db, matches_by_id[score.match_id], score, current_user))

    db.commit()
    for match in updated_matches:
        db.refresh(match)
        recalculate_match_predictions(db, match.id)

    _publish_ranking_update_if_ready(db, updated_matches)
    return updated_matches

@router.post("/matches/{match_id}/confirm-score", response_model=MatchResponse)
def confirm_match_score(
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    if match.score_ft_team1 is None or match.score_ft_team2 is None:
        raise HTTPException(status_code=400, detail="Não é possível confirmar o resultado de uma partida sem placar definido.")

    old_status = match.status
    match.status = "score_confirmed"
    match.score_confirmed_by_admin = True

    db.commit()
    db.refresh(match)

    # Log action
    audit = AuditLog(
        user_id=current_user.id,
        action="match_score_confirm",
        target_type="match",
        target_id=str(match.id),
        old_value={"status": old_status, "confirmed": False},
        new_value={"status": match.status, "confirmed": True}
    )
    db.add(audit)
    db.commit()

    # Force final recalculation
    recalculate_match_predictions(db, match.id)
    _publish_ranking_update_if_ready(db, [match])

    return match

@router.post("/matches/{match_id}/status", response_model=MatchResponse)
def change_match_status(
    match_id: int,
    status_str: str = Query(..., enum=["scheduled", "locked", "live", "postponed", "cancelled"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    old_status = match.status
    match.status = status_str
    
    # If cancelled/postponed, we might clear scores
    if status_str in ["postponed", "cancelled"]:
        match.score_ft_team1 = None
        match.score_ft_team2 = None
        match.score_et_team1 = None
        match.score_et_team2 = None
        match.score_pen_team1 = None
        match.score_pen_team2 = None
        match.score_confirmed_by_admin = False

    db.commit()
    db.refresh(match)

    # Log action
    audit = AuditLog(
        user_id=current_user.id,
        action="match_status_change",
        target_type="match",
        target_id=str(match.id),
        old_value={"status": old_status},
        new_value={"status": match.status}
    )
    db.add(audit)
    db.commit()

    # Recalculate predictions
    recalculate_match_predictions(db, match.id)
    capture_ranking_snapshot(db)

    return match

@router.post("/football-data/check-scores")
def check_football_data_scores(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    return sync_finished_scores_from_football_data(db, trigger="manual")


@router.post("/football-data/sync-fixtures")
def trigger_football_data_fixtures_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    from ..football_data import sync_fixtures_from_football_data
    results = sync_fixtures_from_football_data(db, trigger="manual")
    
    audit = AuditLog(
        user_id=current_user.id,
        action="football_data_fixtures_sync_trigger",
        target_type="sync",
        new_value=results
    )
    db.add(audit)
    db.commit()
    
    return results


ORIGINAL_PLACEHOLDERS = {
    73: ("2A", "2B"),
    74: ("1E", "3A/B/C/D/F"),
    75: ("1F", "2C"),
    76: ("1C", "2F"),
    77: ("1I", "3C/D/F/G/H"),
    78: ("2E", "2I"),
    79: ("1A", "3C/E/F/H/I"),
    80: ("1L", "3E/H/I/J/K"),
    81: ("1D", "3B/E/F/I/J"),
    82: ("1G", "3A/E/H/I/J"),
    83: ("2K", "2L"),
    84: ("1H", "2J"),
    85: ("1B", "3E/F/G/I/J"),
    86: ("1J", "2H"),
    87: ("1K", "3D/E/I/J/L"),
    88: ("2D", "2G"),
    89: ("W74", "W77"),
    90: ("W73", "W75"),
    91: ("W76", "W78"),
    92: ("W79", "W80"),
    93: ("W83", "W84"),
    94: ("W81", "W82"),
    95: ("W86", "W88"),
    96: ("W85", "W87"),
    97: ("W89", "W90"),
    98: ("W93", "W94"),
    99: ("W91", "W92"),
    100: ("W95", "W96"),
    101: ("W97", "W98"),
    102: ("W99", "W100"),
    103: ("L101", "L102"),
    104: ("W101", "W102"),
}

def get_possible_teams(db: Session, placeholder: str) -> list[dict]:
    import re
    from ..models import Team
    placeholder = placeholder.strip()
    
    # Check if this name is a real team
    t_exist = db.query(Team).filter(Team.name == placeholder).first()
    if t_exist and t_exist.group_name != "Knockout Placeholder":
        return [{"name": t_exist.name, "flag_icon": t_exist.flag_icon}]
        
    # If it is a group letter position, e.g. "1A", "2B", "1E"
    if len(placeholder) == 2 and placeholder[0] in ("1", "2") and "A" <= placeholder[1] <= "L":
        pos = int(placeholder[0]) - 1
        g_letter = placeholder[1]
        group_teams = db.query(Team).filter(Team.group_name.in_([g_letter, f"Grupo {g_letter}"])).all()
        return [{"name": t.name, "flag_icon": t.flag_icon} for t in group_teams]

    # If it is a third-placed placeholder, e.g. "3A/B/C/D/F"
    if placeholder.startswith("3"):
        group_letters = [c for c in placeholder[1:] if "A" <= c <= "L"]
        possible_dict = {}
        for letter in group_letters:
            group_teams = db.query(Team).filter(Team.group_name.in_([letter, f"Grupo {letter}"])).all()
            for t in group_teams:
                possible_dict[t.name] = t.flag_icon
        return [{"name": name, "flag_icon": icon} for name, icon in sorted(possible_dict.items())]

    # If it is a winner/loser placeholder, e.g. "W74", "L101"
    if len(placeholder) > 1 and placeholder[0] in ("W", "L") and placeholder[1:].isdigit():
        ref_id = int(placeholder[1:])
        if ref_id in ORIGINAL_PLACEHOLDERS:
            orig_t1, orig_t2 = ORIGINAL_PLACEHOLDERS[ref_id]
            p1 = get_possible_teams(db, orig_t1)
            p2 = get_possible_teams(db, orig_t2)
            combined = {}
            for item in p1 + p2:
                combined[item["name"]] = item["flag_icon"]
            return [{"name": name, "flag_icon": icon} for name, icon in sorted(combined.items())]

    return []


@router.get("/matches/knockout-setup")
def get_knockout_setup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    from ..models import Team, Match
    from .utils import normalized_text_sort_key
    
    # Calculate group standings
    groups = {}
    teams = db.query(Team).filter(Team.group_name != "Knockout Placeholder").all()
    standings = {}
    for t in teams:
        standings[t.name] = {
            "team_name": t.name,
            "group_name": t.group_name,
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
        }

    matches = db.query(Match).filter(
        Match.stage == "Group Stage",
        Match.status.in_(["finished", "score_confirmed"])
    ).all()

    for m in matches:
        t1, t2 = m.team1_name, m.team2_name
        s1, s2 = m.score_ft_team1, m.score_ft_team2
        if s1 is None or s2 is None:
            continue
        if t1 in standings and t2 in standings:
            standings[t1]["played"] += 1
            standings[t2]["played"] += 1
            standings[t1]["goals_for"] += s1
            standings[t1]["goals_against"] += s2
            standings[t2]["goals_for"] += s2
            standings[t2]["goals_against"] += s1
            standings[t1]["goal_difference"] = standings[t1]["goals_for"] - standings[t1]["goals_against"]
            standings[t2]["goal_difference"] = standings[t2]["goals_for"] - standings[t2]["goals_against"]
            if s1 > s2:
                standings[t1]["points"] += 3
                standings[t1]["wins"] += 1
                standings[t2]["losses"] += 1
            elif s1 < s2:
                standings[t2]["points"] += 3
                standings[t2]["wins"] += 1
                standings[t1]["losses"] += 1
            else:
                standings[t1]["points"] += 1
                standings[t2]["points"] += 1
                standings[t1]["draws"] += 1
                standings[t2]["draws"] += 1

    for team_name, stats in standings.items():
        g_name = stats["group_name"]
        groups.setdefault(g_name, []).append(stats)

    for g_name, team_list in groups.items():
        team_list.sort(key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]), reverse=True)

    third_placed = []
    for g_name, team_list in groups.items():
        if len(team_list) >= 3:
            third_placed.append(team_list[2])
    third_placed.sort(key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]), reverse=True)

    def find_suggestion(placeholder: str) -> str | None:
        placeholder = placeholder.strip()
        t_exist = db.query(Team).filter(Team.name == placeholder).first()
        if t_exist and t_exist.group_name != "Knockout Placeholder":
            return placeholder

        if len(placeholder) == 2 and placeholder[0] in ("1", "2") and "A" <= placeholder[1] <= "L":
            pos = int(placeholder[0]) - 1
            g_letter = placeholder[1]
            g_name = f"Grupo {g_letter}"
            if g_name in groups and len(groups[g_name]) > pos:
                return groups[g_name][pos]["team_name"]

        if placeholder.startswith("3"):
            allowed_groups = [f"Grupo {c}" for c in placeholder[1:].split('/')]
            for t in third_placed[:8]:
                if t["group_name"] in allowed_groups:
                    return t["team_name"]

        if placeholder.startswith("W") and placeholder[1:].isdigit():
            m_id = int(placeholder[1:])
            m_ref = db.query(Match).filter(Match.id == m_id).first()
            if m_ref and m_ref.status in ("finished", "score_confirmed"):
                p1 = m_ref.score_pen_team1 or 0
                p2 = m_ref.score_pen_team2 or 0
                et1 = m_ref.score_et_team1 or m_ref.score_ft_team1
                et2 = m_ref.score_et_team2 or m_ref.score_ft_team2
                if p1 > p2:
                    return m_ref.team1_name
                elif p2 > p1:
                    return m_ref.team2_name
                elif et1 > et2:
                    return m_ref.team1_name
                elif et2 > et1:
                    return m_ref.team2_name

        if placeholder.startswith("L") and placeholder[1:].isdigit():
            m_id = int(placeholder[1:])
            m_ref = db.query(Match).filter(Match.id == m_id).first()
            if m_ref and m_ref.status in ("finished", "score_confirmed"):
                p1 = m_ref.score_pen_team1 or 0
                p2 = m_ref.score_pen_team2 or 0
                et1 = m_ref.score_et_team1 or m_ref.score_ft_team1
                et2 = m_ref.score_et_team2 or m_ref.score_ft_team2
                if p1 > p2:
                    return m_ref.team2_name
                elif p2 > p1:
                    return m_ref.team1_name
                elif et1 > et2:
                    return m_ref.team2_name
                elif et2 > et1:
                    return m_ref.team1_name
        return None

    knockout_matches = db.query(Match).filter(Match.stage != "Group Stage").order_by(Match.kickoff_time.asc()).all()
    placeholder_team_names = {t.name for t in db.query(Team).filter(Team.group_name == "Knockout Placeholder").all()}
    
    matches_data = []
    for m in knockout_matches:
        orig_t1, orig_t2 = ORIGINAL_PLACEHOLDERS.get(m.id, (m.team1_name, m.team2_name))
        possible_t1 = get_possible_teams(db, orig_t1)
        possible_t2 = get_possible_teams(db, orig_t2)
        
        # If possible teams list is empty (unseeded DB), fallback to all teams
        if not possible_t1 or not possible_t2:
            all_teams_list = [{"name": t.name, "flag_icon": t.flag_icon} for t in db.query(Team).filter(Team.group_name != "Knockout Placeholder").all()]
            if not possible_t1:
                possible_t1 = all_teams_list
            if not possible_t2:
                possible_t2 = all_teams_list

        matches_data.append({
            "id": m.id,
            "round": m.round,
            "stage": m.stage,
            "date": m.date,
            "time_str": m.time_str,
            "kickoff_time": m.kickoff_time.isoformat(),
            "team1_name": m.team1_name,
            "team2_name": m.team2_name,
            "team1_is_placeholder": m.team1_name in placeholder_team_names,
            "team2_is_placeholder": m.team2_name in placeholder_team_names,
            "suggested_team1": find_suggestion(m.team1_name),
            "suggested_team2": find_suggestion(m.team2_name),
            "possible_teams1": possible_t1,
            "possible_teams2": possible_t2,
        })

    all_teams = [{"name": t.name, "flag_icon": t.flag_icon} for t in teams]
    return {
        "matches": matches_data,
        "groups": groups,
        "third_placed": third_placed,
        "all_teams": all_teams
    }


@router.post("/matches/{match_id}/define-teams")
def define_matchout_teams(
    match_id: int,
    payload: MatchDefineTeams,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    from ..models import Match, Team, AuditLog
    
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")
        
    if match.stage == "Group Stage":
        raise HTTPException(status_code=400, detail="Não é permitido alterar times de partidas da fase de grupos.")

    t1 = db.query(Team).filter(Team.name == payload.team1_name).first()
    t2 = db.query(Team).filter(Team.name == payload.team2_name).first()
    
    if not t1 or t1.group_name == "Knockout Placeholder":
        raise HTTPException(status_code=400, detail=f"Time 1 '{payload.team1_name}' inválido ou é placeholder.")
    if not t2 or t2.group_name == "Knockout Placeholder":
        raise HTTPException(status_code=400, detail=f"Time 2 '{payload.team2_name}' inválido ou é placeholder.")

    old_val = {
        "team1_name": match.team1_name,
        "team2_name": match.team2_name,
    }
    
    match.team1_name = t1.name
    match.team2_name = t2.name
    db.flush()
    
    audit = AuditLog(
        user_id=current_user.id,
        action="match_fixture_manual_update",
        target_type="match",
        target_id=str(match.id),
        old_value=old_val,
        new_value={
            "team1_name": match.team1_name,
            "team2_name": match.team2_name,
        },
        reason="Confronto definido manualmente pelo administrador"
    )
    db.add(audit)
    db.commit()
    
    invalidate_ranking_cache(db)
    
    return {"message": "Times definidos com sucesso.", "team1_name": match.team1_name, "team2_name": match.team2_name}


@router.get("/football-data/logs", response_model=List[FootballDataSyncLogResponse])
def get_football_data_sync_logs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    return db.query(FootballDataSyncLog).order_by(FootballDataSyncLog.started_at.desc()).limit(limit).all()

# ==========================================
# 2. Openfootball Integration
# ==========================================

@router.post("/sync/seed")
def trigger_initial_seed(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    results = seed_initial_data(db)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="sync_seed_trigger",
        target_type="sync",
        new_value=results
    )
    db.add(audit)
    db.commit()
    
    if results["errors"]:
        raise HTTPException(status_code=500, detail={"msg": "Semente de dados concluída com erros.", "results": results})
        
    return {"message": "Importação inicial realizada com sucesso.", "results": results}

@router.post("/sync/job")
def trigger_sync_job(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    msg, requires_review, results = sync_openfootball_data(db, force_sync=True)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="sync_job_trigger",
        target_type="sync",
        new_value={"message": msg, "requires_review": requires_review, "results": results}
    )
    db.add(audit)
    db.commit()
    
    return {"message": msg, "requires_review": requires_review, "results": results}

@router.get("/sync/diffs", response_model=List[SyncMatchDiffResponse])
def get_pending_sync_diffs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    return db.query(SyncMatchDiff).filter(SyncMatchDiff.status == "pending_review").all()


@router.get("/notifications/summary")
def get_admin_notifications_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    pending_sync_diffs = db.query(SyncMatchDiff).filter(
        SyncMatchDiff.status == "pending_review"
    ).count()
    pending_score_reviews = db.query(Match).filter(
        Match.status == "score_pending_review"
    ).count()
    pending_payment_approvals = db.query(User).filter(
        User.payment_status == "submitted"
    ).count()

    total = pending_sync_diffs + pending_score_reviews + pending_payment_approvals
    return {
        "total": total,
        "pending_sync_diffs": pending_sync_diffs,
        "pending_score_reviews": pending_score_reviews,
        "pending_payment_approvals": pending_payment_approvals,
    }

@router.post("/sync/diffs/{diff_id}/apply")
def apply_sync_diff(
    diff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    diff = db.query(SyncMatchDiff).filter(SyncMatchDiff.id == diff_id, SyncMatchDiff.status == "pending_review").first()
    if not diff:
        raise HTTPException(status_code=404, detail="Diferença pendente não encontrada.")
        
    match = db.query(Match).filter(Match.id == diff.match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida associada não encontrada.")
        
    # Apply new values
    nv = diff.new_value
    match.team1_name = nv["team1_name"]
    match.team2_name = nv["team2_name"]
    match.ground = nv["ground"]
    match.kickoff_time = datetime.fromisoformat(nv["kickoff_time"])
    match.score_ft_team1 = nv["score_ft_team1"]
    match.score_ft_team2 = nv["score_ft_team2"]
    match.score_et_team1 = nv["score_et_team1"]
    match.score_et_team2 = nv["score_et_team2"]
    match.score_pen_team1 = nv["score_pen_team1"]
    match.score_pen_team2 = nv["score_pen_team2"]
    match.status = nv["status"]
    
    diff.status = "applied"
    
    # Log audit
    audit = AuditLog(
        user_id=current_user.id,
        action="sync_diff_apply",
        target_type="match",
        target_id=str(match.id),
        old_value=diff.previous_value,
        new_value=diff.new_value,
        reason=f"Aprovado manualmente pelo Score Admin"
    )
    db.add(audit)
    db.commit()
    
    # Recalculate
    recalculate_match_predictions(db, match.id)
    
    return {"message": "Diferença aplicada e placares recalculados com sucesso."}

@router.post("/sync/diffs/{diff_id}/reject")
def reject_sync_diff(
    diff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    diff = db.query(SyncMatchDiff).filter(SyncMatchDiff.id == diff_id, SyncMatchDiff.status == "pending_review").first()
    if not diff:
        raise HTTPException(status_code=404, detail="Diferença pendente não encontrada.")
        
    diff.status = "rejected"
    
    audit = AuditLog(
        user_id=current_user.id,
        action="sync_diff_reject",
        target_type="sync_match_diff",
        target_id=str(diff_id),
        reason=f"Rejeitado manualmente pelo Score Admin"
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Alteração da sincronização rejeitada com sucesso."}

# ==========================================
# 3. Scoring Configuration (System Admin Only)
# ==========================================

@router.get("/settings/prediction-lock-hours")
def get_prediction_lock_setting(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    return {
        "hours": get_prediction_lock_hours(db),
        "max_hours": MAX_PREDICTION_LOCK_HOURS
    }

@router.put("/settings/prediction-lock-hours")
def update_prediction_lock_setting(
    hours: int = Query(..., ge=0, le=MAX_PREDICTION_LOCK_HOURS),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    old_hours = get_prediction_lock_hours(db)
    setting = set_prediction_lock_hours(db, hours)

    audit = AuditLog(
        user_id=current_user.id,
        action="prediction_lock_hours_change",
        target_type="system_setting",
        target_id=setting.key,
        old_value={"hours": old_hours},
        new_value={"hours": hours}
    )
    db.add(audit)
    db.commit()
    db.refresh(setting)
    invalidate_ranking_cache(db)

    return {
        "hours": hours,
        "max_hours": MAX_PREDICTION_LOCK_HOURS,
        "updated_at": setting.updated_at
    }

@router.get("/multipliers", response_model=List[StageMultiplierResponse])
def get_multipliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    # Ensure all stages are present in the table, otherwise return default or preseed
    stages = list(DEFAULT_MULTIPLIERS.keys())
    response_list = []
    for s in stages:
        m = db.query(StageMultiplier).filter(StageMultiplier.stage == s).first()
        if not m:
            # Create transient schema response
            response_list.append(StageMultiplierResponse(
                stage=s,
                multiplier=DEFAULT_MULTIPLIERS[s],
                updated_at=datetime.utcnow()
            ))
        else:
            response_list.append(m)
    return response_list

@router.put("/multipliers/{stage}", response_model=StageMultiplierResponse)
def update_stage_multiplier(
    stage: str,
    mult_update: StageMultiplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    if stage not in DEFAULT_MULTIPLIERS:
        raise HTTPException(status_code=400, detail="Fase do torneio inválida.")
        
    existing = db.query(StageMultiplier).filter(StageMultiplier.stage == stage).first()
    old_val = DEFAULT_MULTIPLIERS[stage]
    
    if existing:
        old_val = float(existing.multiplier)
        existing.multiplier = mult_update.multiplier
        existing.updated_at = datetime.utcnow()
        existing.updated_by_id = current_user.id
    else:
        existing = StageMultiplier(
            stage=stage,
            multiplier=mult_update.multiplier,
            updated_by_id=current_user.id
        )
        db.add(existing)
        
    # Log to history
    history = MultiplierHistory(
        stage=stage,
        old_multiplier=old_val,
        new_multiplier=mult_update.multiplier,
        updated_by_id=current_user.id,
        reason=mult_update.reason
    )
    db.add(history)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="multiplier_change",
        target_type="stage_multiplier",
        target_id=stage,
        old_value={"multiplier": old_val},
        new_value={"multiplier": mult_update.multiplier},
        reason=mult_update.reason
    )
    db.add(audit)
    db.commit()
    db.refresh(existing)
    
    # Automatic prediction and ranking recalculation is triggered immediately
    recalculate_all_predictions_and_rankings(db)
    capture_ranking_snapshot(db)
    
    return existing

@router.get("/multipliers/history", response_model=List[MultiplierHistoryResponse])
def get_multipliers_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    return db.query(MultiplierHistory).order_by(MultiplierHistory.timestamp.desc()).all()

@router.post("/recalculate-all")
def trigger_recalculate_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_score_admin)
):
    recalculate_all_predictions_and_rankings(db)
    capture_ranking_snapshot(db)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="recalculate_all_trigger",
        target_type="predictions"
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Recálculo completo de todas as apostas e rankings executado com sucesso."}

# ==========================================
# 4. Announcements Management (System Admin Only)
# ==========================================

@router.post("/announcements", response_model=AnnouncementResponse)
def create_announcement(
    ann_in: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    if ann_in.target_type == "group":
        if not ann_in.target_group_id:
            raise HTTPException(status_code=400, detail="Grupo de destino é obrigatório para comunicados de grupo.")
        group = db.query(Group).filter(Group.id == ann_in.target_group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Grupo de destino não encontrado.")
    elif ann_in.target_group_id:
        raise HTTPException(status_code=400, detail="Comunicados globais não devem informar grupo de destino.")

    new_ann = Announcement(
        title=ann_in.title,
        body=ann_in.body,
        priority=ann_in.priority,
        target_type=ann_in.target_type,
        target_group_id=ann_in.target_group_id,
        expiration_date=ann_in.expiration_date
    )
    db.add(new_ann)
    db.commit()
    db.refresh(new_ann)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="announcement_create",
        target_type="announcement",
        target_id=str(new_ann.id),
        new_value={"title": new_ann.title, "priority": new_ann.priority, "target": new_ann.target_type}
    )
    db.add(audit)
    db.commit()
    
    return new_ann

# ==========================================
# 5. User Management (System Admin Only)
# ==========================================

@router.get("/users", response_model=List[UserResponse])
def list_users(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    query = db.query(User)
    if search:
        query = query.filter(
            (User.username.ilike(f"%{search}%")) |
            (User.display_name.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%"))
        )
    return sorted(query.all(), key=user_name_sort_key)

@router.post("/users/{user_id}/role", response_model=UserResponse)
def change_user_role(
    user_id: UUID,
    role: str = Query(..., enum=["participant", "group_admin", "score_admin", "system_admin"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode alterar sua própria função administrativa.")
        
    old_role = user.role
    user.role = role
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="user_role_change",
        target_type="user",
        target_id=str(user_id),
        old_value={"role": old_role},
        new_value={"role": role}
    )
    db.add(audit)
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/users/{user_id}/status", response_model=UserResponse)
def change_user_status(
    user_id: UUID,
    active: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode desativar seu próprio acesso.")
        
    old_val = user.is_active
    user.is_active = active
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="user_status_change",
        target_type="user",
        target_id=str(user_id),
        old_value={"is_active": old_val},
        new_value={"is_active": active}
    )
    db.add(audit)
    db.commit()
    db.refresh(user)
    
    return user

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode remover seu próprio usuário.")

    owned_groups_count = db.query(Group).filter(Group.owner_id == user_id).count()
    if owned_groups_count:
        raise HTTPException(
            status_code=400,
            detail="Este usuário é proprietário de grupo(s). Transfira ou remova os grupos antes de excluir o usuário."
        )

    proof_filename = user.payment_proof_filename
    audit = AuditLog(
        user_id=current_user.id,
        action="user_delete",
        target_type="user",
        target_id=str(user.id),
        old_value={
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role
        }
    )
    db.add(audit)

    db.query(AuditLog).filter(AuditLog.user_id == user_id).update({"user_id": None})
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete(synchronize_session=False)
    db.query(GroupInvitation).filter(GroupInvitation.invited_by_id == user_id).delete(synchronize_session=False)
    db.query(GroupInvitation).filter(GroupInvitation.invitee_id == user_id).delete(synchronize_session=False)
    db.query(SystemInvitation).filter(SystemInvitation.used_by_id == user_id).update({"used_by_id": None})

    db.delete(user)
    db.commit()
    invalidate_ranking_cache(db)

    if proof_filename:
        proof_path = os.path.join("/app/uploads", proof_filename)
        try:
            if os.path.exists(proof_path):
                os.remove(proof_path)
        except OSError:
            pass

# ==========================================
# 6. Audit Logs (System Admin Only)
# ==========================================

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    user_id: Optional[UUID] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
        
    return query.order_by(AuditLog.timestamp.desc()).all()

# ==========================================
# 7. CSV Exports (System Admin Only)
# ==========================================

@router.get("/export/users")
def export_users_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    users = db.query(User).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Username", "Email", "Nome Exibido", "Funcao", "Ativo", "Data Cadastro"])
    
    for u in users:
        writer.writerow([
            sanitize_csv_value(str(u.id)),
            sanitize_csv_value(u.username),
            sanitize_csv_value(u.email),
            sanitize_csv_value(u.display_name),
            sanitize_csv_value(u.role),
            sanitize_csv_value(u.is_active),
            sanitize_csv_value(u.created_at.isoformat())
        ])
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=usuarios_export.csv"
    return response

@router.get("/export/predictions")
def export_predictions_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    predictions = db.query(Prediction).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID Aposta", "ID Partida", "Rodada", "Selecoes", "ID Usuario", "Usuario", "Palpite", "Pontos Ganhos", "Base", "Multiplicador"])
    
    for p in predictions:
        match = p.match
        user = p.user
        writer.writerow([
            sanitize_csv_value(p.id),
            sanitize_csv_value(p.match_id),
            sanitize_csv_value(match.round),
            sanitize_csv_value(f"{match.team1_name} x {match.team2_name}"),
            sanitize_csv_value(str(p.user_id)),
            sanitize_csv_value(user.display_name),
            sanitize_csv_value(f"{p.goals_team1} x {p.goals_team2}"),
            sanitize_csv_value(p.points_earned if p.points_earned is not None else "-"),
            sanitize_csv_value(p.base_points if p.base_points is not None else "-"),
            sanitize_csv_value(p.multiplier_used if p.multiplier_used is not None else "-")
        ])
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=apostas_export.csv"
    return response

@router.get("/export/scores")
def export_scores_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    matches = db.query(Match).filter(Match.status.in_(["finished", "score_confirmed"])).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID Partida", "Rodada", "Fase", "Mandante", "Placar Mandante", "Placar Visitante", "Visitante", "Extra Mandante", "Extra Visitante", "Penaltis Mandante", "Penaltis Visitante", "Status", "Confirmado por Admin"])
    
    for m in matches:
        writer.writerow([
            sanitize_csv_value(m.id),
            sanitize_csv_value(m.round),
            sanitize_csv_value(m.stage),
            sanitize_csv_value(m.team1_name),
            sanitize_csv_value(m.score_ft_team1),
            sanitize_csv_value(m.score_ft_team2),
            sanitize_csv_value(m.team2_name),
            sanitize_csv_value(m.score_et_team1 if m.score_et_team1 is not None else ""),
            sanitize_csv_value(m.score_et_team2 if m.score_et_team2 is not None else ""),
            sanitize_csv_value(m.score_pen_team1 if m.score_pen_team1 is not None else ""),
            sanitize_csv_value(m.score_pen_team2 if m.score_pen_team2 is not None else ""),
            sanitize_csv_value(m.status),
            sanitize_csv_value(m.score_confirmed_by_admin)
        ])
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=placares_export.csv"
    return response

@router.get("/export/audit-logs")
def export_audit_logs_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID Log", "Data Hora", "ID Usuario", "Usuario", "Acao", "Tipo Alvo", "ID Alvo", "Motivo"])
    
    for l in logs:
        user_name = l.user.display_name if l.user else "Sistema/Anonimo"
        writer.writerow([
            sanitize_csv_value(l.id),
            sanitize_csv_value(l.timestamp.isoformat()),
            sanitize_csv_value(str(l.user_id) if l.user_id else ""),
            sanitize_csv_value(user_name),
            sanitize_csv_value(l.action),
            sanitize_csv_value(l.target_type),
            sanitize_csv_value(l.target_id or ""),
            sanitize_csv_value(l.reason or "")
        ])
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=auditoria_export.csv"
    return response


# ==========================================
# 8. Invitation Management (System Admin Only)
# ==========================================

def get_invitation_link(code: str) -> str:
    import os

    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base_url}/register?code={code}"


def send_invitation_email(email: str, code: str) -> bool:
    import os
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import logging
    
    logger = logging.getLogger("bolao_invitation")
    
    smtp_host = os.getenv("SMTP_HOST", "172.25.0.1")
    smtp_port = int(os.getenv("SMTP_PORT", "25"))
    from_domain = os.getenv("FROM_DOMAIN", "bru.to")
    
    sender_email = os.getenv("SMTP_FROM", f"no-reply@{from_domain}")
    recipient_email = email
    
    message = MIMEMultipart("alternative")
    message["Subject"] = "Convite para o Bolão Copa do Mundo 2026"
    message["From"] = sender_email
    message["To"] = recipient_email
    
    register_link = get_invitation_link(code)
    
    text = f"Olá!\n\nVocê foi convidado para participar do Bolão Copa 2026.\nSeu cadastro deve ser feito pelo link único abaixo:\n\n{register_link}\n\nEste convite é pessoal e vinculado ao seu e-mail.\n\nBoa sorte!"
    html = f"""\
    <html>
      <body>
        <h2>Você foi convidado!</h2>
        <p>Você foi convidado para participar do <strong>Bolão Copa 2026</strong>.</p>
        <p>Use o link único abaixo para concluir seu cadastro. O convite é pessoal e vinculado ao seu e-mail.</p>
        <p><a href="{register_link}" style="background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Cadastrar no Bolão</a></p>
        <p style="font-size: 0.875rem; color: #4b5563;">Se o botão não funcionar, copie e cole este endereço no navegador:<br>{register_link}</p>
        <p>Boa sorte!</p>
      </body>
    </html>
    """
    
    message.attach(MIMEText(text, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))
    
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            if os.getenv("SMTP_STARTTLS", "false").lower() == "true":
                server.starttls()
            username = os.getenv("SMTP_USERNAME")
            password = os.getenv("SMTP_PASSWORD")
            if username and password:
                server.login(username, password)
            server.sendmail(sender_email, recipient_email, message.as_string())
        logger.info(f"Convite enviado com sucesso para {email}")
        return True
    except Exception as e:
        logger.error(f"Falha ao enviar e-mail de convite para {email}: {str(e)}")
        return False

@router.post("/invitations", response_model=SystemInvitationResponse)
def create_system_invitation(
    invite_in: SystemInvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    import secrets
    
    # Check if this email is already registered
    existing_user = db.query(User).filter(User.email == invite_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este e-mail já está cadastrado no sistema."
        )
        
    # Check if there is already a pending invite for this email
    existing_invite = db.query(SystemInvitation).filter(
        SystemInvitation.email == invite_in.email
    ).first()
    
    if existing_invite:
        if existing_invite.is_used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Um convite para este e-mail já foi utilizado."
            )
        existing_invite.code = secrets.token_hex(8).upper()
        existing_invite.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing_invite)
        
        send_invitation_email(existing_invite.email, existing_invite.code)
        
        audit = AuditLog(
            user_id=current_user.id,
            action="invitation_resend",
            target_type="invitation",
            target_id=str(existing_invite.id),
            new_value={"email": existing_invite.email}
        )
        db.add(audit)
        db.commit()
        
        return existing_invite

    invite_code = secrets.token_hex(8).upper()
    new_invite = SystemInvitation(
        email=invite_in.email,
        code=invite_code,
        is_used=False
    )
    db.add(new_invite)
    db.commit()
    db.refresh(new_invite)
    
    send_invitation_email(new_invite.email, new_invite.code)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="invitation_create",
        target_type="invitation",
        target_id=str(new_invite.id),
        new_value={"email": new_invite.email}
    )
    db.add(audit)
    db.commit()
    
    return new_invite

@router.get("/invitations", response_model=List[SystemInvitationResponse])
def list_system_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    return db.query(SystemInvitation).order_by(SystemInvitation.created_at.desc()).all()

@router.get("/registration-link")
def get_hidden_registration_link(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    setting = get_or_create_hidden_registration_setting(db)
    return {
        "code": setting.value,
        "path": f"/register?access={setting.value}",
        "updated_at": setting.updated_at
    }

@router.post("/registration-link/rotate")
def rotate_hidden_registration_link(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    setting = get_or_create_hidden_registration_setting(db)
    old_code = setting.value
    setting.value = secrets.token_urlsafe(32)
    setting.updated_at = datetime.utcnow()

    audit = AuditLog(
        user_id=current_user.id,
        action="hidden_registration_link_rotate",
        target_type="system_setting",
        target_id="hidden_registration_code",
        old_value={"code_prefix": old_code[:8]},
        new_value={"code_prefix": setting.value[:8]}
    )
    db.add(audit)
    db.commit()
    db.refresh(setting)

    return {
        "code": setting.value,
        "path": f"/register?access={setting.value}",
        "updated_at": setting.updated_at
    }

@router.post("/invitations/{invitation_id}/resend", response_model=SystemInvitationResponse)
def resend_system_invitation(
    invitation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    invitation = db.query(SystemInvitation).filter(SystemInvitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")
    if invitation.is_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Convites já utilizados não podem ser reenviados.")

    sent = send_invitation_email(invitation.email, invitation.code)
    if not sent:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Não foi possível enviar o e-mail do convite.")

    audit = AuditLog(
        user_id=current_user.id,
        action="invitation_resend",
        target_type="invitation",
        target_id=str(invitation.id),
        new_value={"email": invitation.email}
    )
    db.add(audit)
    db.commit()
    db.refresh(invitation)
    return invitation

@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system_invitation(
    invitation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    invitation = db.query(SystemInvitation).filter(SystemInvitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")

    audit = AuditLog(
        user_id=current_user.id,
        action="invitation_delete",
        target_type="invitation",
        target_id=str(invitation.id),
        old_value={"email": invitation.email, "is_used": invitation.is_used}
    )
    db.add(audit)
    db.delete(invitation)
    db.commit()
