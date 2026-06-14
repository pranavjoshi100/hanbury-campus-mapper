"""
JSON API routes.

This file contains all `/api/*` endpoints used by the UI:
- Maps CRUD + activation
- Route saving (drawn routes)
- Filtering, exports, visualization aggregation
- Heatmaps over campus map images
"""

from __future__ import annotations

import base64
import io
import json
import os
import uuid
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ..db import get_db_connection
from ..services.geo import calculate_distance_km, sample_points_along_segment

api_bp = Blueprint("api", __name__)


@api_bp.get("/active-campus-map")
def get_active_campus_map():
    try:
        conn = get_db_connection(current_app)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, image_filename, north_lat, south_lat, east_lng, west_lng, is_active
            FROM campus_maps
            WHERE is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        result = cursor.fetchone()
        conn.close()

        if not result:
            return jsonify({"success": True, "map": None})

        return jsonify(
            {
                "success": True,
                "map": {
                    "id": result[0],
                    "name": result[1],
                    "image_filename": result[2],
                    "bounds_north": result[3],
                    "bounds_south": result[4],
                    "bounds_east": result[5],
                    "bounds_west": result[6],
                    "is_active": bool(result[7]),
                },
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.get("/campus-maps")
def get_all_campus_maps():
    try:
        conn = get_db_connection(current_app)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, image_filename, north_lat, south_lat, east_lng, west_lng, is_active, created_at
            FROM campus_maps
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
        conn.close()
        return jsonify({"success": True, "maps": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.post("/upload-campus-map")
def upload_campus_map():
    try:
        name = request.form["name"]
        image_file = request.files["image_file"]

        if not image_file:
            return jsonify({"success": False, "error": "No image file provided"}), 400

        allowed_extensions = {"jpg", "jpeg", "png"}
        filename = secure_filename(image_file.filename)
        file_ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
        if file_ext not in allowed_extensions:
            return jsonify({"success": False, "error": "Only JPG and PNG files are allowed"}), 400

        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        image_path = os.path.join("maps", unique_filename)
        image_file.save(image_path)

        north_lat = request.form.get("north_lat")
        south_lat = request.form.get("south_lat")
        east_lng = request.form.get("east_lng")
        west_lng = request.form.get("west_lng")

        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        cursor.execute("UPDATE campus_maps SET is_active = 0")
        cursor.execute(
            """
            INSERT INTO campus_maps (name, image_filename, north_lat, south_lat, east_lng, west_lng, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                unique_filename,
                float(north_lat) if north_lat else None,
                float(south_lat) if south_lat else None,
                float(east_lng) if east_lng else None,
                float(west_lng) if west_lng else None,
                1,
            ),
        )

        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Campus map uploaded successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.post("/activate-campus-map")
def activate_campus_map():
    try:
        data = request.get_json(force=True)
        map_id = data["map_id"]
        conn = get_db_connection(current_app)
        cursor = conn.cursor()
        cursor.execute("UPDATE campus_maps SET is_active = 0")
        cursor.execute("UPDATE campus_maps SET is_active = 1 WHERE id = ?", (map_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Campus map activated successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.post("/delete-campus-map")
def delete_campus_map():
    try:
        data = request.get_json(force=True)
        map_id = int(data["map_id"])

        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        cursor.execute("SELECT image_filename, is_active FROM campus_maps WHERE id = ?", (map_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": "Map not found"}), 404

        image_filename = row["image_filename"]
        was_active = bool(row["is_active"])

        cursor.execute("DELETE FROM campus_maps WHERE id = ?", (map_id,))

        if was_active:
            cursor.execute(
                """
                UPDATE campus_maps
                SET is_active = 1
                WHERE id = (SELECT id FROM campus_maps ORDER BY created_at DESC LIMIT 1)
                """
            )

        conn.commit()
        conn.close()

        try:
            map_path = os.path.join("maps", image_filename)
            if os.path.exists(map_path):
                os.remove(map_path)
        except Exception:
            pass

        return jsonify({"success": True, "message": "Campus map deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.get("/maps/<int:map_id>/image")
def serve_map_image_by_id(map_id: int):
    try:
        conn = get_db_connection(current_app)
        cursor = conn.cursor()
        cursor.execute("SELECT image_filename FROM campus_maps WHERE id = ?", (map_id,))
        result = cursor.fetchone()
        conn.close()
        if not result:
            return jsonify({"error": "Map not found"}), 404
        return send_from_directory("maps", result[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.post("/save-route-drawn")
def save_route_drawn():
    """Save a drawn route; store full path in `drawn_segments` and segment endpoints in `routes`."""
    try:
        data = request.get_json(force=True)
        route_id = data["routeId"]
        segments = data["segments"]
        user_data = data["userData"]
        campus_map_id = data.get("campus_map_id")

        user_type = (user_data.get("userType") or "").strip()
        grade_level = (user_data.get("gradeLevel") or "").strip()
        if user_type != "student":
            grade_level = None
        elif grade_level == "":
            grade_level = None

        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        for idx, segment in enumerate(segments):
            path = segment.get("path") or []
            if len(path) < 2:
                continue

            start = path[0]
            end = path[-1]
            distance = calculate_distance_km(start["lat"], start["lng"], end["lat"], end["lng"])

            cursor.execute(
                """
                INSERT INTO routes (
                    timestamp, route_id, segment_id, start_lat, start_lng,
                    end_lat, end_lng, transport_mode, distance_km, duration_seconds,
                    duration_minutes, segment_type, user_type, grade_level,
                    department, full_name, campus_map_id
                )
                VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    idx + 1,
                    start["lat"],
                    start["lng"],
                    end["lat"],
                    end["lng"],
                    segment["transportMode"],
                    distance,
                    segment.get("durationSeconds") or 0,
                    round((segment.get("durationSeconds") or 0) / 60, 2),
                    "stopping",
                    user_type,
                    grade_level,
                    user_data.get("department", ""),
                    user_data.get("fullName", ""),
                    campus_map_id,
                ),
            )

            cursor.execute(
                """
                INSERT INTO drawn_segments (
                    route_id, segment_index, transport_mode,
                    coordinates, duration_seconds, user_type, campus_map_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    idx + 1,
                    segment["transportMode"],
                    json.dumps(path),
                    segment.get("durationSeconds") or 0,
                    user_type,
                    campus_map_id,
                ),
            )

        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Drawn route saved successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.get("/visualization/data")
def get_visualization_data():
    """Return aggregated segments for a map based on filters."""
    try:
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        transport_mode = request.args.get("transport_mode")
        campus_map_id = request.args.get("campus_map_id")
        if not campus_map_id:
            return jsonify({"success": False, "error": "campus_map_id is required"}), 400

        conn = get_db_connection(current_app)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campus_maps WHERE id = ?", (campus_map_id,))
        map_row = cursor.fetchone()
        if not map_row:
            conn.close()
            return jsonify({"success": False, "error": "Map not found"}), 404
        map_data = dict(map_row)

        query = """
            SELECT ds.transport_mode, ds.coordinates, ds.created_at
            FROM drawn_segments ds
            WHERE ds.campus_map_id = ?
        """
        params: list[object] = [int(campus_map_id)]

        if start_date:
            query += " AND DATE(ds.created_at) >= ?"
            params.append(start_date)
        if end_date:
            query += " AND DATE(ds.created_at) <= ?"
            params.append(end_date)
        if transport_mode:
            query += " AND ds.transport_mode = ?"
            params.append(transport_mode)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        aggregated: dict[str, dict[str, object]] = {}
        for row in rows:
            try:
                coords = json.loads(row["coordinates"])
                rounded_coords = [
                    {"lat": round(c.get("lat", 0.0), 5), "lng": round(c.get("lng", 0.0), 5)} for c in coords
                ]
                key = f"{row['transport_mode']}_{json.dumps(rounded_coords)}"
                if key not in aggregated:
                    aggregated[key] = {
                        "transport_mode": row["transport_mode"],
                        "coordinates": coords,
                        "frequency": 0,
                    }
                aggregated[key]["frequency"] = int(aggregated[key]["frequency"]) + 1
            except Exception:
                continue

        return jsonify({"success": True, "segments": list(aggregated.values()), "map_data": map_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.get("/heatmaps/generate")
def generate_heatmaps():
    """Generate heatmap PNGs (base64) overlaid on the map image."""
    try:
        campus_map_id = request.args.get("campus_map_id")
        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        map_data = None
        if campus_map_id:
            cursor.execute("SELECT * FROM campus_maps WHERE id = ?", (campus_map_id,))
            r = cursor.fetchone()
            if r:
                map_data = dict(r)
        else:
            cursor.execute("SELECT * FROM campus_maps WHERE is_active = 1 LIMIT 1")
            r = cursor.fetchone()
            if r:
                map_data = dict(r)

        heatmaps = []
        for mode in ["car", "walking", "micromodal"]:
            query = """
                SELECT start_lat, start_lng, end_lat, end_lng
                FROM routes
                WHERE transport_mode = ?
                AND (
                    (start_lat IS NOT NULL AND start_lng IS NOT NULL)
                    OR
                    (end_lat IS NOT NULL AND end_lng IS NOT NULL)
                )
            """
            params = [mode]
            if map_data:
                query += " AND campus_map_id = ?"
                params.append(map_data["id"])

            cursor.execute(query, params)
            pts = cursor.fetchall()
            if not pts:
                heatmaps.append({"mode": mode, "image_data": None, "message": f"No data available for {mode}"})
                continue

            lats: list[float] = []
            lngs: list[float] = []
            for p in pts:
                if p["start_lat"] and p["start_lng"]:
                    lats.append(p["start_lat"])
                    lngs.append(p["start_lng"])
                if p["end_lat"] and p["end_lng"]:
                    lats.append(p["end_lat"])
                    lngs.append(p["end_lng"])

            if not lats:
                heatmaps.append({"mode": mode, "image_data": None, "message": f"No valid stopping points for {mode}"})
                continue

            fig, ax = plt.subplots(figsize=(12, 10))
            if map_data and map_data.get("image_filename"):
                try:
                    from PIL import Image

                    map_path = os.path.join("maps", map_data["image_filename"])
                    if os.path.exists(map_path):
                        map_img = Image.open(map_path)
                        west = map_data.get("west_lng") or (min(lngs) - 0.01)
                        east = map_data.get("east_lng") or (max(lngs) + 0.01)
                        south = map_data.get("south_lat") or (min(lats) - 0.01)
                        north = map_data.get("north_lat") or (max(lats) + 0.01)
                        ax.imshow(map_img, extent=[west, east, south, north], aspect="auto", alpha=0.7)
                        if all([map_data.get("west_lng"), map_data.get("east_lng"), map_data.get("south_lat"), map_data.get("north_lat")]):
                            ax.set_xlim(map_data["west_lng"], map_data["east_lng"])
                            ax.set_ylim(map_data["south_lat"], map_data["north_lat"])
                except Exception:
                    pass

            hb = ax.hexbin(lngs, lats, gridsize=30, cmap="hot_r", alpha=0.8, mincnt=1)
            plt.colorbar(hb, ax=ax, label="Density")
            ax.set_xlabel("Longitude")
            ax.set_ylabel("Latitude")
            ax.set_title(f"Stopping Points Heatmap - {mode.capitalize()}")
            ax.invert_yaxis()
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            buf.seek(0)
            image_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            heatmaps.append({"mode": mode, "image_data": f"data:image/png;base64,{image_data}"})

        conn.close()
        return jsonify({"success": True, "heatmaps": heatmaps})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.get("/heatmaps/download/<mode>")
def download_heatmap(mode: str):
    """Download a heatmap as PNG with optional map overlay."""
    try:
        campus_map_id = request.args.get("campus_map_id")
        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        map_data = None
        if campus_map_id:
            cursor.execute("SELECT * FROM campus_maps WHERE id = ?", (campus_map_id,))
            r = cursor.fetchone()
            if r:
                map_data = dict(r)

        query = """
            SELECT start_lat, start_lng, end_lat, end_lng
            FROM routes
            WHERE transport_mode = ?
            AND (
                (start_lat IS NOT NULL AND start_lng IS NOT NULL)
                OR
                (end_lat IS NOT NULL AND end_lng IS NOT NULL)
            )
        """
        params = [mode]
        if map_data:
            query += " AND campus_map_id = ?"
            params.append(map_data["id"])

        cursor.execute(query, params)
        pts = cursor.fetchall()
        conn.close()
        if not pts:
            return jsonify({"error": f"No data available for {mode}"}), 404

        lats: list[float] = []
        lngs: list[float] = []
        for p in pts:
            if p["start_lat"] and p["start_lng"]:
                lats.append(p["start_lat"])
                lngs.append(p["start_lng"])
            if p["end_lat"] and p["end_lng"]:
                lats.append(p["end_lat"])
                lngs.append(p["end_lng"])

        fig, ax = plt.subplots(figsize=(12, 10))
        if map_data and map_data.get("image_filename"):
            try:
                from PIL import Image

                map_path = os.path.join("maps", map_data["image_filename"])
                if os.path.exists(map_path):
                    map_img = Image.open(map_path)
                    west = map_data.get("west_lng") or (min(lngs) - 0.01)
                    east = map_data.get("east_lng") or (max(lngs) + 0.01)
                    south = map_data.get("south_lat") or (min(lats) - 0.01)
                    north = map_data.get("north_lat") or (max(lats) + 0.01)
                    ax.imshow(map_img, extent=[west, east, south, north], aspect="auto", alpha=0.7)
                    if all([map_data.get("west_lng"), map_data.get("east_lng"), map_data.get("south_lat"), map_data.get("north_lat")]):
                        ax.set_xlim(map_data["west_lng"], map_data["east_lng"])
                        ax.set_ylim(map_data["south_lat"], map_data["north_lat"])
            except Exception:
                pass

        hb = ax.hexbin(lngs, lats, gridsize=30, cmap="hot_r", alpha=0.8, mincnt=1)
        plt.colorbar(hb, ax=ax, label="Density")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title(f"Stopping Points Heatmap - {mode.capitalize()}")
        ax.invert_yaxis()
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)

        return send_file(
            buf,
            mimetype="image/png",
            as_attachment=True,
            download_name=f"{mode}_stopping_points_heatmap_{datetime.now().strftime('%Y%m%d')}.png",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.get("/test-database")
def test_database():
    try:
        conn = get_db_connection(current_app)
        cursor = conn.cursor()
        cursor.execute("SELECT sqlite_version();")
        version = cursor.fetchone()
        conn.close()
        return jsonify({"success": True, "message": "SQLite database connected successfully", "version": version[0]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Static map image passthrough used by the user-facing map overlay
@api_bp.get("/maps-file/<filename>")
def serve_map_image(filename: str):
    return send_from_directory("maps", filename)

