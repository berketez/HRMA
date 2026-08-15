"""thermal_fea_panel.js bekçileri (D2 termal FEA panelinin kullanıcı yüzü).

KAPATILAN BOŞLUK
----------------
POST /api/fea/thermal ucu sağlamdı (tests/test_fea_termal_uc.py) ama HİÇBİR
kullanıcı yüzü onu çağırmıyordu — 2.7 kapı ölçütü #1 ("mesh üstünde sıcaklık
konturu EKRANDA") açıktı. Panel ölçülmüş zinciri koşturur:
/api/analysis/wall-profile → /api/fea/thermal. Buradaki bekçiler panelin
sözleşmesini kilitler:

  1. KONTUR VERİSİ ÇÖZÜCÜDEN BİREBİR — carpet ızgarası düğüm
     koordinatlarının kendisidir; sıcaklık değerleri ÖLÇEKSİZ çizilir
     (kelvin gelir, kelvin basılır — çarpan yoktur).
  2. İÇ YÜZEY T(z) ve TEPE T(t) GEÇMİŞİ dizilerin KENDİSİDİR.
  3. BİRİM DÖNÜŞÜMÜ ALANIN KAYNAĞINA GÖRE — wall-profile ucu METRE bekler;
     hibrit düz alanlar metre AYNEN geçer, motor_geometry SI bloğu düz mm
     alanını EZER. "Büyüklüğe bak, mm say" sezgiseli YASAKTIR ve buradaki
     sayısal eşitlikler her iki yöndeki (×1000 / ÷1000) mutasyonu yakalar.
  4. SAHTE VERİ YASAĞI — status != 'ok' → HİÇBİR grafik; eksik ADIYLA
     basılır. Çekirdek alan eksikse uç HİÇ çağrılmaz (sunucu varsayılanı
     başka motorun profili olurdu). Yeni motor sonucu eski alanı SİLER.
  5. MALZEME HÜKMÜ SUNUCUNUN — rozet rengi material_limits bayraklarından,
     değerler aynı bloktan; panel eşik uydurmaz.
  6. warnings[] kodları GrainFeaPanel deseniyle basılır (I18N yoksa kod
     AYNEN görünür, gizlenmez).

ÖLÇÜM YÖNTEMİ
-------------
Panel GERÇEK node ile, küçük bir DOM + Plotly taklidi altında BÜTÜN olarak
koşturulur (kalıp: tests/test_fea_panel.py). Çizilen veri GERÇEK zincirden
(/calculate → wall-profile → /api/fea/thermal) gelen uç yanıtıyla
karşılaştırılır — beklenen değerler elle yazılmaz, yanıttan türetilir.
Koşum hedeflidir: tests/test_fea_termal_uc.py ile birlikte çağrılır
(süit disiplini — tam süit koşturulmaz).
"""

import copy
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_fea_termal_uc import HIBRIT_GOVDE, _quiet, kos

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PANEL_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'thermal_fea_panel.js'
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def profil_govdesi(motor):
    """Ölçülmüş zincirin 1. adım gövdesi — panelin buildWallProfileBody
    çıktısının Python aynası. test_node_gövdesi_bu_aynayla_birebir bekçisi
    ikisini birbirine KİLİTLER: panel alan eklerse/çıkarırsa test düşer.
    (Hibrit düz uzunluk alanları METREDİR — analysis_dock LENGTH_UNITS,
    ölçülmüş; burada dönüşüm yoktur çünkü panel de yapmaz.)
    """
    return {
        'chamber_pressure': motor['chamber_pressure'],
        'chamber_temperature': motor['chamber_temperature'],
        'burn_time': motor['burn_time'],
        'mdot_total': motor['mdot_total'],
        'chamber_diameter': motor['chamber_diameter'],
        'chamber_length': motor['chamber_length'],
        'throat_diameter': motor['throat_diameter'],
        'expansion_ratio': motor['expansion_ratio'],
    }


# ---------------------------------------------------------------------------
# node koşum ortamı: küçük DOM + Plotly taklidi, panel dosyası bütün yüklenir
# (AnalysisDock YOK → panelin yedek uzunluk okuyucusu koşar; bekçi 3 tam
# olarak o yolu kilitler)
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
if (payload.showMesh === false) window.ThermalFeaPanel.setShowMesh(false);
plotlyCalls.length = 0;                       // kurulum çağrıları sayılmaz
if ('fea' in payload) {
    window.ThermalFeaPanel.applyPayload(payload.fea, payload.error || null);
}
if (payload.yeniMotorSonucu) {
    plotlyCalls.length = 0;                   // eski çizimler sayılmasın
    window.ThermalFeaPanel.update(payload.yeniMotorSonucu);
}
let bodies = null;
if (Array.isArray(payload.buildBody)) {
    bodies = payload.buildBody.map(
        m => window.ThermalFeaPanel._buildWallProfileBody(m));
}

const els = {};
Object.keys(nodes).forEach(id => {
    els[id] = { html: nodes[id].innerHTML,
                text: nodes[id].textContent,
                display: nodes[id].style.display,
                attrs: nodes[id].attrs };
});
process.stdout.write(JSON.stringify(
    { plotly: plotlyCalls, els: els, bodies: bodies }));
"""


def _run_panel(tmp_path, fea='YOK', error=None, show_mesh=None,
               yeni_motor_sonucu=None, build_body=None):
    """Paneli node'da koşturur; Plotly çağrıları + eleman görüntüleri döner."""
    script = tmp_path / 'kos.js'
    script.write_text(HARNESS, encoding='utf-8')
    girdi = {}
    if fea != 'YOK':
        girdi['fea'] = fea
        girdi['error'] = error
    if yeni_motor_sonucu is not None:
        girdi['yeniMotorSonucu'] = yeni_motor_sonucu
    if show_mesh is not None:
        girdi['showMesh'] = show_mesh
    if build_body is not None:
        girdi['buildBody'] = build_body
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
def motor(client):
    """GERÇEK /calculate hibrit sonucu (uç bekçileriyle aynı gövde)."""
    resp = _quiet(client.post, '/calculate', json=HIBRIT_GOVDE,
                  headers={'Host': '127.0.0.1:8080'})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()['motor']


@pytest.fixture(scope='module')
def profil(client, motor):
    """GERÇEK wall-profile çıktısı — gövde, panel zincirinin aynası."""
    resp = _quiet(client.post, '/api/analysis/wall-profile',
                  json=profil_govdesi(motor),
                  headers={'Host': '127.0.0.1:8080'})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    wp = resp.get_json()['wall_profile']
    assert isinstance(wp['x_mm'], list) and len(wp['x_mm']) >= 2
    return wp


@pytest.fixture(scope='module')
def fea(client, motor, profil):
    """GERÇEK termal FEA yanıtı (fea bloğu) — panelin çizeceği verinin ta
    kendisi. Küçük koşu parametreleri kos() içinden (TERMAL_KUCUK_KOSU)."""
    kod, govde = kos(client, motor=motor, axial_profile=profil,
                     ambient_temperature_K=293.15)
    assert kod == 200 and govde['status'] == 'ok', govde
    return govde


@pytest.fixture(scope='module')
def fea_eksik(client, motor):
    """Profil verilmemiş GERÇEK red yanıtı (dürüstlük sözleşmesi)."""
    kod, govde = kos(client, motor=motor, ambient_temperature_K=293.15)
    assert kod == 200 and govde['status'] == 'NOT_MODELLED', govde
    return govde


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
    assert '/static/js/thermal_fea_panel.js' in html, \
        'panel dosyası sayfaya bağlanmamış'
    assert 'ThermalFeaPanel.init(' in html, 'panel kurulmuyor (init çağrısı yok)'
    # Panel #feaPanel'in HEMEN ALTINA yerleşir — çapa yapısal paneldir.
    assert "anchorId: 'feaPanel'" in html, \
        'panel yapısal FEA paneline çapalanmamış'
    assert "hookName: 'displayCalculationResults'" in html, \
        'bayat-temizleme kancası sayfanın gerçek sonuç basıcısına bağlanmamış'


def test_kaynak_sozlesmeleri():
    """Uç yolları, ambient alanı, kanca ve dürüstlük izleri kaynakta."""
    src = kaynak()
    # Ölçülmüş zincirin iki ucu — panel BAŞKA uç çağırmaz.
    assert "'/api/analysis/wall-profile'" in src
    assert "'/api/fea/thermal'" in src
    # Ambient alanı: 293,15 K ön-dolu, düzenlenebilir; gövdeye
    # ambient_temperature_K adıyla gider.
    assert 'fea_t_ambient' in src
    assert '293.15' in src
    assert 'ambient_temperature_K' in src
    # Bayat-temizleme kancası sayfanın gerçek sonuç basıcısını sarar.
    assert 'displayCalculationResults' in src
    # outer_ambient GÖNDERİLMEZ (yorumda anılabilir ama gövde anahtarı
    # olarak KURULAMAZ): uç adyabatik dış yüzeyi kendisi beyan eder,
    # panel o beyanı (dis_yuzey) basar.
    assert re.search(r'outer_ambient\s*[:=]', src) is None, \
        'panel outer_ambient gövde anahtarı kuruyor — adyabatik sözleşme bozulmuş'
    assert 'dis_yuzey' in src
    # warn-kod işleme yolu (GrainFeaPanel deseni: I18N.tf(code, params)).
    assert 'I18N.tf' in src


def test_sahte_ilerleme_gostergesi_yok():
    src = kaynak().lower()
    assert 'progress' not in src, 'panelde ilerleme çubuğu izi var'
    assert 'data-indeterminate' in kaynak(), \
        'belirsiz süreli koşu için belirsiz gösterge yok'


# ---------------------------------------------------------------------------
# 1. Çizilen veri çözücüden BİREBİR (gerçek zincir yanıtıyla)
# ---------------------------------------------------------------------------
@needs_node
class TestCizimSadakati:

    def test_kontur_izgarasi_dugum_koordinatlarinin_kendisi(self, fea, tmp_path):
        sonuc = _run_panel(tmp_path, fea=fea)
        cagri = _cagri(sonuc, 'fea_t_plot_field')
        assert cagri is not None, 'sıcaklık konturu çizilmemiş'
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

    def test_kontur_degerleri_alanin_kendisi_olceksiz(self, fea, tmp_path):
        """Kelvin gelir, kelvin çizilir — çarpan/bölen YOKTUR."""
        sonuc = _run_panel(tmp_path, fea=fea)
        cc = _iz(_cagri(sonuc, 'fea_t_plot_field'), 'contourcarpet')
        assert len(cc) == 1
        g = fea['mesh']['node_index_grid']
        alan = fea['fields']['temperature_final_K']
        for j in range(len(g[0])):
            for i in range(len(g)):
                assert cc[0]['z'][j][i] == alan[g[i][j]]

    def test_ic_yuzey_grafigi_dizilerin_kendisi(self, fea, tmp_path):
        sonuc = _run_panel(tmp_path, fea=fea)
        cagri = _cagri(sonuc, 'fea_t_plot_inner')
        assert cagri is not None, 'iç yüzey T(z) grafiği çizilmemiş'
        iz = cagri['traces'][0]
        assert iz['x'] == fea['fields']['inner_surface_z_m']
        assert iz['y'] == fea['fields']['inner_surface_T_final_K']

    def test_gecmis_grafigi_dizilerin_kendisi(self, fea, tmp_path):
        sonuc = _run_panel(tmp_path, fea=fea)
        cagri = _cagri(sonuc, 'fea_t_plot_hist')
        assert cagri is not None, 'tepe cidar T(t) grafiği çizilmemiş'
        iz = cagri['traces'][0]
        assert iz['x'] == fea['history']['times_s']
        assert iz['y'] == fea['history']['peak_wall_T_history_K']

    def test_sinir_cizgileri_sunucu_degerleriyle(self, fea, tmp_path):
        """Referans çizgi değerleri material_limits'ten gelir; panel eşik
        uydurmaz (değer yayımlanmadıysa çizgi de yoktur)."""
        sonuc = _run_panel(tmp_path, fea=fea)
        layout = _cagri(sonuc, 'fea_t_plot_inner')['layout']
        y0lar = [s['y0'] for s in layout.get('shapes', [])]
        ml = fea['material_limits']
        for anahtar in ('allowable_temperature_K', 'melting_point_K'):
            deger = ml.get(anahtar)
            if isinstance(deger, (int, float)):
                assert deger in y0lar, f'{anahtar} çizgisi yok'
        assert len(y0lar) == sum(
            1 for k in ('allowable_temperature_K', 'melting_point_K')
            if isinstance(ml.get(k), (int, float)))

    def test_tel_kafes_meta_ile_tutarli_ve_kapatilabilir(self, fea, tmp_path):
        sonuc = _run_panel(tmp_path, fea=fea)
        cagri = _cagri(sonuc, 'fea_t_plot_field')
        wire = None
        for t in cagri['traces']:
            if t.get('mode') == 'lines' and t.get('hoverinfo') == 'skip':
                wire = t
        assert wire is not None, 'tel-kafes katmanı çizilmemiş'
        dolu = [v for v in wire['x'] if v is not None]
        # Her düğüm bir i-çizgisinde, bir j-çizgisinde geçer.
        assert len(dolu) == 2 * fea['mesh']['n_nodes']
        kapali = _run_panel(tmp_path, fea=fea, show_mesh=False)
        for t in _cagri(kapali, 'fea_t_plot_field')['traces']:
            assert not (t.get('mode') == 'lines'
                        and t.get('hoverinfo') == 'skip'), \
                'katman kapatıldığı hâlde tel-kafes çizildi'

    def test_rozetler_ve_malzeme_hukmu_sunucudan(self, fea, tmp_path):
        sonuc = _run_panel(tmp_path, fea=fea)
        badges = sonuc['els']['fea_t_badges']['html']
        assert str(fea['mesh']['n_elems']) in badges
        assert str(fea['mesh']['n_nodes']) in badges
        assert f"{fea['scalars']['peak_wall_T_K']:.0f}" in badges
        ml = fea['material_limits']
        if ml.get('exceeds_melting'):
            assert 'data-badge="err"' in badges, \
                'erime aşımı kırmızı rozet üretmedi'
            assert f"{ml['melting_point_K']:.0f}" in badges
        elif ml.get('exceeds_allowable'):
            assert 'data-badge="warn"' in badges, \
                'izin aşımı turuncu rozet üretmedi'
            assert f"{ml['allowable_temperature_K']:.0f}" in badges
        elif ml.get('exceeds_allowable') is False:
            assert 'data-badge="ok"' in badges

    def test_uyari_kodlari_gizlenmiyor(self, fea, tmp_path):
        """warnings[] kayıtları basılır; I18N yokken kod AYNEN görünür."""
        sonuc = _run_panel(tmp_path, fea=fea)
        uyari_html = sonuc['els']['fea_t_warnings']['html']
        if fea['warnings']:
            for w in fea['warnings']:
                assert w['code'] in uyari_html, f"{w['code']} basılmamış"
        else:
            assert uyari_html == ''

    def test_adyabatik_dis_yuzey_beyani_basiliyor(self, fea, tmp_path):
        """outer_ambient istenmez; ucun kendi beyanı panelde görünür."""
        sonuc = _run_panel(tmp_path, fea=fea)
        beyan = fea['meta']['sinir_kosullari_koprusu']['dis_yuzey']
        assert beyan[:30] in sonuc['els']['fea_t_bc_note']['html']


# ---------------------------------------------------------------------------
# 2. Sahte veri yasağı
# ---------------------------------------------------------------------------
@needs_node
class TestSahteVeriYasagi:

    def test_not_modelled_hicbir_cizim_yok(self, fea_eksik, tmp_path):
        sonuc = _run_panel(tmp_path, fea=fea_eksik)
        assert sonuc['plotly'] == [], 'redli sonuçta grafik çizilmiş'
        cip = sonuc['els']['fea_t_chip']['html']
        assert 'not-modelled' in cip
        for eksik in fea_eksik['missing']:
            assert str(eksik).split(' ')[0] in cip, \
                f'eksik girdi adlandırılmamış: {eksik}'

    def test_izgara_tutarsizsa_hicbir_sey_cizilmez(self, fea, tmp_path):
        bozuk = copy.deepcopy(fea)
        bozuk['mesh']['n_nodes'] = bozuk['mesh']['n_nodes'] + 7
        sonuc = _run_panel(tmp_path, fea=bozuk)
        assert sonuc['plotly'] == []
        assert 'not-modelled' in sonuc['els']['fea_t_chip']['html']

    def test_sunucu_hatasi_cizim_yerine_gerekce(self, tmp_path):
        sonuc = _run_panel(tmp_path, fea=None, error='solver exploded')
        assert sonuc['plotly'] == []
        assert 'solver exploded' in sonuc['els']['fea_t_chip']['html']

    def test_yeni_motor_sonucu_eski_alani_siler(self, fea, tmp_path):
        """Bayat sıcaklık alanı yeni motorunmuş gibi ekranda kalmaz."""
        sonuc = _run_panel(tmp_path, fea=fea,
                           yeni_motor_sonucu={'motor': {'thrust': 5000.0}})
        assert sonuc['plotly'] == [], 'yeni hesaptan sonra eski alan çiziliyor'
        assert sonuc['els']['fea_t_plot_field']['display'] == 'none'
        assert 'not-modelled' in sonuc['els']['fea_t_chip']['html']


# ---------------------------------------------------------------------------
# 3. Birim dönüşümü bekçisi — mm→m mantığı YANLIŞ YÖNE çevrilemez
# ---------------------------------------------------------------------------
@needs_node
class TestBirimDonusumu:

    def test_metre_alanlar_aynen_gecer(self, tmp_path):
        """Hibrit düz alanlar METREDİR (ölçülmüş zincirin sayıları):
        ne ×1000 ne ÷1000 — birebir eşitlik iki yönlü mutasyonu da yakalar."""
        hibrit = {'motor': {
            'chamber_pressure': 20.0, 'chamber_temperature': 3345.4,
            'burn_time': 10.0, 'mdot_total': 0.4472,
            'chamber_diameter': 0.0800, 'chamber_length': 0.5696,
            'throat_diameter': 0.02157, 'expansion_ratio': 3.866,
        }}
        sonuc = _run_panel(tmp_path, build_body=[hibrit])
        b = sonuc['bodies'][0]
        assert b['missing'] == []
        assert b['body']['throat_diameter'] == 0.02157
        assert b['body']['chamber_diameter'] == 0.0800
        assert b['body']['chamber_length'] == 0.5696
        assert b['body']['chamber_pressure'] == 20.0
        assert b['body']['expansion_ratio'] == 3.866

    def test_motor_geometry_si_blogu_mm_duz_alani_ezer(self, tmp_path):
        """thermal_panel.js'te ölçülen tuzağın kilidi: katı tarz sözlük düz
        alanda 17,96 (mm) taşır; SI beyanlı motor_geometry bloğu varsa O
        okunur — 17,96 METRE sanılmaz, büyüklük sezgiseli yoktur."""
        mmli = {
            'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
            'burn_time': 8.0, 'mdot_total': 1.2,
            'chamber_diameter': 80.0, 'chamber_length': 569.6,
            'throat_diameter': 17.96, 'expansion_ratio': 4.0,
            'motor_geometry': {
                'chamber_diameter': 0.0800, 'chamber_length': 0.5696,
                'throat_diameter': 0.01796,
            },
        }
        sonuc = _run_panel(tmp_path, build_body=[mmli])
        b = sonuc['bodies'][0]
        assert b['missing'] == []
        assert b['body']['throat_diameter'] == 0.01796
        assert b['body']['chamber_diameter'] == 0.0800
        assert b['body']['chamber_length'] == 0.5696

    def test_eksik_cekirdek_alan_adiyla_reddediliyor(self, tmp_path):
        """Çekirdek alan yoksa istek gövdesi kurulmaz: wall-profile ucunun
        sunucu varsayılanı (3000 K, 20 bar...) BAŞKA motorun profilidir."""
        eksikli = {'motor': {
            'chamber_pressure': 20.0,           # chamber_temperature YOK
            'burn_time': 10.0, 'mdot_total': 0.4472,
            'chamber_diameter': 0.0800, 'chamber_length': 0.5696,
        }}
        sonuc = _run_panel(tmp_path, build_body=[eksikli])
        b = sonuc['bodies'][0]
        assert 'chamber_temperature' in b['missing']

    def test_gercek_motorla_govde_ayna_ile_birebir(self, motor, tmp_path):
        """Panelin node'da kurduğu gövde, uca giden Python aynasıyla
        (profil_govdesi) alan alan AYNI — zincir sadakati kilidi."""
        sonuc = _run_panel(tmp_path, build_body=[motor])
        b = sonuc['bodies'][0]
        assert b['missing'] == []
        ayna = profil_govdesi(motor)
        assert set(b['body']) == set(ayna)
        for k, v in ayna.items():
            assert b['body'][k] == pytest.approx(v), k
