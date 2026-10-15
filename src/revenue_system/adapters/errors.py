class AmbiguousDeliveryError(RuntimeError):
    """Provider may have accepted the request; stop automatic retries and reconcile."""
