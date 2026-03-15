
# Βιβλιοθήκες
import os
import json
import re
import time
from typing import Any, Dict, List

from dotenv import load_dotenv
import openai

# Πού βρίσκονται τα αρχεία μας
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, "data")           # τα πρωτότυπα JSON με τα raw courses
OUTPUT_DIR = os.path.join(BASE_DIR, "cleaned_data_ai") # εδώ θα αποθηκευτούν τα καθαρισμένα
ENV_PATH   = os.path.join(BASE_DIR, ".env")

MODEL_NAME           = "gpt-5.1"
SLEEP_BETWEEN_CALLS  = 2.0  # λίγη αναμονή μεταξύ κλήσεων για να μην χτυπάμε το rate limit


def load_api_key() -> str:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(f"Δεν βρέθηκε OPENAI_API_KEY στο .env ({ENV_PATH})")
    return api_key


def ensure_output_dir() -> None:
    # Δημιουργούμε τον φάκελο αν δεν υπάρχει ήδη
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def normalize_metadata(metadata: Any) -> Dict[str, Any]:
    # Καθαρίζουμε τα metadata ώστε να είναι συμβατά με JSON
    clean: Dict[str, Any] = {}
    if not isinstance(metadata, dict):
        return clean
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        elif isinstance(value, list):
            clean[key] = [str(v) for v in value]
        else:
            clean[key] = str(value)
    return clean


def safe_json_loads(text: str) -> Dict[str, Any]:
    # Μερικές φορές το GPT τυλίγει το JSON σε ```json blocks — τα αφαιρούμε
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def clean_list_field(value: Any) -> List[str]:
    # Κανονικοποιούμε topics/keywords σε λίστα χωρίς duplicates
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
    elif isinstance(value, str):
        items = [x.strip() for x in re.split(r"[;,]\s*", value) if x.strip()]
    else:
        items = []

    seen, out = set(), []
    for item in items:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def build_prompt(content: str, metadata: Dict[str, Any]) -> str:
    # Ζητάμε από το GPT να εξάγει δομημένα δεδομένα από την περιγραφή του μαθήματος
    title     = metadata.get("title", "")
    university = metadata.get("university", "")
    country   = metadata.get("country", "")
    semester  = metadata.get("semester", "")
    ects      = metadata.get("ects", "")
    course_id = metadata.get("course_id", "")

    return f"""
You are helping prepare university course descriptions for vector embeddings and semantic retrieval.

Return ONLY valid JSON with this schema:
{{
  "clean_description": "string",
  "topics": ["string"],
  "keywords": ["string"],
  "language": "string",
  "category": "string"
}}

Metadata:
title: {title}
course_id: {course_id}
university: {university}
country: {country}
semester: {semester}
ects: {ects}

Raw content:
\"\"\"{content}\"\"\"
""".strip()


def analyze_with_openai(client: openai.OpenAI, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    # Στέλνουμε το μάθημα στο GPT και παίρνουμε πίσω καθαρά, δομημένα δεδομένα
    prompt   = build_prompt(content, metadata)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"}  # εγγυάται valid JSON output
    )
    parsed = safe_json_loads(response.choices[0].message.content)

    # Κανονικοποιούμε τα πεδία
    parsed["topics"]            = clean_list_field(parsed.get("topics", []))
    parsed["keywords"]          = clean_list_field(parsed.get("keywords", []))
    parsed["clean_description"] = str(parsed.get("clean_description", "")).strip()
    parsed["language"]          = str(parsed.get("language", "")).strip()
    parsed["category"]          = str(parsed.get("category", "")).strip()
    return parsed


def build_embedding_content(metadata: Dict[str, Any], ai_result: Dict[str, Any]) -> str:
    # Φτιάχνουμε το τελικό κείμενο που θα γίνει embedding — όσο πιο πλούσιο τόσο καλύτερη η αντιστοίχιση
    lines = []

    title       = metadata.get("title", "")
    course_id   = metadata.get("course_id", "")
    university  = metadata.get("university", "")
    country     = metadata.get("country", "")
    semester    = metadata.get("semester", "")
    ects        = metadata.get("ects", "")
    description = ai_result.get("clean_description", "")
    topics      = ai_result.get("topics", [])
    keywords    = ai_result.get("keywords", [])
    language    = ai_result.get("language", "")
    category    = ai_result.get("category", "")

    if title:      lines.append(f"Course title: {title}")
    if course_id:  lines.append(f"Course code: {course_id}")
    if university: lines.append(f"University: {university}")
    if country:    lines.append(f"Country: {country}")
    if semester != "": lines.append(f"Semester: {semester}")
    if ects != "":     lines.append(f"ECTS: {ects}")
    if language:   lines.append(f"Language of source content: {language}")
    if category:   lines.append(f"Broad category: {category}")

    if description:
        lines.append("")
        lines.append("Course description:")
        lines.append(description)

    if topics:
        lines.append("")
        lines.append("Main topics:")
        for topic in topics:
            lines.append(f"- {topic}")

    if keywords:
        lines.append("")
        lines.append("Keywords:")
        lines.append(", ".join(keywords))

    return "\n".join(lines).strip()


def process_item(client: openai.OpenAI, item: Dict[str, Any], idx: int, filename: str):
    # Επεξεργαζόμαστε ένα μάθημα — καλούμε το GPT και επιστρέφουμε το καθαρισμένο record
    if not isinstance(item, dict):
        return None

    raw_content = item.get("content", "")
    metadata    = normalize_metadata(item.get("metadata", {}))

    if not raw_content or not isinstance(raw_content, str):
        return None

    try:
        ai_result = analyze_with_openai(client, raw_content, metadata)
    except Exception as e:
        print(f"!!! Σφάλμα API για item {idx} στο {filename}: {e}")
        return None

    new_metadata = dict(metadata)
    new_metadata["keywords"]              = ai_result.get("keywords", [])
    new_metadata["topics"]                = ai_result.get("topics", [])
    new_metadata["category"]              = ai_result.get("category", "")
    new_metadata["cleaned_for_embedding"] = True

    embedding_content = build_embedding_content(new_metadata, ai_result)

    if len(embedding_content.strip()) < 40:
        return None

    return {"content": embedding_content, "metadata": new_metadata}


def process_file(client: openai.OpenAI, input_path: str, output_path: str) -> None:
    # Επεξεργαζόμαστε ένα ολόκληρο JSON αρχείο — παραλείπουμε όσα έχουν ήδη γίνει
    filename = os.path.basename(input_path)

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"!!! {filename}: άκυρο JSON → {e}")
            return

    if not isinstance(data, list):
        print(f"!!! {filename}: δεν περιέχει λίστα αντικειμένων.")
        return

    # Φορτώνουμε ό,τι έχει ήδη επεξεργαστεί για να μην ξανακαλέσουμε το API
    existing_cleaned, existing_ids = [], set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            try:
                existing_cleaned = json.load(f)
                for item in existing_cleaned:
                    meta = item.get("metadata", {})
                    cid, uni = meta.get("course_id"), meta.get("university")
                    if cid and uni:
                        existing_ids.add(f"{cid}::{uni}")
            except json.JSONDecodeError:
                existing_cleaned = []

    print(f"\nProcessing: {filename} ({len(existing_ids)} ήδη επεξεργασμένα)")

    new_cleaned = []
    for idx, item in enumerate(data, start=1):
        meta       = normalize_metadata(item.get("metadata", {}))
        cid, uni   = meta.get("course_id"), meta.get("university")
        unique_key = f"{cid}::{uni}"

        if unique_key in existing_ids:
            print(f"⏭ item {idx}/{len(data)} ({cid}) - ΠΑΡΑΛΕΙΠΕΤΑΙ")
            continue

        print(f"→ item {idx}/{len(data)} ({cid}) - ΕΠΕΞΕΡΓΑΣΙΑ")
        cleaned = process_item(client, item, idx, filename)
        if cleaned:
            new_cleaned.append(cleaned)
        time.sleep(SLEEP_BETWEEN_CALLS)

    if not new_cleaned:
        print(f"{filename}: Κανένα νέο course.")
        return

    # Αποθηκεύουμε παλιά + νέα μαζί
    all_cleaned = existing_cleaned + new_cleaned
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_cleaned, f, ensure_ascii=False, indent=2)
    print(f"{filename}: Προστέθηκαν {len(new_cleaned)} νέα courses.")


def main() -> None:
    print("!!!TransformJson LAUNCHED")

    api_key = load_api_key()
    ensure_output_dir()

    # Βρίσκουμε όλα τα JSON στο data/ και τα επεξεργαζόμαστε ένα-ένα
    json_files = sorted([f for f in os.listdir(DATA_DIR) if f.lower().endswith(".json")])
    client     = openai.OpenAI(api_key=api_key)

    for filename in json_files:
        input_path  = os.path.join(DATA_DIR, filename)
        output_path = os.path.join(OUTPUT_DIR, filename)
        process_file(client, input_path, output_path)

    print("!!!THE JSON FILES WERE TRANSFORMED")


if __name__ == "__main__":
    main()
