from fastapi import Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

HTTP_REQUESTS_TOTAL = Counter(
    "bristlecone_http_requests_total",
    "Total HTTP requests processed by the API gateway",
    ["method", "endpoint", "status_code"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "bristlecone_http_request_duration_seconds",
    "HTTP request latency distribution in seconds",
    ["method", "endpoint"]
)

LLM_TOKENS_TOTAL = Counter(
    "bristlecone_llm_tokens_total",
    "Total tokens consumed across model executions",
    ["provider", "model"]
)

LLM_BILLED_USD_TOTAL = Counter(
    "bristlecone_llm_billed_usd_total",
    "Total USD billed for model executions",
    ["provider", "model"]
)

def metrics_response() -> Response:
    """Returns Prometheus formatted metrics response."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
