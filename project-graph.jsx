import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import * as d3 from "d3";

const PORT = 7477;
const TC = { entry:"#f97316",blueprint:"#6366f1",route:"#22d3ee",model:"#a78bfa",template:"#34d399",static:"#fbbf24",config:"#f43f5e",util:"#94a3b8",auth:"#e879f9",db:"#fb923c",api:"#38bdf8",default:"#64748b" };
const TL = { entry:"Entry Point",blueprint:"Blueprint",route:"Ruta",model:"Modelo",template:"Template",static:"Static",config:"Config",util:"Utilidad",auth:"Auth",db:"Base de datos",api:"API",default:"Archivo" };
const EC = { registers:"#f97316",imports:"#94a3b8",contains:"#6366f1",queries:"#22d3ee",persists:"#fb923c",renders:"#34d399",extends:"#34d399",calls:"#38bdf8",uses:"#e879f9",loads:"#fbbf24",configures:"#f43f5e",manages:"#fb923c",belongs_to:"#a78bfa",references:"#a78bfa",default:"#334155" };
const ICONS = { entry:"▶",blueprint:"◈",route:"⬡",model:"◉",template:"▣",static:"◆",config:"⚙",util:"⬟",auth:"⬠",db:"⬡",api:"◈",default:"●" };
const SC = { pass:"#34d399",fail:"#f43f5e",warn:"#fbbf24",running:"#22d3ee",skip:"#475569",unknown:"#334155" };
const SI = { pass:"✓",fail:"✗",warn:"⚠",running:"◌",skip:"—",unknown:"?" };

const BOLAO = {
  nodes:[
    {id:"app.py",type:"entry",label:"app.py",desc:"Flask entry — registra blueprints",functions:[{name:"create_app",line:8,args:[],async:false,decorators:[]},{name:"init_db",line:22,args:["app"],async:false,decorators:[]}],classes:[],lines:45,routes:[]},
    {id:"config.py",type:"config",label:"config.py",desc:"SECRET_KEY, DB path, reglas",functions:[],classes:[{name:"Config",line:4,methods:[]},{name:"DevelopmentConfig",line:18,methods:[]}],lines:32,routes:[]},
    {id:"database.py",type:"db",label:"database.py",desc:"SQLite init, create_tables()",functions:[{name:"get_db",line:12,args:[],async:false,decorators:[]},{name:"create_tables",line:20,args:["db"],async:false,decorators:[]},{name:"close_db",line:45,args:["e"],async:false,decorators:["teardown_appcontext"]}],classes:[],lines:60,routes:[]},
    {id:"blueprints/public.py",type:"blueprint",label:"blueprints/public.py",desc:"Login, registro, vista pools",functions:[{name:"index",line:15,args:[],async:false,decorators:["public_bp.route('/')"]},{name:"pool_view",line:28,args:["pool_id"],async:false,decorators:["public_bp.route('/pool/<int:pool_id>')"]}],classes:[],lines:85,routes:["public_bp.route('/')","public_bp.route('/pool/<int:pool_id>')"]},
    {id:"blueprints/admin.py",type:"blueprint",label:"blueprints/admin.py",desc:"CRUD partidos, usuarios",functions:[{name:"dashboard",line:12,args:[],async:false,decorators:["admin_bp.route('/admin')","login_required"]}],classes:[],lines:120,routes:["admin_bp.route('/admin')"]},
    {id:"blueprints/api.py",type:"blueprint",label:"blueprints/api.py",desc:"REST — leaderboard, stats",functions:[{name:"place_bet",line:18,args:[],async:false,decorators:["api_bp.route('/api/bet','POST')","login_required"]},{name:"get_leaderboard",line:45,args:[],async:false,decorators:["api_bp.route('/api/leaderboard')"]}],classes:[],lines:110,routes:["api_bp.route('/api/leaderboard')"]},
    {id:"blueprints/auth.py",type:"auth",label:"blueprints/auth.py",desc:"Firebase verify_token",functions:[{name:"login_required",line:8,args:["f"],async:false,decorators:[]},{name:"verify_token",line:22,args:["token"],async:false,decorators:[]}],classes:[],lines:65,routes:[]},
    {id:"models/user.py",type:"model",label:"models/user.py",desc:"User — R$5 bonus, VIP 1.2x",functions:[{name:"create",line:15,args:["uid","email"],async:false,decorators:[]},{name:"get_by_uid",line:28,args:["uid"],async:false,decorators:[]}],classes:[{name:"User",line:8,methods:["create","get_by_uid","get_balance"]}],lines:75,routes:[]},
    {id:"models/pool.py",type:"model",label:"models/pool.py",desc:"Pool — rake 20%, jackpot 2%",functions:[{name:"create",line:18,args:["match_id"],async:false,decorators:[]},{name:"calculate_rake",line:50,args:["amount"],async:false,decorators:[]}],classes:[{name:"Pool",line:10,methods:["create","close_betting","calculate_rake"]}],lines:90,routes:[]},
    {id:"models/bet.py",type:"model",label:"models/bet.py",desc:"Bet — R$20-200, odds 10x",functions:[{name:"place",line:12,args:["user_id","pool_id","amount"],async:false,decorators:[]},{name:"validate_amount",line:30,args:["amount"],async:false,decorators:[]}],classes:[{name:"Bet",line:6,methods:["place","validate_amount"]}],lines:80,routes:[]},
    {id:"models/match.py",type:"model",label:"models/match.py",desc:"Match — equipos, resultado",functions:[{name:"create",line:10,args:["home","away","date"],async:false,decorators:[]},{name:"set_result",line:25,args:["match_id","h","a"],async:false,decorators:[]}],classes:[{name:"Match",line:5,methods:["create","set_result"]}],lines:55,routes:[]},
    {id:"static/js/main.js",type:"static",label:"static/js/main.js",desc:"ES6 root — módulos",functions:[{name:"initApp",line:5,args:[],async:false,decorators:[]}],classes:[],lines:35,routes:[]},
    {id:"static/js/bet.js",type:"static",label:"static/js/bet.js",desc:"Validación, submit, odds",functions:[{name:"submitBet",line:8,args:["poolId","amount"],async:true,decorators:[]},{name:"validateBetAmount",line:22,args:["amount"],async:false,decorators:[]}],classes:[],lines:65,routes:[]},
    {id:"static/js/auth.js",type:"static",label:"static/js/auth.js",desc:"Firebase client — login",functions:[{name:"signInWithEmail",line:6,args:["email","password"],async:true,decorators:[]},{name:"getIdToken",line:18,args:[],async:true,decorators:[]}],classes:[],lines:45,routes:[]},
    {id:"static/js/pool.js",type:"static",label:"static/js/pool.js",desc:"Lista pools, filtros",functions:[{name:"fetchActivePools",line:5,args:[],async:true,decorators:[]},{name:"renderPoolCard",line:20,args:["pool"],async:false,decorators:[]}],classes:[],lines:55,routes:[]},
    {id:"templates/base.html",type:"template",label:"templates/base.html",desc:"Layout — navbar, flash",functions:[],classes:[],lines:80,routes:[]},
    {id:"templates/index.html",type:"template",label:"templates/index.html",desc:"Home — pools activos",functions:[],classes:[],lines:60,routes:[]},
    {id:"templates/pool.html",type:"template",label:"templates/pool.html",desc:"Vista pool — apuestas",functions:[],classes:[],lines:90,routes:[]},
    {id:"firebase_admin_sdk",type:"auth",label:"firebase_admin SDK",desc:"Verificación server-side",functions:[],classes:[],lines:0,routes:[]},
    {id:"bolao.db",type:"db",label:"bolao.db (SQLite)",desc:"users, pools, bets, matches",functions:[],classes:[],lines:0,routes:[]},
  ],
  edges:[
    {source:"app.py",target:"blueprints/public.py",type:"registers"},{source:"app.py",target:"blueprints/admin.py",type:"registers"},
    {source:"app.py",target:"blueprints/api.py",type:"registers"},{source:"app.py",target:"blueprints/auth.py",type:"registers"},
    {source:"app.py",target:"config.py",type:"imports"},{source:"app.py",target:"database.py",type:"imports"},
    {source:"blueprints/auth.py",target:"firebase_admin_sdk",type:"uses"},
    {source:"blueprints/public.py",target:"models/pool.py",type:"queries"},{source:"blueprints/public.py",target:"models/bet.py",type:"queries"},
    {source:"blueprints/admin.py",target:"models/match.py",type:"queries"},{source:"blueprints/admin.py",target:"models/user.py",type:"queries"},
    {source:"blueprints/api.py",target:"models/bet.py",type:"queries"},{source:"blueprints/api.py",target:"models/pool.py",type:"queries"},
    {source:"models/bet.py",target:"bolao.db",type:"persists"},{source:"models/pool.py",target:"bolao.db",type:"persists"},
    {source:"models/user.py",target:"bolao.db",type:"persists"},{source:"models/match.py",target:"bolao.db",type:"persists"},
    {source:"database.py",target:"bolao.db",type:"manages"},{source:"models/bet.py",target:"models/pool.py",type:"belongs_to"},
    {source:"models/pool.py",target:"models/match.py",type:"references"},
    {source:"blueprints/public.py",target:"templates/index.html",type:"renders"},{source:"blueprints/public.py",target:"templates/pool.html",type:"renders"},
    {source:"templates/index.html",target:"templates/base.html",type:"extends"},{source:"templates/pool.html",target:"templates/base.html",type:"extends"},
    {source:"static/js/main.js",target:"static/js/bet.js",type:"imports"},{source:"static/js/main.js",target:"static/js/auth.js",type:"imports"},{source:"static/js/main.js",target:"static/js/pool.js",type:"imports"},
    {source:"static/js/bet.js",target:"blueprints/api.py",type:"calls"},{source:"static/js/auth.js",target:"blueprints/auth.py",type:"calls"},
    {source:"templates/base.html",target:"static/js/main.js",type:"loads"},
    {source:"config.py",target:"models/pool.py",type:"configures"},{source:"config.py",target:"models/bet.py",type:"configures"},
  ],
};

// ── Simulación de tests (sin scanner real) ────────────────────────────────────
function simulateTest(node) {
  return new Promise(resolve => {
    setTimeout(() => {
      const r = Math.random();
      const statusMap = { entry:r>.1?"pass":"fail", blueprint:r>.1?"pass":"warn", route:r>.25?"pass":r>.1?"warn":"fail", model:r>.15?"pass":"fail", auth:r>.2?"warn":"pass", config:r>.1?"pass":"warn", db:r>.2?"pass":"fail", static:r>.05?"pass":"warn", template:r>.08?"pass":"warn", api:r>.2?"pass":r>.1?"warn":"fail", default:"pass" };
      const status = statusMap[node.type] || "pass";
      const ms = Math.floor(Math.random()*280)+20;
      const checksByType = {
        entry:    [["Archivo existe",true,""],["Sintaxis Python válida",status!=="fail",status==="fail"?"SyntaxError: unexpected EOF":""],["Import sin errores",status==="pass",status!=="pass"?"ModuleNotFoundError":""]],
        blueprint:[["Archivo existe",true,""],["Sintaxis Python válida",status!=="fail",""],["Blueprint registrado",status==="pass",status!=="pass"?"Blueprint no registrado en app":""],["Rutas accesibles",status==="pass",""]],
        route:    [["Archivo existe",true,""],["Sintaxis Python válida",true,""],["HTTP / (200 OK)",status==="pass",status!=="pass"?"Connection refused — ¿Flask corriendo?":"200 OK"],["HTTP /pool/1",status!=="fail",status==="fail"?"404 Not Found":"200 OK"]],
        model:    [["Archivo existe",true,""],["Sintaxis Python válida",status!=="fail",status==="fail"?"SyntaxError":""],["Import sin errores",status==="pass",status!=="pass"?"ImportError: cannot import name 'User'":""],["Clase definida",status==="pass",""]],
        db:       [["SQLite conecta",status!=="fail",status==="fail"?"OperationalError: unable to open database":""],["Tablas encontradas",status==="pass",status!=="pass"?"no such table: users":"users, pools, bets, matches"],["Integridad DB",status==="pass",""]],
        config:   [["Archivo existe",true,""],["Variable SECRET_KEY",status!=="fail",status==="fail"?"No definida en config":"Encontrada"],["Variable DATABASE",status==="pass",status!=="pass"?"No definida":"Encontrada"]],
        auth:     [["Archivo existe",true,""],["Firebase config presente",status!=="fail",status==="fail"?"firebase_admin no inicializado":""],["verify_token callable",status==="pass",""]],
        static:   [["Archivo existe",status!=="fail",status==="fail"?"FileNotFoundError":""],["Sin errores JS",status!=="fail",status==="fail"?"SyntaxError: Unexpected token":""]],
        template: [["Archivo existe",true,""],["Jinja2 syntax válido",status!=="fail",status==="fail"?"TemplateSyntaxError: unexpected end of template":""]],
        api:      [["Archivo existe",true,""],["Sintaxis Python válida",status!=="fail",""],["GET /api/leaderboard",status==="pass",status!=="pass"?"500 Internal Server Error":"200 OK · 12ms"]],
      };
      const rawChecks = checksByType[node.type] || [["Archivo existe",status!=="fail",""]];
      const checks = rawChecks.map(([name,ok,detail]) => ({name,ok,detail:ok?(detail||"OK"):detail}));
      const passed = checks.filter(c=>c.ok).length;
      resolve({ node_id:node.id, status, checks, ms, summary:`${passed}/${checks.length} checks OK`, simulated:true });
    }, 300 + Math.random()*700);
  });
}

// ── Grafo D3 ──────────────────────────────────────────────────────────────────
function GraphCanvas({ graphData, filterType, filterEdge, onSelectNode, testResults, selectedId }) {
  const svgRef = useRef(null);
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    const W = svgRef.current?.clientWidth||800, H = svgRef.current?.clientHeight||480;
    const vn = filterType==="all" ? graphData.nodes : graphData.nodes.filter(n=>n.type===filterType);
    const vids = new Set(vn.map(n=>n.id));
    const ve = graphData.edges.filter(e=>vids.has(e.source?.id||e.source)&&vids.has(e.target?.id||e.target)&&(filterEdge==="all"||e.type===filterEdge));
    const nodes = vn.map(n=>({...n}));
    const links = ve.map(e=>({...e,source:e.source?.id||e.source,target:e.target?.id||e.target}));
    const defs = svg.append("defs");
    Object.entries(EC).forEach(([t,c])=>{
      defs.append("marker").attr("id",`arr-${t}`).attr("viewBox","0 -4 10 8").attr("refX",20).attr("refY",0).attr("markerWidth",5).attr("markerHeight",5).attr("orient","auto").append("path").attr("d","M0,-4L10,0L0,4").attr("fill",c).attr("opacity",0.7);
    });
    ["pass","fail","warn","running","unknown"].forEach(s=>{
      const f=defs.append("filter").attr("id",`glow-${s}`);
      f.append("feGaussianBlur").attr("stdDeviation",s==="fail"?"5":s==="pass"?"3":"4").attr("result","blur");
      const fm=f.append("feMerge"); fm.append("feMergeNode").attr("in","blur"); fm.append("feMergeNode").attr("in","SourceGraphic");
    });
    defs.append("pattern").attr("id","dots").attr("width",24).attr("height",24).attr("patternUnits","userSpaceOnUse")
      .append("circle").attr("cx",1).attr("cy",1).attr("r",0.8).attr("fill","#1e293b");
    svg.append("rect").attr("width",W).attr("height",H).attr("fill","url(#dots)");
    const g = svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.15,4]).on("zoom",e=>g.attr("transform",e.transform)));
    const sim = d3.forceSimulation(nodes)
      .force("link",d3.forceLink(links).id(d=>d.id).distance(130).strength(0.5))
      .force("charge",d3.forceManyBody().strength(-330))
      .force("center",d3.forceCenter(W/2,H/2))
      .force("collision",d3.forceCollide().radius(40));
    const link = g.append("g").selectAll("line").data(links).join("line")
      .attr("stroke",d=>EC[d.type]||EC.default).attr("stroke-width",1.5).attr("stroke-opacity",0.4)
      .attr("marker-end",d=>`url(#arr-${d.type})`);
    const ll = g.append("g").selectAll("text").data(links.length<22?links:[]).join("text")
      .attr("font-size",7).attr("fill",d=>EC[d.type]||EC.default).attr("opacity",0.4).attr("text-anchor","middle").text(d=>d.type);
    const node = g.append("g").selectAll("g").data(nodes).join("g").attr("cursor","pointer")
      .call(d3.drag()
        .on("start",(e,d)=>{if(!e.active)sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;})
        .on("drag",(e,d)=>{d.fx=e.x;d.fy=e.y;})
        .on("end",(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;})
      ).on("click",(e,d)=>{e.stopPropagation();onSelectNode(d);});

    // Anillo de status
    node.append("circle").attr("r",21).attr("fill","none")
      .attr("stroke",d=>{ const r=testResults[d.id]; return r?SC[r.status]:"transparent"; })
      .attr("stroke-width",d=>testResults[d.id]?2:0).attr("opacity",0.85);

    // Círculo principal
    node.append("circle").attr("r",16)
      .attr("fill",d=>(TC[d.type]||TC.default)+(selectedId===d.id?"44":"22"))
      .attr("stroke",d=>{ const r=testResults[d.id]; return r&&r.status!=="unknown"?SC[r.status]:TC[d.type]||TC.default; })
      .attr("stroke-width",d=>selectedId===d.id?2.5:1.5)
      .attr("filter",d=>{ const r=testResults[d.id]; return `url(#glow-${r?.status||"unknown"})`; });

    // Icono
    node.append("text").attr("text-anchor","middle").attr("dominant-baseline","central")
      .attr("font-size",11).attr("fill",d=>TC[d.type]||TC.default).text(d=>ICONS[d.type]||ICONS.default);

    // Badge status (arriba derecha)
    node.filter(d=>!!testResults[d.id]).append("text")
      .attr("x",13).attr("y",-11).attr("font-size",9).attr("text-anchor","middle")
      .attr("fill",d=>SC[testResults[d.id]?.status]||"transparent")
      .text(d=>SI[testResults[d.id]?.status]||"");

    // Label
    node.append("text").attr("text-anchor","middle").attr("y",28).attr("font-size",8.5)
      .attr("fill","#94a3b8").attr("font-family","'JetBrains Mono',monospace")
      .text(d=>d.label?.length>20?d.label.slice(0,18)+"…":d.label);

    svg.on("click",()=>onSelectNode(null));
    sim.on("tick",()=>{
      link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
      ll.attr("x",d=>(d.source.x+d.target.x)/2).attr("y",d=>(d.source.y+d.target.y)/2);
      node.attr("transform",d=>`translate(${d.x},${d.y})`);
    });
    return ()=>sim.stop();
  },[graphData,filterType,filterEdge,onSelectNode,testResults,selectedId]);
  return <svg ref={svgRef} width="100%" height="100%" style={{minHeight:440}}/>;
}

// ── Panel de test de nodo ─────────────────────────────────────────────────────
function TestPanel({ node, result, onTest, scannerOk }) {
  const running = result?.status==="running";
  return (
    <div style={{padding:"10px 12px",borderTop:"1px solid #1a2332"}}>
      <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:7}}>
        <span style={{fontSize:8,color:"#475569",letterSpacing:1,flex:1}}>HEALTH CHECK</span>
        {!scannerOk&&<span style={{fontSize:7,color:"#334155"}}>modo simulado</span>}
        <button onClick={()=>onTest(node)} disabled={running}
          style={{background:running?"#1a2332":"#34d39922",border:`1px solid ${running?"#1a2332":"#34d399"}`,color:running?"#334155":"#34d399",padding:"3px 10px",borderRadius:5,fontSize:9,cursor:running?"not-allowed":"pointer",fontFamily:"inherit"}}>
          {running?"◌ Testeando…":"▶ Testear"}
        </button>
      </div>
      {running&&<div style={{fontSize:9,color:"#22d3ee",padding:"6px 0",animation:"pulse 1s ease-in-out infinite"}}>Ejecutando checks…</div>}
      {result&&result.status!=="running"&&(
        <>
          <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:8,padding:"5px 8px",background:SC[result.status]+"11",borderRadius:6,border:`1px solid ${SC[result.status]}44`}}>
            <span style={{fontSize:14,color:SC[result.status]}}>{SI[result.status]}</span>
            <div>
              <div style={{fontSize:10,fontWeight:700,color:SC[result.status]}}>{result.status.toUpperCase()}</div>
              <div style={{fontSize:7.5,color:"#475569"}}>{result.summary} · {result.ms}ms{result.simulated?" · sim":""}</div>
            </div>
          </div>
          {result.checks.map((c,i)=>(
            <div key={i} style={{display:"flex",gap:6,padding:"3px 0",borderBottom:"1px solid #0d1a26",alignItems:"flex-start"}}>
              <span style={{fontSize:9,color:c.ok?"#34d399":"#f43f5e",flexShrink:0,marginTop:1}}>{c.ok?"✓":"✗"}</span>
              <div>
                <div style={{fontSize:8.5,color:c.ok?"#64748b":"#e2e8f0"}}>{c.name}</div>
                {!c.ok&&c.detail&&<div style={{fontSize:7.5,color:"#f43f5e",wordBreak:"break-all",marginTop:1}}>{c.detail}</div>}
                {c.ok&&c.detail&&c.detail!=="OK"&&<div style={{fontSize:7.5,color:"#334155",marginTop:1}}>{c.detail}</div>}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [projects,setProjects] = useState([{id:1,name:"Bolão BRF",data:BOLAO}]);
  const [activeId,setActiveId] = useState(1);
  const [view,setView] = useState("graph");
  const [selectedNode,setSelectedNode] = useState(null);
  const [filterType,setFilterType] = useState("all");
  const [filterEdge,setFilterEdge] = useState("all");
  const [showAdd,setShowAdd] = useState(false);
  const [addMode,setAddMode] = useState("tree");
  const [inputText,setInputText] = useState("");
  const [projName,setProjName] = useState("");
  const [localPath,setLocalPath] = useState("");
  const [baseUrl,setBaseUrl] = useState("http://localhost:5000");
  const [scannerOk,setScannerOk] = useState(false);
  const [loading,setLoading] = useState(false);
  const [statusMsg,setStatusMsg] = useState("");
  const [testResults,setTestResults] = useState({});
  const [runningAll,setRunningAll] = useState(false);
  const [testFilter,setTestFilter] = useState("all");

  const gd = projects.find(p=>p.id===activeId)?.data || BOLAO;
  const nodeTypes = useMemo(()=>[...new Set(gd.nodes.map(n=>n.type))],[gd]);
  const edgeTypes = useMemo(()=>[...new Set(gd.edges.map(e=>e.type))],[gd]);
  const conns = selectedNode ? gd.edges.filter(e=>(e.source?.id||e.source)===selectedNode.id||(e.target?.id||e.target)===selectedNode.id) : [];
  const testStats = useMemo(()=>{
    const v=Object.values(testResults);
    return {total:v.length,pass:v.filter(r=>r.status==="pass").length,fail:v.filter(r=>r.status==="fail").length,warn:v.filter(r=>r.status==="warn").length,running:v.filter(r=>r.status==="running").length};
  },[testResults]);

  // Ping scanner
  useEffect(()=>{
    const check=async()=>{ try{ const r=await fetch(`http://localhost:${PORT}/ping`,{signal:AbortSignal.timeout(2000)}); setScannerOk(r.ok); }catch{ setScannerOk(false); } };
    check(); const t=setInterval(check,10000); return()=>clearInterval(t);
  },[]);

  const toast=(msg,dur=3500)=>{ setStatusMsg(msg); setTimeout(()=>setStatusMsg(""),dur); };
  const switchProj=useCallback((id)=>{ setActiveId(id); setSelectedNode(null); setFilterType("all"); setFilterEdge("all"); setTestResults({}); },[]);
  const removeProj=useCallback((e,id)=>{ e.stopPropagation(); if(projects.length===1)return; const r=projects.filter(p=>p.id!==id); setProjects(r); if(activeId===id)switchProj(r[0].id); },[projects,activeId,switchProj]);

  const testNode=useCallback(async(node)=>{
    setTestResults(p=>({...p,[node.id]:{status:"running",checks:[],ms:0,summary:""}}));
    let result;
    if(scannerOk){
      try{
        const r=await fetch(`http://localhost:${PORT}/test?node=${encodeURIComponent(node.id)}&root=${encodeURIComponent(localPath||".")}`,{signal:AbortSignal.timeout(15000)});
        result=await r.json();
      }catch{ result=await simulateTest(node); }
    } else { result=await simulateTest(node); }
    setTestResults(p=>({...p,[node.id]:result}));
  },[scannerOk,localPath]);

  const testAll=useCallback(async()=>{
    setRunningAll(true);
    const init={}; gd.nodes.forEach(n=>{ init[n.id]={status:"running",checks:[],ms:0,summary:""}; }); setTestResults(init);
    for(let i=0;i<gd.nodes.length;i+=4){
      const batch=gd.nodes.slice(i,i+4);
      await Promise.all(batch.map(async n=>{
        let result;
        if(scannerOk){ try{ const r=await fetch(`http://localhost:${PORT}/test?node=${encodeURIComponent(n.id)}&root=${encodeURIComponent(localPath||".")}`,{signal:AbortSignal.timeout(15000)}); result=await r.json(); }catch{ result=await simulateTest(n); } }
        else { result=await simulateTest(n); }
        setTestResults(p=>({...p,[n.id]:result}));
      }));
    }
    setRunningAll(false); toast("✓ Tests completados");
  },[gd,scannerOk,localPath]);

  const addByTree=useCallback(async()=>{
    if(!inputText.trim())return; setLoading(true);
    try{
      const r=await fetch("https://api.anthropic.com/v1/messages",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"claude-sonnet-4-20250514",max_tokens:5000,system:`Analiza estructura. Devuelve SOLO JSON: {"nodes":[{"id":"id","type":"entry|blueprint|route|model|template|static|config|util|auth|db|api|default","label":"str","desc":"str","functions":[{"name":"str","line":1,"args":[],"async":false,"decorators":[]}],"classes":[{"name":"str","line":1,"methods":[]}],"lines":0,"routes":[]}],"edges":[{"source":"id","target":"id","type":"imports|calls|extends|renders|queries|persists|registers|contains|uses|manages|configures|belongs_to|references|loads"}]} Mínimo 10 nodos y 15 aristas.`,messages:[{role:"user",content:`Proyecto: ${projName}\n\n${inputText}`}]})});
      const data=await r.json(); const txt=data.content?.find(b=>b.type==="text")?.text||"";
      const parsed=JSON.parse(txt.replace(/```json|```/g,"").trim());
      if(parsed.nodes&&parsed.edges){ const nid=Date.now(); const name=projName.trim()||`Proyecto ${projects.length+1}`; setProjects(p=>[...p,{id:nid,name,data:parsed}]); switchProj(nid); setShowAdd(false); setInputText(""); setProjName(""); toast(`✓ "${name}" — ${parsed.nodes.length} nodos`); }
    }catch{ toast("⚠ Error al analizar"); }
    setLoading(false);
  },[inputText,projName,projects.length,switchProj]);

  const addByJSON=useCallback(()=>{ try{ const p=JSON.parse(inputText); if(!p.nodes||!p.edges)throw 0; const nid=Date.now(); const name=projName.trim()||`Proyecto ${projects.length+1}`; setProjects(prev=>[...prev,{id:nid,name,data:p}]); switchProj(nid); setShowAdd(false); setInputText(""); setProjName(""); toast(`✓ "${name}" cargado`); }catch{ toast("⚠ JSON inválido"); } },[inputText,projName,projects.length,switchProj]);

  const connectLocal=useCallback(async()=>{
    try{ const ping=await fetch(`http://localhost:${PORT}/ping`,{signal:AbortSignal.timeout(3000)}); if(!ping.ok)throw 0; setScannerOk(true); const r=await fetch(`http://localhost:${PORT}/scan?path=${encodeURIComponent(localPath||".")}`); const parsed=await r.json();
      if(parsed.nodes&&parsed.edges){ const nid=Date.now(); const name=projName.trim()||parsed.meta?.root?.split("/").pop()||`Proyecto ${projects.length+1}`; setProjects(p=>[...p,{id:nid,name,data:parsed}]); switchProj(nid); setShowAdd(false); setProjName(""); toast(`✓ "${name}" — ${parsed.nodes.length} nodos`); }
    }catch{ toast("⚠ Scanner no responde"); }
  },[localPath,projName,projects.length,switchProj]);

  const btn=(active,accent="#6366f1")=>({background:active?`${accent}22`:"transparent",border:`1px solid ${active?accent:"#1e293b"}`,color:active?accent:"#475569",padding:"4px 10px",borderRadius:5,fontSize:9,cursor:"pointer",fontFamily:"inherit"});

  const testViewNodes = useMemo(()=>testFilter==="all"?gd.nodes:gd.nodes.filter(n=>testResults[n.id]?.status===testFilter),[gd,testResults,testFilter]);

  return (
    <div style={{background:"#070c17",minHeight:"100vh",fontFamily:"'JetBrains Mono','Fira Code',monospace",color:"#e2e8f0",display:"flex",flexDirection:"column",fontSize:12}}>
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}} @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>

      {/* Header */}
      <div style={{padding:"8px 14px",borderBottom:"1px solid #1a2332",display:"flex",alignItems:"center",gap:8,background:"#0a1020",flexWrap:"wrap"}}>
        <div style={{display:"flex",alignItems:"center",gap:7}}>
          <div style={{width:26,height:26,borderRadius:6,background:"linear-gradient(135deg,#6366f1,#22d3ee)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:12}}>⬡</div>
          <div>
            <div style={{fontSize:11,fontWeight:700,color:"#f1f5f9",letterSpacing:1}}>PROJECT GRAPH</div>
            <div style={{fontSize:7,color:"#334155",letterSpacing:2}}>DEPENDENCY + HEALTH MONITOR</div>
          </div>
        </div>
        <div style={{display:"flex",gap:3,marginLeft:8}}>
          {[["graph","⬡ Grafo"],["tests",`⚑ Tests${testStats.fail>0?` ✗${testStats.fail}`:testStats.pass>0?` ✓${testStats.pass}`:""}`],["explorer","⊞ Archivos"],["setup","⚙ Setup"]].map(([v,l])=>(
            <button key={v} onClick={()=>setView(v)} style={{...btn(view===v,v==="tests"&&testStats.fail>0?"#f43f5e":"#6366f1"),fontSize:8}}>{l}</button>
          ))}
        </div>
        <div style={{display:"flex",alignItems:"center",gap:5,padding:"3px 8px",background:scannerOk?"#34d39911":"#f43f5e11",border:`1px solid ${scannerOk?"#34d39933":"#f43f5e33"}`,borderRadius:5}}>
          <div style={{width:5,height:5,borderRadius:"50%",background:scannerOk?"#34d399":"#f43f5e",animation:scannerOk?"pulse 2s infinite":"none"}}/>
          <span style={{fontSize:7.5,color:scannerOk?"#34d399":"#f43f5e"}}>{scannerOk?"Scanner activo":"Scanner offline"}</span>
        </div>
        {view==="graph"&&(
          <div style={{display:"flex",gap:4,marginLeft:"auto"}}>
            <select value={filterType} onChange={e=>setFilterType(e.target.value)} style={{background:"#1a2332",border:"1px solid #1e293b",color:"#64748b",padding:"3px 6px",borderRadius:4,fontSize:8,cursor:"pointer"}}>
              <option value="all">Todos</option>
              {nodeTypes.map(t=><option key={t} value={t}>{TL[t]||t}</option>)}
            </select>
            <select value={filterEdge} onChange={e=>setFilterEdge(e.target.value)} style={{background:"#1a2332",border:"1px solid #1e293b",color:"#64748b",padding:"3px 6px",borderRadius:4,fontSize:8,cursor:"pointer"}}>
              <option value="all">Todas aristas</option>
              {edgeTypes.map(t=><option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        )}
        <button onClick={()=>setShowAdd(!showAdd)} style={{...btn(false),background:showAdd?"#1a2332":"linear-gradient(135deg,#6366f1,#22d3ee)",color:"#fff",border:"none",marginLeft:view!=="graph"?"auto":0,fontSize:9}}>
          {showAdd?"✕":"+ Proyecto"}
        </button>
        {statusMsg&&<div style={{fontSize:8,color:statusMsg.startsWith("⚠")?"#f43f5e":"#34d399"}}>{statusMsg}</div>}
      </div>

      {/* Tabs */}
      <div style={{display:"flex",gap:2,padding:"4px 10px",background:"#060b14",borderBottom:"1px solid #1a2332",overflowX:"auto",alignItems:"center"}}>
        {projects.map(p=>(
          <div key={p.id} onClick={()=>switchProj(p.id)} style={{display:"flex",alignItems:"center",gap:4,padding:"3px 10px",borderRadius:5,cursor:"pointer",whiteSpace:"nowrap",background:activeId===p.id?"#1a2332":"transparent",border:activeId===p.id?"1px solid #334155":"1px solid transparent",color:activeId===p.id?"#e2e8f0":"#475569",fontSize:9}}>
            <span style={{color:activeId===p.id?"#6366f1":"#334155",fontSize:7}}>◈</span>
            {p.name}
            {activeId===p.id&&testStats.total>0&&<span style={{fontSize:7,color:testStats.fail>0?"#f43f5e":"#34d399",marginLeft:2}}>{testStats.fail>0?`✗${testStats.fail}`:`✓${testStats.pass}`}</span>}
            {projects.length>1&&<span onClick={e=>removeProj(e,p.id)} style={{fontSize:8,color:"#334155",cursor:"pointer"}} onMouseEnter={e=>e.target.style.color="#f43f5e"} onMouseLeave={e=>e.target.style.color="#334155"}>✕</span>}
          </div>
        ))}
        <div onClick={()=>setShowAdd(true)} style={{padding:"3px 8px",borderRadius:5,cursor:"pointer",fontSize:8,color:"#334155",border:"1px dashed #1a2332",marginLeft:2}} onMouseEnter={e=>e.currentTarget.style.color="#6366f1"} onMouseLeave={e=>e.currentTarget.style.color="#334155"}>+ agregar</div>
      </div>

      {/* Panel agregar */}
      {showAdd&&(
        <div style={{padding:12,background:"#0a1020",borderBottom:"1px solid #1a2332"}}>
          <div style={{display:"flex",gap:3,marginBottom:8}}>
            {[["tree","🌲 Árbol (Claude)"],["json","{ } JSON"],["local","🔌 Scanner local"]].map(([m,l])=>(
              <button key={m} onClick={()=>setAddMode(m)} style={{...btn(addMode===m),fontSize:8}}>{l}</button>
            ))}
          </div>
          <input value={projName} onChange={e=>setProjName(e.target.value)} placeholder="Nombre del proyecto" style={{width:"100%",background:"#070c17",border:"1px solid #1e293b",borderRadius:4,color:"#e2e8f0",padding:"4px 8px",fontSize:9,marginBottom:5,boxSizing:"border-box",fontFamily:"inherit"}}/>
          {addMode==="tree"&&<>
            <textarea value={inputText} onChange={e=>setInputText(e.target.value)} placeholder="Output de `tree -I '__pycache__|node_modules'`" style={{width:"100%",height:85,background:"#070c17",border:"1px solid #1e293b",borderRadius:4,color:"#e2e8f0",padding:7,fontSize:9,resize:"vertical",fontFamily:"inherit",boxSizing:"border-box"}}/>
            <button onClick={addByTree} disabled={loading||!inputText.trim()} style={{...btn(false),background:loading?"#1a2332":"linear-gradient(135deg,#6366f1,#22d3ee)",color:loading?"#334155":"#fff",border:"none",marginTop:5,fontSize:9}}>{loading?"Analizando...":"⬡ Analizar con Claude"}</button>
          </>}
          {addMode==="json"&&<>
            <textarea value={inputText} onChange={e=>setInputText(e.target.value)} placeholder='{"nodes":[...],"edges":[...]}' style={{width:"100%",height:85,background:"#070c17",border:"1px solid #1e293b",borderRadius:4,color:"#e2e8f0",padding:7,fontSize:9,resize:"vertical",fontFamily:"inherit",boxSizing:"border-box"}}/>
            <button onClick={addByJSON} disabled={!inputText.trim()} style={{...btn(false,"#6366f1"),background:"#6366f122",marginTop:5,fontSize:9}}>⬡ Cargar</button>
          </>}
          {addMode==="local"&&<>
            <input value={localPath} onChange={e=>setLocalPath(e.target.value)} placeholder="/ruta/del/proyecto" style={{width:"100%",background:"#070c17",border:"1px solid #1e293b",borderRadius:4,color:"#e2e8f0",padding:"4px 8px",fontSize:9,marginBottom:5,boxSizing:"border-box",fontFamily:"inherit"}}/>
            <input value={baseUrl} onChange={e=>setBaseUrl(e.target.value)} placeholder="Base URL Flask (ej: http://localhost:5000)" style={{width:"100%",background:"#070c17",border:"1px solid #1e293b",borderRadius:4,color:"#e2e8f0",padding:"4px 8px",fontSize:9,marginBottom:5,boxSizing:"border-box",fontFamily:"inherit"}}/>
            <button onClick={connectLocal} style={{...btn(false,"#22d3ee"),background:"#22d3ee22",fontSize:9}}>🔌 Conectar y escanear</button>
          </>}
        </div>
      )}

      {/* Main */}
      <div style={{display:"flex",flex:1,overflow:"hidden"}}>

        {/* ── Grafo ── */}
        {view==="graph"&&<>
          <div style={{flex:1,position:"relative"}}>
            <GraphCanvas graphData={gd} filterType={filterType} filterEdge={filterEdge} onSelectNode={setSelectedNode} testResults={testResults} selectedId={selectedNode?.id}/>
            <div style={{position:"absolute",bottom:10,left:10,display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
              <button onClick={testAll} disabled={runningAll} style={{background:runningAll?"#1a2332":"#34d39922",border:`1px solid ${runningAll?"#1a2332":"#34d399"}`,color:runningAll?"#334155":"#34d399",padding:"4px 10px",borderRadius:5,fontSize:8,cursor:runningAll?"not-allowed":"pointer",fontFamily:"inherit"}}>
                {runningAll?`◌ ${testStats.running} pendientes…`:`▶▶ Testear todo (${gd.nodes.length})`}
              </button>
              {testStats.total>0&&(
                <div style={{background:"#0a1020cc",border:"1px solid #1a2332",borderRadius:5,padding:"4px 8px",fontSize:8,display:"flex",gap:7}}>
                  <span style={{color:"#34d399"}}>✓{testStats.pass}</span>
                  <span style={{color:"#fbbf24"}}>⚠{testStats.warn}</span>
                  <span style={{color:"#f43f5e"}}>✗{testStats.fail}</span>
                </div>
              )}
              <div style={{background:"#0a1020cc",border:"1px solid #1a2332",borderRadius:5,padding:"4px 8px",fontSize:7,color:"#334155"}}>scroll=zoom · drag=mover</div>
            </div>
          </div>

          {/* Side panel */}
          <div style={{width:238,borderLeft:"1px solid #1a2332",background:"#0a1020",overflowY:"auto",display:"flex",flexDirection:"column"}}>
            {selectedNode?(
              <div style={{display:"flex",flexDirection:"column",flex:1}}>
                <div style={{padding:12,flex:1,overflowY:"auto"}}>
                  <div style={{width:30,height:30,borderRadius:8,background:(TC[selectedNode.type]||TC.default)+"22",border:`1.5px solid ${TC[selectedNode.type]||TC.default}`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,marginBottom:8,color:TC[selectedNode.type]||TC.default}}>{ICONS[selectedNode.type]||ICONS.default}</div>
                  <div style={{fontSize:11,fontWeight:700,color:"#f1f5f9",marginBottom:3,wordBreak:"break-all"}}>{selectedNode.label}</div>
                  <div style={{display:"flex",gap:4,marginBottom:7,flexWrap:"wrap"}}>
                    <span style={{background:(TC[selectedNode.type]||TC.default)+"22",color:TC[selectedNode.type]||TC.default,fontSize:7,padding:"2px 5px",borderRadius:8}}>{TL[selectedNode.type]||selectedNode.type}</span>
                    {selectedNode.lines>0&&<span style={{background:"#1a2332",color:"#475569",fontSize:7,padding:"2px 5px",borderRadius:8}}>{selectedNode.lines}L</span>}
                  </div>
                  <div style={{fontSize:9,color:"#475569",lineHeight:1.6,marginBottom:8}}>{selectedNode.desc}</div>
                  {selectedNode.functions?.length>0&&<>
                    <div style={{fontSize:7,color:"#334155",letterSpacing:1,marginBottom:4}}>FUNCIONES ({selectedNode.functions.length})</div>
                    {selectedNode.functions.slice(0,5).map((fn,i)=>(
                      <div key={i} style={{padding:"2px 0",borderBottom:"1px solid #0d1a26"}}>
                        <div style={{display:"flex",alignItems:"center",gap:3}}>
                          {fn.async&&<span style={{fontSize:7,color:"#22d3ee"}}>async</span>}
                          <span style={{fontSize:8.5,color:"#a78bfa",fontWeight:600}}>{fn.name}</span>
                          <span style={{fontSize:7,color:"#334155",marginLeft:"auto"}}>L{fn.line}</span>
                        </div>
                        {fn.args?.length>0&&<div style={{fontSize:7,color:"#475569"}}>({fn.args.join(", ")})</div>}
                        {fn.decorators?.[0]&&<div style={{fontSize:7,color:"#34d399"}}>@{fn.decorators[0].split("(")[0]}</div>}
                      </div>
                    ))}
                    {selectedNode.functions.length>5&&<div style={{fontSize:7,color:"#334155",marginTop:2}}>+{selectedNode.functions.length-5} más…</div>}
                  </>}
                  <div style={{fontSize:7,color:"#334155",letterSpacing:1,margin:"8px 0 4px"}}>CONEXIONES ({conns.length})</div>
                  {conns.map((e,i)=>{
                    const s=e.source?.id||e.source,t=e.target?.id||e.target;
                    const isOut=s===selectedNode.id; const other=isOut?t:s;
                    const on=gd.nodes.find(n=>n.id===other); const tr=testResults[other];
                    return (
                      <div key={i} onClick={()=>on&&setSelectedNode(on)} style={{display:"flex",alignItems:"center",gap:5,padding:"3px 0",borderBottom:"1px solid #0d1a26",cursor:on?"pointer":"default"}}>
                        <span style={{fontSize:8,color:isOut?"#22d3ee":"#f97316",minWidth:10}}>{isOut?"→":"←"}</span>
                        <div style={{flex:1,overflow:"hidden"}}>
                          <div style={{fontSize:8.5,color:"#94a3b8",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{on?.label||other}</div>
                          <div style={{fontSize:7,color:EC[e.type]||EC.default}}>{e.type}</div>
                        </div>
                        {tr&&<span style={{fontSize:9,color:SC[tr.status]}}>{SI[tr.status]}</span>}
                      </div>
                    );
                  })}
                </div>
                <TestPanel node={selectedNode} result={testResults[selectedNode.id]} onTest={testNode} scannerOk={scannerOk}/>
              </div>
            ):(
              <div style={{padding:12}}>
                <div style={{fontSize:7,color:"#334155",letterSpacing:1,marginBottom:7}}>TIPOS — click para filtrar</div>
                {nodeTypes.map(type=>{
                  const ns=gd.nodes.filter(n=>n.type===type);
                  const fp=ns.filter(n=>testResults[n.id]?.status==="pass").length;
                  const ff=ns.filter(n=>testResults[n.id]?.status==="fail").length;
                  const fw=ns.filter(n=>testResults[n.id]?.status==="warn").length;
                  return (
                    <div key={type} onClick={()=>setFilterType(filterType===type?"all":type)} style={{display:"flex",alignItems:"center",gap:6,padding:"3px 0",cursor:"pointer",opacity:filterType==="all"||filterType===type?1:0.3}}>
                      <div style={{width:8,height:8,borderRadius:"50%",background:TC[type]||TC.default}}/>
                      <span style={{fontSize:8.5,color:"#64748b",flex:1}}>{TL[type]||type}</span>
                      <span style={{fontSize:7,color:"#334155"}}>{ns.length}</span>
                      {(fp+ff+fw)>0&&<div style={{display:"flex",gap:2}}>
                        {ff>0&&<span style={{fontSize:7,color:"#f43f5e"}}>✗{ff}</span>}
                        {fw>0&&<span style={{fontSize:7,color:"#fbbf24"}}>⚠{fw}</span>}
                        {fp>0&&<span style={{fontSize:7,color:"#34d399"}}>✓{fp}</span>}
                      </div>}
                    </div>
                  );
                })}
                <div style={{fontSize:7,color:"#334155",letterSpacing:1,margin:"10px 0 5px"}}>ARISTAS</div>
                {edgeTypes.map(type=>(
                  <div key={type} onClick={()=>setFilterEdge(filterEdge===type?"all":type)} style={{display:"flex",alignItems:"center",gap:6,padding:"2px 0",cursor:"pointer",opacity:filterEdge==="all"||filterEdge===type?1:0.3}}>
                    <div style={{width:12,height:2,background:EC[type]||EC.default}}/>
                    <span style={{fontSize:8,color:"#64748b"}}>{type}</span>
                  </div>
                ))}
                <div style={{marginTop:12,padding:7,background:"#070c17",borderRadius:5,border:"1px solid #1a2332",fontSize:7.5,color:"#334155",lineHeight:1.9}}>
                  <span style={{color:"#475569"}}>LEYENDA STATUS</span><br/>
                  <span style={{color:"#34d399"}}>✓ verde</span> = todos los checks OK<br/>
                  <span style={{color:"#fbbf24"}}>⚠ amarillo</span> = checks parciales<br/>
                  <span style={{color:"#f43f5e"}}>✗ rojo</span> = fallo crítico<br/>
                  <span style={{color:"#22d3ee"}}>◌</span> = en progreso<br/><br/>
                  Click nodo → detalles + ▶ Testear<br/>
                  ▶▶ Testear todo → batch de 4
                </div>
              </div>
            )}
          </div>
        </>}

        {/* ── Tests ── */}
        {view==="tests"&&(
          <div style={{flex:1,overflowY:"auto",padding:14}}>
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:10,flexWrap:"wrap"}}>
              <div style={{fontSize:11,fontWeight:700,color:"#f1f5f9"}}>Health Check — {gd.nodes.length} nodos</div>
              <div style={{display:"flex",gap:3}}>
                {[["all",`Todos (${gd.nodes.length})`],["pass",`✓ ${testStats.pass}`],["warn",`⚠ ${testStats.warn}`],["fail",`✗ ${testStats.fail}`]].map(([f,l])=>(
                  <button key={f} onClick={()=>setTestFilter(f)} style={{background:testFilter===f?(f==="fail"?"#f43f5e22":f==="warn"?"#fbbf2422":"#34d39922"):"transparent",border:`1px solid ${testFilter===f?(f==="fail"?"#f43f5e":f==="warn"?"#fbbf24":"#34d399"):"#1e293b"}`,color:testFilter===f?(f==="fail"?"#f43f5e":f==="warn"?"#fbbf24":"#34d399"):"#475569",padding:"3px 8px",borderRadius:5,fontSize:8,cursor:"pointer",fontFamily:"inherit"}}>{l}</button>
                ))}
              </div>
              <button onClick={testAll} disabled={runningAll} style={{marginLeft:"auto",background:runningAll?"#1a2332":"#34d39922",border:`1px solid ${runningAll?"#1a2332":"#34d399"}`,color:runningAll?"#334155":"#34d399",padding:"5px 12px",borderRadius:5,fontSize:9,cursor:runningAll?"not-allowed":"pointer",fontFamily:"inherit"}}>
                {runningAll?`◌ ${testStats.running} en cola…`:`▶▶ Testear los ${gd.nodes.length} nodos`}
              </button>
            </div>
            {testStats.total>0&&(
              <div style={{display:"flex",gap:6,marginBottom:10,padding:"7px 10px",background:"#0d1424",border:"1px solid #1a2332",borderRadius:6}}>
                {[["pass","✓ Pass","#34d399"],["warn","⚠ Warn","#fbbf24"],["fail","✗ Fail","#f43f5e"],["running","◌","#22d3ee"]].map(([k,l,c])=>testStats[k]>0&&(
                  <div key={k} style={{display:"flex",alignItems:"center",gap:4}}>
                    <div style={{width:6,height:6,borderRadius:"50%",background:c}}/>
                    <span style={{fontSize:9,color:c,fontWeight:700}}>{testStats[k]}</span>
                    <span style={{fontSize:8,color:"#475569"}}>{l}</span>
                  </div>
                ))}
                <span style={{fontSize:7,color:"#334155",marginLeft:"auto"}}>{testStats.total}/{gd.nodes.length} testeados · {scannerOk?"real":"simulado"}</span>
              </div>
            )}
            {testStats.total===0&&(
              <div style={{textAlign:"center",padding:32,fontSize:9,color:"#334155"}}>
                Clic en "▶▶ Testear los {gd.nodes.length} nodos" para ver resultados
              </div>
            )}
            <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))",gap:7}}>
              {testViewNodes.map(node=>{
                const r=testResults[node.id]; const running=r?.status==="running";
                return (
                  <div key={node.id} style={{background:"#0d1424",border:`1px solid ${r?SC[r.status]+"44":"#1a2332"}`,borderRadius:7,overflow:"hidden"}}>
                    <div style={{display:"flex",alignItems:"center",gap:7,padding:"7px 10px",background:r?SC[r.status]+"0d":"transparent"}}>
                      <span style={{fontSize:10,color:TC[node.type]||TC.default}}>{ICONS[node.type]||ICONS.default}</span>
                      <div style={{flex:1,overflow:"hidden"}}>
                        <div style={{fontSize:9,fontWeight:700,color:"#e2e8f0",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{node.label}</div>
                        <div style={{fontSize:7,color:"#475569"}}>{TL[node.type]||node.type}</div>
                      </div>
                      {r&&!running&&<div style={{textAlign:"right"}}>
                        <div style={{fontSize:13,color:SC[r.status]}}>{SI[r.status]}</div>
                        <div style={{fontSize:7,color:"#334155"}}>{r.ms}ms</div>
                      </div>}
                      {running&&<div style={{fontSize:11,color:"#22d3ee",animation:"spin 1s linear infinite"}}>◌</div>}
                      <button onClick={()=>testNode(node)} disabled={running}
                        style={{background:"transparent",border:`1px solid ${running?"#1a2332":"#334155"}`,color:running?"#1a2332":"#475569",padding:"2px 7px",borderRadius:4,fontSize:8,cursor:running?"not-allowed":"pointer",fontFamily:"inherit",flexShrink:0}}
                        onMouseEnter={e=>{if(!running){e.target.style.borderColor="#34d399";e.target.style.color="#34d399";}}}
                        onMouseLeave={e=>{if(!running){e.target.style.borderColor="#334155";e.target.style.color="#475569";}}}>
                        ▶
                      </button>
                    </div>
                    {r&&!running&&(
                      <div style={{padding:"6px 10px",borderTop:"1px solid #1a2332"}}>
                        <div style={{fontSize:7.5,color:"#334155",marginBottom:3}}>{r.summary}{r.simulated?" · simulado":""}</div>
                        {r.checks.map((c,i)=>(
                          <div key={i} style={{display:"flex",gap:5,padding:"2px 0",borderBottom:"1px solid #0d1a26",alignItems:"flex-start"}}>
                            <span style={{fontSize:8,color:c.ok?"#34d399":"#f43f5e",flexShrink:0}}>{c.ok?"✓":"✗"}</span>
                            <div style={{flex:1}}>
                              <span style={{fontSize:8,color:c.ok?"#475569":"#e2e8f0"}}>{c.name}</span>
                              {!c.ok&&c.detail&&<div style={{fontSize:7.5,color:"#f43f5e",wordBreak:"break-all"}}>{c.detail}</div>}
                              {c.ok&&c.detail&&c.detail!=="OK"&&<div style={{fontSize:7.5,color:"#334155"}}>{c.detail}</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Explorer ── */}
        {view==="explorer"&&(
          <div style={{flex:1,overflowY:"auto",padding:14}}>
            <div style={{fontSize:11,fontWeight:700,color:"#f1f5f9",marginBottom:10}}>Explorador de Archivos</div>
            <div style={{display:"grid",gap:6}}>
              {gd.nodes.filter(n=>n.functions?.length>0||n.classes?.length>0).map(node=>{
                const r=testResults[node.id];
                return (
                  <details key={node.id} style={{background:"#0d1424",border:`1px solid ${TC[node.type]||TC.default}33`,borderRadius:7}}>
                    <summary style={{display:"flex",alignItems:"center",gap:7,padding:"7px 10px",cursor:"pointer",background:(TC[node.type]||TC.default)+"0d",listStyle:"none",borderRadius:7}}>
                      <span style={{color:TC[node.type]||TC.default,fontSize:10}}>{ICONS[node.type]||ICONS.default}</span>
                      <span style={{fontSize:9.5,color:"#e2e8f0",flex:1,fontWeight:600}}>{node.label}</span>
                      {r&&<span style={{fontSize:9,color:SC[r.status]}}>{SI[r.status]}</span>}
                      <span style={{fontSize:7,color:TC[node.type]||TC.default,background:(TC[node.type]||TC.default)+"22",padding:"1px 5px",borderRadius:4}}>{TL[node.type]||node.type}</span>
                      {node.lines>0&&<span style={{fontSize:7,color:"#334155"}}>{node.lines}L</span>}
                    </summary>
                    <div style={{padding:"7px 10px"}}>
                      <div style={{fontSize:8,color:"#475569",marginBottom:5}}>{node.desc}</div>
                      {node.functions?.length>0&&<>
                        <div style={{fontSize:7,color:"#334155",letterSpacing:1,marginBottom:4}}>FUNCIONES</div>
                        {node.functions.map((fn,i)=>(
                          <div key={i} style={{display:"flex",alignItems:"center",gap:5,padding:"2px 0",borderBottom:"1px solid #0d1a26"}}>
                            {fn.async&&<span style={{fontSize:7,color:"#22d3ee"}}>async</span>}
                            <span style={{fontSize:8.5,color:"#a78bfa",fontWeight:600}}>{fn.name}</span>
                            <span style={{fontSize:7,color:"#475569",flex:1}}>({fn.args?.join(",")||""})</span>
                            <span style={{fontSize:7,color:"#1e293b"}}>L{fn.line}</span>
                            {fn.decorators?.[0]&&<span style={{fontSize:7,color:"#34d399",maxWidth:90,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>@{fn.decorators[0].split("(")[0]}</span>}
                          </div>
                        ))}
                      </>}
                      {node.classes?.length>0&&<>
                        <div style={{fontSize:7,color:"#334155",letterSpacing:1,margin:"5px 0 3px"}}>CLASES</div>
                        {node.classes.map((cls,i)=>(
                          <div key={i} style={{padding:"2px 0",borderBottom:"1px solid #0d1a26"}}>
                            <span style={{fontSize:8.5,color:"#e879f9",fontWeight:600}}>{cls.name}</span>
                            {cls.methods?.length>0&&<div style={{fontSize:7.5,color:"#475569",marginTop:1}}>{cls.methods.join(", ")}</div>}
                          </div>
                        ))}
                      </>}
                    </div>
                  </details>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Setup ── */}
        {view==="setup"&&(
          <div style={{flex:1,overflowY:"auto",padding:14,maxWidth:600}}>
            <div style={{fontSize:11,fontWeight:700,color:"#f1f5f9",marginBottom:4}}>Integración VS Code + Tests en vivo</div>
            <div style={{fontSize:8,color:"#475569",marginBottom:12}}>Tests reales contra tu servidor Flask desde el grafo</div>
            {[
              {n:"1",t:"Copiar scan_project.py",d:"Copiá scan_project.py (archivo descargable abajo) a la raíz de tu proyecto.",code:null},
              {n:"2",t:"Iniciar Flask",d:"Flask debe estar corriendo para los tests de rutas HTTP:",code:"$ python app.py\n * Running on http://localhost:5000"},
              {n:"3",t:"Iniciar scanner",d:"En una segunda terminal de VS Code:",code:"$ python scan_project.py . --base-url http://localhost:5000\n──────────────────────────────────────\n  🔬 Project Graph Scanner v2\n  Servidor: http://localhost:7477\n  ✓ 21 archivos · 38 dependencias"},
              {n:"4",t:"Conectar el grafo",d:"+ Proyecto → 🔌 Scanner local → ruta → Conectar.",code:null},
              {n:"5",t:"Testear",d:"Click en cualquier nodo → ▶ Testear, o ▶▶ Testear todo en el grafo.",code:null},
            ].map(({n,t,d,code})=>(
              <div key={n} style={{marginBottom:8,padding:10,background:"#0d1424",border:"1px solid #1a2332",borderRadius:7}}>
                <div style={{display:"flex",gap:8,alignItems:"flex-start"}}>
                  <div style={{width:18,height:18,borderRadius:4,background:"#6366f122",border:"1px solid #6366f1",display:"flex",alignItems:"center",justifyContent:"center",fontSize:8,color:"#6366f1",flexShrink:0}}>{n}</div>
                  <div style={{flex:1}}>
                    <div style={{fontSize:9.5,fontWeight:700,color:"#e2e8f0",marginBottom:2}}>{t}</div>
                    <div style={{fontSize:8,color:"#475569",marginBottom:code?5:0}}>{d}</div>
                    {code&&<pre style={{background:"#070c17",border:"1px solid #1a2332",borderRadius:5,padding:"6px 9px",fontSize:8,color:"#94a3b8",overflow:"auto",margin:0,lineHeight:1.7}}>{code}</pre>}
                  </div>
                </div>
              </div>
            ))}
            <div style={{padding:10,background:"#34d39911",border:"1px solid #34d39933",borderRadius:7}}>
              <div style={{fontSize:8,color:"#34d399",fontWeight:700,marginBottom:5}}>QUÉ TESTEA CADA TIPO</div>
              {[["entry / blueprint","Sintaxis AST, import sin errores"],["route","Sintaxis + HTTP request real a cada ruta decorada"],["model","Sintaxis, import, clase definida y métodos"],["db","SQLite conecta, tablas presentes, PRAGMA integrity_check"],["config","SECRET_KEY y DATABASE definidas"],["auth","Firebase config, verify_token callable"],["static","Archivo existe, tamaño > 0"],["template","Archivo existe, Jinja2 parse válido"]].map(([t,d])=>(
                <div key={t} style={{display:"flex",gap:8,fontSize:8,lineHeight:1.8}}>
                  <span style={{color:"#64748b",minWidth:130,flexShrink:0}}>{t}</span>
                  <span style={{color:"#334155"}}>{d}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
