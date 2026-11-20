"""V307/GÜVERTE-ISIL bekçileri — Analiz Güvertesi'nin ısıl sekmeleri motorla
çelişmesin (3.0.7 hattı, 17 Kas 2026).

Kalemler (brif: docs/scofield/raw/OH/V307/ana-model/brif_17kas/GUVERTE_ISIL.md;
kanıt ve ölçüm: docs/scofield/raw/OH/V307/guverte-isil/RAPOR.md):

  K1  İki astar modeli: sıvı ablatif motorun astarı motor sonucunda bir sayı,
      TERMAL / ISIL KORUMA sekmesinde başka bir sayı (aynı çekirdek
      ``ablative_thickness``, iki ayrı girdi). Bekçi: aynı motor -> aynı
      gerileme hızı, aynı gerileme payı, aynı zarf hükmü.
  K2  Film / ışınım / dump soğutma: TERMAL sekme doğal taşınıma düşmez, uca
      gitmez, motor sonucunun soğutma sonucunu AYNI sayılarla gösterir.
  K3  Isıl koruma sekmesinin gizli tanım değerleri (2e6 W/m², 10 s, 3000
      W/m²K, 3200 K, 5 mm) yok; kip başına zorunlu küme sunucu = panel.
  K4  ``/analyze_safety`` 3000 K: sıcaklıksız istek adlı 422; motor tohumlu
      istek 200 ve motorun sıcaklığı; aynı 3000'in ikizleri.

Akış gerçektir: motor ucu -> panelin GERÇEK ``fromResults`` /
``contextFromResults`` / ``localResult``'ı (node) -> güvertenin gövde kuralı
-> gerçek güverte ucu.
"""
import json
import math
import os
import re
import subprocess
from pathlib import Path

import pytest

import tests.test_v3_yapi_sf as T
from tests.test_v307_sekme_guverte import NODE, SG_VAKALARI, _motor_yaniti

REPO = Path(__file__).resolve().parents[1]
APP_PY = REPO / 'hrma' / 'app.py'
PROT_JS = REPO / 'hrma' / 'static' / 'js' / 'panels' / 'protection_panel.js'
SAFETY_PY = REPO / 'hrma' / 'analysis' / 'safety_analysis.py'

PANEL_DOSYALARI = {
    'thermal': 'hrma/static/js/panels/thermal_panel.js',
    'protection': 'hrma/static/js/panels/protection_panel.js',
    'safety': 'hrma/static/js/panels/safety_panel.js',
}
#: Isıl koruma paneli kip sözleşmesini şablonun <meta> etiketinden okur; node
#: düzeneğinde şablon yoktur. Taşıyıcı (kanıt dizininde) etiketi ortam
#: değişkeninden (= GERÇEK şablonun bastığı içerik) sunar.
META_TASIYICI = 'docs/scofield/raw/OH/V307/guverte-isil/meta_tasiyici.js'
META_KALIBI = r"""<meta name="hrma-tp-mode-required" content='([^']*)'>"""
HEADERS = {'Host': '127.0.0.1:8080'}

#: Örnek sıvı projenin (LOX/RP-1, Pc 50 bar) soğutma tipi değiştirilmiş hâli.
#: Film soğutmada %0 film kapıda reddedilir; ölçüm gövdesi beyanlı %10.
def _ornek_sivi(tip):
    ek = {'cooling_type': tip}
    if tip == 'film_cooling':
        ek['film_cooling_percent'] = 10
    return ek


_EV = r"""
var out = {};
body.paneller.forEach(function (pid) {
  var spec = window.AnalysisDock._registry.filter(function (s) {
      return s.id === pid; })[0];
  if (!spec) { out[pid] = {_yok: true}; return; }
  try { window.AnalysisDock.init({motorType: body.motorType,
      resultsProvider: function () { return body.motor; }}); } catch (e) {}
  window.currentResults = body.motor;
  var r = {endpoint: spec.endpoint,
           fields: spec.fields.map(function (f) {
             return [f[0], f[1], f[2], Array.isArray(f[3]) ? [] : f[3]]; }),
           required: spec.required || []};
  try { r.suggested = body.motor ? spec.fromResults(body.motor) : null; }
  catch (e) { r._err = String(e.stack || e); }
  if (typeof spec.contextFromResults === 'function' && body.motor) {
    try { r.ctx = spec.contextFromResults(body.motor); } catch (e) { r._err = String(e.stack || e); }
  }
  if (typeof spec.localResult === 'function') {
    var s0 = r.suggested || {};
    try { r.yerel = spec.localResult({cooling_type: s0.cooling_type}); }
    catch (e) { r._err = String(e.stack || e); }
  }
  if (pid === 'protection' && window.ProtectionPanel) {
    r.mode_required = window.ProtectionPanel._modeRequired();
  }
  if (body.data && body.data[pid]) {
    var root = document.createElement('div');
    try { spec.render(body.data[pid], root); } catch (e) { r._err = String(e.stack || e); }
    var h = '';
    (function walk(n) { h += String(n.innerHTML || '');
      (n.children || []).forEach(walk); })(root);
    r.html = h;
  }
  out[pid] = r;
});
return out;
"""


def _sablon_metasi():
    """GERÇEK şablonun (sıvı sayfası) bastığı kip sözleşmesi."""
    import html as _html
    from hrma.app import app
    r = app.test_client().get('/liquid', headers=HEADERS)
    assert r.status_code == 200
    m = re.search(META_KALIBI, r.get_data(as_text=True))
    assert m, 'sıvı sayfası hrma-tp-mode-required etiketini basmıyor'
    return _html.unescape(m.group(1))


def _node(tur, motor, paneller, data=None, meta=True):
    from tests.support.kanit import kanit_gerekli
    from tests.support import guvenlik_meta as GM
    if NODE is None:
        pytest.skip('node yok: panel ölçümü koşamaz (gerekçeli atlama)')
    kanit_gerekli(str(REPO / META_TASIYICI))
    cfg = {'panelId': '_yok',
           'panelFiles': [PANEL_DOSYALARI[p] for p in paneller],
           'extraFiles': ['hrma/static/js/materials_catalog.js', kanit_gerekli(META_TASIYICI),
                          GM.TASIYICI],   # V307/KÜÇÜKLER kalem 6: güvenlik meta
           'dataInline': {'motorType': tur, 'motor': motor,
                          'paneller': paneller, 'data': data},
           'evalFn': _EV}
    ortam = GM.ortam()
    if meta:
        ortam['HRMA_TP_META'] = _sablon_metasi()
    else:
        ortam.pop('HRMA_TP_META', None)
    p = subprocess.run([NODE, kanit_gerekli(str(T._PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=240, env=ortam)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    for pid in paneller:
        assert not ev[pid].get('_err'), ev[pid].get('_err')
    return ev


def _yuk(spec, sug, ek=None):
    """analysis_dock.js buildPayload: öneri ezer; seçici aynen; sayı yalnız
    sonluysa; boş zorunlu alan ``eksik``; form dışı bağlam en son."""
    sug = dict(sug or {})
    sug.pop('__withheld', None)
    sug.update(ek or {})
    out, eksik = {}, []
    beyanli = set(spec.get('required') or [])
    for f in spec['fields']:
        k, var = f[0], f[2]
        v = sug.get(k) if sug.get(k) is not None else var
        if isinstance(f[3], list):
            out[k] = v
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            x = None
        if x is not None and math.isfinite(x):
            out[k] = x
            continue
        if (isinstance(var, (int, float)) and not isinstance(var, bool)) \
                or k in beyanli:
            eksik.append(k)
    for k, v in (spec.get('ctx') or {}).items():
        if k not in out and v is not None:
            out[k] = v
    return out, eksik


def _post(yol, govde):
    from hrma.app import app
    c = app.test_client()
    if yol == '/analyze_thermal_safety':
        r = c.post('/analyze_thermal_safety', json=govde)
    elif yol == '/api/thermal-protection':
        r = c.post('/api/thermal-protection', json=govde)
    elif yol == '/analyze_safety':
        r = c.post('/analyze_safety', json=govde)
    elif yol == '/api/analysis/wall-profile':
        r = c.post('/api/analysis/wall-profile', json=govde)
    else:
        raise AssertionError('bu bekçide olmayan uç: ' + yol)
    return r.status_code, T._json_guvenli(r.get_json(silent=True))


def _ayni(a, b, bagil=1e-12):
    return (a is not None and b is not None
            and abs(float(a) - float(b)) <= bagil * max(1.0, abs(float(b))))


class _TembelMotorlar(dict):
    """Motor yanıtı ilk istendiğinde hesaplanır (modül boyunca bir kez)."""

    def __missing__(self, ad):
        if ad == 'sivi_L1':
            tur, ek = SG_VAKALARI['sivi_abl']
        else:
            tur, ek = 'liquid', _ornek_sivi(ad.split('@', 1)[1])
        self[ad] = (tur, _motor_yaniti(tur, ek))
        return self[ad]


@pytest.fixture(scope='module')
def motorlar(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_v307gi')))
    return _TembelMotorlar()


def _pasif(motor):
    m = motor.get('motor') or motor
    return m['thermal_protection']['passive_thermal_protection']


# ===========================================================================
# K1 — motor ⟷ güverte astar çapraz bekçisi
# ===========================================================================
@pytest.mark.parametrize('vaka', ['sivi_L1', 'ornek@ablative'])
def test_k1_termal_hazne_astari_motorla_ayni(motorlar, vaka):
    """TERMAL sekmesinin hazne astarı = motor sonucunun hazne astarı:
    aynı gerileme hızı, gerileme payı motorun kalınlığına eşit; motor
    boyutlayamıyorsa iki tarafta aynı adlı ret (NOT_SIZED ⟷ zarf dışı)."""
    tur, motor = motorlar[vaka]
    cl = _pasif(motor)['chamber_liner']
    ev = _node(tur, motor, ['thermal'])['thermal']
    yuk, eksik = _yuk(ev, ev['suggested'])
    assert not eksik, eksik
    assert yuk.get('wall_protection') == 'ablative_liner'
    # Motorun astar istasyonu girdileri AYNEN gidiyor (form dışı bağlam).
    assert _ayni(yuk.get('liner_h_gas_W_m2K'), cl['h_gas_W_m2K'])
    assert _ayni(yuk.get('liner_T_recovery_K'), cl['T_recovery_K'])
    kod, y = _post('/analyze_thermal_safety', yuk)
    assert kod == 200, str(y)[:400]
    blok = y['thermal_analysis']['chamber_liner_check']
    assert blok['inputs']['liner_station_source'] == 'supplied'
    if cl.get('thickness_status') == 'sized':
        sz = blok['sizing']
        assert blok['verdict'] == 'LINER_REQUIRED'
        assert _ayni(sz['recession_rate_mm_s'], cl['recession_rate_mm_s'])
        assert _ayni(sz['recession_allowance_mm'], cl['thickness']), (
            'güvertenin gerileme payı motorun yayımladığı astar kalınlığına '
            'eşit değil')
    else:
        assert cl.get('thickness') is None
        assert blok['verdict'] == 'NOT_SIZED'
        assert _ayni(blok['recession_rate_mm_s'], cl['recession_rate_mm_s'])
        assert blok['thickness_status'] == cl['thickness_status']
        assert _ayni(blok['recession_validity_max_mm_s'], 0.35, 0)
        assert _pasif(motor)['liner_sizing_status'] in ('NOT_SIZED',
                                                       'PARTIALLY_SIZED')


@pytest.mark.parametrize('vaka', ['sivi_L1', 'ornek@ablative'])
def test_k1_isil_koruma_ablatif_motorun_istasyonuyla_ayni(motorlar, vaka):
    """ISIL KORUMA sekmesi (ablatif kip) motorun lüle girişi astar
    istasyonuyla aynı girdiyi (çift + c_p + yarıçap) gönderir; gerileme hızı
    ve kalınlık hükmü motorunkiyle aynıdır."""
    tur, motor = motorlar[vaka]
    ne = _pasif(motor)['nozzle_entry_liner']
    ev = _node(tur, motor, ['protection'])['protection']
    yuk, eksik = _yuk(ev, ev['suggested'], {'mode': 'ablative'})
    assert not eksik, eksik
    for alan, motor_alani in (('h_gas_W_m2K', 'h_gas_W_m2K'),
                              ('T_recovery_K', 'T_recovery_K'),
                              ('gas_cp_J_kgK', 'gas_cp_J_kgK'),
                              ('station_radius_m', 'station_radius_m')):
        assert _ayni(yuk.get(alan), ne[motor_alani]), (alan, yuk.get(alan),
                                                       ne[motor_alani])
    kod, y = _post('/api/thermal-protection', yuk)
    assert kod == 200, str(y)[:400]
    assert _ayni(y['recession_rate_mm_s'], ne['recession_rate_mm_s'])
    assert y['thickness_status'] == ne['thickness_status']
    if ne.get('thickness') is None:
        assert y.get('required_thickness_mm') is None


def test_k1_zarf_kaynakli_ve_yukseltilmedi():
    """Zarf (0,35 mm/s) yükseltilmedi; künyesi modülde."""
    from hrma.analysis import thermal_protection as tp
    assert tp.RECESSION_VALID_MAX_MM_S == 0.35
    kaynak = Path(tp.__file__).read_text(encoding='utf-8')
    assert 'TM-107041' in kaynak or 'TM107041' in kaynak


# ===========================================================================
# K2 — soğutma tipi başına TERMAL sekme davranışı
# ===========================================================================
@pytest.mark.parametrize('tip', ['regenerative', 'ablative', 'film_cooling',
                                 'radiative', 'dump_cooling'])
def test_k2_sogutma_tipi_sekmeye_tasinir(motorlar, tip):
    tur, motor = motorlar['ornek@' + tip]
    m = motor.get('motor') or motor
    ev = _node(tur, motor, ['thermal'])['thermal']
    assert ev['suggested'].get('cooling_type') == tip, (
        'motorun soğutma tipi sekmeye taşınmıyor')
    if tip in ('regenerative', 'ablative'):
        assert ev['yerel'] is None, 'modelli tipte uca gidilmeli'
        return
    # Modelsiz tip: istek gönderilmez, motorun soğutma sonucu gösterilir.
    yerel = ev['yerel']
    assert isinstance(yerel, dict) and yerel['cooling_not_modelled_here']
    mc = yerel['motor_cooling']
    assert mc['tip'] == tip
    assert _ayni(mc['toplamKw'], m['cooling_system']['total_heat_load'])
    # Uç aynı gövdeye adlı ret verir (doğrudan çağıran için).
    yuk, _ = _yuk(ev, ev['suggested'])
    kod, y = _post('/analyze_thermal_safety', yuk)
    assert kod == 422 and y['error'] == 'unsupported_cooling_type'
    assert y['motor_cooling_class'] is True
    # Çizim: başka bir soğutmanın hükmü (Doğal / risk) basılmaz.
    ren = _node(tur, motor, ['thermal'], data={'thermal': yerel})['thermal']
    h = ren['html']
    assert 'data-thermal-cooling-not-modelled="%s"' % tip in h
    assert 'data-thermal-motor-cooling="shown"' in h
    assert 'Natural' not in h and 'RISK' not in h.upper().replace(
        'NOT MODELLED', '')
    if tip == 'radiative':
        rad = _pasif(motor)['radiation_equilibrium']
        assert '%.1f' % rad['T_wall_eq_K'] in h


# ===========================================================================
# K3 — ısıl koruma: gizli tanım değeri yok; kip başına zorunlu küme
# ===========================================================================
def test_k3_tanim_degerleri_bos():
    ev = _node('liquid', None, ['protection'])['protection']
    tanim = {f[0]: f[2] for f in ev['fields']}
    for alan in ('q_net_W_m2', 'burn_time_s', 'h_gas_W_m2K', 'T_recovery_K',
                 'wall_thickness_m', 'gas_cp_J_kgK', 'station_radius_m'):
        assert tanim[alan] == '', (alan, tanim[alan])


def test_k3_kip_sozlesmesi_sunucu_panel_ayni():
    from hrma.app import app, thermal_protection_form_contract
    sozlesme = thermal_protection_form_contract()
    assert json.loads(_sablon_metasi()) == sozlesme
    # Sözleşme = ucun kapısının boş gövdeye yanıtı (her kip).
    c = app.test_client()
    for kip, liste in sozlesme.items():
        r = c.post('/api/thermal-protection', json={'mode': kip})
        assert r.status_code == 422, (kip, r.status_code)
        assert r.get_json()['missing_fields'] == liste, kip
    # Panel aynı kümeyi okur; kendi dosyasında ikinci liste yok.
    ev = _node('liquid', None, ['protection'])['protection']
    assert ev['mode_required'] == sozlesme
    assert ev['required'] == sozlesme['ablative']
    src = PROT_JS.read_text(encoding='utf-8')
    assert not re.search(r"ablative\s*:\s*\[\s*'q_net_W_m2'", src)
    assert not re.search(r"radiation_equilibrium\s*:\s*\[", src)


def test_k3_meta_yoksa_on_denetim_uydurulmaz():
    """Sözleşme okunamazsa panel ikinci bir liste uydurmaz (boş küme; uç
    eksik alanı adıyla reddeder)."""
    ev = _node('liquid', None, ['protection'], meta=False)['protection']
    assert ev['mode_required'] is None
    assert ev['required'] == []


def test_k3_motorsuz_bos_govde_istek_gondermez():
    ev = _node('liquid', None, ['protection'])['protection']
    yuk, eksik = _yuk(ev, None, {'mode': 'ablative'})
    assert set(eksik) >= {'q_net_W_m2', 'burn_time_s'}


# ===========================================================================
# K4 — /analyze_safety oda sıcaklığı
# ===========================================================================
K4_GUVENLIK_GOVDESI = {'motor_type': 'hybrid', 'chamber_pressure': 30.0,
            'chamber_temperature': 3279.1, 'thrust': 3000.0, 'burn_time': 10.4,
            'propellant_mass': 15.0, 'propellant_type': 'not_modelled',
            'facility_type': 'test_stand', 'chamber_diameter': 0.1032,
            'wall_thickness': 0.0055, 'material': 'ss_304',
            'chamber_length': 0.745, 'throat_diameter': 0.03}


@pytest.mark.parametrize('deger', ['__yok__', '', None])
def test_k4_sicakliksiz_istek_adli_422(deger):
    govde = dict(K4_GUVENLIK_GOVDESI)
    if deger == '__yok__':
        govde.pop('chamber_temperature')
    else:
        govde['chamber_temperature'] = deger
    kod, y = _post('/analyze_safety', govde)
    assert kod == 422
    assert y['error'] == 'incomplete_safety_input'
    assert y['missing_fields'] == ['chamber_temperature']


@pytest.mark.parametrize('deger', [-3000.0, 0.0, 'NaN', 1e9])
def test_k4_fizik_disi_sicaklik_200_donmez(deger):
    kod, y = _post('/analyze_safety', dict(K4_GUVENLIK_GOVDESI, chamber_temperature=deger))
    assert kod == 422 and y['error'] == 'invalid_safety_input'
    assert [i['field'] for i in y['invalid_fields']] == ['chamber_temperature']


def test_k4_varsayilan_beyani_sicaklik_icermez():
    kod, y = _post('/analyze_safety', K4_GUVENLIK_GOVDESI)
    assert kod == 200
    assert 'chamber_temperature' not in (y.get('defaults_applied') or [])


def test_k4_motor_tohumlu_istek_motorun_sicakligi(motorlar):
    tur, motor = motorlar['sivi_L1']
    m = motor.get('motor') or motor
    ev = _node(tur, motor, ['safety'])['safety']
    assert 'chamber_temperature' in ev['required']
    tanim = {f[0]: f[2] for f in ev['fields']}
    assert tanim['chamber_temperature'] == ''
    yuk, eksik = _yuk(ev, ev['suggested'])
    assert not eksik, eksik
    assert _ayni(yuk['chamber_temperature'], m['chamber_temperature'])
    kod, y = _post('/analyze_safety', yuk)
    assert kod == 200, str(y)[:400]
    assert _ayni(y['safety_analysis']['thermal_safety']['chamber_temperature_k'],
                 m['chamber_temperature'])
    # Motorsuz panel isteği göndermez, alanı adıyla söyler.
    ev0 = _node(tur, None, ['safety'])['safety']
    _, eksik0 = _yuk(ev0, None)
    assert 'chamber_temperature' in eksik0


def test_k4_duvar_profili_sicakliksiz_422():
    govde = {'chamber_pressure': 30.0, 'chamber_diameter': 0.1032,
             'chamber_length': 0.745, 'burn_time': 10.4, 'mdot_total': 1.46,
             'wall_thickness': 0.0055, 'material': 'ss_304',
             'cooling_type': 'natural', 'throat_diameter': 0.03}
    kod, y = _post('/api/analysis/wall-profile', govde)
    assert kod == 422 and y['missing_fields'] == ['chamber_temperature']


def test_k4_guvenlik_modulu_sicaklik_uydurmaz():
    """PDF güvenlik bölümünün yolu: sıcaklıksız motor verisi 3000 K almaz;
    sıcak yüzey ölçütü adıyla değerlendirilmez (LOW da denmez)."""
    from hrma.analysis.safety_analysis import (
        AUTO_IGNITION_NOT_EVALUATED, SafetyAnalyzer)
    a = SafetyAnalyzer()
    for mt in ('hybrid', 'solid'):
        r = a._assess_auto_ignition_risk('composite', None, motor_type=mt)
        assert r['risk_level'] == AUTO_IGNITION_NOT_EVALUATED, mt
        assert 'chamber temperature was not supplied' in r['note']
        sicak = a._assess_auto_ignition_risk('composite', 3279.1,
                                             motor_type=mt)
        assert sicak['risk_level'] == 'MEDIUM'
    th = a._analyze_thermal_safety(
        {'chamber_pressure': 30.0, 'chamber_diameter': 0.1,
         'wall_thickness': 0.005, 'motor_type': 'hybrid'}, 'ss_304')
    assert th['chamber_temperature_k'] is None


def test_k4_pdf_guvenlik_bolumu_ayni_kural():
    """PDF güvenlik bölümü ucun zorunlu kümesini taşır: motor verisinde oda
    sıcaklığı yoksa bölüm koşmaz ve alanı adıyla söyler (3000 K yok)."""
    from hrma.export.pdf_safety import (PDF_SAFETY_REQUIRED_FIELDS,
                                        resolve_safety_inputs)
    assert 'chamber_temperature' in PDF_SAFETY_REQUIRED_FIELDS
    md = {'chamber_pressure': 30.0, 'propellant_mass': 15.0,
          'chamber_diameter': 0.1032, 'motor_type': 'hybrid'}
    _, eksik, _ = resolve_safety_inputs(md, {})
    assert 'chamber_temperature' in eksik
    girdi, eksik, kaynak = resolve_safety_inputs(
        dict(md, chamber_temperature=3279.1), {})
    assert 'chamber_temperature' not in eksik
    assert girdi['chamber_temperature'] == 3279.1
    assert kaynak['chamber_temperature'] == 'chamber_temperature'
    # Ham yükten de okunur (motor verisinde yoksa).
    girdi, eksik, _ = resolve_safety_inputs(md, {'chamber_temperature': 1695.97})
    assert girdi['chamber_temperature'] == 1695.97


def test_k4_kaynaksiz_3000_satirlari_yok():
    """Isıl güverte uçlarında ve güvenlik modülünde oda sıcaklığına 3000
    varsayılanı yazılmaz (aynı kural her yerde)."""
    def _kod(yol):  # yorum satırları (eski satırın künyesi) sayılmaz
        return '\n'.join(s for s in yol.read_text(encoding='utf-8').splitlines()
                         if not s.lstrip().startswith('#'))
    assert not re.search(
        r"'chamber_temperature',\s*(default\s*=\s*)?3000\b", _kod(APP_PY))
    assert not re.search(r"get\('chamber_temperature',\s*3000",
                         _kod(SAFETY_PY))
