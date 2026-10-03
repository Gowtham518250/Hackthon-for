// Production API is intentionally fixed here so an old Render VITE_API_BASE_URL cannot route auth requests to a stale service.
export const API="https://deep-search-ai-p8gi.onrender.com";
let token=sessionStorage.getItem("deep_token")||"";

export function setAuthToken(value:string){
  token=value;
  sessionStorage.setItem("deep_token",value);
}

export function clearAuthToken(){
  token="";
  sessionStorage.removeItem("deep_token");
}

async function req(path:string,opt:any={}){
  const h=new Headers(opt.headers||{});
  if(token)h.set("Authorization","Bearer "+token);
  if(opt.body && !(opt.body instanceof FormData))h.set("Content-Type","application/json");
  const r=await fetch(API+path,{...opt,headers:h,credentials:"include"});
  const raw=await r.text();
  let d:any={};
  try{d=raw?JSON.parse(raw):{}}catch{d={detail:raw}}
  if(!r.ok)throw new Error(d.detail||d.message||("Request failed (HTTP "+r.status+")"));
  return d;
}

export const api={
  login:async(p:any)=>{
    const d=await req("/api/auth/login",{method:"POST",body:JSON.stringify(p)});
    setAuthToken(d.access_token);
    return d;
  },
  register:async(p:any)=>{const d=await req("/api/auth/register",{method:"POST",body:JSON.stringify(p)});if(d.access_token)setAuthToken(d.access_token);return d;},
  verifyRegistration:async(p:any)=>{
    const d=await req("/api/auth/verify-registration",{method:"POST",body:JSON.stringify(p)});
    setAuthToken(d.access_token);
    return d;
  },
  resendRegistrationOtp:(email:string)=>req("/api/auth/resend-registration-otp",{method:"POST",body:JSON.stringify({email})}),
  forgotPassword:(email:string)=>req("/api/auth/forgot-password",{method:"POST",body:JSON.stringify({email})}),
  verifyResetOtp:(p:any)=>req("/api/auth/verify-reset-otp",{method:"POST",body:JSON.stringify(p)}),
  resetPassword:(p:any)=>req("/api/auth/reset-password",{method:"POST",body:JSON.stringify(p)}),
  me:()=>req("/api/auth/me"),
  files:()=>req("/api/files"),
  stats:()=>req("/api/corpus/stats"),
  file:(id:string)=>req("/api/files/"+id),
  chunks:(id:string)=>req("/api/files/"+id+"/chunks?limit=50"),
  deleteFile:(id:string)=>req("/api/files/"+id,{method:"DELETE"}),
  reindexFile:(id:string)=>req("/api/files/"+id+"/reindex",{method:"POST"}),
  upload:(f:File)=>{
    const fd=new FormData(); fd.append("file",f);
    return req("/api/files/upload",{method:"POST",body:fd});
  },
  uploadJob:(id:string)=>req("/api/files/upload-jobs/"+id),
  search:(query:string,limit=20)=>req("/api/search",{method:"POST",body:JSON.stringify({query,limit})}),
  deepSearch:(query:string,limit=20)=>req("/api/deep-search",{method:"POST",body:JSON.stringify({query,limit,with_ai:true})}),
  answer:(query:string)=>req("/api/ai/answer",{method:"POST",body:JSON.stringify({query,limit:12})}),
  evaluationBenchmark:()=>req("/api/evaluation/benchmark?limit=6"),
  evaluationSnapshot:(query:string,limit=5)=>req("/api/evaluation/snapshot",{method:"POST",body:JSON.stringify({query,limit})}),
  evaluationCompare:(before:any,query:string,limit=5)=>req("/api/evaluation/compare",{method:"POST",body:JSON.stringify({before,query,limit})}),
  history:()=>req("/api/history?limit=100"),
  deleteHistory:(id:string)=>req("/api/history/"+id,{method:"DELETE"})
};