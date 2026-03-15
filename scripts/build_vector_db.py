# Οι βιβλιοθήκες που χρειαζόμαστε
import json
import os
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

# Βρίσκουμε πού βρίσκονται τα αρχεία μας
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "cleaned_data_ai")  # εδώ είναι τα καθαρισμένα JSON
DB_DIR   = os.path.join(BASE_DIR, "chroma_db")        # εδώ αποθηκεύεται η βάση με τα embeddings

load_dotenv(os.path.join(BASE_DIR, ".env"))


def normalize_metadata(metadata: dict) -> dict:
    # Το ChromaDB δέχεται μόνο απλούς τύπους — μετατρέπουμε λίστες και None
    clean = {}
    for key, value in metadata.items():
        if value is None:
            continue
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, list):
            clean[key] = ", ".join(str(v) for v in value)
        else:
            clean[key] = str(value)
    return clean


def build_embedding_text(content: str, metadata: dict) -> str:
    # Βάζουμε τίτλο, topics και keywords πρώτα γιατί αυτά "φορτίζουν" το embedding περισσότερο
    # — έτσι μαθήματα με παρόμοιο αντικείμενο βρίσκονται κοντά στον vector space
    title    = metadata.get("title", "")
    topics   = metadata.get("topics", "")
    keywords = metadata.get("keywords", "")

    parts = []
    if title:    parts.append(f"COURSE TITLE: {title}")
    if topics:   parts.append(f"MAIN TOPICS: {topics}")
    if keywords: parts.append(f"IMPORTANT KEYWORDS: {keywords}")
    if content:
        parts.append("\nCOURSE DESCRIPTION:")
        parts.append(content.strip())

    return "\n".join(parts).strip()


def load_documents():
    documents = []
    doc_ids   = []
    seen_ids  = set()

    print("ΔΙΑΒΑΣΜΑ JSON")

    if not os.path.exists(DATA_DIR):
        print(f"!!! Ο φάκελος {DATA_DIR} δεν βρέθηκε !!!")
        return [], []

    json_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]

    for filename in json_files:
        filepath = os.path.join(DATA_DIR, filename)

        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"!!! Πρόβλημα στο {filename}: {e} !!!")
                continue

        if not isinstance(data, list):
            print(f"!!! Το {filename} δεν περιέχει λίστα αντικειμένων !!!")
            continue

        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue

            content  = item.get("content", "")
            metadata = item.get("metadata", {})

            if not content or not isinstance(content, str):
                continue

            if not isinstance(metadata, dict):
                metadata = {}

            metadata  = normalize_metadata(metadata)
            course_id = metadata.get("course_id")
            university = metadata.get("university")
            unique_key = f"{course_id}::{university}"

            # Αγνοούμε duplicates — μπορεί να υπάρχουν στα raw data
            if course_id and university:
                if unique_key in seen_ids:
                    print(f"??? DUPLICATE ΜΑΘΗΜΑ ({unique_key}) ΣΤΟ {filename} ???")
                    continue
                seen_ids.add(unique_key)

            # Φτιάχνουμε το κείμενο που θα μετατραπεί σε embedding
            enriched_content = build_embedding_text(content, metadata)

            documents.append(Document(page_content=enriched_content, metadata=metadata))
            doc_ids.append(unique_key)

    return documents, doc_ids


def main():
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("!!! Δεν βρέθηκε OPENAI_API_KEY στο .env !!!")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # Φορτώνουμε την υπάρχουσα βάση — αν δεν υπάρχει, δημιουργείται αυτόματα
    vector_db = Chroma(
        persist_directory=DB_DIR,
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"}
    )

    existing_ids = set(vector_db.get()["ids"])
    print(f"ΥΠΑΡΧΟΝΤΑ RECORDS ΣΤΗ ΒΑΣΗ: {len(existing_ids)}")

    documents, doc_ids = load_documents()

    if not documents:
        raise ValueError("!!! Δεν φορτώθηκαν documents")

    print(f"ΦΟΡΤΩΘΗΚΑΝ {len(documents)} ΑΡΧΕΙΑ ΣΥΝΟΛΙΚΑ")

    # Κρατάμε μόνο τα νέα μαθήματα που δεν έχουν ήδη embedding
    new_docs = [doc for doc, did in zip(documents, doc_ids) if did not in existing_ids]
    new_ids  = [did for did in doc_ids if did not in existing_ids]

    if not new_docs:
        print("ΔΕΝ ΥΠΑΡΧΟΥΝ ΝΕΑ RECORDS. Η ΒΑΣΗ ΕΙΝΑΙ ΗΔΗ ΕΝΗΜΕΡΩΜΕΝΗ.")
        return

    print(f"ΠΡΟΣΘΗΚΗ {len(new_docs)} ΝΕΩΝ RECORDS...")
    vector_db.add_documents(documents=new_docs, ids=new_ids)

    print(f"Η βάση ενημερώθηκε. Αποθηκεύτηκε στο {DB_DIR}")


if __name__ == "__main__":
    main()
