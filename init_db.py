import logging
import os

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User

def add_development_data():
    """Create the initial admin only when one does not already exist."""
    if not User.query.filter_by(username="admin").first():
        password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
        if len(password) < 12:
            raise RuntimeError(
                "Set INITIAL_ADMIN_PASSWORD to at least 12 characters before initializing a new database."
            )
        db.session.add(User(username="admin", password_hash=generate_password_hash(password), role="ADMIN"))


def main():
    try:
        app = create_app({"START_MONITORING": False})
        with app.app_context():
            db.create_all()
            add_development_data()
            db.session.commit()
    except (RuntimeError, SQLAlchemyError) as error:
        logging.error("Could not initialize the database: %s", error)
        print("Database setup failed. Check DATABASE_URL in .env and your Supabase connection.")
        return 1

    print("Supabase PostgreSQL database is ready. Sign in as admin with INITIAL_ADMIN_PASSWORD.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
