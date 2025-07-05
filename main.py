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
MEXC_API_KEY    = os.getenv("MEXC_API_KEY")
MEXC_SECRET_KEY = os.getenv("MEXC_SECRET_KEY")
MEXC_SYMBOL     = os.getenv("MEXC_SYMBOL", "SUIUSDT")

INFLUX_URL   = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG   = os.getenv("INFLUX_ORG")
INFLUX_BUCKET= os.getenv("INFLUX_BUCKET")

# Polling‐intervaller (sekunder)
TRADE_INTERVAL  = 20
CANDLE_INTERVAL = 300  # 5 minuter

# Influx-klient
client    = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=1))

def sign(params: dict, secret: str) -> str:
    qs = urlencode(params)
    return hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()

def get_my_trades():
    url = "https://api.mexc.com/api/v3/myTrades"
    ts  = int(time.time() * 1000)
    params = {"symbol": MEXC_SYMBOL, "timestamp": ts, "recvWindow": 5000, "limit": 100}
    params["signature"] = sign(params, MEXC_SECRET_KEY)
    headers = {"X-MEXC-APIKEY": MEXC_API_KEY}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json()

def get_balances():
    url = "https://api.mexc.com/api/v3/account"
    ts  = int(time.time() * 1000)
    params = {"timestamp": ts, "recvWindow": 5000}
    params["signature"] = sign(params, MEXC_SECRET_KEY)
    headers = {"X-MEXC-APIKEY": MEXC_API_KEY}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json()

def get_candles(symbol: str, interval: str="1m", limit: int=200):
    url = "https://api.mexc.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()

def write_candles(symbol: str, interval: str="1m", limit: int=200):
    candles = get_candles(symbol, interval, limit)
    for c in candles:
        ts = datetime.utcfromtimestamp(c[0] / 1000)
        point = (
            Point("mexc_candle")
            .tag("symbol", symbol)
            .tag("interval", interval)
            .field("open",  float(c[1]))
            .field("high",  float(c[2]))
            .field("low",   float(c[3]))
            .field("close", float(c[4]))
            .field("volume",float(c[5]))
            .time(ts)
        )
        write_api.write(bucket=INFLUX_BUCKET, record=point)

if __name__ == "__main__":
    last_candle_time = 0

    logging.info("🚀 Startar MEXC → InfluxDB loop")
    try:
        while True:
            now = time.time()

            # 1️⃣ Candles var 5:e minut
            if now - last_candle_time >= CANDLE_INTERVAL:
                try:
                    logging.info("📊 Hämtar candles…")
                    write_candles(MEXC_SYMBOL, "1m", 200)
                    write_api.flush()
                    logging.info("✅ Candles inskrivna")
                except Exception as e:
                    logging.error(f"❌ Candle‐fel: {e}")
                last_candle_time = now

            # 2️⃣ Trades var 20:e sekund
            try:
                logging.info(f"📡 Hämtar trades för {MEXC_SYMBOL}…")
                trades = get_my_trades()
                if isinstance(trades, list):
                    for t in sorted(trades, key=lambda x: int(x["time"])):
                        side   = "buy" if t.get("isBuyer", False) else "sell"
                        price  = float(t["price"])
                        qty    = float(t["qty"])
                        q_qty  = float(t.get("quoteQty", 0))
                        comm   = float(t.get("commission", 0))
                        c_asset= str(t.get("commissionAsset", ""))
                        trade_id = int(t.get("id", 0))
                        order_id = int(t.get("orderId", 0))
                        trade_ts = int(t.get("time", 0))

                        pt = (
                            Point("mexc_trade")
                            .tag("symbol", MEXC_SYMBOL)
                            .tag("side", side)
                            .field("price", price)
                            .field("volume", qty)
                            .field("tradeId", trade_id)
                            .field("orderId", order_id)
                            .field("quoteQty", q_qty)
                            .field("commission", comm)
                            .field("commissionAsset", c_asset)
                            .field("time", trade_ts)
                            .time(datetime.fromtimestamp(trade_ts/1000))
                        )
                        write_api.write(bucket=INFLUX_BUCKET, record=pt)
                        icon = "📈" if side=="buy" else "📉"
                        logging.info(
                            f"{icon} {side.upper()} {price} × {qty} "
                            f"id={trade_id} order={order_id} q={q_qty} "
                            f"comm={comm}{c_asset} time={trade_ts}"
                        )
                else:
                    logging.warning(f"❌ Kunde inte tolka trades: {trades}")
            except Exception as e:
                logging.error(f"💥 Trade‐fel: {e}")

            # 3️⃣ Balans var 20:e sekund
            try:
                balances = get_balances()
                if "balances" in balances:
                    for b in balances["balances"]:
                        if b["asset"] in ["SUI", "USDT"]:
                            free   = float(b.get("free",0))
                            locked = float(b.get("locked",0))
                            bal    = free + locked
                            pt = (
                                Point("mexc_balance")
                                .tag("asset", b["asset"])
                                .field("free",   free)
                                .field("locked", locked)
                                .time(datetime.utcnow())
                            )
                            write_api.write(bucket=INFLUX_BUCKET, record=pt)
                            logging.info(f"💰 Balans {b['asset']}: {bal}")
                else:
                    logging.warning(f"❌ Kunde inte tolka saldo: {balances}")
            except Exception as e:
                logging.error(f"💥 Balans‐fel: {e}")

            # 4️⃣ Vänta
            time.sleep(TRADE_INTERVAL)

    except KeyboardInterrupt:
        logging.info("🛑 Avslutar på användarens kommando")
    finally:
        write_api.close()
        client.close()
