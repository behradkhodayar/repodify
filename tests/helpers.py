"""Shared test helpers for driving gated pipeline runs."""

from __future__ import annotations

import json

from langgraph.types import Command

from repodify.worker.main import run_pipeline


def invoke_through_gates(graph, initial: dict, thread_id: str, resumes: dict | None = None):
    """Run a compiled graph, auto-resuming every interrupt until completion."""
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial, config)
    while isinstance(result, dict) and result.get("__interrupt__"):
        value = result["__interrupt__"][0].value
        gate = value.get("gate") if isinstance(value, dict) else None
        payload = (resumes or {}).get(gate, value if isinstance(value, dict) else {})
        result = graph.invoke(Command(resume=payload), config)
    return result


def run_until_gate(job_id: str, settings, repo, target: str, resumes: dict | None = None) -> str:
    """Run until ``awaiting_config`` at ``target``, or complete."""
    uri = run_pipeline(job_id, settings)
    for _ in range(12):
        job = repo.get_job(job_id)
        if job.status == "completed":
            return uri
        if job.status == "failed":
            raise AssertionError("job failed while driving gates")
        if job.status != "awaiting_config":
            raise AssertionError(f"unexpected status {job.status}")
        report = json.loads(job.report_json or "{}")
        gate = report.get("gate")
        if gate == target:
            return uri
        payload = (resumes or {}).get(gate, {"gate": gate})
        report["pending_resume"] = payload
        repo.set_report(job_id, report)
        uri = run_pipeline(job_id, settings)
    raise AssertionError(f"never reached gate {target}")


def run_through_gates(job_id: str, settings, repo, resumes: dict | None = None) -> str:
    """Call ``run_pipeline`` until the job completes, resuming each gate."""
    uri = run_pipeline(job_id, settings)
    for _ in range(12):
        job = repo.get_job(job_id)
        if job.status == "completed":
            return uri
        if job.status == "failed":
            raise AssertionError("job failed while driving gates")
        if job.status != "awaiting_config":
            raise AssertionError(f"unexpected status {job.status}")
        report = json.loads(job.report_json or "{}")
        gate = report.get("gate")
        payload = (resumes or {}).get(gate, {"gate": gate})
        report["pending_resume"] = payload
        repo.set_report(job_id, report)
        uri = run_pipeline(job_id, settings)
    raise AssertionError("job did not complete after 12 gates")
