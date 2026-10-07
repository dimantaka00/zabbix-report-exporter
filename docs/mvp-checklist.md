# Penerimaan MVP LAN internal

Status aplikasi: **16/16 kriteria terpenuhi (100% checklist MVP)**.
Diperiksa 7 Oktober 2026, terakhir sekitar 09:45 WIB.

Batas yang disepakati pengguna: LAN internal melalui Nginx; login operator pada tahap berikutnya. Persentase ini mengukur fitur dan penerimaan aplikasi dalam batas tersebut. Kapasitas server dan ketersediaan Zabbix tetap menjadi prasyarat operasional.

| Kriteria | Hasil | Bukti |
| --- | --- | --- |
| Host dan metrik numerik aktif dapat dipilih | Lulus | Browser desktop/ponsel; API Zabbix nyata |
| Validasi periode, timezone, jumlah/duplikasi metrik, jam/menit, dan kepemilikan host | Lulus | Pengujian model, API, dan Zabbix client |
| Ekspor beberapa metrik ke PDF dengan nama unik dan penyimpanan atomik | Lulus | Pengujian PDF; PDF nyata 3 halaman, 4.237 byte |
| Data sebagian ditandai PARTIAL; seluruh data kosong menghasilkan FAILED | Lulus | Pengujian backend/browser; PDF PARTIAL nyata dengan satu metrik kosong |
| Grafik dan statistik konstan, extrema trend, rata-rata berbobot, serta history padat | Lulus | Pengujian statistik, trend, dan 10.001 titik history tanpa duplikasi |
| Jadwal dapat dibuat, diedit, diaktifkan/nonaktifkan, dan dihapus | Lulus | CRUD database sementara; browser desktop/ponsel |
| Jadwal memakai hari kalender sebelumnya sesuai timezone | Lulus | Pengujian scheduler; kedua jadwal nyata pada salinan database |
| Eksekusi ganda dicegah dan retry bertahan setelah koneksi database dibuat ulang | Lulus | Advisory lock nyata; restart pool; pemulihan eksekusi terputus; log kedaluwarsa dilindungi lock |
| Jalankan sekarang memakai lock yang sama dan tercatat sebagai manual_schedule | Lulus | Pengujian API; browser |
| Riwayat manual/terjadwal, peringatan, identitas historis, dan pagination | Lulus | API dan browser; riwayat dipertahankan setelah jadwal dihapus |
| Arsip PDF, pagination, unduhan yang sama, dan pembatasan path file | Lulus | API dan browser; unduhan nyata sama byte demi byte |
| Kesiapan backend, heartbeat worker, dan healthcheck layanan | Lulus | Backend/frontend/worker/PostgreSQL/Redis healthy; scheduler running |
| Inisialisasi database idempotent dan data lama dipertahankan | Lulus | Startup bersamaan; seluruh 835 catatan lama masih tersedia |
| Antarmuka desktop/ponsel tanpa error JavaScript atau pelebaran halaman setelah grafik | Lulus | 10 browser tests; viewport dan page width produksi sama-sama 393 px |
| Backup biner, arsip PDF, uji restore, dan deployment dengan referensi rollback | Lulus | Restore 2 jadwal/835 log; snapshot image serta konfigurasi healthcheck tervalidasi |
| Instalasi, konfigurasi contoh, pengujian, dan prosedur operasional terdokumentasi | Lulus | README, .env.example, scripts, bukti JSON dan checklist ini |

## Pengujian dan batas buktinya

- **37 pengujian backend lulus**, memakai PostgreSQL dan Redis sementara. Kasus kegagalan Zabbix, PDF, dan database sengaja disimulasikan untuk memeriksa penanganan error.
- **10 pengujian browser lulus**: lima alur masing-masing pada desktop dan emulasi Pixel 7. API mock memastikan pengujian CRUD tidak mengubah jadwal produksi.
- **Dua jadwal dengan data Zabbix nyata lulus** pada database hasil restore terpisah: jadwal 1 SUCCESS (3.170 byte) dan jadwal 2 SUCCESS (6.132 byte). PDF uji berada di container sementara.
- Uji browser produksi membuat satu laporan manual bernama **MVP acceptance smoke**. Dua metrik pada host 16500 digunakan: SNMP agent availability (917040) dan Uptime (network) (917037). Metrik uptime kosong untuk periode uji; status PARTIAL sesuai harapan. Pengujian ini mempertahankan konfigurasi kedua jadwal.
- Pemeriksaan setelah perbaikan CSS produksi membaca halaman, grafik dan status layanan tanpa membuat laporan tambahan. Tidak ada browser error; halaman /, /schedules dan /reports mengembalikan HTTP 200.
- Nginx config, Compose config, sintaks script PowerShell, TypeScript strict, pip check, dan git diff --check lulus.
- Referensi rollback dan Compose override diperiksa valid. Penggantian image ke versi lama tidak sengaja dijalankan pada produksi untuk menguji kegagalan deployment.

Bukti terstruktur: [uji PDF nyata](mvp-live-validation.json) dan [pemeriksaan deployment final](mvp-deployment-validation.json).
Screenshot dan PDF verifikasi lokal tersedia di backup/mvp-live-dashboard.png, backup/mvp-final-mobile.png, dan backup/mvp-live-validation.pdf.

## Versi yang diterapkan

- Backend/worker: codex-zabbix-backend-mvp:20261007, image ID sha256:781b8b41ad6826a5f8c32a24c7fbb45f81e0af525a0448a728a2b258ce4214b3.
- Frontend final: codex-zabbix-frontend-mvp:20261007, image ID sha256:f88b818b030fc5ddc5620787f29473228bdf2db8050970c2b98253a5a39403a5.
- Tag produksi tetap zabbix-report-exporter-{backend,worker,frontend}:1.0.0.
- Snapshot sebelum penerapan MVP: backup/before-deploy-0e781ed69bdc-images.json dan arsip .dump dengan ID yang sama.
- Snapshot sebelum perbaikan CSS ponsel: backup/before-deploy-7728c92b6338-images.json, backup/before-deploy-7728c92b6338-compose.json, dan arsip .dump.
- Snapshot terakhir sebelum pemulihan log kedaluwarsa: backup/before-deploy-517a11e0a7ad-images.json, backup/before-deploy-517a11e0a7ad-compose.json, dan arsip .dump.
- Backup database dan PDF terpisah: backup/zabbix_report_20261007_092451_f27dd80f.dump dan backup/reports_20261007_092451_f27dd80f.zip.

Worker memperbaiki status RUNNING yang berusia lebih dari batas permintaan (180 detik) ditambah 60 detik. Eksekusi terjadwal yang masih memegang advisory lock tetap dilindungi. Permintaan manual yang baru belum dianggap kedaluwarsa.

Migrasi menambahkan next_retry_at dan last_error pada jadwal, serta schedule_name, host_name dan trigger_type pada riwayat. Jadwal 1 dan 2 tetap aktif, last_run_date=2026-10-07, tanpa next_retry_at atau last_error pada pemeriksaan akhir. Jumlah arsip setelah uji manual adalah 25 PDF; jumlah riwayat 836.

## Catatan operasional server

Drive C tersisa sekitar **280 MB** saat pemeriksaan akhir. Instalasi Chromium awal mengalami ENOSPC; unduhan sementara dari sesi ini telah dibersihkan, dan pengujian beralih ke Chrome yang sudah terpasang. Aplikasi sedang berjalan sehat, tetapi kapasitas ini perlu ditambah sebelum penggunaan rutin agar PDF, log, backup, dan pembaruan dapat terus ditulis. Berkas pribadi, cache proyek lain, dan volume database tidak dibersihkan.

Login/RBAC, email/WhatsApp, jadwal mingguan/bulanan, HA multi-server, dan penghapusan otomatis arsip berada di luar MVP tahap ini. Pengujian membuktikan kasus yang dicatat, bukan menjamin bebas dari seluruh kemungkinan bug atau kegagalan jaringan/perangkat.
