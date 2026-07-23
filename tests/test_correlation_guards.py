"""Korelasyon bekçileri (v2.5.0 G4) — taban-dondurma + kötüleşme kapıları.

Amaç: gerçek-deney korelasyon istatistiği SESSİZCE kötüleşemez (ya da
şüpheli biçimde ani iyileşemez). Taban, 2026-07-18 fizik düzeltmeleri
(gox oksitleyici dalı, HTPB/parafin Hf, merkezi burn_rate_db, adaptör
flux_mode='ox', t4l-12 anomali bayrağı) SONRASI tam koşudan donduruldu.

Bekçi mantığı (ARGE spec 5.2 + Berke onaylı K kararları):
1. DB içerik hash'i dondurulur: hash değiştiyse 'DB mi değişti fizik mi'
   ayrımı yapılamaz — test, tabanın BİLİNÇLİ güncellenmesini ister.
2. Hücre başına kötüleşme kapısı: medAPE ve |bias|, taban x1.25 (+küçük
   tabanlar için mutlak pay) üstüne çıkamaz.
3. Fizik tavanları (mutlak, onaylı): hibrit c* medAPE <= %5, sıvı Isp_vac
   <= %5, katı burn_rate (in-sample) <= %5. Pc / regresyon / Isp hücreleri
   İÇİN MUTLAK TAVAN YOK — bunlar dokümante model-formu sınırlarıdır
   (teorik c* zinciri, tek a-n seti, düşük-akı rejimi; bkz.
   VALIDATION_STATUS.md); yalnız taban-kötüleşme kapısıyla izlenir.
4. Aşırı-iyileşme UYARISI: medAPE tabanın yarısının altına inerse test
   KIRMAZ ama uyarır — ani 'mucize' iyileşme çoğu kez dongusellik
   (ölçümün tahmine sızması) işaretidir; elle incelenmelidir.
5. Kayıt sayıları: hücre n'i tabanın altına düşemez (kayıtlar sessizce
   istatistikten damlayamaz); runner_errors boş kalmalı.

Dürüstlük notları:
- solid burn_rate hücresi IN-SAMPLE'dır (katsayılar aynı veri setinin
  kaynak fitinden; bkz. hrma/data/burn_rate_db.py) — %0.5 medAPE bağımsız
  tahmin becerisi DEĞİLDİR, implementasyon doğrulamasıdır.
- hibrit isp/thrust tabanı (%9.1) önceki sürümdeki %3.0'dan YÜKSEKTİR:
  eski değer, c* eksiği ile CF fazlasının birbirini iptal etmesiydi
  (2026-07-18 incelemesi). Taban dürüst değerden donduruldu.

Koşu maliyeti: tam korelasyon ~15-20 s (module-scoped fixture, tek koşu).
"""

import warnings

import pytest

from hrma.validation.correlation_runner import run_correlation

# --- Dondurulmuş taban (2026-07-18, adaptör v1 + fizik düzeltmeleri)
# Hash güncellemesi (2026-07-18 akşamı, veri genişletme dalgası): 136 -> 199
# kayıt (63 yeni hibrit: Cardillo 2023, Battista 2019, Scaramuzzino/Carmicino
# 2013, Heydari 2017, HPDP 2003, AMROC DM-01, Sims 1998, Knowles 2004).
# ANA İSTATİSTİK SETİ DEĞİŞMEDİ: yeni kayıtların 59'u insufficient_inputs
# (kaynaklar port/boğaz çapını yayımlamamış veya büyük-ölçek İngiliz-birim
# nokta yolu adaptör v2 işi), 4'ü (Heydari S4A1 swirl serisi) v1 eksenel
# model kapsamı dışı olduğundan anomaly bayraklı — anomali katmanında
# izlenir. BASELINE değerleri bu yüzden aynı kaldı.
# Hash güncellemesi (2026-07-23, dünya-çapı genişletme): 199 -> 209 kayıt.
# 10 yeni GERÇEK sıvı motor eklendi (kaynaklı, çoğu birincil ajans belgesi):
# LE-9/LE-7A/LE-5B-2/LE-5B-3 (JAXA-MHI), NK-33/RD-180/RD-0120 (Rusya),
# Vinci (ESA/ArianeGroup), RS-68 (ABD), CE-20 (ISRO). Sıvı vakum Isp örneklemi
# n=4 -> n=14'e, 6 ülkeye çıktı — dış denetimin "n çok küçük" eleştirisine
# yanıt. Ana istatistik iyileşti/genişledi, aşağıda BILINÇLI güncellendi.
EXPECTED_DB_HASH = (
    "2ee2a86bbd6968e4d0c7d4a5f770665cc31094b6c0ba6e1dc2fb9d6971d9eca4")

# (motor, quantity) -> (bias_pct, median_ape_pct, n)
BASELINE = {
    ("hybrid", "c_star"): (0.1, 2.3, 18),
    ("hybrid", "chamber_pressure"): (16.8, 13.8, 35),
    ("hybrid", "isp"): (9.6, 9.1, 18),
    ("hybrid", "port_diameter_final"): (-9.4, 10.1, 18),
    ("hybrid", "regression_rate"): (-20.2, 35.1, 35),
    ("hybrid", "thrust"): (9.6, 9.1, 18),
    # 2026-07-23 dünya-çapı genişletme: n=4 -> n=14 (6 ülke). medAPE %2.8 ->
    # %1.20, bias +0.93. Örneklem 3.5 kat büyüdü ve hata düştü — taban bilinçli
    # sıkılaştırıldı. isp_sl de artık skorlanıyor (n=4).
    ("liquid", "isp_vac"): (0.93, 1.20, 14),
    ("liquid", "isp_sl"): (2.03, 2.06, 4),
    ("liquid", "thrust_vac"): (-0.39, 0.16, 4),
    ("solid", "burn_rate"): (-0.4, 0.5, 27),
}

# Mutlak fizik tavanları (medAPE %, Berke onaylı hedef hücreler)
PHYSICS_CEILING_MEDAPE = {
    ("hybrid", "c_star"): 5.0,
    ("liquid", "isp_vac"): 5.0,
    ("solid", "burn_rate"): 5.0,  # in-sample; bkz. modül docstring
}

DEGRADE_FACTOR = 1.25   # taban x1.25 kötüleşme kapısı
MEDAPE_ABS_SLACK = 1.0  # küçük tabanlarda mutlak pay (yüzde puanı)
BIAS_ABS_SLACK = 1.5


@pytest.fixture(scope="module")
def corr():
    """Tam korelasyon koşusu (bir kez)."""
    return run_correlation()


@pytest.fixture(scope="module")
def cells(corr):
    return {(c["motor_type"], c["quantity"]): c
            for c in corr["statistics"]["cells"]}


def test_db_hash_frozen(corr):
    """DB değiştiyse taban bilinçli güncellenmeli (kör güncelleme yasak)."""
    assert corr["db_content_hash"] == EXPECTED_DB_HASH, (
        "Deney DB içeriği değişti (hash uyuşmuyor). Bu test KASITLI kırılır: "
        "yeni kayıt/düzeltme sonrası tam koşuyu incele, hücre istatistiklerini "
        "gözden geçir ve BASELINE + EXPECTED_DB_HASH değerlerini bilinçli "
        "olarak güncelle (bkz. docs/GUVEN_SURUMU_PLANI.md bekçi bölümü).")


def test_no_runner_errors(corr):
    assert corr["runner_errors"] == [], (
        f"Korelasyon koşusunda patlayan kayıt(lar) var: {corr['runner_errors']}")


def test_all_baseline_cells_present(cells):
    missing = [k for k in BASELINE if k not in cells]
    assert not missing, (
        f"Taban hücreleri istatistikten kayboldu: {missing} — kayıtlar sessizce "
        f"düşmüş olabilir (adaptör/status değişimini incele).")


@pytest.mark.parametrize("key", sorted(BASELINE), ids=lambda k: f"{k[0]}:{k[1]}")
def test_cell_not_degraded(cells, key):
    """medAPE ve |bias| taban kapısının üstüne çıkamaz; n düşemez."""
    base_bias, base_medape, base_n = BASELINE[key]
    cell = cells[key]

    medape_gate = max(base_medape * DEGRADE_FACTOR,
                      base_medape + MEDAPE_ABS_SLACK)
    bias_gate = max(abs(base_bias) * DEGRADE_FACTOR,
                    abs(base_bias) + BIAS_ABS_SLACK)

    assert cell["median_ape_pct"] <= medape_gate, (
        f"{key}: medAPE {cell['median_ape_pct']:.1f}% > kapı {medape_gate:.1f}% "
        f"(taban {base_medape:.1f}%) — fizik/adaptör regresyonu olabilir.")
    assert abs(cell["bias_pct"]) <= bias_gate, (
        f"{key}: |bias| {abs(cell['bias_pct']):.1f}% > kapı {bias_gate:.1f}% "
        f"(taban {base_bias:+.1f}%).")
    assert cell["n"] >= base_n, (
        f"{key}: n {cell['n']} < taban {base_n} — kayıtlar istatistikten "
        f"sessizce düştü.")

    # Aşırı-iyileşme: kırmaz, uyarır (dongusellik şüphesi elle incelenmeli).
    if base_medape >= 2.0 and cell["median_ape_pct"] < 0.5 * base_medape:
        warnings.warn(
            f"{key}: medAPE {cell['median_ape_pct']:.1f}% tabanın "
            f"({base_medape:.1f}%) yarısının altına indi — iyileşme gerçek mi, "
            f"yoksa ölçüm tahmine mi sızdı (dongusellik)? Elle doğrula.",
            stacklevel=1)


@pytest.mark.parametrize("key", sorted(PHYSICS_CEILING_MEDAPE),
                         ids=lambda k: f"{k[0]}:{k[1]}")
def test_physics_ceiling(cells, key):
    """Onaylı mutlak tavanlar (hedef hücreler)."""
    ceiling = PHYSICS_CEILING_MEDAPE[key]
    got = cells[key]["median_ape_pct"]
    assert got <= ceiling, (
        f"{key}: medAPE {got:.1f}% > onaylı fizik tavanı {ceiling:.1f}%.")


def test_anomaly_records_not_in_cells(corr, cells):
    """Anomali bayraklı kayıt ana istatistiğe sızamaz (karantina bütünlüğü)."""
    anomaly_ids = {e["test_id"] for e in corr["statistics"]["anomaly_entries"]}
    assert "hyb-karabeyoglu2003-paraffin-gox-t4l-12" in anomaly_ids, (
        "t4l-12 anomali bayrağı kayboldu (bildiri-içi tutarsızlık kaydı; "
        "bkz. kayıt anomaly.note).")
    assert "hyb-heydari2017-htpb-n2o-s4a1-1" in anomaly_ids, (
        "Heydari swirl (S4A1) anomali bayrağı kayboldu — swirl enjeksiyon "
        "v1 eksenel model kapsamı dışıdır, ana istatistiğe giremez "
        "(bkz. kayıt anomaly.note, 2026-07-18 veri genişletme dalgası).")
    for key, cell in cells.items():
        leaked = anomaly_ids & {e["test_id"] for e in cell["entries"]}
        assert not leaked, f"{key}: anomali kayıtları ana hücreye sızdı: {leaked}"
