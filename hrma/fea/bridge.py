"""
Motor sonucu → FEA köprüsü (D4 — docs/V2.7_ANALIZ_MODULU.md).

Üç motor çözücüsünün (hibrit / sıvı / katı) sonuç sözlüğünden eksenel
simetrik FEA girdilerini çıkarır ve D1 yapısal çözücüsünü
(``structural_axisym.solve_with_refinement``) uçtan uca sürer. Çözücü saf
geometri + malzeme + yük alır (motor sözlüğüne bağımlılık orada YOKTUR);
motor sözlüğünün alan adlarını, birimlerini ve beyan zincirini bilen tek
katman burasıdır.

Alan haritası (KOD OKUNARAK çıkarıldı; commit 67ac180 sonrası motorlar,
2026-08-04 — satır referansları o günkü kaynağa aittir):

  Kontur:
    ``results['nozzle_contour']['points']`` — ``[[z_m, r_m], ...]``, METRE.
    ORİJİN SÖZLEŞMESİ: ilk nokta konverjan girişidir (kamara-lüle
    birleşimi, z = 0, r = kamara yarıçapı) ve z çıkışa doğru artar; üç
    motorda aynı örnekleyiciden gelir
    (``nozzle_design.sample_nozzle_inner_contour``; hibrit
    hybrid_rocket_engine.py ~3087, katı solid_rocket_engine.py ~7669,
    sıvı liquid_rocket_engine.py ~4945; bekçi:
    tests/test_motor_geometri_yayimi.py). Blok/points yoksa kontur
    UYDURULMAZ → NOT_MODELLED redli sonuç.

  Cidar kalınlığı (çözücünün GERÇEKTEN kullandığı değer, mm):
    hibrit : ``structural_analysis.chamber_analysis.wall_thickness_used_mm``
             (StructuralAnalyzer._analyze_chamber_wall'ın değerlendirdiği
             kalınlık; size/verify kipi ``design_mode`` alanında)
    sıvı   : ``structural_analysis.chamber_structure.wall_thickness``
             (_structural_design()['thickness_m'] * 1000; kaynağı
             ``wall_thickness_source`` alanında)
    katı   : ``structural_analysis.case_analysis.wall_thickness_mm``
             (_case_design() cidarı: kullanıcı kalınlığı ya da Barlow)
    Alan yoksa varsayılan kalınlık UYDURULMAZ → red.

  Malzeme:
    ad     : hibrit ``structural_analysis.design_parameters.material``,
             sıvı ``structural_analysis.chamber_structure.material_key``,
             katı ``structural_analysis.case_analysis.case_material``
             (üçü de hrma.data.materials_db anahtarıdır — hibrit
             _resolve_chamber_material, sıvı _material_record, katı
             _case_design ile doğrulanmış).
    E, ν   : materials_db kaydından (``elastic_modulus``,
             ``poisson_ratio``). Motor çözücülerinin hiçbiri E/ν
             KULLANMAZ (ince cidar hoop formülleri gerektirmez); projede
             tek E/ν kaynağı materials_db'dir. Kayıt yoksa (örn. katının
             'composite' ek kaydında E/ν alanı yoktur) → red.
    akma   : motor sonucunun KENDİ yayımladığı değer öncelikli — katıda
             kullanıcı/jenerik taban (250 MPa) DB kaydından (4130: 460
             MPa) FARKLI olabilir; köprünün SF'si motor çözücüsünün
             kullandığı dayanımdan sapmamalıdır. Yayım yoksa DB değeri,
             hangisinin kullanıldığı ``_basis``te beyan edilir.

  İç basınç yükü:
    ``results['chamber_pressure']`` [bar] → Pa (üç motorda da üst düzey
    alan bar taşır: hibrit self.P_c  # bar, sıvı/katı P_c * 1e5
    dönüşümleriyle doğrulandı). Lüle boyunca P(x) HİÇBİR motor sonucunda
    yayımlanmaz (kod tarandı: statik basınç profili üreten
    nozzle_flow_1d sonucu motor sözlüğüne konmuyor); bu yüzden iç yüzeye
    SABİT Pc uygulanır ve beyan edilir. İzantropik lüle akışında statik
    basınç konverjan girişinden çıkışa doğru monoton düşer (Sutton &
    Biblarz, "Rocket Propulsion Elements", 9. baskı, Böl. 3); sabit Pc
    bu yüzden yükün ÜST SINIRIDIR (gerilme için konservatif) — yaklaşım
    gizlenmez, ``_basis``te açık beyanla taşınır.

  Kamara silindiri uzantısı:
    Kontur kamara-lüle birleşiminden başlar; kamara gövdesi (silindir)
    motorun kendi uzunluk alanından eklenir:
      hibrit ``results['chamber_length']`` [m]  (self.L, metre;
             chamber_length_mm = self.L * 1000 satırıyla doğrulandı),
      sıvı   ``results['chamber_length']`` [mm] (cooling
             ['chamber_length'] = chamber_length * 1000  # mm),
      katı   üst düzeyde kasa boyu yayımlanmaz → uzantı YAPILMAZ ve bu
             beyan edilir (grain_length grain boyudur, kasa boyu değil).
    Aynı alan adının motorlara göre FARKLI birim taşıması (m / mm) bu
    modülün motor-tipine göre dönüşüm yapmasının nedenidir; tip tespiti
    aşağıdaki yapısal blok imzasından yapılır, tahmin edilmez.

Motor tipi tespiti: sonuç sözlüklerinde ortak bir 'motor_type' alanı
YOKTUR; tespit, üç çözücünün birbiriyle çakışmayan yapısal blok
imzasından yapılır (chamber_analysis / chamber_structure /
case_analysis). İmza yoksa red — "büyük ihtimalle şudur" tahmini yok.

Sahte veri yasağı: eksik girdi UYDURULMAZ; her eksikte sonuç
``status='NOT_MODELLED'`` + ``missing`` listesi + {code, params} uyarı
kaydıyla döner ve İÇİNDE hiçbir gerilme/SF alanı bulunmaz. Modellenmeyen
fizik (termal gerilme, P(x) dağılımı, lüle için ayrı malzeme/kalınlık)
başarılı sonucun ``meta['not_modelled']`` beyanındadır.

Termal köprü (D2 ile eşleşme) bu dalgada İSKELETTİR: girdi çıkarımı
tamdır ama motorlar Bartz h(z) profilini SONUÇ SÖZLÜĞÜNE YAYIMLAMAZ
(kod tarandı: hibrit yalnız boğaz skalerlerini
``nozzle_material_analysis.throat_thermal`` içine koyar; h(z) dizisi
yalnız HeatTransferAnalyzer.analyze_axial_profile çağrısıyla üretilir ve
app katmanı bunu ayrı uç noktada hesaplar). Profil çağıran tarafından
``axial_profile`` argümanıyla verilmek zorundadır; verilmezse red.
D2 çözücüsü (thermal_axisym) paralel dalgada yazılmaktadır — import
korumalıdır: modül yoksa açıklayıcı NOT_AVAILABLE, varsa INPUTS_READY
(çıkarılmış girdiler) döner; UYDURMA termal alan hiçbir koşulda üretilmez.

Kaynaklar
---------
* Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı, Böl. 3
  (izantropik lüle akışında eksenel basınç dağılımı — sabit-Pc yükünün
  konservatifliği) ve Böl. 8 (kamara/cidar yapısal bağlamı).
* Timoshenko & Goodier, "Theory of Elasticity", 3. baskı, Böl. 4 —
  iç basınçlı silindir (D1 çözücüsünün doğrulama tabanı).
* docs/V2.7_ANALIZ_MODULU.md §3, §5 — mesh/yakınsama politikası ve
  "doğrulanmamış FEA yayımlanmaz" şartı.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from hrma.constants import PA_PER_BAR
from hrma.fea.mesh_axisym import DEFAULT_ELEMS_THROUGH_WALL
from hrma.fea.structural_axisym import (
    DEFAULT_MAX_REFINE_ROUNDS,
    DEFAULT_N_AXIAL0,
    DEFAULT_REFINE_TOL,
    Material,
    solve_with_refinement,
)

# ---------------------------------------------------------------------------
# Durum sözleşmesi — köprünün tüm dönüşleri bu değerlerden birini taşır.
# ---------------------------------------------------------------------------
BRIDGE_STATUS_OK = "ok"
BRIDGE_STATUS_NOT_MODELLED = "NOT_MODELLED"      # girdi eksik → uydurma yok, red
BRIDGE_STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"    # D2 çözücüsü henüz depoda yok
BRIDGE_STATUS_INPUTS_READY = "INPUTS_READY"      # D2 var; girdiler hazır, çağrı
                                          # bağlantısı D2 API'siyle yazılacak

ENGINE_LAYOUTS = ("hybrid", "liquid", "solid")

# Uyarı kodları — {code, params} sözleşmesi (i18n_common.js kaydı ayrı
# kalemdir; kod üreten tek yer burasıdır).
WARN_INPUTS_MISSING = "warn.fea.bridge_inputs_missing"
WARN_THERMAL_PROFILE_MISSING = "warn.fea.bridge_thermal_profile_missing"
WARN_THERMAL_SOLVER_UNAVAILABLE = "warn.fea.bridge_thermal_solver_unavailable"


def _warning(code: str, **params) -> dict:
    """Motor modülleriyle aynı {code, params} uyarı kaydı biçimi."""
    return {"code": code, "params": params}


def _finite_positive(value) -> Optional[float]:
    """Değeri float'a çevirir; sonlu ve > 0 değilse None döner."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v) or v <= 0.0:
        return None
    return v


# ---------------------------------------------------------------------------
# Motor tipi tespiti — yapısal blok imzasından (modül docstring'i).
# ---------------------------------------------------------------------------
def detect_engine_layout(motor_results: dict) -> Optional[str]:
    """Sonuç sözlüğünün hangi motor çözücüsünden geldiğini tespit eder.

    Sonuç sözlüklerinde ortak 'motor_type' alanı yoktur; üç çözücünün
    yapısal blokları birbiriyle çakışmayan alan adları taşır:

      hibrit : structural_analysis.chamber_analysis.wall_thickness_used_mm
               (hrma.analysis.structural_analysis.analyze_structure çıktısı)
      sıvı   : structural_analysis.chamber_structure.wall_thickness
               (liquid_rocket_engine._calculate_structural_loads çıktısı)
      katı   : structural_analysis.case_analysis.wall_thickness_mm
               (solid_rocket_engine._calculate_structural_analysis çıktısı)

    Hiçbiri yoksa None — çağıran red üretir, tahmin edilmez.
    """
    if not isinstance(motor_results, dict):
        return None
    sa = motor_results.get("structural_analysis")
    if not isinstance(sa, dict):
        return None
    ca = sa.get("chamber_analysis")
    if isinstance(ca, dict) and "wall_thickness_used_mm" in ca:
        return "hybrid"
    cs = sa.get("chamber_structure")
    if isinstance(cs, dict) and "wall_thickness" in cs:
        return "liquid"
    case = sa.get("case_analysis")
    if isinstance(case, dict) and "wall_thickness_mm" in case:
        return "solid"
    return None


# ---------------------------------------------------------------------------
# Tekil çıkarımlar — her biri (değer, beyan) ya da (None, eksik-açıklaması)
# döner; toplama extract_structural_inputs'ta yapılır.
# ---------------------------------------------------------------------------
def _extract_contour_points(motor_results: dict):
    """``nozzle_contour.points`` → (N, 2) [z_m, r_m] dizisi.

    Dönüş: (points | None, beyan | eksik-metni).
    """
    nc = motor_results.get("nozzle_contour")
    if not isinstance(nc, dict) or not nc.get("points"):
        return None, ("nozzle_contour.points yok — motor kontur yayımlamamış "
                      "(örnekleyici başarısızsa motorlar bloğu bilerek "
                      "yayımlamaz; uydurma kontur üretilmez)")
    try:
        pts = np.asarray(nc["points"], dtype=float)
    except (TypeError, ValueError):
        return None, "nozzle_contour.points sayısal (N, 2) listeye çevrilemedi"
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 2:
        return None, ("nozzle_contour.points (N, 2) biçiminde ve en az 2 "
                      "noktalı değil")
    if not np.all(np.isfinite(pts)):
        return None, "nozzle_contour.points sonlu olmayan değer içeriyor"
    if np.any(pts[:, 1] <= 0.0):
        return None, ("nozzle_contour.points r <= 0 nokta içeriyor — eksenel "
                      "simetrik cidar çözücüsü ekseni kapsamaz")
    beyan = {
        "kaynak": "results['nozzle_contour']['points'] (metre, [z, r])",
        "nokta_sayisi": int(pts.shape[0]),
        "orijin_sozlesmesi": (
            "ilk nokta konverjan girişi (kamara-lüle birleşimi, z=0, "
            "r=kamara yarıçapı); z çıkışa doğru artar"),
        "motor_beyani": nc.get("_basis"),
    }
    return pts, beyan


def _chamber_length_m(motor_results: dict, layout: str):
    """Kamara gövde (silindir) uzunluğu [m] — motor tipine göre birim.

    Dönüş: (uzunluk_m | None, beyan-metni). Birim haritası modül
    docstring'indedir; None fabrikasyon değil "uzatma yapılmadı" demektir.
    """
    if layout == "hybrid":
        v = _finite_positive(motor_results.get("chamber_length"))
        if v is None:
            return None, ("hibrit results['chamber_length'] yok/geçersiz — "
                          "kamara silindiri eklenmedi")
        return v, ("results['chamber_length'] [m] (hibrit self.L; "
                   "chamber_length_mm = self.L * 1000 satırıyla doğrulandı)")
    if layout == "liquid":
        v = _finite_positive(motor_results.get("chamber_length"))
        if v is None:
            return None, ("sıvı results['chamber_length'] yok/geçersiz — "
                          "kamara silindiri eklenmedi")
        return v / 1000.0, ("results['chamber_length'] [mm] / 1000 (sıvı "
                            "cooling['chamber_length'] = m * 1000  # mm)")
    return None, ("katı motor üst düzey sonuçta kasa boyu yayımlamaz "
                  "(grain_length grain boyudur, kasa boyu değil) — kamara "
                  "silindiri eklenmedi, kontur kamara-lüle birleşiminden "
                  "başlar")


def _extract_wall_thickness_m(motor_results: dict, layout: str):
    """Çözücünün gerçekten kullandığı cidar kalınlığı [m].

    Alan haritası modül docstring'inde; üçü de mm taşır. Dönüş:
    (kalınlık_m | None, beyan | eksik-metni).
    """
    sa = motor_results.get("structural_analysis")
    sa = sa if isinstance(sa, dict) else {}
    if layout == "hybrid":
        blok = sa.get("chamber_analysis") or {}
        t_mm = _finite_positive(blok.get("wall_thickness_used_mm"))
        alan = "structural_analysis.chamber_analysis.wall_thickness_used_mm"
        ek = f"design_mode={blok.get('design_mode')!r}"
    elif layout == "liquid":
        blok = sa.get("chamber_structure") or {}
        t_mm = _finite_positive(blok.get("wall_thickness"))
        alan = "structural_analysis.chamber_structure.wall_thickness"
        ek = f"kaynak={blok.get('wall_thickness_source')!r}"
    elif layout == "solid":
        blok = sa.get("case_analysis") or {}
        t_mm = _finite_positive(blok.get("wall_thickness_mm"))
        alan = "structural_analysis.case_analysis.wall_thickness_mm"
        ek = "kaynak=_case_design (kullanıcı kalınlığı ya da Barlow)"
    else:
        return None, ("motor tipi tespit edilemedi — cidar kalınlığı alanı "
                      "bilinmiyor")
    if t_mm is None:
        return None, f"{alan} yok/geçersiz — varsayılan kalınlık uydurulmaz"
    return t_mm / 1000.0, f"{alan} [mm] / 1000; {ek}"


def _extract_material(motor_results: dict, layout: str):
    """Malzeme adı → materials_db E/ν + motorun yayımladığı akma dayanımı.

    Dönüş: (Material | None, beyan | eksik-metni). Akma önceliği motorun
    kendi yayımladığı değerdedir (modül docstring'i: katıda jenerik taban
    DB'den farklı olabilir; köprü SF'si çözücünün dayanımından sapmaz).
    """
    sa = motor_results.get("structural_analysis")
    sa = sa if isinstance(sa, dict) else {}
    yield_pa = None
    yield_kaynak = None
    if layout == "hybrid":
        key = (sa.get("design_parameters") or {}).get("material")
        alan = "structural_analysis.design_parameters.material"
        mp = sa.get("material_properties") or {}
        yield_pa = _finite_positive(mp.get("yield_strength"))
        yield_kaynak = ("structural_analysis.material_properties."
                        "yield_strength [Pa] (çözücünün yayımladığı "
                        "materials_db kaydı, oda sıcaklığı)")
    elif layout == "liquid":
        cs = sa.get("chamber_structure") or {}
        key = cs.get("material_key")
        alan = "structural_analysis.chamber_structure.material_key"
        y_mpa = _finite_positive(cs.get("yield_strength"))
        if y_mpa is not None:
            yield_pa = y_mpa * 1e6
            yield_kaynak = ("structural_analysis.chamber_structure."
                            "yield_strength [MPa] * 1e6 (oda sıcaklığı; "
                            "çözücünün derated değeri ayrıca "
                            "yield_strength_at_wall_temp alanındadır)")
    elif layout == "solid":
        case = sa.get("case_analysis") or {}
        key = case.get("case_material")
        alan = "structural_analysis.case_analysis.case_material"
        y_mpa = _finite_positive(case.get("yield_strength_mpa"))
        if y_mpa is not None:
            yield_pa = y_mpa * 1e6
            yield_kaynak = ("structural_analysis.case_analysis."
                            "yield_strength_mpa * 1e6 (çözücünün FİİLEN "
                            "kullandığı dayanım — kullanıcı girdisi ya da "
                            "jenerik taban olabilir, DB kaydından farklı "
                            "olması meşrudur)")
    else:
        return None, "motor tipi tespit edilemedi — malzeme alanı bilinmiyor"

    if not key or not isinstance(key, str):
        return None, f"{alan} yok — malzeme uydurulmaz"

    try:
        from hrma.data.materials_db import get_material
        rec = get_material(key)
    except (KeyError, ValueError):
        return None, (f"malzeme '{key}' materials_db'de yok — E/ν "
                      "kaynağı olmadan FEA kurulamaz (örn. katının "
                      "'composite' ek kaydı E/ν taşımaz); uydurma elastik "
                      "sabit konmaz")

    E = _finite_positive(rec.get("elastic_modulus"))
    nu = rec.get("poisson_ratio")
    try:
        nu = float(nu)
    except (TypeError, ValueError):
        nu = None
    if E is None or nu is None or not (0.0 < nu < 0.5):
        return None, (f"materials_db['{key}'] kaydında geçerli "
                      "elastic_modulus/poisson_ratio yok")

    if yield_pa is None:
        yield_pa = _finite_positive(rec.get("yield_strength"))
        yield_kaynak = (f"materials_db['{key}'].yield_strength [Pa] (motor "
                        "sonucu akma yayımlamadı; DB oda sıcaklığı değeri)")

    material = Material(E=E, nu=nu, yield_strength=yield_pa, name=key)
    beyan = {
        "ad_alani": alan,
        "ad": key,
        "E_nu_kaynagi": (f"materials_db['{key}'] (elastic_modulus, "
                         "poisson_ratio) — motor çözücüleri E/ν kullanmaz, "
                         "projedeki tek kaynak DB'dir"),
        "akma_kaynagi": yield_kaynak,
        "E_Pa": E,
        "nu": nu,
        "yield_Pa": yield_pa,
    }
    return material, beyan


def _extract_pressure(motor_results: dict):
    """İç basınç yükü [Pa] + P(x) beyanı.

    Dönüş: (basınç_Pa | None, beyan | eksik-metni).
    """
    p_bar = _finite_positive(motor_results.get("chamber_pressure"))
    if p_bar is None:
        return None, ("results['chamber_pressure'] yok/geçersiz — basınç "
                      "yükü uydurulmaz")
    beyan = {
        "kaynak": "results['chamber_pressure'] [bar] * PA_PER_BAR",
        "Pc_bar": p_bar,
        "Pc_Pa": p_bar * PA_PER_BAR,
        "dagilim": (
            "SABİT Pc — lüle boyunca P(x) hiçbir motor sonucunda "
            "yayımlanmıyor (kod tarandı). İzantropik akışta statik basınç "
            "çıkışa doğru monoton düşer (Sutton & Biblarz 9. baskı, Böl. 3); "
            "sabit Pc yükün üst sınırıdır — gerilme için konservatif."),
    }
    return p_bar * PA_PER_BAR, beyan


# ---------------------------------------------------------------------------
# Toplayıcı: motor sonucu → yapısal FEA girdi paketi
# ---------------------------------------------------------------------------
def extract_structural_inputs(motor_results: dict,
                              include_chamber: bool = True) -> dict:
    """Motor sonuç sözlüğünden D1 çözücü girdilerini çıkarır.

    Başarıda ``status='ok'`` + kontur/kalınlık/malzeme/yük + alan-alan
    ``_basis`` zinciri; herhangi bir girdi eksikse ``status='NOT_MODELLED'``
    + TÜM eksiklerin listesi (ilkinde durulmaz — teşhis tam olsun) döner.
    Redli sonuçta hiçbir gerilme/SF alanı bulunmaz (sahte veri yasağı).

    include_chamber: True ise kamara silindiri motorun kendi uzunluk
    alanından konturun önüne eklenir (birim haritası modül docstring'inde);
    alan yoksa uzatma sessizce atlanmaz, beyanla atlanır.
    """
    if not isinstance(motor_results, dict):
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": None,
            "missing": ["motor_results"],
            "reason": "motor sonucu sözlük değil",
            "warning": _warning(WARN_INPUTS_MISSING, missing="motor_results"),
        }

    layout = detect_engine_layout(motor_results)
    missing = []
    notlar = {}

    pts, kontur_beyan = _extract_contour_points(motor_results)
    if pts is None:
        missing.append("nozzle_contour.points")
        notlar["kontur"] = kontur_beyan

    if layout is None:
        missing.append("structural_analysis (motor tipi imzası)")
        notlar["motor_tipi"] = (
            "yapısal blok imzası bulunamadı (chamber_analysis / "
            "chamber_structure / case_analysis yok) — cidar ve malzeme "
            "alanları çözülemez, tahmin edilmez")
        thickness = material = pressure = None
        t_beyan = m_beyan = p_beyan = None
    else:
        thickness, t_beyan = _extract_wall_thickness_m(motor_results, layout)
        if thickness is None:
            missing.append("cidar kalınlığı")
            notlar["cidar"] = t_beyan
        material, m_beyan = _extract_material(motor_results, layout)
        if material is None:
            missing.append("malzeme (E, ν, akma)")
            notlar["malzeme"] = m_beyan
        pressure, p_beyan = _extract_pressure(motor_results)
        if pressure is None:
            missing.append("chamber_pressure")
            notlar["basinc"] = p_beyan

    if missing:
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": layout,
            "missing": missing,
            "reason": ("FEA girdisi motor sonucundan çıkarılamadı; eksikler: "
                       + "; ".join(missing) + ". Uydurma değer konmaz "
                       "(sahte veri yasağı)."),
            "notes": notlar,
            "warning": _warning(WARN_INPUTS_MISSING,
                                missing=", ".join(missing)),
        }

    # Kamara silindiri uzantısı — motorun kendi uzunluk alanından.
    contour = pts
    ext_m = None
    if include_chamber:
        ext_m, ext_beyan = _chamber_length_m(motor_results, layout)
        # Orijin sözleşmesi: uzatma yalnız kontur gerçekten z=0'dan
        # başlıyorsa yapılır (sözleşme dışı seri gelirse yanlış konuma
        # silindir eklemek yerine uzatma beyanla atlanır).
        if ext_m is not None and abs(float(pts[0, 0])) < 1e-9:
            contour = np.vstack([[-ext_m, pts[0, 1]], pts])
        elif ext_m is not None:
            ext_beyan += (" — UYGULANMADI: konturun ilk noktası z=0 değil, "
                          "orijin sözleşmesi dışı seri")
            ext_m = None
    else:
        ext_beyan = "include_chamber=False — kamara silindiri istenmedi"

    basis = {
        "_source": "hrma.fea.bridge.extract_structural_inputs",
        "_basis": ("motor sonuç sözlüğünden alan-alan çıkarım; harita ve "
                   "birim dönüşümleri hrma/fea/bridge.py modül "
                   "docstring'inde, kod okunarak doğrulanmıştır"),
        "motor_tipi": layout,
        "motor_tipi_tespiti": ("yapısal blok imzasından (chamber_analysis / "
                               "chamber_structure / case_analysis)"),
        "kontur": kontur_beyan,
        "kamara_uzantisi": {"eklendi": ext_m is not None,
                            "uzunluk_m": ext_m, "beyan": ext_beyan},
        "cidar": t_beyan,
        "malzeme": m_beyan,
        "yuk": p_beyan,
    }

    return {
        "status": BRIDGE_STATUS_OK,
        "engine_layout": layout,
        "contour": contour,                 # (N[+1], 2) [z_m, r_m]
        "nozzle_points": pts,               # motor noktaları BİREBİR
        "chamber_extension_m": ext_m,
        "thickness_m": thickness,
        "material": material,
        "material_key": material.name,
        "inner_pressure_pa": pressure,
        "pressure_profile": None,           # P(x) yayımlanmıyor — beyanı yuk'ta
        "_basis": basis,
    }


def run_structural_from_motor(motor_results: dict,
                              tol: float = DEFAULT_REFINE_TOL,
                              axial_fix: str = "z_min",
                              n_axial0: int = DEFAULT_N_AXIAL0,
                              n_radial0: int = DEFAULT_ELEMS_THROUGH_WALL,
                              max_rounds: int = DEFAULT_MAX_REFINE_ROUNDS,
                              offset_mode: str = "normal",
                              include_chamber: bool = True) -> dict:
    """Motor sonucundan uçtan uca yapısal FEA koşusu (D1 + yakınsama).

    Girdi çıkarımı ``extract_structural_inputs`` ile yapılır; eksikte o
    fonksiyonun redli sonucu AYNEN döner (çözüm denenmez). Başarıda D1
    ``solve_with_refinement`` sürülür ve paket şunları taşır:

      von Mises alanı (düğüm + Gauss maks), SF alanı (akma yayımlanmışsa;
      yoksa None — sahte SF üretilmez), yer değiştirme, mesh bilgisi,
      yakınsama beyanı (converged/final_rel_change/history + dürüst metin)
      ve girdilerin alan-alan ``_basis`` zinciri.

    Sayısal parametre varsayılanları D1'in merkezî sabitleridir
    (parametre tutarlılığı kuralı — burada sayı tekrarlanmaz).
    """
    inputs = extract_structural_inputs(motor_results,
                                       include_chamber=include_chamber)
    if inputs["status"] != BRIDGE_STATUS_OK:
        return inputs

    ref = solve_with_refinement(
        inputs["contour"], inputs["thickness_m"], inputs["material"],
        inner_pressure=inputs["inner_pressure_pa"],
        tol=tol, axial_fix=axial_fix,
        n_axial0=n_axial0, n_radial0=n_radial0, max_rounds=max_rounds,
        offset_mode=offset_mode,
    )
    res = ref.result

    meta = {
        "_source": "hrma.fea.bridge.run_structural_from_motor",
        "_basis": ("motor sonucu → girdi çıkarımı (aşağıdaki 'girdiler') → "
                   "hrma.fea.structural_axisym.solve_with_refinement"),
        "girdiler": inputs["_basis"],
        "cozucu": res.meta,
        "yakinsama": ref.meta,
        "not_modelled": [
            "termal gerilme ve dayanım deratingi (D2 termal köprüsüyle "
            "eşleşme sonraki kalem; akma oda sıcaklığı/çözücü değeri)",
            "P(x) basınç dağılımı (yayımlanmıyor — sabit Pc üst sınırı "
            "uygulandı, beyanı girdiler.yuk içinde)",
            "lüle için ayrı malzeme/kalınlık (motorlar tek kamara cidarı "
            "yayımlar; hibrit bunu kendisi de beyan eder)",
            "eksenel itki/burkulma yükleri (D1 lineer elastik iç/dış "
            "basınç modeli)",
        ],
    }

    return {
        "status": BRIDGE_STATUS_OK,
        "engine_layout": inputs["engine_layout"],
        "inputs": inputs,
        "von_mises_nodal": res.von_mises_nodal,
        "von_mises_gauss_max": res.max_von_mises,
        "safety_factor_nodal": res.safety_factor_nodal,
        "min_safety_factor": res.min_safety_factor,
        "displacement": res.displacement,
        "stress_nodal": res.stress_nodal,
        "mesh": {
            "nodes": ref.mesh.nodes,
            "elems": ref.mesh.elems,
            "n_nodes": ref.mesh.n_nodes,
            "n_elems": ref.mesh.n_elems,
            "n_axial": ref.mesh.n_axial,
            "n_radial": ref.mesh.n_radial,
            "meta": ref.mesh.meta,
        },
        "convergence": {
            "converged": ref.converged,
            "final_rel_change": ref.final_rel_change,
            "tol": ref.tol,
            "history": ref.history,
            "beyan": ref.meta.get("beyan"),
        },
        "result": res,          # StructuralResult — ileri işleme için tam nesne
        "refinement": ref,      # RefinementResult
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# Termal köprü İSKELETİ (D2 thermal_axisym paralel dalgada yazılıyor)
# ---------------------------------------------------------------------------
def extract_thermal_inputs(motor_results: dict,
                           axial_profile: Optional[dict] = None,
                           include_chamber: bool = True) -> dict:
    """Termal FEA girdi çıkarımı — geometri + malzeme + Bartz h(z) sınırı.

    Bartz h(z) profili motor SONUÇ SÖZLÜĞÜNDE YOKTUR (kod tarandı,
    2026-08-04): hibrit yalnız boğaz skalerlerini
    ``nozzle_material_analysis.throat_thermal`` içine koyar; h(z) dizisi
    ``HeatTransferAnalyzer.analyze_axial_profile`` çıktısıdır ve app
    katmanı onu ayrı uç noktada hesaplar, motor sözlüğüne koymaz. Bu
    yüzden profil çağıran tarafından ``axial_profile`` argümanıyla
    (analyze_axial_profile sözleşmesi: ``x_mm``, ``h_g`` [W/m²K],
    ``T_recovery`` [K]) verilmek zorundadır; verilmezse red —
    boğaz skalerinden h(z) UYDURULMAZ.

    Malzemenin termal alanları (k, cp, ρ) materials_db kaydından okunur
    (heat_transfer_analysis ile aynı kayıt ailesi).
    """
    yapisal = extract_structural_inputs(motor_results,
                                        include_chamber=include_chamber)
    if yapisal["status"] != BRIDGE_STATUS_OK:
        return yapisal

    if not isinstance(axial_profile, dict):
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": yapisal["engine_layout"],
            "missing": ["Bartz h(z) profili (axial_profile)"],
            "reason": (
                "Motor sonuç sözlüğü Bartz h(z) profilini YAYIMLAMAZ — "
                "hibrit yalnız boğaz skalerini "
                "nozzle_material_analysis.throat_thermal'da verir, katı ve "
                "sıvı hiç vermez. Profil "
                "HeatTransferAnalyzer.analyze_axial_profile ile hesaplanıp "
                "axial_profile argümanıyla verilmelidir; boğaz skalerinden "
                "profil uydurulmaz (sahte veri yasağı)."),
            "warning": _warning(WARN_THERMAL_PROFILE_MISSING),
        }

    eksik_alan = [k for k in ("x_mm", "h_g", "T_recovery")
                  if axial_profile.get(k) is None]
    if eksik_alan:
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": yapisal["engine_layout"],
            "missing": [f"axial_profile.{k}" for k in eksik_alan],
            "reason": ("axial_profile analyze_axial_profile sözleşmesine "
                       "uymuyor (x_mm, h_g, T_recovery zorunlu)"),
            "warning": _warning(WARN_THERMAL_PROFILE_MISSING),
        }
    x_m = np.asarray(axial_profile["x_mm"], dtype=float) / 1000.0
    h_g = np.asarray(axial_profile["h_g"], dtype=float)
    t_rec = np.asarray(axial_profile["T_recovery"], dtype=float)
    if not (x_m.shape == h_g.shape == t_rec.shape) or x_m.size < 2:
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": yapisal["engine_layout"],
            "missing": ["axial_profile dizileri"],
            "reason": ("axial_profile dizileri eş uzunlukta (>= 2) değil"),
            "warning": _warning(WARN_THERMAL_PROFILE_MISSING),
        }
    if (not np.all(np.isfinite(x_m)) or not np.all(np.isfinite(h_g))
            or not np.all(np.isfinite(t_rec)) or np.any(h_g <= 0.0)
            or np.any(t_rec <= 0.0)):
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": yapisal["engine_layout"],
            "missing": ["axial_profile değerleri"],
            "reason": ("axial_profile sonlu olmayan / pozitif olmayan değer "
                       "içeriyor"),
            "warning": _warning(WARN_THERMAL_PROFILE_MISSING),
        }

    from hrma.data.materials_db import get_material
    rec = get_material(yapisal["material_key"])  # yapısal çıkarım doğruladı
    termal_malzeme = {
        "thermal_conductivity_W_mK": float(rec["thermal_conductivity"]),
        "specific_heat_J_kgK": float(rec["specific_heat"]),
        "density_kg_m3": float(rec["density"]),
        "kaynak": (f"materials_db['{yapisal['material_key']}'] — "
                   "heat_transfer_analysis ile aynı kayıt ailesi"),
    }

    basis = dict(yapisal["_basis"])
    basis["_source"] = "hrma.fea.bridge.extract_thermal_inputs"
    basis["h_profili"] = (
        "çağıranın verdiği HeatTransferAnalyzer.analyze_axial_profile "
        "çıktısı (x_mm→m dönüşümü burada); motor sözlüğünde h(z) alanı yok")

    out = dict(yapisal)
    out["_basis"] = basis
    out["h_x_m"] = x_m
    out["h_g_W_m2K"] = h_g
    out["t_recovery_K"] = t_rec
    out["thermal_material"] = termal_malzeme
    return out


def run_thermal_from_motor(motor_results: dict,
                           axial_profile: Optional[dict] = None,
                           include_chamber: bool = True) -> dict:
    """Termal köprü İSKELETİ — girdi çıkarımı + import-korumalı D2 kapısı.

    D2 çözücüsü (hrma.fea.thermal_axisym) paralel dalgada yazılmaktadır:

      * girdiler eksik → extract_thermal_inputs'un redli sonucu (uydurma
        h(z) / malzeme yok),
      * modül henüz depoda yok → ``status='NOT_AVAILABLE'`` + açıklayıcı
        neden (import hatası yutulup sessiz kalınmaz),
      * modül var → ``status='INPUTS_READY'`` + çıkarılmış girdi paketi.
        Çözücü ÇAĞRILMAZ: D2'nin giriş API'si bu iskelet yazılırken
        kesinleşmemişti; API'ye körlemesine parametre geçip dönen her ne
        ise "termal sonuç" diye yayımlamak sahte veri yasağını deler.
        Bağlantı, D2 API'si sabitlenince tek noktadan (burada) yazılacak.

    Hiçbir dalda uydurma sıcaklık/ısı akısı alanı üretilmez.
    """
    inputs = extract_thermal_inputs(motor_results, axial_profile=axial_profile,
                                    include_chamber=include_chamber)
    if inputs["status"] != BRIDGE_STATUS_OK:
        return inputs

    try:
        import hrma.fea.thermal_axisym  # noqa: F401 — varlık denetimi
    except ImportError as exc:
        return {
            "status": BRIDGE_STATUS_NOT_AVAILABLE,
            "engine_layout": inputs["engine_layout"],
            "reason": (
                "hrma.fea.thermal_axisym henüz depoda yok (D2, V2.7 Aşama A "
                "— paralel dalgada yazılıyor). Köprü girdileri çıkarıldı ama "
                f"çözücü çağrılamaz. Import hatası: {exc}"),
            "warning": _warning(WARN_THERMAL_SOLVER_UNAVAILABLE),
            "inputs": inputs,
        }

    return {
        "status": BRIDGE_STATUS_INPUTS_READY,
        "engine_layout": inputs["engine_layout"],
        "reason": (
            "hrma.fea.thermal_axisym mevcut; girdiler hazır. Çözücü çağrısı "
            "D2 API'si sabitlenince buraya bağlanacak — API bilinmeden "
            "çağrı uydurulmaz, sahte termal alan üretilmez."),
        "inputs": inputs,
    }
