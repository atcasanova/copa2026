import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, JSON, Numeric, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    external_provider = Column(String, nullable=True)
    external_subject = Column(String, nullable=True)
    role = Column(String, default="participant", nullable=False)  # participant, group_admin, score_admin, system_admin
    notification_preferences = Column(JSON, default=lambda: {"email": True, "in_app": True}, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Payment fields
    pix_key_receive = Column(String, nullable=True)
    payment_status = Column(String, default="pending", nullable=False)  # pending, submitted, approved, rejected
    payment_proof_filename = Column(String, nullable=True)
    payment_rejected_reason = Column(String, nullable=True)


    predictions = relationship("Prediction", back_populates="user", cascade="all, delete-orphan")
    owned_groups = relationship("Group", back_populates="owner")
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    sent_invitations = relationship("GroupInvitation", foreign_keys="[GroupInvitation.invited_by_id]", back_populates="invited_by")
    received_invitations = relationship("GroupInvitation", foreign_keys="[GroupInvitation.invitee_id]", back_populates="invitee")

class Team(Base):
    __tablename__ = "teams"

    name = Column(String, primary_key=True)
    fifa_code = Column(String, unique=True, nullable=True)
    group_name = Column(String, nullable=False)  # e.g., "A", "B"
    continent = Column(String, nullable=True)
    flag_icon = Column(String, nullable=True)
    confed = Column(String, nullable=True)

class Stadium(Base):
    __tablename__ = "stadiums"

    name = Column(String, primary_key=True)
    city = Column(String, nullable=False)
    capacity = Column(Integer, nullable=True)
    timezone = Column(String, nullable=False)
    coords = Column(String, nullable=True)

class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    round = Column(String, nullable=False)  # Matchday 1, Round of 16, etc.
    stage = Column(String, nullable=False)  # Group Stage, Round of 32, etc.
    group_name = Column(String, nullable=True)  # Group A, etc.
    date = Column(String, nullable=False)  # e.g. "2026-06-11"
    time_str = Column(String, nullable=False)  # e.g. "13:00 UTC-6"
    kickoff_time = Column(DateTime, nullable=False, index=True)  # UTC kickoff datetime
    team1_name = Column(String, ForeignKey("teams.name"), nullable=False)
    team2_name = Column(String, ForeignKey("teams.name"), nullable=False)
    ground = Column(String, ForeignKey("stadiums.name"), nullable=False)
    
    # Status: scheduled, locked, live, finished, score_pending_review, score_confirmed, postponed, cancelled
    status = Column(String, default="scheduled", nullable=False)
    
    score_ft_team1 = Column(Integer, nullable=True)
    score_ft_team2 = Column(Integer, nullable=True)
    score_et_team1 = Column(Integer, nullable=True)
    score_et_team2 = Column(Integer, nullable=True)
    score_pen_team1 = Column(Integer, nullable=True)
    score_pen_team2 = Column(Integer, nullable=True)
    score_confirmed_by_admin = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    team1 = relationship("Team", foreign_keys=[team1_name])
    team2 = relationship("Team", foreign_keys=[team2_name])
    stadium = relationship("Stadium", foreign_keys=[ground])
    predictions = relationship("Prediction", back_populates="match", cascade="all, delete-orphan")

class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("match_id", "user_id", name="uq_match_user_prediction"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    goals_team1 = Column(Integer, nullable=False)
    goals_team2 = Column(Integer, nullable=False)
    qualified_team_name = Column(String, nullable=True)  # Team predicted to qualify in case of knockout draw
    
    points_earned = Column(Integer, nullable=True)
    base_points = Column(Integer, nullable=True)
    multiplier_used = Column(Numeric(precision=3, scale=1), nullable=True)
    scoring_explanation = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    match = relationship("Match", back_populates="predictions")
    user = relationship("User", back_populates="predictions")

class Group(Base):
    __tablename__ = "groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    invite_code = Column(String, unique=True, nullable=False)
    is_private = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="owned_groups")
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    invitations = relationship("GroupInvitation", back_populates="group", cascade="all, delete-orphan")

class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_user_member"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String, default="member", nullable=False)  # owner, admin, member
    is_approved = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")

class GroupInvitation(Base):
    __tablename__ = "group_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False)
    invited_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    invitee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invitee_email = Column(String, nullable=True)
    status = Column(String, default="pending", nullable=False)  # pending, accepted, declined
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    group = relationship("Group", back_populates="invitations")
    invited_by = relationship("User", foreign_keys=[invited_by_id], back_populates="sent_invitations")
    invitee = relationship("User", foreign_keys=[invitee_id], back_populates="received_invitations")

class StageMultiplier(Base):
    __tablename__ = "stage_multipliers"

    stage = Column(String, primary_key=True)  # Group Stage, Round of 32, Round of 16, Quarter-finals, Semi-finals, Final
    multiplier = Column(Numeric(precision=3, scale=1), default=1.0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    updated_by = relationship("User")

class MultiplierHistory(Base):
    __tablename__ = "multiplier_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stage = Column(String, nullable=False)
    old_multiplier = Column(Numeric(precision=3, scale=1), nullable=False)
    new_multiplier = Column(Numeric(precision=3, scale=1), nullable=False)
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    reason = Column(String, nullable=True)

    updated_by = relationship("User")

class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    priority = Column(String, default="low", nullable=False)  # low, medium, high
    target_type = Column(String, default="global", nullable=False)  # global, group
    target_group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=True)
    publication_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    expiration_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    group = relationship("Group")

class AnnouncementRead(Base):
    __tablename__ = "announcement_reads"

    announcement_id = Column(UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_url = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    source_hash = Column(String, nullable=False)
    raw_payload = Column(String, nullable=False)  # Raw JSON payload representation
    status = Column(String, nullable=False)  # success, failed
    details = Column(String, nullable=True)

    diffs = relationship("SyncMatchDiff", back_populates="sync_log", cascade="all, delete-orphan")

class SyncMatchDiff(Base):
    __tablename__ = "sync_match_diffs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_log_id = Column(Integer, ForeignKey("sync_logs.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    previous_value = Column(JSON, nullable=False)
    new_value = Column(JSON, nullable=False)
    status = Column(String, default="pending_review", nullable=False)  # applied, pending_review, rejected

    sync_log = relationship("SyncLog", back_populates="diffs")
    match = relationship("Match")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)  # prediction_create, prediction_edit, score_insert, score_confirm, etc.
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    target_type = Column(String, nullable=False)  # prediction, match, user, multiplier, etc.
    target_id = Column(String, nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    reason = Column(String, nullable=True)

    user = relationship("User")

class AuditBlock(Base):
    __tablename__ = "audit_blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, unique=True)
    block_number = Column(Integer, nullable=False, unique=True)
    payload = Column(JSON, nullable=False)  # List of predictions: [{"username": "...", "goals_team1": X, "goals_team2": Y}]
    previous_hash = Column(String(64), nullable=False)
    hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    match = relationship("Match")


class PixConfig(Base):
    __tablename__ = "pix_configs"

    id = Column(Integer, primary_key=True, default=1)
    pix_key = Column(String, nullable=True)
    merchant_name = Column(String, nullable=True)
    merchant_city = Column(String, nullable=True)
    entry_fee = Column(Numeric(10, 2), default=0.0, nullable=False)


class RankingCache(Base):
    __tablename__ = "ranking_caches"

    key = Column(String, primary_key=True)
    data = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SystemInvitation(Base):
    __tablename__ = "system_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    is_used = Column(Boolean, default=False, nullable=False)
    used_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used_at = Column(DateTime, nullable=True)

    used_by = relationship("User", foreign_keys=[used_by_id])


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

