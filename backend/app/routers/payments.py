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
    
    approved_count = db.query(User).filter(User.payment_status == "approved").count()
    total_collected = entry_fee * approved_count
    
    return {
        "entry_fee": entry_fee,
        "approved_payments_count": approved_count,
        "total_collected": total_collected,
        "prizes": {
            "first_place": total_collected * 0.5,
            "second_place": total_collected * 0.3,
            "third_place": total_collected * 0.2
        }
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

    approved_registry_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True
    ).count()

    approved_payment_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status == "approved"
    ).count()

    total_registered = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"])
    ).count()

    debtors_query = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status != "approved"
    )
    debtors_count = debtors_query.count()
    debtors_list = sorted(debtors_query.all(), key=user_name_sort_key)
    names = "\n".join(_sanitize_debtor_name(user.display_name) for user in debtors_list)

    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    fee = float(config.entry_fee or 0.0) if config else 0.0
    total_val = approved_payment_count * fee

    taxa_str = f"R$ {fee:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    valor_str = f"R$ {total_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return {
        "template": template,
        "values": {
            "devedores": names,
            "aprovados": approved_registry_count,
            "aprovados_pagos": approved_payment_count,
            "valor": valor_str,
            "total_cadastrados": total_registered,
            "devedores_qtd": debtors_count,
            "taxa_inscricao": taxa_str
        }
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
    default_val = (
        "💰 Pagamento de {{usuario}} foi aprovado!\n\n"
        "total na poupança do Gliva: *{{valor}}*\n\n"
        "Previsão de pagamentos para os 3 primeiros:\n"
        "{{prizepool}}"
    )
    template = setting.value if setting else default_val

    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    fee = float(config.entry_fee or 0.0) if config else 0.0
    
    approved_payment_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status == "approved"
    ).count()
    
    total_val = approved_payment_count * fee
    
    pool = {
        "first_place": total_val * 0.5,
        "second_place": total_val * 0.3,
        "third_place": total_val * 0.2,
    }
    
    from ..notifications import _format_brl
    prizepool_text = (
        f"🥇 1º lugar: {_format_brl(pool['first_place'])}\n"
        f"🥈 2º lugar: {_format_brl(pool['second_place'])}\n"
        f"🥉 3º lugar: {_format_brl(pool['third_place'])}"
    )
    
    taxa_str = _format_brl(fee)
    valor_str = _format_brl(total_val)

    return {
        "template": template,
        "values": {
            "usuario": "Fulano de Tal",
            "valor": valor_str,
            "prizepool": prizepool_text,
            "aprovados_pagos": approved_payment_count,
            "taxa_inscricao": taxa_str
        }
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
    names = "\n".join(_sanitize_debtor_name(user.display_name) for user in users)
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

    approved_registry_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True
    ).count()

    approved_payment_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status == "approved"
    ).count()

    total_registered = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"])
    ).count()

    debtors_count = len(users)

    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    fee = float(config.entry_fee or 0.0) if config else 0.0
    total_val = approved_payment_count * fee

    taxa_str = f"R$ {fee:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    valor_str = f"R$ {total_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    msg = template
    msg = msg.replace("{{devedores}}", names)
    msg = msg.replace("{{aprovados}}", str(approved_registry_count))
    msg = msg.replace("{{aprovados_pagos}}", str(approved_payment_count))
    msg = msg.replace("{{valor}}", valor_str)
    msg = msg.replace("{{total_cadastrados}}", str(total_registered))
    msg = msg.replace("{{devedores_qtd}}", str(debtors_count))
    msg = msg.replace("{{taxa_inscricao}}", taxa_str)
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
        
    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    if not config:
        config = PixConfig(id=1)
        db.add(config)
        
    config.pix_key = config_in.pix_key
    config.merchant_name = config_in.merchant_name
    config.merchant_city = config_in.merchant_city
    config.entry_fee = config_in.entry_fee
    
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
            "entry_fee": float(config.entry_fee)
        }
    )
    db.add(audit)
    db.commit()
    
    return config
