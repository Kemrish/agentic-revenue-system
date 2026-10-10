class FixtureTranscriptAdapter:
    def __init__(self, transcripts: dict[str, str] | None = None) -> None:
        self.transcripts = transcripts or {}

    async def get_transcript(self, transcript_id: str) -> str:
        return self.transcripts[transcript_id]

