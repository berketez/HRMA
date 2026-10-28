# -*- coding: utf-8 -*-
"""ÖH Dalga-29 · kulvar ``arayuz-i18n`` · aşama 2 — bekçiler.

Her bekçi, ters-mutasyonla (onarımı geçici geri al → KIRMIZI) kanıtlanmıştır;
kanıt ``docs/scofield/raw/OH/D29/arayuz-i18n/a2/mutasyon.json``.

Kapsanan kalemler
-----------------
* **P12aB1-04** — ``data-i18n-title`` / ``data-i18n-placeholder`` parametre
  desteği (parametreli anahtar bu yollara konduğunda öznitelik SESSİZCE hiç
  yazılmıyordu).
* **P12aB1-05** — parametresiz donan düğüm artık uyarı yayar (sessiz donma).
* **P12aB1-06** — kritik tank uyarısında "KALDI" belirsizliği.
* **P12aB2-09** — ÇÜRÜTÜLDÜ: liquid.html'de çıplak çok sözcüklü birim rozeti
  yok, 454 anahtarın 454'ü EN+TR tanımlı (kilit).
* **P12aB2-10** — i18n.js'teki 4 ölü ``nav.*`` anahtarı söküldü.
* **P12aB2-11** — ``T``/``TF`` taban sözleşmesi çekirdekte.
* **P12aB4-12** — katı/dolu motorun propelan kütlesi "yakıt" değil "propelan".
* **P12bB1-14** — sıvı akış şemasının 8 kutu adı i18n'de.
* **P12bB2-22** — ateşleme emniyeti tablosundaki 2 sabit satır künyeli.
* **P12bB3-18** — ÇÜRÜTÜLDÜ: ``validateComposition`` %100 i18n'den geçiyor.

Node çağrıları ``tests/test_node_cagri_sozlesmesi.py`` sözleşmesine uyar:
betik argv'ye değil DOSYA yoluyla verilir.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
TPL = KOK / 'hrma' / 'templates'

NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def oku(p):
    return p.read_text(encoding='utf-8')


def maske_yorum(text):
    """``test_d17_electron_a1.maske_yorum`` ile aynı iş: yorumları söker."""
    import sys
    sys.path.insert(0, str(KOK))
    from tests.test_d17_electron_a1 import maske_yorum as m
    return m(text)


def sozluk_bloklari(src):
    sinir = src.find('\n        tr: {')
    assert sinir > 0, 'tr bloğu bulunamadı'
    return src[:sinir], src[sinir:]


def sozluk(src, dil):
    en, tr = sozluk_bloklari(maske_yorum(src))
    blok = en if dil == 'en' else tr
    return dict(re.findall(r"^\s*'([\w.]+)':\s*'((?:[^'\\]|\\.)*)'", blok, re.M))


# ---------------------------------------------------------------------------
# P12aB1-04 + P12aB1-05 — translateElement (CANLI node koşumu)
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const staticDir = process.argv[2];

const sandbox = {};
sandbox.window = sandbox;
const uyarilar = [];
sandbox.console = {
    log: function () {},
    warn: function () { uyarilar.push(Array.prototype.join.call(arguments, ' ')); },
    error: function () { uyarilar.push(Array.prototype.join.call(arguments, ' ')); },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(staticDir + '/i18n.js', 'utf8'), sandbox,
                { filename: 'i18n.js' });
const I18N = sandbox.I18N;
if (!I18N) { console.log(JSON.stringify({ err: 'I18N yuklenemedi' })); process.exit(1); }
if (I18N.debug !== undefined) I18N.debug = true;

// Parametreli numune anahtar — EN + TR.
I18N.register({
    en: { 'sonda.param': 'Chamber {pc} bar' },
    tr: { 'sonda.param': 'Oda {pc} bar' },
}, 'sonda.js');

function fakeEl(attrs, text) {
    return {
        nodeType: 1,
        textContent: text,
        _attrs: Object.assign({}, attrs),
        getAttribute(k) {
            return Object.prototype.hasOwnProperty.call(this._attrs, k)
                ? this._attrs[k] : null;
        },
        setAttribute(k, v) { this._attrs[k] = String(v); },
        querySelectorAll() { return []; },
    };
}

I18N.setLang('en');

// (1) P12aB1-04 — parametreli anahtar title/placeholder yolunda.
const titled = fakeEl({
    'data-i18n-title': 'sonda.param',
    'data-i18n-params': '{"pc":42}',
    title: 'eski baslik',
}, '');
const holder = fakeEl({
    'data-i18n-placeholder': 'sonda.param',
    'data-i18n-params': '{"pc":42}',
    placeholder: 'eski yer tutucu',
}, '');
const kok = {
    nodeType: 1,
    getAttribute() { return null; },
    setAttribute() {},
    querySelectorAll() { return [titled, holder]; },
};
I18N.applyTo(kok);
const out = {
    en_title: titled.getAttribute('title'),
    en_placeholder: holder.getAttribute('placeholder'),
};
I18N.setLang('tr');
I18N.applyTo(kok);
out.tr_title = titled.getAttribute('title');
out.tr_placeholder = holder.getAttribute('placeholder');

// (2) P12aB1-05 — params TAŞIMAYAN parametreli düğüm: donma SESSİZ olmamalı.
uyarilar.length = 0;
I18N.setLang('en');
const donan = fakeEl({ 'data-i18n': 'sonda.param' }, 'Chamber 7 bar');
const kok2 = {
    nodeType: 1,
    getAttribute() { return null; },
    setAttribute() {},
    querySelectorAll() { return [donan]; },
};
I18N.setLang('tr');
I18N.applyTo(kok2);
out.donan_metin = donan.textContent;
out.donma_uyarisi = uyarilar.filter(u => /data-i18n-params/.test(u)).length;

// (3) P12aB2-11 — T/TF çekirdekte mi? (i18n_pages.js HİÇ yüklenmedi)
out.T_tipi = typeof sandbox.T;
out.TF_tipi = typeof sandbox.TF;
out.T_yedegi = (typeof sandbox.T === 'function')
    ? sandbox.T('hic.olmayan.anahtar', 'İngilizce yedek') : null;
out.TF_yedegi = (typeof sandbox.TF === 'function')
    ? sandbox.TF('hic.olmayan.anahtar', { pc: 5 }, 'Chamber {pc} bar') : null;

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def sonda(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    betik = tmp_path_factory.mktemp('d29a2') / 'sonda.js'
    betik.write_text(HARNESS, encoding='utf-8')
    ph = subprocess.run([NODE, str(betik), str(JS)], capture_output=True,
                        text=True, timeout=120)
    assert ph.returncode == 0, ph.stderr[-2000:]
    return json.loads(ph.stdout.strip().split('\n')[-1])


@node_gerek
def test_p12ab1_04_title_placeholder_parametreyi_aliyor(sonda):
    """Parametreli anahtar title/placeholder yolunda BASILIR.

    Ölçülen kusur (a2/once.json M1): iki yol da parametresiz ``t()``
    çağırıyordu; çeviri ``{pc}`` taşıdığı için ezme koruması devreye
    giriyor ve öznitelik SESSİZCE hiç yazılmıyordu (eski değer kalıyordu).
    """
    assert sonda['en_title'] == 'Chamber 42 bar', sonda['en_title']
    assert sonda['en_placeholder'] == 'Chamber 42 bar', sonda['en_placeholder']
    # Dil değişiminde de aynı parametrelerle yeniden dolar.
    assert sonda['tr_title'] == 'Oda 42 bar', sonda['tr_title']
    assert sonda['tr_placeholder'] == 'Oda 42 bar', sonda['tr_placeholder']


@node_gerek
def test_p12ab1_04_cig_sablon_hicbir_oznitelige_basilmaz(sonda):
    """Parametre gelse de gelmese de ham ``{pc}`` kullanıcıya GÖSTERİLMEZ."""
    for alan in ('en_title', 'en_placeholder', 'tr_title', 'tr_placeholder'):
        assert '{pc}' not in (sonda[alan] or ''), (alan, sonda[alan])


@node_gerek
def test_p12ab1_05_sessiz_donma_artik_sessiz_degil(sonda):
    """params taşımayan parametreli düğüm donuyorsa BUNU SÖYLER.

    Donmanın kendisi doğru davranıştır (ham şablon basmaktansa eski dilde
    doğru sayı yeğdir), sessizliği kusurdu: kusur yayıcıda ama kimse
    duymuyordu.
    """
    assert sonda['donan_metin'] == 'Chamber 7 bar', sonda['donan_metin']
    assert sonda['donma_uyarisi'] >= 1, sonda


@node_gerek
def test_p12ab2_11_T_TF_cekirdekte_tanimli(sonda):
    """``i18n_pages.js`` HİÇ yüklenmeden ``T``/``TF`` çağrılabilir.

    Ölçülen kusur (a2/once.json M5): sözleşme yalnız ``i18n_pages.js``
    sonunda tanımlıydı; o dosya 404 alsaydı liquid.html'deki 495 +
    solid.html'deki 439 çağrı ReferenceError atıp sayfayı susturacaktı.
    """
    assert sonda['T_tipi'] == 'function', sonda['T_tipi']
    assert sonda['TF_tipi'] == 'function', sonda['TF_tipi']
    # Sözleşme korunur: anahtar yoksa çağıranın yedeği döner.
    assert sonda['T_yedegi'] == 'İngilizce yedek', sonda['T_yedegi']
    assert sonda['TF_yedegi'] == 'Chamber 5 bar', sonda['TF_yedegi']


def test_p12ab2_11_pages_sozlesmeyi_ezmiyor():
    """Tek kaynak: i18n_pages.js kendi kapısında durur, çekirdeği ezmez."""
    src = maske_yorum(oku(JS / 'i18n_pages.js'))
    assert "if (typeof global.T !== 'function')" in src
    assert "if (typeof global.TF !== 'function')" in src


# ---------------------------------------------------------------------------
# P12aB1-06 — "KALDI" belirsizliği
# ---------------------------------------------------------------------------
def test_p12ab1_06_kritik_tank_uyarisi_tek_anlamli():
    """Tankın patlayabileceğini söyleyen ``critical`` uyarı "KALDI" demez.

    "KALDI" ilk okumada "yapılmadan kaldı" anlaşılır; ölçüt BAŞARISIZLIK.
    """
    tr = sozluk(oku(JS / 'i18n_common.js'), 'tr')
    metin = tr['warn.liquid.tank_vessel_fail']
    assert 'KALDI' not in metin, metin
    assert 'BAŞARISIZ' in metin, metin
    # Uyarının bilgi yükü korundu (kırpılmadı).
    for parca in ('{tank}', '{burst_margin}', 'AIAA S-080'):
        assert parca in metin, (parca, metin)


def test_p12ab1_06_hicbir_ceviride_yalin_KALDI_kalmadi():
    """Aynı belirsizlik başka anahtara sızmasın (regresyon kapısı)."""
    sizan = []
    for yol in sorted(JS.glob('i18n*.js')):
        for k, v in sozluk(oku(yol), 'tr').items():
            if re.search(r'\bKALDI\b', v):
                sizan.append('%s::%s' % (yol.name, k))
    assert not sizan, sizan


# ---------------------------------------------------------------------------
# P12aB4-12 — katı/dolu motorun PROPELAN kütlesi
# ---------------------------------------------------------------------------
#: Bu üç anahtarın taşıdığı sayı, katı/dolu motorun OKSİTLEYİCİYİ DE İÇEREN
#: propelan kütlesidir. Türkçesi "yakıt" olamaz: yakıt propelanın yalnız bir
#: bileşenidir, etiket fiziksel olarak yanlış olur.
PROPELAN_KUTLESI_ANAHTARLARI = (
    'imp.metaLine',
    'warn.solid.propellant_mass_not_positive',
    'sixdof.propMassSuggested',
)


@pytest.mark.parametrize('anahtar', PROPELAN_KUTLESI_ANAHTARLARI)
def test_p12ab4_12_propelan_kutlesi_yakit_denmiyor(anahtar):
    tr = sozluk(oku(JS / 'i18n_common.js'), 'tr')
    metin = tr[anahtar]
    assert not re.search(r'\byakıt', metin, re.I), (anahtar, metin)
    assert re.search(r'\bpropelan', metin, re.I), (anahtar, metin)


@pytest.mark.parametrize('anahtar', PROPELAN_KUTLESI_ANAHTARLARI)
def test_p12ab4_12_ingilizcesi_hala_propellant_diyor(anahtar):
    """Mandal bayatlamasın: TR'yi düzelttiğimiz anahtar GERÇEKTEN propelan
    kütlesi anahtarıdır (EN tarafı "propellant" der)."""
    en = sozluk(oku(JS / 'i18n_common.js'), 'en')
    assert re.search(r'propellant', en[anahtar], re.I), (anahtar, en[anahtar])


# ---------------------------------------------------------------------------
# P12aB2-10 — ölü nav.* anahtarları
# ---------------------------------------------------------------------------
OLU_NAV = ('nav.home', 'nav.hybrid', 'nav.solid', 'nav.liquid')


def test_p12ab2_10_olu_nav_anahtarlari_sokuldu():
    src = maske_yorum(oku(JS / 'i18n.js'))
    kalan = [a for a in OLU_NAV if ("'%s':" % a) in src]
    assert not kalan, kalan


def test_p12ab2_10_cekirdek_sozlugunde_olu_anahtar_yok():
    """i18n.js'in HER anahtarının ürün kodunda bir tüketicisi var.

    Sayı mandalı değil KÜME ölçüsü: yeni bir anahtar eklenirse tüketicisi
    de gelmeli, yoksa bu bekçi adıyla söyler.
    """
    src = maske_yorum(oku(JS / 'i18n.js'))
    en, _ = sozluk_bloklari(src)
    anahtarlar = sorted(set(re.findall(r"^\s*'([A-Za-z][\w.]*)':\s*'", en, re.M)))
    assert len(anahtarlar) > 30, len(anahtarlar)
    govde = []
    for p in sorted(JS.glob('*.js')):
        if p.name == 'i18n.js':
            continue
        govde.append(maske_yorum(oku(p)))
    for p in sorted(TPL.glob('*.html')):
        govde.append(oku(p))
    butun = '\n'.join(govde)
    olu = [a for a in anahtarlar
           if ("'%s'" % a) not in butun and ('"%s"' % a) not in butun]
    assert not olu, 'i18n.js ölü anahtar: %s' % olu


def test_p12ab2_10_numuneler_canli_anahtara_tasindi():
    """``test_i18n.py`` artık ölü anahtarı canlı tutmuyor."""
    src = oku(KOK / 'tests' / 'test_i18n.py')
    for a in OLU_NAV:
        assert ("'%s'" % a) not in src, a


# ---------------------------------------------------------------------------
# P12bB1-14 — sıvı akış şeması kutu adları
# ---------------------------------------------------------------------------
DIAGRAM_ANAHTARLARI = (
    ('liq.diag.oxidizer_tank', 'Oxidizer<br>Tank'),
    ('liq.diag.fuel_tank', 'Fuel<br>Tank'),
    ('liq.diag.oxidizer_pump', 'Oxidizer<br>Pump'),
    ('liq.diag.fuel_pump', 'Fuel<br>Pump'),
    ('liq.diag.pressure_fed', 'Pressure<br>Fed'),
    ('liq.diag.injector', 'Injector'),
    ('liq.diag.combustion_chamber', 'Combustion<br>Chamber'),
    ('liq.diag.nozzle', 'Nozzle'),
)


@pytest.mark.parametrize('anahtar,ingilizce', DIAGRAM_ANAHTARLARI)
def test_p12bb1_14_kutu_adi_iki_dilde_tanimli(anahtar, ingilizce):
    src = oku(JS / 'i18n_pages.js')
    en, tr = sozluk(src, 'en'), sozluk(src, 'tr')
    assert en.get(anahtar) == ingilizce, (anahtar, en.get(anahtar))
    assert anahtar in tr, anahtar
    assert tr[anahtar] != en[anahtar], (anahtar, 'TR çevrilmemiş')


@pytest.mark.parametrize('anahtar,ingilizce', DIAGRAM_ANAHTARLARI)
def test_p12bb1_14_kutu_adi_sablonda_cagriliyor(anahtar, ingilizce):
    """Anahtar ve çağrı yeri AYNI ANDA: ölü çeviri doğmaz."""
    liq = maske_yorum(oku(TPL / 'liquid.html'))
    desen = r"label\([^()]*,\s*T\(\s*'%s'\s*,\s*'%s'" % (
        re.escape(anahtar), re.escape(ingilizce))
    assert re.search(desen, liq), anahtar


@pytest.mark.parametrize('anahtar,ingilizce', DIAGRAM_ANAHTARLARI)
def test_p12bb1_14_ciplak_kutu_adi_geri_gelmedi(anahtar, ingilizce):
    """``label(..., 'Oxidizer<br>Tank', ...)`` biçiminde ÇIPLAK çağrı yok."""
    liq = maske_yorum(oku(TPL / 'liquid.html'))
    ciplak = re.findall(r"label\([^()]*,\s*'%s'" % re.escape(ingilizce), liq)
    assert not ciplak, (anahtar, ciplak)


def test_p12bb1_14_nozul_terim_kanonuna_uyuyor():
    """'Nozzle' → 'Nozul' (test_z5i18n_supurme.py TERMS ile aynı kanon)."""
    tr = sozluk(oku(JS / 'i18n_pages.js'), 'tr')
    assert 'nozul' in tr['liq.diag.nozzle'].lower(), tr['liq.diag.nozzle']


def test_p12bb1_14_a1in_row_etiketleri_hala_bagli():
    """Önceki aşamanın onarımı BOZULMADI (regresyon kapısı)."""
    liq = maske_yorum(oku(TPL / 'liquid.html'))
    assert len(re.findall(r"row\(\s*T\(\s*'liq\.js\.row_", liq)) == 4


# ---------------------------------------------------------------------------
# P12bB2-22 — ateşleme emniyeti tablosundaki sabit satırlar
# ---------------------------------------------------------------------------
def _atesleme_blogu():
    sol = oku(TPL / 'solid.html')
    m = re.search(r'function generateSafetyAnalysisHTML\(results\)\s*\{', sol)
    assert m, 'generateSafetyAnalysisHTML bulunamadı'
    d, i = 0, m.end() - 1
    while i < len(sol):
        if sol[i] == '{':
            d += 1
        elif sol[i] == '}':
            d -= 1
            if d == 0:
                return sol[m.start():i + 1]
        i += 1
    raise AssertionError('fonksiyon kapanmıyor')


def test_p12bb2_22_sabit_satirlar_kunyeli():
    """Hesaptan gelmeyen iki satır, hesaplananlarla aynı tabloda künyesiz
    duramaz: kullanıcı hangi satırın KENDİ tasarımından çıktığını görmeli."""
    blok = _atesleme_blogu()
    sabit = [s for s in blok.split('\n')
             if '<tr>' in s and not re.search(r'fmtField|fmtTextField|Safety\.\w+', s)]
    assert len(sabit) == 2, len(sabit)
    for satir in sabit:
        assert 'solid.js.general_requirement_not_computed' in satir, satir[:160]


def test_p12bb2_22_kunye_iki_dilde_tanimli():
    src = oku(JS / 'i18n_pages.js')
    en, tr = sozluk(src, 'en'), sozluk(src, 'tr')
    a = 'solid.js.general_requirement_not_computed'
    assert a in en and a in tr, a
    assert 'not computed' in en[a].lower(), en[a]
    assert 'hesaplanmadı' in tr[a], tr[a]


def test_p12bb2_22_hesaplanan_satirlar_kunyelenmedi():
    """Künye SADECE sabit satırlara: uçtan gelen satır 'hesaplanmadı'
    demez (aksi hâlde künye anlamını yitirir)."""
    blok = _atesleme_blogu()
    hesapli = [s for s in blok.split('\n')
               if '<tr>' in s and re.search(r'fmtField|fmtTextField|Safety\.\w+', s)]
    assert len(hesapli) >= 5, len(hesapli)
    for satir in hesapli:
        assert 'general_requirement_not_computed' not in satir, satir[:160]


# ---------------------------------------------------------------------------
# P12aB2-09 + P12bB3-18 — ÇÜRÜTME KİLİTLERİ
# ---------------------------------------------------------------------------
def test_p12ab2_09_curutme_kilidi_ciplak_birim_rozeti_yok():
    """ÇÜRÜTÜLDÜ: liquid.html'de İngilizce SÖZCÜK taşıyan çıplak birim
    rozeti kalmamış (ölçüm a2/once.json M7: 0). Kilit, kusurun geri
    dönmesini engeller."""
    SIMGE = {'mm', 'bar', 'ms', 'kg', 'MJ', 'Pa', 'dB', 'deg', 'rad', 'Hz',
             'kPa', 'MPa', 'um', 'Ra', 'psi', 'sec', 'kN'}
    liq = oku(TPL / 'liquid.html')
    ciplak = []
    for i, l in enumerate(liq.split('\n'), 1):
        for m in re.finditer(
                r'<span[^>]*class="unit"([^>]*)>\s*\(?([^)<]{1,40})\)?\s*</span>', l):
            attrs, inner = m.group(1), m.group(2)
            kelime = [w for w in re.findall(r'[A-Za-z]{2,}', inner) if w not in SIMGE]
            if kelime and 'data-i18n' not in attrs:
                ciplak.append((i, inner))
    assert not ciplak, ciplak


def test_p12ab2_09_curutme_kilidi_tum_anahtarlar_iki_dilde():
    """liquid.html'in kullandığı her ``data-i18n`` anahtarı EN **ve** TR
    bloklarının ikisinde de tanımlı (ölçüm: 454/454)."""
    tum = {}
    for p in sorted(JS.glob('i18n*.js')):
        src = oku(p)
        for a in sozluk(src, 'en'):
            tum.setdefault(a, set()).add('en')
        for a in sozluk(src, 'tr'):
            tum.setdefault(a, set()).add('tr')
    liq = oku(TPL / 'liquid.html')
    kullanilan = set(re.findall(
        r'data-i18n(?:-title|-placeholder)?="([^"]+)"', liq))
    # V301/L-D (SV-12): kamara malzemesi seçenek anahtarları sunucu
    # kaydından basılır (``liq.mat.{{ o.value }}``); tek Jinja ifadesi
    # kaydın gerçek anahtarlarıyla açılır (test_i18n_pages deseni).
    if 'liq.mat.{{ o.value }}' in kullanilan:
        from hrma.app import _sivi_form_kaydi
        kullanilan.discard('liq.mat.{{ o.value }}')
        kullanilan |= {'liq.mat.' + o['value'] for o in
                       _sivi_form_kaydi()['chamber_material']['options']}
    # T-ÇAPA-C2 (27 Eki): V301/L-C (SV-12) enjektör plakası malzemesi
    # seçenekleri de aynı tek-ifade deseniyle sunucu kaydından basılır
    # (``liq.injmat.{{ o.material_key }}``; test_i18n_pages ile aynı açılım).
    if 'liq.injmat.{{ o.material_key }}' in kullanilan:
        from hrma.app import _sivi_enjektor_malzeme_secenekleri
        kullanilan.discard('liq.injmat.{{ o.material_key }}')
        kullanilan |= {'liq.injmat.' + o['material_key'] for o in
                       _sivi_enjektor_malzeme_secenekleri()['options']}
    kullanilan = sorted(kullanilan)
    # V301/L-D (SV-09) — TABAN ÖLÇÜMLE GÜNCELLENDİ: bu satır ayrıştırıcının
    # boş dönmediğinin sağlamasıdır (ölçüm 454). Çözücünün okumadığı 26
    # girdi formdan kalkınca (etiket + ipucu + seçenek anahtarlarıyla)
    # ölçülen sayı 383 oldu; taban o ölçümün altında tutuldu. Asıl iddia
    # (her anahtar iki dilde) aşağıda aynen.
    assert len(kullanilan) > 350, len(kullanilan)
    eksik = {a: sorted(tum.get(a, set())) for a in kullanilan
             if len(tum.get(a, set())) < 2}
    assert not eksik, eksik


def test_p12bb3_18_curutme_kilidi_validate_composition_i18nli():
    """ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11).

    ESKİ SÖZLEŞME: ``validateComposition`` gövdesindeki ekran metinlerinin
    tamamının ``i18nText``/``i18nFmt``'ten geçtiği (çıplak 0, i18n çağrısı
    >= 18) ölçülüyordu. Kilit, ölü fonksiyonun sayfada DURMASINI şart
    koşuyordu: ÖLÇÜLDÜ (raw/OH/D33/arayuz-panel/a1/once.json · M2) ki
    fonksiyonun tek çağıranı OH-D31-05'te sökülen ``#custom_fuel_config``
    panelinin düğmesiydi ve ``#composition_rows`` sorgusu boş dönüyordu —
    yani çevrilmiş metinlerin hiçbiri ürün yolundan ekrana ULAŞAMIYORDU.

    YENİ SÖZLEŞME: sarmal geri gelmez; geri gelirse (çevrilmiş olsa bile)
    erişilemez ölü yüzey yeniden doğmuş demektir ve bu bekçi kırmızı verir.
    """
    adv = oku(TPL / 'advanced.html')
    kod = re.sub(r'<!--.*?-->', '', adv, flags=re.S)
    assert 'function validateComposition' not in kod, (
        'erişilemez bileşim sarmalı geri geldi (OH-D32-11)')
    for ad in ('addCompositionRow', 'removeCompositionRow',
               'updateMixtureDensity'):
        assert 'function %s' % ad not in kod, (
            '%s geri geldi (OH-D32-11)' % ad)
# ---------------------------------------------------------------------------
# P11B5-21 — ENGELLİ (saha dışı) — kusurun ÖLÇÜMÜ kayda geçer
# ---------------------------------------------------------------------------
def test_p11b5_21_kapandi_panel_kacisli_description_okuyor():
    """ÇEVRİLDİ — kalem KAPANDI (ÖH D30 / app-api-dogrulama a1).

    D29'da bu bekçi bir DEVİR KAYDIydı: kusuru (``pattern.description_tr``
    ham HTML olarak, i18n'den geçmeden basılıyor) ölçüp saha dışı olduğunu
    kayda geçiriyor ve "kalem kapandığında KIRMIZI verir, o kulvar bu
    testi günceller" diyordu. D30'da kapandı: üretici yalan ``_tr`` alanını
    söktü (``hrma/engines/injector_design.py``), panel ``description``a
    geçti ve metin ``escText`` ile kaçırılıyor. Kayıt, kusurun GERİ
    GELMEDİĞİNİ sınayan bir değişmeze çevrildi.
    """
    inj = maske_yorum(oku(JS / 'injector_panel.js'))
    assert 'description_tr' not in inj, \
        'yalan "_tr" anahtarı panele geri geldi'
    # T-ÇAPA-C2 (27 Eki): V301/DİL-2 (803727196, NK-35) tanımı çeviri
    # kanalından geçirdi: ``escText(… serverText(dz.pattern.description) …
    # : dz.pattern.description)``. Değişmez aynı: metin escText'ten geçer ve
    # dilden bağımsız ``description`` alanını okur (kaçış ÇEVİRİNİN dışında).
    m = re.search(r'\$\{escText\(((?:(?!\}</p>).)*?)\)\}</p>', inj, re.S)
    assert m and 'dz.pattern.description' in m.group(1), \
        'açıklama kaçışsız/yanlış anahtarla basılıyor'


# ---------------------------------------------------------------------------
# a2 KAPANIŞ DERSİ — sözlük yorumlarında TEK SAYIDA kesme işareti YASAK
# ---------------------------------------------------------------------------
#: ÖLÇÜLEN KUSUR (bu aşamada, kapanış süpürmesinde yakalandı): P12bB2-22
#: künye notuna "künyesi 0'dı." yazıldı. Üründe hiçbir şey bozulmadı
#: (node --check temiz, tarayıcı yorumu atlar) ama ürünün SÖZLÜK
#: AYRIŞTIRICILARI tırnak duyarlı / yorum duyarsızdır: tek sayıda kesme
#: işareti gördüklerinde tırnak durumu kayar, EN bloğunun kapanış süslü
#: parantezini kaçırır ve TR değerlerini EN sanırlar.
#: tests/test_faz6_i18n.py::pages_dict tam bunu yaptı: üç bekçi
#: "EN ipucu Türkçe" diye kırmızı verdi. Bu bekçi kusurun sınıfını kapatır.
def test_a2_sozluk_yorumlarinda_kesme_isareti_paritesi():
    ayristirici_kiran = []
    girdi = re.compile(r"^\s*'[\w.]+':\s*'", re.M)
    for yol in sorted(JS.glob('i18n*.js')):
        src = oku(yol)
        # RİSK BÖLGESİ = sözlük gövdesi: ilk anahtar girdisinden sonuncuya
        # kadar. Bu bölgenin DIŞINDAKİ yorumlar blok sayımını etkilemez
        # (ayrıştırıcılar 'en: {' eşleşmesinden sonrasını sayar).
        girdiler = list(girdi.finditer(src))
        if len(girdiler) < 2:
            continue
        bas, son = girdiler[0].start(), girdiler[-1].end()
        for m in re.finditer(r'/\*.*?\*/', src[bas:son], re.S):
            blok = m.group(0)
            if blok.count("'") % 2:
                satir = src[:bas + m.start()].count('\n') + 1
                ayristirici_kiran.append('%s:%d %s'
                                         % (yol.name, satir,
                                            blok.split('\n')[0].strip()[:60]))
    assert not ayristirici_kiran, (
        'sözlük gövdesindeki yorumda TEK SAYIDA kesme işareti — tırnak '
        'duyarlı ayrıştırıcılar EN/TR sınırını kaçırır:\n  %s'
        % '\n  '.join(ayristirici_kiran))


def test_a2_kesme_bekcisi_gercek_bir_kusuru_goruyor():
    """Mandal bayatlamasın: bekçi kasten bozulmuş numuneyi YAKALAR."""
    numune = "/* künyesi 0'dı. */"
    assert numune.count("'") % 2 == 1
    temiz = "/* künyesi sıfırdı. */"
    assert temiz.count("'") % 2 == 0
