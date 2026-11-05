"""The question protocol (ADR-0002): a command that needs an answer prints the question and exits 4.

The agent puts the question to the user, then runs the same command again with the
answer flag. Shared by every command that asks (plan, wrap-up, rules, setup, import).
"""

import json

NEEDS_ANSWER = 4


def ask(as_json, ask_id, question, options=None, recommended=None, context=None, answer=None, free_text=False,
        why=None):
    """Print a question for the agent to put to the user, and return exit code 4."""
    payload = {"ask": ask_id, "question": question, "options": options or [], "recommended": recommended,
               "context": context or {}, "free_text": free_text, "answer_flag": answer}
    if why:
        payload["why"] = why
    if as_json:
        print(json.dumps(payload, indent=2))
        return NEEDS_ANSWER
    print("Question (%s): %s" % (ask_id, question))
    if why:
        print("Why: %s" % why)
    for opt in payload["options"]:
        mark = "  (recommended)" if opt["value"] == recommended else ""
        print("  %s: %s%s" % (opt["value"], opt["description"] or opt["label"], mark))
    if free_text:
        print("  (a short text answer)")
    if answer:
        print("Ask the user, then run the same command again with the answer: %s" % answer)
    return NEEDS_ANSWER


def option(value, label, description=""):
    return {"value": value, "label": label, "description": description or label}
