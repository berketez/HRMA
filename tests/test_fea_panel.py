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
  7. KALİTE ROZETİ AYRIŞMIŞ (2026-08-15) — alarm rengi YALNIZ ölçekli
     Jacobian bayrağından sürülür; en-boy oranı sayımı ayrı ve NÖTR
     rozettedir. Ölçülmemiş ölçüt yeşil hüküm almaz. Bu bölümdeki
     bekçilerin bir kısmı KUSURU KİLİTLEMEYİ engellemek için negatiftir:
     uzama sayımının alarm sınıfını sürememesi ayrıca sınanır.
  8. TANE PANELİNDE HÜKÜM KABUL ÖLÇÜTÜNÜN (2026-08-15) — sunucu
     ``convergence.acceptance`` yayımlarsa yakınsama hükmü port gerinimi
     yakınsamasından verilir, tepe von Mises ayrı ve nötr bilgi olur.
     Blok yoksa davranış birebir eskisidir (geriye uyum sınanır).

NEDEN AYRIŞMA (ölçüm, 2026-08-15)
---------------------------------
Canlı üründe iki panel de "MESH QUALITY 1024/1024 (tane: 6144/6144)
elements outside the acceptable range" alarmı basıyordu. Aynı yanıttaki
gerçek: en-boy oranı 27,3-38,4 (eşik 4,0 → hepsi bayraklı) ama ölçekli
Jacobian 0,96-1,0 (eşik 0,5 → SIFIR bayrak; tanede tam 1,0). Sunucunun
kendi ``quality._basis`` cümlesi de bunu söylüyor: uzun kontur boyunca
süpürülen ince cidar uzamış eleman ÜRETİR, gerçek bozulmayı ölçekli
Jacobian raporlar. Yani alarm, bozulma sıfırken korkutuyordu.

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
# Tane kesiti paneli (GrainFeaPanel) AYNI dosyada yaşar; bekçisi de burada.
# Yükü uydurmamak için düzlemsel uç koşucusu ödünç alınır (o dosya
# çözücünün kendisini kilitler, burası panelin sözleşmesini).
from tests.test_fea_planar_grain import uc_kos as grain_uc_kos

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


# Tane kesiti paneli için aynı taklit ortam; fark yalnız kurulan panel ve
# etiket kaynağıdır (GrainFeaPanel etiketleri labelsProvider'dan alır,
# sağlayıcı verilmediğinde panelin KENDİ İngilizce yedekleri basılır —
# bekçiler tam da o yedek metni kilitler).
GRAIN_HARNESS = HARNESS.replace(
    "window.FeaPanel.setShowMesh(false);",
    "window.GrainFeaPanel.setShowMesh(false);").replace(
    "if (payload.metric) window.FeaPanel.setQualityMetric(payload.metric);",
    "").replace(
    "window.FeaPanel.applyPayload(payload.fea, payload.error || null);",
    "window.GrainFeaPanel.applyPayload(payload.fea, payload.error || null);"
).replace(
    "window.FeaPanel.update(payload.yeniMotorSonucu);",
    "window.GrainFeaPanel.update();")


def _run_grain_panel(fea, tmp_path, error=None, show_mesh=None):
    """Tane kesiti panelini node'da koşturur (aynı DOM/Plotly taklidi)."""
    script = tmp_path / 'kos_grain.js'
    script.write_text(GRAIN_HARNESS, encoding='utf-8')
    girdi = {'fea': fea, 'error': error}
    if show_mesh is not None:
        girdi['showMesh'] = show_mesh
    data = tmp_path / 'girdi_grain.json'
    data.write_text(json.dumps(girdi), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(data), str(PANEL_JS)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, 'tane paneli node altında çöktü:\n' + proc.stderr
    return json.loads(proc.stdout)


#: Rozet şeridi ayrıştırıcı — ``badge()`` çıktısı: data-badge sınıfı + metin.
ROZET_RE = re.compile(r'<span data-badge="(\w+)"[^>]*>(.*?)</span>', re.S)


def _rozetler(html):
    """[(sınıf, metin)] — sınıf renk hükmüdür (ok/warn/err/info/dim)."""
    return [(sinif, re.sub(r'\s+', ' ', metin).strip())
            for sinif, metin in ROZET_RE.findall(html)]


def _kalite_rozetleri(html):
    """(bozulma, uzama) rozetleri.

    Ayırt edici damga panelin KENDİ İngilizce yedek metnidir: bozulma
    rozeti ölçekli Jacobian'ı, uzama rozeti en-boy oranını adlandırır.
    Damga metni değişirse bekçi kırılır — ayrışmanın adı sözleşmedir.
    """
    bozulma = uzama = None
    for sinif, metin in _rozetler(html):
        if 'Jacobian' in metin:
            bozulma = (sinif, metin)
        elif 'aspect ratio' in metin:
            uzama = (sinif, metin)
    return bozulma, uzama


ALARM_SINIFLARI = ('warn', 'err')


def _yuzde4(oran):
    """Oransal değişim → panelin bastığı yüzde metni (4 anlamlı basamak).

    Panel ``Number(x.toPrecision(4))`` kullanır; sunucunun beyan metnindeki
    ``'%.4g'`` kuralının aynısıdır (planar_grain._yuzde). Beklenen değer
    testte ELLE yazılmaz, yanıttan türetilir. (Çok küçük değerlerde JS ile
    Python'ın üstel gösterime geçme eşiği farklıdır; buradaki yükler
    %1e-4'ün üstünde kalır.)
    """
    return '%g%%' % float('%.4g' % (100.0 * oran))


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


@pytest.fixture(scope='module')
def grain_fea(client):
    """GERÇEK düzlemsel tane koşusunun uç yanıtı (fea bloğu)."""
    kod, govde = grain_uc_kos(client)
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
# 3b. Kalite ROZETİ ayrışması — alarm yalnız bozulmadan
# ---------------------------------------------------------------------------
@needs_node
class TestKaliteRozetiAyrismasi:
    """Alarm rozetinin SÜRÜCÜSÜ ölçekli Jacobian sayımıdır.

    Buradaki bekçilerin ikisi negatiftir (kusuru kilitleme koruması): uzama
    sayımı ne kadar büyürse büyüsün alarm sınıfı üretemez; ölçülmemiş ölçüt
    de yeşil hüküm üretemez.
    """

    def _rozet_html(self, sonuc):
        return sonuc['els']['fea_badges']['html']

    def test_bozulma_rozeti_jacobian_sayimini_basar(self, fea, tmp_path):
        sonuc = _run_panel(fea, tmp_path)
        bozulma, _ = _kalite_rozetleri(self._rozet_html(sonuc))
        assert bozulma is not None, 'bozulma rozeti basılmamış'
        sayim = fea['quality']['counts']
        assert '%d/%d' % (sayim['scaled_jacobian_flagged'],
                          sayim['n_elems']) in bozulma[1]
        # Sunucu bu koşuda sıfır bozulma raporluyor → hüküm alarm DEĞİL.
        assert sayim['scaled_jacobian_flagged'] == 0, (
            'ölçüm değişmiş: bu bekçi sıfır bozulmalı bir koşu bekliyor')
        assert bozulma[0] == 'ok', (
            'bozulma yokken alarm sınıfı basılıyor: %r' % (bozulma,))

    def test_uzama_sayimi_alarm_sinifi_suremez(self, fea, tmp_path):
        """KUSURU KİLİTLEYEN BEKÇİ — asıl kapatılan hata budur.

        Ölçülen üründe her eleman en-boy oranı eşiğini aşıyordu ve panel
        bunu alarmla basıyordu. Uzama BÜYÜTÜLÜR (hepsi bayraklı), bozulma
        temiz bırakılır: hiçbir kalite rozeti alarm sınıfı almamalıdır.
        """
        bozuk = copy.deepcopy(fea)
        q = bozuk['quality']
        n = len(q['aspect_ratio'])
        q['aspect_ratio'] = [q['thresholds']['aspect_ratio_max'] * 25.0] * n
        q['scaled_jacobian'] = [1.0] * n
        sonuc = _run_panel(bozuk, tmp_path)
        bozulma, uzama = _kalite_rozetleri(self._rozet_html(sonuc))
        assert uzama is not None, 'uzama rozeti hiç basılmamış'
        assert '%d/%d' % (n, n) in uzama[1], 'uzama sayımı gizlenmiş'
        assert uzama[0] not in ALARM_SINIFLARI, (
            'uzama sayımı alarm sınıfı sürüyor: %r' % (uzama,))
        assert bozulma[0] == 'ok' and '0/%d' % n in bozulma[1]

    def test_bozulma_varsa_alarm_sinifina_gecer(self, fea, tmp_path):
        """Karşı yön: tek eleman bozulursa hüküm turuncuya döner."""
        bozuk = copy.deepcopy(fea)
        q = bozuk['quality']
        n = len(q['scaled_jacobian'])
        q['aspect_ratio'] = [1.0] * n
        q['scaled_jacobian'] = [1.0] * n
        q['scaled_jacobian'][n // 3] = q['thresholds']['scaled_jacobian_min'] / 5.0
        sonuc = _run_panel(bozuk, tmp_path)
        bozulma, uzama = _kalite_rozetleri(self._rozet_html(sonuc))
        assert bozulma[0] == 'warn', (
            'gerçek bozulma alarm sınıfı üretmiyor: %r' % (bozulma,))
        assert '1/%d' % n in bozulma[1]
        # Uzama temizken de rozet basılır (sayı gizlenmez) ama nötr kalır.
        assert uzama is not None and uzama[0] not in ALARM_SINIFLARI

    def test_jacobian_yayimlanmamissa_yesil_hukum_yok(self, fea, tmp_path):
        """Ölçülmemiş ölçüt "temiz" DEĞİLDİR: sıfır bayrak yeşil basılmaz."""
        bozuk = copy.deepcopy(fea)
        bozuk['quality'].pop('scaled_jacobian')
        bozuk['quality']['thresholds'].pop('scaled_jacobian_min')
        sonuc = _run_panel(bozuk, tmp_path)
        bozulma, _ = _kalite_rozetleri(self._rozet_html(sonuc))
        assert bozulma is not None
        assert bozulma[0] == 'dim', (
            'ölçülmemiş bozulma ölçütü hüküm rengi almış: %r' % (bozulma,))
        assert 'NOT PUBLISHED' in bozulma[1].upper()

    def test_esik_degeri_yanittan_basilir(self, fea, tmp_path):
        """Rozetteki eşik SUNUCUNUN sayısıdır (panelde sabit değil)."""
        bozuk = copy.deepcopy(fea)
        bozuk['quality']['thresholds']['aspect_ratio_max'] = 9.5
        bozuk['quality']['thresholds']['scaled_jacobian_min'] = 0.25
        sonuc = _run_panel(bozuk, tmp_path)
        bozulma, uzama = _kalite_rozetleri(self._rozet_html(sonuc))
        assert '9.5' in uzama[1], 'uzama eşiği yanıttan basılmıyor: %r' % (uzama,)
        assert '0.25' in bozulma[1], 'bozulma eşiği yanıttan basılmıyor'
        # Bayrak aritmetiği de yeni eşiğe uyar (sunucunun sayımı kopyalanmaz).
        yeni = sum(1 for v in bozuk['quality']['aspect_ratio'] if v > 9.5)
        assert '%d/%d' % (yeni, len(bozuk['quality']['aspect_ratio'])) in uzama[1]

    def test_birlesik_alarm_rozeti_kalkti(self, fea, tmp_path):
        """Eski "outside the acceptable range" rozeti geri gelmemeli."""
        sonuc = _run_panel(fea, tmp_path)
        for _, metin in _rozetler(self._rozet_html(sonuc)):
            assert 'outside the acceptable range' not in metin, (
                'birleşik kalite rozeti geri gelmiş: %r' % metin)
        assert 'badgeQuality' not in kaynak(), \
            'panel eski birleşik rozet anahtarını hâlâ taşıyor'

    def test_harita_ve_olcut_secici_yerinde(self, fea, tmp_path):
        """Ayrışma yalnız ROZETİ değiştirir: harita ve seçici duruyor."""
        sonuc = _run_panel(fea, tmp_path)
        assert _cagri(sonuc, 'fea_plot_quality') is not None
        src = kaynak()
        assert "id=\"fea_metric\"" in src and 'setQualityMetric' in src
        # Not satırı ayrışmayı da yazar (birleşik sayı tek başına kalmaz).
        not_html = sonuc['els']['fea_quality_note']['html']
        sayim = fea['quality']['counts']
        assert str(sayim['aspect_ratio_flagged']) in not_html
        assert 'distortion' in not_html


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


# ---------------------------------------------------------------------------
# 6. TANE KESİTİ paneli (GrainFeaPanel) — aynı ayrışma + kabul ölçütü çipi
# ---------------------------------------------------------------------------
@needs_node
class TestTaneKaliteRozeti:
    """Tane panelinde de alarm YALNIZ bozulmadan gelir.

    Ölçülen üründe tane rozeti "6144/6144 outside the acceptable range"
    basıyordu; aynı yanıtta ölçekli Jacobian TAM 1,0 idi (sıfır bozulma).
    """

    def _rozet_html(self, sonuc):
        return sonuc['els']['grainfea_badges']['html']

    def test_bozulma_rozeti_jacobian_sayimini_basar(self, grain_fea, tmp_path):
        sonuc = _run_grain_panel(grain_fea, tmp_path)
        bozulma, uzama = _kalite_rozetleri(self._rozet_html(sonuc))
        sayim = grain_fea['quality']['counts']
        assert bozulma is not None and uzama is not None
        assert '%d/%d' % (sayim['scaled_jacobian_flagged'],
                          sayim['n_elems']) in bozulma[1]
        assert '%d/%d' % (sayim['aspect_ratio_flagged'],
                          sayim['n_elems']) in uzama[1]
        assert sayim['scaled_jacobian_flagged'] == 0, (
            'ölçüm değişmiş: bu bekçi sıfır bozulmalı bir kesit bekliyor')
        assert bozulma[0] == 'ok'

    def test_uzama_sayimi_alarm_sinifi_suremez(self, grain_fea, tmp_path):
        """KUSURU KİLİTLEYEN BEKÇİ (tane) — hepsi uzamış, bozulma temiz."""
        bozuk = copy.deepcopy(grain_fea)
        q = bozuk['quality']
        n = len(q['aspect_ratio'])
        q['aspect_ratio'] = [q['thresholds']['aspect_ratio_max'] * 25.0] * n
        q['scaled_jacobian'] = [1.0] * n
        sonuc = _run_grain_panel(bozuk, tmp_path)
        bozulma, uzama = _kalite_rozetleri(self._rozet_html(sonuc))
        assert '%d/%d' % (n, n) in uzama[1]
        assert uzama[0] not in ALARM_SINIFLARI, (
            'tane panelinde uzama alarm sürüyor: %r' % (uzama,))
        assert bozulma[0] == 'ok'

    def test_bozulma_varsa_alarm_sinifina_gecer(self, grain_fea, tmp_path):
        bozuk = copy.deepcopy(grain_fea)
        q = bozuk['quality']
        n = len(q['scaled_jacobian'])
        q['scaled_jacobian'] = [1.0] * n
        q['scaled_jacobian'][7] = q['thresholds']['scaled_jacobian_min'] / 4.0
        sonuc = _run_grain_panel(bozuk, tmp_path)
        bozulma, _ = _kalite_rozetleri(self._rozet_html(sonuc))
        assert bozulma[0] == 'warn' and '1/%d' % n in bozulma[1]

    def test_jacobian_yayimlanmamissa_yesil_hukum_yok(self, grain_fea, tmp_path):
        bozuk = copy.deepcopy(grain_fea)
        bozuk['quality'].pop('scaled_jacobian')
        sonuc = _run_grain_panel(bozuk, tmp_path)
        bozulma, _ = _kalite_rozetleri(self._rozet_html(sonuc))
        assert bozulma[0] == 'dim' and 'NOT PUBLISHED' in bozulma[1].upper()

    def test_birlesik_alarm_rozeti_kalkti(self, grain_fea, tmp_path):
        sonuc = _run_grain_panel(grain_fea, tmp_path)
        for _, metin in _rozetler(self._rozet_html(sonuc)):
            assert 'outside the acceptable range' not in metin, (
                'tane panelinde birleşik rozet geri gelmiş: %r' % metin)


@needs_node
class TestTaneKabulCipi:
    """Yakınsama HÜKMÜ kabul ölçütünündür (port gerinimi), vM'nin değil.

    Sunucu sözleşmesi (isteğe bağlı blok):
        convergence.acceptance = {quantity, rel_change, converged, tol}
    Blok yoksa panel bugünkü davranışını sürdürmelidir — sunucu tarafı bu
    bekçiden önce ya da sonra girebilir, iki sırada da kırılma olmamalı.
    """

    def _rozet_html(self, sonuc):
        return sonuc['els']['grainfea_badges']['html']

    def _cip(self, html, damga):
        for sinif, metin in _rozetler(html):
            if damga in metin:
                return (sinif, metin)
        return None

    def _kabul_ekle(self, fea, **alanlar):
        yeni = copy.deepcopy(fea)
        blok = {'quantity': 'max_bore_strain', 'rel_change': 0.0031,
                'converged': True, 'tol': 0.01}
        blok.update(alanlar)
        yeni['convergence']['acceptance'] = blok
        return yeni

    def test_acceptance_yoksa_geriye_uyum(self, grain_fea, tmp_path):
        """Kabul bloğu YOKKEN davranış birebir eski olmalı.

        Sunucu tarafı bu panelden bağımsız ilerliyor: blok bugün geldi,
        yarın adı değişebilir. Blok çıkarılmış yükte panel eski yakınsama
        rozetine düşer — düşmezse tane paneli eski sunucularda hükümsüz
        kalırdı.
        """
        yuk = copy.deepcopy(grain_fea)
        yuk['convergence'].pop('acceptance', None)
        sonuc = _run_grain_panel(yuk, tmp_path)
        html = self._rozet_html(sonuc)
        conv = yuk['convergence']
        beklenen = 'CONVERGED in' if conv['converged'] else 'NOT CONVERGED after'
        cip = self._cip(html, beklenen)
        assert cip is not None, 'eski yakınsama rozeti kaybolmuş'
        assert cip[0] == ('ok' if conv['converged'] else 'warn')
        assert self._cip(html, 'ACCEPTANCE METRIC') is None, \
            'kabul bloğu yokken kabul çipi uyduruluyor'

    def test_canli_yanitta_hukum_kabulden_gelir(self, grain_fea, tmp_path):
        """UÇTAN UCA: sunucunun KENDİ yayımladığı blokla hüküm ayrışması.

        Ölçülen (bates varsayılanı): kabul ölçütü (port lif gerinimi)
        yakınsamış, tepe von Mises HÂLÂ inceliyor. Panel bu koşuda yeşil
        hüküm + nötr vM basmalı; eski davranışta tek turuncu rozet vardı.
        """
        conv = grain_fea['convergence']
        acc = conv.get('acceptance')
        if not acc:
            pytest.skip('sunucu kabul bloğu yayımlamıyor')
        sonuc = _run_grain_panel(grain_fea, tmp_path)
        html = self._rozet_html(sonuc)
        kabul = self._cip(html, 'ACCEPTANCE METRIC')
        assert kabul is not None, 'kabul çipi basılmamış'
        assert kabul[0] == ('ok' if acc['converged'] else 'warn')
        assert acc['quantity'] == 'max_bore_strain'
        assert 'bore strain' in kabul[1], 'kabul büyüklüğü adlandırılmamış'
        # Değişim yüzdesi EZİLMEDEN basılır (4 anlamlı basamak; sabit iki
        # basamak %0,003'ü "%0,00" yapıp yayımlanmış değişimi sıfırlardı).
        assert _yuzde4(acc['rel_change']) in kabul[1], (
            'kabul değişimi yanıttan basılmıyor: %r' % (kabul,))
        vm_cip = self._cip(html, 'PEAK vM')
        assert vm_cip is not None and vm_cip[0] not in ALARM_SINIFLARI
        assert _yuzde4(conv['final_rel_change']) in vm_cip[1]
        if acc['converged'] and not conv['converged']:
            assert 'still refining' in vm_cip[1]

    def test_hukum_kabul_olcutunden_gelir(self, grain_fea, tmp_path):
        """Kabul yakınsadı, vM yakınsamadı → HÜKÜM YEŞİL, vM nötr."""
        yeni = self._kabul_ekle(grain_fea, converged=True, rel_change=0.0031)
        assert grain_fea['convergence']['converged'] is False, (
            'ayrışmayı gösteren koşu değişmiş (vM yakınsamamış olmalı)')
        sonuc = _run_grain_panel(yeni, tmp_path)
        html = self._rozet_html(sonuc)
        kabul = self._cip(html, 'ACCEPTANCE METRIC')
        assert kabul is not None, 'kabul çipi basılmamış'
        assert kabul[0] == 'ok', 'kabul yakınsadığı hâlde yeşil değil: %r' % (kabul,)
        assert 'bore strain' in kabul[1], 'kabul büyüklüğü adlandırılmamış'
        assert '0.31%' in kabul[1], 'kabul değişimi yanıttan basılmıyor'
        assert 'tolerance 1%' in kabul[1], 'kabul toleransı yanıttan basılmıyor'
        # vM AYRI çiptir ve alarm DEĞİLDİR (kabul dayanağı o değil).
        vm_cip = self._cip(html, 'PEAK vM')
        assert vm_cip is not None, 'vM bilgi çipi basılmamış'
        assert vm_cip[0] not in ALARM_SINIFLARI, (
            'vM çipi alarm sınıfı sürüyor: %r' % (vm_cip,))
        assert 'not the acceptance basis' in vm_cip[1]
        assert _yuzde4(grain_fea['convergence']['final_rel_change']) in vm_cip[1]
        # Eski birleşik yakınsama rozeti kabul bloğu varken basılmaz.
        assert self._cip(html, 'CONVERGED in') is None

    def test_kabul_yakinsamadiysa_turuncu(self, grain_fea, tmp_path):
        yeni = self._kabul_ekle(grain_fea, converged=False, rel_change=0.087)
        sonuc = _run_grain_panel(yeni, tmp_path)
        kabul = self._cip(self._rozet_html(sonuc), 'ACCEPTANCE METRIC')
        assert kabul[0] == 'warn', 'kabul yakınsamadığı hâlde alarm yok'
        assert '8.7%' in kabul[1]

    def test_kucuk_degisim_sifira_ezilmez(self, grain_fea, tmp_path):
        """Kabul değişimi ~%0,003 mertebesinde ölçülüyor; iki basamak onu
        "%0,00" yapar ve gerçek bir değişimi yokmuş gibi gösterirdi."""
        yeni = self._kabul_ekle(grain_fea, converged=True,
                                rel_change=3.063191732228627e-05)
        sonuc = _run_grain_panel(yeni, tmp_path)
        kabul = self._cip(self._rozet_html(sonuc), 'ACCEPTANCE METRIC')
        assert '0.003063%' in kabul[1], (
            'küçük değişim basamak kaybına uğramış: %r' % (kabul,))
        assert '0.00%' not in kabul[1]

    def test_kabul_degisimi_null_ise_sayi_uydurulmaz(self, grain_fea, tmp_path):
        """rel_change null gelebilir (sözleşme) — sıfır yazılmaz."""
        yeni = self._kabul_ekle(grain_fea, converged=False, rel_change=None)
        sonuc = _run_grain_panel(yeni, tmp_path)
        kabul = self._cip(self._rozet_html(sonuc), 'ACCEPTANCE METRIC')
        assert kabul[0] == 'warn'
        assert 'not published' in kabul[1]
        assert '0.00%' not in kabul[1], 'yayımlanmamış değişim sıfır basılmış'

    def test_cidar_paneli_kabul_bloguna_bakmaz(self, fea, tmp_path):
        """Cidar panelinin çip mantığı DEĞİŞMEDİ: kabul bloğu enjekte
        edilse bile yakınsama rozeti eski cümledir."""
        yeni = copy.deepcopy(fea)
        yeni['convergence']['acceptance'] = {
            'quantity': 'max_bore_strain', 'rel_change': 0.5,
            'converged': False, 'tol': 0.01}
        sonuc = _run_panel(yeni, tmp_path)
        html = sonuc['els']['fea_badges']['html']
        assert 'ACCEPTANCE METRIC' not in html, \
            'cidar paneline kabul çipi sızmış'
        conv = fea['convergence']
        beklenen = 'CONVERGED in' if conv['converged'] else 'NOT CONVERGED after'
        assert beklenen in html
