from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


class UserRegister(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["operator", "reviewer"] = "operator"


class UserLogin(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserOut


class SampleCreate(BaseModel):
    fruit_type: str = Field(default="Auto", min_length=1, max_length=60, pattern=r"^[A-Za-z][A-Za-z -]*$")
    variety: str | None = None
    source: str | None = None


class SampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sample_id: str
    fruit_type: str
    variety: str | None = None
    source: str | None = None
    status: str
    created_at: datetime


class InspectionProfileIn(BaseModel):
    approximate_weight_g: float | None = Field(default=None, gt=0, le=100000)
    fruit_count: int = Field(default=1, ge=1, le=500)
    fruit_instance_id: str | None = Field(default=None, max_length=80)
    batch_id: str | None = Field(default=None, max_length=80)
    supplier: str | None = Field(default=None, max_length=120)
    storage_location: str | None = Field(default=None, max_length=120)
    inspection_duration_seconds: int | None = Field(default=None, ge=10, le=3600)
    chamber_purged: bool | None = None


class AssistantQuestionIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)

    @model_validator(mode="after")
    def normalize_question(self):
        self.question = " ".join(self.question.strip().split())
        if len(self.question) < 2:
            raise ValueError("Question is too short")
        return self


class SensorIn(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    sample_id: str | None = None
    device_id: str = Field(default="ESP32_01", min_length=1, max_length=80)
    source: Literal["hardware", "simulator"] = "hardware"
    temperature: float | None = Field(default=None, ge=0, le=50)
    humidity: float | None = Field(default=None, ge=0, le=100)
    mq135_raw: float | None = Field(default=None, ge=0, le=4095)
    moisture: float | None = Field(default=None, ge=0, le=100)
    gas_ppm: float | None = Field(default=None, ge=0)
    voc_index: float | None = Field(default=None, ge=0)
    rssi: float | None = None
    uptime_ms: float | None = None
    extra_metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identify_test_data(self):
        if self.device_id.upper().startswith(("SIM", "TEST")) or self.extra_metrics.get("source") == "simulator":
            self.source = "simulator"
        return self


class VerificationIn(BaseModel):
    action: Literal["accept", "incorrect", "ground_truth", "override"]
    ground_truth: Literal["fresh", "ripe", "overripe", "spoiled"] | None = None
    notes: str = Field(default="", max_length=2000)
    reviewer: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def require_label(self):
        if self.action in {"ground_truth", "override"} and self.ground_truth is None:
            raise ValueError("Choose a FreshFusion ground-truth label")
        if self.action == "override" and len(self.notes.strip()) < 3:
            raise ValueError("Explain why the system assessment is being overridden")
        return self


class SensorOut(SensorIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    captured_at: datetime


class FusionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    freshness_score: float
    sensor_score: float | None
    vision_score: float | None
    label: str
    confidence: float
    risk: str
    explanation: str | None
    components: dict[str, Any]
    created_at: datetime
