from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Kind = Literal["goal", "task", "preference", "memory", "project"]


class RecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Kind
    title: str = Field(min_length=1, max_length=240)
    detail: str = Field(default="", max_length=4000)
    status: Literal["active", "done"] = "active"
    due: str | None = None

    goal_id: str | None = Field(default=None, max_length=100)
    priority: Literal["low", "normal", "high"] = "normal"
    effort_minutes: int | None = Field(default=None, ge=5, le=480)

    @model_validator(mode="after")
    def valid_link(self):
        if self.goal_id and self.kind != "task":
            raise ValueError("Only tasks can link to a goal")
        return self

    @field_validator("due")
    @classmethod
    def valid_date(cls, value):
        if value:
            from datetime import date
            date.fromisoformat(value)
        return value or None


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=8000)


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    model: str = Field(default="gemini-3.8-flash", min_length=1, max_length=100, pattern=r"^gemini-[a-zA-Z0-9._-]+$")
    ai_enabled: bool = False
    semantic_memory: bool = False
    quiet_mode: bool = False
    briefings_enabled: bool = False
    activity_awareness: bool = True
    nudges_enabled: bool = True


class ActivitySample(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    app: str = Field(min_length=1, max_length=120)
    bundle_id: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=300)


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    value: str = Field(min_length=10, max_length=1024)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


class GoogleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_id: str = Field(min_length=8, max_length=512, pattern=r"^[a-zA-Z0-9._-]+\.apps\.googleusercontent\.com$")
    client_secret: str = Field(min_length=1, max_length=1024)



class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(default="", max_length=120)
    about: str = Field(default="", max_length=4000)
    preferences: str = Field(default="", max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    timezone: str = Field(default="", max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError:
                raise ValueError("Use a time zone such as Asia/Kolkata")
        return value


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[RecordInput] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def tasks_have_goals(self):
        if any(t.kind != "task" or not t.goal_id for t in self.tasks):
            raise ValueError("Every planned task must link to an active goal")
        return self


class ImportSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(max_length=100)
    record: RecordInput


class ImportCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(max_length=100)
    selections: list[ImportSelection] = Field(min_length=1, max_length=100)
