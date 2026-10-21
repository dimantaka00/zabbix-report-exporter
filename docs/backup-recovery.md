# Backup lengkap dan rollback

Jalankan `scripts/backup-project.ps1` dari PowerShell untuk membuat backup baru. Lokasi default berada di folder saudara `D:\KERJAAN\zabbix-report-exporter-backups`, terpisah dari proyek. Parameter `-BackupRoot` dapat menunjuk drive atau lokasi backup lain. Backup lama tidak dihapus.

Sesuai permintaan pemilik proyek, setiap pekerjaan yang menambah, mengubah, atau menghapus file proyek harus diakhiri dengan snapshot lengkap baru setelah perubahan dan pemeriksaan selesai. Aturan ini disimpan di `AGENTS.md` agar berlaku juga pada pekerjaan berikutnya. Satu pekerjaan dapat mencakup beberapa file; snapshot menyimpan kondisi akhirnya. Jika masih ada perubahan setelah snapshot, buat snapshot baru lagi. Sebelum deployment atau perubahan yang berisiko menimpa data, simpan juga kondisi sebelumnya untuk rollback.

Aturan ini merupakan alur kerja agen ketika mengubah proyek, bukan pemantauan otomatis setiap kali file disimpan di IDE. Untuk perubahan manual, jalankan script backup setelah selesai mengedit. Backup dianggap selesai setelah status `verified` dan uji restore lulus; lokasi snapshot dicantumkan dalam hasil pekerjaan.

Setiap snapshot menyimpan kode sumber terbaru termasuk perubahan yang belum di-commit, riwayat Git dalam `repository.bundle`, `.env`, sertifikat, semua file storage yang sudah selesai ditulis, arsip PostgreSQL, dan enam image Docker yang digunakan layanan saat backup dibuat. Dependencies dan hasil build tidak disalin. `runtime-compose.json` menunjuk image yang disimpan, sehingga rollback dapat dilakukan tanpa rebuild. `manifest.json` merekam commit dan SHA-256 setiap artefak; `file-inventory.json` mencatat hash setiap file di ZIP. Folder snapshot membatasi akses ke pemilik, SYSTEM, dan administrator karena konfigurasi berisi kredensial.

Backup dinyatakan `verified` setelah pemeriksaan Git bundle, isi ZIP, konfigurasi Compose, dan uji pemulihan database pada container sementara. Backup tidak menghentikan layanan produksi. Cache dan lock Redis tidak dipulihkan agar lock lama tidak terbawa.

Verifikasi isi ZIP memakai indeks inventaris per nama file agar pemeriksaan ribuan laporan tidak berulang kali memindai seluruh daftar. Jumlah file dan SHA-256 setiap file tetap diperiksa, dengan progres setiap 1.000 file. PDF dan ZIP di `local-data.zip` menggunakan kompresi `Fastest` untuk mempercepat snapshot; isi file dan kualitas PDF tetap sama. Kompresi ZIP laporan harian tetap DEFLATE tingkat 9.

Uji restore menunggu PostgreSQL sementara siap melalui TCP sebelum memulihkan arsip. Pemeriksaan ini melewati server inisialisasi yang hanya membuka Unix socket dan akan berhenti sebelum server akhir berjalan.

Untuk menjaga konsistensi laporan yang dikemas ke ZIP, script menjalankan `scripts/backup-report-guard.py` sementara di container backend. Helper memakai lock eksklusif PostgreSQL selama dump database dan salinan file storage; pengemas ZIP menunggu sebelum membersihkan PDF. Backend harus berjalan. Jika pengemasan lama menahan lock, backup menunggu dua menit lalu berhenti tanpa menimpa snapshot sebelumnya; jalankan kembali setelah pengemasan selesai. Helper menggunakan kredensial dari lingkungan container, tidak mencetaknya, dan dilepas setelah file snapshot selesai disalin.

Pengujian source backup dapat dijalankan dengan `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test-backup-source.ps1`. Pengujian menggunakan repository sementara di `.cache`, mencakup file yang diubah, ditambahkan, dan dihapus, serta tidak mengakses Docker atau database produksi.

## Memulihkan kode ke folder baru

Script pemulihan disimpan juga di setiap folder backup sehingga dapat dijalankan meskipun proyek asli terhapus. Ganti `LOKASI_BACKUP` dengan folder snapshot yang berisi `manifest.json`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'LOKASI_BACKUP\restore-project.ps1' -BackupDirectory 'LOKASI_BACKUP' -TargetDirectory 'D:\KERJAAN\zabbix-report-exporter-restored' -LoadImages
```

Tujuan harus belum ada. Script memeriksa checksum sebelum menyalin kode, konfigurasi, sertifikat, laporan, dan riwayat Git. `-LoadImages` memuat image Docker yang disimpan. Script ini tidak menjalankan layanan dan tidak menimpa database aktif. Jika proyek asli terhapus, `-TargetDirectory` dapat memakai lokasi asli yang sudah tidak ada.

## Rollback aplikasi ketika database masih tersedia

Untuk memulihkan aplikasi memakai database produksi yang masih ada, lakukan langkah pemulihan folder di atas, hentikan writer lama sebelum mengganti aplikasi, lalu jalankan dari folder hasil pemulihan. Gunakan nilai `compose_project` dari `manifest.json` sebagai `NAMA_PROJECT`; mempertahankan nama ini menjaga volume PostgreSQL yang sama.

```powershell
Set-Location -LiteralPath 'D:\KERJAAN\zabbix-report-exporter-restored'
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml stop backend worker
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml -f runtime-compose.json up -d --no-build --wait
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml -f runtime-compose.json exec -T nginx nginx -t
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml -f runtime-compose.json exec -T nginx nginx -s reload
```

## Memulihkan database jika datanya hilang atau rusak

Pemulihan database mengganti isi database tujuan dengan data pada waktu backup. Sebelum rollback database aktif, buat backup kondisi terbaru dan pastikan pilihan snapshot benar. Jangan jalankan perintah ini hanya untuk memulihkan kode. Lakukan langkah pemulihan folder dan image di atas terlebih dahulu.

```powershell
Set-Location -LiteralPath 'D:\KERJAAN\zabbix-report-exporter-restored'
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml stop backend worker
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml -f runtime-compose.json up -d --no-build --wait postgres redis
$RecoveryDbUser = (docker exec zabbix-report-postgres printenv POSTGRES_USER).Trim()
$RecoveryDbName = (docker exec zabbix-report-postgres printenv POSTGRES_DB).Trim()
docker cp 'LOKASI_BACKUP\database.dump' 'zabbix-report-postgres:/tmp/recovery.dump'
docker exec zabbix-report-postgres pg_restore -U $RecoveryDbUser -d $RecoveryDbName --clean --if-exists --no-owner --no-privileges --exit-on-error /tmp/recovery.dump
# Pastikan pg_restore berhasil sebelum menjalankan layanan berikut.
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml -f runtime-compose.json up -d --no-build --wait
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml -f runtime-compose.json exec -T nginx nginx -s reload
docker compose -p NAMA_PROJECT -f docker-compose.yml -f docker-compose.prod.yml -f runtime-compose.json ps
```

Periksa dashboard, daftar jadwal, arsip PDF, dan status layanan setelah pemulihan. Folder storage hasil restore berisi laporan yang disimpan pada snapshot, sedangkan riwayat dan jadwal mengikuti database yang dipilih. Menyimpan salinan snapshot pada drive lain melindungi dari kerusakan drive D. Simpan secara privat; jangan unggah `.env`, sertifikat, atau arsip data ke GitHub.
