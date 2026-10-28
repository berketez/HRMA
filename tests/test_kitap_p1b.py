# -*- coding: utf-8 -*-
"""ÖH KİTAP p1b — B11 (Ö-4): katı APCP referans kaydının termokimyası.

Kalem: ``hrma/data/propellants_db.py`` ``_APCP_REFERENCE`` kaydının T_c'si
(3614,8 K) c*'tan tek gaz formülüyle GERİ çözülmüştü; aynı bileşimin (AP 68 /
Al 18 / HTPB R-45 14, kütlece) NASA CEA denge oda sıcaklığı 68,9 bar'da
3399,65 K'dir. Kulvar önce DUR kuralıyla durdu (rapor
``docs/scofield/raw/OH/KITAP/p1b/rapor.md`` §3): kaydı CEA ile tutarlı
düzeltmek boğaz ısı akısını +%27,2 değiştiriyordu, çünkü motorun Bartz
zinciri "donmuş" cp ve Pr'yi kaydın gamma'sından türetiyor ve CEA'nın denge
gamma_s'si bu formüle girince cp %41 şişiyor.

UYGULANAN: seçenek F (ana model kararı, 12 Eki 2026; rapor "Seçenek F
uygulaması"). Kayıt CEA DENGE dörtlüsünü taşır (genleşme ve performans);
Bartz gaz özellikleri ayrı ``gamma_frozen_chamber`` alanından (CEA DONMUŞ oda
gamma_s'si) türetilir. Motorun 'apcp' tablosu artık kataloğun ikinci kopyası
değil, ondan türetilir (tek tanım).

Bu dosyanın bekçileri:

1. Bağımsız kâhin (RocketCEA / CEA2) aynı bileşimin dörtlüsünü yeniden
   üretir. Aşağıdaki ``CEA_*`` sabitleri depodaki TEK kâhin kaynağıdır;
   APCP beklentisi taşıyan öteki testler buradan içe aktarır (H-9).
2. CEA'nın iki dörtlüsü (kaydırmalı denge, donmuş) tek fazlı c* özdeşliğini
   %0,1 içinde sağlar.
3. B11 düzeltildi: iki katalog kaydı ('apcp', 'htpb_ap_al') kâhinin denge
   dörtlüsünü ve donmuş oda gamma'sını taşır.
4. Seçenek F'nin bağlantıları: motor tablosu katalogdan türer; iki yakıt adı
   aynı sonucu verir; Bartz zinciri (boğaz/hazne akısı, lüle malzeme marjı,
   yayımlanan kurtarma sıcaklığı) donmuş gamma'yı kullanır ve aynı istasyonun
   tek bir T_aw'ı vardır; gamma ezilirse donmuş değer uygulanmaz; öteki bütün
   katı iticiler tek gamma ile (bit-özdeş) kalır; alan her kayıtta vardır ve
   yükleme anında denetlenir.
5. 3. tur (karar §28-47): iki faz modülü CEA karışım çiftiyle (GAMMAs,
   M(1/n)) etkin özellik ÜRETMEZ (çift sayma, Ş2-2 (a)); eksenel duvar
   profili Bartz'ı motorla aynı gaz çiftiyle kurar (Ş2-1 / D-F3); kayda
   yakın gamma ezmeleri donmuş değeri almaz (Ş2-6).
"""

import math
import re

import pytest


@pytest.fixture
def cea_kapali(monkeypatch):
    """V301/N-CEA-2: NASA CEA kapalı — katı motor katalog (tek basınçlı)
    termokimyasına BEYANLA döner. Bu dosyadaki kayıt/katalog yolu bekçileri
    öncüllerini (motor termokimyası = katalog kaydı) bu yolda korur; CEA
    yolu tests/test_v301_n_cea2.py'de."""
    from hrma.engines import cea_bridge
    monkeypatch.setattr(cea_bridge, 'is_rocketcea_available', lambda: False)

from hrma.constants import G_0, PSIA_PER_BAR, R_UNIVERSAL
from hrma.data import propellants_db
from hrma.data.propellants_db import PROPELLANTS, cstar_from_thermo

# ---------------------------------------------------------------------------
# Kâhin girdisi (CEA reaktan kartları) ve beklenen dörtlüler — TEK KAYNAK.
# Kaynak: NASA RP-1311 (Gordon & McBride 1994) kodu, RocketCEA sarmalayıcısı;
# koşum kanıtı docs/scofield/raw/OH/KITAP/p1b/kanit/cea_P1B_68.9bar_eps10_*.out
# ---------------------------------------------------------------------------
APCP_CEA_KARTI = (
    ' name NH4CLO4(I) wt%=68.00 t(k)=298.15 \n'
    ' name AL(cr) AL 1 wt%=18.00 h,cal=0.0 t(k)=298.15 \n'
    ' name R-45(HTPB) C 7.3165 H 10.3360 O 0.1063 wt%=14.00 '
    'h,cal=1200.0 t(k)=298.15 \n')
APCP_CEA_BASINC_BAR = 68.9

CEA_ODA_T_C_K = 3399.65              # oda (sonsuz kesitli hazne), K
CEA_M_1N_KG_KMOL = 27.829            # M(1/n), yoğuşkan faz dahil
CEA_DENGE_GAMMA_S = 1.1338           # oda, kaydırmalı denge
CEA_DENGE_CSTAR_M_S = 1585.4
CEA_DONMUS_GAMMA_S = 1.1862          # oda, donmuş bileşim
CEA_DONMUS_CSTAR_M_S = 1560.0
CEA_DONMUS_CP_KJ_KGK = 1.9031        # oda, donmuş bileşim Cp (yoğuşkan dahil)

# CEA çıktısının yazdığı ondalık hane yarısı kadar (yuvarlama payı).
TOL_T_K = 0.01
TOL_GAMMA = 0.00005
TOL_CSTAR_M_S = 0.05
TOL_M = 0.0005
TOL_CP_KJ_KGK = 0.00005
# Tek fazlı özdeşlik payı: CEA M(1/n) ve gamma_s iki fazlı karışımın
# değerleridir; ölçülen sapma −%0,053 (denge) ve −%0,032 (donmuş).
OZDESLIK_TOL_YUZDE = 0.1

#: Donmuş oda gamma'sı taşıyan katalog kayıtları (aynı fiziksel yakıt).
APCP_ANAHTARLARI = ('apcp', 'htpb_ap_al')

#: Standart durum sıcaklığı [K] (RP-1311; CEA kartının reaktan sıcaklığı).
#: Tepkime entalpisinin tanımı: ürünleri bu sıcaklıktan T_c'ye çıkaran ısı.
STANDART_REFERANS_T_K = 298.15

#: 2. tur (§28-36 Ş-2 A) ısıl kâhin payı [%]. Motor R'yi Eş. 3-32 ile c*'tan
#: türetir (R = (c*·Γ)²/T_c); c* tek fazlı idealden en çok
#: OZDESLIK_TOL_YUZDE saptığı için R ∝ c*² iki katı sapabilir.
TERMAL_KAHIN_TOL_YUZDE = 2.0 * OZDESLIK_TOL_YUZDE


# ---------------------------------------------------------------------------
# Kâhinden türeyen kapalı biçimler — ürün kodundan BAĞIMSIZ (testte yazılı).
# APCP beklentisi taşıyan öteki testler sayıyı buradan alır, literal yazmaz.
# ---------------------------------------------------------------------------
def tek_faz_ideal_c_yildiz(gamma, t_c_k, m_kg_kmol):
    """Tek fazlı ideal c* [m/s] — Sutton & Biblarz 9. baskı Eş. 3-32:
    c* = sqrt(R_u·T_c/M) / Γ(γ), Γ = sqrt(γ)·(2/(γ+1))^((γ+1)/(2(γ−1)))."""
    gam = math.sqrt(gamma) * (2.0 / (gamma + 1.0)) ** (
        (gamma + 1.0) / (2.0 * (gamma - 1.0)))
    return math.sqrt(R_UNIVERSAL / m_kg_kmol * t_c_k) / gam


def optimum_genlesme_orani(gamma, pc_pe_orani):
    """İzantropik optimum alan oranı ε (P_e = P_a) — Sutton & Biblarz 9.
    baskı Eş. 3-25/3-26: M_e² = 2/(γ−1)·((P_c/P_e)^((γ−1)/γ) − 1),
    ε = (1/M_e)·[(2/(γ+1))·(1 + (γ−1)/2·M_e²)]^((γ+1)/(2(γ−1)))."""
    me2 = 2.0 / (gamma - 1.0) * (pc_pe_orani ** ((gamma - 1.0) / gamma) - 1.0)
    return (1.0 / math.sqrt(me2)) * (
        (2.0 / (gamma + 1.0)) * (1.0 + (gamma - 1.0) / 2.0 * me2)) ** (
        (gamma + 1.0) / (2.0 * (gamma - 1.0)))


def ideal_isp_optimum_s(gamma, c_yildiz_m_s, pa_pc_orani):
    """İdeal (kayıpsız) Isp [s], optimum genişleme P_e = P_a — Sutton &
    Biblarz 9. baskı Eş. 3-30 (C_F) × c* / g0. Kâhin sabitleriyle çağrılır
    (2. tur Ş-3: test_d21 teorik Isp çapaları buradan)."""
    g = gamma
    cf = math.sqrt(2.0 * g * g / (g - 1.0)
                   * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0))
                   * (1.0 - pa_pc_orani ** ((g - 1.0) / g)))
    return cf * c_yildiz_m_s / G_0


def tepkime_entalpisi_kahin_mj_kg():
    """Tepkime entalpisi kâhini [MJ/kg]: CEA donmuş oda Cp'si × (T_c − T_ref).
    Motorun tanımıyla aynı büyüklük (ürünleri alev sıcaklığına çıkaran ısı),
    sayılar yalnız kâhinden (§28-36 Ş-2 A)."""
    return CEA_DONMUS_CP_KJ_KGK * (CEA_ODA_T_C_K - STANDART_REFERANS_T_K) / 1e3


def termal_verim_kahin_yuzde(pc_pa_orani):
    """Termal verim kâhini [%] = ½·v_j² / q_tepkime. v_j izantropik
    GENLEŞMEDİR (Sutton & Biblarz 9. baskı Eş. 3-16; denge γ_s ve
    R = R_u/M, kâhin sabitleri), q_tepkime ``tepkime_entalpisi_kahin_mj_kg``."""
    g = CEA_DENGE_GAMMA_S
    r_gaz = R_UNIVERSAL / CEA_M_1N_KG_KMOL
    vj2 = 2.0 * g * r_gaz / (g - 1.0) * CEA_ODA_T_C_K * (
        1.0 - (1.0 / pc_pa_orani) ** ((g - 1.0) / g))
    return 100.0 * 0.5 * vj2 / (tepkime_entalpisi_kahin_mj_kg() * 1e6)


#: Kâhin denge dörtlüsünün tek fazlı ideal c*'ı ve CEA c*'ının ondan sapması
#: (iki fazlı karışım: negatif; motorun c* kimlik denetiminin beklenen girdisi).
CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S = tek_faz_ideal_c_yildiz(
    CEA_DENGE_GAMMA_S, CEA_ODA_T_C_K, CEA_M_1N_KG_KMOL)
CEA_DENGE_OZDESLIK_SAPMA_YUZDE = 100.0 * (
    CEA_DENGE_CSTAR_M_S - CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S
) / CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S


def _cea_ciktisi(frozen):
    rocketcea = pytest.importorskip('rocketcea')  # noqa: F841
    from hrma.engines.cea_bridge import ensure_isolated_cea_data_dir
    ensure_isolated_cea_data_dir()
    from rocketcea.cea_obj import CEA_Obj, add_new_propellant
    add_new_propellant('APCP_KITAP_P1B', APCP_CEA_KARTI)
    obj = CEA_Obj(propName='APCP_KITAP_P1B')
    return obj.get_full_cea_output(
        Pc=APCP_CEA_BASINC_BAR * PSIA_PER_BAR, eps=10.0, short_output=1,
        output='siunits', frozen=frozen, frozenAtThroat=0)


def _ilk_sutun(metin, etiket):
    m = re.search(r'^\s*' + re.escape(etiket) + r'\s+([0-9.]+)', metin,
                  re.MULTILINE)
    assert m, f'CEA çıktısında {etiket!r} satırı yok'
    return float(m.group(1))


@pytest.mark.parametrize('donmus, gamma_s, cstar', [
    (0, CEA_DENGE_GAMMA_S, CEA_DENGE_CSTAR_M_S),
    (1, CEA_DONMUS_GAMMA_S, CEA_DONMUS_CSTAR_M_S),
])
def test_cea_kahini_apcp_dortlusunu_yeniden_uretir(donmus, gamma_s, cstar):
    s = _cea_ciktisi(donmus)
    assert _ilk_sutun(s, 'T, K') == pytest.approx(CEA_ODA_T_C_K, abs=TOL_T_K)
    assert _ilk_sutun(s, 'M, (1/n)') == pytest.approx(CEA_M_1N_KG_KMOL,
                                                       abs=TOL_M)
    assert _ilk_sutun(s, 'GAMMAs') == pytest.approx(gamma_s, abs=TOL_GAMMA)
    assert _ilk_sutun(s, 'CSTAR, M/SEC') == pytest.approx(cstar,
                                                          abs=TOL_CSTAR_M_S)


def test_cea_kahini_donmus_oda_cp_sini_yeniden_uretir():
    """2. tur (§28-36 Ş-2 A) kâhini: donmuş bileşimli oda Cp'si aynı CEA
    koşumundan yeniden üretilir ve donmuş gamma_s ile cp = γR_u/(M(γ−1))
    kapalı biçimine tutarlıdır (yoğuşkan faz dahil M(1/n))."""
    s = _cea_ciktisi(1)
    assert _ilk_sutun(s, 'Cp, KJ/(KG)(K)') == pytest.approx(
        CEA_DONMUS_CP_KJ_KGK, abs=TOL_CP_KJ_KGK)
    g = CEA_DONMUS_GAMMA_S
    cp_kapali = g * R_UNIVERSAL / CEA_M_1N_KG_KMOL / (g - 1.0) / 1e3
    assert cp_kapali == pytest.approx(CEA_DONMUS_CP_KJ_KGK,
                                      rel=OZDESLIK_TOL_YUZDE / 100.0)


@pytest.mark.parametrize('gamma_s, cstar', [
    (CEA_DENGE_GAMMA_S, CEA_DENGE_CSTAR_M_S),
    (CEA_DONMUS_GAMMA_S, CEA_DONMUS_CSTAR_M_S),
])
def test_cea_dortlusu_tek_faz_c_yildiz_ozdesligini_saglar(gamma_s, cstar):
    ideal = cstar_from_thermo(gamma_s, CEA_ODA_T_C_K, CEA_M_1N_KG_KMOL)
    assert abs(cstar - ideal) / ideal * 100.0 < OZDESLIK_TOL_YUZDE


def test_kahin_kapali_bicimi_urun_tanimiyla_ayni():
    """Testte yazılı Eş. 3-32 kapalı biçimi ürünün tanım noktasıyla
    (``cstar_from_thermo``) aynı sayıyı verir; iki taraf ayrışırsa kâhinden
    türeyen beklentiler (D-8 testleri) sessizce kayardı."""
    for g in (CEA_DENGE_GAMMA_S, CEA_DONMUS_GAMMA_S):
        assert tek_faz_ideal_c_yildiz(
            g, CEA_ODA_T_C_K, CEA_M_1N_KG_KMOL) == pytest.approx(
                cstar_from_thermo(g, CEA_ODA_T_C_K, CEA_M_1N_KG_KMOL),
                rel=1e-12)


# ---------------------------------------------------------------------------
# B11 düzeltildi — kayıt (açık kusur bekçilerinin çevrilmiş hâli)
# ---------------------------------------------------------------------------
def test_B11_duzeltildi_kayit_dortlusu_c_yildiz_ozdesligini_saglar():
    """ÇEVRİLDİ (eski: ``test_yalniz_T_c_duzeltmesi_kaydi_c_yildizla_
    celistirir``). Eski test seçenek B'nin (yalnız T_c) yasaklılığını
    BUGÜNKÜ canlı kaydın gamma, M ve c*'ı üzerinde sınıyordu; beyanı "B11
    düzeltmesi gelince KIRMIZI olur, çevrilir" idi. Düzeltme geldi: kaydın
    dörtlüsü tek bir CEA koşumundandır, özdeşliği iki fazlı payla (%0,1)
    sağlar ve c* tek fazlı idealin ÜSTÜNE çıkmaz (kalem 3).
    """
    rec = PROPELLANTS['apcp']
    ideal = cstar_from_thermo(rec['gamma'], rec['flame_temperature'],
                              rec['molecular_weight'])
    sapma_yuzde = 100.0 * (rec['c_star'] - ideal) / ideal
    assert abs(sapma_yuzde) < OZDESLIK_TOL_YUZDE
    assert rec['c_star'] <= ideal * (1.0 + OZDESLIK_TOL_YUZDE / 100.0)


@pytest.mark.parametrize('anahtar', APCP_ANAHTARLARI)
def test_B11_duzeltildi_kayit_CEA_denge_dortlusunu_tasir(anahtar):
    """ÇEVRİLDİ (eski: ``test_B11_acik_kusur_bekcisi_kayit_T_c_CEA_denge_
    degeri_degil``; ölçülen 215,15 K sapmayı sabitliyordu). Kayıt artık
    kâhinin kaydırmalı denge dörtlüsünü ve donmuş oda gamma'sını taşır."""
    rec = PROPELLANTS[anahtar]
    assert rec['flame_temperature'] == pytest.approx(CEA_ODA_T_C_K,
                                                     abs=TOL_T_K)
    assert rec['c_star'] == pytest.approx(CEA_DENGE_CSTAR_M_S,
                                          abs=TOL_CSTAR_M_S)
    assert rec['gamma'] == pytest.approx(CEA_DENGE_GAMMA_S, abs=TOL_GAMMA)
    assert rec['molecular_weight'] == pytest.approx(CEA_M_1N_KG_KMOL,
                                                    abs=TOL_M)
    assert rec['gamma_frozen_chamber'] == pytest.approx(CEA_DONMUS_GAMMA_S,
                                                        abs=TOL_GAMMA)


def _kunye_sayisi(metin, desen):
    m = re.search(desen, metin)
    assert m, f'künye metninde {desen!r} yok'
    return float(m.group(1))


def test_B11_kunye_metni_kayit_degerlerinden():
    """2. tur (denetim Ş-6, H-9): 'apcp' künyesinin taşıdığı sayılar
    kaydın kendi değerleridir (metin ⟷ değer). Künye ``_APCP_REFERENCE``'tan
    türetilir; biri metne ikinci bir literal yazarsa ya da kayıt değişip
    metin kalırsa bu bekçi KIRMIZI olur. Basınç kâhinin koşum basıncıdır."""
    rec = PROPELLANTS['apcp']
    k = rec['source']
    sayi = r'(-?[0-9]+(?:\.[0-9]+)?)'
    assert _kunye_sayisi(k, r'Pc = ' + sayi + r' bar') == APCP_CEA_BASINC_BAR
    assert _kunye_sayisi(k, r'chamber T = ' + sayi + ' K') == rec[
        'flame_temperature']
    assert _kunye_sayisi(k, r'c\* = ' + sayi + ' m/s') == rec['c_star']
    assert _kunye_sayisi(k, r'gamma_s = ' + sayi + ',') == rec['gamma']
    assert _kunye_sayisi(k, r'M\(1/n\) = ' + sayi + ' kg/kmol') == rec[
        'molecular_weight']
    assert _kunye_sayisi(k, r'gamma_frozen_chamber = ' + sayi) == rec[
        'gamma_frozen_chamber']
    ideal = cstar_from_thermo(rec['gamma'], rec['flame_temperature'],
                              rec['molecular_weight'])
    assert _kunye_sayisi(k, r'identity to ' + sayi + '%') == round(
        100.0 * (rec['c_star'] - ideal) / ideal, 2)
    # Paylaşan kayıt kendi sayısını yazmaz, 'apcp'ye gönderir.
    assert not re.search(r'[0-9]{4}\.[0-9]', PROPELLANTS['htpb_ap_al'][
        'source'])


# ---------------------------------------------------------------------------
# Seçenek F — motor bağlantıları
# ---------------------------------------------------------------------------
def _motor(**kw):
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    return SolidRocketEngine(**kw)


def _yol(sonuc, yol):
    o = sonuc
    for parca in yol.split('.'):
        o = o[parca]
    return o


#: apcp ⟷ htpb_ap_al karşılaştırmasında okunan yayımlanmış yapraklar.
_KIYAS_YAPRAKLARI = (
    'thermal_analysis.heat_transfer.convective_heat_flux_kw_m2',
    'heat_transfer_analysis.gas_side_analysis.chamber_heat_flux',
    'thermal_analysis.heat_transfer.case_temperature_k',
    'thermal_analysis.combustion_thermal.flame_temperature_k',
    'nozzle_material_analysis.adiabatic_wall_temperature_k',
    'nozzle_material_analysis.thermal_margin_k',
    'nozzle_design.performance.throat_recovery_temperature_k',
    'nozzle_design.performance.throat_gas_static_temperature_k',
    'nozzle_design.performance.exit_temperature_k',
    'specific_impulse', 'isp_vacuum', 'average_thrust', 'total_impulse',
    'throat_diameter', 'expansion_ratio', 'c_star', 'gamma',
    'two_phase_loss.two_phase_loss_pct',
)


@pytest.mark.usefixtures('cea_kapali')
def test_B11_motor_tablosu_katalogdan_turer(monkeypatch):
    """D-1 kapandı (tek tanım): motorun 'apcp' termokimyası katalog kaydının
    ikinci kopyası değil, ondan okunan değerdir. Kayıt süreç içinde
    değiştirilince motor onu izler; değiştirilmemiş kayıtta motor = kâhin."""
    e = _motor(propellant_type='apcp')
    assert e.propellant_property_source == 'engine table'
    assert e.T_c == pytest.approx(CEA_ODA_T_C_K, abs=TOL_T_K)
    assert e.c_star_theoretical == pytest.approx(CEA_DENGE_CSTAR_M_S,
                                                 abs=TOL_CSTAR_M_S)
    assert e.gamma == pytest.approx(CEA_DENGE_GAMMA_S, abs=TOL_GAMMA)
    assert e.mw_exhaust == pytest.approx(CEA_M_1N_KG_KMOL, abs=TOL_M)
    assert e.gamma_frozen_chamber == pytest.approx(CEA_DONMUS_GAMMA_S,
                                                   abs=TOL_GAMMA)

    kayit = PROPELLANTS['apcp']
    isaret = {'flame_temperature': 3000.0, 'c_star': 1500.0,
              'gamma': 1.15, 'molecular_weight': 30.0,
              'gamma_frozen_chamber': 1.2, 'density': 1700.0}
    for alan, deger in isaret.items():
        monkeypatch.setitem(kayit, alan, deger)
    m = _motor(propellant_type='apcp')
    assert (m.T_c, m.c_star_theoretical, m.gamma, m.mw_exhaust,
            m.gamma_frozen_chamber, m.rho_p) == (
        3000.0, 1500.0, 1.15, 30.0, 1.2, 1700.0)


def test_B11_apcp_ve_htpb_ap_al_ayni_sonucu_verir():
    """Aynı fiziksel yakıtın iki adı (motor tablosu yolu ⟷ katalog satırı
    yolu) aynı geometride aynı yayımlanmış sayıları verir. Şart turu Ş-2,
    yalnız katalog düzeltilseydi bu iki yolun boğaz akısında %27'ye varan
    fark verdiğini ölçmüştü."""
    a = _motor(propellant_type='apcp')
    b = _motor(propellant_type='htpb_ap_al')
    assert b.propellant_property_source.startswith('central catalogue')
    ra, rb = a.calculate_performance(), b.calculate_performance()
    farkli = {}
    for yol in _KIYAS_YAPRAKLARI:
        va, vb = _yol(ra, yol), _yol(rb, yol)
        if va != pytest.approx(vb, rel=1e-12, abs=0.0):
            farkli[yol] = (va, vb)
    assert farkli == {}
    assert (ra['c_star_identity_audit']['status']
            == rb['c_star_identity_audit']['status'])
    assert a._bartz_gas_gamma() == b._bartz_gas_gamma() == pytest.approx(
        CEA_DONMUS_GAMMA_S, abs=TOL_GAMMA)


@pytest.mark.usefixtures('cea_kapali')
def test_B11_bartz_zinciri_donmus_gamma_kullanir():
    """Bartz gaz özellikleri donmuş oda gamma'sından türer (kapalı biçimle
    bağımsız hesaplanan cp ve T_aw'a eşit). Boğaz istasyonunun yayımlanan
    üç T_aw'ı (ısı akısı zinciri, lüle malzeme marjı, performans bloğundaki
    kurtarma sıcaklığı) tek değerdir. Genleşme denge gamma'sıyla kalır."""
    e = _motor(propellant_type='apcp')
    r = e.calculate_performance()
    assert e._bartz_gas_gamma() == pytest.approx(CEA_DONMUS_GAMMA_S,
                                                 abs=TOL_GAMMA)
    # Kapalı biçim: donmuş cp = γR/(γ−1); Pr = 4γ/(9γ−5) (Eucken, Sutton &
    # Biblarz Eş. 8-23); T_aw = T_c(1 + r·m)/(1 + m), r = Pr^(1/3),
    # m = (γ−1)/2 (boğaz, M = 1).
    g = CEA_DONMUS_GAMMA_S
    cp_beklenen = g * (R_UNIVERSAL / CEA_M_1N_KG_KMOL) / (g - 1.0)
    pr = 4.0 * g / (9.0 * g - 5.0)
    m2 = (g - 1.0) / 2.0
    taw_beklenen = CEA_ODA_T_C_K * (1.0 + pr ** (1.0 / 3.0) * m2) / (1.0 + m2)
    _h, taw_bogaz, cp_bogaz = e._throat_gas_side()
    _hc, _tawc, cp_hazne = e._chamber_gas_side()
    assert cp_bogaz == pytest.approx(cp_beklenen, rel=1e-9)
    assert cp_hazne == pytest.approx(cp_beklenen, rel=1e-9)
    assert taw_bogaz == pytest.approx(taw_beklenen, rel=1e-9)
    perf = r['nozzle_design']['performance']
    assert perf['throat_recovery_temperature_k'] == pytest.approx(
        taw_bogaz, rel=1e-12)
    assert (r['nozzle_material_analysis']['adiabatic_wall_temperature_k']
            == round(taw_bogaz, 1))
    # Genleşme denge gamma'sıyla: statik boğaz sıcaklığı T_c·2/(γ+1).
    assert perf['throat_gas_static_temperature_k'] == pytest.approx(
        CEA_ODA_T_C_K * 2.0 / (CEA_DENGE_GAMMA_S + 1.0), rel=1e-9)
    assert r['gamma'] == pytest.approx(CEA_DENGE_GAMMA_S, abs=TOL_GAMMA)


def test_B11_gamma_ezilirse_donmus_deger_uygulanmaz():
    """Donmuş değer yalnız ait olduğu kayda uygulanır. Kullanıcı gamma'yı
    başka bir değere ezerse (ör. sayfanın form varsayılanı 1,25) Bartz
    zinciri bugünkü gibi motorun gamma'sını kullanır; katalog satırı
    seçilince (form kaydın kendi değerlerini gönderir) donmuş değer geçerli
    kalır; yalnız T_c ezilirse gamma kaydınkidir, donmuş değer geçerlidir."""
    ezik = _motor(propellant_type='apcp', overrides={'gamma': 1.25})
    assert ezik.gamma == 1.25
    assert ezik._bartz_gas_gamma() is ezik.gamma
    assert ezik._frozen_gas_gamma() is ezik.gamma

    # 3. tur (denetim Ş2-6; 2. tur denetiminde D2-7 YAŞIYORDU): kayda YAKIN
    # ezmeler de donmuş değeri almaz. Eşleşme payı yalnız kayan nokta
    # gürültüsüdür; 1,25 kayıttan %10,25 uzak olduğu için %10'luk bir pay
    # onu yine dışarıda bırakıyor, bu iki ezmeyi ise yanlışlıkla eşliyordu.
    for yakin in (1.15, CEA_DENGE_GAMMA_S * (1.0 + 1e-6)):
        m = _motor(propellant_type='apcp', overrides={'gamma': yakin})
        assert m.gamma == yakin
        assert m._frozen_gas_gamma() is m.gamma, yakin
        assert m._bartz_gas_gamma() is m.gamma, yakin

    rec = PROPELLANTS['apcp']
    satir = _motor(propellant_type='apcp', overrides={
        'density': rec['density'], 'char_velocity': rec['c_star'],
        'gamma': rec['gamma'], 'flame_temp': rec['flame_temperature'],
        'molecular_weight': rec['molecular_weight']})
    assert satir._bartz_gas_gamma() == pytest.approx(CEA_DONMUS_GAMMA_S,
                                                     abs=TOL_GAMMA)

    yalniz_tc = _motor(propellant_type='apcp', overrides={'flame_temp': 3200})
    assert yalniz_tc._bartz_gas_gamma() == pytest.approx(CEA_DONMUS_GAMMA_S,
                                                         abs=TOL_GAMMA)


#: APCP dışındaki bütün katalog kayıtları + motor tablosunda olup katalog
#: dışında kalan / bilinmeyen bir ad (jenerik yer tutucu yolu).
_TEK_GAMMA_ANAHTARLARI = tuple(
    sorted(set(PROPELLANTS) - set(APCP_ANAHTARLARI))) + ('bilinmeyen_yakit',)


@pytest.mark.parametrize('anahtar', _TEK_GAMMA_ANAHTARLARI)
def test_B11_diger_katilar_tek_gamma_ile_kalir(anahtar):
    """Bit-özdeşlik bekçisi: donmuş değeri ölçülmemiş her itici (KNDX,
    KNSB, KNSU, KNER, şeker, PBAN, çift bazlı, kara barut, metalsiz AP,
    Blue Thunder, jenerik yer tutucu) Bartz zincirine motorun gamma
    NESNESİNİN KENDİSİNİ verir — seçenek F onlarda hiçbir sayıyı
    değiştiremez. Aile temsilcisi 'apcp'den donmuş değer DEVRALINMAZ
    (pban_ap_al, apcp_nonaluminized, blue_thunder kompozit ailesindedir)."""
    if anahtar in PROPELLANTS:
        assert PROPELLANTS[anahtar]['gamma_frozen_chamber'] is None
    e = _motor(propellant_type=anahtar)
    assert e.gamma_frozen_chamber is None
    assert e._bartz_gas_gamma() is e.gamma
    # 2. tur (Ş-2 A): ısıl cp ve iki faz gaz-yalnız gamma'sı aynı kuraldan.
    assert e._frozen_gas_gamma() is e.gamma
    # 3. tur (§28-47 Ş2-2 (a)): CEA karışım kaydı değil → iki faz modülünün
    # yoğuşkan-faz kapısı hiç tetiklenemez (M referansı yok).
    assert e._mw_frozen_record_ref is None


def test_B11_katalog_alani_her_kayitta_var_ve_denetlenir(monkeypatch):
    """İstemci sözleşmesi (tüm kayıtlar aynı alan kümesi) korunur: alan her
    kayıtta vardır, yalnız APCP kayıtlarında sayıdır. Yükleme denetimi
    fail-closed: bant dışı, sayı olmayan ya da denge gamma'sının altındaki
    donmuş değer reddedilir."""
    dolu = {k for k, r in PROPELLANTS.items()
            if r['gamma_frozen_chamber'] is not None}
    assert dolu == set(APCP_ANAHTARLARI)
    for anahtar in APCP_ANAHTARLARI:
        rec = PROPELLANTS[anahtar]
        assert rec['gamma_frozen_chamber'] >= rec['gamma']

    kndx = PROPELLANTS['kndx']
    # 2. tur (denetim Ş-5): 1,6 bandın ÜSTÜNDE ve denge gamma'sından BÜYÜK —
    # yalnız bant denetimine takılır (1,0 donmuş < denge denetimine de
    # takıldığından bandın üst sınırını sınamıyordu; MD8 yaşıyordu).
    lo, hi = propellants_db._PHYSICAL_RANGES['gamma']
    bant_ustu = 1.6
    assert bant_ustu > hi and bant_ustu > kndx['gamma']
    for kotu in (1.0, kndx['gamma'] - 0.01, bant_ustu, 'yanlis', True):
        monkeypatch.setitem(kndx, 'gamma_frozen_chamber', kotu)
        with pytest.raises(ValueError):
            propellants_db._attach_frozen_chamber_gamma()
    monkeypatch.setitem(kndx, 'gamma_frozen_chamber', None)
    propellants_db._attach_frozen_chamber_gamma()


# ---------------------------------------------------------------------------
# 2. tur — karar §28-36 Ş-2 A (ÖNEMLİ): donmuş oda gamma'sı öteki "donmuş"
# formül tüketicilerine (ısıl analiz cp'si, iki faz gaz-yalnız gamma'sı)
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures('cea_kapali')
def test_B11_S2A_isil_analiz_donmus_cp_ile_kahine_doner():
    """Tepkime entalpisi, ısı salım gücü ve termal verim kâhine döner.

    1. turda cp = γR/(γ−1)'e DENGE γ_s girdiği için tepkime entalpisi
    7,844 MJ/kg (+%32) ve termal verim %38,6 yayımlanıyordu. Kâhin: CEA
    donmuş oda Cp'si × (T_c − 298,15 K) ve Eş. 3-16 jet hızı (denge γ_s).
    Isı salım gücü çözülmüş kütle üretim serisi × tepkime entalpisidir.
    Jet hızı genleşmedir, denge gamma'sıyla kalır (kapalı biçimle aynı)."""
    from hrma.engines.solid_rocket_engine import SEA_LEVEL_PRESSURE_BAR
    e = _motor(propellant_type='apcp')
    r = e.calculate_performance()
    ct = r['thermal_analysis']['combustion_thermal']
    pay = TERMAL_KAHIN_TOL_YUZDE / 100.0
    assert ct['reaction_enthalpy_mj_kg'] == pytest.approx(
        tepkime_entalpisi_kahin_mj_kg(), rel=pay)
    oran = e.P_c / SEA_LEVEL_PRESSURE_BAR
    assert ct['thermal_efficiency_percent'] == pytest.approx(
        termal_verim_kahin_yuzde(oran), rel=pay)
    g = CEA_DENGE_GAMMA_S
    vj = math.sqrt(2.0 * g * R_UNIVERSAL / CEA_M_1N_KG_KMOL / (g - 1.0)
                   * CEA_ODA_T_C_K * (1.0 - (1.0 / oran) ** ((g - 1.0) / g)))
    assert ct['jet_velocity_ms'] == pytest.approx(vj, rel=pay)
    mdot_tepe = max(r['thrust_curve']['mass_flow'])
    assert ct['heat_release_rate_mw'] == pytest.approx(
        mdot_tepe * ct['reaction_enthalpy_mj_kg'], rel=1e-12)


#: Etkin özellik önerisi uygulanabildiğinde yayımlanan sayısal alanlar
#: (``two_phase_loss._effective_properties``); karışım çiftinde HİÇBİRİ
#: yayımlanmaz (karar §28-47 (a)).
_ETKIN_SAYI_ALANLARI = ('gamma_mixture', 'effective_molecular_weight',
                        'effective_gas_constant', 'mixture_cp', 'gas_only',
                        'particle_specific_heat')


@pytest.mark.usefixtures('cea_kapali')
def test_B11_S2_2a_iki_faz_karisim_cifti_cift_sayilmaz():
    """ÇEVRİLDİ (eski: ``test_B11_S2A_iki_faz_gaz_yalniz_gamma_donmus``). Eski
    test CEA donmuş GAMMAs'ı modülün "gaz-yalnız" gamma'sı sayıyor ve karışım
    cp'sini modülün KENDİ Eş. 3-35 formülüyle kilitliyordu (kâhin bağımsız
    değildi; 2. tur yeniden denetimi Ş2-2). Karar §28-47 (a).

    Bağımsız kâhin (NASA CEA, aynı kart): donmuş oda Cp'si 1,9031 kJ/kgK
    yoğuşkan faz DAHİL karışımın Cp'sidir ve (GAMMAs 1,1862, M(1/n) 27,829)
    çiftinin cp = γR_u/(M(γ−1)) kapalı biçimi onu yeniden üretir: çift bir
    KARIŞIM çiftidir. Sutton Eş. 3-35..3-39 bu çifte uygulanırsa yoğuşkan
    ikinci kez katılır — karışım gamma'sı CEA'nın kendi karışım gamma'sından,
    etkin M CEA'nın M(1/n)'inden kopar (çift sayma). Ürün etkin özellikleri
    ÜRETMEZ ve gerekçeyi adıyla yazar; Isp'ye uygulanmayan kayıp aynen."""
    from hrma.analysis.two_phase_loss import (
        AL2O3_LIQUID_CP_J_KG_K, EFFECTIVE_PROPERTIES_DOUBLE_COUNTING)
    g, m = CEA_DONMUS_GAMMA_S, CEA_M_1N_KG_KMOL
    # (1) Kâhin: çift, CEA'nın karışım Cp'sini yeniden üretir.
    cp_cift = g * R_UNIVERSAL / m / (g - 1.0)                     # J/(kg K)
    assert cp_cift / 1e3 == pytest.approx(CEA_DONMUS_CP_KJ_KGK,
                                          rel=OZDESLIK_TOL_YUZDE / 100.0)

    e = _motor(propellant_type='apcp')
    blok = e.calculate_performance()['two_phase_loss']
    kullanilan = blok['inputs_used']
    beta = kullanilan['condensed_mass_fraction']
    assert beta > 0.0
    # (2) Çift sayma: karışım ilişkileri karışım çiftine uygulanırsa sonuç
    # CEA'nın kendi karışım değerleriyle ÇELİŞİR (kapalı biçim testte yazılı;
    # cs = NIST-JANAF Al2O3(l)).
    cs = AL2O3_LIQUID_CP_J_KG_K
    cv_cift = R_UNIVERSAL / m / (g - 1.0)
    gamma_cift_sayim = (((1.0 - beta) * cp_cift + beta * cs)
                        / ((1.0 - beta) * cv_cift + beta * cs))
    assert abs(gamma_cift_sayim / g - 1.0) > OZDESLIK_TOL_YUZDE / 100.0
    assert abs(m / (1.0 - beta) - m) > TOL_M

    # (3) Ürün: etkin özellik yok, gerekçe adıyla.
    ef = blok['effective_properties']
    assert ef['applicable'] is False
    assert ef['reason_code'] == EFFECTIVE_PROPERTIES_DOUBLE_COUNTING
    assert 'double counting' in ef['reason']
    assert not set(_ETKIN_SAYI_ALANLARI) & set(ef)
    # Modüle giden çift kâhinin karışım çiftidir ve künye bunu söyler.
    assert kullanilan['gamma'] == pytest.approx(g, abs=TOL_GAMMA)
    assert kullanilan['molecular_weight_g_mol'] == pytest.approx(m, abs=TOL_M)
    kaynak = kullanilan['gas_property_source']
    assert 'gamma_frozen_chamber' in kaynak and 'MIXTURE' in kaynak
    # Kayıp sayısı gamma/M okumaz ve Isp'ye uygulanmaz (aynen).
    assert blok['status'] == 'computed'
    assert blok['two_phase_loss_pct'] > 0.0
    assert blok['applied_to_isp'] is False


def test_B11_S2A_gamma_ezilirse_isil_ve_iki_faz_motor_gammasi():
    """Donmuş değer yalnız ait olduğu kayda: gamma ezilince iki faz
    modülüne giden gamma motorun (ezilmiş) gamma'sıdır.

    3. tur (karar §28-47 (a); kendi bekçisi güncellendi): modüle giden M
    hâlâ kaydın CEA M(1/n)'sidir — yoğuşkan dahil karışım değeri — bu yüzden
    etkin özellikler yine ÜRETİLMEZ (eskiden M_eff = M(1/n)/(1−β) çift
    sayılıyordu). Kullanıcı gamma VE M'yi birlikte ezerse çift kullanıcınındır
    (termokimyası bilinmiyor): modül eskisi gibi hesaplar."""
    from hrma.analysis.two_phase_loss import (
        EFFECTIVE_PROPERTIES_DOUBLE_COUNTING)
    e = _motor(propellant_type='apcp', overrides={'gamma': 1.25})
    blok = e.calculate_performance()['two_phase_loss']
    assert blok['inputs_used']['gamma'] == 1.25
    assert blok['inputs_used']['molecular_weight_g_mol'] == pytest.approx(
        CEA_M_1N_KG_KMOL, abs=TOL_M)
    ef = blok['effective_properties']
    assert ef['applicable'] is False
    assert ef['reason_code'] == EFFECTIVE_PROPERTIES_DOUBLE_COUNTING
    assert 'M(1/n)' in blok['inputs_used']['gas_property_source']

    ikisi = _motor(propellant_type='apcp',
                   overrides={'gamma': 1.25, 'molecular_weight': 26.0})
    blok2 = ikisi.calculate_performance()['two_phase_loss']
    ef2 = blok2['effective_properties']
    assert ef2['applicable'] is True
    assert ef2['gas_only'] == {'gamma': 1.25, 'molecular_weight': 26.0}
    assert blok2['inputs_used']['gas_property_source'] == (
        'propellant record — the same gamma and exhaust molecular weight '
        'the thrust coefficient and the nozzle exit state use')


def test_B11_S2_2a_modul_kapisi_fail_closed():
    """Güvenlik/kararlılık (§28-33): modülün yoğuşkan-faz kapısının girdisi
    bool değilse karar verilmez (ValueError). Kapı yalnız etkin özellik
    bloğunu etkiler; kayıp sayısı bayraktan bağımsızdır. Varsayılan (False)
    bugünkü bütün çağrıları bit-özdeş bırakır."""
    from hrma.analysis.two_phase_loss import (
        EFFECTIVE_PROPERTIES_DOUBLE_COUNTING, two_phase_loss as tpl)
    temel = dict(condensed_mass_fraction=0.3, throat_diameter=0.03,
                 chamber_pressure=40.0, residence_time_ms=5.0,
                 gamma_gas=1.2, molecular_weight_gas=26.0)
    for kotu in ('evet', 1, 0, None, float('nan')):
        with pytest.raises(ValueError):
            tpl.evaluate(**temel, condensed_phase_in_thermochemistry=kotu)
    with pytest.raises(ValueError):       # β = 0 kısa devresinde de denetlenir
        tpl.evaluate(**dict(temel, condensed_mass_fraction=0.0),
                     condensed_phase_in_thermochemistry='evet')
    acik = tpl.evaluate(**temel)
    assert acik == tpl.evaluate(**temel,
                                condensed_phase_in_thermochemistry=False)
    assert acik['effective_properties']['applicable'] is True
    kapali = tpl.evaluate(**temel, condensed_phase_in_thermochemistry=True)
    assert kapali['effective_properties']['applicable'] is False
    assert (kapali['effective_properties']['reason_code']
            == EFFECTIVE_PROPERTIES_DOUBLE_COUNTING)
    assert kapali['two_phase_loss_pct'] == acik['two_phase_loss_pct']


# ---------------------------------------------------------------------------
# 3. tur — karar §28-47 Ş2-1 / D-F3 (ÖNEMLİ): eksenel duvar profili
# (/api/analysis/wall-profile, motor sözlüğünden) Bartz'ı motorun KENDİ
# gaz çiftiyle kurar
# ---------------------------------------------------------------------------
#: 2. tur yeniden denetiminin D-F3 vakası (APCP BATES D120 Pc 55).
_DF3_GOVDE = dict(propellant_type='apcp', grain_type='bates',
                  chamber_pressure=55, chamber_diameter=120,
                  grain_length=600, core_diameter=40)


def _df3_profil(govde):
    """/calculate_solid → (yanıt, kurucu çıktısı, profil, boğaz indisi).
    Profil panelin yolundan: motor sözlüğü ``motor_results`` gövdesiyle."""
    import contextlib
    import io

    import numpy as np
    from hrma.analysis.heat_transfer_analysis import (
        wall_profile_inputs_from_motor)
    from hrma.app import app
    with app.test_client() as c, contextlib.redirect_stdout(io.StringIO()):
        r = c.post('/calculate_solid', json=govde)
        assert r.status_code == 200, r.get_json()
        sonuc = r.get_json()
        p = c.post('/api/analysis/wall-profile',
                   json={'motor_results': sonuc})
        assert p.status_code == 200, p.get_json()
    wp = p.get_json()['wall_profile']
    i = int(np.argmin(np.asarray(wp['area_ratio'], float)))
    return sonuc, wall_profile_inputs_from_motor(sonuc), wp, i


@pytest.mark.usefixtures('cea_kapali')
def test_B11_DF3_eksenel_profil_bartz_gazini_motordan_alir():
    """Katı yanıt Bartz gaz çiftini ADIYLA ve kaynağıyla yayımlar; eksenel
    profil kurucusu onu okur. 2. tur denetimi: profil yayımlanan (genleşme)
    gamma'sını Bartz'a taşıyordu — boğaz h_g oranı 0,941 → 1,225, profil
    q +%25 (motor −%2,78). Gaz çifti motorunkiyle aynı olunca boğaz kurtarma
    sıcaklığı da aynıdır (kâhin: donmuş γ ile T_aw kapalı biçimi). R, c*
    özdeşliğinden TÜRETİLMEZ (özdeşlik genleşme gamma'sına ait; donmuş
    gamma ile ≈ +%3,3 kayardı)."""
    sonuc, kurulum, wp, i = _df3_profil(_DF3_GOVDE)
    k = sonuc['heat_transfer_analysis']['bartz_gas_properties']
    assert k['gamma'] == pytest.approx(CEA_DONMUS_GAMMA_S, abs=TOL_GAMMA)
    assert k['gamma_source'] == 'gamma_frozen_chamber'
    assert k['expansion_gamma'] == pytest.approx(CEA_DENGE_GAMMA_S,
                                                 abs=TOL_GAMMA)
    assert k['expansion_gamma'] == sonuc['gamma']
    assert k['molecular_weight'] == pytest.approx(CEA_M_1N_KG_KMOL, abs=TOL_M)
    assert k['axial_profile_gas'] == {'gamma': k['gamma'],
                                      'molecular_weight': k['molecular_weight']}

    girdi = kurulum['inputs']
    assert girdi['gamma'] == k['gamma']
    assert girdi['molecular_weight'] == k['molecular_weight']
    assert 'gas_constant' not in girdi
    assert 'gas_constant' not in kurulum['derived']
    assert kurulum['basis']['gamma'] == (
        'heat_transfer_analysis.bartz_gas_properties.axial_profile_gas.gamma')

    gaz = wp['gas_properties_basis']
    assert gaz['gamma']['value'] == k['gamma']
    assert gaz['molecular_weight']['value'] == k['molecular_weight']
    assert gaz['assumed_fields'] == []
    g = CEA_DONMUS_GAMMA_S
    pr = 4.0 * g / (9.0 * g - 5.0)
    m2 = (g - 1.0) / 2.0
    taw_kahin = CEA_ODA_T_C_K * (1.0 + pr ** (1.0 / 3.0) * m2) / (1.0 + m2)
    assert wp['T_recovery'][i] == pytest.approx(taw_kahin, rel=1e-9)
    assert wp['T_recovery'][i] == pytest.approx(
        sonuc['nozzle_design']['performance'][
            'throat_recovery_temperature_k'], rel=1e-12)


@pytest.mark.parametrize('ek', [
    {'propellant_type': 'kndx'},
    {'propellant_type': 'pban_ap_al'},
    {'gamma': 1.20},          # APCP, gamma ezilmiş: donmuş değer uygulanmaz
], ids=['kndx', 'pban_ap_al', 'apcp_gamma_ezik'])
def test_B11_DF3_bartz_gazi_genlesme_gaziysa_profil_yolu_degismez(ek):
    """Bartz gazı genleşme gazıyla aynıysa (donmuş değer yok ya da gamma
    ezilmiş) ``axial_profile_gas`` None'dır ve profil önceki yoldan kurulur:
    yayımlanan gamma + c* özdeşliğinden R (öteki katılar bit-özdeş; 3. tur
    önce/sonra ölçümü)."""
    sonuc, kurulum, _wp, _i = _df3_profil(dict(_DF3_GOVDE, **ek))
    k = sonuc['heat_transfer_analysis']['bartz_gas_properties']
    assert k['axial_profile_gas'] is None
    assert k['gamma_source'] == 'gamma'
    assert k['gamma'] == k['expansion_gamma'] == sonuc['gamma']
    assert kurulum['basis']['gamma'] == 'gamma'
    assert kurulum['inputs']['gamma'] == sonuc['gamma']
    assert 'molecular_weight' not in kurulum['inputs']
    assert 'gas_constant' in kurulum['derived']


def test_B11_S2A_donmus_gamma_kapisi_fail_closed():
    """Güvenlik/kararlılık (§28-33): kuralın kullanacağı donmuş değer sonlu ve
    1'den büyük değilse sayı ÜRETİLMEZ (cp = γR/(γ−1) tanımsız ya da
    işaret değiştirir). Katalog yüklemesi değeri zaten bantta denetler; bu
    kapı motor tarafına elle yazılmış bir değere karşıdır."""
    e = _motor(propellant_type='apcp')
    for kotu in (float('nan'), float('inf'), 1.0, 0.5):
        e.gamma_frozen_chamber = kotu
        with pytest.raises(ValueError):
            e._frozen_gas_gamma()


# ===========================================================================
# 4. tur (14 Eki 2026) — katı sayfa varsayılanları TEK KAYNAKTAN.
#
# Ölçülen kusur (KAB devri 1; docs/kabul/kanit_2026-10-14/taze.json): taze
# katı sayfası ``propellant_name`` 'APCP' diyordu ama beş termokimya alanı
# katalog kaydı DEĞİLDİ (yoğunluk 1850, T_c 3200, M 28,5, γ 1,25, c* 1550;
# katalog 1810 / 3399,65 / 27,829 / 1,1338 / 1585,4). Hiçbir şey seçmeden
# Hesapla → Isp 206,14 s. Aynı termokimyanın ikinci literal kopyası
# (CLAUDE.md §11). Kâhin: katalog kaydının kendisi (B11 F, tek kaynak).
# ===========================================================================
T4_SABLON = (__import__('pathlib').Path(__file__).resolve().parents[1]
             / 'hrma' / 'templates' / 'solid.html')
#: Başlık isteği — tests/test_example_projects.HEADERS ile aynı sözleşme.
T4_BASLIK = {'Host': '127.0.0.1:8080'}


def _t4_sablon():
    return T4_SABLON.read_text(encoding='utf-8')


def _t4_alan_haritasi(html):
    """Sayfanın KENDİ katalog→form haritası (``PROPELLANT_FIELD_MAP``),
    yalnız ``PROPELLANT_FORM_FIELDS`` alanları: form id -> katalog alanı.
    Eşleme burada ikinci kez yazılmaz, şablondan okunur."""
    m = re.search(r'var PROPELLANT_FIELD_MAP = \[(.*?)\];', html, re.S)
    assert m, 'PROPELLANT_FIELD_MAP bulunamadı'
    cift = re.findall(r"\{\s*id:\s*'([\w-]+)',\s*field:\s*'([\w-]+)'",
                      m.group(1))
    harita = {i: f for i, f in cift
              if f in propellants_db.PROPELLANT_FORM_FIELDS}
    assert set(harita.values()) == set(propellants_db.PROPELLANT_FORM_FIELDS), (
        'sayfa haritası beş termokimya alanının hepsini taşımıyor: %r'
        % harita)
    return harita


def _t4_value(html, alan_id):
    m = re.search(r'<input\b[^>]*\bid="%s"[^>]*>' % re.escape(alan_id), html)
    assert m, '#%s bulunamadı' % alan_id
    v = re.search(r'\bvalue="([^"]*)"', m.group(0))
    assert v, '#%s value= özniteliği yok' % alan_id
    return v.group(1)


def test_T4_sablonda_apcp_sayi_literali_yok():
    """Kaynak taraması: beş alanın value= özniteliği katalog ifadesidir,
    sayı DEĞİL; JS'te bu alanlara `|| SAYI` yedeği yoktur (toplayıcı,
    c* düğmesi, kütle önizlemesi)."""
    html = _t4_sablon()
    harita = _t4_alan_haritasi(html)
    for alan_id, katalog_alani in harita.items():
        deger = _t4_value(html, alan_id)
        assert re.fullmatch(r'\{\{\s*propellant_defaults\.%s\s*\}\}'
                            % katalog_alani, deger), (
            '#%s varsayılanı katalogdan gelmiyor: value="%s"'
            % (alan_id, deger))
        yedek = re.findall(
            r"getElementById\('%s'\)\.value\)\s*\|\|\s*[-+0-9.]"
            % re.escape(alan_id), html)
        assert not yedek, (
            '#%s için JS sayı yedeği geri geldi: %r' % (alan_id, yedek))


def _t4_render():
    from hrma.app import app
    yanit = app.test_client().get('/solid', headers=T4_BASLIK)
    assert yanit.status_code == 200, yanit.status_code
    return yanit.get_data(as_text=True)


def test_T4_render_edilen_degerler_katalogla_esit():
    """Taze sayfanın gösterdiği beş sayı = ucun varsayılan yakıtının katalog
    kaydı = ``_APCP_REFERENCE`` (bit-aynı; float repr gidiş-dönüş)."""
    from hrma.app import SOLID_ENDPOINT_DEFAULTS
    from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_PROPELLANT_TYPE
    anahtar = SOLID_ENDPOINT_DEFAULTS['propellant_type']
    # V301/K-C2 (K-B DEVİR 10, ana model kararı): uç varsayılanı 'apcp' ->
    # 'kndx'; kâhin hâlâ kaydın kendisi (eski `_APCP_REFERENCE` eşitliği
    # varsayılanın APCP olduğunu kilitliyordu, kuralı değil).
    assert anahtar == SOLID_DEFAULT_PROPELLANT_TYPE
    kayit = PROPELLANTS[anahtar]
    html = _t4_render()
    harita = _t4_alan_haritasi(_t4_sablon())
    for alan_id, katalog_alani in harita.items():
        gosterilen = float(_t4_value(html, alan_id))
        assert gosterilen == kayit[katalog_alani], (alan_id, gosterilen)


def test_T4_okuma_islevi_fail_closed(monkeypatch):
    """Bilinmeyen anahtar KeyError; kayıtta sonlu olmayan alan sözlüğe
    girmez ve sayfa o alanı BOŞ gösterir (sayı uydurulmaz)."""
    from hrma.app import SOLID_ENDPOINT_DEFAULTS
    with pytest.raises(KeyError):
        propellants_db.propellant_form_values('yok_boyle_yakit')
    # V301/K-C2: bozulan kayıt ucun varsayılan yakıtıdır (eskiden 'apcp').
    v = SOLID_ENDPOINT_DEFAULTS['propellant_type']
    bozuk = dict(PROPELLANTS[v], density=float('nan'),
                 c_star=float('inf'))
    monkeypatch.setitem(PROPELLANTS, v, bozuk)
    degerler = propellants_db.propellant_form_values(v)
    assert 'density' not in degerler and 'c_star' not in degerler
    assert degerler['flame_temperature'] == bozuk['flame_temperature']
    html = _t4_render()
    assert _t4_value(html, 'density') == ''
    assert _t4_value(html, 'char_velocity') == ''


def _t4_taze_form_yuku(html):
    """Render edilmiş sayfanın taze FORM yükü: toplayıcının okuduğu sayı
    alanlarının value= değerleri + select (selected/ilk seçenek) + yakıt adı
    metni + boş ``propellant_type`` (hiçbir katalog satırı seçilmedi)."""
    from tests.support import inventory
    okunan = inventory.collected_fields(html)
    yuk = {}
    for ad, sp in inventory.field_specs(html).items():
        if ad not in okunan:
            continue
        if sp.kind == 'number' and sp.default not in (None, ''):
            yuk[ad] = float(sp.default)
        elif sp.kind == 'choice':
            m = re.search(r'<select\b[^>]*\bid="%s"[^>]*>(.*?)</select>'
                          % re.escape(ad), html, re.S)
            secili = re.search(r'<option\b[^>]*\bvalue="([^"]*)"[^>]*\bselected',
                               m.group(1)) if m else None
            deger = secili.group(1) if secili else (
                sp.options[0] if sp.options else None)
            if deger not in (None, ''):
                yuk[ad] = deger
    yuk['propellant_name'] = _t4_value(html, 'propellant_name')
    # V301/K-C2 (NK-29): sayfa kimliği açık seçiciden gönderir; taze sayfada
    # seçili seçenek ucun varsayılan yakıtıdır (boş '' yalnız eski proje).
    m = re.search(r'<select id="propellant_type"[^>]*>(.*?)</select>', html, re.S)
    secili = re.search(r'<option value="([^"]*)" selected', m.group(1)) if m else None
    yuk['propellant_type'] = secili.group(1) if secili else ''
    return yuk


def test_T4_taze_form_yolu_katalog_termokimyasini_cozer():
    """Hiçbir şey seçmeden Hesapla: çözücünün yayımladığı T_c ve γ katalog
    kaydıdır (eski literal yolda 3200 K / 1,25 idi)."""
    from hrma.app import app
    html = _t4_render()
    yuk = _t4_taze_form_yuku(html)
    yanit = app.test_client().post('/calculate_solid', json=yuk,
                                   headers=T4_BASLIK)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    govde = yanit.get_json()
    # V301/N-CEA-2 (K1): taze form ucun varsayılan yakıtını seçer (V301/K-C2:
    # KNDX); termokimya motorun Pc'sinde NASA CEA'dır (aynı kart). Eski
    # literal yol (3200 K / 1,25) kapalı kalır.
    from hrma.analysis.cea_karsilastirma import solid_cea_solution
    from hrma.app import SOLID_ENDPOINT_DEFAULTS
    assert yuk['propellant_type'] == SOLID_ENDPOINT_DEFAULTS['propellant_type']
    assert govde['thermochemistry_source'] == 'nasa_cea_at_pc'
    oda = solid_cea_solution(yuk['propellant_type'], govde['chamber_pressure'],
                             None)['chamber']
    assert govde['chamber_temperature'] == oda['T_c_K']
    assert govde['gamma'] == oda['gamma_s']
    assert govde['chamber_temperature'] != 3200.0


def _t4_node():
    from tests import test_faz6_f1a_kati as f1a
    return f1a


@pytest.mark.skipif(__import__('shutil').which('node') is None,
                    reason='node kurulu değil')
def test_T4_bos_alanda_js_sayi_uydurmaz():
    """c* düğmesi ve kütle önizlemesi boş termokimya alanında APCP yedeği
    UYDURMAZ: c* alanı olduğu gibi kalır, kütle alanı boş kalır."""
    f1a = _t4_node()
    html = _t4_sablon()
    govde = r"""
formuKur();
const once = ELS['char_velocity'].value;
ELS['flame_temp'].value = '';
calculateCharVelocity();
ok(ELS['char_velocity'].value === once,
   'boş T_c ile c* uyduruldu: ' + ELS['char_velocity'].value);
ELS['flame_temp'].value = '3000';
ELS['gamma'].value = 'abc';
calculateCharVelocity();
ok(ELS['char_velocity'].value === once,
   'geçersiz γ ile c* uyduruldu: ' + ELS['char_velocity'].value);
ELS['density'].value = '';
calculatePropellantMass();
ok(ELS['propellant_mass'].value === '',
   'boş yoğunlukla kütle uyduruldu: ' + ELS['propellant_mass'].value);
"""
    proc = f1a.run_node(f1a.harness(
        html, ['calculateCharVelocity', 'calculatePropellantMass',
               'updateTotalMasses'], govde))
    assert proc.returncode == 0, proc.stdout + proc.stderr
