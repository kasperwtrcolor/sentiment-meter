#!/bin/bash
set -e

# Find the backend directory
if [ -d "/app/backend" ]; then
    cd /app/backend
elif [ -d "backend" ]; then
    cd backend
fi

echo "Working directory: $(pwd)"
echo "Files: $(ls -la)"

# Download NLTK data
python -c "import nltk; nltk.download('vader_lexicon', quiet=True)" 2>/dev/null

# Start the server
exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}