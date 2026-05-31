from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from ..db import get_db
from ..models import User, AuditLog, SystemInvitation, SystemSetting, PasswordResetToken
from ..schemas import UserCreate, UserResponse, UserUpdate, Token, PasswordResetRequest, PasswordResetConfirm
from ..auth import get_password_hash, verify_password, create_access_token, get_current_active_user
import hashlib
import html
import os
import secrets
import smtplib
import time
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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

def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def get_password_reset_link(token: str) -> str:
    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base_url}/reset-password?token={token}"

def send_password_reset_email(email: str, display_name: str, token: str) -> bool:
    import logging

    logger = logging.getLogger("bolao_password_reset")
    smtp_host = os.getenv("SMTP_HOST", "172.25.0.1")
    smtp_port = int(os.getenv("SMTP_PORT", "25"))
    from_domain = os.getenv("FROM_DOMAIN", "bru.to")
    sender_email = os.getenv("SMTP_FROM", f"no-reply@{from_domain}")
    reset_link = get_password_reset_link(token)
    safe_display_name = html.escape(display_name)
    safe_reset_link = html.escape(reset_link, quote=True)

    message = MIMEMultipart("alternative")
    message["Subject"] = "Redefinição de senha - Bolão Copa 2026"
    message["From"] = sender_email
    message["To"] = email

    text = (
        f"Olá, {display_name}!\n\n"
        "Recebemos uma solicitação para redefinir sua senha do Bolão Copa 2026.\n"
        f"Acesse o link abaixo para criar uma nova senha:\n\n{reset_link}\n\n"
        "Se você não solicitou esta alteração, ignore este e-mail."
    )
    html_body = f"""\
    <html>
      <body>
        <p>Olá, {safe_display_name}!</p>
        <p>Recebemos uma solicitação para redefinir sua senha do <strong>Bolão Copa 2026</strong>.</p>
        <p><a href="{safe_reset_link}" style="background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Redefinir senha</a></p>
        <p style="font-size: 0.875rem; color: #4b5563;">Se o botão não funcionar, copie e cole este endereço no navegador:<br>{safe_reset_link}</p>
        <p>Se você não solicitou esta alteração, ignore este e-mail.</p>
      </body>
    </html>
    """

    message.attach(MIMEText(text, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            if os.getenv("SMTP_STARTTLS", "false").lower() == "true":
                server.starttls()
            username = os.getenv("SMTP_USERNAME")
            password = os.getenv("SMTP_PASSWORD")
            if username and password:
                server.login(username, password)
            server.sendmail(sender_email, email, message.as_string())
        return True
    except Exception as e:
        logger.error(f"Falha ao enviar e-mail de redefinição para {email}: {str(e)}")
        return False

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

@router.get("/registration-link/check")
def check_registration_link(code: str, db: Session = Depends(get_db)):
    if not code:
        return {"valid": False, "detail": "Código não fornecido."}

    setting = db.query(SystemSetting).filter(SystemSetting.key == "hidden_registration_code").first()
    if not setting or setting.value != code:
        return {"valid": False, "detail": "Link de cadastro inválido."}

    return {"valid": True}

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_in: UserCreate,
    request: Request,
    invite_code: str = None,
    registration_code: str = None,
    db: Session = Depends(get_db)
):
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
    requires_admin_approval = False
    if user_count > 0:
        if invite_code:
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
        elif registration_code:
            setting = db.query(SystemSetting).filter(SystemSetting.key == "hidden_registration_code").first()
            if not setting or setting.value != registration_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Link de cadastro inválido."
                )
            requires_admin_approval = True
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Um código de convite válido é necessário para se cadastrar."
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
        is_active=not requires_admin_approval
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
        new_value={
            "username": new_user.username,
            "role": new_user.role,
            "requires_admin_approval": requires_admin_approval
        }
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
            detail="Esta conta está inativa ou aguardando aprovação do administrador."
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

@router.post("/password-reset/request")
def request_password_reset(
    reset_in: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    if not check_rate_limit(request.client.host if request.client else "unknown"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas solicitações de redefinição. Por favor, tente novamente mais tarde."
        )

    generic_response = {"message": "Se o e-mail estiver cadastrado, enviaremos um link para redefinição de senha."}
    user = db.query(User).filter(User.email == reset_in.email).first()
    if not user:
        return generic_response

    now = datetime.utcnow()
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at == None,
        PasswordResetToken.expires_at > now
    ).update({"used_at": now})

    raw_token = secrets.token_urlsafe(32)
    expires_minutes = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "60"))
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(raw_token),
        expires_at=now + timedelta(minutes=expires_minutes)
    )
    db.add(reset_token)

    audit = AuditLog(
        user_id=user.id,
        action="password_reset_request",
        target_type="user",
        target_id=str(user.id)
    )
    db.add(audit)
    db.commit()

    sent = send_password_reset_email(user.email, user.display_name, raw_token)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível enviar o e-mail de redefinição de senha."
        )

    return generic_response

@router.post("/password-reset/confirm")
def confirm_password_reset(
    reset_in: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    now = datetime.utcnow()
    token_hash = hash_reset_token(reset_in.token)
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at == None,
        PasswordResetToken.expires_at > now
    ).first()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado."
        )

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado."
        )

    user.hashed_password = get_password_hash(reset_in.password)
    reset_token.used_at = now

    audit = AuditLog(
        user_id=user.id,
        action="password_reset_confirm",
        target_type="user",
        target_id=str(user.id)
    )
    db.add(audit)
    db.commit()

    return {"message": "Senha redefinida com sucesso."}

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
