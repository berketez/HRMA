# -*- coding: utf-8 -*-
"""ÖH Dalga-26 / arayuz aşama-1 bekçisi — **P11B2-10 + P11B1-09** (çift).

İki kalem tek aşamada onarılır çünkü AYNI kaynak sözlüğünü
(``SOURCE_COLORS`` / ``SOURCE_SYMBOLS``) ve aynı dört hükmü
(hesaplandı / kullanıcı / varsayım / modellenmedi) paylaşırlar.

**P11B2-10** — *"E3 değer kaynağı sınıflandırıcısı hiçbir ürün tüketicisi
olmayan ölü katman."* Ölçüldü (``docs/scofield/raw/OH/D26/arayuz/a1/``
``once.json``, taban ağacı): 16 panelin **12'si** ucun beyan alanlarını
(``X_basis`` / ``X_source`` / ``X_status`` / ``X_model``; 76 ayrı alan adı)
okuyor, ama sınıflandırıcıyı çağıran panel sayısı **2**. Beyanı olan 10
panel hükmü hiç vermiyor, beyanı ekrana düz metin olarak döküyordu; beş
yerde de panel kendi damgasını UYDURUYORDU (``chip({kind:'assumed'})``).
Sonra: bağsız panel **0**, elle damga **0**.

**P11B1-09** — *"Sahnenin 'veri yok / varsayım' beyan mekanizması yalnız 3
kaleme uygulanmış."* Ölçüldü: ``extractDims`` birincil ölçülerin dördünü de
(``chamber_diameter`` 0,1 m; ``chamber_length`` 0,3 m; ``throat_diameter``
0,02 m; ``exit_diameter`` 0,08 m) sessiz bir yedekle çözüyor, kasa cidarı
0,045·D geometrik yedeğine, tane dış çapı ``clamp(0.02·D)`` liner
uydurmasına düşüyordu — ve **hiçbir çip çıkmıyordu**. Beyan defteri alan
sayısı **0**, ölçü-çip kanalı **0**. Sonra: defter 7 alan, çip kanalı
sahnenin durum çipi listesine bağlı, 9 i18n anahtarı EN **ve** TR blokta.

Bu dosya iki kalemin de DAVRANIŞINI kilitler: metin arayan iddialar
yalnız "kanal var kapı yok" kusurunun kendisi (bağlama) içindir; hükmün
doğruluğu node altında GERÇEK fonksiyonlar koşturularak sınanır.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = REPO_ROOT / 'hrma' / 'static' / 'js'
DOCK_JS = JS / 'analysis_dock.js'
VIZ_JS = JS / 'motor_viz3d.js'
PANEL_DIZIN = JS / 'panels'
I18N_JS = JS / 'i18n_common.js'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

#: Ölçüm betiği — bekçi kendi ölçütünü yeniden yazmaz, ONU çağırır.
OLCUM = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D26' / 'arayuz'
         / 'a1' / 'olcum.py')
ONCE = OLCUM.parent / 'once.json'

#: Sınıflandırıcıya bağlanabilecek paneller (yardımcı modül hariç) —
#: ölçüm betiğiyle aynı liste, tek kaynak.
PANEL_HARIC = {'oxidizer_reference_density.js'}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _olcum_modulu():
    """``olcum.py``yi modül olarak yükler (ölçüt TEK yerde yazılıdır)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('d26_arayuz_olcum', kanit_gerekli(OLCUM))
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.argv = ['olcum.py', str(REPO_ROOT)]
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def olcum():
    return _olcum_modulu()


@pytest.fixture(scope='module')
def sonuc(olcum):
    return olcum.SONUC


@pytest.fixture(scope='module')
def taban():
    """Taban ağacının ölçümü — 'önce' sayıları (kanıt dizininde)."""
    if not kanit_gerekli(ONCE).exists():
        pytest.skip('once.json yok')
    return json.loads(kanit_gerekli(ONCE).read_text(encoding='utf-8'))


def _viz_kaynak():
    return VIZ_JS.read_text(encoding='utf-8')


def _fonksiyon(src, ad):
    """Bir JS kaynağından tek fonksiyonu süslü parantez sayarak çıkarır."""
    start = src.index('function %s(' % ad)
    depth, idx = 0, start
    while idx < len(src):
        if src[idx] == '{':
            depth += 1
        elif src[idx] == '}':
            depth -= 1
            if depth == 0:
                return src[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmıyor' % ad)


def _sabit(src, ad):
    m = re.search(r'var %s = [^;]+;' % re.escape(ad), src)
    assert m, 'sabit bulunamadı: %s' % ad
    return m.group(0)


def _node(script):
    # Betik stdin ile verilir (argv tavanı; bkz. test_viz3d_cad_kipi.py::_run).
    res = subprocess.run([NODE], input=script, capture_output=True,
                         text=True, timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


#: Panonun kendisini sahte DOM altında yükleyen koşum başı.
#: (Kalıp: tests/test_d15_ui_paneller_a1.py::DOCK_HARNESS_JS)
DOCK_ONSOZ = r"""
'use strict';
function makeNode(id) {
    return {
        id: id, __html: '', textContent: '', style: {}, attrs: {},
        children: [], value: '',
        classList: { contains: function () { return false; },
                     add: function () {}, remove: function () {} },
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        getAttribute: function (k) {
            return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild: function (c) { this.children.push(c); return c; },
        querySelector: function () { return makeNode('q'); },
        querySelectorAll: function () { return []; },
        addEventListener: function () {},
        get innerHTML() { return this.__html; },
        set innerHTML(v) { this.__html = v; },
    };
}
function deepText(n) {
    if (!n) return '';
    let s = String(n.innerHTML || '');
    (n.children || []).forEach(function (c) { s += deepText(c); });
    return s;
}
const nodes = {};
global.document = {
    head: makeNode('head'), body: makeNode('body'),
    getElementById: function (id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement: function () { return makeNode(null); },
    querySelector: function () { return makeNode('q'); },
    querySelectorAll: function () { return []; },
    addEventListener: function () {},
};
global.window = global;
try {
    Object.defineProperty(global, 'navigator',
                          { value: { language: 'en' }, configurable: true });
} catch (e) { /* node >= 21 salt-okur */ }
global.localStorage = { getItem: function () { return null; },
                        setItem: function () {} };
global.requestAnimationFrame = function (fn) { fn(0); return 1; };
global.fetch = function () {
    return Promise.resolve({ ok: false, json: function () { return {}; } });
};
require(%(dock)s);
const SRC = window.AnalysisDock.ui.source;
"""


def _dock_calistir(govde):
    """Panoyu sahte DOM altında yükleyip ``govde`` ifadesini koşar."""
    onsoz = DOCK_ONSOZ % {'dock': json.dumps(str(DOCK_JS))}
    return _node(onsoz + govde)


# ===========================================================================
# P11B2-10 — sınıflandırıcının ürün tüketicisi
# ===========================================================================

class TestP11B210SiniflandiriciBagli:
    """Ölü katman bitti: beyanı olan her panel hükmü ortak yerden alıyor."""

    def test_beyan_okuyan_her_panel_siniflandiriciyi_cagiriyor(
            self, sonuc, taban):
        """ASIL KUSUR. Taban: 10 panel beyanı okuyup hükmü vermiyordu."""
        onc = taban['P11B2-10_olu_siniflandirici']
        son = sonuc['P11B2-10_olu_siniflandirici']
        assert onc['beyanli_ama_bagsiz_panel'] >= 10, (
            'taban ölçümü bayat: kusur artık orada da yok'
        )
        assert son['beyanli_ama_bagsiz_panel'] == 0, (
            'beyanı olup sınıflandırıcıya bağlanmayan panel(ler): %s'
            % son['beyanli_ama_bagsiz_panel_listesi']
        )
        assert son['siniflandiriciya_bagli_panel'] >= 12

    def test_panel_kendi_damgasini_uydurmuyor(self, sonuc, taban):
        """Beş yerde panel ``chip({kind:'assumed'})`` diye ELLE damgalıyordu.

        Hüküm ucun kendi cümlesinden çıkmalı; panel kendi kararını
        sınıflandırıcının yerine koyarsa uç cümlesini değiştirdiğinde
        ekran yalan söyler.
        """
        assert taban['P11B2-10_olu_siniflandirici']['elle_damgalanan_kind'] >= 5
        assert sonuc['P11B2-10_olu_siniflandirici']['elle_damgalanan_kind'] == 0

    def test_pano_baglama_yardimcilarini_disa_veriyor(self):
        """Paneller yardımcıya ancak ``U.source`` üstünden erişebilir;
        dışa verim düşerse bütün bağlamalar sessizce ölür."""
        ciz = _dock_calistir(r"""
process.stdout.write(JSON.stringify(
    ['ledger', 'ledgerInto', 'declarations', 'of', 'chip', 'cell']
        .map(function (k) { return [k, typeof SRC[k]]; })));
""")
        eksik = [k for k, t in ciz if t != 'function']
        assert not eksik, 'U.source.%s dışa verilmiyor' % eksik

    # -- davranış (node + sahte DOM) ------------------------------------

    def test_defter_beyani_ortak_hukumle_basiyor(self):
        """Uç beyanı → ekranda çip. Kanal değil KAPI sınanır."""
        ciz = _dock_calistir(r"""
const root = makeNode('root');
const govde = {
    wall_thickness: 4.2,
    wall_thickness_basis: 'sized by the structural solver for this design',
    liner_thickness: 1.5,
    liner_thickness_source: 'user_input',
    fudge: 9.9,
    fudge_basis: 'handbook default, not solved here'
};
const n = SRC.ledgerInto(root, govde, { deep: true });
const html = deepText(root);
const kinds = (html.match(/data-src-kind="(\w+)"/g) || [])
    .map(function (s) { return s.split('"')[1]; });
const alanlar = (html.match(/data-src-field="([\w.]+)"/g) || [])
    .map(function (s) { return s.split('"')[1]; });
process.stdout.write(JSON.stringify({
    n: n, kinds: kinds, alanlar: alanlar,
    defter: /data-src-ledger="3"/.test(html)
}));
""")
        assert ciz['n'] == 3, 'üç beyanın üçü de deftere girmeli'
        assert ciz['defter'], 'defter düğümü basılmadı'
        assert set(ciz['alanlar']) == {
            'wall_thickness', 'liner_thickness', 'fudge'}
        # Hüküm ucun KENDİ cümlesinden çıkar: çözücü / kullanıcı / varsayım.
        assert ciz['kinds'] == ['computed', 'user', 'assumed'], ciz['kinds']

    def test_degersiz_beyan_hesaplandi_demiyor(self):
        """FAIL-CLOSED (doktrin 1).

        ``x_basis`` var ama ``x`` YOK: ortada hesaplanmış bir sayı yoktur,
        dolayısıyla hüküm 'modellenmedi' olmak zorundadır. Beyan metnini
        değerin yerine koymak — kesintiye uğrayan ilk sürümün yaptığı —
        "computed from the Bartz correlation" diyen ama sayısı olmayan
        alana HESAPLANDI damgası bastırıyordu.
        """
        ciz = _dock_calistir(r"""
const root = makeNode('root');
const govde = {
    q_wall_basis: 'computed from the Bartz correlation for this throat'
};
SRC.ledgerInto(root, govde, { deep: true });
const html = deepText(root);
process.stdout.write(JSON.stringify({
    kinds: (html.match(/data-src-kind="(\w+)"/g) || [])
        .map(function (s) { return s.split('"')[1]; }),
    // Sayı uydurulmadı mı? (em-dash basılmalı)
    emdash: html.indexOf('—') !== -1,
    // Beyan metni yine de gösteriliyor mu (bilgi kaybı yok)?
    beyan: html.indexOf('Bartz') !== -1
}));
""")
        assert ciz['kinds'] == ['missing'], (
            'değeri olmayan beyana %s damgası basıldı' % ciz['kinds'])
        assert ciz['emdash'], 'değer yokken sayı yerine em-dash basılmalı'
        assert ciz['beyan'], 'beyan metni ekrandan düştü — bilgi kaybı'

    def test_beyansiz_blokta_hicbir_dugum_eklenmiyor(self):
        """Boş "kaynaklar" başlığı = gürültü; bağlama sessiz olmalı."""
        ciz = _dock_calistir(r"""
const root = makeNode('root');
const n = SRC.ledgerInto(root, { thrust: 1000, isp: 250 }, { deep: true });
process.stdout.write(JSON.stringify({
    n: n, cocuk: root.children.length, html: deepText(root)
}));
""")
        assert ciz['n'] == 0
        assert ciz['cocuk'] == 0
        assert ciz['html'] == ''

    def test_ic_bloktaki_beyan_da_yakalaniyor(self):
        """Uçlar beyanı ``cfd.*`` / ``safety_factors.*`` altına yayımlıyor."""
        ciz = _dock_calistir(r"""
const root = makeNode('root');
const govde = { cfd: { y_plus: 31.0,
                       y_plus_status: 'not_modelled' } };
SRC.ledgerInto(root, govde, { deep: true });
const html = deepText(root);
process.stdout.write(JSON.stringify({
    alanlar: (html.match(/data-src-field="([\w.]+)"/g) || [])
        .map(function (s) { return s.split('"')[1]; }),
    kinds: (html.match(/data-src-kind="(\w+)"/g) || [])
        .map(function (s) { return s.split('"')[1]; })
}));
""")
        assert ciz['alanlar'] == ['cfd.y_plus'], ciz['alanlar']
        assert ciz['kinds'] == ['missing']

    def test_olumsuzlama_korlugu_geri_gelmedi(self):
        """D24'te onarılan yarı — çift, aynı sözlükten beslendiği için burada
        da çapalanır: "…, NOT entered by the user" USER damgası ALMAZ."""
        ciz = _dock_calistir(r"""
const root = makeNode('root');
const govde = { sf_min: 1.4,
    sf_min_basis: 'materials_db recommended design factor, '
        + 'not the design safety factor entered by the user' };
SRC.ledgerInto(root, govde, { deep: true });
const html = deepText(root);
process.stdout.write(JSON.stringify({
    kinds: (html.match(/data-src-kind="(\w+)"/g) || [])
        .map(function (s) { return s.split('"')[1]; })
}));
""")
        assert ciz['kinds'] == ['assumed'], (
            'olumsuzlama körlüğü: %s damgası basıldı' % ciz['kinds'])


# ===========================================================================
# P11B1-09 — 3B sahnenin ölçü kaynağı beyanı
# ===========================================================================

class TestP11B109SahneOlcuBeyani:
    """Birincil ölçüler uydurma yedeğe düştüğünde sahne bunu SÖYLÜYOR."""

    def test_beyan_defteri_yedi_olcuyu_kapsiyor(self, sonuc, taban):
        onc = taban['P11B1-09_viz3d_beyan']
        son = sonuc['P11B1-09_viz3d_beyan']
        assert onc['beyan_defteri_alan_sayisi'] == 0, (
            'taban ölçümü bayat: sahnede zaten defter var')
        assert set(son['beyan_defteri_alanlari']) >= {
            'chamber_diameter', 'chamber_length', 'throat_diameter',
            'exit_diameter', 'casing_wall', 'grain_outer_diameter',
            'grain_length'}

    def test_cip_kanali_sahnenin_durum_listesine_bagli(self, sonuc, taban):
        """ÖLÜ KATMAN TEKRARININ BEKÇİSİ.

        Çip tanımı ÜRETMEK yetmez; ``_statusChipDefs`` listesine girmezse
        kullanıcı onu hiç görmez — kalemin kendi kusuru buydu.
        """
        assert taban['P11B1-09_viz3d_beyan']['cip_durum_listesine_bagli'] == 0
        assert sonuc['P11B1-09_viz3d_beyan']['cip_durum_listesine_bagli'] >= 1

    def test_simge_tablosu_panoyla_birebir(self, sonuc, taban):
        """Tek görsel dil: sahnedeki çip ile panodaki çip aynı simgeyi kullanır
        (renk tek başına ayırt edici değildir — renk körlüğü)."""
        assert taban['P11B1-09_viz3d_beyan']['simge_tablosu_birebir'] == 0
        son = sonuc['P11B1-09_viz3d_beyan']
        assert son['simge_tablosu_birebir'] == 1
        assert son['renk_tablosu_birebir'] == 1

    def test_sahne_cipi_simgeyi_gercekten_basiyor(self, sonuc, taban):
        """ÖLÜ SABİT BEKÇİSİ.

        Tabloyu dosyaya koymak "tek görsel dil" demek DEĞİLDİR: sahne
        çipi simgeyi basmıyorsa tablo dekoratif bir ölü sabittir — bu
        kalemin kınadığı kusurun ta kendisi. Çip metni ``sourceSymbol``
        ile başlamak zorundadır.
        """
        assert taban['P11B1-09_viz3d_beyan']['sahne_cipi_simge_basiyor'] == 0
        assert sonuc['P11B1-09_viz3d_beyan']['sahne_cipi_simge_basiyor'] == 1

    def test_i18n_anahtarlari_en_ve_tr_blogunda(self, sonuc, taban):
        """Anahtar dosya SONUNA değil, ilgili bloğun İÇİNE."""
        assert taban['i18n_anahtar_sayilari']['_eksiksiz_cift_sayisi'] == 0
        i = sonuc['i18n_anahtar_sayilari']
        assert i['_eksiksiz_cift_sayisi'] == i['_toplam_anahtar'], i

    # -- davranış (node, izole fonksiyon) --------------------------------

    def test_cidar_hukmu_nereden_geldigini_soyluyor(self):
        """``resolveCasingWall`` üç yolun HANGİSİNİ kullandığını beyan eder."""
        src = _viz_kaynak()
        prelude = (_fonksiyon(src, 'num') + '\n'
                   + _sabit(src, 'CASING_WALL_SCHEMAS') + '\n'
                   + _fonksiyon(src, 'resolveCasingWall') + '\n')
        ciz = _node(prelude + r"""
function dene(md) {
    var o = {};
    var v = resolveCasingWall(md, 100, o);
    return { v: v, kind: o.kind, basis: o.basis || null };
}
process.stdout.write(JSON.stringify({
    // 1) Yapısal sonuç YOK → 0,045·D geometrik yedeği: VARSAYIM.
    yedek: dene({}),
    // 2) Çözücünün önerdiği kalınlık: HESAPLANDI.
    onerilen: dene({ structural_analysis: { chamber_structure: {
        required_wall_thickness: 7.5 } } }),
    // 3) Doğrulama kipinde kullanıcının cidarı: KULLANICI.
    kullanici: dene({ structural_analysis: { chamber_structure: {
        design_mode: 'verify', wall_thickness: 6.0,
        required_wall_thickness: 7.5 } } })
}));
""")
        assert ciz['yedek']['kind'] == 'assumed', ciz['yedek']
        assert ciz['yedek']['v'] == pytest.approx(4.5)
        assert ciz['onerilen']['kind'] == 'computed', ciz['onerilen']
        assert ciz['onerilen']['v'] == pytest.approx(7.5)
        assert ciz['kullanici']['kind'] == 'user', ciz['kullanici']
        assert ciz['kullanici']['v'] == pytest.approx(6.0)
        # Beyan ADIYLA verilir — "varsayım" demek yetmez, hangi kural?
        assert ciz['yedek']['basis'], 'yedeğin dayanağı adlandırılmamış'

    def test_cip_yalniz_uydurma_olculer_icin_cikiyor(self):
        """Her ölçüye çip basmak uyarıyı gürültüye gömer: temiz veri =
        temiz sahne, uydurma ölçü = ADIYLA beyan."""
        src = _viz_kaynak()
        prelude = ("function T(k, f) { return f; }\n"
                   + _sabit(src, 'DIM_SRC_LABEL_KEYS') + '\n'
                   + _fonksiyon(src, 'srcNote') + '\n'
                   + _fonksiyon(src, 'dimensionSourceChipDefs') + '\n')
        ciz = _node(prelude + r"""
var hepsiCozucu = { motorType: 'solid', srcDecl: {
    chamber_diameter: { kind: 'computed' },
    chamber_length: { kind: 'computed' },
    throat_diameter: { kind: 'computed' },
    exit_diameter: { kind: 'computed' },
    casing_wall: { kind: 'computed' },
    grain_outer_diameter: { kind: 'computed' },
    grain_length: { kind: 'computed' } } };
var ikisiUydurma = { motorType: 'solid', srcDecl: {
    chamber_diameter: { kind: 'assumed', basis: 'fallback 0.1 m' },
    chamber_length: { kind: 'computed' },
    throat_diameter: { kind: 'computed' },
    exit_diameter: { kind: 'computed' },
    casing_wall: { kind: 'assumed', basis: 'geometric fallback 0.045·D' },
    grain_outer_diameter: { kind: 'computed' },
    grain_length: { kind: 'computed' } } };
// Sıvı motorda TANE ölçüsü anlamsızdır — beyan edilmemeli.
var sivi = { motorType: 'liquid', srcDecl: {
    chamber_diameter: { kind: 'computed' },
    chamber_length: { kind: 'computed' },
    throat_diameter: { kind: 'computed' },
    exit_diameter: { kind: 'computed' },
    casing_wall: { kind: 'computed' },
    grain_outer_diameter: { kind: 'assumed' },
    grain_length: { kind: 'assumed' } } };
process.stdout.write(JSON.stringify({
    temiz: dimensionSourceChipDefs(hepsiCozucu),
    uydurma: dimensionSourceChipDefs(ikisiUydurma),
    sivi: dimensionSourceChipDefs(sivi),
    bos: dimensionSourceChipDefs({})
}));
""")
        assert ciz['temiz'] == [], 'her ölçü çözücüden geldi, çip çıkmamalı'
        assert ciz['sivi'] == [], 'sıvı motorda tane ölçüsü beyan edilmez'
        assert len(ciz['uydurma']) == 1, 'uyarı tek çipte toplanmalı'
        cip = ciz['uydurma'][0]
        assert cip['kind'] == 'assumed'
        assert set(cip['fields']) == {'chamber_diameter', 'casing_wall'}
        # Beyan ADIYLA: kullanıcı hangi ölçünün uydurma olduğunu okumalı.
        assert 'chamber' in cip['text'] and 'casing' in cip['text'], cip['text']
        # Beyanı olmayan (boş) sahne sessiz kalır — uydurma uyarı basılmaz.
        assert ciz['bos'] == []

    def test_extract_dims_defteri_disa_veriyor(self):
        """``extractDims`` dönen sözlükte ``srcDecl`` taşımalı; taşımazsa
        çip kanalı boşa çalışır (kanal var kapı yok)."""
        src = _viz_kaynak()
        govde = _fonksiyon(src, 'extractDims')
        assert 'srcDecl: srcDecl' in govde, (
            'extractDims dönüşünde srcDecl yok')
        for alan in ('chamber_diameter', 'chamber_length', 'throat_diameter',
                     'exit_diameter', 'grain_length'):
            assert "decl('%s'" % alan in govde, (
                '%s için kaynak hükmü yazılmıyor' % alan)


# ===========================================================================
# Ortak — sözlük tek kaynak
# ===========================================================================

def test_kaynak_sozlugu_iki_dosyada_ayni(sonuc):
    """TEK KAYNAK (doktrin 4): sahne ile pano aynı dört hükmü aynı renk ve
    aynı simgeyle gösterir. İkisi ayrışırsa kullanıcı iki görsel dil öğrenir.
    """
    son = sonuc['P11B1-09_viz3d_beyan']
    assert son['renk_tablosu_birebir'] == 1
    assert son['simge_tablosu_birebir'] == 1


def test_panel_dosyalari_node_altinda_ayristirilabiliyor():
    """Bağlama satırı eklenen her panel sözdizimsel olarak sağlam."""
    hedef = ['comparative_panel.js', 'feed_panel.js', 'joint_panel.js',
             'uncertainty_panel.js', 'stability_panel.js', 'cfd_panel.js',
             'protection_panel.js', 'safety_panel.js',
             'structural_panel.js', 'vessel_panel.js']
    for fn in hedef:
        p = PANEL_DIZIN / fn
        assert p.exists(), fn
        res = subprocess.run([NODE, '--check', str(p)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, '%s: %s' % (fn, res.stderr[-600:])
