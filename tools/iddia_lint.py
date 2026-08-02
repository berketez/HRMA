#!/usr/bin/env python3
"""İddia dili denetçisi — kazanılmamış hükümleri ve yanlış standart
başlıklarını ``hrma/`` ağacında tarar.

Neden var
---------
Faz 4 denetimi (``docs/FAZ4_CODEX_TEYIT.md`` C1-C5) şunu ölçtü: kodda 40
farklı standart atfı var ve elle kontrol edilen ÜÇ başlığın ÜÇÜ de yanlıştı.
Aynı denetimde PDF, arayüz ve doğrulayıcı modülü "NASA-grade accurate",
"NASA-standard methodologies", "Professional-grade ... validated NASA
standards" gibi hiçbir kod yolunun kazanmadığı hükümler basıyordu. Bunlar
tek tek düzeltilebilir ama geri gelmelerini yalnız makinece denetim önler.

Bu araç iki şeyi tarar:

1. **Yasak iddia kalıpları** — akreditasyon, uygunluk veya kabul hükmü ima
   eden ifadeler (``FORBIDDEN_CLAIMS``).
2. **Bilinen yanlış standart başlıkları** — ``docs/STANDART_ATIFLARI.md``
   kayıt defterinde doğrulanmış adla çelişen atıflar
   (``WRONG_STANDARD_TITLES``).

Muafiyet
--------
Düzeltme yorumlarımız kaldırdıkları kusuru birebir alıntılamak zorunda;
yoksa gelecekteki okuyucu neyin neden değiştiğini bilemez. İki muafiyet
işareti var:

* Satır içi:  ``IDDIA-LINT-MUAF`` geçen satır atlanır.
* Blok:       ``IDDIA-LINT-MUAF-BASLANGIC`` ile ``IDDIA-LINT-MUAF-BITIS``
  arasındaki satırlar atlanır (docstring içinde kusuru alıntılamak için).

Kayıt defteri (baseline)
------------------------
``tools/iddia_lint_baseline.txt`` bugün ağaçta duran isabetleri gerekçesiyle
listeler. Amaç susturmak değil, **envanteri görünür kılmak**: her satır ya
"meşru" gerekçesini ya da ``AÇIK BORÇ`` etiketini taşır. Kayıt anahtarı
satır NUMARASI değil, satır METNİNİN karması — böylece dosyanın başına satır
eklenince kayıt bayatlamaz, ama metin değişirse yeni isabet sayılır.

Kullanım
--------
    python3 tools/iddia_lint.py              # sadece kayıtta olmayanlar
    python3 tools/iddia_lint.py --all        # kayıttakiler dahil hepsi
    python3 tools/iddia_lint.py --debt       # yalnız AÇIK BORÇ satırları
    python3 tools/iddia_lint.py --emit-baseline   # kayıt taslağı üret

Kayıtta olmayan bir isabet varsa çıkış kodu 1'dir.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCAN_ROOT = os.path.join(REPO_ROOT, 'hrma')
BASELINE_PATH = os.path.join(REPO_ROOT, 'tools', 'iddia_lint_baseline.txt')

SCANNED_SUFFIXES = ('.py', '.js', '.html')
SKIPPED_DIR_NAMES = {'__pycache__', 'node_modules', '.git', 'venv', '.venv'}
SKIPPED_FILE_SUFFIXES = ('.min.js',)

INLINE_EXEMPT = 'IDDIA-LINT-MUAF'
BLOCK_OPEN = 'IDDIA-LINT-MUAF-BASLANGIC'
BLOCK_CLOSE = 'IDDIA-LINT-MUAF-BITIS'

DEBT_MARKER = 'AÇIK BORÇ'


class Rule(NamedTuple):
    """Tek bir tarama kuralı.

    ``allow_if`` verilirse ve satırda eşleşirse isabet sayılmaz — yalnız
    ifadenin OLUMSUZLANDIĞI (ör. "NOT guaranteed") durumlar için.
    """
    rule_id: str
    pattern: str
    why: str
    allow_if: Optional[str] = None


# --------------------------------------------------------------------------
# 1) Yasak iddia kalıpları
# --------------------------------------------------------------------------
FORBIDDEN_CLAIMS: Tuple[Rule, ...] = (
    Rule('nasa_grade', r'NASA[-\s]?grade',
         'Akreditasyon iddiası: NASA hiçbir HRMA çıktısını derecelendirmedi.'),
    Rule('nasa_validated', r'NASA[-\s]validated|validated\s+NASA',
         'Bağımsız doğrulama iddiası: depoda NASA doğrulaması yok.'),
    Rule('nasa_standard_methodology',
         r'NASA[-\s]standards?\s+methodolog\w*',
         'Uygunluk iddiası: hiçbir kod yolu standart uygunluğu denetlemiyor.'),
    Rule('flight_certified', r'flight[-\s]certified|certified\s+for\s+flight',
         'Uçuş sertifikasyonu iddiası: kalifikasyon süreci yok.'),
    Rule('manufacturing_ready',
         r'manufactur\w*[-\s]ready|ready\s+for\s+manufactur\w*',
         'İmalata hazırlık hükmü: tolerans/malzeme kabulü yapılmıyor.'),
    Rule('safe_for_operation', r'safe\s+for\s+operation',
         'İşletme emniyeti hükmü: model emniyet kararı veremez.'),
    Rule('professional_grade', r'professional[-\s]grade',
         'Derecelendirme iddiası: ölçülebilir bir karşılığı yok.'),
    Rule('guaranteed', r'\bguarantee[ds]?\b',
         'Garanti dili: sayısal sonuç için garanti verilemez.',
         allow_if=r'(?i)\b(not|never|no|de[gğ]il|asla)\b[^.]{0,24}guarantee'),
    Rule('high_fidelity', r'high[-\s]fidelity',
         'Sadakat iddiası: yalnız tanımlı bir çözüm kademesinin ADI olarak '
         'meşru; ürün/paket sıfatı olarak kullanılamaz.'),
    Rule('digital_twin', r'digital\s+twin',
         'Dijital ikiz iddiası: kalibrasyon ve telemetri bağı yok.'),
    Rule('code_compliant',
         r'\b(NFPA|OSHA|DOT|ASME|ISO|AIAA)[-\s]compliant'
         r'|compliant\s+with\s+(NFPA|OSHA|DOT)',
         'Yönetmelik uygunluğu hükmü: uygunluk denetimi koşmuyor.'),
    Rule('preliminary_design_ok', r'acceptable\s+for\s+preliminary\s+design',
         'Tasarım aşaması kabul hükmü: dayanağı olan bir eşik yok.'),
)

# --------------------------------------------------------------------------
# 2) Bilinen yanlış standart başlıkları
#    Doğrulanmış adlar: docs/STANDART_ATIFLARI.md
# --------------------------------------------------------------------------
WRONG_STANDARD_TITLES: Tuple[Rule, ...] = (
    Rule('std5012_wrong_title',
         r'NASA[-\s]?STD[-\s]?5012\W{0,3}\s*Pressure\s+Vessels',
         'NASA-STD-5012 = "Strength and Life Assessment Requirements for '
         'Liquid-Fueled Space Propulsion System Engines" (Rev. B, 2016); '
         'basınçlı kap standardı DEĞİL.'),
    Rule('sp8124_wrong_title',
         r'SP[-\s]?8124\W{0,3}\s*Thermal\s+Design\s+Criteria',
         'NASA SP-8124 = "Liquid Rocket Engine Self-Cooled Combustion '
         'Chambers" (1977, NTRS 78N21211).'),
    Rule('sp125_wrong_title',
         r'SP[-\s]?125\W{0,3}\s*Liquid[-\s]Propellant\s+Rocket\s+Engine\s+'
         r'Performance',
         'NASA SP-125 = "Design of Liquid Propellant Rocket Engines" '
         '(Huzel & Huang, 2. baskı 1971).'),
)

ALL_RULES: Tuple[Rule, ...] = FORBIDDEN_CLAIMS + WRONG_STANDARD_TITLES
_COMPILED: Dict[str, Tuple[re.Pattern, Optional[re.Pattern]]] = {
    rule.rule_id: (re.compile(rule.pattern, re.IGNORECASE),
                   re.compile(rule.allow_if) if rule.allow_if else None)
    for rule in ALL_RULES
}
RULES_BY_ID: Dict[str, Rule] = {rule.rule_id: rule for rule in ALL_RULES}


class Finding(NamedTuple):
    path: str          # depo köküne göreli yol
    line_no: int       # 1 tabanlı
    rule_id: str
    matched: str       # eşleşen ham metin
    line_hash: str     # satır metninin karması (kayıt anahtarı)
    line_text: str


def _line_hash(text: str) -> str:
    """Satır metninin normalleştirilmiş karması.

    Satır numarası kullanılmaz: dosyanın başına satır eklendiğinde kayıt
    bayatlamasın. Boşluk normalleştirilir ki yeniden girintileme kaydı
    bozmasın; METİN değişirse karma değişir ve isabet yeniden görünür.
    """
    normalised = ' '.join(text.split())
    return hashlib.sha1(normalised.encode('utf-8')).hexdigest()[:12]


def _iter_source_files(root: str) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIPPED_DIR_NAMES)
        for name in sorted(filenames):
            if not name.endswith(SCANNED_SUFFIXES):
                continue
            if name.endswith(SKIPPED_FILE_SUFFIXES):
                continue
            yield os.path.join(dirpath, name)


def scan_file(abs_path: str) -> List[Finding]:
    rel = os.path.relpath(abs_path, REPO_ROOT)
    try:
        with open(abs_path, encoding='utf-8') as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    findings: List[Finding] = []
    in_exempt_block = False
    for index, raw in enumerate(lines, start=1):
        if BLOCK_OPEN in raw:
            in_exempt_block = True
            continue
        if BLOCK_CLOSE in raw:
            in_exempt_block = False
            continue
        if in_exempt_block or INLINE_EXEMPT in raw:
            continue
        for rule in ALL_RULES:
            pattern, allow = _COMPILED[rule.rule_id]
            match = pattern.search(raw)
            if not match:
                continue
            if allow is not None and allow.search(raw):
                continue
            findings.append(Finding(
                path=rel, line_no=index, rule_id=rule.rule_id,
                matched=match.group(0), line_hash=_line_hash(raw),
                line_text=raw.strip()))
    return findings


def scan(root: str = DEFAULT_SCAN_ROOT) -> List[Finding]:
    """``root`` altındaki kaynak dosyaları tara."""
    findings: List[Finding] = []
    for path in _iter_source_files(root):
        findings.extend(scan_file(path))
    return findings


def load_baseline(path: str = BASELINE_PATH) -> Dict[Tuple[str, str, str], str]:
    """Kayıt defterini oku: (yol, kural, satır karması) -> gerekçe."""
    entries: Dict[Tuple[str, str, str], str] = {}
    if not os.path.exists(path):
        return entries
    with open(path, encoding='utf-8') as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            parts = [part.strip() for part in line.split('|')]
            if len(parts) < 4:
                continue
            entries[(parts[0], parts[1], parts[2])] = '|'.join(parts[3:]).strip()
    return entries


def unbaselined(findings: Iterable[Finding],
                baseline: Dict[Tuple[str, str, str], str]) -> List[Finding]:
    return [f for f in findings
            if (f.path, f.rule_id, f.line_hash) not in baseline]


def open_debts(baseline: Dict[Tuple[str, str, str], str]
               ) -> List[Tuple[str, str, str, str]]:
    """Kayıt defterinde ``AÇIK BORÇ`` etiketli satırlar."""
    return [(path, rule, digest, reason)
            for (path, rule, digest), reason in sorted(baseline.items())
            if DEBT_MARKER in reason]


def _format(finding: Finding) -> str:
    rule = RULES_BY_ID[finding.rule_id]
    return (f'{finding.path}:{finding.line_no}  [{finding.rule_id}] '
            f'"{finding.matched}"\n'
            f'    satır : {finding.line_text[:150]}\n'
            f'    neden : {rule.why}\n'
            f'    kayıt : {finding.path} | {finding.rule_id} | '
            f'{finding.line_hash} | <gerekçe>')


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_SCAN_ROOT,
                        help='taranacak kök dizin (varsayılan: hrma/)')
    parser.add_argument('--all', action='store_true',
                        help='kayıttakiler dahil bütün isabetleri göster')
    parser.add_argument('--debt', action='store_true',
                        help='yalnız AÇIK BORÇ kayıtlarını listele')
    parser.add_argument('--emit-baseline', action='store_true',
                        help='mevcut isabetlerden kayıt taslağı bas')
    args = parser.parse_args(argv)

    findings = scan(args.root)
    baseline = load_baseline()

    if args.emit_baseline:
        for finding in findings:
            print(f'{finding.path} | {finding.rule_id} | '
                  f'{finding.line_hash} | TODO gerekçe  # {finding.line_text[:90]}')
        return 0

    if args.debt:
        debts = open_debts(baseline)
        for path, rule, _digest, reason in debts:
            print(f'{path}  [{rule}]  {reason}')
        print(f'\nAÇIK BORÇ: {len(debts)} kayıt')
        return 0

    shown = findings if args.all else unbaselined(findings, baseline)
    for finding in shown:
        print(_format(finding))
        print()

    new_hits = unbaselined(findings, baseline)
    debts = open_debts(baseline)
    print(f'Taranan kök : {os.path.relpath(args.root, REPO_ROOT)}')
    print(f'Toplam isabet: {len(findings)}  '
          f'(kayıtlı {len(findings) - len(new_hits)}, '
          f'kayıtsız {len(new_hits)}, açık borç {len(debts)})')
    return 1 if new_hits else 0


if __name__ == '__main__':
    sys.exit(main())
