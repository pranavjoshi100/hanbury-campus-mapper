# app.py - Complete Flask Application with All UI Improvements
from flask import Flask, render_template_string, jsonify, request, send_file, send_from_directory
import json
import csv
import os
import sqlite3
from datetime import datetime
import io
import pandas as pd
import numpy as np
from werkzeug.utils import secure_filename
import uuid
import math
import base64
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['DATABASE'] = 'campus_mapper.db'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs("maps", exist_ok=True)  # For campus map images


# Add this helper function near the top of app.py
def dms_to_decimal(dms_str):
    """Convert DMS (Degrees, Minutes, Seconds) to decimal degrees."""
    if not dms_str:
        return None
    
    # Check if already in decimal format
    try:
        return float(dms_str)
    except ValueError:
        pass
    
    # Parse DMS format: 40°42′46″N or 40°42'46"N
    dms_str = dms_str.strip().upper()
    
    # Extract direction
    direction = ''
    if dms_str.endswith('N') or dms_str.endswith('S') or dms_str.endswith('E') or dms_str.endswith('W'):
        direction = dms_str[-1]
        dms_str = dms_str[:-1]
    
    # Replace different minute/second symbols
    dms_str = dms_str.replace('′', "'").replace('″', '"').replace('°', ' ')
    
    # Split by spaces and quotes
    parts = dms_str.replace("'", ' ').replace('"', ' ').split()
    
    if len(parts) >= 1:
        degrees = float(parts[0])
        minutes = float(parts[1]) if len(parts) > 1 else 0
        seconds = float(parts[2]) if len(parts) > 2 else 0
        
        decimal = degrees + minutes/60 + seconds/3600
        
        # Adjust for direction
        if direction in ('S', 'W'):
            decimal = -decimal
        
        return decimal
    
    return None

def get_db_connection():
    """Get SQLite database connection."""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize SQLite database with required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Routes table with map_id association
    cursor.execute('''
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campus_map_id) REFERENCES campus_maps(id)
        )
    ''')
    
    # Campus maps table with IMAGE support (changed from PDF to JPG/PNG)
    cursor.execute('''
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
    ''')
    
    # Congestion data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS congestion_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            intensity INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            campus_map_id INTEGER
        )
    ''')
    
    # Table for storing drawn segments for visualization
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drawn_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            transport_mode TEXT NOT NULL,
            coordinates TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            user_type TEXT NOT NULL,
            campus_map_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campus_map_id) REFERENCES campus_maps(id)
        )
    ''')
    
    # Check for default map
    cursor.execute("SELECT COUNT(*) FROM campus_maps WHERE name = 'Default Campus Map'")
    if cursor.fetchone()[0] == 0:
        # Create default map entry
        cursor.execute('''
            INSERT INTO campus_maps (name, image_filename, is_active)
            VALUES (?, ?, ?)
        ''', ('Default Campus Map', 'campus-map.jpg', 1))
    
    conn.commit()
    conn.close()
    print("✅ SQLite database initialized successfully")

# Initialize database
init_database()

# ===============================
# MODIFIED HTML TEMPLATE WITH REQUESTED CHANGES
# ===============================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Campus Walk Mapper</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" />
    <style>
        /* ===== IMPROVED THEME WITH RED (#E4351A) ACCENTS ===== */
        :root {
            --primary-red: #E4351A;
            --primary-hover: #C12E16;
            --primary-light: rgba(228, 53, 26, 0.1);
            --sidebar-bg: #2c3e50;
            --sidebar-hover: #34495e;
            --card-bg: white;
            --text-dark: #212529;
            --text-light: #6c757d;
            --border-color: #dee2e6;
            --success: #28a745;
            --warning: #ffc107;
            --danger: #dc3545;
            --info: #17a2b8;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ed 100%);
            min-height: 100vh;
        }
        
        /* ===== MODERN HEADER ===== */
        .header {
            background: white;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            position: relative;
            z-index: 1000;
            border-bottom: 3px solid var(--primary-red);
        }
        
        .logo-container {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
.logo {
    width: 50px;
    height: 50px;
    background: white;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    box-shadow: 0 4px 8px rgba(228, 53, 26, 0.3);
    border: 2px solid var(--primary-red);
}
.logo img {
    width: 100%;
    height: 100%;
    object-fit: contain;  /* Keeps aspect ratio */
    /*padding: 5px;  /* Adds some space around the image */
}
        
        .app-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-dark);
            background: linear-gradient(90deg, var(--primary-red), #c12e16);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        /* ===== IMPROVED NAVIGATION ===== */
        .header-nav {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        
        .nav-btn {
            background: transparent;
            border: 2px solid transparent;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            color: var(--text-light);
            border-radius: 10px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .nav-btn:hover {
            background: var(--primary-light);
            color: var(--primary-red);
            transform: translateY(-2px);
        }
        
        .nav-btn.active {
            background: var(--primary-red);
            color: white;
            box-shadow: 0 4px 12px rgba(228, 53, 26, 0.3);
            border-color: var(--primary-red);
        }
        
        /* ===== MODERN MAP CONTAINER ===== */
        .map-container {
            position: relative;
            height: calc(100vh - 78px);
            width: 100%;
            padding: 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ed 100%);
        }
        
        #map {
            width: 100%;
            height: 100%;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border: 3px solid white;
            overflow: hidden;
        }
        
        /* ===== IMPROVED SEARCH BAR ===== */
        .search-bar {
            position: absolute;
            top: 40px;
            left: 40px;
            z-index: 1000;
            background: white;
            border-radius: 20px;
            padding: 14px 24px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            display: flex;
            align-items: center;
            gap: 15px;
            width: 380px;
            border: 2px solid var(--border-color);
            transition: all 0.3s ease;
        }
        
        .search-bar:focus-within {
            border-color: var(--primary-red);
            box-shadow: 0 8px 25px rgba(228, 53, 26, 0.2);
            transform: translateY(-2px);
        }
        
        .search-bar i {
            color: var(--primary-red);
            font-size: 18px;
        }
        
        .search-bar input {
            border: none;
            outline: none;
            flex: 1;
            font-size: 15px;
            background: transparent;
            color: var(--text-dark);
        }
        
        .search-bar input::placeholder {
            color: #adb5bd;
        }
        
        /* ===== ENHANCED DRAWING CONTROLS ===== */
        .drawing-controls {
            position: absolute;
            top: 100px;
            left: 40px;
            z-index: 1000;
            background: white;
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 12px 35px rgba(0,0,0,0.18);
            display: none;
            border: 2px solid var(--border-color);
            min-width: 320px;
        }
        
        .drawing-controls.active {
            display: block;
            animation: slideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .control-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid var(--primary-light);
        }
        
        .control-header i {
            color: var(--primary-red);
            font-size: 20px;
        }
        
        .control-header h3 {
            color: var(--text-dark);
            font-size: 18px;
            font-weight: 600;
        }
        
        /* === MODIFIED: Transport Buttons === */
        .transport-selector {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }
        
        .transport-btn {
            padding: 16px;
            border: 2px solid var(--border-color);
            border-radius: 12px;
            background: white;
            cursor: pointer;
            font-size: 22px;
            transition: all 0.3s ease;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: var(--text-light);
            height: 100px;
        }
        
        .transport-btn:hover {
            border-color: var(--primary-red);
            background: var(--primary-light);
            color: var(--primary-red);
            transform: translateY(-2px);
        }
        
        .transport-btn.active {
            border-color: var(--primary-red);
            background: var(--primary-red);
            color: white;
            box-shadow: 0 4px 12px rgba(228, 53, 26, 0.3);
        }
        
        .transport-label {
            font-size: 12px;
            margin-top: 8px;
            text-align: center;
            font-weight: 500;
        }
        
        /* === MODIFIED: Added STOP button === */
        .segment-controls {
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
        }
        
        .segment-control-btn {
            flex: 1;
            padding: 16px;
            border: none;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        .segment-control-btn.stop {
            background: linear-gradient(135deg, var(--danger), #c82333);
            color: white;
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .segment-control-btn.undo {
            background: linear-gradient(135deg, #6c757d, #5a6268);
            color: white;
            box-shadow: 0 4px 15px rgba(108, 117, 125, 0.3);
        }
        
        .segment-control-btn:hover {
            transform: translateY(-2px);
        }
        
        .segment-control-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        .segment-control-btn.stop:hover:not(:disabled) {
            box-shadow: 0 8px 20px rgba(220, 53, 69, 0.4);
        }
        
        .segment-control-btn.undo:hover:not(:disabled) {
            box-shadow: 0 8px 20px rgba(108, 117, 125, 0.4);
        }
        
        /* === MODIFIED: Caution Alert === */
        .caution-alert {
            background: linear-gradient(135deg, var(--warning), #ffc107);
            color: #212529;
            padding: 12px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: none;
            align-items: center;
            gap: 12px;
            font-weight: 600;
            animation: pulse 2s infinite;
            border: 2px solid #ffc107;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }
        
        /* === MODIFIED: Duration Input - Now Required === */
        .duration-section {
            margin-bottom: 20px;
        }
        
        .duration-label {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-dark);
            font-weight: 600;
            margin-bottom: 10px;
            font-size: 14px;
        }
        
        .duration-label.required::after {
            content: '*';
            color: var(--danger);
            margin-left: 4px;
        }
        
        .duration-label i {
            color: var(--primary-red);
        }
        
        .duration-inputs {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }
        
        .duration-input-group {
            position: relative;
        }
        
        .duration-input {
            width: 100%;
            padding: 14px 14px 14px 45px;
            border: 2px solid var(--border-color);
            border-radius: 12px;
            font-size: 15px;
            text-align: center;
            font-weight: 600;
            color: var(--text-dark);
            transition: all 0.3s ease;
            background-color: #fff;
        }
        
        .duration-input:required:invalid {
            border-color: var(--danger);
            background-color: rgba(220, 53, 69, 0.05);
        }
        
        .duration-input:focus {
            outline: none;
            border-color: var(--primary-red);
            box-shadow: 0 0 0 3px rgba(228, 53, 26, 0.1);
        }
        
        .duration-unit {
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--primary-red);
            font-weight: 600;
            font-size: 14px;
        }
        
        /* === MODIFIED: Added segment count display === */
        .segment-info {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
            padding: 12px 16px;
            background: #f8f9fa;
            border-radius: 12px;
            border: 2px solid var(--border-color);
        }
        
        .segment-count {
            font-weight: 600;
            color: var(--text-dark);
        }
        
        .segment-count span {
            color: var(--primary-red);
            font-size: 1.2em;
        }
        
        .current-mode {
            font-weight: 600;
            color: var(--text-dark);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .current-mode i {
            color: var(--primary-red);
        }
        
        /* === MODIFIED: Drawing instruction === */
        .draw-instruction {
            text-align: center;
            color: var(--text-light);
            font-size: 14px;
            margin-bottom: 15px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 10px;
            border: 1px dashed var(--border-color);
        }
        
        /* === MODIFIED: Submit button === */
        .submit-section {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 2px solid var(--primary-light);
        }
        
        .submit-btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, var(--success), #1e7e34);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(40, 167, 69, 0.4);
        }
        
        .submit-btn:disabled {
            background: #adb5bd;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        /* ===== MODERN SIDEBAR ===== */
        .sidebar {
            position: absolute;
            bottom: 40px;
            right: 40px;
            width: 400px;
            max-height: 60vh;
            background: white;
            border-radius: 20px;
            box-shadow: 0 12px 35px rgba(0,0,0,0.18);
            overflow: hidden;
            z-index: 1000;
            display: none;
            border: 2px solid var(--border-color);
        }
        
        .sidebar.active {
            display: block;
            animation: slideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .sidebar-header {
            padding: 24px;
            border-bottom: 2px solid var(--primary-light);
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        }
        
        .sidebar-title-section h3 {
            font-size: 20px;
            font-weight: 700;
            color: var(--text-dark);
            margin-bottom: 5px;
        }
        
        .sidebar-date {
            font-size: 14px;
            color: var(--text-light);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .sidebar-date i {
            color: var(--primary-red);
        }
        
        .edit-btn {
            width: 48px;
            height: 48px;
            background: white;
            border: 2px solid var(--border-color);
            border-radius: 12px;
            color: var(--text-light);
            font-size: 18px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .edit-btn:hover {
            border-color: var(--primary-red);
            color: var(--primary-red);
            background: var(--primary-light);
            transform: rotate(15deg);
        }
        
        .sidebar-content {
            overflow-y: auto;
            max-height: calc(60vh - 100px);
            padding: 20px;
        }
        
        /* ===== BEAUTIFUL SEGMENT ITEMS ===== */
        .segment-item {
            background: white;
            border: 2px solid var(--border-color);
            border-radius: 15px;
            padding: 18px;
            margin-bottom: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .segment-item::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            background: var(--primary-red);
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .segment-item:hover {
            border-color: var(--primary-red);
            transform: translateX(5px);
            box-shadow: 0 6px 20px rgba(228, 53, 26, 0.15);
        }
        
        .segment-item:hover::before {
            opacity: 1;
        }
        
        .segment-item.editing {
            border-color: var(--primary-red);
            background: var(--primary-light);
            transform: translateX(5px);
        }
        
        .segment-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 12px;
        }
        
        .segment-number {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--primary-red), #c12e16);
            color: white;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
            flex-shrink: 0;
            box-shadow: 0 4px 8px rgba(228, 53, 26, 0.3);
        }
        
        .segment-details {
            flex: 1;
        }
        
        .segment-transport {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-dark);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .segment-transport i {
            font-size: 20px;
            color: var(--primary-red);
        }
        
        .segment-meta {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-top: 8px;
        }
        
        .segment-duration {
            font-size: 14px;
            color: var(--text-light);
            display: flex;
            align-items: center;
            gap: 5px;
            background: #f8f9fa;
            padding: 6px 12px;
            border-radius: 20px;
        }
        
        .segment-type-badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .segment-type-stopping {
            background: rgba(40, 167, 69, 0.1);
            color: #28a745;
            border: 1px solid rgba(40, 167, 69, 0.3);
        }
        
        .segment-type-passing {
            background: rgba(255, 193, 7, 0.1);
            color: #ffc107;
            border: 1px solid rgba(255, 193, 7, 0.3);
        }
        
        /* ===== MODERN MODALS ===== */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(5px);
            z-index: 9999;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .modal-overlay.active {
            display: flex;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        /* ===== WELCOME MODAL (UNCHANGED AS REQUESTED) ===== */
        .welcome-modal {
            background: white;
            border-radius: 25px;
            padding: 50px;
            max-width: 650px;
            width: 100%;
            box-shadow: 0 25px 75px rgba(0,0,0,0.3);
            border: 3px solid white;
            position: relative;
            overflow: hidden;
        }
        
        .welcome-modal::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 5px;
            background: linear-gradient(90deg, var(--primary-red), #c12e16);
        }
        
        .welcome-header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .welcome-title {
            font-size: 38px;
            font-weight: 800;
            margin-bottom: 15px;
            background: linear-gradient(90deg, var(--primary-red), #c12e16);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .welcome-subtitle {
            font-size: 18px;
            color: var(--text-light);
            line-height: 1.6;
        }
        
        .form-section {
            margin-bottom: 35px;
        }
        
        .form-label {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 15px;
            color: var(--text-dark);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .form-label i {
            color: var(--primary-red);
        }
        
        .button-group {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
        
        .option-btn {
            padding: 22px;
            border: 2px solid var(--border-color);
            border-radius: 15px;
            background: white;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            color: var(--text-dark);
            text-align: center;
        }
        
        .option-btn:hover {
            border-color: var(--primary-red);
            background: var(--primary-light);
            color: var(--primary-red);
            transform: translateY(-3px);
        }
        
        .option-btn.active {
            border-color: var(--primary-red);
            background: linear-gradient(135deg, var(--primary-red), #c12e16);
            color: white;
            box-shadow: 0 8px 20px rgba(228, 53, 26, 0.3);
            transform: translateY(-3px);
        }
        
        .text-input {
            width: 100%;
            padding: 18px 20px;
            border: 2px solid var(--border-color);
            border-radius: 15px;
            font-size: 15px;
            transition: all 0.3s ease;
            color: var(--text-dark);
            background: white;
        }
        
        .text-input:focus {
            outline: none;
            border-color: var(--primary-red);
            box-shadow: 0 0 0 4px rgba(228, 53, 26, 0.1);
        }
        
        /* ===== NOTIFICATION TOASTS ===== */
        .notification {
            position: fixed;
            top: 30px;
            right: 30px;
            padding: 20px 25px;
            border-radius: 15px;
            font-size: 14px;
            font-weight: 500;
            z-index: 10000;
            display: flex;
            align-items: center;
            gap: 15px;
            min-width: 350px;
            max-width: 450px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            transform: translateX(500px);
            transition: transform 0.5s cubic-bezier(0.68, -0.55, 0.265, 1.55);
            border-left: 5px solid;
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.success {
            background: white;
            border-left-color: #28a745;
            color: #155724;
        }
        
        .notification.error {
            background: white;
            border-left-color: #dc3545;
            color: #721c24;
        }
        
        .notification.info {
            background: white;
            border-left-color: #17a2b8;
            color: #0c5460;
        }
        
        .notification.warning {
            background: white;
            border-left-color: #ffc107;
            color: #856404;
        }
        
        .notification-icon {
            font-size: 22px;
        }
        
        .notification-content {
            flex: 1;
        }
        
        .notification-title {
            font-weight: 700;
            margin-bottom: 5px;
        }
        
        .notification-close {
            background: none;
            border: none;
            color: inherit;
            opacity: 0.7;
            cursor: pointer;
            font-size: 16px;
            padding: 5px;
            transition: opacity 0.3s ease;
        }
        
        .notification-close:hover {
            opacity: 1;
        }
        
        /* ===== RESPONSIVE DESIGN ===== */
        @media (max-width: 1200px) {
            .sidebar {
                width: 350px;
            }
            
            .drawing-controls {
                min-width: 300px;
            }
        }
        
        @media (max-width: 992px) {
            .header-nav {
                gap: 8px;
            }
            
            .nav-btn {
                padding: 10px 16px;
                font-size: 13px;
            }
            
            .search-bar {
                width: 320px;
                top: 30px;
                left: 30px;
            }
            
            .sidebar {
                width: 300px;
                right: 30px;
                bottom: 30px;
            }
            
            .drawing-controls {
                left: 30px;
                top: 90px;
            }
            
            .transport-selector {
                grid-template-columns: repeat(3, 1fr);
            }
            
            .transport-btn {
                height: 90px;
                font-size: 20px;
            }
            
            .transport-label {
                font-size: 11px;
            }
        }
        
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                gap: 15px;
                padding: 15px;
            }
            
            .header-nav {
                width: 100%;
                justify-content: space-between;
            }
            
            .nav-btn {
                flex: 1;
                justify-content: center;
            }
            
            .map-container {
                height: calc(100vh - 140px);
                padding: 15px;
            }
            
            .search-bar {
                width: calc(100% - 30px);
                left: 15px;
                top: 15px;
            }
            
            .drawing-controls {
                position: fixed;
                top: auto;
                bottom: 20px;
                left: 20px;
                right: 20px;
                width: auto;
            }
            
            .sidebar {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 90%;
                max-height: 70vh;
                bottom: auto;
                right: auto;
            }
            
            .transport-selector {
                grid-template-columns: repeat(3, 1fr);
                gap: 8px;
            }
            
            .transport-btn {
                height: 80px;
                font-size: 18px;
                padding: 12px;
            }
            
            .transport-label {
                font-size: 10px;
            }
        }
        
        @media (max-width: 576px) {
            .welcome-modal {
                padding: 30px;
            }
            
            .button-group {
                grid-template-columns: 1fr;
            }
            
            .transport-selector {
                grid-template-columns: repeat(3, 1fr);
            }
            
            .nav-btn span {
                display: none;
            }
            
            .nav-btn i {
                font-size: 18px;
            }
            
            .segment-controls {
                flex-direction: column;
            }
            
            .segment-control-btn {
                width: 100%;
            }
        }
        
        /* ===== MAP LEGEND ===== */
        .map-legend {
            background: white;
            padding: 15px;
            border-radius: 15px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            font-size: 13px;
            max-width: 250px;
        }
        
        .legend-title {
            font-weight: 700;
            margin-bottom: 12px;
            color: var(--primary-red);
            font-size: 14px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }
        
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }
        
        /* ===== LOADING STATES ===== */
        .loading {
            position: relative;
            pointer-events: none;
            opacity: 0.7;
        }
        
        .loading::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 24px;
            height: 24px;
            margin: -12px 0 0 -12px;
            border: 3px solid var(--border-color);
            border-top-color: var(--primary-red);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* ===== SCROLLBAR STYLING ===== */
        ::-webkit-scrollbar {
            width: 10px;
        }
        
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: linear-gradient(var(--primary-red), #c12e16);
            border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--primary-hover);
        }
        
        /* ===== TOOLTIPS ===== */
        [data-tooltip] {
            position: relative;
        }
        
        [data-tooltip]::after {
            content: attr(data-tooltip);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            padding: 8px 12px;
            background: var(--text-dark);
            color: white;
            font-size: 12px;
            border-radius: 8px;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
            z-index: 1000;
            margin-bottom: 5px;
        }
        
        [data-tooltip]:hover::after {
            opacity: 1;
        }
        
        /* ===== ANIMATIONS ===== */
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .pulse {
            animation: pulse 2s infinite;
        }
        
        /* ===== EMPTY STATES ===== */
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-light);
        }
        
        .empty-state-icon {
            font-size: 60px;
            margin-bottom: 20px;
            opacity: 0.3;
        }
        
        .empty-state h3 {
            color: var(--text-dark);
            margin-bottom: 10px;
            font-size: 18px;
        }
        
        .empty-state p {
            font-size: 14px;
            line-height: 1.6;
        }
        
        /* ===== MAP TYPE SELECTOR ===== */
        .map-type-selector {
            position: absolute;
            top: 40px;
            right: 40px;
            z-index: 1000;
            background: white;
            border-radius: 15px;
            padding: 15px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            min-width: 200px;
        }
        
        .map-type-label {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-dark);
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .map-type-options {
            display: grid;
            gap: 8px;
        }
        
        .map-type-option {
            padding: 10px 15px;
            border: 2px solid var(--border-color);
            border-radius: 10px;
            background: white;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: all 0.3s ease;
            text-align: center;
        }
        
        .map-type-option:hover {
            border-color: var(--primary-red);
            color: var(--primary-red);
        }
        
        .map-type-option.active {
            border-color: var(--primary-red);
            background: var(--primary-red);
            color: white;
        }
    </style>
</head>
<body>
    <!-- Welcome Modal (UNCHANGED as requested) -->
    <div id="welcomeModal" class="modal-overlay active">
        <div class="welcome-modal">
            <div class="welcome-header">
                <h1 class="welcome-title">Campus Walk Mapper</h1>
                <p class="welcome-subtitle">Help us understand campus movement patterns by mapping your route</p>
            </div>
            
            <div class="form-section">
                <label class="form-label">
                    <i class="fas fa-user-graduate"></i>
                    I am a:
                </label>
                <div class="button-group">
                    <button class="option-btn" data-value="student">
                        <i class="fas fa-graduation-cap"></i>
                        Student
                    </button>
                    <button class="option-btn" data-value="faculty">
                        <i class="fas fa-chalkboard-teacher"></i>
                        Staff/Faculty
                    </button>
                    <button class="option-btn" data-value="visitor">
                        <i class="fas fa-map-marked-alt"></i>
                        Visitor
                    </button>
                    <button class="option-btn" data-value="other">
                        <i class="fas fa-users"></i>
                        Other
                    </button>
                </div>
            </div>
            
            <div class="form-section" id="gradeLevelSection" style="display: none;">
                <label class="form-label">
                    <i class="fas fa-layer-group"></i>
                    Grade Level:
                </label>
                <select class="text-input" id="gradeLevel">
                    <option value="">Select grade</option>
                    <option value="freshman">Freshman</option>
                    <option value="sophomore">Sophomore</option>
                    <option value="junior">Junior</option>
                    <option value="senior">Senior</option>
                    <option value="grad">Grad</option>
                </select>
            </div>
            
            <div class="form-section">
                <label class="form-label">
                    <i class="fas fa-university"></i>
                    Department/School (Optional):
                </label>
                <input type="text" class="text-input" id="department" placeholder="e.g. Engineering, Business, Arts & Sciences">
            </div>
            
            <div class="form-section">
                <label class="form-label">
                    <i class="fas fa-user-tag"></i>
                    Full Name (Optional):
                </label>
                <input type="text" class="text-input" id="fullName" placeholder="Your name (for reference)">
            </div>
            
            <button class="primary-btn" id="startBtn" disabled>
                <i class="fas fa-rocket"></i>
                Start Mapping Journey
            </button>
        </div>
    </div>

    <!-- Notification Container -->
    <div id="notificationContainer"></div>

    <!-- Header -->
    <div class="header">
<div class="logo-container">
    <div class="logo">
        <img src="/static/campus-icon.png" alt="Campus Mapper Logo">
    </div>
    <div class="app-title">Campus Mapper</div>
</div>
        
        <div class="header-nav">
            <button class="nav-btn" id="cancelNav" data-tooltip="Clear and cancel current session">
                <i class="fas fa-times-circle"></i>
                <span>Cancel</span>
            </button>
            <button class="nav-btn active" id="startDrawingNav" data-tooltip="Start drawing your route on the map">
                <i class="fas fa-pencil-alt"></i>
                <span>Start Drawing</span>
            </button>

            <button class="nav-btn" id="clearNav" data-tooltip="Clear all drawings and start over">
                <i class="fas fa-broom"></i>
                <span>Clear All</span>
            </button>

        </div>
    </div>

    <!-- Map Container -->
    <div class="map-container">
        <div id="map"></div>
        
        <!-- Search Bar -->
        <div class="search-bar">
            <i class="fas fa-search"></i>
            <input type="text" id="searchInput" placeholder="Search for buildings, landmarks, or locations...">
        </div>
        
        <!-- Drawing Controls - MODIFIED for new requirements -->
        <div class="drawing-controls" id="drawingControls">
            <div class="control-header">
                <i class="fas fa-route"></i>
                <h3>Route Drawing Tools</h3>
            </div>
            
            <!-- Segment Information -->
            <div class="segment-info">
                <div class="segment-count">
                    Segments: <span id="segmentCount">0</span>
                </div>
                <div class="current-mode">
                    <i class="fas fa-car" id="modeIcon"></i>
                    <span id="currentMode">Select Mode</span>
                </div>
            </div>
            
            <!-- Caution Alert -->
            <div class="caution-alert" id="cautionAlert">
                <i class="fas fa-exclamation-triangle"></i>
                <span>You're moving far from current segment!</span>
            </div>
            
            <!-- Drawing Instruction -->
            <div class="draw-instruction">
                <i class="fas fa-mouse-pointer"></i>
                Click and drag to draw, then click STOP to finish segment
            </div>
            
            <!-- Transport Selector - MODIFIED for new modes -->
            <div class="transport-selector">
                <button class="transport-btn active" data-mode="car">
                    <i class="fas fa-car"></i>
                    <div class="transport-label">Car/Transit</div>
                </button>
                <button class="transport-btn" data-mode="walking">
                    <i class="fas fa-person-walking"></i>
                    <div class="transport-label">Walking</div>
                </button>
                <button class="transport-btn" data-mode="micromodal">
                    <i class="fas fa-bicycle"></i>
                    <div class="transport-label">Micromodal</div>
                </button>
            </div>
            
            <!-- Segment Controls - MODIFIED with STOP and Undo buttons -->
            <div class="segment-controls">
                <button class="segment-control-btn stop" id="stopBtn" disabled>
                    <i class="fas fa-stop-circle"></i>
                    STOP Segment
                </button>
                <button class="segment-control-btn undo" id="undoBtn" onclick="undoLastSegment()" disabled>
                    <i class="fas fa-undo"></i>
                    Undo
                </button>
            </div>
            
            <!-- Duration Input - MODIFIED to be required -->
            <!-- Replace the duration section with hours and minutes -->
<div class="duration-section">
    <div class="duration-label required">
        <i class="fas fa-clock"></i>
        Time for this segment
    </div>
    <div class="duration-inputs">
        <div class="duration-input-group">
            <input type="number" class="duration-input" id="hours" 
                   placeholder="0" min="0" max="23" value="0">
            <span class="duration-unit">H</span>
        </div>
        <div class="duration-input-group">
            <input type="number" class="duration-input" id="minutes" 
                   placeholder="0" min="0" max="59" value="0">
            <span class="duration-unit">M</span>
        </div>
    </div>
</div>
            
            <!-- Submit Button - MODIFIED to be enabled/disabled -->
            <div class="submit-section">
                <button class="submit-btn" id="submitBtn" onclick="submitRoute()" disabled>
                    <i class="fas fa-paper-plane"></i>
                    Submit Complete Route
                </button>
            </div>
        </div>
        
        <!-- Current Path Sidebar -->
        <div class="sidebar" id="pathSidebar">
            <div class="sidebar-header">
                <div class="sidebar-title-section">
                    <h3>Your Current Route</h3>
                    <div class="sidebar-date" id="pathDate">
                        <i class="fas fa-calendar-alt"></i>
                        Loading...
                    </div>
                </div>
                <button class="edit-btn" id="editSegmentsBtn" data-tooltip="Edit route segments">
                    <i class="fas fa-edit"></i>
                </button>
            </div>
            <div class="sidebar-content" id="segmentList">
                <!-- Segments will be added here dynamically -->
                <div class="empty-state">
                    <div class="empty-state-icon">
                        <i class="fas fa-route"></i>
                    </div>
                    <h3>No segments yet</h3>
                    <p>Start drawing on the map to create your first route segment</p>
                </div>
            </div>
        </div>
        
        <!-- Map Type Selector -->
        <div class="map-type-selector">
            <div class="map-type-label">
                <i class="fas fa-map"></i>
                Map Type
            </div>
            <div class="map-type-options">
                <button class="map-type-option active" data-type="street">
                    Street View
                </button>
                <button class="map-type-option" data-type="satellite">
                    Satellite
                </button>
                <button class="map-type-option" data-type="terrain">
                    Terrain
                </button>
            </div>
        </div>
        
        <!-- Map Legend - MODIFIED for new transport modes -->
        <div class="map-legend" style="position: absolute; bottom: 40px; left: 40px; z-index: 1000;">
            <div class="legend-title">Route Colors</div>
            <div class="legend-item">
                <div class="legend-color" style="background: #E4351A;"></div>
                <span>Car/Transit</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #28a745;"></div>
                <span>Walking</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #17a2b8;"></div>
                <span>Micromodal</span>
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/heatmap.js/2.0.0/heatmap.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.heat/0.2.0/leaflet-heat.js"></script>
    
    <script>
        // ======================
        // INITIALIZATION
        // ======================
        let map = null;
        let currentRoute = null;
        let currentSegments = [];
        let currentPolylines = [];
        let currentMarkers = [];
        let heatmapLayer = null;
        let drawnItems = null;
        
        // State - MODIFIED for new requirements
        let userData = {
            userType: '',
            gradeLevel: '',
            department: '',
            fullName: ''
        };
        
        let isDrawing = false;
        let isDrawMode = false;
        let selectedTransport = 'car'; // Default to car/transit
        let editMode = false;
        let editingSegmentIndex = -1;
        let activeCampusMapId = null;
        let currentSegmentPoints = [];
        let segmentCount = 0;
        let cautionThreshold = 0.01; // Distance threshold for caution alert (in degrees)
        let baseTileLayer = null; // Reference to base tile layer for removal
        
        // Map configuration - MODIFIED for new transport modes
        const transportColors = {
            'car': '#E4351A',         // Red for Car/Transit
            'walking': '#28a745',     // Green for Walking
            'micromodal': '#17a2b8'   // Blue for Micromodal
        };
        
        const transportIcons = {
            'car': 'fa-car',
            'walking': 'fa-person-walking',
            'micromodal': 'fa-bicycle'
        };
        
        const transportNames = {
            'car': 'Car/Transit',
            'walking': 'Walking',
            'micromodal': 'Micromodal'
        };
        
        // ======================
        // INITIALIZE MAP
        // ======================
async function initializeMap() {
    // Initialize map with a default view, but it will be updated when campus map loads
    map = L.map('map');
    
    // Store reference to base tile layer (will be removed if campus map is loaded)
    baseTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    });
    baseTileLayer.addTo(map);
    
    // Initialize feature group for drawn items
    drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    
    // Initialize drawing handlers
    map.on('mousedown', startDrawing);
    map.on('mousemove', drawPath);
    map.on('mouseup', endDrawing);
    map.on('mouseout', endDrawing);
    
    // Load active campus map - THIS WILL SET THE VIEW
    await loadActiveCampusMap();
    
    // Update sidebar date
    updateSidebarDate();
}

async function loadReportMapOptions() {
    try {
        const response = await fetch('/api/campus-maps');
        const data = await response.json();
        
        if (data.success) {
            const reportSelect = document.getElementById('reportMap');
            let html = '<option value="">All Maps</option>';
            
            data.maps.forEach(map => {
                html += `<option value="${map.id}">${map.name}</option>`;
            });
            
            reportSelect.innerHTML = html;
        }
    } catch (error) {
        console.error('Error loading report map options:', error);
    }
}

        // ======================
        // CAMPUS MAP LOADING
        // ======================
async function loadActiveCampusMap() {
    try {
        const response = await fetch('/api/active-campus-map');
        const data = await response.json();
        
        // Remove existing campus map overlay if it exists
        map.eachLayer(layer => {
            if (layer instanceof L.ImageOverlay) {
                map.removeLayer(layer);
            }
        });
        
        if (data.success && data.map) {
            // Update active campus map ID - this ensures routes are saved with correct map
            activeCampusMapId = data.map.id;
            
            // Remove base tile layer when campus map is loaded (PDF maps don't need background tiles)
            if (baseTileLayer && map.hasLayer(baseTileLayer)) {
                map.removeLayer(baseTileLayer);
            }
            
            // Add the campus map overlay
            const imageUrl = `/maps/${data.map.image_filename}`;
            
            if (data.map.bounds_north && data.map.bounds_south && 
                data.map.bounds_east && data.map.bounds_west) {
                // Use the map's geographic bounds
                const bounds = [
                    [data.map.bounds_south, data.map.bounds_west],
                    [data.map.bounds_north, data.map.bounds_east]
                ];
                
                // Add the campus map image overlay with opacity
                L.imageOverlay(imageUrl, bounds, {
                    opacity: 0.8,
                    interactive: false
                }).addTo(map);
                
                // Fit the map to the campus map bounds
                map.fitBounds(bounds);
                
                // Set a reasonable zoom level
                map.setZoom(16);
            } else {
                // If no bounds are set, use default coordinates
                map.setView([40.7128, -74.0060], 15);
                showNotification('warning', 'No Map Bounds', 'Campus map loaded but no geographic bounds set. Using default coordinates.');
            }
            
            showNotification('success', 'Active campus map loaded', `Using: ${data.map.name} (ID: ${activeCampusMapId})`);
        } else {
            // Use default coordinates if no active map
            // Re-add base tile layer if no campus map is active
            if (baseTileLayer && !map.hasLayer(baseTileLayer)) {
                baseTileLayer.addTo(map);
            }
            activeCampusMapId = null;
            map.setView([40.7128, -74.0060], 15);
            showNotification('info', 'Using default map', 'No active campus map found');
        }
    } catch (error) {
        console.error('Error loading campus map:', error);
        // Re-add base tile layer on error
        if (baseTileLayer && !map.hasLayer(baseTileLayer)) {
            baseTileLayer.addTo(map);
        }
        // Use default coordinates on error
        activeCampusMapId = null;
        map.setView([40.7128, -74.0060], 15);
        showNotification('error', 'Map Error', 'Could not load campus map data. Using default coordinates.');
    }
}
        
        // ======================
        // DRAWING FUNCTIONS - MODIFIED for new requirements
        // ======================
        function startDrawing(e) {
            if (!isDrawMode) {
                showNotification('info', 'Enable Drawing', 'Click "Start Drawing" button first');
                return;
            }
            
            isDrawing = true;
            currentSegmentPoints = [e.latlng];
            
            // Create new polyline for this segment
            currentRoute = L.polyline([], {
                color: transportColors[selectedTransport],
                weight: 6,
                opacity: 0.9,
                lineCap: 'round',
                lineJoin: 'round',
                dashArray: '5, 10' // Dashed line for drawing in progress
            }).addTo(map);
            
            currentRoute.setLatLngs([e.latlng]);
            
            // Enable STOP button
            document.getElementById('stopBtn').disabled = false;
            
            showNotification('info', 'Drawing Started', 'Drag to draw, release to add points');
        }
        
        function drawPath(e) {
            if (!isDrawing || !currentRoute) return;
            
            const lastPoint = currentSegmentPoints[currentSegmentPoints.length - 1];
            const distance = Math.sqrt(
                Math.pow(e.latlng.lat - lastPoint.lat, 2) +
                Math.pow(e.latlng.lng - lastPoint.lng, 2)
            );
            
            // Show caution if moving too far from current segment
            if (distance > cautionThreshold && currentSegmentPoints.length > 1) {
                document.getElementById('cautionAlert').style.display = 'flex';
            } else {
                document.getElementById('cautionAlert').style.display = 'none';
            }
            
            // Add point to current segment
            currentSegmentPoints.push(e.latlng);
            currentRoute.setLatLngs(currentSegmentPoints);
        }
        
        function endDrawing() {
            if (!isDrawing || !currentRoute) return;
            
            isDrawing = false;
            
            if (currentSegmentPoints.length > 1) {
                showNotification('info', 'Segment Drawn', 'Click STOP to save this segment or continue drawing');
            } else {
                // Remove the polyline if only one point was drawn
                map.removeLayer(currentRoute);
                currentRoute = null;
                currentSegmentPoints = [];
                document.getElementById('stopBtn').disabled = true;
            }
        }
        
        // STOP button handler - NEW FUNCTION
        function stopSegment() {
    if (!currentRoute || currentSegmentPoints.length < 2) {
        showNotification('error', 'Invalid Segment', 'Draw a longer segment before stopping');
        return;
    }
    
    const hours = parseInt(document.getElementById('hours').value) || 0;
    const minutes = parseInt(document.getElementById('minutes').value) || 0;
    
    if (hours === 0 && minutes === 0) {
        showNotification('error', 'Time Required', 'Please enter a valid time (hours and/or minutes)');
        document.getElementById('hours').focus();
        return;
    }
    
    // Calculate total seconds
    const totalSeconds = (hours * 3600) + (minutes * 60);
    
    // Convert dashed line to solid line for completed segment
    currentRoute.setStyle({
        dashArray: null,
        opacity: 0.8
    });
    
    // Create segment object
    const segment = {
        path: [...currentSegmentPoints],
        transportMode: selectedTransport,
        durationSeconds: totalSeconds,
        segmentType: 'stopping'
    };
    
    currentSegments.push(segment);
    currentPolylines.push(currentRoute);
    segmentCount++;
    
    // Add marker for the stopping point
    addSegmentMarker(currentSegmentPoints[currentSegmentPoints.length - 1], segmentCount);
    
    // Update UI
    updateSegmentCount();
    updateSidebar();
    enableSubmitButton();
    document.getElementById('undoBtn').disabled = false;
    
    // Reset for next segment
    currentRoute = null;
    currentSegmentPoints = [];
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('hours').value = 0;
    document.getElementById('minutes').value = 0;
    document.getElementById('cautionAlert').style.display = 'none';
    
    const timeStr = hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
    showNotification('success', 'Segment Saved', `Segment ${segmentCount} saved (${timeStr}) as ${transportNames[selectedTransport]}`);
}
        
        // Undo function - NEW FUNCTION
        function undoLastSegment() {
            if (currentSegments.length === 0) return;
            
            // Remove last segment
            const lastSegment = currentSegments.pop();
            const lastPolyline = currentPolylines.pop();
            const lastMarker = currentMarkers.pop();
            
            // Remove from map
            if (lastPolyline) map.removeLayer(lastPolyline);
            if (lastMarker) map.removeLayer(lastMarker);
            
            // Update counts
            segmentCount = currentSegments.length;
            updateSegmentCount();
            updateSidebar();
            
            // Disable buttons if no segments left
            if (currentSegments.length === 0) {
                document.getElementById('undoBtn').disabled = true;
                document.getElementById('submitBtn').disabled = true;
            }
            
            showNotification('info', 'Segment Removed', 'Last segment has been removed');
        }
        
        function addSegmentMarker(latlng, segmentNumber) {
            const marker = L.marker(latlng, {
                icon: L.divIcon({
                    className: 'custom-marker',
                    html: `
                        <div style="
                            width: 36px;
                            height: 36px;
                            background: linear-gradient(135deg, ${transportColors[selectedTransport]}, ${transportColors[selectedTransport]}80);
                            color: white;
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-weight: 700;
                            font-size: 14px;
                            border: 3px solid white;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                        ">
                            ${segmentNumber}
                        </div>
                    `,
                    iconSize: [36, 36]
                })
            }).addTo(map);
            
            currentMarkers.push(marker);
        }
        
        // ======================
        // UI UPDATE FUNCTIONS - NEW FUNCTIONS
        // ======================
        function updateSegmentCount() {
            document.getElementById('segmentCount').textContent = segmentCount;
        }
        
        function updateModeDisplay() {
            const modeIcon = document.getElementById('modeIcon');
            const currentMode = document.getElementById('currentMode');
            
            modeIcon.className = `fas ${transportIcons[selectedTransport]}`;
            currentMode.textContent = transportNames[selectedTransport];
        }
        
        function enableSubmitButton() {
            if (currentSegments.length > 0) {
                document.getElementById('submitBtn').disabled = false;
            }
        }
        
        // ======================
        // UI EVENT HANDLERS - MODIFIED for new requirements
        // ======================
        // Welcome Modal - UNCHANGED as requested
        document.querySelectorAll('.welcome-modal .option-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.welcome-modal .option-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                userData.userType = this.dataset.value;
                
                // Show/hide grade level section
                const gradeLevelSection = document.getElementById('gradeLevelSection');
                const gradeLevelInput = document.getElementById('gradeLevel');
                if (userData.userType === 'student') {
                    gradeLevelSection.style.display = 'block';
                    if (gradeLevelInput) gradeLevelInput.disabled = false;
                } else {
                    gradeLevelSection.style.display = 'none';
                    // Ensure grade is only collected for students
                    if (gradeLevelInput) {
                        gradeLevelInput.value = '';
                        gradeLevelInput.disabled = true;
                    }
                    userData.gradeLevel = '';
                }
                
                // Enable start button
                document.getElementById('startBtn').disabled = false;
            });
        });
        
        document.getElementById('startBtn').addEventListener('click', async () => {
            // Collect user data
            // Only collect grade if student is selected
            const gradeEl = document.getElementById('gradeLevel');
            userData.gradeLevel = (userData.userType === 'student' && gradeEl) ? gradeEl.value : '';
            userData.department = document.getElementById('department').value.trim();
            userData.fullName = document.getElementById('fullName').value.trim();
            
            // Validation
            if (userData.userType === 'student' && !userData.gradeLevel) {
                showNotification('error', 'Validation Error', 'Students must enter a grade level');
                return;
            }
            
            // Close welcome modal
            document.getElementById('welcomeModal').classList.remove('active');
            
            // Initialize map
            await initializeMap();
            
            showNotification('success', 'Welcome!', 'You can now start mapping your campus route');
        });
        
        // Transport buttons - MODIFIED for new modes
        document.querySelectorAll('.transport-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.transport-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                selectedTransport = this.dataset.mode;
                
                // Update current route color if drawing
                if (currentRoute) {
                    currentRoute.setStyle({
                        color: transportColors[selectedTransport]
                    });
                }
                
                // Update mode display
                updateModeDisplay();
            });
        });
        
        // STOP button handler
        document.getElementById('stopBtn').addEventListener('click', stopSegment);
        
        // Navigation buttons
        document.getElementById('startDrawingNav').addEventListener('click', function() {
            isDrawMode = !isDrawMode;
            if (isDrawMode) {
                document.getElementById('drawingControls').classList.add('active');
                document.getElementById('pathSidebar').classList.add('active');
                this.classList.add('active');
                this.innerHTML = '<i class="fas fa-stop-circle"></i><span>Stop Drawing</span>';
                showNotification('success', 'Drawing Mode Enabled', 'Click and drag on the map to draw segments');
            } else {
                isDrawing = false;
                if (currentRoute) {
                    map.removeLayer(currentRoute);
                    currentRoute = null;
                    currentSegmentPoints = [];
                }
                document.getElementById('drawingControls').classList.remove('active');
                this.classList.remove('active');
                this.innerHTML = '<i class="fas fa-pencil-alt"></i><span>Start Drawing</span>';
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('cautionAlert').style.display = 'none';
                showNotification('info', 'Drawing Mode Disabled', 'Route drawing paused');
            }
        });
        
        document.getElementById('finishNav').addEventListener('click', function() {
            if (currentSegments.length > 0) {
                submitRoute();
            } else {
                showNotification('info', 'No Route', 'Draw at least one segment first');
            }
        });
        
        document.getElementById('saveNav').addEventListener('click', async function() {
            if (currentSegments.length === 0) {
                showNotification('error', 'No Route', 'Draw at least one segment before saving');
                return;
            }
            
            await submitRoute();
        });
        
        document.getElementById('clearNav').addEventListener('click', function() {
            if (confirm('Are you sure you want to clear all drawings? This cannot be undone.')) {
                clearAll();
                showNotification('info', 'Cleared', 'All drawings have been cleared');
            }
        });
        
        document.getElementById('cancelNav').addEventListener('click', function() {
            if (confirm('Cancel current session and start over?')) {
                clearAll();
                isDrawing = false;
                isDrawMode = false;
                document.getElementById('drawingControls').classList.remove('active');
                document.getElementById('pathSidebar').classList.remove('active');
                document.getElementById('startDrawingNav').classList.remove('active');
                document.getElementById('startDrawingNav').innerHTML = '<i class="fas fa-pencil-alt"></i><span>Start Drawing</span>';
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('submitBtn').disabled = true;
                document.getElementById('undoBtn').disabled = true;
                document.getElementById('cautionAlert').style.display = 'none';
                showNotification('info', 'Session Cancelled', 'Ready to start new mapping session');
            }
        });
        
        // Edit segments button
        document.getElementById('editSegmentsBtn').addEventListener('click', function() {
            if (currentSegments.length === 0) {
                showNotification('info', 'No Segments', 'Draw some segments first');
                return;
            }
            
            editMode = !editMode;
            if (editMode) {
                this.style.color = '#E4351A';
                this.style.opacity = '1';
                showNotification('info', 'Edit Mode', 'Click any segment to edit it');
            } else {
                this.style.color = '';
                this.style.opacity = '';
                editingSegmentIndex = -1;
                updateSidebar();
                showNotification('info', 'Edit Mode Off', 'Editing disabled');
            }
        });
        
        // Map type selector
        document.querySelectorAll('.map-type-option').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.map-type-option').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                const type = this.dataset.type;
                changeMapType(type);
            });
        });
        
        // ======================
        // ROUTE SUBMISSION - MODIFIED to store drawn data
        // ======================
        async function submitRoute() {
            if (currentSegments.length === 0) {
                showNotification('error', 'No Route', 'Draw at least one segment before submitting');
                return;
            }
            
            try {
                const response = await fetch('/api/save-route-drawn', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        routeId: Date.now(),
                        segments: currentSegments,
                        userData: userData,
                        campus_map_id: activeCampusMapId
                    })
                });
                
                const result = await response.json();
                if (result.success) {
                    showNotification('success', 'Route Submitted!', 'Your route has been saved to the database');
                    clearAll();
                    resetUI();
                } else {
                    showNotification('error', 'Submission Failed', result.error || 'Unknown error');
                }
            } catch (error) {
                console.error('Error submitting route:', error);
                showNotification('error', 'Network Error', 'Could not save route to server');
            }
        }
        
        function resetUI() {
            isDrawMode = false;
            isDrawing = false;
            document.getElementById('drawingControls').classList.remove('active');
            document.getElementById('pathSidebar').classList.remove('active');
            document.getElementById('startDrawingNav').classList.remove('active');
            document.getElementById('startDrawingNav').innerHTML = '<i class="fas fa-pencil-alt"></i><span>Start Drawing</span>';
            document.getElementById('stopBtn').disabled = true;
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('undoBtn').disabled = true;
            document.getElementById('cautionAlert').style.display = 'none';
        }
        
        // ======================
        // HELPER FUNCTIONS
        // ======================
        function changeMapType(type) {
    // Save current view and bounds
    const currentCenter = map.getCenter();
    const currentZoom = map.getZoom();
    
    // Remove existing tile layers but keep the campus map overlay
    map.eachLayer(layer => {
        if (layer instanceof L.TileLayer) {
            map.removeLayer(layer);
        }
    });
    
    // Add new tile layer based on type
    let tileLayer;
    switch(type) {
        case 'satellite':
            tileLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
                attribution: 'Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
            });
            break;
        case 'terrain':
            tileLayer = L.tileLayer('https://stamen-tiles-{s}.a.ssl.fastly.net/terrain/{z}/{x}/{y}.{ext}', {
                attribution: 'Map tiles by <a href="http://stamen.com">Stamen Design</a>, <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a> — Map data © <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                subdomains: 'abcd',
                minZoom: 0,
                maxZoom: 18,
                ext: 'png'
            });
            break;
        default: // street
            tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            });
    }
    
    tileLayer.addTo(map);
    
    // Restore view
    map.setView(currentCenter, currentZoom);
    
    // Re-add drawn items
    map.addLayer(drawnItems);
    currentPolylines.forEach(polyline => map.addLayer(polyline));
    currentMarkers.forEach(marker => map.addLayer(marker));
}
        
        function updateSidebar() {
            const segmentList = document.getElementById('segmentList');
            
            if (currentSegments.length === 0) {
                segmentList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">
                            <i class="fas fa-route"></i>
                        </div>
                        <h3>No segments yet</h3>
                        <p>Start drawing on the map to create your first route segment</p>
                    </div>
                `;
                return;
            }
            
            let html = '';
            currentSegments.forEach((segment, index) => {
                const timeStr = `${segment.durationSeconds} seconds`;
                
                html += `
                    <div class="segment-item ${editingSegmentIndex === index ? 'editing' : ''}" data-index="${index}">
                        <div class="segment-header">
                            <div class="segment-number">${index + 1}</div>
                            <div class="segment-details">
                                <div class="segment-transport">
                                    <i class="fas ${transportIcons[segment.transportMode]}"></i>
                                    ${transportNames[segment.transportMode]}
                                </div>
                                <div class="segment-meta">
                                    <div class="segment-duration">
                                        <i class="fas fa-clock"></i>
                                        ${timeStr}
                                    </div>
                                    <span class="segment-type-badge segment-type-stopping">
                                        Stop
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            segmentList.innerHTML = html;
            
            // Add click handlers to segments
            document.querySelectorAll('.segment-item').forEach(item => {
                item.addEventListener('click', function() {
                    if (editMode) {
                        const index = parseInt(this.dataset.index);
                        editingSegmentIndex = index;
                        
                        // Update UI for editing
                        document.querySelectorAll('.segment-item').forEach(el => el.classList.remove('editing'));
                        this.classList.add('editing');
                        
                        // Load segment data into controls
                        const segment = currentSegments[index];
                        selectedTransport = segment.transportMode;
                        
                        document.querySelectorAll('.transport-btn').forEach(btn => {
                            btn.classList.toggle('active', btn.dataset.mode === selectedTransport);
                        });
                        
                        document.getElementById('durationSeconds').value = segment.durationSeconds;
                        
                        showNotification('info', 'Editing Segment', `Segment ${index + 1} selected for editing`);
                    }
                });
            });
        }
        
        function updateSidebarDate() {
            const now = new Date();
            const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
            document.getElementById('pathDate').innerHTML = `
                <i class="fas fa-calendar-alt"></i>
                ${now.toLocaleDateString('en-US', options)}
            `;
        }
        
        function clearAll() {
            currentSegments = [];
            currentSegmentPoints = [];
            segmentCount = 0;
            
            currentPolylines.forEach(polyline => {
                map.removeLayer(polyline);
            });
            currentPolylines = [];
            
            currentMarkers.forEach(marker => {
                map.removeLayer(marker);
            });
            currentMarkers = [];
            
            if (currentRoute) {
                map.removeLayer(currentRoute);
                currentRoute = null;
            }
            
            updateSegmentCount();
            updateSidebar();
            editingSegmentIndex = -1;
            editMode = false;
            document.getElementById('editSegmentsBtn').style.color = '';
            document.getElementById('editSegmentsBtn').style.opacity = '';
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('undoBtn').disabled = true;
        }
        
        function showNotification(type, title, message) {
            const icons = {
                'success': 'fa-check-circle',
                'error': 'fa-exclamation-circle',
                'info': 'fa-info-circle',
                'warning': 'fa-exclamation-triangle'
            };
            
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.innerHTML = `
                <div class="notification-icon">
                    <i class="fas ${icons[type]}"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${title}</div>
                    <div class="notification-message">${message}</div>
                </div>
                <button class="notification-close">
                    <i class="fas fa-times"></i>
                </button>
            `;
            
            document.getElementById('notificationContainer').appendChild(notification);
            
            // Trigger animation
            setTimeout(() => notification.classList.add('show'), 10);
            
            // Close button
            notification.querySelector('.notification-close').addEventListener('click', () => {
                notification.classList.remove('show');
                setTimeout(() => notification.remove(), 500);
            });
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.classList.remove('show');
                    setTimeout(() => notification.remove(), 500);
                }
            }, 5000);
        }
        
        // ======================
        // SEARCH FUNCTIONALITY
        // ======================
        const searchInput = document.getElementById('searchInput');
        let searchTimeout = null;
        
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(performSearch, 500);
        });
        
        function performSearch() {
            const query = searchInput.value.trim();
            if (query.length < 2) return;
            
            // Implement search logic here
            showNotification('info', 'Search', `Searching for: ${query}`);
        }
        
        // ======================
        // INITIALIZE ON LOAD
        // ======================
        window.addEventListener('load', () => {
            showNotification('info', 'Welcome', 'Fill out the form to begin mapping your campus route');
        });
    </script>
</body>
</html>
'''

# ===============================
# MODIFIED DASHBOARD HTML TEMPLATE with new features
# ===============================
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Campus Mapper Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css" />
    <style>
        /* ===== IMPROVED DASHBOARD THEME ===== */
        :root {
            --primary-red: #E4351A;
            --primary-hover: #C12E16;
            --sidebar-bg: #2c3e50;
            --sidebar-hover: #34495e;
            --card-bg: white;
            --text-dark: #212529;
            --text-light: #6c757d;
            --border-color: #dee2e6;
            --success: #28a745;
            --warning: #ffc107;
            --danger: #dc3545;
            --info: #17a2b8;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8f9fa;
            min-height: 100vh;
        }
        
        /* ===== MODERN DASHBOARD LAYOUT ===== */
        .dashboard {
            display: grid;
            grid-template-columns: 280px 1fr;
            min-height: 100vh;
        }
        
        /* ===== BEAUTIFUL SIDEBAR ===== */
        .sidebar {
            background: linear-gradient(180deg, var(--sidebar-bg), #1a252f);
            color: white;
            padding: 30px 20px;
            box-shadow: 5px 0 15px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            height: 100vh;
            overflow-y: auto;
        }
        
        .sidebar-header {
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }
        
        .sidebar-header h2 {
            display: flex;
            align-items: center;
            gap: 15px;
            color: white;
            font-size: 1.8rem;
            margin-bottom: 10px;
        }
        
        .sidebar-header h2 i {
            color: var(--primary-red);
            background: white;
            width: 50px;
            height: 50px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }
        
        .sidebar-subtitle {
            color: #bdc3c7;
            font-size: 0.9rem;
            padding-left: 65px;
        }
        
        .sidebar nav ul {
            list-style: none;
        }
        
        .sidebar nav li {
            margin-bottom: 8px;
        }
        
        .sidebar nav a {
            color: #ecf0f1;
            text-decoration: none;
            padding: 15px 20px;
            display: flex;
            align-items: center;
            gap: 15px;
            border-radius: 12px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-weight: 500;
            border-left: 4px solid transparent;
        }
        
        .sidebar nav a:hover {
            background: rgba(255,255,255,0.1);
            transform: translateX(10px);
            border-left-color: var(--primary-red);
        }
        
        .sidebar nav a.active {
            background: linear-gradient(90deg, rgba(228, 53, 26, 0.2), transparent);
            border-left-color: var(--primary-red);
            color: white;
        }
        
        .sidebar nav a i {
            width: 24px;
            text-align: center;
            font-size: 1.2rem;
        }
        
        /* ===== MAIN CONTENT AREA ===== */
        .main-content {
            padding: 30px;
            overflow-y: auto;
            max-height: 100vh;
        }
        
        /* ===== IMPROVED HEADER ===== */
        .header {
            background: white;
            padding: 25px 30px;
            border-radius: 20px;
            margin-bottom: 30px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            border-bottom: 4px solid var(--primary-red);
        }
        
        .header h1 {
            color: var(--text-dark);
            font-size: 2.2rem;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .header-subtitle {
            color: var(--text-light);
            font-size: 1rem;
            max-width: 600px;
        }
        
        /* ===== ENHANCED STATS CARDS ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }
        
        .stat-card {
            background: white;
            padding: 30px;
            border-radius: 20px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 2px solid transparent;
            position: relative;
            overflow: hidden;
        }
        
        .stat-card:hover {
            transform: translateY(-10px);
            box-shadow: 0 15px 35px rgba(0,0,0,0.15);
            border-color: var(--primary-red);
        }
        
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 5px;
            background: linear-gradient(90deg, var(--primary-red), #c12e16);
        }
        
        .stat-icon {
            width: 70px;
            height: 70px;
            border-radius: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 20px;
            font-size: 28px;
            color: white;
            box-shadow: 0 8px 20px rgba(0,0,0,0.2);
        }
        
        .stat-icon.route { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .stat-icon.map { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .stat-icon.user { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
        .stat-icon.data { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); }
        
        .stat-card h3 {
            color: var(--text-light);
            font-size: 0.95rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
            font-weight: 600;
        }
        
        .stat-card .value {
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--text-dark);
            line-height: 1;
        }
        
        .stat-change {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 15px;
            font-size: 0.9rem;
            font-weight: 500;
        }
        
        .stat-change.positive {
            color: var(--success);
        }
        
        .stat-change.negative {
            color: var(--danger);
        }
        
        /* ===== CONTENT SECTIONS ===== */
        .content-section {
            background: white;
            padding: 35px;
            border-radius: 20px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            border: 2px solid transparent;
            transition: border-color 0.3s ease;
        }
        
        .content-section:hover {
            border-color: rgba(228, 53, 26, 0.2);
        }
        
        .content-section h2 {
            color: var(--text-dark);
            font-size: 1.8rem;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 3px solid var(--primary-light);
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .content-section h2 i {
            color: var(--primary-red);
            background: rgba(228, 53, 26, 0.1);
            width: 50px;
            height: 50px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
        }
        
        /* ===== MODERN FORMS ===== */
        .form-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        
        @media (max-width: 992px) {
            .form-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 10px;
            font-weight: 600;
            color: var(--text-dark);
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.95rem;
        }
        
        .form-group label i {
            color: var(--primary-red);
        }
        
        .form-group input, 
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 15px 20px;
            border: 2px solid var(--border-color);
            border-radius: 12px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            color: var(--text-dark);
        }
        
        .form-group input:focus, 
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: var(--primary-red);
            box-shadow: 0 0 0 4px rgba(228, 53, 26, 0.1);
        }
        
        .form-section-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin: 25px 0 15px;
            color: var(--text-dark);
            padding-bottom: 10px;
            border-bottom: 2px solid var(--border-color);
        }
        
        /* ===== ENHANCED BUTTONS ===== */
        .btn {
            background: linear-gradient(135deg, var(--primary-red), #c12e16);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: inline-flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            box-shadow: 0 4px 15px rgba(228, 53, 26, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(228, 53, 26, 0.4);
        }
        
        .btn:active {
            transform: translateY(-1px);
        }
        
        .btn-secondary {
            background: #6c757d;
        }
        
        .btn-secondary:hover {
            background: #5a6268;
            box-shadow: 0 8px 20px rgba(108, 117, 125, 0.4);
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger), #c82333);
        }
        
        .btn-danger:hover {
            box-shadow: 0 8px 20px rgba(220, 53, 69, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, var(--success), #1e7e34);
        }
        
        .btn-success:hover {
            box-shadow: 0 8px 20px rgba(40, 167, 69, 0.4);
        }
        
        /* ===== BEAUTIFUL MAP LIST ===== */
        .map-list {
            display: grid;
            gap: 20px;
        }
        
        .map-item {
            background: white;
            border: 2px solid var(--border-color);
            border-radius: 15px;
            padding: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .map-item:hover {
            border-color: var(--primary-red);
            transform: translateX(5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }
        
        .map-item.active {
            border-color: var(--primary-red);
            background: rgba(228, 53, 26, 0.05);
        }
        
        .map-item.active::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 5px;
            background: var(--primary-red);
        }
        
        .map-details {
            flex: 1;
        }
        
        .map-details h4 {
            font-size: 1.2rem;
            font-weight: 600;
            color: var(--text-dark);
            margin-bottom: 8px;
        }
        
        .map-meta {
            display: flex;
            gap: 20px;
            margin-top: 10px;
            font-size: 0.9rem;
            color: var(--text-light);
        }
        
        .map-meta-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .map-meta-item i {
            color: var(--primary-red);
        }
        
        .map-status {
            padding: 6px 15px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .map-status.active {
            background: rgba(40, 167, 69, 0.15);
            color: var(--success);
        }
        
        .map-status.inactive {
            background: rgba(108, 117, 125, 0.15);
            color: var(--text-light);
        }
        
        .map-actions {
            display: flex;
            gap: 10px;
        }
        
        /* ===== ENHANCED FILTERS ===== */
        .filters {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
            background: #f8f9fa;
            padding: 25px;
            border-radius: 15px;
        }
        
        /* ===== BEAUTIFUL TABLES ===== */
        .data-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin-top: 20px;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .data-table thead {
            background: linear-gradient(135deg, var(--primary-red), #c12e16);
        }
        
        .data-table th {
            padding: 18px 20px;
            text-align: left;
            color: white;
            font-weight: 600;
            font-size: 0.95rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border: none;
        }
        
        .data-table th:first-child {
            border-top-left-radius: 15px;
        }
        
        .data-table th:last-child {
            border-top-right-radius: 15px;
        }
        
        .data-table tbody tr {
            background: white;
            transition: all 0.3s ease;
        }
        
        .data-table tbody tr:hover {
            background: rgba(228, 53, 26, 0.05);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .data-table td {
            padding: 18px 20px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-dark);
            font-size: 0.95rem;
        }
        
        .data-table tbody tr:last-child td {
            border-bottom: none;
        }
        
        /* ===== EMPTY STATES ===== */
        .empty-state {
            text-align: center;
            padding: 60px 30px;
            color: var(--text-light);
        }
        
        .empty-state-icon {
            font-size: 64px;
            margin-bottom: 20px;
            opacity: 0.3;
            color: var(--primary-red);
        }
        
        .empty-state h3 {
            color: var(--text-dark);
            margin-bottom: 10px;
            font-size: 1.5rem;
        }
        
        .empty-state p {
            font-size: 1rem;
            line-height: 1.6;
            max-width: 500px;
            margin: 0 auto;
        }
        
        /* ===== TABS ===== */
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 5px;
        }
        
        .tab-btn {
            padding: 15px 30px;
            background: transparent;
            border: none;
            border-bottom: 3px solid transparent;
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-light);
            cursor: pointer;
            transition: all 0.3s ease;
            border-radius: 8px 8px 0 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .tab-btn:hover {
            color: var(--primary-red);
            background: rgba(228, 53, 26, 0.05);
        }
        
        .tab-btn.active {
            color: var(--primary-red);
            border-bottom-color: var(--primary-red);
            background: rgba(228, 53, 26, 0.1);
        }
        
        /* ===== MODAL DIALOGS ===== */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(5px);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            border: 3px solid white;
            position: relative;
        }
        
        .modal-header {
            margin-bottom: 30px;
        }
        
        .modal-title {
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--text-dark);
            margin-bottom: 10px;
        }
        
        .modal-close {
            position: absolute;
            top: 20px;
            right: 20px;
            background: none;
            border: none;
            font-size: 1.5rem;
            color: var(--text-light);
            cursor: pointer;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }
        
        .modal-close:hover {
            background: var(--border-color);
            color: var(--danger);
        }
        
        /* ===== RESPONSIVE DESIGN ===== */
        @media (max-width: 768px) {
            .dashboard {
                grid-template-columns: 1fr;
            }
            
            .sidebar {
                height: auto;
                position: relative;
                display: none;
            }
            
            .sidebar.active {
                display: block;
            }
            
            .mobile-menu-toggle {
                display: block;
                position: fixed;
                top: 20px;
                left: 20px;
                z-index: 100;
                background: var(--primary-red);
                color: white;
                width: 50px;
                height: 50px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
                box-shadow: 0 4px 15px rgba(228, 53, 26, 0.4);
                border: none;
                cursor: pointer;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
        
        /* ===== BADGES ===== */
        .badge {
            display: inline-block;
            padding: 6px 15px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .badge-success {
            background: rgba(40, 167, 69, 0.15);
            color: var(--success);
        }
        
        .badge-warning {
            background: rgba(255, 193, 7, 0.15);
            color: var(--warning);
        }
        
        .badge-danger {
            background: rgba(220, 53, 69, 0.15);
            color: var(--danger);
        }
        
        .badge-info {
            background: rgba(23, 162, 184, 0.15);
            color: var(--info);
        }
        
        /* ===== LOADING STATES ===== */
        .loading {
            position: relative;
            pointer-events: none;
            opacity: 0.7;
        }
        
        .loading::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 30px;
            height: 30px;
            margin: -15px 0 0 -15px;
            border: 3px solid var(--border-color);
            border-top-color: var(--primary-red);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* ===== SCROLLBAR STYLING ===== */
        ::-webkit-scrollbar {
            width: 10px;
        }
        
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: linear-gradient(var(--primary-red), #c12e16);
            border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--primary-hover);
        }
        
        /* ===== HEATMAP STYLES ===== */
        .heatmap-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .heatmap-card {
            background: white;
            border: 2px solid var(--border-color);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
        }
        
        .heatmap-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--text-dark);
        }
        
        .heatmap-image {
            width: 100%;
            height: 250px;
            object-fit: contain;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            margin-bottom: 15px;
        }
        
        /* ===== VISUALIZATION MAP ===== */
        .visualization-map {
            width: 100%;
            height: 500px;
            border-radius: 15px;
            border: 2px solid var(--border-color);
            margin-top: 20px;
        }
        
        /* ===== TIME REPORT STYLES ===== */
        .time-report-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .time-report-card {
            background: white;
            border: 2px solid var(--border-color);
            border-radius: 15px;
            padding: 20px;
        }
        
        .time-report-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--text-dark);
        }
        
        .chart-container {
            width: 100%;
            height: 200px;
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <!-- Mobile Menu Toggle -->
    <button class="mobile-menu-toggle" id="mobileMenuToggle">
        <i class="fas fa-bars"></i>
    </button>

    <div class="dashboard">
        <!-- Sidebar -->
        <div class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <h2>
                    <i class="fas fa-map-marked-alt"></i>
                    Campus Mapper
                </h2>
                <div class="sidebar-subtitle">Administration Dashboard</div>
            </div>
            
            <nav>
                <ul>
                    <li><a href="#" class="active" onclick="showSection('overview')">
                        <i class="fas fa-tachometer-alt"></i>
                        Dashboard Overview
                    </a></li>
                    <li><a href="#" onclick="showSection('maps')">
                        <i class="fas fa-map"></i>
                        Campus Maps
                    </a></li>
                    <li><a href="#" onclick="showSection('filtering')">
                        <i class="fas fa-filter"></i>
                        Filter & Export Data
                    </a></li>
                    <li><a href="#" onclick="showSection('heatmaps')">
                        <i class="fas fa-fire"></i>
                        Heatmaps
                    </a></li>
                    <li><a href="#" onclick="showSection('visualization')">
                        <i class="fas fa-project-diagram"></i>
                        Route Visualization
                    </a></li>
                    <li><a href="#" onclick="showSection('reports')">
                        <i class="fas fa-chart-bar"></i>
                        Special Reports
                    </a></li>
                    <li><a href="#" onclick="showSection('settings')">
                        <i class="fas fa-cog"></i>
                        Settings
                    </a></li>
                    <li><a href="/" target="_blank">
                        <i class="fas fa-external-link-alt"></i>
                        User App
                    </a></li>
                </ul>
            </nav>
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 0.9rem; color: #bdc3c7; margin-bottom: 15px;">
                    <i class="fas fa-info-circle"></i>
                    Quick Stats
                </div>
                <div id="sidebarStats">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span>Routes:</span>
                        <span id="sidebarRoutes">0</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span>Maps:</span>
                        <span id="sidebarMaps">0</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>Active:</span>
                        <span id="sidebarActive">0</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <!-- Header -->
            <div class="header">
                <h1 id="sectionTitle">
                    <i class="fas fa-tachometer-alt"></i>
                    Dashboard Overview
                </h1>
                <div class="header-subtitle" id="sectionSubtitle">
                    Monitor campus movement patterns and manage mapping data
                </div>
            </div>
            
            <!-- Overview Section -->
            <div id="overview" class="content-section">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-icon route">
                            <i class="fas fa-route"></i>
                        </div>
                        <h3>Total Routes</h3>
                        <div class="value" id="totalRoutes">0</div>
                        <div class="stat-change positive" id="routeChange">
                            <i class="fas fa-arrow-up"></i>
                            <span>Loading...</span>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-icon map">
                            <i class="fas fa-map"></i>
                        </div>
                        <h3>Campus Maps</h3>
                        <div class="value" id="totalMaps">0</div>
                        <div class="stat-change positive" id="mapChange">
                            <i class="fas fa-arrow-up"></i>
                            <span>Loading...</span>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-icon user">
                            <i class="fas fa-users"></i>
                        </div>
                        <h3>Active Users</h3>
                        <div class="value" id="activeUsers">0</div>
                        <div class="stat-change positive" id="userChange">
                            <i class="fas fa-arrow-up"></i>
                            <span>Loading...</span>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-icon data">
                            <i class="fas fa-database"></i>
                        </div>
                        <h3>Data Points</h3>
                        <div class="value" id="totalData">0</div>
                        <div class="stat-change positive" id="dataChange">
                            <i class="fas fa-arrow-up"></i>
                            <span>Loading...</span>
                        </div>
                    </div>
                </div>
                
                <!-- Recent Activity -->
                <div style="margin-top: 40px;">
                    <h2><i class="fas fa-history"></i> Recent Activity</h2>
                    <div class="form-grid">
                        <div>
                            <h3 style="font-size: 1.2rem; margin-bottom: 15px;">Recent Routes</h3>
                            <div id="recentRoutes" style="min-height: 200px;">
                                <div class="empty-state">
                                    <div class="empty-state-icon">
                                        <i class="fas fa-route"></i>
                                    </div>
                                    <h3>No recent routes</h3>
                                    <p>Routes will appear here as users save them</p>
                                </div>
                            </div>
                        </div>
                        <div>
                            <h3 style="font-size: 1.2rem; margin-bottom: 15px;">Recent Maps</h3>
                            <div id="recentMaps" style="min-height: 200px;">
                                <div class="empty-state">
                                    <div class="empty-state-icon">
                                        <i class="fas fa-map"></i>
                                    </div>
                                    <h3>No maps uploaded</h3>
                                    <p>Upload your first campus map</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Campus Maps Section -->
            <div id="maps" class="content-section" style="display: none;">
                <div class="tabs">
                    <button class="tab-btn active" onclick="showMapTab('manage')">
                        <i class="fas fa-list"></i>
                        Manage Maps
                    </button>
                    <button class="tab-btn" onclick="showMapTab('upload')">
                        <i class="fas fa-upload"></i>
                        Upload New Map
                    </button>
                </div>
                
                <!-- Manage Maps Tab -->
                <div id="manageMapsTab">
                    <div id="mapsList">
                        <!-- Maps will be loaded here -->
                    </div>
                </div>
                
                <!-- Upload Map Tab -->
                <div id="uploadMapTab" style="display: none;">
                    <div class="form-grid">
                        <div>
                            <div class="form-group">
                                <label><i class="fas fa-tag"></i> Map Name</label>
                                <input type="text" id="mapName" placeholder="e.g., Main Campus - Spring 2024" required>
                            </div>
                            
                            <div class="form-group">
                                <label><i class="fas fa-image"></i> Map Image (JPG/PNG)</label>
                                <input type="file" id="mapImage" accept=".jpg,.jpeg,.png" required>
                                <small style="color: var(--text-light); margin-top: 5px; display: block;">
                                    Upload campus map as JPG or PNG image
                                </small>
                            </div>
                        </div>
                        
                        <div>
                            <div class="form-section-title">
                                <i class="fas fa-globe-americas"></i>
                                Geographic Bounds (Optional)
                            </div>
                            
                            <div class="form-group">
                                <label>North Latitude</label>
                                <input type="number" step="any" id="northLat" placeholder="e.g., 42.283">
                            </div>
                            
                            <div class="form-group">
                                <label>South Latitude</label>
                                <input type="number" step="any" id="southLat" placeholder="e.g., 42.273">
                            </div>
                            
                            <div class="form-group">
                                <label>East Longitude</label>
                                <input type="number" step="any" id="eastLng" placeholder="e.g., -83.733">
                            </div>
                            
                            <div class="form-group">
                                <label>West Longitude</label>
                                <input type="number" step="any" id="westLng" placeholder="e.g., -83.743">
                            </div>
                        </div>
                    </div>
                    
                    <button class="btn" onclick="uploadCampusMap()">
                        <i class="fas fa-upload"></i>
                        Upload Campus Map
                    </button>
                </div>
            </div>
            
            <!-- Filter & Export Data Section -->
            <div id="filtering" class="content-section" style="display: none;">
                <h2><i class="fas fa-filter"></i> Filter & Export Data</h2>
                
                <div class="filters">
                    <div class="form-group">
                        <label><i class="fas fa-calendar"></i> Start Date</label>
                        <input type="date" id="filterStartDate">
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-calendar"></i> End Date</label>
                        <input type="date" id="filterEndDate">
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-car"></i> Transport Mode</label>
                        <select id="filterTransport">
                            <option value="">All Modes</option>
                            <option value="car">Car/Transit</option>
                            <option value="walking">Walking</option>
                            <option value="micromodal">Micromodal</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-map"></i> Campus Map</label>
                        <select id="filterMap">
                            <option value="">All Maps</option>
                        </select>
                    </div>
                </div>
                
                <div style="display: flex; gap: 15px; margin-bottom: 25px;">
                    <button class="btn" onclick="applyFilters()">
                        <i class="fas fa-filter"></i>
                        Apply Filters
                    </button>
                    <button class="btn btn-success" onclick="downloadData('csv')">
                        <i class="fas fa-file-csv"></i>
                        Download CSV
                    </button>
                    <button class="btn btn-success" onclick="downloadData('excel')">
                        <i class="fas fa-file-excel"></i>
                        Download Excel
                    </button>
                    <button class="btn btn-success" onclick="downloadData('json')">
                        <i class="fas fa-file-code"></i>
                        Download JSON
                    </button>
                </div>
                
                <div id="filterResults" style="margin-top: 20px;">
                    <!-- Filtered results will be displayed here -->
                </div>
            </div>
            
            <!-- Heatmaps Section -->
            <div id="heatmaps" class="content-section" style="display: none;">
                <h2><i class="fas fa-fire"></i> Stopping Points Heatmaps</h2>
                <p style="color: var(--text-light); margin-bottom: 25px;">
                    Heatmaps showing concentration of stopping points for each transport mode overlaid on campus maps
                </p>
                
                <div class="filters">
                    <div class="form-group">
                        <label><i class="fas fa-map"></i> Campus Map</label>
                        <select id="heatmapMap">
                            <option value="">Active Map (or All Maps)</option>
                        </select>
                    </div>
                </div>
                
                <div style="display: flex; gap: 15px; margin-bottom: 25px;">
                    <button class="btn" onclick="generateHeatmaps()">
                        <i class="fas fa-sync-alt"></i>
                        Generate Heatmaps
                    </button>
                </div>
                
                <div class="heatmap-container" id="heatmapContainer">
                    <!-- Heatmaps will be loaded here -->
                </div>
            </div>
            
            <!-- Route Visualization Section -->
            <div id="visualization" class="content-section" style="display: none;">
                <h2><i class="fas fa-project-diagram"></i> Route Visualization</h2>
                <p style="color: var(--text-light); margin-bottom: 25px;">
                    Map showing all drawn routes with line thickness representing frequency
                </p>
                
                <div class="filters">
                    <div class="form-group">
                        <label><i class="fas fa-calendar"></i> Start Date</label>
                        <input type="date" id="vizStartDate">
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-calendar"></i> End Date</label>
                        <input type="date" id="vizEndDate">
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-car"></i> Transport Mode</label>
                        <select id="vizTransport">
                            <option value="">All Modes</option>
                            <option value="car">Car/Transit</option>
                            <option value="walking">Walking</option>
                            <option value="micromodal">Micromodal</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-map"></i> Campus Map</label>
                        <select id="vizMap">
                            <option value="">Select a map</option>
                        </select>
                    </div>
                </div>
                
                <button class="btn" onclick="loadVisualization()" style="margin-bottom: 25px;">
                    <i class="fas fa-eye"></i>
                    Load Visualization
                </button>
                
                <div id="visualizationMap" class="visualization-map"></div>
            </div>
            
            <!-- Special Reports Section -->
            <div id="reports" class="content-section" style="display: none;">
                <h2><i class="fas fa-chart-bar"></i> Special Reports</h2>
                
                <div class="tabs">
                    <button class="tab-btn active" onclick="showReportTab('time')">
                        <i class="fas fa-clock"></i>
                        Time on Campus
                    </button>
                </div>
                
                <!-- Time on Campus Report -->
                <div id="timeReportTab">
                    <h3 style="font-size: 1.4rem; margin: 25px 0 15px;">
                        <i class="fas fa-clock"></i>
                        Time on Campus Analysis
                    </h3>
                    
                    <div class="filters">
                        <div class="form-group">
                            <label><i class="fas fa-calendar"></i> Start Date</label>
                            <input type="date" id="reportStartDate">
                        </div>
                        
                        <div class="form-group">
                            <label><i class="fas fa-calendar"></i> End Date</label>
                            <input type="date" id="reportEndDate">
                        </div>
                        
                        <div class="form-group">
                            <label><i class="fas fa-user"></i> User Type</label>
                            <select id="reportUserType">
                                <option value="">All Users</option>
                                <option value="student">Student</option>
                                <option value="faculty">Staff/Faculty</option>
                                <option value="visitor">Visitor</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                    </div>
                    
                    <button class="btn" onclick="generateTimeReport()" style="margin-bottom: 25px;">
                        <i class="fas fa-chart-line"></i>
                        Generate Time Report
                    </button>
                    
                    <div id="timeReportResults">
                        <!-- Time report results will be displayed here -->
                    </div>
                </div>
            </div>
            
            <!-- Settings Section -->
            <div id="settings" class="content-section" style="display: none;">
                <h2><i class="fas fa-cog"></i> Settings</h2>
                <p style="color: var(--text-light); margin-bottom: 25px;">
                    Configure application settings and preferences
                </p>
                
                <div class="form-grid">
                    <div>
                        <div class="form-section-title">
                            <i class="fas fa-palette"></i>
                            Appearance
                        </div>
                        
                        <div class="form-group">
                            <label><i class="fas fa-brush"></i> Theme Color</label>
                            <select id="themeColor">
                                <option value="#E4351A">Red (Default)</option>
                                <option value="#3498db">Blue</option>
                                <option value="#2ecc71">Green</option>
                                <option value="#9b59b6">Purple</option>
                                <option value="#e67e22">Orange</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label><i class="fas fa-eye"></i> Default Map View</label>
                            <select id="defaultMapView">
                                <option value="street">Street View</option>
                                <option value="satellite">Satellite</option>
                                <option value="terrain">Terrain</option>
                            </select>
                        </div>
                    </div>
                    
                    <div>
                        <div class="form-section-title">
                            <i class="fas fa-database"></i>
                            Data Management
                        </div>
                        
                        <div class="form-group">
                            <label><i class="fas fa-trash-alt"></i> Auto-cleanup Days</label>
                            <input type="number" id="cleanupDays" min="0" value="30">
                            <small style="color: var(--text-light);">Days before old data is automatically cleaned up (0 = never)</small>
                        </div>
                        
                        <div style="display: flex; gap: 15px; margin-top: 30px;">
                            <button class="btn" onclick="saveSettings()">
                                <i class="fas fa-save"></i>
                                Save Settings
                            </button>
                            <button class="btn btn-danger" onclick="confirmReset()">
                                <i class="fas fa-undo"></i>
                                Reset to Defaults
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Confirmation Modal -->
    <div class="modal" id="confirmationModal">
        <div class="modal-content">
            <button class="modal-close" onclick="closeModal('confirmationModal')">
                <i class="fas fa-times"></i>
            </button>
            <div class="modal-header">
                <h2 class="modal-title" id="modalTitle">Confirm Action</h2>
                <p id="modalMessage">Are you sure you want to proceed?</p>
            </div>
            <div style="display: flex; gap: 15px; margin-top: 30px;">
                <button class="btn btn-danger" id="confirmAction">
                    Confirm
                </button>
                <button class="btn btn-secondary" onclick="closeModal('confirmationModal')">
                    Cancel
                </button>
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // ======================
        // DASHBOARD FUNCTIONS
        // ======================
        let currentSection = 'overview';
        let currentMapTab = 'manage';
        let currentReportTab = 'time';
        let filteredData = [];
        let vizMap = null;
        
        // Show section
        function showSection(sectionName) {
            // Hide all sections
            document.querySelectorAll('.content-section').forEach(section => {
                section.style.display = 'none';
            });
            
            // Remove active class from all nav links
            document.querySelectorAll('.sidebar nav a').forEach(link => {
                link.classList.remove('active');
            });
            
            // Add active class to clicked link
            const navLinks = {
                'overview': 0,
                'maps': 1,
                'filtering': 2,
                'heatmaps': 3,
                'visualization': 4,
                'reports': 5,
                'settings': 6
            };
            document.querySelectorAll('.sidebar nav a')[navLinks[sectionName]].classList.add('active');
            
            // Show selected section
            document.getElementById(sectionName).style.display = 'block';
            currentSection = sectionName;
            
            // Update section title
            const titles = {
                'overview': 'Dashboard Overview',
                'maps': 'Campus Maps Management',
                'filtering': 'Filter & Export Data',
                'heatmaps': 'Stopping Points Heatmaps',
                'visualization': 'Route Visualization',
                'reports': 'Special Reports',
                'settings': 'Settings'
            };
            
            const subtitles = {
                'overview': 'Monitor campus movement patterns and manage mapping data',
                'maps': 'Upload and manage campus map images with geographic bounds',
                'filtering': 'Filter and export route data with various criteria',
                'heatmaps': 'Visualize stopping point concentrations for each transport mode',
                'visualization': 'View all drawn routes with thickness indicating frequency',
                'reports': 'Generate special reports including time on campus analysis',
                'settings': 'Configure application settings and preferences'
            };
            
            document.getElementById('sectionTitle').innerHTML = `
                <i class="fas fa-${getSectionIcon(sectionName)}"></i>
                ${titles[sectionName]}
            `;
            document.getElementById('sectionSubtitle').textContent = subtitles[sectionName];
            
            // Load section data
            if (sectionName === 'overview') loadOverview();
            if (sectionName === 'maps') loadMaps();
            if (sectionName === 'filtering') loadMapFilterOptions();
            if (sectionName === 'visualization') loadVizMapOptions();
            if (sectionName === 'heatmaps') loadHeatmapMapOptions();
            if (sectionName === 'settings') loadSettings();
            
            // Close mobile menu on small screens
            if (window.innerWidth <= 768) {
                document.getElementById('sidebar').classList.remove('active');
            }
        }
        
        function getSectionIcon(section) {
            const icons = {
                'overview': 'tachometer-alt',
                'maps': 'map',
                'filtering': 'filter',
                'heatmaps': 'fire',
                'visualization': 'project-diagram',
                'reports': 'chart-bar',
                'settings': 'cog'
            };
            return icons[section] || 'circle';
        }
        
        // Map tabs
        function showMapTab(tabName) {
            currentMapTab = tabName;
            
            // Update tab buttons
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Show selected tab
            document.getElementById('manageMapsTab').style.display = tabName === 'manage' ? 'block' : 'none';
            document.getElementById('uploadMapTab').style.display = tabName === 'upload' ? 'block' : 'none';
        }
        
        // Report tabs
        function showReportTab(tabName) {
            currentReportTab = tabName;
            
            // Update tab buttons
            document.querySelectorAll('#reports .tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Show selected tab
            // Currently only one report tab
        }
        
        // Modal functions
        function showModal(modalId, title, message, confirmCallback) {
            document.getElementById('modalTitle').textContent = title;
            document.getElementById('modalMessage').textContent = message;
            document.getElementById(modalId).classList.add('active');
            
            const confirmBtn = document.getElementById('confirmAction');
            const oldHandler = confirmBtn.onclick;
            confirmBtn.onclick = function() {
                if (confirmCallback) confirmCallback();
                closeModal(modalId);
            };
        }
        
        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }
        
        // Mobile menu toggle
        document.getElementById('mobileMenuToggle').addEventListener('click', function() {
            document.getElementById('sidebar').classList.toggle('active');
        });
        
        // ======================
        // DATA LOADING FUNCTIONS
        // ======================
        async function loadOverview() {
            try {
                const response = await fetch('/api/dashboard-stats');
                const data = await response.json();
                
                if (data.success) {
                    // Update main stats
                    document.getElementById('totalRoutes').textContent = data.stats.total_routes;
                    document.getElementById('totalMaps').textContent = data.stats.total_maps;
                    document.getElementById('activeUsers').textContent = data.stats.active_users;
                    document.getElementById('totalData').textContent = data.stats.total_data_points.toLocaleString();
                    
                    // Update sidebar stats
                    document.getElementById('sidebarRoutes').textContent = data.stats.total_routes;
                    document.getElementById('sidebarMaps').textContent = data.stats.total_maps;
                    document.getElementById('sidebarActive').textContent = data.stats.active_users;
                    
                    // Load recent routes
                    await loadRecentRoutes();
                    await loadRecentMaps();
                }
            } catch (error) {
                console.error('Error loading overview:', error);
                showAlert('error', 'Failed to load dashboard data');
            }
        }
        
        async function loadRecentRoutes() {
            try {
                const response = await fetch('/api/recent-routes?limit=5');
                const data = await response.json();
                
                if (data.success && data.routes.length > 0) {
                    const container = document.getElementById('recentRoutes');
                    let html = '';
                    
                    data.routes.forEach(route => {
                        const date = new Date(route.created_at).toLocaleDateString();
                        html += `
                            <div class="map-item" style="margin-bottom: 15px;">
                                <div class="map-details">
                                    <h4>Route #${route.route_id}</h4>
                                    <div class="map-meta">
                                        <span class="map-meta-item">
                                            <i class="fas fa-user"></i>
                                            ${route.user_type || 'Unknown'}
                                        </span>
                                        <span class="map-meta-item">
                                            <i class="fas fa-${getTransportIcon(route.transport_mode)}"></i>
                                            ${route.transport_mode}
                                        </span>
                                        <span class="map-meta-item">
                                            <i class="fas fa-calendar"></i>
                                            ${date}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    
                    container.innerHTML = html;
                } else {
                    document.getElementById('recentRoutes').innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">
                                <i class="fas fa-route"></i>
                            </div>
                            <h3>No recent routes</h3>
                            <p>Routes will appear here as users save them</p>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Error loading recent routes:', error);
            }
        }
        
        async function loadRecentMaps() {
            try {
                const response = await fetch('/api/recent-maps?limit=5');
                const data = await response.json();
                
                if (data.success && data.maps.length > 0) {
                    const container = document.getElementById('recentMaps');
                    let html = '';
                    
                    data.maps.forEach(map => {
                        const date = new Date(map.created_at).toLocaleDateString();
                        html += `
                            <div class="map-item ${map.is_active ? 'active' : ''}" style="margin-bottom: 15px;">
                                <div class="map-details">
                                    <h4>${map.name}</h4>
                                    <div class="map-meta">
                                        <span class="map-meta-item">
                                            <i class="fas fa-calendar"></i>
                                            ${date}
                                        </span>
                                        <span class="map-status ${map.is_active ? 'active' : 'inactive'}">
                                            ${map.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    
                    container.innerHTML = html;
                } else {
                    document.getElementById('recentMaps').innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">
                                <i class="fas fa-map"></i>
                            </div>
                            <h3>No maps uploaded</h3>
                            <p>Upload your first campus map</p>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Error loading recent maps:', error);
            }
        }
        
        async function loadMaps() {
            try {
                const response = await fetch('/api/campus-maps');
                const data = await response.json();
                
                if (data.success) {
                    const container = document.getElementById('mapsList');
                    
                    if (data.maps.length === 0) {
                        container.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-map"></i>
                                </div>
                                <h3>No campus maps found</h3>
                                <p>Upload your first campus map to get started!</p>
                            </div>
                        `;
                        return;
                    }
                    
                    let html = '';
                    data.maps.forEach(map => {
                        const date = new Date(map.created_at).toLocaleDateString();
                        html += `
                            <div class="map-item ${map.is_active ? 'active' : ''}">
                                <div class="map-details">
                                    <h4>${map.name}</h4>
                                    <div class="map-meta">
                                        <span class="map-meta-item">
                                            <i class="fas fa-image"></i>
                                            ${map.image_filename}
                                        </span>
                                        <span class="map-meta-item">
                                            <i class="fas fa-calendar"></i>
                                            ${date}
                                        </span>
                                        ${map.north_lat ? `
                                            <span class="map-meta-item">
                                                <i class="fas fa-globe"></i>
                                                Bounds Set
                                            </span>
                                        ` : ''}
                                        <span class="map-status ${map.is_active ? 'active' : 'inactive'}">
                                            ${map.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </div>
                                </div>
                                <div class="map-actions">
                                    ${!map.is_active ? `
                                        <button class="btn btn-success" onclick="activateMap(${map.id})">
                                            <i class="fas fa-check"></i>
                                            Activate
                                        </button>
                                    ` : ''}
                                    <button class="btn btn-danger" onclick="deleteMap(${map.id})">
                                        <i class="fas fa-trash"></i>
                                        Delete
                                    </button>
                                </div>
                            </div>
                        `;
                    });
                    
                    container.innerHTML = html;
                }
            } catch (error) {
                console.error('Error loading maps:', error);
                showAlert('error', 'Failed to load campus maps');
            }
        }
        
        async function loadMapFilterOptions() {
            try {
                const response = await fetch('/api/campus-maps');
                const data = await response.json();
                
                if (data.success) {
                    const filterSelect = document.getElementById('filterMap');
                    let html = '<option value="">All Maps</option>';
                    
                    data.maps.forEach(map => {
                        html += `<option value="${map.id}">${map.name}</option>`;
                    });
                    
                    filterSelect.innerHTML = html;
                }
            } catch (error) {
                console.error('Error loading map options:', error);
            }
        }
        
        async function loadVizMapOptions() {
            try {
                const response = await fetch('/api/campus-maps');
                const data = await response.json();
                
                if (data.success) {
                    const vizSelect = document.getElementById('vizMap');
                    let html = '<option value="">Select a map</option>';
                    
                    data.maps.forEach(map => {
                        html += `<option value="${map.id}">${map.name}</option>`;
                    });
                    
                    vizSelect.innerHTML = html;
                }
            } catch (error) {
                console.error('Error loading viz map options:', error);
            }
        }
        
        async function loadHeatmapMapOptions() {
            try {
                const response = await fetch('/api/campus-maps');
                const data = await response.json();
                
                if (data.success) {
                    const heatmapSelect = document.getElementById('heatmapMap');
                    let html = '<option value="">Active Map (or All Maps)</option>';
                    
                    data.maps.forEach(map => {
                        const active = map.is_active ? ' (Active)' : '';
                        html += `<option value="${map.id}">${map.name}${active}</option>`;
                    });
                    
                    if (heatmapSelect) {
                        heatmapSelect.innerHTML = html;
                    }
                }
            } catch (error) {
                console.error('Error loading heatmap map options:', error);
            }
        }
        
        // ======================
        // FILTER & EXPORT FUNCTIONS
        // ======================
        async function applyFilters() {
            try {
                const startDate = document.getElementById('filterStartDate').value;
                const endDate = document.getElementById('filterEndDate').value;
                const transport = document.getElementById('filterTransport').value;
                const mapId = document.getElementById('filterMap').value;
                
                const params = new URLSearchParams();
                if (startDate) params.append('start_date', startDate);
                if (endDate) params.append('end_date', endDate);
                if (transport) params.append('transport_mode', transport);
                if (mapId) params.append('campus_map_id', mapId);
                
                const response = await fetch(`/api/filter-routes?${params}`);
                const data = await response.json();
                
                filteredData = data.routes || [];
                
                const resultsDiv = document.getElementById('filterResults');
                if (filteredData.length === 0) {
                    resultsDiv.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">
                                <i class="fas fa-search"></i>
                            </div>
                            <h3>No routes found</h3>
                            <p>No routes match your filter criteria</p>
                        </div>
                    `;
                    return;
                }
                
                let html = `
                    <h3 style="font-size: 1.2rem; margin-bottom: 15px;">
                        <i class="fas fa-list"></i>
                        Filtered Results (${filteredData.length} routes)
                    </h3>
                    <div style="overflow-x: auto;">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Route ID</th>
                                    <th>Date</th>
                                    <th>Transport Mode</th>
                                    <th>User Type</th>
                                    <th>Segments</th>
                                    <th>Total Time</th>
                                </tr>
                            </thead>
                            <tbody>
                `;
                
                filteredData.forEach(route => {
                    const date = new Date(route.timestamp).toLocaleDateString();
                    html += `
                        <tr>
                            <td>${route.route_id}</td>
                            <td>${date}</td>
                            <td>
                                <span class="badge ${getTransportBadge(route.transport_mode)}">
                                    <i class="fas fa-${getTransportIcon(route.transport_mode)}"></i>
                                    ${route.transport_mode}
                                </span>
                            </td>
                            <td>${route.user_type || 'Unknown'}</td>
                            <td>${route.segments || 1}</td>
                            <td>${route.total_time || 'N/A'}</td>
                        </tr>
                    `;
                });
                
                html += '</tbody></table></div>';
                resultsDiv.innerHTML = html;
                
                showAlert('success', `Found ${filteredData.length} routes matching your criteria`);
                
            } catch (error) {
                console.error('Error applying filters:', error);
                showAlert('error', 'Failed to apply filters');
            }
        }
        
        function downloadData(format) {
            if (filteredData.length === 0) {
                showAlert('error', 'No data to download. Please apply filters first.');
                return;
            }
            
            const startDate = document.getElementById('filterStartDate').value;
            const endDate = document.getElementById('filterEndDate').value;
            const transport = document.getElementById('filterTransport').value;
            const mapId = document.getElementById('filterMap').value;
            
            const params = new URLSearchParams();
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            if (transport) params.append('transport_mode', transport);
            if (mapId) params.append('campus_map_id', mapId);
            params.append('format', format);
            
            window.open(`/api/export-filtered-data?${params}`, '_blank');
        }
        
        // ======================
        // HEATMAP FUNCTIONS
        // ======================
        async function generateHeatmaps() {
            try {
                // Get selected map for heatmap generation
                const mapId = document.getElementById('heatmapMap')?.value || '';
                const params = new URLSearchParams();
                if (mapId) params.append('campus_map_id', mapId);
                
                const response = await fetch(`/api/heatmaps/generate?${params}`);
                const data = await response.json();
                
                if (data.success && data.heatmaps) {
                    const container = document.getElementById('heatmapContainer');
                    let html = '';
                    
                    data.heatmaps.forEach(heatmap => {
                        if (heatmap.image_data) {
                            html += `
                                <div class="heatmap-card">
                                    <div class="heatmap-title">
                                        <i class="fas fa-${getTransportIcon(heatmap.mode)}"></i>
                                        ${heatmap.mode.charAt(0).toUpperCase() + heatmap.mode.slice(1)} Stopping Points
                                    </div>
                                    <img src="${heatmap.image_data}" alt="${heatmap.mode} heatmap" class="heatmap-image">
                                    <button class="btn" onclick="downloadHeatmap('${heatmap.mode}')">
                                        <i class="fas fa-download"></i>
                                        Download PNG
                                    </button>
                                </div>
                            `;
                        } else if (heatmap.message) {
                            html += `
                                <div class="heatmap-card">
                                    <div class="heatmap-title">
                                        <i class="fas fa-${getTransportIcon(heatmap.mode)}"></i>
                                        ${heatmap.mode.charAt(0).toUpperCase() + heatmap.mode.slice(1)} Stopping Points
                                    </div>
                                    <div class="empty-state">
                                        <p>${heatmap.message}</p>
                                    </div>
                                </div>
                            `;
                        }
                    });
                    
                    if (html === '') {
                        html = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-fire"></i>
                                </div>
                                <h3>No heatmap data</h3>
                                <p>No stopping point data available for heatmaps</p>
                            </div>
                        `;
                    }
                    
                    container.innerHTML = html;
                } else {
                    showAlert('error', 'Failed to generate heatmaps');
                }
            } catch (error) {
                console.error('Error generating heatmaps:', error);
                showAlert('error', 'Failed to generate heatmaps');
            }
        }
        
        function downloadHeatmap(mode) {
            const mapId = document.getElementById('heatmapMap')?.value || '';
            const params = new URLSearchParams();
            if (mapId) params.append('campus_map_id', mapId);
            window.open(`/api/heatmaps/download/${mode}?${params}`, '_blank');
        }
        
        // ======================
        // VISUALIZATION FUNCTIONS
        // ======================
        async function loadVisualization() {
            try {
                const startDate = document.getElementById('vizStartDate').value;
                const endDate = document.getElementById('vizEndDate').value;
                const transport = document.getElementById('vizTransport').value;
                const mapId = document.getElementById('vizMap').value;
                
                if (!mapId) {
                    showAlert('error', 'Please select a campus map for visualization');
                    return;
                }
                
                const params = new URLSearchParams();
                if (startDate) params.append('start_date', startDate);
                if (endDate) params.append('end_date', endDate);
                if (transport) params.append('transport_mode', transport);
                params.append('campus_map_id', mapId);
                
                const response = await fetch(`/api/visualization/data?${params}`);
                const data = await response.json();
                
                if (data.success) {
                    displayVisualization(data);
                } else {
                    showAlert('error', 'Failed to load visualization data');
                }
            } catch (error) {
                console.error('Error loading visualization:', error);
                showAlert('error', 'Failed to load visualization');
            }
        }
        
        function displayVisualization(data) {
            const container = document.getElementById('visualizationMap');
            container.innerHTML = '';
            
            if (!data.map_data) {
                showAlert('error', 'Map data not available');
                return;
            }
            
            // Initialize map without base tile layer (PDF maps don't need background)
            const bounds = [
                [data.map_data.south_lat, data.map_data.west_lng],
                [data.map_data.north_lat, data.map_data.east_lng]
            ];
            
            vizMap = L.map('visualizationMap', {
                zoomControl: true,
                attributionControl: false
            }).setView(
                [(data.map_data.south_lat + data.map_data.north_lat) / 2,
                 (data.map_data.west_lng + data.map_data.east_lng) / 2],
                15
            );
            
            // Load campus map as the only layer (no base tile layer)
            const imageUrl = `/api/maps/${data.map_data.id}/image`;
            L.imageOverlay(imageUrl, bounds, {
                opacity: 0.8,
                interactive: false
            }).addTo(vizMap);
            vizMap.fitBounds(bounds);
            
            // Add aggregated routes with thickness based on frequency
            if (data.segments && data.segments.length > 0) {
                let totalSegments = 0;
                data.segments.forEach(segment => {
                    try {
                        const coordinates = segment.coordinates;
                        if (coordinates && coordinates.length > 0) {
                            const latLngs = coordinates.map(coord => [coord.lat, coord.lng]);
                            
                            // Calculate thickness based on frequency (more frequent = thicker)
                            const frequency = segment.frequency || 1;
                            const thickness = Math.min(15, 3 + Math.log(frequency) * 2);
                            
                            // Calculate opacity based on frequency
                            const opacity = Math.min(0.9, 0.4 + (frequency / 10) * 0.5);
                            
                            const color = getTransportColor(segment.transport_mode);
                            
                            L.polyline(latLngs, {
                                color: color,
                                weight: thickness,
                                opacity: opacity,
                                lineCap: 'round',
                                lineJoin: 'round'
                            }).addTo(vizMap);
                            
                            totalSegments++;
                        }
                    } catch (e) {
                        console.error('Error displaying segment:', e);
                    }
                });
                
                showAlert('success', `Loaded ${totalSegments} aggregated route segments for visualization`);
            } else {
                showAlert('info', 'No route data found for the selected criteria');
            }
        }
        
        // ======================
        // REPORT FUNCTIONS
        // ======================
        async function generateTimeReport() {
            try {
                const startDate = document.getElementById('reportStartDate').value;
                const endDate = document.getElementById('reportEndDate').value;
                const userType = document.getElementById('reportUserType').value;
                
                const params = new URLSearchParams();
                if (startDate) params.append('start_date', startDate);
                if (endDate) params.append('end_date', endDate);
                if (userType) params.append('user_type', userType);
                
                const response = await fetch(`/api/reports/time-on-campus?${params}`);
                const data = await response.json();
                
                if (data.success) {
                    displayTimeReport(data);
                } else {
                    showAlert('error', 'Failed to generate time report');
                }
            } catch (error) {
                console.error('Error generating time report:', error);
                showAlert('error', 'Failed to generate time report');
            }
        }
        
        function displayTimeReport(data) {
            const container = document.getElementById('timeReportResults');
            
            let html = `
                <div class="time-report-grid">
                    <div class="time-report-card">
                        <div class="time-report-title">
                            <i class="fas fa-users"></i>
                            User Distribution
                        </div>
                        <div class="chart-container">
                            <canvas id="userDistributionChart"></canvas>
                        </div>
                    </div>
                    
                    <div class="time-report-card">
                        <div class="time-report-title">
                            <i class="fas fa-clock"></i>
                            Average Time by Mode
                        </div>
                        <div class="chart-container">
                            <canvas id="timeByModeChart"></canvas>
                        </div>
                    </div>
                </div>
            `;
            
            container.innerHTML = html;
            
            // Create charts
            createTimeReportCharts(data);
        }
        
        function createTimeReportCharts(data) {
            // User Distribution Chart
            const userCtx = document.getElementById('userDistributionChart').getContext('2d');
            new Chart(userCtx, {
                type: 'doughnut',
                data: {
                    labels: Object.keys(data.user_distribution || {}),
                    datasets: [{
                        data: Object.values(data.user_distribution || {}),
                        backgroundColor: ['#E4351A', '#28a745', '#17a2b8', '#ffc107', '#6c757d']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
            
            // Time by Mode Chart
            const timeCtx = document.getElementById('timeByModeChart').getContext('2d');
            new Chart(timeCtx, {
                type: 'bar',
                data: {
                    labels: Object.keys(data.time_by_mode || {}),
                    datasets: [{
                        label: 'Average Time (seconds)',
                        data: Object.values(data.time_by_mode || {}),
                        backgroundColor: ['#E4351A', '#28a745', '#17a2b8']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Seconds'
                            }
                        }
                    }
                }
            });
        }
        
        // ======================
        // ACTION FUNCTIONS
        // ======================
        async function uploadCampusMap() {
            const name = document.getElementById('mapName').value.trim();
            const imageInput = document.getElementById('mapImage');
            const northLat = document.getElementById('northLat').value;
            const southLat = document.getElementById('southLat').value;
            const eastLng = document.getElementById('eastLng').value;
            const westLng = document.getElementById('westLng').value;
            
            if (!name) {
                showAlert('error', 'Please enter a map name');
                return;
            }
            
            if (!imageInput.files || !imageInput.files[0]) {
                showAlert('error', 'Please select a map image file');
                return;
            }
            
            const formData = new FormData();
            formData.append('name', name);
            formData.append('image_file', imageInput.files[0]);
            if (northLat) formData.append('north_lat', northLat);
            if (southLat) formData.append('south_lat', southLat);
            if (eastLng) formData.append('east_lng', eastLng);
            if (westLng) formData.append('west_lng', westLng);
            
            try {
                const response = await fetch('/api/upload-campus-map', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                if (data.success) {
                    showAlert('success', 'Map uploaded successfully!');
                    document.getElementById('mapName').value = '';
                    document.getElementById('mapImage').value = '';
                    document.getElementById('northLat').value = '';
                    document.getElementById('southLat').value = '';
                    document.getElementById('eastLng').value = '';
                    document.getElementById('westLng').value = '';
                    
                    // Refresh maps list
                    loadMaps();
                    loadMapFilterOptions();
                    loadVizMapOptions();
                    showMapTab('manage');
                } else {
                    showAlert('error', data.error || 'Failed to upload map');
                }
            } catch (error) {
                console.error('Error uploading map:', error);
                showAlert('error', 'Failed to upload map');
            }
        }
        
        async function activateMap(mapId) {
            try {
                const response = await fetch('/api/activate-campus-map', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ map_id: mapId })
                });
                
                const data = await response.json();
                if (data.success) {
                    showAlert('success', 'Map activated successfully!');
                    loadMaps();
                    loadOverview();
                } else {
                    showAlert('error', data.error || 'Failed to activate map');
                }
            } catch (error) {
                console.error('Error activating map:', error);
                showAlert('error', 'Failed to activate map');
            }
        }
        
        async function deleteMap(mapId) {
            showModal('confirmationModal', 'Delete Map', 
                'Are you sure you want to delete this map? This action cannot be undone.',
                async function() {
                    try {
                        const response = await fetch('/api/delete-campus-map', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ map_id: mapId })
                        });
                        
                        const data = await response.json();
                        if (data.success) {
                            showAlert('success', 'Map deleted successfully!');
                            loadMaps();
                            loadOverview();
                            loadMapFilterOptions();
                            loadVizMapOptions();
                        } else {
                            showAlert('error', data.error || 'Failed to delete map');
                        }
                    } catch (error) {
                        console.error('Error deleting map:', error);
                        showAlert('error', 'Failed to delete map');
                    }
                }
            );
        }
        
        function saveSettings() {
            // Save settings to localStorage
            const themeColor = document.getElementById('themeColor').value;
            const defaultMapView = document.getElementById('defaultMapView').value;
            const cleanupDays = document.getElementById('cleanupDays').value;
            
            localStorage.setItem('themeColor', themeColor);
            localStorage.setItem('defaultMapView', defaultMapView);
            localStorage.setItem('cleanupDays', cleanupDays);
            
            showAlert('success', 'Settings saved successfully!');
        }
        
        function loadSettings() {
            // Load settings from localStorage or use defaults
            const themeColor = localStorage.getItem('themeColor') || '#E4351A';
            const defaultMapView = localStorage.getItem('defaultMapView') || 'street';
            const cleanupDays = localStorage.getItem('cleanupDays') || '30';
            
            if (document.getElementById('themeColor')) {
                document.getElementById('themeColor').value = themeColor;
            }
            if (document.getElementById('defaultMapView')) {
                document.getElementById('defaultMapView').value = defaultMapView;
            }
            if (document.getElementById('cleanupDays')) {
                document.getElementById('cleanupDays').value = cleanupDays;
            }
        }
        
        function confirmReset() {
            showModal('confirmationModal', 'Reset Settings',
                'Are you sure you want to reset all settings to defaults?',
                function() {
                    // Reset to defaults
                    localStorage.removeItem('themeColor');
                    localStorage.removeItem('defaultMapView');
                    localStorage.removeItem('cleanupDays');
                    
                    // Update UI to show defaults
                    if (document.getElementById('themeColor')) {
                        document.getElementById('themeColor').value = '#E4351A';
                    }
                    if (document.getElementById('defaultMapView')) {
                        document.getElementById('defaultMapView').value = 'street';
                    }
                    if (document.getElementById('cleanupDays')) {
                        document.getElementById('cleanupDays').value = '30';
                    }
                    
                    showAlert('success', 'Settings reset to defaults');
                }
            );
        }
        
        // ======================
        // HELPER FUNCTIONS
        // ======================
        function getTransportIcon(mode) {
            const icons = {
                'car': 'car',
                'walking': 'person-walking',
                'micromodal': 'bicycle'
            };
            return icons[mode] || 'question';
        }
        
        function getTransportBadge(mode) {
            const badges = {
                'car': 'badge-danger',
                'walking': 'badge-success',
                'micromodal': 'badge-info'
            };
            return badges[mode] || 'badge-secondary';
        }
        
        function getTransportColor(mode) {
            const colors = {
                'car': '#E4351A',
                'walking': '#28a745',
                'micromodal': '#17a2b8'
            };
            return colors[mode] || '#666';
        }
        
        function showAlert(type, message) {
            // Create alert element
            const alert = document.createElement('div');
            alert.className = `map-item ${type === 'error' ? 'border-left: 4px solid var(--danger)' : 
                                               type === 'success' ? 'border-left: 4px solid var(--success)' :
                                               'border-left: 4px solid var(--info)'}`;
            alert.innerHTML = `
                <div style="display: flex; align-items: center; gap: 15px;">
                    <i class="fas fa-${type === 'error' ? 'exclamation-circle text-danger' :
                                        type === 'success' ? 'check-circle text-success' :
                                        'info-circle text-info'}"></i>
                    <span>${message}</span>
                </div>
            `;
            
            // Add to page
            const container = document.querySelector('.main-content');
            container.insertBefore(alert, container.firstChild);
            
            // Remove after 5 seconds
            setTimeout(() => {
                alert.remove();
            }, 5000);
        }
        
        // ======================
        // INITIALIZATION
        // ======================
        document.addEventListener('DOMContentLoaded', function() {
            // Load initial data
            loadOverview();
            loadMapFilterOptions();
            loadVizMapOptions();
        });
    </script>
</body>
</html>
'''

# ===============================
# MODIFIED API ROUTES WITH NEW FUNCTIONALITY
# ===============================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

# Helper function for distance calculation
def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points in kilometers using Haversine formula."""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat/2) * math.sin(delta_lat/2) +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lng/2) * math.sin(delta_lng/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

# ======================
# NEW API ENDPOINTS FOR DRAWN DATA
# ======================

@app.route('/api/save-route-drawn', methods=['POST'])
def save_route_drawn():
    """Save a drawn route with segments (new endpoint for drawn data)."""
    try:
        data = request.get_json()
        route_id = data['routeId']
        segments = data['segments']
        user_data = data['userData']
        campus_map_id = data.get('campus_map_id')

        # Only store grade_level when the user_type is student
        user_type = (user_data.get('userType') or '').strip()
        grade_level = (user_data.get('gradeLevel') or '').strip()
        if user_type != 'student':
            grade_level = None
        elif grade_level == '':
            grade_level = None
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for idx, segment in enumerate(segments):
            # Calculate distance from start to end point
            if len(segment['path']) > 1:
                start = segment['path'][0]
                end = segment['path'][-1]
                distance = calculate_distance(start['lat'], start['lng'], end['lat'], end['lng'])
            else:
                distance = 0
            
            # Save to routes table
            cursor.execute('''
                INSERT INTO routes (timestamp, route_id, segment_id, start_lat, start_lng, 
                                  end_lat, end_lng, transport_mode, distance_km, duration_seconds, 
                                  duration_minutes, segment_type, user_type, grade_level, 
                                  department, full_name, campus_map_id)
                VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                route_id, idx+1, 
                segment['path'][0]['lat'], segment['path'][0]['lng'],
                segment['path'][-1]['lat'], segment['path'][-1]['lng'],
                segment['transportMode'], distance, segment['durationSeconds'],
                round(segment['durationSeconds'] / 60, 2) if segment['durationSeconds'] else 0,
                'stopping', user_type,
                grade_level, user_data.get('department', ''),
                user_data.get('fullName', ''), campus_map_id
            ))
            
            # Save to drawn_segments table for visualization
            cursor.execute('''
                INSERT INTO drawn_segments (route_id, segment_index, transport_mode,
                                          coordinates, duration_seconds, user_type, campus_map_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                route_id, idx+1, segment['transportMode'],
                json.dumps(segment['path']), segment['durationSeconds'],
                user_type, campus_map_id
            ))
        
        conn.commit()
        conn.close()
        
        # Update congestion data
        update_congestion_data(segments, campus_map_id)
        
        return jsonify({'success': True, 'message': 'Drawn route saved successfully'})
    except Exception as e:
        print(f"Error saving drawn route: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/filter-routes')
def get_filtered_routes():
    """Get routes filtered by various criteria."""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        transport_mode = request.args.get('transport_mode')
        campus_map_id = request.args.get('campus_map_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT DISTINCT 
                r.route_id,
                r.timestamp,
                r.user_type,
                r.transport_mode,
                r.created_at,
                m.name as map_name,
                COUNT(DISTINCT r.segment_id) as segments,
                SUM(r.duration_seconds) as total_time
            FROM routes r
            LEFT JOIN campus_maps m ON r.campus_map_id = m.id
            WHERE 1=1
        '''
        params = []
        
        if start_date:
            query += ' AND DATE(r.created_at) >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND DATE(r.created_at) <= ?'
            params.append(end_date)
        
        if transport_mode:
            query += ' AND r.transport_mode = ?'
            params.append(transport_mode)
        
        if campus_map_id:
            query += ' AND r.campus_map_id = ?'
            params.append(int(campus_map_id))
        
        query += ' GROUP BY r.route_id ORDER BY r.created_at DESC'
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        routes = []
        for row in results:
            routes.append({
                'route_id': row[0],
                'timestamp': row[1],
                'user_type': row[2],
                'transport_mode': row[3],
                'created_at': row[4],
                'map_name': row[5],
                'segments': row[6],
                'total_time': f"{row[7] // 60}m {row[7] % 60}s" if row[7] else 'N/A'
            })
        
        return jsonify({'success': True, 'routes': routes})
    except Exception as e:
        print(f"Error getting filtered routes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/export-filtered-data')
def export_filtered_data():
    """Export filtered data in various formats."""
    try:
        format_type = request.args.get('format', 'csv')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        transport_mode = request.args.get('transport_mode')
        campus_map_id = request.args.get('campus_map_id')
        
        conn = get_db_connection()
        
        query = 'SELECT * FROM routes WHERE 1=1'
        params = []
        
        if start_date:
            query += ' AND DATE(created_at) >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND DATE(created_at) <= ?'
            params.append(end_date)
        
        if transport_mode:
            query += ' AND transport_mode = ?'
            params.append(transport_mode)
        
        if campus_map_id:
            query += ' AND campus_map_id = ?'
            params.append(int(campus_map_id))
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if format_type == 'csv':
            output = io.StringIO()
            df.to_csv(output, index=False)
            output.seek(0)
            
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'campus_routes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
        elif format_type == 'json':
            return jsonify({
                'success': True,
                'data': json.loads(df.to_json(orient='records'))
            })
        else:  # excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Route Data')
            
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'campus_routes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
    except Exception as e:
        print(f"Error exporting filtered data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/heatmaps/generate')
def generate_heatmaps():
    """Generate heatmaps for stopping points overlaid on campus maps."""
    try:
        campus_map_id = request.args.get('campus_map_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get active map if no map_id specified
        map_data = None
        if campus_map_id:
            cursor.execute('SELECT * FROM campus_maps WHERE id = ?', (campus_map_id,))
            map_row = cursor.fetchone()
            if map_row:
                map_data = dict(map_row)
        else:
            cursor.execute('SELECT * FROM campus_maps WHERE is_active = 1 LIMIT 1')
            map_row = cursor.fetchone()
            if map_row:
                map_data = dict(map_row)
        
        heatmaps = []
        
        # For each transport mode
        for mode in ['car', 'walking', 'micromodal']:
            # Get stopping points (start and end points of segments) for the specific map
            query = '''
                SELECT start_lat, start_lng, end_lat, end_lng 
                FROM routes 
                WHERE transport_mode = ?
                AND (start_lat IS NOT NULL AND start_lng IS NOT NULL 
                     OR end_lat IS NOT NULL AND end_lng IS NOT NULL)
            '''
            params = [mode]
            
            if map_data:
                query += ' AND campus_map_id = ?'
                params.append(map_data['id'])
            
            cursor.execute(query, params)
            points = cursor.fetchall()
            
            if not points:
                heatmaps.append({
                    'mode': mode,
                    'image_data': None,
                    'message': f'No data available for {mode}'
                })
                continue
            
            # Collect all stopping points (start and end)
            lats = []
            lngs = []
            for p in points:
                if p['start_lat'] and p['start_lng']:
                    lats.append(p['start_lat'])
                    lngs.append(p['start_lng'])
                if p['end_lat'] and p['end_lng']:
                    lats.append(p['end_lat'])
                    lngs.append(p['end_lng'])
            
            if not lats or not lngs:
                heatmaps.append({
                    'mode': mode,
                    'image_data': None,
                    'message': f'No valid stopping points for {mode}'
                })
                continue
            
            # Create heatmap
            fig, ax = plt.subplots(figsize=(12, 10))
            
            # Load and display campus map if available
            if map_data and map_data.get('image_filename'):
                try:
                    from PIL import Image
                    map_path = os.path.join('maps', map_data['image_filename'])
                    if os.path.exists(map_path):
                        map_img = Image.open(map_path)
                        ax.imshow(map_img, extent=[
                            map_data.get('west_lng', min(lngs) - 0.01) if map_data.get('west_lng') else min(lngs) - 0.01,
                            map_data.get('east_lng', max(lngs) + 0.01) if map_data.get('east_lng') else max(lngs) + 0.01,
                            map_data.get('south_lat', min(lats) - 0.01) if map_data.get('south_lat') else min(lats) - 0.01,
                            map_data.get('north_lat', max(lats) + 0.01) if map_data.get('north_lat') else max(lats) + 0.01
                        ], aspect='auto', alpha=0.7)
                except Exception as e:
                    print(f"Error loading map image: {e}")
            
            # Overlay heatmap
            if map_data and map_data.get('west_lng') and map_data.get('east_lng') and map_data.get('south_lat') and map_data.get('north_lat'):
                ax.set_xlim(map_data['west_lng'], map_data['east_lng'])
                ax.set_ylim(map_data['south_lat'], map_data['north_lat'])
            
            hb = ax.hexbin(lngs, lats, gridsize=30, cmap='hot_r', alpha=0.8, mincnt=1)
            plt.colorbar(hb, ax=ax, label='Density')
            ax.set_xlabel('Longitude')
            ax.set_ylabel('Latitude')
            ax.set_title(f'Stopping Points Heatmap - {mode.capitalize()}')
            ax.invert_yaxis()  # Invert y-axis for proper map orientation
            plt.tight_layout()
            
            # Save to buffer
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            
            # Convert to base64
            image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            heatmaps.append({
                'mode': mode,
                'image_data': f'data:image/png;base64,{image_data}'
            })
        
        conn.close()
        return jsonify({'success': True, 'heatmaps': heatmaps})
        
    except Exception as e:
        print(f"Error generating heatmaps: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/heatmaps/download/<mode>')
def download_heatmap(mode):
    """Download heatmap as PNG with optional map overlay."""
    try:
        campus_map_id = request.args.get('campus_map_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get map data if specified
        map_data = None
        if campus_map_id:
            cursor.execute('SELECT * FROM campus_maps WHERE id = ?', (campus_map_id,))
            map_row = cursor.fetchone()
            if map_row:
                map_data = dict(map_row)
        
        # Get stopping points (start and end) for the mode
        query = '''
            SELECT start_lat, start_lng, end_lat, end_lng 
            FROM routes 
            WHERE transport_mode = ?
            AND (start_lat IS NOT NULL AND start_lng IS NOT NULL 
                 OR end_lat IS NOT NULL AND end_lng IS NOT NULL)
        '''
        params = [mode]
        
        if map_data:
            query += ' AND campus_map_id = ?'
            params.append(map_data['id'])
        
        cursor.execute(query, params)
        points = cursor.fetchall()
        
        conn.close()
        
        if not points:
            return jsonify({'error': f'No data available for {mode}'}), 404
        
        # Collect all stopping points
        lats = []
        lngs = []
        for p in points:
            if p['start_lat'] and p['start_lng']:
                lats.append(p['start_lat'])
                lngs.append(p['start_lng'])
            if p['end_lat'] and p['end_lng']:
                lats.append(p['end_lat'])
                lngs.append(p['end_lng'])
        
        if not lats or not lngs:
            return jsonify({'error': f'No valid stopping points for {mode}'}), 404
        
        # Create heatmap
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # Load and display campus map if available
        if map_data and map_data.get('image_filename'):
            try:
                from PIL import Image
                map_path = os.path.join('maps', map_data['image_filename'])
                if os.path.exists(map_path):
                    map_img = Image.open(map_path)
                    ax.imshow(map_img, extent=[
                        map_data.get('west_lng', min(lngs) - 0.01) if map_data.get('west_lng') else min(lngs) - 0.01,
                        map_data.get('east_lng', max(lngs) + 0.01) if map_data.get('east_lng') else max(lngs) + 0.01,
                        map_data.get('south_lat', min(lats) - 0.01) if map_data.get('south_lat') else min(lats) - 0.01,
                        map_data.get('north_lat', max(lats) + 0.01) if map_data.get('north_lat') else max(lats) + 0.01
                    ], aspect='auto', alpha=0.7)
            except Exception as e:
                print(f"Error loading map image: {e}")
        
        # Overlay heatmap
        if map_data and map_data.get('west_lng') and map_data.get('east_lng') and map_data.get('south_lat') and map_data.get('north_lat'):
            ax.set_xlim(map_data['west_lng'], map_data['east_lng'])
            ax.set_ylim(map_data['south_lat'], map_data['north_lat'])
        
        hb = ax.hexbin(lngs, lats, gridsize=30, cmap='hot_r', alpha=0.8, mincnt=1)
        plt.colorbar(hb, ax=ax, label='Density')
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.set_title(f'Stopping Points Heatmap - {mode.capitalize()}')
        ax.invert_yaxis()
        plt.tight_layout()
        
        # Save to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'{mode}_stopping_points_heatmap_{datetime.now().strftime("%Y%m%d")}.png'
        )
        
    except Exception as e:
        print(f"Error downloading heatmap: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/visualization/data')
def get_visualization_data():
    """Get aggregated route visualization data for a specific map."""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        transport_mode = request.args.get('transport_mode')
        campus_map_id = request.args.get('campus_map_id')
        
        if not campus_map_id:
            return jsonify({'success': False, 'error': 'campus_map_id is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get map data
        cursor.execute('SELECT * FROM campus_maps WHERE id = ?', (campus_map_id,))
        map_row = cursor.fetchone()
        if not map_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Map not found'}), 404
        
        map_data = dict(map_row)
        
        # Get all drawn segments for this map with filtering
        query = '''
            SELECT 
                ds.route_id,
                ds.segment_index,
                ds.transport_mode,
                ds.coordinates,
                ds.created_at
            FROM drawn_segments ds
            WHERE ds.campus_map_id = ?
        '''
        params = [int(campus_map_id)]
        
        if start_date:
            query += ' AND DATE(ds.created_at) >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND DATE(ds.created_at) <= ?'
            params.append(end_date)
        if transport_mode:
            query += ' AND ds.transport_mode = ?'
            params.append(transport_mode)
        
        query += ' ORDER BY ds.transport_mode, ds.route_id, ds.segment_index'
        cursor.execute(query, params)
        segments = cursor.fetchall()
        
        # Aggregate segments by similar paths (group by transport mode and similar coordinates)
        aggregated_segments = {}
        
        for segment in segments:
            try:
                coords = json.loads(segment['coordinates'])
                if not coords or len(coords) == 0:
                    continue
                
                # Create a key based on transport mode and rounded coordinates (for aggregation)
                # Round coordinates to 5 decimal places (~1 meter precision) for grouping
                rounded_coords = [
                    {
                        'lat': round(coord.get('lat', 0), 5),
                        'lng': round(coord.get('lng', 0), 5)
                    }
                    for coord in coords
                ]
                coord_key = json.dumps(rounded_coords)
                segment_key = f"{segment['transport_mode']}_{coord_key}"
                
                if segment_key not in aggregated_segments:
                    aggregated_segments[segment_key] = {
                        'transport_mode': segment['transport_mode'],
                        'coordinates': coords,  # Use original coordinates for display
                        'frequency': 0
                    }
                
                aggregated_segments[segment_key]['frequency'] += 1
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing segment coordinates: {e}")
                continue
        
        # Convert to list format
        aggregated_list = []
        for key, seg_data in aggregated_segments.items():
            aggregated_list.append({
                'transport_mode': seg_data['transport_mode'],
                'coordinates': seg_data['coordinates'],
                'frequency': seg_data['frequency']
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'segments': aggregated_list,
            'map_data': map_data
        })
        
    except Exception as e:
        print(f"Error getting visualization data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reports/time-on-campus')
def get_time_on_campus_report():
    """Generate time on campus report."""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        user_type = request.args.get('user_type')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        query = '''
            SELECT 
                user_type,
                transport_mode,
                SUM(duration_seconds) as total_time,
                COUNT(DISTINCT route_id) as route_count
            FROM routes
            WHERE 1=1
        '''
        params = []
        
        if start_date:
            query += ' AND DATE(created_at) >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND DATE(created_at) <= ?'
            params.append(end_date)
        if user_type:
            query += ' AND user_type = ?'
            params.append(user_type)
        
        query += ' GROUP BY user_type, transport_mode'
        cursor.execute(query, params)
        data = cursor.fetchall()
        
        # Process data for charts
        user_distribution = {}
        time_by_mode = {'car': 0, 'walking': 0, 'micromodal': 0}
        
        for row in data:
            user_type = row['user_type']
            mode = row['transport_mode']
            total_time = row['total_time'] or 0
            
            # User distribution
            if user_type not in user_distribution:
                user_distribution[user_type] = 0
            user_distribution[user_type] += row['route_count'] or 0
            
            # Time by mode
            if mode in time_by_mode:
                time_by_mode[mode] += total_time
        
        conn.close()
        
        return jsonify({
            'success': True,
            'user_distribution': user_distribution,
            'time_by_mode': time_by_mode
        })
        
    except Exception as e:
        print(f"Error generating time report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ======================
# EXISTING API ENDPOINTS (unchanged)
# ======================

@app.route('/api/active-campus-map')
def get_active_campus_map():
    """Get the currently active campus map."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, image_filename, north_lat, south_lat, east_lng, west_lng, is_active
            FROM campus_maps 
            WHERE is_active = 1 
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return jsonify({
                'success': True,
                'map': {
                    'id': result[0],
                    'name': result[1],
                    'image_filename': result[2],
                    'bounds_north': result[3],
                    'bounds_south': result[4],
                    'bounds_east': result[5],
                    'bounds_west': result[6],
                    'is_active': bool(result[7])
                }
            })
        else:
            return jsonify({
                'success': True,
                'map': None
            })
    except Exception as e:
        print(f"Error getting active campus map: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/campus-maps')
def get_all_campus_maps():
    """Get all campus maps."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM campus_maps ORDER BY created_at DESC')
        maps = cursor.fetchall()
        conn.close()
        
        map_list = []
        for map_item in maps:
            map_list.append({
                'id': map_item[0],
                'name': map_item[1],
                'image_filename': map_item[2],
                'north_lat': map_item[3],
                'south_lat': map_item[4],
                'east_lng': map_item[5],
                'west_lng': map_item[6],
                'is_active': bool(map_item[7]),
                'created_at': map_item[8]
            })
        
        return jsonify({'success': True, 'maps': map_list})
    except Exception as e:
        print(f"Error getting campus maps: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/upload-campus-map', methods=['POST'])
def upload_campus_map():
    """Upload a new campus map (JPG/PNG)."""
    try:
        name = request.form['name']
        image_file = request.files['image_file']
        
        if not image_file:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        # Validate file type
        allowed_extensions = {'jpg', 'jpeg', 'png'}
        filename = secure_filename(image_file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'Only JPG and PNG files are allowed'}), 400
        
        # Save image file
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        image_path = os.path.join("maps", unique_filename)
        image_file.save(image_path)
        
        # Get optional bounds
        north_lat = request.form.get('north_lat')
        south_lat = request.form.get('south_lat')
        east_lng = request.form.get('east_lng')
        west_lng = request.form.get('west_lng')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Deactivate all other maps if this one should be active
        cursor.execute('UPDATE campus_maps SET is_active = 0')
        
        # Insert new map
        cursor.execute('''
            INSERT INTO campus_maps (name, image_filename, north_lat, south_lat, east_lng, west_lng, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, unique_filename,
            float(north_lat) if north_lat else None,
            float(south_lat) if south_lat else None,
            float(east_lng) if east_lng else None,
            float(west_lng) if west_lng else None,
            1  # Make it active by default
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Campus map uploaded successfully'})
    except Exception as e:
        print(f"Error uploading campus map: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/activate-campus-map', methods=['POST'])
def activate_campus_map():
    """Activate a specific campus map."""
    try:
        data = request.get_json()
        map_id = data['map_id']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Deactivate all maps
        cursor.execute('UPDATE campus_maps SET is_active = 0')
        
        # Activate selected map
        cursor.execute('UPDATE campus_maps SET is_active = 1 WHERE id = ?', (map_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Campus map activated successfully'})
    except Exception as e:
        print(f"Error activating campus map: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/delete-campus-map', methods=['POST'])
def delete_campus_map():
    """Delete a campus map."""
    try:
        data = request.get_json()
        map_id = data['map_id']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get filename to delete image file
        cursor.execute('SELECT image_filename FROM campus_maps WHERE id = ?', (map_id,))
        result = cursor.fetchone()
        
        if result:
            image_filename = result[0]
            image_path = os.path.join("maps", image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)
        
        # Delete from database
        cursor.execute('DELETE FROM campus_maps WHERE id = ?', (map_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Campus map deleted successfully'})
    except Exception as e:
        print(f"Error deleting campus map: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/save-route', methods=['POST'])
def save_route():
    """Save a route with campus map association."""
    try:
        data = request.get_json()
        route_id = data['routeId']
        segments = data['segments']
        user_data = data['userData']
        campus_map_id = data.get('campus_map_id')

        # Only store grade_level when the user_type is student
        user_type = (user_data.get('userType') or '').strip()
        grade_level = (user_data.get('gradeLevel') or '').strip()
        if user_type != 'student':
            grade_level = None
        elif grade_level == '':
            grade_level = None
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for idx, segment in enumerate(segments):
            # Calculate distance
            distance = calculate_distance(
                segment['path'][0]['lat'], segment['path'][0]['lng'],
                segment['path'][-1]['lat'], segment['path'][-1]['lng']
            )
            
            cursor.execute('''
                INSERT INTO routes (timestamp, route_id, segment_id, start_lat, start_lng, 
                                  end_lat, end_lng, transport_mode, distance_km, duration_seconds, 
                                  duration_minutes, segment_type, user_type, grade_level, 
                                  department, full_name, campus_map_id)
                VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                route_id, idx+1, 
                segment['path'][0]['lat'], segment['path'][0]['lng'],
                segment['path'][-1]['lat'], segment['path'][-1]['lng'],
                segment['transportMode'], distance, segment['durationSeconds'],
                round(segment['durationSeconds'] / 60, 2) if segment['durationSeconds'] else 0,
                segment['segmentType'], user_type,
                grade_level, user_data.get('department', ''),
                user_data.get('fullName', ''), campus_map_id
            ))
        
        conn.commit()
        conn.close()
        
        # Update congestion data
        update_congestion_data(segments, campus_map_id)
        
        return jsonify({'success': True, 'message': 'Route saved successfully'})
    except Exception as e:
        print(f"Error saving route: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

def update_congestion_data(segments, campus_map_id=None):
    """Update congestion data based on route segments."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for segment in segments:
            # Sample points along the segment
            if len(segment['path']) > 1:
                points = sample_points_along_segment(
                    segment['path'][0]['lat'], segment['path'][0]['lng'],
                    segment['path'][-1]['lat'], segment['path'][-1]['lng'],
                    num_points=3
                )
                
                for lat, lng in points:
                    cursor.execute('''
                        INSERT INTO congestion_data (lat, lng, intensity, timestamp, campus_map_id)
                        VALUES (?, ?, ?, datetime('now'), ?)
                    ''', (lat, lng, 1, campus_map_id))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating congestion data: {e}")

def sample_points_along_segment(lat1, lng1, lat2, lng2, num_points=3):
    """Sample points along a line segment."""
    points = []
    for i in range(num_points):
        fraction = i / (num_points - 1) if num_points > 1 else 0.5
        lat = lat1 + (lat2 - lat1) * fraction
        lng = lng1 + (lng2 - lng1) * fraction
        points.append((lat, lng))
    return points

@app.route('/api/dashboard-stats')
def dashboard_stats():
    """Get dashboard statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total routes
        cursor.execute('SELECT COUNT(DISTINCT route_id) FROM routes')
        total_routes = cursor.fetchone()[0] or 0
        
        # Active users (last 7 days)
        cursor.execute("SELECT COUNT(DISTINCT route_id) FROM routes WHERE created_at > datetime('now', '-7 days')")
        active_users = cursor.fetchone()[0] or 0
        
        # Total maps
        cursor.execute('SELECT COUNT(*) FROM campus_maps')
        total_maps = cursor.fetchone()[0] or 0
        
        # Total data points
        cursor.execute('SELECT COUNT(*) FROM routes')
        total_data_points = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_routes': total_routes,
                'active_users': active_users,
                'total_maps': total_maps,
                'total_data_points': total_data_points
            }
        })
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/recent-routes')
def recent_routes():
    """Get recent routes."""
    try:
        limit = request.args.get('limit', 10)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT route_id, user_type, transport_mode, created_at
            FROM routes 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (int(limit),))
        
        results = cursor.fetchall()
        conn.close()
        
        routes = []
        for row in results:
            routes.append({
                'route_id': row[0],
                'user_type': row[1],
                'transport_mode': row[2],
                'created_at': row[3]
            })
        
        return jsonify({'success': True, 'routes': routes})
    except Exception as e:
        print(f"Error getting recent routes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/recent-maps')
def recent_maps():
    """Get recent campus maps."""
    try:
        limit = request.args.get('limit', 10)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT name, image_filename, is_active, created_at
            FROM campus_maps 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (int(limit),))
        
        results = cursor.fetchall()
        conn.close()
        
        maps = []
        for row in results:
            maps.append({
                'name': row[0],
                'image_filename': row[1],
                'is_active': bool(row[2]),
                'created_at': row[3]
            })
        
        return jsonify({'success': True, 'maps': maps})
    except Exception as e:
        print(f"Error getting recent maps: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/congestion-data')
def get_congestion_data():
    """Get congestion data for heatmap."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get aggregated congestion data
        cursor.execute('''
            SELECT lat, lng, COUNT(*) as intensity 
            FROM congestion_data 
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY lat, lng
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        data = []
        for row in results:
            data.append({
                'lat': row[0],
                'lng': row[1],
                'intensity': min(row[2], 10)  # Cap intensity for better visualization
            })
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        print(f"Error getting congestion data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/export-data')
def export_data():
    """Export data in various formats."""
    try:
        format_type = request.args.get('format', 'excel')
        campus_map_id = request.args.get('campus_map_id', '0')
        user_type = request.args.get('user_type', '')
        transport_mode = request.args.get('transport_mode', '')
        
        conn = get_db_connection()
        
        query = 'SELECT * FROM routes WHERE 1=1'
        params = []
        
        if campus_map_id != '0':
            query += ' AND campus_map_id = ?'
            params.append(int(campus_map_id))
        
        if user_type:
            query += ' AND user_type = ?'
            params.append(user_type)
        
        if transport_mode:
            query += ' AND transport_mode = ?'
            params.append(transport_mode)
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if format_type == 'csv':
            output = io.StringIO()
            df.to_csv(output, index=False)
            output.seek(0)
            
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'campus_routes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
        elif format_type == 'json':
            return jsonify({
                'success': True,
                'data': json.loads(df.to_json(orient='records'))
            })
        else:  # excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Route Data')
            
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'campus_routes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
    except Exception as e:
        print(f"Error exporting data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

# ======================
# STATIC FILE SERVING
# ======================

@app.route('/maps/<filename>')
def serve_map_image(filename):
    """Serve campus map images."""
    return send_from_directory('maps', filename)

@app.route('/api/maps/<int:map_id>/image')
def serve_map_image_by_id(map_id):
    """Serve campus map image by ID."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT image_filename FROM campus_maps WHERE id = ?', (map_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return send_from_directory('maps', result[0])
        else:
            return jsonify({'error': 'Map not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ======================
# TEST ROUTE
# ======================

@app.route('/api/test-database')
def test_database():
    """Test database connection."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT sqlite_version();')
        version = cursor.fetchone()
        conn.close()
        return jsonify({'success': True, 'message': 'SQLite database connected successfully', 'version': version[0]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ======================
# RUN APPLICATION
# ======================

if __name__ == '__main__':
    print("🚀 Starting Campus Mapper with new features...")
    print("📱 Main app: http://localhost:5001")
    print("📊 Dashboard: http://localhost:5001/dashboard")
    print("🎨 UI Theme: Red (#E4351A) accent color throughout")
    print("🔄 New Features:")
    print("   • Transport modes: Car/Transit, Walking, Micromodal")
    print("   • Drawing only (no plotting points)")
    print("   • STOP button for segments")
    print("   • Required time data")
    print("   • Undo button")
    print("   • Caution alert for far movements")
    print("   • Stored drawn data")
    print("   • Filter & export functionality")
    print("   • Heatmaps for stopping points")
    print("   • Route visualization with thickness")
    print("   • Time on campus reports")
    print("✅ Ready to use!")
    app.run(debug=True, host='0.0.0.0', port=5001)