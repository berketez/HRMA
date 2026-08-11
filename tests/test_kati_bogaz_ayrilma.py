"""Katı motorda boğaz boyutlandırması ve akış ayrılması bekçileri (v2.6.27, A1).

Ayberk'in 5. maddesinin ("itki bir anda ~3000 N'e çıkıp hızla düşüyor") kök
sebebi ölçülerek bulundu: boğaz İLK yanma alanına göre açılıyordu
(``A_burn_0 = calculate_burn_area(0.0)``). Progresif taneciklerde Kn = Ab/At
yanma boyunca büyüdüğü için denge basıncı kullanıcının girdiği tasarım
basıncının çok üstüne tırmanıyordu — ölçülen aşım wagon_wheel'de %116'ya
kadar çıkıyordu. Kasa, yalıtım ve boğaz "40 bar" için boyutlandırılırken
motor 86 bara gidiyordu.

İkinci kusur aynı bölgedeydi: ``CF_ideal = max(CF_ideal, 0.0)``. Aşırı
genişlemiş lülede basınç-itki terimi çok negatife gidince CF sıfıra
çakılıyor, eğrinin bir bölümü Pc > 0 ve mdot > 0 iken TAM OLARAK 0 N
gösteriyordu. Aynı fizik sorununda üç motor üç ayrı şey yapıyordu: sıvı
uyarıyor, katı sessizce sıfırlıyor, hibrit hiç kırpmıyordu.

Bu dosya iki düzeltmenin SÖZLEŞMESİNİ kilitler:

  1. Kullanıcının girdiği kamara basıncı eğrinin TAVANI mıdır?
  2. Boğazın hangi ölçüte göre açıldığı beyan ediliyor mu?
  3. Boğulu bir örnekte itki sessizce sıfıra kırpılıyor mu? (kırpılmamalı)
  4. Ayrılma ve boğulma kaybı birbirinden ayrı mı beyan ediliyor?
  5. Bekçinin kendisi kırılabiliyor mu? (mutasyon denetimi — en sondaki test
     eski boyutlandırmayı geri getirip tavanın GERÇEKTEN kırıldığını gösterir;
     yoksa 1. maddedeki bekçi tautoloji olurdu.)

Hiçbir bekçi elle yazılmış bir sayıya bağlanmaz: karşılaştırmalar çözücünün
kendi tasarım basıncına, kendi boyutlandırma künyesine ya da modülün bildirdiği
toleransa yapılır.
"""

import numpy as np
import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_DESIGN_PRESSURE_TOLERANCE,
    SolidRocketEngine,
)

# Ölçüm turunda kullanılan taban geometri (Ayberk'in şikâyetini üreten kurulum).
TABAN = dict(propellant_type="apcp", chamber_diameter=100,
             grain_length=500, core_diameter=30, chamber_pressure=40)

# Yanma yüzeyi büyüyen (progresif) tanecikler — kusur bunlarda görünüyordu.
PROGRESIF = ("star", "finocyl", "wagon_wheel")
TUM_TIPLER = ("bates", "star", "finocyl", "wagon_wheel", "slotted", "end_burner")


def motor(grain_type, **kw):
    return SolidRocketEngine(grain_type=grain_type, **{**TABAN, **kw})


@pytest.fixture(scope="module")
def egriler():
    """Her tanecik tipi için tek koşum (pahalı; modül boyunca paylaşılır)."""
    out = {}
    for gt in TUM_TIPLER:
        m = motor(gt)
        c = m.calculate_thrust_curve()
        out[gt] = (m, c)
    return out


# --------------------------------------------------------------------------
# 1) Tavan garantisi
# --------------------------------------------------------------------------

@pytest.mark.parametrize("grain_type", TUM_TIPLER)
def test_girilen_kamara_basinci_egrinin_tavanidir(egriler, grain_type):
    """Tepe basıncı, tasarım basıncını beyan edilen toleranstan fazla aşamaz.

    Bu, boyutlandırmanın tanımından gelen bir garantidir: A_t her webin
    gereksiniminin maksimumuna eşitse, r ∝ Pc^n ve n < 1 olduğu için her
    webin denge basıncı tasarımın altında kalır.
    """
    m, c = egriler[grain_type]
    basinclar = np.asarray(c["pressure"], dtype=float)
    assert basinclar.size, f"{grain_type}: basınç serisi boş"
    tepe = float(np.nanmax(basinclar))
    tavan = m.P_c * (1.0 + SOLID_DESIGN_PRESSURE_TOLERANCE)
    assert tepe <= tavan, (
        f"{grain_type}: tepe basınç {tepe:.2f} bar, tasarım {m.P_c:.2f} bar "
        f"(+%{SOLID_DESIGN_PRESSURE_TOLERANCE * 100:g} tolerans = {tavan:.2f} bar). "
        f"Aşım %{(tepe / m.P_c - 1) * 100:.1f}")


def test_tasarim_asim_uyarisi_normal_tasarimda_atesLEMEZ(egriler):
    """``pressure_exceeds_design`` bir emniyet ağıdır; normalde sessiz olmalı."""
    for gt in TUM_TIPLER:
        m, _ = egriler[gt]
        kodlar = {u.get("code") for u in m.calculate_performance()
                  .get("design_warnings", [])}
        assert "warn.solid.pressure_exceeds_design" not in kodlar, (
            f"{gt}: boğaz maks Kn'de açıldığı hâlde tasarım aşım uyarısı "
            f"ateşledi — boyutlandırma ya da tarama çözünürlüğü sorunlu")


# --------------------------------------------------------------------------
# 2) Boyutlandırma künyesi
# --------------------------------------------------------------------------

def test_bogazin_hangi_olcute_gore_acildigi_beyan_ediliyor(egriler):
    m, c = egriler["star"]
    rapor = m._throat_sizing_report(c)
    assert rapor["basis"] == "max burn area (Kn_max)"
    assert rapor["basis_text"], "boyutlandırma gerekçesi metni boş"
    # Künye çözücünün kendi tasarım basıncını taşımalı (sabit sayı değil).
    assert rapor["design_chamber_pressure_bar"] == pytest.approx(m.P_c)
    # Ölçülen tepe künyeye yazılıyor ve eğriden geliyor.
    tepe = float(np.nanmax(np.asarray(c["pressure"], dtype=float)))
    assert rapor["peak_chamber_pressure_bar"] == pytest.approx(tepe, rel=1e-9)


def test_kunye_egri_verilmezse_sayi_uydurmaz():
    """Eğri yoksa basınç alanları None kalır — uydurma yasağı."""
    rapor = motor("star")._throat_sizing_report(None)
    assert rapor["peak_chamber_pressure_bar"] is None
    assert rapor["peak_over_design"] is None


@pytest.mark.parametrize("grain_type", PROGRESIF)
def test_progresif_tanecikte_boyutlandirma_alani_baslangictan_buyuk(
        egriler, grain_type):
    """Progresif tanecikte maks yanma alanı, t=0 alanından büyüktür.

    Boyutlandırmanın t=0'dan maks Kn'ye taşındığını gösteren fark tam olarak
    budur; oran 1 çıksaydı düzeltme hiçbir şeyi değiştirmemiş olurdu.
    """
    m, _ = egriler[grain_type]
    d = m._design_throat_detail()
    assert d["design_burn_area_m2"] > d["initial_burn_area_m2"]
    assert d["burn_area_ratio"] > 1.0


def test_uc_yakanda_alan_orani_bire_esittir(egriler):
    """Uç yakan tanecikte yanma alanı sabittir; oran 1 olmalı (nötr denetim)."""
    m, _ = egriler["end_burner"]
    assert m._design_throat_detail()["burn_area_ratio"] == pytest.approx(1.0, abs=1e-6)


# --------------------------------------------------------------------------
# 3) CF sıfır-kırpması kalktı
# --------------------------------------------------------------------------

@pytest.mark.parametrize("grain_type", TUM_TIPLER)
def test_bogulu_ornekte_itki_sessizce_sifira_kirpilmaz(egriler, grain_type):
    """Boğaz boğuluyken ve Pc > 0 iken itki TAM 0 olamaz.

    Eski davranış: ``max(CF_ideal, 0.0)`` yüzünden eğrinin %34'üne kadarı
    Pc = 3,3 bar ve mdot = 0,55 kg/s iken 0 N gösteriyordu. Artık ayrılmış
    bölgede itki kesilmiş-lüle modelinden gelir; sıfır yalnız boğulma
    kaybında ve SEBEBİ bildirilerek raporlanır.
    """
    _, c = egriler[grain_type]
    F = np.asarray(c["thrust"], dtype=float)
    P = np.asarray(c["pressure"], dtype=float)
    bogulu = np.asarray(c["choked"], dtype=bool)
    kotu = np.flatnonzero((F == 0.0) & bogulu & (P > 0.0))
    assert kotu.size == 0, (
        f"{grain_type}: boğulu ve Pc > 0 iken {kotu.size} örnekte itki tam 0 — "
        f"ilk örnek t = {np.asarray(c['time'])[kotu[0]]:.3f} s, "
        f"Pc = {P[kotu[0]]:.3f} bar")


# --------------------------------------------------------------------------
# 4) Ayrılma ve boğulma kaybı ayrı beyan ediliyor
# --------------------------------------------------------------------------

@pytest.mark.parametrize("grain_type", TUM_TIPLER)
def test_ayrilma_ani_bayrakla_tutarli(egriler, grain_type):
    """``separated_from_t`` ayrılma yoksa None, varsa İLK ayrılma anıdır."""
    _, c = egriler[grain_type]
    sep = np.asarray(c["separated"], dtype=bool)
    t = np.asarray(c["time"], dtype=float)
    andan = c["separated_from_t"]
    if not sep.any():
        assert andan is None, f"{grain_type}: ayrılma yok ama an bildirilmiş"
        return
    assert andan is not None, f"{grain_type}: ayrılma var ama an bildirilmemiş"
    assert andan == pytest.approx(float(t[int(np.argmax(sep))]))


def test_ayrilmada_uyari_atesler_ve_olcutunu_soyler():
    m = motor("wagon_wheel")
    sonuc = m.calculate_performance()
    uyarilar = {u["code"]: u for u in sonuc.get("design_warnings", [])}
    assert "warn.solid.flow_separation" in uyarilar, (
        "ayrılma ölçüldüğü hâlde kullanıcıya bildirilmiyor")
    p = uyarilar["warn.solid.flow_separation"]["params"]
    for alan in ("from_t_s", "fraction_percent",
                 "exit_pressure_min_bar", "ambient_bar", "criterion_ratio"):
        assert alan in p, f"ayrılma uyarısında {alan} yok"
    assert 0.0 < p["fraction_percent"] <= 100.0


def test_bogulma_kaybi_ayri_uyari_ve_sifirin_sebebi_yazili():
    m = motor("wagon_wheel")
    c = m.calculate_thrust_curve()
    if float(c.get("unchoked_fraction", 0.0)) <= 0.0:
        pytest.skip("bu geometride boğulma kaybı oluşmuyor")
    kodlar = {u["code"] for u in m.calculate_performance()
              .get("design_warnings", [])}
    assert "warn.solid.nozzle_unchoked" in kodlar
    # Sıfırın sebebi eğrinin kendi sözleşme metninde de yazılı olmalı.
    assert "choked" in c["choking_criterion"].lower()


def test_ayrilma_ve_bogulma_ayri_kavramlar():
    """İkisi aynı maskeye indirgenmemeli — farklı fizik, farklı beyan."""
    c = motor("wagon_wheel").calculate_thrust_curve()
    sep = np.asarray(c["separated"], dtype=bool)
    bogulu = np.asarray(c["choked"], dtype=bool)
    assert sep.size == bogulu.size
    # Ayrılmış ama hâlâ boğulu örnek bulunmalı: ayrılma boğulmadan ÖNCE başlar.
    assert np.any(sep & bogulu), (
        "ayrılma ile boğulma kaybı aynı örneklerde çakışıyor — "
        "iki durum ayrı ayrı modellenmemiş olabilir")


# --------------------------------------------------------------------------
# 5) Mutasyon denetimi — bekçi gerçekten kırılabiliyor mu?
# --------------------------------------------------------------------------

@pytest.mark.parametrize("grain_type", PROGRESIF)
def test_mutasyon_eski_boyutlandirma_tavani_kirar(egriler, grain_type):
    """Boğazı ESKİ ölçüte (Ab(0)) sabitleyince tavan bozulmalı.

    Bu test, yukarıdaki tavan bekçisinin tautoloji OLMADIĞINI kanıtlar: eğer
    boyutlandırma düzeltmesi geri alınırsa tavan bekçisi kırmızıya düşer.
    ``pin_throat_area`` desteklenen bir koldur (üretim toleransı Monte
    Carlo'su onu kullanır), yani iç yapıya yama yapmıyoruz.
    """
    m, _ = egriler[grain_type]
    d = m._design_throat_detail()
    eski_alan = d["throat_area_m2"] / d["burn_area_ratio"]

    m_eski = motor(grain_type)
    m_eski.pin_throat_area(eski_alan)
    tepe = float(np.nanmax(np.asarray(
        m_eski.calculate_thrust_curve()["pressure"], dtype=float)))

    tavan = m.P_c * (1.0 + SOLID_DESIGN_PRESSURE_TOLERANCE)
    assert tepe > tavan, (
        f"{grain_type}: eski boyutlandırmayla bile tepe {tepe:.2f} bar tavanın "
        f"altında kaldı — tavan bekçisi hiçbir şeyi ölçmüyor olabilir")


def test_pin_throat_area_gercekten_etkili():
    """Sabitleme sessizce yok sayılırsa mutasyon denetimi anlamsız olurdu.

    (Bu testin sebebi somut: sabitleme önce ``overrides`` sözlüğüyle denendi,
    hiçbir etkisi olmadı — sabitleme bir METOT. Kanal sessizce yutulursa
    yukarıdaki mutasyon testi 'geçer' ama hiçbir şeyi mutasyona uğratmaz.)
    """
    m = motor("star")
    taban = m._design_throat_detail()["throat_area_m2"]
    m2 = motor("star")
    m2.pin_throat_area(taban * 0.6)
    assert m2._design_throat_detail()["throat_area_m2"] == pytest.approx(taban * 0.6)
    assert m2._design_throat_detail()["pinned"] is True
