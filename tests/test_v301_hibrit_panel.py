# -*- coding: utf-8 -*-
"""V301/H-PANEL — hibrit analiz panelleri tutarlılığı bekçileri.

Kalemler (brif ``_ana_model/brif/HP.md``; son kullanıcı testi NK-…):

* **1 (NK-15/NK-20)** c* verimi: hibrit ucu teslim c* = η_c* · kuramsal c*
  ile boyutlandırır; varsayılan ürünün KENDİ doğrulama kayıtlarındaki
  ölçülmüş η_c*'ların ortancasıdır (N2O/HTPB); kaynağı olmayan çiftte ideal
  c* + açık beyan. Belirsizlik nominali aynı η'yı kullanır.
* **2 (NK-9/NK-50)** blowdown sonu: Pc ↔ ṁ_ox kapanışı köklü çözülür, uçta
  itki/Pc yükselmez; "Tank Boşalması" bloğu ile geçici uç aynı sayıyı verir;
  kendinden basınçlı N2O'da geçici panelin varsayılan kipi blowdown.
* **7 (NK-10)** manşetin yanında c* verimi ve blowdown sayıları.

Beklenen değerler ucun O KOŞUMDAKİ yanıtından okunur; ürün sabitinden
türetilmez (yalnız η varsayılanının KAYITLARDAN yeniden hesaplanması
kaynağın kendisidir).
"""

import contextlib
import glob
import io
import json
import pathlib
import shutil
import statistics
import subprocess
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
ORNEK = KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')


def _ornek_govde(**ek):
    # V301/T-ÇAPA-D: örnek dosya ÖRNEK kulvarından (5fa435893) beri sayfanın
    # boş alanlarını '' olarak taşıyor; sayfa onları göndermez (ölçüm:
    # tests/support/ornek_alanlari.py).
    from tests.support.ornek_alanlari import ornek_alanlari
    f = ornek_alanlari(ORNEK)
    f.pop('motor_name', None)
    f.pop('motor_description', None)
    f['atmospheric_pressure'] = f.pop('single_pressure')
    f.update(ek)
    return {k: v for k, v in f.items() if v is not None}


def _post(uc, govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as c:
            r = c.post(uc, json=govde)
    return r.status_code, r.get_json() or {}


@pytest.fixture(scope='module')
def yanitlar():
    out = {}
    out['ornek'] = _post('/calculate', _ornek_govde())
    out['ornek_95'] = _post('/calculate',
                            _ornek_govde(combustion_efficiency=95))
    out['parafin'] = _post('/calculate', {
        k: v for k, v in _ornek_govde(fuel_type='paraffin').items()
        if k not in ('fuel_density', 'regression_a', 'regression_n')})
    out['gecici_bd'] = _post('/api/transient-analysis', _ornek_govde(
        feed_mode='blowdown', tank_temperature=293.15,
        liquid_fill_fraction=0.85))
    for ad, (kod, j) in out.items():
        assert kod == 200, (ad, kod, str(j)[:400])
    return {ad: j for ad, (kod, j) in out.items()}


# ---------------------------------------------------------------------------
# Kalem 1 — c* verimi
# ---------------------------------------------------------------------------
def test_eta_varsayilani_kayitlarin_ortancasi():
    """Sabit, doğrulama kayıtlarından yeniden hesaplanınca aynı çıkar."""
    from hrma.engines.hybrid_rocket_engine import HYBRID_ETA_C_STAR_MEASURED
    kayit = HYBRID_ETA_C_STAR_MEASURED[('n2o', 'htpb')]
    degerler = []
    for yol in sorted(glob.glob(str(
            KOK / 'hrma' / 'data' / 'validation_records' / 'hybrid'
            / '*.json'))):
        r = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
        if not any(r['test_id'].startswith(p)
                   for p in kayit['record_prefixes']):
            continue
        e = (r.get('measured') or {}).get('c_star_efficiency')
        if e is not None:
            degerler.append(float(e))
    assert len(degerler) == kayit['n_tests']
    assert statistics.median(degerler) == pytest.approx(
        kayit['eta_c_star'], abs=1e-12)
    assert (min(degerler), max(degerler)) == tuple(kayit['measured_band'])


def test_ornek_teslim_c_yildiz_verimle(yanitlar):
    m = yanitlar['ornek']['motor']
    blok = m['c_star_efficiency']
    assert blok['source'] == 'sourced_default' and blok['applied'] is True
    assert blok['eta_c_star'] == pytest.approx(0.89)
    assert m['c_star'] == pytest.approx(
        blok['eta_c_star'] * blok['c_star_theoretical_m_s'], rel=1e-12)
    # Isp = C_F · c* / g0 teslim değerle; ṁ = F / (Isp · g0).
    assert m['isp'] == pytest.approx(m['cf'] * m['c_star'] / 9.80665,
                                     rel=1e-9)
    alanlar = {d.get('field'): d for d in
               yanitlar['ornek'].get('defaults_applied') or []}
    assert 'combustion_efficiency' in alanlar
    assert alanlar['combustion_efficiency']['value'] == pytest.approx(89.0)


def test_kullanici_verimi_uygulanir(yanitlar):
    m = yanitlar['ornek_95']['motor']
    blok = m['c_star_efficiency']
    assert blok['source'] == 'user_input'
    assert m['c_star'] == pytest.approx(
        0.95 * blok['c_star_theoretical_m_s'], rel=1e-12)
    alanlar = [d.get('field') for d in
               yanitlar['ornek_95'].get('defaults_applied') or []]
    assert 'combustion_efficiency' not in alanlar


@pytest.mark.parametrize('deger', [40, 120, 'abc', True])
def test_bant_disi_verim_adiyla_reddedilir(deger):
    kod, j = _post('/calculate', _ornek_govde(combustion_efficiency=deger))
    assert kod == 422, (kod, str(j)[:300])
    assert [f['field'] for f in j['invalid_fields']] == [
        'combustion_efficiency']


def test_kaynaksiz_ciftte_ideal_c_yildiz_beyanli(yanitlar):
    m = yanitlar['parafin']['motor']
    blok = m['c_star_efficiency']
    assert blok['source'] == 'ideal_no_source'
    assert blok['applied'] is False and blok['eta_c_star'] == 1.0
    assert m['c_star'] == blok['c_star_theoretical_m_s']
    assert 'IDEAL' in blok['basis']


def test_cea_karsilastirmasi_kuramsal_kalir(yanitlar):
    """CEA bloğu teorik c*'ı karşılaştırır (teslim değeri değil)."""
    j = yanitlar['ornek']
    satir = [r for r in j['cea_comparison']['rows']
             if r['quantity'] == 'c_star'][0]
    assert satir['hrma'] == pytest.approx(
        j['motor']['c_star_efficiency']['c_star_theoretical_m_s'],
        rel=1e-9)


def test_belirsizlik_nominali_ayni_eta():
    from hrma.analysis import uq_adapters as uqa
    d = uqa.build_distributions('hybrid', None)
    d2 = uqa.center_hybrid_eta_distribution(d, _ornek_govde())
    e = d2['eta_c_star']
    assert e.nominal_value() == pytest.approx(0.89)
    assert e.mean == pytest.approx(0.89)
    # Kullanıcı değeri de aynı yoldan.
    e = uqa.center_hybrid_eta_distribution(
        d, _ornek_govde(combustion_efficiency=95))['eta_c_star']
    assert e.nominal_value() == pytest.approx(0.95) and e.mean == 0.95
    # Kaynaksız çift: dağılım dokunulmaz (beyanlı ideal c*).
    p = uqa.center_hybrid_eta_distribution(
        d, _ornek_govde(fuel_type='paraffin'))['eta_c_star']
    assert p == d['eta_c_star']


# ---------------------------------------------------------------------------
# Kalem 2 — blowdown sonu ve iki panel
# ---------------------------------------------------------------------------
def test_blowdown_sonunda_itki_ve_pc_yukselmez(yanitlar):
    tb = yanitlar['ornek']['motor']['tank_blowdown']
    assert tb['status'] == 'modelled'
    F, Pc, mo = (tb['thrust_N'], tb['chamber_pressure_bar'],
                 tb['mdot_ox_kg_s'])
    P = tb['tank_pressure_bar']
    # Tank basıncı düşerken (son 1 s) itki, Pc ve ṁ_ox de yükselmez.
    n = 20
    for dizi, ad in ((F, 'itki'), (Pc, 'Pc'), (mo, 'mdot_ox'), (P, 'tank')):
        kuyruk = dizi[-n:]
        assert all(b <= a + 1e-9 for a, b in zip(kuyruk, kuyruk[1:])), (
            ad, kuyruk)
    assert tb['thrust_final_N'] <= tb['thrust_initial_N']
    assert tb['thrust_decay_fraction'] >= 0.0
    assert tb['end_event'] != 'feed_pressure_lost'


def test_iki_panel_ayni_blowdown_sayilari(yanitlar):
    tb = yanitlar['ornek']['motor']['tank_blowdown']
    tr = yanitlar['gecici_bd']['transient']
    assert tr['end_event'] == tb['end_event']
    assert tr['time'][-1] == pytest.approx(tb['time_s'][-1], abs=1e-9)
    assert tr['total_impulse'] == pytest.approx(tb['total_impulse_Ns'],
                                                rel=1e-9)
    assert tr['residual_oxidizer_kg'] == pytest.approx(
        tb['residual_oxidizer_kg'], rel=1e-9)


def test_blowdown_kapanisi_spi_ile_tutarli():
    """Yayımlanan (Pc, ṁ_ox) çifti enjektör bağıntısını sağlar."""
    import numpy as np
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    from hrma.analysis.transient_ballistics import TransientBallistics
    with contextlib.redirect_stdout(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        e = HybridRocketEngine(thrust=3000, burn_time=10, of_ratio=7,
                               chamber_pressure=30, fuel_type='htpb',
                               oxidizer_type='n2o', tank_temperature=293.15)
        e.calculate()
        tb = TransientBallistics(e, feed_mode='blowdown',
                                 tank_temperature=293.15,
                                 liquid_fill_fraction=0.85, n_steps=200)
        K = tb._K_inj
        s = tb.solve()
    for i in range(len(s['time'])):
        Pc = s['chamber_pressure'][i]
        Pt = s['tank_pressure'][i]
        rho = tb.tank.props.rho_l(s['tank_temperature'][i])
        spi = K * np.sqrt(2.0 * rho * (Pt - Pc))
        assert s['mdot_ox'][i] == pytest.approx(spi, rel=1e-4), i


_PANEL_DUZENEGI = r"""
'use strict';
const fs = require('fs'); const vm = require('vm'); const path = require('path');
const IN = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const alanlar = IN.form || {};
const secenek = (v) => ({ value: v, disabled: false });
const sel = { value: IN.secili || 'regulated', dataset: IN.dataset || {},
              options: [secenek('regulated'), secenek('blowdown')] };
const not = { style: { display: 'none' } };
const grup = { style: { display: 'none' } };
const sandbox = { console, JSON, Object, Array, Math, Number, String,
                  isFinite, parseFloat, NaN };
sandbox.window = sandbox;
sandbox.document = { getElementById: (id) => {
    if (id === 'tp_feed_mode') return sel;
    if (id === 'tp_feed_note') return not;
    if (id === 'tp_tank_temp_group' || id === 'tp_fill_group') return grup;
    return (id in alanlar) ? { value: alanlar[id] } : null; } };
if (IN.currentRequest) sandbox.currentRequest = IN.currentRequest;
vm.createContext(sandbox);
const dizin = path.dirname(process.argv[2]);
vm.runInContext(fs.readFileSync(path.join(dizin, 'units_constants.js'), 'utf8'),
                sandbox, { filename: 'units_constants.js' });
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox,
                { filename: 'transient_panel.js' });
sandbox.TransientPanel._beslemeKipiniEsle();
process.stdout.write(JSON.stringify({ secili: sel.value,
    grup: grup.style.display }));
"""


def _panel(tmp_path, girdi):
    duzenek = tmp_path / 'p.js'
    duzenek.write_text(_PANEL_DUZENEGI, encoding='utf-8')
    dosya = tmp_path / 'in.json'
    dosya.write_text(json.dumps(girdi), encoding='utf-8')
    islem = subprocess.run([NODE, str(duzenek), str(JS / 'transient_panel.js'),
                            str(dosya)], capture_output=True, text=True,
                           timeout=60)
    assert islem.returncode == 0, islem.stderr
    return json.loads(islem.stdout)


@node_gerekli
def test_kendinden_basincli_n2o_varsayilan_blowdown(tmp_path):
    s = _panel(tmp_path, {'currentRequest': {'oxidizer_type': 'n2o'}})
    assert s == {'secili': 'blowdown', 'grup': ''}
    # Kullanıcı panelde elle seçtiyse ezilmez.
    s = _panel(tmp_path, {'currentRequest': {'oxidizer_type': 'n2o'},
                          'dataset': {'kullaniciSecti': '1'}})
    assert s['secili'] == 'regulated'
    # LOX / kullanıcı tank kipi: blowdown modeli yok → regüleli kalır.
    s = _panel(tmp_path, {'currentRequest': {'oxidizer_type': 'lox'}})
    assert s['secili'] == 'regulated'
    s = _panel(tmp_path, {'currentRequest': {'oxidizer_type': 'n2o',
                                             'tank_pressure_source': 'user',
                                             'tank_pressure': 60}})
    assert s['secili'] == 'regulated'


# ---------------------------------------------------------------------------
# Kalem 1 + 7 — manşetin dayanağı manşetin yanında (app.js)
# ---------------------------------------------------------------------------
_MANSET_DUZENEGI = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const kaynak = fs.readFileSync(process.argv[2], 'utf8');
const bas = kaynak.indexOf('function headlineBasisBlock(');
const son = kaynak.indexOf('\n}\n', bas);
const govde = kaynak.slice(bas, son + 3);
const motor = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sandbox = { JSON, Object, Array, Math, Number, String, isFinite,
    window: {},
    T: (k, f) => f,
    TF: (k, p, f) => String(f).replace(/\{(\w+)\}/g, (w, n) =>
        (p && n in p) ? String(p[n]) : w) };
vm.createContext(sandbox);
vm.runInContext(govde + '\nthis.sonuc = headlineBasisBlock(MOTOR);'
                .replace('MOTOR', JSON.stringify(motor)), sandbox);
process.stdout.write(sandbox.sonuc);
"""


def _manset(tmp_path, motor):
    duzenek = tmp_path / 'm.js'
    duzenek.write_text(_MANSET_DUZENEGI, encoding='utf-8')
    dosya = tmp_path / 'motor.json'
    dosya.write_text(json.dumps(motor), encoding='utf-8')
    islem = subprocess.run([NODE, str(duzenek), str(JS / 'app.js'),
                            str(dosya)], capture_output=True, text=True,
                           timeout=60)
    assert islem.returncode == 0, islem.stderr
    return islem.stdout


@node_gerekli
def test_manset_verim_ve_blowdown_satiri(tmp_path, yanitlar):
    m = yanitlar['ornek']['motor']
    alt = {k: m[k] for k in ('c_star_efficiency', 'tank_blowdown',
                             'total_impulse')}
    html = _manset(tmp_path, alt)
    assert 'data-headline-basis="cstar-eff"' in html
    assert 'data-headline-basis="regulated-vs-blowdown"' in html
    assert 'href="#blowdownPanel"' in html
    # Sayılar yanıttan (toFixed yedeği: I18N yok).
    assert '%.0f' % m['tank_blowdown']['total_impulse_Ns'] in html
    assert '%.2f' % m['tank_blowdown']['burn_duration_s'] in html
    assert '%.0f' % m['c_star_efficiency']['c_star_theoretical_m_s'] in html
    assert 'ideal-cstar' not in html


@node_gerekli
def test_manset_ideal_c_yildiz_beyani(tmp_path, yanitlar):
    m = yanitlar['parafin']['motor']
    html = _manset(tmp_path, {'c_star_efficiency': m['c_star_efficiency']})
    assert 'data-headline-basis="ideal-cstar"' in html
    assert 'IDEAL c*' in html


# ---------------------------------------------------------------------------
# Kalem 8 / 14 — gizli itki/süre yok; impuls kipi çalışır
# ---------------------------------------------------------------------------
def _govde_sil(**ek):
    g = _ornek_govde()
    for ad in ('thrust', 'burn_time', 'total_impulse'):
        g.pop(ad, None)
    g.update(ek)
    return g


def test_impuls_ve_itki_ile_sure_cozulur():
    kod, j = _post('/calculate', _govde_sil(total_impulse=20000, thrust=2000))
    assert kod == 200, str(j)[:300]
    m = j['motor']
    assert m['thrust'] == pytest.approx(2000.0)
    assert m['burn_time'] == pytest.approx(10.0)
    assert m['impulse_input_resolution']['supplied'] == [
        'thrust', 'total_impulse']


def test_yalniz_impuls_adiyla_reddedilir():
    kod, j = _post('/calculate', _govde_sil(total_impulse=20000))
    assert kod == 422, (kod, str(j)[:300])
    assert sorted(f['field'] for f in j['invalid_fields']) == [
        'burn_time', 'thrust']
    assert "optimal" in j['message']


def test_bos_itki_adiyla_reddedilir():
    kod, j = _post('/calculate', _govde_sil(burn_time=10))
    assert kod in (400, 422), (kod, str(j)[:300])
    assert 'thrust' in [f['field'] for f in j['invalid_fields']]
    assert 'motor' not in j


def test_formda_gizli_itki_sayisi_yok():
    """advanced.html toplayıcısında `|| 1000` / `|| 10` / `|| 10000` yok."""
    html = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    bas = html.index("thrust: thrustTimeActive ?")
    parca = html[bas:bas + 900]
    for kalip in ("|| 1000)", "|| 10)", "|| 10000)", ": 1000,", ": 10,"):
        assert kalip not in parca, kalip
