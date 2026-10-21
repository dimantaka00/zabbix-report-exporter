from typing import Annotated, Literal
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.core.config import settings

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]+$", max_length=32)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ClockTime = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
HostCategory = Literal["CS", "TLK", "ICON", "HYP", "MILES"]
GroupReference = Annotated[str, StringConstraints(pattern=r"^(primary|secondary):[0-9]{1,32}$")]


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
    chart_mode: Literal["separate", "combined"] = "separate"
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
        if self.chart_mode == "combined" and len(self.item_ids) < 2:
            raise ValueError("Pilih minimal dua metrik untuk grafik gabungan.")
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


class AutoHostSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zabbix_server: Literal["primary", "secondary"]
    host_id: Identifier
    item_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=5000)

    @field_validator("item_ids")
    @classmethod
    def unique_items(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Pilih setiap metrik hanya sekali.")
        return value


class AutoHostGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: HostCategory
    zabbix_server: Literal["primary", "secondary"]
    group_id: Identifier


class AutoScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    zabbix_server: Literal["primary", "secondary", "all"] = "all"
    host_status: Literal["all", "enabled", "disabled"] = "all"
    selection_mode: Literal["all", "selected"] = "all"
    host_selections: list[AutoHostSelection] = Field(default_factory=list, max_length=200)
    package_zip: bool = True
    data_start_time: ClockTime = "00:00"
    data_end_time: ClockTime = "23:59"
    date_start: date | None = None
    date_end: date | None = None
    host_categories: list[HostCategory] = Field(default_factory=list, max_length=5)
    host_groups: list[AutoHostGroup] = Field(default_factory=list, max_length=200)
    hour: int = Field(default=7, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "Asia/Jakarta"
    enabled: bool = False

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return ScheduleCreate.valid_timezone(value)

    @model_validator(mode="after")
    def valid_selection(self):
        if self.data_end_time < self.data_start_time:
            raise ValueError("Jam akhir laporan harus sama atau setelah jam mulai dalam satu hari.")
        if self.date_start and self.date_end and self.date_end < self.date_start:
            raise ValueError("Tanggal akhir jadwal harus sama atau setelah tanggal mulai.")
        if len(self.host_categories) != len(set(self.host_categories)):
            raise ValueError("Pilih kategori host hanya sekali.")
        if set(self.host_categories) != {group.category for group in self.host_groups}:
            raise ValueError("Pilih minimal satu host group Zabbix untuk setiap kategori yang dicentang.")
        group_keys = [(group.category,group.zabbix_server,group.group_id) for group in self.host_groups]
        if len(group_keys) != len(set(group_keys)):
            raise ValueError("Host group dipilih dua kali dalam kategori yang sama.")
        if self.zabbix_server != "all" and any(group.zabbix_server != self.zabbix_server for group in self.host_groups):
            raise ValueError("Host group harus berasal dari sumber jadwal terpilih.")
        if self.selection_mode == "selected" and not self.host_selections:
            raise ValueError("Pilih minimal satu host untuk jadwal otomatis.")
        if self.selection_mode == "all" and self.host_selections:
            raise ValueError("Daftar host hanya berlaku pada mode host terpilih.")
        keys = [(host.zabbix_server, host.host_id) for host in self.host_selections]
        if len(keys) != len(set(keys)):
            raise ValueError("Pilih setiap host hanya sekali pada sumber yang sama.")
        if self.zabbix_server != "all" and any(host.zabbix_server != self.zabbix_server for host in self.host_selections):
            raise ValueError("Host terpilih harus berasal dari sumber jadwal.")
        if sum(len(host.item_ids or []) for host in self.host_selections) > 20000:
            raise ValueError("Maksimal 20.000 metrik dipilih secara eksplisit per jadwal.")
        return self
