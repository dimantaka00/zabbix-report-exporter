param(
    [Parameter(Mandatory=$true)][string]$RollbackSnapshot,
    [string]$BackendImage = "codex-zabbix-access-backend:20261012",
    [string]$FrontendImage = "codex-zabbix-access-frontend:20261012",
    [string]$BaseUrl = "http://localhost:8080"
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$SnapshotRoot = (Resolve-Path -LiteralPath $RollbackSnapshot).Path
$Manifest = Get-Content -LiteralPath (Join-Path $SnapshotRoot "manifest.json") -Raw | ConvertFrom-Json
if ($Manifest.status -ne "verified") { throw "Snapshot rollback harus terverifikasi." }
foreach ($Artifact in $Manifest.artifacts) {
    $ArtifactPath = [System.IO.Path]::GetFullPath((Join-Path $SnapshotRoot $Artifact.name))
    if (-not $ArtifactPath.StartsWith($SnapshotRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Path artefak tidak valid." }
    if ((Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash -ne $Artifact.sha256) { throw "Checksum snapshot tidak cocok." }
}
$ComposeFiles = @("-f", "docker-compose.yml", "-f", "docker-compose.prod.yml")
function Assert-Success([string]$Message) { if ($LASTEXITCODE -ne 0) { throw $Message } }
function Check-Route([string]$Path, [int]$Expected) {
    $HttpRequest = [System.Net.HttpWebRequest]::Create($BaseUrl.TrimEnd('/') + $Path)
    $HttpRequest.AllowAutoRedirect = $false
    $HttpRequest.Timeout = 15000
    $HttpRequest.UserAgent = "Deployment verification"
    try { $HttpResponse = $HttpRequest.GetResponse() }
    catch { $HttpResponse = $_.Exception.InnerException.Response; if (-not $HttpResponse) { $HttpResponse = $_.Exception.Response }; if (-not $HttpResponse) { throw } }
    try { if ([int]$HttpResponse.StatusCode -ne $Expected) { throw "HTTP tidak sesuai pada $Path" } }
    finally { $HttpResponse.Close() }
    Write-Output "Verified HTTP $Expected $Path"
}
docker image inspect $BackendImage $FrontendImage --format '{{.Id}}'
Assert-Success "Image kandidat tidak ditemukan."
docker compose @ComposeFiles config --quiet
Assert-Success "Compose tidak valid."
docker exec zabbix-report-nginx nginx -t
Assert-Success "Konfigurasi Nginx tidak valid."
$Started = $false
try {
    $Started = $true
    docker image tag $BackendImage zabbix-report-exporter-backend:1.0.0
    Assert-Success "Tag backend gagal."
    docker image tag $BackendImage zabbix-report-exporter-worker:1.0.0
    Assert-Success "Tag worker gagal."
    docker image tag $FrontendImage zabbix-report-exporter-frontend:1.0.0
    Assert-Success "Tag frontend gagal."
    foreach ($Service in @("backend", "frontend", "worker")) {
        docker compose @ComposeFiles up -d --no-deps --no-build --force-recreate --wait --wait-timeout 90 $Service
        Assert-Success "Container $Service belum sehat."
    }
    docker exec zabbix-report-nginx nginx -t
    Assert-Success "Validasi proxy gagal."
    docker exec zabbix-report-nginx nginx -s reload
    Assert-Success "Reload proxy gagal."
    Check-Route "/health/ready" 200
    Check-Route "/login" 200
    Check-Route "/" 302
    Check-Route "/admin" 302
    foreach ($Path in @("/api/v1/auth/me", "/api/v1/schedules", "/api/v1/reports", "/api/v1/admin/summary")) { Check-Route $Path 401 }
    Write-Output "Deployment login dan monitoring akses selesai. Buat snapshot penuh akhir setelah validasi."
} catch {
    $Failure = $_
    if ($Started) {
        Write-Warning "Deployment gagal; memulihkan image dan proxy dari snapshot sebelumnya."
        foreach ($Service in @("backend", "worker", "frontend")) {
            $Image = $Manifest.images | Where-Object {$_.service -eq $Service}
            docker image tag $Image.image_id "zabbix-report-exporter-${Service}:1.0.0"
            Assert-Success "Pemulihan image gagal."
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $Archive = [System.IO.Compression.ZipFile]::OpenRead((Join-Path $SnapshotRoot "source.zip"))
        try {
            $Entry = $Archive.GetEntry("nginx/nginx.conf")
            if (-not $Entry) { throw "Proxy rollback tidak ditemukan." }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($Entry, (Join-Path $ProjectRoot "nginx/nginx.conf"), $true)
        } finally { $Archive.Dispose() }
        docker compose @ComposeFiles up -d --no-deps --no-build --force-recreate --wait --wait-timeout 90 backend frontend worker
        Assert-Success "Pemulihan container gagal."
        docker exec zabbix-report-nginx nginx -t
        Assert-Success "Proxy rollback tidak valid."
        docker exec zabbix-report-nginx nginx -s reload
        Assert-Success "Reload rollback gagal."
    }
    throw $Failure
}
