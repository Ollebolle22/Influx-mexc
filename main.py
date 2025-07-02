import os
import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from influxdb_client import InfluxDBClient, Point, WriteOptions

MEXC_API_KEY = os.getenv("MEXC_API_KEY")
MEXC_SECRET_KEY = os.getenv("MEXC_SECRET_KEY")
SYMBOL = os.getenv("MEXC_SYMBOL", "SUIUSDT").upper()

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=1))

BASE_URL = "https://api.mexc.com"
SEEN_IDS = set()

def sign(params, secret):
    query = urlencode(params)
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

def get_my_trades():
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": SYMBOL,
        "timestamp": timestamp,
        "recvWindow": 5000
    }
    signature = sign(params, MEXC_SECRET_KEY)
    params["signature"] = signature

    headers = {
        "X-MEXC-APIKEY": MEXC_API_KEY
    }

    try:
        r = requests.get(f"{BASE_URL}/api/v3/myTrades", headers=headers, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ API error: {e}")
        return []

def log_trade(trade):
    if trade["id"] in SEEN_IDS:
        return
    SEEN_IDS.add(trade["id"])

    price = float(trade["price"])
    qty = float(trade["qty"])
    side = "buy" if not trade["isBuyer"] else "sell"
    ts = int(trade["time"]) * 1_000_000  # ns

    point = (
        Point("my_trade")
        .tag("symbol", SYMBOL)
        .tag("side", side)
        .field("price", price)
        .field("volume", qty)
        .time(ts)
    )
    write_api.write(bucket=INFLUX_BUCKET, record=point)
    write_api.flush()
    print(f"✅ WROTE: {SYMBOL} {side.upper()} {price} × {qty}")

try:
    print(f"🚀 Polling MEXC myTrades for {SYMBOL}...")
    while True:
        trades = get_my_trades()
        for t in trades:
            log_trade(t)
        time.sleep(15)
finally:
    print("🛑 Closing...")
    write_api.close()
    client.close()
