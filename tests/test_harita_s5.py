"""Harita ayrıntısı 4. tur bekçileri (14 Eki 2026): F1 denetimi Ş5 + HRK devirleri.

Görev kalemleri ve yakalanan arıza sınıfları:

* **Okunurluk (Ş5).** Kar/buz zemininde (Grönland, Antarktika, Alpler,
  Anadolu karı) açık renkli etiket kayboluyordu. Etiket stilinde koyu kontur
  (``-webkit-text-stroke`` + ``paint-order: stroke``) ve sekiz yönlü keskin
  hale kalkarsa KIRMIZI.
* **K-2 (tüm Dünya <= 40 etiket).** Ölçüt §3.2'nin ilk bandına (m/px >
  20.000) bağlıdır. Bandın girişinde (en çok etiket veren uç) dört sahada,
  TR ve EN'de en çok 40 etiket; fazlası öncelik sırasıyla kesilir. Bant
  eşiği vektör modülünün basamak tablosundan okunur (kopya yok).
* **K-3 (titreme).** Yeni etiket, panel aralığına ya da panel ile ekran
  kenarı arasındaki şeride (sayfada 14 ve 22 px) sığıp iki kare görünüp
  kaybolmamalı: yeni etiket boşluk payı bu aralıkları kapatır.
* **Künye dürüstlüğü (HRK devri).** Künye NE'ye uygulanan ad ve sınır
  düzeltmelerini (karar §28-45) varlığın kendi künyesinden sayıp söyler;
  biçim bozuksa sayı uydurulmaz. Metin textContent ile basılır.
* **Kalıcılık (HRK devri).** ``tools/build_launch_site_assets.py`` yeniden
  koşulursa Perekop çizgisini geri getirmez: aynı tabloyu İÇE AKTARIR,
  tablo tutmazsa hiçbir dosya yazmaz.

Sentetik yer/ülke girdileri ve GeoJSON parçaları TEST ALTYAPISIDIR
(fixture), kullanıcıya gösterilen veri değildir. Gerçek veri senaryoları
depodaki ``hrma/static/map`` varlıklarını okur.
"""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import subprocess
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
for _yol in (str(KOK), str(KOK / 'tools'), str(KOK / 'tests')):
    if _yol not in sys.path:
        sys.path.insert(0, _yol)

import build_launch_site_assets as va  # noqa: E402
import build_map_detail_assets as hat  # noqa: E402
from test_harita_etiket import (DUZENEK, ETIKET, GLOBE, I18N, NODE, SABLON,  # noqa: E402
                                THREE_JS, VARLIK_DIZIN, _kod, _oku, _sentetik,
                                _yer, node_gerek)

VEKTOR = KOK / 'hrma' / 'static' / 'js' / 'launch_site_vectors.js'
SINIR = KOK / 'hrma' / 'static' / 'img' / 'earth_borders.json'
VA_YOL = KOK / 'tools' / 'build_launch_site_assets.py'
HRK_KUNYE_ANAHTARLARI = ('site.nameCorrections', 'site.boundaryCorrections')

#: Ölçüm düzeni (tasarım §5.2): 1440×900 pencerede tuval 1440×845 (başlık
#: şeridi 55 px; tarayıcıda ölçüldü, rapor 4. tur).
TUVAL_W, TUVAL_H = 1440, 845
#: §5.2 sahaları.
SAHALAR = (('kennedy', 28.57, -80.65), ('sinop', 42.0, 35.1),
           ('esrange', 67.9, 21.1), ('mahia', -39.26, 177.86))


# ---------------------------------------------------------------------------
# Node düzeneği: test_harita_etiket'inki + vektör modülü (bant eşiği) +
# Dünya merkezli hedef ('merkez') ve m/px ile verilen kamera ('mpp').
# ---------------------------------------------------------------------------
def _duzenek() -> str:
    s = DUZENEK
    eski = "vm.runInContext(fs.readFileSync(ETIKET, 'utf8'), ctx);"
    assert s.count(eski) == 1
    s = s.replace(eski, "if (process.env.HRMA_VEKTOR) vm.runInContext("
                        "fs.readFileSync(process.env.HRMA_VEKTOR, 'utf8'), ctx);\n" + eski)
    eski = "    const hedef = n.clone().multiplyScalar(R);"
    assert s.count(eski) == 1
    s = s.replace(eski, "    const hedef = k.merkez ? new THREE.Vector3(0, 0, 0) : n.clone().multiplyScalar(R);")
    eski = "    const dU = k.d * 1000 / MPU;"
    assert s.count(eski) == 1
    s = s.replace(eski, "    const dU = k.mpp ? k.mpp * H / (2 * Math.tan(19 * Math.PI / 180)) / MPU"
                        " : k.d * 1000 / MPU;")
    eski = "    const yon = n.clone()"
    assert s.count(eski) == 1
    s = s.replace(eski, "    const yon = k.merkez ? n.clone() : n.clone()")
    return s


def _kos(tmp_path: pathlib.Path, adimlar: list, vektor: bool = True) -> list:
    js = tmp_path / 'duzenek_s5.js'
    js.write_text(_duzenek(), encoding='utf-8')
    gorev = tmp_path / 'gorev.json'
    gorev.write_text(json.dumps({'adimlar': adimlar}), encoding='utf-8')
    env = dict(__import__('os').environ)
    if vektor:
        env['HRMA_VEKTOR'] = str(VEKTOR)
    else:
        env.pop('HRMA_VEKTOR', None)
    r = subprocess.run([NODE, str(js), str(THREE_JS), str(GLOBE), str(ETIKET), str(gorev)],
                       capture_output=True, text=True, timeout=240, env=env)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


def _node(kod: str) -> object:
    r = subprocess.run([NODE], input=kod, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def _gercek_varlik_gerek():
    if not ((VARLIK_DIZIN / 'places.json').is_file()
            and (VARLIK_DIZIN / 'vectors_manifest.json').is_file()):
        pytest.fail('hrma/static/map varlıkları depoda yok (F1 birleşti; olmaları gerekir)')


# ===========================================================================
# 1) Okunurluk: kontur + hale (F1 denetimi Ş5)
# ===========================================================================

def _etiket_kurali() -> str:
    s = _oku(SABLON)
    m = re.search(r'#ls-labels \.ls-lbl \{(.*?)\}', s, re.S)
    assert m, 'etiket kuralı bulunamadı'
    return m.group(1)


def test_etiket_hale_rengi_koyu_ve_opak():
    s = _oku(SABLON)
    blok = re.search(r'#ls-labels \{(.*?)\}', s, re.S).group(1)
    m = re.search(r'--ls-lbl-hale:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', blok)
    assert m, 'hale rengi değişkeni yok'
    r, g, b, a = (float(x) for x in m.groups())
    assert max(r, g, b) <= 40 and a >= 0.8, 'hale koyu ve opak değil'


def test_etiket_konturu_dolgunun_arkasinda():
    kural = _etiket_kurali()
    m = re.search(r'-webkit-text-stroke:\s*(\d+(?:\.\d+)?)px\s+var\(--ls-lbl-hale\)', kural)
    assert m and float(m.group(1)) >= 2, 'kontur yok ya da 2 px altında'
    assert re.search(r'paint-order:\s*stroke\b', kural), \
        'kontur dolgunun üstüne çiziliyor (harf incelir) ya da paint-order yok'


def test_etiket_sekiz_yonlu_keskin_hale():
    kural = _etiket_kurali()
    yonler = set(re.findall(r'(-?1px|0) (-?1px|0) 0 var\(--ls-lbl-hale\)', kural))
    beklenen = {(x, y) for x in ('-1px', '0', '1px') for y in ('-1px', '0', '1px')} - {('0', '0')}
    assert yonler == beklenen, sorted(beklenen - yonler)


def test_nokta_halkasi_koyu_kenarli():
    s = _oku(SABLON)
    m = re.search(r'#ls-labels \.ls-lbl-dot \{(.*?)\}', s, re.S)
    assert m and re.search(r'box-shadow:\s*0 0 0 1px var\(--ls-lbl-hale\)', m.group(1)), \
        'şehir noktasında koyu kenar halkası yok (karda nokta kayboluyordu)'


# ===========================================================================
# 2) K-2: tüm Dünya bandında en çok 40 etiket
# ===========================================================================

def test_dunya_tavani_sabiti_ve_bant_esigi_tek_kaynak():
    js = _kod(_oku(ETIKET))
    m = re.search(r'var DUNYA_ETIKET_TAVANI = (\d+);', js)
    assert m and int(m.group(1)) == 40, 'tasarım §5.2: tüm Dünya <= 40 etiket'
    assert '20000' not in js and '20.000' not in js, 'bant eşiği etiket modülüne kopyalanmış'
    assert 'V.BASAMAKLAR' in js and "B[i].ad === '50m'" in js
    vj = _kod(_oku(VEKTOR))
    assert re.search(r"\{ ad: '50m', mppUst: 20000\.0 \}", vj), 'vektör basamak eşiği değişti'


@node_gerek
def test_dunya_bandinda_en_cok_40_etiket_dort_saha_tr_en(tmp_path):
    _gercek_varlik_gerek()
    pozlar = []
    for _, la, lo in SAHALAR:
        # Önce bandın hemen dışında (14.751 m/px, §1 mesafesi): gösterilen
        # etiketler histerezisle taşınır, sayfadaki uzaklaşma hareketi gibi.
        # Bant girişi (m/px 20.050) en çok etiket veren uçtur; 25.000 içeride.
        for mpp in (14751, 20050, 25000):
            pozlar.append({'op': 'kare', 'lat': la, 'lon': lo, 'merkez': True, 'mpp': mpp,
                           'W': TUVAL_W, 'H': TUVAL_H})
    adim = [{'op': 'kur', 'dizin': str(VARLIK_DIZIN), 'dil': 'tr'}] + pozlar \
        + [{'op': 'dil', 'dil': 'en'}] + [dict(p) for p in pozlar]
    r = _kos(tmp_path, adim)
    assert r[0]['durum'] == 'hazir'
    kareler = [s for s in r if s['op'] == 'kare']
    assert len(kareler) == 2 * len(pozlar)
    bantta = [s for s in kareler if s['z'] < 2.97]
    assert len(bantta) == 2 * 2 * len(SAHALAR)
    for s in bantta:
        assert s['info']['dunyaBandiMpp'] == 20000
        assert s['info']['tavan'] == 40
        assert len(s['yer']) <= 40, (len(s['yer']), s['z'])
    # Bandın dışında (14.751 m/px) tavan 150: kesme yalnız bantta.
    assert all(s['info']['tavan'] == 150 for s in kareler if s['z'] > 3.0)
    # Öncelik sırası: kesilen yerlerden önce ülke adları yarışır; Sinop
    # merkezli bant girişinde Türkiye adı kalır.
    sinop_tr = kareler[4]
    assert 'Türkiye' in [p['ad'] for p in sinop_tr['yer']]
    # Kesme gerçekten devrede: bant girişinde Sinop tavana dayanır.
    assert len(sinop_tr['yer']) == 40 and sinop_tr['info']['tavanGizli'] > 0


@node_gerek
def test_dunya_bandi_disinda_tavan_150_ve_modul_yoksa_beyan(tmp_path):
    _gercek_varlik_gerek()
    poz = {'op': 'kare', 'lat': 42.0, 'lon': 35.1, 'merkez': True, 'mpp': 19950,
           'W': TUVAL_W, 'H': TUVAL_H}
    isit = dict(poz, mpp=14751)
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(VARLIK_DIZIN), 'dil': 'tr'}, isit, poz])
    assert r[2]['info']['tavan'] == 150 and len(r[2]['yer']) > 40
    # Vektör modülü yüklenmemişse eşik okunamaz: bant tavanı uygulanmaz ve
    # bu durum getInfo'da null ile beyan edilir (sayı uydurulmaz).
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(VARLIK_DIZIN), 'dil': 'tr'}, isit,
                        dict(poz, mpp=20050)], vektor=False)
    assert r[2]['info']['dunyaBandiMpp'] is None and r[2]['info']['tavan'] == 150


# ===========================================================================
# 3) K-3: panel aralığında iki kare görünüp kaybolan yeni etiket yok
# ===========================================================================

@node_gerek
@pytest.mark.parametrize('aralik', [22, 24])
def test_yeni_etiket_panel_araligina_sigmaz(tmp_path, aralik):
    """Sayfada sol panel ile ölçek kutusu arası 22 px (ölçüldü). 14 px'lik
    yeni etiket bu aralığa sığarsa kaydırırken iki kare görünüp panelin
    altında kaybolur (K-3 ölçümü: Karabük, Tampa; 4 değişim / 2 s). Eski
    pay (3 px) 22 ve 24 px'lik aralığa etiketi sokuyordu."""
    W, H = 1440, 845
    y = H // 2
    ust = [0, 0, W, y - aralik // 2]
    alt = [0, y - aralik // 2 + aralik, W, H]
    d = _sentetik(tmp_path / 'm', [_yer('Aralik', 30.0, 40.0, 2.0, ne_id=1)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d), 'engeller': [ust, alt]},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0, 'W': W, 'H': H}])
    assert [p['ad'] for p in r[1]['yer']] == [], 'yeni etiket %d px aralığa sığdı' % aralik


@node_gerek
def test_gosterilen_etiket_panel_araliginda_kalir(tmp_path):
    """Pay yalnız YENİ etiketlere: zaten gösterilen etiket aynı aralıkta
    kalır (histerezis; aksi hâlde sınırdaki etiket söküp geri gelir)."""
    W, H = 1440, 845
    y = H // 2
    d = _sentetik(tmp_path / 'm', [_yer('Kalan', 30.0, 40.0, 2.0, ne_id=1)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0, 'W': W, 'H': H},
                        {'op': 'engel', 'engeller': [[0, 0, W, y - 11], [0, y + 11, W, H]]},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3001, 'z': 4.0, 'W': W, 'H': H}])
    assert [p['ad'] for p in r[1]['yer']] == ['Kalan']
    assert [p['ad'] for p in r[2]['yer']] == ['Kalan']


# ===========================================================================
# 4) Künye dürüstlüğü: ad ve sınır düzeltmeleri
# ===========================================================================

def _yukle_js(*yollar: pathlib.Path) -> str:
    on = "const vm=require('vm'),fs=require('fs');const ctx={console,Math,JSON,Promise};ctx.window=ctx;vm.createContext(ctx);"
    return on + ''.join("vm.runInContext(fs.readFileSync(%s,'utf8'),ctx);" % json.dumps(str(y))
                        for y in yollar)


@node_gerek
def test_ad_duzeltme_sayisi_varlik_kunyesinden():
    _gercek_varlik_gerek()
    yer = json.loads((VARLIK_DIZIN / 'places.json').read_text(encoding='utf-8'))['provenance']
    ulke = json.loads((VARLIK_DIZIN / 'country_labels.json').read_text(encoding='utf-8'))['provenance']
    # Bağımsız kâhin: K1 tablosunun ad alanlarına dokunan satırları.
    adlar = {'name', 'name_en', 'name_tr'}
    beklenen = [sum(1 for s in p['name_corrections']['applied']
                    if any(c['field'] in adlar for c in s['changes'])) for p in (yer, ulke)]
    assert beklenen[0] > 0 and beklenen[1] > 0
    bozuk = [{'name_corrections': {'applied': 'x'}},
             {'name_corrections': {'applied': [{'changes': None}]}},
             {}, {'name_corrections': {'applied': [{'changes': [{'field': 'adm0'}]}]}}]
    kod = _yukle_js(ETIKET) + "const f=ctx.LaunchSiteLabels.adDuzeltmeSayisi;" \
        "process.stdout.write(JSON.stringify([%s].map(f)));" % ','.join(
            json.dumps(x) for x in [yer, ulke] + bozuk)
    assert _node(kod) == beklenen + [None, None, 0, 0]


@node_gerek
def test_sinir_duzeltmesi_manifest_kunyesinden():
    _gercek_varlik_gerek()
    man = json.loads((VARLIK_DIZIN / 'vectors_manifest.json').read_text(encoding='utf-8'))
    bc = man['provenance']['boundary_corrections']
    beklenen = {'cizgi': max(bc['dropped_lines'].values()), 'karar': bc['decision']}
    assert beklenen['cizgi'] == 1 and 'Kırım' in beklenen['karar']

    def m(bc_):
        return {'provenance': {'boundary_corrections': bc_}}
    vakalar = [man, {'provenance': {}}, None,
               m({'decision': 'x', 'dropped_lines': {'a': -1}}),
               m({'decision': 'x', 'dropped_lines': {'a': 1.5}}),
               m({'decision': 'x', 'dropped_lines': {'a': 'NaN'}}),
               m({'decision': '', 'dropped_lines': {'a': 1}}),
               m({'dropped_lines': {'a': 1}}),
               m({'decision': 'x', 'dropped_lines': {}})]
    kod = _yukle_js(VEKTOR) + "const f=ctx.LaunchSiteVectors.sinirDuzeltmesi;" \
        "process.stdout.write(JSON.stringify([%s].map(f)));" % ','.join(json.dumps(x) for x in vakalar)
    assert _node(kod) == [beklenen] + [None] * 8


def _not_kodu() -> str:
    s = _oku(SABLON)
    m = re.search(r'    function vectorScaleNumber\(v\) \{.*?\n    \}\n    function renderMapNotes\(force\) \{.*?\n    \}\n', s, re.S)
    assert m, 'renderMapNotes bulunamadı'
    return m.group(0)


@node_gerek
@pytest.mark.parametrize('dil', ['tr', 'en'])
def test_kunye_duzeltmeleri_ekranda_textcontent_ile(dil):
    sys.path.insert(0, str(KOK / 'tests'))
    from test_z5i18n_supurme import sozluk  # noqa: E402
    sz = sozluk(I18N, dil)
    kod = r"""
var SOZ = %s;
var I18N = { lang: %s, t: function (k, fb) { return SOZ[k] || fb; },
  tf: function (k, p, fb) { return String(SOZ[k] || fb).replace(/\{(\w+)\}/g, function (m, a) { return p[a]; }); } };
function t(k, fb) { return I18N.t(k, fb); }
function tf(k, p, fb) { return I18N.tf(k, p, fb); }
function fmtNum_(v, d) { return String(v); }
var dugum = {}; ['ls-vecnote', 'ls-ne-attr'].forEach(function (i) { dugum[i] = { style: {}, set innerHTML(v) { throw new Error('innerHTML'); }, textContent: '' }; });
function el(i) { return dugum[i]; }
var VEKTOR_NOTU_MPP = 500, SINIR_GORUNUMU_ANAHTARI = { varsayilan: 'site.boundaryViewDefault' }, mapNoteSig = '';
var VI = { durum: 'hazir', nominalScale: '1:10m', legacyVisible: false, sinirDuzeltmesi: { cizgi: 1, karar: 'k' } };
var globe = { camera: {}, getScaleInfo: function () { return { metersPerPixel: 9000 }; }, getVectorInfo: function () { return VI; } };
var labels = { getInfo: function () { return { durum: 'hazir', kunye: { surum: 'v5.1.2', sinirGorunumu: 'varsayilan', adYedegi: { tr: 0, en: 0 }, adDuzeltmesi: { yer: 13, ulke: 3 } } }; } };
%s
var out = [];
renderMapNotes(true); out.push(dugum['ls-ne-attr'].textContent);
VI.sinirDuzeltmesi = null; labels.getInfo = (function (g) { return function () { var i = g(); i.kunye.adDuzeltmesi = { yer: null, ulke: 3 }; return i; }; })(labels.getInfo);
renderMapNotes(true); out.push(dugum['ls-ne-attr'].textContent);
process.stdout.write(JSON.stringify(out));
""" % (json.dumps(sz, ensure_ascii=False), json.dumps(dil), _not_kodu())
    ilk, ikinci = _node(kod)
    ad = sz['site.nameCorrections'].replace('{n}', '16')
    sinir = sz['site.boundaryCorrections'].replace('{n}', '1')
    assert ad in ilk and sinir in ilk, ilk
    # Sınır künyesi yoksa ya da ad sayısı bozuksa o satır basılmaz.
    assert sinir not in ikinci and sz['site.nameCorrections'].split('{n}')[0] not in ikinci


def test_kunye_anahtarlari_parite_ve_yedek_metin():
    sys.path.insert(0, str(KOK / 'tests'))
    from test_z5i18n_supurme import sozluk  # noqa: E402
    en, tr = sozluk(I18N, 'en'), sozluk(I18N, 'tr')
    for k in HRK_KUNYE_ANAHTARLARI:
        assert k in en and k in tr, k
        assert re.findall(r'\{(\w+)\}', en[k]) == re.findall(r'\{(\w+)\}', tr[k]) == ['n'], k
        for v in (en[k], tr[k]):
            assert '—' not in v and '–' not in v, (k, v)
    assert re.search('[çğıİöşü]', tr['site.boundaryCorrections'])
    assert 'Kırım' in tr['site.boundaryCorrections'] and 'Crimea' in en['site.boundaryCorrections']
    kod = _kod(_oku(SABLON))
    dizgi = r"((?:'(?:[^'\\]|\\.)*'\s*\+?\s*)+)\)"
    for k in HRK_KUNYE_ANAHTARLARI:
        govde = re.search(r"tf\('%s',\s*\{.*?\},\s*" % re.escape(k) + dizgi, kod, re.S)
        assert govde, k
        yedek = ''.join(re.findall(r"'((?:[^'\\]|\\.)*)'", govde.group(1)))
        assert yedek == en[k], (k, yedek)
    # Künye düğümü yalnız textContent ile yazılır.
    assert "na.textContent = parca.join(' ');" in kod and 'na.innerHTML' not in kod


# ===========================================================================
# 5) Kalıcılık: build_launch_site_assets Perekop çizgisini geri getirmez
# ===========================================================================

def _once_katmanlari():
    """Depodaki dosyaya tablodaki çizgiyi geri koyar (düşüş öncesi hâl)."""
    veri = json.loads(SINIR.read_text(encoding='utf-8'))
    t = hat.ESKI_110M_SINIR_DUZELTMESI
    katman = list(veri['layers'][t['layer']])
    katman.insert(t['index_before'], [v for nokta in t['points'] for v in nokta])
    veri['layers'][t['layer']] = katman
    return veri


def test_arac_dusus_oncesinden_depodaki_dosyayi_bayt_bayt_uretir():
    veri = _once_katmanlari()
    t = hat.ESKI_110M_SINIR_DUZELTMESI
    # Kâhin 1: yeniden kurulan düşüş öncesi hâl, tablodaki sha256_before.
    once = va.sinir_yuku_bayt(veri['layers'], veri['retrieved_utc'])
    assert hashlib.sha256(once).hexdigest() == t['sha256_before']
    # Kâhin 2: aracın düzeltme + yazma yolu depodaki dosyayı (sha256_after)
    # bayt bayt verir.
    dusulen = va.sinir_duzeltmesini_uygula(veri['layers'])
    sonra = va.sinir_yuku_bayt(veri['layers'], veri['retrieved_utc'])
    assert dusulen == len(t['points'])
    assert sonra == SINIR.read_bytes()
    assert hashlib.sha256(sonra).hexdigest() == t['sha256_after']
    assert json.loads(sonra)['point_count'] == t['point_count_after']


def test_tablodaki_cizgi_yoksa_yukselir_katman_degismez():
    veri = json.loads(SINIR.read_text(encoding='utf-8'))
    kopya = json.dumps(veri['layers'])
    with pytest.raises(RuntimeError, match='tam 1 bekleniyordu'):
        va.sinir_duzeltmesini_uygula(veri['layers'])
    assert json.dumps(veri['layers']) == kopya


def test_kutuda_baska_sinir_kalirsa_yukselir_katman_degismez():
    veri = _once_katmanlari()
    veri['layers']['borders'].append([33.5, 45.9, 34.0, 46.1])   # kutuda ikinci çizgi
    kopya = json.dumps(veri['layers'])
    with pytest.raises(hat.KaynakHatasi):
        va.sinir_duzeltmesini_uygula(veri['layers'])
    assert json.dumps(veri['layers']) == kopya


def _geojson(yol: pathlib.Path, cizgiler: list) -> pathlib.Path:
    yol.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {}, 'geometry': {'type': 'LineString', 'coordinates': c}}
        for c in cizgiler]}), encoding='utf-8')
    return yol


@pytest.mark.parametrize('perekop_var', [True, False])
def test_build_borders_yazmadan_once_duser(tmp_path, monkeypatch, perekop_var):
    t = hat.ESKI_110M_SINIR_DUZELTMESI
    sinirlar = [[[10.0, 50.0], [11.0, 51.0]]] + ([t['points']] if perekop_var else [])
    kaynak = {'ne_110m_admin_0_boundary_lines_land.geojson':
              _geojson(tmp_path / 'b.geojson', sinirlar),
              'ne_110m_coastline.geojson':
              _geojson(tmp_path / 'c.geojson', [[[0.0, 0.0], [1.0, 1.0]]])}
    monkeypatch.setattr(va, '_download', lambda url, dest, en_az, imza: kaynak[dest.name])
    hedef = tmp_path / 'img'
    monkeypatch.setattr(va, 'IMG_DIR', hedef)
    if not perekop_var:
        with pytest.raises(RuntimeError):
            va.build_borders()
        assert not (hedef / 'earth_borders.json').exists(), 'tablo tutmadı ama dosya yazıldı'
        return
    va.build_borders()
    yaz = json.loads((hedef / 'earth_borders.json').read_text(encoding='utf-8'))
    assert yaz['layers']['borders'] == [[10.0, 50.0, 11.0, 51.0]]
    assert yaz['point_count'] == 4


def test_arac_tabloyu_ice_aktarir_kopya_tutmaz():
    src = VA_YOL.read_text(encoding='utf-8')
    agac = ast.parse(src)
    ithal = [n for n in ast.walk(agac) if isinstance(n, ast.ImportFrom)
             and n.module == 'build_map_detail_assets']
    assert ithal and {'ESKI_110M_SINIR_DUZELTMESI', 'eski_110m_sinir_denetimi'} <= {
        a.name for n in ithal for a in n.names}
    sayilar = {n.value for n in ast.walk(agac) if isinstance(n, ast.Constant)
               and isinstance(n.value, float)}
    tablo = {v for nokta in hat.ESKI_110M_SINIR_DUZELTMESI['points'] for v in nokta}
    assert not (sayilar & tablo), 'Perekop noktaları araca kopyalanmış'
    # build_borders düzeltmeyi yazmadan önce çağırır.
    fn = next(n for n in agac.body if isinstance(n, ast.FunctionDef) and n.name == 'build_borders')
    govde = ast.get_source_segment(src, fn)
    assert govde.index('sinir_duzeltmesini_uygula(layers)') < govde.index('write_bytes')
