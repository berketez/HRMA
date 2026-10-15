"""ÖH D37 · fizik-hazırlık · ON_sembolik — D35 ÖNEMLİ kalemlerinin geriye dönük
SEMBOLİK türetim bekçisi (OH-ON-01 plaka eğilmesi, OH-ON-02 izentropik ε).

Neden bu dosya
--------------
D35 ÖNEMLİ dalgası yayımlanan sayıları değiştirdi (plaka SF 4,107 → 0,550;
ε bandı (4, 250) → koşumun kendi Summerfield ekranı) ve Berke 22 Eylül'de
onayladı; ama kanıt paketinde 14 Eylül kuralının "sembolik (sympy) ya da Lean
türetimi" parçası YOKTU (defter taslağı bulgusu). Bu dosya o parçayı geriye
dönük kapatır: türetim betikleri ve 30 haneli çıktıları
``docs/scofield/raw/OH/D37/fizik-hazirlik/ON_sembolik/`` altındadır
(``on01_plaka_sympy.py`` → ``on01_turetim.json``, ``on02_izentropik_sympy.py``
→ ``on02_turetim.json``); bekçi o çıktıları OKUMAZ, gömer — docs/ yayın
dalına girmez (Berke 15 Eyl) ve 403 dosyalık docs bağımlılığı büyütülmez.

Tasarım kısıtları (ölçüldü, 23 Eylül 2026)
-------------------------------------------
* sympy ürün ya da test bağımlılığı DEĞİL (requirements*.txt'de yok; trimesh
  onu yalnız ``extra == "recommend"`` ile ister, build123d ayrı CI işinde).
  CI atlama bütçesi tam dolu (``tools/atlama_kapisi.py`` ATLAMA_BUTCESI = 76,
  ölçülen 75 + 1) ve modül düzeyi atlama "MODUL DUSTU" hatasıdır. Bu yüzden
  bekçi HİÇBİR koşulda atlamaz: sympy'nin ürettiği kapalı formlar (pycode) ve
  30 haneli referanslar dosyaya gömülüdür; sympy kuruluysa canlı türetim
  ayrıca koşar ve sonucu junit ``record_testsuite_property`` ile beyan edilir.
* Ürün fonksiyonu ``injector_plate_structural`` yapraklarını 3-4 haneye
  YUVARLAYARAK yayımlar; rel 1e-9 kıyas için kodun ifadesi dosyadan AST ile
  okunup yuvarlanmadan değerlendirilir (``inspect.getsource`` DEĞİL — taban
  kaydı dersi). Yayımlanan yuvarlanmış sayıyla eşitlik AYRI bir düğümde.
* Ters mutasyon KODA DOKUNMADAN: kapalı formun sabiti (3/4) ya da üssü
  ((γ+1)/(2(γ−1))) test içinde bozulunca kıyasın kırmızıya döndüğü ölçülür.

Kaynaklar (kanıt paketi: ON_sembolik/rapor.md)
----------------------------------------------
OH-ON-01: Timoshenko & Woinowsky-Krieger, *Theory of Plates and Shells*, §16
(ankastre dairesel plaka, M_r(a) = −q a²/8); Roark 7. baskı Tablo 11.2 durum
10b (ürün künyesi, ``hrma/utils/injector_design.py:1931``); ASME BPVC I PG-52
ligament verimi η = (p − d)/p. Kod: ``injector_design.py:1908-1909`` (p, η),
``:1926`` (t_req), ``:1954`` (σ).
OH-ON-02: Sutton & Biblarz 9. baskı Eş. 3-7 (p0/p–M), 3-14 (A/A*–M), 3-25
(ε–p/p0); NASA GRC izentropik bağıntılar sayfası Eş. 6 ve 9. Kod:
``hrma/flow/quasi1d.py:176-189, 230-242``; ``hrma/engines/hybrid_rocket_engine.py
:3914-3936`` (kapalı form kopyaları), ``:3954-3968`` (brentq), ``:4043-4048``
(ε_sep, k = ``hrma/flow/separation.SUMMERFIELD_FACTOR_DEFAULT``);
``hrma/engines/nozzle_design.py:110-125``.
"""
from __future__ import annotations

import ast
import math
import os
from fractions import Fraction

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.nozzle_design import NozzleDesigner
from hrma.flow import quasi1d
from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT
from hrma.utils import injector_design as ID
from hrma.utils.injector_design import injector_plate_structural

try:                      # sympy varsa canlı türetim de koşar; yoksa ATLANMAZ
    import sympy as _sympy
except ImportError:       # pragma: no cover — CI'da beklenen durum
    _sympy = None

REL_KOD = 1e-9            # görev şartı: türetim ⟷ kod ≥ 3 noktada rel 1e-9
REL_REF = 1e-12           # kapalı form ⟷ sympy 30 haneli referans

# ---------------------------------------------------------------------------
# sympy'nin ürettiği kapalı formlar (on01/on02_turetim.json ``pycode_*``;
# sympy 1.14.0). Canlı katman bunları yeniden türetip 30 haneyle kıyaslar.
# ---------------------------------------------------------------------------
PYCODE_SIGMA = '(3/4)*a**2*q/(eta*t**2)'
PYCODE_T_REQ = ('(1/2)*math.sqrt(3)*math.sqrt(SF)*a*math.sqrt(q)'
                '/(math.sqrt(eta)*math.sqrt(sigma_y))')
PYCODE_ETA = 'math.sqrt(n)*(math.sqrt(math.pi)*a/math.sqrt(n) - d)/(math.sqrt(math.pi)*a)'
PYCODE_EPS_SUTTON = ('pr**(-1/gamma)*((1/2)*gamma + 1/2)**(-1/(gamma - 1))'
                     '/(math.sqrt((1 - pr**((gamma - 1)/gamma))/(gamma - 1))*math.sqrt(gamma + 1))')
PYCODE_M_OF_PR = 'math.sqrt(2)*math.sqrt((pr**((1 - gamma)/gamma) - 1)/(gamma - 1))'
PYCODE_EPS_OF_M = '(2*(M**2*((1/2)*gamma - 1/2) + 1)/(gamma + 1))**((gamma + 1)/(2*gamma - 2))/M'


def _pycode(ifade: str, **degerler):
    return eval(ifade, {'math': math, '__builtins__': {}}, degerler)


# ---------------------------------------------------------------------------
# OH-ON-01 — girdiler (Ornek-H1, D35 a1 once.json / sonra.json koşul H1) ve
# 30 haneli sympy referansları (on01_turetim.json ``test_referanslari``)
# ---------------------------------------------------------------------------
H1 = dict(d_plate_m=Fraction('0.08068496'), t_m=Fraction('0.003'),
          sigma_y_Pa=240_000_000, SF_hedef=Fraction(4))
NOKTALAR_ON01 = {
    # ad: (ΔP bar, n, d_hole m, plaka çapı m, t m, σ_y Pa, SF hedef)
    'H1_sonra': (Fraction('30.5434'), 3, Fraction('0.0021115'), *H1.values()),
    'H1_once': (Fraction(4), 32, Fraction('0.0009055'), *H1.values()),
    'sentetik_8delik': (Fraction('12.5'), 8, Fraction('0.0015'), Fraction('0.1'),
                        Fraction('0.004'), 205_000_000, Fraction('2.5')),
    'sentetik_deliksiz': (Fraction('7.25'), 0, Fraction(0), Fraction('0.06'),
                          Fraction('0.0025'), 310_000_000, Fraction(3)),
}
REF_ON01 = {   # sympy 30 hane (on01_turetim.json)
    'H1_sonra': dict(sigma_MPa='436.578215148039454131605733656',
                     SF='0.549729674254631141188295370612',
                     t_req_mm='8.09238730364568735522889665428',
                     eta='0.948853704388871709700065482780'),
    'H1_once': dict(sigma_MPa='58.4366379053570729501518317926',
                    SF='4.10701246003747992223893300437',
                    t_req_mm='2.96065798190259743188959938241',
                    eta='0.928364892807086269386587803770'),
    'sentetik_8delik': dict(sigma_MPa='153.849629651027619818930176590',
                            SF='1.33246989586517166846414388515',
                            t_req_mm='5.47899990252854706667896446850',
                            eta='0.952126926351828078647206472808'),
    'sentetik_deliksiz': dict(sigma_MPa='78.3000000000000000000000000000',
                              SF='3.95913154533844189016602809706',
                              t_req_mm='2.17620934121104110942756917987',
                              eta='1'),
}
#: D35 a1'in yayımladığı yapraklar (once.json / sonra.json H1; 3-4 hane)
YAYIM_ON01 = {
    'H1_sonra': dict(bending_stress_MPa=436.578, safety_factor=0.550,
                     required_thickness_mm=8.092, ligament_efficiency=0.9489),
    'H1_once': dict(bending_stress_MPa=58.437, safety_factor=4.107,
                    required_thickness_mm=2.961, ligament_efficiency=0.9284),
}


def _plaka_kapali_form(dP_bar, n, d_m, d_plate_m, t_m, sigma_y_Pa, SF_hedef,
                       katsayi=Fraction(3, 4)):
    """Türetimin kapalı formu (Kirchhoff + ASME PG-52); ``katsayi`` ters
    mutasyon için parametredir (3/4 dışı = bozuk türetim)."""
    a = float(d_plate_m) / 2.0
    q = float(dP_bar) * 1e5
    if n > 0 and d_m > 0:
        p = math.sqrt(math.pi * a * a / n)
        eta = (p - float(d_m)) / p
    else:
        eta = 1.0
    k = float(katsayi)
    sigma = k * q * a * a / (float(t_m) ** 2 * eta)
    return dict(eta=eta, sigma_MPa=sigma / 1e6, SF=float(sigma_y_Pa) / sigma,
                t_req_mm=1000.0 * math.sqrt(k * q * a * a * float(SF_hedef)
                                            / (float(sigma_y_Pa) * eta)))


def _bagil(x, y):
    return abs(float(x) - float(y)) / abs(float(y))


# --- kodun ifadeleri: dosyadan AST ile, yuvarlanmadan ------------------------
_HEDEF_ADLAR = ('a', 'q', 'area_plate', 'pitch', 'eta', 't_required', 'sigma')


def _plaka_kod_ast_ifadeleri():
    """``injector_plate_structural`` gövdesindeki atamaları (a, q, area_plate,
    pitch, eta[IfExp], t_required, sigma) kaynak DOSYADAN okur."""
    yol = os.path.abspath(ID.__file__)
    agac = ast.parse(open(yol, encoding='utf-8').read(), filename=yol)
    fn = next(d for d in ast.walk(agac)
              if isinstance(d, ast.FunctionDef) and d.name == 'injector_plate_structural')
    ifadeler = {}
    for dugum in ast.walk(fn):
        if (isinstance(dugum, ast.Assign) and len(dugum.targets) == 1
                and isinstance(dugum.targets[0], ast.Name)
                and dugum.targets[0].id in _HEDEF_ADLAR):
            ad = dugum.targets[0].id
            if ad == 'eta' and not isinstance(dugum.value, ast.IfExp):
                continue                      # ``eta = 1.0`` ön ataması değil, IfExp
            ifadeler[ad] = compile(ast.fix_missing_locations(ast.Expression(body=dugum.value)),
                                   yol, 'eval')
    eksik = set(_HEDEF_ADLAR) - set(ifadeler)
    assert not eksik, f'kaynakta bulunamayan atama: {sorted(eksik)}'
    return ifadeler


def _plaka_kod_ast_degerlendir(dP_bar, n, d_m, d_plate_m, t_m, sigma_y_Pa, SF_hedef):
    """Kodun KENDİ ifadelerini (AST) aynı girdilerle yuvarlamadan hesaplar."""
    ifadeler = _plaka_kod_ast_ifadeleri()
    ns = dict(np=np, float=float, q_bar=float(dP_bar), d_plate=float(d_plate_m),
              t_plate=float(t_m), n=int(n), d_hole=float(d_m),
              hedef_sf=float(SF_hedef), sigma_y=float(sigma_y_Pa))
    for ad in ('a', 'q', 'area_plate'):
        ns[ad] = eval(ifadeler[ad], ns)
    if n > 0 and d_m > 0:
        ns['pitch'] = eval(ifadeler['pitch'], ns)
        ns['eta'] = eval(ifadeler['eta'], ns)
    else:
        ns['eta'] = 1.0
    ns['t_required'] = eval(ifadeler['t_required'], ns)
    ns['sigma'] = eval(ifadeler['sigma'], ns)
    return dict(eta=ns['eta'], sigma_MPa=ns['sigma'] / 1e6,
                SF=ns['sigma_y'] / ns['sigma'], t_req_mm=ns['t_required'] * 1000.0)


def _sigma_katsayisi_kaynaktan():
    """``sigma = 0.75 * q * a ** 2 / ...`` satırındaki literal (AST)."""
    fn_kaynak = open(os.path.abspath(ID.__file__), encoding='utf-8').read()
    fn = next(d for d in ast.walk(ast.parse(fn_kaynak))
              if isinstance(d, ast.FunctionDef) and d.name == 'injector_plate_structural')
    for dugum in ast.walk(fn):
        if (isinstance(dugum, ast.Assign) and isinstance(dugum.targets[0], ast.Name)
                and dugum.targets[0].id == 'sigma'):
            sabitler = [c.value for c in ast.walk(dugum.value)
                        if isinstance(c, ast.Constant) and isinstance(c.value, float)]
            assert sabitler, 'sigma atamasında kayan noktalı literal yok'
            return sabitler[0]
    raise AssertionError('sigma ataması bulunamadı')


# ---------------------------------------------------------------------------
# OH-ON-02 — girdiler ve referanslar (on02_turetim.json ``test_referanslari``)
# ---------------------------------------------------------------------------
NOKTALAR_ON02 = {   # ad: (γ, p/p0)
    'H1_sep': (Fraction('1.1457'), Fraction(1, 50)),      # k·Pa/Pc = 0,4·1/20
    'H1_adapte': (Fraction('1.1457'), Fraction(1, 20)),   # Pa/Pc
    'H4_sep': (Fraction('1.1373'), Fraction(2, 25)),      # 0,4·1/5
    'H4_adapte': (Fraction('1.1373'), Fraction(1, 5)),
    'sentetik': (Fraction('1.2'), Fraction('0.005')),
    'sentetik2': (Fraction('1.4'), Fraction('0.1')),
}
REF_ON02 = {   # sympy 30 hane
    'H1_sep': '7.80977556033727028147241057599',
    'H1_adapte': '3.90414347241400437882771955436',
    'H4_sep': '2.80895505403192565967689430141',
    'H4_adapte': '1.53105556030255819450756282905',
    'sentetik': '20.2179952163716229159805536839',
    'sentetik2': '1.93067774180968203418727012380',
}
#: Yayımlanan HAM ekran değerleri (sonra.json ``genlesme.ekseni``) ve ε_sep'ten
#: geri çözülen γ (nsolve, 20 hane): olcum.py γ'yı 4 haneye yuvarladığından
#: yayımla 4 hanede eşitlik ancak γ_ham ile aranır (4 haneli γ ile fark ~1e-5).
HAM_ON02 = {
    'H1': dict(gamma_ham=1.1457062684634255633, Pc_bar=20.0, Pa_bar=1.0,
               eps_sep_ham=7.8096786507029154, eps_adapte_yayim=3.9041,
               Pe50_bar_ham=0.039374610653528555),
    'H4': dict(gamma_ham=1.1373338934671288346, Pc_bar=5.0, Pa_bar=1.0,
               eps_sep_ham=2.8088437438021785, eps_adapte_yayim=1.5310),
}


def _eps_sutton(pr, gamma, ust=None):
    """ε(p/p0, γ) — Sutton 3-25 kapalı formu. ``ust`` verilirse [(γ+1)/2]
    çarpanının üssü (normali 1/(γ−1)) ters mutasyon için değiştirilir."""
    pr, g = float(pr), float(gamma)
    u = 1.0 / (g - 1.0) if ust is None else float(ust)
    return 1.0 / (((g + 1.0) / 2.0) ** u * pr ** (1.0 / g)
                  * math.sqrt((g + 1.0) / (g - 1.0) * (1.0 - pr ** ((g - 1.0) / g))))


def _eps_alan_mach(pr, gamma):
    """İki temel bağıntının bileşimi: M(p/p0) → A/A*(M)."""
    pr, g = float(pr), float(gamma)
    M = math.sqrt(2.0 / (g - 1.0) * (pr ** (-(g - 1.0) / g) - 1.0))
    return (1.0 / M) * ((2.0 / (g + 1.0)) * (1.0 + 0.5 * (g - 1.0) * M * M)) ** ((g + 1.0) / (2.0 * (g - 1.0)))


# ---------------------------------------------------------------------------
# Boyut defteri (sympy'siz): SI taban üsleri {kg, m, s}
# ---------------------------------------------------------------------------
class _B:
    def __init__(self, **us):
        self.us = {k: Fraction(v) for k, v in us.items() if v}

    def __mul__(self, o):
        return _B(**{k: self.us.get(k, 0) + o.us.get(k, 0) for k in set(self.us) | set(o.us)})

    def __truediv__(self, o):
        return _B(**{k: self.us.get(k, 0) - o.us.get(k, 0) for k in set(self.us) | set(o.us)})

    def __pow__(self, n):
        return _B(**{k: v * Fraction(n) for k, v in self.us.items()})

    def __eq__(self, o):
        return self.us == o.us

    def __repr__(self):
        return 'boyutsuz' if not self.us else ' '.join(f'{k}^{v}' for k, v in sorted(self.us.items()))


BIRIMSIZ, M_, PA_ = _B(), _B(m=1), _B(kg=1, m=-1, s=-2)


# ===========================================================================
# OH-ON-01
# ===========================================================================
@pytest.mark.parametrize('ad', list(NOKTALAR_ON01))
def test_ON01_kod_AST_ifadesi_turetimle_ve_sympy_referansiyla_eslesir(ad):
    """Kodun kendi ifadeleri (dosyadan AST, yuvarlanmamış) ⟷ kapalı form ⟷
    sympy 30 hane: dört noktada σ, SF, t_req, η — rel 1e-9 şartı, ölçülen
    ~1e-16 (1e-12 ile kilitlenir)."""
    girdi = NOKTALAR_ON01[ad]
    kod = _plaka_kod_ast_degerlendir(*girdi)
    kf = _plaka_kapali_form(*girdi)
    for k in ('eta', 'sigma_MPa', 'SF', 't_req_mm'):
        assert _bagil(kod[k], kf[k]) < REL_REF, (ad, k, kod[k], kf[k])
        assert _bagil(kf[k], float(REF_ON01[ad][k])) < REL_REF, (ad, k, kf[k], REF_ON01[ad][k])


def test_ON01_sigma_literali_tam_3_bolu_4():
    """``sigma = 0.75 * …`` literali AST ile okunur; 0.75 = 3·2⁻² kayan noktada
    TAM olduğu için türetimdeki 3/4 ile yuvarlama farkı yoktur."""
    assert Fraction(_sigma_katsayisi_kaynaktan()) == Fraction(3, 4)


@pytest.mark.parametrize('ad', ['H1_sonra', 'H1_once'])
def test_ON01_urun_fonksiyonu_D35_yayimini_ve_kapali_formu_verir(ad):
    """Ürün fonksiyonu (yuvarlanmış yapraklar) D35 a1'in yayımladığı sayıları
    ve kapalı formun aynı yuvarlamasını verir — SF 4,107 → 0,550 bu bekçide
    iki yoldan (kapalı form + ürün) yeniden üretilir."""
    dP, n, d, dpl, t, sy, sf = NOKTALAR_ON01[ad]
    rapor = injector_plate_structural(
        float(dP), float(dpl), {'yield_strength': float(sy), 'name': 'ss_316'},
        material_name='ss_316', plate_thickness_m=float(t), n_holes=n,
        hole_diameter_m=float(d), required_sf=float(sf))
    assert rapor['status'] == 'analyzed'
    kf = _plaka_kapali_form(dP, n, d, dpl, t, sy, sf)
    beklenen = dict(bending_stress_MPa=round(kf['sigma_MPa'], 3), safety_factor=round(kf['SF'], 3),
                    required_thickness_mm=round(kf['t_req_mm'], 3), ligament_efficiency=round(kf['eta'], 4))
    for k, v in beklenen.items():
        assert rapor[k] == v, (ad, k, rapor[k], v)
        assert rapor[k] == YAYIM_ON01[ad][k], (ad, k, rapor[k], YAYIM_ON01[ad][k])
    assert rapor['model'] == 'Roark Table 11.2 case 10b (clamped circular plate)'


def test_ON01_ikinci_yol_olcekleme_ve_kalinlik_orani():
    """İkinci yol: σ_sonra = σ_önce·(ΔP_sonra/ΔP_önce)·(η_önce/η_sonra) ve
    t_req = t·√(SF_hedef/SF) — kapalı formdan bağımsız iki özdeşlik."""
    o = _plaka_kapali_form(*NOKTALAR_ON01['H1_once'])
    s = _plaka_kapali_form(*NOKTALAR_ON01['H1_sonra'])
    olcek = o['sigma_MPa'] * (30.5434 / 4.0) * (o['eta'] / s['eta'])
    assert _bagil(olcek, s['sigma_MPa']) < REL_REF
    for kf in (o, s):
        assert _bagil(3.0 * math.sqrt(4.0 / kf['SF']), kf['t_req_mm']) < REL_REF
    assert round(s['SF'], 3) == 0.550 and round(o['SF'], 3) == 4.107


def test_ON01_boyut_analizi():
    """σ = ¾ q a²/(t² η) → Pa; t_req = √(¾ q a² SF/(σ_y η)) → m; η = (p−d)/p → 1;
    p = √(A/n) → m."""
    q, a, t, sigma_y = PA_, M_, M_, PA_
    p = (M_ ** 2 / BIRIMSIZ) ** Fraction(1, 2)
    eta = (p / p)            # (p − d)/p: p ve d aynı boyutta → oran boyutsuz
    assert p == M_ and eta == BIRIMSIZ
    assert q * a ** 2 / (t ** 2 * eta) == PA_
    assert (q * a ** 2 * BIRIMSIZ / (sigma_y * eta)) ** Fraction(1, 2) == M_


# ===========================================================================
# OH-ON-02
# ===========================================================================
@pytest.mark.parametrize('ad', list(NOKTALAR_ON02))
def test_ON02_kod_kopyalari_kapali_formla_ve_sympy_referansiyla_eslesir(ad):
    """Sutton 3-25 kapalı formu ⟷ kodun ÜÇ kopyası (quasi1d, hibrit
    staticmethod'ları, nozzle_design) ⟷ iki temel bağıntının bileşimi ⟷
    sympy 30 hane — altı noktada rel 1e-9 (ölçülen ~1e-15)."""
    g, pr = NOKTALAR_ON02[ad]
    gf, prf = float(g), float(pr)
    kapali = _eps_sutton(pr, g)
    assert _bagil(kapali, float(REF_ON02[ad])) < REL_REF, (ad, kapali, REF_ON02[ad])
    assert _bagil(_eps_alan_mach(pr, g), kapali) < REL_REF
    kod = {
        'quasi1d': quasi1d.area_ratio_from_mach(quasi1d.mach_from_pressure_ratio(1.0 / prf, gf), gf),
        'hibrit': HybridRocketEngine._area_ratio_from_mach(
            HybridRocketEngine._mach_from_pressure_ratio(prf, gf), gf),
        'nozzle_design': NozzleDesigner.area_ratio_from_mach(
            NozzleDesigner.mach_from_pressure_ratio(1.0 / prf, gf), gf),
    }
    for k, v in kod.items():
        assert _bagil(v, kapali) < REL_KOD, (ad, k, v, kapali)


def test_ON02_kok_arayan_yol_kapali_formla_bilesince_kimlik_verir():
    """Kodun brentq yolu (ε → p/p0) kapalı formla (p/p0 → ε) bileşince ε'yi
    geri verir: ε = 50, γ = 1,1457 (D35 H5 koşulu; P_e 0,0394 bar)."""
    g = 1.1457
    pr50 = HybridRocketEngine._pressure_ratio_at_area_ratio(None, 50.0, g)   # gövde self okumaz
    assert _bagil(_eps_sutton(pr50, g), 50.0) < REL_KOD
    M50 = quasi1d.mach_from_area_ratio(50.0, g)
    pr50_q = (1.0 + 0.5 * (g - 1.0) * M50 * M50) ** (-g / (g - 1.0))
    assert _bagil(pr50_q, pr50) < REL_KOD
    assert round(20.0 * pr50, 4) == 0.0394


@pytest.mark.parametrize('ad', ['H1', 'H4'])
def test_ON02_ekran_epsilon_sep_yayimlanan_ham_degeri_ve_adapte_epsilonu_verir(ad):
    """ε_sep = ε(k·P_a/P_c, γ) (kod :4043-4048, k tek kaynaktan): γ_ham ile
    yayımlanan HAM ε_sep bit düzeyine yakın (1e-12), aynı γ tam adapte ε'yi
    yayımlanan 4 haneyle verir; H1'de ε = 50 çıkış basıncı ham yayımla 1e-9."""
    c = HAM_ON02[ad]
    k = SUMMERFIELD_FACTOR_DEFAULT
    pr_sep = k * c['Pa_bar'] / c['Pc_bar']
    eps_sep = _eps_sutton(pr_sep, c['gamma_ham'])
    assert _bagil(eps_sep, c['eps_sep_ham']) < 1e-12
    kod = HybridRocketEngine._area_ratio_from_mach(
        HybridRocketEngine._mach_from_pressure_ratio(pr_sep, c['gamma_ham']), c['gamma_ham'])
    assert _bagil(kod, eps_sep) < REL_KOD
    assert round(_eps_sutton(c['Pa_bar'] / c['Pc_bar'], c['gamma_ham']), 4) == c['eps_adapte_yayim']
    if 'Pe50_bar_ham' in c:
        M50 = quasi1d.mach_from_area_ratio(50.0, c['gamma_ham'])
        gh = c['gamma_ham']
        Pe50 = c['Pc_bar'] * (1.0 + 0.5 * (gh - 1.0) * M50 * M50) ** (-gh / (gh - 1.0))
        assert _bagil(Pe50, c['Pe50_bar_ham']) < REL_KOD


def test_ON02_boyutsuzluk_ve_geometrik_taban():
    """ε = A_e/A_t → m²/m² = 1; p/p0 → Pa/Pa = 1; M = 1'de ε = 1 (Lean çapası
    ``HRMA.areaRatio_at_sonic``; kodda ``expansion_ratio_supersonic_floor = 1.0``)."""
    assert M_ ** 2 / M_ ** 2 == BIRIMSIZ and PA_ / PA_ == BIRIMSIZ
    for g in (1.1457, 1.1373, 1.2, 1.4):
        assert _bagil(quasi1d.area_ratio_from_mach(1.0, g), 1.0) < REL_REF
        assert _bagil(HybridRocketEngine._area_ratio_from_mach(1.0, g), 1.0) < REL_REF
    # p/p0 → 1⁻ iken M → 0⁺ ve ε → ∞; p/p0 = 1'de kod None (hibrit) / 0 (quasi1d)
    assert HybridRocketEngine._mach_from_pressure_ratio(1.0, 1.2) == 0.0
    assert HybridRocketEngine._mach_from_pressure_ratio(1.5, 1.2) is None


# ===========================================================================
# TERS MUTASYON — koda dokunmadan, bekçinin duyarlılığı
# ===========================================================================
def _bekci_on01_kirmizi_mi(katsayi):
    """Kapalı formun sabiti ``katsayi`` ile bozulunca kod ⟷ türetim kıyası
    (rel 1e-9) DÜŞER mi? True = bekçi kırmızıya döner."""
    for girdi in NOKTALAR_ON01.values():
        kod = _plaka_kod_ast_degerlendir(*girdi)
        kf = _plaka_kapali_form(*girdi, katsayi=katsayi)
        if any(_bagil(kod[k], kf[k]) >= REL_KOD for k in ('sigma_MPa', 'SF', 't_req_mm')):
            return True
    return False


def _bekci_on02_kirmizi_mi(ust_fn):
    """[(γ+1)/2] üssü ``ust_fn(γ)`` ile bozulunca kod ⟷ türetim kıyası düşer mi?"""
    for g, pr in NOKTALAR_ON02.values():
        gf, prf = float(g), float(pr)
        kod = quasi1d.area_ratio_from_mach(quasi1d.mach_from_pressure_ratio(1.0 / prf, gf), gf)
        if _bagil(kod, _eps_sutton(pr, g, ust=ust_fn(gf))) >= REL_KOD:
            return True
    return False


def test_TERS_MUTASYON_sabit_bozulunca_bekci_kirmizi():
    """Mutasyonsuz: yeşil. 3/4 → 0,74 (ya da 1/2, Roark 10a basit mesnet 3/8'in
    yakını) ve üs 1/(γ−1) → 1/γ ya da 2/(γ−1): kırmızı. Kod değişmedi."""
    assert not _bekci_on01_kirmizi_mi(Fraction(3, 4))
    assert _bekci_on01_kirmizi_mi(Fraction('0.74'))
    assert _bekci_on01_kirmizi_mi(Fraction(3, 8))
    assert not _bekci_on02_kirmizi_mi(lambda g: 1.0 / (g - 1.0))
    assert _bekci_on02_kirmizi_mi(lambda g: 1.0 / g)
    assert _bekci_on02_kirmizi_mi(lambda g: 2.0 / (g - 1.0))


# ===========================================================================
# sympy canlı katman — ATLAMAZ: sympy yoksa gömülü pycode ifadeleri (sympy'nin
# kendi çıktısı) kapalı formla kıyaslanır ve durum junit'e yazılır.
# ``record_testsuite_property``: ``record_property`` CI'ın ``--junitxml``
# (xunit2) ailesiyle PytestWarning üretir (ölçüldü: shim koşumunda 1 uyarı);
# süit düzeyi özellik xunit2 şemasına uyar.
# ===========================================================================
def test_SYMPY_turetimi_dondurulmus_pycode_ve_canli(record_testsuite_property):
    # (1) sympy'nin ürettiği pycode dizeleri (gömülü) ⟷ el yazımı kapalı formlar
    for girdi in NOKTALAR_ON01.values():
        dP, n, d, dpl, t, sy, sf = girdi
        a, q, tt = float(dpl) / 2, float(dP) * 1e5, float(t)
        kf = _plaka_kapali_form(*girdi)
        if n > 0:
            assert _bagil(_pycode(PYCODE_ETA, n=n, a=a, d=float(d)), kf['eta']) < REL_REF
        assert _bagil(_pycode(PYCODE_SIGMA, a=a, q=q, eta=kf['eta'], t=tt) / 1e6, kf['sigma_MPa']) < REL_REF
        assert _bagil(1000 * _pycode(PYCODE_T_REQ, SF=float(sf), a=a, q=q, eta=kf['eta'], sigma_y=float(sy)),
                      kf['t_req_mm']) < REL_REF
    for g, pr in NOKTALAR_ON02.values():
        gf, prf = float(g), float(pr)
        assert _bagil(_pycode(PYCODE_EPS_SUTTON, pr=prf, gamma=gf), _eps_sutton(pr, g)) < REL_REF
        M = _pycode(PYCODE_M_OF_PR, pr=prf, gamma=gf)
        assert _bagil(_pycode(PYCODE_EPS_OF_M, M=M, gamma=gf), _eps_sutton(pr, g)) < REL_REF

    # (2) sympy kuruluysa CANLI türetim: Kirchhoff'tan σ_max ve iki bağıntıdan
    #     Sutton 3-25; 30 haneli referanslarla ilk 24 hane aynı olmalı.
    if _sympy is None:
        record_testsuite_property('sympy_canli', 'hayır — sympy kurulu değil; dondurulmuş '
                                                 'sympy çıktısı (pycode + 30 hane) kullanıldı')
        return
    sp = _sympy
    record_testsuite_property('sympy_canli', f'evet — sympy {sp.__version__}')
    r, a, q, D, nu, t, eta, n, d = sp.symbols('r a q D nu t eta n d', positive=True)
    w = q * (a**2 - r**2)**2 / (64 * D)

    def lap(f):
        return sp.diff(f, r, 2) + sp.diff(f, r) / r

    assert sp.simplify(lap(lap(w)) - q / D) == 0
    M_r = -D * (sp.diff(w, r, 2) + nu * sp.diff(w, r) / r)
    assert sp.simplify(M_r.subs(r, a) + q * a**2 / 8) == 0
    sigma = sp.simplify(6 * sp.Abs(M_r.subs(r, a)) / t**2) / eta
    assert sp.simplify(sigma - sp.Rational(3, 4) * q * a**2 / (t**2 * eta)) == 0
    p_ = sp.sqrt(sp.pi * a**2 / n)
    eta_ifade = (p_ - d) / p_
    dP, n_, d_, dpl, t_, sy, sf = NOKTALAR_ON01['H1_sonra']
    sub = {a: sp.Rational(dpl) / 2, q: sp.Rational(dP) * 10**5, t: sp.Rational(t_), n: n_, d: sp.Rational(d_)}
    eta_v = eta_ifade.subs(sub)
    sig_v = sp.N((sigma.subs(eta, eta_v).subs(sub)) / 10**6, 30)
    assert str(sig_v)[:24] == REF_ON01['H1_sonra']['sigma_MPa'][:24], (str(sig_v), REF_ON01['H1_sonra']['sigma_MPa'])
    g, M, pr, x = sp.symbols('gamma M pr x', positive=True)
    eps_M = (1 / M) * ((2 / (g + 1)) * (1 + (g - 1) / 2 * M**2)) ** ((g + 1) / (2 * (g - 1)))
    eps_S = 1 / (((g + 1) / 2) ** (1 / (g - 1)) * pr ** (1 / g)
                 * sp.sqrt((g + 1) / (g - 1) * (1 - pr ** ((g - 1) / g))))
    oran = sp.powsimp(sp.powdenest(eps_M.subs(M, sp.sqrt(2 / (g - 1) * (1 / x - 1)))
                                   / eps_S.subs(pr, x ** (g / (g - 1))), force=True), force=True)
    oran = sp.simplify(sp.simplify(oran).replace(
        lambda e: e.is_Pow, lambda e: sp.Pow(e.base, sp.simplify(sp.together(e.exp)))))
    assert oran == 1, oran
    gh, prh = NOKTALAR_ON02['H1_sep']
    eps_v = sp.N(eps_S.subs({g: sp.Rational(gh), pr: sp.Rational(prh)}), 30)
    assert str(eps_v)[:24] == REF_ON02['H1_sep'][:24], (str(eps_v), REF_ON02['H1_sep'])
