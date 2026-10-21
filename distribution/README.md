# Distribusi client starter

Folder ini menyimpan template bersih untuk mengekspor versi client tanpa mengubah konfigurasi atau branding aplikasi yang sedang berjalan. Source aplikasi diambil melalui allowlist oleh `scripts/export-starter.py`, kemudian template pada `distribution/template/` diterapkan pada salinan ekspor.

Paket tidak menyertakan `.git`, `.env`, laporan, database, sertifikat, log, akun/sesi, host nyata, maupun identitas organisasi internal. Logo baru generik; atribusi pengembang dan MPL-2.0 dipertahankan. Demo menggunakan API Zabbix sintetis dan database Docker terpisah pada loopback port 5011. Produksi client menggunakan database baru dan port default 5010.

## Membuat paket

Dengan Python 3.12, dari root repository:

```sh
python scripts/export-starter.py --output .cache/releases/zabbix-report-exporter-starter-1.0.0 --revision COMMIT_MAIN
```

Gunakan nama output baru pada setiap ekspor. Script tidak menimpa direktori/ZIP lama. Hasilnya adalah direktori source, ZIP terkompresi, dan `PACKAGE-MANIFEST.json` berisi SHA-256 setiap file. Simpan paket akhir di luar folder backup privat bila akan dikirim ke client.

Template `.env.example` disimpan sebagai `environment.example`, dan placeholder direktori sebagai `certs.keep`/`reports.keep`, agar snapshot source utama dapat menyertakannya tanpa mengikutkan data lokal. Exporter mengembalikan nama standar pada paket client.

## Isi untuk client

- `README.md`: quickstart demo dan instalasi produksi kosong.
- `docs/IMPLEMENTATION.md`: peta base code dan urutan implementasi.
- `examples/client.py`: contoh pratinjau dan unduhan PDF melalui API dengan sesi/CSRF.
- `docs/PRODUCT.md`: contoh ruang lingkup penawaran dan materi posting.
- `docs/LICENSING.md`: ketentuan MPL dan distribusi komersial, dengan rujukan resmi Mozilla.
- `docs/images/`: screenshot aplikasi demo, seluruh data sintetis.

Perbaikan source baru pada main perlu diekspor dan diuji ulang sebelum memperbarui paket client. Folder ekspor tidak membawa riwayat Git operasional; branch `client-starter` memakai source bersih sebagai riwayat awal tersendiri.
