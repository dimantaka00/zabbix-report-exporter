from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.core.config import settings

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]+$", max_length=32)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class MetricSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zabbix_server: Literal["primary", "secondary"] = "primary"
    host_id: Identifier | None = None
    host_name: Name
    item_ids: list[Identifier] = Field(min_length=1, max_length=settings.MAX_REPORT_ITEMS)

    @field_validator("item_ids")
    @classmethod
    def unique_items(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Pilih setiap metrik hanya sekali.")
        return value


class ScheduleCreate(MetricSelection):
    name: Name
    hour: int = Field(default=7, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "Asia/Jakarta"
    enabled: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Timezone tidak valid.")
        return value


class GenerateReportRequest(MetricSelection):
    include_downtime: bool = True
    downtime_trigger_id: Identifier | None = None
    time_from: int = Field(ge=0)
    time_till: int = Field(ge=0)
    resolution: Literal["auto", "hourly", "minute"] = "minute"
    title: Name = "ZABBIX MONITORING REPORT"
    timezone: str = "Asia/Jakarta"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return ScheduleCreate.valid_timezone(value)

    @model_validator(mode="after")
    def valid_period(self):
        if self.time_till <= self.time_from:
            raise ValueError("Waktu selesai harus setelah waktu mulai.")
        if self.time_till - self.time_from > settings.MAX_REPORT_DAYS * 86400:
            raise ValueError(f"Periode maksimal {settings.MAX_REPORT_DAYS} hari.")
        return self


class ScheduleUpdate(ScheduleCreate):
    pass


class ScheduleStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
