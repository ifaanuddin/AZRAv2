
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

ingredients = [
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

menu = [
    {"id": "espresso", "name": "Espresso", "price": 120},
    {"id": "latte", "name": "Cafe Latte", "price": 180},
    {"id": "cappuccino", "name": "Cappuccino", "price": 170},
    {"id": "coldcoffee", "name": "Cold Coffee", "price": 200},
    {"id": "sandwich", "name": "Grilled Sandwich", "price": 220},
    {"id": "brownie", "name": "Chocolate Brownie", "price": 150},
]

recipes = [
    ("espresso", "beans", 18),
    ("latte", "beans", 18),
    ("latte", "milk", 200),
    ("cappuccino", "beans", 18),
    ("cappuccino", "milk", 150),
    ("coldcoffee", "beans", 18),
    ("coldcoffee", "milk", 200),
    ("coldcoffee", "syrup", 20),
    ("sandwich", "bread", 2),
    ("sandwich", "cheese", 40),
    ("brownie", "chocolate", 60),
]

# Insert only missing ingredients so rerunning this script
# never resets stock quantities.
existing = supabase.table("ingredients").select("id").execute()
existing_ids = {row["id"] for row in existing.data}

missing = [item for item in ingredients if item["id"] not in existing_ids]
if missing:
    supabase.table("ingredients").insert(missing).execute()

# Upsert menu and recipes safely using their primary keys.
supabase.table("menu_items").upsert(
    [{**item, "active": True} for item in menu]
).execute()

supabase.table("recipes").upsert([
    {"menu_item_id": item_id, "ingredient_id": ingredient_id,
     "quantity": quantity}
    for item_id, ingredient_id, quantity in recipes
]).execute()

print("AZRA database initialized successfully!")
print("Ingredients:", len(
    supabase.table("ingredients").select("id").execute().data
))
print("Menu items:", len(
    supabase.table("menu_items").select("id").execute().data
))
print("Recipes:", len(
    supabase.table("recipes").select("menu_item_id").execute().data
))
