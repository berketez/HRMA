# -*- coding: utf-8 -*-
"""ÖH Dalga-27 / termo-ucus a1 bekçileri.

İki defter kalemi + iki BEKÇİ BORCU (P13B4-10 dağıtımı).

Sayılar ``docs/scofield/raw/OH/D27/termo-ucus/a1/{once,sonra}.json``
koşumundan gelir; ters-mutasyon kanıtı aynı dizindeki ``mutasyon*.json``
altındadır.

  * **OH-D26-01** — P15B2-06 üçüncü ayak: bu kulvarın sahasındaki SEKİZ
    çıplak ``101325`` kullanımı merkezî ``P_SEA_LEVEL_PA``ya bağlandı.
  * **OH-D25-13** — ``/api/analysis/wall-profile`` çağıranın
    ``x_H2O``/``x_CO2``sini tüketiyordu ama kompozisyonun kökenini
    yayımlamıyordu.
  * **BEKÇİ BORCU P4B1-01** (kapalı kalem) — F4-1 uç kapısı.
  * **BEKÇİ BORCU P4B4-01** (kapalı kalem) — su koçu kolon-ayrılması
    fail-closed kapısı override altında kapanmaz.
"""
import ast
import contextlib
import io
import pathlib

import pytest

from hrma.analysis.heat_transfer_analysis import (
    DEFAULT_X_CO2, DEFAULT_X_H2O, HeatTransferAnalyzer,
    MissingHeatTransferInput, missing_heat_transfer_inputs,
    radiation_composition_source)
from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
from hrma.analysis.six_dof_trajectory import _atmosphere_full
from hrma.analysis.water_hammer import FLUID_PROPERTIES, WaterHammerAnalyzer
from hrma.constants import ISA_LAYERS, P_SEA_LEVEL_PA
from hrma.validation.record_adapters import UNIT_TO_SI
from hrma.visualization.advanced_results import SEA_LEVEL_AMBIENT_PA
from hrma.visualization.visualization import NOZZLE_FIG_AMBIENT_PA

KOK = pathlib.Path(__file__).resolve().parents[1]


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


#: OH-D26-01'in süpürdüğü dosyalar. ``hrma/app.py`` LİSTEDE DEĞİLDİR:
#: oradaki üç kullanım app-api sahasıdır ve ``KILITLI_ENVANTER``de durur.
SUPURULEN = (
    'hrma/analysis/nozzle_flow_1d.py',
    'hrma/analysis/six_dof_trajectory.py',
    'hrma/analysis/pressurant_sizing.py',
    'hrma/analysis/water_hammer.py',
    'hrma/validation/record_adapters.py',
    'hrma/visualization/advanced_results.py',
    'hrma/visualization/visualization.py',
)


def _literal_101325(rel):
    """Dosyadaki ``101325`` SAYI literallerinin sayısı (AST; yorum sayılmaz)."""
    agac = ast.parse((KOK / rel).read_text(encoding='utf-8'))
    return sum(
        1 for d in ast.walk(agac)
        if isinstance(d, ast.Constant) and not isinstance(d.value, bool)
        and isinstance(d.value, (int, float)) and d.value == 101325.0)


# ---------------------------------------------------------------- OH-D26-01
class TestOHD2601DenizSeviyesiTekKaynak:
    """P15B2-06 üçüncü ayak — çıplak ``101325`` bu sahada kalmadı.

    ÖLÇÜLDÜ (``once.json`` -> ``sonra.json``, taban 709a235e): sahada
    çıplak literal **8 -> 0**, merkezden ithal eden dosya **0 -> 7**,
    ``tools/sabit_envanteri.py``nin gördüğü ``P_SEA_LEVEL_PA`` ihlali
    **11 -> 3** (kalan üçü ``hrma/app.py``, app-api sahası). Sekiz
    kullanımın DEĞERİ bit-aynı kaldı — bu bir yeniden adlandırmadır,
    fizik değişikliği değildir.
    """

    @pytest.mark.parametrize('rel', SUPURULEN)
    def test_ciplak_literal_kalmadi(self, rel):
        assert _literal_101325(rel) == 0, (
            '%s hâlâ çıplak 101325 literali taşıyor — merkezden '
            '(hrma.constants.P_SEA_LEVEL_PA) ithal edilmeli' % rel)

    @pytest.mark.parametrize('rel', SUPURULEN)
    def test_merkezden_ithal_ediyor(self, rel):
        metin = (KOK / rel).read_text(encoding='utf-8')
        assert 'P_SEA_LEVEL_PA' in metin, (
            '%s literali kaldırmış ama merkezî adı KULLANMIYOR' % rel)

    def test_merkez_YENI_SAYI_yazmiyor(self):
        """Sabit ISA tablosunun kendi taban satırından okunur."""
        assert P_SEA_LEVEL_PA == ISA_LAYERS[0][3]
        assert P_SEA_LEVEL_PA == pytest.approx(101325.0)

    def test_sekiz_kullanimin_DEGERI_bit_ayni(self):
        """Süpürme sayı kaydırmadı (``K1d_degerler`` önce == sonra)."""
        import inspect
        assert (inspect.signature(NozzleFlow1D.__init__)
                .parameters['ambient_pressure'].default) == P_SEA_LEVEL_PA
        assert (inspect.signature(NozzleFlow1D.from_motor_data)
                .parameters['ambient_pressure'].default) == P_SEA_LEVEL_PA
        assert _atmosphere_full(0.0)[2] == P_SEA_LEVEL_PA
        assert FLUID_PROPERTIES['lox']['vapor_pressure_Pa'] == P_SEA_LEVEL_PA
        assert UNIT_TO_SI['atm'] == P_SEA_LEVEL_PA
        assert SEA_LEVEL_AMBIENT_PA == P_SEA_LEVEL_PA
        assert NOZZLE_FIG_AMBIENT_PA == P_SEA_LEVEL_PA

    def test_ISA_tohumu_TABLODAN_okunuyor(self):
        """``_atmosphere_full`` döngü tohumu tablonun taban satırıdır.

        Tohum çıplak yazılınca tablo ile ikinci tanım noktası oluşuyordu:
        ``ISA_LAYERS[0]`` değişse tohum geride kalırdı.
        """
        rho, a, P, T = _atmosphere_full(0.0)
        assert P == ISA_LAYERS[0][3]
        assert T == pytest.approx(ISA_LAYERS[0][1])

    def test_mandal_BAYAT_satir_tasimiyor(self):
        """Ödenen borç ``KILITLI_ENVANTER``de TUTULMAZ (daraltma).

        Bayat bir satır, ileride aynı adla dönen körlüğü sessizce
        affeder. Mandal 11 -> 3'e daraldı; kalan üçü app-api'nin.
        """
        import sys
        sys.path.insert(0, str(KOK / 'tests'))
        from test_d20_altyapi_a1 import KILITLI_ENVANTER
        psl = [k for k in KILITLI_ENVANTER if k[1] == 'P_SEA_LEVEL_PA']
        assert len(psl) == 3, (
            'mandalda %d P_SEA_LEVEL_PA satırı var; ödenen sekizi '
            'düşmeliydi' % len(psl))
        assert {k[0] for k in psl} == {'hrma/app.py'}
        for rel in SUPURULEN:
            assert rel not in {k[0] for k in psl}


# ---------------------------------------------------------------- OH-D25-13
_WP_TABAN = {
    'chamber_pressure': 60.0, 'chamber_temperature': 3400.0,
    'chamber_diameter': 0.15, 'chamber_length': 0.5,
    'burn_time': 20.0, 'mdot_total': 8.0,
    'material': 'steel', 'wall_thickness': 0.005,
    'cooling_type': 'natural', 'n_stations': 11,
}


def _wp(istemci, **ek):
    r = istemci.post('/api/analysis/wall-profile', json=dict(_WP_TABAN, **ek))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _varsayilan(govde, ad):
    for e in (govde.get('inputs_assumed') or []):
        if e.get('field') == ad:
            return e
    return None


class TestOHD2513KompozisyonKokeniYAYIMLANIR:
    """Uç kesirleri TÜKETİYOR (OH-D19-07) ama kökeni SÖYLEMİYORDU.

    ÖLÇÜLDÜ (``once.json`` K2, taban 709a235e; aynı motor, değişen tek
    şey kesirler): ``q_MW`` tepe değeri hiç verilmediğinde 35,508897 —
    ``x_H2O=0,45 / x_CO2=0,20`` ile 35,677326, yalnız ``x_H2O=0,45`` ile
    35,673045, ``x_H2O=0,60 / x_CO2=0,0`` ile 35,794164 MW/m². Yani modül
    varsayılanı SESSİZ bir girdiydi ve dört gövdenin dördünde de kökeni
    söyleyen alan sayısı **0**dı. ``sonra.json``: hiç verilmeyende **5**,
    yalnız birinde **3**; kesirleri gönderen iki gövde BİT-AYNI (üst düzey
    anahtarlar değişmedi, ``q_MW`` tepe değeri değişmedi).
    """

    def test_hic_verilmediginde_IKISI_DE_adiyla_ilan_edilir(self, istemci):
        g = _wp(istemci)
        adlar = sorted(e['field'] for e in (g.get('inputs_assumed') or []))
        assert adlar == ['x_CO2', 'x_H2O'], adlar
        for ad, dfl in (('x_H2O', DEFAULT_X_H2O), ('x_CO2', DEFAULT_X_CO2)):
            e = _varsayilan(g, ad)
            assert e['assumed_value'] == pytest.approx(dfl)
            # Gerekçe ÖLÇÜLMÜŞ etkiyi taşır (uydurma "olabilir" cümlesi değil)
            assert 'q_MW' in e['reason'] and '35.794164' in e['reason']

    def test_koken_etiketi_TEK_TANIM_NOKTASINDAN(self, istemci):
        """Uç ikinci bir köken metni yazmaz; modülün etiketini taşır."""
        g = _wp(istemci)
        beklenen = radiation_composition_source(False, False)
        assert beklenen in _varsayilan(g, 'x_H2O')['reason']
        assert beklenen in _varsayilan(g, 'x_CO2')['reason']

    def test_yalniz_biri_verilince_YALNIZ_eksik_olan_ilan_edilir(self, istemci):
        g = _wp(istemci, x_H2O=0.45)
        adlar = sorted(e['field'] for e in (g.get('inputs_assumed') or []))
        assert adlar == ['x_CO2'], adlar
        kaynak = radiation_composition_source(True, False)
        gerekce = _varsayilan(g, 'x_CO2')['reason']
        assert kaynak in gerekce
        # "ikisini de sen verdin" DEMİYOR
        assert 'caller supplied x_H2O / x_CO2' not in gerekce

    def test_ikisi_de_verilince_govde_BIT_AYNI(self, istemci):
        """Sağlıklı istek yeni alan görmez (ucun kendi doktrini)."""
        g = _wp(istemci, x_H2O=0.45, x_CO2=0.20)
        assert 'inputs_assumed' not in g
        assert sorted(g) == ['inputs_not_used', 'status', 'wall_profile']

    def test_x_CO2_SIFIRI_verilmis_sayilir(self, istemci):
        """``x_CO2 = 0`` FİZİKSEL girdidir (OH-D19-07 kazanımı).

        ``0`` "verilmedi" sayılsaydı beyan yanlış olurdu: uç değeri
        kullanıyor ama "modül varsayılanına düştüm" diyordu.
        """
        g = _wp(istemci, x_H2O=0.60, x_CO2=0.0)
        assert 'inputs_assumed' not in g

    def test_sayiya_cevrilemeyen_kesir_SESSIZCE_dusmuyor(self, istemci):
        """Bozuk kesir yukarıdaki ``except: pass`` ile düşüyordu — sessizdi."""
        g = _wp(istemci, x_H2O='abc')
        e = _varsayilan(g, 'x_H2O')
        assert e is not None, 'bozuk kesir hâlâ sessizce düşüyor'
        assert 'not a number' in e['reason']

    def test_BEYAN_SAYIYI_kaydirmadi(self, istemci):
        """Künye eklemek profili değiştirmedi (``q_MW`` tepe bit-aynı)."""
        g1 = _wp(istemci)
        g2 = _wp(istemci, x_H2O=0.60, x_CO2=0.0)
        t1 = max(v for v in g1['wall_profile']['q_MW'] if v is not None)
        t2 = max(v for v in g2['wall_profile']['q_MW'] if v is not None)
        assert t1 == pytest.approx(35.50889691832093, rel=0, abs=1e-9)
        assert t2 == pytest.approx(35.794163949457115, rel=0, abs=1e-9)

    def test_koken_wall_profile_BLOGUNA_konmadi(self, istemci):
        """D17 hükmü ayakta — ve ÖLÇÜMLE doğrulandı.

        Panel bu bloğu tek tek okumaz, ``/api/fea/thermal`` gövdesine
        AYNEN geçirir; bloğa konan dürüstlük alanı ekrana İNMEZ ve
        ters-yön borcunu büyütür. Kanıt tabanda duruyor: D26/app-api
        a4'ün bloğa koyduğu ``column_basis`` künyesi
        ``tests/test_wave4b_contract.py::TestTersYonBorcEnvanteri::
        test_sagir_alt_bloklar_buyumez``i kırmızıya çevirdi (taban
        ağacında da kırmızı — ölçüldü). Köken bu yüzden YANIT DÜZEYİNDE,
        ucun zaten kurduğu ``inputs_assumed`` sözleşmesiyle ilan edilir.
        """
        wp = _wp(istemci)['wall_profile']
        assert 'radiation_composition_source' not in wp
        # Modül yolu da (D17 bekçisi) aynı hükmü sürdürür.
        p = _sessiz(HeatTransferAnalyzer().analyze_axial_profile,
                    dict(chamber_pressure=60.0, chamber_temperature=3400.0,
                         chamber_diameter=0.15, chamber_length=0.5,
                         burn_time=20.0, mdot_total=8.0), n_stations=11)
        assert 'radiation_composition_source' not in p

    def test_kardes_UC_ayni_soruya_cevap_veriyor(self, istemci):
        """``/analyze_thermal_safety`` kökeni ZATEN söylüyordu.

        İki uç aynı soruya biri cevap verip biri susarak karşılık
        veremez; bu kalemin kusuru tam olarak o sessizlikti.
        """
        r = istemci.post('/analyze_thermal_safety', json=dict(_WP_TABAN))
        assert r.status_code == 200
        gs = r.get_json()['thermal_analysis']['gas_side_analysis']
        assert gs['radiation_composition_source'] == \
            radiation_composition_source(False, False)


# ------------------------------------------------- BEKÇİ BORCU P4B1-01
class TestBekciBorcuP4B101F41UcKapisi:
    """KAPALI kalem; yeniden AÇILMADI — sembolü doğrudan sınayan bekçi.

    P13B4-10 dağıtımı (``p13b410_dagitim.json``) bu kalemi 'defterde
    dosya alanı boş — bekçi hedefi belirsiz' diye borçlu bırakmıştı.
    Kalem: boş gövde 155 yapraklık bir yanıt + 13.027.380 W/m² akı +
    risk HIGH üretiyordu; modül kapısı VARDI ama uç onu çağırmıyordu.
    """

    def test_bos_govde_SAYI_uretmez(self, istemci):
        r = istemci.post('/analyze_thermal_safety', json={})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        j = r.get_json()
        assert j['status'] == 'error'
        metin = r.get_data(as_text=True)
        assert 'q_' not in metin and 'risk' not in metin.lower(), (
            'red gövdesi hâlâ akı/risk sayısı taşıyor')
        assert '13027380' not in metin.replace('.', '').replace(',', '')

    def test_eksik_alanlar_ADIYLA_sayilir(self, istemci):
        r = istemci.post('/analyze_thermal_safety', json={})
        eksik = set(r.get_json().get('missing_fields') or [])
        assert {'chamber_pressure', 'chamber_temperature'} <= eksik, eksik

    def test_UC_ile_MODUL_ayni_listeyi_soyler(self):
        """Tek kaynak: uç listeyi kopyalamaz, modülden okur."""
        assert set(missing_heat_transfer_inputs({})) >= {
            'chamber_pressure', 'chamber_temperature'}
        with pytest.raises(MissingHeatTransferInput):
            _sessiz(HeatTransferAnalyzer().analyze_heat_transfer, {})


# ------------------------------------------------- BEKÇİ BORCU P4B4-01
_WH = dict(fluid='water', line_length_m=100.0, line_id_mm=100.0,
           wall_thickness_mm=6.0, working_pressure_bar=10.0,
           pipe_material='steel_4130', pipe_mawp_bar=500.0)


class TestBekciBorcuP4B401KolonAyrilmasiKapisi:
    """KAPALI kalem; tablonun KENDİ sayıları override verilince kapı
    KAPANMAZ.

    ÖLÇÜLDÜ (kalem metni): su, 100 m × 100 mm × 6 mm, 10 bar, MAWP 500
    bar; tablonun kendi K ve ρ'su override olarak verilince 2 m/s'de
    kolon ayrılması True -> None ve hüküm basıncı 64,38 -> 37,19 bar;
    20 m/s'de hüküm UNSAFE -> SAFE. Doğru ayrım çağrı biçimi değil,
    akışkanın TABLODA olup olmamasıdır.
    """

    @staticmethod
    def _coz(**ek):
        yuk = dict(_WH, flow_velocity_m_s=20.0)
        yuk.update(ek)
        return _sessiz(WaterHammerAnalyzer().analyze, **yuk)

    def test_tablodaki_akiskan_override_ile_OZEL_akiskan_OLMAZ(self):
        rec = FLUID_PROPERTIES['water']
        r = self._coz(bulk_modulus_Pa=rec['bulk_modulus_Pa'],
                      density_kg_m3=rec['density_kg_m3'])
        fp = r['fluid_properties']
        assert fp['record_source'] == 'fluid_table'
        assert sorted(fp['overridden_fields']) == ['bulk_modulus_Pa',
                                                   'density_kg_m3']
        # Buhar basıncı YERİNDE kalır -> kapı kapanmaz.
        assert r['vapor_pressure_Pa'] == pytest.approx(
            rec['vapor_pressure_Pa'])
        assert r['column_separation'] is not None

    def test_iki_cagri_bicimi_AYNI_hukmu_verir(self):
        rec = FLUID_PROPERTIES['water']
        a = self._coz()
        b = self._coz(bulk_modulus_Pa=rec['bulk_modulus_Pa'],
                      density_kg_m3=rec['density_kg_m3'])
        assert a['status'] == b['status']
        assert a['column_separation'] == b['column_separation']
        assert a['peak_pressure_bar'] == pytest.approx(b['peak_pressure_bar'])

    def test_TABLODA_OLMAYAN_akiskan_SAFE_sertifikasi_alamaz(self):
        r = self._coz(fluid='gizemli_sivi', bulk_modulus_Pa=2.2e9,
                      density_kg_m3=998.0, flow_velocity_m_s=0.5,
                      working_pressure_bar=50.0)
        assert r['fluid_properties']['record_source'] == 'user_custom_fluid'
        assert r['vapor_pressure_Pa'] is None
        assert r['column_separation'] is None
        assert r['status'] != WaterHammerAnalyzer.STATUS_SAFE, (
            'buhar basıncı BİLİNMİYORKEN SAFE sertifikası verildi')
