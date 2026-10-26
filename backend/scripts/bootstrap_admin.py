"""Assign the first administrator using trusted server credentials."""
import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")
from app.db import get_db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Exact email of an existing signed-in account")
    args = parser.parse_args()
    db = get_db()
    rows = db.table("profiles").select("id,email").eq("email", args.email.strip()).execute().data
    if len(rows) != 1:
        raise SystemExit("Expected exactly one existing profile with this email. Sign in first.")
    person = rows[0]
    db.table("profiles").update({"role": "admin", "suspended": False}).eq("id", person["id"]).execute()
    db.table("assessment_audit").insert({"actor_id": person["id"], "action": "administrator_bootstrapped",
                                       "target_id": person["id"]}).execute()
    print("Administrator assigned. Sign out and sign back in to refresh the dashboard.")


if __name__ == "__main__":
    main()
