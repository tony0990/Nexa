from datetime import datetime
from dates.reference_time import CAIRO_TZ
from app.db.vector_store import VectorStore
from dedup.embeddings import EmbeddingModel
from intelligence.llm_runtime import LLMRuntime
from app.core.indexer import NexaIndexer
import sys

# Force UTF-8 output for Windows terminal to handle Arabic text
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_end_to_end_demo():
    print("Starting Nexa End-to-End Production Demo...")

    # 1. Initialize Components
    runtime = LLMRuntime(model_path="mock_model.bin")
    runtime.start()
    store = VectorStore()
    indexer = NexaIndexer(runtime, store)
    embedding_model = EmbeddingModel()

    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

    # 2. Sample Production Data
    transcripts = {
        "meeting_001": "أحمد، لازم تخلص الـ report بكرة الساعة 10 الصبح\nسارة، ابعتي الإيميل للعميل يوم الحد",
        "meeting_002": "John, please finish the documentation by Friday\nنور، check the logs today"
    }

    print("\nIndexing Transcripts...")
    for tid, text in transcripts.items():
        count = indexer.process_transcript(text, tid, ref_dt)
        print(f"Indexed {tid}: {count} segments.")

    # 3. Successful Query Response
    # Query: "What is Ahmed doing tomorrow?"
    query_text = "Ahmed's task tomorrow"
    print(f"\nQuerying: '{query_text}'")

    query_embedding = embedding_model.encode(query_text).tolist()
    results = store.query(query_embedding, n_results=2)

    print("\nTop Results:")
    if results['metadatas'] and results['metadatas'][0]:
        for i, meta in enumerate(results['metadatas'][0]):
            print(f"{i+1}. Task: {meta['task']} | Owner: {meta['owner']} | Date: {meta['resolved_date']}")
    else:
        print("No results found.")

    runtime.shutdown()
    print("\nDemo Complete.")

if __name__ == "__main__":
    run_end_to_end_demo()
