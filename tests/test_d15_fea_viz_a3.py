# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · kulvar fea-viz · aşama 3/3 — onarım bekçileri.

Her test, onarımı geçici olarak geri alan TERS MUTASYONLA kırmızıya
düştüğü ölçülerek doğrulanmıştır (kanıt:
``docs/scofield/raw/OH/D15/fea-viz/a3/mutasyon.json``).

Kalemler: P8B4-18, P8B4-25, P8B2-12, P8B2-07, P8B2-04, P8B1-08,
P8B1-09, P8B1-03.
"""

import json

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def _metinler(fig_json):
    """Figürdeki bütün metin taşıyıcıları (iz + anotasyon)."""
    d = json.loads(fig_json) if isinstance(fig_json, str) else fig_json
    parcalar = []
    for tr in d.get("data", []):
        for anahtar in ("text", "hovertext", "hovertemplate", "name"):
            v = tr.get(anahtar)
            if isinstance(v, str):
                parcalar.append(v)
            elif isinstance(v, list):
                parcalar += [s for s in v if isinstance(s, str)]
    for an in (d.get("layout", {}).get("annotations") or []):
        if isinstance(an.get("text"), str):
            parcalar.append(an["text"])
    return d, "\n".join(parcalar)


# ===========================================================================
# P8B4-18 — pintle kesiti BOŞ girdide ölçü uydurmaz
# ===========================================================================
class TestP8B418PintleSemaBeyani:
    """Boş girdide 50/25/1,5 mm ölçüleri teknik resim diliyle basılmaz."""

    def _bos(self):
        from hrma.visualization.visualization import (
            create_pintle_cross_section)
        return _metinler(create_pintle_cross_section({}))

    def test_bos_girdide_uydurma_olcu_basilmaz(self):
        _d, metin = self._bos()
        for yasak in ("D_outer = 50.0", "D_outer: 50.0",
                      "D_pintle = 25.0", "D_pintle: 25.0",
                      "gap = 1.50", "Gap: 1.50"):
            assert yasak not in metin, (
                f"boş girdide uydurma ölçü basıldı: {yasak!r}")

    def test_bos_girdide_anulus_alani_iddia_edilmez(self):
        _d, metin = self._bos()
        assert "Flow Area: 124.9" not in metin
        assert "Flow Area: not computable" in metin

    def test_bos_girdide_cift_oklu_olcu_cizgisi_cizilmez(self):
        """Çift oklu ölçü çizgisi bir İDDİADIR; bildirilmemiş boyuta konmaz."""
        d, _metin = self._bos()
        oklu = [an for an in (d.get("layout", {}).get("annotations") or [])
                if an.get("showarrow") and an.get("arrowside") == "end+start"]
        assert oklu == [], f"boş girdide {len(oklu)} ölçü çizgisi çizildi"

    def test_bos_girdide_sema_beyani_ve_imalat_uyarisi_var(self):
        _d, metin = self._bos()
        assert metin.lower().count("schematic") >= 3
        assert metin.count("not reported") >= 3
        assert "Do not machine" in metin, (
            "kardeş create_swirl_injector'ın disiplini uygulanmamış")

    def test_gercek_boyut_verilince_sayi_basilir(self):
        """Regresyon çapası: gerçek girdide ölçüler AYNEN yayımlanır."""
        from hrma.visualization.visualization import (
            create_pintle_cross_section)
        _d, metin = _metinler(create_pintle_cross_section(
            {"outer_diameter": 62.0, "pintle_diameter": 18.0, "gap": 0.9}))
        assert "D_outer = 62.0 mm" in metin
        assert "D_pintle = 18.0 mm" in metin
        assert "gap = 0.90 mm" in metin
        assert "Do not machine" not in metin

    def test_kardes_swirl_deseni_bozulmadi(self):
        from hrma.visualization.visualization import create_swirl_injector
        _d, metin = _metinler(create_swirl_injector({}))
        assert "Do not machine" in metin
        assert "not reported" in metin


# ===========================================================================
# P8B4-25 — motor kesiti ile enjektör yüz görünümü aynı delik sayısını der
# ===========================================================================
class TestP8B425DelikSayisiTekKaynak:

    def _kesit(self, motor):
        from hrma.visualization.visualization import (
            create_improved_motor_cross_section)
        return _metinler(create_improved_motor_cross_section(motor, "hybrid"))

    def _motor(self, n_holes, n_ori):
        return {
            "chamber_diameter": 100.0, "chamber_length": 0.3,
            "throat_diameter": 30.0, "exit_diameter": 60.0,
            "injector": {"n_holes": n_holes},
            "injector_design": {"injector_type": "showerhead",
                                "number_of_orifices": n_ori},
        }

    def test_kesit_kullanici_yuzundeki_sayiyi_basar(self):
        _d, metin = self._kesit(self._motor(61, 7))
        assert "Showerhead pattern: 61 axial orifices" in metin
        assert "Showerhead pattern: 7 axial orifices" not in metin

    def test_kesit_sayinin_kaynagini_soyler(self):
        _d, metin = self._kesit(self._motor(61, 7))
        assert "results['injector'].n_holes" in metin

    def test_iki_model_celisiyorsa_celiski_beyan_edilir(self):
        _d, metin = self._kesit(self._motor(61, 7))
        assert "differs from injector_design.number_of_orifices (7)" in metin

    def test_celiski_yoksa_celiski_notu_yazilmaz(self):
        _d, metin = self._kesit(self._motor(7, 7))
        assert "Showerhead pattern: 7 axial orifices" in metin
        assert "differs from" not in metin

    def test_sayi_hic_yoksa_sessiz_12_basilmaz(self):
        motor = {"chamber_diameter": 100.0, "chamber_length": 0.3,
                 "throat_diameter": 30.0, "exit_diameter": 60.0,
                 "injector_design": {"injector_type": "showerhead"}}
        _d, metin = self._kesit(motor)
        assert "axial orifices" not in metin or "12 axial orifices" not in metin
        assert "orifice count not reported" in metin

    def test_yuz_gorunumu_yoksa_tasarim_alani_kaynagiyla_kullanilir(self):
        motor = {"chamber_diameter": 100.0, "chamber_length": 0.3,
                 "throat_diameter": 30.0, "exit_diameter": 60.0,
                 "injector_design": {"injector_type": "showerhead",
                                     "number_of_orifices": 9}}
        _d, metin = self._kesit(motor)
        assert "Showerhead pattern: 9 axial orifices" in metin
        assert "injector_design.number_of_orifices" in metin


# ===========================================================================
# P8B2-12 — kamara silindiri uzantısına makullük kapısı
# ===========================================================================
class TestP8B212KamaraUzantisiKapisi:

    def _sivi(self):
        from hrma.app import app
        app.config["TESTING"] = True
        c = app.test_client()
        r = c.post("/calculate_liquid", json={
            "motor_name": "D15A3", "thrust": 25000.0, "burn_time": 30.0,
            "chamber_pressure": 70.0, "mixture_ratio": 2.2,
            "fuel_type": "rp1", "oxidizer_type": "lox",
            "expansion_ratio": 12.0})
        return r.get_json()

    def test_saglikli_motorlar_kapidan_gecer(self):
        from hrma.fea.bridge import extract_structural_inputs
        gir = extract_structural_inputs(self._sivi())
        assert gir["status"] == "ok"
        mk = gir["_basis"]["kamara_uzantisi"]["makullik"]
        assert mk is not None and mk["gecti"] is True
        # Ölçülen sağlıklı değer 1,02; eşik 60.
        assert mk["uzunluk_yaricap_orani"] < 5.0

    def test_imza_cakismasinda_1000x_uzanti_reddedilir(self):
        import copy
        from hrma.fea.bridge import extract_structural_inputs
        carpik = copy.deepcopy(self._sivi())
        sa = carpik.setdefault("structural_analysis", {})
        sa["chamber_analysis"] = {"wall_thickness_used_mm": 2.0,
                                  "design_mode": "verify"}
        sa["design_parameters"] = {"material": "inconel_718"}
        sa["material_properties"] = {"yield_strength": 1.1e9}
        gir = extract_structural_inputs(carpik)
        assert gir["status"] == "NOT_MODELLED", (
            "300 mm'lik kamara 300 m olarak mesh'e girdi")
        assert any("chamber_length" in m for m in gir["missing"])
        assert gir["warning"]["code"] == "warn.fea.chamber_extension_implausible"

    def test_esik_tek_kaynaktan_gelir(self):
        from hrma.fea.bridge import CHAMBER_EXTENSION_MAX_L_OVER_R
        assert CHAMBER_EXTENSION_MAX_L_OVER_R == 60.0


# ===========================================================================
# P8B2-07 — küçük gerinim / geometrik lineerlik sınırı
# ===========================================================================
class TestP8B207KucukGerinimSiniri:

    def _coz(self, pc_bar):
        import hrma.fea.planar_grain as PG
        mat = PG.Material(name="apcp", E=6.0e6, nu=0.4995)
        ref = PG.solve_grain_with_refinement(
            r_inner=0.020, r_outer=0.050, material=mat,
            bore_pressure_pa=pc_bar * 1e5, strain_capability=0.35)
        return getattr(ref, "result", ref)

    def test_50_barda_pay_yayimlanir(self):
        r = self._coz(50)
        assert r.meta["kucuk_gerinim_durumu"] == "gecerli"
        assert r.strain_margin is not None and r.strain_margin > 1.0

    def test_200_barda_uyari_bandi(self):
        r = self._coz(200)
        assert r.meta["kucuk_gerinim_durumu"] == "uyari_bandi"
        assert r.strain_margin is not None
        kodlar = [u["code"] for u in (r.meta.get("uyarilar") or [])]
        assert "warn.fea.planar_grain_small_strain_warn" in kodlar

    def test_800_barda_pay_geri_cekilir(self):
        r = self._coz(800)
        assert abs(r.max_bore_strain) > 0.05
        assert r.meta["kucuk_gerinim_durumu"] == "asildi"
        assert r.strain_margin is None, (
            "%10 gerinimde kabul payı hüküm gibi yayımlandı")
        assert r.meta.get("strain_margin_geri_cekme")
        kodlar = [u["code"] for u in (r.meta.get("uyarilar") or [])]
        assert "warn.fea.planar_grain_small_strain_exceeded" in kodlar

    def test_not_modelled_geometrik_lineerlik_kalemi_var(self):
        r = self._coz(50)
        assert any("GEOMETRİK LİNEERLİK" in s
                   for s in r.meta["not_modelled"])

    def test_esikler_tek_kaynaktan(self):
        from hrma.fea.planar_grain import (
            SMALL_STRAIN_LIMIT, SMALL_STRAIN_WARN)
        assert SMALL_STRAIN_WARN == 0.02 and SMALL_STRAIN_LIMIT == 0.05


# ===========================================================================
# P8B2-04 — profil ⟷ kontur İÇ istasyon hizası
# ===========================================================================
class TestP8B204IcIstasyonHizasi:

    def _kur(self):
        import numpy as np
        import hrma.fea.bridge as BR
        from hrma.app import app
        app.config["TESTING"] = True
        c = app.test_client()
        hib = (c.post("/calculate", json={
            "motor_name": "d15a3", "thrust": 2000, "burn_time": 10,
            "of_ratio": 6.0, "chamber_pressure": 30.0,
            "fuel_type": "htpb", "oxidizer_type": "n2o"}).get_json()
            or {}).get("motor") or {}
        gir = BR.extract_structural_inputs(hib, include_chamber=False)
        kontur = np.asarray(gir["contour"], dtype=float)
        capa = BR._motor_bogaz_adaylari(hib)["h_g_W_m2K"] or {}
        hg0 = float(list(capa.values())[0])
        z, r = kontur[:, 0], kontur[:, 1]
        prof = {"x_mm": (z * 1000.0).tolist(),
                "h_g": (hg0 * (float(np.min(r)) / r) ** 1.8).tolist(),
                "T_recovery": np.full(z.size, 2900.0).tolist()}
        return hib, prof

    def test_hizali_profil_gecer(self):
        import hrma.fea.bridge as BR
        hib, prof = self._kur()
        assert BR.extract_thermal_inputs(hib, prof)["status"] == "ok"

    def test_ic_istasyonlari_kaydirilmis_profil_reddedilir(self):
        import numpy as np
        import hrma.fea.bridge as BR
        hib, prof = self._kur()
        bozuk = {k: list(v) for k, v in prof.items()}
        x = np.asarray(prof["x_mm"], dtype=float)
        tt = (x - x[0]) / (x[-1] - x[0])
        bozuk["x_mm"] = (x[0] + (x[-1] - x[0]) * tt ** 4).tolist()
        # Uçlar AYNEN korunuyor — eski kapı bunu göremiyordu.
        assert abs(bozuk["x_mm"][0] - x[0]) < 1e-9
        assert abs(bozuk["x_mm"][-1] - x[-1]) < 1e-9
        g = BR.extract_thermal_inputs(hib, bozuk)
        assert g["status"] == "NOT_MODELLED"
        assert "boğaz hizası" in " ".join(g["missing"])

    def test_esik_tek_kaynaktan(self):
        from hrma.fea.bridge import THERMAL_PROFILE_THROAT_TOL
        assert THERMAL_PROFILE_THROAT_TOL == 0.02


# ===========================================================================
# P8B1-08 — M-matris ölçümü + fiziksel aralık denetimi
# ===========================================================================
class TestP8B108MaksimumIlkesi:

    def _mesh_ve_cozum(self, n_axial, n_radial, h_yuksek):
        import numpy as np
        import hrma.fea.thermal_axisym as TA
        from hrma.fea.mesh_axisym import build_wall_mesh
        z = np.linspace(0.0, 0.30, 400)
        kontur = np.column_stack([z, np.full_like(z, 0.05)])
        mesh = build_wall_mesh(kontur, 0.004, n_axial=n_axial,
                               n_radial=n_radial)
        mat = TA.ThermalMaterial(name="celik", k=45.0, rho=7800.0, cp=460.0)
        zc = mesh.nodes[:, 0]
        zmid = 0.5 * (zc.min() + zc.max())

        def _h(zz):
            return np.where(np.asarray(zz) < zmid, 1.0, h_yuksek)
        return TA.solve_transient(
            mesh, mat, np.linspace(0.0, 0.64, 33),
            TA.ConvectionBC(h=_h, T_inf=3400.0),
            TA.AdiabaticBC(), 293.15)

    def test_kutle_matrisi_beyani_kosulsuz_iddia_etmez(self):
        sonuc = self._mesh_ve_cozum(200, 2, 45000.0)
        beyan = sonuc.meta["kutle_matrisi"]
        assert "YETERLİ" in beyan and "M-matris" in beyan
        assert "geri Euler ile ayrık maksimum ilkesi korunur" not in beyan

    def test_m_matris_olculur_ve_yayimlanir(self):
        sonuc = self._mesh_ve_cozum(200, 2, 45000.0)
        mm = sonuc.meta["m_matris"]
        assert mm["olculdu"] is True
        assert set(("kosegen_disi_giris", "pozitif_giris", "pozitif_oran",
                    "m_matris_mi")) <= set(mm)

    def test_yuksek_enboy_meshte_ihlal_yakalanir(self):
        import numpy as np
        sonuc = self._mesh_ve_cozum(8, 32, 90000.0)
        ad = sonuc.meta["aralik_denetimi"]
        assert ad["olculdu"] is True
        assert ad["ihlal"] is True, (
            "yalnız ısıtan sınır koşullarıyla alan aralık dışına çıktı ama "
            "hiçbir kapı bunu görmedi")
        assert ad["alt_asim_K"] > 100.0
        assert float(np.min(sonuc.T_history)) < ad["kabul_alt_K"]
        assert sonuc.meta["m_matris"]["m_matris_mi"] is False
        kodlar = [u["code"] for u in (sonuc.meta.get("uyarilar") or [])]
        assert ("warn.fea.thermal_discrete_max_principle_violated" in kodlar)

    def test_saglikli_meshte_ihlal_yok(self):
        sonuc = self._mesh_ve_cozum(200, 2, 45000.0)
        ad = sonuc.meta["aralik_denetimi"]
        assert ad["ihlal"] is False
        assert (sonuc.meta.get("uyarilar") or []) == []


# ===========================================================================
# P8B1-09 — yayımlanan kip kendi yakınsamasını kanıtlar
# ===========================================================================
class TestP8B109YayimlananKipYakinsamasi:

    def test_yayimlanan_kip_yakinsamasi_olculur(self):
        from hrma.app import app
        from hrma.fea.bridge import run_structural_from_motor
        app.config["TESTING"] = True
        c = app.test_client()
        sivi = c.post("/calculate_liquid", json={
            "motor_name": "D15A3K", "thrust": 25000.0, "burn_time": 30.0,
            "chamber_pressure": 70.0, "mixture_ratio": 2.2,
            "fuel_type": "rp1", "oxidizer_type": "lox",
            "expansion_ratio": 12.0}).get_json()
        out = run_structural_from_motor(sivi)
        kd = out["meta"]["kisit_duyarliligi"]
        h = out["meta"]["hukum"]
        # ÇEVRİLEN FİKSTÜR ÖNCÜLÜ (ÖH D19, kulvar fea-cfd, [F4]):
        # Bu test "bu fikstürde karşıt kip kötümserdir, dolayısıyla
        # yayımlanan kip birincilden farklıdır" öncülüne dayanıyordu.
        # Öncül D19'da GEÇERSİZLEŞTİ: karşıt kipin (z_max) kötümserliği
        # yapay rijit-cisim kısıtının yakınsamayan tepesinden geliyordu;
        # hüküm Saint-Venant bandının dışına taşınınca iki kip %5,2
        # içinde anlaşıyor (ölçüm: 512x24'te 1,4754x → 1,0519x,
        # docs/scofield/raw/OH/D19/fea-cfd/a1/sonra_f4_hukum.json) ve bu
        # fikstürde birincil kip (z_min) kötümser kalıyor.
        # Testin ASIL iddiası — "yayımlanan kip kendi yakınsamasını
        # kanıtlar, başka kipin geçmişini DEVRALMAZ" — korunur; artık
        # her iki dal da adıyla sınanır.
        assert kd["yayimlanan_kip"] in ("z_min", "z_max")
        assert "converged_yayimlanan_kip" in h
        assert h["converged"] == (h["converged_birincil_kip"]
                                  and h["converged_yayimlanan_kip"])
        if kd["yayimlanan_kip"] != kd["birincil_kip"]:
            yk = kd["yayimlanan_kip_yakinsamasi"]
            assert yk is not None and yk["olculdu"] is True
            assert "rel_change" in yk and "tol" in yk
        else:
            # Birincil kip yayımlanıyorsa yakınsama geçmişi ZATEN o kipe
            # aittir — devralma yoktur; ürün bunu beyanla söylemeli ve
            # ayrı bir ölçüm uydurmamalıdır.
            assert "yayimlanan_kip_yakinsamasi" not in kd, kd.keys()
            assert h["converged_yayimlanan_kip"] is True
            assert kd["yayimlanan_kip"] == kd["birincil_kip"]

    def test_AYRISAN_kipte_yayimlanan_kip_yakinsamasi_GERCEKTEN_olculuyor(self):
        """AYRIŞAN fikstür: yayımlanan kip birincilden BAŞKA (OH-D19-28).

        Yukarıdaki test iki dallıdır ve D19'dan beri yalnız ``else``
        dalını koşuyordu: o fikstürde iki kip de ``z_min``e düşüyor,
        dolayısıyla P8B1-09'un ASIL iddiası — "yayımlanan kip KENDİ
        yakınsamasını kanıtlar, başka kipin geçmişini DEVRALMAZ" —
        hiç sınanmıyordu (yakınsama zaten yayımlanan kibin geçmişiydi,
        devralma olsa da olmasa da aynı sonuç çıkardı).

        AYRIŞAN VAKA ARANDI VE BULUNDU (ÖH D24 fea-cfd a3, ölçüm
        docs/scofield/raw/OH/D24/fea-cfd/a3/once_ohd19.json — beş sıvı
        vakası tarandı, biri ayrışıyor): 2 kN / 15 bar / ε = 5'te
        birincil kip ``z_min`` (min emniyet 27,391), karşıt kip
        ``z_max`` (15,698) KÖTÜMSER olduğu için yayımlanan odur — oran
        1,7449.

        AYIRT EDİCİ ÖLÇÜM burada: ``converged_birincil_kip = True`` ama
        ``converged_yayimlanan_kip = False`` (bağıl değişim %3,911,
        tolerans %1). Devralma olsaydı ürün bu koşuyu YAKINSADI ilan
        ederdi — birincil kip yakınsamıştı. Ürün ``converged = False``
        diyor: geçmiş devralınmıyor, yayımlanan kip kendi yakınsamasını
        kanıtlıyor. Bu testin ölçtüğü şey budur; iki kipin sayıları
        değil, DEVRALMANIN YOKLUĞU.
        """
        from hrma.app import app
        from hrma.fea.bridge import run_structural_from_motor
        app.config["TESTING"] = True
        c = app.test_client()
        sivi = c.post("/calculate_liquid", json={
            "motor_name": "D24A3AYR", "thrust": 2000.0, "burn_time": 30.0,
            "chamber_pressure": 15.0, "mixture_ratio": 2.2,
            "fuel_type": "rp1", "oxidizer_type": "lox",
            "expansion_ratio": 5.0}).get_json()
        # ARAÇ UYARLANDI (fea-yuk 2. tur, 14 Eki; karar §28-18 (B), kart
        # OH-DK-04): eski sabit-P_c yükünde bu fikstür birincil ``z_min``
        # ⟷ yayımlanan ``z_max`` (oran 1,7449) ayrışıyordu; ayrışma
        # ıraksaktaki yapay net eksenel kuvvetten geliyordu. Doğru yükte
        # (izantropik P(x) + kapalı uç) ``z_min`` hafifçe kötümser kalıyor
        # (22,7678 ⟷ 22,9382; kanit/tur2/arac_olc.jsonl) — birincil kip
        # ürün parametresiyle ``z_max`` seçilince yayımlanan kip ``z_min``
        # olur. İDDİA AYNI: yayımlanan kip birincilden BAŞKA iken kendi
        # yakınsamasını ölçer, devralmaz. Ters mutasyon (eski yük) bu
        # aracı yok eder (eski yükte ``z_max`` kötümser → yayımlanan =
        # birincil) → KIRMIZI.
        from tests.fea.yuk_modeli_araci import (ARAC_BIRINCIL_KIP,
                                                ARAC_YAYIMLANAN_KIP,
                                                izantropik_yukte)
        out = run_structural_from_motor(sivi, axial_fix=ARAC_BIRINCIL_KIP)
        izantropik_yukte(out)
        kd = out["meta"]["kisit_duyarliligi"]
        h = out["meta"]["hukum"]

        # (1) Fikstür GERÇEKTEN ayrışıyor — bu testin ön koşulu.
        assert kd["yayimlanan_kip"] != kd["birincil_kip"], (
            "fikstür artık ayrışmıyor: OH-D19-28'in aradığı vaka kayboldu, "
            f"birincil={kd['birincil_kip']} yayımlanan={kd['yayimlanan_kip']}")
        assert kd["birincil_kip"] == ARAC_BIRINCIL_KIP
        assert kd["yayimlanan_kip"] == ARAC_YAYIMLANAN_KIP
        # Yayımlanan kip KÖTÜMSER olan olmalı (seçim kuralının kendisi).
        assert (kd["karsit_min_safety_factor"]
                < kd["birincil_min_safety_factor"])

        # (2) Yayımlanan kibin yakınsaması GERÇEKTEN ölçülüyor.
        yk = kd["yayimlanan_kip_yakinsamasi"]
        assert yk is not None and yk["olculdu"] is True
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): kapı artık HÜKÜM büyüklüğünü
        # ölçüyor (ham tepeyi değil) ve bu fikstürde o büyüklük
        # yakınsıyor (%0,12 < %1). Bekçinin ASIL iddiası "yayımlanan kip
        # için ölçüm GERÇEKTEN yapılıyor, başka kipten devralınmıyor";
        # o aynen sınanıyor, üstüne kapı alanı ve ham tepenin ayrı
        # beyanı eklendi.
        assert yk["tol"] > 0.0
        assert yk["kapi_alani"] == "max_von_mises_hukum"
        assert yk["yakinsadi"] is (yk["rel_change"] < yk["tol"])
        assert "max_von_mises_nodal" in yk["olculen_alanlar"]
        # Ölçüm iki yayımlanan büyüklüğün İKİSİNİ de kapsar (OH-D15-02).
        assert set(yk["olculen_alanlar"]) >= {"max_von_mises_nodal",
                                              "max_von_mises_hukum"}

        # (3) DEVRALMA YOK — bu kalemin ayırt edici sayısı.
        assert h["converged_birincil_kip"] is True, (
            "ayırt edicilik için birincil kip YAKINSAMIŞ olmalı; yoksa "
            "devralma olsa da olmasa da sonuç aynı çıkar")
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): kapı hüküm büyüklüğünü ölçüyor
        # ve bu fikstürde o büyüklük yakınsıyor, dolayısıyla yayımlanan
        # kip de "yakınsadı" diyor. DEVRALMA YASAĞI ise aynen sınanıyor:
        # yayımlanan kipin bayrağı KENDİ ölçümünden gelmeli.
        assert h["converged_yayimlanan_kip"] is yk["yakinsadi"], (
            "yayımlanan kip bayrağı kendi ölçümünden gelmiyor — başka "
            "kipin geçmişini DEVRALIYOR olabilir (P8B1-09)")
        assert h["converged"] is (h["converged_birincil_kip"]
                                  and h["converged_yayimlanan_kip"])

        # (4) ŞART / OH-D19-28 — ÖLÇÜM KİPİ DEVRALMASI (Fable TOPLU, D32).
        # (1)-(3) "ölçüm yapıldı" der ama ölçümün HANGİ KİPTE yapıldığını
        # ayırt etmez: ürün sayıyı birincil kipin mesh çiftinden alsaydı
        # bütün iddialar yine geçerdi. Burada iki kip için kaba/ince mesh
        # çifti BAĞIMSIZ çözülür (TestOHD1601 deseni) ve ürünün bastığı
        # rel_change'in YAYIMLANAN kipin sayısı olduğu, birincil kipinki
        # OLMADIĞI kilitlenir.
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D32/fea-cfd/a1/once.json →
        # "OH-D19-28"): kaba 1024x4 ⟷ ince 2048x4, kapı alanı
        # max_von_mises_hukum; yayımlanan kip (z_max) %0,046289,
        # birincil kip (z_min) %0,063008 — iki sayı %36 ayrışıyor.
        from hrma.fea import bridge
        from hrma.fea.structural_axisym import (build_wall_mesh,
                                                solve_pressure)
        gir = bridge.extract_structural_inputs(sivi)
        msh = out["mesh"]
        alan = yk["kapi_alani"]

        def _bagimsiz_rel(kip):
            cift = {}
            for ad, nn in (("kaba", yk["kaba_mesh"]),
                           ("ince", {"n_axial": msh["n_axial"],
                                     "n_radial": msh["n_radial"]})):
                m = build_wall_mesh(gir["contour"], gir["thickness_m"],
                                    n_axial=int(nn["n_axial"]),
                                    n_radial=int(nn["n_radial"]),
                                    offset_mode=gir.get("offset_mode",
                                                        "normal"))
                # Bağımsız çözüm ÜRÜNÜN yük modeliyle (fea-yuk 2. tur):
                # skaler P_c artık ürünün çözdüğü yük değildir.
                cift[ad] = solve_pressure(m, gir["material"],
                                          gir["pressure_load"],
                                          axial_fix=kip)
            a = getattr(cift["ince"], alan)
            b = getattr(cift["kaba"], alan)
            return abs(a - b) / abs(b)

        rel_yayimlanan = _bagimsiz_rel(kd["yayimlanan_kip"])
        rel_birincil = _bagimsiz_rel(kd["birincil_kip"])
        assert rel_yayimlanan != pytest.approx(rel_birincil, rel=1e-3), (
            "iki kip AYNI bağıl değişimi veriyor — fikstür ölçüm-kipi "
            "devralmasını ayırt edemez, OH-D19-28'in aradığı vaka "
            f"kayboldu (yayımlanan={rel_yayimlanan}, "
            f"birincil={rel_birincil})")
        assert yk["rel_change"] == pytest.approx(rel_yayimlanan, rel=1e-9)
        assert yk["rel_change"] != pytest.approx(rel_birincil, rel=1e-3), (
            "kapı sayısı BİRİNCİL kipin mesh çiftinden geliyor — "
            "yayımlanan kip başkasının ölçümünü DEVRALIYOR (P8B1-09)")

    def test_AYRISAN_kipte_yayimlanan_kip_BAYRAGI_devralmiyor(self,
                                                              monkeypatch):
        """ŞART / OH-D19-28 ikinci yarısı: BAYRAK devralma sınanır.

        Yukarıdaki test bu fikstürde ``converged_yayimlanan_kip is True``
        ile bitiyor (kapı hüküm büyüklüğünü ölçüyor ve o büyüklük
        yakınsıyor, ÖH D25 / OH-D24-01). Ama "True" iki ayrı dünyada da
        çıkar: ürün kendi ölçümünü yapmış olabilir ya da birincil kipin
        yakınsamasını DEVRALMIŞ olabilir. İkisini ayıran tek deney,
        yayımlanan kibin ölçümünü bozup birincil kipinkini dokunulmadan
        bırakmaktır.

        Yayımlanan kipin KABA mesh çözümüne %50 sapma enjekte edilir
        (yalnız o kip + yalnız o mesh; ince mesh ve birincil kip AYNEN
        kalır). Devralma olsaydı bayrak yine True çıkardı.

        ÖLÇÜLDÜ (docs/scofield/raw/OH/D32/fea-cfd/a1/once.json →
        "OH-D19-28_enjeksiyon"): rel_change %0,046289 → %33,302 (tol %1),
        converged_birincil_kip TRUE kalır, converged_yayimlanan_kip
        FALSE olur, converged FALSE.
        """
        from hrma.app import app
        from hrma.fea import bridge
        app.config["TESTING"] = True
        c = app.test_client()
        sivi = c.post("/calculate_liquid", json={
            "motor_name": "D24A3AYR", "thrust": 2000.0, "burn_time": 30.0,
            "chamber_pressure": 15.0, "mixture_ratio": 2.2,
            "fuel_type": "rp1", "oxidizer_type": "lox",
            "expansion_ratio": 5.0}).get_json()

        # ARAÇ UYARLANDI (fea-yuk 2. tur): yukarıdaki testle aynı araç —
        # birincil kip ürün parametresiyle ``z_max``; yayımlanan ``z_min``.
        from tests.fea.yuk_modeli_araci import (ARAC_BIRINCIL_KIP,
                                                izantropik_yukte)
        temiz = bridge.run_structural_from_motor(
            sivi, axial_fix=ARAC_BIRINCIL_KIP)
        izantropik_yukte(temiz)
        kd0 = temiz["meta"]["kisit_duyarliligi"]
        assert kd0["yayimlanan_kip"] != kd0["birincil_kip"], (
            "fikstür ayrışmıyor — bayrak devralma deneyi anlamsız")
        kaba = kd0["yayimlanan_kip_yakinsamasi"]["kaba_mesh"]
        yayim = kd0["yayimlanan_kip"]
        gercek = bridge.solve_pressure

        def _sapmali(mesh, material, inner_pressure, **kw):
            res = gercek(mesh, material, inner_pressure, **kw)
            ayni_mesh = (
                int(getattr(mesh, "n_axial", -1)) == int(kaba["n_axial"])
                and int(getattr(mesh, "n_radial", -1))
                == int(kaba["n_radial"]))
            if kw.get("axial_fix") == yayim and ayni_mesh:
                for ad in ("max_von_mises_hukum", "max_von_mises_nodal",
                           "max_von_mises"):
                    v = getattr(res, ad, None)
                    if v is not None:
                        setattr(res, ad, float(v) * 1.5)
            return res

        monkeypatch.setattr(bridge, "solve_pressure", _sapmali)
        out = bridge.run_structural_from_motor(sivi,
                                               axial_fix=ARAC_BIRINCIL_KIP)
        kd = out["meta"]["kisit_duyarliligi"]
        h = out["meta"]["hukum"]
        yk = kd["yayimlanan_kip_yakinsamasi"]

        assert yk["rel_change"] > yk["tol"], (
            "enjekte edilen sapma kapıya ULAŞMADI — deney kurulmadı")
        assert h["converged_birincil_kip"] is True, (
            "ayırt edicilik için birincil kip YAKINSAMIŞ kalmalı; "
            "enjeksiyon yanlış kipe/mesh'e sızmış olabilir")
        assert h["converged_yayimlanan_kip"] is False, (
            "yayımlanan kip, kendi ölçümü BOZULDUĞU hâlde 'yakınsadı' "
            "diyor — birincil kipin bayrağını DEVRALIYOR (P8B1-09)")
        assert h["converged"] is False


# ===========================================================================
# P8B1-03 — geometri (cidar kalınlığı) sapması yakınsama ölçütünün parçası
# ===========================================================================
class TestP8B103GeometriKalinlikKapisi:

    def _gir(self):
        from hrma.app import app
        from hrma.fea.bridge import extract_structural_inputs
        app.config["TESTING"] = True
        c = app.test_client()
        hib = (c.post("/calculate", json={
            "motor_name": "d15a3g", "thrust": 2000, "burn_time": 10,
            "of_ratio": 6.0, "chamber_pressure": 30.0,
            "fuel_type": "htpb", "oxidizer_type": "n2o",
            # kitap p1a B16 (karar §28-18 (a)) — SINIF (ii): bu bekçinin amacı
            # termokimya DEĞİL (FEA geometri kalınlık kapısı / kapama payı).
            # Eşik DEĞİŞMEDİ; testin kendi motoru 'gas' fazıyla sabitlendi
            # (298,15 K gaz referansı = kalem öncesi geometri, BİT-AYNI). Sıvı
            # varsayılandaki yeni geometri sonucu defter kalemi KITAP-P1A-D3
            # (p1a rapor §12).
            "oxidizer_phase": "gas"}).get_json()
            or {}).get("motor") or {}
        return extract_structural_inputs(hib)

    def test_sapma_olculup_yayimlanir(self):
        import numpy as np
        from hrma.fea.mesh_axisym import build_wall_mesh
        gir = self._gir()
        t = float(np.max(np.atleast_1d(gir["thickness_m"])))
        # ÖH D27 a1 YARGISI (OH-D25-28): bu bekçi KAPAMA operatörünün
        # kalınlaşmasını sınar; iç kontur köşe tabanı ürün varsayılanı
        # olunca (INNER_KINK_VARSAYILAN_TOL_RAD) aynı motorda sapma
        # 0,28672 → 0,08179'a iner (ölçüm: docs/scofield/raw/OH/D27/
        # fea-cfd/a1/sonra_a1.json §G2). Eşik GEVŞETİLMEDİ; sınadığı
        # operatör YALITILDI ve tabanın ürüne getirdiği İYİLEŞME ayrıca
        # ilişki olarak kilitlendi (sayı çapası değil, yön çapası).
        m = build_wall_mesh(gir["contour"], t, n_axial=16, n_radial=4,
                            inner_kink_tol_rad=0.0)
        tb = m.meta["dis_yuzey_egrilik_tabani"]
        assert "kalinlik_sapma_orani" in tb
        assert tb["kalinlik_sapma_orani"] > 0.20, (
            "na=16'da ölçülen +%24,18 sapma kayboldu")
        # Ürün varsayılanı (taban AÇIK): sapma HÂLÂ ölçülür ve yayımlanır,
        # ama uydurma kalınlaşma KESİN OLARAK AZALIR.
        m_urun = build_wall_mesh(gir["contour"], t, n_axial=16, n_radial=4)
        tb_urun = m_urun.meta["dis_yuzey_egrilik_tabani"]
        assert "kalinlik_sapma_orani" in tb_urun
        assert tb_urun["kalinlik_sapma_orani"] > 0.0, (
            "ürün yolunda sapma ölçümü kayboldu — beyan boşaldı")
        assert tb_urun["kalinlik_sapma_orani"] < tb["kalinlik_sapma_orani"], (
            "iç köşe tabanı kapamanın uydurma kalınlaşmasını AZALTMALIYDI: "
            f"{tb_urun['kalinlik_sapma_orani']} >= "
            f"{tb['kalinlik_sapma_orani']}")

    def test_beyan_artik_ayni_geometriye_yakinsar_demiyor(self):
        import hrma.fea.mesh_axisym as MA
        assert "inceltme turları aynı geometriye yakınsasın" not in (
            MA.__doc__ or "")
        assert "TUR-BAĞIMLIDIR" in (MA.__doc__ or "") or \
               "tur-bağımlıdır" in (MA.__doc__ or "")

    def test_sapmasi_buyuk_tur_yakinsamis_sayilmaz(self):
        """P8B1-03 (ÖH D22): kapı TOPLAM sapmayı değil YERLEŞİM payını ölçer.

        Bu bekçi eskiden ``gk['sapma_orani'] > 0.20`` diyerek kapıyı TOPLAM
        sapmaya kilitliyordu ve kusuru KORUYORDU: toplamın içindeki kapama
        tabanı n_axial'dan BAĞIMSIZDIR, inceltmeyle küçülmez. Gerçek hibrit
        varsayılanında (2 kN/30 bar) o taban %13,99'du, yani eşiğin (%10)
        ÜSTÜNDEYDİ; dolayısıyla na = 16…1024 turlarının HİÇBİRİ kapıdan
        geçemiyordu (0/7 — ölçüldü, taban b84b10a,
        ``docs/scofield/raw/OH/D22/fea-cfd/a1/once_mesh.json``). Kapı bir
        yakınsama ölçütü olmaktan çıkıp geometriye bağlı sabit bir redde
        dönüşmüş, emniyet hükmü hep geri çekilmişti.

        Kalemin ASIL derdi (kalınlaşma saklanmasın) korunuyor: toplam sapma
        ``toplam_kalinlik_sapma_orani``, kapamanın kendi payı
        ``kapama_taban_sapma_orani`` alanında ve çözücünün beyan metninde
        adıyla yayımlanmaya devam ediyor.
        """
        from hrma.fea.structural_axisym import solve_with_refinement
        gir = self._gir()
        r = solve_with_refinement(
            gir["contour"], gir["thickness_m"], gir["material"],
            inner_pressure=gir["inner_pressure_pa"],
            n_axial0=16, max_rounds=0)
        gk = r.meta["geometri_kalinlik_kapisi"]
        # Kalınlaşma HÂLÂ ölçülüp yayımlanıyor (kalemin çekirdeği).
        # ÖH D27 a1 (OH-D25-28): iç köşe tabanı ürün varsayılanı olunca
        # TOPLAM sapma 0,28672 → 0,08179'a indi (ölçüm §G2). Elle yazılmış
        # 0,10 alt sınırı bu yüzden düştü; yerine gelen bağ DAHA DARDIR:
        # toplam sapma yayımlanıyor, pozitif, ve kapamanın kendi payı
        # toplamın baskın bileşeni olarak duruyor (0,13990). Kapama payının
        # 0,10 çapası KORUNDU — o operatör değişmedi.
        assert gk["toplam_kalinlik_sapma_orani"] > 0.0
        assert gk["kapama_taban_sapma_orani"] > 0.10
        assert (gk["kapama_taban_sapma_orani"]
                >= 0.9 * gk["toplam_kalinlik_sapma_orani"]), (
            "kalınlaşmanın baskın kaynağı artık kapama değil — yeni bir "
            f"kaynak doğmuş olabilir: {gk}")
        # Kapı YERLEŞİM payını ölçüyor, toplamı değil.
        assert gk["sapma_orani"] == gk["yerlesim_sapma_orani"]
        assert gk["sapma_orani"] != gk["toplam_kalinlik_sapma_orani"]
        # Kapamanın payı BEYANDA görünür — emniyetsiz yön saklanamaz.
        assert "EĞRİLİK TABANI" in r.meta["beyan"], r.meta["beyan"]
        # max_rounds=0: hiçbir inceltme sondası çözülmedi, yakınsama
        # iddiası KAZANILMADI.
        assert r.converged is False

    def test_inceltme_kapiyi_gecen_tura_gider(self):
        from hrma.fea.structural_axisym import solve_with_refinement
        gir = self._gir()
        r = solve_with_refinement(
            gir["contour"], gir["thickness_m"], gir["material"],
            inner_pressure=gir["inner_pressure_pa"],
            n_axial0=16, max_rounds=6)
        gk = r.meta["geometri_kalinlik_kapisi"]
        if r.converged:
            assert gk["gecti"] is True

    def test_esik_tek_kaynaktan(self):
        from hrma.fea.mesh_axisym import GEOMETRY_THICKNESS_TOL
        assert GEOMETRY_THICKNESS_TOL == 0.10
