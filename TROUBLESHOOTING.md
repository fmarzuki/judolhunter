# Troubleshooting Guide - Judol Hunter

## Error: JSON Parse Error saat Submit Scan

### Symptom
Browser menampilkan error: `JSON.parse: unexpected character at line 1 column 1`

### Root Cause
Ada 2 kemungkinan penyebab:
1. **Backend error yang tidak ter-handle dengan baik** - Server mengembalikan HTML error page atau non-JSON response
2. **Bug di error handler** - Error handler sendiri crash saat mencoba menangani error

### Solution ✅

#### Bug Fix yang Sudah Dilakukan

**1. Fixed Error Handler di `app/main.py`**

Error sebelumnya:
```python
"retry_after": exc.headers.get("Retry-After") if hasattr(exc, "headers") else None,
# ❌ Error jika exc.headers adalah None
```

Perbaikan:
```python
retry_after = None
if hasattr(exc, "headers") and exc.headers is not None:
    retry_after = exc.headers.get("Retry-After")
    
return JSONResponse(
    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    content={
        "detail": str(exc.detail) if hasattr(exc, "detail") else "Rate limit exceeded",
        "retry_after": retry_after,
    },
)
```

**2. Improved Frontend Error Handling di `app/static/js/app.js`**

- Added try-catch untuk JSON parsing
- Better error messages untuk 429 (quota limit)
- Custom error display dengan styling terminal-theme
- Auto-dismiss setelah 10 detik

## Error: 429 Quota Limit Reached

### Symptom
Error message: `Weekly domain limit reached for 'domain.com': X (max: Y)`

### Explanation
Setiap user memiliki quota untuk scanning:
- **Anonymous users**: 2 domains per week
- **Free users**: Berbeda sesuai plan
- **Premium users**: Quota lebih tinggi

### Solution

#### Option 1: Reset Quota (Development/Testing)

Gunakan script `reset_quota.py`:

```bash
# Reset quota untuk user tertentu
python3 reset_quota.py reset user@example.com

# Reset semua quota
python3 reset_quota.py reset

# Cek status quota user
python3 reset_quota.py show user@example.com
```

#### Option 2: Scan Domain yang Berbeda

Gunakan domain lain yang belum di-scan minggu ini.

#### Option 3: Tunggu Reset Mingguan

Quota akan direset otomatis setiap minggu (Monday 00:00).

#### Option 4: Upgrade Plan (Production)

Untuk production, user bisa upgrade ke plan dengan quota lebih tinggi.

## Error: Server 500 Internal Server Error

### Diagnosis

1. **Check Server Logs**
   ```bash
   # Terminal yang menjalankan uvicorn akan menampilkan error traceback
   ```

2. **Common Causes**
   - Missing dependencies
   - Database connection issues
   - Unhandled exceptions
   - Configuration errors

### Solution

1. Check terminal output untuk error traceback
2. Pastikan semua dependencies terinstall: `pip install -r requirements.txt`
3. Pastikan database file exists: `judolhunter.db`
4. Check `.env` file untuk konfigurasi

## Error: EventSource Connection Failed

### Symptom
Progress messages tidak muncul saat scanning

### Diagnosis

1. **Check Browser Console**
   - Open Developer Tools (F12)
   - Check Console tab untuk EventSource errors
   - Check Network tab untuk `/api/scans/{id}/stream` request

2. **Common Issues**
   - CORS issues
   - Authentication issues
   - Server timeout
   - Network connectivity

### Solution

1. **CORS Issue**
   - Check `app/main.py` untuk CORS settings
   - Pastikan origin allowed untuk SSE

2. **Authentication Issue**
   - EventSource tidak support custom headers
   - Untuk authenticated users, consider passing token as query param
   - Atau gunakan cookie-based auth

3. **Server Timeout**
   - Increase SSE timeout di server config
   - Check nginx/proxy timeout settings jika ada

## Database Issues

### Error: Database is Locked

**Cause**: SQLite database file sedang diakses oleh proses lain

**Solution**:
```bash
# Stop all running instances
pkill -f uvicorn

# Restart server
uvicorn app.main:app --reload
```

### Error: Table doesn't exist

**Cause**: Database migrations belum dijalankan

**Solution**:
```bash
# Run migrations
alembic upgrade head
```

## Frontend Issues

### Alpine.js Components Not Working

**Diagnosis**:
1. Check browser console untuk errors
2. Pastikan Alpine.js loaded: `console.log(window.Alpine)`

**Common Issues**:
- Alpine.js not loaded
- Syntax errors in x-data
- Component initialization errors

**Solution**:
1. Check `app/templates/base.html` untuk Alpine.js script tag
2. Validate Alpine.js syntax
3. Check for JavaScript errors in console

### CSS Animations Not Working

**Diagnosis**:
- Check browser compatibility
- Check CSS file loaded
- Disable browser extensions yang bisa interfere

**Solution**:
1. Test di browser lain
2. Check browser DevTools > Network untuk CSS loading
3. Clear browser cache

## Performance Issues

### Slow Scanning

**Possible Causes**:
- Network latency ke target site
- Target site slow to respond
- Too many concurrent scans

**Solution**:
1. Reduce concurrent scans
2. Increase timeout values
3. Add caching for repeated scans

### High Memory Usage

**Diagnosis**:
```bash
# Monitor memory
top -p $(pgrep -f uvicorn)
```

**Common Causes**:
- Memory leaks in SSE connections
- Large HTML responses not cleaned up
- Progress messages accumulating

**Solution**:
1. Restart server periodically
2. Implement proper cleanup in `_scan_progress` dict
3. Limit progress message history

## Development Tools

### Useful Commands

```bash
# Check server status
curl http://localhost:8000/

# Test API endpoint
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'

# Monitor logs
tail -f /var/log/judolhunter.log

# Check database
sqlite3 judolhunter.db "SELECT * FROM scans ORDER BY started_at DESC LIMIT 5;"
```

### Debug Mode

Enable debug mode di `.env`:
```env
DEBUG=true
LOG_LEVEL=debug
```

## Getting Help

1. Check logs di terminal
2. Check browser console
3. Review error traceback
4. Check dokumentasi API
5. Review CLAUDE.md untuk context

## Common Fixes Summary

| Issue | Quick Fix |
|-------|----------|
| JSON parse error | Restart server, check error handler |
| Quota limit | Run `reset_quota.py reset` |
| Server 500 | Check logs, verify dependencies |
| EventSource failed | Check CORS, check authentication |
| Database locked | Restart server |
| Slow scan | Reduce concurrent scans |
| Memory leak | Restart server, check cleanup |

## Prevention Best Practices

1. **Always check server logs** sebelum debugging frontend
2. **Use try-catch** untuk semua async operations
3. **Validate responses** sebelum parsing JSON
4. **Clean up resources** (EventSource, progress messages)
5. **Handle errors gracefully** dengan user-friendly messages
6. **Test with multiple URLs** untuk catch concurrency issues
7. **Monitor memory usage** during development
8. **Reset quota regularly** untuk testing

## Monitoring

### Health Check Endpoint

```bash
# Check if server is running
curl http://localhost:8000/

# Expected: 200 OK with HTML response
```

### Database Health

```bash
# Check database size
ls -lh judolhunter.db

# Check table counts
sqlite3 judolhunter.db "
SELECT 
  'scans' as table_name, COUNT(*) as count FROM scans
UNION ALL
SELECT 'users', COUNT(*) FROM users
UNION ALL  
SELECT 'usage_trackers', COUNT(*) FROM usage_trackers;
"
```

### Memory Usage

```bash
# Check Python process memory
ps aux | grep uvicorn

# For detailed memory profile
pip install memory_profiler
python -m memory_profiler app/main.py
```
