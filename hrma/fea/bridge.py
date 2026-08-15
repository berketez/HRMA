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

Termal köprü (D2 ``thermal_axisym`` ile eşleşme) BAĞLIDIR:
``run_thermal_from_motor`` mesh'i kurar, sınır koşullarını bağlar ve
geçici ısı iletimi çözücüsünü uçtan uca sürer. Bağlamanın girdi
kaynakları (kod okunarak doğrulandı, 2026-08-05):

  Gaz tarafı Bartz h(z), T_recovery(z):
    Motor SONUÇ SÖZLÜĞÜNDE YOKTUR. Hibrit motor
    ``HeatTransferAnalyzer.analyze_axial_profile``'i içeride çağırır ama
    yalnız BOĞAZ SKALERLERİNİ ``nozzle_material_analysis.throat_thermal``
    içine koyar (hybrid_rocket_engine.py ~1055-1100); sıvı ve katı
    eksenel profili hiç üretmez. Diziyi yayımlayan tek yer
    ``/api/analysis/wall-profile`` ucudur. Bu yüzden profil ÇAĞIRAN
    tarafından ``axial_profile`` argümanıyla verilir (sözleşme:
    ``x_mm``, ``h_g`` [W/m²K], ``T_recovery`` [K]); verilmezse red —
    boğaz skalerinden profil UYDURULMAZ.
    Profilin eksen orijini konturunkiyle AYNI olmalıdır (ikisi de
    ``sample_nozzle_inner_contour`` çıktısıdır); uyuşmazlık
    ``THERMAL_PROFILE_DOMAIN_TOL`` ile denetlenir, başka geometriden
    gelen profil sessizce bu mesh'e taşınmaz.

  Yanma süresi (çözüm penceresi t_end):
    ``results['burn_time']`` [s] — üç motor da üst düzeyde yayımlar
    (hibrit self.t_b; sıvı burn_time + burn_time_source; katı hesaplanan
    süre). Alan yoksa red, süre uydurulmaz.

  Ortam sıcaklığı (başlangıç koşulu) ve dış yüzey koşulu:
    HİÇBİR motor çözücüsü yayımlamaz — çözümün ortam verisidir ve
    ÇAĞIRANDAN alınır. Verilmezse red. Dış yüzey için ortam verisi
    gelmezse yüzey ADYABATİK alınır: bu uydurma bir sayı değil, ısıyı
    dışarı kaçırmayan (tepe cidar sıcaklığı için KONSERVATİF) açık bir
    model seçimidir ve ``meta`` içinde beyan edilir.

  Malzemenin ısıl özellikleri (ρ, c_p, k):
    ``materials_db`` kaydından (heat_transfer_analysis ile aynı kayıt
    ailesi). Kayıtta alan eksikse red.

D2 modülü import korumalıdır: modül yoksa açıklayıcı NOT_AVAILABLE,
modül var ama beklenen API yoksa INPUTS_READY (çıkarılmış girdiler)
döner; UYDURMA termal alan hiçbir koşulda üretilmez.

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

import importlib
from typing import Optional

import numpy as np

from hrma.constants import PA_PER_BAR
from hrma.fea.mesh_axisym import DEFAULT_ELEMS_THROUGH_WALL, build_wall_mesh
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
BRIDGE_STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"    # D2 çözücü modülü depoda yok
BRIDGE_STATUS_INPUTS_READY = "INPUTS_READY"      # D2 modülü var ama beklenen
                                          # API'yi taşımıyor: girdiler hazır,
                                          # çözücü çağrılamaz (körlemesine
                                          # çağırıp dönen şeyi "termal sonuç"
                                          # diye yayımlamak yasak)

ENGINE_LAYOUTS = ("hybrid", "liquid", "solid")

#: Bartz profilinin eksen orijini/uzunluğu ile konturunki arasında kabul
#: edilen en büyük sapma (kontur boyunun oranı). İkisi de AYNI örnekleyiciden
#: (``sample_nozzle_inner_contour``) geldiği için fark yalnızca istasyon
#: yeniden örneklemesinden doğar ve binde birler mertebesindedir; bundan
#: büyük fark profilin BAŞKA bir geometri için hesaplandığı anlamına gelir
#: (ölçüldü: aynı motorun geometrisi eksik verilerek çağrılan profil 171 mm,
#: konturu 124 mm çıkıyor). Sapma tolerans içindeyse uçlarda sabit
#: ekstrapolasyon (np.interp kırpması) yapılır ve beyan edilir.
THERMAL_PROFILE_DOMAIN_TOL = 0.05

# Uyarı kodları — {code, params} sözleşmesi (i18n_common.js kaydı ayrı
# kalemdir; kod üreten tek yer burasıdır).
WARN_INPUTS_MISSING = "warn.fea.bridge_inputs_missing"
WARN_THERMAL_PROFILE_MISSING = "warn.fea.bridge_thermal_profile_missing"
WARN_THERMAL_SOLVER_UNAVAILABLE = "warn.fea.bridge_thermal_solver_unavailable"
WARN_THERMAL_WALL_OVER_ALLOWABLE = "warn.fea.thermal_wall_over_allowable"
WARN_PLANAR_GRAIN_UNSUPPORTED = "warn.fea.planar_grain_unsupported_type"
WARN_PLANAR_GRAIN_SHAPELY = "warn.fea.planar_grain_shapely_missing"


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


def _finite_nonnegative(value) -> Optional[float]:
    """Değeri float'a çevirir; sonlu ve >= 0 değilse None döner.

    Sıfırın meşru olduğu alanlar için (dış yüzey taşınım katsayısı h = 0
    "yalnız ışıma" demektir; yayıcılık ε = 0 "ışıma yok" demektir).
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v) or v < 0.0:
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
        # Mesh üreticisinin beyanı AYNEN akar (dış yüzey eğrilik tabanı
        # ölçümleri dahil — mesh_axisym meta'sı girdiler/cozucu zincirinin
        # yanında, kaynağı değiştirilmeden taşınır).
        "mesh_beyani": ref.mesh.meta,
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
# Termal köprü — D2 (hrma.fea.thermal_axisym) geçici ısı iletimi çözücüsüne
# uçtan uca bağlıdır. Girdi kaynakları ve red kuralları modül docstring'inde.
# ---------------------------------------------------------------------------
def _extract_burn_time_s(motor_results: dict):
    """Yanma süresi [s] — çözüm penceresi (t_end).

    Üç motor da ``results['burn_time']`` alanını üst düzeyde saniye olarak
    yayımlar (hibrit self.t_b; sıvı burn_time + burn_time_source; katı
    hesaplanan süre). Dönüş: (süre_s | None, beyan | eksik-metni).
    """
    v = _finite_positive(motor_results.get("burn_time"))
    if v is None:
        return None, ("results['burn_time'] yok/geçersiz — yanma süresi "
                      "uydurulmaz (geçici çözümün penceresi bu alandır)")
    beyan = {
        "kaynak": "results['burn_time'] [s]",
        "t_end_s": v,
        "kaynak_beyani": motor_results.get("burn_time_source"),
        "zaman_penceresi": (
            "t = 0 ateşleme anı, t = burn_time yanma sonu; sınır koşulları "
            "bu pencerede SABİT alınır (kararlı çalışma varsayımı — throttle "
            "ve kapama geçişi D2 çözücüsünün NOT_MODELLED beyanındadır)"),
    }
    return v, beyan


def _extract_thermal_material(material_key: str):
    """materials_db kaydından ρ, c_p, k [SI] — eksikse red.

    Dönüş: (özellik-sözlüğü | None, beyan | eksik-metni).
    """
    from hrma.data.materials_db import get_material
    try:
        rec = get_material(material_key)
    except (KeyError, ValueError):
        return None, (f"malzeme '{material_key}' materials_db'de yok — ısıl "
                      "özellik kaynağı olmadan termal FEA kurulamaz")
    alanlar = {
        "thermal_conductivity_W_mK": _finite_positive(
            rec.get("thermal_conductivity")),
        "specific_heat_J_kgK": _finite_positive(rec.get("specific_heat")),
        "density_kg_m3": _finite_positive(rec.get("density")),
    }
    eksik = [ad for ad, deger in alanlar.items() if deger is None]
    if eksik:
        return None, (f"materials_db['{material_key}'] kaydında geçerli "
                      + ", ".join(eksik) + " yok — uydurma ısıl özellik konmaz")
    alanlar["kaynak"] = (
        f"materials_db['{material_key}'] (thermal_conductivity, "
        "specific_heat, density) — heat_transfer_analysis ile aynı kayıt "
        "ailesi; değerler ODA SICAKLIĞI kaydıdır ve sıcaklıkla değişimi "
        "modellenmez (sabit ρ, c_p, k)")
    # Malzeme sıcaklık sınırı: motor çözücüleriyle AYNI okuma sırası
    # (allowable_temperature, yoksa max_service_temp — hibrit
    # analyze_nozzle_material bu sırayı kullanır).
    allowable = rec.get("allowable_temperature")
    if allowable is None:
        allowable = rec.get("max_service_temp")
    alanlar["allowable_temperature_K"] = _finite_positive(allowable)
    alanlar["melting_point_K"] = _finite_positive(rec.get("melting_point"))
    return alanlar, alanlar["kaynak"]


def extract_thermal_inputs(motor_results: dict,
                           axial_profile: Optional[dict] = None,
                           include_chamber: bool = False) -> dict:
    """Termal FEA girdi çıkarımı — geometri + malzeme + Bartz h(z) + süre.

    Geometri/malzeme yapısal çıkarımdan (``extract_structural_inputs``)
    gelir; üzerine ısıl özellikler, yanma süresi ve ÇAĞIRANIN verdiği
    eksenel gaz-tarafı profili eklenir.

    ``axial_profile`` neden argüman: Bartz h(z) motor SONUÇ SÖZLÜĞÜNDE
    YOKTUR (modül docstring'i, kod okunarak doğrulandı). Diziyi üreten tek
    yer ``HeatTransferAnalyzer.analyze_axial_profile`` / ona bakan
    ``/api/analysis/wall-profile`` ucudur. Sözleşme: ``x_mm`` [mm],
    ``h_g`` [W/m²K], ``T_recovery`` [K]; üçü eş uzunlukta, x kesin artan.

    ``include_chamber`` VARSAYILAN OLARAK KAPALIDIR (yapısal yoldan farklı):
    h(z) profili yalnız lüle konturu boyunca tanımlıdır; kamara silindiri
    eklenirse o bölgede gaz-tarafı katsayısı BİLİNMEZ ve uydurulması
    gerekirdi. Termal alan bu yüzden profilin tanımlı olduğu bölgedir;
    eksik bölge ``meta['not_modelled']`` içinde beyan edilir.
    """
    yapisal = extract_structural_inputs(motor_results,
                                        include_chamber=include_chamber)
    if yapisal["status"] != BRIDGE_STATUS_OK:
        return yapisal

    def _red(missing, reason, code=WARN_THERMAL_PROFILE_MISSING, **params):
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": yapisal["engine_layout"],
            "missing": list(missing),
            "reason": reason,
            "warning": _warning(code, **params),
        }

    if not isinstance(axial_profile, dict):
        return _red(
            ["Bartz h(z) profili (axial_profile)"],
            "Motor sonuç sözlüğü Bartz h(z) profilini YAYIMLAMAZ — hibrit "
            "yalnız boğaz skalerini nozzle_material_analysis.throat_thermal'da "
            "verir, katı ve sıvı hiç vermez. Profil "
            "HeatTransferAnalyzer.analyze_axial_profile ile (ya da "
            "/api/analysis/wall-profile ucuyla) hesaplanıp axial_profile "
            "argümanıyla verilmelidir; boğaz skalerinden profil uydurulmaz "
            "(sahte veri yasağı).")

    eksik_alan = [k for k in ("x_mm", "h_g", "T_recovery")
                  if axial_profile.get(k) is None]
    if eksik_alan:
        return _red([f"axial_profile.{k}" for k in eksik_alan],
                    "axial_profile analyze_axial_profile sözleşmesine uymuyor "
                    "(x_mm, h_g, T_recovery zorunlu)")

    try:
        x_m = np.asarray(axial_profile["x_mm"], dtype=float) / 1000.0
        h_g = np.asarray(axial_profile["h_g"], dtype=float)
        t_rec = np.asarray(axial_profile["T_recovery"], dtype=float)
    except (TypeError, ValueError):
        return _red(["axial_profile dizileri"],
                    "axial_profile dizileri sayısal diziye çevrilemedi")
    if x_m.ndim != 1 or not (x_m.shape == h_g.shape == t_rec.shape) \
            or x_m.size < 2:
        return _red(["axial_profile dizileri"],
                    "axial_profile dizileri eş uzunlukta 1B (>= 2) değil")
    if (not np.all(np.isfinite(x_m)) or not np.all(np.isfinite(h_g))
            or not np.all(np.isfinite(t_rec)) or np.any(h_g <= 0.0)
            or np.any(t_rec <= 0.0)):
        return _red(["axial_profile değerleri"],
                    "axial_profile sonlu olmayan / pozitif olmayan değer "
                    "içeriyor")
    if not np.all(np.diff(x_m) > 0.0):
        return _red(["axial_profile.x_mm"],
                    "axial_profile.x_mm kesin artan değil — sınır koşulu "
                    "enterpolasyonu tanımsız olur")

    # --- Eksen uyuşması: profil ile kontur AYNI geometriden mi? ------------
    # İkisi de sample_nozzle_inner_contour çıktısıdır ve orijin sözleşmesi
    # aynıdır (ilk nokta konverjan girişi, z = 0). Uyuşmazlık, profilin
    # BAŞKA bir geometri için hesaplandığını gösterir; o profili bu mesh'e
    # taşımak sahte veri üretmektir.
    z_kontur = np.asarray(yapisal["contour"], dtype=float)[:, 0]
    z0, z1 = float(np.min(z_kontur)), float(np.max(z_kontur))
    L = z1 - z0
    sapma = max(abs(float(x_m[0]) - z0), abs(float(x_m[-1]) - z1))
    if L <= 0.0 or sapma > THERMAL_PROFILE_DOMAIN_TOL * L:
        return _red(
            ["axial_profile ekseni (kontur ile uyuşmuyor)"],
            "axial_profile ekseni konturla uyuşmuyor: profil "
            f"[{x_m[0] * 1000.0:.3f}, {x_m[-1] * 1000.0:.3f}] mm, kontur "
            f"[{z0 * 1000.0:.3f}, {z1 * 1000.0:.3f}] mm, sapma "
            f"{sapma * 1000.0:.3f} mm > tolerans "
            f"{THERMAL_PROFILE_DOMAIN_TOL * L * 1000.0:.3f} mm "
            f"(kontur boyunun %{100.0 * THERMAL_PROFILE_DOMAIN_TOL:g}'i). "
            "Profil bu geometri için hesaplanmamış görünüyor; başka "
            "geometrinin h(z)'si bu mesh'e taşınmaz. "
            + ("include_chamber=True verildiyse mesh kamara silindirini de "
               "kapsar ama profil yalnız lüle konturunda tanımlıdır."
               if include_chamber else ""))

    termal_malzeme, m_beyan = _extract_thermal_material(
        yapisal["material_key"])
    if termal_malzeme is None:
        return _red(["malzeme ısıl özellikleri (ρ, c_p, k)"], m_beyan,
                    code=WARN_INPUTS_MISSING,
                    missing="malzeme ısıl özellikleri")

    t_end, t_beyan = _extract_burn_time_s(motor_results)
    if t_end is None:
        return _red(["burn_time"], t_beyan, code=WARN_INPUTS_MISSING,
                    missing="burn_time")

    kirpma = (float(x_m[0]) > z0 + 1e-12) or (float(x_m[-1]) < z1 - 1e-12)
    basis = dict(yapisal["_basis"])
    basis["_source"] = "hrma.fea.bridge.extract_thermal_inputs"
    basis["h_profili"] = {
        "kaynak": ("çağıranın verdiği "
                   "HeatTransferAnalyzer.analyze_axial_profile çıktısı "
                   "(x_mm → m dönüşümü burada); motor sonuç sözlüğünde h(z) "
                   "alanı YOKTUR"),
        "nokta_sayisi": int(x_m.size),
        "x_araligi_m": [float(x_m[0]), float(x_m[-1])],
        "kontur_araligi_m": [z0, z1],
        "uc_ekstrapolasyon": (
            "profil konturun tamamını kapsamıyor; kapsanmayan uçta h ve "
            "T_recovery SABİT (en yakın istasyon değeri) alınır — np.interp "
            "kırpması, tolerans içinde beyanlı yaklaşım"
            if kirpma else
            "profil konturu uçtan uca kapsıyor; ekstrapolasyon yapılmadı"),
        "ara_deger": ("kenar orta noktalarında lineer enterpolasyon "
                      "(np.interp); istasyon arası h(z) için başka model "
                      "varsayılmaz"),
    }
    basis["isil_malzeme"] = m_beyan
    basis["yanma_suresi"] = t_beyan
    basis["kamara_uzantisi_termal"] = (
        "kamara silindiri termal alana EKLENMEDİ — gaz tarafı h(z) yalnız "
        "lüle konturu boyunca tanımlı; silindir bölgesinde katsayı "
        "uydurulmaz" if not include_chamber else
        "kamara silindiri istendi (include_chamber=True) — profilin o bölgeyi "
        "de kapsaması gerekir")

    out = dict(yapisal)
    out["_basis"] = basis
    out["h_x_m"] = x_m
    out["h_g_W_m2K"] = h_g
    out["t_recovery_K"] = t_rec
    out["thermal_material"] = termal_malzeme
    out["burn_time_s"] = t_end
    out["profile_clamped"] = bool(kirpma)
    return out


#: D2 çözücüsünden köprünün ihtiyaç duyduğu API adları. Modül var ama bu
#: adlar yoksa çözücü ÇAĞRILMAZ (körlemesine çağırıp dönen şeyi "termal
#: sonuç" diye yayımlamak sahte veri yasağını deler).
_THERMAL_SOLVER_API = (
    "solve_transient_auto", "ThermalMaterial", "ConvectionBC", "AmbientBC",
    "AdiabaticBC", "DEFAULT_DT_TOL", "DEFAULT_N_STEPS0",
    "DEFAULT_MAX_DT_HALVINGS",
)


def run_thermal_from_motor(motor_results: dict,
                           axial_profile: Optional[dict] = None,
                           ambient_temperature_K: Optional[float] = None,
                           outer_ambient: Optional[dict] = None,
                           include_chamber: bool = False,
                           n_axial: int = DEFAULT_N_AXIAL0,
                           n_radial: int = DEFAULT_ELEMS_THROUGH_WALL,
                           offset_mode: str = "normal",
                           dt_tol: Optional[float] = None,
                           n_steps0: Optional[int] = None,
                           max_halvings: Optional[int] = None) -> dict:
    """Motor sonucundan uçtan uca GEÇİCİ TERMAL FEA koşusu (D2 bağlantısı).

    Zincir: girdi çıkarımı (``extract_thermal_inputs``) → mesh
    (``mesh_axisym.build_wall_mesh``) → sınır koşulları → D2
    ``thermal_axisym.solve_transient_auto`` (zaman adımını kendi seçer ve
    beyan eder).

    Sınır koşulları:
      * iç yüzey — ``ConvectionBC``: h(z) ve T_recovery(z) çağıranın verdiği
        Bartz profilinden, kenar orta noktalarında lineer enterpolasyonla.
      * dış yüzey — ``outer_ambient`` verilmemişse ``AdiabaticBC``. Bu bir
        uydurma sayı değil, ısı kaçışını sıfır sayan AÇIK model seçimidir:
        tepe cidar sıcaklığı için üst sınır (konservatif) verir ve beyan
        edilir. ``{'h_W_m2K', 'T_ambient_K', 'emissivity'}`` verilirse
        ``AmbientBC`` (doğal taşınım + lineerleştirilmiş ışıma) kurulur.
      * uç kesitler — adyabatik (D2'nin doğal sınır koşulu).

    ``ambient_temperature_K`` ZORUNLUDUR: başlangıç koşulu tekdüze ortam
    sıcaklığıdır ve bunu HİÇBİR motor çözücüsü yayımlamaz; verilmezse
    NOT_MODELLED döner (varsayılan oda sıcaklığı uydurulmaz).

    Dönüşler:
      * girdi eksik → ``extract_thermal_inputs``in redli sonucu,
      * D2 modülü yok → ``NOT_AVAILABLE`` + açıklayıcı neden,
      * D2 modülü var ama API eksik → ``INPUTS_READY`` (çözücü çağrılmaz),
      * ortam girdisi eksik → ``NOT_MODELLED`` + eksik alan adı,
      * hepsi tamam → ``ok`` + sıcaklık alanı, tepe cidar sıcaklığı geçmişi,
        enerji bütçesi, zaman adımı beyanı ve NOT_MODELLED listesi.

    Hiçbir dalda uydurma sıcaklık/ısı akısı alanı üretilmez.
    """
    inputs = extract_thermal_inputs(motor_results,
                                    axial_profile=axial_profile,
                                    include_chamber=include_chamber)
    if inputs["status"] != BRIDGE_STATUS_OK:
        return inputs

    try:
        ta = importlib.import_module("hrma.fea.thermal_axisym")
    except ImportError as exc:
        return {
            "status": BRIDGE_STATUS_NOT_AVAILABLE,
            "engine_layout": inputs["engine_layout"],
            "reason": (
                "hrma.fea.thermal_axisym içe aktarılamadı (D2 geçici ısı "
                "iletimi çözücüsü). Köprü girdileri çıkarıldı ama çözücü "
                f"çağrılamaz. Import hatası: {exc}"),
            "warning": _warning(WARN_THERMAL_SOLVER_UNAVAILABLE),
            "inputs": inputs,
        }

    eksik_api = [ad for ad in _THERMAL_SOLVER_API if not hasattr(ta, ad)]
    if eksik_api:
        return {
            "status": BRIDGE_STATUS_INPUTS_READY,
            "engine_layout": inputs["engine_layout"],
            "reason": (
                "hrma.fea.thermal_axisym mevcut ama köprünün beklediği API "
                "eksik: " + ", ".join(eksik_api) + ". Girdiler hazır; çözücü "
                "ÇAĞRILMADI — API bilinmeden çağrı uydurulmaz, sahte termal "
                "alan üretilmez."),
            "missing_api": eksik_api,
            "warning": _warning(WARN_THERMAL_SOLVER_UNAVAILABLE),
            "inputs": inputs,
        }

    # --- Ortam (çözüm) girdileri: motor yayımlamaz, çağıran verir ---------
    T0 = _finite_positive(ambient_temperature_K)
    if T0 is None:
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": inputs["engine_layout"],
            "missing": ["ambient_temperature_K"],
            "reason": (
                "Başlangıç koşulu tekdüze ORTAM SICAKLIĞIDIR ve hiçbir motor "
                "çözücüsü bu değeri yayımlamaz (kod tarandı). Çağıran "
                "ambient_temperature_K [K] vermelidir; varsayılan oda "
                "sıcaklığı uydurulup çözücü 'çalışır' gösterilmez."),
            "warning": _warning(WARN_INPUTS_MISSING,
                                missing="ambient_temperature_K"),
            "inputs": inputs,
        }

    if outer_ambient is None:
        outer_bc = ta.AdiabaticBC()
        dis_beyan = (
            "ADYABATİK — çağıran dış ortam verisi vermedi. Uydurma bir "
            "taşınım katsayısı/ortam sıcaklığı konmadı; ısı kaçışı sıfır "
            "sayıldı. Bu KONSERVATİF bir üst sınırdır: gerçek dış yüzey "
            "ısı kaybettiği için tepe cidar sıcaklığı bu koşudakinden "
            "düşük olur. Gerçek dış koşul için outer_ambient "
            "{'h_W_m2K', 'T_ambient_K', 'emissivity'} verilmelidir.")
    else:
        if not isinstance(outer_ambient, dict):
            outer_ambient = {}
        h_out = _finite_nonnegative(outer_ambient.get("h_W_m2K"))
        T_out = _finite_positive(outer_ambient.get("T_ambient_K"))
        eps = _finite_nonnegative(outer_ambient.get("emissivity", 0.0))
        eksik_dis = []
        if h_out is None:
            eksik_dis.append("outer_ambient.h_W_m2K")
        if T_out is None:
            eksik_dis.append("outer_ambient.T_ambient_K")
        if eps is None or eps > 1.0:
            eksik_dis.append("outer_ambient.emissivity ([0, 1])")
        if eksik_dis:
            return {
                "status": BRIDGE_STATUS_NOT_MODELLED,
                "engine_layout": inputs["engine_layout"],
                "missing": eksik_dis,
                "reason": ("outer_ambient verildi ama alanları geçerli değil; "
                           "eksik/geçersiz: " + ", ".join(eksik_dis)
                           + ". Eksik alan varsayılanla doldurulmaz."),
                "warning": _warning(WARN_INPUTS_MISSING,
                                    missing=", ".join(eksik_dis)),
                "inputs": inputs,
            }
        outer_bc = ta.AmbientBC(h=h_out, T_ambient=T_out, emissivity=eps)
        dis_beyan = (
            f"çağıranın verdiği dış ortam: doğal taşınım h = {h_out:g} "
            f"W/(m²K), T_ort = {T_out:g} K, yayıcılık ε = {eps:g} "
            "(ışıma D2 içinde lineerleştirilir, hatası D2 meta'sında)")

    # --- Mesh + sınır koşulları + çözüm -----------------------------------
    mesh = build_wall_mesh(inputs["contour"], inputs["thickness_m"],
                           int(n_axial), int(n_radial),
                           offset_mode=offset_mode)

    tm = inputs["thermal_material"]
    material = ta.ThermalMaterial(
        rho=tm["density_kg_m3"],
        cp=tm["specific_heat_J_kgK"],
        k=tm["thermal_conductivity_W_mK"],
        name=inputs["material_key"],
    )

    x_m = inputs["h_x_m"]
    h_g = inputs["h_g_W_m2K"]
    t_rec = inputs["t_recovery_K"]
    inner_bc = ta.ConvectionBC(
        h=lambda z, _x=x_m, _h=h_g: np.interp(z, _x, _h),
        T_inf=lambda z, _x=x_m, _t=t_rec: np.interp(z, _x, _t),
    )

    res = ta.solve_transient_auto(
        mesh, material,
        t_end=inputs["burn_time_s"],
        inner_bc=inner_bc,
        outer_bc=outer_bc,
        T_initial=T0,
        tol=ta.DEFAULT_DT_TOL if dt_tol is None else float(dt_tol),
        n_steps0=ta.DEFAULT_N_STEPS0 if n_steps0 is None else int(n_steps0),
        max_halvings=(ta.DEFAULT_MAX_DT_HALVINGS if max_halvings is None
                      else int(max_halvings)),
    )

    # --- İç (gaz tarafı) yüzey özeti — çözücü çıktısından türetilir -------
    ic_dugumler = mesh.inner_nodes
    T_ic = res.T_final[ic_dugumler]
    z_ic = mesh.nodes[ic_dugumler, 0]
    i_ic = int(np.argmax(T_ic))
    inner_surface = {
        "_basis": ("iç yüzey (j = 0) düğümlerinin SON andaki sıcaklığı; "
                   "çözücü alanından okundu, ayrıca hesap yapılmadı"),
        "node_ids": ic_dugumler,
        "z_m": z_ic,
        "T_final_K": T_ic,
        "peak_T_K": float(T_ic[i_ic]),
        "peak_z_m": float(z_ic[i_ic]),
    }

    # --- Malzeme sıcaklık sınırı: D2 bunu bilerek çağırana bırakır --------
    uyarilar = []
    sinir = {
        "_basis": ("materials_db kaydından okunan sınırlar; D2 çözücüsü faz "
                   "değişimini modellemez ve sınır denetimini AÇIKÇA çağıran "
                   "katmana bırakır (thermal_axisym meta.not_modelled). "
                   "Karşılaştırma tüm alanın tepe sıcaklığıyla yapılır."),
        "allowable_temperature_K": tm.get("allowable_temperature_K"),
        "melting_point_K": tm.get("melting_point_K"),
        "peak_wall_T_K": float(res.peak_wall_T),
        "exceeds_allowable": None,
        "exceeds_melting": None,
    }
    allow = tm.get("allowable_temperature_K")
    melt = tm.get("melting_point_K")
    if allow is not None:
        sinir["exceeds_allowable"] = bool(res.peak_wall_T > allow)
    if melt is not None:
        sinir["exceeds_melting"] = bool(res.peak_wall_T > melt)
    if sinir["exceeds_allowable"] or sinir["exceeds_melting"]:
        uyarilar.append(_warning(
            WARN_THERMAL_WALL_OVER_ALLOWABLE,
            material=inputs["material_key"],
            peak_wall_T_K=round(float(res.peak_wall_T), 1),
            allowable_K=allow,
            melting_K=melt))

    meta = {
        "_source": "hrma.fea.bridge.run_thermal_from_motor",
        "_basis": ("motor sonucu + çağıranın verdiği eksenel profil ve ortam "
                   "koşulu → girdi çıkarımı (aşağıdaki 'girdiler') → "
                   "hrma.fea.mesh_axisym.build_wall_mesh → "
                   "hrma.fea.thermal_axisym.solve_transient_auto"),
        "girdiler": inputs["_basis"],
        "cozucu": res.meta,
        "sinir_kosullari_koprusu": {
            "ic_yuzey": ("ConvectionBC — h(z) ve T_recovery(z) çağıranın "
                         "verdiği Bartz profilinden (kenar orta noktasında "
                         "lineer enterpolasyon)"),
            "dis_yuzey": dis_beyan,
            "baslangic_kosulu": (f"tekdüze T = {T0:g} K (çağıranın verdiği "
                                 "ortam sıcaklığı; motor yayımlamaz)"),
            "zaman_penceresi": (f"t ∈ [0, {inputs['burn_time_s']:g}] s "
                                "(results['burn_time'])"),
        },
        "mesh_politikasi": {
            "n_axial": int(mesh.n_axial),
            "n_radial": int(mesh.n_radial),
            "n_elems": int(mesh.n_elems),
            "beyan": ("termal yolda MESH yakınsaması otomatik DENETLENMEZ — "
                      "D2 sürücüsü zaman ekseninde yakınsar (adım ikiye "
                      "bölme). Uzamsal ayrıklık yapısal yoldaki merkezî "
                      "başlangıç bölümleridir (DEFAULT_N_AXIAL0, "
                      "DEFAULT_ELEMS_THROUGH_WALL); mesh yakınsaması "
                      "yapılmadığı için sonuç bu beyanla okunmalıdır"),
        },
        "not_modelled": [
            ("termal gerilme / yapısal eşleşme — bu koşu SICAKLIK ALANIDIR; "
             "sıcaklık kaynaklı gerilme ve dayanım deratingi D1 yapısal "
             "koşusuna bağlanmamıştır"),
            ("kamara silindiri — gaz tarafı h(z) yalnız lüle konturunda "
             "tanımlı; termal alan profilin tanımlı olduğu bölgedir"
             if not include_chamber else
             "kamara silindiri istendi; profil o bölgeyi de kapsamalıdır"),
            ("mesh (uzamsal) yakınsaması — yalnız zaman adımı yakınsaması "
             "denetleniyor"),
            ("ρ, c_p, k sıcaklıkla değişimi — materials_db oda sıcaklığı "
             "kaydı sabit alındı"),
        ] + list(res.meta.get("not_modelled", [])),
    }

    return {
        "status": BRIDGE_STATUS_OK,
        "engine_layout": inputs["engine_layout"],
        "inputs": inputs,
        "mesh": {
            "nodes": mesh.nodes,
            "elems": mesh.elems,
            "node_index_grid": mesh.node_index_grid,
            "n_nodes": mesh.n_nodes,
            "n_elems": mesh.n_elems,
            "n_axial": mesh.n_axial,
            "n_radial": mesh.n_radial,
            "meta": mesh.meta,
        },
        "ambient_temperature_K": T0,
        "times_s": res.times,
        "T_final_K": res.T_final,
        "peak_wall_T_history_K": res.peak_wall_T_history,
        "peak_wall_T_K": float(res.peak_wall_T),
        "peak_time_s": float(res.peak_time_s),
        "peak_node": int(res.peak_node),
        "inner_surface": inner_surface,
        "energy": res.energy,
        "time_step": res.meta.get("zaman_adimi"),
        "material_limits": sinir,
        "warnings": uyarilar,
        "result": res,          # ThermalResult — tam alan geçmişi burada
        "mesh_object": mesh,    # AxisymMesh — ileri işleme için
        "meta": meta,
    }


# ===========================================================================
# V2.7 Aşama C — Katı yakıt tanesi kesiti düzlemsel FEA köprüsü
# ---------------------------------------------------------------------------
# Kamara/lüle cidarı eksenel simetriktir ve yukarıdaki yapısal/termal yol onu
# görür; ama tane kesitleri (star/finocyl/slotted) eksenel simetrik DEĞİLDİR
# (docs/mimari/yol-haritasi.md §5). Bu bölüm, kesit geometrisini MOTORUN
# KENDİ fonksiyonlarından alır (geometri yeniden türetilmez — tek kaynak
# solid_rocket_engine port poligon üreticileridir), tane mekaniğini
# SOLID_GRAIN_MECHANICS kaydından okur ve planar_grain çözücüsünü sürer.
# ===========================================================================

#: Düzlemsel tane FEA'sının desteklediği kesitler. wagon_wheel ayrık delikli
#: olduğu için orijine göre yıldız-şekilli DEĞİLDİR (r(θ) tek değerli
#: değil), end_burner'da merkez port yoktur — ikisi de beyanla reddedilir.
PLANAR_GRAIN_SUPPORTED_TYPES = ("bates", "star", "finocyl", "slotted")

#: Bates halkası eksenel simetriktir; dilim genişliği sonuca etki etmez.
#: Yine de dilim çözülür (tam halka gereksiz yere pahalı) ve seçim beyan
#: edilir. 8 = tekillik kapılarından uzak, makul en-boy oranlı dilim.
PLANAR_GRAIN_BATES_SYMMETRY = 8

#: Motor arayüzünün kesit geometrisi alan adları (engine overrides
#: sözlüğünün KENDİ anahtarları — çeviri katmanı yok; birimler arayüzle
#: aynı: sayılar mm, adetler tam sayı, oran birimsiz).
PLANAR_GRAIN_GEOMETRY_KEYS = (
    "star_points", "star_radius",
    "fin_count", "fin_width", "fin_length", "finned_length_fraction",
    "slot_count", "slot_width", "slot_depth",
)


def _planar_grain_reject(grain_type, reason, code, **params):
    """Beyanlı red — uydurma alan içermeyen NOT_MODELLED paketi."""
    return {
        "status": BRIDGE_STATUS_NOT_MODELLED,
        "grain_type": grain_type,
        "missing": [],
        "reason": reason,
        "warning": _warning(code, grain_type=grain_type, **params),
    }


def run_planar_grain_fea(grain_type,
                         propellant_type,
                         outer_diameter_mm,
                         core_diameter_mm,
                         chamber_pressure_bar,
                         grain_length_mm=None,
                         geometry_overrides=None,
                         outer_bc="bonded_rigid",
                         tol=DEFAULT_REFINE_TOL,
                         n_theta0=None,
                         n_radial0=DEFAULT_ELEMS_THROUGH_WALL,
                         max_rounds=DEFAULT_MAX_REFINE_ROUNDS) -> dict:
    """Tane kesiti için uçtan uca 2B düzlemsel FEA koşusu (V2.7 Aşama C).

    Zincir: SolidRocketEngine kurulumu (kesit parametre çözümü + kırpma +
    varsayılan beyanı MOTORUN KENDİ koduyla) → port kesiti (motor poligon
    fonksiyonları) → mesh_planar (1/N simetri dilimi) → planar_grain
    (düzlem şekil değiştirme, B-bar) → yakınsama sürücüsü.

    Parametreler
    ------------
    grain_type : 'bates' | 'star' | 'finocyl' | 'slotted' (desteklenen);
        'wagon_wheel' / 'end_burner' beyanla reddedilir; tanınmayan tip
        motorun kendi ValueError'ını üretir.
    propellant_type : SOLID_GRAIN_MECHANICS anahtarı (motorun aile
        devralma/HTPB düşme kuralları AYNEN geçerli ve beyanlıdır).
    outer_diameter_mm / core_diameter_mm : tane dış çapı / port çapı [mm].
    chamber_pressure_bar : port yüzeyine uygulanan oda basıncı [bar].
    grain_length_mm : yalnız beyan içindir — düzlem şekil değiştirme kesiti
        tane boyundan bağımsızdır; verilmezse motor varsayılanı kullanılır
        ve kesit sonucunu ETKİLEMEZ.
    geometry_overrides : arayüz alan adlarıyla kesit parametreleri
        (PLANAR_GRAIN_GEOMETRY_KEYS); aralık dışı değerleri motorun kendisi
        reddedip design_warnings ile beyan eder.
    outer_bc / tol / n_theta0 / n_radial0 / max_rounds : planar_grain
        çözücüsüne aynen geçer (merkezî varsayılanlar; sayı tekrarlanmaz).

    Dönüş: status='ok' paketi (mesh + alanlar + port gerinimi + yakınsama +
    beyan zinciri) ya da beyanlı NOT_MODELLED. Geçersiz sayısal girdi
    (negatif web, port >= dış çap, geçersiz basınç) ValueError fırlatır.
    """
    from hrma.engines.solid_rocket_engine import (
        SHAPELY_AVAILABLE,
        SUPPORTED_GRAIN_TYPES,
        SolidRocketEngine,
    )
    from hrma.fea.planar_grain import (
        DEFAULT_N_THETA0,
        solve_grain_with_refinement,
    )

    grain_type = str(grain_type)
    if grain_type not in SUPPORTED_GRAIN_TYPES:
        raise ValueError(
            f"Unsupported grain type '{grain_type}'. Supported grain "
            f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")
    if grain_type not in PLANAR_GRAIN_SUPPORTED_TYPES:
        nedenler = {
            "wagon_wheel": (
                "wagon_wheel kesiti ayrık deliklerden oluşur; port sınırı "
                "orijine göre tek değerli r(θ) DEĞİLDİR ve 1/N dilim modeli "
                "kurulamaz. Bu kesit için düzlemsel tane FEA'sı "
                "modellenmemiştir — uydurma alan üretilmez."),
            "end_burner": (
                "end_burner taneli motorda merkez port yoktur (sigara "
                "yanması); iç basınçlı halka kesit modeli bu tipe uymaz. "
                "Düzlemsel tane FEA'sı bu tip için modellenmemiştir."),
        }
        return _planar_grain_reject(
            grain_type,
            nedenler.get(grain_type,
                         f"'{grain_type}' düzlemsel tane FEA'sında "
                         "desteklenmiyor."),
            WARN_PLANAR_GRAIN_UNSUPPORTED)

    d_out = _finite_positive(outer_diameter_mm)
    d_core = _finite_positive(core_diameter_mm)
    p_bar = _finite_positive(chamber_pressure_bar)
    if d_out is None or d_core is None:
        raise ValueError("outer_diameter_mm ve core_diameter_mm sonlu ve "
                         "kesin pozitif olmalı.")
    if p_bar is None:
        raise ValueError("chamber_pressure_bar sonlu ve kesin pozitif "
                         "olmalı.")
    if d_core >= d_out:
        raise ValueError(
            f"Port çapı ({d_core:g} mm) tane dış çapını ({d_out:g} mm) "
            "aşıyor ya da ona eşit: web negatif/sıfır, geometri fiziksel "
            "değil.")

    if grain_type != "bates" and not SHAPELY_AVAILABLE:
        return _planar_grain_reject(
            grain_type,
            "Kesit poligonunun TEK kaynağı motorun shapely tabanlı port "
            "üreticileridir ve shapely kurulu değil. Geometri yeniden "
            "türetilmez (tek-kaynak kuralı); shapely kurulmalı ya da "
            "bates seçilmelidir.",
            WARN_PLANAR_GRAIN_SHAPELY)

    overrides = {k: v for k, v in dict(geometry_overrides or {}).items()
                 if k in PLANAR_GRAIN_GEOMETRY_KEYS and v not in (None, "")}
    l_mm = _finite_positive(grain_length_mm)
    ctor = dict(grain_type=grain_type, propellant_type=str(propellant_type),
                chamber_diameter=d_out, core_diameter=d_core,
                chamber_pressure=p_bar, overrides=overrides)
    if l_mm is not None:
        ctor["grain_length"] = l_mm
    engine = SolidRocketEngine(**ctor)

    # --- Kesit geometrisi: motorun KENDİ fonksiyonlarından ----------------
    r_outer = engine.D_chamber / 2.0
    varsayilanlar, kirpilanlar = [], []
    if grain_type == "bates":
        r_inner = engine.D_core / 2.0
        n_sym = PLANAR_GRAIN_BATES_SYMMETRY
        geom_beyan = {
            "kaynak": "engine.D_core / 2 (dairesel port; poligon gerekmez)",
            "kesit": "halka (bates)",
            "simetri_dilimi": (
                f"1/{n_sym} — bates eksenel simetriktir, dilim genişliği "
                "sonuca etki etmez (PLANAR_GRAIN_BATES_SYMMETRY)"),
        }
    else:
        if grain_type == "star":
            n_sym, depth = engine._star_params()
            poly = engine._star_port_polygon()
            varsayilanlar = [k for k in ("star_points", "star_radius")
                            if k not in overrides]
            geom_beyan = {
                "kaynak": ("engine._star_port_polygon() — zikzak star, "
                           "uçlar θ = 2πk/N (ilk uç θ = 0 ayna düzlemi)"),
                "kesit": f"star ({n_sym} uç, uç derinliği {depth * 1000:.3f} mm"
                         " — motorun kırptığı değer)",
                "simetri_dilimi": f"1/{n_sym} (uç sayısı)",
            }
        elif grain_type == "slotted":
            n_sym, width, depth, varsayilanlar, kirpilanlar = \
                engine._slotted_params()
            poly = engine._slotted_port_polygon()
            geom_beyan = {
                "kaynak": ("engine._slotted_port_polygon() — merkez daire ∪ "
                           "radyal yuvalar, yuva merkezleri θ = 2πk/N "
                           "(ilk yuva θ = 0 ayna düzlemi)"),
                "kesit": (f"slotted ({n_sym} yuva, genişlik "
                          f"{width * 1000:.3f} mm, derinlik "
                          f"{depth * 1000:.3f} mm — motorun çözdüğü "
                          "değerler)"),
                "simetri_dilimi": f"1/{n_sym} (yuva sayısı)",
            }
        else:  # finocyl
            n_sym, width, depth, frac, varsayilanlar, kirpilanlar = \
                engine._finocyl_params()
            poly = engine._finocyl_port_polygon()
            geom_beyan = {
                "kaynak": ("engine._finocyl_port_polygon() — KANATÇIKLI "
                           "kesit (en geniş port, gerilme yoğunlaşmasını "
                           "taşıyan kesit). Finocyl eksenel olarak iki "
                           "kesitlidir; düz silindirik bölüm bates halkası "
                           "problemidir ve bu koşuda ÇÖZÜLMEZ (beyan)."),
                "kesit": (f"finocyl kanatçıklı bölüm ({n_sym} kanatçık, "
                          f"genişlik {width * 1000:.3f} mm, derinlik "
                          f"{depth * 1000:.3f} mm, kanatçıklı boy oranı "
                          f"{frac:g})"),
                "simetri_dilimi": f"1/{n_sym} (kanatçık sayısı)",
            }
        from hrma.fea.mesh_planar import port_radius_sampler_from_polygon
        r_inner = port_radius_sampler_from_polygon(
            np.asarray(poly.exterior.coords, dtype=float))

    # --- Tane mekaniği: SOLID_GRAIN_MECHANICS kaydından (motor kuralları) --
    mech = engine._grain_mechanics()
    material = Material(E=float(mech["elastic_modulus_pa"]),
                        nu=float(mech["poisson_ratio"]),
                        yield_strength=None,
                        name=str(propellant_type))
    strain_capability = float(mech["strain_capability"])

    ref = solve_grain_with_refinement(
        r_inner, r_outer, material,
        bore_pressure_pa=p_bar * PA_PER_BAR,
        symmetry_fraction=int(n_sym),
        outer_bc=outer_bc,
        strain_capability=strain_capability,
        tol=tol,
        n_theta0=DEFAULT_N_THETA0 if n_theta0 is None else int(n_theta0),
        n_radial0=int(n_radial0),
        max_rounds=int(max_rounds),
    )
    res = ref.result

    basis = {
        "_source": "hrma.fea.bridge.run_planar_grain_fea",
        "_basis": ("kesit geometrisi motorun KENDİ port fonksiyonlarından "
                   "(tek-kaynak kuralı: geometri yeniden türetilmez), tane "
                   "mekaniği SOLID_GRAIN_MECHANICS kaydından, çözüm "
                   "hrma.fea.planar_grain (düzlem şekil değiştirme + B-bar)"),
        "geometri": dict(geom_beyan,
                         outer_diameter_mm=d_out,
                         core_diameter_mm=d_core,
                         varsayilan_kullanilan_alanlar=list(varsayilanlar),
                         kirpilan_alanlar=list(kirpilanlar)),
        "tane_boyu": (
            f"grain_length_mm = {l_mm:g} — yalnız beyan; düzlem şekil "
            "değiştirme kesiti tane boyundan bağımsızdır" if l_mm is not None
            else "verilmedi — kesit çözümü tane boyundan bağımsızdır "
                 "(düzlem şekil değiştirme), sonuç etkilenmez"),
        "malzeme": {
            "kaynak": ("SOLID_GRAIN_MECHANICS['" + str(propellant_type)
                       + "'] (engine._grain_mechanics çözümü — aile "
                       "devralma/HTPB düşme kuralları motorunkiyle AYNI)"),
            "kayit_kunyesi": mech.get("source"),
            "devralinan": mech.get("inherited_from"),
            "E_Pa": material.E,
            "nu": material.nu,
            "strain_capability": strain_capability,
        },
        "yuk": {
            "kaynak": "chamber_pressure_bar * PA_PER_BAR",
            "Pc_bar": p_bar,
            "Pc_Pa": p_bar * PA_PER_BAR,
            "dagilim": ("port yüzeyine SABİT Pc — kesit düzleminde basınç "
                        "değişimi modellenmez"),
        },
        "analitik_blok_iliskisi": (
            "Motor sonucundaki grain_structural bloğu (Timoshenko silindir + "
            "nominal Kt) KALIR ve bu kiple ÇELİŞMEZ: analitik blok kasa "
            "esnemesi + kürleme soğumasını içerir ama kesit şeklini Kt "
            "katsayısıyla temsil eder; bu kip kesit şeklinin gerilme "
            "yoğunlaşmasını mesh ile çözer ama viskoelastisite/termal "
            "büzülme/kasa esnemesi modellemez. İkisi birlikte okunmalıdır."),
    }
    if mech.get("inherited_from"):
        basis["malzeme"]["devralma_beyani"] = (
            "kayıt bu yakıtın kendisine ait değil; '"
            + str(mech["inherited_from"]) + "' kaydından devralındı "
            "(motorun beyan kuralı)")

    meta = {
        "_source": "hrma.fea.bridge.run_planar_grain_fea",
        "girdiler": basis,
        "cozucu": res.meta,
        "yakinsama": ref.meta,
        "not_modelled": list(res.meta.get("not_modelled", [])),
    }

    # Motorun kendi girdi uyarıları (aralık dışı red, mekanik kayıt düşmesi)
    # AYNEN taşınır — sessiz varsayım yok.
    uyarilar = [w for w in getattr(engine, "design_warnings", [])
                if isinstance(w, dict)]

    return {
        "status": BRIDGE_STATUS_OK,
        "grain_type": grain_type,
        "propellant_type": str(propellant_type),
        "symmetry_fraction": int(n_sym),
        "inputs": basis,
        "von_mises_nodal": res.von_mises_nodal,
        "von_mises_gauss_max": res.max_von_mises,
        "max_principal_nodal": res.max_principal_nodal,
        "displacement": res.displacement,
        "stress_nodal": res.stress_nodal,
        "bore": {
            "node_ids": res.bore_node_ids,
            "strain_nodal": res.bore_strain_nodal,
            "strain_edges": res.bore_strain_edges,
            "max_strain": res.max_bore_strain,
            "strain_capability": strain_capability,
            "strain_margin": res.strain_margin,
            "_basis": res.meta.get("bore_strain_kaynagi"),
        },
        "mesh": {
            "nodes": ref.mesh.nodes,
            "elems": ref.mesh.elems,
            "node_index_grid": ref.mesh.node_index_grid,
            "n_nodes": ref.mesh.n_nodes,
            "n_elems": ref.mesh.n_elems,
            "n_theta": ref.mesh.n_theta,
            "n_radial": ref.mesh.n_radial,
            "meta": ref.mesh.meta,
        },
        "convergence": {
            "converged": ref.converged,
            "final_rel_change": ref.final_rel_change,
            "tol": ref.tol,
            "history": ref.history,
            # Kabul ölçütü (port lif gerinimi, SP-8073) hükmü — vM tepe
            # değeri ν=0,4995 yakın-sıkıştırılamazlıkta yavaş yakınsar ve
            # kabul ölçütü DEĞİLDİR; hüküm bu bloktan okunur
            # (planar_grain.GrainRefinementResult.acceptance).
            "acceptance": ref.acceptance,
            "beyan": ref.meta.get("beyan"),
        },
        "warnings": uyarilar,
        "result": res,          # PlanarGrainResult — ileri işleme için
        "refinement": ref,      # GrainRefinementResult
        "meta": meta,
    }
