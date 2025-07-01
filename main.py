import asyncio
import websockets
import json
import os
from influxdb_client import InfluxDBClient, Point, WriteOptions

MEXC_SYMBOL = os.getenv("MEXC_SYMBOL", "USDT_SUI")
WS_URL = "wss://wbs.mexc.com/ws"
INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=1, flush_interval=1000))

async def send_ping(ws):
    while True:
        await asyncio.sleep(20)
        try:
            await ws.send("PING")
            print("⏱️  Sent PING")
        except Exception as e:
            print(f"❌ Ping failed: {e}")
            break

async def stream_trades():
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                sub_msg = {
                    "method": "SUBSCRIPTION",
                    "params": [
                        f"spot@public.aggre.deals.v3.api.pb@100ms@{MEXC_SYMBOL}"
                    ],
                    "id": 1
                }
                await ws.send(json.dumps(sub_msg))
                print(f"✅ Subscribed to {MEXC_SYMBOL}")

                # Start ping-loop i bakgrunden
                ping_task = asyncio.create_task(send_ping(ws))

                while True:
                    msg = await ws.recv()
                    if msg == "PONG":
                        print("🏓 Received PONG")
                        continue

                    # Här borde du avkoda protobuf – men vi antar JSON för nu
                    try:
                        data = json.loads(msg)
                        print(f"🔔 Received data: {data}")  # placeholder
                        # ... skriv till Influx om du tolkar datan korrekt ...
                    except:
                        print("⚠️  Unknown message format")
        except Exception as e:
            print(f"❌ WebSocket error: {e}")
            await asyncio.sleep(5)

asyncio.run(stream_trades())
