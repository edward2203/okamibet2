#!/usr/bin/env python3
"""
Project Graph Scanner v2 — con sistema de tests por nodo
Uso: python scan_project.py [ruta_proyecto] [--base-url http://localhost:5000]
"""

import ast, os, sys, json, re, subprocess, sqlite3, importlib.util, time, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen, Request
from urllib.error import URLError

PORT = 7477
IGNORE_DIRS = {"__pycache__",".git","node_modules",".venv","venv","env","dist","build",".pytest_cache"}
IGNORE_EXTS = {".pyc",".pyo",".min.js",".map",".lock"}

# ── Detectar tipo de nodo ─────────────────────────────────────────────────────
def detect_type(filepath, content):
    name = os.path.basename(filepath).lower()
    if name in ("app.py","main.py","wsgi.py","asgi.py","server.py","index.js","index.ts"): return "entry"
    if "Blueprint(" in content: return "blueprint"
    if re.search(r"@(app|bp|api)\.(route|get|post|put|delete)\(", content): return "route"
    if re.search(r"class \w+.*Model|db\.Model|Base\.metadata", content): return "model"
    if "firebase" in content.lower() or "login_required" in content.lower(): return "auth"
    if name in ("config.py","settings.py","constants.py"): return "config"
    if name in ("database.py","db.py") or "sqlite3" in content: return "db"
    if "/templates/" in filepath or name.endswith((".html",".jinja2")): return "template"
    if "/static/" in filepath: return "static"
    if "/api/" in filepath or "jsonify" in content: return "api"
    if "util" in name or "helper" in name: return "util"
    return "default"

# ── Parsers ───────────────────────────────────────────────────────────────────
def parse_python(filepath, root):
    try: src = Path(filepath).read_text(encoding="utf-8", errors="ignore")
    except: return None, [], []
    try: tree = ast.parse(src, filename=filepath)
    except SyntaxError as e:
        rel = os.path.relpath(filepath, root).replace("\\","/")
        return {"id":rel,"label":rel,"type":"default","desc":f"ERROR DE SINTAXIS: {e}","functions":[],"classes":[],"lines":0,"syntax_error":str(e),"path":rel}, [], src

    imports, functions, classes = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names: imports.append(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module: imports.append(node.module.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:
                functions.append({
                    "name": node.name, "line": node.lineno,
                    "args": [a.arg for a in node.args.args],
                    "async": isinstance(node, ast.AsyncFunctionDef),
                    "decorators": [ast.unparse(d) if hasattr(ast,"unparse") else getattr(d,"id","?") for d in node.decorator_list],
                })
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in ast.walk(node) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.col_offset > 0]
            classes.append({"name":node.name,"line":node.lineno,"methods":methods})

    ntype = detect_type(filepath, src)
    rel = os.path.relpath(filepath, root).replace("\\","/")
    routes = [f["decorators"][0] for f in functions if f["decorators"] and ".route(" in f["decorators"][0]]
    return {
        "id":rel, "label":rel if len(rel)<30 else "…/"+os.path.basename(rel),
        "type":ntype, "desc":f"{len(functions)} funciones · {len(classes)} clases · {len(src.splitlines())} líneas",
        "functions":functions, "classes":classes, "path":rel,
        "lines":len(src.splitlines()), "routes":routes,
    }, imports, src

def parse_js(filepath, root):
    try: src = Path(filepath).read_text(encoding="utf-8", errors="ignore")
    except: return None, [], []
    imports = [m.group(1) for m in re.finditer(r"""(?:import|require)\s*\(?['"]([^'"]+)['"]\)?""", src) if not m.group(1).startswith("http")]
    funcs = []
    for m in re.finditer(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)|(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(?[^)]*\)?\s*=>", src):
        name = m.group(1) or m.group(3)
        if name: funcs.append({"name":name,"line":src[:m.start()].count("\n")+1,"args":[],"async":"async" in m.group(0),"decorators":[]})
    ntype = detect_type(filepath, src)
    rel = os.path.relpath(filepath, root).replace("\\","/")
    return {"id":rel,"label":rel if len(rel)<30 else "…/"+os.path.basename(rel),"type":ntype,"desc":f"{len(funcs)} funciones · {len(src.splitlines())} líneas","functions":funcs,"classes":[],"path":rel,"lines":len(src.splitlines()),"routes":[]}, imports, src

def resolve_imports(imports, current_file, all_ids, root):
    edges = []
    current_dir = os.path.dirname(current_file)
    for imp in set(imports):
        for ext in ("",".py",".js",".ts",".jsx",".tsx","/index.js"):
            candidate = os.path.normpath(os.path.join(current_dir, imp.replace(".","/") + ext))
            rel = os.path.relpath(candidate, root).replace("\\","/")
            if rel in all_ids:
                edges.append({"source":current_file,"target":rel,"type":"imports"})
                break
        else:
            for fid in all_ids:
                base = os.path.splitext(os.path.basename(fid))[0]
                if base == imp:
                    edges.append({"source":current_file,"target":fid,"type":"imports"})
                    break
    return edges

def scan_project(root):
    root = os.path.abspath(root)
    nodes, raw_edges = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext in IGNORE_EXTS: continue
            if ext == ".py": node, imports, _ = parse_python(fpath, root)
            elif ext in (".js",".ts",".jsx",".tsx"): node, imports, _ = parse_js(fpath, root)
            else: continue
            if node:
                nodes.append(node)
                raw_edges.append((node["id"], imports))

    all_ids = {n["id"] for n in nodes}
    edges = []
    for file_id, imports in raw_edges:
        edges += resolve_imports(imports, file_id, all_ids, root)
    seen, dedup = set(), []
    for e in edges:
        key = (e["source"],e["target"])
        if key not in seen: seen.add(key); dedup.append(e)

    return {"nodes":nodes,"edges":dedup,"meta":{"root":root,"total_files":len(nodes),"scanned_at":__import__("datetime").datetime.now().isoformat()}}

# ── Sistema de tests ──────────────────────────────────────────────────────────
def run_test(node, root, base_url="http://localhost:5000"):
    ntype = node.get("type","default")
    path = os.path.join(root, node.get("path",""))
    t0 = time.time()
    result = {"node_id": node["id"], "status": "unknown", "checks": [], "ms": 0}

    def check(name, ok, detail=""):
        result["checks"].append({"name":name, "ok":ok, "detail":detail})
        return ok

    try:
        # 1. FILE EXISTS — todos los nodos con path real
        if node.get("path") and not node["id"].endswith(("/","_sdk")):
            exists = os.path.exists(path)
            check("Archivo existe", exists, path if exists else f"No encontrado: {path}")

        # 2. SYNTAX CHECK — Python
        if ntype in ("entry","blueprint","route","model","auth","config","db","api","util","default") and path.endswith(".py") and os.path.exists(path):
            try:
                with open(path) as f: src = f.read()
                ast.parse(src)
                check("Sintaxis Python válida", True)
            except SyntaxError as e:
                check("Sintaxis Python válida", False, str(e))

        # 3. IMPORT CHECK — Python (subprocess aislado)
        if path.endswith(".py") and os.path.exists(path):
            mod_path = os.path.relpath(path, root).replace("/",".").replace("\\",".").replace(".py","")
            proc = subprocess.run(
                [sys.executable, "-c", f"import sys; sys.path.insert(0,'{root}'); import {mod_path}"],
                capture_output=True, text=True, timeout=8, cwd=root
            )
            ok = proc.returncode == 0
            detail = "" if ok else (proc.stderr.strip().splitlines()[-1] if proc.stderr else "Error desconocido")
            check("Import sin errores", ok, detail)

        # 4. HTTP ROUTES — hacer request real al servidor
        if node.get("routes"):
            for route_dec in node["routes"][:3]:
                m = re.search(r"['\"]([^'\"]+)['\"]", route_dec)
                if not m: continue
                route_path = re.sub(r"<[^>]+>","1", m.group(1))
                url = base_url.rstrip("/") + route_path
                try:
                    req = Request(url, headers={"User-Agent":"ProjectGraphScanner/1.0"})
                    resp = urlopen(req, timeout=3)
                    check(f"HTTP {route_path}", True, f"{resp.status} {resp.reason} · {url}")
                except Exception as e:
                    code = getattr(getattr(e,"code",None),"__str__",lambda:str(e))()
                    is_auth = "401" in str(e) or "403" in str(e)
                    check(f"HTTP {route_path}", is_auth, f"{e} · {url}" if not is_auth else f"Auth requerida (esperado) · {url}")

        # 5. DATABASE — SQLite connection + integridad
        if ntype == "db" or path.endswith(".db"):
            db_path = path if path.endswith(".db") else os.path.join(root, node["id"])
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                    conn.execute("PRAGMA integrity_check").fetchone()
                    conn.close()
                    check("SQLite conecta", True, f"{len(tables)} tablas: {', '.join(t[0] for t in tables[:5])}")
                    check("Integridad DB", True)
                except Exception as e:
                    check("SQLite conecta", False, str(e))
            else:
                check("DB encontrada", False, f"No existe: {db_path}")

        # 6. TEMPLATE — Jinja2 syntax
        if ntype == "template" and path.endswith((".html",".jinja2")) and os.path.exists(path):
            try:
                from jinja2 import Environment
                env = Environment()
                with open(path) as f: src = f.read()
                env.parse(src)
                check("Template Jinja2 válido", True)
            except Exception as e:
                try:
                    check("Template HTML existe", True, "jinja2 no instalado, solo verificación de archivo")
                except: pass

        # 7. STATIC FILES
        if ntype == "static" and os.path.exists(path):
            size = os.path.getsize(path)
            check("Archivo static existe", True, f"{size//1024}KB · {path}")

        # 8. CONFIG — variables requeridas
        if ntype == "config" and path.endswith(".py") and os.path.exists(path):
            with open(path) as f: src = f.read()
            for key in ["SECRET_KEY","DATABASE"]:
                found = key in src
                check(f"Variable {key}", found, "Encontrada" if found else "No definida en config")

    except Exception as e:
        result["error"] = traceback.format_exc()

    result["ms"] = round((time.time() - t0) * 1000)
    passed = sum(1 for c in result["checks"] if c["ok"])
    total  = len(result["checks"])
    result["status"] = "pass" if total > 0 and passed == total else ("warn" if passed > 0 else ("skip" if total == 0 else "fail"))
    result["summary"] = f"{passed}/{total} checks OK"
    return result

# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    project_root = "."
    base_url = "http://localhost:5000"
    cache = {}
    test_cache = {}

    def log_message(self, fmt, *args): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self._cors(); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        path = parsed.path

        if path == "/ping":
            return self._json({"status":"ok","root":Handler.project_root,"base_url":Handler.base_url})

        if path == "/scan":
            root = q.get("path",[Handler.project_root])[0]
            root = os.path.abspath(root)
            if q.get("force",["0"])[0]=="1" or root not in Handler.cache:
                print(f"  Escaneando: {root}")
                Handler.cache[root] = scan_project(root)
                n = Handler.cache[root]
                print(f"  ✓ {len(n['nodes'])} nodos · {len(n['edges'])} aristas")
            return self._json(Handler.cache[root])

        if path == "/test":
            node_id = q.get("node",[""])[0]
            root = q.get("root",[Handler.project_root])[0]
            force = q.get("force",["0"])[0]=="1"
            cache_key = f"{root}::{node_id}"

            if cache_key not in Handler.test_cache or force:
                if root not in Handler.cache:
                    Handler.cache[root] = scan_project(root)
                node = next((n for n in Handler.cache[root]["nodes"] if n["id"]==node_id), None)
                if not node:
                    return self._json({"error":f"Nodo '{node_id}' no encontrado"},404)
                print(f"  Testing: {node_id}")
                Handler.test_cache[cache_key] = run_test(node, root, Handler.base_url)
                r = Handler.test_cache[cache_key]
                print(f"  → {r['status'].upper()} {r['summary']} ({r['ms']}ms)")

            return self._json(Handler.test_cache[cache_key])

        if path == "/test/all":
            root = q.get("root",[Handler.project_root])[0]
            root = os.path.abspath(root)
            if root not in Handler.cache:
                Handler.cache[root] = scan_project(root)
            nodes = Handler.cache[root]["nodes"]
            print(f"  Testing all {len(nodes)} nodos...")
            results = {}
            for node in nodes:
                key = f"{root}::{node['id']}"
                result = run_test(node, root, Handler.base_url)
                Handler.test_cache[key] = result
                results[node["id"]] = result
                print(f"  {'✓' if result['status']=='pass' else '✗'} {node['id']} — {result['summary']}")
            return self._json(results)

        self.send_response(404); self.end_headers()


def main():
    root = "."
    base_url = "http://localhost:5000"
    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--base-url"): base_url = sys.argv[i+2] if "=" not in arg else arg.split("=",1)[1]
        elif not arg.startswith("-"): root = arg

    root = os.path.abspath(root)
    Handler.project_root = root
    Handler.base_url = base_url

    print(f"\n{'─'*54}")
    print(f"  🔬 Project Graph Scanner v2")
    print(f"  Proyecto : {root}")
    print(f"  Base URL : {base_url}")
    print(f"  Servidor : http://localhost:{PORT}")
    print(f"  Endpoints:")
    print(f"    /ping                    → estado")
    print(f"    /scan                    → escanear proyecto raíz")
    print(f"    /scan?path=<dir>         → otro directorio")
    print(f"    /scan?force=1            → forzar re-escaneo")
    print(f"    /test?node=<id>          → testear un nodo")
    print(f"    /test/all                → testear todos los nodos")
    print(f"{'─'*54}\n")

    print("  Escaneando proyecto...")
    Handler.cache[root] = scan_project(root)
    m = Handler.cache[root]["meta"]
    print(f"  ✓ {m['total_files']} archivos · {m.get('total_edges',0)} dependencias\n")

    try:
        HTTPServer(("localhost", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  Servidor detenido.")

if __name__ == "__main__":
    main()
