# Tema dashboard berdasarkan referensi

Tema menggunakan latar gelap biru keunguan, kartu dengan permukaan ungu gelap, aksen cyan dan hijau mint, serta teks terang. Sidebar desktop dirampingkan menjadi 76 px; logo Kemensos tetap tampil dan setiap ikon navigasi memiliki tooltip serta nama aksesibel.

Grafik ditempatkan di sebelah kiri dengan bidang lebih luas, sementara konfigurasi laporan berada di kanan. Pada layar lebih kecil, keduanya ditampilkan dalam satu kolom. Pemilih sumber Zabbix dipindahkan ke header dashboard.

Grafik memakai cyan untuk metrik umum/traffic masuk dan hijau mint untuk traffic keluar yang dikenali dari key `net.if.out` atau nama metrik. Warna garis, area, grid, rentang min–max, label waktu, dan teks mengikuti mode aktif. Legenda rentang hanya muncul jika data memiliki minimum dan maksimum yang berbeda. Data dan konversi bandwidth tetap memakai alur sebelumnya.

Mode awal untuk browser tanpa preferensi tersimpan adalah gelap. Preferensi terang/gelap yang sudah dipilih tetap dihormati, tersimpan setelah reload, dan disinkronkan antar tab. Tombol mode tetap berfungsi ketika localStorage diblokir. Perubahan ini berlaku pada dashboard web dan halaman jadwal/laporan; format PDF tetap memakai tampilan untuk pencetakan.

## Validasi

- Build Next.js lokal dan build image Docker frontend lulus, termasuk TypeScript.
- 42 pemeriksaan browser yang sudah ada lulus pada desktop/mobile. Dua pemeriksaan visual baru juga lulus setelah selector pengujiannya disesuaikan dengan label metrik yang mencakup unit dan key. Total 44 pemeriksaan mencakup navigasi, tema, grafik, PDF, host disabled, downtime, jadwal, dan pagination.
- Screenshot contoh menggunakan data mock tersedia di `.cache/reference-dashboard-dark.png` dan `.cache/reference-dashboard-light.png`.
- Frontend Docker diperbarui menggunakan `up -d --no-deps --wait frontend`; container sehat. Konfigurasi nginx lolos `nginx -t` dan dimuat ulang. Backend, worker, dan database tidak dibuild ulang dalam pembaruan tema ini.
- Hasil pemeriksaan browser terhadap layanan yang berjalan disimpan di `dashboard-reference-theme-validation.json`; screenshot live berada di `.cache/reference-live-*.png`.
- Pemeriksaan live lulus pada viewport desktop 1440 px, tablet 820 px, dan mobile 393 px, menggunakan grafik SNMP availability dari Zabbix. Ketiga halaman tidak memiliki overflow horizontal atau error runtime/hydration; mode terang tersimpan setelah reload dan perpindahan halaman. Endpoint readiness dan logo merespons HTTP 200.

## Salinan sebelum perubahan

File yang diubah disalin sebelum implementasi ke `.cache/theme-before-20261009_093417` sesuai struktur aslinya. `manifest.json` mencatat hash file. Salinan ini memuat versi kode tepat sebelum perubahan tema, termasuk perbaikan audit lokal sebelumnya.

Image frontend yang berjalan sebelum pembaruan disimpan dengan tag `zabbix-report-exporter-frontend:before-theme-20261009-094258`. Identitas image ada pada `docker-rollback.json` dalam folder salinan. Untuk mengembalikan container frontend ke image tersebut dari root proyek:

```powershell
docker image tag zabbix-report-exporter-frontend:before-theme-20261009-094258 zabbix-report-exporter-frontend:1.0.0
docker compose -p zabbix-report-exporter -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps --wait frontend
docker exec zabbix-report-nginx nginx -s reload
```

Rollback image hanya mengganti frontend yang berjalan. Untuk mengembalikan kode, salin file dari folder salinan ke path proyek yang sama sebelum melakukan build berikutnya. Backup lengkap 8 Oktober tetap tersedia terpisah; salinan tema ini khusus file tampilan dan image frontend.
