from pathlib import Path
from confio import Group, Entry
from collisions import find_collisions, norm_value

def _g(slug, entries):
    return Group(slug, Path(slug + ".conf"), slug, "", False, entries)

def test_norm_lower_domain_and_tags():
    assert norm_value(Entry("blocked-sites", "Example.COM", "domain")) == "example.com"
    assert norm_value(Entry("blocked-sites", "geosite:YouTube", "geosite")) == "geosite:youtube"
    assert norm_value(Entry("blocked-sites", "1.2.3.4/24", "cidr")) == "1.2.3.4/24"

def test_duplicate_across_groups():
    cs = find_collisions([
        _g("a", [Entry("blocked-sites", "a.com", "domain")]),
        _g("b", [Entry("blocked-sites", "A.com", "domain")]),
    ])
    assert len(cs) == 1
    assert cs[0].value == "a.com"
    assert {h[0] for h in cs[0].hits} == {"a", "b"}

def test_both_sets_is_collision():
    cs = find_collisions([
        _g("a", [
            Entry("blocked-sites", "a.com", "domain"),
            Entry("only-ru", "a.com", "domain"),
        ]),
    ])
    assert len(cs) == 1
    assert {h[1] for h in cs[0].hits} == {"blocked-sites", "only-ru"}

def test_unique_no_collision():
    assert find_collisions([
        _g("a", [Entry("blocked-sites", "a.com", "domain")]),
        _g("b", [Entry("blocked-sites", "b.com", "domain")]),
    ]) == []
