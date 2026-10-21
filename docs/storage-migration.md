# Pemindahan penyimpanan ke drive D

Pemindahan selesai pada 7 Oktober 2026. Aplikasi tetap diakses melalui http://localhost:5010 atau alamat LAN server pada port 5010.

| Data | Lokasi aktif |
| --- | --- |
| Proyek, Git, dan konfigurasi lokal | D:\KERJAAN\zabbix-report-exporter |
| PDF laporan | D:\KERJAAN\zabbix-report-exporter\storage\reports |
| Backup database dan PDF | D:\KERJAAN\zabbix-report-exporter\backup |
| Disk Docker, image, cache, PostgreSQL, dan Redis | D:\DockerDesktopWSL |

## Membuka dan menjalankan proyek

Buka folder proyek di D pada IDE, atau buka file zabbix-report-exporter.code-workspace di dalamnya. Folder proyek lama di C berisi petunjuk dan file workspace yang mengarah ke D; berkas proyeknya telah dipindahkan.

```powershell
Set-Location -LiteralPath 'D:\KERJAAN\zabbix-report-exporter'
docker compose -p zabbix-report-exporter -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build --wait
docker compose -p zabbix-report-exporter -f docker-compose.yml -f docker-compose.prod.yml ps
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/backup-db.ps1
```

Nama project Compose zabbix-report-exporter menjaga penggunaan volume zabbix-report-exporter_postgres_data dan zabbix-report-exporter_redis_data. Seluruh container aplikasi dibuat ulang dari folder D dengan image yang sudah digunakan sebelumnya; mount backend/worker dan konfigurasi Nginx mengarah ke D.

## Pemeriksaan data dan layanan

- Seluruh 27.553 berkas proyek, total 892.938.310 byte, dibandingkan sebelum sumber di C dibersihkan. Konfigurasi lokal dan berkas Git ikut disalin.
- Disk Docker disalin dalam keadaan Docker dan WSL berhenti. SHA-256 disk data dan disk WSL utama cocok dengan backup offline.
- Relokasi dilakukan melalui pengaturan bawaan Docker Desktop 4.88.1. Lokasi disk aktif dan registrasi WSL docker-desktop sudah mengarah ke D.
- Izin akses folder proyek dan disk di D mengikuti lokasi asal, termasuk perlindungan konfigurasi lokal dan backup.
- Seluruh 25 PDF lama cocok dengan hash sebelumnya. PDF baru berjudul **Verifikasi penyimpanan drive D** berstatus SUCCESS, 2 halaman, 3.179 byte; berkas di D dan hasil unduhan identik.
- Jumlah akhir: **2 jadwal aktif, 26 PDF, 837 catatan riwayat**. Satu PDF dan satu catatan tambahan berasal dari verifikasi penyimpanan.
- Halaman Monitoring, Jadwal, dan Laporan diperiksa pada desktop dan ponsel. Tidak ada error JavaScript atau pelebaran halaman; seluruh layanan terhubung dan scheduler berjalan.
- Backup database terbaru dipulihkan pada database sementara: 2 jadwal dan 837 catatan. Database produksi tetap menggunakan volume yang sama.

Bukti terstruktur tersedia di [storage-migration-validation.json](storage-migration-validation.json).

## Backup pemulihan

Backup offline disk berada di backup/docker-before-migration. Manifest hash tersedia di backup/docker-disk-manifest.json; manifest berkas proyek di backup/migration-project-manifest.json. Referensi image, mount, dan konfigurasi sebelum migrasi juga tersimpan di backup. Direktori backup diabaikan Git.

Backup akhir yang sudah diuji:

- Database: backup/zabbix_report_20261007_104216_e61c5a4a.dump.
- PDF: backup/reports_20261007_104216_e61c5a4a.zip.

Pemulihan produksi harus memeriksa backup dan menghentikan writer sebelum penggantian data. Untuk disk Docker, ikuti [panduan backup dan pemulihan Docker Desktop](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/). Perubahan lokasi berikutnya dapat dilakukan lewat Settings → Resources → Advanced, sesuai [panduan WSL Docker](https://docs.docker.com/desktop/features/wsl/).

Sesudah pembersihan sumber, ruang kosong C sekitar **15,66 GiB**, D sekitar **820,41 GiB**. Angka berubah mengikuti laporan, backup, log, dan pemakaian aplikasi lain. Backup disk offline tetap dipertahankan.
