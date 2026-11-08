from fastapi import FastAPI
from payshield.routers import payroll_router, auth_router

app = FastAPI()

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(payroll_router, prefix="/api/v1/payroll", tags=["Payroll"])
