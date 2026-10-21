param([string]$FrontendImage = "zabbix-starter-demo-frontend:1.0.0", [int]$Port = 3301)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ContainerName = "zabbix-browser-test-" + [guid]::NewGuid().ToString("N").Substring(0,12)
$PreviousUrl = $env:E2E_BASE_URL
$Created = $false
try {
    docker run --rm -d --name $ContainerName -p "127.0.0.1:${Port}:3000" $FrontendImage | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Frontend uji gagal berjalan. Pilih port yang kosong." }
    $Created = $true
    $env:E2E_BASE_URL = "http://127.0.0.1:$Port"
    $Ready = $false
    for ($Attempt=0; $Attempt -lt 30; $Attempt++) {
        try {
            $Response = Invoke-WebRequest -Uri $env:E2E_BASE_URL -UseBasicParsing -TimeoutSec 3
            if ($Response.StatusCode -eq 200) { $Ready=$true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $Ready) { throw "Frontend uji belum siap." }
    Push-Location -LiteralPath (Join-Path $ProjectRoot "e2e")
    try {
        npm.cmd test
        if ($LASTEXITCODE -ne 0) { throw "Pengujian browser gagal." }
    } finally { Pop-Location }
} finally {
    $env:E2E_BASE_URL = $PreviousUrl
    if ($Created) { docker stop --time 5 $ContainerName | Out-Null }
}
