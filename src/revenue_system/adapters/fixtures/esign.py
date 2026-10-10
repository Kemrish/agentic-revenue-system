class FixtureESignAdapter:
    async def send_for_signature(self, document: str, idempotency_key: str) -> str:
        return f"fixture-envelope:{idempotency_key}"

