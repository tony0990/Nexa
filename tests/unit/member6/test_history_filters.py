from nexa.services.fakes import FakeAuditService, FakeEmailService
from nexa.ui.history.filters import filter_audit, filter_deliveries


def test_audit_entity_history_by_type_and_id():
    events = FakeAuditService().history("all")
    assert {e.entity_type for e in filter_audit(events, entity_type="action")} == {"action"}
    only_17 = filter_audit(events, "action:17")
    assert len(only_17) == 1 and only_17[0].entity_id == "17"


def test_audit_text_filter_matches_detail_and_actor():
    events = FakeAuditService().history("all")
    assert filter_audit(events, "ahmed hassan")
    assert filter_audit(events, "no-such-text") == []


def test_delivery_filters_combine():
    rows = FakeEmailService().deliveries
    failed = filter_deliveries(rows, status="FAILED")
    assert [r["status"] for r in failed] == ["FAILED"]
    assert filter_deliveries(rows, kind="REPORT", status="FAILED") == []
    assert filter_deliveries(rows, text="ahmed@nexa.local")
