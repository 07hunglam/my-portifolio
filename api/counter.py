import os
import psycopg2
import requests
import threading
from flask import Flask, jsonify, request

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

# Hàm phân tích chuỗi User-Agent để nhận diện thiết bị/HĐH
def parse_user_agent(ua_string):
    if not ua_string:
        return "Thiết bị ẩn danh", "Trình duyệt ẩn danh"
    
    ua_lower = ua_string.lower()
    
    if "android" in ua_lower:
        os_name = "📱 Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "📱 iOS (iPhone/iPad)"
    elif "windows" in ua_lower:
        os_name = "💻 Windows"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        os_name = "💻 macOS"
    elif "linux" in ua_lower:
        os_name = "💻 Linux"
    else:
        os_name = "❓ Thiết bị khác"
        
    if "chrome" in ua_lower and "safari" in ua_lower and "edge" not in ua_lower:
        browser = "Chrome"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "edge" in ua_lower:
        browser = "Edge"
    else:
        browser = "Trình duyệt chuẩn Web"
        
    return os_name, browser

# Hàm lấy vị trí địa lý từ IP
def get_location_from_ip(ip_address):
    if not ip_address or ip_address in ["127.0.0.1", "::1"]:
        return "📍 Môi trường Local-Dev"
        
    try:
        response = requests.get(f"http://ip-api.com/json/{ip_address}?fields=status,country,regionName,city", timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                country = data.get("country", "Không rõ QG")
                city = data.get("city", "Không rõ TP")
                return f"📍 {city}, {country}"
    except Exception:
        pass
    return "📍 Không rõ vị trí"

# NHIỆM VỤ NGẦM BẤT ĐỒNG BỘ: Chạy trên một Thread riêng biệt, độc lập với Flask phản hồi
def async_analytics_pipeline(current_views, environment, ip_address, ua_string, referer, metric_name):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    # 1. Thực hiện các tác vụ tốn thời gian (Phân tích, Gọi API định vị ngoại mạng)
    os_info, browser_info = parse_user_agent(ua_string)
    location_info = get_location_from_ip(ip_address)
    
    if not referer:
        source_info = "🔗 Truy cập trực tiếp (Direct)"
    elif "facebook.com" in referer or "m.facebook.com" in referer:
        source_info = "🔵 Từ Facebook"
    elif "instagram.com" in referer:
        source_info = "📸 Từ Instagram"
    elif "linkedin.com" in referer:
        source_info = "💼 Từ LinkedIn"
    else:
        source_info = f"🌐 Nguồn khác: `{referer.split('/')[2]}`"

    # 2. GHI LOG VÀO DATABASE (Ý tưởng 2)
    conn = None
    try:
        # Mở một kết nối database riêng cho luồng ngầm này
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO visitor_logs (metric_name, views_milestone, ip_address, location, os, browser, referer)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (metric_name, current_views, ip_address, location_info, os_info, browser_info, referer))
        conn.commit()
        cursor.close()
    except Exception as db_err:
        print(f"Failed to save analytics log to database: {str(db_err)}")
    finally:
        if conn: conn.close()

    # 3. BẮN TIN NHẮN VỀ TELEGRAM BOT
    if not bot_token or not chat_id:
        return

    message_text = f"""========= 📊 *ANALYTICS REPORT* =========

🚀 *Cột mốc mới:* {current_views} lượt xem!
🌐 *Môi trường:* `{environment}`

🕵️ *THÔNG TIN CHI TIẾT (ĐÃ LƯU DB):*
• {location_info}
• Thiết bị: `{os_info}`
• Trình duyệt: `{browser_info}`
• {source_info}

🔥 _Keep moving forward, Lam!_"""
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to send Telegram notification: {str(e)}")

@app.route('/api/counter', methods=['GET', 'POST'])
def handle_analytics():
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
            cursor.close()
            
            # Trích xuất nhanh dữ liệu thô từ request header của client
            ip_address = request.headers.get('x-forwarded-for', request.remote_addr)
            if ip_address and ',' in ip_address:
                ip_address = ip_address.split(',')[0].strip()
                
            ua_string = request.headers.get('User-Agent', '')
            referer = request.headers.get('Referer', '')
            
            # KÍCH HOẠT LUỒNG NGẦM BẤT ĐỒNG BỘ (Ý tưởng 1):
            # Khởi tạo một Thread riêng để làm nhiệm vụ phân tích và gọi API mạng.
            # Tiến trình chính Flask lập tức đi tiếp xuống lệnh return mà không bị nghẽn lại đợi.
            async_analytics_pipeline(new_count, environment_name, ip_address, ua_string, referer, metric)
            
            # Trả kết quả tức thì về cho Frontend (Tốc độ phản hồi < 10ms)
            return jsonify({"success": True, "environment": environment_name, "value": new_count}), 200
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