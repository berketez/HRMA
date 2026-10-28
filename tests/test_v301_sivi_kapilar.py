"""v3.0.1 / V301/L-A — sıvı ucunun sunucu kapıları (SV-01/02/03/10/11/15 + SV-19 ek).

Bulgular: ``docs/scofield/raw/OH/V301/kati-sivi/denetim/A-sivi/RAPOR.md``;
kanıt ``docs/scofield/raw/OH/V301/kati-sivi/L-A/``.

  * SV-01: bant dışı / okunamaz / kesirli adet girdi 200 + başka değer DEĞİL,
    motordan ÖNCE 422 ``input_not_accepted`` (bant tek kaynak
    ``LIQUID_INPUT_BANDS``); oda çapı boğaza göre daralma bandı dışında ->
    422 ``chamber_diameter_out_of_band`` + en az / en çok çap.
  * SV-02: ``feed_pressure`` NaN / Infinity / dize / 1e9 -> adlı 422.
  * SV-03: basınç beslemeli tank < gerekli besleme basıncı -> 422
    ``pressure_fed_tank_below_required``; gerekli tank basıncı tek tanım
    (``injection_system.required_*`` = ``engine_cycle_solution.required_*``),
    8 bar pay ayrı alan; pompasız çevrimde ``max_tank_pressure`` yok.
  * SV-10: turbopompalı çevrimde ``feed_pressure`` chug kapısına girmez,
    ``inputs_not_used`` ile beyan edilir.
  * SV-11: ``fuel_boiling_point`` "informational" listesinde değil.
  * SV-15: sıvı sayfası ret gövdesini ortak çözücüyle (kod + cümle + adlı
    alanlar) ve etkin dilde basar; başarılı hesap eski hata bildirimini
    kaldırır.
  * SV-19 (ek): kapanmayan turbopompa çevrimi -> 422
    ``turbopump_cycle_not_closed``.
"""
import contextlib
import copy
import io
import json
import re
import subprocess
import warnings
from pathlib import Path

import pytest

from hrma.engines.liquid_rocket_engine import (
    INJECTOR_FEED_MARGIN_BAR,
    LIQUID_INPUT_BANDS,
    LIQUID_INPUT_COUNT_FIELDS,
    LiquidRocketEngine,
)

KOK = Path(__file__).resolve().parents[1]
LIQUID_HTML = KOK / 'hrma' / 'templates' / 'liquid.html'
MOTOR_PY = KOK / 'hrma' / 'engines' / 'liquid_rocket_engine.py'
I18N_PAGES = KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
#: A-sivi denetiminin Playwright ile alınmış GERÇEK form yükü (basınç
#: beslemeli, feed_pressure 130) + boş gelen üç zorunlu alan.
#: T-ÇAPA-C2 (27 Eki): yük tests/fikstur/v301/ altında (kaynak
#: docs/…/L-A/yuk_form_en.json ile md5 aynı). Eskiden docs yoksa elle yazılmış
#: bir alt kümeye (_YEDEK_FORM) sessizce düşülüyordu — docs'lu ve docs'suz
#: ağaç FARKLI yükle koşuyordu; tek kaynak artık fikstür.
FIKSTUR = KOK / 'tests' / 'fikstur' / 'v301'


def _form():
    yol = FIKSTUR / 'sivi_yuk_form_en.json'
    d = {k: v for k, v in json.loads(yol.read_text(encoding='utf-8')).items()
         if v is not None}
    d.update({'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5})
    return d


TURBO = {'turbopump_efficiency': 75, 'generator_gas_temp': 1000,
         'turbine_inlet_pressure': 150, 'turbine_expansion_ratio': 4}


def _govde(cevrim=None, **ek):
    d = copy.deepcopy(_form())
    if cevrim:
        d['engine_cycle'] = cevrim
        if cevrim != 'pressure_fed':
            d.update(TURBO)
    for k, v in ek.items():
        if v is KeyError:
            d.pop(k, None)
        else:
            d[k] = v
    return d


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, govde):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = istemci.post('/calculate_liquid', json=govde)
    return r.status_code, r.get_json()


@pytest.fixture()
def motor_cagrilmaz(monkeypatch):
    """Bant kapısı motordan ÖNCE koşar: motor kurulursa test kırılır."""
    import hrma.app as uygulama

    class _Yasak:
        def __init__(self, *a, **k):
            raise AssertionError('motor kuruldu: kapı motordan önce değil')
    monkeypatch.setattr(uygulama, 'LiquidRocketEngine', _Yasak)


# ---------------------------------------------------------------------------
# SV-01 — tek bant tablosu ve uç kapısı
# ---------------------------------------------------------------------------
def test_bantlar_tek_kaynaktan_okunur():
    """Motor bantları tablodan okur; satır içi bantlı çağrı kalmadı."""
    kaynak = MOTOR_PY.read_text(encoding='utf-8')
    satir_ici = re.findall(r"self\._override_val\(\s*'(\w+)'", kaynak)
    # Tek istisna kapak cıvatası: bandı aynı sabitten (bolt_count_range)
    # okuyan kendi çağrısı; tablo da o sabiti okur.
    assert satir_ici == ['closure_bolt_count'], satir_ici
    for alan in re.findall(r"self\._override_band\('(\w+)'\)", kaynak):
        assert alan in LIQUID_INPUT_BANDS, alan
    assert LIQUID_INPUT_COUNT_FIELDS <= set(LIQUID_INPUT_BANDS)


BANT_DISI = [
    ('combustion_efficiency', 150, 'out_of_accepted_range'),
    ('combustion_efficiency', 0.97, 'out_of_accepted_range'),
    ('nozzle_expansion_ratio', 1000, 'out_of_accepted_range'),
    ('contraction_ratio', 0.5, 'out_of_accepted_range'),
    ('characteristic_length', 20, 'out_of_accepted_range'),
    ('chamber_wall_thickness', -2, 'out_of_accepted_range'),
    ('cooling_channels', 3, 'out_of_accepted_range'),
    ('film_cooling_percent', 80, 'out_of_accepted_range'),
    ('coolant_flow_percent', 113, 'out_of_accepted_range'),
    ('safety_factor', 0.5, 'out_of_accepted_range'),
    ('coolant_inlet_temp', -50, 'out_of_accepted_range'),
    ('max_wall_temp', 5000, 'out_of_accepted_range'),
    ('fuel_density', 1e6, 'out_of_accepted_range'),
    ('injector_pressure_drop', 300, 'out_of_accepted_range'),
    ('fuel_boiling_point', 1400, 'out_of_accepted_range'),
    ('injector_elements', 2.5, 'not_a_whole_number'),
    ('cooling_channels', 40.5, 'not_a_whole_number'),
    ('fuel_density', 'abc', 'not_a_number'),
    ('safety_factor', True, 'boolean_is_not_a_number'),
    ('feed_pressure', 'NaN', 'not_finite'),
    ('feed_pressure', 'Infinity', 'not_finite'),
    ('feed_pressure', 'abc', 'not_a_number'),
    ('feed_pressure', 1e9, 'out_of_accepted_range'),
]


@pytest.mark.parametrize('alan,deger,neden', BANT_DISI)
def test_bant_disi_girdi_motordan_once_422(istemci, motor_cagrilmaz, alan,
                                           deger, neden):
    kod, g = _post(istemci, _govde(**{alan: deger}))
    assert kod == 422, g
    assert g['error'] == 'input_not_accepted'
    assert g['message'].startswith('No design was published')
    (kayit,) = [k for k in g['invalid_fields'] if k['field'] == alan]
    alt, ust, _, birim = LIQUID_INPUT_BANDS[alan]
    assert kayit['reason'] == neden
    assert (kayit['min'], kayit['max']) == (alt, ust)
    assert kayit['unit'] == (birim.strip() or None)
    assert kayit['motor_form'] == 'liquid'
    assert alan in g['message']


def test_turbopompali_cevrimde_feed_pressure_alt_ucu_da_kapida(
        istemci, motor_cagrilmaz):
    """Basınç beslemede alt uç chug kapısının (400) işidir; turbopompalıda
    o kapı koşmadığı için bant iki uçta da bu kapıdadır."""
    kod, g = _post(istemci, _govde('gas_generator', feed_pressure=-5))
    assert kod == 422 and g['invalid_fields'][0]['field'] == 'feed_pressure'


@pytest.mark.parametrize('deger,metin', [
    (-5, 'must be greater than chamber pressure'),
    (105, 'Insufficient pressure drop'),
])
def test_basinc_beslemede_mevcut_400_retleri_degismedi(istemci, deger, metin):
    kod, g = _post(istemci, _govde(feed_pressure=deger))
    assert kod == 400 and metin in g['error']
    assert g['invalid_fields'][0]['field'] == 'feed_pressure'


def test_oda_capi_bogazdan_kucukse_422_ve_en_kucuk_cap(istemci):
    kod, g = _post(istemci, _govde(chamber_diameter=20))
    assert kod == 422, g
    assert g['error'] == 'chamber_diameter_out_of_band'
    (k,) = g['invalid_fields']
    assert k['field'] == 'chamber_diameter' and k['value'] == 20.0
    # En küçük çap = d_t·sqrt(CR_min), yukarı yuvarlanmış: girilince geçer.
    alt_cr = LIQUID_INPUT_BANDS['contraction_ratio'][0]
    assert k['min'] >= k['throat_diameter_mm'] * alt_cr ** 0.5
    assert k['min'] - k['throat_diameter_mm'] * alt_cr ** 0.5 < 0.01
    assert f"{k['min']:.2f}" in g['message']


# ---------------------------------------------------------------------------
# SV-03 — basınç zinciri
# ---------------------------------------------------------------------------
def test_gerekli_tank_basinci_tek_tanim_ve_pay_ayri(istemci):
    kod, g = _post(istemci, _govde(feed_pressure=125))
    assert kod == 200, g
    inj = g['injection_system']
    cyc = g['detailed_feed_system']['engine_cycle_solution']
    assert inj['required_fuel_tank_pressure'] == \
        cyc['required_tank_pressure_fuel_bar']
    assert inj['required_ox_tank_pressure'] == \
        cyc['required_tank_pressure_ox_bar']
    assert inj['recommended_fuel_tank_pressure_with_margin'] == pytest.approx(
        cyc['required_tank_pressure_fuel_bar'] + INJECTOR_FEED_MARGIN_BAR)
    assert 'max_tank_pressure' not in g['turbopump_system']
    assert 'required_fuel_tank_pressure_terms' not in inj


@pytest.mark.parametrize('ek,kod_adi', [
    ({'feed_pressure': 115}, 'pressure_fed_tank_below_required'),
    ({'feed_pressure': 130, 'injector_pressure_drop': 30},
     'pressure_fed_tank_below_required'),
    ({'feed_pressure': KeyError}, 'pressure_fed_feed_pressure_not_supplied'),
])
def test_basinc_beslemeli_tank_yetersizse_422(istemci, ek, kod_adi):
    kod, g = _post(istemci, _govde(**ek))
    assert kod == 422, g
    assert g['error'] == kod_adi
    (k,) = g['invalid_fields']
    assert k['field'] == 'feed_pressure'
    assert k['min'] >= k['required_tank_pressure_bar']
    assert k['tank_pressure_margin_bar'] < 0
    if ek.get('feed_pressure') is KeyError:
        assert g['missing_fields'] == ['feed_pressure']


def test_chug_kapisi_ile_tank_kapisi_celismez(istemci):
    """İki kapı iki ayrı alt sınırdır; kabul = ikisinin büyüğünün üstü.

    Düşük enjektör ΔP'sinde (5 bar) gereksinim 1,15·Pc'nin altında kalır:
    o aralıkta yalnız chug kapısı (400) ateşler, 422 hiç doğmaz. Yüksek
    ΔP'de (30 bar) gereksinim üstte kalır: 422'nin önerdiği değer chug
    eşiğinin üstündedir, girilince ikisi de geçer.
    """
    kod, g = _post(istemci, _govde(feed_pressure=112,
                                   injector_pressure_drop=5))
    assert kod == 400 and 'Insufficient pressure drop' in g['error']
    kod, g = _post(istemci, _govde(feed_pressure=116,
                                   injector_pressure_drop=5))
    assert kod == 200, g
    kod, g = _post(istemci, _govde(feed_pressure=130,
                                   injector_pressure_drop=30))
    assert kod == 422
    en_az = g['invalid_fields'][0]['min']
    assert en_az > 115.0
    kod, g = _post(istemci, _govde(feed_pressure=en_az,
                                   injector_pressure_drop=30))
    assert kod == 200, g


# ---------------------------------------------------------------------------
# SV-10 / SV-11 / SV-19
# ---------------------------------------------------------------------------
def test_turbopompada_feed_pressure_engellemez_beyan_edilir(istemci):
    kod, g = _post(istemci, _govde('gas_generator', feed_pressure=50))
    assert kod == 200, g
    beyan = [b for b in g.get('inputs_not_used') or []
             if b.get('field') == 'feed_pressure']
    assert beyan and beyan[0]['reason'] == 'not_read_in_turbopump_cycle'
    assert g['injection_system']['required_fuel_tank_pressure'] is None


def test_fuel_boiling_point_bilgi_amacli_degil():
    assert 'fuel_boiling_point' not in \
        LiquidRocketEngine.unwired_inputs(None)['informational']


def test_kapanmayan_turbopompa_cevrimi_422(istemci):
    kod, g = _post(istemci, _govde('expander'))
    assert kod == 422, g
    assert g['error'] == 'turbopump_cycle_not_closed'
    assert 'warn.cycle.expander_fuel_unsupported' in g['message']
    assert g['invalid_fields'][0]['field'] == 'engine_cycle'


def test_guc_acigi_olan_expander_422_ve_acik_yazili(istemci):
    """Türbin gücü < pompa gücü (CH4/LOX expander, 10 kN, Pc 100): önce
    200 + not_converged (L-A once_expander_ek.json), şimdi 422 ve çözücünün
    güç açığı sayısı cümlede."""
    kod, g = _post(istemci, _govde('expander', fuel_type='methane',
                                   mixture_ratio=3.2))
    assert kod == 422, g
    (k,) = g['invalid_fields']
    assert k['reason'] == 'warn.cycle.expander_power_balance_infeasible'
    assert k['params']['deficit_mw'] > 0
    assert 'deficit_mw=' in g['message']


# ---------------------------------------------------------------------------
# SV-15 — ekran: ortak çözücü, TR deseni, eski hatanın temizlenmesi
# ---------------------------------------------------------------------------
def test_sayfa_ret_govdesini_ortak_cozucuyle_basar():
    html = LIQUID_HTML.read_text(encoding='utf-8')
    govde = re.search(r'async function calculateLiquid\(\)(.*?)\n        \}\n',
                      html, re.S).group(1)
    assert '_liquidRetMetni(results, response.status)' in govde
    assert '!response.ok' in govde
    assert "showError('Error: '" not in govde
    # Başarı yolu eski hesap hatalarını kaldırır (sonuç basılmadan önce).
    assert govde.index('_liquidHesapHatalariniTemizle();') < \
        govde.index('currentResults = results;')
    yardimci = re.search(r'function _liquidRetMetni\((.*?)\n        \}\n',
                         html, re.S).group(1)
    assert 'HRMAReject.metni' in yardimci
    assert 'serverText' in yardimci
    sozluk = I18N_PAGES.read_text(encoding='utf-8')
    for anahtar in ('liq.js.server_rejected', 'liq.js.error_prefix'):
        assert sozluk.count(f"'{anahtar}'") == 2, anahtar


from tests.test_app_hata_dili import (  # noqa: E402
    NODE, NODE_DUZENEGI, STATIC_JS, TURKCE_KARAKTER, needs_node)


@needs_node
def test_ret_cumleleri_turkcede_kesilmeden_cevrilir(istemci, tmp_path):
    vakalar = [
        _govde(combustion_efficiency=150, injector_elements=2.5,
               feed_pressure='abc'),
        _govde(chamber_diameter=20),
        _govde(feed_pressure=115),
        _govde(feed_pressure=KeyError),
        _govde('expander', fuel_type='methane', mixture_ratio=3.2),
        _govde(feed_pressure=90),
        _govde(feed_pressure=105),
        _govde(discharge_coefficient=1.2),
    ]
    cumleler = []
    for v in vakalar:
        kod, g = _post(istemci, v)
        assert kod in (400, 422), g
        cumleler.append(g.get('message') or g['error'])
    duzenek = tmp_path / 'srv.js'
    duzenek.write_text(NODE_DUZENEGI, encoding='utf-8')
    girdi = tmp_path / 'in.json'
    girdi.write_text(json.dumps(cumleler), encoding='utf-8')
    islem = subprocess.run(
        [NODE, str(duzenek), str(STATIC_JS), str(girdi)],
        capture_output=True, text=True, timeout=120)
    assert islem.returncode == 0, islem.stderr
    sonuc = json.loads(islem.stdout)
    assert sonuc['en'] == cumleler, 'EN kipinde metin değişti'
    for kaynak, tr in zip(cumleler, sonuc['tr']):
        assert tr != kaynak and TURKCE_KARAKTER.search(tr), (
            'çevrilmedi: %s' % kaynak)
    for tr in sonuc['tr'][:5]:
        assert tr.startswith('Tasarım yayımlanmadı'), tr
    # Ondalık kanonu ve alan adları.
    # V3.0.5 T-ÇAPA-C1: sayı EN kaynağın kendisinden okunur (zincirin gerekli
    # besleme basıncı bugün 124,48 bar, eski çapa 122,54 — hangi kulvarın
    # değiştirdiği çatallanmadı). Sınanan şey ondalık kanonu: EN '124.48' →
    # TR '124,48'.
    import re as _re
    en_sayi = _re.search(r'at least (\d+\.\d{2}) bar', cumleler[2]).group(1)
    tr_sayi = en_sayi.replace('.', ',')
    assert tr_sayi in sonuc['tr'][2] and en_sayi not in sonuc['tr'][2], (
        en_sayi, sonuc['tr'][2])
    assert 'injector_elements' in sonuc['tr'][0]
    assert 'tam sayı değil' in sonuc['tr'][0]
