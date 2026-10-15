# -*- coding: utf-8 -*-
"""ÖH Dalga-28 / kulvar arayuz, aşama 1 — OH-D27-16 bekçileri.

KALEM: D26'nın uca eklediği DOKUZ dürüstlük/künye alanı panellerde
basılmıyordu. Kullanıcı hükmü görüyor, hükmün dayanağını göremiyordu.

    cfd_panel.js          time_integrator_basis, time_integrator,
                          convergence_history
    thermal_fea_panel.js  column_basis (6 çocuk), units (14 sütun)
    feed_panel.js         expulsion_efficiency, swept_volume_m3
    safety_panel.js       addBlastRow x {basis, scaled_distance_m_per_kg13}

ÖLÇÜM: ``docs/scofield/raw/OH/D28/arayuz/a1/olcum.py``
       once.json (taban 7cd08bcc): 9 kör  ->  sonra.json: 0 kör.

Bu dosyanın bekçileri ÜÇ KATMANLIDIR:

  1. OKUMA — panel alanı gerçekten okuyor mu (borç envanterlerinin
     ölçtüğü mekanizmanın AYNISI: ``x.alan`` + ``x['alan']``, i18n
     anahtarları düşülmüş).
  2. ÇİZİM YOLU — okuma ölü bir görünüm-modeli alanında kalmıyor,
     HTML üreten gövdeye bağlı (fonksiyon gövdesi düzeyinde).
  3. EKRAN — gerçek uç yanıtıyla, node ikizinde çizilen ekranda sayı ve
     künye GÖRÜNÜYOR (cfd ve safety için canlı koşum).

Ayrıca ÖDENEN BORÇ SATIRLARININ GERİ GELMEMESİ sınanır: dokuz adın
hiçbiri bir borç/muafiyet envanterinde yeniden af listesine yazılamaz.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import test_cfd_panel as CFDH            # noqa: E402  (node ikizi + harness)
import test_d15_ui_paneller_a1 as D15    # noqa: E402  (güvenlik ekran ikizi)
import test_wave4b_contract as W4B       # noqa: E402  (borç envanterleri)

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'

#: (panel dosyası, alan adı) — ödenen dokuz borcun sekizi statik ölçülür;
#: dokuzuncusu (safety) fonksiyon gövdesi düzeyinde ayrıca sınanır.
OKUMA_BORCU = [
    ('panels/cfd_panel.js', 'time_integrator_basis'),
    ('panels/cfd_panel.js', 'time_integrator'),
    ('panels/cfd_panel.js', 'convergence_history'),
    ('thermal_fea_panel.js', 'column_basis'),
    ('thermal_fea_panel.js', 'units'),
    ('panels/feed_panel.js', 'expulsion_efficiency'),
    ('panels/feed_panel.js', 'swept_volume_m3'),
]

#: Dokuz adın tamamı — af listesine geri yazılamaz.
ODENEN_ADLAR = frozenset({
    'time_integrator_basis', 'time_integrator', 'convergence_history',
    'column_basis', 'units', 'expulsion_efficiency', 'swept_volume_m3',
    'basis', 'scaled_distance_m_per_kg13',
})


def _kaynak(rel):
    return (STATIC_JS / rel).read_text(encoding='utf-8')


def _govde(metin, bas, son=None):
    """Bir fonksiyonun kaynak gövdesi (ad düzeyi ölçüm için)."""
    i = metin.index(bas)
    if son is None:
        return metin[i:]
    return metin[i:metin.index(son, i)]


# ---------------------------------------------------------------------------
# 1. OKUMA — borç envanterinin ölçtüğü mekanizmanın AYNISI
# ---------------------------------------------------------------------------

class TestOHD2716Okuma:
    """Panel alanı OKUYOR mu? (ölçüm: a1/once.json -> a1/sonra.json)"""

    @pytest.mark.parametrize('rel,ad', OKUMA_BORCU,
                             ids=[f'{r}:{a}' for r, a in OKUMA_BORCU])
    def test_alan_panelin_okuma_envanterinde(self, rel, ad):
        envanter = W4B._okuma_envanteri(rel)
        assert ad in envanter, (
            f'{rel} ucun yayımladığı `{ad}` alanını HÂLÂ okumuyor — '
            'kullanıcı hükmü görüp dayanağını göremez '
            '(OH-D27-16, ölçüm a1/once.json)')

    def test_patlama_okuyucusu_kunyeyi_ve_olcekli_mesafeyi_aliyor(self):
        """``addBlastRow`` gövdesi — süpürmenin sayı çakışmasından bağımsız.

        Aynı iddia ``test_d15_ui_paneller_a1`` içinde de duruyor (orada
        xfail(strict) borç imiydi, bu aşamada söküldü). Burada ikinci kez
        durması kasıtlı: ödeme iki dosyadan da izlenebilir olmalı.
        """
        govde = _govde(_kaynak('panels/safety_panel.js'),
                       'function addBlastRow', 'function addQdRow')
        eksik = [ad for ad in ('basis', 'scaled_distance_m_per_kg13')
                 if ad not in govde]
        assert not eksik, (
            'patlama mesafesi okuyucusu şu künye alanlarını hiç okumuyor: '
            + repr(eksik))


# ---------------------------------------------------------------------------
# 2. ÇİZİM YOLU — okuma ölü bir vm alanında kalmıyor
# ---------------------------------------------------------------------------

class TestOHD2716CizimYolu:
    """Alan okundu diye ekrana iner sanılmasın: HTML üreten gövdeye bağlı."""

    def test_cfd_gecmis_bolumu_yakinsama_bolumunden_cagriliyor(self):
        m = _kaynak('panels/cfd_panel.js')
        conv = _govde(m, 'function convergenceHtml',
                      '// HÜKMÜN DAYANDIĞI SERİLER')
        assert 'convergenceHistoryHtml(vm)' in conv, (
            'seriler bölümü yakınsama bölümünden çağrılmıyor — okuma ölü')
        assert 'basisText(vm.timeIntegratorBasis)' in conv, (
            'zaman ilerletme künyesi ekrana basılmıyor')
        assert 'vm.timeIntegrator' in conv, (
            'zaman ilerletme şemasının ADI ekrana basılmıyor')
        gec = _govde(m, 'function convergenceHistoryHtml',
                     '\n    function ', )
        for ad in ('mass_flow_in', 'mass_flow_out', 'throat_mach'):
            assert ad in gec, f'seri {ad} çizilmiyor'
        assert 's._basis' in gec, 'serinin künyesi ekrana basılmıyor'
        assert 's.last' in gec, (
            'seyreltmenin gizleyebileceği son değer basılmıyor')

    def test_termal_kunye_bolumu_sutun_dayanagini_ve_birimi_basiyor(self):
        m = _kaynak('thermal_fea_panel.js')
        assert 'wp.column_basis' in m and 'wp.units' in m, (
            'sütun künyesi / birim bloğu uç yanıtından hiç alınmıyor')
        rb = _govde(m, 'function renderBasis', 'function hidePlots')
        assert 'lastColumnBasis' in rb and 'lastProfileUnits' in rb, (
            'künye bölümü blokları hiç okumuyor')
        assert "T('feaT.columnBasisTitle'" in rb, (
            'sütun künyesi başlığı i18n üzerinden basılmıyor')
        assert 'parts.push' in rb

    def test_besleme_paneli_bosaltma_varsayimini_basiyor(self):
        m = _kaynak('panels/feed_panel.js')
        exp = _govde(m, 'function expulsionHtml',
                     '// ---- Pressurant render')
        assert 'U.kvTable' in exp, 'değerler bir tabloya basılmıyor'
        # OKUMA yetmez: değer bir SATIRA ulaşmalı. (Ters-mutasyon M4
        # ölçtü: satır boşaltılıp okuma yerinde bırakıldığında envanter
        # bekçisi kör kalıyor — alan "okunuyor" ama ekrana ÇIKMIYOR.)
        satirlar = ' '.join(re.findall(r'rows\.push\(([\s\S]*?)\]\);',
                                       exp))
        for ad in ('p.expulsion_efficiency', 'p.swept_volume_m3'):
            assert ad in satirlar, (
                ad + ' bir tablo satırına yazılmıyor — okunup atılıyor')
        ren = _govde(m, 'function renderPressurant',
                     '// ---- Water hammer render')
        assert 'expulsionHtml(p)' in ren, (
            'boşaltma bloğu basınçlandırıcı çiziminden çağrılmıyor — ölü kod')


# ---------------------------------------------------------------------------
# 3. EKRAN — gerçek uç yanıtı, node ikizi
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def motor_hibrit_d28(istemci):
    r = istemci.post('/calculate', json=CFDH.HIBRIT_GOVDE,
                     headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def cfd_yaniti_d28(istemci, motor_hibrit_d28):
    m = motor_hibrit_d28['motor']
    q = m['nozzle_flow_quasi1d']['inputs']
    body = {
        'nozzle_contour': m['nozzle_contour'],
        'P0_Pa': q['P0_Pa'], 'T0_K': q['T0_K'], 'gamma': q['gamma'],
        'R_J_per_kgK': q['R_J_kgK'],
        'P_ambient_Pa': (m['nozzle_expansion_screen']['ambient_pressure_bar']
                         * 1e5),
    }
    # ÖH D28 a3 — OH-D23-12 rota çıkarımı mandalı: uç ADI LİTERAL yazılır
    # (`CFDH.UC` bir Attribute'tü ve tarayıcı çözemiyordu; tavan 39'u
    # aştırıyordu). Literal, kaynağıyla aynı kalsın diye assert'lenir.
    assert CFDH.UC == '/api/cfd/nozzle', CFDH.UC
    r = istemci.post('/api/cfd/nozzle', json=body)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def cfd_ekrani(tmp_path_factory, motor_hibrit_d28, cfd_yaniti_d28):
    tmp = tmp_path_factory.mktemp('d28_cfd')
    out = CFDH.kos_panel(tmp, motorType='hybrid', results=motor_hibrit_d28,
                         response=cfd_yaniti_d28,
                         select=['nozzle_flow', 'cfd'], runs=1)
    return CFDH.gorunum(out)


@node_gerekli
class TestOHD2716Ekran:
    """Sayı ve künye GERÇEKTEN çizilen HTML'de mi?"""

    def test_cfd_zaman_semasi_ve_kunyesi_ekranda(self, cfd_ekrani,
                                                 cfd_yaniti_d28):
        cfd = cfd_yaniti_d28['cfd']
        ad = cfd.get('time_integrator')
        kunye = cfd.get('time_integrator_basis')
        assert ad and kunye, (
            'ölçüm tabanı çürüdü: uç artık time_integrator / '
            'time_integrator_basis yayımlamıyor')
        duz = re.sub(r'<[^>]*>', ' ', cfd_ekrani)
        duz = duz.replace('&amp;', '&').replace('&#39;', "'")
        duz = re.sub(r'\s+', ' ', duz)
        assert str(ad) in duz, (
            'zaman ilerletme şemasının adı ekranda yok: ' + repr(ad))
        assert kunye[:60] in duz, (
            'zaman ilerletme künyesi ekranda yok (kullanıcı hükmü görüp '
            'şemasını göremez)')

    def test_cfd_hukum_serileri_ekranda(self, cfd_ekrani, cfd_yaniti_d28):
        ch = cfd_yaniti_d28['cfd'].get('convergence_history') or {}
        assert set(ch) >= {'mass_flow_in', 'mass_flow_out', 'throat_mach'}, (
            'ölçüm tabanı çürüdü: uç artık üç seriyi yayımlamıyor')
        duz = re.sub(r'<[^>]*>', ' ', cfd_ekrani)
        duz = re.sub(r'\s+', ' ', duz)
        for ad, seri in sorted(ch.items()):
            assert ad in duz, f'seri adı ekranda yok: {ad}'
            son = seri.get('last')
            assert isinstance(son, float), (
                f'ölçüm tabanı çürüdü: {ad}.last sayı değil')
            # Panelin yazdığı biçim: fmtAuto(...,4) — 1e4 üstü / 1e-2 altı
            # üstel, aradaki bant sabit ondalık. İkisi de aranır ki bekçi
            # biçimi TAHMİN etmesin.
            mutlak = abs(son)
            if mutlak != 0 and (mutlak >= 1e4 or mutlak < 1e-2):
                jeton = CFDH._js_ustel(son, 4)
            else:
                jeton = '%.4f' % son
            assert jeton in duz, (
                f'{ad} serisinin son değeri ({jeton}) ekranda yok — '
                'seyreltmenin gizlediği sayı kullanıcıya ulaşmıyor')

    def test_guvenlik_patlama_kunyesi_ve_z_ekranda(self, safety_yaniti_d28,
                                                   safety_ekrani_d28):
        blast = (safety_yaniti_d28['safety_analysis']['explosive_hazards']
                 ['blast_distances'])
        assert blast, 'ölçüm tabanı çürüdü: uç patlama mesafesi vermiyor'
        # BİRLEŞME UYARLAMASI (ana model, 9 Eyl 2026): D28 bekci-cevirisi a1
        # (OH-D27-17) ``_gorunur``ü ad+değer düzeyine çekti — imza artık
        # ``(yol, v, ekran)``; ekran ``_ekran_bolgeleri(render)``dır. Bu test
        # o ölçütle koşar: Z ve künye KENDİ satırında/künye satırında olmalı.
        ekran = D15._ekran_bolgeleri(safety_ekrani_d28)
        for ad, kayit in sorted(blast.items()):
            z = kayit.get('scaled_distance_m_per_kg13')
            assert isinstance(z, float), (
                f'ölçüm tabanı çürüdü: {ad} ölçekli mesafe vermiyor')
            yol = f'explosive_hazards.blast_distances.{ad}.scaled_distance_m_per_kg13'
            assert D15._gorunur(yol, z, ekran), (
                f'{ad}: Hopkinson-Cranz ölçekli mesafe ({z}) ekranda KENDİ '
                'satırında yok (ad+değer ölçütü, OH-D27-17)')
        ad0, kunye = sorted(blast.items(), key=lambda kv: str(kv[1].get('basis')))[0]
        assert D15._gorunur(f'explosive_hazards.blast_distances.{ad0}.basis',
                            kunye.get('basis'), ekran), (
            'patlama mesafesi modelinin künyesi ekranda yok — kullanıcı '
            'mesafeyi görüyor ama hangi bağıntıdan geldiğini göremiyor')


@pytest.fixture(scope='module')
def safety_yaniti_d28(istemci):
    r = istemci.post('/analyze_safety', json=D15.SAFETY_YUKU)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def safety_ekrani_d28(safety_yaniti_d28, tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    tmp = tmp_path_factory.mktemp('d28_safety')
    script = tmp / 'kos_dock_d28.js'
    script.write_text(D15.DOCK_HARNESS_JS, encoding='utf-8')
    girdi = tmp / 'girdi_safety_d28.json'
    girdi.write_text(json.dumps({
        'panelId': 'safety', 'body': safety_yaniti_d28,
        'panelFiles': ['hrma/static/js/panels/safety_panel.js']}),
        encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(REPO_ROOT), str(girdi)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('safety_panel node altında çöktü:\n'
                                  + proc.stderr[-3000:])
    ciz = json.loads(proc.stdout)
    assert not ciz.get('error'), 'render hatası: ' + str(ciz.get('error'))
    # D15 fixture'ıyla AYNI ölçüm düzeltmesi: kullanıcı `&amp;` değil `&`
    # görür (ÖH D28 / arayuz a1).
    import html as _html
    ciz['text'] = _html.unescape(ciz['text'])
    return ciz


# ---------------------------------------------------------------------------
# 4. ÖDENEN BORÇ GERİ GELMEZ
# ---------------------------------------------------------------------------

class TestOHD2716BorcGeriGelmez:
    """Ödenen dokuz ad bir af listesine yeniden yazılamaz."""

    def test_ters_panel_borcu_odenen_adi_tasimiyor(self):
        geri = sorted({ad for blok in W4B.TERS_PANEL_BORCU
                       for ad in W4B.TERS_PANEL_BORCU[blok]}
                      & ODENEN_ADLAR)
        assert not geri, (
            'OH-D27-16 ile ödenen alan yeniden KOZMETİK BORÇ listesine '
            'yazılmış: ' + repr(geri))

    def test_durustluk_borcu_odenen_adi_tasimiyor(self):
        envanter = W4B.TestTersYonBorcEnvanteri.DURUSTLUK_BORCU
        geri = sorted({ad for adlar in envanter.values() for ad in adlar}
                      & ODENEN_ADLAR)
        assert not geri, (
            'OH-D27-16 ile ödenen alan yeniden DÜRÜSTLÜK BORCU listesine '
            'yazılmış: ' + repr(geri))

    def test_guvenlik_yaprak_borcu_bosaldi(self):
        # BİRLEŞME UYARLAMASI (9 Eyl 2026): envanterin BOŞ olması değil,
        # OH-D27-16 ile ödenen PATLAMA yollarının geri gelmemesi ölçülür —
        # D28 bekci-cevirisi a1 (OH-D27-17) iki kap-geometrisi yaprağını
        # (pressure_safety.*_mm) adıyla envantere yazdı; o borç arayuz'un
        # ödediği borç değildir (D29 arayuz), 'boş' mandalı onu engellerdi.
        geri = sorted(k for k in D15.GUVENLIK_YAPRAK_BORCU
                      if k.startswith('explosive_hazards.blast_distances.'))
        assert not geri, (
            'güvenlik yaprak borcu PATLAMA yollarıyla yeniden doldu '
            '(OH-D27-16 ile sekizi de ödenmişti): ' + repr(geri))

    def test_ters_muafiyet_odenen_adi_affetmiyor(self):
        """Borç, muafiyete DÖNÜŞTÜRÜLEREK de kapatılamaz."""
        geri = []
        for blok, (_js, muafiyet) in sorted(W4B.TERS_MUAFIYET.items()):
            for ad in sorted(set(muafiyet) & ODENEN_ADLAR):
                geri.append(f'{blok}:{ad}')
        assert not geri, (
            'ödenen alan "panel bunu bilerek basmıyor" muafiyetine '
            'taşınmış: ' + repr(geri))


# --- besleme paneli: CANLI çizim (window.FeedPanel._renderPressurant) ------
#
# Panelin basınçlandırıcı çizimi güverte sekmesinden çağrılır; panel bu iş
# için zaten bir test kancası yayımlıyor (`window.FeedPanel`). Harness D15'in
# ``DOCK_HARNESS_JS``iyle AYNI sahte DOM'u kullanır, tek farkı kayıt yerine
# doğrudan saf çizimi çağırmasıdır.
FEED_HARNESS_JS = D15.DOCK_HARNESS_JS.replace(
    # feed_panel yüklenirken form kabuğunu kuruyor ve `closest` çağırıyor;
    # D15'in sahte düğümünde o yok (güvenlik paneli çağırmıyordu).
    """        querySelector: function () { return makeNode('q'); },""",
    """        querySelector: function () { return makeNode('q'); },
        closest: function () { return makeNode('closest'); },
        insertBefore: function (c) { this.children.push(c); return c; },
        removeChild: function () {},""").replace(
    """const spec = (window.AnalysisDock._registry || [])
    .filter(function (p) { return p.id === cfg.panelId; })[0];
if (!spec) {
    process.stdout.write(JSON.stringify({ error: 'panel kayıtlı değil' }));
} else {
    const root = makeNode('root');
    let err = null;
    try { spec.render(cfg.body, root); }
    catch (e) { err = String((e && e.stack) || e); }""",
    """const ciz = window.FeedPanel && window.FeedPanel._renderPressurant;
if (!ciz) {
    process.stdout.write(JSON.stringify({ error: 'FeedPanel kancası yok' }));
} else {
    const root = makeNode('root');
    let err = null;
    try { ciz(cfg.body, root); }
    catch (e) { err = String((e && e.stack) || e); }""")

#: Regüle basınçlandırma girdisi — ucun kendi sözleşmesi (wave4b ile aynı
#: aile). İddialar bu adlardan değil, ucun YANITINDAN kurulur.
PRESS_GIRDISI = dict(W4B.PRESS_REGULATED_INPUT)


@pytest.fixture(scope='module')
def press_yaniti_d28(istemci):
    r = istemci.post('/api/pressurant-sizing', json=PRESS_GIRDISI)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def press_ekrani_d28(press_yaniti_d28, tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    tmp = tmp_path_factory.mktemp('d28_feed')
    script = tmp / 'kos_feed_d28.js'
    script.write_text(FEED_HARNESS_JS, encoding='utf-8')
    girdi = tmp / 'girdi_feed_d28.json'
    girdi.write_text(json.dumps({
        'panelId': 'feed', 'body': press_yaniti_d28,
        'panelFiles': ['hrma/static/js/panels/feed_panel.js']}),
        encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(REPO_ROOT), str(girdi)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('feed_panel node altında çöktü:\n'
                                  + proc.stderr[-3000:])
    ciz = json.loads(proc.stdout)
    assert not ciz.get('error'), 'render hatası: ' + str(ciz.get('error'))
    return ciz


@node_gerekli
def test_bosaltma_varsayimi_ekranda(press_yaniti_d28, press_ekrani_d28):
    """Gaz kütlesini ölçekleyen η ve süpürülen hacim GERÇEK ekranda mı?"""
    p = press_yaniti_d28['pressurant']
    eta = p.get('expulsion_efficiency')
    hacim = p.get('swept_volume_m3')
    assert isinstance(eta, float) and isinstance(hacim, float), (
        'ölçüm tabanı çürüdü: uç artık expulsion_efficiency / '
        'swept_volume_m3 yayımlamıyor')
    metin = press_ekrani_d28['text']
    jet = D15._ekran_jetonlari(metin)
    # BİRLEŞME UYARLAMASI (9 Eyl 2026): ``_gorunur`` artık ad+değer bölgesi
    # ister (OH-D27-17, güvenlik DOM'unda ölçüldü); feed paneli için değer
    # düzeyi ölçüt ``_deger_bolgede`` ile korunur, ad ayrıca aşağıda aranır.
    assert D15._deger_bolgede(eta, metin, jet), (
        'boşaltma verimi ekranda yok: kullanıcı gaz kütlesini görüyor ama '
        'kütlenin hangi boşaltma varsayımıyla ölçeklendiğini göremiyor '
        '(η = ' + repr(eta) + ')')
    assert D15._deger_bolgede(hacim, metin, jet), (
        'süpürülen hacim ekranda yok (' + repr(hacim) + ')')
    assert 'expulsion_efficiency' in metin and 'swept_volume_m3' in metin, (
        'sayılar ADSIZ basılmış — hangi yanıt alanı olduğu okunamıyor')
