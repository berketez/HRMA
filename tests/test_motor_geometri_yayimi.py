"""v2.6.27 (B1/B2/B3) — üç motorun geometri yayımının bekçileri.

motor_viz3d.js CAD çizimleri üç passthrough bloğunu bekler (alan adları
SÖZLEŞMEDİR, şablon adaptörleri adları değiştirmeden taşır):

  nozzle_contour:   {points: [[z_m, r_m], ...], _basis}
  cooling_channels: {n_channels, channel_width_m, channel_height_m,
                     land_width_m, _basis}
  injector_pattern: {n_holes, hole_diameter_m, pattern_type,
                     impingement_angle_deg?, n_rings?, _basis}

Bu dosyadaki testler blokların GERÇEK hesaptan (uçtan uca, app.test_client)
geldiğini, şema adlarına birebir uyduğunu ve fiziksel olarak tutarlı
olduğunu kilitler. Ölçümler 4 Ağustos 2026'da bu depoda koşturularak alındı:

  * Hibrit (2 kN, N2O/HTPB, 30 bar): 42 nokta, ilk nokta
    [0.0, 0.050510...] = kamara yarıçapı, z kesin artan, showerhead 5 delik.
  * Katı (Ø100/Ø35 BATES, 40 bar): 42 nokta, ilk nokta [0.0, 0.05],
    son nokta çıkış yarıçapı 0.04456 m.
  * Sıvı (25 kN RP1/LOX, 70 bar, rejeneratif, impinging): 67 nokta,
    38 kanal (3.0 x 2.0 mm, boğaz land 1.512 mm), 28+15 = 43 delik,
    çarpışma tam açısı 60°.

ORİJİN SÖZLEŞMESİ: konturun İLK noktası konverjan girişidir (kamara-lüle
birleşimi, z = 0, r = kamara yarıçapı) ve z çıkışa doğru artar — viz3d bu
varsayımla çizer; boğaz-orijinli seri lüleyi yanlış konumlandırır.

FABRİKASYON YASAĞI: katı ve hibritte rejeneratif kanal, katıda enjektör
FİZİKSEL OLARAK yoktur; sıvıda rejeneratif olmayan soğutmada frezeli kanal
imal edilmez. İlgili bloklar bu durumlarda yanıtta HİÇ bulunmamalıdır —
"boş blok" da yasaktır, çünkü viz savunmacı okur ama boş blok veri varmış
izlenimi verir.
"""

import contextlib
import io
import math

import pytest

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def _quiet(fn, *args, **kwargs):
    """Motor modülleri stdout'a bolca basıyor; testte sessize al."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def hibrit_govde(client):
    yuk = {'motor_name': 'geo-h', 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
           'thrust': 2000, 'burn_time': 10, 'chamber_pressure': 30,
           'of_ratio': 6.0}
    resp = _quiet(client.post, '/calculate', json=yuk)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


@pytest.fixture(scope='module')
def hibrit_yaniti(hibrit_govde):
    """Hibrit viz sözlüğü = /calculate yanıtının 'motor' alt sözlüğü.

    Katı/sıvıdan FARKLI olarak /calculate motor sonuçlarını üst düzeye
    değil 'motor' anahtarına koyar; app.js 3B sahneyi
    ``mountMotorViz(currentResults.motor)`` ile kurar (app.js:679-681).
    Yani hibritte viz3d'nin okuduğu md = yanıt['motor'] — bloklar orada
    aranır. Üst düzeyde aramak bu testin ilk sürümünde yapılan hataydı."""
    motor = hibrit_govde.get('motor')
    assert isinstance(motor, dict), "/calculate yanıtında 'motor' bloğu yok"
    return motor


@pytest.fixture(scope='module')
def kati_yaniti(client):
    yuk = {'motor_name': 'geo-s', 'chamber_pressure': 40, 'thrust': 1500,
           'burn_time': 3, 'grain_type': 'bates', 'outer_diameter': 100,
           'core_diameter': 35, 'grain_length': 300, 'segments': 1,
           'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
           'chamber_temperature': 3000, 'c_star': 1550,
           'propellant_density': 1800, 'propellant_type': 'apcp'}
    resp = _quiet(client.post, '/calculate_solid', json=yuk)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


SIVI_YUK = {'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'mixture_ratio': 2.3,
            'thrust': 25000, 'chamber_pressure': 70,
            'engine_cycle': 'gas_generator', 'injector_type': 'impinging',
            'contraction_ratio': 4, 'characteristic_length': 1.2,
            'chamber_material': 'inconel_718',
            'cooling_type': 'regenerative', 'nozzle_type': 'bell_80',
            'safety_factor': 2.5}


@pytest.fixture(scope='module')
def sivi_yaniti(client):
    pytest.importorskip('rocketcea.cea_obj')
    resp = _quiet(client.post, '/calculate_liquid', json=SIVI_YUK)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


@pytest.fixture(scope='module')
def sivi_ablatif_yaniti(client):
    """Rejeneratif OLMAYAN sıvı tasarım — fabrikasyon-yok bekçisi için."""
    pytest.importorskip('rocketcea.cea_obj')
    yuk = dict(SIVI_YUK, cooling_type='ablative')
    resp = _quiet(client.post, '/calculate_liquid', json=yuk)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


#: Sözleşme anahtar kümeleri — motor_viz3d.js okuyucularının adları.
#: Fazladan anahtar da yakalanır: sözleşme dışı ad sessizce ölü veri olur.
KONTUR_ANAHTARLARI_ZORUNLU = {'points', '_basis'}
KANAL_ANAHTARLARI = {'n_channels', 'channel_width_m', 'channel_height_m',
                     'land_width_m', '_basis'}
DESEN_ANAHTARLARI = {'n_holes', 'hole_diameter_m', 'pattern_type',
                     'impingement_angle_deg', 'n_rings', '_basis'}
DESEN_SOZCUKLERI = {'showerhead', 'impinging', 'swirl', 'pintle', 'coaxial'}


def _kontur_dogrula(yanit, kamara_capi_m, cikis_capi_m, bogaz_capi_m):
    """Ortak kontur bekçisi: şema + fiziksel tutarlılık + orijin sözleşmesi.

    motor_viz3d.js selectNozzleContour'un RED kuralları buradaki
    doğrulamanın aynısıdır (sonlu olmayan / negatif r / artmayan z diziyi
    bütünüyle reddeder); burada geçen bir seri orada da geçer.
    """
    kontur = yanit.get('nozzle_contour')
    assert isinstance(kontur, dict), 'nozzle_contour bloğu yayımlanmıyor'
    eksik = KONTUR_ANAHTARLARI_ZORUNLU - set(kontur)
    assert not eksik, f'nozzle_contour sözleşme anahtarları eksik: {eksik}'
    assert isinstance(kontur['_basis'], str) and kontur['_basis'], (
        '_basis beyanı boş — kaynaksız geometri yayımlanamaz')
    assert 'convergent inlet' in kontur['_basis'], (
        '_basis orijin sözleşmesini beyan etmiyor (ilk nokta = konverjan '
        'girişi); viz3d bu varsayımla çizer')

    pts = kontur['points']
    assert isinstance(pts, list) and len(pts) >= 3, (
        'points en az 3 noktalı liste olmalı (viz3d < 3 noktayı reddeder)')
    for p in pts:
        assert isinstance(p, (list, tuple)) and len(p) == 2, (
            f'nokta [z_m, r_m] çifti değil: {p!r}')
        z, r = p
        assert math.isfinite(z) and math.isfinite(r), f'sonlu olmayan nokta: {p!r}'
        assert r > 0.0, f'yarıçap pozitif değil: {p!r}'

    z_dizi = [p[0] for p in pts]
    r_dizi = [p[1] for p in pts]
    assert all(b > a for a, b in zip(z_dizi, z_dizi[1:])), (
        'z kesin artan değil — viz3d bütün diziyi reddeder')

    # Birim bekçisi: metre sözleşmesi. mm yayımlanırsa z_max binlerce olur.
    assert max(z_dizi) < 5.0 and max(r_dizi) < 1.0, (
        f'değerler metre ölçeğinde değil (z_max={max(z_dizi)}, '
        f'r_max={max(r_dizi)}) — mm yayımı sözleşme ihlalidir')

    # Orijin sözleşmesi: ilk nokta konverjan girişi (z=0, r=kamara yarıçapı).
    assert z_dizi[0] == pytest.approx(0.0, abs=1e-12), (
        'ilk nokta z=0 (konverjan girişi) değil')
    assert r_dizi[0] == pytest.approx(kamara_capi_m / 2.0, rel=1e-6), (
        'ilk nokta kamara yarıçapında değil — kontur boğaz-orijinli ya da '
        'yanlış kamaradan örneklenmiş olabilir')

    # Son nokta çıkış yarıçapı; en dar nokta boğaz yarıçapı.
    assert r_dizi[-1] == pytest.approx(cikis_capi_m / 2.0, rel=1e-3), (
        'son nokta lüle çıkış yarıçapında değil')
    assert min(r_dizi) == pytest.approx(bogaz_capi_m / 2.0, rel=1e-3), (
        'konturun en dar noktası boğaz yarıçapı değil')
    # Boğaz uçlarda değil içeride olmalı (konverjan + ıraksak birlikte).
    en_dar = r_dizi.index(min(r_dizi))
    assert 0 < en_dar < len(r_dizi) - 1, (
        'boğaz konturun ucunda — konverjan ya da ıraksak bölüm eksik')


# ---------------------------------------------------------------------------
# B3 — lüle iç konturu: üç motor tipi
# ---------------------------------------------------------------------------
class TestLuleKonturuYayimi:
    """Kontur, STL/STEP/2B kesitle AYNI örnekleyiciden (nozzle_design.
    sample_nozzle_inner_contour) gelir ve metre cinsinden [z, r] çiftleriyle
    yayımlanır. Motor rotalarının üst düzey birimleri farklıdır (hibrit m,
    katı mm, sıvı karışık) — bekçi her rotada metre sözleşmesini ayrıca
    kilitler."""

    def test_hibrit_konturu(self, hibrit_yaniti):
        # Hibrit üst düzeyi METRE yayımlar.
        _kontur_dogrula(hibrit_yaniti,
                        hibrit_yaniti['chamber_diameter'],
                        hibrit_yaniti['exit_diameter'],
                        hibrit_yaniti['throat_diameter'])

    def test_hibrit_konturu_nozzle_designer_blogunu_ezmiyor(
            self, hibrit_yaniti):
        """Hibritte nozzle_contour zaten NozzleDesigner bloğunu taşıyordu
        (convergent/divergent). points o bloğa EKLENİR; eski anahtarlar
        kaybolursa sample_nozzle_inner_contour ıraksak boyu çözücüden
        okuyamaz hâle gelir (L_div kaynağı 'nozzle_contour.divergent.length')."""
        kontur = hibrit_yaniti['nozzle_contour']
        assert 'convergent' in kontur and 'divergent' in kontur, (
            'NozzleDesigner kontur alt sözlükleri kayboldu — points yayımı '
            'mevcut bloğu ezmiş')

    def test_kati_konturu(self, kati_yaniti):
        # Katı üst düzeyi MM yayımlar; kontur yine METRE olmalı.
        _kontur_dogrula(kati_yaniti,
                        kati_yaniti['chamber_diameter'] / 1000.0,
                        kati_yaniti['exit_diameter'] / 1000.0,
                        kati_yaniti['throat_diameter'] / 1000.0)

    def test_sivi_konturu(self, sivi_yaniti):
        # Sıvı üst düzeyi KARIŞIK yayımlar: chamber mm, throat/exit m.
        _kontur_dogrula(sivi_yaniti,
                        sivi_yaniti['chamber_diameter'] / 1000.0,
                        sivi_yaniti['exit_diameter'],
                        sivi_yaniti['throat_diameter'])


# ---------------------------------------------------------------------------
# B1 — rejeneratif soğutma kanalları (yalnız sıvı + regen)
# ---------------------------------------------------------------------------
class TestSogutmaKanallariYayimi:
    def test_regen_tasarimda_blok_var_ve_tutarli(self, sivi_yaniti):
        blok = sivi_yaniti.get('cooling_channels')
        assert isinstance(blok, dict), (
            'rejeneratif sıvı tasarımda cooling_channels bloğu yok')
        fazla = set(blok) - KANAL_ANAHTARLARI
        assert not fazla, f'sözleşme dışı anahtar: {fazla}'
        assert isinstance(blok['_basis'], str) and blok['_basis']

        n = blok['n_channels']
        assert isinstance(n, int) and n >= 1, f'n_channels geçersiz: {n!r}'
        for ad in ('channel_width_m', 'channel_height_m'):
            assert blok[ad] > 0.0, f'{ad} pozitif değil: {blok[ad]!r}'
            assert blok[ad] < 0.1, (
                f'{ad}={blok[ad]} metre sözleşmesine göre anormal büyük — '
                'mm yayımı olabilir')

        # Çözücünün kendi sayılarıyla birebir aynı kaynak (kopya değil çeviri).
        cool = sivi_yaniti['cooling_system']
        assert n == int(cool['cooling_channels'])
        assert blok['channel_width_m'] == pytest.approx(
            cool['channel_width_mm'] / 1000.0, rel=1e-9)
        assert blok['channel_height_m'] == pytest.approx(
            cool['channel_height_mm'] / 1000.0, rel=1e-9)

        # Land boğazda türetilir: pi*d_t/n - w; yayımlandıysa pozitif ve
        # hatveden küçük olmalı (aksi geometrik saçmalık).
        if 'land_width_m' in blok:
            d_t = sivi_yaniti['throat_diameter']  # m
            hatve = math.pi * d_t / n
            assert 0.0 < blok['land_width_m'] < hatve
            assert blok['land_width_m'] == pytest.approx(
                hatve - blok['channel_width_m'], rel=1e-6)

    def test_regen_olmayan_tasarimda_blok_yok(self, sivi_ablatif_yaniti):
        """Fabrikasyon-yok bekçisi: ablatif cidarda frezeli kanal İMAL
        EDİLMEZ; blok yanıtta hiç bulunmamalı. (Çözücü film/dump soğutmada
        da kanal hidroliği hesaplar — o hesap cooling_system içinde kalır,
        imalat geometrisi sözleşmesine SIZAMAZ.)"""
        assert 'cooling_channels' not in sivi_ablatif_yaniti, (
            'rejeneratif olmayan tasarımda cooling_channels yayımlandı — '
            'viz bu kanalları gömlek geometrisi olarak çizer (fabrikasyon)')

    def test_kati_ve_hibritte_blok_yok(self, kati_yaniti, hibrit_yaniti):
        assert 'cooling_channels' not in kati_yaniti
        assert 'cooling_channels' not in hibrit_yaniti


# ---------------------------------------------------------------------------
# B2 — enjektör delik deseni (sıvı + hibrit; katıda enjektör yok)
# ---------------------------------------------------------------------------
def _desen_dogrula(blok):
    fazla = set(blok) - DESEN_ANAHTARLARI
    assert not fazla, f'sözleşme dışı anahtar: {fazla}'
    assert isinstance(blok['_basis'], str) and blok['_basis']
    assert isinstance(blok['n_holes'], int) and blok['n_holes'] >= 1
    assert blok['pattern_type'] in DESEN_SOZCUKLERI, (
        f"pattern_type sözleşme sözcüğü değil: {blok['pattern_type']!r}")
    if 'hole_diameter_m' in blok:
        assert 0.0 < blok['hole_diameter_m'] < 0.1, (
            'hole_diameter_m metre sözleşmesine uymuyor (mm yayımı?)')
    if 'impingement_angle_deg' in blok:
        assert 0.0 < blok['impingement_angle_deg'] < 180.0
    # Hiçbir çözücü halka sayısı hesaplamıyor: alan yayımlanamaz
    # (hesaplanmayan alan konmaz — sahte veri yasağı).
    assert 'n_rings' not in blok, (
        'n_rings yayımlanmış ama depoda halka yerleşimi çözen kod yok')


class TestEnjektorDeseniYayimi:
    def test_sivi_impinging_deseni(self, sivi_yaniti):
        blok = sivi_yaniti.get('injector_pattern')
        assert isinstance(blok, dict), (
            'devre modeli çözülen sıvı tasarımda injector_pattern yok')
        _desen_dogrula(blok)
        assert blok['pattern_type'] == 'impinging'

        # Delik sayısı devre modelinin KENDİ sayılarının toplamı olmalı.
        detay = sivi_yaniti['injection_system']['injector_design_detail']
        assert detay.get('status') == 'success', (
            'fikstür varsayımı bozuldu: devre modeli çözmemiş')
        n_ox = int(detay['ox_circuit']['n_orifices'])
        n_fuel = int((detay.get('fuel_circuit') or {}).get('n_orifices') or 0)
        assert blok['n_holes'] == n_ox + n_fuel

        # Çarpışmalı tipte sözleşme İKİ JET ARASINDAKİ TAM açıyı taşır
        # (viz yarılayarak çizer); kaynak modülün kendi yarım açısıdır.
        yarim = detay['pattern']['impingement']['half_angle_deg']
        assert blok['impingement_angle_deg'] == pytest.approx(2.0 * yarim)

        # İki devrenin çapı farklıysa tek çap yayımlamak yakıt deliklerini
        # oksitleyici çapında göstermek olur — alan konmaz.
        d_ox = float(detay['ox_circuit']['orifice_d_mm'])
        d_fuel = float((detay.get('fuel_circuit') or {}).get('orifice_d_mm')
                       or 0.0)
        if d_fuel > 0 and abs(d_ox - d_fuel) > 0.01 * max(d_ox, d_fuel):
            assert 'hole_diameter_m' not in blok, (
                'iki devre farklı çapta ama tek hole_diameter_m yayımlanmış')

    def test_hibrit_deseni_tek_devreden(self, hibrit_yaniti):
        detay = hibrit_yaniti.get('injector_design_detail')
        if not (isinstance(detay, dict) and detay.get('status') == 'success'):
            # Devre modeli çözemediyse desen de OLMAMALI (uydurma yok).
            assert 'injector_pattern' not in hibrit_yaniti
            pytest.skip('hibrit devre modeli bu fikstürde çözmedi')
        blok = hibrit_yaniti.get('injector_pattern')
        assert isinstance(blok, dict), (
            'devre modeli çözülen hibritte injector_pattern yok')
        _desen_dogrula(blok)
        oxc = detay['ox_circuit']
        assert blok['n_holes'] == int(oxc['n_orifices'])
        assert blok['hole_diameter_m'] == pytest.approx(
            float(oxc['orifice_d_mm']) / 1000.0, rel=1e-9)

    def test_katida_desen_yok(self, kati_yaniti):
        """Katı motorda enjektör FİZİKSEL OLARAK yoktur."""
        assert 'injector_pattern' not in kati_yaniti


# ---------------------------------------------------------------------------
# Uçtan uca görünürlük: bloklar HTTP yanıtının ÜST DÜZEYİNDE
# ---------------------------------------------------------------------------
class TestUctanUcaGorunurluk:
    """Şablon adaptörleri ('cooling_channels', 'injector_pattern',
    'nozzle_contour') anahtarlarını yanıtın ÜST düzeyinden passthrough
    taşır (liquid.html/solid.html forEach listesi). Blok alt sözlüğe
    gömülürse adaptör onu hiç görmez — bekçi üst düzey adresi kilitler."""

    def test_hibrit_motor_blogunda(self, hibrit_govde, hibrit_yaniti):
        # Hibritte viz md'si yanıtın 'motor' alt sözlüğüdür (fikstür notu).
        assert 'motor' in hibrit_govde
        assert 'nozzle_contour' in hibrit_yaniti
        assert 'points' in hibrit_yaniti['nozzle_contour']

    def test_kati_ust_duzey(self, kati_yaniti):
        assert 'nozzle_contour' in kati_yaniti
        assert 'points' in kati_yaniti['nozzle_contour']

    def test_sivi_ust_duzey(self, sivi_yaniti):
        assert 'nozzle_contour' in sivi_yaniti
        assert 'points' in sivi_yaniti['nozzle_contour']
        assert 'cooling_channels' in sivi_yaniti
        assert 'injector_pattern' in sivi_yaniti
