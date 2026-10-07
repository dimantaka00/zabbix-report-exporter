param([Parameter(Mandatory=$true)][string]$BackupFile,
    [string]$BackendImage="codex-zabbix-backend-mvp:20261007",
    [string]$Network="zabbix-report-exporter_report_net")
$ErrorActionPreference="Stop"
$ProjectRoot=Split-Path -Parent $PSScriptRoot
$Archive=(Resolve-Path -LiteralPath $BackupFile).Path
$Suffix=[guid]::NewGuid().ToString("N").Substring(0,12)
$TestPostgres="zabbix-real-schedules-$Suffix"
$Created=$false
try{
    docker run --rm -d --name $TestPostgres --network $Network --tmpfs /var/lib/postgresql/data -e POSTGRES_PASSWORD=real-schedule-test-only -e POSTGRES_DB=verification postgres:16 | Out-Null
    if($LASTEXITCODE -ne 0){throw "Database sementara gagal berjalan"}
    $Created=$true
    $Ready=$false
    for($Attempt=0;$Attempt -lt 30;$Attempt++){
        docker exec $TestPostgres pg_isready -U postgres -d verification | Out-Null
        if($LASTEXITCODE -eq 0){$Ready=$true;break}
        Start-Sleep -Seconds 1
    }
    if(-not $Ready){throw "Database uji belum siap"}
    docker cp $Archive "${TestPostgres}:/tmp/backup.dump"
    if($LASTEXITCODE -ne 0){throw "Penyalinan backup gagal"}
    docker exec $TestPostgres pg_restore -U postgres -d verification --no-owner --no-privileges --exit-on-error /tmp/backup.dump
    if($LASTEXITCODE -ne 0){throw "Restore database uji gagal"}
    $ValidationCode=@'
import asyncio,json,os
from urllib.parse import urlparse
from app.core.database import init_db,close_db,get_pool
from app.services.scheduler.jobs import run_schedule
from app.services.report.pdf import REPORT_DIR
async def main():
    assert urlparse(os.environ["DATABASE_URL"]).hostname.startswith("zabbix-real-schedules-")
    await init_db()
    try:
        rows=await get_pool().fetch("SELECT * FROM report_schedules WHERE enabled=TRUE ORDER BY id")
        assert rows, "No active schedules in restored backup"
        for row in rows:
            result=await run_schedule(row,force=True)
            assert result["status"] in ("SUCCESS","PARTIAL"), result
            content=(REPORT_DIR/result["report_filename"]).read_bytes()
            assert content.startswith(b"%PDF-") and b"%%EOF" in content
            print(json.dumps({"schedule_id":row["id"],"status":result["status"],
                              "bytes":len(content),"warning":result["warning"]}))
    finally:
        await close_db()
asyncio.run(main())
'@
    $ValidationCode | docker run --rm -i --network $Network --env-file (Join-Path $ProjectRoot ".env") -e "DATABASE_URL=postgresql://postgres:real-schedule-test-only@${TestPostgres}:5432/verification" -e REPORT_STORAGE=/tmp/verification-reports $BackendImage python -
    if($LASTEXITCODE -ne 0){throw "Uji jadwal dengan data Zabbix nyata gagal"}
    Write-Output "Jadwal lulus pada salinan database; jadwal produksi tidak diubah."
}finally{
    if($Created){docker stop --time 5 $TestPostgres | Out-Null}
}
