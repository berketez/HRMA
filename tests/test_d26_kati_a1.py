# -*- coding: utf-8 -*-
"""ÖH D26 / katı aşama-1 bekçileri — defter P15B3-02 (YÜKSEK).

Kalem: *katıda "zarf tutmuyor" rejiminde itki/süre ATIL: eşik aşımında DAHA
ÇOK isteyen DAHA AZ alıyor.*

ÖLÇÜLDÜ (``docs/scofield/raw/OH/D26/kati/a1/once.json``, taban 7751531;
gövde Ø100 / çekirdek 35 / tane 300 mm BATES, APCP, 40 bar, 3 s — Fable-D19'un
RET gerekçesindeki gövde, D25 app-api a4 ölçümünden devralındı):

* İstek 20 / 50 / 100 / 150 / 200 / 250 N → ALTISINDA DA HTTP 200 ve
  ``average_thrust = 1930,475099292884 N``, ``burn_time = 4,479165439800482 s``,
  boğaz ``24,089628036183527 mm``. Altı farklı istek TEK bir yanıt üretiyordu
  (ayırt edici yanıt sayısı 1/6): 20 N isteyen, istediğinin 96,5 katını
  "sonuç" diye alıyordu.
* Zarfın hemen ötesinde yön TERSİNE dönüyordu: istek 250 N → teslim
  1930,475 N; istek 300 N → teslim 282,146 N. Yani +%20 istek, −%85,38
  teslim.
* Süre ekseninde de aynı atalet: 8 / 12 / 20 / 30 s istekleri bit-özdeş
  yanıt veriyordu (ayırt edici yanıt 2/5).

ONARIM (fail-closed, Doktrin 1): tasarım noktası hedefi tutturulamadığında
motor durumu YAPISAL olarak bildirir
(``design_point.status = 'design_point_not_reached'``) ve ``/calculate_solid``
hüküm YAYIMLAMAZ: HTTP 422, hangi büyüklüğün zarfı ne kadar aştığı adıyla
(``design_point.exceeded``), ulaşılabilir sınırlar ``design_point.envelope``
içinde. Başlangıç geometrisinin eğrisi yanıta KONMAZ — o eğri isteğin cevabı
değildir.

SONRA (``sonra.json``, aynı gövde): rejimde 0 × 200 / 6 × 422, ayırt edici
yanıt 6/6, süre ekseninde 5/5, yön tersinmesi YOK. Zarfın TUTTUĞU her nokta
(289 / 290 / 300 / 350 / 400 / 450 / 500 / 2500 / 2580 N) ile hedefsiz
geometri kipi ve uç-yanmalı sağlıklı koşu BİT-AYNI kaldı.
"""
import contextlib
import io
import json

import pytest

from hrma.app import app
from hrma.engines.solid_rocket_engine import (
    DESIGN_POINT_REASON_BATES_ENVELOPE,
    DESIGN_POINT_REASON_END_BURNER_ENVELOPE,
    DESIGN_POINT_REASON_UNSUPPORTED_GRAIN,
    DESIGN_POINT_STATUS_NOT_REACHED,
    DESIGN_STATUS_TARGET_NOT_MET,
)

#: Ölçüm gövdesi — ``docs/scofield/raw/OH/D26/kati/a1/olcum.py`` ile BİREBİR.
KATI_TABAN = {
    'motor_type': 'solid', 'engine_type': 'solid',
    'chamber_pressure': 40, 'burn_time': 3,
    'propellant_type': 'APCP',
    'chamber_diameter': 100, 'core_diameter': 35,
    'grain_length': 300, 'chamber_length': 300,
    'grain_type': 'bates',
}

#: Tabanda ALTISI DA bit-özdeş yanıt veren istekler (once.json).
ZARF_DISI_ITKILER = (20, 50, 100, 150, 200, 250)

#: Tabanda yayımlanan atıl üçlü — bu sayılar artık HİÇBİR zarf-dışı
#: yanıtta görünmemelidir.
TABAN_ATIL_ITKI = 1930.475099292884
TABAN_ATIL_SURE = 4.479165439800482

#: Hedefsiz geometri kipinin BUGÜNKÜ itkisi. ÖH KİTAP p1b (B11, §28-36
#: Ş-3): taban itkisi (yukarıda, tarihsel atıl üçlünün parçası olarak
#: korunur) geri çözülmüş APCP dörtlüsündendi; CEA denge dörtlüsüyle ölçülen
#: yeni taban. Yanma süresi değişmedi (TABAN_ATIL_SURE aynen geçerli).
HEDEFSIZ_GEOMETRI_ITKI = 1946.6898189765143


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(client, **ek):
    govde = dict(KATI_TABAN)
    govde.update(ek)
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            cevap = client.post('/calculate_solid', json=govde)
    return cevap.status_code, (cevap.get_json() or {})


def _imza(kod, govde):
    """Yanıtın İSTEKLE değişip değişmediğinin imzası (olcum.py ile aynı)."""
    return json.dumps(
        [kod, govde.get('average_thrust'), govde.get('burn_time'),
         govde.get('throat_diameter'), govde.get('error')],
        sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# 1) Zarf dışı hedefte HÜKÜM YAYIMLANMAZ
# ---------------------------------------------------------------------------
class TestZarfKapisiFailClosed:

    def test_zarf_disi_hedef_hukum_yayimlamaz(self, client):
        """20 N / 3 s BATES: taban 200 + 1930,475 N veriyordu; artık 422."""
        kod, govde = _post(client, thrust=20)
        assert kod == 422, kod
        assert govde['status'] == DESIGN_STATUS_TARGET_NOT_MET
        # Hüküm YOK: başlangıç geometrisinin eğrisi yanıta girmez.
        for alan in ('average_thrust', 'max_thrust', 'total_impulse',
                     'burn_time', 'throat_diameter', 'specific_impulse'):
            assert alan not in govde, alan
        dp = govde['design_point']
        assert dp['status'] == DESIGN_POINT_STATUS_NOT_REACHED
        assert dp['reason'] == DESIGN_POINT_REASON_BATES_ENVELOPE
        assert dp['achieved'] is False and dp['sizing_applied'] is False
        assert dp['verdict_withheld'] is True
        assert dp['requested_average_thrust_N'] == pytest.approx(20.0)

    def test_taban_atil_sayilari_artik_yayimlanmiyor(self, client):
        """1930,475 N / 4,479165 s hiçbir zarf-dışı yanıtta görünmemeli.

        ÖH KİTAP p1b 3. tur (karar §28-47, denetim Ş2-7): APCP kaydı CEA
        dörtlüsüne geçince (§28-36 Ş-3) atıl üçlünün itki yarısı hiçbir yolun
        üretemeyeceği bir sayıya dönüştü; gerileme olursa yayımlanacak itki
        bugünkü hedefsiz geometri itkisidir (HEDEFSIZ_GEOMETRI_ITKI). İkisi
        birden sınanır."""
        for itki in ZARF_DISI_ITKILER:
            kod, govde = _post(client, thrust=itki)
            assert kod == 422, (itki, kod)
            duz = json.dumps(govde, default=str)
            assert repr(TABAN_ATIL_ITKI) not in duz, itki
            assert repr(HEDEFSIZ_GEOMETRI_ITKI) not in duz, itki
            assert repr(TABAN_ATIL_SURE) not in duz, itki

    def test_zarf_disi_yanit_istekle_gercekten_degisir(self, client):
        """ATALET ölçümü: altı farklı istek altı farklı yanıt üretmeli.

        Taban: 1/6 (bit-özdeş). Bu bekçi kalemin tam gövdesini sınar.
        """
        imzalar = {_imza(*_post(client, thrust=T)) for T in ZARF_DISI_ITKILER}
        assert len(imzalar) == len(ZARF_DISI_ITKILER), len(imzalar)

    def test_sure_ekseninde_de_atalet_yok(self, client):
        """8 / 12 / 20 / 30 s tabanda bit-özdeşti (ayırt edici 2/5)."""
        imzalar = {_imza(*_post(client, thrust=1500, burn_time=t))
                   for t in (3, 8, 12, 20, 30)}
        assert len(imzalar) == 5, len(imzalar)

    def test_daha_cok_isteyen_daha_az_almaz(self, client):
        """Eşiğin iki yanı: yayımlanan itki istekle ters yönde gitmemeli.

        Taban: 250 N -> 1930,475 N ⟷ 300 N -> 282,146 N (−%85,38).
        """
        teslimler = []
        for T in (250, 300):
            kod, govde = _post(client, thrust=T)
            teslimler.append((T, kod, govde.get('average_thrust')))
        yayimlanan = [(T, F) for T, _k, F in teslimler if F is not None]
        for (T1, F1), (T2, F2) in zip(yayimlanan, yayimlanan[1:]):
            assert not (T2 > T1 and F2 < F1), teslimler


# ---------------------------------------------------------------------------
# 2) Gerekçe ADIYLA ve MİKTARIYLA verilir — ve gerçekten uygulanabilir
# ---------------------------------------------------------------------------
class TestZarfGerekcesi:

    def test_asim_adiyla_ve_miktariyla_bildirilir(self, client):
        kod, govde = _post(client, thrust=20)
        assert kod == 422
        asimlar = {a['field']: a for a in govde['design_point']['exceeded']}
        assert 'thrust' in asimlar, asimlar
        itki = asimlar['thrust']
        assert itki['bound_kind'] == 'minimum'
        assert itki['requested'] == pytest.approx(20.0)
        assert itki['feasible_bound'] > itki['requested']
        assert itki['exceeded_by'] == pytest.approx(
            itki['feasible_bound'] - itki['requested'])
        assert itki['exceeded_by_pct'] > 0
        assert govde['fields'], govde['fields']
        # Hata METNİ de alanı ve miktarı taşımalı (otomatik istemci JSON'u,
        # insan metni okur; ikisi AYNI şeyi söylemeli).
        assert 'thrust' in govde['error']

    def test_duyurulan_zarf_siniri_gercekten_cozulebilir(self, client):
        """Sınır bir tahmin değil: %1 üstünde motor GERÇEKTEN boyutlanmalı."""
        _kod, govde = _post(client, thrust=20)
        zarf = govde['design_point']['envelope']
        f_min = zarf['min_average_thrust_N']
        assert f_min is not None and f_min > 0
        kod2, govde2 = _post(client, thrust=f_min * 1.01)
        assert kod2 == 200, (f_min, kod2, govde2.get('error'))
        assert govde2['design_point']['sizing_applied'] is True

    def test_uyari_kayitlari_dilsiz_kalir(self, client):
        """Reddin gerekçesi backend'de {code, params, severity} kalır."""
        _kod, govde = _post(client, thrust=20)
        kayit = govde['error_i18n']
        assert set(kayit) == {'code', 'params', 'severity'}
        assert kayit['code'] == 'warn.solid.bates_envelope'
        kodlar = {k['code'] for k in govde['design_warnings']
                  if isinstance(k, dict) and 'code' in k}
        assert 'warn.solid.bates_envelope' in kodlar


# ---------------------------------------------------------------------------
# 3) Kapı SAĞLIKLI yolu boğmaz (regresyon çapası)
# ---------------------------------------------------------------------------
class TestSaglikliYolDegismedi:

    @pytest.mark.parametrize('itki,beklenen_hedef', [
        (300.0, 300.0),
        (1500.0, 1500.0),
        (2500.0, 2500.0),
    ])
    def test_zarf_tutan_hedef_yayimlanir(self, client, itki, beklenen_hedef):
        kod, govde = _post(client, thrust=itki)
        assert kod == 200, govde.get('error')
        dp = govde['design_point']
        assert dp['achieved'] is True and dp['sizing_applied'] is True
        assert 'status' not in dp
        assert dp['requested_average_thrust_N'] == pytest.approx(
            beklenen_hedef)
        assert govde['average_thrust'] > 0

    def test_hedefsiz_geometri_kipi_kapiya_takilmaz(self, client):
        """Tasarım noktası HİÇ istenmediyse davranış bit-aynı kalır."""
        govde_g = dict(KATI_TABAN)
        govde_g.pop('burn_time')
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                cevap = client.post('/calculate_solid', json=govde_g)
        assert cevap.status_code == 200
        govde = cevap.get_json()
        assert govde.get('design_point') is None
        # once.json/sonra.json: hedefsiz geometri kipi bit-aynı.
        assert govde['average_thrust'] == pytest.approx(HEDEFSIZ_GEOMETRI_ITKI)
        assert govde['burn_time'] == pytest.approx(TABAN_ATIL_SURE)


# ---------------------------------------------------------------------------
# 4) Aynı sessizliğin öteki iki dalı
# ---------------------------------------------------------------------------
class TestHedefinDusurulduguOtekiDallar:

    def test_desteklenmeyen_tane_ailesinde_hedef_sessizce_dusmez(self, client):
        """star / finocyl / slotted / wagon_wheel: taban BAYT BAYT aynıydı.

        Ölçüldü (taban 7751531): ``grain_type='star'`` ile 20 N ve 250 N
        istekleri aynı sha16'yı (8152cfd30fbd) veriyordu ve yanıtta
        ``design_point`` HİÇ yoktu — hedefin okunup atıldığı yalnız uyarı
        listesinden anlaşılabiliyordu.
        """
        imzalar = set()
        for tane in ('star', 'finocyl', 'slotted', 'wagon_wheel'):
            for T in (20, 250):
                kod, govde = _post(client, grain_type=tane, thrust=T)
                assert kod == 422, (tane, T, kod)
                dp = govde['design_point']
                assert dp['status'] == DESIGN_POINT_STATUS_NOT_REACHED
                assert dp['reason'] == DESIGN_POINT_REASON_UNSUPPORTED_GRAIN
                assert dp['envelope']['grain_family'] == tane
                imzalar.add(_imza(kod, govde))
        assert len(imzalar) == 8, len(imzalar)

    def test_end_burner_zarfinin_UST_ucu_da_kapali(self, client):
        """900 kN / 3 s: taban 276,49 N / 36,93 s yayımlıyordu (200)."""
        kod, govde = _post(client, grain_type='end_burner', thrust=900000)
        assert kod == 422, kod
        dp = govde['design_point']
        assert dp['reason'] == DESIGN_POINT_REASON_END_BURNER_ENVELOPE
        zarf = dp['envelope']
        assert zarf['max_average_thrust_N'] is not None
        assert zarf['max_average_thrust_N'] < 900000
        asim = {a['field']: a for a in dp['exceeded']}['thrust']
        assert asim['bound_kind'] == 'maximum'
        assert asim['exceeded_by'] > 0

    def test_end_burner_zarf_ici_bit_ayni(self, client):
        """Uç-yanmalı sağlıklı koşu (20 N / 3 s) değişmedi."""
        kod, govde = _post(client, grain_type='end_burner', thrust=20)
        assert kod == 200
        assert govde['average_thrust'] == pytest.approx(20.0, rel=1e-9)
        assert govde['design_point']['achieved'] is True


# ---------------------------------------------------------------------------
# 5) Kapı SIRASI — yakınsamayan koşum kapısı bu kapının ÖNÜNDE kalmalı
# ---------------------------------------------------------------------------
class TestKapiSirasi:
    """ÖH D26: zarf kapısı, ÖH D22 / P16B2-05 kapısını GÖLGELEMEZ.

    Zarf kapısı ilk yazıldığında hesabın ÖNÜNE konmuştu ("çözülemeyecek
    hedef için tam koşum yapma"). Ölçüldü: bu sıralama
    ``tests/test_d22_app_api_a2.py::TestP16B2_05CozulemeyenHesap422``
    testlerini kırıyordu (taban 7751531'de YEŞİL). Sebep: ``burn_rate_n=1,0``
    gövdesinde İKİ durum birden doğru — çözücü yakınsamıyor VE hedef zarfın
    dışında. Kapı önde olunca yanıt ``TARGET_NOT_MET`` diye sınıflanıyor ve
    ``solver_diagnostics`` / ``burn_rate_inputs`` tanı alanları redde
    kayboluyordu (ÖK-22: kazanılmış davranış gevşetilemez).

    Kural: iki durum çakışırsa DAHA ÖZGÜL olan kazanır — çözücü hiç
    yakınsamadıysa söylenecek şey "zarf tutmadı" değil, "çözüm yok".
    """

    #: D22'nin gövdesiyle aynı rejim: çözücü yakınsamaz (n = 1,0).
    YAKINSAMAYAN = {'burn_rate_n': 1.0, 'burn_rate_a': 0.005}

    def test_yakinsamayan_kosum_zarf_kapisina_yakalanmaz(self, client):
        kod, govde = _post(client, thrust=20, **self.YAKINSAMAYAN)
        assert kod == 422, kod
        assert govde['status'] == 'NOT_CONVERGED', govde['status']
        # D22'nin kazanımı: ret bilgi SİLMEZ.
        for alan in ('error', 'solver_diagnostics', 'burn_rate_inputs'):
            assert alan in govde, alan

    def test_zarf_reddi_tohum_cozumunun_tanisini_sizdirmaz(self, client):
        """``solver_diagnostics`` bilerek taşınmaz: içinde atıl süre var.

        Tanıyı korumak adına hükmü sızdırmak, hükmü yayımlamanın kılık
        değiştirmiş hâlidir: ``solver_diagnostics['burn_time_s']`` tam da
        tabanda yayımlanan 4,479165439800482 s'dir.
        """
        kod, govde = _post(client, thrust=20)
        assert kod == 422
        assert 'solver_diagnostics' not in govde
        # İsteğe ait tanı ise KORUNUR (ret bilgi silmez).
        assert 'burn_rate_inputs' in govde

    def test_zarf_reddi_hala_kendi_gerekcesini_verir(self, client):
        """Sıra değişikliği zarf reddinin gövdesini bozmadı."""
        kod, govde = _post(client, thrust=20)
        assert kod == 422
        assert govde['status'] == DESIGN_STATUS_TARGET_NOT_MET
        assert govde['design_point']['reason'] == (
            DESIGN_POINT_REASON_BATES_ENVELOPE)
        assert govde['design_point']['exceeded']
