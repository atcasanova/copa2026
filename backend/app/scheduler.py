from apscheduler.schedulers.background import BackgroundScheduler
from .sync import sync_openfootball_data
from .db import SessionLocal
from .notifications import send_due_prediction_reminders
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

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

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    # Agenda a execução diária às 01:00 AM no fuso horário America/Sao_Paulo
    scheduler.add_job(
        scheduled_sync_job,
        'cron',
        hour=1,
        minute=0,
        id='daily_sync_job',
        replace_existing=True
    )
    scheduler.add_job(
        scheduled_prediction_reminders_job,
        'interval',
        minutes=5,
        id='prediction_reminders_job',
        replace_existing=True,
        next_run_time=datetime.now(ZoneInfo("America/Sao_Paulo"))
    )
    scheduler.start()
    logger.info("[Scheduler] APScheduler iniciado com sincronização diária e lembretes de palpites a cada 5 minutos.")
