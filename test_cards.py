from main import optimize_credit_card_usage
import json

cards = ['Harvard FCU Platinum Rewards', 'Bank of America Customized Cash Rewards']
recommendations = optimize_credit_card_usage(cards)

print(json.dumps(recommendations, indent=2)) 