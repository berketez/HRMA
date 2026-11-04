# -*- coding: utf-8 -*-
"""V306/ÖLÇÜT kalem 4 — RL10A-3-3A kayıtlarının boğaz geometrisi bekçisi.

Kusur (mühendis turu 2 Kas 2026, sıvı BULGULAR §5 kayıt notu; triyaj S1):
``liq-rl10a33a-*`` kayıtları ``geometry.throat_diameter_in = 2.47`` taşıyordu.
Kaydın KENDİ itki ve basıncıyla bu çap fiziksel değildir: vakum itki katsayısı
F/(Pc·A_t) = 16500 lbf / (475 psia × π·1,235²) = 7,25 çıkar; ideal vakum
C_F'si (ε = 61) en düşük makul γ'da bile ~2,06'dır.

Kaynak (NASA TM-107318, Ocak 1997, sayfa görüntüsünden okundu 4 Kas 2026):
Tablo 2.5.1 2.47 / 5.13 in'i 'Throat/Chamber Diameter' satırında basar; aynı
raporun Ek E Şekil E1'i aynı büyüklükleri 'Radius of Chamber/Nozzle Inner
Wall (inches)' ekseninde (boğaz ~2,5, oda ~5,1 in) çizer ve Tablo 2.5.1'in
model noktası ṁ·c*/Pc = 18,85 in² (D_t 4,90 in) verir. Düzeltme: sayılar
kaynakta basıldığı gibi, alan adı ``throat_radius_in`` / ``chamber_radius_in``.

Bekçi neyi kilitler: KAYDIN İÇ TUTARLILIĞINI (fizik), bugünkü bir HRMA
çıktısını değil. Her RL10 kaydında boğaz büyüklüğü (çap ya da yarıçap,
birim sonekiyle) kaydın kendi itkisi ve oda basıncıyla birleştirildiğinde
vakum itki katsayısı fiziksel aralıkta olmalı:

    C_F,ideal,vak(ε = 1, γ = 1,30)  ≤  F / (Pc · A_t)  ≤  C_F,ideal,vak(ε, γ = 1,10)

Üst sınır: gerçek lüle ideal lüleyi aşamaz ve ideal vakum C_F'si γ düştükçe
büyür; γ = 1,10 LOX/LH2 yanma ürünlerinin γ'sının altındadır (cömert sınır,
HRMA seçimi). Alt sınır: genişleyen bir lülenin vakum C_F'si sonik boğazın
(ε = 1) ideal değerinin altına inmez; γ = 1,30 cömert üst γ (HRMA seçimi).
Bağıntılar: Sutton & Biblarz, Rocket Propulsion Elements 9. bas., Denk. 3-25
(alan oranı ↔ Mach) ve 3-30 (itki katsayısı).

Ters mutasyon (ölçüldü, RAPOR.md): kayıt eski ``throat_diameter_in: 2.47``
değerine döndürülürse ``test_rl10_bogaz_itki_katsayisi_fiziksel`` KIRMIZI.
"""

import json
import math
import pathlib

import pytest

from hrma.validation import record_adapters as ra
from hrma.validation.experiment_db import ensure_valid_record

KOK = pathlib.Path(__file__).resolve().parents[1]
DIZIN = KOK / "hrma" / "data" / "validation_records" / "liquid"
RL10_KIMLIKLERI = ["liq-rl10a33a-nominal-spec"] + [
    f"liq-rl10a33a-t{i}" for i in range(1, 6)]

#: HRMA seçimi (cömert): LOX/LH2 ürünlerinin γ'sı bu aralığın içindedir.
GAMMA_ALT = 1.10
GAMMA_UST = 1.30


def _alan_orani(mach, gamma):
    """İzentropik A/A* (Sutton & Biblarz 9. bas., Denk. 3-25)."""
    return (1.0 / mach) * ((2.0 / (gamma + 1.0)) * (
        1.0 + (gamma - 1.0) / 2.0 * mach * mach)) ** (
        (gamma + 1.0) / (2.0 * (gamma - 1.0)))


def _ideal_cf_vak(eps, gamma):
    """İdeal vakum itki katsayısı (Sutton & Biblarz 9. bas., Denk. 3-30)."""
    if eps <= 1.0:
        mach = 1.0
    else:
        alt, ust = 1.0, 60.0
        for _ in range(200):  # ikiye bölme: A/A* süpersonik dalda artan
            orta = 0.5 * (alt + ust)
            if _alan_orani(orta, gamma) < eps:
                alt = orta
            else:
                ust = orta
        mach = 0.5 * (alt + ust)
    p_orani = (1.0 + (gamma - 1.0) / 2.0 * mach * mach) ** (
        -gamma / (gamma - 1.0))
    momentum = math.sqrt(
        2.0 * gamma * gamma / (gamma - 1.0)
        * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
        * (1.0 - p_orani ** ((gamma - 1.0) / gamma)))
    return momentum + p_orani * eps


def _kayit(kimlik):
    yol = DIZIN / f"{kimlik}.json"
    with open(yol, encoding="utf-8") as f:
        kayit = json.load(f)
    ensure_valid_record(kayit, path=yol)
    return kayit


def _bogaz_alani_m2(geometri):
    """Boğaz alanı (m²) — çap ya da yarıçap anahtarından, birim sonekiyle."""
    bulunan = []
    for anahtar, deger in geometri.items():
        if not isinstance(deger, (int, float)) or isinstance(deger, bool):
            continue
        taban, si = ra.to_si(anahtar, deger)
        if si is None:
            continue
        if taban == "throat_diameter":
            bulunan.append(math.pi * si * si / 4.0)
        elif taban == "throat_radius":
            bulunan.append(math.pi * si * si)
    assert len(bulunan) == 1, (
        f"boğaz büyüklüğü tek ve birimli olmalı, bulunan {len(bulunan)}: "
        f"{sorted(geometri)}")
    return bulunan[0]


def _itki_ve_basinc(kayit):
    """Kaydın kendi itkisi (N) ve oda basıncı (Pa) — kaynaktaki alanlardan."""
    olculen = kayit["measured"]
    girdi = kayit["inputs"]
    if "thrust_vac_lbf" in olculen:
        itki = olculen["thrust_vac_lbf"] * ra.UNIT_TO_SI["lbf"]
    else:
        itki = olculen["thrust_lbf"] * ra.UNIT_TO_SI["lbf"]
    if "chamber_pressure_psia" in girdi:
        basinc = girdi["chamber_pressure_psia"] * ra.UNIT_TO_SI["psia"]
    else:
        basinc = (olculen["chamber_pressure_injector_face_psia"]
                  * ra.UNIT_TO_SI["psia"])
    return itki, basinc


@pytest.mark.parametrize("kimlik", RL10_KIMLIKLERI)
def test_rl10_bogaz_itki_katsayisi_fiziksel(kimlik):
    kayit = _kayit(kimlik)
    eps = float(kayit["geometry"]["expansion_ratio"])
    a_t = _bogaz_alani_m2(kayit["geometry"])
    itki, basinc = _itki_ve_basinc(kayit)
    cf = itki / (basinc * a_t)
    alt = _ideal_cf_vak(1.0, GAMMA_UST)
    ust = _ideal_cf_vak(eps, GAMMA_ALT)
    assert alt <= cf <= ust, (
        f"{kimlik}: kaydın kendi F ve Pc'siyle boğaz alanı {a_t * 1e4:.2f} cm² "
        f"-> C_F,vak = {cf:.3f}; fiziksel aralık [{alt:.3f}, {ust:.3f}] "
        f"(ε = {eps:g}). Boğaz büyüklüğü yanlış adla (çap ⟷ yarıçap) ya da "
        f"yanlış birimle saklanmış olabilir.")


def test_rl10_nominal_oda_bogaz_alan_orani_tablo_e1_ile_tutarli():
    """Oda/boğaz büyüklükleri aynı adla saklanmalı (ikisi de yarıçap).

    TM-107318 Ek E Tablo E1: oda (boğazdan −12.00 in) alan oranı 4.27.
    İki alan farklı büyüklükle (biri çap, biri yarıçap) saklanırsa oran 4×
    ya da ¼× kayar; aynı büyüklükle saklanırsa (5,13/2,47)² = 4,31.
    """
    geo = _kayit("liq-rl10a33a-nominal-spec")["geometry"]
    oda = {ra.to_si(k, v)[0]: ra.to_si(k, v)[1] for k, v in geo.items()
           if isinstance(v, (int, float)) and not isinstance(v, bool)
           and ra.to_si(k, v)[1] is not None}
    a_oda = (math.pi * oda["chamber_radius"] ** 2 if "chamber_radius" in oda
             else math.pi * oda["chamber_diameter"] ** 2 / 4.0)
    oran = a_oda / _bogaz_alani_m2(geo)
    assert abs(oran - 4.27) / 4.27 < 0.02, (
        f"oda/boğaz alan oranı {oran:.3f}; TM-107318 Tablo E1 4.27")


def test_rl10_kayitlari_bogaz_tasiyor():
    """Bekçi boşa dönmesin: altı kaydın hepsinde boğaz büyüklüğü var."""
    for kimlik in RL10_KIMLIKLERI:
        assert _bogaz_alani_m2(_kayit(kimlik)["geometry"]) > 0.0
