"""Step 8 acceptance (verifier half): numeric recompute, accounting identities,
infer premise-chain registration."""
from src.cedg.draft_parser import Claim
from src.cedg.graph import CEDG, ClaimNode
from src.cedg.verifiers import (
    check_identities,
    run_verification,
)


def _graph_with_claims(*specs):
    """specs: (cid, ctype, var_names)"""
    cedg = CEDG()
    for cid, ctype, var_names in specs:
        cedg.add_claim(ClaimNode(cid=cid, ctype=ctype, text=f"text {cid}",
                                 var_names=list(var_names)))
    return cedg


def test_numeric_recompute_verified():
    cedg = _graph_with_claims(("S01-C001", "num", ["rev"]))
    registry = {"rev": {"value": 100.0, "depends_on": ["E001"], "code": "100.0"}}
    results = run_verification(cedg, registry, eval_globals={})
    assert results["S01-C001"] == "verified"
    assert cedg.claims["S01-C001"].nu == "verified"


def test_numeric_recompute_mismatch_fails():
    cedg = _graph_with_claims(("S01-C001", "num", ["rev"]))
    registry = {"rev": {"value": 100.0, "depends_on": ["E001"], "code": "99.0"}}
    results = run_verification(cedg, registry, eval_globals={})
    assert results["S01-C001"] == "failed"


def test_numeric_recompute_uses_executor_globals():
    cedg = _graph_with_claims(("S01-C001", "num", ["area"]))
    registry = {"area": {"value": 50.0, "depends_on": ["E001"], "code": "length * width"}}
    results = run_verification(cedg, registry, eval_globals={"length": 10, "width": 5})
    assert results["S01-C001"] == "verified"


def test_recompute_exception_or_missing_code_is_unresolved():
    cedg = _graph_with_claims(
        ("S01-C001", "num", ["bad"]),
        ("S01-C002", "num", ["nocode"]),
    )
    registry = {
        "bad": {"value": 1.0, "depends_on": [], "code": "1/0"},
        "nocode": {"value": 2.0, "depends_on": [], "code": ""},
    }
    results = run_verification(cedg, registry, eval_globals={})
    assert results["S01-C001"] == "unresolved"
    assert results["S01-C002"] == "unresolved"


def test_tolerance_accepts_float_noise():
    cedg = _graph_with_claims(("S01-C001", "num", ["ratio"]))
    registry = {"ratio": {"value": 0.31, "depends_on": [], "code": "31 / 100"}}
    results = run_verification(cedg, registry, eval_globals={})
    assert results["S01-C001"] == "verified"


def test_identity_balance_sheet():
    ok = {"total_assets": {"value": 100.0}, "total_liabilities": {"value": 60.0},
          "total_equity": {"value": 40.0}}
    checks = check_identities(ok)
    bal = next(c for c in checks if 'assets' in c.name)
    assert bal.status == 'ok'

    bad = dict(ok, total_equity={"value": 30.0})
    checks = check_identities(bad)
    bal = next(c for c in checks if 'assets' in c.name)
    assert bal.status == 'failed'


def test_identity_skipped_when_names_missing():
    checks = check_identities({"revenue": {"value": 1.0}})
    assert all(c.status == 'skipped' for c in checks)


def test_identity_candidates_resolve_aliases():
    reg = {"assets_total": {"value": 100.0}, "total_liability": {"value": 60.0},
           "equity_total": {"value": 40.0}}
    checks = check_identities(reg)
    bal = next(c for c in checks if 'assets' in c.name)
    assert bal.status == 'ok'


def test_failed_identity_fails_participating_claims():
    cedg = _graph_with_claims(
        ("S01-C001", "num", ["total_assets"]),
        ("S01-C002", "num", ["other_var"]),
    )
    registry = {
        "total_assets": {"value": 100.0, "code": "100.0"},
        "total_liabilities": {"value": 60.0, "code": "60.0"},
        "total_equity": {"value": 30.0, "code": "30.0"},   # breaks the identity
        "other_var": {"value": 1.0, "code": "1.0"},
    }
    results = run_verification(cedg, registry, eval_globals={})
    assert results["S01-C001"] == "failed"      # participates in broken identity
    assert results["S01-C002"] == "verified"    # unrelated


def test_infer_claims_get_premise_chain():
    cedg = _graph_with_claims(
        ("S01-C001", "num", ["rev"]),
        ("S01-C002", "fact", []),
        ("S01-C003", "infer", []),
        ("S02-C001", "infer", []),
    )
    registry = {"rev": {"value": 1.0, "code": "1.0"}}
    run_verification(cedg, registry, eval_globals={})

    infer1 = cedg.claims["S01-C003"]
    assert infer1.nu == "infer"
    assert set(infer1.premises) == {"S01-C001", "S01-C002"}   # same-section evidenced claims
    # S02's lone infer claim has no premises in its own section
    assert cedg.claims["S02-C001"].premises == []
    assert cedg.claims["S02-C001"].nu == "infer"


def test_fact_claims_stay_pending():
    cedg = _graph_with_claims(("S01-C001", "fact", []))
    results = run_verification(cedg, {}, eval_globals={})
    assert results["S01-C001"] == "pending"   # NLI verification is phase-2 work
