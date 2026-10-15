# -*- coding: utf-8 -*-
"""ÖH Dalga-24 / kulvar `electron`, aşama 1 — HUD hüküm huni̇si + kanıt hijyeni.

İki kalem:

  P12aB4-18  «D23 DEVİR» — `bindState` sözlük DIŞI bir hüküm sözcüğü
             aldığında `data-state`i siliyordu; `.hd-led` kendi yedeğine
             (`--hd-green`) düşüyor ve GERÇEK bir arka uç hükmü olan
             `EXCEEDS_ALLOWABLE` ("izin verileni aştı") ekranda ONAY
             YEŞİLİ görünüyordu. CANLI Chrome ölçümü (getComputedStyle):
             sözlük dışı 2 sözcüğün 2'si de rgb(45, 212, 168).
             Onarım SINIFLANDIRMA ÜRETMEZ — sözcük yapısal merdivene
             ALINMAZ; yalnız nötr `unrecognized` durumu konur ve ham
             sözcük LED'in `data-verdict` / `aria-label` özniteliğinde
             çevrilmeden taşınır.

  P12aB5-04  «ŞART (Fable-D18 kısım-2)» — ürün onarımı D18'de tamdı, kanıt
             betiği değildi: `olcum_b5_0405.js` beyan olsun olmasın TÜM
             düşen alanları toplayıp sonucu `toplam_beyansiz_dusen_alan`
             diye adlandırıyordu (JSON 31, rapor 0). Betik artık düşme
             SEBEBİNİ beyanıyla eşleştiriyor.

Ham kanıt: docs/scofield/raw/OH/D24/electron/a1/
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

REPO = pathlib.Path(__file__).resolve().parents[1]
JS = REPO / 'hrma' / 'static' / 'js'
CSS = REPO / 'hrma' / 'static' / 'css'
KANIT = REPO / 'docs' / 'scofield' / 'raw' / 'OH' / 'D24' / 'electron' / 'a1'
D18 = REPO / 'docs' / 'scofield' / 'raw' / 'OH' / 'D18' / 'electron' / 'a1'
OLCUM_B5 = D18 / 'olcum_b5_0405.js'
NODE = shutil.which('node')

needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# Yapısal hüküm merdiveni — `data-state` değerleri (hud.js STATE_MAP).
HUKUM_MERDIVENI = {'safe', 'acceptable', 'marginal', 'unsafe', 'not-evaluated'}
# .hd-led yedeği: --hd-green. Sözlük dışı sözcük BU renge düşmemeli.
ONAY_YESILI_DEGISKENI = '--hd-green'


def _oku(p):
    return p.read_text(encoding='utf-8')


# ===========================================================================
# P12aB4-18 — sözlük dışı hüküm sözcüğü sessizce onay yeşiline düşmez
# ===========================================================================
HUD_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];

/* Asgari DOM: kapsayıcı + içindeki tek .hd-led. */
function elem(sinif) {
    const attrs = {};
    const el = {
        attrs,
        _led: null,
        classList: { contains(c) { return c === sinif; } },
        setAttribute(k, v) { attrs[k] = String(v); },
        removeAttribute(k) { delete attrs[k]; },
        getAttribute(k) { return (k in attrs) ? attrs[k] : null; },
        querySelectorAll(sel) {
            return (sel === '.hd-led' && el._led) ? [el._led] : [];
        },
    };
    return el;
}
function kart() {
    const k = elem('hd-metric');
    k._led = elem('hd-led');
    return k;
}
const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    document: { querySelectorAll() { return []; } },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(JSDIR, 'hud.js'), 'utf8'),
                sandbox, { filename: 'hud.js' });

const SOZCUKLER = JSON.parse(process.env.HRMA_SOZCUKLER);
const cikti = {};
for (const s of SOZCUKLER) {
    const k = kart();
    sandbox.HRMAHud.bindState(k, s === '(bos)' ? null : s);
    cikti[s] = {
        kart_state: k.getAttribute('data-state'),
        led_state: k._led.getAttribute('data-state'),
        led_verdict: k._led.getAttribute('data-verdict'),
        led_aria: k._led.getAttribute('aria-label'),
    };
}
console.log(JSON.stringify(cikti));
"""

# Arka uçta GERÇEKTEN üretilen sözlük dışı hüküm sözcüğü
# (solid_rocket_engine.py:2189, hybrid_rocket_engine.py:1992):
#   rapor['verdict'] = 'SAFE' if t_aw <= izin else 'EXCEEDS_ALLOWABLE'
SOZLUK_DISI = 'EXCEEDS_ALLOWABLE'
SENTETIK = 'SOME_FUTURE_VERDICT'   # kural sözcüğe değil ÜYELİĞE bağlı


@pytest.fixture(scope='module')
def hud_veri(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    d = tmp_path_factory.mktemp('hud')
    h = d / 'hud_bekci.js'
    h.write_text(HUD_HARNESS, encoding='utf-8')
    sozcukler = ['SAFE', 'ACCEPTABLE', 'MARGINAL', 'UNSAFE', 'NOT_EVALUATED',
                 SOZLUK_DISI, SENTETIK, '   ', '(bos)']
    ortam = dict(os.environ, HRMA_SOZCUKLER=json.dumps(sozcukler))
    res = subprocess.run([NODE, str(h), str(JS)], capture_output=True,
                         text=True, timeout=120, env=ortam)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


@needs_node
def test_p12ab4_18_sozluk_disi_sozcuk_ozniteliksiz_kalmiyor(hud_veri):
    """ÖNCE (CANLI Chrome, once_b4_18.json): `EXCEEDS_ALLOWABLE`
    -> data-state null -> .hd-led background rgb(45, 212, 168) [ONAY
    YEŞİLİ]. Öznitelik yokluğu bu katmanda fail-OPEN'dır."""
    for s in (SOZLUK_DISI, SENTETIK):
        assert hud_veri[s]['kart_state'], (
            '%s için kapsayıcıya data-state konmuyor — kart varsayılan '
            'yeşil LED\'e düşer' % s)
        assert hud_veri[s]['led_state'], (
            '%s için LED\'e data-state konmuyor — CSS kademesi yüzünden '
            'renk LED\'e ulaşmaz (bkz. P17B2-01)' % s)


@needs_node
def test_p12ab4_18_sozluk_disi_sozcuge_guvenlik_sinifi_uydurulmuyor(hud_veri):
    """Sahte veri yasağı: sınıflandırılamayan sözcük merdivenin BEŞ
    sınıfından hiçbirini almaz. Isıl bir sözcüğü yapısal merdivene almak
    ayrı ve semantik bir karardır; bu onarım onu VERMEZ."""
    for s in (SOZLUK_DISI, SENTETIK):
        assert hud_veri[s]['kart_state'] not in HUKUM_MERDIVENI, (
            '%s sözcüğüne güvenlik sınıfı uyduruldu: %r'
            % (s, hud_veri[s]['kart_state']))
        assert hud_veri[s]['led_state'] not in HUKUM_MERDIVENI, s


@needs_node
def test_p12ab4_18_ham_hukum_sozcugu_cevrilmeden_tasiniyor(hud_veri):
    """Renk tek kanal değil: sınıflandırılamayan sözcüğün KENDİSİ LED'de
    `data-verdict` + `aria-label` olarak durur (uydurma metin yok)."""
    for s in (SOZLUK_DISI, SENTETIK):
        assert hud_veri[s]['led_verdict'] == s, hud_veri[s]
        assert hud_veri[s]['led_aria'] == s, hud_veri[s]


@needs_node
def test_p12ab4_18_bilinen_bes_sozcuk_degismedi(hud_veri):
    """Onarım merdiveni bozmamalı: beş sözcük eskisi gibi eşleşir."""
    beklenen = {'SAFE': 'safe', 'ACCEPTABLE': 'acceptable',
                'MARGINAL': 'marginal', 'UNSAFE': 'unsafe',
                'NOT_EVALUATED': 'not-evaluated'}
    for sozcuk, durum in beklenen.items():
        assert hud_veri[sozcuk]['kart_state'] == durum, hud_veri[sozcuk]
        assert hud_veri[sozcuk]['led_state'] == durum, hud_veri[sozcuk]


@needs_node
def test_p12ab4_18_hukum_hic_yoksa_oznitelik_konmuyor(hud_veri):
    """FAIL-CLOSED'ın öbür yüzü: hüküm HİÇ verilmemişse (null ya da yalnız
    boşluk) uydurma bir durum da konmaz — söylenecek bir şey yoktur."""
    for s in ('(bos)', '   '):
        assert hud_veri[s]['kart_state'] is None, hud_veri[s]
        assert hud_veri[s]['led_state'] is None, hud_veri[s]
        assert hud_veri[s]['led_verdict'] is None, hud_veri[s]


def test_p12ab4_18_merdiven_genisletilmedi():
    """Sözlük tam olarak arka ucun BEŞ yapısal sözcüğü olarak kalır."""
    hud = _oku(JS / 'hud.js')
    m = re.search(r'var STATE_MAP = \{([^}]*)\}', hud)
    assert m, 'STATE_MAP bulunamadı'
    anahtarlar = set(re.findall(r'([A-Z_]+)\s*:', m.group(1)))
    assert anahtarlar == {'SAFE', 'ACCEPTABLE', 'MARGINAL', 'UNSAFE',
                          'NOT_EVALUATED'}, anahtarlar
    degerler = set(re.findall(r":\s*'([a-z-]+)'", m.group(1)))
    assert degerler == HUKUM_MERDIVENI, degerler


def test_p12ab4_18_css_notr_durumu_tanimliyor():
    """`unrecognized` durumu CSS'te tanımlı, NÖTR ve NOT_EVALUATED'dan
    ayırt edilebilir olmalı; aksi hâlde öznitelik konsa da kart yine
    varsayılan yeşil LED'i gösterirdi."""
    css = _oku(CSS / 'results_hud.css')
    kap = re.search(r'\[data-state="unrecognized"\]\s*\{([^}]*)\}', css)
    assert kap, 'CSS `unrecognized` durumunu tanımlamıyor'
    assert '--led' in kap.group(1) and '--state-ink' in kap.group(1), kap.group(1)
    assert ONAY_YESILI_DEGISKENI not in kap.group(1), (
        'sınıflandırılamayan hüküm ONAY YEŞİLİ alıyor: %r' % kap.group(1))

    led = re.search(r'\[data-state="unrecognized"\] \.hd-led \{([^}]*)\}', css)
    assert led, '`unrecognized` LED kuralı yok'
    assert 'background: transparent' in led.group(1), led.group(1)
    assert 'dashed' in led.group(1), (
        'kesik çerçeve yok — `unrecognized` NOT_EVALUATED\'ın düz çerçeveli '
        'boş LED\'inden ayırt edilemiyor: %r' % led.group(1))
    hukumsuz = re.search(
        r'\[data-state="not-evaluated"\] \.hd-led \{([^}]*)\}', css)
    assert hukumsuz and 'solid' in hukumsuz.group(1), hukumsuz


def test_p12ab4_18_canli_olcum_kayitli():
    """CANLI Chrome ölçümü (getComputedStyle) kanıt dizininde durmalı ve
    onarımı sayıyla göstermeli: sözlük dışı 2 sözcüğün 2'si onay yeşiline
    düşüyordu, artık 0'ı düşüyor."""
    once = json.loads(_oku(kanit_gerekli(KANIT / 'once_b4_18.json')))['ozet']
    sonra = json.loads(_oku(kanit_gerekli(KANIT / 'sonra_b4_18.json')))['ozet']
    assert once['sozluk_disi_onay_yesiline_dusen'] == 2, once
    assert sonra['sozluk_disi_onay_yesiline_dusen'] == 0, sonra
    assert sonra['sozluk_disi_data_state_alan'] == 2, sonra
    assert sonra['sozluk_disi_ham_sozcugu_tasiyan'] == 2, sonra
    # Beş bilinen sözcük iki koşumda da doğru — onarım merdiveni bozmadı.
    assert once['bilinen_bes_sozcuk_dogru'] == 5, once
    assert sonra['bilinen_bes_sozcuk_dogru'] == 5, sonra


# ===========================================================================
# P12aB5-04 ŞARTI — kanıt betiği "beyansız düşen"i gerçekten beyansızdan sayar
# ===========================================================================
# Sentetik envanter: iki sayfa, iki AYRI düşme sebebi.
#   /sentetik-kirpma : SENTETIK_SAYISAL sayısal alan -> tavan üstü kalan düşer
#   /sentetik-konum  : 3 sayısal + 2 koordinat -> 2 alan konum yüzünden düşer
SENTETIK_SAYISAL = 70    # /sentetik-kirpma sayfasındaki sayısal alan sayısı
KONUM_DUSEN = 2


def _tavan():
    """TEK KAYNAK: kırpma tavanı ürün modülünden okunur, burada
    yeniden yazılmaz (aksi hâlde sabit iki yerde yaşardı)."""
    m = re.search(r'var MAX_INPUT_FIELDS\s*=\s*(\d+)',
                  (JS / 'bug_report.js').read_text(encoding='utf-8'))
    assert m, 'MAX_INPUT_FIELDS bulunamadı'
    return int(m.group(1))


TAVAN_USTU = SENTETIK_SAYISAL - _tavan()
TOPLAM_DUSEN = TAVAN_USTU + KONUM_DUSEN

SENTETIK_ENVANTER = {
    '/sentetik-kirpma': (
        [{'id': 'alan_%d' % i, 'type': 'number', 'value': str(i + 1)}
         for i in range(SENTETIK_SAYISAL)]),
    '/sentetik-konum': (
        [{'id': 'alan_%d' % i, 'type': 'number', 'value': str(i + 1)}
         for i in range(3)]
        + [{'id': 'ls-lat', 'type': 'number', 'value': '28.6084'},
           {'id': 'ls-lon', 'type': 'number', 'value': '-80.6043'}]),
}


def _olcumu_kos(tmp_path, js_kok=None):
    """`olcum_b5_0405.js`i sentetik envanterle koşar (Flask'a gerek yok)."""
    env_json = tmp_path / 'envanter.json'
    env_json.write_text(json.dumps(SENTETIK_ENVANTER), encoding='utf-8')
    cikti = tmp_path / 'olcum.json'
    ortam = dict(os.environ,
                 HRMA_KOK=str(REPO),
                 HRMA_JS_KOK=str(js_kok or REPO),
                 HRMA_ENVANTER_JSON=str(env_json))
    res = subprocess.run([NODE, kanit_gerekli(str(OLCUM_B5)), str(cikti)],
                         capture_output=True, text=True, timeout=180,
                         env=ortam)
    assert res.returncode == 0, res.stderr
    return json.loads(cikti.read_text(encoding='utf-8'))


@needs_node
def test_p12ab5_04_sart_beyanli_dusen_beyansiz_sayilmiyor(tmp_path):
    """ÖNCE (Fable-D18 kısım-2 bulgusu): betik beyanlı düşenleri de
    `toplam_beyansiz_dusen_alan`a topluyordu; `sonra_b5_0405.json` 31
    yazarken rapor 0 diyordu."""
    d = _olcumu_kos(tmp_path)
    ozet = d['ozet']
    assert ozet['toplam_dusen_alan'] == TOPLAM_DUSEN, ozet
    assert ozet['toplam_beyansiz_dusen_alan'] == 0, (
        'beyanlı düşen alanlar hâlâ "beyansız" sayılıyor: %s' % ozet)
    assert ozet['toplam_beyansiz_dusen_alan_kaba'] == 0, ozet
    for yol, s in d['kirpma'].items():
        assert s['sebep_mutabakati'], (yol, s)
        assert s['beyansiz_dusen'] == 0, (yol, s)


@needs_node
def test_p12ab5_04_sart_iki_dusme_sebebi_ayri_beyanla_eslesiyor(tmp_path):
    """Kırpma ve konum AYRI beyanlardır; betik hangisinin beyanlı olduğunu
    ayrı ayrı kaydeder (ŞART: `/launch-site` için `konum_beyani_var`)."""
    d = _olcumu_kos(tmp_path)
    kirpma = d['kirpma']['/sentetik-kirpma']
    konum = d['kirpma']['/sentetik-konum']
    assert kirpma['kirpma_dusen'] == TAVAN_USTU, kirpma
    assert kirpma['geo_dusen'] == 0, kirpma
    assert kirpma['kirpma_beyani_var'] is True, kirpma
    assert konum['geo_dusen'] == KONUM_DUSEN, konum
    assert konum['kirpma_dusen'] == 0, konum
    assert konum['konum_beyani_var'] is True, konum
    # Alan HER sayfa için kaydedilir, yalnız /launch-site için değil.
    for yol, s in d['kirpma'].items():
        assert 'konum_beyani_var' in s, yol


@needs_node
def test_p12ab5_04_sart_beyan_silinince_alan_kirmizi_veriyor(tmp_path):
    """Alan sabit 0 DEĞİL: beyan gövdeden çıkarılırsa düşen alanların
    tamamı beyansız sayılır. (Ürün dosyası kopyalanır; ağaç değişmez.)"""
    sahte = tmp_path / 'sahte_kok' / 'hrma' / 'static' / 'js'
    sahte.mkdir(parents=True)
    for ad in ('bug_report.js', 'settings_panel.js'):
        (sahte / ad).write_text(_oku(JS / ad), encoding='utf-8')
    kaynak = _oku(JS / 'bug_report.js')
    kirik = (kaynak
             .replace("L.push('> `warn.bugreport.inputs_truncated`');", '')
             .replace("L.push('> `warn.bugreport.geo_withheld`');", ''))
    assert kirik != kaynak, 'beyan satırları bulunamadı — bekçi kör'
    (sahte / 'bug_report.js').write_text(kirik, encoding='utf-8')

    d = _olcumu_kos(tmp_path, js_kok=tmp_path / 'sahte_kok')
    ozet = d['ozet']
    assert ozet['toplam_dusen_alan'] == TOPLAM_DUSEN, ozet
    assert ozet['toplam_beyansiz_dusen_alan'] == TOPLAM_DUSEN, (
        'beyan silindiği hâlde "beyansız düşen" 0 kaldı — alan gerçeği '
        'ölçmüyor: %s' % ozet)
    assert ozet['toplam_beyansiz_dusen_alan_kaba'] == TOPLAM_DUSEN, ozet


def test_p12ab5_04_sart_kanit_json_ile_rapor_hizali():
    """ŞARTın son ayağı: rapor.md'deki manşet sayı JSON'la BİREBİR aynı
    olmalı (eskiden rapor 0, JSON 31 diyordu)."""
    once = json.loads(_oku(kanit_gerekli(D18 / 'once_b5_0405.json')))['ozet']
    sonra = json.loads(_oku(kanit_gerekli(D18 / 'sonra_b5_0405.json')))['ozet']
    assert once['toplam_beyansiz_dusen_alan'] == 29, once
    assert sonra['toplam_beyansiz_dusen_alan'] == 0, sonra
    assert once['toplam_dusen_alan'] == 29, once
    assert sonra['toplam_dusen_alan'] == 31, sonra

    rapor = _oku(kanit_gerekli(D18 / 'rapor.md'))
    assert re.search(
        r'Toplam \*\*beyansız\*\* düşen alan: \*\*%d → %d\*\*'
        % (once['toplam_beyansiz_dusen_alan'],
           sonra['toplam_beyansiz_dusen_alan']), rapor), (
        'rapor.md beyansız manşeti JSON ile hizalı değil')
    assert re.search(
        r'Toplam düşen alan \(beyanlı \+ beyansız\): \*\*%d → %d\*\*'
        % (once['toplam_dusen_alan'], sonra['toplam_dusen_alan']), rapor), (
        'rapor.md toplam düşen manşeti JSON ile hizalı değil')


def test_p12ab5_04_sart_alan_adi_artik_yaniltmiyor():
    """Betikte "tüm düşenler" ile "beyansız düşenler" AYRI iki alandır."""
    src = _oku(kanit_gerekli(OLCUM_B5))
    assert 'toplam_dusen_alan:' in src, 'toplam düşen alanı yayımlanmıyor'
    assert 'toplam_beyansiz_dusen_alan:' in src
    assert 'warn\\.bugreport\\.geo_withheld' in src, (
        'konum beyanı hiç aranmıyor — geo yüzünden düşen alan "beyansız" '
        'sayılırdı')
