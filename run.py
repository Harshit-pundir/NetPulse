import logging

from app import create_app
from app.services.monitoring_service import should_start_monitoring, start_scheduler, stop_scheduler

app = create_app()
log = logging.getLogger(__name__)


if __name__ == "__main__":
    debug_mode = True
    # Keep a single server process: Werkzeug's debug reloader can race its
    # serve_forever thread against socket shutdown on Windows.
    if should_start_monitoring(app, use_reloader=False):
        start_scheduler(app)
    try:
        app.run(debug=debug_mode, use_reloader=False)
    except KeyboardInterrupt:
        log.info("Shutdown requested")
    finally:
        stop_scheduler(app)
