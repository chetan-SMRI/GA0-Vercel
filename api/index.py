from fastapi import FastAPI, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import uuid
import time
import base64

app = FastAPI()

TOTAL_ORDERS = 42
RATE_LIMIT = 20
WINDOW = 10

EMAIL = "24f2008500@ds.study.iitm.ac.in"

rate_buckets = defaultdict(deque)
idempotency_store = {}


@app.middleware("http")
async def middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Do not rate-limit browser preflight CORS requests
    if request.method != "OPTIONS":
        client_id = request.headers.get("X-Client-Id", "anonymous")
        now = time.time()
        bucket = rate_buckets[client_id]

        while bucket and bucket[0] <= now - WINDOW:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = int(WINDOW - (now - bucket[0])) + 1

            return JSONResponse(
                status_code=429,
                content={
                    "email": EMAIL,
                    "request_id": request_id,
                    "detail": "Rate limit exceeded",
                },
                headers={
                    "X-Request-ID": request_id,
                    "Retry-After": str(retry_after),
                },
            )

        bucket.append(now)

    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/ping")
async def ping(request: Request):
    return {
        "email": EMAIL,
        "request_id": request.state.request_id,
    }


@app.post("/orders", status_code=201)
async def create_order(
    request: Request,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={
                "email": EMAIL,
                "request_id": request.state.request_id,
                "detail": "Idempotency-Key header is required",
            },
        )

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "email": EMAIL,
        "status": "created",
    }

    idempotency_store[idempotency_key] = order
    return order


@app.get("/orders")
async def get_orders(
    request: Request,
    limit: int = Query(10, ge=1),
    cursor: str | None = None,
):
    if cursor:
        try:
            start = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        except Exception:
            return JSONResponse(
                status_code=400,
                content={
                    "email": EMAIL,
                    "request_id": request.state.request_id,
                    "detail": "Invalid cursor",
                },
            )
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
        "email": EMAIL,
        "request_id": request.state.request_id,
        "items": items,
        "next_cursor": next_cursor,
    }


# Keep CORS middleware LAST so it wraps even 429 responses
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
        "Idempotency-Key",
        "Content-Type",
    ],
    expose_headers=[
        "X-Request-ID",
        "Retry-After",
    ],
)
