"""Eksenel profilin GEOMETRİ EKSENİ bekçileri (D2 zinciri, v2.6.27).

KAPATILAN KUSUR
---------------
``HeatTransferAnalyzer.analyze_axial_profile`` ile FEA köprüsü
(``hrma.fea.bridge``) AYNI motor için AYNI ekseni üretmek zorundadır: köprü
gaz tarafı h(z)'yi profilden alıp motorun konturu üzerine kurulan mesh'e
taşır. Eksenler ayrışırsa BAŞKA bir geometrinin ısı yükü bu mesh'e basılır;
köprü bunu %5'lik alan toleransıyla yakalar ve fail-closed reddeder
(``THERMAL_PROFILE_DOMAIN_TOL``).

ÖLÇÜLEN (2026-08-15, 2 kN / 30 bar hibrit; düzeltmeden ÖNCE):
  * Örnekleyici lüle tipini YALNIZ ``nozzle_angles['nozzle_type']`` ya da
    ``nozzle_contour['divergent']['type']`` alanlarından okur. Hibrit
    çözücünün kendi çağrısı (hybrid_rocket_engine.py, lüle malzeme analizi)
    tipi ÜST DÜZEY ``motor_data['nozzle_type']`` anahtarına yazıyordu ve o
    anahtarı hiç kimse okumuyordu: bell motorun profili KONİK varsayılıyor,
    eksen 171,85 mm çıkarken yayımlanan kontur 87,31 mm idi (%96,8).
  * Aynı çağrı çıkış çapını da geçirmediği için örnekleyici KENDİ jenerik
    çıkış çapına düşüyordu; bu, konik motorda bile ekseni 126,16 mm yerine
    171,85 mm yapıyordu (%36,2) ve ıslak yüzey integraline %43 fazla alan
    olarak giriyordu.
  * Profil hangi konturu kullandığını HİÇ beyan etmiyordu; jenerik varsayılan
    ile motorun gerçek geometrisi çıktıda birbirinden ayırt edilemiyordu.

NE KİLİTLENİR
-------------
  1. Motor sonucu kontur YAYIMLAMIŞSA eksen o diziden gelir — köprünün
     okuduğu dizinin ta kendisi — yani uyum tesadüf değil, tanım gereğidir
     (konik + bell, sapma tam sıfır).
  2. Köprü bu profili kabul eder (``status='ok'``), tolerans ölçütü
     köprüden OKUNUR (sayı kopyalanmaz).
  3. Uçtan uca zincir yeşil kalır: ``/calculate`` → ``wall-profile`` →
     ``/api/fea/thermal`` (üreme noktası 2 kN/30 bar + varsayılan hibrit).
  4. Üst düzey ``nozzle_type`` artık örnekleyicinin okuduğu yere taşınır.
  5. Verilmeyen şekil alanı ADIYLA beyan edilir (``generic_defaults_used``);
     jenerik eksen sessizce motorun geometrisi gibi sunulmaz.
  6. 0 / '' geometri değeri "verilmedi" sayılır (eski ``setdefault`` tuzağı:
     0 geçerli sanılıp boğaz yarıçapı sıfırlanıyordu).
  7. Yayımlanan kontur bozuksa (kesin artan değil, r <= 0, biçimsiz) sessizce
     kabul edilmez: canlı örneklemeye düşülür ve gerekçe beyan edilir.
  8. Eksenin başlangıcı VARSAYILMAZ, konturdan okunur.
  9. Kapı, KÜNYESİNDE belgelediği kusur vakasını (profil 171 mm / kontur
     124 mm → %37,9 sapma) reddetmeye devam eder; ve bu dosyanın sınırları
     artık ``THERMAL_PROFILE_DOMAIN_TOL``dan TÜRETİLMEZ, ölçülmüş vakalara
     çapalıdır (ÖH FAZ B-1 adım #9 — defter P14M4-03d / P14M4-03c).

Sayısal doğruluk bu dosyanın işi değildir (o profilin kendi fizik
testlerinin işi: tests/test_axial_profile.py); burada kilitlenen şey iki
üreticinin TEK geometri kaynağında buluşmasıdır.
"""

import contextlib
import io

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.fea import bridge

#: Üreme noktası (görev metnindeki nokta) ve varsayılan hibrit.
UREME = dict(fuel_type='htpb', oxidizer_type='n2o', thrust=2000,
             burn_time=10, chamber_pressure=30, of_ratio=7.0)
VARSAYILAN = dict(fuel_type='htpb', oxidizer_type='n2o', thrust=1000,
                  burn_time=10, chamber_pressure=20, of_ratio=7.0)

#: Panelin (thermal_fea_panel.js buildWallProfileBody) GERÇEKTEN gönderdiği
#: alanlar — bekçi zinciri sahadaki gövdeyle koşsun diye birebir kopyalanır.
PANEL_ALANLARI = ('chamber_pressure', 'chamber_temperature', 'burn_time',
                  'mdot_total', 'chamber_diameter', 'chamber_length',
                  'throat_diameter')

# ----------------------------------------------------------------------
# ÖLÇÜLMÜŞ ÇAPALAR (ÖH FAZ B-1 adım #9 — defter P14M4-03d / P14M4-03c)
# ----------------------------------------------------------------------
# H2 KURALI: BİR EŞİĞİ KORUYAN İDDİA O EŞİKTEN TÜRETİLMİŞ OLAMAZ.
#
# Bu dosyanın bekçileri sınırlarını, korumakla yükümlü oldukları sabitin
# KENDİSİYLE yazıyordu (``sapma <= bridge.THERMAL_PROFILE_DOMAIN_TOL * L``).
# Refleks tek-kaynak hijyeni açısından doğruydu ("ölçüt kopyalanmaz, okunur")
# ama eşiğin KENDİ bekçisine uygulandığında iddiayı totolojiye çeviriyordu:
# sabit gevşerse iddia da onunla gevşer.
#
# ÖLÇÜLDÜ (P14M4-03d): ``THERMAL_PROFILE_DOMAIN_TOL`` 0,05 -> 0,40 (8×)
# yapıldığında 6 dosya / 198 test SIFIR kırmızı verdi; gerçek RED bekçisi
# ancak 60×'ten sonra ısırıyordu, arada kalan bantta kapı kendi künyesinde
# BELGELEDİĞİ kusur vakasını sessizce kabul ediyordu.
#
# Çözüm: sınırlar TOL türetmesinden koparıldı ve iki ölçülmüş vakaya
# çapalandı (aşağıdaki iki sabit). Çapalar üründen İTHAL EDİLMEZ.

#: Bugün ölçülen profil-kontur sapması — analizör yolunda da (bu dosyanın
#: 2026-08-26 ölçümü: konik / bell / varsayılan hibrit üçünde de tam
#: 0,000000e+00 mm) UÇTAN UCA zincirde de (aynı ölçüm, panel gövdesi ->
#: /api/analysis/wall-profile -> /api/fea/thermal: yine 0,000000e+00 mm) SIFIR.
#: Sıfır olmasının sebebi tanım gereğidir: eksen, köprünün okuduğu dizinin ta
#: kendisinden okunuyor. Tavan 1e-6 mm = 1 nm; ürün toleransının (TOL·L ≈
#: 4,4-6,3 mm) yaklaşık 5e6 katı SIKI ve tamamen ondan bağımsız.
SAPMA_TAVANI_MM = 1e-6

#: Köprünün kendi künyesinin (``bridge.py:177-178``) BELGELEDİĞİ ölçülmüş
#: kusur vakası: "aynı motorun geometrisi eksik verilerek çağrılan profil
#: 171 mm, konturu 124 mm çıkıyor" — yani kapının var oluş sebebi olan gerçek
#: sapma, kontur boyunun %37,9'udur. Kapı bu vakayı reddetmeyi bırakırsa
#: BAŞKA geometrinin h(z)'si mesh'e taşınır.
KUNYE_PROFIL_MM = 171.0
KUNYE_KONTUR_MM = 124.0
KUNYE_SAPMA_ORANI = (KUNYE_PROFIL_MM - KUNYE_KONTUR_MM) / KUNYE_KONTUR_MM

#: Konik ve bell eksen boylarının ÖLÇÜLEN farkı (2 kN / 30 bar hibrit).
#: 2026-08-26 ölçümü 126,158257 − 87,306353 = 38,851905 mm idi (bell boyunun
#: %44,5'i). v3.0.1'de kamara tane zarfından boyutlanır (port-kamara kulvarı;
#: bu gövdede D_ch 68,66 mm) ve çapa main bd05a6f9e'de kırmızıydı. 2026-10-22
#: YENİDEN ÖLÇÜLDÜ: 97,595082 − 70,919630 = 26,675452 mm (bell boyunun
#: %37,6'sı); ön koşul ("iki geometri gerçekten ayrı", > %25) aynen sağlanıyor.
#: Meta bekçi bu farkı TOL ile değil bu ölçümle sınar.
KONIK_BELL_FARK_MM = 26.675452


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
def analyzer():
    return HeatTransferAnalyzer()


def _coz(client, **ek):
    govde = dict(UREME)
    govde.update(ek)
    resp = _quiet(client.post, '/calculate', json=govde,
                  headers={'Host': '127.0.0.1:8080'})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()['motor']


@pytest.fixture(scope='module')
def motor_konik(client):
    return _coz(client, nozzle_type='conical')


@pytest.fixture(scope='module')
def motor_bell(client):
    return _coz(client, nozzle_type='bell')


@pytest.fixture(scope='module')
def motor_varsayilan(client):
    govde = dict(VARSAYILAN)
    resp = _quiet(client.post, '/calculate', json=govde,
                  headers={'Host': '127.0.0.1:8080'})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()['motor']


def kontur_araligi_mm(motor):
    """Yayımlanan konturun [z_ilk, z_son] aralığı [mm] — köprünün okuduğu dizi."""
    pts = np.asarray(motor['nozzle_contour']['points'], dtype=float)
    z = pts[:, 0] * 1000.0
    return float(z.min()), float(z.max())


def panel_govdesi(motor):
    """thermal_fea_panel.js'in gerçekten gönderdiği wall-profile gövdesi.

    Parti 25: panel gövdesi artık motorun yayımladığı ``nozzle_contour``'u
    da taşıyor (buildWallProfileBody + uç beyaz listesi) — bell/parabolik
    eksen kimliği ancak böyle kuruluyor. Bu ayna, panel bekçisindeki
    ``profil_govdesi`` ile aynı sözleşmededir (test_thermal_fea_panel.py)."""
    govde = {k: motor[k] for k in PANEL_ALANLARI}
    govde['expansion_ratio'] = motor['expansion_ratio']
    kontur = motor.get('nozzle_contour')
    if (isinstance(kontur, dict) and isinstance(kontur.get('points'), list)
            and len(kontur['points']) >= 2):
        govde['nozzle_contour'] = kontur
    # ÖH D19 / P7B3-30: panel motorun kendi malzemesini de gönderiyor —
    # profil ve mesh AYNI cidarı anlatmak zorunda (yoksa /api/fea/thermal
    # adlı 422 ``axial_profile_material_mismatch`` verir).
    # V301/PANEL (NK-12): termal alan yalnız lüledir; panel ÖNCE motorun
    # lüle malzemesini okur (köprü NOZZLE_MATERIAL_PATHS ile aynı sıra).
    for blok, alan in (('nozzle_material_analysis', 'material'),
                       ('nozzle_design', 'material_key')):
        deger = (motor.get(blok) or {}).get(alan)
        if isinstance(deger, str) and deger.strip():
            govde['material'] = deger.strip()
            return govde
    sa = motor.get('structural_analysis')
    if isinstance(sa, dict):
        for blok, alan in (('design_parameters', 'material'),
                           ('chamber_structure', 'material_key'),
                           ('case_analysis', 'case_material')):
            deger = (sa.get(blok) or {}).get(alan)
            if isinstance(deger, str) and deger.strip():
                govde['material'] = deger.strip()
                break
    return govde


# ======================================================================
# 1) Eksen kimliği: profil ile köprü aynı konturu görür
# ======================================================================
class TestEksenKimligi:
    @pytest.mark.parametrize('ad', ['konik', 'bell'])
    def test_eksen_yayimlanan_konturdan_gelir(self, analyzer, ad,
                                              motor_konik, motor_bell):
        """Motor kontur yayımlamışsa eksen O DİZİDEN okunur (sapma = 0).

        Uyum tesadüf değil: köprü de aynı diziyi okur. Konik lülede eski kod
        da tutturuyordu (örnekleyicinin jenerik varsayılanları hibridin konik
        seçimiyle çakışıyor) ama bell'de 38,7 mm ayrışıyordu.
        """
        motor = motor_konik if ad == 'konik' else motor_bell
        profil = analyzer.analyze_axial_profile(motor, n_stations=40)
        z0, z1 = kontur_araligi_mm(motor)
        assert profil['x_mm'][0] == pytest.approx(z0, abs=1e-9)
        assert profil['x_mm'][-1] == pytest.approx(z1, abs=1e-9)
        assert profil['x_exit_mm'] == pytest.approx(z1, abs=1e-9)
        kunye = profil['contour_basis']
        assert 'nozzle_contour' in kunye['source']
        assert kunye['generic_defaults_used'] == []

    @pytest.mark.parametrize('ad', ['konik', 'bell'])
    def test_kopru_profili_kabul_eder(self, analyzer, ad,
                                      motor_konik, motor_bell):
        """Köprü eksen-uyum kapısını GEÇER; sapma ÖLÇÜLMÜŞ tavana çapalıdır.

        ESKİ HALİ (P14M4-03d ile ölçülen kusur):
            ``assert sapma <= bridge.THERMAL_PROFILE_DOMAIN_TOL * (z1 - z0)``
        Bu iddia sınırını, korumakla yükümlü olduğu sabitin KENDİSİNDEN
        türetiyordu: TOL 8× gevşetildiğinde iddianın tavanı da 8× gevşiyor ve
        bekçi hiçbir şey söylemiyordu (6 dosya / 198 test → 0 kırmızı).

        YENİ HALİ: tavan ``SAPMA_TAVANI_MM`` (1e-6 mm), ölçülen sapma
        0,000000e+00 mm'den geliyor ve üründeki hiçbir sabite bakmıyor.
        Kapının kendisinin gevşemesi bu iddiayı gevşetemez; kapının
        gevşemesini yakalayan iddia bir alttaki ``..._kunye_vakasini_reddeder``
        testidir (davranışsal, TOL'den bağımsız).

        H2 kuralı: BİR EŞİĞİ KORUYAN İDDİA O EŞİKTEN TÜRETİLMİŞ OLAMAZ.
        """
        motor = motor_konik if ad == 'konik' else motor_bell
        profil = analyzer.analyze_axial_profile(motor, n_stations=40)
        sonuc = bridge.extract_thermal_inputs(motor, axial_profile=profil,
                                              include_chamber=False)
        assert sonuc['status'] == bridge.BRIDGE_STATUS_OK, sonuc.get('reason')

        z0, z1 = kontur_araligi_mm(motor)
        sapma = max(abs(profil['x_mm'][0] - z0), abs(profil['x_mm'][-1] - z1))
        assert sapma <= SAPMA_TAVANI_MM, (
            '%s: sapma %.6e mm > ölçülmüş tavan %.1e mm (ölçülen taban '
            '0,000000e+00 mm — eksen konturdan OKUNUYOR)'
            % (ad, sapma, SAPMA_TAVANI_MM))

    @pytest.mark.parametrize('ad', ['konik', 'bell'])
    def test_kopru_kunye_vakasini_reddeder(self, analyzer, ad,
                                           motor_konik, motor_bell):
        """Kapı, KÜNYESİNDE belgelediği kusur vakasını reddetmeye devam eder.

        NEDEN BU TEST VAR (defter P14M4-03d, orta; P14M4-03c, düşük):
        eksen kapısının 8×'e kadar KÖR BANDI ölçüldü. Bandın içinde kapı,
        ``bridge.py:177-178``in belgelediği gerçek kusuru — *"aynı motorun
        geometrisi eksik verilerek çağrılan profil 171 mm, konturu 124 mm
        çıkıyor"*, yani kontur boyunun %37,9'u kadar sapma — sessizce kabul
        ediyordu. Depodaki gerçek RED bekçisi profili 500 mm (2,75 × L)
        kaydırıyor: savunduğu kusurdan 7 kat KABA bir uyarıcı.

        Bu bekçi uyarıcıyı kusurun KENDİ ölçüsüne indirir. Ölçüldü
        (2026-08-26, üç motorun üçünde de aynı eşik):

            kaydırma = 0,379032 × L      (konik 47,818 mm / bell 33,092 mm
                                          / varsayılan hibrit 34,069 mm)
            TOL=0,05 (1,0×) → NOT_MODELLED     TOL=0,35 (7,0×) → NOT_MODELLED
            TOL=0,37 (7,4×) → NOT_MODELLED     TOL=0,38 (7,6×) → ok  ← KIRMIZI
            TOL=0,40 (8,0×) → ok               TOL=0,50 (10×)  → ok

        Yani P14'ün kaçan 8× mutasyonu bu bekçiyle kırmızıya döner ve
        duyarlılık 60×'ten 7,6×'e iner. İddia TOL'ü OKUMAZ; kaydırma
        ölçülmüş kusur vakasının oranıdır.
        """
        motor = motor_konik if ad == 'konik' else motor_bell
        profil = analyzer.analyze_axial_profile(motor, n_stations=40)
        z0, z1 = kontur_araligi_mm(motor)
        kaydirma = KUNYE_SAPMA_ORANI * (z1 - z0)
        assert kaydirma > 1.0, kaydirma        # vaka gerçekten kaba olmalı

        kayik = dict(profil)
        kayik['x_mm'] = [x + kaydirma for x in profil['x_mm']]
        sonuc = bridge.extract_thermal_inputs(motor, axial_profile=kayik,
                                              include_chamber=False)
        assert sonuc['status'] == bridge.BRIDGE_STATUS_NOT_MODELLED, (
            '%s: künyenin belgelediği kusur vakası (%.3f mm = kontur boyunun '
            '%%%.1f\'i) KABUL EDİLDİ — başka geometrinin h(z)\'si bu mesh\'e '
            'taşınır. Eksen kapısı gevşetilmiş olabilir '
            '(THERMAL_PROFILE_DOMAIN_TOL).'
            % (ad, kaydirma, 100.0 * KUNYE_SAPMA_ORANI))
        assert 'eksen' in (sonuc.get('reason') or ''), sonuc.get('reason')
        # Kaydırılmamış profil AYNI çağrıda kabul ediliyor: red, kapının
        # topyekûn kapalı olmasından değil eksen uyuşmazlığından geliyor.
        assert bridge.extract_thermal_inputs(
            motor, axial_profile=profil,
            include_chamber=False)['status'] == bridge.BRIDGE_STATUS_OK

    def test_kapi_kunye_vakasindan_sikidir(self):
        """Kapının SAYISI, savunduğu kusur vakasından sıkı kalmalı (ucuz ikiz).

        Yukarıdaki davranış bekçisi zincirin tamamına (``/calculate`` →
        örnekleyici → köprü) bağlıdır; zincir bir gün toplanamaz hâle gelirse
        sessizce kaybolabilir. Bu iddia aynı hükmü fikstürsüz kurar ve
        yalnızca EŞİTSİZLİK sınar: tolerans SIKILAŞTIRILABİLİR (yeşil kalır),
        ölçülmüş kusur vakasının üstüne çıkarılamaz.

        Çapa üründen değil künyeden gelir: ``bridge.py:177-178``in belgelediği
        profil 171 mm / kontur 124 mm vakası → %37,9. Bugün ölçülen pay
        0,379032 / 0,05 = 7,58 kat.
        """
        assert bridge.THERMAL_PROFILE_DOMAIN_TOL < KUNYE_SAPMA_ORANI, (
            'eksen kapısı (%.4f) künyesinde belgelediği kusur vakasının '
            '(%.4f = %.0f mm / %.0f mm) üstüne çıkarılmış: kapı artık kendi '
            'var oluş sebebini kabul ediyor.'
            % (bridge.THERMAL_PROFILE_DOMAIN_TOL, KUNYE_SAPMA_ORANI,
               KUNYE_PROFIL_MM - KUNYE_KONTUR_MM, KUNYE_KONTUR_MM))

    def test_bell_konik_ekseni_gercekten_farkli(self, motor_konik, motor_bell):
        """Bekçinin ANLAMLI olduğunun kanıtı: iki geometri gerçekten ayrı.

        Bu olmasaydı 'bell de geçiyor' cümlesi hiçbir şey ölçmezdi (konik
        varsayımı bell konturuyla zaten çakışıyor olurdu).

        ESKİ HALİ sınırı yine kapının sabitinden türetiyordu
        (``> THERMAL_PROFILE_DOMAIN_TOL * bell_boy``). P14M4-03c bunun
        ÖLÇÜLMÜŞ yan etkisini yazdı: kapı 10× gevşetildiğinde kırmızıya dönen
        TEK test buydu — yani "yakalama" doğru sebepten değildi; bu test
        emniyet gerilemesini değil ÖN KOŞULU ölçer. Sınır artık ölçülen
        farka çapalı (2 kN / 30 bar hibrit, v3.0.1 kamarasıyla: 97,595082 −
        70,919630 = 26,675452 mm, bell boyunun %37,6'sı); kapının gevşemesi bu testte
        artık sahte sinyal üretmez. Kapının gevşemesini ölçen bekçi
        ``test_kopru_kunye_vakasini_reddeder``dir.
        """
        _, konik_boy = kontur_araligi_mm(motor_konik)
        _, bell_boy = kontur_araligi_mm(motor_bell)
        fark = abs(konik_boy - bell_boy)
        assert fark == pytest.approx(KONIK_BELL_FARK_MM, rel=0.05), fark
        assert fark > 0.25 * bell_boy, (fark, bell_boy)


# ======================================================================
# 2) Uçtan uca zincir (üreme noktası + regresyon)
# ======================================================================
class TestUctanUca:
    def _zincir(self, client, motor):
        resp = _quiet(client.post, '/api/analysis/wall-profile',
                      json=panel_govdesi(motor),
                      headers={'Host': '127.0.0.1:8080'})
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        profil = resp.get_json()['wall_profile']
        resp2 = _quiet(client.post, '/api/fea/thermal', json={
            'motor_results': motor,
            'axial_profile': profil,
            'ambient_temperature_K': 293.15,
            'n_axial': 12, 'n_radial': 4, 'max_halvings': 2,
        }, headers={'Host': '127.0.0.1:8080'})
        assert resp2.status_code == 200, resp2.get_data(as_text=True)[:300]
        govde = resp2.get_json()
        return profil, (govde.get('fea') or govde)

    def test_ureme_noktasi_konik_yesil(self, client, motor_konik):
        """2 kN / 30 bar: profil-kontur farkı ölçülmüş tavanda, uç 'ok'.

        Sınır TOL türetmesinden koparıldı (P14M4-03d): uçtan uca zincirde
        ölçülen sapma 0,000000e+00 mm; tavan ``SAPMA_TAVANI_MM``.
        """
        profil, fea = self._zincir(client, motor_konik)
        z0, z1 = kontur_araligi_mm(motor_konik)
        sapma = max(abs(profil['x_mm'][0] - z0), abs(profil['x_mm'][-1] - z1))
        assert sapma <= SAPMA_TAVANI_MM, (
            'profil %.3f mm, kontur %.3f mm, sapma %.6e mm'
            % (profil['x_mm'][-1], z1, sapma))
        assert fea['status'] == bridge.BRIDGE_STATUS_OK, fea.get('reason')

    def test_varsayilan_hibrit_ekseni_bozulmadi(self, client,
                                                motor_varsayilan):
        """Regresyon: çalışan varsayılan hibrit (1 kN / 20 bar) yeşil kalır."""
        profil, fea = self._zincir(client, motor_varsayilan)
        z0, z1 = kontur_araligi_mm(motor_varsayilan)
        assert profil['x_mm'][0] == pytest.approx(z0, abs=1e-6)
        assert profil['x_mm'][-1] == pytest.approx(z1, abs=1e-6)
        assert fea['status'] == bridge.BRIDGE_STATUS_OK, fea.get('reason')

    def test_uc_govdesi_konturu_tasir_bell_yesil(self, client, motor_bell):
        """Parti 25 kapanışı: gövde artık YAYIMLANAN konturu taşıyor.

        Bu bekçi, eski 'açık borç bekçisi'nin (uç gövdesi lüle şeklini
        taşımıyordu, bell motorda köprü dürüstçe reddediyordu) planlı
        halefidir — eski bekçinin docstring'i uç düzeltilince kırmızıya
        dönüp GÜNCELLENMESİNİ şart koşuyordu; düzeltme parti 25'te geldi:
        panel gövdesi + /api/analysis/wall-profile beyaz listesi
        ``nozzle_contour``'u (points) aynen geçiriyor. Ölçülen: kontur
        geçince profil-kontur sapması 0,000 mm (yalnız nozzle_type 38,1 mm,
        tam nozzle_angles 9,7 mm sapıyordu — ikisi de YETMEZ, kilit
        konturdadır).
        """
        profil, fea = self._zincir(client, motor_bell)
        assert 'nozzle_type' not in (profil.get('contour_basis') or {}).get(
            'generic_defaults_used', [])
        z0, z1 = kontur_araligi_mm(motor_bell)
        sapma = max(abs(profil['x_mm'][0] - z0), abs(profil['x_mm'][-1] - z1))
        # Sınır TOL türetmesinden koparıldı (P14M4-03d): docstring'in yazdığı
        # "0,000 mm" ölçümü artık iddianın KENDİSİ.
        assert sapma <= SAPMA_TAVANI_MM, (
            'bell: profil %.3f mm, kontur %.3f mm, sapma %.6e mm'
            % (profil['x_mm'][-1], z1, sapma))
        assert fea['status'] == bridge.BRIDGE_STATUS_OK, fea.get('reason')


# ======================================================================
# 3) Geometri sözlüğünün normalleştirilmesi ve beyanı
# ======================================================================
class TestGeometriBeyani:
    #: Hibrit çözücünün KENDİ çağrısının şeması (hybrid_rocket_engine.py,
    #: lüle malzeme analizi): tip ÜST DÜZEY anahtarda, çıkış çapı yok.
    COZUCU_SEMASI = {
        'chamber_pressure': 30.0,
        'chamber_temperature': 3388.9,
        'chamber_diameter': 0.1019,
        'chamber_length': 0.82,
        'burn_time': 10.0,
        'mdot_total': 0.8416,
        'throat_diameter': 0.02427,
    }

    @pytest.mark.parametrize('tip', ['conical', 'bell', 'parabolic'])
    def test_ust_duzey_nozzle_type_ornekleyiciye_ulasir(self, analyzer, tip):
        """Üst düzey ``nozzle_type`` artık okunur (eskiden hepsi konikti)."""
        md = dict(self.COZUCU_SEMASI, nozzle_type=tip)
        profil = analyzer.analyze_axial_profile(md, n_stations=20)
        assert profil['nozzle_type'] == tip
        assert 'nozzle_type' in profil['contour_basis']['nozzle_type_source']
        assert 'nozzle_type' not in profil['contour_basis'][
            'generic_defaults_used']

    def test_verilmeyen_cikis_capi_beyan_edilir(self, analyzer):
        """Çıkış çapı/genleşme oranı yoksa eksen JENERİKTİR ve söylenir."""
        profil = analyzer.analyze_axial_profile(
            dict(self.COZUCU_SEMASI, nozzle_type='bell'), n_stations=20)
        kunye = profil['contour_basis']
        assert 'exit_diameter' in kunye['generic_defaults_used']
        assert 'NOT GIVEN' in kunye['exit_diameter_source']

    def test_genlesme_orani_verilince_jenerige_dusulmez(self, analyzer):
        """ε verildiğinde çıkış çapı ONDAN türer; jenerik beyan kalkar."""
        profil = analyzer.analyze_axial_profile(
            dict(self.COZUCU_SEMASI, nozzle_type='bell',
                 expansion_ratio=5.2335), n_stations=20)
        kunye = profil['contour_basis']
        assert kunye['generic_defaults_used'] == []
        assert 'expansion_ratio' in kunye['exit_diameter_source']

    def test_sifir_geometri_verilmedi_sayilir(self, analyzer):
        """0 / '' bir ölçü DEĞİLDİR: eski setdefault tuzağı kapalı kalsın.

        ``setdefault`` 0'ı geçerli sayıyordu; örnekleyici de 0'ı sonlu bulup
        boğaz yarıçapını sıfırlıyordu (alan oranı tanımsız).
        """
        md = dict(self.COZUCU_SEMASI)
        md['throat_diameter'] = 0
        md['exit_diameter'] = ''
        profil = analyzer.analyze_axial_profile(md, n_stations=20)
        assert profil['throat_diameter_m'] > 0
        assert np.all(np.isfinite(np.asarray(profil['area_ratio'])))
        assert np.asarray(profil['area_ratio']).min() == pytest.approx(1.0)
        assert 'continuity' in profil['contour_basis'][
            'throat_diameter_source']

    def test_iraksak_boy_kaynagi_yayimlanir(self, analyzer):
        """Boy çözücüden mi geldi türetildi mi — beyan çıktıda taşınır."""
        profil = analyzer.analyze_axial_profile(
            dict(self.COZUCU_SEMASI, nozzle_type='bell',
                 expansion_ratio=5.2335), n_stations=20)
        kaynak = profil['contour_basis']['divergent_length_source']
        assert isinstance(kaynak, str) and kaynak
        # Çözücü boy vermediği için bu şemada türetme beyanı beklenir.
        assert kaynak.startswith('NOT SOLVED') or kaynak.startswith('derived')


# ======================================================================
# 4) Yayımlanan konturun izlenmesi ve bozuk konturun reddi
# ======================================================================
class TestYayimlananKontur:
    def _kontur(self, olcek=1.0, kaydir=0.0):
        """Geçerli (kesin artan, r > 0) sentetik kontur — metre."""
        z = np.array([0.0, 20.0, 40.0, 50.0, 60.0, 90.0, 120.0])
        r = np.array([50.0, 40.0, 20.0, 12.0, 16.0, 24.0, 30.0])
        z = z * olcek + kaydir
        return [[float(zi) / 1000.0, float(ri) / 1000.0]
                for zi, ri in zip(z, r)]

    def _md(self, points):
        return {
            'chamber_pressure': 30.0, 'chamber_temperature': 3300.0,
            'chamber_diameter': 0.10, 'chamber_length': 0.5,
            'burn_time': 10.0, 'mdot_total': 0.84,
            'throat_diameter': 0.024, 'expansion_ratio': 5.0,
            'nozzle_contour': {'points': points},
        }

    def test_profil_yayimlanan_konturu_izler(self, analyzer):
        """Kontur uzarsa eksen de uzar: tercih dekoratif değil, gerçek.

        (Geometri alanları SABİT tutulur; değişen tek şey yayımlanan
        konturdur. Eksen onunla değişiyorsa kaynak gerçekten odur.)
        """
        p1 = analyzer.analyze_axial_profile(
            self._md(self._kontur()), n_stations=20)
        p2 = analyzer.analyze_axial_profile(
            self._md(self._kontur(olcek=1.10)), n_stations=20)
        assert p1['x_mm'][-1] == pytest.approx(120.0)
        assert p2['x_mm'][-1] == pytest.approx(132.0)
        # Boğaz da konturun minimum yarıçapından bulunur (varsayılmaz).
        assert p1['x_throat_mm'] == pytest.approx(50.0)
        assert p2['x_throat_mm'] == pytest.approx(55.0)

    def test_eksen_baslangici_konturdan_okunur(self, analyzer):
        """Kontur z=0'dan başlamıyorsa eksen de başlamaz (0 VARSAYILMAZ)."""
        profil = analyzer.analyze_axial_profile(
            self._md(self._kontur(kaydir=5.0)), n_stations=20)
        assert profil['x_mm'][0] == pytest.approx(5.0)
        assert profil['x_mm'][-1] == pytest.approx(125.0)

    @pytest.mark.parametrize('bozuk,neden', [
        ([[0.0, 0.05], [0.02, 0.012], [0.01, 0.03]], 'z kesin artan değil'),
        ([[0.0, 0.05], [0.02, 0.0], [0.04, 0.03]], 'r <= 0'),
        ([[0.0, 0.05], [0.02, 0.012]], 'nokta sayısı < 3'),
        ([[0.0, 0.05, 1.0], [0.02, 0.012, 1.0], [0.04, 0.03, 1.0]], 'biçim'),
    ])
    def test_bozuk_kontur_canli_ornekleme_ile_degistirilir(self, analyzer,
                                                           bozuk, neden):
        """Bozuk kontur sessizce KABUL EDİLMEZ; canlı örnekleme + gerekçe."""
        profil = analyzer.analyze_axial_profile(self._md(bozuk), n_stations=20)
        kunye = profil['contour_basis']
        assert 'sampled live' in kunye['source'], neden
        assert np.all(np.diff(np.asarray(profil['x_mm'])) > 0)

    def test_bogazsiz_kontur_reddedilir(self, analyzer):
        """İç minimumu olmayan (tek yönlü) kontur boğaz taşımaz → örnekleme."""
        tekduze = [[0.0, 0.012], [0.02, 0.018], [0.04, 0.024],
                   [0.06, 0.030]]
        profil = analyzer.analyze_axial_profile(self._md(tekduze),
                                                n_stations=20)
        assert 'sampled live' in profil['contour_basis']['source']
        assert 'no interior minimum radius' in profil['contour_basis'][
            'source']
