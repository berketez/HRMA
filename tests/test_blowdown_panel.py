"""Hibrit tank_blowdown panelinin bekçileri (v2.6.27, A1/A10 kullanıcı yüzü).

Denetçi ORTA bulgusu: hibrit motor tank_blowdown bloğunu (tank basıncı(t),
ṁ(t), itki düşüşü) ve not_modelled beyanlarını (7 kalem) yayımlıyor ama
HİÇBİR panel kullanıcıya göstermiyordu — "beyanı okuyan karar kapısı"
kuralının UI yarısı eksikti. blowdown_panel.js bu boşluğu kapatır; buradaki
testler sözleşmeyi kilitler:

  1. Blok TAM      → panel veri serilerini BİREBİR taşır (ölçeksiz,
                     yeniden örneklemesiz; tank + kamara basıncı AYNI eksende).
  2. Blok YOK /
     NOT_MODELLED /
     tutarsız      → HİÇBİR eğri çizilmez; gri 'modellenmedi / veri yok'
                     çipi + sunucunun gerekçesi basılır (sahte eğri yasak).
  3. Beyan şeridi  → not_modelled listesi SONUÇLA birebir; metinler ve sayı
                     sonuçtan gelir, kaynakta sabit beyan metni yoktur.
  4. Kararsızlık   → design_warnings / injector_design_detail.warnings içindeki
                     'warn.' önekli chugging/kararsızlık kayıtları panelde
                     vurgulanır; ilgisiz kodlar bu alana sızmaz.

Ölçüm yöntemi: blowdown_panel.js GERÇEK node ile, küçük bir DOM + Plotly
taklidi altında BÜTÜN olarak koşturulur (kalıp: tests/test_liquid_unwired_ui.py
harness'i); yalnız çalıştırılamayan iddialar kaynak taramasıyla sınanır.
Beyan gerçeği, motorun kendi _not_modelled_declarations sözlüğünden alınır —
şablon testi kod gerçeğine bağlanır.
"""

import html as html_mod
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PANEL_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'blowdown_panel.js'
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


# ---------------------------------------------------------------------------
# node koşum ortamı: küçük DOM + Plotly taklidi, panel dosyası bütün yüklenir
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const panelPath = process.argv[3];

const nodes = {};
function makeNode(id) {
    return {
        id: id, innerHTML: '', textContent: '', style: {}, attrs: {},
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild(c) { (this.children = this.children || []).push(c); return c; },
        addEventListener() {},
    };
}
global.document = {
    getElementById(id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement(tag) { return makeNode(null); },
    querySelector() { return null; },
    addEventListener() {},
};
const plotlyCalls = [];
global.Plotly = {
    react(el, traces, layout) {
        plotlyCalls.push({ id: el && el.id, traces: traces, layout: layout });
    },
};
global.window = global;
global.console = console;

require(panelPath);
window.BlowdownPanel.update(payload.results);

const els = {};
Object.keys(nodes).forEach(id => {
    els[id] = { html: nodes[id].innerHTML,
                text: nodes[id].textContent,
                display: nodes[id].style.display };
});
process.stdout.write(JSON.stringify({ plotly: plotlyCalls, els: els }));
"""


def _run_panel(results, tmp_path):
    """Paneli node'da koşturur; Plotly çağrıları + eleman görüntüleri döner."""
    script = tmp_path / 'kos.js'
    script.write_text(HARNESS, encoding='utf-8')
    data = tmp_path / 'girdi.json'
    data.write_text(json.dumps({'results': results}), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(data), str(PANEL_JS)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'panel node altında çöktü:\n' + proc.stderr
    return json.loads(proc.stdout)


def _tam_blok():
    """Sözleşmeye uygun sentetik tank_blowdown bloğu (5 seri, 6 nokta)."""
    return {
        'status': 'modelled',
        'basis': 'equilibrium two-phase N2O tank blowdown (test basis text)',
        'feed_mode': 'blowdown',
        'time_s': [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        'tank_pressure_bar': [50.3, 47.1, 44.0, 41.2, 38.6, 36.3],
        'chamber_pressure_bar': [20.0, 19.1, 18.3, 17.6, 16.9, 16.3],
        'mdot_ox_kg_s': [0.351, 0.336, 0.322, 0.309, 0.297, 0.286],
        'thrust_N': [1000.0, 954.0, 911.0, 872.0, 836.0, 803.0],
        'burn_duration_s': 5.0,
        'total_impulse_Ns': 4376.0,
        'thrust_decay_fraction': 0.197,
        'initial_pressure_bar': 50.3,
        'end_event': 'oxidizer_depleted',
        'warnings': [],
    }


def _motor(**degisiklik):
    motor = {'thrust': 1000.0, 'tank_blowdown': _tam_blok()}
    motor.update(degisiklik)
    return motor


@pytest.fixture(scope='module')
def gercek_beyanlar():
    """Motorun GERÇEK A10 beyanları — UI testi kod gerçeğine bağlanır.

    _not_modelled_declarations hiçbir self alanı kullanmaz (salt sabit
    sözlük döndürür); motor kurmak (CEA) gereksiz pahalı olurdu — aynı
    kestirme tests/test_liquid_unwired_ui.py::engine_unwired'da da var.
    """
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    return HybridRocketEngine._not_modelled_declarations(None)


def kaynak():
    return PANEL_JS.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# 0. Sözdizim + şablon bağlaması
# ---------------------------------------------------------------------------
@needs_node
def test_panel_dosyasi_sozdizimi_gecerli(tmp_path):
    proc = subprocess.run([NODE, '--check', str(PANEL_JS)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_advanced_html_paneli_bagliyor():
    """Script etiketi + init çağrısı + beyan şeridi çapası şablonda var."""
    html = ADVANCED_HTML.read_text(encoding='utf-8')
    assert '/static/js/blowdown_panel.js' in html, 'script etiketi yok'
    assert 'BlowdownPanel.init' in html, 'panel hiç kurulmuyor'
    assert re.search(r'<div id="notModelledStrip"[^>]*display:\s*none',
                     html), 'beyan şeridi çapası yok ya da açılışta gizli değil'
    # Şerit, sonuç bölümünün BAŞINDA durmalı: resultsPanel ile
    # performanceMetrics arasında.
    assert (html.index('id="resultsPanel"')
            < html.index('id="notModelledStrip"')
            < html.index('id="performanceMetrics"')), \
        'beyan şeridi sonuç bölümünün başında değil'
    # Panel script'i, init'i çağıran satır içi bloktan ÖNCE yüklenmeli.
    assert (html.index('/static/js/blowdown_panel.js')
            < html.index('BlowdownPanel.init'))


def test_hesap_koprusu_ozgun_islevi_koruyor():
    """displayCalculationResults sarılır ama HER KOŞULDA çağrılır."""
    src = kaynak()
    assert 'window.displayCalculationResults' in src, 'hesap köprüsü yok'
    sarmal = src[src.index('const original = window.displayCalculationResults'):]
    sarmal = sarmal[:sarmal.index('})();')]
    assert 'original.apply(this, arguments)' in sarmal
    # update hata verse bile özgün çıktı dönmeli (try/catch şart)
    assert 'try {' in sarmal and 'catch' in sarmal, \
        'panel hatası ana hesap gösterimini kırabilir'


# ---------------------------------------------------------------------------
# 1. Blok TAM → seriler birebir
# ---------------------------------------------------------------------------
@needs_node
def test_tam_blok_serileri_birebir_tasinir(tmp_path):
    """Panel eğrileri bloktaki dizilerin AYNISIDIR — ölçek/örnekleme yok."""
    blok = _tam_blok()
    out = _run_panel({'motor': _motor()}, tmp_path)
    grafikler = {c['id']: c for c in out['plotly']}
    assert set(grafikler) == {'bp_plot_pressure', 'bp_plot_mdot',
                              'bp_plot_thrust'}, \
        'beklenen üç grafik çizilmedi: %s' % sorted(grafikler)

    basinc = grafikler['bp_plot_pressure']['traces']
    assert len(basinc) == 2, 'tank + kamara iki eğri olmalı'
    assert basinc[0]['x'] == blok['time_s']
    assert basinc[0]['y'] == blok['tank_pressure_bar']
    assert basinc[1]['x'] == blok['time_s']
    assert basinc[1]['y'] == blok['chamber_pressure_bar']

    mdot = grafikler['bp_plot_mdot']['traces']
    assert len(mdot) == 1 and mdot[0]['y'] == blok['mdot_ox_kg_s']
    assert mdot[0]['x'] == blok['time_s']

    itki = grafikler['bp_plot_thrust']['traces']
    assert len(itki) == 1 and itki[0]['y'] == blok['thrust_N']
    assert itki[0]['x'] == blok['time_s']


@needs_node
def test_tank_ve_kamara_ayni_eksende(tmp_path):
    """Görev sözleşmesi: iki basınç eğrisi AYNI eksende (aradaki fark ΔP)."""
    out = _run_panel({'motor': _motor()}, tmp_path)
    basinc = next(c for c in out['plotly'] if c['id'] == 'bp_plot_pressure')
    for iz in basinc['traces']:
        assert iz.get('yaxis') is None, \
            'basınç eğrisi ikinci eksene kaçmış: %r' % iz.get('yaxis')
    assert 'yaxis2' not in basinc['layout']


@needs_node
def test_rozetler_bloktaki_degerleri_tasiyor(tmp_path):
    """end_event ve feed_mode rozetleri bloktan gelir, uydurulmaz."""
    out = _run_panel({'motor': _motor()}, tmp_path)
    rozetler = out['els']['bp_badges']['html']
    assert 'BLOWDOWN' in rozetler, 'feed_mode rozeti yok'
    assert 'OXIDIZER_DEPLETED' in rozetler, 'end_event rozeti yok'
    assert '5.00' in rozetler, 'yanma süresi rozeti bloktan okunmuyor'
    # Çip yok, grafikler görünür
    assert 'data-chip' not in out['els']['bp_chip']['html']
    assert out['els']['bp_plot_pressure']['display'] == 'block'


@needs_node
def test_basis_kunyesi_sunucudan_aynen_gosterilir(tmp_path):
    out = _run_panel({'motor': _motor()}, tmp_path)
    assert out['els']['bp_basis_text']['text'] == \
        'equilibrium two-phase N2O tank blowdown (test basis text)'
    assert out['els']['bp_basis']['display'] == ''


# ---------------------------------------------------------------------------
# 2. Blok yok / NOT_MODELLED / tutarsız → çip, eğri yok
# ---------------------------------------------------------------------------
@needs_node
def test_blok_yoksa_cip_var_egri_yok(tmp_path):
    out = _run_panel({'motor': {'thrust': 1000.0}}, tmp_path)
    assert out['plotly'] == [], 'blok yokken eğri çizildi (sahte veri)'
    cip = out['els']['bp_chip']['html']
    assert 'data-chip="not-modelled"' in cip, 'veri-yok çipi basılmadı'
    assert 'NO DATA' in cip
    for grafik in ('bp_plot_pressure', 'bp_plot_mdot', 'bp_plot_thrust'):
        assert out['els'][grafik]['display'] == 'none'


@needs_node
def test_not_modelled_blok_gerekce_ile_cip(tmp_path):
    """status NOT_MODELLED → çip + sunucunun reason metni aynen ekranda."""
    gerekce = ('the self-pressurised blowdown model in '
               'hrma/analysis/tank_blowdown.py is N2O-specific')
    motor = {'tank_blowdown': {'status': 'NOT_MODELLED',
                               'basis': 'test basis',
                               'reason': gerekce}}
    out = _run_panel({'motor': motor}, tmp_path)
    assert out['plotly'] == [], 'NOT_MODELLED blokta eğri çizildi'
    cip = out['els']['bp_chip']['html']
    assert 'data-chip="not-modelled"' in cip
    assert 'NOT MODELLED' in cip
    assert gerekce in html_mod.unescape(cip), 'sunucu gerekçesi ekranda yok'


@needs_node
def test_tutarsiz_seriler_cizilmez(tmp_path):
    """Seri boyları uyuşmuyorsa KISMÎ eğri de çizilmez; çip basılır."""
    blok = _tam_blok()
    blok['mdot_ox_kg_s'] = blok['mdot_ox_kg_s'][:-2]      # boy uyuşmazlığı
    out = _run_panel({'motor': {'tank_blowdown': blok}}, tmp_path)
    assert out['plotly'] == [], 'tutarsız serilerle eğri çizildi'
    assert 'data-chip="not-modelled"' in out['els']['bp_chip']['html']


@needs_node
def test_sonuc_yokken_hicbir_sey_basilmaz(tmp_path):
    out = _run_panel(None, tmp_path)
    assert out['plotly'] == []
    assert out['els'].get('bp_chip', {}).get('html', '') == ''
    assert out['els'].get('notModelledStrip', {}).get('display') == 'none'


# ---------------------------------------------------------------------------
# 3. Beyan şeridi: not_modelled ile birebir
# ---------------------------------------------------------------------------
@needs_node
def test_beyan_listesi_motorun_gercek_beyanlariyla_birebir(
        gercek_beyanlar, tmp_path):
    """Şerit, motorun GERÇEK beyan metinlerini aynen listeler; sayı gerçek.

    Alt sınır SABİT DEĞİL: beyan sayısı bir kalem gerçekten modellendiğinde
    DÜŞMELİDİR (2026-08-04: A5 ablatif astarı + A2 slosh bağlanınca 7 → 6).
    Sabit sayı burada beyan çürümesini engellemek yerine bağlamayı yasaklardı.
    Ölçülen sözleşme: blok boş değil ve şeritteki liste motorunkiyle birebir.
    """
    assert gercek_beyanlar, 'motor hiç NOT_MODELLED beyanı yayımlamıyor'
    motor = {'not_modelled': gercek_beyanlar,
             'not_modelled_basis': 'declared absence basis (test)'}
    out = _run_panel({'motor': motor}, tmp_path)
    serit = html_mod.unescape(out['els']['notModelledStrip']['html'])
    for anahtar, metin in gercek_beyanlar.items():
        assert metin in serit, 'beyan şeritte yok: %s' % anahtar
    assert 'data-decl-count="%d"' % len(gercek_beyanlar) in serit, \
        'beyan sayısı listenin gerçek uzunluğu değil'
    assert 'declared absence basis (test)' in serit, \
        'not_modelled_basis şeritte gösterilmiyor'
    assert out['els']['notModelledStrip']['display'] == ''


@needs_node
def test_beyan_sayisi_sonuctan_gelir_sabit_degil(tmp_path):
    """2 kalemlik yanıt → şerit 2 sayar (sabit '7' yazılamaz)."""
    motor = {'not_modelled': {'a_item': 'NOT_MODELLED: first (test)',
                              'b_item': 'NOT_MODELLED: second (test)'}}
    out = _run_panel({'motor': motor}, tmp_path)
    serit = out['els']['notModelledStrip']['html']
    assert 'data-decl-count="2"' in serit
    assert 'NOT_MODELLED: first (test)' in serit


def test_kaynakta_sabit_beyan_metni_yok(gercek_beyanlar):
    """Beyan metinleri sonuçtan okunur; JS kaynağında kopyaları duramaz."""
    src = kaynak()
    for anahtar, metin in gercek_beyanlar.items():
        parca = metin[:40]
        assert parca not in src, \
            'beyan metni panele sabit kodlanmış: %s' % anahtar
        # beyan anahtarları da sabitlenmemeli (liste yanıttan dolaşılır)
        assert "'%s'" % anahtar not in src, \
            'beyan anahtarı panele sabit kodlanmış: %s' % anahtar


# ---------------------------------------------------------------------------
# 4. Kararsızlık uyarıları vurgulu
# ---------------------------------------------------------------------------
@needs_node
def test_kararsizlik_uyarilari_vurgulanir_ilgisizler_sizmasin(tmp_path):
    """warn. önekli chugging/kararsızlık kodları vurgulu alana düşer."""
    motor = _motor(
        design_warnings=[
            {'code': 'warn.injector.chug_risk', 'severity': 'warning',
             'params': {'ratio': 0.12, 'min_ratio': 0.15}},
            {'code': 'warn.hybrid.chamber_material_unknown',
             'severity': 'warning', 'params': {}},
        ],
        injector_design_detail={'warnings': [
            {'code': 'warn.injector.n2o_feed_coupling_risk',
             'severity': 'warning', 'params': {'ratio': 0.18,
                                               'recommended': 0.20}},
        ]})
    out = _run_panel({'motor': motor}, tmp_path)
    alan = out['els']['bp_instability']['html']
    assert 'data-warn-code="warn.injector.chug_risk"' in alan
    assert 'data-warn-code="warn.injector.n2o_feed_coupling_risk"' in alan
    assert 'chamber_material_unknown' not in alan, \
        'kararsızlıkla ilgisiz uyarı vurgu alanına sızdı'


@needs_node
def test_blok_ici_chugging_metni_kirmizi_vurgulu(tmp_path):
    """transient çözücüsünün serbest-metin chugging uyarısı 'err' vurgusu alır."""
    blok = _tam_blok()
    blok['warnings'] = [
        't=3.10s: ΔP/Pc=0.18 < 0.2 — chugging risk (SP-8089)',
        'tank temperature clamped to model band (test, benign)',
    ]
    out = _run_panel({'motor': {'tank_blowdown': blok, 'thrust': 1000.0}},
                     tmp_path)
    rozetler = out['els']['bp_badges']['html']
    assert 'chugging risk (SP-8089)' in rozetler
    # chugging → data-warn="instability"; zararsız uyarı → "general".
    # Uyarı metnindeki '<' esc ile '&lt;' olur; bu yüzden kaçışlı HTML
    # üzerinde aranır (eleman gövdesinde ham '<' kalmaz).
    inst = re.findall(r'data-warn="instability"[^>]*>[^<]*chugging',
                      rozetler, re.S)
    assert inst, 'chugging uyarısı kararsızlık vurgusu almamış'
    genel = re.findall(r'data-warn="general"[^>]*>[^<]*clamped', rozetler, re.S)
    assert genel, 'zararsız blok uyarısı yanlışlıkla kararsızlık vurgusu almış'


@needs_node
def test_kararsizlik_uyarilari_blok_yokken_de_gosterilir(tmp_path):
    """Blowdown NOT_MODELLED olsa da besleme kararsızlığı karar kapısıdır."""
    motor = {'tank_blowdown': {'status': 'NOT_MODELLED', 'basis': 'b',
                               'reason': 'r'},
             'design_warnings': [
                 {'code': 'warn.injector.chug_risk', 'severity': 'warning',
                  'params': {'ratio': 0.1, 'min_ratio': 0.15}}]}
    out = _run_panel({'motor': motor}, tmp_path)
    assert 'warn.injector.chug_risk' in out['els']['bp_instability']['html']


# ---------------------------------------------------------------------------
# 5. Sahte veri yasağı + i18n disiplini (kaynak taraması)
# ---------------------------------------------------------------------------
def test_kaynakta_uydurma_veri_ureteci_yok():
    src = kaynak()
    assert 'Math.random' not in src, 'panelde rastgele veri üretimi var'
    # Seriler bloktan referansla taşınır; sayısal dizi literali (uydurma
    # eğri tohumu) kaynakta duramaz.
    assert not re.search(r'\[\s*\d+(\.\d+)?\s*,\s*\d+(\.\d+)?\s*,', src), \
        'kaynakta sayısal seri literali var (uydurma eğri şüphesi)'


def test_her_t_cagrisinin_ingilizce_yedegi_var():
    """Sözlük anahtarı kayıtlı değilken bile ekrana ham anahtar basılmaz."""
    src = kaynak()
    yediksiz = re.findall(r"\bT\(\s*'[^']+'\s*\)", src)
    assert not yediksiz, 'yedeksiz T() çağrıları: %s' % yediksiz
    yediksiz_tf = re.findall(r"\bTF\(\s*'[^']+'\s*,\s*[^,]+\)\s*[;)]", src)
    assert not yediksiz_tf, 'yedeksiz TF() çağrıları: %s' % yediksiz_tf


def test_yeni_anahtarlar_blowdown_onekli():
    """Panele özgü anahtarlar 'blowdown.' ile başlar; ortak anahtarlar
    (common./transient.) mevcut sözlük kayıtlarını yeniden kullanır."""
    src = kaynak()
    anahtarlar = set(re.findall(r"\bTF?\(\s*'([^']+)'", src))
    assert anahtarlar, 'panel hiç i18n anahtarı kullanmıyor'
    for anahtar in anahtarlar:
        assert anahtar.split('.')[0] in ('blowdown', 'common', 'transient'), \
            'beklenmeyen anahtar alanı: %s' % anahtar


def test_cip_rengi_viz3d_missing_kalibiyla_ayni():
    """Çip, motor_viz3d SOURCE_COLORS.missing grisiyle aynı dili konuşur."""
    src = kaynak()
    assert "MISSING_COLOR = '#8a93a0'" in src
    viz = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'motor_viz3d.js').read_text(
        encoding='utf-8')
    assert "missing: '#8a93a0'" in viz, \
        'viz3d missing rengi değişmiş — çip kalıbı ayrıştı, ikisini eşitleyin'


@needs_node
def test_dil_degisiminde_yeniden_cizim_kaydi_var():
    """i18n.onChange kancası kayıtlı (dil değişince panel eski dilde kalmaz)."""
    src = kaynak()
    assert 'I18N.onChange' in src
