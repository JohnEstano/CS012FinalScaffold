from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class DataPayload(BaseModel):
# Standard payload contract for writing data
    key: str
    value: Any
    is_sensitive: bool = False

class SystemHealth(BaseModel):
# Status report model returned by worker health check endpoints
    status: str
    node_id: str
    active_connections: int = 0
    stored_keys_count: int = 0

class DistributedResponse(BaseModel):
# Standard unified JSON response structure across all nodes
    status: str
    node_id: str
    message: str
    data: Optional[Dict[str, Any]] = None
    trace_id: str


# --- Added for MENDO ---------------------------------------------------------

class Record(BaseModel):
# One thing that happened on a machine (consultation, sale, restock).
# machine_id + seq is unique, so the cloud can ignore duplicates.
    record_id: str
    machine_id: str
    seq: int
    type: str
    data: Dict[str, Any]
    created_at: float

class SyncBatch(BaseModel):
# Queued records a machine sends to the cloud
    machine_id: str
    records: List[Record]

class Heartbeat(BaseModel):
# "I am alive" message a machine sends every few seconds
    machine_id: str
    stock: Dict[str, int]
    queued: int
    last_seq: int

class ConsultRequest(BaseModel):
    text: str
    age: int = 25

class BuyRequest(BaseModel):
    medicine: str

class Switch(BaseModel):
    on: bool
