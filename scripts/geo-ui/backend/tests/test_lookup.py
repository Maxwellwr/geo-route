from lookup import iter_lookup, parse_a_records


def test_parse_a_records_ipv4_only():
    text = "1.2.3.4\n2a00:1450::1\n;; flags\n8.8.8.8\n"
    assert parse_a_records(text) == ["1.2.3.4", "8.8.8.8"]


def test_parse_nslookup_address_lines():
    text = (
        "Server:  127.0.0.1\n"
        "Address:  127.0.0.1:53\n\n"
        "Name:    example.com\n"
        "Address: 93.184.216.34\n"
    )
    assert parse_a_records(text) == ["93.184.216.34"]


def test_iter_lookup_logs_ips(monkeypatch):
    monkeypatch.setattr("lookup.run_query", lambda d: "9.9.9.9\n")
    lines = list(iter_lookup(["example.com"]))
    assert lines == ["lookup example.com → 9.9.9.9"]


def test_iter_lookup_empty_or_no_a(monkeypatch):
    assert list(iter_lookup([])) == []
    monkeypatch.setattr("lookup.run_query", lambda d: "")
    assert list(iter_lookup(["none.example"])) == ["lookup none.example → (нет A)"]
