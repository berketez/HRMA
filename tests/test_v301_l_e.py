"""v3.0.1 / V301/L-E — sıvı SONUÇ ekranı ve paneller (bekçi).

Kanıt ``docs/scofield/raw/OH/V301/kati-sivi/L-E/`` (RAPOR.md).

  * NK-39: irtifa eğrisi sabit lülede (ayrılmasız) AYNI LÜLE özdeşliğiyle
    kurulur — 0 km noktası "Deniz Seviyesi Isp", 100 km noktası "Vakum Isp"
    kartının sayısıdır; iki koşu arasında bayat değer kalmaz.
  * NK-66: kısma haritasının ayrılma hükmü kendi anahtarıyla
    (``warn.liquid.throttle_flow_separation``) ve kısma oranıyla yayımlanır;
    tasarım noktası anahtarı kısma noktasının çıkış basıncıyla basılmaz.
    CFD panelinde 1B ⟷ kesit ortalaması ⟷ duvar mutabakatı.
  * NK-34: türbin iletisi karşı basıncı adıyla ve sayısıyla verir (basınç
    oranı ⟷ basınç oranı); ham oran kırpılmaz.
  * L-A DEVİR 4: kapanmış çevrimde negatif tek kademe özgül iş payı adlı
    uyarıdır (önem: warning).
  * NK-61 + L-A DEVİR 1/3: kart satırları (devir seçimi, özgül hız, lüle ısı
    yükü, basınç beslemeli tank basıncı) ve akış şeması enjektör etiketi.
  * L-KARBON DEVİR 3: soğutma panelinde ayrı karbon birikimi bölümü.
  * NK-36: bütçe grafiğinde 'Cooling Jacket'; sarılmış kategori adı TR'de
    bütün olarak çevrilir.
"""
import contextlib
import io
import json
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
STATIC_JS = KOK / 'hrma' / 'static' / 'js'
LIQUID_HTML = KOK / 'hrma' / 'templates' / 'liquid.html'
COOLING_JS = STATIC_JS / 'panels' / 'cooling_panel.js'
CFD_JS = STATIC_JS / 'panels' / 'cfd_panel.js'
VIS_PY = KOK / 'hrma' / 'visualization' / 'visualization.py'
ORNEK = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _ornek(**ek):
    d = dict(json.loads(ORNEK.read_text(encoding='utf-8'))['inputs']['fields'])
    d.update(ek)
    return d


def _post(istemci, govde):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = istemci.post('/calculate_liquid', json=govde)
    return r.status_code, r.get_json()


def _uyari(j, kod):
    return [w for w in (j.get('input_warnings') or []) if w.get('code') == kod]


@pytest.fixture(scope='module')
def ornek_23(istemci):
    kod, j = _post(istemci, _ornek(mixture_ratio=2.3, turbine_inlet_pressure=150))
    assert kod == 200, j
    return j


# ---------------------------------------------------------------------------
# NK-39 — irtifa eğrisi kartlara oturur, bayat değer yok
# ---------------------------------------------------------------------------
def _irtifa_kart_esitligi(j):
    ap = j['altitude_performance']
    assert ap[0]['altitude'] == 0 and ap[-1]['altitude'] == 100000
    assert ap[0]['specific_impulse'] == pytest.approx(j['isp_sea_level'], rel=1e-12)
    # 100 km'de ortam 2,3e-7 bar: vakum kartından sapma < 1e-6 bağıl.
    assert ap[-1]['specific_impulse'] == pytest.approx(j['isp_vacuum'], rel=1e-6)
    # Ara satırlar aynı lüle özdeşliği: Isp(h) doğrusal p_a(h)'ye göre.
    pa_sl = j['nozzle_design']['performance']['ambient_pressure']
    for s in ap:
        beklenen = (j['isp_vacuum'] - (j['isp_vacuum'] - j['isp_sea_level'])
                    * s['pressure'] / pa_sl)
        assert s['specific_impulse'] == pytest.approx(beklenen, rel=1e-12), s
        assert 'same-nozzle identity' in s['isp_anchor_basis']
        assert 'sea-level design point' in s['isp_anchor_basis']


def test_nk39_irtifa_egrisi_iki_kosuda_da_kartlara_oturur(istemci, ornek_23):
    _irtifa_kart_esitligi(ornek_23)
    kod, j26 = _post(istemci, _ornek(mixture_ratio=2.6))
    assert kod == 200
    _irtifa_kart_esitligi(j26)
    # Ölçülen kusurun sayısı: 100 km 309,174 s idi, kart 311,010 s.
    assert j26['altitude_performance'][-1]['specific_impulse'] == pytest.approx(
        j26['isp_vacuum'], rel=1e-6)
    # V301/T-ÇAPA-D: 309,174 s ESKİ örneğin (Pc 70, Inconel; ÖRNEK 5fa435893
    # öncesi) kusurlu çıktısıydı; yeni örnekte (Pc 50) doğru 100 km değeri
    # 309,501 s tesadüfen ona 1 s'den yakın (ölçüldü 28 Eki), yani sabit
    # sayı artık kusuru ayırt etmiyor. Kusurun kendisi yukarıdaki özdeşlikle
    # (100 km satırı = vakum kartı) ölçülüyor; ek olarak ikinci koşu ilk
    # koşunun (O/F 2,3) satırını taşımıyor (bayat durum yok).
    assert j26['altitude_performance'][-1]['specific_impulse'] != pytest.approx(
        ornek_23['altitude_performance'][-1]['specific_impulse'], rel=1e-9)
    # Aynı süreçte geri dönüş: ilk koşunun sayıları birebir (bayat durum yok).
    kod, j23b = _post(istemci, _ornek(mixture_ratio=2.3, turbine_inlet_pressure=150))
    assert kod == 200
    assert [s['specific_impulse'] for s in j23b['altitude_performance']] == [
        s['specific_impulse'] for s in ornek_23['altitude_performance']]


# ---------------------------------------------------------------------------
# NK-66 — kısma ayrılması kendi anahtarında; tasarım noktası ayrılmıyor
# ---------------------------------------------------------------------------
def test_nk66_kisma_ayrilmasi_tasarim_noktasi_anahtarini_kullanmaz(ornek_23):
    j = ornek_23
    assert not _uyari(j, 'warn.liquid.flow_separation'), (
        'tasarım noktası (P_e %.3f bar) ayrılmıyor ama ayrılma anahtarı basıldı'
        % j['nozzle_angles']['exit_pressure_bar'])
    k = _uyari(j, 'warn.liquid.throttle_flow_separation')
    assert len(k) == 1 and k[0]['severity'] == 'warning'
    p = k[0]['params']
    tm = j['throttle_map']
    pe_tasarim = j['nozzle_angles']['exit_pressure_bar']
    esik = tm['separation_threshold_bar']
    assert pe_tasarim > esik
    assert p['design_pe_bar'] == round(pe_tasarim, 3)
    assert p['onset_pct'] == round(100.0 * esik / pe_tasarim, 1)
    ilk = tm['points'][0]
    assert p['throttle_pct'] == round(100.0 * ilk['throttle_fraction'], 1)
    assert p['pe_bar'] == round(ilk['exit_pressure_bar'], 3)
    assert p['pc_bar'] == round(ilk['chamber_pressure_bar'], 1)


def test_nk66_tasarim_noktasi_ayriksa_hukum_tasarim_degeriyle(istemci):
    kod, j = _post(istemci, _ornek(nozzle_expansion_ratio=30))
    assert kod == 200
    t = _uyari(j, 'warn.liquid.flow_separation')
    assert len(t) == 1
    # Basılan değer TASARIM noktasının çıkış basıncı (kısma noktasının değil).
    assert t[0]['params']['pe_bar'] == round(
        j['nozzle_angles']['exit_pressure_bar'], 3)
    assert not _uyari(j, 'warn.liquid.throttle_flow_separation')


# ---------------------------------------------------------------------------
# NK-34 — türbin iletisi aynı büyüklükleri, karşı basıncı adıyla kıyaslar
# ---------------------------------------------------------------------------
def test_nk34_turbin_iletisi_karsi_basinci_tasir(ornek_23):
    j = ornek_23
    u = _uyari(j, 'warn.liquid.turbine_pr_inconsistent')
    assert len(u) == 1
    p = u[0]['params']
    turb = j['detailed_feed_system']['engine_cycle_solution']['shafts'][0]['turbine']
    p_exit = turb['exit_pressure_bar']
    assert p['exhaust_bar'] == round(p_exit, 1)
    assert p['pr_from_inlet'] == round(150.0 / p_exit, 1)
    assert p['pr_entered'] == round(turb['pressure_ratio'], 1)
    assert p['inlet_consistent_bar'] == round(p_exit * turb['pressure_ratio'], 1)
    # Girilen oranla tutarlı giriş basıncı çözümün türbin giriş basıncıdır.
    assert p['inlet_consistent_bar'] == pytest.approx(
        turb['inlet_pressure_bar'], abs=0.06)


# ---------------------------------------------------------------------------
# L-A DEVİR 4 — negatif tek kademe özgül iş payı adlı uyarı
# ---------------------------------------------------------------------------
def test_devir4_negatif_guc_payi_uyarisi(ornek_23):
    j = ornek_23
    pm = j['detailed_feed_system']['performance_margins']['power_margin']
    assert pm < 0
    u = _uyari(j, 'warn.liquid.turbine_single_stage_work_short')
    assert len(u) == 1 and u[0]['severity'] == 'warning'
    p = u[0]['params']
    assert p['deficit_pct'] == round(-pm, 1)
    assert p['stage_count'] == (
        j['detailed_feed_system']['turbopump_analysis']['turbine']['stage_count'])
    assert p['dh_limit_kj'] < p['dh_ideal_kj']


def test_devir4_pozitif_payda_uyari_yok(istemci):
    kod, j = _post(istemci, _ornek(mixture_ratio=2.3, generator_gas_temp=700))
    assert kod == 200
    assert j['detailed_feed_system']['performance_margins']['power_margin'] > 0
    assert not _uyari(j, 'warn.liquid.turbine_single_stage_work_short')


# ---------------------------------------------------------------------------
# NK-36 — bütçe grafiğinde ceket kalemi
# ---------------------------------------------------------------------------
def test_nk36_butce_grafiginde_ceket_kalemi(ornek_23):
    pf = ornek_23['plots']['performance']
    pf = json.loads(pf) if isinstance(pf, str) else pf
    kat = {v for t in pf['data'] for v in (t.get('x') or []) if isinstance(v, str)}
    assert 'Cooling Jacket' in kat, sorted(kat)
    assert "('regen_jacket', 'Cooling Jacket')" in VIS_PY.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# Arayüz kaynakları (liquid.html, paneller)
# ---------------------------------------------------------------------------
def _islev(src, ad):
    i = src.index('function %s(' % ad)
    j = src.index('\n        }\n', i)
    return src[i:j]


def test_devir1_akis_semasi_enjektoru_pompa_besler():
    src = LIQUID_HTML.read_text(encoding='utf-8')
    govde = _islev(src, 'drawEngineDiagram')
    kod = re.sub(r'//[^\n]*', '', govde)          # yorumlar dışarıda
    assert 'required_ox_tank_pressure' not in kod
    assert 'pd.pump_discharge_pressure_ox' in govde
    assert 'required_pump_discharge_bar' in govde
    assert "'engine_diagram_note'" in govde


def test_nk61_ve_devir3_kart_satirlari():
    src = LIQUID_HTML.read_text(encoding='utf-8')
    assert '${_liqFeedTankRows(results)}' in src
    assert '_liqSpeedBasisCell(results)' in src and '_liqSpecificSpeedCell(results)' in src
    assert 'results.cooling_system.nozzle_heat_load' in src
    tank = _islev(src, '_liqFeedTankRows')
    for alan in ('required_ox_tank_pressure', 'required_fuel_tank_pressure',
                 'recommended_ox_tank_pressure_with_margin',
                 'recommended_fuel_tank_pressure_with_margin'):
        assert alan in tank


def test_karbon_bolumu_ayri_islev_ve_cagri():
    src = COOLING_JS.read_text(encoding='utf-8')
    assert 'function carbonDepositSection(data, root)' in src
    assert 'station_march.carbon_deposit' in src
    render = src[src.index('function render(data, root)'):]
    assert render.index('carbonDepositSection(data, root);') > render.index(
        'fluxPressurePlot(root, cooling);')


def test_nk66_cfd_paneli_mutabakat_bolumu():
    src = CFD_JS.read_text(encoding='utf-8')
    assert 'function exitReconciliationHtml(vm)' in src
    assert 'html += exitReconciliationHtml(vm);' in src


# ---------------------------------------------------------------------------
# EN + TR metinler (node: gerçek sözlük motoru)
# ---------------------------------------------------------------------------
_NODE_DUZENEK = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const ROOT = process.argv[2];
const sandbox = { console, setTimeout, clearTimeout, JSON, Object, Array, Math,
    RegExp, String, Number, Boolean, Date, Error };
sandbox.window = sandbox; sandbox.self = sandbox; sandbox.localStorage = null;
sandbox.document = { readyState: 'complete', documentElement: { setAttribute() {} },
    head: { appendChild() {} }, createElement: () => ({ setAttribute() {}, style: {} }),
    getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {}, dispatchEvent() { return true; } };
sandbox.CustomEvent = function (t) { this.type = t; };
vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_common.js', 'i18n_pages.js', 'i18n_charts.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sandbox, { filename: f });
}
const I = sandbox.I18N;
const uyarilar = {
  'warn.liquid.throttle_flow_separation': { onset_pct: 53.8, onset_pc_bar: 37.7,
      throttle_pct: 40.0, pc_bar: 28.0, pe_bar: 0.301, threshold_bar: 0.405,
      ratio: 0.4, design_pe_bar: 0.753 },
  'warn.liquid.turbine_pr_inconsistent': { inlet_bar: 150.0, pr_from_inlet: 7.4,
      pr_entered: 4.0, exhaust_bar: 20.1, inlet_consistent_bar: 80.6 },
  'warn.liquid.turbine_single_stage_work_short': { deficit_pct: 11.0,
      dh_ideal_kj: 693.8, dh_limit_kj: 617.3, tip_limit_ms: 500.0,
      velocity_ratio: 0.45, stage_count: 3 },
};
const anahtarlar = ['panel.regen.cdTitle', 'panel.regen.cdBandHead',
  'panel.regen.cdPeakFlux', 'panel.regen.cdStatusApplied',
  'panel.cfd.secExitRec', 'panel.cfd.exitRecNote', 'liq.js.speed_basis',
  'liq.js.speed_basis_suction', 'liq.js.specific_speed_val', 'liq.js.nozzle_heat',
  'liq.js.req_tank_p', 'liq.js.rec_tank_p', 'liq.diag.fed_by_pump',
  'liq.diag.injector_feed_not_published'];
const etiketler = ['Cooling<br>Jacket', 'Tank<br>Outlet', 'Main<br>Valve',
  'Feed<br>Lines', 'Filters<br>(assumed<br>K=10)', 'Feed System Pressure Budget (per circuit)'];
const out = {};
for (const dil of ['en', 'tr']) {
  I.setLang(dil);
  out[dil] = {
    uyari: Object.keys(uyarilar).map(k => I.tf(k, uyarilar[k], '')),
    anahtar: anahtarlar.map(k => I.t(k, null)),
    etiket: etiketler.map(e => I.chartText(e)),
  };
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def metinler(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    yol = tmp_path_factory.mktemp('le_i18n') / 'duzenek.js'
    yol.write_text(_NODE_DUZENEK, encoding='utf-8')
    p = subprocess.run([NODE, str(yol), str(STATIC_JS)], capture_output=True,
                       text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


TURKCE = re.compile('[çğıöşüÇĞİÖŞÜ]')


@needs_node
def test_uyari_metinleri_en_tr_yer_tutucusuz(metinler):
    for dil in ('en', 'tr'):
        for m in metinler[dil]['uyari']:
            assert m and '{' not in m, (dil, m)
    en, tr = metinler['en']['uyari'], metinler['tr']['uyari']
    # TR ondalık virgül, EN nokta; Türkçe karakter; çeviri EN kopyası değil.
    assert '0,301' in tr[0] and '0.301' in en[0]
    assert '%53,8' in tr[0] and '53.8%' in en[0]
    for t, e in zip(tr, en):
        assert t != e and TURKCE.search(t)
    # NK-34: "ortama karşı genişleme oranı" iddiası yok; karşı basınç adıyla.
    assert 'ortama karşı' not in tr[1] and 'against ambient' not in en[1]
    assert '20,1 bar' in tr[1] and '20.1 bar' in en[1]
    assert '80,6 bar' in tr[1]


@needs_node
def test_yeni_anahtarlar_en_tr(metinler):
    for e, t in zip(metinler['en']['anahtar'], metinler['tr']['anahtar']):
        assert e and t, (e, t)
        assert e != t or e in ('(tank)',), (e, t)


@needs_node
def test_nk36_sarilmis_etiket_tr_butun_cevrilir(metinler):
    en, tr = metinler['en']['etiket'], metinler['tr']['etiket']
    assert en == ['Cooling<br>Jacket', 'Tank<br>Outlet', 'Main<br>Valve',
                  'Feed<br>Lines', 'Filters<br>(assumed<br>K=10)',
                  'Feed System Pressure Budget (per circuit)']
    assert tr[0] == 'Soğutma<br>Ceketi'
    assert tr[1] == 'Tank<br>çıkışı'
    assert tr[2] == 'Ana<br>vana'
    assert tr[3] == 'Besleme<br>hatları'
    # Üç satırlı kaynak üç satıra bölünür; hiçbir İngilizce sözcük kalmaz.
    assert tr[4].count('<br>') == 2 and 'Filtreler' in tr[4]
    assert not re.search(r'Lines|Outlet|Valve|Jacket|assumed', ' '.join(tr[:5]))
    assert tr[5] == 'Besleme Sistemi Basınç Bütçesi (devre başına)'
