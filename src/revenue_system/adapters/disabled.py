"""Fail explicitly when an integration has not been enabled."""


class DisabledIntegration:
    def __init__(self, name: str):
        self.name = name

    def _refuse(self):
        raise RuntimeError(f"{self.name} is disabled; configure its live mode before executing this action")

    async def send(self, recipient, subject, body, idempotency_key):
        self._refuse()

    async def send_for_signature(self, document, idempotency_key):
        self._refuse()

    async def get_transcript(self, transcript_id):
        self._refuse()
