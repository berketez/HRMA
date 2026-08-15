"""Faz 4B bekçileri: 6-DOF enine atalet (A6) ve çözücü başarı kapısı (B5).

İki ayrı sınıf kusur kilitlenir:

A6 — ``SixDOFTrajectory._inertia`` components-yok dalında Huygens-Steiner
(paralel eksen) terimi YOKTU. Docstring (F162) terimi vaat ediyordu ama
``git show ea6582b`` farkında görüldüğü üzere o düzeltme yalnız docstring'e
ve components dalına girmişti. ÖLÇÜM (m = 25 kg, r = 0.05 m, L = 2 m,
x_cg = 0.55·L): eski 8.348958 kg·m², doğru 8.598958 kg·m² — %2.91 EKSİK.

B5 — ``solve()`` ``sol.success`` / ``sol.message`` alanlarını HİÇ okumuyordu
(``grep -c "success" hrma/analysis/six_dof_trajectory.py`` → 0). Entegrasyon
çökse bile ``sol.y`` kısmi yörüngeyi taşıdığı için çöküş yüksekliği "apoje",
kısmi α ise "kararlılık hükmü" diye yayımlanabiliyordu.
"""

import numpy as np
import pytest

from hrma.analysis import six_dof_trajectory as sdt
from hrma.analysis.six_dof_trajectory import BarrowmanAero, SixDOFTrajectory


def _standard_rocket():
    """test_six_dof_trajectory.py ile aynı temsili araç (d=10 cm, L=2 m)."""
    return BarrowmanAero(
        body_diameter=0.10, nose_length=0.40, body_length=2.0,
        nose_type='ogive', fin_count=4, fin_root_chord=0.20,
        fin_tip_chord=0.10, fin_span=0.11, fin_sweep=0.08)


def _solver(**kwargs):
    kw = dict(dry_mass=8.0, propellant_mass=4.0, thrust=1200.0, burn_time=6.0)
    kw.update(kwargs)
    return SixDOFTrajectory(aero=_standard_rocket(), **kw)


# ---------------------------------------------------------------------------
# A6 — tekdüze dalda paralel eksen terimi
# ---------------------------------------------------------------------------
class TestUniformBranchParallelAxis:

    def test_measured_value_matches_analytic(self):
        """Bulgudaki birebir ölçüm: 8.598958 kg·m² (eski 8.348958 reddedilir)."""
        solver = _solver()
        aero = solver.aero
        m, r, L = 25.0, aero.d / 2.0, aero.L
        assert solver.components is None
        assert solver.x_cg_full == pytest.approx(0.55 * L, rel=1e-12)

        merkezcil = m * (3.0 * r * r + L ** 2) / 12.0     # geometrik merkez
        steiner = m * (0.55 * L - 0.5 * L) ** 2           # x_cg'ye kaydırma
        I_t = solver._inertia(m)[1]

        assert merkezcil == pytest.approx(8.348958333333333, rel=1e-12)
        assert I_t == pytest.approx(merkezcil + steiner, rel=1e-12)
        assert I_t == pytest.approx(8.598958333333333, rel=1e-12)
        # Eski (eksik) değer artık kabul edilmiyor
        assert I_t != pytest.approx(merkezcil, rel=1e-6)
        # Eksiklik oranı: doğru değere göre %2.91
        assert (I_t - merkezcil) / I_t == pytest.approx(0.0291, abs=5e-4)

    def test_uses_supplied_cg_not_only_default(self):
        """Terim BEYAN EDİLEN x_cg'ye bağlı; yanma boyunca CG kaydıkça değişir."""
        solver = _solver()
        L, m = solver.aero.L, 20.0
        # x_cg = L/2 → kaydırma sıfır → merkezcil değere döner
        merkezcil = m * (3.0 * (solver.aero.d / 2.0) ** 2 + L ** 2) / 12.0
        assert solver._inertia(m, 0.5 * L)[1] == pytest.approx(
            merkezcil, rel=1e-12)
        # CG'yi öne ya da arkaya aynı miktarda kaydırmak aynı artışı verir
        ileri = solver._inertia(m, 0.5 * L - 0.2)[1]
        geri = solver._inertia(m, 0.5 * L + 0.2)[1]
        assert ileri == pytest.approx(geri, rel=1e-12)
        assert ileri == pytest.approx(merkezcil + m * 0.04, rel=1e-12)
        # Roll ataleti CG'den bağımsız
        assert solver._inertia(m, 0.3 * L)[0] == pytest.approx(
            solver._inertia(m, 0.9 * L)[0], rel=1e-12)

    def test_two_branches_agree_for_same_vehicle(self):
        """Aynı aracı tekdüze YA DA nokta kütle listesiyle tarif → aynı I_t.

        Bu, düzeltmenin asıl gerekçesi: tekdüze bir çubuğu N nokta kütleye
        bölüp ``components`` olarak verirsen components dalı Steiner terimini
        zaten üretiyordu. Terim eklenmeden önce iki dal %2.91 ayrışıyordu.
        Ayrıklaştırma hatası mL²/12 · N⁻² mertebesindedir (N=4000 → ~6e−8).
        """
        n = 4000
        m_total = 12.0
        aero = _standard_rocket()
        L = aero.L
        xs = (np.arange(n) + 0.5) * L / n
        comps = [{'mass': m_total / n, 'x': float(x)} for x in xs]

        uniform = _solver(dry_mass=m_total, propellant_mass=0.0)
        lumped = _solver(dry_mass=m_total, propellant_mass=0.0,
                         components=comps)
        assert lumped.components is not None

        x_cg = uniform.x_cg_full
        I_uniform = uniform._inertia(m_total, x_cg)[1]
        I_lumped = lumped._inertia(m_total, x_cg)[1]
        assert I_lumped == pytest.approx(I_uniform, rel=1e-6)

    def test_flight_still_solves_and_stays_stable(self):
        """Terim eklendikten sonra uçuş hâlâ çözülüyor ve kararlı kalıyor."""
        res = _solver(cd0=0.45).solve(t_max=200.0)
        assert res['converged'] is True
        assert res['end_reason'] == 'apogee'
        assert res['apogee'] > 1000.0
        assert res['stable'] is True


# ---------------------------------------------------------------------------
# B5 — çözücü başarı kapısı
# ---------------------------------------------------------------------------
class _FailedSolution:
    """``solve_ivp``'nin adım çökmesindeki dönüşünü taklit eder.

    SciPy başarısızlıkta İSTİSNA ATMAZ: ``success=False``, ``status=-1``
    döner ve ``y`` çöküşe kadarki kısmi yörüngeyi taşır. Eski kod bu
    alanları hiç okumadığı için kısmi çözümü tam çözüm gibi yayımlıyordu.
    """

    def __init__(self, n=25):
        t = np.linspace(0.0, 2.4, n)
        y = np.zeros((13, n))
        y[2] = np.linspace(0.0, 640.0, n)      # yükseklik (yukarı)
        y[5] = np.linspace(0.0, 310.0, n)      # dikey hız
        y[6] = 1.0                             # birim quaternion
        self.t = t
        self.y = y
        self.t_events = [np.array([]), np.array([]), np.array([])]
        self.success = False
        self.status = -1
        self.message = 'Required step size is less than spacing between numbers.'


class TestSolverSuccessGate:

    @staticmethod
    def _run_failed(monkeypatch, n=25):
        monkeypatch.setattr(sdt, 'solve_ivp',
                            lambda *a, **k: _FailedSolution(n))
        return _solver(cd0=0.45).solve(t_max=200.0)

    def test_failed_solution_publishes_no_apogee(self, monkeypatch):
        """Çökmüş entegrasyonda apoje ve türevleri None; damga açık."""
        res = self._run_failed(monkeypatch)
        assert res['converged'] is False
        assert res['end_reason'] == 'solver_failed'
        assert 'step size' in res['solver_message']
        for key in ('apogee', 'apogee_time', 'max_speed', 'max_mach',
                    'max_alpha_deg', 'stable', 'lateral_drift_at_end'):
            assert res[key] is None, f'{key} çökmüş çözümde yayımlanmamalı'
        # Kısmi seri, çözücünün gerçekten ürettiği veridir — silinmez, ama
        # yerine uydurma sayı da konmaz.
        assert res['time'].size == 25
        assert res['altitude'].max() == pytest.approx(640.0, rel=1e-12)

    def test_geometry_only_fields_survive(self, monkeypatch):
        """Statik marj / C_Nα / CP entegrasyondan gelmez → çöküşte de geçerli."""
        res = self._run_failed(monkeypatch)
        aero = _standard_rocket()
        assert res['cn_alpha'] == pytest.approx(aero.cn_alpha, rel=1e-12)
        assert res['x_cp'] == pytest.approx(aero.x_cp, rel=1e-12)
        assert res['static_margin_full'] == pytest.approx(
            aero.static_margin(0.55 * aero.L), rel=1e-12)

    def test_single_sample_failure_does_not_crash(self, monkeypatch):
        """İlk adımda çöküş (tek örnek) istisna değil, işaretli sonuç üretir."""
        res = self._run_failed(monkeypatch, n=1)
        assert res['converged'] is False
        assert res['apogee'] is None

    def test_successful_solution_still_reports_values(self):
        """Yakınsayan çözümde kapı hiçbir şeyi bastırmıyor (regresyon)."""
        res = _solver(cd0=0.45).solve(t_max=200.0)
        assert res['converged'] is True
        assert res['solver_message']            # SciPy 'terminated' mesajı
        assert isinstance(res['apogee'], float) and res['apogee'] > 0.0
        assert isinstance(res['max_speed'], float)
        assert res['lateral_drift_at_end'] is not None


# ---------------------------------------------------------------------------
# B5b (TARİHE KARIŞTI, 15 Ağu 2026): alan-Mach kök bulucu bekçileri,
# korudukları modülle (kinetic_analysis.py — emekli, silindi) birlikte
# kaldırıldı. Halef kademeli kinetik verim modeli alan-Mach kökü çözmez;
# eksenel-simetrik zincirin kendi Mach çözücüsü heat_transfer_analysis
# içindedir ve kendi testleriyle korunur.
