"""Typed verification operators over the CEDG (step 8).

num claims   → programmatic recompute of the registered expression (zero model
               cost) + accounting-identity checks; mismatch marks nu="failed".
fact claims  → untouched here (NLI entailment is phase-2 machinery).
infer claims → premise chain registered, nu="infer"; inferences stay traceable
               and are never promoted to facts.
"""
from dataclasses import dataclass, field

# Absolute+relative tolerance for value comparisons.
ABS_TOL = 1e-6
REL_TOL = 1e-6

# Accounting identities: each slot lists candidate variable names (the writing
# model chooses names freely; first registered candidate wins). A rule only
# fires when every slot resolves — no partial checks.
ACCOUNTING_IDENTITIES = [
    {
        'name': 'assets = liabilities + equity',
        'lhs': ['total_assets', 'assets_total', 'total_asset'],
        'rhs': [
            ['total_liabilities', 'liabilities_total', 'total_liability'],
            ['total_equity', 'equity_total', 'total_shareholders_equity'],
        ],
        'op': 'add',
    },
    {
        'name': 'net profit = total profit - income tax',
        'lhs': ['net_profit', 'net_income', 'profit_attributable'],
        'rhs': [
            ['total_profit', 'profit_total', 'profit_before_tax'],
            ['income_tax', 'income_tax_expense', 'tax_expense'],
        ],
        'op': 'sub',
    },
    {
        'name': 'net cash increase = operating + investing + financing CF',
        'lhs': ['net_cash_increase', 'net_increase_in_cash', 'cash_net_increase'],
        'rhs': [
            ['operating_cash_flow', 'cfo', 'operating_cf'],
            ['investing_cash_flow', 'cfi', 'investing_cf'],
            ['financing_cash_flow', 'cff', 'financing_cf'],
        ],
        'op': 'add',
    },
    {
        'name': 'total profit = operating profit + non-operating net',
        'lhs': ['total_profit', 'profit_total', 'profit_before_tax'],
        'rhs': [
            ['operating_profit', 'operating_income'],
            ['non_operating_net', 'non_operating_income_net'],
        ],
        'op': 'add',
    },
]


@dataclass
class IdentityCheck:
    name: str
    status: str                 # ok / failed / skipped
    lhs: float = None
    rhs: float = None
    failed_vars: list = field(default_factory=list)


def _resolve(registry: dict, candidates: list):
    for name in candidates:
        if name in registry:
            return name
    return None


def _value(registry: dict, name: str) -> float:
    value = registry[name]['value']
    return float(value)


def _combine(op: str, registry: dict, names: list) -> float:
    values = [_value(registry, n) for n in names]
    if op == 'sub':
        result = values[0]
        for v in values[1:]:
            result -= v
        return result
    return sum(values)


def check_identities(registry: dict):
    """Evaluate every accounting identity whose slots all resolve."""
    checks = []
    for rule in ACCOUNTING_IDENTITIES:
        lhs_var = _resolve(registry, rule['lhs'])
        rhs_vars = [_resolve(registry, c) for c in rule['rhs']]
        if lhs_var is None or any(v is None for v in rhs_vars):
            checks.append(IdentityCheck(name=rule['name'], status='skipped'))
            continue
        lhs = _value(registry, lhs_var)
        rhs = _combine(rule['op'], registry, rhs_vars)
        tol = max(ABS_TOL, REL_TOL * max(abs(lhs), abs(rhs)))
        ok = abs(lhs - rhs) <= tol
        checks.append(IdentityCheck(
            name=rule['name'],
            status='ok' if ok else 'failed',
            lhs=lhs,
            rhs=rhs,
            failed_vars=[] if ok else [lhs_var] + [v for v in rhs_vars],
        ))
    return checks


def _recompute(code: str, eval_globals: dict):
    """Re-run a registered expression; returns (ok, value_or_error)."""
    if not code or not code.strip():
        return False, 'no code registered'
    try:
        return True, eval(code, dict(eval_globals))
    except Exception as e:  # noqa: BLE001 — any failure means unverifiable
        return False, f'{type(e).__name__}: {e}'


def _close(a, b) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
    return abs(a - b) <= max(ABS_TOL, REL_TOL * max(abs(a), abs(b)))


def run_verification(cedg, var_registry: dict, eval_globals: dict = None):
    """Verify all claims on the graph; mutates ClaimNode.nu/kappa/premises.

    Returns {cid: outcome}.
    """
    if eval_globals is None:
        eval_globals = {}
    results = {}

    identity_checks = check_identities(var_registry)
    failed_vars = set()
    for check in identity_checks:
        if check.status == 'failed':
            failed_vars.update(check.failed_vars)

    # same-section evidenced claims, for premise chains
    section_evidenced = {}
    for cid, claim in cedg.claims.items():
        section = cid.split('-')[0]
        if claim.ctype != 'infer':
            section_evidenced.setdefault(section, []).append(cid)

    for cid, claim in cedg.claims.items():
        if claim.nu == 'unresolved':
            # force-accepted drafts stay flagged; nothing to verify
            results[cid] = 'unresolved'
            continue

        if claim.ctype == 'infer':
            section = cid.split('-')[0]
            claim.premises = sorted(section_evidenced.get(section, []))
            claim.nu = 'infer'
            results[cid] = 'infer'
            continue

        if claim.ctype == 'num':
            outcome = 'verified'
            for var in claim.var_names:
                if var in failed_vars:
                    outcome = 'failed'
                    break
                entry = var_registry.get(var)
                if entry is None:
                    outcome = 'unresolved'
                    break
                ok, recomputed = _recompute(entry.get('code', ''), eval_globals)
                if not ok:
                    outcome = 'unresolved'
                    break
                if not _close(recomputed, entry.get('value')):
                    outcome = 'failed'
                    break
            claim.nu = outcome
            results[cid] = outcome
            continue

        # fact claims: NLI verification arrives with phase-2 machinery
        results[cid] = claim.nu  # stays 'pending'

    return results
