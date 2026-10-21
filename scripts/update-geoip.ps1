param([string]$Release = (Get-Date -Format "yyyy-MM"))
$ErrorActionPreference = "Stop"
if ($Release -notmatch '^20\d{2}-(0[1-9]|1[0-2])$') { throw "Release harus dalam format YYYY-MM." }
$Directory = Join-Path (Split-Path -Parent $PSScriptRoot) "storage/geoip"
New-Item -ItemType Directory -Path $Directory -Force | Out-Null
$Archive = Join-Path $Directory "dbip-country-lite-$Release.mmdb.gz"
Invoke-WebRequest -Uri "https://download.db-ip.com/free/dbip-country-lite-$Release.mmdb.gz" -OutFile $Archive -UseBasicParsing -TimeoutSec 60
$Temporary = Join-Path $Directory ("geoip-" + [guid]::NewGuid().ToString("N") + ".tmp")
$InputStream = [System.IO.File]::OpenRead($Archive)
$Gzip = [System.IO.Compression.GzipStream]::new($InputStream, [System.IO.Compression.CompressionMode]::Decompress)
$OutputStream = [System.IO.File]::Create($Temporary)
try { $Gzip.CopyTo($OutputStream) }
finally { $OutputStream.Dispose(); $Gzip.Dispose(); $InputStream.Dispose() }
if ((Get-Item -LiteralPath $Temporary).Length -lt 1024) { throw "Database unduhan tidak valid." }
Move-Item -LiteralPath $Temporary -Destination (Join-Path $Directory "dbip-country-lite.mmdb") -Force
Write-Output "Basis GeoIP lokal diperbarui ($Release). Sumber: https://db-ip.com/db/download/ip-to-country-lite (CC BY 4.0)."
Write-Output "Jalankan scripts/backup-project.ps1 setelah validasi untuk menyimpan snapshot terbaru."
