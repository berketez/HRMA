# hrma/cfd — CFD duvar basıncı → Summerfield ayrılma hükmü köprüsü (Aşama 1B)
"""
2B eksenel simetrik Euler çözümünün duvar basıncından ayrılma hükmü.

NE OLDUĞU / NE OLMADIĞI
-----------------------
Bu modül YENİ FİZİK GETİRMEZ: ``hrma.cfd.steady.solve_steady_axisym``ın
yayımladığı duvar basıncı dizisine (``wall_pressure_Pa`` / ``wall_pressure_z_m``
sözleşmesi) yayımlanmış Summerfield ölçütünü uygular. Ölçütün kendisi ve
sayısal bandı depoda ZATEN tanımlıdır; buraya KOPYALANMAZ:

- ``hrma.analysis.nozzle_flow_1d.SEPARATION_FACTOR_DEFAULT / _MIN / _MAX``
  → k'nın varsayılanı ve kabul bandı (tek kaynak, parametre tutarlılığı).
- ``hrma.flow.separation.summerfield_pressure_ratio`` → eşik oranını veren
  fonksiyon; ``CRITERION_SUMMERFIELD`` ölçüt adı ve ``SEPARATION_NOT_MODELLED``
  beyanı da oradan alınır (aynı ölçütün ikinci gerçeklemesi yazılmaz).

Fark yalnız DUVAR BASINCININ NEREDEN GELDİĞİDİR:
``hrma.flow.separation.assess_separation`` duvar basıncını tam-akan
izantropik yarı-1B çekirdekten TEMSİL EDER (kendi docstring'inde beyanlı);
burada ise duvar basıncı 2B Euler çözümünün duvara komşu hücrelerinden
ÖLÇÜLMÜŞ değerdir. İç şoklu / ayrılma öncesi gerçek basınç dağılımı yarı-1B
izantropik dalla temsil edilemez — köprünün varlık sebebi budur.

ÖLÇÜT (tek satır)
-----------------
    p_w(z) < k · P_ortam      →  o istasyonda ayrılma öngörülür
    k = 0,40 (varsayılan, literatür bandının muhafazakâr ucu; 0,35-0,40)
    Summerfield, M., Foster, C.R., Swan, W.C., "Flow Separation in
    Overexpanded Supersonic Exhaust Nozzles", Jet Propulsion 24 (1954);
    Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı, Böl. 3.

ARAMA BÖLGESİ (yanlış pozitif kapısı)
-------------------------------------
Ölçüt yalnız IRAKSAK (boğaz sonrası) bölgede aranır. Yakınsak bölge ve
kamara ses-altıdır ve orada p_w, P_ortam'ın çok üstündedir; ölçüt aşırı
genleşmiş SES-ÜSTÜ duvar sınır tabakası için türetilmiştir — ses-altı
girişte uygulanması fiziksel olarak anlamsızdır. Boğaz istasyonunun kendisi
de dışarıdadır (kesit M ≈ 1). Arama bölgesinin dayanağı çıktıda
``search_domain_basis`` ile beyan edilir.

HÜKÜM / DOĞRULAMA AYRIMI
------------------------
Çözücü yakınsamadıysa (``converged=False``) hüküm GİZLENMEZ ama SAĞLAM DA
SUNULMAZ: ``judgment_confidence='suspect'`` ve ``judgment_basis`` çözücünün
kendi ``convergence_basis`` beyanını taşır. Aynı deseni FEA katmanı da
kullanır (kabul ölçütü sağlanmadan hüküm verilmez).

ÇAĞIRAN İÇİN — AD ÇAKIŞMASI UYARISI
-----------------------------------
``hrma.flow`` paketi de ``assess_separation`` adını dışa verir (yarı-1B
sürüm; imzası ``(P0, Pa, gamma, ...)``). Aynı modülde ikisi birden
kullanılacaksa BURADAKİ takma adla alınmalıdır, yoksa sessiz gölgeleme olur:

    from hrma.cfd.separation import assess_separation as assess_cfd_separation

Bu köprünün ilk argümanı çözücü SONUÇ SÖZLÜĞÜDÜR (P0/gamma değil);
yanlışlıkla değiş tokuş edilirse sözleşme denetimi ValueError ile durdurur
(sessiz yanlış hüküm üretilmez).

MODELLENMEYENLER
----------------
Euler ayrılmış bölgeyi ÇÖZEMEZ (viskozite/sınır tabaka yok): bu modül
ayrılmanın BAŞLAMA istasyonunu ölçütle öngörür, ayrılma sonrası akış alanını
üretmez. Ayrılma ardındaki duvar basıncı platosu, yanal yükler, FSS/RSS
ayrımı modellenmedi — çıktıdaki ``not_modelled`` sözlüğü
``hrma.flow.separation.SEPARATION_NOT_MODELLED`` ile ``hrma.cfd``
``CFD_NOT_MODELLED`` beyanlarının birleşimidir.
"""

import numpy as np

# Ölçüt sabitlerinin TEK kaynağı (kopya yasak — parametre tutarlılığı kuralı).
from hrma.analysis.nozzle_flow_1d import (
    SEPARATION_FACTOR_DEFAULT,
    SEPARATION_FACTOR_MAX,
    SEPARATION_FACTOR_MIN,
)
from hrma.flow.separation import (
    CRITERION_SUMMERFIELD,
    SEPARATION_NOT_MODELLED,
    summerfield_pressure_ratio,
)

__all__ = ['assess_separation', 'SEPARATION_FACTOR_DEFAULT',
           'SEPARATION_FACTOR_MIN', 'SEPARATION_FACTOR_MAX',
           'CRITERION_SUMMERFIELD']

_SEARCH_DOMAIN_BASIS = (
    'Ölçüt yalnız ıraksak bölgede (boğaz index\'inin BİR sonrasından çıkışa) '
    'arandı: Summerfield bağıntısı aşırı genleşmiş ses-üstü duvar sınır '
    'tabakası için türetilmiştir; ses-altı yakınsak bölge ve kamara arama '
    'dışıdır (orada p_w >> P_ortam olduğundan hüküm anlamsız, yanlış pozitif '
    'kapısı). Boğaz istasyonunun kendisi de dışarıda (kesit M ≈ 1).')

_Z_INTERP_BASIS = (
    'separation_z_m ilk ayrılmış İSTASYONUN duvar hücresi merkezidir '
    '(separation_wall_pressure_Pa aynı istasyonun değeri). '
    'separation_z_interp_m ise eşiğin geçildiği yerin komşu iki istasyon '
    'arasındaki doğrusal ara değeridir (alt-hücre kestirimi; hücre-merkezli '
    'FVM\'de duvar değeri dışdeğerlenmemiş ham komşu değerdir).')

_LENGTH_BASIS = (
    'Ayrılan bölge, birinci mertebe Summerfield işleyişiyle ilk ayrılma '
    'istasyonundan ÇIKIŞA kadar sayılır (ayrılma sonrası duvarda ortam '
    'basıncı platosu kabulü — hrma.analysis.nozzle_flow_1d._solve_separation '
    'ile aynı gelenek). Oran, ıraksak boya (z_çıkış − z_boğaz) bölünerek '
    'verilir. Ham sayım ayrıca stations_below_threshold ile raporlanır.')

_REATTACH_BASIS = (
    'Ayrılma istasyonunun AŞAĞISINDA p_w eşiğin üstüne geri çıkıyor: '
    'sürtünmesiz (Euler) çözümde bu tipik olarak iç normal şokun basınç '
    'sıçramasıdır. Gerçek viskoz akışta ayrılma şok ayağından itibaren '
    'sürer; Euler ayrılmış bölgeyi çözemediği için bu geri çıkış FİZİKSEL '
    'YENİDEN YAPIŞMA SAYILMAZ, yalnız beyan edilir '
    '(not_modelled.separation_resolution).')


def _as_wall_array(result, key, name):
    """Sonuç sözlüğünden duvar dizisini 1B float dizi olarak çıkarır."""
    if key not in result:
        raise ValueError(
            f'CFD sonucunda {key!r} yok: bu köprü '
            f'hrma.cfd.steady.solve_steady_axisym\'ın duvar basıncı '
            f'sözleşmesini ({name}) tüketir. Sözleşmeyi taşımayan bir '
            f'sözlükten ayrılma hükmü üretilmez.')
    arr = np.asarray(result[key], dtype=float)
    if arr.ndim != 1 or arr.size < 3:
        raise ValueError(
            f'{key!r} 1B ve en az 3 elemanlı olmalı; gelen şekil '
            f'{arr.shape}.')
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            f'{key!r} sonlu olmayan değer içeriyor (ıraksamış koşu?) — '
            f'ayrılma hükmü verilmez.')
    return arr


def _resolve_throat_index(result, z_wall):
    """Boğaz index'i + dayanağı (uydurma yok; bulunamazsa ValueError).

    Merdiven: (1) çözücünün yayımladığı ``throat['i']``; (2) yoksa
    GEOMETRİDEN — duvar sütununun yarıçapı ``r_centers_m[:, -1]`` en küçük
    olan kolon. ``wall_pressure_z_m`` TEK BAŞINA boğazı belirleyemez (eksen
    yarıçap taşımaz), o yüzden ikinci basamak yarıçap alanını ister.
    """
    throat = result.get('throat')
    if isinstance(throat, dict) and throat.get('i') is not None:
        i_t = int(throat['i'])
        if not (0 <= i_t < z_wall.size - 1):
            raise ValueError(
                f"throat['i']={i_t} duvar ekseninin dışında "
                f'(0…{z_wall.size - 2}) — sonuç sözlüğü tutarsız.')
        return i_t, ('Boğaz index\'i çözücünün yayımladığı throat[\'i\'] '
                     'alanından alındı.')

    r_centers = result.get('r_centers_m')
    if r_centers is not None:
        r_arr = np.asarray(r_centers, dtype=float)
        if r_arr.ndim == 2 and r_arr.shape[0] == z_wall.size:
            i_t = int(np.argmin(r_arr[:, -1]))
            return i_t, (
                'Boğaz index\'i sonuçta throat[\'i\'] bulunmadığından '
                'GEOMETRİDEN türetildi: duvar sütunu yarıçapının '
                '(r_centers_m[:, -1]) en küçük olduğu kolon.')

    raise ValueError(
        'Boğaz index\'i belirlenemedi: sonuçta ne throat[\'i\'] ne de '
        'r_centers_m var. wall_pressure_z_m tek başına boğazı veremez '
        '(yarıçap bilgisi taşımaz) ve uydurma bir boğaz konumu '
        'varsayılmaz.')


def _resolve_factor(separation_factor):
    """k katsayısı + kaynağı ('default' | 'caller'); bant denetimi tek bantla."""
    if separation_factor is None:
        factor = float(SEPARATION_FACTOR_DEFAULT)
        source = 'default'
    else:
        factor = float(separation_factor)
        source = 'caller'
    if not (SEPARATION_FACTOR_MIN <= factor <= SEPARATION_FACTOR_MAX):
        raise ValueError(
            f'separation_factor {factor:g}, kabul bandının '
            f'[{SEPARATION_FACTOR_MIN}, {SEPARATION_FACTOR_MAX}] dışında '
            f'(Summerfield literatür bandı 0,35-0,40; bant sabitleri '
            f'hrma.analysis.nozzle_flow_1d\'den ithal edilir).')
    # Eşik değeri ölçütün kendi fonksiyonundan; aynı bandı ikinci kez
    # doğrular (iki kaynak ayrışırsa burada patlar — sürüklenme kapısı).
    return float(summerfield_pressure_ratio(factor)), source


def _not_modelled():
    """Ayrılma + CFD beyanlarının birleşimi (anahtar çakışması yok)."""
    # Paket kökü çağrı anında alınır: hrma.cfd.__init__ steady'yi içe
    # aktarırken bu modül yüklenirse döngü olmasın (steady.py ile aynı desen).
    from hrma.cfd import CFD_NOT_MODELLED
    merged = dict(SEPARATION_NOT_MODELLED)
    merged.update(CFD_NOT_MODELLED)
    return merged


def assess_separation(result, P_ambient_Pa, separation_factor=None):
    """CFD duvar basıncından Summerfield ayrılma hükmü (beyanlı sözlük).

    Args:
        result: ``hrma.cfd.steady.solve_steady_axisym`` sonuç sözlüğü.
            Kullanılan sözleşme: ``wall_pressure_Pa`` (ni,),
            ``wall_pressure_z_m`` (ni,), ``converged``, ``throat['i']``
            (yoksa ``r_centers_m``'den türetilir, dayanağı beyan edilir).
        P_ambient_Pa: Ortam (dış) basıncı [Pa]. ZORUNLU — varsayılanı YOKTUR
            (deniz seviyesi/vakum varsayımı uydurma sayılır). ``None`` ya da
            negatif → ValueError. Tam 0 (vakum) → ayrılma tanımsızdır;
            ``applicable=False`` beyanıyla döner
            (hrma.flow.separation ile aynı gelenek).
        separation_factor: Summerfield k'sı; ``None`` → ithal edilen
            varsayılan (0,40). Bant denetimi ithal edilen MIN/MAX ile.

    Returns:
        dict — anahtarlar (uçtan/panelden tüketilecek sözleşme):
            applicable, separated, separation_index, separation_z_m,
            separation_wall_pressure_Pa, separation_z_interp_m,
            separated_length_m, separated_length_fraction,
            divergent_length_m, stations_below_threshold,
            stations_in_search_domain, reattachment_suspected,
            wall_pressure_min_Pa, wall_pressure_exit_Pa,
            wall_pressure_margin_min (min p_w / eşik; < 1 → ayrılma),
            threshold_Pa, separation_factor, separation_factor_source,
            ambient_pressure_Pa, criterion, criterion_basis,
            search_domain_basis, throat_index, throat_index_basis,
            converged, judgment_confidence, judgment_basis,
            solver_convergence_basis, length_basis, station_basis,
            reattachment_basis (yalnız şüphe varsa), not_applicable_reason
            (yalnız vakumda), not_modelled, inputs.

    Raises:
        ValueError: P_ambient_Pa eksik/negatif; k bant dışı; sonuç sözlüğü
            duvar basıncı sözleşmesini taşımıyor ya da tutarsız.
    """
    if not isinstance(result, dict):
        raise ValueError(
            'result, solve_steady_axisym\'ın döndürdüğü sözlük olmalı.')
    if P_ambient_Pa is None:
        raise ValueError(
            'P_ambient_Pa zorunludur: ayrılma ölçütü p_w < k·P_ortam ortam '
            'basıncına göre tanımlıdır ve varsayılan bir ortam basıncı '
            '(deniz seviyesi ya da vakum) UYDURMA sayılır — çağıran uçuş '
            'irtifasının basıncını vermelidir.')
    try:
        p_amb = float(P_ambient_Pa)
    except (TypeError, ValueError):
        raise ValueError(
            f'P_ambient_Pa sayısal olmalı [Pa]; gelen: {P_ambient_Pa!r}.')
    if not np.isfinite(p_amb) or p_amb < 0.0:
        raise ValueError(
            f'P_ambient_Pa sonlu ve negatif olmayan olmalı [Pa]; gelen '
            f'{p_amb!r}.')

    if 'converged' not in result:
        raise ValueError(
            'CFD sonucunda \'converged\' yok: hüküm/doğrulama ayrımı gereği '
            'yakınsama beyanı OLMADAN ayrılma hükmü verilmez.')
    converged = bool(result['converged'])
    solver_basis = str(result.get('convergence_basis', ''))

    p_wall = _as_wall_array(result, 'wall_pressure_Pa', 'duvar basıncı [Pa]')
    z_wall = _as_wall_array(result, 'wall_pressure_z_m', 'duvar ekseni [m]')
    if p_wall.shape != z_wall.shape:
        raise ValueError(
            f'wall_pressure_Pa {p_wall.shape} ile wall_pressure_z_m '
            f'{z_wall.shape} aynı uzunlukta değil (sözleşme ihlali).')
    if np.any(p_wall <= 0.0):
        raise ValueError(
            'wall_pressure_Pa pozitif olmalı (fiziksel olmayan basınç) — '
            'ayrılma hükmü verilmez.')
    if not np.all(np.diff(z_wall) > 0.0):
        raise ValueError(
            'wall_pressure_z_m kesin artan değil: istasyon sırası bozuk, '
            'ilk ayrılma istasyonu tanımsız olurdu.')

    i_throat, throat_basis = _resolve_throat_index(result, z_wall)
    threshold_ratio, factor_source = _resolve_factor(separation_factor)
    threshold = threshold_ratio * p_amb

    confidence = 'firm' if converged else 'suspect'
    judgment_basis = (
        'Çözücü yakınsadı (converged=True): hüküm oturmuş alana ait.'
        if converged else
        'ÇÖZÜCÜ YAKINSAMADI (converged=False): hüküm ŞÜPHELİ — ölçüt '
        'oturmamış bir duvar basıncı dağılımına uygulandı. Sonuç gizlenmez '
        'ama sağlam sunulmaz; kullanmadan önce çözücünün kendi beyanına '
        'bakın (solver_convergence_basis).')

    criterion_basis = (
        f'Summerfield (1954) ayrılma ölçütü: p_w < k·P_ortam, '
        f'k = {threshold_ratio:.3f} ({"varsayılan" if factor_source == "default" else "çağıranın verdiği"} '
        f'değer; sabitin tek kaynağı hrma.analysis.nozzle_flow_1d, '
        f'literatür bandı 0,35-0,40, kabul bandı '
        f'[{SEPARATION_FACTOR_MIN}, {SEPARATION_FACTOR_MAX}]). '
        f'Eşik = {threshold:.6g} Pa (P_ortam = {p_amb:.6g} Pa). '
        f'Kaynak: Summerfield, Foster & Swan, Jet Propulsion 24 (1954); '
        f'Sutton & Biblarz, 9. baskı, Böl. 3. Duvar basıncı 2B Euler '
        f'çözümünün duvara komşu hücrelerinden ÖLÇÜLDÜ '
        f'(wall_pressure_basis), izantropik yarı-1B temsille DEĞİL.')

    z_throat = float(z_wall[i_throat])
    z_exit = float(z_wall[-1])
    divergent_length = z_exit - z_throat

    out = {
        'applicable': True,
        'separated': False,
        'separation_index': None,
        'separation_z_m': None,
        'separation_wall_pressure_Pa': None,
        'separation_z_interp_m': None,
        'separated_length_m': 0.0,
        'separated_length_fraction': 0.0,
        'divergent_length_m': divergent_length,
        'stations_below_threshold': 0,
        'reattachment_suspected': False,
        'threshold_Pa': float(threshold),
        'separation_factor': float(threshold_ratio),
        'separation_factor_source': factor_source,
        'ambient_pressure_Pa': p_amb,
        'criterion': CRITERION_SUMMERFIELD,
        'criterion_basis': criterion_basis,
        'search_domain_basis': _SEARCH_DOMAIN_BASIS,
        'station_basis': _Z_INTERP_BASIS,
        'length_basis': _LENGTH_BASIS,
        'throat_index': int(i_throat),
        'throat_index_basis': throat_basis,
        'throat_z_m': z_throat,
        'exit_z_m': z_exit,
        'converged': converged,
        'judgment_confidence': confidence,
        'judgment_basis': judgment_basis,
        'solver_convergence_basis': solver_basis,
        'not_modelled': _not_modelled(),
        'inputs': {
            'P_ambient_Pa': p_amb,
            'separation_factor': float(threshold_ratio),
            'wall_stations': int(p_wall.size),
            '_basis': 'Çağıranın verdiği girdilerin yankısı (SI).',
        },
    }

    # Vakum: ölçüt P_ortam'a göre tanımlı; hüküm verilmez (uydurma yerine
    # açık beyan — hrma.flow.separation ile aynı gelenek).
    if p_amb <= 0.0:
        out.update({
            'applicable': False,
            'stations_in_search_domain': int(p_wall.size - i_throat - 1),
            'wall_pressure_min_Pa': float(np.min(p_wall[i_throat + 1:]))
                                    if p_wall.size > i_throat + 1 else None,
            'wall_pressure_exit_Pa': float(p_wall[-1]),
            'wall_pressure_margin_min': None,
            'not_applicable_reason': (
                'Vakumda (P_ortam = 0) aşırı genleşme ve ayrılma tanımsızdır: '
                'eşik k·P_ortam = 0 olur, hiçbir sonlu duvar basıncı altına '
                'inemez. Ayrılma hükmü VERİLMEDİ (0 Pa eşikle "ayrılma yok" '
                'demek yanıltıcı olurdu).'),
        })
        return out

    p_div = p_wall[i_throat + 1:]
    if p_div.size == 0:
        raise ValueError(
            f'Boğaz index\'i {i_throat} son istasyonda: ıraksak bölgede '
            f'aranacak istasyon kalmıyor (ızgara ya da boğaz tespiti bozuk).')

    below = p_div < threshold
    out['stations_in_search_domain'] = int(p_div.size)
    out['stations_below_threshold'] = int(np.count_nonzero(below))
    out['wall_pressure_min_Pa'] = float(np.min(p_div))
    out['wall_pressure_exit_Pa'] = float(p_wall[-1])
    out['wall_pressure_margin_min'] = float(np.min(p_div) / threshold)

    if not np.any(below):
        return out

    k0 = int(np.argmax(below))          # ıraksak dilimde ilk True
    j = i_throat + 1 + k0               # genel index
    out['separated'] = True
    out['separation_index'] = int(j)
    out['separation_z_m'] = float(z_wall[j])
    out['separation_wall_pressure_Pa'] = float(p_wall[j])

    # Alt-hücre kestirimi: eşiğin geçildiği yer, ayrılan istasyon ile bir
    # önceki (eşiğin ÜSTÜNDEKİ) istasyon arasında doğrusal ara değerle.
    if j > 0 and p_wall[j - 1] > threshold:
        dp = p_wall[j] - p_wall[j - 1]
        frac = (threshold - p_wall[j - 1]) / dp
        out['separation_z_interp_m'] = float(
            z_wall[j - 1] + frac * (z_wall[j] - z_wall[j - 1]))
    else:
        # İlk ıraksak istasyon zaten eşiğin altında: bracket yok, kestirim
        # yapılmaz (uydurma yerine None + istasyon değeri kalır).
        out['separation_z_interp_m'] = None

    sep_len = z_exit - float(z_wall[j])
    out['separated_length_m'] = float(sep_len)
    out['separated_length_fraction'] = (
        float(sep_len / divergent_length) if divergent_length > 0.0 else None)

    # Ayrılma istasyonunun aşağısında eşiğin üstüne geri çıkış var mı?
    if np.any(~below[k0:]):
        out['reattachment_suspected'] = True
        out['reattachment_basis'] = _REATTACH_BASIS

    return out
