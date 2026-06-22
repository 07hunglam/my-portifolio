import os
import psycopg2
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

def send_telegram_report(current_views, environment):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    # 1. BẮT BỆNH VERCEL: In ra log xem Vercel có đang đọc được biến không
    print("--- HỆ THỐNG KIỂM TRA TELEGRAM BOT ---")
    print(f"Trạng thái Token: {'Đã nhận' if bot_token else 'TRỐNG (Lỗi cấu hình)'}")
    print(f"Trạng thái Chat ID: {'Đã nhận' if chat_id else 'TRỐNG (Lỗi cấu hình)'}")
    
    if not bot_token or not chat_id:
        print("=> HỦY GỬI: Không tìm thấy khóa bảo mật.")
        return

    # 2. CHUẨN HÓA NỘI DUNG: Dùng triple-quotes (chuỗi 3 ngoặc kép) để chứa nguyên khối văn bản
    message_text = f"""📊 *[PORTFOLIO ANALYTICS]*

🚀 *Cột mốc mới:* {current_views} lượt xem!
🌐 *Môi trường:* `{environment}`

🔥 _Keep moving forward, Lam!_"""
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    
    try:
        # 3. KÍCH HOẠT MẠNG: Gọi sang Telegram và in kết quả trả về
        response = requests.post(url, json=payload, timeout=5)
        print(f"=> Kết nối Telegram (Status {response.status_code}): {response.text}")
    except Exception as e:
        print(f"=> LỖI MẠNG: {str(e)}")

@app.route('/api/counter', methods=['GET', 'POST'])
def handle_analytics():
    # Ép Vercel luôn ghi nhận là Production để số view nhảy đồng bộ trên mọi tên miền
    is_on_vercel = os.environ.get('VERCEL_ENV') is not None
    environment_name = "Production" if is_on_vercel else "Local-Dev"
    metric = 'visitor_count' if is_on_vercel else 'dev_visitor_count'

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
            
            # Khởi động quy trình gửi tin nhắn
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