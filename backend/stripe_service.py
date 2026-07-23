"""
Stripe payment integration.
"""
import os
import stripe
from database import get_user_by_email, get_user_by_stripe_customer, add_credits, find_or_create_user

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:8001")

# Pricing plans
PLANS = {
    "starter": {
        "name": "Starter Pack",
        "credits": 10,
        "price_cents": 500,  # $5
        "price_display": "$5",
    },
    "pro": {
        "name": "Pro Pack",
        "credits": 50,
        "price_cents": 2000,  # $20
        "price_display": "$20",
    },
    "unlimited": {
        "name": "Unlimited Monthly",
        "credits": 999999,  # effectively unlimited
        "price_cents": 5000,  # $50
        "price_display": "$50/mo",
        "is_recurring": True,
    },
}

def create_checkout_session(email, plan_id, origin_url=None):
    """Create a Stripe Checkout Session for a credit purchase."""
    if not STRIPE_SECRET_KEY:
        return {"error": "Stripe not configured"}, 500
    
    plan = PLANS.get(plan_id)
    if not plan:
        return {"error": f"Unknown plan: {plan_id}"}, 400
    
    user, is_new = find_or_create_user(email)
    if not user:
        return {"error": "Failed to create user"}, 500
    
    success_url = f"{origin_url or FRONTEND_URL}/dashboard.html?session_id={{CHECKOUT_SESSION_ID}}&success=true"
    cancel_url = f"{origin_url or FRONTEND_URL}/index.html?canceled=true"
    
    try:
        session = stripe.checkout.Session.create(
            mode="payment" if not plan.get("is_recurring") else "subscription",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": plan["name"],
                        "description": f"{plan['credits']:,} sentiment scans" if plan["credits"] < 999999 else "Unlimited sentiment scans",
                    },
                    "unit_amount": plan["price_cents"],
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=email,
            metadata={
                "plan_id": plan_id,
                "credits": str(plan["credits"]),
                "email": email,
            },
        )
        return {"url": session.url, "session_id": session.id}, 200
    except Exception as e:
        return {"error": str(e)}, 500

def handle_checkout_completed(session):
    """Handle successful checkout — add credits to user account."""
    email = session.get("metadata", {}).get("email") or session.get("customer_details", {}).get("email")
    credits = int(session.get("metadata", {}).get("credits", 0))
    plan_id = session.get("metadata", {}).get("plan_id", "unknown")
    
    if not email or not credits:
        return {"error": "Missing metadata"}, 400
    
    user, _ = find_or_create_user(email)
    if not user:
        return {"error": "User not found"}, 404
    
    # Add credits
    updated_user = add_credits(
        user["api_key"],
        credits,
        description=f"Purchase: {plan_id}",
        stripe_session_id=session["id"],
    )
    
    return {"success": True, "email": email, "credits_added": credits, "total_credits": updated_user["credits"]}

def verify_webhook(payload, sig_header):
    """Verify Stripe webhook signature."""
    if not STRIPE_WEBHOOK_SECRET:
        return None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        return event
    except (ValueError, stripe.error.SignatureVerificationError):
        return None