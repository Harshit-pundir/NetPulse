from app import create_app
from app.services.monitoring_service import should_start_monitoring, start_scheduler

app = create_app()


if __name__ == "__main__":
    debug_mode = True
    if should_start_monitoring(app, debug_mode):
        start_scheduler(app)
    app.run(debug=debug_mode)
