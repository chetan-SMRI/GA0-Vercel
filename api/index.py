from fastapi import FastAPI, Request, Header, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import time
import uuid
import base64
from collections import defaultdict, deque

app = FastAPI()

# Assigned values
TOTAL_ORDERS = 42
RATE_LIMIT = 20
WINDOW_SECONDS = 10

# In-memory storage
idempotency_store = {}
client_requests = defaultdict(deque)

ALLOWED_ORIGINS = [
    "https://exam.sanand.workers.dev",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Idempotency-Key",
        "X-Client-Id",
        "X-Request-ID",
    ],
    expose_headers=[
        "Retry-After",
        "X-Request-ID",
    ],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Always allow CORS preflight
    if request.method == "OPTIONS":
        return JSONResponse(status_code=200, content={})

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    client_id = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()
    bucket = client_requests[client_id]

    # Remove old requests outside 10 second window
    while bucket and bucket[0] <= now - WINDOW_SECONDS:
        bucket.popleft()

    # If already reached limit, block request
    if len(bucket) >= RATE_LIMIT:
        retry_after = max(1, int(WINDOW_SECONDS - (now - bucket[0])))

        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-Request-ID": request_id,
                "Access-Control-Allow-Origin": "https://exam.sanand.workers.dev",
                "Access-Control-Allow-Headers": "Content-Type, Idempotency-Key, X-Client-Id, X-Request-ID",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Expose-Headers": "Retry-After, X-Request-ID",
            },
        )

    bucket.append(now)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def encode_cursor(position: int) -> str:
    raw = str(position).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 1

    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        position = int(raw)
        if position < 1:
            return 1
        if position > TOTAL_ORDERS + 1:
            return TOTAL_ORDERS + 1
        return position
    except Exception:
        return 1


@app.get("/")
def root():
    return {
        "message": "Orders API is running",
        "endpoints": ["/orders"],
    }


@app.post("/orders", status_code=201)
async def create_order(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={"error": "Idempotency-Key header is required"},
        )

    # Repeat request: return same order
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    # First request: create new order
    order_id = str(uuid.uuid4())

    order = {
        "id": order_id,
        "status": "created",
        "message": "Order created successfully",
    }

    idempotency_store[idempotency_key] = order
    return order


@app.get("/orders")
async def list_orders(
    limit: int = Query(default=10, ge=1),
    cursor: str | None = Query(default=None),
):
    # Never allow huge pages
    limit = min(limit, 100)

    start = decode_cursor(cursor)
    end = min(start + limit, TOTAL_ORDERS + 1)

    items = [
        {
            "id": order_id,
            "name": f"Order {order_id}",
        }
        for order_id in range(start, end)
    ]

    next_cursor = None
    if end <= TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
