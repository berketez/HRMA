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
sınar ve yama uygulanınca KENDİLİĞİNDEN etkinleşir (o güne kadar skip).
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

pytestmark = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


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
const vm = require('vm');

const [updateJs, i18nJs, i18nCommonJs, payloadPath, lang] = process.argv.slice(2);
const info = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

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
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
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
El.prototype.matches = function (sel) {
    const self = this;
    return String(sel).split(',').some(function (part) {
        part = part.trim();
        const m = part.match(/^(\w+)?\[([\w-]+)\]$/);
        if (!m) return false;
        if (m[1] && self.tagName !== m[1].toUpperCase()) return false;
        return self.getAttribute(m[2]) !== null;
    });
};
El.prototype.querySelectorAll = function (sel) {
    return this.descendants().filter(function (e) {
        return e.matches && e.matches(sel);
    });
};
El.prototype.querySelector = function (sel) { return this.querySelectorAll(sel)[0] || null; };

const body = new El('body');
const document = {
    nodeType: 9,
    readyState: 'complete',
    documentElement: new El('html'),
    head: new El('head'),
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
    querySelectorAll: function (sel) { return body.querySelectorAll(sel); },
    querySelector: function (sel) { return body.querySelector(sel); }
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

// Gerçek çeviri altyapısı — arayüz dili gerçekten kuruluyor
vm.runInContext(fs.readFileSync(i18nJs, 'utf8'), win, { filename: 'i18n.js' });
vm.runInContext(fs.readFileSync(i18nCommonJs, 'utf8'), win, { filename: 'i18n_common.js' });
win.I18N.setLang(lang);

vm.runInContext(fs.readFileSync(updateJs, 'utf8'), win, { filename: 'update_check.js' });
win.hrmaCheckForUpdates(true);

// fetch zinciri mikro görevlerde çözülür; birkaç tur bekle
setTimeout(function () {
    const modal = document.getElementById('hrma-update-modal');
    if (!modal) {
        console.log(JSON.stringify({ ok: false, reason: 'modal açılmadı', istekler: istekler }));
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
        baslik: String(box.children[0].innerHTML || ''),
        soru: String(box.children[1].innerHTML || ''),
        notlar: metinler.length ? metinler[0] : '',
        istekler: istekler
    }));
}, 20);
"""


def _pencereyi_ac(info, lang):
    """update_check.js'i node içinde çalıştırır, açılan pencereyi döndürür."""
    with tempfile.TemporaryDirectory() as tmp:
        driver = os.path.join(tmp, 'driver.js')
        payload = os.path.join(tmp, 'payload.json')
        with open(driver, 'w', encoding='utf-8') as fh:
            fh.write(HARNESS_JS)
        with open(payload, 'w', encoding='utf-8') as fh:
            json.dump(info, fh, ensure_ascii=False)
        proc = subprocess.run(
            [shutil.which('node'), driver, UPDATE_JS, I18N_JS, I18N_COMMON_JS,
             payload, lang],
            capture_output=True, text=True, timeout=120)
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


def test_ingilizce_arayuzde_notlar_ingilizce_gelir():
    sonuc = _pencereyi_ac(_bilgi(notes=NOTLAR), 'en')
    assert sonuc['lang'] == 'en'
    assert 'UPDATE AVAILABLE' in sonuc['baslik'], sonuc['baslik']
    assert sonuc['notlar'].strip() == BOLUM['en'], (
        'İngilizce arayüzde Türkçe/karışık not gösterildi:\n%s'
        % sonuc['notlar'][:400])


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


def test_imsiz_govdede_ingilizce_arayuz_ingilizce_gorur():
    sonuc = _pencereyi_ac(_bilgi(notes=IMSIZ, source='page'), 'en')
    notlar = sonuc['notlar']
    assert not TR_LETTERS.search(notlar), (
        'İngilizce arayüzde Türkçe bölüm sızdı:\n%s' % notlar[:400])


# ---------------------------------------------------------------------------
# 1. biçim — sunucu dile ayrılmış alan gönderirse o kazanır
# ---------------------------------------------------------------------------
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
def test_tek_dilli_not_gizlenmez():
    """Eski/elle yazılmış tek dilli notlar Türkçe arayüzde de gösterilir.

    Elde başka metin yok; saklamak kullanıcıyı bilgisiz bırakır. (Yanına
    'bu not yalnızca İngilizce mevcut' etiketi eklenmesi için gereken i18n
    anahtarları raporda listelendi.)
    """
    sonuc = _pencereyi_ac(_bilgi(notes=BOLUM['en']), 'tr')
    assert sonuc['notlar'].strip() == BOLUM['en'].strip(), (
        'tek dilli not bölünüp parçalanmış:\n%s' % sonuc['notlar'][:400])


def test_not_yoksa_pencere_yine_acilir():
    """Not gövdesi boş gelse bile güncelleme penceresi çalışmalı."""
    sonuc = _pencereyi_ac(_bilgi(notes=''), 'tr')
    assert 'GÜNCELLEME MEVCUT' in sonuc['baslik']


# ---------------------------------------------------------------------------
# Sunucu sözleşmesi — dosya başlığındaki kök neden
# ---------------------------------------------------------------------------
# Gövdeyi tek parça kırpmak Türkçe bölümü düşürüyor. Sunucu bölümlere
# ayırdıktan sonra kırpınca (split_notes_by_language + notes_en/notes_tr)
# aşağıdaki test kendiliğinden etkinleşir; o zamana dek atlanır.
def _update_checker():
    from hrma.utils import update_checker
    return update_checker


SUNUCU_AYIRIYOR = hasattr(_update_checker(), 'split_notes_by_language')


@pytest.mark.skipif(not SUNUCU_AYIRIYOR,
                    reason='sunucu yaması yok: update_checker gövdeyi hâlâ '
                           'tek parça kırpıyor, Türkçe bölüm istemciye ulaşmıyor')
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
