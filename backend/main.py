import os
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Lock

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "Missing SUPABASE_URL or SUPABASE_SECRET_KEY in backend/.env"
    )

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY,
)

app = FastAPI(title="AZRA - The Palm Bistro")
lock = Lock()


@app.get("/api/db-check")
def check_database():
    try:
        result = supabase.table("ingredients").select("id").limit(1).execute()
        return {
            "status": "connected",
            "message": "Supabase database query successful",
            "rows_found": len(result.data),
        }
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Database connection failed: {exc}",
        )


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
    try:
        orders_result = (
            supabase.table("orders")
            .select("*")
            .order("created_at", desc=True)
            .limit(8)
            .execute()
        )
        ingredients_result = (
            supabase.table("ingredients")
            .select("*")
            .execute()
        )
        all_orders_result = (
            supabase.table("orders")
            .select("*")
            .execute()
        )
        order_items_result = (
            supabase.table("order_items")
            .select("*")
            .execute()
        )

        recent_orders = orders_result.data or []
        ingredients = ingredients_result.data or []
        all_orders = all_orders_result.data or []
        order_items = order_items_result.data or []

        total_revenue = sum(float(o["total"]) for o in all_orders)
        total_cost = sum(float(o["ingredient_cost"]) for o in all_orders)
        total_orders = len(all_orders)

        today = __import__("datetime").date.today()
        today_orders = [
            o for o in all_orders
            if o.get("created_at", "")[:10] == today.isoformat()
        ]
        today_revenue = sum(float(o["total"]) for o in today_orders)

        metrics = {
            "revenue": round(total_revenue, 2),
            "profit": round(total_revenue - total_cost, 2),
            "orders": total_orders,
            "average_order": round(
                total_revenue / total_orders, 2
            ) if total_orders else 0,
            "sales_by_day": [],
            "top_items": [],
        }

        item_sales = {}
        for item in order_items:
            name = item["item_name"]
            item_sales[name] = (
                item_sales.get(name, 0) + item["quantity"]
            )

        metrics["top_items"] = [
            {"name": name, "quantity": quantity}
            for name, quantity in sorted(
                item_sales.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        ]

        low_stock = [
            {
                "id": item["id"],
                "name": item["name"],
                "quantity": item["quantity"],
                "unit": item["unit"],
                "reorder_level": item["reorder_level"],
            }
            for item in ingredients
            if item["quantity"] <= item["reorder_level"]
        ]

        recent_order_items = {}
        for item in order_items:
            recent_order_items.setdefault(item["order_id"], []).append({
                "name": item["item_name"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
            })

        for order in recent_orders:
            order["items"] = recent_order_items.get(order["id"], [])

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
                "today_orders": len(today_orders),
                "today_revenue": round(today_revenue, 2),
                "menu": MENU,
                "recent_orders": recent_orders,
            }

        return {
            "role": "inventory",
            "stock": ingredients,
            "low_stock": low_stock,
            "recent_orders": recent_orders,
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Could not load dashboard data from Supabase."
        )

@app.get("/api/menu")
def get_menu(user=Depends(require_user)):
    return MENU



@app.post("/api/orders")
def create_order(
    data: OrderRequest,
    user=Depends(require_role("cashier", "owner")),
):
    if data.payment_method not in {"Cash", "UPI", "Card"}:
        raise HTTPException(
            status_code=400,
            detail="Choose Cash, UPI or Card.",
        )

    if not data.payment_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirm that payment has been received before completing the order.",
        )

    # Merge duplicate menu items before sending them to the database.
    quantities = {}
    for line in data.items:
        quantities[line.menu_id] = (
            quantities.get(line.menu_id, 0) + line.quantity
        )

    if any(quantity > 50 for quantity in quantities.values()):
        raise HTTPException(
            status_code=400,
            detail="Maximum quantity per menu item is 50.",
        )

    try:
        result = supabase.rpc(
            "create_palm_bistro_order",
            {
                "p_items": [
                    {"menu_id": menu_id, "quantity": quantity}
                    for menu_id, quantity in quantities.items()
                ],
                "p_cashier_username": user["username"],
                "p_collected_by": user["name"],
                "p_payment_method": data.payment_method,
            },
        ).execute()

        order = result.data

        # Keep the existing frontend response structure.
        return {
            "message": "Order completed.",
            "order": order,
        }

    except Exception as exc:
        message = str(exc)

        if "Not enough" in message:
            raise HTTPException(status_code=409, detail=message)

        if "Unknown menu item" in message or "Invalid" in message:
            raise HTTPException(status_code=400, detail=message)

        raise HTTPException(
            status_code=500,
            detail="Could not save the order. Please check the dashboard before retrying.",
        )

@app.post("/api/inventory/{ingredient_id}/deliveries")
def receive_delivery(
    ingredient_id: str,
    data: StockDelivery,
    user=Depends(require_role("inventory", "owner")),
):
    try:
        # Verify the ingredient exists in Supabase.
        result = (
            supabase.table("ingredients")
            .select("*")
            .eq("id", ingredient_id)
            .limit(1)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Ingredient not found."
            )

        # Record the delivery and update stock atomically via RPC.
        delivery_result = supabase.rpc(
            "record_palm_bistro_delivery",
            {
                "p_ingredient_id": ingredient_id,
                "p_quantity": data.quantity,
                "p_recorded_by": user["name"],
            },
        ).execute()

        updated_ingredient = delivery_result.data

        if isinstance(updated_ingredient, list):
            updated_ingredient = (
                updated_ingredient[0] if updated_ingredient else None
            )

        if not updated_ingredient:
            raise HTTPException(
                status_code=500,
                detail="Delivery was not confirmed by the database."
            )

        return {
            "message": "Delivery recorded.",
            "ingredient": updated_ingredient,
            "recorded_by": user["name"],
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Could not record delivery in Supabase."
        )

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
