from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from .models import Match, SystemSetting

PREDICTION_LOCK_HOURS_KEY = "prediction_lock_hours"
DEFAULT_PREDICTION_LOCK_HOURS = 3
MAX_PREDICTION_LOCK_HOURS = 168


def get_prediction_lock_hours(db: Session) -> int:
    setting = db.query(SystemSetting).filter(SystemSetting.key == PREDICTION_LOCK_HOURS_KEY).first()
    if not setting:
        return DEFAULT_PREDICTION_LOCK_HOURS

    try:
        hours = int(setting.value)
    except (TypeError, ValueError):
        return DEFAULT_PREDICTION_LOCK_HOURS

    if hours < 0 or hours > MAX_PREDICTION_LOCK_HOURS:
        return DEFAULT_PREDICTION_LOCK_HOURS
    return hours


def set_prediction_lock_hours(db: Session, hours: int) -> SystemSetting:
    setting = db.query(SystemSetting).filter(SystemSetting.key == PREDICTION_LOCK_HOURS_KEY).first()
    if not setting:
        setting = SystemSetting(key=PREDICTION_LOCK_HOURS_KEY, value=str(hours))
        db.add(setting)
    else:
        setting.value = str(hours)
        setting.updated_at = datetime.utcnow()
    return setting


def get_prediction_lock_delta(db: Session) -> timedelta:
    return timedelta(hours=get_prediction_lock_hours(db))


def get_locked_match_cutoff(db: Session, now_utc: datetime | None = None) -> datetime:
    if now_utc is None:
        now_utc = datetime.utcnow()
    return now_utc + get_prediction_lock_delta(db)


def is_match_locked_for_predictions(db: Session, match: Match, now_utc: datetime | None = None) -> bool:
    if now_utc is None:
        now_utc = datetime.utcnow()
    return now_utc >= match.kickoff_time - get_prediction_lock_delta(db)


def calculate_prizepool(total_collected: float, entry_fee: float, winners_count: int) -> list[dict]:
    """
    Calculates the prizepool distribution based on the number of configured winners (3, 5, or 7).
    Returns a list of dicts with:
      {"position": int, "value": float, "label": str}
    """
    if winners_count == 5:
        distribution = [
            {"position": 1, "percent": 0.45, "label": "🥇 1º lugar (45%)"},
            {"position": 2, "percent": 0.25, "label": "🥈 2º lugar (25%)"},
            {"position": 3, "percent": 0.15, "label": "🥉 3º lugar (15%)"},
            {"position": 4, "percent": 0.10, "label": "4º lugar (10%)"},
            {"position": 5, "percent": 0.05, "label": "5º lugar (5%)"},
        ]
        prizes = []
        for dist in distribution:
            prizes.append({
                "position": dist["position"],
                "value": total_collected * dist["percent"],
                "label": dist["label"]
            })
        return prizes

    elif winners_count == 7:
        seventh_prize = min(entry_fee, total_collected)
        remaining = max(0.0, total_collected - seventh_prize)
        distribution = [
            {"position": 1, "percent": 0.30, "label": "🥇 1º lugar (30%)"},
            {"position": 2, "percent": 0.20, "label": "🥈 2º lugar (20%)"},
            {"position": 3, "percent": 0.15, "label": "🥉 3º lugar (15%)"},
            {"position": 4, "percent": 0.12, "label": "4º lugar (12%)"},
            {"position": 5, "percent": 0.10, "label": "5º lugar (10%)"},
            {"position": 6, "percent": 0.08, "label": "6º lugar (8%)"},
        ]
        prizes = []
        for dist in distribution:
            prizes.append({
                "position": dist["position"],
                "value": remaining * (dist["percent"] / 0.95),
                "label": dist["label"]
            })
        prizes.append({
            "position": 7,
            "value": seventh_prize,
            "label": "7º lugar (Valor de 1 inscrição)"
        })
        return prizes

    else:  # Default to 3
        distribution = [
            {"position": 1, "percent": 0.50, "label": "🥇 1º lugar (50%)"},
            {"position": 2, "percent": 0.30, "label": "🥈 2º lugar (30%)"},
            {"position": 3, "percent": 0.20, "label": "🥉 3º lugar (20%)"},
        ]
        prizes = []
        for dist in distribution:
            prizes.append({
                "position": dist["position"],
                "value": total_collected * dist["percent"],
                "label": dist["label"]
            })
        return prizes
