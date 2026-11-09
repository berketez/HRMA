"""V306/KATI-TANE — katı tanenin sınıf bantları ve port şeklinin yığılması.

Kaynak: docs/scofield/raw/OH/V306/ana-model/brif_04kas/KATI_TANE.md,
kanıt docs/scofield/raw/OH/V306/kati-tane/ (RAPOR, tane_once/sonra.json).

* K1 — çatlak riski (SF 2 / 1) ve ısıl uyum (0,25 / 0,6) bantları
  kaynaksızdı. Yerine NASA SP-8073 §2.5.5 Denk. (46) emniyet payı
  (MS = kapasite / gerinim − 1; MS < 0 kapasite aşılır) ve §3.5.5 Denk. (57)
  ısıl hasar artımı (D = ısıl gerinim / kapasite; D >= 1 ısıl yük tek başına
  aşar). Doğrusal çözümün küçük-gerinim eşiği aşıldığında hüküm tane kesiti
  FEA'sının kuralıyla verilir.
* K2 — star / finocyl / slotted / wagon_wheel için kaynaksız nominal
  Kt = 2,0 kalktı. Port poligonu keskin köşelidir; köşe yığılması çözülmez
  (FEA'nın kabul büyüklüğü oturmaz, ölçüldü). Çözücü dairesel port
  gerinimini ve kapasitenin izin verdiği en büyük yığılma katsayısını basar;
  hüküm yalnız dairesel port gerinimi kapasiteyi zaten aşıyorsa verilir.
  Dairesel port (bates) sayıları BİT-AYNI.
"""
import contextlib
import io
import json
import pathlib
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
ORNEK = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'
MOTOR = KOK / 'hrma' / 'engines' / 'solid_rocket_engine.py'
SOLID = KOK / 'hrma' / 'templates' / 'solid.html'
I18N = KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
I18N_ORTAK = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
PANEL = KOK / 'hrma' / 'static' / 'js' / 'fea_panel.js'

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node yok')

#: Taban (700a67586) ölçümü — docs/scofield/raw/OH/V306/kati-tane/
#: tane_once.json; örnek Ø75/32 KNDX, 60 bar. Dairesel port BİT-AYNI kalır.
TABAN_BATES = {
    'cartridge_loaded': {'bore_strain_percent': 0.5313122972958315,
                         'strain_safety_factor': 3.764264464005831},
    'case_bonded': {'bore_strain_percent': 2.363906802182426,
                    'strain_safety_factor': 0.8460570434306223},
}


def _alanlar():
    return json.loads(ORNEK.read_text(encoding='utf-8'))['inputs']['fields']


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _kati(client, **ek):
    govde = dict(_alanlar(), **ek)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = client.post('/calculate_solid', json=govde)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _gs(j):
    return j['structural_analysis']['grain_structural']


# ---------------------------------------------------------------------------
# K1 — kaynaklı sınıf ölçütü
# ---------------------------------------------------------------------------
def test_k1_kaynaksiz_bant_kalmadi():
    kaynak = MOTOR.read_text(encoding='utf-8')
    # Eski bant kenarları ve sınıf adları motorda atanmıyor.
    for eski in ("crack_risk = 'Low'", "crack_risk = 'Medium'",
                 "crack_risk = 'High'", "thermal_compat = 'Good'",
                 "thermal_compat = 'Marginal'", "thermal_compat = 'Poor'",
                 'strain_margin_kt >= 2.0', 'thermal_ratio < 0.25',
                 'thermal_ratio < 0.6', 'GRAIN_STRESS_CONCENTRATION = {',
                 'GRAIN_STRESS_CONCENTRATION.get('):
        assert eski not in kaynak, eski


@pytest.mark.parametrize('yer', ['cartridge_loaded', 'case_bonded'])
def test_k1_sinif_sp8073_ms_sifir(client, yer):
    g = _gs(_kati(client, grain_support=yer, chamber_pressure=60))
    sf = g['strain_safety_factor']
    assert abs(g['bore_strain_percent']) <= 100 * g['small_strain_limit']
    assert g['crack_propagation_risk'] == (
        'capability_exceeded' if sf < 1.0 else 'capability_not_exceeded')
    assert g['strain_margin_of_safety'] == pytest.approx(sf - 1.0, abs=0)
    assert 'SP-8073' in g['crack_propagation_risk_basis']
    assert 'eq. (46)' in g['crack_propagation_risk_basis']
    assert 'eq. (57)' in g['thermal_expansion_compatibility_basis']
    for alan in ('crack_propagation_risk_basis',
                 'thermal_expansion_compatibility_basis'):
        assert 'unsourced' not in g[alan]


def test_k1_sinir_tam_bir_de(client):
    """Depolama sıcaklığı taramasında (gövdeye yapıştırılmış, 40 bar; ısıl
    pay kürleme 398 K'den uzaklaştıkça büyür; kabul aralığı 180-340 K) SF
    1,3'ten 1'in altına iner: sınıf tam SF = 1'de değişir, eski 2,0
    kenarında DEĞİŞMEZ (1-2 arası noktalar 'aşılmıyor')."""
    goruldu, sf_1_2 = set(), []
    for ts in (340, 335, 325, 315, 305, 295):
        g = _gs(_kati(client, grain_support='case_bonded',
                      chamber_pressure=40, ambient_temp=ts))
        sf = g['strain_safety_factor']
        goruldu.add(g['crack_propagation_risk'])
        assert (g['crack_propagation_risk'] == 'capability_exceeded') == \
            (sf < 1.0), (ts, sf)
        if 1.0 <= sf < 2.0:
            sf_1_2.append(sf)
    assert goruldu == {'capability_exceeded', 'capability_not_exceeded'}
    # Eski 'Medium' bandına düşen noktalar var ve hepsi 'aşılmıyor'
    assert sf_1_2, 'tarama 1-2 aralığını kesmeli'


def test_k1_isil_hasar_artimi(client):
    yap = _gs(_kati(client, grain_support='case_bonded', chamber_pressure=60))
    kar = _gs(_kati(client, grain_support='cartridge_loaded',
                    chamber_pressure=60))
    d = yap['thermal_bore_strain_ratio']
    assert d == pytest.approx(abs(yap['thermal_only_bore_strain_percent'])
                              / yap['strain_capability_percent'], rel=1e-12)
    assert yap['thermal_expansion_compatibility'] == (
        'thermal_exceeds_capability' if d >= 1.0
        else 'thermal_within_capability')
    # Kartuş yüklü: kısıtlı büzülme yok, D = 0
    assert kar['thermal_bore_strain_ratio'] == 0.0
    assert kar['thermal_expansion_compatibility'] == \
        'thermal_within_capability'


def test_k1_kucuk_gerinim_disinda_hukum_fea_kurali(client):
    """Bates APCP Ø100/30 gövdeye yapıştırılmış 40 bar: port gerinimi %5
    eşiğinin üstünde, kapasite (%35) eşiğin içinde ulaşılmıyor → sınıf
    VERİLMEZ (FEA aynı tanede 'undetermined'); eskiden SF 5,6 'Low'."""
    g = _gs(_kati(client, propellant_type='apcp', burn_rate_preset='',
                  outer_diameter=100, core_diameter=30,
                  grain_support='case_bonded', chamber_pressure=40,
                  grain_type='bates'))
    assert abs(g['bore_strain_percent']) > 100 * g['small_strain_limit']
    assert g['strain_capability_percent'] > 100 * g['small_strain_limit']
    assert g['crack_propagation_risk'] == \
        'not_determined_beyond_small_strain'


# ---------------------------------------------------------------------------
# K2 — port şeklinin yığılması
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('yer', ['cartridge_loaded', 'case_bonded'])
def test_k2_bates_bit_ayni(client, yer):
    g = _gs(_kati(client, grain_support=yer, chamber_pressure=60))
    t = TABAN_BATES[yer]
    assert g['bore_strain_percent'] == t['bore_strain_percent']
    assert g['strain_safety_factor'] == t['strain_safety_factor']
    assert g['stress_concentration_factor'] == 1.0
    assert g['stress_concentration_status'] == 'circular_port'
    assert g['circular_port_bore_strain_percent'] == t['bore_strain_percent']
    assert g['allowable_concentration_factor'] == t['strain_safety_factor']


@pytest.mark.parametrize('tip', ['star', 'finocyl', 'slotted', 'wagon_wheel'])
def test_k2_kose_yigilmasi_uydurulmaz(client, tip):
    bates = _gs(_kati(client, grain_support='cartridge_loaded',
                      chamber_pressure=60))
    g = _gs(_kati(client, grain_support='cartridge_loaded',
                  chamber_pressure=60, grain_type=tip, fin_length='',
                  fin_width='', slot_depth='', slot_width=''))
    assert g['stress_concentration_factor'] is None
    assert g['stress_concentration_status'] == 'not_resolved'
    for alan in ('bore_strain_percent', 'strain_safety_factor',
                 'max_grain_stress_mpa', 'structural_efficiency',
                 'strain_margin_of_safety'):
        assert g[alan] is None, alan
    assert 'sharp corners' in g['bore_strain_percent_basis']
    # Dairesel port çözümü aynı port yarıçapı ve yüklerle bates'in kendisi
    assert g['circular_port_bore_strain_percent'] == \
        bates['bore_strain_percent']
    assert g['allowable_concentration_factor'] == \
        bates['strain_safety_factor']
    # Dairesel port gerinimi kapasitenin altında → hüküm verilmez
    assert g['allowable_concentration_factor'] >= 1.0
    assert g['crack_propagation_risk'] == 'not_determined_port_shape'
    assert 'nominal stress-concentration factor of' not in g['model_note']


def test_k2_alt_sinir_asilinca_hukum_ve_adli_uyari(client):
    j = _kati(client, grain_support='case_bonded', chamber_pressure=60,
              grain_type='star')
    g = _gs(j)
    assert g['allowable_concentration_factor'] < 1.0
    assert g['crack_propagation_risk'] == 'capability_exceeded'
    kodlar = [w.get('code') for w in j.get('design_warnings', [])
              if isinstance(w, dict)]
    assert 'warn.solid.grain_circular_strain_exceeds_capability' in kodlar
    # Yığılmış gerinim diye sayı basan eski uyarı bu tanede çıkmaz
    assert 'warn.solid.grain_strain_exceeds_capability' not in kodlar


def test_k2_kartus_tane_fea_bit_ayni(client):
    """Tane kesiti FEA'sına dokunulmadı: kartuş yüklü bates, 60 bar, panel
    gövdesi — taban ölçümüyle (tane_once.json) BİT-AYNI."""
    j = _kati(client, grain_support='cartridge_loaded', chamber_pressure=60)
    gs = _gs(j)
    gd = j['grain_design']
    govde = {'grain_type': 'bates', 'propellant_type': j['propellant_type'],
             'outer_diameter_mm': gd['outer_diameter_mm'],
             'core_diameter_mm': gd['inner_diameter_mm'],
             'chamber_pressure_bar': j['chamber_pressure'],
             'grain_length_mm': gd['grain_length_mm'],
             'grain_support': 'cartridge_loaded',
             'ambient_temp': gs['storage_temperature_k'],
             'case_radial_expansion_mm': gs['case_radial_expansion_mm']}
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = client.post('/api/fea/planar-grain', json=govde)
    assert r.status_code == 200
    assert 100 * r.get_json()['fea']['scalars']['max_bore_strain'] == \
        0.5312855644370211


# ---------------------------------------------------------------------------
# Arayüz: sınıf kodları çevrilir, dayanak satırı kaynaklı, panel iki sınıflı
# ---------------------------------------------------------------------------
TANE_SINIF_KODLARI = ('capability_exceeded', 'capability_not_exceeded',
               'thermal_exceeds_capability', 'thermal_within_capability',
               'not_determined_port_shape',
               'not_determined_beyond_small_strain')


def _i18n_satirlari(dosya, anahtar):
    return [s for s in dosya.read_text(encoding='utf-8').split('\n')
            if s.startswith("            '%s':" % anahtar)]


@pytest.mark.parametrize('kod', TANE_SINIF_KODLARI)
def test_arayuz_sinif_kodu_en_tr(kod):
    sablon = SOLID.read_text(encoding='utf-8')
    assert "'%s': T('solid.js.class.%s'," % (kod, kod) in sablon
    satir = _i18n_satirlari(I18N, 'solid.js.class.' + kod)
    assert len(satir) == 2, satir           # EN + TR
    assert satir[0] != satir[1]


def test_arayuz_dayanak_satirlari():
    sablon = SOLID.read_text(encoding='utf-8')
    for anahtar in ('solid.js.grain_strain_basis',
                    'solid.js.grain_strain_basis_unresolved'):
        assert "TF('%s'" % anahtar in sablon
        en, tr = _i18n_satirlari(I18N, anahtar)
        assert 'SP-8073' in en and 'SP-8073' in tr
        assert 'HRMA choice' not in en and 'unsourced' not in en
    en, tr = _i18n_satirlari(I18N, 'solid.js.grain_strain_basis_unresolved')
    assert '{k}' in en and '{k}' in tr and '%{circ}' in tr


def test_uyari_kodu_en_tr():
    satir = _i18n_satirlari(
        I18N_ORTAK, 'warn.solid.grain_circular_strain_exceeds_capability')
    assert len(satir) == 2
    assert '{strain_percent}%' in satir[0] and '%{strain_percent}' in satir[1]


def _node(kod):
    # Betik stdin'den (test_node_cagri_sozlesmesi: argv ile betik geçilmez).
    r = subprocess.run(['node'], input=kod, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_panel_siniflayici_iki_sinifli_ve_cozulmeyen_yol():
    kaynak = PANEL.read_text(encoding='utf-8')
    a = kaynak.index('    function strainMarginKind(')
    b = kaynak.index('\n    }\n', a) + 6
    c = kaynak.index('    function grainAnalyticFor(')
    d = kaynak.index('\n    }\n', c) + 6
    betik = ('function isNum(x){return typeof x==="number"&&isFinite(x);}\n'
             + kaynak[a:b] + kaynak[c:d]
             + 'console.log(JSON.stringify({k05: strainMarginKind(0.5),'
             ' k15: strainMarginKind(1.5), k30: strainMarginKind(3),'
             ' u: grainAnalyticFor({stress_concentration_status:'
             ' "not_resolved", circular_port_bore_strain_percent: 0.53,'
             ' allowable_concentration_factor: 3.76, grain_support: "x",'
             ' crack_propagation_risk: "not_determined_port_shape"},'
             ' {grain_support: "x"})}));')
    out = _node(betik)
    assert out['k05'] == 'err' and out['k15'] == 'ok' and out['k30'] == 'ok'
    assert out['u'] == {'unresolved': True, 'circular_pct': 0.53,
                        'allowable_kt': 3.76, 'exceeded': False}
    # Oturmamış kabul ölçütünde yeşil yok (standalone rozet)
    assert "_acc.converged !== true && _kind0 === 'ok'" in kaynak
    assert 'nominal factor' not in kaynak


# ---------------------------------------------------------------------------
# K3 (C1-K1) — boğaz / çıkış çapı: kutu salt okunur, ipucu gerçeği söyler ve
# çözücü gönderilen değeri GERÇEKTEN kullanmaz (ipucu ⟷ davranış aynı).
# Onarım tabanda (V306/TANE f1368d9cd); bu bekçi davranışı kilitler.
# ---------------------------------------------------------------------------
def test_k3_bogaz_cikis_girdisi_sonucu_degistirmez(client):
    a = _kati(client, throat_diameter='', exit_diameter='')
    b = _kati(client, throat_diameter=99.0, exit_diameter=150.0)
    for k in ('throat_diameter', 'exit_diameter', 'specific_impulse',
              'average_thrust', 'total_impulse', 'burn_time'):
        assert a[k] == b[k], k
    assert a['throat_diameter'] != 99.0 and a['exit_diameter'] != 150.0


@pytest.mark.parametrize('fid', ['throat_diameter', 'exit_diameter'])
def test_k3_kutu_salt_okunur_ipucu_dogru(fid):
    import re
    sablon = SOLID.read_text(encoding='utf-8')
    m = re.search(r'<input[^>]*id="%s"[^>]*>' % fid, sablon)
    assert m and ' readonly' in m.group(0) and 'value=""' in m.group(0)
    anahtar = {'throat_diameter':
               'solid.ui.nozzle_throat_diameter_critical_parameter_that',
               'exit_diameter':
               'solid.ui.nozzle_exit_diameter_larger_exit_provides'}[fid]
    en, tr = _i18n_satirlari(I18N, anahtar)
    assert 'read-only' in en and 'salt okunur' in tr
    assert 'critical parameter that determines' not in en
