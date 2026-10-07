param([string]$PostgresContainer = "zabbix-report-postgres")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $ProjectRoot "backup"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$BackupId = (Get-Date -Format "yyyyMMdd_HHmmss") + "_" + [guid]::NewGuid().ToString("N").Substring(0,8)
$BackupName = "zabbix_report_$BackupId.dump"
$Destination = Join-Path $BackupDir $BackupName
$DbUser = docker exec $PostgresContainer printenv POSTGRES_USER
if ($LASTEXITCODE -ne 0) { throw "Tidak dapat membaca user database." }
$DbName = docker exec $PostgresContainer printenv POSTGRES_DB
if ($LASTEXITCODE -ne 0) { throw "Tidak dapat membaca nama database." }
docker exec $PostgresContainer pg_dump -U $DbUser -d $DbName --format=custom "--file=/tmp/$BackupName"
if ($LASTEXITCODE -ne 0) { throw "Backup database gagal." }
$Listing = @(docker exec $PostgresContainer pg_restore --list "/tmp/$BackupName")
if ($LASTEXITCODE -ne 0) { throw "Arsip database tidak valid." }
docker cp "${PostgresContainer}:/tmp/$BackupName" $Destination
if ($LASTEXITCODE -ne 0) { throw "Penyalinan backup gagal." }
docker exec $PostgresContainer rm -- "/tmp/$BackupName" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning "Arsip sementara masih berada di container." }
Write-Output "Database: $Destination"
$ReportFolder = Join-Path $ProjectRoot "storage/reports"
if (Test-Path -LiteralPath $ReportFolder) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $ReportArchive = Join-Path $BackupDir "reports_$BackupId.zip"
    [System.IO.Compression.ZipFile]::CreateFromDirectory($ReportFolder, $ReportArchive)
    Write-Output "PDF: $ReportArchive"
}
Write-Output "Backup lama tetap disimpan. Uji pemulihan dengan scripts/test-restore.ps1."
