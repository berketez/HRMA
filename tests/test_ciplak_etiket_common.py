"""Ortak sözlük tüketicilerinde çıplak Isp / ısı-akısı etiketi kalmadı.

Bulgu defterindeki son çıplak-etiket borcunun kapanışı (v2.6.27, parti 20).
``test_sivi_form_alanlari.py`` üç ŞABLONU (advanced/solid/liquid.html) ve iki
SAYFA sözlüğünü kilitlemişti; ``i18n_common.js`` tüketicileri (app.js ve iki
güverte paneli) o iş kaleminde kapsam dışıydı ve orada üç etiket çıplak kaldı.
Bu dosya o üç tüketiciyi kilitler.

ÖLÇÜLEN TANIMLAR (bu dosyadaki her ad iddiası aşağıdaki koşumdan türedi):

1. ``motorData.isp`` — TASARIM NOKTASI Isp'si.
   ``hybrid_rocket_engine.py:1366``: ``Isp = CF * C_star / g0``; CF tasarım
   irtifasının ortam basıncında çözülür. Bit-birebir doğrulandı:
   ``cf*c_star/9.80665 == isp``. AYNI yanıt ``vacuum_isp``, ``sea_level_isp``
   ve ``maximum_isp`` da taşır.
   Koşum (/calculate, 1 kN / 20 bar / N2O-HTPB):
       isp = 230,35 s | vacuum_isp = 259,96 s  -> %12,9 fark
   Çıplak "Specific Impulse" bu dördünden hangisi olduğunu söylemiyordu.
   Aynı sayfanın yazdırma penceresi aynı alanı ZATEN tanımlı adla basıyordu
   (``adv.pop.isp`` = "Isp (design point, at design-altitude ambient)");
   yani aynı sayfada aynı sayı bir yerde künyeli, bir yerde çıplaktı.

2. ``gsa.throat_heat_flux`` / ``gsa.chamber_heat_flux`` — REFERANS SOĞUTULMUŞ
   CİDARDAKİ Bartz tasarım yükü (``heat_transfer_analysis.py``,
   ``throat_heat_flux = gas_side_flux(Tw_ref, h_gas)`` ve
   ``chamber_heat_flux = gas_side_flux(Tw_ref, h_chamber)``;
   ``Tw_ref = min(allowable, 0.8 * Taw)``).
   Koşum (/analyze_thermal_safety, 40 bar / 3000 K / çelik / doğal soğutma):
       throat_heat_flux = 24,12 MW/m², chamber_heat_flux = 2,40 MW/m²,
       reference_wall_temperature = 1073 K

3. ``p.q_MW`` (eksenel profil) — AYNI referans cidardaki tasarım yükü, ama
   istasyon başına yerel Bartz + yerel statik koşullarda ışıma
   (``heat_transfer_analysis.py``, ``q_flux[i] = gas_side_flux(Tw_ref)``).
   Koşum (/api/analysis/wall-profile, aynı motor, boğaz): 25,98 MW/m².
   KRİTİK: bu seri, sağ eksende DENGE cidar sıcaklığıyla birlikte çizilir.
   Aynı koşumda denge cidarındaki (T_wall_eq = 2976,8 K) akı 0,088 MW/m²
   ederdi — basılan sayının 1/294'ü. Çıplak "Heat flux q" adı okuyucuyu tam
   da bu yanlış eşleştirmeye davet ediyordu.

4. ``cooling.q_MW_m2`` ve ``sm.peak_heat_flux_MW_m2`` — KUPLE CİDAR DENGESİ
   akısı (``regen_cooling.py::_station_wall_balance``):
       q = (T_aw - T_soğutucu) / (1/h_g + t_c/k_c + 1/h_c)
   Sıcak cidar sıcaklığı burada SONUÇTUR, sabit bir referans değil.
   Koşum (/api/regen-cooling, panel varsayılanları, boğaz):
       q = 28,50 MW/m², T_wall_hot = 1263 K (izin verilen 1000 K'nin ÜSTÜNDE)

ASIL KUSUR (ölçümle bulundu, görev metninden farklı): ``panel.thermal.
heatFluxSeries`` anahtarı İKİ PANELDE birden kullanılıyordu — termal panelde
(2) sınıfı referans-cidar tasarım yükünü, rejeneratif panelde (4) sınıfı kuple
denge akısını adlandırıyordu. Yani tek anahtar iki AYRI tanım taşıyordu; bu
yüzden etiketi düzeltmek yetmez, anahtarın BÖLÜNMESİ gerekiyordu.
``test_iki_akinin_anahtari_ayrildi`` bu bölünmeyi kilitler.

SÖZLÜK AYAĞI: ``i18n_common.js`` bu iş kaleminde yazılamaz kapsamdaydı.
Yeni anahtarlar sözlüğe İŞLENENE KADAR ``test_yeni_anahtarin_sozluk_degeri_*``
testleri atlanır ve borcu adıyla söyler; anahtar sözlüğe girdiği anda değeri
denetlenmeye başlar (çıplak değer ya da satır içi yedekten sapma = kırmızı).
"""

import hashlib
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = REPO_ROOT / 'hrma' / 'static' / 'js'
APP_JS = JS / 'app.js'
THERMAL_JS = JS / 'panels' / 'thermal_panel.js'
COOLING_JS = JS / 'panels' / 'cooling_panel.js'
I18N_COMMON = JS / 'i18n_common.js'

TUKETICILER = (APP_JS, THERMAL_JS, COOLING_JS)


def read(path):
    return path.read_text(encoding='utf-8')


def mask_comments(text):
    """JS yorumlarını aynı uzunlukta boşlukla maskeler (ofsetler korunur).

    Satır içi '//' bilerek KESİLMEZ (URL ve string içi '//' güvenliği);
    yalnız tam-satır yorumlar maskelenir — test_sivi_form_alanlari.py ile
    aynı yaklaşım. Bu dosyadaki gerekçe yorumları ölçülen etiket metinlerini
    andıran ifadeler içerdiği için maskeleme ŞART.
    """
    out = list(text)
    for pat in (r'/\*[\s\S]*?\*/', r'(?m)^[ \t]*//[^\n]*$'):
        for m in re.finditer(pat, text):
            for i in range(m.start(), m.end()):
                if out[i] != '\n':
                    out[i] = ' '
    return ''.join(out)


# ---------------------------------------------------------------------------
# Çıplak (tanımsız) etiket kümeleri
# ---------------------------------------------------------------------------
# TEK TANIM KURALI: yasaklı biçimler parti 19 bekçisinden İTHAL edilir,
# kopyalanmaz. Aynı kavramın iki dosyada iki listeye ayrılması, birine
# eklenen biçimin diğerinde sessizce serbest kalması demektir.
from tests.test_sivi_form_alanlari import (          # noqa: E402
    CIPLAK_ISP,
    CIPLAK_AKI as CIPLAK_AKI_SABLON,
)

#: Şablon kümesinin ÜST KÜMESİ: bu tüketicilerde ölçülen çıplak biçimler
#: 'Heat Flux' değil, kart/seri adlarının kendisiydi (q_throat, Heat flux q,
#: PEAK HEAT FLUX). Şablon kümesi olduğu gibi içerilir.
CIPLAK_AKI = CIPLAK_AKI_SABLON | {
    'Heat flux q', 'Heat Flux q', 'PEAK HEAT FLUX', 'Peak heat flux',
    'q_throat', 'q_chamber', 'q throat', 'q chamber'}

#: BİLİNÇLİ İSTİSNA — gerekçesiz genişletmek bu bekçiyi anlamsızlaştırır.
#: 'Heat flux (MW/m²)' bir EKSEN başlığıdır: büyüklük + birim söyler, cidar
#: referansı söylemez ve söyleyemez (tek eksen birden çok seriyi taşıyabilir);
#: referans beyanı SERİ adındadır. Ayrıca test_faz6_panel.py::
#: test_t65_temperature_chart_axes_are_still_labelled_where_needed bu eksenin
#: 'common.axis.heatFlux' anahtarıyla YERİNDE KALMASINI şart koşar.
#: İstisnanın kendisi aşağıda test_ciplak_istisna_hala_gecerli ile kilitli.
EKSEN_ISTISNASI = ('common.axis.heatFlux', 'Heat flux (MW/m²)')


def _ciplak_etiketler(text, yasakli):
    """Maskelemeden SONRA kalan, yasaklı kümeye birebir eşit metinler.

    İki biçim taranır: tırnaklı string literalleri (T() yedekleri, dizi
    elemanları, Plotly seri adları) ve HTML düğüm metinleri (>Isp< biçimi).
    """
    bulgular = []
    for m in re.finditer(r"'([^'\\\n]*)'|\"([^\"\\\n]*)\"", text):
        deger = m.group(1) if m.group(1) is not None else m.group(2)
        if deger in yasakli:
            satir = text.count('\n', 0, m.start()) + 1
            bulgular.append('%d: %r' % (satir, deger))
    for m in re.finditer(r'>\s*([^<>]+?)\s*<', text):
        if m.group(1) in yasakli:
            satir = text.count('\n', 0, m.start()) + 1
            bulgular.append('%d: >%s<' % (satir, m.group(1)))
    return bulgular


# ---------------------------------------------------------------------------
# 1. Tarama: çıplak etiket geri gelmedi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('path', TUKETICILER, ids=lambda p: p.name)
def test_ciplak_isp_etiketi_kalmadi(path):
    """Aynı yanıttaki dört Isp (tasarım/vakum/deniz seviyesi/azami) ayırt
    edilebilir olmalı: 'Isp' hangi Isp olduğunu söylemeden basılmaz."""
    bulgu = _ciplak_etiketler(mask_comments(read(path)), CIPLAK_ISP)
    assert not bulgu, (
        '%s içinde çıplak Isp etiketi var (tanımlı ek kullanın, ör. '
        '"Isp (design point, at design-altitude ambient)", "Vacuum Isp"): '
        '\n  %s' % (path.name, '\n  '.join(bulgu)))


@pytest.mark.parametrize('path', TUKETICILER, ids=lambda p: p.name)
def test_ciplak_isi_akisi_etiketi_kalmadi(path):
    """Referans-cidar tasarım yükü ile kuple denge akısı (ölçülen: 294 kata
    varan fark) çıplak bir 'ısı akısı' adını paylaşamaz."""
    bulgu = _ciplak_etiketler(mask_comments(read(path)), CIPLAK_AKI)
    assert not bulgu, (
        '%s içinde çıplak ısı akısı etiketi var (cidar referansını yazın, '
        'ör. "(reference cooled wall)" / "(coupled wall balance)"):\n  %s'
        % (path.name, '\n  '.join(bulgu)))


def test_yasakli_kume_sablon_bekcisiyle_ortak_tanimda():
    """Parti 19 kümesi bu bekçide OLDUĞU GİBİ geçerli (kopya sürüklenmesi yok).

    Şablon bekçisine yeni bir çıplak biçim eklendiğinde burada da geçerli
    olmalı; iki liste ayrışırsa bir yüzey sessizce korumasız kalır.
    """
    assert CIPLAK_AKI_SABLON <= CIPLAK_AKI
    assert 'Heat Flux' in CIPLAK_AKI and 'Specific Impulse' in CIPLAK_ISP


def test_ciplak_etiket_tarayicisi_calisiyor():
    """Negatif kontrol: tarayıcı bilinen çıplak biçimleri gerçekten yakalar."""
    ornek = ("row(T('x.y', 'Specific Impulse'), v)\n"
             "name: T('a.b', 'Heat flux q')\n"
             "<div>PEAK HEAT FLUX</div>")
    assert _ciplak_etiketler(ornek, CIPLAK_ISP) == ["1: 'Specific Impulse'"]
    assert _ciplak_etiketler(ornek, CIPLAK_AKI) == [
        "2: 'Heat flux q'", '3: >PEAK HEAT FLUX<']
    # Tanımlı ekler yakalanmaz (yanlış pozitif üretmez):
    temiz = ("T('x', 'Isp (design point, at design-altitude ambient)')\n"
             "T('y', 'Heat flux q (reference cooled wall)')\n"
             "T('z', 'PEAK HEAT FLUX (coupled wall balance)')")
    assert _ciplak_etiketler(temiz, CIPLAK_ISP) == []
    assert _ciplak_etiketler(temiz, CIPLAK_AKI) == []


def test_ciplak_etiket_tarayicisi_yorumu_maskeliyor():
    """Gerekçe yorumundaki çıplak metin bulgu SAYILMAZ, koddaki sayılır."""
    kod = ("// eski ad 'Heat flux q' idi\nname: T('a.b', 'Heat flux q'),")
    assert _ciplak_etiketler(mask_comments(kod), CIPLAK_AKI) == [
        "2: 'Heat flux q'"]


def test_ciplak_istisna_hala_gecerli():
    """Eksen istisnası dar ve CANLI kalmalı (ölü istisna = sessiz boşluk)."""
    anahtar, metin = EKSEN_ISTISNASI
    for path in (THERMAL_JS, COOLING_JS):
        src = mask_comments(read(path))
        assert ("T('%s', '%s')" % (anahtar, metin)) in src, (
            '%s: eksen istisnası artık bu biçimde yok — istisna ya '
            'güncellenmeli ya kaldırılmalı' % path.name)
    assert metin not in (CIPLAK_ISP | CIPLAK_AKI), (
        'istisna metni yasaklı kümeye girmiş: iki kural çelişiyor')


# ---------------------------------------------------------------------------
# 2. Yapısal: tüketiciler TANIMLI anahtara bağlı
# ---------------------------------------------------------------------------
#: (dosya, yeni anahtar, satır içi yedekte bulunması gereken tanım eki)
TANIMLI_BAGLAMALAR = [
    (APP_JS, 'app.metric.ispDesign', 'design point'),
    (APP_JS, 'app.rep.ispDesignLong', 'design point'),
    (THERMAL_JS, 'panel.thermal.heatFluxSeriesRefWall', 'reference cooled wall'),
    (THERMAL_JS, 'panel.thermal.cardQThroatRefWall', 'reference cooled wall'),
    (THERMAL_JS, 'panel.thermal.cardQChamberRefWall', 'reference cooled wall'),
    (COOLING_JS, 'panel.regen.heatFluxSeriesBalance', 'coupled wall balance'),
    (COOLING_JS, 'panel.regen.cardPeakFluxBalance', 'coupled wall balance'),
    # Balon ipuçları: kısa kart adının taşıyamadığı TAM tanım burada durur,
    # o yüzden onlar da denetlenir (tanım ipucunda bozulursa kart yine
    # tanımsız kalır).
    (THERMAL_JS, 'panel.thermal.cardQThroatTip', 'reference cooled wall'),
    (COOLING_JS, 'panel.regen.cardPeakFluxTip', 'coupled'),
]

#: Çıplak değer taşıyan eski anahtarlar bu tüketicilerde ARTIK ÇAĞRILMAZ.
#: (Sözlükten silinmeleri i18n_common.js partisinin işidir; burada yalnız
#: tüketici tarafı kilitlenir.)
ESKI_ANAHTARLAR = [
    (APP_JS, 'app.metric.isp'),
    (APP_JS, 'app.rep.ispLong'),
    (THERMAL_JS, 'panel.thermal.heatFluxSeries'),
    (THERMAL_JS, 'panel.thermal.cardQThroat'),
    (THERMAL_JS, 'panel.thermal.cardQChamber'),
    (COOLING_JS, 'panel.thermal.heatFluxSeries'),
    (COOLING_JS, 'panel.regen.cardPeakFlux'),
]


def _yedek(src, anahtar):
    """``T('anahtar', 'yedek' [+ ' devam'...])`` çağrısındaki tam EN yedeği.

    Yedek satır sonuna sığmadığında string birleştirmeyle yazılır; parçalar
    burada birleştirilir, yoksa tanım eki aranırken yarısı kaybolur.
    """
    m = re.search(r"T\(\s*'%s'\s*,\s*((?:'[^'\\\n]*'\s*\+?\s*)+)\)"
                  % re.escape(anahtar), src)
    if not m:
        return None
    return ''.join(re.findall(r"'([^'\\\n]*)'", m.group(1)))


@pytest.mark.parametrize('path,anahtar,parca', TANIMLI_BAGLAMALAR,
                         ids=lambda v: v if isinstance(v, str) else v.name)
def test_tuketici_tanimli_anahtari_cagiriyor(path, anahtar, parca):
    """Yeni anahtar çağrılıyor VE satır içi EN yedeği tanım ekini taşıyor.

    Yedek, sözlük yüklenmediğinde ekrana basılan metindir; onun çıplak
    kalması sözlüğü düzeltmeyi anlamsız kılar.
    """
    src = mask_comments(read(path))
    yedek = _yedek(src, anahtar)
    assert yedek is not None, (
        '%s içinde %s anahtarı T() ile çağrılmıyor' % (path.name, anahtar))
    assert parca in yedek, (
        '%s: %s yedeği (%r) beklenen tanım ekini (%r) taşımıyor'
        % (path.name, anahtar, yedek, parca))
    assert yedek not in (CIPLAK_ISP | CIPLAK_AKI), (
        '%s: %s yedeği hâlâ çıplak' % (path.name, anahtar))


@pytest.mark.parametrize('path,anahtar', ESKI_ANAHTARLAR,
                         ids=lambda v: v if isinstance(v, str) else v.name)
def test_eski_ciplak_anahtar_tuketicide_kalmadi(path, anahtar):
    """Çıplak değerli eski anahtar geri çağrılırsa etiket yine çıplak olur.

    Eşleşme tırnaklı TAM biçimde aranır; 'app.metric.isp' yeni
    'app.metric.ispDesign' anahtarının ön ekidir, alt dize araması bu testi
    kalıcı kırmızı yapardı.
    """
    src = mask_comments(read(path))
    assert ("'%s'" % anahtar) not in src, (
        '%s: çıplak değerli eski anahtar %s hâlâ çağrılıyor'
        % (path.name, anahtar))


def test_iki_akinin_anahtari_ayrildi():
    """ASIL KUSUR: tek anahtar iki AYRI tanım taşıyordu.

    Termal paneldeki q(x) referans-cidar tasarım yükü, rejeneratif paneldeki
    q(x) kuple denge akısıdır (ölçüldü: 25,98 MW/m² ile 28,50 MW/m², farklı
    cidar referansları). İki panelin akı ETİKET anahtarları kesişemez.
    """
    termal = mask_comments(read(THERMAL_JS))
    regen = mask_comments(read(COOLING_JS))
    aki_re = re.compile(r"T\(\s*'((?:panel|common)\.[\w.]*"
                        r"(?:[Hh]eatFlux|QThroat|QChamber|PeakFlux)[\w.]*)'")
    t_keys = set(aki_re.findall(termal))
    r_keys = set(aki_re.findall(regen))
    assert t_keys, 'termal panelde akı etiketi bulunamadı (tarayıcı bozuk)'
    assert r_keys, 'rejeneratif panelde akı etiketi bulunamadı (tarayıcı bozuk)'
    ortak = t_keys & r_keys
    eksen = {EKSEN_ISTISNASI[0]}
    assert ortak <= eksen, (
        'İki panel aynı akı anahtarını paylaşıyor ama tanımları farklı '
        '(referans-cidar tasarım yükü / kuple denge akısı): %s'
        % sorted(ortak - eksen))


# ---------------------------------------------------------------------------
# 3. Sözlük ayağı: anahtar işlendiği ANDA denetlenir (o zamana dek atlanır)
# ---------------------------------------------------------------------------
def _sozluk_bloklari():
    """i18n_common.js EN ve TR bloklarının kaba (anahtar -> değer) sözlükleri.

    Blok ayrımı için 'tr:' işaretçisi kullanılır; ondan önceki eşleşmeler EN,
    sonrakiler TR sayılır (i18n_common.js düzeni: önce en, sonra tr).
    """
    src = read(I18N_COMMON)
    m = re.search(r"^\s*tr\s*:\s*\{", src, re.M)
    sinir = m.start() if m else len(src)
    en, tr = {}, {}
    for match in re.finditer(r"'([\w.]+)':\s*'((?:[^'\\]|\\.)*)'", src):
        hedef = en if match.start() < sinir else tr
        hedef.setdefault(match.group(1), match.group(2))
    return en, tr


@pytest.mark.parametrize('path,anahtar,parca', TANIMLI_BAGLAMALAR,
                         ids=lambda v: v if isinstance(v, str) else v.name)
def test_yeni_anahtarin_sozluk_degeri_tanimli(path, anahtar, parca):
    """Sözlüğe işlenen değer, satır içi yedekle AYNI tanımı taşımalı.

    Anahtar henüz sözlükte yoksa test ATLANIR ve borcu adıyla söyler —
    i18n_common.js bu iş kaleminde yazılamaz kapsamdaydı.
    """
    en, tr = _sozluk_bloklari()
    if anahtar not in en:
        pytest.skip('i18n_common.js sözlük borcu: %s henüz işlenmedi' % anahtar)
    assert en[anahtar] == _yedek(mask_comments(read(path)), anahtar), (
        '%s: sözlük değeri satır içi yedekten farklı — dile göre farklı '
        'tanım basılır' % anahtar)
    assert parca in en[anahtar], (
        '%s sözlük değeri (%r) tanım ekini (%r) taşımıyor'
        % (anahtar, en[anahtar], parca))
    assert en[anahtar] not in (CIPLAK_ISP | CIPLAK_AKI), (
        '%s sözlük değeri hâlâ çıplak' % anahtar)
    assert anahtar in tr, '%s TR karşılığı yok' % anahtar
    assert tr[anahtar] not in (CIPLAK_ISP | CIPLAK_AKI), (
        '%s TR değeri hâlâ çıplak' % anahtar)


def test_sozluk_tarayicisi_gercekten_deger_goruyor():
    """Negatif kontrol: sözlük okuyucu bilinen bir kalemi gerçekten görüyor.

    (Aksi hâlde yukarıdaki testler sonsuza dek 'atlandı' der ve borç sessizce
    kapanmış görünür.)
    """
    en, tr = _sozluk_bloklari()
    assert en.get('app.metric.thrust') == 'Thrust', en.get('app.metric.thrust')
    assert tr.get('app.metric.thrust'), 'TR bloğu okunamadı'
    assert tr.get('app.metric.thrust') != en.get('app.metric.thrust')


def test_dosya_bekcisi_kendi_kaynagini_goruyor():
    """Bekçinin okuduğu üç dosya gerçekten var ve boş değil (yol kayması)."""
    for path in TUKETICILER + (I18N_COMMON,):
        data = path.read_bytes()
        assert len(data) > 1000, path
        # md5 yalnız teşhis içindir; sabitlenmez (dosyalar canlı).
        assert hashlib.md5(data).hexdigest()
