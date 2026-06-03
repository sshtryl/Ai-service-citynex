# ai-service/app/ai_agent.py
import re
import json
import uuid
from datetime import datetime
import ollama
from typing import Optional

OLLAMA_HOST = "http://localhost:11434"
MODEL_NAME  = "tinyllama:1.1b"

client = ollama.Client(host=OLLAMA_HOST)

# ─── KATEGORI (sesuai DB report_categories) ───────────────────────────────────
CATEGORIES = {
    1: "Infrastruktur Jalan",
    2: "Lampu Jalan",
    3: "Sampah & Kebersihan",
    4: "Drainase & Saluran Air",
    5: "Lingkungan",
    6: "Lainnya",
}

CATEGORY_KEYWORDS = {
    1: ["jalan", "aspal", "lubang", "trotoar", "jembatan"],
    2: ["lampu", "penerangan", "gelap", "mati", "terang"],
    3: ["sampah", "kotor", "bau", "buang", "tumpukan"],
    4: ["drainase", "gorong", "saluran", "banjir", "genangan", "air"],
    5: ["pohon", "taman", "fasilitas", "lingkungan", "hijau"],
}

PRIORITY_MAP = {
    "critical": {"score": 95, "keywords": ["darurat", "bahaya", "kecelakaan", "korban", "parah sekali", "sangat parah"]},
    "high":     {"score": 75, "keywords": ["parah", "rusak parah", "membahayakan", "besar", "dalam"]},
    "medium":   {"score": 50, "keywords": ["rusak", "berlubang", "sedang", "cukup"]},
    "low":      {"score": 25, "keywords": ["ringan", "kecil", "sedikit", "kecil"]},
}


STEPS = [

    {
        "key":      "location",
        "question": "Di mana lokasi kejadiannya? Sebutkan nama jalan, kelurahan, atau patokan terdekat.",
        "validate": lambda v: len(v.strip()) >= 5,
        "error":    "Lokasi terlalu singkat. Mohon sebutkan nama jalan atau area yang lebih jelas.",
    },
    # step 2 — tingkat keparahan
    {
        "key":      "severity",
        "question": "Seberapa parah kondisinya?\n  1. Ringan\n  2. Sedang\n  3. Parah\n  4. Sangat Parah / Darurat",
        "validate": lambda v: bool(re.search(r"[1-4]|ringan|sedang|parah|darurat", v.lower())),
        "error":    "Jawaban tidak valid. Ketik angka 1-4 atau kata: ringan / sedang / parah / darurat.",
    },
    # step 3 — deskripsi detail
    {
        "key":      "description",
        "question": "Tolong ceritakan detail masalahnya",
        "validate": lambda v: len(v.strip()) >= 15,
        "error":    "Deskripsi terlalu singkat. Mohon jelaskan lebih detail agar laporan valid.",
    },
    # step 4 — judul
    {
        "key":      "title",
        "question": "beri title tentang masalah ini",
        "validate": lambda v: 5 <= len(v.strip()) <= 255,
        "error":    "Judul terlalu pendek atau terlalu panjang (5-255 karakter).",
    },
    {
        "key": "images",
        "question": "Silahkan upload foto terkait masalah ini",
        "validate": lambda v: is_valid_image_url(v),  
        "error":    "Foto WAJIB dilampirkan. Silakan upload foto kerusakan (format: jpg, png, gif, webp).",
    }
]

# ─── HELPER: DETEKSI ──────────────────────────────────────────────────────────

def is_valid_image_url(text: str) -> bool:
    """Cek apakah teks adalah URL gambar atau path upload yang valid (WAJIB)"""
    text = text.strip().lower()

    # Tolak kata-kata penolakan
    if text in ["tidak", "ga ada", "no", "none", "null", "-", "skip"]:
        return False

    # Cek format URL gambar dengan ekstensi
    url_with_ext = r'https?:\/\/[^\s]+\.(jpg|jpeg|png|gif|webp)(\?.*)?$'
    if re.search(url_with_ext, text):
        return True

    # Terima URL upload server tanpa ekstensi (dari /upload endpoint)
    # Format: https://host/uploads/... atau https://host/api/...
    url_any = r'https?:\/\/[^\s]{10,}$'
    if re.search(url_any, text):
        return True

    # Tangkap format [Gambar: url] yang dikirim dari frontend
    bracketed = re.search(r'\[gambar:\s*(https?://[^\]]+)\]', text)
    if bracketed:
        return True

    return False

def extract_image_url(text: str) -> str:
    """Ekstrak URL dari format [Gambar: url] atau kembalikan teks asli."""
    match = re.search(r'\[Gambar:\s*(https?://[^\]]+)\]', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()

def detect_category_id(text: str) -> int:
    """Kembalikan category_id integer berdasarkan keyword."""
    lower = text.lower()
    for cat_id, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return cat_id
    return 6  # Lainnya

def detect_priority(text: str) -> tuple[str, int]:
    """Kembalikan (priority_string, priority_score)."""
    lower = text.lower()
    for priority, data in PRIORITY_MAP.items():
        for kw in data["keywords"]:
            if kw in lower:
                return priority, data["score"]
    return "medium", 50

def detect_fake_score(description: str, location: str, title: str) -> int:
    """
    Heuristik fake score 0-100.
    Semakin tinggi = makin mencurigakan / kemungkinan tidak valid.
    """
    score = 0
    desc_len  = len(description.strip())
    loc_len   = len(location.strip())
    title_len = len(title.strip())

    if desc_len < 20:   score += 30
    if desc_len < 10:   score += 20
    if loc_len < 8:     score += 20
    if title_len < 8:   score += 10

    # Karakter berulang (aaaa, 1111, dll)
    if re.search(r'(.)\1{4,}', description): score += 25
    if re.search(r'(.)\1{4,}', location):    score += 15

    # Semua huruf kapital atau semua angka
    if description.isupper():  score += 10
    if re.fullmatch(r'[\d\s]+', description): score += 20

    return min(score, 100)

def is_gibberish(text: str) -> bool:
    """Deteksi input tidak bermakna."""
    text = text.strip()
    if len(text) < 3:
        return True
    # Lebih dari 40% karakter non-alfanumerik non-spasi
    special = re.findall(r'[^a-zA-Z0-9\s\.,!?\-/]', text)
    if len(special) / max(len(text), 1) > 0.4:
        return True
    # Karakter berulang berlebihan
    if re.search(r'(.)\1{5,}', text):
        return True
    # Hanya angka/simbol
    if re.fullmatch(r'[\d\s\W]+', text):
        return True
    return False

def normalize_severity(text: str) -> str:
    """Normalisasi jawaban keparahan ke string baku."""
    lower = text.lower()
    if "1" in lower or "ringan" in lower:
        return "ringan"
    if "3" in lower or "parah" in lower:
        return "parah"
    if "4" in lower or "darurat" in lower or "sangat" in lower:
        return "sangat parah"
    return "sedang"

# ─── MAIN CHAT FUNCTION ───────────────────────────────────────────────────────

def chat_with_ai(messages: list, collected_data: dict) -> str:
    """
    State-machine berbasis `collected_data['_step']`.
    
    collected_data keys yang dikelola:
      _step            : int  (indeks step saat ini, 0 = belum mulai)
      initial_complaint: str  (cerita pertama user)
      location         : str
      severity         : str
      description      : str
      title            : str
      images           : str  (URL foto - WAJIB)
    """

    # Ambil pesan terakhir user
    last_user_msg = ""
    for m in reversed(messages):
        if m["role"] == "user":
            last_user_msg = m["content"]
            break

    step = collected_data.get("_step", 0)

    # ── STEP 0: initial complaint ─────────────────────────────────────────────
    if step == 0:
        if is_gibberish(last_user_msg):
            return (
                "Maaf, saya tidak dapat memahami laporan Anda. "
                "Mohon ceritakan masalah infrastruktur dengan jelas, "
                "contoh: 'Jalan di depan sekolah berlubang besar.'"
            )

        collected_data["initial_complaint"] = last_user_msg
        collected_data["category_id"] = detect_category_id(last_user_msg)
        collected_data["_step"] = 1
        return STEPS[0]["question"]

    # ── STEP 1–5: kumpulkan data ──────────────────────────────────────────────
    if 1 <= step <= len(STEPS):
        current_step_def = STEPS[step - 1]

        # 🔥 Validasi khusus untuk step foto (tidak boleh kosong, harus URL valid)
        if step == len(STEPS):  # step terakhir (foto)
            if not current_step_def["validate"](last_user_msg):
                return current_step_def["error"]
        else:
            # Validasi normal untuk step lain
            if is_gibberish(last_user_msg):
                return f"Input tidak valid. {current_step_def['error']}"
            
            if not current_step_def["validate"](last_user_msg):
                return current_step_def["error"]

        # Simpan jawaban
        key = current_step_def["key"]
        value = last_user_msg.strip()
        
        if key == "severity":
            value = normalize_severity(value)
        
        # 🔥 Untuk step foto, simpan URL
        if key == "images":
             collected_data["images"] = extract_image_url(value)
        
        collected_data[key] = value
        collected_data["_step"] = step + 1

        # Masih ada step berikutnya?
        if step < len(STEPS):
            return STEPS[step]["question"]

        # ── SEMUA DATA TERKUMPUL (termasuk foto) → buat JSON ───────────────────
        return _finalize_report(collected_data)

    return "Laporan Anda sudah kami terima. Terima kasih!"


# ─── FINALIZE ─────────────────────────────────────────────────────────────────

def _finalize_report(collected_data: dict) -> str:
    """Buat JSON laporan final yang siap masuk tabel `reports`."""

    desc     = collected_data.get("description", "")
    loc      = collected_data.get("location", "")
    title    = collected_data.get("title", "")
    severity = collected_data.get("severity", "sedang")
    initial  = collected_data.get("initial_complaint", "")
    images   = collected_data.get("images", "")  # 🔥 Ambil URL foto

    # 🔥 VALIDASI: Pastikan images tidak kosong
    if not images:
        # Jika tidak ada foto, jangan lanjut ke final
        # Ini seharusnya tidak terjadi karena step foto wajib
        return "Maaf, foto kerusakan WAJIB dilampirkan. Silakan upload foto terlebih dahulu."

    # Deteksi priority dari deskripsi + severity + keluhan awal
    combined = f"{initial} {desc} {severity}"
    priority, priority_score = detect_priority(combined)
    
    if severity == "parah":
        priority = "high"
        priority_score = 75
    elif severity == "sangat parah":
        priority = "critical"
        priority_score = 95

    category_id = collected_data.get("category_id", 6)

    # 🔥 Fake score: lebih tinggi jika deskripsi mencurigakan
    fake_score = detect_fake_score(desc, loc, title)
    
    # Jika tidak ada foto, fake_score +40 (sudah ditangani di step sebelumnya)

    ai_summary = _generate_summary(title, desc, loc)

    report = {
        # FK & ID
        "user_id":           None,     
        "category_id":       category_id,
        # Konten
        "title":             title,
        "description":       desc,
        "priority":          priority,
        "status":            "pending",
        "location":          loc,
        "assigned_admin_id": None,
        # Koordinat (opsional)
        "latitude":          None,
        "longitude":         None,
        # AI fields
        "ai_summary":        ai_summary,
        "fake_score":        round(fake_score, 2),
        "priority_score":    round(priority_score, 2),
        # 🔥 IMAGES (WAJIB)
        "images":            images,
    }

    collected_data["final_report"] = report
    collected_data["_step"] = 99  

    json_str = json.dumps(report, ensure_ascii=False, indent=2)
    
    return (
        f"Terima kasih! Laporan Anda sudah kami rangkum dengan foto yang dilampirkan. 📸\n"
        f"Sistem akan memproses dan meneruskan ke petugas terkait.\n\n"
        f"###REPORT_JSON###\n{json_str}"
    )


def _generate_summary(title: str, description: str, location: str) -> str:
    """Minta Ollama buat summary 1 kalimat; fallback ke string sederhana."""
    prompt = (
        f"Buat 1 kalimat ringkasan laporan infrastruktur berikut dalam Bahasa Indonesia:\n"
        f"Judul: {title}\nLokasi: {location}\nDeskripsi: {description}\n"
        f"Jawab HANYA dengan 1 kalimat ringkasan, tanpa tanda kutip."
    )
    try:
        resp = client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 64},
        )
        summary = resp["message"]["content"].strip().split("\n")[0]
        return summary if len(summary) > 10 else f"{title} di {location}."
    except Exception:
        return f"{title} di {location}."



def extract_report_json(ai_message: str) -> Optional[dict]:
    """
    Ekstrak dict laporan dari respons AI yang mengandung ###REPORT_JSON###.
    Kembalikan None jika belum ada.
    """
    if "###REPORT_JSON###" not in ai_message:
        return None
    json_part = ai_message.split("###REPORT_JSON###", 1)[1].strip()
    match = re.search(r"\{[\s\S]*\}", json_part)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None



def generate_report(data: dict) -> dict:
    """Alias; data sudah lengkap dari _finalize_report."""
    return data.get("final_report", data)