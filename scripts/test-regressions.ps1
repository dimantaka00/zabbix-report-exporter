param(
    [string]$BackendImage = "codex-zabbix-backend-mvp:20261007"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendPath = Join-Path $ProjectRoot "backend"
$TestSuffix = [guid]::NewGuid().ToString("N").Substring(0, 12)
$TestNetwork = "zabbix-regression-$TestSuffix"
$TestPostgres = "zabbix-test-postgres-$TestSuffix"
$TestRedis = "zabbix-test-redis-$TestSuffix"
$NetworkCreated = $false
$CreatedContainers = @()

try {
    docker network create --internal $TestNetwork | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Tidak dapat membuat network pengujian." }
    $NetworkCreated = $true

    docker run --rm -d --network $TestNetwork --name $TestPostgres `
        --tmpfs /var/lib/postgresql/data `
        -e POSTGRES_PASSWORD=regression-only -e POSTGRES_DB=regression postgres:16 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Tidak dapat menjalankan PostgreSQL pengujian." }
    $CreatedContainers += $TestPostgres

    docker run --rm -d --network $TestNetwork --name $TestRedis redis:7-alpine | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Tidak dapat menjalankan Redis pengujian." }
    $CreatedContainers += $TestRedis

    $DatabaseReady = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        docker exec $TestPostgres pg_isready -U postgres -d regression | Out-Null
        if ($LASTEXITCODE -eq 0) { $DatabaseReady = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $DatabaseReady) { throw "PostgreSQL pengujian belum siap." }

    docker run --rm --network $TestNetwork `
        --mount "type=bind,source=$BackendPath,target=/workspace,readonly" `
        --workdir /workspace `
        -e "TEST_DATABASE_URL=postgresql://postgres:regression-only@${TestPostgres}:5432/regression" `
        -e "TEST_REDIS_URL=redis://${TestRedis}:6379/0" `
        -e "REDIS_URL=redis://${TestRedis}:6379/0" `
        $BackendImage python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Pengujian regresi gagal." }
} finally {
    foreach ($Container in $CreatedContainers) {
        docker stop --time 5 $Container | Out-Null
    }
    if ($NetworkCreated) {
        docker network rm $TestNetwork | Out-Null
    }
}
