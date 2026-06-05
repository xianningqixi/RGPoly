import csv
from pathlib import Path

rec = Path.cwd() / "external_execution_receipts.csv"

positions = {}
with open(rec, 'r') as f:
    for row in csv.DictReader(f):
        if row['execution_status'] != 'EXECUTED':
            continue
        
        iid = row['intent_id']
        parts = iid.split(':')
        market_name = parts[4].replace('-', ' ') if len(parts) > 4 else '(unknown)'
        outcome = parts[6] if len(parts) > 6 else '?'
        strategy = parts[1] if len(parts) > 1 else row['source_strategy']
        
        spent = float(row.get('actual_spent_usdc', 0) or 0)
        
        # Group by market_name
        key = market_name
        if key not in positions:
            positions[key] = {'spent': 0, 'strategy': strategy, 'outcome': outcome}
        positions[key]['spent'] += spent

# Separate BTC and ETH
btc = {k: v for k, v in positions.items() if 'eth' not in k.lower()}
eth = {k: v for k, v in positions.items() if 'eth' in k.lower()}

print(f'=== BTC Positions ({len(btc)}) ===')
for i, (m, d) in enumerate(sorted(btc.items()), 1):
    print(f'  {i}. {m[:55]:55s} | {d["outcome"]:4s} | {d["spent"]:5.1f}U')

print(f'\n=== ETH Positions ({len(eth)}) ===')
for i, (m, d) in enumerate(sorted(eth.items()), 1):
    print(f'  {i}. {m[:55]:55s} | {d["outcome"]:4s} | {d["spent"]:5.1f}U')

print(f'\nTotal: {len(btc)} BTC + {len(eth)} ETH = {len(positions)}')
