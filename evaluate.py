"""Evaluate real chatbot answers; automated checks do not prove factual accuracy."""

import argparse
import asyncio
import csv
import hashlib
import json
import math
import re
import time
from pathlib import Path
from unittest.mock import patch

from langchain_core.callbacks import BaseCallbackHandler
from langchain_tavily import TavilySearch

import agent
from agent import chat
from router import classify_intent
from website import search_terms


def load_questions(dataset):
    if dataset.suffix.casefold() == ".csv":
        with dataset.open(encoding="utf-8-sig", newline="") as file:
            rows = [{"id": int(row["ID"]), "category": row["Category"],
                     "question": row["Question"].strip()} for row in csv.DictReader(file)]
    else:
        rows = json.loads(dataset.read_text(encoding="utf-8"))
    if len({row["id"] for row in rows}) != len(rows) or any(not row["question"].strip() for row in rows):
        raise ValueError("Questions need unique IDs and nonempty text")
    return rows


def provider_limit(provider, error):
    """Classify provider failures without saving messages that could expose keys."""
    status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    text = str(error).casefold()
    if status in (402, 432) or re.search(r"(?:credit|balance).{0,50}(?:exhaust|insufficient|deplet)|"
                                      r"insufficient.{0,30}(?:credit|balance)|usage limit.{0,30}(?:exceed|reach)|"
                                      r"exceed.{0,50}(?:quota|usage limit|credits)", text):
        kind = "credits_exhausted"
    elif re.search(r"(?:per day|per_day|daily|\brpd\b|\btpd\b)", text) and re.search(r"limit|quota|exceed", text):
        kind = "daily_quota_reached"
    elif re.search(r"(?:quota.{0,30}(?:exceed|exhaust)|insufficient_quota)", text):
        kind = "quota_exhausted"
    elif status == 429 or "ratelimit" in type(error).__name__.casefold() or "rate limit" in text:
        kind = "temporary_rate_limit"
    elif status in (401, 403):
        kind = "authentication_or_access_error"
    else:
        return None
    return {"provider": provider, "kind": kind, "http_status": status}


class LimitMonitor(BaseCallbackHandler):
    def __init__(self, provider, events):
        self.provider, self.events = provider, events

    def on_llm_error(self, error, **kwargs):
        event = provider_limit(self.provider, error)
        if event:
            self.events.append(event)


def save_report(output, questions, results, stopped=False):
    responses = sum(bool(row.get("answer", "").strip()) for row in results)
    missing = sum(bool(re.search(r"couldn['’]t find|could not find|couldn['’]t verify|"
                                 r"not (?:listed|published|available)", row.get("answer", ""), re.I)) for row in results)
    events = [event for row in results for event in row.get("provider_limits", [])]
    limits = sorted({event["provider"] + ": " + event["kind"] for event in events})
    report = (
        "# CSV chatbot test report\n\n"
        f"- Questions in this run: {len(questions)}\n"
        f"- Attempted: {len(results)}\n"
        f"- Returned a nonempty response: {responses}\n"
        f"- Request failures: {sum('error' in row for row in results)}\n"
        f"- Responses containing missing-information wording: {missing}\n"
        f"- Not attempted: {len(questions) - len(results)}\n"
        f"- Stopped because of a provider quota/access failure: {'yes' if stopped else 'no'}\n\n"
        "## Provider limits observed\n\n" + ("\n".join("- " + limit for limit in limits) or "None reported so far.")
        + "\n\nTemporary rate limits do not establish that paid credits are exhausted. "
        "Exact remaining balances are not available from this test.\n\n"
        "## Interpretation\n\nReturned responses include answers, refusals, clarifications, demo guidance "
        "and missing-information replies; they are not a factual-accuracy score. "
        "The CSV supplies no expected answers or conversation history. Each question runs independently; "
        "multi-turn behavior is therefore not established. No demo forms are submitted. "
        "Answers, evidence, provisional flags and provider-limit events are saved in the adjacent JSON file.\n"
    )
    output.with_suffix(".md").write_text(report, encoding="utf-8")

def check_answer(item, answer, evidence):
    """Flag visible problems for review, without grading truth by word overlap."""
    findings = []
    urls = {row["url"].rstrip("/") for row in evidence}
    answer_urls = re.findall(r"https?://[^\s)\]>]+", answer)
    if any(url.rstrip(".,;!?/") not in urls for url in answer_urls):
        findings.append("unverified_source_link")
    if not answer.strip():
        findings.append("empty_answer")
    if evidence:
        terms = search_terms(item["question"])
        if terms and not terms & search_terms(answer):
            findings.append("possible_irrelevant_answer")
        if re.search(r"couldn['’]t find|could not find|couldn['’]t verify|not (?:listed|published|available)", answer, re.I):
            findings.append("abstention_needs_evidence_review")
    if item.get("expected_behavior") == "demo_guidance" and "Book a Meeting" not in answer:
        findings.append("missing_demo_guidance")
    if item.get("expected_behavior") == "clarify" and "?" not in answer:
        findings.append("missing_clarification")
    if item.get("expected_behavior") == "refuse" and not re.search(
        r"can(?:not|'t|’t)|won(?:'t|’t)|couldn(?:'t|’t)|only help|"
        r"help with information published|not (?:able|provide|share|disclose|booked)|"
        r"(?:cannot|can't) verify",
        answer, re.I,
    ):
        findings.append("refusal_needs_review")
    return findings


def save_results(output, results):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)


async def main(limit, dataset, output, resume=False, timeout=120, stop_on_quota=False, delay=0):
    questions = load_questions(dataset)
    questions = questions[:limit] if limit else questions
    results = json.loads(output.read_text(encoding="utf-8")) if resume and output.exists() else []
    by_id = {row["id"]: row for row in questions}
    if any(row["id"] not in by_id or row["question"] != by_id[row["id"]]["question"] for row in results):
        raise ValueError("Saved results do not match the selected dataset")
    completed = {row["id"] for row in results}
    original_search = agent._run_search
    original_candidates = agent.model_candidates
    original_tavily = TavilySearch.invoke
    provider_events = []

    def watched_candidates(allow_tools=True):
        for provider, model in original_candidates(allow_tools):
            yield provider, model.with_config(callbacks=[LimitMonitor(provider, provider_events)])

    def watched_tavily(model, *args, **kwargs):
        try:
            response = original_tavily(model, *args, **kwargs)
        except Exception as error:
            event = provider_limit("tavily", error)
            if event:
                provider_events.append(event)
            raise
        if isinstance(response, str) or isinstance(response, dict) and response.get("error"):
            event = provider_limit("tavily", response.get("error") if isinstance(response, dict) else response)
            if event:
                provider_events.append(event)
        return response

    root = Path(__file__).parent
    runtime_fingerprint = hashlib.sha256(b"".join(
        (root / name).read_bytes() for name in
        ("agent.py", "tools.py", "website.py", "website_sources.json", "router.py", "conversation.py", "external_sources.py")
    )).hexdigest()

    for index, item in enumerate(questions):
        if item["id"] in completed:
            continue
        question = item["question"]
        history = item.get("history", [])
        page_path = item.get("page_path", "")
        intent = classify_intent(question, history, page_path)
        evidence = []
        provider_events.clear()

        async def capture_search(*args):
            result = await original_search(*args)
            if result:
                evidence.extend(result.get("results", []))
            return result

        started = time.perf_counter()
        row = {**item, "intent": intent, "evidence": evidence,
               "runtime_fingerprint": runtime_fingerprint,
               "review_status": "pending_human_review"}
        if "expected_intent" in item:
            row["route_correct"] = intent == item["expected_intent"]
        try:
            with patch("agent._run_search", side_effect=capture_search), \
                    patch("agent.model_candidates", side_effect=watched_candidates), \
                    patch.object(TavilySearch, "invoke", new=watched_tavily):
                answer = await asyncio.wait_for(chat(question, history, page_path), timeout=timeout)
            row["answer"] = answer
            row["review_flags"] = check_answer(item, answer, evidence)
        except Exception as error:
            row["error"] = type(error).__name__
            row["review_flags"] = ["request_failed"]
        row["seconds"] = round(time.perf_counter() - started, 2)
        row["provider_limits"] = list(provider_events)
        results.append(row)
        save_results(output, results)
        stopped = stop_on_quota and any(event["kind"] != "temporary_rate_limit" for event in provider_events)
        save_report(output, questions, results, stopped)
        print(f"{len(results)}/{len(questions)}: id={item['id']} {row['seconds']}s {','.join(row['review_flags']) or 'checks_clear'}", flush=True)
        if provider_events:
            print("Provider events: " + json.dumps(provider_events), flush=True)
        if stopped:
            print("Stopped on provider quota/access failure; results and report are saved.", flush=True)
            break
        if delay and index < len(questions) - 1:
            await asyncio.sleep(delay)
    print(f"Saved {output}. Automated flags are provisional; check the saved evidence.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("questions.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data" / "evaluation.json")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--stop-on-quota", action="store_true")
    parser.add_argument("--delay", type=float, default=0, help="Seconds between questions, e.g. 60 for a paced bulk test")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1 or args.timeout < 1:
        parser.error("Limit and timeout must be positive")
    if not math.isfinite(args.delay) or args.delay < 0:
        parser.error("Delay must be finite and nonnegative")
    asyncio.run(main(args.limit, args.dataset, args.output, args.resume, args.timeout, args.stop_on_quota, args.delay))
