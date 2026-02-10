# Fitur Animasi Scan Bertahap

## Overview

Fitur ini menambahkan animasi interaktif yang menampilkan progress real-time untuk setiap URL yang sedang di-scan, memberikan feedback visual yang jelas kepada user tentang proses scanning yang sedang berlangsung.

## Fitur Utama

### 1. **Progress Messages Real-time**
- Setiap tahap scan mengirimkan pesan progress via Server-Sent Events (SSE)
- Progress messages dalam Bahasa Indonesia dengan emoji untuk visual clarity
- Messages meliputi:
  - 🔍 Memulai scan
  - 🤖 Mengambil halaman sebagai Googlebot
  - 🌐 Mengambil halaman sebagai Browser
  - 🔬 Menganalisis cloaking
  - 🎰 Memindai kata kunci judi
  - 🔗 Memeriksa link mencurigakan
  - 👁 Mendeteksi elemen tersembunyi
  - 📋 Menganalisis meta tags
  - 🟢/🟡/🔴 Status akhir dengan level risiko

### 2. **Animasi Visual**
- **Scan Pulse**: Border box yang berdenyut dengan glow effect untuk URL yang sedang di-scan
- **Scan Line**: Garis animasi yang bergerak horizontal di bagian atas scan box
- **Fade-in Slide**: Setiap progress message muncul dengan animasi slide dari kiri
- **Loading Dots**: Animasi titik-titik pada current step indicator

### 3. **Progress Log**
- Menampilkan 5 pesan progress terakhir
- Auto-update saat ada pesan baru
- Styling terminal-style dengan prefix `›`

### 4. **Multi-URL Support**
- Streaming progress untuk semua URLs secara paralel
- Setiap URL memiliki progress indicator sendiri
- Auto-scroll ke scan results saat mulai

## Perubahan Teknis

### Backend (`app/api/scans.py`)
```python
# In-memory storage untuk progress messages
_scan_progress = defaultdict(list)

# Store progress callback
async def store_progress(message: str, data: dict | None = None):
    _scan_progress[scan_id].append({
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data
    })

# SSE stream mengirim progress messages
for msg in messages[last_message_count:]:
    event = ScanStreamEvent(
        type="progress",
        scan_id=scan.id,
        url=scan.url,
        message=msg['message'],
        data={...}
    )
    yield event.sse_format()
```

### Scanner Service (`app/services/scanner.py`)
```python
# Progress messages dengan emoji dan bahasa Indonesia
await progress_callback.notify("🔍 Memulai scan untuk URL...")
await progress_callback.notify("🤖 Mengambil halaman sebagai Googlebot...")
# ... dll
```

### Frontend (`app/static/js/app.js`)
```javascript
// Track progress untuk setiap scan
this.scans = this.scans.map(scan => ({
    ...scan,
    progress: [],
    currentStep: null,
    isScanning: true
}));

// Stream semua scans
for (const scan of this.scans) {
    this.streamScan(scan.id);
}

// Handle progress events
if (event.type === 'progress') {
    scan.currentStep = event.message;
    scan.progress.push({
        message: event.message,
        timestamp: event.timestamp
    });
}
```

### Template (`app/templates/scan/new.html`)
```html
<!-- Progress container dengan animasi -->
<div class="scan-progress-container">
    <div class="scan-progress-step">
        <span class="terminal-loading" x-text="scan.currentStep"></span>
    </div>
    
    <!-- Progress log (5 messages terakhir) -->
    <div class="scan-progress-log">
        <template x-for="(msg, idx) in scan.progress.slice(-5)">
            <div class="scan-progress-log-item" x-text="'› ' + msg.message"></div>
        </template>
    </div>
</div>
```

### Styling (`app/static/css/terminal.css`)
```css
/* Scan pulse animation */
.scan-result.scanning {
    animation: scanPulse 2s ease-in-out infinite;
}

/* Moving scan line */
.scan-result.scanning::before {
    animation: scanLine 2s linear infinite;
}

/* Fade in slide untuk progress messages */
.scan-progress-log-item {
    animation: fadeInSlide 0.3s ease-out;
}
```

## User Experience Improvements

### Sebelum
- User hanya melihat "SCANNING..." tanpa detail
- Tidak ada feedback tentang progress scan
- User tidak tahu tahap mana yang sedang berjalan
- Hanya scan pertama yang di-stream

### Sesudah
- User melihat setiap tahap scan secara detail
- Progress messages dengan emoji dan bahasa Indonesia
- Visual feedback dengan animasi pulse dan scan line
- Progress log menampilkan history 5 langkah terakhir
- Semua URLs di-stream secara paralel
- Status akhir dengan icon yang jelas (🟢🟡🔴)

## Testing

### Manual Testing Steps
1. Buka `/scan` (New Scan page)
2. Masukkan beberapa URLs (misalnya 3-5 URLs)
3. Klik "START SCAN"
4. Observe:
   - ✅ Setiap URL box menampilkan animasi pulse
   - ✅ Current step ditampilkan dengan loading dots
   - ✅ Progress log menampilkan messages secara bertahap
   - ✅ Animasi scan line bergerak di bagian atas box
   - ✅ Messages muncul dengan fade-in animation
   - ✅ Status akhir ditampilkan dengan icon dan warna yang tepat

### Example URLs untuk Testing
```
https://example.com
https://google.com
https://github.com
```

## Konfigurasi

### Polling Interval
Default: 500ms (0.5 detik)
```python
# app/api/scans.py
await asyncio.sleep(0.5)  # Polling interval
```

### Progress Log Limit
Default: 5 messages terakhir
```html
<!-- app/templates/scan/new.html -->
scan.progress.slice(-5)
```

### Memory Cleanup
Progress messages dihapus dari memory setelah scan selesai:
```python
if scan_id in _scan_progress:
    del _scan_progress[scan_id]
```

## Browser Compatibility

- ✅ Chrome/Edge (Modern)
- ✅ Firefox (Modern)
- ✅ Safari (Modern)
- ⚠️ IE11 (Not supported - EventSource tidak tersedia)

## Performance Considerations

- In-memory storage untuk progress messages (ringan)
- SSE polling setiap 500ms (balanced antara responsiveness dan load)
- Progress log dibatasi 5 messages (mencegah DOM bloat)
- Auto-cleanup setelah scan selesai (memory efficient)
- CSS animations menggunakan transform untuk better performance

## Future Enhancements

- [ ] Websocket support untuk bi-directional communication
- [ ] Progress percentage indicator
- [ ] Pause/Resume scan capability
- [ ] Export progress log
- [ ] Dark/Light theme toggle
- [ ] Sound notifications untuk scan completion
- [ ] Desktop notifications (dengan permission)

## Troubleshooting

### Progress messages tidak muncul

**Diagnosis:**
1. Check browser console untuk EventSource errors
2. Pastikan SSE endpoint `/api/scans/{scan_id}/stream` accessible
3. Check network tab untuk streaming connection
4. Check server logs untuk "[SSE]" dan "[Scan X] Progress:" messages

**Common Issues:**

**Issue 1: EventSource Authentication Error**
- **Symptom**: Connection gagal, 401/403 error
- **Cause**: EventSource tidak support custom headers
- **Solution**: Token dikirim via query parameter `?token=...`

**Issue 2: No Progress Messages**
- **Symptom**: Status changes terlihat tapi tidak ada detail progress
- **Cause**: Progress callback tidak terhubung ke in-memory storage
- **Solution**: Check server logs untuk `[Scan X] Progress:` messages

**Issue 3: SSE Connection Closed Early**
- **Symptom**: Stream langsung close setelah connect
- **Cause**: Access denied atau scan not found
- **Solution**: Check ownership, pastikan user yang login adalah owner scan

**Testing SSE:**

```bash
# Test SSE streaming dengan script
python3 test_sse.py

# Expected output:
# ✅ Logged in
# ✅ Scan created with ID: X
# 📡 Streaming progress...
# [progress] 🔍 Memulai scan untuk URL...
# [progress] 🤖 Mengambil halaman sebagai Googlebot...
# [progress] ✓ Googlebot: HTTP 200
# [complete] ✓ Scan selesai
```

### Animasi tidak smooth
- Pastikan browser mendukung CSS animations
- Check GPU acceleration di browser settings
- Reduce CSS animation complexity jika device lemah

### Memory leak concern
- Progress messages di-cleanup setelah scan selesai
- EventSource di-close setelah completion
- Monitor dengan browser DevTools memory profiler

## Credits

Dikembangkan dengan menggunakan:
- FastAPI untuk backend async
- Alpine.js untuk reactive UI
- Server-Sent Events (SSE) untuk real-time streaming
- CSS3 animations untuk visual effects
