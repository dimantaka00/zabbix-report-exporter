# Grafik, pembaruan data, dan unduhan PDF

Pratinjau Monitoring dan ekspor PDF membaca data langsung dari API Zabbix. Setelah grafik ditampilkan, opsi **Perbarui grafik otomatis setiap 15 detik** mengambil ulang data untuk host, metrik, sumber, dan periode yang sama selama tab terlihat. Permintaan yang masih berjalan tidak ditumpuk. Mengganti pilihan membatalkan permintaan lama agar hasilnya tidak menggantikan pilihan baru. Jika pembaruan gagal, grafik terakhir tetap terlihat dengan peringatan dan waktu terakhir data dimuat.

Untuk memantau data terbaru, pilih tanggal hari ini. Pembaruan mengikuti sampel yang sudah diterima Zabbix; aplikasi tidak membuat sampel pada menit yang kosong atau mengganti history per menit dengan trend per jam. Host yang berhenti mengirim data tetap dapat memiliki metrik aktif, tetapi tidak memiliki sampel terbaru pada rentang waktu yang dipilih.

Permintaan baca API mencoba ulang gangguan transport atau HTTP 408, 429, 502, 503, dan 504 hingga tiga percobaan dengan jeda terbatas. Penolakan izin dan kesalahan parameter tidak dicoba ulang. Browser juga mencoba ulang permintaan GET ketika koneksi atau gateway sementara gagal. Permintaan POST pembuatan laporan tidak dikirim ulang otomatis sehingga tidak membuat PDF duplikat.

Kegagalan mengambil satu metrik setelah percobaan ulang menghentikan pembuatan PDF, bukan mengubah kegagalan itu menjadi grafik kosong dalam laporan selesai. Pada jadwal otomatis, bagian yang gagal tetap mengikuti mekanisme retry antrean. Respons Zabbix yang berhasil tetapi tanpa sampel tetap dilaporkan sebagai data tidak tersedia pada periode tersebut. Peringatan laporan parsial disimpan pada riwayat; peringatan tanpa jadwal retry tidak menandai proses scheduler sebagai gagal.

PDF baru diterbitkan setelah penulisan file sementara selesai dan diganti secara atomik. Browser menunggu respons unduhan lengkap, memeriksa penanda PDF, dan mempertahankan URL unduhan selama satu menit agar browser sempat mengonsumsinya. Halaman **Laporan** mengambil ulang daftar arsip dan riwayat setiap lima detik saat tab terlihat, dengan pembatalan permintaan lama saat halaman pagination berubah.

PDF adalah snapshot pada saat ekspor. Untuk memasukkan sampel yang datang kemudian, buat ekspor baru. Dokumen PDF yang sudah diunduh tidak berubah sendiri.

Regresi untuk gangguan koneksi sebelum ekspor pertama tersedia pada `backend/tests/test_metric_delivery.py`. Pengujian browser pada `e2e/tests/metric-delivery.spec.ts` mencakup pemulihan pratinjau tanpa klik berulang, pembaruan berkala, mempertahankan grafik saat gagal, jeda pembaruan, unduhan PDF pertama, pencegahan pengiriman POST ulang, dan pembaruan daftar laporan pada desktop serta ponsel.

## Validasi 21 Oktober 2026

- Build backend dan frontend produksi berhasil, termasuk pemeriksaan tipe TypeScript.
- Seluruh 172 pengujian backend lulus pada PostgreSQL dan Redis sementara.
- Seluruh 90 skenario browser desktop/ponsel lulus setelah fixture disesuaikan untuk tiga percobaan baca dan pemilihan alert aplikasi.
- Pemeriksaan langsung pada port 5010 menampilkan 20 titik data dalam satu jam terakhir pada host yang masih menerima sampel. Satu permintaan ekspor menghasilkan PDF lengkap 15.309 byte; unduhan ulang dari arsip identik byte demi byte. Stream PDF berisi instruksi gambar vektor tanpa label grafik kosong.
- Browser tidak mencatat error runtime, tampilan ponsel tidak overflow, dan heartbeat scheduler kembali `running`. Host lain yang sampel terakhirnya tertinggal tetap memerlukan pemeriksaan pengumpulan data pada Zabbix.
