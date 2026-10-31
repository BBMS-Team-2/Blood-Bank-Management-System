import time
from django.db import connection


class PerformanceTimingMiddleware:
    """
    BB-NF-001: Performance Monitoring Middleware (TC-PERF-01)
    Measures request latency and tracks database query profiling metrics:
    - X-Response-Time: formatted in seconds (SLA target < 3.0s)
    - X-DB-Queries: total SQL queries executed during the request lifecycle
    - Server-Timing: standard W3C Server-Timing header for browser & APM tools
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        query_count = 0
        sql_time = 0.0

        def query_counter(execute, sql, params, many, context):
            nonlocal query_count, sql_time
            query_count += 1
            t0 = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                sql_time += (time.perf_counter() - t0)

        start_time = time.perf_counter()
        with connection.execute_wrapper(query_counter):
            response = self.get_response(request)
        duration = time.perf_counter() - start_time

        response['X-Response-Time'] = f"{duration:.4f}s"
        response['X-DB-Queries'] = str(query_count)
        response['Server-Timing'] = (
            f"total;dur={duration * 1000:.2f}, "
            f"sql;dur={sql_time * 1000:.2f};count={query_count}"
        )
        return response

