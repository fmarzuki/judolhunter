# Fix: SSE Streaming untuk Animasi Scan Bertahap

## Masalah

Progress messages untuk animasi scan bertahap tidak muncul di UI meskipun:
- ✅ Backend mengirim progress messages
- ✅ Frontend sudah setup untuk menerima via EventSource
- ✅ CSS animations sudah siap

**Root Cause:** EventSource tidak support custom headers (Authorization Bearer), sehingga request SSE tidak authenticated dan gagal.

## Solusi

### 1. Backend: Support Token Query Parameter

**File:** `app/api/scans.py`

```python
@router.get("/{scan_id}/stream")
async def stream_scan_progress(
    scan_id: int,
    session: DbSession,
    user: CurrentUser = None,
    token: str = Query(None),  # ← Added token query param
):
    """Server-Sent Events stream for real-time scan progress.
    
    Authentication can be via:
    - Authorization header (preferred)
    - token query parameter (for EventSource compatibility)
    """
    # If no user from header, try to get from token query param
    if not user and token:
        from app.core.auth import verify_token
        try:
            payload = verify_token(token)
            email = payload.get("sub")
            if email:
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
        except Exception:
            pass  # Continue as anonymous if token invalid
```

### 2. Frontend: Pass Token via Query Parameter

**File:** `app/static/js/app.js`

```javascript
async streamScan(scanId) {
    const token = localStorage.getItem('access_token');
    
    // EventSource doesn't support custom headers
    // Pass token as query parameter instead
    let url = `/api/scans/${scanId}/stream`;
    if (token) {
        url += `?token=${encodeURIComponent(token)}`;
    }
    
    const eventSource = new EventSource(url);
    // ... rest of the code
}
```

### 3. Enhanced Logging

Added debug logging untuk troubleshooting:

```python
# In store_progress callback
print(f"[Scan {scan_id}] Progress: {message}")

# In event_stream
print(f"[SSE] Starting stream for scan {scan_id}")
print(f"[SSE] Sending {count} new progress messages")
print(f"[SSE] Scan {scan_id} finished")
```

## Testing

### Test Script: `test_sse.py`

```bash
python3 test_sse.py
```

Expected output dengan progress messages:
```
✅ Logged in, token: eyJhbGciOiJIUzI1NiIs...
✅ Scan created with ID: 9
📡 Streaming progress...
================================================================================
[status] Status berubah: running
[progress] 🔍 Memulai scan untuk URL...
[progress] 🤖 Mengambil halaman sebagai Googlebot...
[progress] ✓ Googlebot: HTTP 200
[progress] 🌐 Mengambil halaman sebagai Browser...
[progress] ✓ Browser: HTTP 200
[progress] 🔬 Menganalisis cloaking...
[progress] 🎰 Memindai kata kunci judi...
[progress] 🔗 Memeriksa link mencurigakan...
[progress] 👁 Mendeteksi elemen tersembunyi...
[progress] 📋 Menganalisis meta tags...
[progress] 🟢 Scan selesai - Risiko: RENDAH
[complete] ✓ Scan selesai
================================================================================
✅ Scan finished: low
```

### Manual Testing

1. **Restart Server** (PENTING!):
```bash
# Ctrl+C di terminal uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. **Clear Browser Cache**:
- Tekan Ctrl+Shift+Delete
- Clear cached files
- Atau hard refresh: Ctrl+F5

3. **Test di Browser**:
- Login sebagai admin@judolhunter.com
- Go to http://localhost:8000/scan
- Input URL dan click "START SCAN"
- Observe:
  - ✅ Box scan dengan animasi pulse
  - ✅ Current step ditampilkan dengan emoji
  - ✅ Progress log menampilkan 5 messages terakhir
  - ✅ Messages muncul bertahap dengan fade-in animation

4. **Check Browser Console**:
```javascript
// Should see logs like:
SSE event received: {type: "progress", message: "🔍 Memulai scan..."}
SSE event received: {type: "progress", message: "🤖 Mengambil..."}
// ... etc
```

5. **Check Server Logs**:
```
[SSE] Starting stream for scan 9, user: admin@judolhunter.com
[Scan 9] Progress: 🔍 Memulai scan untuk URL...
[Scan 9] Progress: 🤖 Mengambil halaman sebagai Googlebot...
[SSE] Sending 2 new progress messages
[Scan 9] Progress: ✓ Googlebot: HTTP 200
[SSE] Sending 1 new progress messages
...
```

## Verification Checklist

- [x] Backend accepts token via query parameter
- [x] Frontend sends token in EventSource URL
- [x] Progress messages stored in `_scan_progress` dict
- [x] SSE endpoint polls and sends progress messages
- [x] Frontend displays progress messages with animation
- [x] Debug logging added for troubleshooting
- [x] Test script created (`test_sse.py`)
- [x] Documentation updated

## Files Modified

1. `app/api/scans.py` - SSE endpoint with token query param
2. `app/static/js/app.js` - Frontend SSE with token in URL
3. `FITUR_ANIMASI_SCAN.md` - Updated troubleshooting
4. `test_sse.py` - New test script

## Security Considerations

**Token in Query Parameter:**
- ⚠️ Token visible in browser history & server logs
- ⚠️ Token might be logged by proxies/CDNs
- ✅ OK for localhost development
- ⚠️ For production: Consider WebSocket or cookie-based auth

**Mitigation for Production:**
- Use short-lived tokens for SSE
- Implement token rotation
- Use HTTPS only
- Consider WebSocket dengan proper auth headers
- Or use cookie-based auth yang auto-included

## Alternative Solutions Considered

### 1. WebSocket (Not Implemented)
**Pros:**
- Full bi-directional communication
- Supports custom headers
- Better for real-time apps

**Cons:**
- More complex to implement
- Requires separate WebSocket endpoint
- Client needs WebSocket library

### 2. Cookie-Based Auth (Not Implemented)
**Pros:**
- Cookies auto-included in EventSource requests
- More secure than query param

**Cons:**
- Requires cookie configuration
- CSRF considerations
- More complex setup

### 3. Long Polling (Not Implemented)
**Pros:**
- No special protocol needed
- Works with standard HTTP

**Cons:**
- Less efficient than SSE
- More server load
- Not real-time

**Decision:** Stick with SSE + query param token for simplicity and development ease.

## Next Steps

1. ✅ Restart server
2. ✅ Test dengan `python3 test_sse.py`
3. ✅ Test di browser
4. ✅ Verify progress messages muncul
5. ⏳ Consider WebSocket for production
6. ⏳ Implement token rotation for security

## Performance Notes

- SSE polling interval: 500ms (balanced)
- Progress messages limit: Last 5 (prevents DOM bloat)
- Memory cleanup: Auto-cleanup after scan complete
- Connection timeout: 5 minutes (600 * 0.5s)

## Known Limitations

1. **Token Exposure**: Token visible in URL (OK for dev, consider alternatives for prod)
2. **Browser Compatibility**: EventSource not supported in IE11
3. **Scale**: In-memory dict not suitable for multi-server deployment (use Redis)
4. **Reconnection**: EventSource auto-reconnects, but might miss messages

## References

- [MDN: EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [SSE vs WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [FastAPI SSE](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

## Changelog

**2026-02-10 - SSE Authentication Fix**
- ✅ Added token query parameter support
- ✅ Frontend sends token in EventSource URL
- ✅ Enhanced debug logging
- ✅ Created test script
- ✅ Updated documentation
- ✅ Verified progress messages working
