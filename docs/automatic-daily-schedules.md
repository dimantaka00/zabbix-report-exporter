# Jadwal otomatis host, metrik, dan ZIP

Halaman **Jadwal → Jadwal otomatis host & metrik** menyediakan laporan harian untuk semua host atau beberapa host terpilih. Pilih **Semua sumber Zabbix**, Zabbix 7, atau Zabbix 2, lalu pilih filter semua host, host aktif, atau host nonaktif. Cakupan mengikuti host yang dapat dibaca oleh API token aplikasi.

1. Isi nama jadwal dan **Jam eksekusi harian** dari **00:00 sampai 23:59**.
2. Pilih zona waktu: Asia/Jakarta, Asia/Makassar, atau Asia/Jayapura.
3. Pada **Cakupan laporan otomatis**, pilih **Pilih host dan metrik** bila ingin menentukan sendiri. Cari dan centang beberapa host. Klik **Atur metrik** pada tiap host, lalu pilih **Pilih metrik tertentu** dan centang metriknya; opsi **Semua metrik numerik aktif** juga tersedia per host.
4. **Kemas PDF menjadi satu ZIP** aktif secara default untuk jadwal baru. Satu ZIP dibuat per jadwal per hari setelah semua pekerjaan periode tersebut selesai.
5. Centang aktivasi otomatis untuk menjalankan setiap hari, lalu klik **Simpan otomatis**. Tanpa centang aktivasi, jadwal disimpan sebagai nonaktif.
6. Pantau **Progres jadwal otomatis** dan **Detail host**. **Unduh ZIP** tersedia pada progres periode terbaru dan arsip halaman **Laporan**. Riwayat tetap menyediakan unduhan setiap PDF individual.

Jam eksekusi adalah waktu mulai memasukkan pekerjaan ke antrean, bukan batas waktu semua PDF selesai. Worker memeriksa jadwal setiap 30 detik dan memproses dua pekerjaan host bersamaan. Contoh jadwal 07:00 Asia/Jakarta pada 12 Oktober menghasilkan laporan data 11 Oktober. Jam eksekusi 00:00 maupun 23:59 menggunakan aturan hari sebelumnya yang sama. Jadwal yang baru diaktifkan setelah jam terpilih mulai pada pemeriksaan berikutnya. Satu jadwal hanya memasukkan satu eksekusi per tanggal lokal.

## Rentang jam laporan dan tanggal jadwal

**Jam mulai laporan** dan **Jam akhir laporan** menentukan rentang data dalam hari sebelumnya. Default **00:00–23:59** mencakup pukul 00:00:00 sampai 23:59:59. Contoh rentang **08:15–17:30** menghasilkan data pukul 08:15:00 sampai 17:30:59. Rentang digunakan untuk metrik dan downtime serta dicatat di manifest ZIP. Jam akhir harus sama atau setelah jam mulai dalam satu hari; rentang melewati tengah malam tidak tersedia. Jam yang sama mencakup satu menit lengkap.

**Tanggal mulai jadwal** dan **Tanggal akhir jadwal** membatasi tanggal eksekusi harian secara inklusif sesuai zona waktu. Keduanya opsional; tanggal kosong berarti tidak ada batas pada sisi tersebut. Jadwal 13–31 Oktober membuat periode eksekusi 13–31 Oktober dengan data hari sebelumnya, yaitu 12–30 Oktober. Jadwal baru tidak mengejar periode sebelum dibuat. Setelah jeda/restart, jadwal yang sudah memiliki periode dapat mengejar tanggal eksekusi yang tertunda di dalam rentang tanggal, termasuk setelah tanggal akhir berlalu. Antrean yang sudah dibuat tetap dapat selesai setelah tanggal akhir. Perubahan rentang jam tidak mengubah periode yang sudah masuk antrean.

## Kategori host group

Kategori **CS, TLK, ICON, HYP, MILES** mengikuti host group yang dapat dibaca dari Zabbix. **CS memakai COMNET saja**, sesuai pilihan pengguna; group seperti `CS-UPS-SR` tidak dimasukkan. TLK memakai nama group dengan token `TLK` atau `TELKOM`, HYP memakai `HYP` atau `Hypernet`, sedangkan ICON dan MILES memakai token masing-masing. Pencocokan nama memakai batas token sehingga `Hypervisors`, `ICONIC`, dan `NOTCOMNET` tidak ikut.

Centang kategori untuk memilih seluruh group yang cocok pada sumber tersebut. Gunakan **Atur group** untuk meninjau nama, sumber, dan ID serta memilih sebagian group. Beberapa kategori dan beberapa group digabungkan sebagai gabungan host tanpa duplikasi. Tanpa kategori, cakupan seluruh host pada sumber/status terpilih tetap tersedia. Setiap kategori terpilih harus memiliki minimal satu group; pilihan kosong tidak diperluas menjadi semua host.

Pilihan menyimpan ID group bersama identitas sumber Zabbix, sehingga ID sama pada dua sumber tetap dibedakan. Membership host dibaca kembali setiap periode menggunakan `host.get` dengan `groupids`; nama host tidak digunakan untuk menentukan kategori. Group baru harus dipilih dan disimpan; host baru yang menjadi anggota group terpilih ikut otomatis dalam mode semua host. Pada mode host terpilih, pilihan host harus menjadi anggota minimal satu group terpilih. Sumber Zabbix tanpa group terpilih dilewati. Group yang hilang/tidak dapat dibaca menunda penambahan periode dan menampilkan pesan untuk memperbarui pilihan.

Mengubah sumber atau pilihan group mengosongkan pilihan host agar host di luar cakupan tidak terbawa. Setelah mengganti sumber, kategori tetap dicentang dan group harus dipilih kembali. Jadwal lama dan antreannya dimigrasikan dengan rentang penuh, tanpa batas tanggal, dan tanpa filter group.

API group mengikuti dokumentasi resmi [hostgroup.get Zabbix 6.0](https://www.zabbix.com/documentation/6.0/en/manual/api/reference/hostgroup/get) dan [host.get Zabbix 7.4](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/host/get).

## Pemilihan host dan metrik

Daftar host dibaca setiap kali periode baru masuk antrean. Daftar metrik dibaca ketika setiap host mulai diproses, lalu disimpan untuk periode tersebut. Host dan metrik yang ditambahkan setelah pengambilan daftar tersebut ikut pada periode berikutnya. Status host nonaktif tetap boleh dipilih untuk membaca history yang masih tersimpan.

Mode **Pilih host dan metrik** hanya memproses host yang dicentang. Setiap host menyimpan sumber dan ID sendiri, sehingga ID yang sama pada Zabbix 7 dan Zabbix 2 tidak tertukar. Pilihan host/metrik diperiksa kembali terhadap Zabbix saat disimpan. Host yang hilang atau tidak cocok dengan filter status menyebabkan antrean ditunda dengan pesan; aplikasi tidak memperluas cakupan ke host lain. Bila metrik terpilih menjadi nonaktif atau hilang saat eksekusi, metrik yang masih tersedia tetap diproses dengan peringatan; bila seluruh pilihan metrik hilang, host berstatus gagal.

Pemilihan eksplisit mendukung maksimal 200 host, 5.000 metrik per host, dan 20.000 metrik per jadwal. Pilihan lebih dari 20 metrik tetap dibagi menjadi beberapa PDF. Mode semua host/semua metrik numerik aktif tetap tersedia. Mengganti sumber atau filter status pada formulir mengosongkan pilihan host agar pilihan tidak tertukar; gunakan **Hanya host yang sudah dipilih** untuk meninjau pilihan.

Semua item dengan `status=0` dan `value_type=0` (numeric float) atau `value_type=3` (numeric unsigned) ikut tanpa harus dipilih satu per satu. Item teks/log dan item nonaktif dikecualikan. Kegagalan pengumpulan data tampil sebagai peringatan, bukan dianggap sebagai nilai nol.

Maksimal **20 metrik per PDF**, bukan 20 metrik per host. Host dengan 25 metrik menghasilkan bagian 1/2 berisi 20 metrik dan bagian 2/2 berisi lima metrik. Setiap PDF menggunakan nama file unik; judul serta riwayat menampilkan nomor bagian. Host tanpa metrik numerik aktif berstatus `SKIPPED` dan tidak menghasilkan PDF kosong. Bagian tanpa data diberi status `FAILED` di riwayat; bagian berikutnya tetap dicoba. Host dengan sebagian bagian berhasil atau peringatan berstatus `PARTIAL`.

Resolusi mengikuti laporan harian aplikasi: sampel history dikelompokkan per menit. Batas 50.000 titik history per item, retensi history, interval pengumpulan, dan izin API Zabbix tetap berlaku. Downtime diambil sekali pada bagian pertama setiap host, menggunakan pemilihan trigger otomatis yang sudah ada. Downtime yang tidak tersedia menghasilkan peringatan.

## ZIP dan penghematan penyimpanan

Satu ZIP memuat seluruh PDF yang berhasil dibuat untuk satu jadwal pada satu tanggal laporan, ditambah `manifest.json` berisi ringkasan host, status, ukuran asli, dan SHA-256 setiap PDF. Kompresi memakai DEFLATE tingkat 9 tanpa menurunkan kualitas PDF. PDF biasanya sudah memiliki kompresi internal, sehingga rasio penghematan ZIP bergantung pada isi; ukuran ZIP dan total PDF sebelum kompresi ditampilkan pada progres.

Paket dibuat pada file sementara, dibaca kembali untuk memeriksa CRC dan SHA-256, lalu dipindahkan secara atomik ke nama ZIP final. Setelah identitas arsip tercatat dalam database, hanya PDF sementara milik periode tersebut yang dibersihkan. Isi PDF yang berubah atau ZIP yang tidak lolos verifikasi tidak menyebabkan penghapusan PDF asli. PDF manual, jadwal satu host lama, dan file milik periode lain dipertahankan.

Unduhan PDF individual dari riwayat membaca langsung isi ZIP secara streaming. Aplikasi tidak mengekstrak salinan PDF baru ke disk. File sementara ZIP yang belum selesai tidak ditampilkan sebagai arsip. ZIP yang gagal dibuat dicoba ulang setelah lima menit, dan PDF yang belum dibersihkan tetap disimpan. Restart setelah ZIP tercatat selesai melanjutkan pembersihan dengan verifikasi ulang. Periode tanpa PDF berhasil diberi keterangan **Tidak ada PDF untuk ZIP**, tanpa membuat ZIP kosong. Periode parsial tetap bisa menghasilkan ZIP berisi PDF yang berhasil dan manifest status kegagalannya.

Backup lengkap memakai lock eksklusif PostgreSQL selama pengambilan database dan file laporan; pengemas ZIP memakai lock bersama yang sama. Dengan demikian, pembersihan PDF menunggu sampai file snapshot selesai disalin. Bila pengemasan sedang berjalan lama, backup menunggu maksimal dua menit lalu berhenti tanpa menimpa snapshot sebelumnya; jalankan kembali setelah pekerjaan ZIP selesai. Pengemasan dilanjutkan pada pemeriksaan berikutnya setelah lock backup dilepas.

Jadwal dan periode otomatis yang sudah ada sebelum fitur ZIP mempertahankan penyimpanan PDF semula. Perubahan opsi ZIP berlaku pada periode yang dimasukkan berikutnya. Menghapus jadwal ketika periodenya masih berjalan menghentikan pemrosesan berikutnya; PDF yang sudah dibuat tetap dapat diunduh dari riwayat, sedangkan ZIP baru menunggu seluruh pekerjaan periode selesai. ZIP yang sudah selesai tetap tersimpan.

## Antrean, jeda, dan pemulihan

Antrean dan posisi metrik tersimpan di PostgreSQL. PDF yang sudah tercatat selesai tidak dibuat ulang ketika worker restart. Lock PostgreSQL melindungi penambahan periode dan pemrosesan host dari eksekusi bersamaan. Status dan nama file PDF dicatat dalam transaksi yang sama dengan kemajuan antrean. Jika proses berhenti setelah file dibuat tetapi sebelum transaksi tercatat, file tersebut bisa tersisa sebagai PDF tanpa riwayat; bagian yang belum tercatat akan dicoba kembali.

Gangguan saat pemrosesan bagian dicoba kembali setelah lima menit, maksimal tiga percobaan. Setelah tiga kegagalan bagian, worker melanjutkan metrik berikutnya dan mencatat hasil parsial/gagal. Kegagalan mengambil daftar metrik host setelah tiga percobaan menandai host gagal. Kegagalan inventaris host tidak memajukan tanggal eksekusi dan dicoba lagi setelah lima menit.

Maksimal sepuluh jadwal otomatis aktif. Setiap jadwal dibatasi tujuh periode yang belum selesai. Jika penuh, worker menunda penambahan periode, menampilkan pesan, dan mencoba lagi; tanggal berikutnya tetap menyusul setelah antrean berkurang. Setelah restart atau jeda panjang, periode yang belum masuk antrean ditambahkan berurutan, satu periode pada tiap pemeriksaan. Jadwal baru tidak mengejar tanggal eksekusi sebelum pembuatannya; laporan pertama tetap menggunakan data hari sebelumnya.

**Jeda otomatis** menghentikan pengambilan pekerjaan berikutnya; bagian yang sedang diproses dapat selesai. Penghapusan jadwal menghentikan pekerjaan berikutnya dan mempertahankan PDF, riwayat, serta data eksekusi sebelumnya. Perubahan sumber, jam, atau nama hanya berlaku pada periode yang ditambahkan berikutnya; pekerjaan yang sudah masuk antrean mempertahankan periode dan daftar hostnya.

Tabel dan detail host menampilkan **periode terbaru**. Jumlah **periode dalam antrean** juga mencakup periode sebelumnya yang masih menunggu. Riwayat dan PDF seluruh periode tersedia di halaman Laporan.

## Lokasi kode

- `frontend/components/AutomaticSchedules.tsx`: formulir, cakupan host, progres, dan tindakan antrean.
- `frontend/app/schedules/page.tsx`: integrasi halaman Jadwal; formulir jadwal satu host tetap tersedia.
- `backend/app/api/v1/auto_schedules.py`: API CRUD, preview, status, dan detail host.
- `backend/app/services/scheduler/auto.py`: pemilihan metrik, penambahan periode, antrean, retry, dan pembuatan PDF.
- `backend/app/services/report/archive.py`: kompresi, verifikasi ZIP, pembersihan PDF milik periode, dan pemulihan setelah restart.
- `frontend/components/AutomaticHostSelection.tsx`: pemilihan beberapa host dan metrik per sumber Zabbix.
- `frontend/components/AutomaticGroupPicker.tsx`: pilihan kategori dan ID host group per sumber.
- `backend/app/services/scheduler/scheduler.py`: polling dan konsumen antrean.
- `backend/app/core/database.py`: tabel `report_auto_schedules`, `report_auto_runs`, `report_auto_tasks`, serta identitas bagian pada `report_execution_logs`.
- `backend/tests/test_auto_schedules.py`, `backend/tests/test_selected_archives.py`, dan `e2e/tests/auto-schedules.spec.ts`: pengujian antrean, pilihan host/metrik, waktu, integritas ZIP, unduhan, pembersihan, dan browser.
- `backend/tests/test_schedule_windows_groups.py` dan `e2e/tests/schedule-windows-groups.spec.ts`: rentang jam, batas tanggal, pemetaan kategori, validasi membership, serta pelestarian rentang periode saat jadwal diedit.

Hasil pemeriksaan pengaturan jam, tanggal, group, dan aplikasi lokal tercatat di [automatic-time-groups-validation.json](automatic-time-groups-validation.json).

Fitur dijalankan pada Docker lokal. Login/dashboard admin tetap dinonaktifkan sesuai konfigurasi lokal sebelumnya. Implementasi ini tidak membuat atau mengaktifkan jadwal massal secara otomatis dan tidak melakukan migrasi ke server.
