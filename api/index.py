from fastapi import FastAPI, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import time
import uuid
import base64

app = FastAPI()

# Allow browser grader
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

TOTAL_ORDERS = 42
RATE_LIMIT = 20
WINDOW_SECONDS = 10

# Stores idempotency key -> created order
idempotency_store = {}

# Stores client_id -> timestamps of requests
rate_buckets = defaultdict(deque)


def check_rate_limit(client_id: str):
    now = time.time()
    bucket = rate_buckets[client_id]

    # Remove old requests outside 10 second window
    while bucket and bucket[0] <= now - WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:
        retry_after = int(WINDOW_SECONDS - (now - bucket[0])) + 1
        return False, retry_after

    bucket.append(now)
    return True, None


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id", "anonymous")

    allowed, retry_after = check_rate_limit(client_id)

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)


@app.post("/orders", status_code=201)
async def create_order(idempotency_key: str = Header(None, alias="Idempotency-Key")):
    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={"error": "Idempotency-Key header is required"},
        )

    # If same key comes again, return same order
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "status": "created",
    }

    idempotency_store[idempotency_key] = order
    return order


@app.get("/orders")
async def list_orders(
    limit: int = Query(10, ge=1),
    cursor: str | None = None,
):
    # Cursor means: where to start from
    if cursor:
        start = int(base64.urlsafe_b64decode(cursor.encode()).decode())
    else:
        start = 1

    end = min(start + limit, TOTAL_ORDERS + 1)

    items = [
        {
            "id": i,
            "name": f"Order {i}",
        }
        for i in range(start, end)
    ]

    if end <= TOTAL_ORDERS:
        next_cursor = base64.urlsafe_b64encode(str(end).encode()).decode()
    else:
        next_cursor = None

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
