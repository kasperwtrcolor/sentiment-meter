#!/bin/bash
cd backend
python3 -c "import nltk; nltk.download('vader_lexicon', quiet=True)" 2>/dev/null
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}