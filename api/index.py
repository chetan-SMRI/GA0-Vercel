from fastapi.middleware.cors import CORSMiddleware
import json
import math
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

DATA_PATH = Path(__file__).resolve().parent.parent / "q-vercel-latency.json"

with open(DATA_PATH, "r") as f:
    data = json.load(f)

@app.get("/")
def home():
    return {"message": "POST to /api"}

@app.options("/api")
async def options_api():
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )

@app.post("/api")
async def analytics(request: Request):
    body = await request.json()

    regions = body["regions"]
    threshold = body["threshold_ms"]

    result = {}

    for region in regions:
        rows = [r for r in data if r["region"] == region]

        latencies = [r["latency_ms"] for r in rows]
        uptimes = [r["uptime_pct"] for r in rows]

        latencies_sorted = sorted(latencies)
        p95_index = math.ceil(0.95 * len(latencies_sorted)) - 1

        result[region] = {
            "avg_latency": sum(latencies) / len(latencies),
            "p95_latency": latencies_sorted[p95_index],
            "avg_uptime": sum(uptimes) / len(uptimes),
            "breaches": sum(1 for x in latencies if x > threshold)
        }

    return JSONResponse(
        content=result,
        headers={
            "Access-Control-Allow-Origin": "*"
        }
    )
