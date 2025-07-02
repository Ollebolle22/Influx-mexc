import os
import time
import hmac
import hashlib
from urllib.parse import urlencode
import requests
import logging
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WriteOptions

# Logging med tid
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Miljövariabler
MEXC_API_KEY = os.getenv("MEXC_API_KEY")
MEXC_SECRET_KEY = os.getenv("MEXC_SECRET_KEY")
MEXC_SYMBOL = os.getenv("MEXC_SYMBOL", "SUIUSDT")

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

# Influx-klient
influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx.write_api(write_options=WriteOptions(batch_size=1))

# Signeringsfunktion
def sign(params: dict, secret: str) -> str:
    query = urlencode(params)
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

# Hämta trades
def get_my_trades():
    path = "/api/v3/myTrades"
    url = f"https://api.mexc.com{path}"
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": MEXC_SYMBOL,
        "timestamp": timestamp,
        "recvWindow": 5000
    }
    signature = sign(params, MEXC_SECRET_KEY)
    headers = {"X-MEXC-APIKEY": MEXC_API_KEY}
    params["signature"] = signature
    r = requests.get(url, headers=headers, params=params)
    return r.json()

# Hämta saldo
def get_balances():
    path = "/api/v3/account"
    url = f"https://api.mexc.com{path}"
    timestamp = int(time.time() * 1000)
    params = {
        "timestamp": timestamp,
        "recvWindow": 5000
    }
    signature = sign(params, MEXC_SECRET_KEY)
    headers = {"X-MEXC-APIKEY": MEXC_API_KEY}
    params["signature"] = signature
    r = requests.get(url, headers=headers, params=params)
    return r.json()

# Kör loop
while True:
    try:
        logging.info(f"📡 Hämtar trades och saldo för {MEXC_SYMBOL}...")

        # Hämta och skriv trades
        trades = get_my_trades()
        if isinstance(trades, list):
            for trade in trades:
                side = "sell" if trade.get("side") == "BUY" else "buy"
                point = (
                    Point("mexc_trade")
                    .tag("symbol", MEXC_SYMBOL)
                    .tag("side", side)
                    .field("price", float(trade["price"]))
                    .field("qty", float(trade["qty"]))
                    .time(datetime.utcnow())
                )
                write_api.write(bucket=INFLUX_BUCKET, record=point)
                logging.info(f"📈 Trade {side} @ {trade['price']} x {trade['qty']}")
        else:
            logging.warning(f"❌ Kunde inte tolka trades: {trades}")

        # Hämta och skriv saldo
        balances = get_balances()
        if "balances" in balances:
            for b in balances["balances"]:
                if b["asset"] in ["SUI", "USDT"]:
                    bal = float(b["free"]) + float(b["locked"])
                    point = (
                        Point("mexc_balance")
                        .tag("asset", b["asset"])
                        .field("amount", bal)
                        .time(datetime.utcnow())
                    )
                    write_api.write(bucket=INFLUX_BUCKET, record=point)
                    logging.info(f"💰 Balans {b['asset']}: {bal}")
        else:
            logging.warning(f"❌ Kunde inte tolka saldo: {balances}")

    except Exception as e:
        logging.error(f"💥 Fel i loop: {e}")

    time.sleep(20)  # Polla var 20:e sekund
