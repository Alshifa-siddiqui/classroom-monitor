from datetime import datetime
from typing import Optional, List, Dict

from pydantic import BaseModel, Field, ConfigDict


class StartSessionRequest(BaseModel):
    name: str = Field(default="Session", min_length=1, max_length=120)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    started_at: datetime
    ended_at: Optional[datetime] = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class StudentDetailOut(BaseModel):
    id: int
    student_code: Optional[str] = None
    name: str
    email: Optional[str] = None
    registered_at: Optional[datetime] = None
    embedding_count: int
    enrolled: bool
    has_account: bool = False


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^<>{}]+$")
    # optional login account for the student portal
    email: Optional[str] = Field(default=None, min_length=5, max_length=120,
                                 pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9.-]+$")
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)


class StudentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^<>{}]+$")


class EnrollResult(BaseModel):
    student_id: int
    name: str
    samples_captured: int
    quality: float  # mean pairwise similarity of captured samples


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    token: str
    username: str
    role: str
    expires_in: int
    student_id: Optional[int] = None


class UserCreate(BaseModel):
    # allows plain usernames and email addresses
    username: str = Field(min_length=3, max_length=60,
                          pattern=r"^[a-zA-Z0-9_.@+-]+$")
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(pattern=r"^(admin|teacher|viewer)$")


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=60,
                          pattern=r"^[a-zA-Z0-9_.@+-]+$")
    password: str = Field(min_length=8, max_length=200)
    # optional: matching ADMIN_SIGNUP_CODE creates an admin instead of viewer
    admin_code: Optional[str] = Field(default=None, max_length=100)


class UserRoleUpdate(BaseModel):
    role: str = Field(pattern=r"^(admin|teacher|viewer)$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    created_at: datetime


class TrendPoint(BaseModel):
    bucket: str
    value: float


class EmotionTrendPoint(BaseModel):
    bucket: str
    counts: Dict[str, int]


class TrendsOut(BaseModel):
    attendance: List[TrendPoint]       # distinct students present per bucket
    attention: List[TrendPoint]        # average attention per bucket
    emotions: List[EmotionTrendPoint]
    peak_attendance: Optional[TrendPoint] = None
    most_distracted: Optional[TrendPoint] = None


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    student_id: int
    session_id: int
    timestamp_in: datetime
    timestamp_out: Optional[datetime] = None
    duration: Optional[int] = None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    student_id: Optional[int] = None
    session_id: Optional[int] = None
    message: str
    timestamp: datetime


class AttentionPoint(BaseModel):
    timestamp: datetime
    avg_score: float


class AnalyticsOut(BaseModel):
    session_id: Optional[int]
    present_count: int
    total_students: int
    avg_attention: float
    attention_timeline: List[AttentionPoint]
    emotion_distribution: Dict[str, int]
    alerts: List[AlertOut]
