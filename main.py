import asyncio
import websockets
import json
import os
from influxdb_client import InfluxDBClient, Point, WriteOptions

MEXC_SYMBOL = os.getenv("MEXC_SYMBOL", "BTC_USDT")
WS_URL = "wss://wbs.mexc.com/ws"
INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=1, flush_interval=1000))

async def stream_trades():
    async with websockets.connect(WS_URL) as ws:
        sub_msg = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.deals.v3.api@{MEXC_SYMBOL}"],
            "id": 1
        }
        await ws.send(json.dumps(sub_msg))

        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if "data" in data:
                for trade in data["data"]:
                    ts = int(trade["t"]) * 1_000_000
                    price = float(trade["p"])
                    volume = float(trade["v"])
                    is_buy = trade["T"] == 1

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

asyncio.run(stream_trades())
