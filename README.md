# MEXC WebSocket to InfluxDB

Real-time streaming of trades and balances from MEXC to InfluxDB.

### Trades

Mätningen `mexc_trade` lagrar endast de fält som faktiskt skrivs in av koden:

- taggarna `symbol` och `side`
- fälten `price` och `volume`
- tidsstämpeln från `time`

Ingen PnL räknas automatiskt. Vill du följa vinst och förlust behöver du
beräkna detta separat eller använda andra API-endpoints.

### Balans

Mätningen `mexc_balance` lagrar fälten `asset`, `free` och `locked` för varje tillgång.

## Environment Variables

- `MEXC_SYMBOL` — e.g. `BTC_USDT`
- `INFLUX_URL` — e.g. `http://localhost:8086`
- `INFLUX_TOKEN` — your InfluxDB API token
- `INFLUX_ORG` — your InfluxDB organization name
- `INFLUX_BUCKET` — e.g. `mexc`

## Build & Push

```bash
docker build -t ghcr.io/<your-github-username>/mexc-ws-influx:latest .
docker push ghcr.io/<your-github-username>/mexc-ws-influx:latest
```
