# tests — ÖH Dalga-26 · kulvar fea-cfd · aşama 3 bekçileri
"""ÖH D26 / fea-cfd a3 — onbir kalemin bekçileri.

Kalemler (defter kimlikleri):
  OH-B4-05  CFD örtük yol: yayımlanan MUSCL kalibrasyonu bayat + kazanç
            iddiasının ÖLÇÜTÜ beyansız
  P6B4-12   ``critical_response_table`` ürün tüketicisi 0 → ölü yüzey
  P8B1-10   termal zincirde UZAMSAL yakınsama denetlenmiyor ve beyanı yok
  P8B1-11   termal künye "Bartz h" diyor, çağıranın h'sini sormuyor
  P8B2-08   ``max_bore_strain`` mutlak maksimum → basma gerinimi kopma
            uzamasıyla oranlanıyor
  P8B2-14   katı motorda FEA alanı kasa silindirini kapsamıyor, kapsam
            beyanı hüküm alanının yanında değil
  P8B2-15   ``hrma.fea.MODULE_STATUS`` paket envanterini kapsamıyor
  P8B3-11   yedek enjektör: delikler plakanın dışında + uydurma plaka ölçüsü
  P8B3-12   yedek enjektör: bilinmeyen/eşlenmemiş tip sessizce yeniden adlanır
  P8B3-13   yedek motor kesiti: açı künyesi uydurma varsayılandan
  P8B3-14   yedek motor kesiti: genleşme oranı iki farklı sayı

ÖLÇÜMLER: docs/scofield/raw/OH/D26/fea-cfd/a3/{once,sonra}_a3.json
TERS-MUTASYON: .../mutasyon_a3.json
"""
import json

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# P8B2-15 — MODULE_STATUS envanteri
# ---------------------------------------------------------------------------
class TestP8B215ModulEnvanteri:
    """Envanter ANAHTAR ADIYLA değil KÜME olarak sınanır (savcı S1 §2.2)."""

    def test_envanter_paketle_birebir(self):
        import hrma.fea as fea
        env = fea.module_status_inventory()
        assert env["missing"] == [], (
            "pakette olup MODULE_STATUS'ta olmayan modül: "
            + ", ".join(env["missing"]))
        assert env["extra"] == [], (
            "MODULE_STATUS'ta olup pakette olmayan beyan: "
            + ", ".join(env["extra"]))

    def test_olculen_iki_eksik_anahtar_artik_var(self):
        """ÖLÇÜLDÜ (taban 7751531): bridge ve mesh_planar YOKTU."""
        from hrma.fea import MODULE_STATUS
        for ad in ("bridge", "mesh_planar"):
            assert ad in MODULE_STATUS, f"{ad} beyanı yeniden düştü"

    def test_eksik_anahtar_adiyla_reddedilir(self):
        """Kapı gerçekten kapı mı: anahtar sökülünce ADIYLA patlamalı."""
        import hrma.fea as fea
        yedek = dict(fea.MODULE_STATUS)
        try:
            fea.MODULE_STATUS.pop("bridge")
            with pytest.raises(AssertionError, match="bridge"):
                fea.assert_module_status_complete()
        finally:
            fea.MODULE_STATUS.clear()
            fea.MODULE_STATUS.update(yedek)
        fea.assert_module_status_complete()          # geri döndü


# ---------------------------------------------------------------------------
# P8B2-08 — kabul payı ÇEKME gerinimindendir
# ---------------------------------------------------------------------------
def _basma_baskin_kesit():
    """ÖLÇÜLEN vaka: 8 uçlu yıldız — port çevresinde basma ucu baskın."""
    from hrma.fea.mesh_planar import build_grain_section_mesh
    from hrma.fea.planar_grain import solve_plane_strain_section
    from hrma.fea.structural_axisym import Material

    def r_ic(th):
        return 0.020 + (0.040 - 0.020) * np.cos(8 * np.asarray(th)) ** 2

    mesh = build_grain_section_mesh(r_ic, 0.050, 120, 6)
    mat = Material(E=5.0e6, nu=0.499, yield_strength=1.0e6, name="HTPB")
    return solve_plane_strain_section(mesh, mat, 3.0e6, "bonded_rigid", 0.30)


class TestP8B208GerinimIsareti:

    def test_vaka_hala_basma_baskin(self):
        """Bekçinin çapası: yayımlanan işaretli maksimum NEGATİF olmalı."""
        res = _basma_baskin_kesit()
        assert res.max_bore_strain < 0.0, (
            "vaka değişmiş — bu bekçi basma-baskın kesit üstünde kurulu")

    def test_pay_basma_geriniminden_HESAPLANMAZ(self):
        """ÖLÇÜLDÜ (taban): pay 132,455 = 0,30/|−0,0022649| (BASMA).

        Kopma uzaması bir ÇEKME kabiliyetidir (NASA SP-8073); pay yalnız
        en büyük çekme geriniminden gelir → 0,30/0,0011524 = 260,333.
        """
        res = _basma_baskin_kesit()
        cekme = float(np.max(res.bore_strain_nodal))
        assert cekme > 0.0
        beklenen = 0.30 / cekme
        assert res.strain_margin == pytest.approx(beklenen, rel=1e-9), (
            f"pay {res.strain_margin} — çekmeden beklenen {beklenen}")
        yanlis = 0.30 / abs(res.max_bore_strain)
        assert res.strain_margin != pytest.approx(yanlis, rel=1e-6), (
            "pay hâlâ mutlak maksimumdan (basma gerinimi) hesaplanıyor")

    def test_iki_uc_de_alanda_ADIYLA_durur(self):
        res = _basma_baskin_kesit()
        blok = res.meta["port_lif_gerinimi"]
        assert blok["maks_cekme"] > 0.0
        assert blok["maks_basma"] < 0.0
        assert blok["pay_hangi_gerinimden"] == "cekme"
        assert "ÇEKME" in blok["_basis"]

    def test_basma_kabiliyeti_not_modelled_listesinde(self):
        res = _basma_baskin_kesit()
        assert any("BASMA KABİLİYETİ" in str(x)
                   for x in res.meta["not_modelled"]), (
            "basma tarafının kabul ölçütü olmadığı beyan edilmiyor")

    def test_hic_cekme_yoksa_pay_UYDURULMAZ(self):
        """Fail-closed: çekme yoksa pay None + adlı gerekçe."""
        from hrma.fea.mesh_planar import build_grain_section_mesh
        from hrma.fea.planar_grain import solve_plane_strain_section
        from hrma.fea.structural_axisym import Material
        mesh = build_grain_section_mesh(0.020, 0.050, 48, 4)
        mat = Material(E=5.0e6, nu=0.499, yield_strength=1.0e6, name="HTPB")
        res = solve_plane_strain_section(mesh, mat, 3.0e6, "bonded_rigid",
                                         0.30)
        # Bu vakada çekme VARDIR; kapının kendisi ayrıca sınanır:
        eps = np.asarray(res.bore_strain_nodal)
        if float(np.max(eps)) > 0.0:
            assert res.strain_margin is not None
        else:                                        # pragma: no cover
            assert res.strain_margin is None
            assert "ÇEKME" in res.meta["strain_margin_durumu"]


# ---------------------------------------------------------------------------
# P8B3-11/-12/-13/-14 — yedek çizimler
# ---------------------------------------------------------------------------
def _fig(j):
    return json.loads(j) if isinstance(j, str) else j


def _iz(f, ad):
    return next((t for t in f.get("data", []) if t.get("name") == ad), None)


def _ann(f):
    return [a.get("text") for a in (f.get("layout") or {}).get(
        "annotations", []) if a.get("text")]


class TestP8B311DelikPlakaIcinde:
    """ÖLÇÜLDÜ (taban): 61/91/127 delikte en dış delik 60/75/90 mm,
    plaka yarıçapı sabit 60 mm — üç vakada delikler plakanın DIŞINDA."""

    @pytest.mark.parametrize("n_holes", [7, 19, 37, 61, 91, 127])
    def test_delikler_plakanin_icinde(self, n_holes):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_injector_plot(
            {"n_holes": n_holes, "hole_diameter": 1.5}, "showerhead"))
        plaka = _iz(f, "Injector Plate")
        delikler = next(t for t in f["data"]
                        if str(t.get("name", "")).startswith(
                            "Injection Holes"))
        r_plaka = float(np.max(np.abs(np.asarray(plaka["x"], dtype=float))))
        r_delik = float(np.max(np.hypot(
            np.asarray(delikler["x"], dtype=float),
            np.asarray(delikler["y"], dtype=float))))
        assert r_delik <= r_plaka + 1e-9, (
            f"{n_holes} delikte en dış delik {r_delik:.2f} mm, plaka "
            f"yarıçapı {r_plaka:.2f} mm — delikler plakanın dışında")

    def test_cozucu_plaka_capi_vermediyse_OLCU_BILDIRILMEZ(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_injector_plot(
            {"n_holes": 127, "hole_diameter": 1.5}, "showerhead"))
        ipucu = _iz(f, "Injector Plate")["hovertemplate"]
        assert "schematic outline" in ipucu, (
            "plaka ipucu hâlâ çözücüden gelmeyen bir ÖLÇÜ bildiriyor: "
            + ipucu)

    def test_cozucu_plaka_capi_verdiyse_O_KULLANILIR(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_injector_plot(
            {"n_holes": 37, "hole_diameter": 1.5, "plate_diameter": 200.0},
            "showerhead"))
        plaka = _iz(f, "Injector Plate")
        r = float(np.max(np.abs(np.asarray(plaka["x"], dtype=float))))
        assert r == pytest.approx(100.0, rel=1e-9)
        assert "200.0 mm" in plaka["hovertemplate"]


class TestP8B312TipAdiUydurulmaz:
    """ÖLÇÜLDÜ (taban): coax_swirl → 'Pintle Injector Design',
    impinging_doublet ve BİLİNMEYEN tip → 'Showerhead Injector Design'."""

    def test_bilinmeyen_tip_CIZILMEZ(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_injector_plot(
            {"n_holes": 12, "hole_diameter": 1.2}, "bilinmeyen_tip_xyz"))
        assert not f.get("data"), "bilinmeyen tip için hâlâ çizim üretiliyor"
        metin = " ".join(_ann(f)) + str(
            (f.get("layout") or {}).get("title", ""))
        assert "bilinmeyen_tip_xyz" in metin
        assert "Showerhead" not in metin, (
            "bilinmeyen tip başka bir enjektörün adıyla sunuluyor")

    @pytest.mark.parametrize("tip,veri,desen", [
        ("coax_swirl", {"outer_diameter": 40.0, "pintle_diameter": 12.0,
                        "gap": 2.0}, "pintle"),
        ("impinging_doublet", {"n_holes": 12, "hole_diameter": 1.2},
         "showerhead"),
    ])
    def test_eslenen_tip_ADIYLA_beyanli(self, tip, veri, desen):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_injector_plot(veri, tip))
        baslik = str((f.get("layout") or {}).get("title", {}).get("text", ""))
        assert tip in baslik, (
            f"istenen tip {tip!r} başlıkta yok: {baslik!r}")
        assert desen in baslik.lower(), (
            "hangi şematiğin kullanıldığı beyan edilmiyor: " + baslik)

    def test_kanonik_tip_beyan_EKLEMEZ(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_injector_plot(
            {"n_holes": 12, "hole_diameter": 1.2}, "showerhead"))
        baslik = str((f.get("layout") or {}).get("title", {}).get("text", ""))
        assert "Schematic drawn with" not in baslik


_MOTOR_TAM = {"chamber_length": 0.30, "chamber_diameter": 0.10,
              "port_diameter_initial": 0.03, "port_diameter_final": 0.06,
              "throat_diameter": 0.020, "exit_diameter": 0.080}


class TestP8B313AciKunyesiUydurulmaz:
    """ÖLÇÜLDÜ (taban): açı verilmeden 'α = 15.0°' ve 'β = 12.0°' basılıyordu
    (imzadaki .get varsayılanları)."""

    def test_aci_verilmediyse_KUNYE_YOK(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_motor_plot(dict(_MOTOR_TAM)))
        acilar = [t for t in _ann(f) if "α" in t or "β" in t]
        assert acilar == [], f"uydurma açı künyesi basıldı: {acilar}"

    def test_aci_verilmediyse_ACI_IZI_de_YOK(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_motor_plot(dict(_MOTOR_TAM)))
        adlar = [str(t.get("name", "")) for t in f["data"]]
        assert not any("Angle" in a or "Convergent" in a or "Divergent" in a
                       for a in adlar), (
            "açı yayı/doğrusu hâlâ çiziliyor: " + str(adlar))

    def test_aci_verildiyse_O_SAYI_basilir(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_motor_plot(
            dict(_MOTOR_TAM, convergent_angle=30.0, divergent_angle=14.0)))
        metin = " ".join(_ann(f))
        assert "α = 30°" in metin and "β = 14°" in metin, metin

    def test_yedek_uyarisi_aci_eksigini_de_soyler(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_motor_plot(dict(_MOTOR_TAM)))
        uyari = next(t for t in _ann(f) if "Fallback" in t)
        assert "half-angles" in uyari, (
            "uyarı yalnız lüle konturunu kapsıyor: " + uyari)


class TestP8B314GenlesmeOraniTekSayi:
    """ÖLÇÜLDÜ (taban): ipucu 'Expansion Ratio: 25.0', eksen yazısı
    'ε = 16.0' — aynı figürde aynı büyüklük iki farklı sayı."""

    def test_cozucu_epsilonu_HER_IKI_YERDE_ayni(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_motor_plot(dict(_MOTOR_TAM,
                                           expansion_ratio=25.0)))
        ipucu = _iz(f, "Nozzle")["hovertemplate"]
        eksen = next(t for t in _ann(f) if t.startswith("ε"))
        assert "25.0" in ipucu and "25.0" in eksen, (ipucu, eksen)
        assert "16.0" not in ipucu and "16.0" not in eksen, (ipucu, eksen)

    def test_cozucu_epsilonu_yoksa_GEOMETRIK_oldugu_soylenir(self):
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_motor_plot(dict(_MOTOR_TAM)))
        eksen = next(t for t in _ann(f) if t.startswith("ε"))
        ipucu = _iz(f, "Nozzle")["hovertemplate"]
        assert "geometric" in eksen and "geometric" in ipucu, (eksen, ipucu)
        assert "16.0" in eksen

    def test_bos_sozluk_hala_cizmiyor(self):
        """P8B3-15 kapısı (D22) BOZULMADI."""
        from hrma.visualization import visualization as vz
        f = _fig(vz.create_motor_plot({}))
        assert not f.get("data")


# ---------------------------------------------------------------------------
# P8B1-11 — h(z)'nin kaynağı ÇAĞIRANIN beyanıdır
# ---------------------------------------------------------------------------
def _termal_kosu(h_basis=None, na=8, nr=2, t_end=1.0, n_t=21):
    from hrma.fea.mesh_axisym import build_wall_mesh
    from hrma.fea.thermal_axisym import (AmbientBC, ConvectionBC,
                                         ThermalMaterial, solve_transient)
    z = np.linspace(0.0, 0.30, 21)
    kontur = np.column_stack([z, np.full_like(z, 0.05)])
    mesh = build_wall_mesh(kontur, 0.003, n_axial=na, n_radial=nr)
    mat = ThermalMaterial(rho=8000.0, cp=500.0, k=16.0, name="SS304")
    return solve_transient(
        mesh, mat, np.linspace(0.0, t_end, n_t),
        ConvectionBC(h=1234.0, T_inf=2500.0, h_basis=h_basis),
        AmbientBC(h=10.0, T_ambient=293.15, emissivity=0.0), 293.15)


class TestP8B111HKaynagi:
    """ÖLÇÜLDÜ (taban): çağıran SABİT 1234 W/(m²K) verdiğinde bile künye
    'iç yüzeyde yalnız konveksiyon; Bartz h' diyordu."""

    def test_not_modelled_MODEL_ADI_uydurmaz(self):
        res = _termal_kosu()
        bartz = [x for x in res.meta["not_modelled"] if "Bartz" in str(x)]
        assert bartz == [], (
            "künye çağıranın vermediği bir korelasyon adını ilan ediyor: "
            + str(bartz))

    def test_beyan_edilmediyse_ADIYLA_soylenir(self):
        from hrma.fea.thermal_axisym import H_KAYNAGI_BEYAN_EDILMEDI
        res = _termal_kosu()
        assert res.meta["h_kaynagi"]["ic_yuzey"] == H_KAYNAGI_BEYAN_EDILMEDI

    def test_beyan_verildiyse_AYNEN_yayimlanir(self):
        res = _termal_kosu(h_basis="Bartz 1965 Denk. 4 (HeatTransferAnalyzer)")
        assert res.meta["h_kaynagi"]["ic_yuzey"] == (
            "Bartz 1965 Denk. 4 (HeatTransferAnalyzer)")

    def test_konveksiyon_olmayan_yuzey_de_ADIYLA_beyanli(self):
        res = _termal_kosu()
        assert "h" in res.meta["h_kaynagi"]["dis_yuzey"]


# ---------------------------------------------------------------------------
# P8B1-10 — UZAMSAL yakınsama ölçülür ve HER koşuda beyan edilir
# ---------------------------------------------------------------------------
def _termal_auto(refiner=None, na=16, nr=4):
    from hrma.fea.mesh_axisym import build_wall_mesh
    from hrma.fea.thermal_axisym import (AmbientBC, ConvectionBC,
                                         ThermalMaterial,
                                         solve_transient_auto)
    z = np.linspace(0.0, 0.30, 41)
    kontur = np.column_stack([z, np.full_like(z, 0.05)])
    mk = (lambda a, r: build_wall_mesh(kontur, 0.003, int(a), int(r)))
    mat = ThermalMaterial(rho=8000.0, cp=500.0, k=16.0, name="SS304")
    res = solve_transient_auto(
        mk(na, nr), mat, 3.0,
        ConvectionBC(h=5000.0, T_inf=3000.0),
        AmbientBC(h=10.0, T_ambient=293.15, emissivity=0.0), 293.15,
        mesh_refiner=(mk if refiner else None))
    return res, mk


class TestP8B110UzamsalYakinsama:
    """ÖLÇÜLDÜ (taban): meta'da 'zaman_adimi' vardı, uzamsal karşılığı YOKTU
    ve mesh hiç inceltilmiyordu."""

    def test_blok_HER_kosuda_var(self):
        res, _ = _termal_auto(refiner=False)
        assert "uzamsal_yakinsama" in res.meta, (
            "uzamsal eksen sessizce yok — beyan bile edilmiyor")

    def test_refiner_yoksa_DENETLENMEDI_der_yakinsadi_DEMEZ(self):
        res, _ = _termal_auto(refiner=False)
        blok = res.meta["uzamsal_yakinsama"]
        assert blok["denetlendi"] is False
        assert blok["converged"] is None and blok["rel_change"] is None
        assert "DENETLENMEDİ" in blok["beyan"]

    def test_refiner_varsa_OLCULUR(self):
        res, _ = _termal_auto(refiner=True)
        blok = res.meta["uzamsal_yakinsama"]
        assert blok["denetlendi"] is True
        assert blok["ince_mesh"]["n_axial"] == 2 * blok["kaba_mesh"]["n_axial"]
        assert blok["ince_mesh"]["n_radial"] == (
            2 * blok["kaba_mesh"]["n_radial"])
        assert blok["rel_change"] is not None and blok["rel_change"] >= 0.0
        assert blok["converged"] is True
        assert "%" in blok["beyan"]

    def test_olculen_merdiven_yeniden_uretilir(self):
        """ÖLÇÜLDÜ (taban, once_a3.json): 16×4 → 2191,8468 K,
        32×8 → 2190,7475 K, 64×16 → 2190,4739 K."""
        res, _ = _termal_auto(refiner=True)
        blok = res.meta["uzamsal_yakinsama"]
        assert blok["kaba_peak_wall_T"] == pytest.approx(2191.8468, abs=5e-3)
        assert blok["ince_peak_wall_T"] == pytest.approx(2190.7475, abs=5e-3)

    def test_kopru_urun_yolunda_DENETLIYOR(self):
        """Köprü mesh'i kuran katmandır; refiner'ı O vermeli."""
        import inspect
        from hrma.fea import bridge
        kaynak = inspect.getsource(bridge.run_thermal_from_motor)
        assert "mesh_refiner=" in kaynak, (
            "ürün yolunda uzamsal denetim bağlı değil — beyan 'denetlenmedi' "
            "kalır (P8B1-10)")


# ---------------------------------------------------------------------------
# P8B2-14 — hükmün KAPSAMI hüküm sayısının YANINDA
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def _kati_yapisal():
    import contextlib
    import io
    import os
    os.environ.setdefault("HRMA_HEADLESS", "1")
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
        from hrma.fea import bridge
    app.config["TESTING"] = True
    cli = app.test_client()
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = cli.post("/calculate_solid", json={
            "motor_name": "D26A3", "propellant_type": "apcp",
            "grain_type": "bates", "chamber_pressure": 40.0,
            "thrust": 5000.0, "burn_time": 3.0, "chamber_diameter": 100.0,
            "grain_length": 500.0, "core_diameter": 30.0,
            "expansion_ratio": 8.0})
        md = r.get_json() or {}
        md = md.get("motor", md)
        return bridge.run_structural_from_motor(md), md


class TestP8B214HukumKapsami:
    """ÖLÇÜLDÜ (taban): mesh z ∈ [0; 168,558] mm = TAM OLARAK lüle konturu;
    tane boyu 450,3 mm; kasa silindiri alana hiç girmiyor; min SF 1,2691
    kapsam beyanı OLMADAN yayımlanıyordu."""

    def test_kapsam_alani_HUKUM_YANINDA(self, _kati_yapisal):
        out, _ = _kati_yapisal
        assert out["status"] == "ok"
        assert "hukum_kapsami" in out, (
            "kapsam beyanı hüküm sayısının yanında değil")
        assert out["min_safety_factor"] is not None

    def test_kapsanmayan_bolge_ADIYLA_sayilir(self, _kati_yapisal):
        out, _ = _kati_yapisal
        k = out["hukum_kapsami"]
        assert k["kamara_uzantisi_eklendi"] is False
        assert any("kasa" in str(x) or "silindir" in str(x)
                   for x in k["kapsanmayan"]), k["kapsanmayan"]
        assert "güvenli" in k["_basis"], (
            "kapsam dışı bölgenin 'güvenli' DEMEK OLMADIĞI söylenmiyor")

    def test_alan_gercekten_lule_konturu_kadar(self, _kati_yapisal):
        out, md = _kati_yapisal
        k = out["hukum_kapsami"]
        pts = np.asarray(md["nozzle_contour"]["points"], dtype=float)
        assert k["z_araligi_m"][0] == pytest.approx(float(pts[:, 0].min()),
                                                    abs=1e-9)
        assert k["z_araligi_m"][1] == pytest.approx(float(pts[:, 0].max()),
                                                    abs=1e-9)

    def test_tane_boyu_alanla_KARSILASTIRILIR(self, _kati_yapisal):
        out, _ = _kati_yapisal
        tane = out["hukum_kapsami"]["tane"]
        assert tane is not None
        assert tane["grain_length_m"] > tane["fea_alani_uzunlugu_m"]
        assert "dışında" in tane["beyan"]


# ---------------------------------------------------------------------------
# P6B4-12 — ölü yüzey kalktı, imza sözleşmesi yaşıyor
# ---------------------------------------------------------------------------
class TestP6B412OluYuzeyKalkti:
    """ÖLÇÜLDÜ (taban): ``critical_response_table``ın ürün tüketicisi SIFIR
    (hrma/ altında stability paketi dışında hiçbir atıf yok)."""

    def test_yuzey_yayimlanmiyor(self):
        import hrma.stability as st
        from hrma.stability import response as RS
        assert not hasattr(st, "critical_response_table")
        assert not hasattr(RS, "critical_response_table")
        assert "critical_response_table" not in getattr(st, "__all__", [])

    def test_canli_yol_DURUYOR(self):
        """Kaldırılan davranışın tamamı critical_response_real + çağıranın
        kendi mod döngüsüyle elde edilir."""
        from hrma.stability import (critical_response_real, damping_budget)
        b = damping_budget({"nozzle": -120.0})
        satir = critical_response_real(b["total_damping_1_s"], 1.0e4)
        assert satir["interpretation"] == "threshold_not_verdict"
        assert "verdict" not in satir

    def test_imza_sozlesmesi_YASIYOR(self):
        """D25 onarımının kalıcı ürünü: tek kaynak imza kümesi."""
        from hrma.stability import damping as DM
        assert DM.DAMPING_BUDGET_SIGNATURE_KEYS
        b = DM.damping_budget({"nozzle": -120.0})
        assert DM.DAMPING_BUDGET_SIGNATURE_KEYS.issubset(b.keys())

    def test_urun_tuketicisi_hala_sifir(self):
        """Yüzey geri gelirse ÖNCE tüketici bağlanmalı (ölçülür)."""
        import os
        import hrma
        kok = os.path.dirname(os.path.dirname(os.path.abspath(hrma.__file__)))
        bulunan = []
        for dizin, _, dosyalar in os.walk(os.path.join(kok, "hrma")):
            for d in dosyalar:
                if not d.endswith((".py", ".js", ".html")):
                    continue
                yol = os.path.join(dizin, d)
                try:
                    metin = open(yol, encoding="utf-8").read()
                except (OSError, UnicodeDecodeError):    # pragma: no cover
                    continue
                if "critical_response_table" in metin:
                    bulunan.append(os.path.relpath(yol, kok))
        disarisi = [y for y in bulunan
                    if not y.replace(os.sep, "/").startswith(
                        "hrma/stability/")]
        assert disarisi == [], (
            "ölü yüzeyin adı stability paketi dışında yeniden geçiyor: "
            + ", ".join(disarisi))


# ---------------------------------------------------------------------------
# OH-B4-05 — yayımlanan MUSCL kalibrasyonu BAYAT DEĞİL
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def _cfd_kalibrasyon():
    from hrma.cfd.grid_axisym import build_grid_from_wall
    from hrma.cfd.steady import solve_steady_axisym
    from tests.cfd.conftest import (LULE_GAMMA, LULE_L_CONV, LULE_L_DIV,
                                    LULE_P0, LULE_PB, LULE_R, LULE_T0,
                                    lule_duvar_yaricapi)
    z = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, 61)
    izgara = build_grid_from_wall(z, lule_duvar_yaricapi(z), 12)
    ortak = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R,
                 Pb=LULE_PB)
    acik = solve_steady_axisym(izgara, max_iters=30000, **ortak)
    ortuk = solve_steady_axisym(izgara, max_iters=30000,
                                time_integrator="line_implicit_j", **ortak)
    return acik, ortuk


class TestOHB405KalibrasyonBayatDegil:
    """ÖLÇÜLDÜ (taban 7751531): kaynak 'MUSCL cfl 25→4452' diyordu, bugünkü
    kod 5512 üretiyor — yayımlanan kalibrasyon BAYATLAMIŞTI (kapı OH-Z5-14
    ile geldi ve koşu 4452'de durmuyor)."""

    def test_kalibrasyon_TEK_KAYNAKTA(self):
        from hrma.cfd.steady import IMPLICIT_CALIBRATION as C
        for ad in ("case", "gate", "measured_on", "gain_basis",
                   "muscl_explicit_iters", "muscl_implicit_iters_by_cfl",
                   "first_order_explicit_iters",
                   "first_order_implicit_iters"):
            assert ad in C, f"{ad} beyanı yok"
        assert "öz-tutarlılık" in C["gate"]

    def test_beyan_edilen_sayilar_YENIDEN_URETILIR(self, _cfd_kalibrasyon):
        from hrma.cfd.steady import IMPLICIT_CALIBRATION as C
        acik, ortuk = _cfd_kalibrasyon
        assert acik["converged"] and ortuk["converged"]
        # Bant: iterasyon sayacı tam sayıdır ama platformlar arası son
        # basamakta oynayabilir (float sözleşmesi) — %2 pay.
        assert acik["iterations"] == pytest.approx(
            C["muscl_explicit_iters"], rel=0.02), (
            f"açık yol {acik['iterations']} it, beyan "
            f"{C['muscl_explicit_iters']} — kalibrasyon bayatladı")
        beklenen = C["muscl_implicit_iters_by_cfl"][25.0]
        assert ortuk["iterations"] == pytest.approx(beklenen, rel=0.02), (
            f"örtük yol {ortuk['iterations']} it, beyan {beklenen} — "
            "kalibrasyon bayatladı (OH-B4-05)")

    def test_bayat_sayilar_ARTIK_beyan_degil(self):
        from hrma.cfd.steady import IMPLICIT_CALIBRATION as C
        canli = C["muscl_implicit_iters_by_cfl"]
        bayat = C["stale_pre_gate"]["muscl_implicit_iters_by_cfl"]
        assert canli != bayat
        assert bayat[25.0] == 4452, "tarihsel kayıt korunmalı"
        assert canli[25.0] != 4452

    def test_kazanc_ORTAK_olcut_altinda(self, _cfd_kalibrasyon):
        """Kazanç ancak iki yol da AYNI hüküm ölçütünü geçtiğinde ölçülür:
        öz-tutarlılık kapısı iki yolda da şema kalıntısını sınar."""
        acik, ortuk = _cfd_kalibrasyon
        for r in (acik, ortuk):
            assert r["scheme_residual_exceeds_tol"] is False, (
                "hüküm şemanın kalıntısıyla desteklenmiyor — kazanç "
                "karşılaştırması dürüst değil")
        assert ortuk["iterations"] < acik["iterations"], (
            "bu vakada ölçülen kazanç kayboldu")

    def test_cfl_secimi_MUSCL_minimumu(self):
        from hrma.cfd.steady import (DEFAULT_CFL_IMPLICIT_MAX,
                                     IMPLICIT_CALIBRATION as C)
        tablo = C["muscl_implicit_iters_by_cfl"]
        en_iyi = min(tablo, key=lambda k: tablo[k])
        assert en_iyi == DEFAULT_CFL_IMPLICIT_MAX, (
            f"varsayılan CFL {DEFAULT_CFL_IMPLICIT_MAX}, ölçülen minimum "
            f"{en_iyi} — kalibrasyonun KARARI da bayatlamış")
