# hrma/cfd — viskoz duvar çıktılarının ÜRÜN köprüleri (§8.1 termal, §8.2 itki)
"""Yakınsamış viskoz CFD çözümünü ürünün hazır sözleşmelerine taşır.

NE OLDUĞU / NE OLMADIĞI
-----------------------
Bu modül YENİ FİZİK GETİRMEZ ve YENİ SAYI UYDURMAZ. Girdisi
``hrma.cfd.steady.solve_steady_axisym``ın yayımladığı ``viscous`` bloğudur
(``viscous.py``nin ÖLÇTÜĞÜ ``WallOutputs`` dizileri); çıktısı iki hazır
tüketici sözleşmesidir:

1. **Termal FEA köprüsü** (tasarım §8.1) — ``hrma.fea.bridge``ın istediği
   ``axial_profile`` üçlüsü (``x_mm``, ``h_g``, ``T_recovery``). Bugün o
   üçlüyü Bartz korelasyonu üretiyor (``HeatTransferAnalyzer.
   analyze_axial_profile``); burası aynı arayüzden ÇÖZÜLMÜŞ profili verir.
   İkisi arasındaki seçim kullanıcıya "kaynak: Bartz | CFD" olarak
   beyanlanır — birini sessizce diğeriyle değiştirmek YASAKTIR, bu yüzden
   çıktı ``source='cfd_viscous'`` imini ve çözüm künyesini taşır.

2. **İtki kaybı** (tasarım §8.2) — ``F_sürtünme = ∮ τ_w·ê_z dA`` dönel
   yüzey integrali. Yarı-1B zincirin ``friction_source`` politikası
   (``hrma.analysis.nozzle_flow_1d``: user > integral_bl_measured >
   legacy_constant) BU MODÜLDE DEĞİŞTİRİLMEZ; buradan çıkan sayı ÜÇÜNCÜ
   bir ölçüm olarak (``'cfd_viscous_measured'``) YAN YANA raporlanır.

ADYABATİK KOŞU h_g VEREMEZ (kapı, sessiz varsayılan yok)
--------------------------------------------------------
Adyabatik duvarda q_w ayrık olarak TAM SIFIRDIR ve T_w = T_aw'dir; yani
h_g = q_w/(T_aw − T_w) = 0/0 tanımsızdır. Bu modül o koşuda uydurma bir
h_g üretmez, ``ValueError`` ile reddeder ve hangi koşumun gerektiğini
söyler (izotermal duvar + T_wall_source beyanı).

T_aw'NİN KAYNAĞI HER ZAMAN BEYANLIDIR (``t_aw_basis``)
------------------------------------------------------
İki meşru yol vardır ve hangisinin kullanıldığı çıktıda ADLA durur:

* ``'recovery_factor'`` (VARSAYILAN) — kurtarma faktörü tanımı
  T_aw = T_e·(1 + r·(γ−1)/2·M_e²), r = Pr^(1/2) laminer / Pr^(1/3)
  türbülanslı. Bağıntının ve üslerin TEK kaynağı
  ``hrma.flow.boundary_layer`` (recovery_factor / recovery_temperature);
  burada ikinci kez yazılmaz. Laminer/türbülanslı ayrımı KOŞUMUN KENDİ
  beyanından okunur (``viscous['turbulence']`` None ise laminer), çağıran
  tahmininden değil.
* ``'adiabatic_companion_run'`` — aynı geometri ve aynı çalışma noktasında
  koşulmuş ADYABATİK ikiz çözümün ÖLÇÜLEN duvar sıcaklığı.

ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-19; conftest lülesi 64×16 laminer
doğrulama akışkanı μ = 0,15 Pa·s, izotermal duvar T_w = 0,6·T₀) —
sayılar ``tests/cfd/test_wall_output.py`` künyesinde tam tablosuyla:
iki yolun T_aw farkı ölçülür ve bekçiyle kilitlidir. İKİ YOL AYNI ŞEYİ
ÖLÇMEZ ve bu bir kusur değil TANIM farkıdır: adyabatik ikiz AYRI bir
çözümdür (duvar ısıl koşulu akışın tamamını değiştirir — ölçülen: aynı
ızgarada debi %8 kayıyor), kurtarma faktörü yolu ise izotermal koşunun
KENDİ kenar durumunu kullanır. Bu yüzden varsayılan kurtarma faktörü
yoludur: tek koşu, aynı alan, beyanlı bağıntı.
"""

import numpy as np

# Kurtarma faktörü/sıcaklığı bağıntısının TEK kaynağı (kopya yasak —
# parametre tutarlılığı kuralı; üsler orada künyeli sabittir).
from hrma.flow.boundary_layer import recovery_factor, recovery_temperature

# Yarı-1B zincirin defter sabiti: BURADA DEĞİŞTİRİLMEZ, yalnız yan yana
# raporlanır (göç politikası hrma/analysis/nozzle_flow_1d.py'de).
from hrma.constants import NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT

__all__ = [
    'THERMAL_PROFILE_SOURCE',
    'FRICTION_SOURCE',
    'T_AW_BASIS_RECOVERY',
    'T_AW_BASIS_ADIABATIC',
    'T_AW_BASES',
    'EDGE_SOURCE_AXIS',
    'EDGE_SOURCE_WALL_PRESSURE',
    'EDGE_SOURCES',
    'SUTTON_FRICTION_BAND',
    'SUTTON_FRICTION_BAND_CITATION',
    'WALL_OUTPUT_NOT_MODELLED',
    'Y_PLUS_WALL_RESOLVED',
    'Y_PLUS_LOG_LAYER',
    'wall_resolution_declaration',
    'thermal_axial_profile',
    'friction_thrust_loss',
    'viscous_wall_block',
    'solution_declaration',
]

#: Termal profilin kaynağı — panel/uç 'Bartz | CFD' karşılaştırmasını bu
#: imle kurar (Bartz tarafının imi analyze_axial_profile çıktısındadır).
THERMAL_PROFILE_SOURCE = 'cfd_viscous'

#: Sürtünme kaybının kaynağı — yarı-1B zincirin
#: ``losses.friction_loss_fraction_source`` alanıyla AYNI sözlük düzenidir
#: ('user' / 'integral_bl_measured' / 'legacy_constant' üçlüsünün YANINA
#: giren dördüncü ad; o zincirin varsayılanı BU PARTİDE DEĞİŞMEDİ).
FRICTION_SOURCE = 'cfd_viscous_measured'

T_AW_BASIS_RECOVERY = 'recovery_factor'
T_AW_BASIS_ADIABATIC = 'adiabatic_companion_run'
T_AW_BASES = (T_AW_BASIS_RECOVERY, T_AW_BASIS_ADIABATIC)

#: Kenar (edge) durumunun kaynağı — kurtarma faktörü yolunun T_e ve M_e'si.
EDGE_SOURCE_AXIS = 'axis_column'
EDGE_SOURCE_WALL_PRESSURE = 'isentropic_from_wall_pressure'
EDGE_SOURCES = (EDGE_SOURCE_AXIS, EDGE_SOURCE_WALL_PRESSURE)

#: Sürtünme kaybının literatür bandı [kesir]. Bu değer depoda BUGÜNE DEK
#: yalnız DÜZ METİNDE geçiyordu (hrma/constants.py ve
#: hrma/analysis/nozzle_flow_1d.py docstring'leri: "typical band 0.5-2 %");
#: sayısal biçimiyle İLK KEZ burada tanımlanıyor ve tek tanım yeri burasıdır
#: (CLAUDE.md kural 11). Defter sabiti (0,015) bu bandın içindedir ve
#: NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT'tan İTHAL EDİLİR, kopyalanmaz.
SUTTON_FRICTION_BAND = (0.005, 0.02)
SUTTON_FRICTION_BAND_CITATION = (
    'Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı, Böl. 3.5 '
    '(lüle kayıpları); Huzel & Huang, Böl. 1. Bant İYİ TASARLANMIŞ, '
    'TÜRBÜLANSLI sınır tabakalı roket lüleleri içindir.')

#: y⁺ BANT KENARLARI — TEK TANIM YERİ (ÖH D16 / P6B2-01, CLAUDE.md kural 11).
#: Bu iki sayı v2.6 boyunca ``hrma/app.py`` içinde düz sabit olarak duruyordu
#: (``CFD_Y_PLUS_WALL_RESOLVED`` / ``CFD_Y_PLUS_LOG_LAYER``) ve yalnız UÇ
#: rozetini besliyordu; FEA köprüsüne giden ``thermal_axial_profile`` onları
#: hiç görmüyordu. Tanım buraya taşındı çünkü duvar çözünürlüğü bir SUNUM
#: ayrıntısı değil, h_g'nin geçerlilik koşuludur; uç bu modülden ithal eder.
#:   * y⁺ ≤ 1   — duvar-çözümlü ızgara (çözücünün y⁺ döngüsünün hedefi;
#:                duvara integre eden bir kapanışın geçerlilik koşulu).
#:   * y⁺ ≥ 30  — log katmanının başlangıcı. Bu çözücüde DUVAR FONKSİYONU
#:                YOKTUR: ilk hücre log katmanına düşerse duvar gradyanı
#:                ızgarayla sınırlıdır ve q_w EKSİK ölçülür.
Y_PLUS_WALL_RESOLVED = 1.0
Y_PLUS_LOG_LAYER = 30.0

#: Bu köprünün KENDİ modellenmeyenleri (çözücünün not_modelled'ına EK).
WALL_OUTPUT_NOT_MODELLED = {
    'wall_resolution': (
        'Duvar ÇÖZÜNÜRLÜĞÜ bu koşumda garanti EDİLMEZ ve bir duvar '
        'fonksiyonu da yoktur: ilk hücre log katmanına düşerse (y⁺ ≥ '
        f'{Y_PLUS_LOG_LAYER:g}) duvar gradyanı ızgarayla sınırlıdır, q_w '
        'EKSİK ölçülür ve h_g = q_w/(T_aw − T_w) o oranda DÜŞÜK çıkar. '
        'Yön EMNİYETSİZDİR (düşük h_g → daha soğuk cidar → tasarım '
        'olduğundan güvenli görünür), bu yüzden hüküm burada bırakılmaz: '
        'ölçülen y⁺ ve çözünürlük kararı profilin kendi '
        '``wall_resolution`` bloğunda taşınır ve termal FEA köprüsü '
        'çözünmemiş duvardan gelen profili KABUL ETMEZ.'),
    'wall_roughness': (
        'Cidar pürüzlülüğü modellenmedi: τ_w ve q_w hidrolik olarak DÜZGÜN '
        'duvar için çözüldü. Pürüzlülük ikisini de artırır (sürtünme kaybı '
        've ısı yükü yönünde), yani bu köprünün sayıları o yönde İYİMSER.'),
    'radiation': (
        'Işıma ısı akısı YOK: q_w yalnız taşınım+iletimdir (k_eff ∂T/∂n). '
        'Bartz yolunun yanındaki gaz ışıması (Leckner) bu profilde '
        'MODELLENMEDİ; ikisi karşılaştırılırken bu fark beyanlıdır.'),
    'wall_temperature_coupling': (
        'Duvar sıcaklığı CFD koşusunda SABİT sınır koşuludur; termal FEA '
        'içinde T_w zamanla değişir. h_g bu koşumun T_w\'sinde ölçülmüştür '
        've h_g\'nin T_w bağımlılığı (Bartz σ düzeltmesinin karşılığı) '
        'ÇÖZÜLMEDİ — eşleşik (conjugate) koşum yapılmadı.'),
}

_MM_PER_M = 1000.0


# ---------------------------------------------------------------------------
# Sözleşme kapıları (sessiz varsayım yok)
# ---------------------------------------------------------------------------

def viscous_wall_block(result):
    """Sonuç sözlüğünden viskoz bloğu çıkarır; yoksa ADLA reddeder."""
    if not isinstance(result, dict):
        raise ValueError(
            'result, hrma.cfd.steady.solve_steady_axisym\'ın döndürdüğü '
            f'sözlük olmalı; gelen {type(result).__name__}.')
    if 'viscous' not in result:
        raise ValueError(
            'CFD sonucunda \'viscous\' anahtarı yok: bu köprü VİSKOZ '
            'koşunun duvar dizilerini tüketir. Euler koşusunda duvar '
            'kayma gerilmesi ve ısı akısı YOKTUR (kayma duvarı) ve '
            'uydurulmaz.')
    block = result['viscous']
    if not isinstance(block, dict):
        raise ValueError(
            'result[\'viscous\'] None: çözücü viskoz KAPALI koşuldu '
            '(ViscousOptions verilmedi). Termal profil ve sürtünme kaybı '
            'viskoz çözümden ÖLÇÜLÜR, Euler koşusundan türetilmez.')
    return block


def _wall_array(block, key, name, ni_ref=None):
    """Viskoz bloktan duvar dizisi: 1B, sonlu, beklenen uzunlukta."""
    if key not in block:
        raise ValueError(
            f'viscous[{key!r}] yok: bu köprü _viscous_output_block '
            f'sözleşmesini ({name}) tüketir.')
    arr = np.asarray(block[key], dtype=float)
    if arr.ndim != 1 or arr.size < 2:
        raise ValueError(
            f'viscous[{key!r}] 1B ve en az 2 elemanlı olmalı; gelen şekil '
            f'{arr.shape}.')
    if ni_ref is not None and arr.size != ni_ref:
        raise ValueError(
            f'viscous[{key!r}] uzunluğu {arr.size}, duvar ekseninin '
            f'uzunluğu {ni_ref} — sözleşme ihlali (diziler aynı '
            'istasyonlarda olmalı).')
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            f'viscous[{key!r}] sonlu olmayan değer içeriyor (ıraksamış '
            'koşu?) — profil üretilmez.')
    return arr


def _inputs(result, key, name):
    """``result['inputs']`` yankısından zorunlu skaler (varsayılan YOK)."""
    inputs = result.get('inputs')
    if not isinstance(inputs, dict) or inputs.get(key) is None:
        raise ValueError(
            f'CFD sonucunda inputs[{key!r}] ({name}) yok: bu köprü '
            'çözücünün girdi yankısını tüketir ve gaz/rezervuar '
            'büyüklüğünü UYDURMAZ.')
    return float(inputs[key])


def _prandtl(block):
    """Pr'ı koşumun KENDİ taşınım beyanından okur (ikinci kaynak yok)."""
    try:
        pr = block['declaration']['transport']['prandtl']
    except (KeyError, TypeError):
        raise ValueError(
            'viscous[\'declaration\'][\'transport\'][\'prandtl\'] yok: '
            'kurtarma faktörü r = Pr^n koşumun KENDİ Prandtl sayısıyla '
            'kurulur (GasTransport.declaration); varsayılan bir Pr '
            'uydurulmaz.')
    pr = float(pr)
    if not np.isfinite(pr) or pr <= 0.0:
        raise ValueError(f'Beyandaki Prandtl sayısı geçersiz: {pr!r}.')
    return pr


def _is_turbulent(block):
    """Koşum türbülanslı mıydı? (Kurtarma üssünü BU belirler, çağıran değil.)"""
    return block.get('turbulence') is not None


# ---------------------------------------------------------------------------
# Çözüm künyesi (panel/uç bunu 'Bartz | CFD' seçiminde gösterir)
# ---------------------------------------------------------------------------

def solution_declaration(result):
    """Profilin arkasındaki koşumun künyesi: ızgara, y⁺, yakınsama.

    HİÇBİR SAYI ÜRETMEZ — çözücünün yayımladığı alanları toplar. Panel bu
    künyeyle "bu profil hangi koşumdan geldi" sorusunu cevaplar; künyesiz
    profil yayımlanmaz (FEA beyan deseni).
    """
    block = viscous_wall_block(result)
    inputs = result.get('inputs') or {}
    y_loop = block.get('y_plus_loop') or {}
    res_hist = result.get('residual_history')
    son_kalinti = (None if res_hist is None or len(res_hist) == 0
                   else float(np.asarray(res_hist)[-1]))
    durum = result.get('convergence_status')
    plato = result.get('convergence_plateau')
    # ÜÇ DURUMLU HÜKÜM (OH-D31-15): çözücü None döndürdüyse hüküm
    # YARGILANMAMIŞTIR ve künye bunu AYNEN taşır. Alan HİÇ yoksa (eski
    # sözleşme) False kalır — "hüküm yok" ile "hüküm alanı yayımlanmadı"
    # ayrı şeylerdir ve burada ikincisi fail-closed False sayılır.
    _hukum = result.get('converged', False)
    return {
        'converged': (None if _hukum is None else bool(_hukum)),
        'convergence_basis': str(result.get('convergence_basis', '')),
        # HÜKÜMSÜZLÜĞÜN CİNSİ (ÖH defter OH-D15-07): çözücü
        # 'converged' | 'not_evaluated' | 'plateau' | 'not_converged' |
        # 'diverged' alanını
        # steady.py'de ZATEN yayımlıyor; künye onu TAŞIMIYORDU ve tüketici
        # (panel, FEA köprüsü) platoyu bütçe yetmezliğinden ancak
        # convergence_basis CÜMLESİNİ ayrıştırarak ayırabiliyordu.
        # Sayı türetilmez, çözücünün alanı AYNEN geçirilir; koşum onu
        # yayımlamadıysa None kalır ('bilinmiyor' ASLA 'plato' sayılmaz).
        'convergence_status': (None if durum is None else str(durum)),
        'convergence_plateau': (dict(plato) if isinstance(plato, dict)
                                else None),
        'iterations': (None if result.get('iterations') is None
                       else int(result['iterations'])),
        'final_residual_scaled': son_kalinti,
        'grid_ni': inputs.get('grid_ni'),
        'grid_nj': inputs.get('grid_nj'),
        'grid_radial_distribution': inputs.get('grid_radial_distribution'),
        'y_plus_target': y_loop.get('target'),
        'y_plus_achieved_max': y_loop.get('achieved_max'),
        'y_plus_achieved_mean': y_loop.get('achieved_mean'),
        'y_plus_fraction_within_target': y_loop.get('fraction_within_target'),
        'turbulence': (None if block.get('turbulence') is None
                       else block['turbulence'].get('model')),
        'thermal_mode': block.get('thermal_mode'),
        'T_wall_source': block.get('T_wall_source'),
        'kernel_backend': result.get('kernel_backend'),
        'time_integrator': result.get('time_integrator'),
        'runtime_s': result.get('runtime_s'),
        '_basis': (
            'Koşum künyesi: profilin/kuvvetin arkasındaki çözümün kimliği. '
            'converged=False ise sayılar GİZLENMEZ ama SAĞLAM DA '
            'SUNULMAZ — tüketici (panel, FEA köprüsü) bu bayrağı ve '
            'convergence_basis metnini göstermek zorundadır. y⁺ alanları '
            'ÖLÇÜMDÜR (τ_w\'den), korelasyon tahmini değildir. '
            'HÜKÜMSÜZLÜĞÜN CİNSİ convergence_status alanından MAKİNE-OKUR '
            'çıkar (converged | plateau | not_converged | diverged) ve '
            'ayrıntısı convergence_plateau sözlüğündedir: plato, kalıntının '
            'ÖLÇÜLEN bir bantta durduğu — yani bütçeyi büyütmenin kapıyı '
            'geçirmeyeceği — hâldir ve hükmün YERİNE GEÇMEZ (converged yine '
            'False). İkisi de None ise koşum bu alanları yayımlamamıştır; '
            'cins BİLİNMİYOR demektir, plato sayılmaz.'),
    }


def wall_resolution_declaration(kunye):
    """Duvar çözünürlüğü HÜKMÜ — h_g'nin geçerlilik koşulu (P6B2-01).

    ``solution_declaration`` çıktısındaki ÖLÇÜLEN y⁺ maksimumunu bir
    hükme çevirir. Ham sayı zaten yayımlanıyordu ama YORUMSUZDU: ölçüldü
    (a1 ``once.json`` K4) y⁺_maks = 268,86 olan bir koşumun h_g'si
    16,96-110,95 W/(m²·K) idi, yani deponun kendi Bartz zincirinin
    yaklaşık %1'i — ve bu profil termal FEA köprüsüne hiçbir engel
    olmadan girebiliyordu.

    Args:
        kunye: ``solution_declaration(result)`` çıktısı.

    Returns:
        dict — ``resolved`` (True/False/None), ``y_plus_max``,
        ``y_plus_wall_resolved_edge``, ``y_plus_log_layer_edge``,
        ``regime`` ve ``basis``. ``resolved is None`` = y⁺ ÖLÇÜLEMEDİ
        (viskoz olmayan koşu); hüküm UYDURULMAZ.
    """
    y = kunye.get('y_plus_achieved_max')
    try:
        y = None if y is None else float(y)
    except (TypeError, ValueError):
        y = None
    if y is None or not np.isfinite(y):
        return {
            'resolved': None,
            'y_plus_max': None,
            'y_plus_wall_resolved_edge': Y_PLUS_WALL_RESOLVED,
            'y_plus_log_layer_edge': Y_PLUS_LOG_LAYER,
            'regime': None,
            'basis': ('y⁺ bu koşumda ÖLÇÜLMEDİ (viskoz duvar çıktısı yok); '
                      'duvar çözünürlüğü hükmü verilmez ve "çözüldü" '
                      'varsayılmaz.'),
        }
    if y <= Y_PLUS_WALL_RESOLVED:
        rejim = 'wall_resolved'
    elif y < Y_PLUS_LOG_LAYER:
        rejim = 'buffer_layer'
    else:
        rejim = 'log_layer'
    return {
        'resolved': bool(rejim == 'wall_resolved'),
        'y_plus_max': y,
        'y_plus_wall_resolved_edge': Y_PLUS_WALL_RESOLVED,
        'y_plus_log_layer_edge': Y_PLUS_LOG_LAYER,
        'regime': rejim,
        'basis': (
            f'ÖLÇÜLEN maks y⁺ = {y:.4g}. Duvar-çözümlü sayılması için '
            f'y⁺ ≤ {Y_PLUS_WALL_RESOLVED:g} gerekir (bu çözücüde duvar '
            f'fonksiyonu YOKTUR; y⁺ ≥ {Y_PLUS_LOG_LAYER:g} log katmanıdır). '
            'Çözünmemiş duvarda duvar gradyanı ızgarayla sınırlıdır: q_w '
            've dolayısıyla h_g EKSİK ölçülür ve hata yönü EMNİYETSİZDİR '
            '(daha soğuk cidar öngörüsü). Termal FEA köprüsü bu hükme '
            'BAKAR (bridge.extract_thermal_inputs).'),
    }


# ---------------------------------------------------------------------------
# §8.1 — Termal FEA köprüsü
# ---------------------------------------------------------------------------

def _edge_state(result, block, edge_source, gamma):
    """Kenar (edge) durumunu ADLI kaynağından çıkarır: (M_e, T_e, beyan)."""
    ni = np.asarray(block['wall_z_m']).size
    if edge_source == EDGE_SOURCE_AXIS:
        fields = result.get('fields')
        if not isinstance(fields, dict) or 'mach' not in fields \
                or 'temperature_K' not in fields:
            raise ValueError(
                'edge_source=\'axis_column\' için result[\'fields\'] '
                '(\'mach\' ve \'temperature_K\') gerekir — çözücünün alan '
                'yayını olmadan kenar durumu ölçülemez.')
        mach = np.asarray(fields['mach'], dtype=float)
        temp = np.asarray(fields['temperature_K'], dtype=float)
        if mach.ndim != 2 or mach.shape[0] != ni:
            raise ValueError(
                f'fields[\'mach\'] biçimi ({ni}, nj) olmalı; gelen '
                f'{mach.shape}.')
        return mach[:, 0], temp[:, 0], (
            'Kenar durumu EKSEN KOLONUNDAN (j = 0) ölçüldü: çekirdek '
            'akışın kendi hücre değerleri. Bu seçim sınır tabakasının '
            'kanalı DOLDURMADIĞI akışlar içindir (lüle); tam gelişmiş '
            'boru akışında eksen "kenar" DEĞİLDİR ve bu kaynak '
            'kullanılmamalıdır.')
    if edge_source == EDGE_SOURCE_WALL_PRESSURE:
        P0 = _inputs(result, 'P0_Pa', 'rezervuar durma basıncı')
        T0 = _inputs(result, 'T0_K', 'rezervuar durma sıcaklığı')
        if 'wall_pressure_Pa' not in result:
            raise ValueError(
                'edge_source=\'isentropic_from_wall_pressure\' için '
                'result[\'wall_pressure_Pa\'] gerekir.')
        p_w = np.asarray(result['wall_pressure_Pa'], dtype=float)
        if p_w.size != ni:
            raise ValueError(
                f'wall_pressure_Pa uzunluğu {p_w.size}, duvar ekseni {ni}.')
        if np.any(p_w <= 0.0) or P0 <= 0.0:
            raise ValueError('Basınçlar pozitif olmalı (izantropik ters '
                             'çözüm tanımsız).')
        # M_e izantropik ters bağıntıdan: p₀/p = (1 + (γ−1)/2 M²)^(γ/(γ−1)).
        # Sınır tabakası boyunca p sabit kabulü (tabakanın KENDİ yaklaşımı).
        oran = np.power(P0 / p_w, (gamma - 1.0) / gamma) - 1.0
        oran = np.maximum(oran, 0.0)
        mach = np.sqrt(2.0 * oran / (gamma - 1.0))
        temp = T0 / (1.0 + 0.5 * (gamma - 1.0) * mach ** 2)
        return mach, temp, (
            'Kenar durumu DUVAR BASINCINDAN izantropik olarak kuruldu: '
            'M_e = √(2/(γ−1)·((P₀/p_w)^((γ−1)/γ) − 1)), '
            'T_e = T₀/(1 + (γ−1)/2·M_e²). Dayanağı sınır tabakası '
            'yaklaşımının kendisidir (∂p/∂n ≈ 0), ama P₀ REZERVUAR '
            'değeridir: viskoz durma basıncı kaybı çekirdekte ihmal '
            'edilmiştir (şok varsa bu kaynak GEÇERSİZDİR).')
    raise ValueError(
        f'edge_source {edge_source!r} tanımsız — geçerli kaynaklar '
        f'{EDGE_SOURCES}. Varsayılan {EDGE_SOURCE_AXIS!r}dır ve seçilen '
        'kaynak çıktıda ADLA görünür (sessizce birine düşülmez).')


def thermal_axial_profile(result, *, t_aw_basis=T_AW_BASIS_RECOVERY,
                          adiabatic_result=None,
                          edge_source=EDGE_SOURCE_AXIS):
    """Viskoz çözümden FEA köprüsünün ``axial_profile`` üçlüsü (§8.1).

    Args:
        result: ``solve_steady_axisym`` sonuç sözlüğü — İZOTERMAL duvarlı
            viskoz koşu (adyabatik koşuda h_g tanımsızdır, aşağıya bakın).
        t_aw_basis: ``'recovery_factor'`` (varsayılan) ya da
            ``'adiabatic_companion_run'``. Hangi yol seçildiyse çıktıda
            ``t_aw_basis`` alanıyla BEYAN EDİLİR.
        adiabatic_result: ``'adiabatic_companion_run'`` yolunda ZORUNLU —
            aynı ızgarada, aynı çalışma noktasında koşulmuş adyabatik
            duvarlı çözüm sözlüğü. Duvar sıcaklığı O KOŞUMUN ÖLÇÜMÜDÜR.
        edge_source: kurtarma faktörü yolunda kenar durumunun kaynağı
            (``EDGE_SOURCES``).

    Returns:
        dict — köprü sözleşmesi (``x_mm``, ``h_g``, ``T_recovery``) +
        ölçülen ham diziler (``q_w_W_m2``, ``T_wall_K``, ``T_edge_K``,
        ``mach_edge``) + kaynak imi ve çözüm künyesi.

    Raises:
        ValueError: viskoz blok yok/None; koşu adyabatik (h_g tanımsız);
            t_aw_basis tanımsız ya da eşlikçisi verilmemiş; T_aw ≤ T_w
            (h_g işareti tanımsız); eksen kesin artan değil.
    """
    block = viscous_wall_block(result)
    if t_aw_basis not in T_AW_BASES:
        raise ValueError(
            f't_aw_basis {t_aw_basis!r} tanımsız — geçerli değerler '
            f'{T_AW_BASES}. T_aw\'nin kaynağı BEYANLI bir seçimdir; '
            'sessizce birine düşülmez.')

    mode = block.get('thermal_mode')
    if mode == 'adiabatic':
        raise ValueError(
            'Bu koşu ADYABATİK duvarlıdır: q_w ayrık olarak TAM SIFIR ve '
            'T_w = T_aw\'dir, yani h_g = q_w/(T_aw − T_w) = 0/0 '
            'TANIMSIZDIR. Termal FEA sınır koşulu için İZOTERMAL duvarlı '
            'bir koşu gerekir (ViscousOptions(wall_thermal="isothermal", '
            'T_wall=..., T_wall_source=...)). Adyabatik koşu bu köprüde '
            'yalnız adiabatic_result olarak, T_aw KAYNAĞI diye '
            'kullanılabilir.')
    if mode != 'isothermal':
        raise ValueError(
            f'viscous[\'thermal_mode\'] {mode!r} beklenmedik — bu köprü '
            '\'isothermal\' koşu ister.')

    z = _wall_array(block, 'wall_z_m', 'duvar ekseni [m]')
    ni = z.size
    q_w = _wall_array(block, 'wall_heat_flux_W_m2', 'duvar ısı akısı', ni)
    T_w = _wall_array(block, 'wall_temperature_K', 'duvar sıcaklığı', ni)
    if not np.all(np.diff(z) > 0.0):
        raise ValueError(
            'viscous[\'wall_z_m\'] kesin artan değil: FEA köprüsü '
            'axial_profile.x_mm için kesin artan eksen ister '
            '(enterpolasyon tanımsız olurdu).')
    if np.any(T_w <= 0.0):
        raise ValueError('Duvar sıcaklığı pozitif olmalı.')

    gamma = _inputs(result, 'gamma', 'özgül ısı oranı γ')
    pr = _prandtl(block)
    turbulent = _is_turbulent(block)

    if t_aw_basis == T_AW_BASIS_ADIABATIC:
        if adiabatic_result is None:
            raise ValueError(
                't_aw_basis=\'adiabatic_companion_run\' seçildi ama '
                'adiabatic_result verilmedi. Bu yol T_aw\'yi AYRI BİR '
                'KOŞUMUN ölçümünden alır; eşlikçisiz kullanılamaz ve '
                'sessizce kurtarma faktörü yoluna düşülmez.')
        adi = viscous_wall_block(adiabatic_result)
        if adi.get('thermal_mode') != 'adiabatic':
            raise ValueError(
                'adiabatic_result ADYABATİK duvarlı bir koşu olmalı; gelen '
                f'thermal_mode={adi.get("thermal_mode")!r}. İzotermal bir '
                'koşumun duvar sıcaklığı kurtarma sıcaklığı DEĞİLDİR.')
        T_aw = _wall_array(adi, 'wall_temperature_K',
                           'adyabatik duvar sıcaklığı', ni)
        z_adi = _wall_array(adi, 'wall_z_m', 'adyabatik duvar ekseni', ni)
        if not np.allclose(z_adi, z, rtol=1e-12, atol=0.0):
            raise ValueError(
                'adiabatic_result AYNI ızgarada değil: duvar ekseni '
                'uyuşmuyor. Başka bir ızgaranın T_aw\'si bu profile '
                'taşınmaz (eksen uyuşmazlığı sessiz sahte veridir).')
        r_f = recovery_factor(pr, turbulent=turbulent)
        M_e = T_e = None
        edge_beyan = (
            'Kenar durumu KULLANILMADI: T_aw doğrudan adyabatik ikiz '
            'koşumun ÖLÇÜLEN duvar sıcaklığıdır.')
        t_aw_detay = (
            'T_aw = adyabatik duvarlı EŞ KOŞUMUN ölçülen yüz sıcaklığı '
            '(wall_thermal="adiabatic": ∂T/∂n = 0 sınır koşulu, sıcaklık '
            'SONUÇTUR). UYARI — iki koşu AYNI AKIŞ ALANI DEĞİLDİR: duvar '
            'ısıl koşulu yoğunluk profilini ve dolayısıyla debiyi '
            'değiştirir (ölçüldü, tests/cfd/test_wall_output.py künyesi). '
            'Bu yolun bedeli iki koşumdur; kazancı kurtarma faktörü '
            'kabulünden bağımsız olmasıdır.')
    else:
        M_e, T_e, edge_beyan = _edge_state(result, block, edge_source, gamma)
        if np.any(T_e <= 0.0):
            raise ValueError('Kenar sıcaklığı pozitif olmalı.')
        r_f = recovery_factor(pr, turbulent=turbulent)
        T_aw = np.array([recovery_temperature(float(te), float(me), gamma,
                                              r_f)
                         for te, me in zip(T_e, M_e)], dtype=float)
        t_aw_detay = (
            f'T_aw = T_e·(1 + r·(γ−1)/2·M_e²), r = Pr^'
            f'{"1/3 (türbülanslı)" if turbulent else "1/2 (laminer)"} = '
            f'{r_f:.6f} (Pr = {pr:g}, koşumun KENDİ taşınım beyanından). '
            'Bağıntı ve üsler hrma.flow.boundary_layer\'ın tek '
            'kaynağından ithal edildi; laminer/türbülanslı ayrımı '
            'koşumun kendi turbulence beyanından okundu (çağıran '
            'tahmininden değil). ' + edge_beyan)

    delta_T = T_aw - T_w
    if np.any(delta_T <= 0.0):
        kotu = int(np.argmin(delta_T))
        raise ValueError(
            f'T_aw ≤ T_w olan istasyon var (i = {kotu}, z = '
            f'{z[kotu] * _MM_PER_M:.4f} mm, T_aw = {T_aw[kotu]:.2f} K, '
            f'T_w = {T_w[kotu]:.2f} K): h_g = q_w/(T_aw − T_w) tanımsız ya '
            'da işareti belirsiz olurdu. Duvar kurtarma sıcaklığından '
            'sıcaksa ısı transferi yönü terstir; bu koşum termal FEA '
            'sınır koşulu üretmez ve uydurma bir h_g yayımlanmaz.')
    h_g = q_w / delta_T
    if np.any(h_g <= 0.0):
        kotu = int(np.argmin(h_g))
        raise ValueError(
            f'h_g ≤ 0 olan istasyon var (i = {kotu}, h_g = {h_g[kotu]:.6g} '
            f'W/(m²·K), q_w = {q_w[kotu]:.6g} W/m²): FEA köprüsü kesin '
            'pozitif h_g ister (bridge.extract_thermal_inputs sözleşmesi) '
            've negatif değer kırpılarak "pozitif" gösterilmez.')

    kunye = solution_declaration(result)
    return {
        # --- FEA köprüsünün ZORUNLU üçlüsü (bridge.extract_thermal_inputs)
        'x_mm': (z * _MM_PER_M).tolist(),
        'h_g': h_g.tolist(),
        'T_recovery': T_aw.tolist(),
        # --- ölçülen ham diziler (tüketici gizli hesaba muhtaç değil) -----
        'q_w_W_m2': q_w.tolist(),
        'T_wall_K': T_w.tolist(),
        'T_edge_K': (None if T_e is None else np.asarray(T_e).tolist()),
        'mach_edge': (None if M_e is None else np.asarray(M_e).tolist()),
        'n_stations': int(ni),
        # --- kaynak imi ve beyan ------------------------------------------
        'source': THERMAL_PROFILE_SOURCE,
        't_aw_basis': t_aw_basis,
        't_aw_basis_detail': t_aw_detay,
        'edge_source': (None if t_aw_basis == T_AW_BASIS_ADIABATIC
                        else edge_source),
        'recovery_factor': float(r_f),
        'recovery_regime': 'turbulent' if turbulent else 'laminar',
        'prandtl': float(pr),
        'solution_basis': kunye,
        # ÖH D16 / P6B2-01 — h_g'nin GEÇERLİLİK KOŞULU profille birlikte
        # seyahat eder. Uyarı eskiden yalnız uç yanıtının BAŞKA bir
        # bloğundaydı (``viscous.y_plus_badge``); köprü payload'ı forward
        # edildiğinde geride kalıyordu ve FEA tarafı çözünmemiş duvardan
        # gelen h_g'yi kapısız kabul ediyordu.
        'wall_resolution': wall_resolution_declaration(kunye),
        'not_modelled': dict(WALL_OUTPUT_NOT_MODELLED),
        '_basis': (
            'h_g(z) = q_w(z)/(T_aw(z) − T_w(z)) — q_w ve T_w viskoz '
            'çözümün ÖLÇÜMÜDÜR (viscous.py WallOutputs), T_aw\'nin '
            'kaynağı t_aw_basis ile ADLA beyanlıdır. Eksen (x_mm) duvar '
            'YÜZLERİNİN orta noktalarıdır; ızgara '
            'sample_nozzle_inner_contour konturundan kurulduğunda FEA '
            'köprüsünün eksen uyuşması TANIM GEREĞİ sağlanır (kalan fark '
            'yarım hücredir ve köprünün THERMAL_PROFILE_DOMAIN_TOL '
            'toleransının çok içindedir; kapsanmayan uç için köprü kendi '
            'sabit-değer beyanını yapar). BARTZ İLE DEĞİŞTİRME YASAĞI: bu '
            'profil source=\'cfd_viscous\' imiyle gelir ve Bartz profiliyle '
            'YAN YANA gösterilir; biri diğerinin yerine sessizce '
            'konmaz.'),
    }


# ---------------------------------------------------------------------------
# §8.2 — İtki kaybı
# ---------------------------------------------------------------------------

def _wall_normals(grid, block):
    """Duvar yüzü birim normalleri — IZGARADAN ölçülür, varsayılmaz.

    ``grid.face_j[:, -1]`` 2π çarpanını İÇEREN dönel yüzey vektörüdür
    (grid_axisym.AxisymGrid sözleşmesi); büyüklüğü duvar yüz alanıdır ve
    viskoz bloğun ``wall_area_m2`` dizisiyle ÖZDEŞ olmalıdır — özdeş
    değilse ızgara ile sonuç aynı koşuma ait değildir ve reddedilir.
    """
    face = np.asarray(grid.face_j[:, -1], dtype=float)
    area = np.hypot(face[:, 0], face[:, 1])
    area_pub = np.asarray(block['wall_area_m2'], dtype=float)
    if area.shape != area_pub.shape:
        raise ValueError(
            f'Izgara duvar yüzü sayısı {area.shape} ile sonucun '
            f'wall_area_m2 uzunluğu {area_pub.shape} uyuşmuyor: grid bu '
            'çözümün ızgarası değil.')
    if not np.allclose(area, area_pub, rtol=1e-12, atol=0.0):
        raise ValueError(
            'Izgaranın duvar yüz alanları sonucun wall_area_m2 dizisiyle '
            'uyuşmuyor (bağıl fark '
            f'{float(np.max(np.abs(area - area_pub) / area_pub)):.3e}): '
            'verilen grid bu çözümün ızgarası değil. Başka bir ızgaranın '
            'normalleriyle kuvvet integrali alınmaz.')
    return face[:, 0] / area, face[:, 1] / area, area


def friction_thrust_loss(result, grid):
    """Duvar sürtünmesinin itki kaybı (§8.2): ∮ τ_w·ê_z dA, beyanlı sözlük.

    İŞARET SÖZLEŞMESİ: yayımlanan ``friction_force_N`` **itkiyi AZALTAN**
    büyüklüktür, yani bağlı (ayrılmamış) akışta POZİTİFTİR. Çözücünün ham
    ölçümü ``viscous['axial_friction_force_on_fluid_N']`` bunun TERSİDİR
    (akışkana etkiyen kuvvet, sürüklenmede negatif) — burada işaret bir kez
    ve BEYANLA çevrilir, ikinci bir yerde çevrilmez.

    İKİ TANIM YAN YANA ÖLÇÜLÜR (biri diğerinin yerine geçmez):
      * ``friction_force_N`` — ∮ (τ·n̂)_z dA, akışkanın gördüğü eksenel
        viskoz kuvvetin TAMAMI (kayma + normal gerilme bileşeni). Momentum
        bütçesine giren büyüklük budur.
      * ``friction_force_tangential_N`` — ∮ τ_w·(t̂·ê_z) dA, tasarım
        §8.2'nin yazdığı SALT KAYMA biçimi. Aradaki fark normal viskoz
        gerilmenin payıdır ve ``normal_stress_share`` ile yayımlanır
        (ölçülür, ihmal EDİLDİĞİ VARSAYILMAZ).

    Args:
        result: viskoz ``solve_steady_axisym`` sonucu.
        grid: o koşumun ``AxisymGrid``i — duvar normalleri ve çıkış yüzey
            vektörleri ORADAN ölçülür (2π dâhil). Sonuç sözlüğü ızgarayı
            taşımadığı için ZORUNLUDUR; uyuşmazsa reddedilir.

    Returns:
        dict — kuvvet [N], referans itki bileşenleri, kesirler, Sutton
        bandı karşılaştırması ve beyan.
    """
    block = viscous_wall_block(result)
    ham = block.get('axial_friction_force_on_fluid_N')
    if ham is None or not np.isfinite(float(ham)):
        raise ValueError(
            'viscous[\'axial_friction_force_on_fluid_N\'] yok ya da sonlu '
            'değil: sürtünme kaybı çözümün KENDİ yüzey integralinden '
            'gelir (viscous.py WallOutputs), burada yeniden türetilmez.')
    n_z, n_r, area = _wall_normals(grid, block)
    tau = _wall_array(block, 'wall_shear_Pa', 'duvar kayma gerilmesi',
                      area.size)

    # Akış teğeti t̂ = (n_r, −n_z) — viscous.py'nin τ_w tanımıyla AYNI
    # teğet (orada tau_wall = −(traction_z·n_r − traction_r·n_z) olarak
    # kurulur). t̂·ê_z = n_r.
    F_tan = float(np.sum(tau * n_r * area))
    F_traction = -float(ham)

    # --- referans yüzey: ÇIKIŞ DÜZLEMİNİN kendi momentum akısı -----------
    fields = result.get('fields')
    if not isinstance(fields, dict):
        raise ValueError('result[\'fields\'] yok: itki referansı çıkış '
                         'düzleminden ölçülür.')
    S = np.asarray(grid.face_i[-1], dtype=float)
    rho = np.asarray(fields['rho_kg_m3'], dtype=float)[-1]
    uz = np.asarray(fields['u_z_m_s'], dtype=float)[-1]
    ur = np.asarray(fields['u_r_m_s'], dtype=float)[-1]
    p = np.asarray(fields['pressure_Pa'], dtype=float)[-1]
    if S.shape[0] != rho.size:
        raise ValueError(
            f'Izgara çıkış yüzü sayısı {S.shape[0]} ile alan sütunu '
            f'{rho.size} uyuşmuyor: grid bu çözümün ızgarası değil.')
    mdot_face = rho * (uz * S[:, 0] + ur * S[:, 1])
    F_mom = float(np.sum(mdot_face * uz))
    F_p_gauge = float(np.sum(p * S[:, 0]))
    if not (F_mom > 0.0):
        raise ValueError(
            f'Çıkış momentum akısı pozitif değil ({F_mom:.6g} N): kayıp '
            'kesri tanımsız olurdu (payda sıfır/negatif). Ham kuvvet '
            'yine de friction_force_N ile okunabilir.')

    kesir = F_traction / F_mom
    bant_ic = bool(SUTTON_FRICTION_BAND[0] <= kesir
                   <= SUTTON_FRICTION_BAND[1])
    return {
        'friction_force_N': F_traction,
        'friction_force_tangential_N': F_tan,
        'normal_stress_share': ((F_traction - F_tan) / F_traction
                                if F_traction != 0.0 else float('nan')),
        'axial_friction_force_on_fluid_N': float(ham),
        'wetted_area_m2': float(np.sum(area)),
        'momentum_thrust_N': F_mom,
        'exit_pressure_force_N': F_p_gauge,
        'exit_mass_flow_kg_s': float(np.sum(mdot_face)),
        'friction_loss_fraction': float(kesir),
        'friction_loss_fraction_of_momentum_plus_pressure':
            float(F_traction / (F_mom + F_p_gauge))
            if (F_mom + F_p_gauge) > 0.0 else None,
        'friction_source': FRICTION_SOURCE,
        'sutton_band': tuple(SUTTON_FRICTION_BAND),
        'sutton_band_citation': SUTTON_FRICTION_BAND_CITATION,
        'within_sutton_band': bant_ic,
        'legacy_constant': float(NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT),
        'solution_basis': solution_declaration(result),
        'not_modelled': dict(WALL_OUTPUT_NOT_MODELLED),
        'reference_surface_basis': (
            'Kayıp KESRİ, kuvvetin ÇIKIŞ DÜZLEMİNİN momentum akısına '
            'oranıdır: F_mom = Σ_çıkış ρ·u_z·(u·S), S 2π dâhil dönel yüzey '
            'vektörü (grid.face_i[-1]). Bu, yarı-1B zincirin kesir tanımıyla '
            '(friction_drag_N/momentum_thrust, hrma.analysis.nozzle_flow_1d) '
            'AYNI referans yüzeydir — iki sayı yan yana konabilsin diye '
            'bilerek aynı seçildi. Basınç itkisi ayrı yayımlanır (mutlak '
            'basınç ile; ortam basıncı BU KATMANDA BİLİNMEZ, o yüzden '
            '"pressure thrust" adı KULLANILMADI).'),
        'policy_basis': (
            'BU SAYI HİÇBİR VARSAYILANI DEĞİŞTİRMEZ. Yarı-1B lüle '
            'zincirinin yayımladığı sürtünme kaybı politikası (user > '
            'integral_bl_measured > legacy_constant, göç manifestosu '
            'tests/flow/test_surtunme_gocu.py) OLDUĞU GİBİ kalır; buradaki '
            f'ölçüm {FRICTION_SOURCE!r} adıyla ÜÇÜNCÜ bir sayı olarak yan '
            'yana raporlanır. Defter sabiti '
            f'({NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT}) ithal edildi, '
            'kopyalanmadı.'),
        'band_comparison_basis': (
            'within_sutton_band, ölçülen kesrin '
            f'{SUTTON_FRICTION_BAND[0]:.3f}-{SUTTON_FRICTION_BAND[1]:.3f} '
            'bandına düşüp düşmediğidir. ANLAM SINIRI: bant TÜRBÜLANSLI '
            'sınır tabakalı, uçuş sınıfı roket lüleleri içindir. Laminer '
            'bir doğrulama akışkanıyla (ya da Reynolds sayısı uçuş '
            'rejiminin çok altında bir koşumla) ölçülen kesir bu bandın '
            'DIŞINA düşebilir; O VAKADA bant-dışılık vakanın rejim '
            'farkıdır ve bayrak hüküm değil BEYANDIR. '
            'BU MUAFİYET KOŞULLUDUR VE KOŞULU BURADA OKUNMAZ (ÖH defter '
            'P6B2-03): ürünün KENDİ varsayılan lüle koşumu laminer bir '
            'doğrulama vakası DEĞİLDİR — orada Re_D = 1,67e+06 (uçuş '
            'sınıfı) ölçülmüş ve kesir 3,06e-04 çıkmıştır, yani bandın alt '
            'ucunun 16,3 KATI ALTINDA. Bu satır o vakayı "kusur değil" '
            'ilan ETMEZ ve edemez: rejim türbülanslıysa bant-dışılık '
            'AÇIKLANMASI GEREKEN bir sapmadır (ölçülen kök: duvar '
            'çözünmemiştir — wall_resolution hükmüne bakılır, '
            'wall_resolution_declaration). Rejimi ve çözünürlüğü görmek '
            'için solution_basis (ızgara, y⁺) ve koşumun taşınım beyanı '
            'okunmalıdır; hangi muafiyetin geçerli olduğuna BU KATMAN '
            'karar VERMEZ, ikisini de ölçülmüş biçimde yan yana koyar.'),
        '_basis': (
            'F_sürtünme = ∮ τ_w·ê_z dA (tasarım §8.2), dönel yüzey '
            'integrali: yüz alanları ızgaranın KENDİ 2π\'li yüzey '
            'vektörlerinden ölçüldü (grid.face_j[:, -1]) ve sonucun '
            'wall_area_m2 dizisiyle özdeşliği DENETLENDİ. İşaret: '
            'yayımlanan değer itkiyi AZALTAN kayıptır (bağlı akışta '
            'pozitif); ayrılmış bölgede τ_w işaret değiştirir ve integrale '
            'ters işaretle girer — kırpma yapılmaz.'),
    }
