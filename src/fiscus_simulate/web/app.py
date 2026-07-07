"""Flask application factory and dev/prod entry point."""
from __future__ import annotations

import argparse

from flask import Flask

from .state import AppState


def create_app(state: AppState | None = None) -> Flask:
    """Build and configure the Flask app.

    Parameters
    ----------
    state : AppState, optional
        Injected application state (defaults to a fresh :class:`AppState`). Passing one
        in keeps tests hermetic (e.g. a temp state dir).
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    app.config["APP_STATE"] = state or AppState()

    from . import routes  # noqa: F401  (side-effect: registers the blueprint)

    app.register_blueprint(routes.bp)

    @app.context_processor
    def _inject_globals() -> dict:
        return {"app_version": app.config["APP_STATE"].version}

    return app


def main() -> None:
    """Console entry point (``fiscus-simulate``): serve the app locally.

    Binds ``127.0.0.1`` by default (localhost only); ``--prod`` uses waitress.
    """
    parser = argparse.ArgumentParser(description="Run the fiscus_simulate web app.")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default localhost)")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--prod", action="store_true", help="serve with waitress (production WSGI)")
    args = parser.parse_args()

    app = create_app()
    if args.prod:
        from waitress import serve

        serve(app, host=args.host, port=args.port)
    else:
        app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
