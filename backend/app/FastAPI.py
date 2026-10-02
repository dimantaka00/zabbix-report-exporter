from fastapi import FastAPI

app = FastAPI(
    title="Zabbix Report Exporter",
    version="1.0.0"
)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "zabbix-report-exporter"
    }