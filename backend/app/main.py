from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache import cache
from app.database import create_tables
from app.routers import auth, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await cache.connect()
    yield
    await cache.close()


app = FastAPI(
    title="Config Vault",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(users.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
