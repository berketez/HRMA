# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · kulvar `sablonlar` · aşama 2 — onarım bekçileri.

Her test TEK bir kusuru görür ve o kusur geri konduğunda KIRMIZI olur
(ters-mutasyon kanıtı: `docs/scofield/raw/OH/D15/sablonlar/a2/mutasyon.json`).
Ölçümler: aynı dizindeki `once.json` (a1 kapanışının şablonları) ve
`sonra.json` (bu aşamanın şablonları).

Saf JS yardımcıları node ile GERÇEKTEN koşturulur — metin sınamak yetmez
(`test_i18n_pages` deseninin aynısı). node yoksa o testler atlanır.

Engelli kalemler (P12bB2-03, P12bB2-06: ÖK-21 form katmanı; P12bB2-09:
`hrma/analysis/trajectory_analysis.py` skaler itki sözleşmesi) için KUSURU
GÖREN bekçi bilerek yazılmadı — bunun yerine söküm sırası geldiğinde
arkasında duracak SAĞLAM taraf korunuyor (uç kapısı, çözücünün yayımladığı
eğri). Kusuru kilitleyen bekçi yazmak ÖK-05'in tersidir.
"""

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLONLAR = KOK / 'hrma' / 'templates'
SOLID = SABLONLAR / 'solid.html'
ADVANCED = SABLONLAR / 'advanced.html'
MOTOR_YANMA = KOK / 'hrma' / 'engines' / 'combustion_analysis.py'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D15' / 'sablonlar' / 'a2'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason=('node yürütülebiliri bulunamadı; şablonun saf JS yardımcıları '
            'GERÇEKTEN koşturulamıyor. Kurulum sorusu: bu ortamda node '
            'kurulu mu? (CI node garantisi P13B1-04/A3 kalemidir.)'))


@pytest.fixture(scope='module')
def solid_src():
    return SOLID.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def advanced_src():
    return ADVANCED.read_text(encoding='utf-8')


def _fonksiyon_kaynagi(src, ad):
    """`function ad(` ile başlayan bloğu süslü parantez eşleyerek çıkarır."""
    m = re.search(r'\n(\s*)(?:async\s+)?function %s\s*\(' % re.escape(ad), src)
    assert m, '%s fonksiyonu şablonda bulunamadı' % ad
    i = src.index('{', m.end() - 1)
    derinlik = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            derinlik += 1
        elif src[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return src[m.start():j + 1]
    raise AssertionError('%s bloğu kapanmıyor' % ad)


def _node_kos(parcalar, govde):
    kod = '\n'.join(parcalar) + '\n' + govde
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as fh:
        fh.write(kod)
        yol = fh.name
    try:
        cp = subprocess.run([NODE, yol], capture_output=True, text=True,
                            timeout=90)
        assert cp.returncode == 0, cp.stderr
        return json.loads(cp.stdout)
    finally:
        pathlib.Path(yol).unlink(missing_ok=True)


def _fuel_select(src):
    m = re.search(r'<select id="fuel_type"[^>]*>(.*?)</select>', src, re.S)
    assert m, '#fuel_type seçicisi bulunamadı'
    return m.group(1)


# =========================================================== P12bB2-01
def test_b2_01_yedek_katalog_yanma_hizi_uydurmuyor(solid_src):
    """Yedek katalog satırı çözücünün çözeceği sayıyı ELİNDEN ALMAZ.

    Ölçüldü (once.json / sonra.json): yedeğin yazdığı a=0,005 n=0,35 çifti
    aynı APCP motorunun ortalama itkisini 2.975,3 N -> 6.663,6 N (2,2397 kat)
    çıkarıyor, yanma süresini 4,3997 s -> 1,9645 s indiriyordu. Merkezi
    katalog a = 0,0022552 diyor. Alan boş kalınca yük anahtarı düşer ve arka
    uç kaynağını beyan ederek katalogdan çözer.
    """
    m = re.search(r'var FALLBACK_PROPELLANTS = \[(.*?)\n        \];',
                  solid_src, re.S)
    assert m, 'FALLBACK_PROPELLANTS bulunamadı'
    blok = m.group(1)
    # Yedek listedeki HİÇBİR satır yanma hızı katsayısı yazmamalı.
    for alan in ('burn_rate_a', 'burn_rate_n'):
        degerler = re.findall(r'\b%s:\s*([^,\n]+)' % alan, blok)
        assert degerler, '%s yedek katalogda hiç geçmiyor (kalıp değişti mi?)' % alan
        for d in degerler:
            assert d.strip() == 'null', (
                'Yedek katalog %s için sayı uyduruyor: %r. Ölçülen bedel: '
                'ortalama itki 2,2397 kat.' % (alan, d.strip()))


def test_b2_01_yedek_katalogun_obur_sayilari_form_varsayilaninin_aynisi(
        solid_src):
    """ÖH D30 · P12bB2-24 — BEKÇİ ÇEVRİLDİ (kusuru koruyordu).

    ESKİ ÖLÇÜ: "yedek APCP kaydının beş sayısı sayfanın form varsayılanıyla
    BİREBİR AYNI olmalı" (density 1850, c_star 1550, flame 3200, M 28,5,
    gamma 1,25). İddia doğruydu ama YANLIŞ ŞEYİ kilitliyordu: beş sayının
    hepsi MERKEZÎ KATALOGTAN (hrma/data/propellants_db._APCP_REFERENCE:
    1810,0 / 1598,2 / 3614,8 / 28,0 / 1,1986) sapıyordu ve bu bekçi tam da o
    sapmayı yerinde tutuyordu — c*'ta %3,0, alev sıcaklığında %11,5. Kayıt
    kendini "Built-in fallback (catalogue endpoint unavailable)" diye
    künyeliyor; kullanıcı katalog ucu düştüğünde forma yazılan bu sayıları
    "kataloğun değeri" sanıyordu. Doktrin 4 (TEK KAYNAK) bir sayının iki
    yerde farklı yazılmasını yasaklar.

    YENİ ÖLÇÜ (sayı mandalı DEĞİL, ilişki): yedek kayıt merkezî katalogla
    ÇELİŞEN hiçbir sayı yayımlamaz. Sayı ya merkezle birebir aynıdır ya da
    hiç yazılmaz (null) — KNDX/KNSB satırlarının zaten izlediği yol. Form
    katmanının KENDİ varsayılanları bu bekçinin konusu değildir (ÖK-21).
    """
    from hrma.data.propellants_db import PROPELLANTS
    m = re.search(r"key: 'apcp'.*?(?=\n            \{)", solid_src, re.S)
    assert m, 'yedek apcp satırı bulunamadı'
    satir = m.group(0)

    merkez = PROPELLANTS['apcp']
    celisen = {}
    for alan in ('density', 'c_star', 'flame_temperature',
                 'molecular_weight', 'gamma'):
        mm = re.search(r'\b%s:\s*([-\d.eE+]+|null)' % alan, satir)
        assert mm, 'yedek %s alanı bulunamadı' % alan
        if mm.group(1) == 'null':
            continue
        yedek = float(mm.group(1))
        gercek = merkez[alan]
        if abs(yedek - gercek) > 1e-9:
            celisen[alan] = (yedek, gercek)
    assert not celisen, (
        'yedek kayıt merkezî katalogla çelişen sayı yayımlıyor '
        '(yedek, merkez): %r' % celisen)


# =========================================================== P12bB2-02
@node_gerekli
def test_b2_02_irtifa_verilmisse_ortam_basinci_yuke_konmaz(solid_src):
    """Ortam basıncı TEK kanaldan bildirilir; irtifa artık ölü değil.

    Ölçüldü: motor `test_altitude`'u ISA basıncına çevirip hemen ardından
    `atm_pressure` ile KOŞULSUZ eziyor (solid_rocket_engine.py:1598-1604).
    Sayfa ikisini birden gönderdiği sürece 10.000 m'de isp_sea_level
    201,91043286634925 s'de 17 anlamlı basamak sabit kalıyordu; doğrusu
    223,43600959522135 s (+%10,661), ortalama itki 2.975,28 -> 3.292,47 N.
    """
    parcalar = [_fonksiyon_kaynagi(solid_src, ad) for ad in
                ('solidAmbientAltitudeM', 'solidAmbientFields',
                 'syncAmbientPressureInterlock')]
    govde = """
function mkEl(v) { return { value: String(v), disabled: false }; }
function kos(alt) {
  const els = { test_altitude: mkEl(alt), atm_pressure: mkEl('101.325') };
  globalThis.document = { getElementById: (id) => els[id] || null };
  const alan = solidAmbientFields();
  syncAmbientPressureInterlock();
  return {
    anahtarlar: Object.keys(alan).sort(),
    test_altitude: alan.test_altitude,
    kilitli: els.atm_pressure.disabled
  };
}
console.log(JSON.stringify({
  yuksek: kos('10000'), deniz: kos('0'), bos: kos(''), negatif: kos('-5')
}));
"""
    r = _node_kos(parcalar, govde)

    # İrtifa bildirildiyse yalnız irtifa gider ve basınç alanı kilitlenir.
    assert r['yuksek']['anahtarlar'] == ['test_altitude'], r['yuksek']
    assert r['yuksek']['test_altitude'] == 10000
    assert r['yuksek']['kilitli'] is True, (
        'irtifa sürerken basınç alanı kilitlenmiyor — kullanıcı hangi kanalın '
        'hüküm verdiğini göremez')

    # İrtifa yoksa basınç alanı sürer; kilit açıktır.
    # ÖH D15 fix-4 (ana model, 1 Eyl 2026): deniz-seviyesi dalı artık
    # `test_altitude: 0` GÖNDERMİYOR — app-api P7B2-15 kapısı (7ec4f9e) 0'ı
    # açık kanal sayıp ölçülmüş ortam basıncını 422 ile reddediyordu (Fable
    # şablonlar denetimi). Tek beyan kuralı: yükte yalnız süren kanalın
    # anahtarı bulunur.
    for ad in ('deniz', 'bos', 'negatif'):
        assert r[ad]['anahtarlar'] == ['atm_pressure'], (ad, r[ad])
        assert 'test_altitude' not in r[ad] or r[ad]['test_altitude'] is None, (
            ad, r[ad])
        assert r[ad]['kilitli'] is False, ad


def test_b2_02_toplayici_atm_pressure_i_kosulsuz_gondermiyor(solid_src):
    """Toplayıcıda `atm_pressure: ... || 101.325` kalıbı kalmamalı."""
    capa = _fonksiyon_kaynagi(solid_src, 'collectAllParameters')
    assert not re.search(
        r"atm_pressure:\s*parseFloat\(document\.getElementById"
        r"\('atm_pressure'\)\.value\)\s*\|\|", capa), (
        'ortam basıncı yine koşulsuz gönderiliyor; test_altitude ölü demektir')
    assert 'solidAmbientFields()' in capa, (
        'ortam basıncı tek-kanal yardımcısından gelmiyor')


# =========================================================== P12bB2-07
def test_b2_07_kap_hukmu_ve_kunyesi_ekrana_basiliyor(solid_src):
    """Çözücünün kap hükmü ve gerekçesi Safety sekmesine ULAŞIR.

    Ölçüldü: uç `pressure_safety` altında 29 alan yayımlıyor, sekme 4'ünü
    basıyordu; `vessel_status` şablonun tamamında 0 kez geçiyordu. Düşenler
    arasında gerçek bir uyarı vardı ("t/r = 0.151 > 0.1 — thin-wall
    assumptions degrade...") ve o uyarı `results.warnings` listesinde de yok,
    yani uyarı panelinde de görünmüyordu.
    """
    hukum = _fonksiyon_kaynagi(solid_src, 'vesselVerdictHTML')
    for alan in ('vessel_status', 'vessel_status_basis',
                 'vessel_status_is_tautological', 'vessel_warnings'):
        assert 'ps.%s' % alan in hukum, '%s hüküm bloğunda okunmuyor' % alan

    guvenlik = _fonksiyon_kaynagi(solid_src, 'generateSafetyAnalysisHTML')
    assert 'vesselVerdictHTML(pressureSafety)' in guvenlik, (
        'hüküm bloğu Safety sekmesine bağlanmamış')
    assert "'wall_thickness_source'" in guvenlik, (
        'cidar kalınlığının kaynağı basılmıyor')


@node_gerekli
def test_b2_07_kazanilmamis_onay_yesil_basilmaz(solid_src):
    """Hüküm bloğu renk vermiyor, HÜKMÜ aktarıyor: taut. PASS yeşil olamaz."""
    # T-ÇAPA-C2 (27 Eki): V301/DİL-2 (f36795100) hüküm bloğuna sunucu cümlesi
    # çeviri kanalı ekledi (``window.I18N.serverText``; tanınmazsa AYNEN). Sayfa
    # ikizi tarayıcıda her zaman var olan ``window`` nesnesini tanımlamıyordu;
    # boş bir pencere verilir — I18N yoksa cümle aynen basılır (ürünün yolu).
    parcalar = [
        "const T = (k, d) => d;",
        "const window = {};",
        _fonksiyon_kaynagi(solid_src, 'vesselVerdictHTML'),
    ]
    govde = """
const canli = {
  vessel_status: 'PASS', vessel_status_is_tautological: false,
  vessel_status_basis: 'The case wall thickness was supplied by the user',
  vessel_warnings: ['t/r = 0.151 > 0.1 - thin-wall assumptions degrade'],
  wall_thickness_source: 'user_supplied'
};
const taut = Object.assign({}, canli, { vessel_status_is_tautological: true });
const degerlendirilmedi = Object.assign({}, canli, {
  vessel_status: 'NOT_EVALUATED', vessel_status_is_tautological: true });
const bos = {};
const yesil = '#1b7f4b';
console.log(JSON.stringify({
  canli_yesil: vesselVerdictHTML(canli).includes(yesil),
  taut_yesil: vesselVerdictHTML(taut).includes(yesil),
  degerlendirilmedi_yesil: vesselVerdictHTML(degerlendirilmedi).includes(yesil),
  uyari_basildi: vesselVerdictHTML(canli).includes('thin-wall assumptions degrade'),
  gerekce_basildi: vesselVerdictHTML(canli).includes('supplied by the user'),
  taut_isareti: vesselVerdictHTML(taut).includes('vessel_status_is_tautological'),
  bos_govde: vesselVerdictHTML(bos),
  yoksa: vesselVerdictHTML(null)
}));
"""
    r = _node_kos(parcalar, govde)
    assert r['canli_yesil'] is True, 'kazanılmış PASS yeşil basılmıyor'
    assert r['taut_yesil'] is False, (
        'totolojik PASS yeşil basılıyor — kazanılmamış onay yeşil olamaz')
    assert r['degerlendirilmedi_yesil'] is False
    assert r['uyari_basildi'] is True, 'kabın kendi uyarısı yine yutuluyor'
    assert r['gerekce_basildi'] is True, 'hükmün gerekçesi basılmıyor'
    assert r['taut_isareti'] is True
    # Veri yoksa hüküm ÜRETİLMEZ (uydurma yeşil rozet yok).
    assert r['bos_govde'] == ''
    assert r['yoksa'] == ''


# =========================================================== P12bB2-10
def test_b2_10_pdf_yuku_formu_degil_cozucuyu_belgeler(solid_src):
    """Rapor geometrisi `motor_geometry`den gelir; grain ölçüsünden değil.

    Ölçüldü: PDF yükü `chamber_diameter`'ı `#outer_diameter`'dan (100,0 mm)
    ve `chamber_length`'i `#grain_length`'ten (500,0 mm) okuyordu; çözücü
    106,0 mm / 604,0 mm diyor (fark 6,0 ve 104,0 mm). Aynı sayfanın Motor
    Design tablosu, Excel çıktısı ve CAD sekmesi çözücüyü okuyor — PDF
    dördüncü tüketici olarak atlanmıştı.
    """
    pdf = _fonksiyon_kaynagi(solid_src, 'exportPDF')
    for olcu, form_alani in (('chamber_diameter', 'outer_diameter'),
                             ('chamber_length', 'grain_length')):
        assert not re.search(
            r"%s:\s*parseFloat\(document\.getElementById\('%s'\)"
            % (olcu, form_alani), pdf), (
            'PDF yükü %s için yine form alanı #%s okuyor' % (olcu, form_alani))
    assert '_mm(_geo.chamber_diameter)' in pdf
    assert '_mm(_geo.chamber_length)' in pdf
    assert "_r.propellant_name" in pdf, (
        'yakıt kimliği yine form alanından/sabit yedekten okunuyor')
    assert "|| 'APCP'" not in pdf, 'uydurma APCP yedeği geri gelmiş'


@node_gerekli
def test_b2_10_eksik_geometride_anahtar_yuke_konmaz(solid_src):
    """FAIL-CLOSED: çözücü ölçüyü yayımlamadıysa rapor sayı uydurmaz."""
    pdf = _fonksiyon_kaynagi(solid_src, 'exportPDF')
    i = pdf.index('const _r = window.currentResults')
    j = pdf.index('Object.keys(_pdfAlanlar)')
    k = pdf.index('});', j) + 3
    parca = pdf[i:k]
    govde = """
function kos(sonuc) {
  globalThis.window = { currentResults: sonuc };
  globalThis.document = { getElementById: () => ({ value: 'bates' }) };
  const motorName = 'X';
  %s
  return motorData;
}
const tam = kos({
  motor_geometry: { chamber_diameter: 0.106, chamber_length: 0.604 },
  propellant_name: 'APCP', throat_diameter: 27.98280727986316,
  exit_diameter: 65.3799501773285, density: 1850.0,
  propellant_mass: 6.6110890403980225, expansion_ratio: 5.458918464802987
});
const bos = kos(null);
console.log(JSON.stringify({
  tam_cap_mm: tam.chamber_diameter, tam_boy_mm: tam.chamber_length,
  tam_bogaz: tam.throat_diameter, tam_yakit: tam.propellant_type,
  bos_anahtarlar: Object.keys(bos).sort()
}));
""" % parca.replace('const motorData', 'let motorData')
    r = _node_kos([], govde)
    # motor_geometry METRE yayımlıyor, PDF üreteci mm bekliyor.
    assert abs(r['tam_cap_mm'] - 106.0) < 1e-9, r['tam_cap_mm']
    assert abs(r['tam_boy_mm'] - 604.0) < 1e-9, r['tam_boy_mm']
    assert abs(r['tam_bogaz'] - 27.98280727986316) < 1e-12
    assert r['tam_yakit'] == 'APCP'
    # Hesap yokken hiçbir geometri anahtarı gitmez (uydurma yedek yok).
    assert r['bos_anahtarlar'] == ['grain_type', 'motor_name', 'motor_type'], (
        r['bos_anahtarlar'])


# =========================================================== P12bB3-02
def test_b3_02_sunulan_her_yakit_cozucunun_onurlandirdigi_yakittir(
        advanced_src):
    """Seçici, motorun desteklediği yakıt kümesiyle ÇAPRAZLANIR (tek kaynak).

    Ölçüldü: 11 seçeneğin 4'ü (`carbon`, `al2o3`, `mixture`, `custom`)
    /calculate'te HTTP 400 veriyordu; ikisinin sayfada tam donanımlı alt
    paneli vardı ve o panelin tek çıktısı hataydı. Desteklenen liste
    motorun KENDİ kaynağından okunur: uç yeni yakıt kazanır ya da
    kaybederse bu test kırmızı olur ve seçici güncellenmeye zorlanır.
    """
    # ÖH D21 / P12bB3-02 — ÇEVRİLEN BEKÇİ. Eski gövde desteklenen listeyi
    # motorun İNGİLİZCE HATA CÜMLESİNDEN regex ile söküyordu; yani sözleşme
    # bir insan metnine asılıydı ve o metin listenin İKİNCİ kopyasıydı
    # (fonksiyon içi FUEL_KEYS demeti birinci). Bekçi bu ikiliği yerinde
    # tutuyordu: kopyayı kaldıran her onarım testi kırıyordu. Liste artık
    # tek kaynaktan (SUPPORTED_HYBRID_FUEL_KEYS) OKUNUR; iddia aynı kaldı.
    from hrma.engines.combustion_analysis import SUPPORTED_HYBRID_FUEL_KEYS

    destekli = set(SUPPORTED_HYBRID_FUEL_KEYS)
    assert destekli == {'htpb', 'paraffin', 'pe', 'pmma', 'abs', 'pla',
                        'aluminum'}, destekli
    # Tek kaynak GERÇEKTEN tek olmalı: liste ikinci kez elle yazılmasın.
    motor = MOTOR_YANMA.read_text(encoding='utf-8')
    assert 'htpb, paraffin, pe, pmma, abs, pla, aluminum' not in motor, (
        'desteklenen yakıt listesi motor kaynağında ikinci kez elle yazılı')

    govde = _fuel_select(advanced_src)
    secenekler = re.findall(r'<option value="([^"]+)"([^>]*)>', govde)
    # ÖH D32 / OH-D31-05 — ÇEVRİLEN BEKÇİ (KUSURU KORUYAN MANDAL).
    # Eski gövde iki SAYIM MANDALI taşıyordu: `len(secenekler) == 11` ve
    # `kapali == {'carbon', 'al2o3', 'mixture', 'custom'}`. Bu ikisi
    # birlikte, ÖLÜ bir seçeneğin seçicide DURMASINI şart koşuyordu —
    # yani kalemi onaran her değişikliği kırmızıya düşürüyordu.
    # Berke karar dosyası §7 (a): `al2o3` yakıt DEĞİLDİR (alüminyum zaten
    # tam oksitlenmiştir; uç `not_a_fuel` ile reddediyor), bu bir veri
    # eksikliği değil KATEGORİ hatasıdır ve seçenek kilitlenmek yerine
    # KALDIRILDI (11 -> 10 seçenek).
    # İDDİA ZAYIFLATILMADI: asıl kural "sunulan her yakıt çözücünün
    # onurlandırdığı yakıttır" aynen duruyor ve artık ÇİFT YÖNLÜ
    # (`sunulan == destekli`) ölçülüyor; sayım mandalı yerine KÜME ölçüsü
    # geçti. Kapalı küme de ada bağlı kaldı: `carbon` hakemli korelasyon,
    # `mixture`/`custom` istek şeması bekliyor.
    assert len(secenekler) == 10, len(secenekler)
    sunulan = {v for v, rest in secenekler if not re.search(r'\bdisabled\b', rest)}
    kapali = {v for v, rest in secenekler if re.search(r'\bdisabled\b', rest)}

    assert sunulan == destekli, (
        'seçici ile çözücü ayrıştı; yalnız seçicide: %s, yalnız çözücüde: %s'
        % (sorted(sunulan - destekli), sorted(destekli - sunulan)))
    assert kapali == {'carbon', 'mixture', 'custom'}, sorted(kapali)
    assert 'al2o3' not in {v for v, _r in secenekler}, (
        'al2o3 seçiciye geri döndü (OH-D31-05)')
    # Karşı yön: desteklenen bir yakıt sebepsiz kapatılmış olmasın.
    assert not (kapali & destekli), sorted(kapali & destekli)


# =========================================================== P12bB3-03
@node_gerekli
def test_b3_03_irtifa_basinc_ceviricisi_gercekten_ussa_1976(advanced_src):
    """Rozet "US Standard Atmosphere 1976" diyorsa sayı da o olmalı.

    Ölçüldü: eski gövde 11 km üstünü tek izotermal katmanla yaklaşıyordu;
    #single_altitude bandının SINIRINDA (50.000 m) sapma -%36,41 idi
    (0,000483 bar ⟷ USSA 0,000759 bar). Bu test şablonun çeviricisini node
    ile koşturup deponun kendi `hrma.constants.isa_pressure` uygulamasıyla
    karşılaştırır — iki taraf ayrışırsa kırmızı olur (TEK KAYNAK).
    """
    from hrma.constants import isa_pressure

    m = re.search(r'var ISA_LAYERS_JS = \[.*?var ISA_TABLE_TOP_M_JS = [0-9.]+;',
                  advanced_src, re.S)
    assert m, 'şablonda ISA katman tablosu yok'
    parcalar = [m.group(0),
                _fonksiyon_kaynagi(advanced_src, '_isaLayerJS'),
                _fonksiyon_kaynagi(advanced_src, '_isaPressurePaJS'),
                _fonksiyon_kaynagi(advanced_src, 'altitudeToPressure')]
    govde = """
const hs = [];
for (let h = 0; h <= 90000; h += 250) hs.push(h);
[0, 11000, 20000, 25000, 32000, 40000, 47000, 50000, 51000, 71000, 84852]
  .forEach(h => { if (!hs.includes(h)) hs.push(h); });
hs.sort((a, b) => a - b);
console.log(JSON.stringify({
  noktalar: hs.map(h => [h, altitudeToPressure(h)]),
  bos: altitudeToPressure(''),
  negatif: altitudeToPressure(-100)
}));
"""
    r = _node_kos(parcalar, govde)

    en_kotu = 0.0
    en_kotu_h = None
    for h, p in r['noktalar']:
        ref = isa_pressure(h) / 1e5          # Pa -> bar
        bagil = abs(p / ref - 1.0)
        if bagil > en_kotu:
            en_kotu, en_kotu_h = bagil, h
    assert en_kotu < 1e-12, (
        'şablonun çeviricisi deponun USSA 1976 uygulamasından sapıyor: '
        'h=%s m, bağıl fark %.3e' % (en_kotu_h, en_kotu))

    # Kampanyanın ölçtüğü nokta ayrıca sayıyla kilitlenir.
    p50 = dict(r['noktalar'])[50000]
    assert abs(p50 - isa_pressure(50000) / 1e5) < 1e-15
    assert p50 > 7.0e-4, (
        'eski basitleştirilmiş stratosfer geri gelmiş (50 km 4,83e-4 bar '
        'veriyordu, doğrusu 7,59e-4 bar)')

    # Sayı çözülemiyorsa uydurulmaz.
    assert r['bos'] is None or r['bos'] != r['bos'], r['bos']   # NaN
    assert abs(r['negatif'] - isa_pressure(0) / 1e5) < 1e-15


def test_b3_03_katman_tablosu_deponun_tablosuyla_ayni(advanced_src):
    """Katman tablosunun her sayısı `hrma.constants` ile birebir aynıdır."""
    from hrma.constants import (G_0, ISA_LAYERS, ISA_TABLE_TOP_M, M_AIR,
                                R_STAR_ICAO)

    m = re.search(r'var ISA_LAYERS_JS = \[(.*?)\];', advanced_src, re.S)
    assert m, 'ISA katman tablosu bulunamadı'
    satirlar = re.findall(r'\[\s*(-?[0-9.eE+-]+),\s*(-?[0-9.eE+-]+),\s*'
                          r'(-?[0-9.eE+-]+),\s*(-?[0-9.eE+-]+)\s*\]',
                          m.group(1))
    assert len(satirlar) == len(ISA_LAYERS), (len(satirlar), len(ISA_LAYERS))
    for js, py in zip(satirlar, ISA_LAYERS):
        assert tuple(float(x) for x in js) == tuple(float(x) for x in py), (
            js, py)

    for ad, beklenen in (('ISA_G0_JS', G_0), ('ISA_M_AIR_JS', M_AIR),
                         ('ISA_R_STAR_JS', R_STAR_ICAO),
                         ('ISA_TABLE_TOP_M_JS', ISA_TABLE_TOP_M)):
        mm = re.search(r'var %s = ([0-9.eE+-]+);' % ad, advanced_src)
        assert mm, '%s bulunamadı' % ad
        assert float(mm.group(1)) == float(beklenen), (ad, mm.group(1))


# =========================================================== P12bB3-05
def test_b3_05_nist_rozeti_guncelleyicinin_erisiminde_kalir(advanced_src):
    """ÇEVRİLDİ (v3.0.1 K kulvarı, Ayberk tur 1) — rozet SÖKÜLDÜ.

    P12bB3-05 başarılı oksitleyici çekiminin NIST rozetini YETİM bıraktığını
    (sınıfı ezdiğini) ölçmüş, D24/a3 de çekim yolunun rozete yazmasını
    yasaklamıştı; bekçi rozetin ve tek güncelleyicisinin (setNistStatus)
    VARLIĞINI node altında koşturarak şart koşuyordu. ÖLÇÜLDÜ
    (docs/scofield/raw/OH/V301/ayberk1/kaynak-cea/gorsel_once.json): rozet
    her makinede "NIST WebBook Offline" diyordu ve hesabın hiçbir sayısının
    kaynağı değildi; söküldü. Kalemin kazanımı (göstergeyi TEK yetkili
    yazıcı yazar, çekim yolu sınıf/metin EZMEZ) yeni oksitleyici veri
    kaynağı satırında ölçülür.
    """
    assert 'setNistStatus(' not in advanced_src
    assert not re.search(r"getElementById\('nist_status'\)", advanced_src)
    govde = _fonksiyon_kaynagi(advanced_src, 'updateOxidizerProperties')
    # Çekim yolu satıra DOĞRUDAN yazmaz; künyeyi tek yazıcıya devreder.
    assert 'oxidizer_data_source' not in govde
    assert 'setOxidizerSourceKunye(result);' in govde
    assert _fonksiyon_kaynagi(advanced_src, 'renderDataSourceLines').count(
        "getElementById('oxidizer_data_source')") == 1


# =========================================================== P12bB3-08
@node_gerekli
def test_b3_08_paket_hukmu_alt_cagrilarin_sonucundan_gelir(advanced_src):
    """Yeşil hüküm KOŞULSUZ basılamaz; hesap yokken paket üretilmiş sayılmaz.

    Ölçüldü (node): hesap koşulmadan tıklandığında alt çağrılar hata
    basıyor, sonra koşulsuz 'success' geliyordu; showMessage kutuyu her
    çağrıda temizlediği için doğru hata siliniyordu. Kullanıcının gördüğü
    "SUCCESS - Complete package generated successfully", üretilen dosya 0.
    """
    parcalar = ["""
let messages = [];
let uretilen = 0;
let cadDus = false, zipDus = false;
function showMessage(text, type) { messages = [{ type, text }]; }
function i18nText(k, d) { return d; }
function i18nFmt(k, p, d) {
  return String(d).replace(/\\{(\\w+)\\}/g, (m, g) =>
    (p && p[g] !== undefined ? p[g] : m));
}
var currentResults = null;
const durumEl = { textContent: '' };
globalThis.document = {
  getElementById: (id) => (id === 'packageStatus' ? durumEl : null)
};
async function generateCAD() {
  if (!currentResults || !currentResults.motor) {
    showMessage('Please run analysis first by clicking the Calculate button', 'error');
    return false;
  }
  if (cadDus) { showMessage('Error generating design: boom', 'error'); return false; }
  uretilen++; return true;
}
async function exportCompleteZip() {
  if (!currentResults || !currentResults.motor) {
    showMessage('Please run analysis first', 'error'); return false;
  }
  if (zipDus) { showMessage('Complete design package export failed: HTTP 500', 'error'); return false; }
  uretilen++; return true;
}
""", _fonksiyon_kaynagi(advanced_src, 'generateCompletePackage')]
    govde = """
(async () => {
  const sonuc = {};
  async function senaryo(ad, kur) {
    messages = []; uretilen = 0; cadDus = false; zipDus = false;
    durumEl.textContent = ''; currentResults = null;
    kur();
    const d = await generateCompletePackage();
    sonuc[ad] = { donus: d, uretilen,
                  hukum: messages.length
                    ? messages[0].type.toUpperCase() + ' - ' + messages[0].text
                    : '(yok)',
                  yesil: messages.length > 0 && messages[0].type === 'success',
                  durum_satiri: durumEl.textContent };
  }
  await senaryo('hesapsiz', () => {});
  await senaryo('tam', () => { currentResults = { motor: { motor_name: 'X' } }; });
  await senaryo('cad_dustu', () => {
    currentResults = { motor: { motor_name: 'X' } }; cadDus = true; });
  await senaryo('zip_dustu', () => {
    currentResults = { motor: { motor_name: 'X' } }; zipDus = true; });
  console.log(JSON.stringify(sonuc));
})();
"""
    r = _node_kos(parcalar, govde)

    # 1) Hesap yokken: yeşil YOK, dosya 0, gerçek uyarı ekranda.
    assert r['hesapsiz']['yesil'] is False, r['hesapsiz']['hukum']
    assert r['hesapsiz']['uretilen'] == 0
    assert r['hesapsiz']['donus'] is False
    assert 'run analysis first' in r['hesapsiz']['hukum'].lower()
    assert r['hesapsiz']['durum_satiri'], (
        '#packageStatus yine hiç yazılmıyor')

    # 2) İkisi de başarılıysa yeşil hüküm meşrudur.
    assert r['tam']['yesil'] is True
    assert r['tam']['uretilen'] == 2
    assert r['tam']['donus'] is True

    # 3) Bir alt çağrı düşerse HATASI EKRANDA KALIR, üstüne yeşil yazılmaz.
    for ad, iz in (('cad_dustu', 'Error generating design'),
                   ('zip_dustu', 'export failed')):
        assert r[ad]['yesil'] is False, (ad, r[ad]['hukum'])
        assert iz.lower() in r[ad]['hukum'].lower(), (ad, r[ad]['hukum'])
        assert r[ad]['donus'] is False


@node_gerekli
def test_b3_08_alt_cagrilarin_kapisi_hukmunu_bildiriyor(advanced_src):
    """Alt çağrıların FAIL-CLOSED kapıları `false` DÖNER (metin değil davranış).

    `generateCompletePackage` yeşil hükmü bu dönüş değerlerinden kuruyor;
    kapı sessizce dönerse (`return;` -> undefined) paket yine "başarılı"
    sayılır. Bu yüzden kapılar node ile GERÇEKTEN koşturulup dönüşleri
    okunuyor.
    """
    ortak = """
let messages = [];
function showMessage(text, type) { messages = [{ type, text }]; }
function i18nText(k, d) { return d; }
function i18nFmt(k, p, d) {
  return String(d).replace(/\\{(\\w+)\\}/g, (m, g) =>
    (p && p[g] !== undefined ? p[g] : m));
}
var currentResults = null;
globalThis.document = {
  querySelector: () => null,
  getElementById: () => null,
  body: { appendChild: () => {}, removeChild: () => {} }
};
"""
    for ad in ('generateCAD', '_downloadExport'):
        parcalar = [ortak, _fonksiyon_kaynagi(advanced_src, ad)]
        govde = """
(async () => {
  const d = await %s('/api/x', 'x.zip', 'X');
  console.log(JSON.stringify({ donus: d, tip: typeof d,
                               mesaj: messages.length ? messages[0].type : null }));
})();
""" % ad
        r = _node_kos(parcalar, govde)
        assert r['donus'] is False, (
            '%s kapısı %r döndürüyor (sessiz dönüş) — paket hükmü bunu '
            '"başarısız" sayamaz' % (ad, r['donus']))
        assert r['mesaj'] == 'error', (ad, r['mesaj'])

    # Başarı yolu da hükmünü bildirmeli (metin denetimi; başarı yolu ağ ister).
    for ad in ('generateCAD', '_downloadExport'):
        assert 'return true' in _fonksiyon_kaynagi(advanced_src, ad), (
            '%s başarısını bildirmiyor' % ad)


# ================================================= ENGELLİ KALEMLERİN SAĞLAM TARAFI
def test_b2_09_cozucu_gercek_itki_egrisini_yayimliyor():
    """P12bB2-09 (ENGELLİ) — onarımın ön koşulu ayakta kalır.

    Kusur ölçüldü: yörünge paneli uca TEK skaler `average_thrust`
    gönderiyor; wagon_wheel tanesinde tepe/ortalama = 3,7117
    (8.300,4 N ⟷ 2.236,3 N), yani azami ivme bu oran kadar eksik
    raporlanıyor. Onarım bu kulvarda YAPILAMAZ: tüketici
    `hrma/analysis/trajectory_analysis.py` `motor_data['thrust']`ı SKALER
    okuyor (satır 432) ve o dosya bu kulvarın sahası değil.

    Bu bekçi kusuru kilitlemez; onarımın DAYANACAĞI gerçeği korur: çözücü
    gerçek eğriyi zaten yayımlıyor. Eğri kaybolursa onarım imkânsızlaşır ve
    bu test kırmızı olur.
    """
    kaynak = (KOK / 'hrma' / 'analysis'
              / 'trajectory_analysis.py').read_text(encoding='utf-8')
    assert "motor_data['thrust']" in kaynak, (
        'yörünge çözücüsünün itki sözleşmesi değişmiş — P12bB2-09 engeli '
        'yeniden ölçülmeli')

    olcum = json.loads((kanit_gerekli(KANIT / 'sonra.json')).read_text(encoding='utf-8'))
    b209 = olcum['P12bB2-09']
    assert b209['yayimlanan_egri_nokta_sayisi'] >= 2, b209
    assert b209['wagon_wheel_tepe_ortalama_orani'] > 3.0, b209


def test_b2_03_ve_b2_06_ucun_fail_closed_kapisi_ayakta_kalir():
    """P12bB2-03 (D31 a3'te ONARILDI) / P12bB2-06 — uç kapısı korunur.

    İki kalemin kökü de form katmanıdır (`value="8"` + `|| 8`; toplayıcıda
    72 adet `|| SAYI`) ve ÖK-21 gereği bu dalgada sökülemez. Kusuru gören
    bekçi bilerek YAZILMADI (kusuru kilitlerdi). Korunan şey, söküm sırası
    geldiğinde arkasında duracak sağlam taraf: ucun kendi fail-closed
    kapısı (ÖK-22 — sağlıklı envanter gevşetilemez).
    """
    once = json.loads((kanit_gerekli(KANIT / 'once.json')).read_text(encoding='utf-8'))
    sonra = json.loads((kanit_gerekli(KANIT / 'sonra.json')).read_text(encoding='utf-8'))

    # Uç boş gövdeyi 422 ile reddediyor (kapı canlı).
    for kayit in (once, sonra):
        assert kayit['P12bB2-06']['bos_govde_durum'] == 422, kayit['P12bB2-06']
        # Cidar verilmediğinde onay geri çekiliyor: bu dal ÜRÜNDEN
        # erişilemez ama UÇTA ayakta.
        assert kayit['P12bB2-03']['vessel_status_ansiz'] == 'NOT_EVALUATED'
        assert kayit['P12bB2-03']['wall_thickness_source_ansiz'] == 'sized_by_hrma'

    # ÖK-21 MANDALI ÇEVRİLDİ — ÖH D31 · arayuz-panel a3 (14 Eyl 2026).
    #
    # Bu blok ÖK-21 kilidi KAPALIYKEN yazılmıştı ve "form varsayılanı
    # sökülmüş" durumunu İHLAL sayıyordu. Berke 14 Eyl'de kilidi AÇTI
    # (D31 ÖZEL, ÖK-21 form katmanı doktrini); P12bB2-03 aynı dalgada
    # onarıldı (`docs/scofield/raw/OH/D31/arayuz-panel/a3/`). Mandal
    # yerinde bırakılsaydı ONARIMI kırmızıya düşürür, yani kusuru
    # KORUYAN bekçi hâline gelirdi.
    #
    # Korunan şey değişmedi: ucun fail-closed kapısı (yukarıdaki üç
    # iddia) AYNEN duruyor. Değişen tek şey, form katmanının artık
    # sökülmüş OLMASI gerektiğidir — yön tersine döndü.
    solid = SOLID.read_text(encoding='utf-8')
    assert not re.search(r'id="case_thickness"[^>]*value="[-\d.]+"', solid), (
        'case_thickness yeniden form sabiti taşıyor: ÖK-21 sökümü geri '
        'alınmış (D31 a3 onarımı, P12bB2-03)')
    capa = _fonksiyon_kaynagi(solid, 'collectAllParameters')
    assert len(re.findall(r"\|\|\s*[0-9]", capa)) <= 68, (
        'toplayıcıdaki `|| SAYI` kalıbı ARTMIŞ: yeni bir sessiz yedek '
        'eklenmiş (D31 a3 ölçümü: 70 -> 68)')
    assert "two_phase_loss: solOptNum('two_phase_loss')," in capa
    assert "case_thickness: solOptNum('case_thickness')," in capa
