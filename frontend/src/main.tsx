import React,{useEffect,useState}from"react";
import{createRoot}from"react-dom/client";
import{Canvas}from"@react-three/fiber";
import{OrbitControls,Float,Stars}from"@react-three/drei";
import{Search,Upload,LogOut,FileText,Image as ImageIcon,Sheet,ShieldCheck,Database,Sparkles,LockKeyhole}from"lucide-react";
import"./styles.css";
import{api}from"./api";

function Scene(){return <Canvas camera={{position:[0,0,10],fov:50}}><Stars radius={80} depth={40} count={1500} factor={3} fade/><ambientLight intensity={1.2}/><pointLight position={[5,5,8]} intensity={20}/><Float speed={1} rotationIntensity={1} floatIntensity={1}><mesh><icosahedronGeometry args={[2.5,1]}/><meshStandardMaterial color="#6d8cff" metalness={.8} roughness={.18} wireframe/></mesh></Float><OrbitControls enableZoom={false} autoRotate autoRotateSpeed={.35}/></Canvas>}

function App(){
 const[token,setToken]=useState(sessionStorage.getItem("deep_token")||"");
 const[user,setUser]=useState<any>(null);
 const[mode,setMode]=useState<"login"|"signup">("login");
 const[email,setEmail]=useState("");const[pw,setPw]=useState("");const[name,setName]=useState("");
 const[q,setQ]=useState("");const[results,setResults]=useState<any[]>([]);const[files,setFiles]=useState<any[]>([]);
 const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);const[answer,setAnswer]=useState<any>(null);const[answerLoading,setAnswerLoading]=useState(false);
 const logged=!!token;
 const load=async()=>{try{const me=await api.me();setUser(me.user);const f=await api.files();setFiles(f.files)}catch{setToken("");sessionStorage.removeItem("deep_token")}};
 useEffect(()=>{if(token)load()},[token]);
 async function auth(e:any){e.preventDefault();setMsg("");try{const d=mode==="login"?await api.login({email,password:pw}):await api.register({full_name:name,email,password:pw});if(d.access_token){sessionStorage.setItem("deep_token",d.access_token);setToken(d.access_token)}else setMsg(d.message||"Account created")}catch(x:any){setMsg(x.message)}}
 async function search(){
  if(!q.trim())return;
  setLoading(true);setAnswer(null);setMsg("");
  try{
    const d=await api.search(q);
    setResults(d.results||[]);
  }catch(e:any){
    setMsg(`Search failed: ${e.message}`);
    setResults([]);
  }finally{
    setLoading(false);
  }
}
 async function explain(){
  if(!q.trim())return;
  setAnswerLoading(true);setAnswer(null);
  try{
    const d=await api.answer(q);
    setAnswer(d.answer||null);
    if(!d.answer)setMsg("AI returned no grounded answer.");
  }catch(e:any){
    setMsg(`AI explanation failed: ${e.message}`);
  }finally{
    setAnswerLoading(false);
  }
}
 async function upload(e:any){const f=e.target.files?.[0];if(!f)return;setMsg("Indexing "+f.name+"…");try{await api.upload(f);setMsg("Indexed "+f.name);await load()}catch(x:any){setMsg(x.message)}}
 if(!logged)return <div className="landing"><div className="hero3d"><Scene/><div className="overlay"><div className="brand">DEEP<span>SEARCH</span></div><h1>Search everything.<br/><em>Understand anything.</em></h1><p>Deep semantic search across PDFs, Word, Excel, CSV and images—with OCR, ranking, evidence previews and guarded AI explanations.</p></div></div><div className="authCard"><div className="tabs"><button className={mode==="login"?"active":""} onClick={()=>setMode("login")}>Sign in</button><button className={mode==="signup"?"active":""} onClick={()=>setMode("signup")}>Create account</button></div><form onSubmit={auth}>{mode==="signup"&&<input placeholder="Full name" value={name} onChange={e=>setName(e.target.value)} required/>}<input type="email" placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} required/><input type="password" placeholder="Password" value={pw} onChange={e=>setPw(e.target.value)} required minLength={8}/><button className="primary">{mode==="login"?"Enter DeepSearch":"Create workspace"}</button></form>{msg&&<div className="msg">{msg}</div>}</div></div>;
 return <div className="app"><aside><div className="brand">DEEP<span>SEARCH</span></div><div className="sideStat"><Sparkles/><b>AI File Intelligence</b><small>OCR · Semantic · Ranked</small></div><div className="guardBadge"><LockKeyhole size={15}/><span>AI Guardrails Active</span></div><div className="guardList"><span>✓ Prompt-injection defense</span><span>✓ Grounded citations</span><span>✓ Secret redaction</span><span>✓ Upload limits</span><span>✓ Rate limits</span></div><button className="ghost" onClick={()=>{sessionStorage.removeItem("deep_token");setToken("")}}><LogOut size={16}/> Logout</button></aside>
 <main><div className="top"><div><div className="eyebrow">LOCAL CORPUS · PRIVATE WORKSPACE</div><h2>Good to see you, {user?.full_name||"there"}.</h2><p>Search your files like you search the web—except every AI explanation is constrained to retrieved evidence.</p></div><label className="upload"><Upload size={17}/> Upload<input type="file" hidden accept=".pdf,.docx,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.txt,.md" onChange={upload}/></label></div>
 <div className="searchbar"><Search/><input value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>e.key==="Enter"&&search()} placeholder='Try “customer payment delays” or “invoice above one lakh”'/><button className="primary" onClick={search}>{loading?"Searching…":"Deep Search"}</button></div>
 {msg&&<div className="msg">{msg}</div>}
 <section className="metrics"><div><Database/><b>{files.length}</b><span>indexed files</span></div><div><ShieldCheck/><b>5</b><span>guardrails</span></div><div><Sparkles/><b>{results.length}</b><span>current matches</span></div></section>
 <section><div className="sectionTitle"><h3>Indexed corpus</h3><small>{files.length} files</small></div><div className="files">{files.map(f=><div className="file" key={f.id}>{f.mime_type.includes("image")?<ImageIcon/>:f.mime_type.includes("sheet")?<Sheet/>:<FileText/>}<div><b>{f.name}</b><small>{f.status} · {f.chunk_count} chunks {f.ocr_used?"· OCR":""}</small></div></div>)}</div></section>
 <section><div className="sectionTitle"><h3>Ranked evidence</h3><div className="rowBtns"><small>{q||"Run a search"}</small>{q&&<button className="evidence aiBtn" onClick={explain}>{answerLoading?"Explaining…":"Explain with guarded AI"}</button>}</div></div><div className="results">{results.map(r=><div className="result" key={r.chunk_id}><div className="score">{Math.round(r.score*100)}%</div><div><b>{r.file_name}</b><small>{r.source_ref}</small><p>{r.content}</p><button className="evidence">View evidence</button></div></div>)}</div></section>
 {answer&&<section className="aiAnswer"><div className="sectionTitle"><h3>Guarded AI explanation</h3><span className="confidence">{Math.round(answer.confidence)}% confidence</span></div><p>{answer.answer}</p><div className="citationRow">{answer.citations?.map((c:any,i:number)=><span className="citation" key={i}>{c.file_name} · {c.source_ref}</span>)}</div><div className="guardTrace">{(answer.guardrails||[]).map((g:string)=><span key={g}>✓ {g.replaceAll("_"," ")}</span>)}</div></section>}
 </main></div>
}
createRoot(document.getElementById("root")!).render(<App/>);
