import csv
from pathlib import Path

rec = Path.cwd() / "external_execution_receipts.csv"

with open(rec, 'r') as f:
    for i, row in enumerate(csv.DictReader(f)):
        if row['execution_status'] == 'EXECUTED' and i < 5:
            tid = row['ticket_id']
            iid = row['intent_id']
            strategy = row['source_strategy']
            spent = row['actual_spent_usdc']
            
            # Try to parse market name from intent_id
            parts = iid.split(':')
            market_name = parts[4].replace('-', ' ') if len(parts) > 4 else '(unknown)'
            outcome = parts[6] if len(parts) > 6 else '?'
            
            print(f'Market: {market_name[:50]:50s} | {outcome:4s} | {spent}U | {strategy[:25]}')
