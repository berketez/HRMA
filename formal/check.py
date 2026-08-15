#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HRMA biçimsel doğrulama kapısı.

Üç denetim yapar ve herhangi biri düşerse çıkış kodu 1 döner:

1. DERLEME  — `lake build` çalıştırır; çıktıda `sorry`/`sorryAx` arar.
2. AKSİYOM  — registry.json'daki HER teorem için `#print axioms` çalıştırır;
              teorem yoksa veya `sorryAx`'a dayanıyorsa hata verir. Bu denetim
              derleme önbelleği sessiz kaldığında bile ispat deliklerini yakalar.
3. BAĞ      — registry.json'daki her kaydın
              (a) lean_file:lean_line satırında gerçekten o teoremin bildirimi,
              (b) python_file:python_line satırında gerçekten `anchor` metni
              var mı diye bakar. Dosya yoksa, satır kaydıysa veya anchor
              başka satıra taşındıysa hata verir (taşındıysa yeni satırı önerir).

Kullanım:
    python3 formal/check.py                # tam denetim (derleme dahil)
    python3 formal/check.py --skip-build   # yalnız aksiyom + bağ denetimi
    python3 formal/check.py --links-only   # yalnız bağ denetimi (Lean gerekmez)

Neden var: Lean ile Python arasındaki bağ elle tutuluyor. Bu betik, bağın
sessizce çürümesini (satır kayması, dosya taşınması, deftere girmemiş delikli
ispat) makine düzeyinde engeller.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FORMAL_DIR = Path(__file__).resolve().parent
REPO_DIR = FORMAL_DIR.parent
REGISTRY_PATH = FORMAL_DIR / "registry.json"

# `sorry` içeren derleme uyarıları: "declaration uses 'sorry'" veya sorryAx.
SORRY_RE = re.compile(r"\bsorry(Ax)?\b")
AXIOM_LINE_RE = re.compile(r"'([^']+)' depends on axioms: \[([^\]]*)\]")
NO_AXIOM_LINE_RE = re.compile(r"'([^']+)' does not depend on any axioms")

FAIL = "HATA"
OK = "TAMAM"


def load_registry() -> list[dict]:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    entries = data["entries"]
    if not entries:
        raise SystemExit(f"{FAIL}: registry.json boş — denetlenecek teorem yok.")
    return entries


def run_build() -> list[str]:
    """`lake build` çalıştırır; hataları döndürür (boş liste = temiz)."""
    errors: list[str] = []
    print("[1/3] lake build ...", flush=True)
    proc = subprocess.run(
        ["lake", "build"],
        cwd=FORMAL_DIR,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    out = proc.stdout + proc.stderr
    tail = "\n".join(out.strip().splitlines()[-3:])
    if proc.returncode != 0:
        errors.append(f"lake build başarısız (çıkış {proc.returncode}). Son satırlar:\n{tail}")
        return errors
    print(f"      {tail}")
    for line in out.splitlines():
        # Aksiyom bilgi satırlarını atla; onları 2. adım ayrıca değerlendiriyor.
        if AXIOM_LINE_RE.search(line) or NO_AXIOM_LINE_RE.search(line):
            if "sorryAx" in line:
                errors.append(f"derleme çıktısında sorryAx'lı aksiyom satırı: {line.strip()}")
            continue
        if SORRY_RE.search(line):
            errors.append(f"derleme çıktısında sorry izi: {line.strip()}")
    return errors


def run_axiom_check(entries: list[dict]) -> list[str]:
    """Her teorem için #print axioms çalıştırıp sorryAx arar."""
    errors: list[str] = []
    print("[2/3] aksiyom denetimi (#print axioms) ...", flush=True)
    check_dir = FORMAL_DIR / ".lake"
    check_dir.mkdir(exist_ok=True)
    check_file = check_dir / "check_axioms.lean"
    lines = ["import LeanLab", ""]
    lines += [f"#print axioms {e['theorem']}" for e in entries]
    check_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    proc = subprocess.run(
        ["lake", "env", "lean", str(check_file)],
        cwd=FORMAL_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        head = "\n".join(out.strip().splitlines()[:8])
        errors.append(
            f"#print axioms derlemesi başarısız (çıkış {proc.returncode}) — "
            f"muhtemelen defterdeki bir teorem Lean'de yok. İlk satırlar:\n{head}"
        )
    reported: dict[str, str] = {}
    for line in out.splitlines():
        m = AXIOM_LINE_RE.search(line)
        if m:
            reported[m.group(1)] = m.group(2)
            continue
        m = NO_AXIOM_LINE_RE.search(line)
        if m:
            reported[m.group(1)] = ""
    for e in entries:
        name = e["theorem"]
        if name not in reported:
            errors.append(f"{name}: #print axioms çıktısı alınamadı (teorem mevcut mu?)")
            continue
        axioms = reported[name]
        if "sorryAx" in axioms:
            errors.append(f"{name}: ispat delikli — sorryAx'a dayanıyor: [{axioms}]")
    if not errors:
        print(f"      {len(entries)} teoremin tamamı doğrulandı; hiçbirinde sorryAx yok.")
    return errors


def check_line(path: Path, lineno: int, needle: str, label: str) -> str | None:
    """path:lineno satırında needle var mı? Yoksa açıklayıcı hata döndürür."""
    if not path.is_file():
        return f"{label}: dosya yok: {path}"
    file_lines = path.read_text(encoding="utf-8").splitlines()
    if lineno < 1 or lineno > len(file_lines):
        return f"{label}: satır {lineno} dosya dışında ({path.name} {len(file_lines)} satır)"
    if needle in file_lines[lineno - 1]:
        return None
    # Satır kaymış olabilir — anchor'ı dosyada ara, bulursan öner.
    hits = [i + 1 for i, ln in enumerate(file_lines) if needle in ln]
    if hits:
        return (
            f"{label}: satır {lineno} kaymış; aranan metin şimdi "
            f"{', '.join(str(h) for h in hits)}. satırda. registry.json'u güncelle."
        )
    return f"{label}: aranan metin dosyada hiç yok: {needle!r}"


def run_link_check(entries: list[dict]) -> list[str]:
    errors: list[str] = []
    print("[3/3] bağ denetimi (registry ↔ Lean ↔ Python) ...", flush=True)
    for e in entries:
        name = e["theorem"]
        short = name.rsplit(".", 1)[-1]
        lean_path = REPO_DIR / e["lean_file"]
        err = check_line(lean_path, e["lean_line"], f"theorem {short}",
                         f"{name} → {e['lean_file']}:{e['lean_line']}")
        if err:
            errors.append(err)
        py_path = REPO_DIR / e["python_file"]
        err = check_line(py_path, e["python_line"], e["anchor"],
                         f"{name} → {e['python_file']}:{e['python_line']}")
        if err:
            errors.append(err)
    if not errors:
        print(f"      {len(entries)} kaydın Lean ve Python bağlarının tamamı yerinde.")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-build", action="store_true",
                    help="lake build adımını atla (aksiyom + bağ denetimi kalır)")
    ap.add_argument("--links-only", action="store_true",
                    help="yalnız registry bağ denetimi (Lean araç zinciri gerekmez)")
    args = ap.parse_args()

    entries = load_registry()
    errors: list[str] = []

    if args.links_only:
        print("[1/3] lake build — atlandı (--links-only)")
        print("[2/3] aksiyom denetimi — atlandı (--links-only)")
    else:
        if args.skip_build:
            print("[1/3] lake build — atlandı (--skip-build)")
        else:
            errors += run_build()
        errors += run_axiom_check(entries)
    errors += run_link_check(entries)

    print()
    if errors:
        print(f"{FAIL} — {len(errors)} sorun:")
        for err in errors:
            print(f"  ✗ {err}")
        return 1
    print(f"{OK} — kayıt defterindeki {len(entries)} teorem: derleme temiz, "
          "sorryAx yok, tüm bağlar yerinde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
