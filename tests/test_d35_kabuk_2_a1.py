"""ÖH Dalga-35 · kulvar **kabuk-2** · aşama a1 — BEKÇİ.

21 Eylül görsel kabul turunun (Cowork) ve ana modelin piksel turunun
kabuk/güverte kalemlerini kilitler. Bekçi ölçütünü yeniden yazmaz: ölçüm
``docs/scofield/raw/OH/D35/kabuk-2/a1/olc.js`` betiğinindir; buradaki
iddialar onun SAYILARINI sınar ve nerede mümkünse KAYNAK DİZESİ değil
DAVRANIŞ okur (ilgili işlev node altında yalıtılıp gerçekten koşturulur).

Kalemler ve ÖLÇÜLEN kusur (``a1/once.json``, taban ``32e98e9a``):

==========  ==========================================  ===================
Kalem       Kusur                                       Önce → Sonra
==========  ==========================================  ===================
OH-GT-31    güverte seçicisi seçili seçeneği ortadan     ızgara 170→210 px,
            kesiyor, tam metni okumanın yolu yok        bütçeyi aşan 64→36,
                                                        title yok → var
OH-GT-32    "Yapısal Asgari EK" kartı künyesi (SAHA      ölçüldü, onarım
            DIŞI: app.js — sayi-bicimi kulvarı)         DEVREDİLDİ
OH-GT-33    büyütme birim simgelerini ve özel adları    şerit adı büyütülen
            bozuyor (kN→KN, mm→MM, Summerfield→         → yazıldığı gibi;
            SUMMERFİELD, Pa→PA, liquid→LİQUİD)          merkez etiketi 8→0
OH-GT-34    hesap öncesi grafik yer tutucusu Türkçe      TR kuralı yok → var
            kipte İngilizce (CSS ``content``)
OH-GT-35    /launch-site dili KENDİ EN/TR düğmeleriyle   düğme 2 → 0
            değiştiriyor (ürünün geri kalanı kabuk
            şeridindeki Ayarlar > Dil ile)
OH-GT-36    güverte koşumu bitince durum satırı         status boşaltılıyor
            boşalıyor; kullanıcı "hiçbir şey olmadı"    → "Tamamlandı · N s"
            sanıyor                                      (``ac.run.done``)
==========  ==========================================  ===================

TERS-MUTASYON: her iddianın kırmızıya döndüğü ``a1/mutasyon.json``da
kayıtlıdır.
"""

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
KANIT = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D35' / 'kabuk-2' / 'a1'
OLC_JS = KANIT / 'olc.js'
ONCE_JSON = KANIT / 'once.json'

JS = REPO_ROOT / 'hrma' / 'static' / 'js'
CSS = REPO_ROOT / 'hrma' / 'static' / 'css'
SABLON = REPO_ROOT / 'hrma' / 'templates'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadı')


def oku(p):
    return pathlib.Path(p).read_text(encoding='utf-8')


def govde(src, ad):
    """``function <ad>(...) { … }`` gövdesini AYNEN döndürür (süslü eşleme)."""
    m = re.search(r'(?:async\s+)?function\s+%s\s*\(' % re.escape(ad), src)
    if not m:
        return None
    i = src.index('{', m.end() - 1)
    derinlik = 0
    for j in range(i, len(src)):
        c = src[j]
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
            if derinlik == 0:
                return src[m.start():j + 1]
    return None


def yorumsuz(js):
    """JS kaynağından yorumları atar — iddia KODU okumalı, yorumu değil.

    (Ters-mutasyon bunu ölçtü: `I18N.number` adı aynı işlevin AÇIKLAMA
    satırında da geçiyordu, dolayısıyla çağrı sökülse bile düz arama yeşil
    kalıyordu.)
    """
    js = re.sub(r'/\*.*?\*/', ' ', js, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', js)


def node(betik):
    res = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2500:]
    return json.loads(res.stdout)


@pytest.fixture(scope='module')
def taban():
    """Taban (onarım öncesi) ölçümü — kusurun GERÇEKTEN var olduğunun kaydı."""
    assert kanit_gerekli(ONCE_JSON).exists(), 'taban ölçümü yok: %s' % ONCE_JSON
    return json.loads(kanit_gerekli(ONCE_JSON).read_text(encoding='utf-8'))['olcumler']


@pytest.fixture(scope='module')
def olcum():
    """CANLI ölçüm: ölçüm betiği ÇALIŞAN ağaç üstünde yeniden koşturulur.

    ``sonra.json`` okunmaz — okunsaydı bekçi bir dosyayı değil bir kaydı
    korurdu ve kod geri alınsa bile yeşil kalırdı.
    """
    assert kanit_gerekli(OLC_JS).exists(), 'ölçüm betiği yok: %s' % OLC_JS
    with tempfile.NamedTemporaryFile('r', suffix='.json', delete=False) as f:
        hedef = f.name
    res = subprocess.run([NODE, kanit_gerekli(str(OLC_JS)), hedef], capture_output=True,
                         text=True, timeout=300, cwd=str(REPO_ROOT))
    assert res.returncode == 0, res.stderr[-2500:]
    return json.loads(pathlib.Path(hedef).read_text(encoding='utf-8'))['olcumler']


# ===========================================================================
# OH-GT-31 — güverte seçicileri seçili seçeneği kesiyordu
# ===========================================================================
class TestGT31SeciciKesik:

    def test_taban_kusuru_gerceklesti(self, taban):
        m = taban['M1_secici_kesik']
        assert m['fieldHtml_select_title_var_mi'] is False
        assert m['dock_select_ellipsis_kurali_var_mi'] is False
        assert m['grid_minmax_degerleri'] == [170]
        assert m['butceyi_asan_secenek_sayisi'] == 64, (
            'taban ölçümü değişmiş: bütçeyi aşan seçenek sayısı 64 değil %s'
            % m['butceyi_asan_secenek_sayisi'])

    def test_izgara_asgarisi_genisledi(self, olcum):
        m = olcum['M1_secici_kesik']
        assert m['grid_minmax_degerleri'] == [210], (
            'güverte bölüm ızgarasının asgari sütunu 210 px olmalı (170 px '
            'hücrede seçenek metinlerinin %64ü kesiliyordu — OH-GT-31)')

    def test_kesilen_secenek_sayisi_dustu(self, olcum, taban):
        assert (olcum['M1_secici_kesik']['butceyi_asan_secenek_sayisi']
                < taban['M1_secici_kesik']['butceyi_asan_secenek_sayisi'])

    def test_kirpma_kurali_var(self, olcum):
        assert olcum['M1_secici_kesik']['dock_select_ellipsis_kurali_var_mi'], (
            'sığmayan seçenek metni üç noktayla bitmeli (theme.css)')

    def test_fieldHtml_secili_secenegin_tam_metnini_title_yazar(self):
        """ÜRÜN KOŞUMU: ``fieldHtml`` node altında yalıtılıp koşturulur."""
        src = oku(JS / 'analysis_dock.js')
        parca = govde(src, 'fieldHtml')
        assert parca, 'fieldHtml bulunamadı'
        betik = """
'use strict';
function i18nAttr(k) { return k ? ' data-i18n="' + k + '"' : ''; }
function T(k, fb) { return k === 'x.uzun' ? 'Ters yönlü (çıkıştan odaya)' : fb; }
function escAttr(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function fieldDomId(p, f) { return 'ad_f_' + p + '_' + f; }
function fieldSourceSlotId(p, f) { return 'ad_src_' + p + '_' + f; }
""" + parca + """
var html = fieldHtml('t', ['yon', 'Yon', 'ters', [
    ['ayni', 'Ayni yonlu', null],
    ['ters', 'Ters yonlu "kacisli"', 'x.uzun']]]);
var sayi = fieldHtml('t', ['pc', 'Pc', 20, 0.1]);
process.stdout.write(JSON.stringify({
    select_html: html,
    title_var: /<select[^>]*\\stitle="/.test(html),
    title_degeri: (html.match(/title="([^"]*)"/) || [])[1] || null,
    sayi_alaninda_title: /<input[^>]*\\stitle="/.test(sayi)
}));
"""
        r = node(betik)
        assert r['title_var'], ('seçicinin `title` niteliği yok — seçili '
                               'seçeneğin TAM metni hiçbir yerden okunamıyor')
        assert r['title_degeri'] == 'Ters yönlü (çıkıştan odaya)', (
            'title seçili seçeneğin ÇEVRİLMİŞ tam metni olmalı, gelen: %r'
            % r['title_degeri'])
        assert not r['sayi_alaninda_title'], 'sayı alanına ipucu eklenmemeli'

    def test_secimIpucu_secim_degisince_tazeler_ve_fail_closed(self):
        """ÜRÜN KOŞUMU: ``secimIpucu`` gerçek bir seçici nesnesiyle koşar."""
        src = oku(JS / 'analysis_dock.js')
        parca = govde(src, 'secimIpucu')
        assert parca, 'secimIpucu bulunamadı'
        betik = parca + """
function sel(idx, metinler) {
    return { tagName: 'SELECT', selectedIndex: idx,
        options: metinler.map(function (t) { return { textContent: t }; }),
        attrs: {},
        setAttribute: function (k, v) { this.attrs[k] = v; },
        removeAttribute: function (k) { delete this.attrs[k]; },
        getAttribute: function (k) { return this.attrs[k] === undefined ? null : this.attrs[k]; } };
}
var a = sel(1, ['Bir', '  Ters yonlu (cikistan odaya)  ']);
secimIpucu(a);
var ilk = a.getAttribute('title');
a.selectedIndex = 0; secimIpucu(a);
var ikinci = a.getAttribute('title');
var bos = sel(-1, ['Bir']); bos.setAttribute('title', 'ESKI'); secimIpucu(bos);
var girdi = { tagName: 'INPUT', attrs: {},
    setAttribute: function (k, v) { this.attrs[k] = v; },
    removeAttribute: function (k) { delete this.attrs[k]; } };
secimIpucu(girdi);
process.stdout.write(JSON.stringify({
    ilk: ilk, ikinci: ikinci,
    secim_yoksa_title: bos.getAttribute('title'),
    girdiye_dokunmaz: Object.keys(girdi.attrs).length === 0
}));
"""
        r = node(betik)
        assert r['ilk'] == 'Ters yonlu (cikistan odaya)', r['ilk']
        assert r['ikinci'] == 'Bir', 'seçim değişince ipucu tazelenmiyor'
        assert r['secim_yoksa_title'] is None, (
            'fail-closed: seçili seçenek yoksa eski (artık yanlış) ipucu '
            'ekranda kalmamalı')
        assert r['girdiye_dokunmaz']


# ===========================================================================
# OH-GT-32 — "Yapısal Asgari EK" künyesi (SAHA DIŞI, ölçüm kaydı)
# ===========================================================================
class TestGT32KunyeSahaDisi:

    def test_kunye_app_js_de_kuruluyor(self, olcum):
        """Kalemin yeri ÖLÇÜLDÜ: ana model panels/structural_panel.js dedi,
        künyeyi kuran YER app.js. app.js bu dalgada sayi-bicimi kulvarınındır
        → onarım DEVREDİLDİ; bekçi yalnız yerin kaymadığını kilitler."""
        m = olcum['M2_kunye']
        assert m['kunye_kurucusu_dosya'] == 'hrma/static/js/app.js'
        assert m['structural_panel_de_calculate_kunyesi_var_mi'] is False
        assert m['tek_satir_zinciri'] is True, (
            'künye hâlâ tek " · " zinciri; satır satır kurulunca bu iddia '
            'düşer ve bekçi devrin yapıldığını söyler')
        # V301/DİL (NK-4, devir D1 yapıldı): künye satırları okunur cümleye
        # indi; ham `minimum_earned_safety_factor` / `binding` anahtarı kalmadı.
        assert 'minimum_earned_safety_factor' not in m['ham_anahtarlar']
        assert 'binding' not in m['ham_anahtarlar']


# ===========================================================================
# OH-GT-33 — büyütme birim simgelerini ve özel adları bozuyordu
# ===========================================================================
class TestGT33Buyutme:

    def test_taban_kusuru_gerceklesti(self, taban):
        m = taban['M3_buyutme']
        assert m['recent_strip_ad_ham_atama'] is True
        assert m['index_aux_link_uppercase'] is True
        assert m['merkez_etiket_uppercase'] is True
        assert m['theme_ac_field_kurali_var_mi'] is False
        assert m['tip_rozeti_tr_goruntu'] == 'LİQUİD'
        bozuk = {b['bozulan'][0] for b in m['proje_adi_bozulmalari']}
        assert 'simge kN→KN' in bozuk and 'simge mm→MM' in bozuk

    def test_merkez_etiketleri_artik_buyutulmuyor(self, olcum):
        assert olcum['M3_buyutme']['theme_ac_field_kurali_var_mi'], (
            'Analiz Merkezi alan etiketlerinin harf dönüşümü kapatılmalı — '
            'aksi hâlde "Summerfield k [-]" ekranda "SUMMERFİELD K [-]" '
            'olur (özel ad + simge bozulması, OH-GT-33)')
        kural = oku(CSS / 'theme.css')
        assert re.search(r'\.ac-field\s*>\s*label\s*\{[^}]*text-transform:\s*none',
                         kural), 'kural theme.css’te bulunamadı'

    def test_son_projeler_seridinde_ad_yazildigi_gibi(self):
        """ÜRÜN KOŞUMU: ``buildRecentStrip`` node altında koşturulur."""
        src = oku(JS / 'project_bar.js')
        parca = govde(src, 'buildRecentStrip')
        assert parca, 'buildRecentStrip bulunamadı'
        betik = """
'use strict';
function dugum(tag) {
    return { tag: tag, cocuk: [], style: {}, className: '', href: '', id: '',
        attrs: {}, textContent: '',
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        appendChild: function (c) { this.cocuk.push(c); return c; },
        insertBefore: function (c) { this.cocuk.push(c); return c; },
        querySelector: function () { return null; } };
}
var _kap = dugum('div');
global.document = {
    createElement: dugum,
    querySelector: function (s) { return s === '.container' ? _kap : null; }
};
global.window = global;
global.console = console;
var TYPE_PATH = { liquid: '/liquid', solid: '/solid', hybrid: '/hybrid' };
function T(k, fb) { return fb; }
function summaryMini() { return 'Isp 207.1 s'; }
async function apiList() {
    return [{ name: 'Example Liquid LOX-RP1 25kN', motor_type: 'liquid',
              results_summary: {} }];
}
""" + parca + """
buildRecentStrip().then(function () {
    var bolum = _kap.cocuk[0];
    var liste = bolum.cocuk[1];
    var a = liste.cocuk[0];
    var adEl = a.cocuk[0];
    process.stdout.write(JSON.stringify({
        a_sinifi: a.className,
        a_dogrudan_metni: a.textContent,
        ad_metni: adEl.textContent,
        ad_donusumu: adEl.style.textTransform || null,
        cocuk_sayisi: a.cocuk.length,
        tip_metni: (a.cocuk[1] || {}).textContent || null
    }));
});
"""
        r = node(betik)
        assert r['a_sinifi'] == 'aux-link'
        assert r['ad_metni'] == 'Example Liquid LOX-RP1 25kN', (
            'kullanıcının yazdığı ad DOM metninde bozulmuş: %r' % r['ad_metni'])
        assert r['ad_donusumu'] == 'none', (
            'ad `.aux-link`in `text-transform: uppercase` kuralının altında '
            'kalıyor — ekranda "EXAMPLE LİQUİD … 25KN" olur (OH-GT-33)')
        assert r['a_dogrudan_metni'] == '', (
            'ad hâlâ bağlantının kendi metni; kendi kabında olmalı')
        assert r['tip_metni'] == ' [LIQUID]'

    def test_proje_listesi_tip_rozeti_yerelden_bagimsiz(self):
        """ÜRÜN KOŞUMU: ``projectRow`` node altında koşturulur."""
        src = oku(JS / 'project_bar.js')
        parca = govde(src, 'projectRow')
        assert parca, 'projectRow bulunamadı'
        betik = """
'use strict';
function dugum(tag) {
    return { tag: tag, cocuk: [], style: { cssText: '' }, attrs: {},
        textContent: '',
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        addEventListener: function () {},
        appendChild: function (c) { this.cocuk.push(c); return c; } };
}
global.document = { createElement: dugum };
global.window = global;
function T(k, fb) { return fb; }
function nf(x) { return String(x); }
function srv(s) { return s; }
function toast() {}
function loadIntoPage() {}
function closeModal() {}
function summaryMini() { return ''; }
function TF(k, v, fb) { return fb; }
""" + parca + """
var row = projectRow({ name: 'Example Liquid', motor_type: 'liquid' });
var rozet = row.cocuk[1];
process.stdout.write(JSON.stringify({
    rozet_metni: rozet.textContent,
    rozet_stili: rozet.style.cssText,
    css_buyutme: rozet.style.cssText.indexOf('text-transform:uppercase') >= 0
}));
"""
        r = node(betik)
        assert r['rozet_metni'] == 'LIQUID', (
            'rozet metni ham enum ("liquid"); büyütme CSS’e bırakılırsa '
            'Türkçe kipte "LİQUİD" olur (OH-GT-33)')
        assert not r['css_buyutme'], (
            'rozet hâlâ CSS ile büyütülüyor — dile bağlı `i→İ` kuralı '
            'makine adını bozar')


# ===========================================================================
# OH-GT-34 — grafik yer tutucusu Türkçe kipte İngilizce
# ===========================================================================
class TestGT34YerTutucu:

    def test_taban_kusuru_gerceklesti(self, taban):
        m = taban['M4_yer_tutucu']
        assert m['en_kurali_var_mi'] is True
        assert m['tr_kurali_var_mi'] is False
        assert m['tr_metni'] is None

    def test_turkce_kural_var_ingilizce_bozulmadi(self, olcum):
        m = olcum['M4_yer_tutucu']
        assert m['tr_kurali_var_mi'], (
            'Türkçe arayüzde hesap öncesi grafik kabı hâlâ "NO DATA — RUN '
            'ANALYSIS TO GENERATE THIS PLOT" basıyor (OH-GT-34)')
        assert m['tr_metni'] == 'VERİ YOK — GRAFİK İÇİN ANALİZİ ÇALIŞTIRIN'
        assert m['en_kurali_var_mi'], 'İngilizce kural düşmemeli'
        assert m['kok_lang_ayarlaniyor_mu'], (
            'kural `html[lang="tr"]`e bağlı; kök `lang` yazılmazsa hiç '
            'eşleşmez')


# ===========================================================================
# OH-GT-35 — /launch-site kendi dil düğmeleri
# ===========================================================================
class TestGT35DilKanali:

    def test_taban_kusuru_gerceklesti(self, taban):
        m = taban['M5_dil_dugmeleri']
        assert m['data_lang_dugme_sayisi'] == 2
        assert m['setlang_dinleyici_sayisi'] == 1
        assert m['kabuk_kanali_yukleniyor_mu'] is True

    def test_sayfaya_ozel_dugmeler_kalkti(self, olcum):
        m = olcum['M5_dil_dugmeleri']
        assert m['data_lang_dugme_sayisi'] == 0, (
            '/launch-site hâlâ kendi EN/TR düğmeleriyle dil değiştiriyor '
            '(OH-GT-35)')
        assert m['ls_lang_kabi_var_mi'] is False
        assert m['setlang_dinleyici_sayisi'] == 0
        assert m['markLang_cagri_sayisi'] == 0, (
            'ölü kod: `markLang` çağrıları kaldı')

    def test_kabuk_kanali_ayakta(self, olcum):
        m = olcum['M5_dil_dugmeleri']
        assert m['kabuk_kanali_yukleniyor_mu'], (
            'düğmeler kaldırıldı ama kabuk dil kanalı (i18n_shell + '
            'settings_panel) bu sayfada yüklü değil — dil DEĞİŞTİRİLEMEZ')
        assert m['kabuk_serit_enjeksiyonu'], (
            'Ayarlar bağlantısı `#ls-topbar` şeridine enjekte edilmiyor')


# ===========================================================================
# OH-GT-36 — koşum bitince durum satırı boş kalıyordu
# ===========================================================================
class TestGT36BitisGeriBildirimi:

    def test_taban_kusuru_gerceklesti(self, taban):
        m = taban['M6_bitis_geri_bildirimi']
        assert m['basari_dalinda_status_bosaltiliyor_mu'] is True
        assert m['sure_olculuyor_mu'] is False

    def test_sure_olculuyor(self, olcum):
        assert olcum['M6_bitis_geri_bildirimi']['sure_olculuyor_mu']

    def test_basari_dalinda_durum_satiri_dolu(self):
        """ÜRÜN KOŞUMU: ``runPanel`` node altında sahte uçla koşturulur."""
        src = oku(JS / 'analysis_dock.js')
        parca = govde(src, 'runPanel')
        assert parca, 'runPanel bulunamadı'
        betik = """
'use strict';
function dugum(id) {
    return { id: id, textContent: '', disabled: false, innerHTML: '',
        style: { display: '' }, querySelectorAll: function () { return []; } };
}
var _d = { ad_status_t: dugum('s'), ad_root_t: dugum('r'), ad_run_t: dugum('b') };
global.document = { getElementById: function (k) { return _d[k] || null; } };
global.window = global;
global.performance = { now: (function () { var t = 0; return function () { t += 1234; return t; }; })() };
global.fetch = function () {
    return Promise.resolve({ ok: true, status: 200,
        text: function () { return Promise.resolve('{"status":"ok"}'); } });
};
var blockedSelects = {};
var lastData = {};
function T(k, fb) { return fb; }
function TF(k, v, fb) {
    return String(fb).replace(/\\{(\\w+)\\}/g, function (_, n) { return v[n]; });
}
function buildPayload() { return { payload: { a: 1 }, missing: [] }; }
function readJsonBody(r) { return r.text().then(JSON.parse); }
function ucRedMetni(d, s) { return 'HTTP ' + s; }
function purgePlots() {}
function secimIpuclariniTazele() {}
""" + parca + """
var spec = { id: 't', endpoint: '/x', render: function () {} };
runPanel(spec).then(function () {
    process.stdout.write(JSON.stringify({
        status_metni: _d.ad_status_t.textContent,
        root_gorunur: _d.ad_root_t.style.display,
        dugme_serbest: _d.ad_run_t.disabled === false
    }));
});
"""
        r = node(betik)
        assert r['root_gorunur'] == 'block'
        assert r['dugme_serbest']
        assert r['status_metni'], (
            'koşum başarıyla bittiğinde durum satırı BOŞ kalıyor — kullanıcı '
            '"hiçbir şey olmadı" sanıyor (OH-GT-36)')
        assert 'Completed' in r['status_metni'], (
            'bitiş iletisi bulunamadı: %r' % r['status_metni'])
        assert re.search(r'\d', r['status_metni']), (
            'bitiş iletisi süreyi taşımalı: %r' % r['status_metni'])

    def test_bitis_iletisi_yeni_anahtar_icat_etmiyor(self):
        """TEK KAYNAK: Analiz Merkezi'nin bitiş cümlesi yeniden kullanılır."""
        src = oku(JS / 'analysis_dock.js')
        assert "'ac.run.done'" in src, (
            'bitiş iletisi mevcut `ac.run.done` anahtarına bağlanmalı')
        sozluk = oku(JS / 'i18n_common.js')
        assert "'ac.run.done': 'Completed in {seconds} s.'" in sozluk
        assert "'ac.run.done': '{seconds} sn içinde tamamlandı.'" in sozluk

    def test_ondalik_ayraci_tek_kaynaktan(self):
        src = oku(JS / 'analysis_dock.js')
        parca = yorumsuz(govde(src, 'runPanel'))
        assert 'I18N.number(' in parca, (
            'süre sayısı `I18N.number` kanonundan geçmeli (ondalık ayracı '
            'iki yerde yazılmaz)')
