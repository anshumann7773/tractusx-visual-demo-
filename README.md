# Tractus-X digital twin demo

Bob (supplier) shares brake disc data with Alice (car maker) the Catena-X way:

1. Bob registers a **digital twin** of his part in a real **Tractus-X Digital Twin Registry**.
2. Alice finds Bob's registry in his connector catalog (Catena-X type `DigitalTwinRegistry`).
3. Alice gets a contract, looks up the part, and learns where its data lives.
4. Alice gets a second contract and fetches the data directly from Bob.

## Use it

```bash
bash setup.sh        # once (a few minutes if the connectors are already built, else 10-20 minutes)
bash run-demo.sh     # run the demo – the live view opens at http://localhost:8765
docker compose down  # when you're done
```

## What's inside

| File | What it does |
|---|---|
| `setup.sh` | One-time setup |
| `run-demo.sh` | Starts everything fresh and runs the demo |
| `demo.py` | The demo itself: 8 steps, pauses before each one (`--details` shows JSON, IDs, tokens) |
| `dashboard.py`, `dashboard.html` | Live view in the browser (Hochschule Aalen look) |
| `docker-compose.yml` | Registry + its database, Bob's part data server, the two connectors |
| `brake-disc.json` | Bob's part data (fictional) |
| `Dockerfile` | Builds Bob's and Alice's connectors |

## Honest notes for the audience

- The registry is the real Tractus-X Digital Twin Registry (v0.13.0), in its local mode without login.
- The connectors are plain Eclipse EDC from the official samples. Tractus-X EDC is built on top of EDC.
- The brake disc data is fictional and uses a simplified format, not an official Catena-X aspect model.
- The policy allows everyone. In Catena-X, policies check membership, the framework agreement and the BPN.
- Company identities (BPN, verifiable credentials) are not part of this demo.

Both demo folders use the same ports, so only one demo runs at a time. Starting one stops the other automatically.
