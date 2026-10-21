# Grafik gabungan dan PDF

## Penggunaan

1. Pilih sumber Zabbix dan host pada halaman Monitoring.
2. Centang minimal dua metrik, misalnya Bits received dan Bits sent.
3. Pada Mode grafik dan PDF, pilih Grafik gabungan dari metrik terpilih.
4. Pilih tanggal atau rentang tanggal, lalu klik Tampilkan grafik.
5. Isi judul laporan dan klik Ekspor PDF untuk membuat laporan dengan mode yang sama.

Semua metrik yang dicentang masuk ke grafik gabungan; pemilih satu metrik hanya digunakan pada mode grafik terpisah. Maksimal 20 metrik mengikuti batas laporan yang sudah ada. Setiap tanggal menghasilkan grafik sendiri dengan sumbu 00:00–23:59. PDF memakai judul dan nama file host yang sama dengan alur ekspor sebelumnya, serta bagian downtime sesuai pilihan pengguna.

## Warna, unit, dan statistik

Received menggunakan hijau, Sent merah. Arah dikenali dari key `net.if.in`/`net.if.out` atau nama metrik received/sent. Metrik lain mendapat warna berbeda. Beberapa metrik dengan arah yang sama menggunakan pola garis solid, dashed, atau dotted; legenda menggunakan nama masing-masing metrik. Warna dashboard menyesuaikan kontras tema terang/gelap, sementara PDF memakai hijau dan merah pada latar putih.

Grafik menempatkan setiap metrik pada waktu sampelnya tanpa menjumlahkan nilainya. Bandwidth menggunakan skala bit per second bersama: bps, Kbps, Mbps, dan seterusnya. Byte rate dikonversi ke bit rate untuk sumbu bersama menggunakan 8 bit per byte dan faktor sumber Zabbix yang sudah digunakan proyek. Ukuran data bits/bytes menggunakan skala ukuran bersama. Unit lain hanya dapat digabung jika sama persis; bandwidth tidak dapat dicampur dengan persen, ukuran data, atau unit yang berbeda.

Tabel harian tetap memiliki satu baris tiap metrik, dengan Last, Min, Average, dan Max dari sampelnya sendiri. Average ditimbang berdasarkan jumlah sampel; Last menggunakan sampel terakhir yang tersedia. Nilai tabel mempertahankan unit asli Zabbix dan konversi tampilan masing-masing, termasuk dua desimal untuk unit jaringan. Trend tanpa nilai terakhir tetap menampilkan Last kosong.

Menit tanpa sampel tidak ditambah atau diisi nol. Hari kosong tetap ditampilkan dengan statistik kosong. Jika salah satu permintaan metrik gagal, preview mempertahankan metrik lainnya dan menampilkan keterangan pada metrik yang tidak tersedia. PDF parsial mengikuti status PARTIAL yang sudah ada. Kegagalan seluruh data mengikuti aturan laporan sebelumnya.

## Implementasi dan validasi

Permintaan manual `POST /api/v1/reports/generate` menerima `chart_mode: "separate" | "combined"`, default `separate`. Backend menolak combined dengan kurang dari dua metrik atau unit yang tidak sejenis. Pilihan ini berlaku untuk preview dan laporan manual pada Monitoring. Jadwal otomatis tetap memakai format grafik terpisah; tidak ada perubahan skema database jadwal.

Backend diuji untuk konversi bps/Mbps/byte rate, pemisahan dimensi unit, warna/pola garis, statistik tiap metrik, hari kosong, label yang perlu di-escape, metrik yang tidak tersedia, pagination 20 metrik, serta penerusan mode dan pencatatan hasil pada API. Browser diuji pada desktop/ponsel, kedua tema, ekspor mode gabungan, perubahan pilihan metrik, validasi unit, data parsial, dan rentang tanggal dengan hari kosong.

Validasi 9 Oktober 2026: 103 pengujian regresi backend lulus, dilanjutkan dua pengujian integrasi handler API baru (105 kasus backend seluruhnya); 58 pengujian browser lulus. Build frontend dan kedua image Docker berhasil. Dashboard produksi diverifikasi pada desktop/ponsel, kedua tema, dan pergantian sumber. Pasangan internal1 Received/Sent dari Zabbix asli memuat 1.432/1.433 titik menit untuk 8 Oktober 2026 dan berhasil diekspor menjadi satu PDF gabungan dengan nama file host. Ringkasan pemeriksaan tersimpan pada [hasil validasi](combined-metrics-validation.json). Contoh simulasi yang dirender menghasilkan satu halaman berisi kedua grafik warna dan dua baris statistik.

Contoh `combined-metrics-preview.pdf` pada folder lokal `.cache` memakai data simulasi untuk meninjau tata letak. Data operasional tetap diambil dari sumber Zabbix yang dipilih pengguna. Snapshot lengkap proyek dibuat setelah validasi akhir melalui `scripts/backup-project.ps1`.
