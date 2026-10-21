# Project instructions

## Required backups

The user requires a backup whenever project files are added, changed, or deleted. This preference applies to future work in this repository without asking for confirmation again.

- For every task that changes source, configuration, scripts, or documentation, create a new full project snapshot after all edits and relevant validation, before reporting completion. Group the edits for one task into one snapshot; do not run a full backup after each individual keystroke or file save.
- Run from the project root: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/backup-project.ps1`.
- The default backup directory is the sibling folder `D:\KERJAAN\zabbix-report-exporter-backups`. Backups must remain outside the project. Each snapshot has its own timestamp and identifier; preserve previous snapshots and do not delete or overwrite them without the user's instruction.
- Include uncommitted source changes, Git history, local configuration, certificates, completed report files, PostgreSQL data, the running Docker images, and recovery instructions using the existing backup script. Do not treat a Git commit, a GitHub push, or a copy under `.cache` as a substitute for this full backup.
- Before a destructive change or deployment, also preserve the previous affected files or running images for rollback. The final full snapshot is still required.
- Complete all project-file edits before the final snapshot. If another project file changes afterward, create another snapshot so the final backup reflects the final state.
- Verify a successful script exit, `manifest.json` status `verified`, and the restore test result. Report the snapshot location in the final response. If backup fails, preserve the previous backups, diagnose and retry, and state any remaining limitation accurately.
- Credentials and private archives must remain local with the script's restricted permissions. Do not print `.env` contents or upload backup archives, credentials, certificates, or database dumps to GitHub.
- Read-only questions and inspections that do not change project files do not require a new snapshot.
