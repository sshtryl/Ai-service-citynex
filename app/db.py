# ai-service/app/db.py
import psycopg2
import psycopg2.extras
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi database dari environment variables
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "aspirakita"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

def get_connection():
    """Mendapatkan koneksi database PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

def save_report(report_data: dict) -> dict:
    """
    Menyimpan laporan ke tabel reports.
    
    Report data expected keys:
    - user_id (wajib, akan diisi oleh backend setelah auth)
    - category_id
    - title
    - description
    - priority (low/medium/high/critical)
    - status (pending)
    - location
    - assigned_admin_id (opsional, bisa None)
    - latitude (opsional)
    - longitude (opsional)
    - ai_summary
    - fake_score
    - priority_score
    """
    conn = get_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        cursor = conn.cursor()
        
        # Query INSERT dengan RETURNING id
        query = """
            INSERT INTO reports (
                user_id,
                category_id,
                title,
                description,
                priority,
                status,
                location,
                assigned_admin_id,
                latitude,
                longitude,
                ai_summary,
                fake_score,
                priority_score,
                images,
                created_at,
                updated_at
            ) VALUES (
                %(user_id)s,
                %(category_id)s,
                %(title)s,
                %(description)s,
                %(priority)s,
                %(status)s,
                %(location)s,
                %(assigned_admin_id)s,
                %(latitude)s,
                %(longitude)s,
                %(ai_summary)s,
                %(fake_score)s,
                %(priority_score)s,
                %(images)s,
                NOW(),
                NOW()
            )
            RETURNING id
        """
        
        # Set default values jika tidak ada
        report_data.setdefault("status", "pending")
        report_data.setdefault("assigned_admin_id", None)
        report_data.setdefault("latitude", None)
        report_data.setdefault("longitude", None)
        report_data.setdefault("images", None)
        
        cursor.execute(query, report_data)
        report_id = cursor.fetchone()[0]
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Report saved successfully with ID: {report_id}")
        return {"success": True, "report_id": report_id}
        
    except Exception as e:
        print(f"❌ Error saving report: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return {"success": False, "error": str(e)}

def get_report_by_id(report_id: int):
    """Mengambil laporan berdasarkan ID"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = "SELECT * FROM reports WHERE id = %s"
        cursor.execute(query, (report_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return dict(result) if result else None
    except Exception as e:
        print(f"❌ Error fetching report: {e}")
        return None