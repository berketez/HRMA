# -*- coding: utf-8 -*-
"""ÖH Dalga-23 · electron kulvarı · aşama-1 bekçileri.

Tek kalem: **P17B2-05** — "tek Ayarlar penceresinde üç kusur".

Kalemin üç ayağının ÖLÇÜLEN durumu (canlı Chrome, /hybrid → TR → Ayarlar;
betik ``docs/scofield/raw/OH/D23/electron/a1/olcum_ayarlar.py``):

===========================  ==================  ==================
ayak                         P17 turu (ilk)      D23 "önce" (ef527ae)
===========================  ==================  ==================
"Hata bildir" TR'de İngiliz. 9 / 22 satır        0 / 22   (D17'de kapandı)
"Sürüm: v?"                  v?                  v2.6.27  (D20'de kapandı)
kontrast 2,75:1              en düşük 2,75:1     en düşük 5,97:1 (D21)
**12 px**                    13 / 22 satır       **9 / 22 satır — AÇIK**
===========================  ==================  ==================

Yani D23'e kalan ayak yalnız BOYUTTU: pencerede 9 satır hâlâ 13 px'in
altında basılıyordu (dördü bölüm başlığı 11 px, dördü alan etiketi 12 px,
biri güncelleme durum satırı 12 px; önizleme adımında ayrıca karakter
sayacı 12 px ve tek aralıklı gövde alanı 12 px). Onarım: pencerenin yazı
ölçeği TEK KAYNAĞA bağlandı (``PX_TABAN`` / ``PX_BASLIK``) ve taban 13 px
yapıldı. Ölçülen sonuç: 13 px altı satır **9 → 0**, en küçük boyut
**11 → 13 px** (``sonra_ayarlar.json``).

Kanıt: ``once_ayarlar.json`` (worktree, onarımdan önce),
``once2_taban_ayarlar.json`` (ortak taban ağacı, aynı sayılar),
``sonra_ayarlar.json``; ters mutasyon ``mutasyon.json``.

Kural (ÖK-05): buradaki her sınama, onarımı geçici olarak geri alınca
KIRMIZI olduğu gösterilmiş bir sınamadır.
"""
import os
import re

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PANEL = 'hrma/static/js/settings_panel.js'
TEMA = 'hrma/static/css/theme.css'

#: Kampanyanın okunabilirlik tabanı. P17 turu "13 px'ten küçük satır" sayarak
#: ölçtü, D21 açıklama satırlarını buna çıkardı; D23 tüm pencereyi çıkarıyor.
TABAN_PX = 13


def oku(gorece):
    with open(os.path.join(KOK, gorece), encoding='utf-8') as f:
        return f.read()


def kod(metin):
    """JS/CSS yorumlarını söker — bekçi KODU ölçer, gerekçe metnini değil."""
    metin = re.sub(r'/\*.*?\*/', ' ', metin, flags=re.S)
    metin = re.sub(r'^\s*//.*$', ' ', metin, flags=re.M)
    return metin


# --------------------------------------------------------------------------
# Kaynaktan "sanal çizim": her font-size bildirimini piksele çöz
# --------------------------------------------------------------------------
BILDIRIM = re.compile(r"font-size:(?:' \+ (PX_[A-Z_]+) \+ '|(\d+(?:\.\d+)?))px")


def _sabitler(govde):
    """Yazı ölçeği sabitleri — DÜZ SAYI ya da başka sabitten TÜREV.

    ÖH D34 · OH-GT-15 (bekçi genişletildi): bu çözücü yalnız
    ``var PX_X = 13;`` biçimini tanıyordu. Ayarlar penceresinin bölüm
    başlığı gövdeyle aynı puntodaydı (ölçüldü: 13 ⟷ 13 px) ve onarım
    ``var PX_BOLUM_BASLIK = PX_TABAN + 1;`` ile geldi — yani TAM DA bu
    dosyanın savunduğu "tek kaynak" ilkesinin gereği olarak, ikinci bir
    çıplak sayı yazılmadan. Eski düz-sayı kalıbı bunu göremediği için
    ``_boyutlar`` "tanımsız yazı ölçeği sabiti" diye düşüyordu: bekçi,
    kendi ilkesine uyan yazımı cezalandırıyordu.

    Çözücü artık türevi de okur. Değerlendirme dar tutulur (yalnız
    ``PX_*`` adları, tamsayılar ve ``+``/``-``); başka bir şey yazılırsa
    sabit ÇÖZÜLMEZ ve ``_boyutlar``ın kendi savı onu yakalar (fail-closed:
    sessizce bir sayı varsayılmaz).
    """
    cozulmus = {ad: int(deger) for ad, deger in
                re.findall(r'var (PX_[A-Z_]+) = (\d+);', govde)}
    turevler = re.findall(r'var (PX_[A-Z_]+) = ([^;\n]+);', govde)
    for _ in range(len(turevler) + 1):          # zincirli türev için yinele
        for ad, ifade in turevler:
            if ad in cozulmus:
                continue
            acik = ifade
            for s_ad in sorted(cozulmus, key=len, reverse=True):
                acik = re.sub(r'\b%s\b' % re.escape(s_ad),
                              str(cozulmus[s_ad]), acik)
            if not re.fullmatch(r'[\d\s+\-]+', acik.strip()):
                continue                        # tanınmayan ifade: çözme
            try:
                cozulmus[ad] = int(eval(acik, {'__builtins__': {}}, {}))
            except Exception:
                pass
    return cozulmus


def _boyutlar(govde):
    """[(çözülmüş px, sabit adı ya da None), ...] — kaynak sırasında."""
    sabit = _sabitler(govde)
    cikti = []
    for m in BILDIRIM.finditer(kod(govde)):
        ad, ham = m.group(1), m.group(2)
        if ad is not None:
            assert ad in sabit, 'tanımsız yazı ölçeği sabiti: %s' % ad
            cikti.append((float(sabit[ad]), ad))
        else:
            cikti.append((float(ham), None))
    return cikti


def _blok(govde, imza, uzunluk=340):
    i = govde.find(imza)
    assert i != -1, 'imza bulunamadı: %s' % imza
    return kod(govde[i:i + uzunluk])


class TestP17B205AyarlarYaziOlcegi:
    """Ayarlar penceresinde 13 px'in altında satır basılmaz."""

    def test_olcek_sabitleri_tek_yerde_ve_tabanin_ustunde(self):
        sabit = _sabitler(oku(PANEL))
        assert sabit, 'yazı ölçeği sabitleri yok — boyut yine dağınık'
        assert sabit.get('PX_TABAN') == TABAN_PX, sabit
        assert sabit.get('PX_BASLIK', 0) >= sabit['PX_TABAN'], sabit

    def test_kaynakta_ciplak_piksel_bildirimi_kalmadi(self):
        """TEK KAYNAK: dosyada elle yazılmış font-size sayısı YOKTUR."""
        ciplak = [px for px, ad in _boyutlar(oku(PANEL)) if ad is None]
        assert ciplak == [], 'çıplak font-size değerleri: %s' % ciplak

    def test_hicbir_bildirim_tabanin_altinda_degil(self):
        """P17'nin saydığı kusur: 13 px altı satır. Kaynakta sıfır olmalı."""
        boyut = _boyutlar(oku(PANEL))
        assert boyut, 'panelde hiç font-size bulunamadı — regex bozulmuş'
        kucuk = [(px, ad) for px, ad in boyut if px < TABAN_PX]
        assert kucuk == [], '13 px altı bildirim: %s' % kucuk
        assert min(px for px, _ in boyut) == TABAN_PX

    @pytest.mark.parametrize('imza', [
        # "önce" ölçümünde 11 px basılan satırlar
        "function sectionTitle(key, fallback) {",
        "function warnChip(w) {",
        "urlIn.style.cssText = INPUT_STYLE +",
        # "önce" ölçümünde 12 px basılan satırlar
        # V3.0.5 T-ÇAPA-C1 — imza değişti (V301/N-girdi-2 e16219b14: ipucu
        # anahtarı üçüncü parametre); ölçülen satır aynı üretici.
        "function fieldLabel(key, fallback, helpKey) {",
        "var MONO_AREA_STYLE = INPUT_STYLE +",
        "var counter = el('div',",
        "var vBasis = el('span',",
        "formStatus.id = 'hrma-bug-form-status'",
        "var checkStatus = el('div',",
        "var skipStatus = el('div',",
        "sendStatus.id = 'hrma-bug-send-status'",
    ])
    def test_kucuk_basilan_satirlar_tabana_cikti(self, imza):
        """Ölçümde 11-12 px çıkan HER üretici artık tabandan besleniyor."""
        govde = oku(PANEL)
        # durum satırlarında bildirim atamadan ÖNCE gelir; blok geriye de bakar
        i = govde.find(imza)
        assert i != -1, imza
        pencere = kod(govde[max(0, i - 260):i + 340])
        boyut = [px for px, ad in
                 [(float(_sabitler(govde)[m.group(1)]), m.group(1))
                  if m.group(1) else (float(m.group(2)), None)
                  for m in BILDIRIM.finditer(pencere)]]
        assert boyut, 'blokta font-size yok: %s' % imza
        assert min(boyut) >= TABAN_PX, '%s → %s' % (imza, boyut)

    def test_baslik_hala_govdeden_buyuk(self):
        """Taban yükselirken başlık hiyerarşisi ezilmemeli."""
        sabit = _sabitler(oku(PANEL))
        assert sabit['PX_BASLIK'] > sabit['PX_TABAN']


# --------------------------------------------------------------------------
# WCAG 2.1 bağıl parlaklık — kalemin kontrast ayağı (D21'de kapandı, KİLİTLİ)
# --------------------------------------------------------------------------
def _bagil_parlaklik(rgb):
    def k(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * k(rgb[0]) + 0.7152 * k(rgb[1]) + 0.0722 * k(rgb[2])


def _onalti(s):
    s = s.lstrip('#')
    return [int(s[i:i + 2], 16) for i in (0, 2, 4)]


def _kontrast(a, b):
    la, lb = _bagil_parlaklik(a), _bagil_parlaklik(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _belirtec(ad):
    """theme.css :root bloğundaki renk belirtecinin değeri."""
    m = re.search(r'--%s:\s*(#[0-9a-fA-F]{6})' % re.escape(ad), oku(TEMA))
    assert m, 'belirteç bulunamadı: --%s' % ad
    return _onalti(m.group(1))


def _bindir(ust, alfa, alt):
    return [ust[i] * alfa + alt[i] * (1 - alfa) for i in range(3)]


class TestP17B205AyarlarKontrasti:
    """2,75:1 geri gelemez: pencerenin mürekkepleri AA eşiğinin üstünde."""

    def test_aciklama_murekkebi_AA_gecer(self):
        oran = _kontrast(_belirtec('hd-ink-dim'), _belirtec('hd-panel-solid'))
        assert oran >= 4.5, 'ölçülen %.3f:1' % oran

    def test_yer_tutucu_murekkebi_AA_gecer(self):
        """Yer tutucular tema dosyasından gelir (`input::placeholder`).

        Zemin zinciri: `--hd-inset` (rgba, 0,85) → `--hd-panel-solid`.
        Canlı ölçüm 4,87:1 diyor; aritmetik onu yeniden üretir.
        """
        assert re.search(r'input::placeholder[^{]*\{\s*color:\s*var\(--hd-ink-faint',
                         oku(TEMA)), 'yer tutucu kuralı değişmiş'
        m = re.search(r'--hd-inset:\s*rgba\(([^)]+)\)', oku(TEMA))
        assert m, '--hd-inset belirteci bulunamadı'
        p = [float(x) for x in m.group(1).split(',')]
        zemin = _bindir(p[:3], p[3], _belirtec('hd-panel-solid'))
        oran = _kontrast(_belirtec('hd-ink-faint'), zemin)
        assert oran >= 4.5, 'yer tutucu kontrastı %.3f:1' % oran

    def test_panelde_en_sonuk_murekkep_kullanilmiyor(self):
        assert kod(oku(PANEL)).count('--hd-ink-faint') == 0


class TestP17B205SurumBeyani:
    """"Sürüm: v?" geri gelmez: okunamayan sürüm için sayı uydurulmaz."""

    def test_soru_isareti_yedegi_yok(self):
        """FAIL-CLOSED: okunamayan sürüm için sessiz '?' yedeği YASAK."""
        govde = kod(oku(PANEL))
        assert "'v?'" not in govde and '"v?"' not in govde
        assert "': v?'" not in govde
        yedek = re.findall(r"\|\|\s*'\?'", govde) + re.findall(r'\|\|\s*"\?"', govde)
        assert yedek == [], 'sessiz soru işareti yedeği: %s' % yedek

    def test_tek_kaynak_okuyucu_kullaniliyor(self):
        govde = kod(oku(PANEL))
        assert 'HRMABugReport' in govde
        assert 'detectVersion' in govde

    def test_okunamayinca_neden_yaziliyor(self):
        """Fail-closed: değer yoksa '?' değil, NEDEN + denenen kaynaklar."""
        govde = kod(oku(PANEL))
        assert 'shell.settings.versionUnknown' in govde
        assert 'shell.settings.versionBasis' in govde
