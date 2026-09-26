"""Automation services package."""

from app.services.automation.daily_close import (
    build_daily_close_summary,
    run_daily_close,
    run_daily_close_for_user,
    send_daily_close_telegram,
)
from app.services.automation.reliability import install_execution_state_reliability

# Install the reliability policy before dispatcher imports the execution-state
# retry query.  This keeps the existing dispatcher/claim/dedupe implementation
# intact while adding bounded backoff and safe same-day catch-up in production.
install_execution_state_reliability()

__all__ = [
    "build_daily_close_summary",
    "build_execution_key",
    "claim_execution",
    "execute_job",
    "execution_state_lock",
    "get_execution_state_path",
    "get_retryable_executions",
    "load_execution_state",
    "parse_execution_key",
    "prune_execution_state",
    "record_execution_failure",
    "record_execution_success",
    "resolve_due_jobs",
    "resolve_global_automation_owner",
    "run_daily_close",
    "run_daily_close_for_user",
    "run_due_automation",
    "sanitize_error_code",
    "save_execution_state",
    "send_daily_close_telegram",
]


def __getattr__(name: str):
    if name in (
        "execute_job",
        "resolve_due_jobs",
        "resolve_global_automation_owner",
        "run_due_automation",
    ):
        from app.services.automation import dispatcher
        return getattr(dispatcher, name)
    if name in (
        "build_execution_key",
        "claim_execution",
        "execution_state_lock",
        "get_execution_state_path",
        "get_retryable_executions",
        "load_execution_state",
        "parse_execution_key",
        "prune_execution_state",
        "record_execution_failure",
        "record_execution_success",
        "sanitize_error_code",
        "save_execution_state",
    ):
        from app.services.automation import execution_state
        return getattr(execution_state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
