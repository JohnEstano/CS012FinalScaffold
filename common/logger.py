import logging
import os
import time
import uuid
from collections import deque
from contextvars import ContextVar

# Context Variable to store X-Trace-ID per request lifecycle
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="NO_TRACE_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Trace-ID: %(trace_id)s] %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)

class TraceLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"{msg}", {**kwargs, "extra": {"trace_id": trace_id_var.get()}}

def get_logger(name: str):
    logger = logging.getLogger(name)
    return TraceLoggerAdapter(logger, {})

def generate_trace_id() -> str:
    return str(uuid.uuid4())[:8]


# --- Added for MENDO ---------------------------------------------------------
# Every event is printed to the console, written to logs/<node>.log,
# and kept in memory so the web page can show it.
EVENTS = deque(maxlen=600)

def log_event(logger, node: str, message: str, level: str = "INFO", kind: str = "event"):
    # kind: "event" (something happened) or "api" (an API call sent or received)
    event = {"time": time.strftime("%H:%M:%S"), "ts": time.time(), "node": node, "level": level,
             "trace_id": trace_id_var.get(), "message": message, "kind": kind}
    EVENTS.append(event)
    os.makedirs("logs", exist_ok=True)
    with open(f"logs/{node}.log", "a", encoding="utf-8") as f:
        f.write(f"{event['time']} [{level}] [Trace-ID: {event['trace_id']}] {message}\n")
    if level == "WARN":
        logger.warning(message)
    else:
        logger.info(message)
