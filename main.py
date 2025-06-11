from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os
import re
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
    def is_false(val):
        return str(val).strip().lower() in ['false', 'no', '0', '']
    
    # Define regex patterns and priorities
    category_patterns = [
        (r"Amazon|Whole Foods|Amazon Fresh", "Amazon", 100),
        (r"Target", "Target", 100),
        (r"Nordstrom", "Nordstrom", 100),
        (r"Marriott", "Marriott", 100),
        (r"Southwest", "Southwest", 100),
        (r"Delta", "Delta", 100),
        (r"United", "United", 100),
        (r"Office Supply", "Office Supply", 100),
        (r"Rapid Rewards", "Rapid Rewards", 100),
        (r"Social Media|Search Ads", "Social Media/Search Ads", 100),
        (r"Referrals", "Referrals", 100),
        (r"Monthly spend", "Monthly Spend", 100),
        (r"Top 2 spend", "Top 2 Spend", 100),
        (r"Choice category|user-selected", "User-Selected Category", 90),
        (r"Prepaid Hotels", "Prepaid Hotels", 100),
        (r"BofA Travel Center", "BofA Travel Center", 100),
        (r"Dining|Restaurants", "Dining", 80),
        (r"Groceries|Supermarkets|Grocery Stores|Wholesale Clubs", "Groceries", 80),
        (r"Gas", "Gas", 80),
        (r"Drugstore", "Drugstores", 80),
        (r"Streaming", "Streaming", 80),
        (r"Entertainment", "Entertainment", 80),
        (r"Travel|Flights|Hotels|Car rentals|Transit", "Travel", 80),
        (r"Online Retail|Online Shopping", "Online Shopping", 80),
        (r"Phone|Internet|Cable|Wireless", "Phone/Internet", 80),
        (r"Rideshare", "Rideshare", 80),
        (r"Everything Else", "Everything Else", 10),
        (r"Rotating", "Rotating Category", 50),
        (r"activation required", "Activation Required", 50),
    ]
    canonical_categories = [p[1] for p in category_patterns if p[2] >= 80]
    # Build card_category_matches using regex/priority
    card_category_matches = []
    for _, row in user_df.iterrows():
        for i in range(1, 4):
            bonus_cat = str(row.get(f'bonus_category_{i}', '')).strip()
            bonus_rate = row.get(f'bonus_rate_{i}')
            if not bonus_cat or bonus_cat == 'nan' or pd.isnull(bonus_rate):
                continue
            for pattern, canonical, priority in category_patterns:
                if re.search(pattern, bonus_cat, re.IGNORECASE):
                    is_rotating = is_true(row.get('rotating_categories', False)) or re.search(r'Rotating', bonus_cat, re.IGNORECASE)
                    is_activation = is_true(row.get('activation_required', False)) or re.search(r'activation required', bonus_cat, re.IGNORECASE)
                    card_category_matches.append({
                        'canonical_category': canonical,
                        'rate': float(bonus_rate),
                        'priority': priority,
                        'card_name': row['card_name'],
                        'currency_type': row.get('currency_type', 'CASHBACK'),
                        'base_redemption_value': row.get('base_redemption_value', 1),
                        'is_rotating': is_rotating,
                        'is_activation': is_activation
                    })
    # For each canonical category, pick the best card (highest priority, then highest rate)
    recommendations = []
    for cat in canonical_categories:
        best = None
        for match in card_category_matches:
            if match['canonical_category'] == cat:
                if (best is None or
                    match['priority'] > best['priority'] or
                    (match['priority'] == best['priority'] and match['rate'] > best['rate'])):
                    best = match
        if best:
            if best['currency_type'] == 'POINTS':
                point_value = float(best['base_redemption_value'])
                reward_desc = f"{best['rate']*100:.1f}% points (equivalent to {best['rate']*point_value*100:.1f}% when redeemed)"
            else:
                reward_desc = f"{best['rate']*100:.1f}% cashback"
            instructions = ""
            if best['is_rotating'] or best['is_activation']:
                instructions = "Remember to activate this category"
            recommendations.append({
                "Category": cat,
                "Card": best['card_name'],
                "Reward Rate": reward_desc,
                "Instructions": instructions
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
