from flask import Flask, render_template_string, jsonify, request, send_file
import json
import csv
import os
import sqlite3
from datetime import datetime
import io

app = Flask(__name__)

# Store vectors in memory (in production, use a database)
vectors_storage = {}

# Create a CSV file if it doesn't exist
CSV_FILE = 'vector_data.csv'
EXCEL_FILE = 'vector_data.xlsx'

# Note: On Render and similar platforms, files are ephemeral and may be lost on redeployment
# For production, consider using a database (PostgreSQL, MongoDB) or cloud storage (S3, Google Cloud Storage)

# Database file for better persistence
DB_FILE = 'campus_data.db'

def init_database():
    """Initialize SQLite database for better data persistence."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create routes table
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
            experience_rating INTEGER NOT NULL,
            user_type TEXT NOT NULL,
            grade_level TEXT,
            department TEXT,
            full_name TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def save_to_database(route_id, segments, user_data):
    """Save route data to SQLite database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        
        for idx, segment in enumerate(segments):
            start_lat = segment['start']['lat']
            start_lng = segment['start']['lng']
            end_lat = segment['end']['lat']
            end_lng = segment['end']['lng']
            transport = segment['transportMode']
            duration_seconds = segment.get('durationSeconds', 0)
            duration_minutes = round(duration_seconds / 60, 2)
            experience_rating = segment.get('experienceRating', 0)
            
            # Calculate distance
            from math import radians, sin, cos, sqrt, atan2
            R = 6371
            lat1, lon1 = radians(start_lat), radians(start_lng)
            lat2, lon2 = radians(end_lat), radians(end_lng)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance = R * c
            
            cursor.execute('''
                INSERT INTO routes (timestamp, route_id, segment_id, start_lat, start_lng, 
                                  end_lat, end_lng, transport_mode, distance_km, duration_seconds, 
                                  duration_minutes, experience_rating, user_type, grade_level, 
                                  department, full_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, route_id, idx+1, start_lat, start_lng, end_lat, end_lng,
                  transport, distance, duration_seconds, duration_minutes, experience_rating,
                  user_data.get('userType', ''), user_data.get('gradeLevel', ''),
                  user_data.get('department', ''), user_data.get('fullName', '')))
        
        conn.commit()
        conn.close()
        print(f"Route {route_id} saved to database")
        return True
    except Exception as e:
        print(f"Error saving to database: {e}")
        return False

# Initialize database on startup
init_database()

def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Full_Name', 'Route_ID', 'Segment_ID', 'Start_Lat', 'Start_Lng', 'End_Lat', 'End_Lng', 'Transport_Mode', 'Distance_KM', 'Duration_Seconds', 'Duration_Minutes', 'Experience_Rating', 'User_Type', 'Grade_Level', 'Department'])
    else:
        # Check if header needs updating and fix it
        with open(CSV_FILE, 'r', newline='') as f:
            reader = csv.reader(f)
            header = next(reader, [])
            if 'Full_Name' not in header or 'Timestamp' in header:
                # Backup current content
                f.seek(0)
                content = f.read()
                
                # Write new header and content
                with open(CSV_FILE, 'w', newline='') as fd:
                    writer = csv.writer(fd)
                    writer.writerow(['Full_Name', 'Route_ID', 'Segment_ID', 'Start_Lat', 'Start_Lng', 'End_Lat', 'End_Lng', 'Transport_Mode', 'Distance_KM', 'Duration_Seconds', 'Duration_Minutes', 'Experience_Rating', 'User_Type', 'Grade_Level', 'Department'])
                    # Rewrite existing data, but skip the old header
                    lines = content.split('\n')
                    if len(lines) > 1:
                        fd.write('\n'.join(lines[1:]))

initialize_csv()

def append_route_to_excel(timestamp_iso, route_id, segments, user_data):
    """Append a row to EXCEL_FILE with dynamic segment columns."""
    try:
        import pandas as pd
    except ImportError:
        print("Warning: pandas not available, Excel export disabled")
        return

    full_name = user_data.get('fullName', '')
    demographic = user_data.get('userType', '')
    department = user_data.get('department', '')
    grade_level = user_data.get('gradeLevel', '') if demographic == 'student' else 'N/A'

    row_data = {
        'Full name': [full_name],
        'Demographic': [demographic],
        'Department': [department], 
        'Grade level': [grade_level]
    }

    for idx, seg in enumerate(segments, start=1):
        start_lat = seg.get('start', {}).get('lat', '')
        start_lng = seg.get('start', {}).get('lng', '')
        end_lat = seg.get('end', {}).get('lat', '')
        end_lng = seg.get('end', {}).get('lng', '')
        transport = seg.get('transportMode', '')
        time_spent = int(seg.get('durationSeconds', 0))
        experience_rating = seg.get('experienceRating', '')

        start_point = f"{start_lat},{start_lng}" if start_lat and start_lng else ""
        end_point = f"{end_lat},{end_lng}" if end_lat and end_lng else ""

        row_data[f'Vector {idx}'] = [idx]
        row_data[f'Transportation mode {idx}'] = [transport]
        row_data[f'Start point {idx}'] = [start_point]
        row_data[f'End point {idx}'] = [end_point]
        row_data[f'Time spent {idx}'] = [time_spent]
        row_data[f'Experience rating {idx}'] = [experience_rating]

    new_row_df = pd.DataFrame(row_data)

    if os.path.exists(EXCEL_FILE):
        try:
            existing = pd.read_excel(EXCEL_FILE)
            all_cols = list(dict.fromkeys(list(existing.columns) + list(new_row_df.columns)))
            existing = existing.reindex(columns=all_cols)
            new_row_df = new_row_df.reindex(columns=all_cols)
            combined = pd.concat([existing, new_row_df], ignore_index=True)
        except Exception:
            combined = new_row_df
    else:
        combined = new_row_df

    try:
        with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
            combined.to_excel(writer, index=False, sheet_name='Vectors')
        print(f"Excel file updated: {EXCEL_FILE}")
    except Exception as e:
        print(f"Error writing Excel file: {e}")
        # Try to create a basic Excel file if it fails
        try:
            combined.to_excel(EXCEL_FILE, index=False, sheet_name='Vectors')
            print(f"Excel file created with basic method: {EXCEL_FILE}")
        except Exception as e2:
            print(f"Failed to create Excel file: {e2}")

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Campus Walk Mapper</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css" />
    <style>
        body {
            margin: 0;
            padding: 20px;
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            z-index: 9999;
            align-items: center;
            justify-content: center;
        }
        .modal-overlay.active {
            display: flex;
        }
        .modal {
            background: white;
            border-radius: 10px;
            padding: 30px;
            max-width: 500px;
            width: 90%;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
        }
        .modal h2 {
            margin-top: 0;
            color: #667eea;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #333;
        }
        .form-group select,
        .form-group input {
            width: 100%;
            padding: 10px;
            border: 2px solid #e9ecef;
            border-radius: 5px;
            font-size: 14px;
            box-sizing: border-box;
        }
        .form-group select:focus,
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        .modal-buttons {
            display: flex;
            gap: 10px;
            margin-top: 25px;
        }
        .btn-block {
            flex: 1;
        }
        .user-info-bar {
            background: #e7f3ff;
            padding: 10px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 14px;
            color: #0c5460;
            border-bottom: 1px solid #bee5eb;
        }
        .user-info-item {
            margin-right: 20px;
        }
        .user-info-label {
            font-weight: bold;
        }
        .edit-info-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .edit-info-btn:hover {
            background: #5a6fd8;
        }
        .controls {
            background: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #667eea;
            color: white;
        }
        .btn-primary:hover {
            background: #5a6fd8;
        }
        .btn-primary.active {
            background: #4c63d2;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.2);
        }
        .btn-danger {
            background: #dc3545;
            color: white;
        }
        .btn-danger:hover {
            background: #c82333;
        }
        .btn-secondary {
            background: #6c757d;
            color: white;
        }
        .btn-secondary:hover {
            background: #5a6268;
        }
        .mode-indicator {
            margin-left: auto;
            padding: 8px 12px;
            background: #e7f3ff;
            border-radius: 5px;
            font-size: 14px;
            color: #0c5460;
            font-weight: 500;
        }
        .content {
            display: flex;
            height: 600px;
        }
        #map {
            flex: 1;
            height: 100%;
            cursor: crosshair;
        }
        #map.normal-cursor {
            cursor: default;
        }
        .sidebar {
            width: 350px;
            padding: 20px;
            background-color: #f8f9fa;
            border-left: 1px solid #e9ecef;
            overflow-y: auto;
        }
        @media (max-width: 1024px) {
            .content {
                height: 500px;
            }
            .sidebar {
                width: 280px;
                padding: 15px;
            }
        }
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            .container {
                border-radius: 5px;
            }
            .content {
                flex-direction: column;
                height: auto;
                min-height: 600px;
            }
            #map {
                height: 400px;
                min-height: 300px;
            }
            .sidebar {
                width: 100%;
                border-left: none;
                border-top: 1px solid #e9ecef;
                max-height: 300px;
            }
            .controls {
                padding: 10px 15px;
                gap: 8px;
            }
            .btn {
                padding: 6px 12px;
                font-size: 12px;
            }
            .mode-indicator {
                width: 100%;
                margin-left: 0;
                margin-top: 10px;
                font-size: 12px;
            }
            .user-info-bar {
                padding: 8px 15px;
                font-size: 12px;
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
            .edit-info-btn {
                padding: 4px 12px;
                font-size: 11px;
            }
        }
        @media (max-width: 480px) {
            body {
                padding: 8px;
            }
            #map {
                height: 350px;
            }
            .sidebar {
                max-height: 250px;
                padding: 12px;
            }
            .controls {
                padding: 8px 10px;
                gap: 5px;
            }
            .btn {
                padding: 5px 8px;
                font-size: 11px;
                flex: 1;
                min-width: 60px;
            }
            .mode-indicator {
                display: none;
            }
            .user-info-bar {
                padding: 6px 10px;
                font-size: 11px;
            }
            .user-info-item {
                margin-right: 10px;
            }
        }
        .vector-item {
            background: white;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .vector-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .vector-title {
            font-weight: bold;
            color: #333;
            flex: 1;
        }
        .delete-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .delete-btn:hover {
            background: #c82333;
        }
        .vector-info {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
        .transport-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 8px;
        }
        .transport-walking { background: #d4edda; color: #155724; }
        .transport-biking { background: #fff3cd; color: #856404; }
        .transport-driving { background: #f8d7da; color: #721c24; }
        .transport-transit { background: #d1ecf1; color: #0c5460; }
        .transport-other { background: #e2e3e5; color: #383d41; }
        .stats {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #e9ecef;
        }
        .stat-item {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-size: 14px;
        }
        .stat-label {
            color: #666;
        }
        .stat-value {
            font-weight: bold;
            color: #333;
        }
        .instructions {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
            color: #0c5460;
        }
        .transport-selector {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: white;
            padding: 15px 20px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 1000;
            display: none;
            min-width: 400px;
            max-height: 90vh;
            overflow-y: auto;
        }
        .transport-selector.active {
            display: block;
        }
        .transport-selector h3 {
            margin: 0 0 10px 0;
            font-size: 16px;
            color: #333;
        }
        .transport-selector-content {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .transport-selector select {
            flex: 1;
            padding: 8px;
            border: 2px solid #667eea;
            border-radius: 5px;
            font-size: 14px;
        }
        .transport-selector button {
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 500;
        }
        .transport-selector button:hover {
            background: #5a6fd8;
        }
        .segment-info {
            font-size: 12px;
            color: #666;
            margin-bottom: 8px;
        }
        .time-input-group {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e9ecef;
        }
        .time-input-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #333;
            font-size: 14px;
        }
        .time-inputs {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .time-input {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .time-input input {
            width: 100%;
            padding: 8px;
            border: 2px solid #e9ecef;
            border-radius: 5px;
            font-size: 14px;
            box-sizing: border-box;
        }
        .time-input input:focus {
            outline: none;
            border-color: #667eea;
        }
        .time-input span {
            font-size: 11px;
            color: #666;
            text-align: center;
        }
        .time-badge {
            display: inline-block;
            padding: 2px 6px;
            background: #e7f3ff;
            color: #0c5460;
            border-radius: 8px;
            font-size: 10px;
            font-weight: 600;
            margin-left: 5px;
        }
        .star-rating {
            display: flex;
            gap: 5px;
            font-size: 28px;
        }
        .star {
            cursor: pointer;
            color: #ddd;
            transition: color 0.2s;
        }
        .star:hover,
        .star.active {
            color: #ffc107;
        }
    </style>
</head>
<body>
    <div id="userInfoModal" class="modal-overlay active">
        <div class="modal">
            <h2>Welcome! Please provide your information</h2>
            <form id="userInfoForm">
                <div class="form-group">
                    <label for="fullName">Full name:</label>
                    <input type="text" id="fullName" placeholder="e.g., Jane Doe" required>
                </div>
                <div class="form-group">
                    <label for="userType">I am a:</label>
                    <select id="userType" required>
                        <option value="">-- Select --</option>
                        <option value="student">Student</option>
                        <option value="faculty">Faculty</option>
                        <option value="staff">Staff</option>
                        <option value="visitor">Visitor</option>
                    </select>
                </div>
                <div class="form-group" id="gradeLevelGroup" style="display: none;">
                    <label for="gradeLevel">Grade Level:</label>
                    <select id="gradeLevel">
                        <option value="">-- Select --</option>
                        <option value="freshman">Freshman</option>
                        <option value="sophomore">Sophomore</option>
                        <option value="junior">Junior</option>
                        <option value="senior">Senior</option>
                        <option value="graduate">Graduate Student</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="department">Department/School (Optional):</label>
                    <input type="text" id="department" placeholder="e.g., Engineering, Business">
                </div>
                <div class="modal-buttons">
                    <button type="submit" class="btn btn-primary btn-block">Start Mapping</button>
                </div>
            </form>
        </div>
    </div>

    <div class="container">
        <div class="user-info-bar">
            <div style="display: flex; flex-wrap: wrap;">
                <div class="user-info-item" id="displayFullNameContainer">
                    <span class="user-info-label">Name:</span> <span id="displayFullName">-</span>
                </div>
                <div class="user-info-item">
                    <span class="user-info-label">Type:</span> <span id="displayUserType">-</span>
                </div>
                <div class="user-info-item" id="displayGradeLevelContainer" style="display: none;">
                    <span class="user-info-label">Grade:</span> <span id="displayGradeLevel">-</span>
                </div>
                <div class="user-info-item" id="displayDepartmentContainer" style="display: none;">
                    <span class="user-info-label">Department:</span> <span id="displayDepartment">-</span>
                </div>
            </div>
            <button class="edit-info-btn" onclick="editUserInfo()">Edit Info</button>
        </div>
        
        <div class="controls">
            <button id="drawBtn" class="btn btn-primary">Start Drawing</button>
            <button id="finishBtn" class="btn btn-secondary" disabled>Finish Line</button>
            <button id="cancelBtn" class="btn btn-secondary" disabled>Cancel</button>
            <button id="clearBtn" class="btn btn-danger">Clear All</button>
            <button id="saveBtn" class="btn btn-primary">Save to Server</button>
            <button id="exportExcelBtn" class="btn btn-secondary">Download Excel</button>
            <div id="modeIndicator" class="mode-indicator">Click "Start Drawing" to begin</div>
        </div>
        
        <div class="content">
            <div id="map"></div>
            <div class="sidebar">
                <div class="instructions">
                    <strong>How to map your walk:</strong><br>
                    1. Click "Start Drawing"<br>
                    2. Click points on the map<br>
                    3. Rate and time each segment<br>
                    4. Double-click or click "Finish Line" to complete<br>
                    5. Click "Save to Server"
                </div>
                
                <div class="stats">
                    <div class="stat-item">
                        <span class="stat-label">Total Routes:</span>
                        <span class="stat-value" id="vectorCount">0</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Total Segments:</span>
                        <span class="stat-value" id="segmentCount">0</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Total Distance:</span>
                        <span class="stat-value" id="totalLength">0.00 km</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Current Points:</span>
                        <span class="stat-value" id="currentPoints">0</span>
                    </div>
                </div>
                
                <div id="vectorList"></div>
            </div>
        </div>
        
        <div id="transportSelector" class="transport-selector">
            <h3>Tell us about this segment</h3>
            <div class="segment-info" id="segmentInfo"></div>
            <div class="transport-selector-content">
                <select id="currentTransportMode">
                    <option value="walking">Walking</option>
                    <option value="biking">Biking</option>
                    <option value="driving">Driving</option>
                    <option value="transit">Public Transit</option>
                    <option value="other">Other</option>
                </select>
            </div>
            <div class="time-input-group">
                <label>How long did you spend at this point?</label>
                <div class="time-inputs">
                    <div class="time-input">
                        <input type="number" id="segmentMinutes" min="0" max="999" value="0" placeholder="0">
                        <span>Minutes</span>
                    </div>
                    <div class="time-input">
                        <input type="number" id="segmentSeconds" min="0" max="59" value="0" placeholder="0">
                        <span>Seconds</span>
                    </div>
                </div>
            </div>
            <div class="time-input-group">
                <label>How would you rate this location? (1-5 stars)</label>
                <div class="star-rating" id="starRating">
                    <span class="star" data-value="1">★</span>
                    <span class="star" data-value="2">★</span>
                    <span class="star" data-value="3">★</span>
                    <span class="star" data-value="4">★</span>
                    <span class="star" data-value="5">★</span>
                </div>
            </div>
            <div style="margin-top: 15px;">
                <button id="confirmSegmentBtn" style="width: 100%;">Confirm Segment</button>
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
    <script>
        const imageBounds = [[0, 0], [1536, 2048]];

const map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: -2,
    maxZoom: 2,
    zoomControl: false,
    attributionControl: false
});

const imageUrl = '/static/campus-map.jpg';
const imageOverlay = L.imageOverlay(imageUrl, imageBounds).addTo(map);

map.fitBounds(imageOverlay.getBounds());
        
        let userData = {
            fullName: '',
            userType: '',
            gradeLevel: '',
            department: ''
        };
        
        let isDrawing = false;
        let currentPoints = [];
        let currentSegments = [];
        let pendingSegment = null;
        let currentPolylines = [];
        let tempLine = null;
        let vectors = new Map();
        let vectorCounter = 0;
        let selectedRating = 0;
        
        const drawBtn = document.getElementById('drawBtn');
        const finishBtn = document.getElementById('finishBtn');
        const cancelBtn = document.getElementById('cancelBtn');
        const clearBtn = document.getElementById('clearBtn');
        const saveBtn = document.getElementById('saveBtn');
        const exportExcelBtn = document.getElementById('exportExcelBtn');
        const modeIndicator = document.getElementById('modeIndicator');
        const mapElement = document.getElementById('map');
        const userInfoModal = document.getElementById('userInfoModal');
        const transportSelector = document.getElementById('transportSelector');
        const currentTransportModeSelect = document.getElementById('currentTransportMode');
        const confirmSegmentBtn = document.getElementById('confirmSegmentBtn');
        const segmentInfo = document.getElementById('segmentInfo');
        const segmentMinutesInput = document.getElementById('segmentMinutes');
        const segmentSecondsInput = document.getElementById('segmentSeconds');
        const starRating = document.getElementById('starRating');
        
        starRating.addEventListener('click', function(e) {
            if (e.target.classList.contains('star')) {
                selectedRating = parseInt(e.target.dataset.value);
                document.querySelectorAll('.star').forEach((star, idx) => {
                    if (idx < selectedRating) {
                        star.classList.add('active');
                    } else {
                        star.classList.remove('active');
                    }
                });
            }
        });
        
        confirmSegmentBtn.addEventListener('click', function() {
            if (!pendingSegment) return;
            
            const transportMode = currentTransportModeSelect.value;
            const minutes = parseInt(segmentMinutesInput.value) || 0;
            const seconds = parseInt(segmentSecondsInput.value) || 0;
            const totalSeconds = minutes * 60 + seconds;
            
            if (selectedRating === 0) {
                alert('Please select a star rating (1-5)');
                return;
            }
            
            pendingSegment.transportMode = transportMode;
            pendingSegment.durationSeconds = totalSeconds;
            pendingSegment.experienceRating = selectedRating;
            currentSegments.push(pendingSegment);
            pendingSegment = null;
            
            segmentMinutesInput.value = '0';
            segmentSecondsInput.value = '0';
            selectedRating = 0;
            document.querySelectorAll('.star').forEach(s => s.classList.remove('active'));
            
            transportSelector.classList.remove('active');
            redrawCurrentSegments();
            updateUI();
        });
        
        document.getElementById('userType').addEventListener('change', function() {
            const gradeLevelGroup = document.getElementById('gradeLevelGroup');
            if (this.value === 'student') {
                gradeLevelGroup.style.display = 'block';
                document.getElementById('gradeLevel').required = true;
            } else {
                gradeLevelGroup.style.display = 'none';
                document.getElementById('gradeLevel').required = false;
            }
        });
        
        document.getElementById('userInfoForm').addEventListener('submit', function(e) {
            e.preventDefault();
            userData.fullName = document.getElementById('fullName').value;
            userData.userType = document.getElementById('userType').value;
            userData.gradeLevel = document.getElementById('gradeLevel').value;
            userData.department = document.getElementById('department').value;
            
            updateUserInfoDisplay();
            userInfoModal.classList.remove('active');
        });
        
        function updateUserInfoDisplay() {
            const userTypeMap = {
                'student': 'Student',
                'faculty': 'Faculty',
                'staff': 'Staff',
                'visitor': 'Visitor'
            };
            
            const gradeLevelMap = {
                'freshman': 'Freshman',
                'sophomore': 'Sophomore',
                'junior': 'Junior',
                'senior': 'Senior',
                'graduate': 'Graduate'
            };
            
            document.getElementById('displayFullName').textContent = userData.fullName || '-';
            document.getElementById('displayUserType').textContent = userTypeMap[userData.userType] || '-';
            
            const gradeLevelContainer = document.getElementById('displayGradeLevelContainer');
            const gradeLevelDisplay = document.getElementById('displayGradeLevel');
            if (userData.gradeLevel) {
                gradeLevelContainer.style.display = 'block';
                gradeLevelDisplay.textContent = gradeLevelMap[userData.gradeLevel] || userData.gradeLevel;
            } else {
                gradeLevelContainer.style.display = 'none';
            }
            
            const deptContainer = document.getElementById('displayDepartmentContainer');
            const deptDisplay = document.getElementById('displayDepartment');
            if (userData.department) {
                deptContainer.style.display = 'block';
                deptDisplay.textContent = userData.department;
            } else {
                deptContainer.style.display = 'none';
            }
        }
        
        function editUserInfo() {
            document.getElementById('fullName').value = userData.fullName;
            document.getElementById('userType').value = userData.userType;
            document.getElementById('gradeLevel').value = userData.gradeLevel;
            document.getElementById('department').value = userData.department;
            
            if (userData.userType === 'student') {
                document.getElementById('gradeLevelGroup').style.display = 'block';
            }
            
            userInfoModal.classList.add('active');
        }
        
        function calculateDistance(latlng1, latlng2) {
            return latlng1.distanceTo(latlng2) / 1000;
        }
        
        function formatCoordinate(coord, precision = 6) {
            return parseFloat(coord).toFixed(precision);
        }
        
        function updateStats() {
            const vectorCount = vectors.size;
            let totalLength = 0;
            let totalSegments = 0;
            
            vectors.forEach(vector => {
                totalLength += vector.length;
                totalSegments += vector.segments.length;
            });
            
            document.getElementById('vectorCount').textContent = vectorCount;
            document.getElementById('segmentCount').textContent = totalSegments;
            document.getElementById('totalLength').textContent = totalLength.toFixed(2) + ' km';
            document.getElementById('currentPoints').textContent = currentPoints.length;
        }
        
        function updateUI() {
            if (isDrawing) {
                drawBtn.textContent = 'Drawing...';
                drawBtn.classList.add('active');
                finishBtn.disabled = currentSegments.length === 0;
                cancelBtn.disabled = false;
                
                if (pendingSegment) {
                    modeIndicator.textContent = `Waiting for rating and time...`;
                } else {
                    modeIndicator.textContent = `Drawing - ${currentPoints.length} points, ${currentSegments.length} segments`;
                }
                
                mapElement.classList.remove('normal-cursor');
            } else {
                drawBtn.textContent = 'Start Drawing';
                drawBtn.classList.remove('active');
                finishBtn.disabled = true;
                cancelBtn.disabled = true;
                modeIndicator.textContent = 'Click "Start Drawing" to begin';
                mapElement.classList.add('normal-cursor');
                transportSelector.classList.remove('active');
            }
            updateStats();
        }
        
        function addVectorToSidebar(id, segments, totalLength) {
            const vectorList = document.getElementById('vectorList');
            const vectorItem = document.createElement('div');
            vectorItem.className = 'vector-item';
            vectorItem.id = `vector-${id}`;
            
            const transportLabels = {
                'walking': 'Walking',
                'biking': 'Biking',
                'driving': 'Driving',
                'transit': 'Transit',
                'other': 'Other'
            };
            
            let totalSeconds = 0;
            segments.forEach(seg => {
                totalSeconds += seg.durationSeconds || 0;
            });
            const totalMinutes = Math.floor(totalSeconds / 60);
            const remainingSeconds = totalSeconds % 60;
            const totalTimeStr = totalMinutes > 0 
                ? `${totalMinutes}m ${remainingSeconds}s` 
                : `${remainingSeconds}s`;
            
            let segmentHTML = '';
            segments.forEach((seg, idx) => {
                const segLength = calculateDistance(seg.start, seg.end);
                const segMinutes = Math.floor(seg.durationSeconds / 60);
                const segSeconds = seg.durationSeconds % 60;
                const segTimeStr = segMinutes > 0 
                    ? `${segMinutes}m ${segSeconds}s` 
                    : `${segSeconds}s`;
                
                segmentHTML += `
                    <div style="margin: 5px 0; padding: 5px; background: #f8f9fa; border-radius: 4px;">
                        <span class="transport-badge transport-${seg.transportMode}" style="font-size: 10px;">${transportLabels[seg.transportMode]}</span>
                        <span style="font-size: 11px; color: #666; margin-left: 5px;">${segLength.toFixed(3)} km</span>
                        <span class="time-badge">${segTimeStr}</span>
                        <span class="time-badge" style="background: #fff3cd; color: #856404;">★${seg.experienceRating}</span>
                        <div style="font-size: 10px; color: #999; margin-top: 2px;">
                            ${formatCoordinate(seg.start.lat)}, ${formatCoordinate(seg.start.lng)} → 
                            ${formatCoordinate(seg.end.lat)}, ${formatCoordinate(seg.end.lng)}
                        </div>
                    </div>
                `;
            });
            
            vectorItem.innerHTML = `
                <div class="vector-header">
                    <div class="vector-title">Route #${id}</div>
                    <button class="delete-btn" onclick="deleteVector(${id})">Delete</button>
                </div>
                <div class="vector-info">Total: ${totalLength.toFixed(3)} km | ${segments.length} segments | ${totalTimeStr}</div>
                ${segmentHTML}
            `;
            
            vectorList.insertBefore(vectorItem, vectorList.firstChild);
        }
        
        function startDrawing() {
            isDrawing = true;
            currentPoints = [];
            currentSegments = [];
            pendingSegment = null;
            currentTransportModeSelect.value = 'walking';
            updateUI();
        }
        
        function getTransportColor(mode) {
            const transportColors = {
                'walking': '#28a745',
                'biking': '#ffc107',
                'driving': '#dc3545',
                'transit': '#17a2b8',
                'other': '#6c757d'
            };
            return transportColors[mode] || '#667eea';
        }
        
        function redrawCurrentSegments() {
            currentPolylines.forEach(polyline => map.removeLayer(polyline));
            currentPolylines = [];
            
            if (currentPoints.length === 0) return;
            
            if (currentPoints.length >= 1) {
                const marker = L.circleMarker(currentPoints[0], {
                    radius: 4,
                    fillColor: '#667eea',
                    color: '#667eea',
                    weight: 2,
                    fillOpacity: 0.8
                }).addTo(map);
                currentPolylines.push(marker);
            }
            
            for (let i = 0; i < currentSegments.length; i++) {
                const segment = currentSegments[i];
                
                const polyline = L.polyline([segment.start, segment.end], {
                    color: getTransportColor(segment.transportMode),
                    weight: 3,
                    opacity: 0.6,
                    dashArray: '10, 5'
                }).addTo(map);
                
                currentPolylines.push(polyline);
            }
            
            if (pendingSegment) {
                const polyline = L.polyline([pendingSegment.start, pendingSegment.end], {
                    color: '#999999',
                    weight: 3,
                    opacity: 0.4,
                    dashArray: '10, 5'
                }).addTo(map);
                
                currentPolylines.push(polyline);
            }
        }
        
        async function saveRouteToCSV(routeId, segments) {
            try {
                const response = await fetch('/api/save-csv', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        routeId: routeId,
                        segments: segments.map(seg => ({
                            start: {lat: seg.start.lat, lng: seg.start.lng},
                            end: {lat: seg.end.lat, lng: seg.end.lng},
                            transportMode: seg.transportMode,
                            durationSeconds: seg.durationSeconds,
                            experienceRating: seg.experienceRating
                        })),
                        userData: userData
                    })
                });
                
                const result = await response.json();
                if (!result.success) {
                    console.error('Error saving to CSV:', result.error);
                }
            } catch (error) {
                console.error('Error saving to CSV:', error);
            }
        }
        
        function finishDrawing() {
            if (currentSegments.length === 0) return;
            
            if (pendingSegment) {
                alert('Please confirm the transportation mode and rating for the current segment before finishing.');
                return;
            }
            
            vectorCounter++;
            
            const finalSegments = [...currentSegments];
            
            let totalLength = 0;
            finalSegments.forEach(seg => {
                totalLength += calculateDistance(seg.start, seg.end);
            });
            
            currentPolylines.forEach(polyline => map.removeLayer(polyline));
            currentPolylines = [];
            
            const finalLayers = [];
            finalSegments.forEach(seg => {
                const polyline = L.polyline([seg.start, seg.end], {
                    color: getTransportColor(seg.transportMode),
                    weight: 3,
                    opacity: 0.8
                }).addTo(map);
                
                const transportLabels = {
                    'walking': 'Walking',
                    'biking': 'Biking',
                    'driving': 'Driving',
                    'transit': 'Transit',
                    'other': 'Other'
                };
                
                polyline.bindPopup(`
                    <div style="text-align: center;">
                        <strong>Route #${vectorCounter}</strong><br>
                        ${transportLabels[seg.transportMode]}<br>
                        ${calculateDistance(seg.start, seg.end).toFixed(3)} km<br>
                        ★ ${seg.experienceRating}/5
                    </div>
                `);
                
                finalLayers.push(polyline);
            });
            
            vectors.set(vectorCounter, {
                layers: finalLayers,
                segments: finalSegments,
                length: totalLength,
                userData: {...userData}
            });
            
            addVectorToSidebar(vectorCounter, finalSegments, totalLength);
            saveRouteToCSV(vectorCounter, finalSegments);
            
            cancelDrawing();
        }
        
        function cancelDrawing() {
            isDrawing = false;
            currentPoints = [];
            currentSegments = [];
            pendingSegment = null;
            
            currentPolylines.forEach(polyline => map.removeLayer(polyline));
            currentPolylines = [];
            
            if (tempLine) {
                map.removeLayer(tempLine);
                tempLine = null;
            }
            
            updateUI();
        }
        
        function clearAllVectors() {
            if (confirm('Are you sure you want to clear all routes?')) {
                vectors.forEach(vector => {
                    vector.layers.forEach(layer => map.removeLayer(layer));
                });
                vectors.clear();
                document.getElementById('vectorList').innerHTML = '';
                updateStats();
            }
        }
        
        function deleteVector(id) {
            const vector = vectors.get(id);
            if (vector) {
                vector.layers.forEach(layer => map.removeLayer(layer));
                vectors.delete(id);
                document.getElementById(`vector-${id}`).remove();
                updateStats();
            }
        }
        
        async function saveToServer() {
            const data = {
                userData: userData,
                vectors: Array.from(vectors.entries()).map(([id, vector]) => ({
                    id: id,
                    segments: vector.segments.map(seg => ({
                        start: {lat: seg.start.lat, lng: seg.start.lng},
                        end: {lat: seg.end.lat, lng: seg.end.lng},
                        transportMode: seg.transportMode,
                        durationSeconds: seg.durationSeconds,
                        experienceRating: seg.experienceRating
                    })),
                    length: vector.length,
                    userData: vector.userData
                }))
            };
            
            try {
                const response = await fetch('/api/save', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                if (result.success) {
                    alert('Data saved successfully! ID: ' + result.session_id);
                } else {
                    alert('Error saving data: ' + result.error);
                }
            } catch (error) {
                alert('Error saving data: ' + error.message);
            }
        }
        
        drawBtn.addEventListener('click', () => {
            if (isDrawing) {
                cancelDrawing();
            } else {
                startDrawing();
            }
        });
        
        finishBtn.addEventListener('click', finishDrawing);
        cancelBtn.addEventListener('click', cancelDrawing);
        clearBtn.addEventListener('click', clearAllVectors);
        saveBtn.addEventListener('click', saveToServer);
        exportExcelBtn.addEventListener('click', () => {
            window.location.href = '/api/export-excel';
        });
        
        map.on('click', function(e) {
            if (!isDrawing) return;
            
            if (pendingSegment) {
                alert('Please select a transportation mode and rating for the current segment before adding another point.');
                return;
            }
            
            const latlng = e.latlng;
            
            if (currentPoints.length >= 1) {
                pendingSegment = {
                    start: currentPoints[currentPoints.length - 1],
                    end: latlng,
                    transportMode: null,
                    experienceRating: 0
                };
                
                const distance = calculateDistance(pendingSegment.start, pendingSegment.end);
                segmentInfo.textContent = `Segment ${currentSegments.length + 1}: ${distance.toFixed(3)} km`;
                transportSelector.classList.add('active');
                currentTransportModeSelect.value = 'walking';
                segmentMinutesInput.value = '0';
                segmentSecondsInput.value = '0';
                selectedRating = 0;
                document.querySelectorAll('.star').forEach(s => s.classList.remove('active'));
                segmentMinutesInput.focus();
            }
            
            currentPoints.push(latlng);
            redrawCurrentSegments();
            updateUI();
        });
        
        map.on('dblclick', function(e) {
            if (isDrawing && currentPoints.length >= 2) {
                e.originalEvent.preventDefault();
                finishDrawing();
            }
        });
        
        map.on('mousemove', function(e) {
            if (!isDrawing || currentPoints.length === 0 || pendingSegment) return;
            
            if (tempLine) {
                map.removeLayer(tempLine);
            }
            
            const lastPoint = currentPoints[currentPoints.length - 1];
            tempLine = L.polyline([lastPoint, e.latlng], {
                color: '#999999',
                weight: 2,
                opacity: 0.3,
                dashArray: '5, 5'
            }).addTo(map);
        });
        
        window.addEventListener('resize', function() {
            map.invalidateSize();
        });
        
        updateUI();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/save-csv', methods=['POST'])
def save_csv():
    try:
        data = request.get_json()
        route_id = data['routeId']
        segments = data['segments']
        user_data = data['userData']
        
        full_name = user_data.get('fullName', '')
        
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            
            for idx, segment in enumerate(segments):
                start_lat = segment['start']['lat']
                start_lng = segment['start']['lng']
                end_lat = segment['end']['lat']
                end_lng = segment['end']['lng']
                transport = segment['transportMode']
                duration_seconds = segment.get('durationSeconds', 0)
                duration_minutes = round(duration_seconds / 60, 2)
                experience_rating = segment.get('experienceRating', '')
                
                from math import radians, sin, cos, sqrt, atan2
                R = 6371
                
                lat1, lon1 = radians(start_lat), radians(start_lng)
                lat2, lon2 = radians(end_lat), radians(end_lng)
                
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                distance = R * c
                
                user_type = user_data.get('userType', '')
                grade_level = user_data.get('gradeLevel', '')
                department = user_data.get('department', '')
                
                writer.writerow([full_name, route_id, idx+1, start_lat, start_lng, end_lat, end_lng, 
                               transport, f"{distance:.6f}", duration_seconds, duration_minutes, 
                               experience_rating, user_type, grade_level, department])
        
        # Save to database for better persistence
        db_success = save_to_database(route_id, segments, user_data)
        
        # Try to append to Excel file
        try:
            timestamp = datetime.now().isoformat()
            append_route_to_excel(timestamp, route_id, segments, user_data)
        except Exception as e:
            print(f"Warning: Failed to update Excel file: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Route saved to CSV{" and database" if db_success else " (database save failed)"}'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        data = request.get_json()
        
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        vectors_storage[session_id] = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Data saved successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/load/<session_id>', methods=['GET'])
def load_data(session_id):
    try:
        if session_id in vectors_storage:
            return jsonify({
                'success': True,
                'data': vectors_storage[session_id]['data']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    try:
        sessions = []
        for session_id, session_data in vectors_storage.items():
            sessions.append({
                'session_id': session_id,
                'timestamp': session_data['timestamp'],
                'vector_count': len(session_data['data'].get('vectors', []))
            })
        
        return jsonify({
            'success': True,
            'sessions': sessions
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/export/<session_id>', methods=['GET'])
def export_data(session_id):
    try:
        if session_id not in vectors_storage:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        data = vectors_storage[session_id]['data']
        
        csv_lines = ['Route_ID,Segment_ID,Start_Lat,Start_Lng,End_Lat,End_Lng,Transport_Mode,Distance_KM,Duration_Seconds,Duration_Minutes,Experience_Rating,User_Type,Grade_Level,Department']
        
        for vector in data.get('vectors', []):
            route_id = vector['id']
            for idx, segment in enumerate(vector['segments']):
                start_lat = segment['start']['lat']
                start_lng = segment['start']['lng']
                end_lat = segment['end']['lat']
                end_lng = segment['end']['lng']
                transport = segment['transportMode']
                duration_seconds = segment.get('durationSeconds', 0)
                duration_minutes = round(duration_seconds / 60, 2)
                experience_rating = segment.get('experienceRating', '')
                
                from math import radians, sin, cos, sqrt, atan2
                R = 6371
                
                lat1, lon1 = radians(start_lat), radians(start_lng)
                lat2, lon2 = radians(end_lat), radians(end_lng)
                
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                distance = R * c
                
                user_type = vector.get('userData', {}).get('userType', '')
                grade_level = vector.get('userData', {}).get('gradeLevel', '')
                department = vector.get('userData', {}).get('department', '')
                
                csv_lines.append(f"{route_id},{idx+1},{start_lat},{start_lng},{end_lat},{end_lng},{transport},{distance:.6f},{duration_seconds},{duration_minutes},{experience_rating},{user_type},{grade_level},{department}")
        
        csv_content = '\n'.join(csv_lines)
        
        return csv_content, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename={session_id}.csv'
        }
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/export-excel', methods=['GET'])
def export_excel():
    try:
        import pandas as pd
        
        df = None
        
        # First try to get data from database
        try:
            conn = sqlite3.connect(DB_FILE)
            df = pd.read_sql_query('SELECT * FROM routes', conn)
            conn.close()
            print(f"Loaded data from database: {len(df)} records")
        except Exception as e:
            print(f"Could not load from database: {e}")
        
        # If no database data, try CSV file
        if df is None or len(df) == 0:
            if os.path.exists(CSV_FILE):
                df = pd.read_csv(CSV_FILE)
                print(f"Loaded data from CSV: {len(df)} records")
            else:
                return jsonify({'success': False, 'error': 'No data found. Please save a route first.'}), 404
        
        if df is None or len(df) == 0:
            return jsonify({'success': False, 'error': 'No data found. Please save a route first.'}), 404
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Vectors')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='vector_data.xlsx'
        )
        
    except ImportError:
        return jsonify({'success': False, 'error': 'Excel export requires pandas and openpyxl packages. Please contact administrator.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/clear-data', methods=['POST'])
def clear_data():
    try:
        if os.path.exists(EXCEL_FILE):
            os.remove(EXCEL_FILE)

        if os.path.exists(CSV_FILE):
            os.remove(CSV_FILE)
        initialize_csv()

        return jsonify({'success': True, 'message': 'Excel and CSV cleared'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
