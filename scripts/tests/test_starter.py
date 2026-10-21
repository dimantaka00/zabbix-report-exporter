import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = load("export_starter", ROOT / "scripts/export-starter.py")
configure = load("starter_configure", ROOT / "distribution/template/scripts/configure.py")


class ConfigurationTests(unittest.TestCase):
    def create(self, folder):
        path = Path(folder)
        shutil.copyfile(ROOT / "distribution/template/environment.example", path / ".env.example")
        return path

    def test_independent_credentials_and_existing_configuration_preserved(self):
        passwords = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as folder:
                root = self.create(folder)
                with patch.object(configure, "ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                    configure.configure("https://zabbix.example.invalid/api_jsonrpc.php", "synthetic-read-only-token")
                    original = (root / ".env").read_text()
                    settings = dict(line.split("=", 1) for line in original.splitlines() if line and not line.startswith("#"))
                    passwords.append(settings["POSTGRES_PASSWORD"])
                    self.assertGreaterEqual(len(settings["POSTGRES_PASSWORD"]), 32)
                    self.assertNotEqual(settings["POSTGRES_PASSWORD"], settings["AUTH_BOOTSTRAP_PASSWORD"])
                    self.assertEqual(settings["AUTH_ENABLED"], "true")
                    self.assertIn(settings["POSTGRES_PASSWORD"], settings["DATABASE_URL"])
                    if os.name != "nt":
                        self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)
                    with self.assertRaises(FileExistsError):
                        configure.configure("https://zabbix.example.invalid/api_jsonrpc.php", "another-test-token")
                    self.assertEqual((root / ".env").read_text(), original)
        self.assertNotEqual(*passwords)

    def test_env_injection_and_embedded_credentials_are_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(configure, "ROOT", Path(folder)):
            for url in ("https://example.invalid/\nAUTH_ENABLED=false", "https://user:pass@example.invalid/api", "file:///etc/passwd", "https://example.invalid/$TOKEN", "https://example.invalid/api?token=abc"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    configure.configure(url, "synthetic-token")
            for token in ("", "one\nAUTH_ENABLED=false", "$TOKEN", "abc#value"):
                with self.subTest(token=token), self.assertRaises(ValueError):
                    configure.configure("https://example.invalid/api", token)
            self.assertFalse((Path(folder) / ".env").exists())


class ExportTests(unittest.TestCase):
    def test_allowlist_excludes_local_data_and_zip_checksums_match(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source"
            template = source / "distribution/template"
            shutil.copytree(ROOT / "distribution/template", template)
            for name in exporter.SOURCE_FILES:
                path = ROOT / name
                if path.exists():
                    target = source / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
            for name in ("frontend/components/Navigation.tsx", "frontend/components/AccessShell.tsx", "frontend/app/login/page.tsx", "frontend/app/page.tsx", "frontend/app/layout.tsx"):
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            for name in (".env", ".git/config", "storage/reports/private.pdf", "certs/private.key", ".cache/session.json", "backend/app/legacy.py.backup", "frontend/app/legacy.tsx.backup"):
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("PRIVATE_EXPORT_SENTINEL")
            output = base / "customer-source-1.0.0"
            with patch.object(exporter, "ROOT", source), patch.object(exporter, "TEMPLATE", template), contextlib.redirect_stdout(io.StringIO()):
                exporter.export(output, "test-revision")
            manifest = json.loads((output / "PACKAGE-MANIFEST.json").read_text())
            self.assertEqual(manifest["source_revision"], "test-revision")
            self.assertFalse((output / ".env").exists())
            self.assertTrue((output / ".env.example").exists())
            self.assertTrue((output / "storage/reports/.gitkeep").exists())
            self.assertFalse(list(output.rglob("*.backup")))
            self.assertIn("CONTOH ORGANISASI", (output / "frontend/lib/branding.ts").read_text())
            for record in manifest["files"]:
                data = (output / record["path"]).read_bytes()
                self.assertNotIn(b"PRIVATE_EXPORT_SENTINEL", data)
                if not record["path"].endswith(".png"):
                    self.assertNotIn(b"\r\n", data)
                self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
            with zipfile.ZipFile(output.parent / (output.name + ".zip")) as package:
                self.assertIsNone(package.testzip())
                self.assertTrue(any(name.endswith("/.env.example") for name in package.namelist()))
                self.assertFalse(any(name.endswith("/.env") for name in package.namelist()))


if __name__ == "__main__":
    unittest.main()
