import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR=Path(__file__).resolve().parents[1]
@dataclass(frozen=True)
class Settings:
    frontend_origin:str=os.getenv("FRONTEND_ORIGIN","http://localhost:5173")
    jwt_secret:str=os.getenv("JWT_SECRET","CHANGE-ME")
    access_minutes:int=int(os.getenv("ACCESS_TOKEN_MINUTES","15"))
    refresh_days:int=int(os.getenv("REFRESH_TOKEN_DAYS","7"))
    database_url:str=os.getenv("DATABASE_URL","sqlite:///./deepsearch.db")
    upload_dir:str=os.getenv("UPLOAD_DIR",str(BASE_DIR/"uploads"))
    openai_api_key:str=os.getenv("OPENAI_API_KEY","")
    openai_model:str=os.getenv("OPENAI_MODEL","gpt-4.1-mini")
    debug:bool=os.getenv("DEBUG","true").lower()=="true"
settings=Settings()
