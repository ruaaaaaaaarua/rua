from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(StrictModel):
    key: str = Field(min_length=1)
    text: str = Field(min_length=1)


Answer = Union[str, List[str]]


def normalize_answer(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        items = (str(item).strip() for item in value)
        return "".join(sorted(item for item in items if item))
    return str(value).strip()


class ExtractedQuestion(StrictModel):
    number: Optional[Union[int, str]] = None
    kind: Literal["single", "multiple", "judge"]
    text: str = Field(min_length=1)
    options: List[Option] = Field(default_factory=list)
    user_answer: str = ""
    reasoning: str = ""
    confidence: Literal["certain", "unsure", "guess", "unknown"] = "unknown"
    subject: str = Field(min_length=1)
    chapter: str = Field(min_length=1)
    knowledge: str = Field(min_length=1)
    attachment_id: Optional[str] = None
    recognition_note: Optional[str] = None

    @field_validator("user_answer", mode="before")
    @classmethod
    def normalize_user_answer(cls, value: Any) -> str:
        return normalize_answer(value) or ""

    @field_validator("reasoning", mode="before")
    @classmethod
    def normalize_reasoning(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()


class ExtractedQuestions(RootModel[List[ExtractedQuestion]]):
    pass


class Solution(StrictModel):
    answer: Answer
    explanation: str = Field(min_length=1)
    valid: bool = True
    status: Literal["confirmed", "pending"] = "confirmed"

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_output_answer(cls, value: Any) -> Any:
        return normalize_answer(value)

    @model_validator(mode="after")
    def answer_matches_status(self):
        empty = not self.answer if isinstance(self.answer, list) else not self.answer.strip()
        if empty and self.valid and self.status != "pending":
            raise ValueError("empty answer is only valid for pending or invalid solutions")
        return self


class BatchedSolution(Solution):
    index: int = Field(ge=0)


class BatchedSolutions(RootModel[List[BatchedSolution]]):
    pass


class Diagnosis(StrictModel):
    correct: Optional[bool]
    answer: Optional[Answer] = None
    knowledge_point: str = Field(min_length=1)
    diagnosis: str = ""
    distinction: str = ""
    hint: str = Field(min_length=1)
    explanation: Optional[str] = None
    reasoning_ok: Optional[bool]
    error_type: Optional[
        Literal[
            "concept_error",
            "calculation_error",
            "formula_error",
            "unit_error",
            "reasoning_error",
            "reading_error",
            "memory_error",
            "careless_error",
            "answer_only",
            "insufficient_information",
            "unknown",
        ]
    ] = None
    status: Literal["confirmed", "pending"]
    source: Literal["model", "reference", "review"] = "model"

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_output_answer(cls, value: Any) -> Any:
        return normalize_answer(value)

    @model_validator(mode="after")
    def correctness_matches_status(self):
        if self.status == "pending" and self.correct is not None:
            raise ValueError("pending diagnosis must not claim correctness")
        if self.status == "confirmed" and self.correct is None:
            raise ValueError("confirmed diagnosis must claim correctness")
        return self


class BatchedDiagnosis(Diagnosis):
    index: int = Field(ge=0)


class BatchedDiagnoses(RootModel[List[BatchedDiagnosis]]):
    pass


class ChatAction(StrictModel):
    type: Literal["train", "reveal", "recheck", "navigate", "answer_quiz", "retry_question", "none"]
    question_id: Optional[str] = None
    knowledge_id: Optional[str] = None
    purpose: Optional[Literal["variant", "verify", "prerequisite", "depth"]] = None
    reference: Optional[str] = None
    quiz_id: Optional[str] = None
    answer: Optional[Answer] = None
    reasoning: Optional[str] = None

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_output_answer(cls, value: Any) -> Any:
        return normalize_answer(value)

    @model_validator(mode="after")
    def required_action_arguments(self):
        if self.type == "train" and not self.purpose:
            raise ValueError("train action requires purpose")
        if self.type == "answer_quiz" and (not self.quiz_id or self.answer is None):
            raise ValueError("answer_quiz action requires quiz_id and answer")
        if self.type == "recheck" and (not self.question_id or not self.reference):
            raise ValueError("recheck action requires question_id and reference")
        return self


class ChatReply(StrictModel):
    content: str = Field(min_length=1)
    correction: Optional[bool] = None
    action: Optional[ChatAction] = None


class GeneratedQuestion(StrictModel):
    kind: Literal["single", "multiple", "judge", "short"]
    text: str = Field(min_length=1)
    options: List[Option] = Field(default_factory=list)
    answer: Answer
    explanation: str = Field(min_length=1)
    knowledge_point: str = Field(min_length=1)
    knowledge: str = Field(min_length=1)
    subject: Optional[str] = None
    chapter: Optional[str] = None
    purpose: Literal["variant", "verify", "prerequisite", "depth"]

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_output_answer(cls, value: Any) -> Any:
        return normalize_answer(value)

    @model_validator(mode="after")
    def valid_answer_shape(self):
        validate_choice_answer(self.kind, self.options, self.answer)
        return self


class Verification(StrictModel):
    answer: Answer
    explanation: str = Field(min_length=1)
    valid: bool
    issues: List[str] = Field(default_factory=list)

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_output_answer(cls, value: Any) -> Any:
        return normalize_answer(value)

    @model_validator(mode="after")
    def invalid_may_have_empty_answer(self):
        empty = not self.answer if isinstance(self.answer, list) else not self.answer.strip()
        if empty and self.valid:
            raise ValueError("valid verification requires an answer")
        return self


class ReferenceExtraction(StrictModel):
    content: str = Field(min_length=1)


def validate_choice_answer(kind: str, options: List[Option], answer: Answer) -> None:
    if kind == "short":
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("short answer must be non-empty text")
        return
    if kind == "judge":
        if not isinstance(answer, str) or answer.strip() not in {"正确", "错误"}:
            raise ValueError("judge answer must be 正确 or 错误")
        return
    keys = [option.key.strip() for option in options]
    if not keys or len(keys) != len(set(keys)):
        raise ValueError("choice options require unique keys")
    if kind == "single":
        if not isinstance(answer, str) or answer.strip() not in keys:
            raise ValueError("single answer must be one option key")
        return
    values = answer if isinstance(answer, list) else list(answer.strip())
    normalized = [str(item).strip() for item in values]
    if not normalized or len(normalized) != len(set(normalized)) or not set(normalized).issubset(keys):
        raise ValueError("multiple answer must be a unique set of option keys")
