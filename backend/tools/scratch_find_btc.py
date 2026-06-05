import re
import urllib.request

url = "https://polymarket.com/crypto/bitcoin"
html = urllib.request.urlopen(
    urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
    timeout=60,
).read().decode("utf-8", "replace")
print("len", len(html))
for match in re.finditer(r'href="([^"]*(?:bitcoin|btc)[^"]*up[^"]*down[^"]*)"', html, re.I):
    print(match.group(1)[:200])
print("contains", "Up or Down" in html, "Bitcoin" in html)
