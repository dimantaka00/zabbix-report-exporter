param([Parameter(Mandatory=$true)][string]$BackupFile)
$ErrorActionPreference = "Stop"
$ArchivePath = (Resolve-Path -LiteralPath $BackupFile).Path
if ([System.IO.Path]::GetExtension($ArchivePath) -ne ".dump") { throw "Pilih arsip custom PostgreSQL (.dump)." }
$Suffix = [guid]::NewGuid().ToString("N").Substring(0,12)
$RestoreNetwork = "zabbix-restore-$Suffix"
$RestoreContainer = "zabbix-restore-postgres-$Suffix"
$NetworkCreated = $false
$ContainerCreated = $false
try {
    docker network create --internal $RestoreNetwork | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Pembuatan network uji gagal." }
    $NetworkCreated = $true
    docker run --rm -d --name $RestoreContainer --network $RestoreNetwork --tmpfs /var/lib/postgresql/data -e POSTGRES_PASSWORD=restore-test-only -e POSTGRES_DB=restored postgres:16 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL uji tidak dapat berjalan." }
    $ContainerCreated = $true
    $Ready = $false
    for ($Attempt=0; $Attempt -lt 30; $Attempt++) {
        # The image's initialization server accepts Unix sockets before restarting.
        # TCP becomes ready only after initialization and the final server startup.
        docker exec $RestoreContainer pg_isready -h 127.0.0.1 -U postgres -d restored | Out-Null
        if ($LASTEXITCODE -eq 0) { $Ready=$true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $Ready) { throw "PostgreSQL uji belum siap." }
    docker cp $ArchivePath "${RestoreContainer}:/tmp/backup.dump"
    if ($LASTEXITCODE -ne 0) { throw "Penyalinan arsip uji gagal." }
    docker exec $RestoreContainer pg_restore -U postgres -d restored --no-owner --no-privileges --exit-on-error /tmp/backup.dump
    if ($LASTEXITCODE -ne 0) { throw "Pemulihan arsip gagal." }
    docker exec $RestoreContainer psql -U postgres -d restored -v ON_ERROR_STOP=1 -c "SELECT 'schedules' AS table_name, COUNT(*) FROM report_schedules UNION ALL SELECT 'execution_logs', COUNT(*) FROM report_execution_logs;"
    if ($LASTEXITCODE -ne 0) { throw "Pemeriksaan isi database gagal." }
    $AccessTables = @(docker exec $RestoreContainer psql -U postgres -d restored -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('app_users','app_sessions','access_events','report_auto_schedules','report_auto_runs','report_auto_tasks') ORDER BY tablename;")
    if ($LASTEXITCODE -ne 0) { throw "Pemeriksaan tabel akses gagal." }
    foreach ($TableName in $AccessTables) {
        $TableName = $TableName.Trim()
        if ($TableName -notin @("app_users", "app_sessions", "access_events", "report_auto_schedules", "report_auto_runs", "report_auto_tasks")) { continue }
        docker exec $RestoreContainer psql -U postgres -d restored -v ON_ERROR_STOP=1 -c "SELECT '$TableName' AS table_name, COUNT(*) FROM $TableName;"
        if ($LASTEXITCODE -ne 0) { throw "Pemeriksaan restore tabel $TableName gagal." }
    }
    Write-Output "Uji restore lulus pada database sementara. Database produksi tidak diubah."
} finally {
    if ($ContainerCreated) { docker stop --time 5 $RestoreContainer | Out-Null }
    if ($NetworkCreated) { docker network rm $RestoreNetwork | Out-Null }
}
