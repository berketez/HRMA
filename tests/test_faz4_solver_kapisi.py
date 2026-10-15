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


#: UYDURULAN CG VARSAYILANLARI — ÖLÇÜLDÜ (27 Ağustos 2026,
#: six_dof_trajectory.py:656-657): ``x_cg_full``/``x_cg_empty`` verilmezse
#: (ya da 0 verilirse) araç geometrisinden DEĞİL, L'nin kaba bir kesrinden
#: kuruluyor. Bu iki sayı ÖLÇÜLMÜŞ DAVRANIŞTIR, sözleşme değil: kararlılık
#: hükmü (``stable``, ``static_margin_*``) bunlardan çıkıyor (ÖH defter
#: P4B3-07). Yön burada DONDURULUR — kesir sessizce değişirse bekçi kırmızı
#: olur ve değişikliğin deftere yazılmasını zorlar; ama hiçbir bekçi bu
#: kesri DOĞRU sayı gibi yeniden üretmez (aşağıdaki bekçiler solver'ın kendi
#: alanını okur, 0.55*L yazmaz).
CG_VARSAYILAN_KESRI_OLCULEN = {'full': 0.55, 'empty': 0.50}


# ---------------------------------------------------------------------------
# A6 — tekdüze dalda paralel eksen terimi
# ---------------------------------------------------------------------------
class TestUniformBranchParallelAxis:

    def test_varsayilan_cg_kesri_dondurulmus(self):
        """Uydurulan CG kesri bir ÖLÇÜMdür; sessizce değişemez.

        ÖH Faz B (defter P4B3-07). Eski hâlinde ``0.55 * L`` iddiası
        ölçüm bekçisinin İÇİNDE, atalet çapasının yanında duruyordu; bu,
        uydurulan varsayılanı sözleşme mertebesine çıkarıyor ve kusuru
        (kararlılık hükmünün uydurulan CG'den çıkması) kilitliyordu.
        Ölçüm burada AYRI durur ve ne olduğu adıyla yazılıdır.
        """
        solver = _solver()
        L = solver.aero.L
        assert solver.x_cg_full == pytest.approx(
            CG_VARSAYILAN_KESRI_OLCULEN['full'] * L, rel=1e-12), (
            'CG varsayılan kesri değişmiş — bu, yayımlanan statik marjı ve '
            'kararlılık hükmünü doğrudan kaydırır (ÖH defter P4B3-07)')
        assert solver.x_cg_empty == pytest.approx(
            CG_VARSAYILAN_KESRI_OLCULEN['empty'] * L, rel=1e-12)
        # 0 (burun ucu) fiziksel olarak anlamsız -> eksik girdi sayılır.
        assert _solver(x_cg_full=0.0).x_cg_full == pytest.approx(
            CG_VARSAYILAN_KESRI_OLCULEN['full'] * L, rel=1e-12)

    def test_measured_value_matches_analytic(self):
        """Bulgudaki birebir ölçüm: 8.598958 kg·m² (eski 8.348958 reddedilir).

        ÖH Faz B (defter P4B3-07): çapa artık uydurulan varsayılana
        BAĞLI DEĞİL — x_cg açıkça geçirilir, yani sayı Steiner teriminin
        kendisini sınar. Varsayılanın ölçümü ayrı bekçidedir
        (``test_varsayilan_cg_kesri_dondurulmus``).
        """
        solver = _solver()
        aero = solver.aero
        m, r, L = 25.0, aero.d / 2.0, aero.L
        assert solver.components is None
        x_cg = 0.55 * L                                   # açıkça geçirilir

        merkezcil = m * (3.0 * r * r + L ** 2) / 12.0     # geometrik merkez
        steiner = m * (x_cg - 0.5 * L) ** 2               # x_cg'ye kaydırma
        I_t = solver._inertia(m, x_cg)[1]

        assert merkezcil == pytest.approx(8.348958333333333, rel=1e-12)
        assert I_t == pytest.approx(merkezcil + steiner, rel=1e-12)
        assert I_t == pytest.approx(8.598958333333333, rel=1e-12)
        # Eski (eksik) değer artık kabul edilmiyor
        assert I_t != pytest.approx(merkezcil, rel=1e-6)
        # Eksiklik oranı: doğru değere göre %2.91
        assert (I_t - merkezcil) / I_t == pytest.approx(0.0291, abs=5e-4)
        # Argümansız çağrı solver'ın KENDİ beyan ettiği CG'yi kullanmalı
        # (taşıma iddiası: 0.55*L burada yeniden üretilmez).
        assert solver._inertia(m)[1] == pytest.approx(
            solver._inertia(m, solver.x_cg_full)[1], rel=1e-12)

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
        """Statik marj / C_Nα / CP entegrasyondan gelmez → çöküşte de geçerli.

        ÖH Faz B (defter P4B3-07): statik marj iddiası artık testin İÇİNDE
        ``0.55 * aero.L`` uydurulan varsayılanını yeniden üretmiyor —
        çözücünün BEYAN ETTİĞİ CG'den kuruluyor. Böylece bu bekçi taşıma
        iddiası olarak kalır ve uydurulan varsayılanı sözleşmeye
        çevirmez; varsayılanın kendisi ayrı bekçilerde ölçülür/borçlanır.
        """
        res = self._run_failed(monkeypatch)
        solver = _solver(cd0=0.45)
        aero = solver.aero
        assert res['cn_alpha'] == pytest.approx(aero.cn_alpha, rel=1e-12)
        assert res['x_cp'] == pytest.approx(aero.x_cp, rel=1e-12)
        assert res['static_margin_full'] == pytest.approx(
            aero.static_margin(solver.x_cg_full), rel=1e-12)
        assert res['static_margin_empty'] == pytest.approx(
            aero.static_margin(solver.x_cg_empty), rel=1e-12)
        # Kararlılık HÜKMÜ ise çöküşte yayımlanmaz (B5 kapısı).
        assert res['stable'] is None

    def test_uydurulan_cg_beyansiz_hukum_veremiyor(self):
        """Uydurulan CG, hükümle birlikte BEYAN edilmek zorunda.

        ÖH Z5S / PK2 ONARILDI (defter P4B3-07) — xfail borç imi SÖKÜLDÜ.
        ÖNCE: CG verilmediğinde 0,55·L / 0,50·L uyduruluyor ve kararlılık
        hükmü (``stable``, ``static_margin_full/empty``) BU uydurulan sayıdan
        çıkıyordu; çıktıda ne CG değeri ne de kaynağı yayımlanıyordu.
        ÖLÇÜLDÜ (27 Ağustos 2026, d=10 cm / L=2 m): CG verilmeyen koşum ile
        aynı CG açıkça verilen koşum BİREBİR aynı çıktıyı üretiyordu
        (static_margin_full 5,199; uyarı listesi de aynı). Kullanıcı gerçek
        CG'yi (0,30·L) verdiğinde marj 5,199 → 10,199 kalibreye çıkıyor,
        yani fark hükmün mertebesindedir.
        SONRA: ``x_cg_full`` / ``x_cg_empty`` / ``x_cg_source`` /
        ``x_cg_is_estimate`` alanları yayımlanıyor; kesir tahmini kullanılan
        koşumda ``x_cg_source == 'assumed_length_fraction'``, açık CG verilen
        koşumda ``'supplied'`` — yani iki koşum artık ayırt edilebiliyor.
        Sayılar (marj, stable) DEĞİŞMEDİ.
        """
        varsayilan = _solver(cd0=0.45).solve(t_max=200.0)
        L = _standard_rocket().L
        acik = _solver(cd0=0.45,
                       x_cg_full=CG_VARSAYILAN_KESRI_OLCULEN['full'] * L,
                       x_cg_empty=CG_VARSAYILAN_KESRI_OLCULEN['empty'] * L
                       ).solve(t_max=200.0)
        # Ön koşul: iki koşum aynı sayıyı kullanıyor (fizik aynı).
        assert varsayilan['static_margin_full'] == pytest.approx(
            acik['static_margin_full'], rel=1e-12)
        assert varsayilan['stable'] is True
        # Asıl iddia: uydurulmuş olması bir yerde GÖRÜNMELİ.
        kodlar = {w['code'] for w in varsayilan['warnings']}
        acik_kodlar = {w['code'] for w in acik['warnings']}
        beyan_alani = any(k for k in varsayilan if 'cg' in k.lower())
        assert (kodlar - acik_kodlar) or beyan_alani, (
            'CG uydurulduğu hâlde çıktı, CG\'nin açıkça verildiği koşumdan '
            f'ayırt edilemiyor (uyarı kodları {sorted(kodlar)}, CG alanı '
            f'yok). Aynı modül eksik ENLEM için uyarı yayımlıyor; eksik CG '
            'kararlılık hükmünü doğrudan belirlediği hâlde sessiz')

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
