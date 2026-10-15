"""Güncelleme penceresindeki sürüm notu, arayüz diliyle aynı dilde olmalı.

Berke'nin saha bildirimi (2026-07-29): "sürüm notları kısmında ben Türkçe
güncelleme var yazısı aldığımda sürüm notları İngilizce."

Bu dosya "yazılmış mı" değil "çalışıyor mu" testidir: hrma/static/js/
update_check.js gerçek node içinde, sahte bir DOM ve GERÇEK i18n sözlüğüyle
yüklenir, /api/update/check yanıtı taklit edilir ve KULLANICININ GÖRDÜĞÜ
pencere okunur. Not gövdeleri uydurulmaz — depodaki gerçek yayın notu
dosyası (packaging/release_notes_v*.md) kullanılır.

Kapsanan üç taşıma biçimi (update_check.js'teki açıklamayla aynı sıra):
  1. Sunucu dile ayrılmış alan gönderir (notes_tr / notes_en)
  2. Gövde <!--HRMA-LANG:xx--> imlerini taşır (GitHub API yolu)
  3. İm yok ama gövde iki dilli (Atom yedek yolu; GitHub'ın ürettiği HTML
     yorum satırlarını içermez — 2026-07-29'da canlı akışta ölçüldü)

SUNUCU TARAFINDAKİ KÖK NEDEN (ayrı yama):
hrma/utils/update_checker.py gövdeyi `[:4000]` ile TEK PARÇA kırpıyor.
Yayımlanmış v2.6.25 gövdesi 16045 karakter ve Türkçe im 8072. indekste
başlıyor; kırpma Türkçe bölümü tamamen atıyor, istemciye hiç ulaşmıyor.
Sunucu bölümlere AYIRDIKTAN sonra kırpmadıkça (notes_tr / notes_en) hiçbir
istemci düzeltmesi bunu kurtaramaz. Dosyadaki son bölüm o sözleşmeyi
sınar.

ÖH D24 / OH-D23-11 (a): bu künye eskiden son bölümün yama gelene
kadar ATLANDIĞINI söylüyordu ve BAYATTI — o kapı ÖH D18 / P13B1-09
ile kaldırılmıştı (kendini kapatan bekçi), sunucu yaması uygulandı.
Ölçüldü (once_ohd23_11.json): ``split_notes_by_language`` var,
koşullu kapılı test sayısı 0. Var olmayan bir kapıyı anlatan künye
okuyucuya "bu bölüm belki atlanıyordur" dedirtir; bölüm ATLANMIYOR,
sözleşme her koşumda SINANIYOR.

ÖH D33-2 / OH-UC-13: buradaki 8 node bekçisi bir süre kırmızıydı ve
kırmızıyı DOĞRUDAN doğuran şey SÜRÜCÜYDÜ — sahte DOM `<script src=…>`
ögesini head'e alıp hiç çalıştırmıyordu, oysa `update_check.js` D30/OH-D21-06'dan beri
ortak sözlüğü TALEP ÜZERİNE indirip pencereyi ancak o geri çağrımda
çiziyor. Sürücü artık tarayıcı sözleşmesini taklit eder (ayrıntı
`HARNESS_JS` künyesinde) ve sayfa modelini iki kiple sınar:
`lazy` (launch_site/liquid/solid — ortak sözlük sayfada yok) ve
`onceden` (index/formulas — sözlük sayfayla gelir). Sürücü düzelince
ortaya çıkan GERÇEK ürün kusuru (`force` akışında pencerenin sözlük
inmeden İngilizce çizilmesi) aynı dalgada onarıldı; davranış bekçisi
`tests/test_d33_altyapi_a1.py`nin son bölümündedir.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_JS = os.path.join(ROOT, 'hrma', 'static', 'js')
UPDATE_JS = os.path.join(STATIC_JS, 'update_check.js')
I18N_JS = os.path.join(STATIC_JS, 'i18n.js')
I18N_COMMON_JS = os.path.join(STATIC_JS, 'i18n_common.js')

TR_LETTERS = re.compile(r'[çğıİöşüÇĞÖŞÜ]')
MARKER = re.compile(r'<!--\s*HRMA-LANG:([a-z]{2})\s*-->', re.I)

#: ÖH D24 / OH-D23-11 (b): bu kapı MODÜL düzeyindeydi
#: (``pytestmark``) ve node yoksa dosyadaki HER şeyi atlıyordu —
#: node'a hiç dokunmayan 5 saf-Python sözleşme testi dâhil
#: (ölçüm: once_ohd23_11.json ``node_GEREKTIRMEYEN_testler``).
#: Bunların arasında P13B1-09'un "yama geri alınamaz" bekçisi de
#: vardı: node kurulu olmayan bir makinede sunucu yaması sessizce
#: geri alınabilirdi ve hiçbir test kırmızıya dönmezdi. Kapı artık
#: yalnız node ÇALIŞTIRAN testlerin üstünde durur; saf-Python
#: sözleşmesi her makinede sınanır (fail-closed).
node_gerekir = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node kurulu değil (bu test '
                                         'update_check.js\'i gerçek node '
                                         'içinde çalıştırır)')


# ---------------------------------------------------------------------------
# Gerçek yayın notu (uydurma metin yok)
# ---------------------------------------------------------------------------
def _newest_release_notes():
    """Depodaki en yeni packaging/release_notes_v<sürüm>.md dosyasını okur."""
    pkg = os.path.join(ROOT, 'packaging')
    adaylar = []
    for name in os.listdir(pkg):
        m = re.match(r'release_notes_v(\d[\d.]*)\.md$', name)
        if m:
            surum = tuple(int(p) for p in m.group(1).split('.'))
            adaylar.append((surum, os.path.join(pkg, name)))
    assert adaylar, 'packaging/ içinde yayın notu dosyası yok'
    with open(max(adaylar)[1], encoding='utf-8') as fh:
        return fh.read()


def _bolumler(notlar):
    """İm işaretli notu {'en': ..., 'tr': ...} sözlüğüne ayırır."""
    parcalar = MARKER.split(notlar)
    return {parcalar[i].lower(): parcalar[i + 1].strip()
            for i in range(1, len(parcalar) - 1, 2)}


NOTLAR = _newest_release_notes()
BOLUM = _bolumler(NOTLAR)


def test_yayin_notu_iki_dilli_kaynak_olarak_okunabiliyor():
    """Testlerin dayandığı gerçek veri gerçekten iki dilli olmalı."""
    assert set(BOLUM) == {'en', 'tr'}, (
        'yayın notunda iki dil imi yok: %s' % sorted(BOLUM))
    assert not TR_LETTERS.search(BOLUM['en']), 'EN bölümünde Türkçe harf var'
    assert len(TR_LETTERS.findall(BOLUM['tr'])) >= 3, 'TR bölümü Türkçe değil'


# ---------------------------------------------------------------------------
# node koşum takımı: update_check.js'i sahte DOM içinde gerçekten çalıştırır
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

/* ÖH D33-2 · OH-UC-13 — SAHTE DOM ARTIK BETİK YÜKLER.
   ÖLÇÜLDÜ (a1/once_ohuc13.json): bu sürücü `<script src=…>` ögesini
   head'e alıyor ama HİÇ çalıştırmıyordu; ne `onload` ne `onerror`
   ateşleniyordu (head_script_sayisi=1, onload_atesledi=false,
   onerror_atesledi=false). ÖH D30 / OH-D21-06 ile `update_check.js`
   ortak sözlüğü TALEP ÜZERİNE yüklemeye başlayınca (`sozlukHazir`)
   pencere ancak o geri çağrımdan sonra çiziliyor; geri çağrım hiç
   ateşlenmediği için 8 node bekçisi "modal açılmadı" diye kırmızıya
   düşüyordu. Kusur üründe değil, sürücünün eksik tarayıcı taklidindeydi.

   Tarayıcı sözleşmesi buraya taşındı: DOM'a giren `<script src>` kaynağı
   GERÇEKTEN diskten okunur (Flask'ın `/static/js` yolunun karşılığı),
   bağlamda çalıştırılır, sonra `onload` ateşlenir; dosya yoksa `onerror`.
   Metin uydurulmaz — çalıştırılan dosya depodaki dosyanın ta kendisidir. */
let STATIC_DIR = null;      // argv çözülünce dolar
let VM_CTX = null;          // vm.createContext'ten sonra dolar
const YUKLENEN = [];        // gerçekten çalıştırılan <script src> listesi

function betigiYukle(el) {
    const src = String(el.src || (el.getAttribute && el.getAttribute('src')) || '');
    if (!src) return;
    setTimeout(function () {
        let kod = null, yol = null;
        try {
            yol = path.join(STATIC_DIR || '', src.replace(/^.*\/static\/js\//, ''));
            kod = fs.readFileSync(yol, 'utf8');
        } catch (e) { kod = null; }
        if (kod === null || !VM_CTX) {
            if (typeof el.onerror === 'function') el.onerror({ type: 'error', target: el });
            return;
        }
        try {
            vm.runInContext(kod, VM_CTX, { filename: path.basename(yol) });
            YUKLENEN.push(src);
            if (typeof el.onload === 'function') el.onload({ type: 'load', target: el });
        } catch (e) {
            if (typeof el.onerror === 'function') el.onerror({ type: 'error', target: el });
        }
    }, 0);
}

// --- ARGV BLOGU BASLANGIC (DOM sondası bu bloğu atlar) ---
const [updateJs, i18nJs, i18nCommonJs, payloadPath, lang, sozlukKipiArg] =
    process.argv.slice(2);
// 'lazy'   : launch_site/liquid/solid — ortak sözlük sayfada YOK, pencere
//            onu kendi ister (ÖH D30 / OH-D21-06'nın canlı yolu).
// 'onceden': index/formulas — ortak sözlük sayfayla birlikte gelir,
//            `sozlukHazir` erken dönüş dalını kullanır.
const sozlukKipi = sozlukKipiArg || 'lazy';
STATIC_DIR = path.dirname(i18nCommonJs);
const info = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
// --- ARGV BLOGU BITIS ---

function El(tag) {
    this.nodeType = 1;
    this.tagName = (tag || 'div').toUpperCase();
    this._attrs = {};
    this.style = {};
    this.children = [];
    this.textContent = '';
    this.innerHTML = '';
    this.id = '';
    this.className = '';
    this._listeners = {};
}
El.prototype.getAttribute = function (k) {
    if (Object.prototype.hasOwnProperty.call(this._attrs, k)) return this._attrs[k];
    // `tag.src = …` biçiminde DOM ÖZELLİĞİNE yazılan URL alanları tarayıcıda
    // özniteliğe de yansır; yalnız bu iki alan yansıtılır (id/className gibi
    // her zaman dolu alanlar yansıtılsaydı `[id]` seçicisi her ögeyi tutardı).
    if ((k === 'src' || k === 'href') && typeof this[k] === 'string') return this[k];
    return null;
};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.appendChild = function (c) {
    this.children.push(c);
    // ÖH D33-2 · OH-UC-13: tarayıcıda DOM'a giren betik ÇALIŞIR.
    if (c && c.tagName === 'SCRIPT') betigiYukle(c);
    return c;
};
El.prototype.removeChild = function (c) {
    const i = this.children.indexOf(c);
    if (i >= 0) this.children.splice(i, 1);
    return c;
};
El.prototype.remove = function () {};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.descendants = function () {
    let out = [];
    this.children.forEach(function (c) {
        out.push(c);
        if (c.descendants) out = out.concat(c.descendants());
    });
    return out;
};
/* ÖH D33-2 · OH-UC-13: seçici dilbilgisi `tag[attr]`den `[attr*="değer"]`e
   genişletildi. ÖLÇÜLDÜ (once_ohuc13.json: secici_attr_contains_eslesti=false):
   eski dilbilgisi `script[src*="i18n_common.js"]`i TANIMIYORDU; ürünün
   "sözlük zaten sayfada" erken dönüş dalı bu seçiciye bağlı olduğu için o
   dal hiçbir koşumda sınanamıyordu (bekçi körlüğü). */
El.prototype.matches = function (sel) {
    const self = this;
    return String(sel).split(',').some(function (part) {
        part = part.trim();
        const m = part.match(/^(\w+)?\[([\w-]+)(?:([*^$~|]?=)\s*"?([^"\]]*)"?)?\]$/);
        if (!m) return false;
        if (m[1] && self.tagName !== m[1].toUpperCase()) return false;
        const v = self.getAttribute(m[2]);
        if (v === null || v === undefined) return false;
        if (!m[3]) return true;                       // yalnız varlık sınaması
        const hedef = m[4];
        if (m[3] === '=') return v === hedef;
        if (m[3] === '*=') return v.indexOf(hedef) >= 0;
        if (m[3] === '^=') return v.indexOf(hedef) === 0;
        if (m[3] === '$=') return hedef.length <= v.length &&
                                  v.lastIndexOf(hedef) === v.length - hedef.length;
        return false;                                  // ~= / |= kullanılmıyor
    });
};
El.prototype.querySelectorAll = function (sel) {
    return this.descendants().filter(function (e) {
        return e.matches && e.matches(sel);
    });
};
El.prototype.querySelector = function (sel) { return this.querySelectorAll(sel)[0] || null; };

const body = new El('body');
const head = new El('head');
const document = {
    nodeType: 9,
    readyState: 'complete',
    documentElement: new El('html'),
    head: head,
    body: body,
    createElement: function (tag) { return new El(tag); },
    createTextNode: function (text) {
        return { nodeType: 3, textContent: String(text), children: [] };
    },
    getElementById: function (id) {
        return body.descendants().filter(function (e) { return e.id === id; })[0] || null;
    },
    addEventListener: function () {},
    dispatchEvent: function () { return true; },
    // ÖH D33-2: sayfa betikleri <head>'te yaşar; arama gövdeyle sınırlı kalamaz.
    querySelectorAll: function (sel) {
        return head.querySelectorAll(sel).concat(body.querySelectorAll(sel));
    },
    querySelector: function (sel) { return document.querySelectorAll(sel)[0] || null; }
};

const store = { hrma_update_autocheck: 'off' };   // otomatik denetim kapalı: koşum belirlenimci
const istekler = [];
const win = {
    document: document,
    console: { warn: function () {}, log: function () {}, error: function () {} },
    localStorage: {
        getItem: function (k) {
            return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
        },
        setItem: function (k, v) { store[k] = String(v); },
        removeItem: function (k) { delete store[k]; }
    },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    WeakMap: WeakMap,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    addEventListener: function () {},
    open: function () {},
    fetch: function (url) {
        istekler.push(String(url));
        if (String(url) === '/api/update/check') {
            return Promise.resolve({ json: function () { return Promise.resolve(info); } });
        }
        return Promise.reject(new Error('beklenmeyen istek: ' + url));
    }
};
win.window = win;
win.self = win;
vm.createContext(win);
VM_CTX = win;

// Her şablonun kendi yüklediği çeviri altyapısı
vm.runInContext(fs.readFileSync(i18nJs, 'utf8'), win, { filename: 'i18n.js' });

function sayfayiKur(devam) {
    if (sozlukKipi !== 'onceden') { devam(); return; }
    const s = document.createElement('script');
    s.src = '/static/js/i18n_common.js';
    s.onload = function () { devam(); };
    s.onerror = function () { devam(); };
    document.head.appendChild(s);
}

sayfayiKur(function () {
    win.I18N.setLang(lang);
    vm.runInContext(fs.readFileSync(updateJs, 'utf8'), win, { filename: 'update_check.js' });
    win.hrmaCheckForUpdates(true);

    // Pencere, sözlük geldikten SONRA çizilir: sabit gecikme yerine bekle.
    const bitis = Date.now() + 15000;
    (function bekle() {
        const modal = document.getElementById('hrma-update-modal');
        if (!modal) {
            if (Date.now() < bitis) { setTimeout(bekle, 10); return; }
            console.log(JSON.stringify({ ok: false, reason: 'modal açılmadı',
                                         istekler: istekler, yuklenen_betikler: YUKLENEN }));
            return;
        }
        const box = modal.children[0];
        const metinler = box.descendants()
            .concat(box.children)
            .map(function (e) { return String(e.textContent || ''); })
            .filter(function (s) { return s.trim().length > 0; });
        metinler.sort(function (a, b) { return b.length - a.length; });
        console.log(JSON.stringify({
            ok: true,
            lang: win.I18N.lang,
            sozluk_kipi: sozlukKipi,
            baslik: String(box.children[0].innerHTML || ''),
            soru: String(box.children[1].innerHTML || ''),
            notlar: metinler.length ? metinler[0] : '',
            istekler: istekler,
            yuklenen_betikler: YUKLENEN
        }));
    })();
});
"""


#: Sayfa modeli — ortak sözlüğün (i18n_common.js) sayfaya nasıl geldiği.
#: ÖLÇÜLDÜ (a1/once_ohuc13.json, şablon taraması): `update_check.js`i yükleyen
#: 6 şablonun 3'ü (launch_site, liquid, solid) `i18n_common.js`i YÜKLEMEZ —
#: pencere sözlüğü kendi ister (``lazy``); 3'ü (index, formulas, advanced)
#: sayfayla birlikte getirir (``onceden``). İki yol da canlıdır, ikisi de
#: sınanır.
SOZLUK_KIPLERI = ('lazy', 'onceden')


def _pencereyi_ac(info, lang, sozluk='lazy'):
    """update_check.js'i node içinde çalıştırır, açılan pencereyi döndürür."""
    assert sozluk in SOZLUK_KIPLERI, sozluk
    with tempfile.TemporaryDirectory() as tmp:
        driver = os.path.join(tmp, 'driver.js')
        payload = os.path.join(tmp, 'payload.json')
        with open(driver, 'w', encoding='utf-8') as fh:
            fh.write(HARNESS_JS)
        with open(payload, 'w', encoding='utf-8') as fh:
            json.dump(info, fh, ensure_ascii=False)
        proc = subprocess.run(
            [shutil.which('node'), driver, UPDATE_JS, I18N_JS, I18N_COMMON_JS,
             payload, lang, sozluk],
            capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, 'node koşumu çöktü:\n%s' % proc.stderr
    sonuc = json.loads(proc.stdout.strip().splitlines()[-1])
    assert sonuc['ok'], 'güncelleme penceresi açılmadı: %s' % sonuc
    return sonuc


def _bilgi(**ekstra):
    """/api/update/check yanıtının şeması (update_checker.check_for_update)."""
    info = {'available': True, 'current': '2.6.2', 'latest': 'v2.6.25',
            'notes': '', 'page_url': 'https://github.com/berketez/HRMA/releases/latest',
            'asset': None, 'error': None, 'error_kind': None, 'source': 'api'}
    info.update(ekstra)
    return info


# ---------------------------------------------------------------------------
# 2. biçim — GitHub API gövdesi, dil imleri yerinde
# ---------------------------------------------------------------------------
@node_gerekir
def test_turkce_arayuzde_notlar_turkce_gelir():
    """Kullanıcının bildirdiği durum: soru Türkçe ise not da Türkçe olmalı."""
    sonuc = _pencereyi_ac(_bilgi(notes=NOTLAR), 'tr')
    assert sonuc['lang'] == 'tr'
    # Arayüz gerçekten Türkçe (sözlükten gelen başlık)
    assert 'GÜNCELLEME MEVCUT' in sonuc['baslik'], sonuc['baslik']
    # ve notlar da Türkçe bölümün ta kendisi
    assert sonuc['notlar'].strip() == BOLUM['tr'], (
        'Türkçe arayüzde İngilizce/karışık not gösterildi:\n%s'
        % sonuc['notlar'][:400])


@node_gerekir
def test_ingilizce_arayuzde_notlar_ingilizce_gelir():
    sonuc = _pencereyi_ac(_bilgi(notes=NOTLAR), 'en')
    assert sonuc['lang'] == 'en'
    assert 'UPDATE AVAILABLE' in sonuc['baslik'], sonuc['baslik']
    assert sonuc['notlar'].strip() == BOLUM['en'], (
        'İngilizce arayüzde Türkçe/karışık not gösterildi:\n%s'
        % sonuc['notlar'][:400])


@node_gerekir
def test_notlarda_dil_imi_kullaniciya_sizmaz():
    """<!--HRMA-LANG:tr--> gibi makine imleri metinde görünmemeli."""
    for lang in ('tr', 'en'):
        sonuc = _pencereyi_ac(_bilgi(notes=NOTLAR), lang)
        assert 'HRMA-LANG' not in sonuc['notlar'], (
            '%s arayüzünde dil imi kullanıcıya gösteriliyor' % lang)


# ---------------------------------------------------------------------------
# 3. biçim — Atom yedek yolu: imler yok, gövde yine iki dilli
# ---------------------------------------------------------------------------
# GitHub'ın ürettiği HTML (releases.atom) yorum satırlarını içermez; sunucudaki
# etiket temizliği de aynı imleri silerdi. Kota dolduğunda güncelleme notu bu
# yoldan gelir, yani im YOKKEN iki dilli metin gelir.
IMSIZ = MARKER.sub('', NOTLAR)


@node_gerekir
def test_imsiz_iki_dilli_govdede_de_turkce_secilir():
    """Kota yedeği (Atom) yolunda da Türkçe arayüz Türkçe not görmeli."""
    sonuc = _pencereyi_ac(_bilgi(notes=IMSIZ, source='page'), 'tr')
    notlar = sonuc['notlar']
    assert len(TR_LETTERS.findall(notlar)) >= 3, (
        'im yok diye tüm gövde (önce İngilizce) gösterildi:\n%s' % notlar[:400])
    # İngilizce bölümün ilk satırı sızmamalı
    en_baslik = BOLUM['en'].splitlines()[0].strip()
    assert en_baslik not in notlar, (
        'Türkçe not içinde İngilizce bölüm var: %r' % en_baslik)
    assert BOLUM['tr'].splitlines()[0].strip() in notlar


@node_gerekir
def test_imsiz_govdede_ingilizce_arayuz_ingilizce_gorur():
    sonuc = _pencereyi_ac(_bilgi(notes=IMSIZ, source='page'), 'en')
    notlar = sonuc['notlar']
    assert not TR_LETTERS.search(notlar), (
        'İngilizce arayüzde Türkçe bölüm sızdı:\n%s' % notlar[:400])


# ---------------------------------------------------------------------------
# 1. biçim — sunucu dile ayrılmış alan gönderirse o kazanır
# ---------------------------------------------------------------------------
@node_gerekir
def test_sunucunun_ayirdigi_alan_kirpik_govdeyi_yener():
    """Sunucu kırpmadan ÖNCE bölerse istemci doğru dili göstermeli.

    Gövde alanı burada bilerek sunucunun bugünkü davranışıdır: iki dilli
    metnin ilk 4000 karakteri (yalnız İngilizce). notes_tr geldiğinde
    pencere o kırpık İngilizceyi DEĞİL Türkçe bölümü göstermeli.
    """
    info = _bilgi(notes=NOTLAR[:4000], notes_en=BOLUM['en'], notes_tr=BOLUM['tr'])
    sonuc = _pencereyi_ac(info, 'tr')
    assert sonuc['notlar'].strip() == BOLUM['tr'], sonuc['notlar'][:400]

    sonuc_en = _pencereyi_ac(info, 'en')
    assert sonuc_en['notlar'].strip() == BOLUM['en'], sonuc_en['notlar'][:400]


# ---------------------------------------------------------------------------
# Dürüst yedek: tek dilli not gizlenmez
# ---------------------------------------------------------------------------
@node_gerekir
def test_tek_dilli_not_gizlenmez():
    """Eski/elle yazılmış tek dilli notlar Türkçe arayüzde de gösterilir.

    Elde başka metin yok; saklamak kullanıcıyı bilgisiz bırakır. (Yanına
    'bu not yalnızca İngilizce mevcut' etiketi eklenmesi için gereken i18n
    anahtarları raporda listelendi.)
    """
    sonuc = _pencereyi_ac(_bilgi(notes=BOLUM['en']), 'tr')
    assert sonuc['notlar'].strip() == BOLUM['en'].strip(), (
        'tek dilli not bölünüp parçalanmış:\n%s' % sonuc['notlar'][:400])


@node_gerekir
def test_not_yoksa_pencere_yine_acilir():
    """Not gövdesi boş gelse bile güncelleme penceresi çalışmalı."""
    sonuc = _pencereyi_ac(_bilgi(notes=''), 'tr')
    assert 'GÜNCELLEME MEVCUT' in sonuc['baslik']


# ---------------------------------------------------------------------------
# Sunucu sözleşmesi — dosya başlığındaki kök neden
# ---------------------------------------------------------------------------
# Gövdeyi tek parça kırpmak Türkçe bölümü düşürüyor. Sunucu bölümlere
# ayırdıktan sonra kırpınca (split_notes_by_language + notes_en/notes_tr)
# aşağıdaki testler bu sözleşmeyi kilitler.
#
# ÖH D18 · P13B1-09 — BEKÇİ YÖNÜ TERSTİ (kendini kapatan bekçi).
# Buradaki bekçi eskiden ``@pytest.mark.skipif(not SUNUCU_AYIRIYOR, …)``
# ile korunuyordu. O kapı, tam da bekçinin koruduğu REGRESYON
# gerçekleştiğinde (``split_notes_by_language`` kaybolduğunda) testi
# KIRMIZI yapmak yerine ATLIYORDU: yani kusur ortaya çıkınca bekçi kendi
# kendini kapatıyordu. Üstelik atlama gerekçesi ("sunucu yaması yok:
# update_checker gövdeyi hâlâ tek parça kırpıyor") bugün YALANDI —
# ölçüldü (D18): ``hasattr(update_checker, 'split_notes_by_language')``
# True, dosya 12 geçti / 0 atlandı. Kapı, var olmayan bir geçmişi
# beklerken gelecekteki gerilemeyi affediyordu.
#
# Kapı KALDIRILDI ve yerine ADLI bir sözleşme iddiası kondu: yamanın
# varlığı artık bir ön koşul değil, SINANAN bir gerçektir.
def _update_checker():
    from hrma.utils import update_checker
    return update_checker


def test_sunucu_dil_ayirma_yamasi_geri_alinamaz():
    """``split_notes_by_language`` sözleşmenin parçasıdır, seçenek değil.

    P13B1-09: bu iddia olmasaydı, işlevin kaldırılması aşağıdaki bekçiyi
    kırmızıya değil ATLAMAYA düşürürdü — kusur sessizce geçerdi.
    """
    uc = _update_checker()
    assert hasattr(uc, 'split_notes_by_language'), (
        'update_checker.split_notes_by_language kayboldu: sunucu gövdeyi '
        'yine tek parça kırpıyor, Türkçe bölüm istemciye ulaşmıyor '
        '(v2.6.2 CORS hatasıyla aynı sınıf gerileme)')
    assert callable(uc.split_notes_by_language)


def test_sunucu_dil_bolumlerini_ayri_gonderir(monkeypatch):
    """check_for_update, notları dile ayırıp bölüm başına kırpmalı."""
    uc = _update_checker()
    monkeypatch.setattr(uc, '_fetch_latest_release',
                        lambda timeout_s=8: {'tag_name': 'v999.0.0',
                                             'draft': False, 'prerelease': False,
                                             'assets': [], 'body': NOTLAR,
                                             'html_url': ''})
    with uc._cache_lock:
        uc._cache.update(checked_at=0.0, result=None)
    try:
        r = uc.check_for_update(force=True)
    finally:
        with uc._cache_lock:
            uc._cache.update(checked_at=0.0, result=None)

    assert r['notes_tr'].strip() == BOLUM['tr'], 'Türkçe bölüm eksik/kırpık'
    assert r['notes_en'].strip() == BOLUM['en'], 'İngilizce bölüm eksik/kırpık'
    # Sahadaki v2.6.25 penceresi yalnız 'notes' alanını okur ve kendi dilini
    # imlerden ayıklar; iki im de bu alanda kalmalı.
    for dil in ('en', 'tr'):
        assert '<!--HRMA-LANG:%s-->' % dil in r['notes'], (
            '%s imi eski istemciler için korunmamış' % dil)


# ---------------------------------------------------------------------------
# Kırpma sessiz olmamalı (Faz 6 / 3 Ağustos 2026)
# ---------------------------------------------------------------------------
#
# Ölçülen arıza: ``NOTES_MAX_CHARS`` 4000'di ve gerçek sürüm notları bunun iki
# katıydı (v2.6.26: 8161 en / 7774 tr; depodaki en büyük tarihsel bölüm 8929).
# Kırpma düz ``metin[:limit]`` olduğu için Türkçe bölüm 3989. karakterde,
# "göndermiyordu" kelimesinin ORTASINDA kesiliyordu ve kullanıcıya kesildiğine
# dair hiçbir işaret verilmiyordu. Yarım cümleyi notun tamamı sanmak, bu
# sürümün kapattığı "ekran veriden fazlasını söylüyor" sınıfının aynısı.

def test_gercek_surum_notu_sinira_sigar():
    """Depodaki en büyük dil bölümü sınırın altında kalmalı.

    Sınır yükü bağlamak içindir, notu budamak için değil. Gerçek bir sürüm
    notu sınırı aşıyorsa sınır yanlıştır.
    """
    import glob

    from hrma.utils import update_checker as uc

    en_buyuk, nerede = 0, ''
    for yol in glob.glob(str(_paket_kok() / 'release_notes_v*.md')):
        with open(yol, encoding='utf-8') as f:
            govde = f.read()
        bolumler = uc.split_notes_by_language(govde) or {'?': govde}
        for kod, metin in bolumler.items():
            if len(metin) > en_buyuk:
                en_buyuk, nerede = len(metin), '%s[%s]' % (yol.split('/')[-1], kod)
    assert en_buyuk <= uc.NOTES_MAX_CHARS, (
        'en büyük sürüm notu bölümü (%s, %d karakter) NOTES_MAX_CHARS=%d '
        'sınırını aşıyor — kullanıcı notun bir kısmını hiç görmez'
        % (nerede, en_buyuk, uc.NOTES_MAX_CHARS))


def test_kirpma_satir_sinirinda_ve_beyanli():
    """Sınır aşılırsa kelime ortasında kesilmemeli ve kesildiği yazmalı."""
    from hrma.utils import update_checker as uc

    with open(_paket_kok() / 'release_notes_v2.6.26.md', encoding='utf-8') as f:
        govde = f.read()

    kirpik = uc.clip_notes(govde, limit=1200)
    bolumler = uc.split_notes_by_language(kirpik)
    assert set(bolumler) == {'en', 'tr'}, 'kırpma dil bölümlerini düşürmüş'

    for kod, metin in bolumler.items():
        assert len(metin) <= 1200, '%s bölümü sınırı aşıyor: %d' % (kod, len(metin))
        im = uc.NOTES_CLIP_MARK_TR if kod == 'tr' else uc.NOTES_CLIP_MARK_EN
        assert metin.endswith(im.strip()), (
            '%s bölümü kırpıldığı hâlde beyan taşımıyor; son 40: %r'
            % (kod, metin[-40:]))
        govde_kismi = metin[:-len(im.strip())].rstrip()
        # Satır ya da boşluk sınırında kesilmiş olmalı: kesilen yerin hemen
        # ardından gelen karakter kaynakta boşluk/satır sonu olmalı.
        assert govde_kismi, '%s bölümü tamamen boşaltılmış' % kod
        kaynak = bolumler_kaynak(govde)[kod]
        ard = kaynak[len(govde_kismi):len(govde_kismi) + 1]
        assert ard in ('', ' ', '\n'), (
            '%s bölümü kelime ortasında kesilmiş: ...%r|%r...'
            % (kod, govde_kismi[-25:], ard))


def bolumler_kaynak(govde):
    from hrma.utils import update_checker as uc
    return uc.split_notes_by_language(govde)


def _paket_kok():
    import pathlib
    return pathlib.Path(__file__).resolve().parents[1] / 'packaging'
