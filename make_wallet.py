from solders.keypair import Keypair
import json, os

kp = Keypair()

# IMPORTANT: bytes(kp) is the full 64-byte keypair (seed + pubkey)
raw64 = bytes(kp)

with open("jupiter_alt.json", "w", encoding="utf-8") as f:
    json.dump(list(raw64), f)

print("Created:", os.path.abspath("jupiter_alt.json"))
print("PUBKEY:", kp.pubkey())

