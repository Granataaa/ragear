"""
Benchmark CLI tool for evaluating RAGEAR recommendations against queries in queries.txt.
"""

import os
import sys
import time
import argparse
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas.models import RecommendationRequest
from app.services.recommender import recommender

async def run_benchmarks(query_limit: int = 5, top_k: int = 50):
    queries_file = Path("queries.txt")
    if not queries_file.exists():
        print("queries.txt not found in current directory.")
        return

    with open(queries_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    print(f"=== RAGEAR BENCHMARK EVALUATION ===")
    print(f"Total queries available: {len(lines)}")
    print(f"Executing first {query_limit} queries with Top K = {top_k} chunks...\n")

    latencies = []

    for idx, q in enumerate(lines[:query_limit], start=1):
        print(f"--------------------------------------------------------------------------------")
        print(f"Query #{idx}: \"{q[:80]}...\"" if len(q) > 80 else f"Query #{idx}: \"{q}\"")

        req = RecommendationRequest(question=q, top_k_chunks=top_k)
        start = time.time()
        try:
            res = await recommender.recommend(req)
            elapsed = time.time() - start
            latencies.append(elapsed)

            print(f"Latency: {elapsed:.3f}s | Evaluated Chunks: {res.total_candidates_evaluated}")
            print(f"Top Recommended Courses:")
            if not res.recommendations:
                print("   (Nessun corso raccomandato)")
            for r in res.recommendations[:3]:
                print(f"   #{r.rank} [{r.confidence_percent}%] {r.course_title} ({r.facolta} - {r.cfu or '?'} CFU)")
                print(f"       Score: {r.recommendation_score:.6f} | Match lezioni: {len(r.matched_lessons)}")
        except Exception as e:
            print(f"   [ERRORE]: {e}")

    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        print(f"\n================================================================================")
        print(f"BENCHMARK COMPLETED: {len(latencies)} queries")
        print(f"Average latency: {avg_lat:.3f}s | Min: {min(latencies):.3f}s | Max: {max(latencies):.3f}s")
        print(f"================================================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RAGEAR benchmark queries.")
    parser.add_argument("--limit", type=int, default=5, help="Number of queries to run")
    parser.add_argument("--top-k", type=int, default=50, help="Number of chunks to evaluate")
    args = parser.parse_args()

    asyncio.run(run_benchmarks(query_limit=args.limit, top_k=args.top_k))
