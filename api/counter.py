import os
import psycopg2
from flask import Flask, jsonify, request

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

# Cấu hình endpoint chấp nhận cả phương thức GET (Chỉ đọc) và POST (Tăng số)
@app.route('/api/counter', methods=['GET', 'POST'])
def handle_counter():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            # NẾU LÀ POST: Thực hiện tăng biến đếm nguyên tử
            cursor.execute("""
                INSERT INTO site_analytics (metric_name, value) 
                VALUES ('visitor_count', 1)
                ON CONFLICT (metric_name) 
                DO UPDATE SET value = site_analytics.value + 1
                RETURNING value;
            """)
            new_count = cursor.fetchone()[0]
            conn.commit()
        else:
            # NẾU LÀ GET: Chỉ thực hiện truy vấn SELECT lấy số lượng hiện tại, không thay đổi dữ liệu
            cursor.execute("SELECT value FROM site_analytics WHERE metric_name = 'visitor_count';")
            result = cursor.fetchone()
            new_count = result[0] if result else 0
            
        cursor.close()
        return jsonify({"success": True, "visitor_count": new_count}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404