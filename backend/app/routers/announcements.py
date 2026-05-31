from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from datetime import datetime
from ..db import get_db
from ..models import Announcement, AnnouncementRead, GroupMember, User
from ..schemas import AnnouncementResponse
from ..auth import get_current_active_user

router = APIRouter(prefix="/api/announcements", tags=["Announcements"])

@router.get("/", response_model=List[AnnouncementResponse])
def get_announcements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all active (published and not expired) announcements targeting:
    1. Global audience.
    2. Groups where user is a member.
    """
    now = datetime.utcnow()
    
    # Subquery groups user belongs to
    my_group_ids = [m.group_id for m in db.query(GroupMember.group_id).filter(
        GroupMember.user_id == current_user.id,
        GroupMember.is_approved == True
    ).all()]
    
    # Query announcements
    query = db.query(Announcement).filter(
        Announcement.publication_date <= now,
        (Announcement.expiration_date == None) | (Announcement.expiration_date > now)
    )
    
    # Apply targets filter
    query = query.filter(
        (Announcement.target_type == "global") |
        ((Announcement.target_type == "group") & (Announcement.target_group_id.in_(my_group_ids)))
    )
    
    announcements = query.order_by(Announcement.publication_date.desc()).all()
    
    # Fetch read IDs
    read_announcement_ids = [r.announcement_id for r in db.query(AnnouncementRead.announcement_id).filter(
        AnnouncementRead.user_id == current_user.id
    ).all()]
    
    response_data = []
    for ann in announcements:
        # Create schema compatible object or dict
        item = AnnouncementResponse.model_validate(ann)
        item.is_read = ann.id in read_announcement_ids
        response_data.append(item)
        
    return response_data

@router.post("/{announcement_id}/read", status_code=status.HTTP_200_OK)
def mark_as_read(
    announcement_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Comunicado não encontrado.")
        
    # Check if already marked as read
    existing = db.query(AnnouncementRead).filter(
        AnnouncementRead.announcement_id == announcement_id,
        AnnouncementRead.user_id == current_user.id
    ).first()
    
    if not existing:
        read_record = AnnouncementRead(
            announcement_id=announcement_id,
            user_id=current_user.id,
            read_at=datetime.utcnow()
        )
        db.add(read_record)
        db.commit()
        
    return {"message": "Comunicado marcado como lido."}
