"""ÖH D37 · A2-3 · kulvar hibrit (kart A2-3) bekçileri — 25 Eylül 2026.

Kanıt: docs/scofield/raw/OH/A2/hibrit/a1/ (once/, sonra/, mutasyon.md,
rapor.md, patch/). Bu dosya docs kanıtını OKUMAZ: bütün girdiler ürün
kaynağından (AST / metin), ürün modüllerinden ya da uçun kendisinden (Flask
test istemcisi, Ornek-H1) gelir; yayın dalında da koşar.

Kalemler ve bekçileri
---------------------
F-10 (= CW-A5, YB-03)  Orifis çapı bandı TEK KAYNAK: ``hrma.constants.
          ORIFICE_D_BAND_MM`` (0,5-2,5 mm) + künye ``ORIFICE_D_BAND_SOURCE``
          (Sutton & Biblarz 9. bs. §8.9 s. 337; Mishra 2017 Böl. 10 s. 348).
          T1 kimlik (engines takma adı ``is``, DEFAULT_CONSTRAINTS öğeleri
          demetin KENDİ öğeleri, utils imzası None + gövde bant, app.py
          tablosu — yama), T2 künye bandın kendisini söyler (denetçi-3
          Ş-1'den beri ``tests/test_sabit_tek_kaynak.py``de), T3 künye adı
          tüketen dosyalarda anılır, T4 literal 0,3/2,0/3,0 KALMADI (AST;
          denetçi Ş4'ten beri ``.get(<bant adı>, <yedek>)`` yedeğinde
          HERHANGİ bir çıplak sayı da ihlal; denetçi-2 Ş-E'den beri
          bant adına bağlı ``or <sayı>`` ve koşullu ifade yedeği de),
          T5 Ornek-H1 kanon alanı bant içinde uyarısız + sabit n yolunda
          uyarı bandın sayısını taşır, T6 plaka SF delik sayısından
          BAĞIMSIZ (Lean ``ligament_n_invariant`` kilidi), T7 bekçi kapsamı
          (adlar BEKCI dosyasının gövdesinde; kulvar dosyası listede YOK),
          T8 i18n bant uyarısı parametreli kaldı, T9 DAVRANIŞ (denetçi-2
          Ş-C: çarpışmalı ``/calculate`` çift seçimi bandın üst kenarından
          + element_pairs = 1 karşılanır — app yaması koşullu; devre
          çözücüsü küçük alanda n = max(1, ⌊4A/(π·d_min²)⌋), d_min banttan),
          YB-03 ölü bant yok,
          KANON yolda "sayı değişmedi" çapası (Berke önce/sonra tablosu;
          D35 çapası yenilenmedi — kanon DIŞI yollarda, çarpışmalı ve
          kullanıcı ΔP'li duş başlığında, sayı DEĞİŞİR: denetçi Ş1,
          docs/scofield/raw/OH/A2/hibrit/a1/sart/once_sonra_s1.json; kanon
          yolda da yalnız A ≥ π·(0,5 mm)²/4 ≈ 0,196 mm² iken değişmez —
          devre sert kısıtı 0,3/3,0 → 0,5/2,5: denetçi-2 Ş-B, sart3/).
F-09 (= OH-D31-09)  ``chug_loop.tau_c_vs_residence_time.residual_decomposition``
          yayımlanır; kapanış explained·(1 + unexplained/100) = ratio
          (Lean ``residual_decomposition_closes``); terimler yanıtın KENDİ
          yapraklarından bağımsız yolla yeniden üretilir; C_D terimiyle
          açıklanamayan ≈ 0 (C_D kararı kilidi); eski "exactly 1/C_D"
          iddiası metinden kalktı; girdi eksikse alan konmaz (fail-closed).
K-8  (CAD B1 H07)  Hibrit ``grain_design`` uydurma ``number_of_segments``
          yayımlamaz; ``segmentation: not_modelled`` + gerekçe; STEP
          segment planı None (tek parça + künye).
YB-04 (OH-ON-01 §6)  ``injector_design.feed_pressure_bar/_source/_basis``:
          P₁ = Pc + ΔP, N₂O'da P_sat(T_tank); ``tank_pressure`` alanının
          devreye girmediği adıyla beyanlı.
Lean/registry  Dört yeni teorem dosyada, ``sorry`` yok; registry çapaları
          Python satırlarında gerçekten duruyor.

``hrma/app.py`` bu kulvarda PATCH ile değişir (patch/F10_app_bant.patch,
birleşmede ana model uygular). app.py'ye bağlı iddialar yama uygulanmamışken
``xfail(strict=True)`` ile KIRMIZI beklenir; yama uygulanınca koşul düşer ve
iddialar normal test olur — bütünleştiricinin elle bir şey silmesi gerekmez.
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import sys
import warnings

import numpy as np
import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / 'tools'))
import sabit_envanteri  # noqa: E402

os.environ.setdefault('HRMA_HEADLESS', '1')

CONSTANTS_PY = KOK / 'hrma' / 'constants.py'
ENGINES_INJ = KOK / 'hrma' / 'engines' / 'injector_design.py'
UTILS_INJ = KOK / 'hrma' / 'utils' / 'injector_design.py'
APP_PY = KOK / 'hrma' / 'app.py'
VALIDATION_PY = KOK / 'hrma' / 'validation' / 'validation_system.py'
HYBRID_PY = KOK / 'hrma' / 'engines' / 'hybrid_rocket_engine.py'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
LEAN = KOK / 'formal' / 'LeanLab' / 'HRMAInjector.lean'
REGISTRY = KOK / 'formal' / 'registry.json'

#: Ornek-H1 (D35 ``ORNEK_H1``; A1a hibrit-beyan ve A2 ``olcum.py`` ile aynı).
ORNEK_H1 = {
    'thrust': 1000.0, 'burn_time': 10.0, 'chamber_pressure': 20.0,
    'of_ratio': 7.5, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'tank_pressure': 50.0, 'injector_type': 'showerhead',
    'injector_material': 'stainless_steel', 'chamber_material': 'steel_304',
    'wall_thickness': 5.0, 'safety_factor': 4.0,
    'pressure_drop': 4.0,
    # V3.0.5 T-ÇAPA-C1 — c* VERİMİ AÇIKÇA İDEAL (%100). V301/H-PANEL
    # (74b55500a, 26 Eki; Berke onaylı yayımlanan sayı değişimi) hibrit
    # formuna 'combustion_efficiency' girdisi ve N2O/HTPB için kaynaklı
    # 0,89 varsayılanı getirdi; bu dosyanın kenar vakaları (H20/H22/H24
    # yakınlık penceresi, I50 e3/e4 kırpılmış plan, f10/t9 çapaları) ideal
    # c* motorunun debisiyle KURULMUŞ enjektör sınırlarıdır ve η=0,89 ile
    # pencereden çıkıyordu (ölçüldü, e038d626f: H24 delik 0,5743 → 0,6087
    # mm, f10 SF 2,1245 → 2,2506). Vakaların konusu enjektör mantığıdır,
    # verim değil; η=%100 gönderildiğinde dosyanın 168 düğümünden 167'si
    # H-PANEL öncesi çapalarıyla BİREBİR yeşil (kalan 1: Lean bağı, ayrı
    # kök). Verimin kendisi tests/test_v301_hibrit_panel.py'de kilitli.
    'combustion_efficiency': 100.0,
}

#: V301/E2 (Ayberk tur 1) — ÇARPIŞMALI EKRAN BLOĞU ARTIK DEVREYİ TÜKETİR.
#: ``/calculate`` çarpışmalı yolda plaka bloğu eskiden kendi tek fazlı (SPI)
#: alanıyla çift planı kurup bandına kırpıyordu; devre (Dyer NHNE) başka bir
#: plan yayımlıyordu (ölçüldü: docs/scofield/raw/OH/V301/ayberk1/
#: enjektor-genel/once.json — 2 çift × Ø1,541 mm ⟷ 3 delik × Ø2,111 mm).
#: Artık plan devrenindir (``design_like_doublet``). Bu dosyanın ölçtüğü
#: plaka KIRPMA yolu yalnız ΔP AÇIK ezmesinde koşar (ALAN ve ΔP AYRILMAZ);
#: o yolu ESKİ sayılarla ölçmek için ezme devrenin kendi ΔP'siyle yapılır
#: (Ornek-H1: P_sat(293,15 K) − Pc = 30,5433585 bar, aşağıdaki çapa testiyle
#: aynı sayı). Beklentiler değişmedi; değişen yalnız yolun seçimidir.
H1_DEVRE_DP_BAR = 30.5433585
KANON_DISI_DP = {'pressure_drop': H1_DEVRE_DP_BAR,
                 'pressure_drop_source': 'user'}

#: Ornek-H1 kanon planının toplam orifis alanı [m²] (yanıt: 10,5053 mm²;
#: elle 3·π·2,1115²/4 = 10,5049 mm²). Bant testi bu alanla ürünün KENDİ
#: planlayıcısını çağırır.
H1_ALAN_M2 = 10.505333967843919e-6

#: Bantla ilişkili ESKİ literaller — hiçbiri artık bant anahtar/argümanına
#: bağlı olarak kaynakta duramaz (0,3 alt; 2,0 ve 3,0 üst).
ESKI_BANT_LITERALLERI = {0.3, 2.0, 3.0}
BANT_ADLARI = {'hole_diameter_min', 'hole_diameter_max',
               'd_min_mm', 'd_max_mm'}


def _oku(yol: pathlib.Path) -> str:
    return yol.read_text(encoding='utf-8')


def _app_yamasi_uygulanmadi() -> bool:
    """app.py hâlâ eski literal tabloyu mu taşıyor? (yama bekçisi koşulu)"""
    return "'hole_diameter_min': (0.3, 'mm', 'not_supplied')" in _oku(APP_PY)


app_yamasi_bekleniyor = pytest.mark.xfail(
    condition=_app_yamasi_uygulanmadi(), strict=True,
    reason='hrma/app.py bu kulvarda PATCH ile değişir '
           '(docs/scofield/raw/OH/A2/hibrit/a1/patch/F10_app_bant.patch); '
           'yama uygulanmadan bu iddia kırmızıdır')


# ===========================================================================
# Fikstürler
# ===========================================================================
@pytest.fixture(scope='module')
def taban():
    """Motor düzeyi taban koşusu (test_stability_hibrit_chug ile aynı nokta)."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=2.5,
                                   chamber_pressure=20.0,
                                   track_performance=False)
        sonuc = motor.calculate()
    return motor, sonuc


@pytest.fixture(scope='module')
def h1():
    """Ornek-H1 ``/calculate`` yanıtı (tek koşu, modül başına)."""
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=dict(ORNEK_H1))
    assert cevap.status_code == 200, cevap.get_json()
    return cevap.get_json()


# ===========================================================================
# F-10 · T1 — tek tanım noktası, KİMLİK
# ===========================================================================
def test_f10_t1_engines_takma_adi_ve_kisit_sozlugu_kimlik():
    from hrma import constants as c
    from hrma.engines import injector_design as eid
    assert isinstance(c.ORIFICE_D_BAND_MM, tuple) and len(c.ORIFICE_D_BAND_MM) == 2
    alt, ust = c.ORIFICE_D_BAND_MM
    assert 0 < alt < ust
    assert eid.ORIFICE_D_PREF_MM is c.ORIFICE_D_BAND_MM, (
        'engines takma adı değer eşitliği değil KİMLİK olmalı')
    assert eid.DEFAULT_CONSTRAINTS['d_min_mm'] is c.ORIFICE_D_BAND_MM[0]
    assert eid.DEFAULT_CONSTRAINTS['d_max_mm'] is c.ORIFICE_D_BAND_MM[1]


def _imza_varsayilanlari(kaynak: str, sinif: str, yontem: str) -> dict:
    """``sinif.yontem`` imzasındaki (ad → varsayılan AST düğümü) eşlemesi."""
    agac = ast.parse(kaynak)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.ClassDef) and dugum.name == sinif:
            for uye in dugum.body:
                if isinstance(uye, ast.FunctionDef) and uye.name == yontem:
                    args = uye.args
                    adlar = [a.arg for a in args.args]
                    vars_ = args.defaults
                    eslem = dict(zip(adlar[len(adlar) - len(vars_):], vars_))
                    eslem.update({a.arg: d for a, d in
                                  zip(args.kwonlyargs, args.kw_defaults)
                                  if d is not None})
                    return eslem
    raise AssertionError(f'{sinif}.{yontem} bulunamadı')


@pytest.mark.parametrize('yontem', ['set_showerhead_params',
                                    'set_impingement_params'])
def test_f10_t1_utils_imzasi_none_ve_govde_bant(yontem):
    """utils imza varsayılanı None ("çağıran vermedi"), gövde tek kaynağa düşer."""
    kaynak = _oku(UTILS_INJ)
    vars_ = _imza_varsayilanlari(kaynak, 'InjectorDesign', yontem)
    for ad in ('hole_diameter_min', 'hole_diameter_max'):
        assert ad in vars_, (yontem, ad)
        assert isinstance(vars_[ad], ast.Constant) and vars_[ad].value is None, (
            f'{yontem}({ad}=...) varsayılanı None değil: {ast.dump(vars_[ad])}')
    # Gövde: None → ORIFICE_D_BAND_MM[0]/[1]
    from hrma.utils.injector_design import InjectorDesign
    from hrma import constants as c
    enj = InjectorDesign.__new__(InjectorDesign)
    if yontem == 'set_showerhead_params':
        InjectorDesign.set_showerhead_params(enj)
        p = enj.showerhead_params
    else:
        InjectorDesign.set_impingement_params(enj)
        p = enj.impingement_params
    assert p['d_min'] == pytest.approx(c.ORIFICE_D_BAND_MM[0] / 1000, rel=1e-15)
    assert p['d_max'] == pytest.approx(c.ORIFICE_D_BAND_MM[1] / 1000, rel=1e-15)
    # Kullanıcı bandı verirse o uygulanır (bant hakem değil, varsayılan).
    if yontem == 'set_showerhead_params':
        InjectorDesign.set_showerhead_params(enj, hole_diameter_min=1.0,
                                            hole_diameter_max=1.5)
        p = enj.showerhead_params
    else:
        InjectorDesign.set_impingement_params(enj, hole_diameter_min=1.0,
                                             hole_diameter_max=1.5)
        p = enj.impingement_params
    assert (p['d_min'], p['d_max']) == pytest.approx((1.0e-3, 1.5e-3), rel=1e-15)


@app_yamasi_bekleniyor
def test_f10_t1_app_uc_tablosu_kimlik():
    from hrma import constants as c
    from hrma import app as uygulama
    tablo = uygulama._CALCULATE_UC_VARSAYILANLARI
    assert tablo['hole_diameter_min'][0] is c.ORIFICE_D_BAND_MM[0]
    assert tablo['hole_diameter_max'][0] is c.ORIFICE_D_BAND_MM[1]
    assert tablo['hole_diameter_min'][1:] == ('mm', 'not_supplied')


# ===========================================================================
# F-10 · T2 — künye bandın KENDİSİNİ söyler (L* kalıbı) — TAŞINDI
# ===========================================================================
# Denetçi-3 Ş-1 (ana model kararı (ii), 29 Eyl): bu bekçi mevcut bir BEKCI
# dosyasına taşındı — ``tests/test_sabit_tek_kaynak.py::
# test_orifis_cap_bandi_kunyesiyle_AYNI_araligi_soyluyor`` (künye aralığı =
# bant, Sutton s. 337 + Mishra s. 348, tüketici kimliği). Gerekçe T7'de.


# ===========================================================================
# F-10 · T3 — künye adı tüketen dosyalarda ANILIYOR
# ===========================================================================
@pytest.mark.parametrize('yol', [ENGINES_INJ, UTILS_INJ])
def test_f10_t3_kunye_adi_tuketen_dosyada(yol):
    assert 'ORIFICE_D_BAND_SOURCE' in _oku(yol), yol.name
    assert 'ORIFICE_D_BAND_MM' in _oku(yol), yol.name


@app_yamasi_bekleniyor
def test_f10_t3_kunye_adi_app_py_de():
    assert 'ORIFICE_D_BAND_SOURCE' in _oku(APP_PY)


# ===========================================================================
# F-10 · T4 — eski literal bant sayıları KALMADI (AST)
# ===========================================================================
def _sabit_degerler(dugum) -> set:
    """Alt ağaçtaki bütün sayısal ``ast.Constant`` değerleri."""
    return {n.value for n in ast.walk(dugum)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, (int, float))
            and not isinstance(n.value, bool)}


def _ciplak_sayilar(dugum) -> set:
    """Alt ağaçtaki sayısal literaller — abonelik İNDİSLERİ hariç.

    ``ORIFICE_D_BAND_MM[0]`` / ``DEFAULT_CONSTRAINTS['d_min_mm']`` tek
    kaynağa bağlı bir okumadır (indis 0/1 bir bant sayısı değildir);
    ``0.3`` / ``2.5`` / ``3.0 * 1`` ise kaynağı olmayan çıplak sayıdır.
    """
    atla = set()
    for n in ast.walk(dugum):
        if isinstance(n, ast.Subscript):
            atla.update(id(m) for m in ast.walk(n.slice))
    return {n.value for n in ast.walk(dugum)
            if id(n) not in atla
            and isinstance(n, ast.Constant)
            and isinstance(n.value, (int, float))
            and not isinstance(n.value, bool)}


def _get_yedegi(cagri):
    """``x.get('<ad>', <yedek>)`` çağrısıysa (ad, yedek düğümü); değilse None."""
    if not (isinstance(cagri, ast.Call)
            and isinstance(cagri.func, ast.Attribute)
            and cagri.func.attr == 'get' and cagri.args
            and isinstance(cagri.args[0], ast.Constant)
            and isinstance(cagri.args[0].value, str)):
        return None
    yedek = (cagri.args[1] if len(cagri.args) > 1 else
             next((k.value for k in cagri.keywords if k.arg == 'default'),
                  None))
    return (cagri.args[0].value, yedek)


def _bant_adi_anilir(dugum) -> bool:
    """Alt ağaçta bir bant adı geçiyor mu? (dizge sabiti ya da değişken adı)"""
    return any((isinstance(n, ast.Constant) and n.value in BANT_ADLARI)
               or (isinstance(n, ast.Name) and n.id in BANT_ADLARI)
               for n in ast.walk(dugum))


def _banda_baglanan_degerler(agac) -> set:
    """Bir bant ADINA atanan değer ifadelerinin (ve alt düğümlerinin) id'leri.

    Bağlama biçimleri: ``f(<bant adı>=<ifade>)``, ``{'<bant adı>': <ifade>}``,
    ``<bant adı> = <ifade>`` / ``x['<bant adı>'] = <ifade>``.
    """
    kokler = []
    for n in ast.walk(agac):
        if isinstance(n, ast.keyword) and n.arg in BANT_ADLARI:
            kokler.append(n.value)
        elif isinstance(n, ast.Dict):
            kokler.extend(v for k, v in zip(n.keys, n.values)
                          if isinstance(k, ast.Constant)
                          and k.value in BANT_ADLARI)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None:
            hedefler = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any((isinstance(h, ast.Name) and h.id in BANT_ADLARI)
                   or (isinstance(h, ast.Subscript)
                       and isinstance(h.slice, ast.Constant)
                       and h.slice.value in BANT_ADLARI)
                   for h in hedefler):
                kokler.append(n.value)
    return {id(m) for k in kokler for m in ast.walk(k)}


def _yedek_dallari(dugum, bagli: set) -> list:
    """Bant adına bağlı ``or`` / koşullu ifadenin YEDEK işlenenleri.

    Denetçi-2 Ş-E (N4): ``constraints.get('d_min_mm') or 0.3`` biçimi
    ``.get(ad, yedek)`` taramasına girmiyordu (yedek ``.get``in DIŞINDA).
    Kapsam: ``ast.BoolOp(Or)`` ve ``ast.IfExp``. İfade ya kendisi bir bant
    adını anar (``x.get('d_min_mm') or …``, ``… if d_min_mm is None else …``)
    ya da bir bant adına atanan değerin içindedir. Yedek = bant adını ANMAYAN
    işlenen (``IfExp``in koşulu hariç; ``or`` zincirinde karşılaştırma
    düğümleri — koşul işlenenleri — hariç). Bağlı değilse boş liste.
    """
    if isinstance(dugum, ast.BoolOp) and isinstance(dugum.op, ast.Or):
        dallar = [d for d in dugum.values if not isinstance(d, ast.Compare)]
    elif isinstance(dugum, ast.IfExp):
        dallar = [dugum.body, dugum.orelse]
    else:
        return []
    if not (_bant_adi_anilir(dugum) or id(dugum) in bagli):
        return []
    return [d for d in dallar if not _bant_adi_anilir(d)]


def _bant_literalleri(kaynak: str) -> list:
    """Bant anahtar/argüman/varsayılanına BAĞLI eski literaller (yer listesi).

    Denetçi Ş4 (D12/D13): ``constraints.get('d_min_mm', 0.3)`` biçimindeki
    YEDEK literal de bant tanımıdır (anahtar eksik geldiğinde uygulanan
    bant). Bu biçim sözlük/anahtar-sözcük/imza varsayılanı taramasına
    GİRMİYORDU; artık ``.get(<bant adı>, <yedek>)`` yedeğinde HERHANGİ bir
    çıplak sayı (eski 0,3/2,0/3,0 değil, doğru sayı 0,5/2,5 bile) ihlaldir —
    yedek tek kaynaktan okunmalıdır.

    Denetçi-2 Ş-E (N4): aynı kural ``.get`` DIŞINDAKİ yedek biçimlerine de
    uygulanır — ``<bant okuması> or <sayı>`` ve ``<sayı> if … else <bant
    okuması>`` (bkz. ``_yedek_dallari``). Abonelik indisi (``[0]``/``[1]``)
    çıplak sayı sayılmaz.
    """
    agac = ast.parse(kaynak)
    bagli = _banda_baglanan_degerler(agac)
    ihlal = []
    for dugum in ast.walk(agac):
        for dal in _yedek_dallari(dugum, bagli):
            if _ciplak_sayilar(dal):
                ihlal.append((dugum.lineno, '%s yedeği <literal>'
                              % type(dugum).__name__))
        get_yedegi = _get_yedegi(dugum)
        if get_yedegi is not None:
            ad, yedek = get_yedegi
            if (ad in BANT_ADLARI and yedek is not None
                    and _ciplak_sayilar(yedek)):
                ihlal.append((dugum.lineno, '.get(%r, <literal>)' % ad))
        elif isinstance(dugum, ast.Dict):
            for k, v in zip(dugum.keys, dugum.values):
                if (isinstance(k, ast.Constant) and k.value in BANT_ADLARI
                        and _sabit_degerler(v) & ESKI_BANT_LITERALLERI):
                    ihlal.append((dugum.lineno, k.value))
        elif isinstance(dugum, ast.keyword):
            if (dugum.arg in BANT_ADLARI
                    and _sabit_degerler(dugum.value) & ESKI_BANT_LITERALLERI):
                ihlal.append((dugum.value.lineno, dugum.arg))
        elif isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = dugum.args
            adlar = [a.arg for a in args.args]
            vars_ = args.defaults
            for ad, v in zip(adlar[len(adlar) - len(vars_):], vars_):
                if ad in BANT_ADLARI and _sabit_degerler(v) & ESKI_BANT_LITERALLERI:
                    ihlal.append((dugum.lineno, ad))
    return ihlal


@pytest.mark.parametrize('yol', [ENGINES_INJ, UTILS_INJ])
def test_f10_t4_literal_bant_sayisi_KALMADI(yol):
    assert _bant_literalleri(_oku(yol)) == [], yol.name


@app_yamasi_bekleniyor
def test_f10_t4_literal_bant_sayisi_app_py_de_KALMADI():
    assert _bant_literalleri(_oku(APP_PY)) == []


# ===========================================================================
# F-10 · T5 — Ornek-H1 kanon alanı bant içinde, uyarı YOK; sabit n yolu
# ===========================================================================
def test_f10_t5_h1_alani_varsayilan_bantta_uyarisiz():
    from hrma.engines.injector_design import (_plan_orifices,
                                              DEFAULT_CONSTRAINTS)
    u = []
    n, d = _plan_orifices(H1_ALAN_M2, dict(DEFAULT_CONSTRAINTS), u)
    assert (n, d * 1e3) == (3, pytest.approx(2.1115402465584556, rel=1e-9))
    assert u == [], u


def test_f10_t5_sabit_n_yolunda_uyari_bandin_sayisini_tasir():
    """§6.3 kural 2: kullanıcı n sabitlerse kırpılmaz, bant dışı ADIYLA."""
    from hrma.engines.injector_design import (_plan_orifices,
                                              DEFAULT_CONSTRAINTS)
    from hrma.constants import ORIFICE_D_BAND_MM
    u = []
    n, d = _plan_orifices(H1_ALAN_M2, dict(DEFAULT_CONSTRAINTS), u, n_fixed=6)
    assert n == 6 and ORIFICE_D_BAND_MM[0] <= d * 1e3 <= ORIFICE_D_BAND_MM[1]
    assert u == [], 'bant içi sabit n uyarı üretmemeli'
    u = []
    n, d = _plan_orifices(H1_ALAN_M2, dict(DEFAULT_CONSTRAINTS), u, n_fixed=1)
    assert n == 1 and d * 1e3 > ORIFICE_D_BAND_MM[1]
    assert [w['code'] for w in u] == [
        'warn.injector.fixed_n_outside_manufacturing_band']
    assert (u[0]['params']['d_min_mm'], u[0]['params']['d_max_mm']) == (
        round(ORIFICE_D_BAND_MM[0], 1), round(ORIFICE_D_BAND_MM[1], 1))
    # Tek bantta "tercih bandı" dalı ULAŞILAMAZ: aynı geometri iki hüküm almaz.
    assert not any('pref_band' in w['code'] for w in u)


def test_f10_t5_devre_yaniti_bandi_ve_kaynagini_adiyla_tasir(h1):
    """``injector_design_detail.orifice_band`` — tüketici bandı buradan okur."""
    from hrma.constants import ORIFICE_D_BAND_MM, ORIFICE_D_BAND_SOURCE
    bant = h1['motor']['injector_design_detail']['orifice_band']
    assert (bant['d_min_mm'], bant['d_max_mm']) == ORIFICE_D_BAND_MM
    assert bant['source'] == ORIFICE_D_BAND_SOURCE


@app_yamasi_bekleniyor
def test_f10_t5_utils_yolu_h1_planina_bant_disi_demiyor(h1):
    """Cowork A-5'in gördüğü uyarı: aynı plaka için ikinci hüküm KALKTI."""
    uyarilar = h1['injector']['warnings']
    assert not any('manufacturing band' in u for u in uyarilar), uyarilar
    # defaults_applied künyesi sabitten okunur (0,5 / 2,5).
    from hrma.constants import ORIFICE_D_BAND_MM
    kunye = {d['field']: d['value'] for d in h1['defaults_applied']}
    assert kunye['hole_diameter_min'] == ORIFICE_D_BAND_MM[0]
    assert kunye['hole_diameter_max'] == ORIFICE_D_BAND_MM[1]


@pytest.fixture(scope='module')
def h1_plakali():
    """Ornek-H1 + açık plaka kalınlığı 3,0 mm (V3.0.5, 28 Eki).

    HİBRİT-DIŞA kalem 4: plaka kalınlığı verilmezse plaka denetimi kazanılmamış
    3,0 mm ile KOŞMAZ. F-10 çapası plaka SF'sini de kilitlediği için kalınlık
    açıkça verilir (eski örtük değerle aynı → sayılar bit-aynı); öbür vakalar
    plakasız h1 ile koşmaya devam eder.
    """
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=dict(ORNEK_H1, plate_thickness=3.0))
    assert cevap.status_code == 200, cevap.get_json()
    return cevap.get_json()


def test_f10_sayi_degismedi_capasi(h1_plakali):
    """Berke önce/sonra tablosu: Ornek-H1 KANON duş başlığı yolunda
    YAYIMLANAN SAYI DEĞİŞMEZ (denetçi Ş1: bu hüküm yalnız kanon yol
    içindir; çarpışmalı ve kanon-dışı duş başlığı yolunda F-10 sayıyı
    değiştirir — Sunum 2, berke_onay_A2.md F-10 ikinci tablo).

    D35 çapası (3 × Ø2,1115 mm, ΔP 30,5434 bar, SF 0,55, η 0,9489)
    yenilenmedi; değişen yalnız bir uyarı metni ve iki künye sayısı.
    """
    idd = h1_plakali['motor']['injector_design']
    assert idd['number_of_orifices'] == 3
    # 8. tur (14 Eki): çapa B16'lı tabana yenilendi — kâhin main 3edc78b9
    # bağımsız ölçümü (rapor '8. tur', sart8/kahin/); ΔP aynı.
    # v3.0.1 port kulvarı (20 Eki): grain dış çapı = son port (eski 1,5·D_son);
    # kamara küçüldü -> gerçekleşen L* ↓ -> kinetik verim ↓ -> Isp −%0,17 -> ṁ ↑
    # -> delik çapı +%0,08. Pencere/bant hükmü DEĞİŞMEDİ, yalnız ölçüm çapası.
    assert idd['orifice_diameter_mm'] == pytest.approx(2.124505645947217, rel=1e-9)
    assert idd['injection_pressure_drop_bar'] == pytest.approx(30.5433585, rel=1e-7)
    inj = h1_plakali['injector']
    assert (inj['n_holes'], inj['hole_diameter']) == (
        3, pytest.approx(2.124505645947217, rel=1e-9))
    ps = inj['plate_structural']
    # v3.0.1 port kulvarı (20 Eki): plaka çapı = kamara iç çapı 80,68 -> 54,04 mm
    # (grain dış çapı artık son port). Eğilme gerilmesi ~D²/η ile ölçeklenir:
    # 440,114·(54,04/80,68)²·(0,9488/0,9232) ≈ 202,9 MPa (ölçülen 201,292;
    # fark yuvarlanmış çaplardan). Eski çapa (0,545, 0,9488, 440,114 MPa).
    assert (ps['safety_factor'], ps['ligament_efficiency']) == (1.192, 0.9232)
    assert ps['bending_stress_MPa'] == pytest.approx(201.292, abs=1e-3)


# ===========================================================================
# F-10 · T6 — plaka SF delik sayısından BAĞIMSIZ (Lean ligament_n_invariant)
# ===========================================================================
def test_f10_t6_plaka_SF_delik_sayisindan_BAGIMSIZ():
    from hrma.utils.injector_design import injector_plate_structural
    malzeme = {'yield_strength': 240e6, 'density': 7900.0}
    a_plaka = np.pi * (0.080684963 / 2) ** 2      # H1 plaka çapı ~ kamara çapı
    sonuclar = {}
    for n in (3, 4, 5, 6, 8):
        d = float(np.sqrt(4.0 * H1_ALAN_M2 / (np.pi * n)))
        r = injector_plate_structural(30.5433585, 0.080684963, malzeme,
                                      material_name='ss_316',
                                      plate_thickness_m=0.003,
                                      n_holes=n, hole_diameter_m=d,
                                      required_sf=4.0)
        assert r['status'] == 'analyzed', r
        sonuclar[n] = r
    taban = sonuclar[3]
    eta_beklenen = 1.0 - 2.0 * np.sqrt(H1_ALAN_M2 / (np.pi * a_plaka))
    for n, r in sonuclar.items():
        for alan in ('safety_factor', 'bending_stress_MPa',
                     'required_thickness_mm', 'plate_mass_kg',
                     'ligament_efficiency'):
            assert r[alan] == pytest.approx(taban[alan], rel=1e-9), (n, alan)
        assert r['ligament_efficiency'] == pytest.approx(eta_beklenen, abs=5e-5)
        assert r['n_holes'] == n


# ===========================================================================
# F-10 · T7 — bekçi kapsamı yeni adları görüyor (bu gövde adları anar)
# ===========================================================================
#: Denetçi-3 Ş-1 (ana model kararı (ii), 29 Eyl). İlk yol (T7 yaması,
#: ``28bf467a``) bu dosyayı ``tools/sabit_envanteri.BEKCI_DOSYALARI``e
#: ekliyordu; ``test_d27_altyapi_a1::test_kapsam_sayilari_OLCUMLE_uyusuyor``
#: listedeki HER dosyayı D27 taban ağacından (``git show 709a235e:<dosya>``)
#: okur ve bu dosya orada yoktur → iki bekçi gerilime girdi (docs'suz ağaçta
#: D27 bekçisi kanıt kapısında ATLANDIĞI için görünmedi). Yama geri alındı;
#: ORIFICE_D_BAND_* bekçisi mevcut BEKCI dosyasına taşındı
#: (``tests/test_sabit_tek_kaynak.py::test_orifis_cap_bandi_kunyesiyle_AYNI_
#: araligi_soyluyor``). Bu test iki şeyi ölçer: kapsam aracı adları bir test
#: GÖVDESİNDE görüyor ve liste bu dosyayı (D27 tabanında olmayan dosyayı)
#: yeniden taşımıyor — docs'suz yayın dalında da koşar.
BU_DOSYA_BAGIL = 'tests/test_d37_hibrit_f1.py'


def test_f10_t7_bekci_kapsami_yeni_adlari_goruyor():
    kapsam = sabit_envanteri.bekci_kapsami(KOK)
    assert {'ORIFICE_D_BAND_MM', 'ORIFICE_D_BAND_SOURCE'} <= set(kapsam['govde'])
    assert BU_DOSYA_BAGIL not in sabit_envanteri.BEKCI_DOSYALARI, (
        'kulvar bekçi dosyası BEKCI_DOSYALARI\'na geri girdi: D27 ölçüm çapası '
        '(709a235e) bu dosyayı okuyamaz → test_d27_altyapi_a1 kırmızı')


# ===========================================================================
# F-10 · T8 — i18n bant uyarısı parametreli kaldı (sayı metne gömülmedi)
# ===========================================================================
def test_f10_t8_i18n_bant_uyarisi_parametreli_kaldi():
    metin = _oku(I18N_COMMON)
    satirlar = [s for s in metin.splitlines()
                if "'warn.injector.fixed_n_outside_manufacturing_band'" in s]
    assert len(satirlar) == 2, 'EN + TR bekleniyor'
    for s in satirlar:
        assert '{d_min_mm}' in s and '{d_max_mm}' in s, s
        assert not re.search(r'\d\.\d+\s*-\s*\d\.\d+', s), (
            'bant sayısı metne gömülmüş: ' + s)


# ===========================================================================
# F-10 · T9 — DAVRANIŞ bekçileri (denetçi-2 Ş-C)
# ===========================================================================
# Denetçi-2 N8: app yamasının çarpışmalı dalında üst kenar yanlış indisle
# okunduğunda ([1] → [0], bant 0,5/0,5'e çöker) f1 + TestP16 +
# test_field_wiring_layer_b YEŞİL kalıyordu — T4 yalnız literale, T1 yalnız
# duş başlığı uç tablosuna bakıyor; sayısı DEĞİŞEN çarpışmalı /calculate
# yolunun bant BAĞLANTISINI hiçbir test ölçmüyordu. T9 davranışı ölçer:
# beklenen plan ürün kodu kullanılmadan, yanıtın KENDİ alanından ve
# ``ORIFICE_D_BAND_MM``den türetilir (Ş-B ölçümü:
# docs/scofield/raw/OH/A2/hibrit/a1/sart3/sb_*.json).

@pytest.fixture(scope='module')
def carpismali():
    """Çarpışmalı ``/calculate`` yanıtları: 3 kN ve 1 kN + element_pairs = 1."""
    from hrma.app import app
    app.config['TESTING'] = True
    yanitlar = {}
    with app.test_client() as ist:
        for ad, ek in (('3kN', {'thrust': 3000.0}),
                       ('ep1', {'element_pairs': 1})):
            cevap = ist.post('/calculate', json=dict(
                ORNEK_H1, injector_type='impingement', **ek))
            assert cevap.status_code == 200, cevap.get_json()
            yanitlar[ad] = cevap.get_json()['injector']
    return yanitlar


def _cift_capi_mm(alan_mm2: float, cift: int) -> float:
    """``cift`` doublet (2·cift delik) aynı toplam alanı taşırsa delik çapı."""
    return 2.0 * float(np.sqrt(alan_mm2 / (2.0 * cift * np.pi)))


@app_yamasi_bekleniyor
def test_f10_t9_carpismali_cift_secimi_bandin_ust_kenarindan(carpismali):
    """3 kN: çift sayısı, çapı ``ORIFICE_D_BAND_MM[1]``i aşmayan EN KÜÇÜK çift.

    Utils kuralı (``_calculate_impingement``): ``n_pairs`` 2'den başlar,
    çap üst kenara inene dek artar; çap banda oturduğu için kırpma yok →
    alan korunur. Beklenen çift sayısı yanıtın ``injection_area``sından ve
    bandın üst kenarından bağımsız yolla çıkarılır. Yama öncesi (üst kenar
    literal 2,0) 8 × 1,881 mm verirdi → KIRMIZI; N8 (üst kenar [0] = 0,5)
    → KIRMIZI.
    """
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    inj = carpismali['3kN']
    alan = inj['injection_area']
    cift = 2
    while _cift_capi_mm(alan, cift) > ust * (1 + 1e-12):
        cift += 1
    assert (inj['n_pairs'], inj['n_holes']) == (cift, 2 * cift), (
        f"çift seçimi banttan değil: yanıt {inj['n_pairs']} çift, bant üst "
        f"kenarı {ust} mm ile en küçük çift {cift}")
    assert inj['hole_diameter'] == pytest.approx(_cift_capi_mm(alan, cift),
                                                 rel=1e-9)
    assert alt <= inj['hole_diameter'] <= ust * (1 + 1e-12)
    # Bir eksik çift banda SIĞMAZ (en küçük n; alt sınır 2 çift).
    assert cift == 2 or _cift_capi_mm(alan, cift - 1) > ust
    assert not any('re-solved' in u or 'clamped' in u
                   for u in inj['warnings']), inj['warnings']


@app_yamasi_bekleniyor
def test_f10_t9_carpismali_tek_cift_istegi_bantta_karsilanir(carpismali):
    """1 kN + ``element_pairs = 1``: istek KARŞILANIR (1 çift / 2 delik).

    v3.0.1: çap artık iki fazlı kanon alandan, ≈ 2,60 mm, bandın üstünde;
    istek karşılanır ve bant hükmü yayımlanır (sessiz değil).

    Yama öncesi (üst kenar 2,0) çap 2,0'a kırpılıp 4 × 2,0 mm'ye yeniden
    çözülüyordu ("re-solved to 2"); N8'de (üst kenar 0,5) yine kırpılır.
    """
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    inj = carpismali['ep1']
    assert (inj['n_pairs'], inj['n_holes']) == (1, 2), (
        'kullanıcının 1 çifti karşılanmadı: '
        f"{inj['n_pairs']} çift / {inj['n_holes']} delik; {inj['warnings']}")
    d = inj['hole_diameter']
    assert d == pytest.approx(_cift_capi_mm(inj['injection_area'], 1),
                              rel=1e-9)
    # v3.0.1 E2 (20 Eki): ekran bloğu artık devrenin KANON akış alanını
    # tüketiyor. Bu alan kendinden basınçlı N₂O için Dyer NHNE ile çözülür.
    # Eski 2,19 mm tek fazlı SPI alanından geliyordu ve iki fazlı akışta
    # hedef debinin ~%71'ini veriyordu (E2 raporu). Doğru alanla tek çift
    # Ø2,602 mm ister; bu, kaynaklı bandın (0,5-2,5 mm) ÜSTÜNDEDİR. İstek
    # olduğu gibi karşılanır (1 çift) ve bant hükmü kullanıcıya iner
    # (devre uyarısı ekran bloğuna taşınır; ana model, çapraz kırılma).
    assert d > ust
    assert d == pytest.approx(2.6020, abs=5e-4)
    kodlar = [w.get('code') for w in inj['warnings'] if isinstance(w, dict)]
    assert 'warn.injector.fixed_n_outside_manufacturing_band' in kodlar, (
        'bant dışı tek çift planı sessiz yayımlanıyor: %r' % inj['warnings'])
    assert not any('re-solved' in u for u in inj['warnings']), inj['warnings']


#: Küçük alan penceresi [mm²]: n = 1 ile çap bandın altında kalır (A <
#: π·d_alt²/4 ≈ 0,196 mm²). 0,15 / 0,1697 / 0,19 eski sert kısıtla (d_min
#: 0,3 mm) 2 delik verirdi (A ≥ 2·π·0,3²/4 ≈ 0,141 mm²) — Ş-B tablosu;
#: 0,05 iki kısıtta da 1 delik (pencere dışı kontrol).
KUCUK_ALANLAR_MM2 = (0.05, 0.15, 0.1697374107353576, 0.19)


@pytest.mark.parametrize('alan_mm2', KUCUK_ALANLAR_MM2)
def test_f10_t9_devre_kucuk_alanda_d_min_yedegi_banttan(alan_mm2):
    """Devre çözücüsü: bant tutmazsa n = max(1, ⌊4A/(π·d_min²)⌋), d_min BANTTAN.

    Hem varsayılan kısıt sözlüğüyle hem anahtarsız sözlükle (``.get``
    yedeği) aynı sonuç. Beklenen değer ürün kodu kullanılmadan
    ``ORIFICE_D_BAND_MM[0]``dan türetilir.
    """
    from hrma.engines.injector_design import (_plan_orifices,
                                              DEFAULT_CONSTRAINTS)
    from hrma.constants import ORIFICE_D_BAND_MM
    alan = alan_mm2 * 1e-6
    d_min = ORIFICE_D_BAND_MM[0] * 1e-3
    # Ön koşul: tek delikte bile çap bandın altında (arama döngüsü boş kalır).
    assert np.sqrt(4.0 * alan / np.pi) < d_min
    n_bek = max(1, int(np.floor(4.0 * alan / (np.pi * d_min ** 2))))
    d_bek = float(np.sqrt(4.0 * alan / (np.pi * n_bek)))
    for kisit in (dict(DEFAULT_CONSTRAINTS), {}):
        uyarilar = []
        n, d = _plan_orifices(alan, kisit, uyarilar)
        assert (n, d) == (n_bek, pytest.approx(d_bek, rel=1e-12)), (
            f'kısıt {sorted(kisit)}: {n} × {d * 1e3:.4f} mm, beklenen '
            f'{n_bek} × {d_bek * 1e3:.4f} mm')
        # 5. tur Ş-4: tek delikte bile d < d_min → "imalat bandı dışı (alt
        # sınırın altında)" sınıfı; eski ``orifice_d_below_pref_band``
        # ("imalat alt sınırına yakın") bu çapa yanlış hüküm veriyordu.
        assert [w['code'] for w in uyarilar] == [
            'warn.injector.orifice_d_below_manufacturing_band']


def test_f10_t9_devre_yaniti_kucuk_alanda_bandin_d_min_ile_cozulur():
    """``design_injector`` (``/api/injector-design``in çözücüsü) ucu ucuna.

    Ş-B ölçümü: ṁ_ox 0,004 kg/s → A 0,1697 mm²; eski sert kısıt 2 × 0,3287,
    bant 1 × 0,4649 mm. Beklenen n yanıtın KENDİ alanından ve bandın alt
    kenarından türetilir.
    """
    from hrma.engines.injector_design import design_injector
    from hrma.constants import ORIFICE_D_BAND_MM
    r = design_injector({'motor_type': 'hybrid', 'injector_type': 'showerhead',
                         'mdot_ox': 0.004, 'rho_ox': 1141.0, 'Pc_bar': 20.0,
                         'dp_ratio_ox': 0.2})
    ox = r['ox_circuit']
    alan = ox['total_area_mm2'] * 1e-6
    d_min = ORIFICE_D_BAND_MM[0] * 1e-3
    n_bek = max(1, int(np.floor(4.0 * alan / (np.pi * d_min ** 2))))
    assert ox['n_orifices'] == n_bek, (ox['n_orifices'], n_bek)
    assert ox['orifice_d_mm'] == pytest.approx(
        np.sqrt(4.0 * alan / (np.pi * n_bek)) * 1e3, rel=1e-12)
    assert (r['orifice_band']['d_min_mm'],
            r['orifice_band']['d_max_mm']) == ORIFICE_D_BAND_MM


# ===========================================================================
# F-10 · T10 — çarpışmalı ALT KENAR kırpması (denetçi-3 Ş-4 (i) + Ş-6 K3y)
# ===========================================================================
# Denetçi-3: otomatik çift yolunda (n_pairs = 0) çap alt kenara kırpılınca
# çift tabanı max(2, …) yüzünden alan istenenin ÜSTÜNE çıkıyor, hız düşüyor
# ve HİÇBİR uyarı yazılmıyordu (fail-open; 50 N'de eski hız uyarısı
# kalkıyordu). K3y (max(2, …) → max(1, …)) f1'de YEŞİL kalıyordu — alt kenar
# kırpmasını ölçen bekçi yoktu. Beklenen plan ürün kodu kullanılmadan alan
# korunumundan (A = ṁ/(C_d·√(2ρΔP))) ve ``ORIFICE_D_BAND_MM``den türetilir.

#: 2 çiftte (4 delik) çap alt kenarın ALTINDA kalan debiler [kg/s]
#: (ΔP 4 bar, N₂O 293 K: 0,002 → 0,18 mm, 0,005 → 0,29, 0,01 → 0,40 mm).
KIRPMA_DEBILERI_KG_S = (0.002, 0.005, 0.01)


def _carpismali_utils(mdot):
    import contextlib
    import io
    from hrma.utils.injector_design import InjectorDesign
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        inj = InjectorDesign(mdot_ox=mdot, chamber_pressure=20.0,
                             pressure_drop=4.0, injector_type='impingement')
        inj.set_impingement_params()
        return inj, inj.calculate()


@pytest.mark.parametrize('mdot', KIRPMA_DEBILERI_KG_S)
def test_f10_t10_carpismali_alt_kenar_kirpmasi_alaniyla_yayimlanir(mdot):
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    inj, r = _carpismali_utils(mdot)
    a_req = mdot / (inj.C_d * np.sqrt(2.0 * inj.rho_ox * inj.delta_P_inj * 1e5))
    # Ön koşul: en küçük plan (2 çift = 4 delik) bile alt kenarın altında.
    assert 2.0 * np.sqrt(a_req / (4 * np.pi)) < alt * 1e-3
    a_delik = np.pi * (alt * 1e-3) ** 2 / 4.0
    cift = max(2, int(np.ceil(a_req / (2.0 * a_delik))))
    a_tes = 2 * cift * a_delik
    assert (r['n_pairs'], r['n_holes']) == (cift, 2 * cift), (
        f"çift tabanı banttan değil: {r['n_pairs']} çift, beklenen {cift}")
    assert r['hole_diameter'] == pytest.approx(alt, rel=1e-12)
    assert r['injection_area'] == pytest.approx(a_tes * 1e6, rel=1e-12)
    assert r['exit_velocity'] == pytest.approx(
        mdot / (inj.rho_ox * a_tes), rel=1e-9)
    # Kırpma SESSİZ DEĞİL: tek uyarı, bandın sayısı + iki alan + oran.
    kirpma = [w for w in r['warnings'] if 'clamped to' in w]
    assert len(kirpma) == 1, r['warnings']
    w = kirpma[0]
    assert w.startswith('The auto-selected minimum of 2 doublet pairs'), w
    assert f'({alt:.2f}-{ust:.2f} mm)' in w, w
    assert f'clamped to {alt:.2f} mm with {cift} pairs' in w, w
    assert f'{a_tes * 1e6:.4g} mm^2 against the {a_req * 1e6:.4g} mm^2' in w, w
    assert f'(ratio {a_tes / a_req:.3f})' in w, w
    assert a_tes / a_req > 1.0


def test_f10_t10_bant_icinde_kirpma_uyarisi_yok():
    """Kontrol: çap bantta (ṁ 0,02 kg/s → 4 × 0,57 mm) kırpma uyarısı YOK."""
    from hrma.constants import ORIFICE_D_BAND_MM
    _, r = _carpismali_utils(0.02)
    assert ORIFICE_D_BAND_MM[0] < r['hole_diameter'] < ORIFICE_D_BAND_MM[1]
    assert not any('clamped to' in w or 're-solved' in w
                   for w in r['warnings']), r['warnings']


@app_yamasi_bekleniyor
def test_f10_t10_calculate_50N_kirpmasi_yanitta_adiyla():
    """``/calculate`` Ornek-H1 çarpışmalı 50 N (denetçi-3 ölçümü: 4 × 0,347 →
    4 × 0,50 mm, A 0,378 → 0,785 mm², v 68,75 → 33,12 m/s, uyarısız).

    Yama öncesi app bandı 0,3/2,0 → 0,347 mm bant içi, kırpma yok → KIRMIZI
    (xfail-strict); yamayla uyarı yanıtın ``injector.warnings``inde durur ve
    andığı teslim alanı yanıtın ``injection_area``sıdır.
    """
    from hrma.app import app
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=dict(
            ORNEK_H1, thrust=50.0, injector_type='impingement',
            **KANON_DISI_DP))
    assert cevap.status_code == 200, cevap.get_json()
    inj = cevap.get_json()['injector']
    assert (inj['n_pairs'], inj['n_holes']) == (2, 4)
    assert inj['hole_diameter'] == pytest.approx(alt, rel=1e-12)
    kirpma = [w for w in inj['warnings'] if 'clamped to' in w]
    assert len(kirpma) == 1, inj['warnings']
    assert f'({alt:.2f}-{ust:.2f} mm)' in kirpma[0]
    assert f"{inj['injection_area']:.4g} mm^2 against" in kirpma[0], (
        kirpma[0], inj['injection_area'])


# ===========================================================================
# F-10 · T11 — devre uyarı SINIFI (d) ve anahtarsız sözlük (denetçi-3 Ş-6)
# ===========================================================================
# K5: n_max sınırında plan_infeasible eşiği d_max·1,2 yapılınca (eski
# above_pref sınıfı geri gelir) f1 + test_injector_design + test_d20_hibrit_a1
# 98/98 YEŞİL kalıyordu. K6: ``.get('d_min_mm', …)`` yedeği yanlış öğeye
# (``DEFAULT_CONSTRAINTS['d_max_mm']``) bağlanınca f1 YEŞİL kalıyordu — T9'un
# anahtarsız sözlük vakası yalnız küçük alanda koşuyor, orada formül n = 1'e
# dejenere. Beklenen sınıf ürün kodu kullanılmadan banttan türetilir.

#: Sabit n yolunda denenen çaplar [mm]: bant altı, bant içi ×2, (2,5; 3,0].
SABIT_N_CAPLARI_MM = (0.4, 1.0, 2.0, 2.8)
SABIT_N = 12


def _alan_m2(n, d_mm):
    return n * np.pi * (d_mm * 1e-3) ** 2 / 4.0


@pytest.mark.parametrize('d_mm', SABIT_N_CAPLARI_MM)
@pytest.mark.parametrize('sozluk', ['varsayilan', 'anahtarsiz'])
def test_f10_t11_sabit_n_uyari_sinifi_banttan(d_mm, sozluk):
    from hrma.engines.injector_design import (_plan_orifices,
                                              DEFAULT_CONSTRAINTS)
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    kisit = dict(DEFAULT_CONSTRAINTS) if sozluk == 'varsayilan' else {}
    uyarilar = []
    n, d = _plan_orifices(_alan_m2(SABIT_N, d_mm), kisit, uyarilar,
                          n_fixed=SABIT_N)
    assert (n, d * 1e3) == (SABIT_N, pytest.approx(d_mm, rel=1e-12))
    beklenen = ([] if alt <= d_mm <= ust
                else ['warn.injector.fixed_n_outside_manufacturing_band'])
    assert [w['code'] for w in uyarilar] == beklenen, (sozluk, d_mm, uyarilar)
    for w in uyarilar:
        p = w.get('params') or {}
        assert (p.get('d_min_mm'), p.get('d_max_mm')) == (alt, ust), w


@pytest.mark.parametrize('sozluk', ['varsayilan', 'anahtarsiz'])
def test_f10_t11_n_max_sinirinda_ust_kenar_ustu_plan_saglanamaz(sozluk):
    """(d) sınıfı: n_max'ta çap (2,5; 3,0] mm → ``orifice_plan_infeasible``.

    Eski sert kısıtla (3,0) bu aralık ``orifice_d_above_pref_band`` (tercih
    bandı dışı) alıyordu; tek bantta plan SAĞLANAMAZ hükmüdür (Sunum 2
    üçüncü tablo, sıvı 55/65 kN). K5 (eşik d_max·1,2) → KIRMIZI.
    """
    from hrma.engines.injector_design import (_plan_orifices,
                                              DEFAULT_CONSTRAINTS)
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    n_max = int(DEFAULT_CONSTRAINTS['n_max'])
    kisit = dict(DEFAULT_CONSTRAINTS) if sozluk == 'varsayilan' else {}
    for d_mm in (ust * 1.04, ust * 1.12, ust * 1.2):     # 2,6 / 2,8 / 3,0 mm
        uyarilar = []
        n, d = _plan_orifices(_alan_m2(n_max, d_mm), kisit, uyarilar)
        assert n == n_max and d * 1e3 == pytest.approx(d_mm, rel=1e-12)
        assert [w['code'] for w in uyarilar] == [
            'warn.injector.orifice_plan_infeasible'], (sozluk, d_mm, uyarilar)
        assert uyarilar[0]['params']['d_max_mm'] == ust


# ===========================================================================
# YB-03 — ölü dördüncü bant yok
# ===========================================================================
def test_yb03_validation_olu_hole_diameter_bandi_yok():
    from hrma.validation.validation_system import ValidationSystem
    assert 'hole_diameter' not in ValidationSystem().injector_limits
    assert "'hole_diameter': (" not in _oku(VALIDATION_PY)


# ===========================================================================
# F-09 — kalıntı ayrıştırması
# ===========================================================================
def test_f09_residual_decomposition_yayimlanir_ve_kapanir(taban):
    _, sonuc = taban
    cross = sonuc['combustion_stability']['chug_loop']['tau_c_vs_residence_time']
    rd = cross['residual_decomposition']
    for k in ('discharge_coefficient_term', 'throat_discharge_coefficient',
              'rt_identity_term', 'rt_from_cstar_m2_s2', 'rt_from_cea_m2_s2',
              'rt_identity_break_pct', 'explained_ratio', 'unexplained_pct',
              '_basis'):
        assert k in rd, k
    # Kapanış (Lean residual_decomposition_closes): e·(1 + u/100) = r.
    assert rd['explained_ratio'] * (1.0 + rd['unexplained_pct'] / 100.0) == \
        pytest.approx(cross['ratio'], rel=1e-12)
    # Çarpım özdeşliği.
    assert rd['discharge_coefficient_term'] * rd['rt_identity_term'] == \
        pytest.approx(rd['explained_ratio'], rel=1e-14)


def test_f09_terimler_yanitin_kendi_yapraklarindan_yeniden_uretilir(taban):
    """Bağımsız ikinci yol: c*, γ, MW, T_c → terimler (ürün kodu KULLANILMAZ)."""
    from hrma.constants import R_UNIVERSAL
    from hrma.engines.hybrid_rocket_engine import THROAT_DISCHARGE_COEFFICIENT
    from hrma.stability.chamber import gamma_function
    _, sonuc = taban
    rd = sonuc['combustion_stability']['chug_loop']['tau_c_vs_residence_time'][
        'residual_decomposition']
    c_star, gamma = float(sonuc['c_star']), float(sonuc['gamma'])
    rt_cstar = (c_star * gamma_function(gamma)) ** 2
    rt_cea = (R_UNIVERSAL / float(sonuc['molecular_weight'])) * float(
        sonuc['chamber_temperature'])
    assert rd['discharge_coefficient_term'] == pytest.approx(
        1.0 / THROAT_DISCHARGE_COEFFICIENT, rel=1e-14)
    assert rd['throat_discharge_coefficient'] == THROAT_DISCHARGE_COEFFICIENT
    assert rd['rt_from_cstar_m2_s2'] == pytest.approx(rt_cstar, rel=1e-12)
    assert rd['rt_from_cea_m2_s2'] == pytest.approx(rt_cea, rel=1e-12)
    assert rd['rt_identity_term'] == pytest.approx(rt_cstar / rt_cea, rel=1e-12)
    assert rd['rt_identity_break_pct'] == pytest.approx(
        (rt_cea - rt_cstar) / rt_cstar * 100.0, rel=1e-9)


def test_f09_cd_terimi_karari_kilidi(taban):
    """C_D terimi DÂHİL: açıklanamayan ≈ 0. Dışarıda bırakılsa %2 kalırdı.

    Ölçüldü (A2 hibrit a1 once K3): oran 1,028589 = 1,020408 × 1,008017;
    C_D terimsiz açıklanamayan %2,04 (= 1/C_D − 1). Bu bekçi kararı kilitler:
    iki terim birlikte oranı KAPATIR, biri eksilirse kapatmaz.
    """
    _, sonuc = taban
    cross = sonuc['combustion_stability']['chug_loop']['tau_c_vs_residence_time']
    rd = cross['residual_decomposition']
    assert abs(rd['unexplained_pct']) < 1e-6, rd
    acik_cd_siz = (cross['ratio'] - rd['rt_identity_term']) / rd['rt_identity_term'] * 100
    assert acik_cd_siz == pytest.approx(
        (rd['discharge_coefficient_term'] - 1.0) * 100.0, rel=1e-9)
    assert acik_cd_siz > 1.0, 'C_D terimi olmadan artık açıklanamaz kalmalı'


def test_f09_yorum_metni_artik_tam_1_bolu_cd_iddia_etmiyor(taban):
    from hrma.engines.hybrid_rocket_engine import HYBRID_TAU_C_RESIDUAL
    from hrma.engines.liquid_rocket_engine import (
        TAU_C_RESIDUAL_DECOMPOSITION_BASIS)
    _, sonuc = taban
    cross = sonuc['combustion_stability']['chug_loop']['tau_c_vs_residence_time']
    assert 'exactly 1/C_D' not in cross['interpretation']
    assert 'residual_decomposition' in cross['interpretation']
    assert cross['interpretation'].endswith(HYBRID_TAU_C_RESIDUAL)
    # Künye TEK tanım yeri: sıvı motorun sabiti, ikinci metin yazılmadı.
    assert cross['residual_decomposition']['_basis'] is \
        TAU_C_RESIDUAL_DECOMPOSITION_BASIS


def test_f09_girdi_eksikse_alan_konmaz(taban):
    """Fail-closed: MW yoksa terimler UYDURULMAZ (None → alan yok)."""
    motor, sonuc = taban
    tau_c = sonuc['combustion_stability']['chug_loop']['chamber_time_constant']
    assert motor._tau_c_residual_terms(
        {'chamber_temperature': 3000.0}, tau_c, 0.01) is None
    assert motor._tau_c_residual_terms(
        {'chamber_temperature': 3000.0, 'molecular_weight': 'yok'},
        tau_c, 0.01) is None
    from hrma.engines.liquid_rocket_engine import tau_c_vs_residence_time_field
    alan = tau_c_vs_residence_time_field(0.01, 0.0102, 'x', residual_terms=None)
    assert 'residual_decomposition' not in alan


def test_f09_h1_ucunda_da_yayimlanir(h1):
    cross = h1['motor']['combustion_stability']['chug_loop'][
        'tau_c_vs_residence_time']
    rd = cross['residual_decomposition']
    assert rd['explained_ratio'] * (1.0 + rd['unexplained_pct'] / 100.0) == \
        pytest.approx(cross['ratio'], rel=1e-12)
    assert abs(rd['unexplained_pct']) < 1e-6


# ===========================================================================
# K-8 — segment sayısı uydurulmaz
# ===========================================================================
def test_k8_grain_design_uydurma_segment_sayisi_yayimlamaz(taban):
    _, sonuc = taban
    gd = sonuc['grain_design']
    assert 'number_of_segments' not in gd, gd
    assert 'segment_length_mm' not in gd
    assert gd['segmentation'] == 'not_modelled'
    assert 'number_of_segments' in gd['segmentation_basis']
    assert '0.3' in gd['segmentation_basis'], 'eski kuralın adı beyanda'


def test_k8_h1_ucunda_da_yok(h1):
    for dugum in (h1['motor']['grain_design'],
                  h1['motor']['motor_geometry']['grain_design']):
        assert 'number_of_segments' not in dugum
        assert dugum['segmentation'] == 'not_modelled'


def test_k8_kaynakta_segment_anahtari_kalmadi():
    """AST: hibrit motor sözlüklerinde 'number_of_segments' anahtarı YOK."""
    agac = ast.parse(_oku(HYBRID_PY))
    anahtarlar = [(n.lineno, k.value) for n in ast.walk(agac)
                  if isinstance(n, ast.Dict)
                  for k in n.keys
                  if isinstance(k, ast.Constant) and k.value == 'number_of_segments']
    assert anahtarlar == []
    assert 'fuel_length / 0.3' not in _oku(HYBRID_PY)


def test_k8_step_segment_plani_tek_parca(taban):
    """Tüketici fail-closed: plan None → tek parça + künye (uydurma yok)."""
    from hrma.export.step_export import _grain_segment_plan
    _, sonuc = taban
    assert _grain_segment_plan({'grain_design': sonuc['grain_design']}) is None


# ===========================================================================
# YB-04 — besleme basıncı kaynağı beyanlı
# ===========================================================================
def test_yb04_feed_pressure_beyani(taban):
    _, sonuc = taban
    idd = sonuc['injector_design']
    oxc = sonuc['injector_design_detail']['ox_circuit']
    assert idd['feed_pressure_bar'] == pytest.approx(
        float(sonuc['chamber_pressure']) + oxc['delta_p_bar'], rel=1e-12)
    assert idd['feed_pressure_source'] == 'n2o_saturation_at_tank_temperature'
    # Ölçülen gerçek: N₂O devresinde P₁ = P_sat(T_tank) (doyma tablosu).
    assert idd['feed_pressure_bar'] == pytest.approx(
        oxc['vapor_pressure_bar'], rel=1e-9)
    assert 'tank_pressure' in idd['feed_pressure_basis']
    assert 'NOT an input' in idd['feed_pressure_basis']


def test_yb04_tank_pressure_devreye_girmiyor_beyani_h1_de(h1):
    """Ornek-H1: kullanıcının 50 bar'ı yankı, devre P_sat 50,54 bar kullanır."""
    idd = h1['motor']['injector_design']
    assert h1['motor']['tank_pressure'] == 50.0
    assert idd['feed_pressure_source'] == 'n2o_saturation_at_tank_temperature'
    assert idd['feed_pressure_bar'] == pytest.approx(50.5433585, rel=1e-7)
    assert idd['feed_pressure_bar'] != h1['motor']['tank_pressure']


# ===========================================================================
# Lean + registry
# ===========================================================================
YENI_TEOREMLER = ('orificeCount_area_invariant', 'ligament_n_invariant',
                  'tauC_ratio_factorises', 'residual_decomposition_closes')

#: Denetçi Ş5: çapa METNİ doğru satırda olsa bile YANLIŞ işlevde olabilir —
#: ``d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))`` metni
#: ``engines/injector_design.py``de altı kez geçer; kayıt :966'yı
#: (``_plan_gas_elements``, gaz elemanı planı) gösteriyordu ve
#: ``check.py --links-only`` yalnız metne baktığı için yeşildi. Teoremin
#: iddiası sıvı ORİFİS planıdır → çapa ``_plan_orifices`` gövdesinde durmalı.
TEOREM_ISLEVI = {
    'orificeCount_area_invariant': '_plan_orifices',
    'ligament_n_invariant': 'injector_plate_structural',
    'tauC_ratio_factorises': '_tau_c_residual_terms',
    'residual_decomposition_closes': '_tau_c_residual_terms',
}


def _satirin_islevi(kaynak: str, satir: int):
    """``satir``ı kapsayan EN İÇTEKİ işlevin adı (yoksa None)."""
    en_ic = None
    for n in ast.walk(ast.parse(kaynak)):
        if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.lineno <= satir <= n.end_lineno
                and (en_ic is None or n.lineno > en_ic.lineno)):
            en_ic = n
    return en_ic.name if en_ic is not None else None


def test_lean_teoremleri_dosyada_ve_deftere_bagli():
    """Ad eşleşmesi SÖZCÜK sınırıyla: ``residual_decomposition_closes_x`` gibi
    bir yeniden adlandırma "var" sayılmaz (ters mutasyon M15 dersi)."""
    metin = _oku(LEAN)
    assert 'sorry' not in metin
    for ad in YENI_TEOREMLER:
        assert re.search(rf'^theorem {re.escape(ad)}\b', metin, re.M), ad
        assert re.search(rf'^#print axioms HRMA\.{re.escape(ad)}\s*$', metin,
                         re.M), ad
    kayit = json.loads(_oku(REGISTRY))
    benim = {e['theorem']: e for e in kayit['entries']
             if e['theorem'].split('.')[-1] in YENI_TEOREMLER}
    assert set(benim) == {f'HRMA.{ad}' for ad in YENI_TEOREMLER}
    lean_satirlar = metin.splitlines()
    for e in benim.values():
        ad = e['theorem'].split('.')[-1]
        assert e['status'] == 'proved'
        assert e['lean_file'] == 'formal/LeanLab/HRMAInjector.lean'
        assert re.match(rf'theorem {re.escape(ad)}\b',
                        lean_satirlar[e['lean_line'] - 1]), (ad, e['lean_line'])
        py_kaynak = _oku(KOK / e['python_file'])
        py = py_kaynak.splitlines()
        assert e['anchor'] in py[e['python_line'] - 1], (e['theorem'],
                                                        e['python_line'])
        assert (_satirin_islevi(py_kaynak, e['python_line'])
                == TEOREM_ISLEVI[ad]), (
            e['theorem'], e['python_line'],
            _satirin_islevi(py_kaynak, e['python_line']))


# ===========================================================================
# 5. tur · Ş-4 — delik çapı hükmü TEK sınıflandırıcıdan (ana model kararı
# (i), Astra danışmalı, §28-18)
# ===========================================================================
# Denetim-4 (7 Eki): küçük alan penceresinde aynı yanıtta devre yolu d < 0,5
# mm için "imalat alt sınırına yakın" (``orifice_d_below_pref_band``), plaka
# yolu "imalat bandı dışı" diyordu. Beklenen sınıflar ürün kodu
# kullanılmadan bandın kenarlarından ve adlandırılmış yakınlık payından
# türetilir; sınırın altı / tam eşiti / üstü ve 'yakın' penceresinin iki
# kenarı ayrı vakadır.

def _bant_ve_yakin_kenar():
    from hrma.constants import ORIFICE_D_BAND_MM
    from hrma.engines.injector_design import ORIFICE_D_NEAR_LOWER_EDGE_FRAC
    alt, ust = ORIFICE_D_BAND_MM
    return alt, ust, alt * (1.0 + ORIFICE_D_NEAR_LOWER_EDGE_FRAC)


def _beklenen_sinif(d, alt, ust, yakin):
    """Sınıflandırıcının testte bağımsız yazılmış tanımı (kenarlar içeride)."""
    if d < alt:
        return 'below_band'
    if d > ust:
        return 'above_band'
    return 'near_lower_edge' if d < yakin else 'in_band'


#: (ad, çap üreteci (alt, üst, yakın) → mm) — Ş-4 sınama noktaları.
S4_NOKTALAR = (
    ('alt_sinirin_altinda', lambda a, u, y: a * (1 - 1e-6)),
    ('alt_sinira_tam_esit', lambda a, u, y: a),
    ('alt_sinirin_ustunde', lambda a, u, y: a * (1 + 1e-6)),
    ('yakin_ust_kenarin_altinda', lambda a, u, y: y * (1 - 1e-6)),
    ('yakin_ust_kenara_tam_esit', lambda a, u, y: y),
    ('yakin_ust_kenarin_ustunde', lambda a, u, y: y * (1 + 1e-6)),
    ('ust_sinira_tam_esit', lambda a, u, y: u),
    ('ust_sinirin_ustunde', lambda a, u, y: u * (1 + 1e-6)),
)


@pytest.mark.parametrize('ad,uret', S4_NOKTALAR, ids=[n[0] for n in S4_NOKTALAR])
def test_s5_s4_siniflandirici_kenarlari(ad, uret):
    from hrma.engines.injector_design import classify_orifice_d
    alt, ust, yakin = _bant_ve_yakin_kenar()
    d = uret(alt, ust, yakin)
    assert classify_orifice_d(d, alt, ust) == _beklenen_sinif(
        d, alt, ust, yakin), (ad, d)


def test_s5_s4_yakinlik_payi_adlandirilmis_ve_beyanli():
    """Yakınlık eşiği adlandırılmış sabit; künyesi HRMA seçimi olduğunu
    ve literatür değeri OLMADIĞINI söyler (uydurma künye yok)."""
    from hrma.engines import injector_design as e
    assert 0.0 < e.ORIFICE_D_NEAR_LOWER_EDGE_FRAC < 1.0
    assert 'HRMA choice' in e.ORIFICE_D_NEAR_LOWER_EDGE_BASIS
    assert 'no literature value' in e.ORIFICE_D_NEAR_LOWER_EDGE_BASIS
    # İkinci literal kopya yok: payın sayısı engines dosyasında bir kez.
    atamalar = re.findall(r'^ORIFICE_D_NEAR_LOWER_EDGE_FRAC\s*=\s*([0-9.]+)\s*$',
                          _oku(ENGINES_INJ), re.M)
    assert [float(x) for x in atamalar] == [e.ORIFICE_D_NEAR_LOWER_EDGE_FRAC]


@pytest.mark.parametrize('ad,uret', S4_NOKTALAR[:6],
                         ids=[n[0] for n in S4_NOKTALAR[:6]])
def test_s5_s4_devre_plani_sinifa_gore_uyarir(ad, uret):
    """Tek delik penceresi: varsayılan kısıtla devre çözücüsünün uyarı kodu
    çapın sınıfından. Çap ürünün bağıntısıyla değil testte alandan geri
    hesaplanır; sınıf testin kendi tanımından."""
    from hrma.engines.injector_design import (_plan_orifices,
                                              DEFAULT_CONSTRAINTS)
    alt, ust, yakin = _bant_ve_yakin_kenar()
    d1 = uret(alt, ust, yakin) * 1e-3
    alan = np.pi * d1 ** 2 / 4.0
    d_tek = float(np.sqrt(4.0 * alan / np.pi)) * 1e3
    sinif = _beklenen_sinif(d_tek, alt, ust, yakin)
    beklenen = {
        'below_band': ['warn.injector.orifice_d_below_manufacturing_band'],
        'near_lower_edge': ['warn.injector.orifice_d_near_manufacturing_min'],
        'in_band': [],
    }[sinif]
    for kisit in (dict(DEFAULT_CONSTRAINTS), {}):
        uyarilar = []
        n, d = _plan_orifices(alan, kisit, uyarilar)
        assert n == 1, (ad, n)
        assert [w['code'] for w in uyarilar] == beklenen, (ad, d_tek, uyarilar)
        for w in uyarilar:
            assert (w['params']['d_min_mm'], w['params']['d_max_mm']) == (
                alt, ust), w


def test_s5_s4_yakin_sinifi_yalniz_bant_icinde_cagiran_kisitiyla():
    """Çağıranın geniş kısıtıyla (0,3-3,0) çap tercih bandının altında ama
    çağıranın bandının İÇİNDE: ``orifice_d_below_pref_band`` artık "alt sınıra
    yakın" demez; yakınlık yalnız çağıranın alt kenarına yakınsa ayrı kodla."""
    from hrma.engines.injector_design import (_plan_orifices,
                                              ORIFICE_D_NEAR_LOWER_EDGE_FRAC)
    kisit = {'d_min_mm': 0.3, 'd_max_mm': 3.0}
    for d1_mm, yakin_mi in ((0.4, False), (0.32, True)):
        assert (d1_mm < kisit['d_min_mm'] * (
            1 + ORIFICE_D_NEAR_LOWER_EDGE_FRAC)) is yakin_mi
        alan = np.pi * (d1_mm * 1e-3) ** 2 / 4.0
        uyarilar = []
        n, d = _plan_orifices(alan, dict(kisit), uyarilar)
        assert n == 1 and d * 1e3 == pytest.approx(d1_mm, rel=1e-12)
        kodlar = [w['code'] for w in uyarilar]
        assert kodlar[0] == 'warn.injector.orifice_d_below_pref_band', kodlar
        assert ('warn.injector.orifice_d_near_manufacturing_min'
                in kodlar) is yakin_mi, kodlar
        assert 'warn.injector.orifice_d_below_manufacturing_band' not in kodlar


I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'


def _i18n_iki_dil(anahtar):
    """``i18n_common.js``te anahtarın EN (ilk) ve TR (ikinci) metni."""
    bul = re.findall(rf"^\s*'{re.escape(anahtar)}': '([^']*)',\s*$",
                     _oku(I18N_COMMON), re.M)
    assert len(bul) == 2, (anahtar, bul)
    return bul[0], bul[1]


def test_s5_s4_i18n_siniflar_iki_dilde_ayni_anlamda():
    yer = lambda m: sorted(re.findall(r'\{(\w+)\}', m))  # noqa: E731
    en, tr = _i18n_iki_dil('warn.injector.orifice_d_below_manufacturing_band')
    assert 'outside the manufacturing band' in en and 'below' in en
    assert 'imalat bandının' in tr and 'dışında' in tr and 'altında' in tr
    assert yer(en) == yer(tr) == ['d_max_mm', 'd_min_mm', 'd_mm']
    en, tr = _i18n_iki_dil('warn.injector.orifice_d_near_manufacturing_min')
    assert 'inside the manufacturing band' in en
    assert 'close to the manufacturing minimum' in en
    assert 'içinde' in tr and 'imalat alt sınırına yakın' in tr
    assert yer(en) == yer(tr) == ['d_max_mm', 'd_min_mm', 'd_mm', 'near_pct']
    # Eski anahtar artık "yakın" hükmü taşımaz (iki dilde birlikte).
    en, tr = _i18n_iki_dil('warn.injector.orifice_d_below_pref_band')
    assert 'close to' not in en and 'yakın' not in tr, (en, tr)
    assert yer(en) == yer(tr) == ['band_hi_mm', 'band_lo_mm', 'd_mm']


def test_s5_s4_api_injector_design_kucuk_alan_bant_disi_sinifi():
    """``/api/injector-design`` ṁ 0,004 (denetim-4 vakası): 1 × 0,4649 mm
    → bant dışı sınıfı; "yakın" metni yok."""
    from hrma.app import app
    from hrma.constants import ORIFICE_D_BAND_MM
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/api/injector-design', json={
            'motor_type': 'hybrid', 'injector_type': 'showerhead',
            'mdot_ox': 0.004, 'rho_ox': 1141.0, 'Pc_bar': 20.0,
            'dp_ratio_ox': 0.2})
    assert cevap.status_code == 200, cevap.get_json()
    d = cevap.get_json()['design']
    ox = d['ox_circuit']
    assert ox['n_orifices'] == 1 and ox['orifice_d_mm'] < ORIFICE_D_BAND_MM[0]
    kodlar = [w['code'] for w in d['warnings']]
    assert 'warn.injector.orifice_d_below_manufacturing_band' in kodlar
    assert 'warn.injector.orifice_d_below_pref_band' not in kodlar
    assert 'warn.injector.orifice_d_near_manufacturing_min' not in kodlar


def _devre_kodlari(o, out=None):
    """Yanıtta ``warn.injector.orifice_*`` kodlu devre uyarılarının kodları."""
    if out is None:
        out = []
    if isinstance(o, dict):
        k = o.get('code')
        if isinstance(k, str) and k.startswith('warn.injector.orifice_d_'):
            out.append(k)
        for v in o.values():
            _devre_kodlari(v, out)
    elif isinstance(o, list):
        for v in o:
            _devre_kodlari(v, out)
    return out


@app_yamasi_bekleniyor
@pytest.mark.parametrize('itki', (14.0, 16.0, 18.0))
def test_s5_s4_ayni_yanitta_devre_ve_plaka_ayni_sinif(itki):
    """Hibrit duş başlığı 14/16/18 N (denetim-4: H16 devre 0,47 mm "yakın",
    plaka "bant dışı"). Devre sınıfı ile plaka hükmü aynı sınıflandırıcıdan:
    çap bandın altında → devre ``orifice_d_below_manufacturing_band`` ve
    plaka "outside the manufacturing band"; "yakın" kodu hiçbir yerde yok."""
    from hrma.app import app
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=dict(ORNEK_H1, thrust=itki))
    assert cevap.status_code == 200, cevap.get_json()
    j = cevap.get_json()
    d = j['injector']['hole_diameter']
    assert d < alt
    kodlar = set(_devre_kodlari(j['motor']))
    assert kodlar == {'warn.injector.orifice_d_below_manufacturing_band'}, kodlar
    plaka = [w for w in j['injector']['warnings']
             if 'manufacturing band' in w]
    assert len(plaka) == 1 and plaka[0].startswith(
        f'Solved orifice diameter {d:.4f} mm is outside the manufacturing '
        f'band ({alt:.2f}-{ust:.2f} mm)'), plaka


@pytest.mark.parametrize('mr', (6.0, 8.0))
def test_s5_s4_sivi_100N_devre_bant_disi_sinifi(mr):
    """Sıvı 100 N Pc 60 bar (denetim-4: yakıt devresi 0,46 mm "yakın"
    diyordu). Sıvı yanıtında plaka metni yok; devre hükmü bant dışı."""
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate_liquid', json={
            'motor_name': 'S5A', 'thrust': 100.0, 'chamber_pressure': 60.0,
            'mixture_ratio': mr, 'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'expansion_ratio': 8.0})
    assert cevap.status_code == 200, cevap.get_json()
    kodlar = set(_devre_kodlari(cevap.get_json()))
    assert kodlar == {'warn.injector.orifice_d_below_manufacturing_band'}, kodlar


# ===========================================================================
# 5. tur · Ş-5 — istenen çift değişince teslim alanı, oran, hedef ve
# hesaplanan debi (ana model kararı (i), Astra danışmalı, §28-18)
# ===========================================================================
# Denetim-4: I50 element_pairs 3/4'te "re-solved to 2 to preserve the target
# flow rate" yazılıyordu; teslim alanı istenenin 2,076 katı, ΔP tasarım
# değerinde kaldığı için hedef debi DOĞRULANMIYOR. Beklenen sayılar ürün
# kodu kullanılmadan alan korunumundan ve orifis bağıntısından türetilir.

def _carpismali_istenen(mdot, cift):
    import contextlib
    import io
    from hrma.utils.injector_design import InjectorDesign
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        inj = InjectorDesign(mdot_ox=mdot, chamber_pressure=20.0,
                             pressure_drop=4.0, injector_type='impingement')
        inj.set_impingement_params(n_pairs=cift)
        return inj, inj.calculate()


def _teslim_beklenen(inj, mdot, cift_teslim):
    from hrma.constants import ORIFICE_D_BAND_MM
    dp = inj.delta_P_inj * 1e5
    a_req = mdot / (inj.C_d * np.sqrt(2.0 * inj.rho_ox * dp))
    a_tes = 2 * cift_teslim * np.pi * (ORIFICE_D_BAND_MM[0] * 1e-3) ** 2 / 4.0
    r = a_tes / a_req
    return {
        'a_req': a_req, 'a_tes': a_tes, 'r': r,
        'v': mdot / (inj.rho_ox * a_tes),
        'mdot_dp': inj.C_d * a_tes * np.sqrt(2.0 * inj.rho_ox * dp),
    }


def _teslim_cumlesi_iceriyor(w, b, mdot, dp_bar):
    assert (f"Delivered injection area {b['a_tes'] * 1e6:.4g} mm^2 against "
            f"{b['a_req'] * 1e6:.4g} mm^2 required: {b['r']:.2f}x (area "
            f"{(b['r'] - 1) * 100:.0f}% larger)") in w, w
    assert f'Target flow {mdot:.4g} kg/s' in w, w
    assert f"exit velocity at the target flow {b['v']:.4g} m/s" in w, w
    assert (f"At the published pressure drop ({dp_bar:.4g} bar) the orifice "
            f"equation gives {b['mdot_dp']:.4g} kg/s ({b['r']:.2f}x the "
            f"target)") in w, w
    assert 'not verified at this pressure drop' in w, w
    assert 'preserve' not in w, w


#: (ṁ kg/s, istenen çift, tabanın bağlaması) — ṁ 0,005: 2 çiftte 0,29 mm
#: (istenen 3/4 → taban max(2, …) bağlar); ṁ 0,02: 2 çiftte 0,57 mm, istenen
#: 8 → 0,285 mm, ⌈A/(2a)⌉ = 3 > 2 (taban bağlamaz).
S5_ISTENEN_DEGISEN = ((0.005, 3, True), (0.005, 4, True), (0.02, 8, False))


@pytest.mark.parametrize('mdot,cift,taban_baglar', S5_ISTENEN_DEGISEN)
def test_s5_s5_istenen_cift_degisince_teslim_yayimlanir(mdot, cift,
                                                         taban_baglar):
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    inj, r = _carpismali_istenen(mdot, cift)
    dp = inj.delta_P_inj * 1e5
    a_req = mdot / (inj.C_d * np.sqrt(2.0 * inj.rho_ox * dp))
    a_delik = np.pi * (alt * 1e-3) ** 2 / 4.0
    tavan = int(np.ceil(a_req / (2.0 * a_delik)))
    assert (tavan < 2) is taban_baglar, tavan
    teslim = max(2, tavan)
    assert teslim != cift
    assert (r['n_pairs'], r['hole_diameter']) == (
        teslim, pytest.approx(alt, rel=1e-12))
    b = _teslim_beklenen(inj, mdot, teslim)
    assert r['injection_area'] == pytest.approx(b['a_tes'] * 1e6, rel=1e-12)
    assert r['exit_velocity'] == pytest.approx(b['v'], rel=1e-12)
    yeniden = [w for w in r['warnings'] if 're-solved' in w]
    assert len(yeniden) == 1, r['warnings']
    w = yeniden[0]
    assert w.startswith(f'Requested {cift} doublet pairs would need'), w
    assert (f're-solved to {teslim} pairs of {alt:.2f} mm holes.') in w, w
    _teslim_cumlesi_iceriyor(w, b, mdot, inj.delta_P_inj)
    if taban_baglar:
        assert b['r'] > 1.5, b['r']


@pytest.mark.parametrize('cift', (0, 2))
def test_s5_s5_s6a_korunan_ve_otomatik_yolun_etiketi(cift):
    """Ş-6 (a): istenen çiftin KORUNDUĞU yol (2 çift istendi, 2 teslim)
    'Requested 2 …' ile, otomatik yol 'The auto-selected minimum of 2 …' ile
    başlar — E1 / D4-M1 mutasyonu (korunan yola otomatik etiketi basmak)
    burada KIRMIZI olur. İkisinde de Ş-5 teslim cümlesi var."""
    mdot = 0.005
    inj, r = _carpismali_istenen(mdot, cift)
    kirpma = [w for w in r['warnings'] if 'clamped to' in w]
    assert len(kirpma) == 1, r['warnings']
    w = kirpma[0]
    if cift:
        assert w.startswith(f'Requested {cift} doublet pairs would need'), w
        assert 'auto-selected' not in w, w
    else:
        assert w.startswith('The auto-selected minimum of 2 doublet pairs'), w
    assert not any('re-solved' in u for u in r['warnings'])
    _teslim_cumlesi_iceriyor(w, _teslim_beklenen(inj, mdot, 2), mdot,
                             inj.delta_P_inj)


@app_yamasi_bekleniyor
@pytest.mark.parametrize('itki,cift,teslim,capa', (
    # 10. tur (HB9 devir 45; dört koşul): oran 2,055 plaka 293,00 K iken;
    # kâhin A_teslim/A_gerek, ρ = CoolProp(293,15 K) → 2,053965.
    (50.0, 3, 2, '2.05x (area 105% larger)'),
    (50.0, 4, 2, '2.05x (area 105% larger)'),
    (200.0, 8, 4, None),
))
def test_s5_s5_calculate_istenen_cift_vakalari(itki, cift, teslim, capa):
    """``/calculate`` Ornek-H1 çarpışmalı (denetim-4 vakaları I50 e3/e4,
    I200 e8). Çapa: I50'de ölçülen oran 2,055 → "2.06x (area 106% larger)"
    (8. tur: B16'lı taban; önceki tabanda 2,076 → "2.08x").
    Teslim alanı ve hız cümlede yanıtın KENDİ yapraklarıyla aynı."""
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=dict(
            ORNEK_H1, thrust=itki, injector_type='impingement',
            element_pairs=cift, **KANON_DISI_DP))
    assert cevap.status_code == 200, cevap.get_json()
    inj = cevap.get_json()['injector']
    assert inj['n_pairs'] == teslim
    yeniden = [w for w in inj['warnings'] if 're-solved' in w]
    assert len(yeniden) == 1, inj['warnings']
    w = yeniden[0]
    assert f"Delivered injection area {inj['injection_area']:.4g} mm^2" in w
    assert f"exit velocity at the target flow {inj['exit_velocity']:.4g} m/s" in w
    assert 'preserve' not in w and 'not verified' in w, w
    if capa:
        assert capa in w, w


# ===========================================================================
# 5. tur · Ş-6 (b) — çağıranın bandının künyesi 'caller-supplied …'
# ===========================================================================
@pytest.mark.parametrize('kisit,cagiran', (
    (None, False),
    ({'d_min_mm': 0.3, 'd_max_mm': 3.0}, True),
    ({'d_min_mm': 0.3}, True),
    ({'n_max': 60}, False),
))
def test_s5_s6b_orifice_band_kunyesi_cagirana_gore(kisit, cagiran):
    """E8 mutasyonu (çağıranın bandına Sutton/Mishra künyesi basmak) burada
    KIRMIZI olur: çağıranın bandı kaynaklı bant DEĞİLDİR."""
    from hrma.constants import ORIFICE_D_BAND_MM, ORIFICE_D_BAND_SOURCE
    from hrma.engines.injector_design import design_injector
    spec = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
            'mdot_ox': 0.05, 'rho_ox': 1141.0, 'Pc_bar': 20.0,
            'dp_ratio_ox': 0.2}
    if kisit is not None:
        spec['orifice_constraints'] = kisit
    bant = design_injector(spec)['orifice_band']
    if cagiran:
        assert bant['source'].startswith('caller-supplied'), bant
        assert 'Sutton' not in bant['source'] and 'Mishra' not in bant['source']
        assert (bant['d_min_mm'], bant['d_max_mm']) != ORIFICE_D_BAND_MM
    else:
        assert bant['source'] == ORIFICE_D_BAND_SOURCE, bant
        assert (bant['d_min_mm'], bant['d_max_mm']) == ORIFICE_D_BAND_MM


# ===========================================================================
# 6. tur · Ş5-1 / Ş5-2 — yayımlanan yakınlık penceresinin DAVRANIŞ bekçisi
# (yeniden denetim-5, 8 Eki 2026)
# ===========================================================================
# Denetim-5 bulgusu (D5-M3, D5-M6b YEŞİL kaldı): Ş-4 testleri yakınlık payını
# ``ORIFICE_D_NEAR_LOWER_EDGE_FRAC``in KENDİSİNDEN türetiyordu; payı 0,10 →
# 0,15 yapmak hiçbir bekçiyi kırmıyordu. Oysa pay YAYIMLANAN bir uyarı
# penceresidir (Sunum 2, ``berke_onay_A2.md`` F-10 üçüncü tablo). Aşağıdaki
# vakalar payı ürün sabitinden OKUMAZ: her biri ürünün kendi yanıtından
# ölçülmüş bir plan (n × d) ve o planın yayımlanan hükmüdür ("yakın" uyarısı
# VAR / YOK). Çaplar Sunum 2 satırlarıyla aynı ölçümden (main 24b3e488 ⟷ dal
# + F10 + W4B; plan iki ağaçta bit-aynı, yalnız uyarı kanalı değişir;
# kanıt docs/scofield/raw/OH/A2/hibrit/a1/sart6/). Kenar çifti (ṁ 0,00557 /
# 0,00562 kg/s) pencerenin ÜST KENARINI 0,5486 ile 0,5510 mm arasına
# sıkıştırır (0,55 mm'ye göre yaklaşık −%0,25 / +%0,18); pay cinsinden bu
# 0,0972 < f ≤ 0,1021 aralığıdır (yaklaşık −%2,8 / +%2,1). Bu aralığın
# dışına çıkan her pay bu tabloda KIRMIZI olur (ters mutasyonlar 0,10 → 0,15
# ve 0,10 → 0,05: mutasyon.md "6. tur"; denetim-6 0,095 / 0,105). [7. tur:
# yorumun kalibrasyon cümlesi denetim-6'nın "küçük, belge doğruluğu"
# maddesine göre düzeltildi; ölçüt değişmedi.]
#
# 7. tur (Ş6-1 + Ş6-3): sapma listesi yayımlanan ``near_pct``i LİTERAL 10 ile
# ölçer (ürün sabitinden TÜRETİLMEZ; kaynak Sunum 2 F-10 üçüncü tablo, 6. tur
# sabit-n satırı "near_pct 10" ve 7. tur Ş6-3 satırı). Uyarının ``d_mm``
# parametresi 7. turdan beri planın 4 ondalıklı çapıdır (Ş6-3: iki ondalık
# 0,55 gösterimi "less than 10 percent above" metniyle çelişiyordu); beklenen
# değer tablodaki ölçülmüş çaptır (aynı Sunum satırları).
SUNUM_NEAR_PCT = 10

_API_HIBRIT_DUS = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
                   'rho_ox': 1141.0, 'Pc_bar': 20.0, 'dp_ratio_ox': 0.2}
_SIVI_S6 = {'motor_name': 'S6', 'chamber_pressure': 60.0,
            'mixture_ratio': 6.0, 'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'expansion_ratio': 8.0}
_YOL_CALCULATE_OX = ('motor', 'injector_design_detail', 'ox_circuit')
_YOL_API_OX = ('design', 'ox_circuit')
_YOL_SIVI_YAKIT = ('injection_system', 'injector_design_detail',
                   'fuel_circuit')

#: Arama yolu (``_plan_orifices`` n_fixed'siz; son ``_near_lower_edge_warning``
#: çağrısı). (ad, uç, yük, devre yolu, n, ölçülen d [mm], 'yakın' uyarısı?)
S6_YAKINLIK_ARAMA = (
    ('H20', '/calculate', dict(ORNEK_H1, thrust=20.0), _YOL_CALCULATE_OX,
     1, 0.5243, True),  # v3.0.1 port kulvarı: 0,5240 -> 0,5243
    ('H24', '/calculate', dict(ORNEK_H1, thrust=24.0), _YOL_CALCULATE_OX,
     1, 0.5743, False),  # v3.0.1 port kulvarı: 0,5740 -> 0,5743
    ('api_0.005', '/api/injector-design', dict(_API_HIBRIT_DUS, mdot_ox=0.005),
     _YOL_API_OX, 1, 0.5198, True),
    ('api_0.00557', '/api/injector-design',
     dict(_API_HIBRIT_DUS, mdot_ox=0.00557), _YOL_API_OX, 1, 0.5486, True),
    ('api_0.00562', '/api/injector-design',
     dict(_API_HIBRIT_DUS, mdot_ox=0.00562), _YOL_API_OX, 1, 0.5510, False),
)

#: Sabit-n yolu (``_plan_orifices(n_fixed=…)``; erken dönüşteki
#: ``_near_lower_edge_warning`` çağrısı) — çağıran delik sayısını verir:
#: ``/api/injector-design`` ``n_orifices_ox``, sıvı ``injector_elements``.
S6_YAKINLIK_SABIT_N = (
    ('api_n2_0.01', '/api/injector-design',
     dict(_API_HIBRIT_DUS, mdot_ox=0.01, n_orifices_ox=2), _YOL_API_OX,
     2, 0.5198, True),
    ('api_n2_0.012', '/api/injector-design',
     dict(_API_HIBRIT_DUS, mdot_ox=0.012, n_orifices_ox=2), _YOL_API_OX,
     2, 0.5694, False),
    ('sivi_250N_e2', '/calculate_liquid',
     dict(_SIVI_S6, thrust=250.0, injector_elements=2), _YOL_SIVI_YAKIT,
     2, 0.5181, True),
    ('sivi_300N_e2', '/calculate_liquid',
     dict(_SIVI_S6, thrust=300.0, injector_elements=2), _YOL_SIVI_YAKIT,
     2, 0.5671, False),
)

_YAKIN_KODU = 'warn.injector.orifice_d_near_manufacturing_min'


def _plan_kodlari(o, out=None):
    """Yanıtta delik planına ait uyarıların (kod, parametreler) listesi:
    ``warn.injector.orifice_d_*`` ve ``warn.injector.fixed_n_*``."""
    if out is None:
        out = []
    if isinstance(o, dict):
        k = o.get('code')
        if isinstance(k, str) and k.startswith(('warn.injector.orifice_d_',
                                                'warn.injector.fixed_n_')):
            out.append((k, o.get('params') or {}))
        for v in o.values():
            _plan_kodlari(v, out)
    elif isinstance(o, list):
        for v in o:
            _plan_kodlari(v, out)
    return out


def _yakinlik_olc(uc, yuk, yol):
    """Uçtan yanıt al; devrenin planı (n, d [mm]) ve delik planı uyarıları."""
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post(uc, json=dict(yuk))
    j = cevap.get_json()
    if cevap.status_code != 200:
        return {'http': cevap.status_code, 'yanit': j}
    devre = j
    for k in yol:
        devre = devre[k]
    kapsam = j['motor'] if uc == '/calculate' else j
    return {'http': 200, 'n': devre['n_orifices'], 'd': devre['orifice_d_mm'],
            'kodlar': _plan_kodlari(kapsam)}


def _yakinlik_farklari(o, n_bek, d_bek, yakin_mi):
    """Ölçülen vakanın yayımlanan hükümden sapmaları (boş liste = uyumlu)."""
    from hrma.constants import ORIFICE_D_BAND_MM
    alt, ust = ORIFICE_D_BAND_MM
    if o['http'] != 200:
        return ['HTTP %s: %s' % (o['http'], o.get('yanit'))]
    fark = []
    n, d = o['n'], o['d']
    # Plan ölçülen (yayımlanan) planla aynı; vaka pencerede beklenen yerde.
    if n != n_bek or abs(d - d_bek) > 5e-5:
        fark.append('plan %s × %s ≠ %s × %s' % (n, d, n_bek, d_bek))
    if not alt <= d <= ust:
        fark.append('çap bandın dışında: %s' % d)
    beklenen = {_YAKIN_KODU} if yakin_mi else set()
    if {k for k, _ in o['kodlar']} != beklenen:
        fark.append('uyarı kodları %s ≠ %s' % (o['kodlar'], beklenen))
    for k, p in o['kodlar']:
        # 7. tur Ş6-3: d_mm = Sunum satırının 4 ondalıklı ölçülmüş çapı
        # (eskiden round(d, 2) idi; 0,5469 → 0,55 metni kendiyle çelişiyordu).
        if p.get('d_mm') != d_bek or (
                p.get('d_min_mm'), p.get('d_max_mm')) != (alt, ust):
            fark.append('uyarı parametresi %s %s (d = %s)' % (k, p, d))
        # 7. tur Ş6-1: yayımlanan pencere yüzdesi LİTERAL (Sunum 2 F-10
        # üçüncü tablo); ürün sabitinden türetilmez (D6D-M3 dersi).
        if k == _YAKIN_KODU and p.get('near_pct') != SUNUM_NEAR_PCT:
            fark.append('near_pct %s ≠ Sunum 2 değeri %s'
                        % (p.get('near_pct'), SUNUM_NEAR_PCT))
    return fark


@pytest.mark.parametrize('ad,uc,yuk,yol,n,d,yakin_mi', S6_YAKINLIK_ARAMA,
                         ids=[v[0] for v in S6_YAKINLIK_ARAMA])
def test_s6_s51_yayimlanan_yakinlik_penceresi_arama_yolu(ad, uc, yuk, yol, n,
                                                         d, yakin_mi):
    """Ş5-1: H20 (1 × 0,5243) ve api ṁ 0,005 (1 × 0,5198) 'yakın' uyarısı
    ALIR, H24 (1 × 0,5743) ALMAZ; kenar çifti pencerenin üst kenarını
    0,5486-0,5510 mm arasına sabitler."""
    o = _yakinlik_olc(uc, yuk, yol)
    assert not _yakinlik_farklari(o, n, d, yakin_mi), (ad, o)


@pytest.mark.parametrize('ad,uc,yuk,yol,n,d,yakin_mi', S6_YAKINLIK_SABIT_N,
                         ids=[v[0] for v in S6_YAKINLIK_SABIT_N])
def test_s6_s52_sabit_n_yolunda_yakinlik_uyarisi(ad, uc, yuk, yol, n, d,
                                                 yakin_mi):
    """Ş5-2: çağıran delik sayısını verdiğinde (``n_orifices_ox`` /
    ``injector_elements``) yakınlık hükmü sabit-n dönüşünden basılır. D5-M6b
    (o çağrıyı satır sayısını koruyarak düşürmek) burada KIRMIZI olur.
    Sıvıda uyarının yakıt devresine ait olduğunu parametresindeki çap
    (``d_mm`` = yakıt devresinin çapı) gösterir."""
    o = _yakinlik_olc(uc, yuk, yol)
    assert not _yakinlik_farklari(o, n, d, yakin_mi), (ad, o)


def test_s6_s52_ayni_alan_arama_yolunda_yakin_degil():
    """Sabit-n vakasının (api ṁ 0,01, n = 2 → 2 × 0,5198 mm) uyarısı yalnız
    sabit-n yolundan gelebilir: aynı istek delik sayısı verilmeden arama
    yoluna düşer, n = 1 ve çap pencerenin dışında kalır (1 × 0,7350 mm)."""
    o = _yakinlik_olc('/api/injector-design',
                      dict(_API_HIBRIT_DUS, mdot_ox=0.01), _YOL_API_OX)
    assert not _yakinlik_farklari(o, 1, 0.7350, False), o


# ===========================================================================
# 7. tur — karar §28-25 Astra şartları + yeniden denetim-6 Ş6-1…Ş6-3
# (12 Eki 2026). Kanıt: docs/scofield/raw/OH/A2/hibrit/a1/sart7/.
# ===========================================================================
# Madde 1: kırpılmış ve hedef debiyi tutmayan plana olumlu hüküm yok.
# Madde 2 / Ş6-3: yakınlık penceresi "HRMA sezgisel uyarı eşiği" diye
#   yanıtta ve metinde; d_mm gösterimi metinle çelişmez.
# Madde 3 (YB-04): N₂O kipinde tank_pressure formda salt-okur; API sapma
#   uyarısı (istek reddedilmez).
# Beklenen sayılar ürün kodu kullanılmadan alan korunumu ve orifis
# bağıntısından; yayımlanan paylar Sunum 2 7. tur satırlarından LİTERAL
# (ürün sabitinden türetilmez — D6D-M3 dersi).

ADV_HTML = KOK / 'hrma' / 'templates' / 'advanced.html'
I18N_ADV = KOK / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'
HB7_YAMASI = ('docs/scofield/raw/OH/A2/hibrit/a1/patch/'
              'HB7_app_hibrit_uyari_gecisi.patch')

#: Sunum 2 7. tur: kırpılmış planın hedef debi toleransı (HRMA seçimi).
SUNUM_HEDEF_DEBI_PAYI = 0.05
#: Sunum 2 7. tur YB-04: tank basıncı ⟷ P_sat sapma payı (HRMA seçimi).
SUNUM_TANK_PSAT_PAYI = 0.02
_HEDEF_KODU = 'warn.injector.target_flow_not_met'
_TANK_KODU = 'warn.hybrid.tank_pressure_not_used'
_N2O_DOYMA = 'n2o_saturation_at_tank_temperature'


def _hb7_yamasi_uygulanmadi() -> bool:
    """app.py 7. tur uyarı geçişlerini taşıyor mu? (yama ``HB7_YAMASI``)"""
    metin = _oku(APP_PY)
    return ('withhold_validation_pass_for_target_flow' not in metin
            or 'tank_pressure_not_used_warning' not in metin)


hb7_yamasi_bekleniyor = pytest.mark.xfail(
    condition=_hb7_yamasi_uygulanmadi(), strict=True,
    reason='hrma/app.py 7. turda PATCH ile değişir (%s); yama uygulanmadan '
           'bu iddia kırmızıdır' % HB7_YAMASI)
hb7_ve_f10_bekleniyor = pytest.mark.xfail(
    condition=_hb7_yamasi_uygulanmadi() or _app_yamasi_uygulanmadi(),
    strict=True,
    reason='çarpışmalı /calculate bandı F10 yamasıyla (0,5-2,5), hüküm geçişi '
           'HB7 yamasıyla gelir; ikisi uygulanmadan bu iddia kırmızıdır')


def _utils_plan(tip, mdot, n):
    """utils ``InjectorDesign`` doğrudan (ΔP 4 bar, Pc 20 bar, N₂O)."""
    import contextlib
    import io
    from hrma.utils.injector_design import InjectorDesign
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        inj = InjectorDesign(mdot_ox=mdot, chamber_pressure=20.0,
                             pressure_drop=4.0, injector_type=tip)
        if tip == 'showerhead':
            inj.set_showerhead_params(n_holes=n)
        else:
            inj.set_impingement_params(n_pairs=n)
        return inj, inj.calculate()


def _hedef_debi_olc(inj, r):
    """Yayımlanan plandan (n × d) bağımsız yol: teslim alanı, ṁ_ΔP, oran."""
    a_teslim = r['n_holes'] * np.pi * (r['hole_diameter'] * 1e-3) ** 2 / 4.0
    dp = inj.delta_P_inj * 1e5
    a_gerekli = inj.mdot_ox / (inj.C_d * np.sqrt(2.0 * inj.rho_ox * dp))
    mdot_dp = inj.C_d * a_teslim * np.sqrt(2.0 * inj.rho_ox * dp)
    return {'a_teslim': a_teslim, 'a_gerekli': a_gerekli, 'mdot_dp': mdot_dp,
            'oran': mdot_dp / inj.mdot_ox}


#: (ad, tip, ṁ kg/s, istenen n/çift, kırpıldı mı, hedef karşılanmıyor mu) —
#: ölçüldü (sart7/olc7.py): çarpışmalı ṁ 0,005 istenen/korunan/otomatik
#: 3,07×; ṁ 0,02 e8 1,15×; duş başlığı ṁ 0,5 n 4 1,15×, ṁ 0,01 otomatik
#: 1,54×; duş başlığı ṁ 0,5 n 150 KIRPILIR ama hedefi tolerans içinde tutar.
S7_PLANLAR = (
    ('imp_m0.005_e3', 'impingement', 0.005, 3, True, True),
    ('imp_m0.005_e2', 'impingement', 0.005, 2, True, True),
    ('imp_m0.005_oto', 'impingement', 0.005, 0, True, True),
    ('imp_m0.02_e8', 'impingement', 0.02, 8, True, True),
    ('imp_m0.02_oto', 'impingement', 0.02, 0, False, False),
    ('sh_m0.5_n4', 'showerhead', 0.5, 4, True, True),
    ('sh_m0.01_oto', 'showerhead', 0.01, 0, True, True),
    ('sh_m0.5_n150', 'showerhead', 0.5, 150, True, False),
    ('sh_m0.5_oto', 'showerhead', 0.5, 0, False, False),
)


def _hedef_debi_farklari(inj, r, kirpildi, karsilanmiyor):
    """Planın hedef debi sınıfının yayımlanan hükümden sapmaları."""
    fark = []
    o = _hedef_debi_olc(inj, r)
    kirpma_izi = any(('clamped' in w or 're-solved' in w)
                     for w in r['warnings'] if isinstance(w, str))
    if kirpma_izi is not kirpildi:
        fark.append('kırpma izi %s ≠ beklenen %s' % (kirpma_izi, kirpildi))
    if bool(abs(o['oran'] - 1.0) > SUNUM_HEDEF_DEBI_PAYI) is not karsilanmiyor:
        fark.append('bağımsız oran %.4f ≠ beklenen sınıf' % o['oran'])
    tfc = r.get('target_flow_check')
    if not karsilanmiyor:
        if 'target_flow_check' in r:
            fark.append('hedefi tutan/kırpılmayan planda alan var: %s' % tfc)
        return fark
    if not isinstance(tfc, dict) or tfc.get('status') != 'target_flow_not_met':
        return fark + ['sınıf yok: %s' % tfc]
    if tfc['ratio'] != pytest.approx(o['oran'], rel=1e-9):
        fark.append('oran %s ≠ %s' % (tfc['ratio'], o['oran']))
    if tfc['mdot_at_published_dp_kg_s'] != pytest.approx(o['mdot_dp'], rel=1e-9):
        fark.append('ṁ_ΔP %s ≠ %s' % (tfc['mdot_at_published_dp_kg_s'],
                                      o['mdot_dp']))
    if tfc['target_mdot_kg_s'] != pytest.approx(inj.mdot_ox, rel=1e-12):
        fark.append('hedef ṁ %s' % tfc['target_mdot_kg_s'])
    if tfc['relative_tolerance'] != SUNUM_HEDEF_DEBI_PAYI:
        fark.append('pay %s ≠ Sunum 2 değeri' % tfc['relative_tolerance'])
    for parca in ('HRMA choice', 'no literature value', 'NOT re-solved'):
        if parca not in tfc['tolerance_basis']:
            fark.append('künyede yok: %s' % parca)
    return fark


@pytest.mark.parametrize('ad,tip,mdot,n,kirpildi,karsilanmiyor', S7_PLANLAR,
                         ids=[v[0] for v in S7_PLANLAR])
def test_s7_m1_kirpilmis_plan_hedef_debi_sinifi(ad, tip, mdot, n, kirpildi,
                                                karsilanmiyor):
    """Madde 1: kırpılıp yayımlanan ΔP'de hedeften toleransın ötesinde sapan
    plan ``target_flow_not_met`` sınıfı alır; kırpılmayan ya da hedefi tutan
    planda alan HİÇ yoktur (yanıt bit-aynı). D7-M1/M2/M11 burada KIRMIZI."""
    inj, r = _utils_plan(tip, mdot, n)
    assert not _hedef_debi_farklari(inj, r, kirpildi, karsilanmiyor), (ad, r)


def test_s7_m1_tolerans_adlandirilmis_ve_sunum_degerinde():
    from hrma.engines import injector_design as e
    assert e.CLAMPED_PLAN_TARGET_FLOW_REL_TOL == SUNUM_HEDEF_DEBI_PAYI
    assert 'HRMA choice' in e.CLAMPED_PLAN_TARGET_FLOW_TOL_BASIS
    assert 'no literature value' in e.CLAMPED_PLAN_TARGET_FLOW_TOL_BASIS
    atamalar = re.findall(
        r'^CLAMPED_PLAN_TARGET_FLOW_REL_TOL\s*=\s*([0-9.]+)\s*$',
        _oku(ENGINES_INJ), re.M)
    assert [float(x) for x in atamalar] == [SUNUM_HEDEF_DEBI_PAYI]


def test_s7_m1_dogrulama_ozeti_gecti_hukmunu_geri_ceker():
    """Kayıt doğrulama özetine kritik olarak geçer; sınıf yoksa rapor
    DOKUNULMAZ; üretilemeyen rapora dizi uydurulmaz. D7-M3 burada KIRMIZI."""
    import copy
    from hrma.utils.injector_design import (
        withhold_validation_pass_for_target_flow)
    taban = {'overall_status': {'code': 'status.normal', 'params': {},
                                'severity': 'info'},
             'critical_warnings': [], 'regular_warnings': [],
             'total_warnings': 0, 'validation_passed': True}
    inj, r = _utils_plan('impingement', 0.005, 3)
    o = _hedef_debi_olc(inj, r)
    rapor = copy.deepcopy(taban)
    kayit = withhold_validation_pass_for_target_flow(rapor, r)
    assert kayit is not None and kayit['code'] == _HEDEF_KODU
    assert kayit['severity'] == 'critical'
    assert kayit['params']['ratio'] == round(o['oran'], 3)
    assert kayit['params']['mdot_dp'] == round(o['mdot_dp'], 6)
    assert kayit['params']['tol_pct'] == round(SUNUM_HEDEF_DEBI_PAYI * 100)
    assert rapor['validation_passed'] is False
    assert rapor['overall_status']['code'] == 'status.critical'
    assert rapor['critical_warnings'] == [kayit]
    assert rapor['total_warnings'] == 1
    # Hedefi tolerans içinde tutan kırpılmış plan: rapor bit-aynı.
    _, r2 = _utils_plan('showerhead', 0.5, 150)
    rapor2 = copy.deepcopy(taban)
    assert withhold_validation_pass_for_target_flow(rapor2, r2) is None
    assert rapor2 == taban
    # Rapor üretilemediyse (not_evaluated) uyarı dizisi uydurulmaz.
    bos = {'status': 'not_evaluated', 'validation_passed': False}
    assert withhold_validation_pass_for_target_flow(bos, r) is None
    assert bos == {'status': 'not_evaluated', 'validation_passed': False}


#: /calculate Ornek-H1 çarpışmalı (Sunum 2 7. tur satırları): (itki N,
#: istenen çift (0 = otomatik), hedef karşılanmıyor mu, Sunum oranı).
S7_CALCULATE_KARSILANMIYOR = (
    # 10. tur (HB9 devir 45; dört koşul): 2,055 / 3,422 plaka 293,00 K iken;
    # kâhin ṁ(ΔP)/ṁ_hedef, ρ = CoolProp(293,15 K) → 2,053965 / 3,419515.
    # v3.0.1 port kulvarı: 2,054 -> 2,051 ve 3,42 -> 3,415 (ṁ +%0,17).
    (50.0, 3, 2.051), (50.0, 4, 2.051), (30.0, 0, 3.415),
)
#: Kırpılıp hedefi tolerans içinde tutan (Sunum oranı 1,04×) — bit-aynı.
S7_CALCULATE_KARSILANIYOR = ((200.0, 8), (100.0, 0))


#: Ornek-H1 devresinin ΔP'si [bar] (P_sat(293,15 K) − Pc; f10 çapası).
ORNEK_H1_DEVRE_DP_BAR = 30.5433585


def _calculate_carpismali(itki, cift, dp_ezme=False):
    from hrma.app import app
    yuk = dict(ORNEK_H1, thrust=itki, injector_type='impingement')
    if cift:
        yuk['element_pairs'] = cift
    if dp_ezme:
        # v3.0.1 E2: kanon yolunda (çözücü ΔP) ekran bloğu devrenin planını
        # TÜKETİR, kırpma olmaz. Kırpılmış plan sözleşmesi ΔP AÇIK ezmesi
        # yolunda yaşar (ekran bloğu kendi planlar). ΔP devrenin kendi
        # değeridir, yani oranlar kanon yoldaki eski ölçümle aynı kalır.
        yuk['pressure_drop_source'] = 'user'
        yuk['pressure_drop'] = ORNEK_H1_DEVRE_DP_BAR
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=yuk)
    assert cevap.status_code == 200, cevap.get_json()
    return cevap.get_json()


@hb7_ve_f10_bekleniyor
@pytest.mark.parametrize('itki,cift,oran', S7_CALCULATE_KARSILANMIYOR)
def test_s7_m1_calculate_kirpilmis_plan_gecti_almaz(itki, cift, oran):
    """Ornek-H1 çarpışmalı I50 e3/e4 ve I30 otomatik: doğrulama özeti
    ``validation_passed`` False, durum ``status.critical``, kritik kayıt
    tek ve oranı yanıtın ``target_flow_check``iyle aynı."""
    j = _calculate_carpismali(itki, cift, dp_ezme=True)
    tfc = j['injector'].get('target_flow_check')
    val = j['validation']
    kritik = [w for w in val['critical_warnings'] if w.get('code') == _HEDEF_KODU]
    assert tfc['status'] == 'target_flow_not_met'
    assert round(tfc['ratio'], 3) == oran
    assert val['validation_passed'] is False
    assert val['overall_status']['code'] == 'status.critical'
    assert len(kritik) == 1
    assert kritik[0]['params']['ratio'] == round(tfc['ratio'], 3)


@pytest.mark.parametrize('itki,cift', S7_CALCULATE_KARSILANIYOR)
def test_s7_m1_calculate_hedefi_tutan_kirpilmis_plan_bit_ayni(itki, cift):
    """I200 e8 / I100 otomatik (1,04×): sınıf yok, kritik kayıt yok."""
    j = _calculate_carpismali(itki, cift)
    assert 'target_flow_check' not in j['injector']
    assert not [w for w in j['validation']['critical_warnings']
                if w.get('code') == _HEDEF_KODU]


# ---------------------------------------------------------------------------
# Madde 2 / Ş6-3 — pencere "HRMA sezgisel uyarı eşiği"; metin kendiyle
# çelişmez.
# ---------------------------------------------------------------------------
def test_s7_m2_pencere_yanitta_hrma_sezgisel_esigi_diye_beyanli():
    """``orifice_band`` pencereyi ve künyesini yayımlar. D7-M5 KIRMIZI."""
    from hrma.engines.injector_design import design_injector
    bant = design_injector(dict(_API_HIBRIT_DUS, mdot_ox=0.05))['orifice_band']
    assert bant['near_lower_edge_fraction'] == SUNUM_NEAR_PCT / 100
    kunye = bant['near_lower_edge_basis']
    for parca in ('HRMA heuristic warning threshold', 'no literature value',
                  'NOT a manufacturing standard', 'NOT a safety limit',
                  '%d%%' % SUNUM_NEAR_PCT):
        assert parca in kunye, (parca, kunye)


def test_s7_m2_uyari_metni_iki_dilde_esigi_beyan_eder():
    """EN = TR: yer tutucular değişmedi, beyan iki dilde. D7-M10 KIRMIZI."""
    yer = lambda m: sorted(re.findall(r'\{(\w+)\}', m))  # noqa: E731
    en, tr = _i18n_iki_dil(_YAKIN_KODU)
    assert yer(en) == yer(tr) == ['d_max_mm', 'd_min_mm', 'd_mm', 'near_pct']
    assert 'HRMA heuristic warning threshold' in en
    assert 'not a manufacturing standard or a safety limit' in en
    assert 'HRMA sezgisel uyarı eşiği' in tr
    assert 'imalat standardı ya da güvenlik sınırı değildir' in tr


#: Ş6-3 kenar vakaları: ölçülen plan ve Sunum 2 satırındaki 4 ondalıklı çap.
S7_KENAR = (
    ('H22', '/calculate', dict(ORNEK_H1, thrust=22.0), _YOL_CALCULATE_OX,
     0.5499),  # v3.0.1 port kulvarı: 0,5496 -> 0,5499 (pencere içinde kalır)
    ('api_0.00557', '/api/injector-design',
     dict(_API_HIBRIT_DUS, mdot_ox=0.00557), _YOL_API_OX, 0.5486),
)


@pytest.mark.parametrize('ad,uc,yuk,yol,d_sunum', S7_KENAR,
                         ids=[v[0] for v in S7_KENAR])
def test_s7_s63_kenar_vakasinda_metin_kendiyle_celismez(ad, uc, yuk, yol,
                                                         d_sunum):
    """Metin "d=X mm ... inside (L-U) ... less than P percent above its lower
    limit": yayımlanan X için L ≤ X < L·(1 + P/100). Eski iki ondalıklı
    gösterim X = 0,55'i basıyordu (= L·1,1). D7-M4 burada KIRMIZI."""
    o = _yakinlik_olc(uc, yuk, yol)
    yakin = [p for k, p in o['kodlar'] if k == _YAKIN_KODU]
    assert yakin, (ad, o)
    for p in yakin:
        assert p['d_mm'] == d_sunum, p
        assert p['d_min_mm'] <= p['d_mm'] < p['d_min_mm'] * (
            1 + p['near_pct'] / 100.0), p


@pytest.mark.parametrize('d1_mm', (0.54996, 0.5499999, 0.549999999))
def test_s7_s63_pencere_ust_kenarinin_hemen_altinda_gosterim_kenara_cikmaz(
        d1_mm):
    """Tek delik penceresinin üst kenarına (0,55 mm) çok yakın çap: gösterim
    kenara yuvarlanmaz (ondalık sayısı artar)."""
    from hrma.engines.injector_design import _plan_orifices
    alan = np.pi * (d1_mm * 1e-3) ** 2 / 4.0
    uyarilar = []
    n, d = _plan_orifices(alan, {}, uyarilar)
    yakin = [w['params'] for w in uyarilar if w['code'] == _YAKIN_KODU]
    assert n == 1 and len(yakin) == 1, uyarilar
    p = yakin[0]
    assert p['d_min_mm'] <= p['d_mm'] < p['d_min_mm'] * (
        1 + p['near_pct'] / 100.0), p
    assert p['d_mm'] == pytest.approx(d1_mm, abs=1e-9)


def test_s7_s63_cagiranin_iki_ondalikli_bandi_gosterimde_korunur():
    """Çağıran bandı 0,35-3,0 mm: eski bir ondalıklı gösterim kenarı 0,3'e
    (ya da 0,4'e) çeviriyordu; metin 0,37 mm için "yüzde 10'dan az üstünde"
    derken 0,3'e göre %23 üstündeydi."""
    from hrma.engines.injector_design import _plan_orifices
    alan = np.pi * (0.37e-3) ** 2 / 4.0
    uyarilar = []
    n, d = _plan_orifices(alan, {'d_min_mm': 0.35, 'd_max_mm': 3.0}, uyarilar)
    yakin = [w['params'] for w in uyarilar if w['code'] == _YAKIN_KODU]
    assert n == 1 and len(yakin) == 1, uyarilar
    assert (yakin[0]['d_min_mm'], yakin[0]['d_max_mm']) == (0.35, 3.0)
    assert yakin[0]['d_min_mm'] <= yakin[0]['d_mm'] < 0.35 * 1.1


# ---------------------------------------------------------------------------
# Madde 3 — YB-04 (ana model kararı, §28-25)
# ---------------------------------------------------------------------------
def test_s7_yb04_sapma_uyarisi_islevi():
    """Pay LİTERAL (Sunum 2 7. tur); N₂O kipinde 80 bar uyarı, P_sat'a eşit
    ve pay içi değer uyarısız; başka kip ve okunamayan değer uyarısız.
    D7-M6 burada KIRMIZI."""
    from hrma.engines import hybrid_rocket_engine as h
    assert h.TANK_PRESSURE_PSAT_REL_TOL == SUNUM_TANK_PSAT_PAYI
    assert h.FEED_PRESSURE_SOURCE_N2O_SAT == _N2O_DOYMA
    p_sat = 50.5433585
    blok = {'feed_pressure_source': _N2O_DOYMA, 'feed_pressure_bar': p_sat}
    kayit = h.tank_pressure_not_used_warning(80.0, blok)
    assert kayit == {'code': _TANK_KODU, 'severity': 'warning', 'params': {
        'tank_pressure_bar': 80.0, 'feed_pressure_bar': round(p_sat, 3),
        'deviation_pct': round((80.0 - p_sat) / p_sat * 100, 1),
        'tol_pct': round(SUNUM_TANK_PSAT_PAYI * 100)}}
    # pay içi (Ornek-H1 50 bar: −%1,07) ve P_sat'a eşit: uyarı YOK
    assert h.tank_pressure_not_used_warning(p_sat, blok) is None
    assert h.tank_pressure_not_used_warning(50.0, blok) is None
    # payın hemen dışı iki yönde: uyarı VAR
    assert h.tank_pressure_not_used_warning(p_sat * 1.03, blok) is not None
    assert h.tank_pressure_not_used_warning(p_sat * 0.97, blok) is not None
    baska = dict(blok, feed_pressure_source=(
        'chamber_pressure_plus_design_pressure_drop'))
    assert h.tank_pressure_not_used_warning(80.0, baska) is None
    for kotu in (None, 'yirmi', float('nan'), float('inf'), -5.0, 0.0):
        assert h.tank_pressure_not_used_warning(kotu, blok) is None, kotu
    assert h.tank_pressure_not_used_warning(80.0, None) is None


def test_s7_yb04_i18n_iki_dilde():
    yer = lambda m: sorted(re.findall(r'\{(\w+)\}', m))  # noqa: E731
    en, tr = _i18n_iki_dil(_TANK_KODU)
    assert yer(en) == yer(tr) == ['deviation_pct', 'feed_pressure_bar',
                                  'tank_pressure_bar', 'tol_pct']
    assert 'was not used' in en and 'P_sat(T_tank)' in en
    assert 'kullanılmadı' in tr and 'P_sat(T_tank)' in tr
    en, tr = _i18n_iki_dil(_HEDEF_KODU)
    assert yer(en) == yer(tr) == ['dp_bar', 'mdot_dp', 'mdot_target', 'ratio',
                                  'tol_pct']
    assert 'No positive design verdict' in en
    assert 'olumlu tasarım hükmü verilmez' in tr


def _calculate_motor(**ek):
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=dict(ORNEK_H1, **ek))
    assert cevap.status_code == 200, cevap.get_json()
    return cevap.get_json()


@hb7_yamasi_bekleniyor
def test_s7_yb04_calculate_uyari_kanalinda_istek_reddedilmez():
    """API: 80 bar istek REDDEDİLMEZ (HTTP 200), motor uyarı kanalında adlı
    uyarı; P_sat'a eşit istek uyarısız; enjektör çözümü iki istekte aynı."""
    j80 = _calculate_motor(tank_pressure=80.0)
    m80 = j80['motor']
    p_sat = m80['injector_design']['feed_pressure_bar']
    jsat = _calculate_motor(tank_pressure=p_sat)
    tank = [w for w in m80['warnings'] if w.get('code') == _TANK_KODU]
    assert len(tank) == 1, m80['warnings']
    assert tank[0]['params']['tank_pressure_bar'] == 80.0
    assert tank[0]['params']['feed_pressure_bar'] == round(p_sat, 3)
    assert not [w for w in jsat['motor']['warnings']
                if w.get('code') == _TANK_KODU]
    # Beyan yerinde, devre bit-aynı (bağlama v3.1).
    assert 'NOT an input' in m80['injector_design']['feed_pressure_basis']
    assert (json.dumps(m80['injector_design_detail'], sort_keys=True)
            == json.dumps(jsat['motor']['injector_design_detail'],
                          sort_keys=True))


# --- arayüz: N₂O kipinde alan salt-okur (node ile DOM ikizi) ---------------
def _sablon_islevi(metin, ad):
    """Şablondaki ``function ad(...) {...}`` gövdesi (parantez dengesiyle)."""
    i = metin.index('function %s(' % ad)
    j = metin.index('{', metin.index(')', i))
    derinlik = 0
    for k in range(j, len(metin)):
        if metin[k] == '{':
            derinlik += 1
        elif metin[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i:k + 1]
    raise AssertionError('işlev kapanmıyor: %s' % ad)


#: v3.0.1 (kulvar T): kip yardımcıları ``tankPressureMode`` ve
#: ``updateTankPressureSourceOption`` eklendi; ``applyTankPressureMode`` ve
#: ``showTankPressureFeedFromResults`` onları çağırır.
_TANK_UI_ISLEVLERI = ('tankPressureMode', 'tankPressureIsSaturationDriven',
                      'updateTankPressureSourceOption', 'setTankPressureNote',
                      'applyTankPressureMode', 'clearTankPressureFeed',
                      'showTankPressureFeedFromResults', 'validateFormData')
#: Şablondaki üç besleme kaynağı sabiti (v3.0.1: tasarım ΔP ve kullanıcı
#: kaynağı eklendi); düzenek hepsini şablondan okur.
_TANK_UI_SABITLERI = ('TANK_PRESSURE_N2O_FEED_SOURCE',
                      'TANK_PRESSURE_DESIGN_DP_FEED_SOURCE',
                      'TANK_PRESSURE_USER_FEED_SOURCE')

_TANK_UI_JS = r"""
'use strict';
const vm = require('vm');
const yedekler = {};
function el(id, value) {
    return { id: id, value: value, readOnly: false, dataset: {}, style: {},
             attrs: {}, textContent: '',
             setAttribute(k, v) { this.attrs[k] = String(v); },
             getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
             removeAttribute(k) { delete this.attrs[k]; } };
}
const els = { oxidizer_type: { value: 'n2o' },
              tank_pressure: el('tank_pressure', '55'),
              tank_pressure_feed_note: el('tank_pressure_feed_note', ''),
              pressure_warning: { style: { display: 'none' } } };
const sb = { JSON, Math, String, Number, isFinite, Object,
    document: { getElementById: (id) => els[id] || null },
    validatePressures() {},
    i18nText(k, f) { yedekler[k] = f; return k; },
    i18nFmt(k, p, f) { yedekler[k] = f; return k + JSON.stringify(p || {}); } };
vm.createContext(sb);
vm.runInContext(JOB.kaynak, sb);
const tp = els.tank_pressure, not = els.tank_pressure_feed_note;
function durum() {
    return { readOnly: tp.readOnly, value: tp.value,
             held: tp.dataset.heldValue === undefined ? null : tp.dataset.heldValue,
             ph: tp.getAttribute('data-i18n-placeholder'),
             aria: tp.getAttribute('aria-readonly'),
             not: not.getAttribute('data-i18n'),
             notParams: not.getAttribute('data-i18n-params') };
}
const sonuc = (s, k) => ({ motor: { injector_design: {
    feed_pressure_bar: s, feed_pressure_source: k } } });
const out = {};
sb.applyTankPressureMode(); out.A = durum();
sb.showTankPressureFeedFromResults(sonuc(50.5433585, JOB.kaynak_kodu)); out.B = durum();
sb.clearTankPressureFeed(); out.C = durum();
sb.showTankPressureFeedFromResults(sonuc(50.5433585, JOB.kaynak_kodu));
els.oxidizer_type.value = 'lox'; sb.clearTankPressureFeed(); out.E = durum();
els.oxidizer_type.value = 'n2o'; sb.applyTankPressureMode();
sb.showTankPressureFeedFromResults(sonuc(24.0,
    'chamber_pressure_plus_design_pressure_drop')); out.F = durum();
const tam = { motor_name: 'x', atmospheric_pressure: 1, of_ratio: 7.5,
              chamber_pressure: 20, thrust: 1000, burn_time: 10,
              fuel_type: 'htpb', injector_type: 'showerhead' };
out.formN2O = sb.validateFormData(Object.assign({ oxidizer_type: 'n2o' }, tam));
out.formLOX = sb.validateFormData(Object.assign({ oxidizer_type: 'lox' }, tam));
out.yedekler = yedekler;
process.stdout.write(JSON.stringify(out));
"""


def _tank_ui_kos():
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node kurulu değil')
    metin = _oku(ADV_HTML)
    kaynak = '\n'.join(_sablon_islevi(metin, ad) for ad in _TANK_UI_ISLEVLERI)
    for ad in reversed(_TANK_UI_SABITLERI):
        sabit = re.search(r"^\s*const %s = '([^']+)';" % ad, metin, re.M)
        assert sabit, '%s yok' % ad
        kaynak = "const %s = '%s';\n" % (ad, sabit.group(1)) + kaynak
    girdi = ('const JOB = %s;\n' % json.dumps(
        {'kaynak': kaynak, 'kaynak_kodu': _N2O_DOYMA})) + _TANK_UI_JS
    p = subprocess.run([node], input=girdi, capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def _i18n_adv_iki_dil(anahtar):
    bul = re.findall(rf"^\s*'{re.escape(anahtar)}': '([^']*)',\s*$",
                     _oku(I18N_ADV), re.M)
    assert len(bul) == 2, (anahtar, bul)
    return bul[0], bul[1]


def test_s7_yb04_form_alani_n2o_kipinde_salt_okur_ve_sunucu_degerini_gosterir():
    """DOM ikizi (node): N₂O kipinde alan salt-okur, kullanıcı/proje sayısı
    gösterilmez (saklanır), hesaptan sonra sunucunun P_sat'ı ve kaynağı; sıcaklık
    değişince değer silinir; başka oksitleyicide alan açılır ve saklanan
    sayı geri gelir; sunucu N₂O doyma kaynağı yayımlamadıysa sayı yok.
    Form doğrulaması N₂O kipinde tank basıncını zorunlu saymaz.
    D7-M7 ve D7-M9 burada KIRMIZI."""
    o = _tank_ui_kos()
    n2o_ph, n2o_not = 'adv.ph.tankPressureN2oSat', 'adv.js.tankPressureN2oNote'
    assert o['A'] == {'readOnly': True, 'value': '', 'held': '55',
                      'ph': n2o_ph, 'aria': 'true', 'not': n2o_not,
                      'notParams': None}, o['A']
    assert o['B']['readOnly'] is True and o['B']['value'] == '50.54'
    assert o['B']['not'] == 'adv.js.tankPressureFeedUsed'
    assert json.loads(o['B']['notParams']) == {'p': 50.54}
    assert (o['C']['value'], o['C']['not'], o['C']['readOnly']) == (
        '', n2o_not, True)
    # v3.0.1 (kulvar T) — BEKLENTİ ÇEVRİLDİ. Eski beklenti LOX'a geçince
    # alanın açılıp 55 bar'ın GÖNDERİLMESİNİ kilitliyordu; ölçüldü (kulvar T
    # once.json A_lox_tank50 ⟷ B_lox_user30/40): LOX devresi P₁ = P_c·1,2
    # alıyordu ve 30/40/50 bar enjektör çözümünü bit-aynı bırakıyordu — yani
    # alan kullanılmadığı hâlde düzenlenebilir görünüyordu (Ayberk'in
    # maddesinin kökü). Artık LOX'un varsayılan kipi (tasarım ΔP oranı) da
    # salt-okurdur; kullanıcı tank basıncı 'user' kipinde girilir
    # (tests/test_v301_tank_basinci.py o kipi sınar).
    assert o['E'] == {'readOnly': True, 'value': '', 'held': '55',
                      'ph': 'adv.ph.tankPressureDesignDp', 'aria': 'true',
                      'not': 'adv.js.tankPressureDesignDpNote',
                      'notParams': None}, o['E']
    assert (o['F']['value'], o['F']['not'], o['F']['readOnly']) == (
        '', 'adv.js.tankPressureFeedNotPublished', True)
    assert not any('tank_pressure' in h for h in o['formN2O']), o['formN2O']
    # v3.0.1 (kulvar T): LOX'un varsayılan kipinde de tank basıncı bir girdi
    # değildir — zorunlu sayılmaz (zorunluluk 'user' kipine taşındı).
    assert not any('tank_pressure' in h for h in o['formLOX']), o['formLOX']
    # Yedek metinler EN sözlüğüyle birebir (EN = TR anahtar çifti var).
    for anahtar in ('adv.ph.tankPressureN2oSat', 'adv.js.tankPressureN2oNote',
                    'adv.js.tankPressureFeedUsed',
                    'adv.js.tankPressureFeedNotPublished'):
        en, tr = _i18n_adv_iki_dil(anahtar)
        assert o['yedekler'][anahtar] == en, anahtar
        assert tr and tr != en, anahtar


def test_s7_yb04_form_n2o_kipinde_tank_basincini_gondermez():
    """Şablonun GERÇEK ``getFormData`` işlevi node'da, şablondan türetilmiş
    DOM ikiziyle (``tests/test_d36_hibrit_a1.py`` düzeneği, aynen): N₂O
    kipinde yükte ``tank_pressure`` YOK (kullanıcı 80 bar yazmış olsa da);
    LOX kipinde kullanıcının değeri aynen gider. Düzenek getFormData'yı
    yalnız yanındaki dört işlevle koşar — işlev başka bir yardımcıya
    dayanırsa ReferenceError verir (7. tur süpürmesi ilk sürümde
    `test_d36_hibrit_a1` / `test_d37_cw_a4b`'deki 7 düğümün bu yüzden
    kırıldığını yakaladı). D7-M8 burada KIRMIZI."""
    from tests.test_d36_hibrit_a1 import NODE, _govde
    if NODE is None:
        pytest.skip('node kurulu değil')
    n2o = _govde(deger={'oxidizer_type': 'n2o', 'tank_pressure': 80})
    assert 'tank_pressure' not in n2o, n2o.get('tank_pressure')
    # v3.0.1 (kulvar T) — BEKLENTİ ÇEVRİLDİ (gerekçe yukarıdaki E durumu):
    # LOX'un varsayılan kipinde sayı devreye girmediği için GÖNDERİLMEZ;
    # kullanıcı tank basıncı kipinde ('user') kaynak beyanıyla birlikte gider.
    lox = _govde(deger={'oxidizer_type': 'lox', 'tank_pressure': 80})
    assert 'tank_pressure' not in lox, lox.get('tank_pressure')
    assert 'tank_pressure_source' not in lox
    lox_u = _govde(deger={'oxidizer_type': 'lox', 'tank_pressure': 80,
                          'tank_pressure_source': 'user'})
    assert lox_u.get('tank_pressure') == 80, lox_u.get('tank_pressure')
    assert lox_u.get('tank_pressure_source') == 'user'


# ===========================================================================
# 9. tur (14 Eki) — metin kalemleri: 7. tur Devir 32 / 33 / 35 / 36 / 37.
# Sayısal model DEĞİŞMEZ (rapor 9. tur: 19 /calculate vakasında sayısal
# yaprak sha256'sı önce = sonra). Kâhinler: CoolProp (N₂O doyma eğrisi,
# Lemmon & Span 2006), orifis bağıntısı A = ṁ/(C_d·√(2ρΔP)) (Sutton &
# Biblarz Böl. 8) ve çapın kendisi (gösterim kendi hükmüyle çelişmez).
# ===========================================================================
import math as _math  # noqa: E402

_T9_CACHE = {}


def _t9_calculate(anahtar, **ek):
    """Aynı yükü bir kez koşar (her /calculate ~4 s)."""
    if anahtar not in _T9_CACHE:
        from hrma.app import app
        yuk = dict(ORNEK_H1)
        for k, v in ek.items():
            if v is None:
                yuk.pop(k, None)
            else:
                yuk[k] = v
        app.config['TESTING'] = True
        with app.test_client() as ist:
            cevap = ist.post('/calculate', json=yuk)
        assert cevap.status_code == 200, cevap.get_json()
        _T9_CACHE[anahtar] = cevap.get_json()
    return _T9_CACHE[anahtar]


def _t9_tank_kaydi(j):
    kayit = [k for k in (j.get('defaults_applied') or [])
             if isinstance(k, dict) and k.get('field') == 'tank_pressure']
    assert len(kayit) <= 1, kayit
    return kayit[0] if kayit else None


def _t9_coolprop_psat_bar(sicaklik_k):
    cp = pytest.importorskip('CoolProp.CoolProp')
    return cp.PropsSI('P', 'T', float(sicaklik_k), 'Q', 0, 'NitrousOxide') / 1e5


# --- Devir 32 ---------------------------------------------------------------
def test_t9_d32_n2o_kipinde_tank_yedegi_kullanilmadi_diye_isaretli():
    """N₂O doyma kipinde ``tank_pressure`` gönderilmediğinde künye satırı
    KALIR (uç sözleşmesi, ``test_d32_app_api_uc_a1``) ama ``applied: False``
    ve ``used_by_model`` = devrenin P₁'i taşır; ileti 'NOT used' der.

    Kâhin 1 (ölçüm): istek 80 bar gönderse de enjektör çözümü bit-aynı —
    yedek hiçbir yayımlanan enjektör sayısına girmiyor. Kâhin 2: P₁,
    CoolProp P_sat(T_tank)'e ``TANK_PRESSURE_PSAT_REL_TOL`` içinde eşit
    (ürünün kendi sapma payı; tablo ara değeri ⟷ EOS). T9-M1 KIRMIZI."""
    from hrma.engines.hybrid_rocket_engine import TANK_PRESSURE_PSAT_REL_TOL
    yok = _t9_calculate('n2o_tanksiz', tank_pressure=None)
    t80 = _t9_calculate('n2o_tank80', tank_pressure=80.0)
    kayit = _t9_tank_kaydi(yok)
    assert kayit is not None, yok.get('defaults_applied')
    assert kayit['value'] == 50.0 and kayit['reason'] == 'not_supplied'
    assert kayit.get('applied') is False, kayit
    idd = yok['motor']['injector_design']
    assert idd['feed_pressure_source'] == _N2O_DOYMA
    assert kayit['used_by_model'] == idd['feed_pressure_bar']
    assert kayit['used_by_model_source'] == _N2O_DOYMA
    assert 'NOT used' in kayit['message']
    assert 'describes THAT input' not in kayit['message']
    # Kâhin 1: yedek kullanılmıyor (80 bar ile enjektör çözümü aynı).
    for blok in ('injector_design_detail',):
        assert (json.dumps(yok['motor'][blok], sort_keys=True)
                == json.dumps(t80['motor'][blok], sort_keys=True))
    for anahtar in ('n_holes', 'hole_diameter', 'pressure_drop_bar',
                    'injection_area'):
        assert yok['injector'][anahtar] == t80['injector'][anahtar], anahtar
    # Kâhin 2: P₁ = P_sat(T_tank) (bağımsız EOS çağrısı).
    t_tank = yok['motor']['oxidizer_inlet_state']['temperature_K']
    p_sat = _t9_coolprop_psat_bar(t_tank)
    assert abs(kayit['used_by_model'] - p_sat) / p_sat <= TANK_PRESSURE_PSAT_REL_TOL


def test_t9_d32_tank_basinci_dp_turettiginde_kayit_degismez():
    """Kullanıcı ΔP ezmesini 0 ile beyan edince plaka ΔP'yi tank basıncından
    seçer (otomatik dal ``P_tank − P_c``): yedek GERÇEKTEN girer → kayıt
    eski sözleşmesiyle durur (``applied`` yok, ileti 'the run used this
    server's own default'). T9-M2 KIRMIZI."""
    j = _t9_calculate('n2o_tanksiz_userdp0', tank_pressure=None,
                      pressure_drop_source='user', pressure_drop=0)
    assert j['injector']['pressure_drop_source'].startswith('auto')
    kayit = _t9_tank_kaydi(j)
    assert kayit is not None
    assert 'applied' not in kayit and 'used_by_model' not in kayit, kayit
    assert "used this server's own default" in kayit['message']


def test_t9_d32_tank_gonderildiyse_kayit_yok():
    """Kullanıcı değeri gönderdiyse künye yok (sözleşme aynı)."""
    assert _t9_tank_kaydi(_t9_calculate('n2o_tank80', tank_pressure=80.0)) is None


def test_t9_d32_isaretleme_islevi_fail_closed():
    """Doyma kipi değilse, P₁ sonlu değilse ya da blok yoksa kayıt AYNEN
    döner (uydurma P_sat yok)."""
    from hrma.app import _n2o_doyma_tank_kunyesi
    kayit = [{'field': 'tank_pressure', 'value': 50.0, 'reason': 'not_supplied',
              'unit': 'bar', 'message': 'm'}]
    iyi = {'feed_pressure_source': _N2O_DOYMA, 'feed_pressure_bar': 50.5}
    assert _n2o_doyma_tank_kunyesi(kayit, iyi, 'user override')[0]['applied'] is False
    for blok in (None, {}, dict(iyi, feed_pressure_source='chamber_pressure_plus_design_pressure_drop'),
                 dict(iyi, feed_pressure_bar=float('nan')),
                 dict(iyi, feed_pressure_bar=float('inf')),
                 dict(iyi, feed_pressure_bar=-1.0),
                 dict(iyi, feed_pressure_bar='elli')):
        assert _n2o_doyma_tank_kunyesi(kayit, blok, 'user override') == kayit, blok
    from hrma.utils.injector_design import DP_SOURCE_AUTO, DP_SOURCE_SAT
    for kaynak in (DP_SOURCE_AUTO, DP_SOURCE_SAT):
        assert _n2o_doyma_tank_kunyesi(kayit, iyi, kaynak) == kayit


# --- Devir 33 ---------------------------------------------------------------
def test_t9_d33_ornek_hibrit_tank_basinci_doyma_basincidir():
    """``examples/Example Hybrid N2O-HTPB 3kN.hrma`` tank basıncı CoolProp
    P_sat(oxidizer_temp)'e ``TANK_PRESSURE_PSAT_REL_TOL`` içinde (eski 55 bar
    +%9,2 sapıyordu) ve /calculate'te ``tank_pressure_not_used`` uyarısı
    YOK. T9-M3 (55 bar) KIRMIZI."""
    from hrma.engines.hybrid_rocket_engine import TANK_PRESSURE_PSAT_REL_TOL
    from tests.test_example_projects import calculate_payload, load_example_doc
    alanlar = load_example_doc('hybrid')['inputs']['fields']
    assert alanlar['oxidizer_type'] == 'n2o'
    p_sat = _t9_coolprop_psat_bar(alanlar['oxidizer_temp'])
    assert abs(alanlar['tank_pressure'] - p_sat) / p_sat <= TANK_PRESSURE_PSAT_REL_TOL, (
        alanlar['tank_pressure'], p_sat)
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=calculate_payload('hybrid', alanlar))
    assert cevap.status_code == 200
    assert not [w for w in cevap.get_json()['motor'].get('warnings') or []
                if isinstance(w, dict) and w.get('code') == _TANK_KODU]


# --- Devir 35 ---------------------------------------------------------------
@pytest.mark.parametrize('d_mm', [0.4951, 0.4975, 0.4999, 0.49999])
def test_t9_d35_bant_alti_cap_gosterimde_kenara_esitlenmez(d_mm):
    """Tek delik d ∈ [0,495; 0,5) mm: yayımlanan ``d_mm`` gösterilen alt
    kenarın ALTINDA (eski: 0.5 = 0.5, "bandın altında" metniyle çelişik).
    Kâhin: çapın kendisi (d < 0,5). T9-M4 KIRMIZI."""
    from hrma.engines.injector_design import DEFAULT_CONSTRAINTS, _plan_orifices
    w = []
    _plan_orifices(_math.pi * (d_mm * 1e-3) ** 2 / 4.0,
                   dict(DEFAULT_CONSTRAINTS), w)
    kayit = [k for k in w
             if k['code'] == 'warn.injector.orifice_d_below_manufacturing_band']
    assert len(kayit) == 1, w
    p = kayit[0]['params']
    assert p['d_mm'] < p['d_min_mm'] <= p['d_max_mm'], p
    assert p['d_min_mm'] == DEFAULT_CONSTRAINTS['d_min_mm']
    assert abs(p['d_mm'] - d_mm) < (p['d_min_mm'] - d_mm) + 1e-12


def test_t9_d35_pencere_disinda_parametreler_bit_ayni():
    """Çelişki yoksa eski gösterim AYNEN (0,4665 → 0,47 / 0,5 / 2,5;
    rapor 9. tur 'önce' ölçümü). Yayımlanan parametre sınıfı değişmez."""
    from hrma.engines.injector_design import DEFAULT_CONSTRAINTS, _plan_orifices
    w = []
    _plan_orifices(_math.pi * (0.4665e-3) ** 2 / 4.0, dict(DEFAULT_CONSTRAINTS), w)
    assert w[0]['params'] == {'d_mm': 0.47, 'd_min_mm': 0.5, 'd_max_mm': 2.5}


@pytest.mark.parametrize('d_mm', [2.503, 2.5049])
def test_t9_d35_sabit_n_bant_ustu_gosterimde_kenara_esitlenmez(d_mm):
    """Sabit n = 2, d ∈ (2,5; 2,505) mm: ``d_mm`` > gösterilen üst kenar."""
    from hrma.engines.injector_design import DEFAULT_CONSTRAINTS, _plan_orifices
    w = []
    _plan_orifices(2 * _math.pi * (d_mm * 1e-3) ** 2 / 4.0,
                   dict(DEFAULT_CONSTRAINTS), w, n_fixed=2)
    p = [k for k in w if k['code']
         == 'warn.injector.fixed_n_outside_manufacturing_band'][0]['params']
    assert p['d_mm'] > p['d_max_mm'] == DEFAULT_CONSTRAINTS['d_max_mm'], p


def test_t9_d35_cagiranin_iki_ondalikli_bandi_bant_disi_uyarisinda_korunur():
    """Çağıran bandı 0,35 mm: bant dışı uyarısında kenar 0,35 kalır (eski
    gösterim 0,3 diyordu) ve çap kenarın altında."""
    from hrma.engines.injector_design import _plan_orifices
    w = []
    _plan_orifices(_math.pi * (0.3497e-3) ** 2 / 4.0,
                   {'d_min_mm': 0.35, 'd_max_mm': 1.8, 'n_max': 1}, w)
    p = w[0]['params']
    assert p['d_min_mm'] == 0.35 and p['d_mm'] < 0.35, p


def test_t9_d35_carpismali_kirpma_metni_istenen_capi_kenara_esitlemez():
    """utils çarpışmalı kırpma metni: 2 çift için gereken çap 0,4975 mm iken
    metin "0.50 mm holes, outside the manufacturing band (0.50-…" demez;
    gösterilen çap gösterilen alt kenardan küçük. Kâhin: ṁ, orifis
    bağıntısından d = 0,4975 mm verecek biçimde kurulur."""
    from hrma.utils.injector_design import InjectorDesign
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        inj = InjectorDesign(mdot_ox=0.05, chamber_pressure=20.0,
                             tank_pressure=50.0, pressure_drop=4.0,
                             pressure_drop_source='user', oxidizer_temp=293.0,
                             oxidizer_type='n2o', injector_type='impingement')
        inj.set_impingement_params(n_pairs=2)
        d_hedef = 0.4975e-3
        alan = 4 * _math.pi * d_hedef ** 2 / 4.0
        inj.mdot_ox = alan * inj.C_d * _math.sqrt(
            2.0 * inj.rho_ox * inj.delta_P_inj * 1e5)
        sonuc = inj.calculate()
    metin = [u for u in sonuc['warnings'] if 'would need' in str(u)]
    assert len(metin) == 1, sonuc['warnings']
    m = re.search(r'would need (\S+) mm holes, outside the manufacturing band '
                  r'\((\S+)-(\S+) mm\)', metin[0])
    assert m, metin[0]
    assert float(m.group(1)) < float(m.group(2)), metin[0]


# --- Devir 36 ---------------------------------------------------------------
def _t9_dus_kirpma(n_holes):
    from hrma.utils.injector_design import InjectorDesign
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        inj = InjectorDesign(mdot_ox=0.5, chamber_pressure=20.0,
                             tank_pressure=50.0, oxidizer_temp=293.0,
                             oxidizer_type='n2o', injector_type='showerhead')
        inj.set_showerhead_params(n_holes=n_holes)
        return inj, inj.calculate()


@pytest.mark.parametrize('n_holes', [4, 400])
def test_t9_d36_dus_basligi_kirpma_metni_hedef_debi_sinifiyla_uyumlu(n_holes):
    """Kanon dışı duş başlığı kırpması: metin artık "preserve target flow
    rate" DEMEZ; teslim alanı, oran ve "not verified" cümlesini taşır ve
    sınıf (``target_flow_check``) metindeki oranla tutarlıdır. Kâhin:
    A_gerekli = ṁ/(C_d·√(2ρΔP)), A_teslim = n·π·d²/4 (yanıtın planı).
    T9-M5 KIRMIZI."""
    from hrma.engines.injector_design import CLAMPED_PLAN_TARGET_FLOW_REL_TOL
    inj, s = _t9_dus_kirpma(n_holes)
    metin = [u for u in s['warnings'] if 'clamped to manufacturing band' in str(u)]
    assert len(metin) == 1, s['warnings']
    w = metin[0]
    assert 'preserve' not in w, w
    assert 'to cover the injection area required for the target flow' in w
    assert 'not verified at this pressure drop' in w
    a_ger = inj.mdot_ox / (inj.C_d * _math.sqrt(
        2.0 * inj.rho_ox * inj.delta_P_inj * 1e5)) * 1e6
    a_tes = s['n_holes'] * _math.pi * s['hole_diameter'] ** 2 / 4.0
    oran = a_tes / a_ger
    assert f'required: {oran:.2f}x' in w, (oran, w)
    karsilanmiyor = abs(oran - 1.0) > CLAMPED_PLAN_TARGET_FLOW_REL_TOL
    assert (s.get('target_flow_check', {}).get('status')
            == ('target_flow_not_met' if karsilanmiyor else None))


def test_t9_d36_calculate_kanon_disi_dus_basligi():
    """/calculate kullanıcı ΔP + n 4 (rapor 9. tur ``SHu_n4``): 5 × 2,5 mm,
    sınıf ``target_flow_not_met`` ve metin "preserve" demiyor."""
    j = _t9_calculate('shu_n4', injector_type='showerhead',
                      pressure_drop_source='user', n_holes=4)
    inj = j['injector']
    assert inj['target_flow_check']['status'] == 'target_flow_not_met'
    metin = [u for u in inj['warnings'] if 'clamped to manufacturing band' in str(u)]
    assert len(metin) == 1 and 'preserve' not in metin[0], inj['warnings']
    assert f"{inj['target_flow_check']['ratio']:.2f}x the target" in metin[0]


# --- Devir 37 ---------------------------------------------------------------
@pytest.mark.parametrize('itki,d_mm,cift', [(50.0, 1.0, None), (1000.0, 0.8, None),
                                            (1000.0, 2.0, None), (50.0, 1.0, 3),
                                            (1000.0, 2.0, 2)])
def test_t9_d37_sabit_carpismali_capta_kirpma_metni_var(itki, d_mm, cift):
    """Kullanıcı ``orifice_diameter`` ile çapı sabitledi (d_min = d_max):
    kırpma metni artık VAR ve sabit çapı adıyla söyler; "manufacturing band
    (1.00-1.00 mm)" gibi yanlış adlı metin YOK. Metindeki oran bağımsız
    kâhinle (CoolProp ρ, orifis bağıntısı) aynı ve sınıfla tutarlı.
    T9-M6 KIRMIZI."""
    cp = pytest.importorskip('CoolProp.CoolProp')
    j = _t9_calculate(f'od_{itki}_{d_mm}_{cift}', thrust=itki,
                      injector_type='impingement', orifice_diameter=d_mm,
                      element_pairs=cift, **KANON_DISI_DP)
    inj = j['injector']
    metin = [u for u in inj['warnings'] if 'Hole diameter fixed by the request'
             in str(u)]
    assert len(metin) == 1, inj['warnings']
    w = metin[0]
    assert f'at {d_mm:.2f} mm (orifice_diameter)' in w
    assert 'manufacturing band' not in w
    assert ('the requested' if cift else 'the auto-selected minimum of') in w
    # 10. tur (HB9 devir 45; dört koşul): plaka artık TEK tank sıcaklığında
    # (karar: 20 °C = 293,15 K; eski uç yedeği 293 K); kâhin CoolProp.
    rho = cp.PropsSI('D', 'T', 293.15, 'Q', 0, 'NitrousOxide')
    assert '293.15 K' in inj['density_source']
    a_ger = j['motor']['mdot_ox'] / (inj['discharge_coefficient'] * _math.sqrt(
        2.0 * rho * inj['pressure_drop_bar'] * 1e5))
    a_tes = inj['n_holes'] * _math.pi * (inj['hole_diameter'] * 1e-3) ** 2 / 4.0
    assert f'required: {a_tes / a_ger:.2f}x' in w, (a_tes / a_ger, w)
    assert inj['target_flow_check']['status'] == 'target_flow_not_met'


# --- i18n: yeni metinler iki dilde (EN = üretici, TR = desen) ---------------
def test_t9_yeni_metinler_TR_desenle_cevrilir_EN_aynen():
    """Node: üç yeni/değişen metin (duş başlığı kırpma gövdesi, sabit çap
    gövdesi, teslim kuyruğu) TR'de İngilizce gövde bırakmadan ve ondalık
    virgülle çevrilir; EN'de metin aynen döner. T9-M7 KIRMIZI."""
    from tests.test_d36_dil2_a2 import NODE, SERVERTEXT_JS, node_calistir
    if NODE is None:
        pytest.skip('node kurulu değil')
    _, s4 = _t9_dus_kirpma(4)
    j = _t9_calculate('od_50.0_1.0_None', thrust=50.0,
                      injector_type='impingement', orifice_diameter=1.0,
                      element_pairs=None, **KANON_DISI_DP)
    msgs = ([u for u in s4['warnings'] if 'clamped to manufacturing' in str(u)]
            + [u for u in j['injector']['warnings']
               if 'Hole diameter fixed by the request' in str(u)])
    assert len(msgs) == 2, s4['warnings']
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        sonuc = node_calistir(KOK, SERVERTEXT_JS, {'msgs': msgs}, td, 't9')
    assert 'error' not in sonuc, sonuc
    assert sonuc['en'] == msgs
    for tr in sonuc['tr']:
        for ing in ('Hole diameter', 'Delivered injection area', 'doublet pairs',
                    'not verified', 'mm^2'):
            assert ing not in tr, (ing, tr)
        assert 'hedef debi bu basınç düşümünde doğrulanmadı' in tr, tr
        assert not re.search(r'\d\.\d', tr), tr


def test_t9_desenler_ureticinin_cumlesiyle_ayni():
    """Desen üreticinin sabit gövdesini birebir taşır (üretici cümleyi
    değiştirirse bekçi düşer — sessiz İngilizce yok)."""
    uretici = _oku(UTILS_INJ)
    for parca in ('to cover the injection ', 'area required for the target flow '
                  'at the design pressure ', 'Hole diameter fixed by the request at ',
                  '(orifice_diameter): ', 'doublet pairs would need ',
                  'holes for the target flow at the ', 'design pressure drop, so '
                  'the plan uses ', 'Delivered injection area ',
                  'rate is not verified at this pressure drop.'):
        assert parca in uretici, parca
    desen = _oku(KOK / 'hrma' / 'static' / 'js' / 'i18n_charts.js')
    for parca in ('hole count adjusted to (\\S+) to cover the injection area',
                  'Hole diameter fixed by the request at (\\S+) mm',
                  '/ Delivered injection area (\\S+) mm\\^2 against'):
        assert parca in desen, parca


# ===========================================================================
# 10. tur (14 Eki) — malzeme varsayılanı + HB9 devirleri 44 / 45 / 46 / 47 / 48.
# Kâhinler: kayıtlı karar (ana model 10. tur: TEK varsayılan, değer formun
# ekranda gösterdiği seçenek), CoolProp (N₂O doyma eğrisi), bağımsız delik
# planı araması (en küçük n, iki bandın kesişimi) ve çapın kendisi.
# ===========================================================================
APP_JS_T10 = KOK / 'hrma' / 'static' / 'js' / 'app.js'
I18N_COMMON_T10 = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
I18N_CHARTS_T10 = KOK / 'hrma' / 'static' / 'js' / 'i18n_charts.js'


def _t10_varsayilan_satiri(yanit, dil, alan):
    """app.js ``defaultsAppliedBlock`` çıktısında ``alan`` satırının metni
    (node koşum takımı ``tests/test_d37_hibrit_a1.py``ninkidir)."""
    from tests.test_d37_hibrit_a1 import _metin, _node
    html = _node({'sozluk': True, 'dil': dil,
                  'defaults_results': yanit})['defaults_html']
    m = re.search(r'<div class="hd-defaults-applied-row"\s+data-defaults-'
                  r'applied-field="' + re.escape(alan) + r'".*?</div>',
                  html, re.S)
    return (_metin(m.group(0)) if m else None), html


# --- Devir 44: applied:false satırı ekranda "uyguladı" demez ----------------
def test_t10_d44_kullanilmayan_yedek_ekranda_kullanilmadi_der():
    """N₂O doyma kipinde API kaydı ``applied: False`` + ``used_by_model``
    taşıyor (9. tur); ekran satırı artık "sunucu kendi varsayılanını
    uyguladı" DEMEZ, "KULLANILMADI" der ve modelin sayısını (P_sat) basar.
    Kâhin: kaydın kendi ``used_by_model`` alanı (9. turda CoolProp'a
    bağlandı). T10-M1 KIRMIZI."""
    from tests.test_d37_hibrit_a1 import NODE
    if NODE is None:
        pytest.skip('node kurulu değil')
    yok = _t9_calculate('n2o_tanksiz', tank_pressure=None)
    kayit = _t9_tank_kaydi(yok)
    assert kayit is not None and kayit.get('applied') is False, kayit
    tr, _ = _t10_varsayilan_satiri(yok, 'tr', 'tank_pressure')
    en, _ = _t10_varsayilan_satiri(yok, 'en', 'tank_pressure')
    assert tr is not None and en is not None
    assert 'KULLANILMADI' in tr and 'P_sat(T_tank)' in tr, tr
    assert 'kendi varsayılanını uyguladı' not in tr, tr
    assert 'NOT used in this run' in en and 'P_sat(T_tank)' in en, en
    assert 'applied its own default' not in en, en
    # Modelin sayısı kayıttan (ondalık virgül TR, nokta EN).
    sayi = f"{kayit['used_by_model']:.4f}"
    assert sayi in en, (sayi, en)
    assert sayi.replace('.', ',') in tr, (sayi, tr)
    # Uygulanan bir yedek (ör. l_star) eski cümlesini korur.
    for k in yok['defaults_applied']:
        if k.get('reason') == 'not_supplied' and 'applied' not in k:
            satir, _ = _t10_varsayilan_satiri(yok, 'tr', k['field'])
            assert 'kendi varsayılanını uyguladı' in satir, satir
            break
    else:
        pytest.fail('uygulanan bir yedek kaydı bulunamadı')


def test_t10_d44_kaynak_literali_python_sabitiyle_ayni_ve_kacisli():
    """JS'teki kaynak adı ``FEED_PRESSURE_SOURCE_N2O_SAT`` ile aynı; sözlük
    EN = TR; kullanıcı denetimindeki alan adı innerHTML'e kaçışsız girmez."""
    from hrma.engines.hybrid_rocket_engine import FEED_PRESSURE_SOURCE_N2O_SAT
    from tests.test_d37_hibrit_a1 import NODE, _islev
    govde = _islev(_oku(APP_JS_T10), 'function defaultsAppliedBlock(')
    assert f"=== '{FEED_PRESSURE_SOURCE_N2O_SAT}'" in govde
    sozluk = _oku(I18N_COMMON_T10)
    for anahtar in ('app.defaultsApplied.notUsed',
                    'app.defaultsApplied.notUsedN2oSat',
                    'app.defaultsApplied.notUsedValue'):
        assert sozluk.count(f"'{anahtar}':") == 2, anahtar
    if NODE is None:
        pytest.skip('node kurulu değil')
    kotu = {'defaults_applied': [
        {'field': '<img src=x onerror=1>', 'value': 1.0, 'unit': 'bar',
         'reason': 'not_supplied', 'applied': False, 'used_by_model': 2.0,
         'used_by_model_source': '<b>x</b>'},
        {'field': 'p2', 'value': 1.0, 'reason': 'not_supplied',
         'applied': False, 'used_by_model': 'NaN'}]}
    _, html = _t10_varsayilan_satiri(kotu, 'en', 'p2')
    assert '<img' not in html and '<b>x' not in html, html
    assert '&lt;img' in html
    satir, _ = _t10_varsayilan_satiri(kotu, 'en', 'p2')
    assert satir.endswith('NOT used in this run'), satir


# --- Devir 46: çağıranın d_max'ı arama yolunda da uygulanır -----------------
def _t10_bagimsiz_plan(alan_m2, d_lo, d_hi, n_max):
    """Bağımsız kâhin: [d_lo, d_hi] (metre) içine çapı oturtan EN KÜÇÜK n."""
    for n in range(1, n_max + 1):
        d = _math.sqrt(4.0 * alan_m2 / (_math.pi * n))
        if d_lo <= d <= d_hi:
            return n, d
    return None


def test_t10_d46_cagiranin_d_maxi_arama_yolunda_uygulanir():
    """ÖLÇÜLDÜ (9. tur ``bant035_d1.8003``): ``{'d_min_mm': 0.35,
    'd_max_mm': 1.8, 'n_max': 1}`` ve d = 1,8003 mm için uyarı listesi
    boştu. Artık plan çağıranın bandını aşarsa ADLI uyarı var; n_max izin
    verirse çağıranın bandına oturan plan seçilir. T10-M2 KIRMIZI."""
    from hrma.engines.injector_design import (ORIFICE_D_PREF_MM,
                                              _plan_orifices)
    alan = _math.pi * (1.8003e-3) ** 2 / 4.0
    u = []
    n, d = _plan_orifices(alan, {'d_min_mm': 0.35, 'd_max_mm': 1.8,
                                 'n_max': 1}, u)
    assert (n, round(d * 1e3, 4)) == (1, 1.8003)
    assert [w['code'] for w in u] == ['warn.injector.orifice_plan_infeasible'], u
    assert u[0]['params']['d_mm'] > u[0]['params']['d_max_mm'] == 1.8, u
    u = []
    kisit = {'d_min_mm': 0.35, 'd_max_mm': 1.8, 'n_max': 4}
    n, d = _plan_orifices(alan, kisit, u)
    lo = max(ORIFICE_D_PREF_MM[0], kisit['d_min_mm']) * 1e-3
    hi = min(ORIFICE_D_PREF_MM[1], kisit['d_max_mm']) * 1e-3
    assert (n, d) == _t10_bagimsiz_plan(alan, lo, hi, kisit['n_max'])
    assert d * 1e3 <= kisit['d_max_mm'] and u == [], u


def test_t10_d46_dar_bantta_son_kapi_adiyla_soyler():
    """Hiçbir tam sayı n çapı çağıranın bandına oturtamıyorsa (dar bant)
    plan ``orifice_d_outside_caller_band`` ile ADIYLA bildirilir; eski
    kod 'tercih bandının altında' diyordu (çap 2,0 mm iken). T10-M3
    KIRMIZI."""
    from hrma.engines.injector_design import _plan_orifices
    kisit = {'d_min_mm': 1.8, 'd_max_mm': 1.85, 'n_max': 50}
    alan = _math.pi * (4.0e-3) ** 2 / 4.0
    assert _t10_bagimsiz_plan(alan, 1.8e-3, 1.85e-3, 50) is None
    u = []
    n, d = _plan_orifices(alan, kisit, u)
    assert d * 1e3 > kisit['d_max_mm']
    assert [w['code'] for w in u] == [
        'warn.injector.orifice_d_outside_caller_band'], u
    p = u[0]['params']
    assert (p['n'], p['n_max'], p['d_min_mm'], p['d_max_mm']) == (
        n, 50, 1.8, 1.85), p
    assert p['d_mm'] == round(d * 1e3, 2)


def test_t10_d46_urun_yolu_bit_ayni():
    """Varsayılan kısıtla (d_min ≡ d_lo, d_max ≡ d_hi) kesişim tercih
    bandının kendisidir: 400 alanlık taramada plan bağımsız aramayla birebir,
    yeni kod hiç basılmaz."""
    from hrma.engines.injector_design import (DEFAULT_CONSTRAINTS,
                                              ORIFICE_D_PREF_MM, _plan_orifices)
    lo, hi = (x * 1e-3 for x in ORIFICE_D_PREF_MM)
    for d1 in np.geomspace(0.3, 40.0, 400):
        alan = _math.pi * (d1 * 1e-3) ** 2 / 4.0
        u = []
        n, d = _plan_orifices(alan, dict(DEFAULT_CONSTRAINTS), u)
        beklenen = _t10_bagimsiz_plan(alan, lo, hi,
                                      int(DEFAULT_CONSTRAINTS['n_max']))
        if beklenen is not None:
            assert (n, d) == beklenen, d1
        assert 'warn.injector.orifice_d_outside_caller_band' not in [
            w['code'] for w in u], (d1, u)


# --- Devir 47: çarpışmalı kırpma gövdeleri TR'de çevrilir -------------------
def test_t10_d47_carpismali_kirpma_govdeleri_TR_desenle():
    """Node: 'Requested N doublet pairs … re-solved' ve 'The auto-selected
    minimum of …' gövdeleri TR'de İngilizce bırakmadan, ondalık virgülle
    çevrilir (kuyruk 9. turdan beri ayrı); EN aynen. T10-M4 KIRMIZI."""
    from tests.test_d36_dil2_a2 import NODE, SERVERTEXT_JS, node_calistir
    if NODE is None:
        pytest.skip('node kurulu değil')
    msgs = []
    for anahtar, ep in (('t10_ep3', 3), ('t10_ep0', None)):
        j = _t9_calculate(anahtar, thrust=50.0, injector_type='impingement',
                          element_pairs=ep, **KANON_DISI_DP)
        msgs += [u for u in j['injector']['warnings']
                 if 'doublet pairs would need' in str(u)]
    assert len(msgs) == 2, msgs
    assert msgs[0].startswith('Requested 3 doublet pairs') and (
        'the pair count was re-solved' in msgs[0]), msgs[0]
    assert msgs[1].startswith('The auto-selected minimum of'), msgs[1]
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        sonuc = node_calistir(KOK, SERVERTEXT_JS, {'msgs': msgs}, td, 't10')
    assert 'error' not in sonuc, sonuc
    assert sonuc['en'] == msgs
    for tr in sonuc['tr']:
        for ing in ('doublet pairs', 'Requested', 'auto-selected',
                    'manufacturing band', 'clamped', 'not verified'):
            assert ing not in tr, (ing, tr)
        assert 'çarpışmalı jet çifti' in tr, tr
        assert not re.search(r'\d\.\d', tr), tr


def test_t10_d47_desenler_ureticinin_cumlesiyle_ayni():
    """Desen üreticinin sabit parçalarını birebir taşır."""
    uretici = _oku(UTILS_INJ)
    for parca in ('doublet pairs would need ', ' mm holes, outside the '
                  'manufacturing ', '; the pair count was ',
                  're-solved to ', '; the holes were ', 'clamped to ',
                  'pairs, so the injection area is ',
                  'mm^2 required for the target ',
                  'flow at the design pressure drop (ratio ',
                  '); the exit velocity is ',
                  'divided by the same ratio.',
                  "'The auto-selected minimum of'"):
        assert parca in uretici, parca
    desen = _oku(I18N_CHARTS_T10)
    for parca in ('the pair count was re-solved to (\\S+) pairs of (\\S+) mm '
                  'holes\\.$/',
                  '(Requested|The auto-selected minimum of) (\\S+) doublet '
                  'pairs would need'):
        assert parca in desen, parca


# --- Devir 48: kanon bant metni çapı kenara yuvarlanmaz ---------------------
def test_t10_d48_kanon_bant_metni_pencerede_celismez():
    """d ∈ [0,49995; 0,5) mm'de ``:.4f`` '0.5000' basıyordu (gösterilen
    çap gösterilen kenara eşit, hüküm 'bandın dışında'). Ondalık artık
    gösterim hükümle çelişmeyene dek artar; pencere dışında 4 ondalık
    (bit-aynı; :1273 düğümü bu yüzden ÇEVRİLMEDİ). T10-M5 KIRMIZI."""
    from hrma.utils.injector_design import (KANON_BANT_METNI_CAP_ONDALIGI,
                                            _kanon_cap_ondaligi)
    params = {'d_min': 0.5e-3, 'd_max': 2.5e-3}
    for d_mm, yon in ((0.49996, -1), (0.499951, -1), (2.50004, 1)):
        k = _kanon_cap_ondaligi(d_mm * 1e-3, params)
        gosterim = float(f'{d_mm:.{k}f}')
        kenar = 0.5 if yon < 0 else 2.5
        assert (gosterim < kenar) if yon < 0 else (gosterim > kenar), (d_mm, k)
    for d_mm in (0.4665, 0.4649, 0.3, 3.1):
        assert _kanon_cap_ondaligi(d_mm * 1e-3, params) == (
            KANON_BANT_METNI_CAP_ONDALIGI), d_mm
    assert ('Solved orifice diameter {d_h * 1000:.{_kanon_cap_ondaligi('
            'd_h, params)}f} mm') in _oku(UTILS_INJ)


# --- Ana model kararı: kamara malzemesinin TEK varsayılanı ------------------
def _t10_kayit(j, alan):
    k = [x for x in (j.get('defaults_applied') or [])
         if isinstance(x, dict) and x.get('field') == alan]
    assert len(k) <= 1, k
    return k[0] if k else None


def test_t10_malzeme_sabiti_karar_degeri_ve_sablonun_secili_secenegi():
    """Kâhin: kayıtlı karar (ana model 10. tur — değer formun ekranda
    gösterdiği seçenek, AISI 304). Sunucunun ``/hybrid`` sayfası seçili
    seçeneği AYNI sabitten basar (şablonda ikinci varsayılan yok). T10-M7
    KIRMIZI."""
    from hrma.app import app
    from hrma.engines.hybrid_rocket_engine import HYBRID_CHAMBER_MATERIAL_DEFAULT
    assert HYBRID_CHAMBER_MATERIAL_DEFAULT == 'steel_304'
    app.config['TESTING'] = True
    with app.test_client() as ist:
        html = ist.get('/hybrid').get_data(as_text=True)
    m = re.search(r'<select id="chamber_material"[^>]*>(.*?)</select>', html, re.S)
    assert m, 'chamber_material seçicisi yok'
    secenekler = re.findall(r'<option value="([^"]+)"([^>]*)>', m.group(1))
    secili = [v for v, oz in secenekler if re.search(r'\bselected\b', oz)]
    assert secili == [HYBRID_CHAMBER_MATERIAL_DEFAULT], secenekler
    sablon = _oku(KOK / 'hrma' / 'templates' / 'advanced.html')
    # v3.0.1 kulvar M: seçenekler sunucu kaydından makroyla basılır; seçili
    # seçenek yine AYNI sabitten (şablonda elle yazılmış seçenek yok — bu
    # eski '{% if hybrid_chamber_material_default == ... %}' satırlarından
    # daha sıkı: ikinci varsayılanın yazılabileceği bir <option> kalmadı).
    assert ('malzeme_secenekleri(hybrid_materials.chamber_material, '
            'hybrid_chamber_material_default)') in sablon
    secici = sablon[sablon.index('<select id="chamber_material"'):]
    assert '<option' not in secici[:secici.index('</select>')]


def test_t10_malzeme_api_yolu_varsayilani_beyanli_ve_form_yoluyla_bit_ayni():
    """Alan gönderilmeyen API çağrısı formun gönderdiği malzemeyle (seçili
    seçenek) AYNI motoru verir — yapısal ve kütle blokları bit-aynı; uç
    varsayılanı ``defaults_applied``da ADIYLA beyan eder; alan
    gönderilince kayıt yok. Kâhin: form yolu (``chamber_material=steel_304``
    gönderen gövde). T10-M6 / T10-M8 KIRMIZI."""
    from hrma.data.materials_db import get_material_safe
    from hrma.engines.hybrid_rocket_engine import HYBRID_CHAMBER_MATERIAL_DEFAULT
    api = _t9_calculate('t10_malzemesiz', chamber_material=None)
    form = _t9_calculate('t10_malzeme_304', chamber_material='steel_304')
    kanonik = get_material_safe(HYBRID_CHAMBER_MATERIAL_DEFAULT)[1]
    assert api['motor']['chamber_material'] == kanonik
    assert form['motor']['chamber_material'] == kanonik
    for blok in ('structural_analysis', 'heat_transfer_analysis'):
        assert (json.dumps(api['motor'][blok], sort_keys=True, default=str)
                == json.dumps(form['motor'][blok], sort_keys=True,
                              default=str)), blok
    kayit = _t10_kayit(api, 'chamber_material')
    assert kayit is not None, api.get('defaults_applied')
    assert (kayit['value'], kayit['reason']) == (
        HYBRID_CHAMBER_MATERIAL_DEFAULT, 'not_supplied'), kayit
    assert "this server's own default" in kayit['message']
    assert api['structural_design_basis']['chamber_material_source'] == (
        f'default:{HYBRID_CHAMBER_MATERIAL_DEFAULT}')
    assert _t10_kayit(form, 'chamber_material') is None


@pytest.mark.parametrize('uc', ['/api/quick-geometry', '/api/transient-analysis'])
def test_t10_malzeme_kardes_uclarda_da_beyanli(uc):
    """Hızlı geometri ve geçici analiz uçları da aynı sabiti kullanır ve
    beyan eder (katalog taban yükü; malzeme alanı yok)."""
    from hrma.engines.hybrid_rocket_engine import HYBRID_CHAMBER_MATERIAL_DEFAULT
    from tests.support import uc_katalogu
    from hrma.app import app
    yuk = dict(uc_katalogu.taban_yuk(uc))
    yuk.pop('chamber_material', None)
    # ÖH 14 Eki (ana model): çağrı parametrize testin İÇİNDE — depo bekçisi
    # (test_d24 OH-D23-12 rota çıkarımı) fonksiyon parametresini çözemiyor,
    # parametrize adını çözüyor; ayrı yardımcı tavanı 23 → 24 yapmıştı.
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post(uc, json=yuk)
    assert cevap.status_code == 200, cevap.get_json()
    kayit = _t10_kayit(cevap.get_json(), 'chamber_material')
    assert kayit is not None and kayit['value'] == HYBRID_CHAMBER_MATERIAL_DEFAULT


def test_t10_bilinmeyen_malzeme_ayni_sabite_duser():
    """Tanınmayan ad da TEK sabite düşer (uyarı korunur; ikinci yedek yok).

    v3.0.1 kulvar M: ``/calculate`` tanınmayan adı artık ADLI 422 ile
    reddeder (eskiden bu yolla ss_304 sayıları yayımlanıyordu — once.json
    S4); düşüş yalnız motorun DOĞRUDAN kullanımında kalır ve o yol hâlâ TEK
    sabite düşer. İki iddia ayrı ayrı sınanır."""
    from hrma.app import app
    from hrma.data.materials_db import get_material_safe
    from hrma.engines.hybrid_rocket_engine import (
        HybridRocketEngine, HYBRID_CHAMBER_MATERIAL_DEFAULT)
    app.config['TESTING'] = True
    with app.test_client() as ist:
        r = ist.post('/calculate', json=dict(ORNEK_H1, chamber_material='peynir'))
    assert r.status_code == 422
    assert r.get_json()['invalid_fields'][0]['field'] == 'chamber_material'
    e = HybridRocketEngine.__new__(HybridRocketEngine)
    e.design_warnings = []
    assert e._resolve_chamber_material('peynir') == get_material_safe(
        HYBRID_CHAMBER_MATERIAL_DEFAULT)[1]
    uyari = [w for w in e.design_warnings
             if w.get('code') == 'warn.hybrid.chamber_material_unknown']
    assert uyari and uyari[0]['params']['used'] == HYBRID_CHAMBER_MATERIAL_DEFAULT


def test_t10_ornek_hibrit_malzemeyi_ve_tank_sicakligini_acikca_tasir():
    """Örnek = form yolu: kamara malzemesi alanı AÇIKÇA, tank sıcaklığı
    TEK sabitten; üretici literal taşımaz. T10-M11 KIRMIZI."""
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_CHAMBER_MATERIAL_DEFAULT, TANK_TEMPERATURE_DEFAULT_K)
    from tests.test_example_projects import load_example_doc
    alanlar = load_example_doc('hybrid')['inputs']['fields']
    assert alanlar['chamber_material'] == HYBRID_CHAMBER_MATERIAL_DEFAULT
    assert alanlar['oxidizer_temp'] == TANK_TEMPERATURE_DEFAULT_K
    uretici = _oku(KOK / 'examples' / 'generate_examples.py')
    assert 'HIBRIT_TANK_SICAKLIGI_K = TANK_TEMPERATURE_DEFAULT_K' in uretici
    assert "'chamber_material': HYBRID_CHAMBER_MATERIAL_DEFAULT" in uretici


# --- Devir 45: aynı yanıtta TEK tank sıcaklığı ------------------------------
def test_t10_d45_api_yolunda_plaka_ve_devre_ayni_sicaklikta():
    """ÖLÇÜLDÜ (9. tur I50od1): plaka 293 K (P_sat 50,373 bar), devre
    293,15 K (50,543 bar) — aynı yanıtta iki tank sıcaklığı. Artık uç
    yedeği, plaka yoğunluğu, plakanın P_v'si, devrenin P₁'i ve motorun
    giriş durumu TEK sabitte. Kâhin: CoolProp P_sat(T) (bağımsız EOS).
    T10-M9 KIRMIZI."""
    from hrma.engines.hybrid_rocket_engine import (TANK_PRESSURE_PSAT_REL_TOL,
                                                   TANK_TEMPERATURE_DEFAULT_K)
    j = _t9_calculate('t10_sicakliksiz_I50od1', thrust=50.0,
                      injector_type='impingement', orifice_diameter=1.0,
                      oxidizer_temp=None, **KANON_DISI_DP)
    kayit = _t10_kayit(j, 'oxidizer_temp')
    assert kayit is not None and kayit['value'] == TANK_TEMPERATURE_DEFAULT_K
    assert j['motor']['oxidizer_inlet_state']['temperature_K'] == (
        TANK_TEMPERATURE_DEFAULT_K)
    inj, idd = j['injector'], j['motor']['injector_design']
    assert f'at {TANK_TEMPERATURE_DEFAULT_K:.2f} K' in inj['density_source']
    assert inj['vapor_pressure_bar'] == idd['feed_pressure_bar']
    p_sat = _t9_coolprop_psat_bar(TANK_TEMPERATURE_DEFAULT_K)
    assert abs(idd['feed_pressure_bar'] - p_sat) / p_sat <= TANK_PRESSURE_PSAT_REL_TOL


def test_t10_d45_enjektor_sinifi_varsayilani_tek_kaynaktan():
    """``InjectorDesign`` sıcaklık verilmezse TEK sabiti kullanır; açık
    ``None`` eskisi gibi ADIYLA reddedilir. T10-M10 KIRMIZI."""
    import contextlib
    import io
    from hrma.engines.hybrid_rocket_engine import TANK_TEMPERATURE_DEFAULT_K
    from hrma.utils.injector_design import InjectorDesign
    with contextlib.redirect_stdout(io.StringIO()):
        d = InjectorDesign(mdot_ox=0.5, chamber_pressure=30.0, tank_pressure=50.0)
    assert d.oxidizer_temp == TANK_TEMPERATURE_DEFAULT_K
    with pytest.raises(ValueError, match='finite number in kelvin'):
        with contextlib.redirect_stdout(io.StringIO()):
            InjectorDesign(mdot_ox=0.5, chamber_pressure=30.0,
                           tank_pressure=50.0, oxidizer_temp=None)
    app_kaynak = _oku(APP_PY)
    assert "'oxidizer_temp': (TANK_TEMPERATURE_DEFAULT_K, 'K', 'not_supplied')" in app_kaynak
    assert "'tank_temperature', 293.15" not in app_kaynak
