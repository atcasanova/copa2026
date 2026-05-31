import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JWT_SECRET"] = "test_secret_key"
os.environ["TESTING"] = "true"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db import Base, get_db
from app.main import app
from app.auth import get_password_hash
from app.models import User, Match, Team, Stadium, StageMultiplier

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    # Create tables
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    
    # Preseed multipliers
    stages = ["Group Stage", "Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Final"]
    for s in stages:
        m = StageMultiplier(stage=s, multiplier=1.0)
        session.add(m)
    session.commit()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def test_users(db_session):
    users = []
    # 1. Admin
    admin = User(
        username="admin_user",
        email="admin@test.com",
        display_name="Admin Teste",
        hashed_password=get_password_hash("password"),
        role="system_admin"
    )
    db_session.add(admin)
    
    # 2. Score Admin
    score_admin = User(
        username="score_admin_user",
        email="scoreadmin@test.com",
        display_name="Score Admin Teste",
        hashed_password=get_password_hash("password"),
        role="score_admin"
    )
    db_session.add(score_admin)

    # 3. Participant 1
    p1 = User(
        username="p1_user",
        email="p1@test.com",
        display_name="Ana",
        hashed_password=get_password_hash("password"),
        role="participant",
        payment_status="approved"
    )
    db_session.add(p1)

    # 4. Participant 2
    p2 = User(
        username="p2_user",
        email="p2@test.com",
        display_name="Bruno",
        hashed_password=get_password_hash("password"),
        role="participant",
        payment_status="approved"
    )
    db_session.add(p2)

    db_session.commit()
    return [admin, score_admin, p1, p2]
