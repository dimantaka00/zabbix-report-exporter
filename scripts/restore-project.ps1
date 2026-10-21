param(
    [string]$BackupDirectory = $PSScriptRoot,
    [string]$TargetDirectory,
    [switch]$LoadImages
)
$ErrorActionPreference = "Stop"
$ArchiveRoot = (Resolve-Path -LiteralPath $BackupDirectory).Path
$Manifest = Get-Content -LiteralPath (Join-Path $ArchiveRoot "manifest.json") -Raw | ConvertFrom-Json
if ($Manifest.status -ne "verified") { throw "Backup belum selesai diverifikasi." }
if (-not $TargetDirectory) {
    $TargetDirectory = Join-Path (Split-Path -Parent $ArchiveRoot) ("restored-" + (Get-Date -Format "yyyyMMdd_HHmmss"))
}
$RestoreRoot = [System.IO.Path]::GetFullPath($TargetDirectory)
if (Test-Path -LiteralPath $RestoreRoot) { throw "Folder tujuan sudah ada. Pilih folder baru agar data tidak tertimpa." }
foreach ($Artifact in $Manifest.artifacts) {
    $ArtifactPath = [System.IO.Path]::GetFullPath((Join-Path $ArchiveRoot $Artifact.name))
    if (-not $ArtifactPath.StartsWith($ArchiveRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Nama file backup tidak valid."
    }
    if ((Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash -ne $Artifact.sha256) {
        throw "Checksum tidak cocok: $($Artifact.name)"
    }
}
Write-Output "Checksum seluruh artefak backup cocok."
git clone --no-checkout (Join-Path $ArchiveRoot "repository.bundle") $RestoreRoot
if ($LASTEXITCODE -ne 0) { throw "Pemulihan repository gagal." }
Set-Acl -LiteralPath $RestoreRoot -AclObject (Get-Acl -LiteralPath $ArchiveRoot)
Add-Type -AssemblyName System.IO.Compression.FileSystem
foreach ($ZipName in @("source.zip", "local-data.zip")) {
    $Zip = [System.IO.Compression.ZipFile]::OpenRead((Join-Path $ArchiveRoot $ZipName))
    try {
        foreach ($Entry in $Zip.Entries) {
            $Destination = [System.IO.Path]::GetFullPath((Join-Path $RestoreRoot $Entry.FullName))
            if (-not $Destination.StartsWith($RestoreRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
                $Entry.FullName -match '(^|[\\/])\.git([\\/]|$)') { throw "Path arsip tidak valid." }
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($Entry, $Destination, $false)
        }
    } finally { $Zip.Dispose() }
}
git -C $RestoreRoot reset --mixed $Manifest.git_commit
if ($LASTEXITCODE -ne 0) { throw "Pemulihan index Git gagal." }
git -C $RestoreRoot remote set-url origin $Manifest.git_remote
if ($LASTEXITCODE -ne 0) { throw "Pemulihan tujuan GitHub gagal." }
Copy-Item -LiteralPath (Join-Path $ArchiveRoot "runtime-compose.json") -Destination $RestoreRoot
Copy-Item -LiteralPath (Join-Path $ArchiveRoot "RECOVERY.md") -Destination $RestoreRoot
if ($LoadImages) {
    docker image load --input (Join-Path $ArchiveRoot "docker-images.tar")
    if ($LASTEXITCODE -ne 0) { throw "Pemulihan image Docker gagal." }
}
Write-Output "Kode, konfigurasi, sertifikat, dan laporan dipulihkan ke: $RestoreRoot"
Write-Output "Layanan dan database produksi belum diubah. Ikuti RECOVERY.md untuk tahap database dan startup."
