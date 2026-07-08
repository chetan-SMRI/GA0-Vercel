from fastapi import FastAPI, Request, Header, Query
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import time
import uuid
import base64

app = FastAPI()

TOTAL_ORDERS = 42
RATE_LIMIT = 20
WINDOW = 10

idempotency_store = {}
requests_store = defaultdict(deque)

ALLOWED_ORIGIN = "https://exam.sanand.workers.dev"


def cors_headers():
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Idempotency-Key, X-Client-Id, X-Request-ID",
        "Access-Control-Expose-Headers": "Retry-After, X-Request-ID",
        "Access-Control-Max-Age": "86400",
    }


@app.middleware("http")
async def middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Browser CORS preflight
    if request.method == "OPTIONS":
        return JSONResponse(
            status_code=200,
            content={},
            headers={
                **cors_headers(),
                "X-Request-ID": request_id,
            },
        )

    client_id = request.headers.get("X-Client-Id", "anonymous")
    now = time.time()
    bucket = requests_store[client_id]

    while bucket and bucket[0] <= now - WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:
        retry_after = max(1, int(WINDOW - (now - bucket[0])))

        return JSONResponse(
            status_code=429,
            content={"error": "rate limit exceeded"},
            headers={
                **cors_headers(),
                "Retry-After": str(retry_after),
                "X-Request-ID": request_id,
            },
        )

    bucket.append(now)

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    for k, v in cors_headers().items():
        response.headers[k] = v

    return response


def encode_cursor(n: int) -> str:
    return base64.urlsafe_b64encode(str(n).encode()).decode()


def decode_cursor(cursor):
    if not cursor:
        return 1

    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 1


@app.get("/")
def home():
    return {"ok": True}


@app.post("/orders")
def create_order(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={"error": "Idempotency-Key header required"},
            headers=cors_headers(),
        )

    if idempotency_key in idempotency_store:
        return JSONResponse(
            status_code=201,
            content=idempotency_store[idempotency_key],
            headers=cors_headers(),
        )

    order = {
        "id": str(uuid.uuid4()),
        "status": "created",
    }

    idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order,
        headers=cors_headers(),
    )


@app.get("/orders")
def get_orders(
    limit: int = Query(default=10),
    cursor: str | None = Query(default=None),
):
    limit = max(1, min(limit, 100))

    start = decode_cursor(cursor)

    if start < 1:
        start = 1

    if start > TOTAL_ORDERS:
        return {
            "items": [],
            "next_cursor": None,
        }

    end = min(start + limit, TOTAL_ORDERS + 1)

    items = [
        {
            "id": i,
            "name": f"Order {i}",
        }
        for i in range(start, end)
    ]

    next_cursor = encode_cursor(end) if end <= TOTAL_ORDERS else None

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
