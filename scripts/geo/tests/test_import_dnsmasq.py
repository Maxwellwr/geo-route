import importlib.util
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "import_dnsmasq.py"
spec = importlib.util.spec_from_file_location("import_dnsmasq", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class ParseDirectiveTests(unittest.TestCase):
    def test_parses_multiple_domains_and_sets(self):
        d = mod.parse_ipset_line("ipset=/youtube.com/googlevideo.com/blocked-sites,other-set\n")
        self.assertIsNotNone(d)
        self.assertEqual(d.domains, ["youtube.com", "googlevideo.com"])
        self.assertEqual(d.sets, ["blocked-sites", "other-set"])

    def test_rejects_special_dnsmasq_domain_expression(self):
        d = mod.parse_ipset_line("ipset=/#/blocked-sites\n")
        self.assertIsNotNone(d)
        self.assertFalse(d.supported)
        self.assertEqual(d.unsupported_domains, ["#"])

    def test_rewrite_removes_only_selected_set(self):
        d = mod.parse_ipset_line("  ipset=/a.com/b.com/blocked-sites,other-set # keep\n")
        self.assertEqual(
            mod.rewrite_directive(d, {"blocked-sites": None}),
            "  ipset=/a.com/b.com/other-set # keep\n",
        )

    def test_rewrite_can_redirect_reserved_set_to_site_set(self):
        d = mod.parse_ipset_line("ipset=/a.com/blocked-sites,other-set\n")
        self.assertEqual(
            mod.rewrite_directive(d, {"blocked-sites": "blocked-sites-site"}),
            "ipset=/a.com/blocked-sites-site,other-set\n",
        )


class ImportConfigTests(unittest.TestCase):
    def test_merge_import_config_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "imported-dnsmasq.conf"
            mod.merge_import_config(
                path,
                {
                    "blocked-sites": {"b.com", "a.com"},
                    "only-ru": {"ya.ru"},
                },
            )
            first = path.read_text()
            mod.merge_import_config(
                path,
                {
                    "blocked-sites": {"a.com"},
                    "only-ru": {"ya.ru"},
                },
            )
            self.assertEqual(path.read_text(), first)
            self.assertIn("[blocked-sites]\na.com\nb.com", first)
            self.assertIn("[only-ru]\nya.ru", first)


class ScanTests(unittest.TestCase):
    def test_scan_skips_generated_and_backup_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "a.conf").write_text("ipset=/a.com/blocked-sites\n")
            (root / "geo-generated.conf").write_text("ipset=/self.com/blocked-sites-site\n")
            (root / "old.conf.geo-route.bak").write_text("ipset=/old.com/blocked-sites\n")
            found = mod.scan_dnsmasq_dir(root)
            self.assertEqual([x.path.name for x in found], ["a.conf"])


class IpsetParsingTests(unittest.TestCase):
    def test_parse_ipset_list_hash_ip(self):
        text = """Name: blocked-sites
Type: hash:ip
Revision: 5
Header: family inet hashsize 1024 maxelem 65536
Size in memory: 200
References: 0
Number of entries: 2
Members:
1.2.3.4
5.6.7.8
"""
        state = mod.parse_ipset_list(text)
        self.assertEqual(state.set_type, "hash:ip")
        self.assertEqual(state.references, 0)
        self.assertEqual(state.members, ["1.2.3.4", "5.6.7.8"])


if __name__ == "__main__":
    unittest.main()
