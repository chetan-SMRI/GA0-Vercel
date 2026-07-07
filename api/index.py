from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
import time
from collections import defaultdict, deque

app = FastAPI()

RATE_LIMIT = 15
WINDOW = 10
requests = defaultdict(deque)

EMAIL = "24f2008500@ds.study.iitm.ac.in"


@app.middleware("http")
async def middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    if request.method != "OPTIONS":
        client_id = request.headers.get("X-Client-Id", "anonymous")
        now = time.time()
        bucket = requests[client_id]

        while bucket and bucket[0] <= now - WINDOW:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={
                    "email": EMAIL,
                    "request_id": request_id,
                    "detail": "Rate limit exceeded",
                },
                headers={"X-Request-ID": request_id},
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


# Keep CORS middleware LAST so it wraps even 429 responses
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app-v3s45q.example.com",
        "https://exam.sanand.workers.dev",
    ],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
    expose_headers=["X-Request-ID"],
)
