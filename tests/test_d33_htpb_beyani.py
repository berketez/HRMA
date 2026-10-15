"""HTPB yanlılık beyanının ARAYÜZ DİLİNDE TAM olması (ÖH D33-3 / OH-D33-46).

ÖLÇÜLEN KUSUR (bu depo, 16 Eylül 2026; varsayılan hibrit koşusu — HTPB/N₂O,
1 kN, O/F 7,5 — ürünün KENDİ ``app.js::warnToText`` yolundan node içinde
çizdirildi). Türkçe uyarı panelinde ``warn.hybrid.htpb_coeff_bias`` satırı
şöyle basılıyordu ve bu hâliyle Türkçe kullanma kılavuzunun uyarı paneli
ekran karesine (``docs/user_guide/img/tr-07-warnings.png``, 3. satır) girdi::

    ... kampanya başına bant %-50.6 · -41.8 ve kampanyalar şunlar:
    {"campaign":"Rezaei 2018","oxidizer":"n2o","points":29,"bias_pct":-50.6,
    "medape_pct":50.9} · {"campaign":"Carmicino 2013", ...}. İki belirleme
    UZLAŞTIRILMADI (uzlaştırıldı mı: false); ölçülen gerekçeler: record pools
    differ (43 own vs 46 independent points) · the product path runs a
    G_ox-fitted coefficient under a G_total flux closure, which lifts the
    predicted regression by +10-18% (propellant_database.py header). ...
    zarf eşleşmesi true.

Yani tek cümlede DÖRT ayrı kusur vardı:

  1. İngilizce nesir — "uzlaşmama gerekçeleri" Python tarafında İNGİLİZCE
     CÜMLE olarak üretiliyordu; JS'in çevirecek bir kodu yoktu.
  2. Ham JSON — kampanya satırları ``code`` taşımadığı için ``warnToText``
     onları ``JSON.stringify`` ile yazıya döküyordu (TR ve EN'de birden).
  3. Ham ikili — ``false`` / ``true`` doğrudan kullanıcıya basılıyordu.
  4. Noktalı ondalık — bant ``-50.6 · -41.8`` diye çıkıyordu, oysa aynı
     cümlenin öteki sayıları virgüllüydü (%-39,5): tek satırda iki ayraç.

ONARIMIN KANONU (bu deponun ``warn.*`` sözleşmesi): sayı ve olgu Python'dan,
DİL JS'ten. Python artık nesir değil ``{code, params, severity}`` kaydı
yayımlıyor; ``i18n_common.js`` o kodları çeviriyor ve ikili/sayı-dizisi/nesir
parametrelerini sunum katmanında yerelleştiriyor.

HİÇBİR SAYI DEĞİŞMEDİ. Bu dosyanın ikinci bölümü tam olarak bunu ölçer:
yayımlanan yükün her sayısı LİTERAL olarak yazılıdır (ürün sabiti İTHAL
EDİLMEZ — P14S1-02: eşiği kendinden türeten bekçi, eşik değişince sessizce
yeşil kalır).
"""

import contextlib
import io
import json
import pathlib
import re
import shutil
import subprocess

import pytest

# Uyarı susturması YALNIZ bu modülün testlerine (süreç geneli değil —
# test_d32_altyapi_a1 OH-D31-19 envanteri; taban kırmızısı onarımı, 24 Eyl).
pytestmark = pytest.mark.filterwarnings('ignore')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
DICT_JS = STATIC_JS / 'i18n_common.js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason='node kurulu değil — uyarı metni ürünün KENDİ çizim yolundan '
           'ölçülemiyor (kurulum: `brew install node`)')

KOD = 'warn.hybrid.htpb_coeff_bias'

#: Ürünün varsayılan hibrit koşusu (kılavuz ekran karesindeki koşu).
TEMEL = dict(of_ratio=7.5, chamber_pressure=20, atmospheric_pressure=1.0,
             fuel_type='htpb', oxidizer_type='n2o', thrust=1000, burn_time=10)


# ---------------------------------------------------------------------------
# Ürünün kendi çizim yolu — node, sahte DOM, GERÇEK dosyalar
# ---------------------------------------------------------------------------
# Kopya render YOKTUR: i18n.js + i18n_common.js + i18n_charts.js +
# analysis_dock.js + app.js yüklenir ve ``window.warnToText`` çağrılır —
# tarayıcıda uyarı panelini yazan fonksiyonun ta kendisi.
CIZIM_KOSUCUSU = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._a = {};
    this.innerHTML = ''; this.dataset = {}; this.id = ''; this.textContent = '';
}
El.prototype.appendChild = function (x) { this.children.push(x); return x; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._a, k) ? this._a[k] : null; };
El.prototype.removeAttribute = function (k) { delete this._a[k]; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.querySelector = function () { return null; };
El.prototype.addEventListener = function () {};
const depo = {};
const doc = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    documentElement: new El('html'),
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () {}, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    alert: function () {}, document: doc,
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
kos(path.join(staticDir, 'hud.js'));
kos(path.join(staticDir, 'analysis_dock.js'));
kos(path.join(staticDir, 'app.js'));
const OUT = {};
['tr', 'en'].forEach(function (dil) {
    sb.window.I18N.setLang(dil);
    OUT[dil] = {};
    Object.keys(P).forEach(function (ad) {
        OUT[dil][ad] = (P[ad] === null) ? null : sb.window.warnToText(P[ad]);
    });
});
process.stdout.write(JSON.stringify(OUT));
"""


def _kos(**kw):
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    ayar = dict(TEMEL)
    ayar.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return HybridRocketEngine(**ayar).calculate()


def _uyari(sonuc, kod):
    for u in (sonuc.get('warnings') or []):
        if isinstance(u, dict) and u.get('code') == kod:
            return u
    return None


@pytest.fixture(scope='module')
def kayitlar():
    """Ürünün GERÇEKTEN yayımladığı uyarı kayıtları (uydurma yük yok)."""
    n2o = _uyari(_kos(), KOD)
    assert n2o is not None, (
        '%s varsayılan hibrit koşusunda hiç ateşlenmedi; bu dosya uyarının '
        'VARLIĞINI değil METNİNİ ölçer, kapı ölmüşse önce o onarılmalı.' % KOD)
    lox = _uyari(_kos(oxidizer_type='lox'), KOD)
    assert lox is not None, '%s lox koşusunda ateşlenmedi' % KOD
    sogutmali = _uyari(_kos(cooling_type='radial'),
                       'warn.hybrid.cooling_channels_assumed')
    return {'n2o': n2o, 'lox': lox, 'kanal': sogutmali}


@pytest.fixture(scope='module')
def metinler(kayitlar, tmp_path_factory):
    if NODE is None:                                    # pragma: no cover
        pytest.skip('node kurulu değil')
    dizin = tmp_path_factory.mktemp('htpb_beyani')
    girdi = dizin / 'kayitlar.json'
    girdi.write_text(json.dumps(kayitlar, ensure_ascii=False),
                     encoding='utf-8')
    kosucu = dizin / 'cizim.js'
    kosucu.write_text(CIZIM_KOSUCUSU, encoding='utf-8')
    proc = subprocess.run(
        [NODE, str(kosucu), str(STATIC_JS), str(girdi)],
        capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('ürünün çizim yolu node altında çöktü:\n'
                                  + proc.stderr[-4000:])
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# 1. TÜRKÇE ÇIKTI — İngilizce parça, ham ikili, noktalı ondalık KALMADI
# ---------------------------------------------------------------------------
#: ÖNCE ölçülen (ve kılavuz ekran karesine giren) İngilizce parçalar.
#: Her biri TR çıktıda ADIYLA aranır: biri geri dönerse bekçi kırmızı verir.
TR_DE_OLMAMASI_GEREKEN = (
    'record pools differ',
    'the product path runs',
    'flux closure',
    'independent points',
    'propellant_database.py header',
    'median absolute error',
    'The published bias body was measured',
    'which is outside that envelope',
    'No bias was extrapolated',
    'The band is reported for the coefficient in force',
    'points:',
    'campaigns',
)

#: Künye/makine dizeleri: yerelleşmezler, o yüzden ondalık taramasından
#: ÖNCE cümleden ayrılırlar (ayrım cümle ⟷ künyedir).
KUNYE_DESENI = re.compile(r'\S+\.(?:md|py|js|html|json)\b')


@node_gerekli
@pytest.mark.parametrize('kosu', ['n2o', 'lox'])
def test_turkce_cikti_tamamen_turkce(metinler, kosu):
    tr = metinler['tr'][kosu]
    kalan = [p for p in TR_DE_OLMAMASI_GEREKEN if p in tr]
    assert not kalan, (
        'Türkçe uyarı panelinde İngilizce parça kaldı (%s koşusu): %r\n'
        'Beyan yarım çevrilmiş demektir; ölçülen kusurun ta kendisi budur.\n'
        'TAM METİN:\n%s' % (kosu, kalan, tr))


@node_gerekli
@pytest.mark.parametrize('kosu', ['n2o', 'lox'])
def test_turkce_ciktida_ham_ikili_yok(metinler, kosu):
    """``true`` / ``false`` hiçbir dilde kullanıcı metni değildir."""
    tr = metinler['tr'][kosu]
    ham = re.findall(r'\b(?:true|false)\b', tr, re.I)
    assert not ham, (
        'Türkçe metinde ham JSON ikilisi basılıyor: %r\nTAM METİN:\n%s'
        % (ham, tr))
    assert 'evet' in tr or 'hayır' in tr, (
        'İkili alanlar sözcüğe çevrilmemiş görünüyor (ne evet ne hayır '
        'geçiyor):\n%s' % tr)


@node_gerekli
@pytest.mark.parametrize('kosu', ['n2o', 'lox'])
def test_turkce_ciktida_ham_json_yok(metinler, kosu):
    tr = metinler['tr'][kosu]
    for im in ('{"', '":', 'medape_pct', 'bias_pct', 'oxidizer\u0022'):
        assert im not in tr, (
            'Türkçe metinde ham JSON kalıntısı (%r) var — kampanya satırları '
            'çevrilebilir kaba girmemiş:\n%s' % (im, tr))


@node_gerekli
@pytest.mark.parametrize('kosu', ['n2o', 'lox'])
def test_turkce_ciktida_noktali_ondalik_yok(metinler, kosu):
    """TR cümlesinde ondalık ayracı VİRGÜLdür; künye dizeleri hariç."""
    tr = KUNYE_DESENI.sub(' ', metinler['tr'][kosu])
    noktali = re.findall(r'-?\d+\.\d+', tr)
    assert not noktali, (
        'Türkçe cümlede noktalı ondalık kaldı: %r — aynı cümlede iki ayraç '
        'okunuyor (ölçülen kusur: bant "%%-50.6 · -41.8" iken öteki sayılar '
        'virgüllüydü).\nTAM METİN:\n%s' % (noktali, metinler['tr'][kosu]))
    assert '-50,6' in tr and '-41,8' in tr, (
        'Kampanya bandı Türkçe ayraçla basılmıyor:\n%s' % tr)


@node_gerekli
def test_turkce_ciktida_gerekceler_ve_kampanyalar_okunuyor(metinler):
    """Onarım metni SUSTURMADI: her iki gerekçe ve üç kampanya da orada."""
    tr = metinler['tr']['n2o']
    for parca in ('iki kayıt havuzu aynı küme değil',
                  'G_total akı kapanışı',
                  'Rezaei 2018', 'Carmicino 2013', 'Heydari 2017',
                  'medyan mutlak hata bildirilmedi'):
        assert parca in tr, ('Türkçe beyandan parça düşmüş: %r\n%s'
                             % (parca, tr))


@node_gerekli
def test_ikili_cevirisi_bu_uyariya_ozel_degil(metinler, kayitlar):
    """Sarmalayıcı BİR uyarıya değil, ikili alanın KENDİSİNE bakar.

    ``warn.hybrid.cooling_channels_assumed`` de ``geometry_modelled=False``
    yayımlar; o da ham ``false`` basmamalıdır.
    """
    if kayitlar['kanal'] is None:                       # pragma: no cover
        pytest.skip('kanal geometrisi uyarısı bu koşuda doğmadı')
    tr = metinler['tr']['kanal']
    assert not re.findall(r'\b(?:true|false)\b', tr, re.I), (
        'kanal geometrisi uyarısı ham ikili basıyor:\n%s' % tr)


# ---------------------------------------------------------------------------
# 2. İNGİLİZCE ÇIKTI BOZULMADI — anlam korundu, ham JSON oradan da kalktı
# ---------------------------------------------------------------------------
@node_gerekli
def test_ingilizce_cikti_anlamini_koruyor(metinler):
    en = metinler['en']['n2o']
    for parca in ('The built-in HTPB/ABS regression coefficients are biased',
                  'median bias -39.5%',
                  'median absolute error 46.6%',
                  '46 published points',
                  '-47.6% bias',
                  '49.4% median absolute error',
                  '-50.6', '-41.8',
                  'Rezaei 2018', 'Carmicino 2013', 'Heydari 2017',
                  'were NOT reconciled',
                  'the two record pools are not the same set',
                  'G_total flux closure',
                  '10-18%',
                  'deliberately NOT retuned',
                  'docs/arastirma/fizik/A3-hibrit-regresyon.md'):
        assert parca in en, ('İngilizce beyandan parça düşmüş: %r\n%s'
                             % (parca, en))


@node_gerekli
def test_ingilizce_ciktida_ham_json_ve_ikili_yok(metinler):
    """EN kullanıcı da ham JSON / ham ikili görmemeli (aynı kusur, aynı hüküm)."""
    en = metinler['en']['n2o']
    assert '{"' not in en and '"campaign"' not in en, (
        'İngilizce metinde ham JSON kalmış:\n%s' % en)
    assert not re.findall(r'\b(?:true|false)\b', en), (
        'İngilizce metinde ham ikili kalmış:\n%s' % en)
    assert 'reconciled: no' in en, (
        'İngilizce ikili sözcüğe çevrilmemiş:\n%s' % en)


@node_gerekli
def test_ingilizce_ciktida_virgullu_ondalik_yok(metinler):
    """EN ondalık ayracı NOKTAdır — sarmalayıcı yanlış yöne çalışmamalı."""
    en = metinler['en']['n2o']
    assert not re.findall(r'\d,\d', en), (
        'İngilizce metne Türkçe ondalık ayracı sızmış:\n%s' % en)


# ---------------------------------------------------------------------------
# 3. HİÇBİR SAYI DEĞİŞMEDİ — yük LİTERAL olarak kilitli
# ---------------------------------------------------------------------------
#: Yayımlanan kampanya gövdesi (A3:187-192). Ürün sabiti BİLEREK ithal
#: edilmez: sayı sessizce değişirse bu bekçi kırmızı verir.
KAMPANYA_GOVDESI = (
    ('Rezaei 2018', 'n2o', 29, -50.6, 50.9),
    ('Carmicino 2013', 'n2o', 16, -41.8, 43.5),
    ('Heydari 2017', 'n2o', 1, -50.3, None),
)


def test_yayimlanan_sayilar_degismedi(kayitlar):
    p = kayitlar['n2o']['params']
    assert p['bias_pct'] == -39.5
    assert p['medape_pct'] == 46.6
    assert p['own_pool_points'] == 43
    assert p['independent_pool_points'] == 46
    assert p['independent_pool_bias_pct'] == -47.6
    assert p['independent_pool_medape_pct'] == 49.4
    assert p['independent_campaign_bias_band_pct'] == [-50.6, -41.8]
    assert p['reconciled'] is False
    assert p['campaign_scope_match'] is True
    assert p['source'] == 'docs/arastirma/fizik/A3-hibrit-regresyon.md'


def test_kampanya_satirlarinin_makine_alanlari_yerinde(kayitlar):
    """Çevrilebilir kap EKLENDİ, makine sözleşmesi DEĞİŞMEDİ."""
    kampanyalar = kayitlar['n2o']['params']['independent_campaigns']
    olculen = tuple(
        (k['campaign'], k['oxidizer'], k['points'], k['bias_pct'],
         k.get('medape_pct'))
        for k in kampanyalar)
    assert olculen == KAMPANYA_GOVDESI, olculen
    for k in kampanyalar:
        assert k['code'].startswith('warn.hybrid.htpb_campaign_entry'), k
        assert isinstance(k['params'], dict) and k['params'], k
        # params kampanyanın KENDİ alanlarından türetilir; ikinci bir sayı
        # kaynağı yoktur.
        for ad, deger in k['params'].items():
            assert k[ad] == deger, (ad, k)


def test_uzlasmama_gerekceleri_kayit_oldu(kayitlar):
    """Gerekçeler nesir değil ``{code, params}`` kaydı; sayıları ADIYLA taşır."""
    gerekceler = kayitlar['n2o']['params']['unreconciled_reasons']
    assert len(gerekceler) >= 2, gerekceler
    kodlar = [g['code'] for g in gerekceler]
    assert kodlar == ['warn.hybrid.htpb_bias_unreconciled_pools',
                      'warn.hybrid.htpb_bias_unreconciled_flux_closure'], kodlar
    havuz, aki = gerekceler
    assert havuz['params'] == {'own_pool_points': 43,
                               'independent_pool_points': 46}
    assert aki['params']['lift_low_pct'] == 10
    assert aki['params']['lift_high_pct'] == 18
    assert aki['params']['source'] == 'propellant_database.py'


def test_aki_kapanisi_bandi_tek_kaynaktan_okunuyor():
    """+%10-18 artık nesrin içinde değil, ADI olan bir sabitte (kural 11)."""
    from hrma.data.propellant_database import (
        HYBRID_GOX_FIT_UNDER_GTOTAL_LIFT_PCT)
    assert HYBRID_GOX_FIT_UNDER_GTOTAL_LIFT_PCT == (10, 18)


# ---------------------------------------------------------------------------
# 4. SÖZLÜK AYAĞI — kodların karşılığı iki dilde de var, ikili anahtarları
#    ürün tarafında ADIYLA yazılı
# ---------------------------------------------------------------------------
ANAHTAR_SATIRI = re.compile(
    r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',?\s*$", re.M)


def _blok(dil):
    """i18n_common.js içindeki bir dil bloğunun {anahtar: metin} sözlüğü."""
    kaynak = DICT_JS.read_text(encoding='utf-8')
    bas = kaynak.index("        %s: {" % dil)
    derinlik = 0
    for i in range(bas + len("        %s: " % dil), len(kaynak)):
        if kaynak[i] == '{':
            derinlik += 1
        elif kaynak[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                govde = kaynak[bas:i]
                break
    else:                                               # pragma: no cover
        pytest.fail("i18n_common.js '%s' bloğu kapanmıyor" % dil)
    return {k.replace("\\'", "'"): v.replace("\\'", "'")
            for k, v in ANAHTAR_SATIRI.findall(govde)}


YENI_KODLAR = (
    'warn.hybrid.htpb_bias_unreconciled_pools',
    'warn.hybrid.htpb_bias_unreconciled_flux_closure',
    'warn.hybrid.htpb_campaign_entry',
    'warn.hybrid.htpb_campaign_entry_no_medape',
)


@pytest.mark.parametrize('kod', YENI_KODLAR)
def test_yeni_kodlarin_karsiligi_iki_dilde_de_var(kod):
    en, tr = _blok('en'), _blok('tr')
    assert kod in en, 'EN sözlüğünde yok: %s' % kod
    assert kod in tr, 'TR sözlüğünde yok: %s' % kod
    assert set(re.findall(r'\{(\w+)\}', en[kod])) == set(
        re.findall(r'\{(\w+)\}', tr[kod])), (
        '%s: yer tutucular iki dilde aynı değil' % kod)


def test_ikili_anahtarlari_urun_tarafinda_adiyla_yazili():
    """Sarmalayıcının kullandığı anahtar, yükü yayımlayan modülde tanımlı.

    Bu bağ mekanik olarak da gereklidir: ``tests/test_i18n_common.py``
    kullanım taraması SÖZLÜK dosyalarını taramaz, yani anahtar yalnız
    ``i18n_common.js``te kalsaydı "ölü çeviri" sayılırdı.
    """
    from hrma.engines.hybrid_rocket_engine import WARNING_BOOL_I18N_KEYS
    assert WARNING_BOOL_I18N_KEYS == {True: 'common.bool.true',
                                      False: 'common.bool.false'}
    en, tr = _blok('en'), _blok('tr')
    kaynak = DICT_JS.read_text(encoding='utf-8')
    for anahtar in WARNING_BOOL_I18N_KEYS.values():
        assert anahtar in en and anahtar in tr, (
            '%s iki sözlükten birinde yok' % anahtar)
        assert kaynak.count("'%s'" % anahtar) >= 2, (
            '%s sözlükte var ama sarmalayıcı onu çağırmıyor' % anahtar)
    assert en['common.bool.true'] == 'yes'
    assert en['common.bool.false'] == 'no'
    assert tr['common.bool.true'] == 'evet'
    assert tr['common.bool.false'] == 'hayır'


def test_sunum_sarmalayicisi_yerinde():
    """Kanal ADIYLA duruyor: sarmalayıcı sökülürse bu bekçi kırmızı verir."""
    kaynak = DICT_JS.read_text(encoding='utf-8')
    assert '__sunumSarmali' in kaynak, (
        'i18n_common.js sunum sarmalayıcısı sökülmüş — ikili ve sayı-dizisi '
        'parametreleri yeniden ham basılır')
    assert 'I18N.decimalText' in kaynak or 'decimalText' in kaynak, (
        'sayı yerelleştirmesi TEK KAYNAKtan (I18N.decimalText) okunmuyor')
