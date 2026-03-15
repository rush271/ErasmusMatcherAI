"""
chatbot_advisor.py
------------------
Chatbot κάτω από τον πίνακα αποτελεσμάτων.
Απαντά σε ερωτήσεις για μαθήματα, πανεπιστήμιο, πόλη, Erasmus ζωή.
Ανιχνεύει αν ο χρήστης θέλει αλλαγή πανεπιστημίου/εξαμήνου (redirect).
"""
import os
import json
import openai
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from memorytraining import get_corrections

load_dotenv()

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
DB_DIR    = os.path.join(BASE_PATH, "chroma_db")

# Φορτώνουμε τη βάση με τα embeddings και τον OpenAI client μία φορά κατά το startup
_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
_vector_db  = Chroma(persist_directory=DB_DIR, embedding_function=_embeddings)
_client     = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ── Redirect detection ────────────────────────────────────────────────────────

def _detect_redirect(question: str, context: dict, history: list = None):
    """Ελέγχει αν ο χρήστης ζητά αλλαγή πανεπιστημίου ή εξαμήνου."""
    current_uni = context.get("target_university", "")
    current_sem = context.get("semester", "")

    last_assistant = ""
    if history:
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                last_assistant = msg.get("content", "")[:200]
                break

    conv_ctx = f'\nLast assistant message: "{last_assistant}"\n' if last_assistant else ""

    prompt = f"""The user is viewing Erasmus course matches for:
- University: {current_uni}
- Semester: {current_sem}
{conv_ctx}
Does the user's message EXPLICITLY ask to switch to a DIFFERENT university or semester?

Rules:
- ONLY return redirect=true if the user clearly wants different university or semester
- If the last message was about courses, short replies with numbers are course follow-ups NOT redirects
- Ordinals like "3ο", "5ο", "the 3rd" referring to course position are NEVER semester requests
- A redirect needs explicit intent: "show me Aalto", "switch to semester 3", "try TU Delft", "θέλω άλλο πανεπιστήμιο"

Available universities: AALTO (Aalto University), UPM (Universidad Politécnica de Madrid), TUDelft (TU Delft)

Return ONLY valid JSON: {{"redirect": true or false, "university_key": "AALTO" or "UPM" or "TUDelft" or null, "semester": number or null}}
User message: "{question}"
"""
    try:
        res = _client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_completion_tokens=50
        )
        parsed = json.loads(res.choices[0].message.content)
        if not parsed.get("redirect"):
            return None
        uni_key  = parsed.get("university_key") or current_uni
        semester = parsed.get("semester") or current_sem
        if uni_key and semester:
            return {"university": uni_key, "semester": int(semester)}
    except Exception:
        pass
    return None


# ── Main handler ──────────────────────────────────────────────────────────────

def handle_chat(data: dict) -> dict:
    question      = data.get("question", "").strip()
    history       = data.get("history", [])
    context       = data.get("context", {})
    table_results = data.get("table_results", [])
    saved_facts   = data.get("facts", [])

    if not question:
        return {"answer": "Παρακαλώ γράψε μια ερώτηση."}

    # Πρώτα ελέγχουμε αν ο χρήστης θέλει να αλλάξει πανεπιστήμιο/εξάμηνο
    try:
        redirect = _detect_redirect(question, context, history)
    except Exception:
        redirect = None
    if redirect:
        return {"redirect": redirect}

    # Αν το μήνυμα αποκαλύπτει κάτι για τον χρήστη (π.χ. κατεύθυνση, στόχοι), το αποθηκεύουμε
    new_fact = None
    try:
        fact_res = _client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": f"""Does this message reveal a personal fact about the user (major, interests, goals)?
If yes, return a short fact in 1 sentence. If no, return null.
Return ONLY valid JSON: {{"fact": "..." or null}}
Message: "{question}"
"""}],
            response_format={"type": "json_object"},
            max_completion_tokens=30
        )
        new_fact = json.loads(fact_res.choices[0].message.content).get("fact") or None
    except Exception:
        pass

    # Ψάχνουμε στη vector βάση για σχετικά μαθήματα — αυτά θα δοθούν ως context στο GPT
    try:
        docs = _vector_db.similarity_search(question, k=6)
        courses_text = ""
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            courses_text += (
                f"\n{i}. {meta.get('title','')} ({meta.get('course_id','')})"
                f" — {meta.get('university','')}\n"
                f"   ECTS: {meta.get('ects','')} | Topics: {meta.get('topics','')}\n"
                f"   {doc.page_content[:300]}\n"
            )
    except Exception:
        courses_text = ""

    # Ο πίνακας που βλέπει ο χρήστης αυτή τη στιγμή — το GPT το χρησιμοποιεί για "το 3ο μάθημα" κλπ
    table_text = ""
    if table_results:
        table_text = f"\nCourses in the results table ({len(table_results)} total):\n"
        for r in table_results:
            match_info = f"→ {r['match']} ({r['match_ects']} ECTS, {r['score']}% match)" if r.get('match') else "→ No match"
            table_text += f"{r['index']}. {r['source']} ({r['source_ects']} ECTS)  {match_info}\n"

    # Corrections από προηγούμενα 👎 — μπαίνουν ως κανόνες στο system prompt
    try:
        corrections = get_corrections("default", limit=10)
    except Exception:
        corrections = []
    corrections_text = ""
    if corrections:
        corrections_text = "\nRules learned from past user feedback (MUST follow):\n"
        for c in corrections:
            corrections_text += f'- When asked "{c["question"][:60]}": {c["correction"]}\n'

    # User facts
    facts_text = ""
    if saved_facts:
        facts_text = "\nKnown about this user:\n" + "".join(f"- {f}\n" for f in saved_facts[-5:])

    system_prompt = f"""You are an Erasmus advisor chatbot helping a student from {context.get("source_university", "their university")} who is considering Erasmus at {context.get("target_university", "a partner university")}, semester {context.get("semester", "")}.

You can answer ANY question relevant to a student going on Erasmus, including:
- Course matching: which courses correspond, ECTS differences, syllabus comparisons
- The partner university: history, reputation, facilities, departments
- The city/country: weather, cost of living, rent, food, transport, safety, student life
- Erasmus practicalities: housing, language, culture, tips
- Anything else useful for a student planning this Erasmus

{table_text}
Relevant courses from knowledge base:
{courses_text}
{facts_text}
{corrections_text}
Rules:
- If the user refers to "the 1st", "the 3rd", "το 3ο" etc., look it up in the table above
- The table has EXACTLY {len(table_results)} courses. If asked about course #{len(table_results)+1} or higher, say it doesn't exist
- Base course answers on the knowledge base data above
- For university/city/practical questions, use your own knowledge — be specific and helpful
- Be concise: 2-3 sentences max. No filler, no repetition.
- No bullet points
- Reply in the same language as the user (Greek or English)
- If truly unrelated to Erasmus, decline in one sentence"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    try:
        response = _client.chat.completions.create(
            model="gpt-5.1",
            messages=messages,
            max_completion_tokens=200
        )
        result = {"answer": response.choices[0].message.content or "Συγγνώμη, δοκίμασε ξανά σε λίγο."}
        if new_fact:
            result["new_fact"] = new_fact
        return result
    except Exception:
        return {"answer": "Συγγνώμη, δοκίμασε ξανά σε λίγο."}
