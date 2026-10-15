"""ÖH D29 · arayuz-panel aşama-3 bekçileri.

Kapsam (11 kalem): P11B1-13, P11B1-14, P11B2-15, P11B2-16, P11B2-17,
P11B2-19, P11B2-21, P11B3-13, P11B3-17, P11B3-22, P11B3-25.

Her iddia bir ÖLÇÜME dayanır (``docs/scofield/raw/OH/D29/arayuz-panel/a3/
once.json`` → ``sonra.json``) ve ters-mutasyonla kırmızı verdiği kanıtlanır
(``mutasyon.json``). Saf katmanı olan kalemler node ile DAVRANIŞTAN ölçülür;
kaynak metni sayan bekçilerde gövde önce yorumlardan arındırılır (D29 a1
dersi: yorumdaki sembol "bağlanmış" sanılmasın).
"""
import json
import os
import re
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


def _yorumsuz_js(metin):
    metin = re.sub(r'/\*.*?\*/', '', metin, flags=re.S)
    return re.sub(r'(?m)//.*$', '', metin)


def _blok(metin, imza):
    """``imza`` ile başlayan gövdeyi süslü parantez dengesiyle döndürür."""
    i = metin.find(imza)
    if i < 0:
        return None
    j = metin.find('{', i)
    if j < 0:
        return None
    derinlik, k = 0, j
    while k < len(metin):
        if metin[k] == '{':
            derinlik += 1
        elif metin[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i:k + 1]
        k += 1
    return None


def _node(betik):
    ck = subprocess.run(['node'], input=betik, capture_output=True,
                        text=True, timeout=90)
    assert ck.returncode == 0, ck.stderr
    return json.loads(ck.stdout)


@pytest.fixture(scope='module')
def viz():
    return _oku('hrma/static/js/motor_viz3d.js')


@pytest.fixture(scope='module')
def deck():
    return _oku('hrma/static/js/motor_viz_deck.js')


@pytest.fixture(scope='module')
def appjs():
    return _oku('hrma/static/js/app.js')


@pytest.fixture(scope='module')
def center():
    return _oku('hrma/static/js/analysis_center.js')


@pytest.fixture(scope='module')
def dock():
    return _oku('hrma/static/js/analysis_dock.js')


@pytest.fixture(scope='module')
def fea():
    return _oku('hrma/static/js/fea_panel.js')


@pytest.fixture(scope='module')
def cfd():
    return _oku('hrma/static/js/panels/cfd_panel.js')


# ==========================================================================
# P11B1-13 — cıvata sayısı uydurulmaz
# ==========================================================================

def test_p11b113_civata_tabani_yok(viz):
    """``Math.max(6, …)`` tabanı ve ``num(..., 8)`` yedeği sökülmeli.

    Ölçülen (once.json): taban `nBolts: Math.max(6, Math.round(num(
    fasteners.num_bolts, 8)))`. Katı ve sıvı /calculate yanıtlarında
    `fastener_analysis.num_bolts` YOKTUR (çapa yükünden ölçüldü), yani o
    iki sayfada çizilen 8 cıvatanın kaynağı bu satırdı.
    """
    g = _yorumsuz_js(viz)
    assert 'Math.max(6, Math.round(num(fasteners.num_bolts' not in g, \
        'cıvata sayısında sessiz yukarı yuvarlama geri gelmiş'
    assert not re.search(r'num\(fasteners\.num_bolts,\s*8\)', g), \
        'çözücü sayı vermeyince 8 cıvata uyduruluyor'


def test_p11b113_civata_kaynagi_olculuyor(viz):
    """Sayı yoksa 0 çizilir; hüküm ölçülür ve defterde durur."""
    g = _yorumsuz_js(viz)
    assert re.search(
        r'var boltKaynakli = isFinite\(boltSrc\) && boltSrc > 0;', g), \
        'cıvata sayısının hükmü ölçülmüyor'
    assert re.search(r'nBolts:\s*boltKaynakli \? Math\.round\(boltSrc\) : 0', g), \
        'kaynaksız cıvata sayısı 0 değil'
    assert "srcDecl['bolt_count']" in g, 'cıvata hükmü defterde yok'
    assert "kind: 'missing'" in _blok(g, "srcDecl['bolt_count']") or \
        "kind: 'missing'" in g[g.find("srcDecl['bolt_count']"):
                               g.find("srcDecl['bolt_count']") + 600], \
        'yayımlanmayan cıvata sayısı "missing" olarak imlenmiyor'


def test_p11b113_cip_etiketi_bagli(viz):
    """Beyan çipe bağlı olmalı — defterde durup ekranda görünmeyen hüküm."""
    g = _yorumsuz_js(viz)
    i = g.find('var DIM_SRC_LABEL_KEYS = ')
    assert i > 0
    tablo = g[i:g.find('};', i)]
    assert 'bolt_count:' in tablo, 'bolt_count çip etiketi tabloda yok'


def test_p11b113_orifis_emsali_bozulmadi(viz):
    """Aynı kuralın ilk uygulaması (orifis) yerinde kalmalı."""
    g = _yorumsuz_js(viz)
    assert re.search(r'nOrifices:\s*\(\(injSrc\.nOrifices\s*>\s*0', g)


# ==========================================================================
# P11B1-14 — ısı efsanesinin niteleyicisi
# ==========================================================================

def test_p11b114_niteleyici_guvertede(deck):
    """Efsane başlığı hibrit sayfayla AYNI niteleyiciyi taşımalı.

    Dize BÖLÜNEREK eklenir: ``HEAT_LEGEND_TEXT`` i18n_charts.js sözlüğünde
    BİREBİR bu metinle anahtarlıdır (o dosya bu dalgada kardeş kulvarın),
    dizeyi değiştirmek TR karşılığını düşürürdü.
    """
    g = _yorumsuz_js(deck)
    assert "var HEAT_LEGEND_WALL_REF = '(reference cooled wall)';" in g
    assert re.search(
        r"return TX\(HEAT_LEGEND_TEXT\) \+ ' ' \+ TX\(HEAT_LEGEND_WALL_REF\);",
        g), 'başlık iki parçadan kurulmuyor'
    # Sözlük anahtarı olan dize DEĞİŞMEMİŞ olmalı (çeviri düşmesin).
    assert ("var HEAT_LEGEND_TEXT = "
            "'WALL HEAT FLUX — BARTZ (A<sub>t</sub>/A)<sup>0.9</sup>';") in g


def test_p11b114_baslik_her_iki_yolda_ayni(deck):
    """İlk çizim ve refreshLabels AYNI kaynaktan konuşmalı."""
    g = _yorumsuz_js(deck)
    assert g.count('heatLegendHead()') >= 2, \
        'başlık iki yoldan birinde eski (parçasız) hâline dönmüş'
    assert 'TX(HEAT_LEGEND_TEXT) + ' in g
    assert not re.search(r"hlHead\.innerHTML = TX\(HEAT_LEGEND_TEXT\);", g)


def test_p11b114_borc_notu_tasindi(deck):
    """~2,5 kat borcu güvertede de yazılı olmalı (title künyesi)."""
    g = _yorumsuz_js(deck)
    assert 'HEAT_LEGEND_DEBT_NOTE' in g
    assert '2.5x lower' in g, 'borç cümlesindeki oran düşmüş'
    assert 'escAttr(TX(HEAT_LEGEND_DEBT_NOTE))' in g


def test_p11b114_efsane_olu_degil(deck):
    """ÇÜRÜTME KİLİDİ: kalemin 'ölü kod' yarısı bugün YANLIŞ.

    Ölçüldü (once.json): katı ve sıvı adaptörleri
    ``data.heat_transfer_analysis`` bloğunu geçiriyor ve ürün üç uçta da
    ``gas_side_analysis.throat_heat_flux`` yayımlıyor — ısı düğmesi
    gizlenmiyor. Kilit: gizleme koşulu ``getHeatInfo()``ya bağlı kalmalı
    (koşulsuz gizleme geri gelirse kırmızı).
    """
    g = _yorumsuz_js(deck)
    assert 'if (heatBtn && !viz.getHeatInfo())' in g, \
        'ısı düğmesinin gizlenmesi ölçüme değil sabite bağlanmış'
    for sayfa in ('hrma/templates/solid.html', 'hrma/templates/liquid.html'):
        assert re.search(r'data\.heat_transfer_analysis\s*=', _oku(sayfa)), \
            '%s ısıl bloğu güverteye geçirmiyor' % sayfa


# ==========================================================================
# P11B2-15 — thrust_curve.mass_flow çizilir, künyesi basılır
# ==========================================================================

def test_p11b215_mass_flow_izi_var(appjs):
    g = _yorumsuz_js(appjs)
    assert 'curve.mass_flow' in g, 'mass_flow hâlâ okunmuyor'
    assert re.search(r'const massFlowCizilir = massFlow\.length === '
                     r'curve\.time\.length', g), \
        'debi izi uzunluk kapısı olmadan ekleniyor'
    assert 'v => typeof v === \'number\' && isFinite(v)' in g
    # Kör nokta kapısı: iz sadece TANIMLI değil, koşulsuz-ölü de olmamalı.
    assert re.search(r'\n    if \(massFlowCizilir\) \{\n        traces\.push\(\{',
                     g), 'debi izi ölü dala alınmış'


def test_p11b215_kunye_basiliyor(appjs):
    g = _yorumsuz_js(appjs)
    assert 'function thrustCurveDeclaration(' in g
    govde = _blok(g, 'function thrustCurveDeclaration(')
    for alan in ('thrust_curve.basis', 'points_published', 'points_computed',
                 'solver_time_step_s', 'cap_exceeded'):
        assert alan in govde, 'künyede %s yok' % alan
    assert '\n    thrustCurveDeclaration(panel, curve);' in g, \
        'künye üreticisi çizim yolundan çağrılmıyor (tanım satırı sayılmaz)'


def test_p11b215_kunye_bos_yukte_kutu_acmaz(appjs):
    """Alan yoksa satır YAZILMAZ; boş kutu bırakılmaz (fail-closed)."""
    govde = _blok(_yorumsuz_js(appjs), 'function thrustCurveDeclaration(')
    assert re.search(r'if \(!satirlar\.length\) \{\s*if \(kutu\) kutu\.remove\(\);',
                     govde), 'boş künye kutusu ekranda kalıyor'


# ==========================================================================
# P11B2-16 — sunucunun ham gövdesi kullanıcıya basılmaz
# ==========================================================================

def test_p11b216_ham_govde_mesaja_gomulmuyor(appjs):
    g = _yorumsuz_js(appjs)
    assert 'body: ${errorText}' not in g, \
        'Flask gövdesi yeniden hata mesajına gömülmüş'
    assert 'sunucuHataMetni(' in g


def test_p11b216_alert_ozetten_geciyor(appjs):
    g = _yorumsuz_js(appjs)
    assert "${hataGovdeOzeti(error.message)}" in g, \
        'alert ham error.message basıyor'


def test_p11b216_davranis_node_ile(appjs):
    """Üç gövde türü: yapılı JSON, HTML, uzun düz metin."""
    g = _yorumsuz_js(appjs)
    parcalar = [_blok(g, 'function hataGovdeOzeti('),
                _blok(g, 'function sunucuHataMetni(')]
    assert all(parcalar)
    tavan = re.search(r'const HATA_GOVDE_TAVANI = (\d+);', g)
    assert tavan
    betik = ('function SRV(t) { return t; }\nconst HATA_GOVDE_TAVANI = '
             + tavan.group(1) + ';\n' + '\n'.join(parcalar) + r"""
var html = '<!doctype html><html><body><pre>Traceback (most recent call '
    + 'last): File "app.py", line 1</pre></body></html>';
process.stdout.write(JSON.stringify({
  yapili: sunucuHataMetni(422, 'application/json',
      JSON.stringify({ error: 'chamber_length out of band', field: 'L_c' })),
  html: sunucuHataMetni(500, 'text/html; charset=utf-8', html),
  uzun: sunucuHataMetni(500, 'text/plain', 'x'.repeat(1200)),
  bos: sunucuHataMetni(503, null, '')
}));
""")
    r = _node(betik)
    assert r['yapili'] == 'HTTP 422: chamber_length out of band [L_c]'
    assert 'Traceback' not in r['html'], 'HTML gövde kullanıcıya sızıyor'
    assert '<' not in r['html']
    assert 'text/html' in r['html'] and 'browser console' in r['html']
    assert 'truncated' in r['uzun'] and '1200 bytes total' in r['uzun']
    assert len(r['uzun']) < 500
    assert r['bos'] == 'HTTP 503'


# ==========================================================================
# P11B2-17 — koşum geçmişi sınırsız büyümez
# ==========================================================================

def test_p11b217_tavanlar_tanimli(center):
    g = _yorumsuz_js(center)
    assert re.search(r'const GECMIS_TAVANI = \d+;', g)
    assert re.search(r'const GECMIS_YUK_TAVANI = \d+;', g)
    assert 'gecmisiBuda();' in g, 'budama pushEntry yolundan çağrılmıyor'
    assert 'clearHistory: gecmisiTemizle,' in g, 'silme yolu dışa açık değil'


def test_p11b217_budama_davranisi_node_ile(center):
    """Yük bırakma SATIRIN SON kaydını korumalı; kayıt tavanı en eskiyi atmalı."""
    g = _yorumsuz_js(center)
    govde = _blok(g, 'function gecmisiBuda(')
    assert govde
    tav = re.search(r'const GECMIS_TAVANI = (\d+);', g).group(1)
    yuk = re.search(r'const GECMIS_YUK_TAVANI = (\d+);', g).group(1)
    betik = ('const GECMIS_TAVANI = ' + tav + ';\nconst GECMIS_YUK_TAVANI = '
             + yuk + ';\nvar runHistory = [], lastEntryByRow = {}, '
             'viewingEntryId = null;\n' + govde + r"""
for (var i = 0; i < 60; i++) {
    var e = { id: i, rowKey: 'row' + (i % 12), ok: true, data: { big: i } };
    runHistory.push(e);
    lastEntryByRow[e.rowKey] = e;
    gecmisiBuda();
}
var n = runHistory.length;
var sonKayit = {};
Object.keys(lastEntryByRow).forEach(function (k) {
    sonKayit[lastEntryByRow[k].id] = true; });
// Yüklü kalan her kayıt YA en yeni GECMIS_YUK_TAVANI içinde YA DA bir
// satırın SON kaydı olmalı — başka gerekçeyle yük tutulamaz.
var gereksizYuklu = runHistory.filter(function (e, i) {
    return e.data !== null && i < n - GECMIS_YUK_TAVANI && !sonKayit[e.id];
});
var sonlar = Object.keys(lastEntryByRow).map(function (k) {
    return lastEntryByRow[k].data !== null; });
process.stdout.write(JSON.stringify({
    kayit: n, tavan: GECMIS_TAVANI,
    gereksizYuklu: gereksizYuklu.length,
    sonKayitlariYuklu: sonlar,
    birakilan: runHistory.filter(function (e) { return e.yukBirakildi; }).length
}));
""")
    r = _node(betik)
    assert r['kayit'] == r['tavan'], 'kayıt tavanı uygulanmıyor'
    assert r['gereksizYuklu'] == 0, \
        'yük tavanı dışında kalan %d kaydın yükü hâlâ bellekte' % r['gereksizYuklu']
    assert all(r['sonKayitlariYuklu']), \
        'bir satırın SON koşumunun yükü bırakılmış (ekrandaki sonuç kaybolur)'
    assert r['birakilan'] > 0, 'hiç yük bırakılmamış — tavan ölü'


def test_p11b217_birakilan_yuk_sessiz_degil(center):
    """Yükü bırakılmış kayıt görüntüleyicide ADIYLA söylenir; kiracı çağrılmaz."""
    g = _yorumsuz_js(center)
    assert 'data-ac-payload-released' in g
    assert re.search(r'if \(entry\.ok && entry\.yukBirakildi\) \{', g)
    i = g.find('if (entry.ok && entry.yukBirakildi)')
    j = g.find('spec.render(entry.data, root)')
    assert 0 < i < j, 'bırakılmış yük dalı kiracı çağrısından SONRA'


# ==========================================================================
# P11B2-19 — warnText düz metin alanlarını ham JSON basmaz
# ==========================================================================

def test_p11b219_dock_ham_json_basmiyor(dock):
    g = _yorumsuz_js(dock)
    assert 'if (!w.code) return JSON.stringify(w);' not in g
    assert "if (!w.code) return SRV(w.message || w.text || JSON.stringify(w));" in g


def test_p11b219_davranis_node_ile(dock, appjs):
    """Dock ve app.js AYNI girdide AYNI metni üretmeli."""
    gd, ga = _yorumsuz_js(dock), _yorumsuz_js(appjs)
    dw = _blok(gd, 'function warnText(w, depth)')
    aw = _blok(ga, 'function warnToText(w, depth)')
    assert dw and aw
    # app.js'in yerel dalı: dock yüklü değilken çalışan kısım.
    aw = aw.replace(
        "if (window.AnalysisDock && window.AnalysisDock.ui\n"
        "        && window.AnalysisDock.ui.warnText) {\n"
        "        return window.AnalysisDock.ui.warnText(w);\n    }\n", '')
    betik = ("var window = {};\nfunction SRV(t) { return t; }\n"
             "function TF(k, p, f) { return f; }\n" + dw + '\n' + aw + r"""
var ornek = [{ message: 'plain message' }, { text: 'plain text field' },
             { code: 'warn.x', fallback: 'fallback text' }];
process.stdout.write(JSON.stringify({
    dock: ornek.map(function (o) { return warnText(o); }),
    app: ornek.map(function (o) { return warnToText(o); })
}));
""")
    r = _node(betik)
    assert r['dock'] == ['plain message', 'plain text field', 'fallback text']
    assert r['dock'] == r['app'], \
        'iki uygulama aynı sözleşmede yine ayrışıyor: %r' % (r,)


# ==========================================================================
# P11B2-21 — kapalı Run düğmesi gerekçesini söyler
# ==========================================================================

def test_p11b221_gerekce_uretiliyor(center):
    g = _yorumsuz_js(center)
    assert 'function mesgulGerekcesi(' in g
    assert 'busyRow = row;' in g, 'koşan satır kaydedilmiyor'
    assert g.count('busyRow = null;') >= 3, \
        'koşum bitince koşan satır temizlenmiyor (bayat gerekçe)'


def test_p11b221_bos_durum_satiri_kalmiyor(center):
    """``statusState`` boşken KOŞUM SÜRÜYORSA gerekçe basılmalı."""
    g = _yorumsuz_js(center)
    govde = _blok(g, 'function renderStatus(')
    assert govde
    assert 'btn.title = busy ? mesgulGerekcesi() : \'\';' in govde, \
        'kapalı düğmenin kendi künyesi yok'
    assert re.search(r'if \(!statusState\) \{\s*if \(busy\) \{\s*'
                     r'el\.textContent = mesgulGerekcesi\(\);', govde), \
        'seçim değişince durum satırı yine sessiz kalıyor'


def test_p11b221_gerekce_adi_uydurmuyor(center):
    """Ad kayıtlı spec'ten gelir; yoksa yalnız genel metin basılır."""
    govde = _blok(_yorumsuz_js(center), 'function mesgulGerekcesi(')
    assert 'if (!busyRow) return kok;' in govde
    assert 'busyRow.titleKey' in govde


# ==========================================================================
# P11B3-13 — yakınsama grafiği inceltmenin yönünü gizlemez
# ==========================================================================

def test_p11b313_yon_verisi_aliniyor(fea):
    g = _yorumsuz_js(fea)
    govde = _blok(g, 'function buildConvergence(')
    assert govde
    for alan in ('h.n_axial', 'h.n_radial', 'h.yon', 'karar'):
        assert alan in govde, 'buildConvergence %s okumuyor' % alan
    assert 'yon_katlama' in govde


def test_p11b313_katlama_sayimi_node_ile(fea):
    """Ölçülen geçmiş: (12,4) → (12,8) → (12,16) → (12,32).

    Beklenen: eksenel 0 katlama, radyal 3. Panel bunu SAYAR, uydurmaz.
    """
    g = _yorumsuz_js(fea)
    govde = _blok(g, 'function buildConvergence(')
    betik = ("const PA_PER_MPA = 1e6;\nfunction isNum(v) { return typeof v "
             "=== 'number' && isFinite(v); }\n" + govde + r"""
var hist = [
  { n_elems: 48, n_axial: 12, n_radial: 4, max_von_mises: 1e7, rel_change: null },
  { n_elems: 96, n_axial: 12, n_radial: 8, max_von_mises: 1.1e7, rel_change: 0.09,
    yon: 'radyal' },
  { n_elems: 192, n_axial: 12, n_radial: 16, max_von_mises: 1.12e7,
    rel_change: 0.02, yon: 'radyal' },
  { n_elems: 384, n_axial: 12, n_radial: 32, max_von_mises: 1.121e7,
    rel_change: 0.0089, yon: 'radyal',
    karar: { d_eksenel: 0.00227, d_radyal: 0.00664, gerekce: 'radyal katlandı' } }
];
var c = buildConvergence({ history: hist, converged: true, tol: 0.01,
                           final_rel_change: 0.0089 });
process.stdout.write(JSON.stringify({
  katlama: c.yon_katlama, karar: !!c.karar,
  gerekce: c.karar && c.karar.gerekce, nAxial: c.n_axial, nRadial: c.n_radial
}));
""")
    r = _node(betik)
    assert r['katlama'] == {'eksenel': 0, 'radyal': 3}, \
        'yön katlama sayımı yanlış: %r' % (r['katlama'],)
    assert r['karar'] and r['gerekce'] == 'radyal katlandı'
    assert r['nAxial'] == [12, 12, 12, 12]


def test_p11b313_grafik_yon_kunyesi_ve_rel_izi(fea):
    g = _yorumsuz_js(fea)
    assert 'function convYonEtiketleri(' in g
    figur = _blok(g, 'function convergenceFigure(')
    assert re.search(r'if \(yonEtiket\) \{\s*izler\[0\]\.text = yonEtiket;',
                     figur), 'yön künyesi ölü dala alınmış'
    assert 'hovertemplate' in figur, 'noktaların yön künyesi yok'
    assert 'conv.rel_change_pct' in figur, \
        'yükte hazır göreli değişim dizisi yine çizilmiyor'
    assert "yaxis: 'y2'" in figur
    # Kesit paneli de aynı künyeyi almalı (aynı buildConvergence).
    gfigur = _blok(g, 'function grainConvergenceFigure(')
    assert 'convYonEtiketleri(conv)' in gfigur


def test_p11b313_yon_beyani_notta(fea):
    g = _yorumsuz_js(fea)
    assert 'conv.yon_katlama' in g
    assert 'refinements)' in g
    assert 'not a uniform-refinement study' in g, \
        'tek yönde inceltme uyarısı düşmüş'
    assert 'conv.karar.gerekce' in g


# ==========================================================================
# P11B3-17 — kabul grafiği kapasite çizgisiyle ezilmez
# ==========================================================================

def test_p11b317_eksen_karari_saf_katmanda(fea):
    g = _yorumsuz_js(fea)
    assert 'function boreEksenAraligi(' in g
    assert re.search(r'const BORE_EKSEN_PAYI = [\d.]+;', g)
    assert '_boreEksenAraligi: boreEksenAraligi,' in g


def test_p11b317_ezilme_node_ile_olculur(fea):
    """Ölçülen (P11 kaydı): gerinim -0,1393 … 0,8414 %, kapasite 35,0 %.

    Ortak eksende bant, eksenin %2,8'ini kaplıyordu. Onarımdan sonra eksen
    banda oturur (pay > %70) ve kapasite ölçek dışı OLDUĞU YAZILIR.
    """
    g = _yorumsuz_js(fea)
    govde = _blok(g, 'function boreEksenAraligi(')
    pay = re.search(r'const BORE_EKSEN_PAYI = ([\d.]+);', g).group(1)
    betik = ("const BORE_EKSEN_PAYI = " + pay + ";\nfunction isNum(v) "
             "{ return typeof v === 'number' && isFinite(v); }\n" + govde + r"""
var strain = [-0.1393, 0.2, 0.5, 0.8414];
var uzak = boreEksenAraligi(strain, 35.0);
var yakin = boreEksenAraligi(strain, 1.2);
process.stdout.write(JSON.stringify({ uzak: uzak, yakin: yakin }));
""")
    r = _node(betik)
    assert r['yakin'] is None, \
        'kapasite banda YAKINken eksen kilitleniyor (bilgi kaybı)'
    assert r['uzak'], 'kapasite ölçek dışıyken eksen hâlâ ona kilitli'
    lo, hi = r['uzak']['range']
    bant = 0.8414 - (-0.1393)
    assert (hi - lo) < 1.6 * bant, 'eksen banda oturmuyor'
    assert bant / (hi - lo) > 0.70, 'gerinim bandı eksenin %70\'inden az'
    # Ortak eksende ölçülen pay (kusurun kendisi) çok daha küçüktü:
    assert bant / (35.0 - (-0.1393)) < 0.05
    assert abs(r['uzak']['kapasiteOlcekDisi'] - 0.8414 / 35.0) < 1e-9


def test_p11b317_olcek_disi_beyani_grafikte(fea):
    """Kapasite çizilmiyorsa DEĞERİ ve oranı ekranda yazılı olmalı."""
    figur = _blok(_yorumsuz_js(fea), 'function grainBoreFigure(')
    assert 'boreEksenAraligi(' in figur
    assert re.search(r'if \(boreRange\) \{\s*layout\.yaxis\.range = '
                     r'boreRange\.range;', figur), \
        'eksen aralığı ölü dala alınmış'
    assert 'strain_capability_pct = ' in figur
    assert 'off scale' in figur
    assert 'kapasiteOlcekDisi' in figur


# ==========================================================================
# P11B3-22 — viskoz köprünün kendi "iyimser" beyanları panelde
# ==========================================================================

def test_p11b322_gorunum_modeline_aliniyor(cfd):
    g = _yorumsuz_js(cfd)
    vm = _blok(g, 'function viscousModel(')
    assert 'tp.not_modelled' in vm, 'thermal_profile.not_modelled alınmıyor'
    assert 'fr.not_modelled' in vm, 'friction.not_modelled alınmıyor'


def test_p11b322_ekranda_basiliyor(cfd):
    g = _yorumsuz_js(cfd)
    assert 'function altNotModelledHtml(' in g
    assert g.count("altNotModelledHtml('viscous.thermal_profile'") >= 2, \
        'profil çizilemediği dalda beyan düşüyor'
    assert "altNotModelledHtml('viscous.friction'" in g
    govde = _blok(g, 'function altNotModelledHtml(')
    assert 'listBlock(blok)' in govde
    assert "data-cfd-block=\"not-modelled-'" in govde, \
        'blok makine okunur imini taşımıyor'


def test_p11b322_bos_blok_baslik_acmaz(cfd):
    govde = _blok(_yorumsuz_js(cfd), 'function altNotModelledHtml(')
    assert re.search(r"!Object\.keys\(blok\)\.length", govde), \
        'boş sözlük için boş başlık basılıyor'


def test_p11b322_urun_bloklari_yerinde():
    """Kaynak: bu beyanlar köprünün KENDİ metnidir, panel uydurmaz."""
    wo = _oku('hrma/cfd/wall_output.py')
    for ad in ('wall_roughness', 'radiation', 'wall_temperature_coupling'):
        assert "'%s':" % ad in wo, 'köprü beyanı %s kaybolmuş' % ad


# ==========================================================================
# P11B3-25 — ayrılma ölçütü eşikleri ve istasyonları düşmez
# ==========================================================================

def test_p11b325_uye_kunyesi_basiliyor(cfd):
    g = _yorumsuz_js(cfd)
    govde = _blok(g, 'function separationCriteriaHtml(')
    assert govde
    for alan in ('basis_kind', 'threshold_min_Pa', 'threshold_max_Pa',
                 'separation_index', 'reliability_basis'):
        assert alan in govde, 'ölçüt künyesinde %s yok' % alan
    assert re.search(r'if \(isNum\(m\.threshold_min_Pa\) \|\| '
                     r'isNum\(m\.threshold_max_Pa\)\) \{', govde), \
        'eşik satırı ölü dala alınmış'


def test_p11b325_uye_konumlari_ve_fark(cfd):
    g = _yorumsuz_js(cfd)
    govde = _blok(g, 'function separationCriteriaHtml(')
    assert 'yayilim.separation_z_m' in govde, \
        'üye başına ayrılma konumu yine düşüyor'
    assert re.search(r'if \(isNum\(spread\.cfd_minus_empirical_m\)\) \{',
                     govde), \
        'CFD ile ampirik üyeler arasındaki işaretli fark basılmıyor'
    assert 'spread.z_span_m' in govde, 'mevcut yayılım satırı kaybolmuş'


def test_p11b325_kunye_html_kacisina_takilmaz(cfd):
    """``kvTable`` hücreyi esc'ler: künye HTML ile yazılmamalı."""
    govde = _blok(_yorumsuz_js(cfd), 'function separationCriteriaHtml(')
    i = govde.find('const kunye = [];')
    j = govde.find('return [ad, deger];')
    assert 0 < i < j
    assert '<div' not in govde[i:j], \
        'künye HTML olarak ekleniyor — kvTable onu düz metin basar'


def test_p11b325_guven_kunyesi_tekillestiriliyor(cfd):
    govde = _blok(_yorumsuz_js(cfd), 'function separationCriteriaHtml(')
    assert 'const guvenKunyeleri = {};' in govde
    assert 'Object.keys(guvenKunyeleri).forEach(' in govde


# ==========================================================================
# Ölçüm dosyaları — bekçi ölçümün KENDİSİNİ de bağlar
# ==========================================================================

def test_olcum_dosyalari_kalemleri_kapsiyor():
    kok = 'docs/scofield/raw/OH/D29/arayuz-panel/a3/'
    once = json.loads(_oku(kanit_gerekli(kok + 'once.json')))
    sonra = json.loads(_oku(kanit_gerekli(kok + 'sonra.json')))
    kalemler = ['P11B1-13', 'P11B1-14', 'P11B2-15', 'P11B2-16', 'P11B2-17',
                'P11B2-19', 'P11B2-21', 'P11B3-13', 'P11B3-17', 'P11B3-22',
                'P11B3-25']
    assert sorted(once) == sorted(kalemler)
    assert sorted(sonra) == sorted(kalemler)
    degisen = [k for k in kalemler if once[k] != sonra[k]]
    assert sorted(degisen) == sorted(kalemler), \
        'ölçüm bazı kalemlerde hiç değişmemiş: %s' % (
            sorted(set(kalemler) - set(degisen)),)
