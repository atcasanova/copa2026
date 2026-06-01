from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

# User Schemas
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    display_name: str = Field(..., min_length=2, max_length=100)

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=2, max_length=100)
    avatar_url: Optional[str] = None
    notification_preferences: Optional[Dict[str, bool]] = None
    password: Optional[str] = Field(None, min_length=6)
    pix_key_receive: Optional[str] = None

class UserResponse(UserBase):
    id: UUID
    role: str
    avatar_url: Optional[str] = None
    notification_preferences: Dict[str, bool]
    is_active: bool
    created_at: datetime
    pix_key_receive: Optional[str] = None
    payment_status: str
    payment_proof_filename: Optional[str] = None
    payment_rejected_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class UserPublicResponse(BaseModel):
    id: UUID
    username: str
    display_name: str
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=20)
    password: str = Field(..., min_length=6)

# Team Schemas
class TeamResponse(BaseModel):
    name: str
    fifa_code: Optional[str] = None
    group_name: str
    continent: Optional[str] = None
    flag_icon: Optional[str] = None
    confed: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Stadium Schemas
class StadiumResponse(BaseModel):
    name: str
    city: str
    capacity: Optional[int] = None
    timezone: str
    coords: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Match Schemas
class MatchResponse(BaseModel):
    id: int
    round: str
    stage: str
    group_name: Optional[str] = None
    date: str
    time_str: str
    kickoff_time: datetime
    team1_name: str
    team2_name: str
    ground: str
    status: str
    score_ft_team1: Optional[int] = None
    score_ft_team2: Optional[int] = None
    score_et_team1: Optional[int] = None
    score_et_team2: Optional[int] = None
    score_pen_team1: Optional[int] = None
    score_pen_team2: Optional[int] = None
    score_confirmed_by_admin: bool
    team1: Optional[TeamResponse] = None
    team2: Optional[TeamResponse] = None
    stadium: Optional[StadiumResponse] = None

    model_config = ConfigDict(from_attributes=True)

class MatchScoreUpdate(BaseModel):
    match_id: int
    score_ft_team1: int = Field(..., ge=0)
    score_ft_team2: int = Field(..., ge=0)
    score_et_team1: Optional[int] = Field(None, ge=0)
    score_et_team2: Optional[int] = Field(None, ge=0)
    score_pen_team1: Optional[int] = Field(None, ge=0)
    score_pen_team2: Optional[int] = Field(None, ge=0)

class MatchScoreBatchUpdate(BaseModel):
    scores: List[MatchScoreUpdate] = Field(..., min_length=1, max_length=20)

# Prediction Schemas
class PredictionCreate(BaseModel):
    goals_team1: int = Field(..., ge=0)
    goals_team2: int = Field(..., ge=0)
    qualified_team_name: Optional[str] = None

class PredictionResponse(BaseModel):
    id: int
    match_id: int
    user_id: UUID
    goals_team1: int
    goals_team2: int
    qualified_team_name: Optional[str] = None
    points_earned: Optional[int] = None
    base_points: Optional[int] = None
    multiplier_used: Optional[float] = None
    scoring_explanation: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    match: Optional[MatchResponse] = None

    model_config = ConfigDict(from_attributes=True)

class PredictionBulkUpdate(BaseModel):
    match_id: int
    goals_team1: int = Field(..., ge=0)
    goals_team2: int = Field(..., ge=0)
    qualified_team_name: Optional[str] = None

class MatchPredictionVisibilityEntry(BaseModel):
    user_id: UUID
    display_name: str
    avatar_url: Optional[str] = None
    created_at: datetime
    goals_team1: Optional[int] = None
    goals_team2: Optional[int] = None
    qualified_team_name: Optional[str] = None

class MatchPredictionVisibilityResponse(BaseModel):
    match_id: int
    is_locked: bool
    total_predictions: int
    entries: List[MatchPredictionVisibilityEntry]

# Group Schemas
class GroupCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_private: bool = False

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_private: Optional[bool] = None

class GroupMemberResponse(BaseModel):
    id: int
    group_id: UUID
    user_id: UUID
    role: str
    is_approved: bool
    created_at: datetime
    user: UserPublicResponse

    model_config = ConfigDict(from_attributes=True)

class GroupResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    owner_id: UUID
    is_private: bool
    created_at: datetime
    owner: Optional[UserPublicResponse] = None

    model_config = ConfigDict(from_attributes=True)

class GroupDetailResponse(GroupResponse):
    invite_code: Optional[str] = None

# Group Invitation Schemas
class GroupInvitationCreate(BaseModel):
    invitee_identifier: str  # Can be username or email

class GroupInvitationResponse(BaseModel):
    id: UUID
    group_id: UUID
    invited_by_id: UUID
    invitee_id: Optional[UUID] = None
    invitee_email: Optional[str] = None
    status: str
    created_at: datetime
    group: GroupResponse
    invited_by: UserPublicResponse
    invitee: Optional[UserPublicResponse] = None

    model_config = ConfigDict(from_attributes=True)

# Ranking Row Schema
class RankingRowResponse(BaseModel):
    position: int
    user_id: UUID
    display_name: str
    avatar_url: Optional[str] = None
    total_points: int
    exact_scores_count: int
    correct_results_count: int
    predictions_count: int
    missing_predictions_count: int
    registration_date: datetime

# Stage Multiplier Schemas
class StageMultiplierResponse(BaseModel):
    stage: str
    multiplier: float
    updated_at: datetime
    updated_by_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)

class StageMultiplierUpdate(BaseModel):
    multiplier: float = Field(..., gt=0.0)
    reason: Optional[str] = Field(None, max_length=200)

class MultiplierHistoryResponse(BaseModel):
    id: int
    stage: str
    old_multiplier: float
    new_multiplier: float
    updated_by_id: UUID
    timestamp: datetime
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Announcement Schemas
class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    body: str = Field(..., min_length=10)
    priority: str = Field("low", pattern="^(low|medium|high)$")
    target_type: str = Field("global", pattern="^(global|group)$")
    target_group_id: Optional[UUID] = None
    expiration_date: Optional[datetime] = None

class AnnouncementResponse(BaseModel):
    id: UUID
    title: str
    body: str
    priority: str
    target_type: str
    target_group_id: Optional[UUID] = None
    publication_date: datetime
    expiration_date: Optional[datetime] = None
    created_at: datetime
    is_read: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)

# Audit Log Schemas
class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[UUID] = None
    action: str
    timestamp: datetime
    target_type: str
    target_id: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    reason: Optional[str] = None
    user: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)

# Sync Schemas
class SyncMatchDiffResponse(BaseModel):
    id: int
    sync_log_id: int
    match_id: int
    previous_value: Dict[str, Any]
    new_value: Dict[str, Any]
    status: str

    model_config = ConfigDict(from_attributes=True)

class SyncLogResponse(BaseModel):
    id: int
    source_url: str
    timestamp: datetime
    source_hash: str
    status: str
    details: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class AuditBlockResponse(BaseModel):
    id: int
    match_id: int
    block_number: int
    payload: List[Dict[str, Any]]
    previous_hash: str
    hash: str
    created_at: datetime
    match: Optional[MatchResponse] = None

    model_config = ConfigDict(from_attributes=True)


# Pix Config Schemas
class PixConfigBase(BaseModel):
    pix_key: Optional[str] = None
    merchant_name: Optional[str] = None
    merchant_city: Optional[str] = None
    entry_fee: float = 0.0

class PixConfigResponse(PixConfigBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class PixConfigUpdate(PixConfigBase):
    pass


class SystemInvitationCreate(BaseModel):
    email: EmailStr

class SystemInvitationResponse(BaseModel):
    id: UUID
    email: str
    code: str
    is_used: bool
    used_by_id: Optional[UUID] = None
    created_at: datetime
    used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
