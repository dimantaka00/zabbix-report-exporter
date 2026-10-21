# Login dan monitoring akses

## Status lokal sementara: login dinonaktifkan

Sesuai permintaan pengguna pada 12 Oktober 2026, `.env` lokal menggunakan `AUTH_ENABLED=false` sambil menunggu migrasi server. Monitoring, jadwal, laporan, dan unduhan dapat dibuka tanpa login. Menu akun/logout/admin disembunyikan; halaman `/login`, `/admin`, dan `/password` diarahkan ke monitoring. API pengelolaan akun dan log akses tetap ditolak (HTTP 403), termasuk bila browser masih memiliki sesi admin. Akun, hash password, sesi, dan log lama tidak dihapus. Retensi/masa berlaku yang sudah ada tetap berlaku. Mode ini tidak mencatat identitas pengguna baru karena tidak ada login.

Untuk mengaktifkan kembali setelah migrasi, ubah `AUTH_ENABLED=true` pada `.env`, lalu restart konfigurasi backend/worker dengan `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build --force-recreate --wait backend worker`, dan muat ulang browser. Frontend serta Nginx mengikuti status dari backend sehingga tidak memerlukan penggantian konfigurasi proxy atau build ulang untuk perubahan flag. Default pada kode dan `.env.example` tetap `true`; hanya nilai `false` eksplisit menonaktifkan autentikasi. Jangan gunakan script deployment yang memverifikasi API anonim sebagai 401 sebelum mengaktifkan kembali flag.

Validasi penonaktifan lokal tersedia di [login-disabled-validation.json](login-disabled-validation.json): 121 pengujian backend dan 12 pengujian browser desktop/mobile lulus. Halaman utama/jadwal/laporan aktif merespons 200 tanpa login; API akun dan log admin merespons 403. Kode fitur login tetap tersedia untuk diaktifkan kembali.

Aplikasi lokal tersedia di http://localhost:5010/login. Username bootstrap berada pada `AUTH_BOOTSTRAP_USERNAME` (default `admin`); password sementara tersedia pada `AUTH_BOOTSTRAP_PASSWORD` di `.env` lokal. Jangan menyalin `.env` ke GitHub atau chat. Password awal dibuat acak dan `.env` dibatasi untuk pemilik, SYSTEM, dan Administrators. Bootstrap hanya membuat admin saat tabel pengguna kosong; mengedit variabel tersebut setelahnya tidak mengganti password akun.

Saat pertama masuk, admin wajib mengganti password sementara dengan password minimal 12 karakter. Login berikutnya menggunakan password baru. Halaman **Akses admin** (`/admin`) tersedia hanya untuk admin, dengan:

- Akun dan IP unik hari ini, sesi aktif dalam lima menit terakhir, serta percobaan login gagal.
- Riwayat login berhasil/gagal, logout, halaman yang dibuka, akses ditolak, aktivitas API, dan perubahan akun. Pencarian akun/IP/negara, filter jenis aktivitas, periode 1–90 hari, serta pagination tersedia.
- Alamat IP yang terlihat oleh server, perkiraan negara, user-agent perangkat/browser, waktu, endpoint, dan hasil HTTP. Browser/perangkat dilaporkan oleh klien dan dapat dipalsukan. Nama pada percobaan login gagal adalah username yang dicoba, bukan identitas terverifikasi.
- Sesi pengguna yang dapat dicabut. Cabut sesi memaksa login ulang pada permintaan berikutnya.
- Pembuatan akun admin/operator, penonaktifan/aktivasi, serta reset password sementara. Akun baru dan akun yang direset wajib mengganti password; penonaktifan dan reset mencabut seluruh sesi akun tersebut. Admin tidak dapat menonaktifkan dirinya sendiri atau admin aktif terakhir.

Operator dapat memakai monitoring, laporan, dan jadwal, tetapi tidak dapat membaca monitoring akses atau mengelola akun. Semua API bisnis dan unduhan PDF membutuhkan sesi server; cookie sesi HttpOnly/SameSite=Lax berakhir setelah delapan jam dan token sesi hanya disimpan sebagai hash di PostgreSQL. Password menggunakan scrypt dengan salt acak. Permintaan perubahan memerlukan token CSRF serta pemeriksaan Origin bila dikirim browser. Login dibatasi delapan kegagalan per pasangan IP/username atau 25 per IP dalam sepuluh menit; penghitung diserialisasi untuk mencegah percobaan paralel melewati batas.

Nginx melindungi halaman aplikasi melalui auth_request, dan meneruskan IP klien dengan header yang ditimpa. Backend dijalankan dengan `--no-proxy-headers`; hanya alamat peer Nginx yang diperoleh dari DNS Docker yang dipercaya untuk `X-Real-IP`. Header kiriman pengunjung langsung tidak dipercaya. Jika ada proxy/load balancer lain di depan Nginx, atur trusted real_ip secara eksplisit; jangan mempercayai semua alamat. NAT/Docker Desktop/VPN dapat menyebabkan server hanya melihat IP gateway atau alamat bersama. IP tidak membuktikan identitas seseorang.

Negara dicari **secara lokal**, tanpa mengirim IP pengunjung ke API eksternal. Basis DB-IP Lite Oktober 2026 tersedia di `storage/geoip/dbip-country-lite.mmdb`, dipasang melalui volume storage, dan masuk snapshot lengkap. IP privat, loopback, serta non-global ditandai **Jaringan internal / lokal**, tanpa negara rekaan. IP publik yang tidak ditemukan atau database yang tidak tersedia menampilkan **Tidak diketahui**. Negara merupakan perkiraan lokasi jaringan publik dan dapat mengikuti lokasi VPN/proxy. Data DB-IP Lite memiliki cakupan/akurasi terbatas dan lisensi CC BY 4.0; dashboard menyertakan atribusi [DB-IP](https://db-ip.com/db/download/ip-to-country-lite).

Perbarui basis bulanan dengan `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/update-geoip.ps1 -Release YYYY-MM`, validasi hasil, lalu buat snapshot proyek. Tidak ada pengambilan negara melalui internet pada setiap akses.

Log akses disimpan 90 hari dan dibersihkan tiap jam. Cookie/password/token CSRF, request body, query string, serta kredensial Zabbix tidak disimpan dalam log akses. Log sebelum fitur diterapkan tidak tersedia. Ringkasan harian mengikuti Asia/Jakarta; sesi online merupakan perkiraan dari aktivitas lima menit terakhir. Polling dashboard admin berlangsung tiap 15 detik.

Deployment lokal saat ini masih HTTP. Untuk akses LAN dengan login, sediakan HTTPS di reverse proxy lalu set `AUTH_COOKIE_SECURE=true`; jangan menyalakan flag tersebut pada HTTP karena browser tidak akan mengirim cookie. Header anti-iframe telah diterapkan. Ini menambahkan kontrol akses dan pencatatan, bukan menyelesaikan seluruh temuan audit keamanan sebelumnya.

Pengujian backend menggunakan PostgreSQL/Redis sementara melalui `scripts/test-regressions.ps1`. Pengujian browser `scripts/test-browser.ps1` menggunakan mock API; login, ganti password, dashboard admin, pembuatan akun, pencabutan sesi, dan layout desktop/mobile dicakup. Script pemeriksaan produksi lama membutuhkan login/sesi yang sah setelah fitur ini aktif.

Deployment fitur ini memakai `scripts/deploy-access.ps1 -RollbackSnapshot PATH_SNAPSHOT_TERVERIFIKASI` setelah image kandidat lulus validasi. Script memeriksa checksum snapshot, mengganti backend/frontend/worker, reload Nginx, memeriksa login/kesiapan database, dan memastikan API anonim ditolak. Jika gagal, image serta konfigurasi proxy sebelumnya dipulihkan tanpa menimpa database. Script `deploy-reviewed.ps1` lama ditujukan untuk versi MVP tanpa autentikasi; jangan gunakan pemeriksaan API anonimnya untuk versi login ini.

Rollback menggunakan snapshot sebelum perubahan dan petunjuk RECOVERY.md. Tabel login/log baru bersifat tambahan; jangan menimpa database aktif hanya untuk mengembalikan image. Mengembalikan image lama juga mengembalikan API tanpa autentikasi, sehingga rollback tersebut harus mempertimbangkan paparan akses.

Bukti validasi tersedia di [access-monitoring-validation.json](access-monitoring-validation.json): 119 pengujian backend, 58 pengujian browser monitoring lama, dan delapan pengujian login/admin desktop/mobile lulus. Login/logout admin bootstrap, penolakan API anonim, serta penolakan header IP palsu juga diverifikasi pada layanan aktif. Akses localhost di Docker Desktop ini terlihat sebagai gateway `172.18.0.1`; alamat ini tidak dapat dipakai untuk menyimpulkan negara atau IP asli di balik NAT.
