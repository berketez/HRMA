"""Sıvı motor imalat bloğu dürüstlük bekçisi (2026-07-28, bulgu LIQ-MFG-4).

``_analyze_manufacturing_requirements`` dört sözlüğün tamamını literal
döndürüyordu ve sonuç ölü kod değildi: ``calculate_performance`` içinde
sonuç sözlüğüne ``manufacturing_analysis`` olarak giriyor, liquid.html
imalat kartında kullanıcıya basılıyordu. Yani 10 N'lik bir itici de
2 MN'lik bir booster motoru da ekranda aynı satırları görüyordu:

    'development': '$2M - $5M'      -> motorun itkisinden BAĞIMSIZ
    'production_unit': '$100k - $300k'
    'design_phase': '18 months'
    'throat_diameter': '±0.1mm'     -> boğaz çapından BAĞIMSIZ

Maliyet ve termin için bu projede tedarikçi fiyatı, işçilik ücreti ya da
program verisi YOKTUR; ölçeklenen bir korelasyon uydurmak yerine alanlar
kaldırıldı. Toleranslar ise motorun HESAPLANMIŞ nominal ölçüsünden
ISO 2768-1 tablosuyla aranır — yani girdi değişince çıktı da değişir.

Bu dosyanın ölçütü tektir:

    "Kullanıcı bu sayının kendi motoruna ait olduğuna inanır mı?
     İnanıyorsa, motoru değiştirince sayı DEĞİŞMELİDİR;
     değişemiyorsa sayı orada durmamalıdır."

Not: kurucuya ``propellant_data`` enjekte edilir — testler ağa çıkmaz.
"""

import contextlib
import io
import re
import warnings

import pytest

from hrma.engines.liquid_rocket_engine import (
    LiquidRocketEngine,
    ISO2768_MIN_NOMINAL_MM,
    _iso2768_feature,
    _iso2768_linear_tolerance_mm,
)

warnings.filterwarnings('ignore')

PROPELLANT_DATA = {'rp1': {}, 'lox': {}}

# Kaldırılan sınıfın imzaları: para birimi ve program takvimi.
FORBIDDEN_PATTERNS = (
    re.compile(r'\$'),                       # '$2M - $5M', '$100k - $300k'
    re.compile(r'\d\s*(months?|weeks?|yrs?|years?)\b', re.I),  # '18 months'
    re.compile(r'\d\s*-\s*\d+\s*units\b', re.I),               # '50 - 200 units'
    re.compile(r'±'),                        # '±0.1mm' sabit tolerans dizesi
)


def build(**ctor):
    """Sessiz motor koşusu — motor bol miktarda tanı çıktısı basıyor."""
    params = dict(thrust=10000.0, chamber_pressure=100.0, mixture_ratio=2.5,
                  fuel_type='rp1', oxidizer_type='lox',
                  propellant_data=PROPELLANT_DATA)
    params.update(ctor)
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(**params)
        result = engine.calculate_performance()
    return engine, result


@pytest.fixture(scope='module')
def small_engine():
    """500 N sınıfı itici — boğazı milimetrik."""
    return build(thrust=500.0)


@pytest.fixture(scope='module')
def large_engine():
    """500 kN sınıfı motor — boğazı desimetrik. Aynı ekranı görüyor."""
    return build(thrust=500000.0)


def walk_strings(obj, path='mfg'):
    """Sözlük/liste ağacındaki tüm dizeleri (yol, değer) olarak dolaşır."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk_strings(value, '{}.{}'.format(path, key))
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            yield from walk_strings(value, '{}[{}]'.format(path, i))
    elif isinstance(obj, str):
        yield path, obj


# ---------------------------------------------------------------------------
# 1) Kaldırılan alanlar geri gelmesin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('fixture_name', ['small_engine', 'large_engine'])
def test_cost_and_schedule_fields_are_gone(fixture_name, request):
    """Maliyet/termin sözlükleri kaldırıldı; geri eklenirse test kırılır."""
    _engine, result = request.getfixturevalue(fixture_name)
    mfg = result['manufacturing_analysis']
    for removed in ('estimated_costs', 'production_timeline',
                    'annual_production'):
        assert removed not in mfg, (
            '{} geri gelmiş: HRMA tedarikçi fiyatı/termin verisi tutmuyor, '
            'bu alan hesaplanamaz'.format(removed))


@pytest.mark.parametrize('fixture_name', ['small_engine', 'large_engine'])
def test_no_currency_or_schedule_literals(fixture_name, request):
    """Çıktının HİÇBİR dizesinde para birimi/takvim/sabit tolerans olmasın."""
    _engine, result = request.getfixturevalue(fixture_name)
    mfg = result['manufacturing_analysis']
    offenders = [
        (path, text) for path, text in walk_strings(mfg)
        # Alanın YOKLUĞUNU açıklayan durum dizesi denetim dışı: bir sayı
        # sunmuyor, tam tersine sunulmadığını söylüyor.
        if path != 'mfg.cost_and_schedule_status'
        for pattern in FORBIDDEN_PATTERNS if pattern.search(text)
    ]
    assert not offenders, 'uydurma maliyet/termin/tolerans dizesi: {}'.format(
        offenders)


def test_cost_status_says_not_calculated(small_engine):
    """Arayüz boş hücre yerine basabilsin diye yokluk açıkça raporlanır."""
    _engine, result = small_engine
    status = result['manufacturing_analysis']['cost_and_schedule_status']
    assert 'not calculated' in status.lower()


# ---------------------------------------------------------------------------
# 2) Toleranslar gerçek geometriden türesin
# ---------------------------------------------------------------------------

def test_tolerances_differ_between_engine_classes(small_engine, large_engine):
    """500 N ile 500 kN aynı tolerans tablosunu görmemeli."""
    small_feats = (small_engine[1]['manufacturing_analysis']
                   ['critical_tolerances']['features'])
    large_feats = (large_engine[1]['manufacturing_analysis']
                   ['critical_tolerances']['features'])

    small_throat = small_feats['throat_diameter']
    large_throat = large_feats['throat_diameter']

    # Nominal ölçüler sınıf farkını yansıtmalı (mm mertebesi -> dm mertebesi).
    assert large_throat['nominal_mm'] > 10 * small_throat['nominal_mm']
    # ISO sınıfı farklı aralığa düştüğü için sapma da farklılaşmalı.
    assert large_throat['tolerance_mm'] > small_throat['tolerance_mm']
    # Ve mühendislik anlamı ters yönde: küçük boğazda aynı atölye toleransı
    # alan (dolayısıyla itki) bandını çok daha fazla açar.
    assert (small_throat['throat_area_variation_percent']
            > large_throat['throat_area_variation_percent'])

    assert (large_feats['chamber_diameter']['nominal_mm']
            != small_feats['chamber_diameter']['nominal_mm'])


@pytest.mark.parametrize('fixture_name', ['small_engine', 'large_engine'])
def test_throat_nominal_equals_computed_geometry(fixture_name, request):
    """Nominal ölçü motorun kendi d_t'si olmalı — bağımsız bir sayı değil."""
    engine, result = request.getfixturevalue(fixture_name)
    feats = (result['manufacturing_analysis']['critical_tolerances']
             ['features'])
    assert feats['throat_diameter']['nominal_mm'] == pytest.approx(
        engine.d_t * 1000.0, rel=1e-6, abs=1e-3)
    assert feats['chamber_diameter']['nominal_mm'] == pytest.approx(
        result['chamber_diameter'], rel=1e-6, abs=1e-3)


@pytest.mark.parametrize('fixture_name', ['small_engine', 'large_engine'])
def test_throat_area_variation_is_derived(fixture_name, request):
    """dA/A = 2·dD/D ilişkisi gerçekten hesaplanıyor mu."""
    _engine, result = request.getfixturevalue(fixture_name)
    throat = (result['manufacturing_analysis']['critical_tolerances']
              ['features']['throat_diameter'])
    expected = 200.0 * throat['tolerance_mm'] / throat['nominal_mm']
    assert throat['throat_area_variation_percent'] == pytest.approx(
        expected, abs=0.01)


@pytest.mark.parametrize('fixture_name', ['small_engine', 'large_engine'])
def test_tolerance_basis_is_labelled(fixture_name, request):
    """Tolerans bir tasarım dağıtımı değil; kaynağı çıktıda yazmalı."""
    _engine, result = request.getfixturevalue(fixture_name)
    basis = (result['manufacturing_analysis']['critical_tolerances']['basis'])
    assert 'ISO 2768' in basis
    assert 'not a performance-driven' in basis.lower() or 'NOT a' in basis


def test_injector_orifice_tolerance_tracks_injector_design(small_engine):
    """Enjektör deliği toleransı enjektör hesabındaki çapa bağlı olmalı."""
    _engine, result = small_engine
    feats = (result['manufacturing_analysis']['critical_tolerances']
             ['features'])
    assert feats['fuel_injector_orifice']['nominal_mm'] == pytest.approx(
        result['injection_system']['fuel_orifice_diameter'], rel=1e-6,
        abs=1e-3)
    assert feats['oxidizer_injector_orifice']['nominal_mm'] == pytest.approx(
        result['injection_system']['ox_orifice_diameter'], rel=1e-6, abs=1e-3)


# ---------------------------------------------------------------------------
# 3) ISO 2768-1 tablosu
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('nominal_mm,grade,expected', [
    (1.0, 'f', 0.05), (3.0, 'f', 0.05), (3.0, 'm', 0.1),
    (6.0, 'f', 0.05), (6.01, 'f', 0.1), (30.0, 'f', 0.1), (30.0, 'm', 0.2),
    (30.5, 'f', 0.15), (120.0, 'm', 0.3), (200.0, 'f', 0.2),
    (400.0, 'm', 0.5), (900.0, 'f', 0.3), (1500.0, 'm', 1.2),
    (3000.0, 'm', 2.0),
])
def test_iso2768_table_values(nominal_mm, grade, expected):
    """Tablo sınır değerleri ISO 2768-1 ile birebir olmalı."""
    assert _iso2768_linear_tolerance_mm(nominal_mm, grade) == expected


@pytest.mark.parametrize('nominal_mm', [0.0, 0.2, 0.49, 5000.0, float('nan'),
                                        float('inf'), None, 'abc'])
def test_iso2768_out_of_scope_returns_none(nominal_mm):
    """Standardın kapsamı dışında tolerans UYDURULMAZ, None döner."""
    assert _iso2768_linear_tolerance_mm(nominal_mm, 'f') is None


def test_iso2768_min_nominal_boundary():
    """0.5 mm standardın alt sınırı: altında yok, üstünde var."""
    assert _iso2768_linear_tolerance_mm(ISO2768_MIN_NOMINAL_MM, 'f') == 0.05
    assert _iso2768_linear_tolerance_mm(
        ISO2768_MIN_NOMINAL_MM - 1e-6, 'f') is None


def test_iso2768_feature_marks_out_of_scope_dimension():
    """Kapsam dışı ölçüde sapma None kalır ve durumu yazılır (sessiz geçmez)."""
    entry = _iso2768_feature(0.25, 'f')
    assert entry['nominal_mm'] == 0.25
    assert entry['tolerance_mm'] is None
    assert 'outside' in entry['status']


def test_iso2768_feature_rejects_invalid_dimension():
    """Ölçü yoksa kayıt hiç üretilmez — sıfır/negatif nominal kabul edilmez."""
    assert _iso2768_feature(None, 'f') is None
    assert _iso2768_feature(0.0, 'f') is None
    assert _iso2768_feature(-3.0, 'f') is None


# ---------------------------------------------------------------------------
# 4) Üretim rotası konfigürasyonu izlesin
# ---------------------------------------------------------------------------

def test_processes_follow_cooling_choice():
    """Ablatif motora 'frezeli kanal + lehim' yazılmamalı."""
    _e_regen, regen = build(cooling_type='regenerative')
    _e_abl, ablative = build(cooling_type='ablative')

    regen_proc = regen['manufacturing_analysis']['manufacturing_processes']
    abl_proc = ablative['manufacturing_analysis']['manufacturing_processes']

    assert regen_proc['chamber'] != abl_proc['chamber']
    assert regen_proc['nozzle'] != abl_proc['nozzle']
    assert 'coolant channels' in regen_proc['chamber']
    assert 'ablative' in abl_proc['chamber'].lower()


@pytest.mark.parametrize('ctor', [
    {'feed_system_type': 'pressure_fed'},
    # Arayüzün gerçek yolu: çevrim override'ı feed_system_type'ı çeviriyor.
    {'overrides': {'engine_cycle': 'pressure_fed'}},
])
def test_pressure_fed_engine_has_no_turbomachinery_process(ctor):
    """Basınç beslemeli motorda 'investment cast impeller' gösterilmemeli."""
    _engine, result = build(**ctor)
    processes = result['manufacturing_analysis']['manufacturing_processes']
    assert 'impeller' not in processes['feed_system'].lower()
    assert 'no turbomachinery' in processes['feed_system'].lower()


def test_processes_follow_injector_choice():
    """Enjektör rotası seçilen enjektör tipini yansıtmalı."""
    _e_imp, impinging = build(injector_type='impinging')
    _e_pin, pintle = build(injector_type='pintle')
    imp_proc = impinging['manufacturing_analysis']['manufacturing_processes']
    pin_proc = pintle['manufacturing_analysis']['manufacturing_processes']
    assert imp_proc['injector'] != pin_proc['injector']
    assert 'pintle' in pin_proc['injector'].lower()


def test_process_route_is_labelled(small_engine):
    """Nitel rota hesaplanmış gibi sunulmasın: kaynağı çıktıda yazmalı."""
    _engine, result = small_engine
    basis = result['manufacturing_analysis']['manufacturing_processes_basis']
    assert 'not computed' in basis.lower()


# ---------------------------------------------------------------------------
# 5) Bağlantı bekçisi: blok hâlâ sonuç sözlüğüne giriyor mu
# ---------------------------------------------------------------------------

def test_manufacturing_block_is_wired_into_results(small_engine):
    """Arayüzün okuduğu anahtarlar yerinde olmalı (kart boş kalmasın)."""
    _engine, result = small_engine
    mfg = result['manufacturing_analysis']
    for key in ('manufacturing_processes', 'manufacturing_processes_basis',
                'critical_tolerances', 'cost_and_schedule_status'):
        assert key in mfg
    for key in ('chamber', 'nozzle', 'injector', 'feed_system'):
        assert mfg['manufacturing_processes'][key]


def test_standalone_call_matches_wired_call(small_engine):
    """Fonksiyon argümansız da çağrılabilmeli ve aynı sonucu vermeli."""
    engine, result = small_engine
    with contextlib.redirect_stdout(io.StringIO()):
        standalone = engine._analyze_manufacturing_requirements()
    assert (standalone['critical_tolerances']['features']['throat_diameter']
            == result['manufacturing_analysis']['critical_tolerances']
            ['features']['throat_diameter'])
