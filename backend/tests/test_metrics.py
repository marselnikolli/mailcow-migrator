"""Tests for the lightweight Prometheus metrics module."""

from app.core.metrics import Counter, Gauge, Histogram, render_metrics


def test_counter_render():
    c = Counter("test_total", "help", labelnames=["outcome"])
    c.inc(labels={"outcome": "ok"})
    c.inc(labels={"outcome": "ok"})
    c.inc(labels={"outcome": "failed"})
    out = c.render()
    assert "# TYPE test_total counter" in out
    assert 'test_total{outcome="ok"} 2.0' in out
    assert 'test_total{outcome="failed"} 1.0' in out


def test_gauge_render():
    g = Gauge("test_gauge", "help")
    g.set(42)
    out = g.render()
    assert "# TYPE test_gauge gauge" in out
    assert "test_gauge 42.0" in out


def test_histogram_render():
    h = Histogram("test_hist", "help")
    h.observe(0.2)
    h.observe(1.5)
    out = h.render()
    assert 'test_hist_bucket{le="0.1"} 0' in out
    assert 'test_hist_bucket{le="0.5"} 1' in out
    assert 'test_hist_bucket{le="5"} 2' in out
    assert 'test_hist_bucket{le="+Inf"} 2' in out
    assert "test_hist_sum 1.7" in out
    assert "test_hist_count 2" in out


def test_render_metrics_registry():
    out = render_metrics()
    assert "migrator_jobs_total" in out
    assert "migrator_queue_depth" in out
