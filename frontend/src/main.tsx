
import React,{useEffect,useMemo,useState}from"react";
import{createRoot}from"react-dom/client";
import{Canvas}from"@react-three/fiber";
import{Float,OrbitControls,Stars,Text,Line,Sparkles as ThreeSparkles}from"@react-three/drei";
import{motion,AnimatePresence}from"framer-motion";
import{Search,Upload,LogOut,FileText,Image as ImageIcon,Sheet,ShieldCheck,Database,Sparkles,LockKeyhole,Trash2,X,BrainCircuit,Network,Layers3,ArrowUpRight,Activity,FileSearch,ScanText,ChevronRight,CircleCheck,AlertTriangle,Mail,ArrowRight,RefreshCcw,BookOpen,KeyRound,FolderOpen}from"lucide-react";
import"./styles.css";
import{api,clearAuthToken}from"./api";

type FileRecord={id:string;name:string;mime_type:string;status:string;ocr_used:number;page_count:number;chunk_count:number;created_at:string};
type Result={score:number;file_id:string;file_name:string;chunk_id:string;content:string;source_ref:string;metadata:any;retrieval?:string;match_reasons?:string[];signals?:any};
type AIAnswer={answer:string;confidence:number;citations:any[];provider?:string;model?:string;guardrails?:string[]};

function navigate(path:string){window.history.pushState({},'',path);window.dispatchEvent(new PopStateEvent("popstate"))}
function usePath(){const[path,setPath]=useState(window.location.pathname+window.location.search);useEffect(()=>{const f=()=>setPath(window.location.pathname+window.location.search);window.addEventListener("popstate",f);return()=>window.removeEventListener("popstate",f)},[]);return path}
function queryParam(name:string){return new URLSearchParams(window.location.search).get(name)||""}

function DeepSearchVisual({large=false}:{large?:boolean}){
  return <div className={large?"ds-visual large":"ds-visual"}>
    <div className="ds-glow glow-a"/>
    <div className="ds-glow glow-b"/>
    <div className="ds-particle-field">
      {Array.from({length:18}).map((_,i)=><span key={i} style={{["--i" as any]:i} as React.CSSProperties}/>)}
    </div>

    <motion.div className="ds-core-card" animate={{y:[0,-10,0],rotateZ:[0,.6,0]}} transition={{duration:5,repeat:Infinity,ease:"easeInOut"}}>
      <div className="ds-core-icon"><Database size={large?24:18}/></div>
      <div className="ds-core-lines"><span/><span/><span/></div>
      <div className="ds-core-status"><i/>INDEXED</div>
    </motion.div>

    <motion.div className="ds-float-card card-pdf" animate={{y:[0,-16,0],x:[0,6,0],rotateZ:[-3,0,-3]}} transition={{duration:5.4,repeat:Infinity,ease:"easeInOut"}}>
      <FileText size={15}/><div><b>report.pdf</b><small>page 42 · 91% match</small></div>
    </motion.div>

    <motion.div className="ds-float-card card-data" animate={{y:[0,11,0],x:[0,-5,0],rotateZ:[4,1,4]}} transition={{duration:4.6,repeat:Infinity,ease:"easeInOut",delay:.4}}>
      <Sheet size={15}/><div><b>sales.xlsx</b><small>sheet Q3 · 1,284 rows</small></div>
    </motion.div>

    <motion.div className="ds-float-card card-ai" animate={{y:[0,-12,0],x:[0,5,0],scale:[1,1.03,1]}} transition={{duration:4.2,repeat:Infinity,ease:"easeInOut",delay:.8}}>
      <Sparkles size={15}/><div><b>Grounded answer</b><small>3 citations · Groq</small></div>
    </motion.div>

    <motion.div className="ds-float-card card-ocr" animate={{y:[0,9,0],x:[0,-4,0]}} transition={{duration:5.8,repeat:Infinity,ease:"easeInOut",delay:1.1}}>
      <ScanText size={15}/><div><b>OCR extracted</b><small>image → searchable text</small></div>
    </motion.div>

  </div>;
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

function scrollToSection(id:string){
  document.getElementById(id)?.scrollIntoView({behavior:"smooth",block:"start"});
}

function DataGlobe(){
  const points=useMemo(()=>{
    const items=[];
    const total=70;
    for(let i=0;i<total;i++){
      const phi=Math.acos(1-(2*(i+.5))/total);
      const theta=Math.PI*(1+Math.sqrt(5))*i;
      const r=1.58;
      items.push([r*Math.sin(phi)*Math.cos(theta),r*Math.cos(phi),r*Math.sin(phi)*Math.sin(theta)]);
    }
    return items;
  },[]);
  return <group rotation={[0.18,-0.45,0]}>
    <mesh>
      <sphereGeometry args={[1.58,48,48]}/>
      <meshStandardMaterial color="#101b50" emissive="#1f2c98" emissiveIntensity={.8} metalness={.9} roughness={.28} wireframe transparent opacity={.6}/>
    </mesh>
    <mesh>
      <sphereGeometry args={[1.49,32,32]}/>
      <meshBasicMaterial color="#7180ff" wireframe transparent opacity={.06}/>
    </mesh>
    {points.map((p,i)=><Float key={i} speed={.7+(i%4)*.12} floatIntensity={.1}>
      <mesh position={p as [number,number,number]}>
        <sphereGeometry args={[i%7===0?.025:.014,8,8]}/>
        <meshBasicMaterial color={i%9===0?"#c37cff":"#7087ff"}/>
      </mesh>
    </Float>)}
    <mesh rotation={[Math.PI/2,0,0]}>
      <torusGeometry args={[1.69,.01,8,128]}/>
      <meshBasicMaterial color="#667aff" transparent opacity={.35}/>
    </mesh>
    <mesh rotation={[0,Math.PI/3,0]}>
      <torusGeometry args={[1.72,.008,8,128]}/>
      <meshBasicMaterial color="#a06eff" transparent opacity={.22}/>
    </mesh>
  </group>;
}

function HeroUniverse(){
  return <div className="hero-universe">
    <div className="landing-3d-canvas">
      <Canvas camera={{position:[0,0,7.8],fov:42}} dpr={[1,1.5]}>
        <ambientLight intensity={.6}/>
        <pointLight position={[3,4,6]} intensity={18} color="#8291ff"/>
        <pointLight position={[-4,-1,3]} intensity={9} color="#b36cff"/>
        <Stars radius={38} depth={20} count={900} factor={1.8} saturation={0} fade/>
        <ThreeSparkles count={130} scale={[12,7,8]} size={1.5} speed={.25} color="#9baaff"/>

        <Float speed={.55} floatIntensity={.22}><DataGlobe/></Float>

        <Float speed={1.2} floatIntensity={.5}>
          <mesh position={[-1.9,1.2,.1]}>
            <boxGeometry args={[.35,.5,.06]}/>
            <meshStandardMaterial color="#715fff" emissive="#715fff" emissiveIntensity={1.2} metalness={.7} roughness={.22}/>
          </mesh>
        </Float>
        <Float speed={1.4} floatIntensity={.65}>
          <mesh position={[2.0,-.85,.2]}>
            <boxGeometry args={[.4,.55,.06]}/>
            <meshStandardMaterial color="#a06cff" emissive="#a06cff" emissiveIntensity={1.2} metalness={.7} roughness={.22}/>
          </mesh>
        </Float>
      </Canvas>
    </div>

    <form className="hero-search-panel" onSubmit={(e)=>{e.preventDefault();navigate("/register")}}>
      <div className="hero-search-top">
        <Search size={19}/>
        <input aria-label="Search your files" placeholder="Search across your files..." />
        <button aria-label="Start searching" type="submit"><ArrowRight size={17}/></button>
      </div>
      <div className="hero-format-row">
        <span><FileText size={13}/> PDF</span>
        <span><FileText size={13}/> DOCX</span>
        <span><Sheet size={13}/> XLSX</span>
        <span><Sheet size={13}/> CSV</span>
        <span><ImageIcon size={13}/> Images</span>
      </div>
      <div className="hero-search-label">Try searching:</div>
      <div className="hero-query-row">
        <button type="button" onClick={()=>navigate("/register")}>“last month invoices”</button>
        <button type="button" onClick={()=>navigate("/register")}>“project report summary”</button>
        <button type="button" onClick={()=>navigate("/register")}>“revenue in Q3”</button>
      </div>
    </form>

    <motion.div className="hero-doc-card doc-red" animate={{y:[0,-10,0],rotateZ:[-4,-1,-4]}} transition={{duration:5.5,repeat:Infinity,ease:"easeInOut"}}>
      <FileText size={16}/><div><b>Annual report.pdf</b><small>page 12 · 92% match</small></div>
    </motion.div>
    <motion.div className="hero-doc-card doc-blue" animate={{y:[0,9,0],rotateZ:[4,1,4]}} transition={{duration:4.7,repeat:Infinity,ease:"easeInOut",delay:.4}}>
      <FileText size={16}/><div><b>brief.docx</b><small>semantic match</small></div>
    </motion.div>
    <motion.div className="hero-doc-card doc-green" animate={{y:[0,-7,0],x:[0,4,0]}} transition={{duration:4.9,repeat:Infinity,ease:"easeInOut",delay:.8}}>
      <Sheet size={16}/><div><b>sales.xlsx</b><small>sheet Q3 · 1,284 rows</small></div>
    </motion.div>
    <motion.div className="hero-doc-card doc-purple" animate={{y:[0,8,0],x:[0,-5,0]}} transition={{duration:5.2,repeat:Infinity,ease:"easeInOut",delay:1}}>
      <ScanText size={16}/><div><b>OCR image</b><small>searchable text</small></div>
    </motion.div>
    <motion.div className="hero-answer-card" animate={{y:[0,-6,0]}} transition={{duration:5.2,repeat:Infinity,ease:"easeInOut",delay:.6}}>
      <div className="answer-top"><Sparkles size={14}/><b>Grounded answer</b><span>3 citations</span></div>
      <p>Annual revenue increased by <strong>32%</strong> in Q3 2024.</p>
      <small>Annual Revenue Report 2024.pdf · Page 12</small>
    </motion.div>
  </div>;
}

function HomePage(){
  return <Layout>
    <div className="site-background">
      <div className="site-glow glow-left"/>
      <div className="site-glow glow-right"/>
      <div className="site-particle-dust"/>
    </div>

    <header className="site-nav">
      <button className="brand-mark link-brand" onClick={()=>window.scrollTo({top:0,behavior:"smooth"})}>
        <span>DEEP</span>SEARCH
      </button>
      <nav className="desktop-nav">
        <a href="#home" onClick={(e)=>{e.preventDefault();scrollToSection("home")}}>Home</a>
        <a href="#capabilities" onClick={(e)=>{e.preventDefault();scrollToSection("capabilities")}}>Features</a>
        <a href="#how-it-works" onClick={(e)=>{e.preventDefault();scrollToSection("how-it-works")}}>How it works</a>
        <a href="#use-cases" onClick={(e)=>{e.preventDefault();scrollToSection("use-cases")}}>Use Cases</a>
        <a href="#pricing" onClick={(e)=>{e.preventDefault();scrollToSection("pricing")}}>Pricing</a>
      </nav>
      <button className="nav-about" onClick={()=>scrollToSection("about")}>About DeepSearch <ArrowRight size={14}/></button>
    </header>

    <main>
      <section id="home" className="hero-section">
        <div className="hero-copy">
          <div className="hero-badge"><Sparkles size={13}/> AI POWERED FILE SEARCH</div>
          <h1>Turn your files into<br/><span>a searchable intelligence layer.</span></h1>
          <p>
            DeepSearch reads PDFs, Word documents, spreadsheets and images,
            understands their content, tables and context, and returns
            ranked evidence you can inspect.
          </p>
          <div className="hero-actions">
            <button className="gradient-button hero-primary" onClick={()=>navigate("/register")}>Start searching <ArrowRight size={17}/></button>
            <button className="ghost-play" onClick={()=>scrollToSection("how-it-works")}><span>▶</span> See how it works</button>
          </div>

          <div className="hero-feature-row">
            <div><div className="hero-feature-icon"><Search size={16}/></div><div><b>Semantic Search</b><span>Find meaning, not just keywords</span></div></div>
            <div><div className="hero-feature-icon"><ScanText size={16}/></div><div><b>OCR for Images</b><span>Search inside scanned files</span></div></div>
            <div><div className="hero-feature-icon"><Layers3 size={16}/></div><div><b>Multi-Format</b><span>PDF, Word, Excel, CSV and more</span></div></div>
          </div>

          <div className="hero-stats">
            <div><b>5+</b><span>File formats</span></div>
            <div><b>Hybrid</b><span>Semantic + lexical</span></div>
            <div><b>Source</b><span>Evidence citations</span></div>
            <div><b>Groq</b><span>Grounded generation</span></div>
          </div>
        </div>

        <HeroUniverse/>
      </section>

      <section id="capabilities" className="flow-strip">
        <div className="flow-card">
          <div className="flow-num">01</div><div className="flow-icon"><Upload size={19}/></div>
          <div><b>Ingest everything</b><span>Upload files and extract text, tables, pages and OCR content.</span></div>
          <ArrowRight className="flow-arrow" size={18}/>
        </div>
        <div className="flow-card">
          <div className="flow-num">02</div><div className="flow-icon"><Search size={19}/></div>
          <div><b>Retrieve precisely</b><span>Combine semantic vectors, lexical signals and structured metadata.</span></div>
          <ArrowRight className="flow-arrow" size={18}/>
        </div>
        <div className="flow-card">
          <div className="flow-num">03</div><div className="flow-icon"><FileSearch size={19}/></div>
          <div><b>See evidence</b><span>Open the exact source chunk behind every ranked result.</span></div>
          <ArrowRight className="flow-arrow" size={18}/>
        </div>
      </section>

      <section id="how-it-works" className="dark-section how-section-new">
        <div className="section-head-center"><div className="section-eyebrow">HOW IT WORKS</div><h2>Search first. Generate second.</h2><p>The system retrieves evidence before Groq writes an answer.</p></div>
        <div className="pipeline-visual">
          <div><span>01</span><Search size={19}/><b>Your question</b><small>Natural language</small></div>
          <i>→</i>
          <div><span>02</span><Network size={19}/><b>Relevant chunks</b><small>Semantic + lexical</small></div>
          <i>→</i>
          <div><span>03</span><ShieldCheck size={19}/><b>Guarded AI</b><small>Groq + citations</small></div>
          <i>→</i>
          <div><span>04</span><FileText size={19}/><b>Final answer</b><small>Traceable evidence</small></div>
        </div>
      </section>

      <section id="use-cases" className="use-case-section">
        <div className="section-eyebrow">USE CASES</div><h2>Built for questions buried inside files.</h2>
        <div className="use-case-grid">
          <article><div className="use-icon"><BookOpen size={18}/></div><h3>Study & placement</h3><p>Ask across aptitude sheets, notes, PDFs and preparation material without manually hunting every page.</p></article>
          <article><div className="use-icon"><Database size={18}/></div><h3>Reports & operations</h3><p>Find figures, tables, customer notes and report evidence across office documents and spreadsheets.</p></article>
          <article><div className="use-icon"><ScanText size={18}/></div><h3>Scanned archives</h3><p>Use OCR to make image-based documents searchable and bring their evidence into ranked results.</p></article>
        </div>
      </section>

      <section id="pricing" className="pricing-section">
        <div className="section-head-center"><div className="section-eyebrow">PRICING</div><h2>Simple while we build.</h2><p>A focused hackathon workspace first. Scale the storage and infrastructure later.</p></div>
        <div className="pricing-card">
          <div><span className="price-kicker">DEEPSEARCH DEMO</span><h3>Free workspace</h3><p>Everything needed to experience the evidence-first search flow.</p></div>
          <div className="price-list"><span><CircleCheck size={14}/> Multi-format ingestion</span><span><CircleCheck size={14}/> OCR + structured chunks</span><span><CircleCheck size={14}/> Hybrid retrieval</span><span><CircleCheck size={14}/> Groq grounded answers</span></div>
          <button className="gradient-button" onClick={()=>navigate("/register")}>Create workspace <ArrowRight size={16}/></button>
        </div>
      </section>

      <section id="about" className="about-mini-section">
        <div><div className="section-eyebrow">ABOUT DEEPSEARCH</div><h2>A private intelligence layer for your own corpus.</h2><p>Upload, index, ask and inspect. The product is designed around one principle: the answer should always be traceable back to the evidence.</p></div>
        <button className="subtle-button big" onClick={()=>navigate("/register")}>Open the workspace <ArrowRight size={15}/></button>
      </section>
    </main>

    <footer className="site-footer">
      <div className="brand-mark"><span>DEEP</span>SEARCH</div>
      <span>Private file intelligence · semantic retrieval · grounded AI</span>
      <button onClick={()=>navigate("/login")}>Sign in <ArrowRight size={13}/></button>
    </footer>
  </Layout>;
}



function AuthScene({kind}:{kind:"login"|"register"|"forgot"|"verify"|"reset"}){
  const title=kind==="verify"?"VERIFY":kind==="forgot"||kind==="reset"?"RECOVER":kind==="register"?"CREATE":"SEARCH";
  return <div className="auth-scene">
    <Canvas camera={{position:[0,0,7],fov:42}} dpr={[1,1.5]}>
      <ambientLight intensity={.55}/>
      <pointLight position={[3,4,5]} intensity={16} color="#7f91ff"/>
      <pointLight position={[-3,-1,4]} intensity={8} color="#b76dff"/>
      <Stars radius={32} depth={18} count={620} factor={1.6} saturation={0} fade/>
      <ThreeSparkles count={95} scale={[10,7,8]} size={1.5} speed={.2} color="#9caaff"/>
      <Float speed={.65} floatIntensity={.18}>
        <mesh rotation={[.2,-.35,.08]}>
          <boxGeometry args={[1.75,1.12,.22]}/>
          <meshStandardMaterial color="#111b45" emissive="#263799" emissiveIntensity={.9} metalness={.85} roughness={.23}/>
        </mesh>
        <mesh position={[0,.1,.16]}>
          <boxGeometry args={[1.28,.08,.04]}/>
          <meshBasicMaterial color="#8497ff"/>
        </mesh>
        <mesh position={[0,-.12,.16]}>
          <boxGeometry args={[.92,.06,.04]}/>
          <meshBasicMaterial color="#5f73d8"/>
        </mesh>
      </Float>
      {[
        ["PDF",-2.2,1.45,"#e66f91"],
        ["DOCX",2.15,1.2,"#708eff"],
        ["XLSX",2.2,-1.15,"#69c8a0"],
        ["OCR",-2.1,-1.25,"#ba78ff"],
      ].map(([label,x,y,color],i)=>
        <Float key={i} speed={1+i*.08} floatIntensity={.35}>
          <group position={[x as number,y as number,.15]}>
            <mesh>
              <boxGeometry args={[.62,.78,.08]}/>
              <meshStandardMaterial color={color as string} emissive={color as string} emissiveIntensity={.65} metalness={.55} roughness={.28}/>
            </mesh>
            <Text position={[0,-.06,.08]} fontSize={.12} color="#fff" anchorX="center">{label as string}</Text>
          </group>
        </Float>
      )}
    </Canvas>
    <div className="auth-scene-copy">
      <div className="auth-scene-kicker">DEEPSEARCH</div>
      <h2>{title}</h2>
      <p>{kind==="verify"?"Secure email verification keeps your workspace protected.":kind==="forgot"||kind==="reset"?"Recover access with a short-lived email OTP.":"Private document intelligence with evidence-first AI."}</p>
      <div className="auth-scene-tags"><span>PDF</span><span>DOCX</span><span>XLSX</span><span>OCR</span><span>GROQ</span></div>
    </div>
  </div>;
}

function AuthShell({kind,title,subtitle,children}:{kind:"login"|"register"|"forgot"|"verify"|"reset";title:string;subtitle:string;children:React.ReactNode}){
  return <Layout>
    <div className="auth-page">
      <header className="auth-page-nav">
        <button className="brand-mark link-brand" onClick={()=>navigate("/")}>
          <span>DEEP</span>SEARCH
        </button>
        <button className="auth-home-link" onClick={()=>navigate("/")}>Back to home <ArrowRight size={13}/></button>
      </header>
      <div className="auth-page-scene"><AuthScene kind={kind}/></div>
      <main className="auth-page-main">
        <motion.section className="auth-form-card" initial={{opacity:0,y:18}} animate={{opacity:1,y:0}} transition={{duration:.45}}>
          <div className="auth-form-header">
            <div className="auth-mini-brand"><span>DEEP</span>SEARCH</div>
            <div className="auth-kicker">PRIVATE WORKSPACE</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          {children}
        </motion.section>
      </main>
    </div>
  </Layout>;
}

function LoginPage(){
  const[email,setEmail]=useState("");const[password,setPassword]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);const[verifyNeeded,setVerifyNeeded]=useState(false);
  async function submit(e:React.FormEvent){
    e.preventDefault();setLoading(true);setMsg("");setVerifyNeeded(false);
    try{await api.login({email,password});navigate("/dashboard")}
    catch(err:any){setMsg(err.message);setVerifyNeeded(String(err.message).toLowerCase().includes("verify your email"))}
    finally{setLoading(false)}
  }
  return <AuthShell kind="login" title="Welcome back" subtitle="Sign in to search your files with evidence-first AI.">
    <form className="auth-form-main" onSubmit={submit}>
      <label>Email address<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" required/></label>
      <label><span className="field-label-row">Password<button type="button" className="inline-link" onClick={()=>navigate("/forgot-password")}>Forgot password?</button></span><input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" required/></label>
      <label className="check-line"><input type="checkbox"/> <span>Remember me</span></label>
      <button className="auth-submit" disabled={loading}>{loading?"Signing in…":"Sign in"}<ArrowRight size={16}/></button>
    </form>
    {msg&&<div className="auth-alert">{msg}</div>}
    {verifyNeeded&&<button className="auth-secondary" onClick={()=>navigate("/check-email?email="+encodeURIComponent(email))}>Verify email <Mail size={14}/></button>}
    <div className="auth-divider"><span>PRIVATE WORKSPACE</span></div>
    <p className="auth-switch">New here? <button onClick={()=>navigate("/register")}>Create an account</button></p>
  </AuthShell>;
}

function RegisterPage(){
  const[name,setName]=useState("");const[email,setEmail]=useState("");const[password,setPassword]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  async function submit(e:React.FormEvent){
    e.preventDefault();setLoading(true);setMsg("");
    try{const d=await api.register({full_name:name,email,password});navigate("/check-email?email="+encodeURIComponent(d.email||email))}
    catch(err:any){setMsg(err.message)}
    finally{setLoading(false)}
  }
  return <AuthShell kind="register" title="Create your account" subtitle="Join DeepSearch and unlock intelligent file search.">
    <form className="auth-form-main" onSubmit={submit}>
      <label>Full name<input value={name} onChange={e=>setName(e.target.value)} placeholder="Your full name" required minLength={2}/></label>
      <label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required/></label>
      <label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 8 characters" required minLength={8}/></label>
      <label className="terms-line"><input type="checkbox" required/> <span>I agree to the Terms of Service and Privacy Policy</span></label>
      <button className="auth-submit" disabled={loading}>{loading?"Creating…":"Create account & send code"}<ArrowRight size={16}/></button>
    </form>
    {msg&&<div className="auth-alert">{msg}</div>}
    <p className="auth-switch">Already have an account? <button onClick={()=>navigate("/login")}>Sign in</button></p>
  </AuthShell>;
}

function CheckEmailPage(){
  const email=queryParam("email");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);const[seconds,setSeconds]=useState(0);
  useEffect(()=>{if(seconds<=0)return;const t=setInterval(()=>setSeconds(v=>Math.max(0,v-1)),1000);return()=>clearInterval(t)},[seconds]);
  async function resend(){if(seconds>0)return;setLoading(true);setMsg("");try{await api.resendRegistrationOtp(email);setSeconds(60);setMsg("A fresh verification OTP was sent.")}catch(e:any){setMsg(e.message)}finally{setLoading(false)}}
  return <AuthShell kind="verify" title="Check your email" subtitle={"We sent a 6-digit verification OTP to "+email+". The code expires in 10 minutes."}>
    <div className="check-email-art"><Mail size={58}/><div className="check-mail-badge">✓</div></div>
    <div className="check-steps"><span><Mail size={15}/> Open your email</span><span><KeyRound size={15}/> Copy the 6-digit code</span><span><ShieldCheck size={15}/> Verify and open dashboard</span></div>
    <button className="auth-submit" onClick={()=>navigate("/verify-email?email="+encodeURIComponent(email))}>Enter verification code <ArrowRight size={16}/></button>
    <button className="auth-secondary" onClick={resend} disabled={loading||seconds>0}>{seconds?("Resend OTP in "+seconds+"s"):(loading?"Sending…":"Resend verification OTP")}<RefreshCcw size={14}/></button>
    {msg&&<div className="auth-alert">{msg}</div>}
    <p className="auth-switch"><button onClick={()=>navigate("/login")}>Back to sign in</button></p>
  </AuthShell>;
}

function VerifyEmailPage(){
  const email=queryParam("email");const[otp,setOtp]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  async function verify(e:React.FormEvent){e.preventDefault();setLoading(true);setMsg("");try{await api.verifyRegistration({email,otp});navigate("/dashboard")}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell kind="verify" title="Verify your email" subtitle={"Enter the 6-digit code sent to "+email+"."}>
    <form className="auth-form-main" onSubmit={verify}>
      <label>Verification code<input className="otp-input" inputMode="numeric" value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,"").slice(0,6))} placeholder="000000" maxLength={6} autoComplete="one-time-code" required/></label>
      <button className="auth-submit" disabled={loading}>{loading?"Verifying…":"Verify email"}<ArrowRight size={16}/></button>
    </form>
    {msg&&<div className="auth-alert">{msg}</div>}
    <p className="auth-switch">Didn't receive it? <button onClick={()=>navigate("/check-email?email="+encodeURIComponent(email))}>Resend OTP</button></p>
  </AuthShell>;
}

function ForgotPasswordPage(){
  const[email,setEmail]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  async function submit(e:React.FormEvent){e.preventDefault();setLoading(true);setMsg("");try{await api.forgotPassword(email);navigate("/verify-reset?email="+encodeURIComponent(email))}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell kind="forgot" title="Forgot password?" subtitle="Enter your email and we’ll send you a verification OTP to reset your password.">
    <form className="auth-form-main" onSubmit={submit}>
      <label>Email address<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required/></label>
      <button className="auth-submit" disabled={loading}>{loading?"Sending OTP…":"Send verification OTP"}<ArrowRight size={16}/></button>
    </form>
    {msg&&<div className="auth-alert">{msg}</div>}
    <p className="auth-switch"><button onClick={()=>navigate("/login")}>Back to sign in</button></p>
  </AuthShell>;
}

function VerifyResetPage(){
  const email=queryParam("email");const[otp,setOtp]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  async function submit(e:React.FormEvent){e.preventDefault();setLoading(true);setMsg("");try{const d=await api.verifyResetOtp({email,otp});sessionStorage.setItem("deep_reset_token",d.reset_token);navigate("/reset-password")}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell kind="reset" title="Enter your OTP" subtitle={"Check the email sent to "+email+" and enter the 6-digit code."}>
    <form className="auth-form-main" onSubmit={submit}>
      <label>6-digit OTP<input className="otp-input" inputMode="numeric" value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,"").slice(0,6))} placeholder="000000" maxLength={6} autoComplete="one-time-code" required/></label>
      <button className="auth-submit" disabled={loading}>{loading?"Checking…":"Verify OTP"}<ArrowRight size={16}/></button>
    </form>
    {msg&&<div className="auth-alert">{msg}</div>}
    <p className="auth-switch"><button onClick={()=>navigate("/forgot-password")}>Request another OTP</button></p>
  </AuthShell>;
}

function ResetPasswordPage(){
  const[token,setToken]=useState(()=>sessionStorage.getItem("deep_reset_token")||"");const[pw,setPw]=useState("");const[confirm,setConfirm]=useState("");const[msg,setMsg]=useState("");const[loading,setLoading]=useState(false);
  useEffect(()=>{if(!token)navigate("/forgot-password")},[token]);
  async function submit(e:React.FormEvent){e.preventDefault();if(pw!==confirm){setMsg("Passwords do not match.");return}setLoading(true);setMsg("");try{await api.resetPassword({reset_token:token,new_password:pw});sessionStorage.removeItem("deep_reset_token");navigate("/login")}catch(err:any){setMsg(err.message)}finally{setLoading(false)}}
  return <AuthShell kind="reset" title="Create a new password" subtitle="Choose a new password and then sign in again.">
    <form className="auth-form-main" onSubmit={submit}>
      <label>New password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} minLength={8} required/></label>
      <label>Confirm password<input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} minLength={8} required/></label>
      <button className="auth-submit" disabled={loading}>{loading?"Saving…":"Reset password"}<ArrowRight size={16}/></button>
    </form>
    {msg&&<div className="auth-alert">{msg}</div>}
  </AuthShell>;
}

function footerNav(prefix:string,label:string,path:string){return <p className="switch-text">{prefix} <button className="link-button" onClick={()=>navigate(path)}>{label}</button></p>}

function WorkspaceUniverse({files}:{files:FileRecord[]}){
  const labels=(files.length?files.slice(0,5):[
    {name:"report.pdf"} as FileRecord,
    {name:"brief.docx"} as FileRecord,
    {name:"sales.xlsx"} as FileRecord,
    {name:"archive.csv"} as FileRecord,
    {name:"scan.png"} as FileRecord
  ]);
  return <div className="workspace-universe">
    <Canvas camera={{position:[0,0,7.6],fov:42}} dpr={[1,1.5]}>
      <ambientLight intensity={.6}/>
      <pointLight position={[3,4,6]} intensity={17} color="#8291ff"/>
      <pointLight position={[-4,-1,3]} intensity={8} color="#b36cff"/>
      <Stars radius={36} depth={20} count={720} factor={1.7} saturation={0} fade/>
      <ThreeSparkles count={110} scale={[11,7,8]} size={1.35} speed={.24} color="#9aaaff"/>
      <Float speed={.5} floatIntensity={.15}><DataGlobe/></Float>
    </Canvas>
    <div className="workspace-search-glass">
      <div className="search-glass-line"><Search size={19}/><span>Ask anything in your corpus...</span></div>
      <div className="workspace-type-row"><span>PDF</span><span>DOCX</span><span>XLSX</span><span>CSV</span><span>Images</span></div>
    </div>
    {labels.map((f,i)=><motion.div key={i} className={"workspace-doc wd-"+i} animate={{y:[0,i%2?9:-9,0],rotateZ:[i%2?-3:3,0,i%2?-3:3]}} transition={{duration:4.5+i*.35,repeat:Infinity,ease:"easeInOut",delay:i*.18}}>
      {iconFor(f.mime_type||"")}<div><b>{f.name}</b><small>{i===0?"source evidence":i===1?"semantic match":"indexed document"}</small></div>
    </motion.div>)}
  </div>;
}

function Dashboard(){
  const[user,setUser]=useState<any>(null);
  const[files,setFiles]=useState<FileRecord[]>([]);
  const[results,setResults]=useState<Result[]>([]);
  const[answer,setAnswer]=useState<AIAnswer|null>(null);
  const[stats,setStats]=useState<any>({files:0,chunks:0,embedded_chunks:0});
  const[selectedFile,setSelectedFile]=useState<any>(null);
  const[selectedChunks,setSelectedChunks]=useState<any[]>([]);
  const[query,setQuery]=useState("");
  const[loading,setLoading]=useState(false);
  const[uploading,setUploading]=useState(false);
  const[msg,setMsg]=useState("");
  const[filter,setFilter]=useState("All");
  const inputRef=React.useRef<HTMLInputElement>(null);

  const load=async()=>{
    try{
      const[m,f,st]=await Promise.all([api.me(),api.files(),api.stats()]);
      setUser(m.user);setFiles(f.files||[]);setStats(st);
    }catch{clearAuthToken();navigate("/login")}
  };
  useEffect(()=>{load()},[]);

  const recentSearches=useMemo(()=>{
    try{return JSON.parse(localStorage.getItem("deep_recent_searches")||"[]")}catch{return[]}
  },[results]);

  const fileTypeCounts=useMemo(()=>{
    const counts={PDF:0,DOCX:0,XLSX:0,CSV:0,Images:0,Other:0};
    for(const f of files){
      const n=(f.name||"").toLowerCase();
      if(n.endsWith(".pdf"))counts.PDF++;
      else if(n.endsWith(".docx"))counts.DOCX++;
      else if(n.endsWith(".xlsx")||n.endsWith(".xls"))counts.XLSX++;
      else if(n.endsWith(".csv"))counts.CSV++;
      else if([".png",".jpg",".jpeg"].some(x=>n.endsWith(x)))counts.Images++;
      else counts.Other++;
    }
    return counts;
  },[files]);

  const recentFiles=useMemo(()=>{
    const list=filter==="All"?files:files.filter(f=>{
      const n=f.name.toLowerCase();
      if(filter==="PDF")return n.endsWith(".pdf");
      if(filter==="DOCX")return n.endsWith(".docx");
      if(filter==="XLSX")return n.endsWith(".xlsx")||n.endsWith(".xls");
      if(filter==="CSV")return n.endsWith(".csv");
      if(filter==="Images")return [".png",".jpg",".jpeg"].some(x=>n.endsWith(x));
      return true;
    });
    return list.slice(0,6);
  },[files,filter]);

  function saveSearch(q:string){
    let old:string[]=[];
    try{old=JSON.parse(localStorage.getItem("deep_recent_searches")||"[]")}catch{}
    localStorage.setItem("deep_recent_searches",JSON.stringify([q,...old.filter(x=>x.toLowerCase()!==q.toLowerCase())].slice(0,8)));
  }

  async function deepSearch(q=query){
    if(!q.trim())return;
    setQuery(q);saveSearch(q);setLoading(true);setMsg("");
    document.getElementById("dashboard-search-results")?.scrollIntoView({behavior:"smooth",block:"start"});
    try{const d=await api.deepSearch(q,20);setResults(d.results||[]);setAnswer(d.answer||null)}
    catch(e:any){setMsg("Deep Search failed: "+e.message)}
    finally{setLoading(false)}
  }

  async function upload(e:React.ChangeEvent<HTMLInputElement>){
    const file=e.target.files?.[0];if(!file)return;
    setUploading(true);setMsg("Indexing "+file.name+"…");
    try{const d=await api.upload(file);setMsg(d.name+" indexed · "+d.chunks+" chunks · "+d.embedding_chunks+" semantic vectors");await load()}
    catch(err:any){setMsg("Indexing failed: "+err.message)}
    finally{setUploading(false);e.target.value=""}
  }

  async function openFile(id:string){
    try{const[d,c]=await Promise.all([api.file(id),api.chunks(id)]);setSelectedFile(d.file);setSelectedChunks(c.chunks||[])}
    catch(e:any){setMsg(e.message)}
  }

  async function removeFile(){
    if(!selectedFile)return;
    try{await api.deleteFile(selectedFile.id);setSelectedFile(null);await load()}
    catch(e:any){setMsg(e.message)}
  }

  function scrollSearch(){inputRef.current?.focus();window.scrollTo({top:0,behavior:"smooth"})}
  function scrollFiles(){document.getElementById("recent-files")?.scrollIntoView({behavior:"smooth"})}

  return <div className="reference-dashboard">
    <aside className="dashboard-sidebar">
      <div className="dashboard-brand"><span className="brand-glyph">◆</span><span>DEEP<span>SEARCH</span></span></div>
      <div className="sidebar-workspace"><small>PRIVATE WORKSPACE</small><b>AI FILE INTELLIGENCE</b><span>Semantic · OCR · grounded AI</span></div>
      <nav className="dashboard-nav">
        <button className="active" onClick={()=>window.scrollTo({top:0,behavior:"smooth"})}><span>⌂</span>Home</button>
        <button onClick={scrollSearch}><Search size={15}/>Search</button>
        <button onClick={scrollFiles}><FileText size={15}/>My Files</button>
        <button onClick={()=>document.getElementById("recent-files")?.scrollIntoView({behavior:"smooth"})}><RefreshCcw size={15}/>Recent</button>
        <button onClick={()=>setMsg("Sharing is available after corpus sharing is enabled for this workspace.")}><Mail size={15}/>Shared With Me</button>
        <button onClick={()=>setMsg("Favourites will appear here when you pin evidence.")}><ShieldCheck size={15}/>Favourites</button>
        <button onClick={()=>setMsg("Deleted files are removed permanently in the current demo.")}><Trash2 size={15}/>Trash</button>
      </nav>
      <div className="sidebar-storage"><small>Corpus storage</small><b>{stats.files} files indexed</b><div className="storage-bar"><span style={{width:(Math.min(100,Math.max(4,(stats.chunks||0)/5)))+"%"}}/></div><span>{stats.chunks} retrieval chunks</span></div>
      <div className="sidebar-profile" onClick={()=>{clearAuthToken();navigate("/")}}><div className="profile-avatar">{(user?.full_name||"G").slice(0,1).toUpperCase()}</div><div><b>{user?.full_name||"User"}</b><small>{user?.email||""}</small></div><LogOut size={14}/></div>
    </aside>

    <div className="dashboard-main">
      <header className="dashboard-header">
        <div><div className="dashboard-heading"><h1>DeepSearch</h1><span>PRIVATE FILE INTELLIGENCE</span></div><p>Search across PDFs, Word, Excel, CSV and images with evidence-first AI.</p></div>
        <label className="dashboard-upload">{uploading?<Activity size={15}/>:<Upload size={15}/>} {uploading?"Indexing…":"Upload Files"}<input type="file" hidden accept=".pdf,.docx,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.txt,.md" onChange={upload} disabled={uploading}/></label>
      </header>

      <section className="dashboard-search-hero">
        <div className="dashboard-searchbar">
          <Search size={19}/>
          <input ref={inputRef} value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")deepSearch()}} placeholder="Search across PDF, Word, Excel, CSV, images..." />
          <button onClick={()=>deepSearch()} disabled={loading}>{loading?"Searching…":"Search"}</button>
        </div>
        <div className="dashboard-filter-row">
          {["All","PDF","DOCX","XLSX","CSV","Images"].map(x=><button key={x} className={filter===x?"active":""} onClick={()=>setFilter(x)}>{x}</button>)}
        </div>
      </section>

      {msg&&<div className="dashboard-message"><AlertTriangle size={14}/>{msg}</div>}

      <section className="file-type-grid">
        <div className="file-type-total"><div className="file-type-icon blue"><FileText size={20}/></div><div><b>{stats.files}</b><span>Total Files</span></div></div>
        <div><div className="file-type-icon red"><FileText size={19}/></div><div><b>{fileTypeCounts.PDF}</b><span>PDF files</span></div></div>
        <div><div className="file-type-icon blue"><FileText size={19}/></div><div><b>{fileTypeCounts.DOCX}</b><span>Word</span></div></div>
        <div><div className="file-type-icon green"><Sheet size={19}/></div><div><b>{fileTypeCounts.XLSX}</b><span>Excel</span></div></div>
        <div><div className="file-type-icon orange"><Sheet size={19}/></div><div><b>{fileTypeCounts.CSV}</b><span>CSV</span></div></div>
        <div><div className="file-type-icon purple"><ImageIcon size={19}/></div><div><b>{fileTypeCounts.Images}</b><span>Images</span></div></div>
      </section>

      <section className="dashboard-grid-two">
        <div id="recent-files" className="panel-box">
          <div className="panel-heading"><div><b>Recent Files</b><span>Your latest indexed documents</span></div><button onClick={scrollFiles}>View all →</button></div>
          <div className="recent-file-list">
            {recentFiles.length?recentFiles.map(f=><button key={f.id} onClick={()=>openFile(f.id)} className="recent-file-row"><div className="recent-file-icon">{iconFor(f.mime_type||"")}</div><div><b>{f.name}</b><small>{f.mime_type||"file"} · {f.chunk_count} chunks</small></div><ChevronRight size={14}/></button>):<div className="dashboard-empty"><FileSearch size={24}/><b>No files yet</b><span>Upload your first document.</span></div>}
          </div>
        </div>

        <div className="panel-box">
          <div className="panel-heading"><div><b>Quick Actions</b><span>Jump straight into your workflow</span></div></div>
          <div className="quick-action-grid">
            <label className="quick-action blue"><Upload size={18}/><b>Upload Files</b><small>Index documents</small><input type="file" hidden accept=".pdf,.docx,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.txt,.md" onChange={upload}/></label>
            <button className="quick-action purple" onClick={scrollSearch}><Search size={18}/><b>New Search</b><small>Ask DeepSearch</small></button>
            <button className="quick-action green" onClick={scrollFiles}><FileText size={18}/><b>View Corpus</b><small>Browse indexed files</small></button>
            <button className="quick-action orange" onClick={()=>{setQuery("summarize my indexed files");deepSearch("summarize my indexed files")}}><BrainCircuit size={18}/><b>AI Summary</b><small>Grounded answer</small></button>
          </div>
        </div>
      </section>

      <section className="dashboard-grid-two lower">
        <div className="panel-box">
          <div className="panel-heading"><div><b>Corpus Overview</b><span>{stats.chunks} retrieval chunks · {stats.embedded_chunks} semantic vectors</span></div></div>
          <div className="corpus-overview">
            <div className="overview-3d"><WorkspaceUniverse files={files}/></div>
            <div className="overview-copy"><b>Every document becomes searchable.</b><p>Upload a file, let DeepSearch extract and chunk it, then search across its content using hybrid semantic and lexical retrieval.</p><button onClick={scrollSearch}>Search the corpus <ArrowRight size={13}/></button></div>
          </div>
        </div>

        <div className="panel-box">
          <div className="panel-heading"><div><b>Recent Searches</b><span>Your latest questions</span></div><button onClick={scrollSearch}>New search →</button></div>
          <div className="recent-search-list">
            {recentSearches.length?recentSearches.map((q:string,i:number)=><button key={q+i} onClick={()=>deepSearch(q)} className="recent-search-row"><RefreshCcw size={14}/><span>{q}</span><small>{i===0?"just now":(i+" ago")}</small><ArrowUpRight size={12}/></button>):<div className="dashboard-empty"><Search size={24}/><b>No searches yet</b><span>Your recent DeepSearch questions will appear here.</span></div>}
          </div>
        </div>
      </section>

      <section id="dashboard-search-results" className="dashboard-results">
        <div className="panel-heading"><div><b>Ranked Evidence & Final Answer</b><span>Retrieved chunks are shown before Groq reasoning</span></div><span>{results.length} results</span></div>
        <div className="results-and-ai">
          <div className="results-list">
            {results.length?results.map((r,i)=><article key={r.chunk_id} className="dashboard-result-card"><div className="result-rank">{String(i+1).padStart(2,"0")}</div><div><div className="result-title"><b>{r.file_name}</b><small>{r.source_ref}</small><strong>{Math.round(r.score*100)}%</strong></div><p>{r.content}</p><div className="reason-row">{(r.match_reasons||[]).slice(0,3).map(x=><span key={x}>{x}</span>)}</div><button className="text-button" onClick={()=>openFile(r.file_id)}>View evidence <ArrowUpRight size={13}/></button></div></article>):<div className="dashboard-empty"><Search size={24}/><b>No ranked evidence yet</b><span>Run a search to see the exact chunks used by AI.</span></div>}
          </div>
          <aside className="dashboard-ai">
            <div className="ai-panel-top"><div className="ai-orb"><Sparkles size={15}/></div><div><div className="eyebrow">GROUNDED AI</div><h3>Final answer</h3></div></div>
            {answer?<><div className="confidence-row"><span>Confidence</span><b>{Math.round(answer.confidence)}%</b></div><div className="confidence-bar"><span style={{width:Math.max(0,Math.min(100,answer.confidence))+"%"}}/></div><p className="ai-answer-text">{answer.answer}</p><div className="citation-block"><div className="eyebrow">CITATIONS</div>{answer.citations?.map((c:any,i:number)=><button className="citation-card" key={i} onClick={()=>openFile(c.file_id)}><FileText size={13}/><span><b>{c.file_name}</b><small>{c.source_ref}</small></span></button>)}</div></>:<div className="dashboard-ai-empty"><BrainCircuit size={24}/><b>Ask your corpus</b><span>DeepSearch retrieves evidence, then Groq explains only what those chunks support.</span></div>}
          </aside>
        </div>
      </section>
    </main>
    </div>

    <AnimatePresence>{selectedFile&&<motion.div className="drawer-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onClick={()=>setSelectedFile(null)}><motion.aside className="evidence-drawer" initial={{x:70}} animate={{x:0}} exit={{x:70}} onClick={e=>e.stopPropagation()}><div className="drawer-head"><div><div className="eyebrow">SOURCE INSPECTOR</div><h3>{selectedFile.name}</h3></div><button className="icon-button" onClick={()=>setSelectedFile(null)}><X size={17}/></button></div><div className="drawer-meta"><span>{selectedFile.status}</span><span>{selectedFile.chunk_count} chunks</span><span>{selectedFile.ocr_used?"OCR":"Text extracted"}</span></div><div className="source-list">{selectedChunks.map((c:any,i:number)=><div className="source-block" key={c.id}><div className="source-label"><span>{String(i+1).padStart(2,"0")}</span><b>{c.source_ref}</b></div><p>{c.content}</p></div>)}</div><button className="delete-file" onClick={removeFile}><Trash2 size={15}/> Delete file</button></motion.aside></motion.div>}</AnimatePresence>
  </div>;
}


function iconFor(mime:string){if(mime.includes("image"))return <ImageIcon size={18}/>;if(mime.includes("sheet")||mime.includes("csv"))return <Sheet size={18}/>;return <FileText size={18}/>}

function App(){const route=usePath();const path=route.split("?")[0];const token=sessionStorage.getItem("deep_token");useEffect(()=>{if(path==="/dashboard"&&!sessionStorage.getItem("deep_token"))navigate("/login");if(["/login","/register","/forgot-password"].includes(path)&&token)navigate("/dashboard")},[path,token]);
  if(path==="/"||path==="/about")return <HomePage/>;if(path==="/login")return <LoginPage/>;if(path==="/register")return <RegisterPage/>;if(path==="/check-email")return <CheckEmailPage/>;if(path==="/verify-email")return <VerifyEmailPage/>;if(path==="/forgot-password")return <ForgotPasswordPage/>;if(path==="/verify-reset")return <VerifyResetPage/>;if(path==="/reset-password")return <ResetPasswordPage/>;if(path==="/dashboard")return <Dashboard/>;return <HomePage/>}
createRoot(document.getElementById("root")!).render(<App/>);
