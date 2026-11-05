"""Check the existing database and add the first admin account if needed."""
import os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models import User
from werkzeug.security import generate_password_hash


def main():
    # Do not create, drop, or rebuild tables; this project uses the existing schema.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    with SessionLocal() as session:
        if not session.query(User).filter_by(username="admin").first():
            password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
            if len(password) < 12:
                raise RuntimeError("Set INITIAL_ADMIN_PASSWORD to at least 12 characters before initializing a new database.")
            session.add(User(username="admin", password_hash=generate_password_hash(password), role="ADMIN"))
            session.commit()
    print("Database is ready. Sign in as admin with INITIAL_ADMIN_PASSWORD.")


if __name__ == "__main__": main()
