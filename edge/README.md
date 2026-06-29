# Acoustic Audit System - Edge Module

Modul Edge ini bertanggung jawab untuk membaca data dari sensor suara (INMP441) yang terhubung ke Raspberry Pi via I2S, menghitung estimasi tingkat kebisingan (dBA), dan mengirimkannya (publish) ke MQTT Broker.

## Daftar File
- **`acoustic_edge.py`**: Skrip utama untuk membaca stream audio dari perangkat fisik INMP441, menghitung dBA secara *real-time*, dan publish ke MQTT.
- **`demo-simulate.py`**: Skrip simulator. Digunakan sebagai *fallback* (cadangan) apabila perangkat fisik bermasalah atau saat melakukan presentasi/demo tanpa hardware.
- **`.env.example`**: Konfigurasi environment variables yang wajib disetup sebelum menjalankan skrip.

## Persiapan (M4 Demo Ready)
Pastikan hal berikut sebelum presentasi/demo:
1. Copy `.env.example` menjadi `.env` dan sesuaikan nilainya:
   ```bash
   cp .env.example .env
   ```
2. Pastikan `MQTT_HOST` menunjuk ke IP VPS/Broker yang benar, dan `MQTT_USERNAME` serta `MQTT_PASSWORD` sudah valid.
3. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
   *(Untuk Raspberry Pi, pastikan driver I2S sudah aktif dan Anda sudah menjalankan `sudo apt-get install libportaudio2` jika menggunakan `sounddevice`).*

## Mode Operasi
### 1. Menjalankan Sensor Asli (Utama)
Digunakan saat hardware lengkap terhubung ke Raspberry Pi.
```bash
python acoustic_edge.py
```
> **Kalibrasi:** Anda dapat mengubah nilai `CALIBRATION_OFFSET` di dalam `.env` untuk menyesuaikan output dBA agar lebih mendekati angka yang ditunjukkan oleh alat *Sound Level Meter* sungguhan.

### 2. Menjalankan Simulator (Fallback/Cadangan)
Jika hardware gagal (misal: I2S error, kabel putus), segera matikan `acoustic_edge.py` dan jalankan simulator. Dashboard akan tetap berjalan seolah-olah data valid.
```bash
python demo-simulate.py
```

### 3. Mode Dry-Run (Tanpa MQTT)
Digunakan untuk menguji coba penangkapan suara dan melihat estimasi SPL secara lokal tanpa memerlukan koneksi ke MQTT.
```bash
python acoustic_edge.py --dry-run
```

## Mode Pembobotan Suara (Weighting)
Modul edge mendukung konfigurasi `WEIGHTING` di file `.env`:
* **Flat Weighting (`WEIGHTING=flat`)**: Estimasi SPL (Sound Pressure Level) murni dari sinyal audio tanpa pembobotan filter. (Default)
* **A-Weighting (`WEIGHTING=A`)**: Menerapkan filter frekuensi yang secara khusus mengaproksimasi sensitivitas pendengaran telinga manusia. (Membutuhkan `scipy` terinstall).

**Perhatian:** 
* Sistem dashboard hanya akan menampilkan satuan **dBA** jika payload dikirimkan menggunakan A-Weighting filter. 
* Sistem ini memberikan estimasi Sound Pressure Level (SPL). Walaupun filter A-Weighting diterapkan, pengukuran ini tidak tersertifikasi dan tetap memerlukan kalibrasi manual (via `CALIBRATION_OFFSET`) untuk mencocokkan dengan *Sound Level Meter* sungguhan.

## Tips Demo
- Jika menjalankan via `systemd` (tugas Role 4), Anda dapat melihat log secara *real-time* dengan:
  ```bash
  sudo journalctl -u acoustic-edge.service -f
  ```
- Saat mendemokan *sensor asli*, buatlah suara berisik (misal tepuk tangan) untuk menunjukkan kepada dosen bahwa grafik di *Dashboard* langsung naik secara *real-time*.
