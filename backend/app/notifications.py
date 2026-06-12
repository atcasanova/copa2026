import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session

from .models import Match, PixConfig, Prediction, SystemSetting, User
from .scoring import get_rankings

logger = logging.getLogger(__name__)

REMINDER_LEAD_MINUTES = 150
REMINDER_SCAN_WINDOW_MINUTES = 5
LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


def whatsapp_notifications_enabled() -> bool:
    return _env_bool(
        "WHATSAPP_NOTIFY_ENABLED",
        _env_bool("PAYMENT_APPROVAL_NOTIFY_ENABLED", False)
    )


def send_whatsapp_message(text: str) -> bool:
    if not whatsapp_notifications_enabled():
        return False

    url = _env_first("WHATSAPP_NOTIFY_URL", "PAYMENT_APPROVAL_NOTIFY_URL")
    token = _env_first("WHATSAPP_NOTIFY_TOKEN", "PAYMENT_APPROVAL_NOTIFY_TOKEN")
    to = _env_first("WHATSAPP_NOTIFY_TO", "PAYMENT_APPROVAL_NOTIFY_TO")
    send_as = _env_first("WHATSAPP_NOTIFY_SEND_AS", "PAYMENT_APPROVAL_NOTIFY_SEND_AS", default="text") or "text"

    try:
        timeout = float(_env_first(
            "WHATSAPP_NOTIFY_TIMEOUT_SECONDS",
            "PAYMENT_APPROVAL_NOTIFY_TIMEOUT_SECONDS",
            default="5"
        ))
    except ValueError:
        timeout = 5.0

    if not url or not token or not to:
        logger.warning("Mensagem WhatsApp não enviada: configuração incompleta.")
        return False

    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            files={
                "to": (None, to),
                "text": (None, text),
                "sendAs": (None, send_as),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Falha ao enviar mensagem WhatsApp: %s", exc)
        return False


def _format_brl(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def get_payment_pool_summary(db: Session) -> dict:
    config = db.query(PixConfig).filter(PixConfig.id == 1).first()
    entry_fee = float(config.entry_fee) if config and config.entry_fee is not None else 0.0
    winners_count = config.prizepool_winners if config else 3
    approved_count = db.query(User).filter(
        User.role.notin_(["system_admin", "score_admin"]),
        User.is_active == True,
        User.payment_status == "approved"
    ).count()
    total_collected = entry_fee * approved_count
    
    from .settings import calculate_prizepool
    prizes = calculate_prizepool(total_collected, entry_fee, winners_count)
    
    # Keep legacy keys for safety/tests
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
        "approved_count": approved_count,
        "total_collected": total_collected,
        "first_place": legacy_prizes["first_place"],
        "second_place": legacy_prizes["second_place"],
        "third_place": legacy_prizes["third_place"],
        "prizes": prizes,
        "winners_count": winners_count
    }


def format_payment_approval_message(db: Session, display_name: str, payment_pool: dict) -> str:
    setting = db.query(SystemSetting).filter(SystemSetting.key == "payment_approval_template").first()
    winners_count = payment_pool.get("winners_count", 3) if payment_pool else 3
    default_val = (
        "💰 Pagamento de {{usuario}} foi aprovado!\n\n"
        "total na poupança do Gliva: *{{valor}}*\n\n"
        f"Previsão de pagamentos para os {winners_count} primeiros:\n"
        "{{prizepool}}"
    )
    template = setting.value if setting and setting.value else default_val

    from .routers.payments import get_all_placeholder_values
    vals = get_all_placeholder_values(db, target_user_name=display_name)
    
    msg = template
    for key, val in vals.items():
        msg = msg.replace(f"{{{{{key}}}}}", str(val))
    return msg


def send_payment_approval_notification(db: Session, user: User) -> bool:
    return send_whatsapp_message(format_payment_approval_message(db, user.display_name, get_payment_pool_summary(db)))


def _format_local_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LOCAL_TIMEZONE).strftime("%d/%m/%Y %H:%M")


def format_matches_reminder_message(
    kickoff_time: datetime,
    matches: list[Match],
    missing_prediction_counts: dict[int, int] | None = None
) -> str:
    lines = [
        "\u23f0 *Lembrete de palpites*",
        "",
        f"Jogos de *{_format_local_datetime(kickoff_time)}* começam em 2h30:",
        ""
    ]
    for match in matches:
        missing_count = (missing_prediction_counts or {}).get(match.id)
        missing_suffix = f" - Não palpitaram: {missing_count}" if missing_count is not None else ""
        lines.append(f"\u2022 {match.team1_name} x {match.team2_name}{missing_suffix}")
    lines.extend(["", "Entre no bolão e registre seus palpites."])
    return "\n".join(lines)


def _participant_query(db: Session):
    return db.query(User).filter(
        User.is_active == True,
        User.role.notin_(["system_admin", "score_admin"]),
        User.payment_status == "approved"
    )


def _missing_prediction_counts(db: Session, matches: list[Match]) -> dict[int, int]:
    total_participants = _participant_query(db).count()
    counts = {}
    for match in matches:
        predicted_count = db.query(Prediction.user_id).join(User, User.id == Prediction.user_id).filter(
            Prediction.match_id == match.id,
            User.is_active == True,
            User.role.notin_(["system_admin", "score_admin"]),
            User.payment_status == "approved"
        ).distinct().count()
        counts[match.id] = max(0, total_participants - predicted_count)
    return counts


def _reminder_setting_key(kickoff_time: datetime) -> str:
    return f"whatsapp_reminder_sent:{kickoff_time.isoformat()}"


def _mark_reminder_sent(db: Session, kickoff_time: datetime) -> None:
    setting = SystemSetting(
        key=_reminder_setting_key(kickoff_time),
        value=datetime.utcnow().isoformat()
    )
    db.add(setting)
    db.commit()


def send_due_prediction_reminders(db: Session) -> int:
    if not whatsapp_notifications_enabled():
        return 0

    now = datetime.utcnow()
    window_start = now + timedelta(minutes=REMINDER_LEAD_MINUTES)
    window_end = window_start + timedelta(minutes=REMINDER_SCAN_WINDOW_MINUTES)

    kickoff_rows = db.query(Match.kickoff_time).filter(
        Match.kickoff_time >= window_start,
        Match.kickoff_time < window_end,
        Match.status.notin_(["postponed", "cancelled"]),
        Match.score_ft_team1 == None,
        Match.score_ft_team2 == None
    ).distinct().all()

    sent_count = 0
    for (kickoff_time,) in kickoff_rows:
        if db.query(SystemSetting).filter(SystemSetting.key == _reminder_setting_key(kickoff_time)).first():
            continue

        matches = db.query(Match).filter(
            Match.kickoff_time == kickoff_time,
            Match.status.notin_(["postponed", "cancelled"]),
            Match.score_ft_team1 == None,
            Match.score_ft_team2 == None
        ).order_by(Match.id).all()
        if not matches:
            continue

        missing_prediction_counts = _missing_prediction_counts(db, matches)
        if send_whatsapp_message(format_matches_reminder_message(kickoff_time, matches, missing_prediction_counts)):
            _mark_reminder_sent(db, kickoff_time)
            sent_count += 1

    return sent_count


def format_ranking_message(ranking: list[dict]) -> str:
    lines = ["\U0001f3c6 *Ranking atualizado*", "", "*Top 10 geral*"]
    if not ranking:
        lines.append("Ainda não há participantes no ranking.")
        return "\n".join(lines)

    medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
    for row in ranking[:10]:
        position = row["position"]
        prefix = medals.get(position, f"{position}.")
        position_change = row.get("position_change")
        movement = ""
        if position_change:
            if position_change > 0:
                movement = f" \U0001f7e2\u2b06\ufe0f{position_change}"
            else:
                movement = f" \U0001f534\u2b07\ufe0f{abs(position_change)}"
        lines.append(
            f"{prefix} *{row['display_name']}*{movement} - {row['total_points']} pts"
        )
    return "\n".join(lines)


def send_general_ranking_notification(db: Session) -> bool:
    if not whatsapp_notifications_enabled():
        return False
    ranking = get_rankings(db)
    return send_whatsapp_message(format_ranking_message(ranking))


def send_match_start_notification(db: Session, match: Match):
    if not whatsapp_notifications_enabled():
        return
    enabled_setting = db.query(SystemSetting).filter(SystemSetting.key == "whatsapp_match_start_enabled").first()
    enabled = enabled_setting.value.lower() in {"1", "true", "yes", "on"} if enabled_setting else True
    if not enabled:
        return
    
    template_setting = db.query(SystemSetting).filter(SystemSetting.key == "whatsapp_match_start_template").first()
    template = template_setting.value if template_setting else "🎬 Bola rolando! {{match}} começou!"
    
    flag1 = match.team1.flag_icon or ""
    flag2 = match.team2.flag_icon or ""
    match_str = f"{match.team1_name} {flag1} x {flag2} {match.team2_name}"
    
    msg = template.replace("{{match}}", match_str)
    send_whatsapp_message(msg)


def send_match_goal_notification(db: Session, match: Match, score1: int, score2: int):
    if not whatsapp_notifications_enabled():
        return
    enabled_setting = db.query(SystemSetting).filter(SystemSetting.key == "whatsapp_match_goal_enabled").first()
    enabled = enabled_setting.value.lower() in {"1", "true", "yes", "on"} if enabled_setting else True
    if not enabled:
        return
        
    template_setting = db.query(SystemSetting).filter(SystemSetting.key == "whatsapp_match_goal_template").first()
    template = template_setting.value if template_setting else "⚽ GOL! {{score}}"
    
    code1 = match.team1.fifa_code or match.team1_name[:3].upper()
    flag1 = match.team1.flag_icon or ""
    code2 = match.team2.fifa_code or match.team2_name[:3].upper()
    flag2 = match.team2.flag_icon or ""
    score_str = f"{code1} {flag1}{score1} X {score2} {flag2}{code2}"
    
    msg = template.replace("{{score}}", score_str)
    send_whatsapp_message(msg)


def send_match_end_notification(db: Session, match: Match, score1: int, score2: int):
    if not whatsapp_notifications_enabled():
        return
    enabled_setting = db.query(SystemSetting).filter(SystemSetting.key == "whatsapp_match_end_enabled").first()
    enabled = enabled_setting.value.lower() in {"1", "true", "yes", "on"} if enabled_setting else True
    if not enabled:
        return
        
    template_setting = db.query(SystemSetting).filter(SystemSetting.key == "whatsapp_match_end_template").first()
    template = template_setting.value if template_setting else "🏁 Fim de papo! {{match}} finalizado. Placar: {{score}}"
    
    flag1 = match.team1.flag_icon or ""
    flag2 = match.team2.flag_icon or ""
    match_str = f"{match.team1_name} {flag1} x {flag2} {match.team2_name}"
    
    code1 = match.team1.fifa_code or match.team1_name[:3].upper()
    flag1 = match.team1.flag_icon or ""
    code2 = match.team2.fifa_code or match.team2_name[:3].upper()
    flag2 = match.team2.flag_icon or ""
    score_str = f"{code1} {flag1}{score1} X {score2} {flag2}{code2}"
    
    msg = template.replace("{{match}}", match_str).replace("{{score}}", score_str)
    send_whatsapp_message(msg)
