"""Inspect and manually approve or revoke local knowledge records."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .ingest_knowledge import OUTPUT_PATH


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: dict) -> None:
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(content, encoding="utf-8")


def find(payload: dict, document_id: str) -> dict:
    for record in payload.get("records", []):
        if record.get("document_id") == document_id:
            return record
    raise SystemExit(f"Unknown document ID: {document_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "show", "approve", "revoke"))
    parser.add_argument("document_id", nargs="?")
    parser.add_argument("--path", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--status", choices=("pending_review", "approved"))
    args = parser.parse_args()
    payload = load(args.path)
    if args.action == "list":
        for record in payload.get("records", []):
            if not args.status or record.get("approval_status") == args.status:
                print(
                    record["document_id"],
                    record["approval_status"],
                    record["section_heading"],
                    record["source_url"],
                )
    else:
        if not args.document_id:
            parser.error("document_id is required for show, approve and revoke")
        record = find(payload, args.document_id)
        if args.action == "show":
            print(json.dumps(record, indent=2, ensure_ascii=False))
        else:
            record["approval_status"] = "approved" if args.action == "approve" else "pending_review"
            record["last_reviewed_at"] = (
                datetime.now(timezone.utc).isoformat() if args.action == "approve" else None
            )
            save(args.path, payload)
            print(f"{record['document_id']} is now {record['approval_status']}.")


if __name__ == "__main__":
    main()
