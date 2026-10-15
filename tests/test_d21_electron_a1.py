# -*- coding: utf-8 -*-
"""ÖH Dalga-21 / kulvar `electron`, aşama 1 — kabuk + fırlatma sahası bekçileri.

Kapatılan kalemler (parti P12A, bulucu 4 ve 5):

  P12aB4-17  `hud.js` STATE_MAP backend'in ürettiği BEŞ yapısal hüküm
             sözcüğünden üçünü tanıyordu; 'ACCEPTABLE' ve 'NOT_EVALUATED'
             hiç `data-state` almıyor, kart CSS varsayılanı olan YEŞİL LED'e
             düşüyordu (onayı geri çekilmiş hüküm "sorunsuz" görünüyordu).
  P12aB4-19  `getTileInfo()` "çevrimdışı notu" yayımladığını beyan ediyordu
             ama notun ekranda düğümü yoktu; `attribution` alanı hiç
             okunmuyordu (aynı künyenin ikinci kaynağı).
  P12aB4-20  Düz malzeme renklerinin bir kısmı `srgb()` dönüşümünü atlıyordu:
             kıyı/sınır çizgileri ve dokusuz küre ekranda açık çıkıyordu.
  P12aB4-21  Proje kartlarındaki sayılar her dilde nokta ondalık ayırıcı
             kullanıyordu (`toFixed`), ürünün geri kalanı TR'de virgül basar.
  P12aB4-22  `FlightHandoff.readLast`/`clear` ölüydü; launch_site.html
             depolama anahtarını kendi kopyalıyordu (iki kaynak).
  P12aB4-23  `project_bar.escapeHtml` ölü koddu; kirli yıldızının ipucu dil
             değişiminde eski dilde kalıyordu.
  P12aB4-25  Küre modülünün konsol uyarıları Türkçe sabitti.
  P12aB4-26  `TILE_MIN_ZOOM` yorumu davranışı yanlış anlatıyordu (atlama
             değil kırpma).
  P12aB5-07  /launch-site'ta "Şimdi denetle" "güncelleme penceresi açılıyor"
             yazıyor ama `update_check.js` o sayfada yüklü değildi.

Bekçilerin çoğu ÜRÜN DAVRANIŞINI ölçer (node ile gerçek modül yüklenir,
asgari DOM/depolama kurulur, üretilen değer okunur). Kaynak metnini sınayan
denetimler TEK KAYNAK sözleşmesi ve künye dürüstlüğü içindir.

Ham kanıt: docs/scofield/raw/OH/D21/electron/a1/
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
JS = REPO / 'hrma' / 'static' / 'js'
CSS = REPO / 'hrma' / 'static' / 'css'
TPL = REPO / 'hrma' / 'templates'
NODE = shutil.which('node')

needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(p):
    return p.read_text(encoding='utf-8')


def _yorumsuz(metin):
    """Yorum satırlarını ve HTML yorum bloklarını atar.

    Bekçiler KODU sınar; kusurun tarihçesini anlatan yorumlar (içinde eski
    kod parçası geçebilir) yanlış kırmızı üretmemeli.
    """
    metin = re.sub(r'<!--.*?-->', '', metin, flags=re.S)
    metin = re.sub(r'/\*.*?\*/', '', metin, flags=re.S)
    return '\n'.join(s for s in metin.splitlines()
                     if not s.strip().startswith(('//', '*')))


def _node(kaynak, tmp_path, ad='bekci.js'):
    h = tmp_path / ad
    h.write_text(kaynak, encoding='utf-8')
    res = subprocess.run([NODE, str(h), str(JS)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, 'node koşumu hata verdi:\n' + res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def _sozluk(path, lang):
    """i18n sözlük bloğunu (anahtar -> ham değer) çıkarır."""
    kaynak = _oku(path)
    m = re.search(r'^\s{8}%s:\s*\{' % lang, kaynak, re.M)
    assert m, '%s içinde %r bloğu yok' % (path.name, lang)
    govde = kaynak[m.end():]
    return dict(re.findall(r"^\s*'([^']+)':\s*'(.*)',?$",
                           govde[:govde.index('\n        }')], re.M))


# ===========================================================================
# P12aB4-17 — yapısal hüküm sözlüğünün kapsamı
# ===========================================================================
def _backend_hukum_sozcukleri():
    """structural_analysis.py'nin ÜRETEBİLDİĞİ hüküm sözcükleri (tek kaynak)."""
    src = _oku(REPO / 'hrma' / 'analysis' / 'structural_analysis.py')
    merdiven = re.search(r'STRUCTURAL_RISK_LADDER = \((.*?)\)\n', src, re.S)
    assert merdiven, 'STRUCTURAL_RISK_LADDER bulunamadı'
    sozcukler = set(re.findall(r"'([A-Z_]+)',\s*'[A-Z ]+'\)", merdiven.group(1)))
    sozcukler.add(re.search(r"STRUCTURAL_RISK_TOP = \('([A-Z]+)'", src).group(1))
    sozcukler.add(re.search(
        r"STRUCTURAL_VERDICT_NOT_EVALUATED = '([A-Z_]+)'", src).group(1))
    assert len(sozcukler) == 5, sozcukler
    return sozcukler


HUD_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];

/* Asgari DOM: yalnız data-state öznitelik defteri. */
function elem() {
    const attrs = {};
    return {
        attrs,
        setAttribute(k, v) { attrs[k] = String(v); },
        removeAttribute(k) { delete attrs[k]; },
        getAttribute(k) { return (k in attrs) ? attrs[k] : null; },
    };
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
const sonuc = {};
for (const s of SOZCUKLER) {
    const el = elem();
    sandbox.HRMAHud.bindState(el, s);
    sonuc[s] = el.getAttribute('data-state');
}
/* ÖH D24 / P12aB4-18 — BEKÇİ ÇEVRİLDİ. Eskiden burada tanınmayan sözcüğün
   HİÇ öznitelik almaması bekleniyordu (`uydurma is None`). ÖLÇÜLDÜ ki bu
   beklenti kusuru KORUYORDU: öznitelik konmayınca `.hd-led` kendi yedeğine
   (--hd-green) düşüyor ve sözlük dışı GERÇEK bir arka uç hükmü
   (`EXCEEDS_ALLOWABLE`) ekranda ONAY YEŞİLİ oluyordu — CANLI Chrome
   ölçümü rgb(45, 212, 168); raw/OH/D24/electron/a1/once_b4_18.json.
   Yeni beklenti DAHA DAR: tanınmayan sözcük merdivenin beş sınıfından
   HİÇBİRİNİ almaz (uydurma sınıflandırma yok) ama özniteliksiz de kalmaz
   (sessiz yeşile düşüş yok). */
const bilinmeyen = elem();
sandbox.HRMAHud.bindState(bilinmeyen, 'HOKUS_POKUS');
/* Hüküm HİÇ verilmemişse öznitelik konmamalı — söylenecek bir şey yok. */
const bos = elem();
sandbox.HRMAHud.bindState(bos, null);
console.log(JSON.stringify({
    eslesme: sonuc,
    bilinmeyen_durum: bilinmeyen.getAttribute('data-state'),
    bilinmeyen_verdict: bilinmeyen.getAttribute('data-verdict'),
    hukumsuz_durum: bos.getAttribute('data-state'),
}));
"""


@needs_node
def test_p12ab4_17_bes_hukum_sozcugu_de_data_state_aliyor(tmp_path):
    """ÖNCE (ölçüldü): 5 sözcüğün 2'si (ACCEPTABLE, NOT_EVALUATED) öznitelik
    ALMIYORDU; hud.js tanımadığında `removeAttribute` çağırıyor ve kart
    `.hd-led` varsayılanı olan `--hd-green`e düşüyordu."""
    import os
    sozcukler = sorted(_backend_hukum_sozcukleri())
    h = tmp_path / 'hud_bekci.js'
    h.write_text(HUD_HARNESS, encoding='utf-8')
    ortam = dict(os.environ, HRMA_SOZCUKLER=json.dumps(sozcukler))
    res = subprocess.run([NODE, str(h), str(JS)], capture_output=True,
                         text=True, timeout=120, env=ortam)
    assert res.returncode == 0, res.stderr
    veri = json.loads(res.stdout.strip().splitlines()[-1])

    # ÖH D33-KOLAY · P12aB4-17 denetim ŞARTI — ÖLÇÜT ÇEVRİLDİ.
    #
    # ESKİ ölçüt `if not v` idi: "öznitelik BOŞ mu?". D24'ün (30ef9b7e)
    # getirdiği UNRECOGNIZED_STATE yedeğinden sonra bu ölçüt KÖRDÜ —
    # `bindState` tanımadığı sözcüğe artık 'unrecognized' YAZIYOR, yani
    # öznitelik hiçbir zaman boş kalmıyor. ÖLÇÜLDÜ (``a2/once.json`` K2,
    # gerileme ikizi: STATE_MAP D21 öncesi ÜÇ sözcüğe geriletilir):
    # `not v` ölçütü 0 sözcük yakalıyor, merdiven ölçütü 2 sözcük
    # (ACCEPTABLE, NOT_EVALUATED) yakalıyor. Yani eski ölçütle STATE_MAP
    # sessizce üç sözcüğe gerileyebilir ve bekçi yeşil kalırdı.
    #
    # Yeni ölçüt: backend'in ÜRETTİĞİ bir sözcük asla D24'ün nötr
    # 'unrecognized' kovasına DÜŞMEMELİ — merdivenin beş sınıfından
    # birine girmeli.
    merdiven = {'safe', 'acceptable', 'marginal', 'unsafe', 'not-evaluated'}
    tanimsiz = [s for s, v in veri['eslesme'].items() if v not in merdiven]
    assert not tanimsiz, (
        'backend bu hüküm sözcüklerini üretiyor ama hud.js onları '
        'merdivenin bir sınıfına koymuyor (sözlük dışı kovaya düşüyorlar; '
        'kart hükmün rengini almaz): %s'
        % [(s, veri['eslesme'][s]) for s in tanimsiz])
    # Tanınmayan dize merdivenin BEŞ sınıfından hiçbirini almamalı
    # (uydurma sınıflandırma yok) — ama özniteliksiz de kalmamalı, çünkü
    # öznitelik yokluğu `.hd-led`i varsayılan ONAY YEŞİLİNE düşürüyor
    # (ÖH D24 / P12aB4-18, CANLI ölçüm once_b4_18.json).
    assert veri['bilinmeyen_durum'] not in merdiven, (
        'tanınmayan sözcüğe güvenlik sınıfı UYDURULDU: %r'
        % veri['bilinmeyen_durum'])
    assert veri['bilinmeyen_durum'], (
        'tanınmayan sözcük öznitelik almıyor — kart varsayılan yeşil LED\'e '
        'düşer (fail-open)')
    # (Ham sözcük `data-verdict` olarak LED düğümüne yazılır — bu asgari
    # DOM'da .hd-led yok; o ayak tests/test_d24_electron_a1.py'de ve CANLI
    # ölçümde (sonra_b4_18.json) bekçili.)
    # Hüküm HİÇ verilmemişse öznitelik de konmaz.
    assert veri['hukumsuz_durum'] is None, veri['hukumsuz_durum']


def test_p12ab4_17_her_durum_icin_css_murekkep_tanimli():
    """data-state konmuş her kart için `--state-ink` tanımlı olmalı; aksi
    hâlde öznitelik var ama kart yine nötr görünürdü."""
    hud = _oku(JS / 'hud.js')
    m = re.search(r'var STATE_MAP = \{([^}]*)\}', hud)
    degerler = set(re.findall(r":\s*'([a-z-]+)'", m.group(1)))
    css = _oku(CSS / 'results_hud.css')
    tanimli = set(re.findall(r'\[data-state="([a-z-]+)"\][^\n]*--state-ink', css))
    assert degerler <= tanimli, (
        'CSS bu durumlar için --state-ink tanımlamıyor: %s'
        % sorted(degerler - tanimli))


def test_p12ab4_17_hukumsuz_kart_yesil_lede_dusmuyor():
    """NOT_EVALUATED bir hüküm DEĞİL, hükmün geri çekilmesidir: LED'i dolu
    yeşil (varsayılan) olamaz — içi boş çizilir."""
    css = _oku(CSS / 'results_hud.css')
    blok = re.search(
        r'\[data-state="not-evaluated"\] \.hd-led \{([^}]*)\}', css)
    assert blok, 'hükümsüz durumun LED kuralı yok'
    assert 'background: transparent' in blok.group(1)
    assert 'border:' in blok.group(1)


# ===========================================================================
# P12aB4-19 — çevrimdışı karo notu + atıf tek kaynakta
# ===========================================================================
def test_p12ab4_19_atif_metni_kure_modulunde_yazili_degil():
    """Künye METNİ tek kaynakta (i18n sözlüğü) durur; modül yalnız katmanın
    ANAHTARINI yayımlar. Aksi hâlde aynı cümlenin iki kaynağı olurdu."""
    globe = _oku(JS / 'launch_site_globe.js')
    gov = globe[globe.index('LaunchSiteGlobe.prototype.getTileInfo'):
                globe.index('LaunchSiteGlobe.prototype._updateTilePatch')]
    assert 'attributionKey' in gov, 'katman -> künye anahtarı yayımlanmıyor'
    assert 'NASA GIBS' not in gov, (
        'atıf metni küre modülünde yeniden yazılmış — i18n sözlüğüyle '
        'çift kaynak')


def test_p12ab4_19_cevrimdisi_notu_gercek_tuketiciye_bagli():
    """ÖNCE (ölçüldü): `anyFail`/`attribution` alanlarının DOM tüketicisi
    yoktu; karolar düştüğünde ekranda hiçbir not çıkmıyordu."""
    html = _oku(TPL / 'launch_site.html')
    assert 'id="ls-tile-offline"' in html, 'çevrimdışı notu düğümü yok'
    assert re.search(r"el\('ls-tile-offline'\)\.style\.display\s*=\s*"
                     r"\(info\.failedCount > 0\)", html), (
        'çevrimdışı notu düşen karo sayısına bağlı değil')
    # Atıf artık modülün yayımladığı anahtardan kurulur.
    assert 'info.attributionKey' in html


def test_p12ab4_19_cevrimdisi_notu_ceviride_var():
    en = _sozluk(JS / 'i18n_launch_site.js', 'en')
    tr = _sozluk(JS / 'i18n_launch_site.js', 'tr')
    assert 'site.tileOffline' in en and 'site.tileOffline' in tr
    assert set(en) == set(tr), 'EN/TR anahtar paritesi bozuldu'


# ===========================================================================
# P12aB4-20 — sRGB kalıntısı
# ===========================================================================
def test_p12ab4_20_duz_malzeme_renkleri_lineere_cevriliyor():
    """Çıkış sRGB kodlandığı için düz malzeme rengine verilen HAM hex ekranda
    açılır. ÖNCE (ölçüldü): 5 renk (kıyı, sınır, dokusuz küre + iki specular)
    `srgb()` dönüşümünü atlıyordu."""
    globe = _oku(JS / 'launch_site_globe.js')
    kacaklar = []
    desenler = (r'(?:color|specular):\s*(srgb\()?(0x[0-9a-fA-F]{6})',
                r'mkLines\(layers\.\w+,\s*(srgb\()?(0x[0-9a-fA-F]{6})')
    satirlar = globe.splitlines()
    for desen in desenler:
        for m in re.finditer(desen, globe):
            ln = globe[:m.start()].count('\n')
            if satirlar[ln].strip().startswith('//'):
                continue
            if m.group(1) or m.group(2).lower() == '0xffffff':
                continue          # sarılı ya da beyaz (iki uzayda da 1,0)
            kacaklar.append('%d: %s' % (ln + 1, satirlar[ln].strip()))
    assert not kacaklar, (
        'srgb() atlanmış düz malzeme rengi (ekranda açılır):\n' +
        '\n'.join(kacaklar))


# ===========================================================================
# P12aB4-21 — ondalık ayırıcı
# ===========================================================================
SAYI_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];
const src = fs.readFileSync(path.join(JSDIR, 'project_bar.js'), 'utf8');

/* summaryMini + nf gövdelerini kaynaktan SÖKÜP çalıştır: dosyanın geri
   kalanı (DOM/fetch) gerekmesin ama ölçülen KOD gerçek kod olsun. */
function govde(ad) {
    const i = src.indexOf('function ' + ad + '(');
    if (i < 0) throw new Error(ad + ' bulunamadı');
    let derinlik = 0, j = src.indexOf('{', i);
    for (let k = j; k < src.length; k++) {
        if (src[k] === '{') derinlik++;
        else if (src[k] === '}') { derinlik--; if (!derinlik) return src.slice(i, k + 1); }
    }
    throw new Error(ad + ' gövdesi kapanmadı');
}

const ozet = { thrust_N: 1000.4, isp_s: 207.14, total_impulse_Ns: 13428.2 };
const cikti = {};
for (const dil of ['en', 'tr']) {
    const sandbox = { console: { log() {} } };
    sandbox.window = sandbox;
    sandbox.window.I18N = {
        lang: dil,
        number(v, d) {
            if (typeof v !== 'number' || !isFinite(v)) return String(v);
            let t = (typeof d === 'number') ? v.toFixed(d) : String(v);
            if (this.lang === 'tr') t = t.replace('.', ',');
            return t;
        },
    };
    vm.createContext(sandbox);
    vm.runInContext(govde('nf') + '\n' + govde('summaryMini')
                    + '\nglobals = summaryMini(' + JSON.stringify(ozet) + ');',
                    sandbox, { filename: 'project_bar_parca.js' });
    cikti[dil] = sandbox.globals;
}
/* Sözlük motoru hiç yokken de sayı basılmalı (çıplak yedek). */
const bos = { console: { log() {} } };
bos.window = bos;
vm.createContext(bos);
vm.runInContext(govde('nf') + '\n' + govde('summaryMini')
                + '\nglobals = summaryMini(' + JSON.stringify(ozet) + ');',
                bos, { filename: 'project_bar_parca.js' });
cikti.sozluksuz = bos.globals;
console.log(JSON.stringify(cikti));
"""


@needs_node
def test_p12ab4_21_proje_karti_sayilari_dilin_ayiricisini_kullaniyor(tmp_path):
    """ÖNCE (ölçüldü): `summaryMini` doğrudan `toFixed` çağırıyordu, TR
    kipinde kart "Isp 207.1 s" basıyordu (ürünün geri kalanı "207,1")."""
    veri = _node(SAYI_HARNESS, tmp_path, 'sayi_bekci.js')
    assert 'Isp 207.1 s' in veri['en'], veri['en']
    assert 'Isp 207,1 s' in veri['tr'], (
        'TR kipinde proje kartı hâlâ nokta ondalık ayırıcı basıyor: %s'
        % veri['tr'])
    assert '.' not in veri['tr'].replace('·', ''), veri['tr']
    # Sözlük yoksa sayı yine basılır (boş/uydurma değer YOK).
    assert 'Isp 207.1 s' in veri['sozluksuz'], veri['sozluksuz']


def test_p12ab4_21_import_ozeti_de_ayni_bicimleyiciden_geciyor():
    """`I18N.tf` yalnız SAYI tipini biçimler; fmtNum dizge verdiği için
    ayırıcı TR'de de nokta kalıyordu."""
    iu = _oku(JS / 'import_ui.js')
    gov = iu[iu.index('function fmtNum('):iu.index('function metaLineHtml(')]
    assert 'I18N.number' in gov, 'fmtNum tek kaynaktan biçimlemiyor'
    assert "'--'" in gov, 'sonlu olmayan değer için fail-closed dal kayboldu'


# ===========================================================================
# P12aB4-22 — köprünün kendi API'si
# ===========================================================================
KOPRU_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];

function kur(depo) {
    const sandbox = { console: { log() {}, warn() {}, debug() {} } };
    sandbox.window = sandbox;
    sandbox.window.localStorage = depo;
    sandbox.document = { getElementById() { return null; } };
    sandbox.location = { pathname: '/launch-site' };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(JSDIR, 'flight_handoff.js'), 'utf8'),
                    sandbox, { filename: 'flight_handoff.js' });
    return sandbox.window.FlightHandoff;
}
function depo(deger) {
    const kutu = { v: deger };
    return {
        kutu,
        getItem() { return kutu.v; },
        setItem(k, v) { kutu.v = v; },
        removeItem() { kutu.v = null; },
    };
}
const sonuc = {};
for (const [ad, ham] of [['bos', null],
                         ['bozuk', '{ bu json degil'],
                         ['saglam', JSON.stringify({ vehicle: { thrust: 1234 } })]]) {
    const d = depo(ham);
    const FH = kur(d);
    const out = {};
    const kayit = FH.readLast(out);
    sonuc[ad] = { status: out.status, kayitVar: !!kayit };
}
/* Depolama tümden patlıyorsa 'empty' DEĞİL 'unreadable' denmeli. */
const patlak = { getItem() { throw new Error('kapalı'); }, removeItem() {} };
const FHp = kur(patlak);
const outp = {};
FHp.readLast(outp);
sonuc.patlak = { status: outp.status };
/* clear() gerçekten siliyor mu? */
const d2 = depo('x');
const FH2 = kur(d2);
FH2.clear();
sonuc.clearSiliyor = d2.kutu.v === null;
sonuc.anahtar = FH2.STORAGE_KEY;
console.log(JSON.stringify(sonuc));
"""


@needs_node
def test_p12ab4_22_readLast_kayit_yok_ile_okunamadi_durumunu_ayiriyor(tmp_path):
    """ÖNCE (ölçüldü): `readLast` iki durumda da null dönüyordu; tüketici
    bozuk kaydı "henüz hesap yapılmamış" diye raporlayacaktı (sessiz yedek)."""
    veri = _node(KOPRU_HARNESS, tmp_path, 'kopru_bekci.js')
    assert veri['bos'] == {'status': 'empty', 'kayitVar': False}, veri['bos']
    assert veri['bozuk'] == {'status': 'unreadable', 'kayitVar': False}, veri['bozuk']
    assert veri['saglam'] == {'status': 'ok', 'kayitVar': True}, veri['saglam']
    assert veri['patlak']['status'] == 'unreadable', veri['patlak']
    assert veri['clearSiliyor'] is True
    assert veri['anahtar'] == 'hrma.flight.lastVehicle'


def test_p12ab4_22_launch_site_kopru_apisini_kullaniyor():
    """ÖNCE (ölçüldü): sayfa `var HANDOFF_KEY = 'hrma.flight.lastVehicle'`
    diye İKİNCİ bir anahtar bildirip localStorage'a doğrudan gidiyordu;
    `FlightHandoff.readLast`/`clear` çağrısı 0'dı."""
    ham = _oku(TPL / 'launch_site.html')
    assert 'flight_handoff.js' in ham, 'köprü betiği yüklenmiyor'
    html = _yorumsuz(ham)
    assert 'FlightHandoff.readLast(' in html
    assert 'FlightHandoff.clear(' in html
    assert 'var HANDOFF_KEY' not in html, 'ikinci anahtar sabiti geri geldi'
    # Anahtar dizgesinin TEK kaynağı köprü modülüdür.
    assert "'hrma.flight.lastVehicle'" not in html


# ===========================================================================
# P12aB4-23 — ölü kaçış yardımcısı + dil değişiminde ipucu
# ===========================================================================
def test_p12ab4_23_olu_escapehtml_kalmadi():
    """Ölü güvenlik yardımcısı "burada kaçış yapılıyor" izlenimi verir."""
    kod = _yorumsuz(_oku(JS / 'project_bar.js'))
    assert 'function escapeHtml(' not in kod
    # Kaçış yardımcısı kaldırıldı: bu dosya HTML gövdesine DİZGE gömmemeli.
    # `innerHTML = ''` (kap boşaltma) bir gömme değildir; yasak olan, içine
    # değişken metin yazılmasıdır.
    gommeler = [s.strip() for s in kod.splitlines()
                if 'innerHTML' in s and not re.search(r"innerHTML\s*=\s*''\s*;", s)]
    assert not gommeler, 'HTML gövdesine dizge gömülüyor: %s' % gommeler


def test_p12ab4_23_kirli_yildizinin_ipucu_dil_degisiminde_tazeleniyor():
    """ÖNCE (ölçüldü): `star.title` bir kez atanıyordu, `data-i18n-title`
    taşımıyordu; dil değişince ipucu eski dilde kalıyordu."""
    pb = _yorumsuz(_oku(JS / 'project_bar.js'))
    assert re.search(r"star\.setAttribute\('data-i18n-title',\s*'proj\.dirtyHint'\)",
                     pb), 'kirli yıldızı I18N.apply kanalına bağlı değil'
    i18n = _oku(JS / 'i18n.js')
    assert "data-i18n-title" in i18n, 'i18n.js bu kanalı çevirmiyor'


# ===========================================================================
# P12aB4-25 — konsol tek dilde
# ===========================================================================
def test_p12ab4_25_kure_konsol_metinleri_tek_dilde():
    """Ürünün varsayılan dili İngilizce; konsol metni ekran metni değildir ve
    çevrilmez, ama TEK dilde olmalıdır."""
    globe = _oku(JS / 'launch_site_globe.js')
    tr = re.compile(r'[çğıöşüÇĞİÖŞÜ]')
    kacaklar = []
    for m in re.finditer(r"console\.(?:warn|error|log)\(([^;]{0,200})", globe):
        for dize in re.findall(r"'([^']*)'", m.group(1)):
            if tr.search(dize):
                kacaklar.append(dize)
    # _warnStars'a geçilen gerekçe dizgeleri de aynı konsol satırına gider.
    for m in re.finditer(r"_warnStars\(url,\s*([^;]{0,160})", globe):
        for dize in re.findall(r"'([^']*)'", m.group(1)):
            if tr.search(dize):
                kacaklar.append(dize)
    assert not kacaklar, 'Türkçe konsol metni: %s' % kacaklar


# ===========================================================================
# P12aB4-26 — yorum davranışı doğru anlatıyor
# ===========================================================================
def test_p12ab4_26_tile_min_zoom_yorumu_davranisla_uyusuyor():
    """ÖNCE (ölçüldü): yorum "z<4 … patch yüklenmez" diyordu; kod ise z'yi
    4'e YUKARI kırpıp yine karo istiyordu (atlama yok)."""
    globe = _oku(JS / 'launch_site_globe.js')
    m = re.search(r'var TILE_MIN_ZOOM = (\d+);\s*//([^\n]*)', globe)
    assert m, 'TILE_MIN_ZOOM tanımı bulunamadı'
    yorum = m.group(2)
    clamp_var = bool(re.search(r'z = clamp\(z, TILE_MIN_ZOOM, TILE_MAX_ZOOM\);',
                               globe))
    assert clamp_var, 'kırpma satırı değişti — yorum yeniden denetlenmeli'
    assert 'yüklenmez' not in yorum, (
        'yorum karo İSTENMEDİĞİNİ söylüyor ama kod kırpıp yine istiyor: %r'
        % yorum)


# ===========================================================================
# P12aB5-07 — güncelleme penceresi sözü
# ===========================================================================
def test_p12ab5_07_launch_site_guncelleme_penceresini_yukluyor():
    """ÖNCE (ölçüldü): altı sayfa arasında `update_check.js`i yüklemeyen TEK
    sayfa buydu; `window.hrmaCheckForUpdates` tanımsız kalıyordu."""
    sayfalar = ('advanced.html', 'solid.html', 'liquid.html',
                'index.html', 'formulas.html', 'launch_site.html')
    # Yorumda geçen dosya adı YÜKLEME değildir: betik ETİKETİ aranır.
    etiket = '<script src="/static/js/update_check.js"'
    eksik = [s for s in sayfalar if etiket not in _yorumsuz(_oku(TPL / s))]
    assert not eksik, 'güncelleme köprüsü yüklenmeyen sayfa: %s' % eksik
    # ------------------------------------------------------------------
    # ÖH D31 fix-34b — SÖZLEŞME DEĞİŞTİ, bekçi yeni sözleşmeyi okuyor.
    #
    # Bu ayak eskiden launch_site.html'de
    # ``<script src="/static/js/i18n_common.js">`` ETİKETİNİ arıyordu.
    # OH-D21-06 (D30 arayuz-panel a2, 4757dbf0; ana ağaca 2e6a481a) o
    # etiketi BİLEREK söktü: 505.460 baytlık sözlük, güverte taşımayan bu
    # sayfada yalnız "güncelleme penceresi açılabilir" ihtimali için her
    # açılışta iniyordu, oysa pencere oturumların çoğunda hiç açılmıyor.
    # Sözlük artık TALEP ÜZERİNE gelir: ``update_check.js::sozlukHazir``
    # metin basılmadan ÖNCE betiği enjekte eder ve pencereyi/bildirimi
    # ancak ``onload``/``onerror`` geri çağrımında kurar.
    #
    # İDDİA KORUNUR — "pencerenin metinlerini biri sağlamalı" sorusu aynen
    # sorulur, yalnız sağlayıcı değişti: sayfa değil köprünün kendisi.
    # Ölçülen, o tek kaynağın hâlâ orada olduğudur (ürünün ÇIKTISI
    # test_d27_electron_a1::TestOHD2618KaynakBeyani'nde node ikiziyle
    # ayrıca koşturulur).
    uc = _oku(JS / 'update_check.js')
    assert "tag.src = '/static/js/i18n_common.js';" in uc, (
        'pencerenin metinleri (update.*) i18n_common.js\'te yaşıyor; '
        'talep üzerine yükleyen tek kaynak (sozlukHazir) kalkmış')
    # ÖH D33-2 · OH-UC-13 — BEKÇİ ÇEVRİLDİ (metin kilidi → sözleşme kilidi).
    # Bu iki satır eskiden `cb` DEĞİŞKEN ADINI kilitliyordu ve o ad, kusurun
    # ta kendisini taşıyordu: `force` akışında `sozlukHazir` iki kez çağrılıp
    # ikinci çağrı kendi etiketini görerek erken dönüyor, pencere sözlük
    # inmeden İngilizce çiziliyordu (ölçüm: docs/scofield/raw/OH/D33-2/
    # altyapi/a1/ara_surucu_onarildi.json — lazy kipinde başlık
    # 'UPDATE AVAILABLE', arayüz Türkçe). Onarım geri çağrımı KUYRUK
    # boşaltan bir işleve bağladı; ad kilidi onarımı kırıyordu.
    # İDDİA KORUNUR: "betik inmezse pencere HİÇ kurulmaz (sağır ekran)"
    # sorusu aynen sorulur — yalnız ADA değil BAĞLANMIŞ OLMAYA bakılır.
    onload_m = re.search(r'tag\.onload\s*=\s*(\w+);', uc)
    onerror_m = re.search(r'tag\.onerror\s*=\s*(\w+);', uc)
    assert onload_m and onerror_m, (
        'sözlük enjeksiyonunun onload/onerror geri çağrımı yok: betik '
        'inmezse pencere HİÇ kurulmaz (sağır ekran)')
    assert onload_m.group(1) == onerror_m.group(1), (
        'onload ve onerror farklı geri çağrıma bağlı: başarısız inişte '
        'pencere kurulmayan bir dal kalır (sağır ekran)')
    html = _yorumsuz(_oku(TPL / 'launch_site.html'))
    assert '<script src="/static/js/i18n_common.js"' not in html, (
        'OH-D21-06 geri alındı: 505 KB sözlük yine sayfa açılışında '
        'iniyor (güverte yok, pencere çoğu oturumda açılmıyor)')


def test_p12ab5_07_pencere_sozu_saglayiciya_bagli():
    """Metin KOŞULSUZ, çağrı KOŞULLU yazılmıştı: sağlayıcı yokken ekranda
    "güncelleme penceresi açılıyor" yazıp hiçbir şey olmuyordu."""
    sp = _oku(JS / 'settings_panel.js')
    gov = sp[sp.index('checkBtn.addEventListener'):sp.index('var skipRow')]
    assert 'updateFoundNoWindow' in gov, (
        'sağlayıcı yokken ayrı (söz vermeyen) metin yok')
    assert re.search(r'var pencereVar = !!window\.hrmaCheckForUpdates;', gov)
    assert re.search(r'if \(pencereVar\) window\.hrmaCheckForUpdates\(true\);', gov)
    # Söz veren metin YALNIZ sağlayıcı varken basılmalı.
    soz = gov.index("'shell.settings.updateFound'")
    kosul = gov.index('var pencereVar')
    assert kosul < soz, 'söz veren metin koşuldan önce basılıyor'


def test_p12ab5_07_yeni_anahtar_en_tr_paritesinde():
    en = _sozluk(JS / 'i18n_shell.js', 'en')
    tr = _sozluk(JS / 'i18n_shell.js', 'tr')
    assert 'shell.settings.updateFoundNoWindow' in en
    assert 'shell.settings.updateFoundNoWindow' in tr
    assert set(en) == set(tr), 'EN/TR anahtar paritesi bozuldu'
    for d in (en, tr):
        assert '{version}' in d['shell.settings.updateFoundNoWindow']
