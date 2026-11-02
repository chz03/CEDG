"""Step 1 acceptance: explicit evidence addressing (E-IDs) in Memory."""
from src.memory.variable_memory import Memory

from tests.conftest import make_tool_result


def test_add_data_assigns_monotonic_eids(memory):
    items = [make_tool_result(f"d{i}") for i in range(3)]
    for item in items:
        memory.add_data(item)

    assert len(memory.data2eid) == 3
    assert list(memory.data2eid.values()) == ["E001", "E002", "E003"]
    assert memory.get_eid(items[0]) == "E001"
    assert memory.get_eid(items[2]) == "E003"


def test_get_eid_unknown_item_returns_empty(memory):
    stranger = make_tool_result("stranger")
    assert memory.get_eid(stranger) == ""


def test_get_evidence_by_eid(memory):
    a, b = make_tool_result("a"), make_tool_result("b")
    memory.add_data(a)
    memory.add_data(b)

    assert memory.get_evidence_by_eid("E002") is b
    assert memory.get_evidence_by_eid("E001") is a
    assert memory.get_evidence_by_eid("E999") is None


def test_save_load_preserves_eids_and_counter(memory):
    for name in ("x", "y", "z"):
        memory.add_data(make_tool_result(name))
    memory.save()

    # Fresh instance over the same save_dir simulates a restart.
    memory2 = Memory(memory.config)
    assert memory2.load() is True

    # id()-keyed dict must have been rebuilt for the deserialized objects.
    assert memory2.get_eid(memory2.data[0]) == "E001"
    assert memory2.get_eid(memory2.data[2]) == "E003"
    assert memory2.get_evidence_by_eid("E002") is memory2.data[1]

    # Counter continues monotonically after resume.
    w = make_tool_result("w")
    memory2.add_data(w)
    assert memory2.get_eid(w) == "E004"
