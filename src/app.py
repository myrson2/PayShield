from fastapi import FastAPI
from src.payshield import create_tables

app = FastAPI(root_path='/api/v1')

create_tables()
