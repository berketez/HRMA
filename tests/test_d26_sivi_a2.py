# -*- coding: utf-8 -*-
"""ÖH D26 · kulvar **sivi** · aşama **2/2** — bekçiler.

Bu dosya beş kalemi kilitler. Her sınıfın belge dizesi, kusuru gördüğü
ÖLÇÜMÜ taşır (``docs/scofield/raw/OH/D26/sivi/a2/once*.json``).

* **P7B2-09** — ``/calculate_liquid`` tank basıncı kapısının kendisiyle
  çelişkisi: uç, çözücünün OKUMADIĞI ``tank_pressure``ı 400 ile reddederken
  kullanıcıya "onun yerine ``feed_pressure`` kullan" diyordu; o alan ise
  hiçbir ΔP kapısından geçmiyordu.
* **OH-D25-16** — mm dönüşümü on ayrı yerde elle yazılıydı (doktrin 4).
* **OH-D25-21** — h_gas birim çaprazı ``if`` koşuluna bağlıydı (ölü adam).
* **P4B4-07** — haritasız itici için su koçu bağlaması fail-closed.
* **P4B4-08** — iki malzeme adı iki ayrı argüman.
"""
import ast
import inspect
import os

import pytest


SIVI = {'thrust': 10000.0, 'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0}

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LRE_YOLU = os.path.join(KOK, 'hrma', 'engines', 'liquid_rocket_engine.py')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def gonder(client, yuk):
    y = client.post('/calculate_liquid', json=yuk)
    try:
        return y.status_code, (y.get_json() or {})
    except Exception:  # pragma: no cover — gövde JSON değilse iddia düşer
        return y.status_code, {}


# =====================================================================
# P7B2-09 — TEK FİZİK, TEK HÜKÜM
# =====================================================================
class TestP7B209KapiCeliskisi:
    """ÖLÇÜLDÜ (``a2/once.json`` ``P7B2-09``; 10 kN RP-1/LOX, Pc = 30 bar):

    ===========================  ==========  ==========
    gövde                        ÖNCE        SONRA
    ===========================  ==========  ==========
    ``tank_pressure = 3``        HTTP 400    HTTP 400
    ``tank_pressure = 29``       HTTP 400    HTTP 400
    ``feed_pressure = 3``        HTTP **200**  HTTP 400
    ``feed_pressure = 10``       HTTP **200**  HTTP 400
    ``feed_pressure = 29``       HTTP **200**  HTTP 400
    ``feed_pressure = 130``      HTTP 200    HTTP 200
    ===========================  ==========  ==========

    V301/L-A (SV-10) — ÇEVRİM EKSENİ: ``SIVI`` gövdesi çevrim yazmaz ve uç
    turbopompalı varsayılana düşer; o çevrimde ``feed_pressure`` enjektörü
    BESLEMEZ ve çözücü onu OKUMAZ (A-sivi SV-10; L-A once.json gg_fp_yok ⟷
    v_gg: yalnız yankı yaprağı değişiyor). Kapı orada sağlıklı tasarımı
    engelliyordu; artık YALNIZ basınç beslemede ısırır, turbopompalıda alan
    ``inputs_not_used`` ile beyan edilir. Ret iddiaları bu yüzden
    ``engine_cycle = 'pressure_fed'`` gövdesinde ölçülür; sayılar ve
    hükümler (400) DEĞİŞMEDİ.

    ÖNCE, 3 bar besleme ile 30 bar hazne 10.000 N itki yayımlıyordu ve tek
    bir uyarı bile yoktu (``uyari_sayisi = 0``); ``feed_pressure_input_bar``
    yanıtta 3,0 olarak yankılanıyordu, yani sayı ÇÖZÜCÜYE ULAŞIYORDU.
    Reddedilen ad (``tank_pressure``) ise çözücünün hiç okumadığı addı ve
    ucun kendi ret gövdesi ``use_instead = 'feed_pressure'`` diyordu — yani
    ürünün kendi tavsiyesine uymak kapıyı tamamen atlatıyordu.
    """

    @pytest.mark.parametrize('feed', [3.0, 10.0, 29.0])
    def test_hazneden_dusuk_besleme_basinci_reddedilir(self, client, feed):
        kod, govde = gonder(client, dict(SIVI, engine_cycle='pressure_fed',
                                         feed_pressure=feed))
        assert kod == 400, (
            f'feed_pressure={feed} bar, chamber_pressure=30 bar — enjektör '
            f'AKAMAZ ama uç HTTP {kod} verdi')
        alanlar = govde.get('invalid_fields') or []
        assert alanlar and alanlar[0].get('field') == 'feed_pressure', govde

    def test_ret_fail_closed_tasarim_uretmez(self, client):
        """Ret gövdesinde tasarım yaprağı bulunmamalı (sayı uydurulmaz)."""
        _, govde = gonder(client, dict(SIVI, engine_cycle='pressure_fed',
                                       feed_pressure=3.0))
        for anahtar in ('motor_geometry', 'performance', 'plots',
                        'detailed_feed_system'):
            assert anahtar not in govde, (
                f'ret gövdesi {anahtar!r} taşıyor — reddedilen istek yine '
                f'tasarım yayımlamış')

    def test_saglikli_besleme_basinci_gecer(self, client):
        """Kapı SAĞLIKLI gövdeyi ısırmaz — ÖK-22 (envanter gevşemez/daralmaz).

        130 bar, ``liquid.html`` formunun kendi varsayılanıdır.
        """
        kod, govde = gonder(client, dict(SIVI, feed_pressure=130.0))
        assert kod == 200, f'sağlıklı besleme basıncı reddedildi; HTTP {kod}'
        assert govde.get('motor_geometry'), 'tasarım üretilmemiş'

    def test_alan_gonderilmeyince_kapi_ISIRMAZ(self, client):
        """Kapı YALNIZ kullanıcının gönderdiği alana uygulanır."""
        kod, _ = gonder(client, dict(SIVI))
        assert kod == 200, (
            f'feed_pressure gönderilmedi ama kapı ısırdı; HTTP {kod} — '
            f'çözücünün kendi besleme çözümü dokunulmaz kalmalıydı')

    def test_TEK_FIZIK_TEK_HUKUM(self, client):
        """Kalemin ta kendisi: aynı fizik iki ada göre ayrışmamalı.

        ÖH D27 / OH-D26-12 — BEKÇİ ÇEVRİLDİ (gerekçe ölçülü). Bu test
        ``tank_pressure`` ile ``feed_pressure``ın AYNI fiziği adlandırdığını
        varsayıyordu ve gövdeye çevrim yazmadığı için uç turbopompalı
        varsayılana düşüyordu. O varsayım tam olarak P7B2-09'un KAPANMAYAN
        ayağıydı: turbopompalı çevrimde tank enjektörü BESLEMEZ (pompa
        besler), yani orada tek fizik YOKTUR — iki ad iki ayrı büyüklüktür.
        Test artık iddiasını ikiye bölüyor:
          * basınç beslemeli çevrimde iki ad TEK fiziktir -> AYNI hüküm,
          * turbopompalı çevrimde ayrı büyüklüklerdir -> tank adıyla
            reddedilir (okunmayan alan), feed ΔP kapısına girer.
        Hiçbir vaka 400'den 200'e geçmedi (ÖK-22: kapsam daralmadı).
        """
        # (a) TEK FİZİK: tank gerçekten enjektörü besliyorsa aynı hüküm.
        pf = dict(SIVI, engine_cycle='pressure_fed')
        kod_tank, _ = gonder(client, dict(pf, tank_pressure=29))
        kod_feed, _ = gonder(client, dict(pf, feed_pressure=29))
        assert kod_tank == kod_feed == 400, (
            f'basınç beslemeli çevrim, enjektörü besleyen basınç 29 bar ⟷ '
            f'hazne 30 bar: tank_pressure -> HTTP {kod_tank}, feed_pressure '
            f'-> HTTP {kod_feed}. Tek fizik, iki hüküm (P7B2-09).')

        # (b) İKİ BÜYÜKLÜK: turbopompalı çevrimde tank okunmayan alandır.
        # V301/L-A (SV-10) — BEKLENTİ DEĞİŞTİ: turbopompalı çevrimde
        # ``feed_pressure`` da çözücünün OKUMADIĞI bir alandır (enjektörü
        # pompa besler; ölçüm sınıf notunda). Eski 400 sağlıklı tasarımı
        # engelliyordu; artık 200 + ``inputs_not_used`` beyanı.
        kod_tank_t, govde_t = gonder(client, dict(SIVI, tank_pressure=29))
        kod_feed_t, govde_f = gonder(client, dict(SIVI, feed_pressure=29))
        assert kod_feed_t == 200, (
            f'turbopompalı çevrimde feed_pressure okunmuyor, tasarımı '
            f'engellememeliydi; HTTP {kod_feed_t}')
        beyan = [b for b in govde_f.get('inputs_not_used') or []
                 if b.get('field') == 'feed_pressure']
        assert beyan and beyan[0]['reason'] == 'not_read_in_turbopump_cycle'
        assert kod_tank_t == 422, (
            f'turbopompalı çevrimde tank_pressure bu ucun okumadığı bir '
            f'alandır ve adıyla reddedilmeliydi; HTTP {kod_tank_t}')
        assert govde_t.get('error') == (
            'tank_pressure_not_read_in_turbopump_cycle'), govde_t

    def test_esik_YENI_DEGIL_tek_kaynaktan(self, client):
        """Kapı yeni eşik icat etmez: ``CHUG_DP_RATIO_MINIMUM``.

        Eşiğin hemen ÜSTÜ geçer, hemen ALTI reddedilir — sınır ürünün kendi
        tek kaynağından okunur, bu dosyada sayı YAZILMAZ.
        """
        from hrma.utils.common_fixes import CHUG_DP_RATIO_MINIMUM

        pc = SIVI['chamber_pressure']
        ust = pc * (1.0 + CHUG_DP_RATIO_MINIMUM) * 1.02
        alt = pc * (1.0 + CHUG_DP_RATIO_MINIMUM) * 0.98
        # V301/L-A: kapı yalnız basınç beslemede koşar (SV-10). Orada tank
        # ayrıca besleme zincirinin gereksinimini (Pc + ΔP_enj + ceket +
        # hat) karşılamalıdır (SV-03); varsayılan ΔP_enj (%22) ile eşiğin
        # hemen üstü 38,48 bar'lık gereksinimin altında kalıp 422 alırdı
        # (ölçüldü). Chug eşiğini ölçmek için enjektör ΔP'si 2 bar seçilir:
        # ust -> 200 (marj 1,32 bar), alt -> chug 400 (ölçüldü).
        pf = dict(SIVI, engine_cycle='pressure_fed', injector_pressure_drop=2)
        kod_ust, _ = gonder(client, dict(pf, feed_pressure=ust))
        kod_alt, _ = gonder(client, dict(pf, feed_pressure=alt))
        assert kod_ust == 200, f'eşiğin üstü reddedildi; HTTP {kod_ust}'
        assert kod_alt == 400, f'eşiğin altı geçti; HTTP {kod_alt}'

    def test_sayiya_cevrilemeyen_deger_TIP_HATASI_URETMEZ(self, client):
        """P16B2-08'in tank tarafında ısırdığı ``TypeError`` burada doğmaz.

        V301/L-A (SV-02): metin/sonsuz değer artık motorun beyan yolundan
        GEÇMEZ; tek sıvı bant kapısı onu 422 ``input_not_accepted`` ile adıyla
        reddeder. Bu testin iddiası (500 yok, çıplak Python tip hatası yok)
        aynen geçerlidir.
        """
        for ham in ('NaN', 'Infinity', 'abc'):
            kod, govde = gonder(client, dict(SIVI, feed_pressure=ham))
            assert kod != 500, f'feed_pressure={ham!r} -> HTTP {kod}'
            assert 'not supported between instances' not in str(
                govde.get('error') or ''), (
                f'çıplak Python tip hatası yayımlanıyor: {govde.get("error")}')


# =====================================================================
# OH-D25-16 — TEK DÖNÜŞÜM NOKTASI
# =====================================================================
class TestOHD2516TekDonusumNoktasi:
    """ÖLÇÜLDÜ (``a2/once.json`` ``OH-D25-16``): ``nozzle_geom`` sözlüğünün
    aynı üç alanı **on** ayrı yerde elle ``* 1000`` / ``* 1000.0`` ile
    çevriliyordu (``ifade_sayisi = 9`` satır, biri iki kez), tek dönüşüm
    yardımcısı YOKTU (``tek_donusum_yardimcisi_var_mi = False``).
    """

    def test_elle_yazili_carpim_kalmadi(self):
        """AST: ``nozzle_geom[...] * 1000`` deseni kaynakta olmamalı."""
        with open(LRE_YOLU, encoding='utf-8') as fh:
            kaynak = fh.read()
        agac = ast.parse(kaynak)
        kalanlar = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.BinOp) or not isinstance(
                    dugum.op, ast.Mult):
                continue
            metin = ast.unparse(dugum)
            if 'nozzle_geom[' in metin and '1000' in metin:
                kalanlar.append((getattr(dugum, 'lineno', None), metin))
        assert not kalanlar, (
            f'elle yazılı mm dönüşümü kaldı: {kalanlar} — dönüşüm '
            f'm_to_mm() tek noktasından geçmeli (OH-D25-16)')

    def test_yardimci_var_ve_katsayi_tek_yerde(self):
        from hrma.engines import liquid_rocket_engine as lre

        assert callable(getattr(lre, 'm_to_mm', None)), (
            'm_to_mm dönüşüm yardımcısı yok')
        assert lre.MM_PER_M == 1000.0
        assert lre.m_to_mm(0.05527802111294594) == pytest.approx(
            55.27802111294594, rel=0, abs=0.0)
        # Katsayı gövdede elle yazılmamalı: yardımcı sabiti kullanmalı.
        gövde = inspect.getsource(lre.m_to_mm)
        assert 'MM_PER_M' in gövde, (
            'm_to_mm katsayıyı kendi içinde elle yazıyor — tek kaynak yok')

    def test_yardimci_tipi_sabitler(self):
        """``float()`` sarmalaması, numpy skalerinin JSON tipini ayırmasını
        engeller — dönüşümün tek yerde olmasının SEBEBİ budur."""
        import numpy as np

        from hrma.engines.liquid_rocket_engine import m_to_mm

        assert type(m_to_mm(np.float64(0.05))) is float

    def test_iki_blok_ayni_sayiyi_yayimlar(self, client):
        """Üst düzey blok ⟷ ``motor_geometry.nozzle_angles``: repr EŞİT."""
        kod, govde = gonder(client, dict(SIVI))
        assert kod == 200
        acilar = ((govde.get('motor_geometry') or {}).get('nozzle_angles')
                  or {})
        assert acilar, 'motor_geometry.nozzle_angles yok'
        for alan in ('throat_diameter_mm', 'exit_diameter_mm'):
            assert repr(govde.get(alan)) == repr(acilar.get(alan)), (
                f'{alan}: üst düzey {govde.get(alan)!r} ⟷ motor bloğu '
                f'{acilar.get(alan)!r} — iki dönüşüm ayrışmış')


# =====================================================================
# OH-D25-21 — ÖLÜ ADAM DÜĞMESİ SÖKÜLDÜ
# =====================================================================
class TestOHD2521CaprazAtlanamaz:
    """ÖLÇÜLDÜ (``a2/once.json`` ``OH-D25-21``): ``test_d16_sivi_a1.py:300``
    çaprazı ``if q is not None and q_kw:`` koşuluna bağlıydı; ürün iki
    yapraktan birini yayımlamayı bıraksa (ya da ``q_kw`` 0,0 dönse) çapraz
    SESSİZCE atlanıp test yeşil kalıyordu.
    """

    def test_kosullu_atlama_kaynakta_kalmadi(self):
        yol = os.path.join(KOK, 'tests', 'test_d16_sivi_a1.py')
        agac = ast.parse(open(yol, encoding='utf-8').read())
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.If) and 'q_kw' in ast.unparse(
                    dugum.test) and 'q is not None' in ast.unparse(
                    dugum.test):
                pytest.fail(
                    f'koşullu atlama satır {dugum.lineno}: '
                    f'{ast.unparse(dugum.test)}')

    def test_iki_yaprak_da_yayimlaniyor(self, client):
        """Çaprazın ölçtüğü iki yaprak GERÇEKTEN var (7011230,019 W/m² ⟷
        7011,230 kW/m², oran tam 1000)."""
        kod, govde = gonder(client, dict(SIVI))
        assert kod == 200
        gaz = ((govde.get('heat_transfer_analysis') or {})
               .get('gas_side_analysis') or {})
        cool = govde.get('cooling_system') or {}
        assert gaz.get('chamber_heat_flux') is not None
        assert cool.get('chamber_heat_flux') is not None
        assert float(cool['chamber_heat_flux']) > 0.0
        assert float(gaz['chamber_heat_flux']) == pytest.approx(
            float(cool['chamber_heat_flux']) * 1000.0, rel=1e-9)


# =====================================================================
# P4B4-07 — FAIL-CLOSED SÖZLEŞMESİ (veri borcu AYRI kalem)
# =====================================================================
class TestP4B407FailClosed:
    """ÖLÇÜLDÜ (``a2/once_su_kocu.json`` ``P4B4-07``): haritasız YEDİ itici
    (lh2, methane, mmh, udmh, n2o, h2o2, n2o4) için su koçu bağlaması HİÇ
    üretilmiyor ve uydurulan ``'water'`` etiketi **0/7**.

    Bu bekçi HARİTANIN DOLMASINI istemez (o, ``test_c_kulvari_bilesenler.py``
    içindeki strict xfail borç iminin işidir ve gerçek bir VERİ borcudur);
    bu bekçi, harita boşken ürünün SESSİZ SU'ya düşmediğini kilitler —
    yani P4B4-07'nin YALAN ayağını.
    """

    def _kwargs(self, akiskan_anahtari):
        from hrma.analysis.valve_feedline import analyze_valve_feedline

        return analyze_valve_feedline(
            mass_flow_kg_s=2.0, density_kg_m3=70.8, viscosity_Pa_s=1.3e-5,
            line_id_m=0.05, line_length_m=3.0, inlet_pressure_Pa=25.0e5,
            valve_pressure_drop_Pa=2.0e5, wall_thickness_m=0.002,
            fluid=akiskan_anahtari, vapor_pressure_Pa=101325.0)

    def test_haritasiz_itici_icin_water_UYDURULMAZ(self):
        from hrma.engines.liquid_rocket_engine import WATER_HAMMER_FLUID_KEY
        from hrma.data.propellant_database import PropellantDatabase

        db = PropellantDatabase()
        iticiler = (db.get_propellant_list('liquid_fuels')
                    + db.get_propellant_list('oxidizers'))
        haritasiz = [p for p in iticiler if p not in WATER_HAMMER_FLUID_KEY]
        assert haritasiz, (
            'harita dolmuş — bu bekçi artık boş haritayı ölçemez, '
            'xfail borç imi de sökülmüş olmalı (P4B4-07)')
        uyduranlar = []
        for p in haritasiz:
            out = self._kwargs(WATER_HAMMER_FLUID_KEY.get(p))
            kw = (out.get('water_hammer') or {}).get('analyzer_kwargs') or {}
            if kw.get('fluid') == 'water':
                uyduranlar.append(p)
        assert not uyduranlar, (
            f"haritasız itici(ler) için fluid='water' uyduruldu: "
            f'{uyduranlar} (P4B4-07 YALAN ayağı geri geldi)')

    def test_haritasiz_itici_icin_baglama_URETILMEZ(self):
        """Fail-closed: hüküm kazanılmadıysa yayımlanmaz."""
        out = self._kwargs(None)
        kw = (out.get('water_hammer') or {}).get('analyzer_kwargs')
        assert not kw, (
            f'akışkan anahtarı yokken su koçu bağlaması üretildi: {kw!r}')

    def test_haritali_itici_icin_baglama_URETILIR(self):
        """Kapı sağlıklı yolu kesmiyor (ÖK-22)."""
        for anahtar in ('lox', 'rp1'):
            out = self._kwargs(anahtar)
            kw = (out.get('water_hammer') or {}).get('analyzer_kwargs') or {}
            assert kw.get('fluid') == anahtar, (
                f'{anahtar} haritalı ama bağlama üretilmedi: {kw!r}')
