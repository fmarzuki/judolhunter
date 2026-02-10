# Admin Unlimited Quota

## Overview

Admin user (`admin@judolhunter.com`) sekarang memiliki **unlimited quota** untuk scanning:
- ✅ **Tidak ada batasan jumlah URL per scan** (max 1000 untuk pydantic validation)
- ✅ **Tidak ada batasan domain per minggu** (unlimited)
- ✅ **Bypass semua quota checking**

## User Roles dan Quota

### Admin Role
**Email:** `admin@judolhunter.com`
**Password:** `Admin@123`
**Plan:** Corporate
**Quota:**
- URLs per scan: **Unlimited** (max 1000 karena schema validation)
- Domains per week: **Unlimited**

### Regular User (Test)
**Email:** `test@judolhunter.com`
**Password:** `Test@123`
**Plan:** Pro
**Quota:**
- URLs per scan: 500
- Domains per week: Unlimited

### Anonymous User
**Quota:**
- URLs per scan: 5
- Domains per week: 2

## Technical Implementation

### 1. Quota Bypass di Rate Limiter

File: `app/core/rate_limiter.py`

```python
async def check_quota(...):
    # Bypass quota for admin
    if user and user.role == UserRole.ADMIN:
        return True, None
    
    # ... normal quota checking untuk user biasa
```

### 2. Quota Service Update

File: `app/services/quota_service.py`

```python
@staticmethod
async def get_user_quota_limits(user: User) -> dict[str, Any]:
    # Bypass quota for admin (unlimited)
    if user.role == UserRole.ADMIN:
        return {
            "max_urls_per_scan": None,  # Unlimited
            "max_domains_per_week": None,  # Unlimited
        }
    
    # ... return quota untuk plan lainnya
```

### 3. Unlimited Handling

File: `app/core/rate_limiter.py`

```python
# Check URL count limit (None means unlimited)
if plan.max_urls_per_scan and url_count > plan.max_urls_per_scan:
    return (False, f"URL limit exceeded: {url_count}")

# Check domain weekly limit (None means unlimited)
if plan.max_domains_per_week is None:
    return True, None  # Unlimited domains
```

## Usage

### Login sebagai Admin

1. **Via Web UI:**
   - Go to http://localhost:8000/login
   - Email: `admin@judolhunter.com`
   - Password: `Admin@123`

2. **Via API:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@judolhunter.com",
    "password": "Admin@123"
  }'
```

### Scan dengan Admin

Setelah login sebagai admin, Anda bisa:

1. **Scan banyak URLs sekaligus** (sampai 1000 URLs)
2. **Scan domain yang sama berulang kali** tanpa batasan weekly limit
3. **Tidak perlu reset quota**

### Example: Scan Multiple URLs

```bash
# Login dulu untuk dapat token
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@judolhunter.com","password":"Admin@123"}' \
  | jq -r '.access_token')

# Scan banyak URLs
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "urls": [
      "https://example1.com",
      "https://example2.com",
      "https://example3.com",
      "https://unsoed.ac.id",
      "https://unsoed.ac.id/page1",
      "https://unsoed.ac.id/page2"
    ]
  }'
```

## Testing

### Test Script

Jalankan test script untuk verify admin quota bypass:

```bash
python3 test_admin_quota.py
```

Expected output:
```
================================================================================
🧪 TESTING ADMIN QUOTA BYPASS
================================================================================
✅ Admin user ditemukan: admin@judolhunter.com
   Role: admin
   Plan: corporate

✅ Admin dapat scan 100 URLs tanpa batasan!
   Quota check: BYPASS

📊 Perbandingan dengan user biasa (test@judolhunter.com):
   ✅ User biasa dapat scan 10 URLs

📋 Daftar Users dan Quota:
================================================================================

👤 Administrator
   Email: admin@judolhunter.com
   Role: admin
   Plan: corporate
   Max URLs per scan: ♾️  Unlimited
   Max domains per week: ♾️  Unlimited

👤 Test User
   Email: test@judolhunter.com
   Role: user
   Plan: pro
   Max URLs per scan: 500
   Max domains per week: ♾️  Unlimited
```

### Manual Testing

1. **Test dengan Web UI:**
   - Login sebagai admin
   - Go to `/scan`
   - Input banyak URLs (lebih dari 5)
   - Scan domain yang sama berulang kali
   - Tidak ada error quota limit

2. **Check Quota Status:**
```bash
# Show admin quota status
python3 reset_quota.py show admin@judolhunter.com

# Output: Admin tidak perlu quota tracking karena unlimited
```

## Troubleshooting

### Issue: Admin masih terkena quota limit

**Check:**
1. Pastikan user role adalah `admin`:
```bash
python3 -c "
import asyncio
from sqlalchemy import select
from app.utils.db import async_session_maker
from app.models.user import User

async def check():
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.email == 'admin@judolhunter.com')
        )
        admin = result.scalar_one_or_none()
        print(f'Role: {admin.role}')
        print(f'Is Admin: {admin.role == \"admin\"}')

asyncio.run(check())
"
```

2. Restart server untuk apply changes:
```bash
# Stop server (Ctrl+C)
# Start again
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

3. Clear browser cache dan login ulang

### Issue: Schema validation error (max 1000 URLs)

**Cause:** Pydantic schema masih membatasi `max_length=1000`

**Solution:** Untuk scan lebih dari 1000 URLs, split request menjadi batch:
```python
# Split URLs into batches of 1000
batch_size = 1000
for i in range(0, len(all_urls), batch_size):
    batch = all_urls[i:i+batch_size]
    # Submit batch scan
```

## Plan Comparison

| Plan | URLs/Scan | Domains/Week | Price |
|------|-----------|--------------|-------|
| Anonymous | 5 | 2 | Free |
| Free | 20 | 3 | Free |
| Lite | 100 | 15 | Paid |
| Pro | 500 | ♾️ Unlimited | Paid |
| Corporate | ♾️ Unlimited | ♾️ Unlimited | Paid |
| **Admin** | **♾️ Unlimited** | **♾️ Unlimited** | **-** |

## Database Schema

Admin user sudah dibuat dengan:
- `role = 'admin'`
- `plan_type = 'corporate'`
- `is_active = True`
- `is_verified = True`

Tidak perlu manual setup, sudah otomatis saat run `create_users.py`.

## Security Notes

1. **Admin credentials** harus dijaga ketat
2. Jangan expose admin credentials di code atau logs
3. Gunakan environment variables untuk production
4. Implement 2FA untuk admin di production
5. Monitor admin scan activity untuk detect abuse

## Future Enhancements

- [ ] Add SUPERADMIN role dengan additional privileges
- [ ] Add audit logging untuk admin scans
- [ ] Add rate limiting bypass untuk specific IPs
- [ ] Add temporary quota boost for specific users
- [ ] Add quota monitoring dashboard
- [ ] Add email notifications untuk high usage

## Related Files

- `app/core/rate_limiter.py` - Quota checking logic
- `app/services/quota_service.py` - Quota service
- `app/models/user.py` - User model dengan roles
- `create_users.py` - Script untuk create admin user
- `test_admin_quota.py` - Test script untuk verify quota bypass
- `reset_quota.py` - Script untuk reset quota (tidak perlu untuk admin)

## Support

Jika ada issue atau pertanyaan:
1. Check TROUBLESHOOTING.md
2. Run test script: `python3 test_admin_quota.py`
3. Check server logs untuk errors
4. Verify user role di database

## Changelog

### 2026-02-10
- ✅ Implemented admin quota bypass
- ✅ Fixed unlimited quota handling (None values)
- ✅ Added admin role checking
- ✅ Updated quota service untuk admin
- ✅ Created test script
- ✅ Documentation complete
