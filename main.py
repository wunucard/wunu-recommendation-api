from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os
from supabase import create_client, Client

app = FastAPI()

# Create Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

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
            # Apply point value multiplier for points cards
            point_value = float(row.get('base_redemption_value', 1))
            rate *= point_value
        return rate
    
    # Define major spending categories to analyze
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
    
    # Find best card for each category
    for category, keywords in categories.items():
        best_card = None
        best_rate = 0
        best_instructions = ""
        
        for _, row in user_df.iterrows():
            # Check bonus categories
            for i in range(1, 4):
                bonus_cat = str(row.get(f'bonus_category_{i}', '')).lower()
                bonus_rate = row.get(f'bonus_rate_{i}')
                
                if any(keyword.lower() in bonus_cat for keyword in keywords):
                    effective_rate = get_effective_rate(row, bonus_rate, 'POINTS' in str(row.get('currency_type', '')))
                    
                    if effective_rate > best_rate:
                        best_rate = effective_rate
                        best_card = row['card_name']
                        
                        # Add special instructions
                        if row.get('rotating_categories', False):
                            best_instructions = f"Select this as your quarterly category"
                        elif row.get('user_selectable_categories', False):
                            best_instructions = f"Select this as your category"
                        elif row.get('activation_required', False):
                            best_instructions = f"Remember to activate this category"
                        else:
                            best_instructions = ""
        
        if best_card:
            card_info = user_df[user_df['card_name'] == best_card].iloc[0]
            currency_type = str(card_info.get('currency_type', 'CASHBACK'))
            
            if currency_type == 'POINTS':
                point_value = float(card_info.get('base_redemption_value', 1))
                effective_rate = best_rate * point_value
                reward_desc = f"{fmt(best_rate)} points (equivalent to {fmt(effective_rate)} when redeemed)"
            else:
                reward_desc = f"{fmt(best_rate)} cashback"
            
            recommendations.append({
                "Category": category,
                "Card": best_card,
                "Reward Rate": reward_desc,
                "Instructions": best_instructions
            })
    
    # Find best catch-all card
    best_catchall = None
    best_catchall_rate = 0
    
    for _, row in user_df.iterrows():
        base_rate = float(row.get('base_rate', 0))
        if 'POINTS' in str(row.get('currency_type', '')):
            point_value = float(row.get('base_redemption_value', 1))
            effective_rate = base_rate * point_value
        else:
            effective_rate = base_rate
            
        if effective_rate > best_catchall_rate:
            best_catchall_rate = effective_rate
            best_catchall = row['card_name']
    
    if best_catchall:
        card_info = user_df[user_df['card_name'] == best_catchall].iloc[0]
        currency_type = str(card_info.get('currency_type', 'CASHBACK'))
        
        if currency_type == 'POINTS':
            point_value = float(card_info.get('base_redemption_value', 1))
            effective_rate = best_catchall_rate * point_value
            reward_desc = f"{fmt(best_catchall_rate)} points (equivalent to {fmt(effective_rate)} when redeemed)"
        else:
            reward_desc = f"{fmt(best_catchall_rate)} cashback"
            
        recommendations.append({
            "Category": "Everything else",
            "Card": best_catchall,
            "Reward Rate": reward_desc,
            "Instructions": "Use this card for all other purchases"
        })
    
    return recommendations

# API endpoint
@app.post("/recommend")
async def recommend(request: Request):
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
