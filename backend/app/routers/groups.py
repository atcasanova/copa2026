import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from ..db import get_db
from ..models import Group, GroupMember, GroupInvitation, User, AuditLog, Match, Prediction
from ..schemas import GroupCreate, GroupResponse, GroupDetailResponse, GroupUpdate, GroupMemberResponse, GroupInvitationResponse, GroupInvitationCreate, UserPublicResponse
from ..auth import get_current_active_user
from ..settings import get_locked_match_cutoff
import io
import csv
from fastapi.responses import StreamingResponse

def sanitize_csv_value(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    val_str = str(val)
    if val_str and val_str[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + val_str
    return val_str

router = APIRouter(prefix="/api/groups", tags=["Groups"])

def generate_invite_code() -> str:
    return secrets.token_hex(4).upper() # 8 characters hex

def check_group_admin(db: Session, group_id: UUID, user_id: UUID) -> bool:
    """
    Returns True if user is group owner/admin, or system_admin.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.role == "system_admin":
        return True
        
    membership = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
        GroupMember.is_approved == True,
        GroupMember.role.in_(["owner", "admin"])
    ).first()
    return membership is not None

def serialize_group_detail(group: Group, include_invite_code: bool) -> dict:
    data = {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "owner_id": group.owner_id,
        "is_private": group.is_private,
        "created_at": group.created_at,
        "owner": group.owner,
        "invite_code": group.invite_code if include_invite_code else None,
    }
    return data

def create_group_record(
    group_in: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    invite_code = generate_invite_code()
    # Ensure unique invite code
    while db.query(Group).filter(Group.invite_code == invite_code).first():
        invite_code = generate_invite_code()
        
    new_group = Group(
        name=group_in.name,
        description=group_in.description,
        owner_id=current_user.id,
        invite_code=invite_code,
        is_private=group_in.is_private
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    
    # Auto join owner
    member = GroupMember(
        group_id=new_group.id,
        user_id=current_user.id,
        role="owner",
        is_approved=True
    )
    db.add(member)
    db.commit()
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_create",
        target_type="group",
        target_id=str(new_group.id),
        new_value={"name": new_group.name, "is_private": new_group.is_private}
    )
    db.add(audit)
    db.commit()
	    
    return new_group

def list_my_and_public_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get groups that are either public or where the current user is a member.
    """
    # Subquery groups current user belongs to
    my_group_ids = [m.group_id for m in db.query(GroupMember.group_id).filter(
        GroupMember.user_id == current_user.id,
        GroupMember.is_approved == True
    ).all()]
    
    return db.query(Group).filter(
        (Group.is_private == False) | (Group.id.in_(my_group_ids))
    ).all()

@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_group_without_trailing_slash(
    group_in: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return create_group_record(group_in, db, current_user)

@router.post("/", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    group_in: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return create_group_record(group_in, db, current_user)

@router.get("", response_model=List[GroupResponse], include_in_schema=False)
def get_my_and_public_groups_without_trailing_slash(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return list_my_and_public_groups(db, current_user)

@router.get("/", response_model=List[GroupResponse])
def get_my_and_public_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return list_my_and_public_groups(db, current_user)

@router.get("/{group_id}", response_model=GroupDetailResponse)
def get_group_details(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    # Check permission if private group
    if group.is_private:
        membership = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
            GroupMember.is_approved == True
        ).first()
        # Admin bypass
        if not membership and current_user.role != "system_admin":
            raise HTTPException(status_code=403, detail="Acesso negado: Este é um grupo privado.")
            
    return serialize_group_detail(group, check_group_admin(db, group_id, current_user.id))

@router.get("/{group_id}/members", response_model=List[GroupMemberResponse])
def get_group_members(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    # If private group, user must be a member to see members list (or be system_admin)
    if group.is_private and current_user.role != "system_admin":
        membership = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
            GroupMember.is_approved == True
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Acesso negado.")
            
    return db.query(GroupMember).filter(GroupMember.group_id == group_id).all()

@router.post("/join/code/{invite_code}", response_model=GroupMemberResponse)
def join_group_by_code(
    invite_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    group = db.query(Group).filter(Group.invite_code == invite_code.strip().upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="Código de convite inválido.")
        
    # Check if already a member
    existing = db.query(GroupMember).filter(
        GroupMember.group_id == group.id,
        GroupMember.user_id == current_user.id
    ).first()
    if existing:
        if existing.is_approved:
            raise HTTPException(status_code=400, detail="Você já é membro deste grupo.")
        else:
            raise HTTPException(status_code=400, detail="Sua solicitação de entrada já está pendente de aprovação.")
            
    # If public, auto approve. If private, requires approval.
    is_approved = not group.is_private
    
    new_member = GroupMember(
        group_id=group.id,
        user_id=current_user.id,
        role="member",
        is_approved=is_approved
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_join",
        target_type="group",
        target_id=str(group.id),
        new_value={"is_approved": is_approved}
    )
    db.add(audit)
    db.commit()
    
    return new_member

@router.post("/{group_id}/invite", response_model=GroupInvitationResponse)
def invite_user(
    group_id: UUID,
    invite_in: GroupInvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Verify group exists
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    # Only group owner or admin can invite (or system admin)
    if not check_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Apenas administradores do grupo podem enviar convites.")
        
    # Find user by username or email. A leading @ is accepted for manual username input.
    invitee_identifier = invite_in.invitee_identifier.strip()
    invitee_username = invitee_identifier.lstrip("@")
    invitee = db.query(User).filter(
        or_(
            User.username.ilike(invitee_username),
            User.email.ilike(invitee_identifier),
            User.display_name.ilike(invitee_identifier)
        )
    ).first()
    
    # If user doesn't exist, we can register an email-only invite, but in this version we restrict to existing users.
    if not invitee:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    # Check if already a member
    membership = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == invitee.id
    ).first()
    if membership:
        raise HTTPException(status_code=400, detail="Este usuário já pertence ao grupo.")
        
    # Check if pending invite exists
    existing_invite = db.query(GroupInvitation).filter(
        GroupInvitation.group_id == group_id,
        GroupInvitation.invitee_id == invitee.id,
        GroupInvitation.status == "pending"
    ).first()
    if existing_invite:
        raise HTTPException(status_code=400, detail="Já existe um convite pendente para este usuário.")
        
    new_invite = GroupInvitation(
        group_id=group_id,
        invited_by_id=current_user.id,
        invitee_id=invitee.id,
        invitee_email=invitee.email,
        status="pending"
    )
    db.add(new_invite)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_invite_send",
        target_type="group_invitation",
        target_id=str(new_invite.id),
        new_value={"invitee_id": str(invitee.id), "group_id": str(group_id)}
    )
    db.add(audit)
    db.commit()
    db.refresh(new_invite)
    
    return new_invite

@router.get("/{group_id}/invite-candidates", response_model=List[UserPublicResponse])
def search_group_invite_candidates(
    group_id: UUID,
    q: str = Query(..., min_length=2, max_length=80),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")

    if not check_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Apenas administradores do grupo podem buscar participantes.")

    member_ids = [
        row.user_id for row in db.query(GroupMember.user_id).filter(
            GroupMember.group_id == group_id
        ).all()
    ]
    pending_invite_ids = [
        row.invitee_id for row in db.query(GroupInvitation.invitee_id).filter(
            GroupInvitation.group_id == group_id,
            GroupInvitation.status == "pending",
            GroupInvitation.invitee_id.isnot(None)
        ).all()
    ]
    excluded_ids = [*member_ids, *pending_invite_ids]
    term = f"%{q.strip().lstrip('@')}%"

    query = db.query(User).filter(
        User.is_active == True,
        User.role.notin_(["system_admin", "score_admin"]),
        or_(
            User.username.ilike(term),
            User.display_name.ilike(term)
        )
    )
    if excluded_ids:
        query = query.filter(~User.id.in_(excluded_ids))

    return query.order_by(User.display_name.asc(), User.username.asc()).limit(10).all()

@router.get("/invitations/pending", response_model=List[GroupInvitationResponse])
def get_my_pending_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return db.query(GroupInvitation).filter(
        GroupInvitation.invitee_id == current_user.id,
        GroupInvitation.status == "pending"
    ).all()

@router.post("/invitations/{invite_id}/respond")
def respond_to_invitation(
    invite_id: UUID,
    accept: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    invite = db.query(GroupInvitation).filter(
        GroupInvitation.id == invite_id,
        GroupInvitation.invitee_id == current_user.id,
        GroupInvitation.status == "pending"
    ).first()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Convite não encontrado ou já processado.")
        
    if accept:
        invite.status = "accepted"
        # Create group member
        member = GroupMember(
            group_id=invite.group_id,
            user_id=current_user.id,
            role="member",
            is_approved=True
        )
        db.add(member)
        action = "group_invite_accept"
    else:
        invite.status = "declined"
        action = "group_invite_decline"
        
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action=action,
        target_type="group_invitation",
        target_id=str(invite.id)
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Resposta registrada com sucesso.", "status": invite.status}

@router.post("/{group_id}/members/{user_id}/approve", response_model=GroupMemberResponse)
def approve_member(
    group_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not check_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Sem permissão administrativa.")
        
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")
        
    member.is_approved = True
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_member_approve",
        target_type="group_member",
        target_id=str(member.id),
        new_value={"user_id": str(user_id)}
    )
    db.add(audit)
    db.commit()
    db.refresh(member)
    return member

@router.post("/{group_id}/members/{user_id}/remove")
def remove_member(
    group_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not check_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Sem permissão administrativa.")
        
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")
        
    if member.role == "owner" and current_user.role != "system_admin":
        raise HTTPException(status_code=400, detail="Não é possível remover o proprietário do grupo.")
        
    db.delete(member)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_member_remove",
        target_type="group",
        target_id=str(group_id),
        old_value={"removed_user_id": str(user_id)}
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Membro removido do grupo com sucesso."}

@router.post("/{group_id}/members/{user_id}/role", response_model=GroupMemberResponse)
def change_member_role(
    group_id: UUID,
    user_id: UUID,
    new_role: str = Query(..., enum=["admin", "member"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Only group owner can change roles (or system admin)
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    if group.owner_id != current_user.id and current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="Apenas o proprietário do grupo pode promover ou demitir membros.")
        
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
        GroupMember.is_approved == True
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Membro ativo não encontrado.")
        
    old_role = member.role
    member.role = new_role
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_member_role_change",
        target_type="group_member",
        target_id=str(member.id),
        old_value={"role": old_role},
        new_value={"role": new_role}
    )
    db.add(audit)
    db.commit()
    db.refresh(member)
    
    return member

@router.post("/{group_id}/invite-code/regenerate")
def regenerate_invite_code(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not check_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Sem permissão administrativa.")
        
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    old_code = group.invite_code
    new_code = generate_invite_code()
    while db.query(Group).filter(Group.invite_code == new_code).first():
        new_code = generate_invite_code()
        
    group.invite_code = new_code
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_invite_code_regenerate",
        target_type="group",
        target_id=str(group_id),
        old_value={"invite_code": old_code},
        new_value={"invite_code": new_code}
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Código de convite regenerado com sucesso.", "invite_code": new_code}

@router.post("/{group_id}/privacy")
def change_group_privacy(
    group_id: UUID,
    is_private: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not check_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Sem permissão administrativa.")
        
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    old_val = group.is_private
    group.is_private = is_private
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="group_privacy_change",
        target_type="group",
        target_id=str(group_id),
        old_value={"is_private": old_val},
        new_value={"is_private": is_private}
    )
    db.add(audit)
    db.commit()
    
    return {"message": f"Privacidade do grupo alterada para {'privado' if is_private else 'público'} com sucesso."}

@router.get("/{group_id}/export/ranking")
def export_group_ranking_csv(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Exports group ranking to CSV.
    Accessible by approved group members or system admins.
    """
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    # Check membership
    membership = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id,
        GroupMember.is_approved == True
    ).first()
    if not membership and current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="Apenas membros aprovados podem exportar o ranking.")
        
    from ..scoring import get_rankings
    ranking = get_rankings(db, group_id=group_id)
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Posicao", "Participante", "Pontos Totais", 
        "Placares Exatos", "Resultados Corretos", 
        "Palpites Feitos", "Palpites Faltantes"
    ])
    
    for row in ranking:
        writer.writerow([
            sanitize_csv_value(row["position"]),
            sanitize_csv_value(row["display_name"]),
            sanitize_csv_value(row["total_points"]),
            sanitize_csv_value(row["exact_scores_count"]),
            sanitize_csv_value(row["correct_results_count"]),
            sanitize_csv_value(row["predictions_count"]),
            sanitize_csv_value(row["missing_predictions_count"])
        ])
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=ranking_grupo_{group_id}.csv"
    return response

@router.get("/{group_id}/export/predictions")
def export_group_predictions_csv(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Exports predictions of group members.
    Group admins only.
    Security rule: Only exports predictions for matches that are already locked by the configured prediction window.
    """
    if not check_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Apenas administradores do grupo podem exportar os palpites.")
        
    # Fetch all members
    member_ids = [m.user_id for m in db.query(GroupMember.user_id).filter(
        GroupMember.group_id == group_id, 
        GroupMember.is_approved == True
    ).all()]
    
    # Fetch locked matches
    locked_threshold = get_locked_match_cutoff(db)
    locked_matches = db.query(Match).filter(
        Match.kickoff_time <= locked_threshold
    ).all()
    
    # Build columns dynamically: user name + all locked matches
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    
    headers = ["Participante"]
    for match in locked_matches:
        headers.append(f"{match.team1_name} x {match.team2_name} ({match.round})")
    writer.writerow(headers)
    
    for member_id in member_ids:
        user = db.query(User).filter(User.id == member_id).first()
        if not user:
            continue
            
        row = [sanitize_csv_value(user.display_name)]
        for match in locked_matches:
            pred = db.query(Prediction).filter(
                Prediction.user_id == member_id,
                Prediction.match_id == match.id
            ).first()
            if pred:
                row.append(sanitize_csv_value(f"{pred.goals_team1} x {pred.goals_team2}"))
            else:
                row.append("-")
        writer.writerow(row)
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=palpites_grupo_{group_id}.csv"
    return response
