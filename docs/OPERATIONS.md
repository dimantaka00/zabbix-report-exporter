# Operasional dan pemulihan client

Seluruh perintah produksi dijalankan dari folder project dengan `.env` client. Jangan memakai file Compose demo untuk produksi.

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 100 backend worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Sebelum upgrade, simpan salinan source/config/image versi berjalan serta backup database dan seluruh laporan. `.env`, sertifikat, dump, dan laporan bersifat privat; simpan di luar project dengan izin terbatas. Backup bukan hanya commit Git.

Untuk snapshot yang konsisten, hentikan sementara pembuat laporan dan API selama pengambilan database serta file laporan. Jangan hapus volume ketika melakukan backup:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop worker backend
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > ../client-backup/database.dump
```

Siapkan folder backup privat terlebih dahulu. Salin `.env`, `certs/`, `storage/reports/`, source, serta file Compose ke lokasi tersebut. Pertahankan snapshot sebelumnya. Setelah salinan selesai, hidupkan kembali service:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml start backend worker
```

Pengalihan stdout dump biner di atas menggunakan shell POSIX atau PowerShell 7.4+. Pada Windows PowerShell 5.1, gunakan `docker compose ... exec ... pg_dump --file=/tmp/client.dump`, lalu `docker compose ... cp postgres:/tmp/client.dump ../client-backup/database.dump` agar dump tidak diubah oleh encoding shell.

Uji pemulihan di project Docker terpisah dengan database kosong: pulihkan dump melalui `pg_restore`, letakkan laporan dan sertifikat pada direktori yang sesuai, salin konfigurasi privat, lalu jalankan image/source versi yang cocok. Periksa jadwal, akun, serta unduhan laporan sebelum melakukan pemulihan produksi. Pembersihan volume dan penimpaan database produksi memerlukan prosedur terpisah dan tidak dijalankan oleh starter ini.

Jika grafik kosong, bandingkan sumber, host/item, timezone, rentang tanggal, interval, dan retensi history dengan Zabbix. Gangguan transport sementara dicoba ulang; data yang memang tidak tersedia tetap ditandai kosong. Laporan parsial menyimpan peringatan pada riwayat. PDF yang sudah diekspor adalah snapshot dan tidak memperbarui dirinya sendiri.
