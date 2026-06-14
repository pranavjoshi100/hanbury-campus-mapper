"""
Campus Mapper Flask application package.

This package contains:
- App factory (`create_app`)
- Database initialization
- API routes (JSON)
- Page routes (HTML templates)

The goal is to keep the application modular and readable.
"""

from __future__ import annotations

import os
from flask import Flask

from .db import init_database
from .routes.api import api_bp
from .routes.pages import pages_bp


def create_app() -> Flask:
    """Create and configure the Flask app (app factory pattern)."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
        static_url_path="/static",
    )

    # Basic config
    app.config["UPLOAD_FOLDER"] = "uploads"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config["DATABASE"] = os.environ.get("DATABASE_PATH", "campus_mapper.db")

    # Ensure directories exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs("maps", exist_ok=True)

    # Initialize database tables
    init_database(app)

    # Register blueprints
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app

