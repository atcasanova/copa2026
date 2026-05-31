from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import io
import csv
import secrets
from fastapi.responses import StreamingResponse

from ..db import get_db
from ..models import User, Match, Prediction, StageMultiplier, MultiplierHistory, Announcement, AuditLog, SyncLog, SyncMatchDiff, Team, Stadium, SystemInvitation, SystemSetting, Group
from ..schemas import (
    MatchResponse, StageMultiplierResponse, StageMultiplierUpdate, MultiplierHistoryResponse,
    AnnouncementCreate, AnnouncementResponse, UserResponse, AuditLogResponse, SyncLogResponse, SyncMatchDiffResponse,
    SystemInvitationCreate, SystemInvitationResponse
)
from ..auth import require_system_admin, require_score_admin, require_participant
from ..scoring import recalculate_match_predictions, recalculate_all_predictions_and_rankings, get_rankings, DEFAULT_MULTIPLIERS, invalidate_ranking_cache
from ..sync import seed_initial_data, sync_openfootball_data
from ..settings import get_prediction_lock_hours, set_prediction_lock_hours, MAX_PREDICTION_LOCK_HOURS

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

    old_val = {
        "score_ft_team1": match.score_ft_team1, "score_ft_team2": match.score_ft_team2,
        "score_et_team1": match.score_et_team1, "score_et_team2": match.score_et_team2,
        "score_pen_team1": match.score_pen_team1, "score_pen_team2": match.score_pen_team2,
        "status": match.status
    }

    match.score_ft_team1 = score_ft_team1
    match.score_ft_team2 = score_ft_team2
    match.score_et_team1 = score_et_team1
    match.score_et_team2 = score_et_team2
    match.score_pen_team1 = score_pen_team1
    match.score_pen_team2 = score_pen_team2
    
    # Set status to pending review or finished
    match.status = "score_pending_review"

    db.commit()
    db.refresh(match)

    new_val = {
        "score_ft_team1": match.score_ft_team1, "score_ft_team2": match.score_ft_team2,
        "score_et_team1": match.score_et_team1, "score_et_team2": match.score_et_team2,
        "score_pen_team1": match.score_pen_team1, "score_pen_team2": match.score_pen_team2,
        "status": match.status
    }

    # Log action
    audit = AuditLog(
        user_id=current_user.id,
        action="match_score_insert",
        target_type="match",
        target_id=str(match.id),
        old_value=old_val,
        new_value=new_val
    )
    db.add(audit)
    db.commit()

    # Recalculate predictions
    recalculate_match_predictions(db, match.id)

    return match

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

    return match

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
    return query.order_by(User.username.asc()).all()

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

@router.get("/export/ranking")
def export_general_ranking_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_system_admin)
):
    ranking = get_rankings(db)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Posicao", "Participante", "ID Usuario", "Pontos Totais", "Placares Exatos", "Resultados Corretos", "Palpites Feitos", "Palpites Faltantes"])
    
    for r in ranking:
        writer.writerow([
            sanitize_csv_value(r["position"]),
            sanitize_csv_value(r["display_name"]),
            sanitize_csv_value(str(r["user_id"])),
            sanitize_csv_value(r["total_points"]),
            sanitize_csv_value(r["exact_scores_count"]),
            sanitize_csv_value(r["correct_results_count"]),
            sanitize_csv_value(r["predictions_count"]),
            sanitize_csv_value(r["missing_predictions_count"])
        ])
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=ranking_geral_export.csv"
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
