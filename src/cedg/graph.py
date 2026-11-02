"""Claim–Evidence Dependency Graph (CEDG) data structure.

The report is compiled from this graph: claims bound to evidence addresses at
drafting time, verified on the graph (step 8), rendered last (step 9). The
graph itself is the auditable provenance trace.
"""
import json
from dataclasses import dataclass, field, asdict


@dataclass
class EvidenceNode:
    eid: str
    kind: str          # tool_result / analysis / web
    ref_repr: str      # brief_str() summary


@dataclass
class ClaimNode:
    cid: str
    ctype: str         # num / fact / infer
    text: str
    var_names: list = field(default_factory=list)
    kappa: float = 1.0
    nu: str = "pending"   # pending / verified / failed / infer / unresolved


@dataclass
class CEDG:
    evidence: dict = field(default_factory=dict)   # eid -> EvidenceNode
    claims: dict = field(default_factory=dict)     # cid -> ClaimNode
    edges: list = field(default_factory=list)      # [(src, dst, "sup"|"derive"|"conflict")]

    def add_evidence(self, eid: str, kind: str, ref_repr: str) -> EvidenceNode:
        if eid not in self.evidence:
            self.evidence[eid] = EvidenceNode(eid=eid, kind=kind, ref_repr=ref_repr)
        return self.evidence[eid]

    def add_claim(self, claim: ClaimNode) -> ClaimNode:
        self.claims[claim.cid] = claim
        return claim

    def add_edge(self, src: str, dst: str, relation: str):
        edge = (src, dst, relation)
        if edge not in self.edges:
            self.edges.append(edge)

    def to_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "evidence": {k: asdict(v) for k, v in self.evidence.items()},
                "claims": {k: asdict(v) for k, v in self.claims.items()},
                "edges": [list(e) for e in self.edges],
            }, f, ensure_ascii=False, indent=2)
