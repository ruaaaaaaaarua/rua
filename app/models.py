from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator
from .classification import optional_classification


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Option(StrictModel):
    key: str = Field(min_length=1)
    text: str = Field(min_length=1)


Answer = Union[str, List[str]]


def normalize_answer(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return ''.join(sorted(str(item).strip() for item in value if str(item).strip()))
    return str(value).strip()


class ExtractedQuestion(StrictModel):
    number: Optional[Union[int, str]] = None
    kind: Literal['single', 'multiple', 'judge']
    text: str = Field(min_length=1)
    options: List[Option] = Field(default_factory=list)
    user_answer: str = ''
    subject: str = '电力系统分析'
    chapter: str = '待归类'
    knowledge: str = '待归类'
    attachment_id: Optional[str] = None
    recognition_note: Optional[str] = None
    incomplete: bool = False

    @field_validator('user_answer', mode='before')
    @classmethod
    def normalize_user_answer(cls, value):
        return normalize_answer(value) or ''


class ExtractedQuestions(RootModel[List[ExtractedQuestion]]):
    pass


class Solution(StrictModel):
    answer: Answer
    explanation: str = Field(min_length=1)
    valid: bool = True
    status: Literal['confirmed', 'pending'] = 'confirmed'
    classification: Optional[dict] = None

    @field_validator('classification', mode='before')
    @classmethod
    def tolerate_optional_metadata(cls, value):
        return optional_classification(value)

    @field_validator('answer', mode='before')
    @classmethod
    def normalize_output_answer(cls, value):
        return normalize_answer(value)

    @model_validator(mode='after')
    def answer_matches_status(self):
        if not self.answer and self.valid and self.status == 'confirmed':
            raise ValueError('empty answer requires pending status')
        return self


class BatchedSolution(Solution):
    index: int = Field(ge=0)


class BatchedSolutions(RootModel[List[BatchedSolution]]):
    pass


class ChatReply(StrictModel):
    content: str = Field(min_length=1)


class ReferenceExtraction(StrictModel):
    content: str = Field(min_length=1)


def validate_choice_answer(kind, options, answer):
    answer = normalize_answer(answer)
    if kind == 'multiple':
        import re
        answer = re.sub(r'[,，、\s]+', '', answer or '')
    if kind == 'judge':
        if answer not in {'正确', '错误'}:
            raise ValueError('判断题答案应为正确或错误')
        return
    keys = [o.key.strip() for o in options]
    if not keys or len(keys) != len(set(keys)):
        raise ValueError('选项键必须唯一')
    if kind == 'single':
        if answer not in keys:
            raise ValueError('请选择一个有效选项')
        return
    if kind != 'multiple' or not answer or len(answer) != len(set(answer)) or not set(answer).issubset(keys):
        raise ValueError('请选择有效选项，多选不得重复')
