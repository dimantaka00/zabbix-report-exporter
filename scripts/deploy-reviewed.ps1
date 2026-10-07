param(
    [string]$BackendImage = "codex-zabbix-backend-mvp:20261007",
    [string]$FrontendImage = "codex-zabbix-frontend-mvp:20261007",
    [string]$BaseUrl = "http://localhost:8080"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$ComposeFiles = @("-f", "docker-compose.yml", "-f", "docker-compose.prod.yml")
$DeploymentId = [guid]::NewGuid().ToString("N").Substring(0, 12)
$BackupDirectory = Join-Path $ProjectRoot "backup"
$BackupName = "before-deploy-$DeploymentId.dump"
$SnapshotFile = Join-Path $BackupDirectory "before-deploy-$DeploymentId-images.json"
$RollbackComposeFile = Join-Path $BackupDirectory "before-deploy-$DeploymentId-compose.json"
$RollbackServices = @{}
$ProductionImages = @{
    backend = "zabbix-report-exporter-backend:1.0.0"
    worker = "zabbix-report-exporter-worker:1.0.0"
    frontend = "zabbix-report-exporter-frontend:1.0.0"
}
$RollbackImages = @{}
$DeploymentStarted = $false

function Assert-DockerSuccess([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Reload-Proxy {
    docker compose @ComposeFiles exec -T nginx nginx -t
    Assert-DockerSuccess "Konfigurasi Nginx tidak valid."
    docker compose @ComposeFiles exec -T nginx nginx -s reload
    Assert-DockerSuccess "Reload Nginx gagal."
}

function Wait-Endpoint([string]$Path) {
    for ($Attempt = 0; $Attempt -lt 10; $Attempt++) {
        try {
            $Response = Invoke-WebRequest -Uri "$($BaseUrl.TrimEnd('/'))$Path" `
                -UseBasicParsing -TimeoutSec 10
            if ($Response.StatusCode -eq 200) {
                Write-Output "HTTP 200 $Path"
                return
            }
        } catch {
            if ($Attempt -eq 9) { throw }
        }
        Start-Sleep -Seconds 2
    }
    throw "Endpoint belum siap: $Path"
}

try {
    docker image inspect $BackendImage $FrontendImage --format '{{.Id}}'
    Assert-DockerSuccess "Image yang sudah diuji tidak ditemukan."
    New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null

    foreach ($Service in @("backend", "worker", "frontend")) {
        $ImageId = docker inspect --format '{{.Image}}' "zabbix-report-$Service"
        Assert-DockerSuccess "Tidak dapat membaca image $Service."
        $RollbackTag = "codex-zabbix-$Service-before-deploy`:$DeploymentId"
        docker image tag $ImageId $RollbackTag
        Assert-DockerSuccess "Tidak dapat menyimpan image rollback $Service."
        $RollbackImages[$Service] = @{ image_id = $ImageId; rollback_tag = $RollbackTag }
        $HealthJson = docker inspect --format '{{json .Config.Healthcheck}}' "zabbix-report-$Service"
        Assert-DockerSuccess "Healthcheck rollback $Service tidak dapat dibaca."
        $Health = $HealthJson | ConvertFrom-Json
        if ($Health -and $Health.Test -and $Health.Test[0] -ne "NONE") {
            $HealthConfig = @{test=@($Health.Test)}
            foreach ($Field in @("Interval","Timeout","StartPeriod")) {
                if ($Health.$Field) { $HealthKey = if ($Field -eq "StartPeriod") { "start_period" } else { $Field.ToLower() }; $HealthConfig[$HealthKey] = "$($Health.$Field)ns" }
            }
            if ($Health.Retries) { $HealthConfig.retries=$Health.Retries }
            $RollbackServices[$Service]=@{healthcheck=$HealthConfig}
        } else {
            $RollbackServices[$Service]=@{healthcheck=@{disable=$true}}
        }
    }

    $DbUser = docker exec zabbix-report-postgres printenv POSTGRES_USER
    Assert-DockerSuccess "User database tidak dapat dibaca."
    $DbName = docker exec zabbix-report-postgres printenv POSTGRES_DB
    Assert-DockerSuccess "Nama database tidak dapat dibaca."
    docker exec zabbix-report-postgres pg_dump -U $DbUser -d $DbName `
        --format=custom "--file=/tmp/$BackupName"
    Assert-DockerSuccess "Backup database gagal."
    $ArchiveListing = @(docker exec zabbix-report-postgres pg_restore --list "/tmp/$BackupName")
    Assert-DockerSuccess "Archive database tidak valid."
    docker cp "zabbix-report-postgres:/tmp/$BackupName" (Join-Path $BackupDirectory $BackupName)
    Assert-DockerSuccess "Penyalinan backup database gagal."

    $RollbackServices.nginx=@{depends_on=@{frontend=@{condition="service_started"}}}
    [System.IO.File]::WriteAllText($RollbackComposeFile,
        (@{services=$RollbackServices} | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
    docker compose @ComposeFiles -f $RollbackComposeFile config --quiet
    Assert-DockerSuccess "Konfigurasi rollback tidak valid."
    $Snapshot = @{
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        backup = $BackupName
        rollback_compose = [System.IO.Path]::GetFileName($RollbackComposeFile)
        images = $RollbackImages
        reviewed_backend = $BackendImage
        reviewed_frontend = $FrontendImage
    }
    [System.IO.File]::WriteAllText($SnapshotFile,
        ($Snapshot | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    Write-Output "Backup dan image rollback tersimpan: $SnapshotFile"

    $DeploymentStarted = $true
    foreach ($Service in @("backend", "worker", "frontend")) {
        $ReviewedImage = if ($Service -eq "frontend") { $FrontendImage } else { $BackendImage }
        docker image tag $ReviewedImage $ProductionImages[$Service]
        Assert-DockerSuccess "Penyiapan image $Service gagal."
    }

    docker compose @ComposeFiles up -d --no-deps --no-build --wait --wait-timeout 60 backend
    Assert-DockerSuccess "Backend baru belum sehat."
    Reload-Proxy
    Wait-Endpoint "/health/ready"
    Wait-Endpoint "/api/v1/dashboard/summary"

    docker compose @ComposeFiles up -d --no-deps --no-build --wait --wait-timeout 60 frontend
    Assert-DockerSuccess "Frontend baru gagal berjalan."
    Reload-Proxy
    foreach ($Path in @("/", "/reports", "/schedules", "/api/v1/history")) {
        Wait-Endpoint $Path
    }

    docker compose @ComposeFiles up -d --no-deps --no-build --wait --wait-timeout 60 worker
    Assert-DockerSuccess "Worker baru gagal berjalan."
    $SchedulerReady = $false
    for ($Attempt=0; $Attempt -lt 30; $Attempt++) {
        $ServiceStatus = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/api/v1/dashboard/status" -TimeoutSec 40
        if ($ServiceStatus.data.scheduler -eq "running") { $SchedulerReady=$true; break }
        if ($ServiceStatus.data.scheduler -eq "error") { throw "Scheduler melaporkan kegagalan eksekusi." }
        Start-Sleep -Seconds 2
    }
    if (-not $SchedulerReady) { throw "Heartbeat scheduler belum siap." }
    Write-Output "Scheduler running"
    $Snapshot.deployed_at_utc = [DateTime]::UtcNow.ToString("o")
    [System.IO.File]::WriteAllText($SnapshotFile,
        ($Snapshot | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    Write-Output "Penerapan selesai. Snapshot rollback: $SnapshotFile"
} catch {
    $DeploymentFailure = $_
    if ($DeploymentStarted) {
        Write-Warning "Penerapan gagal; memulihkan image sebelumnya."
        foreach ($Service in @("backend", "worker", "frontend")) {
            docker image tag $RollbackImages[$Service].rollback_tag $ProductionImages[$Service]
            Assert-DockerSuccess "Pemulihan image $Service gagal. Snapshot: $SnapshotFile"
        }
        $RollbackFiles = $ComposeFiles + @("-f", $RollbackComposeFile)
        docker compose @RollbackFiles up -d --no-deps --no-build --wait --wait-timeout 60 backend frontend worker
        Assert-DockerSuccess "Pemulihan container gagal. Snapshot: $SnapshotFile"
        Reload-Proxy
        Wait-Endpoint "/health"
    }
    throw $DeploymentFailure
}
