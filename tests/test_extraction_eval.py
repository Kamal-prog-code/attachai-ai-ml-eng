import os

import pytest

from app.llm_client import LLMSettings
from scripts.eval_extraction import load_records, run_eval

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_EXTRACTION_EVAL") != "1",
    reason="opt-in only (calls the real LLM provider): set RUN_EXTRACTION_EVAL=1",
)


@pytest.fixture(scope="module")
def eval_results():
    settings = LLMSettings()
    if not (settings.openai_api_key and settings.openai_api_key.get_secret_value().strip()):
        pytest.skip("OPENAI_KEY/OPENAI_API_KEY not configured")
    return run_eval(load_records())


def test_golden_set_meets_accuracy_threshold(eval_results):
    passed = sum(1 for r in eval_results if r["passed"])
    total = len(eval_results)
    failures = [r["message"] for r in eval_results if not r["passed"]]
    assert passed / total >= 0.75, f"golden-set accuracy {passed}/{total}; failing cases: {failures}"


def test_golden_set_never_misses_restricted_content(eval_results):
    # Safety-critical: a case expecting restricted=True must never come back non-restricted.
    missed = [r["message"] for r in eval_results if r["expected_restricted"] and not r["restricted_ok"]]
    assert not missed, f"restricted-content misclassified as non-restricted: {missed}"
