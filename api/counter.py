import os
import psycopg2
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

# Hàm phân tích chuỗi User-Agent để nhận diện thiết bị/HĐH nhanh
def parse_user_agent(ua_string):
    if not ua_string:
        return "Thiết bị ẩn danh", "Trình duyệt ẩn danh"
    
    ua_lower = ua_string.lower()
    
    # Nhận diện Hệ điều hành / Thiết bị
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
        
    # Nhận diện Trình duyệt
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

# Hàm lấy vị trí địa lý từ IP của khách truy cập
def get_location_from_ip(ip_address):
    # Tránh tra cứu các IP chạy local (localhost)
    if not ip_address or ip_address in ["127.0.0.1", "::1"]:
        return "📍 Môi trường Local-Dev"
        
    try:
        # Sử dụng API miễn phí ip-api.com để lấy thông tin IP nhanh
        response = requests.get(f"http://ip-api.com/json/{ip_address}?fields=status,country,regionName,city", timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                country = data.get("country", "Không rõ QG")
                city = data.get("city", "Không rõ TP")
                return f"📍 {city}, {country}"
    except Exception:
        pass
    return "📍 Không rõ vị trí (Bị chặn/Ẩn danh)"

def send_telegram_report(current_views, environment, ip_address, ua_string, referer):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        return

    # 1. Thu thập dữ liệu phân tích chuyên sâu
    os_info, browser_info = parse_user_agent(ua_string)
    location_info = get_location_from_ip(ip_address)
    
    # 2. Xử lý nguồn truy cập (Referer)
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

    # 3. Thiết kế giao diện báo cáo chuyên nghiệp
    message_text = f"""📊 *[PORTFOLIO ADVANCED ANALYTICS]*

🚀 *Cột mốc mới:* {current_views} lượt xem!
🌐 *Môi trường:* `{environment}`

🕵️ *THÔNG TIN KHÁCH TRUY CẬP:*
• {location_info}
• Hệ điều hành: `{os_info}`
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
        print(f"Failed to send Advanced Telegram notification: {str(e)}")

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
            
            # Lấy các thông tin phân tích hệ thống từ Request Header
            # Vercel tự động chuyển tiếp IP thật của khách qua Header 'x-forwarded-for'
            ip_address = request.headers.get('x-forwarded-for', request.remote_addr)
            if ip_address and ',' in ip_address:
                ip_address = ip_address.split(',')[0].strip() # Lấy IP gốc đầu tiên nếu qua nhiều proxy
                
            ua_string = request.headers.get('User-Agent', '')
            referer = request.headers.get('Referer', '')
            
            # Kích hoạt gửi báo cáo phân tích chuyên sâu
            send_telegram_report(new_count, environment_name, ip_address, ua_string, referer)
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