# hrma/utils — Izgara Yakınsama İndeksi (GCI) — TEK TANIM (ÖH D37 A3a cfd-kok-a, F-04)
"""
Celik, Ghia, Roache, Freitas, Coleman, Raad, "Procedure for Estimation and
Reporting of Uncertainty Due to Discretization in CFD Applications",
J. Fluids Eng. 130(7):078001, 2008 — beş adımlı prosedür:

  1. Temsili hücre boyu  h = (1/N)^(1/dim)         (Eş. 1; 2B'de dim = 2)
  2. Üç ızgara, oran     r = h_kaba / h_ince ≥ 1,3  (metin, §2 adım 2)
  3. Gözlenen mertebe    p: ε21 = f2 − f1, ε32 = f3 − f2,
                         p = |ln|ε32/ε21| + q(p)| / ln r21,
                         q(p) = ln((r21^p − s)/(r32^p − s)), s = sign(ε32/ε21)
                                                   (Eş. 2-4)
  4. Richardson dışdeğer f_ext21 = (r21^p f1 − f2)/(r21^p − 1)   (Eş. 5)
  5. Hata/GCI            e_a21 = |(f1 − f2)/f1|,
                         GCI_fine21 = Fs·e_a21/(r21^p − 1), Fs = 1,25  (Eş. 6-8)

BU GERÇEKLEMENİN CELİK 2008'DEN AYRILDIĞI VE DK KAMPANYASININ GEREKTİRDİĞİ
NOKTALAR (docs/scofield/raw/OH/D37/dogrulama/cfd/rapor.md §(h)1-2; hakem
düzeltmesi 24 Eyl 2026 ve gci_bekci.py karşı örnekleri):

* Mertebe İŞARETLİDİR: p·ln r21 = ln(ε32/ε21) + q(p) MUTLAK DEĞERSİZ çözülür.
  Celik'in Eş. 3'teki dış mutlak değeri büyüyen fark dizisini (ör. (4, 2, 1),
  ε21/ε32 > 1) pozitif mertebeli "yakınsama" gibi gösterir; ölçüldü — DK'nın
  eski aracı (4,2,1) için p = +1, GCI = %62,5 döndürüyordu, 38 üçlüden 4'ü
  böyle sahte-pozitifti (C1 mach_L2 ince, C2 exit_p ince, C2b ṁ ince, C2b
  p02/p01 kaba). İşaretli p < 0 → 'monotonic_divergent', GCI YAZILMAZ.
* Eşit fark (ε21 = ε32, p = 0) sıfıra bölmez; 'equal_differences', GCI yok.
* Salınımlı dizide (ε21/ε32 < 0) Celik'in "salınımlı yakınsama" notu vardır;
  burada GCI yazılmaz, yalnız bant (maks−min)/|f1| beyan edilir ('oscillatory'
  |R| < 1, 'oscillatory_divergent' |R| ≥ 1).
* GEÇERLİLİK KAPISI ayrı fonksiyondur (``ucu_gecerli``): sayı dizisinin
  sınıflanması, koşumların yakınsamış olup olmadığını BİLMEZ. Limit döngüsü
  ya da yakınsamamış koşumdan GCI yazılmaz; açık yolda plato-dondurmalı
  ('not_evaluated') seviye ancak dondurma İNİŞ KAPISINI geçmişse
  (``limiter_freeze.descent_decades_at_freeze ≥ descent_gate_decades``) ve
  yayımlanan kalıntı hedefin altındaysa geçerli sayılır — gerekçe ve ölçüm
  hrma/cfd/steady.py PLATEAU_* sabitlerinde (C1 120×24: geç dondurma kökü
  satır-örtük kökle 1,1e-6 bağıl aynı; erken dondurma 240×48'de 1,8e-4
  sapmış ve mertebeyi 2,07 → 0,58 çökertmişti — OH-DK-12).

Bu modül SAYI ÜRETMEZ, sınıflar; sınıf 'monotonic' değilse GCI alanı YOKTUR
(anahtar bile yazılmaz — tüketici ``gci_valid`` bayrağını okur).
Bekçi: tests/cfd/test_d37_gci.py (DK gci_bekci.py'nin 8 karşı örneği + ters
mutasyon). F06 ``kosum_betigi.gci`` ve DK ``referans.gci`` bu modülün
yerine geçtiği eski kopyalardır; ürün kodu yalnız burayı çağırır.
"""

import math

__all__ = [
    'gci', 'p_isaretli', 'ucu_gecerli', 'GCI_FS', 'GCI_R_MIN',
    'GCI_DURUMLARI', 'GECERLI_HUKUMLER',
]

#: Celik 2008 güvenlik çarpanı (üç ızgara, Eş. 7 — Roache'un Fs = 1,25'i).
GCI_FS = 1.25
#: Celik 2008 §2 adım 2: inceltme oranı en az 1,3 olmalı (deneyime dayalı).
GCI_R_MIN = 1.3

GCI_DURUMLARI = ('monotonic', 'monotonic_divergent', 'equal_differences',
                 'oscillatory', 'oscillatory_divergent', 'degenerate',
                 'unsolved')
_SINIF_TR = {
    'monotonic': 'monoton yakınsama',
    'monotonic_divergent': 'monoton ıraksama',
    'equal_differences': 'eşit fark (p = 0)',
    'oscillatory': 'salınımlı yakınsama',
    'oscillatory_divergent': 'salınımlı ıraksama',
    'degenerate': 'dejenere',
    'unsolved': 'p çözülemedi',
}

#: Koşum hükümlerinden GCI'ya GİREBİLECEK olanlar (``ucu_gecerli``).
GECERLI_HUKUMLER = ('converged', 'not_evaluated')


def p_isaretli(r21, r32, oran, maxit=500, tol=1e-12):
    """İşaretli gözlenen mertebe (oran = ε32/ε21 > 0).

    p·ln r21 = ln(oran) + q(p), q(p) = ln((r21^p − 1)/(r32^p − 1)); mutlak
    değer ALINMAZ. r21 = r32 iken q ≡ 0 → kapalı biçim (Celik Eş. 3'ün
    eşit-oran özel hâli). Aksi hâlde sönümlü sabit-nokta iterasyonu (Celik
    §2 adım 3 "solved using fixed-point iteration"). Dönüş (p, çözüldü_mü).
    """
    r21 = float(r21)
    r32 = float(r32)
    oran = float(oran)
    if oran <= 0.0 or r21 <= 1.0 or r32 <= 1.0:
        return float('nan'), False
    L = math.log(oran)
    if abs(r21 - r32) < 1e-12 * r21:
        return L / math.log(r21), True

    def q(p):
        if abs(p) < 1e-12:
            return math.log(math.log(r21) / math.log(r32))
        return math.log((r21 ** p - 1.0) / (r32 ** p - 1.0))

    p = L / math.log(r21)
    for _ in range(int(maxit)):
        try:
            p_new = (L + q(p)) / math.log(r21)
        except (ValueError, ZeroDivisionError, OverflowError):
            return float('nan'), False
        if abs(p_new - p) < tol:
            return p_new, True
        p = 0.5 * (p + p_new)
    return p, False


def gci(N, f, Fs=GCI_FS, dim=2):
    """Üç seviyeli Celik 2008 GCI — sayı dizisini SINIFLAR.

    Args:
        N: (N1, N2, N3) hücre sayıları, 1 = EN İNCE (N1 > N2 > N3).
        f: (f1, f2, f3) aynı sırada büyüklük değerleri.
        Fs: güvenlik çarpanı (varsayılan 1,25).
        dim: uzay boyutu (h = N^(−1/dim)).

    Returns:
        dict: her zaman N, f, r21, r32, eps21, eps32, Fs, refinement_ok,
        status, sinif, gci_valid; R (ε21/ε32) tanımlıysa; p_signed (çözüldüyse);
        YALNIZ status == 'monotonic' iken p, f_ext, e_a21, e_ext21,
        GCI_fine21, GCI_medium32, asymptotic_ratio. Diğer sınıflarda
        band_rel = (maks f − min f)/|f1| beyan edilir, GCI anahtarı YOKTUR.
    """
    if len(N) != 3 or len(f) != 3:
        raise ValueError('N ve f üçer elemanlı olmalı (ince → kaba).')
    N1, N2, N3 = [float(x) for x in N]
    f1, f2, f3 = [float(x) for x in f]
    if not (N1 > N2 > N3 > 0.0):
        raise ValueError(f'N ince→kaba azalan olmalı: {N}')
    if not all(math.isfinite(x) for x in (f1, f2, f3)):
        raise ValueError(f'f sonlu olmalı: {f}')
    h = [N1 ** (-1.0 / dim), N2 ** (-1.0 / dim), N3 ** (-1.0 / dim)]
    r21, r32 = h[1] / h[0], h[2] / h[1]
    e21, e32 = f2 - f1, f3 - f2
    band = (abs(max(f1, f2, f3) - min(f1, f2, f3)) / abs(f1)
            if f1 != 0.0 else None)
    out = dict(N=[N1, N2, N3], f=[f1, f2, f3], r21=r21, r32=r32,
               eps21=e21, eps32=e32, Fs=float(Fs), dim=int(dim),
               refinement_ok=bool(min(r21, r32) >= GCI_R_MIN),
               gci_valid=False)

    def _bitir(status, **ek):
        out.update(status=status, sinif=_SINIF_TR[status], band_rel=band,
                   **ek)
        return out

    if e21 == 0.0 or e32 == 0.0:
        return _bitir('degenerate')
    R = e21 / e32
    out['R'] = R
    if R < 0.0:
        return _bitir('oscillatory' if abs(R) < 1.0
                      else 'oscillatory_divergent')
    p, ok = p_isaretli(r21, r32, e32 / e21)
    if not ok:
        return _bitir('unsolved')
    out['p_signed'] = p
    if abs(p) < 1e-9:
        return _bitir('equal_differences')
    if p < 0.0:
        return _bitir('monotonic_divergent')
    f_ext = (r21 ** p * f1 - f2) / (r21 ** p - 1.0)
    e_a = abs((f1 - f2) / f1) if f1 != 0.0 else float('nan')
    e_ext = abs((f_ext - f1) / f_ext) if f_ext != 0.0 else float('nan')
    gci_fine = Fs * e_a / (r21 ** p - 1.0)
    gci_med = (Fs * abs((f2 - f3) / f2) / (r32 ** p - 1.0)
               if f2 != 0.0 else None)
    out.update(status='monotonic', sinif=_SINIF_TR['monotonic'],
               gci_valid=True, p=p, f_ext=f_ext, e_a21=e_a, e_ext21=e_ext,
               GCI_fine21=gci_fine, GCI_medium32=gci_med,
               asymptotic_ratio=((r21 ** p * gci_fine / gci_med)
                                 if gci_med else None))
    return out


def ucu_gecerli(seviyeler):
    """Üçlünün her seviyesi GCI'ya girebilir mi? — KOŞUM-DURUMU KAPISI.

    Args:
        seviyeler: her seviye için sözlük — ``convergence_status`` zorunlu;
            'not_evaluated' için ayrıca ``limiter_freeze`` (steady.py
            çıktısındaki blok: ``descent_decades_at_freeze``,
            ``descent_gate_decades``) ve ``residual_last`` + ``tol_res``.

    Returns:
        (gecerli: bool, etiket: str, sorunlar: list[dict]) — fail-closed:
        eksik alan "ölçülemedi" sayılır, geçerli DEĞİLDİR.

    Kural (kilit: docs/scofield/raw/OH/A3a/cfd-kok-a/olcut_kulvar.json K1):
      * 'converged'                       → geçerli
      * 'not_evaluated' (açık yol, plato-dondurmalı kök) → geçerli ANCAK
        dondurma iniş kapısını geçmişse (descent_decades_at_freeze ≥
        descent_gate_decades) VE yayımlanan kalıntı < tol_res; dondurma
        hiç olmadıysa ('not_evaluated' ama frozen_at None — olamaz, açık
        yolda canlı operatör hüküm verir) → geçersiz
      * 'not_converged' / 'plateau' / 'diverged' / 'wall_star_pressure_
        nonpositive' / bilinmeyen → geçersiz (limit döngüsü ya da
        yakınsamamış koşumdan GCI yazılmaz — DK hakem §4.3)
    """
    sorunlar = []
    for k, s in enumerate(seviyeler):
        st = s.get('convergence_status')
        if st == 'converged':
            continue
        if st == 'not_evaluated':
            lf = s.get('limiter_freeze') or {}
            inis = lf.get('descent_decades_at_freeze')
            kapi = lf.get('descent_gate_decades')
            kal = s.get('residual_last')
            tol = s.get('tol_res')
            if lf.get('frozen_at_iter') is None or inis is None or kapi is None:
                sorunlar.append(dict(seviye=k, durum=st, neden=(
                    'donmuş kök ama iniş kapısı ölçümü yok (limiter_freeze '
                    'bloğu eksik ya da dondurma kaydı yok) — ölçülemeyen '
                    'geçerli sayılmaz')))
                continue
            if not (float(inis) >= float(kapi)):
                sorunlar.append(dict(seviye=k, durum=st, neden=(
                    f'erken dondurma: iniş {float(inis):.2f} mertebe < kapı '
                    f'{float(kapi):.2f} — dondurulmuş kök yapay (OH-DK-12)')))
                continue
            if kal is None or tol is None or not (float(kal) < float(tol)):
                sorunlar.append(dict(seviye=k, durum=st, neden=(
                    'yayımlanan kalıntı hedefin altında değil ya da '
                    'ölçülmedi')))
                continue
            continue
        sorunlar.append(dict(seviye=k, durum=st, neden=(
            f'{st!r}: yakınsamamış / limit döngüsü / hükümsüz koşumdan GCI '
            'yazılmaz')))
    if sorunlar:
        return False, 'GEÇERSİZ — ' + '; '.join(
            f"seviye {x['seviye']} {x['durum']}" for x in sorunlar), sorunlar
    return True, 'geçerli (her seviye converged ya da iniş kapılı donmuş kök)', []
