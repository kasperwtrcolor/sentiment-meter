"""
Sentiment-Powered Solana xStock Rebalance Bot — Backend API.
Adds user wallet onboarding, random cyberpunk handles, Jupiter client approval payloads,
and profile retrieval.
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

from database import (
    init_db, get_user_by_api_key, deduct_credit, record_scan, get_scan_history, 
    find_or_create_user, get_or_create_wallet_user, record_wallet_swap, get_wallet_profile
)
from sentiment import analyze
from stripe_service import create_checkout_session, handle_checkout_completed, verify_webhook
from price_service import fetch_live_stock_prices
from stock_sentiment import get_all_stock_sentiment, inject_breaking_news, reset_breaking_news
from rebalance import get_current_portfolio, run_rebalance, compute_target_allocation
from jupiter_service import get_jupiter_quote, build_jupiter_swap_tx, DEFAULT_WALLET_PUBKEY
from stocks import STOCKS, USDC

app = FastAPI(title="Solana xStock Sentiment Terminal API", version="2.5.0")

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
class RebalanceRequest(BaseModel):
    threshold: Optional[float] = 0.03
    wallet_address: Optional[str] = None

class SimulateNewsRequest(BaseModel):
    ticker: str
    headline: str
    is_positive: Optional[bool] = False

class ConnectWalletRequest(BaseModel):
    wallet_address: str

class RecordSwapRequest(BaseModel):
    wallet_address: str
    tx_hash: str
    from_symbol: str
    to_symbol: str
    amount_usd: float

class PrepareSwapRequest(BaseModel):
    wallet_address: str
    from_symbol: str
    to_symbol: str
    amount_usd: float

class AnalyzeRequest(BaseModel):
    person: str

class CheckoutRequest(BaseModel):
    email: str
    plan_id: str
    origin_url: Optional[str] = None

class SignupRequest(BaseModel):
    email: str

def require_user(api_key: str = Header(None, alias="X-API-Key")):
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    user = get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user

# ══════════════════════════════════════════════════════════════════════════
# WALLET PROFILE & ONBOARDING APIs
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/wallet/connect")
def connect_wallet_endpoint(req: ConnectWalletRequest):
    """
    Onboards a user via Solana wallet address.
    Assigns a unique cyberpunk pseudonym (e.g. 'CyberBull Quant #412') and stores them in SQLite.
    """
    addr = req.wallet_address.strip()
    if not addr or len(addr) < 20:
        raise HTTPException(status_code=400, detail="Invalid Solana wallet address format")
    
    profile = get_wallet_profile(addr)
    return {
        "success": True,
        "profile": profile["user"],
        "history": profile["history"]
    }

@app.get("/api/wallet/profile/{wallet_address}")
def get_profile_endpoint(wallet_address: str):
    """Fetches user profile, display name, trading volume, and past executions."""
    profile = get_wallet_profile(wallet_address.strip())
    return profile

@app.post("/api/wallet/record-swap")
def record_swap_endpoint(req: RecordSwapRequest):
    """Records an executed user-signed swap in their personal history."""
    record_wallet_swap(
        req.wallet_address.strip(),
        req.tx_hash.strip(),
        req.from_symbol.upper(),
        req.to_symbol.upper(),
        req.amount_usd
    )
    return {"success": True}

# ══════════════════════════════════════════════════════════════════════════
# MODEL A: JUPITER PREPARE SWAP (Client Wallet Signing)
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/prepare-swap")
def prepare_swap_endpoint(req: PrepareSwapRequest):
    """
    Prepares a real serialized Jupiter swap transaction for Model A (Phantom/Solflare wallet approval).
    Returns the base64 swapTransaction ready for window.solana.signAndSendTransaction.
    """
    from_mint = STOCKS.get(req.from_symbol, {}).get("mint") or USDC["mint"]
    to_mint = STOCKS.get(req.to_symbol, {}).get("mint") or USDC["mint"]
    amount_units = int(req.amount_usd * 1_000_000)

    quote = get_jupiter_quote(from_mint, to_mint, amount_units)
    swap_res = build_jupiter_swap_tx(quote, user_public_key=req.wallet_address)

    return {
        "from_symbol": req.from_symbol,
        "to_symbol": req.to_symbol,
        "amount_usd": req.amount_usd,
        "quote": quote,
        "swap_transaction": swap_res.get("swap_transaction"),
        "simulated_tx_hash": swap_res.get("simulated_tx_hash")
    }

# ══════════════════════════════════════════════════════════════════════════
# PORTFOLIO, REBALANCE, AND SENTIMENT APIs
# ══════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "name": "Solana xStock Sentiment Terminal API",
        "version": "2.5.0",
        "network": "Solana",
        "dex_router": "Jupiter v1",
        "oracle": "Pyth Hermes Network",
        "docs": "/docs"
    }

@app.get("/api/portfolio")
def get_portfolio_endpoint(wallet: Optional[str] = None):
    portfolio = get_current_portfolio()
    sentiments = get_all_stock_sentiment()
    sentiment_map = {t: sentiments[t]["compound_score"] for t in sentiments}
    target_weights = compute_target_allocation(sentiment_map)
    
    # If user passed custom wallet, resolve display name
    user_info = None
    if wallet:
        user_info = get_or_create_wallet_user(wallet)

    return {
        "portfolio": portfolio,
        "target_weights": target_weights,
        "sentiment_scores": sentiments,
        "wallet_public_key": wallet or portfolio.get("wallet_address", DEFAULT_WALLET_PUBKEY),
        "user_profile": user_info
    }

@app.get("/api/scores")
def get_scores_endpoint(refresh: bool = False):
    scores = get_all_stock_sentiment(force_refresh=refresh)
    return {"scores": scores}

@app.get("/api/prices")
def get_prices_endpoint():
    prices = fetch_live_stock_prices()
    return {"prices": prices}

@app.post("/api/rebalance")
def rebalance_endpoint(req: Optional[RebalanceRequest] = None):
    threshold = req.threshold if req else 0.03
    sentiments = get_all_stock_sentiment()
    sentiment_map = {t: sentiments[t]["compound_score"] for t in sentiments}
    
    rebalance_result = run_rebalance(sentiment_map, threshold=threshold)
    
    # If wallet address provided, record swaps to profile
    if req and req.wallet_address:
        for s in rebalance_result.get("swaps", []):
            record_wallet_swap(
                req.wallet_address.strip(),
                s["tx_hash"],
                s["from_symbol"],
                s["to_symbol"],
                s["amount_usd"]
            )
            
    return rebalance_result

@app.post("/api/simulate-news")
def simulate_news_endpoint(req: SimulateNewsRequest):
    ticker = req.ticker.upper()
    if ticker not in STOCKS:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}. Valid: {list(STOCKS.keys())}")
    
    news_res = inject_breaking_news(ticker, req.headline, req.is_positive)
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
    reset_breaking_news(ticker.upper() if ticker else None)
    return {"success": True, "message": "Organic news signals restored"}

@app.get("/api/quote")
def quote_endpoint(from_token: str, to_token: str, amount_usd: float = 100.0):
    from_mint = STOCKS.get(from_token, {}).get("mint") or USDC["mint"]
    to_mint = STOCKS.get(to_token, {}).get("mint") or USDC["mint"]
    amount_units = int(amount_usd * 1_000_000)
    quote = get_jupiter_quote(from_mint, to_mint, amount_units)
    return {"from": from_token, "to": to_token, "amount_usd": amount_usd, "quote": quote}

# ══════════════════════════════════════════════════════════════════════════
# BACKWARD-COMPATIBLE ENDPOINTS (Analyze, Demo, Auth, Credits, Stripe)
# ══════════════════════════════════════════════════════════════════════════

@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest, user: dict = Depends(require_user)):
    ok, updated_user = deduct_credit(user["api_key"])
    if not ok:
        return JSONResponse(status_code=402, content={"error": "Insufficient credits", "credits": updated_user["credits"] if updated_user else 0})
    result = analyze(req.person)
    if "error" in result:
        return JSONResponse(status_code=500, content=result)
    record_scan(user["api_key"], req.person, result.get("summary", {}).get("sentiment_label", "Unknown"), result.get("summary", {}).get("avg_compound", 0), result.get("summary", {}).get("total", 0))
    return {**result, "credits_remaining": updated_user["credits"]}

@app.post("/analyze/demo")
def analyze_demo(req: AnalyzeRequest):
    result = analyze(req.person)
    if "error" in result:
        return JSONResponse(status_code=500, content=result)
    return {"person": result["person"], "summary": result.get("summary", {}), "results": result.get("results", [])[:3]}

@app.get("/credits")
def get_credits(user: dict = Depends(require_user)):
    return {"credits": user["credits"], "total_scans": user["total_scans"]}

@app.get("/history")
def get_history(user: dict = Depends(require_user)):
    return {"history": get_scan_history(user["api_key"])}

@app.post("/signup")
def signup(req: SignupRequest):
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
    result, status_code = create_checkout_session(req.email, req.plan_id, req.origin_url)
    return JSONResponse(content=result, status_code=status_code)

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = verify_webhook(payload, sig_header)
    if not event:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        return handle_checkout_completed(session)
    return {"received": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)