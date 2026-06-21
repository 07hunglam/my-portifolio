import os
import psycopg2
from flask import Flask, jsonify

app = Flask(__name__)

def get_db_connection():
    # Gọi chuỗi kết nối an toàn từ biến môi trường của Vercel
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

@app.route('/api/counter', methods=['POST'])
def increment_counter():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Tăng biến đếm và lấy giá trị mới ngay trong 1 truy vấn (Atomic)
        cursor.execute("""
            INSERT INTO site_analytics (metric_name, value) 
            VALUES ('visitor_count', 1)
            ON CONFLICT (metric_name) 
            DO UPDATE SET value = site_analytics.value + 1
            RETURNING value;
        """)
        
        new_count = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        
        return jsonify({"success": True, "visitor_count": new_count}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()