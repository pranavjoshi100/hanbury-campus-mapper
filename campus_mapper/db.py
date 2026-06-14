"""
Database helpers and schema initialization.

We use SQLite for simplicity. All SQL is centralized here to keep routes clean.
"""

from __future__ import annotations

import sqlite3
from flask import Flask


def get_db_connection(app: Flask) -> sqlite3.Connection:
    """Open a SQLite connection configured for dict-like row access."""
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_database(app: Flask) -> None:
    """Create all required tables if they don't exist, and seed defaults."""
    conn = get_db_connection(app)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            route_id INTEGER NOT NULL,
            segment_id INTEGER NOT NULL,
            start_lat REAL NOT NULL,
            start_lng REAL NOT NULL,
            end_lat REAL NOT NULL,
            end_lng REAL NOT NULL,
            transport_mode TEXT NOT NULL,
            distance_km REAL NOT NULL,
            duration_seconds INTEGER NOT NULL,
            duration_minutes REAL NOT NULL,
            segment_type TEXT NOT NULL,
            user_type TEXT NOT NULL,
            grade_level TEXT,
            department TEXT,
            full_name TEXT,
            campus_map_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS campus_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            image_filename TEXT NOT NULL,
            north_lat REAL,
            south_lat REAL,
            east_lng REAL,
            west_lng REAL,
            is_active BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS congestion_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            intensity INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            campus_map_id INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS drawn_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            transport_mode TEXT NOT NULL,
            coordinates TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            user_type TEXT NOT NULL,
            campus_map_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Seed default map row if missing
    cursor.execute("SELECT COUNT(*) as c FROM campus_maps WHERE name = 'Default Campus Map'")
    if cursor.fetchone()["c"] == 0:
        cursor.execute(
            """
            INSERT INTO campus_maps (name, image_filename, is_active)
            VALUES (?, ?, ?)
            """,
            ("Default Campus Map", "campus-map.jpg", 1),
        )

    conn.commit()
    conn.close()

