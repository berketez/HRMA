# hrma/cfd — CFD duvar basıncı/kayma gerilmesi → ayrılma hükmü köprüsü
"""
2B eksenel simetrik çözümün duvar dizilerinden ayrılma hükmü.

V4 EKİ — DÖRT ÜYE (tasarım §8.3; bu bölüm 2026-08-19'da eklendi)
----------------------------------------------------------------
Aşama 1B'de bu köprü YALNIZ Summerfield ölçütünü uyguluyordu. Artık aynı
çıktıda DÖRT üye durur (``criteria``, ``SEPARATION_CRITERIA`` sırasıyla):

  summerfield / schmucker / kalt_badal  — AMPİRİK basınç ölçütleri; eşik
      bağıntıları ``hrma.flow.separation``ın TEK kaynağından ithal edilir
      (ikinci gerçekleme yazılmadı). Schmucker eşiği yerel Mach'a bağlı
      olduğundan istasyon başına kurulur; yereldeki Mach, sınır tabakası
      yaklaşımı (∂p/∂n ≈ 0) gereği ÖLÇÜLEN duvar basıncından izantropik
      olarak çıkarılır.
  cfd_tau_w  — HESAPLANMIŞ üye: viskoz çözümde τ_w'nin işaret değiştirdiği
      istasyon. Ampirik bir eşik DEĞİL, ayrılmanın TANIMIDIR. Yalnız
      VİSKOZ koşuda vardır; Euler koşusunda duvar kaymalıdır (τ_w ≡ 0) ve
      bu üye UYDURULMAZ (``available=False`` + gerekçe).

``criteria_spread`` üyeler arası farkı taşır (kim ayrılma dedi, konumlar ne
kadar ayrıştı, CFD ile ampirik üyeler arasındaki mesafe). Üyelerin
ÇELİŞMESİ beklenen bir durumdur ve gizlenmez: ampirik üçlü türbülanslı
deneylerden kalibrelidir, CFD üyesi ise koşumun kendi fiziğidir.

ÜST DÜZEY (DÜZ) ALANLAR GERİYE UYUMLUDUR ve Summerfield üyesinin ta
kendisidir: ölçüt aritmetiği tek yerdedir (``_threshold_member``) ve düz
alanlar oradan DOLDURULUR — iki hesap sessizce ayrışamaz (yapısal bekçi:
tests/cfd/test_ayrilma.py::test_duz_alanlar_UYENIN_KENDISINDEN_doluyor_
YAPISAL).

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
SUNULMAZ: ``judgment_confidence='suspect'`` (çözücü YAKINSAMADI) ya da
``'not_evaluated'`` (çözücü hükmü YARGILAMADI, converged=None — OH-D31-15)
ve ``judgment_basis`` çözücünün
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
    SUMMERFIELD_FACTOR_ACCEPT_BAND,
    SUMMERFIELD_FACTOR_BAND,
    CRITERION_KALT_BADAL,
    CRITERION_SCHMUCKER,
    CRITERION_SUMMERFIELD,
    SEPARATION_NOT_MODELLED,
    kalt_badal_pressure_ratio,
    schmucker_pressure_ratio,
    summerfield_pressure_ratio,
)

#: Dördüncü, HESAPLANMIŞ üye (tasarım §8.3): ayrılma başlangıcı τ_w'nin
#: işaret değiştirdiği istasyondur — ampirik eşik değil, TANIM.
CRITERION_CFD_TAU_W = 'cfd_tau_w'

__all__ = ['assess_separation', 'SEPARATION_FACTOR_DEFAULT',
           'SEPARATION_FACTOR_MIN', 'SEPARATION_FACTOR_MAX',
           'CRITERION_SUMMERFIELD', 'CRITERION_SCHMUCKER',
           'CRITERION_KALT_BADAL', 'CRITERION_CFD_TAU_W',
           'SEPARATION_CRITERIA']

#: Çıktıdaki ``criteria`` sözlüğünün üye sırası (beyan; hüküm değil).
SEPARATION_CRITERIA = (CRITERION_SUMMERFIELD, CRITERION_SCHMUCKER,
                       CRITERION_KALT_BADAL, CRITERION_CFD_TAU_W)

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

_CFD_RELIABILITY_BASIS = (
    'GÜVEN ETİKETİ: model bağımlı (tasarım §8.3 + §13 soru 7). τ_w = 0 '
    'istasyonu ampirik bir eşik DEĞİL, ayrılmanın TANIMIDIR; ama onu '
    'üreten çözüm bir modeldir. Laminer koşuda kapanış yoktur (doğrudan '
    'Navier-Stokes), türbülanslı koşuda ise ayrılma noktası TÜRBÜLANS '
    'MODELİNE duyarlıdır ve şok-sınır tabakası etkileşiminde tek '
    'denklemli modeller ayrılmayı tipik olarak GEÇ öngörür. Bu üye '
    'ampirik üçlünün yerine GEÇMEZ; yanlarında durur ve farkları '
    'criteria_spread ile yayımlanır.')

_EMPIRICAL_RELIABILITY_BASIS = (
    'GÜVEN ETİKETİ: ampirik korelasyon. Eşik, TÜRBÜLANSLI sınır tabakalı '
    'aşırı genleşmiş lüle deneylerinden kalibre edilmiştir; duvar basıncı '
    'ise bu koşumda 2B çözümden ÖLÇÜLMÜŞTÜR. Korelasyonun kendi geçerlilik '
    'bandı dışındaki rejimlerde (laminer, düşük Reynolds, güçlü iç şok) '
    'hükmü CFD üyesinden ayrışabilir — ayrışma criteria_spread ile '
    'GÖRÜLÜR, gizlenmez.')

_CRITERIA_BASIS = (
    'Dört üye AYNI çözümün duvar dizilerine uygulandı ve AYNI arama '
    'bölgesinde (boğazın bir sonrasından çıkışa) arandı. Üçü ampirik '
    'basınç ölçütüdür (eşikleri hrma.flow.separation\'ın TEK '
    'kaynağından: summerfield/schmucker/kalt_badal_pressure_ratio — '
    'ikinci gerçekleme yazılmadı); dördüncüsü viskoz çözümün τ_w işaret '
    'değişimidir ve ancak VİSKOZ koşuda vardır. Viskoz koşu yoksa '
    'dördüncü üye UYDURULMAZ: available=False + gerekçe. Üst düzey '
    '(düz) alanlar GERİYE UYUM için Summerfield üyesinin ta kendisidir; '
    'criteria[\'summerfield\'] ile aynı hesaptan gelir (tek gerçekleme).')


def _empty_member(name, kind, reason=None):
    """Üye şeması — dört üye de AYNI anahtarları taşır (yanyana okunsun)."""
    return {
        'criterion': name,
        'basis_kind': kind,
        'available': reason is None,
        'not_available_reason': reason,
        'separated': False,
        'separation_index': None,
        'separation_z_m': None,
        'separation_z_interp_m': None,
        'separation_wall_pressure_Pa': None,
        'separated_length_m': 0.0,
        'separated_length_fraction': 0.0,
        'stations_below_threshold': 0,
        'reattachment_suspected': False,
        'threshold_Pa': None,
        'threshold_min_Pa': None,
        'threshold_max_Pa': None,
        'margin_min': None,
        #: ``margin_min`` HANGİ büyüklüktür ve KRİTİK DEĞERİ nedir?
        #: (ÖH defter P6B3-12: eskiden bu anahtar ampirik üyelerde
        #: p_w/eşik — kritik değer 1 — CFD üyesinde ise min(τ)/maks|τ|
        #: — kritik değer 0 — taşıyordu; yapışık bir koşuda CFD üyesi
        #: 0,2636 yayımlıyordu ve "1'in altında" diye okunduğunda
        #: AYRILMIŞ gibi görünüyordu. Artık ``margin_min`` TEK
        #: büyüklüktür: ölçüt niceliğinin EŞİĞİNE oranı, kritik değer
        #: 1. Tanımsız olduğu üyede None'dır, uydurulmaz.)
        'margin_kind': None,
        'margin_basis': None,
        'validity_warning': None,
        #: Ölçüt KENDİ türetim/literatür bandının dışında mı? (ÖH defter
        #: P6B3-03) Makine-okur ikizi ``validity_warning``ın kendisidir;
        #: tüketici metin ayrıştırmak zorunda kalmasın diye ayrı alan.
        'outside_validity_band': False,
        'reliability': None,
        'reliability_basis': None,
    }


def _threshold_member(name, p_wall, z_wall, i_throat, threshold,
                      divergent_length, kind='empirical_wall_pressure'):
    """Eşik ölçütünün TEK gerçeklemesi: ilk ayrılma istasyonu + beyan.

    ``threshold`` skaler (Summerfield, Kalt-Badal) ya da ıraksak dilimle
    aynı uzunlukta dizi (Schmucker — eşik yerel Mach'a bağlı) olabilir.
    Üst düzey düz alanlar da BU çıktıdan doldurulur; ölçüt aritmetiği
    depoda tek yerde durur.
    """
    m = _empty_member(name, kind)
    m['reliability'] = 'empirical_correlation'
    m['reliability_basis'] = _EMPIRICAL_RELIABILITY_BASIS
    p_div = p_wall[i_throat + 1:]
    esik = np.asarray(threshold, dtype=float)
    if esik.ndim == 0:
        m['threshold_Pa'] = float(esik)
    m['threshold_min_Pa'] = float(np.min(esik))
    m['threshold_max_Pa'] = float(np.max(esik))

    below = p_div < esik
    m['stations_below_threshold'] = int(np.count_nonzero(below))
    # Pay: yalnız eşiği TANIMLI olan istasyonlar. Schmucker'da tanımsız
    # istasyonların eşiği +sonsuzdur; oraya 0 payı yazmak "eşiğin çok
    # altında" gibi okunurdu (sessiz yanlış beyan).
    sonlu = np.isfinite(esik)
    if np.any(sonlu):
        oran = np.where(sonlu, p_div / np.where(sonlu, esik, 1.0), np.inf)
        m['margin_min'] = float(np.min(oran))
        m['margin_kind'] = 'wall_pressure_over_threshold'
        m['margin_basis'] = (
            'min(p_w / eşik) ıraksak dilimde; BİRİMSİZ ve KRİTİK DEĞERİ '
            '1\'dir: < 1 olan istasyon eşiğin altındadır, yani bu ölçüte '
            'göre AYRILMIŞTIR. Pay yalnız eşiği TANIMLI olan '
            'istasyonlardan alınır (Schmucker\'da tanımsız istasyonun '
            'eşiği +sonsuzdur).')
    if not np.any(below):
        return m

    k0 = int(np.argmax(below))          # ıraksak dilimde ilk True
    j = i_throat + 1 + k0               # genel index
    esik_j = float(esik) if esik.ndim == 0 else float(esik[k0])
    m['separated'] = True
    m['separation_index'] = int(j)
    m['separation_z_m'] = float(z_wall[j])
    m['separation_wall_pressure_Pa'] = float(p_wall[j])

    # Alt-hücre kestirimi: eşiğin geçildiği yer, ayrılan istasyon ile bir
    # önceki (eşiğin ÜSTÜNDEKİ) istasyon arasında doğrusal ara değerle.
    if j > 0 and p_wall[j - 1] > esik_j:
        dp = p_wall[j] - p_wall[j - 1]
        frac = (esik_j - p_wall[j - 1]) / dp
        m['separation_z_interp_m'] = float(
            z_wall[j - 1] + frac * (z_wall[j] - z_wall[j - 1]))
    # aksi hâlde bracket yok: kestirim YAPILMAZ (None kalır, uydurma yok)

    sep_len = float(z_wall[-1]) - float(z_wall[j])
    m['separated_length_m'] = sep_len
    m['separated_length_fraction'] = (
        float(sep_len / divergent_length) if divergent_length > 0.0 else None)
    if np.any(~below[k0:]):
        m['reattachment_suspected'] = True
    return m


def _isentropic_wall_mach(p_wall, P0, gamma):
    """Duvar basıncından izantropik yerel Mach (Schmucker'ın M'i).

    Schmucker eşiği YEREL Mach'a bağlıdır. 2B çözümde duvara komşu hücre
    ses-altıdır (no-slip); ölçütün istediği M, sınır tabakasının KENARINDAKİ
    (çekirdek) Mach'tır ve sınır tabakası yaklaşımı gereği (∂p/∂n ≈ 0) o
    da duvar basıncından izantropik olarak kurulur — yarı-1B sürümün
    (hrma.flow.separation._criterion_schmucker) yaptığının ta kendisi,
    orada alan oranından, burada ÖLÇÜLEN duvar basıncından.
    """
    oran = np.power(P0 / p_wall, (gamma - 1.0) / gamma) - 1.0
    return np.sqrt(np.maximum(oran, 0.0) * 2.0 / (gamma - 1.0))


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
        # BOĞAZ İMZASI KAPISI (ÖH defter P6B1-07) — bu kapı YOKTU.
        # Ayrılma hükmü boğazın IRAKSAK tarafında aranır (p_wall[i+1:]);
        # son istasyon kapısı aşağıda vardı ama GİRİŞ tarafındaki
        # kardeşi yoktu. Salt ıraksak bir konturda çözücünün kolon
        # minimumu i=0'a düşer (ölçüldü, D17 fea-cfd once.json) ve
        # köprü tüm alanı "ıraksak bölge" sayıp ayrılma hükmü
        # yayımlıyordu — oysa o alanda boğaz YOKTUR. Çözücü artık
        # boğaz İDDİASINI throat['interior'] ile beyan ediyor; iddia
        # yoksa hüküm verilmez (fail-closed, uydurma boğaz konmaz).
        if throat.get('interior') is False:
            raise ValueError(
                f"throat['interior'] = False: çözücü i={i_t} kolonunu "
                'BOĞAZ olarak İDDİA ETMİYOR (alan minimumu uç kolonda, '
                'kontur o alanda tek yönlü). Ayrılma hükmü boğazın '
                'ıraksak tarafında aranır; boğaz iddiası olmadan arama '
                'alanı tanımsızdır ve uydurma bir boğaz konumu '
                'varsayılmaz. Çözücünün beyanı: '
                f"{throat.get('interior_basis')}")
        return i_t, ('Boğaz index\'i çözücünün yayımladığı throat[\'i\'] '
                     'alanından alındı'
                     + (' (throat[\'interior\'] = True: çözücü bu kolonu '
                        'boğaz olarak İDDİA EDİYOR).'
                        if throat.get('interior') is True else
                        '; çözücü boğaz imzası (throat[\'interior\']) '
                        'YAYIMLAMIYOR — eski sürüm sonucu, imza '
                        'sınanamadı.'))

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


#: İKİ kabul bandının ÇAPRAZ DENETİMİ (ÖH defter P6B3-03 — SÜRÜKLENME
#: KAPISI). Eski kapı ``summerfield_pressure_ratio(factor)``ı çağırıp
#: sonucu k ile karşılaştırmıyordu; o fonksiyon k'yı OLDUĞU GİBİ döndürdüğü
#: için "ikinci doğrulama" TOTOLOJİKTİ — ölçüldü (a2/once.json): 0,20-0,60
#: arasında 800 değerde ATEŞ SAYISI 0. Gerçek sürüklenme riski iki AYRI
#: modüldeki bant ikizinin ayrışmasıydı; kapı artık ONU ölçer ve ithal
#: anında (koşum başlamadan) patlar.
if (float(SEPARATION_FACTOR_MIN),
        float(SEPARATION_FACTOR_MAX)) != tuple(
            float(v) for v in SUMMERFIELD_FACTOR_ACCEPT_BAND):
    raise ImportError(
        'Ayrılma katsayısı kabul bandı İKİ kaynakta ayrışmış: '
        f'hrma.analysis.nozzle_flow_1d = [{SEPARATION_FACTOR_MIN}, '
        f'{SEPARATION_FACTOR_MAX}], hrma.flow.separation = '
        f'{tuple(SUMMERFIELD_FACTOR_ACCEPT_BAND)}. Tek kaynak kuralı '
        'ihlali — ölçüt aritmetiği iki farklı bant altında koşamaz.')


def _resolve_factor(separation_factor):
    """k katsayısı, kaynağı ('default' | 'caller') ve GEÇERLİLİK beyanı.

    Döner: ``(k, kaynak, validity_warning_or_None)``.

    Kabul bandı [0,20; 0,60] kullanıcı deneyleri için LİTERATÜR bandından
    (0,35-0,40) geniştir; ÖH defter P6B3-03'te ölçülen kusur bandın
    genişliği DEĞİL, geniş banttaki bir k'nın **sessizce** yayımlanmasıydı:
    k = 0,60 (literatür bandının 1,5 katı) eşiği 40.000 -> 60.000 Pa'ya
    taşıyıp ayrılan istasyonu 46 -> 43'e çekerken ``validity_warning`` None
    kalıyordu — kardeş ``hrma.flow.separation`` AYNI k'da uyarı verirken.
    """
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
            f'(Summerfield literatür bandı {SUMMERFIELD_FACTOR_BAND[0]}-'
            f'{SUMMERFIELD_FACTOR_BAND[1]}; bant sabitleri '
            f'hrma.analysis.nozzle_flow_1d\'den ithal edilir).')
    uyari = None
    if not (SUMMERFIELD_FACTOR_BAND[0] <= factor
            <= SUMMERFIELD_FACTOR_BAND[1]):
        uyari = (
            f'Seçilen eşik {factor:.2f}, literatür bandının '
            f'({SUMMERFIELD_FACTOR_BAND[0]:.2f}-'
            f'{SUMMERFIELD_FACTOR_BAND[1]:.2f}) dışında.')
    return float(summerfield_pressure_ratio(factor)), source, uyari


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

            **V4 EKİ (tasarım §8.3) — dört üyeli karşılaştırma:**
            ``criteria`` (``SEPARATION_CRITERIA`` sırasıyla summerfield /
            schmucker / kalt_badal / cfd_tau_w; hepsi AYNI şemada, üye
            kurulamıyorsa ``available=False`` + ``not_available_reason``),
            ``criteria_spread`` (kim ayrılma dedi, konum farkları),
            ``criteria_basis``. Üst düzey DÜZ alanlar geriye uyum için
            Summerfield üyesinin ta kendisidir ve ondan doldurulur.

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
    # ÜÇ DURUMLU HÜKÜM (OH-D31-15): çözücü ``None`` döndürdüyse hüküm
    # YARGILANMAMIŞTIR. ``bool()`` burada 'değerlendirilmedi'yi
    # 'yakınsamadı' yapardı — ikisi ayrı şeydir ve ayrı yayımlanır.
    _solver_verdict = result['converged']
    converged = (None if _solver_verdict is None else bool(_solver_verdict))
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
    (threshold_ratio, factor_source,
     factor_validity_warning) = _resolve_factor(separation_factor)
    threshold = threshold_ratio * p_amb

    # GÜVEN ETİKETİ ÜÇ DEĞERLİ (OH-D31-15 / Berke kararı 15 Eyl 2026 §3):
    # 'firm' YALNIZ çözücü hükmü VERDİYSE. Hüküm yargılanmadıysa etiket
    # 'not_evaluated'tır; 'suspect' ÖLÇÜLMÜŞ bir yakınsamama hükmüne
    # ayrılmıştır ve ikisi karıştırılmaz (biri "alan oturmadı" der, öteki
    # "oturup oturmadığına bakılmadı" der).
    if converged is True:
        confidence = 'firm'
        judgment_basis = (
            'Çözücü yakınsadı (converged=True): hüküm oturmuş alana ait.')
    elif converged is None:
        confidence = 'not_evaluated'
        judgment_basis = (
            'ÇÖZÜCÜ HÜKÜM VERMEDİ (converged=None, convergence_status='
            'not_evaluated): yakınsama için gerekli değerlendirme bu koşuda '
            'YAPILMADI — öz-tutarlılık kapısı koşuyu kapsamıyor. Ayrılma '
            'ölçütü yine de uygulandı ve sayıları gizlenmiyor, ama bu hüküm '
            'SAĞLAM sunulamaz: dayandığı alanın yakınsadığı '
            'KANITLANMAMIŞTIR. "Yakınsamadı" da denmiyor — yargılanmadı '
            'deniyor; çözücünün kendi beyanına bakın '
            '(solver_convergence_basis).')
    else:
        confidence = 'suspect'
        judgment_basis = (
            'ÇÖZÜCÜ YAKINSAMADI (converged=False): hüküm ŞÜPHELİ — ölçüt '
            'oturmamış bir duvar basıncı dağılımına uygulandı. Sonuç '
            'gizlenmez ama sağlam sunulmaz; kullanmadan önce çözücünün '
            'kendi beyanına bakın (solver_convergence_basis).')

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
        'validity_warning': factor_validity_warning,
        'outside_validity_band': bool(factor_validity_warning),
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
        # Dört üye de VAKUMDA tanımsızdır (üçü P_ortam'a bağlı eşiklidir,
        # dördüncüsü ise ayrılma KAVRAMININ tanımsız olduğu bir akışta
        # hüküm veremez): üyeler UYDURULMAZ, gerekçeli olarak yok sayılır.
        vakum = ('Vakumda (P_ortam = 0) ayrılma tanımsızdır; hiçbir ölçüt '
                 'üyesi hüküm vermez.')
        out['criteria'] = {ad: _empty_member(
            ad, ('computed_wall_shear' if ad == CRITERION_CFD_TAU_W
                 else 'empirical_wall_pressure'), vakum)
            for ad in SEPARATION_CRITERIA}
        out['criteria_spread'] = _criteria_spread(out['criteria'])
        out['criteria_basis'] = _CRITERIA_BASIS
        return out

    p_div = p_wall[i_throat + 1:]
    if p_div.size == 0:
        raise ValueError(
            f'Boğaz index\'i {i_throat} son istasyonda: ıraksak bölgede '
            f'aranacak istasyon kalmıyor (ızgara ya da boğaz tespiti bozuk).')

    out['stations_in_search_domain'] = int(p_div.size)
    out['wall_pressure_min_Pa'] = float(np.min(p_div))
    out['wall_pressure_exit_Pa'] = float(p_wall[-1])

    # --- Summerfield üyesi: ölçüt aritmetiğinin TEK gerçeklemesi ---------
    # Üst düzey (düz) alanlar bu üyeden DOLDURULUR; ikinci bir arama
    # döngüsü yazılmaz, dolayısıyla düz alanlarla criteria['summerfield']
    # sessizce ayrışamaz (yapısal eşitlik, bekçili).
    m_sum = _threshold_member(CRITERION_SUMMERFIELD, p_wall, z_wall,
                              i_throat, threshold, divergent_length)
    # GEÇERLİLİK BEYANI (ÖH defter P6B3-03): kabul bandı literatür
    # bandından geniştir; bandın dışındaki k SESSİZ kalamaz. Sayı
    # gizlenmez — hüküm ADIYLA "dışkestirim" der (kardeş
    # hrma.flow.separation ile AYNI cümle, tek gerçekleme oradaki
    # SUMMERFIELD_FACTOR_BAND sabitidir).
    m_sum['validity_warning'] = factor_validity_warning
    m_sum['outside_validity_band'] = bool(factor_validity_warning)
    out['validity_warning'] = factor_validity_warning
    out['outside_validity_band'] = bool(factor_validity_warning)
    out['stations_below_threshold'] = m_sum['stations_below_threshold']
    out['wall_pressure_margin_min'] = m_sum['margin_min']
    for duz, uye in (('separated', 'separated'),
                     ('separation_index', 'separation_index'),
                     ('separation_z_m', 'separation_z_m'),
                     ('separation_wall_pressure_Pa',
                      'separation_wall_pressure_Pa'),
                     ('separation_z_interp_m', 'separation_z_interp_m'),
                     ('separated_length_m', 'separated_length_m'),
                     ('separated_length_fraction', 'separated_length_fraction'),
                     ('reattachment_suspected', 'reattachment_suspected')):
        out[duz] = m_sum[uye]
    if m_sum['reattachment_suspected']:
        out['reattachment_basis'] = _REATTACH_BASIS

    out['criteria'] = _build_criteria(result, m_sum, p_wall, z_wall, i_throat,
                                      p_amb, divergent_length)
    out['criteria_spread'] = _criteria_spread(out['criteria'])
    out['criteria_basis'] = _CRITERIA_BASIS
    return out


# ---------------------------------------------------------------------------
# Dört üyeli karşılaştırma (tasarım §8.3)
# ---------------------------------------------------------------------------

def _build_criteria(result, summerfield_member, p_wall, z_wall, i_throat,
                    p_amb, divergent_length):
    """Summerfield / Schmucker / Kalt-Badal / CFD-τ_w üyeleri, aynı şemada."""
    criteria = {CRITERION_SUMMERFIELD: summerfield_member}

    inputs = result.get('inputs') if isinstance(result, dict) else None
    P0 = None if not isinstance(inputs, dict) else inputs.get('P0_Pa')
    gamma = None if not isinstance(inputs, dict) else inputs.get('gamma')
    eksik = None
    if P0 is None or gamma is None:
        eksik = (
            'Sonuç sözlüğü inputs[\'P0_Pa\'] / inputs[\'gamma\'] yankısını '
            'taşımıyor. Schmucker eşiği YEREL Mach\'a, Kalt-Badal eşiği '
            'basınç oranına (P₀/P_ortam) bağlıdır; ikisi de rezervuar '
            'basıncı olmadan kurulamaz ve uydurma bir P₀ ile hüküm '
            'verilmez.')

    if eksik is not None:
        criteria[CRITERION_SCHMUCKER] = _empty_member(
            CRITERION_SCHMUCKER, 'empirical_wall_pressure', eksik)
        criteria[CRITERION_KALT_BADAL] = _empty_member(
            CRITERION_KALT_BADAL, 'empirical_wall_pressure', eksik)
    else:
        P0 = float(P0)
        gamma = float(gamma)
        # --- Schmucker: eşik istasyon başına (yerel Mach'a bağlı) --------
        p_div = p_wall[i_throat + 1:]
        mach_div = _isentropic_wall_mach(p_div, P0, gamma)
        gecerli = (1.88 * mach_div - 1.0) > 0.0
        if not np.any(gecerli):
            criteria[CRITERION_SCHMUCKER] = _empty_member(
                CRITERION_SCHMUCKER, 'empirical_wall_pressure',
                'Iraksak bölgenin hiçbir istasyonunda 1,88·M − 1 > 0 '
                'sağlanmıyor (M ≤ 0,532): Schmucker eşiği tanımsız. '
                'Ses-üstü olmayan bir ıraksak bölgede bu ölçüt '
                'kullanılmaz.')
        else:
            # Tanımsız istasyonlarda eşik +sonsuz alınır (o istasyonda
            # ölçüt "ayrılma yok" der) — kırpma değil, tanım gereği.
            esik = np.full(p_div.shape, np.inf)
            esik[gecerli] = p_amb * np.array(
                [schmucker_pressure_ratio(float(m))
                 for m in mach_div[gecerli]])
            m_sch = _threshold_member(CRITERION_SCHMUCKER, p_wall, z_wall,
                                      i_throat, esik, divergent_length)
            m_sch['threshold_max_Pa'] = (
                None if not np.any(np.isfinite(esik))
                else float(np.max(esik[np.isfinite(esik)])))
            m_sch['local_mach_min'] = float(np.min(mach_div))
            m_sch['local_mach_max'] = float(np.max(mach_div))
            if m_sch['separated'] and m_sch['separation_index'] is not None:
                m_i = float(mach_div[m_sch['separation_index'] - i_throat - 1])
                m_sch['mach_sep'] = m_i
                if not (1.5 <= m_i <= 4.5):
                    m_sch['validity_warning'] = (
                        f'Ayrılma Mach sayısı {m_i:.2f}, Schmucker türetim '
                        'bandının (1,5-4,5) dışında — dışkestirim.')
            m_sch['stations_undefined'] = int(np.count_nonzero(~gecerli))
            criteria[CRITERION_SCHMUCKER] = m_sch

        # --- Kalt-Badal: eşik sabit, basınç oranına bağlı ---------------
        npr = P0 / p_amb
        if npr <= 1.0:
            criteria[CRITERION_KALT_BADAL] = _empty_member(
                CRITERION_KALT_BADAL, 'empirical_wall_pressure',
                f'Basınç oranı P₀/P_ortam = {npr:.4g} ≤ 1: Kalt-Badal '
                'eşiği tanımsız (aşırı genleşme yok).')
        else:
            esik_kb = kalt_badal_pressure_ratio(npr) * p_amb
            m_kb = _threshold_member(CRITERION_KALT_BADAL, p_wall, z_wall,
                                     i_throat, esik_kb, divergent_length)
            m_kb['pressure_ratio_npr'] = float(npr)
            criteria[CRITERION_KALT_BADAL] = m_kb

    criteria[CRITERION_CFD_TAU_W] = _tau_wall_member(
        result, p_wall, z_wall, i_throat, divergent_length)
    return criteria


def _tau_wall_member(result, p_wall, z_wall, i_throat, divergent_length):
    """CFD-τ_w üyesi: viskoz çözümde τ_w'nin işaret değiştirdiği istasyon."""
    kind = 'computed_wall_shear'
    block = result.get('viscous') if isinstance(result, dict) else None
    if not isinstance(block, dict):
        return _empty_member(
            CRITERION_CFD_TAU_W, kind,
            'Bu koşu VİSKOZ DEĞİL (result[\'viscous\'] yok ya da None): '
            'duvar kayma gerilmesi hiç çözülmedi, τ_w = 0 istasyonu '
            'TANIMSIZDIR. Euler duvarı kaymalıdır (τ_w ≡ 0) ve ondan '
            'ayrılma istasyonu türetilmez — uydurma üye yayımlanmaz. '
            'Bu üyeyi doldurmak için ViscousOptions ile viskoz koşu '
            'gerekir.')
    if 'wall_shear_Pa' not in block or 'wall_z_m' not in block:
        return _empty_member(
            CRITERION_CFD_TAU_W, kind,
            'Viskoz blok wall_shear_Pa / wall_z_m sözleşmesini taşımıyor.')
    tau = np.asarray(block['wall_shear_Pa'], dtype=float)
    z_tau = np.asarray(block['wall_z_m'], dtype=float)
    if tau.shape != z_wall.shape:
        return _empty_member(
            CRITERION_CFD_TAU_W, kind,
            f'Viskoz duvar dizisi {tau.shape}, duvar basıncı ekseni '
            f'{z_wall.shape} ile aynı uzunlukta değil: iki dizi aynı '
            'istasyonlarda olmadan üyeler yan yana konamaz.')
    if not np.all(np.isfinite(tau)):
        return _empty_member(
            CRITERION_CFD_TAU_W, kind,
            'wall_shear_Pa sonlu olmayan değer içeriyor (ıraksamış '
            'viskoz koşu) — ayrılma istasyonu verilmez.')
    # EKSEN EŞ-KONUMLULUĞU (ölçülür, varsayılmaz). İki eksen AYNI ŞEY
    # DEĞİLDİR ve olmak zorunda da değildir: wall_pressure_z_m duvara
    # komşu HÜCRE MERKEZİNİN z'si, wall_z_m ise duvar YÜZÜNÜN orta
    # noktasıdır. Aynı kolonda ikisi yarım hücreden az ayrışır (ÖLÇÜLDÜ,
    # conftest lülesi: 64×16'da maks 11,4 µm = hücrenin %0,24'ü, 192×48'de
    # 1,26 µm). Kapı bunu ölçer: sapma yerel istasyon aralığının yarısını
    # aşıyorsa diziler aynı istasyonlara ait değildir ve üyeler yan yana
    # konamaz.
    aralik = np.empty_like(z_wall)
    aralik[0] = z_wall[1] - z_wall[0]
    aralik[-1] = z_wall[-1] - z_wall[-2]
    aralik[1:-1] = 0.5 * (z_wall[2:] - z_wall[:-2])
    sapma = np.abs(z_tau - z_wall)
    if np.any(sapma > 0.5 * aralik):
        return _empty_member(
            CRITERION_CFD_TAU_W, kind,
            'Viskoz duvar ekseni (wall_z_m) ile duvar basıncı ekseni '
            '(wall_pressure_z_m) aynı istasyonlara ait değil: maks sapma '
            f'{float(np.max(sapma)):.6g} m, yerel istasyon aralığının '
            'yarısını aşıyor. Farklı koşumların dizileri yan yana '
            'konmaz.')

    m = _empty_member(CRITERION_CFD_TAU_W, kind)
    m['axis_offset_max_m'] = float(np.max(sapma))
    m['axis_offset_basis'] = (
        'separation_z_m bu üyede DUVAR YÜZÜNÜN orta noktasıdır (τ_w orada '
        'ölçülür); ampirik üyelerinki duvara komşu HÜCRE MERKEZİDİR. '
        'İkisi arasındaki yarım-hücreden küçük kaymanın ölçülen değeri '
        'axis_offset_max_m ile yayımlanır — criteria_spread\'teki konum '
        'farkları okunurken bu taban gürültüsü bilinir.')
    m['reliability'] = 'model_dependent'
    m['reliability_basis'] = _CFD_RELIABILITY_BASIS
    m['threshold_Pa'] = 0.0
    m['threshold_min_Pa'] = 0.0
    m['threshold_max_Pa'] = 0.0
    m['tau_wall_min_Pa'] = float(np.min(tau))
    m['tau_wall_sign_changes_total'] = int(
        np.count_nonzero(np.diff(np.signbit(tau))))
    m['stations_negative_total'] = int(np.count_nonzero(tau < 0.0))

    tau_div = tau[i_throat + 1:]
    below = tau_div < 0.0
    m['stations_below_threshold'] = int(np.count_nonzero(below))
    tau_ref = float(np.max(np.abs(tau_div)))
    # ``margin_min`` BU ÜYEDE TANIMSIZDIR (ÖH defter P6B3-12): şemanın
    # margin'i ölçüt niceliğinin EŞİĞİNE oranıdır ve bu üyenin eşiği
    # SIFIRDIR — τ/0 tanımsız. Eskiden buraya min(τ)/maks|τ| yazılıyordu;
    # o BAŞKA bir büyüklüktür (kritik değeri 0) ve aynı anahtarda
    # yayımlandığında yapışık koşunun 0,2636'sı ampirik üyelerin
    # "1'in altı = ayrıldı" kuralıyla okunup YANLIŞ POZİTİF veriyordu.
    # Uydurulmaz: alan None kalır, gerekçesi yazılır, normalize edilmiş
    # kayma KENDİ adıyla ayrı alanda yayımlanır.
    m['margin_min'] = None
    m['margin_basis'] = (
        'Bu üyede TANIMSIZ: şemanın margin\'i ölçüt niceliğinin eşiğine '
        'oranıdır (kritik değer 1) ve bu üyenin eşiği τ_w = 0\'dır — '
        'sıfıra bölme. Ölçütün kendi payı tau_wall_min_over_max_abs ile '
        'yayımlanır; onun KRİTİK DEĞERİ 0\'dır (negatife düşen istasyon '
        'ayrılmıştır), 1 DEĞİL. İki sayı aynı anahtarda toplanmaz.')
    m['tau_wall_min_over_max_abs'] = (
        float(np.min(tau_div) / tau_ref) if tau_ref > 0.0 else None)
    m['tau_wall_margin_critical_value'] = 0.0
    if not np.any(below):
        return m

    k0 = int(np.argmax(below))
    j = i_throat + 1 + k0
    m['separated'] = True
    m['separation_index'] = int(j)
    m['separation_z_m'] = float(z_wall[j])
    m['separation_wall_pressure_Pa'] = float(p_wall[j])
    m['tau_wall_at_separation_Pa'] = float(tau[j])
    # τ_w = 0 kökü: işaret değişimini kuşatan iki istasyon arasında
    # doğrusal ara değer (alt-hücre kestirimi; ölçüt eşiği SIFIRDIR).
    if j > 0 and tau[j - 1] > 0.0:
        dtau = tau[j] - tau[j - 1]
        frac = (0.0 - tau[j - 1]) / dtau
        m['separation_z_interp_m'] = float(
            z_wall[j - 1] + frac * (z_wall[j] - z_wall[j - 1]))
    sep_len = float(z_wall[-1]) - float(z_wall[j])
    m['separated_length_m'] = sep_len
    m['separated_length_fraction'] = (
        float(sep_len / divergent_length) if divergent_length > 0.0 else None)
    if np.any(~below[k0:]):
        m['reattachment_suspected'] = True
    return m


def _criteria_spread(criteria):
    """Üyeler arası fark alanı: kim ayrılma dedi, konumlar ne kadar ayrıştı."""
    ayrilan = [ad for ad in SEPARATION_CRITERIA
               if criteria[ad]['available'] and criteria[ad]['separated']]
    ayrilmayan = [ad for ad in SEPARATION_CRITERIA
                  if criteria[ad]['available'] and not criteria[ad]['separated']]
    yok = [ad for ad in SEPARATION_CRITERIA if not criteria[ad]['available']]
    z = {ad: criteria[ad]['separation_z_m'] for ad in SEPARATION_CRITERIA}
    z_ayrilan = [z[ad] for ad in ayrilan if z[ad] is not None]
    cfd = criteria[CRITERION_CFD_TAU_W]
    fark = {}
    if cfd['available'] and cfd['separated']:
        for ad in (CRITERION_SUMMERFIELD, CRITERION_SCHMUCKER,
                   CRITERION_KALT_BADAL):
            uye = criteria[ad]
            fark[ad] = (float(cfd['separation_z_m'] - uye['separation_z_m'])
                        if uye['available'] and uye['separated'] else None)
    return {
        'members_separated': ayrilan,
        'members_attached': ayrilmayan,
        'members_unavailable': yok,
        'members_available_count': len(ayrilan) + len(ayrilmayan),
        # HEMFİKİRLİK EN AZ İKİ HÜKÜM İSTER (ÖH defter P6B3-07). Eskiden
        # ifade ``len(ayrilan) == 0 or len(ayrilmayan) == 0`` idi ve
        # HİÇBİR üye hüküm vermediğinde (dördü de available=False, ör.
        # P_ambient_Pa = 0 vakumunda) ikisi de boş olduğu için True
        # dönüyordu: "ölçütler hemfikir" diye okunan bir hüküm, hiçbir
        # ölçüt konuşmamışken. Fail-closed: hüküm kazanılmadıysa
        # yayımlanmaz (None), gerekçesi unanimous_basis'te durur.
        'unanimous': ((len(ayrilan) == 0 or len(ayrilmayan) == 0)
                      if len(ayrilan) + len(ayrilmayan) >= 2 else None),
        'unanimous_basis': (
            'İki ya da daha çok üye HÜKÜM VERDİYSE: True = hepsi aynı '
            'yönde, False = çelişki. Hüküm veren üye sayısı 2\'den azsa '
            'hemfikirlik TANIMSIZDIR ve None yayımlanır — bir tek sesin '
            '(ya da hiç sesin) kendisiyle uyuşması hemfikirlik değildir. '
            f'Bu koşuda hüküm veren üye sayısı: '
            f'{len(ayrilan) + len(ayrilmayan)}/{len(SEPARATION_CRITERIA)}.'),
        'separation_z_m': z,
        'z_span_m': (float(max(z_ayrilan) - min(z_ayrilan))
                     if len(z_ayrilan) >= 2 else None),
        'cfd_minus_empirical_m': fark,
        '_basis': (
            'Üyeler arası FARK alanı: hangi ölçüt ayrılma dedi, konumları '
            'ne kadar ayrıştı. unanimous=None ise hüküm veren üye '
            'sayısı 2\'den azdır (hemfikirlik tanımsız, bkz. '
            'unanimous_basis). unanimous=False, ölçütlerin ÇELİŞTİĞİ '
            'anlamına gelir ve bu bir hata DEĞİLDİR — ampirik üçlü '
            'türbülanslı deneylerden kalibrelidir, CFD üyesi ise bu '
            'koşumun kendi fiziğidir. Çelişki gizlenmez; kullanıcı dört '
            'sayıyı da görür. cfd_minus_empirical_m pozitifse CFD '
            'ayrılmayı ampirik ölçütten DAHA AŞAĞIDA (çıkışa yakın) '
            'öngörüyor demektir.'),
    }
