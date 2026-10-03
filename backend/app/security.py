import base64,hashlib,hmac,os,secrets,jwt
from datetime import datetime,timedelta,timezone
from .config import settings

def hash_password(password:str)->str:
    salt=os.urandom(16); digest=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1)
    return "scrypt$16384$8$1$"+base64.urlsafe_b64encode(salt).decode()+"$"+base64.urlsafe_b64encode(digest).decode()
def verify_password(password:str,encoded:str)->bool:
    try:
        _,n,r,p,salt_b64,digest_b64=encoded.split("$",5); salt=base64.urlsafe_b64decode(salt_b64); expected=base64.urlsafe_b64decode(digest_b64)
        return hmac.compare_digest(hashlib.scrypt(password.encode(),salt=salt,n=int(n),r=int(r),p=int(p)),expected)
    except Exception:return False
def hash_token(token:str)->str:return hashlib.sha256(token.encode()).hexdigest()
def create_token(sub:str,kind:str,delta:timedelta):
    now=datetime.now(timezone.utc); exp=now+delta; jti=secrets.token_urlsafe(24)
    return jwt.encode({"sub":sub,"type":kind,"jti":jti,"iat":int(now.timestamp()),"exp":int(exp.timestamp())},settings.jwt_secret,algorithm="HS256"),jti,exp
def decode(token:str,kind:str):
    p=jwt.decode(token,settings.jwt_secret,algorithms=["HS256"])
    if p.get("type")!=kind:raise jwt.InvalidTokenError("token type")
    return p
