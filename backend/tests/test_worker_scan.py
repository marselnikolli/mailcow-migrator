"""Tests for the worker's pre-migration scan executor and progress math."""

import time

from app.core.worker import MigrationWorker
from app.repositories.job_repo import JobRepository


class FakeLogger:
    def log_info(self, *a, **k):
        pass

    def log_error(self, *a, **k):
        pass


def make_worker():
    w = MigrationWorker()
    w.job_logger = FakeLogger()
    return w


def scan_payload(worker, **overrides):
    payload = {
        "id": 1,
        "tenant_id": 1,
        "source_email": "a@b.com",
        "source_password": worker.secrets.encrypt("p"),
        "source_host": "imap.example.com",
        "source_port": 993,
        "source_ssl": True,
        "folders": "INBOX",
        "maxage_days": 30,
        "since_date": None,
        "sync_calendar": True,
        "sync_contacts": True,
        "sync_tasks": False,
    }
    payload.update(overrides)
    return payload


def test_process_scan_stores_totals(monkeypatch):
    w = make_worker()

    calls = {}
    monkeypatch.setattr(
        JobRepository, "update_job",
        lambda job_id, tenant_id, **kw: calls.update(kw) or True,
    )

    class FakeEstimate:
        def __init__(self, *a, **k):
            pass

        def estimate(self, **k):
            # The scan must forward the job's date filters to the estimator.
            assert k.get("maxage_days") == 30
            assert k.get("folders") == "INBOX"
            return {"total_messages": 100, "filtered": True}

    class FakeDav:
        def __init__(self, *a, **k):
            pass

        def estimate(self, **k):
            return {"calendar": 10, "contacts": 5, "tasks": 0}

    monkeypatch.setattr("app.core.worker.MailboxEstimator", FakeEstimate)
    monkeypatch.setattr("app.core.worker.DavSyncer", FakeDav)

    w.process_scan(scan_payload(w))

    assert calls["scan_status"] == "done"
    assert calls["total_messages"] == 100
    assert calls["total_calendar"] == 10
    assert calls["total_contacts"] == 5
    assert calls["total_tasks"] == 0
    assert calls["expected_total"] == 115


def test_process_scan_failure_sets_failed(monkeypatch):
    w = make_worker()

    calls = {}
    monkeypatch.setattr(
        JobRepository, "update_job",
        lambda job_id, tenant_id, **kw: calls.update(kw) or True,
    )

    class Boom:
        def __init__(self, *a, **k):
            pass

        def estimate(self, **k):
            raise RuntimeError("auth failed")

    monkeypatch.setattr("app.core.worker.MailboxEstimator", Boom)

    w.process_scan(scan_payload(w))
    assert calls["scan_status"] == "failed"


def test_weighted_progress(monkeypatch):
    w = make_worker()

    class FakeJob:
        expected_total = 200

    monkeypatch.setattr(JobRepository, "get_job_by_id", lambda *a, **k: FakeJob())
    start = time.time() - 10  # pretend 10s have elapsed

    pct, eta = w._weighted_progress(1, 1, 50, start)
    assert pct == 25
    assert eta is not None and eta > 0

    pct2, eta2 = w._weighted_progress(1, 1, 0, start)
    assert pct2 == 0
    assert eta2 is None

    # No scan total yet -> graceful fallback to (0, None).
    class FakeJobZero:
        expected_total = 0

    monkeypatch.setattr(JobRepository, "get_job_by_id", lambda *a, **k: FakeJobZero())
    pct3, eta3 = w._weighted_progress(1, 1, 50, start)
    assert pct3 == 0
    assert eta3 is None
