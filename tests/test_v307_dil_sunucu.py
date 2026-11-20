"""V307/DİL-SUNUCU bekçisi (18 Kas 2026).

Sunucunun ürettiği ve Türkçe ekranda / PDF'te İngilizce kalan cümleler ile
kullanıcı metnindeki 'fabricated / uydurma' üslubu. Motor koşturmaz (basınçlı
kap çözümleyicisi kapalı biçimli ve hızlıdır). TR çeviri PDF'in kendi
çevirmeniyle (``rapor_sozluk.cevir``) ölçülür: bu çevirmen ekranın
``i18n_charts.js`` sözlüğünü ve dize şablonlu desenlerini DOSYADAN okur, yani
ekran ve PDF aynı kaynaktan Türkçeleşir.

Kanıt: docs/scofield/raw/OH/V307/dil-sunucu/RAPOR.md
"""
import ast
import pathlib
import re

import pytest

from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
from hrma.export import rapor_sozluk

KOK = pathlib.Path(__file__).resolve().parent.parent
HRMA = KOK / 'hrma'


def _dizgiler(yol):
    """Docstring dışı dizgi sabitleri (f-string parçaları dahil)."""
    agac = ast.parse(yol.read_text(encoding='utf-8'))
    ds = set()
    for d in ast.walk(agac):
        govde = getattr(d, 'body', None)
        if (isinstance(d, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)) and govde
                and isinstance(govde[0], ast.Expr)
                and isinstance(getattr(govde[0], 'value', None), ast.Constant)
                and isinstance(govde[0].value.value, str)):
            ds.add(id(govde[0].value))
    for d in ast.walk(agac):
        if (isinstance(d, ast.Constant) and isinstance(d.value, str)
                and id(d) not in ds):
            yield d.lineno, d.value


_INGILIZCE = re.compile(r'\b(the|is|are|this|that|which|with|not|and|from)\b')


def _tr(metin):
    return rapor_sozluk.cevir(metin, 'tr')


# --- kalem 2 + ÜB-4: basınçlı kap uyarı ve varsayım satırları ---------------

_KAP_VAKALARI = [
    dict(material='steel_4130', temperature_K=90.0, wall_thickness_mm=0.4,
         head_type='torispherical', code_mode='asme_viii'),
    dict(material='ss_304', temperature_K=90.0, wall_thickness_mm=None,
         head_type='ellipsoidal_2_1', code_mode='aiaa_s080'),
    dict(material='graphite', temperature_K=90.0, wall_thickness_mm=3.0,
         head_type='hemispherical', code_mode='aiaa_s080'),
    dict(material='titanium_6al4v', temperature_K=90.0, wall_thickness_mm=3.0,
         head_type='ellipsoidal_2_1', code_mode='nasa_std_5012c'),
    dict(material='aluminum_6061', temperature_K=600.0, wall_thickness_mm=3.0,
         head_type='ellipsoidal_2_1', code_mode='asme_viii'),
    dict(material='steel_4130', temperature_K=293.15, wall_thickness_mm=30.0,
         head_type='ellipsoidal_2_1', code_mode='asme_viii'),
]


@pytest.mark.parametrize('vaka', _KAP_VAKALARI,
                         ids=[f"{v['material']}-{v['temperature_K']:.0f}K"
                              for v in _KAP_VAKALARI])
def test_kap_uyari_ve_varsayimlari_turkce(vaka):
    r = PressureVesselAnalyzer().analyze(
        meop_bar=60.0, inner_diameter_mm=150.0, weld_efficiency=0.85, **vaka)
    satirlar = list(r['warnings']) + list(r['assumptions'])
    assert satirlar
    # Yalnız 'çevrildi mi' değil: PDF çevirmeni tanımadığı cümleyi parça parça
    # bırakabilir; TR çıktıda İngilizce işlev sözcüğü kalmamalı.
    kalan = [f'{s}\n  -> {_tr(s)}' for s in satirlar
             if _tr(s) == s or _INGILIZCE.search(_tr(s))]
    assert not kalan, 'TR karşılığı eksik kap satırı:\n' + '\n'.join(kalan)


def test_kap_kapak_uyarisinda_ham_anahtar_yok():
    r = PressureVesselAnalyzer().analyze(
        meop_bar=60.0, inner_diameter_mm=150.0, material='steel_4130',
        wall_thickness_mm=0.4, head_type='ellipsoidal_2_1')
    metin = ' '.join(r['warnings'] + r['assumptions'])
    assert 'HEAD UNDER-THICKNESS' in metin
    for ham in ('ellipsoidal_2_1', 'head_thickness_mm', 'cryogenic_ductility'):
        assert ham not in metin, ham


# --- kalem 3: 'fabricated' üslubu ------------------------------------------

#: Üslup değil, imalat adımı ("2. Fabricate internal structures").
_FABRICATE_IZINLI = {('export/cad_export.py', 'Fabricate internal structures')}


def test_fabricated_uslubu_kullanici_metninde_yok():
    bulunan = []
    for yol in sorted(HRMA.rglob('*.py')):
        for no, metin in _dizgiler(yol):
            if re.search(r'(?i)fabricat', metin):
                goreli = str(yol.relative_to(HRMA))
                if any(goreli == d and p in metin
                       for d, p in _FABRICATE_IZINLI):
                    continue
                bulunan.append(f'{goreli}:{no}: {metin[:90]}')
    assert not bulunan, '\n'.join(bulunan)


# --- kalem 1: FEA / CFD beyanlarında 'uydur*' -------------------------------

def test_fea_cfd_beyanlarinda_uydurma_ifadesi_yok():
    bulunan = []
    for alt in ('fea', 'cfd'):
        for yol in sorted((HRMA / alt).glob('*.py')):
            for no, metin in _dizgiler(yol):
                if re.search(r'(?i)uydur', metin):
                    bulunan.append(f'{alt}/{yol.name}:{no}: {metin[:90]}')
    assert not bulunan, '\n'.join(bulunan)


# --- kalem 4: N·s -----------------------------------------------------------

def test_kesilmis_kuyruk_cumlesi_n_nokta_s():
    kaynak = (HRMA / 'analysis' / 'transient_ballistics.py').read_text(
        encoding='utf-8')
    assert 'f"{artik_i:.0f} N·s, "' in kaynak
    assert 'N*s, ' not in kaynak


# --- kalem 10: irtifa 422 metni ---------------------------------------------

def test_irtifa_alt_sinir_metni_geometrik_tanimi_soyler():
    from hrma.app import app
    app.config['TESTING'] = True
    y = app.test_client().post('/api/altitude-to-pressure',
                               json={'altitude': -6000.0})
    assert y.status_code == 422
    mesaj = y.get_json()['message']
    assert 'geometric altitudes of -5000 m and above' in mesaj
    assert 'begin at -5000 m geopotential height' not in mesaj


# --- kalem 6: sıvı tasarım ortamı künyeleri ---------------------------------

def test_sivi_tasarim_ortami_kunyeleri_turkce():
    from hrma.engines import liquid_rocket_engine as L
    for ad in ('DESIGN_AMBIENT_BASIS', 'DESIGN_AMBIENT_SEA_LEVEL_BASIS',
               'FIXED_NOZZLE_SEPARATION_DESIGN_AMBIENT_BASIS'):
        metin = getattr(L, ad)
        tr = _tr(metin)
        assert tr != metin, ad
        assert 'design_ambient.sea_level' not in tr
        assert 'max_attached_expansion_ratio' not in tr


# --- kalem 5: PDF'te en sık İngilizce kalan cümleler -------------------------

_PDF_SIK = (
    'Advisory comparison only. It does not change any number HRMA publishes '
    '(the design is sized from the HRMA solver alone) and it applies no '
    'pass/fail threshold, because no sourced threshold exists for the '
    'difference between two equilibrium codes.',
    'Activate fire suppression system',
    'Evacuate upwind',
)


@pytest.mark.parametrize('metin', _PDF_SIK, ids=['cea', 'yangin', 'tahliye'])
def test_pdf_sik_cumleler_turkce(metin):
    assert _tr(metin) != metin


# --- kalem 4 (S4, S9): hibrit bağıntı ve τ gerekçesi ------------------------

def test_hibrit_zarf_bagintisi_ham_degisken_adi_tasimaz():
    kaynak = (HRMA / 'engines' / 'hybrid_rocket_engine.py').read_text(
        encoding='utf-8')
    govde = kaynak[kaynak.index('def _grain_sizing_formula(self):'):]
    govde = govde[:govde.index('\n    def ', 10)]
    assert 'D_grain_outer' not in govde and 't_residual' not in govde
    assert _tr('grain outer diameter = final port diameter + 2 × residual web') \
        == 'blok dış çapı = son port çapı + 2 × artık et'


def test_hibrit_tau_secimi_olculmedi_gerekcesi_turkce():
    agac = ast.parse((HRMA / 'engines' / 'hybrid_rocket_engine.py').read_text(
        encoding='utf-8'))
    metinler = [n.value for n in ast.walk(agac)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value.startswith(
                    'The tau-choice sensitivity block is NOT published: this')]
    assert len(metinler) == 1
    tr = _tr(metinler[0])
    assert tr.startswith('τ seçimi duyarlılık bloğu YAYIMLANMAZ')
    assert not _INGILIZCE.search(tr)


# --- kalem 6: güverte / analiz uçlarının adlı ret cümleleri -----------------

def test_ret_cumleleri_turkce_ve_uc_adi_yok():
    agac = ast.parse((HRMA / 'app.py').read_text(encoding='utf-8'))
    metinler = sorted({n.value for n in ast.walk(agac)
                       if isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and 'cannot be produced from' in n.value})
    assert len(metinler) >= 20
    kalan = [m for m in metinler if _tr(m) == m or _INGILIZCE.search(_tr(m))]
    assert not kalan, '\n'.join(kalan)
    assert not [m for m in metinler if 'endpoint' in m or '/calculate' in m]


# --- V307/DİL-SUNUCU-2 kalem 3: faydalı yük retleri (AĞIRLIK-MERKEZİ-2 DEVİR 2) --

def _yuk_ret_cumleleri():
    """Faydalı yük retlerinin GERÇEK cümleleri: component_cg'nin adlı retleri
    (uç ' Nothing was integrated.' ekler) + app.py payload_needs_component_cg."""
    from hrma.analysis import flight_vehicle as fv
    yerlesim = {'schema': fv.CG_LAYOUT_SCHEMA,
                'version': fv.CG_LAYOUT_SCHEMA_VERSION, 'stations_from': 'tail',
                'inert': [{'mass_kg': 10.0, 'x_from_tail_m': 0.4}],
                'propellant': [{'model': 'fixed', 'loaded_kg': 20.0,
                                'consumed_kg': 18.0, 'x_from_tail_m': 0.4}]}
    vakalar = [(20.0, 5.0, None), (20.0, 5.0, 3.25), (20.0, -1.0, 0.7),
               (20.0, 5.0, 0.0), (13.0, 5.0, 0.7)]
    cikti = {}
    for kuru, m, x in vakalar:
        with pytest.raises(fv.CgLayoutRejected) as e:
            fv.component_cg(yerlesim, 3.0, kuru, 18.0, payload_mass_kg=m,
                            payload_station_m=x)
        cikti.setdefault(e.value.code, []).append(
            str(e.value) + ' Nothing was integrated.')
    agac = ast.parse((HRMA / 'app.py').read_text(encoding='utf-8'))
    uc = [n.value for n in ast.walk(agac)
          if isinstance(n, ast.Constant) and isinstance(n.value, str)
          and n.value.startswith('The payload mass and station are placed')]
    assert len(uc) == 1
    cikti['payload_needs_component_cg'] = uc
    return cikti


def test_faydali_yuk_retleri_turkce():
    cumleler = _yuk_ret_cumleleri()
    assert set(cumleler) == {'PAYLOAD_INCOMPLETE', 'PAYLOAD_OUTSIDE_BODY',
                             'LAYOUT_NUMBER_INVALID',
                             'DRY_MASS_BELOW_ENGINE_AND_PAYLOAD',
                             'payload_needs_component_cg'}
    hepsi = [c for liste in cumleler.values() for c in liste]
    kalan = [f'{c}\n  -> {_tr(c)}' for c in hepsi
             if _tr(c) == c or _INGILIZCE.search(_tr(c))
             or 'payload_' in _tr(c)]
    assert not kalan, 'TR karşılığı eksik yük reddi:\n' + '\n'.join(kalan)
    # Sayı ondalık kanonundan geçer (3.25 → 3,25), değeri değişmez.
    assert '3,25 m' in _tr(cumleler['PAYLOAD_OUTSIDE_BODY'][0])


# --- V307/DİL-SUNUCU-2 kalem 1: DİL-EKRAN DEVİR'inin ekranda görünen cümleleri --

def test_yapisal_burkulma_ve_isil_not_turkce():
    """YAPISAL panel burkulma tablosu (external_pressure_model) ve ısıl not
    (service_temperature_basis) SRV'den geçer; TR karşılığı sözlükte."""
    kaynak = HRMA / 'analysis' / 'structural_analysis.py'
    metinler = {m for _, m in _dizgiler(kaynak)}
    adaylar = ['long-cylinder classical form (length-independent); '
               'conservative for short cylinders',
               'peak (inner-wall) metal temperature; strength derating uses '
               'the section-average temperature']
    # Cümleler kaynakta bitişik dize parçalarıdır; derleyici birleştirir.
    agac = ast.parse(kaynak.read_text(encoding='utf-8'))
    birlesik = {n.value for n in ast.walk(agac)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for a in adaylar:
        assert a in birlesik or a in metinler, a
        assert _tr(a) != a and not _INGILIZCE.search(_tr(a)), _tr(a)


def test_isil_koruma_ablatif_kunyeleri_turkce():
    from hrma.analysis.thermal_protection import ABLATIVE_MATERIALS
    kalan = [v['source'] for v in ABLATIVE_MATERIALS.values()
             if _tr(v['source']) == v['source']
             or _INGILIZCE.search(_tr(v['source']))]
    assert not kalan, kalan


def test_parametrik_baslik_ve_eksen_arayuz_taramalari_turkce():
    """Arayüzün sunduğu üç taramanın (advanced.html param_type) grafik başlığı
    ve x ekseni TR sözlükte; ad app.py'nin kendi eşlemesinden okunur."""
    from hrma import app as uygulama
    for p in ('of_ratio', 'chamber_pressure', 'expansion_ratio'):
        ad = uygulama._parametrik_eksen_adi(p)
        for metin in (ad, f'Parametric Analysis: {ad} Sweep'):
            tr = _tr(metin)
            assert tr != metin and not _INGILIZCE.search(tr), metin
            # Yarım çeviri de yok: başlığın İngilizce sözcükleri TR'de kalmaz.
            artik = [w for w in metin.replace(':', ' ').split()
                     if w not in ('O/F', 'L*') and w in tr.split()]
            assert not artik, (metin, tr, artik)


def test_yapisal_deger_kaynaklari_gerekceleri_turkce():
    """YAPISAL DEĞER KAYNAKLARI defterinin gerekçe hücreleri (DİL-EKRAN DEVİR 4).
    Sabit cümleler PDF çevirmeniyle de çevrilir; Türkçesi olmayan nesir
    yalnız bu bilinen kümede kalabilir (ikisi ekranda işlev gövdeli desenle
    çevrilir: istasyon listesi ve kapak türü; öbürleri defterde basılmıyor)."""
    from hrma.analysis.structural_analysis import StructuralAnalyzer
    r = StructuralAnalyzer().analyze_structure(
        {'chamber_pressure': 30.0, 'chamber_diameter': 0.12,
         'chamber_length': 0.4, 'throat_diameter': 0.03,
         'exit_diameter': 0.08, 'thrust': 3000.0, 'burn_time': 10.0},
        material='steel_4130')

    def gez(o, yol=''):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from gez(v, yol + '.' + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from gez(v, yol + '[%d]' % i)
        elif (isinstance(o, str) and len(o.split()) >= 5
              and _INGILIZCE.search(o)):
            yield yol, o

    nesir = list(gez(r))
    assert len(nesir) >= 40
    kalan = {y for y, s in nesir if _tr(s) == s or _INGILIZCE.search(_tr(s))}
    bilinen = {'.inputs_defaulted.nozzle_type.reason',
               '.fatigue_analysis.assumptions[2]',
               '.fatigue_analysis.assumptions[3]',
               '.weight_analysis.end_caps_weight_basis',
               '.safety_analysis.recommendation_basis',
               '.safety_analysis.design_target_assessment.basis',
               '.safety_analysis.minimum_safety_factor_verdict_basis',
               '.buckling_analysis.buckling_status_scope',
               '.material_properties.derating_curve.basis'}
    assert kalan <= bilinen, sorted(kalan - bilinen)


def test_sivi_oda_malzemesi_kunyeleri_turkce():
    """Sıvı formu Oda Malzemesi künyesi (KILAVUZ ÜB-5; DİL-EKRAN DEVİR 6):
    formun kendi seçenek kaydındaki her 'source' cümlesinin TR karşılığı var."""
    from hrma.app import _sivi_form_kaydi
    ops = _sivi_form_kaydi()['chamber_material']['options']
    kunyeler = [o['source'] for o in ops if o.get('source')]
    assert len(kunyeler) >= 8
    # Künyelerin İngilizce içerik sözcükleri (işlev sözcüğü taşımayan yarım
    # çeviriyi de yakalar; künye adları ve standart göstergeleri bunlar değil).
    icerik = re.compile(r'\b(Mechanical|Thermal|datasheets?|approximate|derating|'
                        r'fatigue|yield|melting|annealed|normalized|curves?|prior|'
                        r'elevated|temperature|assumption|aged|softening)\b')
    kalan = [k for k in kunyeler
             if _tr(k) == k or _INGILIZCE.search(_tr(k)) or icerik.search(_tr(k))]
    assert not kalan, kalan


# --- V307/DİL-SUNUCU-2 kalem 2: PDF'te kalan çözücü künyeleri (bugünkü kod) ---

_PDF_KUNYE_ONEKLERI = (
    'CF_vac x Pc x A_t integrated over the same thrust curve',
    'DELIVERED burn-averaged specific impulse of THIS run',
    'burn_time is the burn the motor actually sustains.',
    'oxidizer_mass is the LOADED mass:',
    'propellant_type_source names the INPUT',
    'total_impulse = thrust x burn_time:',
    "HRMA's theoretical solid thermochemistry",
    'NASA CEA equilibrium chamber gamma_s',
    'NASA CEA shifting-equilibrium expansion (condensed phase included) to',
    'solved: 1D RP-1 regenerative station march (thermal_protection',
)


def test_pdf_kunyeleri_bugunku_kaynaktan_turkce():
    """PDF'in çözücü künyeleri kaynaktaki BİREBİR sabitlerden okunur (bayat
    derlem değil); her birinin TR karşılığı var ve Türkçede ham alan adı yok."""
    sabitler = set()
    for yol in (HRMA / 'engines').glob('*.py'):
        for n in ast.walk(ast.parse(yol.read_text(encoding='utf-8'))):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                sabitler.add(n.value)
    for yol in (HRMA / 'analysis').glob('*.py'):
        for n in ast.walk(ast.parse(yol.read_text(encoding='utf-8'))):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                sabitler.add(n.value)
    eksik, kalan = [], []
    for onek in _PDF_KUNYE_ONEKLERI:
        bulunan = [s for s in sabitler if s.startswith(onek)]
        if not bulunan:
            eksik.append(onek)
        for s in bulunan:
            tr = _tr(s)
            if tr == s or _INGILIZCE.search(tr) or re.search(r'\b[a-z]+_[a-z_]+\b', tr):
                kalan.append(f'{s[:80]}\n  -> {tr[:120]}')
    assert not eksik, eksik
    assert not kalan, '\n'.join(kalan)


def test_pdf_bicimli_kunyeler_turkce():
    """Biçimli (sayı/ad taşıyan) PDF künyeleri: kaynaktaki f-dizgisinin sabit
    parçaları kaynakta durur ve örnek sayılarla kurulan cümle TR'ye iner."""
    kaynak = {
        'solid': (HRMA / 'engines' / 'solid_rocket_engine.py').read_text(encoding='utf-8'),
        'liquid': (HRMA / 'engines' / 'liquid_rocket_engine.py').read_text(encoding='utf-8'),
        'safety': (HRMA / 'analysis' / 'safety_analysis.py').read_text(encoding='utf-8'),
    }
    for ad, parca in (('solid', "'ratio, capped at 40 for separation/mass limits). This motor is '"),
                      ('solid', "and no user multiplier was supplied, so the '"),
                      ('liquid', "'. It is the term that closes Isp = C_F * c_star / '"),
                      ('safety', 'names a propellant CLASS, not a propellant: '),
                      ('safety', 'has no tabulated toxic component in HRMA, so no ')):
        assert parca in kaynak[ad], (ad, parca)
    bas = ("The value sent in propellant_type ('lox / htpb (oxidizer / fuel)') is not "
           'one of the propellant classes HRMA has a toxic inventory rule for and no '
           'tabulated component name was found in it, so the class below was taken '
           "from motor_type ('hybrid'), NOT from what you typed. ")
    ornekler = [
        'SUGGESTED vacuum-optimised nozzle (4x the sea-level expansion ratio, capped '
        'at 40 for separation/mass limits). This motor is not built with it: the '
        'delivered nozzle has eps = 10.417 and isp_vacuum is computed for THAT nozzle.',
        "X_p = 0.340 > 0 and no user multiplier was supplied, so the thrust "
        "coefficient carries NO two-phase factor at all (two_phase_efficiency_applied "
        "= 1.0) even though the solver's own models estimate a non-zero loss for "
        "this state.",
        bas + "'hybrid_n2o' names a propellant CLASS, not a propellant: the toxic "
        'inventory depends on which propellants are actually used (LOX/RP-1 and '
        "N2O4/MMH are both liquid bipropellants and are not comparable; a hybrid's "
        'inventory is set by its oxidiser). Name the propellant in propellant_type '
        "(for example 'hybrid_n2o n2o') to get an inventory.",
        bas + "'composite' has no tabulated toxic component in HRMA, so no toxic "
        'inventory is reported. SCOPE: this covers the stored propellant only. '
        'Combustion PRODUCTS (for example HCl and alumina from ammonium-perchlorate '
        'composites) are NOT inventoried by this analysis.',
    ]
    kalan = [o[:70] for o in ornekler if _tr(o) == o or 'payload_' in _tr(o)
             or re.search(r'\b(is|are|the|which)\b', _tr(o))]
    assert not kalan, kalan
    assert '10,417' in _tr(ornekler[0])


def test_hibrit_pdf_impuls_ve_modellenmeyen_beyani_turkce():
    """Hibrit teknik PDF'inin her vakada basılan iki künyesi (gerçek koşunun
    total_impulse_basis ve not_modelled_basis alanları) TR'ye iner."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    r = HybridRocketEngine(thrust=3000.0, burn_time=10.0, of_ratio=6.0,
                           chamber_pressure=30.0, atmospheric_pressure=1.0,
                           fuel_type='htpb', oxidizer_type='n2o',
                           track_performance=True).calculate()
    alanlar = ['not_modelled_basis']
    # Varsayılan N2O kendinden basınçlı tank boşalması dalı (ölçülen dal);
    # düzenlenmiş besleme dalının cümlesi bu kalemin kapsamında değil.
    if 'N2O self-pressurised tank blowdown' in r['total_impulse_basis']:
        alanlar.append('total_impulse_basis')
    for alan in alanlar:
        tr = _tr(r[alan])
        assert tr != r[alan] and not _INGILIZCE.search(tr), (alan, tr[:120])
        assert not re.search(r'\b[a-z]+_[a-z_]+\b', tr), (alan, tr[:200])
