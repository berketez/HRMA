"""Sıvı yakıt sayfası (liquid.html) sözleşme testleri — 2026-07-19 parite dalgası.

Bu dosya, sıvı sayfasında düzeltilen dört sınıf hatayı kalıcı olarak kilitler:

  1. PANEL YERLEŞİMİ
     SixDofPanel / InjectorPanel / AnalysisDock init çağrılarında
     `anchorId: 'analysis-dock-anchor'` VARDIR ve çapa #results kabının
     İÇİNDEDİR. anchorId verilmezse paneller `.results-grid` arar, bu sayfada
     öyle bir kap yoktur, `.container`a düşerler ve hesap yapılmadan görünür
     olurlar (2026-07-19 bulgusu; katı sayfada da aynı hata vardı).

  2. HİBRİT/KATI PARİTESİ
     NASA CEA + NIST rozetleri, motor kesiti lejant açıklaması, uyarı paneli,
     ve altı gerçek export butonu (.eng / çizim PDF / DXF / STEP / komple ZIP /
     Excel) sayfada VARDIR ve doğru uçlara gider.

  3. YANILTICI BOŞ KUTU YOK
     `#parametric_plots` bölümü tamamen kaldırıldı — /parametric-analysis ucu
     yalnız HybridRocketEngine kurar, sıvı motoru desteklemez.

  4. SESSİZ VERİ KAYBI YOK
     app.py'deki LiquidRocketEngine(...) çağrısı yalnız yedi alanı kabul eder.
     Şablon bunu hem toplu bir "Solver Input Scope" notuyla hem de bağlanmamış
     alanların yanındaki satır içi işaretle DÜRÜSTÇE gösterir. Test, şablondaki
     SOLVER_WIRED_INPUT_IDS listesinin app.py'nin gerçek imzasıyla birebir
     tuttuğunu doğrular — backend bir alanı bağlarsa test kırılır ve liste
     güncellenmeye zorlanır.

Ayrıca: satır içi script'ler `node --check` geçer (node varsa) ve kullanıcıya
görünen Türkçe metin kalmamıştır (kod yorumları bilinçli olarak Türkçedir).
"""

import ast
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'
APP_PY = REPO_ROOT / 'hrma' / 'app.py'

DOCK_ANCHOR_ID = 'analysis-dock-anchor'

# Panellerin init çağrılarında anchorId ZORUNLU olan JS modülleri.
ANCHORED_PANELS = ['SixDofPanel', 'InjectorPanel', 'AnalysisDock']

# Sayfada bulunması gereken gerçek export uçları.
EXPORT_ENDPOINTS = [
    '/api/export-eng',
    '/api/export-drawings-pdf',
    '/api/export-dxf',
    '/api/export-step',
    '/api/export-complete-zip',
    '/api/export-xlsx',
]

# Export butonlarının çağırdığı fonksiyon adları (onclick içinde).
EXPORT_HANDLERS = [
    'downloadLiquidEng',
    'exportLiquidDrawingsPDF',
    'exportLiquidDXF',
    'exportLiquidSTEP',
    'exportLiquidCompleteZip',
    'exportLiquidExcel',
]

# app.py:1544 civarındaki LiquidRocketEngine(...) çağrısının GERÇEKTEN
# okuduğu form alanları. Şablondaki SOLVER_WIRED_INPUT_IDS bununla aynı olmalı.
EXPECTED_WIRED_FIELDS = {
    'fuel_type', 'oxidizer_type', 'thrust', 'chamber_pressure',
    'mixture_ratio', 'cooling_type', 'injector_type',
}

# Kesit lejantındaki renkler visualization.py paletinden birebir gelir.
CROSS_SECTION_COLORS = {
    'chamber wall': 'rgba(148,163,180,0.85)',   # C_CASE
    'injector plate': 'rgba(210,177,116,0.95)',  # C_INJ
    'nozzle': 'rgba(122,136,150,0.9)',           # C_NOZ
}

# Daha önce sayfada bulunan, kullanıcıya görünen Türkçe metinler.
FORBIDDEN_VISIBLE_TR = ['>Parametre<', '>Birim<', '>Motor Kesiti<', 'Referans Alan']

TURKISH_CHARS = re.compile(r'[çğıİöşüÇĞÖŞÜ]')
ALLOWED_TR_TOKENS = ('Tezgöçen', 'Türkçe')


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def html():
    return LIQUID_HTML.read_text(encoding='utf-8')


def inline_scripts(text):
    """src'siz <script> bloklarının gövdelerini döndürür."""
    return re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', text, re.S)


def mask_comments_and_style(text):
    """Yorumları ve <style> bloklarını aynı uzunlukta boşlukla değiştirir.

    Satır sayısı korunur (ofsetler bozulmasın diye newline'lar aynen bırakılır),
    böylece bulgu satır numarasıyla raporlanabilir. Türkçe KOD YORUMLARI proje
    tercihidir; testin kapsamı yalnız ekranda görünen metin.
    """
    out = list(text)
    patterns = [
        r'<!--[\s\S]*?-->',
        r'<style[\s\S]*?</style>',
        r'/\*[\s\S]*?\*/',
        r'(?m)^[ \t]*//[^\n]*$',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            for i in range(m.start(), m.end()):
                if out[i] != '\n':
                    out[i] = ' '
    return ''.join(out)


def strip_allowed(fragment):
    for token in ALLOWED_TR_TOKENS:
        fragment = fragment.replace(token, '')
    return fragment


# ---------------------------------------------------------------------------
# 1. Panel yerleşimi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('panel', ANCHORED_PANELS)
def test_panel_init_has_anchor_id(html, panel):
    """Her panel init'i anchorId ile çağrılır (yoksa .container'a düşer)."""
    m = re.search(re.escape(panel) + r'\.init\(\{(.*?)\n\s*\}\);', html, re.S)
    assert m, f'{panel}.init(...) çağrısı bulunamadı'
    body = m.group(1)
    assert f"anchorId: '{DOCK_ANCHOR_ID}'" in body, (
        f'{panel}.init içinde anchorId eksik — panel hesap yapılmadan görünür'
    )


def test_dock_anchor_is_inside_results_container(html):
    """Çapa #results kabının İÇİNDE olmalı ki hesap bitmeden görünmesin."""
    start = html.index('<div id="results" class="results">')
    anchor = html.index(f'<div id="{DOCK_ANCHOR_ID}"></div>')
    assert anchor > start, 'analysis-dock-anchor #results kabından önce geliyor'

    # #results ile çapa arasında kapanmamış <div> sayısı > 0 olmalı
    between = html[start:anchor]
    opens = len(re.findall(r'<div\b', between))
    closes = len(re.findall(r'</div>', between))
    assert opens > closes, 'analysis-dock-anchor #results kabının dışına düşmüş'


def test_results_grid_absent(html):
    """Panellerin yedek çapası .results-grid bu sayfada YOK — bug'ın kökü."""
    assert 'class="results-grid"' not in html


# ---------------------------------------------------------------------------
# 2. Parite: rozetler / kesit açıklaması / uyarı paneli / exportlar
# ---------------------------------------------------------------------------
#: Rozet sınıfı ⟷ rozet metni sözleşmesi (ÖH D22 · P13B2-05). Her sınıf
#: kendi metnini ZORUNLU kılar; hangi sınıfın ilk boyada durduğu ŞART
#: DEĞİLDİR. Böylece rozet sınıfı ileride "status-unknown"a çevrilse de
#: (P17B2-07 onarımı) bekçi bir DÜZELTMEyi kırmızıya çevirmez.
ROZET_SINIF_METNI = {
    'status-connected': ('Connected',),
    'status-disconnected': ('Offline',),
    'status-unknown': ('not checked',),
}


def test_database_status_badges_present(html):
    """Rozetler var, iki durum da tanımlı ve sınıf ⟷ metin çelişmiyor.

    ÇEVRİLDİ (ÖH D22 · P13B2-05). Eski hâli statik
    ``class="database-status status-connected cea-status"`` dizesini ŞART
    koşuyordu — yani hiçbir denetim koşmadan YEŞİL yanan rozeti. Kardeş
    şablonlarda (advanced.html, solid.html) tam bu kusur P17B2-07 olarak
    ölçüldü ve ÖH D21'de onarıldı; liquid.html onarımın dışında kaldı
    ÇÜNKÜ bu bekçi kusuru kilitliyordu (``tests/test_d21_arayuz_a2.py``
    ``ROZET_SABLONLARI`` bu yüzden yalnız iki şablon sayıyor).

    Kilit kaldırıldı; yerine iki fail-closed iddia kondu:

    1. Rozetler ve İKİ durum sınıfı da tanımlı olmalı (kaybolma bekçisi).
    2. Bir rozetin İLAN ETTİĞİ sınıf ile YAZDIĞI metin çelişemez —
       "status-unknown" taşıyıp "Connected" yazan ya da "status-connected"
       taşıyıp "not checked" yazan rozet, hangi yönde olursa olsun
       kullanıcıya yalan söyler.

    Şablonun kendisi (``hrma/templates/liquid.html``) ÖH D22'de sivi ve
    arayuz kulvarlarının sahasındadır; bu kulvar ürün dosyasına dokunmaz.
    """
    for sinif in ('cea-status', 'nist-status'):
        assert 'class="database-status' in html, 'rozet kabı yok'
        assert sinif in html, sinif
    assert '.status-connected' in html and '.status-disconnected' in html
    rozetler = re.findall(
        r'<span class="database-status ([^"]*)"[^>]*>([^<]*)</span>', html)
    assert rozetler, 'sayfada hiç veri tabanı rozeti bulunamadı'
    for siniflar, metin in rozetler:
        durum = [d for d in ROZET_SINIF_METNI if d in siniflar]
        assert len(durum) == 1, (siniflar, metin)
        beklenen = ROZET_SINIF_METNI[durum[0]]
        assert any(b in metin for b in beklenen), (
            'rozet sınıfı %r ile metni %r çelişiyor (beklenen: %s)'
            % (durum[0], metin, ' / '.join(beklenen)))
        # Ters yön: başka bir durumun metnini taşıyamaz.
        for baska, metinler in ROZET_SINIF_METNI.items():
            if baska == durum[0]:
                continue
            assert not any(m in metin for m in metinler), (siniflar, metin)


def test_database_status_is_fetched(html):
    assert "fetch('/api/database-status')" in html
    assert 'function checkDatabaseStatus' in html
    assert 'checkDatabaseStatus();' in html, 'rozet güncelleyici hiç çağrılmıyor'


def test_cross_section_explanation_present(html):
    """Motor kesiti için renk-kutucuklu lejant açıklaması var."""
    assert 'id="liquid_kesit_explanation"' in html
    block = html[html.index('id="liquid_kesit_explanation"'):]
    block = block[:block.index('id="liquid_motor_kesit"')]
    low = block.lower()
    for label, color in CROSS_SECTION_COLORS.items():
        assert label in low, f'kesit lejantında "{label}" yok'
        assert color in block, f'"{label}" için visualization.py rengi ({color}) yok'
    assert 'legend-swatch' in block


def test_cross_section_explanation_has_no_grain(html):
    """Sıvı motorda yakıt grain'i/liner YOKTUR; lejant grain listelemez."""
    block = html[html.index('id="liquid_kesit_explanation"'):]
    block = block[:block.index('id="liquid_motor_kesit"')].lower()
    # 'no fuel grain or liner' cümlesi hariç, grain bir BİLEŞEN olarak geçmemeli
    assert 'rgba(178,116,68' not in block, 'grain rengi (C_GRAIN) sıvı lejantında olmamalı'


def test_warnings_panel_present_and_hidden_by_default(html):
    assert 'id="warningsPanel"' in html
    assert 'id="warningsList"' in html
    m = re.search(r'<div id="warningsPanel"[^>]*>', html)
    assert 'display: none' in m.group(0), 'uyarı paneli varsayılan olarak gizli olmalı'
    assert 'function displayLiquidWarnings' in html
    assert 'displayLiquidWarnings(results);' in html, 'uyarı paneli hiç doldurulmuyor'


@pytest.mark.parametrize('endpoint', EXPORT_ENDPOINTS)
def test_export_endpoint_referenced(html, endpoint):
    assert f"'{endpoint}'" in html, f'{endpoint} ucu sayfada kullanılmıyor'


@pytest.mark.parametrize('handler', EXPORT_HANDLERS)
def test_export_button_and_handler(html, handler):
    assert f'onclick="{handler}()"' in html, f'{handler} butonu yok'
    assert re.search(r'function\s+' + handler + r'\s*\(', html), \
        f'{handler} fonksiyonu tanımlı değil'


def test_excel_sheets_are_liquid_specific(html):
    """Excel çalışma kitabı sıvıya uygun sayfalar içerir."""
    block = html[html.index('async function exportLiquidExcel'):]
    block = block[:block.index('SESSİZ VERİ KAYBI KORUMASI')]
    for sheet in ("name: 'Performance'", "name: 'Geometry'",
                  "name: 'Injector'", "name: 'Feed system'"):
        assert sheet in block, f'Excel sayfası eksik: {sheet}'


def test_eng_export_uses_declared_burn_time(html):
    """ÖH D36 / LU-2 (ÇEVRİLEN BEKÇİ): .eng düğmesi çözücünün yanıtını gönderir.

    Eski iddia ("yanma süresi çözücüden gelmez; alan açıkça okunur" +
    istemcide ``total_impulse: thrust * burnTime``) Cowork LU-2'nin kusurunun
    kendisiydi: düğme form alanından F x t ve mdot x t türetiyor, çözücünün
    tank kartını göndermiyordu ve uç 400 s ile bile 422 veriyordu (ölçüm:
    raw/OH/D36/onemli2-sivi/a1/once.json). Süre artık çözücüye girer
    (LU-1) ve düğme o koşumun yanıtını olduğu gibi gönderir; istemci sayı
    türetmez, formu yeniden okumaz.
    """
    block = html[html.index('async function downloadLiquidEng'):]
    block = block[:block.index('async function exportLiquidExcel')]
    assert "getElementById('max_burn_duration')" not in block
    assert 'thrust * burnTime' not in block
    assert 'Object.assign({}, cr, { motor_name: _liquidMotorName() })' in block


# ---------------------------------------------------------------------------
# 3. Yanıltıcı boş kutu yok
# ---------------------------------------------------------------------------
def test_parametric_placeholder_removed(html):
    """#parametric_plots ve 'hesaplanmıyor' yer tutucusu tamamen kaldırıldı."""
    assert 'id="parametric_plots"' not in html
    assert 'id="parametric_trajectory_content"' not in html
    assert "showSubTab('parametric_trajectory')" not in html
    assert 'computed in this release' not in html


def test_no_dead_plot_containers(html):
    """Sayfadaki her Plotly hedefi ya doldurulur ya da hiç yoktur."""
    # generateParametricPlots yalnız gerçekten çizilen üç div'i doldurur
    assert 'function generateParametricPlots' in html
    block = html[html.index('function generateParametricPlots'):]
    block = block[:block.index('function hrmaFmt')]
    for div in ('drawSingleAltitudePlot', 'drawAltitudeProfilePlot', 'drawEngineDiagram'):
        assert div in block


# ---------------------------------------------------------------------------
# 4. Sessiz veri kaybı: bağlanmamış alanlar dürüstçe işaretli
# ---------------------------------------------------------------------------
#: ``LiquidRocketEngine(...)`` çağrısına verilmesine rağmen bir İSTEK ALANI
#: taşımayan anahtarlar. ``overrides=data`` bütün sözlüğü toptan geçirir; adı
#: geçen tek bir alan değildir, bu yüzden alan sayımına girmez.
_LIQUID_ALAN_DISI_KWARG = {'overrides'}


def _istek_alanlari(dugum, fn):
    """``dugum`` ifadesinin OKUDUĞU ``data['X']`` / ``data.get('X')`` adları.

    Yerel değişkene uğrayan yol da çözülür: ``cooling_type=cooling_type``
    gibi bir anahtar, aynı fonksiyonda ``cooling_type = data.get(
    'cooling_type')`` ile kurulmuşsa alan ADI oradan okunur.

    ÖH D15 birleştirme (1 Eyl 2026) — BU İŞLEV BEKÇİYİ ÇEVİRİYOR. Eskisi
    çağrı METNİNDE ``data.get('X')`` deseni arıyor, bulamadığı üç adı da
    ('thrust', 'chamber_pressure', 'mixture_ratio') elle beyaz listeye
    yazıyordu. Sıvı kulvarının fail-closed soğutma kapısı (app.py
    ``unsupported_cooling_type``, KAPI 1e) ``cooling_type``ı çağrıdan ÖNCE
    bir yerele aldı — alan hâlâ çözücüye gidiyor, ama artık metinde
    görünmüyor. Beyaz liste büyütmek kusuru gizlerdi: liste, alanın
    gerçekten bağlı olduğunu DEĞİL yalnız testin onu affettiğini söyler.
    Bu yüzden bağ artık AST ile İZLENİYOR; bir alan tümden düşerse bekçi
    kırmızı yanar.

    ÖH D27 / fix-26b — ÜÇÜNCÜ OKUMA BİÇİMİ (``f(data, 'alan', ...)``).
    ÖLÇÜLDÜ (taban ``8abbe822``): ``cooling_type`` ve ``injector_type``
    "hangi istek alanından beslendiği ÇÖZÜLEMEDİ" diye kırmızı veriyordu.
    Sebep bir gerileme değil: D26 / sivi a1 (``e000be6e``, P16B3-02 kalan)
    bu iki okumayı ``data.get(...)``tan alıp TEK KAYNAĞA, yani
    ``_sivi_secim_varsayilani(data, 'cooling_type', ...)`` yardımcısına
    taşıdı (ÖK-19 künyesi: varsayılana düşülünce ``defaults_applied``a
    yazılıyor). Alan hâlâ okunuyor; değişen yalnız okumanın BİÇİMİDİR.
    Çözücü GENEL desenle genişletildi, ad beyaz listesi YAZILMADI: ilk
    konumsal argümanı ``data``, ikincisi DİZE SABİTİ olan her çağrı o
    dizeyi bir istek alanı sayar. Alan tümden düşerse ad da düşer ve
    bekçi yine kırmızı yanar (ters-mutasyon M9 bunu ölçtü).
    """
    adlar = set()
    yerel_adlar = set()
    for n in ast.walk(dugum):
        if isinstance(n, ast.Name):
            yerel_adlar.add(n.id)
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'get'
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == 'data' and n.args
                and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            adlar.add(n.args[0].value)
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and len(n.args) >= 2
                and isinstance(n.args[0], ast.Name)
                and n.args[0].id == 'data'
                and isinstance(n.args[1], ast.Constant)
                and isinstance(n.args[1].value, str)):
            adlar.add(n.args[1].value)
        if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                and n.value.id == 'data'
                and isinstance(n.slice, ast.Constant)
                and isinstance(n.slice.value, str)):
            adlar.add(n.slice.value)
    if adlar:
        return adlar
    # Yerele uğrayan yol: aynı fonksiyondaki atamalarını izle.
    for hedef_ad in yerel_adlar:
        if hedef_ad == 'data':
            continue
        for n in ast.walk(fn):
            if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                continue
            hedefler = (n.targets if isinstance(n, ast.Assign)
                        else [n.target])
            if not any(isinstance(t, ast.Name) and t.id == hedef_ad
                       for t in hedefler):
                continue
            if n.value is None:
                continue
            adlar |= _istek_alanlari(n.value, ast.Module(body=[], type_ignores=[]))
    return adlar


def _liquid_engine_wired_fields():
    """``calculate_liquid``ın ``LiquidRocketEngine``e GERÇEKTEN bağladığı alanlar."""
    agac = ast.parse(APP_PY.read_text(encoding='utf-8'))
    fn = None
    cagri = None
    for f in ast.walk(agac):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(f):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == 'LiquidRocketEngine'):
                fn, cagri = f, n
    assert cagri is not None, 'app.py içinde LiquidRocketEngine(...) çağrısı yok'
    kullanilan = set()
    cozulemeyen = []
    for kw in cagri.keywords:
        if kw.arg in _LIQUID_ALAN_DISI_KWARG or kw.arg is None:
            continue
        alanlar = _istek_alanlari(kw.value, fn)
        if not alanlar:
            cozulemeyen.append(kw.arg)
        kullanilan |= alanlar
    assert not cozulemeyen, (
        'bu anahtarların hangi istek alanından beslendiği ÇÖZÜLEMEDİ, yani '
        'bağ ölçülemiyor (sessizce "bağlı" saymak yerine söyleniyor): %s'
        % sorted(cozulemeyen))
    return kullanilan


def test_solver_wired_list_matches_app_py(html):
    """Şablondaki 'çözücüye bağlı alanlar' listesi app.py imzasıyla aynı."""
    m = re.search(r'const SOLVER_WIRED_INPUT_IDS = \[(.*?)\];', html, re.S)
    assert m, 'SOLVER_WIRED_INPUT_IDS listesi bulunamadı'
    declared = set(re.findall(r"'([^']+)'", m.group(1)))
    assert declared == EXPECTED_WIRED_FIELDS, (
        'Şablondaki bağlı-alan listesi app.py ile uyuşmuyor.\n'
        f'  şablon: {sorted(declared)}\n'
        f'  beklenen: {sorted(EXPECTED_WIRED_FIELDS)}'
    )

    # app.py gerçekten bu alanları mı okuyor?
    used = _liquid_engine_wired_fields()
    assert used == EXPECTED_WIRED_FIELDS, (
        'app.py artık farklı alanlar okuyor — liquid.html listesini güncelle.\n'
        f'  app.py: {sorted(used)}\n'
        f'  şablon: {sorted(EXPECTED_WIRED_FIELDS)}'
    )


def test_unwired_inputs_are_marked(html):
    """Çözücüye ulaşmayan alanlar arayüzde işaretlenir (sessiz kayıp yok)."""
    m = re.search(r'const UNWIRED_INPUT_IDS = \[(.*?)\];', html, re.S)
    assert m, 'UNWIRED_INPUT_IDS listesi bulunamadı'
    unwired = set(re.findall(r"'([^']+)'", m.group(1)))
    # Görev metninde açıkça adı geçen alanlar mutlaka listede olmalı
    for field in ('startup_sequence', 'throttle_response'):
        assert field in unwired, f'{field} bağlanmamış olduğu halde işaretlenmiyor'
    # ÖH D15 · P12bB1-09 — BEKÇİ ÇEVRİLDİ. Bu satır 'min_throttle' alanının
    # statik "Not wired to the solver yet" yaftasını KİLİTLİYORDU. Çözücü o
    # alanı 2026-07'de kendi unwired_inputs() beyanından çıkardı (gerekçe
    # liquid_rocket_engine.py:1573 civarında yazılı) ve alan bugün
    # throttle_map.min_throttle_pct ile chug RİSK hükmünü çeviriyor
    # (ölçüm: min_throttle 40 → chug_risk True, 80 → False;
    #  docs/scofield/raw/OH/D15/sablonlar/a1/once.json). Hesaptan ÖNCE basılan
    # yafta bu yüzden yalandı; testin eski hâli yalanı koruyordu.
    assert 'min_throttle' not in unwired, (
        'min_throttle çözücüye BAĞLI (chug risk hükmünü çeviriyor); '
        'statik "bağlanmamış" yaftası yalan olur'
    )
    # Bağlı alanlar YANLIŞLIKLA işaretlenmemeli
    assert not (unwired & EXPECTED_WIRED_FIELDS)

    assert 'function markUnwiredInputs' in html
    assert 'markUnwiredInputs();' in html, 'işaretleyici hiç çağrılmıyor'
    assert 'not-wired-note' in html


def test_export_only_input_is_labelled_separately(html):
    """ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ): max_burn_duration artık "yalnızca
    dışa aktarım" diye işaretlenmez.

    Eski iddia ("çözücüyü etkilemez ama .eng exportunu besler") 2026-07-19
    denetiminden beri YANLIŞTI: çözücü süreyi itici kütlesine, tank kartına
    ve toplam impulsa sokuyor (Cowork LU-1 madde 3). Yeni iddia: alanın
    altına GERÇEK kapsam notu basılır ve eski "export only" işaretleyicisi
    sayfada çağrılmaz.
    """
    assert 'const INPUT_SCOPE_NOTES' in html
    assert 'markInputScopeNotes();' in html
    assert 'markExportOnlyInputs();' not in html
    assert 'const EXPORT_ONLY_INPUTS' not in html


def test_solver_scope_note_present(html):
    """Kullanıcı formu ayarlamadan önce kapsamı görür."""
    assert 'id="solver_scope_note"' in html
    block = html[html.index('id="solver_scope_note"'):]
    block = block[:block.index('<!-- 1. Propellant Data -->')]
    assert 'Solver Input Scope' in block
    assert 'does not change the computed result' in block


def test_pdf_report_geometry_comes_from_results(html):
    """PDF geometrisi kullanıcının yazdığı (yok sayılan) değerlerden okunmaz."""
    block = html[html.index('async function exportPDF'):]
    block = block[:block.index('GRAFİK KALİTESİ')]
    assert "getElementById('chamber_diameter')" not in block
    assert "getElementById('throat_diameter')" not in block
    assert 'chamber_diameter: cr.chamber_diameter' in block


# ---------------------------------------------------------------------------
# 5. Grafik kalitesi
# ---------------------------------------------------------------------------
def test_all_plots_go_through_shared_renderer(html):
    """Tek doğrudan Plotly.newPlot çağrısı liquidPlot'un KENDİSİ olmalı."""
    direct = re.findall(r'Plotly\.newPlot\(', html)
    assert len(direct) == 1, (
        f'{len(direct)} doğrudan Plotly.newPlot çağrısı var; hepsi liquidPlot()'
        ' üzerinden geçmeli (responsive + hovermode + min-height)'
    )
    # Tek çağrı liquidPlot'un GÖVDESİNDE olmalı. OH-P-17 (D34 piksel turu,
    # 0f093fb7; defter OH-YENI.jsonl) çağrının sonuna kasıtlı olarak
    # `.then(... Plotly.Plots.resize ...)` ekledi (gizli kapta 700 px
    # varsayılanı → kabın gerçek genişliği); bu yüzden satır sonundaki ';'
    # artık sözleşmenin parçası değil. Çağrının YERİ ve argümanları öyle.
    body = html[html.index('function liquidPlot('):]
    body = body[:body.index('function setNistStatus')]
    assert 'return Plotly.newPlot(el, traces, lay, cfg)' in body, \
        'tek Plotly.newPlot çağrısı liquidPlot gövdesinde değil'


def test_shared_renderer_applies_quality_defaults(html):
    block = html[html.index('function liquidPlot('):]
    block = block[:block.index('function setNistStatus')]
    assert 'delete lay.width;' in block, 'sabit width kaldırılmıyor'
    assert "lay.hovermode = 'x unified'" in block
    assert 'responsive: true' in block
    assert 'LIQUID_PLOT_MIN_HEIGHT_PX' in block


def test_no_fixed_width_in_plot_layouts(html):
    """Layout literal'lerinde sabit piksel genişliği kalmadı."""
    assert not re.search(r'\n\s*width:\s*\d{3,}\s*,', html)


def test_plot_containers_have_min_height(html):
    """Her Plotly kabı CSS'te açık min-height alır (0 px'e ezilme koruması)."""
    css = html[html.index('<style>'):html.index('</style>')]
    assert 'min-height: 400px' in css
    for cid in ('#liquid_motor_kesit', '#altitude_analysis_plot',
                '#altitude_profile_plot', '#engine_diagram', '#trajectory_plots'):
        assert cid in css, f'{cid} için min-height kuralı yok'


# ---------------------------------------------------------------------------
# 6. Sözdizimi ve dil
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
def test_inline_scripts_parse(html):
    blocks = inline_scripts(html)
    assert len(blocks) >= 3, 'satır içi script blokları bulunamadı'
    for idx, body in enumerate(blocks):
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(body)
            path = fh.name
        proc = subprocess.run(['node', '--check', path],
                              capture_output=True, text=True)
        pathlib.Path(path).unlink(missing_ok=True)
        assert proc.returncode == 0, (
            f'{idx}. satır içi script sözdizimi hatalı:\n{proc.stderr}')


@pytest.mark.parametrize('needle', FORBIDDEN_VISIBLE_TR)
def test_known_turkish_strings_removed(html, needle):
    assert needle not in html, f'kullanıcıya görünen Türkçe metin kaldı: {needle}'


def test_no_visible_turkish_text(html):
    """Yorumlar/style hariç, görünen metinde Türkçe'ye özgü harf kalmadı."""
    masked = mask_comments_and_style(html)
    offenders = []
    for lineno, line in enumerate(masked.split('\n'), 1):
        for m in re.finditer(r'>([^<>]{2,200})<', line):
            frag = strip_allowed(m.group(1))
            if TURKISH_CHARS.search(frag):
                offenders.append((lineno, frag.strip()))
        for m in re.finditer(r'(?:title|placeholder|alt|aria-label)\s*=\s*"([^"]*)"',
                             line):
            frag = strip_allowed(m.group(1))
            if TURKISH_CHARS.search(frag):
                offenders.append((lineno, frag.strip()))
    assert not offenders, f'görünen Türkçe metin: {offenders[:5]}'


def test_no_emoji_in_template(html):
    """Emoji yasağı (Berke 2026-07-15)."""
    emoji = re.compile(
        '[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]')
    hits = emoji.findall(html)
    assert not hits, f'şablonda emoji var: {hits[:10]}'


# ---------------------------------------------------------------------------
# 7. Sayfa gerçekten servis ediliyor mu
# ---------------------------------------------------------------------------
def test_liquid_page_renders():
    from hrma.app import app
    client = app.test_client()
    resp = client.get('/liquid')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f"anchorId: '{DOCK_ANCHOR_ID}'" in body
    assert 'id="liquid_export_panel"' in body
    assert 'id="warningsPanel"' in body
