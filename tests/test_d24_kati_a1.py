# -*- coding: utf-8 -*-
"""ÖH Dalga-24 · katı motor · aşama 1 — iki onarımın bekçisi.

Her sınıf TEK kalemi tutar ve kalemin ONARIMDAN ÖNCEKİ davranışını reddeder;
onarım geçici olarak geri alındığında (ters mutasyon) kırmızıya döner.
Ölçüm dosyaları: ``docs/scofield/raw/OH/D24/kati/a1/once.json`` (taban ağacı
88a29d3) ve ``sonra.json`` (bu ağaç); üreten betik aynı dizindeki
``olcum.py``, ters-mutasyon kanıtı ``mutasyon.py`` / ``mutasyon.json``.

Kapsanan kalemler:
  OH-D23-10  ısıl koruma katman sırası (grain → liner → yalıtım → kasa)
             halkalara İŞLİYOR ve kaynağıyla birlikte YAYIMLANIYOR
  OH-D23-19  /calculate_solid yanıtı ``openrocket`` bloğunu taşıyor
             (hibrit/sıvı ile aynı sözleşme, fail-closed)
"""

import math
import warnings

import pytest

from hrma.app import app as flask_app
from hrma.engines.solid_rocket_engine import (
    SOLID_THERMAL_LAYER_ORDER,
    SOLID_THERMAL_LAYER_ORDER_BASIS,
    SolidRocketEngine,
)

TABAN = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100, grain_length=500,
             core_diameter=30, chamber_pressure=40)

UC_TABAN = dict(motor_name='D24-KATI', propellant_type='apcp',
                grain_type='bates', chamber_pressure=40.0, thrust=5000.0,
                burn_time=3.0, chamber_diameter=100.0, grain_length=500.0,
                core_diameter=30.0, expansion_ratio=8.0)

SIVI_TABAN = dict(motor_name='D24-SIVI', thrust=5000.0,
                  chamber_pressure=20.0, mixture_ratio=2.2,
                  fuel_type='rp1', oxidizer_type='lox',
                  expansion_ratio=8.0)


def _motor(**ov):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return SolidRocketEngine(overrides=dict(ov), **TABAN)


def _sessiz(fn, *a, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **kw)


def _halka_ic_capi(kutle, kalinlik, L, rho):
    """Halka kütlesinden iç çapı geri çözer.

    m = pi * (d_ic + t) * t * L * rho  ->  d_ic = m / (pi * t * L * rho) - t
    Bu, bekçinin formülü ürün kodundan KOPYALAMADAN geometriyi ölçmesini
    sağlar: kütle hangi halkadan geliyorsa iç çapı odur.
    """
    return kutle / (math.pi * kalinlik * L * rho) - kalinlik


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# OH-D23-10 — katman sırası: grain → liner → yalıtım → kasa
# ---------------------------------------------------------------------------
class TestOHD2310KatmanSirasi:
    """ÖLÇÜLDÜ (once.json, taban 88a29d3; D=100 mm, L_kasa=0,6 m,
    rho=1200 kg/m3, yalıtım 20 mm / liner 5 mm):

        kalem          ÖNCE        SONRA
        yalıtım iç çapı 0,100 m     0,110 m   (= D + 2*t_liner)
        liner iç çapı   0,140 m     0,100 m   (= D, grain'e yapışık)
        insulation_kg   5,428672    5,881061
        liner_kg        1,639911    1,187522
        toplam          7,068583    7,068583  (bit-aynı)

    Yani ÖNCE liner yalıtımın DIŞINDA, kasa iç çapının bile ötesinde bir
    halkaydı; katı motorun yapım sırasında liner grain'i yalıtıma bağlayan
    en iç katmandır (NASA SP-8093; Sutton & Biblarz 9. baskı Böl. 12).
    """

    KALIN = dict(insulation_thickness=20.0, liner_thickness=5.0)

    def test_liner_halkasi_graine_yapisik(self):
        e = _motor(**self.KALIN)
        ins, lin = _sessiz(e._insulation_liner_masses)
        L = e._case_inner_length()
        rho = e._insulation_density()
        d_liner = _halka_ic_capi(lin, e.liner_thickness, L, rho)
        assert d_liner == pytest.approx(e.D_chamber, rel=1e-12), (
            'liner halkasının iç çapı grain dış çapı olmalı (bağ katmanı); '
            'ölçülen %r, grain %r' % (d_liner, e.D_chamber))

    def test_yalitim_halkasi_linerin_disinda(self):
        e = _motor(**self.KALIN)
        ins, lin = _sessiz(e._insulation_liner_masses)
        L = e._case_inner_length()
        rho = e._insulation_density()
        d_ins = _halka_ic_capi(ins, e.insulation_thickness_m, L, rho)
        beklenen = e.D_chamber + 2.0 * e.liner_thickness
        assert d_ins == pytest.approx(beklenen, rel=1e-12), (
            'yalıtım halkası liner’ın hemen dışında olmalı: beklenen %r, '
            'ölçülen %r' % (beklenen, d_ins))

    def test_liner_ic_capi_yalitim_kalinligindan_BAGIMSIZ(self):
        """Kusurun imzası: eski sırada liner iç çapı yalıtım kalınlığıyla
        büyüyordu (D + 2*t_ins). Doğru sırada liner hep grain'e yapışıktır,
        yalıtım ne olursa olsun iç çapı D'dir."""
        L = None
        capillar = []
        for t_ins in (0.0, 5.0, 20.0, 50.0):
            e = _motor(insulation_thickness=t_ins, liner_thickness=5.0)
            _ins, lin = _sessiz(e._insulation_liner_masses)
            L = e._case_inner_length()
            capillar.append(_halka_ic_capi(lin, e.liner_thickness, L,
                                           e._insulation_density()))
        for d in capillar:
            assert d == pytest.approx(0.1, rel=1e-12), capillar
        assert max(capillar) - min(capillar) < 1e-12, capillar

    def test_toplam_kutle_siradan_BAGIMSIZ(self):
        """Sıra iki kalem arasında kütle taşır, toplamı DEĞİŞTİRMEZ:
        (D+t_i)t_i + (D+2t_i+t_l)t_l == (D+t_l)t_l + (D+2t_l+t_i)t_i.
        Bu kimlik onarımın kuru kütleyi kıpırdatmadığının kanıtıdır."""
        e = _motor(**self.KALIN)
        ins, lin = _sessiz(e._insulation_liner_masses)
        D = e.D_chamber
        t_i = e.insulation_thickness_m
        t_l = e.liner_thickness
        L = e._case_inner_length()
        rho = e._insulation_density()
        tek_halka = math.pi * (D + t_i + t_l) * (t_i + t_l) * L * rho
        assert ins + lin == pytest.approx(tek_halka, rel=1e-12)
        # Ölçülen sayılar (once.json = sonra.json bu satırda):
        assert ins + lin == pytest.approx(7.068583471, rel=1e-9)
        dokum = _sessiz(e._dry_mass_breakdown)
        assert dokum['total_kg'] == pytest.approx(17.926904842, rel=1e-9)

    def test_dokum_kalemleri_olculen_sayilarda(self):
        e = _motor(**self.KALIN)
        dokum = _sessiz(e._dry_mass_breakdown)
        assert dokum['insulation_kg'] == pytest.approx(5.881061448, rel=1e-9)
        assert dokum['liner_kg'] == pytest.approx(1.187522023, rel=1e-9)

    def test_sira_TEK_kaynaktan_yayimlaniyor(self):
        e = _motor(**self.KALIN)
        panel = _sessiz(e._design_insulation_system)['thermal_barrier']
        assert panel['layer_order'] == list(SOLID_THERMAL_LAYER_ORDER)
        assert panel['layer_order_basis'] == SOLID_THERMAL_LAYER_ORDER_BASIS
        assert SOLID_THERMAL_LAYER_ORDER == (
            'propellant_grain', 'liner', 'insulation', 'case')

    def test_kunye_kaynagini_ADIYLA_soyluyor(self):
        metin = SOLID_THERMAL_LAYER_ORDER_BASIS
        assert 'SP-8093' in metin
        assert 'Sutton' in metin
        # Beyan uydurma değil, kütle zincirinin gerçek sırasını söylüyor
        # olmalı: liner iki halkanın İÇ olanı.
        assert 'liner' in metin and 'insulation' in metin
        assert metin.index('liner') < metin.index('insulation')

    def test_beyan_ile_geometri_AYRISAMAZ(self):
        """Beyan bir etiket değildir: yayımlanan sıra, kütle halkalarının
        ÖLÇÜLEN iç çaplarıyla birebir aynı sırayı vermek zorundadır."""
        e = _motor(**self.KALIN)
        ins, lin = _sessiz(e._insulation_liner_masses)
        L = e._case_inner_length()
        rho = e._insulation_density()
        yaricap = {
            'liner': _halka_ic_capi(lin, e.liner_thickness, L, rho),
            'insulation': _halka_ic_capi(ins, e.insulation_thickness_m,
                                         L, rho),
        }
        sira = [ad for ad in SOLID_THERMAL_LAYER_ORDER if ad in yaricap]
        olculen = sorted(yaricap, key=yaricap.get)
        assert sira == olculen, (
            'yayımlanan katman sırası %r, kütle halkalarının ölçülen sırası '
            '%r (iç çaplar: %r)' % (sira, olculen, yaricap))

    def test_varsayilan_motor_BIT_AYNI(self):
        """Yalıtımı olmayan (varsayılan) motorda iki sıra da aynı sonucu
        verir; onarım sessiz bir regresyon getirmedi."""
        e = _motor()
        dokum = _sessiz(e._dry_mass_breakdown)
        assert dokum['liner_kg'] == pytest.approx(0.4614371289592694,
                                                  rel=1e-12)
        assert dokum['insulation_kg'] == 0.0
        assert dokum['total_kg'] == pytest.approx(6.001397012523196,
                                                  rel=1e-12)


# ---------------------------------------------------------------------------
# OH-D23-19 — /calculate_solid openrocket bloğu
# ---------------------------------------------------------------------------
class TestOHD2319KatiOpenRocketBlogu:
    """ÖLÇÜLDÜ (once.json, taban 88a29d3): ``POST /calculate_solid`` HTTP 200,
    72 üst düzey yaprak, ``openrocket`` YOK; aynı ağaçta
    ``POST /calculate_liquid`` altı anahtarlı ``openrocket`` bloğunu
    taşıyordu. SONRA: katı uçta 73 yaprak, blok VAR, ``eng_file`` 3053
    karakter, ``eng_error`` None.
    """

    @pytest.fixture(scope='class')
    def kati(self, client):
        r = client.post('/calculate_solid', json=dict(UC_TABAN))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()

    def test_blok_var(self, kati):
        assert 'openrocket' in kati, (
            '/calculate_solid yanıtı openrocket bloğu taşımıyor '
            '(OH-D23-19 / OH-D19-14 katı ayağı)')
        assert isinstance(kati['openrocket'], dict)

    def test_sozlesme_sivi_ucuyla_AYNI(self, client, kati):
        rl = client.post('/calculate_liquid', json=dict(SIVI_TABAN))
        assert rl.status_code == 200, rl.get_data(as_text=True)[:300]
        sivi = rl.get_json()['openrocket']
        assert set(kati['openrocket']) == set(sivi), (
            'katı ve sıvı uçlarının openrocket şeması ayrıştı: %r ⟷ %r'
            % (sorted(kati['openrocket']), sorted(sivi)))
        assert set(kati['openrocket']) == {
            'eng_file', 'eng_error', 'eng_envelope_warning',
            'motor_summary', 'flight_profile', 'flight_profile_reason'}

    def test_FAIL_CLOSED_ya_dosya_ya_adli_gerekce(self, kati):
        blok = kati['openrocket']
        dosya, hata = blok['eng_file'], blok['eng_error']
        assert (dosya is None) != (hata is None), (
            'aynı anda hem .eng hem ret, ya da ikisi birden yok: %r / %r'
            % (type(dosya).__name__, hata))
        if hata is not None:
            assert hata['error'] == 'missing_export_data'
            assert isinstance(hata['missing_fields'], list)
            assert isinstance(hata['field_reasons'], dict)
        else:
            assert isinstance(dosya, str) and len(dosya) > 200
            # RASP .eng: yorum satırlarıyla başlar, sonra künye satırı.
            assert dosya.lstrip().startswith(';')

    def test_ucus_profili_UYDURULMUYOR(self, kati):
        blok = kati['openrocket']
        assert blok['flight_profile'] is None, (
            'katı ucu roket/rampa parametresi almıyor; uçuş profili '
            'uydurulmamalı')
        gerekce = blok['flight_profile_reason']
        assert isinstance(gerekce, str) and gerekce
        assert 'solid endpoint' in gerekce
        assert 'no rocket or launch parameters' in gerekce

    def test_YAKINSAMAYAN_kosuda_motor_dosyasi_YOK(self, client):
        """422 ile reddedilen (çözülemeyen) koşuda sahte .eng yayımlanmaz —
        blok yakınsama kapısının ARDINDADIR."""
        yuk = dict(UC_TABAN)
        yuk['burn_rate_n'] = 1.0
        r = client.post('/calculate_solid', json=yuk)
        assert r.status_code == 422, r.status_code
        govde = r.get_json()
        assert 'openrocket' not in govde, (
            'yakınsamayan koşu openrocket bloğu yayımlıyor')

    def test_ozet_bos_degil(self, kati):
        ozet = kati['openrocket']['motor_summary']
        assert isinstance(ozet, dict) and ozet, (
            'motor_summary boş: hibrit/sıvı uçlarında dolu')
