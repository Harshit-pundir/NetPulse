"""Add an initial administrator to the existing Supabase users table if needed."""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from werkzeug.security import generate_password_hash
from app.database import supabase


def main():
    """Keep existing accounts; only add the admin when the table has no admin."""
    admins = supabase.table("users").select("id").eq("username", "admin").limit(1).execute().data or []
    if admins:
        print("An admin account already exists; no database changes were made.")
        return 0
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if len(password) < 12:
        raise RuntimeError("Set INITIAL_ADMIN_PASSWORD to at least 12 characters before creating the first admin.")
    supabase.table("users").insert({
        "username": "admin", "password_hash": generate_password_hash(password), "role": "ADMIN",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    print("Initial admin account added to the existing Supabase users table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
