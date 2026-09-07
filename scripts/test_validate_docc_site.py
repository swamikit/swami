from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prepare_docc_site import prepare
from validate_docc_site import validate


class ValidateDocCSiteTests(unittest.TestCase):
    def test_valid_site_resolves_assets_inside_hosting_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "js").mkdir()
            (site / "js/app.js").write_text("ok")
            (site / "documentation/swami").mkdir(parents=True)
            (site / "documentation/swami/index.html").write_text(
                '<script>var baseUrl = "/swami/pr-7"</script>'
                '<script src="/swami/pr-7/js/app.js"></script>'
            )
            prepare(site, "/swami/pr-7", "documentation/swami")
            self.assertEqual(validate(site, "/swami/pr-7"), [])

    def test_rejects_the_blank_page_failure_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "documentation/swami").mkdir(parents=True)
            (site / "documentation/swami/index.html").write_text(
                '<script>var baseUrl = "/"</script><script src="/js/app.js"></script>'
            )
            prepare(site, "/swami/pr-7", "documentation/swami")
            errors = validate(site, "/swami/pr-7")
            self.assertTrue(any("baseUrl" in error for error in errors))
            self.assertTrue(any("escapes hosting base" in error for error in errors))

    def test_missing_asset_fails_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "documentation/swami").mkdir(parents=True)
            (site / "documentation/swami/index.html").write_text(
                '<script>var baseUrl = "/swami/dev"</script>'
                '<script src="/swami/dev/js/missing.js"></script>'
            )
            prepare(site, "/swami/dev", "documentation/swami")
            self.assertIn(
                "referenced asset is missing: js/missing.js",
                validate(site, "/swami/dev"),
            )

    def test_missing_landing_page_cannot_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "landing page is missing"):
                prepare(Path(directory), "/swami/dev", "documentation/swami")


if __name__ == "__main__":
    unittest.main()
