"""ÖH Z5S / P09-C — OpenRocket (.eng / .ork) dışa aktarımının bekçileri.

Sekiz kalem, sekiz sözleşme. Hepsinin ortak ilkesi Z4'te kurulan
**kazanılmış künye** sözleşmesinin ihraç katmanındaki eşleniğidir: dosyanın
yazdığı her iddia ya ölçülmüş bir sayıya dayanır ya da hiç yazılmaz.

  P9B3-10  ``export_motor_summary`` 10 000 N·s / 0 varsayılanlarına düşmez
  P9B3-16  sınıf harfi, çözücünün teslim ettiği impuls ve YAZILAN eğrinin
           integrali üçü birden dosyada durur; sınıf çelişkisi uyarı üretir
  P9B3-17  sınıf tablosunda boşluk yok; tablo dışında harf uydurulmaz
  P9B3-27  negatif itki kenetlemesi sayısıyla BEYAN edilir
  P9B3-18  motor adındaki boşluk RASP satırını bozmaz, değişiklik beyan edilir
  P9B3-20  ".eng"deki "yapısal analiz yok" yalanı bitti
  P9B3-19  apoje yakalanmadıysa ``max_altitude`` apoje diye sunulmaz
  P9B3-15  .ork motor yuvası gövde borusuna sığmıyorsa dosya bunu söyler

Bu dosya P09-C ajanının kendi bekçi dosyasıdır; mevcut bekçi dosyalarına
DOKUNULMAZ (kalemlerin çoğu zaten bekçisizdi, P9B3-17'ninki ise yanlış yeri
kilitliyordu: ``_designation``ı sabitliyor, ``_get_motor_class``
boşluklarını değil).
"""
import json
import math
import os

import pytest

from hrma.export.openrocket_integration import (
    EXPORTER_EXAMPLE_VEHICLE, ORK_BODY_TUBE_WALL_M, OpenRocketExporter,
    _sanitize_motor_name)
from hrma.utils.numeric_compat import trapezoid
from tests.support.kanit import kanit_gerekli

FIXTURE_DIZIN = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'docs', 'scofield', 'raw', 'P09', 'cikti', 'B3')

#: Kapıyı geçen en küçük gerçekçi motor (geometri + kütle + eğri girdileri).
#: Sayılar GİRDİdir, çıktı iddiası değildir.
Z5S_MOTOR = {
    'motor_name': 'Z5S-C',
    'thrust': 1000.0,
    'burn_time': 5.0,
    'total_impulse': 5000.0,
    'isp': 210.0,
    'propellant_mass_total': 2.0,
    'chamber_diameter': 0.10,
    'chamber_length': 0.30,
    'throat_diameter': 0.02,
    'exit_diameter': 0.05,
}

Z5S_ARAC = {'name': 'Z5S-ARAC', 'dry_mass': 12.0, 'diameter': 0.20,
               'length': 2.4, 'drag_coefficient': 0.45}


@pytest.fixture()
def exporter():
    return OpenRocketExporter()


@pytest.fixture(scope='module')
def gercek_kati():
    """Çözücünün GERÇEK katı motor çıktısı (P09 keşif turunun kaydı)."""
    yol = os.path.join(FIXTURE_DIZIN, 'motor_solid.json')
    with open(kanit_gerekli(yol), encoding='utf-8') as f:
        return json.load(f)


def motor_satiri(eng: str):
    for line in eng.splitlines():
        if line and not line.startswith(';'):
            return line
    return None


def veri_satirlari(eng: str):
    return [l for l in eng.splitlines() if l and not l.startswith(';')]


def yorum(eng: str):
    return '\n'.join(l for l in eng.splitlines() if l.startswith(';'))


# ---------------------------------------------------------------------------
# P9B3-10 — özet uydurma varsayılanlara düşmez
# ---------------------------------------------------------------------------

class TestP9B3_10_OzetVarsayilanlari:
    """ÖLÇÜLDÜ (onarım öncesi): ``export_motor_summary({})`` ->
    ``total_impulse=10000, motor_class='M', average_thrust=0, burn_time=0,
    propellant_mass=0``. Aynı istekte .eng yolu kapıyı işletip dosya
    üretmiyordu: tek yanıtın iki ucu çelişiyordu."""

    def test_bos_sozlukte_hicbir_sayi_uydurulmaz(self, exporter):
        ozet = exporter.export_motor_summary({})
        for alan in ('total_impulse', 'motor_class', 'average_thrust',
                     'burn_time', 'specific_impulse', 'propellant_mass',
                     'chamber_pressure', 'of_ratio'):
            assert ozet[alan] is None, f'{alan} uydurma değer taşıyor'
        assert 10000 not in ozet.values()
        assert ozet['designation'].startswith('UNKNOWN-')

    def test_kaynak_alanlari_kunyeyi_kazandiriyor(self, exporter):
        ozet = exporter.export_motor_summary({})
        assert ozet['total_impulse_source'] == 'none'
        assert ozet['average_thrust_source'] == 'none'
        assert ozet['propellant_mass_source'] == 'none'

    def test_ozet_eng_ile_ayni_cozucuden_beslenir(self, exporter):
        """Katı motorda üst seviyede ``thrust`` ve ``propellant_mass_total``
        yok; özet eskiden bu yüzden 0 yazıyordu."""
        data = {k: v for k, v in Z5S_MOTOR.items()
                if k not in ('thrust', 'propellant_mass_total')}
        data['average_thrust'] = 6704.935576774943
        data['propellant_mass'] = 6.468146574659687
        ozet = exporter.export_motor_summary(data)
        assert ozet['average_thrust'] == pytest.approx(6704.935576774943)
        assert ozet['average_thrust_source'] == 'average_thrust'
        assert ozet['propellant_mass'] == pytest.approx(6.468146574659687)
        assert ozet['propellant_mass_source'] == 'propellant_mass'
        # Özetin sınıf harfi .eng adıyla aynı olmalı (tek çözücü).
        assert ozet['designation'].startswith(ozet['motor_class'])

    def test_sinif_harfinin_arali_ozette_yazili(self, exporter):
        ozet = exporter.export_motor_summary(dict(Z5S_MOTOR))
        alt, ust = ozet['motor_class_range_Ns']
        assert alt <= ozet['total_impulse'] <= ust


# ---------------------------------------------------------------------------
# P9B3-17 — sınıf tablosunda boşluk yok
# ---------------------------------------------------------------------------

class TestP9B3_17_SinifBosluklari:
    """ÖLÇÜLDÜ (onarım öncesi): 2,505 / 5,005 / 20 480,005 N·s'nin ÜÇÜ de
    ``'A'`` dönüyordu — 20 kN·s'lik motor 2,5 N·s'lik oyuncakla aynı harfi
    alıyordu."""

    @pytest.mark.parametrize('impulse,beklenen', [
        (2.505, 'B'), (5.005, 'C'), (10.005, 'D'), (20.005, 'E'),
        (40.005, 'F'), (80.005, 'G'), (160.005, 'H'), (320.005, 'I'),
        (640.005, 'J'), (1280.005, 'K'), (2560.005, 'L'), (5120.005, 'M'),
        (10240.005, 'N'), (20480.005, 'O'),
    ])
    def test_araliklarin_arasina_dusen_impuls_A_olmuyor(self, exporter,
                                                        impulse, beklenen):
        assert exporter._get_motor_class(impulse) == beklenen

    def test_tablonun_kendi_araliklari_korunuyor(self, exporter):
        """Onarım tablodaki SAYILARI değiştirmedi: her sınıfın kendi bandı
        hâlâ aynı harfe düşüyor."""
        for harf, (alt, ust) in exporter.motor_classes.items():
            assert exporter._get_motor_class(alt) == harf
            assert exporter._get_motor_class(ust) == harf

    def test_sinif_harfi_impulsla_monoton(self, exporter):
        harfler = [exporter._get_motor_class(v)
                   for v in (1.3, 3.0, 7.0, 15.0, 30.0, 60.0, 120.0)]
        assert harfler == ['A', 'B', 'C', 'D', 'E', 'F', 'G']

    @pytest.mark.parametrize('impulse', [0.0, 1.0, 1.25, -5.0, float('nan'),
                                         float('inf'), None, 'x'])
    def test_tablo_disi_deger_harf_uydurmaz(self, exporter, impulse):
        assert exporter._get_motor_class(impulse) is None

    def test_tablo_ustu_hala_P_arti(self, exporter):
        """Davranış değişmedi: tablo O'da bitiyor, üstü 'P ve üzeri'."""
        assert exporter._get_motor_class(3e6) == 'P+'

    def test_designation_tablo_disinda_harf_basmaz(self, exporter):
        data = dict(Z5S_MOTOR, total_impulse=1.0)
        assert exporter._designation(data).startswith('UNKNOWN-')
        assert not exporter._designation(data).startswith('A')


# ---------------------------------------------------------------------------
# P9B3-16 — teslim edilen impuls + yazılan eğrinin integrali
# ---------------------------------------------------------------------------

class TestP9B3_16_ImpulsDenetimi:
    """ÖLÇÜLDÜ (gerçek hibrit sonucu): başlık 20 000,0 N·s, çözücünün teslim
    ettiği 19 950,385 N·s, dosyaya yazılan eğrinin integrali 19 960,339 N·s.
    ``total_impulse_delivered_Ns`` modülde 0 atıfla duruyordu."""

    def test_teslim_edilen_impuls_artik_okunuyor(self, exporter):
        data = {k: v for k, v in Z5S_MOTOR.items() if k != 'total_impulse'}
        data['total_impulse_delivered_Ns'] = 19950.384563680964
        impulse, source = exporter.resolve_total_impulse(data)
        assert source == 'total_impulse_delivered_Ns'
        assert impulse == pytest.approx(19950.384563680964)

    def test_denetim_yazilan_egrinin_integralini_olcuyor(self, exporter):
        data = dict(Z5S_MOTOR, total_impulse_delivered_Ns=4900.0)
        pts, _src = exporter.resolve_thrust_curve(data)
        audit = exporter.impulse_audit(data, pts)
        bagimsiz = float(trapezoid([p[1] for p in pts], [p[0] for p in pts]))
        assert audit['written_curve_Ns'] == pytest.approx(bagimsiz, rel=1e-12)
        assert audit['header_Ns'] == pytest.approx(5000.0)
        assert audit['delivered_Ns'] == pytest.approx(4900.0)
        assert audit['delivered_percent_vs_header'] == pytest.approx(-2.0)

    def test_eng_ucunu_de_yaziyor(self, exporter):
        data = dict(Z5S_MOTOR, total_impulse_delivered_Ns=4900.0)
        eng = exporter.export_motor_file(data)
        metin = yorum(eng)
        assert '; total impulse (5000.0 N-s' in metin
        assert 'solver-reported delivered impulse = 4900.000 N-s' in metin
        assert 'the thrust curve written below integrates to' in metin
        assert 'class letter L covers' in metin

    def test_sinif_celiskisi_uyari_uretiyor(self, exporter):
        """Başlık L sınıfı diyor, dosyanın altındaki eğri K sınıfı veriyor:
        OpenRocket EĞRİYİ simüle eder, sessiz kalmak yanlış motor demektir."""
        data = dict(Z5S_MOTOR, total_impulse=2600.0, thrust=1000.0,
                    burn_time=2.0)
        audit = exporter.impulse_audit(data)
        assert audit['class_letter_header'] == 'L'
        assert audit['class_letter_written_curve'] == 'K'
        assert audit['class_letters_agree'] is False
        eng = exporter.export_motor_file(data)
        assert 'WARNING: the class letter in the motor name' in eng
        assert 'DIFFERENT class' in eng

    def test_uyumlu_motorda_celiski_uyarisi_cikmiyor(self, exporter):
        """Fazla agresif değil: sayılar tutuyorsa uyarı basılmaz."""
        eng = exporter.export_motor_file(dict(Z5S_MOTOR))
        assert 'DIFFERENT class' not in eng


# ---------------------------------------------------------------------------
# P9B3-27 — negatif itki kenetlemesi beyan edilir
# ---------------------------------------------------------------------------

Z5S_NEGATIF_MOTOR = dict(
    {k: v for k, v in Z5S_MOTOR.items() if k != 'total_impulse'},
    thrust_curve={'time': [0.0, 1.0, 2.0, 3.0, 4.0],
                  'thrust': [0.0, 1000.0, 800.0, -200.0, 0.0]},
)


class TestP9B3_27_NegatifKenetleme:
    """ÖLÇÜLDÜ (gerçek hibrit eğrisinin son 12 örneği negatife çevrildi):
    ham integral 17 631,934 N·s, kenetlenmiş 18 805,534 N·s — dosya farkı
    hiç yazmıyor, kaynağını yine de "integral of the time-resolved thrust
    curve" diye beyan ediyordu."""

    def test_denetim_negatifleri_sayiyor(self, exporter):
        audit = exporter.impulse_audit(Z5S_NEGATIF_MOTOR)
        assert audit['negative_samples'] == 1
        assert audit['most_negative_N'] == pytest.approx(-200.0)
        assert audit['raw_curve_Ns'] == pytest.approx(1600.0)
        assert audit['clamped_curve_Ns'] == pytest.approx(1800.0)
        assert audit['negative_samples_clamped'] is True

    def test_eng_kenetlemeyi_sayisiyla_beyan_ediyor(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_NEGATIF_MOTOR))
        assert 'solved thrust samples are NEGATIVE' in eng
        assert 'the curve below is CLAMPED' in eng
        assert 'raw (unclamped) curve integral = 1600.000 N-s' in eng
        assert 'clamped curve integral = 1800.000 N-s' in eng

    def test_yazilan_egride_negatif_deger_yok(self, exporter):
        """Kenetleme RASP'ın zorunluluğu: sayı değiştirilmedi, beyan eklendi."""
        eng = exporter.export_motor_file(dict(Z5S_NEGATIF_MOTOR))
        for satir in veri_satirlari(eng)[1:]:
            _t, f = (float(x) for x in satir.split())
            assert f >= 0.0

    def test_negatifsiz_egride_uyari_yok(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_MOTOR))
        assert 'NEGATIVE' not in eng


# ---------------------------------------------------------------------------
# P9B3-18 — motor adı RASP satırını bozmaz
# ---------------------------------------------------------------------------

class TestP9B3_18_MotorAdi:
    """ÖLÇÜLDÜ (onarım öncesi): ``'My Motor'`` -> 8 alan, ``'UZAYTEK HRM
    001'`` -> 9 alan, ``'A\\nB'`` -> dosyada başıboş satır + 1 alanlık motor
    satırı."""

    @pytest.mark.parametrize('ad', ['My Motor', 'UZAYTEK HRM 001', 'A\nB',
                                    ' bosluklu ', 'iki  bosluk', 'tab\tayrik'])
    def test_bosluklu_ad_yedi_alani_bozmuyor(self, exporter, ad):
        eng = exporter.export_motor_file(dict(Z5S_MOTOR, motor_name=ad))
        payload = veri_satirlari(eng)
        assert len(payload[0].split()) == 7, payload[0]
        # Motor satırından sonraki her satır iki float olmalı: adın satır
        # sonu içermesi dosyaya başıboş bir satır sokmamalı.
        for satir in payload[1:]:
            t, f = (float(x) for x in satir.split())
            assert math.isfinite(t) and math.isfinite(f)

    @pytest.mark.parametrize('ad,beklenen', [
        ('My Motor', 'My_Motor'), ('A\nB', 'A_B'),
        (' bosluklu ', 'bosluklu'), ('temiz-ad', 'temiz-ad'), (None, ''),
    ])
    def test_ad_temizligi_tek_parcaya_indiriyor(self, ad, beklenen):
        temiz, _beyan = _sanitize_motor_name(ad)
        assert temiz == beklenen
        assert len(temiz.split()) <= 1

    def test_degisen_ad_dosyada_beyan_ediliyor(self, exporter):
        eng = exporter.export_motor_file(
            dict(Z5S_MOTOR, motor_name='My Motor'))
        assert "motor name written as 'My_Motor'" in eng
        assert "'My Motor'" in eng          # kullanıcının yazdığı ad da durur

    def test_dokunulmayan_ad_beyan_uretmiyor(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_MOTOR))
        assert 'motor name written as' not in eng


# ---------------------------------------------------------------------------
# P9B3-20 — "yapısal analiz yok" yalanı
# ---------------------------------------------------------------------------

Z5S_YAPISAL_KUTLESIZ = dict(
    Z5S_MOTOR,
    structural_analysis={
        'case_analysis': {'wall_thickness_mm': 4.65,
                          'safety_factor': 2.1},
        'grain_structural': {'status': 'ok'},
    },
)


class TestP9B3_20_YapisalBeyan:
    """ÖLÇÜLDÜ (gerçek katı ve sıvı sonuçları): ``.eng`` "no structural
    analysis in this export" yazıyordu; oysa yapısal analiz VAR (katıda
    case_analysis + grain_structural, sıvıda chamber_structure) ve cidar bile
    çözülüyor (4,65 mm / 2,00 mm). Eksik olan ANALİZ değil, KÜTLE."""

    def test_yanlis_beyan_bitti(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_YAPISAL_KUTLESIZ))
        assert 'no structural analysis in this export' not in eng

    def test_uyari_hala_var_ve_eksigi_dogru_adlandiriyor(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_YAPISAL_KUTLESIZ))
        assert 'WARNING: loaded mass EXCLUDES motor case mass' in eng
        assert 'a structural analysis IS present in this result' in eng
        assert 'case_analysis' in eng
        assert 'what is missing is the total mass' in eng
        assert 'case wall thickness of 4.65 mm' in eng

    def test_gercekten_yapisal_yoksa_bunu_soyluyor(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_MOTOR))
        assert 'carries no structural analysis block either' in eng
        assert 'a structural analysis IS present' not in eng

    def test_aranan_alanlar_dosyada_adiyla_yazili(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_MOTOR))
        for alan in OpenRocketExporter.INERT_MASS_SEARCH_PATH:
            assert alan in eng

    def test_kutle_cozulunce_uyari_hic_cikmiyor(self, exporter):
        eng = exporter.export_motor_file(dict(Z5S_YAPISAL_KUTLESIZ,
                                              dry_mass=4.0))
        assert 'WARNING: loaded mass EXCLUDES' not in eng
        assert 'a structural analysis IS present' not in eng

    def test_gercek_kati_sonucta_da_dogru(self, exporter, gercek_kati):
        md = dict(gercek_kati, motor_name='Z5S-KATI')
        eng = exporter.export_motor_file(md)
        assert 'no structural analysis in this export' not in eng
        assert 'a structural analysis IS present in this result' in eng


# ---------------------------------------------------------------------------
# P9B3-19 — apoje penceresi
# ---------------------------------------------------------------------------

class TestP9B3_19_ApojePenceresi:
    """ÖLÇÜLDÜ (gerçek katı motor + 12 kg araç): pencere 0..15,267 s, tepe SON
    adımda (599/599), son adımdaki dikey hız hâlâ +111,81 m/s. Yani
    ``max_altitude`` = 4958,50 m tırmanışın kesildiği nokta; aynı entegrasyon
    sürdürülünce apoje 5465,86 m (t = 25,10 s)."""

    def test_kesilen_pencerede_max_altitude_apoje_diye_sunulmuyor(
            self, exporter, gercek_kati):
        fp = exporter.generate_flight_profile(dict(gercek_kati),
                                              dict(Z5S_ARAC))
        assert fp['velocity_data'][-1] > 0.0, 'ölçüm koşulu: hâlâ tırmanıyor'
        assert fp['apogee_status'] == 'reached_after_window'
        assert fp['max_altitude_is_apogee'] is False
        assert fp['apogee_altitude'] > fp['max_altitude']
        assert fp['apogee_time'] > fp['flight_time']
        assert 'NOT the apogee' in fp['max_altitude_method']

    def test_apoje_ayni_entegrasyondan_geliyor(self, exporter, gercek_kati):
        """Apoje UYDURULMUYOR: adım sayısı ve süresi pencerenin dt'siyle
        tutarlı olmalı (yeni bir model değil, aynı çözümün devamı)."""
        fp = exporter.generate_flight_profile(dict(gercek_kati),
                                              dict(Z5S_ARAC))
        dt = fp['time_data'][-1] - fp['time_data'][-2]
        beklenen = fp['flight_time'] + fp['apogee_continuation_steps'] * dt
        assert fp['apogee_time'] == pytest.approx(beklenen, rel=1e-9)
        assert 0 < fp['apogee_continuation_steps'] <= \
            OpenRocketExporter.APOGEE_CONTINUATION_MAX_STEPS

    def test_pencerede_yakalanan_apoje_max_altitude_ile_ayni(self, exporter):
        # Ağır araç: apoje pencerenin İÇİNDE kalıyor (ölçüldü: son adımda
        # hız -29,45 m/s, yani araç çoktan alçalıyor).
        fp = exporter.generate_flight_profile(dict(Z5S_MOTOR),
                                              dict(Z5S_ARAC, dry_mass=40.0))
        assert fp['velocity_data'][-1] <= 0.0
        assert fp['apogee_status'] == 'reached_in_window'
        assert fp['max_altitude_is_apogee'] is True
        assert fp['apogee_altitude'] == pytest.approx(fp['max_altitude'])
        assert 'NOT the apogee' not in fp['max_altitude_method']

    def test_kalkamayan_arac_ucus_gibi_sunulmuyor(self, exporter):
        """İtki ağırlığı yenemiyorsa irtifa serisi bir uçuş değildir."""
        fp = exporter.generate_flight_profile(
            dict(Z5S_MOTOR, thrust=5.0, total_impulse=25.0),
            dict(Z5S_ARAC, dry_mass=500.0))
        assert fp['apogee_status'] == 'no_liftoff'
        assert fp['max_altitude'] == pytest.approx(0.0)
        assert 'never leaves the pad' in fp['max_altitude_method']

    def test_veri_yoksa_apoje_alanlari_da_bos_doner(self, exporter):
        fp = exporter.generate_flight_profile({'propellant_mass_total': 2.0})
        assert fp['status'] == 'insufficient_data'
        assert fp['apogee_altitude'] is None
        assert fp['apogee_status'] == 'not_computed'
        assert fp['max_altitude_is_apogee'] is False


# ---------------------------------------------------------------------------
# P9B3-15 — .ork motor yuvası gövde borusuna sığıyor mu
# ---------------------------------------------------------------------------

class TestP9B3_15_YuvaGovdeKapisi:
    """ÖLÇÜLDÜ (üç gerçek sonuç, araçsız istek): yuva yarıçapı 0,0623 /
    0,0822 / 0,0747 m, gövde borusunun iç yarıçapı 0,0450 m — üçü de
    sığmıyor ve şablonda bunu söyleyen tek satır yok."""

    def test_ornek_aractan_buyuk_motor_beyan_ediliyor(self, exporter):
        buyuk = dict(Z5S_MOTOR, chamber_diameter=0.16, chamber_length=0.4)
        xml = exporter.create_ork_project_template(buyuk)
        assert 'THE MOTOR DOES NOT FIT THE BODY TUBE' in xml
        assert 'the mount sticks out by' in xml
        assert 'EXAMPLE vehicle bundled with the exporter' in xml

    def test_sigan_motorda_olcum_yaziliyor_uyari_yok(self, exporter):
        xml = exporter.create_ork_project_template(
            dict(Z5S_MOTOR), dict(Z5S_ARAC, diameter=0.30))
        assert 'motor mount FITS the body tube' in xml
        assert 'DOES NOT FIT' not in xml

    def test_kullanicinin_araci_ornek_diye_gecistirilmiyor(self, exporter):
        xml = exporter.create_ork_project_template(
            dict(Z5S_MOTOR, chamber_diameter=0.25), dict(Z5S_ARAC))
        assert 'THE MOTOR DOES NOT FIT THE BODY TUBE' in xml
        assert 'the body tube above is YOUR vehicle' in xml
        assert 'EXAMPLE vehicle bundled' not in xml

    def test_olcum_govde_borusunun_kendi_kalinligini_kullaniyor(self, exporter):
        """Tek tanım noktası: XML'e yazılan et kalınlığı ile kapının
        kullandığı kalınlık aynı sayı olmalı (CLAUDE.md kural 11)."""
        arac = dict(Z5S_ARAC, diameter=0.30)
        xml = exporter.create_ork_project_template(dict(Z5S_MOTOR), arac)
        assert f'<thickness>{ORK_BODY_TUBE_WALL_M}</thickness>' in xml
        fit = exporter.motor_mount_fit(0.05, arac, {'diameter': 'request'})
        assert fit['body_tube_wall_m'] == ORK_BODY_TUBE_WALL_M
        assert fit['body_tube_inner_radius_m'] == pytest.approx(
            0.15 - ORK_BODY_TUBE_WALL_M)
        assert fit['fits'] is True

    def test_capi_cozulemeyen_aracta_kapi_iddia_uretmiyor(self, exporter):
        fit = exporter.motor_mount_fit(0.05, {'diameter': None}, {})
        assert fit['fits'] is None
        assert exporter._motor_mount_fit_notes(fit)[0].startswith(
            'motor mount fit NOT checked')

    def test_ornek_arac_capi_kapinin_referansiyla_ayni(self, exporter):
        """Kapı, şablonun gerçekten yazdığı gövdeyi ölçmeli."""
        xml = exporter.create_ork_project_template(dict(Z5S_MOTOR))
        yaricap = EXPORTER_EXAMPLE_VEHICLE['diameter'] / 2.0
        assert f'<outerradius>{yaricap}</outerradius>' in xml
        assert f'{yaricap - ORK_BODY_TUBE_WALL_M:.4f} m' in xml
