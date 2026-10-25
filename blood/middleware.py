import time


class PerformanceTimingMiddleware:
    """
    BB-NF-001: Performance Monitoring Middleware (TC-PERF-01)
    Measures request latency and adds standard performance headers:
    - X-Response-Time: formatted in seconds
    - Server-Timing: standard W3C Server-Timing header for browser & APM tools
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.perf_counter()
        response = self.get_response(request)
        duration = time.perf_counter() - start_time

        response['X-Response-Time'] = f"{duration:.4f}s"
        response['Server-Timing'] = f"total;dur={duration * 1000:.2f}"
        return response
