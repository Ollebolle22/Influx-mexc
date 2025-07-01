import asyncio
import websockets
import json
import os
from influxdb_client import InfluxDBClient, Point, WriteOptions

MEXC_SYMBOL = os.getenv("MEXC_SYMBOL", "BTC_USDT")
WS_URL = "wss://stream.mexc.com/spot/ws"
INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=1, flush_interval=1000))

async def stream_trades():
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20) as ws:
                sub_msg = {
                    "method": "SUBSCRIBE",
                    "params": [f"{MEXC_SYMBOL.lower()}@trade"],
                    "id": 1
                }
                await ws.send(json.dumps(sub_msg))

                print(f"🔌 Subscribed to {MEXC_SYMBOL.lower()}@trade")

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    if "p" in data:
                        ts = int(data["T"]) * 1_000_000
                        price = float(data["p"])
                        volume = float(data["q"])
                        is_buy = data["m"] is False  # market maker = sell

                        point = (
                            Point("mexc_trade")
                            .tag("symbol", MEXC_SYMBOL)
                            .tag("side", "buy" if is_buy else "sell")
                            .field("price", price)
                            .field("volume", volume)
                            .time(ts)
                        )
                        write_api.write(bucket=INFLUX_BUCKET, record=point)
                        print(f"[{MEXC_SYMBOL}] {price} {volume} {'BUY' if is_buy else 'SELL'}")

        except Exception as e:
            print(f"❌ WebSocket error: {e}")
            await asyncio.sleep(5)

asyncio.run(stream_trades())
