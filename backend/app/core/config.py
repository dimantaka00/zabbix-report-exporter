import os


class Settings:
    APP_NAME = os.getenv(
        "APP_NAME",
        "Zabbix Report Exporter",
    )

    APP_ENV = os.getenv(
        "APP_ENV",
        "development",
    )

    ZABBIX_URL = os.getenv(
        "ZABBIX_URL",
        "",
    )

    ZABBIX_API_TOKEN = os.getenv(
        "ZABBIX_API_TOKEN",
        "",
    )

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "",
    )

    REDIS_URL = os.getenv(
        "REDIS_URL",
        "",
    )


settings = Settings()