from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter()

# Templates directory
templates_dir = os.path.join(os.path.dirname(__file__), "../../../templates")
os.makedirs(templates_dir, exist_ok=True)

# Create simple checkout HTML if not exists
checkout_html = os.path.join(templates_dir, "checkout.html")
if not os.path.exists(checkout_html):
    with open(checkout_html, "w") as f:
        f.write("""<!DOCTYPE html>
<html>
<head><title>Checkout</title></head>
<body>
<h3>Checkout</h3>
<form action="/api/v1/payment/process" method="POST">
Amount: <input type="number" name="amount" required><br>
User ID: <input type="text" name="user_id" required><br>
Merchant ID: <input type="text" name="merchant_id" required><br>
<button type="submit">Pay</button>
</form>
</body>
</html>""")

templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def checkout_page(request: Request):
    return templates.TemplateResponse("checkout.html", {"request": request})

@router.post("/process", response_class=HTMLResponse)
async def process_payment(request: Request, amount: float = Form(...), user_id: str = Form(...), merchant_id: str = Form(...)):
    risk = min(amount / 1200, 0.99)
    is_fraud = risk > 0.8
    
    if is_fraud:
        return HTMLResponse(f"<h3>❌ Transaction Blocked!</h3><p>Risk Score: {risk:.2%}</p><a href='/api/v1/payment/'>Try Again</a>")
    else:
        return HTMLResponse(f"<h3>✅ Payment Successful!</h3><p>Risk Score: {risk:.2%}</p>")

@router.get("/health")
async def payment_health():
    return {"status": "healthy", "service": "payment-gateway"}