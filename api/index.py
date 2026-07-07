from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import uuid
from collections import defaultdict, deque

app = FastAPI()

YOUR_EMAIL = "director@shrimayanand.com"

ALLOWED_ORIGINS = [
    "https://app-v3s45q.example.com",

    # Put your exam/grader page origin here also.
    # Example:
    # "https://exam.example.com",
]

RATE_LIMIT = 15
WINDOW_SECONDS = 10

client_requests = defaultdict(deque)


@app.middleware("http")
async def request_context_and_rate_limit(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Let CORS preflight pass
    if request.method == "OPTIONS":
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    client_id = request.headers.get("X-Client-Id", "anonymous")
    now = time.time()

    bucket = client_requests[client_id]

    # Remove old requests outside 10 second window
    while bucket and bucket[0] <= now - WINDOW_SECONDS:
        bucket.popleft()

    # If already used 15 requests in 10 seconds, block
    if len(bucket) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    bucket.append(now)

    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
)


@app.get("/ping")
async def ping(request: Request):
    return {
        "email": YOUR_EMAIL,
        "request_id": request.state.request_id,
    }
