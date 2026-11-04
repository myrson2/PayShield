from fastapi import FastAPI
from src.payshield import create_tables
from src.payshield.routers import payroll_router, auth_router

app = FastAPI(root_path='/api/v1')

app.include_router(payroll_router)
app.include_router(auth_router)

create_tables()
