import os
import time
import json
import asyncio
import sqlite3
import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from common.models import DataPayload, SystemHealth, DistributedResponse
from common.models import ConsultRequest, BuyRequest, Switch, Record
from common.logger import get_logger, trace_id_var, generate_trace_id, log_event, EVENTS

NODE_ID = os.getenv("NODE_ID", "Worker-Default")
PORT = int(os.getenv("PORT", "8001"))
IS_PRIVATE_NODE = os.getenv("IS_PRIVATE", "false").lower() == "true"
CLOUD_URL = os.getenv("CLOUD_URL", "http://127.0.0.1:8000")   # MENDO
API_KEY = os.getenv("API_KEY", "")                            # MENDO

app = FastAPI(title=f"Worker Node {NODE_ID}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
logger = get_logger(NODE_ID)

local_store: dict[str, str] = {}

@app.middleware("http")
async def trace_and_security_middleware(request: Request, call_next):
    # 1. Trace ID Extraction
    trace_id = request.headers.get("X-Trace-ID", "NO_TRACE_ID")
    trace_id_var.set(trace_id)

    # 2. Cloud Deployment Model Simulation (Private Cloud / VPC Middleware Security Check)
    if IS_PRIVATE_NODE and request.url.path in ["/store", "/read"]:
        network_zone = request.headers.get("X-Network-Zone")
        if network_zone != "PRIVATE_VPC":
            logger.warning("Access denied: Private VPC Token missing.")
            return JSONResponse(status_code=403, content={"detail": "Forbidden: Node reachable only via Private Cloud VPC network."})

    # MENDO: requests from the cloud travel over the internet, so they fail while this machine is offline
    if request.headers.get("X-From") == "cloud" and not online:
        return JSONResponse(status_code=503, content={"detail": "machine offline"})

    polling = request.url.path in ["/state", "/logs"]   # MENDO: don't log the page's refresh polling
    if not polling:
        logger.info(f"Processing request: {request.method} {request.url.path}")
    start = time.perf_counter()
    response = await call_next(request)
    if not polling and request.scope.get("route") is not None:   # MENDO: log every API call this machine receives
        caller = "cloud" if request.headers.get("X-From") == "cloud" else "screen"
        log_event(logger, NODE_ID, f"<- {request.method} {request.url.path} from {caller}: {response.status_code} "
                  f"({(time.perf_counter() - start) * 1000:.0f} ms)", kind="api")
    response.headers["X-Trace-ID"] = trace_id
    return response

# Check status of all nodes
@app.get("/health", response_model=SystemHealth)
async def health_check():
    return SystemHealth(
        status="HEALTHY",
        node_id=NODE_ID,
        stored_keys_count=len(local_store)
    )

@app.post("/store", response_model=DistributedResponse)
async def store_data(payload: DataPayload, x_trace_id: str = Header(default="")):
    # Simulate low LAN latency for internal nodes vs WAN latency
    await asyncio.sleep(0.02)
    local_store[payload.key] = str(payload.value)
    logger.info(f"Stored key '{payload.key}' successfully.")

    return DistributedResponse(
        status="SUCCESS",
        node_id=NODE_ID,
        message=f"Key '{payload.key}' stored on node {NODE_ID}",
        data={"key": payload.key, "value": payload.value},
        trace_id=trace_id_var.get()
    )

@app.get("/read/{key}", response_model=DistributedResponse)
async def read_data(key: str, simulate_delay: float = 0.0):
    if simulate_delay > 0:
        logger.info(f"Simulating network latency delay of {simulate_delay}s...")
        await asyncio.sleep(simulate_delay)

    if key not in local_store:
        raise HTTPException(status_code=404, detail="Key not found on this node")

    return DistributedResponse(
        status="SUCCESS",
        node_id=NODE_ID,
        message="Data retrieved",
        data={"key": key, "value": local_store[key]},
        trace_id=trace_id_var.get()
    )

@app.post("/compute-parallel")
async def heavy_computation_task(data_item: int):
    """Simulates parallel execution workloads on individual worker nodes."""
    await asyncio.sleep(0.15)
    result = data_item * data_item
    return {"node_id": NODE_ID, "input": data_item, "result": result}


# =============================================================================
# Added for MENDO: the vending machine itself
# =============================================================================

def event(message, level="INFO"):
    log_event(logger, NODE_ID, message, level)

# The 10 medicine slots (same as the thesis machine)
MEDICINES = {
    "Biogesic":   {"slot": 1,  "treats": ["fever", "headache"],  "min_age": 2,  "price": 5},
    "Bioflu":     {"slot": 2,  "treats": ["colds", "fever"],     "min_age": 7,  "price": 12},
    "Medicol":    {"slot": 3,  "treats": ["body pain", "headache"], "min_age": 12, "price": 8},
    "Solmux":     {"slot": 4,  "treats": ["phlegm"],             "min_age": 12, "price": 12},
    "Sinecod":    {"slot": 5,  "treats": ["dry cough"],          "min_age": 13, "price": 10},
    "Symdex-D":   {"slot": 6,  "treats": ["stuffy nose"],        "min_age": 6,  "price": 10},
    "Cetirizine": {"slot": 7,  "treats": ["allergy"],            "min_age": 6,  "price": 5},
    "Diatabs":    {"slot": 8,  "treats": ["diarrhea"],           "min_age": 12, "price": 11},
    "Kremil-S":   {"slot": 9,  "treats": ["acidity"],            "min_age": 12, "price": 8},
    "Buscopan":   {"slot": 10, "treats": ["cramps"],             "min_age": 6,  "price": 8},
}
KEYWORDS = {  # English / Tagalog / Bisaya
    "fever": ["fever", "lagnat", "hilanat"],
    "headache": ["headache", "sakit ng ulo", "masakit ulo", "sakit ulo", "labad"],
    "body pain": ["body pain", "masakit katawan", "masakit ang katawan", "sakit sa lawas", "nangangalay"],
    "phlegm": ["phlegm", "plema"],
    "dry cough": ["dry cough", "ubo", "cough"],
    "colds": ["colds", "sipon", "runny nose"],
    "stuffy nose": ["stuffy nose", "barado ilong", "barado ang ilong"],
    "allergy": ["allergy", "sneezing", "bahing", "pantal", "kati"],
    "diarrhea": ["diarrhea", "nagtatae", "lbm", "kalibanga"],
    "acidity": ["hyperacidity", "heartburn", "sikmura", "acid"],
    "cramps": ["cramps", "hilab", "humihilab"],
}
RED_FLAGS = ["chest pain", "difficulty breathing", "hirap huminga", "seizure", "dugo", "blood"]


def recommend(text, age, stock):
    """Simplified version of the thesis recommender (rules only)."""
    t = text.lower()
    if any(flag in t for flag in RED_FLAGS):
        return {"action": "REFER", "message": "Possible emergency. Please see a doctor."}
    symptoms = [s for s, words in KEYWORDS.items() if any(w in t for w in words)]
    if not symptoms:
        return {"action": "NO_MATCH", "message": "Sorry, I did not understand the symptoms."}
    for name, med in MEDICINES.items():
        if any(s in med["treats"] for s in symptoms) and age >= med["min_age"] and stock[name] > 0:
            return {"action": "RECOMMEND", "symptoms": symptoms, "medicine": name,
                    "slot": med["slot"], "price": med["price"]}
    return {"action": "REFER", "symptoms": symptoms, "message": "No suitable medicine available. Please see a pharmacist."}


# ---------------------------------------------------------------- local database
os.makedirs("data", exist_ok=True)
db = sqlite3.connect(f"data/{NODE_ID}.db", check_same_thread=False, isolation_level=None)
db.execute("CREATE TABLE IF NOT EXISTS stock(medicine TEXT PRIMARY KEY, qty INTEGER)")
db.execute("CREATE TABLE IF NOT EXISTS queue(seq INTEGER PRIMARY KEY, type TEXT, data TEXT, created_at REAL, synced INTEGER DEFAULT 0)")
for name in MEDICINES:
    db.execute("INSERT OR IGNORE INTO stock VALUES(?, 10)", (name,))

def get_stock():
    rows = dict(db.execute("SELECT medicine, qty FROM stock").fetchall())
    return {name: rows[name] for name in MEDICINES}   # slot order

def save_record(rtype, data):
    """Every action is saved locally first. It is sent to the cloud later."""
    cur = db.execute("INSERT INTO queue(type, data, created_at) VALUES(?,?,?)", (rtype, json.dumps(data), time.time()))
    return cur.lastrowid

def queued_count():
    return db.execute("SELECT COUNT(*) FROM queue WHERE synced=0").fetchone()[0]

def last_seq():
    return db.execute("SELECT COALESCE(MAX(seq),0) FROM queue").fetchone()[0]


# ---------------------------------------------------------------- state
online = True          # simulated internet connection of this machine
cloud_ok = True        # did the last contact with the cloud work?
last_sync = None
stock_lock = asyncio.Lock()   # two customers can't buy the same last item
client = None


def api_log(message, level="INFO"):
    log_event(logger, NODE_ID, message, level, kind="api")


async def send_to_cloud(path, body):
    """Every call this machine makes to the cloud goes through here and is logged."""
    if not online:
        api_log(f"-> POST cloud{path}: failed (no internet)", "WARN")
        raise ConnectionError("no internet")
    headers = {"X-API-Key": API_KEY, "X-Trace-ID": trace_id_var.get()}
    start = time.perf_counter()
    try:
        r = await client.post(CLOUD_URL + path, json=body, headers=headers, timeout=3)
    except httpx.HTTPError:
        api_log(f"-> POST cloud{path}: failed (cloud not reachable)", "WARN")
        raise
    ms = (time.perf_counter() - start) * 1000
    api_log(f"-> POST cloud{path}: {r.status_code} ({ms:.0f} ms)", "INFO" if r.status_code < 400 else "WARN")
    r.raise_for_status()
    return r.json()


async def sync_loop():
    """Every 3 seconds: heartbeat, then send queued records."""
    global cloud_ok, last_sync
    while True:
        await asyncio.sleep(3)
        trace_id_var.set(generate_trace_id())
        try:
            # 1. heartbeat
            reply = await send_to_cloud("/api/heartbeat", {
                "machine_id": NODE_ID, "stock": get_stock(), "queued": queued_count(), "last_seq": last_seq()})
            if not cloud_ok:
                event(f"Connected to cloud again. Sending {queued_count()} queued records.")
            cloud_ok = True

            # If the cloud lost records (restored from backup), send them again.
            cloud_has = reply["cloud_has_up_to"]
            resent = db.execute("UPDATE queue SET synced=0 WHERE seq>? AND synced=1", (cloud_has,)).rowcount
            if resent:
                event(f"Cloud is missing records after #{cloud_has}. Sending {resent} records again.", "WARN")

            # 2. send queued records
            rows = db.execute("SELECT seq, type, data, created_at FROM queue WHERE synced=0 ORDER BY seq LIMIT 50").fetchall()
            if rows:
                records = [Record(record_id=f"{NODE_ID}-{seq}", machine_id=NODE_ID, seq=seq, type=t,
                                  data=json.loads(d), created_at=c).model_dump() for seq, t, d, c in rows]
                result = await send_to_cloud("/api/sync", {"machine_id": NODE_ID, "records": records})
                db.executemany("UPDATE queue SET synced=1 WHERE seq=?", [(r[0],) for r in rows])
                last_sync = time.time()
                event(f"Synced {len(rows)} records to cloud ({result['duplicates']} were already there).")
        except Exception:
            if cloud_ok:
                reason = "no internet" if not online else "cloud not responding"
                event(f"Cannot reach cloud ({reason}). Working offline; records are queued locally.", "WARN")
            cloud_ok = False


@app.on_event("startup")
async def startup():
    global client
    client = httpx.AsyncClient(trust_env=False)
    event(f"{NODE_ID} started with {queued_count()} queued records from before.")
    asyncio.create_task(sync_loop())


@app.post("/consult")
async def consult(req: ConsultRequest):
    """Customer types symptoms; the machine recommends a medicine (works offline)."""
    result = recommend(req.text, req.age, get_stock())
    seq = save_record("CONSULTATION", {"symptoms": result.get("symptoms", []), "action": result["action"]})
    event(f"Consultation #{seq}: '{req.text}' (age {req.age}) -> {result.get('medicine') or result['action']}")
    return result


@app.post("/buy")
async def buy(req: BuyRequest):
    """Dispense one medicine. The lock keeps parallel buyers from overselling."""
    if req.medicine not in MEDICINES:
        raise HTTPException(404, "Unknown medicine")
    async with stock_lock:
        if get_stock()[req.medicine] <= 0:
            event(f"Sale refused: {req.medicine} is out of stock.", "WARN")
            raise HTTPException(409, f"{req.medicine} is out of stock")
        db.execute("UPDATE stock SET qty = qty - 1 WHERE medicine=?", (req.medicine,))
        await asyncio.sleep(0.3)  # dispensing motor
    price = MEDICINES[req.medicine]["price"]
    seq = save_record("SALE", {"medicine": req.medicine, "price": price})
    event(f"Sale #{seq}: dispensed {req.medicine} from slot {MEDICINES[req.medicine]['slot']} (PHP {price}).")
    left = get_stock()[req.medicine]
    if left <= 2:
        event(f"Low stock: {req.medicine} has {left} left.", "WARN")
    return {"medicine": req.medicine, "price": price, "left": left}


@app.post("/restock")
async def restock():
    """Staff refills the machine."""
    async with stock_lock:
        db.execute("UPDATE stock SET qty = 10")
    seq = save_record("RESTOCK", {"qty": 10})
    event(f"Restock #{seq}: all 10 slots refilled to 10.")
    return get_stock()


@app.post("/network")
async def set_network(req: Switch):
    """Simulation: turn this machine's internet on or off."""
    global online
    online = req.on
    event("Internet turned ON." if online else "Internet turned OFF.", "INFO" if online else "WARN")
    return {"online": online}


@app.get("/state")
async def state():
    return {"machine_id": NODE_ID, "online": online, "cloud_ok": cloud_ok, "stock": get_stock(),
            "queued": queued_count(), "last_seq": last_seq(), "last_sync": last_sync}


@app.get("/logs")
async def logs():
    return list(EVENTS)
