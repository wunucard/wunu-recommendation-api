from main import optimize_credit_card_usage
import json

cards = [
    'Harvard FCU Platinum Rewards',
    'Bank of America Customized Cash Rewards',
    'Chase Sapphire Preferred',
    'Chase Amazon Prime Visa',
    'Bilt Mastercard'
]
recommendations = optimize_credit_card_usage(cards)

print(json.dumps(recommendations, indent=2)) 