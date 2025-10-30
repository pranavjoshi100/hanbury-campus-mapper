from flask import Flask, render_template_string, jsonify, request, send_file
import json
import csv
import os
import sqlite3
from datetime import datetime
import io

app = Flask(__name__)

vectors_storage = {}

CSV_FILE = 'vector_data.csv'
EXCEL_FILE = 'vector_data.xlsx'
DB_FILE = 'campus_data.db'

def init_database():
    """Initialize SQLite database for better data persistence."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
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
            segment_type TEXT NOT NULL,
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
            
            from math import radians, sin, cos, sqrt, atan2
            R = 6371
            lat1, lon1 = radians(start_lat), radians(start_lng)
            lat2, lon2 = radians(end_lat), radians(end_lng)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance = R * c
            
            segment_type = 'stopping' if duration_seconds > 0 or experience_rating > 0 else 'passing'
            
            cursor.execute('''
                INSERT INTO routes (timestamp, route_id, segment_id, start_lat, start_lng, 
                                  end_lat, end_lng, transport_mode, distance_km, duration_seconds, 
                                  duration_minutes, experience_rating, segment_type, user_type, grade_level, 
                                  department, full_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, route_id, idx+1, start_lat, start_lng, end_lat, end_lng,
                  transport, distance, duration_seconds, duration_minutes, experience_rating,
                  segment_type, user_data.get('userType', ''), user_data.get('gradeLevel', ''),
                  user_data.get('department', ''), user_data.get('fullName', '')))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving to database: {e}")
        return False

init_database()

def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Full_Name', 'Route_ID', 'Segment_ID', 'Start_Lat', 'Start_Lng', 'End_Lat', 'End_Lng', 'Transport_Mode', 'Distance_KM', 'Duration_Seconds', 'Duration_Minutes', 'Experience_Rating', 'Segment_Type', 'User_Type', 'Grade_Level', 'Department'])

initialize_csv()

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
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f5f5f5;
            overflow: hidden;
        }
        
        /* Header */
        .header {
            background: white;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: relative;
            z-index: 100;
        }
        
        .logo {
            width: 50px;
            height: 50px;
            background: #E4351A;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 28px;
            font-weight: bold;
        }
        
        .header-nav {
            display: flex;
            gap: 32px;
            align-items: center;
            flex: 1;
            justify-content: center;
        }
        
        .nav-btn {
            background: none;
            border: none;
            font-size: 16px;
            cursor: pointer;
            color: #666;
            transition: color 0.2s;
        }
        
        .nav-btn:hover {
            color: #E4351A;
        }
        
        .nav-btn.active {
            color: #E4351A;
            font-weight: 500;
        }
        
        .help-btn {
            color: #E4351A;
            font-size: 16px;
        }
        
        /* Map Container */
        .map-container {
            position: relative;
            height: calc(100vh - 74px);
            width: 100%;
        }
        
        #map {
            width: 100%;
            height: 100%;
        }
        
        /* Search Bar */
        .search-bar {
            position: absolute;
            top: 20px;
            left: 20px;
            z-index: 1000;
            background: white;
            border-radius: 24px;
            padding: 12px 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            display: flex;
            align-items: center;
            gap: 12px;
            width: 300px;
        }
        
        .search-bar i {
            color: #999;
        }
        
        .search-bar input {
            border: none;
            outline: none;
            flex: 1;
            font-size: 14px;
        }
        
        .search-bar input::placeholder {
            color: #ccc;
        }
        
        /* Add Stop Button */
        .add-stop-btn {
            position: absolute;
            top: 80px;
            left: 20px;
            z-index: 1000;
            background: #E4351A;
            color: white;
            border: none;
            border-radius: 24px;
            padding: 12px 24px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            box-shadow: 0 2px 8px rgba(228, 53, 26, 0.3);
            display: none;
            align-items: center;
            gap: 8px;
        }
        
        .add-stop-btn.active {
            display: flex;
        }
        
        /* Current Path Sidebar */
        .sidebar {
            position: absolute;
            bottom: 20px;
            right: 20px;
            width: 400px;
            max-height: 60vh;
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            overflow: hidden;
            z-index: 1000;
            display: none;
        }
        
        .sidebar.active {
            display: block;
        }
        
        .sidebar-header {
            padding: 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .sidebar-title {
            font-size: 20px;
            font-weight: 600;
        }
        
        .sidebar-date {
            font-size: 14px;
            color: #999;
        }
        
        .edit-btn {
            background: none;
            border: none;
            color: #E4351A;
            font-size: 18px;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        
        .edit-btn:hover {
            opacity: 0.7;
        }
        
        .sidebar-content {
            overflow-y: auto;
            max-height: calc(60vh - 80px);
            padding: 20px;
        }
        
        .segment-item {
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 12px;
            background: #f9f9f9;
            border-radius: 12px;
            margin-bottom: 12px;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .segment-item:hover {
            background: #f0f0f0;
        }
        
        .segment-item.editing {
            background: #fff5f3;
            border: 2px solid #E4351A;
        }
        
        .segment-number {
            width: 32px;
            height: 32px;
            background: #E4351A;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 14px;
            flex-shrink: 0;
        }
        
        .segment-details {
            flex: 1;
        }
        
        .segment-transport {
            font-size: 14px;
            color: #333;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .segment-transport i {
            font-size: 18px;
        }
        
        .segment-meta {
            display: flex;
            gap: 16px;
            margin-top: 4px;
            font-size: 13px;
            color: #666;
        }
        
        .segment-stars {
            color: #FFC107;
        }
        
        /* Modal Overlay */
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
        
        /* Welcome Modal */
        .welcome-modal {
            background: white;
            border-radius: 24px;
            padding: 48px;
            max-width: 600px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .welcome-title {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
            text-align: center;
        }
        
        .welcome-subtitle {
            font-size: 16px;
            color: #666;
            margin-bottom: 32px;
            text-align: center;
        }
        
        .form-section {
            margin-bottom: 32px;
        }
        
        .form-label {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
            display: block;
        }
        
        .button-group {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        .option-btn {
            flex: 1;
            min-width: 120px;
            padding: 16px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            background: white;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .option-btn:hover {
            border-color: #E4351A;
            background: #fff5f3;
        }
        
        .option-btn.active {
            border-color: #E4351A;
            background: #E4351A;
            color: white;
        }
        
        .text-input {
            width: 100%;
            padding: 16px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 14px;
            transition: border-color 0.2s;
        }
        
        .text-input:focus {
            outline: none;
            border-color: #E4351A;
        }
        
        .primary-btn {
            width: 100%;
            padding: 18px;
            background: #E4351A;
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .primary-btn:hover {
            background: #c72e16;
        }
        
        .primary-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        
        /* Error Message */
        .error-message {
            background: #fee;
            color: #c33;
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 12px;
            font-size: 14px;
            display: none;
            border-left: 4px solid #c33;
        }
        
        .error-message.show {
            display: block;
        }
        
        .success-message {
            background: #efe;
            color: #3c3;
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 12px;
            font-size: 14px;
            display: none;
            border-left: 4px solid #3c3;
        }
        
        .success-message.show {
            display: block;
        }
        
        /* Transport Selector Modal */
        .transport-modal {
            background: white;
            border-radius: 24px;
            padding: 32px;
            width: 500px;
            max-width: 90%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-height: 90vh;
            overflow-y: auto;
        }
        
        .transport-modal h2 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 24px;
            text-align: center;
        }
        
        .transport-options {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 24px;
        }
        
        .transport-option {
            aspect-ratio: 1;
            border: 2px solid #e0e0e0;
            border-radius: 16px;
            background: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            transition: all 0.2s;
        }
        
        .transport-option:hover {
            border-color: #E4351A;
            background: #fff5f3;
        }
        
        .transport-option.active {
            border-color: #E4351A;
            background: #E4351A;
            color: white;
        }
        
        .duration-section {
            margin: 24px 0;
        }
        
        .section-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
        }
        
        .duration-inputs {
            display: flex;
            gap: 16px;
        }
        
        .duration-input {
            flex: 1;
            padding: 16px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 14px;
            text-align: center;
        }
        
        .duration-input:focus {
            outline: none;
            border-color: #E4351A;
        }
        
        .rating-section {
            margin: 24px 0;
        }
        
        .star-rating {
            display: flex;
            gap: 8px;
            justify-content: center;
        }
        
        .star {
            font-size: 40px;
            color: #ddd;
            cursor: pointer;
            transition: color 0.2s;
        }
        
        .star:hover,
        .star.active {
            color: #FFC107;
        }
        
        /* Help Modal */
        .help-modal {
            background: white;
            border-radius: 24px;
            padding: 48px;
            max-width: 700px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .help-title {
            background: #E4351A;
            color: white;
            padding: 12px 32px;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 600;
            text-align: center;
            margin-bottom: 32px;
            display: inline-block;
        }
        
        .help-content {
            font-size: 18px;
            line-height: 1.8;
        }
        
        .help-content ol {
            padding-left: 24px;
        }
        
        .help-content li {
            margin-bottom: 12px;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .sidebar {
                width: calc(100% - 40px);
                max-height: 50vh;
            }
            
            .transport-options {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .header-nav {
                gap: 16px;
            }
            
            .nav-btn {
                font-size: 14px;
            }
        }
    </style>
</head>
<body>
    <!-- Welcome Modal -->
    <div id="welcomeModal" class="modal-overlay active">
        <div class="welcome-modal">
            <h1 class="welcome-title">Welcome</h1>
            <p class="welcome-subtitle">Tell us about yourself</p>
            
            <div class="form-section">
                <label class="form-label">I am a:</label>
                <div class="button-group">
                    <button class="option-btn" data-value="student">Student</button>
                    <button class="option-btn" data-value="faculty">Staff/Faculty</button>
                    <button class="option-btn" data-value="visitor">Visitor</button>
                    <button class="option-btn" data-value="other">Other</button>
                </div>
            </div>
            
            <div class="form-section" id="gradeLevelSection" style="display: none;">
                <label class="form-label">Grade Level:</label>
                <input type="text" class="text-input" id="gradeLevel" placeholder="e.g. Freshman, Sophomore">
            </div>
            
            <div class="form-section">
                <label class="form-label">Department/School (Optional):</label>
                <input type="text" class="text-input" id="department" placeholder="e.g. Engineering, Business">
            </div>
            
            <div class="error-message" id="welcomeError"></div>
            
            <button class="primary-btn" id="startBtn" disabled>How to Draw:</button>
        </div>
    </div>

    <!-- Transport Selector Modal -->
    <div id="transportModal" class="modal-overlay">
        <div class="transport-modal">
            <h2>Select Mode of Transport</h2>
            
            <div class="transport-options">
                <div class="transport-option" data-mode="driving">
                    <i class="fas fa-car"></i>
                </div>
                <div class="transport-option" data-mode="transit">
                    <i class="fas fa-bus"></i>
                </div>
                <div class="transport-option active" data-mode="biking">
                    <i class="fas fa-bicycle"></i>
                </div>
                <div class="transport-option" data-mode="walking">
                    <i class="fas fa-person-walking"></i>
                </div>
            </div>
            
            <div class="duration-section">
                <div class="section-title">Duration</div>
                <div class="duration-inputs">
                    <input type="number" class="duration-input" id="hours" placeholder="Hours" min="0">
                    <input type="number" class="duration-input" id="minutes" placeholder="Minutes" min="0">
                </div>
            </div>
            
            <div class="rating-section">
                <div class="section-title">Rating</div>
                <div class="star-rating" id="starRating">
                    <span class="star active" data-value="1">★</span>
                    <span class="star active" data-value="2">★</span>
                    <span class="star" data-value="3">★</span>
                    <span class="star" data-value="4">★</span>
                    <span class="star" data-value="5">★</span>
                </div>
            </div>
            
            <div class="error-message" id="transportError"></div>
            
            <button class="primary-btn" id="confirmTransport">Confirm</button>
        </div>
    </div>

    <!-- Help Modal -->
    <div id="helpModal" class="modal-overlay">
        <div class="help-modal">
            <div class="help-title">How to Draw:</div>
            <div class="help-content">
                <ol>
                    <li>Click the Start Drawing Button.</li>
                    <li>Click your points on map.</li>
                    <li>Select your mode of transport for each segment.</li>
                    <li>Click Finish Line (or double-click) to complete.</li>
                    <li>Click Save when done to save to server.</li>
                </ol>
            </div>
        </div>
    </div>

    <!-- Header -->
    <div class="header">
        <div class="logo">H</div>
        <div class="header-nav">
            <button class="nav-btn" id="cancelNav">Cancel</button>
            <button class="nav-btn active" id="startDrawingNav">Start Drawing</button>
            <button class="nav-btn" id="saveNav">Save to Server</button>
            <button class="nav-btn" id="clearNav">Clear All</button>
            <button class="nav-btn" id="finishNav">Finish Line</button>
        </div>
        <button class="nav-btn help-btn" id="helpNav">Help</button>
    </div>

    <!-- Map Container -->
    <div class="map-container">
        <div id="map"></div>
        
        <!-- Search Bar -->
        <div class="search-bar">
            <i class="fas fa-search"></i>
            <input type="text" placeholder="Search stopping points">
        </div>
        
        <!-- Add Stop Button -->
        <button class="add-stop-btn" id="addStopBtn">
            <i class="fas fa-plus"></i>
            Add stop
        </button>
        
        <!-- Current Path Sidebar -->
        <div class="sidebar" id="pathSidebar">
            <div class="sidebar-header">
                <div>
                    <div class="sidebar-title">Current Path</div>
                    <div class="sidebar-date" id="pathDate">10/22/2025</div>
                </div>
                <button class="edit-btn" id="editSegmentsBtn">
                    <i class="fas fa-pen"></i>
                </button>
            </div>
            <div class="sidebar-content" id="segmentList">
                <!-- Segments will be added here dynamically -->
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
    <script>
        // Initialize map with image overlay
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
        
        // State
        let userData = {
            userType: '',
            gradeLevel: '',
            department: ''
        };
        let isDrawing = false;
        let currentPoints = [];
        let currentSegments = [];
        let currentPolylines = [];
        let vectors = new Map();
        let vectorCounter = 0;
        let selectedRating = 0;
        let selectedTransport = 'biking';
        let editMode = false;
        let editingSegmentIndex = -1;
        
        // Utility function to show error messages
        function showError(elementId, message, duration = 4000) {
            const errorEl = document.getElementById(elementId);
            errorEl.textContent = message;
            errorEl.classList.add('show');
            setTimeout(() => {
                errorEl.classList.remove('show');
            }, duration);
        }
        
        function showSuccess(message, duration = 3000) {
            const toast = document.createElement('div');
            toast.className = 'success-message show';
            toast.textContent = message;
            toast.style.position = 'fixed';
            toast.style.top = '20px';
            toast.style.right = '20px';
            toast.style.zIndex = '10000';
            toast.style.minWidth = '300px';
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }
        
        // Elements
        const welcomeModal = document.getElementById('welcomeModal');
        const transportModal = document.getElementById('transportModal');
        const helpModal = document.getElementById('helpModal');
        const pathSidebar = document.getElementById('pathSidebar');
        const segmentList = document.getElementById('segmentList');
        const addStopBtn = document.getElementById('addStopBtn');
        const editSegmentsBtn = document.getElementById('editSegmentsBtn');
        
        // Edit Segments Button
        editSegmentsBtn.addEventListener('click', () => {
            if (currentSegments.length === 0) {
                showError('transportError', 'No segments to edit. Start drawing first!');
                return;
            }
            
            editMode = !editMode;
            if (editMode) {
                editSegmentsBtn.style.color = '#E4351A';
                editSegmentsBtn.style.opacity = '1';
                showSuccess('Edit mode active - Click any segment to edit it');
            } else {
                editSegmentsBtn.style.color = '';
                editSegmentsBtn.style.opacity = '';
                editingSegmentIndex = -1;
                updateSidebar();
            }
        });
        
        // Welcome Modal - User Type Selection
        document.querySelectorAll('.welcome-modal .option-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.welcome-modal .option-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                userData.userType = this.dataset.value;
                
                const gradeLevelSection = document.getElementById('gradeLevelSection');
                if (userData.userType === 'student') {
                    gradeLevelSection.style.display = 'block';
                } else {
                    gradeLevelSection.style.display = 'none';
                }
                
                document.getElementById('startBtn').disabled = false;
            });
        });
        
        document.getElementById('startBtn').addEventListener('click', () => {
            userData.gradeLevel = document.getElementById('gradeLevel').value;
            userData.department = document.getElementById('department').value;
            
            // Validate student must have grade level
            if (userData.userType === 'student' && !userData.gradeLevel.trim()) {
                showError('welcomeError', 'Students must enter a grade level');
                return;
            }
            
            welcomeModal.classList.remove('active');
            helpModal.classList.add('active');
        });
        
        // Help Modal - Close on click
        helpModal.addEventListener('click', (e) => {
            if (e.target === helpModal) {
                helpModal.classList.remove('active');
            }
        });
        
        document.getElementById('helpNav').addEventListener('click', () => {
            helpModal.classList.add('active');
        });
        
        // Transport Modal - Transport Selection
        document.querySelectorAll('.transport-option').forEach(option => {
            option.addEventListener('click', function() {
                document.querySelectorAll('.transport-option').forEach(o => o.classList.remove('active'));
                this.classList.add('active');
                selectedTransport = this.dataset.mode;
            });
        });
        
        // Star Rating
        document.querySelectorAll('.star').forEach(star => {
            star.addEventListener('click', function() {
                selectedRating = parseInt(this.dataset.value);
                document.querySelectorAll('.star').forEach((s, idx) => {
                    if (idx < selectedRating) {
                        s.classList.add('active');
                    } else {
                        s.classList.remove('active');
                    }
                });
            });
        });
        
        // Navigation
        document.getElementById('startDrawingNav').addEventListener('click', () => {
            isDrawing = !isDrawing;
            if (isDrawing) {
                addStopBtn.classList.add('active');
                pathSidebar.classList.add('active');
                document.getElementById('startDrawingNav').textContent = 'Stop Drawing';
            } else {
                addStopBtn.classList.remove('active');
                document.getElementById('startDrawingNav').textContent = 'Start Drawing';
            }
        });
        
        document.getElementById('finishNav').addEventListener('click', () => {
            if (currentSegments.length > 0) {
                finishRoute();
            }
        });
        
        document.getElementById('clearNav').addEventListener('click', () => {
            if (confirm('Clear all routes?')) {
                currentPoints = [];
                currentSegments = [];
                currentPolylines.forEach(p => map.removeLayer(p));
                currentPolylines = [];
                segmentList.innerHTML = '';
                pathSidebar.classList.remove('active');
            }
        });
        
        document.getElementById('cancelNav').addEventListener('click', () => {
            currentPoints = [];
            currentSegments = [];
            currentPolylines.forEach(p => map.removeLayer(p));
            currentPolylines = [];
            segmentList.innerHTML = '';
            isDrawing = false;
            addStopBtn.classList.remove('active');
            pathSidebar.classList.remove('active');
            document.getElementById('startDrawingNav').textContent = 'Start Drawing';
        });
        
        // Map Click Handler
        map.on('click', function(e) {
            if (!isDrawing) {
                showError('transportError', 'Click "Start Drawing" first to begin mapping your route');
                return;
            }
            
            const latlng = [e.latlng.lat, e.latlng.lng];
            currentPoints.push(latlng);
            
            if (currentPoints.length > 1) {
                transportModal.classList.add('active');
            }
            
            updateMap();
        });
        
        // Confirm Transport
        document.getElementById('confirmTransport').addEventListener('click', () => {
            const hours = parseInt(document.getElementById('hours').value) || 0;
            const minutes = parseInt(document.getElementById('minutes').value) || 0;
            const durationSeconds = (hours * 3600) + (minutes * 60);
            
            // Validation
            if (selectedRating === 0) {
                showError('transportError', 'Please select a star rating (1-5 stars)');
                return;
            }
            
            if (hours === 0 && minutes === 0) {
                showError('transportError', 'Please enter a duration (time spent at this location)');
                return;
            }
            
            if (editingSegmentIndex >= 0) {
                // Edit existing segment
                currentSegments[editingSegmentIndex].transportMode = selectedTransport;
                currentSegments[editingSegmentIndex].durationSeconds = durationSeconds;
                currentSegments[editingSegmentIndex].experienceRating = selectedRating;
                editingSegmentIndex = -1;
                editMode = false;
                editSegmentsBtn.style.color = '';
                editSegmentsBtn.style.opacity = '';
                showSuccess('Segment updated successfully!');
            } else {
                // Add new segment
                const segment = {
                    start: currentPoints[currentPoints.length - 2],
                    end: currentPoints[currentPoints.length - 1],
                    transportMode: selectedTransport,
                    durationSeconds: durationSeconds,
                    experienceRating: selectedRating
                };
                
                currentSegments.push(segment);
            }
            
            // Reset inputs
            document.getElementById('hours').value = '';
            document.getElementById('minutes').value = '';
            selectedRating = 0;
            document.querySelectorAll('.star').forEach(s => s.classList.remove('active'));
            
            transportModal.classList.remove('active');
            updateMap();
            updateSidebar();
        });
        
        function updateMap() {
            // Clear existing polylines
            currentPolylines.forEach(p => map.removeLayer(p));
            currentPolylines = [];
            
            // Draw segments
            currentSegments.forEach((seg, idx) => {
                const color = getTransportColor(seg.transportMode);
                const line = L.polyline([seg.start, seg.end], {
                    color: color,
                    weight: 4,
                    opacity: 0.8
                }).addTo(map);
                currentPolylines.push(line);
            });
            
            // Draw markers
            currentPoints.forEach((point, idx) => {
                const marker = L.marker(point, {
                    icon: L.divIcon({
                        className: 'custom-marker',
                        html: `<div style="width: 32px; height: 32px; background: #E4351A; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; border: 3px solid white; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">${idx + 1}</div>`,
                        iconSize: [32, 32]
                    })
                }).addTo(map);
                currentPolylines.push(marker);
            });
        }
        
        function updateSidebar() {
            segmentList.innerHTML = '';
            
            currentSegments.forEach((seg, idx) => {
                const transportIcons = {
                    'walking': '<i class="fas fa-person-walking"></i>',
                    'biking': '<i class="fas fa-bicycle"></i>',
                    'driving': '<i class="fas fa-car"></i>',
                    'transit': '<i class="fas fa-bus"></i>',
                    'other': '<i class="fas fa-walking"></i>'
                };
                
                const transportNames = {
                    'walking': 'Walking',
                    'biking': 'Biking',
                    'driving': 'Driving',
                    'transit': 'Transit',
                    'other': 'Other'
                };
                
                const hours = Math.floor(seg.durationSeconds / 3600);
                const minutes = Math.floor((seg.durationSeconds % 3600) / 60);
                const timeStr = hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
                
                const stars = '★'.repeat(seg.experienceRating);
                
                const segmentEl = document.createElement('div');
                segmentEl.className = 'segment-item';
                if (editingSegmentIndex === idx) {
                    segmentEl.classList.add('editing');
                }
                segmentEl.innerHTML = `
                    <div class="segment-number">${idx + 1}</div>
                    <div class="segment-details">
                        <div class="segment-transport">
                            ${transportIcons[seg.transportMode]}
                            ${transportNames[seg.transportMode]}
                        </div>
                        <div class="segment-meta">
                            <span>${timeStr}</span>
                            <span class="segment-stars">${stars}</span>
                        </div>
                    </div>
                `;
                
                // Add click handler for editing
                segmentEl.addEventListener('click', () => {
                    if (editMode) {
                        editingSegmentIndex = idx;
                        
                        // Pre-fill the modal with current values
                        selectedTransport = seg.transportMode;
                        document.querySelectorAll('.transport-option').forEach(opt => {
                            if (opt.dataset.mode === selectedTransport) {
                                opt.classList.add('active');
                            } else {
                                opt.classList.remove('active');
                            }
                        });
                        
                        const hours = Math.floor(seg.durationSeconds / 3600);
                        const minutes = Math.floor((seg.durationSeconds % 3600) / 60);
                        document.getElementById('hours').value = hours;
                        document.getElementById('minutes').value = minutes;
                        
                        selectedRating = seg.experienceRating;
                        document.querySelectorAll('.star').forEach((s, i) => {
                            if (i < selectedRating) {
                                s.classList.add('active');
                            } else {
                                s.classList.remove('active');
                            }
                        });
                        
                        transportModal.classList.add('active');
                        updateSidebar(); // Refresh to show editing state
                    }
                });
                
                segmentList.appendChild(segmentEl);
            });
            
            // Update date
            const today = new Date();
            document.getElementById('pathDate').textContent = `${today.getMonth() + 1}/${today.getDate()}/${today.getFullYear()}`;
        }
        
        function getTransportColor(mode) {
            const colors = {
                'walking': '#28a745',
                'biking': '#ffc107',
                'driving': '#dc3545',
                'transit': '#17a2b8',
                'other': '#6c757d'
            };
            return colors[mode] || '#667eea';
        }
        
        function finishRoute() {
            if (currentSegments.length === 0) {
                showError('transportError', 'No route to save. Draw at least one segment first!');
                return;
            }
            
            vectorCounter++;
            
            // Save to backend
            saveRouteToBackend(vectorCounter, currentSegments);
            
            // Reset
            currentPoints = [];
            currentSegments = [];
            currentPolylines.forEach(p => map.removeLayer(p));
            currentPolylines = [];
            segmentList.innerHTML = '';
            isDrawing = false;
            addStopBtn.classList.remove('active');
            document.getElementById('startDrawingNav').textContent = 'Start Drawing';
            
            showSuccess('Route saved successfully! 🎉');
        }
        
        async function saveRouteToBackend(routeId, segments) {
            try {
                const response = await fetch('/api/save-csv', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        routeId: routeId,
                        segments: segments.map(seg => ({
                            start: {lat: seg.start[0], lng: seg.start[1]},
                            end: {lat: seg.end[0], lng: seg.end[1]},
                            transportMode: seg.transportMode,
                            durationSeconds: seg.durationSeconds,
                            experienceRating: seg.experienceRating
                        })),
                        userData: userData
                    })
                });
                
                const result = await response.json();
                if (!result.success) {
                    showError('transportError', 'Failed to save route: ' + (result.error || 'Unknown error'));
                    console.error('Error saving:', result.error);
                }
            } catch (error) {
                showError('transportError', 'Network error - could not save route. Please check your connection.');
                console.error('Error saving:', error);
            }
        }
        
        document.getElementById('saveNav').addEventListener('click', async () => {
            if (currentSegments.length === 0) {
                showError('transportError', 'No route to save. Draw some segments first!');
                return;
            }
            
            finishRoute();
        });
        
        document.getElementById('clearNav').addEventListener('click', () => {
            if (currentSegments.length === 0) {
                showError('transportError', 'Nothing to clear - no route in progress');
                return;
            }
            
            if (confirm('Clear all routes? This cannot be undone.')) {
                currentPoints = [];
                currentSegments = [];
                currentPolylines.forEach(p => map.removeLayer(p));
                currentPolylines = [];
                segmentList.innerHTML = '';
                pathSidebar.classList.remove('active');
                showSuccess('Route cleared');
            }
        });
        
        window.addEventListener('resize', () => {
            map.invalidateSize();
        });
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
                
                segment_type = 'stopping' if duration_seconds > 0 or experience_rating > 0 else 'passing'
                
                writer.writerow([full_name, route_id, idx+1, start_lat, start_lng, end_lat, end_lng, 
                               transport, f"{distance:.6f}", duration_seconds, duration_minutes, 
                               experience_rating, segment_type, user_type, grade_level, department])
        
        save_to_database(route_id, segments, user_data)
        
        return jsonify({
            'success': True,
            'message': 'Route saved successfully'
        })
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
        
        try:
            conn = sqlite3.connect(DB_FILE)
            df = pd.read_sql_query('SELECT * FROM routes', conn)
            conn.close()
        except Exception as e:
            print(f"Could not load from database: {e}")
        
        if df is None or len(df) == 0:
            if os.path.exists(CSV_FILE):
                df = pd.read_csv(CSV_FILE)
            else:
                return jsonify({'success': False, 'error': 'No data found'}), 404
        
        if df is None or len(df) == 0:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
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
        return jsonify({'success': False, 'error': 'pandas/openpyxl not available'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
