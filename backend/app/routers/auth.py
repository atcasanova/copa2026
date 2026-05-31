from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from ..db import get_db
from ..models import User, AuditLog, SystemInvitation
from ..schemas import UserCreate, UserResponse, UserUpdate, Token
from ..auth import get_password_hash, verify_password, create_access_token, get_current_active_user
import uuid
import time
from collections import defaultdict

# Simple in-memory rate limiting dictionary
# Format: {ip: [timestamp1, timestamp2, ...]}
RATE_LIMIT_WINDOW = 60 # 1 minute
MAX_ATTEMPTS = 15 # max 15 attempts per minute
rate_limit_db = defaultdict(list)

def check_rate_limit(ip: str) -> bool:
    import os
    if os.getenv("TESTING", "false").lower() == "true":
        return True
    now = time.time()
    # Filter out attempts outside the window
    attempts = [t for t in rate_limit_db[ip] if now - t < RATE_LIMIT_WINDOW]
    rate_limit_db[ip] = attempts
    if len(attempts) >= MAX_ATTEMPTS:
        return False
    rate_limit_db[ip].append(now)
    return True

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.get("/invitations/check")
def check_invitation(code: str, db: Session = Depends(get_db)):
    if not code:
        return {"valid": False, "detail": "Código não fornecido."}
    
    invitation = db.query(SystemInvitation).filter(
        SystemInvitation.code == code,
        SystemInvitation.is_used == False
    ).first()
    
    if not invitation:
        return {"valid": False, "detail": "Código inválido ou já utilizado."}
        
    return {"valid": True, "email": invitation.email}

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, request: Request, invite_code: str = None, db: Session = Depends(get_db)):
    if not check_rate_limit(request.client.host if request.client else "unknown"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas solicitações de registro. Por favor, tente novamente mais tarde."
        )
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user_in.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome de usuário já cadastrado no sistema."
        )
    # Check if email exists
    existing_email = db.query(User).filter(User.email == user_in.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="E-mail já cadastrado no sistema."
        )

    # First user is registered as system_admin, others are participants
    user_count = db.query(User).count()
    
    # Enforce invitation check if user_count > 0 (bootstrap admin is exempted)
    invitation = None
    if user_count > 0:
        if not invite_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Um código de convite válido é necessário para se cadastrar."
            )
        invitation = db.query(SystemInvitation).filter(
            SystemInvitation.code == invite_code,
            SystemInvitation.is_used == False
        ).first()
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Código de convite inválido ou já utilizado."
            )
        if invitation.email.strip().lower() != user_in.email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O e-mail informado não corresponde ao e-mail deste convite."
            )

    role = "system_admin" if user_count == 0 else "participant"

    # Hash password
    hashed_pwd = get_password_hash(user_in.password)

    new_user = User(
        username=user_in.username,
        email=user_in.email,
        display_name=user_in.display_name,
        hashed_password=hashed_pwd,
        role=role,
        notification_preferences={"email": True, "in_app": True},
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    if invitation:
        invitation.is_used = True
        invitation.used_by_id = new_user.id
        invitation.used_at = datetime.utcnow()
        db.commit()

    # Log action
    audit = AuditLog(
        user_id=new_user.id,
        action="user_register",
        target_type="user",
        target_id=str(new_user.id),
        new_value={"username": new_user.username, "role": new_user.role}
    )
    db.add(audit)
    db.commit()

    return new_user

@router.post("/login", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    if not check_rate_limit(request.client.host if request.client else "unknown"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de login. Por favor, tente novamente mais tarde."
        )
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta conta foi desativada pelo administrador."
        )

    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    
    # Log login event
    audit = AuditLog(
        user_id=user.id,
        action="user_login",
        target_type="user",
        target_id=str(user.id)
    )
    db.add(audit)
    db.commit()

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    # JWT tokens are stateless, so logout is primarily handled on the client side by destroying the token.
    # However, we register an audit log for the action.
    audit = AuditLog(
        user_id=current_user.id,
        action="user_logout",
        target_type="user",
        target_id=str(current_user.id)
    )
    db.add(audit)
    db.commit()
    return {"message": "Sessão encerrada com sucesso."}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@router.put("/me", response_model=UserResponse)
def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    old_value = {
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "notification_preferences": current_user.notification_preferences,
        "pix_key_receive": current_user.pix_key_receive
    }

    if user_update.display_name is not None:
        current_user.display_name = user_update.display_name
    if user_update.avatar_url is not None:
        current_user.avatar_url = user_update.avatar_url
    if user_update.notification_preferences is not None:
        current_user.notification_preferences = user_update.notification_preferences
    if user_update.password is not None:
        current_user.hashed_password = get_password_hash(user_update.password)
    if user_update.pix_key_receive is not None:
        current_user.pix_key_receive = user_update.pix_key_receive

    db.commit()
    db.refresh(current_user)

    # Log action
    new_value = {
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "notification_preferences": current_user.notification_preferences,
        "pix_key_receive": current_user.pix_key_receive
    }
    audit = AuditLog(
        user_id=current_user.id,
        action="user_update_profile",
        target_type="user",
        target_id=str(current_user.id),
        old_value=old_value,
        new_value=new_value
    )
    db.add(audit)
    db.commit()

    return current_user
