"""Mühendislik CAD montaj planı (CM-0) — motor tipi başına TEK geometri kaynağı.

ÖH D37 A2 cm-0-plan. Tasarım: ``docs/tasarim/cad-montaj/B1_tasarim.md``
(§1 montaj ağacı, §2.1 STEP ağacı, §3 ``cad_assembly`` v1 şeması, §4 fizik
kalemleri, §6 kararlar).

NEDEN VAR
---------
Bugün STEP (``step_export``), STL (``cad_visualization``), DXF
(``drawing_generator``) ve 3B sahne (``motor_viz3d.js``) dört AYRI geometri
kuruyor; ortak olan yalnız kamara kabı, ince kabuk lüle ve tane (B1 §0).
Bu modül motor sonucundan adlı, gruplu, ölçüsü ölçü ölçü künyeli bir parça
listesi üretir; sonraki kademeler (CM-1 STEP, CM-2 STL/DXF/uç, CM-3 sahne)
yalnız bu planı okur, kendi ölçü türetmez.

DOKTRİN (değişmez)
------------------
* Her ölçü ya çözücünün/kullanıcının YAYIMLADIĞI yanıt alanından gelir
  (``solver`` / ``user`` — değer alanın kendisidir; metre alanlarda tek
  çarpma ``x 1000``) ya da ``ASSUMED_RULES`` tablosunda ADI olan bir
  yerleşim/şekil kuralından (``assumed``). Uydurma ölçü sessizce girmez.
* **Karar 1 (B1 §6, öneri uygulanır — itirazda geri):** basınç sınırı
  kalınlıkları (cidar, kapak, plaka, flanş, tutucu, boğaz eki, ceket)
  ASSUMED ÇİZİLMEZ; hesap yoksa parça ``new_calc_required`` ile
  ``not_modelled`` listesine girer. TEK istisna ADIYLA: katı/sıvı lüle
  eti üreteç kuralı (``NOZZLE_WALL_GENERATOR_RULE``) — bugünkü STEP onu
  çiziyor, F-CAD-5 gelene kadar kaldırılmaz (geri gitmemek için, B1 §4).
* ``0,0 = yayımlanmadı``: alanın kaynak künyesi (``*_source``) yoksa sıfır
  bir ölçü sayılmaz (``pre_chamber_length = 0.0`` SOLVER DEĞİLDİR). Künye
  yayımlıysa değer ona göre okunur (``grain_gap_source='user_input'`` 0,0
  = kullanıcının gerçek sıfırı; ``step_export._grain_gap_reading``).
* **Girişim kapısı fail-closed-ama-dosya:** iki parçanın r–z kesitleri
  ``_MONTAJ_GIRISIM_TOLERANS_MM``den derin örtüşürse DÜŞÜK öncelikli parça
  (eşit öncelikte İKİSİ) çizilmez ve gerekçesi ``not_modelled`` listesine
  yazılır. Plan asla 422 üretmez; ret kararı tüketicinin (CM-1'in mevcut
  kapıları) işidir.
* Girişim/temas denetimi OCC'siz, SAF geometridir: eksenel simetrik iki
  katı ancak ve ancak (x, r) yarı düzlemindeki kesitleri örtüşürse
  kesişir; kesitler dışbükey hücrelere bölünüp Sutherland–Hodgman ile
  kırpılır.

EKSEN
-----
+X, x = 0 enjektör yüzü (katıda ön kapak iç yüzü) —
``motor_geometry.EXPORT_AXIS_NOTE`` tek kaynaktır. Kapak ``x ∈ [-t_k, 0]``,
kasa borusu ``[0, L]``. Enjektörlü motorda plakanın eksenel yeri CAD
kulvarının TEK kuralıdır (ÖH V3 CAD A1 · H8, karar §28-21):
``cad_visualization.injector_plate_axial_span_mm`` — plaka kapak iç yüzüne
OTURUR, ``[x0, x0 + t]`` (``x0 = INJECTOR_PLATE_SEAT_X_MM``); plenum boşluğu
ve boru uzatması YOKTUR (eski ``INJECTOR_PLATE_AXIAL_OFFSET_MM`` CAD
kulvarında kaldırıldı, bu modül ikinci kaynak yazmaz). Çözücünün
``pre_chamber_length``'i x = 0'dan ölçülür ve ``pre + tane + post ==
chamber_length`` eksenel bütçesi çizimde bit-aynı kapanır; plaka ön odanın
içindedir ve CAD künyesinin söylediği gibi analiz kamara hacmi plakayı
düşmez (uyum turu, 14 Eki — kanıt raporu "Uyum turu (14 Eki)").

İTHALLER
--------
``step_export`` / ``cad_visualization`` modül düzeyinde İTHAL EDİLMEZ:
``step_export`` build123d'yi yükler ve CM-1'de bu modülü ithal edeceği için
modül düzeyi ithal döngü yaratır. Sabitler ve çözümleyiciler fonksiyon
içinde tek kaynaktan okunur (``_kaynaklar``).
"""

import hashlib
import json
import math

# ---------------------------------------------------------------------------
# Şema sabitleri
# ---------------------------------------------------------------------------
#: ``cad_assembly`` şema adı (B1 §3).
SCHEMA_ID = 'hrma.cad_assembly.v1'
#: Planı üreten fonksiyonun tam adı (B1 §3 ``generator`` alanı).
GENERATOR_ID = 'hrma.export.motor_assembly.build_plan'
#: Plan içindeki bütün uzunlukların birimi.
PLAN_UNIT = 'mm'
#: ``plan_signature`` uzunluğu (onaltılık karakter; B1 §3 ``[:16]``).
SIGNATURE_HEX_LENGTH = 16
#: Ölçü kaynak türleri (B1 §3 kuralı). Yenisi İCAT EDİLMEZ.
SOURCE_KINDS = ('solver', 'user', 'assumed', 'new_calc_required',
                'not_modelled')
#: ``profile_rz_mm`` noktalarının eksen SIRASI: [eksenel x, yarıçap r].
#: Depo sözleşmesi (``step_export._revolve_profile(points_rz)`` ve
#: ``sample_nozzle_inner_contour`` (z, r) yazar); B1 §3 örneği (r, z)
#: sırasındaydı — karışmasın diye her geometri bu alanı taşır.
PROFILE_AXES = ('x', 'r')
#: Metre birimli alan -> mm çarpanı (tek çevrim; bekçi ``value == raw *
#: çarpan`` eşitliğini tam sınar).
M_TO_MM = 1000.0

#: Grup kimlikleri (B1 §2.1 ağacı). Numara sırası STEP ağacının sırasıdır;
#: ``extra_groups`` (turbo B1 §6, besleme B1 §6) 70 ve üstünü kullanır.
GROUPS = ('10_case', '20_injector', '30_thermal', '40_propellant',
          '50_nozzle', '60_fasteners')
#: ``extra_groups`` ile eklenen grupların alt sınırı (motor grupları < 70).
EXTRA_GROUP_MIN_NUMBER = 70

#: Rol -> renk (B1 §2.1, karar 6 önerisi: renk = ROL; kaynak türü etikette
#: ve manifestte, renkte değil). TEK TANIM: CM-1/2/3 buradan okur.
ROLE_COLORS = {
    'case': '#2a78d6',
    'closure': '#2a78d6',
    'retainer': '#2a78d6',
    'flange': '#2a78d6',
    'propellant': '#eb6834',
    'nozzle_housing': '#1baf7a',
    'throat_insert': '#3a3f47',
    'injector_plate': '#9aa5b1',
    'manifold': '#9aa5b1',
    'thermal': '#c9a36b',
    'fastener': '#5a6270',
    'seal': '#1a1a1a',
    'igniter': '#5a6270',
    'jacket': '#2a78d6',
    'feed': '#9aa5b1',
    'mount': '#2a78d6',
}

#: Girişimde hangi parçanın KALACAĞI (büyük = öncelikli). Basınç sınırı
#: parçaları kazanır; eşit öncelikte iki parça girişirse İKİSİ de çizilmez
#: (hangisinin doğru olduğu bir fizik kalemi sorusudur, plan seçmez).
ROLE_PRIORITY = {
    'case': 100, 'closure': 100, 'flange': 100, 'retainer': 100,
    'jacket': 90, 'nozzle_housing': 90,
    'injector_plate': 80, 'manifold': 80,
    'propellant': 70,
    'throat_insert': 60,
    'thermal': 50,
    'fastener': 40, 'seal': 40, 'igniter': 40, 'feed': 40, 'mount': 40,
}


class AssemblyPlanError(ValueError):
    """Plan isteği BİÇİMCE geçersiz (motor tipi, ``extra_groups`` şeması).

    Veri eksikliği bu hatayı DOĞURMAZ: eksik ölçü parçayı ``not_modelled``
    listesine iter, plan yine üretilir (fail-closed-ama-dosya).
    """


# ---------------------------------------------------------------------------
# ASSUMED kuralları — TEK TABLO (B1 §4 karar 1; CAD hakem #3/#4)
# ---------------------------------------------------------------------------
#: Her satır bir yerleşim/şekil kuralıdır. ``constant`` satırlarının SAYISI
#: burada YAZILMAZ — tanımlandığı modülden okunur (``assumed_rule_values``).
#: ``defined_at`` satırları ithal edilemeyen (fonksiyon içi literal) çözücü
#: kurallarıdır: sayı yanıt alanından gelir, künye bu tablodan.
#:
#: ``text`` alanı künyenin KENDİSİDİR; 3B sahne (``motor_viz3d.js``
#: ``BOLT_CIRCLE_BASIS``) aynı metni bayt bayt taşır (A1a CM-S1; bekçi
#: ``tests/test_cad_montaj_a1.py``).
ASSUMED_RULES = {
    'INJECTOR_RING_RADIUS_FRACTIONS': {
        'class': 'layout',
        'constant': 'hrma.export.step_export.INJECTOR_RING_RADIUS_FRACTIONS',
        'text': ('assumed: injector orifice ring radius = fraction x '
                 'chamber radius (0.7 R first circuit, 0.38 R second); no '
                 'solver models the orifice layout'),
        'parts': ('H03', 'L01'),
        'replaced_by': None,
    },
    # ÖH V3 CAD A1 · H8 (uyum turu 14 Eki): eski
    # ``INJECTOR_PLATE_AXIAL_OFFSET_MM`` (4,0 mm plenum) satırının yerini
    # aldı; sayı ve yerleşim CAD kulvarının tek kaynağından okunur.
    'INJECTOR_PLATE_SEAT_RULE': {
        'class': 'layout',
        'constant': 'hrma.export.cad_visualization.INJECTOR_PLATE_SEAT_X_MM',
        'text': ('assumed: injector plate seated on the closure-head inner '
                 'face (CAD single rule cad_visualization.'
                 'injector_plate_axial_span_mm); no solver places the plate '
                 'axially or sizes a plenum, so no gap is invented'),
        'parts': ('H03', 'L01'),
        'replaced_by': 'F-CAD-7',
    },
    'GRAIN_AXIAL_POSITION_RULE': {
        'class': 'layout',
        'constant': (
            'hrma.export.cad_visualization.GRAIN_AXIAL_POSITION_FRACTION',
            'hrma.export.cad_visualization.GRAIN_AXIAL_MIN_SLACK_MM'),
        'text': ('assumed: grain front face at fraction x max(min slack, '
                 'chamber length - grain stack) from x = 0 (generator layout '
                 'rule); no solver publishes the axial position of this '
                 'grain'),
        'parts': ('S05', 'H07'),
        'replaced_by': 'F-CAD-11 (solid forward insulation thickness)',
    },
    'NOZZLE_WALL_GENERATOR_RULE': {
        'class': 'pressure_boundary_exception',
        'constant': (
            'hrma.export.cad_visualization.NOZZLE_WALL_MIN_MM',
            'hrma.export.cad_visualization.NOZZLE_WALL_THROAT_FRACTION'),
        'text': ('assumed generator rule: nozzle wall = max(min wall, '
                 'fraction x throat diameter); NOT from a structural or '
                 'thermal analysis of the nozzle. Named exception to karar 1 '
                 '(today\'s STEP draws it; kept until F-CAD-5 so the export '
                 'does not regress)'),
        'parts': ('S09', 'L10'),
        'replaced_by': 'F-CAD-5 (ÖNEMLİ)',
    },
    'STRUCTURAL_BOLT_CIRCLE_RADIUS_RULE': {
        'class': 'layout',
        'defined_at': ('hrma/analysis/structural_analysis.py:2215 '
                       'bolt_circle_radius = D/2 + 0.025 m'),
        'field': 'structural_analysis.fastener_analysis.bolt_circle_radius',
        'text': 'assumed: fixed +25 mm layout rule',
        'parts': ('H14', 'S14', 'L15'),
        'replaced_by': 'F-CAD-3',
    },
    'STRUCTURAL_BOLT_CIRCLE_DIAMETER_RULE': {
        'class': 'layout',
        'defined_at': ('hrma/analysis/structural_analysis.py:1982 '
                       'bolt_circle_diameter = D + 0.05 m'),
        'field': 'structural_analysis.end_cap_analysis.bolt_circle_diameter',
        'text': 'assumed: fixed +50 mm layout rule',
        'parts': ('H14', 'S14', 'L15'),
        'replaced_by': 'F-CAD-3',
    },
}


def _modul_sabiti(yol):
    """``paket.modul.AD`` yolundaki sabiti ithal ederek okur."""
    import importlib
    modul, _, ad = yol.rpartition('.')
    return getattr(importlib.import_module(modul), ad)


def assumed_rule_values():
    """``ASSUMED_RULES`` satırlarının SAYILARINI tanımlandıkları yerden okur.

    Döner ``{kural_adı: değer | (değerler...) | None}``; ``defined_at``
    satırları ``None`` döner (sayı yanıt alanından okunur).
    """
    out = {}
    for ad, satir in ASSUMED_RULES.items():
        sabit = satir.get('constant')
        if sabit is None:
            out[ad] = None
        elif isinstance(sabit, tuple):
            out[ad] = tuple(_modul_sabiti(s) for s in sabit)
        else:
            out[ad] = _modul_sabiti(sabit)
    return out


# ---------------------------------------------------------------------------
# Parça kataloğu (B1 §1, CM-0 düzeltmeleriyle — kanıt raporu "§1/§2.1")
# ---------------------------------------------------------------------------
#: Her motor tipinin TAM parça kataloğu: (kimlik, ad, grup, rol, sınıf).
#: ``sınıf``: ``pressure_boundary`` (kalınlığı basınç sınırı — karar 1),
#: ``layout`` (yerleşim/şekil), ``geometry`` (çözücü geometrisi), ``region``
#: (parça değil boşluk; DXF ölçüsü), ``hardware`` (bağlantı elemanı / conta /
#: ateşleyici). Planın ``parts`` ∪ ``not_modelled`` ∪ ``regions`` kümesi bu
#: kataloğun TAMAMINI bir kez kapsar (bekçi).
PART_CATALOG = {
    'solid': (
        ('S01', 'case_tube', '10_case', 'case', 'pressure_boundary'),
        ('S02', 'forward_closure', '10_case', 'closure', 'pressure_boundary'),
        ('S03', 'aft_closure_nozzle_retainer', '10_case', 'retainer',
         'pressure_boundary'),
        ('S04', 'retaining_ring', '60_fasteners', 'fastener', 'hardware'),
        ('S05', 'fuel_grain', '40_propellant', 'propellant', 'geometry'),
        ('S06', 'liner_tube', '30_thermal', 'thermal', 'layout'),
        ('S07', 'insulation_tube', '30_thermal', 'thermal', 'layout'),
        ('S08a', 'forward_insulation', '30_thermal', 'thermal', 'layout'),
        ('S08b', 'aft_insulation', '30_thermal', 'thermal', 'layout'),
        ('S09', 'nozzle_housing', '50_nozzle', 'nozzle_housing',
         'pressure_boundary'),
        ('S10', 'throat_insert', '50_nozzle', 'throat_insert',
         'pressure_boundary'),
        ('S12', 'igniter', '20_injector', 'igniter', 'hardware'),
        ('S13', 'oring_seals', '60_fasteners', 'seal', 'hardware'),
        ('S14', 'closure_bolts', '60_fasteners', 'fastener', 'hardware'),
    ),
    'hybrid': (
        ('H01', 'case_tube', '10_case', 'case', 'pressure_boundary'),
        ('H02', 'forward_closure', '10_case', 'closure', 'pressure_boundary'),
        ('H03', 'injector_plate', '20_injector', 'injector_plate',
         'pressure_boundary'),
        ('H04', 'oxidizer_manifold_dome', '20_injector', 'manifold',
         'pressure_boundary'),
        ('H05', 'oxidizer_inlet_port', '20_injector', 'feed', 'hardware'),
        ('H06', 'pre_combustion_chamber', '40_propellant', 'region',
         'region'),
        ('H07', 'fuel_grain', '40_propellant', 'propellant', 'geometry'),
        ('H08', 'post_combustion_chamber', '40_propellant', 'region',
         'region'),
        ('H09a', 'chamber_liner_pre', '30_thermal', 'thermal', 'layout'),
        ('H09b', 'chamber_liner_post', '30_thermal', 'thermal', 'layout'),
        ('H09c', 'nozzle_entry_liner', '30_thermal', 'thermal', 'layout'),
        ('H10', 'nozzle_housing', '50_nozzle', 'nozzle_housing',
         'pressure_boundary'),
        ('H11', 'throat_insert', '50_nozzle', 'throat_insert',
         'pressure_boundary'),
        ('H12', 'aft_flange_nozzle_retainer', '10_case', 'flange',
         'pressure_boundary'),
        ('H13', 'oring_seals', '60_fasteners', 'seal', 'hardware'),
        ('H14', 'closure_bolts', '60_fasteners', 'fastener', 'hardware'),
        ('H15', 'igniter', '20_injector', 'igniter', 'hardware'),
    ),
    'liquid': (
        ('L01', 'injector_face_plate', '20_injector', 'injector_plate',
         'pressure_boundary'),
        ('L02', 'oxidizer_manifold_dome', '20_injector', 'manifold',
         'pressure_boundary'),
        ('L03', 'fuel_manifold_ring', '20_injector', 'manifold',
         'pressure_boundary'),
        ('L04', 'propellant_inlets', '20_injector', 'feed', 'hardware'),
        ('L05', 'chamber_liner_wall', '10_case', 'case',
         'pressure_boundary'),
        ('L06', 'regen_channels', '10_case', 'jacket', 'geometry'),
        ('L07', 'cooling_jacket', '10_case', 'jacket', 'pressure_boundary'),
        ('L08', 'coolant_manifolds', '10_case', 'manifold',
         'pressure_boundary'),
        ('L09', 'ablative_liner', '30_thermal', 'thermal', 'layout'),
        ('L10', 'nozzle_housing', '50_nozzle', 'nozzle_housing',
         'pressure_boundary'),
        ('L12', 'head_and_nozzle_flanges', '10_case', 'flange',
         'pressure_boundary'),
        ('L13', 'mount_gimbal_flange', '10_case', 'mount', 'hardware'),
        ('L14', 'igniter_port', '20_injector', 'igniter', 'hardware'),
        ('L15', 'oring_seals_and_bolts', '60_fasteners', 'fastener',
         'hardware'),
        ('L16', 'forward_closure', '10_case', 'closure', 'pressure_boundary'),
    ),
}


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------
def _sonlu(v):
    """Sonlu float ya da None — merkezî kapıdan (``input_guard``,
    ÖH D28 / OH-D27-11: el yazısı çevirici kapısı açılmaz; bool sayı
    sayılmaz)."""
    from hrma.utils.input_guard import finite_number
    return finite_number(v)


def _pozitif(v):
    """Sonlu ve pozitif float ya da None — merkezî kapıdan."""
    from hrma.utils.input_guard import finite_positive
    return finite_positive(v)


def _yol(d, yol):
    """Noktalı yolu izler. Döner ``(bulundu, değer)``."""
    cur = d
    for parca in yol.split('.'):
        if not isinstance(cur, dict) or parca not in cur:
            return False, None
        cur = cur[parca]
    return True, cur


def _ilk_alan(md, yollar, kok_etiketleri=('', 'motor_geometry')):
    """``yollar``daki ilk POZİTİF sonlu alanı bulur.

    Kökler sırayla denenir: gövdenin kendisi, sonra (varsa) gövdedeki
    ``motor_geometry`` sözlüğü. Döner ``(değer, tam_yol)`` ya da
    ``(None, None)``. ``tam_yol`` gövdeye GÖRELİDİR (aile sözleşmesi:
    ``invalid_fields`` yolları ``motor_data``ya göreli).
    """
    for kok in kok_etiketleri:
        dugum = md if not kok else md.get(kok)
        if not isinstance(dugum, dict):
            continue
        for y in yollar:
            bulundu, deger = _yol(dugum, y)
            if bulundu and _pozitif(deger) is not None:
                return float(deger), (f'{kok}.{y}' if kok else y)
    return None, None


def _dim(value, kind, field=None, raw=None, unit=None, rule=None,
         solver_code=None, basis=None):
    """Tek ölçü kaydı (B1 §3 ``dims[k]``)."""
    if kind not in SOURCE_KINDS:
        raise AssemblyPlanError(f'unknown source kind {kind!r}')
    src = {'kind': kind}
    if field is not None:
        src['field'] = field
    if raw is not None:
        src['raw'] = raw
        src['raw_unit'] = unit
    if rule is not None:
        src['rule'] = rule
    if solver_code is not None:
        src['solver_code'] = solver_code
    if basis is not None:
        src['basis'] = basis
    return {'value': (None if value is None else float(value)),
            'source': src}


def _kullanici_mi(kod):
    """Çözücü künye kodu "bu sayı istekten geldi" diyor mu?"""
    if not isinstance(kod, str):
        return False
    k = kod.lower()
    return any(m in k for m in ('user', 'request_value', 'caller',
                                'input'))


def _uzunluk_mm(md, anahtar):
    """Metre/mm belirsiz üst seviye uzunluk alanını mm'ye TEK çevrimle okur.

    Birim ``motor_geometry.resolve_length_m`` ile çözülür (depodaki tek
    kural); ham sayı ALANIN KENDİSİNDEN okunur, böylece ``value == raw *
    1000`` (metre) ya da ``value == raw`` (mm) tam eşitliği sınanabilir.
    Döner ``(mm | None, künye sözlüğü)``.
    """
    from hrma.export.motor_geometry import (EXPORT_LENGTH_FIELDS,
                                            LENGTH_SI_MAX_M, resolve_length_m)
    deger_m, nasil = resolve_length_m(
        md, anahtar, EXPORT_LENGTH_FIELDS.get(anahtar, LENGTH_SI_MAX_M))
    if deger_m is None:
        return None, {'field': anahtar, 'unit_resolution': nasil}
    if nasil == 'motor_geometry':
        alan, ham, birim = f'motor_geometry.{anahtar}', \
            md['motor_geometry'][anahtar], 'm'
    elif nasil in ('declared:m', 'si'):
        alan, ham, birim = anahtar, md[anahtar], 'm'
    else:  # 'declared:mm' / 'mm'
        alan, ham, birim = anahtar, md[anahtar], 'mm'
    ham = float(ham)
    mm = ham * M_TO_MM if birim == 'm' else ham
    return mm, {'field': alan, 'raw': ham, 'unit': birim,
                'unit_resolution': nasil}


# ---------------------------------------------------------------------------
# Saf geometri: kesit hücreleri, kırpma, girişim, temas
# ---------------------------------------------------------------------------
def _alan(poly):
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def _cevre(poly):
    n = len(poly)
    return sum(math.hypot(poly[(i + 1) % n][0] - poly[i][0],
                          poly[(i + 1) % n][1] - poly[i][1])
               for i in range(n))


def _ccw(poly):
    return poly if _alan(poly) >= 0 else list(reversed(poly))


def _kapali_degil(poly):
    """Son nokta ilkini tekrarlıyorsa atar."""
    pts = [(float(x), float(r)) for x, r in poly]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    # Ardışık tekrarları at (sıfır boy kenar kulak kırpmayı bozar).
    temiz = []
    for p in pts:
        if not temiz or p != temiz[-1]:
            temiz.append(p)
    if len(temiz) > 1 and temiz[0] == temiz[-1]:
        temiz.pop()
    return temiz


def _ucgenlere_bol(poly):
    """Basit çokgeni kulak kırpma ile üçgenlere böler (dışbükey hücreler)."""
    pts = _ccw(_kapali_degil(poly))
    idx = list(range(len(pts)))
    ucgenler = []

    def _cross(o, a, b):
        return ((a[0] - o[0]) * (b[1] - o[1])
                - (a[1] - o[1]) * (b[0] - o[0]))

    def _icinde(p, a, b, c):
        d1 = _cross(a, b, p)
        d2 = _cross(b, c, p)
        d3 = _cross(c, a, p)
        return d1 >= 0 and d2 >= 0 and d3 >= 0

    koruma = 0
    while len(idx) > 3 and koruma < 100000:
        koruma += 1
        kulak = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            cr = _cross(a, b, c)
            if cr <= 1e-15:
                if abs(cr) <= 1e-15:
                    # Doğrusal köşe: at, üçgen üretme.
                    idx.pop(k)
                    kulak = True
                    break
                continue
            if any(_icinde(pts[j], a, b, c) for j in idx
                   if j not in (i0, i1, i2)):
                continue
            ucgenler.append([a, b, c])
            idx.pop(k)
            kulak = True
            break
        if not kulak:
            break
    if len(idx) == 3:
        a, b, c = (pts[i] for i in idx)
        if abs(_cross(a, b, c)) > 1e-15:
            ucgenler.append([a, b, c])
    return ucgenler


def _hucreler(poly):
    """Kesiti dışbükey hücrelere böler: dikdörtgen tek hücre, gerisi üçgen."""
    pts = _kapali_degil(poly)
    xs = sorted({p[0] for p in pts})
    rs = sorted({p[1] for p in pts})
    if len(pts) == 4 and len(xs) == 2 and len(rs) == 2:
        return [_ccw(pts)]
    return _ucgenlere_bol(pts)


def _kirp(konu, kirpici):
    """Sutherland–Hodgman: dışbükey ``konu`` ∩ dışbükey ``kirpici``."""
    cikti = list(konu)
    n = len(kirpici)
    for i in range(n):
        a, b = kirpici[i], kirpici[(i + 1) % n]
        girdi, cikti = cikti, []
        if not girdi:
            break

        def _ic(p):
            return ((b[0] - a[0]) * (p[1] - a[1])
                    - (b[1] - a[1]) * (p[0] - a[0])) >= 0

        def _kesisim(p, q):
            x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
            x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if den == 0:
                return q
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

        for j in range(len(girdi)):
            p, q = girdi[j - 1], girdi[j]
            if _ic(q):
                if not _ic(p):
                    cikti.append(_kesisim(p, q))
                cikti.append(q)
            elif _ic(p):
                cikti.append(_kesisim(p, q))
    return cikti


def section_overlap(poly_a, poly_b):
    """İki r–z kesitinin örtüşmesi. Döner ``{'area_mm2', 'depth_mm', 'x_mm',
    'r_mm'}`` (son ikisi örtüşme bölgesinin sınır kutusu, yoksa None).

    ``depth_mm`` örtüşme hücrelerinin en büyük ``2·alan/çevre`` değeridir
    (ince bir şeridin kalınlığı; dikdörtgende kısa kenara yakınsar).
    Eksenel simetrik iki katı ancak kesitleri pozitif alanla örtüşürse
    hacimce kesişir.
    """
    toplam, derin = 0.0, 0.0
    xs, rs = [], []
    ha, hb = _hucreler(poly_a), _hucreler(poly_b)
    for ca in ha:
        xa = [p[0] for p in ca]
        ra = [p[1] for p in ca]
        for cb in hb:
            if (max(xa) <= min(p[0] for p in cb)
                    or min(xa) >= max(p[0] for p in cb)
                    or max(ra) <= min(p[1] for p in cb)
                    or min(ra) >= max(p[1] for p in cb)):
                continue
            ortak = _kirp(ca, cb)
            if len(ortak) < 3:
                continue
            a = abs(_alan(ortak))
            if a <= 0.0:
                continue
            toplam += a
            xs.extend(p[0] for p in ortak)
            rs.extend(p[1] for p in ortak)
            c = _cevre(ortak)
            if c > 0:
                derin = max(derin, 2.0 * a / c)
    return {'area_mm2': toplam, 'depth_mm': derin,
            'x_mm': [min(xs), max(xs)] if xs else None,
            'r_mm': [min(rs), max(rs)] if rs else None}


def _parca_uzaklik(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0.0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def section_distance(poly_a, poly_b):
    """İki kesit sınırı arasındaki en kısa uzaklık [mm] (örtüşme ayrıca)."""
    pa, pb = _kapali_degil(poly_a), _kapali_degil(poly_b)
    en = math.inf
    for i in range(len(pa)):
        a1, a2 = pa[i], pa[(i + 1) % len(pa)]
        for j in range(len(pb)):
            b1, b2 = pb[j], pb[(j + 1) % len(pb)]
            en = min(en, _parca_uzaklik(a1, b1, b2), _parca_uzaklik(a2, b1, b2),
                     _parca_uzaklik(b1, a1, a2), _parca_uzaklik(b2, a1, a2))
            if en == 0.0:
                return 0.0
    return en


def profile_volume_mm3(profile):
    """Kapalı r–z profilinin eksen etrafında döndürülmüş hacmi [mm³].

    Pappus–Guldinus: ``V = 2π · r̄ · A``; çokgen için kapalı biçim
    ``V = (π/3) · |Σ (r_i + r_{i+1}) (x_i r_{i+1} − x_{i+1} r_i)|``
    (sembolik doğrulama kanıt dizininde). OCC'siz ikinci yol: STEP'in OCC
    hacmiyle kıyaslanır.
    """
    pts = _kapali_degil(profile)
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, r1 = pts[i]
        x2, r2 = pts[(i + 1) % n]
        s += (r1 + r2) * (x1 * r2 - x2 * r1)
    return abs(math.pi / 3.0 * s)


def part_volume_mm3(part):
    """Parçanın hacmi: döner profil − eksenel delikler (plaka orifisleri)."""
    geo = part['geometry']
    v = profile_volume_mm3(geo['profile_rz_mm'])
    kutu = _kutu(geo['profile_rz_mm'])
    kalinlik = kutu['x_mm'][1] - kutu['x_mm'][0]
    for h in geo.get('holes') or ():
        v -= h['n'] * math.pi * (h['d_mm'] / 2.0) ** 2 * kalinlik
    return v


def _dikdortgen(x0, x1, r0, r1):
    """[x0,x1]×[r0,r1] kapalı r–z profili (saat yönü tersi)."""
    return [[float(x0), float(r0)], [float(x1), float(r0)],
            [float(x1), float(r1)], [float(x0), float(r1)]]


def _kutu(poly):
    xs = [p[0] for p in poly]
    rs = [p[1] for p in poly]
    return {'x_mm': [min(xs), max(xs)], 'r_mm': [min(rs), max(rs)]}


# ---------------------------------------------------------------------------
# İmza
# ---------------------------------------------------------------------------
def canonical_json(obj):
    """Kararlı JSON: sıralı anahtar, boşluksuz, NaN yasak."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def plan_signature(parts):
    """``sha256(canonical_json(parts))[:16]`` (B1 §3). ``parts`` = plan
    ``parts`` listesi (yalnız çizilen parçalar)."""
    ozet = hashlib.sha256(canonical_json(parts).encode('utf-8')).hexdigest()
    return ozet[:SIGNATURE_HEX_LENGTH]


# ---------------------------------------------------------------------------
# Plan kurucu
# ---------------------------------------------------------------------------
class _Kurucu:
    """Tek planın ara durumu (parça, çizilmeyen, bölge, temas listeleri)."""

    def __init__(self, motor_type):
        self.motor_type = motor_type
        self.katalog = {k[0]: k for k in PART_CATALOG[motor_type]}
        self.parts = []
        self.not_modelled = []
        self.regions = []
        self.contacts = []
        self.declared_global = []
        self.invalid_fields = []

    def _kat(self, pid):
        return self.katalog[pid]

    def parca(self, pid, profile, dims, declared=(), material=None,
              holes=None, name=None):
        _i, ad, grup, rol, _s = self._kat(pid)
        geo = {'kind': 'revolve', 'profile_axes': list(PROFILE_AXES),
               'profile_rz_mm': [[float(x), float(r)] for x, r in profile]}
        if holes:
            geo['holes'] = holes
        kayit = {'id': pid, 'name': name or ad, 'group': grup, 'role': rol,
                 'material': material, 'color': ROLE_COLORS[rol],
                 'drawn': True, 'geometry': geo, 'dims': dims,
                 'declared': list(declared)}
        kayit['bbox_mm'] = _kutu(geo['profile_rz_mm'])
        self.parts.append(kayit)
        return kayit

    def cizilmez(self, pid, kind, reason, replaced_by=None, fields=None,
                 name=None, extra=None):
        _i, ad, grup, rol, sinif = self._kat(pid)
        kayit = {'id': pid, 'name': name or ad, 'group': grup, 'role': rol,
                 'class': sinif, 'kind': kind, 'reason': reason}
        if replaced_by:
            kayit['replaced_by'] = replaced_by
        if fields:
            kayit['fields_looked_for'] = list(fields)
        if extra:
            kayit.update(extra)
        self.not_modelled.append(kayit)
        return kayit

    def bolge(self, pid, x0, x1, dims, declared=()):
        _i, ad, _g, _r, _s = self._kat(pid)
        self.regions.append({'id': pid, 'name': ad, 'x_mm': [float(x0),
                                                             float(x1)],
                             'dims': dims, 'declared': list(declared)})

    def temas(self, a, b, kind, gap_mm, basis):
        self.contacts.append({'a': a, 'b': b, 'kind': kind,
                              'gap_mm': float(gap_mm), 'basis': basis})


def _malzeme(md, yollar, not_=None):
    """Yayımlanan malzeme anahtarı; yoksa None (malzeme UYDURULMAZ)."""
    for kok in ('', 'motor_geometry'):
        dugum = md if not kok else md.get(kok)
        if not isinstance(dugum, dict):
            continue
        for y in yollar:
            bulundu, deger = _yol(dugum, y)
            if bulundu and isinstance(deger, str) and deger.strip():
                kayit = {'key': deger.strip(),
                         'field': f'{kok}.{y}' if kok else y}
                if not_:
                    kayit['note'] = not_
                return kayit
    return None


def _cidar(md, k):
    """Kamara/kasa cidarı — ``cad_visualization._chamber_wall_design`` kararı
    ile, değer ise SEÇİLEN alanın kendisinden (bit-aynı)."""
    from hrma.export.cad_visualization import (CHAMBER_WALL_SCHEMAS,
                                               _chamber_wall_design)
    tasarim = _chamber_wall_design(md)
    blok_adi = tasarim.get('schema')
    if tasarim['thickness_m'] is None or blok_adi is None:
        kabul = [f'structural_analysis.{b}.{a}'
                 for b, u, o, _y in CHAMBER_WALL_SCHEMAS for a in (u, o)]
        return None, kabul, tasarim
    struct = md.get('structural_analysis') or {}
    blok = struct.get(blok_adi) or {}
    for b, kullanilan, onerilen, _y in CHAMBER_WALL_SCHEMAS:
        if b != blok_adi:
            continue
        for anahtar in (kullanilan, onerilen):
            v = _sonlu(blok.get(anahtar))
            if v is not None and abs(v / 1000.0 - tasarim['thickness_m']) \
                    <= 1e-15:
                kod = blok.get('wall_thickness_source')
                tur = 'user' if _kullanici_mi(kod) else 'solver'
                return _dim(v, tur,
                            field=f'structural_analysis.{blok_adi}.{anahtar}',
                            raw=v, unit='mm', solver_code=kod,
                            basis=tasarim['source']), None, tasarim
    return None, [], tasarim


def build_plan(motor_data, motor_type, injector=None, extra_groups=None):
    """Motor sonucundan ``cad_assembly`` v1 planını kurar.

    ``motor_data`` ihraç uçlarının aldığı gövdedir (hibrit
    ``currentResults.motor``, katı/sıvı ``currentResults.motor_geometry``);
    tam ``/calculate_*`` yanıtı da verilebilir — alanlar gövdeye göreli
    yollarla aranır (kök, sonra ``motor_geometry``). ``injector`` hibrit
    sayfanın ayrı tuttuğu enjektör paneli bloğudur (K-1 kablolaması);
    gövdede ``injector`` yoksa oraya konur. ``extra_groups`` turbo/besleme
    planlarının ekleme noktasıdır (turbo B1 §6, besleme B1 §6): ``[{'group':
    '70_ad', 'parts': [<parça şeması>...]}]``.

    Veri eksikliği hata DEĞİLDİR: çözülemeyen parça ``not_modelled``
    listesine gerekçesiyle girer. ``AssemblyPlanError`` yalnız biçim
    hatasında (motor tipi, ``extra_groups`` şeması) yükselir.
    """
    from hrma.constants import MOTOR_TYPES
    if not isinstance(motor_type, str) or \
            motor_type.strip().lower() not in MOTOR_TYPES:
        raise AssemblyPlanError(
            f'motor_type must be one of {list(MOTOR_TYPES)}; received '
            f'{motor_type!r}. The part set depends on it, so no substitute '
            'type is assumed.')
    motor_type = motor_type.strip().lower()
    ham = dict(motor_data) if isinstance(motor_data, dict) else {}
    injector_supplied = isinstance(injector, dict) and bool(injector)
    if injector_supplied and not isinstance(ham.get('injector'), dict):
        ham['injector'] = dict(injector)

    k = _Kurucu(motor_type)
    kurallar = assumed_rule_values()

    # ---- Çapa: kamara boyu, deliği, cidarı ---------------------------------
    L, L_k = _uzunluk_mm(ham, 'chamber_length')
    D, D_k = _uzunluk_mm(ham, 'chamber_diameter')
    cidar, cidar_kabul, cidar_tasarim = _cidar(ham, k)
    if L is None:
        k.invalid_fields.append({'field': 'chamber_length',
                                 'reason': 'unresolved',
                                 'unit_resolution': L_k.get('unit_resolution')})
    if D is None:
        k.invalid_fields.append({'field': 'chamber_diameter',
                                 'reason': 'unresolved',
                                 'unit_resolution': D_k.get('unit_resolution')})
    if cidar is None:
        k.invalid_fields.append({'field': (cidar_kabul or ['?'])[0],
                                 'reason': 'not_supplied',
                                 'accepted_paths': cidar_kabul or []})

    if L is None or D is None or cidar is None:
        # Plan çapasız kurulamaz: HİÇBİR parça çizilmez, katalog gerekçeli.
        neden = ('the assembly cannot be anchored: chamber length, chamber '
                 'bore and chamber wall must all be published (see '
                 'invalid_fields); no part is placed on a guessed frame')
        for pid, *_r in PART_CATALOG[motor_type]:
            k.cizilmez(pid, 'not_modelled', neden)
        return _bitir(k, ham, motor_type, injector_supplied, extra_groups,
                      status='not_drawable')

    rc = D / 2.0
    t_w = cidar['value']
    dims_kamara = {
        'bore_diameter_mm': _dim(D, 'solver', field=D_k['field'],
                                 raw=D_k['raw'], unit=D_k['unit']),
        'chamber_length_mm': _dim(L, 'solver', field=L_k['field'],
                                  raw=L_k['raw'], unit=L_k['unit']),
        'wall_thickness_mm': cidar,
    }
    cidar_beyan = []
    if cidar_tasarim.get('note'):
        cidar_beyan.append(cidar_tasarim['note'])
    sf = cidar_tasarim.get('safety_factor')
    if sf is not None and cidar_tasarim.get('safety_factor_is_measured') \
            is True and sf < 1.0:
        cidar_beyan.append(f'safety factor at this wall = {sf:.4f} - BELOW '
                           '1.0, THE WALL FAILS (drawn as published, K-7)')

    # ---- Enjektör plakası ve baş payı ---------------------------------------
    plaka = None
    if motor_type in ('hybrid', 'liquid'):
        plaka = _enjektor_plakasi(ham, k, motor_type, rc, kurallar)
    if plaka is not None and plaka['x1'] > L:
        # CAD'in STEP kapısıyla aynı hüküm (``shorter_than_injector_plate``):
        # kamaraya sığmayan plaka lüleye taşar; ölçü uydurulmaz, çizilmez.
        k.cizilmez(plaka['id'], 'not_modelled',
                   f'the injector plate ({plaka["t"]:.4g} mm, seated at '
                   f'x = {plaka["x0"]:.4g} mm) does not fit inside the '
                   f'{L:.4g} mm chamber (shorter_than_injector_plate, the '
                   'STEP export refuses the same input)',
                   extra={'dims': plaka['dims']})
        plaka = None
    # Kapak iç yüzü x = 0'dadır; boru öne UZAMAZ (plenum yok, CAD H8).
    x_on = 0.0

    # ---- Kasa borusu ---------------------------------------------------------
    kasa_id = {'solid': 'S01', 'hybrid': 'H01', 'liquid': 'L05'}[motor_type]
    kasa_dims = dict(dims_kamara)
    kasa_beyan = list(cidar_beyan)
    k.parca(kasa_id, _dikdortgen(x_on, L, rc, rc + t_w), kasa_dims,
            declared=kasa_beyan,
            material=_malzeme(ham, ('structural_analysis.case_analysis'
                                    '.case_material',
                                    'structural_analysis.chamber_structure'
                                    '.material_key',
                                    'chamber_material')))

    # ---- Ön kapak -----------------------------------------------------------
    kapak_id = {'solid': 'S02', 'hybrid': 'H02', 'liquid': 'L16'}[motor_type]
    kapak, kapak_alan = _ilk_alan(
        ham, ('structural_analysis.end_cap_analysis.flat_head_thickness',))
    if kapak is None:
        k.cizilmez(kapak_id, 'new_calc_required',
                   'closure head thickness is not published '
                   '(structural_analysis.end_cap_analysis.flat_head_thickness)'
                   '; a pressure-boundary thickness is never drawn from an '
                   'assumed rule (karar 1)',
                   fields=['structural_analysis.end_cap_analysis'
                           '.flat_head_thickness'])
    else:
        _b, cap_blok = _yol(ham, kapak_alan.rsplit('.', 1)[0])
        kapak_beyan = ['flat closure head drawn as a disc of the case outer '
                       'diameter (the export and scene definition)']
        if isinstance(cap_blok, dict) and cap_blok.get('recommended_type') \
                == 'dished':
            kapak_beyan.append('the analysis recommends a DISHED head; this '
                               'plan models a FLAT head, so the flat-head '
                               'thickness is used')
        kapak_beyan.append('closure flange lip (bolt circle + edge margin) '
                           'NOT drawn: flange thickness needs F-CAD-2')
        k.parca(kapak_id, _dikdortgen(x_on - kapak, x_on, 0.0, rc + t_w),
                {'thickness_mm': _dim(kapak, 'solver', field=kapak_alan,
                                      raw=kapak, unit='mm')},
                declared=kapak_beyan,
                material=_malzeme(ham, ('structural_analysis.end_cap_analysis'
                                        '.material_key',
                                        'structural_analysis.end_cap_analysis'
                                        '.case_material',
                                        'structural_analysis.case_analysis'
                                        '.case_material',
                                        'structural_analysis'
                                        '.chamber_structure.material_key',
                                        'chamber_material')))
        k.temas(kapak_id, kasa_id, 'axial_face', 0.0,
                'closure inner face on the tube front face')

    # ---- Plaka parçası (çözüldüyse) -----------------------------------------
    if plaka is not None:
        plaka_id = plaka['id']
        k.parca(plaka_id, _dikdortgen(plaka['x0'], plaka['x1'], 0.0, rc),
                plaka['dims'], declared=plaka['declared'],
                material=plaka['material'], holes=plaka['holes'])
        k.temas(plaka_id, kasa_id, 'radial_face', 0.0,
                'plate outer diameter = chamber bore (line-to-line fit)')
        if kapak is not None:
            # Kapak iç yüzü x = x_on = 0; boşluk CAD'in oturma yerinden.
            k.temas(kapak_id, plaka_id, 'axial_gap', plaka['x0'] - x_on,
                    'plate seated on the closure-head inner face '
                    '(INJECTOR_PLATE_SEAT_RULE, CAD single rule)')
        manifold_id = 'H04' if motor_type == 'hybrid' else 'L02'
        k.cizilmez(manifold_id, 'new_calc_required',
                   'manifold dome / plenum is not sized; the plate seats on '
                   'the closure-head inner face (CAD single rule '
                   'injector_plate_axial_span_mm), no plenum gap is invented '
                   'and no dome solid is drawn',
                   replaced_by='F-CAD-7')

    # ---- Motor tipine özgü parçalar -----------------------------------------
    if motor_type == 'solid':
        _kati_parcalar(ham, k, L, rc, t_w, kurallar, kasa_id)
    elif motor_type == 'hybrid':
        _hibrit_parcalar(ham, k, L, rc, t_w, kurallar, kasa_id, plaka)
    else:
        _sivi_parcalar(ham, k, L, rc, t_w, kurallar, kasa_id, plaka)

    # ---- Lüle ----------------------------------------------------------------
    _lule(ham, k, L, rc, t_w, kurallar, kasa_id)

    # ---- Bağlantı elemanları (ortak) -----------------------------------------
    _baglanti_elemanlari(ham, k, rc)

    return _bitir(k, ham, motor_type, injector_supplied, extra_groups,
                  status='ok')


def _enjektor_plakasi(md, k, motor_type, rc, kurallar):
    """Plaka kalınlığı + delik planı. Çözülemezse ``None`` (+ not_modelled).

    Kalınlık YALNIZ ``injector_design.plate_thickness_mm``den okunur (A1a
    CM-H1 künyesiyle; sahne ``publishedPartPlan`` ile aynı kural).
    ``injector_results.plate_structural`` üçüncü yolu CM-H1 DEVİR'i
    kapanana kadar okunmaz: kazanılmamış modül varsayılanı taşıyabilir.
    """
    from hrma.export.step_export import resolve_injector_circuits
    pid = 'H03' if motor_type == 'hybrid' else 'L01'
    blok, blok_adi, devreler, eksik = resolve_injector_circuits(
        md, motor_type=motor_type)
    if blok is None:
        k.cizilmez(pid, 'not_modelled',
                   'this result publishes no injector block '
                   '(injector_results / injector_design / injector)',
                   fields=['injector_design', 'injector_results', 'injector'])
        return None
    if not devreler:
        k.cizilmez(pid, 'not_modelled',
                   'injector orifice count / diameter could not be resolved '
                   f'from {blok_adi}; no orifice plan is invented',
                   fields=[f'{blok_adi}.number_of_orifices',
                           f'{blok_adi}.orifice_diameter_mm'])
        return None
    inj = md.get('injector_design') if isinstance(
        md.get('injector_design'), dict) else {}
    t = _pozitif(inj.get('plate_thickness_mm'))
    if t is None:
        neden = ('injector plate thickness is not published '
                 '(injector_design.plate_thickness_mm); a pressure-boundary '
                 'thickness is never assumed (karar 1)')
        if motor_type == 'liquid':
            neden += ('; the liquid engine does not call '
                      'injector_plate_structural yet (F-CAD-9 wiring)')
        k.cizilmez(pid, 'new_calc_required', neden,
                   replaced_by='F-CAD-9' if motor_type == 'liquid' else None,
                   fields=['injector_design.plate_thickness_mm'],
                   extra={'orifice_plan_available': [
                       {'circuit': c['name'], 'n': c['n'], 'd_mm': c['d_mm']}
                       for c in devreler]})
        return None
    kod = inj.get('plate_thickness_source')
    dims = {'thickness_mm': _dim(
        t, 'user' if _kullanici_mi(kod) else 'solver',
        field='injector_design.plate_thickness_mm', raw=t, unit='mm',
        solver_code=kod,
        basis=(inj.get('plate_thickness_basis')
               if isinstance(inj.get('plate_thickness_basis'), str)
               else None))}
    fraksiyonlar = kurallar['INJECTOR_RING_RADIUS_FRACTIONS']
    halka_verilen = _pozitif((blok or {}).get('orifice_ring_radius_mm'))
    delikler = []
    beyan = []
    for i, c in enumerate(devreler):
        if i == 0 and halka_verilen is not None:
            halka = float(halka_verilen)
            h_src = {'kind': 'solver',
                     'field': f'{blok_adi}.orifice_ring_radius_mm'}
        else:
            frac = fraksiyonlar[min(i, len(fraksiyonlar) - 1)]
            halka = frac * rc
            h_src = {'kind': 'assumed',
                     'rule': 'INJECTOR_RING_RADIUS_FRACTIONS',
                     'rule_value': frac}
            beyan.append(f'{c["name"]} orifice ring radius ASSUMED '
                         f'{frac:g} x chamber radius = {halka:.4g} mm '
                         '(INJECTOR_RING_RADIUS_FRACTIONS), not from pattern '
                         'analysis')
        delikler.append({'circuit': c['name'], 'n': int(c['n']),
                         'd_mm': float(c['d_mm']), 'ring_r_mm': halka,
                         'count_field': c['count_field'],
                         'diameter_field': c['diameter_field'],
                         'ring_source': h_src})
    for m in eksik:
        beyan.append(m)
    # Eksenel yer: CAD kulvarının TEK kuralı (ÖH V3 CAD A1 · H8). Sayı ve
    # künye cümlesi oradan okunur; burada ikinci bir yerleşim yazılmaz.
    from hrma.export.cad_visualization import injector_plate_axial_span_mm
    x0, x1, yerlesim = injector_plate_axial_span_mm(t)
    dims['axial_position_mm'] = _dim(
        x0, 'assumed', rule='INJECTOR_PLATE_SEAT_RULE', basis=yerlesim)
    beyan.append(yerlesim)
    return {'id': pid, 't': float(t), 'x0': float(x0), 'x1': float(x1),
            'dims': dims, 'declared': beyan,
            'holes': delikler,
            'material': _malzeme(md, ('injector_results.plate_structural'
                                      '.material', 'injector_material'))}


def _tane_alanlari(md):
    """Tane boyu / port / dış çap — mm alanlarından (``resolve_grain_m`` düğüm
    sırası: önce ``motor_geometry``, sonra kök)."""
    sonuc = {}
    for kok in ('motor_geometry', ''):
        dugum = md.get(kok) if kok else md
        if not isinstance(dugum, dict):
            continue
        gd = dugum.get('grain_design')
        if not isinstance(gd, dict):
            continue
        onek = f'{kok}.grain_design' if kok else 'grain_design'
        for ad, adaylar in (('length', ('grain_length_mm',)),
                            ('port', ('port_diameter_initial_mm',
                                      'inner_diameter_mm')),
                            ('outer', ('grain_outer_diameter_mm',
                                       'outer_diameter_mm'))):
            if ad in sonuc:
                continue
            for a in adaylar:
                v = _pozitif(gd.get(a))
                if v is not None:
                    sonuc[ad] = (v, f'{onek}.{a}')
                    break
    return sonuc


def _tane(md, k, L, rc, kurallar, pid, kasa_id, x0_cozucu=None,
          x0_alan=None):
    """Tane (tek parça ya da BATES segmentleri). Döner ``(x0, x1)`` ya da
    ``None``."""
    from hrma.export.step_export import _grain_segment_plan
    alanlar = _tane_alanlari(md)
    eksik = [a for a in ('length', 'port', 'outer') if a not in alanlar]
    if eksik:
        k.cizilmez(pid, 'not_modelled',
                   'the grain geometry is not published: missing '
                   + ', '.join(eksik) + ' (grain_design.*_mm); no grain is '
                   'drawn in its place',
                   fields=['grain_design.grain_length_mm',
                           'grain_design.port_diameter_initial_mm',
                           'grain_design.outer_diameter_mm'])
        return None
    Lg, Lg_a = alanlar['length']
    dp, dp_a = alanlar['port']
    do, do_a = alanlar['outer']
    r_go, r_p = do / 2.0, dp / 2.0
    plan = _grain_segment_plan(md)
    yigin = plan['stack_mm'] if plan else Lg
    dims = {'grain_length_mm': _dim(Lg, 'solver', field=Lg_a, raw=Lg,
                                    unit='mm'),
            'port_diameter_mm': _dim(dp, 'solver', field=dp_a, raw=dp,
                                     unit='mm'),
            'outer_diameter_mm': _dim(do, 'solver', field=do_a, raw=do,
                                      unit='mm')}
    beyan = []
    # Boyut reddinde de yayımlanan ölçüler kayıtta kalır: eksenel bütçe
    # çizim durumundan bağımsız hesaplanır (denetçi Ş4).
    if r_go > rc:
        k.cizilmez(pid, 'not_modelled',
                   f'the grain outer diameter {do:.4g} mm is larger than the '
                   f'chamber bore {2 * rc:.4g} mm; the grain cannot be loaded '
                   'into its own case and is not drawn',
                   extra={'dims': dims, 'grain_stack_mm': yigin})
        return None
    if max(Lg, yigin) > L:
        k.cizilmez(pid, 'not_modelled',
                   f'the grain ({max(Lg, yigin):.4g} mm) is longer than its '
                   f'chamber ({L:.4g} mm); it is not shortened to fit',
                   extra={'dims': dims, 'grain_stack_mm': yigin})
        return None
    if x0_cozucu is not None:
        x0 = float(x0_cozucu)
        dims['axial_position_mm'] = _dim(
            x0, 'solver', field=x0_alan['field'], raw=x0_alan['raw'],
            unit=x0_alan['unit'],
            basis='grain front face = pre-combustion chamber length from '
                  'the injector face')
    else:
        frac, slack = kurallar['GRAIN_AXIAL_POSITION_RULE']
        x0 = min(frac * max(slack, L - yigin), L - yigin)
        dims['axial_position_mm'] = _dim(
            x0, 'assumed', rule='GRAIN_AXIAL_POSITION_RULE',
            basis=f'{frac:g} x max({slack:g} mm, chamber length - grain '
                  'stack)')
        beyan.append(f'axial position ASSUMED: front face at {x0:.4g} mm '
                     '(GRAIN_AXIAL_POSITION_RULE); no solver publishes it')
    if plan is not None and plan['n'] > 1:
        n, seg, gap = plan['n'], plan['segment_mm'], plan['gap_mm']
        dims['number_of_segments'] = {'value': n, 'source': {
            'kind': 'solver', 'field': 'grain_design.number_of_segments'}}
        dims['segment_length_mm'] = _dim(seg, 'solver',
                                         field='grain_design'
                                               '.segment_length_mm',
                                         raw=seg, unit='mm')
        gap_kod = plan.get('gap_source')
        # Denetçi Ş5(d): YAYIMLANMAYAN boşluk künyesi ne derse desin
        # not_modelled'dır (alan yokken 'user_input' künyesi kalmış olabilir;
        # ölçüldü: eski sıralama onu 'user' yazıyordu); yayımlıysa
        # user_input -> user, öteki kodlar -> solver.
        if not plan['gap_published']:
            gap_turu = 'not_modelled'
        elif gap_kod == 'user_input':
            gap_turu = 'user'
        else:
            gap_turu = 'solver'
        dims['segment_gap_mm'] = _dim(
            gap, gap_turu,
            field='grain_design.grain_gap_mm', raw=gap, unit='mm',
            solver_code=gap_kod)
        beyan.append(plan['source'])
        onceki = None
        for i in range(n):
            a = x0 + i * (seg + gap)
            sid = f'{pid}-{i + 1}'
            kayit = k.parca(pid, _dikdortgen(a, a + seg, r_p, r_go), dims,
                            declared=beyan,
                            name=f'grain_segment_{i + 1}_of_{n}',
                            material=_malzeme(md, ('propellant_type',
                                                   'fuel_type')))
            kayit['id'] = sid
            k.temas(sid, kasa_id, 'radial_gap', rc - r_go,
                    'bore radius - published grain outer radius')
            if onceki is not None:
                k.temas(onceki, sid, 'axial_gap', gap,
                        'inter-segment gap grain_design.grain_gap_mm')
            onceki = sid
        return x0, x0 + yigin
    if plan is None:
        gd = (md.get('grain_design') or {}) if isinstance(
            md.get('grain_design'), dict) else {}
        if gd.get('number_of_segments') is not None:
            beyan.append('grain_design.number_of_segments='
                         f'{gd.get("number_of_segments")} is published '
                         'without segment_length_mm, so the grain is drawn '
                         'as ONE piece (K-8)')
    k.parca(pid, _dikdortgen(x0, x0 + Lg, r_p, r_go), dims, declared=beyan,
            material=_malzeme(md, ('propellant_type', 'fuel_type')))
    k.temas(pid, kasa_id, 'radial_gap', rc - r_go,
            'bore radius - published grain outer radius')
    return x0, x0 + Lg


#: Katı kapak yalıtım bloklarının arandığı kökler (tam yanıt
#: ``cad_design.insulation_system``; düz gövde ``insulation_system``).
INSULATION_BLOCK_ROOTS = ('cad_design.insulation_system',
                          'insulation_system')
#: Kapak yalıtım bloğunda çözücünün GEREKÇE metnini taşıyan alanlar, okuma
#: sırasıyla. ``basis`` bloğun asıl gerekçesidir (çözücü Q* koşusunda
#: ``validity_note``'u ona gömer: ``solid_rocket_engine._ablative_liner_sizing``);
#: ``validity_note`` yalnız ``basis`` yoksa okunur.
INSULATION_BASIS_FIELDS = ('basis', 'validity_note')
#: Çözücünün "sıfır gerileme, kalınlık yayımlanmadı" hükmünün KENDİ
#: metnindeki işareti (``thermal_protection.ablative_thickness``
#: ``validity_note``). Plan bu işareti UYDURMAZ: yalnız çözücü metninde
#: varsa F-CAD-11'in yeniden tanımını yazar.
NO_NET_HEATING_MARKER = 'NO NET HEATING'
#: F-CAD-11'in NO NET HEATING hükmüne dayanan yeniden tanımı (rapor Kalem 7).
FCAD11_TRANSIENT_REDEFINITION = ('F-CAD-11 (transient conduction, criterion: '
                                 'back-face temperature limit, tool '
                                 'heat_sink_transient)')


def _kapak_yalitimi_gerekcesi(anahtar, blok, blok_yolu):
    """Kalınlığı yayımlanmayan kapak yalıtımının gerekçesi — ÇÖZÜCÜ METNİ.

    Denetçi Ş1 (fail-closed): plan çözücüye bir gerekçe ATFETMEZ. Metin
    bloğun kendi ``basis`` (yoksa ``validity_note``) alanından AYNEN
    aktarılır; metin yoksa "basis not published" denir. F-CAD-11'in geçici
    iletim yeniden tanımı YALNIZ çözücü metni NO NET HEATING hükmünü
    taşıyorsa yazılır; öteki dallarda kalem yalnız ``F-CAD-11``dir.

    Döner ``(neden, replaced_by, ek_alanlar)``.
    """
    on = f'{anahtar}.thickness is not published'
    if blok is None:
        return (on + f' (no {anahtar} block in this body; looked for '
                + ' / '.join(INSULATION_BLOCK_ROOTS) + ')',
                'F-CAD-11', {'solver_basis_field': None})
    durum = blok.get('thickness_status')
    for alan in INSULATION_BASIS_FIELDS:
        metin = blok.get(alan)
        if isinstance(metin, str) and metin.strip():
            kaynak = f'{blok_yolu}.{alan}'
            neden = (on + f' (thickness_status={durum!r}; solver text '
                     f'{kaynak}: "{metin}")')
            nnh = NO_NET_HEATING_MARKER in metin
            return (neden,
                    FCAD11_TRANSIENT_REDEFINITION if nnh else 'F-CAD-11',
                    {'solver_basis_field': kaynak,
                     'solver_no_net_heating': nnh})
    return (on + f' (thickness_status={durum!r}; basis not published: '
            + ' / '.join(f'{blok_yolu}.{a}' for a in INSULATION_BASIS_FIELDS)
            + ' carry no text)',
            'F-CAD-11', {'solver_basis_field': None})


def _kati_parcalar(md, k, L, rc, t_w, kurallar, kasa_id):
    tane = _tane(md, k, L, rc, kurallar, 'S05', kasa_id)
    # Isıl bariyer: kasa zinciri (layer_order) — alanlar ihraç gövdesinde
    # yoksa çizilmez (K-1 sınıfı kablolama devri).
    tb_yol = ('cad_design.insulation_system.thermal_barrier',
              'insulation_system.thermal_barrier')
    tb = None
    tb_alan = None
    for y in tb_yol:
        b, v = _yol(md, y)
        if b and isinstance(v, dict):
            tb, tb_alan = v, y
            break
    alanlar = _tane_alanlari(md)
    if tb is None:
        for pid in ('S06', 'S07'):
            k.cizilmez(pid, 'not_modelled',
                       'the liner / insulation thicknesses are not in this '
                       'body (looked for ' + ' / '.join(tb_yol) + '); the '
                       'solid export body (motor_geometry) does not carry '
                       'them', fields=list(tb_yol))
    elif 'outer' not in alanlar:
        for pid in ('S06', 'S07'):
            k.cizilmez(pid, 'not_modelled',
                       'the grain outer diameter is not published, so the '
                       'liner/insulation radii cannot be placed')
    else:
        r_go = alanlar['outer'][0] / 2.0
        t_li = _sonlu(tb.get('liner_thickness'))
        t_in = _sonlu(tb.get('thickness'))
        x0, x1 = (tane if tane else (0.0, L))
        # Astar tane dış yüzüne sarılır; yalıtım kasa iç yüzüne yapışır
        # (layer_order: grain, liner, insulation, case).
        for pid, t, alan, r0, r1 in (
                ('S06', t_li, f'{tb_alan}.liner_thickness', r_go,
                 None if t_li is None else r_go + t_li),
                ('S07', t_in, f'{tb_alan}.thickness',
                 None if t_in is None else rc - t_in, rc)):
            if t is None or t <= 0.0:
                k.cizilmez(pid, 'not_modelled',
                           f'{alan} is not a positive published thickness '
                           '(0 = no layer specified)', fields=[alan])
                continue
            k.parca(pid, _dikdortgen(x0, x1, r0, r1),
                    {'thickness_mm': _dim(t, 'user', field=alan, raw=t,
                                          unit='mm')},
                    declared=['axial extent = grain stack (the solver '
                              'publishes no separate layer length)'],
                    material=_malzeme(md, (f'{tb_alan}.material',)))
    # Kapak yalıtımları: gerekçe ÇÖZÜCÜNÜN KENDİ metninden (denetçi Ş1).
    for pid, anahtar in (('S08a', 'forward_insulation'),
                         ('S08b', 'aft_insulation')):
        blok = None
        blok_yolu = None
        for kok in INSULATION_BLOCK_ROOTS:
            b, v = _yol(md, f'{kok}.{anahtar}')
            if b and isinstance(v, dict):
                blok, blok_yolu = v, f'{kok}.{anahtar}'
                break
        if blok is not None and _pozitif(blok.get('thickness')) is not None:
            # Bugün hiçbir örnek yayımlamıyor; yayımlanırsa bile bu kademe
            # çizmez: kapak yalıtımı yerleşimi F-CAD-11 ile gelir.
            k.cizilmez(pid, 'new_calc_required',
                       f'{anahtar}.thickness is published but its placement '
                       'on the closure is F-CAD-11 work', replaced_by='F-CAD-11')
            continue
        neden, yerine, ek = _kapak_yalitimi_gerekcesi(anahtar, blok,
                                                     blok_yolu)
        k.cizilmez(pid, 'new_calc_required', neden, replaced_by=yerine,
                   fields=[f'{kok}.{anahtar}.thickness'
                           for kok in INSULATION_BLOCK_ROOTS],
                   extra=ek)
    k.cizilmez('S03', 'new_calc_required',
               'aft closure / nozzle retainer ring thickness and retaining '
               'ring groove are not sized (closure_joint not sized); a '
               'pressure-boundary thickness is never assumed (karar 1)',
               replaced_by='F-CAD-1')
    k.cizilmez('S04', 'not_modelled',
               'retaining ring table (DIN 472) is not in constants yet',
               replaced_by='F-CAD-1')
    k.cizilmez('S12', 'new_calc_required',
               'igniter case diameter/length are not published '
               '(igniter_case.material = NOT_DEFINED); only the charge '
               'volume is solved', replaced_by='F-CAD-12')
    k.cizilmez('S13', 'not_modelled',
               'seal table absent (Parker ORD 5700 / AS568 not in constants)',
               replaced_by='F-CAD-6')


def _hibrit_parcalar(md, k, L, rc, t_w, kurallar, kasa_id, plaka):
    # Ön oda boyu: çözücü yayımlıyorsa tane konumu ondan (B4 tersi: alan
    # VARKEN assumed yazılamaz). 0,0 / yok = yayımlanmadı -> ASSUMED kural.
    pre, pre_k = _uzunluk_mm(md, 'pre_chamber_length')
    post, post_k = _uzunluk_mm(md, 'post_chamber_length')
    tane = _tane(md, k, L, rc, kurallar, 'H07', kasa_id,
                 x0_cozucu=pre, x0_alan=pre_k if pre is not None else None)
    if pre is not None:
        k.bolge('H06', 0.0, pre, {'length_mm': _dim(
            pre, 'solver', field=pre_k['field'], raw=pre_k['raw'],
            unit=pre_k['unit'])})
    else:
        k.cizilmez('H06', 'not_modelled',
                   'pre_chamber_length is not published (0.0 / absent is '
                   'read as not published)', fields=['pre_chamber_length'])
    if post is not None:
        k.bolge('H08', L - post, L, {'length_mm': _dim(
            post, 'solver', field=post_k['field'], raw=post_k['raw'],
            unit=post_k['unit'])})
    else:
        k.cizilmez('H08', 'not_modelled',
                   'post_chamber_length is not published',
                   fields=['post_chamber_length'])
    # Astar: çözücünün kendi tanımıyla tanenin ÖRTMEDİĞİ kesimler.
    tl, tl_a = _ilk_alan(md, ('thermal_protection.chamber_liner.thickness',))
    blok_ok, cl = _yol(md, 'thermal_protection.chamber_liner')
    if tl is None or tane is None:
        for pid in ('H09a', 'H09b'):
            k.cizilmez(pid, 'not_modelled',
                       'chamber liner thickness is not published '
                       '(thermal_protection.chamber_liner.thickness)'
                       if tl is None else
                       'the grain is not placed, so the liner sections '
                       '(outside the grain) cannot be placed',
                       fields=['thermal_protection.chamber_liner.thickness'])
    else:
        x0, x1 = tane
        mal = _malzeme(md, ('thermal_protection.chamber_liner.material',))
        dims = {'thickness_mm': _dim(
            tl, 'solver', field=tl_a, raw=tl, unit='mm',
            solver_code=(cl or {}).get('thickness_status'))}
        # Ön oda astarı plakanın arka yüzünden başlar (plaka [x0p, x1p]
        # kapak iç yüzüne oturur, CAD H8); plaka yoksa x = 0'dan.
        on_bas = plaka['x1'] if plaka is not None else 0.0
        for pid, a, b in (('H09a', on_bas, x0), ('H09b', x1, L)):
            if b - a <= 0.0:
                k.cizilmez(pid, 'not_modelled',
                           'no chamber section outside the grain here')
                continue
            k.parca(pid, _dikdortgen(a, b, rc - tl, rc), dims,
                    declared=['liner covers the chamber section NOT '
                              'shielded by fuel (solver chamber_liner'
                              '.function); outer face = chamber bore'],
                    material=mal)
            k.temas(pid, kasa_id, 'radial_face', 0.0,
                    'liner outer face on the chamber bore')
            if any(p['id'] == 'H07' for p in k.parts):
                k.temas(pid, 'H07', 'axial_face', 0.0,
                        'liner section ends where the grain begins/ends')
        if plaka is not None and any(p['id'] == 'H09a' for p in k.parts):
            k.temas(plaka['id'], 'H09a', 'axial_face', 0.0,
                    'pre-chamber liner starts at the injector plate aft '
                    'face')
    nel_ok, nel = _yol(md, 'thermal_protection.nozzle_entry_liner')
    k.cizilmez('H09c', 'not_modelled',
               'nozzle_entry_liner thickness is not published'
               + (f' (thickness_status={nel.get("thickness_status")!r})'
                  if isinstance(nel, dict) else ''),
               fields=['thermal_protection.nozzle_entry_liner.thickness'])
    if plaka is None and not any(n['id'] == 'H04'
                                 for n in k.not_modelled):
        k.cizilmez('H04', 'new_calc_required',
                   'manifold dome is not sized and no injector plate is '
                   'placed', replaced_by='F-CAD-7')
    k.cizilmez('H05', 'not_modelled',
               'oxidizer inlet line diameter is not published '
               '(not_modelled.feed_system = NOT_MODELLED); no port is cut',
               fields=['not_modelled.feed_system'])
    k.cizilmez('H12', 'new_calc_required',
               'nozzle retainer flange thickness is not sized (UG-34 bolt '
               'moment term); a pressure-boundary thickness is never assumed '
               '(karar 1)', replaced_by='F-CAD-2')
    k.cizilmez('H13', 'not_modelled',
               'seal table absent (Parker ORD 5700 / AS568 not in constants)',
               replaced_by='F-CAD-6')
    ig_ok, ig = _yol(md, 'igniter_sizing')
    k.cizilmez('H15', 'not_modelled',
               'igniter_sizing.status = '
               + repr((ig or {}).get('status') if isinstance(ig, dict)
                      else None)
               + '; no port is cut (a hole is a part)',
               fields=['igniter_sizing.status'])


def _sivi_parcalar(md, k, L, rc, t_w, kurallar, kasa_id, plaka):
    if plaka is None and not any(n['id'] == 'L02' for n in k.not_modelled):
        k.cizilmez('L02', 'new_calc_required',
                   'oxidizer manifold dome is not sized (manifold pressure '
                   '= chamber pressure + injector pressure drop, UG-32)',
                   replaced_by='F-CAD-7')
    k.cizilmez('L03', 'new_calc_required',
               'fuel manifold ring is not sized', replaced_by='F-CAD-7')
    k.cizilmez('L04', 'not_modelled',
               'propellant inlet stubs: the line diameter is solved '
               '(feed_system) but no stub length / wall / flange is '
               'published; feed-line CAD is BS-7', replaced_by='BS-7')
    kanal_ok, kanal = _yol(md, 'cooling_channels')
    k.cizilmez('L06', 'new_calc_required',
               'regenerative channels are not drawn: the fit criterion '
               '(F-17 regen_cooling.channel_fit_limit) is not in the '
               'codebase yet and the channel solid is F-18b'
               + ('' if isinstance(kanal, dict) else
                  '; this body carries no cooling_channels block'),
               replaced_by='F-17 + F-18b (cm-1b-kanal)',
               fields=['cooling_channels'])
    k.cizilmez('L07', 'new_calc_required',
               'cooling jacket wall is not sized (coolant-pressure hoop); a '
               'pressure-boundary thickness is never assumed (karar 1)',
               replaced_by='F-CAD-8')
    k.cizilmez('L08', 'new_calc_required',
               'coolant inlet/outlet manifolds are not sized',
               replaced_by='F-CAD-8')
    ct_ok, ct = _yol(md, 'cooling_type')
    k.cizilmez('L09', 'not_modelled',
               (f'cooling_type = {ct!r}: an ablative liner applies only to '
                'a non-regenerative chamber' if isinstance(ct, str) else
                'cooling_type is not in this body; ablative liner thickness '
                'is not published'), fields=['cooling_type'])
    k.cizilmez('L12', 'new_calc_required',
               'head-end / nozzle-end flange thickness is not sized (UG-34 '
               'bolt moment term); bolt count not sized', replaced_by='F-CAD-2')
    k.cizilmez('L13', 'not_modelled',
               'engine_mount / gimbal_range are inputs the solver does not '
               'read; no mount is drawn')
    k.cizilmez('L14', 'not_modelled',
               'ignition system is NOT_MODELLED (non-hypergolic); no port is '
               'cut')


def _lule(md, k, L, rc, t_w, kurallar, kasa_id):
    """Lüle gövdesi: iç kontur tek kaynaktan, et yayımlanmış ya da ADLI
    istisna kuralı (katı/sıvı)."""
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    from hrma.export.motor_geometry import normalise_export_geometry
    pid = {'solid': 'S09', 'hybrid': 'H10', 'liquid': 'L10'}[k.motor_type]
    ek_id = {'solid': 'S10', 'hybrid': 'H11', 'liquid': None}[k.motor_type]
    Dt, Dt_k = _uzunluk_mm(md, 'throat_diameter')
    De, De_k = _uzunluk_mm(md, 'exit_diameter')
    if Dt is None or De is None:
        k.cizilmez(pid, 'not_modelled',
                   'throat / exit diameter could not be resolved; no nozzle '
                   'is drawn on a generator fallback throat',
                   fields=['throat_diameter', 'exit_diameter'])
    else:
        md_n, _rap = normalise_export_geometry(md)
        try:
            pts, meta = sample_nozzle_inner_contour(
                md_n, require_solved_length=True)
        except ValueError as exc:
            k.cizilmez(pid, 'not_modelled',
                       f'nozzle contour refused: {exc}')
            pts = None
        if pts is not None:
            geo_ok, ng = _yol(md, 'nozzle_geometry')
            et = _pozitif((ng or {}).get('wall_thickness')) \
                if isinstance(ng, dict) else None
            beyan = []
            if et is not None:
                et_dim = _dim(et, 'solver',
                              field='nozzle_geometry.wall_thickness', raw=et,
                              unit='mm',
                              solver_code=(ng or {}).get(
                                  'wall_thickness_basis'))
            else:
                en_az, oran = kurallar['NOZZLE_WALL_GENERATOR_RULE']
                throat_m = md_n.get('throat_diameter')
                # STEP ile AYNI ifade (bit-aynı: step_export wall_noz).
                et = max(en_az, oran * float(throat_m) * 1000)
                et_dim = _dim(et, 'assumed',
                              rule='NOZZLE_WALL_GENERATOR_RULE',
                              basis=f'max({en_az:g} mm, {oran:g} x throat '
                                    'diameter)')
                beyan.append(ASSUMED_RULES['NOZZLE_WALL_GENERATOR_RULE']
                             ['text'])
            ic = [(L + float(z), float(r)) for z, r in pts]
            dis = [(x, r + et) for x, r in reversed(ic)]
            dims = {'wall_thickness_mm': et_dim,
                    'throat_diameter_mm': _dim(Dt, 'solver',
                                               field=Dt_k['field'],
                                               raw=Dt_k['raw'],
                                               unit=Dt_k['unit']),
                    'exit_diameter_mm': _dim(De, 'solver',
                                             field=De_k['field'],
                                             raw=De_k['raw'],
                                             unit=De_k['unit']),
                    'divergent_length_mm': {
                        'value': float(meta['divergent_length_mm']),
                        'source': {'kind': 'solver',
                                   'basis': str(
                                       meta['divergent_length_source'])}},
                    'convergent_length_mm': {
                        'value': float(meta['z_throat']),
                        'source': {'kind': 'solver',
                                   'basis': 'sample_nozzle_inner_contour '
                                            '(single contour source)'}}}
            beyan.append('inner contour = sample_nozzle_inner_contour (the '
                         'one contour source of STEP/STL/DXF/scene); outer '
                         'surface = inner radius + wall (radial offset, as '
                         'the STEP draws it)')
            if k.motor_type == 'solid':
                beyan.append('exit cone is part of this housing (S11 is not a '
                             'separate part)')
            if k.motor_type == 'liquid':
                beyan.append('convergent/throat (L10) and bell (L11) are one '
                             'housing: no joint is published between them')
            mal = _malzeme(md, ('nozzle_geometry.wall_material',
                                'nozzle_design.material_key',
                                'nozzle_material'))
            k.parca(pid, ic + dis, dims, declared=beyan, material=mal)
            k.temas(kasa_id, pid, 'axial_face', 0.0,
                    'nozzle entry face on the tube aft face (x = chamber '
                    'length)')
    if ek_id is not None:
        k.cizilmez(ek_id, 'new_calc_required',
                   'throat insert thickness is not sized (thermal + erosion '
                   '+ Lamé); a pressure-boundary thickness is never assumed '
                   '(karar 1); single-piece vs housing + insert is karar 9',
                   replaced_by='F-CAD-4')


def _baglanti_elemanlari(md, k, rc):
    """Cıvatalar/contalar: sayı ve yerleşim künyesi — bugün çizilmez."""
    pid = {'solid': 'S14', 'hybrid': 'H14', 'liquid': 'L15'}[k.motor_type]
    fa_ok, fa = _yol(md, 'structural_analysis.fastener_analysis')
    bj = None
    for y in ('bolted_joint', 'closure_joint.bearing',
              'structural_analysis.closure_joint.bearing',
              'structural_analysis.assembly_integrity.closure_joint.bearing'):
        b, v = _yol(md, y)
        if b and isinstance(v, dict) and \
                _pozitif(v.get('clearance_hole_diameter_mm')) is not None:
            bj = (y, v)
            break
    extra = {}
    if isinstance(fa, dict):
        n = fa.get('num_bolts')
        rbc = _pozitif(fa.get('bolt_circle_radius'))
        extra['bolt_plan_published'] = {
            'num_bolts': n, 'num_bolts_field':
                'structural_analysis.fastener_analysis.num_bolts',
            'recommended_bolt_size': fa.get('recommended_bolt_size'),
            'bolt_circle_radius_mm': _dim(
                rbc, 'assumed',
                field='structural_analysis.fastener_analysis'
                      '.bolt_circle_radius', raw=rbc, unit='mm',
                rule='STRUCTURAL_BOLT_CIRCLE_RADIUS_RULE',
                basis=ASSUMED_RULES['STRUCTURAL_BOLT_CIRCLE_RADIUS_RULE']
                ['text']) if rbc is not None else None,
            'bolt_circle_offset_from_bore_mm':
                (rbc - rc) if rbc is not None else None}
    ec_ok, ec = _yol(md, 'structural_analysis.end_cap_analysis')
    if isinstance(ec, dict) and _pozitif(ec.get('bolt_circle_diameter')):
        dbc = float(ec['bolt_circle_diameter'])
        extra['end_cap_bolt_circle_diameter_mm'] = _dim(
            dbc, 'assumed',
            field='structural_analysis.end_cap_analysis.bolt_circle_diameter',
            raw=dbc, unit='mm', rule='STRUCTURAL_BOLT_CIRCLE_DIAMETER_RULE',
            basis=ASSUMED_RULES['STRUCTURAL_BOLT_CIRCLE_DIAMETER_RULE']
            ['text'])
        extra['end_cap_bolt_circle_offset_from_bore_mm'] = dbc - 2.0 * rc
    cj = None
    for y in ('closure_joint', 'structural_analysis.closure_joint',
              'structural_analysis.assembly_integrity.closure_joint'):
        b, v = _yol(md, y)
        if b and isinstance(v, dict):
            cj = (y, v)
            break
    if cj is not None:
        extra['closure_joint'] = {'field': cj[0],
                                  'status': cj[1].get('status'),
                                  'bolt_count': cj[1].get('bolt_count')}
    neden = ('bolts are not drawn: '
             + ('no clearance-hole diameter is published '
                '(bolted_joint(.bearing).clearance_hole_diameter_mm)'
                if bj is None else
                f'the clearance hole is published at {bj[0]}')
             + '; the flanges they pass through need F-CAD-2; the published '
               'bolt circle is a fixed layout rule, not a dimension '
               '(hakem #4)')
    k.cizilmez(pid, 'not_modelled', neden, replaced_by='F-CAD-2 / F-CAD-3',
               extra=extra)


# ---------------------------------------------------------------------------
# Denetimler ve son biçim
# ---------------------------------------------------------------------------
def _ek_gruplar(k, extra_groups):
    """``extra_groups`` şemasını doğrular ve parçaları plana ekler."""
    if extra_groups is None:
        return []
    if not isinstance(extra_groups, (list, tuple)):
        raise AssemblyPlanError('extra_groups must be a list of '
                                '{group, parts} objects')
    eklenen = []
    mevcut = {p['id'] for p in k.parts} | {n['id'] for n in k.not_modelled}
    for g in extra_groups:
        if not isinstance(g, dict) or not isinstance(g.get('group'), str):
            raise AssemblyPlanError('each extra group needs a string '
                                    '"group"')
        grup = g['group']
        try:
            numara = int(grup.split('_', 1)[0])
        except ValueError:
            raise AssemblyPlanError(f'extra group {grup!r} must start with a '
                                    'two-digit number and an underscore')
        if numara < EXTRA_GROUP_MIN_NUMBER or grup in GROUPS:
            raise AssemblyPlanError(
                f'extra group {grup!r} collides with the motor groups '
                f'(extra groups start at {EXTRA_GROUP_MIN_NUMBER})')
        for p in g.get('parts') or ():
            if not isinstance(p, dict):
                raise AssemblyPlanError('extra part must be an object')
            pid = p.get('id')
            if not isinstance(pid, str) or pid in mevcut:
                raise AssemblyPlanError(f'extra part id {pid!r} is missing '
                                        'or not unique')
            rol = p.get('role')
            if rol not in ROLE_COLORS:
                raise AssemblyPlanError(f'extra part {pid!r} role {rol!r} '
                                        'is not in ROLE_COLORS')
            geo = p.get('geometry') or {}
            prof = geo.get('profile_rz_mm')
            if geo.get('kind') != 'revolve' or not isinstance(prof, list) \
                    or len(prof) < 3:
                raise AssemblyPlanError(f'extra part {pid!r} needs a '
                                        'revolve profile_rz_mm')
            for d in (p.get('dims') or {}).values():
                if (d.get('source') or {}).get('kind') not in SOURCE_KINDS:
                    raise AssemblyPlanError(f'extra part {pid!r} has a dim '
                                            'with an unknown source kind')
            kayit = dict(p)
            kayit['geometry'] = dict(geo)
            eksen = kayit['geometry'].setdefault('profile_axes',
                                                 list(PROFILE_AXES))
            if list(eksen) != list(PROFILE_AXES):
                raise AssemblyPlanError(f'extra part {pid!r} profile_axes '
                                        f'must be {list(PROFILE_AXES)}')
            kayit['group'] = grup
            kayit['drawn'] = True
            kayit['color'] = ROLE_COLORS[rol]
            kayit.setdefault('declared', [])
            kayit['bbox_mm'] = _kutu(prof)
            k.parts.append(kayit)
            mevcut.add(pid)
            eklenen.append(pid)
    return eklenen


#: Çapasız planda (``status: not_drawable``) ek parçanın düşme nedeni.
NOT_ANCHORED_REASON = ('plan not anchored: chamber length, chamber bore and '
                       'chamber wall are not all published (see '
                       'invalid_fields), so this extra part is not placed '
                       'next to a motor that is not drawn and is not '
                       'checked for interference')


def _capasiz_ek_parcalar(k, ek_kimlikler):
    """Çapasız planda ``extra_groups`` parçalarını ``not_modelled``'a taşır."""
    if not ek_kimlikler:
        return
    ek = set(ek_kimlikler)
    kalan = []
    for p in k.parts:
        if p['id'] not in ek:
            kalan.append(p)
            continue
        k.not_modelled.append({
            'id': p['id'], 'name': p.get('name'), 'group': p['group'],
            'role': p['role'], 'class': 'not_anchored',
            'kind': 'not_modelled', 'reason': NOT_ANCHORED_REASON,
            'geometry_not_drawn': p['geometry'],
            'dims': p.get('dims') or {}})
    k.parts = kalan


def _girisim(k, tol):
    """Çift çift örtüşme; düşük öncelikli parça çizilmez (eşitte ikisi)."""
    cizilen = list(k.parts)
    ciftler = []
    dusur = {}
    for i in range(len(cizilen)):
        for j in range(i + 1, len(cizilen)):
            a, b = cizilen[i], cizilen[j]
            ka, kb = a['bbox_mm'], b['bbox_mm']
            if (ka['x_mm'][1] <= kb['x_mm'][0] or kb['x_mm'][1] <= ka['x_mm'][0]
                    or ka['r_mm'][1] <= kb['r_mm'][0]
                    or kb['r_mm'][1] <= ka['r_mm'][0]):
                continue
            o = section_overlap(a['geometry']['profile_rz_mm'],
                                b['geometry']['profile_rz_mm'])
            if o['depth_mm'] <= tol:
                continue
            pa = ROLE_PRIORITY.get(a['role'], 0)
            pb = ROLE_PRIORITY.get(b['role'], 0)
            kaybeden = ([a] if pa < pb else [b] if pb < pa else [a, b])
            ciftler.append({'a': a['id'], 'b': b['id'],
                            'overlap_area_mm2': o['area_mm2'],
                            'penetration_mm': o['depth_mm'],
                            'overlap_x_mm': o['x_mm'], 'overlap_r_mm': o['r_mm'],
                            'not_drawn': [x['id'] for x in kaybeden]})
            for x in kaybeden:
                dusur.setdefault(x['id'], []).append(
                    (b if x is a else a)['id'])
    if dusur:
        kalan = []
        for p in k.parts:
            if p['id'] in dusur:
                diger = ', '.join(dusur[p['id']])
                k.not_modelled.append({
                    'id': p['id'], 'name': p['name'], 'group': p['group'],
                    'role': p['role'], 'class': 'interference',
                    'kind': 'not_modelled',
                    'reason': (f'interferes with {diger} by more than the '
                               f'{tol:g} mm assembly tolerance; the part is '
                               'not drawn (fail-closed, the file is still '
                               'produced)'),
                    'geometry_not_drawn': p['geometry'],
                    'dims': p['dims']})
            else:
                kalan.append(p)
        k.parts = kalan
    return ciftler


def _temas_denetimi(k, tol):
    """Beyan edilen temasların ölçülen boşluğu beyana eşit mi?"""
    profil = {p['id']: p['geometry']['profile_rz_mm'] for p in k.parts}
    sonuc = []
    for c in k.contacts:
        if c['a'] not in profil or c['b'] not in profil:
            c = dict(c, measured_gap_mm=None, ok=None,
                     note='a party is not drawn')
            sonuc.append(c)
            continue
        olcum = section_distance(profil[c['a']], profil[c['b']])
        c = dict(c, measured_gap_mm=olcum,
                 ok=abs(olcum - c['gap_mm']) <= tol)
        sonuc.append(c)
    return sonuc


def _yayimlanan_olculer(k, taban_id):
    """Parçanın YAYIMLANAN ölçüleri, çizim durumundan bağımsız (Ş4).

    Önce çizilen parça (segmentlerde ilk çizilen), yoksa ``not_modelled``
    kaydının ``dims``'i (girişimle düşen ya da boyutça reddedilen parça).
    Döner ``(dims | None, çizilmeyen kayıtlar)``; ölçü hiç yayımlanmadıysa
    ``dims`` None'dır.
    """
    cizilen = _cizilen_parcalar(k, taban_id)
    dusen = [n for n in k.not_modelled if n['id'].split('-')[0] == taban_id]
    if cizilen:
        return cizilen[0]['dims'], dusen
    for n in dusen:
        if isinstance(n.get('dims'), dict) and n['dims']:
            return n['dims'], dusen
    return None, dusen


def _cizilen_parcalar(k, taban_id):
    """``taban_id`` kimlikli (segmentlerde ``taban_id-i``) ÇİZİLEN parçalar."""
    return [p for p in k.parts if p['id'].split('-')[0] == taban_id]


def _dusme_nedeni(ad, dusen, cizilen=()):
    """Bütçe terimi çizilmediyse kısa neden.

    Terimin tamamı düştüyse ``grain not drawn (...)``. Segmentlerin YALNIZ
    bir kısmı düştüyse (denetçi-2 notu, 3. tur) düşen ve çizilen kimlikler
    adıyla yazılır: ``grain partly not drawn: S05-2 (interference); drawn:
    S05-1, S05-3`` — "tane çizilmedi" denip çizili segmentler gizlenmez.
    Kimlik sırası parça sırasıdır (segment sırası).
    """
    if not dusen:
        return None
    siniflar = sorted({('interference' if n.get('class') == 'interference'
                        else 'rejected: ' + n['id']) for n in dusen})
    if cizilen:
        return (f'{ad} partly not drawn: '
                + ', '.join(n['id'] for n in dusen)
                + f' ({", ".join(siniflar)}); drawn: '
                + ', '.join(p['id'] for p in cizilen))
    return f'{ad} not drawn ({", ".join(siniflar)})'


def _eksenel_butce(k, tol):
    """Hibrit: pre + tane + post == L; katı: yığın ≤ L. Döner sözlük.

    Denetçi Ş4: terimler çizim durumundan BAĞIMSIZ, yayımlanan ölçülerden
    kurulur. Tane girişimle düştüyse bile artık hesaplanır ve ``reason``
    ``grain not drawn (interference); residual = … mm`` der; artık ≠ 0 ise
    ``ok`` False'tur (tutarsızlık "terim yayımlanmadı" diye gizlenmez).
    """
    kasa_id = {'solid': 'S01', 'hybrid': 'H01', 'liquid': 'L05'}[k.motor_type]
    kasa, _d = _yayimlanan_olculer(k, kasa_id)
    if kasa is None or 'chamber_length_mm' not in kasa:
        return None
    L = kasa['chamber_length_mm']['value']
    if k.motor_type == 'hybrid':
        kural = 'pre + grain + post == chamber length'
        pre = next((r for r in k.regions if r['id'] == 'H06'), None)
        post = next((r for r in k.regions if r['id'] == 'H08'), None)
        tane, dusen = _yayimlanan_olculer(k, 'H07')
        eksik = [ad for ad, v in (('pre_chamber_length', pre),
                                  ('grain_design.grain_length_mm', tane),
                                  ('post_chamber_length', post)) if v is None]
        if eksik:
            return {'rule': kural, 'ok': None,
                    'reason': 'a term is not published: ' + ', '.join(eksik)}
        g = tane['grain_length_mm']['value']
        toplam = (pre['dims']['length_mm']['value'] + g
                  + post['dims']['length_mm']['value'])
        sonuc = {'rule': kural,
                 'sum_mm': toplam, 'chamber_length_mm': L,
                 'residual_mm': toplam - L, 'ok': abs(toplam - L) <= tol}
        neden = _dusme_nedeni('grain', dusen, _cizilen_parcalar(k, 'H07'))
        if neden is not None:
            sonuc['reason'] = f'{neden}; residual = {toplam - L:+.4f} mm'
        return sonuc
    if k.motor_type == 'solid':
        kural = 'grain stack <= chamber length'
        tane, dusen = _yayimlanan_olculer(k, 'S05')
        if tane is None:
            return {'rule': kural, 'ok': None,
                    'reason': 'grain not published'}
        if 'segment_length_mm' in tane and 'number_of_segments' in tane:
            # _grain_segment_plan ile AYNI ifade (stack_mm).
            n = tane['number_of_segments']['value']
            yigin = (n * tane['segment_length_mm']['value']
                     + (n - 1) * tane['segment_gap_mm']['value'])
        else:
            kayit = next((d for d in dusen if 'grain_stack_mm' in d), None)
            yigin = (float(kayit['grain_stack_mm']) if kayit is not None
                     else tane['grain_length_mm']['value'])
        sonuc = {'rule': kural,
                 'stack_mm': yigin, 'chamber_length_mm': L,
                 'free_mm': L - yigin, 'ok': yigin <= L + tol}
        neden = _dusme_nedeni('grain', dusen, _cizilen_parcalar(k, 'S05'))
        if neden is not None:
            sonuc['reason'] = f'{neden}; free = {L - yigin:+.4f} mm'
        return sonuc
    return {'rule': 'no propellant grain in a liquid engine', 'ok': None}


def _delik_denetimi(k):
    sonuc = []
    for p in k.parts:
        for h in (p['geometry'].get('holes') or ()):
            r_dis = p['bbox_mm']['r_mm'][1]
            aralik = (2.0 * math.pi * h['ring_r_mm'] / h['n']
                      if h['n'] > 0 else None)
            sonuc.append({
                'part': p['id'], 'circuit': h['circuit'],
                'inside_plate': h['ring_r_mm'] + h['d_mm'] / 2.0 <= r_dis,
                'pitch_mm': aralik,
                'holes_do_not_overlap': (aralik is not None
                                         and aralik > h['d_mm'])})
    return sonuc


def _bitir(k, md, motor_type, injector_supplied, extra_groups, status):
    from hrma.export.cad_visualization import _MONTAJ_GIRISIM_TOLERANS_MM
    from hrma.export.motor_geometry import EXPORT_AXIS, EXPORT_AXIS_NOTE
    tol = float(_MONTAJ_GIRISIM_TOLERANS_MM)
    ek = _ek_gruplar(k, extra_groups)
    if status != 'ok':
        # Denetçi Ş3: çapasız planda ek parça da ÇİZİLMEZ (şema yine
        # doğrulandı; biçim hatası yine AssemblyPlanError).
        _capasiz_ek_parcalar(k, ek)
    ciftler = _girisim(k, tol) if status == 'ok' else []
    temaslar = _temas_denetimi(k, tol)
    butce = _eksenel_butce(k, tol) if status == 'ok' else None
    # Lüle girişinde kasa dış yarıçapını aşma (K-3; girişim değil, bildirim).
    kasa = next((p for p in k.parts if p['id'] in ('S01', 'H01', 'L05')),
                None)
    lule = next((p for p in k.parts if p['id'] in ('S09', 'H10', 'L10')),
                None)
    tasma = None
    if kasa and lule:
        L = kasa['dims']['chamber_length_mm']['value']
        r_kasa = kasa['bbox_mm']['r_mm'][1]
        giris = [r for x, r in lule['geometry']['profile_rz_mm'] if x == L]
        if giris:
            tasma = max(giris) - r_kasa
    kontroller = {
        'tolerance_mm': tol,
        'interference_pairs': ciftler,
        'contacts_ok': (all(c['ok'] for c in temaslar if c['ok'] is not None)
                        if temaslar else None),
        'axial_budget': butce,
        'axial_budget_ok': (butce or {}).get('ok'),
        'channel_fit_ok': None,
        'channel_fit_basis': ('F-17 regen_cooling.channel_fit_limit is not in '
                              'the codebase; channels are not drawn'
                              if motor_type == 'liquid' else
                              'no cooling channels in this motor type'),
        'holes': _delik_denetimi(k),
        'nozzle_entry_overhang_mm': tasma,
    }
    parts = sorted(k.parts, key=lambda p: (p['group'], p['id']))
    plan = {
        'schema': SCHEMA_ID,
        'motor_type': motor_type,
        'unit': PLAN_UNIT,
        'axis': f'+{EXPORT_AXIS}, x=0 injector face',
        'axis_note': EXPORT_AXIS_NOTE,
        'generator': GENERATOR_ID,
        'status': status,
        'parts': parts,
        'not_modelled': sorted(k.not_modelled, key=lambda n: n['id']),
        'regions': k.regions,
        'contacts': temaslar,
        'checks': kontroller,
        'inputs': {'injector_supplied': bool(injector_supplied),
                   'extra_parts': ek,
                   'motor_name': md.get('motor_name')},
        'assumed_rules_used': sorted(_kullanilan_kurallar(parts)),
    }
    if k.invalid_fields:
        plan['invalid_fields'] = k.invalid_fields
    plan['plan_signature'] = plan_signature(parts)
    json.dumps(plan, allow_nan=False)  # NaN sızarsa burada patlar
    return plan


def _kullanilan_kurallar(parts):
    kural = set()

    def _gez(o):
        if isinstance(o, dict):
            if o.get('kind') == 'assumed' and isinstance(o.get('rule'), str):
                kural.add(o['rule'])
            for v in o.values():
                _gez(v)
        elif isinstance(o, list):
            for v in o:
                _gez(v)
    _gez(parts)
    return kural


def plan_table_rows(plan):
    """Sayısal yerleşim tablosu satırları (kanıt ve DXF ölçü listesi için)."""
    satirlar = []
    for p in plan['parts']:
        kaynaklar = sorted({d['source']['kind'] for d in p['dims'].values()
                            if isinstance(d, dict) and 'source' in d})
        satirlar.append({'id': p['id'], 'name': p['name'],
                         'group': p['group'],
                         'x_mm': p['bbox_mm']['x_mm'],
                         'r_mm': p['bbox_mm']['r_mm'],
                         'source_kinds': kaynaklar})
    return satirlar
