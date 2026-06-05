from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from zoneinfo import ZoneInfo
from ..db import get_db
from ..scoring import get_rankings
from ..schemas import RankingRowResponse
from ..auth import get_current_active_user
from ..models import Group, GroupMember, RankingSnapshot

router = APIRouter(prefix="/api/rankings", tags=["Rankings"])
LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")

@router.get("/general", response_model=List[RankingRowResponse])
def get_general_ranking(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return get_rankings(db)

@router.get("/group/{group_id}", response_model=List[RankingRowResponse])
def get_group_ranking(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    # Security check: If private group, user must be a member
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    if group.is_private:
        membership = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
            GroupMember.is_approved == True
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Acesso negado: Este é um grupo privado.")
            
    return get_rankings(db, group_id=group_id)

@router.get("/stage", response_model=List[RankingRowResponse])
def get_stage_ranking(
    stage: str = Query(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return get_rankings(db, stage=stage)

@router.get("/date", response_model=List[RankingRowResponse])
def get_date_ranking(
    date: str = Query(...), # Format: YYYY-MM-DD
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return get_rankings(db, date_str=date)

@router.get("/history")
def get_ranking_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    rows = db.query(RankingSnapshot).order_by(
        RankingSnapshot.snapshot_date.asc(),
        RankingSnapshot.position.asc(),
        RankingSnapshot.display_name.asc()
    ).all()

    current_ranking = get_rankings(db)
    today = datetime.now(LOCAL_TIMEZONE).date()
    has_today_snapshot = any(row.snapshot_date == today for row in rows)
    if not has_today_snapshot:
        for row in current_ranking:
            rows.append(type("CurrentSnapshot", (), {
                "snapshot_date": today,
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "avatar_url": row["avatar_url"],
                "position": row["position"],
                "total_points": row["total_points"],
                "exact_scores_count": row["exact_scores_count"],
                "correct_results_count": row["correct_results_count"],
            })())

    dates = sorted({row.snapshot_date for row in rows})
    current_top_ids = {str(row["user_id"]) for row in current_ranking[:5]}
    current_user_id = str(current_user.id)
    participants: dict[str, dict] = {}

    for row in rows:
        user_id = str(row.user_id)
        if user_id not in participants:
            participants[user_id] = {
                "user_id": user_id,
                "display_name": row.display_name,
                "avatar_url": row.avatar_url,
                "is_default_visible": user_id == current_user_id or user_id in current_top_ids,
                "snapshots": []
            }
        participants[user_id]["snapshots"].append({
            "date": row.snapshot_date.isoformat(),
            "position": row.position,
            "total_points": row.total_points,
            "exact_scores_count": row.exact_scores_count,
            "correct_results_count": row.correct_results_count,
        })

    def latest_position(participant: dict) -> int:
        if not participant["snapshots"]:
            return 999999
        return participant["snapshots"][-1]["position"]

    ordered_participants = sorted(
        participants.values(),
        key=lambda item: (latest_position(item), item["display_name"].lower())
    )
    return {
        "dates": [date.isoformat() for date in dates],
        "participants": ordered_participants,
    }

@router.get("/me")
def get_my_ranking_positions(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Returns the user's positions in the general ranking and in all groups they belong to.
    """
    general = get_rankings(db)
    my_general = next((row for row in general if row["user_id"] == current_user.id), None)
    
    # Get user memberships
    memberships = db.query(GroupMember).filter(
        GroupMember.user_id == current_user.id,
        GroupMember.is_approved == True
    ).all()
    
    group_positions = []
    for mem in memberships:
        group_ranking = get_rankings(db, group_id=mem.group_id)
        my_group_row = next((row for row in group_ranking if row["user_id"] == current_user.id), None)
        if my_group_row:
            group_positions.append({
                "group_id": mem.group_id,
                "group_name": mem.group.name,
                "position": my_group_row["position"],
                "total_points": my_group_row["total_points"]
            })
            
    return {
        "general": {
            "position": my_general["position"] if my_general else None,
            "total_points": my_general["total_points"] if my_general else 0,
            "exact_scores_count": my_general["exact_scores_count"] if my_general else 0,
            "correct_results_count": my_general["correct_results_count"] if my_general else 0,
            "predictions_count": my_general["predictions_count"] if my_general else 0,
            "missing_predictions_count": my_general["missing_predictions_count"] if my_general else 0,
        },
        "groups": group_positions
    }
