"""
Sentiment-Powered Solana xStock Rebalance Bot — Backend API.
Combines Google News RSS NLP sentiment signals, real-time Pyth & market feeds,
Jupiter DEX automated routing, and portfolio target weight allocation.
"""
import os
import sys
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_user_by_api_key, deduct_credit, record_scan, get_scan_history, find_or_create_user
from sentiment import analyze
from stripe_service import create_checkout_session, handle_checkout_completed, verify_webhook
from price_service import fetch_live_stock_prices
from stock_sentiment import get_all_stock_sentiment, inject_breaking_news, reset_breaking_news
from rebalance import get_current_portfolio, run_rebalance, compute_target_allocation
from jupiter_service import get_jupiter_quote, DEFAULT_WALLET_PUBKEY
from stocks import STOCKS, USDC

app = FastAPI(title="Sentiment-Powered Solana xStock Rebalance Bot API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:8001")

# ── Startup ──
@app.on_event("startup")
def startup():
    init_db()

# ── Pydantic Request Models ──
class AnalyzeRequest(BaseModel):
    person: str

class CheckoutRequest(BaseModel):
    email: str
    plan_id: str
    origin_url: Optional[str] = None

class SignupRequest(BaseModel):
    email: str

class RebalanceRequest(BaseModel):
    threshold: Optional[float] = 0.03

class SimulateNewsRequest(BaseModel):
    ticker: str
    headline: str
    is_positive: Optional[bool] = False

# ── Auth helper (Backward compatible) ──
def require_user(api_key: str = Header(None, alias="X-API-Key")):
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    user = get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user

# ══════════════════════════════════════════════════════════════════════════
# NEW HACKATHON APIs: Solana xStock Rebalancing & Sentiment Architecture
# ══════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "name": "Sentiment-Powered Solana xStock Rebalance Bot API",
        "version": "2.0.0",
        "network": "Solana",
        "dex_router": "Jupiter v1",
        "oracle": "Pyth Hermes Network",
        "docs": "/docs",
        "endpoints": {
            "portfolio": "/api/portfolio",
            "scores": "/api/scores",
            "prices": "/api/prices",
            "rebalance": "/api/rebalance",
            "simulate_news": "/api/simulate-news",
            "quote": "/api/quote"
        }
    }

@app.get("/api/portfolio")
def get_portfolio_endpoint():
    """
    Returns live valued Solana portfolio:
    Balances, current prices, current weights, and recommended target weights.
    """
    portfolio = get_current_portfolio()
    sentiments = get_all_stock_sentiment()
    sentiment_map = {t: sentiments[t]["compound_score"] for t in sentiments}
    target_weights = compute_target_allocation(sentiment_map)
    
    return {
        "portfolio": portfolio,
        "target_weights": target_weights,
        "sentiment_scores": sentiments,
        "wallet_public_key": portfolio.get("wallet_address", DEFAULT_WALLET_PUBKEY)
    }

@app.get("/api/scores")
def get_scores_endpoint(refresh: bool = False):
    """
    Returns live sentiment signals across the stock basket (TSLA, AAPL, NVDA, MSFT, GOOGL).
    """
    scores = get_all_stock_sentiment(force_refresh=refresh)
    return {"scores": scores}

@app.get("/api/prices")
def get_prices_endpoint():
    """
    Returns real-time Pyth & equity market prices for all basket assets and USDC.
    """
    prices = fetch_live_stock_prices()
    return {"prices": prices}

@app.post("/api/rebalance")
def rebalance_endpoint(req: Optional[RebalanceRequest] = None):
    """
    Executes Solana xStock rebalancing:
    1. Evaluates sentiment weights.
    2. Identifies deviations > threshold.
    3. Executes swaps on Jupiter DEX.
    4. Records confirmation and tx hash.
    """
    threshold = req.threshold if req else 0.03
    sentiments = get_all_stock_sentiment()
    sentiment_map = {t: sentiments[t]["compound_score"] for t in sentiments}
    
    rebalance_result = run_rebalance(sentiment_map, threshold=threshold)
    return rebalance_result

@app.post("/api/simulate-news")
def simulate_news_endpoint(req: SimulateNewsRequest):
    """
    Hackathon Demo Trigger:
    Simulates breaking news to demonstrate live sentiment shift and automatic rebalancing.
    Example: TSLA recall or NVDA record earnings.
    """
    ticker = req.ticker.upper()
    if ticker not in STOCKS:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}. Valid: {list(STOCKS.keys())}")
    
    news_res = inject_breaking_news(ticker, req.headline, req.is_positive)
    
    # Auto recalculate target weights
    sentiments = get_all_stock_sentiment()
    sentiment_map = {t: sentiments[t]["compound_score"] for t in sentiments}
    targets = compute_target_allocation(sentiment_map)

    return {
        "success": True,
        "injected": news_res,
        "updated_sentiment": sentiments[ticker],
        "new_target_weights": targets
    }

@app.post("/api/reset-news")
def reset_news_endpoint(ticker: Optional[str] = None):
    """Resets injected news back to pure organic Google News signals."""
    reset_breaking_news(ticker.upper() if ticker else None)
    return {"success": True, "message": "Simulated news cleared"}

@app.get("/api/quote")
def quote_endpoint(from_token: str, to_token: str, amount_usd: float = 100.0):
    """
    Returns real-time swap route and price impact from Jupiter aggregator.
    """
    from_mint = STOCKS.get(from_token, {}).get("mint") or USDC["mint"]
    to_mint = STOCKS.get(to_token, {}).get("mint") or USDC["mint"]
    amount_units = int(amount_usd * 1_000_000)
    
    quote = get_jupiter_quote(from_mint, to_mint, amount_units)
    return {
        "from": from_token,
        "to": to_token,
        "amount_usd": amount_usd,
        "quote": quote
    }

# ══════════════════════════════════════════════════════════════════════════
# EXISTING BACKWARD-COMPATIBLE ENDPOINTS (Analyze, Demo, Auth, Credits)
# ══════════════════════════════════════════════════════════════════════════

@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest, user: dict = Depends(require_user)):
    """Run sentiment analysis on any subject. Costs 1 credit."""
    ok, updated_user = deduct_credit(user["api_key"])
    if not ok:
        return JSONResponse(
            status_code=402,
            content={"error": "Insufficient credits", "credits": updated_user["credits"] if updated_user else 0}
        )
    
    result = analyze(req.person)
    if "error" in result:
        return JSONResponse(status_code=500, content=result)
    
    record_scan(
        user["api_key"],
        req.person,
        result.get("summary", {}).get("sentiment_label", "Unknown"),
        result.get("summary", {}).get("avg_compound", 0),
        result.get("summary", {}).get("total", 0),
    )
    
    return {
        **result,
        "credits_remaining": updated_user["credits"],
    }

@app.post("/analyze/demo")
def analyze_demo(req: AnalyzeRequest):
    """Free demo — no auth required, returns real live NLP analysis."""
    result = analyze(req.person)
    if "error" in result:
        return JSONResponse(status_code=500, content=result)
    
    return {
        "person": result["person"],
        "summary": result.get("summary", {}),
        "results": result.get("results", [])[:3],
    }

@app.get("/credits")
def get_credits(user: dict = Depends(require_user)):
    return {"credits": user["credits"], "total_scans": user["total_scans"]}

@app.get("/history")
def get_history(user: dict = Depends(require_user)):
    history = get_scan_history(user["api_key"])
    return {"history": history}

@app.post("/signup")
def signup(req: SignupRequest):
    """Create or retrieve API key with free scans."""
    from database import create_user, get_user_by_email
    existing = get_user_by_email(req.email)
    if existing:
        return {"api_key": existing["api_key"], "credits": existing["credits"], "existing": True}
    user = create_user(req.email)
    if user:
        return {"api_key": user["api_key"], "credits": user["credits"], "existing": False}
    return JSONResponse(status_code=500, content={"error": "Failed to create user"})

@app.post("/checkout")
def checkout(req: CheckoutRequest):
    """Create a Stripe Checkout session."""
    result, status_code = create_checkout_session(req.email, req.plan_id, req.origin_url)
    return JSONResponse(content=result, status_code=status_code)

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    event = verify_webhook(payload, sig_header)
    if not event:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        result = handle_checkout_completed(session)
        return result
    
    return {"received": True}

# ── Main ──
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)