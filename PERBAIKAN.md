# Perbaikan JSON Parse Error

## Masalah
Error `JSON.parse: unexpected character at line 1 column 1 of the JSON data` terjadi ketika:
1. User tanpa login (anonymous) mencoba mengakses aplikasi
2. Frontend mencoba check autentikasi dengan token yang invalid/expired
3. Response dari server bukan JSON yang valid

## Solusi yang Diterapkan

### 1. **Frontend (`app/static/js/app.js`)**
- ✅ Menambahkan error handling yang lebih baik di `checkAuth()`
- ✅ Menghapus token yang invalid secara otomatis
- ✅ Handle response non-JSON dengan proper error logging
- ✅ Menambahkan content-type check sebelum parse JSON di `submitScan()`

### 2. **Backend Authentication (`app/dependencies.py`)**
- ✅ Mengubah `get_current_user()` untuk return `None` jika token invalid
- ✅ Sebelumnya: raise exception → sekarang: return None untuk anonymous access
- ✅ Hanya user yang benar-benar butuh auth yang akan dapat 401 error

### 3. **Auth Endpoint (`app/api/auth.py`)**
- ✅ Endpoint `/api/auth/me` sekarang menggunakan `AuthUser` dependency
- ✅ Akan return proper JSON 401 error jika tidak authenticated
- ✅ Error response selalu dalam format JSON yang valid

### 4. **Scan Endpoint (`app/api/scans.py`)**
- ✅ Menambahkan `= None` default untuk parameter `user` di `create_scan()`
- ✅ Anonymous users sekarang bisa melakukan scan dengan batasan quota
- ✅ Menambahkan debug logging untuk troubleshooting

### 5. **Response Schema (`app/schemas/scan.py`)**
- ✅ Menambahkan field `user_id` dan `session_id` ke `ScanResponse`
- ✅ Menambahkan default values `None` untuk optional fields
- ✅ Menambahkan JSON encoder untuk datetime serialization

## Quota Limits

### Anonymous Users (Tanpa Login)
- 5 URLs per scan
- 2 domains per minggu

### Free Users (Login)
- 20 URLs per scan  
- 3 domains per minggu

### Lite Plan
- 100 URLs per scan
- 15 domains per minggu

### Pro & Corporate
- 500-1000 URLs per scan
- Unlimited domains

## Testing

Untuk test manual:
1. Buka `http://localhost:8000/scan` tanpa login
2. Masukkan 1-2 URL untuk di-scan
3. Klik "START SCAN"
4. Harusnya scan berjalan tanpa error JSON parsing

Jika ada error, check:
1. Console browser (F12) untuk error messages
2. Server logs untuk traceback
3. Network tab untuk melihat response yang sebenarnya

## Files yang Diubah

1. `app/static/js/app.js` - Frontend error handling
2. `app/dependencies.py` - Authentication logic  
3. `app/api/auth.py` - Auth endpoint
4. `app/api/scans.py` - Scan endpoint & background task
5. `app/schemas/scan.py` - Response schema
6. `app/templates/scan/new.html` - Template fixes

## Langkah Selanjutnya

Untuk menjalankan aplikasi:

```bash
# Install dependencies (jika belum)
pip install -r requirements.txt

# Jalankan server
python -m uvicorn app.main:app --reload --port 8000

# Atau dengan script
python app/main.py
```

Kemudian akses: `http://localhost:8000/scan`
