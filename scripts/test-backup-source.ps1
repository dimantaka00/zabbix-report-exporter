$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FixtureRoot = Join-Path $ProjectRoot (".cache/backup-source-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$FixtureProject = Join-Path $FixtureRoot "project"
$FixtureBackups = Join-Path $FixtureRoot "backups"
New-Item -ItemType Directory -Path (Join-Path $FixtureProject "scripts") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "backup-project.ps1") -Destination (Join-Path $FixtureProject "scripts/backup-project.ps1")
Push-Location -LiteralPath $FixtureProject
try {
    git init --quiet
    if ($LASTEXITCODE -ne 0) { throw "Fixture Git init failed." }
    git config user.name "Backup regression"
    git config user.email "backup-regression@example.invalid"
    git remote add origin "https://example.invalid/backup-fixture.git"
    Set-Content -LiteralPath "changed.txt" -Value "original"
    Set-Content -LiteralPath "deleted.txt" -Value "original"
    Set-Content -LiteralPath ".env.example" -Value "EXAMPLE=value"
    git add -- changed.txt deleted.txt .env.example
    git commit --quiet -m "Backup fixture"
    if ($LASTEXITCODE -ne 0) { throw "Fixture commit failed." }
    Set-Content -LiteralPath "changed.txt" -Value "modified"
    Set-Content -LiteralPath "new file.txt" -Value "untracked"
    Set-Content -LiteralPath ".env" -Value "TEST_ONLY=private"
    Remove-Item -LiteralPath "deleted.txt"

    # Stop before PostgreSQL/Docker work; this checks the real source archive path.
    function docker { throw "TEST_STOP_AFTER_SOURCE" }
    try {
        & (Join-Path $FixtureProject "scripts/backup-project.ps1") -BackupRoot $FixtureBackups
        throw "Expected the test to stop before Docker access."
    } catch {
        if ($_.Exception.Message -ne "TEST_STOP_AFTER_SOURCE") { throw }
    }
    $Snapshot = @(Get-ChildItem -LiteralPath $FixtureBackups -Directory)
    if ($Snapshot.Count -ne 1) { throw "Expected one test snapshot." }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Zip = [System.IO.Compression.ZipFile]::OpenRead((Join-Path $Snapshot[0].FullName "source.zip"))
    try {
        $Names = @($Zip.Entries | ForEach-Object {$_.FullName})
        foreach ($Name in @("changed.txt", "new file.txt", ".env.example", "scripts/backup-project.ps1")) {
            if ($Name -notin $Names) { throw "Missing source file: $Name" }
        }
        foreach ($Name in @("deleted.txt", ".env")) {
            if ($Name -in $Names) { throw "Excluded file was archived: $Name" }
        }
        $Reader = [System.IO.StreamReader]::new($Zip.GetEntry("changed.txt").Open())
        try {
            if ($Reader.ReadToEnd().Trim() -ne "modified") { throw "Working-tree edits were lost." }
        } finally { $Reader.Dispose() }
    } finally { $Zip.Dispose() }
    git bundle verify (Join-Path $Snapshot[0].FullName "repository.bundle")
    if ($LASTEXITCODE -ne 0) { throw "Git history bundle failed verification." }
    $FixtureStatus = @(git status --short)
    if (-not ($FixtureStatus -match ' D deleted.txt')) { throw "Fixture working tree was modified by backup." }
    Write-Output "PASS: deleted tracked files, modified files, untracked files, .env exclusion, and Git bundle verified."
} finally { Pop-Location }
