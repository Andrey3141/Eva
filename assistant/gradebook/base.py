from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StudentMatch:
    full_name: str
    row: int
    sheet: str


@dataclass
class GradeTarget:
    student: str
    sheet: str
    row: int
    column: str    # "F"
    cell: str      # "F2"


class Gradebook(ABC):
    """
    Абстракция журнала. Action и Validator работают только через этот интерфейс.
    """

    @abstractmethod
    def load(self, path: str) -> None:
        ...

    @abstractmethod
    def get_students(self) -> list[str]:
        ...

    @abstractmethod
    def find_student(self, name: str) -> list[StudentMatch]:
        ...

    @abstractmethod
    def find_grade_target(
        self,
        student: StudentMatch,
        subject: str,
        lesson: str,
    ) -> GradeTarget | None:
        ...

    @abstractmethod
    def get_grade(self, target: GradeTarget) -> int | None:
        ...

    @abstractmethod
    def set_grade(self, target: GradeTarget, grade: int) -> None:
        ...

    @abstractmethod
    def save(self) -> None:
        ...
