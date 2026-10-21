"""Export a customer source package using an explicit source allowlist.

Run with Python 3.12. No Git metadata, local configuration or runtime data is read.
"""
import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "distribution" / "template"
SOURCE_TREES = ("backend/app", "backend/tests", "frontend/app", "frontend/components", "frontend/lib", "e2e/tests", "nginx")
SOURCE_FILES = ("LICENSE", "backend/Dockerfile", "backend/requirements.txt", "backend/.dockerignore",
                "frontend/Dockerfile", "frontend/Dockerfile.prod", "frontend/.dockerignore", "frontend/package.json",
                "frontend/package-lock.json", "frontend/tsconfig.json", "frontend/next-env.d.ts",
                "e2e/package.json", "e2e/package-lock.json", "e2e/playwright.config.ts", "docker-compose.yml", "docker-compose.prod.yml",
                "scripts/test-regressions.ps1", "scripts/test-browser.ps1")
SKIP = {"node_modules", ".next", "__pycache__", ".git", ".cache"}
PACKAGE_VERSION = "1.0.1"


def files_under(folder):
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink is not allowed: {path.name}")
        if path.is_file() and not SKIP.intersection(path.relative_to(folder).parts) and path.suffix not in (".pyc", ".pyo"):
            yield path


def validate(folder):
    findings = []
    for path in files_under(folder):
        relative = path.relative_to(folder).as_posix()
        if ".git" in path.relative_to(folder).parts or path.name == ".env" or path.suffix.lower() in (".dump", ".key", ".pem", ".crt", ".pdf", ".zip", ".tar", ".bundle", ".backup", ".bak", ".tmp", ".log"):
            findings.append(relative)
        content = path.read_bytes()
        if b"\0" in content:
            continue
        text = content.decode("utf-8", errors="replace")
        if re.search(r"kemensos|pusdatin|D:\\KERJAAN|Users[\\/]dcpus|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}", text, re.I):
            findings.append(relative)
    if findings:
        raise ValueError("Customer package contains excluded data: " + ", ".join(sorted(set(findings))))


def export(output, revision):
    output = output.resolve()
    if output.exists():
        raise ValueError("Output already exists; use a new directory to preserve previous packages.")
    if ROOT == output or output in ROOT.parents or (ROOT / "distribution") in (output, *output.parents):
        raise ValueError("Output must not replace the source project or templates.")
    output.mkdir(parents=True)
    for tree in SOURCE_TREES:
        extensions = {".py"} if tree.startswith("backend/") else {".conf"} if tree == "nginx" else {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".json"}
        for source in files_under(ROOT / tree):
            if source.suffix.lower() not in extensions:
                continue
            target = output / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for name in SOURCE_FILES:
        source = ROOT / name
        if source.exists():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    # Brand substitutions are applied only to the export, never the live project.
    replacements = {
        "frontend/components/Navigation.tsx": [
            ('aria-label="Zabbix Reports — PUSDATIN KEMENSOS" title="PUSDATIN KEMENSOS"', 'aria-label={branding.product} title={branding.organization}'),
            ('src="/brand/kemensos.png" alt="Logo Kementerian Sosial Republik Indonesia"', 'src={branding.logo} alt={branding.product}'),
            ('<span className="brand-copy">Zabbix Reports<small>PUSDATIN KEMENSOS</small>', '<span className="brand-copy">{branding.product}<small>{branding.organization}</small>'),
        ],
        "frontend/app/login/page.tsx": [
            ('src="/brand/kemensos.png" alt="Logo Kemensos"', 'src={branding.logo} alt={branding.product}'),
            ('<strong>Zabbix Reports</strong><small>PUSDATIN KEMENSOS</small>', '<strong>{branding.product}</strong><small>{branding.organization}</small>'),
            ('TIM DATA CENTER', 'OPERATIONS TEAM'),
        ],
        "frontend/app/page.tsx": [('TIM DATA CENTER PUSDATIN KEMENSOS', '{branding.organization}')],
        "frontend/app/layout.tsx": [('title:"Zabbix Report Exporter"', 'title:branding.product'), ('icon:"/brand/kemensos.png"', 'icon:branding.logo')],
    }
    for name, changes in replacements.items():
        path = output / name
        text = path.read_text(encoding="utf-8")
        depth = "../../lib/branding" if name == "frontend/app/login/page.tsx" else "../lib/branding"
        text = text.replace('import ', f'import {{branding}} from "{depth}";\nimport ', 1)
        for old, new in changes:
            if old not in text:
                raise ValueError(f"Branding source changed; review export transform: {name}")
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    shell = output / "frontend/components/AccessShell.tsx"
    text = shell.read_text(encoding="utf-8").replace('import {useEffect', 'import {branding} from "../lib/branding";\nimport {useEffect', 1)
    text = text.replace('<div className="workspace-content">', '<div className="workspace-content">{branding.demo && <p className="alert warning">DEMO — Data sintetis untuk contoh implementasi. Tidak terhubung ke server client.</p>}')
    shell.write_text(text, encoding="utf-8")

    for tree in (output / "backend", output / "e2e", output / "frontend"):
        for path in files_under(tree):
            if path.suffix not in (".py", ".ts", ".tsx"):
                continue
            text = path.read_text(encoding="utf-8")
            text = text.replace("Zabbix 7", "Zabbix Utama").replace("Zabbix 2", "Zabbix Cadangan")
            text = text.replace("PUSDATIN KEMENSOS", "CONTOH ORGANISASI").replace("Logo Kementerian Sosial Republik Indonesia", "Zabbix Report Exporter")
            text = text.replace("PUSDATIN", "OPERASIONAL").replace("kemensos.png", "logo.svg")
            text = text.replace("10.59.0.", "192.0.2.")
            path.write_text(text, encoding="utf-8")

    compose = output / "docker-compose.yml"
    text = re.sub(r"^\s+container_name:.*\n", "", compose.read_text(encoding="utf-8"), flags=re.M)
    compose.write_text(text, encoding="utf-8")
    prod = output / "docker-compose.prod.yml"
    text = prod.read_text(encoding="utf-8").replace("zabbix-report-exporter-backend:1.0.0", "${COMPOSE_PROJECT_NAME:-zabbix-starter}-backend:1.0.0")
    text = text.replace("zabbix-report-exporter-worker:1.0.0", "${COMPOSE_PROJECT_NAME:-zabbix-starter}-worker:1.0.0").replace("zabbix-report-exporter-frontend:1.0.0", "${COMPOSE_PROJECT_NAME:-zabbix-starter}-frontend:1.0.0")
    prod.write_text(text, encoding="utf-8")
    frontend = output / "frontend/Dockerfile.prod"
    frontend.write_text(frontend.read_text(encoding="utf-8").replace("RUN npm run build", "ARG NEXT_PUBLIC_DEMO_MODE=false\nENV NEXT_PUBLIC_DEMO_MODE=$NEXT_PUBLIC_DEMO_MODE\nRUN npm run build"), encoding="utf-8")
    for name in ("scripts/test-regressions.ps1", "scripts/test-browser.ps1"):
        path = output / name
        if path.exists():
            text = path.read_text(encoding="utf-8").replace("codex-zabbix-backend-mvp:20261007", "zabbix-starter-demo-backend:1.0.0")
            text = text.replace("codex-zabbix-frontend-enterprise:20261007", "zabbix-starter-demo-frontend:1.0.0")
            path.write_text(text, encoding="utf-8")

    for source in files_under(TEMPLATE):
        relative = source.relative_to(TEMPLATE).as_posix()
        relative = {"environment.example": ".env.example", "certs.keep": "certs/.gitkeep", "reports.keep": "storage/reports/.gitkeep"}.get(relative, relative)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Keep Git clones and ZIPs byte-identical on Windows and Linux. PNG assets
    # retain their original bytes; all other allowlisted files are UTF-8 text.
    for path in files_under(output):
        if path.suffix.lower() != ".png":
            data = path.read_bytes()
            if b"\r\n" in data:
                path.write_bytes(data.replace(b"\r\n", b"\n"))
    validate(output)
    inventory = [{"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files_under(output)]
    manifest = {"edition": "client-starter", "version": PACKAGE_VERSION, "source_revision": revision,
                "contains_production_runtime_data": False, "contains_production_credentials": False,
                "demo_data_is_synthetic": True, "files": inventory}
    (output / "PACKAGE-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive = output.parent / (output.name + ".zip")
    if archive.exists():
        raise ValueError("ZIP already exists; previous packages are preserved.")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path in files_under(output):
            package.write(path, Path(output.name) / path.relative_to(output))
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError("ZIP verification failed")
    print(json.dumps({"output": str(output), "zip": str(archive), "source_files": len(inventory),
                      "zip_bytes": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--revision", default="working-tree")
    args = parser.parse_args()
    export(args.output, args.revision)
