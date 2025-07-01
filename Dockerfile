FROM python:3.11-slim

WORKDIR /app

COPY main.py .

RUN pip install websockets influxdb-client

CMD ["python", "main.py"]
