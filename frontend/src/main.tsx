
import React,{useEffect,useMemo,useState}from"react";
import{createRoot}from"react-dom/client";
import{Canvas}from"@react-three/fiber";
import{Float,OrbitControls,Stars,Text,Line,Sparkles as ThreeSparkles}from"@react-three/drei";
import{motion,AnimatePresence}from"framer-motion";
import{Search,Upload,LogOut,FileText,Image as ImageIcon,Sheet,ShieldCheck,Database,Sparkles,LockKeyhole,Trash2,X,BrainCircuit,Network,Layers3,ArrowUpRight,Activity,FileSearch,ScanText,ChevronRight,CircleCheck,AlertTriangle}from"lucide-react";
import"./styles.css";
import{api}from"./api";

type FileRecord={id:string;name:string;mime_type:string;status:string;ocr_used:number;page_count:number;chunk_count:number;created_at:string};
type Result={score:number;file_id:string;file_name:string;chunk_id:string;content:string;source_ref:string;metadata:any;retrieval?:string;match_reasons?:string[];signals?:any};
type AIAnswer={answer:string;confidence:number;citations:any[];provider?:string;model?:string;guardrails?:string[];requested_count?:number|null};

function iconFor(mime:string){
  if(mime.includes("image"))return <ImageIcon size={18}/>;
  if(mime.includes("sheet")||mime.includes("csv"))return <Sheet size={18}/>;
  return <FileText size={18}/>;
}
function Node({position,label,active,onClick,color}:any){
  return <group position={position}>
    <Float speed={1.5} rotationIntensity={.3} floatIntensity={.65}>
      <mesh onClick={onClick}>
        <icosahedronGeometry args={[active?.34:.24,1]}/>
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={active?1.7:.6} metalness={.75} roughness={.2}/>
      </mesh>
      <Text position={[0,-.52,0]} fontSize={.14} maxWidth={1.7} anchorX="center" color="#c7d4ff">{label}</Text>
    </Float>
  </group>;
}
function CorpusScene({files,results,onSelectFile,landing=false}:{files:FileRecord[];results:Result[];onSelectFile:(id:string)=>void;landing?:boolean}){
  const positions=useMemo(()=>{const count=Math.max(files.length,landing?9:1);return Array.from({length:count},(_,i)=>{const a=i/count*Math.PI*2;const r=landing?3.5+(i%3)*.7:3.1+(i%2)*.7;return [Math.cos(a)*r,Math.sin(a*1.7)*1.7,Math.sin(a)*r*.55]})},[files.length,landing]);
  const active=new Set(results.map(r=>r.file_id));
  return <Canvas camera={{position:[0,.5,10],fov:46}} dpr={[1,1.5]}>
    <ambientLight intensity={.7}/><pointLight position={[4,5,7]} intensity={13} color="#7f8cff"/><pointLight position={[-5,-2,4]} intensity={8} color="#b65dff"/>
    <Stars radius={55} depth={35} count={landing?1200:700} factor={2.2} saturation={0} fade/>
    <ThreeSparkles count={landing?180:90} scale={[14,8,14]} size={1.5} speed={.35} color="#9aa7ff"/>
    <Float speed={.8} rotationIntensity={.15} floatIntensity={.5}>
      <mesh><icosahedronGeometry args={[1.25,2]}/><meshStandardMaterial color="#6f80ff" emissive="#3f4dff" emissiveIntensity={.8} metalness={.8} roughness={.2} wireframe/></mesh>
    </Float>
    {!landing&&positions.slice(0,files.length).map((pos,i)=><Node key={files[i].id} position={pos} label={files[i].name.slice(0,18)} active={active.has(files[i].id)} onClick={()=>onSelectFile(files[i].id)} color={active.has(files[i].id)?"#ba72ff":"#6c84ff"}/>)}
    {!landing&&positions.slice(0,Math.min(files.length,8)).map((p,i)=>{const n=positions[(i+1)%Math.max(1,Math.min(files.length,8))];return n?<Line key={i} points={[p as any,n as any]} color="#5b6fcf" transparent opacity={.22} lineWidth={1}/>:null})}
    {landing&&positions.map((pos,i)=><Node key={i} position={pos} label={i%3===0?"PDF":i%3===1?"DATA":"IMAGE"} active={i===2||i===7} onClick={()=>undefined} color={i%2===0?"#6e85ff":"#b66cff"}/>)}
    <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={landing?.2:.12}/>
  </Canvas>;
}
function AuthScreen({mode,setMode,email,setEmail,password,setPassword,name,setName,msg,onSubmit}:any){
  return <div className="landing-shell">
    <div className="landing-scene"><CorpusScene files={[]} results={[]} onSelectFile={()=>undefined} landing/></div><div className="landing-grid"/>
    <div className="landing-copy">
      <div className="brand-mark"><span>DEEP</span>SEARCH</div>
      <div className="eyebrow">PRIVATE FILE INTELLIGENCE · SEMANTIC SEARCH · GROUNDED AI</div>
      <h1>Search the corpus.<br/><span>See the intelligence.</span></h1>
      <p>A private search engine for PDFs, Word files, spreadsheets and images. Every answer is tied back to retrieved evidence.</p>
      <div className="landing-badges"><span><BrainCircuit size={14}/> Groq reasoning</span><span><Network size={14}/> FAISS semantic graph</span><span><ScanText size={14}/> OCR ingestion</span></div>
    </div>
    <motion.div className="auth-panel" initial={{opacity:0,y:24}} animate={{opacity:1,y:0}}>
      <div className="auth-kicker">YOUR PRIVATE WORKSPACE</div><h2>{mode==="login"?"Enter DeepSearch":"Create your workspace"}</h2>
      <p>Index your own files and ask questions in natural language.</p>
      <div className="auth-tabs"><button className={mode==="login"?"active":""} onClick={()=>setMode("login")}>Sign in</button><button className={mode==="signup"?"active":""} onClick={()=>setMode("signup")}>Create account</button></div>
      <form onSubmit={onSubmit} className="auth-form">
        {mode==="signup"&&<input value={name} onChange={e=>setName(e.target.value)} placeholder="Full name" required/>}
        <input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="Email address" required/>
        <input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Password" minLength={8} required/>
        <button className="gradient-button">{mode==="login"?"Open workspace":"Create workspace"}<ArrowUpRight size={17}/></button>
      </form>
      {msg&&<div className="alert">{msg}</div>}
      <div className="auth-foot"><LockKeyhole size={14}/> Private corpus · evidence-grounded AI</div>
    </motion.div>
  </div>;
}
function App(){
  const[token,setToken]=useState(sessionStorage.getItem("deep_token")||"");
  const[user,setUser]=useState<any>(null);
  const[mode,setMode]=useState<"login"|"signup">("login");
  const[email,setEmail]=useState("");const[password,setPassword]=useState("");const[name,setName]=useState("");
  const[query,setQuery]=useState("");const[files,setFiles]=useState<FileRecord[]>([]);const[results,setResults]=useState<Result[]>([]);
  const[answer,setAnswer]=useState<AIAnswer|null>(null);const[selectedFile,setSelectedFile]=useState<any>(null);const[selectedChunks,setSelectedChunks]=useState<any[]>([]);
  const[stats,setStats]=useState<any>({files:0,chunks:0,embedded_chunks:0});const[loading,setLoading]=useState(false);const[answerLoading,setAnswerLoading]=useState(false);
  const[uploading,setUploading]=useState(false);const[msg,setMsg]=useState("");const[activeView,setActiveView]=useState<"search"|"files">("search");

  const loadWorkspace=async()=>{try{const[me,fs,st]=await Promise.all([api.me(),api.files(),api.stats()]);setUser(me.user);setFiles(fs.files||[]);setStats(st)}catch{sessionStorage.removeItem("deep_token");setToken("")}};
  useEffect(()=>{if(token)loadWorkspace()},[token]);

  async function authenticate(e:React.FormEvent){e.preventDefault();setMsg("");try{const d=mode==="login"?await api.login({email,password}):await api.register({full_name:name,email,password});if(d.access_token){sessionStorage.setItem("deep_token",d.access_token);setToken(d.access_token)}else{setMsg(d.message||"Account created. Sign in to continue.");setMode("login")}}catch(e:any){setMsg(e.message)}}
  async function runSearch(){if(!query.trim())return;setLoading(true);setMsg("");setAnswer(null);try{const d=await api.search(query,20);setResults(d.results||[]);setActiveView("search")}catch(e:any){setResults([]);setMsg("Search failed: "+e.message)}finally{setLoading(false)}}
  async function runAI(){if(!query.trim())return;setAnswerLoading(true);setMsg("");try{const d=await api.answer(query);setAnswer(d.answer||null);if(!d.answer)setMsg("The AI did not return a grounded answer.")}catch(e:any){setMsg("AI explanation failed: "+e.message);setAnswer(null)}finally{setAnswerLoading(false)}}
  async function runDeepSearch(){if(!query.trim())return;setLoading(true);setAnswerLoading(true);setMsg("");try{const d=await api.deepSearch(query,20);setResults(d.results||[]);setAnswer(d.answer||null);setActiveView("search")}catch(e:any){setMsg("Deep Search failed: "+e.message);setResults([]);setAnswer(null)}finally{setLoading(false);setAnswerLoading(false)}}
  async function uploadFile(e:React.ChangeEvent<HTMLInputElement>){const file=e.target.files?.[0];if(!file)return;setUploading(true);setMsg("Indexing "+file.name+"…");try{const d=await api.upload(file);setMsg(d.name+" indexed · "+d.chunks+" chunks · "+d.embedding_chunks+" semantic vectors");await loadWorkspace()}catch(e:any){setMsg("Indexing failed: "+e.message)}finally{setUploading(false);e.target.value=""}}
  async function openFile(id:string){try{const[d,c]=await Promise.all([api.file(id),api.chunks(id)]);setSelectedFile(d.file);setSelectedChunks(c.chunks||[])}catch(e:any){setMsg(e.message)}}
  async function deleteSelectedFile(){if(!selectedFile)return;try{await api.deleteFile(selectedFile.id);setSelectedFile(null);setSelectedChunks([]);await loadWorkspace();setMsg("File removed from your corpus.")}catch(e:any){setMsg("Delete failed: "+e.message)}}

  if(!token)return <AuthScreen mode={mode} setMode={setMode} email={email} setEmail={setEmail} password={password} setPassword={setPassword} name={name} setName={setName} msg={msg} onSubmit={authenticate}/>;

  return <div className="workspace-shell">
    <div className="workspace-bg"><CorpusScene files={files} results={results} onSelectFile={openFile}/></div><div className="workspace-vignette"/>
    <aside className="sidebar-glass">
      <div><div className="brand-mark small"><span>DEEP</span>SEARCH</div><div className="workspace-label">PRIVATE CORPUS</div></div>
      <div className="sidebar-core"><div className="core-orbit"><span/></div><b>AI FILE INTELLIGENCE</b><small>Semantic · lexical · evidence</small></div>
      <nav className="sidebar-nav"><button className={activeView==="search"?"active":""} onClick={()=>setActiveView("search")}><Search size={16}/> Deep Search</button><button className={activeView==="files"?"active":""} onClick={()=>setActiveView("files")}><Layers3 size={16}/> Corpus</button></nav>
      <div className="guard-card"><div className="guard-title"><LockKeyhole size={15}/> AI Guardrails Active</div><span><CircleCheck size={12}/> Prompt-injection defense</span><span><CircleCheck size={12}/> Grounded citations</span><span><CircleCheck size={12}/> Secret redaction</span><span><CircleCheck size={12}/> Upload limits</span></div>
      <div className="sidebar-user"><div className="avatar">{(user?.full_name||"U").slice(0,1).toUpperCase()}</div><div><b>{user?.full_name||"Workspace user"}</b><small>{user?.email}</small></div></div>
      <button className="logout-button" onClick={()=>{sessionStorage.removeItem("deep_token");setToken("")}}><LogOut size={16}/> Logout</button>
    </aside>

    <main className="dashboard">
      <header className="topbar"><div><div className="eyebrow">LOCAL CORPUS · LIVE INTELLIGENCE LAYER</div><h2>Good to see you, {user?.full_name?.split(" ")[0]||"there"}.</h2><p>Search across your files. Every answer stays anchored to retrieved evidence.</p></div>
      <label className={"upload-button "+(uploading?"busy":"")}>{uploading?<Activity size={16}/>:<Upload size={16}/>} {uploading?"Indexing…":"Upload file"}<input type="file" hidden accept=".pdf,.docx,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.txt,.md" onChange={uploadFile} disabled={uploading}/></label></header>

      <section className="command-deck"><div className="search-icon-wrap"><Search size={20}/></div><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")runDeepSearch()}} placeholder='Ask anything in your corpus — "top 10 difficult DSA questions"'/><div className="search-actions"><button className="subtle-button" onClick={runSearch} disabled={loading}><Search size={15}/> Search</button><button className="gradient-button compact" onClick={runDeepSearch} disabled={loading||answerLoading}><Sparkles size={15}/> {loading||answerLoading?"Thinking…":"Deep Search"}</button></div></section>
      {msg&&<motion.div className="message-bar" initial={{opacity:0,y:-6}} animate={{opacity:1,y:0}}><AlertTriangle size={15}/>{msg}</motion.div>}

      <section className="metric-grid">
        <div className="metric-card"><div className="metric-icon"><Database size={17}/></div><div><b>{stats.files??files.length}</b><span>indexed files</span></div><ArrowUpRight size={16} className="metric-arrow"/></div>
        <div className="metric-card"><div className="metric-icon"><Network size={17}/></div><div><b>{stats.chunks??0}</b><span>retrieval chunks</span></div><ArrowUpRight size={16} className="metric-arrow"/></div>
        <div className="metric-card"><div className="metric-icon"><BrainCircuit size={17}/></div><div><b>{stats.embedded_chunks??0}</b><span>semantic vectors</span></div><ArrowUpRight size={16} className="metric-arrow"/></div>
        <div className="metric-card accent-card"><div className="metric-icon"><ShieldCheck size={17}/></div><div><b>6</b><span>active guardrails</span></div><ArrowUpRight size={16} className="metric-arrow"/></div>
      </section>

      <section className="hero-canvas-card"><div className="hero-canvas-copy"><div className="eyebrow">CORPUS UNIVERSE</div><h3>Your files are a searchable knowledge graph.</h3><p>Click a node to inspect extracted evidence. Search results glow in the graph.</p><div className="mini-status"><span><i className="live-dot"/> Live corpus</span><span>FAISS + lexical reranking</span></div></div><div className="hero-canvas"><CorpusScene files={files} results={results} onSelectFile={openFile}/></div></section>

      <section className="content-grid">
        <div className="primary-column">
          <div className="section-heading"><div><div className="eyebrow">EVIDENCE ENGINE</div><h3>{activeView==="files"?"Indexed corpus":"Ranked evidence"}</h3></div><span>{activeView==="files"?files.length+" files":results.length+" matches"}</span></div>
          {activeView==="files"?<div className="file-grid">{files.length?files.map(f=><motion.button whileHover={{y:-4}} className="file-card" key={f.id} onClick={()=>openFile(f.id)}><div className="file-card-icon">{iconFor(f.mime_type)}</div><div className="file-card-main"><b>{f.name}</b><small>{f.status} · {f.chunk_count} chunks{f.ocr_used?" · OCR":""}</small></div><ChevronRight size={16}/></motion.button>):<div className="empty-state"><FileSearch size={25}/><b>Your corpus is empty.</b><span>Upload your first PDF, spreadsheet, document or image.</span></div>}</div>:
          <div className="result-stack">{results.length?results.map((r,i)=><motion.article key={r.chunk_id} className="evidence-card" initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} transition={{delay:Math.min(i*.04,.25)}}><div className="rank-badge">{String(i+1).padStart(2,"0")}</div><div className="evidence-body"><div className="evidence-head"><div><b>{r.file_name}</b><small>{r.source_ref}</small></div><span className="score-chip">{Math.round(r.score*100)}%</span></div><p>{r.content}</p><div className="evidence-foot"><div className="reason-row">{(r.match_reasons||["semantic relevance"]).slice(0,3).map(x=><span key={x}>{x}</span>)}</div><button onClick={()=>openFile(r.file_id)} className="text-button">View evidence <ArrowUpRight size={14}/></button></div></div></motion.article>):<div className="empty-state"><Search size={25}/><b>No evidence yet.</b><span>Run Deep Search against your indexed corpus.</span></div>}</div>}
        </div>

        <aside className="ai-column">
          <div className="ai-panel"><div className="ai-panel-top"><div className="ai-orb"><Sparkles size={17}/></div><div><div className="eyebrow">GROUNDED AI</div><h3>Reason over evidence</h3></div></div>
            {!answer?<div className="ai-empty"><BrainCircuit size={28}/><b>Ask the corpus a question.</b><span>Deep Search retrieves evidence first. Groq explains only what those sources support.</span><button className="gradient-button compact" onClick={runAI} disabled={!query.trim()||answerLoading}>{answerLoading?"Generating…":"Explain current query"}</button></div>:
            <AnimatePresence mode="wait"><motion.div initial={{opacity:0}} animate={{opacity:1}} className="ai-answer-wrap"><div className="confidence-row"><span>Confidence</span><b>{Math.round(answer.confidence)}%</b></div><div className="confidence-bar"><span style={{width:Math.max(0,Math.min(100,answer.confidence))+"%"}}/></div><p className="ai-answer-text">{answer.answer}</p><div className="citation-block"><div className="eyebrow">CITATIONS</div>{answer.citations?.map((c:any,i:number)=><button key={i} onClick={()=>openFile(c.file_id)} className="citation-card"><FileText size={14}/><span><b>{c.file_name}</b><small>{c.source_ref}</small></span><ArrowUpRight size={13}/></button>)}</div><div className="guard-trace">{(answer.guardrails||[]).map(g=><span key={g}><CircleCheck size={11}/> {g.replaceAll("_"," ")}</span>)}</div></motion.div></AnimatePresence>}
          </div>
          <div className="system-card"><div className="system-head"><Activity size={15}/> SYSTEM STATUS</div><div className="status-row"><span>Retrieval</span><b>Hybrid</b></div><div className="status-row"><span>Embedding</span><b>MiniLM</b></div><div className="status-row"><span>Generation</span><b>Groq</b></div><div className="status-row"><span>Corpus</span><b>{stats.files??0} files</b></div></div>
        </aside>
      </section>
    </main>

    <AnimatePresence>{selectedFile&&<motion.div className="drawer-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onClick={()=>setSelectedFile(null)}><motion.aside className="evidence-drawer" initial={{x:70,opacity:0}} animate={{x:0,opacity:1}} exit={{x:70,opacity:0}} onClick={e=>e.stopPropagation()}><div className="drawer-head"><div><div className="eyebrow">SOURCE INSPECTOR</div><h3>{selectedFile.name}</h3></div><button className="icon-button" onClick={()=>setSelectedFile(null)}><X size={17}/></button></div><div className="drawer-meta"><span>{selectedFile.status}</span><span>{selectedFile.chunk_count} chunks</span><span>{selectedFile.ocr_used?"OCR":"Text extracted"}</span></div><div className="source-list">{selectedChunks.map((c,i)=><div className="source-block" key={c.id}><div className="source-label"><span>{String(i+1).padStart(2,"0")}</span><b>{c.source_ref}</b></div><p>{c.content}</p></div>)}</div><button className="delete-file" onClick={deleteSelectedFile}><Trash2 size={15}/> Delete this file</button></motion.aside></motion.div>}</AnimatePresence>
  </div>;
}
createRoot(document.getElementById("root")!).render(<App/>);
