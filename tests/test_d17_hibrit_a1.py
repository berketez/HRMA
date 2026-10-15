# -*- coding: utf-8 -*-
"""ÖH Dalga-17 · kulvar **hibrit** · aşama 1/1 — onarım bekçileri.

Her sınıf TEK bir kalemi kilitler ve o kalemin ONARIMI GERİ ALINDIĞINDA
kırmızıya döner (ters-mutasyon kanıtı:
``docs/scofield/raw/OH/D17/hibrit/a1/mutasyon.json``).

Kapsanan kalemler:
  B1-06     (Fable-D15 ŞARTI) ``design_gate_checks`` hiç sıfırlanmıyor,
            ikinci ``calculate()`` aynı hükmü ikinci kez yazıyordu
  B1-11     (Fable-D15 ŞARTI) 20,0 bar yer tutucusu 10 sitede çıplak literal
  P7B1-02   (Fable-D15 ŞARTI) ``/calculate`` yanma grafiği oda basıncını
            ikinci kez ve ÇIPLAK LİTERALLE çözüyordu
  OH-Z5-02  (D16 devri, radyasyon ayağı) motor denge kompozisyonunu çözüyor
            ama ısı modülüne x_H2O/x_CO2 GÖNDERMİYORDU; modül sınıf-ortalaması
            sabitlerine (0,25/0,15) düşüp bunu yanıtta beyan ediyordu
  P15B2-08  polietilen yoğunluğu dört tabloda üç farklı sayı (940/950/960)
"""
import ast
import contextlib
import io
import os
import warnings as _warnings

import pytest

from hrma.analysis import heat_transfer_analysis as _ht
from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.data.propellant_database import (
    HYBRID_FUEL_DENSITY_KG_M3,
    PropellantDatabase,
)
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.hybrid_rocket_engine import (
    CHAMBER_PRESSURE_PLACEHOLDER_BAR,
    HybridRocketEngine,
)

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOTOR_KAYNAK = os.path.join(_KOK, 'hrma', 'engines', 'hybrid_rocket_engine.py')
_APP_KAYNAK = os.path.join(_KOK, 'hrma', 'app.py')

#: Tüm hibrit koşularının ortak tabanı (ölçüm betiğiyle AYNI nokta:
#: ``docs/scofield/raw/OH/D17/hibrit/a1/olcum.py``).
TABAN = dict(thrust=1000.0, burn_time=10.0, of_ratio=6.0,
             chamber_pressure=20.0, fuel_type='htpb', oxidizer_type='n2o')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        with _warnings.catch_warnings():
            _warnings.simplefilter('ignore')
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def motor_kaynagi():
    with open(_MOTOR_KAYNAK, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def app_kaynagi():
    with open(_APP_KAYNAK, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def calculate_yaniti():
    """``/calculate`` tam gövdesi — modül başına TEK koşum (ağır)."""
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    istemci = app.test_client()
    r = _sessiz(istemci.post, '/calculate', json=dict(TABAN))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    govde = r.get_json() or {}
    return govde.get('results', govde)


# =========================================================================
# B1-06 · hüküm defteri tekilleştirilir (Fable-D15 ŞARTI)
# =========================================================================
class TestB106HukumDefteriTekillestirilir:
    """ŞART: ``design_gate_checks`` calculate() başında sıfırlansın YA DA
    gate+quantity anahtarıyla tekilleştirilsin; bekçiye 'iki calculate() →
    tek c_star_plausibility kaydı' testi eklensin.

    ÖLÇÜLDÜ (once.json ``B1_06``): tek koşumda 1 kayıt, iki koşumda 2 kayıt.
    """

    @pytest.fixture
    def motor(self):
        return HybridRocketEngine(**TABAN)

    def test_iki_calculate_tek_c_star_kaydi(self, motor):
        """ŞARTIN birebir istediği bekçi."""
        _sessiz(motor.calculate)
        ilk = [k for k in motor.design_gate_checks
               if k['gate'] == 'c_star_plausibility']
        assert len(ilk) == 1
        _sessiz(motor.calculate)
        ikinci = [k for k in motor.design_gate_checks
                  if k['gate'] == 'c_star_plausibility']
        assert len(ikinci) == 1, (
            'ikinci calculate() aynı hükmü ikinci kez yazdı: %d kayıt'
            % len(ikinci))

    def test_defterin_tamami_gate_quantity_ile_tekil(self, motor):
        _sessiz(motor.calculate)
        _sessiz(motor.calculate)
        _sessiz(motor.calculate)
        anahtarlar = [(k.get('gate'), k.get('quantity'))
                      for k in motor.design_gate_checks]
        assert len(anahtarlar) == len(set(anahtarlar)), anahtarlar

    def test_son_yazan_kazanir_ve_sira_korunur(self, motor):
        """Tekilleştirme kaydı listenin SONUNA taşımaz (okuma sırası sabit)."""
        _sessiz(motor.calculate)
        once = [(k.get('gate'), k.get('quantity'))
                for k in motor.design_gate_checks]
        _sessiz(motor.calculate)
        sonra = [(k.get('gate'), k.get('quantity'))
                 for k in motor.design_gate_checks]
        assert once == sonra

    def test_ayni_kapi_farkli_buyukluk_ayri_kalir(self):
        """``gate`` tek başına anahtar OLMAMALI: oxidizer_flux_flooding iki
        ayrı büyüklük için meşru iki hüküm yazar."""
        m = HybridRocketEngine(**TABAN)
        m._hukum_kaydet({'gate': 'x', 'quantity': 'a', 'value': 1})
        m._hukum_kaydet({'gate': 'x', 'quantity': 'b', 'value': 2})
        m._hukum_kaydet({'gate': 'x', 'quantity': 'a', 'value': 3})
        kayitlar = [k for k in m.design_gate_checks if k['gate'] == 'x']
        assert len(kayitlar) == 2
        assert [k['value'] for k in kayitlar] == [3, 2]

    def test_yanitta_da_tekil(self, calculate_yaniti):
        defter = (calculate_yaniti.get('motor') or {}).get(
            'design_gate_checks') or []
        anahtarlar = [(k.get('gate'), k.get('quantity')) for k in defter]
        assert len(anahtarlar) == len(set(anahtarlar)), anahtarlar

    def test_ciplak_append_geri_gelmedi(self, motor_kaynagi):
        """Yeni bir kapı eklenirken ``append`` yeniden kullanılırsa yakala."""
        assert motor_kaynagi.count('self.design_gate_checks.append(') == 1, (
            'design_gate_checks.append yalnız _hukum_kaydet içinde olmalı')


# =========================================================================
# B1-11 · oda basıncı yer tutucusu TEK sabit (Fable-D15 ŞARTI)
# =========================================================================
class TestB111OdaBasinciYerTutucusuTekKaynak:
    """ŞART: 20,0 bar yer tutucu tek sabite alınsın; kurucu varsayılanı,
    kapı yedeği ve app.py ``_CALCULATE_PC_DEFAULT_BAR`` oradan okusun.

    ÖLÇÜLDÜ (once.json ``B1_11``): sabit yok, 10 çıplak literal site.
    """

    def test_modul_sabiti_var_ve_sayi_degismedi(self):
        assert CHAMBER_PRESSURE_PLACEHOLDER_BAR == 20.0

    def test_kurucu_varsayilani_sabitten_gelir(self):
        import inspect
        imza = inspect.signature(HybridRocketEngine.__init__)
        assert (imza.parameters['chamber_pressure'].default
                is CHAMBER_PRESSURE_PLACEHOLDER_BAR)

    def test_kapi_yedegi_sabitten_gelir(self):
        m = HybridRocketEngine(**dict(TABAN, chamber_pressure=None))
        assert m.P_c == CHAMBER_PRESSURE_PLACEHOLDER_BAR
        assert 'chamber_pressure' in m._defaults_used

    def test_app_sabiti_ayni_nesne(self):
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma import app as _app
        assert (_app._CALCULATE_PC_DEFAULT_BAR
                is CHAMBER_PRESSURE_PLACEHOLDER_BAR)

    def test_motorda_ciplak_literal_kalmadi(self, motor_kaynagi):
        """Kurucu imzası ve kapı yedeği ARTIK sayı yazmaz."""
        assert 'chamber_pressure=20.0' not in motor_kaynagi
        assert 'self.P_c = 20.0' not in motor_kaynagi

    def test_app_kendi_sayisini_yazmaz(self, app_kaynagi):
        assert '_CALCULATE_PC_DEFAULT_BAR = 20.0' not in app_kaynagi


# =========================================================================
# P7B1-02 · /calculate yanma grafiği oda basıncını İKİNCİ kez çözmez
# =========================================================================
class TestP7B102GrafikOdaBasinciniIkinciKezCozmez:
    """ŞART: app.py'deki literal 20,0 yerine ``_CALCULATE_PC_DEFAULT_BAR``
    (ya da çözülmüş ``chamber_pressure_input``) okunsun.

    Aynı istek gövdesinde motor ``chamber_pressure_input``, grafik kendi
    ``data.get('chamber_pressure', 20.0)``'ını okuyordu — iki sözleşme.
    """

    def _calculate_govdesi(self, app_kaynagi):
        agac = ast.parse(app_kaynagi)
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.FunctionDef) and dugum.name == 'calculate':
                return dugum
        raise AssertionError('app.py içinde calculate() bulunamadı')

    def test_grafik_cagrisi_cozulmus_basinci_okur(self, app_kaynagi):
        fn = self._calculate_govdesi(app_kaynagi)
        bulundu = []
        for dugum in ast.walk(fn):
            if (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Attribute)
                    and dugum.func.attr == 'analyze_combustion'):
                bulundu.append(dugum)
        assert bulundu, 'analyze_combustion çağrısı bulunamadı'
        for cagri in bulundu:
            son = cagri.args[-1]
            assert isinstance(son, ast.Name), ast.dump(son)
            assert son.id == 'chamber_pressure_input', son.id

    def test_calculate_icinde_ciplak_20_bar_kalmadi(self, app_kaynagi):
        """AST tabanlı: ``data.get('chamber_pressure', <sayı>)`` biçiminde
        ikinci bir okuma /calculate gövdesinde KALMAMALI (yorumdaki alıntı
        metni sayılmaz — bu yüzden metin araması değil ağaç araması).

        Yalnız İSTEK GÖVDESİ (``data``) okumaları sayılır. Aynı gövdedeki
        ``motor_results.get('chamber_pressure', 0)`` başka bir sözlükten
        okur (serileştirme hata yolu) ve bu kalemin konusu değildir —
        ayrı kalem olarak D17 hibrit a1 raporunda beyan edildi."""
        fn = self._calculate_govdesi(app_kaynagi)
        suclu = []
        for dugum in ast.walk(fn):
            if (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Attribute)
                    and dugum.func.attr == 'get'
                    and isinstance(dugum.func.value, ast.Name)
                    and dugum.func.value.id == 'data'
                    and len(dugum.args) == 2
                    and isinstance(dugum.args[0], ast.Constant)
                    and dugum.args[0].value == 'chamber_pressure'
                    and isinstance(dugum.args[1], ast.Constant)):
                suclu.append(dugum.lineno)
        assert not suclu, (
            '/calculate gövdesinde çıplak yer tutuculu ikinci oda basıncı '
            'okuması kaldı, satır(lar): %s' % suclu)


# =========================================================================
# OH-Z5-02 (radyasyon ayağı) · motor ışıyan tür kesirlerini GÖNDERİR
# =========================================================================
class TestOHZ502RadyasyonKompozisyonuMotordanGelir:
    """Motor dengeyi ZATEN çözüyordu; ısı modülüne göndermiyordu.

    ÖLÇÜLDÜ (once.json ``OH_Z5_02``): HTPB/N2O O/F=6,0 dengesinde gerçek
    kesirler x_H2O = 0,128582 / x_CO2 = 0,061211 iken ısı modülü kendi
    DEFAULT_X_H2O = 0,25 / DEFAULT_X_CO2 = 0,15 sabitlerini kullanıyor ve
    yanıtta "module default ... no x_H2O/x_CO2 was supplied" yazıyordu.
    """

    @pytest.fixture(scope='class')
    def gaz_tarafi(self, calculate_yaniti):
        return ((calculate_yaniti.get('motor') or {})
                .get('heat_transfer_analysis', {})
                .get('gas_side_analysis') or {})

    def test_kesirler_modul_varsayilani_degil(self, gaz_tarafi):
        assert gaz_tarafi['radiation_x_H2O'] != pytest.approx(
            _ht.DEFAULT_X_H2O)
        assert gaz_tarafi['radiation_x_CO2'] != pytest.approx(
            _ht.DEFAULT_X_CO2)

    def test_kunye_cagirandan_geldigini_soyler(self, gaz_tarafi):
        assert 'caller supplied' in gaz_tarafi['radiation_composition_source']

    def test_kesirler_motorun_cozdugu_dengeyle_ayni(self, calculate_yaniti,
                                                   gaz_tarafi):
        turler = ((calculate_yaniti.get('motor') or {})
                  .get('combustion_analysis', {})
                  .get('compositions', {}).get('chamber', {})
                  .get('species') or {})
        assert gaz_tarafi['radiation_x_H2O'] == pytest.approx(
            turler['H2O']['mole_fraction'], rel=1e-12)
        assert gaz_tarafi['radiation_x_CO2'] == pytest.approx(
            turler['CO2']['mole_fraction'], rel=1e-12)

    def test_motor_alanlari_denge_cozulunce_dolar(self):
        m = HybridRocketEngine(**TABAN)
        assert m.x_H2O_chamber is None and m.x_CO2_chamber is None
        _sessiz(m.calculate)
        assert 0.0 < m.x_H2O_chamber < 1.0
        assert 0.0 < m.x_CO2_chamber < 1.0

    def test_denge_cozulmediyse_uydurma_sayi_gecmez(self):
        """FAIL-CLOSED: kesir yoksa GÖNDERİLMEZ (sıfır/varsayılan uydurulmaz)."""
        m = HybridRocketEngine(**TABAN)
        m.x_H2O_chamber = None
        m.x_CO2_chamber = None
        kaynak = open(_MOTOR_KAYNAK, encoding='utf-8').read()
        assert "if _x_h2o is not None and _x_co2 is not None:" in kaynak


# =========================================================================
# P15B2-08 · polietilen yoğunluğu TEK KAYNAK
# =========================================================================
class TestP15B208YakitYogunluguTekKaynak:
    """ÖLÇÜLDÜ (once.json ``P15B2_08``): ``pe`` yoğunluğu 940 (yanma tablosu)
    ⟷ 950 (motor) ⟷ 960 (yakıt veritabanı + regresyon) = ÜÇ ayrı sayı.
    """

    def test_pe_tek_deger(self):
        pdb = PropellantDatabase().database['pe']['density']
        reg = RegressionAnalyzer().fuel_properties['pe']['density']
        assert pdb == reg == HYBRID_FUEL_DENSITY_KG_M3['pe'] == 960

    def test_motor_merkezi_tablodan_okur(self):
        m = HybridRocketEngine(**dict(TABAN, fuel_type='pe'))
        assert m.rho_f == HYBRID_FUEL_DENSITY_KG_M3['pe']

    def test_abs_de_tekillesti(self):
        pdb = PropellantDatabase().database['abs']['density']
        m = HybridRocketEngine(**dict(TABAN, fuel_type='abs'))
        assert pdb == m.rho_f == HYBRID_FUEL_DENSITY_KG_M3['abs'] == 1050

    def test_pe_tek_ad(self):
        assert (PropellantDatabase().database['pe']['name']
                == RegressionAnalyzer().fuel_properties['pe']['name'])

    def test_ciplak_yogunluk_literali_geri_gelmedi(self, motor_kaynagi):
        for lit in ("'density': 950,", "'density': 940,", "'density': 1040,"):
            assert lit not in motor_kaynagi, lit

    #: ÖH D20 / OH-D19-10 — merkezi YOĞUNLUK tablosunda anahtarı olup
    #: ``PropellantDatabase.database`` ve ``RegressionAnalyzer.fuel_properties``
    #: rosterlerinde BİLEREK bulunmayan yakıtlar. ``pla`` D20'de yoğunluk
    #: tablosuna girdi (motor 1250 ⟷ yanma çözücüsü 1240 ayrışması kapandı)
    #: ama regresyon korelasyonu DOĞRULANMAMIŞTIR
    #: (``hybrid_rocket_engine.UNVALIDATED_REGRESSION_FUELS``), o yüzden
    #: regresyon/itici rosterlerinde yeri yok. Küme ADLIDIR: yeni bir yakıt
    #: sessizce dışarıda kalamaz, buraya yazılmadıkça test kırmızıya döner.
    ROSTER_DISI = frozenset({'pla'})

    def test_dort_tablonun_hepsi_ayni_sayiyi_soyler(self):
        """Merkezi tabloda anahtarı olan HER yakıt için tüketiciler uyuşur.

        ÖH D20: döngü ``pdb[ad]``/``reg[ad]`` ile çıplak indeksliyordu ve
        yoğunluk tablosuna yeni bir anahtar girdiğinde ``KeyError`` veriyordu
        (yani "roster" ile "yoğunluk tek kaynağı" aynı küme sanılıyordu).
        İddia korunuyor, kapsamı ADLANDIRILDI: roster dışı yakıt için
        eşitlik ARANMAZ ama o yakıtın roster dışında olduğu DOĞRULANIR.
        """
        pdb = PropellantDatabase().database
        reg = RegressionAnalyzer().fuel_properties
        m_tablo = HybridRocketEngine(**TABAN)
        for ad, deger in HYBRID_FUEL_DENSITY_KG_M3.items():
            motor = HybridRocketEngine(**dict(TABAN, fuel_type=ad))
            assert motor.rho_f == deger, ad
            if ad in self.ROSTER_DISI:
                assert ad not in pdb and ad not in reg, (
                    f'{ad} roster dışı ilan edilmiş ama rosterlerde var — '
                    'ya listeden çıkar ya eşitliği sına')
                continue
            assert pdb[ad]['density'] == deger, ad
            assert reg[ad]['density'] == deger, ad
        assert m_tablo is not None

    # --- ÖH D20 · Fable-D17 ŞARTI (DÖRDÜNCÜ TÜKETİCİ) --------------------
    # ŞART metni: "tests/test_d17_hibrit_a1.py::TestP15B208YakitYogunluguTek
    # Kaynak'a CombustionAnalyzer().propellant_specs[ad]['density'] ==
    # HYBRID_FUEL_DENSITY_KG_M3[ad] (pe ve abs; tabloda anahtarı olan her
    # yakıt) eşitliği eklensin — M5b mutasyonu kırmızıya dönmeli".
    # Fable ÖLÇTÜ: bu dördüncü tüketici BEKÇİSİZDİ — combustion_analysis'te
    # 'density': 940 geri konunca sınıf 6/6 YEŞİL kalıyordu, çünkü yukarıdaki
    # test adı "dört tablonun hepsi" diyor ama ÜÇÜNÜ sınıyordu.
    def test_yanma_cozucusu_de_ayni_sayiyi_soyler(self):
        """Dördüncü tüketici: ``CombustionAnalyzer.propellant_specs``."""
        ozel = _sessiz(CombustionAnalyzer).propellant_specs
        for ad, deger in HYBRID_FUEL_DENSITY_KG_M3.items():
            assert ad in ozel, ad
            assert ozel[ad]['density'] == deger, (
                f'{ad}: yanma çözücüsü {ozel[ad]["density"]} diyor, merkezi '
                f'kayıt {deger}')

    def test_yanma_cozucusunde_ciplak_yogunluk_literali_kalmadi(self):
        """ŞARTIN ölçüm ayağı: regex değil, çalışma zamanı okuması."""
        import inspect

        from hrma.engines import combustion_analysis as _ca_modul
        kaynak = inspect.getsource(_ca_modul.CombustionAnalyzer)
        for lit in ("'density': 920,", "'density': 900,", "'density': 940,",
                    "'density': 950,", "'density': 1050,",
                    "'density': 1180,", "'density': 1240,"):
            assert lit not in kaynak, lit
