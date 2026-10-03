import uuid,shutil
from pathlib import Path
import jwt
from fastapi import FastAPI,UploadFile,File,Depends,Header,HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel,EmailStr,Field
from .config import settings
from .db import init_db,one,all_,exe,jd,jl,now
from .security import hash_password,verify_password,create_token,decode,hash_token
from .ingest import extract
from .search import search
app=FastAPI(title="DeepSearch API",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
Path(settings.upload_dir).mkdir(parents=True,exist_ok=True)
@app.on_event("startup")
def startup():init_db()
class Register(BaseModel):full_name:str=Field(min_length=2);email:EmailStr;password:str=Field(min_length=8)
class Login(BaseModel):email:EmailStr;password:str
class Query(BaseModel):query:str;limit:int=20
async def user(authorization:str|None=Header(default=None)):
 if not authorization:raise HTTPException(401,"Authentication required")
 try:p=decode(authorization.split(" ",1)[1],"access")
 except jwt.PyJWTError:raise HTTPException(401,"Invalid token")
 u=one("SELECT * FROM users WHERE id=?",(p["sub"],))
 if not u:raise HTTPException(401,"User not found")
 return u
@app.get("/api/health")
def health():return {"status":"ok","service":"deepsearch"}
@app.post("/api/auth/register")
def register(b:Register):
 e=b.email.lower();
 if one("SELECT id FROM users WHERE email=?",(e,)):raise HTTPException(409,"Account exists")
 uid=str(uuid.uuid4());exe("INSERT INTO users VALUES(?,?,?,?,?,?)",(uid,e,b.full_name,hash_password(b.password),0,now()));return {"message":"Account created. Development verification can be completed from the admin seed flow."}
@app.post("/api/auth/login")
def login(b:Login):
 u=one("SELECT * FROM users WHERE email=?",(b.email.lower(),))
 if not u or not verify_password(b.password,u["password_hash"]):raise HTTPException(401,"Invalid credentials")
 access,_,_=create_token(u["id"],"access",__import__('datetime').timedelta(minutes=settings.access_minutes));return {"access_token":access,"user":{"id":u["id"],"email":u["email"],"full_name":u["full_name"]}}
@app.get("/api/auth/me")
def me(u=Depends(user)):return {"user":{"id":u["id"],"email":u["email"],"full_name":u["full_name"]}}
@app.post("/api/files/upload")
async def upload(file:UploadFile=File(...),u=Depends(user)):
 ext=Path(file.filename or "").suffix.lower();allowed={".pdf",".docx",".xlsx",".xls",".csv",".jpg",".jpeg",".png",".txt",".md"}
 if ext not in allowed:raise HTTPException(400,"Unsupported file type")
 fid=str(uuid.uuid4());dest=Path(settings.upload_dir)/f"{fid}{ext}";dest.write_bytes(await file.read());text,refs,ocr,pages=extract(dest)
 chunks=[x.strip() for x in text.split("\n\n") if x.strip()] or [text[:4000]]
 for i,c in enumerate(chunks):exe("INSERT INTO chunks VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),fid,u["id"],c,refs[min(i,len(refs)-1)] if refs else "document",jd({"index":i}),None))
 exe("INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?)",(fid,u["id"],file.filename,file.content_type or "application/octet-stream",str(dest),"indexed",int(ocr),pages,len(chunks),now()))
 return {"file_id":fid,"name":file.filename,"status":"indexed","chunks":len(chunks)}
@app.get("/api/files")
def files(u=Depends(user)):return {"files":all_("SELECT id,name,mime_type,status,ocr_used,page_count,chunk_count,created_at FROM files WHERE user_id=? ORDER BY created_at DESC",(u["id"],))}
@app.post("/api/search")
def do_search(b:Query,u=Depends(user)):return {"query":b.query,"results":search(u["id"],b.query,min(b.limit,50))}
