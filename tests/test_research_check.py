"""research_check: the model is started only when something is new, and a failed read is never 'no changes'."""
import datetime as dt
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("research_check", ROOT / "scripts" / "research_check.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

TODAY = dt.date(2026, 10, 21)

BACKLOG = """## 6. Daily site-refresh queue

| # | Status | Site id | Name | St | Why queued | Last researched | Next due |
|---|---|---|---|---|---|---|---|
| 1 | queued | NEW000000001 | Fresh Site | TX | shipped 5 acres to check | — | — |
| 2 | done 2026-07-01 | OLD000000001 | Old Depot | OH | x | 2026-07-01 | 2026-09-30 |

### Run log

## 7. Later
"""


def fr_body(*items):
    return json.dumps({"results": [{"html_url": u, "title": t, "publication_date": d} for u, t, d in items]})


def bing_body(*items):
    xml = "".join(
        f"<item><title>{t}</title><description>{t} story</description>"
        f"<link>https://www.bing.com/news/apiclick.aspx?ref=x&amp;url={u}</link>"
        f"<pubDate>{d}</pubDate></item>" for u, t, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{xml}</channel></rss>'


def make_root(tmp_path, dossier_next="2026-09-30", researched="2026-07-01"):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "research_queue.py").write_text((ROOT / "scripts" / "research_queue.py").read_text())
    data = tmp_path / "docs" / "data"
    data.mkdir(parents=True)
    sites = [{"id": "NEW000000001", "name": "FRESH SITE", "state": "TX"},
             {"id": "OLD000000001", "name": "OLD DEPOT (USARMY)", "state": "OH"}]
    for f in ("superfund-npl.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json"):
        (data / f).write_text(json.dumps({"sites": sites if f == "superfund-npl.json" else []}))
    (data / "site-research.json").write_text(json.dumps({"sites": [
        {"id": "OLD000000001", "researched_at": researched, "next_review": dossier_next}]}))
    (tmp_path / "backlog.md").write_text(BACKLOG)
    return tmp_path


def fetcher(fr=None, bing=None, fail=()):
    calls = []

    def fetch(url):
        calls.append(url)
        kind = "federalregister" if "federalregister" in url else "bing-news"
        if kind in fail:
            raise OSError("boom")
        return (fr if kind == "federalregister" else bing) or (fr_body() if kind == "federalregister" else bing_body())
    fetch.calls = calls
    return fetch


def go(root, fetch, state=None, comments=([], ""), **kw):
    state = state if state is not None else {"sites": {}}
    return rc.run(root, fetch, state, TODAY, comments=comments, **kw), state


def test_search_name_drops_agency_codes_and_titlecases():
    assert rc.search_name("CAMP LEJEUNE MILITARY RES. (USNAVY)") == "Camp Lejeune Military Reservation"
    assert rc.search_name("Sangamo Electric Dump/Crab Orchard NWR (USDOI)") == "Sangamo Electric Dump"


def test_bing_link_is_decoded_and_noise_dropped():
    body = bing_body(("https://news.example/a", "Old Depot cleanup plan", "Mon, 05 Oct 2026 10:00:00 GMT"),
                     ("https://news.example/b", "Unrelated celebrity story", "Mon, 05 Oct 2026 10:00:00 GMT"))
    leads = rc.parse_bing_rss(body, "Old Depot")
    assert [l["url"] for l in leads] == ["https://news.example/a"] and leads[0]["date"] == "2026-10-05"


def test_nothing_new_and_all_read_is_no_changes(tmp_path):
    root = make_root(tmp_path, dossier_next="2026-12-01")   # nothing overdue, no baseline rows left
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    res, _ = go(root, fetcher())
    assert res["status"] == rc.STATUS_NO_CHANGES and res["sites_checked"] == 0
    assert res["sources_planned"] == res["sources_read"] == 1   # only the PR-comment read
    assert res["unread"] == [] and "no changes" in rc.render(res)


def test_overdue_dossier_with_no_leads_is_quiet_not_work(tmp_path):
    root = make_root(tmp_path)   # overdue 21 days: below the escalation threshold
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    res, _ = go(root, fetcher())
    assert res["status"] == rc.STATUS_NO_CHANGES and res["work"] == [] and len(res["quiet"]) == 1
    assert res["sources_read"] == res["sources_planned"] == 3   # 2 sources for OLD + the PR read


def test_bing_first_look_on_a_dossier_site_is_baseline_only(tmp_path):
    root = make_root(tmp_path)
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    bing = bing_body(("https://news.example/a", "Old Depot reposted", "Mon, 19 Oct 2026 10:00:00 GMT"))
    res, state = go(root, fetcher(bing=bing))
    assert res["status"] == rc.STATUS_NO_CHANGES                      # looked, but only a baseline
    arrival = bing_body(("https://news.example/a", "Old Depot reposted", "Mon, 19 Oct 2026 10:00:00 GMT"),
                        ("https://news.example/c", "Old Depot land sold", "Tue, 20 Oct 2026 10:00:00 GMT"))
    res2, _ = go(root, fetcher(bing=arrival), state=state)
    assert res2["status"] == rc.STATUS_CHANGES
    assert [l["url"] for l in res2["work"][0]["new"]] == ["https://news.example/c"]


def test_new_lead_on_overdue_dossier_is_reported_then_stays_pending_until_ack(tmp_path):
    root = make_root(tmp_path)
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    f = fetcher(fr=fr_body(("https://www.federalregister.gov/d/1", "Old Depot notice", "2026-10-02"),
                           ("https://www.federalregister.gov/d/0", "Older, before last research", "2026-05-01")))
    res, state = go(root, f)
    assert res["status"] == rc.STATUS_CHANGES
    assert [l["url"] for l in res["work"][0]["new"]] == ["https://www.federalregister.gov/d/1"]
    res2, _ = go(root, f, state=state)                       # not acked: still reported
    assert res2["status"] == rc.STATUS_CHANGES
    rc.ack(state, ["OLD000000001"])
    res3, _ = go(root, f, state=state)                       # acked: quiet
    assert res3["status"] == rc.STATUS_NO_CHANGES


def test_failed_fetch_is_unread_never_no_changes_and_not_marked_seen(tmp_path):
    root = make_root(tmp_path)
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    fail = fetcher(fail=("bing-news",), fr=fr_body(("https://www.federalregister.gov/d/9", "Old Depot notice", "2026-10-02")))
    res, state = go(root, fail)
    assert res["status"] == rc.STATUS_CHANGES        # the FR lead is real even though bing failed
    assert any("bing-news" in u for u in res["unread"]) and res["sources_read"] == 2 and res["sources_planned"] == 3
    # Only the failure: unread, exit 2, nothing seen.
    res, state = go(root, fetcher(fail=("federalregister", "bing-news")))
    assert res["status"] == rc.STATUS_UNREAD and "no changes" not in rc.render(res)
    assert state["sites"]["OLD000000001"]["seen"] == {} and state["sites"]["OLD000000001"]["unread_streak"] == 1


def test_pr_comment_read_failure_is_unread(tmp_path):
    root = make_root(tmp_path)
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    res, _ = go(root, fetcher(), comments=(None, "gh: not logged in"))
    assert res["status"] == rc.STATUS_UNREAD and any("PR comments" in u for u in res["unread"])


def test_unanswered_pr_comment_is_work(tmp_path):
    root = make_root(tmp_path)
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    res, _ = go(root, fetcher(), comments=([{"id": 1, "path": "x", "line": 1, "body": "b"}], ""))
    assert res["status"] == rc.STATUS_CHANGES and "unanswered review comment" in rc.render(res)


def test_baseline_row_is_work_and_site_cap_defers_extras(tmp_path):
    root = make_root(tmp_path)
    f = fetcher(fr=fr_body(("https://www.federalregister.gov/d/1", "Old Depot notice", "2026-10-02")))
    res, _ = go(root, f, max_sites=1)
    assert res["status"] == rc.STATUS_CHANGES
    assert res["work"][0]["id"] == "OLD000000001"                    # dossier with leads outranks baseline
    assert [w["id"] for w in res["deferred"]] == ["NEW000000001"]


def test_very_overdue_dossier_escalates_even_without_leads(tmp_path):
    root = make_root(tmp_path, dossier_next="2026-08-01")            # 81 days overdue
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    res, _ = go(root, fetcher())
    assert res["status"] == rc.STATUS_CHANGES and "full review" in res["work"][0]["why"]


def test_state_roundtrip_and_exit_codes(tmp_path):
    p = tmp_path / "s" / "state.json"
    rc.save_state({"sites": {"A": {"seen": {"u": None}}}}, p)
    assert rc.load_state(p)["sites"]["A"]["seen"] == {"u": None}
    assert rc.EXIT == {"no-changes": 0, "changes": 10, "unread": 2}


def test_federal_register_zero_matches_is_empty_not_unread():
    # Real response shape for a query with no hits: no `results` key at all.
    assert rc.parse_federal_register('{"description":"Documents matching x","count":0}') == []
    import pytest
    with pytest.raises(ValueError):
        rc.parse_federal_register('{"error":"rate limited"}')


def test_a_failed_first_look_still_records_the_bing_baseline(tmp_path):
    root = make_root(tmp_path)
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    bing = bing_body(("https://news.example/a", "Old Depot reposted", "Mon, 19 Oct 2026 10:00:00 GMT"))
    res, state = go(root, fetcher(bing=bing, fail=("federalregister",)))
    assert res["status"] == rc.STATUS_UNREAD                       # FR failed, Bing was only a baseline
    res2, _ = go(root, fetcher(bing=bing), state=state)
    assert res2["status"] == rc.STATUS_NO_CHANGES                  # the baseline repost is not a new lead


def test_a_site_left_unread_is_retried_after_its_review_date_moves_out(tmp_path):
    root = make_root(tmp_path, dossier_next="2026-12-31")              # researched since; not due
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    state = {"sites": {"OLD000000001": {"seen": {}, "pending": {}, "unread_streak": 1}}}
    res, _ = go(root, fetcher(), state=state)
    assert res["sites_checked"] >= 1 and "OLD000000001" in [r for r in state["sites"]]
    assert state["sites"]["OLD000000001"]["unread_streak"] == 0      # retried and read this time


def test_a_pending_lead_stays_reported_after_it_leaves_the_feed(tmp_path):
    root = make_root(tmp_path)
    (root / "backlog.md").write_text(BACKLOG.replace("queued | NEW000000001", "done 2026-10-20 | NEW000000001"))
    f = fetcher(fr=fr_body(("https://www.federalregister.gov/d/5", "Old Depot notice", "2026-10-02")))
    res, state = go(root, f)
    assert res["status"] == rc.STATUS_CHANGES
    res2, _ = go(root, fetcher(), state=state)                        # gone from the source
    assert res2["status"] == rc.STATUS_CHANGES
    assert [l["url"] for l in res2["work"][0]["new"]] == ["https://www.federalregister.gov/d/5"]
    rc.ack(state, ["OLD000000001"])
    res3, _ = go(root, fetcher(), state=state)
    assert res3["status"] == rc.STATUS_NO_CHANGES


def test_a_development_on_the_window_start_date_counts():
    site = {"id": "OLD000000001", "name": "OLD DEPOT"}
    state = {"sites": {"OLD000000001": {"seen": {}, "pending": {}, "unread_streak": 0}}}
    f = fetcher(fr=fr_body(("https://www.federalregister.gov/d/7", "Old Depot notice", "2026-07-01")))
    r = rc.check_site(site, {"researched_at": "2026-07-01"}, state, f, TODAY)
    assert [l["url"] for l in r["new"]] == ["https://www.federalregister.gov/d/7"]


def test_throttled_fetch_backs_off_then_succeeds(monkeypatch):
    import io
    import urllib.error
    calls, waits = [], []

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "7"} if len(calls) == 1 else {}, None)
        return Resp(b"ok")

    monkeypatch.setattr(rc.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(rc, "SLEEP", waits.append)
    monkeypatch.setattr(rc.time, "sleep", lambda s: None)
    assert rc.http_fetch("https://example.test/x") == "ok"
    assert waits == [7.0, 20] and len(calls) == 3                     # Retry-After first, then the schedule


def test_a_hard_error_is_not_retried(monkeypatch):
    import urllib.error
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(rc.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(rc, "SLEEP", lambda s: (_ for _ in ()).throw(AssertionError("slept")))
    monkeypatch.setattr(rc.time, "sleep", lambda s: None)
    try:
        rc.http_fetch("https://example.test/y")
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError:
        pass
    assert len(calls) == 1
