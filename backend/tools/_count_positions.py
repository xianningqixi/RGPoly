import csv
from pathlib import Path

rec = Path.cwd() / "external_execution_receipts.csv"

positions = {}
with open(rec, 'r') as f:
    for row in csv.DictReader(f):
        if row['execution_status'] != 'EXECUTED':
            continue
        ticket_parts = row['ticket_id'].split(':')
        title = ticket_parts[5].replace('-', ' ') if len(ticket_parts) > 5 else row['ticket_id'][:30]
        shares = float(row.get('actual_shares', 0) or 0)
        spent = float(row.get('actual_spent_usdc', 0) or 0)
        strategy = ticket_parts[1] if len(ticket_parts) > 1 else '?'

        if title not in positions:
            positions[title] = {'shares': 0, 'spent': 0, 'count': 0, 'strategy': strategy}
        positions[title]['shares'] += shares
        positions[title]['spent'] += spent
        positions[title]['count'] += 1

n = 0
for title, pos in sorted(positions.items()):
    n += 1
    tag = '(ETH)' if 'eth' in title.lower() else '(BTC)'
    print(f'{n:2d}. {title[:55]:55s} | {pos["shares"]:8.2f} sh | {pos["spent"]:5.1f}U | {pos["count"]} tx | {tag}')

print(f'\nTotal: {n} distinct positions')
