import csv

rec = r'C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket\external_execution_receipts.csv'

# Group by strategy + token_id to get deduplicated positions
btc_positions = {}
eth_positions = {}

with open(rec, 'r') as f:
    for row in csv.DictReader(f):
        if row['execution_status'] != 'EXECUTED':
            continue
        
        order_id = row.get('actual_order_id', '')
        shares = float(row.get('actual_shares', 0) or 0)
        spent = float(row.get('actual_spent_usdc', 0) or 0)
        
        ticket = row['ticket_id']
        parts = ticket.split(':')
        strategy = parts[1] if len(parts) > 1 else '?'
        
        # Extract readable market name from the ticket path
        # The title is in parts[4] (the hyphenated market name)
        market_name = parts[4].replace('-', ' ') if len(parts) > 4 else ticket[:40]
        
        # Use order_id as unique key - same market can have multiple orders
        key = (market_name, order_id)
        
        if strategy == 'eth_directional_copy':
            eth_positions[key] = {'market': market_name, 'shares': shares, 'spent': spent, 'order': order_id[:20]}
        else:
            btc_positions[key] = {'market': market_name, 'shares': shares, 'spent': spent, 'order': order_id[:20]}

print(f'=== BTC Positions (btc_no_dominant) ===')
markets = {}
for key, pos in sorted(btc_positions.items()):
    market = key[0][:60]
    if market not in markets:
        markets[market] = {'shares': 0, 'spent': 0, 'orders': 0}
    markets[market]['shares'] += pos['shares']
    markets[market]['spent'] += pos['spent']
    markets[market]['orders'] += 1

for i, (m, data) in enumerate(sorted(markets.items()), 1):
    print(f'  {i}. {m:55s} | {data["shares"]:6.2f} sh | {data["spent"]:5.1f}U | {data["orders"]} order(s)')

print(f'\n  Total BTC markets: {len(markets)}')

print(f'\n=== ETH Positions (eth_directional) ===')
eth_markets = {}
for key, pos in sorted(eth_positions.items()):
    market = key[0][:60]
    if market not in eth_markets:
        eth_markets[market] = {'shares': 0, 'spent': 0, 'orders': 0}
    eth_markets[market]['shares'] += pos['shares']
    eth_markets[market]['spent'] += pos['spent']
    eth_markets[market]['orders'] += 1

for i, (m, data) in enumerate(sorted(eth_markets.items()), 1):
    print(f'  {i}. {m:55s} | {data["shares"]:6.2f} sh | {data["spent"]:5.1f}U | {data["orders"]} order(s)')

print(f'\n  Total ETH markets: {len(eth_markets)}')
print(f'\nTotal positions on Polymarket: {len(markets) + len(eth_markets)}')
