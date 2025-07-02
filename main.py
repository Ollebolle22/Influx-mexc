import asyncio
import json
import os
import hmac
import hashlib
import time
import logging
import requests
import websockets
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WriteOptions

# Logging
logging.basicConfig(format='%(asctime)s | %(levelname)s | %(message)s', level=logging.INFO)

# Env
MEXC_API_KEY = os.getenv("MEXC_API_KEY")
MEXC_SECRET_KEY = os.getenv("MEXC_SECRET_KEY")
MEXC_SYMBOL = os.getenv("MEXC_SYMBOL", "BTCUSDT").lower()
INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=1))

def sign(params: dict, secret: str) -> str:
    query = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

def get_my_trades():
    endpoint = "https://api.mexc.com/api/v3/myTrades"
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": MEXC_SYMBOL.upper(),
        "timestamp": timestamp,
    }
    signature = sign(params, MEXC_SECRET_KEY)
    headers = {"X-MEXC-APIKEY": MEXC_API_KEY}
    params["signature"] = signature
    resp = requests.get(endpoint, headers=headers, params=params)
    return resp.json()

def get_wallet_balances():
    endpoint = "https://api.mexc.com/api/v3/account"
    timestamp = int(time.time() * 1000)
    params = {
        "timestamp": timestamp,
    }
    signature = sign(params, MEXC_SECRET_KEY)
    headers = {"X-MEXC-APIKEY": MEXC_API_KEY}
    params["signature"] = signature
    resp = requests.get(endpoint, headers=headers, params=params)
    balances = resp.json().get("balances", [])
    for b in balances:
        if b["asset"] in ["SUI", "USDT"]:
            point = Point("wallet_balance").tag("asset", b["asset"]).field("free", float(b["free"]))
            write_api.write(bucket=INFLUX_BUCKET, record=point)
            logging.info(f"💰 Balance {b['asset']}: {b['free']}")

async def stream_trades():
    url = "wss://wbs.mexc.com/ws"
    async with websockets.connect(url) as ws:
        sub_msg = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.deals.v3.api@{MEXC_SYMBOL}"],
            "id": 1
        }
        await ws.send(json.dumps(sub_msg))
        logging.info(f"✅ Subscribed to {MEXC_SYMBOL}")

        async def ping_loop():
            while True:
                try:
                    ping_msg = {"method": "PING"}
                    await ws.send(json.dumps(ping_msg))
                    logging.info("⏱️  Sent PING")
                    await asyncio.sleep(20)
                except Exception as e:
                    logging.warning(f"❌ Ping failed: {e}")
                    break

        asyncio.create_task(ping_loop())

        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                if "data" in data and isinstance(data["data"], list):
                    for d in data["data"]:
                        price = float(d["p"])
                        qty = float(d["v"])
                        side = "sell" if d["S"].lower() == "buy" else "buy"  # Fixat!

                        point = Point("mexc_trade") \
                            .tag("symbol", MEXC_SYMBOL) \
                            .tag("side", side) \
                            .field("price", price) \
                            .field("volume", qty)

                        write_api.write(bucket=INFLUX_BUCKET, record=point)
                        logging.info(f"📈 {side.upper()} {qty} @ {price}")
            except Exception as e:
                logging.error(f"🔌 WebSocket error: {e}")
                break

if __name__ == "__main__":
    try:
        logging.info(f"🚀 Polling MEXC myTrades for {MEXC_SYMBOL}...")
        trades = get_my_trades()
        for t in trades:
            logging.info(f"🧾 Trade: {t}")
        get_wallet_balances()
        asyncio.run(stream_trades())
    except KeyboardInterrupt:
        logging.info("🛑 Stoppat av användaren")
