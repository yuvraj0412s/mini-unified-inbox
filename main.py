from fastapi import FastAPI
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List, Optional
import json

app = FastAPI(title="Mini Unified Inbox System")

@app.get("/")
def root():
    return {
        "message": "Mini Unified Inbox API is running",
        "docs": "http://127.0.0.1:8000/docs"
    }

#moderls
class Email(BaseModel):
    id: str
    thread_id: str
    from_email: str
    to: List[str]
    timestamp: str
    subject: Optional[str]
    body: Optional[str]

class Thread(BaseModel):
    thread_id: str
    emails: List[Email]
    lead_email: str
    assigned_sdr: Optional[str]
    state: str
    last_activity: str
    sla_breached: bool

class SDR(BaseModel):
    id: str
    name: str
    max_active_threads: int
    active_threads: int

class Lead(BaseModel):
    email: str
    company: str
    status: str
    last_contacted_at: str

# Load Input Data

with open("emails.json") as f:
    raw_emails = json.load(f)

emails = []
for e in raw_emails:
    emails.append({
        "id": e["id"],
        "thread_id": e["thread_id"],
        "from_email": e["from"],
        "to": e["to"],
        "timestamp": e["timestamp"],
        "subject": e.get("subject"),
        "body": e.get("body")
    })

with open("sdrs.json") as f:
    sdrs = json.load(f)

with open("leads.json") as f:
    leads = json.load(f)

# In-Memory Stores

threads = {}
lead_map = {lead["email"]: lead for lead in leads}
sdr_map = {
    sdr["id"]: {**sdr, "active_threads": 0}
    for sdr in sdrs
}

# Helper Functions

def parse_time(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", ""))

def get_least_loaded_sdr():
    eligible = [
        sdr for sdr in sdr_map.values()
        if sdr["active_threads"] < sdr["max_active_threads"]
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda s: s["active_threads"])

# Core Logic

# 1. Grouping of emails into threadds
for email in emails:
    t_id = email["thread_id"]

    if t_id not in threads:
        threads[t_id] = {
            "thread_id": t_id,
            "emails": [],
            "lead_email": None,
            "assigned_sdr": None,
            "state": "new",
            "last_activity": None,
            "sla_breached": False
        }

    threads[t_id]["emails"].append(email)

# 2. Processing of  each thread
for thread in threads.values():
    # Sort emails by timestamp
    thread["emails"].sort(key=lambda e: parse_time(e["timestamp"]))
    last_email = thread["emails"][-1]
    thread["last_activity"] = last_email["timestamp"]

    lead_email = last_email["from_email"]
    thread["lead_email"] = lead_email

    # Lead mapping
    if lead_email not in lead_map:
        lead_map[lead_email] = {
            "email": lead_email,
            "company": "Unknown",
            "status": "new",
            "last_contacted_at": last_email["timestamp"]
        }
    else:
        lead_map[lead_email]["last_contacted_at"] = last_email["timestamp"]

    # Conversation state logic
    if "leandex@gmail.com" in last_email.get("to", []):
        thread["state"] = "waiting_on_sdr"
        lead_map[lead_email]["status"] = "contacted"
    else:
        thread["state"] = "waiting_on_lead"
        lead_map[lead_email]["status"] = "engaged"

    # SLA check if>24 hours-> breached
    if datetime.utcnow() - parse_time(last_email["timestamp"]) > timedelta(hours=24):
        thread["sla_breached"] = True

# 3. SDR 
for thread in threads.values():
    if thread["assigned_sdr"] is None and thread["state"] != "closed":
        sdr = get_least_loaded_sdr()
        if sdr:
            thread["assigned_sdr"] = sdr["id"]
            sdr["active_threads"] += 1

# API Endpoints

@app.get("/inbox", response_model=List[Thread])
def get_inbox():
    """
    Returns all conversation threads sorted by latest activity
    """
    return sorted(
        threads.values(),
        key=lambda t: parse_time(t["last_activity"]),
        reverse=True
    )

@app.get("/sdrs", response_model=List[SDR])
def get_sdrs():
    """
    Returns SDRs with active thread count
    """
    return list(sdr_map.values())

@app.get("/leads", response_model=List[Lead])
def get_leads():
    """
    Returns leads with status and last contact date
    """
    return list(lead_map.values())
