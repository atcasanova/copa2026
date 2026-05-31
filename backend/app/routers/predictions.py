from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from ..db import get_db
from ..models import Prediction, Match, User, AuditLog
from ..schemas import PredictionCreate, PredictionResponse, PredictionBulkUpdate, MatchResponse
from ..auth import get_current_active_user
from ..settings import get_prediction_lock_hours, get_locked_match_cutoff, is_match_locked_for_predictions
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
    return {"prediction_lock_hours": get_prediction_lock_hours(db)}

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
