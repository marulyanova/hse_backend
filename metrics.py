from prometheus_client import Counter, Histogram

AUTH_REQUESTS_TOTAL = Counter(
    "auth_requests_total",
    "Total number of authentication requests",
    ["status"],
)

AUTH_REQUEST_DURATION = Histogram(
    "auth_request_duration_seconds",
    "Time spent on authentication requests",
    ["endpoint"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

AUTH_FAILURES_TOTAL = Counter(
    "auth_failures_total",
    "Number of failed authentication attempts",
    ["reason"],
)

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

PREDICTIONS_TOTAL = Counter(
    "predictions_total", "Total number of predictions", ["result"]
)

PREDICTION_DURATION = Histogram(
    "prediction_duration_seconds",
    "Time spent on ML model inference",
    ["model_name"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

PREDICTION_ERRORS_TOTAL = Counter(
    "prediction_errors_total", "Number of prediction errors", ["error_type"]
)

DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Database query duration",
    ["query_type", "table"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

MODEL_PREDICTION_PROBABILITY = Histogram(
    "model_prediction_probability",
    "Distribution of violation probabilities from ML model",
    ["model_name"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
