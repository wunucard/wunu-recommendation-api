from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd

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
            recs.append("✅ Good for foreign purchases")
        else:
            recs.append("❌ Avoid abroad (foreign fee)")

        # Rent payment
        rent_capability = str(row.get("rent_payment_capability", "")).strip().lower()
        rewards_on_rent = str(row.get("rewards_on_rent", "None")).strip()
        rent_fee = str(row.get("transaction_fee", "Unknown")).strip()
        rent_notes = str(row.get("notes_rent_payments", "")).strip()

        if rent_capability == "yes":
            recs.append(f"✅ Good for rent payments ({rewards_on_rent}, {rent_fee})")
        elif rent_capability == "limited":
            recs.append(f"⚠️ Can be used for rent ({rewards_on_rent}, {rent_fee})")
        elif rent_capability == "no":
            recs.append("❌ Not suitable for rent payments")

        if rent_notes:
            recs.append(f"📝 {rent_notes}")

        # Catch-all card logic
        if float(row['base_rate']) >= 0.015:
            recs.append(f"Use as catch-all card ({fmt(row['base_rate'])})")

        recommendations.append({
            "Card Name": card_name,
            "Optimal Uses": "\n".join(recs)
        })

    return recommendations


# API endpoint
@app.post("/recommend")
async def recommend(request: CardRequest):
    cards = request.cards
    recommendations = optimize_credit_card_usage(cards)
    return {"recommendations": recommendations}
