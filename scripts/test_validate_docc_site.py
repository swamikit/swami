from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from validate_docc_site import validate


class ValidateDocCSiteTests(unittest.TestCase):
    def test_valid_site_resolves_assets_inside_hosting_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "js").mkdir()
            (site / "js/app.js").write_text("ok")
            (site / "index.html").write_text(
                '<script>var baseUrl = "/swami/pr-7"</script>'
                '<script src="/swami/pr-7/js/app.js"></script>'
            )
            self.assertEqual(validate(site, "/swami/pr-7"), [])

    def test_rejects_the_blank_page_failure_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text(
                '<script>var baseUrl = "/"</script><script src="/js/app.js"></script>'
            )
            errors = validate(site, "/swami/pr-7")
            self.assertTrue(any("baseUrl" in error for error in errors))
            self.assertTrue(any("escapes hosting base" in error for error in errors))

    def test_missing_asset_fails_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text(
                '<script>var baseUrl = "/swami/dev"</script>'
                '<script src="/swami/dev/js/missing.js"></script>'
            )
            self.assertIn(
                "referenced asset is missing: js/missing.js",
                validate(site, "/swami/dev"),
            )


if __name__ == "__main__":
    unittest.main()
