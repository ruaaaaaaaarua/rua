import json
from typing import Any, Dict, Iterable


QUESTION_FIELDS = {"text", "kind", "options", "number", "subject", "chapter"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def independent_question(question: Dict[str, Any], allow_reference: bool = False) -> Dict[str, Any]:
    clean = {key: question[key] for key in QUESTION_FIELDS if key in question}
    if allow_reference and question.get("reference_note"):
        clean["reference_note"] = question["reference_note"]
    return clean


def extraction_prompt(names: Iterable[str]) -> str:
    return (
        "识别图片中的全部题目和学生作答痕迹。保留原文，不要判分。"
        "输出 JSON 数组；每项严格包含 kind(single/multiple/judge)、text、options、"
        "user_answer、reasoning、confidence(certain/unsure/guess/unknown)、subject、"
        "chapter、knowledge，并可包含 number、recognition_note。图片名："
        + _json(list(names))
    )


def solve_prompt(question: Dict[str, Any]) -> str:
    return (
        "独立解题。不得推测或迎合学生答案。若有 reference_note，将其作为待核验参考资料。"
        "只输出 JSON：answer, explanation, valid, status(confirmed/pending)。题目："
        + _json(independent_question(question, allow_reference=True))
    )


def diagnosis_prompt(question: Dict[str, Any], solution: Dict[str, Any], history: Any) -> str:
    return (
        "依据独立解答诊断学生作答，包括按含义评判简答题，禁止仅做字符串相等比较。"
        "纵览整页上下文后简短诊断，并明确区分容易混淆的假设。diagnosis 或 distinction 可为空字符串。"
        "仅当题目或答案本身确有歧义、无法可靠判断时 correct=null 且 status=pending；"
        "学生未写推理只令 reasoning_ok=null，不得因此把 correct 设为 null 或 pending。"
        "没有学生推理时不得臆测具体错误原因。knowledge_point 用一句话；diagnosis 和 distinction "
        "各限一至两句短句，默认不写长篇解释；hint 只给下一步，绝不泄露最终答案。"
        "error_type 使用 concept_error/calculation_error/formula_error/unit_error/reasoning_error/"
        "reading_error/memory_error/careless_error/answer_only/insufficient_information/unknown。"
        "只输出 JSON：correct,answer,knowledge_point,diagnosis,distinction,hint,explanation,"
        "reasoning_ok,error_type,status,source。材料："
        + _json({"question": question, "independent_solution": solution, "history": history})
    )


def chat_prompt(context: Any, text: str, mode: str) -> str:
    instruction = (
        "提示模式：只给下一步提示或概念辨析，不透露最终答案或完整解法。"
        if mode == "hint"
        else "直接模式：清楚回答问题，可在需要时解释完整解法。"
    )
    return (
        instruction
        + " 默认简短回答，只有用户明确要求详细说明时才展开。不创建测验，不修改学习状态。"
        "仅当用户明确要求操作时，可返回 action；否则省略。"
        "只输出 JSON：content，可选 correction(boolean)，可选 action={type(train/reveal/recheck/"
        "navigate/answer_quiz/retry_question/none),question_id,quiz_id,answer,purpose,reference,reasoning}。输入："
        + _json({"context": context, "text": text})
    )


def generation_prompt(context: Any, purpose: str) -> str:
    return (
        "生成一道可独立作答的电网学习题，允许 short 简答题。默认最小变式：一次只改变一个关键认知变量；"
        "允许有意义的数值替换，但不要只改选项顺序。purpose=prerequisite 时考前置知识，verify 时同层验证，"
        "variant 时同知识异情境；只有 purpose=depth 才能提高难度。只输出 JSON：kind,text,options,"
        "answer,explanation,knowledge_point,knowledge,subject,chapter,purpose；knowledge 是生成题目标知识名称。"
        "purpose 必须保持为请求值。输入："
        + _json({"context": context, "purpose": purpose})
    )


def verification_prompt(question: Dict[str, Any]) -> str:
    return (
        "独立验证题目是否成立并重新求解。你看不到生成器答案，不得猜测其答案。"
        "只输出 JSON：answer,explanation,valid,issues。题目："
        + _json(independent_question(question))
    )


def reference_extraction_prompt(names: Iterable[str]) -> str:
    return (
        "识别截图中的参考资料、题目答案和依据，忠实转写，不自行判定用户作答。"
        "只输出 JSON：content。图片名：" + _json(list(names))
    )
