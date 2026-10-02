$BackupDir = ".\backup"

New-Item -ItemType Directory -Force $BackupDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$File = "$BackupDir\zabbix_report_$Timestamp.sql"

docker compose exec -T postgres pg_dump -U report -d zabbix_report > $File

if ($LASTEXITCODE -eq 0) {
    Write-Host "Backup berhasil: $File"
} else {
    Write-Host "Backup GAGAL"
    exit 1
}

# Hapus backup lebih dari 30 hari
Get-ChildItem "$BackupDir\*.sql" |
    Where-Object {
        $_.LastWriteTime -lt (Get-Date).AddDays(-30)
    } |
    Remove-Item -Force