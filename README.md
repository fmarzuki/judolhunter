# Judol Hunter - Deteksi URL Tersusupi Link Judol (Judi Online)

**Judol Hunter** adalah tool untuk mendeteksi website yang telah diretas dan disusupi konten judi online (judol) menggunakan teknik **cloaking**. Tersedia dalam mode **CLI** dan **Web App**. Tool ini bekerja dengan mensimulasikan request sebagai Googlebot dan membandingkannya dengan request browser biasa untuk mengidentifikasi perbedaan konten yang mencurigakan.

## Fitur Utama

- **Deteksi Cloaking** - Membandingkan response Googlebot vs browser biasa menggunakan SequenceMatcher untuk mendeteksi konten berbeda yang disajikan ke search engine
- **Deteksi Keyword Judol** - Memindai 87+ keyword judi online/slot/togel dari database pattern (`patterns.json`)
- **Deteksi Link Mencurigakan** - Mengidentifikasi link eksternal ke domain judi yang sudah dikenal (46+ domain)
- **Deteksi Elemen Tersembunyi** - Menemukan konten spam yang disembunyikan via CSS (`display:none`, `visibility:hidden`, `opacity:0`, dll)
- **Deteksi Meta Injection** - Memeriksa tag `<title>`, `<meta description>`, `<meta keywords>`, dan Open Graph yang disusupi
- **Crawl Mode** - Otomatis menemukan subpage terinfeksi dengan membandingkan URL yang hanya muncul di response Googlebot
- **Penilaian Risiko** - Klasifikasi otomatis: `clean`, `suspicious`, `infected` dengan level `low`/`medium`/`high`/`critical`
- **Web App** - Antarmuka web dengan terminal UI, autentikasi, scan history, dan tiered quotas
- **Batch Scan** - Mendukung scan banyak URL dari file teks
- **Export JSON** - Hasil scan bisa disimpan ke file JSON

## Instalasi

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Sesuaikan konfigurasi
```

## Penggunaan CLI

```bash
python googlebot.py https://example.com              # Scan satu URL
python googlebot.py -f urls.txt                       # Scan dari file
python googlebot.py https://example.com --crawl       # Crawl + scan subpage
python googlebot.py -f urls.txt -o hasil.json -v      # Batch scan, export JSON, verbose
```

### Opsi CLI

| Flag | Deskripsi |
|------|-----------|
| `url` | URL yang akan di-scan |
| `-f`, `--file` | File berisi daftar URL (satu per baris) |
| `-o`, `--output` | Simpan hasil ke file JSON |
| `-c`, `--crawl` | Crawl subpage untuk cari halaman tersusupi |
| `-v`, `--verbose` | Tampilkan detail proses |

## Web App

### Menjalankan (Development)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Buka `http://localhost:8000` di browser.

### Menjalankan (Production)

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Konfigurasi `.env`

| Variable | Default | Deskripsi |
|----------|---------|-----------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./judolhunter.db` | SQLite (dev) atau MySQL (prod) |
| `SECRET_KEY` | - | Secret key untuk JWT, generate dengan `openssl rand -hex 32` |
| `DEBUG` | `false` | Mode debug |
| `CORS_ORIGINS` | `http://localhost:8000` | Allowed CORS origins (comma-separated) |
| `SCAN_TIMEOUT` | `15.0` | Timeout per URL dalam detik |
| `MAX_URLS_PER_SCAN_UNAUTH` | `5` | Maks URL per scan (anonymous) |
| `MAX_DOMAINS_PER_WEEK_UNAUTH` | `2` | Maks domain per minggu (anonymous) |
| `MAX_URLS_PER_SCAN_FREE` | `20` | Maks URL per scan (free plan) |
| `MAX_DOMAINS_PER_WEEK_FREE` | `3` | Maks domain per minggu (free plan) |

### Fitur Web App

- **Terminal UI** - Antarmuka bergaya terminal hacker
- **Autentikasi** - Register/login dengan JWT
- **Real-time Scan** - Progress scan via SSE (Server-Sent Events)
- **Scan History** - Riwayat scan tersimpan di database
- **Tiered Quotas** - Anonymous, Free, dan Admin dengan batas berbeda
- **Admin Dashboard** - Manajemen user dan scan

## Cara Kerja

1. Fetch halaman dengan User-Agent **Googlebot/2.1** dan **Chrome browser**
2. Bandingkan kedua response untuk deteksi **cloaking** (similarity < 70% = cloaking)
3. Scan konten Googlebot untuk **keyword judol**, **link mencurigakan**, **elemen tersembunyi**, dan **meta injection**
4. Tentukan risk level berdasarkan kombinasi temuan
5. Tampilkan ringkasan hasil dalam tabel/web UI

## Dependensi

- `fastapi` + `uvicorn` - Web framework dan ASGI server
- `sqlalchemy` + `aiosqlite` - Database ORM (async)
- `httpx` - HTTP client untuk dual-fetch (Googlebot & browser UA)
- `beautifulsoup4` - HTML parsing dan ekstraksi konten
- `rich` - Output terminal berwarna (CLI mode)
- `python-jose` + `passlib` - JWT auth dan password hashing

## Support

<a href="https://www.buymeacoffee.com/fmarzuki" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>
