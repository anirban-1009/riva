#!/usr/bin/env python3
"""Smoke test script for Riva M4 (Phase 1: Embeddings & Phase 2: Vector Store).

Validates:
1. Embedding provider connectivity and vector generation.
2. sqlite-vec extension loading and table creation in SQLite.
3. Ingesting turns and indexing embeddings in `vec_turns`.
4. Zero-keyword semantic recall queries and cosine distance thresholds.
5. Active session exclusion filters.
6. SQL database trigger cascading deletions (`trg_turns_delete_embeddings`).
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from common.llm.embeddings import create_embedding_provider
from common.memory.store import EpisodicStore


async def run_smoke_test() -> int:
    print("=" * 60)
    print("  Riva Milestone 4 (Semantic Recall) Smoke Test")
    print("=" * 60)

    # 1. Initialize Embedding Provider
    print("\n[Step 1/6] Initializing Embedding Provider...")
    try:
        provider = create_embedding_provider("ollama", model="nomic-embed-text:latest", dimension=768)
        # Cold start ping
        test_vec = await provider.embed_query("ping")
        norm = sum(x**2 for x in test_vec) ** 0.5
        print(f"  ✓ Connected to Ollama '{provider.model}' (dim: {provider.dimension}, norm: {norm:.4f})")
    except Exception as e:
        print(f"  ! Ollama connection failed ({e}). Falling back to MockEmbeddingProvider.")
        provider = create_embedding_provider("mock", dimension=768)
        test_vec = await provider.embed_query("ping")
        print(f"  ✓ Initialized Mock provider (dim: {provider.dimension})")

    # 2. EpisodicStore with sqlite-vec
    print("\n[Step 2/6] Initializing EpisodicStore with sqlite-vec...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "smoke_memory.db"
        store = EpisodicStore(db_path, embedding_dim=768)
        if not store._vec_enabled:
            print("  ✗ FAILED: sqlite-vec extension was not loaded into SQLite!")
            return 1
        print("  ✓ sqlite-vec extension loaded and virtual table vec_turns created.")

        # 3. Log conversation turns
        print("\n[Step 3/6] Logging multi-topic conversation turns across sessions...")
        corpus = [
            ("sess-hw", "user", "My MacBook Pro has an Apple M3 Max chip with 36GB unified memory."),
            (
                "sess-food",
                "user",
                "In Bavaria, traditional breakfast includes Weisswurst with sweet mustard and pretzels.",
            ),
            ("sess-hike", "user", "I really enjoy hiking near Lake Tegernsee and Wallberg mountain in Upper Bavaria."),
            ("sess-riva", "user", "We are developing Riva as a local-first privacy-respecting personal AI assistant."),
        ]

        turn_ids = []
        for sid, role, text in corpus:
            tid = store.log_turn(sid, role, text)
            turn_ids.append((tid, sid, text))
            print(f'  ✓ Turn #{tid} [{sid}]: "{text[:50]}..."')

        # 4. Ingest embeddings
        print("\n[Step 4/6] Embedding and indexing turns into vec_turns...")
        texts = [t[2] for t in turn_ids]
        vectors = await provider.embed_documents(texts)
        for (tid, sid, text), vec in zip(turn_ids, vectors):
            store.add_embedding(tid, vec, session_id=sid, content=text)
            print(f"  ✓ Indexed Turn #{tid} (vector dim={len(vec)})")

        stats = store.get_stats()
        print(f"  ✓ Store stats: {stats['turns']} turns, {stats['embeddings']} vector embeddings indexed.")
        assert stats["embeddings"] == 4
        assert stats["turns"] == 4

        # 5. Semantic recall queries
        print("\n[Step 5/6] Performing zero-keyword semantic recall queries...")
        queries = [
            ("What computer hardware and RAM do I have?", "sess-hw"),
            ("What typical Bavarian breakfast or sausages do you recommend?", "sess-food"),
            ("What are good outdoor trails or alpine peaks to explore?", "sess-hike"),
        ]

        for q_text, expected_sess in queries:
            print(f'\n  Query: "{q_text}"')
            q_vec = await provider.embed_query(q_text)
            matches = store.search_similar(q_vec, top_k=2)

            if not matches:
                print("  ✗ No matches found!")
                return 1

            top = matches[0]
            sim = 1.0 - top.distance
            status = "✓ MATCH" if top.session_id == expected_sess else "✗ UNEXPECTED"
            print(f"    {status} Top: Turn #{top.turn_id} (sim={sim:.3f}, dist={top.distance:.4f}) [{top.session_id}]")
            print(f'      "{top.content}"')
            assert top.session_id == expected_sess, f"Expected {expected_sess}, got {top.session_id}"

        # Test session exclusion
        print("\n  Testing session exclusion filter:")
        q_vec = await provider.embed_query("Tell me about my laptop specs")
        matches_filtered = store.search_similar(q_vec, top_k=2, exclude_session_id="sess-hw")
        top_sess_filtered = matches_filtered[0].session_id if matches_filtered else "None"
        print(f"    ✓ Query with exclude_session_id='sess-hw' returned top: '{top_sess_filtered}' (sess-hw excluded)")
        assert top_sess_filtered != "sess-hw"

        # 6. SQL Database Trigger cascading deletions
        print("\n[Step 6/6] Testing SQL Trigger cascade deletion (deleting Turn #1)...")
        target_tid = turn_ids[0][0]
        assert store.has_embedding(target_tid) is True

        # Call store.delete_turn which triggers AFTER DELETE ON turns
        deleted = store.delete_turn(target_tid)
        assert deleted is True

        # Verify vector embedding was purged automatically
        has_emb = store.has_embedding(target_tid)
        stats_after = store.get_stats()
        print(f"  ✓ Turn #{target_tid} deleted.")
        print(f"  ✓ has_embedding({target_tid}) = {has_emb}")
        print(f"  ✓ Store stats after deletion: {stats_after['turns']} turns, {stats_after['embeddings']} embeddings.")
        assert has_emb is False
        assert stats_after["turns"] == 3
        assert stats_after["embeddings"] == 3
        print("  ✓ SQL Trigger 'trg_turns_delete_embeddings' cascaded delete cleanly!")

    await provider.close()
    print("\n" + "=" * 60)
    print("  ALL M4 PHASE 1 & 2 SMOKE TESTS PASSED SUCCESSFULLY! ")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_smoke_test()))
