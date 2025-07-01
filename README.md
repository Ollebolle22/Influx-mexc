# MEXC WebSocket to InfluxDB

Real-time streaming of trades from MEXC to InfluxDB using WebSocket.

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
