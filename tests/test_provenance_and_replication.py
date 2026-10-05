"""Provenance and replication, as queries over the artefacts.

Every round of review on this project has found the same thing: the numbers
survive re-derivation and the labels do not. These tests move what a reader
takes on faith from the labels to nothing, by making provenance a field and
replication a computation.
"""
import glob
import json
import os
import pathlib
import re

import pytest

TC = pathlib.Path("results/S2-toolchoice-2026-10-04.json")
REPL = pathlib.Path("results/replication")
VOCAB = {"ledger", "harness_counter", "framework_api", "declared",
         "modelled", "hand_authored", "per_runner"}


@pytest.fixture(scope="module")
def doc():
    assert TC.exists(), "the toolchoice artefact is missing; this test has no subject"
    return json.loads(TC.read_text())


class TestProvenanceIsDeclared:
    def test_every_declared_provenance_is_in_the_vocabulary(self, doc):
        fp = doc["field_provenance"]
        for field, prov in fp["fields"].items():
            assert prov in VOCAB, f"{field} claims unknown provenance {prov!r}"
        for fw, prov in fp["framework_reported_llm_calls_by_framework"].items():
            assert prov in VOCAB, f"{fw} claims unknown provenance {prov!r}"

    def test_every_numeric_cell_field_has_a_provenance(self, doc):
        declared = set(doc["field_provenance"]["fields"])
        missing = set()
        for cell in doc["cells"].values():
            for k, v in cell.items():
                if isinstance(v, bool) or v is None:
                    continue
                if isinstance(v, (int, float)) and k not in declared:
                    missing.add(k)
        assert not missing, f"numeric fields with no declared provenance: {sorted(missing)}"

    def test_nothing_claims_framework_api_that_is_not_one(self, doc):
        """The claim this project keeps making by accident.

        `actual_tool_calls` is `tool_calls_observed`, a counter this harness
        increments inside each tool body in all eight runners. `actual_llm_calls`
        is `len(ledger)` for four runners and `budget_value` for openai-agents.
        Neither is a framework self-report, however the field is named.
        """
        fp = doc["field_provenance"]["fields"]
        assert fp["framework_reported_tool_calls"] == "harness_counter", (
            "the executed tool count is a harness counter, not a framework API read")
        assert fp["framework_reported_llm_calls"] != "framework_api"

    def test_the_llm_calls_provenance_matches_the_runner_source(self, doc):
        """Derive it independently, because a grep once got this wrong.

        `grep 'actual_llm_calls=len('` reported five runners and missed
        semantic_kernel, which assigns through an intermediate variable. This
        reads the same property a different way.
        """
        claimed = doc["field_provenance"]["framework_reported_llm_calls_by_framework"]
        for fw, prov in claimed.items():
            src = pathlib.Path(f"runners/runner_{fw}.py").read_text()
            if re.search(r"llm_calls\s*=\s*len\(", src):
                expected = "ledger"
            elif re.search(r"llm_calls\s*=\s*budget_value", src):
                expected = "declared"
            else:
                expected = "framework_api"
            assert prov == expected, (
                f"{fw}: file claims {prov!r}, runner source says {expected!r}")

    def test_the_mechanism_label_lists_its_evidence(self, doc):
        for fw, m in doc["mechanisms"].items():
            assert "classified_on" in m, f"{fw}'s label does not list its inputs"
            co = m["classified_on"]
            for key in ("withdraws_tools", "signals_tool_choice_none",
                        "tool_calls_offered", "stopped_by", "input_provenance"):
                assert key in co, f"{fw} classified_on is missing {key}"
            assert co["input_provenance"]["stopped_by"] == "framework_api"
            assert co["input_provenance"]["tool_calls_executed"] == "harness_counter"


class TestReplicationHasADenominator:
    """"Two runs, zero differences" with a number a test can compute.

    Previously this lived only in README prose, so a reader had nothing to
    check. Run A and run B are committed; the comparison is performed here.
    """

    VOLATILE_DOC = {"executed_at"}
    VOLATILE_LEDGER = {"request_id", "timestamp"}

    def test_both_runs_are_committed(self):
        for name in ("run-a.json", "run-b.json"):
            assert (REPL / name).exists(), f"results/replication/{name} is missing"
        for d in ("run-a-ledgers", "run-b-ledgers"):
            n = len(glob.glob(str(REPL / d / "*.json")))
            assert n == 8, f"{d} holds {n} ledgers, expected 8"

    def test_the_two_runs_agree_on_every_measured_field(self):
        a = json.loads((REPL / "run-a.json").read_text())
        b = json.loads((REPL / "run-b.json").read_text())
        strip = lambda d: {k: v for k, v in d.items() if k not in self.VOLATILE_DOC}
        sa, sb = strip(a), strip(b)
        diffs = [k for k in set(sa) | set(sb) if sa.get(k) != sb.get(k)]
        n_fields = sum(len(c) for c in a["cells"].values())
        assert not diffs, (
            f"{len(diffs)} differences across {len(a['cells'])} cells / "
            f"{n_fields} fields: {diffs}")
        assert n_fields >= 100, (
            f"only {n_fields} fields compared; a clean result over a tiny "
            f"denominator proves little")

    def test_the_two_runs_agree_on_every_ledger_entry(self):
        files = sorted(glob.glob(str(REPL / "run-a-ledgers" / "*.json")))
        assert files, "no ledgers to compare"
        strip = lambda L: [{k: v for k, v in e.items()
                            if k not in self.VOLATILE_LEDGER} for e in L]
        entries = 0
        bad = []
        for f in files:
            g = f.replace("run-a-ledgers", "run-b-ledgers")
            la = json.loads(pathlib.Path(f).read_text())
            lb = json.loads(pathlib.Path(g).read_text())
            entries += len(la)
            if strip(la) != strip(lb):
                bad.append(os.path.basename(f))
        assert not bad, f"ledgers differing on measured fields: {bad}"
        assert entries >= 30, f"only {entries} ledger entries compared"

    def test_the_comparison_can_detect_a_difference(self):
        """A comparison that cannot fail proves nothing — ERRATA E7."""
        a = json.loads((REPL / "run-a.json").read_text())
        b = json.loads((REPL / "run-b.json").read_text())
        b["cells"]["agno/ignore"]["ledger_tool_calls"] = 999
        strip = lambda d: {k: v for k, v in d.items() if k not in self.VOLATILE_DOC}
        sa, sb = strip(a), strip(b)
        diffs = [k for k in set(sa) | set(sb) if sa.get(k) != sb.get(k)]
        assert diffs == ["cells"], (
            "the comparison did not notice a planted difference")


class TestErrataCrossReferencesResolveToTheRightEntry:
    """A pointer that names the wrong entry sends a reader to the wrong page.

    `docs/HANDOFF-2026-10-04.md` said "E5 is the harness defect above". The
    defect it describes above — the mock never reading `tool_choice` — is
    documented in E4's BODY, under a heading about the published preprint. E5
    is a different mock defect, the null final answer, which the handoff never
    mentions. The reference was checked at heading granularity and declared
    verified; the reference was to a body.

    So this test checks each claim against the body of the entry it names.
    """

    CLAIMS = {
        # entry -> a phrase that must appear inside that entry's body
        "E4": "never read `tool_choice`",
        "E5": "null final answer",
        "E6": "did not start",
        "E7": "broke a neighbour",
    }

    def _entries(self):
        import re
        text = pathlib.Path("ERRATA.md").read_text()
        heads = [(m.start(), m.group(1)) for m in
                 re.finditer(r"^## (E\d+)", text, re.M)]
        out = {}
        for i, (pos, name) in enumerate(heads):
            end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
            out[name] = text[pos:end]
        return out

    def test_every_named_entry_exists_and_discusses_what_is_claimed(self):
        entries = self._entries()
        assert len(entries) >= 7, f"only found {sorted(entries)}"
        for name, phrase in self.CLAIMS.items():
            assert name in entries, f"{name} is referenced but does not exist"
            assert phrase in entries[name], (
                f"{name} is cited for {phrase!r} but its body does not contain it")

    def test_the_handoff_names_entries_that_match_their_bodies(self):
        doc = pathlib.Path("docs/HANDOFF-2026-10-04.md")
        if not doc.exists():
            pytest.skip("handoff not committed")
        text = doc.read_text()
        entries = self._entries()
        import re
        # Every "E<n> <description>" claim in the handoff must be satisfiable.
        for name, phrase in self.CLAIMS.items():
            if name not in text:
                continue
            assert phrase in entries[name], (
                f"the handoff cites {name}, whose body lacks {phrase!r}")
        assert "is the harness defect" not in text, (
            "the old 'E5 is the harness defect above' phrasing is back; it "
            "depends on paragraph order and named the wrong entry")

    def test_the_check_can_fail(self):
        """Control: a deliberately wrong pairing must not pass."""
        entries = self._entries()
        assert "null final answer" not in entries["E4"], (
            "E4 should not contain E5's defect; if it does, the entries have "
            "been merged and this test's premise is gone")
