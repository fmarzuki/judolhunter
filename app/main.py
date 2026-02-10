"""Judol Hunter - FastAPI Web Application Entry Point."""
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.scans import router as scans_router
from app.config import get_settings
from app.models.scan import Scan
from app.models.user import Plan, User

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print(f"🚀 Judol Hunter v{settings.APP_VERSION} starting...")
    print(f"📦 Database: {settings.database_type.upper()}")
    print(f"🔧 Debug: {settings.DEBUG}")

    yield

    # Shutdown
    print("👋 Judol Hunter shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Deteksi URL tersusupi link judi online dengan simulasi Googlebot",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(status.HTTP_401_UNAUTHORIZED)
async def unauthorized_handler(request: Request, exc):
    """Handle unauthorized errors."""
    if request.headers.get("accept") == "application/json":
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Authentication required"},
        )
    # Redirect to login for web requests
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login", status_code=302)


@app.exception_handler(status.HTTP_403_FORBIDDEN)
async def forbidden_handler(request: Request, exc):
    """Handle forbidden errors."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc.detail) if hasattr(exc, "detail") else "Access denied"},
    )


@app.exception_handler(status.HTTP_429_TOO_MANY_REQUESTS)
async def rate_limit_handler(request: Request, exc):
    """Handle rate limit errors."""
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


# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="app/templates")


# Include API routers
app.include_router(auth_router)
app.include_router(scans_router)
app.include_router(admin_router)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
    }


# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Render landing page."""
    return templates.TemplateResponse("index.html", {"request": request})


# Scan pages
@app.get("/scan", response_class=HTMLResponse)
async def new_scan(request: Request):
    """Render new scan page."""
    return templates.TemplateResponse("scan/new.html", {"request": request})


@app.get("/history", response_class=HTMLResponse)
async def scan_history(request: Request):
    """Render scan history page."""
    return templates.TemplateResponse("scan/history.html", {"request": request})


@app.get("/scans/{scan_id}", response_class=HTMLResponse)
async def scan_detail(request: Request, scan_id: int):
    """Render scan detail page."""
    return templates.TemplateResponse(
        "scan/results.html",
        {"request": request, "scan_id": scan_id}
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render user dashboard."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


# Auth pages
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login page."""
    return templates.TemplateResponse("auth/login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Render registration page."""
    return templates.TemplateResponse("auth/register.html", {"request": request})


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    """Render pricing page."""
    return templates.TemplateResponse("index.html", {"request": request})  # Reuse landing for now


# CLI mode entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
