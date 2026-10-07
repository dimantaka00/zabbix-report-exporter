# Catatan perbaikan awal scheduler, database, dan dashboard

Dokumen ini menyimpan hasil tahap perbaikan awal. Untuk fitur, script dan hasil terbaru, gunakan [checklist MVP](mvp-checklist.md) serta [README](../README.md).

- Variabel `today` ditentukan sebelum pemeriksaan tanggal eksekusi.
- Hasil Zabbix dengan `points` kosong tidak dianggap laporan berhasil. Jika semua
  metrik gagal atau kosong, eksekusi dicatat `FAILED` dan dicoba ulang setelah
  lima menit. `last_run_date` hanya diperbarui setelah PDF berhasil dibuat.
- Inisialisasi membuat `report_schedules` dan `report_execution_logs` dalam
  transaksi. Advisory lock mencegah backend dan worker membuat tabel bersamaan.
  Skema tabel riwayat sesuai database yang sudah ada; tidak ada penghapusan tabel,
  kolom, atau riwayat. Ini bukan migrasi untuk skema lain yang tidak kompatibel.
- Worker mengirim heartbeat ke Redis setiap 15 detik dengan TTL 90 detik.
  `/api/v1/dashboard/status` menampilkan scheduler `starting`, `running`, atau
  `error` dari heartbeat; `stopped` jika heartbeat habis; `unknown` jika Redis
  tidak tersedia. Kegagalan jadwal tetap berstatus `error` selama menunggu retry.
- Dependency `redis>=5,<6` ditambahkan. Koneksi status memiliki timeout dan
  ditutup dengan `aclose()` sesuai [dokumentasi redis-py](https://redis.io/docs/latest/develop/clients/redis-py/async/).
- Semua router aktif dikumpulkan di `app.api.router`. Entry point dan import
  lama menjadi wrapper ke implementasi yang sama. Tampilan Execution History
  yang kedua di halaman monitoring dihapus.

## Pengujian terpisah

Jalankan dari root proyek:

```powershell
docker build -t codex-zabbix-backend-review:20261006 ./backend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-regressions.ps1 -BackendImage codex-zabbix-backend-review:20261006
docker build -f frontend/Dockerfile.prod -t codex-zabbix-frontend-review:20261006 ./frontend
git diff --check
```

Skrip pengujian membuat PostgreSQL dan Redis sementara di network Docker internal
terpisah. PostgreSQL menggunakan tmpfs. Kode dipasang read-only dan `.env`,
database produksi, serta `storage/` produksi tidak dipasang ke container pengujian.
Container dan network sementara dibersihkan setelah selesai.

Pengujian meliputi jadwal sebelum/sesudah waktunya, pencegahan eksekusi ulang,
periode hari sebelumnya, data kosong, kegagalan upstream/PDF, cooldown dan retry,
status gagal/pulih, heartbeat kedaluwarsa, kompatibilitas route/import, pembuatan
database baru secara bersamaan, dan pengulangan inisialisasi tanpa kehilangan
riwayat. CRUD jadwal diuji pada database sementara.

## Penerapan ke layanan aktif

Penerapan memerlukan persetujuan karena backend, worker, dan frontend perlu
dibuat ulang dan dapat mengalami jeda layanan. Worker yang sudah diperbaiki bisa
langsung menjalankan jadwal hari ini yang tertunda dan membuat PDF baru.

Sebelum penerapan, simpan backup database dan referensi image container yang
sedang berjalan untuk rollback. Gunakan kedua berkas Compose produksi secara
eksplisit. Hindari `down -v`; perbaikan ini tidak memerlukan penghapusan volume.

Setelah penerapan, periksa `/health`, `/api/v1/dashboard/status`, daftar jadwal,
riwayat eksekusi, log worker, dan tampilan monitoring. Tunggu setidaknya satu
siklus polling (30 detik) sebelum menilai status scheduler yang baru dimulai.

## Hasil penerapan 7 Oktober 2026

Penerapan dilakukan setelah persetujuan pengguna dengan
`scripts/deploy-reviewed.ps1`. Image aktif backend, worker, dan frontend telah
dicocokkan dengan image yang diuji dan kode sumber. Backend/frontend/worker
dibuat ulang secara bertahap; Nginx dimuat ulang setelah pergantian upstream.
Ada satu respons 502 singkat saat frontend baru mulai; pemeriksaan ulang berhasil
dan tidak ada error layanan baru setelah worker pulih.

Backup terbaru berada di `backup/before-deploy-4c7bd5ff4851.dump`. Referensi image
rollback disimpan di `backup/before-deploy-4c7bd5ff4851-images.json`.

Jadwal 1 awalnya gagal karena item `917037` (Uptime (network)) tidak mempunyai
data untuk periode laporan 6 Oktober, tidak mempunyai trend untuk periode
tersebut, dan tidak mempunyai history pada satu jam terakhir saat diperiksa.
`lastclock=0` tidak membuktikan item belum pernah mengirim data; tampilan field
itu dibatasi periode tertentu menurut
[dokumentasi Zabbix](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/item/object).

Setelah pengguna menyetujui penggantian metrik pada host yang sama, jadwal 1
diubah ke `917040` (SNMP agent availability) pada host `16500`
(BBPPKS-BANDUNG-CS-BACKUP). Empat titik data tersedia pada periode laporan.
Konfigurasi sebelumnya disimpan di
`backup/schedule-1-before-metric-change-c12b7d3485a0.json`. Nama laporan, host,
waktu, timezone, dan status aktif dipertahankan. Worker di-restart agar langsung
mencoba metrik baru.

Hasil pemeriksaan akhir:

- Kedua jadwal mencatat `SUCCESS` dan `last_run_date=2026-10-07`.
- PDF jadwal 1: `zabbix_report_20261007_085725.pdf`.
- PDF jadwal 2: `zabbix_report_20261007_085318.pdf`.
- Semua koneksi backend/PostgreSQL/Redis/Zabbix berstatus `connected`; scheduler
  berstatus `running`.
- Halaman `/`, `/reports`, `/schedules`, health, host Zabbix, daftar jadwal,
  daftar laporan, history, dan summary mengembalikan HTTP 200.
- Halaman monitoring hanya merender satu heading Execution History.
- Grafik menyediakan 1.440 titik data untuk metrik ICMP ping jadwal 2.
- Ekspor PDF manual menghasilkan `zabbix_report_20261007_085826.pdf`, tersimpan
  sebagai laporan verifikasi. Hasil unduhan sama dengan hasil generate.
- Semua PDF yang diperiksa mempunyai header dan terminator PDF yang valid.
- `pip check` tidak menemukan dependency rusak; pemeriksaan diff lulus.
- Tidak ada traceback, error layanan, atau restart otomatis container aplikasi
  yang ditemukan pada pemeriksaan setelah worker pulih.

Pemeriksaan ini memverifikasi kondisi saat penerapan, bukan jaminan bahwa
ketersediaan data Zabbix atau layanan tidak akan berubah di kemudian hari.
