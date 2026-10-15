# -*- coding: utf-8 -*-
"""ÖH Dalga-16 · katı motor · aşama 1 — sekiz onarımın bekçisi.

Her sınıf TEK bir kalemi tutar ve kalemin ONARIMDAN ÖNCEKİ davranışını
reddeder; onarım geçici olarak geri alındığında (ters mutasyon) kırmızıya
döner. Ölçüm dosyaları: ``docs/scofield/raw/OH/D16/kati/a1/once.json`` ve
``sonra.json``; üreten betik aynı dizindeki ``olcum.py``, ters-mutasyon
kanıtı ``mutasyon.py`` / ``mutasyon.txt``.

Kapsanan kalemler:
  OH-Z5-03  katı motor güvertenin okuduğu ``heat_transfer_analysis``ı yayımlar
  P2B2-13   shapely yoksa star/wagon_wheel FAIL-CLOSED (kaba sayı uydurmaz)
  P2B2-14   kaynaksız 'pressure plateau' çarpanı yok; Saint-Robert künyesi doğru
  P2B3-04   maliyetin yakıt kütlesi grain tipini görür (tek kaynak)
  P2B3-05   maliyetin yalıtım kütlesi kullanıcının kalınlığını görür
  P16B4-06  /api/detailed-cad/solid boş çizimi 'success' diye yayımlamaz
  P14M4-06  /calculate_solid kırpma künyesi (clamped/uncapped/basis) bekçili
  P13S1-02  solid.html çekirdek ipucu ölçülen eğilimle çelişmez
  P13B1-02  katı ürün uçlarının boş-gövde kapıları (adlandırılmış 422)
"""

import io
import json
import os
import re
import warnings

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# ÖH D24 · OH-D23-09 — MONOTONLUK İDDİASININ YÖNÜ
#
# Eski bekçi (bu dosyada :490) şunu yazıyordu::
#
#     assert 'monoton' in parca or 'not monotonic' in parca
#
# ``'monoton'`` ``'monotonic'``in ALT DİZESİDİR, yani metin tam TERS şeyi
# ("the trend is monotonic") söylese de iddia geçiyordu — fail-open.
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D24/bekci-cevirisi/a1/once_ohd23_09.json):
# olumsuzlama sökülmüş metin 2/2 yolda eski iddiadan geçiyor.
#
# Aşağıdaki sınıflandırıcı alt-dize saymaz, İDDİANIN YÖNÜNÜ okur: kökün her
# geçişi olumsuzlayıcı bir komşusu var mı diye sınanır (İngilizce önek
# ``not/non/never/no``, Türkçe sonek ``değil``). Hüküm fail-closed'dur:
# tanınmayan bağlam OLUMLU sayılır, yani bekçi şüphede kırmızıya döner.
# ---------------------------------------------------------------------------

#: 'monoton', 'monotonic', 'monotonik', 'monotonluk' … hepsini yakalar.
MONOTON_KOKU = re.compile(r'monoton\w*', re.IGNORECASE)
#: İngilizce olumsuzlayıcı, kökten HEMEN önce (araya noktalama girebilir).
_ONEK_OLUMSUZ = re.compile(r'\b(not|non|never|no)\b[\s\-]*$', re.IGNORECASE)
#: Türkçe olumsuzlayıcı, kökten HEMEN sonra ('monoton değil').
_SONEK_OLUMSUZ = re.compile(r'^[\s\-]*(değil|degil)\b', re.IGNORECASE)


def monotonluk_iddialari(parca):
    """Metindeki her monotonluk geçişini yönüne göre ayırır.

    Döner: ``(olumlu, olumsuz)`` — her biri geçişin çevresini taşıyan
    dizge listesi. ``olumlu`` BOŞ DEĞİLSE metin monotonluk VAAT ediyor
    demektir; ölçüm monoton olmadığı için bu bir çelişkidir.
    """
    olumlu, olumsuz = [], []
    for m in MONOTON_KOKU.finditer(parca):
        onceki = parca[max(0, m.start() - 24):m.start()]
        sonraki = parca[m.end():m.end() + 16]
        cevre = parca[max(0, m.start() - 40):m.end() + 40]
        if _ONEK_OLUMSUZ.search(onceki) or _SONEK_OLUMSUZ.search(sonraki):
            olumsuz.append(cevre)
        else:
            olumlu.append(cevre)
    return olumlu, olumsuz


from hrma.app import app as flask_app
from hrma.engines.solid_rocket_engine import (
    SOLID_COST_PARAMS,
    SOLID_PROPELLANT_COST_FAMILY,
    SOLID_THERMAL,
    SolidRocketEngine,
)
from hrma.engines import solid_rocket_engine as sre

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TABAN = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100, grain_length=500,
             core_diameter=30, chamber_pressure=40)

UC_TABAN = dict(motor_name='D16-KATI', propellant_type='apcp',
                grain_type='bates', chamber_pressure=40.0, thrust=5000.0,
                burn_time=3.0, chamber_diameter=100.0, grain_length=500.0,
                core_diameter=30.0, expansion_ratio=8.0)


def _motor(**kw):
    p = dict(TABAN)
    p.update(kw)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return SolidRocketEngine(**p)


def _sessiz(fn, *a, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def kati_yanit(client):
    r = client.post('/calculate_solid', json=dict(UC_TABAN))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


# ---------------------------------------------------------------------------
# OH-Z5-03 — güverte ısı haritasının veri kanalı katıda AÇIK
# ---------------------------------------------------------------------------
class TestKatiIsiAktarimBloguYayimlanir:
    """ÖLÇÜLDÜ (once.json OH-Z5-03): ``/calculate_solid`` yanıtında
    ``heat_transfer_analysis`` YOKTU; ``motor_viz3d.js:1843`` kapısı
    (``if (gas.throat_heat_flux)``) null döndüğü için güverte ısı düğmesi
    GİZLENİYORDU. Blok artık Bartz zincirinin KENDİ sayılarını yayımlar."""

    def test_blok_yayimlanir_ve_guverte_kapisi_acilir(self, kati_yanit):
        ht = kati_yanit.get('heat_transfer_analysis')
        assert ht is not None, 'heat_transfer_analysis bloğu yayımlanmıyor'
        assert ht.get('status') == 'modelled', ht.get('reason')
        gas = ht['gas_side_analysis']
        # Güvertenin OKUDUĞU tam alan adları (motor_viz3d readHeat):
        q_t = gas.get('throat_heat_flux')
        q_c = gas.get('chamber_heat_flux')
        assert isinstance(q_t, float) and np.isfinite(q_t) and q_t > 0, q_t
        assert isinstance(q_c, float) and np.isfinite(q_c) and q_c > 0, q_c
        # Boğaz akısı hazneden BÜYÜK olmalı (Bartz A_t/A bağımlılığı).
        assert q_t > q_c, (q_t, q_c)

    def test_akilar_cozucunun_kendi_bartz_zincirinden_gelir(self, kati_yanit):
        """Blok YENİ FİZİK yazmaz: boğaz akısı ``_calculate_heat_flux``ın
        birebir kW/m² -> W/m² çevrimidir. Sayı bağımsız bir yerden
        gelirse (yeniden hesap, sabit, ölçek hatası) test kırmızıya döner."""
        # (a) AYNI yanıtın içinde iki blok AYRIŞAMAZ: thermal_analysis
        # kW/m², heat_transfer_analysis W/m², kaynak tek.
        yayimlanan = kati_yanit['heat_transfer_analysis'][
            'gas_side_analysis']['throat_heat_flux']
        kw = (kati_yanit['thermal_analysis']['heat_transfer']
              ['convective_heat_flux_kw_m2'])
        assert yayimlanan == pytest.approx(kw * 1000.0, rel=1e-12)
        # (b) Motor katmanında da aynı özdeşlik: blok kendi Bartz'ını
        # yeniden hesaplamaz, _calculate_heat_flux'ı çevirir.
        e = _motor()
        beklenen = float(_sessiz(e._calculate_heat_flux)) * 1000.0
        ht = _sessiz(e._build_heat_transfer_analysis)
        assert ht['gas_side_analysis']['throat_heat_flux'] == pytest.approx(
            beklenen, rel=1e-12)

    def test_ic_cidar_sicakligi_varsayim_oldugu_icin_yayimlanmaz(
            self, kati_yanit):
        """FAIL-CLOSED: Bartz referans cidarı (700 K) bir TASARIM DEĞERİdir.
        ``inner_temperature`` alanına yazılırsa güverte efsanesi onu
        ÖLÇÜLMÜŞ cidar sıcaklığı gibi basar (sıvı motorun Z5-C5 kapısıyla
        aynı ilke)."""
        wall = kati_yanit['heat_transfer_analysis']['wall_analysis']
        assert wall['inner_temperature'] is None
        assert wall['wall_temperature_solved'] is False
        assert wall['wall_temperature_status'] == 'inner_not_solved'
        assert wall['wall_temperature_withheld_reason']
        # Referans değer GİZLENMEZ, adı konmuş ayrı bir alanda durur.
        assert wall['bartz_reference_wall_temperature_K'] == pytest.approx(
            float(SOLID_THERMAL['bartz_reference_wall_temp_k']))

    def test_aki_cozulemezse_blok_NOT_MODELLED_doner(self):
        """Kapının ikinci yarısı: sayı yoksa uydurulmaz ve
        ``throat_heat_flux`` KONMAZ (güverte düğmesi kapalı kalır)."""
        e = _motor()

        def _patlat():
            raise RuntimeError('bartz zinciri çözülemedi')

        e._calculate_heat_flux = _patlat
        e._chamber_gas_side = _patlat
        ht = _sessiz(e._build_heat_transfer_analysis)
        assert ht['status'] == 'NOT_MODELLED'
        assert 'throat_heat_flux' not in ht['gas_side_analysis']
        assert 'throat_heat_flux' in ht['reason']


# ---------------------------------------------------------------------------
# P2B2-13 — shapely yoksa star/wagon_wheel FAIL-CLOSED
# ---------------------------------------------------------------------------
class TestShapelysizStarWagonSayiUydurmaz:
    """ÖLÇÜLDÜ (once.json P2B2-13, aynı geometri): shapely yokken
    wagon_wheel Isp 1276,3 s ve toplam impuls 6,08 kat; star 1,33 kat.
    Uyarı yalnız ``warnings.warn`` ile veriliyordu, YANITA GİRMİYORDU
    (``yanit_uyarisi_var: false``). Artık finocyl/slotted ile aynı kapı."""

    @pytest.fixture
    def shapelysiz(self):
        eski = sre.SHAPELY_AVAILABLE
        sre.SHAPELY_AVAILABLE = False
        try:
            yield
        finally:
            sre.SHAPELY_AVAILABLE = eski

    @pytest.mark.parametrize('gtip', ['star', 'wagon_wheel'])
    def test_yanan_alan_kaba_yaklasiklik_uretmez(self, shapelysiz, gtip):
        e = _motor(grain_type=gtip)
        with pytest.raises(RuntimeError) as hata:
            _sessiz(e.calculate_burn_area, 0.001)
        assert gtip in str(hata.value)
        assert 'shapely' in str(hata.value)

    @pytest.mark.parametrize('gtip', ['star', 'wagon_wheel'])
    def test_yakit_hacmi_de_ayni_kapiyi_gorur(self, shapelysiz, gtip):
        """Kütle korunumunun İKİ tarafı aynı geometriden gelmek zorunda:
        eskiden hacim yolu star'ı BATES annulusuna, wagon_wheel'i
        çakışmasız 7-daireye düşürüyordu."""
        e = _motor(grain_type=gtip)
        with pytest.raises(RuntimeError):
            _sessiz(e._propellant_volume_uncached)

    @pytest.mark.parametrize('gtip', ['bates', 'end_burner'])
    def test_kapali_form_tipleri_etkilenmez(self, shapelysiz, gtip):
        """Kapalı-form modeli GERÇEKTEN olan tipler shapely'siz de çalışır —
        kapı gereğinden geniş atılmadı."""
        e = _motor(grain_type=gtip)
        assert _sessiz(e.calculate_burn_area, 0.001) > 0
        assert _sessiz(e._propellant_volume_uncached) > 0


# ---------------------------------------------------------------------------
# P2B2-14 — kaynaksız 'pressure plateau' çarpanı yok
# ---------------------------------------------------------------------------
class TestPlateauCarpaniSaintRobertiEzmez:
    """ÖLÇÜLDÜ (once.json P2B2-14): 150 bar'da r_ürün/r_SaintRobert 0,99648;
    300 bar'da 0,99046 — oysa yayımlanan künye "single-exponent
    Saint-Robert law ... with the coefficients supplied" diyor. Üstelik
    çarpan KAYNAKLI parçalı yasanın (Nakka rejim tablosu) üstüne de
    biniyordu: kndx @150 bar 0,01582196 -> 0,01576624 m/s."""

    @pytest.mark.parametrize('pc', [40.0, 120.0, 150.0, 300.0, 500.0])
    def test_yayimlanan_kunye_yanma_hiziyla_bire_bir(self, pc):
        e = _motor(chamber_pressure=pc if pc <= 110 else 100)
        # Referans sıcaklıkta ve erozyonsuz (mass_flux=0) çağrıda ürünün
        # döndürdüğü hız KÜNYE'nin söylediği yasadan bit-aynı olmalı.
        e.mass_flux = 0.0
        beklenen = float(e.a * (pc ** e.n))
        assert e.burn_rate(pc) == pytest.approx(beklenen, rel=1e-15), pc

    def test_parcali_yasa_kendi_tablosunu_verir(self):
        """Plateau/mesa rejimi TEK ve KAYNAKLI yoldan gelir. Kaynaksız
        çarpan geri konursa bu eşitlik 0,99648 çarpanıyla bozulur."""
        from hrma.data import burn_rate_db as brdb
        e = _motor(propellant_type='kndx', chamber_pressure=100)
        yasa = getattr(e, 'burn_rate_law_key', None)
        assert yasa, 'kndx parçalı yasası etkin değil — kalem adresi kaydı'
        e.mass_flux = 0.0
        beklenen = brdb.burn_rate_mmps(yasa, 150.0 / 10.0) / 1000.0
        assert e.burn_rate(150.0) == pytest.approx(beklenen, rel=1e-15)

    def test_100_bar_altinda_davranis_degismedi(self):
        """Çarpan zaten 100 bar altında 1,0 idi — söküm oradaki sayıları
        kaydırmamalı (regresyon çapası)."""
        e = _motor()
        e.mass_flux = 0.0
        assert e.burn_rate(40.0) == pytest.approx(
            float(e.a * (40.0 ** e.n)), rel=1e-15)


# ---------------------------------------------------------------------------
# P2B3-04 / P2B3-05 — maliyet kütleleri analiz zinciriyle AYNI kaynaktan
# ---------------------------------------------------------------------------
class TestMaliyetKutleleriTekKaynaktan:
    """ÖLÇÜLDÜ (once.json): fiyatlanan yakıt kütlesi her grain tipinde
    6,4675 kg idi (end_burner gerçeği 7,1079 -> -%9,00; star 5,8861 ->
    +%9,89; wagon_wheel 5,9886 -> +%8,01). Yalıtım ise kalınlıktan
    BAĞIMSIZ 0,564 kg / 14,1 USD idi (0, 3, 12 mm'de aynı)."""

    @staticmethod
    def _fiyatlanan_yakit_kg(e, mal):
        aile = SOLID_PROPELLANT_COST_FAMILY[
            str(e.propellant_type).strip().lower()]
        usd = mal['material_costs_usd']['propellant']
        return usd / SOLID_COST_PARAMS['propellant_usd_per_kg'][aile]

    @pytest.mark.parametrize('gtip', ['bates', 'end_burner', 'star',
                                      'wagon_wheel'])
    def test_yakit_kutlesi_grain_tipini_gorur(self, gtip):
        e = _motor(grain_type=gtip)
        mal = _sessiz(e._calculate_cost_analysis)
        gercek = float(_sessiz(e._propellant_volume)) * e.rho_p
        # Yayımlanan kalem 0,1 USD'ye yuvarlanır; tolerans o yuvarlamadır.
        assert self._fiyatlanan_yakit_kg(e, mal) == pytest.approx(
            gercek, abs=0.002), gtip

    def test_grain_tipleri_birbirinden_AYRISIR(self):
        """Tek kaynağa bağlanmadan önce dört tip de AYNI sayıyı veriyordu;
        bu test o çökmeyi (hepsi eşit) doğrudan reddeder."""
        degerler = {}
        for gtip in ('bates', 'end_burner', 'star', 'wagon_wheel'):
            e = _motor(grain_type=gtip)
            mal = _sessiz(e._calculate_cost_analysis)
            degerler[gtip] = round(self._fiyatlanan_yakit_kg(e, mal), 3)
        assert len(set(degerler.values())) == 4, degerler

    @pytest.mark.parametrize('t_mm,beklenen_sifir', [(0.0, True),
                                                     (3.0, False),
                                                     (12.0, False)])
    def test_yalitim_kutlesi_kullanicinin_kalinligini_gorur(
            self, t_mm, beklenen_sifir):
        e = _motor()
        e.insulation_thickness_m = t_mm / 1000.0
        mal = _sessiz(e._calculate_cost_analysis)
        usd = mal['material_costs_usd']['insulation']
        kg = usd / SOLID_COST_PARAMS['insulation_usd_per_kg']
        zincir = float(_sessiz(e._dry_mass_breakdown)['insulation_kg'])
        assert kg == pytest.approx(zincir, abs=0.005), (t_mm, kg, zincir)
        if beklenen_sifir:
            # Yalıtım yokken parası da yok (eski model 14,1 USD alıyordu).
            assert usd == pytest.approx(0.0, abs=1e-9)
        else:
            assert usd > 0.0

    def test_yalitim_kalinliga_MONOTON_bagli(self):
        """Sabit 3 mm / 1200 kg-m3 geri konursa üç değer eşitlenir."""
        bedeller = []
        for t_mm in (0.0, 3.0, 12.0):
            e = _motor()
            e.insulation_thickness_m = t_mm / 1000.0
            mal = _sessiz(e._calculate_cost_analysis)
            bedeller.append(mal['material_costs_usd']['insulation'])
        assert bedeller[0] < bedeller[1] < bedeller[2], bedeller


# ---------------------------------------------------------------------------
# P16B4-06 — boş çizim 'success' diye yayımlanmaz
# ---------------------------------------------------------------------------
class TestDetayliCadBosCizimYayimlamaz:
    """ÖLÇÜLDÜ (once.json P16B4-06): beş FARKLI motor (Ø80x300 ⟷ Ø250x1500,
    40 ⟷ 120 bar, apcp ⟷ kndx) için 200 + 8.939 bayt BAYT-AYNI yanıt.
    Kök sebep üretici: ``generate_solid_motor_cad`` bir taslaktır ve
    ÜRETTİĞİ FİGÜRÜN İZ SAYISI 0'dır (ölçüldü)."""

    IYI = dict(chamber_diameter=100.0, chamber_length=500.0,
               throat_diameter=25.0, exit_diameter=60.0, nozzle_length=150.0)

    @pytest.fixture(scope='class')
    def uretici_iz(self):
        """Üreticinin BU koşuda gerçekten ürettiği iz sayısı — sözleşmenin
        ölçüm ayağı. Taslak hâl (0 iz) kilitlenmez; üretici çizmeye
        başladığı gün beklenti kendiliğinden 200'e döner."""
        from hrma.export.cad_visualization import DetailedCADGenerator
        sonuc = _sessiz(DetailedCADGenerator().generate_solid_motor_cad,
                        dict(self.IYI))
        return len(json.loads(sonuc['plot_json']).get('data') or [])

    def test_uc_hukmu_URETICININ_OLCUMUNU_izliyor(self, client, uretici_iz):
        """ÖH D18 (Fable-D16 ŞART, P16B4-06): iddia 'izsiz çizim success
        olamaz'dır, 'katı hep 501'dir değil. Bu yüzden beklenti üreticinin
        ÖLÇÜLEN iz sayısına koşulludur — ihracat kulvarının kardeş
        çevirisiyle aynı sözleşme."""
        r = client.post('/api/detailed-cad/solid', json=dict(self.IYI))
        govde = r.get_json()
        if uretici_iz == 0:
            assert r.status_code == 501, r.get_data(as_text=True)[:200]
            assert govde['error'] == 'cad_not_modelled'
            assert govde['motor_type'] == 'solid'
            assert govde['trace_count'] == 0
        else:
            assert r.status_code == 200, r.get_data(as_text=True)[:200]
            assert govde['status'] == 'success'
            assert govde['trace_count'] == uretici_iz, (
                'uç kendi beyan ettiği iz sayısını üreticinin ölçülen iz '
                'sayısıyla eşitlemeli')

    def test_bos_cizim_ASLA_success_olamaz(self, client, uretici_iz):
        """Kalemin kalıcı iddiası: iz sayısı 0 ise 200/success yasaktır.
        Üretici çizmeye başlarsa bu test sessizce geçer (ön koşul düşer),
        kilitlediği tek şey 'boş figür başarı diye yayımlanamaz'dır."""
        r = client.post('/api/detailed-cad/solid', json=dict(self.IYI))
        govde = r.get_json() or {}
        if govde.get('trace_count') == 0:
            assert r.status_code != 200, r.get_data(as_text=True)[:200]
            assert govde.get('status') != 'success'

    def test_geometri_kapisi_kapidan_ONCE_calisir(self, client):
        """Sıra korunmalı: eksik geometri hâlâ 422 (aile sözleşmesi),
        501 onu gölgelemiyor."""
        r = client.post('/api/detailed-cad/solid', json={})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'missing_export_geometry'

    def test_cizim_gercekten_varsa_kapi_KENDILIGINDEN_acilir(self, client):
        """Kardeş uç (liquid) gerçek geometri üretir; kapı ölçüme bağlı
        olduğu için orada 200 kalır ve iz sayısı yayımlanır."""
        r = client.post('/api/detailed-cad/liquid', json=dict(self.IYI))
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert govde['status'] == 'success'
        assert govde['trace_count'] > 0


# ---------------------------------------------------------------------------
# P14M4-06 — /calculate_solid kırpma künyesi bekçili
# ---------------------------------------------------------------------------
class TestKirpmaKunyesiUctaBekcili:
    """ÖLÇÜLDÜ (once.json P14M4-06): künye 8/8 satırda yayımlanıyor,
    5 satır kırpılmış. Kalem 'tamamen bekçisiz' diyordu: uç seviyesinde
    ``expansion_ratio_clamped`` / ``_uncapped`` / ``_basis`` üçlüsünü
    kilitleyen tek test yoktu (D15 bekçisi yalnız MOTOR API'sindeydi)."""

    BAND_ALT, BAND_UST = 2.5, 500.0

    @pytest.fixture(scope='class')
    def satirlar(self, client):
        r = client.post('/calculate_solid',
                        json=dict(UC_TABAN, chamber_pressure=5.0,
                                  expansion_ratio=2.5))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        ap = r.get_json()['altitude_performance']
        if isinstance(ap, dict):
            ap = ap['altitude_performance']
        assert isinstance(ap, list) and ap
        return ap

    def test_kunye_HER_satirda_var(self, satirlar):
        for s in satirlar:
            assert 'expansion_ratio_clamped' in s, s.get('altitude')
            assert 'expansion_ratio_basis' in s, s.get('altitude')
            assert 'expansion_ratio_uncapped' in s, s.get('altitude')

    def test_kirpilan_satirlar_gercekten_BANT_KENARINDA(self, satirlar):
        """``clamped`` sabit False'a çevrilirse bu test kırmızı olur:
        kırpılmış satır kalmaz. Sabit True'ya çevrilirse de kırmızı olur:
        bant kenarında olmayan satırlar kırpılmış görünür."""
        kirpilan = [s for s in satirlar if s['expansion_ratio_clamped']]
        assert kirpilan, 'bu köşede kırpma bekleniyordu (ölçüm: 5/8 satır)'
        for s in kirpilan:
            eps = s['expansion_ratio']
            assert (eps == pytest.approx(self.BAND_ALT)
                    or eps == pytest.approx(self.BAND_UST)), s['altitude']
            ham = s['expansion_ratio_uncapped']
            assert ham is not None and abs(ham - eps) > 1e-9, s['altitude']

    def test_kirpilmamis_satirda_ham_deger_YOK(self, satirlar):
        temiz = [s for s in satirlar if not s['expansion_ratio_clamped']]
        assert temiz, 'bu köşede kırpılmamış satır da bekleniyordu'
        for s in temiz:
            assert s['expansion_ratio_uncapped'] is None, s['altitude']
            assert self.BAND_ALT - 1e-9 <= s['expansion_ratio'] <= (
                self.BAND_UST + 1e-9)

    def test_basis_metni_iki_durumu_AYIRIR(self, satirlar):
        """Tek sabit metne çevrilirse (mutasyon) bu test kırmızı olur."""
        metinler = {bool(s['expansion_ratio_clamped']):
                    s['expansion_ratio_basis'] for s in satirlar}
        assert set(metinler) == {True, False}
        assert metinler[True] != metinler[False]
        assert 'clamped' in metinler[True]
        assert 'optimum' in metinler[False]


# ---------------------------------------------------------------------------
# P13S1-02 — çekirdek ipucu ölçülen eğilimle çelişmez
# ---------------------------------------------------------------------------
class TestCekirdekIpucuOlcumleCelismez:
    """ÖLÇÜLDÜ (once.json P13S1-02): ipucu "Smaller cores give progressive
    thrust, larger cores give regressive thrust" diyordu. Çözücünün kendi
    sınıflandırıcısı ise 10 / 30 / 60 mm çekirdek için sırasıyla
    Progressive-Regressive / Regressive / Regressive veriyor ve bitiş/
    başlangıç platosu oranı 0,111 -> 0,205 -> 0,493, yani küçük çekirdek
    DAHA çok azalıyor — ipucunun hem hükmü hem eğilimi tersti."""

    ANAHTAR = 'solid.ui.initial_diameter_of_the_central_core'

    @staticmethod
    def _ipucu(yol, anahtar):
        with io.open(os.path.join(KOK, yol), encoding='utf-8') as fh:
            metin = fh.read()
        i = metin.index(anahtar)
        return metin[i:i + 900]

    @pytest.fixture(scope='class')
    def olculen(self):
        sonuc = {}
        for core in (10.0, 60.0):
            e = _motor(core_diameter=core)
            egri = _sessiz(e.calculate_thrust_curve)
            rapor = _sessiz(e._thrust_shape_report,
                            egri['thrust'], egri['time'])
            sonuc[core] = rapor
        return sonuc

    def test_olculen_egilim_kucuk_cekirdekte_DAHA_azalan(self, olculen):
        """İpucunun düzeltilmiş yönünün ÖLÇÜM dayanağı. Motor tarafı ters
        yöne kayarsa ipucu da yanlışlanmış olur ve bu test uyarır."""
        oran = {c: r['end_plateau_N'] / r['start_plateau_N']
                for c, r in olculen.items()}
        assert oran[10.0] < oran[60.0], oran
        assert 'Regressive' in olculen[60.0]['shape'], olculen[60.0]['shape']

    def test_10mm_sinifi_metinle_CELISMIYOR(self, olculen):
        """ÖH D18 (Fable-D16 ŞART, P13S1-02): eski düzeltme 'çekirdek
        aralığının TAMAMINDA azalan sınıf' diyordu; ölçüm 10 mm'de
        Progressive-Regressive veriyor. Metin artık bu sınıfı ADIYLA anar
        ve tek-sınıf iddiasını taşımaz; bu test iki yarıyı birbirine bağlar:
        çözücü 10 mm'de hangi sınıfı veriyorsa metin onu anmalıdır."""
        sinif = olculen[10.0]['shape']
        assert sinif == 'Progressive-Regressive', sinif
        for yol in ('hrma/templates/solid.html',
                    'hrma/static/js/i18n_pages.js'):
            parca = self._ipucu(yol, self.ANAHTAR)
            assert sinif in parca, (
                '%s: ölçülen 10 mm sınıfı (%s) ipucunda anılmıyor'
                % (yol, sinif))

    def test_olcum_MONOTON_DEGIL_ve_metin_bunu_soyluyor(self, monoton):
        """ŞART'ın ikinci yarısı: 'küçük çekirdek DAHA çok azalır' cümlesi
        monoton bir eğilim vaat ediyordu, ölçüm monoton değil
        (15 mm 0,088 < 10 mm 0,111). Metin artık monotonluk iddia etmiyor.

        ÖH D24 / OH-D23-09: iddia alt-dize denetiminden ÇIKARILDI. Eski
        biçim ``'monoton' in parca`` idi ve 'monoton' 'monotonic'in alt
        dizesi olduğu için metin tam TERSİNİ söylese de geçiyordu. Artık
        iddianın YÖNÜ okunur: olumsuz geçiş ZORUNLU, olumlu geçiş YASAK.
        """
        oranlar, monoton_mu = monoton
        assert monoton_mu is False, oranlar
        for yol in ('hrma/templates/solid.html',
                    'hrma/static/js/i18n_pages.js'):
            parca = self._ipucu(yol, self.ANAHTAR)
            olumlu, olumsuz = monotonluk_iddialari(parca)
            assert olumsuz, (
                '%s: ipucu monotonluğu AÇIKÇA reddetmiyor; ölçüm monoton '
                'değil (%s) ama metinde olumsuzlanmış monotonluk geçişi yok'
                % (yol, oranlar))
            assert not olumlu, (
                '%s: ipucu monotonluk VAAT eden bir geçiş taşıyor, oysa '
                'ölçüm monoton değil (%s): %s' % (yol, oranlar, olumlu))

    @pytest.fixture(scope='class')
    def monoton(self):
        oranlar = {}
        for core in (10.0, 15.0, 30.0, 60.0):
            e = _motor(core_diameter=core)
            egri = _sessiz(e.calculate_thrust_curve)
            rapor = _sessiz(e._thrust_shape_report,
                            egri['thrust'], egri['time'])
            oranlar[core] = (rapor['end_plateau_N']
                             / rapor['start_plateau_N'])
        sirali = [oranlar[c] for c in (10.0, 15.0, 30.0, 60.0)]
        return oranlar, sirali == sorted(sirali)

    @pytest.mark.parametrize('yol', ['hrma/templates/solid.html',
                                     'hrma/static/js/i18n_pages.js'])
    def test_ters_hukum_metinde_KALMADI(self, yol):
        parca = self._ipucu(yol, self.ANAHTAR)
        assert 'Smaller cores give progressive' not in parca, yol
        assert 'Küçük çekirdek artan' not in parca, yol
        # ÖH D18 (ŞART): ölçümü aşan 'aralığın tamamında tek sınıf' iddiası
        # da kaldırıldı — 10 mm Progressive-Regressive ölçülüyor.
        assert 'regressive over the whole core range' not in parca, yol
        assert 'aralığının tamamında AZALAN' not in parca, yol

    def test_turkce_karsilik_da_duzeltildi(self):
        parca = self._ipucu('hrma/static/js/i18n_pages.js', self.ANAHTAR)
        # EN ve TR kayıtları aynı anahtarla iki kez geçer; TR olanı ara.
        with io.open(os.path.join(KOK, 'hrma/static/js/i18n_pages.js'),
                     encoding='utf-8') as fh:
            metin = fh.read()
        assert metin.count('Küçük çekirdek artan') == 0
        # ÖH D18: eski TR cümlesi ('AZALAN itki verir') ölçümü aşıyordu;
        # yerine ölçülen ifade aranır.
        assert 'bitiş platosu her çekirdekte başlangıcın altındadır' in metin
        assert parca  # ilk kayıt da okunabilmeli


# ---------------------------------------------------------------------------
# P13B1-02 — katı ürün uçlarının boş-gövde kapıları
# ---------------------------------------------------------------------------
class TestKatiUclariBosGovdeyeHukumUretmez:
    """Kalemin ikinci yarısı ('/api/solid-monte-carlo boş gövdeyle 200 +
    tam istatistik hüküm') bu tabanda ZATEN onarılmıştı (ölçüm once.json:
    422). Bekçisi yoktu — geri dönebilirdi. Bu sınıf onu kilitler."""

    @pytest.mark.parametrize('yol', ['/api/solid-monte-carlo',
                                     '/api/detailed-cad/solid'])
    def test_bos_govde_adlandirilmis_422(self, client, yol):
        r = client.post(yol, json={})
        assert r.status_code == 422, (
            f'{yol} boş gövdeye {r.status_code} döndü, '
            f'{len(r.get_data())} bayt')
        govde = r.get_json()
        assert govde.get('error'), govde
        # Sayı UYDURULMAMIŞ olmalı: hüküm alanları gövdede olmamalı.
        ham = r.get_data(as_text=True)
        for yasak in ('"mean"', '"std_dev"', '"percentile', '"cad_data"'):
            assert yasak not in ham, (yol, yasak)
