"""F2b-2 — sıvı motorun chug bağlaması + eşiğin TEK KAYNAK bekçisi.

İKİ İŞ
------
**1. Eşik tekleştirme.** ΔP/Pc chug tasarım kuralının sayı çifti (0,20/0,15)
depoda DÖRT yerde tanımlıydı ve İKİ ayrı künyeyle savunuluyordu (tasarım
belgesi §1.1-1'in ölçtüğü üçe, F2b-2 taraması bir dördüncüsünü ekledi):

    hrma/analysis/acoustic_modes.py       0.20/0.15   Sutton Böl. 8 + SP-194
    hrma/engines/liquid_rocket_engine.py  0.15/0.20   SP-8089
    hrma/engines/injector_design.py       0.15/0.20   SP-8089
    hrma/analysis/transient_ballistics.py 0.15        SP-8089

Aynı sayının iki künyesi olamaz: künye ya sayının dayanağıdır ya değildir.
Hüküm (kaynağa inilerek, ``CHUG_THRESHOLD_SOURCE`` içinde yazılı): mekanizma
SP-194 Böl. 5-6'dan, sayı bandı tasarım pratiğinden (Sutton Böl. 8) gelir;
SP-8089 bu depoda BELGE olarak doğrulanmıştır (docs/STANDART_ATIFLARI.md,
NTRS 19760023196) ama bandın o belgede SAYFA düzeyinde geçtiği
doğrulanmamıştır — defterin kendi kuralı gereği bandın dayanağı yapılamaz.
Sayı DEĞİŞMEDİ; tanım tekleşti.

**2. Chug bağlaması.** Sıvı motorun oran kuralı (ΔP/Pc ≥ 0,20) artık tek
başına değil: ``hrma.stability.chug``un GERÇEK çevrimi (nötr eğri + baskın
kök) motorun kendi ΔP, L*, c* ve atomizasyon süresiyle koşuyor. Bu iki ölçüt
AYNI SORUYU farklı bilgiyle yanıtlıyor ve bu depoda ÇELİŞTİKLERİ ölçüldü —
o yüzden çelişkinin kendisi bir çıktı alanıdır (``rule_vs_loop``), sessiz
değil.

KAPSAM ETİKETİ ZORUNLU: çevrimin hükmü ``verdict_scope`` olmadan
yayımlanamaz (F2a karar 1 + sıkılaştırma); çıplak "STABLE"i kullanıcı "her
mekanizmaya karşı stabil" okur.
"""

import ast
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.analysis import acoustic_modes                    # noqa: E402
from hrma.analysis import transient_ballistics              # noqa: E402
from hrma.engines import liquid_rocket_engine as lre        # noqa: E402
from hrma.stability import chug as chug_mod                 # noqa: E402
from hrma.engines.liquid_rocket_engine import (             # noqa: E402
    LiquidRocketEngine,
)

TABAN = dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
             fuel_type='rp1', oxidizer_type='lox',
             cooling_type='regenerative', injector_type='impinging')


@pytest.fixture(scope='module')
def taban():
    eng = LiquidRocketEngine(**TABAN)
    return eng, eng.calculate_performance()


@pytest.fixture(scope='module')
def kararlilik(taban):
    return taban[1]['combustion_analysis']['stability_analysis']


@pytest.fixture(scope='module')
def cevrim(kararlilik):
    return kararlilik['chug_loop']


# ===========================================================================
# 1) EŞİK TEK KAYNAK
# ===========================================================================
#: Tanımın TEK sahibi. Diğer her modül buradan ithal eder.
KAYNAK_MODUL = 'hrma/analysis/acoustic_modes.py'

#: Eşiği ADIYLA taşıyan ama F2b-2'de SAHİPLİĞİ bu partide olmayan dosyalar.
#: Bunlar hâlâ kendi sayısını tanımlıyor; kalemleri devredildi. Liste DAR
#: tutulur ve her satırı kod kanıtlıdır. Bir satır kapanırsa (dosya artık
#: ithal ediyorsa) aşağıdaki bekçi KIRMIZI olur ve satırın silinmesini
#: zorlar — muafiyet listesi kendiliğinden çürüyemez.
#:
#: v2.6.27 parti 31: liste BOŞALDI. Tek satırı olan
#: ``hrma/engines/injector_design.py`` (CHUG_DP_PC_MIN /
#: CHUG_DP_PC_RECOMMENDED) artık merkezî tanımın takma adıdır — sayı orada
#: bir daha yazılmıyor. Satırı silmek zorunda kalmamız bu bekçinin ÇALIŞTIĞI
#: anlamına gelir: borç kapandığında muafiyet de düşer.
DEVREDILEN_KOPYALAR = {}

#: ADLI kopya tavanı: ``CHUG`` adını taşıyan ikinci bir sayısal tanım
#: kalmadı (parti 31'de kapandı). Bu sayı 0'dan YÜKSELTİLEMEZ.
ADLI_DEVIR_TAVANI = 0

# ---------------------------------------------------------------------------
# ÖH FAZ B-1 / adım #7 — bekçiyi ADdan DEĞERe çevirme
# ---------------------------------------------------------------------------
# ÖLÇÜLEN KUSUR (P14M2-03/-03b/-04/-04b/-05/-05b, savcı §3.1-7):
# Yukarıdaki bekçi yalnız ``ast.Assign`` düğümlerini ve yalnız adında 'CHUG'
# geçen hedefleri tarıyordu. Bu iki süzgeç birlikte, ölçülen borcun
# TAMAMINI görünmez yapıyordu:
#
#   * ``if self.delta_P_inj < 0.2 * self.P_c:`` — sayı bir ``Compare``
#     operandı, hiçbir ada bağlı değil; ``Assign`` taraması göremez.
#   * ``INJECTOR_DP_FRAC_LIQUID_DEFAULT = 0.20`` — ``Assign`` AMA adında
#     'CHUG' yok; ad süzgeci eler. (H2 §5(c): ayrım adlandırılmış/çıplak
#     değil, "bekçinin desenine uyacak biçimde adlandırılmış"tır.)
#   * ``spec.get('dp_ratio_ox', 0.20)`` — ``Call`` varsayılanı.
#   * ``'dp_ratio_ox': ... else 0.20`` — ``Dict`` değeri.
#
# Sonuç: bekçi ``DEVIR_TAVANI = 0`` ile "borç 0" ilan ediyordu; savcının
# ölçtüğü gerçek borç **12 site / 6 dosya** (``raw/P14/S1-olcum-08.py`` (b)).
# Üç beyan birden yanlıştı (bekçi, tavan ve ürün yorumu).
#
# TAVANIN BİRİMİ DEĞİŞTİ: eski 0, "muaf DOSYA sayısı" idi ve kırık bir
# süzgeçle ölçülmüştü. Yeni tavan ölçülmüş SİTE sayısıdır. Adlı kopya
# tavanı gevşemedi — ``ADLI_DEVIR_TAVANI`` olarak 0'da duruyor.
DEVIR_TAVANI = 0   # ÖH D20 / P4B4-18: 10 -> 9; ÖH D21 / P15B2-07: 9 -> 7;
#                    ÖH D26 / P14M2-05(+b): 7 -> 5 (hibritin İKİ sitesi kapandı);
#                    ÖH D27 / OH-D26-07: 5 -> 0 (bağlam varsayılanları tek kaynağa)

#: Sayı çiftinin ΔP/Pc bağlamında arandığı desen — savcının ölçümüyle AYNI
#: (``S1-olcum-08.py`` (b)), ki sayım birebir yeniden üretilebilsin.
ORAN_BAGLAMI = re.compile(
    r'(?i)dp|delta_p|pressure_drop|p_c|chamber_pressure|inj')

#: ÖLÇÜLEN BORÇ — savcının ölçtüğü 12 site / 6 dosyadan İKİ site ÖH Z5S'te
#: kapandı (28 Ağu 2026): P10-Z5S-A ``hrma/utils/injector_design.py``deki
#: ``delta_P_inj`` sitesini, P10-Z5S-B ``hrma/utils/common_fixes.py``deki
#: ``min_pressure_drop`` sitesini ``acoustic_modes`` tek kaynağına bağladı —
#: kalan borç 10 site / 4 dosya. Her satır ``(dosya, sahip)``; sahip,
#: satır numarasından bağımsız olsun diye AST'den türetilir (atama hedefi,
#: sözlük anahtarı, çağrı anahtarı ya da karşılaştırmanın sol tarafı).
#: Liste ne büyüyebilir (yeni site) ne de çürüyebilir (kapanan site listede
#: kalamaz); ikisi de aşağıdaki bekçiyi KIRMIZI yapar.
# ÖH D20 / P4B4-18 — BORÇ AZALDI (bu bekçinin kendi talimatıyla):
# ``cycle_power_balance.INJECTOR_DP_FRAC_LIQUID_DEFAULT`` artık kendi
# 0,20 literalini yazmıyor, ``acoustic_modes.CHUG_DP_RATIO_RECOMMENDED``
# tanım noktasından okuyor. Kapanan borç defterde tutulamaz (bekçi bunu
# "Defter ÇÜRÜMÜŞ" diye kırmızı yapıyordu); satır silindi, sayım ve tavan
# DÜŞÜRÜLDÜ — gevşetme değil daraltmadır.
#: ÖH D27 · OH-D26-07 — BORÇ KAPANDI (5 -> 0). Ölçüm:
#: ``docs/scofield/raw/OH/D27/sivi/a1/{once,sonra}.json`` ``OH-D26-07``.
#: DÖRT site tanım noktasına BAĞLANDI (sayı değişmedi, ikinci tanım
#: noktaları kalktı):
#:   injector_design.py     dp_ratio_ox / dp_ratio_fuel çağrı varsayılanı
#:                          -> ``CHUG_DP_RATIO_RECOMMENDED`` (0,20)
#:   liquid_rocket_engine   INJECTOR_TYPE_DP_FRACTION_DEFAULT
#:                          -> ``CHUG_DP_RATIO_RECOMMENDED`` (0,20)
#: Kalan İKİ site (cycle_power_balance'ın gaz + ön yakıcı 0,15 ikizi) TEK
#: tanıma indirildi: ``INJECTOR_DP_FRAC_HOT_GAS_BAND_LOW``. O tek tanım
#: chug kuralı DEĞİLDİR (sıcak gaz / ön yakıcı enjeksiyonu; Huzel & Huang
#: NASA SP-125 Böl. 4) ve bu yüzden ``SEMANTIK_DISI`` kaydına gerekçesiyle
#: taşındı — chug bandına bağlamak sayısal bir tesadüfü fizik gibi
#: göstermek olurdu (önceki dalganın ayrımı korunur). Kapanan borç defterde
#: tutulamaz (bekçi bunu "Defter ÇÜRÜMÜŞ" diye kırmızı yapar): küme boşaldı,
#: sayım ve tavan DÜŞÜRÜLDÜ. Gevşetme değil DARALTMADIR — yeni bir site
#: doğarsa bekçi yine kırmızıya döner.
CHUG_ORAN_SITELERI = set()
#: ``pressure_drop_factor`` aynı dosyada İKİ kez (0,15 ve 0,20) yazılıyor —
#: küme tek kayıt tutar, sayım ise site bazındadır. ÖH D20'de sıvı enjektör
#: varsayılanı tanım noktasına bağlandığı için site sayısı 10 -> 9,
#: farklı (dosya, sahip) çifti 9 -> 8 indi.
#: ÖH D21 · P15B2-07: ``calculate_injector_design``in BEŞ satır-içi ΔP/Pc
#: kopyası (0,22 / 0,18 / 0,28 / 0,15 / 0,20) silindi ve oran tek tanım
#: yerinden (``_injector_dp_fraction`` -> ``INJECTOR_TYPE_DP_FRACTION``)
#: okunuyor; ``pressure_drop_factor`` sahibi defterden DÜŞTÜ, site sayısı
#: 9 -> 7, tavan 9 -> 7. Gevşetme değil DARALTMADIR.
#: ÖH D26 · P14M2-05 (+P14M2-05b): hibrit motorun İKİ sitesi kapandı —
#: ``_design_fuel_grain``daki ``delta_P = 0.2 * self.P_c`` çıplak literali
#: ve ``dp_ratio_ox`` yedek dalındaki ``else 0.20`` — ikisi de artık
#: ``acoustic_modes.CHUG_DP_RATIO_RECOMMENDED``dan okuyor (ölçüldü:
#: docs/scofield/raw/OH/D26/hibrit/a1/sonra.json, hibritte çıplak geçiş
#: 3 -> 1 ve kalan tek geçiş ΔP/Pc DEĞİL O/F kayma eşiğidir). Kapanan borç
#: defterde tutulamaz; site sayısı 7 -> 5, tavan 7 -> 5. DARALTMADIR.
#: ÖH D27 · OH-D26-07: 5 -> 0 (dördü tanım noktasına bağlandı, ikisi tek
#: tanıma indirilip gerekçeli muafiyete taşındı).
CHUG_ORAN_SITE_SAYISI = 0

#: MEKANİK olarak desene uyan ama chug ΔP/Pc kuralı OLMAYAN geçişler.
#: Her satırın gerekçesi yazılıdır; gerekçesiz muafiyet yoktur. Bir satır
#: kaybolursa bekçi kırmızı olur ve muafiyetin silinmesini zorlar.
SEMANTIK_DISI = {
    ('hrma/engines/liquid_rocket_engine.py', 'injector_pressure_drop'):
        'kullanıcı override BANDI (0,2 bar - 200 bar) — birim bar, oran değil',
    ('hrma/engines/solid_rocket_engine.py', 'pressure_fraction_default'):
        'katı motorun ateşleme basıncı payı (P_ateş/P_c) — başka mekanizma',
    ('hrma/utils/injector_design.py', 'INJECTOR_PLATE_MIN_LIGAMENT'):
        'plaka ligament kalınlığı alt sınırı [mm] — basınç oranı değil',
    # ÖH D27 · OH-D26-07: SICAK GAZ / ÖN YAKICI enjektör ΔP/Pc alt bandı.
    # Bu sayı chug kuralı DEĞİLDİR: chug bandı SIVI enjeksiyonun besleme
    # kuplajı eşiğidir (acoustic_modes), buradaki oran sıcak gaz
    # enjeksiyonunun boyutlandırma pratiğidir (Huzel & Huang, NASA SP-125,
    # Böl. 4). İkisinin 0,15'te çakışması sayısal tesadüftür ve önceki
    # dalga ayrımı BİLEREK kurmuştur (cycle_power_balance yorumu). Bu
    # dalgada iki takma ad (gaz + ön yakıcı) TEK tanıma indirildi; muaf
    # olan o tek tanım noktasıdır, iki kopya değil.
    ('hrma/engines/cycle_power_balance.py',
     'INJECTOR_DP_FRAC_HOT_GAS_BAND_LOW'):
        'sıcak gaz / ön yakıcı enjektör ΔP/Pc alt bandı (H&H SP-125 Böl. 4) '
        '— chug kararlılık eşiği DEĞİL, ayrı büyüklük',
}


def _sabit_sahibi(dugum, ebeveyn):
    """Bir sayı sabitinin AST'deki SAHİBİ (satır numarasından bağımsız ad).

    ``Assign`` hedefi, ``Dict`` anahtarı, ``Call``in ilk dize argümanı,
    ``keyword`` adı ya da ``Compare``in sol tarafı — hangisi önce gelirse.
    """
    n = dugum
    while n in ebeveyn:
        ust = ebeveyn[n]
        if isinstance(ust, ast.Assign):
            for hedef in ust.targets:
                if isinstance(hedef, ast.Name):
                    return hedef.id
                if isinstance(hedef, ast.Attribute):
                    return hedef.attr
            return None
        if isinstance(ust, ast.Dict):
            for anahtar, deger in zip(ust.keys, ust.values):
                if deger is n and isinstance(anahtar, ast.Constant):
                    return str(anahtar.value)
            return None
        if isinstance(ust, ast.Compare):
            sol = ust.left
            if isinstance(sol, ast.Attribute):
                return sol.attr
            if isinstance(sol, ast.Name):
                return sol.id
            return None
        if isinstance(ust, ast.keyword):
            return ust.arg
        if isinstance(ust, ast.Call):
            for arg in ust.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    return arg.value
            if isinstance(ust.func, ast.Attribute):
                return ust.func.attr
            return None
        n = ust
    return None


def _oran_sitelerini_tara():
    """0,20/0,15 çiftinin ΔP/Pc bağlamındaki TÜM AST geçişleri.

    ``Assign`` ile sınırlı DEĞİL: sabit hangi düğümün içinde durursa dursun
    (``Compare``, ``BinOp``, ``Call``, ``Dict``) bulunur. Kanonik modül
    dışlanır — tanımın sahibi orasıdır.
    """
    hedefler = (0.20, 0.15)
    siteler = []
    for kok, _dizinler, dosyalar in os.walk(os.path.join(REPO_ROOT, 'hrma')):
        if '__pycache__' in kok:
            continue
        for dosya in sorted(dosyalar):
            if not dosya.endswith('.py'):
                continue
            tam = os.path.join(kok, dosya)
            bagil = os.path.relpath(tam, REPO_ROOT).replace(os.sep, '/')
            if bagil == KAYNAK_MODUL:
                continue
            with open(tam, encoding='utf-8') as f:
                kaynak = f.read()
            agac = ast.parse(kaynak, filename=tam)
            satirlar = kaynak.split('\n')
            ebeveyn = {}
            for ust in ast.walk(agac):
                for cocuk in ast.iter_child_nodes(ust):
                    ebeveyn[cocuk] = ust
            for dugum in ast.walk(agac):
                if not isinstance(dugum, ast.Constant):
                    continue
                deger = dugum.value
                if isinstance(deger, bool) or not isinstance(deger, (int, float)):
                    continue
                if not any(abs(deger - h) < 1e-12 for h in hedefler):
                    continue
                satir = satirlar[dugum.lineno - 1]
                if not ORAN_BAGLAMI.search(satir):
                    continue
                sahip = _sabit_sahibi(dugum, ebeveyn)
                siteler.append((bagil, sahip, deger, dugum.lineno,
                                satir.strip()[:96]))
    return siteler


def test_chug_orani_DEGER_duzeyinde_envanterli():
    """ΔP/Pc sayı çiftinin ürün kodundaki her geçişi DEFTERE kayıtlı olmalı.

    Bu, ``test_chug_esigi_tek_kaynak``ın ad süzgecinin GÖREMEDİĞİ katmandır:
    çıplak ``Compare`` operandı, 'CHUG' adını taşımayan sabit, çağrı
    varsayılanı, sözlük değeri. Envanter üç yönde birden kilitlidir:

    * yeni site  -> borç büyüdü, KIRMIZI (deftere yazmadan eklenemez);
    * kapanan site defterde kaldı -> muafiyet çürüdü, KIRMIZI;
    * semantik muafiyet kayboldu  -> gerekçe boşa düştü, KIRMIZI.

    Bekçinin kendisi borcu ONAYLAMAZ; sayar. Tekilleştirme indikçe defter
    satır satır boşalır ve her boşalma bu testi kırarak görünür olur.
    """
    olculen = _oran_sitelerini_tara()
    olculen_ciftler = {(d, s) for d, s, _v, _l, _m in olculen}

    yeni = sorted(olculen_ciftler - CHUG_ORAN_SITELERI - set(SEMANTIK_DISI))
    ayrinti = {(d, s): (l, m) for d, s, _v, l, m in olculen}
    assert not yeni, (
        'ΔP/Pc sayı çifti DEFTERE YAZILMADAN yeni bir yerde doğmuş:\n'
        + '\n'.join(f'  {d}:{ayrinti[(d, s)][0]} [{s}] {ayrinti[(d, s)][1]}'
                    for d, s in yeni)
        + f'\nTek tanım yeri: {KAYNAK_MODUL}. Oradan ithal et; ithal '
          'edemiyorsan siteyi CHUG_ORAN_SITELERI defterine gerekçesiyle yaz.')

    kapanan = sorted(CHUG_ORAN_SITELERI - olculen_ciftler)
    assert not kapanan, (
        f'Defter ÇÜRÜMÜŞ: {kapanan} artık kendi sayısını yazmıyor. '
        'CHUG_ORAN_SITELERI listesinden sil ve CHUG_ORAN_SITE_SAYISI ile '
        'DEVIR_TAVANI değerlerini düşür (borç kapandıktan sonra da durmaz).')

    dusen_muafiyet = sorted(set(SEMANTIK_DISI) - olculen_ciftler)
    assert not dusen_muafiyet, (
        f'Semantik muafiyet boşa düştü: {dusen_muafiyet} artık taranmıyor. '
        'SEMANTIK_DISI listesinden sil.')

    assert len(olculen) - len(SEMANTIK_DISI) == CHUG_ORAN_SITE_SAYISI, (
        f'ölçülen chug ΔP/Pc sitesi {len(olculen) - len(SEMANTIK_DISI)}, '
        f'defter {CHUG_ORAN_SITE_SAYISI} diyor')
    assert CHUG_ORAN_SITE_SAYISI <= DEVIR_TAVANI, (
        'borç tavanı aşıldı — tavanı yükseltmek borcu gizlemektir')


def test_yayimlanan_kunye_TEK_TANIM_diye_yalan_soylemiyor():
    """Kullanıcıya giden künye metni, ölçülen borçla çelişemez.

    İki yönlü kapanır: ya cümle gerçeğe çevrilir, ya da kalan siteler
    tekilleştirilip cümle doğru hâle gelir. İkisi de bu satırı yeşile
    döndürür — yani bekçi çözümü dayatmaz, YALANI yasaklar.

    ÖH D26 / OH-B1-03 — BORÇ İMİ KALKTI. Ölçülen (once.json, K2): yayımlanan
    ``_chug_report()['threshold_source']`` alanı "This pair (0.20 / 0.15) is
    the ONLY numeric definition of the chug design rule in HRMA" diyordu,
    ürün kodundaki borç ise 7 site / 4 dosyaydı (hepsi ``hrma/engines/``
    altında: sıvı/katı/hibrit kulvarlarının sahası, akustik modülünden
    tekilleştirilemez). Münhasırlık iddiası düzyazıdan SÖKÜLDÜ; yerine
    doğrulanabilir olan yayımlandı — tanımın SAHİBİ (modül + sembol adları)
    ve münhasır OLMADIĞI. Bekçi artık iki katmanı birden kilitler: düzyazı
    yeniden münhasırlık iddia edemez, yapısal alan da borç dururken
    ``exclusive_in_repository=True`` diyemez.
    """
    metin = acoustic_modes.CHUG_THRESHOLD_SOURCE
    tekil_iddiasi = 'ONLY numeric definition' in metin
    borc = len(_oran_sitelerini_tara()) - len(SEMANTIK_DISI)
    assert not (tekil_iddiasi and borc), (
        f'yayımlanan künye "TEK sayısal tanım" diyor ama ürün kodunda '
        f'{borc} site daha var. Ya cümle düzeltilir ya borç kapatılır.')

    # YAPISAL ayak: iddia artık düzyazıya değil alana bağlı, alan da borca.
    chug = acoustic_modes.AcousticModeAnalyzer().analyze(
        chamber_temperature=3000.0, gamma=1.2, gas_constant=360.0,
        chamber_diameter=0.10, chamber_length=0.40,
        injector_dp_ratio=0.20)['stability_report']['chug']
    tanim = chug['threshold_definition_point']
    assert tanim['module'] == 'hrma.analysis.acoustic_modes'
    for sembol in tanim['symbols']:
        assert hasattr(acoustic_modes, sembol), sembol
    assert not (tanim['exclusive_in_repository'] and borc), (
        f'yayımlanan tanım-noktası kaydı münhasırlık iddia ediyor ama ürün '
        f'kodunda {borc} site daha var.')


def test_chug_esigi_tek_kaynak():
    """Eşik çifti YALNIZ merkezî modülde SAYISAL olarak tanımlı olsun.

    Tarama AST üstündendir: docstring/yorum tarihçeyi anlatabilir (anlatmak
    ZORUNDADIR), ama kodda sayı olarak ikinci kez doğamaz.

    KAPSAM BEYANI (P14M2-03/-04/-05 ölçümü): bu bekçi yalnız ``ast.Assign``
    düğümlerini ve yalnız adında 'CHUG' geçen hedefleri görür — yani
    "eşiğin ADIYLA yeniden doğması"nı yasaklar. Sayının ADSIZ ya da başka
    adla doğmasını GÖREMEZ; o katman
    ``test_chug_orani_DEGER_duzeyinde_envanterli`` ile ölçülür. Bu iki
    bekçi birbirinin yerine geçmez.
    """
    hedefler = (0.20, 0.15)
    ihlaller = []
    for kok, _dizinler, dosyalar in os.walk(os.path.join(REPO_ROOT, 'hrma')):
        if '__pycache__' in kok:
            continue
        for dosya in dosyalar:
            if not dosya.endswith('.py'):
                continue
            tam = os.path.join(kok, dosya)
            bagil = os.path.relpath(tam, REPO_ROOT)
            if bagil.replace(os.sep, '/') == KAYNAK_MODUL:
                continue
            with open(tam, encoding='utf-8') as f:
                agac = ast.parse(f.read(), filename=tam)
            for dugum in ast.walk(agac):
                if not isinstance(dugum, ast.Assign):
                    continue
                adlar = [h.id for h in dugum.targets
                         if isinstance(h, ast.Name)]
                if not any('CHUG' in ad and ('DP' in ad or 'RATIO' in ad)
                           for ad in adlar):
                    continue
                if not isinstance(dugum.value, ast.Constant):
                    continue          # takma ad (Name) -> tek kaynak korunur
                if any(abs(dugum.value.value - h) < 1e-12 for h in hedefler):
                    ihlaller.append(
                        (bagil.replace(os.sep, '/'), adlar[0],
                         dugum.value.value, dugum.lineno))

    bilinen = {(yol, ad) for yol, kayit in DEVREDILEN_KOPYALAR.items()
               for ad in kayit['adlar']}
    yeni = [i for i in ihlaller if (i[0], i[1]) not in bilinen]
    assert not yeni, (
        'Chug eşiği YENİDEN kopyalanmış (tek kaynak kuralı):\n'
        + '\n'.join(f'  {y}:{s} {a} = {d}' for y, a, d, s in yeni)
        + f'\nTek tanım yeri: {KAYNAK_MODUL}. Oradan ithal et.')

    kapananlar = bilinen - {(i[0], i[1]) for i in ihlaller}
    assert not kapananlar, (
        f'Devir listesi ÇÜRÜMÜŞ: {sorted(kapananlar)} artık kendi sayısını '
        'tanımlamıyor. DEVREDILEN_KOPYALAR listesinden sil (muafiyet, borç '
        'kapandıktan sonra da durmaz).')
    assert len(DEVREDILEN_KOPYALAR) <= ADLI_DEVIR_TAVANI


def test_esik_kullanicilari_ayni_NESNEYI_okuyor():
    """Takma adlar aynı nesneye bağlı olmalı — "aynı değer" YETMEZ.

    Değer eşitliği, iki ayrı sabitin bugün aynı sayıyı taşımasıyla da
    sağlanır; kusur tam olarak buydu. Kimlik (``is``) ise ancak tek kaynaktan
    ithal edilmişse sağlanır.
    """
    kaynak_min = acoustic_modes.CHUG_DP_RATIO_MINIMUM
    kaynak_rec = acoustic_modes.CHUG_DP_RATIO_RECOMMENDED
    assert lre.CHUG_DP_PC_MIN_LIQUID is kaynak_min
    assert lre.CHUG_DP_PC_RECOMMENDED_LIQUID is kaynak_rec
    assert transient_ballistics.DP_RATIO_WARN is kaynak_min
    assert chug_mod.CHUG_DP_RATIO_MINIMUM is kaynak_min
    assert chug_mod.CHUG_DP_RATIO_RECOMMENDED is kaynak_rec
    # Sayılar DEĞİŞMEDİ (göç sessiz sayı değişikliği değildir).
    assert kaynak_min == 0.15 and kaynak_rec == 0.20


def test_kunye_hukmu_tek_metinde_ve_beyanli():
    """Künye çelişkisi metinde ADIYLA çözülmüş olmalı."""
    metin = acoustic_modes.CHUG_THRESHOLD_SOURCE
    assert 'Sutton' in metin and 'SP-194' in metin
    assert 'SP-8089' in metin, (
        'İkinci künye yok sayılamaz: aynı bandı savunan diğer atıf ADIYLA '
        'anılmalı ve neden dayanak YAPILMADIĞI yazılmalı.')
    assert 'NOT been verified' in metin
    # Künye, çıktının içinde kullanıcıya da ulaşmalı.
    assert acoustic_modes.AcousticModeAnalyzer()._chug_report(
        None, None, 0.2)['threshold_source'] is metin


def test_model_gecerlilik_tabani_chug_esigiyle_karistirilmadi():
    """0,05 bir chug eşiği DEĞİL, çözücü durdurma korumasıdır.

    Aynı aileye sokulup tek kaynağa taşınsaydı, bir gün "chug eşiği 0,05'e
    düştü" diye okunurdu. İki kavram ayrı kalır ve ayrı beyan edilir.
    """
    assert transient_ballistics.DP_RATIO_UNSTABLE == 0.05
    assert transient_ballistics.DP_RATIO_UNSTABLE is not \
        acoustic_modes.CHUG_DP_RATIO_MINIMUM
    yol = os.path.join(REPO_ROOT, 'hrma', 'analysis',
                       'transient_ballistics.py')
    with open(yol, encoding='utf-8') as f:
        govde = f.read()
    assert 'ÇÖZÜCÜ GEÇERLİLİK TABANI' in govde


def test_i18n_bagli_uyari_metni_korundu():
    """Uyarı METNİ ile i18n deseni BİRLİKTE tutar.

    ÖH D18 (P2B4-08) — bu bekçi eskiden metnin ``(SP-8089)`` künyesini
    HARFİ HARFİNE arıyordu. Oysa deponun eşiği tanımlayan tek kaynağı
    (``acoustic_modes.CHUG_THRESHOLD_SOURCE``) o atfı AÇIKÇA geri çekiyor:
    "the band has NOT been verified page-by-page inside it in this
    repository, so the threshold is not attributed to it". Yani bekçi geri
    çekilmiş bir künyeyi sözleşme yapıyordu ve düzeltmeyi kırmızıya
    çeviriyordu (ÖK-05 'kusuru koruyan bekçi' deseni).

    Sınanan şey değişmedi: uyarı metni ile ``i18n_charts.js`` deseni
    birlikte tutmalıdır. Artık künye TEK kaynaktan okunur ve desen künyeyi
    YAKALAR, ona çivilenmez — sözleşme metnin ŞEKLİDİR, künyenin kendisi
    değil.
    """
    from hrma.analysis.acoustic_modes import CHUG_THRESHOLD_CITATION
    yol = os.path.join(REPO_ROOT, 'hrma', 'analysis',
                       'transient_ballistics.py')
    with open(yol, encoding='utf-8') as f:
        govde = f.read()
    assert 'chugging risk ({CHUG_THRESHOLD_CITATION})' in govde, (
        'künye tek kaynaktan gelmiyor')
    assert 'chugging risk (SP-8089)' not in govde, (
        'geri çekilmiş SP-8089 atfı metne geri döndü')
    js = os.path.join(REPO_ROOT, 'hrma', 'static', 'js', 'i18n_charts.js')
    with open(js, encoding='utf-8') as f:
        js_govde = f.read()
    m = re.search(r'\[/(\^t=.*?chugging risk[^/]*)/,', js_govde)
    assert m, 'i18n chug deseni bulunamadı'
    desen = m.group(1).replace('\\/', '/')
    ornek = ('t=3.10s: ΔP/Pc=0.11 < 0.15 — chugging risk (%s)'
             % CHUG_THRESHOLD_CITATION)
    assert re.match(desen, ornek), (
        'i18n deseni çözücünün ürettiği cümleyi artık yakalamıyor: '
        '%r ⟷ %r' % (desen, ornek))


# ===========================================================================
# 2) CHUG BAĞLAMASI
# ===========================================================================
def test_cevrim_gercekten_kosuyor(cevrim):
    """Sıvı motor artık oran kuralı DEĞİL, çevrimi de yayımlıyor."""
    assert cevrim['status'] == 'modelled'
    assert cevrim['model'] == 'lumped_capacitance_resistance_delay'
    for anahtar in ('dp_ratio_j', 'tau_s', 'tau_c_s', 'tau_over_tau_c',
                    'neutral_delay_s', 'neutral_tau_over_tau_c',
                    'growth_rate_1_s', 'frequency_hz'):
        assert anahtar in cevrim, anahtar


def test_cevrim_girdileri_motorun_KENDI_cozumunden(taban, cevrim, kararlilik):
    """J, τ ve τ_c uydurma değil: üçü de bu koşunun yayımlanan sayıları."""
    eng, sonuc = taban
    comb = sonuc['combustion_analysis']['combustion_analysis']
    # J = yayımlanan ΔP/Pc
    assert cevrim['dp_ratio_j'] == kararlilik['injector_dp_over_pc']
    # τ = yayımlanan atomizasyon süresi (ms -> s)
    assert cevrim['tau_s'] == pytest.approx(comb['mixing_time'] / 1000.0,
                                            rel=1e-12)
    # τ_c = L*/(c*Γ²), L* ve c* motorun kendi değerleri
    #
    # ÖH D17 · P6B4-01 — ÇEVRİLEN BEKÇİ. Bu satır
    # ``eng._l_star()`` (İSTENEN L*) yazıyordu ve tam da kalemin kusurunu
    # KİLİTLİYORDU: chug çevrimi çizilmeyen bir haznenin L*'ını tüketiyor,
    # bekçi de "doğru" diyordu. Ölçüldü (raw/OH/D17/sivi/a1/once.json):
    # 250 kN'da çizilen L* 3,4720 m ⟷ istenen 1,2 m, 1 MN'da 5,7428 ⟷ 1,2;
    # τ_c üç itkide bit-aynı 0,001596822 s çıkıyordu. İddia ÇİZİLEN L*'a
    # çevrildi (``_chamber_volume_split()`` altıncı dönüşü, aynı sayı
    # ``cooling_system.l_star`` olarak yayımlanır). Bu fikstür 10 kN
    # olduğu için çizilen = istenen; iddia gevşemedi, DOĞRU büyüklüğe
    # bağlandı ve büyük motorlarda artık gerçekten kilitliyor.
    tc = cevrim['chamber_time_constant']
    _l_star_cizilen = eng._chamber_volume_split()[5]
    assert tc['l_star_m'] == pytest.approx(_l_star_cizilen, rel=1e-12)
    assert tc['c_star_m_s'] == pytest.approx(float(eng.c_star), rel=1e-12)
    assert cevrim['tau_c_s'] == tc['tau_c_s']


def test_tau_c_ikinci_yolla_capraz_ve_fark_BEYANLI(cevrim, taban):
    """τ_c ile kalış süresi aynı büyüklüktür; kalan fark yayımlanmalı.

    ρV/ṁ = L*/(c*Γ²) özdeşliği ancak ṁ = P_c·A_t/c* tam sağlanırsa geçerli.
    Sıvı zincirinde ṁ itki/Isp yolundan geliyor; ÖLÇÜLEN artık %2,5. Bunu
    gizlemek "aynı yanıtta iki tanım" kusurudur — çıktıda duruyor.
    """
    capraz = cevrim['tau_c_vs_residence_time']
    comb = taban[1]['combustion_analysis']['combustion_analysis']
    assert capraz['residence_time_s'] == pytest.approx(
        comb['residence_time'] / 1000.0, rel=1e-12)
    assert capraz['ratio'] == pytest.approx(
        capraz['residence_time_s'] / capraz['tau_c_s'], rel=1e-12)
    # 17 Ağu 2026 ölçümü: 1,0255. Bant, kusur büyürse haber versin diye dar.
    assert 1.0 <= capraz['ratio'] <= 1.10, capraz['ratio']
    assert 'mdot' in capraz['interpretation']


def test_hukum_KAPSAM_ETIKETSIZ_yayimlanamaz(cevrim):
    """F2a karar 1 sıkılaştırması: çıplak hüküm yasak."""
    assert cevrim['verdict'] in ('stable', 'unstable', 'marginal')
    kapsam = cevrim['verdict_scope']
    assert kapsam and 'chug' in kapsam
    assert 'modeled mechanism only' in kapsam
    assert cevrim['verdict_basis']
    # Motorun GENEL hükmü hâlâ verilmiyor.
    blok_verdict = cevrim['verdict']
    assert blok_verdict != 'unknown'


def test_genel_hukum_hala_verilmiyor(kararlilik):
    """Chug hükmü, motorun genel kararlılık hükmüne TERFİ etmemeli."""
    assert kararlilik['stability_rating'] == 'unknown'
    assert kararlilik['acoustic_analysis'] == 'not_modelled'
    assert 'scope-labelled' in kararlilik['stability_rating_basis']


def test_oran_kurali_ile_cevrimin_iliskisi_OLCULU(cevrim, kararlilik):
    """Çelişki sessiz kalamaz: ilişki adıyla yayımlanır.

    ÖLÇÜLEN (17 Ağu 2026, taban motor): oran kuralı 'chug_margin_ok'
    (J = 0,22 ≥ 0,20) derken çevrim 'unstable' diyor — çünkü kural τ'yu ve
    τ_c'yi HİÇ görmüyor. Bu depoda üç örnek motorun ÜÇÜNDE de çelişki çıktı.
    """
    iliski = cevrim['rule_vs_loop']
    assert iliski['ratio_rule_rating'] == kararlilik['chug_rating']
    assert iliski['loop_verdict'] == cevrim['verdict']
    assert iliski['agreement'] in ('agree', 'disagree')
    beklenen = ('agree'
                if (iliski['ratio_rule_rating'] in ('chug_margin_ok',
                                                    'chug_margin_marginal'))
                == (iliski['loop_verdict'] == 'stable') else 'disagree')
    assert iliski['agreement'] == beklenen
    assert 'blind to the sensitive time lag' in iliski['interpretation']
    # τ'nun yönü de beyanlı olmalı (muhafazakâr taraf hangisi).
    assert 'conservative' in cevrim['tau_source'].lower()


def test_klasik_kural_capraz_kontrolu_cikitida(cevrim):
    """Kuralın nötr eğri üstünde NEREYE düştüğü ölçülü olarak yayımlanır."""
    capraz = cevrim['classical_rule_cross_check']
    assert capraz['rule_min_ratio'] == acoustic_modes.CHUG_DP_RATIO_MINIMUM
    assert capraz['rule_recommended_ratio'] == \
        acoustic_modes.CHUG_DP_RATIO_RECOMMENDED
    # J = 0,20'de nötr τ/τ_c = 0,865152... (tasarım belgesi §3.2 çapası)
    assert capraz['model_neutral_tau_over_tau_c_at_rule_recommended'] == \
        pytest.approx(0.8651517, rel=1e-6)


# ===========================================================================
# 3) BESLEME HATTI KAPISI (karar 5) — forma alan EKLENMEDİ
# ===========================================================================
def test_hat_verilmeyince_ataletsiz_ve_BEYANLI(cevrim):
    """Varsayılan koşuda ataletsiz model + açık beyan (uydurma hat yok)."""
    assert cevrim['inertance_included'] is False
    assert cevrim['tau_f_s'] is None
    assert cevrim['feed_line'] is None
    assert 'no layout default is assumed' in cevrim['inertance_basis']
    assert 'inertance-free feed line' in cevrim['verdict_scope']


def test_yerlesim_varsayimi_motora_KOPYALANMADI():
    """2,5 m'lik hat varsayımı chug yoluna sızmamalı."""
    yol = os.path.join(REPO_ROOT, 'hrma', 'engines', 'liquid_rocket_engine.py')
    with open(yol, encoding='utf-8') as f:
        agac = ast.parse(f.read(), filename=yol)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.FunctionDef) and dugum.name in (
                '_feed_line_inertance_inputs', '_chug_loop_block'):
            for alt in ast.walk(dugum):
                if isinstance(alt, ast.Constant) and isinstance(
                        alt.value, float) and abs(alt.value - 2.5) < 1e-9:
                    pytest.fail(
                        f'{dugum.name}:{alt.lineno} yerleşim varsayımı '
                        f'(2,5 m) kopyalanmış — karar 5 ihlali.')


def test_hat_verilince_ataletli_forma_geciyor(cevrim):
    """Çözücü tarafı HAZIR: gerçek hat verilirse ikinci mertebe model koşar.

    Forma alan EKLENMEDİ (karar 5, UI eş zamanlı değil); kapı override
    yolundan ölçülür. Aynı motorda τ_f > 0 olunca model adı ve kapsam
    etiketi DEĞİŞMELİ — yoksa "ataletli koştu" iddiası ekrandan okunamaz.
    """
    eng = LiquidRocketEngine(overrides={'feed_line_length_m': 1.5,
                                        'feed_line_diameter_mm': 12.0},
                             **TABAN)
    blok = eng.calculate_performance()[
        'combustion_analysis']['stability_analysis']['chug_loop']
    assert blok['inertance_included'] is True
    assert blok['model'] == 'lumped_inertance_capacitance_resistance_delay'
    assert blok['tau_f_s'] > 0
    assert blok['feed_line']['line_length_m'] == 1.5
    assert blok['feed_line']['line_area_m2'] == pytest.approx(
        3.141592653589793 * 0.012 ** 2 / 4.0, rel=1e-12)
    assert 'inertance-free' not in blok['verdict_scope']
    # Ataletsiz koşunun τ_c'si değişmemeli: hat yalnız τ_f getirir.
    assert blok['tau_c_s'] == pytest.approx(cevrim['tau_c_s'], rel=1e-12)


def test_eksik_girdi_uydurma_uretmez():
    """τ çözülemezse hüküm YOK, gerekçe VAR (uydurma yasağı)."""
    eng = LiquidRocketEngine(**TABAN)
    blok = eng._chug_loop_block(dp_pc=0.2, mixing_time=None, l_star_m=1.2,
                                rule_rating='chug_margin_ok')
    assert blok['status'] == 'NOT_EVALUATED'
    assert any('tau' in m for m in blok['missing_inputs'])
    assert 'verdict' not in blok
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in blok.values())
