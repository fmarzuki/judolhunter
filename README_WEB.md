# Judol Hunter - Web Interface

Modern web application for detecting websites compromised by gambling content injection (cloaking attacks). Transforms the CLI-based tool into a full-featured web platform with user authentication, tiered pricing, and quota management.

## Features

- **Dual-Fetch Scanning**: Simulates Googlebot vs browser requests to detect cloaking
- **Real-Time Progress**: Server-Sent Events for live scan updates
- **User Authentication**: JWT-based auth with role-based access control
- **Quota Management**: Tiered plans with weekly domain limits
- **Terminal UI**: Cyberpunk-style terminal interface
- **Admin Panel**: User and plan management
- **API Access**: RESTful API for programmatic access

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (async Python) |
| Frontend | HTMX + Alpine.js + TailwindCSS |
| Database | SQLAlchemy 2.0 Async (SQLite/MySQL) |
| Auth | JWT (python-jose) + passlib |
| Templates | Jinja2 |
| Rate Limiting | slowapi (with Redis support) |

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd judolhunter

# Run setup script
chmod +x setup.sh
./setup.sh
```

Or manually:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Initialize database
alembic upgrade head

# Seed initial data
python -m app.services.seeder
```

### 2. Start Development Server

```bash
source venv/bin/activate
uvicorn app.main:app --reload
```

Visit http://localhost:8000

### 3. Default Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@judolhunter.com | Admin@123 |
| Test User | test@judolhunter.com | Test@123 |

## Project Structure

```
judolhunter/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings with env-based DB switch
│   ├── dependencies.py      # Dependency injection
│   ├── core/                # Security, rate limiting, terminal utils
│   ├── models/              # SQLAlchemy models (User, Plan, Scan)
│   ├── schemas/             # Pydantic DTOs
│   ├── api/                 # FastAPI routers (auth, scans, admin)
│   ├── services/            # Business logic (scanner, quota, seeder)
│   ├── templates/           # Jinja2 templates
│   ├── static/              # CSS, JS, fonts
│   └── utils/               # Helper functions
├── alembic/                 # Database migrations
├── googlebot.py             # Original CLI (kept for reference)
├── patterns.json            # Shared pattern database
└── requirements.txt         # Python dependencies
```

## API Endpoints

### Authentication
```
POST /api/auth/register  - Register new user
POST /api/auth/login     - Login and get token
GET  /api/auth/me        - Get current user profile
```

### Scans
```
POST /api/scans          - Create scan jobs
GET  /api/scans          - List user's scans
GET  /api/scans/{id}     - Get scan details
GET  /api/scans/{id}/stream  - SSE for real-time progress
```

### Admin
```
GET    /api/admin/stats    - Platform statistics
GET    /api/admin/users    - List users
PUT    /api/admin/users/{id}  - Update user
GET    /api/admin/plans    - List plans
POST   /api/admin/plans    - Create plan
```

## Database Switch (SQLite ↔ MySQL)

Single environment variable change in `.env`:

```bash
# Development (SQLite)
DATABASE_URL=sqlite+aiosqlite:///./judolhunter.db

# Production (MySQL)
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/judolhunter
```

No code changes required.

## Quota Structure

| Tier | Max URLs/scan | Max domains/week | Price |
|------|---------------|------------------|-------|
| Unauthenticated | 5 | 2 | Free |
| Free (login) | 20 | 3 | Free |
| Lite | 100 | 15 | Rp 50K/bln |
| Pro | 500 | Unlimited | Rp 150K/bln |
| Corporate | 1000 | Unlimited | Rp 500K/bln |

## Production Deployment

### Using Gunicorn

```bash
pip install gunicorn
gunicorn app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile -
```

### Environment Variables for Production

```bash
DATABASE_URL=mysql+aiomysql://user:password@host/db
SECRET_KEY=<generate with: openssl rand -hex 32>
DEBUG=false
CORS_ORIGINS=https://yourdomain.com
```

### Using Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "app.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

## CLI Mode (Original)

The original CLI tool is preserved as `googlebot.py`:

```bash
# Single URL scan
python googlebot.py https://example.com

# Batch scan from file
python googlebot.py -f urls.txt

# Crawl mode - discovers subpages with injected content
python googlebot.py https://example.com --crawl
```

## Security Considerations

This tool detects malicious content injection for defensive purposes:
- Webmasters checking if their sites are compromised
- Security researchers analyzing cloaking attacks
- Identifying black-hat SEO spam campaigns

The tool does NOT create or distribute gambling content.

## License

MIT License - See LICENSE file for details.
