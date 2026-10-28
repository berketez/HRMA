# -*- coding: utf-8 -*-
"""ÖH D35 · sayi-bicimi · a1 — EKRAN SAYI BİÇİMİ BEKÇİSİ.

Kapatılan kusur sınıfı
----------------------
Türkçe oturumda ekrana giden ondalıklar NOKTA ile basılıyordu. Ana modelin
tarayıcı sayımı (22 Eylül, TR, 1440x900, örnek projelerle hesap sonrası
``document.body.innerText``): noktalı ondalık **hibrit 202 / katı 210 /
sıvı 95**, buna karşılık virgüllü yalnız 36 / 20 / 30.

Sebep tek bir hata değil DESENDİ: ayraç kararı her çağrı yerinde ayrı
``toFixed`` ile veriliyordu. Onarım kararı i18n.js kanonuna devretti
(``I18N.number`` / ``I18N.unit`` / ``I18N.percent``), sayfalar da ince
delegatörlerle (``numTxt`` / ``pctTxt`` / ``i18nNumber``) ona bağlandı.

Bu dosyanın iki ayağı
---------------------
1. **KAYNAK** — biçimlendiricilerin kanona bağlı olduğunu ve ham
   ``toFixed`` sayısının ölçülen tavanı aşmadığını dosyadan okur.
2. **DAVRANIŞ** — node altında ``lang='tr'`` ile GERÇEK çıktıyı ölçer.
   Şablon-körü değildir: fonksiyon gövdesi sökülür ve çalıştırılır.

node çağrıları ``tests/test_node_cagri_sozlesmesi.py`` sözleşmesine uyar:
betik **stdin** ile verilir, argv ile değil.
"""
import json
import os
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


def oku(yol):
    return yol.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# 1) KANON — ayraç/birim/yüzde kararı TEK yerde yaşar
# ---------------------------------------------------------------------------
def test_kanon_birim_ve_yuzde_yardimcilari_i18n_dosyasinda():
    """`I18N.unit` / `I18N.percent` i18n.js'te tanımlı olmalı."""
    src = oku(JS / 'i18n.js')
    assert re.search(r'I18N\.unit\s*=\s*function', src), 'I18N.unit yok'
    assert re.search(r'I18N\.percent\s*=\s*function', src), 'I18N.percent yok'


def test_ayrac_karari_tek_kaynakta():
    """Ayraç seçimi yalnız `ondalikAyraci()` içinde yazılı olmalı."""
    src = oku(JS / 'i18n.js')
    # `lang === 'tr') ? ',' : '.'` benzeri karar YALNIZ bir kez geçmeli
    kararlar = re.findall(r"lang\s*===\s*'tr'\s*\)\s*\?\s*','", src)
    assert len(kararlar) == 1, (
        'ondalık ayracı kararı %d yerde yazılı; tek kaynak olmalı '
        '(i18n.js `ondalikAyraci`)' % len(kararlar))


def test_yuzde_yardimcisi_ayraci_kendisi_yazmaz():
    """`I18N.percent` sayıyı `I18N.number`a sormalı (kural iki kez yazılmasın)."""
    src = oku(JS / 'i18n.js')
    govde = src[src.index('I18N.percent = function'):]
    govde = govde[:govde.index('\n    };')]
    assert 'I18N.number(' in govde, 'percent sayıyı kanondan almıyor'
    assert '.toFixed(' not in govde, 'percent kendi biçimini kuruyor'


# ---------------------------------------------------------------------------
# 2) SAYFA BİÇİMLENDİRİCİLERİ KANONA BAĞLI (kaynak okuyan ayak)
# ---------------------------------------------------------------------------
#: (etiket, dosya, fonksiyon adı, gövdede geçmesi gereken delegatör)
BAGLI_BICIMLEYICILER = [
    ('liquid.hrmaFmt',         TPL / 'liquid.html', 'hrmaFmt',         'numTxt'),
    ('solid.fmtNum',           TPL / 'solid.html',  'fmtNum',          'numTxt'),
    ('solid.fmtPercentOrNA',   TPL / 'solid.html',  'fmtPercentOrNA',  'pctTxt'),
    ('cfd_panel.fmt',          JS / 'panels' / 'cfd_panel.js',       'fmt',    '_num'),
    ('stability_panel.fmt',    JS / 'panels' / 'stability_panel.js', 'fmt',    '_num'),
    ('stability_panel.fmtExp', JS / 'panels' / 'stability_panel.js', 'fmtExp', 'decimalText'),
    ('stability_panel.sig',    JS / 'panels' / 'stability_panel.js', 'sig',    'decimalText'),
]


def govde_cek(metin, ad):
    """`function AD(...) { ... }` gövdesini dengeli süslü parantezle çeker."""
    m = re.search(r'function\s+%s\s*\(' % re.escape(ad), metin)
    assert m, '%s tanımı bulunamadı' % ad
    k = metin.index('{', m.end())
    d, i = 0, k
    while i < len(metin):
        if metin[i] == '{':
            d += 1
        elif metin[i] == '}':
            d -= 1
            if d == 0:
                break
        i += 1
    return metin[m.start():i + 1]


def yorumsuz(js):
    """JS gövdesinden yorumları atar.

    NEDEN: ilk sürüm gövdeyi HAM ararken bekçi ısırmıyordu — ölçüldü
    (mutasyon M4, 22 Eylül): `sig` kanondan koparıldığı hâlde test yeşil
    kaldı, çünkü fonksiyonun Türkçe künyesi "decimalText" sözcüğünü
    geçiriyordu ve alt dize eşleşmesi YORUMDAN besleniyordu. Yorum kod
    değildir; kanona bağlılık KODDAN okunur.
    """
    js = re.sub(r'/\*.*?\*/', ' ', js, flags=re.S)
    js = re.sub(r'//[^\n]*', ' ', js)
    return js


@pytest.mark.parametrize('etiket,yol,ad,delegator', BAGLI_BICIMLEYICILER,
                         ids=[b[0] for b in BAGLI_BICIMLEYICILER])
def test_bicimlendirici_kanona_bagli(etiket, yol, ad, delegator):
    """Ekrana giden biçimlendirici kendi ayracını YAZMAZ, kanona sorar."""
    govde = yorumsuz(govde_cek(oku(yol), ad))
    assert delegator in govde, (
        '%s kanona (%s) bağlı değil; kendi biçimini kuruyor:\n%s'
        % (etiket, delegator, govde[:400]))


#: Onarımdan SONRA ölçülen ham `.toFixed(` sayıları. Tavan, dosyanın
#: dışa aktarım / form `.value` / `Number(x.toFixed())` yollarını kapsar —
#: bunlar EKRAN METNİ DEĞİLDİR ve bilerek dokunulmamıştır. Sayı ARTARSA
#: yeni bir çağrı yeri kanonu atlamış demektir.
#:
#: T-ÇAPA-C2 (27 Eki) ölçümü — tavan yükselen iki dosyada YENİ çağrıların
#: hepsi ekran metni değil, satır satır denetlendi:
#:   * liquid.html 4 → 5: V301/UÇUŞ 2433377ec (liquidSixDofSeed,
#:     ``el.value = deger.toFixed(basamak)`` + gövde çapı
#:     ``govde.value = (…).toFixed(3)``, +2); f75da1023 eski yörünge
#:     tohumunun ``el.value = v.toFixed(3)``unu liquidTrajectorySeed'e taşıdı
#:     (net 0); V301/L-C f8504d4a4 bir çağrı söktü (−1). Eklenenlerin ikisi de
#:     sayı girdisinin ``.value``'su (tarayıcı ondalık NOKTA ister; TR virgülü
#:     girdiyi bozardı).
#:   * solid.html 18 → 20: V301/K-C2 1b3ec145b (primeCatalogValues ve
#:     _kayitDegeriMi): ``Number(raw.toFixed(f.digits))`` — kayıt değerini
#:     form basamağına yuvarlayıp SAYI olarak karşılaştırır, ekrana basmaz.
TOFIXED_TAVANI = {
    'app.js': 4,
    'motor_viz3d.js': 1,
    'liquid.html': 5,
    'solid.html': 20,
    'advanced.html': 11,
    'cfd_panel.js': 1,
    'stability_panel.js': 1,
}
TOFIXED_YOLLARI = {
    'app.js': JS / 'app.js',
    'motor_viz3d.js': JS / 'motor_viz3d.js',
    'liquid.html': TPL / 'liquid.html',
    'solid.html': TPL / 'solid.html',
    'advanced.html': TPL / 'advanced.html',
    'cfd_panel.js': JS / 'panels' / 'cfd_panel.js',
    'stability_panel.js': JS / 'panels' / 'stability_panel.js',
}


@pytest.mark.parametrize('ad', sorted(TOFIXED_TAVANI))
def test_ham_tofixed_tavani_asilmadi(ad):
    """Yeni çağrı yerleri kanonu atlayamaz (ölçülmüş tavan)."""
    n = oku(TOFIXED_YOLLARI[ad]).count('.toFixed(')
    assert n <= TOFIXED_TAVANI[ad], (
        '%s içinde ham .toFixed( sayısı %d; ölçülen tavan %d. Yeni eklenen '
        'ekran çağrısı I18N.number kanonuna (numTxt/i18nNumber) bağlanmalı.'
        % (ad, n, TOFIXED_TAVANI[ad]))


# ---------------------------------------------------------------------------
# 3) DAVRANIŞ — node altında lang='tr' / 'en'
# ---------------------------------------------------------------------------
KOSUCU = r'''
const fs = require('fs');
global.window = global;
global.localStorage = {
  _d: {}, getItem(k){ return (k in this._d) ? this._d[k] : null; },
  setItem(k,v){ this._d[k] = String(v); }, removeItem(k){ delete this._d[k]; }
};
(0, eval)(fs.readFileSync(process.env.I18N_YOLU, 'utf8'));
const I18N = global.I18N;
const T = (k, f) => (f === undefined ? k : f);
%(hazirlik)s
const out = {};
%(govde)s
process.stdout.write(JSON.stringify(out));
'''


def node_kos(govde, hazirlik=''):
    betik = KOSUCU % {'govde': govde, 'hazirlik': hazirlik}
    ortam = dict(os.environ)
    ortam['I18N_YOLU'] = str(JS / 'i18n.js')
    p = subprocess.run([NODE], input=betik, env=ortam,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-3000:]
    return json.loads(p.stdout)


@node_gerek
def test_davranis_kanon_tr_virgul_en_nokta():
    """Kanonun kendisi: TR virgül, EN nokta; basamak sayısı korunur."""
    r = node_kos(r'''
    I18N.lang = 'tr';
    out.tr_number   = I18N.number(222.8, 1);
    out.tr_unit     = I18N.unit(222.8, 's', 1);
    out.tr_unit_kgs = I18N.unit(0.458, 'kg/s', 3);
    out.tr_derece   = I18N.unit(45.5, '\u00B0', 1);
    out.tr_percent  = I18N.percent(100, 0);
    out.tr_percent1 = I18N.percent(12.5, 1);
    out.tr_kucuk    = I18N.number(0.0019643, 7);
    I18N.lang = 'en';
    out.en_number   = I18N.number(222.8, 1);
    out.en_unit     = I18N.unit(222.8, 's', 1);
    out.en_percent  = I18N.percent(100, 0);
    ''')
    assert r['tr_number'] == '222,8'
    assert r['en_number'] == '222.8'
    # SI: sayı ile birim arasında BÖLÜNMEZ boşluk
    assert r['tr_unit'] == '222,8\u00a0s', repr(r['tr_unit'])
    assert r['en_unit'] == '222.8\u00a0s', repr(r['en_unit'])
    assert r['tr_unit_kgs'] == '0,458\u00a0kg/s', repr(r['tr_unit_kgs'])
    # Derece BİTİŞİK yazılır (SI istisnası)
    assert r['tr_derece'] == '45,5\u00b0', repr(r['tr_derece'])
    # Yüzde işaretinin yeri dile bağlı
    assert r['tr_percent'] == '%100', repr(r['tr_percent'])
    assert r['tr_percent1'] == '%12,5', repr(r['tr_percent1'])
    assert r['en_percent'] == '100%', repr(r['en_percent'])
    # Basamak sayısı çağıranın; yuvarlama YOK
    assert r['tr_kucuk'] == '0,0019643', repr(r['tr_kucuk'])


#: Yalıtılmış koşum için komşu yardımcılar — panellerin KENDİ kaynağındaki
#: tanımların aynısı (ölçüm iskelesi; ürün kodu değil).
PANEL_HAZ = (
    "function isNum(v){return typeof v==='number'&&isFinite(v);}\n"
    "function _num(v,d){return (global.I18N&&global.I18N.number)"
    "?global.I18N.number(v,d):v.toFixed(d);}\n"
    "function sigFig(value){var v=Number(value);"
    "if(!isFinite(v)||v===0)return v;return Number(v.toPrecision(6));}\n"
)


@node_gerek
def test_davranis_sayfa_bicimlendiricileri_tr_virgul():
    """Sayfa biçimlendiricileri lang='tr' ile VİRGÜL basmalı (canlı koşum)."""
    liquid = oku(TPL / 'liquid.html')
    solid = oku(TPL / 'solid.html')
    stab = oku(JS / 'panels' / 'stability_panel.js')
    hazirlik = '\n'.join([
        govde_cek(solid, 'numTxt'),
        govde_cek(solid, 'pctTxt'),
        govde_cek(liquid, 'hrmaFmt'),
        govde_cek(solid, 'fmtNum'),
        govde_cek(solid, 'fmtPercentOrNA'),
        PANEL_HAZ,
        govde_cek(stab, 'fmtExp'),
        govde_cek(stab, 'sig'),
    ])
    r = node_kos(r'''
    I18N.lang = 'tr';
    out.hrmaFmt      = hrmaFmt(222.8, 1);
    out.hrmaFmt_unit = hrmaFmt(40, 1, 'bar');
    out.fmtNum       = fmtNum(1425.9, 1);
    out.fmtPercent   = fmtPercentOrNA(68);
    out.fmtExp       = fmtExp(0.0019643, 2);
    out.sig          = sig(80.6);
    I18N.lang = 'en';
    out.en_fmtNum    = fmtNum(1425.9, 1);
    out.en_fmtPercent = fmtPercentOrNA(68);
    out.en_sig       = sig(80.6);
    ''', hazirlik)
    assert r['hrmaFmt'] == '222,8', repr(r['hrmaFmt'])
    assert r['hrmaFmt_unit'] == '40,0 bar', repr(r['hrmaFmt_unit'])
    assert r['fmtNum'] == '1425,9', repr(r['fmtNum'])
    assert r['fmtPercent'] == '%68', repr(r['fmtPercent'])
    assert r['fmtExp'] == '1,96e-3', repr(r['fmtExp'])
    assert r['sig'] == '80,6', repr(r['sig'])
    # İngilizce oturum BOZULMADI
    assert r['en_fmtNum'] == '1425.9', repr(r['en_fmtNum'])
    assert r['en_fmtPercent'] == '68%', repr(r['en_fmtPercent'])
    assert r['en_sig'] == '80.6', repr(r['en_sig'])


@node_gerek
def test_davranis_delegator_sozluksuz_ortamda_sayi_uydurmaz():
    """Sözlük yoksa ayraç yerelleşmez ama SAYI DEĞİŞMEZ (fail-safe)."""
    solid = oku(TPL / 'solid.html')
    betik = (govde_cek(solid, 'numTxt') + '\n'
             + "const out = {};\n"
             + "out.a = numTxt(1425.9, 1);\n"
             + "out.b = numTxt(0.0019643, 7);\n"
             + "process.stdout.write(JSON.stringify(out));")
    p = subprocess.run([NODE], input=betik, capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-2000:]
    r = json.loads(p.stdout)
    assert r['a'] == '1425.9', repr(r['a'])
    assert r['b'] == '0.0019643', repr(r['b'])


# ---------------------------------------------------------------------------
# 4) OH-GT-27 — ham enum ekranda etiket olarak DURMAZ (fail-closed)
# ---------------------------------------------------------------------------
def test_motor_cevrimi_ham_anahtar_basmaz():
    """`engine_cycle` satırı ham enum yerine okunur ad basmalı."""
    src = oku(TPL / 'liquid.html')
    assert "esc(cycleLabelText(fs.engine_cycle))" in src, \
        'çevrim satırı hâlâ ham enum basıyor'
    govde = govde_cek(src, 'cycleLabelText')
    # Fail-closed: bilinmeyen değer UYDURULMAZ, işaretlenir
    assert "'(?)'" in govde or '(?)' in govde, \
        'bilinmeyen çevrim değeri işaretlenmiyor (fail-closed değil)'


def test_cevrim_etiketleri_sayfanin_kendi_anahtarlarini_kullanir():
    """Eşleme YENİ anahtar açmaz; seçicinin `data-i18n` anahtarlarını kullanır."""
    src = oku(TPL / 'liquid.html')
    # YALNIZ motor çevrimi seçicisi (sayfada başka <select>'ler de var;
    # alt dize eşleşmesi 'low' <-> 'full_flow_staged' gibi yanlış
    # pozitif verir, o yüzden eşleşme TAM anahtar üzerinden yapılır).
    bas = src.index('<select id="engine_cycle">')
    secici = dict(re.findall(
        r'<option value="(\w+)" data-i18n="([\w.]+)"',
        src[bas:src.index('</select>', bas)]))
    assert secici, 'çevrim seçicisi okunamadı'
    govde = src[src.index('var CYCLE_LABEL_KEYS'):]
    govde = govde[:govde.index('};') + 2]
    esleme = dict(re.findall(r"(\w+):\s*\['([\w.]+)'", govde))
    assert esleme, 'CYCLE_LABEL_KEYS eşlemesi okunamadı'
    for deger, anahtar in esleme.items():
        assert deger in secici, (
            '%s seçicide yok; eşleme sayfanın kendi kümesinden sapmış' % deger)
        assert secici[deger] == anahtar, (
            '%s için seçicideki anahtar %s, eşlemede %s — YENİ anahtar '
            'açılmış olabilir' % (deger, secici[deger], anahtar))


# ---------------------------------------------------------------------------
# 5) OH-GT-26 — HUD birimi KART birimiyle aynı
# ---------------------------------------------------------------------------
def test_hud_itki_birimi_kartla_ayni():
    """Kart 'N' derken HUD 'kN' diyemez (aynı ekran, aynı büyüklük)."""
    kart = oku(JS / 'app.js')
    m = re.search(r"app\.metric\.thrust'[^}]*unit:\s*'(\w+)'", kart)
    assert m, 'kart itki birimi okunamadı'
    kart_birimi = m.group(1)
    adv = oku(TPL / 'advanced.html')
    m2 = re.search(r"setVizChip\('viz_v_thrust',[^;]*?,\s*'(\w+)'", adv, re.S)
    assert m2, 'HUD itki birimi okunamadı'
    assert m2.group(1) == kart_birimi, (
        "HUD itki birimi %r, kart %r — aynı olmalı" % (m2.group(1), kart_birimi))
    assert "'kN' : 'N'" not in adv, 'birim eşiği (kN/N) geri gelmiş'


def test_hud_yuzde_cipi_dile_bagli():
    """Web yüzdesi `i18nPercent` üzerinden basılmalı (TR'de işaret önde)."""
    adv = oku(TPL / 'advanced.html')
    assert re.search(r"setVizChip\('viz_v_web',\s*i18nPercent\(", adv), \
        'web çipi yüzde kanonunu kullanmıyor'


# ---------------------------------------------------------------------------
# 6) OH-GT-30 — katı 3B CAD sahnesi
# ---------------------------------------------------------------------------
def test_kati_cad_sahnesi_gercek_orani_ve_yatay_yonelimi_korur():
    """Uzun eksen (Z) ekranın DİKEYİNE binmemeli; oran veriden gelmeli."""
    src = oku(TPL / 'solid.html')
    i = src.index("T('solid.msg.solid_motor_3d_cad_view'")
    blok = src[i:i + 3400]
    assert "aspectmode: 'data'" in blok, \
        'sahne oranı veriden gelmiyor (gerçek narinlik bozulur)'
    m = re.search(r'up:\s*\{\s*x:\s*([\d.]+),\s*y:\s*([\d.]+),\s*z:\s*([\d.]+)', blok)
    assert m, 'kamera `up` vektörü beyan edilmemiş'
    assert float(m.group(3)) == 0.0, (
        'kamera `up` hâlâ Z; gövde Z boyunca kurulduğu için motor ekranda '
        'dikey ince çubuğa sıkışır (OH-P-14)')
    assert 'height: 400' in blok, 'çizim yüksekliği beyan edilmemiş (kap 400 px)'


def test_kati_cad_govdesi_z_ekseni_boyunca_kuruluyor():
    """`up` hükmünün dayanağı: silindir gerçekten Z boyunca uzuyor."""
    src = oku(TPL / 'solid.html')
    govde = govde_cek(src, 'createCylinderTrace')
    assert re.search(r'pz\s*=\s*z\s*\+\s*ring\s*\*\s*height', govde), (
        'silindir artık Z boyunca kurulmuyor; kamera `up` hükmü '
        'yeniden ölçülmeli')
