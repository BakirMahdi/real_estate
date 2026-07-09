"""Cooperative cancellation support shared by the orchestrator and the scrapers."""


class ScrapeCancelled(Exception):
    """Raised inside a scrape run when the user requested cancellation."""


def raise_if_cancelled(cancel_event, executor=None):
    """Raise ScrapeCancelled if the cancel event is set.

    When an executor is given, its queued futures are cancelled first so the
    surrounding `with ThreadPoolExecutor(...)` block doesn't wait for every
    pending request before the exception can propagate.
    """
    if cancel_event is not None and cancel_event.is_set():
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        raise ScrapeCancelled()
