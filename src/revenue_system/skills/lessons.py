from dataclasses import dataclass


@dataclass
class Lesson:
    id: str
    statement: str
    segment: str
    status: str = "proposed"
    evidence: list[str] | None = None


class LessonService:
    def __init__(self) -> None:
        self._lessons: list[Lesson] = []

    def add(self, lesson: Lesson) -> None:
        self._lessons.append(lesson)

    def active_for(self, segment: str) -> list[Lesson]:
        return [lesson for lesson in self._lessons if lesson.status == "active" and lesson.segment in {segment, "global"}]

