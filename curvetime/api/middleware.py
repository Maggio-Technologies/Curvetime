from fastapi import Request, HTTPException
import time

async def log_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    print(f"{request.method} {request.url.path} - {duration:.3f}s")
    return response

async def auth_middleware(request: Request, call_next):
    # JWT验证占位
    return await call_next(request)