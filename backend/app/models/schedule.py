from dataclasses import dataclass
from datetime import datetime


@dataclass
class ReportSchedule:
    id: int
    name: str
    host_name: str
    item_ids: list[str]
    hour: int
    minute: int
    timezone: str
    enabled: bool
    created_at: datetime