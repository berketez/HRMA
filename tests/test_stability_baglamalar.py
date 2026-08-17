"""F2b-1 bekçileri: hibrit ve katı motorların YANMA KARARLILIĞI bağlamaları.

Çekirdeğin (``hrma/stability/``) kendi 233 bekçisi fiziği kilitler; bu dosya
BAĞLAMAYI kilitler — yani "motor gerçekten o çekirdeği mi çağırıyor, kendi
büyüklükleriyle mi, ve hükmü olduğu gibi mi taşıyor?" sorusunu. İkisi ayrı
kusur sınıfıdır ve biri diğerini yakalamaz:

* Çekirdek yeşil, bağlama kırık: motor doğru fiziği YANLIŞ girdiyle çağırır
  (yanlış anda alınan akı, bar yerine Pa, korelasyonun kalibre sabiti yerine
  çözücünün R·T'si). Sayı üretilir ve inandırıcı görünür.
* Bağlama yeşil, çekirdek kırık: motorun suçu yoktur ama sayı yanlıştır.

Bu yüzden buradaki her sayısal iddia ya (a) çekirdeğin DOĞRUDAN çağrısıyla
BİT-AYNI karşılaştırılır, ya da (b) kapalı formdan bağımsız türetilen bir
ÖZDEŞLİKLE sınanır. Motorun yayımladığı sayıyı yine motorun yayımladığı
sayıyla karşılaştıran totoloji YOKTUR.

ÖLÇÜLEN DEĞERLER (bu depo, 2026-08-17; bekçilerin çapası):
  hibrit 5 kN / 20 bar / O-F 2,5 / N₂O-HTPB:
      LFI f = 13,00 Hz · τ_bl2 = 36,9 ms · R·T üçlüsü 4,47e5 / 7,55e5 / 1,689
      1L = 138,03 Hz (ayrışma 1,03 dekad) · α_lüle = −18,17 1/s
      R_crit(1L) = 6,56 (literatür bandı 1-3'ün ÜSTÜNDE — hibritte yanan
      yüzeyden yalnız yakıt girdiği için)
  katı BATES 100/30/500 mm, 40 bar, APCP:
      τ_c = 0,940 ms · L* = 0,631 m · bulk mod n = 0,35 → 'stable'
      α_lüle = −1169,6 1/s · R_crit = 1,83431 = (γ+1)/γ (analitik kilit)
"""

import hashlib
import math
import pathlib

import pytest

from hrma.stability import (
    QSHODBand,
    assess_hybrid_lfi,
    bulk_mode_zero_lag,
    forbid_verdict_key,
    tau_c_from_volume,
)
from hrma.stability.hybrid_lfi import RT_AV_M2_S2


# ---------------------------------------------------------------------------
# Motorlar — GERÇEK koşumlar (modül kapsamında bir kez)
#
# Katı taban TEK KAYNAKTAN gelir: ``tests/test_faz4_motor_kapilari.KATI_TABAN``
# (ölçülmüş yakınsayan APCP tanesi, app.py /calculate_solid varsayılanlarıyla
# aynı). İkinci bir kopya tanımlamak, o dosya güncellenince bu bekçilerin
# sessizce başka bir motoru ölçmesi demektir.
# ---------------------------------------------------------------------------
from tests.test_faz4_motor_kapilari import KATI_TABAN     # noqa: E402


@pytest.fixture(scope='module')
def hibrit():
    """Gerçek hibrit koşumu (motor nesnesi + tam sonuç)."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=5000, burn_time=10, of_ratio=2.5,
                               chamber_pressure=20, fuel_type='htpb',
                               oxidizer_type='n2o')
    return motor, motor.calculate()


@pytest.fixture(scope='module')
def kati():
    """Gerçek katı koşumu (motor nesnesi + tam sonuç)."""
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    motor = SolidRocketEngine(**KATI_TABAN)
    sonuc = motor.calculate_performance()
    assert not sonuc.get('error'), sonuc.get('error')
    return motor, sonuc


def _sayi_yollari(dugum, yol=''):
    """Ağaçtaki TÜM sayısal yaprakların yolu (bool hariç).

    "Girdi yoksa sayı da yok" iddiasını ölçmenin tek dürüst yolu: alan
    listelemek değil, ağacı TARAMAK.
    """
    bulunan = []
    if isinstance(dugum, dict):
        for ad, deger in dugum.items():
            bulunan += _sayi_yollari(deger, f'{yol}.{ad}')
    elif isinstance(dugum, (list, tuple)):
        for i, deger in enumerate(dugum):
            bulunan += _sayi_yollari(deger, f'{yol}[{i}]')
    elif isinstance(dugum, (int, float)) and not isinstance(dugum, bool):
        bulunan.append(yol)
    return bulunan


def _anahtar_var_mi(dugum, aranan):
    """Ağaçta (iç içe dahil) bu adda bir anahtar var mı?"""
    if isinstance(dugum, dict):
        if aranan in dugum:
            return True
        return any(_anahtar_var_mi(v, aranan) for v in dugum.values())
    if isinstance(dugum, (list, tuple)):
        return any(_anahtar_var_mi(v, aranan) for v in dugum)
    return False


# ===========================================================================
# HİBRİT — LFI (hüküm veren yol)
# ===========================================================================
def test_hibrit_kararlilik_blogu_yayimlaniyor(hibrit):
    """Blok var, iki ayağı da çözülmüş ve her ayağın künyesi dolu."""
    _, sonuc = hibrit
    blok = sonuc['combustion_stability']
    assert blok['model'] == 'hrma.stability F2b hybrid binding'
    assert blok['_basis'].strip()
    assert blok['operating_point'] == 'design_instant_t0'
    assert blok['lfi']['status'] == 'modelled'
    assert blok['acoustic_response_threshold']['status'] == 'modelled'
    # Kapsam beyanları çekirdekten taşındı (sessiz yok sayma yasak)
    for ad in ('vortex_shedding', 'pogo', 'three_dimensional_acoustics',
               'injection_coupled_hf', 'damping_devices',
               'detailed_flame_dynamics'):
        assert blok['not_modelled'][ad].strip()


def test_hibrit_lfi_cekirdegin_DOGRUDAN_cagrisiyla_bit_ayni(hibrit):
    """Motorun yayımladığı frekans, çekirdeğin kendi sonucunun TA KENDİSİ.

    Girdiler motorun YAYIMLADIĞI alanlardan okunur (motor bloğundan değil):
    yani bu bekçi hem matematiğin bozulmadığını hem de doğru alanların
    okunduğunu ölçer. Motor kendi çıktısını kendi çıktısıyla doğrulamaz.
    """
    motor, sonuc = hibrit
    lfi = sonuc['combustion_stability']['lfi']
    f_1l = None
    for mod in sonuc['acoustic_modes']['modes']:
        if mod['indices'] == {'tangential_m': 0, 'radial_n': 0,
                              'longitudinal_q': 1}:
            f_1l = float(mod['frequency_hz'])
            break
    assert f_1l is not None, '1L modu tabloda yok — çapraz kurulamıyor'
    r_ozgul = 8314.462618 / float(sonuc['molecular_weight'])
    beklenen = assess_hybrid_lfi(
        oxidizer_type=motor.oxidizer_type,
        grain_length_m=float(sonuc['grain_length']),
        chamber_pressure_Pa=float(sonuc['chamber_pressure']) * 1e5,
        oxidizer_flux_kg_m2_s=float(sonuc['g_ox_initial']),
        of_ratio=float(sonuc['of_ratio_initial']),
        rt_thermo_m2_s2=r_ozgul * float(sonuc['chamber_temperature']),
        acoustic_first_longitudinal_hz=f_1l)
    for alan in ('frequency_hz', 'boundary_layer_delay_s', 'rt_corr_m2_s2',
                 'rt_thermo_m2_s2', 'rt_ratio', 'flux_group_kg_m2_s',
                 'coefficient', 'delay_constant_c_prime'):
        assert lfi[alan] == beklenen[alan], (
            f'{alan}: motor {lfi[alan]!r}, çekirdek {beklenen[alan]!r} — '
            f'bağlama çekirdeği olduğu gibi çağırmıyor')
    assert (lfi['acoustic_separation']['separation_decades']
            == beklenen['acoustic_separation']['separation_decades'])
    # Frekans SABİT DEĞİL: gerçekten türetiliyor (uydurma sabit sınıfı)
    assert 1.0 < lfi['frequency_hz'] < 100.0, lfi['frequency_hz']


def test_hibrit_lfi_hukmu_cekirdekten_OLDUGU_GIBI_tasiniyor(hibrit):
    """Motor katmanı yeniden hükümleştirmez; kapsam etiketi de düşmez."""
    motor, sonuc = hibrit
    lfi = sonuc['combustion_stability']['lfi']
    beklenen = assess_hybrid_lfi(
        oxidizer_type=motor.oxidizer_type,
        grain_length_m=float(sonuc['grain_length']),
        chamber_pressure_Pa=float(sonuc['chamber_pressure']) * 1e5,
        oxidizer_flux_kg_m2_s=float(sonuc['g_ox_initial']),
        of_ratio=float(sonuc['of_ratio_initial']))
    assert lfi['verdict'] == beklenen['verdict'] == 'marginal'
    assert lfi['verdict_scope'] == beklenen['verdict_scope']
    assert lfi['verdict_basis'] == beklenen['verdict_basis']
    # ÇIPLAK HÜKÜM YASAĞI: kapsam ve gerekçe boş olamaz
    assert 'amplitude NOT modelled' in lfi['verdict_scope']
    assert lfi['verdict_basis'].strip()


def test_hibrit_lfi_kalibre_sabiti_IKAME_EDILMEDI(hibrit):
    """R·T üçlüsü: kalibre sabit korelasyonda, çözücünün R·T'si TANIDA.

    Tasarım kararı 2. Bu bekçi mutasyon hedefidir: korelasyona rt_thermo
    konursa frekans ~1,7 kat kayar ve hem burası hem bit-aynılık bekçisi
    kırmızıya döner.
    """
    _, sonuc = hibrit
    lfi = sonuc['combustion_stability']['lfi']
    assert lfi['rt_gate'] == 'n2o'
    assert lfi['rt_corr_m2_s2'] == RT_AV_M2_S2['n2o']
    assert lfi['rt_thermo_m2_s2'] != lfi['rt_corr_m2_s2'], (
        'tanı değeri kalibre sabitle aynı çıktı — biri diğerinin yerine '
        'konmuş olabilir')
    assert lfi['rt_ratio'] == pytest.approx(
        lfi['rt_thermo_m2_s2'] / lfi['rt_corr_m2_s2'], rel=1e-12)
    assert 'diagnostic only' in lfi['rt_ratio_label']
    # Frekans KALİBRE sabitle kurulmuş olmalı: Denk. 15'i elle kur
    beklenen_f = (0.2341 * (2.0 + 1.0 / float(sonuc['of_ratio_initial']))
                  * float(sonuc['g_ox_initial']) * RT_AV_M2_S2['n2o']
                  / (float(sonuc['grain_length'])
                     * float(sonuc['chamber_pressure']) * 1e5))
    assert lfi['frequency_hz'] == pytest.approx(beklenen_f, rel=1e-12)
    # Reddedilen ders notu katsayısı adıyla beyanlı, KULLANILMIYOR
    assert '0.119' in lfi['coefficient_identity']
    assert 'NOT used' in lfi['coefficient_identity']


def test_hibrit_desteklenmeyen_oksitleyicide_frekans_uydurulmuyor(hibrit):
    """Kalibre sabiti olmayan oksitleyicide sayı YOK, gerekçe VAR."""
    motor, sonuc = hibrit
    eski = motor.oxidizer_type
    try:
        motor.oxidizer_type = 'h2o2'
        blok = motor._hybrid_lfi_block(sonuc)
    finally:
        motor.oxidizer_type = eski
    assert blok['status'] == 'NOT_EVALUATED'
    assert "'h2o2'" in blok['missing_inputs'][0]
    assert not _sayi_yollari(blok), (
        f'reddedilen oksitleyicide sayı yayımlandı: {_sayi_yollari(blok)}')


def test_hibrit_girdi_yoksa_iki_ayak_da_sayi_uydurmuyor(hibrit):
    """Boş sonuç sözlüğü: eksik girdiler ADIYLA, sayı sıfır."""
    motor, _ = hibrit
    lfi = motor._hybrid_lfi_block({})
    esik = motor._acoustic_response_threshold_block({})
    assert lfi['status'] == 'NOT_EVALUATED'
    assert set(lfi['missing_inputs']) >= {'grain_length', 'g_ox_initial',
                                          'chamber_pressure',
                                          'of_ratio_initial'}
    assert not _sayi_yollari(lfi)
    assert esik['status'] == 'NOT_MODELLED'
    assert 'acoustic_modes' in esik['missing_inputs'][0]
    assert not _sayi_yollari(esik)


def test_hibrit_a10_beyani_daraldi_ve_yalan_degil(hibrit):
    """Modellenen şeyi 'modellenmiyor' ilan etmek de yalandır.

    LFI artık KONUMLANIYOR; beyanın kalan gerçek yokluğu tepki
    fonksiyonudur ve beyan bunu söylemek zorundadır.
    """
    _, sonuc = hibrit
    beyan = sonuc['not_modelled']['hybrid_boundary_layer_instability']
    assert beyan.startswith('NOT_MODELLED')
    assert 'RESPONSE FUNCTION' in beyan
    assert 'combustion_stability.lfi' in beyan, (
        'beyan, modellenen kısmın NEREDE olduğunu söylemeli')
    # Eski cümle ("...low-frequency instability ... is not modelled") artık
    # YALAN olurdu: mod konumlanıyor. Kalıbın kendisi yasak.
    assert 'is not modelled' not in beyan.lower(), (
        'eski "LFI modellenmiyor" cümlesi kalmış — bağlama onu çürüttü')
    # A10 sözleşmesi: beyan hâlâ kendi alanını adıyla anıyor
    assert 'boundary layer' in beyan.lower()


# ===========================================================================
# HİBRİT — akustik kritik tepki EŞİĞİ (hüküm YOK)
# ===========================================================================
def test_hibrit_akustik_esikte_HUKUM_YASAK(hibrit):
    """Eşik yolunda 'verdict' anahtarı YAPISAL olarak bulunamaz."""
    _, sonuc = hibrit
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    assert not _anahtar_var_mi(esik, 'verdict')
    assert not _anahtar_var_mi(esik, 'verdict_scope')
    assert esik['interpretation'] == 'threshold_not_verdict'
    # Çekirdeğin kendi bekçisi de razı olmalı (şema düzeyi kilit)
    forbid_verdict_key(esik, 'test')


def test_hibrit_esik_kapali_form_ozdesligiyle_dogrulaniyor(hibrit):
    """R_crit = ((γ+1)/γ)·(ṁ/ṁ_yakıt)·(1/2)/⟨ψ²⟩ — bağımsız türetim.

    Lüle sönümü ile basınç kuplajlı kazanç aynı M_N ve aynı (ā/L) çarpanını
    taşır; oran alınınca kavite idealleştirmesi DÜŞER ve geriye yalnız γ,
    yakıt payı ve mod şekli ortalaması kalır. Motorun sayısı bu kapalı formu
    tutmuyorsa bağlamada bir çarpan kaymış demektir.
    """
    _, sonuc = hibrit
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    gamma = float(sonuc['gamma'])
    yakit_payi = float(sonuc['mdot_total']) / float(sonuc['mdot_f'])
    assert esik['modes'], 'boyuna mod satırı üretilmedi'
    for satir in esik['modes']:
        beklenen = ((gamma + 1.0) / gamma * yakit_payi * 0.5
                    / satir['mode_shape_mean_square'])
        assert satir['critical_response_real'] == pytest.approx(
            beklenen, rel=1e-12), satir['label']
    # Hibritte eşik literatür bandının (1-3) ÜSTÜNDEDİR: yanan yüzeyden
    # yalnız yakıt girer. Bu bir hüküm değil, ölçülen sonucun yönüdür.
    assert esik['modes'][0]['critical_response_real'] > 3.0


def test_hibrit_kazanc_yalniz_YAKIT_debisiyle_kuruluyor(hibrit):
    """Oksitleyici baş taraftan girer: kazanca toplam debi konamaz."""
    _, sonuc = hibrit
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    rho = esik['chamber_gas_density_kg_m3']
    a_ses = esik['sound_speed_m_s']
    assert esik['surface_mach_M_b'] == pytest.approx(
        float(sonuc['mdot_f']) / (rho * a_ses
                                  * esik['burning_surface_area_m2']),
        rel=1e-12)
    assert esik['mean_flow_mach_M_N'] == pytest.approx(
        float(sonuc['mdot_total']) / (rho * a_ses
                                      * esik['acoustic_cavity_area_m2']),
        rel=1e-12)
    # İkisi karışırsa eşik (1 + O/F) katı kayar — ayrımın ölçülen izi
    assert esik['mean_flow_mach_M_N'] > esik['surface_mach_M_b']


def test_hibrit_mod_sekli_ortalamasi_GERCEK_pencereden(hibrit):
    """⟨ψ²⟩ yakıt portu penceresinden gelir; 1/2 varsayılanı değil."""
    _, sonuc = hibrit
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    L = float(sonuc['chamber_length'])
    z1 = float(sonuc['pre_chamber_length'])
    z2 = z1 + float(sonuc['grain_length'])
    for satir in esik['modes']:
        q = int(satir['label'].rstrip('L'))
        beklenen = 0.5 + (L / (4.0 * math.pi * q * (z2 - z1))) * (
            math.sin(2.0 * math.pi * q * z2 / L)
            - math.sin(2.0 * math.pi * q * z1 / L))
        assert satir['mode_shape_mean_square'] == pytest.approx(
            beklenen, rel=1e-12)
    # Pencere kaviteden kısa olduğu için ortalama 1/2 DEĞİL (ölçülen fark)
    assert esik['modes'][0]['mode_shape_mean_square'] < 0.5
    assert esik['modes'][0]['mode_shape_mean_square'] > 0.45


def test_hibrit_esik_yalniz_boyuna_modlarda(hibrit):
    """Enine/karma modlara sayı YAZILMAZ, gerekçesiyle listelenir."""
    _, sonuc = hibrit
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    etiketler = [s['label'] for s in esik['modes']]
    assert etiketler == ['1L', '2L', '3L', '4L', '5L', '6L']
    assert 'T' in ''.join(esik['transverse_modes_not_evaluated'])
    assert esik['transverse_modes_basis'].strip()
    # Enine modlar için hiçbir eşik sayısı yayımlanmıyor
    for etiket in esik['transverse_modes_not_evaluated']:
        assert etiket not in etiketler


def test_hibrit_eksik_kayip_terimleri_BEYANLI(hibrit):
    """Partikül/viskoz/yapısal sönüm yok ve eşiği kötümser yaptığı yazılı."""
    _, sonuc = hibrit
    sonum = sonuc['combustion_stability'][
        'acoustic_response_threshold']['damping']
    assert set(sonum['terms']) == {'nozzle'}
    for ad in ('particle_damping', 'viscous_wall_damping',
               'structural_damping', 'nozzle_unsteady_admittance'):
        assert sonum['not_modelled'][ad].strip()
    assert 'pessimistic' in sonum['bias_basis']
    assert sonum['total_damping_1_s'] < 0.0


# ===========================================================================
# KATI — τ_c, bulk (L*) modu ve çözücü kapısı çaprazı
# ===========================================================================
def test_kati_kararlilik_blogu_yayimlaniyor(kati):
    _, sonuc = kati
    blok = sonuc['combustion_stability']
    assert blok['model'] == 'hrma.stability F2b solid binding'
    assert blok['cavity_state'] == 'ignition'
    assert blok['chamber_time_constant']['status'] == 'modelled'
    assert blok['bulk_mode']['status'] == 'modelled'
    assert blok['acoustic_response_threshold']['status'] == 'modelled'


def test_kati_tau_c_cekirdekle_bit_ayni_ve_L_yildiz_tutarli(kati):
    """τ_c çekirdeğin doğrudan çağrısıyla bit-aynı; L* = V/A_t özdeşliği."""
    motor, sonuc = kati
    tau = sonuc['combustion_stability']['chamber_time_constant']
    beklenen = tau_c_from_volume(float(motor._case_free_volume()),
                                 tau['throat_area_m2'],
                                 float(motor.c_star), float(motor.gamma))
    for alan in ('tau_c_s', 'l_star_m', 'gamma_function_sq', 'c_star_m_s',
                 'chamber_volume_m3'):
        assert tau[alan] == beklenen[alan], alan
    assert tau['l_star_m'] == pytest.approx(
        tau['chamber_volume_m3'] / tau['throat_area_m2'], rel=1e-12)
    # Hacim, akustik bloğun kullandığı serbest hacmin TA KENDİSİ (tek kaynak)
    assert tau['chamber_volume_m3'] == pytest.approx(
        sonuc['acoustic_modes']['equivalent_cavity']['free_gas_volume_m3'],
        rel=1e-12)


def test_kati_bulk_modu_ve_cozucu_kapisi_AYNI_seyi_soyluyor(kati):
    """n < 1: hüküm 'stable', kritik uyarı yok, tutarlılık ölçülüp yayımlı."""
    motor, sonuc = kati
    bulk = sonuc['combustion_stability']['bulk_mode']
    beklenen = bulk_mode_zero_lag(
        float(motor.n),
        tau_c_s=sonuc['combustion_stability']['chamber_time_constant'][
            'tau_c_s'])
    assert bulk['verdict'] == beklenen['verdict'] == 'stable'
    assert bulk['verdict_scope'] == beklenen['verdict_scope']
    assert bulk['growth_rate_1_s'] == beklenen['growth_rate_1_s'] < 0.0
    kapi = bulk['solver_gate_consistency']
    assert kapi['warning_code'] == 'warn.solid.burn_rate_exponent_ge_one'
    assert kapi['warning_present'] is False
    assert kapi['criterion_met'] is False
    assert kapi['consistent'] is True
    assert 'zero thermal-lag' in bulk['verdict_scope']


def test_kati_n_bir_ustunde_UC_yol_da_ayni_seyi_soyluyor():
    """n >= 1: çekirdek 'unstable', çözücü kritik uyarı, koşu FAIL-CLOSED.

    Üç yol da aynı fiziği söylemek zorundadır. Üçüncüsü (yakınsama kapısı)
    performans sonucunu HİÇ üretmez, bu yüzden yayımlanan bir sonuçta bulk
    hükmü zorunlu olarak 'stable'dır; bu görünüşteki sabitlik bloğun kendi
    beyanındadır ve burada ölçülür.
    """
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    motor = SolidRocketEngine(burn_rate_n=1.0, **KATI_TABAN)
    sonuc = motor.calculate_performance()
    # (1) çözücü fail-closed: performans sonucu YOK
    assert sonuc.get('error'), 'n = 1,0 koşusu sonuç üretmemeliydi'
    assert 'combustion_stability' not in sonuc
    # (2) kritik uyarı yine de kullanıcıya ulaşıyor
    kodlar = [u.get('code') for u in (sonuc.get('warnings') or [])]
    assert 'warn.solid.burn_rate_exponent_ge_one' in kodlar
    # (3) aynı motorun bulk bağlaması 'unstable' der ve kapıyla tutarlıdır
    bulk = motor._bulk_mode_block(sonuc, {'tau_c_s': 1.0e-3})
    assert bulk['verdict'] == 'unstable'
    assert bulk['criterion_met'] is True
    assert bulk['growth_rate_1_s'] == pytest.approx(0.0, abs=1e-12)
    assert bulk['solver_gate_consistency']['consistent'] is True
    # Beyan, yayımlanan sonuçtaki görünür sabitliği açıklıyor mu?
    assert 'fails closed' in bulk['solver_gate_consistency']['basis']


# ===========================================================================
# KATI — akustik eşik ve QSHOD kapısı
# ===========================================================================
def test_kati_akustik_esikte_HUKUM_YASAK_ve_ozdeslik_tutuyor(kati):
    """Hüküm yok; yalnız lüle sönümüyle R_crit analitik olarak (γ+1)/γ."""
    motor, sonuc = kati
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    assert not _anahtar_var_mi(esik, 'verdict')
    forbid_verdict_key(esik, 'test')
    gamma = float(motor.gamma)
    assert esik['modes'], 'boyuna mod satırı üretilmedi'
    for satir in esik['modes']:
        assert satir['critical_response_real'] == pytest.approx(
            (gamma + 1.0) / gamma, rel=1e-12), satir['label']
        assert satir['mode_shape_mean_square'] == 0.5
    # Katıda tüm kütle yanan yüzeyden girer: iki Mach da AYNI ṁ ile kurulur
    assert esik['mean_flow_mach_M_N'] == pytest.approx(
        esik['surface_mach_M_b'] * esik['burning_surface_area_m2']
        / esik['acoustic_cavity_area_m2'], rel=1e-12)
    # Kavite, akustik bloğun BEYAN ETTİĞİ eşdeğer silindirdir (tek kaynak)
    kavite = sonuc['acoustic_modes']['equivalent_cavity']
    assert esik['acoustic_cavity_area_m2'] == pytest.approx(
        kavite['free_gas_volume_m3'] / kavite['length_m'], rel=1e-12)


def test_kati_ortalama_akis_machi_YAYIMLANIYOR(kati):
    """Yarı-kararlı kısa lüle limiti küçük M_N ister; sayı görünür olmalı.

    Ölçüldü (bu tane): M_N ≈ 0,56 — küçük değil. Eşikten düştüğü için
    R_crit'i kaydırmaz ama α ve kazanç değerlerinin geçerlilik zarfını
    kullanıcı ancak bu sayıyı görürse yargılayabilir.
    """
    _, sonuc = kati
    esik = sonuc['combustion_stability']['acoustic_response_threshold']
    assert 0.0 < esik['mean_flow_mach_M_N'] < 1.0
    assert 'small mean-flow mach' in esik['mach_basis'].lower()
    assert 'cancels out of' in esik['mach_basis']


def test_kati_qshod_kapisi_kapali_ve_VARSAYILAN_YOK(kati):
    """(A, B) ve κ verilmedikçe hiçbir sayı yayımlanmaz."""
    _, sonuc = kati
    blok = sonuc['combustion_stability']['qshod_response_band']
    assert blok['status'] == 'NOT_EVALUATED'
    assert any('combustion_response_band' in e for e in blok['missing_inputs'])
    assert 'propellant_thermal_diffusivity_m2_s' in blok['missing_inputs']
    assert not _sayi_yollari(blok), (
        f'kapalı kapıdan sayı sızdı: {_sayi_yollari(blok)}')


def _kati_curve_stub(sonuc):
    """Yayımlanan itki eğrisinden çekirdek için gereken iki dizi."""
    egri = sonuc['thrust_curve']
    return {'burn_area': egri['burn_area'], 'mass_flow': egri['mass_flow']}


def test_kati_qshod_bant_verilince_yol_UCTAN_UCA_calisiyor(kati):
    """Bant + κ verilirse mod başına Re(R_p) bandı üretilir (sentetik bant).

    Bantların KÜNYELİ tablosu bu partide yazılmadı; burada ölçülen şey
    yolun kendisidir: üstverili bant kabul edilir, zarf içi 'firm' rozeti
    alır, zarf dışı çalışma noktası 'extrapolated_low' ile döner.
    """
    motor, sonuc = kati
    akustik = sonuc['acoustic_modes']
    egri = _kati_curve_stub(sonuc)
    bant = QSHODBand(
        a_range=(6.0, 14.0), b_range=(0.55, 0.60), pressure_exponent_n=0.35,
        formulation_class='SYNTHETIC band — exercises the gated path only',
        pressure_range_Pa=(2.0e6, 8.0e6),
        temperature_range_K=(3000.0, 3700.0),
        source='synthetic test band (not a literature record)')
    eski_bant = getattr(motor, 'combustion_response_band', None)
    eski_kappa = getattr(motor, 'propellant_thermal_diffusivity_m2_s', None)
    try:
        motor.combustion_response_band = bant
        motor.propellant_thermal_diffusivity_m2_s = 1.0e-7
        blok = motor._qshod_band_block(akustik, egri)
        # Zarf DIŞI çalışma noktası: aynı bant, dar basınç zarfı
        dar = QSHODBand(
            a_range=(6.0, 14.0), b_range=(0.55, 0.60),
            pressure_exponent_n=0.35,
            formulation_class='SYNTHETIC band — narrow envelope',
            pressure_range_Pa=(1.0e5, 1.0e6),
            temperature_range_K=(3000.0, 3700.0),
            source='synthetic test band (not a literature record)')
        motor.combustion_response_band = dar
        blok_dar = motor._qshod_band_block(akustik, egri)
    finally:
        motor.combustion_response_band = eski_bant
        motor.propellant_thermal_diffusivity_m2_s = eski_kappa

    assert blok['status'] == 'modelled'
    assert [s['label'] for s in blok['modes']][:3] == ['1L', '2L', '3L']
    for satir in blok['modes']:
        assert satir['confidence'] == 'firm'
        assert satir['response_real_min'] <= satir['response_real_max']
        assert len(satir['corners']) == 4
        assert satir['omega_nondim'] > 0
    # ṙ_b çözücünün KENDİ kütle dengesinden okunur (ikinci model yok)
    assert blok['regression_rate_m_s'] == pytest.approx(
        float(egri['mass_flow'][0])
        / (float(motor.rho_p) * float(egri['burn_area'][0])), rel=1e-12)
    # Zarf dışı: gizlenmez ama rozeti düşer
    assert all(s['confidence'] == 'extrapolated_low'
               for s in blok_dar['modes'])
    assert 'OUTSIDE the validity envelope' in blok_dar['modes'][0][
        'confidence_basis']


# ===========================================================================
# Şema sözleşmesi (F2c paneli bu adlardan okuyacak)
# ===========================================================================
@pytest.mark.parametrize('motor_tipi', ['hibrit', 'kati'])
def test_iki_motorda_da_ayni_blok_adlari(motor_tipi, hibrit, kati):
    """İki motor aynı kavramı aynı adla yayımlar (ad icat etme yasağı)."""
    sonuc = hibrit[1] if motor_tipi == 'hibrit' else kati[1]
    blok = sonuc['combustion_stability']
    assert 'acoustic_response_threshold' in blok
    esik = blok['acoustic_response_threshold']
    for alan in ('sound_speed_m_s', 'chamber_gas_density_kg_m3',
                 'acoustic_cavity_area_m2', 'burning_surface_area_m2',
                 'mean_flow_mach_M_N', 'surface_mach_M_b', 'modes',
                 'modes_not_evaluated', 'transverse_modes_not_evaluated',
                 'interpretation', 'damping'):
        assert alan in esik, f'{motor_tipi}: {alan} yok'
    for satir in esik['modes']:
        assert set(satir) >= {'label', 'frequency_hz',
                              'critical_response_real', 'damping_total_1_s',
                              'response_gain_1_s', 'mode_shape_mean_square',
                              'interpretation'}


def test_esik_bloklari_sabit_metni_MOD_BASINA_tekrarlamiyor(hibrit, kati):
    """Uzun beyanlar blok düzeyinde tek kez; metin de KAYBOLMAMIŞ."""
    for _, sonuc in (hibrit, kati):
        esik = sonuc['combustion_stability']['acoustic_response_threshold']
        assert set(esik['not_modelled']) >= {
            'combustion_response_measurement', 'velocity_coupling',
            'flame_temperature_fluctuation'}
        for satir in esik['modes']:
            assert 'not_modelled' not in satir
            assert 'interpretation_basis' not in satir


# ===========================================================================
# Kaynak kanıtı: eşikler ve sabitler İKİNCİ KEZ tanımlanmadı
# ===========================================================================
def test_baglama_kendi_sabitini_TANIMLAMIYOR():
    """Motor dosyalarında korelasyon sabitinin kopyası olmamalı.

    Bağlama yalnız çekirdeği çağırır; 0,2341 / 2,050 / 6,38e5 / 4,47e5
    sayıları hrma/stability içinde TEK yerde durur. (Kopya sabit, çekirdek
    güncellenince sessizce eskir — parametre tutarlılığı kuralı.)
    """
    kok = pathlib.Path(__file__).resolve().parents[1] / 'hrma' / 'engines'
    yasak = ('0.2341', '2.050', '6.38e5', '4.47e5', '638000', '447000')
    for ad in ('hybrid_rocket_engine.py', 'solid_rocket_engine.py'):
        metin = (kok / ad).read_text(encoding='utf-8')
        for sayi in yasak:
            assert sayi not in metin, (
                f'{ad}: kalibre sabit {sayi} motor dosyasına kopyalanmış')


def test_bekci_dosyasi_kendi_ozetini_biliyor():
    """Mutasyon kanıtlarının md5'i bu dosyanın kendisine bağlıdır.

    Mutasyon turları (parti kaydında md5'li) bu dosyanın İÇERİĞİNE karşı
    koşuldu; dosya değişirse özet de değişir ve kanıt yeniden üretilmelidir.
    Bu bekçi yalnız özetin okunabilir olduğunu sabitler (dosya adı/konumu).
    """
    yol = pathlib.Path(__file__).resolve()
    ozet = hashlib.md5(yol.read_bytes()).hexdigest()
    assert len(ozet) == 32
