import os
from pathlib import Path


class Settings:
    APP_NAME = os.getenv("APP_NAME", "Zabbix Report Exporter")
    APP_ENV = os.getenv("APP_ENV", "development")
    ZABBIX_URL = os.getenv("ZABBIX_URL", "")
    ZABBIX_API_TOKEN = os.getenv("ZABBIX_API_TOKEN", "")
    ZABBIX_SECONDARY_URL = os.getenv("ZABBIX_SECONDARY_URL", "")
    ZABBIX_SECONDARY_API_TOKEN = os.getenv("ZABBIX_SECONDARY_API_TOKEN", "")
    ZABBIX_SECONDARY_CA_FILE = os.getenv("ZABBIX_SECONDARY_CA_FILE", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    REDIS_URL = os.getenv("REDIS_URL", "")
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Jakarta")
    REPORT_STORAGE = Path(os.getenv("REPORT_STORAGE", "/app/storage/reports"))
    MAX_REPORT_ITEMS = 20
    MAX_REPORT_DAYS = 90
    MAX_DATA_POINTS = 50000
    REPORT_TIMEOUT_SECONDS = 180


settings = Settings()
