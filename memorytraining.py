# In-memory αποθήκευση feedback — χάνεται όταν κλείσει ο server, αρκεί για demo
_feedback = []


def add_feedback(user_id, question, answer, label, correction=""):
    """Αποθηκεύει feedback στη μνήμη. Αγνοεί duplicates."""
    entry = {
        "question":   question.strip(),
        "answer":     answer.strip(),
        "label":      label.strip().lower(),
        "correction": correction.strip()
    }
    # Αποφεύγουμε duplicates
    for existing in _feedback:
        if (existing["question"] == entry["question"] and
                existing["answer"] == entry["answer"] and
                existing["label"] == entry["label"]):
            return
    _feedback.append(entry)


def get_corrections(user_id=None, limit=10):
    """Επιστρέφει τα negative feedbacks με correction — χρησιμοποιούνται ως κανόνες στο system prompt."""
    corrections = [f for f in _feedback if f["label"] == "negative" and f.get("correction")]
    return corrections[-limit:]
