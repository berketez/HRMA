"""ÖH Dalga-33-2 · motorlar kulvarı a1 bekçileri.

Dört kalem, dört bekçi kümesi. Her biri TERS-MUTASYONLA kanıtlanmıştır
(``docs/scofield/raw/OH/D33-2/motorlar/a1/mutasyon.json``):

* **OH-D32-08** — ``chug_tau_sensitivity`` yalnız FREKANSI banda alıyordu.
  Ölçüldü (``once.json``): aynı çevrimde ``growth_rate_1_s`` adaylar
  arasında 191,1397 ⟷ 162,9580 1/s (28,1816 1/s, %17,3) değişirken bunu
  bildiren alan sayısı **0**. Büyüme oranı SÖNÜMLEME tasarımını süren
  sayıdır; monotonluk savı hükmü kapsar, kökün gerçek kısmının
  BÜYÜKLÜĞÜNÜ kapsamaz.
* **OH-D32-07** — hibrit chug ayağı ``assess_chug``a ``alternative_taus``
  vermiyordu ve ``tau_choice_sensitivity`` SESSİZCE yok oluyordu.
  Ölçüldü: yanıtın tamamında alan 0 kez, hibrit enjektör bloğunda ikinci
  karışma zaman ölçeği de 0 kez geçiyor. "Ölçülmedi" ile "duyarsız" aynı
  şey değildir.
* **OH-FB-02** (Fable sivi-03) — enjektör zinciri KAPI DIŞI arızada
  besleme bütçesi 0,0 bar kalem yayımlıyor ve bunu söyleyen tek işaret bir
  İNGİLİZCE CÜMLEnin ön ekiydi. Ölçüldü: 6,6000 -> 0,0000 bar,
  ``pump_discharge_pressure_ox`` 38,4738 -> 31,8738 bar.
* **OH-FB-03** (Fable sivi-03) — kademe kararı çözülemezken (Ns ölçülemez)
  kart ``stage_count: null`` diyor ama çarkı TOPLAM yükle TEK kademe
  çözüp YAYIMLIYORDU: hüküm yok, geometri var.
"""

import math

import pytest

from hrma.stability.chug import assess_chug, chug_tau_sensitivity

# Defterin ölçtüğü koşu (P6B4-03): iki karışım zaman ölçeği, aynı çevrim.
J = 0.12
TAU_C_S = 2.0e-3
TAU_ATOM_S = 4.489e-3
TAU_MIX_S = 1.264e-3


# ---------------------------------------------------------------------------
# OH-D32-08 — BÜYÜME ORANI BANDI ÖLÇÜLÜR
# ---------------------------------------------------------------------------

def _defter_blogu():
    blok = chug_tau_sensitivity(J, TAU_C_S, None,
                                {'atomisation': TAU_ATOM_S,
                                 'mixing_residence_time': TAU_MIX_S})
    assert blok is not None
    return blok


def test_oh_d32_08_buyume_bandi_yayimlanir():
    """Band alanı VAR ve uçları adayların KENDİ sayılarından gelir."""
    blok = _defter_blogu()
    band = blok['growth_rate_1_s_span']
    assert band is not None, 'büyüme oranı bandı yayımlanmıyor (OH-D32-08)'
    buyumeler = [v['growth_rate_1_s'] for v in blok['candidates'].values()
                 if isinstance(v['growth_rate_1_s'], float)
                 and math.isfinite(v['growth_rate_1_s'])]
    assert band['min_1_s'] == min(buyumeler)
    assert band['max_1_s'] == max(buyumeler)
    assert band['span_1_s'] == max(buyumeler) - min(buyumeler)
    # Uçlar ADIYLA durur — ikinci bir hesap yok.
    assert band['min_1_s'] == \
        blok['candidates'][band['min_candidate']]['growth_rate_1_s']
    assert band['max_1_s'] == \
        blok['candidates'][band['max_candidate']]['growth_rate_1_s']


def test_oh_d32_08_bandin_genisligi_defterdeki_kadar():
    """Ölçülen fark sıfır DEĞİL: tek yayımlanan büyüme oranı kesin değil."""
    band = _defter_blogu()['growth_rate_1_s_span']
    assert band['span_1_s'] > 0.0
    assert band['max_1_s'] > band['min_1_s']


def test_oh_d32_08_bayrak_buyumeyi_de_kapsar():
    """``is_tau_sensitive`` üç eksenin BİRLEŞİMİ (hüküm VEYA frekans VEYA
    büyüme) — tek eksene bakan tüketici yanılmasın."""
    blok = _defter_blogu()
    assert blok['growth_is_tau_sensitive'] is True
    assert blok['is_tau_sensitive'] is True
    assert 'growth_rate_1_s_span' in blok['_basis']


def test_oh_d32_08_olculemeyen_band_false_degil_none():
    """Tek aday: band YOK, bayrak False DEĞİL None + gerekçe (fail-closed)."""
    blok = chug_tau_sensitivity(J, TAU_C_S, None, {'yalniz': TAU_ATOM_S})
    assert blok is not None
    assert blok['growth_rate_1_s_span'] is None
    assert blok['growth_is_tau_sensitive'] is None, (
        'ölçülmeyen eksen False diye yayımlanamaz (sessiz güven)')
    gerekce = blok['growth_span_not_resolved_reason']
    assert isinstance(gerekce, str) and 'not measured' in gerekce.lower()
    # Frekans ekseni de ölçülemediği için birleşik bayrak da None kalır.
    assert blok['is_tau_sensitive'] is None


def test_oh_d32_08_negatif_buyume_banddan_DUSMEZ():
    """Kararlı adaylarda büyüme NEGATİFtir; geçerlilik ölçütü SONLU olmak.

    Frekans bandının "f > 0" şartı buraya KOPYALANIRSA kararlı adaylar
    sessizce banddan düşer ve band "ölçülemedi" sanılır.
    """
    # J = 0,45 -> nötr gecikme büyük; iki aday da kararlı (büyüme < 0).
    blok = chug_tau_sensitivity(0.45, TAU_C_S, None,
                                {'a': 0.2e-3, 'b': 0.4e-3})
    assert blok is not None
    buyumeler = [v['growth_rate_1_s'] for v in blok['candidates'].values()]
    assert all(isinstance(g, float) and g < 0.0 for g in buyumeler), buyumeler
    band = blok['growth_rate_1_s_span']
    assert band is not None, 'negatif büyümeler banddan düşmemeli'
    assert set(band['resolved_candidates']) == set(blok['candidates'])
    # İşaret sıfırı geçmediği (hepsi negatif) için ORAN yayımlanmaz.
    assert band['ratio'] is None
    assert isinstance(band['ratio_not_applicable_reason'], str)


def test_oh_d32_08_pozitif_bandda_oran_yayimlanir():
    """Band tümüyle pozitifse oran ANLAMLIDIR ve yayımlanır."""
    band = _defter_blogu()['growth_rate_1_s_span']
    assert band['min_1_s'] > 0.0
    assert band['ratio'] == band['max_1_s'] / band['min_1_s']
    assert band['ratio_not_applicable_reason'] is None


def test_oh_d32_08_yalniz_buyume_ekseni_olculdugunde_bayrak_dogru():
    """FREKANS ölçülemezken BÜYÜME ölçülebilir — bayrak bunu görmelidir.

    J = 0,45 ve τ = {0,05; 0,10} ms'de baskın kök GERÇEKTİR: yayımlanan
    frekans iki adayda da 0,0 Hz olduğu için frekans bandı ÖLÇÜLEMEZ
    (fail-closed, None). Büyüme oranı ise ölçülür ve adaylar arasında
    -1086,5731 ⟷ -1121,4885 1/s değişir. D32'nin iki eksenli bayrağı bu
    koşuda ``None`` ("ölçemedim") derdi; üçüncü eksen eklendiğinde
    ölçülmüş bir duyarlılık ADIYLA görünür.
    """
    blok = chug_tau_sensitivity(0.45, TAU_C_S, None,
                                {'a': 0.05e-3, 'b': 0.10e-3})
    assert blok is not None
    assert blok['frequency_hz_span'] is None, 'bu koşuda frekans bandı yok'
    assert blok['frequency_is_tau_sensitive'] is None
    assert blok['growth_rate_1_s_span'] is not None
    assert blok['growth_is_tau_sensitive'] is True
    assert blok['is_tau_sensitive'] is True, (
        'ölçülmüş büyüme duyarlılığı birleşik bayrağa girmeli (OH-D32-08)')


def test_oh_d32_08_aday_yoksa_blok_hic_konmaz():
    """Aday verilmezse duyarlılık bloğu HİÇ konmaz (çapa bit-aynı kalır)."""
    sonuc = assess_chug(dp_ratio_j=J, tau_s=TAU_ATOM_S, tau_c_s=TAU_C_S)
    assert 'tau_choice_sensitivity' not in sonuc


# ---------------------------------------------------------------------------
# OH-D32-07 — HİBRİT AYAĞI: ALANIN YOKLUĞU SESSİZ KALMAZ
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def hibrit_cevrim():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=1000.0, burn_time=10.0, of_ratio=6.0,
                               chamber_pressure=20.0, fuel_type='htpb',
                               oxidizer_type='n2o')
    sonuc = motor.calculate()
    blok = ((sonuc.get('combustion_stability') or {}).get('chug_loop') or {})
    if blok.get('status') != 'modelled':
        pytest.skip('bu koşuda chug çevrimi çözülmedi')
    return motor, sonuc, blok


def test_oh_d32_07_aday_kanali_baglandi(hibrit_cevrim):
    """Hibrit ayağı ``alternative_taus`` kanalını KURAR (yardımcı vardır)."""
    motor, sonuc, _ = hibrit_cevrim
    adaylar, arama = motor._chug_tau_candidates(sonuc)
    assert isinstance(adaylar, dict)
    assert isinstance(arama, list) and len(arama) >= 3, (
        'her aday kaynağının yoklandığı kayda geçmeli')
    # Aday çıkmayan kaynak da SESSİZ kalmaz: gerekçesi metinde durur.
    assert any('mixing_residence_time' in m for m in arama)
    assert any('lfi' in m.lower() for m in arama)


def test_oh_d32_07_olculmedi_beyani_adiyla_durur(hibrit_cevrim):
    """Blok yoksa NEDEN yok olduğu yayımlanır — "duyarsız" sanılmasın."""
    _, _, blok = hibrit_cevrim
    if 'tau_choice_sensitivity' in blok:
        pytest.skip('bu koşuda geçerli bir alternatif aday çözüldü')
    beyan = blok.get('tau_choice_not_measured')
    assert isinstance(beyan, dict), (
        'tau_choice_sensitivity yoksa yokluğun gerekçesi ADIYLA durmalı '
        '(OH-D32-07)')
    assert 'not measured' in beyan['reason'].lower()
    assert 'insensitive' in beyan['reason'].lower()
    assert isinstance(beyan['candidate_sources_examined'], list)
    assert beyan['candidate_sources_examined']


def test_oh_d32_07_gecerli_aday_varsa_blok_konur():
    """Kanal GERÇEKTEN bağlı: aday çözülürse çekirdek bloğu üretir."""
    sonuc = assess_chug(dp_ratio_j=J, tau_s=TAU_ATOM_S, tau_c_s=TAU_C_S,
                        alternative_taus={'mixing_residence_time': TAU_MIX_S})
    blok = sonuc.get('tau_choice_sensitivity')
    assert blok is not None
    assert set(blok['candidates']) == {'selected', 'mixing_residence_time'}


# ---------------------------------------------------------------------------
# OH-FB-02 — BESLEME BÜTÇESİNİN KAPI DIŞI ARIZASI MAKİNE OKUNUR
# ---------------------------------------------------------------------------

def _sivi_motor():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    m = LiquidRocketEngine(thrust=10000.0, chamber_pressure=30.0,
                           mixture_ratio=2.2, fuel_type='rp1',
                           oxidizer_type='lox')
    m.calculate_nozzle_geometry()
    return m


def test_oh_fb_02_saglak_kosuda_kapi_computed():
    """Sağlam koşuda kapı 'computed' ve bütçe alt sınır DEĞİL."""
    drops = _sivi_motor()._calculate_feed_system_pressure_drops()
    assert drops['injector_drop_status'] == 'computed'
    assert drops['feed_budget_is_lower_bound'] is False
    assert drops['feed_budget_lower_bound_fields'] is None
    assert drops['injector'] > 0.0


def test_oh_fb_02_kapi_disi_arizada_makine_okunur_kapi():
    """KAPI DIŞI arızada durum CÜMLE AYRIŞTIRMADAN okunabilir.

    ÖH A2 sivi-sogutma F-20 (Berke Sunum 2 onayı sonrası çeviri, denetçi
    Ş5.5): arıza yolunda alt sınır ARTIK YAYIMLANMAZ — kalem ve onu içeren
    toplamlar None; bayrak alt sınır iddiası taşımaz. Makine okunur kapı
    (status + basis) aynen korunur.
    """
    m = _sivi_motor()

    def _patlat():
        raise RuntimeError('kapı DIŞI arıza (bekçi)')

    m.calculate_injector_design = _patlat
    drops = m._calculate_feed_system_pressure_drops()
    assert drops['injector_drop_status'] == 'not_computed', (
        'kapı dışı arıza makine okunur bir alanla bildirilmeli (OH-FB-02)')
    # Enjektör kalemini içeren HER yük taşıyan alan yayımlanmaz (None; alt
    # sınır da sıfır da DEĞİL).
    for ad in ('injector', 'total_ox', 'total_fuel',
               'pump_discharge_pressure_ox', 'pump_discharge_pressure_fuel'):
        assert drops[ad] is None, ad
    assert drops['feed_budget_is_lower_bound'] is False
    assert isinstance(drops['feed_budget_lower_bound_basis'], str)


def test_oh_fb_02_kapi_hatalari_hala_yukselir():
    """Kapı hataları YUTULMAZ — fail-closed hükmü alt sınıra dönüşmez."""
    from hrma.engines.liquid_rocket_engine import (
        LiquidRocketEngine, UnsupportedInjectorTypeError,
    )
    m = _sivi_motor()

    def _kapi():
        raise UnsupportedInjectorTypeError('tanınmayan tip (bekçi)')

    m.calculate_injector_design = _kapi
    with pytest.raises(UnsupportedInjectorTypeError):
        m._calculate_feed_system_pressure_drops()
    assert LiquidRocketEngine is not None


# ---------------------------------------------------------------------------
# OH-FB-03 — KADEME KARARI YOKSA ÇARK GEOMETRİSİ YAYIMLANMAZ
# ---------------------------------------------------------------------------

def _pompa_karti(shaft_power_kw=None):
    return _sivi_motor()._design_pump(5.0, 1140.0, 60.0, 3.0,
                                      shaft_power_kw=shaft_power_kw,
                                      propellant='lox', role='oxidizer')


def test_oh_fb_03_karar_verilince_geometri_yayimlanir():
    """Kademe kararı çözülen koşuda zincir bit-aynı davranır."""
    kart = _pompa_karti()
    assert kart['stage_count'] == 1
    assert kart['stage_count_not_resolved_reason'] is None
    assert kart['impeller_geometry_status'] == 'modelled'
    assert isinstance(kart['impeller_diameter'], float)
    assert kart['impeller_diameter'] > 0.0


def test_oh_fb_03_karar_yoksa_geometri_yayimlanmaz():
    """Ns ölçülemezse: karar YOK, geometri de YOK (sessiz n = 1 yasak)."""
    kart = _pompa_karti(shaft_power_kw=0.0)     # cycle_scale = 0 -> H_top = 0
    assert kart['specific_speed_us'] is None
    assert kart['stage_count'] is None
    assert kart['impeller_geometry_status'] == 'not_computed', (
        'kademe kararı verilemezken çark TOPLAM yükle çözülüp '
        'yayımlanamaz (OH-FB-03)')
    assert kart['impeller_diameter'] is None
    assert kart['impeller_tip_speed'] is None
    # İma edilen geometri kaybolmaz; AYRI adla ve "tasarım değildir"
    # künyesiyle durur.
    assert isinstance(kart['impeller_diameter_if_inlet_head_floor'], float)


def test_oh_fb_03_kararsizligin_gerekcesi_adiyla_durur():
    """``stage_count: null`` tek başına NEDEN demez; gerekçe alanı vardır."""
    kart = _pompa_karti(shaft_power_kw=0.0)
    gerekce = kart['stage_count_not_resolved_reason']
    assert isinstance(gerekce, str) and gerekce
    assert 'total_head_m' in gerekce, (
        'hangi girdinin düştüğü ADIYLA yazmalı')
    assert 'not published' in kart['impeller_geometry_basis'].lower()


# ---------------------------------------------------------------------------
# OH-UC-04 — REGÜLELİ KİPTE TANK DURUMUNUN ROLÜ YAYIMLANIR
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def gecici_cozum():
    from hrma.analysis.transient_ballistics import TransientBallistics
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=1000.0, burn_time=10.0, of_ratio=6.0,
                               chamber_pressure=20.0, fuel_type='htpb',
                               oxidizer_type='n2o')
    motor.calculate()
    return TransientBallistics, motor


def test_oh_uc_04_reguleli_kipte_tank_durumu_rolu_yayimlanir(gecici_cozum):
    """Hayalet girdi bırakılmaz: alınan tank T ADIYLA ve rolüyle durur."""
    TB, motor = gecici_cozum
    cozucu = TB(motor, feed_mode='regulated', tank_temperature=250.0)
    rol = cozucu._tank_state_role
    assert isinstance(rol, dict), (
        'regüleli kipte tank durumunun rolü yayımlanmalı (OH-UC-04)')
    assert rol['tank_temperature_K_received'] == 250.0
    assert rol['used_by_this_model'] is False
    assert 'prescribed' in rol['reason'].lower()
    # Modelin DIŞINDA kalan fizik adıyla durur (beyan değil, kapsam).
    assert 'sqrt' in rol['not_modelled'].lower()


def test_oh_uc_04_duyarlilik_olculur_uydurulmaz(gecici_cozum):
    """Atılan etkinin BÜYÜKLÜĞÜ aynı özellik modelinden ÖLÇÜLÜR."""
    TB, motor = gecici_cozum
    soguk = TB(motor, feed_mode='regulated',
               tank_temperature=250.0)._tank_state_role
    duyar = soguk['regulated_flow_temperature_sensitivity']
    if duyar is None:
        assert isinstance(
            soguk['regulated_flow_temperature_sensitivity_not_measured_'
                  'reason'], str)
        pytest.skip('özellik modeli bu sıcaklıkta çözmedi')
    # Soğuk tank DAHA YOĞUN -> aynı ΔP'de debi çarpanı 1'in ÜSTÜNDE.
    assert duyar['liquid_density_kg_m3'] > \
        duyar['reference_liquid_density_kg_m3']
    assert duyar['implied_mdot_factor_sqrt_rho_ratio'] == pytest.approx(
        math.sqrt(duyar['liquid_density_kg_m3']
                  / duyar['reference_liquid_density_kg_m3']))
    assert duyar['implied_mdot_factor_sqrt_rho_ratio'] > 1.0


def test_oh_uc_04_blowdown_kipinde_alan_konmaz(gecici_cozum):
    """Blowdown'da tank durumu ZATEN çözücüye girer; alan None kalır."""
    TB, motor = gecici_cozum
    try:
        cozucu = TB(motor, feed_mode='blowdown', tank_temperature=293.15)
    except ValueError:
        pytest.skip('bu motorda blowdown beslemesi kurulamıyor')
    assert cozucu._tank_state_role is None
