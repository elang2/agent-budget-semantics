FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY cli.py harness.py otel_comparison.py otel_span_capture.py cost_divergence.py report_generator.py ./
COPY DIMENSIONS.md ./
COPY runners/ ./runners/
COPY mock-llm/ ./mock-llm/
COPY scenarios/ ./scenarios/
COPY tests/ ./tests/

RUN pip install --no-cache-dir -e ".[dev]"

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "cli.py"]
CMD ["compare"]
