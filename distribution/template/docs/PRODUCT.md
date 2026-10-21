# Contoh materi produk dan ruang lingkup penawaran

## Deskripsi yang dapat disesuaikan

**Zabbix Report Exporter** membantu tim operasional mengubah metrik Zabbix menjadi grafik, laporan PDF, dan arsip harian ZIP. Host serta metrik dapat dipilih per sumber; jadwal mendukung jam eksekusi, rentang jam data, dan tanggal berlaku. Login admin/operator dan riwayat akses membantu pengelolaan penggunaan aplikasi.

Paket mencakup source MPL-2.0, konfigurasi Docker, generator `.env`, demo sintetis, contoh API, dan panduan implementasi. Gambar promosi berasal dari demo; hasil di lingkungan client mengikuti konfigurasi dan ketersediaan data Zabbix mereka.

## Contoh isi penawaran

| Komponen | Isi yang dapat ditawarkan |
| --- | --- |
| Paket source | Source lengkap dan panduan sesuai MPL-2.0 |
| Implementasi | Instalasi Docker, konfigurasi koneksi Zabbix, branding, akun, dan uji serah terima |
| Kustomisasi | Perubahan layout PDF, preset host group, dan kebutuhan khusus yang disepakati |
| Pelatihan | Penggunaan dashboard, pemilihan metrik, jadwal, dan unduhan arsip |
| Dukungan | Durasi, jam layanan, kanal, dan target respons yang ditetapkan penyedia |

Tentukan sendiri harga, masa dukungan, cakupan perubahan, biaya infrastruktur, dan kriteria penerimaan pada penawaran final. Source yang sudah diberikan menurut MPL tetap membawa hak penerima menurut lisensi tersebut; jasa dan dukungan dapat diberi ruang lingkup komersial tersendiri.

## Checklist materi yang dikirim ke calon client

- Gunakan gambar pada `docs/images/` dengan keterangan **data demo sintetis**.
- Sertakan kebutuhan Docker Compose v2, kapasitas server yang diuji bersama client, dan akses token baca Zabbix.
- Jelaskan pembaruan grafik mengikuti interval pengumpulan Zabbix, bukan jaminan setiap nilai berubah setiap 15 detik.
- Nyatakan bahwa domain, TLS, lisensi database GeoIP, migrasi data, dan operasional server disediakan sesuai lingkup kontrak.
- Lampirkan `LICENSE`, `NOTICE`, source, panduan implementasi, dan contoh konfigurasi tanpa kredensial nyata.
