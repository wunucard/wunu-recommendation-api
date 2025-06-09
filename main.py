from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
    
    recommendations = []
    
    # First pass: Build recommendations for each card (without catch-all logic)
    for _, row in user_df.iterrows():
        card_name = row['card_name']
        recs = []
        
        # Bonus categories
        if pd.notnull(row['bonus_category_1']) and float(row['bonus_rate_1']) > float(row['base_rate']):
            recs.append(f"{row['bonus_category_1']}: {fmt(row['bonus_rate_1'])}")
        if pd.notnull(row['bonus_category_2']) and float(row['bonus_rate_2']) > float(row['base_rate']):
            recs.append(f"{row['bonus_category_2']}: {fmt(row['bonus_rate_2'])}")
        if pd.notnull(row['bonus_category_3']) and float(row['bonus_rate_3']) > float(row['base_rate']):
            recs.append(f"{row['bonus_category_3']}: {fmt(row['bonus_rate_3'])}")
        
        # Foreign transaction
        try:
            foreign_fee = float(row['foreign_transaction_fee'])
        except:
            foreign_fee = 0.03
        if foreign_fee == 0.0:
            recs.append("✅ Good for foreign purchases (no foreign fee)")
        else:
            recs.append("❌ Avoid abroad (foreign fee)")
        
        # Rent payment
        rent_capability = str(row.get("rent_payment_capability", "")).strip().lower()
        rewards_on_rent = str(row.get("rewards_on_rent", "None")).strip()
        rent_fee = str(row.get("transaction_fee", "Unknown")).strip()
        rent_notes = str(row.get("notes_rent_payments", "")).strip()
        
        if "yes" in rent_capability:
            recs.append(f"✅ Good for rent payments ({rewards_on_rent}, {rent_fee})")
        elif "limited" in rent_capability:
            recs.append(f"⚠️ Rent payments typically incur fees; rewards may not offset costs.")
        elif "no" in rent_capability:
            recs.append("❌ Not suitable for rent payments")
        
        recommendations.append({
            "Card Name": card_name,
            "Optimal Uses": "\n".join(recs)
        })
    
    # Second pass: Determine the best catch-all card AFTER processing all cards
    if not user_df.empty:
        # Find card with highest base rate
        best_catchall = user_df.loc[user_df['base_rate'].idxmax()]
        best_catchall_rate = float(best_catchall['base_rate'])
        
        # Only recommend as catch-all if rate is good enough
        if best_catchall_rate >= 0.015:
            # Add catch-all recommendation to the best card only
            for rec in recommendations:
                if rec["Card Name"] == best_catchall['card_name']:
                    if rec["Optimal Uses"]:  # Add newline if there are existing recommendations
                        rec["Optimal Uses"] += f"\n🎯 **Best catch-all card** ({fmt(best_catchall_rate)})"
                    else:  # First recommendation for this card
                        rec["Optimal Uses"] = f"🎯 **Best catch-all card** ({fmt(best_catchall_rate)})"
                    break
    
    return recommendations

# API endpoint
@app.post("/recommend")
async def recommend(request: CardRequest):
    cards = request.cards
    recommendations = optimize_credit_card_usage(cards)
    return {"recommendations": recommendations}
