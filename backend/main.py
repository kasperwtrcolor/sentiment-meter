"""
Sentiment Meter — FastAPI Backend
"""
import os
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_user_by_api_key, deduct_credit, record_scan, get_scan_history, find_or_create_user
from sentiment import analyze
from stripe_service import create_checkout_session, handle_checkout_completed, verify_webhook

app = FastAPI(title="Sentiment Meter API", version="1.0.0")

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

# ── Models ──
class AnalyzeRequest(BaseModel):
    person: str

class CheckoutRequest(BaseModel):
    email: str
    plan_id: str
    origin_url: Optional[str] = None

class SignupRequest(BaseModel):
    email: str

# ── Auth helper ──
def require_user(api_key: str = Header(None, alias="X-API-Key")):
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    user = get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user

# ── Endpoints ──

@app.get("/")
def root():
    return {"name": "Sentiment Meter API", "version": "1.0.0", "docs": "/docs"}

@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest, user: dict = Depends(require_user)):
    """Run sentiment analysis on a person. Costs 1 credit."""
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
    """Free demo — no auth required, limited results."""
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

# ── Checkout / Stripe ──

@app.post("/signup")
def signup(req: SignupRequest):
    """Create a new account with 3 free credits."""
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