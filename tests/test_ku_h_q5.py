# -*- coding: utf-8 -*-
"""ÖH KU h-q5 — kitap uyum hızlı düzeltmeleri: ısı/soğutma, enjektör,
kararlılık ve valf (H-8, H-11, H-14 parçaları, KU-K4/K5 künyeleri, beyanlar).

Her bekçi ÖLÇÜLEN bir değere ya da yayımlanan bir metne bağlıdır ve ters
mutasyonla KIRMIZI olduğu gösterilmiştir
(docs/scofield/raw/OH/KU/h-q5/mutasyon.md).

Kaynaklar yerel metinlerden doğrulandı (6 Eki 2026):
  NASA SP-8089 s. 13, 21, 35, 38, 43, 84, 85; SP-8087 s. 61, 62, 70;
  SP-8124 s. 27, 28, 53, 55, 70, 84; SP-194 s. 17, 143, 163, 165, 236-239,
  270-273; SP-8123 s. 85; SP-8097 s. 10, 89; SP-8080 s. 11;
  Sutton & Biblarz 9. bs. s. 313, 320, 337, 350.
"""
import pytest

from hrma.engines import injector_design as inj
from hrma.engines.injector_design import (
    CD_TABLE, FLIP_SENSITIVE_LD_BAND,
    ORIFICE_D_PLUGGING_LIMIT_MM, HYPERGOLIC_BLOWAPART_D_MM,
    discharge_coefficient, default_discharge_coefficient,
    hydraulic_flip_sensitive_band, orifice_plugging_check,
    reactive_stream_separation_check, discharge_coefficient_regime)


# ---------------------------------------------------------------------------
# H-8 — enjektör
# ---------------------------------------------------------------------------
class TestH8Enjektor:

    def test_uzun_keskin_orifis_celiskisi_beyanli(self):
        """SP-8089 Şek. 15 s. 43: tam dolu plato ~0,825; sürtünme Cd'yi
        yalnız DÜŞÜRÜR. Değer (0,84) test kırma kuralı gereği DEĞİŞMEDİ
        (devir); bekçi çelişkinin yayımlanan gerekçede BEYAN edildiğini ve
        eski "friction increases" iddiasının geri gelmediğini ölçer."""
        for ld in (5.0, 5.5, 6.0, 10.0, 50.0):
            cd, gerekce = discharge_coefficient('sharp', ld)
            assert cd == pytest.approx(0.84, abs=0.0)
            assert 'increases' not in gerekce
            assert 'ABOVE the full-flow plateau' in gerekce
            assert 'Fig. 15' in gerekce

    def test_tablo_disi_uc_degeri_tablodan_okunuyor(self):
        son_keskin = [r for r in CD_TABLE if r[0] == 'sharp'][-1][3]
        son_yuvarlak = [r for r in CD_TABLE if r[0] == 'radiused'][-1][3]
        assert discharge_coefficient('sharp', 1e6)[0] == son_keskin
        assert discharge_coefficient('radiused', 1e6)[0] == son_yuvarlak

    def test_varsayilan_LD4_yolu_degismedi(self):
        cd, _ = default_discharge_coefficient()
        assert cd == pytest.approx(0.78, abs=0.0)

    def test_flip_duyarli_bant_SP8089(self):
        assert FLIP_SENSITIVE_LD_BAND == (4.0, 6.0)
        assert hydraulic_flip_sensitive_band(5.5, True)['in_band'] is True
        assert hydraulic_flip_sensitive_band(6.0, True)['in_band'] is True
        assert hydraulic_flip_sensitive_band(3.0, True)['in_band'] is False
        # Kazanılmamış L/D'den bayrak yayımlanmaz (kazanılmamış hüküm yasağı).
        k = hydraulic_flip_sensitive_band(4.0, False)
        assert k['in_band'] is None and 'NOT DECIDED' in k['basis']

    def test_tikanma_alt_siniri_0_015_in(self):
        assert ORIFICE_D_PLUGGING_LIMIT_MM == pytest.approx(0.015 * 25.4)
        assert orifice_plugging_check(0.30)['below_limit'] is True
        assert orifice_plugging_check(0.50)['below_limit'] is False

    def test_blowapart_yalniz_hipergolik_ciftte(self):
        assert HYPERGOLIC_BLOWAPART_D_MM == pytest.approx(0.03 * 25.4)
        h = reactive_stream_separation_check('n2o4', 'mmh', 1.2, 1.0)
        assert h['applies'] is True and h['risk'] is True
        h2 = reactive_stream_separation_check('n2o4', 'mmh', 0.5, 0.6)
        assert h2['applies'] is True and h2['risk'] is False
        n = reactive_stream_separation_check('lox', 'rp1', 1.2, 1.0)
        assert n['applies'] is False and n['risk'] is None

    def test_cd_rejim_etiketi(self):
        assert 'BETWEEN' in discharge_coefficient_regime('sharp', 4.0)
        assert 'separated' in discharge_coefficient_regime('sharp', 0.5)
        assert 'full flow' in discharge_coefficient_regime('sharp', 7.0)

    def _sivi_spec(self, **ek):
        spec = {
            'motor_type': 'liquid', 'injector_type': 'impinging_doublet',
            'mdot_ox': 2.0, 'mdot_fuel': 1.0, 'Pc_bar': 30.0,
            'rho_ox': 1440.0, 'rho_fuel': 880.0,
            'fluid_ox': 'n2o4', 'fluid_fuel': 'mmh',
            'dp_ratio_ox': 0.2, 'dp_ratio_fuel': 0.2,
        }
        spec.update(ek)
        return spec

    def test_devre_yeni_alanlari_yayimliyor(self):
        r = inj.design_injector(self._sivi_spec())
        for devre in (r['ox_circuit'], r['fuel_circuit']):
            assert 'cd_regime' in devre
            assert 'band_l_over_d' in devre['hydraulic_flip_sensitive_band']
            assert 'limit_mm' in devre['orifice_plugging_check']
        rss = r['pattern']['impingement']['reactive_stream_separation']
        assert rss['applies'] is True
        assert r['stability']['chug_rule'] == 'dP/Pc >= 0.15-0.20 (NASA SP-8089)'
        kunye = r['stability']['chug_rule_basis']
        assert 'p. 337' in kunye and 'p. 35' in kunye
        assert 'NO universal value' in kunye

    def test_swirl_ideal_teori_beyani(self):
        r = inj.design_injector(self._sivi_spec(
            injector_type='swirl', swirl={'K': 0.5}))
        assert 'Ideal (inviscid)' in r['swirl_geometry']['model_basis']


# ---------------------------------------------------------------------------
# H-11 — RP-1 kritik ısı akısı ekranı
# ---------------------------------------------------------------------------
def _regen_rp1(p_in, mdot=3.0):
    # Denetim Ş-1 (6 Eki): mdot 3,0 kg/s'de kanal hızı ~14 m/s, yani Sutton
    # Tablo 8-5'in 8,5 m/s üst sınırının DIŞINDA. Zarf içi vaka mdot=1,5
    # (~7 m/s) ile kurulur; varsayılan değişmedi.
    from hrma.analysis.regen_cooling import RegenCooling
    return RegenCooling(
        chamber_pressure=20e5, chamber_temperature=3000.0, gamma=1.2,
        molecular_weight=24.0, throat_diameter=0.03, expansion_ratio=6.0,
        coolant='rp1', coolant_mdot=mdot, coolant_inlet_temp=300.0,
        coolant_inlet_pressure=p_in, n_channels=60, channel_width=1.5e-3,
        channel_height=3.0e-3, wall_thickness=1.0e-3, wall_material='cucrzr',
        n_stations=40, coolant_props_source='table').solve()['summary']


def _regen_rp1_tam(p_in, mdot=3.0):
    from hrma.analysis.regen_cooling import RegenCooling
    return RegenCooling(
        chamber_pressure=20e5, chamber_temperature=3000.0, gamma=1.2,
        molecular_weight=24.0, throat_diameter=0.03, expansion_ratio=6.0,
        coolant='rp1', coolant_mdot=mdot, coolant_inlet_temp=300.0,
        coolant_inlet_pressure=p_in, n_channels=60, channel_width=1.5e-3,
        channel_height=3.0e-3, wall_thickness=1.0e-3, wall_material='cucrzr',
        n_stations=40, coolant_props_source='table').solve()


class TestH11Rp1Ekrani:
    """Yalnız uyarı: yeni alan tests/test_wave4b_contract.py ters yön
    sözleşmesini kırdığı için yayımlanmadı (devir)."""

    def test_superkritikte_uyari_yok_ve_alan_yok(self):
        from hrma.analysis.regen_cooling import RP1_CRITICAL_PRESSURE_PA
        assert RP1_CRITICAL_PRESSURE_PA == pytest.approx(2.21e6)
        s = _regen_rp1(80e5)
        assert not any('SUBCRITICAL RP-1' in w for w in s['warnings'])
        assert 'rp1_burnout_screen' not in s

    def test_kritik_altinda_uyari_ve_oran(self):
        # Ş-1: önceki girdi (mdot 3,0, v ~14 m/s) tablo zarfının dışındaydı;
        # beklenti aynı, girdi zarf içine (v ~7 m/s, p 12,7-13 bar) alındı.
        s = _regen_rp1(13e5, mdot=1.5)
        uy = [w for w in s['warnings'] if 'SUBCRITICAL RP-1' in w]
        assert len(uy) == 1
        assert 'peak q/q_max' in uy[0] and '80%' in uy[0]
        assert '22.1 bar' in uy[0]

    # --- Denetim Ş-1 (6 Eki): zarfın alt basınç ve üst hız kenarları ---
    def test_zarf_sabitleri_sutton_T8_5(self):
        """Sutton & Biblarz 9. bs. Tablo 8-5 s. 320 (PDF s. 344, yerel
        metinden doğrulandı): kerosen çekirdekli kaynama satırları
        0,689 / 1,38 MPa ve 1 / 8,5 m/s."""
        from hrma.analysis import regen_cooling as rc
        assert rc.KEROSENE_QMAX_TABLE_P_MIN_PA == pytest.approx(0.689e6)
        assert rc.KEROSENE_QMAX_TABLE_P_MAX_PA == pytest.approx(1.38e6)
        assert rc.KEROSENE_QMAX_TABLE_V_MIN_M_S == pytest.approx(1.0)
        assert rc.KEROSENE_QMAX_TABLE_V_MAX_M_S == pytest.approx(8.5)

    def test_alt_basinc_siniri_5_bar_oran_yazilmaz(self):
        """5 bar giriş (p ≤ 5 bar < 6,89 bar), hız zarf içinde (~7 m/s):
        oran yazılmamalı. Denetçinin vakası (mdot 3,0) da aynı sonucu
        vermeli."""
        for mdot in (1.5, 3.0):
            s = _regen_rp1(5e5, mdot=mdot)
            uy = [w for w in s['warnings'] if 'SUBCRITICAL RP-1' in w]
            assert len(uy) == 1, mdot
            assert 'q/q_max not evaluated' in uy[0], mdot
            assert 'inside the table envelope' not in uy[0], mdot
            assert 'peak q/q_max' not in uy[0], mdot
            assert '0.689-1.38 MPa' in uy[0] and '1-8.5 m/s' in uy[0]

    def test_ust_hiz_siniri_oran_yazilmaz(self):
        """13 bar giriş (basınç zarf içinde), mdot 3,0 → v ~14 m/s > 8,5:
        oran yazılmamalı."""
        r = _regen_rp1_tam(13e5, mdot=3.0)
        assert min(r['velocity_m_s']) > 8.5
        assert 6.89 <= min(r['P_coolant_bar']) <= max(r['P_coolant_bar']) <= 13.8
        uy = [w for w in r['summary']['warnings'] if 'SUBCRITICAL RP-1' in w]
        assert len(uy) == 1
        assert 'q/q_max not evaluated' in uy[0]
        assert 'inside the table envelope' not in uy[0]

    def test_su_icin_uyari_yok(self):
        from hrma.analysis.regen_cooling import RegenCooling
        s = RegenCooling(
            chamber_pressure=20e5, chamber_temperature=3000.0, gamma=1.2,
            molecular_weight=24.0, throat_diameter=0.03, expansion_ratio=6.0,
            coolant='water', coolant_mdot=6.0, coolant_inlet_temp=300.0,
            coolant_inlet_pressure=13e5, n_channels=60,
            channel_width=1.5e-3, channel_height=3.0e-3,
            wall_thickness=1.0e-3, wall_material='cucrzr', n_stations=40,
            coolant_props_source='table').solve()['summary']
        assert not any('SUBCRITICAL RP-1' in w for w in s['warnings'])


# ---------------------------------------------------------------------------
# H-14 + künye + beyanlar
# ---------------------------------------------------------------------------
class TestKunyeBeyan:

    def test_radyasyon_P_E_sapma_iddiasi_kalkti(self):
        from hrma.analysis.heat_transfer_analysis import RADIATION_MODEL_BASIS
        assert 'instead of the printed' not in RADIATION_MODEL_BASIS
        assert 'Howell' in RADIATION_MODEL_BASIS
        assert 'Two DELIBERATE departures' in RADIATION_MODEL_BASIS

    def test_bartz_kunyesi_ve_gaz_tarafi_beyani(self):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        from tests.test_heat_transfer_validation import RS25
        r = HeatTransferAnalyzer().analyze_heat_transfer(dict(RS25))
        htc = r['heat_transfer_coefficients']
        assert htc['correlation'].startswith('Bartz')
        assert 'Bartz 1965' in htc['correlation']
        assert 'laminarization' in htc['gas_side_model_limits']
        assert 'p. 53' in htc['gas_side_model_limits']

    def test_radyasyon_dengesi_iki_yonlu_beyan(self):
        from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer
        out = ThermalProtectionAnalyzer().radiation_equilibrium(
            h_gas_W_m2K=100.0, T_recovery_K=3800.0, emissivity=0.8)
        # Bayrağın ANLAMI değişmedi (hüküm değişikliği ÖNEMLİ, devir).
        assert out['unconservative'] is True
        assert 'OUTER-surface' in out['unconservative_note']
        assert 'single-surface' in out['model_note']
        # Zarubin örneği (RUS notu): ε 0,8, F 1 → ~1500,5 K; sayı aynı kalır.
        assert out['T_wall_eq_K'] == pytest.approx(1500.5, abs=0.5)

    def test_c103_kunyesi_sure_bagimli_bant(self):
        from hrma.analysis.thermal_protection import (
            RADIATION_EXTENSION_MATERIALS)
        from hrma.data.materials_db import get_material
        tp = RADIATION_EXTENSION_MATERIALS['niobium_c103']
        assert tp['service_limit_K'] == pytest.approx(1640.0)
        assert 'SP-8124' in tp['source'] and 'p. 70' in tp['source']
        assert 'Apollo' not in tp['source']
        assert 'SP-8124' in get_material('niobium_c103')['source']

    def test_akustik_bant_kunyesi(self):
        from hrma.analysis.acoustic_modes import (FREQ_BAND_SOURCE,
                                                  NOT_MODELLED)
        assert 'Table 9-2, p. 350' in FREQ_BAND_SOURCE
        assert 'SP-194 introduction' not in FREQ_BAND_SOURCE
        assert 'destabilizing for transverse' in NOT_MODELLED['damping']

    def test_sonum_lule_enine_beyani(self):
        from hrma.stability.damping import DAMPING_NOT_MODELLED
        metin = DAMPING_NOT_MODELLED['nozzle_unsteady_admittance']
        assert 'LONGITUDINAL modes only' in metin and 'p. 163' in metin

    def test_chug_not_modelled_SP194(self):
        from hrma.stability.chug import assess_chug
        r = assess_chug(dp_ratio_j=0.3, tau_s=1e-3, tau_c_s=1.5e-3)
        nm = r['not_modelled']
        for k in ('manifold_capacitance', 'double_time_lag',
                  'intrinsic_low_frequency_mode',
                  'unconditional_stability_scope'):
            assert nm[k].strip(), k
        assert 'p. 270' in nm['unconditional_stability_scope']

    def test_valf_hortum_ve_regulator(self):
        from hrma.analysis.valve_feedline import (NOT_MODELLED,
                                                  FITTING_LD_SOURCE)
        assert '10 to 15' in NOT_MODELLED['flex_hose']
        assert 'several times' not in NOT_MODELLED['flex_hose']
        assert 'SP-8080' in NOT_MODELLED['regulator_tolerance']
        assert 'SP-8097' in FITTING_LD_SOURCE

    def test_koklasma_degeri_ayni(self):
        from hrma.analysis.regen_cooling import RP1_COKING_TEMP_K
        assert RP1_COKING_TEMP_K == pytest.approx(561.0)


# ---------------------------------------------------------------------------
# Denetim Ş-2 (6 Eki) — bekçisiz kalan yeni enjektör alanları
# ---------------------------------------------------------------------------
def _sivi(**ek):
    spec = {
        'motor_type': 'liquid', 'injector_type': 'impinging_doublet',
        'mdot_ox': 2.0, 'mdot_fuel': 1.0, 'Pc_bar': 30.0,
        'rho_ox': 1440.0, 'rho_fuel': 880.0,
        'fluid_ox': 'n2o4', 'fluid_fuel': 'mmh',
        'dp_ratio_ox': 0.2, 'dp_ratio_fuel': 0.2,
    }
    spec.update(ek)
    return inj.design_injector(spec)


class TestS2EnjektorBekcileri:

    def test_triplet_hipergolik_blowapart_uygulanir(self):
        """(a) impinging_triplet + n2o4/mmh: triplet de unlike elemandır
        (SP-8089 s. 13) → applies True."""
        r = _sivi(injector_type='impinging_triplet')
        rss = r['pattern']['impingement']['reactive_stream_separation']
        assert rss['applies'] is True
        assert rss['largest_orifice_d_mm'] == pytest.approx(max(
            r['ox_circuit']['orifice_d_mm'], r['fuel_circuit']['orifice_d_mm']))

    @pytest.mark.parametrize('mdot_ox,mdot_fuel,beklenen,kisit', [
        # ÖH D37 A2 hibrit · 5. tur Ş-1 (ana model kararı (i), 7 Eki): True
        # vakası ÇAĞIRAN KISITIYLA kurulur; ölçüldü: 2 × 0,3133 / 1 × 0,3544
        # mm < 0,381. Düğüm kimliği değişmesin diye id eski hâliyle verilir.
        pytest.param(0.005, 0.0025, True, {'d_min_mm': 0.3, 'd_max_mm': 3.0},
                     id='0.005-0.0025-True'),
        pytest.param(0.02, 0.01, False, None,  # ölçüldü: d 0,886 / 0,709 mm
                     id='0.02-0.01-False'),
    ])
    def test_devre_tikanma_bayragi_orifis_capina_bagli(self, mdot_ox,
                                                       mdot_fuel, beklenen,
                                                       kisit):
        """(b) Devre düzeyinde below_limit == (orifice_d_mm < sınır); iki
        yönde de vaka var (birim hatası tek yönü gizleyemez).

        Neden True vakası çağıran kısıtıyla (``orifice_constraints``
        {'d_min_mm': 0.3, 'd_max_mm': 3.0}) kuruluyor: ÖH D37 A2 hibrit F-10
        devre çözücüsünün sert kısıtını tek kaynaklı imalat bandına çekti
        (``DEFAULT_CONSTRAINTS`` d_min 0,3 → 0,5 mm; Sutton & Biblarz 9. bs.
        s. 337, Mishra 2017 s. 348). Varsayılan yolda delik çapı 0,5 mm'nin
        altına yalnız tek delikte iner; bu vakada yükseltgen devresi
        1 × 0,443 mm çıkar (ölçüldü, 7 Eki). SP-8089 0,381 mm tıkanma
        bayrağının True yönü varsayılan yolda artık bu vakada yanamaz. Bu
        yüzden eski geniş bant çağıranın kendi kısıtı olarak verilir; False
        vakası ve dosyanın geri kalanı varsayılan yolda kalır."""
        ek = {'orifice_constraints': kisit} if kisit else {}
        r = _sivi(mdot_ox=mdot_ox, mdot_fuel=mdot_fuel, **ek)
        for ad in ('ox_circuit', 'fuel_circuit'):
            d = r[ad]
            chk = d['orifice_plugging_check']
            assert chk['below_limit'] is (
                d['orifice_d_mm'] < ORIFICE_D_PLUGGING_LIMIT_MM), ad
            assert chk['below_limit'] is beklenen, ad

    def test_cd_rejim_kullanici_cd_ve_swirl_not_applicable(self):
        """(c) Kullanıcı Cd'si (spec 'cd') ve swirl elemanında Cd tablodan
        gelmez → 'not applicable'; tablo yolunda rejim etiketi."""
        tablo = _sivi()
        for ad in ('ox_circuit', 'fuel_circuit'):
            assert not tablo[ad]['cd_regime'].startswith('not applicable'), ad
        kullanici = _sivi(cd=0.7)
        for ad in ('ox_circuit', 'fuel_circuit'):
            assert kullanici[ad]['cd_regime'].startswith('not applicable'), ad
        swirl = _sivi(injector_type='swirl', swirl={'K': 0.5})
        assert swirl['ox_circuit']['cd_regime'].startswith('not applicable')
        # Swirl'de yakıt devresi düz orifistir; Cd tablodan gelir.
        assert not swirl['fuel_circuit']['cd_regime'].startswith(
            'not applicable')


# ---------------------------------------------------------------------------
# Denetim Ş-3a (6 Eki) — RP1_CRITICAL_PRESSURE_PA yalnız uyarıda
# ---------------------------------------------------------------------------
def test_rp1_kritik_basinc_yalniz_uyarida_kullaniliyor():
    """Gerilim kaydı: water_hammer.py RP-1 'critical_pressure_Pa'yı BİLEREK
    taşımıyor (ÖH D19 / P5B3-08, fail-closed). regen_cooling'deki 2,21 MPa
    sabiti hiçbir hükme bağlanmamalı; tek kaynak kararı Berke'nin.

    AST ile ölçülür:
      1. hrma/ altında başka hiçbir modül bu adı anmaz;
      2. regen_cooling.py'de adın her OKUNUŞU tek bir ``if self.coolant ==
         'rp1':`` bloğunun içindedir;
      3. o blok yalnız yerel ad atar ve tek yan etkisi
         ``warnings_list.append`` çağrısıdır (return, öznitelik/indis
         yazımı yok);
      4. blokta atanan yerel adlar blok dışında okunmaz.
    """
    import ast
    import pathlib
    kok = pathlib.Path(__file__).resolve().parents[1] / 'hrma'
    AD = 'RP1_CRITICAL_PRESSURE_PA'
    hedef = kok / 'analysis' / 'regen_cooling.py'
    for f in kok.rglob('*.py'):
        if f == hedef:
            continue
        agac = ast.parse(f.read_text(encoding='utf-8'))
        for n in ast.walk(agac):
            assert not (isinstance(n, ast.Name) and n.id == AD), f
            assert not (isinstance(n, ast.Attribute) and n.attr == AD), f
            if isinstance(n, ast.ImportFrom):
                assert AD not in [a.name for a in n.names], f

    agac = ast.parse(hedef.read_text(encoding='utf-8'))
    ebeveyn = {}
    for n in ast.walk(agac):
        for c in ast.iter_child_nodes(n):
            ebeveyn[c] = n

    def rp1_blogu(n):
        while n in ebeveyn:
            n = ebeveyn[n]
            if (isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                    and ast.unparse(n.test) == "self.coolant == 'rp1'"):
                return n
        return None

    okunus = [n for n in ast.walk(agac) if isinstance(n, ast.Name)
              and n.id == AD and isinstance(n.ctx, ast.Load)]
    assert okunus, 'sabit hiç okunmuyor (bekçi boşa düşer)'
    bloklar = {rp1_blogu(n) for n in okunus}
    assert len(bloklar) == 1 and None not in bloklar, bloklar
    blok = bloklar.pop()

    yerel = set()
    ek_cagri = 0
    for n in ast.walk(blok):
        assert not isinstance(n, (ast.Return, ast.Yield, ast.Global,
                                  ast.Nonlocal)), ast.dump(n)
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            hedefler = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in hedefler:
                assert isinstance(t, ast.Name), ast.unparse(t)
                yerel.add(t.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if isinstance(n.func.value, ast.Name) and n.func.value.id == 'np':
                continue
            assert ast.unparse(n.func) == 'warnings_list.append', \
                ast.unparse(n.func)
            ek_cagri += 1
    assert ek_cagri == 1

    fonk = blok
    while not isinstance(fonk, ast.FunctionDef):
        fonk = ebeveyn[fonk]
    blok_ici = set(ast.walk(blok))
    for n in ast.walk(fonk):
        if (isinstance(n, ast.Name) and n.id in yerel
                and isinstance(n.ctx, ast.Load) and n not in blok_ici):
            raise AssertionError(
                f'{n.id} H-11 bloğu dışında okunuyor (satır {n.lineno})')
