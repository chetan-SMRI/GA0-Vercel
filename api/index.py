from fastapi import FastAPI, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app-v3s45q.example.com",
        "https://exam.sanand.workers.dev",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "X-Request-ID",
        "X-Client-Id",
        "Content-Type",
        "Idempotency-Key",
    ],
    expose_headers=[
        "X-Request-ID",
        "Retry-After",
    ],
)


@app.middleware("http")
async def middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # IMPORTANT: never rate limit OPTIONS preflight
    if request.method == "OPTIONS":
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

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
                "Retry-After": str(retry_after),
                "X-Request-ID": request_id,
            },
        )

    bucket.append(now)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
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
    return {"ok": True, "message": "Orders API running"}


@app.post("/orders")
def create_order(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={"error": "Idempotency-Key header required"},
        )

    if idempotency_key in idempotency_store:
        return JSONResponse(
            status_code=201,
            content=idempotency_store[idempotency_key],
        )

    order = {
        "id": str(uuid.uuid4()),
        "status": "created",
    }

    idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order,
    )


@app.get("/orders")
def get_orders(
    limit: int = Query(default=10),
    cursor: str | None = Query(default=None),
):
    if limit < 1:
        limit = 1

    limit = min(limit, 100)

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

    next_cursor = None
    if end <= TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
