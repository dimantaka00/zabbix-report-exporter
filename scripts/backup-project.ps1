param([string]$BackupRoot)
$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $BackupRoot) {
    $BackupRoot = Join-Path (Split-Path -Parent $ProjectRoot) ((Split-Path -Leaf $ProjectRoot) + "-backups")
}
$BackupRoot = [System.IO.Path]::GetFullPath($BackupRoot)
if ($BackupRoot.Equals($ProjectRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $BackupRoot.StartsWith($ProjectRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Backup harus berada di luar folder proyek."
}
$BackupId = (Get-Date -Format "yyyyMMdd_HHmmss") + "_" + [guid]::NewGuid().ToString("N").Substring(0,8)
$Snapshot = Join-Path $BackupRoot $BackupId
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
New-Item -ItemType Directory -Path $Snapshot | Out-Null
# The archives contain local credentials; allow only this user, SYSTEM, and Administrators.
$SnapshotAcl = Get-Acl -LiteralPath $Snapshot
$SnapshotAcl.SetAccessRuleProtection($true, $false)
foreach ($Sid in @([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value, "S-1-5-18", "S-1-5-32-544")) {
    $Rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        [System.Security.Principal.SecurityIdentifier]::new($Sid), "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
    $SnapshotAcl.AddAccessRule($Rule)
}
Set-Acl -LiteralPath $Snapshot -AclObject $SnapshotAcl
Write-Output "Folder backup: $Snapshot"
function Assert-Success([string]$Message) { if ($LASTEXITCODE -ne 0) { throw $Message } }
function Write-Json($Value, [string]$Path) {
    [System.IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), [System.Text.UTF8Encoding]::new($false))
}
$Manifest = [ordered]@{status="incomplete"; created_at=(Get-Date).ToString("o"); project=$ProjectRoot}
$GuardToken = "/tmp/backup-report-guard-$BackupId"
$GuardScript = "$GuardToken.py"
$GuardStarted = $false
function Stop-ReportGuard {
    if (-not $script:GuardStarted) { return }
    $PreviousGuardPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        docker exec zabbix-report-backend touch "$GuardToken.stop" | Out-Null
        for ($GuardAttempt=0; $GuardAttempt -lt 20; $GuardAttempt++) {
            docker exec zabbix-report-backend test -f "$GuardToken.ready" 2>$null
            if ($LASTEXITCODE -ne 0) { break }
            Start-Sleep -Milliseconds 250
        }
        # Also terminate a guard still waiting for an archive lock after a startup timeout.
        $GuardPid = @(docker exec zabbix-report-backend cat "$GuardToken.pid" 2>$null)
        if ($GuardPid.Count -eq 1 -and $GuardPid[0] -match '^[0-9]+$' -and [int]$GuardPid[0] -gt 1) {
            docker exec zabbix-report-backend kill -0 -- $GuardPid[0] 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { docker exec zabbix-report-backend kill -- $GuardPid[0] 2>$null | Out-Null }
        }
        docker exec zabbix-report-backend rm -f -- $GuardScript "$GuardToken.pid" "$GuardToken.ready" "$GuardToken.stop" "$GuardToken.failed" | Out-Null
        $script:GuardStarted = $false
    } finally { $ErrorActionPreference = $PreviousGuardPreference }
}
Write-Json $Manifest (Join-Path $Snapshot "manifest.json")
Push-Location -LiteralPath $ProjectRoot
try {
    $Manifest.git_commit = (git rev-parse HEAD).Trim(); Assert-Success "Tidak dapat membaca commit Git."
    $Manifest.git_branch = (git branch --show-current).Trim(); Assert-Success "Tidak dapat membaca branch Git."
    $Manifest.git_remote = (git remote get-url origin).Trim(); Assert-Success "Tidak dapat membaca tujuan GitHub."
    $Manifest.git_status = @(git status --short); Assert-Success "Tidak dapat membaca status Git."
    git bundle create (Join-Path $Snapshot "repository.bundle") --all
    Assert-Success "Backup riwayat Git gagal."
    git bundle verify (Join-Path $Snapshot "repository.bundle")
    Assert-Success "Bundle Git tidak valid."
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Inventory = [System.Collections.Generic.List[object]]::new()
    function New-Archive([string]$Name, [string[]]$Files) {
        $Zip = [System.IO.Compression.ZipFile]::Open((Join-Path $Snapshot $Name), "Create")
        try {
            foreach ($Relative in ($Files | Sort-Object -Unique)) {
                $Absolute = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Relative))
                if (-not $Absolute.StartsWith($ProjectRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
                    throw "File berada di luar proyek: $Relative"
                }
                $File = Get-Item -LiteralPath $Absolute -Force
                if ($File.PSIsContainer -or ($File.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                    throw "File backup harus berupa file biasa: $Relative"
                }
                $EntryName = $Relative.Replace('\', '/')
                # Report archives already compress their content; prioritize backup throughput.
                $Compression = [System.IO.Compression.CompressionLevel]::Optimal
                if ($Name -eq "local-data.zip" -and $File.Extension.ToLowerInvariant() -in @(".pdf", ".zip")) {
                    $Compression = [System.IO.Compression.CompressionLevel]::Fastest
                }
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($Zip, $Absolute, $EntryName, $Compression) | Out-Null
                $Inventory.Add([ordered]@{archive=$Name; path=$EntryName; bytes=$File.Length;
                    sha256=(Get-FileHash -LiteralPath $Absolute -Algorithm SHA256).Hash})
            }
        } finally { $Zip.Dispose() }
    }
    $SourceFiles = @(git -c core.quotepath=false ls-files --cached --others --exclude-standard)
    Assert-Success "Daftar source tidak dapat dibaca."
    # Build output and dependencies are regenerated; local configuration is archived separately.
    $SourceFiles = @($SourceFiles | Where-Object {
        ($_ -notmatch '(^|/)(node_modules|\.next|__pycache__|\.venv|venv|backup|\.cache|storage)(/|$)' -and
        ($_ -notmatch '(^|/)\.env($|\.)' -or $_ -eq '.env.example')) -and
        (Test-Path -LiteralPath (Join-Path $ProjectRoot $_) -PathType Leaf)
    })
    New-Archive "source.zip" $SourceFiles
    $LocalFiles = @(Get-ChildItem -LiteralPath $ProjectRoot -Force -File -Filter ".env*" |
        Where-Object {$_.Name -ne ".env.example"} | ForEach-Object {$_.Name})
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".env"))) { throw "Konfigurasi .env tidak ditemukan." }
    # Archive cleanup must not remove PDFs between pg_dump and the report-file copy.
    docker cp (Join-Path $PSScriptRoot "backup-report-guard.py") "zabbix-report-backend:$GuardScript"
    Assert-Success "Helper penguncian laporan tidak dapat disalin."
    $GuardStarted = $true
    docker exec -d zabbix-report-backend python $GuardScript $GuardToken
    Assert-Success "Penguncian file laporan untuk backup tidak dapat dimulai."
    $GuardReady = $false
    for ($GuardAttempt=0; $GuardAttempt -lt 120; $GuardAttempt++) {
        docker exec zabbix-report-backend test -f "$GuardToken.ready" 2>$null
        if ($LASTEXITCODE -eq 0) { $GuardReady=$true; break }
        docker exec zabbix-report-backend test -f "$GuardToken.failed" 2>$null
        if ($LASTEXITCODE -eq 0) { throw "Helper penguncian laporan gagal. Periksa koneksi database backend." }
        Start-Sleep -Seconds 1
    }
    if (-not $GuardReady) { throw "Pengemasan ZIP belum selesai; backup ditunda agar file laporan tetap konsisten." }
    $Manifest.report_file_guard = "postgresql-exclusive-lock"
    Write-Output "Database dan file laporan dilindungi dari pembersihan ZIP selama snapshot..."
    # pg_dump uses one consistent database snapshot. Copy report files after the dump.
    $DbUser = (docker exec zabbix-report-postgres printenv POSTGRES_USER).Trim(); Assert-Success "User database tidak terbaca."
    $DbName = (docker exec zabbix-report-postgres printenv POSTGRES_DB).Trim(); Assert-Success "Nama database tidak terbaca."
    $RemoteDump = "/tmp/backup-project-$BackupId.dump"
    docker exec zabbix-report-postgres pg_dump -U $DbUser -d $DbName --format=custom "--file=$RemoteDump"
    Assert-Success "Backup PostgreSQL gagal."
    try {
        $DumpListing = @(docker exec zabbix-report-postgres pg_restore --list $RemoteDump)
        Assert-Success "Arsip PostgreSQL tidak valid."
        docker cp "zabbix-report-postgres:$RemoteDump" (Join-Path $Snapshot "database.dump")
        Assert-Success "Penyalinan database gagal."
    } finally { docker exec zabbix-report-postgres rm -- $RemoteDump | Out-Null }
    foreach ($Directory in @("certs", "storage")) {
        $DirectoryPath = Join-Path $ProjectRoot $Directory
        if (Test-Path -LiteralPath $DirectoryPath) {
            $LocalFiles += @(Get-ChildItem -LiteralPath $DirectoryPath -Force -File -Recurse |
                Where-Object {$_.Extension -ne ".tmp"} | ForEach-Object {
                    $_.FullName.Substring($ProjectRoot.Length + 1).Replace('\', '/')
                } | Where-Object {$_ -notin $SourceFiles})
        }
    }
    New-Archive "local-data.zip" $LocalFiles
    Stop-ReportGuard
    Write-Json $Inventory (Join-Path $Snapshot "file-inventory.json")
    $Labels = (docker inspect --format '{{json .Config.Labels}}' zabbix-report-postgres | ConvertFrom-Json)
    Assert-Success "Label Compose tidak terbaca."
    $Manifest.compose_project = $Labels.'com.docker.compose.project'
    $RuntimeServices = @{}
    $Images = @()
    foreach ($Service in @("backend", "worker", "frontend", "nginx", "postgres", "redis")) {
        $ImageId = (docker inspect --format '{{.Image}}' "zabbix-report-$Service").Trim()
        Assert-Success "Image $Service tidak dapat dibaca."
        $Tag = "zabbix-report-backup/${Service}:$BackupId"
        docker image tag $ImageId $Tag; Assert-Success "Tag backup $Service gagal."
        $RuntimeServices[$Service] = @{image=$Tag; pull_policy="never"}
        $Images += [ordered]@{service=$Service; image_id=$ImageId; backup_tag=$Tag}
    }
    Write-Json @{services=$RuntimeServices} (Join-Path $Snapshot "runtime-compose.json")
    $Manifest.images = $Images
    docker compose -p $Manifest.compose_project -f docker-compose.yml -f docker-compose.prod.yml -f (Join-Path $Snapshot "runtime-compose.json") config --quiet
    Assert-Success "Compose rollback tidak valid."
    Write-Output "Menyimpan enam image Docker untuk pemulihan tanpa rebuild..."
    $Tags = @($Images | ForEach-Object {$_.backup_tag})
    docker image save --output (Join-Path $Snapshot "docker-images.tar") @Tags
    Assert-Success "Arsip image Docker gagal."
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "restore-project.ps1") -Destination (Join-Path $Snapshot "restore-project.ps1")
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs/backup-recovery.md") -Destination (Join-Path $Snapshot "RECOVERY.md")
    Write-Output "Menguji restore database pada PostgreSQL sementara..."
    $RestoreOutput = @(& (Join-Path $PSScriptRoot "test-restore.ps1") -BackupFile (Join-Path $Snapshot "database.dump"))
    $RestoreOutput | Set-Content -LiteralPath (Join-Path $Snapshot "database-restore-test.txt") -Encoding UTF8
    foreach ($Name in @("source.zip", "local-data.zip")) {
        $ExpectedEntries = @{}
        foreach ($FileRecord in $Inventory) {
            if ($FileRecord.archive -eq $Name) { $ExpectedEntries[$FileRecord.path] = $FileRecord }
        }
        $Zip = [System.IO.Compression.ZipFile]::OpenRead((Join-Path $Snapshot $Name))
        try {
            if ($Zip.Entries.Count -ne $ExpectedEntries.Count) { throw "Jumlah file dalam ZIP tidak cocok: $Name" }
            $VerifiedEntries = 0
            foreach ($Entry in $Zip.Entries) {
                $Expected = $ExpectedEntries[$Entry.FullName]
                if ($null -eq $Expected) { throw "File ZIP tidak ada dalam inventaris: $($Entry.FullName)" }
                $Stream = $Entry.Open()
                $Hasher = [System.Security.Cryptography.SHA256]::Create()
                try { $Actual = [BitConverter]::ToString($Hasher.ComputeHash($Stream)).Replace('-', '') }
                finally {$Hasher.Dispose(); $Stream.Dispose()}
                if ($Actual -ne $Expected.sha256) {throw "Checksum isi ZIP tidak cocok: $($Entry.FullName)"}
                $VerifiedEntries++
                if ($VerifiedEntries % 1000 -eq 0) { Write-Output "Memverifikasi ${Name}: $VerifiedEntries/$($Zip.Entries.Count) file" }
            }
        } finally {$Zip.Dispose()}
    }
    $Manifest.source_files = @($Inventory | Where-Object {$_.archive -eq "source.zip"}).Count
    $Manifest.local_files = @($Inventory | Where-Object {$_.archive -eq "local-data.zip"}).Count
    $Manifest.artifacts = @(Get-ChildItem -LiteralPath $Snapshot -File | Where-Object {$_.Name -ne "manifest.json"} |
        ForEach-Object {[ordered]@{name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}})
    $Manifest.status = "verified"
    Write-Json $Manifest (Join-Path $Snapshot "manifest.json")
    Write-Output "Backup lengkap dan restore database terverifikasi: $Snapshot"
} finally {Stop-ReportGuard; Pop-Location}
