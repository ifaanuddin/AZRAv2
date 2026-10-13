
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Lock

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="AZRA - The Palm Bistro")
lock = Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROLES = {
    "owner": "Café Owner",
    "cashier": "Cashier 1",
    "inventory": "Inventory Manager",
}

# Demo-only accounts. Change these passwords before sharing the demo.
USERS = {
    "owner": {
        "password": "PalmOwner123!",
        "role": "owner",
        "name": "Aarav Mehta",
    },
    "cashier1": {
        "password": "PalmCashier123!",
        "role": "cashier",
        "name": "Cashier 1",
    },
    "stockmanager": {
        "password": "PalmStock123!",
        "role": "inventory",
        "name": "Inventory Manager",
    },
}

sessions = {}

MENU = [
    {"id": "espresso", "name": "Espresso", "category": "Coffee", "price": 120,
     "recipe": {"beans": 18}},
    {"id": "latte", "name": "Café Latte", "category": "Coffee", "price": 180,
     "recipe": {"beans": 18, "milk": 200}},
    {"id": "cappuccino", "name": "Cappuccino", "category": "Coffee", "price": 170,
     "recipe": {"beans": 18, "milk": 150}},
    {"id": "coldcoffee", "name": "Cold Coffee", "category": "Cold Drinks", "price": 200,
     "recipe": {"beans": 18, "milk": 200, "syrup": 20}},
    {"id": "sandwich", "name": "Grilled Sandwich", "category": "Food", "price": 220,
     "recipe": {"bread": 2, "cheese": 40}},
    {"id": "brownie", "name": "Chocolate Brownie", "category": "Desserts", "price": 150,
     "recipe": {"chocolate": 60}},
]

INITIAL_STOCK = [
    {"id": "beans", "name": "Coffee Beans", "quantity": 4500,
     "unit": "g", "reorder_level": 1000, "unit_cost": 0.65},
    {"id": "milk", "name": "Milk", "quantity": 6500,
     "unit": "ml", "reorder_level": 2000, "unit_cost": 0.08},
    {"id": "syrup", "name": "Flavoured Syrup", "quantity": 800,
     "unit": "ml", "reorder_level": 250, "unit_cost": 0.35},
    {"id": "bread", "name": "Bread", "quantity": 60,
     "unit": "slices", "reorder_level": 20, "unit_cost": 4},
    {"id": "cheese", "name": "Cheese", "quantity": 1200,
     "unit": "g", "reorder_level": 400, "unit_cost": 0.5},
    {"id": "chocolate", "name": "Chocolate", "quantity": 900,
     "unit": "g", "reorder_level": 300, "unit_cost": 0.6},
]

stock = {item["id"]: item.copy() for item in INITIAL_STOCK}
orders = []
next_order_id = 1001


class LoginRequest(BaseModel):
    username: str
    password: str


class OrderItem(BaseModel):
    menu_id: str
    quantity: int = Field(ge=1, le=50)


class OrderRequest(BaseModel):
    items: list[OrderItem] = Field(min_length=1, max_length=30)
    payment_method: str
    payment_confirmed: bool


class StockDelivery(BaseModel):
    quantity: int = Field(gt=0, le=1000000)


def require_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please sign in.")

    token = authorization.removeprefix("Bearer ").strip()
    user = sessions.get(token)

    if not user:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")

    return user


def require_role(*allowed_roles):
    def check(user=Depends(require_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Your account does not have permission for this action.",
            )
        return user
    return check


def money(value):
    return round(value, 2)


def calculate_metrics():
    paid_orders = [o for o in orders if o["payment_status"] == "Collected"]
    revenue = sum(o["total"] for o in paid_orders)
    estimated_cost = sum(o["ingredient_cost"] for o in paid_orders)

    by_day = {}
    for order in paid_orders:
        day = order["created_at"][:10]
        by_day[day] = by_day.get(day, 0) + order["total"]

    top_items = {}
    for order in paid_orders:
        for item in order["items"]:
            top_items[item["name"]] = (
                top_items.get(item["name"], 0) + item["quantity"]
            )

    return {
        "revenue": money(revenue),
        "estimated_profit": money(revenue - estimated_cost),
        "orders": len(paid_orders),
        "average_order": money(revenue / len(paid_orders)) if paid_orders else 0,
        "sales_by_day": [
            {"date": day, "revenue": money(value)}
            for day, value in sorted(by_day.items())
        ],
        "top_items": [
            {"name": name, "quantity": quantity}
            for name, quantity in sorted(
                top_items.items(), key=lambda item: item[1], reverse=True
            )[:5]
        ],
    }


@app.get("/")
def root():
    return {"message": "The Palm Bistro API is running.", "status": "ok"}


@app.post("/api/login")
def login(data: LoginRequest):
    account = USERS.get(data.username)

    if not account or account["password"] != data.password:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    token = token_urlsafe(32)
    sessions[token] = {
        "username": data.username,
        "name": account["name"],
        "role": account["role"],
    }

    return {
        "token": token,
        "user": {
            "username": data.username,
            "name": account["name"],
            "role": account["role"],
            "role_label": ROLES[account["role"]],
        },
    }


@app.post("/api/logout")
def logout(user=Depends(require_user), authorization: str = Header()):
    token = authorization.removeprefix("Bearer ").strip()
    sessions.pop(token, None)
    return {"message": "Signed out."}


@app.get("/api/me")
def me(user=Depends(require_user)):
    return {**user, "role_label": ROLES[user["role"]]}


@app.get("/api/dashboard")
def dashboard(user=Depends(require_user)):
    with lock:
        metrics = calculate_metrics()
        low_stock = [
            item.copy() for item in stock.values()
            if item["quantity"] <= item["reorder_level"]
        ]
        recent_orders = [o.copy() for o in reversed(orders[-8:])]

    if user["role"] == "owner":
        return {
            "role": "owner",
            "metrics": metrics,
            "low_stock": low_stock,
            "recent_orders": recent_orders,
        }

    if user["role"] == "cashier":
        return {
            "role": "cashier",
            "today_orders": metrics["orders"],
            "today_revenue": metrics["revenue"],
            "menu": MENU,
            "recent_orders": recent_orders,
        }

    return {
        "role": "inventory",
        "stock": list(stock.values()),
        "low_stock": low_stock,
        "recent_orders": recent_orders,
    }


@app.get("/api/menu")
def get_menu(user=Depends(require_user)):
    return MENU


@app.post("/api/orders")
def create_order(
    data: OrderRequest,
    user=Depends(require_role("cashier", "owner")),
):
    global next_order_id

    if data.payment_method not in {"Cash", "UPI", "Card"}:
        raise HTTPException(status_code=400, detail="Choose Cash, UPI or Card.")

    if not data.payment_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirm that payment has been received before completing the order.",
        )

    with lock:
        # Validate the complete order before changing inventory.
        selected = []
        ingredient_totals = {}
        subtotal = 0
        ingredient_cost = 0

        for line in data.items:
            product = next((m for m in MENU if m["id"] == line.menu_id), None)
            if not product:
                raise HTTPException(status_code=400, detail="Unknown menu item.")

            subtotal += product["price"] * line.quantity
            selected.append({
                "menu_id": product["id"],
                "name": product["name"],
                "quantity": line.quantity,
                "unit_price": product["price"],
                "line_total": product["price"] * line.quantity,
            })

            for ingredient, amount in product["recipe"].items():
                ingredient_totals[ingredient] = (
                    ingredient_totals.get(ingredient, 0) + amount * line.quantity
                )

        for ingredient, amount in ingredient_totals.items():
            if stock[ingredient]["quantity"] < amount:
                raise HTTPException(
                    status_code=409,
                    detail=f"Not enough {stock[ingredient]['name']} to complete this order.",
                )
            ingredient_cost += amount * stock[ingredient]["unit_cost"]

        for ingredient, amount in ingredient_totals.items():
            stock[ingredient]["quantity"] -= amount

        order = {
            "id": next_order_id,
            "items": selected,
            "total": money(subtotal),
            "payment_method": data.payment_method,
            "payment_status": "Collected",
            "collected_by": user["name"],
            "cashier_username": user["username"],
            "ingredient_cost": money(ingredient_cost),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        orders.append(order)
        next_order_id += 1

    return {"message": "Order completed.", "order": order}


@app.post("/api/inventory/{ingredient_id}/deliveries")
def receive_delivery(
    ingredient_id: str,
    data: StockDelivery,
    user=Depends(require_role("inventory", "owner")),
):
    with lock:
        item = stock.get(ingredient_id)
        if not item:
            raise HTTPException(status_code=404, detail="Ingredient not found.")

        item["quantity"] += data.quantity
        return {
            "message": "Delivery recorded.",
            "ingredient": item.copy(),
            "recorded_by": user["name"],
        }


@app.post("/api/chat")
def chat(
    data: dict,
    user=Depends(require_user),
):
    # Grounded demo assistant. Connect a real AI provider later.
    question = str(data.get("message", "")).strip().lower()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a message.")

    with lock:
        metrics = calculate_metrics()
        low_stock = [
            item["name"] for item in stock.values()
            if item["quantity"] <= item["reorder_level"]
        ]
        best = metrics["top_items"][0] if metrics["top_items"] else None

    if any(word in question for word in ["stock", "ingredient", "inventory", "milk"]):
        if low_stock:
            answer = "These ingredients need attention: " + ", ".join(low_stock) + "."
        else:
            answer = "No ingredients are currently below their reorder levels."
    elif any(word in question for word in ["best", "popular", "selling", "product"]):
        answer = (
            f"{best['name']} is currently the best seller with "
            f"{best['quantity']} units sold."
            if best else "No completed sales have been recorded yet."
        )
    elif any(word in question for word in ["profit", "revenue", "sales", "earning"]):
        answer = (
            f"Recorded revenue is ₹{metrics['revenue']:,.2f} across "
            f"{metrics['orders']} completed orders. Estimated profit after "
            f"tracked ingredient costs is ₹{metrics['estimated_profit']:,.2f}. "
            "This excludes other operating expenses."
        )
    else:
        answer = (
            f"I'm Happy, your Palm Bistro assistant! Recorded revenue is "
            f"₹{metrics['revenue']:,.2f}, with {metrics['orders']} completed orders. "
            "Ask me about sales, best-selling products, profit, or ingredient stock."
        )

    return {"answer": answer, "mode": "demo-data"}
