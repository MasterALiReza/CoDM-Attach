#!/usr/bin/env python3
"""Simple QA script to verify used i18n keys exist in locales/en.json and locales/fa.json.

Usage:
  python scripts/check_i18n_keys.py [--paths handlers,app,core,managers,utils] [--fail-on-missing]

Notes:
- Only validates static keys like: t("some.key", ...). Dynamic f-strings are reported as skipped.
- Prints a compact report with missing keys per locale and exit code 1 when --fail-on-missing is set and any missing key is found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

RE_T_CALL = re.compile(r"t\(\s*([\'\"]) (?P<key>[^\'\"]+) \1", re.VERBOSE)
RE_T_FSTRING = re.compile(r"t\(\s*f[\'\"]", re.VERBOSE)

# Consider only probable i18n keys like: section.sub.key (alnum/underscore segments)
KEY_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$", re.IGNORECASE)

def filter_probable_keys(used: set[str]) -> set[str]:
    """Keep only keys matching dotted i18n pattern to avoid noise (punctuation, bare words)."""
    return {k for k in used if KEY_PATTERN.match(k)}


class Report(NamedTuple):
    used_keys: set[str]
    skipped_dynamic_usages: int
    missing_en: set[str]
    missing_fa: set[str]
    unused_in_en: set[str]
    unused_in_fa: set[str]


def flatten_json_keys(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= flatten_json_keys(v, key)
        else:
            keys.add(key)
    return keys


def iter_py_files(paths: Iterable[Path]) -> Iterator[Path]:
    for base in paths:
        if base.is_file() and base.suffix == ".py":
            yield base
        elif base.is_dir():
            for p in base.rglob("*.py"):
                # skip common virtual/test/cache folders
                if any(part in {".venv", "__pycache__", ".pytest_cache"} for part in p.parts):
                    continue
                yield p


def find_used_i18n_keys(files: Iterable[Path]) -> tuple[set[str], int]:
    used: set[str] = set()
    skipped_dynamic = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Count dynamic usages (f-strings)
        skipped_dynamic += len(RE_T_FSTRING.findall(text))
        # Collect static string-literal keys
        for m in RE_T_CALL.finditer(text):
            used.add(m.group("key"))
    return used, skipped_dynamic


def load_locale_keys(locale_path: Path) -> set[str]:
    try:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: failed to read locale file {locale_path}: {e}")
        return set()
    return flatten_json_keys(data)


def make_report(repo_root: Path, scan_dirs: list[str]) -> Report:
    targets = [repo_root / d for d in scan_dirs]
    files = list(iter_py_files(targets))

    used_keys, skipped_dynamic = find_used_i18n_keys(files)
    used_keys = filter_probable_keys(used_keys)

    en_keys = load_locale_keys(repo_root / "locales" / "en.json")
    fa_keys = load_locale_keys(repo_root / "locales" / "fa.json")

    missing_en = {k for k in used_keys if k not in en_keys}
    missing_fa = {k for k in used_keys if k not in fa_keys}

    unused_in_en = {k for k in en_keys if k not in used_keys}
    unused_in_fa = {k for k in fa_keys if k not in used_keys}

    return Report(
        used_keys=used_keys,
        skipped_dynamic_usages=skipped_dynamic,
        missing_en=missing_en,
        missing_fa=missing_fa,
        unused_in_en=unused_in_en,
        unused_in_fa=unused_in_fa,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QA i18n keys checker")
    parser.add_argument(
        "--paths",
        default="handlers,app,core,managers,utils",
        help="Comma-separated list of directories (relative to repo root) to scan",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit with non-zero code if any missing key is found",
    )
    args = parser.parse_args(argv)

    # repo root = parent of scripts/
    repo_root = Path(__file__).resolve().parents[1]
    scan_dirs = [s.strip() for s in args.paths.split(",") if s.strip()]

    report = make_report(repo_root, scan_dirs)

    print("\n=== i18n QA Report ===")
    print(f"Scanned directories: {', '.join(scan_dirs)}")
    print(f"Static keys used: {len(report.used_keys)} | Dynamic usages (skipped): {report.skipped_dynamic_usages}")

    if report.missing_en:
        print(f"\nMissing keys in en.json ({len(report.missing_en)}):")
        for k in sorted(report.missing_en):
            print(f"  - {k}")
    if report.missing_fa:
        print(f"\nMissing keys in fa.json ({len(report.missing_fa)}):")
        for k in sorted(report.missing_fa):
            print(f"  - {k}")

    # Uncomment to also show unused keys (can be noisy on large projects)
    # print(f"\nUnused keys in en.json: {len(report.unused_in_en)}")
    # print(f"Unused keys in fa.json: {len(report.unused_in_fa)}")

    if args.fail_on_missing and (report.missing_en or report.missing_fa):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
