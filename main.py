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

# Hämta candles
def get_candles(symbol: str, interval: str = "1m", limit: int = 200):
    url = "https://api.mexc.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()


def write_candles(symbol: str = MEXC_SYMBOL, interval: str = "1m", limit: int = 200):
    candles = get_candles(symbol, interval, limit)
    for c in candles:
        open_price = float(c[1])
        high_price = float(c[2])
        low_price = float(c[3])
        close_price = float(c[4])
        volume = float(c[5])
        ts = datetime.utcfromtimestamp(c[0] / 1000)
        point = (
            Point("mexc_candle")
            .tag("symbol", symbol)
            .tag("interval", interval)
            .field("open", open_price)
            .field("high", high_price)
            .field("low", low_price)
            .field("close", close_price)
            .field("volume", volume)
            .time(ts)
        )
        write_api.write(bucket=INFLUX_BUCKET, record=point)

# Hämta och skriv senaste candles
try:
    logging.info("📊 Hämtar candles...")
    write_candles(MEXC_SYMBOL, "1m", 200)
    logging.info("✅ Candles inskrivna")
except Exception as e:
    logging.error(f"❌ Kunde inte hämta candles: {e}")

# Kör loop
while True:
    try:
        logging.info(f"📡 Hämtar trades och saldo för {MEXC_SYMBOL}...")

        # Hämta och skriv trades
        trades = get_my_trades()
        if isinstance(trades, list):
            trades_sorted = sorted(trades, key=lambda t: int(t["time"]))
            for trade in trades_sorted:
                if "isBuyer" in trade:
                    side = "buy" if trade.get("isBuyer") else "sell"
                else:
                    side = trade.get("side", "").lower()
                price = float(trade["price"])
                qty = float(trade["qty"])
                total = price * qty
                trade_id = trade.get("tradeId") or trade.get("id")
                order_id = trade.get("orderId")
                quote_qty = float(trade.get("quoteQty", 0))
                commission = float(trade.get("commission", 0))
                commission_asset = trade.get("commissionAsset")
                trade_time = int(trade.get("time", 0))
                point = (
                    Point("mexc_trade")
                    .tag("symbol", MEXC_SYMBOL)
                    .tag("side", side)
                    .field("price", price)
                    .field("qty", qty)
                    .field("total_usd", total)
                    .field("tradeId", trade_id)
                    .field("orderId", order_id)
                    .field("quoteQty", quote_qty)
                    .field("commission", commission)
                    .field("commissionAsset", commission_asset)
                    .field("time", trade_time)
                    .time(datetime.fromtimestamp(int(trade["time"]) / 1000))
                )
                write_api.write(bucket=INFLUX_BUCKET, record=point)
                icon = "📈" if side == "buy" else "📉"
                logging.info(
                    f"{icon} {side.upper()} {trade['price']} x {trade['qty']} = {total} USD"
                )
        else:
            logging.warning(f"❌ Kunde inte tolka trades: {trades}")

        # Hämta och skriv saldo
        balances = get_balances()
        if "balances" in balances:
            for b in balances["balances"]:
                if b["asset"] in ["SUI", "USDT"]:
                    free_amt = float(b.get("free", 0))
                    locked_amt = float(b.get("locked", 0))
                    bal = free_amt + locked_amt
                    point = (
                        Point("mexc_balance")
                        .tag("asset", b["asset"])
                        .field("asset", b["asset"])
                        .field("free", free_amt)
                        .field("locked", locked_amt)
                        .time(datetime.utcnow())
                    )
                    write_api.write(bucket=INFLUX_BUCKET, record=point)
                    logging.info(f"💰 Balans {b['asset']}: {bal}")
        else:
            logging.warning(f"❌ Kunde inte tolka saldo: {balances}")

    except Exception as e:
        logging.error(f"💥 Fel i loop: {e}")

    time.sleep(20)  # Polla var 20:e sekund
