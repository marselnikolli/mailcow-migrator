"""Tests for the migration report generator."""

from app.core.report import build_report, report_to_csv

SAMPLE_LOG = """Transfer started at Wednesday 26 August 2026-08-26 13:29:30 +0000 UTC PID 200
Host1: folder [INBOX] selected 10 messages, duplicates 0
msg INBOX/1 {100} copied to INBOX/1 2.02 msgs/s 1.6 MiB/s 100 MiB copied ETA: x 330 s 9/10 msgs left
msg INBOX/2 {100} already transferred to INBOX/2
Host1: folder [Sent] selected 5 messages, duplicates 0
msg Sent/1 {100} copied to Sent/1 1.0 msgs/s
Uploaded 3 calendar items to https://...
Uploaded 0 contacts
Exiting with return value 0
"""


def test_build_report_counts():
    report = build_report(7, SAMPLE_LOG)
    assert report["summary"]["copied_messages"] == 2
    assert report["summary"]["skipped_messages"] == 1
    assert report["summary"]["calendar_items"] == 3
    assert report["summary"]["contacts"] == 0
    assert report["summary"]["exit_code"] == 0
    assert report["summary"]["success"] is True


def test_build_report_folders():
    report = build_report(7, SAMPLE_LOG)
    assert report["folders"]["INBOX"]["selected"] == 10
    assert report["folders"]["INBOX"]["copied"] == 1
    assert report["folders"]["Sent"]["selected"] == 5
    assert report["folders"]["Sent"]["copied"] == 1


def test_build_report_job_meta():
    report = build_report(7, SAMPLE_LOG, job_meta={"source_email": "a@b.com"})
    assert report["job"]["source_email"] == "a@b.com"


def test_report_to_csv():
    report = build_report(7, SAMPLE_LOG, job_meta={"source_email": "src@x.com", "target_email": "dst@x.com"})
    csv = report_to_csv(report)
    lines = csv.strip().splitlines()
    assert lines[0] == "source_email,target_email,folder,selected,copied,skipped"
    assert "src@x.com" in csv
    assert "__TOTAL__" in csv
