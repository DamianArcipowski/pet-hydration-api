from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, devices, pets, readings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (devices, readings, pets, auth):
    app.include_router(module.router)