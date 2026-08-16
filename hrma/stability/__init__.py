# hrma/stability — F2 yanma kararlılığı çekirdeği (Aşama F2a)
"""hrma.stability — yanma kararlılığı çekirdeği: zaman sabitleri, chug çevrimi,
hibrit LFI korelasyonu, sönüm bütçesi ve kritik yanma tepkisi eşiği.

Tasarım belgesi: ``docs/mimari/f2-yanma-tepkisi-tasarimi.md`` (BAĞLAYICI —
model kararları, kapsam ve §8.1'deki sekiz karar orada). Bu paket F2a'dır:
**motor bağlaması YOKTUR**. Saf fiziktir; motor sonuç sözlüklerini okumaz,
Flask katmanını tanımaz, hiçbir ``hrma.engines`` modülünü ithal etmez.
Motor ayakları (hibrit/katı/sıvı) F2b'nin, panel F2c'nin işidir.

``hrma/analysis/acoustic_modes.py`` YERİNDE KALIR ve buradan **ithal edilir**
(36 bekçisi + üç motor çağrısı ona bağlı); mod tablosu ikinci kez üretilmez.

===========================================================================
DONDURULMUŞ TİP SÖZLEŞMESİ (karar 7 — F2b/F2c bunun üstüne yazacak)
===========================================================================
CFD kulvarının (``hrma/cfd/steady.py``) adlandırma geleneği AYNEN sürer;
aynı temel büyüklük iki kulvarda iki ayrı adla icat edilmez.

1) BİRİM SONEKİ ZORUNLU VE SI
   Her sayısal alan adı büyüklüğü + SI birimini taşır. Ölçülen depo geleneği
   (cfd/steady.py, acoustic_modes.py): ``_Pa``, ``_K``, ``_m``, ``_m2``,
   ``_m3``, ``_m_s`` (m/s), ``_m2_s2`` ((m/s)²), ``_kg_s``, ``_kg_m3``,
   ``_kg_m2_s``, ``_s``, ``_1_s`` (1/s), ``_hz``, ``_W``, ``_J_kgK``.
   Boyutsuz büyüklükte sonek yoktur (``gamma``, ``mach``, ``of_ratio``).

   **Zaman SI'dir: saniye.** Tasarım belgesi §4.2 taslağındaki ``tau_c_ms``
   yerine ``tau_c_s`` yayımlanır (ms dönüşümü sunum katmanının — F2c —
   işidir; aynı büyüklük iki birimle iki anahtarda taşınmaz).

2) ORTAK BÜYÜKLÜK ADLARI (bu paketin her yerinde AYNI anlam)
   ``l_star_m``            karakteristik kamara boyu L* = V/A_t [m]
   ``c_star_m_s``          karakteristik hız c* [m/s]
   ``gamma``               izantropik üs (boyutsuz, > 1)
   ``gamma_function_sq``   Γ² = γ(2/(γ+1))^((γ+1)/(γ−1))  (0, 1) aralığında
   ``tau_c_s``             kamara doldurma/boşaltma zaman sabiti [s]
   ``tau_s``               yanmanın duyarlı zaman gecikmesi τ [s]
   ``tau_f_s``             besleme hattı atalet zaman sabiti [s]
   ``dp_ratio_j``          J = ΔP_enjektör / P_c (boyutsuz, chug kazancı)
   ``growth_rate_1_s``     lineer büyüme oranı Re(s) [1/s]; > 0 büyüme
   ``frequency_hz``        salınım frekansı [Hz]
   ``damping_1_s``         sönüm katkısı α [1/s]; NEGATİF = sönümleme
   ``response_real``       basınç kuplajlı yanma tepkisinin gerçek kısmı
                           Re(R_p) (boyutsuz; R_p ≡ (ṁ'/ṁ̄)/(p'/p̄))

3) BEYAN ALANLARI (CFD deseniyle birebir)
   ``*_basis``       o sayının nereden geldiğinin künyeli cümlesi (İngilizce)
   ``not_modelled``  modellenmeyen fizik sözlüğü; sonuca AYNEN kopyalanır
   ``assumptions``   varsayım etiketleri listesi
   ``inputs``        çağıranın verdiği her sayının yankısı + ``_basis``

4) HÜKÜM SÖZLEŞMESİ (karar 1 + sıkılaştırma — ŞEMA DÜZEYİNDE ZORLANIR)
   Hüküm ``make_verdict()`` DIŞINDA kurulamaz. Üretilen üçlü:
   ``verdict`` ∈ {'stable', 'unstable', 'marginal'} · ``verdict_scope``
   (mekanizma kapsamı, ZORUNLU) · ``verdict_basis`` (gerekçe, ZORUNLU).
   Çıplak hüküm YASAKTIR: kapsamsız/boş kapsamlı çağrı ``ValueError`` atar
   (kullanıcı çıplak "STABLE"i "tüm mekanizmalara karşı stabil" okur).

   Hüküm YALNIZ çevrimin kapandığı yerde verilir: chug (``chug.py``), katı
   bulk modu (``chamber.py``) ve hibrit LFI'nin varlık beyanı
   (``hybrid_lfi.py``). **Akustik yolda hüküm YOKTUR**: ``response.py``
   sonuçlarında 'verdict' anahtarı YAPISAL olarak bulunmaz (eşik bir gün
   sessizce hükme dönüşmesin diye ``forbid_verdict_key()`` bekçisi kurulur).

5) UYDURMA VARSAYILAN YASAĞI
   Bu pakette hiçbir fiziksel/geometrik girdinin varsayılanı yoktur. Eksik
   girdi ``ValueError`` ile reddedilir (``acoustic_modes`` deseni). Modül
   sabitleri yalnız KÜNYELİ literatür sabitleridir (Karabeyoglu 2005'in
   kalibre RT_av'i, Culick & Yang 1990 bağıntı katsayıları) ve tek yerde
   tanımlıdır. Chug eşikleri (0,20/0,15) burada YENİDEN tanımlanmaz;
   ``hrma.analysis.acoustic_modes``ten ithal edilir (tek kaynak kuralı).

Modüller:
    chamber.py     Γ², τ_c, R·T = (c*Γ)² özdeşliği, katı bulk (L*) modu
    chug.py        konsantre parametreli besleme çevrimi + nötr eğri +
                   Lambert-W büyüme oranı + (opsiyonel) besleme ataleti
    hybrid_lfi.py  Karabeyoglu ve ark. 2005 Denk. 15 + oksitleyici kapısı
    damping.py     lüle sönümü (Culick & Yang 1990) + sönüm bütçesi
    response.py    QSHOD/Denison-Baum tepki fonksiyonu (bant kapılı) +
                   kritik tepki eşiği R_crit (mod başına, HÜKÜMSÜZ)
"""

__version__ = '0.1.0'          # F2a çekirdeği (motor bağlaması/UI YOK)

# ---------------------------------------------------------------------------
# Hüküm sözlüğü — tek kaynak. Tasarım belgesi §4.2'nin üç değeri, karar 1'in
# kapsam zorunluluğuyla.
# ---------------------------------------------------------------------------
VERDICT_STABLE = 'stable'
VERDICT_UNSTABLE = 'unstable'
VERDICT_MARGINAL = 'marginal'
VERDICTS = frozenset((VERDICT_STABLE, VERDICT_UNSTABLE, VERDICT_MARGINAL))

# ---------------------------------------------------------------------------
# Bilinçli olarak MODELLENMEYENLER (tasarım belgesi §2.2). Sonuç sözlüklerine
# aynen kopyalanır; "sessizce yok sayıldı" durumu oluşmaz.
# ---------------------------------------------------------------------------
STABILITY_NOT_MODELLED = {
    'nonlinear_behaviour': (
        'Nonlinear behaviour is NOT modelled: triggering, limit-cycle '
        'amplitude and DC pressure shift are outside this linear analysis. '
        'A linearly stable motor can still be triggered into a limit cycle '
        'by a finite disturbance; no amplitude is predicted anywhere.'),
    'combustion_response_measurement': (
        'The combustion response function is NOT derived from propellant '
        'chemistry: it is measured (T-burner, dynamic pressure). Where it is '
        'not supplied, only the critical threshold R_crit is inverted from '
        'the damping budget — a threshold, never a verdict.'),
    'detailed_flame_dynamics': (
        'Detailed flame dynamics (LES / hybrid RANS-LES flame transfer '
        'functions) are NOT modelled; out of scope for this solver.'),
    'vortex_shedding': (
        'Vortex-shedding / acoustic lock-in (VSO, VSA, VSP) is NOT '
        'modelled: the vortex source location (inhibitor, step, diaphragm) '
        'is not part of the solved geometry.'),
    'pogo': (
        'POGO is NOT modelled: the loop closes through vehicle structure, '
        'which this solver does not model.'),
    'injection_coupled_hf': (
        'Injection-coupled high frequency modes (e.g. LOX post quarter-wave) '
        'are NOT modelled: injector element post length is not produced by '
        'the injector design module.'),
    'three_dimensional_acoustics': (
        'Three-dimensional Helmholtz eigenvalue solution and linearised '
        'Euler with mean flow are NOT modelled; the mode table stays in the '
        'analytic cylinder idealisation (see acoustic_modes.not_modelled).'),
    'damping_devices': (
        'Baffle / acoustic cavity damping EFFECTIVENESS is NOT modelled: no '
        'claim of the form "this baffle damps this mode by X" is made.'),
}


def make_verdict(verdict, scope, basis):
    """Kapsam etiketi ZORUNLU hüküm üçlüsü kurar (karar 1 sıkılaştırması).

    Bu paketteki tek hüküm üretme yolu budur; çıplak 'stable' yayımlanamaz.

    Args:
        verdict: 'stable' | 'unstable' | 'marginal'.
        scope: hükmün geçerli olduğu MEKANİZMA kapsamı (boş olamaz), ör.
            'feed-coupled chug (modeled mechanism only)'.
        basis: hükmün gerekçesi (boş olamaz).

    Returns:
        dict: verdict / verdict_scope / verdict_basis.

    Raises:
        ValueError: hüküm sözlükte değilse ya da kapsam/gerekçe boşsa.
    """
    if verdict not in VERDICTS:
        raise ValueError(
            f"verdict must be one of {sorted(VERDICTS)} (got {verdict!r}).")
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError(
            'verdict_scope is mandatory: a verdict may not be published '
            'without naming the mechanism it covers (a bare verdict is read '
            'as "stable against every instability mechanism").')
    if not isinstance(basis, str) or not basis.strip():
        raise ValueError(
            'verdict_basis is mandatory: the reason behind the verdict must '
            'be published with it.')
    return {
        'verdict': verdict,
        'verdict_scope': scope.strip(),
        'verdict_basis': basis.strip(),
    }


def forbid_verdict_key(payload, where):
    """Hükümsüz yolların ('eşik' yolları) şema bekçisi.

    ``response.py`` gibi YAPISAL olarak hüküm vermeyen yollarda çağrılır:
    sözlükte (iç içe dahil) 'verdict' anahtarı belirirse ``ValueError``.
    Gerekçe: kritik tepki eşiği R_crit bir GÖSTERGEDİR; ileride sessizce
    hükme dönüşmesi bu bekçiyle imkânsız kılınır.
    """
    def _walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == 'verdict':
                    raise ValueError(
                        f"{where}: 'verdict' key is structurally forbidden on "
                        f"this path (found at {path or '<root>'}). The "
                        f"critical response is a THRESHOLD, not a verdict "
                        f"(design doc §3.0/§4.2).")
                _walk(value, f'{path}.{key}' if path else str(key))
        elif isinstance(node, (list, tuple)):
            for i, value in enumerate(node):
                _walk(value, f'{path}[{i}]')
    _walk(payload, '')
    return payload


from hrma.stability.chamber import (              # noqa: E402
    bulk_mode_zero_lag,
    chamber_time_constant,
    cstar_from_rt,
    gamma_function,
    gamma_function_sq,
    rt_from_cstar,
    tau_c_from_volume,
)
from hrma.stability.chug import (                  # noqa: E402
    CHUG_GAIN_J_MAX,
    assess_chug,
    chug_neutral_frequency_hz,
    chug_neutral_tau_ratio,
    chug_rightmost_root,
    feed_inertance_time_constant,
    sweep_feed_line_length,
)
from hrma.stability.damping import (               # noqa: E402
    damping_budget,
    nozzle_damping_quasi_steady,
)
from hrma.stability.hybrid_lfi import (            # noqa: E402
    LFI_COEFFICIENT,
    LFI_DELAY_CONSTANT_C_PRIME,
    LFI_FREQUENCY_DELAY_COEFFICIENT,
    RT_AV_M2_S2,
    assess_hybrid_lfi,
    boundary_layer_delay_s,
    lfi_frequency_hz,
    rt_av_for_oxidizer,
)
from hrma.stability.response import (              # noqa: E402
    QSHODBand,
    critical_response_table,
    critical_response_real,
    qshod_response,
    response_gain_uniform_chamber,
)

__all__ = [
    '__version__',
    'VERDICT_STABLE', 'VERDICT_UNSTABLE', 'VERDICT_MARGINAL', 'VERDICTS',
    'STABILITY_NOT_MODELLED',
    'make_verdict', 'forbid_verdict_key',
    # chamber
    'gamma_function', 'gamma_function_sq', 'chamber_time_constant',
    'tau_c_from_volume', 'rt_from_cstar', 'cstar_from_rt',
    'bulk_mode_zero_lag',
    # chug
    'CHUG_GAIN_J_MAX', 'chug_neutral_tau_ratio', 'chug_neutral_frequency_hz',
    'chug_rightmost_root', 'feed_inertance_time_constant', 'assess_chug',
    'sweep_feed_line_length',
    # hybrid LFI
    'RT_AV_M2_S2', 'LFI_COEFFICIENT', 'LFI_DELAY_CONSTANT_C_PRIME',
    'LFI_FREQUENCY_DELAY_COEFFICIENT', 'rt_av_for_oxidizer',
    'boundary_layer_delay_s', 'lfi_frequency_hz', 'assess_hybrid_lfi',
    # damping / response
    'nozzle_damping_quasi_steady', 'damping_budget',
    'QSHODBand', 'qshod_response', 'response_gain_uniform_chamber',
    'critical_response_real', 'critical_response_table',
]
