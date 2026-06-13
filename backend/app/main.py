import os
import httpx
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import logging

from .db import engine, Base, SessionLocal
from .models import User, StageMultiplier, PixConfig, SystemSetting
from .auth import get_password_hash
from .settings import DEFAULT_PREDICTION_LOCK_HOURS, PREDICTION_LOCK_HOURS_KEY
from .routers import auth, matches, predictions, rankings, groups, announcements, admin, audit, payments
from .sync import seed_initial_data
from .scheduler import start_scheduler
from .scoring import DEFAULT_MULTIPLIERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bolao_main")

app = FastAPI(
    title="Bolão Copa do Mundo 2026 API",
    description="Backend para o bolão de palpites da Copa do Mundo FIFA 2026",
    version="1.0.0"
)

# Configure CORS
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(matches.router)
app.include_router(predictions.router)
app.include_router(rankings.router)
app.include_router(groups.router)
app.include_router(announcements.router)
app.include_router(admin.router)
app.include_router(audit.router)
app.include_router(payments.router)

@app.on_event("startup")
def on_startup():
    logger.info("Executando tarefas de inicialização...")
    
    # 1. Automatic table creation (safe schema migration)
    logger.info("Criando tabelas no banco de dados...")
    Base.metadata.create_all(bind=engine)
    
    # Ensure uploads directory exists
    os.makedirs("/app/uploads", exist_ok=True)
    
    db = SessionLocal()
    try:
        from sqlalchemy import text
        if db.bind.dialect.name != "sqlite":
            cols_to_add = [
                ("pix_key_receive", "VARCHAR", "NULL"),
                ("payment_status", "VARCHAR", "NOT NULL DEFAULT 'pending'"),
                ("payment_proof_filename", "VARCHAR", "NULL"),
                ("payment_rejected_reason", "VARCHAR", "NULL")
            ]
            for col_name, col_type, col_constraints in cols_to_add:
                res = db.execute(text(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name='users' AND column_name='{col_name}'"
                )).fetchone()
                if not res:
                    logger.info(f"Adicionando coluna {col_name} na tabela 'users'...")
                    db.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type} {col_constraints}"))
                    db.commit()

            # Ensure prizepool_winners column exists in pix_configs
            res_pix = db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='pix_configs' AND column_name='prizepool_winners'"
            )).fetchone()
            if not res_pix:
                logger.info("Adicionando coluna prizepool_winners na tabela 'pix_configs'...")
                db.execute(text("ALTER TABLE pix_configs ADD COLUMN prizepool_winners INTEGER NOT NULL DEFAULT 3"))
                db.commit()

            # Ensure live_minute column exists in matches
            res_matches = db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='matches' AND column_name='live_minute'"
            )).fetchone()
            if not res_matches:
                logger.info("Adicionando coluna live_minute na tabela 'matches'...")
                db.execute(text("ALTER TABLE matches ADD COLUMN live_minute VARCHAR NULL"))
                db.commit()
                
        # Ensure default PixConfig row exists
        existing_pix = db.query(PixConfig).filter(PixConfig.id == 1).first()
        if not existing_pix:
            logger.info("Criando registro inicial de configuração do Pix...")
            default_pix = PixConfig(id=1, entry_fee=0.0)
            db.add(default_pix)
            db.commit()

        lock_setting = db.query(SystemSetting).filter(SystemSetting.key == PREDICTION_LOCK_HOURS_KEY).first()
        if not lock_setting:
            logger.info("Criando configuração padrão de bloqueio de palpites...")
            db.add(SystemSetting(key=PREDICTION_LOCK_HOURS_KEY, value=str(DEFAULT_PREDICTION_LOCK_HOURS)))
            db.commit()
    except Exception as e:
        logger.error(f"Erro ao inicializar dados/colunas de pagamento: {str(e)}")
        db.rollback()
    try:
        # 2. Preseed Stage Multipliers
        logger.info("Verificando multiplicadores de fase...")
        for stage, default_val in DEFAULT_MULTIPLIERS.items():
            existing = db.query(StageMultiplier).filter(StageMultiplier.stage == stage).first()
            if not existing:
                mult = StageMultiplier(
                    stage=stage,
                    multiplier=default_val
                )
                db.add(mult)
        db.commit()

        # 3. Bootstrap initial Admin User
        enable_bootstrap = os.getenv("ENABLE_ADMIN_BOOTSTRAP", "false").lower() == "true"
        if enable_bootstrap:
            admin_username = os.getenv("ADMIN_BOOTSTRAP_USERNAME")
            admin_email = os.getenv("ADMIN_BOOTSTRAP_EMAIL")
            admin_password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
            
            if not admin_username or not admin_email or not admin_password:
                raise RuntimeError("ADMIN_BOOTSTRAP_USERNAME, ADMIN_BOOTSTRAP_EMAIL, and ADMIN_BOOTSTRAP_PASSWORD are required when ENABLE_ADMIN_BOOTSTRAP is true")
                
            logger.info(f"Verificando usuário administrador padrão ({admin_username})...")
            existing_admin = db.query(User).filter(User.username == admin_username).first()
            if not existing_admin:
                hashed_pwd = get_password_hash(admin_password)
                bootstrap_admin = User(
                    username=admin_username,
                    email=admin_email,
                    display_name="Administrador do Sistema",
                    hashed_password=hashed_pwd,
                    role="system_admin",
                    notification_preferences={"email": True, "in_app": True},
                    is_active=True
                )
                db.add(bootstrap_admin)
                db.commit()
                logger.info("Usuário administrador padrão criado com sucesso.")
            else:
                logger.info("Usuário administrador padrão já existe.")
        else:
            logger.info("Bootstrap de administrador desativado (ENABLE_ADMIN_BOOTSTRAP=false ou não definido).")

        # 4. Run initial data seed (Teams, Stadiums, Matches) from openfootball URLs
        if os.getenv("TESTING", "false").lower() != "true":
            logger.info("Executando importação inicial de dados (Times, Estádios e Partidas)...")
            seed_result = seed_initial_data(db)
            logger.info(f"Resultado do seeding: {seed_result}")

            # 5. Start Daily Synchronization APScheduler
            logger.info("Iniciando agendador de tarefas em segundo plano...")
            start_scheduler()
        else:
            logger.info("Sementes de dados e agendador pulados no ambiente de testes (TESTING=true).")
        
        # Clear ranking cache on startup to avoid stale standing pages
        from .scoring import invalidate_ranking_cache
        invalidate_ranking_cache(db)
        
    except Exception as e:
        logger.error(f"Erro crítico durante a inicialização: {str(e)}")
    finally:
        db.close()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "Bolão Copa do Mundo 2026",
        "version": "1.0.0",
        "documentation": "/docs"
    }

@app.get("/api/proxy-image")
async def proxy_image(url: str):
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")
    
    # 1. SSRF prevention: Validate hostname and check that IP is not loopback/private/link-local
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise HTTPException(status_code=400, detail="Invalid hostname")
        
        # Resolve hostname to check IPs
        ips = socket.getaddrinfo(hostname, None)
        for ip_info in ips:
            ip_str = ip_info[4][0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast:
                raise HTTPException(status_code=403, detail="Access to private/local networks is forbidden")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to validate URL: {str(e)}")

    # 2. Resource exhaustion & Content-type validation
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, timeout=5.0, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail="Failed to fetch image")
                
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    raise HTTPException(status_code=400, detail="URL does not point to an image")
                
                # Check content length header if present (limit to 5MB)
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > 5 * 1024 * 1024:
                            raise HTTPException(status_code=400, detail="Image size exceeds 5MB limit")
                    except ValueError:
                        pass
                
                # Stream the content in chunks to enforce size limit dynamically
                chunks = []
                bytes_downloaded = 0
                async for chunk in response.aiter_bytes():
                    bytes_downloaded += len(chunk)
                    if bytes_downloaded > 5 * 1024 * 1024:
                        raise HTTPException(status_code=400, detail="Image size exceeds 5MB limit")
                    chunks.append(chunk)
                
                return Response(
                    content=b"".join(chunks),
                    media_type=content_type,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=86400"
                    }
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying image {url}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to proxy image: {str(e)}")
