"""V307/K2 — ÇALKANTI-6DOF bağlama bekçileri (KARTLAR §2 K2; CALKANTI §B, §C).

§C-a   sağ tarafın sonlu fark Jacobian'ının özdeğerleri ⟷ kapalı biçim
       (a1) Ω_c (boşluk, bağıl 10⁻⁶) ve (a0) (büyük u, bağıl 10⁻³); zaman
       alanında boşlukta çalkantı frekansı ⟷ Ω_c
§C-b   m1 = 0'da 100 rastgele durumda ilk 13 türev rijit çözücüyle
       ``np.array_equal``; m1/m → 0 dizisinde etki m1 ile doğrusal, 10⁻⁹'da
       yörünge ölçütleri
§C-c   çalkantı kapalıyken 6-DOF bugünkü (taban 0d369e4b7) ile BİT-AYNI:
       üç katı vaka + sıvı + hibrit, çözücünün bütün sayısal alanları ``==``
Hüküm  85 km'de HÜKÜM YOK; yere çarpan araçta KARARLI yok; rozette tek durum
Hurwitz ⟷ özdeğer tutarlılığı; ζ_min > 0 örneği (betik v2 §H, Örnek-4);
       (B-5)–(B-7) ⟷ betik v2 §F kökleri; girdi kapıları; ray 15° kapısı.

Örnek araç/tank sayıları KEYFÎ DOĞRULAMA GİRDİSİDİR (boyutça tutarlı).
Kanıt: docs/scofield/raw/OH/V307/calkanti-6dof/RAPOR.md.
"""
import contextlib
import importlib.util
import io
import json
import math
import pathlib
import subprocess
import sys
import types

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from hrma.analysis import six_dof_slosh as sds
from hrma.analysis import slosh_tablo as st
from hrma.analysis.six_dof_trajectory import (
    BarrowmanAero, SixDOFTrajectory, _quat_from_elevation_azimuth)
from hrma.analysis.slosh_analysis import silindir_tablosu

KOK = pathlib.Path(__file__).resolve().parents[1]
#: §C-c referansı: K2'nin başladığı entegrasyon tabanı (bakim/3.0.6 4e801ce52
#: + K1 + K3a). Ana model yeniden tabanlarsa bu SHA yeni tabana çekilir ve
#: test yeniden koşulur (KARTLAR §1 bekçisi).
TABAN_SHA = '0d369e4b7'

RHO_LOX = 1141.0


def _arac(**ek):
    aero = BarrowmanAero(0.20, 0.6, 4.0, fin_count=4, fin_root_chord=0.3,
                         fin_tip_chord=0.15, fin_span=0.18, fin_sweep=0.1)
    kw = dict(aero=aero, dry_mass=40.0, propellant_mass=43.0, thrust=3000.0,
              burn_time=12.0, x_cg_full=2.2, x_cg_empty=2.0,
              launch_elevation_deg=88.0, rail_length=6.0)
    kw.update(ek)
    return kw


def _tank(rho=RHO_LOX, R=0.09, H=1.0, nu=1.7e-7, sigma=0.0132, x=2.6,
          dolu=0.95, kalan=0.02, t_b=12.0, zeta_ek=None, tid='oksitleyici'):
    tab = silindir_tablosu(tid, R, H, rho, 'LOX', sigma=sigma, nu=nu)
    m0 = rho * math.pi * R * R * H * dolu
    tt = np.linspace(0.0, t_b, 25)
    mm = m0 * (1.0 - tt / t_b * (1.0 - kalan / dolu))
    return {'tank_id': tid, 'x_tank_taban_m': x, 'tablo': tab,
            'm_t': {'t': list(tt), 'm': list(mm)}, 'zeta_ek': zeta_ek}


# ---------------------------------------------------------------------------
# Yardımcılar: boşluk/yüksek hız durumu ve sonlu fark Jacobian'ı
# ---------------------------------------------------------------------------
def _durum(s, h, u, el=90.0, eta=None):
    q0 = _quat_from_elevation_azimuth(el, 0.0)
    C = np.array(__import__('hrma.analysis.six_dof_trajectory',
                            fromlist=['_quat_to_dcm'])._quat_to_dcm(q0))
    y = np.concatenate([[0.0, 0.0, h], u * C[:, 0], q0, np.zeros(3)])
    n = s._slosh.n if s._slosh is not None else 0
    z = np.zeros(4 * n)
    if eta is not None:
        z[:2 * n] = np.ravel(eta)
    return np.concatenate([y, z])


def _jacobian(f, t, y):
    J = np.zeros((y.size, y.size))
    for j in range(y.size):
        h = 1e-6 * max(1.0, abs(y[j]))
        yp, ym = y.copy(), y.copy()
        yp[j] += h
        ym[j] -= h
        J[:, j] = (f(t, yp) - f(t, ym)) / (2.0 * h)
    return J


def _bosluk_cozucu(F=6000.0, kuru=400.0, R=0.15, H=1.2, dolu=0.6, x=1.8):
    """Boşluk testi aracı: itici kütlesi 0 (sabit kütle, ṁ = 0 → jet sönümü
    yok), sabit itki, sıvı kuru kütlenin içinde (sabit m_t), ν yok (ζ = 0)."""
    tab = silindir_tablosu('oksitleyici', R, H, RHO_LOX, 'LOX', sigma=None,
                           nu=None)
    m_s = RHO_LOX * math.pi * R * R * H * dolu
    aero = BarrowmanAero(0.4, 0.8, 5.0, fin_count=4, fin_root_chord=0.4,
                         fin_tip_chord=0.2, fin_span=0.3, fin_sweep=0.15)
    s = SixDOFTrajectory(aero=aero, dry_mass=kuru, propellant_mass=0.0,
                         thrust=F, burn_time=100.0, x_cg_full=2.6,
                         x_cg_empty=2.6, rail_length=6.0,
                         slosh_tanks=[{'tank_id': 'oksitleyici',
                                       'x_tank_taban_m': x, 'tablo': tab,
                                       'm_t': {'t': [0.0, 100.0],
                                               'm': [m_s, m_s]},
                                       'zeta_ek': None}])
    s._r0 = np.zeros(3)
    return s


# ---------------------------------------------------------------------------
# §C-a
# ---------------------------------------------------------------------------
class TestCa:
    def test_bosluk_jacobian_ozdegerleri_omega_c(self):
        """(a1): boşlukta RHS Jacobian'ı ±iΩ_c'yi (iki düzlem) 10⁻⁶ ile verir."""
        s = _bosluk_cozucu()
        t = 5.0
        y = _durum(s, 300e3, 1500.0)
        J = _jacobian(s._derivatives, t, y)
        lam = np.linalg.eigvals(J)
        m = s._mass_at(t)
        x_cg = s._cg_at(t)
        _, I_t = s._inertia(m, x_cg)
        f = s._thrust_at(t) / m
        p = s._slosh.parametreler(t, x_cg, f)[0]
        assert p['acik'] and p['zeta'] == 0.0
        Oc = sds.omega_c_kapali(m, I_t, p['m1'], p['L1'], p['xi'], f)
        assert Oc > math.sqrt(p['w1sq'])          # bağlaşım frekansı yükseltir
        yakin = sorted(lam, key=lambda z: abs(z - 1j * Oc))[:2]
        for z in yakin:                            # yunuslama + sapma
            assert abs(z - 1j * Oc) / Oc < 1e-6, (z, Oc)
        # doğrusal model (aerodinamiksiz, u = 0) aynı Ω_c
        A = sds.bosluk_modeli(m, I_t, f, [(p['m1'], p['xi'], p['w1sq'], 0.0)])
        lb = np.linalg.eigvals(A)
        assert min(abs(z - 1j * Oc) for z in lb) / Oc < 1e-12

    def test_yuksek_hiz_jacobian_a0(self):
        """(a0): büyük u'da RHS Jacobian'ının gövde+çalkantı kökleri kapalı
        biçim A s⁴ + B s² + C köklerine bağıl 10⁻³ içinde."""
        s = _bosluk_cozucu(F=3.0e4, kuru=900.0, R=0.2, H=1.5, dolu=0.5, x=2.0)
        t = 5.0
        y = _durum(s, 52e3, 6000.0)
        k = sds.dondurulmus_katsayilar(s, t, y)
        p = [q for q in k['prm'] if q['acik']][0]
        kok, (A, B, C) = sds.a0_kokleri(k['m'], k['I'], p['m1'], p['L1'],
                                        p['xi'], k['f_x'], k['N_alpha'],
                                        k['M_alpha'])
        lam = np.linalg.eigvals(_jacobian(s._derivatives, t, y))
        enkotu = max(min(abs(z - r) for z in lam) / abs(r) for r in kok)
        assert enkotu < 1e-3, enkotu
        # (B-5)–(B-7): u̇ = 0'da yüksek hız sınırı (a0)'dır (betik v2 §D
        # denetim 2); u̇α terimi kökleri MUTLAK olarak u̇/u mertebesinde
        # kaydırır (α = −w/u'nun kinematiği; tasarım §C-a açık kalem 1).
        tt = [(p['m1'], p['xi'], p['w1sq'], 0.0)]
        ortak = (k['m'], k['I'], k['u'])
        aero = (k['N_alpha'], k['M_alpha'], k['M_q'], k['f_x'])
        l0 = np.linalg.eigvals(sds.dogrusal_model(*ortak, 0.0, *aero, tt))
        assert max(min(abs(z - r) for z in l0) / abs(r) for r in kok) < 1e-3
        lu = np.linalg.eigvals(sds.dogrusal_model(*ortak, k['u_dot'], *aero,
                                                  tt))
        kayma = max(min(abs(z - r) for z in lu) for r in l0)
        assert 0.0 < kayma <= 2.0 * abs(k['u_dot']) / k['u'], kayma

    def test_zaman_alani_bosluk_frekansi(self):
        """Boşlukta sabit itkiyle çalkantı salınım frekansı ⟷ Ω_c."""
        s = _bosluk_cozucu()
        t0 = 2.0
        y0 = _durum(s, 300e3, 1500.0, eta=[[0.0, 1e-4]])
        m = s._mass_at(t0)
        x_cg = s._cg_at(t0)
        _, I_t = s._inertia(m, x_cg)
        f = s._thrust_at(t0) / m
        p = s._slosh.parametreler(t0, x_cg, f)[0]
        Oc = sds.omega_c_kapali(m, I_t, p['m1'], p['L1'], p['xi'], f)
        T = 2 * math.pi / Oc
        sol = solve_ivp(s._derivatives, (t0, t0 + 30 * T), y0, method='DOP853',
                        rtol=1e-10, atol=1e-13, max_step=T / 40)
        ez = sol.y[13 + 1]                      # tank 0, η_z
        zc = [sol.t[i] - ez[i] * (sol.t[i + 1] - sol.t[i]) / (ez[i + 1] - ez[i])
              for i in range(ez.size - 1) if ez[i] > 0 >= ez[i + 1]]
        Om = 2 * math.pi / np.mean(np.diff(zc))
        assert len(zc) >= 25
        assert abs(Om - Oc) / Oc < 1e-3, (Om, Oc)


# ---------------------------------------------------------------------------
# §C-b
# ---------------------------------------------------------------------------
class TestCb:
    def test_m1_sifirda_ilk_13_turev_bit_ayni(self, monkeypatch):
        kw = _arac()
        rij = SixDOFTrajectory(**kw)
        cal = SixDOFTrajectory(**kw, slosh_tanks=[_tank()])
        rij._r0 = np.zeros(3)
        cal._r0 = np.zeros(3)
        asil = cal._slosh.parametreler

        def m1_sifir(t, x_cg, f_x, **k):
            out = asil(t, x_cg, f_x, **k)
            for p in out:
                if p['acik']:
                    p['m1'] = 0.0               # bağlı ama kütlesiz
            return out
        monkeypatch.setattr(cal._slosh, 'parametreler', m1_sifir)
        rng = np.random.default_rng(20261104)
        ray = serbest = acik = 0
        for i in range(100):
            q = rng.normal(size=4)
            q /= np.linalg.norm(q)
            r = rng.normal(size=3) * (2.0 if i % 4 == 0 else 3000.0)
            r[2] = abs(r[2])
            y = np.concatenate([r, rng.normal(size=3) * 300.0, q,
                                rng.normal(size=3) * 2.0,
                                rng.normal(size=4) * 0.01,
                                rng.normal(size=4) * 0.1])
            t = float(rng.uniform(0.0, 11.9))
            d_r = rij._derivatives(t, y[:13])
            d_c = cal._derivatives(t, y)
            assert d_c.size == 17
            assert np.array_equal(d_r, d_c[:13]), i
            if np.linalg.norm(r) < 6.0:
                ray += 1
            else:
                serbest += 1
            acik += int(np.any(d_c[13:] != 0.0))
        assert ray >= 10 and serbest >= 50 and acik >= 50

    def test_m1_sifira_giderken_etki_dogrusal(self):
        """m1 ∝ ρ_s: (10⁻³, 10⁻⁶, 10⁻⁹) dizisinde etki m1 ile doğrusal (fark
        oranı ~10³ ± %20); 10⁻⁹'da rijit koşuyla apoje ≤ 10⁻⁴ bağıl.

        α ölçütü (tasarım düzeltmesi, CALKANTI §C-b): durum 13 → 17 büyüyünce
        çalkantı modu adımları sıklaştırır; ``max_alpha_deg`` pencere
        girişindeki örneğe bağlı olduğu için rijit koşunun KENDİSİ max_step
        0,1/0,05/0,02/0,01'de 5,99–6,64° verir (rüzgârlı vaka). Ölçüt: 10⁻⁹
        koşusunun α(t)'si (rijit örnek anlarına aradeğerli) ve max α'sı rijit
        çözücünün kendi adım duyarlılığı içinde; 10⁻⁶ ile 10⁻⁹ kalıntıları
        aynı (çalkantı katkısı yok, kalan entegratör adım dizisi).
        """
        kw = _arac(wind_speed=6.0)
        rij = SixDOFTrajectory(**kw).solve()
        sonuc = {}
        for eps in (1e-3, 1e-6, 1e-9):
            # σ verilmez: Bo = ρ g R²/σ de ρ ile küçülür ve Bond kapısı
            # (Bo < 10 RET) tankı kapatırdı; ölçekleme yalnız m1'i değiştirsin.
            s = SixDOFTrajectory(**kw, slosh_tanks=[
                _tank(rho=RHO_LOX * eps, sigma=None)])
            sonuc[eps] = s.solve()
            assert sonuc[eps]['slosh_active'].any()
        for alan in ('apogee', 'max_alpha_deg'):
            d1 = sonuc[1e-3][alan] - sonuc[1e-9][alan]
            d2 = sonuc[1e-6][alan] - sonuc[1e-9][alan]
            oran = d1 / d2
            assert 0.8 * 1e3 < oran < 1.2 * 1e3, (alan, d1, d2, oran)
        a9 = sonuc[1e-9]
        assert abs(a9['apogee'] - rij['apogee']) / rij['apogee'] <= 1e-4
        tr = rij['time']
        pen = (tr > 1.0) & (tr < a9['time'][-1])

        def dalfa(o):
            return np.max(np.abs(np.interp(tr[pen], o['time'], o['alpha_deg'])
                                 - rij['alpha_deg'][pen]))
        assert abs(dalfa(a9) - dalfa(sonuc[1e-6])) < 1e-6
        duyarlilik, maxa = [], [rij['max_alpha_deg']]
        for ms in (0.05, 0.02, 0.01):
            rf = SixDOFTrajectory(**kw).solve(max_step=ms)
            duyarlilik.append(dalfa(rf))
            maxa.append(rf['max_alpha_deg'])
        assert dalfa(a9) <= max(duyarlilik)
        assert min(maxa) <= a9['max_alpha_deg'] <= max(maxa)


# ---------------------------------------------------------------------------
# §C-c — çalkantı kapalıyken BİT-AYNI (taban 0d369e4b7)
# ---------------------------------------------------------------------------
def _taban_modulu():
    try:
        kod = subprocess.run(
            ['git', '-C', str(KOK), 'show',
             f'{TABAN_SHA}:hrma/analysis/six_dof_trajectory.py'],
            capture_output=True, check=True, timeout=30).stdout.decode('utf-8')
    except (OSError, subprocess.SubprocessError):
        pytest.skip(f'git nesnesi {TABAN_SHA} yok (sığ klon); §C-c kanıtı '
                    'docs/scofield/raw/OH/V307/calkanti-6dof/olcum_cc_*.json')
    mod = types.ModuleType('six_dof_trajectory_taban')
    mod.__file__ = 'six_dof_trajectory_taban.py'
    exec(compile(kod, mod.__file__, 'exec'), mod.__dict__)
    return mod


def _esit(a, b, yol=''):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        assert np.array_equal(np.asarray(a), np.asarray(b)), yol
        return
    if isinstance(a, dict):
        assert set(a) == set(b), yol
        for k in a:
            _esit(a[k], b[k], f'{yol}.{k}')
        return
    if isinstance(a, (list, tuple)):
        assert len(a) == len(b), yol
        for i, (x, z) in enumerate(zip(a, b)):
            _esit(x, z, f'{yol}[{i}]')
        return
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a):
        assert math.isnan(b), yol
        return
    assert a == b, (yol, a, b)


class TestCc:
    CC_VAKALARI = (('kati', 'L1'), ('kati', 'L3'), ('kati', 'L4'),
               ('sivi', 'L3'), ('hibrit', 'L3'))

    @pytest.fixture(scope='class')
    def istemci(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    @pytest.mark.parametrize("sistem,L", CC_VAKALARI)
    def test_calkanti_kapali_bit_ayni(self, istemci, sistem, L):
        from tests.support.kanit import kanit_gerekli
        from hrma.analysis import six_dof_trajectory as sdt
        from hrma.analysis.flight_vehicle import motor_flight_thrust
        taban = _taban_modulu()
        yol = kanit_gerekli(KOK / 'docs/scofield/raw/OH/V306/muhendis-turu'
                            / sistem / 'vakalar' / (L + '.json'))
        v = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
        fv = [r for r in v['istekler'] if r['uc'] == '/api/flight-vehicle'][-1]
        g = dict([r for r in v['istekler']
                  if r['uc'] == '/api/six-dof-analysis'][-1]['govde'])
        u = motor_flight_thrust({'kati': 'solid', 'sivi': 'liquid',
                                 'hibrit': 'hybrid'}[sistem],
                                fv['govde']['results'])
        g['nozzle_exit_area'] = u['nozzle_exit_area_m2']
        g['thrust_reference_pressure'] = u['thrust_reference_pressure_pa']
        sonuc = {}
        for ad, sinif, aero in (
                ('simdi', sdt.SixDOFTrajectory, sdt.BarrowmanAero),
                ('taban', taban.SixDOFTrajectory, taban.BarrowmanAero)):
            yakala = []
            asil = sinif.solve

            def sar(self, *a, _asil=asil, _y=yakala, **k):
                out = _asil(self, *a, **k)
                _y.append(out)
                return out
            eski = (sdt.SixDOFTrajectory, sdt.BarrowmanAero)
            sdt.SixDOFTrajectory, sdt.BarrowmanAero = sinif, aero
            sinif.solve = sar
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    r = istemci.post('/api/six-dof-analysis', json=g)
            finally:
                sinif.solve = asil
                sdt.SixDOFTrajectory, sdt.BarrowmanAero = eski
            assert r.status_code == 200
            assert len(yakala) == 1
            yanit = r.get_json()
            yanit.pop('solver_wall_time_s', None)
            sonuc[ad] = (yakala[0], yanit)
        cs, ct = sonuc['simdi'][0], sonuc['taban'][0]
        assert not [k for k in cs if k.startswith('slosh') or k == 'g_eff']
        _esit(cs, ct, sistem + L)
        _esit(sonuc['simdi'][1], sonuc['taban'][1], sistem + L + ':yanit')

    def test_bos_liste_none_ile_ayni(self):
        kw = _arac()
        a = SixDOFTrajectory(**kw).solve()
        b = SixDOFTrajectory(**kw, slosh_tanks=[]).solve()
        assert set(a) == set(b) and np.array_equal(a['altitude'], b['altitude'])
        _esit(a, b)


# ---------------------------------------------------------------------------
# Hüküm kuralları
# ---------------------------------------------------------------------------
class TestHukum:
    def test_85_km_hukum_yok(self):
        """Havasız bölgede (85 km) dondurulmuş katsayı ölçütü sağlanmaz."""
        s = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank()])
        s._r0 = np.zeros(3)
        t = 6.0
        y = _durum(s, 85e3, 1500.0)
        a = sds._an_degerlendir(s, 'en_buyuk_q', t, np.array([t]),
                                y[:, None], {'converged': True}, 'apogee')
        assert a['hukum'] == sds.HUKUM_YOK
        assert a['sebep'] == 'DONDURULMUS_KATSAYI_GECERSIZ'
        assert a['dondurulmus_olcut'] < sds.DONDURULMUS_KATSAYI_ESIGI
        # aynı araç, aynı hız, 2 km'de ölçüt sağlanır ve hüküm verilir
        y2 = _durum(s, 2e3, 300.0)
        b = sds._an_degerlendir(s, 'en_buyuk_q', t, np.array([t]),
                                y2[:, None], {'converged': True}, 'apogee')
        assert b['hukum'] in (sds.HUKUM_KARARLI, sds.HUKUM_CALKANTI_KARARSIZ,
                              sds.HUKUM_RIJIT_KARARSIZ)

    def test_yere_carpan_aracta_kararli_yok(self):
        """Uzun yanmalı alçak atış itki altında yere çarpar: tek hüküm
        HUKUM_YOK (uçuş apojeye varmadı), hiçbir anda KARARLI yok."""
        kw = _arac(launch_elevation_deg=45.0, thrust=1500.0, burn_time=30.0,
                   propellant_mass=30.0, rail_length=2.0)
        out = SixDOFTrajectory(**kw, slosh_tanks=[_tank(t_b=30.0)]).solve()
        assert out['flight_verdict']['flight'] == 'ground_impact_under_power'
        ss = out['slosh_stability']
        assert ss['hukum'] == sds.HUKUM_YOK
        assert ss['sebep'] == ['UCUS_APOJEYE_VARMADI']
        assert all(a['hukum'] != sds.HUKUM_KARARLI for a in ss['anlar'].values())
        # yere çarpma anındaki en büyük q: dondurulmuş katsayı ölçütü
        # SAĞLANIYOR ve kökler sol yarı düzlemde — yine de KARARLI denmez
        q = ss['anlar']['en_buyuk_q']
        assert q['dondurulmus_olcut'] >= sds.DONDURULMUS_KATSAYI_ESIGI
        assert q['kararli_ozdeger'] is True
        assert q['sebep'] == 'UCUS_APOJEYE_VARMADI'
        assert 'RAY_STATIK_EGIM_SINIR_DISI' in ss['baslangic_beyan']

    def test_rozette_tek_durum_ve_ornek_arac(self):
        out = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank()]).solve()
        ss = out['slosh_stability']
        assert isinstance(ss['hukum'], str) and ss['hukum'] in sds.HUKUMLER
        assert ss['hukum'] == sds.HUKUM_KARARLI
        for ad in sds.ANLAR:
            assert isinstance(ss['anlar'][ad]['hukum'], str)
        assert ss['anlar']['kalkis']['sebep'] == 'KALKIS_ANI_ALFA_TANIMSIZ'
        assert ss['anlar']['kalkis']['omega_c_rad_s']
        assert ss['kapsam_disi']['kod'] == sds.KAPSAM_DISI_KODU
        # 6-DOF'un kendi hükmü tek durum olarak kalır
        assert out['flight_verdict']['stability'] == 'stable'

    def test_calkanti_kaynakli_kararsizlik_hukmu(self, monkeypatch):
        """Örnek-4 katsayılarıyla (betik v2 §H) bir anda ÇALKANTI KAYNAKLI
        KARARSIZLIK hükmü, ζ_min ve bafl önerisi."""
        s = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank()])
        s._r0 = np.zeros(3)
        k4 = _ornek4()

        def sahte(cozucu, t, y):
            return {'t': t, 'm': k4['m'], 'I': k4['I'], 'x_cg': 2.1,
                    'u': k4['u'], 'u_dot': k4['ud'], 'rho': 0.5,
                    'qbar': 4e4, 'mach': 1.2, 'cn_alpha': 8.0, 'x_cp': 3.6,
                    'N_alpha': k4['Na'], 'M_alpha': k4['Ma'], 'M_q': k4['Mq'],
                    'f_x': k4['f'], 'dqbar_dt': 0.0, 'altitude_m': 3e3,
                    'ray': False,
                    'prm': [{'acik': True, 'm1': k4['m1'], 'xi': k4['xi'],
                             'w1sq': k4['w1sq'], 'c': 0.0, 'zeta': 0.0,
                             'L1': k4['L1'], 'doluluk': 0.3, 'kod': []}]}
        monkeypatch.setattr(sds, 'dondurulmus_katsayilar', sahte)
        a = sds._an_degerlendir(s, 'en_buyuk_q', 3.0, np.array([3.0]),
                                np.zeros((17, 1)), {'converged': True},
                                'apogee')
        assert a['hukum'] == sds.HUKUM_CALKANTI_KARARSIZ
        assert a['rijit_kararli'] and not a['kararli_ozdeger']
        assert a['zeta_min'] == pytest.approx(0.022517, rel=1e-4)
        assert a['bafl_onerisi'][0]['oneri']['target_damping_ratio'] == \
            pytest.approx(a['zeta_min'])


# ---------------------------------------------------------------------------
# Doğrusal model, Hurwitz, ζ_min
# ---------------------------------------------------------------------------
def _ornek4():
    """Betik v2 §H Örnek-4 (keyfî doğrulama girdisi)."""
    m, I, u = 5000.0, 10000.0, 400.0
    ud = 15.0 - 9.80665 * math.sin(math.radians(80.0))
    S = math.pi * 1.0 ** 2 / 4.0
    qb = 0.5 * 0.5 * u * u
    Na = qb * S * 8.0
    Ma = -1.5 * Na
    Mq = -qb * S * 8.0 * 1.5 ** 2 / u
    R, h, f = 0.4, 0.12, 15.0
    xi1 = 1.841183781340659
    w2 = f * xi1 / R * math.tanh(xi1 * h / R)
    mL = RHO_LOX * math.pi * R * R * h
    m1 = mL * 2 * R * math.tanh(xi1 * h / R) / (xi1 * (xi1 * xi1 - 1) * h)
    der = 2 * R / xi1 * math.tanh(xi1 * h / (2 * R))
    return dict(m=m, I=I, u=u, ud=ud, Na=Na, Ma=Ma, Mq=Mq, f=f, m1=m1,
                L1=f / w2, w1sq=w2, xi=1.0 - der)


class TestDogrusalModel:
    def test_betik_v2_ornek1_kokleri(self):
        """(B-5)–(B-7), u̇ = 0: betik v2 §F Örnek-1 kökleri (6 basamak)."""
        xi1 = 1.841183781340659
        R, h, f = 0.14, 0.60, 45.0
        w2 = f * xi1 / R * math.tanh(xi1 * h / R)
        mL = RHO_LOX * math.pi * R * R * h
        m1 = mL * 2 * R * math.tanh(xi1 * h / R) / (xi1 * (xi1 ** 2 - 1) * h)
        der = 2 * R / xi1 * math.tanh(xi1 * h / (2 * R))
        S = math.pi * 0.3 ** 2 / 4
        qb = 0.5 * 0.7 * 500.0 ** 2
        Na = qb * S * 9.0
        Mq = -qb * S * 9.0 * 0.8 ** 2 / 500.0 - 6.0 * 2.2 ** 2
        A = sds.dogrusal_model(450.0, 420.0, 500.0, 0.0, Na, -0.8 * Na, Mq, f,
                               [(m1, 1.10 - der, w2, 0.002)])
        lam = np.linalg.eigvals(A)
        for hedef in (-0.242830 + 10.300607j, -0.051286 + 24.570865j):
            assert min(abs(z - hedef) for z in lam) < 2e-6

    def test_ornek4_zeta_min_ve_a0(self):
        k = _ornek4()
        tt = [(k['m1'], k['xi'], k['w1sq'], 0.0)]
        A = sds.dogrusal_model(k['m'], k['I'], k['u'], k['ud'], k['Na'],
                               k['Ma'], k['Mq'], k['f'], tt)
        lam = np.linalg.eigvals(A)
        assert lam.real.max() == pytest.approx(0.091663, abs=2e-6)
        zmin = sds.zeta_min_ara(k['m'], k['I'], k['u'], k['ud'], k['Na'],
                                k['Ma'], k['Mq'], k['f'], tt)
        assert zmin == pytest.approx(0.022517, rel=1e-4)
        _, (Aa, B, C) = sds.a0_kokleri(k['m'], k['I'], k['m1'], k['L1'],
                                       k['xi'], k['f'], k['Na'], k['Ma'])
        assert B * B - 4 * Aa * C < 0.0          # frekans birleşmesi
        # ζ_min'in hemen altı kararsız, üstü kararlı
        for z, beklenen in ((0.999 * zmin, False), (1.001 * zmin, True)):
            Az = sds.dogrusal_model(k['m'], k['I'], k['u'], k['ud'], k['Na'],
                                    k['Ma'], k['Mq'], k['f'],
                                    [(k['m1'], k['xi'], k['w1sq'], z)])
            assert bool(np.all(np.linalg.eigvals(Az).real < 0)) is beklenen

    def test_karisik_modlarda_etiket_tekil(self):
        """Frekans yakınlığında (Örnek-4, ω_b ≈ ω1) iki mod güçlü karışır;
        her salınımlı çift TEK etiket alır (gövde + tank), katılım payları
        yayımlanır ve toplamı 1."""
        k = _ornek4()
        an = sds.an_analizi(k['m'], k['I'], k['u'], k['ud'], k['Na'], k['Ma'],
                            k['Mq'], k['f'],
                            [(k['m1'], k['xi'], k['w1sq'], 0.05)], 0.05)
        et = sorted(m['mod'] for m in an['modlar'])
        assert et == ['calkanti:0', 'govde']
        for m in an['modlar']:
            assert sum(m['katilim'].values()) == pytest.approx(1.0)
            assert max(m['katilim'].values()) < 0.95      # gerçekten karışık
        assert an['yakinlik'][0]['uyari'] is True

    def test_hurwitz_ozdeger_tutarli(self):
        rng = np.random.default_rng(7)
        say = {True: 0, False: 0}
        for _ in range(300):
            n_t = int(rng.integers(1, 3))
            tt = [(float(rng.uniform(1, 200)), float(rng.uniform(-3, 3)),
                   float(rng.uniform(4, 900)), float(rng.uniform(0, 0.05)))
                  for _ in range(n_t)]
            m = float(rng.uniform(800, 20000))
            I = m * float(rng.uniform(1, 10))
            u = float(rng.uniform(50, 1500))
            Na = float(rng.uniform(1e3, 5e5))
            A = sds.dogrusal_model(m, I, u, float(rng.uniform(-5, 40)), Na,
                                   -float(rng.uniform(-0.3, 2.0)) * Na,
                                   -float(rng.uniform(0, 2e3)),
                                   float(rng.uniform(5, 60)), tt)
            lam = np.linalg.eigvals(A)
            if abs(lam.real.max()) < 1e-7 * np.abs(lam).max():
                continue                          # sınırda: işaret anlamsız
            kats, r = sds.karakteristik_polinom(A)
            ref = np.real(np.poly(lam / r))
            assert np.allclose(kats, ref, rtol=1e-6, atol=1e-9)
            hw, _ = sds.hurwitz_kararli(kats)
            oz = bool(np.all(lam.real < 0))
            assert hw == oz
            say[oz] += 1
        assert say[True] > 30 and say[False] > 30


# ---------------------------------------------------------------------------
# Girdi kapıları, ray kapısı, kapanma, zaman alanı
# ---------------------------------------------------------------------------
class TestGirdi:
    @pytest.mark.parametrize('degis,kod', [
        (lambda g: g.update(fazla=1), 'ALAN_BILINMEYEN'),
        (lambda g: g.pop('zeta_ek'), 'ALAN_EKSIK'),
        (lambda g: g.update(tank_id='yakit'), 'TANK_KIMLIGI_TABLO'),
        (lambda g: g.update(tank_id='kerosen'), 'TANK_KIMLIGI'),
        (lambda g: g.update(tablo={'sema': 'x'}), 'TIP'),
        (lambda g: g.update(x_tank_taban_m=9.0), 'TANK_KONUMU_ARAC_DISI'),
        (lambda g: g.update(x_tank_taban_m=0.5), 'TANK_KONUMU_ARAC_DISI'),
        (lambda g: g.update(x_tank_taban_m=float('nan')), 'SAYI_DEGIL'),
        (lambda g: g.update(zeta_ek=1.0), 'ARALIK'),
        (lambda g: g.update(zeta_ek=-0.1), 'ARALIK'),
        (lambda g: g.update(m_t={'t': [0, 1, 1], 'm': [3, 2, 1]}), 'SIRA'),
        (lambda g: g.update(m_t={'t': [0, 1], 'm': [3, -1]}), 'ARALIK'),
        (lambda g: g.update(m_t={'t': [0, 1], 'm': [500, 1]}), 'KUTLE_TUTARSIZ'),
        (lambda g: g.update(m_t={'t': [0], 'm': [1, 2]}), 'BOYUT'),
        (lambda g: g.update(m_t=[1, 2]), 'TIP'),
    ])
    def test_adli_ret(self, degis, kod):
        g = _tank()
        degis(g)
        with pytest.raises(sds.SloshBaglamaHatasi) as e:
            SixDOFTrajectory(**_arac(), slosh_tanks=[g])
        assert e.value.kod == kod

    def test_tank_tekrari_ve_atalet_tutarsizligi(self):
        with pytest.raises(sds.SloshBaglamaHatasi) as e:
            SixDOFTrajectory(**_arac(), slosh_tanks=[_tank(), _tank()])
        assert e.value.kod == 'TANK_KIMLIGI_TEKRAR'
        # 2 kg'lık narin araçta 40 kg sıvı: rijit kısmın ataleti negatif
        with pytest.raises(sds.SloshBaglamaHatasi) as e:
            SixDOFTrajectory(**_arac(dry_mass=2.0, propellant_mass=60.0,
                                     x_cg_full=0.5, x_cg_empty=0.5),
                             slosh_tanks=[_tank(x=4.0)])
        assert e.value.kod == 'ATALET_TUTARSIZ'

    def test_kutle_yoksa_baglanmaz_uydurma_yok(self):
        g = _tank()
        g['m_t'] = None
        out = SixDOFTrajectory(**_arac(), slosh_tanks=[g]).solve()
        ss = out['slosh_stability']
        assert ss['hukum'] == sds.HUKUM_UYGULANMAZ
        assert ss['sebep'] == ['TANK_BAGLANMADI']
        assert ss['tanks_not_coupled'][0]['sebep'] == ['TANK_KUTLESI_VERILMEDI']
        assert 'slosh_eta' not in out

    def test_tek_nokta_kutle_itkiyle_orantili(self):
        g = _tank()
        g['m_t'] = {'t': [0.0], 'm': [g['m_t']['m'][0]]}
        s = SixDOFTrajectory(**_arac(), slosh_tanks=[g])
        m0 = g['m_t']['m'][0]
        for t in (0.0, 3.0, 9.0):
            kesir = (s._mass_at(t) - s.m_dry) / s.m_prop
            assert s._slosh.sivi_kutlesi(0, t)[0] == pytest.approx(m0 * kesir)
        assert 'TANK_TUKETIMI_ITKIYLE_ORANTILI' in s._slosh.tanklar[0]['beyan']

    @pytest.mark.parametrize('el,kapi', [(85.0, False), (70.0, True)])
    def test_ray_statik_egim_kapisi(self, el, kapi):
        s = SixDOFTrajectory(**_arac(launch_elevation_deg=el),
                             slosh_tanks=[_tank()])
        from hrma.analysis.six_dof_trajectory import _quat_to_dcm
        C = _quat_to_dcm(s.q0)
        z0, beyan = s._slosh.baslangic_durumu(C, s.g_surface)
        assert ('RAY_STATIK_EGIM_SINIR_DISI' in beyan) is kapi
        if kapi:
            assert np.all(z0 == 0.0)
        else:
            g_b = C.T @ np.array([0.0, 0.0, -s.g_surface])
            f_x = -g_b[0]
            p = s._slosh.parametreler(0.0, s._cg_at(0.0), f_x)[0]
            assert np.allclose(z0[:2], (sds.E.T @ g_b) / p['w1sq'], rtol=1e-14)
            assert np.all(z0[2:] == 0.0) and np.any(z0[:2] != 0.0)

    def test_kapanma_kodlari(self):
        s = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank()])
        p = s._slosh.parametreler(5.0, 2.1, -1.0)[0]
        assert not p['acik'] and 'FX_POZITIF_DEGIL' in p['kod']
        p = s._slosh.parametreler(12.0, 2.1, 30.0)[0]
        assert not p['acik'] and p['kod'] == ['YANMA_BITTI']
        p = s._slosh.parametreler(11.99, 2.1, 30.0)[0]   # doluluk < 0,005?
        assert p['acik'] or 'IZGARA_DISI' in p['kod']

    def test_zaman_alani_ciktilari(self):
        out = SixDOFTrajectory(**_arac(wind_speed=6.0),
                               slosh_tanks=[_tank()]).solve()
        N = out['time'].size
        assert out['slosh_eta'].shape == (1, 2, N)
        act = out['slosh_active'][0]
        tb = 12.0
        assert not act[out['time'] >= tb].any()
        assert np.isnan(out['slosh_eta'][0, :, ~act]).all()
        assert act[out['time'] < 11.0].all()
        p = out['slosh_params_t']
        # F = m1 (ω1² η + 2ζω1 η̇) — çıktıdaki parametrelerle yeniden kur
        j = int(np.nonzero(act)[0][len(np.nonzero(act)[0]) // 2])
        yy = out['slosh_eta'][0, :, j]
        assert np.all(np.isfinite(out['slosh_force_body'][0, :, j]))
        assert out['g_eff'][j] > 0.0
        assert out['slosh_angle_deg'][0, j] == pytest.approx(
            math.degrees(np.hypot(*yy) / p['L1_m'][0, j]))
        assert out['slosh_rigid_comparison']['apogee'] is not None
        assert np.nanmax(out['slosh_rigid_comparison']['delta_theta_deg']) > 0
