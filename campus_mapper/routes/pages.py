"""
HTML page routes.

These render templates for:
- User-facing mapper (`/`)
- Admin/dashboard (`/dashboard`)
"""

from __future__ import annotations

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def index():
    return render_template("index.html")


@pages_bp.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")

