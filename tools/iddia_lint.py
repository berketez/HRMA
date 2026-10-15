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

#: Kullanıcıya GİDEN belgeler (Faz 5 / H5-5).
#:
#: Ölçüm (3 Ağustos 2026, HEAD 9d3728e): araç yalnız ``hrma/`` ağacını ve
#: yalnız ``.py/.js/.html`` uzantılarını tarıyordu. Yani ``README.md``,
#: ``docs/USER_MANUAL.md``, ``docs/user_guide/*.tex`` ve sürüm notları HİÇ
#: taranmıyordu — oysa ``hrma/app.py:786`` (``/user-guide/open``) kullanıcıya
#: doğrudan ``docs/user_guide`` içeriğini açıyor. Aynı kuralları belgelere
#: uygulayınca çıkan isabetlerin arasında düzeltilmiş sayılan bir kusurun
#: hayatta kalan kolu vardı: ``packaging/release_notes_v2.6.1.md:47``
#: "'digital twin' wording is now 'interactive 3D model' THROUGHOUT" diyordu,
#: ama ``docs/README.md`` ve ``docs/USER_MANUAL.md`` beş yerde hâlâ
#: "digital twin" yazıyordu.
#:
#: Kapsam sınırı bilinçlidir: DENETİM ve PLAN belgeleri (``docs/archive/``,
#: bulgu defterleri, faz planları, ``paper/``) buraya alınmadı; onlar
#: kaldırdıkları kusuru BİREBİR alıntılamak zorundadır, taranırlarsa araç
#: kendi kanıt defterini ihlal sayar. Buradaki liste "kullanıcının eline
#: geçen metin" ölçütüyle seçilmiştir.
USER_FACING_DOC_TARGETS: Tuple[str, ...] = (
    'README.md',
    'INSTALL.md',
    'CONTRIBUTING.md',
    'docs/README.md',
    'docs/USER_MANUAL.md',
    'docs/RELEASE.md',
    'docs/user_guide',      # /user-guide/open ile kullanıcıya açılır
    'packaging',            # sürüm notları güncelleme akışında gösterilir
)

#: Varsayılan tarama hedefleri: kaynak ağacı + kullanıcıya giden belgeler.
DEFAULT_SCAN_TARGETS: Tuple[str, ...] = ('hrma',) + USER_FACING_DOC_TARGETS

SCANNED_SUFFIXES = ('.py', '.js', '.html', '.md', '.tex')
#: Taranmayan dizin ADLARI. Son üçü DERLEME ARTIĞIDIR ve 3 Ağustos 2026'da
#: eklendi: ``packaging`` tarama hedefine girince (sürüm notları için, H5-5)
#: ``packaging/win/payload/app/hrma/app.py`` da taranmaya başladı — bu,
#: uygulamanın ESKİ bir derlemeden kalma tam kopyasıdır ve içinde o gün
#: kaynaktan kaldırılmış "ready for manufacturing" ifadesi hâlâ duruyordu.
#: Artığı kaynak sanıp rapor etmek yanlış: derleme sırasında
#: ``build_win_payload.sh`` ``$SRC/hrma``'yı taze rsync'liyor. Kaynak ağacında
#: bu adlarda dizin YOK (kontrol edildi), yani ad bazlı atlama güvenli.
SKIPPED_DIR_NAMES = {'__pycache__', 'node_modules', '.git', 'venv', '.venv',
                     'archive',
                     'payload', 'libs', 'build.noindex'}
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
         # MUAFİYET İFADE KAPSAMLI (P10B4-03). Eski desen
         #   \b(not|never|no|değil|asla)\b[^.]{0,24}guarantee
         # olumsuzlamanın garanti sözcüğünü GERÇEKTEN kapsayıp kapsamadığına
         # bakmıyordu, yalnız 24 karakterlik bir pencerede olumsuzlama sözcüğü
         # arıyordu. Ölçülen kaçak: "There is no doubt: results are guaranteed
         # to 3 sigma." — 'no doubt: results are guarantee' penceresi tuttuğu
         # için isabet ÜRETİLMİYORDU. "no risk is guaranteed" aynı sınıftır.
         # Yeni desen yalnız olumsuzlamanın doğrudan garanti eylemini yönettiği
         # biçimleri muaf tutar; araya noktalama giremez (\w+ noktalama
         # eşleşmez) ve en fazla iki sözcük girebilir.
         allow_if=r'(?i)(?:\bno\s+guarantee[sd]?\b'
                  r'|\bwithout\s+(?:any\s+)?guarantee'
                  r'|\b(?:not|never)\s+(?:\w+\s+){0,2}guarantee[ds]?\b'
                  r'|\bguarantee[ds]?\s+(?:de[gğ]ildir|edilmez|verilmez))'),
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

# --------------------------------------------------------------------------
# 3) KÜNYE YALANI ve KAZANILMAMIŞ DOĞRULUK/EMNİYET HÜKMÜ (P10B4-01)
#
# Ölçüm (27 Ağustos 2026, ``docs/scofield/raw/P10/B4-repro-01.py``):
# kampanyanın P4-P7'de ÖLÇÜMLE kanıtladığı 15 iddia sınıfını temsil eden
# satırlar tek dosyaya yazılıp ``scan_file`` çalıştırıldı; **yakalanan 3,
# kaçan 15**. Yakalanan üçü (``NASA-grade``, ``digital twin``,
# ``guaranteed``) aracın yazıldığı gün zaten bilinen sınıflardı. Yani araç,
# kampanyanın kanıtladığı kusur sınıfını görmüyordu.
#
# Buradaki kurallar o boşluğu kapatır. İki tasarım kararı ölçüme dayanır:
#
# * Kurallar hem İNGİLİZCE hem TÜRKÇE biçimleri arar: ürünün Türkçe yüzü
#   (``hrma/static/js/i18n*.js``) hiçbir eski kuralın kapsamında değildi.
# * ``heritage`` ("Ariane 5 heritage" künyesi) için kural YAZILMADI:
#   ölçüldü, ağaçta 17 isabet üretiyor ve bunların büyük çoğunluğu meşru
#   malzeme/motor mirası atfı — kural sinyalden çok gürültü olurdu. Onun
#   yerine künyenin ÖLÇÜLEBİLİR biçimi (``built-in ... table``) arandı.
# --------------------------------------------------------------------------
KUNYE_YALANI: Tuple[Rule, ...] = (
    Rule('accuracy_band', r'accurate\s+to\s+within'
                          r'|accuracy\s+(?:of|to|within)\s*[±+\-]?\s*\d'
                          r'|do[gğ]ruluk\s+band[ıi]',
         'Kazanılmamış doğruluk bandı: bandı ölçen bir kod yolu yok '
         '(fizik raporu: boğazda +%95 sapma ölçüldü).'),
    Rule('experimental_validation',
         r'validated\s+against\s+(?:experimental|test|flight|measured)'
         r'|experimentally\s+(?:verified|validated)'
         r'|deneyle\s+do[gğ]rulan'
         r'|deneysel\s+(?:olarak\s+)?do[gğ]rulan',
         'Deneysel doğrulama künyesi: depoda doğrulama kampanyası koşmuyor.'),
    Rule('cea_validated',
         r'(?:NASA\s+)?CEA\s+(?:validated|verified)'
         r'|CEA\s+[Dd]o[gğ]rulamal[ıi]'
         r'|match\w*\s+(?:NASA\s+)?CEA\s+to\s+within'
         r'|validated\s+(?:with|against)\s+(?:NASA\s+)?CEA'
         r'|CEA\s+ile\s+do[gğ]ruland',
         'CEA uyum künyesi: ölçüldü, HRMA c* fakir karışımda CEA’dan '
         '−%2,8..−%5,9 sapıyor.'),
    Rule('sigma_coverage', r'\d\s*[-\s]?sigma\s+coverage|\d\s*σ\s+kapsam',
         'Sigma kapsama iddiası: fizik raporu bunu VERİ-İMKÂNSIZ ölçtü '
         '(n_eff en iyi 14).'),
    Rule('cfd_verified',
         r'verified\s+by\s+CFD|CFD\s+(?:ile\s+)?do[gğ]ruland'
         r'|mesh\s+independence\s+demonstrated',
         'CFD doğrulama künyesi: yayımlanan kalıntı dondurulmuş operatörün, '
         'CONVERGED rozeti şemayı temsil etmiyor.'),
    Rule('safe_verdict_tr',
         r'tasar[ıi]m\s+g[üu]venlidir|g[üu]venli\s+oldu[gğ]u\s+do[gğ]ruland',
         'Türkçe emniyet hükmü: model emniyet kararı veremez '
         '("safe for operation" kuralının Türkçe kardeşi).'),
    Rule('safe_verdict_en',
         r'design\s+is\s+safe|motor\s+is\s+safe'
         r'|safe\s+for\s+(?:the\s+)?(?:specified|operating|flight)',
         'Emniyet hükmü: "safe for operation" dışındaki kalıpları da kapsar.'),
    Rule('standard_compliant_tr',
         r'standart\w*\s+uygun(?:dur|\s+(?:hesap|y[öo]ntem|tasar[ıi]m|olarak))',
         'Türkçe uygunluk hükmü: hiçbir kod yolu standart uygunluğu '
         'denetlemiyor.'),
    Rule('provenance_label',
         r'_(?:source|basis|method|origin)\W{0,6}'
         r'["\'](?:measured|validated|verified|earned|user_supplied|'
         r'experimental|deneysel)["\']',
         'Künye değeri sayının KAZANILDIĞINI söylüyor; künyenin doğruluğu '
         'ölçülmeden yayımlanamaz (P7 KRİTİK: 0,5 mm kullanıcı cidarı '
         'sessizce 2,0 mm oldu, künye "user_supplied" kaldı).'),
    Rule('builtin_table_claim', r'built[-\s]in\s+\w+\s+table',
         'Kaynak künyesi: değerin gerçekten o tablodan geldiği ölçülmeli '
         '(P7 KRİTİK: n2o4 için 1200 kg/m³ "Ariane 5" künyesi, gerçek 1443).'),

    # ------------------------------------------------------------------
    # ÖH D22 · OH-Z5-08 — ÖLÇÜLEN ÜÇ DESEN BOŞLUĞU.
    #
    # Z5S gece filosu 9 satırlık bir sondayla ölçtü: aracın 25 kuralı bu
    # dokuzun DOKUZUNU birden kaçırıyordu (once.json::OH-Z5-08, yakalanan=0),
    # negatif korpusta ise yanlış isabet yoktu. Üç sınıf:
    #
    #  1. TÜRKÇE EDİLGEN KİP. Var olan kurallar Türkçe'yi yalnız ETKEN/sıfat
    #     biçimlerinde arıyordu ('deneyle doğrulanan', 'CEA ile doğrulandı').
    #     Ürünün Türkçe yüzünde asıl kullanılan kip ise "-mıştır"dır:
    #     'CFD ile doğrulanmıştır' hiçbir kurala takılmıyordu.
    #  2. BİTİŞİK SIFAT. 'verified by CFD' yakalanıyor, 'CFD-verified nozzle'
    #     yakalanmıyordu — aynı iddianın sıfat hâli künyede daha sık geçer.
    #  3. 'complies with <STANDART> standard'. Var olan 'code_compliant'
    #     kuralı yalnız '<STD>-compliant' ve 'compliant with NFPA|OSHA|DOT'
    #     biçimlerini arıyordu; 'complies with' fiili ve ASME/ISO/AIAA
    #     kurumları listede yoktu.
    #
    # Üç desen de ÖLÇÜLDÜ: 9/9 pozitif yakalanıyor, 6 satırlık negatif
    # korpusta 0 yanlış isabet (sonra.json::OH-Z5-08).
    # ------------------------------------------------------------------
    # 'kanıtlanmıştır' BİLEREK DIŞARIDA: ölçüldü, ürünün Türkçe yüzünde
    # tasarım MİRASI anlamında geçiyor ("çarpışmalı enjektör basit ve
    # kanıtlanmıştır" — i18n_pages.js:2162, uçuşta kanıtlanmış tasarım),
    # HRMA'nın kendi sayısına dair bir doğruluk hükmü değil. Kural sinyalden
    # çok gürültü üretirdi ('heritage' kuralının yazılmama gerekçesiyle aynı).
    # KAPSAM BİLEREK DAR: yalnız -mIştIr EDİLGEN KESİN KİPİ. Ölçüldü —
    # yalın geçmiş ("doğrulandı") ağaçta 70 satırda geçiyor ve bunların
    # tamamı mühendislik YORUMU ("bu katsayı ölçümle doğrulandı"), yani
    # geliştiriciye yazılmış bir kayıt; kullanıcıya verilen hüküm değil.
    # Onları da yakalayan geniş desen 72 kayıtsız isabet üretip kapıyı
    # gürültüyle kırmızıya çeviriyordu (once/sonra.json::OH-Z5-08_repo).
    # İddia kipi olan "-mIştIr" ise ürün metninde hüküm gibi okunur.
    Rule('dogrulanmistir_tr',
         r'do[gğ]rulanm[ıi][sş]t[ıi]r|te[yi]it\s+edilmi[sş]tir',
         'Türkçe edilgen doğrulama kipi: "-doğrulanmıştır/kanıtlanmıştır" '
         'kazanılmış bir doğrulama kampanyası ister; depoda koşmuyor.',
         # Olumsuz kip ("doğrulanmamıştır", "doğrulanamamıştır") muaftır.
         allow_if=r'(?i)do[gğ]rulan(?:ma|ama)m[ıi][sş]'),
    Rule('cfd_verified_sifat',
         r'\bCFD[-\s]verified\b|\bCFD[-\s]validated\b'
         r'|\bmesh[-\s]independent\b',
         'Bitişik CFD doğrulama sıfatı: yayımlanan kalıntı dondurulmuş '
         'operatörün; ağdan-bağımsızlık çalışması koşmuyor.'),
    Rule('complies_with_standard',
         r'compl(?:ies|y|ying)\s+with\s+(?:the\s+)?'
         r'(?:NFPA|OSHA|DOT|ASME|ISO|AIAA|NASA|MIL)\b',
         'Standart uygunluğu fiili: hiçbir kod yolu standart uygunluğunu '
         'denetlemiyor ("code_compliant" kuralının fiil hâli).',
         # Uygunluğun DENETLENMEDİĞİNİ söyleyen cümle muaftır.
         allow_if=r'(?i)\b(?:not|never|no)\b[^.]{0,40}\bcompl'),
)

ALL_RULES: Tuple[Rule, ...] = (FORBIDDEN_CLAIMS + WRONG_STANDARD_TITLES
                               + KUNYE_YALANI)
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


class Aklanan(NamedTuple):
    """``allow_if`` muafiyetiyle isabet SAYILMAYAN satır.

    P10B4-03: muafiyetin ne yuttuğu görünmezse, bir iddiayı bekçiden
    kaçırmanın yolu cümleye olumsuzlama sözcüğü koymak kadar ucuz kalır.
    Bu kayıt ``--aklananlar`` ile listelenir; sayısı özet satırında görünür.
    """
    path: str
    line_no: int
    rule_id: str
    matched: str        # ana desenin yakaladığı metin
    muafiyet: str       # allow_if deseninin yakaladığı metin
    line_text: str


def _derle(rules: Tuple[Rule, ...]
           ) -> Dict[str, Tuple[re.Pattern, Optional[re.Pattern]]]:
    """Kural kümesini derler. Varsayılan küme için hazır tablo kullanılır."""
    if rules is ALL_RULES:
        return _COMPILED
    return {rule.rule_id: (re.compile(rule.pattern, re.IGNORECASE),
                           re.compile(rule.allow_if) if rule.allow_if else None)
            for rule in rules}


def _line_hash(text: str) -> str:
    """Satır metninin normalleştirilmiş karması.

    Satır numarası kullanılmaz: dosyanın başına satır eklendiğinde kayıt
    bayatlamasın. Boşluk normalleştirilir ki yeniden girintileme kaydı
    bozmasın; METİN değişirse karma değişir ve isabet yeniden görünür.
    """
    normalised = ' '.join(text.split())
    return hashlib.sha1(normalised.encode('utf-8')).hexdigest()[:12]


def _is_scannable(name: str) -> bool:
    return (name.endswith(SCANNED_SUFFIXES)
            and not name.endswith(SKIPPED_FILE_SUFFIXES))


def _iter_source_files(root: str) -> Iterable[str]:
    """``root`` bir DİZİN ya da tek bir DOSYA olabilir.

    Tek dosya desteği H5-5 ile geldi: kullanıcıya giden belgelerin bir kısmı
    (``README.md``, ``docs/USER_MANUAL.md``) dizin değil tek dosyadır.
    """
    if os.path.isfile(root):
        if _is_scannable(os.path.basename(root)):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIPPED_DIR_NAMES)
        for name in sorted(filenames):
            if not _is_scannable(name):
                continue
            yield os.path.join(dirpath, name)


def scan_file(abs_path: str,
              rules: Optional[Tuple[Rule, ...]] = None,
              aklananlar: Optional[List[Aklanan]] = None) -> List[Finding]:
    """Tek dosyayı tarar.

    ``rules``: varsayılan ``ALL_RULES``. Kural kümesini dışarıdan vermek
    MUTASYON KANITI içindir (P10B4-18): bir kural listeden çıkarıldığında
    bekçinin gerçekten kırmızıya döndüğü, dosyaya dokunmadan gösterilebilir.
    ``aklananlar``: verilirse ``allow_if`` ile aklanan satırlar buraya eklenir.
    """
    rules = ALL_RULES if rules is None else tuple(rules)
    derlenmis = _derle(rules)
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
        for rule in rules:
            pattern, allow = derlenmis[rule.rule_id]
            match = pattern.search(raw)
            if not match:
                continue
            if allow is not None:
                muaf = allow.search(raw)
                if muaf:
                    if aklananlar is not None:
                        aklananlar.append(Aklanan(
                            path=rel, line_no=index, rule_id=rule.rule_id,
                            matched=match.group(0), muafiyet=muaf.group(0),
                            line_text=raw.strip()))
                    continue
            findings.append(Finding(
                path=rel, line_no=index, rule_id=rule.rule_id,
                matched=match.group(0), line_hash=_line_hash(raw),
                line_text=raw.strip()))
    return findings


def scan(root: Optional[str] = None,
         rules: Optional[Tuple[Rule, ...]] = None,
         aklananlar: Optional[List[Aklanan]] = None) -> List[Finding]:
    """Tara.

    ``root`` verilmezse varsayılan hedef kümesi taranır: kaynak ağacı
    (``hrma/``) + kullanıcıya giden belgeler (``USER_FACING_DOC_TARGETS``).
    Tek bir dizin ya da dosya da verilebilir.
    """
    if root is None:
        hedefler = [os.path.join(REPO_ROOT, t) for t in DEFAULT_SCAN_TARGETS]
    else:
        hedefler = [root]

    findings: List[Finding] = []
    gorulen = set()
    for hedef in hedefler:
        if not os.path.exists(hedef):
            continue
        for path in _iter_source_files(hedef):
            gercek = os.path.realpath(path)
            if gercek in gorulen:      # hedefler örtüşürse iki kez sayma
                continue
            gorulen.add(gercek)
            findings.extend(scan_file(path, rules=rules,
                                      aklananlar=aklananlar))
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
    parser.add_argument('--root', default=None,
                        help='tek bir kök dizin/dosya tara (varsayılan: '
                             'hrma/ + kullanıcıya giden belgeler)')
    parser.add_argument('--all', action='store_true',
                        help='kayıttakiler dahil bütün isabetleri göster')
    parser.add_argument('--debt', action='store_true',
                        help='yalnız AÇIK BORÇ kayıtlarını listele')
    parser.add_argument('--emit-baseline', action='store_true',
                        help='mevcut isabetlerden kayıt taslağı bas')
    parser.add_argument('--aklananlar', action='store_true',
                        help='allow_if muafiyetiyle ELENEN satırları listele')
    parser.add_argument('--check', action='store_true',
                        help='KAPI kipi: yalnız özet bas, kayıtsız isabet '
                             'varsa çıkış kodu 1')
    args = parser.parse_args(argv)

    aklananlar: List[Aklanan] = []
    findings = scan(args.root, aklananlar=aklananlar)
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

    if args.aklananlar:
        for a in aklananlar:
            print(f'{a.path}:{a.line_no}  [{a.rule_id}] '
                  f'"{a.matched}" muafiyet="{a.muafiyet}"\n'
                  f'    satır : {a.line_text[:150]}')
        print(f'\nallow_if ile AKLANAN satır: {len(aklananlar)}')
        return 0

    shown = [] if args.check else (
        findings if args.all else unbaselined(findings, baseline))
    for finding in shown:
        print(_format(finding))
        print()

    new_hits = unbaselined(findings, baseline)
    debts = open_debts(baseline)
    if args.root is None:
        kok = ', '.join(DEFAULT_SCAN_TARGETS)
    else:
        kok = os.path.relpath(args.root, REPO_ROOT)
    print(f'Taranan kök : {kok}')
    print(f'Kural sayısı: {len(ALL_RULES)}')
    print(f'Toplam isabet: {len(findings)}  '
          f'(kayıtlı {len(findings) - len(new_hits)}, '
          f'kayıtsız {len(new_hits)}, açık borç {len(debts)}, '
          f'allow_if ile aklanan {len(aklananlar)})')
    if new_hits:
        print('KAPI KIRMIZI: kayıtsız isabet var.')
    return 1 if new_hits else 0


if __name__ == '__main__':
    sys.exit(main())
