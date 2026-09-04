class BurqanWebhookError(Exception):
    def __init__(self, status, error, extra=None):
        super().__init__(error)
        self.status = status
        self.error = error
        self.extra = extra or {}
