import logging
import os
import secrets
import hmac

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, session

# Load .env before Config reads DATABASE_URL from the environment.
load_dotenv()

from config import Config
from .extensions import db, login_manager


def create_app(test_config=None):
    """Create and configure the NetPulse Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # Tests provide a small replacement configuration, such as an in-memory database.
    if test_config:
        app.config.update(test_config)

    if not app.testing and not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is missing. Set a long random value in .env.")
    if not app.testing and app.config.get("SECRET_KEY") in ("change-me", "dev-change-this-secret"):
        raise RuntimeError("SECRET_KEY must not use a placeholder value. Set a long random value in .env.")

    database_url = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing. Add your Supabase PostgreSQL URL to .env."
        )
    if not app.testing and not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "DATABASE_URL must use the PostgreSQL psycopg format: "
            "postgresql+psycopg://..."
        )

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)

    @app.context_processor
    def csrf_context():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"]}

    @app.before_request
    def protect_state_changes():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(400, description="The form expired or its security token was missing. Refresh and try again.")

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .routes.alerts import bp as alerts_bp
    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.devices import bp as devices_bp
    from .routes.logs import bp as logs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(logs_bp)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error="Resource not found"), 404

    @app.errorhandler(403)
    def forbidden(_error):
        return jsonify(error="Permission denied"), 403

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(error=getattr(error, "description", "Invalid request")), 400

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return app
