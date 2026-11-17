"""Request and response models for the tracking API."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


class VehicleCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    label: str = Field(min_length=1, max_length=128)
    type: str = Field(default="simulated", min_length=1, max_length=64)
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class VehiclePatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    type: str | None = Field(default=None, min_length=1, max_length=64)
    active: bool | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "VehiclePatch":
        if self.label is None and self.type is None and self.active is None and self.metadata is None:
            raise ValueError("at least one field is required")
        return self


class TelemetryIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    vehicle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    event_time: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    sequence: int = Field(ge=0)
    simulation_run_id: str | None = Field(default=None, max_length=160)
    source_type: Literal["synthetic", "nyc_tlc_derived"] = "synthetic"
    source_record_id: str | None = Field(default=None, max_length=128)
    generation_method: str = Field(default="deterministic_linear_track", max_length=128)
    simulation_seed: int | None = None

    @field_validator("event_time")
    @classmethod
    def event_time_utc(cls, value: datetime) -> datetime:
        return _aware_utc(value)


class SimulationRunIn(BaseModel):
    run_id: str = Field(min_length=1, max_length=160)
    mode: Literal["baseline", "delay", "loss", "failure", "seed", "demo"]
    seed: int | None = None
    vehicle_count: int | None = Field(default=None, ge=0)
    send_interval_ms: int | None = Field(default=None, ge=0)
    impairment: dict[str, Any] = Field(default_factory=dict)
    result_artifact_path: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def optional_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value)
