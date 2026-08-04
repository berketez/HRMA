"""fea_panel.js bekçileri (D5 — yapısal FEA panelinin kullanıcı yüzü).

KAPATILAN KUSUR
---------------
``hrma/fea/`` çözücüleri depoda çalışıyordu ama kullanıcıya HİÇBİR ŞEY
göstermiyordu. Panel POST /api/fea/structural yanıtını çizer; buradaki
bekçiler panelin sözleşmesini kilitler:

  1. KONTUR VERİSİ ÇÖZÜCÜDEN BİREBİR — carpet ızgarası düğüm
     koordinatlarının kendisidir, kontur değerleri von Mises alanının
     yalnız Pa → MPa bölünmüş hâlidir (yumuşatma/yeniden örnekleme yok).
  2. MESH TEL-KAFESİ META İLE TUTARLI — çizilen düğüm sayısı sunucunun
     beyan ettiği ``n_nodes`` ile birebir uyar (her düğüm bir i-çizgisinde,
     bir j-çizgisinde geçer).
  3. KALİTE EŞİĞİ AŞAN ELEMAN KIRMIZI — eşik SUNUCUDAN gelir; panelde eşik
     sabiti yoktur. Tek eleman kötüyse yalnız o eleman kırmızıya girer.
  4. YAKINSAMA GRAFİĞİ GERÇEK GEÇMİŞTEN — noktalar köprünün ``history``
     kayıtlarıdır.
  5. SAHTE VERİ YASAĞI — NOT_MODELLED / tutarsız ızgara / SF yayımlanmamış
     hâllerinde ilgili grafik HİÇ kurulmaz; gerekçe basılır.
  6. SAHTE İLERLEME YASAĞI — koşarken yüzdeli çubuk yoktur, belirsiz
     gösterge kullanılır.

ÖLÇÜM YÖNTEMİ
-------------
Panel GERÇEK node ile, küçük bir DOM + Plotly taklidi altında BÜTÜN olarak
koşturulur (kalıp: tests/test_blowdown_panel.py). Çizilen veri, GERÇEK
çözücü koşusundan gelen uç yanıtıyla karşılaştırılır — beklenen değerler
testte elle yazılmaz, yanıttan türetilir (bekçi kusuru kilitlemez).
"""

import copy
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_fea_endpoint import kos, sentetik_hibrit_motor

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PANEL_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'fea_panel.js'
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

PA_PER_MPA = 1e6          # panelin beyan ettiği tek dönüşüm


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
        checked: true, value: '',
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
    createElement() { return makeNode(null); },
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
if (payload.showMesh === false) window.FeaPanel.setShowMesh(false);
if (payload.metric) window.FeaPanel.setQualityMetric(payload.metric);
plotlyCalls.length = 0;                       // kurulum çağrıları sayılmaz
window.FeaPanel.applyPayload(payload.fea, payload.error || null);
if (payload.yeniMotorSonucu) {
    plotlyCalls.length = 0;                   // eski çizimler sayılmasın
    window.FeaPanel.update(payload.yeniMotorSonucu);
}

const els = {};
Object.keys(nodes).forEach(id => {
    els[id] = { html: nodes[id].innerHTML,
                text: nodes[id].textContent,
                display: nodes[id].style.display,
                attrs: nodes[id].attrs };
});
process.stdout.write(JSON.stringify({ plotly: plotlyCalls, els: els }));
"""


def _run_panel(fea, tmp_path, error=None, show_mesh=None, metric=None,
               yeni_motor_sonucu=None):
    """Paneli node'da koşturur; Plotly çağrıları + eleman görüntüleri döner."""
    script = tmp_path / 'kos.js'
    script.write_text(HARNESS, encoding='utf-8')
    girdi = {'fea': fea, 'error': error}
    if yeni_motor_sonucu is not None:
        girdi['yeniMotorSonucu'] = yeni_motor_sonucu
    if show_mesh is not None:
        girdi['showMesh'] = show_mesh
    if metric is not None:
        girdi['metric'] = metric
    data = tmp_path / 'girdi.json'
    data.write_text(json.dumps(girdi), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(data), str(PANEL_JS)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, 'panel node altında çöktü:\n' + proc.stderr
    return json.loads(proc.stdout)


def _cagri(sonuc, plot_id):
    for c in sonuc['plotly']:
        if c['id'] == plot_id:
            return c
    return None


def _iz(cagri, tip):
    return [t for t in cagri['traces'] if t.get('type') == tip]


def kaynak():
    return PANEL_JS.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def fea(client):
    """GERÇEK çözücü koşusunun uç yanıtı (fea bloğu)."""
    kod, govde = kos(client, sentetik_hibrit_motor())
    assert kod == 200 and govde['fea']['status'] == 'ok', govde
    return govde['fea']


# ---------------------------------------------------------------------------
# 0. Sözdizim + şablon bağlaması
# ---------------------------------------------------------------------------
@needs_node
def test_panel_sozdizimi_gecerli():
    proc = subprocess.run([NODE, '--check', str(PANEL_JS)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_advanced_html_paneli_yukluyor_ve_kuruyor():
    html = ADVANCED_HTML.read_text(encoding='utf-8')
    assert '/static/js/fea_panel.js' in html, 'panel dosyası sayfaya bağlanmamış'
    assert 'FeaPanel.init(' in html, 'panel kurulmuyor (init çağrısı yok)'


# ---------------------------------------------------------------------------
# 1. Kontur verisi çözücüden BİREBİR
# ---------------------------------------------------------------------------
@needs_node
class TestKonturVerisi:
    def test_carpet_izgarasi_dugum_koordinatlarinin_kendisi(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path)
        cagri = _cagri(sonuc, 'fea_plot_vm')
        assert cagri is not None, 'von Mises grafiği çizilmemiş'
        carpet = _iz(cagri, 'carpet')
        assert len(carpet) == 1
        g = fea['mesh']['node_index_grid']
        nodes = fea['mesh']['nodes']
        ni, nj = len(g), len(g[0])
        assert len(carpet[0]['x']) == nj and len(carpet[0]['x'][0]) == ni
        for j in range(nj):
            for i in range(ni):
                assert carpet[0]['x'][j][i] == nodes[g[i][j]][0]
                assert carpet[0]['y'][j][i] == nodes[g[i][j]][1]

    def test_kontur_degerleri_alanin_MPa_karsiligi(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path)
        cagri = _cagri(sonuc, 'fea_plot_vm')
        cc = _iz(cagri, 'contourcarpet')
        assert len(cc) == 1
        g = fea['mesh']['node_index_grid']
        vm = fea['fields']['von_mises_pa']
        for j in range(len(g[0])):
            for i in range(len(g)):
                assert cc[0]['z'][j][i] == vm[g[i][j]] / PA_PER_MPA

    def test_sf_haritasi_alanin_kendisi(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path)
        cagri = _cagri(sonuc, 'fea_plot_sf')
        assert cagri is not None, 'SF alanı yayımlandığı hâlde çizilmemiş'
        cc = _iz(cagri, 'contourcarpet')[0]
        g = fea['mesh']['node_index_grid']
        sf = fea['fields']['safety_factor']
        for j in range(len(g[0])):
            for i in range(len(g)):
                assert cc['z'][j][i] == sf[g[i][j]]


# ---------------------------------------------------------------------------
# 2. Mesh tel-kafesi
# ---------------------------------------------------------------------------
@needs_node
class TestTelKafes:
    def _wire(self, cagri):
        for t in cagri['traces']:
            if t.get('mode') == 'lines' and t.get('hoverinfo') == 'skip':
                return t
        return None

    def test_dugum_sayisi_meta_ile_tutarli(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path)
        wire = self._wire(_cagri(sonuc, 'fea_plot_vm'))
        assert wire is not None, 'tel-kafes katmanı çizilmemiş'
        dolu = [v for v in wire['x'] if v is not None]
        # Her düğüm bir i-çizgisinde, bir j-çizgisinde geçer.
        assert len(dolu) == 2 * fea['mesh']['n_nodes']
        assert len(wire['x']) == len(wire['y'])
        # Çizilen noktalar mesh düğümlerinin kümesidir (uydurma nokta yok).
        cizilen = {(x, y) for x, y in zip(wire['x'], wire['y'])
                   if x is not None}
        gercek = {(n[0], n[1]) for n in fea['mesh']['nodes']}
        assert cizilen == gercek

    def test_katman_kapatilinca_telkafes_cizilmez(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path, show_mesh=False)
        for pid in ('fea_plot_vm', 'fea_plot_sf', 'fea_plot_quality'):
            cagri = _cagri(sonuc, pid)
            if cagri:
                assert self._wire(cagri) is None, f'{pid} tel-kafesi kapanmamış'


# ---------------------------------------------------------------------------
# 3. Eleman kalite boyaması
# ---------------------------------------------------------------------------
@needs_node
class TestKalite:
    KIRMIZI = '#ff5d73'

    def _kirmizi(self, cagri):
        """Eşik dışı eleman katmanı: tek renkli (dizi olmayan) kırmızı iz."""
        for t in cagri['traces']:
            m = t.get('marker') or {}
            renk = m.get('color')
            if isinstance(renk, str) and renk.lower() == self.KIRMIZI:
                return t
        return None

    def test_esik_disi_katman_ayirt_ediciyse_cizilir(self, fea, tmp_path):
        """Kırmızı katman AYIRT EDİCİ olduğunda çizilir.

        Hiçbiri ya da hepsi eşik dışıysa katman bilgi taşımaz (hepsi
        kırmızıysa ölçüt haritasını da örter); o hâlde sayı not satırında
        ve rozette YAZILI kalır — gizlenmez.
        """
        sonuc = _run_panel(fea, tmp_path)
        cagri = _cagri(sonuc, 'fea_plot_quality')
        assert cagri is not None, 'kalite haritası çizilmemiş'
        kirmizi = self._kirmizi(cagri)
        sayim = fea['quality']['counts']
        toplam, kotu = sayim['n_elems'], sayim['flagged']
        not_html = sonuc['els']['fea_quality_note']['html']
        assert str(kotu) in not_html and str(toplam) in not_html
        if kotu == 0 or kotu == toplam:
            assert kirmizi is None
        else:
            assert kirmizi is not None
            assert len(kirmizi['x']) == kotu
            assert kirmizi['marker']['color'].lower() == self.KIRMIZI

    def test_tek_kotu_eleman_yalniz_o_elemani_kirmiziya_sokar(self, fea, tmp_path):
        """Eşik SUNUCUDAN gelir; bayrak aritmetiği panelde doğrulanır."""
        bozuk = copy.deepcopy(fea)
        q = bozuk['quality']
        th = q['thresholds']
        n = len(q['aspect_ratio'])
        hedef = n // 3
        q['aspect_ratio'] = [1.0] * n
        q['aspect_ratio'][hedef] = th['aspect_ratio_max'] * 10.0
        q['scaled_jacobian'] = [1.0] * n
        sonuc = _run_panel(bozuk, tmp_path)
        kirmizi = self._kirmizi(_cagri(sonuc, 'fea_plot_quality'))
        assert kirmizi is not None and len(kirmizi['x']) == 1
        elem = bozuk['mesh']['elems'][hedef]
        nodes = bozuk['mesh']['nodes']
        mx = sum(nodes[k][0] for k in elem) / len(elem)
        my = sum(nodes[k][1] for k in elem) / len(elem)
        assert kirmizi['x'][0] == pytest.approx(mx)
        assert kirmizi['y'][0] == pytest.approx(my)

    def test_esikler_panelde_sabit_degil(self):
        """Panel kaynağında kalite eşiği sabiti BULUNMAMALI (tek tanım
        yeri sunucudur; eşik değiştiğinde panel kendiliğinden uyar)."""
        src = kaynak()
        assert 'quality.thresholds' in src, 'panel eşikleri yanıttan okumuyor'
        # Eşik adına SAYI atanmışsa panel kendi eşiğini uyduruyor demektir.
        for ad in ('aspect_ratio_max', 'scaled_jacobian_min'):
            kotu = re.search(ad + r'\s*[:=]\s*[-+0-9.]', src)
            assert kotu is None, f'panelde eşik sabiti var: {kotu.group(0)!r}'

    def test_olcut_secimi_ayni_diziyi_kullanir(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path, metric='scaled_jacobian')
        cagri = _cagri(sonuc, 'fea_plot_quality')
        renkli = None
        for t in cagri['traces']:
            m = t.get('marker') or {}
            if isinstance(m.get('color'), list):
                renkli = t
        assert renkli is not None
        assert renkli['marker']['color'] == fea['quality']['scaled_jacobian']


# ---------------------------------------------------------------------------
# 4. Yakınsama grafiği
# ---------------------------------------------------------------------------
@needs_node
class TestYakinsama:
    def test_noktalar_gercek_gecmisten(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path)
        cagri = _cagri(sonuc, 'fea_plot_conv')
        assert cagri is not None, 'yakınsama grafiği çizilmemiş'
        iz = cagri['traces'][0]
        hist = fea['convergence']['history']
        assert iz['x'] == [h['n_elems'] for h in hist]
        assert iz['y'] == [h['max_von_mises'] / PA_PER_MPA for h in hist]

    def test_beyan_sunucunun_cumlesini_tasir(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path)
        not_html = sonuc['els']['fea_conv_note']['html']
        assert fea['convergence']['beyan'][:40] in not_html
        # Tur sayısı ve son fark METİNDE de var (sabit sayı yazılmaz).
        assert str(len(fea['convergence']['history'])) in not_html


# ---------------------------------------------------------------------------
# 5. Sahte veri yasağı
# ---------------------------------------------------------------------------
@needs_node
class TestSahteVeriYasagi:
    def test_not_modelled_hicbir_cizim_yok(self, client, tmp_path):
        kod, govde = kos(client, {'thrust': 1.0})
        assert kod == 200 and govde['fea']['status'] == 'NOT_MODELLED'
        sonuc = _run_panel(govde['fea'], tmp_path)
        assert sonuc['plotly'] == [], 'redli sonuçta grafik çizilmiş'
        cip = sonuc['els']['fea_chip']['html']
        assert 'not-modelled' in cip
        for eksik in govde['fea']['missing']:
            assert eksik.split(' ')[0] in cip

    def test_sf_yayimlanmadiysa_sf_grafigi_kurulmaz(self, fea, tmp_path):
        bozuk = copy.deepcopy(fea)
        bozuk['fields']['safety_factor'] = None
        bozuk['scalars']['min_safety_factor'] = None
        bozuk['scalars']['yield_strength_pa'] = None
        sonuc = _run_panel(bozuk, tmp_path)
        assert _cagri(sonuc, 'fea_plot_sf') is None
        assert _cagri(sonuc, 'fea_plot_vm') is not None
        assert 'NOT PUBLISHED' in sonuc['els']['fea_badges']['html'].upper()

    def test_izgara_tutarsizsa_hicbir_sey_cizilmez(self, fea, tmp_path):
        bozuk = copy.deepcopy(fea)
        bozuk['mesh']['n_nodes'] = bozuk['mesh']['n_nodes'] + 7
        sonuc = _run_panel(bozuk, tmp_path)
        assert sonuc['plotly'] == []
        assert 'not-modelled' in sonuc['els']['fea_chip']['html']

    def test_sunucu_hatasi_cizim_yerine_gerekce(self, fea, tmp_path):
        sonuc = _run_panel(None, tmp_path, error='solver exploded')
        assert sonuc['plotly'] == []
        assert 'solver exploded' in sonuc['els']['fea_chip']['html']

    def test_yeni_motor_sonucu_eski_fea_ciktisini_siler(self, fea, tmp_path):
        """Bayat gerilme alanı yeni motorunmuş gibi ekranda kalmaz."""
        sonuc = _run_panel(fea, tmp_path,
                           yeni_motor_sonucu={'motor': {'thrust': 5000.0}})
        assert sonuc['plotly'] == [], 'yeni hesaptan sonra eski alan çiziliyor'
        assert sonuc['els']['fea_plot_vm']['display'] == 'none'
        assert 'not-modelled' in sonuc['els']['fea_chip']['html']

    def test_sahte_ilerleme_gostergesi_yok(self):
        src = kaynak().lower()
        assert 'progress' not in src, 'panelde ilerleme çubuğu izi var'
        assert 'data-indeterminate' in kaynak(), \
            'belirsiz süreli koşu için belirsiz gösterge yok'
