"""
chatbot_search.py
-----------------
Το πρώτο chatbot — βρίσκεται στην αρχική σελίδα.
Παίρνει ελεύθερο κείμενο από τον χρήστη και εξάγει πανεπιστήμιο + εξάμηνο.
"""
import os
import json
import openai
from dotenv import load_dotenv

load_dotenv()

_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
CLEAN_DATA_DIR = os.path.join(BASE_DIR, "cleaned_data_ai")


def discover_json_files():
    # Βρίσκουμε δυναμικά ποια πανεπιστήμια υποστηρίζουμε από τα JSON αρχεία
    json_files = {}
    for filename in os.listdir(CLEAN_DATA_DIR):
        if filename.endswith(".json"):
            university_key = os.path.splitext(filename)[0]
            json_files[university_key] = os.path.join(CLEAN_DATA_DIR, filename)
    return json_files


JSON_FILES = discover_json_files()


def handle_parse_query(text: str) -> dict:
    if not text or not text.strip():
        return {"error": "empty", "message": "Δεν δόθηκε κείμενο."}

    universities = list(JSON_FILES.keys())

    # Ζητάμε από το GPT να εξάγει πανεπιστήμιο και εξάμηνο — χειρίζεται ορθογραφικά λάθη,
    # ελληνικά, greeklish, συντομογραφίες κλπ
    prompt = f"""
You are a strict extraction engine.

Your ONLY task is to identify from the user's message:
1. the target university
2. the semester number

Available university keys:
{json.dumps(universities, ensure_ascii=False)}

University matching rules:
- The user may write the university name with spelling mistakes, repeated letters,
abbreviations, slang, or mixed languages.
Examples:
"aalto", "aaaaaaaaaalto", "aaltoooo", "aalto university"
"delft", "tu delft", "delftttt"
"upm", "upm madrid", "madrid polytechnic"

Match the message to the MOST similar university key.

However:
- If the message does not resemble any available university, return university_key = null
- Do NOT invent universities

Semester rules:
- The semester must be returned as an integer
- Accept natural language formats such as:
  "3rd semester", "semester 3", "3ο εξάμηνο", "τρίτο", "δευτερο", "first", "seventh"
- Convert the result to a number
- If no semester is found return null

Return ONLY valid JSON in this format:
{{
  "university_key": string or null,
  "semester": integer or null,
  "status": "ok" | "missing_university" | "missing_semester" | "missing_both",
  "message": string
}}

Message rules:
- If both found → "Βρέθηκε πανεπιστήμιο και εξάμηνο."
- If university missing → "Δεν βρέθηκε έγκυρο πανεπιστήμιο."
- If semester missing → "Δεν βρέθηκε έγκυρο εξάμηνο."
- If both missing → "Δεν βρέθηκε πανεπιστήμιο και εξάμηνο."

User message: "{text}"
"""

    try:
        response = _client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_completion_tokens=80
        )
        parsed   = json.loads(response.choices[0].message.content)
        uni_key  = parsed.get("university_key")
        semester = parsed.get("semester")
        message  = parsed.get("message")
    except Exception as e:
        return {"error": str(e)}

    # Αν λείπει κάτι, επιστρέφουμε τι ακριβώς λείπει για να το ζητήσει το UI
    missing = []
    if semester is None: missing.append("εξάμηνο")
    if uni_key is None:  missing.append("πανεπιστήμιο")

    if missing:
        return {"error": "parse_failed", "missing": missing, "message": message}

    return {
        "semester":        int(semester),
        "university":      uni_key,
        "university_name": uni_key,
        "message":         message
    }
