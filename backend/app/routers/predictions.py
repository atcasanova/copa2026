from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from collections import Counter
from ..db import get_db
from ..models import Prediction, Match, User, AuditLog
from ..schemas import PredictionCreate, PredictionResponse, PredictionBulkUpdate, MatchResponse, MatchPredictionVisibilityResponse
from ..auth import get_current_active_user
from ..settings import get_prediction_lock_hours, get_locked_match_cutoff, is_match_locked_for_predictions
from ..scoring import DEFAULT_MULTIPLIERS, get_stage_multiplier
from uuid import UUID

router = APIRouter(prefix="/api/predictions", tags=["Predictions"])

def check_match_locked(db: Session, match: Match) -> bool:
    """
    Returns True if match is inside the configured prediction lock window.
    """
    return is_match_locked_for_predictions(db, match)

@router.get("/settings")
def get_prediction_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return {
        "prediction_lock_hours": get_prediction_lock_hours(db),
        "multipliers": [
            {
                "stage": stage,
                "multiplier": float(get_stage_multiplier(db, stage))
            }
            for stage in DEFAULT_MULTIPLIERS.keys()
        ]
    }

@router.get("/my-predictions", response_model=List[PredictionResponse])
def get_my_predictions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Returns all predictions for the currently authenticated user.
    """
    query = db.query(Prediction).filter(Prediction.user_id == current_user.id)
    if current_user.role not in ["system_admin", "score_admin"]:
        from .utils import get_unlocked_stages
        unlocked = get_unlocked_stages(db)
        query = query.join(Match).filter(Match.stage.in_(unlocked))
    return query.all()

@router.post("/save", response_model=PredictionResponse)
def save_prediction(
    match_id: int,
    pred_in: PredictionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Save or update a single prediction.
    """
    if current_user.role in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administradores não participam do bolão e não podem fazer palpites."
        )
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    # Enforce payment validation
    if current_user.role not in ["system_admin", "score_admin"]:
        if current_user.payment_status != "approved":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você precisa ter o seu pagamento aprovado para realizar palpites."
            )

    # Enforce stage unlocking validation
    if current_user.role not in ["system_admin", "score_admin"]:
        from .utils import get_unlocked_stages
        unlocked = get_unlocked_stages(db)
        if match.stage not in unlocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Fase do torneio ainda bloqueada para palpites."
            )

    # Enforce lock validation
    if check_match_locked(db, match):
        lock_hours = get_prediction_lock_hours(db)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aposta bloqueada: apostas devem ser feitas até {lock_hours} hora(s) antes do início da partida."
        )

    # Check if prediction already exists
    prediction = db.query(Prediction).filter(
        Prediction.match_id == match_id,
        Prediction.user_id == current_user.id
    ).first()

    old_val = None
    if prediction:
        old_val = {"goals_team1": prediction.goals_team1, "goals_team2": prediction.goals_team2, "qualified_team_name": prediction.qualified_team_name}
        prediction.goals_team1 = pred_in.goals_team1
        prediction.goals_team2 = pred_in.goals_team2
        prediction.qualified_team_name = pred_in.qualified_team_name
        action = "prediction_edit"
    else:
        prediction = Prediction(
            match_id=match_id,
            user_id=current_user.id,
            goals_team1=pred_in.goals_team1,
            goals_team2=pred_in.goals_team2,
            qualified_team_name=pred_in.qualified_team_name
        )
        db.add(prediction)
        action = "prediction_create"

    db.commit()
    db.refresh(prediction)

    # Log action
    new_val = {"goals_team1": prediction.goals_team1, "goals_team2": prediction.goals_team2, "qualified_team_name": prediction.qualified_team_name}
    audit = AuditLog(
        user_id=current_user.id,
        action=action,
        target_type="prediction",
        target_id=str(prediction.id),
        old_value=old_val,
        new_value=new_val
    )
    db.add(audit)
    db.commit()

    return prediction

@router.post("/bulk-save", response_model=List[PredictionResponse])
def bulk_save_predictions(
    predictions_in: List[PredictionBulkUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Save or update multiple predictions at once. Used in compact table view.
    Enforces locking rule per match.
    """
    if current_user.role in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administradores não participam do bolão e não podem fazer palpites."
        )
    saved_predictions = []
    
    for item in predictions_in:
        match = db.query(Match).filter(Match.id == item.match_id).first()
        if not match:
            continue
            
        # Enforce payment validation
        if current_user.role not in ["system_admin", "score_admin"]:
            if current_user.payment_status != "approved":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você precisa ter o seu pagamento aprovado para realizar palpites."
                )

        # Enforce stage unlocking validation
        if current_user.role not in ["system_admin", "score_admin"]:
            from .utils import get_unlocked_stages
            unlocked = get_unlocked_stages(db)
            if match.stage not in unlocked:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Não foi possível salvar: A fase {match.stage} ainda está bloqueada para palpites."
                )

        # Skip locked matches silently in bulk save, or raise error.
        # It's better to raise an error if any is locked to prevent front-end state mismatch,
        # or skip locked ones. Let's raise error for transparency.
        if check_match_locked(db, match):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não foi possível salvar: A partida {match.team1_name} x {match.team2_name} já está bloqueada para palpites."
            )
            
        prediction = db.query(Prediction).filter(
            Prediction.match_id == item.match_id,
            Prediction.user_id == current_user.id
        ).first()
        
        old_val = None
        if prediction:
            old_val = {"goals_team1": prediction.goals_team1, "goals_team2": prediction.goals_team2, "qualified_team_name": prediction.qualified_team_name}
            prediction.goals_team1 = item.goals_team1
            prediction.goals_team2 = item.goals_team2
            prediction.qualified_team_name = item.qualified_team_name
            action = "prediction_edit"
        else:
            prediction = Prediction(
                match_id=item.match_id,
                user_id=current_user.id,
                goals_team1=item.goals_team1,
                goals_team2=item.goals_team2,
                qualified_team_name=item.qualified_team_name
            )
            db.add(prediction)
            action = "prediction_create"
            
        db.commit()
        db.refresh(prediction)
        saved_predictions.append(prediction)
        
        # Log action
        new_val = {"goals_team1": prediction.goals_team1, "goals_team2": prediction.goals_team2, "qualified_team_name": prediction.qualified_team_name}
        audit = AuditLog(
            user_id=current_user.id,
            action=action,
            target_type="prediction",
            target_id=str(prediction.id),
            old_value=old_val,
            new_value=new_val
        )
        db.add(audit)
        
    db.commit()
    return saved_predictions

@router.get("/missing", response_model=List[MatchResponse])
def get_missing_predictions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get matches that current user has NOT predicted yet and that are NOT locked yet.
    """
    open_threshold = get_locked_match_cutoff(db)
    
    # Matches that are not locked
    open_matches = db.query(Match).filter(Match.kickoff_time > open_threshold).all()
    
    # Subquery of matches user has predicted
    pred_match_ids = [p.match_id for p in db.query(Prediction.match_id).filter(Prediction.user_id == current_user.id).all()]
    
    missing = [m for m in open_matches if m.id not in pred_match_ids]
    return missing

@router.get("/locking-soon", response_model=List[MatchResponse])
def get_matches_locking_soon(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get matches that will lock in the next N hours, where the user has NOT placed a prediction.
    """
    lock_time_start = get_locked_match_cutoff(db)
    lock_time_end = lock_time_start + timedelta(hours=hours)
    
    # Matches locking soon
    soon_matches = db.query(Match).filter(
        Match.kickoff_time > lock_time_start,
        Match.kickoff_time <= lock_time_end
    ).all()
    
    # Subquery of matches user has predicted
    pred_match_ids = [p.match_id for p in db.query(Prediction.match_id).filter(Prediction.user_id == current_user.id).all()]
    
    locking_soon_missing = [m for m in soon_matches if m.id not in pred_match_ids]
    return locking_soon_missing

@router.get("/match/{match_id}/visibility", response_model=MatchPredictionVisibilityResponse)
def get_match_prediction_visibility(
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Before the match lock window, returns only who already predicted.
    After lock, returns the submitted prediction scores.
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    locked = is_match_locked_for_predictions(db, match)
    is_scored = match.score_ft_team1 is not None and match.score_ft_team2 is not None
    total_participants = db.query(User).filter(
        User.is_active == True,
        User.role.notin_(["system_admin", "score_admin"])
    ).count()
    predictions = db.query(Prediction).join(User, User.id == Prediction.user_id).filter(
        Prediction.match_id == match_id,
        User.is_active == True,
        User.role.notin_(["system_admin", "score_admin"])
    ).all()
    predictions.sort(
        key=lambda pred: (
            -(pred.points_earned if is_scored and pred.points_earned is not None else -1),
            pred.user.display_name.lower()
        )
    )

    points_counter = Counter()
    if is_scored:
        points_counter.update(pred.points_earned or 0 for pred in predictions)
    points_summary = [
        {"points": points, "count": count}
        for points, count in sorted(points_counter.items(), key=lambda item: item[0], reverse=True)
    ]

    entries = []
    for pred in predictions:
        entry = {
            "user_id": pred.user_id,
            "display_name": pred.user.display_name,
            "avatar_url": pred.user.avatar_url,
            "created_at": pred.created_at.replace(tzinfo=timezone.utc) if pred.created_at.tzinfo is None else pred.created_at.astimezone(timezone.utc),
            "goals_team1": None,
            "goals_team2": None,
            "qualified_team_name": None,
            "points_earned": None
        }
        if locked:
            entry["goals_team1"] = pred.goals_team1
            entry["goals_team2"] = pred.goals_team2
            entry["qualified_team_name"] = pred.qualified_team_name
        if is_scored:
            entry["points_earned"] = pred.points_earned or 0
        entries.append(entry)

    return {
        "match_id": match.id,
        "is_locked": locked,
        "is_scored": is_scored,
        "total_predictions": len(entries),
        "total_participants": total_participants,
        "points_summary": points_summary,
        "entries": entries
    }

@router.get("/user/{user_id}", response_model=List[PredictionResponse])
def get_predictions_for_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get predictions for another user.
    Security rule: Only show predictions for matches that are already locked by the configured prediction window.
    Predictions for upcoming/unlocked matches are strictly hidden.
    """
    now_utc = datetime.utcnow()
    
    # If checking own predictions, no restrictions
    if user_id == current_user.id:
        return db.query(Prediction).filter(Prediction.user_id == user_id).all()
        
    # Check predictions of other user
    predictions = db.query(Prediction).join(Match, Match.id == Prediction.match_id)\
                                     .filter(Prediction.user_id == user_id).all()
                                     
    filtered_predictions = []
    for pred in predictions:
        if is_match_locked_for_predictions(db, pred.match, now_utc):
            filtered_predictions.append(pred)
            
    return filtered_predictions
