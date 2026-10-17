from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jsonschema import ValidationError as SchemaValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import use_stubs
from app.core.fixtures import seed_workspace
from app.routers import core, generate

@asynccontextmanager
async def lifespan(app):
    if use_stubs():
        seed_workspace()
    yield

app = FastAPI(title='Brand Copilot', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173'], allow_methods=['*'], allow_headers=['*'])
app.include_router(core.router)
app.include_router(generate.router)

@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({'error':str(exc.detail)}, status_code=exc.status_code)

@app.exception_handler(KeyError)
async def missing(request: Request, exc: KeyError):
    return JSONResponse({'error':str(exc.args[0])}, status_code=404)

@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
@app.exception_handler(SchemaValidationError)
async def invalid(request: Request, exc):
    return JSONResponse({'error':str(exc)}, status_code=422)

@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    return JSONResponse({'error':'Internal server error'}, status_code=500)
