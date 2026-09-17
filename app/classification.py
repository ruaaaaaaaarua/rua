"""Validated, conservative question-demand classification."""
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

METHODS = {
    "concept": "概念辨析", "calculation": "计算求解", "comparison": "方案比较",
    "condition": "适用条件", "judgment": "正误判断",
}
VARIANTS = {"direct": "直接应用", "inverse": "逆向求解", "boundary": "边界条件", "composite": "综合分析"}
DIFFICULTIES = {"basic": "基础", "intermediate": "进阶", "advanced": "挑战"}


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_ids: list[str] = Field(min_length=1, max_length=5)
    primary_knowledge_id: str
    method: Literal[tuple(METHODS)]
    variant: Literal[tuple(VARIANTS)]
    conditions: list[str] = Field(min_length=1, max_length=8)
    difficulty: Literal["basic", "intermediate", "advanced"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def consistent(self):
        self.knowledge_ids = list(dict.fromkeys(v.strip() for v in self.knowledge_ids if v.strip()))
        self.conditions = sorted(set(re.sub(r"\s+", " ", v.strip()).casefold()
                                     for v in self.conditions if v.strip()))
        required = ('target:', 'method:', 'boundary:')
        if (not self.knowledge_ids or self.primary_knowledge_id not in self.knowledge_ids or
                any(not any(v.startswith(prefix) and len(v) > len(prefix) for v in self.conditions)
                    for prefix in required)):
            raise ValueError("分类的知识点与区分条件不完整")
        return self


def validate_classification(value, known_ids=None):
    item = Classification.model_validate(value)
    if known_ids is not None and any(k not in known_ids for k in item.knowledge_ids):
        raise ValueError("分类包含未知知识点")
    return item.model_dump()


def optional_classification(value):
    try:
        return validate_classification(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def group_key(classification, links):
    if not classification or classification.get("source") != "manual" and classification.get("confidence", 0) < .8:
        return None
    conditions = classification.get("conditions") or []
    linked = sorted(link["knowledge_id"] for link in links)
    classified = sorted(classification.get("knowledge_ids") or [])
    if not conditions or linked != classified:
        return None
    return json.dumps([classification["method"], classification["variant"], conditions, linked],
                      ensure_ascii=False, separators=(",", ":"))


def taxonomy():
    return {
        "methods": [{"id": key, "label": value} for key, value in METHODS.items()],
        "variants": [{"id": key, "label": value} for key, value in VARIANTS.items()],
        "difficulties": [{"id": key, "label": value} for key, value in DIFFICULTIES.items()],
        "condition_requirements": ["target:", "method:", "boundary:"],
    }
