class FixtureMailAdapter:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, recipient: str, subject: str, body: str, idempotency_key: str) -> str:
        self.sent.append({"recipient": recipient, "subject": subject, "body": body, "idempotency_key": idempotency_key})
        return f"fixture-mail:{idempotency_key}"

