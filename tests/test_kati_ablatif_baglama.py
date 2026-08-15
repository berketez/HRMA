"""Katı motor ablatif kapak astarı bağlaması — mutasyon denetimli bekçiler.

v2.6.27 blokaj denetimi (B6-4) kapak astarını yeni fiziğe geçirdi:

  * Sabit üfleme blokajı 0.5 KALDIRILDI — yanlış rejimin katsayısıydı
    (psi=0.5 ⇒ B'≈1.6-2.5 atmosferik giriş; roket noktalarında B'≈0.02-0.25
    ⇒ psi 0.90-1.0). Blokaj artık B' üzerinden ÖZ-TUTARLI çözülür
    (Aerotherm/CMA: psi = 2λB'/(exp(2λB')−1), λ=0.4).
  * no_net_heating rejimi kalınlık YAYIMLAMAZ: 0.0 mm bir tasarım değildir,
    astarı kasa/bond hattı iletim sınırı belirler ve modül onu modellemiyor.
  * İki kapak ayrı istasyondur: ön kapak hazne Bartz katsayısı + EPDM
    (SP-8093 kubbe pratiği), lüle girişi boğaz katsayısı + silika-fenolik
    (SP-8115); parçacıklı akış beyanı X_p tablosundan gelir.

Bekçiler APCP noktasında kuruludur çünkü 'sized' yol orada yaşar (KNDX'te
her iki kapak no_net_heating'e düşer — o sözleşme de burada ayrıca kilitli).
Bekçilerin TAUTOLOJİ olmadığı mutasyon testiyle KANITLANIR: çözücü eski
kusura (sabit psi=0.5) geri döndürüldüğünde ön kapak bekçisi KIRILMALIDIR.
"""

import pytest

import hrma.analysis.thermal_protection as tp_mod
from hrma.analysis.thermal_protection import (
    RECESSION_VALID_MAX_MM_S,
    STEFAN_BOLTZMANN,
)
from hrma.engines.solid_rocket_engine import (
    SOLID_CONDENSED_MASS_FRACTION,
    SolidRocketEngine,
)


@pytest.fixture(scope='module')
def apcp_motor():
    """Görev tanımındaki APCP çalışma noktası (sized yol burada yaşıyor)."""
    motor = SolidRocketEngine(chamber_diameter=75, grain_length=360,
                              core_diameter=32, chamber_pressure=40,
                              grain_type='bates', propellant_type='apcp')
    motor.calculate_performance()
    return motor


@pytest.fixture(scope='module')
def apcp_yalitim(apcp_motor):
    return apcp_motor._design_insulation_system()


@pytest.fixture(scope='module')
def kndx_yalitim():
    motor = SolidRocketEngine(chamber_diameter=75, grain_length=360,
                              core_diameter=32, chamber_pressure=40,
                              grain_type='bates', propellant_type='kndx')
    motor.calculate_performance()
    return motor._design_insulation_system()


def _on_kapak_bekcisi(blok):
    """Ön kapak 'sized + çözülmüş blokaj' iddiası — TEK tanım noktası.

    Hem sağlıklı koşunun bekçisi hem mutasyon testinin kurbanı budur:
    çözücü eski kusura döndürülürse bu iddialar KIRILMALIDIR (aşağıdaki
    mutasyon testi bunu kanıtlar; bekçi tautoloji değildir).

    Sayılar bu depoda ÖLÇÜLDÜ (2026-08-15, APCP 75/32/360 @ 40 bar):
    t = 0.694 mm, psi = 0.948, B' = 0.132, sdot = 0.156 mm/s.
    """
    assert blok['thickness_status'] == 'sized'
    assert blok['recession_regime'] == 'steady_ablation'
    assert blok['thickness'] is not None
    assert blok['thickness'] == pytest.approx(0.6942, rel=0.05)
    # Blokaj ÇÖZÜLMÜŞ olmalı: 0 < psi < 1 ve B' > 0. Sabit 0.5 bu noktada
    # q_net'in işaretini ters çevirirdi (aşağıdaki mutasyon testi).
    assert 0.0 < blok['blowing_blockage'] < 1.0
    assert blok['blowing_blockage'] == pytest.approx(0.9482, abs=0.02)
    assert blok['b_prime'] > 0.0
    assert blok['b_prime'] == pytest.approx(0.1318, rel=0.10)
    assert 'SOLVED' in blok['blockage_basis']
    assert blok['recession_rate_mm_s'] == pytest.approx(0.1558, rel=0.05)
    assert blok['recession_rate_mm_s'] <= RECESSION_VALID_MAX_MM_S
    # Malzeme beyan edilmiş tasarım seçimi: EPDM ailesi (SP-8093 kubbe).
    assert 'EPDM' in blok['material']


def test_apcp_on_kapak_boyutlanmis_ve_blokaj_cozulmus(apcp_yalitim):
    """APCP ön kapak: sized + psi çözülmüş + EPDM ailesi."""
    _on_kapak_bekcisi(apcp_yalitim['forward_insulation'])


def test_apcp_arka_kapak_zarf_disi_ve_parcacik_beyani(apcp_yalitim):
    """APCP lüle girişi: zarf-dışı hız → NOT_MODELLED + parçacık beyanı.

    Ölçülen (2026-08-15): sdot = 1.561 mm/s > 0.35 mm/s tavanı — Seviye-1
    yarı-kararlı Q* modeli bu istasyonu boyutlayamaz; sayı uydurulmaz.
    APCP'nin yoğuşmuş faz kesri (X_p ≈ 0.34, iki-fazlı kayıp tablosundan)
    sıfırdan büyük olduğu için parçacık erozyonunun MODELLENMEDİĞİ beyanı
    zorunludur.
    """
    blok = apcp_yalitim['aft_insulation']
    assert blok['thickness_status'] == 'NOT_MODELLED'
    assert blok['thickness'] is None
    # Gerekçenin kanıtı yayımlanmaya devam eder: hız tavan üstünde.
    assert blok['recession_rate_mm_s'] > RECESSION_VALID_MAX_MM_S
    assert blok['recession_rate_mm_s'] == pytest.approx(1.561, rel=0.05)
    note = blok['validity_note']
    assert note and 'MODEL OUT OF ENVELOPE' in note
    # Parçacık beyanı X_p TABLOSUNDAN gelir (yakıt adından değil).
    x_p = SOLID_CONDENSED_MASS_FRACTION['apcp']
    assert x_p > 0
    assert 'PARTICLE-LADEN' in blok['basis']
    assert f'{x_p:.2f}' in blok['basis'], (
        'beyandaki X_p, iki-fazlı kayıp tablosunun değeri olmalı')
    # İstasyon malzemesi lüle girişi fenoliği (SP-8115 sınıfı).
    assert 'Silica-phenolic' in blok['material']


def test_mutasyon_sabit_blokaj_bekciyi_kirar(apcp_motor, apcp_yalitim,
                                             monkeypatch):
    """MUTASYON DENETİMİ: eski kusur (sabit psi=0.5) geri gelirse bekçi kırılır.

    Bekçinin tautoloji olmadığının kanıtı. Çözücü, v2.6.27 öncesi kusuru
    taklit edecek şekilde yamalanır: psi SABİT 0.5, B' çözülmez. Bu noktada
    (APCP ön kapak: h_g≈1632 W/m2K, T_aw≈3615 K, T_s=2300 K, eps=0.85)
    q_net'in İŞARETİ değişir:

        psi=1 çözümü : q_net > 0  → sized, t ≈ 0.694 mm
        psi=0.5      : 0.5·h·ΔT ≈ 1.07 MW/m² < eps·σ·T_s⁴ ≈ 1.35 MW/m²
                       → q_net < 0 → 'no_net_heating' → kalınlık YOK

    Yani kusur geri gelirse ön kapak bekçisi ('sized', 0<psi<1, t≈0.694)
    AssertionError ile düşer — bu test tam da onu talep eder.
    """
    # Önce sağlıklı hâl: bekçi geçiyor olmalı (aksi hâlde mutasyonun
    # kırdığı şey bekçi değil, zaten bozuk bir koşudur).
    _on_kapak_bekcisi(apcp_yalitim['forward_insulation'])

    def sabit_blokaj_mutanti(h_gas_W_m2K, T_recovery_K, T_surface_K,
                             emissivity, rho_qstar, density_kg_m3,
                             gas_cp_J_kgK, gas_fraction,
                             lam=tp_mod.BLOWING_LAMBDA):
        """v2.6.27 öncesi kusur: psi sabit 0.5, öz-tutarlı çözüm yok."""
        psi = 0.5
        q_unblown = float(h_gas_W_m2K) * (float(T_recovery_K)
                                          - float(T_surface_K))
        q_rerad = float(emissivity) * STEFAN_BOLTZMANN \
            * float(T_surface_K) ** 4
        q_net = psi * q_unblown - q_rerad
        return {
            'recession_rate_m_s': max(q_net, 0.0) / rho_qstar,
            'blowing_blockage': psi,
            'b_prime': 1.6,   # sabit 0.5'in ima ettiği rejimin B' mertebesi
            'q_conv_blocked_W_m2': psi * q_unblown,
            'q_reradiated_W_m2': q_rerad,
            'q_net_W_m2': q_net,
            'blockage_basis': 'MUTANT: fixed psi=0.5 (pre-v2.6.27 defect)',
            'iterations': 0,
        }

    monkeypatch.setattr(tp_mod, '_solve_blown_surface_balance',
                        sabit_blokaj_mutanti)
    mutant_yalitim = apcp_motor._design_insulation_system()
    mutant_fwd = mutant_yalitim['forward_insulation']

    # Kusurun ölçülen ayak izi: işaret dönmesi → no_net_heating → t=None.
    assert mutant_fwd['recession_regime'] == 'no_net_heating'
    assert mutant_fwd['thickness'] is None
    assert mutant_fwd['thickness_status'] == 'NOT_MODELLED'

    # ... ve bekçi bu çıktıyı KABUL ETMEZ.
    with pytest.raises(AssertionError):
        _on_kapak_bekcisi(mutant_fwd)


def test_kndx_no_net_kalinlik_yok_gerekce_var(kndx_yalitim):
    """KNDX: her iki kapak no_net_heating — sayı yok, gerekçe var.

    Eski sözleşme bu rejimde 0.0 mm + 'sized' basıyordu (sessiz tehlike).
    Yeni sözleşme: t=None + NOT_MODELLED; gerileme payının sıfır olduğu
    bilgisi total_recession_mm=0 alanında durur; gerekçe kasa/bond hattı
    iletim sınırına işaret eder (modülün BOYUTLAMADIĞI şeyin adı).
    """
    for istasyon in ('forward_insulation', 'aft_insulation'):
        blok = kndx_yalitim[istasyon]
        assert blok['thickness'] is None, istasyon
        assert blok['thickness_status'] == 'NOT_MODELLED', istasyon
        assert blok['recession_regime'] == 'no_net_heating', istasyon
        assert blok['total_recession_mm'] == pytest.approx(0.0), istasyon
        # Üfleme yoksa blokaj da yoktur: psi=1 limiti.
        assert blok['blowing_blockage'] == pytest.approx(1.0), istasyon
        assert blok['b_prime'] == pytest.approx(0.0), istasyon
        note = blok['validity_note']
        assert note and 'NO NET HEATING' in note, istasyon
        assert 'case/bond-line' in note, (
            f'{istasyon}: gerekçe kasa/bond hattı iletim sınırını anmalı')


def test_kndx_istasyonlari_ayri_malzeme_ayri_katsayi(kndx_yalitim):
    """no_net rejiminde bile istasyon kimlikleri ayrışık kalmalı."""
    fwd = kndx_yalitim['forward_insulation']
    aft = kndx_yalitim['aft_insulation']
    assert 'EPDM' in fwd['material']
    assert 'Silica-phenolic' in aft['material']
    assert aft['h_gas_W_m2K'] > fwd['h_gas_W_m2K'], (
        'boğaz Bartz katsayısı hazne katsayısından büyük olmalı')
