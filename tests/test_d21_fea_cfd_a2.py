# -*- coding: utf-8 -*-
"""ÖH D21 — kulvar fea-cfd, aşama 2/2 bekçileri.

Her sınıf bir defter kalemini korur. Bekçilerin ters-mutasyonla KIRMIZI
olduğu ölçüldü: docs/scofield/raw/OH/D21/fea-cfd/a2/mutasyon.json.

Ortak ilke (Berke doktrini): beyan çözüm değildir. Buradaki testler
"uyarı metni var mı" diye sormaz; RET'in gerçekten olduğunu, SAYININ
düzeldiğini ve hükmün DÖNEN alana ait olduğunu ölçer.
"""
import math

import numpy as np
import pytest

from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.separation import assess_separation as cfd_assess_separation
from hrma.cfd.steady import (MIN_MAX_ITERS, MIN_RAMP_ITERS,
                             solve_steady_axisym)
from hrma.flow.boundary_layer import solve_boundary_layer
from hrma.flow.separation import (DERIVATION_BANDS, KALT_BADAL_NPR_BAND,
                                  SCHMUCKER_MACH_SEP_BAND,
                                  SUMMERFIELD_FACTOR_ACCEPT_BAND,
                                  SUMMERFIELD_FACTOR_BAND,
                                  SUMMERFIELD_NPR_BAND, assess_separation)
from hrma.stability.chug import _neutral_omega_general, chug_neutral_delay_s


# --------------------------------------------------------------------------
# Ortak fikstürler (küçük ızgara — makine paylaşımlı, SIRALI koşum)
# --------------------------------------------------------------------------
def _kucuk_izgara(ni=41, nj=8):
    z = np.linspace(0.0, 0.30, ni)
    r = 0.05 - 0.03 * np.exp(-((z - 0.12) / 0.05) ** 2)
    return build_grid_from_wall(z, r, nj=nj)


@pytest.fixture(scope='module')
def izgara():
    return _kucuk_izgara()


_GAZ = dict(P0=2.0e6, T0=2800.0, gamma=1.2, R=320.0)


# ==========================================================================
# P6B1-06 — sürücü ayarı kapıları
# ==========================================================================
class TestP6B1_06SurucuAyariKapilari:
    """Ham istisna da sessiz kabul de fail-closed DEĞİLDİR.

    ÖLÇÜLDÜ (a2/once.json, taban 35aa279): max_iters=0/-5 ham IndexError,
    ramp_iters=0 ham ZeroDivisionError; ramp_iters=-2, tol_res=0/-1,
    cfl_start=-1, cfl_max<cfl_start SESSİZCE kabul; settle_tol<=0 ise
    çağıranın HİÇ göndermediği freeze_settle_tol alanını suçluyordu.
    """

    @pytest.mark.parametrize('kw, alan', [
        (dict(max_iters=0), 'max_iters'),
        (dict(max_iters=-5), 'max_iters'),
        (dict(max_iters=2.5), 'max_iters'),
        (dict(ramp_iters=0, max_iters=3), 'ramp_iters'),
        (dict(ramp_iters=-2, max_iters=3), 'ramp_iters'),
        (dict(tol_res=0.0, max_iters=3), 'tol_res'),
        (dict(tol_res=-1.0, max_iters=3), 'tol_res'),
        (dict(settle_tol=0.0, max_iters=3), 'settle_tol'),
        (dict(settle_tol=-1e-3, max_iters=3), 'settle_tol'),
        (dict(cfl_start=-1.0, max_iters=3), 'cfl_start'),
        (dict(cfl_max=0.0, max_iters=3), 'cfl_max'),
        (dict(cfl_start=0.9, cfl_max=0.1, max_iters=3), 'cfl_max'),
    ])
    def test_gecersiz_ayar_ADIYLA_reddedilir(self, izgara, kw, alan):
        """Ret ValueError'dır ve REDDEDİLEN ALANIN ADINI taşır."""
        with pytest.raises(ValueError) as exc:
            solve_steady_axisym(grid=izgara, **_GAZ, **kw)
        assert alan in str(exc.value), (
            f'{kw!r} reddedildi ama gerekçe {alan!r} alanını anmıyor: '
            f'{exc.value}')

    def test_settle_tol_KENDI_adiyla_suclanir(self, izgara):
        """Eski kusur: settle_tol<=0 için mesaj freeze_settle_tol diyordu.

        Çağıranın göndermediği bir alanı suçlamak yanlış teşhistir. Mesaj
        settle_tol ile BAŞLAMALIDIR (freeste ayrım cümlesi sonra gelebilir).
        """
        with pytest.raises(ValueError) as exc:
            solve_steady_axisym(grid=izgara, **_GAZ, settle_tol=0.0,
                                max_iters=3)
        assert str(exc.value).startswith('settle_tol'), str(exc.value)

    def test_saglikli_ayar_kabul_edilir(self, izgara):
        """Kapı bir GEVŞETME değil: sağlıklı koşum aynen çalışır."""
        s = solve_steady_axisym(grid=izgara, **_GAZ, max_iters=3)
        assert s['iterations'] == 3
        assert len(s['residual_history']) >= 3

    def test_alt_sinirlar_tanimin_asgarisi(self):
        """MIN_* sabitleri uydurma değil: 'en az bir iterasyon' demek."""
        assert MIN_MAX_ITERS == 1
        assert MIN_RAMP_ITERS == 1

    def test_asiri_cfl_beyanla_doner_istisna_sizmaz(self, izgara):
        """Büyüklüğe UYDURMA tavan konmadı: aşırı CFL 'diverged' beyanıdır.

        ÖLÇÜLDÜ: cfl_max=1e6 -> convergence_status='diverged' (istisna
        sızmaz). Kapı işareti/yönü denetler, büyüklüğü değil.
        """
        s = solve_steady_axisym(grid=izgara, **_GAZ, cfl_max=1.0e6,
                                max_iters=3)
        assert s['convergence_status'] == 'diverged'
        assert s['converged'] is False


# ==========================================================================
# P6B1-09 — yayımlanan son kalıntı DÖNEN alanın olmalı
# ==========================================================================
class TestP6B1_09SonKalintiDonenAlanin:
    """ÖLÇÜLDÜ (a2/once.json): tavanda biten koşuda residual_history[-1]
    bir ZAMAN ADIMI gerisinin kalıntısıydı — açık yolda %5,74 ve %1,17,
    örtük tazeleme çevriminde %6,55 sapma.
    """

    @pytest.fixture(scope='class')
    def tavan_kosumu(self):
        return solve_steady_axisym(grid=_kucuk_izgara(ni=49, nj=10),
                                   **_GAZ, max_iters=40, tol_res=1e-14)

    def test_history_sonu_donen_alanin_kalintisidir(self, tavan_kosumu):
        s = tavan_kosumu
        assert s['residual_history_last_is_returned_field'] is True
        assert float(s['residual_history'][-1]) == pytest.approx(
            float(s['final_residual_of_returned_field']), rel=0.0, abs=0.0)

    def test_canli_operatorde_sema_olcumuyle_de_ortusur(self, tavan_kosumu):
        """Operatör canlıyken şemanın ölçtüğü kalıntı AYNI alanın AYNI
        ölçüsüdür; eskiden aralarında bir zaman adımı fark vardı."""
        s = tavan_kosumu
        assert s['residual_operator'] == 'scheme_live_minmod'
        assert float(s['final_residual_of_returned_field']) == pytest.approx(
            float(s['scheme_residual_norm']), rel=1e-12)

    def test_ortuk_yolda_da_donen_alanin(self):
        s = solve_steady_axisym(grid=_kucuk_izgara(ni=41, nj=8), **_GAZ,
                                time_integrator='line_implicit_j',
                                second_order=True, max_iters=30,
                                tol_res=1e-14)
        assert s['residual_history_last_is_returned_field'] is True
        assert float(s['residual_history'][-1]) == pytest.approx(
            float(s['final_residual_of_returned_field']), rel=0.0, abs=0.0)

    def test_yakinsayan_kosuda_gecmis_UZAMAZ(self, izgara):
        """break yolunda iki sayı zaten aynıdır: mükerrer kayıt EKLENMEZ.

        ÇEVRİLDİ — ÖH D31 fea-cfd a1 (P6B1-10). Eski satır
        ``assert s['converged'] is True`` idi ve bu bekçinin ASIL iddiası
        değil, break yoluna girildiğinin VEKİLİYDİ. Fikstür toleransları
        bilerek absürttür (``tol_res=1e30``, ``settle_tol=1e30``): koşu
        2. iterasyonda "yakınsadı" sayılır, yani alan hâlâ BAŞLANGIÇ
        GEÇİCİSİNDEDİR.

        P6B1-10 kapısı bu alanda gerçek bir kusur ÖLÇTÜ: duvarın en
        negatif normal Mach'ı **−0,98527** (eşik −1/γ = −0,83333), 40
        duvar yüzünün **4'ünde** yıldız basıncı negatif, en küçüğü
        **−23.680,09 Pa** — yani duvar akışkanı itmek yerine EMİYOR.
        Kapı bu yüzden hükmü fail-closed geri çekiyor
        (``convergence_status = 'wall_star_pressure_nonpositive'``).
        Bu bir gerileme DEĞİL, kapının amacının ta kendisidir.

        Bekçi SÖKÜLMEDİ: asıl iddiası (break yolunda mükerrer kalıntı
        kaydı eklenmemesi) aynen ölçülür. Kapı break yolunu DEĞİŞTİRMEZ —
        yalnız nihai hükmü yargılar — bu yüzden defter bookkeeping'i
        sınanabilir durumda kalır.
        """
        s = solve_steady_axisym(grid=izgara, **_GAZ, max_iters=200,
                                tol_res=1e30, settle_tol=1e30,
                                settle_window=2)
        # Break yoluna GİRİLDİ: tavan 200 iken koşu çok önce durdu.
        assert s['iterations'] < 200, s['iterations']
        # Yakınsama break'i U güncellenmeden ÖNCEdir -> aynı sayı, tek kayıt.
        assert len(s['residual_history']) == s['iterations']
        # P6B1-10 KAPATILDI (ÖH D37 A3a cfd-kok-a F-05; Berke Sunum 3a onayı
        # 24 Eyl): işletilen duvar yıldız basıncı artık iki-genişleme (TRRS)
        # — vakuma kadar pozitif. Aynı alanda AKUSTİK biçim hâlâ negatife
        # düşer (kusurun yeri kıyas sütununda ölçülür), işletilen biçim
        # düşmez → kapı ateşlemez, break hükmü düşmez.
        ws = s['wall_star_pressure']
        assert ws['operator'] == 'trrs', ws
        assert ws['akustik_negatif_yuz_sayisi'] > 0, ws   # D21 ölçümünün yeri
        assert ws['min_M_n'] < ws['esik_M_n_akustik'], ws  # < −1/γ
        assert ws['min_M_n'] > ws['esik_M_n'], ws          # vakum sınırının içinde
        assert ws['pozitif_mi'] is True, ws
        assert ws['negatif_p_star_yuz_sayisi'] == 0, ws
        assert s['convergence_status'] != 'wall_star_pressure_nonpositive'


# ==========================================================================
# P6B3-02 — march.completed_fraction
# ==========================================================================
def _bl_vaka():
    x = np.linspace(0.0, 0.40, 41)
    r = 0.05 - 0.03 * np.exp(-((x - 0.12) / 0.06) ** 2)
    mach = np.linspace(0.15, 3.2, x.size)
    p = 2.0e6 * (1.0 + 0.1 * mach ** 2) ** (-6.0)
    T = 2800.0 / (1.0 + 0.1 * mach ** 2)
    return dict(x_m=x, radius_m=r, mach=mach, pressure_Pa=p,
                temperature_K=T, gamma=1.2, gas_constant_J_kgK=320.0,
                prandtl=0.72,
                viscosity_fn=lambda t: 1.716e-5 * (t / 273.15) ** 0.666,
                wall_temperature_K=800.0)


class TestP6B3_02KapsamaOrani:
    """ÖLÇÜLDÜ (a2/once.json): çağıran marşı %30/%50/%75'te durdurduğunda
    completed_fraction ÜÇÜNDE DE tam 1,0000 yayımlanıyordu — payda
    stop_x_m ile birlikte küçülüyordu.
    """

    @pytest.mark.parametrize('frak', [0.30, 0.50, 0.75])
    def test_kesilen_marsta_oran_GERCEK_kapsamadir(self, frak):
        kw = _bl_vaka()
        x = kw['x_m']
        stop = float(x[0] + frak * (x[-1] - x[0]))
        s = solve_boundary_layer(**kw, stop_x_m=stop,
                                 stop_reason='bekçi: çağıran durdurdu')
        m = s['march']
        assert m['status'] == 'stopped_by_caller'
        assert m['completed_fraction'] == pytest.approx(frak, rel=1e-9)
        assert m['completed_fraction'] < 1.0
        # Kesilmiş ızgaranın KENDİ oranı AYRI alandadır ve kaybolmadı.
        assert m['completed_fraction_of_march_grid'] == pytest.approx(
            1.0, rel=1e-9)
        assert m['march_grid_truncated'] is True

    def test_tam_marsta_bir_kalir(self):
        s = solve_boundary_layer(**_bl_vaka())
        m = s['march']
        assert m['completed_fraction'] == pytest.approx(1.0, rel=1e-9)
        assert m['march_grid_truncated'] is False

    def test_oranin_dayanagi_yayimlanir(self):
        m = solve_boundary_layer(**_bl_vaka())['march']
        assert 'marched_to_x_m' in m['completed_fraction_basis']


# ==========================================================================
# P6B3-03 — CFD ayrılma köprüsünde k bandı beyanı + gerçek sürüklenme kapısı
# ==========================================================================
def _cfd_duvar_sonucu():
    ni = 60
    z = np.linspace(0.0, 0.30, ni)
    r = 0.05 - 0.03 * np.exp(-((z - 0.10) / 0.05) ** 2)
    i_t = int(np.argmin(r))
    p = 2.0e6 * np.exp(-6.0 * np.maximum(z - z[i_t], 0.0) / 0.20)
    return {
        'wall_pressure_Pa': p,
        'wall_pressure_z_m': z,
        'converged': True,
        'convergence_basis': 'bekçi fikstürü',
        'throat': {'i': i_t, 'interior': True,
                   'interior_basis': 'bekçi fikstürü'},
    }


class TestP6B3_03KBandiBeyani:
    """ÖLÇÜLDÜ (a2/once.json): k = 0,50 ve 0,60 (literatür bandının 1,25 ve
    1,5 katı) eşiği 50.000/60.000 Pa'ya taşıyıp ayrılan istasyonu 46 -> 45/43
    çekerken validity_warning None kalıyordu; kardeş hrma.flow.separation
    AYNI k'da uyarı veriyordu.
    """

    @pytest.mark.parametrize('k', [0.45, 0.50, 0.60])
    def test_bant_disi_k_BEYAN_edilir(self, k):
        s = cfd_assess_separation(_cfd_duvar_sonucu(), 1.0e5,
                                  separation_factor=k)
        assert s['outside_validity_band'] is True
        assert s['criteria']['summerfield']['outside_validity_band'] is True
        assert f'{k:.2f}' in s['validity_warning']

    @pytest.mark.parametrize('k', [0.35, 0.375, 0.40])
    def test_bant_ici_k_uyarisiz(self, k):
        s = cfd_assess_separation(_cfd_duvar_sonucu(), 1.0e5,
                                  separation_factor=k)
        assert s['outside_validity_band'] is False
        assert s['validity_warning'] is None

    def test_kardes_modulle_AYNI_hukum(self):
        """Aynı k'da iki modül aynı yönde hüküm verir (ayrışma kusurdu)."""
        for k in (0.35, 0.60):
            cfd = cfd_assess_separation(_cfd_duvar_sonucu(), 1.0e5,
                                        separation_factor=k)
            akis = assess_separation(2.0e6, 1.0e5, 1.2, area_ratio_exit=8.0,
                                     summerfield_factor=k)
            disinda = not (SUMMERFIELD_FACTOR_BAND[0] <= k
                           <= SUMMERFIELD_FACTOR_BAND[1])
            assert cfd['outside_validity_band'] is disinda
            assert bool(
                'literatür bandının' in
                (akis['criteria']['summerfield']['validity_warning'] or '')
            ) is disinda

    def test_kabul_bandi_TEK_kaynak(self):
        """Sürüklenme kapısının GERÇEK ölçtüğü şey: iki modüldeki bant ikizi.

        Eski 'kapı' summerfield_pressure_ratio(k) == k totolojisiydi
        (ölçüldü: 800 değerde 0 ateşleme). Yenisi ithal anında patlar.
        """
        from hrma.analysis.nozzle_flow_1d import (SEPARATION_FACTOR_MAX,
                                                  SEPARATION_FACTOR_MIN)
        assert (float(SEPARATION_FACTOR_MIN),
                float(SEPARATION_FACTOR_MAX)) == tuple(
                    float(v) for v in SUMMERFIELD_FACTOR_ACCEPT_BAND)

    def test_kabul_bandi_disi_hala_REDDEDILIR(self):
        with pytest.raises(ValueError):
            cfd_assess_separation(_cfd_duvar_sonucu(), 1.0e5,
                                  separation_factor=0.75)


# ==========================================================================
# P6B3-04 — türetim bantları hükme bağlı
# ==========================================================================
class TestP6B3_04TuretimBandi:
    """ÖLÇÜLDÜ (a2/once.json): NPR = 5'te (Kalt-Badal bandı 10-1000,
    Summerfield bandı 15-20) ÜÇ ölçüt de outside_validity_band=False
    yayımlıyordu; bantlar yalnız düz metinde duruyordu.
    """

    def test_bantlar_metinle_AYNI_kaynaktan(self):
        from hrma.flow import separation as sep
        assert f'{SUMMERFIELD_NPR_BAND[0]:g}-{SUMMERFIELD_NPR_BAND[1]:g}' \
            in sep._VALIDITY['summerfield']
        assert (f'{KALT_BADAL_NPR_BAND[0]:g}-{KALT_BADAL_NPR_BAND[1]:g}'
                in sep._VALIDITY['kalt_badal'])
        assert (f'{SCHMUCKER_MACH_SEP_BAND[0]:g}-'
                f'{SCHMUCKER_MACH_SEP_BAND[1]:g}'
                in sep._VALIDITY['schmucker'])

    @pytest.mark.parametrize('npr, ad', [
        (5.0, 'summerfield'), (5.0, 'kalt_badal'),
        (8.0, 'summerfield'), (8.0, 'kalt_badal'),
        (40.0, 'summerfield'), (1500.0, 'kalt_badal'),
    ])
    def test_bant_disi_NPR_DISKESTIRIM_der(self, npr, ad):
        s = assess_separation(npr * 1.0e5, 1.0e5, 1.2, area_ratio_exit=8.0)
        c = s['criteria'][ad]
        assert c['outside_validity_band'] is True
        assert 'DIŞKESTİRİM' in c['validity_warning']

    @pytest.mark.parametrize('npr, ad', [
        (18.0, 'summerfield'), (40.0, 'kalt_badal'), (18.0, 'kalt_badal'),
    ])
    def test_bant_ici_NPR_uyarisiz(self, npr, ad):
        c = assess_separation(npr * 1.0e5, 1.0e5, 1.2,
                              area_ratio_exit=8.0)['criteria'][ad]
        assert c['outside_validity_band'] is False
        assert c['validity_warning'] is None

    def test_schmucker_bandi_MACH_uzerinde_ve_ayrilma_yoksa_hukum_yok(self):
        """Battaniye uyarı YOK: Schmucker'ın bandı M_sep üstündedir ve
        ayrılma öngörülmediyse o büyüklük TANIMSIZDIR."""
        c = assess_separation(5.0e5, 1.0e5, 1.2,
                              area_ratio_exit=8.0)['criteria']['schmucker']
        assert c['separated'] is True
        assert SCHMUCKER_MACH_SEP_BAND[0] <= c['mach_sep'] \
            <= SCHMUCKER_MACH_SEP_BAND[1]
        assert c['outside_validity_band'] is False

    def test_bant_makine_okur_yayimlanir(self):
        s = assess_separation(5.0e5, 1.0e5, 1.2, area_ratio_exit=8.0)
        for ad, (buyukluk, bant) in DERIVATION_BANDS.items():
            d = s['criteria'][ad]['derivation_band']
            assert d['quantity'] == buyukluk
            assert (d['low'], d['high']) == (float(bant[0]), float(bant[1]))


# ==========================================================================
# P6B4-06 — bikuadratik kök iptalden ölmesin
# ==========================================================================
def _omega_referans(j, tau_c, tau_f):
    """Bağımsız referans: kesin artan sol tarafın ikiye bölme kökü."""
    hedef = 1.0 / (2.0 * j)

    def f(w):
        return (math.sqrt(1.0 + (w * tau_c) ** 2)
                * math.sqrt(1.0 + (w * tau_f) ** 2) - hedef)

    lo, hi = 0.0, 1.0
    while f(hi) < 0.0:
        hi *= 2.0
    for _ in range(400):
        mid = 0.5 * (lo + hi)
        if f(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


class TestP6B4_06BikuadratikKok:
    """ÖLÇÜLDÜ (a2/once_p6b4_06.json; J=0,30, τ_c=2 ms): ω bağıl hatası
    τ_f=1e4'te 2,290e-04, 1e5'te 3,110e-02, τ_f>=1e6'da pay TAM 0,0 ->
    ω=0 -> chug_neutral_delay_s'te ham ZeroDivisionError (3/9 vaka).
    """

    @pytest.mark.parametrize('tau_f', [1e-3, 1.0, 1e2, 1e4, 1e5, 1e6, 1e7,
                                       1e9])
    def test_kok_makine_hassasiyetinde(self, tau_f):
        j, tau_c = 0.30, 2.0e-3
        w = _neutral_omega_general(j, tau_c, tau_f)
        assert w > 0.0, 'ω iptalden sıfıra çöktü'
        assert w == pytest.approx(_omega_referans(j, tau_c, tau_f),
                                  rel=1e-12)

    @pytest.mark.parametrize('tau_f', [1e6, 1e7, 1e9])
    def test_buyuk_ataletde_cokme_yok(self, tau_f):
        """Eski hâl: ZeroDivisionError (uçta HTTP 500)."""
        tau = chug_neutral_delay_s(0.30, 2.0e-3, tau_f)
        assert math.isfinite(tau) and tau > 0.0

    def test_ataletsiz_hal_kapali_formla_ozdes(self):
        """b == 0 dalı DEĞİŞMEDİ: bit-özdeşlik korundu."""
        j, tau_c = 0.30, 2.0e-3
        beklenen = math.sqrt((1.0 / (4 * j * j) - 1.0) / (tau_c * tau_c))
        assert _neutral_omega_general(j, tau_c, 0.0) == beklenen
