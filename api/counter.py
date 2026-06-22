import os
import psycopg2
import json
import urllib.parse
import urllib.request
from flask import Flask, jsonify, request

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

# Hàm gửi báo cáo ngầm qua Telegram Bot API
def send_telegram_report(current_views, environment):
    # Chỉ nhắn tin khi số view đạt các mốc chẵn chia hết cho 10 để tránh spam
        
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    # Nếu chưa cấu hình đủ biến môi trường trên Vercel thì bỏ qua
    if not bot_token or not chat_id:
        return

    # Soạn nội dung tin nhắn Markdown
    message_text = (
        f"📊 *[PORTFOLIO ANALYTICS]*\n\n"
        f"🚀 *Cột mốc mới:* {current_views} lượt xem!\n"
        f"🌐 *Môi trường:* `{environment}`\n\n"
        f"🔥 _Keep moving forward, Lam!_"
    )
    
    # Đường dẫn API gửi tin nhắn của Telegram
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Tạo payload dữ liệu dạng JSON
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown"  # Kích hoạt định dạng chữ đậm/nghiêng
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req) as response:
            response.read() # Đọc phản hồi ngầm
    except Exception as e:
        print(f"Failed to send Telegram notification: {str(e)}")

@app.route('/api/counter', methods=['GET', 'POST'])
def handle_analytics():
    # Tự động cách ly môi trường (Ý tưởng 3)
    is_production = os.environ.get('VERCEL_ENV') == 'production'
    environment_name = "Production" if is_production else "Local-Dev"
    
    metric = 'visitor_count' if is_production else 'dev_visitor_count'

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            cursor.execute("""
                INSERT INTO site_analytics (metric_name, value) 
                VALUES (%s, 1)
                ON CONFLICT (metric_name) 
                DO UPDATE SET value = site_analytics.value + 1
                RETURNING value;
            """, (metric,))
            new_count = cursor.fetchone()[0]
            conn.commit()
            
            # Kích hoạt gửi báo cáo sang Telegram (Ý tưởng 1)
            send_telegram_report(new_count, environment_name)
        else:
            cursor.execute("SELECT value FROM site_analytics WHERE metric_name = %s;", (metric,))
            result = cursor.fetchone()
            new_count = result[0] if result else 0
            
        cursor.close()
        return jsonify({"success": True, "environment": environment_name, "value": new_count}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404