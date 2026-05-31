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
