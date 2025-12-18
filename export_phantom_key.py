import json
import base58

# Load your Solana secret key (64 bytes) from the JSON file
with open("jupiter_alt.json", "r", encoding="utf-8") as f:
    secret = bytes(json.load(f))

# Print the base58-encoded secret key (what Phantom wants for "Import Private Key")
print(base58.b58encode(secret).decode())
