FROM python:3.12-slim

WORKDIR /app

# Keep this list in step with [tool.hatch.build.targets.wheel] only-include in
# pyproject.toml. It previously omitted cost_source_divergence.py, which made
# the README's advertised `docker run ... cost-source` fail with
# ModuleNotFoundError, and omitted budget_accumulator.py, synthesis_detector.py
# and expectations/, so the accumulator and the no-synthesis enforcement that
# CI gates on could not be exercised in the container at all.
COPY pyproject.toml README.md LICENSE ./
COPY cli.py harness.py ./
COPY otel_comparison.py otel_span_capture.py ./
COPY cost_divergence.py cost_source_divergence.py ./
COPY budget_accumulator.py synthesis_detector.py report_generator.py ./
COPY DIMENSIONS.md ./
COPY runners/ ./runners/
COPY mock-llm/ ./mock-llm/
COPY scenarios/ ./scenarios/
COPY expectations/ ./expectations/
# results/ holds the executed readings. Without it the report falls back to the
# prediction model for every row and shows Agno at the modelled 3 rather than
# the observed 10, which is exactly the substitution the validity contract
# refuses. The image ran `compare` and `cost` in CI, neither of which reads it,
# so the omission stayed invisible.
COPY results/ ./results/
COPY tests/ ./tests/

# [dev] only, by decision rather than by omission. The container exists for the
# derived analyses, which need no agent framework: compare, cost, cost-source,
# spans and dimensions all read committed inputs. Installing one framework
# extra would add hundreds of megabytes and still could not produce a
# differential result, since the finding is a disagreement among eleven
# frameworks rather than the behaviour of any one; worse, a bare `pip install
# .[langchain]` resolves to whatever version is current, which would contradict
# the pinned versions in PINS.md that every recorded result depends on.
# Per-framework execution therefore belongs in the pinned environment, not here.
# README.md states this boundary where the image is advertised.
RUN pip install --no-cache-dir -e ".[dev]"

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "cli.py"]
CMD ["compare"]
