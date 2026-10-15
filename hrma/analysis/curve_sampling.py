"""Yayımlanan zaman serilerinin TEPEYİ KORUYAN seyreltmesi — TEK tanım noktası.

Neden ortak modül
-----------------
Katı ve hibrit motorların çözücüleri farklıdır ama yayın katmanındaki sorun
AYNIDIR: sabit adımlı bir integratör, yanma süresiyle sınırsız büyüyen bir
dizi üretir ve bu dizi olduğu gibi istemciye gönderilir. İki motor bunu ayrı
ayrı çözerse, aynı algoritmanın iki kopyası ve iki farklı tavanı doğar; biri
düzeltilirken diğeri unutulur (CLAUDE.md kural 11). Bu yüzden hem tavan hem
seçme algoritması hem de kullanıcıya yapılan BEYAN buradan gelir.

ÖLÇÜLEN kusur (ikisi de bu depoda ölçüldü, tahmin değil)
--------------------------------------------------------
* Katı, v2.6.27 B2-3 öncesi: ``end_burner``, L = 500 mm, t_b = 61,6 s ->
  6157 nokta / 519 KB, yanıtın %87'si.
* Hibrit, bu düzeltmeden önce: port çapı 5 mm, t_b = 50 s -> 17 317 nokta /
  1,29 MB (``thrust_curve``) + 17 317 nokta / 1,28 MB
  (``of_shift_performance``); toplam yanıt 2,75 MB ve bunun %94'ü bu iki
  dizi. Hibritte adım sayısı ``t_b·2·ṙ_0/(0,01·D_port_0)`` ile büyür, yani
  küçük port + uzun yanma en kötü hâldir.

ÇÖZÜCÜYE DOKUNULMAZ
-------------------
Seyreltme yalnız YAYIMLANAN diziye uygulanır. İntegrasyon adımı, dolayısıyla
bütün türetilmiş büyüklükler (toplam impuls, ortalama itki, kararlılık,
biçim, O/F kayması, uyarılar) tam çözünürlüklü çözümden hesaplanmaya devam
eder. Aynı desen depoda üç yerde daha kurulu: ``WALL_HISTORY_MAX_POINTS``,
``port_history``, ``TPS_WALL_HISTORY_MAX_POINTS``.
"""

import numpy as np

from hrma.utils.numeric_compat import trapezoid

# ---------------------------------------------------------------------------
# Yayımlanan eğrinin örnek tavanı — İKİ motor için de.
# 400 nokta, ekran çözünürlüğünde çizilen bir eğrinin ayırt edebileceğinden
# fazladır (tipik grafik genişliği ~800 px, kova başına iki örnek alındığı
# için piksel başına bir uç düşer).
# ---------------------------------------------------------------------------
THRUST_CURVE_MAX_POINTS = 400

# ---------------------------------------------------------------------------
# ÖH D26 / P5B4-33 — ‰1 İDDİASININ KAPSAMI (eskiden KAYITSIZ ŞARTSIZDI)
#
# Bu blok eskiden şunu yazıyordu: tavan "trapez impuls hatasını ölçülen uç
# girdilerde ‰1'in altında tutar (bkz. tests/test_hibrit_egri_ornekleme.py)".
# Cümle kapsamsızdı: modül keyfi bir eğri alabilir, iddia ise sınırsız
# okunuyordu. ÖLÇÜLDÜ (D26 tabanı 7751531, n = 20 000 sentetik eğri, AYNI
# seyreltici; kanıt ``docs/scofield/raw/OH/D26/yapisal-sistem/a1/once.json``):
#
#     ateşleme tepesi (ilk 20 örnekte 0 -> 4000 N rampa)      +5,9942 ‰
#     tek örneklik iğne (tek örnekte 1000 -> 50 000 N)      +120,9846 ‰
#     %5 görev döngülü darbe dizisi (10/200 örnek dolu)    +4452,7264 ‰
#
# (Aynı üç eğri, P5B4-31 kova bütçesi onarımından SONRA — kova sayısı
# 200 -> 198 düştüğü için sapmalar kaydı, mertebe aynı kaldı:
# +6,0691 ‰ / +123,4288 ‰ / +4052,0260 ‰. Kapsam metnindeki sayılar
# BUGÜNKÜ koddan alınmıştır ve bekçi onları mandallar.)
#
# yani iddia üç kat, 121 kat ve 4453 kat aşılıyordu. Gerçek HRMA eğrilerinde
# (sürekli, tek tepeli, yanma süresince yavaş değişen) sapma +0,00714 ‰
# ölçüldü — ürün etkisi bugün YOKTUR; kusur BEYANDAYDI.
#
# ONARIM: iddia kapsamıyla birlikte yazıldı ve ÖLÇÜLEBİLİR hâle getirildi
# (:func:`trapezoid_error_permil`). Sayıyı düzeltmek yerine cümleyi
# düzeltmek burada meşrudur çünkü kusurun kendisi cümleydi: seyreltici
# TEPEYİ koruyan bir örnekleyicidir, ALAN KORUYAN değildir ve alan koruyan
# bir örnekleyiciye geçmek zarf/tepe garantisini bozardı (ayrı ürün kararı).
# Bekçi artık kapsamın İÇİNİ kilitliyor ve DIŞINI ölçülmüş sayılarla
# mandallıyor: cümle sessizce yeniden genişletilirse test kırmızı düşer.
# ---------------------------------------------------------------------------
TRAPEZOID_PERMIL_LIMIT = 1.0

TRAPEZOID_PERMIL_SCOPE = (
    'The <=1 permil trapezoidal-impulse bound is a MEASURED property of the '
    'curves this repository actually solves (continuous, single-peaked '
    'thrust histories whose value changes slowly between solver steps): on '
    'those the measured deviation is +0.00714 permil. It is NOT a guarantee '
    'for an arbitrary array. The thinning preserves the PEAK and the '
    'ENVELOPE, not the AREA, so a curve whose area lives in a few samples '
    'breaks the bound: measured on 20000-sample synthetic curves, an '
    'ignition spike gives +6.07 permil, a single-sample needle +123.43 '
    'permil, and a 5%-duty pulse train +4052.03 permil. Callers that thin '
    'such a curve must publish trapezoid_error_permil() for it instead of '
    'relying on this bound.')


def trapezoid_error_permil(time, thrust, indices):
    """Seyreltilmiş eğrinin trapez impuls sapması [‰] — ÖLÇÜM, iddia değil.

    :data:`TRAPEZOID_PERMIL_SCOPE` bir GENEL sınır vermez; bu yardımcı,
    çağıranın kendi eğrisi için sapmayı SAYIYLA öğrenmesini sağlar. Tam
    çözünürlüklü impuls sıfır ya da sonlu değilse ``None`` döner — oran
    UYDURULMAZ.

    Args:
        time: tam çözünürlüklü zaman dizisi [s].
        thrust: tam çözünürlüklü itki dizisi [N].
        indices: :func:`decimate_curve_indices` çıktısı (yayımlanan indeksler).

    Returns:
        ``1000 * (I_yayin - I_tam) / I_tam`` ya da ``None``.
    """
    t = np.asarray(time, dtype=float)
    F = np.asarray(thrust, dtype=float)
    if t.size != F.size or t.size < 2:
        return None
    idx = np.asarray(indices, dtype=int)
    if idx.size < 2:
        return None
    I_tam = float(trapezoid(F, t))
    if not np.isfinite(I_tam) or I_tam == 0.0:
        return None
    I_yayin = float(trapezoid(F[idx], t[idx]))
    if not np.isfinite(I_yayin):
        return None
    return 1000.0 * (I_yayin - I_tam) / I_tam


def decimate_curve_indices(thrust, pressure=None, keep=(),
                           max_points=THRUST_CURVE_MAX_POINTS):
    """Yayımlanacak eğri için TEPEYİ KORUYAN örnek indeksleri.

    SABİT ADIMLI seyreltme tepeyi ıskalayabilir, o yüzden burada iki koruma
    birlikte çalışır:

    1. **Kova uçları.** Örnekler eşit sayıda kovaya bölünür ve her kovadan
       itkinin EN BÜYÜK ve EN KÜÇÜK olduğu örnek alınır. Bu, küresel tepeyi
       tanım gereği taşır ve eğrinin zarfını (salınım genliğini) korur; düz
       stride ise zarfı rastgele kırpar.
    2. **Zorunlu örnekler.** ``keep`` ile verilen indeksler (kullanıcıya
       BEYAN EDİLEN olayların anları: ayrılma, boğulmanın kesilmesi,
       tükeniş, yanma sonu, oksitleyici bitişi, O/F uçları) kovalardan
       bağımsız olarak eklenir.

    İlk ve son örnek her hâlde korunur (yanma süresi ve kapanış noktası
    eğriden okunabilmelidir).

    Args:
        thrust: itki örnekleri (zarfı belirleyen birincil dizi).
        pressure: verilirse tepe basınç örneği de zorunlu tutulur.
        keep: ek zorunlu indeksler (None/aralık dışı olanlar atılır).
        max_points: yaklaşık üst sınır. Dizi bundan kısaysa HİÇBİR seyreltme
            yapılmaz ve bütün indeksler döner.

    Returns:
        Artan sırada, tekrarsız indeks dizisi (numpy int dizisi).
    """
    F = np.asarray(thrust, dtype=float)
    n = int(F.size)
    if n == 0:
        return np.zeros(0, dtype=int)
    if n <= int(max_points):
        return np.arange(n, dtype=int)

    zorunlu = {0, n - 1}
    sonlu = np.isfinite(F)
    if bool(sonlu.any()):
        zorunlu.add(int(np.nanargmax(np.where(sonlu, F, -np.inf))))
    if pressure is not None:
        P = np.asarray(pressure, dtype=float)
        if P.size == n and bool(np.isfinite(P).any()):
            zorunlu.add(int(np.nanargmax(
                np.where(np.isfinite(P), P, -np.inf))))
    for idx in keep:
        if idx is None:
            continue
        i = int(idx)
        if 0 <= i < n:
            zorunlu.add(i)

    # --- ÖH D26 / P5B4-31: KOVA BÜTÇESİ ZORUNLU ÖRNEKLERİ HESABA KATAR --
    # ÖLÇÜLEN KUSUR (D26 tabanı 7751531, kanıt
    # ``docs/scofield/raw/OH/D26/yapisal-sistem/a1/once.json``; n = 5000
    # sentetik eğri, sabit tohum): eski kod ``max_points // 2`` kova açıp
    # her kovadan iki örnek alıyor, ZORUNLU örnekleri (ilk/son, tepe itki,
    # tepe basınç, beyan edilen olaylar) bunun ÜSTÜNE ekliyordu::
    #
    #     olaysız yayın   402 nokta   (tavan 400)   -> aşım +2
    #     6 olaylı yayın  408 nokta   (tavan 400)   -> aşım +8
    #
    # ve ``sampling_block`` aynı sözlükte ``points_published=408`` ile
    # ``max_points=400``ü yan yana yayımlıyordu; aşımı söyleyen alan YOKTU
    # (P05 ölçümünde canlı ``/calculate_solid`` çıktısında da 402/400).
    #
    # ONARIM: bütçe önce ZORUNLU örneklere ayrılır, kova sayısı KALANDAN
    # açılır. Böylece toplam ``len(zorunlu) + 2*kova <= max_points`` olur ve
    # tavan tanım gereği tutar. Tavan DÜŞÜRÜLMEDİ, zorunlu örnek de
    # ATILMADI — yalnız kovaya ayrılan pay doğru hesaplanıyor.
    #
    # TEK İSTİSNA: ``keep`` tek başına tavanı aşacak kadar olay taşıyorsa
    # (beyan edilen olayları atmak, kullanıcıya söylenen bir anı eğriden
    # silmek olurdu) aşım KABUL EDİLİR ve ``sampling_block`` bunu ADIYLA
    # beyan eder (fail-closed: sessiz aşım yok).
    kalan_butce = int(max_points) - len(zorunlu)
    kova = max(1, kalan_butce // 2)
    sinirlar = np.linspace(0, n, kova + 1).astype(int)
    secilen = set(zorunlu)
    for bas, son in zip(sinirlar[:-1], sinirlar[1:]):
        if son <= bas:
            continue
        dilim = F[bas:son]
        gecerli = np.isfinite(dilim)
        if not bool(gecerli.any()):
            secilen.add(int(bas))
            continue
        secilen.add(int(bas + np.nanargmax(np.where(gecerli, dilim, -np.inf))))
        secilen.add(int(bas + np.nanargmin(np.where(gecerli, dilim, np.inf))))
    return np.array(sorted(secilen), dtype=int)


def nearest_sample_index(times, t_value):
    """BEYAN EDİLEN bir olay anının (saniye) eğrideki en yakın örnek indeksi.

    Olay yoksa (``None``) ya da dizi boşsa ``None`` döner — indeks
    UYDURULMAZ. Aralık dışındaki bir zaman en yakın uca düşer; çağıran taraf
    olayın gerçekten pencerede olup olmadığına kendisi karar verir (hibritte
    oksitleyici tükenişi kırpılan yanmada pencerenin DIŞINDADIR).
    """
    if t_value is None:
        return None
    t = np.asarray(times, dtype=float)
    if t.size == 0 or not np.isfinite(float(t_value)):
        return None
    return int(np.argmin(np.abs(t - float(t_value))))


def _dayanak_metni(ogeler) -> str:
    """Künye cümlesinin ORTASINA girecek listeyi İngilizce ibareye çevir.

    ÖH D24 / P5B4-32 — ÖLÇÜLEN KUSUR (taban ``88a29d3``, kanıt
    ``once_p5b432.json``): ``basis`` metni listeyi ``str(...)`` ile
    gömüyordu. Liste geçirildiğinde İngilizce cümlenin ortasında Python
    söz dizimi çıkıyordu::

        ... plus the first and last sample, the peak-pressure sample, and
        ['burnout', 'chuffing'].

    Bugün iki canlı çağıran da düz dize geçirdiği için ürün metni temizdi
    (latent tuzak); imza ``critical_events``/``derived_quantities``
    çoğuldur, yani liste geçirmek sözleşmenin İÇİNDE bir kullanımdır.
    Dize geçirilirse metin BİT-AYNI kalır (çapa değişmez).
    """
    if isinstance(ogeler, str):
        return ogeler
    try:
        parcalar = [str(o) for o in ogeler]
    except TypeError:
        return str(ogeler)
    if not parcalar:
        return 'no items'
    if len(parcalar) == 1:
        return parcalar[0]
    if len(parcalar) == 2:
        return f'{parcalar[0]} and {parcalar[1]}'
    return ', '.join(parcalar[:-1]) + ' and ' + parcalar[-1]


def sampling_block(points_published, points_computed, solver_time_step_s,
                   critical_events, derived_quantities,
                   max_points=THRUST_CURVE_MAX_POINTS):
    """Yayımlanan eğrinin ``sampling`` beyanı — iki motorda AYNI sözleşme.

    Dizinin ÇÖZÜM çözünürlüğü değil YAYIN çözünürlüğü olduğu, neyin
    korunduğu ve türetilmiş sayıların nereden geldiği burada bir kez yazılır.
    İki motor bu metni ayrı ayrı yazsaydı, algoritma değiştiğinde biri eski
    açıklamayı göstermeye devam ederdi — kullanıcı koşulmayan bir işlemin
    açıklamasını okurdu (aynı kusur ``SOLID_MC_TOLERANCE_MODEL`` bloğunda
    ölçülmüştü).

    Args:
        points_published: yayımlanan örnek sayısı.
        points_computed: çözücünün ürettiği örnek sayısı.
        solver_time_step_s: çözücü adımı [s] (değişmediğinin kanıtı).
        critical_events: bu motorda ZORUNLU taşınan olayların İngilizce
            listesi (motora özgüdür: katıda ayrılma/boğulma/tükeniş,
            hibritte yanma sonu/oksitleyici bitişi/O/F uçları).
        derived_quantities: tam çözünürlükten hesaplanan büyüklüklerin
            İngilizce listesi (motora özgüdür).
        max_points: uygulanan tavan.
    """
    yayin = int(points_published)
    tavan = int(max_points)
    blok = {
        'points_published': yayin,
        'points_computed': int(points_computed),
        'decimated': bool(yayin < int(points_computed)),
        'solver_time_step_s': solver_time_step_s,
        'max_points': tavan,
        'basis': (
            'The solver time step is UNCHANGED; only the published array is '
            'thinned. Thinning keeps, in every bucket, the samples of '
            'largest and smallest thrust (so the peak and the envelope '
            'survive) plus the first and last sample, the peak-pressure '
            'sample, and ' + _dayanak_metni(critical_events) + '. Every '
            'derived '
            'quantity in this response (' + _dayanak_metni(
                derived_quantities) + ') is '
            'computed from the FULL-resolution solution, not from this '
            'array.'),
    }
    # --- ÖH D26 / P5B4-31: TAVAN AŞIMI SESSİZ KALAMAZ -------------------
    # ``decimate_curve_indices`` bütçeyi zorunlu örneklerden sonra açtığı
    # için normal yolda aşım DOĞMAZ. Yalnız beyan edilen olaylar tek
    # başına tavanı aşarsa aşım kalır (olay örneğini atmak kullanıcıya
    # söylenen bir anı eğriden silmek olurdu) — o hâlde sayı yan yana
    # yayımlanıp susulmaz, ADIYLA söylenir.
    blok['cap_exceeded'] = bool(yayin > tavan)
    if blok['cap_exceeded']:
        blok['cap_note'] = (
            f'The published array exceeds the declared cap by {yayin - tavan} '
            f'sample(s) ({yayin} > {tavan}). Nothing was dropped to hide '
            'this: the samples above the cap are the MANDATORY ones (first '
            'and last sample, peak thrust, peak pressure, and the declared '
            'critical events), which alone need more room than the cap '
            'allows. The bucket budget is already reduced to zero.')
    return blok
