# -*- coding: utf-8 -*-
"""OH-D33-44 — künye metni kartın dışına taşıyordu.

ÖLÇÜLDÜ (kılavuzda YAYIMLANMIŞ iki karede birden, tr-02-results.png ve
en-02-results.png): sonuç kartının künye satırı kartın çerçevesini aşıyor ve
sağ kenarda kırpılıyordu; ``minimum_earned_safety_factor`` sözcük ortasından
kesiliyordu. Kullanıcı hükmün hangi alandan geldiğini yarım okuyordu.

Bu dosya kusurun KÖKÜNÜ kilitler: künye metnini basan sınıf adları
``app.js``ten OKUNUR (sabit liste değil), her biri için sarma kuralının
CSS'te DURDUĞU ölçülür. Sınıf adı JS'te değişirse bekçi kırmızıya döner —
kural dosyada kalıp artık kimseye uygulanmıyor olmaz.
"""
import os
import re

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js', 'app.js')
CSS = os.path.join(KOK, 'hrma', 'static', 'css', 'results_hud.css')

#: Künye/not metnini taşıyan elemanların sınıf adları app.js'ten çıkarılır.
#: Desen: `class="hd-..."` ve içinde 'kunye' ya da 'note' geçen sınıflar.
KUNYE_SINIF_DESENI = re.compile(r'class="(hd-[a-z-]*(?:kunye|note)[a-z-]*)"')

#: Boşluksuz uzun alan adını bölebilen CSS özellikleri. Biri yeterlidir.
SARMA_OZELLIKLERI = ('overflow-wrap', 'word-break')


def _js():
    with open(JS, encoding='utf-8') as fh:
        return fh.read()


def _css():
    with open(CSS, encoding='utf-8') as fh:
        return fh.read()


def _yorumsuz(css):
    """CSS yorumlarını ayıklar.

    Yorum içindeki virgüller seçici listesi sanılırsa bekçi kendi kuralını
    göremez; ilk yazımda tam olarak bu oldu (ölçüldü: .hd-metric-note kuralı
    dosyada dururken bekçi 'yok' dedi).
    """
    return re.sub(r'/\*.*?\*/', ' ', css, flags=re.S)


def _kural_govdesi(css, sinif):
    """`.sinif` seçicisini İÇEREN kural bloklarının gövdelerini döndürür."""
    css = _yorumsuz(css)
    govdeler = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        seciciler = [s.strip() for s in m.group(1).split(',')]
        if any(s == '.' + sinif or s.startswith('.' + sinif + ':')
               or s.startswith('.' + sinif + ' ')
               for s in seciciler):
            govdeler.append(m.group(2))
    return govdeler


def test_kunye_sinifi_gercekten_basiliyor():
    """Bekçinin ölçtüğü sınıf adları uydurma değil, JS'in bastığı adlardır."""
    siniflar = set(KUNYE_SINIF_DESENI.findall(_js()))
    assert siniflar, ('app.js künye/not sınıfı basmıyor görünüyor — desen '
                      'bayatlamış olabilir, elle denetleyin')
    # Ölçüldü (16 Eyl 2026): iki sınıf var. Sayı artarsa bekçi yeni sınıfı
    # da kapsar; azalırsa burada görürüz.
    assert 'hd-metric-note' in siniflar, sorted(siniflar)
    assert 'hd-verdict-kunye' in siniflar, sorted(siniflar)


@pytest.mark.parametrize('sinif', sorted(set(
    KUNYE_SINIF_DESENI.findall(open(JS, encoding='utf-8').read()))))
def test_kunye_sinifinin_sarma_kurali_var(sinif):
    """Her künye sınıfı boşluksuz uzun belirteci kart içinde bölebilmeli."""
    govdeler = _kural_govdesi(_css(), sinif)
    assert govdeler, (
        f'.{sinif} için results_hud.css içinde kural yok; künye kartı '
        'aşarsa kırpılır (kusurun ta kendisi)')
    birlesik = ' '.join(govdeler)
    assert any(o in birlesik for o in SARMA_OZELLIKLERI), (
        f'.{sinif} kuralında sarma özelliği yok ({SARMA_OZELLIKLERI}); '
        'boşluksuz alan adları kartın dışına taşar')


def test_kart_hucresi_buzulebiliyor():
    """Izgara hücresi min-width:auto ile büzülmeyi reddederse sarma yetmez."""
    govdeler = _kural_govdesi(_css(), 'hd-metric')
    assert any('min-width' in g and '0' in g for g in govdeler), (
        '.hd-metric için min-width:0 yok; ızgara hücresi varsayılan '
        'min-width:auto ile içeriğinden küçülemez ve künye yine taşar')
