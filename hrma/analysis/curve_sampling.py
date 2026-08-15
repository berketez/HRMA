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

# ---------------------------------------------------------------------------
# Yayımlanan eğrinin örnek tavanı — İKİ motor için de.
# 400 nokta, ekran çözünürlüğünde çizilen bir eğrinin ayırt edebileceğinden
# fazladır (tipik grafik genişliği ~800 px, kova başına iki örnek alındığı
# için piksel başına bir uç düşer) ve trapez impuls hatasını ölçülen uç
# girdilerde ‰1'in altında tutar (bkz. tests/test_hibrit_egri_ornekleme.py).
# ---------------------------------------------------------------------------
THRUST_CURVE_MAX_POINTS = 400


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

    # Kova sayısı: her kovadan iki örnek (min + maks) alındığı için tavanın
    # yarısı kadar kova açılır.
    kova = max(1, int(max_points) // 2)
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
    return {
        'points_published': int(points_published),
        'points_computed': int(points_computed),
        'decimated': bool(int(points_published) < int(points_computed)),
        'solver_time_step_s': solver_time_step_s,
        'max_points': int(max_points),
        'basis': (
            'The solver time step is UNCHANGED; only the published array is '
            'thinned. Thinning keeps, in every bucket, the samples of '
            'largest and smallest thrust (so the peak and the envelope '
            'survive) plus the first and last sample, the peak-pressure '
            'sample, and ' + str(critical_events) + '. Every derived '
            'quantity in this response (' + str(derived_quantities) + ') is '
            'computed from the FULL-resolution solution, not from this '
            'array.'),
    }
