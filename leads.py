"""A separate confirmed demo form; it does not add steps to normal chat."""
import sqlite3
from contextlib import closing
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "leads.sqlite3"


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=200)
    need: str = Field(min_length=1, max_length=2000)
    confirmed: Literal[True]
    request_id: UUID


def save_demo(lead: DemoRequest) -> dict:
    DB_PATH.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as db:
        with db:
            # Compatible with the lead table from the earlier prototype.
            db.execute(
                """CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    request_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    company TEXT NOT NULL,
                    need TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            existing = db.execute(
                "SELECT id, name, company, need FROM leads WHERE request_id = ?",
                (str(lead.request_id),),
            ).fetchone()
            if existing:
                if existing[1:] != (lead.name, lead.company, lead.need):
                    raise ValueError("Request ID was already used for different details.")
                return {"lead_id": existing[0], "status": "saved"}
            lead_id = str(uuid4())
            db.execute(
                "INSERT INTO leads (id, request_id, name, company, need) "
                "VALUES (?, ?, ?, ?, ?)",
                (lead_id, str(lead.request_id), lead.name, lead.company, lead.need),
            )
    return {"lead_id": lead_id, "status": "saved"}
