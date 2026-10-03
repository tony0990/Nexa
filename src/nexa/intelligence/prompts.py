from datetime import datetime
from typing import List, Tuple

# Versioning is required for the golden-file suite (§5.2)
PROMPT_VERSION = "v1.0.0"

# System prompt copied verbatim from §5.1
SYSTEM_PROMPT = """You are an extraction engine for meeting transcripts. Your ONLY job is to find
action items that have an explicit task and, ideally, a clear owner and/or
date/time commitment.

STRICT RULES:
1. Output ONLY valid JSON matching the given schema. No prose, no markdown,
   no explanation, no leading/trailing text.
2. If a sentence discusses something in general terms with no specific
   commitment to do something by/on a specific time, DO NOT extract it.
3. NEVER invent a date, time, or owner that was not explicitly stated in
   the text. If unstated, leave the field null.
4. Preserve the EXACT original wording for evidence_text and any raw_date /
   raw_time / owner_text fields you extract — do not translate, correct
   grammar, or paraphrase them.
5. The text may mix Arabic and English within the same sentence
   (code-switching). Treat this as normal and extract from it directly.
6. When in doubt about whether something is an actionable commitment,
   DO NOT extract it. Precision matters far more than completeness.
"""

# Few-shot library covering the 10 mandatory scenarios from §5.2
FEW_SHOT_EXAMPLES = [
    {
        "scenario": "Clear task + owner + date",
        "input": "أحمد، لازم تخلص الـ report بكرة الساعة 10 الصبح",
        "output": '{"items": [{"task": "تخلص الـ report", "owner_text": "أحمد", "raw_date_phrase": "بكرة", "raw_time_phrase": "الساعة 10 الصبح", "confidence": 0.9, "needs_review": false, "evidence_text": "أحمد، لازم تخلص الـ report بكرة الساعة 10 الصبح", "evidence_span": [0, 45], "extraction_id": "uuid-1"}]}'
    },
    {
        "scenario": "Pure discussion, zero commitments (Variant 1)",
        "input": "إحنا محتاجين نفكر في موضوع الـ budget للسنة الجاية",
        "output": '{"items": []}'
    },
    {
        "scenario": "Pure discussion, zero commitments (Variant 2)",
        "input": "The current progress is okay but we might need more resources",
        "output": '{"items": []}'
    },
    {
        "scenario": "Pure discussion, zero commitments (Variant 3)",
        "input": "I think the meeting was productive, let's just keep in touch",
        "output": '{"items": []}'
    },
    {
        "scenario": "Multiple actions in one long segment",
        "input": "سارة، ابعتي الإيميل للعميل بكرة، ومحمد يجهز الـ presentation يوم الحد",
        "output": '{"items": [{"task": "ابعتي الإيميل للعميل", "owner_text": "سارة", "raw_date_phrase": "بكرة", "raw_time_phrase": null, "confidence": 0.9, "needs_review": false, "evidence_text": "سارة، ابعتي الإيميل للعميل بكرة", "evidence_span": [0, 30], "extraction_id": "uuid-2"}, {"task": "يجهز الـ presentation", "owner_text": "محمد", "raw_date_phrase": "يوم الحد", "raw_time_phrase": null, "confidence": 0.9, "needs_review": false, "evidence_text": "محمد يجهز الـ presentation يوم الحد", "evidence_span": [32, 65], "extraction_id": "uuid-3"}]}'
    },
    {
        "scenario": "Task with no stated owner",
        "input": "لازم نبعت الـ feedback للشركة قبل يوم الخميس",
        "output": '{"items": [{"task": "نبعت الـ feedback للشركة", "owner_text": null, "raw_date_phrase": "قبل يوم الخميس", "raw_time_phrase": null, "confidence": 0.7, "needs_review": true, "evidence_text": "لازم نبعت الـ feedback للشركة قبل يوم الخميس", "evidence_span": [0, 40], "extraction_id": "uuid-4"}]}'
    },
    {
        "scenario": "Task with no stated time/date",
        "input": "أحمد، ابعتلي الـ file دلوقتي",
        "output": '{"items": [{"task": "ابعتلي الـ file", "owner_text": "أحمد", "raw_date_phrase": null, "raw_time_phrase": null, "confidence": 0.8, "needs_review": false, "evidence_text": "أحمد، ابعتلي الـ file دلوقتي", "evidence_span": [0, 25], "extraction_id": "uuid-5"}]}'
    },
    {
        "scenario": "Pure Arabic sentence",
        "input": "منى، جهزي الاجتماع الجاي يوم الثلاثاء",
        "output": '{"items": [{"task": "جهزي الاجتماع الجاي", "owner_text": "منى", "raw_date_phrase": "يوم الثلاثاء", "raw_time_phrase": null, "confidence": 0.9, "needs_review": false, "evidence_text": "منى، جهزي الاجتماع الجاي يوم الثلاثاء", "evidence_span": [0, 35], "extraction_id": "uuid-6"}]}'
    },
    {
        "scenario": "Pure English sentence",
        "input": "John, please finish the documentation by Friday",
        "output": '{"items": [{"task": "finish the documentation", "owner_text": "John", "raw_date_phrase": "by Friday", "raw_time_phrase": null, "confidence": 0.9, "needs_review": false, "evidence_text": "John, please finish the documentation by Friday", "evidence_span": [0, 45], "extraction_id": "uuid-7"}]}'
    },
    {
        "scenario": "Code-switched sentence",
        "input": "لازم نخلص الـ deployment before Friday",
        "output": '{"items": [{"task": "نخلص الـ deployment", "owner_text": null, "raw_date_phrase": "before Friday", "raw_time_phrase": null, "confidence": 0.8, "needs_review": true, "evidence_text": "لازم نخلص الـ deployment before Friday", "evidence_span": [0, 35], "extraction_id": "uuid-8"}]}'
    },
    {
        "scenario": "Vague/soft language",
        "input": "محتاجين نفكر في طريقة لتحسين الـ performance",
        "output": '{"items": []}'
    },
    {
        "scenario": "Duplicate-name ambiguity",
        "input": "قول لأحمد يجهز الـ slide",
        "output": '{"items": [{"task": "يجهز الـ slide", "owner_text": "أحمد", "raw_date_phrase": null, "raw_time_phrase": null, "confidence": 0.7, "needs_review": false, "evidence_text": "قول لأحمد يجهز الـ slide", "evidence_span": [0, 25], "extraction_id": "uuid-9"}]}'
    },
]

def build_extraction_prompt(segment_text: str, reference_datetime: datetime) -> str:
    """
    Builds the prompt for the LLM.
    Embeds reference_datetime to ground relative phrases (§5.3).
    """
    ref_str = reference_datetime.strftime("%A %Y-%m-%d %H:%M, Africa/Cairo")

    prompt = f"{SYSTEM_PROMPT}\n\n"
    prompt += f"Reference date/time: {ref_str}\n\n"

    # Add few-shots
    for ex in FEW_SHOT_EXAMPLES:
        prompt += f"Input: {ex['input']}\nOutput: {ex['output']}\n\n"

    prompt += f"Input: {segment_text}\nOutput: "
    return prompt
