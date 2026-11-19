"""V307/CI-KIRMIZI — aynı büyüklüğün iki yolu TEK hesaptan (platform bekçisi).

CI 44290629774 (aday/v3.0.7-rc.1) Linux'ta dört test yalnız son basamakta
kırmızıydı: aynı büyüklük iki yolda farklı işlem sırasıyla hesaplanıyordu ve
macOS'ta yuvarlama tesadüfen çakışıyordu. Linux'u yerelde koşamayız; bu
bekçiler platform farkını TAKLİT eder: üst akış girdileri (v_e, ṁ, A_e, ρ_l)
platforma göre son bitte değişir — rastgele girdi ve ρ_l'nin birkaç ulp
kaydırılması bunu yerelde üretir. İki yol aynı işlevden geçiyorsa her girdide
bit-aynıdır; ayrı formüllerse bu bekçiler macOS'ta da KIRMIZI olur (ters
mutasyon: docs/scofield/raw/OH/V307/ci-kirmizi/RAPOR.md).
"""
import math
import random
import types

import pytest

from hrma.analysis import altitude_performance as ap
from hrma.analysis import tank_blowdown as tbm
from hrma.engines import combustion_analysis as ca
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine

_H = [0.0, 1000.0, 5000.0, 10000.0, 15000.0, 20000.0]


# ---------------------------------------------------------------------------
# 1. Hibrit İrtifa Profili ⟷ motorun irtifa tablosu (test_v307_sekme_motor:461)
# ---------------------------------------------------------------------------
def test_irtifa_iki_yol_ayni_islevi_cagirir():
    assert ap.fixed_nozzle_altitude_point is ca.fixed_nozzle_altitude_point


def test_irtifa_iki_yol_rastgele_girdide_bit_ayni():
    rnd = random.Random(20261118)
    sayac = 0
    for _ in range(200):
        mdot = rnd.uniform(0.2, 5.0)
        v_e = rnd.uniform(1500.0, 2600.0)
        P_e = rnd.uniform(0.6, 1.2)
        A_e = rnd.uniform(5e-4, 2e-2)
        P_cap = rnd.choice([101325.0, 100000.0, rnd.uniform(5e4, 1.1e5)])
        f_sl = (mdot * v_e + (P_e * 1e5 - P_cap) * A_e) * rnd.uniform(0.9, 0.99)
        rows, meta = ca.CombustionAnalyzer._fixed_nozzle_altitude_sweep(
            mdot, v_e, P_e, rnd.uniform(1200, 2200), rnd.uniform(250, 380),
            _H, thrust_sea_level=f_sl, exit_area_m2=A_e,
            anchor_ambient_pressure_pa=P_cap)
        assert meta['anchored_to_delivered_thrust'] is True
        motor = {'thrust': f_sl,
                 'altitude_performance': {'nozzle_loss_model': meta},
                 'nozzle_expansion_screen': {'exit_pressure_bar': P_e}}
        prof = ap.fixed_nozzle_profile(
            motor, {'start': 0, 'end': 20000, 'points': 21})
        assert prof['status'] == 'computed'
        tablo = {r['altitude']: r for r in rows}
        for r in prof['rows']:
            m = tablo.get(r['altitude_m'])
            if m is None:
                continue
            assert r['thrust_n'] is not None
            assert (r['thrust_n'], r['isp_s']) == (m['thrust'], m['isp'])
            sayac += 1
    assert sayac == 200 * len(_H)


# ---------------------------------------------------------------------------
# 2. Yüklenen sıvı: tank ⟷ çözücü m_ox (test_slosh_motor_baglanti:392)
# ---------------------------------------------------------------------------
def _rho_kaydir(monkeypatch, k):
    """ρ_l'yi k ulp kaydırır (platformun libm/EOS son bit farkının taklidi)."""
    asil = tbm.N2OSaturation.rho_l

    def kaydirilmis(self, T):
        v = float(asil(self, T))
        for _ in range(abs(k)):
            v = math.nextafter(v, math.inf if k > 0 else -math.inf)
        return v
    monkeypatch.setattr(tbm.N2OSaturation, 'rho_l', kaydirilmis)


@pytest.mark.parametrize('k', [-3, -1, 0, 1, 2, 5])
def test_tank_ateslemedeki_sivisi_boyutlandirma_kutlesi(monkeypatch, k):
    _rho_kaydir(monkeypatch, k)
    rnd = random.Random(1000 + k)
    for _ in range(60):
        m_ox = rnd.uniform(0.5, 40.0)
        T = rnd.uniform(250.0, 300.0)
        tank = tbm.N2OTankBlowdown.from_oxidizer_mass(
            m_ox, initial_temperature=T, liquid_fill_fraction=0.85)
        assert tank.liquid_mass == m_ox


# ---------------------------------------------------------------------------
# 3. Sıvı yoğunluğu: çalkantı bloğu ⟷ boşalma serisi (test_six_dof_slosh_tarama:893)
# ---------------------------------------------------------------------------
def test_calkanti_blogu_yogunlugu_bosalma_serisinin_t0_degeri():
    rnd = random.Random(893)
    for _ in range(100):
        m_ox = rnd.uniform(1.0, 30.0)
        rho0 = rnd.uniform(700.0, 950.0)
        f = 0.85
        V = (m_ox / rho0) / f
        rho0_kayik = math.nextafter(rho0, math.inf)   # platform taklidi
        sahte = types.SimpleNamespace(m_ox=m_ox, g0=9.80665, uq_mode=False)
        blok = HybridRocketEngine._oxidizer_tank_slosh_block(sahte, {
            'status': 'modelled', 'tank_volume_m3': V,
            'liquid_fill_fraction': f,
            'oxidizer_inventory': {
                'liquid_density_kg_m3': [rho0_kayik, rho0_kayik * 1.1]}})
        assert blok['status'] == 'modelled', blok
        assert blok['liquid_density_kg_m3'] == rho0_kayik
        assert blok['liquid_mass_kg'] == m_ox
