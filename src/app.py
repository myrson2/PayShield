from fastapi import FastAPI
from src.payshield import create_tables
from src.payshield.controller import router as payshield_router

app = FastAPI(root_path='/api/v1')

app.include_router(payshield_router)

create_tables()
