# -*- coding: utf-8 -*-
"""ÖH Dalga-32 · kulvar fea-cfd · aşama 1/2 — onarım bekçileri.

Kalemler:

* **P8B1-04** (FABLE ŞART, Fable TOPLU fizik / hüküm-20) — D25 a3 kanıtı
  nihai kodla yenilendi; kaynak yorumu "Material reddediyor" demekten
  vazgeçti.
* **OH-FT-08** (Fable fea-cfd-03) — ``SAINT_VENANT_KAT`` künyesi artık
  İKİ etki kanalını da anıyor ve merdivende eşiğin değişimini yayımlıyor.
* **OH-D19-28** (FABLE ŞART) — ayırt edici iki iddia
  ``tests/test_d15_fea_viz_a3.py``de; burada yalnız VARLIKLARI kilitlenir.

Her iddia ters mutasyonla kırmızıya düştüğü ölçülerek doğrulanmıştır
(kanıt ``docs/scofield/raw/OH/D32/fea-cfd/a1/mutasyon.json``).
"""

import json
import os

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, "docs", "scofield", "raw", "OH", "D32",
                     "fea-cfd", "a1")
D25_KANIT = os.path.join(KOK, "docs", "scofield", "raw", "OH", "D25",
                         "fea-cfd", "a3", "sonra_a3.json")
STRUCT_PY = os.path.join(KOK, "hrma", "fea", "structural_axisym.py")
D15_TEST = os.path.join(KOK, "tests", "test_d15_fea_viz_a3.py")

KILITLI_KAPI = ("Material kabul + min_safety_factor=None + "
                "safety_factor_durumu")


def _oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def d25_p8b104():
    return json.loads(_oku(kanit_gerekli(D25_KANIT)))["P8B1-04"]


@pytest.fixture(scope="module")
def once_kanit():
    return json.loads(_oku(kanit_gerekli(os.path.join(KANIT, "once.json"))))


# ===========================================================================
# P8B1-04 — FABLE ŞART: kanıt nihai kodla yenilendi + yorum düzeltildi
# ===========================================================================
class TestP8B104SartKanitYenilemesi:
    """ŞART METNİ (hüküm-20): D25 a3 kanıtı nihai kodla yeniden alınsın.

    TABAN (dd1dcddc) ölçümü — ``once.json`` → ``P8B1-04_sart``:
      sart_1 False (kilitli satırlar "Material ValueError" diyordu),
      sart_2 False (kapı metni "çağrıları REDDEDİLİR" idi),
      sart_3 False (kabul listesi yalnız [0,49]).
    Oysa NİHAİ kod nu = 0,4995 ve 0,49999'u KABUL ediyor ve emniyet
    hükmünü vermiyordu: kanıt ile ürün AYRIŞMIŞTI.
    """

    def test_kilitli_satirlar_uc_alani_TASIYOR(self, d25_p8b104):
        kilitli = [s for s in d25_p8b104["satirlar"]
                   if float(s["nu"]) >= 0.495]
        assert kilitli, "kanıt kilitlenme bölgesini hiç ölçmüyor"
        for s in kilitli:
            assert s["kapi"] == KILITLI_KAPI, s
            assert s["Material_kabul"] is True, s
            assert s["min_safety_factor"] is None, s
            assert s["safety_factor_durumu"], s
            assert "VERİLMEDİ" in s["safety_factor_durumu"], s

    def test_kapi_metni_HEAD_ile_AYNI(self, d25_p8b104):
        from hrma.fea.structural_axisym import Q4_LOCKING_NU_MAX
        head = (f"nu >= {Q4_LOCKING_NU_MAX:g} koşumlarında EMNİYET HÜKMÜ "
                "VERİLMEZ (min_safety_factor = None, gerekçe "
                "meta['safety_factor_durumu']); bu çözücüde karma/B-bar "
                "formülasyonu YOKTUR")
        metinler = {s["kilitlenme_beyani"]["kapi"]
                    for s in d25_p8b104["satirlar"]
                    if "kilitlenme_beyani" in s}
        assert metinler == {head}, metinler

    def test_Material_kabulu_0_4995_ve_0_49999_iceriyor(self, d25_p8b104):
        kabul = d25_p8b104["Material_nu_ust_siniri_kabul"]
        assert 0.4995 in kabul and 0.49999 in kabul, kabul

    def test_URUN_gercekten_boyle_davraniyor(self):
        """Kanıt metni değil, ÜRÜN ölçülür: Material reddetmez, hüküm yok."""
        import numpy as np
        from hrma.fea import structural_axisym as sa
        from hrma.fea.mesh_axisym import build_wall_mesh
        a, b, p = 0.05, 0.08, 10.0e6
        kontur = np.array([[0.0, a], [0.20, a]])
        for nu in (0.4995, 0.49999):
            mat = sa.Material(E=6.0e6, nu=nu, yield_strength=1.0e6)
            assert mat.nu == nu
        mat = sa.Material(E=6.0e6, nu=0.4995, yield_strength=1.0e6)
        m = build_wall_mesh(kontur, b - a, 16, 4, offset_mode="radial")
        r = sa.solve_pressure(m, mat, p, axial_fix="both_ends")
        assert r.min_safety_factor is None
        assert "VERİLMEDİ" in r.meta["safety_factor_durumu"]
        assert r.von_mises_nodal is not None and r.von_mises_nodal.size

    def test_KAYNAK_YORUMU_artik_Material_reddediyor_DEMIYOR(self):
        """ŞARTIN ikinci yarısı: yanlış yorum cümlesi kaldırıldı."""
        src = _oku(STRUCT_PY)
        assert "eşiğin üstünde çağrı reddediliyor" not in src, (
            "yanlış yorum geri geldi: Material nu >= 0,495'i REDDETMİYOR")
        assert "eşiğin üstünde EMNİYET HÜKMÜ verilmiyor" in src


# ===========================================================================
# OH-FT-08 — SAINT_VENANT_KAT'ın İKİNCİ ETKİ KANALI
# ===========================================================================
class TestOHFT08KatIkinciKanal:
    """Kat'ın tek kanalı maske DEĞİL: P8B2-09 kapısının eşiği de ondan türer.

    ÖLÇÜLDÜ (``once.json`` → ``OH-FT-08``), ürün hibrit koşusu
    (2 kN / 30 bar, nu = 0,27; iki-kip bağıl farkı %7,030):
    kat 1,25/2,0/2,5/3,0/5,0 → eşik %39,808/%15,112/%7,923/%4,154/%0,314.
    2,5'te hüküm DURUYOR (pay 0,89 puan), 3,0'da GERİ ÇEKİLİYOR.
    """

    MERDIVEN = (1.25, 2.0, 2.5, 3.0, 5.0)

    def _esik(self, kat, nu):
        from hrma.fea import structural_axisym as sa
        eski = sa.SAINT_VENANT_KAT
        try:
            sa.SAINT_VENANT_KAT = float(kat)
            return float(sa.kisit_yeri_duyarlilik_esigi(float(nu)))
        finally:
            sa.SAINT_VENANT_KAT = eski

    def test_esik_KAT_ile_degisiyor(self, once_kanit):
        nu = float(once_kanit["OH-FT-08"]["nu"])
        esikler = [self._esik(k, nu) for k in self.MERDIVEN]
        assert esikler == sorted(esikler, reverse=True), esikler
        assert max(esikler) / min(esikler) > 100.0, (
            "eşik merdivende neredeyse sabit — ikinci kanal iddiası "
            "ölçümle desteklenmiyor")

    def test_hibrit_hukmu_merdivende_CEVRILIYOR(self, once_kanit):
        ft = once_kanit["OH-FT-08"]
        nu = float(ft["nu"])
        fark = float(ft["olculen_bagil_fark"]["hibrit"])
        asildi = {k: fark > self._esik(k, nu) for k in self.MERDIVEN}
        assert asildi[2.5] is False, (
            "varsayılan katta hibrit kapısı aşılıyor — ürün davranışı "
            "sessizce değişmiş")
        assert asildi[3.0] is True, (
            "kat 3,0'da da aşılmıyor: kat'ın ikinci kanalı hükmü "
            "çevirmiyor demektir, künye iddiası ölçümle çürür")
        assert len(set(asildi.values())) > 1

    def test_KAYNAK_KUNYESI_ikinci_kanali_ADIYLA_aniyor(self):
        src = _oku(STRUCT_PY)
        i = src.find("# OH-D24-07 — KAT SEÇİMİNİN DUYARLILIĞI")
        j = src.find("SAINT_VENANT_KAT = ", i)
        assert i >= 0 and j > i
        kunye = src[i:j]
        assert "kisit_yeri_duyarlilik_esigi" in kunye, (
            "künye hâlâ tek etki kanalını (maske) anıyor — OH-FT-08")
        assert "OH-FT-08" in kunye
        # Merdivenin sayıları künyede DURUYOR (beyan ölçüme bağlı).
        for parca in ("39,808", "15,112", "7,923", "4,154", "0,314"):
            assert parca in kunye, parca

    def test_RUNTIME_kunye_ikinci_kanali_yayimliyor(self):
        """Ürün yüzü: kapı künyesi kat'ı ve iki kanalı makine-okur basar."""
        from hrma.app import app
        from hrma.fea import bridge
        from hrma.fea.structural_axisym import SAINT_VENANT_KAT
        app.config["TESTING"] = True
        sivi = app.test_client().post("/calculate_liquid", json={
            "motor_name": "D32FT08", "thrust": 2000.0, "burn_time": 30.0,
            "chamber_pressure": 15.0, "mixture_ratio": 2.2,
            "fuel_type": "rp1", "oxidizer_type": "lox",
            "expansion_ratio": 5.0}).get_json()
        out = bridge.run_structural_from_motor(sivi)
        kapi = out["meta"]["kisit_duyarliligi"]["kapi"]
        assert kapi["uygulanir"] is True
        assert kapi["saint_venant_kat"] == pytest.approx(SAINT_VENANT_KAT)
        assert "kisit_yeri_duyarlilik_esigi" not in kapi
        assert "İKİ kanaldan" in kapi["kat_etki_kanallari"]
        assert "saint_venant_hukum_maskesi" in kapi["kat_etki_kanallari"]
        # Pay = eşik − ölçülen fark; işareti kapının hükmüyle tutarlı.
        assert kapi["pay"] == pytest.approx(
            kapi["esik"] - kapi["bagil_fark"], rel=1e-12)
        assert (kapi["pay"] < 0.0) is bool(kapi["asildi"])


# ===========================================================================
# OH-D19-28 — FABLE ŞART: iki ayırt edici iddia YERİNDE duruyor
# ===========================================================================
class TestOHD1928SartIddialariYerinde:
    """ŞART: ayrışan kip bekçisine iki ayırt edici iddia eklenecekti.

    İddiaların KENDİSİ ``tests/test_d15_fea_viz_a3.py``dedir (orada
    koşulur); burada sessizce silinmelerine karşı kilit konur.
    TABAN ölçümü (``once.json`` → ``OH-D19-28_bekci``): dört göstergenin
    DÖRDÜ de False idi.
    """

    def _govde(self, ad):
        src = _oku(D15_TEST)
        i = src.find("def " + ad)
        assert i >= 0, ad
        j = src.find("\n    def ", i + 1)
        k = src.find("\nclass ", i + 1)
        son = min([x for x in (j, k, len(src)) if x > 0])
        return src[i:son]

    def test_iddia_1_iki_kip_BAGIMSIZ_olculuyor(self):
        g = self._govde(
            "test_AYRISAN_kipte_yayimlanan_kip_yakinsamasi_GERCEKTEN_"
            "olculuyor")
        assert "_bagimsiz_rel(" in g
        assert "rel_yayimlanan" in g and "rel_birincil" in g
        assert "rel=1e-9" in g and "rel=1e-3" in g

    def test_iddia_2_bayrak_devralma_enjeksiyonla_sinaniyor(self):
        g = self._govde(
            "test_AYRISAN_kipte_yayimlanan_kip_BAYRAGI_devralmiyor")
        assert "monkeypatch" in g
        assert "converged_yayimlanan_kip\"] is False" in g
        assert "converged_birincil_kip\"] is True" in g
