import os
import psycopg2
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

# Hàm gửi báo cáo ngầm qua Telegram Bot API (Nâng cấp lên thư viện requests)
def send_telegram_report(current_views, environment):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    # Nếu chưa cấu hình đủ biến môi trường trên Vercel thì bỏ qua
    if not bot_token or not chat_id:
        return

    # Soạn nội dung tin nhắn dạng Markdown
   # Sửa lại định dạng ghép chuỗi chuẩn Python
    message_text = (
        f"📊 *[PORTFOLIO ANALYTICS]*\n\n"
        "🚀 *Cột mốc mới:* {current_views} lượt xem!\n"
        "🌐 *Môi trường:* `{environment}`\n\n"
        "🔥 _Keep moving forward, Lam!_"
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    
    try:
        # Sử dụng requests.post giúp tự động xử lý gói tin và phân giải DNS IPv4/IPv6 chuẩn xác
        response = requests.post(url, json=payload, timeout=5)
        # Nếu Telegram trả về lỗi (ví dụ sai token/id), dòng này sẽ in log ra Vercel Logs để kiểm tra
        if response.status_code != 200:
            print(f"Telegram API Error: {response.text}")
    except Exception as e:
        print(f"Failed to send Telegram notification due to network error: {str(e)}")

@app.route('/api/counter', methods=['GET', 'POST'])
def handle_analytics():
    # Tự động cách ly môi trường
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
            
            # Kích hoạt gửi báo cáo sang Telegram
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