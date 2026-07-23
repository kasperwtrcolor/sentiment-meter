# Sentiment Meter

**AI-powered sentiment & emotion analysis as a paid web service.**

Type any name — get instant polarity scoring, emotion detection, and a visual report from 100+ news articles. Powered by VADER + Emotion Lexicon.

## Architecture

```
┌──────────┐     ┌──────────────┐
│  Vercel  │────▶│   Railway    │
│ (Static) │     │ (FastAPI)    │
├──────────┤     ├──────────────┤
│ index    │     │ /analyze     │
│ app.html │     │ /analyze/demo│
│ dashboard│     │ /signup      │
│ style.css│     │ /checkout    │
└──────────┘     │ /credits     │
                 │ /history     │
                 │ /stripe-wh.. │
                 └──────────────┘
```

## Quick Start (Local)

```bash
# Backend
cd backend
cp .env.example .env  # Add your Stripe keys
pip install -r requirements.txt
python main.py

# Frontend (just open the HTML)
open frontend/index.html
```

## Deploy

### Option 1: Vercel + Railway (Recommended)

1. **Frontend → Vercel**
   - Connect `sentiment-meter/frontend` to Vercel
   - Vercel auto-detects `vercel.json`

2. **Backend → Railway**
   - Connect `sentiment-meter/backend` to Railway
   - Set env vars: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `FRONTEND_URL`
   - Railway auto-detects `requirements.txt`

3. **Stripe Webhook**
   - In Stripe Dashboard → Webhooks → Add endpoint: `https://your-app.railway.app/stripe-webhook`
   - Select event: `checkout.session.completed`
   - Copy signing secret → set as `STRIPE_WEBHOOK_SECRET`

### Option 2: Docker

```bash
docker-compose up -d
```

## API

| Endpoint | Auth | Cost | Description |
|----------|------|------|-------------|
| `POST /analyze` | API key | 1 credit | Full analysis |
| `POST /analyze/demo` | None | Free | 3 headlines only |
| `POST /signup` | None | Free | Get API key + 3 free credits |
| `GET /credits` | API key | Free | Check balance |
| `GET /history` | API key | Free | Scan history |
| `POST /checkout` | None | — | Create Stripe checkout session |

## Pricing

| Plan | Price | Credits |
|------|-------|---------|
| Starter | $5 | 10 scans |
| Pro | $20 | 50 scans |
| Unlimited | $50/mo | Unlimited |

## License

MIT