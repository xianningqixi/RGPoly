from py_clob_client_v2 import ClobClient
import os

private_key = os.getenv("PRIVATE_KEY")
if not private_key:
    raise RuntimeError("PRIVATE_KEY is missing")

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=private_key
)

credentials = client.create_or_derive_api_key()
print(credentials)