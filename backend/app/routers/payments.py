from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import io
import qrcode
from uuid import UUID
from PIL import Image, UnidentifiedImageError

from ..db import get_db
from ..models import User, PixConfig, AuditLog, SystemSetting
from ..schemas import PixConfigResponse, PixConfigUpdate, UserResponse
from ..auth import get_current_active_user
from ..notifications import send_payment_approval_notification, send_whatsapp_message
from ..scoring import invalidate_ranking_cache
from .utils import user_name_sort_key

router = APIRouter(prefix="/api/payments", tags=["Payments"])

ALLOWED_PROOF_TYPES = {
    ".png": {"content_types": {"image/png"}, "magic": b"\x89PNG\r\n\x1a\n", "media_type": "image/png"},
    ".jpg": {"content_types": {"image/jpeg"}, "magic": b"\xff\xd8\xff", "media_type": "image/jpeg"},
    ".jpeg": {"content_types": {"image/jpeg"}, "magic": b"\xff\xd8\xff", "media_type": "image/jpeg"},
    ".pdf": {"content_types": {"application/pdf"}, "magic": b"%PDF-", "media_type": "application/pdf"},
}

PDF_ACTIVE_CONTENT_MARKERS = (
    b"/JavaScript",
    b"/JS",
    b"/OpenAction",
    b"/AA",
    b"/Launch",
    b"/EmbeddedFile",
    b"/RichMedia",
    b"/AcroForm",
    b"/XFA",
)

def validate_payment_proof_upload(filename: str, content_type: str, content: bytes) -> tuple[str, str]:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_PROOF_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos PNG, JPG, JPEG e PDF são aceitos."
        )

    expected = ALLOWED_PROOF_TYPES[ext]
    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_content_type not in expected["content_types"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O tipo MIME informado não corresponde ao formato do arquivo."
        )

    if not content.startswith(expected["magic"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo enviado não possui uma assinatura (magic bytes) válida para o formato informado."
        )

    if ext in [".png", ".jpg", ".jpeg"]:
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
                detected_format = image.format
        except (UnidentifiedImageError, OSError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A imagem enviada não pôde ser validada."
            )

        if ext == ".png" and detected_format != "PNG":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O conteúdo do arquivo não é um PNG válido.")
        if ext in [".jpg", ".jpeg"] and detected_format != "JPEG":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O conteúdo do arquivo não é um JPEG válido.")

    if ext == ".pdf":
        if b"%%EOF" not in content[-2048:]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O PDF enviado não parece estar completo."
            )
        lowered = content.lower()
        if any(marker.lower() in lowered for marker in PDF_ACTIVE_CONTENT_MARKERS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDFs com conteúdo ativo, scripts ou anexos embutidos não são aceitos."
            )

    return ext, expected["media_type"]

def crc16_ccitt(data: str) -> str:
    """
    Computes CRC16-CCITT for Pix payload calculation.
    Polynomial: 0x1021, Init: 0xFFFF.
    """
    crc = 0xFFFF
    for char in data:
        crc ^= (ord(char) << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04x}".upper()

def generate_pix_copia_cola(pix_key: str, merchant_name: str, merchant_city: str, entry_fee: float) -> str:
    """
    Translates the Pix generation bash script logic to pure Python.
    Formats and concatenates EMV fields and calculates CRC16 check.
    """
    if not pix_key or not merchant_name or not merchant_city:
        return ""
        
    merchant_name = merchant_name.upper().strip()
    merchant_city = merchant_city.upper().replace(" ", ".").strip()
    
    format_indicator = "01"
    gui = "br.gov.bcb.pix"
    merchant_category = "0000"
    currency = "986" # BRL
    country = "BR"
    txid = "***"
    
    s_format = f"{len(format_indicator):02d}{format_indicator}"
    s_gui = f"{len(gui):02d}{gui}"
    s_chave = f"{len(pix_key):02d}{pix_key}"
    
    inner_26 = f"00{s_gui}01{s_chave}"
    field_26 = f"26{len(inner_26):02d}{inner_26}"
    
    field_52 = f"5204{merchant_category}"
    field_53 = f"5303{currency}"
    
    field_54 = ""
    if entry_fee > 0:
        fee_str = f"{entry_fee:.2f}"
        field_54 = f"54{len(fee_str):02d}{fee_str}"
        
    field_58 = f"5802{country}"
    field_59 = f"59{len(merchant_name):02d}{merchant_name}"
    field_60 = f"60{len(merchant_city):02d}{merchant_city}"
    
    subfield_05 = f"05{len(txid):02d}{txid}"
    field_62 = f"62{len(subfield_05):02d}{subfield_05}"
    
    partial_string = f"00{s_format}{field_26}{field_52}{field_53}{field_54}{field_58}{field_59}{field_60}{field_62}6304"
    
    crc = crc16_ccitt(partial_string)
    
    return f"{partial_string}{crc}"

@router.get("/config")
def get_payment_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Returns Pix config and the generated copy & paste payload string.
    """
    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    if not config:
        return {
            "pix_key": "",
            "merchant_name": "",
            "merchant_city": "",
            "entry_fee": 0.0,
            "prizepool_winners": 3,
            "copia_e_cola": ""
        }
        
    copia_cola = generate_pix_copia_cola(
        pix_key=config.pix_key,
        merchant_name=config.merchant_name,
        merchant_city=config.merchant_city,
        entry_fee=float(config.entry_fee)
    )
    
    return {
        "pix_key": config.pix_key or "",
        "merchant_name": config.merchant_name or "",
        "merchant_city": config.merchant_city or "",
        "entry_fee": float(config.entry_fee),
        "prizepool_winners": config.prizepool_winners,
        "copia_e_cola": copia_cola
    }

@router.get("/qrcode")
def get_qrcode(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Dynamically generates and returns the QR Code as PNG image stream.
    """
    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    if not config or not config.pix_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pix não configurado pelo administrador do sistema."
        )
        
    payload = generate_pix_copia_cola(
        pix_key=config.pix_key,
        merchant_name=config.merchant_name,
        merchant_city=config.merchant_city,
        entry_fee=float(config.entry_fee)
    )
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pix inválido ou incompleto."
        )
        
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)
    
    return StreamingResponse(img_buf, media_type="image/png")

@router.get("/summary")
def get_payment_summary(db: Session = Depends(get_db)):
    """
    Returns public billing info and dynamic prize breakdowns for the Rules view.
    """
    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    entry_fee = float(config.entry_fee) if config else 0.0
    winners_count = config.prizepool_winners if config else 3
    
    approved_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status == "approved"
    ).count()
    total_collected = entry_fee * approved_count
    
    from ..settings import calculate_prizepool
    prizes = calculate_prizepool(total_collected, entry_fee, winners_count)
    
    legacy_prizes = {
        "first_place": 0.0,
        "second_place": 0.0,
        "third_place": 0.0
    }
    for p in prizes:
        if p["position"] == 1:
            legacy_prizes["first_place"] = p["value"]
        elif p["position"] == 2:
            legacy_prizes["second_place"] = p["value"]
        elif p["position"] == 3:
            legacy_prizes["third_place"] = p["value"]
            
    return {
        "entry_fee": entry_fee,
        "approved_payments_count": approved_count,
        "total_collected": total_collected,
        "prizes": legacy_prizes,
        "prize_list": prizes
    }

@router.post("/submit-proof", response_model=UserResponse)
async def submit_proof(
    pix_key_receive: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Saves proof receipt, validates size limit (<1MB) and magic bytes.
    Sets status to 'submitted'.
    """
    if current_user.payment_status in ["submitted", "approved"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comprovante já enviado ou pagamento aprovado."
        )
        
    content = await file.read()
    if len(content) > 1024 * 1024:  # 1MB
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O tamanho do arquivo excede o limite de 1MB."
        )
        
    filename = file.filename or ""
    ext, _ = validate_payment_proof_upload(filename, file.content_type or "", content)
        
    save_filename = f"proof_{current_user.id}{ext}"
    save_path = os.path.join("/app/uploads", save_filename)
    
    try:
        with open(save_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao salvar o arquivo no servidor: {str(e)}"
        )
        
    current_user.pix_key_receive = pix_key_receive
    current_user.payment_status = "submitted"
    current_user.payment_proof_filename = save_filename
    current_user.payment_rejected_reason = None
    
    db.commit()
    db.refresh(current_user)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="payment_submit_proof",
        target_type="user",
        target_id=str(current_user.id),
        new_value={"pix_key_receive": pix_key_receive, "filename": save_filename}
    )
    db.add(audit)
    db.commit()
    
    try:
        send_payment_proof_email(
            user=current_user,
            file_content=content,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            pix_key=pix_key_receive,
            db=db
        )
    except Exception as email_err:
        import logging
        logger = logging.getLogger("bolao_payments")
        logger.error(f"Erro ao disparar envio de e-mail do comprovante: {str(email_err)}")
        
    return current_user

@router.get("/proof/me")
def get_my_proof(
    current_user: User = Depends(get_current_active_user)
):
    """
    Streams the current user's uploaded proof file.
    """
    if not current_user.payment_proof_filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum comprovante enviado por você."
        )
        
    path = os.path.join("/app/uploads", current_user.payment_proof_filename)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo do comprovante não encontrado no servidor."
        )
        
    ext = os.path.splitext(current_user.payment_proof_filename)[1].lower()
    media_type = ALLOWED_PROOF_TYPES.get(ext, {}).get("media_type", "application/octet-stream")
    
    return FileResponse(path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})

@router.get("/proof/{user_id}")
def get_user_proof(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Streams a specific user's proof file. Admin access only.
    """
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.payment_proof_filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comprovante de pagamento não encontrado."
        )
        
    path = os.path.join("/app/uploads", user.payment_proof_filename)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo do comprovante não encontrado no servidor."
        )
        
    ext = os.path.splitext(user.payment_proof_filename)[1].lower()
    media_type = ALLOWED_PROOF_TYPES.get(ext, {}).get("media_type", "application/octet-stream")
    
    return FileResponse(path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})

@router.get("/admin/list", response_model=List[UserResponse])
def admin_list_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Lists all users to track and manage payment statuses. Admin access only.
    """
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )
    return sorted(db.query(User).all(), key=user_name_sort_key)


def _sanitize_debtor_name(display_name: str) -> str:
    clean = "".join(ch if ch.isprintable() else " " for ch in (display_name or "Participante"))
    clean = " ".join(clean.split())
    return clean[:80] or "Participante"


from pydantic import BaseModel

class ChargeTemplateUpdate(BaseModel):
    template: str


def _format_brl(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def get_all_placeholder_values(
    db: Session,
    target_user_name: str = "Fulano de Tal",
    debtors_list: list[User] = None
) -> dict:
    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    fee = float(config.entry_fee or 0.0) if config else 0.0
    winners_count = config.prizepool_winners if config else 3

    # Total active registered users (excluding admins)
    approved_registry_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True
    ).count()

    # Total active paid users (excluding admins)
    approved_payment_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status == "approved"
    ).count()

    # Total registered users (excluding admins)
    total_registered = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"])
    ).count()

    # Debtors list & count
    if debtors_list is None:
        debtors_query = db.query(User).filter(
            User.role.notin_(["system_admin", "score_admin"]),
            User.is_active == True,
            User.payment_status != "approved"
        )
        debtors_list = sorted(debtors_query.all(), key=user_name_sort_key)

    debtors_count = len(debtors_list)
    names = "\n".join(_sanitize_debtor_name(u.display_name) for u in debtors_list)

    total_val = approved_payment_count * fee

    from ..settings import calculate_prizepool
    prizes = calculate_prizepool(total_val, fee, winners_count)

    prizepool_text = "\n".join(f"{p['label']}: {_format_brl(p['value'])}" for p in prizes)

    taxa_str = _format_brl(fee)
    valor_str = _format_brl(total_val)

    safe_user_name = " ".join((target_user_name or "Participante").split())

    return {
        "usuario": safe_user_name,
        "devedores": names,
        "aprovados": approved_registry_count,
        "aprovados_pagos": approved_payment_count,
        "valor": valor_str,
        "prizepool": prizepool_text,
        "total_cadastrados": total_registered,
        "devedores_qtd": debtors_count,
        "taxa_inscricao": taxa_str
    }


@router.get("/admin/charge-template")
def get_payment_charge_template(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )

    setting = db.query(SystemSetting).filter(SystemSetting.key == "payment_charge_template").first()
    default_val = (
        "📢 *BOLÃO 2026 INFORMA:*\n\n"
        "O VAR financeiro revisou o lance e encontrou pendências:\n"
        "{{devedores}}\n\n"
        "Ainda não pagaram o bolão! 😅\n"
        "Sem pagar não pode palpitar! Faça o pagamento 👇"
    )
    template = setting.value if setting else default_val

    return {
        "template": template,
        "values": get_all_placeholder_values(db, target_user_name="Fulano de Tal")
    }


@router.put("/admin/charge-template")
def update_payment_charge_template(
    payload: ChargeTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )

    setting = db.query(SystemSetting).filter(SystemSetting.key == "payment_charge_template").first()
    if not setting:
        setting = SystemSetting(key="payment_charge_template", value=payload.template)
        db.add(setting)
    else:
        setting.value = payload.template
    db.commit()
    return {"template": setting.value}


class ApprovalTemplateUpdate(BaseModel):
    template: str


@router.get("/admin/approval-template")
def get_payment_approval_template(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )

    setting = db.query(SystemSetting).filter(SystemSetting.key == "payment_approval_template").first()
    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    winners_count = config.prizepool_winners if config else 3
    default_val = (
        "💰 Pagamento de {{usuario}} foi aprovado!\n\n"
        "total na poupança do Gliva: *{{valor}}*\n\n"
        f"Previsão de pagamentos para os {winners_count} primeiros:\n"
        "{{prizepool}}"
    )
    template = setting.value if setting else default_val

    return {
        "template": template,
        "values": get_all_placeholder_values(db, target_user_name="Fulano de Tal")
    }


@router.put("/admin/approval-template")
def update_payment_approval_template(
    payload: ApprovalTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )

    setting = db.query(SystemSetting).filter(SystemSetting.key == "payment_approval_template").first()
    if not setting:
        setting = SystemSetting(key="payment_approval_template", value=payload.template)
        db.add(setting)
    else:
        setting.value = payload.template
    db.commit()
    return {"template": setting.value}


def _format_payment_charge_message(db: Session, users: list[User]) -> str:
    setting = db.query(SystemSetting).filter(SystemSetting.key == "payment_charge_template").first()
    if setting and setting.value:
        template = setting.value
    else:
        template = (
            "📢 *BOLÃO 2026 INFORMA:*\n\n"
            "O VAR financeiro revisou o lance e encontrou pendências:\n"
            "{{devedores}}\n\n"
            "Ainda não pagaram o bolão! 😅\n"
            "Sem pagar não pode palpitar! Faça o pagamento 👇"
        )

    vals = get_all_placeholder_values(db, target_user_name="Todos", debtors_list=users)
    msg = template
    for key, val in vals.items():
        msg = msg.replace(f"{{{{{key}}}}}", str(val))
    return msg


@router.post("/admin/charge-debtors")
def admin_charge_payment_debtors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Sends a WhatsApp charge message to the configured group for participants
    whose payment has not been approved yet.
    """
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )

    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    if not config or not config.pix_key or not config.merchant_name or not config.merchant_city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configure o Pix antes de enviar a cobrança."
        )

    copia_cola = generate_pix_copia_cola(
        pix_key=config.pix_key,
        merchant_name=config.merchant_name,
        merchant_city=config.merchant_city,
        entry_fee=float(config.entry_fee or 0.0)
    )
    if not copia_cola:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível gerar o Pix copia e cola."
        )

    debtors = sorted(db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status != "approved"
    ).all(), key=user_name_sort_key)

    if not debtors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há participantes com pagamento pendente."
        )

    charge_msg = _format_payment_charge_message(db, debtors)
    first_sent = send_whatsapp_message(charge_msg)
    if not first_sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível enviar a cobrança pelo WhatsApp."
        )

    second_sent = send_whatsapp_message(copia_cola)
    if not second_sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="A cobrança foi enviada, mas não foi possível enviar o Pix copia e cola."
        )

    audit = AuditLog(
        user_id=current_user.id,
        action="payment_charge_debtors",
        target_type="payment",
        target_id="debtors",
        new_value={"debtors_count": len(debtors)}
    )
    db.add(audit)
    db.commit()

    return {"sent": True, "debtors_count": len(debtors)}

@router.post("/admin/approve/{user_id}", response_model=UserResponse)
def admin_approve_payment(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Approves a participant payment. Admin access only.
    """
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado."
        )
        
    user.payment_status = "approved"
    user.payment_rejected_reason = None
    
    db.commit()
    db.refresh(user)
    invalidate_ranking_cache(db)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="payment_approve",
        target_type="user",
        target_id=str(user.id),
        new_value={"payment_status": "approved"}
    )
    db.add(audit)
    db.commit()
    send_payment_approval_notification(db, user)
    
    return user

@router.post("/admin/revert/{user_id}", response_model=UserResponse)
def admin_revert_payment_approval(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reverts an approved participant payment back to review/pending state.
    """
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado."
        )

    if user.payment_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas pagamentos aprovados podem ser revertidos."
        )

    previous_status = user.payment_status
    next_status = "submitted" if user.payment_proof_filename else "pending"
    user.payment_status = next_status
    user.payment_rejected_reason = None

    db.commit()
    db.refresh(user)
    invalidate_ranking_cache(db)

    audit = AuditLog(
        user_id=current_user.id,
        action="payment_revert_approval",
        target_type="user",
        target_id=str(user.id),
        old_value={"payment_status": previous_status},
        new_value={"payment_status": next_status}
    )
    db.add(audit)
    db.commit()

    return user

@router.post("/admin/reject/{user_id}", response_model=UserResponse)
def admin_reject_payment(
    user_id: UUID,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Rejects a participant payment with a reason. Admin access only.
    """
    if current_user.role not in ["system_admin", "score_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores."
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado."
        )
        
    user.payment_status = "rejected"
    user.payment_rejected_reason = reason
    
    db.commit()
    db.refresh(user)
    invalidate_ranking_cache(db)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="payment_reject",
        target_type="user",
        target_id=str(user.id),
        new_value={"payment_status": "rejected", "reason": reason}
    )
    db.add(audit)
    db.commit()
    
    return user

@router.post("/admin/config", response_model=PixConfigResponse)
def admin_update_config(
    config_in: PixConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Updates the global Pix parameters. System admin access only.
    """
    if current_user.role != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores do sistema podem alterar a configuração do Pix."
        )
        
    if config_in.prizepool_winners not in [3, 5, 7]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O número de premiados deve ser 3, 5 ou 7."
        )

    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    if not config:
        config = PixConfig(id=1)
        db.add(config)
        
    config.pix_key = config_in.pix_key
    config.merchant_name = config_in.merchant_name
    config.merchant_city = config_in.merchant_city
    config.entry_fee = config_in.entry_fee
    config.prizepool_winners = config_in.prizepool_winners
    
    db.commit()
    db.refresh(config)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="payment_update_config",
        target_type="pix_config",
        target_id="1",
        new_value={
            "pix_key": config.pix_key,
            "merchant_name": config.merchant_name,
            "merchant_city": config.merchant_city,
            "entry_fee": float(config.entry_fee),
            "prizepool_winners": config.prizepool_winners
        }
    )
    db.add(audit)
    db.commit()
    
    return config


def send_payment_proof_email(
    user: User,
    file_content: bytes,
    filename: str,
    content_type: str,
    pix_key: str,
    db: Session
) -> bool:
    import logging
    import smtplib
    import html
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    from .auth import get_admin_registration_notification_recipients, get_admin_payments_link

    recipients = get_admin_registration_notification_recipients(db)
    if not recipients:
        return False

    logger = logging.getLogger("bolao_payment_proof_notification")
    smtp_host = os.getenv("SMTP_HOST", "172.25.0.1")
    smtp_port = int(os.getenv("SMTP_PORT", "25"))
    from_domain = os.getenv("FROM_DOMAIN", "bru.to")
    sender_email = os.getenv("SMTP_FROM", f"no-reply@{from_domain}")
    admin_link = get_admin_payments_link()

    safe_display_name = html.escape(user.display_name)
    safe_username = html.escape(user.username)
    safe_email = html.escape(user.email)
    safe_pix_key = html.escape(pix_key)
    safe_admin_link = html.escape(admin_link, quote=True)

    message = MIMEMultipart("mixed")
    message["Subject"] = f"Novo comprovante de pagamento - {user.display_name}"
    message["From"] = sender_email
    message["To"] = ", ".join(recipients)

    msg_alternative = MIMEMultipart("alternative")
    
    text = (
        "Novo comprovante de pagamento recebido no Bolão Copa 2026.\n\n"
        f"Nome: {user.display_name}\n"
        f"Usuário: {user.username}\n"
        f"E-mail: {user.email}\n"
        f"Chave Pix: {pix_key}\n\n"
        f"Acesse o painel de pagamentos para aprovar: {admin_link}\n\n"
        "O comprovante está anexado a este e-mail."
    )

    html_body = f"""\
    <html>
      <body style="font-family: Arial, sans-serif; color: #111827; background: #f9fafb; padding: 24px;">
        <div style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
          <div style="background: #0f172a; color: #ffffff; padding: 20px 24px;">
            <h1 style="margin: 0; font-size: 20px;">Novo comprovante de pagamento recebido</h1>
          </div>
          <div style="padding: 24px;">
            <p style="margin-top: 0;">O participante <strong>{safe_display_name}</strong> anexou um comprovante de pagamento para validação.</p>
            <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
              <tr><td style="padding: 8px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Nome</td><td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{safe_display_name}</td></tr>
              <tr><td style="padding: 8px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">Usuário</td><td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{safe_username}</td></tr>
              <tr><td style="padding: 8px; border-bottom: 1px solid #e5e7eb; font-weight: bold;">E-mail</td><td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{safe_email}</td></tr>
              <tr><td style="padding: 8px; font-weight: bold;">Chave Pix Informada</td><td style="padding: 8px;">{safe_pix_key}</td></tr>
            </table>
            <p>O arquivo do comprovante está anexado a este e-mail.</p>
            <p>Clique no botão abaixo para acessar o painel de pagamentos e realizar a aprovação:</p>
            <p>
              <a href="{safe_admin_link}" style="background: #10b981; color: white; padding: 12px 18px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">Verificar e Aprovar</a>
            </p>
            <p style="font-size: 13px; color: #6b7280;">Se o botão não funcionar, copie e cole este endereço no navegador:<br>{safe_admin_link}</p>
          </div>
        </div>
      </body>
    </html>
    """

    msg_alternative.attach(MIMEText(text, "plain", "utf-8"))
    msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))
    message.attach(msg_alternative)

    try:
        main_type, sub_type = "application", "octet-stream"
        if content_type and "/" in content_type:
            parts = content_type.split("/", 1)
            main_type, sub_type = parts[0], parts[1]
            
        attachment = MIMEApplication(file_content, _subtype=sub_type)
        attachment.add_header('Content-Disposition', 'attachment', filename=filename)
        attachment.replace_header('Content-Type', content_type)
        message.attach(attachment)
    except Exception as e:
        logger.error(f"Erro ao anexar arquivo de comprovante de pagamento: {str(e)}")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            if os.getenv("SMTP_STARTTLS", "false").lower() == "true":
                server.starttls()
            username = os.getenv("SMTP_USERNAME")
            password = os.getenv("SMTP_PASSWORD")
            if username and password:
                server.login(username, password)
            server.sendmail(sender_email, recipients, message.as_string())
        logger.info(f"E-mail de comprovante de pagamento enviado para os administradores: {recipients}")
        return True
    except Exception as e:
        logger.error(f"Falha ao enviar e-mail de comprovante de pagamento: {str(e)}")
        return False
