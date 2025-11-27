from flask import Flask, render_template_string, request, jsonify, send_file, session
from datetime import datetime, date, timedelta
import json
import os
import sqlite3
from werkzeug.utils import secure_filename
import csv
import io
from functools import wraps

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

    # Create default profiles if none exist
    c.execute('SELECT COUNT(*) FROM profiles')
    if c.fetchone()[0] == 0:
        default_profiles = ['Person A', 'Person B', 'Person C']
        for profile in default_profiles:
            c.execute('INSERT INTO profiles (name, theme, created_date) VALUES (?, ?, ?)',
                      (profile, 'modern', datetime.now().isoformat()))

    # Add default categories for each profile
    c.execute('SELECT id FROM profiles')
    profiles = c.fetchall()
    defaults = ['Food', 'Transport', 'Utilities', 'Entertainment', 'Shopping', 'Healthcare', 'Miscellaneous']
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

# HTML Template with modern dark mobile UI
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Expense Tracker Pro</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --bg-primary: #1a1f3c;
            --bg-secondary: #252d4a;
            --bg-card: #2a3352;
            --bg-card-alt: #323b5c;
            --accent-green: #4ade80;
            --accent-green-dark: #22c55e;
            --accent-orange: #fb923c;
            --accent-blue: #60a5fa;
            --accent-purple: #a78bfa;
            --accent-teal: #2dd4bf;
            --accent-pink: #f472b6;
            --accent-red: #f87171;
            --text-primary: #ffffff;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-color: #3d4a6b;
            --shadow: rgba(0, 0, 0, 0.3);
            --glow-green: rgba(74, 222, 128, 0.3);
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            min-height: 100vh;
            color: var(--text-primary);
            padding-bottom: 100px;
            overflow-x: hidden;
        }
        
        /* Background glow effects */
        body::before {
            content: '';
            position: fixed;
            top: 10%;
            left: 50%;
            transform: translateX(-50%);
            width: 300px;
            height: 300px;
            background: radial-gradient(circle, rgba(74, 222, 128, 0.08) 0%, transparent 70%);
            pointer-events: none;
            z-index: 0;
        }
        
        .app-container {
            max-width: 480px;
            margin: 0 auto;
            padding: 20px 16px;
            position: relative;
            z-index: 1;
        }
        
        /* Header Section */
        .header {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 28px;
        }
        
        .avatar {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 4px 15px rgba(96, 165, 250, 0.3);
        }
        
        .greeting h1 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        
        .greeting p {
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.4;
        }
        
        .profile-switcher {
            margin-left: auto;
            position: relative;
        }
        
        .profile-btn {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 8px 14px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.3s;
        }
        
        .profile-btn:hover {
            background: var(--bg-card-alt);
        }
        
        .profile-dropdown {
            position: absolute;
            top: 100%;
            right: 0;
            margin-top: 8px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            min-width: 150px;
            display: none;
            overflow: hidden;
            z-index: 100;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
        }
        
        .profile-dropdown.active {
            display: block;
        }
        
        .profile-option {
            padding: 12px 16px;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            background: none;
            color: var(--text-primary);
            width: 100%;
            text-align: left;
        }
        
        .profile-option:hover {
            background: var(--bg-card-alt);
        }
        
        .profile-option.active {
            background: var(--accent-green);
            color: var(--bg-primary);
            font-weight: 600;
        }
        
        /* Monthly Overview Card */
        .overview-card {
            background: var(--bg-card);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
        }
        
        .overview-card::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -30%;
            width: 200px;
            height: 200px;
            background: radial-gradient(circle, var(--glow-green) 0%, transparent 70%);
            pointer-events: none;
        }
        
        .overview-title {
            text-align: center;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 24px;
            color: var(--text-primary);
        }
        
        .circular-progress-container {
            display: flex;
            justify-content: center;
            margin-bottom: 20px;
        }
        
        .circular-progress {
            position: relative;
            width: 160px;
            height: 160px;
        }
        
        .circular-progress svg {
            transform: rotate(-90deg);
        }
        
        .circular-progress .bg-circle {
            fill: none;
            stroke: var(--bg-card-alt);
            stroke-width: 12;
        }
        
        .circular-progress .progress-circle {
            fill: none;
            stroke: var(--accent-green);
            stroke-width: 12;
            stroke-linecap: round;
            transition: stroke-dashoffset 0.8s ease;
            filter: drop-shadow(0 0 8px var(--glow-green));
        }
        
        .circular-progress .progress-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }
        
        .progress-percentage {
            font-size: 36px;
            font-weight: 800;
            color: var(--text-primary);
            line-height: 1;
        }
        
        .progress-label {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 4px;
        }
        
        .budget-details {
            text-align: center;
        }
        
        .budget-amount {
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
        }
        
        .budget-remaining {
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 4px;
        }
        
        /* Category Card */
        .category-card {
            background: var(--bg-card);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 20px;
        }
        
        .category-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 20px;
            color: var(--text-primary);
        }
        
        .category-chart-container {
            position: relative;
            height: 220px;
            margin-bottom: 20px;
        }
        
        .budget-status {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }
        
        .status-dot.over {
            background: var(--accent-orange);
            box-shadow: 0 0 8px var(--accent-orange);
        }
        
        .status-dot.under {
            background: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
        }
        
        .status-label.over {
            color: var(--accent-orange);
        }
        
        .status-label.under {
            color: var(--accent-green);
        }
        
        /* Transaction Cards */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        
        .section-title {
            font-size: 16px;
            font-weight: 600;
        }
        
        .see-all {
            font-size: 13px;
            color: var(--accent-green);
            cursor: pointer;
            font-weight: 500;
        }
        
        .transaction-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .transaction-item {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 16px;
            display: flex;
            align-items: center;
            gap: 14px;
            transition: all 0.3s;
        }
        
        .transaction-item:hover {
            background: var(--bg-card-alt);
            transform: translateX(4px);
        }
        
        .transaction-icon {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }
        
        .transaction-icon.food { background: rgba(251, 146, 60, 0.2); }
        .transaction-icon.transport { background: rgba(74, 222, 128, 0.2); }
        .transaction-icon.entertainment { background: rgba(96, 165, 250, 0.2); }
        .transaction-icon.utilities { background: rgba(251, 146, 60, 0.2); }
        .transaction-icon.shopping { background: rgba(244, 114, 182, 0.2); }
        .transaction-icon.healthcare { background: rgba(248, 113, 113, 0.2); }
        .transaction-icon.income { background: rgba(74, 222, 128, 0.2); }
        
        .transaction-details {
            flex: 1;
        }
        
        .transaction-title {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .transaction-subtitle {
            font-size: 12px;
            color: var(--text-secondary);
        }
        
        .transaction-amount {
            font-size: 16px;
            font-weight: 700;
        }
        
        .transaction-amount.expense {
            color: var(--accent-orange);
        }
        
        .transaction-amount.income {
            color: var(--accent-green);
        }
        
        /* Bottom Navigation */
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-color);
            padding: 12px 20px 24px;
            display: flex;
            justify-content: space-around;
            align-items: flex-end;
            z-index: 1000;
        }
        
        .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            transition: all 0.3s;
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 4px 12px;
        }
        
        .nav-item:hover, .nav-item.active {
            color: var(--accent-green);
        }
        
        .nav-item .icon {
            font-size: 22px;
        }
        
        .nav-item .label {
            font-size: 11px;
            font-weight: 500;
        }
        
        .fab-container {
            position: relative;
            margin-top: -30px;
        }
        
        .fab {
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: var(--accent-green);
            border: none;
            color: var(--bg-primary);
            font-size: 28px;
            font-weight: 300;
            cursor: pointer;
            box-shadow: 0 4px 20px var(--glow-green);
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .fab:hover {
            transform: scale(1.1);
            box-shadow: 0 6px 30px var(--glow-green);
        }
        
        .fab-label {
            font-size: 10px;
            color: var(--text-secondary);
            margin-top: 8px;
            white-space: nowrap;
        }
        
        /* Modal Styles */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(4px);
            display: none;
            align-items: flex-end;
            justify-content: center;
            z-index: 2000;
        }
        
        .modal-overlay.active {
            display: flex;
        }
        
        .modal {
            background: var(--bg-secondary);
            border-radius: 24px 24px 0 0;
            width: 100%;
            max-width: 480px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 24px;
            animation: slideUp 0.3s ease;
        }
        
        @keyframes slideUp {
            from {
                transform: translateY(100%);
            }
            to {
                transform: translateY(0);
            }
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }
        
        .modal-title {
            font-size: 20px;
            font-weight: 700;
        }
        
        .modal-close {
            background: var(--bg-card);
            border: none;
            color: var(--text-primary);
            width: 36px;
            height: 36px;
            border-radius: 50%;
            font-size: 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .form-input {
            width: 100%;
            padding: 16px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            font-size: 16px;
            color: var(--text-primary);
            transition: all 0.3s;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--accent-green);
            box-shadow: 0 0 0 3px var(--glow-green);
        }
        
        .form-input::placeholder {
            color: var(--text-muted);
        }
        
        .amount-input-wrapper {
            position: relative;
        }
        
        .currency-symbol {
            position: absolute;
            left: 16px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 28px;
            font-weight: 700;
            color: var(--text-secondary);
        }
        
        .amount-input {
            font-size: 36px;
            font-weight: 700;
            text-align: center;
            padding: 20px;
        }
        
        .payment-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        
        .payment-option {
            background: var(--bg-card);
            border: 2px solid var(--border-color);
            border-radius: 14px;
            padding: 16px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            color: var(--text-primary);
        }
        
        .payment-option:hover {
            border-color: var(--accent-green);
        }
        
        .payment-option.selected {
            border-color: var(--accent-green);
            background: rgba(74, 222, 128, 0.1);
        }
        
        .payment-icon {
            font-size: 24px;
            margin-bottom: 8px;
        }
        
        .payment-label {
            font-size: 13px;
            font-weight: 600;
        }
        
        .submit-btn {
            width: 100%;
            padding: 18px;
            background: var(--accent-green);
            border: none;
            border-radius: 14px;
            font-size: 16px;
            font-weight: 700;
            color: var(--bg-primary);
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 10px;
        }
        
        .submit-btn:hover {
            background: var(--accent-green-dark);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px var(--glow-green);
        }
        
        /* Tabs in modal */
        .modal-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
        }
        
        .modal-tab {
            flex: 1;
            padding: 12px;
            background: var(--bg-card);
            border: none;
            border-radius: 10px;
            color: var(--text-secondary);
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .modal-tab.active {
            background: var(--accent-green);
            color: var(--bg-primary);
        }
        
        /* Charts Section */
        .charts-section {
            display: none;
        }
        
        .charts-section.active {
            display: block;
        }
        
        .chart-card {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 16px;
        }
        
        .chart-title {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 16px;
        }
        
        .chart-wrapper {
            height: 200px;
            position: relative;
        }
        
        /* Period Selector */
        .period-selector {
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            overflow-x: auto;
            padding-bottom: 8px;
        }
        
        .period-btn {
            padding: 10px 18px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.3s;
        }
        
        .period-btn.active {
            background: var(--accent-green);
            border-color: var(--accent-green);
            color: var(--bg-primary);
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
            border-radius: 16px;
            padding: 16px;
        }
        
        .stat-label {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 22px;
            font-weight: 700;
            color: var(--accent-green);
        }
        
        .stat-value.alt {
            color: var(--accent-blue);
        }
        
        /* Settings Section */
        .settings-section {
            display: none;
        }
        
        .settings-section.active {
            display: block;
        }
        
        .settings-card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 16px;
        }
        
        .settings-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
        }
        
        .category-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 16px;
        }
        
        .category-tag {
            background: rgba(74, 222, 128, 0.2);
            color: var(--accent-green);
            padding: 10px 16px;
            border-radius: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            font-weight: 600;
        }
        
        .category-delete {
            background: rgba(248, 113, 113, 0.3);
            border: none;
            color: var(--accent-red);
            width: 20px;
            height: 20px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 14px;
        }
        
        /* Custom Date Range */
        .date-range {
            display: none;
            gap: 10px;
            margin-bottom: 16px;
        }
        
        .date-range.active {
            display: flex;
        }
        
        .date-range input {
            flex: 1;
        }
        
        .apply-btn {
            padding: 14px 24px;
            background: var(--accent-blue);
            border: none;
            border-radius: 14px;
            color: white;
            font-weight: 600;
            cursor: pointer;
        }
        
        /* Alert */
        .toast {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--accent-green);
            color: var(--bg-primary);
            padding: 14px 24px;
            border-radius: 12px;
            font-weight: 600;
            z-index: 3000;
            display: none;
            box-shadow: 0 4px 20px var(--glow-green);
        }
        
        .toast.active {
            display: block;
            animation: fadeInOut 3s ease;
        }
        
        .toast.error {
            background: var(--accent-red);
        }
        
        @keyframes fadeInOut {
            0%, 100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
            10%, 90% { opacity: 1; transform: translateX(-50%) translateY(0); }
        }
        
        /* Budget Overview */
        .budget-progress-item {
            margin-bottom: 20px;
        }
        
        .budget-progress-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        
        .budget-progress-label {
            font-size: 14px;
            font-weight: 600;
        }
        
        .budget-progress-amount {
            font-size: 14px;
            font-weight: 600;
        }
        
        .budget-progress-bar {
            height: 10px;
            background: var(--bg-card-alt);
            border-radius: 5px;
            overflow: hidden;
        }
        
        .budget-progress-fill {
            height: 100%;
            border-radius: 5px;
            transition: width 0.5s ease;
        }
        
        .budget-progress-fill.safe { background: var(--accent-green); }
        .budget-progress-fill.warning { background: var(--accent-orange); }
        .budget-progress-fill.danger { background: var(--accent-red); }
        
        /* Credit Card Section */
        .upload-area {
            border: 2px dashed var(--border-color);
            border-radius: 16px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .upload-area:hover {
            border-color: var(--accent-green);
            background: rgba(74, 222, 128, 0.05);
        }
        
        .upload-icon {
            font-size: 48px;
            margin-bottom: 12px;
        }
        
        .upload-text {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .upload-hint {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        /* Hide default file input */
        input[type="file"] {
            display: none;
        }
        
        /* Expenses Section */
        .expenses-section {
            display: none;
        }
        
        .expenses-section.active {
            display: block;
        }
        
        /* Dashboard Section */
        .dashboard-section {
            display: block;
        }
        
        .dashboard-section.active {
            display: block;
        }
        
        /* Groups Section (Budget) */
        .groups-section {
            display: none;
        }
        
        .groups-section.active {
            display: block;
        }
        
        .income-list-section {
            margin-top: 24px;
        }
        
        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 6px;
        }
        
        ::-webkit-scrollbar-track {
            background: var(--bg-primary);
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 3px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="toast" id="toast"></div>
    
    <div class="app-container">
        <!-- Header -->
        <div class="header">
            <div class="avatar">👤</div>
            <div class="greeting">
                <h1>Hello <span id="userName">User</span>!</h1>
                <p>Let's see how you're tracking.<br>Your spending is looking great! Keep it up!</p>
            </div>
            <div class="profile-switcher">
                <button class="profile-btn" id="profileToggle" onclick="toggleProfileDropdown()">
                    <span>👤</span>
                    <span>▼</span>
                </button>
                <div class="profile-dropdown" id="profileDropdown"></div>
            </div>
        </div>
        
        <!-- Dashboard Section -->
        <div class="dashboard-section" id="dashboardSection">
            <!-- Monthly Overview Card -->
            <div class="overview-card">
                <h2 class="overview-title">Monthly Overview</h2>
                <div class="circular-progress-container">
                    <div class="circular-progress">
                        <svg width="160" height="160">
                            <circle class="bg-circle" cx="80" cy="80" r="68"></circle>
                            <circle class="progress-circle" id="progressCircle" cx="80" cy="80" r="68" 
                                stroke-dasharray="427" stroke-dashoffset="427"></circle>
                        </svg>
                        <div class="progress-text">
                            <div class="progress-percentage" id="usedPercentage">0%</div>
                            <div class="progress-label">Used</div>
                        </div>
                    </div>
                </div>
                <div class="budget-details">
                    <div class="budget-amount">₹<span id="spentAmount">0</span> / <span id="budgetAmount">0</span></div>
                    <div class="budget-remaining">Remaining: ₹<span id="remainingAmount">0</span></div>
                </div>
            </div>
            
            <!-- Spending by Category Card -->
            <div class="category-card">
                <h2 class="category-title">Spending by Category</h2>
                <div class="category-chart-container">
                    <canvas id="categoryDonutChart"></canvas>
                </div>
                <div class="budget-status" id="budgetStatus">
                    <!-- Dynamic content -->
                </div>
            </div>
            
            <!-- Recent Transactions -->
            <div class="section-header">
                <h2 class="section-title">Recent Transactions</h2>
                <span class="see-all" onclick="switchSection('expenses')">See All</span>
            </div>
            <div class="transaction-list" id="recentTransactions">
                <!-- Dynamic content -->
            </div>
        </div>
        
        <!-- Expenses Section -->
        <div class="expenses-section" id="expensesSection">
            <h2 class="section-title" style="margin-bottom: 20px;">All Transactions</h2>
            
            <div class="period-selector">
                <button class="period-btn" onclick="setPeriod('daily', this)">Daily</button>
                <button class="period-btn active" onclick="setPeriod('monthly', this)">Monthly</button>
                <button class="period-btn" onclick="setPeriod('yearly', this)">Yearly</button>
                <button class="period-btn" onclick="setPeriod('lifetime', this)">Lifetime</button>
                <button class="period-btn" onclick="setPeriod('custom', this)">Custom</button>
            </div>
            
            <div class="date-range" id="dateRange">
                <input type="date" class="form-input" id="startDate">
                <input type="date" class="form-input" id="endDate">
                <button class="apply-btn" onclick="applyCustomRange()">Apply</button>
            </div>
            
            <div class="transaction-list" id="allTransactions">
                <!-- Dynamic content -->
            </div>
        </div>
        
        <!-- Analytics/Charts Section -->
        <div class="charts-section" id="chartsSection">
            <h2 class="section-title" style="margin-bottom: 20px;">Analytics</h2>
            
            <div class="period-selector">
                <button class="period-btn" onclick="setAnalyticsPeriod('daily', this)">Daily</button>
                <button class="period-btn active" onclick="setAnalyticsPeriod('monthly', this)">Monthly</button>
                <button class="period-btn" onclick="setAnalyticsPeriod('yearly', this)">Yearly</button>
                <button class="period-btn" onclick="setAnalyticsPeriod('lifetime', this)">Lifetime</button>
            </div>
            
            <div class="stats-grid" id="statsGrid">
                <!-- Dynamic content -->
            </div>
            
            <div class="chart-card">
                <h3 class="chart-title">Spending Trend</h3>
                <div class="chart-wrapper">
                    <canvas id="trendChart"></canvas>
                </div>
            </div>
            
            <div class="chart-card">
                <h3 class="chart-title">Payment Methods</h3>
                <div class="chart-wrapper">
                    <canvas id="paymentChart"></canvas>
                </div>
            </div>
            
            <div class="chart-card">
                <h3 class="chart-title">Income vs Expenses</h3>
                <div class="chart-wrapper">
                    <canvas id="incomeExpenseChart"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Groups/Budget Section -->
        <div class="groups-section" id="groupsSection">
            <h2 class="section-title" style="margin-bottom: 20px;">Budget Settings</h2>
            
            <div class="settings-card">
                <h3 class="settings-title">Monthly Budget</h3>
                <div class="form-group">
                    <label class="form-label">Total Monthly Budget (₹)</label>
                    <input type="number" class="form-input" id="monthlyBudget" placeholder="Enter amount">
                </div>
                <button class="submit-btn" onclick="saveMonthlyBudget()">Save Monthly Budget</button>
            </div>
            
            <div class="settings-card">
                <h3 class="settings-title">Category Budgets</h3>
                <div id="categoryBudgets">
                    <!-- Dynamic content -->
                </div>
                <button class="submit-btn" onclick="saveCategoryBudgets()" style="margin-top: 16px;">Save Category Budgets</button>
            </div>
            
            <div class="settings-card">
                <h3 class="settings-title">Budget Overview</h3>
                <div id="budgetOverview">
                    <!-- Dynamic content -->
                </div>
            </div>
            
            <div class="settings-card">
                <h3 class="settings-title">Credit Card Statements</h3>
                <div class="upload-area" onclick="document.getElementById('statementFile').click()">
                    <input type="file" id="statementFile" accept=".csv" onchange="uploadStatement()">
                    <div class="upload-icon">📄</div>
                    <div class="upload-text">Click to upload CSV</div>
                    <div class="upload-hint">Format: Date, Merchant, Amount, Category</div>
                </div>
                <div id="creditList" style="margin-top: 20px;">
                    <!-- Dynamic content -->
                </div>
            </div>
        </div>
        
        <!-- Settings Section -->
        <div class="settings-section" id="settingsSection">
            <h2 class="section-title" style="margin-bottom: 20px;">Settings</h2>
            
            <div class="settings-card">
                <h3 class="settings-title">Edit Profile</h3>
                <div class="form-group">
                    <label class="form-label">Profile Name</label>
                    <input type="text" class="form-input" id="profileName" placeholder="Enter name">
                </div>
                <button class="submit-btn" onclick="updateProfileName()">Update Name</button>
            </div>
            
            <div class="settings-card">
                <h3 class="settings-title">Manage Categories</h3>
                <div class="form-group">
                    <label class="form-label">Add New Category</label>
                    <input type="text" class="form-input" id="newCategory" placeholder="Category name">
                </div>
                <button class="submit-btn" onclick="addCategory()">Add Category</button>
                <div class="category-tags" id="categoryList">
                    <!-- Dynamic content -->
                </div>
            </div>
            
            <div class="settings-card">
                <h3 class="settings-title">Recent Income</h3>
                <div class="transaction-list" id="incomeList">
                    <!-- Dynamic content -->
                </div>
            </div>
            
            <div class="settings-card">
                <h3 class="settings-title">Export Data</h3>
                <button class="submit-btn" onclick="exportData()">Download All Data (CSV)</button>
            </div>
        </div>
    </div>
    
    <!-- Bottom Navigation -->
    <nav class="bottom-nav">
        <button class="nav-item active" onclick="switchSection('dashboard')">
            <span class="icon">🏠</span>
            <span class="label">Dashboard</span>
        </button>
        <button class="nav-item" onclick="switchSection('expenses')">
            <span class="icon">📋</span>
            <span class="label">Expenses</span>
        </button>
        <div class="fab-container">
            <button class="fab" onclick="openAddModal()">+</button>
            <div class="fab-label">Single Entry</div>
        </div>
        <button class="nav-item" onclick="switchSection('groups')">
            <span class="icon">💰</span>
            <span class="label">Budget</span>
        </button>
        <button class="nav-item" onclick="switchSection('settings')">
            <span class="icon">⚙️</span>
            <span class="label">Settings</span>
        </button>
    </nav>
    
    <!-- Add Entry Modal -->
    <div class="modal-overlay" id="addModal">
        <div class="modal">
            <div class="modal-header">
                <h2 class="modal-title">Add Entry</h2>
                <button class="modal-close" onclick="closeAddModal()">×</button>
            </div>
            
            <div class="modal-tabs">
                <button class="modal-tab active" onclick="switchModalTab('expense', this)">💸 Expense</button>
                <button class="modal-tab" onclick="switchModalTab('income', this)">💰 Income</button>
            </div>
            
            <!-- Expense Form -->
            <form id="expenseForm" class="modal-form">
                <div class="form-group">
                    <label class="form-label">Amount (₹)</label>
                    <input type="number" class="form-input amount-input" id="amount" placeholder="0.00" step="0.01" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Description</label>
                    <input type="text" class="form-input" id="description" placeholder="What did you spend on?">
                </div>
                <div class="form-group">
                    <label class="form-label">Payment Method</label>
                    <div class="payment-grid">
                        <div class="payment-option" data-method="Cash" onclick="selectPayment(this)">
                            <div class="payment-icon">💵</div>
                            <div class="payment-label">Cash</div>
                        </div>
                        <div class="payment-option" data-method="Credit Card" onclick="selectPayment(this)">
                            <div class="payment-icon">💳</div>
                            <div class="payment-label">Credit</div>
                        </div>
                        <div class="payment-option" data-method="Debit Card" onclick="selectPayment(this)">
                            <div class="payment-icon">🏦</div>
                            <div class="payment-label">Debit</div>
                        </div>
                        <div class="payment-option" data-method="UPI" onclick="selectPayment(this)">
                            <div class="payment-icon">📱</div>
                            <div class="payment-label">UPI</div>
                        </div>
                    </div>
                    <input type="hidden" id="paymentMethod" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Category</label>
                    <select class="form-input" id="category" required></select>
                </div>
                <div class="form-group">
                    <label class="form-label">Date</label>
                    <input type="date" class="form-input" id="date" required>
                </div>
                <button type="submit" class="submit-btn">Add Expense</button>
            </form>
            
            <!-- Income Form -->
            <form id="incomeForm" class="modal-form" style="display: none;">
                <div class="form-group">
                    <label class="form-label">Amount (₹)</label>
                    <input type="number" class="form-input amount-input" id="incomeAmount" placeholder="0.00" step="0.01" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Source</label>
                    <input type="text" class="form-input" id="incomeSource" placeholder="e.g., Salary, Freelance" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Type</label>
                    <select class="form-input" id="incomeType" required>
                        <option value="Regular">Regular Income</option>
                        <option value="Additional">Additional Income</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Date</label>
                    <input type="date" class="form-input" id="incomeDate" required>
                </div>
                <button type="submit" class="submit-btn">Add Income</button>
            </form>
        </div>
    </div>

    <script>
        let currentPeriod = 'monthly';
        let analyticsPeriod = 'monthly';
        let charts = {};
        let customStartDate = '';
        let customEndDate = '';
        
        const categoryIcons = {
            'Food': '🍔',
            'Transport': '🚗',
            'Utilities': '💡',
            'Entertainment': '🎬',
            'Shopping': '🛍️',
            'Healthcare': '🏥',
            'Miscellaneous': '📦'
        };
        
        const categoryColors = {
            'Food': '#fb923c',
            'Transport': '#4ade80',
            'Utilities': '#60a5fa',
            'Entertainment': '#a78bfa',
            'Shopping': '#f472b6',
            'Healthcare': '#f87171',
            'Miscellaneous': '#fbbf24'
        };

        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('date').valueAsDate = new Date();
            document.getElementById('incomeDate').valueAsDate = new Date();
            loadProfiles();
            loadCategories();
            updateDashboard();
            loadRecentTransactions();
        });

        function showToast(message, isError = false) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast active' + (isError ? ' error' : '');
            setTimeout(() => toast.className = 'toast', 3000);
        }

        async function loadProfiles() {
            const response = await fetch('/api/profiles');
            const profiles = await response.json();
            
            const dropdown = document.getElementById('profileDropdown');
            dropdown.innerHTML = '';
            
            profiles.forEach(profile => {
                const btn = document.createElement('button');
                btn.className = 'profile-option' + (profile.is_current ? ' active' : '');
                btn.textContent = profile.name;
                btn.onclick = (e) => {
                    e.stopPropagation();
                    switchProfile(profile.id);
                };
                dropdown.appendChild(btn);
                
                if (profile.is_current) {
                    document.getElementById('userName').textContent = profile.name;
                    document.getElementById('profileName').value = profile.name;
                }
            });
        }

        function toggleProfileDropdown() {
            document.getElementById('profileDropdown').classList.toggle('active');
        }

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.profile-switcher')) {
                document.getElementById('profileDropdown').classList.remove('active');
            }
        });

        async function switchProfile(profileId) {
            await fetch('/api/profile/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile_id: profileId })
            });
            location.reload();
        }

        async function updateProfileName() {
            const name = document.getElementById('profileName').value.trim();
            if (!name) return;
            
            const response = await fetch('/api/profile/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
            
            if (response.ok) {
                showToast('Profile name updated!');
                loadProfiles();
            }
        }

        function switchSection(section) {
            const sections = ['dashboard', 'expenses', 'charts', 'groups', 'settings'];
            sections.forEach(s => {
                const el = document.getElementById(s + 'Section');
                if (el) el.classList.remove('active');
            });
            
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            
            const sectionEl = document.getElementById(section + 'Section');
            if (sectionEl) sectionEl.classList.add('active');
            
            const navItems = document.querySelectorAll('.nav-item');
            const navMap = { dashboard: 0, expenses: 1, groups: 3, settings: 4 };
            if (navMap[section] !== undefined) {
                navItems[navMap[section]].classList.add('active');
            }
            
            if (section === 'expenses') loadAllTransactions();
            if (section === 'charts') loadAnalytics();
            if (section === 'groups') loadBudgets();
            if (section === 'settings') {
                renderCategoryList();
                loadIncome();
            }
        }

        function openAddModal() {
            document.getElementById('addModal').classList.add('active');
        }

        function closeAddModal() {
            document.getElementById('addModal').classList.remove('active');
        }

        function switchModalTab(tab, btn) {
            document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
            btn.classList.add('active');
            
            if (tab === 'expense') {
                document.getElementById('expenseForm').style.display = 'block';
                document.getElementById('incomeForm').style.display = 'none';
            } else {
                document.getElementById('expenseForm').style.display = 'none';
                document.getElementById('incomeForm').style.display = 'block';
            }
        }

        function selectPayment(el) {
            document.querySelectorAll('.payment-option').forEach(p => p.classList.remove('selected'));
            el.classList.add('selected');
            document.getElementById('paymentMethod').value = el.dataset.method;
        }

        async function loadCategories() {
            const response = await fetch('/api/categories');
            const categories = await response.json();
            
            const select = document.getElementById('category');
            select.innerHTML = '<option value="">Select category...</option>';
            
            categories.forEach(cat => {
                const option = document.createElement('option');
                option.value = cat.name;
                option.textContent = cat.name;
                select.appendChild(option);
            });
        }

        async function updateDashboard() {
            const response = await fetch(`/api/summary?period=monthly`);
            const data = await response.json();
            
            const spent = data.total_expenses;
            const budget = data.total_budget || spent * 1.5;
            const remaining = Math.max(0, budget - spent);
            const percentage = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
            
            document.getElementById('spentAmount').textContent = spent.toFixed(0);
            document.getElementById('budgetAmount').textContent = budget.toFixed(0);
            document.getElementById('remainingAmount').textContent = remaining.toFixed(0);
            document.getElementById('usedPercentage').textContent = percentage.toFixed(0) + '%';
            
            const circumference = 427;
            const offset = circumference - (percentage / 100) * circumference;
            document.getElementById('progressCircle').style.strokeDashoffset = offset;
            
            // Update category chart
            updateCategoryChart(data.by_category || {});
            
            // Update budget status
            updateBudgetStatus(data.by_category || {});
        }

        function updateCategoryChart(categoryData) {
            const ctx = document.getElementById('categoryDonutChart').getContext('2d');
            
            if (charts.categoryDonut) charts.categoryDonut.destroy();
            
            const labels = Object.keys(categoryData);
            const values = Object.values(categoryData);
            const colors = labels.map(l => categoryColors[l] || '#6b7280');
            
            if (labels.length === 0) {
                labels.push('No Data');
                values.push(1);
                colors.push('#3d4a6b');
            }
            
            charts.categoryDonut = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors,
                        borderWidth: 0,
                        cutout: '65%'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: '#94a3b8',
                                padding: 15,
                                usePointStyle: true,
                                font: { size: 11, weight: '500' }
                            }
                        }
                    }
                }
            });
        }

        async function updateBudgetStatus(categorySpending) {
            const budgetsResp = await fetch('/api/budgets');
            const budgets = await budgetsResp.json();
            
            const statusContainer = document.getElementById('budgetStatus');
            statusContainer.innerHTML = '';
            
            let overCount = 0;
            let underCount = 0;
            
            for (const [cat, spent] of Object.entries(categorySpending)) {
                const budget = budgets.categories && budgets.categories[cat] || 0;
                if (budget > 0) {
                    if (spent > budget) overCount++;
                    else underCount++;
                }
            }
            
            if (overCount > 0) {
                statusContainer.innerHTML += `
                    <div class="status-item">
                        <span class="status-dot over"></span>
                        <span class="status-label over">${overCount} OVER BUDGET</span>
                    </div>
                `;
            }
            
            if (underCount > 0) {
                statusContainer.innerHTML += `
                    <div class="status-item">
                        <span class="status-dot under"></span>
                        <span class="status-label under">${underCount} UNDER BUDGET</span>
                    </div>
                `;
            }
        }

        async function loadRecentTransactions() {
            const response = await fetch('/api/expenses');
            const expenses = await response.json();
            
            const container = document.getElementById('recentTransactions');
            container.innerHTML = '';
            
            expenses.slice(0, 5).forEach(exp => {
                const iconClass = exp.category.toLowerCase().replace(/\\s+/g, '');
                container.innerHTML += `
                    <div class="transaction-item">
                        <div class="transaction-icon ${iconClass}">
                            ${categoryIcons[exp.category] || '📦'}
                        </div>
                        <div class="transaction-details">
                            <div class="transaction-title">${exp.description || exp.category}</div>
                            <div class="transaction-subtitle">${exp.category} • ${exp.date}</div>
                        </div>
                        <div class="transaction-amount expense">-₹${exp.amount.toFixed(0)}</div>
                    </div>
                `;
            });
        }

        async function loadAllTransactions() {
            let url = `/api/expenses`;
            const response = await fetch(url);
            const expenses = await response.json();
            
            const container = document.getElementById('allTransactions');
            container.innerHTML = '';
            
            expenses.forEach(exp => {
                const iconClass = exp.category.toLowerCase().replace(/\\s+/g, '');
                container.innerHTML += `
                    <div class="transaction-item">
                        <div class="transaction-icon ${iconClass}">
                            ${categoryIcons[exp.category] || '📦'}
                        </div>
                        <div class="transaction-details">
                            <div class="transaction-title">${exp.description || exp.category}</div>
                            <div class="transaction-subtitle">${exp.category} • ${exp.paymentMethod} • ${exp.date}</div>
                        </div>
                        <div class="transaction-amount expense">-₹${exp.amount.toFixed(0)}</div>
                    </div>
                `;
            });
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

            const response = await fetch('/api/expenses', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(expense)
            });

            if (response.ok) {
                showToast('Expense added successfully!');
                this.reset();
                document.getElementById('date').valueAsDate = new Date();
                document.querySelectorAll('.payment-option').forEach(p => p.classList.remove('selected'));
                closeAddModal();
                updateDashboard();
                loadRecentTransactions();
            }
        });

        document.getElementById('incomeForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const income = {
                amount: parseFloat(document.getElementById('incomeAmount').value),
                source: document.getElementById('incomeSource').value,
                type: document.getElementById('incomeType').value,
                date: document.getElementById('incomeDate').value
            };

            const response = await fetch('/api/income', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(income)
            });

            if (response.ok) {
                showToast('Income added successfully!');
                this.reset();
                document.getElementById('incomeDate').valueAsDate = new Date();
                closeAddModal();
                updateDashboard();
            }
        });

        async function loadIncome() {
            const response = await fetch('/api/income');
            const incomes = await response.json();
            
            const container = document.getElementById('incomeList');
            container.innerHTML = '';
            
            incomes.slice(0, 10).forEach(inc => {
                container.innerHTML += `
                    <div class="transaction-item">
                        <div class="transaction-icon income">💰</div>
                        <div class="transaction-details">
                            <div class="transaction-title">${inc.source}</div>
                            <div class="transaction-subtitle">${inc.type} • ${inc.date}</div>
                        </div>
                        <div class="transaction-amount income">+₹${inc.amount.toFixed(0)}</div>
                    </div>
                `;
            });
        }

        function setPeriod(period, btn) {
            currentPeriod = period;
            document.querySelectorAll('#expensesSection .period-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            if (period === 'custom') {
                document.getElementById('dateRange').classList.add('active');
            } else {
                document.getElementById('dateRange').classList.remove('active');
                loadAllTransactions();
            }
        }

        function applyCustomRange() {
            customStartDate = document.getElementById('startDate').value;
            customEndDate = document.getElementById('endDate').value;
            if (customStartDate && customEndDate) {
                loadAllTransactions();
            }
        }

        function setAnalyticsPeriod(period, btn) {
            analyticsPeriod = period;
            document.querySelectorAll('#chartsSection .period-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadAnalytics();
        }

        async function loadAnalytics() {
            const response = await fetch(`/api/analytics?period=${analyticsPeriod}`);
            const data = await response.json();
            
            const statsGrid = document.getElementById('statsGrid');
            statsGrid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-label">Total Expenses</div>
                    <div class="stat-value">₹${data.total_expenses.toFixed(0)}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg Daily</div>
                    <div class="stat-value alt">₹${data.avg_daily.toFixed(0)}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Top Category</div>
                    <div class="stat-value" style="font-size: 14px; color: var(--accent-orange);">${data.highest_category || 'N/A'}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Transactions</div>
                    <div class="stat-value alt">${data.transaction_count}</div>
                </div>
            `;
            
            // Trend Chart
            if (charts.trend) charts.trend.destroy();
            const ctxTrend = document.getElementById('trendChart').getContext('2d');
            charts.trend = new Chart(ctxTrend, {
                type: 'line',
                data: {
                    labels: data.trend_labels.slice(-14),
                    datasets: [{
                        label: 'Spending',
                        data: data.trend_data.slice(-14),
                        borderColor: '#4ade80',
                        backgroundColor: 'rgba(74, 222, 128, 0.1)',
                        tension: 0.4,
                        fill: true,
                        borderWidth: 2,
                        pointRadius: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { 
                            display: false
                        },
                        y: { 
                            display: false
                        }
                    }
                }
            });
            
            // Payment Chart
            if (charts.payment) charts.payment.destroy();
            const ctxPayment = document.getElementById('paymentChart').getContext('2d');
            charts.payment = new Chart(ctxPayment, {
                type: 'doughnut',
                data: {
                    labels: Object.keys(data.by_payment),
                    datasets: [{
                        data: Object.values(data.by_payment),
                        backgroundColor: ['#4ade80', '#60a5fa', '#a78bfa', '#fb923c'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { 
                        legend: { 
                            position: 'bottom',
                            labels: { color: '#94a3b8', font: { size: 11 } }
                        } 
                    }
                }
            });
            
            // Income vs Expense Chart
            if (charts.incomeExpense) charts.incomeExpense.destroy();
            const ctxIncExp = document.getElementById('incomeExpenseChart').getContext('2d');
            charts.incomeExpense = new Chart(ctxIncExp, {
                type: 'bar',
                data: {
                    labels: data.income_expense_labels,
                    datasets: [{
                        label: 'Income',
                        data: data.income_data,
                        backgroundColor: '#4ade80'
                    }, {
                        label: 'Expenses',
                        data: data.expense_data,
                        backgroundColor: '#f87171'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { 
                        legend: { 
                            position: 'bottom',
                            labels: { color: '#94a3b8', font: { size: 11 } }
                        } 
                    },
                    scales: {
                        x: { 
                            grid: { display: false },
                            ticks: { color: '#64748b' }
                        },
                        y: { 
                            grid: { color: '#2a3352' },
                            ticks: { color: '#64748b' }
                        }
                    }
                }
            });
        }

        async function loadBudgets() {
            const response = await fetch('/api/budgets');
            const budgets = await response.json();
            document.getElementById('monthlyBudget').value = budgets.monthly || '';

            const container = document.getElementById('categoryBudgets');
            container.innerHTML = '';

            const cats = await fetch('/api/categories').then(r => r.json());
            cats.forEach(cat => {
                const val = budgets.categories && budgets.categories[cat.name] || '';
                container.innerHTML += `
                    <div class="form-group">
                        <label class="form-label">${cat.name}</label>
                        <input type="number" class="form-input" id="budget-${cat.name}" value="${val}" placeholder="0.00" step="0.01">
                    </div>
                `;
            });

            // Budget Overview
            const overview = document.getElementById('budgetOverview');
            const summaryResp = await fetch('/api/summary?period=monthly');
            const summary = await summaryResp.json();

            overview.innerHTML = '';
            for (const [cat, spent] of Object.entries(summary.by_category || {})) {
                const budget = budgets.categories && budgets.categories[cat] || 0;
                const percentage = budget > 0 ? (spent / budget * 100) : 0;
                let colorClass = 'safe';
                if (percentage > 100) colorClass = 'danger';
                else if (percentage > 80) colorClass = 'warning';

                overview.innerHTML += `
                    <div class="budget-progress-item">
                        <div class="budget-progress-header">
                            <span class="budget-progress-label">${cat}</span>
                            <span class="budget-progress-amount" style="color: var(--accent-${colorClass === 'safe' ? 'green' : colorClass === 'warning' ? 'orange' : 'red'})">₹${spent.toFixed(0)} / ₹${budget.toFixed(0)}</span>
                        </div>
                        <div class="budget-progress-bar">
                            <div class="budget-progress-fill ${colorClass}" style="width: ${Math.min(percentage, 100)}%"></div>
                        </div>
                    </div>
                `;
            }
            
            // Load credit data
            loadCreditData();
        }

        async function saveMonthlyBudget() {
            const amount = parseFloat(document.getElementById('monthlyBudget').value) || 0;
            const response = await fetch('/api/budgets/monthly', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount })
            });

            if (response.ok) {
                showToast('Monthly budget saved!');
                updateDashboard();
            }
        }

        async function saveCategoryBudgets() {
            const cats = await fetch('/api/categories').then(r => r.json());
            const budgets = {};
            cats.forEach(cat => {
                const input = document.getElementById(`budget-${cat.name}`);
                if (input && input.value) budgets[cat.name] = parseFloat(input.value);
            });

            const response = await fetch('/api/budgets/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ budgets })
            });

            if (response.ok) {
                showToast('Category budgets saved!');
                loadBudgets();
            }
        }

        async function uploadStatement() {
            const file = document.getElementById('statementFile').files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/credit/upload', {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                showToast('Statement uploaded!');
                loadCreditData();
                updateDashboard();
            } else {
                showToast('Error uploading statement', true);
            }
        }

        async function loadCreditData() {
            const response = await fetch('/api/credit/statements');
            const statements = await response.json();
            
            const container = document.getElementById('creditList');
            container.innerHTML = '';

            statements.slice(0, 5).forEach(stmt => {
                container.innerHTML += `
                    <div class="transaction-item">
                        <div class="transaction-icon shopping">💳</div>
                        <div class="transaction-details">
                            <div class="transaction-title">${stmt.merchant}</div>
                            <div class="transaction-subtitle">${stmt.category} • ${stmt.date}</div>
                        </div>
                        <div class="transaction-amount expense">-₹${stmt.amount.toFixed(0)}</div>
                    </div>
                `;
            });
        }

        async function addCategory() {
            const name = document.getElementById('newCategory').value.trim();
            if (!name) return;

            const response = await fetch('/api/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });

            if (response.ok) {
                document.getElementById('newCategory').value = '';
                showToast('Category added!');
                loadCategories();
                renderCategoryList();
            }
        }

        async function renderCategoryList() {
            const response = await fetch('/api/categories');
            const categories = await response.json();
            const container = document.getElementById('categoryList');
            container.innerHTML = '';

            categories.forEach(cat => {
                container.innerHTML += `
                    <div class="category-tag">
                        ${categoryIcons[cat.name] || '📦'} ${cat.name}
                        <button class="category-delete" onclick="deleteCategory('${cat.name}')">×</button>
                    </div>
                `;
            });
        }

        async function deleteCategory(name) {
            if (!confirm(`Delete category "${name}"?`)) return;
            const response = await fetch(`/api/categories/${name}`, { method: 'DELETE' });
            if (response.ok) {
                loadCategories();
                renderCategoryList();
            }
        }

        function exportData() {
            window.location.href = '/api/export';
        }
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

@app.route('/api/profile/theme', methods=['POST'])
def update_theme():
    theme = request.json['theme']
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('UPDATE profiles SET theme = ? WHERE id = ?', (theme, profile_id))
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

    c.execute('SELECT id, name FROM categories WHERE profile_id = ? ORDER BY name', (profile_id,))
    categories = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
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

@app.route('/api/income', methods=['GET', 'POST'])
def income():
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    if request.method == 'POST':
        inc = request.json
        c.execute('''INSERT INTO income (profile_id, amount, source, type, date, timestamp)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (profile_id, inc['amount'], inc['source'], inc['type'],
                   inc['date'], datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    c.execute('SELECT * FROM income WHERE profile_id = ? ORDER BY date DESC', (profile_id,))
    incomes = []
    for row in c.fetchall():
        incomes.append({
            'id': row[0], 'amount': row[2], 'source': row[3],
            'type': row[4], 'date': row[5]
        })
    conn.close()
    return jsonify(incomes)

@app.route('/api/summary')
def summary():
    profile_id = get_profile_id()
    period = request.args.get('period', 'monthly')
    start_custom = request.args.get('start')
    end_custom = request.args.get('end')

    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    today = date.today()
    if period == 'daily':
        start_date = today.isoformat()
    elif period == 'monthly':
        start_date = today.replace(day=1).isoformat()
    elif period == 'yearly':
        start_date = today.replace(month=1, day=1).isoformat()
    elif period == 'custom' and start_custom and end_custom:
        start_date = start_custom
        today = date.fromisoformat(end_custom)
    else:
        start_date = '1970-01-01'

    c.execute('SELECT SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ?',
              (profile_id, start_date, today.isoformat()))
    total_expenses = c.fetchone()[0] or 0

    c.execute('SELECT SUM(amount) FROM income WHERE profile_id = ? AND date >= ? AND date <= ?',
              (profile_id, start_date, today.isoformat()))
    total_income = c.fetchone()[0] or 0

    c.execute('SELECT category, SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ? GROUP BY category',
              (profile_id, start_date, today.isoformat()))
    by_category = {row[0]: row[1] for row in c.fetchall()}

    c.execute("SELECT amount FROM budgets WHERE profile_id = ? AND category = 'MONTHLY' AND period = 'monthly'", (profile_id,))
    result = c.fetchone()
    total_budget = result[0] if result else 0

    conn.close()

    return jsonify({
        'total_expenses': total_expenses,
        'total_income': total_income,
        'total_budget': total_budget,
        'by_category': by_category
    })

@app.route('/api/analytics')
def analytics():
    profile_id = get_profile_id()
    period = request.args.get('period', 'monthly')
    start_custom = request.args.get('start')
    end_custom = request.args.get('end')

    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    today = date.today()
    if period == 'daily':
        start_date = today.isoformat()
        days = 1
    elif period == 'monthly':
        start_date = today.replace(day=1).isoformat()
        days = (today - today.replace(day=1)).days + 1
    elif period == 'yearly':
        start_date = today.replace(month=1, day=1).isoformat()
        days = (today - today.replace(month=1, day=1)).days + 1
    elif period == 'custom' and start_custom and end_custom:
        start_date = start_custom
        today = date.fromisoformat(end_custom)
        days = (today - date.fromisoformat(start_date)).days + 1
    else:
        start_date = '1970-01-01'
        c.execute('SELECT MIN(date) FROM expenses WHERE profile_id = ?', (profile_id,))
        first_date = c.fetchone()[0]
        days = (today - date.fromisoformat(first_date)).days + 1 if first_date else 1

    c.execute('SELECT SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ?',
              (profile_id, start_date, today.isoformat()))
    total_expenses = c.fetchone()[0] or 0

    c.execute('SELECT COUNT(*) FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ?',
              (profile_id, start_date, today.isoformat()))
    transaction_count = c.fetchone()[0]

    c.execute('SELECT category, SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ? GROUP BY category',
              (profile_id, start_date, today.isoformat()))
    by_category = {row[0]: row[1] for row in c.fetchall()}
    highest_category = max(by_category, key=by_category.get) if by_category else None

    c.execute('SELECT payment_method, SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ? GROUP BY payment_method',
              (profile_id, start_date, today.isoformat()))
    by_payment = {row[0]: row[1] for row in c.fetchall()}

    c.execute('SELECT date, SUM(amount) FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ? GROUP BY date ORDER BY date',
              (profile_id, start_date, today.isoformat()))
    trend_data = {row[0]: row[1] for row in c.fetchall()}

    current = date.fromisoformat(start_date)
    trend_labels = []
    trend_values = []
    while current <= today:
        trend_labels.append(current.strftime('%Y-%m-%d'))
        trend_values.append(trend_data.get(current.isoformat(), 0))
        current += timedelta(days=1)

    c.execute('''SELECT strftime('%Y-%m', date) as month, SUM(amount) 
                 FROM expenses WHERE profile_id = ? AND date >= ? AND date <= ? GROUP BY month ORDER BY month''',
              (profile_id, start_date, today.isoformat()))
    expense_by_month = {row[0]: row[1] for row in c.fetchall()}

    c.execute('''SELECT strftime('%Y-%m', date) as month, SUM(amount) 
                 FROM income WHERE profile_id = ? AND date >= ? AND date <= ? GROUP BY month ORDER BY month''',
              (profile_id, start_date, today.isoformat()))
    income_by_month = {row[0]: row[1] for row in c.fetchall()}

    all_months = sorted(set(list(expense_by_month.keys()) + list(income_by_month.keys())))
    income_data = [income_by_month.get(m, 0) for m in all_months]
    expense_data = [expense_by_month.get(m, 0) for m in all_months]

    conn.close()

    return jsonify({
        'total_expenses': total_expenses,
        'avg_daily': total_expenses / days if days > 0 else 0,
        'transaction_count': transaction_count,
        'highest_category': highest_category,
        'by_category': by_category,
        'by_payment': by_payment,
        'trend_labels': trend_labels,
        'trend_data': trend_values,
        'income_expense_labels': all_months,
        'income_data': income_data,
        'expense_data': expense_data
    })

@app.route('/api/budgets', methods=['GET'])
def get_budgets():
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    c.execute("SELECT amount FROM budgets WHERE profile_id = ? AND category = 'MONTHLY' AND period = 'monthly'", (profile_id,))
    result = c.fetchone()
    monthly = result[0] if result else 0

    c.execute("SELECT category, amount FROM budgets WHERE profile_id = ? AND category != 'MONTHLY'", (profile_id,))
    categories = {row[0]: row[1] for row in c.fetchall()}

    conn.close()
    return jsonify({'monthly': monthly, 'categories': categories})

@app.route('/api/budgets/monthly', methods=['POST'])
def set_monthly_budget():
    profile_id = get_profile_id()
    amount = request.json['amount']
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    c.execute("DELETE FROM budgets WHERE profile_id = ? AND category = 'MONTHLY' AND period = 'monthly'", (profile_id,))
    c.execute("INSERT INTO budgets (profile_id, category, amount, period) VALUES (?, 'MONTHLY', ?, 'monthly')", (profile_id, amount))

    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/budgets/categories', methods=['POST'])
def set_category_budgets():
    profile_id = get_profile_id()
    budgets = request.json['budgets']
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    for category, amount in budgets.items():
        c.execute("DELETE FROM budgets WHERE profile_id = ? AND category = ? AND period = 'monthly'", (profile_id, category))
        c.execute("INSERT INTO budgets (profile_id, category, amount, period) VALUES (?, ?, ?, 'monthly')", (profile_id, category, amount))

    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/credit/upload', methods=['POST'])
def upload_credit_statement():
    profile_id = get_profile_id()
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and file.filename.endswith('.csv'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        conn = sqlite3.connect('expenses.db')
        c = conn.cursor()

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    date_str = row.get('Date', row.get('date', ''))
                    merchant = row.get('Merchant', row.get('merchant', row.get('Description', '')))
                    amount = float(row.get('Amount', row.get('amount', '0')).replace(',', '').replace('₹', ''))
                    category = row.get('Category', row.get('category', 'Miscellaneous'))

                    c.execute('''INSERT INTO credit_statements 
                                (profile_id, card_name, amount, merchant, category, date, uploaded_date)
                                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                              (profile_id, filename, abs(amount), merchant, category, date_str, datetime.now().isoformat()))

                    c.execute('''INSERT INTO expenses 
                                (profile_id, amount, description, payment_method, category, date, timestamp)
                                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                              (profile_id, abs(amount), merchant, 'Credit Card', category, date_str, datetime.now().isoformat()))
                except Exception as e:
                    print(f"Error processing row: {e}")
                    continue

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    return jsonify({'error': 'Invalid file format'}), 400

@app.route('/api/credit/statements')
def get_credit_statements():
    profile_id = get_profile_id()
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()

    c.execute('SELECT * FROM credit_statements WHERE profile_id = ? ORDER BY date DESC', (profile_id,))
    statements = []
    for row in c.fetchall():
        statements.append({
            'id': row[0], 'card_name': row[2], 'amount': row[3],
            'merchant': row[4], 'category': row[5], 'date': row[6]
        })

    conn.close()
    return jsonify(statements)

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

    c.execute('SELECT date, amount, source, type FROM income WHERE profile_id = ? ORDER BY date DESC', (profile_id,))
    for row in c.fetchall():
        writer.writerow(['Income', row[0], row[1], row[2], row[3]])

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