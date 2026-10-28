# -*- coding: utf-8 -*-
"""ÖH Dalga-21 · kulvar **kati** · aşama 1 — onarım bekçileri.

Her sınıf tek bir defter kalemini kilitler. Sayılar
``docs/scofield/raw/OH/D21/kati/a1/once.json`` (kusurlu hâl) ve
``sonra.json`` (onarılmış hâl) dosyalarından gelir; elle yazılmış tek bir
ölçüm yoktur. Ters-mutasyon kanıtı: ``mutasyon.json``.
"""
import ast
import contextlib
import inspect
import io
import re

import pytest

# V301/T-ÇAPA-A: katı örnek motor geometrisi tek tanımdan (çekirdek
# 30 -> 48 mm). Eski Ø100/500/30 @ 40 bar BATES portu boğuluyordu
# (A_p/A_t 0,947) ve K-A port kapısından 422 alıyor; bu dosyadaki
# düğümlerin konusu boğulan port değil (K-A RAPOR §6, kural 1).
from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM  # noqa: E402
_CEKIRDEK_MM = SOLID_DEFAULT_GEOMETRY_MM['core_diameter']



@pytest.fixture
def cea_kapali(monkeypatch):
    """V301/N-CEA-2: NASA CEA kapalı — katı motor katalog (tek basınçlı)
    termokimyasına BEYANLA döner. Bu dosyadaki kayıt/katalog yolu bekçileri
    öncüllerini (motor termokimyası = katalog kaydı) bu yolda korur; CEA
    yolu tests/test_v301_n_cea2.py'de."""
    from hrma.engines import cea_bridge
    monkeypatch.setattr(cea_bridge, 'is_rocketcea_available', lambda: False)

import hrma.engines.solid_rocket_engine as SRE
from hrma.data.propellants_db import PROPELLANTS
from hrma.engines.solid_rocket_engine import (
    SOLID_CASE_CLOSURE_LENGTH_M,
    SOLID_CASE_MATERIAL_EXTRA,
    SOLID_COST_PARAMS,
    SolidRocketEngine,
    _c_star_basis_of_record,
    _c_star_identity_audit,
)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**kw):
    p = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100, grain_length=500, core_diameter=_CEKIRDEK_MM,
             chamber_pressure=40)
    p.update(kw)
    return _sessiz(SolidRocketEngine, **p)


@pytest.fixture(scope='module')
def apcp_sonuc():
    return _sessiz(_motor().calculate_performance)


# =====================================================================
# P2B1-08 — kapak payının TEK tanım noktası
# =====================================================================
class TestP2B1_08KapakPayiTekTanimNoktasi:
    """Kapak payı iki yerde çıplak literaldi; künye 'tek tanım noktası
    artık burası' diyordu (ölçüldü: once.json/P2B1-08, 3 çıplak satır)."""

    def test_sabit_var_ve_degeri_korundu(self):
        assert SOLID_CASE_CLOSURE_LENGTH_M == pytest.approx(0.1)

    def test_kasa_ic_boyu_sabiti_okur(self, monkeypatch):
        """Pay değişince kasa iç boyu AYNI kadar değişmeli.

        Kusurlu hâlde ``_case_inner_length`` çıplak 0.1 yazıyordu ve
        sabit değişse bile boy sabit kalıyordu (once.json:
        boy_0.15 = 0.6, yani hiç kıpırdamadı).
        """
        e = _motor()
        taban = e._case_inner_length()
        monkeypatch.setattr(SRE, 'SOLID_CASE_CLOSURE_LENGTH_M', 0.15)
        assert e._case_inner_length() - taban == pytest.approx(0.05)

    def test_grain_zarf_hacmi_ayni_sabiti_okur(self, monkeypatch):
        """Zarf hacmi payı GERİ ÇIKARIR: pay değişse de hacim değişmez.

        Bu iki iddia birlikte ayrımı tamdır. İki çağrı yeri de sabiti
        okumuyorsa boy testi kırmızıya döner; yalnız BİRİ okuyorsa
        (yarım onarım) pay artınca hacim de kayar ve BU test kırmızıya
        döner — çünkü hacim = pi r^2 (L_grain + araları) olmalıdır.
        """
        e = _motor()
        taban = e._grain_envelope_volume()
        monkeypatch.setattr(SRE, 'SOLID_CASE_CLOSURE_LENGTH_M', 0.15)
        assert e._grain_envelope_volume() == pytest.approx(taban, rel=1e-12)

    def test_urun_kodunda_ciplak_kopya_kalmadi(self):
        kaynak = inspect.getsource(SRE)
        kod = [s for s in kaynak.splitlines()
               if not s.lstrip().startswith('#')]
        kopya = [s.strip() for s in kod
                 if re.search(r'_case_inner_length\(\)\s*-\s*0\.1(?!\d)', s)
                 or re.search(r'L_grain \+ gaps \+ 0\.1(?!\d)', s)]
        assert kopya == [], (
            'Kapak payı yeniden çıplak literal olarak yazılmış: %r' % kopya)


# =====================================================================
# P2B1-09 — yakıt kimliği/özellik KÖKENİ yanıta çıkar
# =====================================================================
class TestP2B1_09YakitKokeniYayimlaniyor:
    """İki künye motorda kuruluyor ama yanıtta HİÇ geçmiyordu
    (once.json: '<YAYIMLANMIYOR>', depo genelinde 0 okuma noktası)."""

    def test_iki_koken_alani_yanitta(self, apcp_sonuc):
        assert apcp_sonuc['propellant_type_source'] == 'endpoint default'
        assert apcp_sonuc['propellant_property_source'] == 'engine table'

    def test_kunye_alani_var(self, apcp_sonuc):
        kunye = apcp_sonuc.get('propellant_source_basis') or ''
        assert 'propellant_type_source' in kunye
        assert 'propellant_property_source' in kunye

    def test_koken_motorun_kendi_degeriyle_ayni(self):
        """Yanıt ikinci bir kaynak kurmaz; motorun alanını yayımlar."""
        e = _motor(propellant_type='kndx')
        r = _sessiz(e.calculate_performance)
        assert r['propellant_type_source'] == e.propellant_type_source
        assert (r['propellant_property_source']
                == e.propellant_property_source)


# =====================================================================
# P2B1-12 — maliyet tablosundaki ölü yoğunluk sütunu
# =====================================================================
class TestP2B1_12MaliyetTablosuYalnizFiyat:

    def test_case_materials_yalnizca_usd_kg(self):
        for aile, deger in SOLID_COST_PARAMS['case_materials'].items():
            assert isinstance(deger, (int, float)), (
                f"'{aile}' yine ikili taşıyor: {deger!r} — yoğunluk sütunu "
                f'geri gelmiş (P2B1-12).')

    def test_kompozit_yogunlugunun_tek_tanim_noktasi(self):
        """Atıf ölü sütuna değil, kaydın kendisine bağlı."""
        rho = _motor(
            overrides={'case_material': 'composite'})._case_density()
        assert rho == pytest.approx(
            SOLID_CASE_MATERIAL_EXTRA['composite']['density'])

    def test_yaniltici_atif_metni_kalkti(self):
        kaynak = inspect.getsource(SRE)
        # 'tek tanım noktası olan SOLID_COST_PARAMS[...]' cümlesi
        assert not re.search(
            r'TEK tanım noktası olan\s*\n?#?\s*SOLID_COST_PARAMS', kaynak)

    def test_kasa_maliyeti_hala_hesaplaniyor(self, apcp_sonuc):
        """Sütun kalkarken fiyat kolu kopmamalı."""
        kalem = apcp_sonuc['cost_analysis']['material_costs_usd']
        assert kalem['case_materials'] is not None
        assert kalem['case_materials'] > 0.0
        assert kalem['unpriced_items'] == []


# =====================================================================
# P2B3-12 — end burner'daki ölü hacim değişkeni
# =====================================================================
class TestP2B3_12EndBurnerOluDegisken:

    def test_atanip_okunmayan_ad_kalmadi(self):
        kaynak = inspect.getsource(
            SolidRocketEngine._analyze_end_burner_grain)
        agac = ast.parse(kaynak.lstrip())
        atanan, okunan = set(), set()
        for d in ast.walk(agac):
            if isinstance(d, ast.Name):
                (atanan if isinstance(d.ctx, ast.Store)
                 else okunan).add(d.id)
        assert sorted(atanan - okunan) == [], (
            'end burner raporunda ölü yerel değişken var (P2B3-12)')

    def test_yayimlanan_hacim_tek_kaynaktan(self):
        e = _motor(grain_type='end_burner')
        r = e._analyze_end_burner_grain()
        assert r['grain_volume'] == pytest.approx(
            e._propellant_volume() * 1e6)
        assert r['propellant_mass'] == pytest.approx(
            e._propellant_volume() * e.rho_p)


# =====================================================================
# P2B4-10 — teorik Isp'de sessiz Pe/Pc kırpması
# =====================================================================
class TestP2B4_10TeorikIspKirpmasi:

    def test_ortam_haznenin_ustundeyken_sayi_yayimlanmaz(self):
        """once.json: Pc=1,0 ve Pc=0,5 bar BİT-AYNI 4,725684670150419 s
        alıyordu; kırpma girdiyi siliyordu."""
        e = _motor()
        assert e._calculate_theoretical_isp(1.0) is None
        assert e._calculate_theoretical_isp(0.5) is None

    @pytest.mark.usefixtures('cea_kapali')
    def test_gecerli_bandda_sayi_bit_ayni_kaldi(self):
        # ÖH KİTAP p1b (B11, §28-36 Ş-3): eski 247,8934603651343 /
        # 176,94719509884675 APCP kaydının geri çözülmüş dörtlüsünden
        # (γ 1,1986, c* 1598,2) türemişti. Beklenen artık kâhinden: Eş. 3-30
        # kapalı biçimi × CEA denge γ_s ve c* (tests/test_kitap_p1b.py).
        from tests.test_kitap_p1b import (
            CEA_DENGE_CSTAR_M_S, CEA_DENGE_GAMMA_S, ideal_isp_optimum_s)
        from hrma.engines.solid_rocket_engine import SEA_LEVEL_PRESSURE_BAR
        e = _motor()
        for pc in (40.0, 5.0):
            assert e._calculate_theoretical_isp(pc) == pytest.approx(
                ideal_isp_optimum_s(CEA_DENGE_GAMMA_S, CEA_DENGE_CSTAR_M_S,
                                    SEA_LEVEL_PRESSURE_BAR / pc), rel=1e-12)

    def test_kunye_alani_yayimlaniyor(self, apcp_sonuc):
        blok = (apcp_sonuc['detailed_analysis']['performance_metrics']
                ['theoretical_vs_actual_isp'])
        # ÖH KİTAP p1b (B11, §28-36 Ş-3): eski 238,95657975449012 geri
        # çözülmüş APCP dörtlüsündendi; ortalama hazne basıncında (tam motor
        # çözümü) ölçülen yeni taban.
        # V301/T-ÇAPA-A: 240,97355643245413 30 mm çekirdekte (boğulan port,
        # K-A 422) ve N-CEA-2 öncesi katalog termokimyasıyla ölçülmüştü.
        # Yeniden ölçüldü: tek tanımın 48 mm'si + ürün yolu (γ, c* motorun
        # Pc'sinde NASA CEA'dan, ``thermochemistry_source`` nasa_cea_at_pc)
        # -> 241,3367656363926 (CEA kapalı aynı motor 242,84579887675298).
        assert blok['theoretical_isp'] == pytest.approx(241.3367656363926,
                                                        rel=1e-12)
        assert 'Eq. 3-30' in (blok.get('theoretical_isp_basis') or '')

    def test_kirpilmis_dalda_kunye_gerekce_veriyor(self):
        """Kazanılamayan sayı için alan boş + gerekçe (sıvı motorla aynı
        sözleşme)."""
        e = _motor(chamber_pressure=40)
        e.ambient_pressure_bar = 60.0
        r = _sessiz(e.calculate_performance)
        blok = (r['detailed_analysis']['performance_metrics']
                ['theoretical_vs_actual_isp'])
        assert blok['theoretical_isp'] is None
        assert 'Not computable' in (blok['theoretical_isp_basis'] or '')


# =====================================================================
# P2B4-11 / P2B4-12 — TransientBallistics sözleşmesi
# =====================================================================
def _hibrit():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    e = _sessiz(
        HybridRocketEngine,
        thrust=3000, burn_time=10, of_ratio=7.96,
        chamber_pressure=20, atmospheric_pressure=1.01325,
        fuel_type='paraffin', oxidizer_type='n2o',
        fuel_density=900, regression_a=1.17e-4, regression_n=0.62,
        l_star=1.0, expansion_ratio=0, nozzle_type='conical')
    _sessiz(e.calculate)
    return e


class TestP2B4_11CozucuTekKullanimlik:

    def test_ikinci_solve_reddediliyor(self):
        """once.json: 2. ve 3. koşu steps_total=1 ile SESSİZCE dönüyordu
        (tank boşalmıştı); sayaçlar birikip '406 of 1 steps' gibi
        imkânsız cümle üretiyordu."""
        from hrma.analysis.transient_ballistics import TransientBallistics
        tb = TransientBallistics(_hibrit(), feed_mode='blowdown',
                                 tank_temperature=293.15)
        ilk = _sessiz(tb.solve)
        assert ilk['flow_separation']['steps_total'] > 100
        with pytest.raises(RuntimeError, match='single-use'):
            tb.solve()

    def test_yeni_nesne_hala_cozuyor(self):
        """Reddin kapsamı NESNEdir: yeni çözücü aynı motoru çözebilmeli."""
        from hrma.analysis.transient_ballistics import TransientBallistics
        e = _hibrit()
        a = _sessiz(TransientBallistics(e, feed_mode='regulated').solve)
        b = _sessiz(TransientBallistics(e, feed_mode='regulated').solve)
        assert a['flow_separation']['steps_total'] == \
            b['flow_separation']['steps_total']

    def test_sayaclar_adim_sayisini_asamaz(self):
        from hrma.analysis.transient_ballistics import TransientBallistics
        s = _sessiz(TransientBallistics(_hibrit(),
                                        feed_mode='regulated').solve)
        fs = s['flow_separation']
        assert fs['steps_floored'] <= fs['steps_total']
        assert fs['steps_zero_clamped'] <= fs['steps_total']


class TestP2B4_12SifirOrnekliCozum:

    def test_cokmuyor_ve_sayi_uydurmuyor(self):
        """once.json: IndexError: list index out of range
        (transient_ballistics.py, float(dthr_arr[-1]))."""
        from hrma.analysis.transient_ballistics import TransientBallistics
        s = _sessiz(TransientBallistics(_hibrit(), feed_mode='regulated',
                                        t_max_factor=0.0).solve)
        assert len(s['time']) == 0
        ero = s['erosion']
        assert ero['status'] == 'no_samples'
        assert ero['final_throat_diameter_mm'] is None
        assert ero['total_recession_mm'] is None
        assert ero['initial_throat_diameter_mm'] > 0.0

    def test_normal_cozumde_ozet_hala_dolu(self):
        from hrma.analysis.transient_ballistics import TransientBallistics
        s = _sessiz(TransientBallistics(_hibrit(),
                                        feed_mode='regulated').solve)
        ero = s['erosion']
        assert ero['status'] == 'computed'
        assert ero['final_throat_diameter_mm'] > 0.0
        assert ero['total_recession_mm'] is not None


# =====================================================================
# P2B4-13 — dört uydurma uçuş sabiti
# =====================================================================
class TestP2B4_13UydurmaUcusSabitleri:

    @pytest.mark.parametrize('ad', ('_estimate_apogee',
                                    '_estimate_max_velocity',
                                    '_estimate_max_acceleration',
                                    '_estimate_flight_time'))
    def test_metot_silindi(self, ad):
        assert not hasattr(SolidRocketEngine, ad), (
            f'{ad} geri gelmiş: HRMA\'nın trajektori çözücüsü yok, bu '
            f'sayılar hiçbir modelden gelmiyordu (P2B4-13).')

    def test_govdesiz_sabit_donduren_estimate_kalmadi(self):
        """Motor sınıfında girdiye bakmayıp tek sabit döndüren
        '_estimate_*' metodu bulunmamalı."""
        agac = ast.parse(inspect.getsource(SRE))
        suclu = []
        for d in ast.walk(agac):
            if not isinstance(d, ast.FunctionDef):
                continue
            if not d.name.startswith('_estimate'):
                continue
            govde = [x for x in d.body
                     if not (isinstance(x, ast.Expr)
                             and isinstance(x.value, ast.Constant)
                             and isinstance(x.value.value, str))]
            if (len(govde) == 1 and isinstance(govde[0], ast.Return)
                    and isinstance(govde[0].value, ast.Constant)
                    and isinstance(govde[0].value.value, (int, float))):
                suclu.append(d.name)
        assert suclu == [], f'gövdesiz sabit döndüren estimate: {suclu}'


# =====================================================================
# OH-D19-22 — X_p > 0 beyan eden kaydın tek-fazlı c*'ı
# =====================================================================
class TestOHD1922YogusmusFazHukmu:

    @pytest.mark.usefixtures('cea_kapali')
    def test_kndx_knsb_artik_tutarli_sayilmiyor(self):
        """D21'de KUSURU KORUYAN hâliyle yazılmıştı, D31'de ÇEVRİLDİ.

        D21 bu bekçiyi "kndx/knsb hâlâ 'two_phase_record_single_phase_c_star'
        sınıfında" diye kilitlemişti; o sınıf D21'in kendi teşhisiydi
        ("sıfır sapma kanıt değil aritmetik artıktır"), çözümü değil.
        D31 kati a1 (OH-D19-22) kusuru ORTADAN KALDIRDI: iki kaydın
        termokimyası knsu/sugar ile AYNI CEA tabanına taşındı, bu yüzden
        eski iddia artık kusurun kendisini savunur. Bekçi, onarılmış
        hükmü kilitleyecek biçimde çevrildi; X_p ve iki-faz açığı
        iddiaları AYNEN korundu (gevşetme yok, tersine sınıf sıkılaştı).
        """
        for k in ('kndx', 'knsb'):
            e = _motor(propellant_type=k)
            a = _c_star_identity_audit(k, e.gamma, e.T_c, e.mw_exhaust,
                                       e.c_star)
            assert a['status'] == 'two_phase_explained', (k, a['status'])
            assert a['condensed_mass_fraction'] == pytest.approx(0.44)
            assert a['identity_is_independent'] is True
            assert a['record_c_star_basis'] == 'cea'

    @pytest.mark.usefixtures('cea_kapali')
    def test_koken_alanlari_iki_sinifi_ayirt_ediyor(self):
        """D31'de ÇEVRİLDİ: D21 "iki sınıf var ama sebebi yayımlanıyor"
        hâlini kilitliyordu; D31 (OH-D19-22 / P9B4-23) SINIF FARKINI
        KALDIRDI. Aynı X_p'yi taşıyan dört kardeş artık aynı CEA
        tabanında ve aynı hüküm sınıfında; bekçi köken alanlarının hâlâ
        yayımlandığını, ama ayrımın kalmadığını kilitler."""
        hukumler = {}
        for k in ('kndx', 'knsb', 'knsu', 'sugar'):
            e = _motor(propellant_type=k)
            hukumler[k] = _c_star_identity_audit(
                k, e.gamma, e.T_c, e.mw_exhaust, e.c_star)
        for k, h in hukumler.items():
            assert h['condensed_mass_fraction'] == pytest.approx(0.44), k
            # köken alanı YAYIMLANMAYA devam ediyor (D21 kazanımı)
            assert h['record_c_star_basis'] == 'cea', k
            assert h['identity_is_independent'] is True, k
        # ve dört kardeş TEK sınıfta
        assert {h['status'] for h in hukumler.values()} == {
            'two_phase_explained'}

    @pytest.mark.usefixtures('cea_kapali')
    def test_bagimsiz_kayitlarin_hukmu_degismedi(self):
        """Onarım yalnız kör noktayı kapatır; bağımsız kaynaklı kayıtlar
        D17'deki hükümlerini korur (once.json ile bit-aynı)."""
        # ÖH KİTAP p1b (B11, §28-36 Ş-3): 'apcp' eski hükmü
        # ('single_phase_consistent') geri çözülmüş dörtlüden; kâhinin denge
        # dörtlüsü tek fazlı idealin ALTINDA (CEA_DENGE_OZDESLIK_SAPMA_YUZDE
        # = −%0,0535, yoğuşkan faz) → iki fazlı açıklanan.
        beklenen = {'apcp': 'two_phase_explained',
                    'double_base': 'single_phase_consistent',
                    'knsu': 'two_phase_explained',
                    'black_powder': 'two_phase_explained'}
        for k, durum in beklenen.items():
            e = _motor(propellant_type=k)
            a = _c_star_identity_audit(k, e.gamma, e.T_c, e.mw_exhaust,
                                       e.c_star)
            assert a['status'] == durum, (k, a['status'])

    def test_koken_baska_bir_sayiya_yapistirilmaz(self):
        """Denetlenen c* kaydın kendi c*'ı değilse köken beyanı
        DÖNMEZ — başka bir kaydın künyesi ödünç alınmaz."""
        # D31: kndx'in kayıtlı c*'ı 912,4 -> 915,9 ve tabanı 'eq3-32' ->
        # 'cea' oldu (OH-D19-22). Bekçinin ASIL iddiası ("köken yalnız
        # kaydın KENDİ sayısı için döner") aynen korunuyor; sayılar
        # merkezî katalogdan OKUNUR, teste kopyalanmaz (tek kaynak).
        _kndx = PROPELLANTS['kndx']['c_star']
        assert _c_star_basis_of_record('kndx', _kndx) == 'cea'
        assert _c_star_basis_of_record('kndx', 912.4) is None
        assert _c_star_basis_of_record('kndx', 800.0) is None
        assert _c_star_basis_of_record('bilinmeyen_yakit', _kndx) is None

    def test_denetim_yaniti_kokeni_tasiyor(self, apcp_sonuc):
        a = apcp_sonuc['c_star_identity_audit']
        assert a['record_c_star_basis'] == 'cea'
        assert a['identity_is_independent'] is True
