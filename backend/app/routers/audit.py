from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import json
import hashlib

from ..db import get_db
from ..models import AuditBlock, Match, Prediction
from ..schemas import AuditBlockResponse
from ..auth import get_current_active_user
from ..settings import get_locked_match_cutoff, is_match_locked_for_predictions

router = APIRouter(prefix="/api/audit", tags=["Cryptographic Audit"])

def get_or_create_audit_block(db: Session, match_id: int) -> AuditBlock:
    """
    Get existing audit block or lazily create it by hashing prediction payload + previous block's hash.
    Chaining order is determined by Match.kickoff_time ASC, Match.id ASC.
    """
    # Check if block already exists
    block = db.query(AuditBlock).filter(AuditBlock.match_id == match_id).first()
    if block:
        return block

    # Get match details
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return None

    now_utc = datetime.utcnow()
    if not is_match_locked_for_predictions(db, match, now_utc):
        return None  # Cannot generate block for an active/unlocked match

    # Find previous locked match in the deterministic chain
    prev_match = db.query(Match).filter(
        (Match.kickoff_time < match.kickoff_time) |
        ((Match.kickoff_time == match.kickoff_time) & (Match.id < match.id))
    ).order_by(Match.kickoff_time.desc(), Match.id.desc()).first()

    prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    if prev_match:
        # Recursively ensure previous block is generated to construct the hash chain link
        prev_block = get_or_create_audit_block(db, prev_match.id)
        if prev_block:
            prev_hash = prev_block.hash

    # Fetch predictions for this match and sort them by user_id to ensure determinism
    predictions = db.query(Prediction).filter(Prediction.match_id == match_id).all()
    predictions.sort(key=lambda p: str(p.user_id))

    # Construct the audit payload
    payload = []
    for pred in predictions:
        payload.append({
            "username": pred.user.username,
            "goals_team1": pred.goals_team1,
            "goals_team2": pred.goals_team2
        })

    # Serialize payload deterministically (sort_keys=True and separators=(',',':') matches standard JS JSON.stringify)
    payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)

    # Calculate current block hash: SHA-256(payload_str + previous_hash)
    content_to_hash = payload_str + prev_hash
    block_hash = hashlib.sha256(content_to_hash.encode('utf-8')).hexdigest()

    # Determine sequence block number (count existing blocks)
    block_number = db.query(AuditBlock).count() + 1

    # Save to db
    db_block = AuditBlock(
        match_id=match_id,
        block_number=block_number,
        payload=payload,
        previous_hash=prev_hash,
        hash=block_hash
    )
    db.add(db_block)
    db.commit()
    db.refresh(db_block)
    return db_block

@router.get("/blocks", response_model=List[AuditBlockResponse])
def get_all_audit_blocks(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Get the list of all audit blocks.
    Triggers block creation on-the-fly for any matches that have locked but do not have an audit block yet.
    """
    now_utc = datetime.utcnow()
    lock_threshold = get_locked_match_cutoff(db, now_utc)

    # Fetch all matches that are currently locked, ordered by chain order
    locked_matches = db.query(Match).filter(
        Match.kickoff_time <= lock_threshold
    ).order_by(Match.kickoff_time.asc(), Match.id.asc()).all()

    # Lazily generate blocks for each locked match
    for match in locked_matches:
        get_or_create_audit_block(db, match.id)

    # Return all audit blocks ordered by block number ascending
    return db.query(AuditBlock).order_by(AuditBlock.block_number.asc()).all()

@router.get("/blocks/{block_number}", response_model=AuditBlockResponse)
def get_audit_block_by_number(
    block_number: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Get detailed information for a specific audit block by block number.
    """
    block = db.query(AuditBlock).filter(AuditBlock.block_number == block_number).first()
    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bloco de auditoria número {block_number} não encontrado."
        )
    return block
