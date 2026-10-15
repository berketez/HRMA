# -*- coding: utf-8 -*-
"""ÖH Dalga-30 · kulvar ``arayuz-i18n`` · aşama 1 — bekçiler.

Her bekçi ters-mutasyonla (onarımı geçici geri al → KIRMIZI) kanıtlanmıştır;
kanıt ``docs/scofield/raw/OH/D30/arayuz-i18n/a1/mutasyon.json``.

Kapsanan kalemler
-----------------
* **P12aB1-01** (D29 devri) — Türkçe ekranda tek cümlede İKİ ondalık ayracı:
  ``tf`` yalnız ``typeof v === 'number'`` parametresini virgüle çeviriyordu;
  panellerin ``toFixed``/``fmt``/``fmtExp`` ile ÖNCEDEN biçimlediği metin
  parametreleri NOKTA kalıyordu (ölçüldü: ``i18n_common`` anahtarlı TF
  çağrılarının **61** parametresi; 14 anahtar ikisini bir arada taşıyor).
  Kalemi D27/D28/D29'da durduran engel — "dize parametrelerine dokunulursa
  sürüm/tarih/aralık bozulur" — burada SAYIYLA kapatılır: kapsam yalnız SAF
  ondalık sayı metnidir.
* **P11B1-14 kalan yarı** (D29 devri) — güverte ısı efsanesinin dört metni
  (``T_wall``, ``T_wall outer``, ``(reference cooled wall)``, efsane borç
  notu) hiçbir sözlükte yoktu; D29 arayuz-panel a3 onları TX() yoluna bağladı
  ama ``i18n_charts.js`` bu kulvarın sahası olduğu için TR karşılığı
  yazılamamıştı ("i18n devri"). TR modda güverte İngilizce basıyordu.
* **P12bB4-14** — ``site.tileUnit`` anahtarı hiçbir sözlükte yoktu: karo
  önbelleği göstergesi Türkçe kipte de "480 tile" yazıyordu.

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


def sozluk_bloklari(src):
    """``en:`` ve ``tr:`` blok gövdelerini döndürür (i18n dosya sözleşmesi)."""
    sinir = src.find('\n        tr: {')
    assert sinir > 0, 'tr bloğu bulunamadı'
    bas = src.find('\n        en: {')
    assert 0 <= bas < sinir, 'en bloğu bulunamadı'
    return src[bas:sinir], src[sinir:]


def _coz(kacisli):
    """Tek tırnaklı JS dizesindeki kaçışları çözer (\\u ve \\')."""
    def _u(m):
        return chr(int(m.group(1), 16))
    return re.sub(r'\\u([0-9a-fA-F]{4})', _u, kacisli).replace("\\'", "'")


def metin_anahtarli_sozluk(src, dil):
    """i18n_charts sözleşmesi: anahtar = İngilizce metnin KENDİSİ."""
    en, tr = sozluk_bloklari(src)
    blok = en if dil == 'en' else tr
    return {
        _coz(k): _coz(v)
        for k, v in re.findall(r"'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'", blok)
    }


def nokta_anahtarli_sozluk(src, dil):
    """Nokta ayrılmış anahtarlı sözlük (i18n_common / i18n_launch_site …)."""
    en, tr = sozluk_bloklari(src)
    blok = en if dil == 'en' else tr
    return {
        k: _coz(v)
        for k, v in re.findall(r"'([\w.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'", blok)
    }


# ===========================================================================
# P12aB1-01 — tf() ondalık ayracı (CANLI node koşumu)
# ===========================================================================
# Sonda i18n.js'i sandbox'ta koşar; hem onarılan davranışı hem de kalemi
# üç dalga boyunca durduran ENGELİN kapandığını (sürüm / tarih / aralık
# dizeleri BOZULMUYOR) tek çıktıda ölçer.
HARNESS_AYRAC = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const staticDir = process.argv[2];

const sandbox = {};
sandbox.window = sandbox;
sandbox.console = { log: function () {}, warn: function () {}, error: function () {} };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(staticDir + '/i18n.js', 'utf8'), sandbox,
                { filename: 'i18n.js' });
const I18N = sandbox.I18N;
if (!I18N) { console.log(JSON.stringify({ err: 'I18N yuklenemedi' })); process.exit(1); }

I18N.register({
    en: {
        'sonda.tank': 'Tank pressure ({tank} bar) must exceed chamber ({pc} bar). Minimum: {min} bar',
        'sonda.surum': 'HRMA v{version} is up to date.',
        'sonda.tek': '[{v}]'
    },
    tr: {
        'sonda.tank': 'Tank basıncı ({tank} bar) oda basıncından ({pc} bar) yüksek olmalı. Gereken alt sınır: {min} bar',
        'sonda.surum': 'HRMA v{version} güncel.',
        'sonda.tek': '[{v}]'
    }
}, 'sonda.js');

const out = {};

// (1) Parti raporundaki ÖLÇÜLEN cümle: {tank}/{pc} sayı, {min} metin.
I18N.setLang('tr');
out.tr_tank = I18N.tf('sonda.tank', { tank: 35.5, pc: 30.25, min: (36.3).toFixed(1) });
I18N.setLang('en');
out.en_tank = I18N.tf('sonda.tank', { tank: 35.5, pc: 30.25, min: (36.3).toFixed(1) });

// (2) Dize sınıfları: DEĞİŞMESİ beklenen ve BOZULMAMASI şart olanlar.
const KORPUS = {
    saf_ondalik: '36.3',
    saf_ondalik_kucuk: '0.184',
    saf_ondalik_negatif: '-3.5',
    ustel: '3.40e-3',
    tamsayi: '20000',
    surum: '2.6.27',
    surum_v: 'v2.6.27',
    surum_dort: '2.6.27.1',
    tarih: '2026-09-08',
    tarih_iso: '2026-09-08T12:00:00Z',
    aralik_mm: '10-60 mm',
    aralik_virgullu: '0,09-0,49',
    aralik_noktali: '0.09-0.49',
    birimli: '36.3 bar',
    yuzde: '%0.43',
    em_tire: '—',
    soru: '?',
    turbulans: 'k-omega SST',
    cozunurluk: 'medium'
};
out.tr_korpus = {};
out.en_korpus = {};
I18N.setLang('tr');
Object.keys(KORPUS).forEach(function (k) {
    out.tr_korpus[k] = I18N.tf('sonda.tek', { v: KORPUS[k] }).slice(1, -1);
});
I18N.setLang('en');
Object.keys(KORPUS).forEach(function (k) {
    out.en_korpus[k] = I18N.tf('sonda.tek', { v: KORPUS[k] }).slice(1, -1);
});

// (3) Sürüm cümlesi (update_check.js:618 deseni) TR'de bozulmuyor mu?
I18N.setLang('tr');
out.tr_surum_cumlesi = I18N.tf('sonda.surum', { version: '2.6.27' });

// (4) Sayı yolu (I18N.number) hâlâ tek kaynaktan mı okuyor?
out.tr_sayi = I18N.number(36.3);
I18N.setLang('en');
out.en_sayi = I18N.number(36.3);

// (5) Yuvarlama YOK: çağıranın seçtiği basamak sayısı korunur.
I18N.setLang('tr');
out.tr_basamak_korunur = I18N.tf('sonda.tek', { v: (2).toFixed(6) }).slice(1, -1);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def ayrac(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    betik = tmp_path_factory.mktemp('d30a1') / 'sonda_ayrac.js'
    betik.write_text(HARNESS_AYRAC, encoding='utf-8')
    ph = subprocess.run([NODE, str(betik), str(JS)], capture_output=True,
                        text=True, timeout=120)
    assert ph.returncode == 0, ph.stderr[-2000:]
    return json.loads(ph.stdout.strip().split('\n')[-1])


@node_gerek
def test_p12ab1_01_tek_cumlede_tek_ondalik_ayraci(ayrac):
    """ÖLÇÜLEN cümlede artık tek ayraç var.

    Parti raporunun ölçtüğü hâl (raw/P12A/B1-rapor.md#P12aB1-01):
    ``Tank basıncı (35,5 bar) … Gereken alt sınır: 36.3 bar`` — ``{tank}``
    ve ``{pc}`` sayı olduğu için virgül, ``{min}`` ise ``toFixed(1)`` ile
    metne çevrildiği için nokta.
    """
    tr = ayrac['tr_tank']
    assert '36,3 bar' in tr, tr
    assert '36.3' not in tr, tr
    # Cümlede NOKTA hiç kalmamalı (cümle sonu noktası hariç: sayıya bitişik
    # nokta aranır).
    assert not re.search(r'\d\.\d', tr), tr
    # İngilizce yol DEĞİŞMEZ.
    assert '36.3 bar' in ayrac['en_tank'], ayrac['en_tank']
    assert ',' not in re.sub(r'[^\d.,]', '', ayrac['en_tank']).replace('.', ''), ayrac['en_tank']


@node_gerek
def test_p12ab1_01_saf_ondalik_metin_virgule_cevrilir(ayrac):
    """toFixed/fmtExp çıktısı olan SAF sayı metni TR'de virgül alır."""
    tr = ayrac['tr_korpus']
    assert tr['saf_ondalik'] == '36,3', tr['saf_ondalik']
    assert tr['saf_ondalik_kucuk'] == '0,184', tr['saf_ondalik_kucuk']
    assert tr['saf_ondalik_negatif'] == '-3,5', tr['saf_ondalik_negatif']
    assert tr['ustel'] == '3,40e-3', tr['ustel']
    # Ondalık kesri olmayan metinde çevrilecek ayraç YOK.
    assert tr['tamsayi'] == '20000', tr['tamsayi']


@node_gerek
def test_p12ab1_01_surum_tarih_aralik_BOZULMAZ(ayrac):
    """D27/D28/D29 engelinin kapanışı: riskli dize sınıfları AYNEN kalır.

    Kalem üç dalga boyunca açılamadı çünkü onarımın ``tf``'in DİZE
    parametrelerine dokunacağı, dolayısıyla sürüm (``v2.6.27``), tarih
    (``2026-09-08``) ve aralık (``10-60 mm``, ``0,09-0,49``) dizelerini
    bozacağı gerekçesi vardı. Kapsam SAF ondalık sayı metniyle
    sınırlandığı için bu sınıfların hiçbiri desene uymaz.
    """
    tr = ayrac['tr_korpus']
    bozulmamali = {
        'surum': '2.6.27', 'surum_v': 'v2.6.27', 'surum_dort': '2.6.27.1',
        'tarih': '2026-09-08', 'tarih_iso': '2026-09-08T12:00:00Z',
        'aralik_mm': '10-60 mm', 'aralik_virgullu': '0,09-0,49',
        'aralik_noktali': '0.09-0.49', 'birimli': '36.3 bar', 'yuzde': '%0.43',
        'em_tire': '—', 'soru': '?', 'turbulans': 'k-omega SST',
        'cozunurluk': 'medium',
    }
    for ad, beklenen in bozulmamali.items():
        assert tr[ad] == beklenen, '%s: %r != %r' % (ad, tr[ad], beklenen)
    assert ayrac['tr_surum_cumlesi'] == 'HRMA v2.6.27 güncel.', ayrac['tr_surum_cumlesi']


@node_gerek
def test_p12ab1_01_ingilizce_kipte_hicbir_metin_degismez(ayrac):
    """EN kipte ayraç NOKTA'dır: hiçbir dize parametresi değişmez."""
    beklenen = {
        'saf_ondalik': '36.3', 'saf_ondalik_kucuk': '0.184',
        'saf_ondalik_negatif': '-3.5', 'ustel': '3.40e-3', 'tamsayi': '20000',
        'surum': '2.6.27', 'surum_v': 'v2.6.27', 'surum_dort': '2.6.27.1',
        'tarih': '2026-09-08', 'tarih_iso': '2026-09-08T12:00:00Z',
        'aralik_mm': '10-60 mm', 'aralik_virgullu': '0,09-0,49',
        'aralik_noktali': '0.09-0.49', 'birimli': '36.3 bar', 'yuzde': '%0.43',
        'em_tire': '—', 'soru': '?', 'turbulans': 'k-omega SST',
        'cozunurluk': 'medium',
    }
    for ad, deger in beklenen.items():
        assert ayrac['en_korpus'][ad] == deger, '%s: %r' % (ad, ayrac['en_korpus'][ad])


@node_gerek
def test_p12ab1_01_yuvarlama_yapilmaz_ve_sayi_yolu_tek_kaynak(ayrac):
    """Metin yolu basamak sayısını DEĞİŞTİRMEZ; sayı yolu aynı ayracı kullanır.

    ``toFixed(6)`` ile gelen ``2.000000`` altı basamağını korur — aksi
    hâlde ekranda çağıranın seçmediği bir duyarlık ilan edilirdi.
    """
    assert ayrac['tr_basamak_korunur'] == '2,000000', ayrac['tr_basamak_korunur']
    assert ayrac['tr_sayi'] == '36,3', ayrac['tr_sayi']
    assert ayrac['en_sayi'] == '36.3', ayrac['en_sayi']


def test_p12ab1_01_ayrac_tek_kaynakta_tanimli():
    """Ondalık ayracı iki yerde YAZILMAZ (doktrin 4 — tek kaynak).

    Kusur tam da ayracın iki ayrı yolda (sayı / metin) ayrı ayrı ele
    alınmasından doğdu; ``ondalikAyraci()`` tek kapıdır.
    """
    src = oku(JS / 'i18n.js')
    assert src.count('function ondalikAyraci(') == 1, 'tek kaynak yardımcısı yok'
    # Ham "'tr' ? ',' : '.'" kararı başka yerde tekrarlanmamalı.
    kacak = re.findall(r"lang\s*===\s*'tr'\s*\)\s*\{?\s*[a-zA-Z]*\s*=?\s*.*replace\('\.'", src)
    assert kacak == [], kacak
    assert src.count("replace('.', ondalikAyraci())") == 2, \
        'hem number() hem decimalText() tek kaynaktan okumalı'


def test_p12ab1_01_kapsam_dar_kalir():
    """Desen genişletilirse (ör. rakam-arası her nokta) sürüm dizesi bozulur.

    Bu bekçi deseni MANDALLAR: yalnız baştan sona sayı olan ve ondalık
    kesri bulunan metin çevrilebilir.
    """
    src = oku(JS / 'i18n.js')
    m = re.search(r'var SAF_ONDALIK_METIN = (/.*?/);', src)
    assert m, 'SAF_ONDALIK_METIN deseni bulunamadı'
    desen = m.group(1)
    assert desen.startswith('/^') and desen.endswith('$/'), desen
    assert r'\d+\.\d+' in desen, desen


# ===========================================================================
# P11B1-14 (kalan yarı) — güverte ısı efsanesinin TR karşılıkları
# ===========================================================================
def _deck_sabitleri():
    src = oku(JS / 'motor_viz_deck.js')
    out = {}
    for ad, govde in re.findall(
            r"\bvar\s+([A-Z][A-Z0-9_]*)\s*=\s*((?:'(?:[^'\\]|\\.)*'\s*(?:\+\s*)?)+);", src):
        out[ad] = ''.join(_coz(p[1:-1]) for p in re.findall(r"'(?:[^'\\]|\\.)*'", govde))
    return src, out


def test_p11b114_isi_efsanesi_metinleri_TR_sozlukte():
    """Güverte ısı efsanesinin dört metni TR karşılığıyla sözlükte.

    ÖLÇÜLEN kusur (a1/once_p11b114.json): ``(reference cooled wall)`` ve
    efsane borç notu HİÇBİR sözlükte yoktu; ``T_wall`` ile ``T_wall outer``
    de yoktu. D29 arayuz-panel a3 bunları TX() yoluna bağladı ama
    ``i18n_charts.js`` bu kulvarın sahası olduğundan TR karşılığı
    yazılamamıştı — TR modda güverte İngilizce basıyordu.
    """
    deck_src, sabit = _deck_sabitleri()
    charts = oku(JS / 'i18n_charts.js')
    en = metin_anahtarli_sozluk(charts, 'en')
    tr = metin_anahtarli_sozluk(charts, 'tr')

    aile = sorted(k for k in sabit if k.startswith('HEAT_LEGEND'))
    assert aile == ['HEAT_LEGEND_DEBT_NOTE', 'HEAT_LEGEND_TEXT',
                    'HEAT_LEGEND_WALL_REF'], aile
    for ad in aile:
        metin = sabit[ad]
        assert re.search(r'TXK?\(\s*%s\s*\)' % ad, deck_src), '%s TX yolundan geçmiyor' % ad
        assert metin in en, '%s EN sözlükte yok' % ad
        assert metin in tr, '%s TR sözlükte yok' % ad
        assert tr[metin] != metin, '%s TR karşılığı hâlâ İngilizce' % ad

    # Cidar sıcaklığı etiketleri (efsanenin alt satırı) de çevrili.
    for metin in ('T_wall', 'T_wall outer'):
        assert metin in en, '%r EN sözlükte yok' % metin
        assert metin in tr, '%r TR sözlükte yok' % metin
        assert tr[metin] != metin, '%r TR karşılığı hâlâ İngilizce' % metin


def test_p11b114_cidar_terimi_kardes_anahtarlarla_birebir():
    """Terim tekliği: 'referans soğutulmuş cidar' + 'T_cidar' ailesi.

    D28 dersi (test_z5i18n_supurme 'aynı İngilizce tek Türkçe'): yeni
    anahtarın TR karşılığı kardeşiyle birebir olmalı, yoksa aynı sayı iki
    sayfada iki ayrı adla okunur — kalemin kendi şikâyeti budur.
    """
    charts = oku(JS / 'i18n_charts.js')
    tr = metin_anahtarli_sozluk(charts, 'tr')
    assert tr['(reference cooled wall)'] == '(referans soğutulmuş cidar)', \
        tr['(reference cooled wall)']
    # advanced.html'in aynı niteleyiciyi taşıyan anahtarı ile aynı terim.
    adv = nokta_anahtarli_sozluk(oku(JS / 'i18n_advanced.js'), 'tr')
    assert 'referans soğutulmuş cidar' in adv['adv.txt.wallHeatFluxBartz'], \
        adv['adv.txt.wallHeatFluxBartz']
    # T_wall ailesi tek kökten türer.
    assert tr['T_wall'] == 'T_cidar', tr['T_wall']
    assert tr['T_wall inner'] == 'T_cidar iç', tr['T_wall inner']
    assert tr['T_wall outer'] == 'T_cidar dış', tr['T_wall outer']


def test_p11b114_borc_notu_2_5_kat_TR_metinde():
    """Borç notunun TR karşılığı ölçüyü SAYIYLA taşır (~2,5 kat).

    Beyan çözüm değildir ama beyanın kendisi eksiksiz olmalı: TR metin de
    hem alan adını (``gas_side_analysis…``) hem oranı taşır.
    """
    charts = oku(JS / 'i18n_charts.js')
    tr = metin_anahtarli_sozluk(charts, 'tr')
    _, sabit = _deck_sabitleri()
    borc_tr = tr[sabit['HEAT_LEGEND_DEBT_NOTE']]
    assert 'gas_side_analysis' in borc_tr, borc_tr
    assert '2,5' in borc_tr, borc_tr
    assert 'TASARIM' in borc_tr, borc_tr


# ===========================================================================
# P12bB4-14 — site.tileUnit
# ===========================================================================
def test_p12bb4_14_tile_birimi_sozlukte():
    """``site.tileUnit`` EN+TR blok İÇİNDE tanımlı.

    ÖLÇÜLEN kusur (a1/once_p12bb414.json): launch_site.html'in kullandığı 91
    ``site.*`` anahtarından ikisi sözlükte yoktu; biri dinamik önek
    (``'site.src.' + src``, yanlış pozitif), diğeri ``site.tileUnit`` —
    karo önbelleği göstergesi Türkçe kipte de "480 tile" yazıyordu.
    """
    src = oku(JS / 'i18n_launch_site.js')
    en = nokta_anahtarli_sozluk(src, 'en')
    tr = nokta_anahtarli_sozluk(src, 'tr')
    assert en.get('site.tileUnit') == 'tile', en.get('site.tileUnit')
    assert tr.get('site.tileUnit') == 'karo', tr.get('site.tileUnit')


def test_p12bb4_14_cagri_yeri_ve_anahtar_ayni_anda():
    """Ölü çeviri yok: anahtarın ÇAĞRI YERİ üründe duruyor.

    T74 onarımı yeniden-basımı düzeltmiş ama anahtarı hiç eklememişti;
    ters durum (anahtar var, çağrı yok) da kabul edilemez.
    """
    html = oku(TPL / 'launch_site.html')
    assert re.search(r"t\(\s*'site\.tileUnit'\s*,\s*'tile'\s*\)", html), \
        'site.tileUnit çağrı yeri launch_site.html içinde bulunamadı'


def test_p12bb4_14_launch_site_anahtar_yuzeyi_kapali():
    """launch_site.html'in kullandığı her statik ``site.*`` anahtarı tanımlı.

    Tek satır yamamak yetmez: yüzeyin tamamı ölçülür. Tek istisna, sözlükte
    varyantlarıyla tanımlı dinamik önek ``'site.src.' + src``.
    """
    html = oku(TPL / 'launch_site.html')
    kullanilan = set()
    for desen in (r"\bt\s*\(\s*'(site\.[\w.]+)'", r"\btf\s*\(\s*'(site\.[\w.]+)'",
                  r'data-i18n(?:-title|-placeholder)?\s*=\s*"(site\.[\w.]+)"'):
        kullanilan |= set(re.findall(desen, html))
    kullanilan.discard('site.src.')          # dinamik önek (i18n_launch_site.js:13)

    tanimli_en, tanimli_tr = set(), set()
    for p in sorted(JS.glob('i18n*.js')):
        s = oku(p)
        if '\n        en: {' not in s:
            continue
        tanimli_en |= set(nokta_anahtarli_sozluk(s, 'en'))
        tanimli_tr |= set(nokta_anahtarli_sozluk(s, 'tr'))

    eksik_en = sorted(kullanilan - tanimli_en)
    eksik_tr = sorted(kullanilan - tanimli_tr)
    assert eksik_en == [], eksik_en
    assert eksik_tr == [], eksik_tr
    assert len(kullanilan) >= 90, len(kullanilan)
