# -*- coding: utf-8 -*-
"""ÖH D24 / app-api aşama-1 bekçileri.

Kapsanan kalemler
-----------------
* **P16B3-13** — ``/api/flow-analysis``: ``n_stations`` sessizce
  kelepçelenmez, ``wall_temperature`` gazdan sıcak olamaz.
* **P16B3-12** — ``/api/water-hammer``: cidar ≥ iç yarıçap geometrisinde
  emniyet hükmü YAYIMLANMAZ.
* **P16B3-11** — aynı uçta ``pipe_mawp_bar`` ezmesi UNSAFE hükmünü SAFE'e
  ÇEVİREMEZ (kalem başlığı ölçümle çürütüldü; bekçi geri dönüşü kilitler).
* **P16B3-08** — ``/api/uncertainty-analysis``: ``n_samples`` üst sınırlı.
* **P16B3-10** — 6DOF büyüklük kapısı (kalem başlığı çürütüldü; bekçi
  ``stable``/``apogee``ın geri çekildiğini kilitler).

Her testin ölçümü ``docs/scofield/raw/OH/D24/app-api/a1/`` altındadır
(``once.json`` / ``sonra.json``).
"""
import pytest

from hrma.app import app
from hrma.analysis.nozzle_flow_1d import N_STATIONS_MIN, N_STATIONS_MAX
from hrma.analysis.uncertainty import LEVEL_BUDGETS
from hrma.analysis.trajectory_analysis import LAUNCH_CONDITION_BANDS


@pytest.fixture()
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ÖH D32 / arayuz-panel a2 (OH-D31-14): zorunlu altı alanın eksik üçü
# (gamma, molecular_weight, ambient_pressure) tabana eklendi. Değerler ucun
# KANONİK tablosundan (``FLOW_ANALYSIS_DEFAULTS``) alındı, yani bu dosyanın
# hiçbir sayısı değişmedi — eskiden aynı üç sayı sessizce varsayılıyordu,
# artık gövde onları açıkça söylüyor. Kalemin konusu (istasyon bandı, cidar
# sıcaklığı) ETKİLENMEDİ.
AKIS_TEMEL = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'gamma': 1.2, 'molecular_weight': 24.0, 'ambient_pressure': 101325.0,
    'throat_diameter': 0.02, 'expansion_ratio': 4.0, 'fidelity': 'fast',
}

SU_KOCU_TEMEL = {
    'fluid': 'water', 'line_length_m': 10.0, 'line_id_mm': 20.0,
    'wall_thickness_mm': 1.5, 'working_pressure_bar': 50.0,
    'flow_velocity_m_s': 8.0, 'pipe_material': 'ss_304',
    'valve_closure_time_ms': 5.0,
}

UQ_GIRDI = {'thrust': 1000, 'burn_time': 10, 'chamber_pressure': 20,
            'of_ratio': 6.0}

ALTI_DOF_TEMEL = {
    'body_diameter': 0.1, 'body_length': 2.0, 'nose_length': 0.3,
    'dry_mass': 20.0, 'propellant_mass': 10.0, 'cd0': 0.5,
    'thrust': 5000.0, 'burn_time': 5.0, 'rail_length': 5.0,
}


# --------------------------------------------------------------- P16B3-13
class TestP16B313AkisKapilari:
    """Ölçüm (once.json): ``n_stations`` −5 / 0 / 1e6 üçü de HTTP 200 ve
    tam istasyon dizisi; çözücü değeri [30, 60] aralığına SESSİZCE
    kelepçeliyordu. ``wall_temperature = 1e9`` K de 200 dönüyordu.
    """

    @pytest.mark.parametrize('deger', [-5, 0, 1, N_STATIONS_MIN - 1,
                                       N_STATIONS_MAX + 1, 1000000])
    def test_bant_disi_istasyon_sayisi_reddedilir(self, istemci, deger):
        y = istemci.post('/api/flow-analysis',
                         json=dict(AKIS_TEMEL, fidelity='engineering',
                                   n_stations=deger))
        assert y.status_code == 400, (
            f'n_stations={deger} kabul edildi — çözücü onu sessizce '
            f'[{N_STATIONS_MIN}, {N_STATIONS_MAX}] aralığına kelepçeler')
        g = y.get_json()
        alanlar = g.get('invalid_fields') or []
        assert any(a.get('field') == 'n_stations' for a in alanlar), (
            'ret ALANI adıyla anmıyor: ' + repr(g))
        assert any(a.get('accepted_range') == [N_STATIONS_MIN, N_STATIONS_MAX]
                   for a in alanlar), 'kabul edilen bant yayımlanmıyor'

    @pytest.mark.parametrize('deger', [N_STATIONS_MIN, 45, N_STATIONS_MAX])
    def test_bant_ici_istasyon_sayisi_kabul(self, istemci, deger):
        y = istemci.post('/api/flow-analysis',
                         json=dict(AKIS_TEMEL, fidelity='engineering',
                                   n_stations=deger))
        assert y.status_code == 200, (
            f'n_stations={deger} bandın İÇİNDE ama reddedildi — kapı '
            'sağlıklı envanteri daraltmış')

    def test_istasyon_alani_gonderilmezse_davranis_degismez(self, istemci):
        y = istemci.post('/api/flow-analysis',
                         json=dict(AKIS_TEMEL, fidelity='engineering'))
        assert y.status_code == 200

    def test_cidar_gazdan_sicak_olamaz(self, istemci):
        y = istemci.post('/api/flow-analysis',
                         json=dict(AKIS_TEMEL, wall_temperature=1e9))
        assert y.status_code == 400, (
            'cidar 1e9 K, oda 3000 K — taşınım akısı q = h(T_aw - T_w) '
            'işaret değiştirir, bu bir lüle cidarı değildir')
        alanlar = y.get_json().get('invalid_fields') or []
        assert any(a.get('field') == 'wall_temperature'
                   and a.get('reason') == 'wall_hotter_than_gas'
                   for a in alanlar)

    def test_cidar_gazdan_soguksa_kabul(self, istemci):
        y = istemci.post('/api/flow-analysis',
                         json=dict(AKIS_TEMEL, wall_temperature=800.0))
        assert y.status_code == 200

    def test_cidar_alt_ucu_hala_kapali(self, istemci):
        """Çözücünün kendi '> 0' kapısı sökülmedi (ölçüm: -500 -> 400)."""
        y = istemci.post('/api/flow-analysis',
                         json=dict(AKIS_TEMEL, wall_temperature=-500.0))
        assert y.status_code == 400


# --------------------------------------------------------------- P16B3-12
class TestP16B312SuKocuGeometrisi:
    """Ölçüm (once.json): ID = 20 mm hattında cidar 10 / 20 / 50 mm'nin
    ÜÇÜ de HTTP 200 + ``status: SAFE`` veriyordu. Hükmün dayandığı
    ince-cidar hoop bağıntısı (P = sigma_y·t/r) o bölgede sınırsız büyür.
    """

    @pytest.mark.parametrize('cidar_mm', [10.0, 12.0, 20.0, 50.0])
    def test_cidar_ic_yaricapi_asarsa_hukum_yayimlanmaz(self, istemci,
                                                        cidar_mm):
        y = istemci.post('/api/water-hammer',
                         json=dict(SU_KOCU_TEMEL,
                                   wall_thickness_mm=cidar_mm))
        assert y.status_code == 422, (
            f'cidar {cidar_mm} mm >= iç yarıçap 10 mm iken hüküm '
            'yayımlandı')
        g = y.get_json()
        assert 'water_hammer' not in g, 'reddedilen koşumdan sonuç sızmış'
        alanlar = g.get('invalid_fields') or []
        assert any(
            a.get('field') == 'wall_thickness_mm'
            and a.get('reason') == 'wall_thickness_at_or_above_inner_radius'
            for a in alanlar), repr(g)

    @pytest.mark.parametrize('cidar_mm', [0.5, 1.5, 3.0, 9.9])
    def test_gercek_hatlar_hala_hukum_aliyor(self, istemci, cidar_mm):
        """ÖK-22: sağlıklı envanter daraltılmadı — t/r_i = 0,15 olan depo
        örneği dahil, iç yarıçapın ALTINDAKİ her cidar hüküm alır."""
        y = istemci.post('/api/water-hammer',
                         json=dict(SU_KOCU_TEMEL,
                                   wall_thickness_mm=cidar_mm))
        assert y.status_code == 200, (
            f'cidar {cidar_mm} mm iç yarıçapın altında ama reddedildi')
        assert y.get_json()['water_hammer']['status'] in (
            'SAFE', 'MARGINAL', 'UNSAFE')


# --------------------------------------------------------------- P16B3-11
class TestP16B311MawpEzmesiHukmuCeviremez:
    """Kalem başlığı ÇÜRÜTÜLDÜ (ölçüm, once.json): ``pipe_mawp_bar``
    ezmesi UNSAFE hükmünü SAFE'e çevirmiyor — modül etkin dayanımı
    ``min(verilen MAWP, hoop akma)`` alıyor (ÖH D15 / P4B4-03). Bu bekçi
    o kapının geri sökülmesini kırmızıya çevirir.
    """

    def test_unsafe_kosum_ezmeyle_safe_olmuyor(self, istemci):
        # Yüksek hız + ani kapanma: tepe basınç hoop akmayı aşar.
        agir = dict(SU_KOCU_TEMEL, flow_velocity_m_s=60.0,
                    wall_thickness_mm=0.4, working_pressure_bar=80.0)
        agir.pop('valve_closure_time_ms', None)
        ezmesiz = istemci.post('/api/water-hammer', json=agir)
        assert ezmesiz.status_code == 200
        h0 = ezmesiz.get_json()['water_hammer']['status']
        if h0 != 'UNSAFE':
            pytest.skip(f'taban hüküm UNSAFE değil ({h0}); bu bekçi yalnız '
                        'UNSAFE -> SAFE çevrilmesini kilitler')
        ezmeli = istemci.post('/api/water-hammer',
                              json=dict(agir, pipe_mawp_bar=1e6))
        assert ezmeli.status_code == 200
        h1 = ezmeli.get_json()['water_hammer']['status']
        assert h1 == 'UNSAFE', (
            f'pipe_mawp_bar ezmesi hükmü {h0} -> {h1} yaptı; anma sınıfı '
            'modellenen cidarın akma basıncının üstünde sertifika veremez')

    def test_akmanin_ustundeki_sinif_adiyla_uyariliyor(self, istemci):
        y = istemci.post('/api/water-hammer',
                         json=dict(SU_KOCU_TEMEL, pipe_mawp_bar=1e6))
        assert y.status_code == 200
        wh = y.get_json()['water_hammer']
        metin = ' '.join(str(u) for u in (wh.get('warnings') or []))
        assert 'pipe_mawp_bar' in metin and 'ABOVE' in metin, (
            'akmanın üstündeki basınç sınıfı sessizce kabul edildi')


# --------------------------------------------------------------- P16B3-08
class TestP16B308OrnekSayisiTavani:
    """Ölçüm (once.json): ``n_samples`` üst sınırsızdı — ``level: 'fast'``
    ile 1e9 örnek isteyen eşzamanlı istek sonda kapağında (30 s) hâlâ
    koşuyordu. ``inputs: {}`` ayağı tabanda ZATEN kapalıydı (422).
    """

    @pytest.mark.parametrize('n', [1000000000, 100000, 3001])
    def test_mutlak_tavan(self, istemci, n):
        y = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast',
                               'inputs': UQ_GIRDI, 'n_samples': n})
        assert y.status_code == 400, f'n_samples={n} kabul edildi'
        alanlar = y.get_json().get('invalid_fields') or []
        assert any(a.get('field') == 'n_samples' for a in alanlar)

    @pytest.mark.parametrize('n', [1, 0, -5])
    def test_alt_uc_ucta_kapali(self, istemci, n):
        y = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast',
                               'inputs': UQ_GIRDI, 'n_samples': n})
        assert y.status_code == 400

    def test_es_zamanli_butce_asilamaz(self, istemci):
        n = LEVEL_BUDGETS['engineering'] + 1
        y = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast',
                               'inputs': UQ_GIRDI, 'n_samples': n})
        assert y.status_code == 400
        assert (y.get_json().get('error')
                == 'n_samples_above_synchronous_budget')

    def test_tavan_LEVEL_BUDGETS_ten_okunur(self, istemci):
        """Tek kaynak: tavan uçta İKİNCİ KEZ yazılmadı, tablodan okunur.

        Ölçüt kod metni değil DAVRANIŞtır: tablonun en yüksek bütçesi
        kabul edilir, bir fazlası edilmez. Tablo değişirse kapı onunla
        birlikte kayar; sabit kopyalanmış olsaydı kaymazdı.
        """
        import inspect
        from hrma import app as app_modulu
        kaynak = inspect.getsource(app_modulu.uncertainty_analysis)
        assert "_LEVELS['high_fidelity']" in kaynak, (
            'tavan LEVEL_BUDGETS yerine elle yazılmış')
        tavan = LEVEL_BUDGETS['high_fidelity']
        asiri = istemci.post('/api/uncertainty-analysis',
                             json={'motor_type': 'hybrid',
                                   'level': 'high_fidelity',
                                   'inputs': UQ_GIRDI,
                                   'n_samples': tavan + 1})
        assert asiri.status_code == 400
        alanlar = asiri.get_json().get('invalid_fields') or []
        assert any(a.get('accepted_range') == [2, tavan] for a in alanlar), (
            'yayımlanan bant LEVEL_BUDGETS ile aynı değil')

    def test_girdisiz_istek_hala_reddediliyor(self, istemci):
        """Kalemin ilk ayağı tabanda kapalıydı; sökülmediğini kilitler."""
        for govde in ({'motor_type': 'hybrid', 'level': 'fast',
                       'inputs': {}},
                      {'motor_type': 'hybrid', 'level': 'fast'}):
            y = istemci.post('/api/uncertainty-analysis', json=govde)
            assert y.status_code == 422


# --------------------------------------------------------------- P16B3-10
class TestP16B310AltiDofBuyuklukKapisi:
    """Kalem başlığı ÇÜRÜTÜLDÜ (ölçüm, once.json): itki 1e9 N ve rüzgâr
    1e9 m/s koşumlarında ``stable`` artık ``true`` DEĞİL. Bekçi o kapıların
    sökülmesini kırmızıya çevirir.

    ÖH D25 fix-23 — KAPI SAYISI İKİ, YERLERİ AYRI (ölçüldü, 8f30b6d):
      * ``wind_speed`` bir ATIŞ KOŞULUDUR ve bandı
        ``LAUNCH_CONDITION_BANDS``tadır (D24 termo-ucus a2, P4B3-16); uç
        isteği HİÇ BAŞLATMADAN 422 verir — kardeş 2B ucuyla aynı tablodan.
      * ``thrust`` için böyle bir atış-koşulu bandı yoktur; hükmü ÖH D15 /
        P7B1-09 aerodinamik bant kapısı çözümden SONRA geri çeker (200 +
        ``aero_model_out_of_band``, ``stable``/``apogee`` = null).
    """

    @pytest.mark.parametrize('ek', [{'thrust': 1e9}])
    def test_bant_disi_kosumda_hukum_geri_cekilir(self, istemci, ek):
        """Koşum BAŞLIYOR ama hüküm yayımlanmıyor (aerodinamik bant kapısı).

        ÖH D25 fix-23 — VAKA AYRIŞTI (ölçüldü, taban 8f30b6d). Bu satır
        ``wind_speed = 1e9``u da buraya parametreliyordu ve 200 bekliyordu;
        D24 termo-ucus a2 (``d386a4a``, P4B3-16) atış koşulu bantlarını TEK
        KAYNAĞA (``LAUNCH_CONDITION_BANDS``) bağlayınca rüzgâr artık UCUN
        GİRİŞİNDE 422 ile reddediliyor. İki kapı da hükmü geri çekiyor ama
        AYNI ŞEY DEĞİLLER ve tek testte toplanamazlar: rüzgâr kapısı
        entegrasyon HİÇ BAŞLAMADAN konuşur (fail-closed, aşağıdaki test),
        itki için böyle bir bant yoktur ve hükmü çözümden SONRA aerodinamik
        bant geri çeker. Beklenti gevşemedi, İKİYE AYRILDI: 200 yolu burada,
        422 yolu aşağıda ölçülüyor.
        """
        y = istemci.post('/api/six-dof-analysis',
                         json=dict(ALTI_DOF_TEMEL, **ek))
        assert y.status_code == 200
        ozet = (y.get_json() or {}).get('summary') or {}
        if not ozet:
            pytest.skip('uç özet yayımlamadı; kapı ayrı yolda')
        assert ozet.get('aero_model_out_of_band') is True, (
            'aerodinamik bant kapısı ateşlemedi: ' + repr(sorted(ozet)))
        assert ozet.get('stable') is None, (
            "ışık hızı mertebesindeki koşuma 'kararlı' damgası basıldı")
        assert ozet.get('apogee') is None, 'apoje hükmü yayımlandı'

    def test_ruzgar_bandi_kosumu_hic_baslatmadan_reddediyor(self, istemci):
        """1e9 m/s "rüzgâr" bir atış koşulu değildir: 422, hüküm YOK.

        ÖLÇÜLDÜ (8f30b6d): yanıt 422 + ``invalid_fields`` ve alan adı
        ``wind_speed``. Bant SAYI OLARAK KOPYALANMAZ; tablodan okunur, yani
        ``LAUNCH_CONDITION_BANDS`` değişirse bu bekçi onunla birlikte kayar.
        """
        y = istemci.post('/api/six-dof-analysis',
                         json=dict(ALTI_DOF_TEMEL, wind_speed=1e9))
        assert y.status_code == 422, (
            'ışık hızı mertebesinde bir "rüzgâr" ile koşum başlatıldı')
        govde = y.get_json() or {}
        alanlar = govde.get('invalid_fields') or []
        ruzgar = [a for a in alanlar if a.get('field') == 'wind_speed']
        assert ruzgar, ('reddin gerekçesi alan adıyla yayımlanmadı: '
                        + repr(alanlar))
        alt, ust = LAUNCH_CONDITION_BANDS['wind_speed'][:2]
        # ÖH D27 a2 / OH-D25-23 — BEKÇİ ÇEVRİLDİ ve SIKILDI. Bu satır
        # kusurun kendisiydi: tüketici bandı okumak için İKİ anahtarı
        # da denemek zorundaydı. Ad tek kanona indi; hoşgörü kalkıyor,
        # çünkü hoşgörü ayrışmanın geri gelmesini SESSİZ kılardı.
        assert 'allowed_range' not in ruzgar[0], (
            'eski bant adı geri geldi: %r' % (ruzgar[0],))
        bant = ruzgar[0].get('accepted_range')
        assert bant == [alt, ust], (
            'yayımlanan bant tek kaynakla aynı değil: %r != %r'
            % (bant, [alt, ust]))
        # Reddedilen istekten hiçbir hüküm sızmaz.
        assert 'summary' not in govde, 'red yanıtında özet hükmü var'

    def test_iki_uc_ayni_ruzgara_ayni_hukmu_veriyor(self, istemci):
        """P4B3-16'nın ürünü: 2B ve 6-DOF uçları tek tablodan besleniyor.

        Aynı büyüklük iki uca gönderildiğinde ikisi de reddetmeli; D24
        öncesinde 6-DOF 200, 2B 422 veriyordu (``a2/once.json`` K2).
        """
        alti = istemci.post('/api/six-dof-analysis',
                            json=dict(ALTI_DOF_TEMEL, wind_speed=1e9))
        iki_b = istemci.post('/api/trajectory-analysis',
                             json={'motor_type': 'hybrid',
                                   'thrust': 5000.0, 'burn_time': 5.0,
                                   'propellant_mass': 10.0,
                                   'dry_mass': 20.0,
                                   'body_diameter': 0.15,
                                   'wind_speed': 1e9})
        assert alti.status_code == iki_b.status_code == 422, (
            'iki uç aynı rüzgâra farklı hüküm verdi: 6DOF=%s, 2B=%s'
            % (alti.status_code, iki_b.status_code))

    def test_saglikli_kosum_hukum_almaya_devam_ediyor(self, istemci):
        y = istemci.post('/api/six-dof-analysis', json=dict(ALTI_DOF_TEMEL))
        assert y.status_code == 200
        ozet = (y.get_json() or {}).get('summary') or {}
        assert ozet.get('aero_model_out_of_band') is not True
        assert ozet.get('apogee') is not None


def _kap_blogu(govde):
    """``/calculate_solid`` yanıtındaki basınçlı kap bloğunu bulur.

    Yanıt kabuğu sürümler arasında (``results`` sarmalı olan/olmayan)
    değişebiliyor; bekçi kabuğa değil BLOĞA bakar.
    """
    for kok in (govde.get('results'), govde):
        if isinstance(kok, dict):
            press = ((kok.get('safety_analysis') or {})
                     .get('pressure_safety'))
            if isinstance(press, dict):
                return press
    raise AssertionError('pressure_safety bloğu yanıtta yok: '
                         + repr(sorted(govde))[:200])


KATI_TEMEL = {'motor_type': 'solid', 'propellant_type': 'apcp',
              'chamber_diameter': 100.0, 'grain_length': 300.0,
              'core_diameter': 40.0, 'chamber_pressure': 20.0}


# --------------------------------------------------------------- P16B3-07
class TestP16B307GecicianalizMotorKimligi:
    """Ölçüm (once.json): boş gövde ayağı tabanda ZATEN kapalıydı
    (400 + 0 sayısal yaprak). Ayakta kalan ayak ``motor_type``ın
    YUTULMASIYDI: ``solid`` / ``liquid`` / ``peynir`` üçünün de yanıtı
    ``motor_type: 'hybrid'`` diye yankılıyordu.
    """

    @pytest.mark.parametrize('tip', ['solid', 'liquid', 'peynir', 'HYBRIDX'])
    def test_cozulmeyen_motor_kimligi_reddedilir(self, istemci, tip):
        y = istemci.post('/api/transient-analysis', json={'motor_type': tip})
        assert y.status_code == 422, (
            f'motor_type={tip!r} hibrit çözücüyle yanıtlandı')
        g = y.get_json()
        assert g.get('error') == 'unsupported_motor_type'
        assert g.get('motor_type') != 'hybrid', (
            'reddedilen istek yine "hybrid" diye etiketlendi')
        alanlar = g.get('invalid_fields') or []
        assert any(a.get('field') == 'motor_type' for a in alanlar)

    def test_bos_govde_hala_sayi_uretmiyor(self, istemci):
        """Kalemin ilk ayağı (D15/P7B1-03) sökülmedi."""
        y = istemci.post('/api/transient-analysis', json={})
        assert y.status_code == 400
        assert 'time' not in (y.get_json() or {})

    def test_hybrid_ve_alansiz_yol_degismedi(self, istemci):
        """Kapı yalnız GÖNDERİLMİŞ ve çözülemeyen kimliği reddeder."""
        for govde in ({}, {'motor_type': 'hybrid'}):
            y = istemci.post('/api/transient-analysis', json=govde)
            assert y.status_code == 400, (
                'kapı hibrit/alansız yolu da yutmuş: ' + repr(govde))
            assert (y.get_json() or {}).get('error') != (
                'unsupported_motor_type')


# --------------------------------------------------------------- P16B2-06
class TestP16B206KasaCidariTekKapi:
    """Kalem başlığı ÇÜRÜTÜLDÜ (ölçüm, once.json): ``case_thickness``
    alanında İKİ kapı yok, TEK kapı var; NaN/inf/liste/sözlük künyesi
    ``user_supplied`` DEĞİL. Ölçülen imzalar::

        6 mm      -> user_supplied         / ok         / PASS
        0,05 mm   -> user_value_not_applied/ ok         / NOT_EVALUATED
        NaN, inf  -> user_value_not_applied/ not_finite / NOT_EVALUATED
        liste,    -> user_value_not_applied/ unreadable / NOT_EVALUATED
        sözlük,
        True, 'abc'

    Bu bekçi künyenin ``user_supplied``a geri dönmesini kırmızı yapar.
    """

    # V301/K-A (KT-06/KT-13; ana model kararı 3) — TERS KAPIYA ÇEVRİLDİ.
    # Okunamayan / bant dışı cidar eskiden 200 ile "kullanılmadı" künyesi ve
    # geri çekilen hükümle YAYIMLANIYORDU (cidarı HRMA boyutluyordu). Artık
    # tasarım hiç yayımlanmaz: 422 input_not_accepted, alan + gerekçe kodu
    # ADIYLA. Asıl iddia (kullanılmayan değer kullanıcının cidarı diye
    # sunulmaz) daha güçlü biçimde korunur: hiçbir cidar sunulmaz.
    @pytest.mark.parametrize('deger,beklenen_durum', [
        (float('nan'), 'not_finite'),
        (float('inf'), 'not_finite'),
        ([1, 2], 'not_a_number'),
        ({'a': 1}, 'not_a_number'),
        (True, 'boolean_is_not_a_number'),
        ('abc', 'not_a_number'),
        (0.05, 'out_of_accepted_range'),
    ])
    def test_okunamayan_cidar_user_supplied_kunyesi_almaz(
            self, istemci, deger, beklenen_durum):
        y = istemci.post('/calculate_solid',
                         json=dict(KATI_TEMEL, case_thickness=deger))
        assert y.status_code == 422, y.get_data(as_text=True)[:300]
        g = y.get_json()
        assert g['error_code'] == 'input_not_accepted'
        assert 'structural_analysis' not in g and 'safety_analysis' not in g
        kayit = [k for k in g['invalid_fields']
                 if k['field'] == 'case_thickness']
        assert kayit, g['invalid_fields']
        assert kayit[0]['reason'] == beklenen_durum, (
            'girdi durumu ADIYLA ayrışmıyor — iki farklı ret aynı '
            'künyeye çökmüş')

    def test_gecerli_cidar_hala_dogrulaniyor(self, istemci):
        y = istemci.post('/calculate_solid',
                         json=dict(KATI_TEMEL, case_thickness=6.0))
        assert y.status_code == 200
        press = _kap_blogu(y.get_json())
        assert press['wall_thickness_source'] == 'user_supplied'
        assert press['wall_thickness_input_status'] == 'ok'
        assert press['vessel_status_is_tautological'] is False
