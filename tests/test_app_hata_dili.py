"""app.py hata/uyarı dili bekçisi (2026-08-04) — son i18n borcu.

KAPATILAN KUSUR
---------------
``app.py`` dil anahtarından bağımsız TÜRKÇE üretilen kullanıcı-görünür
metinler taşıyordu; EN kipteki kullanıcı Türkçe hata görüyordu. Ölçülen
sızıntılar (HEAD 3b91dc4):

* ``/calculate_solid`` ve ``/calculate_liquid`` eksik girdi yanıtı
  (``error`` + ``hint``) — 'Katı/Sıvı motor hesabı için zorunlu girdiler
  eksik; ...'
* ``/calculate`` enjektör ``unused_inputs``/``warnings`` gerekçeleri —
  "Input 'x' was not consumed: <TÜRKÇE gerekçe>" karışık dil üretiyordu
* ``/api/injector/design`` yedek metni 'tasarım hatası'
* CAD paket üreticisi: README satırları ('HRMA CAD paketi', 'N dosya')
  ve 500 gövdesi 'CAD üretilemedi: ...'
* STL ucu 500 gövdeleri 'CAD montajı üretilemedi' / 'STL üretilemedi'
* Yörünge ucu ``plot_error`` alanı 'Yörünge grafiği üretilemedi: %s'
* 3B performans yüzeyi ``analysis_info.reference`` içinde '2. baskı'

SÖZLEŞME
--------
Backend EN üretir; TR karşılığı i18n katmanından döner:

* Sabit metin -> ``i18n_charts.js`` sözlüğü (anahtar = EN metnin kendisi,
  ``serverText`` birebir arar)
* Dinamik değerli metin -> ``i18n_charts.js`` ``MSG_PATTERNS`` kuralı

Kullanıcıya DÖNMEYEN Türkçe (yorumlar, docstring'ler, günlük satırları)
bu bekçinin kapsamı dışındadır: AST taraması docstring/yalın-ifade
dizgilerini bilerek dışlar.

Bekçiler:
  1. KAYNAK — app.py'de docstring dışı hiçbir dizgi değişmezi Türkçe
     karakter taşımaz (EN üretim sözleşmesinin kendisi).
  2. UÇ — eksik girdiyle çağrılan uçların yanıt gövdesi Türkçe karaktersiz
     ve metinler sözlük anahtarlarıyla BİREBİR aynı (anahtar = EN metin
     sözleşmesi; metin app.py'de değişir de sözlük güncellenmezse kırılır).
  3. SÖZLÜK — her yeni EN metnin TR karşılığı var ve kopya değil.
  4. DESEN — dinamik mesajların MSG_PATTERNS kuralları kayıtlı ve özel
     kural genel kuraldan önce (applyPatterns ilk eşleşmede döner).
  5. DAVRANIŞ (node varsa) — serverText TR'de çevirir, EN'e dokunmaz.
"""

import ast
import json
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

warnings.filterwarnings('ignore')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / 'hrma' / 'app.py'
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
CHARTS_JS = STATIC_JS / 'i18n_charts.js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

TURKCE_KARAKTER = re.compile(r'[çğıöşüÇĞİÖŞÜ]')

# ---------------------------------------------------------------------------
# app.py'nin ürettiği, sözlükte TR karşılığı ZORUNLU sabit EN metinler.
# Metin app.py'de değişirse burası da değişmeli — bilerek: anahtar = EN
# metin sözleşmesinde metni değiştirmek sözlük anahtarını da değiştirir.
# ---------------------------------------------------------------------------
SOLID_EKSIK_GIRDI = ('Required inputs for the solid motor calculation are '
                     'missing; defaults were not applied and no design was '
                     'produced.')
LIQUID_EKSIK_GIRDI = ('Required inputs for the liquid motor calculation are '
                      'missing; defaults were not applied and no design was '
                      'produced.')
SOLID_HINT = ('Geometry mode takes diameter/length/core, design-point mode '
              'takes thrust + burn time. For the tutorial scenario send '
              '"use_tutorial_defaults": true; the result declares which '
              'inputs came from defaults in the "defaults_applied" field.')
LIQUID_HINT = ('For the tutorial/demo scenario send "use_tutorial_defaults": '
               'true; the result declares which inputs came from defaults in '
               'the "defaults_applied" field.')

SOZLUK_ZORUNLU_ANAHTARLAR = [
    SOLID_EKSIK_GIRDI,
    LIQUID_EKSIK_GIRDI,
    SOLID_HINT,
    LIQUID_HINT,
    'CAD assembly could not be generated',
    'STL generation failed',
    'injector design error',
    # Enjektör "tüketilmedi" gerekçeleri (sabit dört tanesi; beşincisi
    # dinamik ve MSG_PATTERNS kuralıyla çevrilir)
    ('the model COMPUTES this distance from the impingement angle and hole '
     'diameter; see the value in the results'),
    ('this path models like-on-like doublets; the momentum-ratio criterion '
     'applies to unlike impingement'),
    ('the model COMPUTES the recess from the inner jet diameter; see the '
     'value in the results'),
    ('this path sizes a single coaxial element; use the Injector Design '
     'panel for a multi-element array'),
]

#: MSG_PATTERNS'ta bulunması zorunlu kural imzaları (kaynak metinde aranır).
DESEN_IMZALARI = [
    "was not consumed",
    "pattern is not modelled on this path",
    "CAD generation failed",
    "Trajectory plot could not be generated",
]


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 1. KAYNAK BEKÇİSİ — docstring dışı Türkçe dizgi değişmezi kalmadı
# ---------------------------------------------------------------------------
def _docstring_disi_turkce_dizgiler():
    """app.py'deki docstring/yalın-ifade DIŞI Türkçe dizgi değişmezleri.

    Yorumlar zaten AST'de yok; docstring'ler ve yalın ifade (``Expr``)
    dizgileri kullanıcıya dönmez, dışlanır. Geri kalan HER dizgi bir
    ifadenin parçasıdır (yanıt gövdesi, f-string, sözlük değeri...) ve
    EN üretim sözleşmesine tabidir.
    """
    kaynak = APP_PY.read_text(encoding='utf-8')
    agac = ast.parse(kaynak)

    yalin_ifade_dizgileri = set()
    for dugum in ast.walk(agac):
        if (isinstance(dugum, ast.Expr)
                and isinstance(dugum.value, ast.Constant)
                and isinstance(dugum.value.value, str)):
            yalin_ifade_dizgileri.add(id(dugum.value))

    bulgular = []
    for dugum in ast.walk(agac):
        if (isinstance(dugum, ast.Constant)
                and isinstance(dugum.value, str)
                and id(dugum) not in yalin_ifade_dizgileri
                and TURKCE_KARAKTER.search(dugum.value)):
            bulgular.append((dugum.lineno, dugum.value[:90]))
    return bulgular


def test_app_py_docstring_disi_turkce_dizgi_yok():
    """EN üretim sözleşmesi: kod içi dizgilerde Türkçe karakter kalmaz.

    Kırmızıya dönerse metni Türkçe yazma — EN yaz, TR karşılığını
    i18n_charts.js sözlüğüne (sabit) veya MSG_PATTERNS'a (dinamik) ekle.
    """
    bulgular = _docstring_disi_turkce_dizgiler()
    assert not bulgular, (
        'app.py kod dizgilerinde Türkçe karakter var (satır, metin):\n  '
        + '\n  '.join('%d: %r' % b for b in bulgular)
    )


# ---------------------------------------------------------------------------
# 2. UÇ BEKÇİSİ — eksik girdi yanıtları EN
# ---------------------------------------------------------------------------
def test_calculate_solid_eksik_girdi_yaniti_ingilizce(client):
    yanit = client.post('/calculate_solid', json={})
    assert yanit.status_code == 422
    metin = yanit.get_data(as_text=True)
    assert not TURKCE_KARAKTER.search(metin), (
        'EN üretim sözleşmesi bozuldu — /calculate_solid 422 gövdesinde '
        'Türkçe karakter var:\n' + metin[:600])
    govde = yanit.get_json()
    assert govde['error'] == SOLID_EKSIK_GIRDI, (
        'error metni sözlük anahtarından saptı (anahtar = EN metin '
        'sözleşmesi; ikisini birlikte güncelle): %r' % govde['error'])
    assert govde['hint'] == SOLID_HINT


def test_calculate_liquid_eksik_girdi_yaniti_ingilizce(client):
    yanit = client.post('/calculate_liquid', json={})
    assert yanit.status_code == 422
    metin = yanit.get_data(as_text=True)
    assert not TURKCE_KARAKTER.search(metin), (
        'EN üretim sözleşmesi bozuldu — /calculate_liquid 422 gövdesinde '
        'Türkçe karakter var:\n' + metin[:600])
    govde = yanit.get_json()
    assert govde['error'] == LIQUID_EKSIK_GIRDI
    assert govde['hint'] == LIQUID_HINT


# ---------------------------------------------------------------------------
# 3. SÖZLÜK BEKÇİSİ — her EN metnin TR karşılığı var
# ---------------------------------------------------------------------------
def _dil_blogu(kaynak, dil):
    """i18n_charts.js içindeki ``<dil>: { ... }`` bloğunun gövdesi.

    test_i18n_charts.py::_lang_block ile aynı tırnak-duyarlı tarama;
    kopya, iki test dosyası birbirine import bağı kurmasın diye.
    """
    baslangic = re.search(r'\b%s\s*:\s*\{' % dil, kaynak)
    assert baslangic, "i18n_charts.js içinde '%s' bloğu yok" % dil
    idx, derinlik = baslangic.end() - 1, 0
    tirnak, kacis = None, False
    while idx < len(kaynak):
        ch = kaynak[idx]
        if tirnak:
            if kacis:
                kacis = False
            elif ch == '\\':
                kacis = True
            elif ch == tirnak:
                tirnak = None
        elif ch in '\'"`':
            tirnak = ch
        elif ch == '{':
            derinlik += 1
        elif ch == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[baslangic.end():idx]
        idx += 1
    raise AssertionError("'%s' bloğu kapanmıyor" % dil)


CIFT_DESENI = re.compile(
    r"^\s*'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$", re.M)


@pytest.fixture(scope='module')
def sozluk():
    kaynak = CHARTS_JS.read_text(encoding='utf-8')
    kaynak = re.sub(r'/\*.*?\*/', '', kaynak, flags=re.S)
    cozulmus = {}
    for dil in ('en', 'tr'):
        ciftler = CIFT_DESENI.findall(_dil_blogu(kaynak, dil))
        cozulmus[dil] = {k.replace("\\'", "'"): v.replace("\\'", "'")
                         for k, v in ciftler}
    return cozulmus


def test_yeni_en_metinlerin_tr_karsiligi_sozlukte(sozluk):
    eksik_en = [k for k in SOZLUK_ZORUNLU_ANAHTARLAR if k not in sozluk['en']]
    eksik_tr = [k for k in SOZLUK_ZORUNLU_ANAHTARLAR if k not in sozluk['tr']]
    assert not eksik_en, ('i18n_charts.js EN bloğunda eksik anahtar:\n  '
                          + '\n  '.join(eksik_en))
    assert not eksik_tr, ('i18n_charts.js TR bloğunda eksik anahtar:\n  '
                          + '\n  '.join(eksik_tr))


def test_yeni_tr_degerleri_ceviri_kopya_degil(sozluk):
    """TR değeri EN kopyası olamaz ve Türkçe karakter taşımalı."""
    sorunlu = []
    for anahtar in SOZLUK_ZORUNLU_ANAHTARLAR:
        tr = sozluk['tr'].get(anahtar, '')
        if tr == sozluk['en'].get(anahtar) or not TURKCE_KARAKTER.search(tr):
            sorunlu.append('%s -> %r' % (anahtar[:60], tr[:60]))
    assert not sorunlu, ('TR değeri çevrilmemiş görünüyor:\n  '
                         + '\n  '.join(sorunlu))


# ---------------------------------------------------------------------------
# 4. DESEN BEKÇİSİ — dinamik mesaj kuralları kayıtlı ve doğru sırada
# ---------------------------------------------------------------------------
def test_msg_patterns_yeni_kurallar_kayitli():
    kaynak = CHARTS_JS.read_text(encoding='utf-8')
    eksik = [imza for imza in DESEN_IMZALARI if imza not in kaynak]
    assert not eksik, ('i18n_charts.js MSG_PATTERNS eksik kural imzaları:\n  '
                       + '\n  '.join(eksik))


def test_ozel_kural_genel_kuraldan_once():
    """applyPatterns İLK eşleşmede döner: özel kural önce gelmezse
    dinamik desen gerekçesi TR'de İngilizce kalır (yarım çeviri)."""
    kaynak = CHARTS_JS.read_text(encoding='utf-8')
    ozel = kaynak.find("was not consumed: the '(.+)' pattern is not modelled")
    genel = kaynak.find("was not consumed: (.+)$")
    assert ozel != -1, 'özel (pattern is not modelled) kuralı yok'
    assert genel != -1, 'genel (was not consumed) kuralı yok'
    assert ozel < genel, (
        'Özel kural genel kuraldan SONRA — applyPatterns ilk eşleşmede '
        'döndüğü için özel kural ölü kod olur')


# ---------------------------------------------------------------------------
# 5. DAVRANIŞ (node) — serverText TR'de çevirir, EN'e dokunmaz
# ---------------------------------------------------------------------------
NODE_DUZENEGI = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const ROOT = process.argv[2];
const IN = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sandbox = {
    console, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error,
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.document = {
    readyState: 'complete',
    documentElement: { setAttribute() {}, appendChild() {} },
    head: { appendChild() {} },
    createElement: () => ({ setAttribute() {}, appendChild() {}, style: {} }),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {}, dispatchEvent() { return true; },
};
sandbox.localStorage = null;
sandbox.CustomEvent = function (t, i) { this.type = t; this.detail = i && i.detail; };
vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_charts.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sandbox, { filename: f });
}
sandbox.I18N.setLang('tr');
const tr = IN.map((s) => sandbox.I18N.serverText(s));
sandbox.I18N.setLang('en');
const en = IN.map((s) => sandbox.I18N.serverText(s));
process.stdout.write(JSON.stringify({ tr, en }));
"""

#: app.py'nin GERÇEKTEN ürettiği biçimlerle birebir örnek dinamik mesajlar.
DINAMIK_ORNEKLER = [
    "Input 'impingement_distance' was not consumed: the model COMPUTES this "
    'distance from the impingement angle and hole diameter; see the value '
    'in the results',
    "Input 'impingement_pattern' was not consumed: the 'triplet' pattern is "
    'not modelled on this path; use the Injector Design panel for a full '
    'solution (doublet/triplet/like/coax-swirl)',
    "Input 'n_elements' was not consumed: this path sizes a single coaxial "
    'element; use the Injector Design panel for a multi-element array',
    'CAD generation failed: HRMA CAD package — X (solid) | STEP: FAILED (e) '
    '| STL: FAILED (e)',
    "Trajectory plot could not be generated: KeyError: 'time'",
    SOLID_EKSIK_GIRDI,
    LIQUID_HINT,
]


@needs_node
def test_server_text_dinamik_mesajlari_tr_ye_ceviriyor(tmp_path):
    duzenek = tmp_path / 'srv.js'
    duzenek.write_text(NODE_DUZENEGI, encoding='utf-8')
    girdi = tmp_path / 'in.json'
    girdi.write_text(json.dumps(DINAMIK_ORNEKLER), encoding='utf-8')
    islem = subprocess.run(
        [NODE, str(duzenek), str(STATIC_JS), str(girdi)],
        capture_output=True, text=True, timeout=120)
    assert islem.returncode == 0, 'node düzeneği düştü:\n%s' % islem.stderr
    sonuc = json.loads(islem.stdout)

    # EN dokunulmazlığı
    assert sonuc['en'] == DINAMIK_ORNEKLER, \
        'serverText EN kipinde metni değiştirdi'

    # TR: hepsi değişmeli ve Türkçe karakter taşımalı
    cevrilemeyen = [kaynak for kaynak, tr in zip(DINAMIK_ORNEKLER, sonuc['tr'])
                    if kaynak == tr or not TURKCE_KARAKTER.search(tr)]
    assert not cevrilemeyen, (
        "serverText TR'de çeviremedi:\n  " + '\n  '.join(cevrilemeyen))
