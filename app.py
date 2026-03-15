from flask import Flask, render_template, request, jsonify
import os
import math
from typing import Any, Dict, List
import numpy as np
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from chatbot_search import handle_parse_query
from chatbot_advisor import handle_chat
from memorytraining import add_feedback
import subprocess

load_dotenv()

app = Flask(__name__, static_folder='templates', static_url_path='/static')

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
DB_DIR    = os.path.join(BASE_PATH, "chroma_db")

# Δημιουργούμε τον φάκελο της βάσης αν δεν υπάρχει
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR, exist_ok=True)
    print(f"Δημιουργήθηκε ο φάκελος {DB_DIR} για ChromaDB.")

# Κατά την εκκίνηση τρέχουμε το pipeline — καθαρίζει νέα μαθήματα και χτίζει τα embeddings
print("Εκκίνηση Data Pipeline: Έλεγχος για νέα μαθήματα...")
try:
    subprocess.run(["python", "scripts/TransformJson.py"], check=True)
    print("TransformJson ολοκληρώθηκε.")
except subprocess.CalledProcessError as e:
    print(f" Σφάλμα στην εκτέλεση του TransformJson.py: {e}")

try:
    subprocess.run(["python", "scripts/build_vector_db.py"], check=True)
    print("build_vector_db ολοκληρώθηκε.")
except subprocess.CalledProcessError as e:
    print(f" Σφάλμα στην εκτέλεση του build_vector_db.py: {e}")

print("Το Data Pipeline εχει ολοκληρωθεί (ή τερματίστηκε με σφάλματα).")

# Φορτώνουμε τη βάση μία φορά — δεν ξανακαλούμε embeddings API εδώ
print("Φορτώνω ChromaDB...")
vector_db = Chroma(persist_directory=DB_DIR)
print("ChromaDB φορτώθηκε!")


CLEAN_DATA_DIR = os.path.join(BASE_PATH, "cleaned_data_ai")

# Χώρα → emoji σημαία
_COUNTRY_FLAGS = {
    "GR": "🇬🇷", "GREECE": "🇬🇷", "ΕΛΛΑΔΑ": "🇬🇷",
    "FI": "🇫🇮", "FINLAND": "🇫🇮",
    "NL": "🇳🇱", "NETHERLANDS": "🇳🇱",
    "ES": "🇪🇸", "SPAIN": "🇪🇸",
    "DE": "🇩🇪", "GERMANY": "🇩🇪",
    "FR": "🇫🇷", "FRANCE": "🇫🇷",
    "SE": "🇸🇪", "SWEDEN": "🇸🇪",
    "IT": "🇮🇹", "ITALY": "🇮🇹",
    "PT": "🇵🇹", "PORTUGAL": "🇵🇹",
    "BE": "🇧🇪", "BELGIUM": "🇧🇪",
    "AT": "🇦🇹", "AUSTRIA": "🇦🇹",
    "DK": "🇩🇰", "DENMARK": "🇩🇰",
    "NO": "🇳🇴", "NORWAY": "🇳🇴",
    "CZ": "🇨🇿", "CZECH REPUBLIC": "🇨🇿",
    "PL": "🇵🇱", "POLAND": "🇵🇱",
}

_GREEK_COUNTRIES = {"GR", "GREECE", "ΕΛΛΑΔΑ"}


def _discover_universities():
    """Διαβάζει τα JSON από cleaned_data_ai/ και χτίζει δυναμικά τα dicts πανεπιστημίων.
    Το filename (π.χ. AALTO.json) γίνεται το key. Πανεπιστήμια με ελληνική χώρα → source, υπόλοιπα → target."""
    import json as _json
    sources, targets = {}, {}
    if not os.path.exists(CLEAN_DATA_DIR):
        return sources, targets
    for filename in sorted(os.listdir(CLEAN_DATA_DIR)):
        if not filename.endswith(".json"):
            continue
        key = os.path.splitext(filename)[0]
        try:
            with open(os.path.join(CLEAN_DATA_DIR, filename), "r", encoding="utf-8") as f:
                data = _json.load(f)
            if not isinstance(data, list) or not data:
                continue
            meta     = data[0].get("metadata", {})
            uni_name = meta.get("university", key)
            country  = meta.get("country", "").strip().upper()
            flag     = _COUNTRY_FLAGS.get(country, "🏫")
            if country in _GREEK_COUNTRIES or "AUTH" in key.upper():
                sources[key] = {"name": uni_name, "flag": flag}
            else:
                # Keywords: το key, το πλήρες όνομα, οι λέξεις του ονόματος, η χώρα
                keywords = list({key.upper(), uni_name.upper()} |
                                {w.upper() for w in uni_name.split() if len(w) > 2} |
                                ({country} if country else set()))
                targets[key] = {"name": uni_name, "flag": flag, "keywords": keywords}
        except Exception:
            continue
    return sources, targets


# Χτίζουμε τα dicts κατά την εκκίνηση — αν προστεθεί νέο πανεπιστήμιο στο cleaned_data_ai/, εμφανίζεται αυτόματα
UNIVERSITIES, TARGET_UNIVERSITIES = _discover_universities()
if not UNIVERSITIES:
    UNIVERSITIES = {"AUTH": {"name": "Αριστοτέλειο Πανεπιστήμιο Θεσσαλονίκης", "flag": "🇬🇷"}}


# Μετατρέπει οτιδήποτε σε int χωρίς να κρασάρει
def safe_int(value: Any, default: int = 0) -> int:
    try: return int(value)
    except Exception: return default

# Κανονικοποιεί κείμενο σε κεφαλαία για σύγκριση
def normalize_text(value: Any) -> str:
    if value is None: return ""
    return str(value).strip().upper()

# Cosine similarity μεταξύ δύο vectors — μετράει πόσο "κοντά" είναι δύο μαθήματα στο embedding space
def cosine_similarity(vec1, vec2) -> float:
    if vec1 is None or vec2 is None: return 0.0
    vec1 = np.asarray(vec1, dtype=float)
    vec2 = np.asarray(vec2, dtype=float)
    if vec1.size == 0 or vec2.size == 0 or vec1.shape != vec2.shape: return 0.0
    norm1, norm2 = np.linalg.norm(vec1), np.linalg.norm(vec2)
    if norm1 == 0.0 or norm2 == 0.0: return 0.0
    return float(max(0.0, min(1.0, np.dot(vec1, vec2) / (norm1 * norm2))))

# Το raw cosine score είναι συμπιεσμένο γύρω στο 0.6-0.7 — το sigmoid το απλώνει σε 0-100% για να φαίνεται πιο κατανοητό
def stretch_display_score(raw_cosine: float) -> int:
    x0, k = 0.625, 60.0
    try:    sigmoid_val = 1.0 / (1.0 + math.exp(-k * (raw_cosine - x0)))
    except OverflowError: sigmoid_val = 0.0 if raw_cosine < x0 else 1.0
    return int(min(100.0, max(0.0, round(sigmoid_val * 100.0, 1))))

# Χρώμα ανάλογα με το σκορ — κόκκινο/πορτοκαλί/πράσινο
def score_color(display_score: float) -> str:
    if display_score < 50: return "red"
    if display_score < 75: return "orange"
    return "green"

# Ελέγχει αν ένα μάθημα ανήκει στο πανεπιστήμιο προέλευσης
def is_source_auth_course(metadata: Dict[str, Any], source_key: str) -> bool:
    country    = normalize_text(metadata.get("country", ""))
    university = normalize_text(metadata.get("university", ""))
    if source_key == "AUTH":
        return country in {"GR", "GREECE", "ΕΛΛΑΔΑ"} or "AUTH" in university or "ΑΡΙΣΤΟΤΕΛΕΙΟ" in university or "ΘΕΣΣΑΛΟΝΙΚΗ" in university
    return source_key in university

# Ελέγχει αν ένα μάθημα ανήκει στο πανεπιστήμιο υποδοχής με βάση τα keywords
def is_target_course(metadata: Dict[str, Any], target_key: str) -> bool:
    country    = normalize_text(metadata.get("country", ""))
    university = normalize_text(metadata.get("university", ""))
    for kw in TARGET_UNIVERSITIES[target_key]["keywords"]:
        if kw.upper() == country or kw.upper() in university: return True
    return False

# Φορτώνει όλα τα μαθήματα από τη ChromaDB μαζί με τα embeddings τους
def load_all_courses() -> List[Dict[str, Any]]:
    data = vector_db.get(include=["documents", "metadatas", "embeddings"])
    return [
        {"content": doc, "metadata": meta, "embedding": emb}
        for doc, meta, emb in zip(data.get("documents", []), data.get("metadatas", []), data.get("embeddings", []))
        if meta and emb is not None
    ]

# Βρίσκει τα διαθέσιμα εξάμηνα από τα μαθήματα του ΑΠΘ
def get_semesters() -> List[int]:
    semesters = {safe_int(c["metadata"].get("semester"), 0) for c in load_all_courses() if is_source_auth_course(c["metadata"], "AUTH")}
    return sorted(s for s in semesters if s > 0)

# Επιστρέφει τα μαθήματα του ΑΠΘ για συγκεκριμένο εξάμηνο
def get_source_courses(source_key: str, semester: int) -> List[Dict[str, Any]]:
    return [c for c in load_all_courses() if is_source_auth_course(c["metadata"], source_key) and safe_int(c["metadata"].get("semester"), 0) == semester]

# Επιστρέφει όλα τα μαθήματα ενός πανεπιστημίου υποδοχής
def get_target_courses(target_key: str) -> List[Dict[str, Any]]:
    return [c for c in load_all_courses() if is_target_course(c["metadata"], target_key)]

# Για κάθε μάθημα του ΑΠΘ βρίσκει το πιο κοντινό μάθημα του target με cosine similarity
def find_matches(source_courses: List[Dict[str, Any]], target_key: str) -> List[Dict[str, Any]]:
    target_courses = get_target_courses(target_key)
    if not target_courses: return []
    results = []
    for src in source_courses:
        best_score, best = max(
            ((cosine_similarity(src["embedding"], t["embedding"]), t) for t in target_courses),
            key=lambda x: x[0]
        )
        display_score = stretch_display_score(best_score)
        results.append({
            "source": src["metadata"],
            "matches": [{
                "title":         best["metadata"].get("title", "Άγνωστος Τίτλος"),
                "course_id":     best["metadata"].get("course_id", ""),
                "university":    best["metadata"].get("university", ""),
                "semester":      best["metadata"].get("semester", ""),
                "ects":          best["metadata"].get("ects", ""),
                "syllabus_url":  best["metadata"].get("syllabus_url", "#"),
                "score":         display_score,
                "raw_score":     round(best_score * 100, 1),
                "display_color": score_color(display_score),
                "topics":        best["metadata"].get("topics", ""),
                "keywords":      best["metadata"].get("keywords", ""),
                "category":      best["metadata"].get("category", ""),
            }],
            "is_match":   best_score >= 0.55,
            "best_score": display_score,
        })
    return results


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html",
        universities={k: {"name": v["name"], "flag": v["flag"]} for k, v in UNIVERSITIES.items()},
        targets={k: {"name": v["name"], "flag": v["flag"]} for k, v in TARGET_UNIVERSITIES.items()})

# Τα διαθέσιμα εξάμηνα για το dropdown
@app.route("/api/semesters")
def get_semesters_api():
    return jsonify(get_semesters())

# Κύριο endpoint — παίρνει πανεπιστήμιο + εξάμηνο και επιστρέφει τις αντιστοιχίσεις
@app.route("/api/match", methods=["POST"])
def match():
    data       = request.json or {}
    source_key = data.get("source_university")
    target_key = data.get("target_university")
    try:    semester = int(data.get("semester"))
    except: return jsonify({"error": "Μη έγκυρο εξάμηνο"}), 400
    if source_key not in UNIVERSITIES:      return jsonify({"error": "Invalid source university"}), 400
    if target_key not in TARGET_UNIVERSITIES: return jsonify({"error": "Invalid target university"}), 400
    source_courses = get_source_courses(source_key, semester)
    if not source_courses: return jsonify({"error": f"Δεν βρέθηκαν μαθήματα για το {semester}ο εξάμηνο."}), 404
    results = find_matches(source_courses, target_key)
    return jsonify({"source_university": UNIVERSITIES[source_key]["name"], "target_university": TARGET_UNIVERSITIES[target_key]["name"],
                    "semester": semester, "total_courses": len(source_courses), "match_count": sum(1 for r in results if r["is_match"]), "results": results})

# Παίρνει ελεύθερο κείμενο και εξάγει πανεπιστήμιο + εξάμηνο μέσω GPT
@app.route("/api/parse_query", methods=["POST"])
def parse_query():
    result = handle_parse_query((request.json or {}).get("text", "").strip())
    if "error" in result and result["error"] not in ("parse_failed",): return jsonify(result), 500
    if "missing" in result: return jsonify(result), 422
    return jsonify(result)

# Το chatbot — απαντάει ερωτήσεις για μαθήματα, Erasmus, πανεπιστήμια
@app.route("/api/chat", methods=["POST"])
def chat():
    result = handle_chat(request.json or {})
    return jsonify(result), (400 if "error" in result else 200)

# Αποθηκεύει το feedback του χρήστη (👎 με correction χρησιμοποιείται ως κανόνας στο chatbot)
@app.route("/api/feedback", methods=["POST"])
def feedback():
    data = request.json or {}
    add_feedback(
        user_id    = "default",
        question   = data.get("question", ""),
        answer     = data.get("answer", ""),
        label      = data.get("label", ""),
        correction = data.get("correction", ""),
    )
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
