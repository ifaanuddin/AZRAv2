import os
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Lock

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
    customer_name: str | None = Field(default=None, max_length=120)

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
        print("ORDER CHECK: endpoint reached; calling Supabase RPC", flush=True)
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
                "p_payment_method": data.payment_method,
                "p_customer_name": (data.customer_name or "").strip() or None,
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
        print("ORDER SAVE ERROR:", repr(exc), flush=True)

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
    from calendar import monthrange

    question = str(data.get("message", "")).strip().lower()

    if not question:
        raise HTTPException(status_code=400, detail="Enter a message.")

    try:
        orders_result = (
            supabase.table("orders")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        items_result = (
            supabase.table("order_items")
            .select("order_id,item_name,quantity,unit_price")
            .execute()
        )
        ingredients_result = (
            supabase.table("ingredients")
            .select("id,name,quantity,unit,reorder_level")
            .execute()
        )

        orders_data = orders_result.data or []
        order_items = items_result.data or []
        ingredients = ingredients_result.data or []

        tz = ZoneInfo("Asia/Kolkata")
        now = datetime.now(tz)
        today = now.date()

        def order_datetime(order):
            value = order.get("created_at")
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
                return parsed.astimezone(tz)
            except (ValueError, TypeError):
                return None

        def in_period(order, start, end):
            dt = order_datetime(order)
            return dt is not None and start <= dt < end

        def order_lines(order):
            return [
                item for item in order_items
                if str(item["order_id"]) == str(order["id"])
            ]

        def format_order(order):
            lines = order_lines(order)
            items_text = ", ".join(
                f"{item['item_name']} x {item['quantity']}"
                for item in lines
            ) or "item details unavailable"
            dt = order_datetime(order)
            date_text = dt.strftime("%d %b %Y, %I:%M %p") if dt else "date unavailable"
            return (
                f"Order #{order['id']} on {date_text}: {items_text}; "
                f"total ₹{float(order['total']):,.2f} "
                f"({order.get('payment_method', 'payment method unavailable')})."
            )

        def detect_period():
            if "yesterday" in question:
                start_date = today - timedelta(days=1)
                return (
                    datetime.combine(start_date, datetime.min.time(), tzinfo=tz),
                    datetime.combine(today, datetime.min.time(), tzinfo=tz),
                    "yesterday",
                )

            if "today" in question or "tonight" in question:
                return (
                    datetime.combine(today, datetime.min.time(), tzinfo=tz),
                    datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=tz),
                    "today",
                )

            if "last week" in question or "past week" in question:
                start_date = today - timedelta(days=7)
                return (
                    datetime.combine(start_date, datetime.min.time(), tzinfo=tz),
                    datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=tz),
                    "the past 7 days",
                )

            if "this month" in question or "monthly" in question:
                start_date = today.replace(day=1)
                return (
                    datetime.combine(start_date, datetime.min.time(), tzinfo=tz),
                    datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=tz),
                    "this month",
                )

            if "this week" in question:
                start_date = today - timedelta(days=today.weekday())
                return (
                    datetime.combine(start_date, datetime.min.time(), tzinfo=tz),
                    datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=tz),
                    "this week",
                )

            return None

        period = detect_period()

        selected_orders = orders_data
        period_label = "all recorded time"

        if period:
            start, end, period_label = period
            selected_orders = [
                order for order in orders_data
                if in_period(order, start, end)
            ]

        revenue = sum(float(o["total"]) for o in orders_data)
        order_count = len(orders_data)

        # Synthetic demo orders have zero ingredient cost by design.
        # Exclude them from estimated-profit calculations.
        real_orders = [
            o for o in orders_data
            if not o.get("is_demo_seed", False)
        ]
        real_revenue = sum(float(o["total"]) for o in real_orders)
        real_cost = sum(
            float(o.get("ingredient_cost") or 0)
            for o in real_orders
        )
        estimated_profit = real_revenue - real_cost

        item_sales = {}
        for item in order_items:
            item_sales[item["item_name"]] = (
                item_sales.get(item["item_name"], 0)
                + int(item["quantity"])
            )

        best = (
            max(item_sales.items(), key=lambda pair: pair[1])
            if item_sales else None
        )

        low_stock = [
            item for item in ingredients
            if float(item["quantity"]) <= float(item["reorder_level"])
        ]

        # Match saved customer names against the user's question.
        known_names = sorted(
            {
                str(o.get("customer_name", "")).strip()
                for o in orders_data
                if o.get("customer_name")
            },
            key=len,
            reverse=True,
        )
        customer_name = next(
            (
                name for name in known_names
                if name.lower() in question
            ),
            None,
        )

        customer_question = any(term in question for term in [
            "customer", "purchase", "purchased", "bought",
            "visit", "visited", "spent", "spend", "their order",
            "his order", "her order", "previous order",
            "order history", "ordered by",
        ])

        # 1. Customer history comes before general order/revenue logic.
        if customer_name and (
            customer_question
            or "last order" in question
            or "latest order" in question
            or "order" in question
        ):
            customer_orders = [
                o for o in orders_data
                if str(o.get("customer_name", "")).strip().lower()
                == customer_name.lower()
            ]

            if period:
                customer_orders = [
                    o for o in customer_orders
                    if in_period(o, start, end)
                ]

            customer_orders.sort(
                key=lambda o: order_datetime(o) or datetime.min.replace(tzinfo=tz),
                reverse=True,
            )

            if not customer_orders:
                answer = (
                    f"I couldn't find orders for {customer_name}"
                    + (f" during {period_label}." if period else ".")
                )
            elif any(term in question for term in ["how much", "spent", "spend", "total amount"]):
                amount = sum(float(o["total"]) for o in customer_orders)
                answer = (
                    f"{customer_name} has spent ₹{amount:,.2f} across "
                    f"{len(customer_orders)} recorded orders"
                    + (f" during {period_label}." if period else ".")
                )
            elif any(term in question for term in ["how many", "number of", "times", "visit", "visited"]):
                answer = (
                    f"{customer_name} has {len(customer_orders)} recorded orders"
                    + (f" during {period_label}." if period else ".")
                )
            elif any(term in question for term in ["last order", "latest order", "most recent"]):
                answer = format_order(customer_orders[0])
            else:
                recent = customer_orders[:5]
                answer = (
                    f"{customer_name} has {len(customer_orders)} recorded orders. "
                    + " ".join(format_order(o) for o in recent)
                )
                if len(customer_orders) > 5:
                    answer += " Showing the five most recent orders."

        # 2. Date-based business questions.
        elif period and any(term in question for term in [
            "revenue", "sales", "earning", "orders", "order count",
            "how many", "total", "made", "busy"
        ]):
            period_revenue = sum(float(o["total"]) for o in selected_orders)

            if any(term in question for term in ["how many", "number of", "count", "busy"]):
                answer = (
                    f"There were {len(selected_orders)} recorded orders "
                    f"during {period_label}, totaling ₹{period_revenue:,.2f}."
                )
            else:
                answer = (
                    f"Recorded revenue during {period_label} was "
                    f"₹{period_revenue:,.2f}, across "
                    f"{len(selected_orders)} orders."
                )

        # 3. Specific latest order.
        elif any(phrase in question for phrase in [
            "last order", "latest order", "most recent order",
            "recent order", "what was ordered", "what did we order",
            "what was the last"
        ]):
            if orders_data:
                latest_order = orders_data[0]
                answer = format_order(latest_order)
            else:
                answer = "There are no saved orders yet."

        # 4. Inventory questions.
        elif any(word in question for word in [
            "stock", "ingredient", "inventory", "milk", "beans"
        ]):
            requested = next(
                (
                    item for item in ingredients
                    if str(item["name"]).lower() in question
                    or str(item["id"]).lower() in question
                ),
                None,
            )

            if requested:
                answer = (
                    f"{requested['name']} stock is "
                    f"{requested['quantity']} {requested['unit']}."
                )
                if requested in low_stock:
                    answer += " This ingredient is at or below its reorder level."
            elif low_stock:
                answer = "These ingredients need attention: " + ", ".join(
                    f"{item['name']} ({item['quantity']} {item['unit']})"
                    for item in low_stock
                ) + "."
            else:
                answer = "No ingredients are currently below their reorder levels."

        # 5. Best sellers.
        elif any(word in question for word in [
            "best", "popular", "selling", "product", "seller"
        ]):
            answer = (
                f"{best[0]} is currently the best seller with {best[1]} units sold."
                if best else "No completed sales have been recorded yet."
            )

        # 6. General revenue and profit.
        elif any(word in question for word in [
            "profit", "revenue", "sales", "earning", "order", "made"
        ]):
            if "profit" in question:
                answer = (
                    f"Estimated profit from non-seeded orders is "
                    f"₹{estimated_profit:,.2f}, based on recorded revenue "
                    f"of ₹{real_revenue:,.2f} minus tracked ingredient costs "
                    f"of ₹{real_cost:,.2f}. This excludes synthetic demo orders "
                    "and other operating expenses."
                )
            else:
                answer = (
                    f"Recorded revenue is ₹{revenue:,.2f} across "
                    f"{order_count} saved orders, including synthetic demo orders."
                )

        else:
            if user["role"] == "owner":
                answer = (
                    f"Hey, boss! 🌱 Recorded revenue is ₹{revenue:,.2f} "
                    f"across {order_count} saved orders. Ask about revenue "
                    "today or yesterday, estimated profit, best sellers, "
                    "or low stock."
                )
            elif user["role"] == "cashier":
                answer = (
                    "I'm Happy, your checkout buddy! 🌱 Ask about a customer's "
                    "saved purchase history by their full name, the latest order, "
                    "or today's and yesterday's orders."
                )
            else:
                answer = (
                    "I'm Happy, your stockroom buddy! 🌱 Ask about ingredient "
                    "quantities, low stock, deliveries, or restocking needs."
                )

        return {"answer": answer, "mode": "supabase-data"}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Happy could not retrieve the latest business data."
        )

from fastapi import Query


@app.get("/api/customers/search")
def search_customers(
    q: str = Query(default="", max_length=120),
    user=Depends(require_role("cashier", "owner")),
):
    query = q.strip()

    if len(query) < 2:
        return {"customers": []}

    try:
        result = (
            supabase.table("orders")
            .select("customer_name")
            .ilike("customer_name", f"%{query}%")
            .limit(100)
            .execute()
        )

        names = sorted({
            row["customer_name"].strip()
            for row in (result.data or [])
            if row.get("customer_name")
            and row["customer_name"].strip()
        }, key=str.lower)

        return {"customers": names[:10]}

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Could not search customer records.",
        )


@app.post("/api/customers/history")
def customer_history(
    data: dict,
    user=Depends(require_role("cashier", "owner")),
):
    name = str(data.get("customer_name", "")).strip()

    if not name or len(name) > 120:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid customer name.",
        )

    try:
        orders_result = (
            supabase.table("orders")
            .select("id,customer_name,total,payment_method,created_at")
            .ilike("customer_name", name)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

        matching_orders = [
            order for order in (orders_result.data or [])
            if (order.get("customer_name") or "").strip().casefold()
            == name.casefold()
        ]

        if not matching_orders:
            return {"customer_name": name, "orders": []}

        order_ids = [order["id"] for order in matching_orders]

        items_result = (
            supabase.table("order_items")
            .select("order_id,menu_item_id,item_name,quantity,unit_price")
            .in_("order_id", order_ids)
            .execute()
        )

        items_by_order = {}
        for item in items_result.data or []:
            items_by_order.setdefault(str(item["order_id"]), []).append({
                "menu_item_id": item["menu_item_id"],
                "name": item["item_name"],
                "quantity": item["quantity"],
                "unit_price": float(item["unit_price"]),
            })

        orders = []
        for order in matching_orders:
            orders.append({
                **order,
                "total": float(order["total"]),
                "items": items_by_order.get(str(order["id"]), []),
            })

        return {"customer_name": name, "orders": orders}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve customer order history.",
        )
