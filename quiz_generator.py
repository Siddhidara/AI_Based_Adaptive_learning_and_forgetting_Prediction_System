"""
quiz_generator.py - Quiz Generation Module
Uses the Groq API to generate 10 MCQ questions from a summary.
"""

import os
import json
import re
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

QUIZ_PROMPT_TEMPLATE = """Create exactly 10 multiple choice questions based on this text.

Return ONLY a JSON array. No explanation. No markdown. No code blocks.
Start with [ and end with ]

Each item must follow this exact structure:
{{"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, "correct_answer": "A"}}

TEXT:
{summary}"""


def generate_quiz(summary: str) -> list:
    """Call Groq API and return list of 10 MCQ question dicts."""

    print("[quiz_generator] Calling Groq API …")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": QUIZ_PROMPT_TEMPLATE.format(summary=summary)
            }
        ],
        temperature=0.9,
        max_tokens=3000,
    )

    raw = response.choices[0].message.content.strip()

    # ── DEBUG: print exactly what came back ──────────────────
    print("=" * 60)
    print("[quiz_generator] RAW RESPONSE FROM GROQ:")
    print(raw[:2000])
    print("=" * 60)

    questions = _parse_quiz_response(raw)
    print(f"[quiz_generator] Parsed {len(questions)} question(s).")
    return questions


def _parse_quiz_response(raw: str) -> list:
    """Robustly parse JSON from Groq response."""

    # Step 1: strip markdown fences
    raw = re.sub(r"```json", "", raw)
    raw = re.sub(r"```",     "", raw)
    raw = raw.strip()

    # Step 2: extract the JSON array between first [ and last ]
    start = raw.find("[")
    end   = raw.rfind("]")

    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]
    else:
        raise ValueError(
            f"No JSON array found in response. Got:\n{raw[:500]}"
        )

    # Step 3: fix common JSON issues
    raw = re.sub(r",\s*]", "]", raw)
    raw = re.sub(r",\s*}", "}", raw)

    # Step 4: parse
    try:
        questions = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON parse failed: {exc}\nCleaned response:\n{raw[:500]}"
        ) from exc

    # Step 5: unwrap if model returned {"questions": [...]}
    if isinstance(questions, dict):
        for value in questions.values():
            if isinstance(value, list):
                questions = value
                break

    if not isinstance(questions, list) or len(questions) == 0:
        raise ValueError("Expected a non-empty JSON array of questions.")

    # Step 6: validate each question has required fields
    validated = []
    for item in questions:
        if (
            isinstance(item, dict)
            and "question"       in item
            and "options"        in item
            and "correct_answer" in item
            and isinstance(item["options"], dict)
        ):
            validated.append(item)

    if len(validated) == 0:
        raise ValueError(
            f"No valid questions found. Raw questions: {questions[:2]}"
        )

    return validated