from apscheduler.schedulers.background import BackgroundScheduler
from .sync import sync_openfootball_data
from .db import SessionLocal
from .notifications import send_due_prediction_reminders
from .football_data import sync_finished_scores_from_football_data, sync_fixtures_from_football_data
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bolao_scheduler")

def scheduled_sync_job():
    db = SessionLocal()
    try:
        logger.info("[Scheduler] Iniciando job diário de sincronização (01:00 AM)...")
        msg, requires_review, results = sync_openfootball_data(db)
        logger.info(f"[Scheduler] Sincronização concluída: {msg}")
    except Exception as e:
        logger.error(f"[Scheduler] Falha na execução da sincronização agendada: {str(e)}")
    finally:
        db.close()

def scheduled_prediction_reminders_job():
    db = SessionLocal()
    try:
        sent_count = send_due_prediction_reminders(db)
        if sent_count:
            logger.info(f"[Scheduler] Lembretes de palpites enviados: {sent_count}")
    except Exception as e:
        logger.error(f"[Scheduler] Falha ao enviar lembretes de palpites: {str(e)}")
    finally:
        db.close()

def scheduled_football_data_scores_job():
    db = SessionLocal()
    try:
        result = sync_finished_scores_from_football_data(db, trigger="scheduled")
        if result.get("updated_matches") or result.get("errors"):
            logger.info(f"[Scheduler] Consulta football-data.org concluída: {result}")
    except Exception as e:
        logger.error(f"[Scheduler] Falha ao consultar placares do football-data.org: {str(e)}")
    finally:
        db.close()

def scheduled_football_data_fixtures_job():
    db = SessionLocal()
    try:
        result = sync_fixtures_from_football_data(db, trigger="scheduled")
        if result.get("updated_matches") or result.get("errors"):
            logger.info(f"[Scheduler] Sincronização de confrontos (football-data.org) concluída: {result}")
    except Exception as e:
        logger.error(f"[Scheduler] Falha ao sincronizar confrontos do football-data.org: {str(e)}")
    finally:
        db.close()

def openfootball_daily_sync_enabled():
    return os.getenv("OPENFOOTBALL_DAILY_SYNC_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    if openfootball_daily_sync_enabled():
        scheduler.add_job(
            scheduled_sync_job,
            'cron',
            hour=1,
            minute=0,
            id='daily_sync_job',
            replace_existing=True
        )
    else:
        logger.info("[Scheduler] Sincronização diária openfootball desabilitada por configuração.")
    scheduler.add_job(
        scheduled_prediction_reminders_job,
        'interval',
        minutes=5,
        id='prediction_reminders_job',
        replace_existing=True,
        next_run_time=datetime.now(ZoneInfo("America/Sao_Paulo"))
    )
    scheduler.add_job(
        scheduled_football_data_scores_job,
        'interval',
        minutes=1,
        id='football_data_scores_job',
        replace_existing=True,
        next_run_time=datetime.now(ZoneInfo("America/Sao_Paulo"))
    )
    scheduler.add_job(
        scheduled_football_data_fixtures_job,
        'interval',
        minutes=15,
        id='football_data_fixtures_job',
        replace_existing=True,
        next_run_time=datetime.now(ZoneInfo("America/Sao_Paulo"))
    )
    scheduler.start()
    logger.info("[Scheduler] APScheduler iniciado com lembretes e consulta automática de placares.")
