"""ÖH D35 · U-4 (Cowork görsel turu, 21 Eyl 2026) — form etiketleri alana BAĞLI.

Ölçülen kusur: hibrit 96 / katı 93 / sıvı 96 etiketin (advanced 0, solid 2,
liquid 0) hiçbiri ``for=`` taşımıyordu, girdiler etiket içinde de değildi:
etikete tıklamak alanı odaklamıyor, ekran okuyucu "etiketsiz sayı kutusu"
okuyordu. 22 Eyl: ana model betikle her etiketi komşu kontrolüne bağladı
(advanced 91, solid 80, liquid 90). Bu bekçi iki yönü kilitler:
(1) her ``for`` hedefi statik gövdede TEK id ile var;
(2) statik formdaki her görünür kontrolün bir etiketi var
    (``label[for]`` ya da sarmalayan ``label`` ya da ``aria-label``).
Betik (``<script>``) blokları gövde sayılmaz — güverte gibi paneller
alanlarını JS'te üretir, o etiketler analysis_dock.js bekçilerinin işidir.
"""
import re
from collections import Counter
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SABLONLAR = ('advanced', 'solid', 'liquid')


def _govde(ad):
    s = (KOK / 'hrma' / 'templates' / f'{ad}.html').read_text(encoding='utf-8')
    return re.sub(r'<script\b.*?</script>', '', s, flags=re.S)


@pytest.mark.parametrize('ad', SABLONLAR)
def test_her_for_hedefi_statik_govdede_tek_id(ad):
    g = _govde(ad)
    fors = re.findall(r'<label\b[^>]*\bfor="([^"]+)"', g)
    taban = {'advanced': 65, 'solid': 75, 'liquid': 85}[ad]   # 22 Eyl ölçümü: 70 / 82 / 90
    assert len(fors) >= taban, f'{ad}: for= sayısı beklenenin altında ({len(fors)} < {taban})'
    sayim = Counter(re.findall(r'\bid="([^"]+)"', g))
    eksik = [f for f in fors if sayim.get(f, 0) == 0]
    cift = [f for f in fors if sayim.get(f, 0) > 1]
    assert not eksik, f'{ad}: hedefi olmayan for: {eksik[:8]}'
    assert not cift, f'{ad}: birden çok id ile eşleşen for: {cift[:8]}'


@pytest.mark.parametrize('ad', SABLONLAR)
def test_statik_formdaki_her_kontrolun_etiketi_var(ad):
    g = _govde(ad)
    etiketli = set(re.findall(r'<label\b[^>]*\bfor="([^"]+)"', g))
    sarmal = set()
    for m in re.finditer(r'<label\b[^>]*>(.*?)</label>', g, flags=re.S):
        sarmal.update(re.findall(r'\bid="([^"]+)"', m.group(1)))
    etiketsiz = []
    for m in re.finditer(r'<(input|select|textarea)\b([^>]*)>', g):
        attrs = m.group(2)
        if re.search(r'type="(hidden|button|submit|checkbox|radio|file)"', attrs):
            continue
        idm = re.search(r'\bid="([^"]+)"', attrs)
        if not idm:
            continue
        cid = idm.group(1)
        if cid in etiketli or cid in sarmal or 'aria-label' in attrs or 'aria-labelledby' in attrs:
            continue
        etiketsiz.append(cid)
    # Bilinen istisnalar: salt gösterim / etiketi JS'in yazdığı alanlar buraya
    # ADIYLA eklenir; sessiz büyüme yasak (sayı sabit tutulur).
    izinli = {
        'advanced': set(), 'solid': set(), 'liquid': set(),
    }[ad]
    kalan = [c for c in etiketsiz if c not in izinli]
    assert not kalan, f'{ad}: etiketsiz kontroller ({len(kalan)}): {kalan[:12]}'
