import logging, os
from flask import Flask, jsonify
from dotenv import load_dotenv
from config import Config
from .extensions import db, login_manager

def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app); login_manager.init_app(app)
    from .models import User
    @login_manager.user_loader
    def load_user(user_id): return db.session.get(User, int(user_id))
    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.devices import bp as devices_bp
    from .routes.alerts import bp as alerts_bp
    from .routes.logs import bp as logs_bp
    for blueprint in (auth_bp, dashboard_bp, devices_bp, alerts_bp, logs_bp): app.register_blueprint(blueprint)
    @app.errorhandler(404)
    def not_found(_): return jsonify(error='Resource not found'), 404
    @app.errorhandler(403)
    def forbidden(_): return jsonify(error='Permission denied'), 403
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    return app
