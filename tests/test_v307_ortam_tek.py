"""V307/ORTAM-TEK — hibrit varsayılan ortamının tek tanımı (19 Kas 2026).

Kanıt: docs/scofield/raw/OH/V307/ortam-tek/ (RAPOR.md, olcum/, betik/).

Kalem 2: ``/api/regen-cooling`` eksik zorunlu alan → adlı 422
(``incomplete_regen_input``); okunamayan sıcaklığın ve tasarım ortamı
kaydının ret nedeni gerekçe KANONUNDAN (emekli ``not_a_finite_number`` yok).
Kalem 3: kurucu, ``/api/quick-geometry`` ve ``/api/transient-analysis`` ortam
yokken ``HYBRID_DEFAULT_AMBIENT_BAR`` (ISA) kullanır ve bunu beyan eder.
Kalem 4: tasarım ortamının irtifa satırı Isp'si başlığın KENDİSİ (bit).
Kalem 5: hibrit İrtifa Performansı panelinde C_F tanım ipucu (EN + TR).

Hepsi Flask test istemcisi ya da kaynak okuması: tarayıcı, node, docs
kanıtı ya da yalnız macOS gerekmez (CI'da atlanmaz).
"""

import contextlib
import inspect
import io
import json
import math
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates' / 'advanced.html'

#: Hibrit sayfasının formunun gönderdiği tasarım ortamı (ölçüldü:
#: docs/scofield/raw/OH/V307/ortam-tek/olcum/form_ortam.json).
FORM_ORTAM_BAR = 1.01325


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, uc, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        return istemci.post(uc, data=json.dumps(govde),
                            content_type='application/json')


def _sozluk_degeri(yol, anahtar):
    """i18n sözlüğünden (EN, TR) değer çifti (ilk geçiş EN, ikinci TR)."""
    metin = yol.read_text(encoding='utf-8')
    desen = re.compile(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'")
    bulunan = desen.findall(metin)
    assert len(bulunan) == 2, (anahtar, len(bulunan))
    return bulunan[0], bulunan[1]


# ---------------------------------------------------------------- kalem 2
#: Sağlıklı rejen gövdesi — KÜÇÜKLER-2'nin aynı gövdesi (tek tanım).
from tests.test_v307_kucukler_2 import REGEN_GOVDE as REGEN  # noqa: E402


@pytest.mark.parametrize('eksik', [
    ('chamber_temperature',), ('chamber_pressure',), ('throat_diameter',),
    ('chamber_pressure', 'chamber_temperature', 'throat_diameter'),
])
def test_k2_rejen_eksik_zorunlu_alan_adli_422(istemci, eksik):
    govde = {k: v for k, v in REGEN.items() if k not in eksik}
    r = _post(istemci, '/api/regen-cooling', govde)
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'incomplete_regen_input'
    assert j['missing_fields'] == list(eksik)
    assert 'cooling' not in j
    assert 'is required' not in str(j)


@pytest.mark.parametrize('deger', ['', None])
def test_k2_rejen_bos_sicaklik_eksik_sayilir(istemci, deger):
    r = _post(istemci, '/api/regen-cooling',
              dict(REGEN, chamber_temperature=deger))
    assert r.status_code == 422
    assert r.get_json()['missing_fields'] == ['chamber_temperature']


@pytest.mark.parametrize('deger,neden', [
    ('NaN', 'not_a_json_number'), ('abc', 'not_a_json_number'),
    (True, 'boolean_is_not_a_number'), (math.nan, 'not_finite'),
    (-1.0, 'out_of_range'),
])
def test_k2_rejen_okunamayan_sicaklik_kanon_gerekcesi(istemci, deger, neden):
    r = _post(istemci, '/api/regen-cooling',
              dict(REGEN, chamber_temperature=deger))
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'invalid_regen_input'
    assert [f['reason'] for f in j['invalid_fields']] == [neden]


@pytest.mark.parametrize('ham,neden', [
    ({'mode': 'pressure', 'pressure_bar': True}, 'boolean_is_not_a_number'),
    ({'mode': 'pressure', 'pressure_bar': '1.0'}, 'not_a_json_number'),
    ({'mode': 'pressure', 'pressure_bar': math.nan}, 'not_finite'),
    ({'mode': 'altitude', 'altitude_m': math.inf}, 'not_finite'),
    ({'mode': 'pressure', 'pressure_bar': -1.0}, 'out_of_range'),
])
def test_k2_tasarim_ortami_kaydi_kanon_gerekcesi(ham, neden):
    from hrma.app import app, _tasarim_ortami_kaydi_oku
    with app.test_request_context():
        ortam, ret = _tasarim_ortami_kaydi_oku(ham)
        assert ortam is None and ret is not None and ret[1] == 422
        nedenler = [f['reason'] for f in ret[0].get_json()['invalid_fields']]
    assert nedenler == [neden]


def test_k2_guverte_eksik_rejen_kodunu_taniyor_tr_en():
    src = (JS / 'analysis_dock.js').read_text(encoding='utf-8')
    assert ("incomplete_regen_input: 'dock.err.incompleteRegenInput'"
            in src)
    en, tr = _sozluk_degeri(JS / 'i18n_common.js',
                            'dock.err.incompleteRegenInput')
    assert en != tr and re.search('[çğıİöşüÇĞÖŞÜ]', tr)
    yedek = re.search(r"incomplete_regen_input:\s*\n\s*'([^']*)'\s*\n\s*\+\s*"
                      r"'([^']*)'", src)
    assert yedek and (yedek.group(1) + yedek.group(2)) == en


# ---------------------------------------------------------------- kalem 3
def test_k3_kurucu_varsayilani_tek_ad():
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_DEFAULT_AMBIENT_BAR, HybridRocketEngine)
    imza = inspect.signature(HybridRocketEngine.__init__)
    assert imza.parameters['atmospheric_pressure'].default is \
        HYBRID_DEFAULT_AMBIENT_BAR
    assert HYBRID_DEFAULT_AMBIENT_BAR == FORM_ORTAM_BAR


def test_k3_uclarda_bir_bar_yedegi_kalmadi():
    """``/api/quick-geometry`` ve ``/api/transient-analysis`` gövdesinde
    ortamın yokluk yedeği yalnız tek addan okunur."""
    import hrma.app as a
    for islev in (a.quick_geometry, a.transient_analysis):
        kaynak = inspect.getsource(islev)
        assert "'atmospheric_pressure', 1.0" not in kaynak
        assert "'atmospheric_pressure', default=1.0" not in kaynak
        assert '_HYBRID_AMBIENT_DEFAULT_BAR' in kaynak


def test_k3_parametrik_yedegi_tek_ad():
    """``/parametric-analysis`` yalnız ``HybridRocketEngine`` kurar (ölçüldü:
    app.py tarama döngüsü); ortam yedeği hibrit motorun TEK adı, beyan
    künyesi aynı sayıyı yazar (ana model, 19 Kas: 4. yer)."""
    from hrma.app import _PARAMETRIK_UC_VARSAYILANLARI
    from hrma.engines.hybrid_rocket_engine import HYBRID_DEFAULT_AMBIENT_BAR
    deger, birim, neden = _PARAMETRIK_UC_VARSAYILANLARI['atmospheric_pressure']
    assert deger is HYBRID_DEFAULT_AMBIENT_BAR
    assert (birim, neden) == ('bar', 'not_supplied')


@pytest.mark.slow
def test_k3_parametrik_ortamsiz_beyan_isa(istemci):
    govde = {'thrust': 1000, 'burn_time': 10, 'chamber_pressure': 20.0,
             'of_ratio': 2.0, 'fuel_type': 'htpb', 'param_type': 'of_ratio',
             'param_start': 1.0, 'param_end': 3.0, 'param_steps': 3}
    j = _post(istemci, '/parametric-analysis', govde).get_json()
    beyan = [d for d in j.get('defaults_applied') or []
             if d.get('field') == 'atmospheric_pressure']
    assert len(beyan) == 1, j.get('defaults_applied')
    assert beyan[0]['value'] == FORM_ORTAM_BAR and beyan[0]['unit'] == 'bar'


QG = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0, 'fuel_type': 'htpb',
      'oxidizer_type': 'n2o', 'chamber_pressure': 25.0}
TR = {'thrust': 1000.0, 'burn_time': 8.0, 'of_ratio': 7.0,
      'chamber_pressure': 30.0, 'expansion_ratio': 0, 'fuel_type': 'htpb',
      'oxidizer_type': 'n2o', 'erosion_enabled': False}


@pytest.mark.slow
def test_k3_quick_geometry_ortamsiz_isa_ile_bit_ayni_ve_beyanli(istemci):
    yok = _post(istemci, '/api/quick-geometry', QG).get_json()
    isa = _post(istemci, '/api/quick-geometry',
                dict(QG, atmospheric_pressure=FORM_ORTAM_BAR)).get_json()
    for j in (yok, isa):
        assert j['status'] == 'success'
    for alan in ('isp', 'cf', 'throat_diameter', 'expansion_ratio'):
        assert yok['motor'][alan] == isa['motor'][alan], alan
    assert yok['motor']['design_ambient']['source'] == \
        'not_supplied_isa_sea_level'
    assert isa['motor']['design_ambient']['source'] != \
        'not_supplied_isa_sea_level'


@pytest.mark.slow
def test_k3_transient_ortamsiz_isa_ile_bit_ayni_ve_beyanli(istemci):
    yok = _post(istemci, '/api/transient-analysis', TR).get_json()
    isa = _post(istemci, '/api/transient-analysis',
                dict(TR, atmospheric_pressure=FORM_ORTAM_BAR)).get_json()
    assert yok['transient']['thrust'] == isa['transient']['thrust']
    assert (yok['transient']['erosion']['initial_throat_diameter_mm']
            == isa['transient']['erosion']['initial_throat_diameter_mm'])
    beyan = [d for d in yok.get('defaults_applied') or []
             if d.get('field') == 'atmospheric_pressure']
    assert len(beyan) == 1 and beyan[0]['value'] == FORM_ORTAM_BAR
    assert not [d for d in isa.get('defaults_applied') or []
                if d.get('field') == 'atmospheric_pressure']


# ---------------------------------------------------------------- kalem 4
def test_k4_baglama_islevi_yalniz_tasarim_satirina_dokunur():
    from hrma.engines.hybrid_rocket_engine import (
        bind_design_row_isp_to_headline)
    satirlar = [
        {'altitude': 0.0, 'pressure': 1.01325, 'isp': 1.0},
        {'altitude': 1000.0, 'pressure': 0.8987, 'isp': 2.0},
        {'altitude': 5000.0, 'pressure': 0.54, 'isp': None},
    ]
    bagli = bind_design_row_isp_to_headline(
        satirlar, 'pressure', 1e5, 'isp', 101325.0, 195.5)
    assert bagli == [satirlar[0]]
    assert [s['isp'] for s in satirlar] == [195.5, 2.0, None]


#: 300 N / 20 bar hibrit — HİBRİT-ORTAM'ın gövdesi (tek tanım), ISA tasarım
#: ortamı + 0–20 km İrtifa Profili.
from tests.test_v307_hibrit_ortam import HIBRIT_ORTAM_GOVDE  # noqa: E402
HIBRIT_300N = dict(HIBRIT_ORTAM_GOVDE, atmospheric_pressure=FORM_ORTAM_BAR,
                   altitude_profile={'start': 0, 'end': 20000, 'points': 5})


@pytest.mark.slow
def test_k4_isa_tasarimda_deniz_seviyesi_isp_ailesi_basligin_kendisi(istemci):
    """Ölçüm: olcum/k4_once.json (6 yaprak …534 ⟷ başlık …536) →
    k4_sonra.json (0 yaprak farklı)."""
    m = _post(istemci, '/calculate', HIBRIT_300N).get_json()['motor']
    isp = m['isp']
    ap = m['altitude_performance']
    assert ap['altitude_performance'][0]['altitude'] == 0.0
    aile = {
        'tablo 0 m': ap['altitude_performance'][0]['isp'],
        'tablo sea_level_isp': ap['sea_level_isp'],
        'sea_level_isp': m['sea_level_isp'],
        'design_ambient.isp_sea_level_s':
            m['design_ambient']['isp_sea_level_s'],
        'design_ambient.sea_level.isp_s':
            m['design_ambient']['sea_level']['isp_s'],
        'itki tablosu 0 m':
            m['thrust_altitude_analysis']['thrust_altitude_data'][0]['isp'],
        'İrtifa Profili 0 m':
            m['altitude_profile_performance']['rows'][0]['isp_s'],
    }
    farkli = {k: repr(v) for k, v in aile.items() if v != isp}
    assert not farkli, (repr(isp), farkli)
    # Tasarım satırı dışındaki satırlar başlığa bağlanmaz.
    assert ap['altitude_performance'][1]['isp'] != isp


# ---------------------------------------------------------------- kalem 5
def test_k5_cf_tanim_ipucu_ortak_bilesen_iki_dil():
    sablon = SABLON.read_text(encoding='utf-8')
    i = sablon.index('data-i18n="adv.txt.cfPureNozzleContribution"')
    li = sablon[i:sablon.index('</li>', i)]
    assert 'class="tooltip hrma-help"' in li
    assert 'class="tooltip-icon" tabindex="0" role="button"' in li
    assert 'data-i18n="adv.tip.cfAltitudeDefinition"' in li
    en, tr = _sozluk_degeri(JS / 'i18n_advanced.js',
                            'adv.tip.cfAltitudeDefinition')
    # Kodun gerçek tanımı: etkin boğaz (C_D = 0,98) ve itki oranı ölçeği.
    from hrma.engines.hybrid_rocket_engine import THROAT_DISCHARGE_COEFFICIENT
    assert THROAT_DISCHARGE_COEFFICIENT == 0.98
    assert 'CD = 0.98' in en and 'CD = 0,98' in tr
    assert 'Sutton & Biblarz' in en and 'Sutton & Biblarz' in tr
    assert 'F(h) / F,design' in en and 'F(h) / F,tasarım' in tr
    assert re.search('[çğıİöşüÇĞÖŞÜ]', tr)
    for metin in (en, tr):
        assert '/api/' not in metin and '_' not in metin
        assert 'uydur' not in metin.lower() and 'invent' not in metin.lower()
