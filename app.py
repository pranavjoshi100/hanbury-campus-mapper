from flask import Flask, render_template_string, jsonify, request
import json
import csv
import os
from datetime import datetime

app = Flask(__name__)

# Store vectors in memory (in production, use a database)
vectors_storage = {}

# Create a CSV file if it doesn't exist
CSV_FILE = 'vector_data.csv'

def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Route_ID', 'Segment_ID', 'Start_Y', 'Start_X', 'End_Y', 'End_X', 'Transport_Mode', 'Distance_Pixels', 'Duration_Seconds', 'Duration_Minutes', 'User_Type', 'Grade_Level', 'Department'])

initialize_csv()

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
            .transport-selector {
                min-width: 90%;
                width: 90vw;
                padding: 12px 15px;
                bottom: 10px;
                left: 5vw;
                transform: none;
            }
            .transport-selector h3 {
                font-size: 14px;
                margin-bottom: 8px;
            }
            .segment-info {
                font-size: 11px;
            }
            .time-inputs {
                gap: 8px;
            }
            .time-input input {
                padding: 6px;
                font-size: 13px;
            }
        }
        @media (max-width: 480px) {
            body {
                padding: 8px;
            }
            .header {
                padding: 15px;
            }
            .header h1 {
                font-size: 18px;
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
            .instructions {
                font-size: 12px;
                padding: 12px;
                margin-bottom: 15px;
            }
            .stats {
                padding: 12px;
                margin-bottom: 15px;
            }
            .stat-item {
                font-size: 12px;
                margin-bottom: 4px;
            }
            .transport-selector {
                min-width: 95%;
                width: 95vw;
                padding: 10px 12px;
                bottom: 5px;
                left: 2.5vw;
            }
            .transport-selector h3 {
                font-size: 13px;
                margin: 0 0 8px 0;
            }
            .transport-selector-content {
                gap: 8px;
            }
            .transport-selector select {
                font-size: 13px;
                padding: 6px;
            }
            .transport-selector button {
                padding: 6px 12px;
                font-size: 12px;
            }
            .time-input-group {
                margin-top: 10px;
                padding-top: 10px;
            }
            .time-input span {
                font-size: 10px;
            }
            .vector-item {
                padding: 12px;
                margin-bottom: 8px;
            }
            .vector-title {
                font-size: 14px;
            }
            .delete-btn {
                padding: 4px 8px;
                font-size: 11px;
            }
            .modal {
                padding: 20px;
                max-width: 90%;
            }
            .modal h2 {
                font-size: 18px;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group input,
            .form-group select {
                font-size: 16px;
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
    </style>
</head>
<body>
    <div id="userInfoModal" class="modal-overlay active">
        <div class="modal">
            <h2>Welcome! Please provide your information</h2>
            <form id="userInfoForm">
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
            <div style="display: flex;">
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
            <div id="modeIndicator" class="mode-indicator">Click "Start Drawing" to begin</div>
        </div>
        
        <div class="content">
            <div id="map"></div>
            <div class="sidebar">
                <div class="instructions">
                    <strong>How to draw routes:</strong><br>
                    1. Click "Start Drawing" button<br>
                    2. Click points on the campus map<br>
                    3. Select transport mode for each segment<br>
                    4. Click "Finish Line" or double-click to complete<br>
                    5. Click "Save to Server" when done
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
                        <span class="stat-label">Current Points:</span>
                        <span class="stat-value" id="currentPoints">0</span>
                    </div>
                </div>
                
                <div id="vectorList"></div>
            </div>
        </div>
        
        <div id="transportSelector" class="transport-selector">
            <h3>Transportation mode for this segment?</h3>
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
                <label>How long did this segment take?</label>
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
            <div style="margin-top: 15px;">
                <button id="confirmSegmentBtn" style="width: 100%;">Confirm Segment</button>
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
    <script>
        // Image overlay setup with simple CRS (pixel-based coordinates)
        const imageBounds = [[0, 0], [1536, 2048]]; // [height, width] in pixels
        
        const map = L.map('map', {
            crs: L.CRS.Simple,
            minZoom: -2,
            maxZoom: 2,
            zoomControl: false,
            attributionControl: false
        });
        
        // Add the campus map image - place your image in the static folder
        const imageUrl = '/static/campus-map.jpg';
        const imageOverlay = L.imageOverlay(imageUrl, imageBounds).addTo(map);
        
        // Fit map to image bounds
        map.fitBounds(imageOverlay.getBounds());
        
        let userData = {
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
        
        const drawBtn = document.getElementById('drawBtn');
        const finishBtn = document.getElementById('finishBtn');
        const cancelBtn = document.getElementById('cancelBtn');
        const clearBtn = document.getElementById('clearBtn');
        const saveBtn = document.getElementById('saveBtn');
        const modeIndicator = document.getElementById('modeIndicator');
        const mapElement = document.getElementById('map');
        const userInfoModal = document.getElementById('userInfoModal');
        const transportSelector = document.getElementById('transportSelector');
        const currentTransportModeSelect = document.getElementById('currentTransportMode');
        const confirmSegmentBtn = document.getElementById('confirmSegmentBtn');
        const segmentInfo = document.getElementById('segmentInfo');
        const segmentMinutesInput = document.getElementById('segmentMinutes');
        const segmentSecondsInput = document.getElementById('segmentSeconds');
        
        confirmSegmentBtn.addEventListener('click', function() {
            if (!pendingSegment) return;
            
            const transportMode = currentTransportModeSelect.value;
            const minutes = parseInt(segmentMinutesInput.value) || 0;
            const seconds = parseInt(segmentSecondsInput.value) || 0;
            const totalSeconds = minutes * 60 + seconds;
            
            if (totalSeconds <= 0) {
                alert('Please enter a valid time duration (greater than 0)');
                return;
            }
            
            pendingSegment.transportMode = transportMode;
            pendingSegment.durationSeconds = totalSeconds;
            currentSegments.push(pendingSegment);
            pendingSegment = null;
            
            segmentMinutesInput.value = '0';
            segmentSecondsInput.value = '0';
            
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
            
            document.getElementById('displayUserType').textContent = userTypeMap[userData.userType] || '-';
            
            const gradeLevelContainer = document.getElementById('displayGradeLevelContainer');
            const gradeLevelDisplay = document.getElementById('displayGradeLevel');
            if (userData.gradeLevel) {
                gradeLevelContainer.style.display = 'block';
                gradeLevelDisplay.textContent = userData.gradeLevel;
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
        
        function calculateDistance(point1, point2) {
            const dx = point2[0] - point1[0];
            const dy = point2[1] - point1[1];
            return Math.sqrt(dx * dx + dy * dy);
        }
        
        function updateStats() {
            const vectorCount = vectors.size;
            let totalSegments = 0;
            
            vectors.forEach(vector => {
                totalSegments += vector.segments.length;
            });
            
            document.getElementById('vectorCount').textContent = vectorCount;
            document.getElementById('segmentCount').textContent = totalSegments;
            document.getElementById('currentPoints').textContent = currentPoints.length;
        }
        
        function updateUI() {
            if (isDrawing) {
                drawBtn.textContent = 'Drawing...';
                drawBtn.classList.add('active');
                finishBtn.disabled = currentSegments.length === 0;
                cancelBtn.disabled = false;
                
                if (pendingSegment) {
                    modeIndicator.textContent = 'Waiting for transport mode...';
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
        
        function addVectorToSidebar(id, segments) {
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
                        <span class="transport-badge transport-${seg.transportMode}">${transportLabels[seg.transportMode]}</span>
                        <span style="font-size: 11px; color: #666; margin-left: 5px;">${segLength.toFixed(1)} px</span>
                        <span class="time-badge">${segTimeStr}</span>
                    </div>
                `;
            });
            
            vectorItem.innerHTML = `
                <div class="vector-header">
                    <div class="vector-title">Route #${id}</div>
                    <button class="delete-btn" onclick="deleteVector(${id})">Delete</button>
                </div>
                <div class="vector-info">${segments.length} segments | ${totalTimeStr}</div>
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
                            start: {y: seg.start[0], x: seg.start[1]},
                            end: {y: seg.end[0], x: seg.end[1]},
                            transportMode: seg.transportMode,
                            durationSeconds: seg.durationSeconds
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
                alert('Please confirm the transportation mode before finishing.');
                return;
            }
            
            vectorCounter++;
            
            const finalSegments = [...currentSegments];
            
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
                        ${calculateDistance(seg.start, seg.end).toFixed(1)} pixels
                    </div>
                `);
                
                finalLayers.push(polyline);
            });
            
            vectors.set(vectorCounter, {
                layers: finalLayers,
                segments: finalSegments,
                userData: {...userData}
            });
            
            addVectorToSidebar(vectorCounter, finalSegments);
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
                        start: {y: seg.start[0], x: seg.start[1]},
                        end: {y: seg.end[0], x: seg.end[1]},
                        transportMode: seg.transportMode,
                        durationSeconds: seg.durationSeconds
                    })),
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
                    alert('Data saved successfully! Session ID: ' + result.session_id);
                } else {
                    alert('Error saving data: ' + result.error);
                }
            } catch (error) {
                alert('Error saving data: ' + error.message);
            }
        }
        
        function editUserInfo() {
            document.getElementById('userType').value = userData.userType;
            document.getElementById('gradeLevel').value = userData.gradeLevel;
            document.getElementById('department').value = userData.department;
            
            if (userData.userType === 'student') {
                document.getElementById('gradeLevelGroup').style.display = 'block';
            }
            
            userInfoModal.classList.add('active');
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
        
        map.on('click', function(e) {
            if (!isDrawing) return;
            
            if (pendingSegment) {
                alert('Please select a transportation mode for the current segment before adding another point.');
                return;
            }
            
            const latlng = [e.latlng.lat, e.latlng.lng];
            
            if (currentPoints.length >= 1) {
                pendingSegment = {
                    start: currentPoints[currentPoints.length - 1],
                    end: latlng,
                    transportMode: null
                };
                
                const distance = calculateDistance(pendingSegment.start, pendingSegment.end);
                segmentInfo.textContent = `Segment ${currentSegments.length + 1}: ${distance.toFixed(1)} pixels`;
                transportSelector.classList.add('active');
                currentTransportModeSelect.value = 'walking';
                segmentMinutesInput.value = '0';
                segmentSecondsInput.value = '0';
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
            const currentPos = [e.latlng.lat, e.latlng.lng];
            tempLine = L.polyline([lastPoint, currentPos], {
                color: '#999999',
                weight: 2,
                opacity: 0.3,
                dashArray: '5, 5'
            }).addTo(map);
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
        
        timestamp = datetime.now().isoformat()
        
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            
            for idx, segment in enumerate(segments):
                start_y = segment['start']['y']
                start_x = segment['start']['x']
                end_y = segment['end']['y']
                end_x = segment['end']['x']
                transport = segment['transportMode']
                duration_seconds = segment.get('durationSeconds', 0)
                duration_minutes = round(duration_seconds / 60, 2)
                
                # Calculate pixel distance
                dx = end_x - start_x
                dy = end_y - start_y
                distance = (dx * dx + dy * dy) ** 0.5
                
                user_type = user_data.get('userType', '')
                grade_level = user_data.get('gradeLevel', '')
                department = user_data.get('department', '')
                
                writer.writerow([timestamp, route_id, idx+1, start_y, start_x, end_y, end_x, 
                               transport, f"{distance:.2f}", duration_seconds, duration_minutes, 
                               user_type, grade_level, department])
        
        return jsonify({
            'success': True,
            'message': 'Route saved to CSV'
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
                'route_count': len(session_data['data'].get('vectors', []))
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
        
        csv_lines = ['Route_ID,Segment_ID,Start_Y,Start_X,End_Y,End_X,Transport_Mode,Distance_Pixels,Duration_Seconds,Duration_Minutes,User_Type,Grade_Level,Department']
        
        for vector in data.get('vectors', []):
            route_id = vector['id']
            for idx, segment in enumerate(vector['segments']):
                start_y = segment['start']['y']
                start_x = segment['start']['x']
                end_y = segment['end']['y']
                end_x = segment['end']['x']
                transport = segment['transportMode']
                duration_seconds = segment.get('durationSeconds', 0)
                duration_minutes = round(duration_seconds / 60, 2)
                
                dx = end_x - start_x
                dy = end_y - start_y
                distance = (dx * dx + dy * dy) ** 0.5
                
                user_type = vector.get('userData', {}).get('userType', '')
                grade_level = vector.get('userData', {}).get('gradeLevel', '')
                department = vector.get('userData', {}).get('department', '')
                
                csv_lines.append(f"{route_id},{idx+1},{start_y},{start_x},{end_y},{end_x},{transport},{distance:.2f},{duration_seconds},{duration_minutes},{user_type},{grade_level},{department}")
        
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)