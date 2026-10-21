# Detail host sebelum ekspor PDF

Pada halaman Monitoring, pilih sumber Zabbix dan host. Panel Detail host muncul tepat di bawah pemilih host dan dapat dilipat melalui judulnya.

Panel menampilkan:

- Nama tampilan dan nama teknis host.
- Groups dan template yang langsung tertaut ke host.
- Description, termasuk pemisahan baris dari Zabbix.
- Proxy atau proxy group, termasuk assigned proxy bila dikonfigurasi; host yang dipantau langsung menampilkan Zabbix server.
- Seluruh interface: Agent, SNMP, IPMI, atau JMX, beserta IP address, DNS, port, interface default, dan alamat polling.
- SNMPv1/v2c/v3, bulk request, dan security level untuk SNMPv3.

Port yang menggunakan macro ditampilkan sebagaimana konfigurasi Zabbix, tanpa menebak atau membuka nilai macro. Template yang ditampilkan adalah template langsung, bukan seluruh rantai pewarisan. Data yang tidak diisi memiliki keterangan kosong. Detail host yang dinonaktifkan tetap dapat dilihat.

Pergantian host membatalkan permintaan sebelumnya. Pergantian sumber Zabbix mengosongkan pilihan host. Kegagalan permintaan detail menyediakan tombol Coba lagi dan tidak menghalangi pemilihan metrik atau ekspor laporan. Bila API token tidak boleh membaca nama proxy, panel mempertahankan ID proxy dan menunjukkan keterangan; field host lainnya tetap tersedia.

Endpoint: `GET /api/v1/zabbix/hosts/{hostid}/details?server_id=primary|secondary`. Backend hanya mengirim versi, bulk, dan security level dari detail SNMP. Community string, security name, authentication/privacy password, dan raw SNMP details tidak dikirim ke browser. Panel ini merupakan pemeriksaan dashboard sebelum ekspor; struktur laporan PDF tidak ditambah dengan detail host.

## Kompatibilitas API

Backend mendeteksi versi setiap sumber. Zabbix 6.0 memakai `selectGroups` dan `proxy_hostid`; 6.2/6.4 memakai `selectHostGroups` dan proxy lama; 7.x memakai `selectHostGroups`, `monitored_by`, `proxyid`, `proxy_groupid`, dan `assigned_proxyid`. Nama proxy lama memakai properti `host`, sedangkan 7.x memakai `name`.

Referensi resmi: [host.get 6.0](https://www.zabbix.com/documentation/6.0/en/manual/api/reference/host/get), [host.get 6.2](https://www.zabbix.com/documentation/6.2/en/manual/api/reference/host/get), [host object 7.0](https://www.zabbix.com/documentation/7.0/en/manual/api/reference/host/object), [proxy object 7.4](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/proxy/object), dan [host interface object](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/hostinterface/object).

## Validasi

Pengujian backend mencakup selector group/proxy antarversi, beberapa interface, penyaringan kredensial SNMP, host disabled, penolakan ID tidak valid, host tidak dapat diakses, proxy group, dan keterbatasan izin proxy. Pengujian browser mencakup tampilan desktop/ponsel dan kedua tema, panel yang dapat dilipat, field kosong, pergantian host/sumber, retry, dan respons terlambat yang tidak boleh menggantikan host baru.

Validasi 9 Oktober 2026: **97 pengujian backend** lulus, **52 kasus browser** lulus (dua kasus retry diulang setelah koreksi locator pengujian), dan build frontend/Docker berhasil. Pembacaan langsung berhasil pada Zabbix 1 versi 7.4.10 serta Zabbix 2 versi 6.0.42. Dashboard produksi diperiksa pada desktop dan ponsel, kedua tema, dengan pergantian sumber dan tanpa error JavaScript. Ringkasan pemeriksaan tersedia pada [hasil validasi](host-details-validation.json).

Perubahan disertakan dalam snapshot lengkap melalui `scripts/backup-project.ps1`; panduan pemulihan tersedia dalam setiap folder snapshot dan pada [backup dan rollback](backup-recovery.md).
