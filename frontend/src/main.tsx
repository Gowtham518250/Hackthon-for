
import React,{useEffect,useMemo,useState}from"react";
import{createRoot}from"react-dom/client";
import{Canvas}from"@react-three/fiber";
import{Float,OrbitControls,Stars,Text,Line,Sparkles as ThreeSparkles}from"@react-three/drei";
import{motion,AnimatePresence}from"framer-motion";
import{Search,Upload,LogOut,FileText,Image as ImageIcon,Sheet,ShieldCheck,Database,Sparkles,LockKeyhole,Trash2,X,BrainCircuit,Network,Layers3,ArrowUpRight,Activity,FileSearch,ScanText,ChevronRight,CircleCheck,AlertTriangle,Mail,ArrowRight,RefreshCcw,BookOpen,KeyRound}from"lucide-react";
import"./styles.css";
import{api,clearAuthToken}from"./api";

type FileRecord={id:string;name:string;mime_type:string;status:string;ocr_used:number;page_count:number;chunk_count:number;created_at:string};
type Result={score:number;file_id:string;file_name:string;chunk_id:string;content:string;source_ref:string;metadata:any;retrieval?:string;match_reasons?:string[];signals?:any};
type AIAnswer={answer:string;confidence:number;citations:any[];provider?:string;model?:string;guardrails?:string[]};

function navigate(path:string){window.history.pushState({},'',path);window.dispatchEvent(new PopStateEvent("popstate"))}
function usePath(){const[path,setPath]=useState(window.location.pathname+window.location.search);useEffect(()=>{const f=()=>setPath(window.location.pathname+window.location.search);window.addEventListener("popstate",f);return()=>window.removeEventListener("popstate",f)},[]);return path}
function queryParam(name:string){return new URLSearchParams(window.location.search).get(name)||""}

function OrbitVisual({large=false}:{large?:boolean}){
  return <div className={large?"orbit-visual large":"orbit-visual"}>
    <div className="orbit-core"><div className="core-dot"/><div className="core-ring"/></div>
    <div className="orbit-ring r1"><span/><i/></div>
    <div className="orbit-ring r2"><span/><i/></div>
    <div className="orbit-ring r3"><span/><i/></div>
  </div>
}

function Node({position,label,active,onClick,color}:any){
  return <group position={position}><Float speed={1.4} rotationIntensity={.3} floatIntensity={.65}>
    <mesh onClick={onClick}><icosahedronGeometry args={[active?.34:.24,1]}/><meshStandardMaterial color={color} emissive={color} emissiveIntensity={active?1.7:.6} metalness={.75} roughness={.2}/></mesh>
    <Text position={[0,-.52,0]} fontSize={.14} maxWidth={1.7} anchorX="center" color="#c7d4ff">{label}</Text>
  </Float></group>
}
function CorpusScene({files,results,onSelectFile,landing=false}:{files:FileRecord[];results:Result[];onSelectFile:(id:string)=>void;landing?:boolean}){
  const positions=useMemo(()=>{const n=Math.max(files.length,landing?9:1);return Array.from({length:n},(_,i)=>{const a=i/n*Math.PI*2;const r=landing?3.5+(i%3)*.7:3.1+(i%2)*.7;return[Math.cos(a)*r,Math.sin(a*1.7)*1.7,Math.sin(a)*r*.55]})},[files.length,landing]);
  const active=new Set(results.map(r=>r.file_id));
  return <Canvas camera={{position:[0,.5,10],fov:46}} dpr={[1,1.5]}>
    <ambientLight intensity={.7}/><pointLight position={[4,5,7]} intensity={13} color="#7f8cff"/><pointLight position={[-5,-2,4]} intensity={8} color="#b65dff"/>
    <Stars radius={55} depth={35} count={landing?1200:700} factor={2.2} saturation={0} fade/><ThreeSparkles count={landing?180:90} scale={[14,8,14]} size={1.5} speed={.35} color="#9aa7ff"/>
    <Float speed={.8} rotationIntensity={.15} floatIntensity={.5}><mesh><icosahedronGeometry args={[1.25,2]}/><meshStandardMaterial color="#6f80ff" emissive="#3f4dff" emissiveIntensity={.8} metalness={.8} roughness={.2} wireframe/></mesh></Float>
    {!landing&&positions.slice(0,files.length).map((p,i)=><Node key={files[i].id} position={p} label={files[i].name.slice(0,18)} active={active.has(files[i].id)} onClick={()=>onSelectFile(files[i].id)} color={active.has(files[i].id)?"#ba72ff":"#6c84ff"}/>)}
    {!landing&&positions.slice(0,Math.min(files.length,8)).map((p,i)=>{const n=positions[(i+1)%Math.max(1,Math.min(files.length,8))];return n?<Line key={i} points={[p as any,n as any]} color="#5b6fcf" transparent opacity={.22} lineWidth={1}/>:null})}
    {landing&&positions.map((p,i)=><Node key={i} position={p} label={i%3===0?"PDF":i%3===1?"DATA":"IMAGE"} active={i===2||i===7} onClick={()=>{}} color={i%2===0?"#6e85ff":"#b66cff"}/>)}
    <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={landing?.2:.12}/>
  </Canvas>
}

function Layout({children,user=false}:{children:React.ReactNode;user?:boolean}){
  return <div className={user?"page-shell":"landing-shell"}><div className="noise-layer"/>{children}</div>
}

function AboutPage(){
  return <Layout>
    <div className="about-space"><CorpusScene files={[]} results={[]} onSelectFile={()=>{}} landing/></div>
    <div className="about-stars"/>
    <header className="public-nav">
      <button className="brand-mark link-brand" onClick={()=>navigate("/about")}><span>DEEP</span>SEARCH</button>
      <nav>
        <button onClick={()=>document.getElementById("how-it-works")?.scrollIntoView({behavior:"smooth"})}>How it works</button>
        <button onClick={()=>document.getElementById("capabilities")?.scrollIntoView({behavior:"smooth"})}>Capabilities</button>
        <button onClick={()=>navigate("/login")}>Sign in</button>
        <button onClick={()=>navigate("/register")} className="nav-cta">Create workspace <ArrowUpRight size={14}/></button>
      </nav>
    </header>

    <main className="about-main">
      <section className="about-hero-new">
        <div className="about-kicker">PRIVATE FILE INTELLIGENCE</div>
        <h1>Turn your files into<br/><span>a searchable intelligence layer.</span></h1>
        <p>DeepSearch reads your local corpus, retrieves the most relevant evidence and gives you a grounded answer you can trace back to the exact source.</p>
        <div className="about-actions">
          <button className="gradient-button" onClick={()=>navigate("/register")}>Start searching <ArrowRight size={16}/></button>
          <button className="subtle-button big" onClick={()=>document.getElementById("how-it-works")?.scrollIntoView({behavior:"smooth"})}>See how it works</button>
        </div>

        <div className="hero-orbit-stage">
          <OrbitVisual large/>
          <div className="hero-chip chip-top"><FileText size={14}/><b>PDF</b><span>page-aware</span></div>
          <div className="hero-chip chip-left"><Network size={14}/><b>SEMANTIC</b><span>vector retrieval</span></div>
          <div className="hero-chip chip-right"><ScanText size={14}/><b>OCR</b><span>image extraction</span></div>
          <div className="hero-chip chip-bottom"><ShieldCheck size={14}/><b>GROUNDED AI</b><span>citations enforced</span></div>
        </div>
      </section>

      <section id="capabilities" className="capability-row">
        <div><div className="cap-icon"><ScanText size={16}/></div><b>Ingest everything</b><span>PDF · Word · Excel · CSV · images</span></div>
        <div><div className="cap-icon"><Network size={16}/></div><b>Retrieve precisely</b><span>semantic + lexical + structured evidence</span></div>
        <div><div className="cap-icon"><BrainCircuit size={16}/></div><b>Explain safely</b><span>Groq answers only from retrieved chunks</span></div>
      </section>

      <section id="how-it-works" className="how-section">
        <div className="section-eyebrow">THE DEEPSEARCH LOOP</div>
        <h2>Extract. Retrieve. Explain.</h2>
        <p>Every question follows the same evidence-first path.</p>
        <div className="loop-grid">
          <div><span>01</span><h3>Extract</h3><p>Parse text, tables, pages and OCR content into structured source-aware chunks.</p></div>
          <div><span>02</span><h3>Retrieve</h3><p>Combine semantic vectors with lexical signals and metadata to rank the relevant chunks.</p></div>
          <div><span>03</span><h3>Explain</h3><p>Groq receives only retrieved evidence and returns a cited, guarded answer.</p></div>
        </div>
      </section>
    </main>
  </Layout>
}
function AuthShell({title,subtitle,children}:{title:string;subtitle:string;children:React.ReactNode}){
  return <Layout>
    <div className="auth-space"><CorpusScene files={[]} results={[]} onSelectFile={()=>{}} landing/></div>
    <header className="auth-nav">
      <button className="brand-mark link-brand" onClick={()=>navigate("/about")}><span>DEEP</span>SEARCH</button>
      <button className="back-link" onClick={()=>navigate("/about")}>About DeepSearch</button>
    </header>
    <main className="auth-center-page">
      <section className="auth-card">
        <div className="auth-orb"><OrbitVisual/></div>
        <div className="auth-copy">
          <div className="auth-kicker">PRIVATE WORKSPACE</div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        {children}
      </section>
    </main>
  </Layout>
}
function LoginPage(){
  const[email,setEmail]=useState("");const[password,setPassword]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  async function submit(e:React.FormEvent){e.preventDefault();setLoading(true);setMsg("");try{await api.login({email,password});navigate("/dashboard")}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell title="Welcome back" subtitle="Sign in and return to your private document intelligence workspace."><div className="auth-kicker">SIGN IN</div><h1 className="auth-title">Enter DeepSearch</h1><p className="auth-subtitle">Your corpus stays tied to your account.</p>
    <form className="auth-form" onSubmit={submit}><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" required/></label><label><span className="field-label-row">Password<button type="button" className="inline-link" onClick={()=>navigate("/forgot-password")}>Forgot password?</button></span><input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" required/></label><button className="gradient-button" disabled={loading}>{loading?"Signing in…":"Sign in"}<ArrowRight size={16}/></button></form>{msg&&<div className="alert">{msg}</div>}{footerNav("New here?","Create an account","/register")}</AuthShell>
}
function RegisterPage(){
  const[name,setName]=useState("");const[email,setEmail]=useState("");const[password,setPassword]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  async function submit(e:React.FormEvent){e.preventDefault();setLoading(true);setMsg("");try{await api.register({full_name:name,email,password});navigate("/dashboard")}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell title="Create your workspace" subtitle="Register once and enter your private DeepSearch dashboard immediately."><div className="auth-kicker">CREATE ACCOUNT</div><h1 className="auth-title">Build your corpus</h1><p className="auth-subtitle">Your account is created securely and you are signed in automatically.</p>
    <form className="auth-form" onSubmit={submit}><label>Full name<input value={name} onChange={e=>setName(e.target.value)} placeholder="Your full name" required minLength={2}/></label><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required/></label><label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 8 characters" required minLength={8}/></label><button className="gradient-button" disabled={loading}>{loading?"Creating…":"Create account"}<ArrowRight size={16}/></button></form>{msg&&<div className="alert">{msg}</div>}{footerNav("Already have an account?","Sign in","/login")}</AuthShell>
}
function VerifyEmailPage(){
  const[email,setEmail]=useState(queryParam("email"));const[otp,setOtp]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);const[resend,setResend]=useState(0);
  useEffect(()=>{if(resend<=0)return;const t=setInterval(()=>setResend(x=>Math.max(0,x-1)),1000);return()=>clearInterval(t)},[resend]);
  async function verify(e:React.FormEvent){e.preventDefault();setLoading(true);setMsg("");try{await api.verifyRegistration({email,otp});navigate("/dashboard")}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  async function resendOtp(){if(resend>0)return;setLoading(true);setMsg("");try{await api.resendRegistrationOtp(email);setResend(60);setMsg("A new OTP has been sent.")}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell title="Verify your email" subtitle="One final step before DeepSearch opens your workspace."> <div className="auth-kicker">EMAIL VERIFICATION</div><h1 className="auth-title">Enter your OTP</h1><p className="auth-subtitle">We sent a 6-digit code to <b>{email}</b>.</p><form className="auth-form" onSubmit={verify}><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label><label>6-digit OTP<input inputMode="numeric" value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,"").slice(0,6))} placeholder="000000" maxLength={6} autoComplete="one-time-code" required/></label><button className="gradient-button" disabled={loading}>{loading?"Verifying…":"Verify & open dashboard"}<ArrowRight size={16}/></button></form><button className="otp-resend" onClick={resendOtp} disabled={loading||resend>0}><RefreshCcw size={14}/>{resend>0?"Resend in "+resend+"s":"Resend OTP"}</button>{msg&&<div className="alert">{msg}</div>}</AuthShell>
}
function ForgotPasswordPage(){
  const[email,setEmail]=useState(queryParam("email"));const[step,setStep]=useState<"request"|"verify"|"reset">("request");const[otp,setOtp]=useState("");const[resetToken,setResetToken]=useState("");const[pw,setPw]=useState("");const[confirm,setConfirm]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  async function submit(e:React.FormEvent){e.preventDefault();setLoading(true);setMsg("");try{if(step==="request"){await api.forgotPassword(email);setStep("verify");setMsg("If the account exists, the OTP has been sent.")}else if(step==="verify"){const d=await api.verifyResetOtp({email,otp});setResetToken(d.reset_token);setStep("reset");setMsg("OTP verified. Create a new password.")}else{if(pw!==confirm)throw new Error("Passwords do not match.");await api.resetPassword({reset_token:resetToken,new_password:pw});navigate("/login")}}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell title="Recover your account" subtitle="Use the same 6-digit email OTP pattern used by Retail Mind: secure, expiring and attempt-limited."><div className="auth-kicker">PASSWORD RESET</div><h1 className="auth-title">{step==="request"?"Forgot password":step==="verify"?"Verify reset OTP":"Set new password"}</h1><p className="auth-subtitle">{step==="request"?"We’ll email a 6-digit OTP.":step==="verify"?"The code expires in 10 minutes.":"Your new password must be at least 8 characters."}</p>
    <form className="auth-form" onSubmit={submit}>{step==="request"&&<label>Registered email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label>}{step==="verify"&&<><label>6-digit OTP<input inputMode="numeric" value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,"").slice(0,6))} maxLength={6} autoComplete="one-time-code" required/></label><button type="button" className="otp-resend" onClick={()=>{setStep("request");setMsg("")}}><Mail size={14}/> Request a new OTP</button></>}{step==="reset"&&<><label>New password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} minLength={8} required/></label><label>Confirm password<input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} minLength={8} required/></label></>}<button className="gradient-button" disabled={loading}>{loading?"Working…":step==="request"?"Send OTP":step==="verify"?"Verify OTP":"Reset password"}<ArrowRight size={16}/></button></form>{msg&&<div className="alert">{msg}</div>}{footerNav("Remembered your password?","Back to sign in","/login")}</AuthShell>
}
function footerNav(prefix:string,label:string,path:string){return <p className="switch-text">{prefix} <button className="link-button" onClick={()=>navigate(path)}>{label}</button></p>}

function Dashboard(){
  const[user,setUser]=useState<any>(null);const[files,setFiles]=useState<FileRecord[]>([]);const[results,setResults]=useState<Result[]>([]);const[answer,setAnswer]=useState<AIAnswer|null>(null);const[stats,setStats]=useState<any>({files:0,chunks:0,embedded_chunks:0});const[selectedFile,setSelectedFile]=useState<any>(null);const[selectedChunks,setSelectedChunks]=useState<any[]>([]);const[query,setQuery]=useState("");const[loading,setLoading]=useState(false);const[uploading,setUploading]=useState(false);const[msg,setMsg]=useState("");const[activeView,setActiveView]=useState<"search"|"files">("search");
  const load=async()=>{try{const[m,f,s]=await Promise.all([api.me(),api.files(),api.stats()]);setUser(m.user);setFiles(f.files||[]);setStats(s)}catch{clearAuthToken();navigate("/login")}};useEffect(()=>{load()},[]);
  async function deepSearch(){if(!query.trim())return;setLoading(true);setMsg("");try{const d=await api.deepSearch(query,20);setResults(d.results||[]);setAnswer(d.answer||null)}catch(e:any){setMsg("Deep Search failed: "+e.message)}finally{setLoading(false)}}
  async function upload(e:React.ChangeEvent<HTMLInputElement>){const file=e.target.files?.[0];if(!file)return;setUploading(true);setMsg("Indexing "+file.name+"…");try{const d=await api.upload(file);setMsg(d.name+" indexed · "+d.chunks+" chunks · "+d.embedding_chunks+" semantic vectors");await load()}catch(err:any){setMsg("Indexing failed: "+err.message)}finally{setUploading(false);e.target.value=""}}
  async function openFile(id:string){try{const[d,c]=await Promise.all([api.file(id),api.chunks(id)]);setSelectedFile(d.file);setSelectedChunks(c.chunks||[])}catch(e:any){setMsg(e.message)}}
  async function removeFile(){if(!selectedFile)return;try{await api.deleteFile(selectedFile.id);setSelectedFile(null);await load()}catch(e:any){setMsg(e.message)}}
  return <div className="workspace-shell"><div className="workspace-bg"><CorpusScene files={files} results={results} onSelectFile={openFile}/></div><div className="workspace-vignette"/>
    <aside className="sidebar-glass"><div><div className="brand-mark small"><span>DEEP</span>SEARCH</div><div className="workspace-label">PRIVATE CORPUS</div></div><div className="sidebar-core"><div className="core-orbit"><span/></div><b>AI FILE INTELLIGENCE</b><small>Semantic · lexical · evidence</small></div>
      <nav className="sidebar-nav"><button className={activeView==="search"?"active":""} onClick={()=>setActiveView("search")}><Search size={16}/> Deep Search</button><button className={activeView==="files"?"active":""} onClick={()=>setActiveView("files")}><Layers3 size={16}/> Corpus</button></nav>
      <div className="guard-card"><div className="guard-title"><LockKeyhole size={15}/> AI Guardrails Active</div><span><CircleCheck size={12}/> Prompt-injection defense</span><span><CircleCheck size={12}/> Grounded citations</span><span><CircleCheck size={12}/> Secret redaction</span><span><CircleCheck size={12}/> Upload limits</span></div>
      <div className="sidebar-user"><div className="avatar">{(user?.full_name||"U").slice(0,1).toUpperCase()}</div><div><b>{user?.full_name||"Workspace user"}</b><small>{user?.email}</small></div></div><button className="logout-button" onClick={()=>{clearAuthToken();navigate("/about")}}><LogOut size={16}/> Logout</button></aside>
    <main className="dashboard"><header className="topbar"><div><div className="eyebrow">LOCAL CORPUS · LIVE INTELLIGENCE LAYER</div><h2>Good to see you, {user?.full_name?.split(" ")[0]||"there"}.</h2><p>Search across your files. Every answer stays anchored to retrieved evidence.</p></div><label className="upload-button">{uploading?<Activity size={16}/>:<Upload size={16}/>} {uploading?"Indexing…":"Upload file"}<input type="file" hidden accept=".pdf,.docx,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.txt,.md" onChange={upload} disabled={uploading}/></label></header>
      <section className="command-deck"><div className="search-icon-wrap"><Search size={20}/></div><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")deepSearch()}} placeholder='Ask anything — “top 10 difficult DSA questions”'/><button className="gradient-button compact" onClick={deepSearch} disabled={loading}><Sparkles size={15}/>{loading?"Searching…":"Deep Search"}</button></section>
      {msg&&<div className="message-bar"><AlertTriangle size={15}/>{msg}</div>}
      <section className="metric-grid"><div className="metric-card"><div className="metric-icon"><Database size={17}/></div><div><b>{stats.files}</b><span>indexed files</span></div></div><div className="metric-card"><div className="metric-icon"><Network size={17}/></div><div><b>{stats.chunks}</b><span>retrieval chunks</span></div></div><div className="metric-card"><div className="metric-icon"><BrainCircuit size={17}/></div><div><b>{stats.embedded_chunks}</b><span>semantic vectors</span></div></div><div className="metric-card accent-card"><div className="metric-icon"><ShieldCheck size={17}/></div><div><b>6</b><span>guardrails</span></div></div></section>
      <section className="hero-canvas-card"><div className="hero-canvas-copy"><div className="eyebrow">CORPUS UNIVERSE</div><h3>Every file becomes a searchable node.</h3><p>Search results glow in the graph. Click any file to inspect source chunks.</p><div className="mini-status"><span><i className="live-dot"/> Live corpus</span><span>Hybrid retrieval</span><span>Groq grounded AI</span></div></div><div className="hero-canvas"><CorpusScene files={files} results={results} onSelectFile={openFile}/></div></section>
      <section className="content-grid"><div className="primary-column"><div className="section-heading"><div><div className="eyebrow">EVIDENCE ENGINE</div><h3>{activeView==="files"?"Indexed corpus":"Ranked evidence"}</h3></div><span>{activeView==="files"?files.length+" files":results.length+" matches"}</span></div>{activeView==="files"?<div className="file-grid">{files.length?files.map(f=><button className="file-card" key={f.id} onClick={()=>openFile(f.id)}><div className="file-card-icon">{iconFor(f.mime_type)}</div><div className="file-card-main"><b>{f.name}</b><small>{f.status} · {f.chunk_count} chunks{f.ocr_used?" · OCR":""}</small></div><ChevronRight size={16}/></button>):<div className="empty-state"><FileSearch size={25}/><b>Your corpus is empty.</b><span>Upload a document to begin.</span></div>}</div>:<div className="result-stack">{results.length?results.map((r,i)=><article className="evidence-card" key={r.chunk_id}><div className="rank-badge">{String(i+1).padStart(2,"0")}</div><div className="evidence-body"><div className="evidence-head"><div><b>{r.file_name}</b><small>{r.source_ref}</small></div><span className="score-chip">{Math.round(r.score*100)}%</span></div><p>{r.content}</p><div className="evidence-foot"><div className="reason-row">{(r.match_reasons||[]).slice(0,3).map(x=><span key={x}>{x}</span>)}</div><button className="text-button" onClick={()=>openFile(r.file_id)}>View evidence <ArrowUpRight size={14}/></button></div></div></article>):<div className="empty-state"><Search size={25}/><b>No evidence yet.</b><span>Ask a question against your indexed files.</span></div>}</div>}</div>
        <aside className="ai-column"><div className="ai-panel"><div className="ai-panel-top"><div className="ai-orb"><Sparkles size={17}/></div><div><div className="eyebrow">GROUNDED AI</div><h3>Final answer</h3></div></div>{answer?<div className="ai-answer-wrap"><div className="confidence-row"><span>Confidence</span><b>{Math.round(answer.confidence)}%</b></div><div className="confidence-bar"><span style={{width:Math.max(0,Math.min(100,answer.confidence))+"%"}}/></div><p className="ai-answer-text">{answer.answer}</p><div className="citation-block"><div className="eyebrow">CITATIONS</div>{answer.citations?.map((c:any,i:number)=><button className="citation-card" key={i} onClick={()=>openFile(c.file_id)}><FileText size={14}/><span><b>{c.file_name}</b><small>{c.source_ref}</small></span><ArrowUpRight size={13}/></button>)}</div></div>:<div className="ai-empty"><BrainCircuit size={28}/><b>Deep Search first.</b><span>Retrieve evidence, then Groq explains only what those chunks support.</span></div>}</div><div className="system-card"><div className="system-head"><Activity size={15}/> SYSTEM STATUS</div><div className="status-row"><span>Retrieval</span><b>Hybrid + metadata</b></div><div className="status-row"><span>Embedding</span><b>MiniLM</b></div><div className="status-row"><span>Generation</span><b>Groq</b></div><div className="status-row"><span>Corpus</span><b>{stats.files} files</b></div></div></aside>
      </section>
    </main>
    <AnimatePresence>{selectedFile&&<motion.div className="drawer-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onClick={()=>setSelectedFile(null)}><motion.aside className="evidence-drawer" initial={{x:70}} animate={{x:0}} exit={{x:70}} onClick={e=>e.stopPropagation()}><div className="drawer-head"><div><div className="eyebrow">SOURCE INSPECTOR</div><h3>{selectedFile.name}</h3></div><button className="icon-button" onClick={()=>setSelectedFile(null)}><X size={17}/></button></div><div className="drawer-meta"><span>{selectedFile.status}</span><span>{selectedFile.chunk_count} chunks</span><span>{selectedFile.ocr_used?"OCR":"Text extracted"}</span></div><div className="source-list">{selectedChunks.map((c:any,i:number)=><div className="source-block" key={c.id}><div className="source-label"><span>{String(i+1).padStart(2,"0")}</span><b>{c.source_ref}</b></div><p>{c.content}</p></div>)}</div><button className="delete-file" onClick={removeFile}><Trash2 size={15}/> Delete file</button></motion.aside></motion.div>}</AnimatePresence>
  </div>
}
function iconFor(mime:string){if(mime.includes("image"))return <ImageIcon size={18}/>;if(mime.includes("sheet")||mime.includes("csv"))return <Sheet size={18}/>;return <FileText size={18}/>}

function App(){const route=usePath();const path=route.split("?")[0];const token=sessionStorage.getItem("deep_token");useEffect(()=>{if(path==="/dashboard"&&!sessionStorage.getItem("deep_token"))navigate("/login");if(["/login","/register","/forgot-password"].includes(path)&&token)navigate("/dashboard")},[path,token]);
  if(path==="/"||path==="/about")return <AboutPage/>;if(path==="/login")return <LoginPage/>;if(path==="/register")return <RegisterPage/>;if(path==="/verify-email")return <VerifyEmailPage/>;if(path==="/forgot-password"||path==="/reset-password")return <ForgotPasswordPage/>;if(path==="/dashboard")return <Dashboard/>;return <AboutPage/>}
createRoot(document.getElementById("root")!).render(<App/>);
