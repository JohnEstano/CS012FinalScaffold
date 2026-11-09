"""MENDO Cloud (the center of the star).

Receives heartbeats and records from every machine, keeps the central
database, shows the dashboard, raises alerts and makes backups.
"""
import os
import time
import json
import shutil
import asyncio
import sqlite3
from collections import defaultdict, Counter
import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from common.models import DataPayload, DistributedResponse
from common.models import SyncBatch, Heartbeat, Switch
from common.logger import get_logger, trace_id_var, generate_trace_id, log_event, EVENTS

app = FastAPI(title="MENDO Cloud")
logger = get_logger("CLOUD")

# Configured worker endpoints (the MENDO machines)
WORKER_NODES = os.getenv("WORKERS", "http://127.0.0.1:8101,http://127.0.0.1:8102,http://127.0.0.1:8103").split(",")
# Each machine has its own API key; admins use the admin key.
MACHINE_KEYS = dict(pair.split("=") for pair in os.getenv("MACHINE_KEYS", "").split(",") if pair)
ADMIN_KEY = os.getenv("ADMIN_KEY", "admin-demo")
OFFLINE_AFTER = 10  # seconds without a heartbeat

def event(message, level="INFO"):
    log_event(logger, "CLOUD", message, level)


# ---------------------------------------------------------------- central database
os.makedirs("data", exist_ok=True)
DB_PATH, BACKUP_PATH = "data/cloud.db", "data/cloud-backup.db"
db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)

def create_tables():
    db.execute("""CREATE TABLE IF NOT EXISTS records(record_id TEXT PRIMARY KEY, machine_id TEXT, seq INTEGER,
                  type TEXT, data TEXT, created_at REAL, received_at REAL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS machines(machine_id TEXT PRIMARY KEY, last_seen REAL, last_sync REAL,
                  stock TEXT, queued INTEGER, last_seq INTEGER, duplicates INTEGER DEFAULT 0)""")
create_tables()

def cloud_has_up_to(machine_id):
    """Highest seq where the cloud has every record from 1 up to it (no gaps)."""
    n = 0
    for (seq,) in db.execute("SELECT seq FROM records WHERE machine_id=? ORDER BY seq", (machine_id,)):
        if seq != n + 1:
            break
        n = seq
    return n


# ---------------------------------------------------------------- simulation switches
cloud_down = False     # whole cloud API unavailable
sync_fails = False     # cloud saves records but the reply to the machine is lost
offline_alerted = {}      # machine_id -> time the alert was raised
low_stock_alerted = {}    # (machine_id, medicine) -> (qty, time)

# Performance metrics: response time and errors per API endpoint
METRICS = defaultdict(lambda: {"count": 0, "total_ms": 0.0, "max_ms": 0.0, "errors": 0})

def record_metric(path, ms, status):
    m = METRICS[path]
    m["count"] += 1
    m["total_ms"] += ms
    m["max_ms"] = max(m["max_ms"], ms)
    if status >= 400:
        m["errors"] += 1


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    # Generates or captures X-Trace-ID and propagates it across all hop requests
    trace_id = request.headers.get("X-Trace-ID") or generate_trace_id()
    trace_id_var.set(trace_id)
    start = time.perf_counter()
    path = request.url.path
    if cloud_down and path.startswith(("/api", "/cluster")):
        record_metric(f"{request.method} {path}", 0, 503)
        return JSONResponse({"detail": "cloud is down (simulated)"}, status_code=503)
    if path not in ["/", "/logs", "/sim/status", "/api/dashboard", "/api/metrics"]:   # skip the page's refresh polling
        logger.info(f"Incoming Gateway Request: {request.method} {path}")
    response = await call_next(request)
    route = request.scope.get("route")
    if route is not None and path.startswith(("/api", "/cluster")):
        record_metric(f"{request.method} {route.path}", (time.perf_counter() - start) * 1000, response.status_code)
    response.headers["X-Trace-ID"] = trace_id
    return response


def check_machine(machine_id, key):
    if MACHINE_KEYS.get(machine_id) != key:
        event(f"Rejected request: wrong API key for {machine_id}.", "WARN")
        raise HTTPException(401, "Invalid machine API key")

def check_admin(key):
    if key != ADMIN_KEY:
        raise HTTPException(401, "Admin key required")


# ---------------------------------------------------------------- machine API
@app.post("/api/heartbeat")
async def heartbeat(hb: Heartbeat, x_api_key: str = Header("")):
    check_machine(hb.machine_id, x_api_key)
    if hb.machine_id in offline_alerted:
        offline_alerted.pop(hb.machine_id)
        event(f"{hb.machine_id} is back online.")
    db.execute("""INSERT INTO machines(machine_id, last_seen, stock, queued, last_seq) VALUES(?,?,?,?,?)
                  ON CONFLICT(machine_id) DO UPDATE SET last_seen=excluded.last_seen, stock=excluded.stock,
                  queued=excluded.queued, last_seq=excluded.last_seq""",
               (hb.machine_id, time.time(), json.dumps(hb.stock), hb.queued, hb.last_seq))
    for med, qty in hb.stock.items():
        key = (hb.machine_id, med)
        if qty <= 2:
            if key not in low_stock_alerted:
                event(f"ALERT: {hb.machine_id} is low on {med} ({qty} left).", "WARN")
            low_stock_alerted[key] = (qty, low_stock_alerted.get(key, (0, time.time()))[1])
        else:
            low_stock_alerted.pop(key, None)
    return {"cloud_has_up_to": cloud_has_up_to(hb.machine_id)}


@app.post("/api/sync")
async def sync(batch: SyncBatch, x_api_key: str = Header("")):
    """Save records. The record_id is the primary key, so a record sent twice is stored once."""
    check_machine(batch.machine_id, x_api_key)
    new = 0
    for r in batch.records:
        cur = db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?)",
                         (r.record_id, r.machine_id, r.seq, r.type, json.dumps(r.data), r.created_at, time.time()))
        new += cur.rowcount
    duplicates = len(batch.records) - new
    db.execute("UPDATE machines SET last_sync=?, duplicates=duplicates+? WHERE machine_id=?",
               (time.time(), duplicates, batch.machine_id))
    event(f"Received {len(batch.records)} records from {batch.machine_id}: {new} new, {duplicates} duplicates ignored.")
    if sync_fails:
        event(f"Sync failure (simulated): records from {batch.machine_id} were saved but the reply was lost.", "WARN")
        raise HTTPException(500, "simulated sync failure")
    return {"saved": new, "duplicates": duplicates}


# ---------------------------------------------------------------- dashboard API (admin)
@app.get("/api/dashboard")
async def dashboard(x_admin_key: str = Header("")):
    check_admin(x_admin_key)
    now = time.time()
    machines = []
    for mid, last_seen, last_sync, stock, queued, mseq, dups in db.execute("SELECT * FROM machines ORDER BY machine_id"):
        sales = db.execute("SELECT COUNT(*), COALESCE(SUM(json_extract(data,'$.price')),0) FROM records "
                           "WHERE machine_id=? AND type='SALE'", (mid,)).fetchone()
        status = "ONLINE" if now - last_seen < OFFLINE_AFTER else "OFFLINE"
        machines.append({
            "machine_id": mid, "status": status,
            "last_sync": last_sync, "stock": json.loads(stock), "queued": queued,
            # cloud data may be outdated if the machine is offline, or records have waited over 10 s
            "outdated": status == "OFFLINE" or (queued > 0 and now - (last_sync or 0) > OFFLINE_AFTER),
            "records_in_cloud": db.execute("SELECT COUNT(*) FROM records WHERE machine_id=?", (mid,)).fetchone()[0],
            "sales": sales[0], "revenue": sales[1],
        })

    # alerts for the admin (still active)
    alerts = [{"time": t, "text": f"{m} is OFFLINE"} for m, t in offline_alerted.items()]
    alerts += [{"time": t, "text": f"{m} low on {med} ({q} left)"} for (m, med), (q, t) in low_stock_alerted.items()]
    alerts.sort(key=lambda a: -a["time"])

    # analytics: what sells and what people complain about, across all machines
    medicines, symptoms = Counter(), Counter()
    for rtype, data in db.execute("SELECT type, data FROM records WHERE type IN ('SALE','CONSULTATION')"):
        data = json.loads(data)
        if rtype == "SALE":
            medicines[data["medicine"]] += 1
        else:
            symptoms.update(data.get("symptoms", []))
    return {"machines": machines, "alerts": alerts,
            "top_medicines": medicines.most_common(5), "top_symptoms": symptoms.most_common(5)}


@app.get("/api/metrics")
async def metrics(x_admin_key: str = Header("")):
    """API response times, errors, and how long records wait before reaching the cloud."""
    check_admin(x_admin_key)
    endpoints = [{"endpoint": path, "requests": m["count"], "avg_ms": round(m["total_ms"] / m["count"], 1),
                  "max_ms": round(m["max_ms"], 1), "errors": m["errors"]} for path, m in sorted(METRICS.items())]
    sync_delay = {}
    for (mid,) in db.execute("SELECT machine_id FROM machines ORDER BY machine_id").fetchall():
        delays = [r - c for r, c in db.execute("SELECT received_at, created_at FROM records WHERE machine_id=? "
                                               "ORDER BY received_at DESC LIMIT 50", (mid,))]
        if delays:
            sync_delay[mid] = {"avg_s": round(sum(delays) / len(delays), 1), "max_s": round(max(delays), 1)}
    return {"endpoints": endpoints, "sync_delay": sync_delay}


@app.get("/api/check")
async def check_records(x_admin_key: str = Header("")):
    """Compare what each machine has with what the cloud has."""
    check_admin(x_admin_key)
    result = []
    for mid, mseq, dups in db.execute("SELECT machine_id, last_seq, duplicates FROM machines ORDER BY machine_id"):
        in_cloud = db.execute("SELECT COUNT(*) FROM records WHERE machine_id=?", (mid,)).fetchone()[0]
        result.append({"machine_id": mid, "machine_has": mseq, "cloud_has": in_cloud,
                       "missing": mseq - in_cloud, "duplicates_ignored": dups})
    event("Record check: " + ", ".join(f"{r['machine_id']} {r['cloud_has']}/{r['machine_has']}" for r in result))
    return result


@app.post("/api/backup")
async def backup(x_admin_key: str = Header("")):
    check_admin(x_admin_key)
    with sqlite3.connect(BACKUP_PATH) as dest:
        db.backup(dest)
    count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    event(f"Backup saved ({count} records).")
    return {"records": count}


@app.post("/api/restore")
async def restore(x_admin_key: str = Header("")):
    check_admin(x_admin_key)
    if not os.path.exists(BACKUP_PATH):
        raise HTTPException(404, "No backup yet")
    with sqlite3.connect(BACKUP_PATH) as src:
        src.backup(db)
    count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    event(f"Database restored from backup ({count} records). Machines will resend anything newer.", "WARN")
    return {"records": count}


# ---------------------------------------------------------------- scaffold endpoints
def get_target_node_for_key(key: str) -> str:
    """Consistently maps a data key to a specific node (Key Sharding Simulation)."""
    hash_value = sum(ord(char) for char in key)
    selected_index = hash_value % len(WORKER_NODES)
    return WORKER_NODES[selected_index]

@app.get("/cluster/health")
async def cluster_health():
    """Checks the operational status of all worker nodes in parallel."""
    headers = {"X-Trace-ID": trace_id_var.get(), "X-From": "cloud"}
    async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
        tasks = [client.get(f"{node}/health", headers=headers) for node in WORKER_NODES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        status_report = {}
        for node, resp in zip(WORKER_NODES, results):
            if isinstance(resp, Exception) or resp.status_code != 200:
                status_report[node] = {"status": "UNREACHABLE"}
            else:
                status_report[node] = resp.json()

    event("Health check: " + ", ".join(f"{n.rsplit(':', 1)[1]} {v['status']}" for n, v in status_report.items()))
    return {"cluster_status": status_report, "trace_id": trace_id_var.get()}

@app.post("/api/v1/write")
async def write_data(payload: DataPayload):
    """Shards incoming write requests based on key hash or sensitivity."""
    if payload.is_sensitive:
        target_node = WORKER_NODES[0]  # Force to Private VPC Node
    else:
        target_node = get_target_node_for_key(payload.key)

    logger.info(f"Routing Key '{payload.key}' -> Target Node: {target_node}")
    headers = {"X-Trace-ID": trace_id_var.get(), "X-Network-Zone": "PRIVATE_VPC" if payload.is_sensitive else "PUBLIC", "X-From": "cloud"}

    async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
        try:
            resp = await client.post(f"{target_node}/store", json=payload.model_dump(), headers=headers)
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Target node {target_node} unavailable: {exc}")

@app.get("/api/v1/read/{key}")
async def read_data(key: str):
    """Directly routes request to partition hosting the key."""
    target_node = get_target_node_for_key(key)
    headers = {"X-Trace-ID": trace_id_var.get(), "X-From": "cloud"}

    async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
        try:
            resp = await client.get(f"{target_node}/read/{key}", headers=headers)
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail=f"Worker node {target_node} unavailable.")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Key not found in distributed store.")
        return resp.json()


# ---------------------------------------------------------------- monitoring
async def monitor_loop():
    """Every 2 seconds: alert when a machine stops sending heartbeats."""
    while True:
        await asyncio.sleep(2)
        if cloud_down:
            continue
        for mid, last_seen in db.execute("SELECT machine_id, last_seen FROM machines").fetchall():
            if time.time() - last_seen > OFFLINE_AFTER and mid not in offline_alerted:
                offline_alerted[mid] = time.time()
                trace_id_var.set(generate_trace_id())
                event(f"ALERT: {mid} is OFFLINE (no heartbeat for {OFFLINE_AFTER}s). Its data here may be outdated.", "WARN")


@app.on_event("startup")
async def startup():
    event(f"Cloud started. Watching {len(WORKER_NODES)} machines.")
    asyncio.create_task(monitor_loop())


# ---------------------------------------------------------------- simulation + page
@app.post("/sim/cloud-down")
async def set_cloud_down(req: Switch):
    global cloud_down
    cloud_down = req.on
    if not cloud_down:  # give machines a moment to report in before marking them offline
        db.execute("UPDATE machines SET last_seen=?", (time.time(),))
    event("Cloud is DOWN (simulated)." if cloud_down else "Cloud is back UP.", "WARN" if cloud_down else "INFO")
    return {"cloud_down": cloud_down}


@app.post("/sim/sync-fails")
async def set_sync_fails(req: Switch):
    global sync_fails
    sync_fails = req.on
    event("Sync failure mode ON." if sync_fails else "Sync failure mode OFF.", "WARN" if sync_fails else "INFO")
    return {"sync_fails": sync_fails}


@app.get("/sim/status")
async def sim_status():
    return {"cloud_down": cloud_down, "sync_fails": sync_fails}


@app.get("/logs")
async def logs():
    return list(EVENTS)


@app.get("/")
async def page():
    return FileResponse("web/index.html")


@app.get("/world.js")
async def world_js():
    return FileResponse("web/world.js", media_type="text/javascript")
