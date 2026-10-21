"""Create a new production .env with independent random credentials.

Python 3.10+; token input is hidden. Existing configurations are never overwritten.
"""
import argparse
import csv
import getpass
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def configure(url, token):
    if any(char.isspace() or ord(char)<32 or char in '\"\' $`#\\' for char in url):
        raise ValueError("URL API tidak boleh mengandung karakter kontrol atau sintaks .env.")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Gunakan URL API HTTP/HTTPS tanpa user, password, query, atau fragment.")
    if not token or any(char in token for char in '\r\n"\' $`#\\'):
        raise ValueError("Token API harus satu baris tanpa karakter kontrol atau sintaks .env.")
    database_password, admin_password = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    text = text.replace("GENERATE_A_NEW_RANDOM_DATABASE_PASSWORD", database_password)
    text = text.replace("GENERATE_A_NEW_RANDOM_ADMIN_PASSWORD", admin_password)
    text = text.replace("https://zabbix.example.invalid/api_jsonrpc.php", url)
    text = text.replace("REPLACE_WITH_YOUR_READ_ONLY_ZABBIX_TOKEN", token)
    target = ROOT / ".env"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)
    if os.name == "nt":
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, text=True)
        sid = next(csv.reader(result.stdout.splitlines()))[1]
        subprocess.run(["icacls", str(target), "/inheritance:r", "/grant:r", f"*{sid}:(F)",
                        "*S-1-5-18:(F)", "*S-1-5-32-544:(F)"], check=True, capture_output=True)
    print("Konfigurasi dibuat pada .env. Username awal: admin.")
    print("Password awal acak tersimpan pada AUTH_BOOTSTRAP_PASSWORD; buka .env secara lokal.")
    print("Jalankan: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="URL API Zabbix client")
    parser.add_argument("--non-interactive", action="store_true", help="Read token from ZABBIX_SETUP_TOKEN; requires --url")
    args = parser.parse_args()
    try:
        url = args.url or ("" if args.non_interactive else input("URL API Zabbix: ").strip())
        token = os.environ.get("ZABBIX_SETUP_TOKEN", "") if args.non_interactive else getpass.getpass("Read-only API token: ").strip()
        configure(url, token)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("Konfigurasi gagal. URL/token harus valid dan .env belum boleh ada; periksa izin file.") from None
