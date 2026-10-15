"""Gerçek STEP (AP214) katı model üretimi — build123d/OCC tabanlı.

Eski durum: "STEP" butonu ya alert'ti ya da FreeCAD'e bağlıydı (kurulu değil,
hiç çalışmadı). Bu modül build123d (OpenCascade çekirdeği) ile ÇÖZÜCÜNÜN
kendi geometrisinden parametrik katılar üretir:

  - chamber   : silindirik duvar + baş kapak (revolve edilmiş kapalı profil)
  - nozzle    : gerçek iç kontur (sample_nozzle_inner_contour — 2D/3D/STL ile
                AYNI tek kaynak) + duvar ofseti, eksen etrafında revolve
  - fuel_grain: portlu halka silindir
  - injector  : orifis delikli plaka (gerçek boolean delikler)

Her bileşen ayrı .step + tümü tek assembly .step olarak yazılır.
build123d import edilemezse RuntimeError yükselir; endpoint bunu 501 olarak
kullanıcıya AÇIKÇA raporlar (sessiz düşüş yok).

EKSEN SÖZLEŞMESİ (ÖH Z5S / defter P9B2-28): bu modülün ürettiği katıların
motor ekseni **+X**'tir ve x = 0 enjektör yüzüdür. Aynı CAD paketindeki STL
mesh'leri (``hrma/export/cad_visualization.py``) **+Z** ekseninde kuruludur;
iki dosya birlikte açıldığında motor 90° dönük görünür. Sözleşme
:data:`STEP_AXIS_NOTE` metninde, montaj parçasının adında ve
:func:`step_package_readme` çıktısında taşınır.
"""

class StepExportDataError(ValueError):
    """STEP üretilemez: girdi/analiz EKSİK (sunucu arızası DEĞİL).

    ÖH D18 / P16B4-02 (Fable-D16 ŞART: "export-step'in 500'ü adlı 422'ye
    dönsün"). ÖLÇÜLDÜ (taban 9071a64, ``once.json`` A bölümü): sağlıklı
    bir gövdede bile ``/api/export-step`` HTTP **500** + "chamber wall
    thickness is not available from the structural analysis ... refusing to
    emit a manufacturing STEP with an assumed wall" veriyordu. Metin
    DOĞRUYDU — reddin kendisi fail-closed ve yerinde — ama taşıyıcı
    yanlıştı: 5xx "sunucu arızası" demektir, izleme katmanları bunu nöbetçi
    çağırır ve istemci düzeltilebilir bir eksik gönderdiğini anlamaz.
    Kardeş uçlar (``-stl``, ``-dxf``, ``-cad``) aynı girdi sınıfına adlı
    422 veriyor.

    ``ValueError`` alt sınıfıdır: bu modülü ``except ValueError`` ile saran
    mevcut çağıranlar ve bekçiler AYNEN çalışmaya devam eder.

    ÖH D30 / OH-D29-09 (S1-05 kalan yarısı) — RET ARTIK ALANI ADIYLA VERİR.
    ÖLÇÜLDÜ (taban ``ab7cf68b``, ``once_taban.json`` K1): ihracat ailesinin
    32 ret hücresinin 22'sinde ``invalid_fields`` yoktu; ``/api/export-step``
    ise makine-okur HİÇBİR alan adı vermiyordu. Ölçümün EYLEME DÖNÜŞTÜRME
    turu (reddin ADLANDIRDIĞI yolları doldurup yeniden gönder): ``-stl`` tek
    adımda 200'e çıkıyordu, ``-step`` sıfır yol adlandırdığı için 422'de
    KİLİTLİ kalıyordu — istemci düzeltilebilir bir eksik gönderdiğini
    okuyabiliyor ama NEYİ göndereceğini okuyamıyordu. Ret metni doğruydu;
    eksik olan, metnin yanında duran makine-okur alan künyesiydi.

    ``invalid_fields`` aile sözleşmesinin kendisidir (``field`` + ``reason``,
    gerektiğinde ``accepted_paths``); yollar ``motor_data``ya GÖRELİDİR,
    çünkü kardeş ``/api/export-stl``in ``missing_fields`` listesi de öyledir.
    """

    def __init__(self, message, invalid_fields=()):
        super().__init__(message)
        #: Aile sözleşmesi: ``[{'field': <motor_data'ya göreli yol>,
        #: 'reason': <kod>, ...}]``. ZORUNLU DEĞİLDİR — tek argümanla çağıran
        #: mevcut kod aynen çalışır ve boş liste alır.
        self.invalid_fields = [dict(k) for k in (invalid_fields or ())]


import os

import numpy as np

from hrma.constants import MOTOR_TYPES
from hrma.engines.nozzle_design import (
    CONTOUR_ENVELOPE_TOLERANCE_MM, CONTOUR_POINT_MERGE_MM, NOZZLE_CONTOUR_FIELD,
    NozzleContourError, nozzle_contour_gate, sample_nozzle_inner_contour)
from hrma.export.export_workspace import (
    atomic_produce, new_workspace, purge_stale_workspaces)
from hrma.utils.input_guard import (
    finite_number, first_finite_positive, safe_name)

try:
    from build123d import (
        BuildPart, BuildSketch, BuildLine, Plane, Polyline, Line,
        make_face, revolve, Axis, Cylinder, Pos, Compound, export_step,
        Mode, Locations, Edge, Wire, Face,
    )
    # Pürüzsüz lüle konturu (ÖH V3 CAD · §28-41): build123d'nin kendi OCC
    # bağlaması (OCP); build123d kuruluysa o da vardır.
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.GC import GC_MakeSegment
    from OCP.GeomAPI import GeomAPI_Interpolate
    from OCP.GeomConvert import GeomConvert_CompCurveToBSplineCurve
    from OCP.TColgp import TColgp_Array1OfVec, TColgp_HArray1OfPnt
    from OCP.TColStd import TColStd_HArray1OfBoolean
    from OCP.gp import gp_Pnt, gp_Vec
    BUILD123D_AVAILABLE = True
except Exception:  # ImportError ve OCC yükleme hataları
    BUILD123D_AVAILABLE = False


# ÖH D32 / OH-D31-16: enjektör plakasının ÜRETEÇ YEDEĞİ KALDIRILDI.
# Eski kural (0,9 x ön kapak, 6-24 mm kelepçesi) hiçbir çözücüden gelmiyordu
# ve kardeş üretici ``cad_visualization`` ÖH D15 / P9B1-13'te aynı ikameyi
# zaten reddetmişti (ölçüm: mesh/gerçek plaka oranı 10,0x). Kalınlık artık
# TEK çözümleyiciden (``_injector_plate_design``) gelir; çözülemiyorsa plaka
# çizilmez. Sabitleri geri koymak, iki üreticiyi yeniden ayrıştırır.
#
# ÖH V3 CAD A1 · H8: ``INJECTOR_PLATE_AXIAL_OFFSET_MM = 4,0`` ("montaj
# boşluğu", çözücüden gelmeyen üreteç sabiti) KALDIRILDI. Plakanın eksenel
# yeri artık STL ile tek kuraldır:
# ``cad_visualization.injector_plate_axial_span_mm``.
#: Delik yarıçapının alt kelepçesi [mm]. Değer v2.6.26'dan beri yerinde;
#: ÖH Z5S'te yalnız ADLANDIRILDI ve ısırdığında BEYAN edilir hâle geldi —
#: eskiden çözücünün verdiği çap sessizce büyütülüyordu.
INJECTOR_MIN_HOLE_RADIUS_MM = 0.25

# ---------------------------------------------------------------------------
# Enjektör devrelerinin yerleşimi (ÖH Z5S / defter P9B2-01, KRİTİK)
# ---------------------------------------------------------------------------
#: Devrelerin KANONİK sırası. Sıra keyfi değil: tek devre yayımlayan motorda
#: (hibrit) o devre OKSİTLEYİCİdir — ``hybrid_rocket_engine`` özet bloğu
#: ``injector_design.number_of_orifices`` alanını doğrudan
#: ``injector_design_detail.ox_circuit['n_orifices']`` alanından kopyalar.
INJECTOR_CIRCUIT_ORDER = ('oxidizer', 'fuel')
#: Devre halkalarının plaka yarıçapına oranı. HİÇBİR çözücü orifis
#: YERLEŞİMİNİ modellemez (devre modeli sayı/çap/ΔP verir, radyal konum
#: vermez); bu yüzden değerler ASSUMED'dır ve parça adında beyan edilir.
#: Sayılar UYDURULMADI: deponun kendi enjektör yüz çizimi
#: (``drawing_generator._injector_face_png``) orifisleri zaten 0,7·R ve
#: 0,38·R halkalarına dağıtıyor — iki çıktı aynı yerleşimi anlatsın diye
#: aynı kesirler kullanılır. İlk devre 0,7·R'de kalır; böylece tek devreli
#: motorların katısı ÖNCEKİYLE BİT-AYNI çıkar.
INJECTOR_RING_RADIUS_FRACTIONS = (0.7, 0.38)

# ---------------------------------------------------------------------------
# Grain'in eksenel yerleşimi (ÖH Z5S / defter P9B2-22)
# ---------------------------------------------------------------------------
# ÖH V3 CAD A2 · H7: iki sabitin TEK tanım noktası artık
# ``cad_visualization``dır (STEP, STL ve DXF aynı
# ``grain_axial_layout_mm``i okur). Burada aynı adlarla yeniden ihraç
# edilir; değerleri değişmedi (0,35 ve 4,0 mm).
from hrma.export.cad_visualization import (  # noqa: E402,F401
    GRAIN_AXIAL_MIN_SLACK_MM, GRAIN_AXIAL_POSITION_FRACTION)
#: ÖH D15 (defter P9B2-12) — SESSİZ KIRPMA KALDIRILDI.
#:
#: Eskiden grain boyu ``min(L_g, 0.92 * L)`` ile kırpılıyordu. 0,92 fiziksel
#: bir sınır değil, bir üreteç yerleşim tercihiydi ve kırpma HİÇBİR çıktıda
#: beyan edilmiyordu. Ölçüldü (31 Ağustos 2026, ``motor_solid`` fikstürü +
#: ``grain_length_mm = 900``, kamara 400 mm): STEP ``fuel_grain`` 368,000 mm
#: çiziyor, aynı girdiden üretilen DXF ``grain 900.0 mm`` yazıyor —
#: **2,446 kat** fark, iki imalat dosyası aynı motoru anlatmıyor.
#:
#: 0,92 kuralının SAĞLIKLI vakayı da ısırdığı ölçüldü: P09 hibrit fikstürü
#: grain 3387,38 mm / kamara 3509,40 mm = kamaranın **%96,5**'i (hibritte
#: normaldir; kalanı ön/arka yanma odasıdır) ve STEP onu sessizce 3228,65
#: mm'ye kırpıyordu (-%4,7). Yeni kural FİZİKSELDİR: grain kamarasına
#: SIĞMALIDIR. Sığıyorsa çözücünün boyu AYNEN çizilir (DXF ile birebir);
#: sığmıyorsa katı üretilmez (aşağıdaki ValueError) ve rota katmanı aynı
#: girdiyi 422 ``grain_longer_than_chamber`` ile reddeder.

# ---------------------------------------------------------------------------
# Lüle et kalınlığı (ÖH Z5S / defter P9B2-29)
# ---------------------------------------------------------------------------
# Lüle eti, çözücü yayımlamadığında bir üreteç kuralıdır (adlı, beyanlı).
# ÖH V3 CAD A1: kuralın üç sayısının TEK tanım noktası artık
# ``cad_visualization``dır (STEP, STL, kütle, DXF notu ve imalat emniyet
# kapısı aynı ``_nozzle_wall_design``i okur). Burada yalnız aynı adlarla
# yeniden ihraç edilir; ``cad_visualization`` bu modülü İTHAL ETMEZ, çünkü
# bu modül build123d/OCC yığınını yükler (H3-B14: +433 MB) ve imalat kapısının
# reddettiği istek o yığını yüklememelidir.
from hrma.export.cad_visualization import (  # noqa: E402,F401
    NOZZLE_WALL_MIN_MM, NOZZLE_WALL_THROAT_FALLBACK_M,
    NOZZLE_WALL_THROAT_FRACTION)

# ---------------------------------------------------------------------------
# Eksen sözleşmesi (ÖH Z5S / defter P9B2-28)
# ---------------------------------------------------------------------------
#: Bu modülün ürettiği KATILAR motor eksenini +X kabul eder
#: (``_revolve_profile`` profili ``Axis.X`` etrafında döndürür ve x = 0
#: enjektör yüzüdür). Aynı CAD paketindeki STL dosyaları da ARTIK bu
#: sözleşmeye çevrilerek yazılır (ÖH D26 / P15B4-01); sözleşme montaj
#: parçasının adında (CAD ağacında görünür), paket README'sinde ve CAD
#: sözlüğünde taşınır.
#
# ÖH D26 / defter P15B4-01 — BEYAN ÇÖZÜM DEĞİLDİ. Bu metin eskiden ayrışmayı
# ANLATIYORDU ("the STL meshes ... are built about +Z, so rotate them 90 deg
# about Y"), yani kullanıcıya iki dosyayı elle çakıştırmasını söylüyordu.
# Ayrışmanın kendisi ölçülüp kapatıldı (``cad_visualization.export_stl_files``
# dosyaya yazdığı kopyayı pakete çevirir); sözleşme artık TEK yerde,
# ``motor_geometry.EXPORT_AXIS_NOTE``ta yazılıdır ve buradan yalnız okunur.
from hrma.export.motor_geometry import EXPORT_AXIS_NOTE as STEP_AXIS_NOTE


def _num(v, fb):
    """Sonlu sayı ya da ``fb`` yedeği — kural merkezden (OH-D27-11)."""
    return finite_number(v, fb)


def _require():
    if not BUILD123D_AVAILABLE:
        raise RuntimeError(
            "build123d kurulu değil — STEP üretimi yapılamıyor. "
            "Kurulum: pip install build123d 'numpy<2'")


def _revolve_profile(points_rz):
    """(z, r) kapalı profilini X ekseni etrafında revolve eder (katı döner).

    build123d: profil XY düzleminde (x=z ekseni, y=r) çizilir, X ekseni
    etrafında 360° döndürülür.
    """
    pts = [(float(z), float(r)) for z, r in points_rz]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    with BuildPart() as part:
        with BuildSketch(Plane.XY) as sk:
            with BuildLine():
                Polyline(*pts)
            make_face()
        revolve(axis=Axis.X)
    return part.part


# ---------------------------------------------------------------------------
# Pürüzsüz lüle yüzeyi (ÖH V3 CAD · karar §28-41, 14 Eki 2026)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (12 Eki, sıvı örnek): lüle konturu ``Polyline`` ile revolve
# edildiği için STEP'te 130 ayrı CONICAL_SURFACE vardı, B-spline 0 — CAD'de
# ve render'da "çizgi çizgi" basamaklı yüzey. Şimdi AYNI kontur noktalarından
# TEK B-spline eğri geçirilir (interpolasyon: eğri her noktadan TAM geçer;
# noktalar ve dolayısıyla yayımlanan ölçüler — boğaz, çıkış, boy, et —
# DEĞİŞMEZ) ve o eğri revolve edilir: lülenin iç ve dış yüzü STEP'te birer
# düzgün dönel yüzeydir.
#: Lüle türü adı: ``sample_nozzle_inner_contour``un konik dalı ıraksak
#: kısmı TEK doğru parçası olarak verir (yaydan sonra yalnız çıkış noktası).
#: O parça gerçekten bir konidir; interpolasyona sokulursa uzun tek aralık
#: eğriyi salındırır (ölçüldü: sıvı örneğin konik ikizinde eğri eksen
#: boyunca geri dönüyor). Bu yüzden konikte kuyruk DOĞRU kalır, eğriye aynı
#: yönde (G1) eklenir ve sonuç yine TEK B-spline'dır.
NOZZLE_TYPE_CONE = 'conical'
#: ``CONTOUR_POINT_MERGE_MM`` ve ``CONTOUR_ENVELOPE_TOLERANCE_MM`` (çakışık
#: nokta birleştirme ve yarıçap zarfı payı) imalat kontur kapısıyla birlikte
#: ``nozzle_design``a taşındı (14 Eki, CADP D-T5-5: DXF/PDF/STL aynı kapıdan
#: geçer); burada yeniden YAZILMAZ, oradan ithal edilir.
#: Eğrinin denetim örneklemesi: kontur noktası başına ara nokta sayısı.
#: Eksen boyunca geri dönen ya da ekseni kesen (salınan) eğri imalat
#: çıktısına GİRMEZ.
CONTOUR_CHECK_SAMPLES_PER_POINT = 8


def _contour_refusal(reason, message):
    return StepExportDataError(
        message + '; refusing to emit a manufacturing STEP.',
        invalid_fields=[{'field': NOZZLE_CONTOUR_FIELD, 'reason': reason}])


def _occ_bspline_trace(pts, straight_tail):
    """Kontur noktalarından TEK B-spline eğri (XY düzlemi: x = z, y = r).

    ``nozzle_contour_gate``in ``curve_builder``ı: döner ``(eğri, zs, rs)``
    — eğri ve denetim örnekleri. ``straight_tail``: son aralık doğru
    parçasıdır (konik ıraksak). Eğri sondan bir önceki noktaya kadar
    interpolasyonla kurulur, o noktadaki teğeti kuyruk doğrusunun yönüne
    bağlanır (G1) ve doğru aynı B-spline'a eklenir. Eğri her kontur
    noktasından geçer.
    """
    govde = pts[:-1] if straight_tail else pts
    dizi = TColgp_HArray1OfPnt(1, len(govde))
    for i, (z, r) in enumerate(govde):
        dizi.SetValue(i + 1, gp_Pnt(z, r, 0.0))
    kurucu = GeomAPI_Interpolate(dizi, False, CONTOUR_POINT_MERGE_MM)
    if straight_tail:
        (z1, r1), (z2, r2) = pts[-2], pts[-1]
        tegetler = TColgp_Array1OfVec(1, len(govde))
        bayrak = TColStd_HArray1OfBoolean(1, len(govde))
        for i in range(len(govde)):
            son = i == len(govde) - 1
            bayrak.SetValue(i + 1, son)
            tegetler.SetValue(i + 1, gp_Vec(z2 - z1, r2 - r1, 0.0)
                              if son else gp_Vec(0.0, 0.0, 0.0))
        kurucu.Load(tegetler, bayrak, True)
    kurucu.Perform()
    if not kurucu.IsDone():
        raise NozzleContourError(
            'contour_interpolation_failed',
            'the nozzle contour could not be interpolated by a B-spline')
    egri = kurucu.Curve()
    if straight_tail:
        birlestir = GeomConvert_CompCurveToBSplineCurve(egri)
        kuyruk = GC_MakeSegment(gp_Pnt(z1, r1, 0.0),
                                gp_Pnt(z2, r2, 0.0)).Value()
        if not birlestir.Add(kuyruk, CONTOUR_POINT_MERGE_MM):
            raise NozzleContourError(
                'contour_interpolation_failed',
                'the cone segment of the nozzle contour could not be joined '
                'to the interpolated curve')
        egri = birlestir.BSplineCurve()
    u0, u1 = egri.FirstParameter(), egri.LastParameter()
    n = max(2, CONTOUR_CHECK_SAMPLES_PER_POINT * len(pts))
    ornek = [egri.Value(u0 + (u1 - u0) * k / (n - 1)) for k in range(n)]
    return (egri, np.array([p.X() for p in ornek]),
            np.array([p.Y() for p in ornek]))


def _contour_bspline_edge(points_zr, straight_tail,
                          throat_radius_curvature_mm=None,
                          unreadable_angle_fields=None):
    """Kontur noktalarından TEK B-spline kenar — imalat kontur kapısından.

    Denetimin kendisi ``nozzle_design.nozzle_contour_gate``tedir (TEK işlev;
    DXF, çizim PDF'i ve STL de aynı kapıdan geçer). Burada yalnız eğri
    kuruluşu (``_occ_bspline_trace``) verilir ve kapının adlı reddi aile
    sözleşmesine (``StepExportDataError``) taşınır: eksen boyunca geri
    dönen ya da ekseni kesen (salınan) eğri, noktaların yarıçap zarfını
    taşan eğri ve pozitif olmayan boğaz yayı sessiz bozuk yüzey yerine ret.
    """
    try:
        _pts, egri = nozzle_contour_gate(
            points_zr, straight_tail=straight_tail,
            curve_builder=lambda pts: _occ_bspline_trace(pts, straight_tail),
            throat_radius_curvature_mm=throat_radius_curvature_mm,
            unreadable_angle_fields=unreadable_angle_fields)
    except NozzleContourError as e:
        raise _contour_refusal(e.reason, e.message) from None
    return Edge(BRepBuilderAPI_MakeEdge(egri).Edge())


def _revolve_smooth_nozzle(inner_zr, wall_mm, straight_tail,
                           throat_radius_curvature_mm=None,
                           unreadable_angle_fields=None):
    """Lüle katısı: iç kontur (B-spline) + dış kontur (aynı noktalar r + et,
    aynı B-spline kuruluşu) + iki uç halka düzlemi; X ekseni etrafında
    revolve (``_revolve_profile`` ile aynı eksen ve aynı profil tanımı).

    Dış kontur iç konturun noktalarının r + ``wall_mm`` kaydırılmışıdır
    (eski çokgen profille AYNI tanım). Kiriş boyu parametrelemesi kaydırmada
    değişmediği için dış eğri iç eğrinin tam kaydırılmışıdır: her eksenel
    istasyonda et = ``wall_mm``.

    ``throat_radius_curvature_mm``: konturu çizen boğaz yayı (örnekleyici
    ``meta``sı); imalat kontur kapısı onu da denetler (DXF/PDF/STL ile aynı).
    ``unreadable_angle_fields``: örnekleyici ``meta``sının yayımlanmış ama
    sonlu olmayan açı yolları (CADI D-T6-4; DXF/PDF/STL ile aynı kapı).
    """
    ic = _contour_bspline_edge(
        inner_zr, straight_tail,
        throat_radius_curvature_mm=throat_radius_curvature_mm,
        unreadable_angle_fields=unreadable_angle_fields)
    dis = _contour_bspline_edge([(z, r + wall_mm) for z, r in inner_zr],
                                straight_tail)
    (za, ra), (zb, rb) = inner_zr[0], inner_zr[-1]
    giris = Edge.make_line((float(za), float(ra) + wall_mm, 0.0),
                           (float(za), float(ra), 0.0))
    cikis = Edge.make_line((float(zb), float(rb), 0.0),
                           (float(zb), float(rb) + wall_mm, 0.0))
    tel = Wire.combine([giris, ic, cikis, dis])
    if len(tel) != 1 or not tel[0].is_closed:
        raise _contour_refusal(
            'contour_profile_not_closed',
            'the smooth nozzle profile does not close')
    return revolve(Face(tel[0]), axis=Axis.X)


def _export_step_atomic(shape, path):
    """STEP dosyasını ATOMİK yazar (yarım dosya okunamasın — D1)."""
    return atomic_produce(path, lambda tmp: export_step(shape, tmp))


# ---------------------------------------------------------------------------
# BATES segment planı (ÖH D35 · OH-ON-04)
# ---------------------------------------------------------------------------
# ÖH V3 CAD A2 · H7 — TAŞINDI: planın tamamı (``_grain_segment_plan``,
# ``_grain_segment_plan_derived``, ``grain_stack_plan``,
# ``_grain_gap_reading`` ve sabitleri) artık ``cad_visualization``da TEK
# yerde yaşar. Gerekçe ölçüldü: DXF çizimi segmentleri STEP ile aynı
# plandan çizmek zorunda (7 Eki CAD kontrolü H7: STEP 3 segment, STL ve
# DXF tek parça) ve bu modülü ithal etmek build123d/OCC yığınını yükler
# (H3-B14: +433 MB). Adlar burada aynen yeniden ihraç edilir (bekçiler ve
# çağıranlar ``step_export._grain_segment_plan``i okumaya devam eder).
from hrma.export.cad_visualization import (  # noqa: E402,F401
    GRAIN_GAP_ABSENT, GRAIN_GAP_SOURCE_TEXT,
    GRAIN_SEGMENT_LENGTH_TOLERANCE_MM, _grain_gap_reading,
    _grain_segment_plan, _grain_segment_plan_derived, grain_stack_plan)

# ---------------------------------------------------------------------------
# Enjektör delik planı — İKİ DEVRE (ÖH Z5S / defter P9B2-01, KRİTİK)
# ---------------------------------------------------------------------------

#: Devre başına, çözücünün delik SAYISINI yayımladığı alanlar (öncelik sırası).
#: ``number_of_elements`` en sonda: sıvı motor bir "eleman"ı devre başına BİR
#: delik olarak boyutlandırır (``liquid_rocket_engine``:
#: ``ox_orifice_count = fuel_orifice_count = n_elements``), yani devrenin kendi
#: sayısı yoksa eleman sayısı o devrenin delik sayısıdır.
_CIRCUIT_COUNT_FIELDS = {
    'oxidizer': (('injector_design_detail.ox_circuit', 'n_orifices'),
                 ('top', 'ox_orifice_count'),
                 ('injector', 'ox_orifice_count'),
                 ('injector', 'number_of_elements')),
    'fuel': (('injector_design_detail.fuel_circuit', 'n_orifices'),
             ('top', 'fuel_orifice_count'),
             ('injector', 'fuel_orifice_count'),
             ('injector', 'number_of_elements')),
}
#: Devre başına orifis ÇAPI alanları [mm].
_CIRCUIT_DIAMETER_FIELDS = {
    'oxidizer': (('injector_design_detail.ox_circuit', 'orifice_d_mm'),
                 ('top', 'ox_orifice_diameter'),
                 ('injector', 'oxidizer_orifice_diameter_mm'),
                 ('injector', 'ox_orifice_diameter_mm')),
    'fuel': (('injector_design_detail.fuel_circuit', 'orifice_d_mm'),
             ('top', 'fuel_orifice_diameter'),
             ('injector', 'fuel_orifice_diameter_mm')),
}
#: Devre adı TAŞIMAYAN (eski/uyarlanmış) şema. ``motor_geometry``nin sıvı
#: uyarlayıcısı ve hibrit özet bloğu bu adları kullanır.
_UNNAMED_COUNT_FIELDS = ('number_of_orifices', 'n_holes')
_UNNAMED_DIAMETER_FIELDS = ('orifice_diameter_mm', 'hole_diameter')


def _pick(md, inj, detail, specs, inj_key='injector_design'):
    """Alan listesindeki İLK sonlu-pozitif değeri (değer, alan_adı) döndürür.

    ``inj_key``: ``inj`` bloğunun gövdedeki GERÇEK adı. Künye eskiden her
    durumda ``injector_design.`` yazıyordu; panel (``injector_results``)
    kazandığında imalat çıktısı sayının geldiği bloğun adını YANLIŞ
    söylüyordu (ÖH D33-2 / OH-D32-04 — künye yalnız gerçeği söyler).
    """
    from hrma.export.motor_geometry import _first_positive

    for where, key in specs:
        if where == 'top':
            block, prefix = md, ''
        elif where == 'injector':
            block, prefix = inj, f'{inj_key}.'
        else:
            sub = where.split('.')[-1]
            block = detail.get(sub) if isinstance(detail, dict) else None
            prefix = f'injector_design_detail.{sub}.'
        if not isinstance(block, dict):
            continue
        value = _first_positive(block.get(key))
        if value is not None:
            return value, prefix + key
    return None, None


def resolve_injector_plan(motor_results, motor_type='hybrid'):
    """Enjektör plakasının delik planını ÇÖZÜCÜDEN çözer — HER DEVRE İÇİN.

    ÖH Z5S / defter P9B2-01 (KRİTİK). Ölçüldü (27 Ağustos 2026, 10 kN sıvı
    motor, Pc = 100 bar, MR = 2,5): çözücü ``number_of_elements = 5``,
    ``fuel_orifice_diameter_mm = 2,3073`` **ve**
    ``oxidizer_orifice_diameter_mm = 2,4994`` yayımlarken bu modülün kapısı
    yalnız ``number_of_orifices | n_holes | number_of_elements`` +
    ``orifice_diameter_mm | hole_diameter | fuel_orifice_diameter_mm``
    zincirini okuyordu. Sonuç: plakaya 5 YAKIT deliği deliniyor, OKSİTLEYİCİ
    devresi %0 iniyordu — üretilen enjektör hiç püskürtemez.

    Yeni sözleşme (paket notundaki iki seçenekten İKİSİ birden):

    * çözücü bir devreyi yayımlıyorsa o devre GERÇEKTEN delinir;
    * yayımlamıyorsa devre parça adında BEYAN edilir ("NOT drilled ...") —
      mevcut ``ASSUMED ring radius`` kalıbının eşleniği. Sayı uydurulmaz.

    Döner::

        {'claimed': bool,          # sonuçta bir enjektör iddiası var mı
         'circuits': [{'name', 'n', 'd_mm', 'count_field', 'diameter_field'}],
         'missing': [str],         # çizilmeyen devrelerin beyan metinleri
         'not_analyzed': bool}     # motor planı REDDETTİ mi

    ``claimed`` False ise çağıran parçayı hiç çizmez (grain ilkesi H4-1'in
    eşleniği); ``claimed`` True ama ``circuits`` boşsa çağıran REDDEDER.
    """
    md = motor_results if isinstance(motor_results, dict) else {}
    inj, _key, circuits, missing = resolve_injector_circuits(
        md, motor_type=motor_type)
    if inj is None:
        return {'claimed': False, 'circuits': [], 'missing': [],
                'not_analyzed': False}
    return {
        'claimed': True,
        'circuits': circuits,
        'missing': missing,
        'not_analyzed': str(inj.get('status') or '').lower() == 'not_analyzed',
    }


#: Enjektör iddiasını taşıyabilen blokların ÖNCELİK SIRASI. TEK KAYNAK:
#: STEP üreticisi (``resolve_injector_plan``) ve STL/çizim üreticisi
#: (``cad_visualization._injector_spec``) bu demeti okur, kendi sırasını
#: yazmaz.
#:
#: ÖH D33-2 / defter OH-D32-04. ÖLÇÜLDÜ (taban ``5e0714c1``,
#: ``docs/scofield/raw/OH/D33-2/ihracat-cad/a1/once.json`` bölüm A4): aynı
#: sıvı gövdeye enjektör paneli sonucu eklendiğinde STL/çizim katmanı paneli
#: BİRİNCİL sayıp **125 delik x Ø0,957 mm** yazarken bu modül
#: ``injector_design``i birincil sayıp **12 delik** (6 ox Ø2,4920 + 6 yakıt
#: Ø2,3217) deliyordu — aynı ZIP'te iki farklı makine.
#:
#: Sıra, deponun ZATEN YAZILI doktrinidir (v2.6.26 K2 notu: *"Panel,
#: enjektörün BİRİNCİL çözücüsüdür"*; bekçileri
#: ``test_cad_geometry_consistency_v2626.py::
#: TestInjectorSingleSourceReachesTheSolid::test_drawing_uses_the_panel_result``
#: ve ``test_export_real_data.py::TestInjectorSingleSource::
#: test_injector_panel_result_wins``). Bu modül paneli yalnız "mevcut
#: paketler bit-aynı kalsın" diye SONA koymuştu (D24 / P15B4-04 notu); o
#: geçici tercih artık iki üreticinin ayrışma kaynağıydı ve kaldırıldı.
INJECTOR_BLOCK_ORDER = ('injector_results', 'injector_design', 'injector')


def injector_declared_count(md, inj, detail, sadece_blok=False,
                            inj_key='injector_design'):
    """Çözücünün YAYIMLADIĞI delik sayısı — çap çözülemese bile.

    ``injector_circuits_from_block`` bir devreyi ancak SAYI ve ÇAP birlikte
    çözülürse döndürür (delik uydurmamak için). Ama teknik çizimin
    ``orifice_count`` alanı bir İDDİADIR, delme emri değil: çözücü sayıyı
    yayımlamışsa çizim onu yazar, plaka yine delinmez.

    ÖH D33-2 / OH-D32-04 — bekçisi ``tests/test_d19_ihracat_a1.py::
    TestP9B123EnjektorKirpmasiBildiriliyor`` (çapı METRE olarak, tanınmayan
    ``orifice_diameter`` adıyla yayımlayan gövde: sayı 125, çap çözülemiyor).
    Alan adları burada da ŞEMADAN gelir, ikinci kez yazılmaz.
    """
    def _kapsam(specs):
        return ([sp for sp in specs if sp[0] == 'injector']
                if sadece_blok else specs)

    toplam = 0
    for name in INJECTOR_CIRCUIT_ORDER:
        n, _f = _pick(md, inj, detail, _kapsam(_CIRCUIT_COUNT_FIELDS[name]),
                      inj_key=inj_key)
        if n is not None:
            toplam += int(round(n))
    if toplam:
        return toplam
    n, _f = _pick(md, inj, detail,
                  _kapsam([('injector', k) for k in _UNNAMED_COUNT_FIELDS]),
                  inj_key=inj_key)
    return int(round(n)) if n is not None else None


def resolve_injector_circuits(md, motor_type='hybrid'):
    """Kazanan enjektör bloğunu ve devre planını çözer.

    Döner ``(block, block_key, circuits, missing)``; hiçbir blok yoksa
    ``(None, None, [], [])``.

    Seçim kuralı: **devre planı YAYIMLAYAN ilk blok kazanır.** Yalnız
    "sözlük mü" diye bakmak yetmez — ölçüldü (ÖH D33-2, ``once.json`` A2):
    sıvı koşumunda panel yalnız ``plate_structural`` taşıyorken bile blok
    olarak seçiliyor, delik planı ise ``injector_design``de duruyordu;
    sonuç STL'de **0 delik**, STEP'te **12 delik**ti. Boş bir blok sırayı
    KİLİTLEMEZ.

    KAYNAK KARIŞTIRMA YASAĞI (v2.6.26 K2): kazanan blok PANEL ise devreler
    yalnız panelin kendi alanlarından okunur. ``injector_design_detail``
    motorun devre modeline aittir; panel adı altında oradan sayı almak, K2
    denetiminin yasakladığı melez spesifikasyonun ta kendisidir.
    """
    md = md if isinstance(md, dict) else {}
    detail = md.get('injector_design_detail')
    if not isinstance(detail, dict):
        detail = {}
    ilk_blok = ilk_key = None
    for key in INJECTOR_BLOCK_ORDER:
        block = md.get(key)
        if not isinstance(block, dict):
            continue
        if ilk_blok is None:
            ilk_blok, ilk_key = block, key
        circuits, missing = injector_circuits_from_block(
            md, block, detail, motor_type=motor_type,
            sadece_blok=(key == 'injector_results'), inj_key=key)
        if circuits:
            return block, key, circuits, missing
    if ilk_blok is None:
        return None, None, [], []
    # Hiçbir blok devre yayımlamadı: kaynak ADI ilk bloktur, devre YOKTUR.
    circuits, missing = injector_circuits_from_block(
        md, ilk_blok, detail, motor_type=motor_type,
        sadece_blok=(ilk_key == 'injector_results'), inj_key=ilk_key)
    return ilk_blok, ilk_key, circuits, missing


def injector_circuits_from_block(md, inj, detail, motor_type='hybrid',
                                 sadece_blok=False,
                                 inj_key='injector_design'):
    """Verilen enjektör bloğundan devre planını çözer. Döner ``(circuits,
    missing)``.

    ``resolve_injector_plan``ın çekirdeği; ALAN ŞEMALARI burada TEK KEZ
    okunur. ``cad_visualization`` da bu fonksiyonu çağırır, böylece STL/çizim
    ile STEP aynı alan adlarını arar (ÖH D33-2 / OH-D32-04).

    ``sadece_blok``: True ise YALNIZ ``inj`` bloğunun kendi alanları okunur
    (üst seviye ve ``injector_design_detail`` kapsam dışı) — panel gibi
    kendi kendine yeten bir çözücü sonucu kazandığında K2'nin melez
    spesifikasyon yasağı böyle uygulanır.
    """
    def _kapsam(specs):
        return ([sp for sp in specs if sp[0] == 'injector']
                if sadece_blok else specs)

    circuits, missing = [], []
    for name in INJECTOR_CIRCUIT_ORDER:
        n, n_field = _pick(md, inj, detail,
                           _kapsam(_CIRCUIT_COUNT_FIELDS[name]),
                           inj_key=inj_key)
        d, d_field = _pick(md, inj, detail,
                           _kapsam(_CIRCUIT_DIAMETER_FIELDS[name]),
                           inj_key=inj_key)
        # Devre ancak İKİ ölçüsü de çözüldüyse delinir: sayı bilinip çap
        # bilinmiyorsa (ya da tersi) delik uydurmak gerekirdi.
        if n is not None and d is not None:
            circuits.append({'name': name, 'n': int(round(n)), 'd_mm': float(d),
                             'count_field': n_field, 'diameter_field': d_field})
        elif name == 'fuel' and motor_type == 'hybrid':
            missing.append(
                'fuel circuit NOT drilled: a hybrid motor burns a solid grain, '
                'it has no fuel injector circuit')
        else:
            missing.append(
                f'{name} circuit NOT drilled: this analysis result does not '
                f'publish its orifice count and diameter (looked for '
                + ', '.join(f'{w.split(".")[-1] if w != "top" else "result"}.{k}'
                            for w, k in _CIRCUIT_COUNT_FIELDS[name])
                + ' / '
                + ', '.join(f'{w.split(".")[-1] if w != "top" else "result"}.{k}'
                            for w, k in _CIRCUIT_DIAMETER_FIELDS[name])
                + ')')

    if not circuits:
        # Devre adı taşımayan (eski/uyarlanmış) şema: motor_geometry'nin sıvı
        # uyarlayıcısı ve hibrit özet bloğu delik planını adsız yayımlar.
        n, n_field = _pick(md, inj, detail,
                           [('injector', k) for k in _UNNAMED_COUNT_FIELDS],
                           inj_key=inj_key)
        d, d_field = _pick(md, inj, detail,
                           [('injector', k) for k in _UNNAMED_DIAMETER_FIELDS],
                           inj_key=inj_key)
        if n is not None and d is not None:
            if motor_type == 'hybrid':
                # Hibritte adsız çift OKSİTLEYİCİ devresidir: motorun özet
                # bloğu bu alanları ox_circuit'ten kopyalar (kaynak:
                # hybrid_rocket_engine, injector_design bloğu).
                circuits = [{'name': 'oxidizer', 'n': int(round(n)),
                             'd_mm': float(d), 'count_field': n_field,
                             'diameter_field': d_field}]
                missing = ['fuel circuit NOT drilled: a hybrid motor burns a '
                           'solid grain, it has no fuel injector circuit']
            else:
                # Hangi itici maddeyi beslediğini SÖYLEMEYEN tek devre.
                # Tahmin edilmez — payload ne diyorsa o yazılır.
                circuits = [{'name': 'unidentified', 'n': int(round(n)),
                             'd_mm': float(d), 'count_field': n_field,
                             'diameter_field': d_field}]
                missing = ['the payload publishes ONE orifice circuit and does '
                           'not say which propellant it feeds; any second '
                           'circuit is NOT drilled in this plate']

    return circuits, missing


#: ÖH V3 CAD · CADP D-T5-2 (14 Eki) — LÜLE HACMİ OKUMA NOTU (EN + TR).
#: ÖLÇÜLDÜ (pürüzsüz yüzey turu, ``kanit/t5/hacim_kahin.json``): FreeCAD
#: ``Shape.Volume`` ve build123d ``.volume`` (OCC varsayılan hassasiyeti)
#: dönel B-spline lüle yüzeyinde %0,04-1,48 yanılıyor (katı örnek lülede
#: +%1,48); OCC uyarlamalı integrali bağımsız kesik koni kâhinine 4e-6
#: içinde uyuyor. Sapma okuyucudadır, geometride değil; imalatçı kütleyi
#: varsayılan okumayla doğrularsa yanlış sonuca varır. HRMA'nın beyan ettiği
#: lüle kütlesinin kaynağı ``cad_visualization`` ``mass_breakdown``
#: ``nozzle_mass_basis`` (aynı kontur, et ve malzeme; kesik koni halka
#: hacmi x yoğunluk). Lüle ya da montaj STEP'i pakette varsa README'ye girer.
STEP_NOZZLE_VOLUME_NOTE = (
    'Nozzle volume/mass in CAD tools: the nozzle walls in these STEP files '
    'are smooth B-spline surfaces of revolution. The default volume of '
    'FreeCAD (Shape.Volume) and of other OpenCASCADE-based tools was '
    'measured to be off by 0.04-1.48 % on such surfaces (+1.48 % on the '
    'solid example nozzle); read the nozzle volume or mass with a '
    'high-precision (adaptive) volume integration. The nozzle mass HRMA '
    'declares (mass_breakdown.nozzle_mass) is not read from this file: it '
    'is integrated over the same contour points, wall and material '
    '(frustum-annulus volume x density).',
    'CAD aracında lüle hacmi/kütlesi: bu STEP dosyalarındaki lüle cidarları '
    'pürüzsüz dönel B-spline yüzeylerdir. FreeCAD (Shape.Volume) ve öteki '
    'OpenCASCADE tabanlı araçların varsayılan hacmi bu yüzeylerde '
    '%0,04-1,48 sapıyor (ölçüldü; katı örnek lülede +%1,48); lüle hacmini '
    'ya da kütlesini yüksek hassasiyetli (uyarlamalı) hacim integraliyle '
    'okuyun. HRMA\'nın beyan ettiği lüle kütlesi '
    '(mass_breakdown.nozzle_mass) bu dosyadan okunmaz: aynı kontur '
    'noktaları, cidar ve malzeme üzerinden integre edilir (kesik koni halka '
    'hacmi x yoğunluk).',
)

#: Notun girdiği parça anahtarları (``step_package_readme`` etiket tablosu):
#: lüle ve onu içeren montaj.
STEP_NOZZLE_VOLUME_NOTE_PARTS = frozenset({'nozzle', 'assembly'})


def step_package_readme(paths, axis_note=STEP_AXIS_NOTE):
    """STEP paketinin parça listesi — ARŞİVDEKİ dosyalardan okunur.

    ÖH Z5S / defter P9B2-20. Ölçüldü: paketin README'si her koşuda dört
    parçayı da sayıyordu ("chamber, nozzle (true contour), fuel grain,
    injector plate (drilled orifices) + assembly") — katı motor paketinde
    enjektör plakası, sıvı motor paketinde yakıt grain'i YOKKEN bile. Parça
    listesi artık iddia değil ÖLÇÜM: yalnız gerçekten üretilmiş dosyalar
    sayılır (aynı fail-closed ilke: dosya yoksa parça yazılmaz).

    ``paths`` üretilen STEP yollarıdır (``generate_step_assembly``ın döndürdüğü
    sözlüğün değerleri). Dönen metin birim satırı İÇERMEZ — birim iddiası
    dosya başlığından okunur ve o iş çağıranın (``app._step_readme_text``)
    kendi ölçümüdür; bu üreteç yalnız parça listesini ve eksen sözleşmesini
    üretir.
    """
    labels = (
        ('chamber', 'chamber (wall + closure head)'),
        ('nozzle', 'nozzle (true inner contour)'),
        ('fuel_grain', 'fuel grain'),
        ('injector', 'injector plate (drilled orifices)'),
        ('assembly', 'assembly'),
    )
    present = []
    present_keys = set()
    for path in paths or ():
        try:
            base = os.path.basename(str(path))
        except Exception:
            continue
        if not os.path.exists(str(path)):
            continue
        for key, text in labels:
            if base.endswith(f'_{key}.step') and text not in present:
                present.append(text)
                present_keys.add(key)
    lines = ['HRMA STEP export (AP214)',
             'Solver-generated parametric solids.']
    if present:
        lines.append('Parts in this archive: ' + ', '.join(present) + '.')
    else:
        lines.append('Parts in this archive: none could be listed - no '
                     'generated STEP file was found at the paths handed to '
                     'this README producer.')
    # Yalnız ilk harf büyütülür: ``capitalize()`` metnin geri kalanını
    # küçültüp "+X" -> "+x", "STL" -> "stl" yapıyordu (eksen adı okunmaz hâle
    # gelir; ölçüldü).
    lines.append(axis_note[:1].upper() + axis_note[1:] + '.')
    # CADP D-T5-2: lüle (ya da onu içeren montaj) dosyası varsa hacim notu.
    if present_keys & STEP_NOZZLE_VOLUME_NOTE_PARTS:
        lines.extend(STEP_NOZZLE_VOLUME_NOTE)
    return '\n'.join(lines) + '\n'


#: ÖH D25 / defter P15B4-04 — ``generate_step_assembly``ın tanıdığı motor
#: tipleri. TEK KAYNAK: uçlar bu demeti okur, kendi listelerini yazmaz.
#:
#: ÖH D25 fix-23 — DEMET BURADA YENİDEN YAZILMAZ. Bu satır
#: ``('hybrid', 'solid', 'liquid')`` literalini İKİNCİ KEZ yazıyordu ve
#: ``tests/test_sabit_tek_kaynak.py::test_motor_types_tek_tanim_noktasi``
#: bunu ikiz tanım olarak yakaladı: üçlünün adlandırılmış tanımı yalnız
#: ``hrma/constants.py``de olabilir (sıra da semantiktir — kayıt gezme
#: sırası ve hata metinleri oradan gelir). Ad KORUNUYOR (uçlar ve bekçiler
#: ``STEP_MOTOR_TYPES``i ithal ediyor), değer tek kaynaktan geliyor; ikisinin
#: ayrışması artık yapısal olarak imkânsız.
STEP_MOTOR_TYPES = MOTOR_TYPES


def normalise_step_motor_type(value):
    """İstekten gelen motor tipini çözer. Döner: ``(tip|None, hata|None)``.

    ÖH D25 (defter P15B4-04). ÖLÇÜLDÜ (taban ``cdf2106``, ``once.json``
    bölüm MA): AYNI katı motor gövdesi (enjektör paneli taşıyan
    ``/calculate_solid`` sonucu) iki uçtan ZIT paket alıyordu —
    ``/export_solid_motor_cad`` uca gömülü ``motor_type='solid'`` ile **4
    STEP** dosyası üretirken, ``/api/export-complete-zip`` tipi HİÇ
    söyleyemediği için bu fonksiyonun ``motor_type='hybrid'`` VARSAYILANINA
    düşüyor, katı motorda enjektör plakası çizmeye kalkıyor ve orifis planı
    çözülemediği için TÜM montajı reddediyordu (**0 STEP**, MANIFEST
    ``[FAILED] STEP solids``). Aynı sunucu, aynı gövde, zıt hüküm.

    Varsayılan sessiz bir tahmindi: gövdede motor tipi işareti YOK (ölçüldü:
    ``motor_type / engine_type / analysis_type / motor_class`` dördü de
    ``None``). Tahmin edilemeyen bir girdi UYDURULMAZ; uç artık isteğin
    kendisinden okur. Tanınmayan bir değer sessizce 'hybrid'e düşmez, ADIYLA
    reddedilir.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if not isinstance(value, str):
        return None, (f'motor_type must be one of {list(STEP_MOTOR_TYPES)}; '
                      f'received {type(value).__name__}')
    v = value.strip().lower()
    if v in STEP_MOTOR_TYPES:
        return v, None
    return None, (f'motor_type {value!r} is not a motor type this exporter '
                  f'can build: expected one of {list(STEP_MOTOR_TYPES)}. The '
                  'part set (grain / injector plate) depends on it, so no '
                  'substitute type is assumed.')


def generate_step_assembly(motor_results, out_dir=None, motor_type='hybrid'):
    """Motor bileşenlerini STEP olarak üretir; dosya yolu SÖZLÜĞÜ döner.

    motor_type: 'hybrid' (grain+enjektör), 'solid' (grain var, enjektör yok),
    'liquid' (enjektör var, grain yok).

    SÖZLEŞME (D1, v2.6.26): ``out_dir`` verilmezse her çağrı KENDİ benzersiz
    geçici dizinini alır (``mkdtemp``). Eski davranış saniye çözünürlüklü bir
    zaman damgasıydı ve ``exist_ok=True`` ile aynı saniyedeki iki istek aynı
    dizine yazıyordu. Dönen sözlüğün değerleri MUTLAK yollardır; çağıran
    dosyaları okuduktan sonra dizini silmelidir
    (``export_workspace.cleanup_workspace``).

    A8 (fail-closed): kamara/kasa cidar kalınlığı yapısal analizden
    okunamazsa ``ValueError`` yükseltilir. Eskiden ``0.045·D_ch`` yedeğine
    düşülüyordu; ölçüldü (Ø100 mm katı motor): analiz 2.40 mm, STEP 4.50 mm —
    imalata analizde hiç doğrulanmamış bir cidar gidiyordu.

    ÖH Z2 (defter P15B4-10 + P9B2-07, 27 Ağustos 2026): cidar bu kapıdan
    geçerken ÖN KAPAK sabitti — üç motor tipinde de 8,0000 mm, oysa aynı
    koşunun yapısal analizi (hibrit) kapağı 1,9948 mm hesaplıyordu (4,01x).
    Kapak da artık tek çözümleyiciden gelir ve kaynağı (analiz mi, üreteç
    varsayımı mı) parça adına yazılır. Ayrıca cidarın DOĞRULANMA durumu
    (``_chamber_wall_design``) parça adında taşınır: eskiden okunuyor ama
    hiçbir yere yazılmıyordu.

    v2.6.27 (dürüstlük kapısı, enjektör): sonuç bir enjektör bloğu taşıyor
    ama orifis sayısı/çapı çözülemiyorsa ``ValueError`` yükseltilir (eski
    davranış: 12 × Ø1,5 mm uydurma plaka — ham sıvı sonucunda motorun
    hesapladığı ``number_of_elements`` bile okunmuyordu). Sonuç enjektörden
    hiç söz etmiyorsa parça grain ilkesindeki gibi (H4-1) çizilmez. Orifis
    halka yarıçapı hiçbir çözücüde modellenmediği için desen verisi yoksa
    katı, parça adına gömülü açık ``ASSUMED`` beyanıyla çizilir (bkz.
    gövdedeki kapı notu).

    Faz 5B / H4-1 ve H4-2 (ölçüldü, HEAD 9d3728e):

    * Birim: girdi KOŞULSUZ metre kabul ediliyordu. ``/calculate_solid``
      yanıtı doğrudan verilince STEP montaj zarfı 174 992 × 98 156 mm
      çıkıyordu (gerçek 782.68 × 98.16 mm). Artık birim
      ``motor_geometry.normalise_export_geometry`` ile açıkça çözülür.
    * Grain: ``motor_type`` varsayılanı 'hybrid' olduğu ve rota katmanı bu
      argümanı hiç geçmediği için SIVI motorda da ``fuel_grain.step``
      üretiliyordu (ölçüldü: 85.22 mm boyunda, Ø30 mm portlu uydurma bir
      blok). Grain artık yalnız sonuçta gerçekten varsa üretilir.
    """
    _require()
    from hrma.export.motor_geometry import (
        _first_positive, normalise_export_geometry, resolve_grain_m)

    # ÖH V3 CAD A1: yerleşim çözücüsü (STL/DXF ile tek kaynak); grain
    # bloğu kamara katısından ÖNCE doğrulandığı için burada ithal edilir.
    from hrma.export.cad_visualization import (
        GrainLayoutError, grain_axial_layout_mm, grain_gate_message,
        grain_radial_clearance_note, grain_section_note,
        grain_section_refusals)

    md, _report = normalise_export_geometry(motor_results)
    grain_geo, _grain_reason = resolve_grain_m(md)
    # Grain iki koşulun İKİSİNİ birden ister: motor tipi grain taşıyor olmalı
    # VE çözümde gerçek grain geometrisi bulunmalı. Yedek ölçü YOK.
    has_grain = motor_type in ('hybrid', 'solid') and grain_geo is not None
    has_injector = motor_type in ('hybrid', 'liquid')
    if has_grain:
        # ÖH V3 CAD A2 · H1 — TANE KESİTİ KAPISI (karar §28-21 (c)). Bu
        # üreteç yalnız TEK DAİRESEL portu çizebilir; yıldız/finocyl/çok
        # portlu tane eskiden SESSİZCE BATES borusu olarak iniyordu (ölçüldü:
        # yıldız itici kütlesi iddia 1,951 kg, çizilen 2,407 kg, +%23,3).
        # Uç kapısı (app.py) aynı hükmü 422 + i18n ile verir; bu, uçtan
        # geçmeyen doğrudan çağrılar için ikinci kapıdır. Katı üretiminden
        # ÖNCE koşar: çalışma dizinine yarım dosya yazılmaz.
        _kesit_reddi = grain_section_refusals(motor_results)
        if _kesit_reddi:
            raise StepExportDataError(
                grain_gate_message(_kesit_reddi, 'Manufacturing STEP'),
                invalid_fields=[
                    {'field': (r.get('grain_type_field')
                               or r.get('port_count_field')),
                     'reason': r['reason'],
                     'grain_type': r.get('grain_type'),
                     'port_count': r.get('port_count')}
                    for r in _kesit_reddi])

    # Ad dosya yoluna giriyor: mutlak yol / '..' geçmesin (K-1).
    name = safe_name(md.get('motor_name'))
    if out_dir is None:
        # Çökme sonrası kalanları topla (D10), sonra kendi dizinini aç.
        purge_stale_workspaces()
        out_dir = new_workspace('hrma_step_')
    else:
        os.makedirs(out_dir, exist_ok=True)
    out_dir = os.path.abspath(out_dir)

    # ---- boyutlar (mm) — girdi yukarıda METRE'ye indirgendi ----
    L_m = md.get('chamber_length')
    D_m = md.get('chamber_diameter')
    if not (isinstance(L_m, (int, float)) and np.isfinite(L_m) and L_m > 0
            and isinstance(D_m, (int, float)) and np.isfinite(D_m) and D_m > 0):
        raise StepExportDataError(
            'chamber_length / chamber_diameter could not be resolved from the '
            'analysis result (checked motor_geometry, the declared '
            'length_units and the top-level fields); refusing to emit a '
            'manufacturing STEP built from generator defaults.',
            invalid_fields=[
                {'field': f, 'reason': 'unresolved',
                 'accepted_paths': [f, f'motor_geometry.{f}']}
                for f in ('chamber_length', 'chamber_diameter')])
    L = float(L_m) * 1000.0
    D_ch = float(D_m) * 1000.0
    rc = D_ch / 2
    if has_grain:
        # ÖH D15 / defter P9B2-12: SESSİZ KIRPMA KALDIRILDI. Zarfı aşan grain
        # artık kırpılmaz; imalat katısı üretilmez ve gerekçesi adıyla verilir.
        # (Rota katmanı aynı kuralı 422 ile uygular; bu, uçtan geçmeyen
        # doğrudan çağrılar için ikinci kapıdır.)
        L_g = grain_geo['length'] * 1000.0
        # ÖH D35 · OH-ON-04: sığma, TANENİN BOYU değil YIĞININ boyu ile
        # sınanır — çok segmentli BATES'te aralar da yer kaplar. Boşluk
        # yayımlanmadığında yığın boyu tane boyuna eşittir (bitişik yerleşim),
        # yani kapı bugünküyle BİT-AYNI davranır.
        # ÖH V3 CAD A1 · H3: plan STL ile TEK fonksiyondan
        # (``grain_stack_plan``): açık plan yoksa yayımlanan segment SAYISI
        # tane boyunu eşit böler (hibrit çözücü sayıyı yayımlar, boyu değil).
        _yigin = grain_stack_plan(md, L_g)
        grain_plan = _yigin['plan']
        # Sığma kapısı ÖNCE koşar: "kasaya hiç giriyor mu" sorusu segment
        # bölümünden daha kaba ve daha temeldir. Ölçü, yayımlanan tane boyu
        # ile yığın boyunun BÜYÜĞÜDÜR — yani kapı eskisinden gevşek olamaz.
        L_stack = _yigin['stack_mm']
        if max(L_g, L_stack) > L:
            raise StepExportDataError(
                f'the solved grain is {max(L_g, L_stack):.2f} mm long but its '
                f'chamber is only {L:.2f} mm, so the grain does not fit '
                'inside the case; '
                'refusing to emit a manufacturing STEP whose grain is '
                'silently shortened to fit. Earlier releases clamped it here '
                'without saying so while the DXF of the same request drew the '
                'full solved length - the two files described the same motor '
                f'{L_g / L:.2f}x apart.',
                invalid_fields=[{
                    'field': 'chamber_length',
                    'reason': 'shorter_than_solved_grain',
                    'submitted_mm': round(L, 4),
                    'solved_grain_length_mm': round(L_g, 4),
                    'solved_grain_stack_mm': round(L_stack, 4)}])
        if grain_plan is not None and not grain_plan.get('derived'):
            # İki sayı da aynı çözücüden gelir (``L_grain`` ve ``L_grain/n``);
            # uyuşmuyorlarsa yanıtta İKİ AYRI tane boyu var demektir ve
            # hangisinin imalata gideceği KAZANILMAMIŞTIR.
            _toplam_seg = grain_plan['n'] * grain_plan['segment_mm']
            if abs(_toplam_seg - L_g) > GRAIN_SEGMENT_LENGTH_TOLERANCE_MM:
                raise StepExportDataError(
                    f'the analysis publishes {grain_plan["n"]} grain segments '
                    f'of {grain_plan["segment_mm"]:.4g} mm '
                    f'({_toplam_seg:.4g} mm of propellant) but the same '
                    f'response reports a grain length of {L_g:.4g} mm; the '
                    'two disagree, so it is not established which length goes '
                    'to manufacturing. Refusing to emit a STEP built on a '
                    'guess.',
                    invalid_fields=[{
                        'field': 'grain_design.segment_length_mm',
                        'reason': 'inconsistent_with_grain_length_mm',
                        'number_of_segments': grain_plan['n'],
                        'segment_length_mm': round(grain_plan['segment_mm'], 4),
                        'segments_total_mm': round(_toplam_seg, 4),
                        'grain_length_mm': round(L_g, 4)}])
        # ÖH V3 CAD A1 · H3 — tanenin yeri, çözücü yayımlıyorsa ONDAN
        # (``solver_grain_front_mm``; STL ve DXF aynı fonksiyonu okur).
        # Katı üretimine BAŞLAMADAN doğrulanır: yayımlanan düzen sığmıyor ya
        # da kapanmıyorsa çalışma dizinine yarım dosya yazılmaz. HAM girdi
        # okunur: normalize kopya ön/arka oda alanlarını çevirmez.
        # ÖH V3 CAD A2 · H7 — çözücü konum yayımlamıyorsa (katı) üreteç
        # kuralı da ARTIK aynı fonksiyondan (``grain_axial_layout_mm``):
        # STL ve DXF eskiden kendi kopya kurallarıyla 1,4 mm farklı yere ve
        # segmentsiz çiziyordu.
        try:
            grain_layout = grain_axial_layout_mm(motor_results, L, L_stack)
        except GrainLayoutError as _hata:
            raise StepExportDataError(
                str(_hata), invalid_fields=_hata.invalid_fields) from _hata
        r_p0 = grain_geo['port_initial'] * 1000.0 / 2
    # Cidar TEK çözümleyiciden gelir (üç motor tipinin üç ayrı anahtar şeması
    # orada tanınır): chamber_analysis / case_analysis / chamber_structure.
    from hrma.export.cad_visualization import (
        _MONTAJ_GIRISIM_TOLERANS_MM,
        _chamber_wall_design, _front_cap_design, _grain_outer_radius_m,
        _injector_plate_design, _nozzle_wall_design, _wall_sf_basis_text,
        injector_plate_axial_span_mm)
    wall_design = _chamber_wall_design(md)
    wall_m, wall_src = wall_design['thickness_m'], wall_design['source']
    if wall_m is None:
        # ÖH D30 / OH-D29-09: kabul edilen yolların listesi ELLE
        # YAZILMAZ — cidarı çözen tablonun (``CHAMBER_WALL_SCHEMAS``)
        # kendisinden türetilir, yoksa tabloya eklenecek dördüncü bir şema
        # ret metninde görünmez ve künye sessizce bayatlardı (TEK KAYNAK).
        from hrma.export.cad_visualization import CHAMBER_WALL_SCHEMAS
        _kabul = [f'structural_analysis.{blok}.{anahtar}'
                  for blok, kullanilan, onerilen, _yetkili in
                  CHAMBER_WALL_SCHEMAS
                  for anahtar in (kullanilan, onerilen)]
        raise StepExportDataError(
            'chamber wall thickness is not available from the structural '
            'analysis (looked for chamber_analysis / case_analysis / '
            'chamber_structure); refusing to emit a manufacturing STEP with '
            'an assumed wall. Run the structural analysis first. The exact '
            'paths this export reads are listed in invalid_fields'
            '[0].accepted_paths.',
            invalid_fields=[{
                'field': _kabul[0],
                'reason': 'not_supplied',
                'accepted_paths': _kabul}])
    wall = wall_m * 1000.0
    # Grain DIŞ yarıçapı: ÇÖZÜCÜNÜN kendi çapından, mesh'le AYNI çözümleyici
    # üzerinden (TEK KAYNAK: cad_visualization._grain_outer_radius_m).
    #
    # ÖH D15 / defter P9B2-03. Eski kural ``r_go = rc - liner`` idi ve
    # ``liner = min(max(0,02.D_ch; 1,5); 5,0)`` hiçbir çözücüden gelmeyen bir
    # üreteç sabitiydi. Ölçüldü (31 Ağustos 2026, ``motor_solid`` fikstürü):
    # çözücü ``grain_design.outer_diameter_mm = 100,000`` derken üretilen
    # ``fuel_grain.step`` sınır kutusu Ø**96,000** mm — itici hacmi -%8,6,
    # web -%5,7 ve HİÇBİR çıktı bu "liner"ı beyan etmiyordu. Aynı koşunun
    # STL'i (P9B1-04 onarımından sonra) çözücünün Ø100'ünü çiziyordu: tek
    # pakette iki farklı grain. Çap artık çözücüden gelir; çözücü çapı
    # yayımlamıyorsa grain UYDURULMAZ, çizilmez ve gerekçesi adlandırılır.
    grain_r_outer_m, grain_r_outer_src = _grain_outer_radius_m(md)
    grain_not_drawn_reason = None
    if has_grain and grain_r_outer_m is None:
        has_grain = False
        grain_not_drawn_reason = (
            'fuel grain NOT modelled: ' + grain_r_outer_src
            + '; the outer diameter is NOT derived from a generator liner '
              'rule, because that silently shrank the propellant')
    # Ön kapak: cidarla AYNI ilke (P15B4-10, ÖH D21 / P9B1-17).
    #
    # D15/Z2'de kalınlık tek çözümleyiciye toplanmış ama analiz YOKKEN üreteç
    # kuralı (1,6 x cidar, taban 8 mm) çalışmaya devam ediyordu; künye
    # "ASSUMED" diyordu, imalata giden sayı yine uydurma idi. ÖLÇÜLDÜ
    # (35aa279, once.json bölüm F): aynı gövdede cidar ``None`` dönüp bu
    # üretici REDDEDERKEN kapak 8,00 mm üretiliyordu — tek dosyada iki zıt
    # hüküm. Kapak da basınç sınırının parçasıdır (gerilmesi Roark Tbl. 11.2
    # ile structural_analysis._analyze_end_caps'te hesaplanır), dolayısıyla
    # doğru davranış cidarınkiyle aynıdır: analiz yoksa sayı uydurulmaz.
    # Bunun kapısı ``_front_cap_design(require_analysis=True)`` olarak
    # yazıldı — ama aşağıdaki gerekçeyle BU ÇAĞRIYA henüz bağlanmadı.
    #
    # ÖH D21 KAPANIŞ NOTU — KAPI BU DALGADA BAĞLANMADI. ``require_analysis=True``
    # denendi ve ÖLÇÜLDÜ: katı ve sıvı motorların yapısal analizi kapak
    # kalınlığı HİÇ yayımlamadığı için (``case_analysis`` + ``grain_structural``
    # + ``assembly_integrity`` var, ``end_cap_analysis`` yok;
    # ``assembly_integrity.closure_joint.status == 'not_sized'``) imalat STEP'i
    # o iki motor tipinde tamamen kayboluyordu — dört dosyada 27 bekçi
    # kırmızıya döndü (test_faz5_cizim_birim, test_d15_ihracat_a2,
    # test_z5guard_urun_tur, test_z5guard_kunye_tutar). Kalemin GERÇEK kapanışı
    # kapağın yapısal analizde BOYUTLANDIRILMASIDIR (girdileri hazır:
    # ``chamber_pressure``, ``case_analysis.yield_strength_mpa``,
    # ``design_safety_factor``, ``case_material``; formül
    # ``structural_analysis._analyze_end_caps``, Roark Tbl. 11.2) ve orası
    # yapisal-sistem / kati / sivi sahasıdır. Kapı mekanizması
    # ``_front_cap_design(require_analysis=...)`` olarak HAZIR duruyor ve
    # bekçisi tests/test_d21_ihracat_a1.py'de; kapak analizi o kulvarlarda
    # üretilir üretilmez burada tek satırla açılır.
    cap_design = _front_cap_design(md, wall_mm=wall, bore_radius_mm=rc)
    cap = cap_design['thickness_mm']
    if cap is None:
        raise StepExportDataError(
            'closure head thickness could not be resolved; refusing to emit '
            'a manufacturing STEP with an undeclared head. Reason: '
            + str(cap_design.get('source') or 'not available'),
            invalid_fields=[{
                'field': 'structural_analysis.end_cap_analysis'
                         '.flat_head_thickness',
                'reason': 'not_supplied',
                'accepted_paths': [
                    'structural_analysis.end_cap_analysis'
                    '.flat_head_thickness',
                    'structural_analysis.end_cap_analysis'
                    '.head_thickness_used_mm'],
                'resolver_source': str(cap_design.get('source')
                                       or 'not available')}])

    # ---- Enjektör girdileri: katı üretimine BAŞLAMADAN doğrula ----
    # v2.6.27 dürüstlük kapısı: "12 delik × Ø1,5 mm" uydurma varsayılanları
    # KALDIRILDI. Ölçüldü (denetçi, 2026-08-04): enjektör verisi hiç olmayan
    # bir sonuçla bile buradan 12 delikli bir "imalat" plakası çıkıyordu;
    # ham sıvı sonucunda ise motorun GERÇEKTEN hesapladığı plan
    # (``number_of_elements`` / ``fuel_orifice_diameter_mm``) okunmayıp
    # yerine yine 12 × Ø1,5 mm uyduruluyordu. Yeni sözleşme iki hâli ayırır:
    #
    # * Sonuç bir enjektör bloğu TAŞIYOR ama plan çözülemiyor (boş blok ya da
    #   motorun ``status: not_analyzed`` beyanı) -> REDDET (A8 ilkesi).
    #   Motorun kendi sözleşmesi (hybrid_rocket_engine, v2.6.26) delik planı
    #   üretilemediğinde uydurma yedek üretmez — imalat çıktısı, motorun
    #   reddettiği planı uyduramaz.
    # * Sonuç enjektörden HİÇ söz etmiyor (ör. katı motor sonucu varsayılan
    #   'hybrid' rotasından geçti) -> parça uydurulMAZ ve çizilMEZ — grain
    #   ilkesinin (H4-1: "yalnız sonuçta gerçekten varsa üretilir") eşleniği.
    #
    # Doğrulama katı üretiminden ÖNCE yapılır ki ret hâlinde çalışma dizinine
    # yarım dosya yazılmasın.
    #
    # ÖH Z5S / defter P9B2-01 (KRİTİK): plan artık HER DEVRE için ayrı
    # çözülür. Eski kapı TEK bir (sayı, çap) çifti okuyordu ve sıvı motorda o
    # çift YAKIT devresiydi — oksitleyici plakaya %0 iniyordu.
    if has_injector:
        inj = md.get('injector_design')
        if not isinstance(inj, dict):
            inj = md.get('injector')
        if not isinstance(inj, dict):
            # ÖH D24 / P15B4-04 — ``resolve_injector_plan`` ile AYNI kaynak
            # zinciri (panel yedeği). Eskiden burası panelde kalan sonucu
            # göremediği için ``inj`` None kalıyor, aşağıdaki
            # ``inj.get('orifice_ring_radius_mm')`` ham
            # ``'NoneType' object has no attribute 'get'`` ile düşüyordu —
            # kullanıcı STEP'in NEDEN üretilmediğini okuyamıyordu.
            inj = md.get('injector_results')
        if not isinstance(inj, dict):
            inj = {}
        plan = resolve_injector_plan(md, motor_type=motor_type)
        if not plan['claimed']:
            has_injector = False  # sonuçta enjektör iddiası yok — çizilmez
    # ÖH D32 / OH-D31-16 — PLAKA KALINLIĞI KAPISI: KARDEŞ ÜRETİCİYLE AYNI
    # ÇÖZÜMLEYİCİ.
    #
    # ÖLÇÜLDÜ (taban dd1dcddc, ``once_oh_d31_16.json``): ham
    # ``/calculate_liquid`` sonucu iki katı üreticisine verildiğinde
    #     STL  -> chamber, nozzle                      (2 parça)
    #     STEP -> chamber, injector, nozzle            (3 parça)
    # iniyordu; ``/api/export-complete-zip`` ikisini karşılaştırıp paketi
    # **HTTP 422** ile reddediyordu (``only_in_step = ['injector']``). Yani
    # sıvı motorun komple tasarım paketi ÜRÜNDE HİÇ ÜRETİLEMİYORDU. Kapı
    # doğru davranıyordu; ayrışan üreticilerdi.
    #
    # Kök: ÖH D15 / defter P9B1-13 doktrini YARIM uygulanmış. Orada ölçülen
    # kusur şuydu — aynı koşuda enjektör plakası DÖRT ayrı sayıydı ve
    # üreticiler kamaranın ÖN KAPAK kalınlığını plaka yerine koyuyordu
    # (mesh/gerçek oranı 10,0x). ``cad_visualization`` o dalgada
    # ``_injector_plate_design``e bağlandı: plaka kalınlığı yayımlanmamışsa
    # plaka ÇİZİLMEZ, TARTILMAZ, ihraç edilmez. Bu modül ise bağlanmadı ve
    # ``t_inj = cap_design['flat_mm']`` ile TAM O YASAK İKAMEYİ sürdürdü
    # ("kamara kapağının kalınlığı ... enjektör plakası yerine geçemez"),
    # kapak da yoksa saf bir üreteç sabitine düşüyordu.
    #
    # İki bekçi aynı dosyada, AYNI fikstürde çelişiyordu:
    #   tests/test_export_generators.py::TestSTLQuality
    #       ::test_injector_orifices_actually_drilled  -> STL'de plaka YOK
    #   tests/test_export_generators.py::TestSTEP
    #       ::test_step_assembly_roundtrip             -> STEP'te plaka VAR
    #
    # Doktrin 1: beyan çözüm değildir — parça adına "ASSUMED plate thickness"
    # yazmak uydurma kalınlığı meşrulaştırmaz. Doktrin 4: kalınlık İKİ yerde
    # ayrı kuralla türetilmez. Kalınlık artık TEK çözümleyiciden gelir;
    # çözülemiyorsa parça çizilmez ve gerekçesi montaj adında yayımlanır
    # (çizilmeyen grain'in kanalıyla aynı).
    #
    # SIRA ÖNEMLİ: bu kapı, ORİFİS REDDİNDEN SONRA koşar. "Enjektör iddia
    # ediliyor ama delikleri çözülemiyor" hâli bir REDDİR (aşağıdaki
    # ``StepExportDataError``) ve plaka kalınlığının yokluğu onu YUTAMAZ;
    # yoksa boş/``not_analyzed`` enjektör bloğu sessizce parçasız bir pakete
    # dönüşürdü.
    plate_design = _injector_plate_design(md)
    injector_not_drawn_reason = None
    if has_injector:
        if not plan['circuits']:
            raise StepExportDataError(
                'injector orifice count / diameter could not be resolved '
                'from the analysis result (looked for injector_design / '
                'injector: number_of_orifices | n_holes | number_of_elements '
                'and orifice_diameter_mm | hole_diameter | '
                'fuel_orifice_diameter_mm, plus the per-circuit fields '
                'injector_design_detail.ox_circuit / .fuel_circuit; the '
                'injector circuit model may have reported '
                'status=not_analyzed; refusing to emit a manufacturing STEP '
                'built from generator defaults. The exact paths this export '
                'reads are listed in invalid_fields[0].accepted_paths.',
                invalid_fields=[{
                    'field': 'injector_design.number_of_orifices',
                    'reason': 'unresolved',
                    'accepted_paths': [
                        'injector_design.number_of_orifices',
                        'injector_design.n_holes',
                        'injector_design.number_of_elements',
                        'injector_design.orifice_diameter_mm',
                        'injector_design.hole_diameter',
                        'injector_design.fuel_orifice_diameter_mm',
                        'injector_design_detail.ox_circuit',
                        'injector_design_detail.fuel_circuit'],
                    'circuit_model_note': plan.get('note')}])
        # Orifisler çözüldü; sıra PLAKANIN KENDİSİNDE (yukarıdaki nota bak).
        # Kalınlık çözülemiyorsa parça çizilmez: delinecek yüzeyin kalınlığı
        # bilinmeden delik derinliği de imal edilemez.
        if plate_design['thickness_m'] is None:
            has_injector = False
            injector_not_drawn_reason = plate_design['source']
    if has_injector:
        # Halka yarıçapı: hiçbir çözücü orifis YERLEŞİMİNİ modellemez (devre
        # modeli sayı/çap/ΔP verir, radyal konum vermez). Delik sayısı/çapının
        # aksine bu "çözülemedi" değil "modellenmiyor" hâlidir; her enjektör
        # STEP'ini reddetmek imalat çıktısını tümden öldürürdü. Depodaki
        # yerleşik kalıp (safety_analysis 'ASSUMED L/D', water_hammer
        # 'ASSUMED material') izlenir: değer gerçek desen verisinden
        # gelmiyorsa katı ANCAK açık 'ASSUMED' beyanıyla çizilir ve beyan
        # STEP dosyasının içinde, parça adında taşınır (CAD ağacında görünür).
        # İLK devre eski yerinde (0,7·R) kalır: tek devre yayımlayan motorun
        # katısı böylece onarım öncesiyle BİT-AYNI çıkar.
        ring_given = _first_positive(inj.get('orifice_ring_radius_mm'))
        for index, circuit in enumerate(plan['circuits']):
            if index == 0 and ring_given is not None:
                circuit['ring_r_mm'] = float(ring_given)
                circuit['ring_assumed'] = False
                circuit['ring_fraction'] = None
            else:
                frac = INJECTOR_RING_RADIUS_FRACTIONS[
                    min(index, len(INJECTOR_RING_RADIUS_FRACTIONS) - 1)]
                circuit['ring_r_mm'] = frac * rc
                circuit['ring_assumed'] = True
                circuit['ring_fraction'] = frac

    files = {}
    solids = []

    # ---- Kamara: duvar + baş kapak (kapalı profil revolve) ----
    chamber_profile = [
        (-cap, 0.0), (-cap, rc + wall), (L, rc + wall), (L, rc),
        (0.0, rc), (0.0, 0.0),
    ]
    chamber = _revolve_profile(chamber_profile)
    # KÜNYE PARÇA ADINDA (enjektör orifis halkasındaki desenin eşleniği):
    # dosyayı açan imalatçı, çizilen cidarın DOĞRULANMIŞ mı yoksa hedefe
    # boyutlandırılmış mı olduğunu ve kapağın nereden geldiğini CAD ağacında
    # görür. Önceden bu bilgi çözümleyiciden okunuyor ama hiçbir yere
    # yazılmıyordu (``wall_src`` atanıp kullanılmıyordu) — STEP sessizdi.
    chamber_notes = [f'wall {wall:.2f} mm - {wall_src}']
    if wall_design['recommended_mm'] is not None:
        chamber_notes.append(
            f"structural sizing recommends {wall_design['recommended_mm']:.2f} mm")
    _sf = wall_design['safety_factor']
    _measured = wall_design['safety_factor_is_measured']
    if _measured is not None and _sf is not None:
        chamber_notes.append(
            f'safety factor at this wall = {_sf:.4f}'
            + ('' if _sf >= 1.0 else ' - BELOW 1.0, THE WALL FAILS')
            + ('' if _measured else ' - NOT A VERIFICATION, basis: '
               + (wall_design['safety_factor_basis']
                  or _wall_sf_basis_text(wall_design))))
    else:
        chamber_notes.append(
            'safety factor at this wall NOT PUBLISHED by this analysis; basis: '
            + (wall_design['safety_factor_basis']
               or _wall_sf_basis_text(wall_design)))
    chamber_notes.append(f"closure head {cap:.2f} mm - {cap_design['source']}")
    chamber.label = 'chamber (' + '; '.join(chamber_notes) + ')'
    files['chamber'] = os.path.join(out_dir, f'{name}_chamber.step')
    _export_step_atomic(chamber, files['chamber'])
    solids.append(chamber)

    # ---- Nozul: iç kontur + duvar ofseti (tek kontur kaynağı) ----
    # İmalat çıktısı: ıraksak boy hesaplanmadıysa katı ÜRETİLMEZ (A5).
    pts, meta = sample_nozzle_inner_contour(md, require_solved_length=True)
    # ÖH V3 CAD A1 · H2 — ET TEK KAYNAKTAN (``_nozzle_wall_design``; STL ve
    # kütle dökümü de onu okur). ÖLÇÜLDÜ (7 Eki CAD kontrolü, hibrit örnek):
    # çözücü ``nozzle_geometry.wall_thickness = 7,185 mm`` (thin_wall_hoop)
    # yayımlarken bu satır kuralı kendi içinde yeniden hesaplıyor ve 3,00 mm
    # çiziyordu; künye "NOT from a structural or thermal analysis" diyordu,
    # aynı paketteki STL lülesi 7,19 mm idi (hacim 2,53x). Et yayımlanmamışsa
    # (katı/sıvı) üreteç kuralı aynen sürer ve künyesi DEĞİŞMEDİ
    # (ÖH Z5S / P9B2-29: kuralın adı, kesri ve boğaz yedeği yazılır).
    noz_wall = _nozzle_wall_design(md)
    wall_noz = noz_wall['thickness_m'] * 1000.0
    inner = [(L + z, r) for z, r in pts]
    # ÖH V3 CAD · §28-41 — PÜRÜZSÜZ YÜZEY: aynı kontur noktaları ve aynı
    # et; çokgen (``_revolve_profile(inner + outer)``, nokta başına bir koni
    # yüzü) yerine noktalardan geçen B-spline revolve edilir.
    nozzle = _revolve_smooth_nozzle(
        inner, wall_noz, straight_tail=meta['noz_type'] == NOZZLE_TYPE_CONE,
        throat_radius_curvature_mm=meta['throat_radius_curvature_mm'],
        unreadable_angle_fields=meta['unreadable_angle_fields'])
    if noz_wall['published']:
        noz_notes = [f"wall {wall_noz:.2f} mm - {noz_wall['source']}"]
    else:
        noz_notes = [
            f'wall {wall_noz:.2f} mm - ASSUMED generator rule '
            f'max({NOZZLE_WALL_MIN_MM:.2f} mm, '
            f'{NOZZLE_WALL_THROAT_FRACTION:g} x throat diameter); NOT from a '
            'structural or thermal analysis of the nozzle',
        ]
        if not noz_wall['throat_resolved']:
            noz_notes.append(
                'throat diameter could not be resolved from this result, so '
                'the generator fallback '
                f'{NOZZLE_WALL_THROAT_FALLBACK_M * 1000:.2f} mm was used in '
                'that rule')
    # Etiket ihraçtan ÖNCE atanır (P9B2-05): sonra atanınca tek parça
    # dosyasına COMPOUND yazılıyordu.
    nozzle.label = 'nozzle (' + '; '.join(noz_notes) + ')'
    files['nozzle'] = os.path.join(out_dir, f'{name}_nozzle.step')
    _export_step_atomic(nozzle, files['nozzle'])
    solids.append(nozzle)

    # ---- Yakıt grain'i: portlu halka silindir ----
    if has_grain:
        r_go = grain_r_outer_m * 1000.0
        if r_go > rc:
            raise StepExportDataError(
                f'the solved grain outer diameter is {2 * r_go:.2f} mm but '
                f'the chamber bore is only {2 * rc:.2f} mm, so the grain '
                'cannot be loaded into its own case; refusing to emit a '
                'manufacturing STEP for a grain that does not fit '
                f'(source: {grain_r_outer_src}).',
                invalid_fields=[{
                    'field': 'chamber_diameter',
                    'reason': 'smaller_than_solved_grain_outer_diameter',
                    'submitted_bore_mm': round(2 * rc, 4),
                    'solved_grain_outer_diameter_mm': round(2 * r_go, 4),
                    'grain_outer_diameter_source': str(grain_r_outer_src)}])
        # ÖH Z5S / defter P9B2-22: eksenel konum bir ÜRETEÇ YERLEŞİM
        # kuralıdır, hiçbir çözücüden gelmez. Sayı değişmedi; adı, kuralı ve
        # sonucu (mm) artık parça adında beyan edilir.
        #
        # ÖH D15 / P9B2-12 eki: kırpma kalktığı için grain kamaranın SONUNU
        # aşabilir (``L - L_g`` küçükken asgari boşluk kuralı ısırır). Bu bir
        # KONUM sorunudur, boy sorunu değil: parça geriye kaydırılır (konum
        # zaten ASSUMED olarak beyanlı), boy DEĞİŞMEZ.
        #
        # ÖH V3 CAD A1 · H3: yukarıdaki "hiçbir çözücüden gelmez" cümlesi
        # hibritte YANLIŞTI (çözücü ``pre_chamber_length`` yayımlıyor). Kural
        # artık yalnız çözücü konum YAYIMLAMIYORSA çalışır ve künyesi o
        # durumu anlatır.
        zg0 = grain_layout['front_mm']
        _yerlesim = grain_layout['note']
        # ÖH V3 CAD A2 · H6 — astar/yalıtım ÇİZİLMEZ; radyal pay ölçülüp
        # beyan edilir, yanıt bir astar iddia ediyorsa sığıp sığmadığı da.
        _yerlesim += ('; ' + grain_radial_clearance_note(motor_results, rc, r_go)
                      + '; ' + grain_section_note(motor_results))

        def _segment_kati(z0, boy):
            """Tek halka silindir: [z0, z0+boy] aralığında, portu delinmiş."""
            with BuildPart() as _bp:
                with Locations((z0 + boy / 2, 0, 0)):
                    Cylinder(radius=r_go, height=boy, rotation=(0, 90, 0))
                    Cylinder(radius=max(r_p0, 1.0), height=boy + 2,
                             rotation=(0, 90, 0), mode=Mode.SUBTRACT)
            return _bp.part

        if grain_plan is not None and grain_plan['n'] > 1:
            # ÖH D35 · OH-ON-04: her segment KENDİ katısıdır. Ölçüldü ki tek
            # parça boru, analizin altı uç cephesinden gelen nötr eğrisini
            # (Kn 145,6 -> 148,4) yalanlıyordu: ihraç edilen tanede yalnız
            # 2 uç yüzey vardı. Segment sayısı ve boyu çözücüden gelir;
            # uydurulmaz (bkz. _grain_segment_plan).
            _n = grain_plan['n']
            _seg = grain_plan['segment_mm']
            _gap = grain_plan['gap_mm']
            _parcalar = []
            for _i in range(_n):
                _p = _segment_kati(zg0 + _i * (_seg + _gap), _seg)
                _p.label = (f'fuel_grain_segment_{_i + 1}_of_{_n} '
                            f'(length {_seg:.2f} mm, outer diameter '
                            f'{2 * r_go:.2f} mm from {grain_r_outer_src})')
                _parcalar.append(_p)
            grain = Compound(children=_parcalar)
            # Türetilmiş plan (hibrit: yalnız sayı yayımlı) BATES DEĞİLDİR;
            # künye segmentlerin neden eşit olduğunu ``source``ta söyler.
            _tur = ('grain segments' if grain_plan.get('derived')
                    else 'BATES segments')
            grain.label = (
                f'fuel_grain ({_n} separate {_tur} of {_seg:.2f} mm, '
                + (f'inter-segment gap {_gap:.2f} mm, '
                   if grain_plan['gap_published'] else '')
                + f'stack length {grain_plan["stack_mm"]:.2f} mm, '
                + f'{2 * _n} end faces; source: {grain_plan["source"]}; '
                + f'outer diameter {2 * r_go:.2f} mm from '
                + f'{grain_r_outer_src}; {_yerlesim})')
        else:
            grain = _segment_kati(zg0, L_g)
            _neden = (grain_plan['source'] if grain_plan is not None else
                      'the analysis does not publish '
                      'grain_design.number_of_segments / segment_length_mm, '
                      'so the number of grain segments is NOT established and '
                      'the grain is modelled as a single piece')
            grain.label = (
                f'fuel_grain (single piece, 2 end faces; {_neden}; '
                f'outer diameter {2 * r_go:.2f} mm from '
                f'{grain_r_outer_src}; {_yerlesim})')
        files['fuel_grain'] = os.path.join(out_dir, f'{name}_fuel_grain.step')
        _export_step_atomic(grain, files['fuel_grain'])
        solids.append(grain)

    # ---- Enjektör plakası: gerçek orifis delikleri ----
    # Delik sayısı/çapı yukarıdaki kapıdan gelir (çözülemediyse buraya hiç
    # ulaşılmaz); halka yarıçapı desen verisi yoksa 'ASSUMED' beyanıyla çizilir.
    if has_injector:
        # Plaka kalınlığı: KARDEŞ ÜRETİCİYLE TEK ÇÖZÜMLEYİCİ
        # (``cad_visualization._injector_plate_design``, ÖH D15 / P9B1-13).
        # Buraya ancak kalınlık ÇÖZÜLDÜYSE ulaşılır; yukarıdaki kapı
        # çözülemeyen koşuda parçayı hiç çizmez. Kamaranın ön kapak
        # kalınlığı (``cap_design['flat_mm']``) plaka yerine GEÇMEZ.
        t_inj = plate_design['thickness_m'] * 1000.0
        # ÖH V3 CAD A1 · H8 — EKSENEL YER, STL İLE TEK KURAL
        # (``injector_plate_axial_span_mm``): plaka kapak iç yüzüne oturur.
        # Eski 4,0 mm'lik "montaj boşluğu" (``INJECTOR_PLATE_AXIAL_OFFSET_MM``)
        # hiçbir çözücüden gelmiyordu ve STEP'i aynı paketteki STL'den 4 mm
        # kaydırıyordu (ölçüldü: STEP x = 4-7, STL x = 0-3 mm); kaldırıldı.
        inj_x0, inj_x1, inj_yerlesim = injector_plate_axial_span_mm(t_inj)
        # Plaka artık üreteç kelepçesiyle (<= 24 mm) sınırlı olmadığı için
        # kamaraya SIĞDIĞI açıkça denetlenir. Sığmıyorsa katı sessizce
        # lüleden dışarı taşardı; ölçü uydurmak yerine reddedilir (A8 ilkesi).
        if inj_x1 > L:
            raise StepExportDataError(
                f'the injector plate resolved to {t_inj:.2f} mm '
                f'({"structural end-cap analysis" if cap_design["flat_mm"] else "generator rule"}) '
                f'but the chamber is only {L:.2f} mm long, so the plate would '
                'not fit inside it; refusing to emit a manufacturing STEP '
                'with a plate that pierces the chamber.',
                invalid_fields=[{
                    'field': 'chamber_length',
                    'reason': 'shorter_than_injector_plate',
                    'submitted_mm': round(L, 4),
                    'plate_thickness_mm': round(t_inj, 4),
                    'plate_seat_x_mm': inj_x0}])
        # Taneyle girişim: STL üreticisinin kapısıyla AYNI hüküm
        # (``injector_plate_intersects_fuel_grain``) — iç içe geçmiş iki
        # parça imal edilemez, beyanla da yayımlanmaz.
        if has_grain and inj_x1 - zg0 > _MONTAJ_GIRISIM_TOLERANS_MM:
            raise StepExportDataError(
                f'the injector plate ends at x = {inj_x1:.2f} mm but the fuel '
                f'grain starts at x = {zg0:.2f} mm, so the two solids overlap '
                f'by {inj_x1 - zg0:.2f} mm; no assembly is exported with '
                'interpenetrating parts.',
                invalid_fields=[{
                    'field': 'injector_results.plate_structural'
                             '.plate_thickness_mm',
                    'reason': 'injector_plate_intersects_fuel_grain',
                    'plate_end_mm': round(inj_x1, 4),
                    'grain_front_mm': round(zg0, 4)}])
        clamped = []
        with BuildPart() as inj_bp:
            with Locations((inj_x0 + t_inj / 2, 0, 0)):
                Cylinder(radius=rc - 0.5, height=t_inj, rotation=(0, 90, 0))
            # HER DEVRE kendi halkasına delinir (P9B2-01). Tek devreli
            # sonuçta döngü tam olarak eski tek-halka davranışını üretir.
            for circuit in plan['circuits']:
                ring_r = float(circuit['ring_r_mm'])
                k = max(int(circuit['n']), 1)
                r_hole = max(circuit['d_mm'] / 2, INJECTOR_MIN_HOLE_RADIUS_MM)
                if r_hole > circuit['d_mm'] / 2:
                    clamped.append(circuit['name'])
                for i in range(k):
                    a = 2 * np.pi * i / k
                    with Locations((inj_x0 + t_inj / 2,
                                    ring_r * np.cos(a),
                                   ring_r * np.sin(a))):
                        Cylinder(radius=r_hole, height=t_inj + 2,
                                 rotation=(0, 90, 0), mode=Mode.SUBTRACT)
        injector = inj_bp.part
        files['injector'] = os.path.join(out_dir, f'{name}_injector.step')
        # Beyan parça ADINDA taşınır: STEP dosyasına ve CAD ağacına gömülür,
        # dosyayı açan imalatçı varsayımı görmeden deliği konumlandıramaz.
        inj_notes = []
        for circuit in plan['circuits']:
            note = (f"{circuit['name']} circuit: {circuit['n']} x "
                    f"d{circuit['d_mm']:.2f} mm "
                    f"[{circuit['count_field']}, {circuit['diameter_field']}]")
            if circuit['ring_assumed']:
                note += (' - orifice ring radius ASSUMED '
                         f"{circuit['ring_fraction']:g}*R_chamber "
                         f"({circuit['ring_r_mm']:.2f} mm), not from pattern "
                         'analysis')
            else:
                note += (' - orifice ring radius '
                         f"{circuit['ring_r_mm']:.2f} mm from "
                         'injector_design.orifice_ring_radius_mm')
            inj_notes.append(note)
        # ÇİZİLMEYEN devreler de adıyla yazılır: imalatçı, plakada olmayan
        # devreyi ancak burada görebilir (P9B2-01'in kapanış şartı).
        inj_notes.extend(plan['missing'])
        if clamped:
            inj_notes.append(
                'orifice diameter CLAMPED UP to the generator minimum '
                f'{2 * INJECTOR_MIN_HOLE_RADIUS_MM:.2f} mm on: '
                + ', '.join(clamped)
                + ' - the drilled hole is LARGER than the solved orifice')
        # Künye artık GERÇEĞİ söyler: kalınlığın hangi çözücüden geldiği.
        # "ASSUMED plate thickness" dalı kalktı — uydurulan kalınlık beyan
        # edilmez, ÜRETİLMEZ (ÖH D32 / OH-D31-16).
        inj_notes.append(f'plate {t_inj:.2f} mm - {plate_design["source"]}')
        inj_notes.append(inj_yerlesim)
        injector.label = 'injector (' + '; '.join(inj_notes) + ')'
        _export_step_atomic(injector, files['injector'])
        solids.append(injector)

    # ---- Assembly (tek dosya) ----
    # Parça adları CAD ağacında görünsün (SolidWorks/Fusion 'COMPOUND ×5' sorunu)
    # ÖH Z5S / defter P9B2-28: eksen sözleşmesi montaj adında taşınır. Aynı
    # paketteki STL mesh'leri +Z ekseninde kurulu; iki dosya birlikte
    # açıldığında motor 90° dönük görünüyor ve hiçbir künye bunu söylemiyordu.
    asm_notes = [STEP_AXIS_NOTE]
    # ÇİZİLMEYEN grain montaj adında da söylenir: paketi açan imalatçı, eksik
    # parçanın gerekçesini ancak burada görebilir (enjektör devrelerindeki
    # 'NOT drilled' beyanının eşleniği).
    if grain_not_drawn_reason:
        asm_notes.append(grain_not_drawn_reason)
    # ÖH D32 / OH-D31-16: çizilmeyen ENJEKTÖR de aynı kanaldan söylenir.
    # Paketi açan imalatçı, plakanın neden yokluğunu ancak burada görür;
    # sessiz eksilme, uydurma plakadan daha iyi değildir.
    if injector_not_drawn_reason:
        asm_notes.append('injector plate NOT modelled: '
                         + injector_not_drawn_reason)
    # ÖH A2 sivi-sogutma · F-18a (CW-L4a): rejeneratif kanallar STEP'te
    # ÇİZİLMİYOR (oda parçası düz cidar) ve bu hiçbir yerde söylenmiyordu;
    # enjektör için 'NOT modelled' beyanı vardı, kanal için yoktu. Analiz
    # kanal yayımlıyorsa beyan montaj adında sayısıyla durur (sayı çözücünün
    # kanal sayısıdır — F-17 tek sığma ölçütü; ikinci kez hesaplanmaz).
    kanal_notu = _cooling_channel_note(md)
    if kanal_notu:
        asm_notes.append(kanal_notu)
    asm_notes.append(_assembly_length_note(
        md, assembly_solids=solids, cap=cap,
        convergent_mm=(meta or {}).get('z_throat')))
    assembly = Compound(children=solids,
                        label='HRMA_motor_assembly (' + '; '.join(asm_notes)
                              + ')')
    files['assembly'] = os.path.join(out_dir, f'{name}_assembly.step')
    _export_step_atomic(assembly, files['assembly'])

    return files


def _cooling_channel_note(md):
    """Kanal beyanı: ``cooling_channels: NOT_MODELLED (n=N, w=…, h=…)``.

    ÖH A2 sivi-sogutma · F-18a. Okunan alanlar çözücünün soğutma bloğudur
    (``cooling_system.cooling_channels / channel_width_mm /
    channel_height_mm``); kanal sayısı yayımlanmamışsa (ya da 0 ise: ceket
    yok) beyan ÜRETİLMEZ — olmayan kanal için beyan da uydurma olurdu.
    Genişlik/derinlik yayımlanmamışsa o parça ``?`` değil ADIYLA
    'not published' yazılır.
    """
    cs = md.get('cooling_system') if isinstance(md, dict) else None
    if not isinstance(cs, dict):
        return None
    n = _first_positive_local(cs.get('cooling_channels'))
    if n is None:
        return None

    def _mm(alan):
        v = _first_positive_local(cs.get(alan))
        return (f'{v:.2f} mm' if v is not None
                else f'not published ({alan})')

    return (f'cooling_channels: NOT_MODELLED (n={int(round(n))}, '
            f'w={_mm("channel_width_mm")}, h={_mm("channel_height_mm")}) - '
            'the regenerative channels are analysis only; the chamber solid '
            'in this STEP is a plain wall without slots')


#: ÖH V3 CAD A2 · U4 — montaj boyu uzlaştırmasının okuduğu YAYIMLANMIŞ boy
#: alanları (``design_summary.key_dimensions``), öncelik sırasıyla. ÖLÇÜLDÜ
#: (7 Eki CAD kontrolü U4): eski kontrol yalnız ``overall_length_mm`` /
#: ``total_length_mm`` arıyordu; hibrit çözücü ``total_motor_length_*``
#: yayımladığı için kontrol hibritte HİÇ koşmuyordu ve künye "this run
#: publishes no ... overall_length_mm to reconcile it against" diyordu —
#: yayımlanan bir alan için yanlış cümle. Alanların hepsi çözücülerin kendi
#: beyanına göre ÖN KAPAĞI SAYMAZ (sıvı ``overall_length_basis``, hibrit
#: ``total_motor_length_basis``, katı ``total_length_mm`` = kasa boyu + lüle);
#: imalat STEP'i kapağı x < 0'da çizer.
ASSEMBLY_LENGTH_FIELDS = (
    'overall_length_mm',                       # sıvı
    'total_motor_length_chamber_nozzle_mm',    # hibrit (açık ad)
    'total_motor_length_mm',                   # hibrit (eski ad, aynı sayı)
    'total_length_mm',                         # katı
)
#: Analizin KENDİ kapağıyla yayımladığı boy alanları (yalnız bilgi satırı).
ASSEMBLY_LENGTH_WITH_CLOSURE_FIELDS = (
    'overall_length_with_closure_mm',          # sıvı
    'total_motor_length_with_caps_mm',         # hibrit
)
#: Uzlaştırma toleransı: |açıklanamayan fark| ≤ max(mutlak, bağıl x boy).
#: 7 Eki CAD kontrolünün ÖNCEDEN yazılmış uzunluk toleransıyla AYNI
#: (``06_iddia_karsilastir.py``: max(0,5 mm; %0,5)); aşılırsa künye
#: "LENGTH MISMATCH" uyarısını basar.
ASSEMBLY_LENGTH_TOLERANCE_ABS_MM = 0.5
ASSEMBLY_LENGTH_TOLERANCE_REL = 0.005


def _assembly_length_note(md, assembly_solids, cap, convergent_mm=None):
    """Montajın ÖLÇÜLEN boyu ile yayımlanan boyu uzlaştıran künye.

    ÖH D15 (defter P9B2-24 / -04). Ölçüldü (31 Ağustos 2026, P09 fikstürleri):

    ========  =======================  ====================  ========
    motor     yayımlanan (arayüz)      indirilen STEP montaj  fark
    ========  =======================  ====================  ========
    sıvı      578,846 mm               **613,492 mm**        +34,646
    katı      552,935 mm               **561,855 mm**         +8,920
    ========  =======================  ====================  ========

    Kullanıcı roket gövdesini yayımlanan boya göre boyutlandırıp daha uzun bir
    katı indiriyordu ve iki sayı hiçbir yerde uzlaştırılmıyordu. Uzlaştırma
    montaj parçasının ADINDA (CAD ağacında görünür) taşınır.

    ÖH V3 CAD A2 · U4 — kontrol artık DOĞRU alanları okur
    (``ASSEMBLY_LENGTH_FIELDS``) ve farkı ÖLÇÜLEN parçalarla AÇIKLAR: önce
    çizilen kapak (yayımlanan boyların hiçbiri onu saymaz); kalan fark
    çizilen yakınsak koniye eşitse (eski P09 sözleşmesi) o da adlandırılır.
    Açıklanamayan fark toleransı aşarsa künye ``LENGTH MISMATCH`` uyarısını
    basar (fail-closed: uzlaşmamış iki sayı uzlaşmış gibi sunulmaz). Hiçbir
    alan yayımlanmamışsa uzlaştırma YAPILMADIĞI söylenir.
    """
    try:
        bb = Compound(children=list(assembly_solids)).bounding_box()
        measured = float(bb.max.X - bb.min.X)
    except Exception:
        return ('overall length of this assembly could not be measured from '
                'the solids')
    note = f'as-built overall length {measured:.2f} mm (measured on the solids'
    if cap is not None:
        note += f', includes the {cap:.2f} mm closure head at x < 0'
    note += ')'
    kd = ((md.get('design_summary') or {}).get('key_dimensions') or {})
    published = None
    for key in ASSEMBLY_LENGTH_FIELDS:
        value = _first_positive_local(kd.get(key))
        if value is not None:
            published, published_key = value, key
            break
    if published is None:
        return note + ('; LENGTH NOT RECONCILED: this export body carries no '
                       'published overall length (design_summary.'
                       'key_dimensions.' + ' / '.join(ASSEMBLY_LENGTH_FIELDS)
                       + '), so the as-built length is not checked against '
                       'the analysis')
    delta = measured - published
    note += (f'; the analysis publishes {published_key} = {published:.2f} mm, '
             f'a difference of {delta:+.2f} mm ({delta / published * 100:+.2f}'
             ' %)')
    tol = max(ASSEMBLY_LENGTH_TOLERANCE_ABS_MM,
              ASSEMBLY_LENGTH_TOLERANCE_REL * published)
    cap_mm = float(cap) if cap else 0.0
    conv = (float(convergent_mm) if convergent_mm is not None
            and _first_positive_local(convergent_mm) is not None else None)
    parts = []
    if cap_mm:
        parts.append(f'closure head {cap_mm:.2f} mm')
    residual = delta - cap_mm
    if abs(residual) > tol and conv is not None and abs(residual - conv) <= tol:
        parts.append(f'convergent cone {conv:.2f} mm')
        residual -= conv
    if parts:
        note += ('. The published length does not include: '
                 + ', '.join(parts))
    if abs(residual) <= tol:
        note += (f'; reconciled, unexplained remainder {residual:+.2f} mm '
                 f'(tolerance {tol:.2f} mm = max('
                 f'{ASSEMBLY_LENGTH_TOLERANCE_ABS_MM:g} mm, '
                 f'{ASSEMBLY_LENGTH_TOLERANCE_REL * 100:g} %))')
    else:
        note += (f'; ** LENGTH MISMATCH: {residual:+.2f} mm of the difference '
                 'is NOT explained by the drawn closure head or convergent '
                 f'cone (tolerance {tol:.2f} mm); the exported assembly and '
                 'the published length describe different motors - check '
                 'before sizing the airframe **')
    for key in ASSEMBLY_LENGTH_WITH_CLOSURE_FIELDS:
        value = _first_positive_local(kd.get(key))
        if value is None:
            continue
        own = _first_positive_local(kd.get('forward_closure_length_mm'))
        note += (f'. The analysis also publishes {key} = {value:.2f} mm'
                 + (f' with its own forward closure of {own:.2f} mm '
                    '(forward_closure_length_mm)' if own is not None else '')
                 + f'; the as-built assembly differs from it by '
                 f'{measured - value:+.2f} mm')
        if own is not None and cap_mm and abs(own - cap_mm) > tol:
            note += (f' because the drawn flat closure head is {cap_mm:.2f} mm '
                     f'and the analysis closure is {own:.2f} mm (see the '
                     'chamber part name)')
        break
    return note


def _first_positive_local(value):
    """Tek değerli sonlu-pozitif kapısı.

    ``motor_geometry._first_positive`` ile AYNI kararı verir, çünkü ikisi de
    aynı merkezî kapıyı çağırır (``input_guard.first_finite_positive``,
    ÖH D28 / OH-D27-11); eskiden bağ komşu modüle zincirlenerek kuruluyordu.
    """
    return first_finite_positive(value)


# Tank STEP zarfı: bu sınırların dışındaki ölçü bir birim hatasının işaretidir,
# geçerli bir tasarım değil. Sessizce devam etmek yerine hata verilir.
_TANK_MIN_MM, _TANK_MAX_MM = 10.0, 10_000.0


def generate_tank_step(tank_data, out_dir=None):
    """Sıvı motor tankları için gerçek STEP (düz uçlu silindir kabuk).

    ÖH V3 CAD A2 · H4: başlıklar eskiden yarıküreydi; artık boyutlandırma
    modelinin düz uçlu silindiri çizilir (bkz. gövdedeki not).

    BİRİM SÖZLEŞMESİ: ``diameter`` ve ``length`` **milimetre** cinsindendir —
    modülün geri kalanı ve üretilen AP214 dosyası da mm kullanır.

    v2.6.2 düzeltmesi (1000× birim hatası):
    Bu fonksiyon girdiyi METRE varsayıp 1000 ile çarpıyordu. Fakat çağıran
    adaptör (``cad_export.generate_tank_cad``) sıvı motorun ürettiği
    ``dimensions.diameter`` değerini geçiriyor ve o değer ZATEN mm.
    Sonuç: 300 mm'lik bir tank 300.000 mm = **300 metre** olarak kuruluyordu.
    Hata yalnız varsayılan yolda görünmüyordu, çünkü varsayılan 0.3 metre
    cinsindendi ve ×1000 ile doğru 300 mm'yi veriyordu — yani veri geldiğinde
    bozuluyor, gelmediğinde doğru çalışıyordu.

    Daha kötüsü: OpenCascade 300 metrelik silindir + küre birleşimini kuramayıp
    SESSİZCE boş bir katı döndürüyordu. İstisna fırlamadığı için
    ``cad_export`` içindeki "STEP_NOT_AVAILABLE" emniyet yolu hiç tetiklenmiyor,
    kullanıcı geçerli görünen ama içi tamamen boş bir STEP dosyası indiriyordu.
    Bu yüzden aşağıda hem zarf denetimi hem de üretilen katının boş olmadığı
    kontrolü var.
    """
    _require()

    # D1: saniye çözünürlüklü zaman damgası yerine istek başına benzersiz dizin.
    if out_dir is None:
        purge_stale_workspaces()
        out_dir = new_workspace('hrma_tank_step_')
    else:
        os.makedirs(out_dir, exist_ok=True)
    out_dir = os.path.abspath(out_dir)

    files = {}
    for key in ('fuel_tank', 'oxidizer_tank'):
        td = (tank_data or {}).get(key) or {}
        # Girdi ZATEN mm — burada ölçek dönüşümü YOK (bkz. docstring).
        # v2.6.27 dürüstlük kapısı: 300 / 800 mm uydurma varsayılanları
        # KALDIRILDI. Ölçüldü (denetçi, 2026-08-04): ``generate_tank_step({})``
        # hiç veri olmadan iki eksiksiz "imalat" tankı üretiyordu — Ø300 mm,
        # 800 mm gövde, tamamı üreteç varsayımı. Kamara kolundaki ilke burada
        # da geçerlidir: ölçü çözülemiyorsa STEP ÜRETİLMEZ.
        D = _num(td.get('diameter'), None)
        Lc = _num(td.get('length'), None)
        if D is None or Lc is None or D <= 0.0 or Lc <= 0.0:
            raise StepExportDataError(
                f'{key}.diameter / {key}.length could not be resolved from '
                'the tank analysis result; refusing to emit a manufacturing '
                'STEP built from generator defaults. Run the tank sizing '
                'analysis first.',
                invalid_fields=[{'field': f'{key}.{alan}',
                                 'reason': 'unresolved'}
                                for alan in ('diameter', 'length')])
        for label, val in (('diameter', D), ('length', Lc)):
            if not (_TANK_MIN_MM <= val <= _TANK_MAX_MM):
                raise StepExportDataError(
                    f'{key}.{label} = {val:g} mm is outside the physical '
                    f'envelope [{_TANK_MIN_MM:g}, {_TANK_MAX_MM:g}] mm. '
                    'This usually means the value was supplied in metres '
                    'instead of millimetres.',
                    invalid_fields=[{
                        'field': f'{key}.{label}', 'reason': 'out_of_range',
                        'submitted_mm': val,
                        'accepted_range_mm': [_TANK_MIN_MM, _TANK_MAX_MM]}])
        # ---- Cidar: OYULUR, çünkü tank bir KABUKTUR ----
        # ÖH D15 / defter P9B2-15. Kusur: ``wall_thickness`` geometriye HİÇ
        # girmiyordu; üretilen katı içi DOLU bir alüminyum kütüktü. Ölçüldü
        # (31 Ağustos 2026, 10 kN RP1/LOX oksitleyici tankı, Ø743,7556 mm,
        # gövde 1859,3891 mm, Al 2024-T3 @ 2780 kg/m3):
        #   çizilen katı hacmi 1 023 252 929 mm3 -> **2844,64 kg**
        #   aynı pakette yayımlanan tank kütlesi   ->   **47,62 kg**  (59,7x)
        # Üstelik paketin kendi ``*_geometry.json``ı oymayı AÇIKÇA tarif
        # ediyordu (``step3_boolean_cut: "Hollow tank shell"``): paket, kendi
        # STEP'inin yapmadığı işi talimat olarak veriyordu.
        t = _num(td.get('wall_thickness'), None)
        if t is None or t <= 0.0:
            raise StepExportDataError(
                f'{key}.wall_thickness could not be resolved from the tank '
                'analysis result; refusing to emit a manufacturing STEP as a '
                'SOLID BILLET. A tank is a shell: without a wall thickness '
                'the exported solid would weigh about 60x the published tank '
                'mass. Run the tank sizing analysis first.',
                invalid_fields=[{'field': f'{key}.wall_thickness',
                                 'reason': 'unresolved'}])
        r = D / 2
        if t >= r:
            raise StepExportDataError(
                f'{key}.wall_thickness = {t:g} mm is not smaller than the '
                f'tank radius {r:g} mm, so the shell has no bore; refusing '
                'to emit a manufacturing STEP for a tank that cannot hold '
                'propellant.',
                invalid_fields=[{
                    'field': f'{key}.wall_thickness',
                    'reason': 'not_smaller_than_tank_radius',
                    'submitted_mm': t, 'tank_radius_mm': r}])
        # ÖH V3 CAD A2 · H4 (karar §28-21 (b)) — BOYUTLANDIRMANIN MODELİ.
        # ÖLÇÜLDÜ (7 Eki CAD kontrolü): bu katı silindire iki TAM küre
        # ekliyordu (yarıküre başlık) ve iç hacmi iddianın 1,225x / 1,231x'i
        # idi; boyutlandırma ise tankı DÜZ UÇLU silindir sayar
        # (``dimensions.volume = π·D²·L/4``, basınçlı kap analizi
        # ``inner_diameter_mm = D``). Geometri artık tek kaynaktan
        # (``cad_visualization.tank_shell_geometry_mm``; STL aynı profili
        # döndürür): boşluk Ø D x L, cidar t DIŞARI eklenir (gövde + iki düz
        # kapak). Yayımlanan hacim verilmişse boşluk onunla sınanır
        # (fail-closed). Yarıküre başlık bu kulvarın işi DEĞİLDİR.
        from hrma.export.cad_visualization import tank_shell_geometry_mm
        try:
            geo = tank_shell_geometry_mm(
                key, D, Lc, t, volume_l=td.get('volume'),
                analysed_head_type=td.get('analysed_head_type'))
        except ValueError as hata:
            raise StepExportDataError(
                str(hata), invalid_fields=[{
                    'field': f'{key}.volume',
                    'reason': 'cavity_does_not_match_published_volume',
                    'submitted': td.get('volume')}]) from hata
        part = _revolve_profile(geo['profile_xr'])
        # Cidarın ve başlık beyanının nereden geldiği CAD ağacında görünür
        # (kamara kolundaki ``chamber (wall ... - ...)`` deseninin eşleniği).
        part.label = geo['label']
        files[key] = os.path.join(out_dir, f'{key}.step')
        _export_step_atomic(part, files[key])
    return files
