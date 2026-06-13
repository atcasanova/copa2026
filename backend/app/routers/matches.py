from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from ..db import get_db
from ..models import Match
from ..schemas import MatchResponse
from ..auth import get_current_active_user

router = APIRouter(prefix="/api/matches", tags=["Matches"])

def list_matches(
    date: Optional[str] = None,
    stage: Optional[str] = None,
    group_name: Optional[str] = None,
    team: Optional[str] = None,
    ground: Optional[str] = None,
    status: Optional[str] = None,
    missing_score: bool = False,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    query = db.query(Match)
    
    # Filter by unlocked stages or defined matchups for standard users
    if current_user.role not in ["system_admin", "score_admin"]:
        from .utils import get_unlocked_stages
        from ..models import Team
        from sqlalchemy import or_
        from sqlalchemy.orm import aliased
        
        unlocked = get_unlocked_stages(db)
        t1 = aliased(Team)
        t2 = aliased(Team)
        query = query.join(t1, Match.team1_name == t1.name).join(t2, Match.team2_name == t2.name)
        query = query.filter(
            or_(
                Match.stage.in_(unlocked),
                (t1.group_name != "Knockout Placeholder") & (t2.group_name != "Knockout Placeholder")
            )
        )
        
    if date:
        query = query.filter(Match.date == date)
    if stage:
        query = query.filter(Match.stage == stage)
    if group_name:
        query = query.filter(Match.group_name == group_name)
    if ground:
        query = query.filter(Match.ground == ground)
    if status:
        query = query.filter(Match.status == status)
    if missing_score:
        query = query.filter(Match.score_ft_team1 == None, Match.score_ft_team2 == None)
    if team:
        query = query.filter(or_(Match.team1_name == team, Match.team2_name == team))
        
    # Sort matches by kickoff time
    query = query.order_by(Match.kickoff_time.asc())
    if limit is not None:
        query = query.limit(limit)
    return query.all()

@router.get("", response_model=List[MatchResponse], include_in_schema=False)
def get_matches_without_trailing_slash(
    date: Optional[str] = None,
    stage: Optional[str] = None,
    group_name: Optional[str] = None,
    team: Optional[str] = None,
    ground: Optional[str] = None,
    status: Optional[str] = None,
    missing_score: bool = False,
    limit: Optional[int] = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return list_matches(date, stage, group_name, team, ground, status, missing_score, limit, db, current_user)

@router.get("/", response_model=List[MatchResponse])
def get_matches(
    date: Optional[str] = None,
    stage: Optional[str] = None,
    group_name: Optional[str] = None,
    team: Optional[str] = None,
    ground: Optional[str] = None,
    status: Optional[str] = None,
    missing_score: bool = False,
    limit: Optional[int] = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return list_matches(date, stage, group_name, team, ground, status, missing_score, limit, db, current_user)

@router.get("/broadcasts")
def get_broadcasts(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    from ..broadcasters import get_match_broadcasters
    return get_match_broadcasters(db)

@router.get("/{match_id}", response_model=MatchResponse)
def get_match_detail(
    match_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")
    return match
