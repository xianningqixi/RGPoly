from btc_signal_bot import discover_slugs, parse_slug_window
import time

now = int(time.time())
items = []
for slug in discover_slugs():
    parsed = parse_slug_window(slug)
    if parsed:
        label, start, end = parsed
        items.append((start - now, label, slug))
for item in sorted(set(items))[:30]:
    print(item)
print("count", len(items))
