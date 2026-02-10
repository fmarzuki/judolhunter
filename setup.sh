#!/bin/bash
# Judol Hunter - Web Interface Setup Script

set -e

echo "=========================================="
echo "  Judol Hunter Web Interface Setup"
echo "=========================================="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip -q

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# Copy environment file if not exists
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file..."
    cp .env.example .env
    echo "✓ .env file created (please update with your settings)"
else
    echo "✓ .env file exists"
fi

# Initialize database
echo ""
echo "Initializing database..."

# Run Alembic migrations
if command -v alembic &> /dev/null; then
    alembic upgrade head
else
    python -m alembic upgrade head
fi
echo "✓ Database initialized"

# Run seeder
echo ""
echo "Seeding initial data..."
python -m app.services.seeder
echo "✓ Initial data seeded"

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "To start the development server:"
echo ""
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload"
echo ""
echo "Then visit: http://localhost:8000"
echo ""
echo "Default accounts:"
echo "  Admin: admin@judolhunter.com / Admin@123"
echo "  Test:  test@judolhunter.com / Test@123"
echo ""
