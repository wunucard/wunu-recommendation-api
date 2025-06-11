from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os
import re
import json
import csv
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

# Manual normalization mapping for categories (shared by all functions)
manual = {
    'Travel (via Chase Travel portal)': 'Travel via Chase Travel portal',
    'Travel via Chase Travel portal': 'Travel via Chase Travel portal',
    'Travel (via CapOne Travel)': 'Travel via CapOne Travel',
    'Hotels & Rental Cars via CapOne Travel': 'Hotels & Rental Cars via CapOne Travel',
    'Flights via CapOne Travel': 'Flights via CapOne Travel',
    'Travel booked via BofA Travel Center': 'Travel via BofA Travel Center',
    'Prepaid Hotels (via Amex Travel)': 'Prepaid Hotels via Amex Travel',
    'Travel (general, after $300 credit)': 'Travel (general, after $300 credit)',
    'Flights via Chase Travel portal (5x) & Hotels/Car rentals via Chase Travel (10x)': 'Flights/Hotels/Car rentals via Chase Travel portal',
    'Dining (restaurants & delivery)': 'Dining (restaurants & delivery)',
    'Dining (restaurants)': 'Dining (restaurants)',
    'Dining (incl. delivery)': 'Dining (restaurants & delivery)',
    'Dining (up to $8k combined)': 'Dining (up to $8k combined)',
    'Dining & Drugstores': 'Dining & Drugstores',
    'Dining & Entertainment': 'Dining & Entertainment',
    'Drugstore purchases': 'Drugstores',
    'Grocery Stores & Wholesale Clubs': 'Grocery Stores & Wholesale Clubs',
    'Grocery Stores (up to $8k combined)': 'Grocery Stores (up to $8k combined)',
    'U.S. Supermarkets (up to $25k/yr)': 'U.S. Supermarkets (up to $25k/yr)',
    'U.S. Supermarkets (up to $6k/yr)': 'U.S. Supermarkets (up to $6k/yr)',
    'Online groceries & Streaming services': 'Online groceries & Streaming services',
    'Popular Streaming Services': 'Popular Streaming Services',
    'Amazon.com, Whole Foods, Amazon Fresh, Chase Travel': 'Amazon.com, Whole Foods, Amazon Fresh, Chase Travel',
    'Amazon.com & Whole Foods (Prime members)': 'Amazon.com & Whole Foods (Prime members)',
    'Target purchases (in-store and online)': 'Target purchases (in-store and online)',
    'Marriott hotel purchases': 'Marriott hotel purchases',
    'Gas Stations (up to $8k combined)': 'Gas Stations (up to $8k combined)',
    'U.S. Gas Stations (up to $6k/yr)': 'U.S. Gas Stations (up to $6k/yr)',
    'Gas & Restaurants (combined)': 'Gas & Restaurants (combined)',
    'Everything Else': 'Other',
    'Office Supply & Internet/Phone/Cable (combined)': 'Office Supply & Internet/Phone/Cable (combined)',
    'Social Media/Search Ads & Internet/Phone services; Rideshare': 'Social Media/Search Ads & Internet/Phone services; Rideshare',
    'Monthly spend over $1,000': 'Monthly spend over $1,000',
    'Referrals (30-day window)': 'Referrals (30-day window)',
    'Top 2 spend categories each month (ads, tech, dining, gas, transit, wireless)': 'Top 2 spend categories each month',
    'Choice category (user-selected)': 'User-Selected Category',
    'Rotating bonus categories (quarterly)': 'Rotating Category',
    'Rotating quarterly categories': 'Rotating Category',
    '3% category (user-selected quarterly)': 'User-Selected Category',
    '2% category (user-selected quarterly)': 'User-Selected Category',
    'Rapid Rewards hotel & car partners': 'Rapid Rewards hotel & car partners',
    'United Airlines purchases': 'United Airlines purchases',
    'Delta Air Lines purchases': 'Delta Air Lines purchases',
    'Southwest Airlines purchases': 'Southwest Airlines purchases',
    'Hotel stays': 'Hotel stays',
    'Air Travel & Hotels': 'Air Travel & Hotels',
    'Restaurants & Supermarkets': 'Restaurants & Supermarkets',
    'U.S. Supermarkets & Gas (combined up to $6k/yr)': 'U.S. Supermarkets & Gas (combined up to $6k/yr)',
    'Travel & Transit (global)': 'Travel & Transit (global)',
    'Travel, Transit, Gas, Dining, Streaming, Phone Plans': 'Travel, Transit, Gas, Dining, Streaming, Phone Plans',
    'Flights (booked directly or via Amex Travel)': 'Flights via Amex Travel',
    'Flights (direct or Amex Travel)': 'Flights via Amex Travel',
    'Prepaid Hotels (via Amex Travel)': 'Prepaid Hotels via Amex Travel',
    'Hotels & Rental Cars via CapOne Travel': 'Hotels & Rental Cars via CapOne Travel',
    'Travel booked via BofA Travel Center': 'Travel via BofA Travel Center',
    'Travel (general, after $300 credit)': 'Travel (general, after $300 credit)',
    'Travel via Chase Travel portal': 'Travel via Chase Travel portal',
    'Travel (via Chase Travel portal)': 'Travel via Chase Travel portal',
    'Travel (via CapOne Travel)': 'Travel via CapOne Travel',
    'Travel (via BofA Travel Center)': 'Travel via BofA Travel Center',
    'Prepaid Hotels (via Amex Travel)': 'Prepaid Hotels via Amex Travel',
    'Travel (general, after $300 credit)': 'Travel (general, after $300 credit)',
    'Flights via Chase Travel portal (5x) & Hotels/Car rentals via Chase Travel (10x)': 'Flights/Hotels/Car rentals via Chase Travel portal',
}

def build_category_hierarchy(df):
    hierarchy = {}
    for i in range(1, 4):
        for _, row in df.iterrows():
            raw_cat = str(row[f'bonus_category_{i}']).strip()
            if not raw_cat or raw_cat == 'nan':
                continue
            norm_cat = manual.get(raw_cat, raw_cat)
            parent = raw_cat.split()[0]
            if isinstance(norm_cat, list):
                for nc in norm_cat:
                    if parent not in hierarchy:
                        hierarchy[parent] = {"subcategories": set()}
                    if nc != parent:
                        hierarchy[parent]["subcategories"].add(nc)
            else:
                if parent not in hierarchy:
                    hierarchy[parent] = {"subcategories": set()}
                if norm_cat != parent:
                    hierarchy[parent]["subcategories"].add(norm_cat)
    # Remove redundant subcategories (normalize)
    for parent in hierarchy:
        hierarchy[parent]["subcategories"] = list(set(hierarchy[parent]["subcategories"]))
        hierarchy[parent]["other"] = f"Other {parent}"
    return hierarchy

def optimize_credit_card_usage(user_cards, dataset_path="cards_dataset.csv"):
    df = pd.read_csv(dataset_path)
    user_df = df[df['card_name'].isin(user_cards)].copy()
    hierarchy = build_category_hierarchy(df)
    cat_to_cards = {}
    for _, row in user_df.iterrows():
        for i in range(1, 4):
            raw_cat = str(row.get(f'bonus_category_{i}', '')).strip()
            rate = row.get(f'bonus_rate_{i}')
            if not raw_cat or raw_cat == 'nan' or pd.isnull(rate) or rate == 'no':
                continue
            try:
                rate_val = float(rate)
            except ValueError:
                continue
            norm_cat = manual.get(raw_cat, raw_cat)
            parent = raw_cat.split()[0]
            if isinstance(norm_cat, list):
                for nc in norm_cat:
                    if nc not in cat_to_cards:
                        cat_to_cards[nc] = []
                    cat_to_cards[nc].append({
                        'card': row['card_name'],
                        'rate': rate_val,
                        'currency_type': row.get('currency_type', 'CASHBACK'),
                        'base_redemption_value': row.get('base_redemption_value', 1)
                    })
                    if nc == parent:
                        if f'Other {parent}' not in cat_to_cards:
                            cat_to_cards[f'Other {parent}'] = []
                        cat_to_cards[f'Other {parent}'].append({
                            'card': row['card_name'],
                            'rate': rate_val,
                            'currency_type': row.get('currency_type', 'CASHBACK'),
                            'base_redemption_value': row.get('base_redemption_value', 1)
                        })
            else:
                if norm_cat not in cat_to_cards:
                    cat_to_cards[norm_cat] = []
                cat_to_cards[norm_cat].append({
                    'card': row['card_name'],
                    'rate': rate_val,
                    'currency_type': row.get('currency_type', 'CASHBACK'),
                    'base_redemption_value': row.get('base_redemption_value', 1)
                })
                if norm_cat == parent:
                    if f'Other {parent}' not in cat_to_cards:
                        cat_to_cards[f'Other {parent}'] = []
                    cat_to_cards[f'Other {parent}'].append({
                        'card': row['card_name'],
                        'rate': rate_val,
                        'currency_type': row.get('currency_type', 'CASHBACK'),
                        'base_redemption_value': row.get('base_redemption_value', 1)
                    })
    recommendations = []
    for parent, data in hierarchy.items():
        for subcat in data['subcategories']:
            if subcat in cat_to_cards:
                best = max(cat_to_cards[subcat], key=lambda x: x['rate'])
                reward_desc = f"{best['rate']*100:.1f}% cashback" if best['currency_type'] == 'CASHBACK' else f"{best['rate']*100:.1f}% points (equivalent to {best['rate']*float(best['base_redemption_value'])*100:.1f}% when redeemed)"
                recommendations.append({
                    'Category': subcat,
                    'Card': best['card'],
                    'Reward Rate': reward_desc,
                    'Instructions': ''
                })
        other_cat = data['other']
        if other_cat in cat_to_cards:
            subcat_cards = set()
            for subcat in data['subcategories']:
                if subcat in cat_to_cards:
                    subcat_cards.update([x['card'] for x in cat_to_cards[subcat]])
            filtered = [x for x in cat_to_cards[other_cat] if x['card'] not in subcat_cards]
            if filtered:
                max_rate = max(x['rate'] for x in filtered)
                bests = [x for x in filtered if x['rate'] == max_rate]
                card_names = ', '.join([b['card'] for b in bests])
                reward_desc = f"{max_rate*100:.1f}% cashback" if bests[0]['currency_type'] == 'CASHBACK' else f"{max_rate*100:.1f}% points (equivalent to {max_rate*float(bests[0]['base_redemption_value'])*100:.1f}% when redeemed)"
                recommendations.append({
                    'Category': other_cat,
                    'Card': card_names,
                    'Reward Rate': reward_desc,
                    'Instructions': f'Use for all {parent.lower()} purchases not covered by a more specific category.'
                })
    # Rent handling (as before)
    rent_recommendations = []
    for _, row in user_df.iterrows():
        rent_cap = str(row.get('rent_payment_capability', '')).strip().lower()
        if rent_cap in ['yes', 'limited']:
            rewards = str(row.get('rewards_on_rent', '')).strip()
            fee = str(row.get('transaction_fee', '')).strip()
            notes = str(row.get('notes_rent_payments', '')).strip()
            card_name = row['card_name']
            fee_val = 9999
            try:
                if fee.startswith('$'):
                    fee_val = float(fee.replace('$','').replace(',',''))
                elif fee.lower() == 'varies':
                    fee_val = 1000
                elif fee == '':
                    fee_val = 9999
                else:
                    fee_val = float(fee)
            except:
                fee_val = 9999
            rent_recommendations.append({
                'card_name': card_name,
                'rewards': rewards,
                'fee': fee_val,
                'fee_str': fee,
                'cap': rent_cap,
                'notes': notes
            })
    rent_recommendations.sort(key=lambda x: (x['cap'] != 'yes', x['fee']))
    if rent_recommendations:
        best = rent_recommendations[0]
        instructions = f"Use this card for rent payments. Fee: {best['fee_str']}. {best['notes']}".strip()
        recommendations.append({
            'Category': 'Rent',
            'Card': best['card_name'],
            'Reward Rate': best['rewards'],
            'Instructions': instructions
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

def load_category_hierarchy(json_path="categories.json"):
    with open(json_path, "r") as f:
        return json.load(f)

def map_to_general_category(bonus_category, category_hierarchy):
    for general, data in category_hierarchy.items():
        for kw in data["keywords"]:
            if re.search(kw, bonus_category, re.IGNORECASE):
                return general
    return None

def match_subcategory(general_category, bonus_category, category_hierarchy):
    subcats = category_hierarchy[general_category].get("subcategories", {})
    for subcat, subdata in subcats.items():
        for pat in subdata["patterns"]:
            if re.search(pat, bonus_category, re.IGNORECASE):
                return subcat, subdata["priority"]
    return None, 0

def get_all_cards():
    cards = []
    with open('cards_dataset.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            card_name_key = 'card_name' if 'card_name' in row else '\ufeffcard_name'
            card = {
                'name': row[card_name_key],
                'bonus_categories': {}
            }
            for key, value in row.items():
                if key != card_name_key:
                    card['bonus_categories'][key] = value
            cards.append(card)
    return cards

def optimize_credit_card_usage(cards):
    # Placeholder for the old logic
    return {}

if __name__ == "__main__":
    test_cards = ["Chase Sapphire Preferred", "Bilt Mastercard", "Amazon Prime Rewards Visa", "Chase Freedom Flex"]
    print("\nRaw rates for 'Other Travel':")
    df = pd.read_csv("cards_dataset.csv")
    user_df = df[df['card_name'].isin(test_cards)].copy()
    for _, row in user_df.iterrows():
        for i in range(1, 5):
            cat = str(row.get(f'bonus_category_{i}', '')).strip()
            rate = row.get(f'bonus_rate_{i}')
            if cat == 'Travel' and pd.notnull(rate):
                print(f"{row['card_name']}: {rate} ({float(rate)*100:.0f}% if rate is numeric)")
    print("\nRaw rates for 'Travel (outside Chase portal)':")
    found = False
    for _, row in user_df.iterrows():
        for i in range(1, 5):
            cat = str(row.get(f'bonus_category_{i}', '')).strip()
            rate = row.get(f'bonus_rate_{i}')
            if cat == 'Travel (outside Chase portal)' and pd.notnull(rate):
                print(f"{row['card_name']}: {rate} ({float(rate)*100:.0f}% if rate is numeric)")
                found = True
    if not found:
        print("No rates found.")
