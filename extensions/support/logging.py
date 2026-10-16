"""Cloud logging whitelist: arbitrary messages, URL queries and tracebacks are not logs."""
import json
import logging


class SafeRuntimeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        component = next((name for name in ("coworker", "uvicorn", "psycopg", "extensions") if record.name.startswith(name + ".") or record.name == name), "runtime")
        # Do not call getMessage()/formatException(): either can contain tokens/private body.
        return json.dumps({"level": record.levelname if record.levelname in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "ERROR",
                           "component": component, "event": "runtime_log"})


def cloud_log_config() -> dict:
    return {"version": 1, "disable_existing_loggers": True,
            "formatters": {"safe": {"()": SafeRuntimeFormatter}},
            "handlers": {"safe": {"class": "logging.StreamHandler", "formatter": "safe", "stream": "ext://sys.stderr"}},
            "root": {"level": "INFO", "handlers": ["safe"]},
            "loggers": {name: {"level": "INFO", "handlers": ["safe"], "propagate": False}
                        for name in ("coworker", "extensions", "uvicorn", "uvicorn.error", "uvicorn.access", "psycopg.pool")}}
