# -*- coding: utf-8 -*-
"""F3 — KAMUYA AÇIK YAYIMLANMIŞ statik test verisiyle korelasyon döngüsü (2.7 kapı #3).

Kayıtlar (Nakka Kappa kampanyası, nakka-rocketry.net; tam künye kayıtların
``source`` bloğunda):

  - sol-nakka2000-kappa-ksb002  KNSB, temiz yakma  -> ANA katman (bayrak kayıt)
  - sol-nakka2000-kappa-kdx002  KNDX               -> LOW katman (tane boyu
        kardeş-test çıkarımı; gerekçe kaydın extraction_note'unda)
  - sol-nakka2000-kappa-ksb001  KNSB, anomalili    -> ANOMALY katmanı
        (tutuşma gecikmesi + basınç sensör hattı tıkanması)

Bekçi kapsamı:
  (a) şema kapısı: üç kayıt ``ensure_valid_record``'dan ve üretim ağacı
      yüklemesinden geçer;
  (b) korelasyon koşusu deterministiktir ve ÖLÇÜLEN sapma bantları kilitlidir
      (bantlar 2026-08-18 koşusundan ölçüldü, uydurma tolerans yok; platform
      payı ±1.0 yüzde puanı — bkz. platform float sözleşmesi notu);
  (c) dürüstlük alanları: ``digitized: true``, kaynak künyesi, sayısallaştırma
      yöntemi/belirsizliği extraction_note'ta;
  (d) kayıtlar 'yayımlanmış literatür' imlidir ve 'dış kullanıcı' İDDİA
      EDİLMEZ (dış-kullanıcı ayağı Ayberk verisiyle ayrıca kapanacak).

Ek bekçiler — F3 sırasında ölçülüp kapatılan üç adaptör kusuru geri gelemez:
  #1 kayıt geometrisindeki BATES segment sayısı motora kablolanmalı
     (kablosuz: t_b %13, F_tepe %15 sapıyordu — ölçüldü);
  #2 assumed_defaults, motorun GERÇEKTE çözdüğü a-n'i raporlamalı
     (eski kod kullanılmayan 0.005/0.35'i 'varsayılan' diye beyan ediyordu);
  #3 grain tipi eşlemesi sözcük sınırlı olmalı (Türkçe 'astarlanmış' alt-dizgi
     eşlemesinde 'star'a takılıp motoru YILDIZ tane koşturuyordu — tepe itki
     +%68.8 artefakt, ölçüldü).

Girdi-yankısı bekçisi: HRMA katı motoru basınç eğrisi tepesini tasarım Pc
girdisine birebir yankılar (ölçüldü: 4 farklı girdide Pc_curve_max == Pc_in).
Bu yüzden kayıtlarda tepe oda basıncı SKALAR skorlanabilir anahtar olarak
yazılmaz (eğri + notlarda taşınır); yankı davranışı değişirse buradaki test
bilerek kırılır ve kayıt politikası yeniden değerlendirilir.

Not: tam-DB uç sözleşmesi tests/test_correlation_endpoint.py'de; buradaki
koşular YALNIZ üç F3 kaydıyla yapılır (hızlı — Cantera yolu yok).
"""

import copy
import json
import math
import pathlib
import shutil
import subprocess

import pytest

from hrma.validation import record_adapters as ra
from hrma.validation.correlation_runner import (deterministic_view,
                                                run_correlation, to_markdown)
from hrma.validation.experiment_db import ensure_valid_record, load_records

REPO = pathlib.Path(__file__).resolve().parents[1]
KAYIT_DIZINI = REPO / "hrma" / "data" / "validation_records" / "solid"
PANEL_JS = REPO / "hrma" / "static" / "js" / "panels" / "correlation_panel.js"

F3_TEST_IDS = (
    "sol-nakka2000-kappa-kdx002",
    "sol-nakka2000-kappa-ksb001",
    "sol-nakka2000-kappa-ksb002",
)

# Tek kaynak: birim tablosu adaptörden (NIST SP 811 sabiti orada tanımlı)
LBF_N = ra.UNIT_TO_SI["lbf"]

# --- ÖLÇÜLMÜŞ sapma bantları (2026-08-18 koşusu; işaret: (tahmin-ölçüm)/ölçüm)
# Tolerans ±1.0 yüzde puanı: platform/derleme payı. Bant uydurulmadı —
# koşudan okundu ve kilitlendi; bilinçli model değişikliğinde güncellenir.
BANT_TOL = 1.0
# total_impulse BİLİNÇLİ olarak bantlarda YOK (19 Ağu 2026, F022-katı):
# impuls = m_p·g0·Isp cebirsel kopyası olduğundan artık skorlanmıyor
# (skipped_derived) — ölçülen kimlikler test_tahmin_tarafi_cebirsel_bag ve
# test_kopya_zinciri_skor_disi bekçilerinde. Eski kilitli bantlar kayıt
# olarak: kdx +15.26 / ksb001 +28.24 / ksb002 +28.94 (≈ kütle∘Isp bileşimi).
BANTLAR = {
    ("sol-nakka2000-kappa-kdx002", "burn_time"): -14.80,
    ("sol-nakka2000-kappa-kdx002", "isp"): +9.60,
    ("sol-nakka2000-kappa-kdx002", "propellant_mass"): +4.74,
    ("sol-nakka2000-kappa-kdx002", "thrust_peak"): +8.72,
    ("sol-nakka2000-kappa-ksb001", "burn_time"): -22.02,
    ("sol-nakka2000-kappa-ksb001", "isp"): +21.94,
    ("sol-nakka2000-kappa-ksb001", "propellant_mass"): +5.14,
    ("sol-nakka2000-kappa-ksb001", "thrust_peak"): -10.27,
    ("sol-nakka2000-kappa-ksb002", "burn_time"): -20.29,
    ("sol-nakka2000-kappa-ksb002", "isp"): +17.56,
    ("sol-nakka2000-kappa-ksb002", "propellant_mass"): +9.57,
    ("sol-nakka2000-kappa-ksb002", "thrust_peak"): -8.26,
}


# ---------------------------------------------------------------------------
# Fikstürler
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def kayitlar():
    """Üç F3 kaydı — üretim ağacından, şema kapısından geçerek."""
    out = {}
    for tid in F3_TEST_IDS:
        path = KAYIT_DIZINI / f"{tid}.json"
        assert path.is_file(), f"F3 kaydı yok: {path}"
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        ensure_valid_record(rec, path=path)
        out[tid] = rec
    return out


@pytest.fixture(scope="module")
def kosu(kayitlar):
    """Yalnız üç F3 kaydıyla korelasyon koşusu (hızlı, Cantera yolu yok)."""
    return run_correlation(records=list(kayitlar.values()))


def _skorlar(kosu_sonucu, test_id):
    for rr in kosu_sonucu["records"]:
        if rr["test_id"] == test_id:
            return rr
    raise AssertionError(f"koşuda kayıt yok: {test_id}")


# ---------------------------------------------------------------------------
# (a) Şema kapısı + üretim ağacı
# ---------------------------------------------------------------------------

class TestSemaKapisi:
    def test_kayitlar_uretim_agacindan_yukleniyor(self):
        """load_records üretim kapısı (klasör/tip/benzersizlik) geçilmeli."""
        recs = load_records(motor_type="solid")
        ids = {r["test_id"] for r in recs}
        for tid in F3_TEST_IDS:
            assert tid in ids, f"{tid} üretim ağacı yüklemesinde yok"

    def test_zorunlu_alanlar_ve_tipler(self, kayitlar):
        for tid, rec in kayitlar.items():
            assert rec["motor_type"] == "solid"
            assert rec.get("record_type", "static_fire") == "static_fire"
            assert rec["digitized"] is True, (
                f"{tid}: eğri/tepe değerler şekilden sayısallaştırıldı — "
                f"digitized bayrağı dürüstlük gereği true kalmalı")
            assert rec.get("synthetic", False) is False

    def test_kaynak_kunyesi(self, kayitlar):
        for tid, rec in kayitlar.items():
            src = rec["source"]
            assert "Nakka" in src["citation"]
            assert src["url"].startswith("https://www.nakka-rocketry.net/")
            assert src["access"] == "webpage"
            assert src["data_extraction"] == "figure_digitized"
            # Sayısallaştırma yöntemi ve okuma belirsizliği beyanlı olmalı
            assert "belirsizli" in src["extraction_note"], tid
            assert src["date_checked"] == "2026-08-18"

    def test_yayimlanmis_literatur_imli_dis_kullanici_iddia_edilmiyor(
            self, kayitlar):
        """F3 dürüstlük bekçisi: bu döngü YAYIMLANMIŞ veriyle kapandı."""
        for tid, rec in kayitlar.items():
            assert "published_literature" in rec.get("tags", []), tid
            assert "f3_korelasyon_dongusu" in rec.get("tags", []), tid
            notes = rec.get("notes", "")
            assert "YAYIMLANMIŞ LİTERATÜR" in notes, tid
            assert "DIŞ KULLANICI VERİSİ DEĞİLDİR" in notes, (
                f"{tid}: kayıt dış-kullanıcı verisi gibi okunabilir — "
                f"Ayberk ayağı ayrı kayıttır, iddia edilemez")

    def test_belirsizlik_uydurulmamis(self, kayitlar):
        """Kaynak gösterge sınıfı yayımlamıyor -> alan HİÇ yazılmaz."""
        for tid, rec in kayitlar.items():
            assert "measurement_uncertainty" not in rec, (
                f"{tid}: kaynak belirsizlik vermiyor; alan uydurulamaz")

    def test_katman_gerekceleri_kayitta(self, kayitlar):
        kdx = kayitlar["sol-nakka2000-kappa-kdx002"]
        assert kdx["source"]["confidence"] == "low"
        assert "grain_length" in kdx["source"]["extraction_note"], (
            "KDX-002 düşük güveninin gerekçesi (tane boyu çıkarımı) "
            "extraction_note'ta belgeli olmalı")
        ksb2 = kayitlar["sol-nakka2000-kappa-ksb002"]
        assert ksb2["source"]["confidence"] == "medium"
        assert ksb2["anomaly"]["flag"] is False
        ksb1 = kayitlar["sol-nakka2000-kappa-ksb001"]
        assert ksb1["anomaly"]["flag"] is True
        assert "tıkal" in ksb1["anomaly"]["note"] or \
            "TIKALI" in ksb1["anomaly"]["note"]

    def test_egri_impuls_tutarliligi(self, kayitlar):
        """Sayısallaştırılmış itki eğrisinin integrali beyan edilen toplam
        impulsla tutarlı olmalı (±%5 — ölçülen: -%0.5 / -%3.5 / +%2.4).

        Bu bekçi eğri bozulmasını (mutasyon M2 dahil) şema kapısından önce
        yakalar: eğri ile skalar beyan birbirinden bağımsız iki kaynak
        okumasıdır, tutarlılıkları ölçülmüştür.
        """
        for tid, rec in kayitlar.items():
            m = rec["measured"]
            curve = m.get("thrust_curve_n") or m.get("thrust_curve_lbf")
            unit = 1.0 if "thrust_curve_n" in m else LBF_N
            t, v = curve["time_s"], curve["value"]
            integral = sum((t[i + 1] - t[i]) * (v[i] + v[i + 1]) / 2.0
                           for i in range(len(t) - 1)) * unit
            beyan = m["total_impulse_ns"]
            fark = abs(integral - beyan) / beyan * 100.0
            assert fark <= 5.0, (
                f"{tid}: eğri integrali {integral:.0f} N·s, beyan {beyan} "
                f"N·s — fark %{fark:.1f} > %5 (eğri veya skalar bozulmuş)")

    def test_isp_impuls_kutle_cebirsel_bagi_olculdu(self, kayitlar):
        """Ölçüm tarafında Isp = I/(m·g0) özdeşliği tutmalı (kaynak böyle
        hesaplamış; üç skorlanan büyüklük bağımsız üç kanıt DEĞİLDİR —
        kayıt notlarında beyanlı, katı adaptöründe kopya-zinciri bekçisi yok).
        """
        g0 = 9.80665
        for tid, rec in kayitlar.items():
            m = rec["measured"]
            isp_hesap = m["total_impulse_ns"] / (m["propellant_mass_g"] / 1000.0 * g0)
            assert abs(isp_hesap - m["isp_s"]) <= 0.6, (
                f"{tid}: Isp özdeşliği bozuldu ({isp_hesap:.2f} vs "
                f"{m['isp_s']}) — alanlardan biri bozulmuş")


# ---------------------------------------------------------------------------
# (b) Korelasyon koşusu: determinizm + kilitli bantlar + katmanlar
# ---------------------------------------------------------------------------

class TestKorelasyonKosusu:
    def test_uc_kayit_da_ok(self, kosu):
        assert kosu["n_records"] == 3
        assert kosu["status_counts"] == {"ok": 3}
        assert kosu["runner_errors"] == []

    def test_deterministik(self, kayitlar, kosu):
        tekrar = run_correlation(records=list(kayitlar.values()))
        assert deterministic_view(tekrar) == deterministic_view(kosu), (
            "Aynı üç kayıtla iki koşu farklı sonuç verdi — determinizm "
            "sözleşmesi (spec 3.4) bozuldu")

    @pytest.mark.parametrize("anahtar", sorted(BANTLAR),
                             ids=lambda k: f"{k[0].rsplit('-', 1)[-1]}:{k[1]}")
    def test_skor_bantlari_kilitli(self, kosu, anahtar):
        test_id, quantity = anahtar
        rr = _skorlar(kosu, test_id)
        skor = rr["scores"].get(quantity)
        assert skor and skor.get("status") == "scored", (
            f"{test_id}/{quantity}: skorlanmadı ({skor}) — adaptör yolu "
            f"değişti veya kayıt bozuldu")
        beklenen = BANTLAR[anahtar]
        assert abs(skor["error_pct"] - beklenen) <= BANT_TOL, (
            f"{test_id}/{quantity}: hata %{skor['error_pct']:+.2f}, kilitli "
            f"bant %{beklenen:+.2f}±{BANT_TOL} — DB mi değişti model mi? "
            f"Bilinçli değişimde bandı ölçüp güncelle.")

    def test_katmanlar(self, kosu):
        """KSB-002 ana, KDX-002 low, KSB-001 anomaly — karantina bütünlüğü."""
        stats = kosu["statistics"]
        ana_idler = {e["test_id"] for c in stats["cells"]
                     for e in c["entries"]}
        low_idler = {e["test_id"] for c in stats["low_confidence_cells"]
                     for e in c["entries"]}
        anomali_idler = {e["test_id"] for e in stats["anomaly_entries"]}
        assert ana_idler == {"sol-nakka2000-kappa-ksb002"}
        assert low_idler == {"sol-nakka2000-kappa-kdx002"}
        assert anomali_idler == {"sol-nakka2000-kappa-ksb001"}
        # 4 skorlanan büyüklük / kayıt (5'ti; total_impulse 19 Ağu'da
        # F022-katı ile skor dışına alındı — BANTLAR yorumundaki gerekçe)
        assert len(stats["cells"]) == 4
        assert len(stats["low_confidence_cells"]) == 4
        assert len({e["quantity"] for e in stats["anomaly_entries"]}) == 4

    def test_tahmin_tarafi_cebirsel_bag(self, kosu, kayitlar):
        """Tahmin tarafında da I_pred = m_pred·g0·Isp_pred (kopya zinciri).

        total_impulse kütle+Isp hatasının bileşimidir; bağımsız üçüncü kanıt
        değildir. Bileşim özdeşliği ±0.5 puanla ölçülü kalmalı — artık skor
        yerine adaptör çıktısından ölçülür (F022-katı sonrası impuls
        skorlanmıyor; skorlanma bekçisi test_kopya_zinciri_skor_disi).
        """
        for tid in F3_TEST_IDS:
            ad = ra.adapt_record(kayitlar[tid])
            pred, meas = ad["predictions"], ad["measured_si"]
            em = pred["propellant_mass"] / meas["propellant_mass"] - 1.0
            ei = pred["isp"] / meas["isp"] - 1.0
            eI = pred["total_impulse"] / meas["total_impulse"] - 1.0
            bilesim = (1 + em) * (1 + ei) - 1
            assert abs(bilesim - eI) * 100.0 <= 0.5, (
                f"{tid}: impuls hatası kütle×Isp bileşiminden ayrıştı "
                f"(%{eI*100:+.2f} vs %{bilesim*100:+.2f}) — zincir varsayımı "
                f"değişti, kayıt notları ve bu bekçi güncellenmeli")

    def test_kopya_zinciri_skor_disi(self, kosu):
        """F022-katı bekçisi (19 Ağu 2026): isp+total_impulse birlikte
        ölçüldüğünde yalnız İLK halka (isp) skorlanır; total_impulse
        skipped_derived + derived_bases + adaptör notu taşır. Zincir
        sökülürse (mutasyon F3-M5) üç kayıtta birden kırmızı."""
        for tid in F3_TEST_IDS:
            rr = _skorlar(kosu, tid)
            assert rr["scores"]["isp"]["status"] == "scored", (
                f"{tid}: zincirin ilk halkası isp skorlanmalı")
            assert rr["scores"]["total_impulse"]["status"] == \
                "skipped_derived", (
                f"{tid}: total_impulse skor dışı değil — F022-katı zinciri "
                f"söküldü mü? ({rr['scores']['total_impulse']})")
            assert "total_impulse" in rr["derived_bases"]
            assert any("F022-kati" in n for n in rr["adapter_notes"]), (
                f"{tid}: F022-kati beyan notu yok — sessiz skor-dışı "
                f"bırakma yasak, not zorunlu")

    def test_girdi_yankisi_skorlanmiyor(self, kayitlar, kosu):
        """Tepe oda basıncı skalar skorlanamaz: tahmin, tasarım Pc girdisinin
        birebir yankısıdır (ölçüldü). Yankı kaybolursa bu test kırılır ve
        kayıt politikası bilinçli yeniden değerlendirilir."""
        for tid, rec in kayitlar.items():
            for key in rec["measured"]:
                base, _ = ra.split_quantity_key(key)
                base = ra.BASE_ALIASES.get(base, base)
                assert base != "chamber_pressure_peak", (
                    f"{tid}.{key}: tepe oda basıncı skalar olarak eklenmiş — "
                    f"bu skor tasarım Pc girdisinin yankısı olur (kayıt "
                    f"notlarındaki gerekçeye bakın)")
            # Yankının kendisi hâlâ geçerli mi? (politikanın ölçülü dayanağı)
            rr = _skorlar(kosu, tid)
            pred_peak = None
            res = ra.adapt_record(rec)
            pred_peak = res["predictions"].get("chamber_pressure_peak")
            pc_in = rec["inputs"]["chamber_pressure_psia"] * 6894.757293168
            assert pred_peak is not None
            # Ölçülen yankı sapması ~2e-6 (eğri float zinciri); gerçek bir
            # model tahmini yüzdelerle ayrışırdı — eşik 1e-4 bağıl.
            assert abs(pred_peak - pc_in) / pc_in < 1e-4, (
                f"{tid}: Pc tepe tahmini artık girdi yankısı DEĞİL "
                f"({pred_peak:.0f} vs {pc_in:.0f} Pa) — model değişmiş; "
                f"tepe basınç skorlanabilir hâle gelmiş olabilir, kayıt "
                f"politikasını bilinçli güncelle")
            assert rr is not None  # koşuda mevcut


# ---------------------------------------------------------------------------
# F3 adaptör onarımlarının bekçileri (#1 n_segments, #2 a-n beyanı, #3 star)
# ---------------------------------------------------------------------------

class TestAdaptorOnarimlari:
    def test_n_segments_motora_ulasiyor(self, kayitlar):
        """Onarım #1: kayıttaki 4 segment motora kablolu olmalı. Kablo
        koparsa motor L/D konvansiyonuyla 7 segment varsayar — fark ölçüldü
        (t_b %13, F_tepe %15); bu test kablosuz hâlde kırılır."""
        rec = kayitlar["sol-nakka2000-kappa-ksb002"]
        kablolu = ra.adapt_record(rec)
        assert any("n_segments=4" in n for n in kablolu["adapter_notes"]), (
            "adaptör n_segments'i kayıttan aldığını beyan etmiyor")
        kablosuz = copy.deepcopy(rec)
        del kablosuz["geometry"]["n_segments"]
        serbest = ra.adapt_record(kablosuz)
        fark = abs(serbest["predictions"]["thrust_peak"]
                   - kablolu["predictions"]["thrust_peak"])
        assert fark / kablolu["predictions"]["thrust_peak"] > 0.05, (
            "n_segments kaydını silmek tahmini değiştirmedi — kablo kopmuş "
            "(override motora ulaşmıyor) ya da motor segment sayısına "
            "duyarsızlaşmış; onarım #1 bekçisi")

    def test_an_beyani_gercek_katsayilar(self, kayitlar):
        """Onarım #2: assumed_defaults motorun GERÇEKTE çözdüğü a-n'i
        raporlamalı. Eski kod koşulsuz 0.005/0.35 beyan ediyordu; knsb için
        motorun çözdüğü a=0.0022334 ölçüldü."""
        res = ra.adapt_record(kayitlar["sol-nakka2000-kappa-ksb002"])
        a = res["assumed_defaults"]["burn_rate_a"]
        assert a != 0.005, (
            "assumed_defaults yine sabit 0.005 beyan ediyor — kullanılmayan "
            "varsayımın beyanı dürüstlük ihlali (onarım #2 geri alınmış)")
        assert 0.0015 < a < 0.0035, (
            f"knsb için beyan edilen a={a} ölçülen katalog bandının dışında "
            f"— katalog bilinçli değiştiyse bandı güncelle")

    def test_grain_tipi_sozcuk_sinirli(self, kayitlar):
        """Onarım #3: 'astarlanmış' sözcüğü 'star' belirtecine takılamaz.

        Ölçülen artefakt: alt-dizgi eşlemesiyle KSB-002 yıldız tane koştu,
        tepe itki +%68.8 saptı. Davranış bekçisi: yalnız grain_geometry
        metni farklı iki kayıt AYNI tahminleri vermeli."""
        rec = kayitlar["sol-nakka2000-kappa-ksb002"]
        assert "astarlanmış" in rec["geometry"]["grain_geometry"], (
            "bekçinin öncülü değişti: kayıt metninde 'astarlanmış' yok — "
            "bekçiyi gerçek metne göre güncelle")
        sade = copy.deepcopy(rec)
        sade["geometry"]["grain_geometry"] = "BATES, 4 segment"
        p1 = ra.adapt_record(rec)["predictions"]
        p2 = ra.adapt_record(sade)["predictions"]
        assert p1 == p2, (
            "grain_geometry metnindeki Türkçe sözcükler tahmini değiştirdi — "
            "belirteç eşlemesi yine alt-dizgiye dönmüş olabilir (onarım #3)")


# ---------------------------------------------------------------------------
# Panel sözleşmesi — node düzeyi kanıt (panel JS'e DOKUNULMAZ)
# ---------------------------------------------------------------------------

_PANEL_HARNESS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const [,, panelPath, bodyPath] = process.argv;

function makeNode() {
    const node = {
        innerHTML: '', style: {}, children: [],
        appendChild(child) { node.children.push(child); return child; },
        insertBefore(child) { node.children.push(child); return child; },
        addEventListener() {},
        get firstElementChild() { return { _from: node, innerHTML: node.innerHTML }; },
    };
    return node;
}

const created = [];
global.document = {
    readyState: 'loading',
    addEventListener() {},
    getElementById() { return null; },
    createElement() { const n = makeNode(); created.push(n); return n; },
};
global.setInterval = () => 0;
global.clearInterval = () => {};
global.window = global;

let registered = null;
global.window.AnalysisDock = {
    ui: {
        t: (key, fallback) => fallback || key,
        tf: (key, params, fallback) => String(fallback || key).replace(/\{(\w+)\}/g, (m, k) => params[k]),
        TD: 'padding:2px;', TBL: 'width:100%;',
        badge: (txt) => `<span>${txt}</span>`,
        sectionTitle: (s) => `<h4>${s}</h4>`,
        // ÖH D31 arayuz-panel a1 (OH-D30-06): paneller sayıyı dock'un tek
        // biçimleyicisinden (ui.num → I18N.number, sözlük yoksa toFixed) basar;
        // ikiz dock'un aynı sözleşmeyi taşıması gerekir (ana model, 14 Eyl).
        num: (value, digits) => (typeof value !== 'number' || !isFinite(value))
            ? ((value === null || value === undefined) ? '' : String(value))
            : ((typeof digits === 'number') ? value.toFixed(digits) : String(value)),
    },
    getMotorType: () => 'solid',
    register: (spec) => { registered = spec; },
};

require(path.resolve(panelPath));

const CP = global.window.CorrelationPanel;
if (!CP) { console.error('FAIL: CorrelationPanel disari verilmedi'); process.exit(1); }
if (!registered || registered.id !== 'correlation') {
    console.error('FAIL: panel AnalysisDock.register cagirmadi'); process.exit(1);
}

const body = JSON.parse(fs.readFileSync(bodyPath, 'utf8'));

const mainCells = body.cells.filter(c => c.layer === 'main');
const ordered = CP._orderCells(mainCells);
if (!ordered.length || ordered[0].motor_type !== 'solid') {
    console.error('FAIL: orderCells solid satirlari one almadi'); process.exit(1);
}

const mainHtml = CP._cellTableHtml(mainCells);
for (const needle of ['sol-nakka2000-kappa-ksb002', 'thrust_peak', 'propellant_mass', 'burn_time']) {
    if (!mainHtml.includes(needle)) { console.error('FAIL: ana tabloda eksik: ' + needle); process.exit(1); }
}

const root = makeNode();
CP._render(body, root);
const allHtml = created.map(n => n.innerHTML).join('\n');
for (const needle of ['sol-nakka2000-kappa-ksb002', 'sol-nakka2000-kappa-kdx002',
                      'sol-nakka2000-kappa-ksb001', 'Low-confidence records', 'Anomalous records']) {
    if (!allHtml.includes(needle)) { console.error('FAIL: render ciktisinda eksik: ' + needle); process.exit(1); }
}
console.log('PANEL-OK cells=' + body.cells.length);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_panel_gercek_render_uc_katmani_gosteriyor(kosu, tmp_path):
    """correlation_panel.js GERÇEK kaynak kodu, üretim fonksiyonlarıyla
    (correlation_cells + to_markdown) kurulmuş uç gövdesini node üzerinde
    hatasız çizer; üç F3 kaydı üç ayrı katmanda görünür. Panel dosyasına
    dokunulmadığının ve veri sözleşmesine uyduğunun kanıtı."""
    from hrma.validation.status_report import correlation_cells

    body = {
        "status": "ok",
        "db_hash": kosu["db_content_hash"],
        "cached": False,
        "generated_s": 0.1,
        "record_counts": {
            "total": kosu["n_records"],
            "scored": kosu["status_counts"].get("ok", 0),
            "insufficient_inputs": 0, "not_supported": 0, "runner_error": 0,
        },
        "cells": correlation_cells(kosu["statistics"]),
        "markdown": to_markdown(kosu),
    }
    harness = tmp_path / "f3_panel_harness.js"
    harness.write_text(_PANEL_HARNESS, encoding="utf-8")
    body_json = tmp_path / "f3_body.json"
    body_json.write_text(json.dumps(body), encoding="utf-8")

    proc = subprocess.run(
        ["node", str(harness), str(PANEL_JS), str(body_json)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, (
        f"panel node koşumu kırıldı:\n{proc.stdout}\n{proc.stderr}")
    assert "PANEL-OK" in proc.stdout


def test_markdown_ozeti_kayitlari_aniyor(kosu):
    """to_markdown çıktısı üç kaydı da anmalı (rapor/panel markdown yolu)."""
    md = to_markdown(kosu)
    for tid in F3_TEST_IDS:
        assert tid in md
    assert "Anomaly-flagged records" in md
