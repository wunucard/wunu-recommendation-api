from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os
# from supabase import create_client, Client  # Move import inside app section

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://wunucard.com"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic model for request body
class CardRequest(BaseModel):
    cards: List[str]

# Credit card recommendation logic
def optimize_credit_card_usage(user_cards, dataset_path="cards_dataset.csv"):
    df = pd.read_csv(dataset_path)
    user_df = df[df['card_name'].isin(user_cards)].copy()
    
    def fmt(rate):
        return f"{float(rate) * 100:.1f}%" if pd.notnull(rate) else ""
    
    def get_effective_rate(row, category_rate, is_points=False):
        if pd.isnull(category_rate):
            return 0
        rate = float(category_rate)
        if is_points:
            point_value = float(row.get('base_redemption_value', 1))
            rate *= point_value
        return rate
    
    def is_true(val):
        return str(val).strip().lower() in ['true', 'yes', '1']
    
    categories = {
        'Dining': ['Dining', 'Restaurants', 'Restaurants worldwide'],
        'Travel': ['Travel', 'Flights', 'Hotels', 'Air Travel'],
        'Groceries': ['Supermarkets', 'Grocery Stores', 'U.S. Supermarkets'],
        'Gas': ['Gas', 'Gas Stations'],
        'Online Shopping': ['Online Shopping', 'Online Retail'],
        'Entertainment': ['Entertainment', 'Streaming Services'],
        'Drugstores': ['Drugstores', 'Drug Stores']
    }
    
    recommendations = []
    covered_categories = set()
    best_cards_by_category = {}
    
    # Find best card for each category
    for category, keywords in categories.items():
        best_card = None
        best_rate = 0
        best_instructions = ""
        best_row = None
        for _, row in user_df.iterrows():
            for i in range(1, 4):
                bonus_cat = str(row.get(f'bonus_category_{i}', '')).lower()
                bonus_rate = row.get(f'bonus_rate_{i}')
                if any(keyword.lower() in bonus_cat for keyword in keywords):
                    effective_rate = get_effective_rate(row, bonus_rate, 'POINTS' in str(row.get('currency_type', '')))
                    if effective_rate > best_rate:
                        best_rate = effective_rate
                        best_card = row['card_name']
                        best_row = row
                        # Only show activation/rotating instructions if needed and not for set-rate
                        if ((row.get('rotating_categories', False) or row.get('activation_required', False)) and not is_true(row.get('user_selectable_categories', False))):
                            best_instructions = f"Remember to activate this category"
                        else:
                            best_instructions = ""
        if best_card:
            covered_categories.add(category)
            best_cards_by_category[category] = best_card
            card_info = user_df[user_df['card_name'] == best_card].iloc[0]
            currency_type = str(card_info.get('currency_type', 'CASHBACK'))
            if currency_type == 'POINTS':
                point_value = float(card_info.get('base_redemption_value', 1))
                reward_desc = f"{fmt(best_rate)} points (equivalent to {fmt(best_rate * point_value)} when redeemed)"
            else:
                reward_desc = f"{fmt(best_rate)} cashback"
            recommendations.append({
                "Category": category,
                "Card": best_card,
                "Reward Rate": reward_desc,
                "Instructions": best_instructions
            })
    # Find best catch-all card(s)
    best_catchall_rate = 0
    catchall_cards = []
    for _, row in user_df.iterrows():
        base_rate = float(row.get('base_rate', 0))
        if 'POINTS' in str(row.get('currency_type', '')):
            point_value = float(row.get('base_redemption_value', 1))
            effective_rate = base_rate * point_value
        else:
            effective_rate = base_rate
        if effective_rate > best_catchall_rate:
            best_catchall_rate = effective_rate
            catchall_cards = [row['card_name']]
        elif effective_rate == best_catchall_rate and effective_rate > 0:
            catchall_cards.append(row['card_name'])
    if catchall_cards and best_catchall_rate > 0:
        card_infos = [user_df[user_df['card_name'] == c].iloc[0] for c in catchall_cards]
        currency_type = str(card_infos[0].get('currency_type', 'CASHBACK'))
        if currency_type == 'POINTS':
            point_value = float(card_infos[0].get('base_redemption_value', 1))
            reward_desc = f"{fmt(best_catchall_rate)} points (equivalent to {fmt(best_catchall_rate * point_value)} when redeemed)"
        else:
            reward_desc = f"{fmt(best_catchall_rate)} cashback"
        card_names = ', '.join(catchall_cards)
        utilization_note = "Track your credit line utilization across these cards to avoid negative credit score impact."
        recommendations.append({
            "Category": "Everything else",
            "Card": card_names,
            "Reward Rate": reward_desc,
            "Instructions": f"Use any of these cards for all other purchases. {utilization_note}"
        })
    # Always add a separate recommendation for user-selectable cards' default category, even if already best
    for _, row in user_df.iterrows():
        if is_true(row.get('user_selectable_categories', False)):
            default_cat = str(row.get('selectable_category_options', '')).split(',')[0].strip()
            # Find the bonus rate for the default category
            default_rate = None
            for i in range(1, 4):
                bonus_cat = str(row.get(f'bonus_category_{i}', '')).lower()
                bonus_rate = row.get(f'bonus_rate_{i}')
                if default_cat.lower() in bonus_cat:
                    default_rate = bonus_rate
                    break
            # If not found, use the user-selected category rate
            if default_rate is None:
                for i in range(1, 4):
                    bonus_cat = str(row.get(f'bonus_category_{i}', '')).lower()
                    bonus_rate = row.get(f'bonus_rate_{i}')
                    if 'choice category' in bonus_cat or 'user-selected' in bonus_cat:
                        default_rate = bonus_rate
                        break
            if default_rate is not None:
                currency_type = str(row.get('currency_type', 'CASHBACK'))
                if currency_type == 'POINTS':
                    point_value = float(row.get('base_redemption_value', 1))
                    reward_desc = f"{fmt(default_rate)} points (equivalent to {fmt(float(default_rate) * point_value)} when redeemed)"
                else:
                    reward_desc = f"{fmt(default_rate)} cashback"
                recommendations.append({
                    "Category": default_cat,
                    "Card": row['card_name'],
                    "Reward Rate": reward_desc,
                    "Instructions": f"You have {reward_desc} on {default_cat} for {row['card_name']}. Recommend changing to a high-spend category not covered by other cards."
                })
    return recommendations

# API endpoint
@app.post("/recommend")
async def recommend(request: Request):
    from supabase import create_client, Client
    supabase: Client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY")
    )
    data = await request.json()
    cards = data.get("cards", [])
    recommendations = optimize_credit_card_usage(cards)

    # Log the query
    supabase.table("recommendation_logs").insert({
        "cards": cards,
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent")
    }).execute()

    return {"recommendations": recommendations}
