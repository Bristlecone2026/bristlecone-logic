import asyncio
import time
import warnings
import httpx

# Target Nginx proxy container via Docker bridge DNS
TARGET_URL = "https://bristlecone_proxy/api/v1/keys/test-metered"
API_KEY = "bl_test_key_2026"
CONCURRENCY = 50       # Parallel worker tasks
TOTAL_REQUESTS = 150   # Total requests to fire

warnings.filterwarnings("ignore")  # Suppress SSL warnings for self-signed proxy cert

async def send_request(client: httpx.AsyncClient, req_id: int) -> dict:
    headers = {"X-API-Key": API_KEY}
    start_time = time.perf_counter()
    try:
        response = await client.post(TARGET_URL, headers=headers)
        elapsed = time.perf_counter() - start_time
        return {
            "req_id": req_id,
            "status": response.status_code,
            "latency": elapsed,
            "rate_limit_remaining": response.headers.get("x-ratelimit-remaining"),
            "error": None
        }
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        return {
            "req_id": req_id,
            "status": 0,
            "latency": elapsed,
            "rate_limit_remaining": None,
            "error": str(e)
        }

async def run_load_test():
    print("=" * 60)
    print(f"🚀 BRISTLECONE M2M SWARM LOAD TEST")
    print(f"Target:      {TARGET_URL}")
    print(f"Concurrency: {CONCURRENCY} workers")
    print(f"Total Reqs:  {TOTAL_REQUESTS} requests")
    print("=" * 60)

    limits = httpx.Limits(max_keepalive_connections=CONCURRENCY, max_connections=CONCURRENCY * 2)
    
    async with httpx.AsyncClient(verify=False, limits=limits, timeout=15.0) as client:
        sem = asyncio.Semaphore(CONCURRENCY)

        async def worker(req_id: int):
            async with sem:
                return await send_request(client, req_id)

        start_time = time.perf_counter()
        tasks = [worker(i) for i in range(1, TOTAL_REQUESTS + 1)]
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

    # Process Results
    status_counts = {}
    latencies = []
    errors = []

    for r in results:
        status = r["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        latencies.append(r["latency"])
        if r["error"]:
            errors.append(r["error"])

    avg_latency = (sum(latencies) / len(latencies)) * 1000 if latencies else 0
    sorted_lat = sorted(latencies)
    p95_latency = sorted_lat[int(len(sorted_lat) * 0.95)] * 1000 if latencies else 0
    p99_latency = sorted_lat[int(len(sorted_lat) * 0.99)] * 1000 if latencies else 0
    rps = TOTAL_REQUESTS / total_time if total_time > 0 else 0

    print("\n📊 EXECUTION SUMMARY")
    print("-" * 60)
    print(f"Total Duration:     {total_time:.3f} seconds")
    print(f"Throughput:         {rps:.2f} req/sec")
    print(f"Avg Latency:        {avg_latency:.2f} ms")
    print(f"P95 Latency:        {p95_latency:.2f} ms")
    print(f"P99 Latency:        {p99_latency:.2f} ms")
    
    print("\nHTTP Response Breakdown:")
    for code, count in sorted(status_counts.items()):
        label = "Connection Error" if code == 0 else f"HTTP {code}"
        if code == 200:
            desc = "(Success & Metered)"
        elif code == 429:
            desc = "(Rate Limited via Redis)"
        elif code == 500:
            desc = "(Internal Error / Lock Failure)"
        else:
            desc = ""
        print(f"  [{label}] {desc}: {count}")

    if errors:
        print(f"\n⚠️ Encountered {len(errors)} client-level connection errors.")
        print(f"  Sample error: {errors[0]}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_load_test())
