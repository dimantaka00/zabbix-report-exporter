# Validasi edisi client starter — 21 Oktober 2026

Edisi bersih diekspor melalui allowlist dari source aplikasi dan template distribusi. Perubahan branding hanya diterapkan pada salinan ekspor; konfigurasi, identitas, dan database aplikasi utama tetap terpisah.

| Pemeriksaan | Hasil |
| --- | --- |
| Build backend dan frontend starter | Berhasil; TypeScript lulus |
| Regresi backend pada source starter | 172 tes lulus pada PostgreSQL/Redis sementara |
| Browser starter desktop dan ponsel | 90 skenario lulus |
| Generator konfigurasi/paket | 3 tes lulus: password independen, izin POSIX 0600, pencegahan injeksi/penimpaan, pengecualian data privat, dan checksum ZIP |
| Instalasi produksi baru | Login aktif, anonim HTTP 401, admin baru wajib mengganti password |
| Data awal produksi | 0 jadwal biasa, 0 jadwal otomatis, 0 riwayat, 0 sesi sebelum login, 0 PDF |
| Demo terisolasi | Database awal kosong; data berasal dari API Zabbix sintetis |
| Ekspor demo | PDF lengkap 45.976 byte; ZIP jadwal selesai dan dapat diunduh |
| Contoh API Python | Membaca 60 titik data dan menyimpan PDF 16.703 byte |
| Tampilan | Lima screenshot sintetis; branding generik; tanpa overflow ponsel/error runtime |
| Privasi | Tidak menyertakan `.env`, sertifikat, dump, PDF nyata, log, data/sesi lama, atau riwayat Git operasional pada paket client |

Pengujian dilakukan dengan Docker Compose pada mesin pengembangan Windows dan container Linux. Izin POSIX pada generator diuji di container; jalur ACL Windows tersedia di generator dan perlu diverifikasi kembali sesuai kebijakan mesin client. Screenshot berasal dari demo yang berjalan, bukan gambar data produksi. ZIP final menyertakan manifest hash source dan dapat dibuat ulang dari revision yang dicantumkan.

Koneksi client nyata, TLS, hak token, interval/retensi Zabbix, kapasitas server, GeoIP, serta pemulihan backup tetap harus diverifikasi pada lingkungan client saat implementasi. Lisensi MPL-2.0 dan atribusi pengembang asli dipertahankan.
