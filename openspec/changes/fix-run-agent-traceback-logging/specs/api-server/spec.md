## ADDED Requirements

### Requirement: _run_agent logs full traceback on internal error
When the outer `except Exception` block in `_run_agent` is triggered (i.e., any exception escapes from `LLMClient`, `Browser`, or `loop()`), the system SHALL emit an `ERROR`-level log record via `logging.getLogger(__name__)` that includes the full exception traceback and the `run_id` as a structured extra field, before attempting to write the `final.failure.reason="internal error"` row. The inner `except Exception: pass` block SHALL remain and SHALL continue to suppress any exception raised by `writer.close_run` during the error-path close attempt. The `final.failure.reason="internal error"` row SHALL still be written to SQLite when `writer.close_run` succeeds.

#### Scenario: Exception in loop() produces ERROR log with traceback
- **WHEN** `_run_agent` is called and `loop()` raises `RuntimeError("boom")`
- **THEN** an `ERROR`-level log record is emitted on the `api.server` logger whose `exc_text` contains `RuntimeError: boom` and includes the file name and line number of the raise site

#### Scenario: Exception in loop() still writes internal-error DB row
- **WHEN** `_run_agent` is called and `loop()` raises any exception
- **THEN** the `traces_runs` row for `run_id` is updated with `status="failed"` and `final.failure.reason="internal error"`

#### Scenario: writer.close_run failure in error path is silently swallowed
- **WHEN** `_run_agent` catches an outer exception and `writer.close_run` itself raises during the error-path attempt
- **THEN** no exception propagates out of `_run_agent` and no additional log record is emitted for the close failure

#### Scenario: Successful run emits no ERROR log
- **WHEN** `_run_agent` completes without exception
- **THEN** no `ERROR`-level log record is emitted on the `api.server` logger
