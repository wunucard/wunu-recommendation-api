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

def optimize_credit_card_usage(cards, test_cards):
    recommendations = {}
    for card in cards:
        if isinstance(card, dict) and 'name' in card and card['name'] in test_cards:
            for i in range(1, 5):
                bonus_rate_key = f'bonus_rate_{i}'
                if bonus_rate_key in card['bonus_categories']:
                    bonus_rate = card['bonus_categories'][bonus_rate_key]
                    for j in range(1, 5):
                        main_category_key = f'main_category_{i}.{j}'
                        if main_category_key in card['bonus_categories']:
                            category = card['bonus_categories'][main_category_key]
                            if category and category.strip():  # Check if category is not blank
                                if category not in recommendations:
                                    recommendations[category] = []
                                try:
                                    rate_float = float(bonus_rate) if bonus_rate else 0
                                    recommendations[category].append((card['name'], rate_float))
                                except ValueError:
                                    continue
    return recommendations

# API endpoint
@app.post("/recommend")
async def recommend(request: CardRequest):
    cards = request.cards
    recommendations = optimize_credit_card_usage(get_all_cards(), cards)
    formatted_recommendations = []
    for category, card_rates in recommendations.items():
        if not card_rates:
            continue
        max_rate = max(card_rates, key=lambda x: x[1])[1]
        max_cards = [card for card, rate in card_rates if rate == max_rate]
        default_rate = 0.01  # Assuming default rate is 1%
        if max_rate > default_rate:
            if len(max_cards) > 1:
                formatted_recommendations.append({
                    "Category": category,
                    "Card": ", ".join(max_cards),
                    "Reward Rate": f"{max_rate*100:.1f}%",
                    "Instructions": f"Use either {', '.join(max_cards)} for {category} purchases"
                })
            else:
                formatted_recommendations.append({
                    "Category": category,
                    "Card": max_cards[0],
                    "Reward Rate": f"{max_rate*100:.1f}%",
                    "Instructions": f"Use {max_cards[0]} for {category} purchases"
                })
            for card, rate in card_rates:
                if card not in max_cards and rate > default_rate:
                    formatted_recommendations.append({
                        "Category": category,
                        "Card": card,
                        "Reward Rate": f"{rate*100:.1f}%",
                        "Instructions": f"Use {card} for all other purchases in {category}"
                    })
    base_rate = 0.01  # Assuming base rate is 1%
    if len(cards) > 1:
        formatted_recommendations.append({
            "Category": "Catch-all",
            "Card": ", ".join(cards),
            "Reward Rate": f"{base_rate*100:.1f}%",
            "Instructions": f"Use either {', '.join(cards)} as a catch-all card"
        })
    else:
        formatted_recommendations.append({
            "Category": "Catch-all",
            "Card": cards[0],
            "Reward Rate": f"{base_rate*100:.1f}%",
            "Instructions": f"Use {cards[0]} as a catch-all card"
        })
    return {"recommendations": formatted_recommendations}

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
    with open('cards_dataset.v03.csv', 'r') as f:
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

if __name__ == "__main__":
    # User selection of cards
    test_cards = []  # This will be populated with user-selected cards
    print("\nRaw rates for 'Other Travel':")
    df = pd.read_csv("cards_dataset.v03.csv")
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

    # Generate personalized recommendations
    all_cards = get_all_cards()
    recommendations = optimize_credit_card_usage(all_cards, test_cards)
    print("\nPersonalized Credit Card Recommendations:")
    for category, card_rates in recommendations.items():
        if not card_rates:
            continue
        max_rate = max(card_rates, key=lambda x: x[1])[1]
        max_cards = [card for card, rate in card_rates if rate == max_rate]
        default_rate = 0.01  # Assuming default rate is 1%
        if max_rate > default_rate:
            print(f"{category}:")
            if len(max_cards) > 1:
                print(f"- Use either {', '.join(max_cards)} for {category} purchases ({max_rate*100:.1f}% back)")
            else:
                print(f"- Use {max_cards[0]} for {category} purchases ({max_rate*100:.1f}% back)")
            for card, rate in card_rates:
                if card not in max_cards and rate > default_rate:
                    print(f"- Use {card} for all other purchases in {category} ({rate*100:.1f}% back)")
    print("\nCatch-all Card Recommendations:")
    base_rate = 0.01  # Assuming base rate is 1%
    if len(test_cards) > 1:
        print(f"- Use either {', '.join(test_cards)} as a catch-all card ({base_rate*100:.1f}% back)")
    else:
        print(f"- Use {test_cards[0]} as a catch-all card ({base_rate*100:.1f}% back)")
