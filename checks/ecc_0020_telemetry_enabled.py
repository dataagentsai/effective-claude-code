"""ECC-0020 -- Telemetry export is enabled once more than one developer is using Claude Code."""

import os

from _framework import failed, passed


def run(ctx):
    env = {}
    for _, settings in ctx.all_settings:
        env.update(settings.get("env") or {})

    telemetry_on = str(env.get("CLAUDE_CODE_ENABLE_TELEMETRY", os.environ.get("CLAUDE_CODE_ENABLE_TELEMETRY", ""))) == "1"
    metrics_exporter = env.get("OTEL_METRICS_EXPORTER") or os.environ.get("OTEL_METRICS_EXPORTER")
    logs_exporter = env.get("OTEL_LOGS_EXPORTER") or os.environ.get("OTEL_LOGS_EXPORTER")

    evidence = [
        f"CLAUDE_CODE_ENABLE_TELEMETRY: {env.get('CLAUDE_CODE_ENABLE_TELEMETRY', os.environ.get('CLAUDE_CODE_ENABLE_TELEMETRY', '<unset>'))}",
        f"OTEL_METRICS_EXPORTER: {metrics_exporter or '<unset>'}",
        f"OTEL_LOGS_EXPORTER: {logs_exporter or '<unset>'}",
    ]

    if not telemetry_on:
        return failed(
            "CLAUDE_CODE_ENABLE_TELEMETRY is not set to 1. Usage data exists only as each "
            "developer's own local transcripts, which nobody aggregates and which expire.",
            evidence,
        )

    exporter_set = bool(metrics_exporter and metrics_exporter != "none") or bool(logs_exporter and logs_exporter != "none")
    if not exporter_set:
        return failed(
            "Telemetry is enabled but no OTEL_METRICS_EXPORTER or OTEL_LOGS_EXPORTER points "
            "anywhere -- events are generated and dropped.",
            evidence,
        )

    return passed("Telemetry is enabled with an exporter configured.", evidence)
