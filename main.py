from flask import Flask, render_template_string, request, jsonify, send_file, session
from datetime import datetime, date, timedelta
import json
import os
import sqlite3
from werkzeug.utils import secure_filename
import csv
import io

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def init_db():
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS profiles
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE NOT NULL,
                  theme TEXT DEFAULT 'modern',
                  created_date TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS expenses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  profile_id INTEGER,
                  amount REAL NOT NULL,
                  description TEXT,
                  payment_method TEXT,
                  category TEXT,
                  date TEXT,
                  timestamp TEXT,
                  FOREIGN KEY (profile_id) REFERENCES profiles (id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS categories
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  profile_id INTEGER,
                  name TEXT,
                  UNIQUE(profile_id, name),
                  FOREIGN KEY (profile_id) REFERENCES profiles (id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS income
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  profile_id INTEGER,
                  amount REAL NOT NULL,
                  source TEXT,
                  type TEXT,
                  date TEXT,
                  timestamp TEXT,
                  FOREIGN KEY (profile_id) REFERENCES profiles (id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS budgets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  profile_id INTEGER,
                  category TEXT,
                  amount REAL,
                  period TEXT,
                  FOREIGN KEY (profile_id) REFERENCES profiles (id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS credit_statements
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  profile_id INTEGER,
                  card_name TEXT,
                  amount REAL,
                  merchant TEXT,
                  category TEXT,
                  date TEXT,
                  uploaded_date TEXT,
                  FOREIGN KEY (profile_id) REFERENCES profiles (id))''')

    c.execute('SELECT COUNT(*) FROM profiles')
    if c.fetchone()[0] == 0:
        default_profiles = ['Person A', 'Person B', 'Person C']
        for profile in default_profiles:
            c.execute('INSERT INTO profiles (name, theme, created_date) VALUES (?, ?, ?)',
                      (profile, 'modern', datetime.now().isoformat()))

    c.execute('SELECT id FROM profiles')
    profiles = c.fetchall()
    defaults = ['Food & Dining', 'Transport', 'Utilities', 'Entertainment', 'Shopping', 'Healthcare', 'Miscellaneous']
    for profile_id, in profiles:
        for cat in defaults:
            c.execute('SELECT COUNT(*) FROM categories WHERE profile_id = ? AND name = ?', (profile_id, cat))
            if c.fetchone()[0] == 0:
                c.execute('INSERT INTO categories (profile_id, name) VALUES (?, ?)', (profile_id, cat))

    conn.commit()
    conn.close()

init_db()

def get_profile_id():
    return session.get('profile_id', 1)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>💰 Expense Tracker</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }
        
        :root {
            --primary: #00D9A3;
            --primary-dark: #00B388;
            --secondary: #1E2738;
            --bg-dark: #151B28;
            --bg-card: #1E2738;
            --text-primary: #FFFFFF;
            --text-secondary: #8F9BB3;
            --danger: #FF3D71;
            --warning: #FFAA00;
            --success: #00E096;
            --shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }
        
        /* Dashboard Header */
        .dashboard-header {
            background: linear-gradient(135deg, #1E2738 0%, #151B28 100%);
            padding: 24px 20px;
            border-radius: 0 0 32px 32px;
            margin-bottom: 20px;
        }
        
        .user-greeting {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 24px;
        }
        
        .user-avatar {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary) 0%, #00B388 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }
        
        .greeting-text h2 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        
        .greeting-text p {
            font-size: 13px;
            color: var(--text-secondary);
        }
        
        /* Monthly Overview Card */
        .overview-card {
            background: var(--bg-card);
            border-radius: 24px;
            padding: 24px;
            text-align: center;
            margin-bottom: 24px;
        }
        
        .overview-card h3 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 24px;
        }
        
        .circular-progress {
            position: relative;
            width: 180px;
            height: 180px;
            margin: 0 auto 24px;
        }
        
        .progress-ring {
            transform: rotate(-90deg);
        }
        
        .progress-ring-bg {
            fill: none;
            stroke: rgba(0, 217, 163, 0.1);
            stroke-width: 12;
        }
        
        .progress-ring-fill {
            fill: none;
            stroke: url(#progressGradient);
            stroke-width: 12;
            stroke-linecap: round;
            transition: stroke-dashoffset 0.5s ease;
        }
        
        .progress-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }
        
        .progress-percentage {
            font-size: 42px;
            font-weight: 800;
            display: block;
        }
        
        .progress-label {
            font-size: 14px;
            color: var(--text-secondary);
        }
        
        .budget-info {
            display: flex;
            justify-content: space-between;
            padding: 16px 0;
            border-top: 1px solid rgba(143, 155, 179, 0.1);
        }
        
        .budget-info span {
            font-size: 14px;
            color: var(--text-secondary);
        }
        
        .budget-info strong {
            font-size: 18px;
            color: var(--text-primary);
            display: block;
            margin-top: 4px;
        }
        
        /* Category Chart */
        .category-chart-card {
            background: var(--bg-card);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 24px;
        }
        
        .category-chart-card h3 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 20px;
        }
        
        .chart-wrapper {
            position: relative;
            height: 260px;
            margin-bottom: 20px;
        }
        
        .category-legend {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
        }
        
        .legend-color {
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }
        
        .legend-label {
            flex: 1;
            color: var(--text-secondary);
        }
        
        .legend-value {
            font-weight: 600;
        }
        
        /* Budget Indicators */
        .budget-indicators {
            display: flex;
            gap: 12px;
            margin-top: 16px;
        }
        
        .indicator {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            padding: 6px 12px;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.05);
        }
        
        .indicator-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }
        
        .indicator.over .indicator-dot {
            background: var(--danger);
        }
        
        .indicator.under .indicator-dot {
            background: var(--success);
        }
        
        /* Bottom Navigation */
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-card);
            border-radius: 24px 24px 0 0;
            padding: 12px 20px 24px;
            display: flex;
            justify-content: space-around;
            align-items: center;
            box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.3);
            z-index: 100;
        }
        
        .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.3s;
            padding: 8px 12px;
            border-radius: 12px;
        }
        
        .nav-item.active {
            color: var(--primary);
        }
        
        .nav-icon {
            font-size: 24px;
        }
        
        .add-button {
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            color: white;
            cursor: pointer;
            box-shadow: 0 8px 24px rgba(0, 217, 163, 0.4);
            transition: all 0.3s;
            margin-top: -28px;
        }
        
        .add-button:active {
            transform: scale(0.95);
        }
        
        /* Modal */
        .modal {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            display: none;
            align-items: flex-end;
            z-index: 200;
            animation: fadeIn 0.3s;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: var(--bg-card);
            border-radius: 24px 24px 0 0;
            width: 100%;
            max-height: 85vh;
            overflow-y: auto;
            padding: 24px 20px 40px;
            animation: slideUp 0.3s;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        @keyframes slideUp {
            from { transform: translateY(100%); }
            to { transform: translateY(0); }
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }
        
        .modal-header h2 {
            font-size: 22px;
            font-weight: 700;
        }
        
        .close-btn {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.1);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            cursor: pointer;
        }
        
        /* Form Styles */
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        input, select, textarea {
            width: 100%;
            padding: 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            color: var(--text-primary);
            font-size: 16px;
            font-family: 'Inter', sans-serif;
            transition: all 0.3s;
        }
        
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: var(--primary);
            background: rgba(0, 217, 163, 0.05);
        }
        
        .amount-input {
            font-size: 36px;
            font-weight: 700;
            text-align: center;
            letter-spacing: -1px;
        }
        
        /* Payment Methods */
        .payment-methods {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        
        .payment-option {
            padding: 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 600;
        }
        
        .payment-option.selected {
            background: rgba(0, 217, 163, 0.1);
            border-color: var(--primary);
            color: var(--primary);
        }
        
        /* Button */
        .btn-primary {
            width: 100%;
            padding: 18px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            border-radius: 16px;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 8px 24px rgba(0, 217, 163, 0.3);
        }
        
        .btn-primary:active {
            transform: scale(0.98);
        }
        
        /* Content Pages */
        .page-content {
            padding: 0 20px 100px;
            display: none;
        }
        
        .page-content.active {
            display: block;
        }
        
        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: var(--bg-card);
            padding: 20px;
            border-radius: 20px;
            text-align: center;
        }
        
        .stat-label {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: 700;
            color: var(--primary);
        }
        
        /* Profile Selector */
        .profile-selector {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
            overflow-x: auto;
            padding-bottom: 8px;
        }
        
        .profile-chip {
            padding: 8px 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .profile-chip.active {
            background: rgba(0, 217, 163, 0.1);
            border-color: var(--primary);
            color: var(--primary);
        }
        
        /* Alert */
        .alert {
            padding: 16px;
            border-radius: 16px;
            margin-bottom: 16px;
            font-weight: 600;
            animation: slideDown 0.3s;
        }
        
        .alert.success {
            background: rgba(0, 224, 150, 0.1);
            color: var(--success);
            border: 1px solid var(--success);
        }
        
        .alert.error {
            background: rgba(255, 61, 113, 0.1);
            color: var(--danger);
            border: 1px solid var(--danger);
        }
        
        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        /* Transaction List */
        .transaction-list {
            margin-top: 20px;
        }
        
        .transaction-item {
            background: var(--bg-card);
            padding: 16px;
            border-radius: 16px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .transaction-icon {
            width: 48px;
            height: 48px;
            border-radius: 14px;
            background: rgba(0, 217, 163, 0.1);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }
        
        .transaction-details {
            flex: 1;
        }
        
        .transaction-title {
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .transaction-meta {
            font-size: 12px;
            color: var(--text-secondary);
        }
        
        .transaction-amount {
            font-size: 18px;
            font-weight: 700;
            color: var(--primary);
        }
        
        /* Settings Page */
        .settings-section {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 16px;
        }
        
        .settings-section h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
        }
        
        .category-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }
        
        .category-tag {
            padding: 8px 16px;
            background: rgba(0, 217, 163, 0.1);
            border: 1px solid var(--primary);
            color: var(--primary);
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .delete-icon {
            cursor: pointer;
            opacity: 0.7;
        }
        
        .delete-icon:hover {
            opacity: 1;
        }
        
        /* Responsive */
        @media (max-width: 390px) {
            .circular-progress {
                width: 160px;
                height: 160px;
            }
            
            .progress-percentage {
                font-size: 36px;
            }
        }
        
        /* Loading State */
        .loading {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-secondary);
        }
        
        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid rgba(0, 217, 163, 0.1);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 16px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <!-- Dashboard Page -->
    <div class="page-content active" id="dashboardPage">
        <div class="dashboard-header">
            <div class="user-greeting">
                <div class="user-avatar">👤</div>
                <div class="greeting-text">
                    <h2>Hello, <span id="userName">User</span>!</h2>
                    <p>Let's see how you're tracking</p>
                </div>
            </div>
            
            <div class="profile-selector" id="profileSelector"></div>
        </div>
        
        <div style="padding: 0 20px;">
            <div class="overview-card">
                <h3>Monthly Overview</h3>
                
                <div class="circular-progress">
                    <svg class="progress-ring" width="180" height="180">
                        <defs>
                            <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:#00D9A3"/>
                                <stop offset="100%" style="stop-color:#00B388"/>
                            </linearGradient>
                        </defs>
                        <circle class="progress-ring-bg" cx="90" cy="90" r="80"/>
                        <circle class="progress-ring-fill" id="progressCircle" cx="90" cy="90" r="80" 
                                stroke-dasharray="502.65" stroke-dashoffset="125.66"/>
                    </svg>
                    <div class="progress-text">
                        <span class="progress-percentage" id="usedPercentage">75%</span>
                        <span class="progress-label">Used</span>
                    </div>
                </div>
                
                <div class="budget-info">
                    <div>
                        <span>Spent</span>
                        <strong>₹<span id="totalSpent">1,500</span></strong>
                    </div>
                    <div>
                        <span>Budget</span>
                        <strong>₹<span id="totalBudget">2,000</span></strong>
                    </div>
                </div>
                <div style="text-align: center; margin-top: 8px; font-size: 13px; color: var(--text-secondary);">
                    Remaining: <strong style="color: var(--primary);">₹<span id="remaining">500</span></strong>
                </div>
            </div>
            
            <div class="category-chart-card">
                <h3>Spending by Category</h3>
                <div class="chart-wrapper">
                    <canvas id="categoryChart"></canvas>
                </div>
                <div class="category-legend" id="categoryLegend"></div>
                
                <div class="budget-indicators">
                    <div class="indicator over">
                        <div class="indicator-dot"></div>
                        <span id="overBudget">Over Budget</span>
                    </div>
                    <div class="indicator under">
                        <div class="indicator-dot"></div>
                        <span id="underBudget">Under Budget</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Expenses Page -->
    <div class="page-content" id="expensesPage">
        <div style="padding-top: 20px;">
            <h2 style="font-size: 24px; margin-bottom: 20px; padding: 0 20px;">Recent Expenses</h2>
            <div id="expensesList" style="padding: 0 20px;"></div>
        </div>
    </div>
    
    <!-- Analytics Page -->
    <div class="page-content" id="analyticsPage">
        <div style="padding-top: 20px;">
            <h2 style="font-size: 24px; margin-bottom: 20px; padding: 0 20px;">Analytics</h2>
            <div class="stats-grid" style="padding: 0 20px;" id="statsGrid"></div>
        </div>
    </div>
    
    <!-- Settings Page -->
    <div class="page-content" id="settingsPage">
        <div style="padding-top: 20px; padding: 20px;">
            <h2 style="font-size: 24px; margin-bottom: 20px;">Settings</h2>
            
            <div class="settings-section">
                <h3>Profile Name</h3>
                <input type="text" id="profileName" placeholder="Your name">
                <button class="btn-primary" style="margin-top: 12px;" onclick="updateProfileName()">Update Name</button>
            </div>
            
            <div class="settings-section">
                <h3>Categories</h3>
                <input type="text" id="newCategory" placeholder="Add new category">
                <button class="btn-primary" style="margin-top: 12px;" onclick="addCategory()">Add Category</button>
                <div class="category-tags" id="categoryTags"></div>
            </div>
            
            <div class="settings-section">
                <h3>Export Data</h3>
                <button class="btn-primary" onclick="exportData()">Download CSV</button>
            </div>
        </div>
    </div>
    
    <!-- Add Expense Modal -->
    <div class="modal" id="expenseModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Add Expense</h2>
                <div class="close-btn" onclick="closeModal()">✕</div>
            </div>
            
            <div id="modalAlert"></div>
            
            <form id="expenseForm">
                <div class="form-group">
                    <label>Amount (₹)</label>
                    <input type="number" id="amount" class="amount-input" placeholder="0" step="0.01" required>
                </div>
                
                <div class="form-group">
                    <label>Description</label>
                    <input type="text" id="description" placeholder="What did you spend on?">
                </div>
                
                <div class="form-group">
                    <label>Payment Method</label>
                    <div class="payment-methods">
                        <div class="payment-option" data-method="Cash" onclick="selectPayment(this)">💵 Cash</div>
                        <div class="payment-option" data-method="Credit Card" onclick="selectPayment(this)">💳 Credit</div>
                        <div class="payment-option" data-method="Debit Card" onclick="selectPayment(this)">💳 Debit</div>
                        <div class="payment-option" data-method="UPI" onclick="selectPayment(this)">📱 UPI</div>
                    </div>
                    <input type="hidden" id="paymentMethod" required>
                </div>
                
                <div class="form-group">
                    <label>Category</label>
                    <select id="category" required></select>
                </div>
                
                <div class="form-group">
                    <label>Date</label>
                    <input type="date" id="date" required>
                </div>
                
                <button type="submit" class="btn-primary">Add Expense</button>
            </form>
        </div>
    </div>
    
    <!-- Bottom Navigation -->
    <div class="bottom-nav">
        <div class="nav-item active" onclick="switchPage('dashboard')">
            <div class="nav-icon">📊</div>
            <span>Dashboard</span>
        </div>
        <div class="nav-item" onclick="switchPage('expenses')">
            <div class="nav-icon">💸</div>
            <span>Expenses</span>
        </div>
        <div class="add-button" onclick="openModal()">+</div>
        <div class="nav-item" onclick="switchPage('analytics')">
            <div class="nav-icon">📈</div>
            <span>Analytics</span>
        </div>
        <div class="nav-item" onclick="switchPage('settings')">
            <div class="nav-icon">⚙️</div>
            <span>Settings</span>
        </div>
    </div>

    <script>
        let chart = null;
        const colors = ['#00D9A3', '#FF6B9D', '#FFA94D', '#845EC2', '#2C73D2', '#00C9A7', '#C34A36'];
        
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('date').valueAsDate = new Date();
            loadProfiles();
            loadData();
            setInterval(updateCircularProgress, 100);
        });

        async function loadProfiles() {
            try {
                const response = await fetch('/api/profiles');
                const profiles = await response.json();
                
                const container = document.getElementById('profileSelector');
                container.innerHTML = '';
                
                profiles.forEach(profile => {
                    const chip = document.createElement('div');
                    chip.className = 'profile-chip' + (profile.is_current ? ' active' : '');
                    chip.textContent = profile.name;
                    chip.onclick = () => switchProfile(profile.id);
                    container.appendChild(chip);
                });
                
                const current = profiles.find(p => p.is_current);
                if (current) {
                    document.getElementById('userName').textContent = current.name;
                    const nameInput = document.getElementById('profileName');
                    if (nameInput) nameInput.value = current.name;
                }
            } catch (error) {
                console.error('Error loading profiles:', error);
            }
        }

        async function switchProfile(profileId) {
            await fetch('/api/profile/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile_id: profileId })
            });
            location.reload();
        }

        async function loadData() {
            await loadCategories();
            await loadSummary();
            await loadExpenses();
        }

        async function loadCategories() {
            try {
                const response = await fetch('/api/categories');
                const categories = await response.json();
                
                const categorySelect = document.getElementById('category');
                categorySelect.innerHTML = '<option value="">Select category...</option>';
                
                // Remove duplicates
                const uniqueCategories = [...new Map(categories.map(cat => [cat.name, cat])).values()];
                
                uniqueCategories.forEach(cat => {
                    const option = document.createElement('option');
                    option.value = cat.name;
                    option.textContent = cat.name;
                    categorySelect.appendChild(option);
                });
                
                // Update settings category tags
                const tagsContainer = document.getElementById('categoryTags');
                if (tagsContainer) {
                    tagsContainer.innerHTML = '';
                    uniqueCategories.forEach(cat => {
                        const tag = document.createElement('div');
                        tag.className = 'category-tag';
                        tag.innerHTML = `${cat.name} <span class="delete-icon" onclick="deleteCategory('${cat.name}')">✕</span>`;
                        tagsContainer.appendChild(tag);
                    });
                }
            } catch (error) {
                console.error('Error loading categories:', error);
            }
        }

        async function loadSummary() {
            try {
                const response = await fetch('/api/summary?period=monthly');
                const data = await response.json();
                
                document.getElementById('totalSpent').textContent = data.total_expenses.toFixed(0);
                document.getElementById('totalBudget').textContent = data.total_budget.toFixed(0);
                document.getElementById('remaining').textContent = (data.total_budget - data.total_expenses).toFixed(0);
                
                const percentage = data.total_budget > 0 ? (data.total_expenses / data.total_budget * 100) : 0;
                document.getElementById('usedPercentage').textContent = Math.round(percentage) + '%';
                
                updateCircularProgress(percentage);
                updateCategoryChart(data.by_category);
            } catch (error) {
                console.error('Error loading summary:', error);
            }
        }

        function updateCircularProgress(percentage = 75) {
            const circle = document.getElementById('progressCircle');
            const circumference = 2 * Math.PI * 80;
            const offset = circumference - (percentage / 100) * circumference;
            circle.style.strokeDashoffset = offset;
        }

        function updateCategoryChart(categoryData) {
            const ctx = document.getElementById('categoryChart').getContext('2d');
            
            if (chart) chart.destroy();
            
            const labels = Object.keys(categoryData);
            const values = Object.values(categoryData);
            const total = values.reduce((a, b) => a + b, 0);
            
            chart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors,
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '70%',
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: '#1E2738',
                            padding: 12,
                            titleFont: { size: 14, weight: '600' },
                            bodyFont: { size: 13 },
                            cornerRadius: 8
                        }
                    }
                }
            });
            
            // Update legend
            const legend = document.getElementById('categoryLegend');
            legend.innerHTML = '';
            labels.forEach((label, i) => {
                const percentage = total > 0 ? ((values[i] / total) * 100).toFixed(0) : 0;
                legend.innerHTML += `
                    <div class="legend-item">
                        <div class="legend-color" style="background: ${colors[i]}"></div>
                        <span class="legend-label">${label}</span>
                        <span class="legend-value">${percentage}%</span>
                    </div>
                `;
            });
        }

        async function loadExpenses() {
            try {
                const response = await fetch('/api/expenses');
                const expenses = await response.json();
                
                const container = document.getElementById('expensesList');
                container.innerHTML = '';
                
                expenses.slice(0, 20).forEach(expense => {
                    const emoji = getCategoryEmoji(expense.category);
                    container.innerHTML += `
                        <div class="transaction-item">
                            <div class="transaction-icon">${emoji}</div>
                            <div class="transaction-details">
                                <div class="transaction-title">${expense.description || expense.category}</div>
                                <div class="transaction-meta">${expense.category} • ${expense.date}</div>
                            </div>
                            <div class="transaction-amount">₹${expense.amount.toFixed(0)}</div>
                        </div>
                    `;
                });
            } catch (error) {
                console.error('Error loading expenses:', error);
            }
        }

        function getCategoryEmoji(category) {
            const emojis = {
                'Food & Dining': '🍔',
                'Transport': '🚗',
                'Utilities': '💡',
                'Entertainment': '🎬',
                'Shopping': '🛍️',
                'Healthcare': '🏥',
                'Miscellaneous': '📦'
            };
            return emojis[category] || '💰';
        }

        function switchPage(page) {
            document.querySelectorAll('.page-content').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            
            document.getElementById(page + 'Page').classList.add('active');
            event.currentTarget.classList.add('active');
            
            if (page === 'analytics') loadAnalytics();
        }

        async function loadAnalytics() {
            try {
                const response = await fetch('/api/analytics?period=monthly');
                const data = await response.json();
                
                const grid = document.getElementById('statsGrid');
                grid.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-label">Total Spent</div>
                        <div class="stat-value">₹${data.total_expenses.toFixed(0)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Avg Daily</div>
                        <div class="stat-value">₹${data.avg_daily.toFixed(0)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Transactions</div>
                        <div class="stat-value">${data.transaction_count}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Top Category</div>
                        <div class="stat-value" style="font-size: 16px;">${data.highest_category || 'N/A'}</div>
                    </div>
                `;
            } catch (error) {
                console.error('Error loading analytics:', error);
            }
        }

        function openModal() {
            document.getElementById('expenseModal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('expenseModal').classList.remove('active');
        }

        function selectPayment(element) {
            document.querySelectorAll('.payment-option').forEach(el => el.classList.remove('selected'));
            element.classList.add('selected');
            document.getElementById('paymentMethod').value = element.dataset.method;
        }

        document.getElementById('expenseForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const expense = {
                amount: parseFloat(document.getElementById('amount').value),
                description: document.getElementById('description').value,
                paymentMethod: document.getElementById('paymentMethod').value,
                category: document.getElementById('category').value,
                date: document.getElementById('date').value
            };

            try {
                const response = await fetch('/api/expenses', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(expense)
                });

                if (response.ok) {
                    showAlert('Expense added successfully!', 'success');
                    this.reset();
                    document.getElementById('date').valueAsDate = new Date();
                    document.querySelectorAll('.payment-option').forEach(el => el.classList.remove('selected'));
                    setTimeout(() => {
                        closeModal();
                        loadData();
                    }, 1500);
                }
            } catch (error) {
                showAlert('Error adding expense', 'error');
            }
        });

        async function addCategory() {
            const name = document.getElementById('newCategory').value.trim();
            if (!name) return;

            try {
                const response = await fetch('/api/categories', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });

                if (response.ok) {
                    document.getElementById('newCategory').value = '';
                    showAlert('Category added!', 'success');
                    loadCategories();
                }
            } catch (error) {
                showAlert('Error adding category', 'error');
            }
        }

        async function deleteCategory(name) {
            if (!confirm(`Delete "${name}"?`)) return;

            try {
                const response = await fetch(`/api/categories/${encodeURIComponent(name)}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    showAlert('Category deleted!', 'success');
                    loadCategories();
                }
            } catch (error) {
                showAlert('Error deleting category', 'error');
            }
        }

        async function updateProfileName() {
            const name = document.getElementById('profileName').value.trim();
            if (!name) return;

            try {
                const response = await fetch('/api/profile/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });

                if (response.ok) {
                    showAlert('Profile updated!', 'success');
                    loadProfiles();
                }
            } catch (error) {
                showAlert('Error updating profile', 'error');
            }
        }

        function exportData() {
            window.location.href = '/api/export';
        }

        function showAlert(message, type) {
            const container = document.getElementById('modalAlert');
            container.innerHTML = `<div class="alert ${type}">${message}</div>`;
            setTimeout(() => container.innerHTML = '', 3000);
        }

        // Close modal on backdrop click
        document.getElementById('expenseModal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/profiles')
def get_profiles():
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('SELECT id, name, theme FROM profiles')
    profiles = []
    current_profile_id = get_profile_id()
    for row in c.fetchall():
        profiles.append({
            'id': row[0],
            'name': row[1],
            'theme': row[2],
            'is_current': row[0] == current_profile_id
        })
    conn.close()
    return jsonify(profiles)

@app.route('/api/profile/switch', methods=['POST'])
def switch_profile():
    profile_id = request.json['profile_id']
    session['profile_id'] = profile_id
    return jsonify({'success': True})

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    name = request.json['name']
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('UPDATE profiles SET name = ? WHERE id = ?', (name, profile_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/categories', methods=['GET', 'POST'])
def categories():
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    if request.method == 'POST':
        name = request.json['name']
        try:
            c.execute('INSERT INTO categories (profile_id, name) VALUES (?, ?)', (profile_id, name))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'error': 'Category exists'}), 400

    c.execute('SELECT DISTINCT name FROM categories WHERE profile_id = ? ORDER BY name', (profile_id,))
    categories = [{'id': i, 'name': row[0]} for i, row in enumerate(c.fetchall())]
    conn.close()
    return jsonify(categories)

@app.route('/api/categories/<name>', methods=['DELETE'])
def delete_category(name):
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('DELETE FROM categories WHERE profile_id = ? AND name = ?', (profile_id, name))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/expenses', methods=['GET', 'POST'])
def expenses():
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    if request.method == 'POST':
        exp = request.json
        c.execute('''INSERT INTO expenses (profile_id, amount, description, payment_method, category, date, timestamp)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (profile_id, exp['amount'], exp['description'], exp['paymentMethod'],
                   exp['category'], exp['date'], datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    c.execute('SELECT * FROM expenses WHERE profile_id = ? ORDER BY date DESC', (profile_id,))
    expenses = []
    for row in c.fetchall():
        expenses.append({
            'id': row[0], 'amount': row[2], 'description': row[3],
            'paymentMethod': row[4], 'category': row[5], 'date': row[6]
        })
    conn.close()
    return jsonify(expenses)

@app.route('/api/summary')
def summary():
    profile_id = get_profile_id()
    period = request.args.get('period', 'monthly')

    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    today = date.today()
    if period == 'monthly':
        start_date = today.replace(day=1).isoformat()
    else:
        start_date = '1970-01-01'

    c.execute('SELECT SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ?', (profile_id, start_date))
    total_expenses = c.fetchone()[0] or 0

    c.execute('SELECT category, SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? GROUP BY category',
              (profile_id, start_date))
    by_category = {row[0]: row[1] for row in c.fetchall()}

    c.execute("SELECT amount FROM budgets WHERE profile_id = ? AND category = 'MONTHLY' AND period = 'monthly'", (profile_id,))
    result = c.fetchone()
    total_budget = result[0] if result else 0

    conn.close()

    return jsonify({
        'total_expenses': total_expenses,
        'total_budget': total_budget,
        'by_category': by_category
    })

@app.route('/api/analytics')
def analytics():
    profile_id = get_profile_id()
    period = request.args.get('period', 'monthly')

    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    today = date.today()
    start_date = today.replace(day=1).isoformat()
    days = (today - today.replace(day=1)).days + 1

    c.execute('SELECT SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ?', (profile_id, start_date))
    total_expenses = c.fetchone()[0] or 0

    c.execute('SELECT COUNT(*) FROM expenses WHERE profile_id = ? AND date >= ?', (profile_id, start_date))
    transaction_count = c.fetchone()[0]

    c.execute('SELECT category, SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? GROUP BY category',
              (profile_id, start_date))
    by_category = {row[0]: row[1] for row in c.fetchall()}
    highest_category = max(by_category, key=by_category.get) if by_category else None

    conn.close()

    return jsonify({
        'total_expenses': total_expenses,
        'avg_daily': total_expenses / days if days > 0 else 0,
        'transaction_count': transaction_count,
        'highest_category': highest_category
    })

@app.route('/api/export')
def export_data():
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['Type', 'Date', 'Amount', 'Category', 'Description', 'Payment Method'])

    c.execute('SELECT date, amount, category, description, payment_method FROM expenses WHERE profile_id = ? ORDER BY date DESC', (profile_id,))
    for row in c.fetchall():
        writer.writerow(['Expense', row[0], row[1], row[2], row[3], row[4]])

    conn.close()

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'expenses_export_{datetime.now().strftime("%Y%m%d")}.csv'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)