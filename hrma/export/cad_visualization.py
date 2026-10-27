"""
3D CAD Visualization Module for Hybrid Rocket Motors
Combines motor assembly visualization (MotorCADDesigner) and
detailed engineering cross-section views (DetailedCADGenerator).

Both classes use Plotly for interactive 3D rendering.
MotorCADDesigner also uses trimesh for mesh-based geometry.
"""

import numpy as np
import trimesh

from hrma.constants import G_0
from hrma.data.materials_db import get_material
from hrma.utils.input_guard import finite_number, finite_positive
from hrma.engines.nozzle_design import (
    NOZZLE_CONTOUR_FIELD, NOZZLE_CONTOUR_REASONS, sample_nozzle_inner_contour)
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Tuple, Optional
import json
import base64
import math
from io import BytesIO


# =============================================================================
# MotorCADDesigner - 3D Motor Assembly (trimesh + Plotly)
# Originally from cad_design.py
# =============================================================================

def _real_nested(d, path):
    """İç içe dict'ten sonlu pozitif float çek (yoksa None)."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return finite_positive(cur)


# ---------------------------------------------------------------------------
# Çıktı etiketleri — TEK tanım noktası (CLAUDE.md kural 11).
# Bir imalat değeri çözücüden gelmiyorsa sabit sayı UYDURULMAZ; alan bu
# metinle işaretlenir, kullanıcı neyin hesaplanmadığını görür.
# ---------------------------------------------------------------------------
NOT_AVAILABLE_SPEC = 'NOT AVAILABLE - not produced by this analysis run'

# Yapısal analiz yoksa 3B mesh ve kütle hesabı AYNI yedek cidar kuralını
# kullanır (görsel ile kütlenin çelişmemesi için tek sabit).
CHAMBER_WALL_FALLBACK_FRACTION = 0.045  # cidar / kamara çapı

# 3B mesh üretiminde delik sayısı üst sınırı (boolean kararlılığı). YALNIZ
# mesh için geçerlidir; teknik çizim ve spesifikasyon çıktısı gerçek sayıyı
# yazar (bkz. _injector_spec).
MESH_MAX_INJECTOR_ORIFICES = 16

# ---------------------------------------------------------------------------
# ÖH Z5S (defter P9B1-05). Kamara boyunun ÇİZİLEBİLİR kabul bandı [m].
#
# Kusur: bant DIŞINDAKİ boy sessizce atılıp yerine L* kuralından türetilen ve
# ardından ``max(0.3, min(2.0, ...))`` ile KELEPÇELENEN bir sayı çiziliyordu.
# Ölçüldü (27 Ağustos 2026, hibrit 5 kN): ``chamber_length = 5.0 m``,
# ``= 0.015 m`` ve "alan hiç yok" — ÜÇÜ DE aynı 300 mm'lik kamarayı çizdi
# (mesh z aralığı -0.0148 .. 0.3000 m). Kullanıcının 5 m'lik girdisiyle
# girdisizlik ayırt edilemiyordu; çizim, STL ve kütle bu uydurma boydandı.
#
# Bant artık TEK yerde tanımlıdır ve hem doğrudan okunan hem L*'tan türetilen
# hem de kullanıcının override ettiği boy AYNI banda tabidir. Bandın dışına
# düşen değer KELEPÇELENMEZ: ihraç adlandırılmış bir hatayla durur.
#: İhracatın KENDİ üst sınırı [m]. Doğrulayıcının bandı (20 m) daha geniştir;
#: mesh/Plotly ölçeğinde bundan uzun bir gövde çizilmez.
CHAMBER_LENGTH_MAX_M = 5.0

#: Doğrulayıcının bandı okunamazsa kullanılacak alt sınır [m].
CHAMBER_LENGTH_MIN_FALLBACK_M = 0.02


def _dogrulayici_bandi_m(alan):
    """``MotorDataValidator.limits`` içindeki METRE bandı, ya da ``None``.

    Tek tanım noktası doğrulayıcıdır (CLAUDE.md kural 11); burada bandın
    KOPYASI tutulmaz.
    """
    try:
        from hrma.validation.motor_validation import MotorDataValidator
        band = MotorDataValidator().limits.get(alan)
        if isinstance(band, dict) and band.get('unit') == 'm':
            return float(band['min']), float(band['max'])
    except Exception:                                    # pragma: no cover
        return None
    return None


#: Çizilebilir kamara boyunun ALT sınırı [m] — UÇ DÂHİL.
#:
#: ÖH D26 / OH-Z5-12. Buraya 0,02 yazılıydı ve bu sayı ULAŞILAMAZDI:
#: ihracat girdiyi okumadan önce birim çözümü (``motor_geometry``) çalışır ve
#: o katman doğrulayıcının KENDİ bandını uygular
#: (``MotorDataValidator.limits['chamber_length'] = [0,05; 20,0] m``).
#: ÖLÇÜLDÜ (taban 7751531, ``once.json`` → ``OH-Z5-12.sinirlar``):
#: ``chamber_length = 0.02`` ve ``0.021`` girdileri
#: *"could not be read as a drawable length (out_of_band ...)"* diye
#: reddediliyor, buna rağmen KARDEŞ ret iletisi bandı ``[0.02, 5] m`` diye
#: ilan ediyordu — yani ürün, kabul ettiğini söylediği sayıyı reddediyordu.
#: Alt sınır artık o tek kaynaktan okunur; iki ileti aynı şeyi söyler.
CHAMBER_LENGTH_MIN_M = (
    (_dogrulayici_bandi_m('chamber_length') or (CHAMBER_LENGTH_MIN_FALLBACK_M,
                                                CHAMBER_LENGTH_MAX_M))[0])

# Kesit görünümünde çizilen tekrarlı öğe (soğutma kanalı / enjektör deliği)
# üst sınırı. Plotly her öğeye bir iz (trace) açtığı için 500 kanallı bir
# motor tarayıcıyı kilitler. MESH_MAX_INJECTOR_ORIFICES ile AYNI desen:
# çizilen sayı kırpılabilir, ama GERÇEK sayı çıktıda ayrı alanda yazılır ve
# kırpma açıkça beyan edilir.
CROSS_SECTION_MAX_CHANNELS = 64
CROSS_SECTION_MAX_INJECTOR_HOLES = 64

# Nitel imalat zorluğu (beceri seviyesi, özel takım) atölye deneyimi
# kaynaklıdır; motorun hesabından türetilmez ve çıktıda böyle etiketlenir.
MANUFACTURING_EFFORT_BASIS = ('typical machine-shop experience for this size '
                              'class; not computed from the analysis')

# Termin (işleme/montaj süresi) alanları v2.6.26'da KALDIRILDI — V2.6.26
# planı §2.2. Arayüz boş hücre yerine bu açıklamayı basabilsin diye alanın
# yokluğu açıkça raporlanır (sıvı motordaki MANUFACTURING_COST_STATUS deseni).
MANUFACTURING_EFFORT_STATUS = (
    'not calculated: HRMA has no machine-shop routing, labour-rate or '
    'programme schedule data. Machining and assembly durations were removed '
    'because the previous values ("24-48 hours", "4-6 hours") were fixed '
    'literals, identical for a 500 N amateur motor and a 50 kN motor')

# İmalat notlarında SAYILAR çözücüden gelir; adımların kendisi (tornalama,
# delme, çapak alma, sızdırmazlık) genel atölye pratiğidir ve bu motorun
# analizinden türetilmez. MANUFACTURING_EFFORT_BASIS ile aynı desen.
MANUFACTURING_NOTE_BASIS = ('numeric values in the steps above come from this '
                            'analysis run (source named inline); the process '
                            'steps themselves are general machine-shop practice '
                            'and are not computed for this motor')

# ANSI B1.1 / AWS D1.1 gerçek standartlardır, ancak "bu tasarıma uygulanır"
# iddiası bu yazılım tarafından DOĞRULANMAZ; referans olarak listelenir.
MANUFACTURING_STANDARD_BASIS = ('the standards cited (ANSI B1.1 threads, '
                                'AWS D1.1 welding) are real published standards '
                                'listed for reference only; this analysis does '
                                'not verify that they are the applicable '
                                'standards for this design')

# Yüzey pürüzlülüğü bu yazılımın tasarım çıktısı DEĞİLDİR; standart atölye
# değeridir ve çizim sözlüğünde kaynağıyla (finish_basis) birlikte verilir.
# v2.6.26 (P4): DRAWING_TOLERANCE_BASIS kaldırıldı — künyesi ("ISO 2768-m")
# ile yanında yazılan sabit sayılar ('+-0.1 mm' / '+-0.5 mm') birbirini
# tutmuyordu. Tolerans artık ölçüden aranır: bkz. _iso2768_tolerance_block.
DRAWING_SURFACE_FINISH_BASIS = ('ISO 1302 typical machined finish (workshop '
                                'standard, not computed by this analysis)')
DRAWING_SURFACE_FINISH_CHAMBER = 'Ra 3.2 um'
DRAWING_SURFACE_FINISH_NOZZLE = 'Ra 1.6 um'
DRAWING_SURFACE_FINISH_INJECTOR = 'Ra 0.8 um'


def _real_scalar(value):
    """Sonlu pozitif float döndürür; aksi halde None (uydurma varsayılan yok).

    Kural merkezden (``input_guard.finite_positive``, ÖH D28 / OH-D27-11).
    """
    return finite_positive(value)


#: ÖH D36 / onemli2-sivi a2 — ``_add_performance_chart`` sabit itki izini
#: süre yayımlanmadığında ÇİZMEZ ve alt grafiğe bu gerekçeyi yazar. Metin
#: İngilizcedir: CAD paketinin şekil/README metinleri EN üretilir (backend
#: sözleşmesi, app.py CAD paketi manifest notu).
PERFORMANCE_CHART_NOT_DRAWN_REASON = (
    'Performance chart not drawn: burn_time was not published by the solver '
    '(no burn time was supplied) and no duration is assumed.')


def _iso2768_tolerance_block(bore_mm, outer_mm, length_mm):
    """Kamara çizimi için ISO 2768-1 genel tolerans bloğu.

    v2.6.26 (P4). Öncesi: sabit '+-0.1 mm' çap / '+-0.5 mm' boy. Bu iki sayı
    75 mm'lik amatör motorla 500 mm'lik motora aynıydı VE yanlarındaki künye
    "ISO 2768-m" diyordu — oysa o standardın tablosu ölçüye göre değişir.
    Yani sayılar gösterilen kaynağa uymuyordu.

    Tablo BU DOSYADA TEKRAR TANIMLANMAZ: proje içinde tek tanım noktası
    ``hrma.engines.liquid_rocket_engine`` içindedir (sıvı motorun kritik
    tolerans bloğu onu kullanır). Modül okunamazsa sayı UYDURULMAZ; blok
    'NOT_AVAILABLE' durumu döner.

    İşlenmiş yatak yüzeyleri hassas (f), gövde/montaj ölçüleri orta (m)
    sınıfta aranır — sıvı motordaki aynı gerekçe.
    """
    try:
        from hrma.engines.liquid_rocket_engine import (
            ISO2768_GRADE_GENERAL, ISO2768_GRADE_PRECISION,
            ISO2768_TOLERANCE_BASIS, _iso2768_feature)
    except Exception as exc:                       # pragma: no cover
        return {'status': 'NOT_AVAILABLE',
                'basis': f'ISO 2768-1 tolerance table unavailable: {exc}'}

    def _feature(nominal, grade):
        # Ölçü yoksa tolerans da yoktur; komşu alanlarla aynı etiket kullanılır.
        return _iso2768_feature(nominal, grade) or NOT_AVAILABLE_SPEC

    return {
        # Grain/kapak bu deliğe oturur: işlenmiş yatak -> hassas sınıf
        'diameter': _feature(bore_mm, ISO2768_GRADE_PRECISION),
        'outer_diameter': _feature(outer_mm, ISO2768_GRADE_GENERAL),
        'length': _feature(length_mm, ISO2768_GRADE_GENERAL),
        'basis': ISO2768_TOLERANCE_BASIS,
        'source': ('ISO 2768-1 Table 1 (permissible deviations for linear '
                   'dimensions), classes f and m'),
    }


def _nozzle_half_angles(motor_data):
    """Lüle yarı açılarını ÇÖZÜCÜ çıktısından okur.

    Döner: (konverjan_derece|None, diverjan_derece|None, lüle_tipi)
    Kaynak sırası: nozzle_angles -> nozzle_contour.divergent. Bell lülede
    diverjan açısı boğaz çıkış açısıdır (tek bir konik açı yoktur), bu yüzden
    tip de döndürülür ve çizim etiketinde kullanılır. Değer yoksa None döner —
    çağıran sabit 15°/12° uydurmak yerine açıyı hiç etiketlemez.
    """
    md = motor_data or {}
    angles = md.get('nozzle_angles') or {}
    divergent = (md.get('nozzle_contour') or {}).get('divergent') or {}

    conv = _real_scalar(angles.get('convergent_half_angle_deg'))
    noz_type = (divergent.get('type') or angles.get('nozzle_type') or '').lower()

    div = _real_scalar(angles.get('divergent_half_angle_deg'))
    if _nozzle_family(noz_type) == 'bell':
        # Bell: boğaz çıkış açısı gerçek imalat açısıdır
        div = _real_scalar(divergent.get('throat_angle')) or div
    elif div is None:
        div = _real_scalar(divergent.get('half_angle'))

    return conv, div, (noz_type or 'conical')


def _nozzle_exit_angle_deg(motor_data):
    """Lülenin ÇIKIŞ yarı açısı [derece]; yayımlanmamışsa ``None``.

    Çan lülede ıraksak bölümün açısı SABİT DEĞİLDİR: boğazda ``theta_n``,
    çıkışta ``theta_e`` olur ve **itki kaybını belirleyen çıkıştaki açıdır**
    (``lambda = (1 + cos theta_e) / 2``).

    ÖH D15 (defter P9B2-09) — TEK KAYNAK. Ölçüldü (31 Ağustos 2026, 10 kN
    RP1/LOX, ``nozzle_type = bell_80``): çözücü ``exit_angle_deg = 8,5`` ve
    ``divergence_efficiency = 0,9945079316809584`` yayımlıyor; özdeşlik
    doğrulandı ``(1 + cos 8,5 derece) / 2 = 0,9945079``, yani yayımlanan Isp
    8,5 dereceye demirli. İmalat çiziminin lüle satırı ise yalnız
    ``bell_80; conv 30.0 deg, div 30.0 deg`` yazıyordu — 30 derece BOĞAZ
    açısıdır ve çıkış açısı çizimin HİÇBİR yerinde geçmiyordu. O künyeye
    bakıp 30 derecelik düz koni üreten atölye ``(1 + cos 30) / 2 = 0,9330127``
    ile **-%6,18** itki/Isp elde eder.

    Değer iki şemadan da okunur: ``nozzle_contour.divergent.exit_angle``
    (kontur üreteci) ve ``nozzle_angles.exit_angle_deg`` (sıvı çözücüsü —
    kontur bloğunu boş bırakıp açıyı burada yayımlıyor).
    """
    md = motor_data or {}
    return (_real_scalar(((md.get('nozzle_contour') or {})
                          .get('divergent') or {}).get('exit_angle'))
            or _real_scalar((md.get('nozzle_angles') or {})
                            .get('exit_angle_deg')))


def _nozzle_family(noz_type):
    """Lüle tipini AİLESİNE indirger: 'bell_80' -> 'bell'.

    ÖH D15 (defter P9B1-15). Kusur: kontur ailesi ``== 'bell'`` KESİN
    EŞİTLİĞİYLE aranıyordu. Sıvı çözücüsü tipi ``'bell_80'`` (yüzde-boy ekli)
    yayımladığı için bell dalı HİÇ çalışmıyordu: ölçüldü (31 Ağustos 2026,
    ``motor_liquid`` fikstürü) ``technical_drawings.nozzle`` bir 50 genişleme
    oranlı çan lülesine ``'conical: constant half angle'`` + 30,0 derece
    yazıyordu — yani imalatçıya "sabit 30 derece yarı açılı koni tornala"
    diyordu. Aynı sonuçta gerçek çıkış açısı (``exit_angle_deg`` = 8,5) hazır
    duruyordu.

    Aile adı yalnız ETİKET/ANLAM seçiminde kullanılır; çıktıya yazılan
    ``nozzle_type`` çözücünün yazdığı tam addır ('bell_80'), kısaltılmaz.
    """
    t = (noz_type or '').strip().lower()
    if t.startswith('bell') or t.startswith('rao') or t.startswith('parabolic'):
        return 'bell'
    return t


def _nozzle_angle_source_label(motor_data):
    """Lüle açısı künyesi — ÇÖZÜCÜNÜN kendi beyanı DÜŞÜRÜLMEDEN.

    ÖH Z5S (defter P9B1-24). Kusur: çizim sözlüğü açı künyesine koşulsuz
    ``'solver nozzle_angles / nozzle_contour'`` yazıyordu. Katı motor çözücüsü
    (``hrma/engines/solid_rocket_engine.py``) aynı blokta
    ``nozzle_angles['angles_source']`` alanını yayımlar ve değeri
    ``'conical_default_30_15'`` olduğunda "bu açılar ÜRETEÇ VARSAYIMIDIR,
    kullanıcı girdisi değildir" demektedir. İhraç katmanı bu beyanı siliyordu:
    ölçüldü (27 Ağustos 2026), ``angles_source='conical_default_30_15'`` ile
    ``angles_source='user_input'`` koşumları BİREBİR aynı künyeyi basıyordu.

    Künye artık kazanılır: kaynağını çözücü beyan ettiyse beyan aynen taşınır,
    beyan "varsayılan" diyorsa bu okuyucuya açıkça söylenir, hiç beyan yoksa
    (hibrit çözücüsünün bugünkü hâli) künye "bilinmiyor" der — yani
    "kullanıcı girdisi" İDDİA EDİLMEZ (fail-closed).
    """
    angles = (motor_data or {}).get('nozzle_angles') or {}
    base = 'solver nozzle_angles / nozzle_contour'
    declared = angles.get('angles_source')
    if not isinstance(declared, str) or not declared.strip():
        return (f'{base}; this analysis run does not state whether the angles '
                'are a user input or a generator default')
    declared = declared.strip()
    if 'default' in declared.lower():
        return (f'{base}; solver angles_source = "{declared}" - these are '
                'DEFAULT angles produced by the solver, NOT a user input and '
                'NOT an optimised contour')
    return f'{base}; solver angles_source = "{declared}"'


def _measured_envelope_diameter_mm(assembly_meshes):
    """Üretilen katıların GERÇEK radyal zarf çapı [mm] + künye.

    ÖH Z5S (defter P9B1-02, kritik). Kusur: yayımlanan ``max_diameter`` bir
    FORMÜLDÜ (``max(kamara deliği + 2 x cidar, lüle çıkışı + 2 x lüle cidarı)``)
    ve formül, lüle cidarı sonuçta yoksa lüleyi zarftan TAMAMEN düşürüyordu —
    oysa 3B katı o durumda da lüleyi ``max(0.003, 0.1 x boğaz çapı)`` yedek
    cidarıyla çiziyordu. Ölçüldü (27 Ağustos 2026, hibrit 5 kN, geniş lüle,
    ``nozzle_geometry.wall_thickness`` alanı kaldırılmış): yayımlanan zarf
    187,015 mm, aynı koşuda üretilen katının gerçek zarfı 364,485 mm (1,949x).
    Zarf çapı gövde tüpü ve yük hattı seçimine giren ölçüdür.

    Onarım tek kurala iner: **zarf ÖLÇÜLÜR, hesaplanmaz.** Katı üretilmediyse
    (bu özet katılar olmadan çağrıldıysa) sayı BASILMAZ — bir tahmin ayrı ve
    adı tahmin olan bir alanda taşınır.

    Eksen sözleşmesi: montaj katıları z ekseninde dizilir (kamara [0, L], lüle
    [L, L+Ln]), bu yüzden radyal yarıçap ``hypot(x, y)``dir.

    Döner: ``(çap_mm|None, künye_metni)``
    """
    if not assembly_meshes:
        return None, ('not measured: this summary was produced without the '
                      'generated 3D solids, so the envelope of the drawn '
                      'assembly could not be read off it')
    r_max = None
    for item in assembly_meshes:
        try:
            _name, mesh = item
        except (TypeError, ValueError):
            continue
        try:
            vertices = np.asarray(mesh.vertices, dtype=float)
        except Exception:
            continue
        if vertices.ndim != 2 or vertices.shape[0] == 0 or vertices.shape[1] < 2:
            continue
        radii = np.hypot(vertices[:, 0], vertices[:, 1])
        radii = radii[np.isfinite(radii)]
        if radii.size == 0:
            continue
        part_r = float(radii.max())
        r_max = part_r if r_max is None else max(r_max, part_r)
    if r_max is None or not np.isfinite(r_max) or r_max <= 0.0:
        return None, ('not measured: the generated solids carry no usable '
                      'vertex coordinates, so no envelope was read off them')
    return (2.0 * r_max * 1000.0,
            'MEASURED on the generated 3D solids: 2 x max(hypot(x, y)) over '
            'every assembly-mesh vertex (assembly axis is z). This is the '
            'envelope of the parts that were actually drawn, not a formula.')


def _mesh_orifice_count(n_orifices):
    """3B katıda GERÇEKTEN açılan delik sayısı (ÖH D19, defter P9B1-23).

    Kırpma kuralı ``generate_3d_motor_assembly`` içinde zaten vardı ama
    yalnız üreticinin yerel kopyasına yazılıyordu. Kural burada İKİNCİ KEZ
    YAZILMAZ: ikisi de ``MESH_MAX_INJECTOR_ORIFICES`` sabitini okur ve aynı
    ``max(1, min(...))`` kalıbını kullanır.
    """
    try:
        gercek = int(n_orifices) if n_orifices else 0
    except (TypeError, ValueError):
        return 0
    if gercek <= 0:
        return 0
    return max(1, min(gercek, MESH_MAX_INJECTOR_ORIFICES))


def _injector_circuit_summary(circuits):
    """Devre başına delik planının okunur özeti (ÖH D33-2 / OH-D32-04).

    ``'6 x 2.4920 mm (oxidizer), 6 x 2.3217 mm (fuel)'``. Devreler farklı
    çaplarda olabildiği için tek bir çap yayımlamak sayı uydurmak olurdu;
    imalat notu ve çizim sözlüğü bu özeti yazar. Boş listede None döner.
    """
    if not circuits:
        return None
    return ', '.join(
        f"{int(c['n'])} x {float(c['d_mm']):.4f} mm ({c['name']})"
        for c in circuits)


def _mesh_orifice_plan(circuits):
    """MESH'te GERÇEKTEN delinecek devre planı (ÖH D33-2, defter OH-D32-04).

    ``circuits`` ``_injector_spec``in devre listesidir. Toplam delik sayısı
    ``MESH_MAX_INJECTOR_ORIFICES``i aşarsa devreler ORANTILI kırpılır ve her
    devre en az bir delik korur — böylece STL'i açan kişi, tasarımın kaç
    devresi olduğunu görür (tek devreyi tamamen düşürmek plakayı yanlış
    anlatırdı). Kırpma KURALI ikinci kez yazılmaz: toplam
    ``_mesh_orifice_count`` ile bulunur.

    Döner: ``[{'name', 'n', 'd_mm'}]`` — boş liste = delik açılmaz.
    """
    temiz = [c for c in (circuits or [])
             if c.get('n') and c.get('d_mm') and c['n'] > 0 and c['d_mm'] > 0]
    if not temiz:
        return []
    toplam = sum(int(c['n']) for c in temiz)
    hedef = _mesh_orifice_count(toplam)
    if hedef >= toplam:
        return [{'name': c['name'], 'n': int(c['n']), 'd_mm': float(c['d_mm'])}
                for c in temiz]
    if hedef < len(temiz):
        # Her devreye bir delik bile düşmüyor: devre SAYISINI kırpmak
        # plakayı yanlış anlatır, o yüzden her devre bir delikle temsil
        # edilir (kırpma künyesi bunu zaten söyler).
        return [{'name': c['name'], 'n': 1, 'd_mm': float(c['d_mm'])}
                for c in temiz]
    plan = [{'name': c['name'], 'd_mm': float(c['d_mm']),
             'n': max(1, int(round(int(c['n']) * hedef / toplam)))}
            for c in temiz]
    # Yuvarlama hedefi kaçırabilir: fazlalık en büyük devreden düşülür,
    # eksiklik en büyük devreye eklenir (hiçbir devre 1'in altına inmez).
    while sum(x['n'] for x in plan) > hedef:
        en_buyuk = max(plan, key=lambda x: x['n'])
        if en_buyuk['n'] <= 1:
            break
        en_buyuk['n'] -= 1
    while sum(x['n'] for x in plan) < hedef:
        max(plan, key=lambda x: x['n'])['n'] += 1
    return plan


def _mesh_orifice_basis(n_orifices):
    """``orifice_count_in_mesh`` künyesi — kırpıldıysa ADIYLA söyler."""
    ciz = _mesh_orifice_count(n_orifices)
    if not ciz:
        return ('no orifices are drilled in the 3D solid: this run publishes '
                'no injector orifice count, so no hole pattern was cut')
    try:
        gercek = int(n_orifices)
    except (TypeError, ValueError):
        gercek = ciz
    if gercek > ciz:
        return (f'the design calls for {gercek} orifices but the 3D solid '
                f'(and therefore the exported STL) carries only {ciz}: the '
                f'mesh boolean is capped at MESH_MAX_INJECTOR_ORIFICES = '
                f'{MESH_MAX_INJECTOR_ORIFICES} for render stability. The '
                f'orifice_count field above is the DESIGN number; this file '
                f'is not a drilling master for the injector plate.')
    return (f'the 3D solid carries all {ciz} design orifices (no mesh cap '
            f'applied; cap is MESH_MAX_INJECTOR_ORIFICES = '
            f'{MESH_MAX_INJECTOR_ORIFICES})')


def _solver_convergent_fraction(motor_data, chamber_dia_m, throat_dia_m,
                                exit_dia_m):
    """Konverjan/diverjan bölünmesi ÇÖZÜCÜDEN. Döner: ``(kesir|None, künye)``.

    ÖH D25 (defter OH-D24-09, zincir P9B1-08). Kusur: kesit lüle profili
    bölünmeyi ``CONV_FRAC = 0.3`` GÖRÜNTÜ SABİTİNDEN alıyordu, yani panelin
    ima ettiği boğaz konumu her motorda lüle boyunun %30'undaydı. Ölçüldü
    (taban ``cdf2106``, ``once.json`` bölüm MB; aynı gövdenin çözücü
    konturuyla kıyas): çözücünün ``z_throat/z_exit`` kesri hibritte
    **0,3074**, katıda **0,4718**, sıvıda **0,9989** iken çizilen profil
    üçünde de 0,30 (0,3061) ima ediyordu — sıvıda boğaz, lülenin sonuna
    yakın olması gerekirken başına yakın çiziliyordu.

    Bölünme artık deponun TEK kontur kaynağından
    (``nozzle_design.sample_nozzle_inner_contour``, 2B kesit / 3B CAD / STL /
    DXF / STEP hepsinin okuduğu örnekleyici) okunur; oran birimsizdir, bu
    yüzden panelin mm sözleşmesi ile çözücünün metre sözleşmesi arasında
    dönüşüm gerekmez. Kontur üretilemezse sayı UYDURULMAZ: ``None`` döner ve
    çağıran konverjanı ÇİZMEZ (kamara çapı yokken uygulanan kuralın ikizi).
    """
    md = dict(motor_data) if isinstance(motor_data, dict) else None
    if md is None:
        return None, ('convergent/divergent split not drawn: no analysis '
                      'result was supplied to the cross-section, so the '
                      'throat station could not be read from the solver '
                      'contour')
    # Panelin ÇİZDİĞİ ölçüler (metre) örnekleyiciye olduğu gibi verilir ki
    # kesit ile kontur aynı motoru anlatsın.
    for ad, v in (('chamber_diameter', chamber_dia_m),
                  ('throat_diameter', throat_dia_m),
                  ('exit_diameter', exit_dia_m)):
        if v is not None and float(v) > 0:
            md[ad] = float(v)
    try:
        _pts, meta = sample_nozzle_inner_contour(md)
        z_t = float(meta['z_throat'])
        z_e = float(meta['z_exit'])
    except Exception as exc:
        return None, ('convergent/divergent split not drawn: the solver '
                      'nozzle contour could not be sampled '
                      f'({type(exc).__name__}: {exc}); no display constant '
                      'is substituted')
    if not (np.isfinite(z_t) and np.isfinite(z_e)) or not (0.0 < z_t < z_e):
        return None, ('convergent/divergent split not drawn: the solver '
                      'contour places the throat at '
                      f'z_throat={z_t!r} of z_exit={z_e!r}, which is not a '
                      'usable split; no display constant is substituted')
    return (z_t / z_e,
            'convergent/divergent split MEASURED on the solver nozzle '
            'contour (nozzle_design.sample_nozzle_inner_contour): '
            f'z_throat = {z_t:.4f} mm of z_exit = {z_e:.4f} mm, i.e. the '
            f'throat sits at {100.0 * z_t / z_e:.2f}% of the nozzle length. '
            'Divergent length basis: '
            f'{meta.get("divergent_length_source")!r}.')


def _measured_envelope_length_mm(assembly_meshes):
    """Üretilen katıların GERÇEK eksenel boyu [mm] + künye.

    ÖH D19 (defter P15B4-11). Kusur: ``geometry_summary.total_length``
    CAD'in KENDİ toplamıydı (``chamber_length + _nozzle_length_m``) ve
    motorun yayımladığı boy tanımlarının HİÇBİRİNE eşit değildi. Ölçüldü
    (``docs/scofield/raw/OH/D19/ihracat/a1/once.json``, 1 kN hibrit):
    CAD 771,7501 mm derken motor iki tanım yayımlıyordu —
    ``total_motor_length_chamber_nozzle_mm`` 771,2074 ve
    ``total_motor_length_with_caps_mm`` 772,2390. Üstelik motorun kendi
    ``total_motor_length_basis`` künyesi "3B görünümün toplam-boy etiketi
    kapak DÂHİLDİR, yani with-caps tanımına karşılık gelir" diyordu; CAD'in
    bastığı üçüncü sayı bu beyanı da yalanlıyordu.

    Onarım ``max_diameter`` ile AYNI kurala iner (P9B1-02): **boy ÖLÇÜLÜR,
    hesaplanmaz.** Katılar yoksa sayı BASILMAZ; formülün sonucu ayrı ve adı
    "tahmin" olan bir alanda kalır. Bir formül ile bir katı birbirini
    tutmadığında imalata giden sayı KATININ sayısıdır.

    Eksen sözleşmesi: montaj katıları z ekseninde dizilir (kamara [0, L],
    lüle [L, L+Ln]), bu yüzden eksenel boy ``max(z) - min(z)``dir.

    Döner: ``(boy_mm|None, künye_metni)``
    """
    if not assembly_meshes:
        return None, ('not measured: this summary was produced without the '
                      'generated 3D solids, so the axial length of the drawn '
                      'assembly could not be read off it')
    z_min = None
    z_max = None
    for item in assembly_meshes:
        try:
            _name, mesh = item
        except (TypeError, ValueError):
            continue
        try:
            vertices = np.asarray(mesh.vertices, dtype=float)
        except Exception:
            continue
        if vertices.ndim != 2 or vertices.shape[0] == 0 or vertices.shape[1] < 3:
            continue
        zs = vertices[:, 2]
        zs = zs[np.isfinite(zs)]
        if zs.size == 0:
            continue
        part_min, part_max = float(zs.min()), float(zs.max())
        z_min = part_min if z_min is None else min(z_min, part_min)
        z_max = part_max if z_max is None else max(z_max, part_max)
    if z_min is None or z_max is None or not np.isfinite(z_max - z_min):
        return None, ('not measured: the generated solids carry no usable '
                      'vertex coordinates, so no axial length was read off '
                      'them')
    boy = z_max - z_min
    if boy <= 0.0:
        return None, ('not measured: the generated solids collapse to a '
                      'single axial station, so no axial length was read '
                      'off them')
    return (boy * 1000.0,
            'MEASURED on the generated 3D solids: max(z) - min(z) over every '
            'assembly-mesh vertex (assembly axis is z). This is the axial '
            'envelope of the parts that were actually drawn - including the '
            'forward closure - not a formula.')


def _solver_injector_element_count(motor_data):
    """Enjektör eleman/orifis sayısı — ÇÖZÜCÜDEN (arayüz sabitinden DEĞİL).

    ÖH Z5S (defter P9B1-21). Sıvı kesit çizimi delik sayısını
    ``motor_data.get('injector_holes', 24)`` ile okuyordu. ``injector_holes``
    arayüzün gönderdiği SABİTTİR; aynı yanıtın bileşen tablosu (
    :meth:`DetailedCADGenerator._get_component_details`) bu anahtarı BİLEREK
    reddeder. Ölçüldü (27 Ağustos 2026): çözücü 41 eleman raporlarken kesitte
    24 delik çizildi; çözücü hiç eleman üretmediği koşumda tablo
    "NOT AVAILABLE" derken kesit yine 24 delik çizdi.

    Döner: ``int`` (>=1) ya da ``None`` (çözücü sayı üretmedi -> DELİK ÇİZİLMEZ).
    """
    md = motor_data or {}
    inj_design = md.get('injector_design') or {}
    n = _real_scalar(inj_design.get('number_of_elements')
                     or inj_design.get('number_of_orifices')
                     or md.get('injector_elements'))
    return int(round(n)) if n else None


def _solver_cooling_channel_count(motor_data):
    """Soğutma kanalı sayısı — ÇÖZÜCÜDEN.

    ÖH Z5S (defter P9B1-20). Sıvı kesit çizimi HER motorda tam 24 kanal
    çiziyordu (``n_channels = 24``). Ölçüldü (27 Ağustos 2026): aynı yanıtın
    bileşen tablosu ``cooling_system.cooling_channels = 80`` yazarken kesit
    24 kanal çizdi; çözücü kanal üretmediği koşumda tablo "NOT AVAILABLE"
    derken kesit yine 24 kanal çizdi.

    Döner: ``int`` (>=1) ya da ``None`` (çözücü sayı üretmedi -> KANAL ÇİZİLMEZ).
    """
    md = motor_data or {}
    cooling = md.get('cooling_system') or {}
    n = _real_scalar(cooling.get('cooling_channels')
                     or md.get('cooling_channels'))
    return int(round(n)) if n else None


def _nozzle_length_m(motor_data):
    """Lüle boyu [m] — sonuçta varsa oradan, yoksa GERÇEK kontur uzunluğundan.

    Sabit 0.15 m yedeği kullanılmaz: sample_nozzle_inner_contour zaten motorun
    kendi geometrisinden çıkarılmış konturu döndürür.
    """
    md = motor_data or {}
    length = _real_scalar(md.get('nozzle_length'))
    if length is not None:
        return length
    try:
        _pts, meta = sample_nozzle_inner_contour(md)
        return float(meta['z_exit']) / 1000.0
    except Exception:
        return None


def _first_real(mapping, *keys):
    """Verilen anahtarlardan İLK sonlu-pozitif değeri döndürür (yoksa None)."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = _real_scalar(mapping.get(key))
        if value is not None:
            return value
    return None


def _injector_motor_type(motor_data):
    """Koşunun motor tipi — TAHMİN EDİLMEZ, gövdeden okunur.

    ``step_export.normalise_step_motor_type`` ile AYNI alanlar ve AYNI
    reddetme kuralı; tanınmayan/eksik değerde ``resolve_injector_plan``ın
    kendi varsayılanına (``'hybrid'``) düşülür, böylece iki üretici aynı
    dalı seçer.
    """
    from hrma.export.step_export import normalise_step_motor_type

    md = motor_data if isinstance(motor_data, dict) else {}
    for key in ('motor_type', 'engine_type', 'analysis_type', 'motor_class'):
        tip, _hata = normalise_step_motor_type(md.get(key))
        if tip:
            return tip
    return 'hybrid'


def _injector_block(motor_data):
    """Enjektör iddiasını taşıyan bloğu SEÇER — STEP ile AYNI seçiciden.

    Seçim ``step_export.resolve_injector_circuits``tedir (TEK KAYNAK); burada
    ikinci bir öncelik listesi ya da ikinci bir seçim kuralı YAZILMAZ, yoksa
    iki üretici aynı gövdede farklı bloğa bakardı (ÖH D33-2 / OH-D32-04).
    """
    from hrma.export.step_export import resolve_injector_circuits

    block, key, _c, _m = resolve_injector_circuits(
        motor_data if isinstance(motor_data, dict) else {},
        motor_type=_injector_motor_type(motor_data))
    return block, key


def _injector_spec(motor_data):
    """Enjektör için TEK doğruluk kaynağı.

    Döner: {'n_orifices', 'orifice_diameter_mm', 'circuits', 'missing',
            'plate_diameter_mm', 'type', 'pressure_drop_bar', 'source'}
    Aynı motor koşusunda ekran grafiği, teknik çizim PDF'i ve CAD sözlüğü
    farklı delik sayıları gösteriyordu (2026-07-19 denetimi, kritik bulgu);
    bütün CAD/çizim katmanı artık bu tek fonksiyondan okur. Değer yoksa
    None bırakılır — sabit sayı uydurulmaz.

    KAYNAK KARIŞTIRMA YASAĞI (v2.6.26, K2 denetimi). Hibrit ``/calculate``
    İKİ bağımsız enjektör çözücüsü koşturur:
      1. Enjektör paneli (``injector_results``) — ekran tablosu ve 2B şema,
      2. Motorun kendi devre modeli (``injector_design`` /
         ``injector_design_detail``) — N2O'da doyma basıncını kullanır.
    Eski kod delik sayısını (1)'den, basınç düşümünü (2)'den okuyabiliyordu.
    Ölçüldü: panel 125 delik x 0,957 mm / ΔP 4,00 bar derken çizim sözlüğü
    aynı satırda ΔP 30,37 bar yazıyordu — 7,6 kat. Böyle bir enjektör HİÇBİR
    çözücüde yoktur; melez spesifikasyon uydurmadır. Bir kaynak seçilir ve
    BÜTÜN alanlar o kaynaktan okunur; kaynakta olmayan alan None kalır.

    ÖH D33-2 / defter OH-D32-04 — ALAN ADLARI ve BLOK SIRASI ARTIK STEP
    ÜRETİCİSİYLE ORTAK.

    ÖLÇÜLDÜ (taban ``5e0714c1``, ``docs/scofield/raw/OH/D33-2/ihracat-cad/
    a1/once.json``): bu fonksiyon ``number_of_orifices | n_holes |
    n_elements`` + ``orifice_diameter_mm | hole_diameter`` zincirini
    okuyordu; sıvı çözücünün GERÇEKTE yayımladığı adlar ise
    ``number_of_elements`` + ``oxidizer_orifice_diameter_mm`` /
    ``fuel_orifice_diameter_mm``. Sonuç (bölüm A1/A2, 10 kN LOX/RP-1):
    AYNI koşuda STL/çizim tarafı ``n_orifices=None``, ``source='not
    available'`` derken STEP tarafı (``resolve_injector_plan``) **12 delik**
    (6 oksitleyici Ø2,4920 mm + 6 yakıt Ø2,3217 mm) deliyordu. Plaka
    kalınlığı kazanılan koşuda iki üretici de plakayı çizdiği için parça
    listeleri UYUŞUYOR, 422 kapısı ATEŞLEMİYOR ve aynı ZIP'te **0 delikli**
    bir STL ile **12 delikli** bir STEP yan yana iniyordu.

    İkinci kök: BLOK ÖNCELİĞİ de iki yerde ve TERSTİ. Burası paneli,
    ``step_export`` ``injector_design``i birincil sayıyordu; ölçüldü (A4,
    her iki blok da delik yayımlıyorken) STL **125 x Ø0,957 mm**, STEP
    **12 delik** diyordu. Dahası panel YALNIZ ``plate_structural``
    taşıdığında bile burada sırayı KİLİTLİYOR ve delik planı
    ``injector_design``de dururken sonuç ``not available`` oluyordu (A2 —
    kusurun asıl ürün yolu).

    Artık ikisi de tek seçiciden (``step_export.resolve_injector_circuits``,
    sıra ``INJECTOR_BLOCK_ORDER``) geçer; kural ``devre planı YAYIMLAYAN
    ilk blok kazanır``, boş blok sırayı kilitlemez. Sıranın yönü bu
    fonksiyonun kendi doktrinidir (panel BİRİNCİL); ``step_export`` paneli
    yalnız geçici bir bit-aynılık kaygısıyla sona koymuştu.

    ``circuits`` devre başına (sayı, çap) taşır — sıvıda oksitleyici ve
    yakıt devrelerinin çapları FARKLIDIR, tek bir çifte indirgemek çap
    uydurmak olurdu. Geriye dönük ``n_orifices`` devrelerin TOPLAMI,
    ``orifice_diameter_mm`` ise yalnız bütün devreler aynı çapı
    paylaşıyorsa doludur; paylaşmıyorsa None kalır ve okuyucu ``circuits``e
    bakmak zorundadır (fail-closed).
    """
    from hrma.export.step_export import (
        injector_declared_count, resolve_injector_circuits)

    md = motor_data or {}
    detail = md.get('injector_design_detail') or {}
    if not isinstance(detail, dict):
        detail = {}
    ox = detail.get('ox_circuit') or {}

    block, block_key, circuits, missing = resolve_injector_circuits(
        md, motor_type=_injector_motor_type(md))

    if block is not None:
        inj = block
        # K2: TİP ve BASINÇ DÜŞÜMÜ, delik planıyla AYNI bloktan okunur.
        dp = (_first_real(inj, 'injection_pressure_drop_bar',
                          'pressure_drop_bar', 'pressure_drop')
              or (_first_real(ox, 'delta_p_bar')
                  if block_key != 'injector_results' else None))
        inj_type = (inj.get('injector_type') or inj.get('type')
                    or (detail.get('injector_type')
                        if block_key != 'injector_results' else None))
        source_name = ('injector panel (injector_results)'
                       if block_key == 'injector_results'
                       else f'motor result {block_key}')
    else:
        dp = None
        inj_type = None
        source_name = 'not available'

    if circuits:
        n_total = sum(c['n'] for c in circuits)
    elif block is not None:
        # Çap çözülemese bile çözücünün YAYIMLADIĞI sayı çizimde durur
        # (delme emri değil, tasarım iddiası); plaka yine delinmez.
        n_total = injector_declared_count(
            md, block, detail, sadece_blok=(block_key == 'injector_results'),
            inj_key=block_key)
    else:
        n_total = None
    # Tek çap YALNIZ bütün devreler aynı çapı paylaşıyorsa yayımlanır.
    d_mm = None
    if circuits:
        caplar = [c['d_mm'] for c in circuits]
        if max(caplar) - min(caplar) <= 1e-9 * max(1.0, max(caplar)):
            d_mm = caplar[0]

    plate_mm = _real_scalar(md.get('chamber_diameter'))
    plate_mm = plate_mm * 1000.0 if plate_mm is not None else None

    return {
        'n_orifices': n_total,
        'orifice_diameter_mm': d_mm,
        'circuits': circuits,
        'missing': missing,
        'plate_diameter_mm': plate_mm,
        'type': inj_type,
        'pressure_drop_bar': dp,
        'source': source_name if n_total else 'not available',
    }


#: Yapısal analiz sonucunda kamara/kasa cidarının yaşadığı ÜÇ ayrı şema.
#: Motor tipleri aynı büyüklüğü farklı adla yayımlıyor — imalata giden STEP
#: yalnız ilkini tanıdığı için katı ve sıvı motorda cidarı BULAMIYOR ve
#: 0.045·D geometrik yedeğine düşüyordu (Faz 4B / A8).
#: Ölçüm (Ø100 mm katı motor, HEAD a7ff1e7): analiz
#: case_analysis.wall_thickness_mm = 2.40 mm, STEP'in ürettiği cidar 4.50 mm.
#: Her giriş: (blok_adı, as_designed_anahtar, önerilen_anahtar,
#: as_designed_kesin_mi) — değerler mm.
#: Son alan: blokta ``design_mode`` yoksa as-designed kalınlığın gerilmelerin
#: GERÇEKTEN hesaplandığı kalınlık olduğunu bildirir. Katıda
#: ``hoop_stress = P·r/t_wall`` doğrudan ``_case_design()``in verdiği
#: ``wall_thickness_mm`` ile, sıvıda ``chamber_structure.wall_thickness`` ile
#: hesaplanır; önerilen/gerekli kalınlık ayrı bir alandır. Öneriyi çizmek
#: kullanıcının tasarımını sessizce değiştirirdi (hibritte Y5 ile kapatılan
#: kusurun aynısı).
CHAMBER_WALL_SCHEMAS = (
    # hibrit / ortak yapısal modül (analysis/structural_analysis.py)
    ('chamber_analysis', 'wall_thickness_used_mm', 'recommended_thickness',
     False),
    # katı motor (engines/solid_rocket_engine.py::_calculate_structural_analysis)
    ('case_analysis', 'wall_thickness_mm', 'recommended_wall_thickness_mm',
     True),
    # sıvı motor (engines/liquid_rocket_engine.py::_calculate_structural_loads)
    ('chamber_structure', 'wall_thickness', 'required_wall_thickness', True),
)

#: Aynı üç bloğun EMNİYET KATSAYISI künyesi (ÖH Z2 / defter P9B1-01, P9B2-07).
#:
#: Kusur: ihraç katmanı "ölçülmüş SF" ile "kullanıcının SF HEDEFİ"ni tek bir
#: ``safety_factor`` alanında topluyordu. Ölçüldü (27 Ağustos 2026,
#: ``/calculate_liquid``, SF hedefi 2,5): ``chamber_structure.safety_factor``
#: = **2,5** — kardeş alan ``safety_factor_source`` bunu zaten
#: *"user input (safety factor)"* diye künyeliyor; yani çizime inen sayı
#: kullanıcının GİRDİSİNİN geri okunmasıydı. Aynı koşuda çizilen cidarın
#: gerçek gerilme durumu (hoop 61,53 MPa / derate edilmiş akma 958,16 MPa)
#: hiçbir alanda SF olarak yayımlanmıyor.
#:
#: Her giriş:
#:   ``measured_keys`` -> ÇİZİLEN cidarda hesaplanmış SF adayları (sırayla).
#:   ``target_keys``   -> tasarım HEDEFİ (yalnız kıyas notu olarak basılır).
#: Boş ``measured_keys`` = "bu blok çizilen cidara ait bir SF yayımlamıyor"
#: -> fail-closed: ihraç sayı uydurmaz, alanın yokluğunu BEYAN eder.
CHAMBER_WALL_SF_SCHEMAS = {
    'chamber_analysis': {
        'measured_keys': ('safety_factor_total', 'hoop_safety_factor'),
        'target_keys': ('design_safety_factor_target',),
    },
    'case_analysis': {
        'measured_keys': ('safety_factor',),
        'target_keys': ('design_safety_factor',),
    },
    # ÖH D16 / OH-Z4-01: ``measured_keys`` BOŞTU ve bu, sıvı motorun çizilen
    # cidarında GERÇEKTEN hesaplanan ``hoop_safety_factor``ı ihraç katmanına
    # görünmez kılıyordu. Ölçüldü (``raw/OH/D16/sivi/a1/once.json``, 10 kN /
    # Pc = 30 bar): blok ``hoop_safety_factor = 6,6031`` yayımlarken şema onu
    # ölçüm adayı saymadığı için ``safety_factor_is_measured`` HER hâlde
    # ``False`` kalıyordu — yani doğrulama iddiası KAZANILAMIYORDU. Motorun
    # kendi yorumu ise şemanın bu anahtarı "zaten tanıdığını" yazıyordu
    # (yanlış); iki taraf artık aynı şeyi söylüyor.
    'chamber_structure': {
        'measured_keys': ('hoop_safety_factor',),
        'target_keys': ('safety_factor',),
    },
}

#: Bir SF alanının kardeş künyesi bu ibareleri taşıyorsa sayı bir ÖLÇÜM değil,
#: girdinin geri okunmasıdır (sıvı motorun ``safety_factor_source`` alanı
#: "user input (safety factor)" yazar). Künye metinleri çözücülerde İngilizce
#: üretilir; karşılaştırma küçük harfe indirilerek yapılır.
SF_INPUT_READBACK_MARKERS = ('user input', 'user_supplied', 'user supplied',
                             'input read back', 'not a verification')


def _declares_input_readback(*labels):
    """Künye metinlerinden herhangi biri "bu sayı girdidir" diyor mu?"""
    for label in labels:
        if not isinstance(label, str):
            continue
        low = label.lower()
        if any(marker in low for marker in SF_INPUT_READBACK_MARKERS):
            return True
    return False


def _wall_safety_factor(chamber, block_name):
    """Cidar bloğundan (SF, ölçülmüş_mü, hedef, künye) çıkarır.

    ``ölçülmüş_mü`` üç değerlidir:
      * ``True``  -> çözücü sayının ÇİZİLEN cidarda hesaplandığını beyan etti
        (``safety_factor_is_tautological is False`` ya da
        ``design_mode == 'verify'``);
      * ``False`` -> çözücü sayının hedefin geri okunması olduğunu beyan etti
        (``safety_factor_is_tautological is True`` / ``design_mode == 'size'``
        / SF'nin kendi künyesi "user input" diyor);
      * ``None``  -> blok hiçbir beyan taşımıyor -> **iddia edilmez**
        (fail-closed; ihraç "doğrulandı" damgası basamaz).

    Dönen SF sayısı geriye dönük uyum için bloğun yayımladığı değerdir
    (tek kaynak korunur); onun bir ÖLÇÜM mü yoksa HEDEF mi olduğunu ikinci
    dönüş değeri söyler.

    NOT (27 Ağustos 2026 ölçümü, önemli): ``False`` "sayı anlamsız" DEMEK
    DEĞİLDİR. Hibrit cidarsız koşumda ``design_mode='size'`` olduğu için
    blok ``safety_factor_is_tautological=True`` yazar, ama yayımlanan
    ``safety_factor_total`` **0,9410**'dur — hedef 4,0 değil. Sebep:
    boyutlandırma yalnız BASINÇ hoop'unu hedefe oturtur, toplam SF termal
    hoop'u da içerir. Yani sayı çizilen cidarda gerçekten hesaplanmıştır ve
    1'in ALTINDADIR. Bu yüzden ihraç katmanı sayıyı GİZLEMEZ; yalnız
    "doğrulandı" İDDİASINI geri çeker. Sayının hiç yayımlanmadığı hâl
    (``None``) ayrıdır ve orada alan boş bırakılır.
    """
    schema = CHAMBER_WALL_SF_SCHEMAS.get(block_name) or {}
    basis = chamber.get('safety_factor_basis')
    basis = basis if isinstance(basis, str) else None

    target = None
    for key in schema.get('target_keys', ()):
        target = _real_scalar(chamber.get(key))
        if target is not None:
            break

    measured = None
    measured_key = None
    for key in schema.get('measured_keys', ()):
        value = _real_scalar(chamber.get(key))
        if value is None:
            continue
        # Alanın KENDİ künyesi "girdi" diyorsa ölçüm sayılmaz.
        #
        # ÖH D16 / OH-Z4-01: süzgeç eskiden blok düzeyindeki
        # ``safety_factor_source``a da bakıyordu ve bu, ANAHTAR-BAŞINA olması
        # gereken hükmü bloğun tamamına yayıyordu. ``safety_factor_source``
        # ``safety_factor`` alanının künyesidir, kardeşlerinin değil:
        # kullanıcı bir SF hedefi girdiğinde alan "user input (safety
        # factor)" yazar (ölçüldü, ``once.json`` -> ``verify_sf_kullanici``)
        # ve o tek cümle, çizilen cidarda hesaplanmış ``hoop_safety_factor``ı
        # da "girdinin geri okunması" saydırıyordu. Artık her aday YALNIZ
        # kendi ``<anahtar>_source`` künyesiyle elenir; ``safety_factor``
        # anahtarında bu zaten aynı alandır, yani eski davranış o anahtar
        # için birebir korunur.
        if _declares_input_readback(chamber.get(f'{key}_source')):
            continue
        measured, measured_key = value, key
        break

    tautological = chamber.get('safety_factor_is_tautological')
    mode = chamber.get('design_mode')
    if tautological is True:
        is_measured = False
    elif tautological is False:
        is_measured = measured is not None
    elif mode == 'verify':
        is_measured = measured is not None
    elif mode == 'size':
        is_measured = False
    else:
        # Beyan yok: sıvı bloğunun bugünkü hâli. Bloğun yayımladığı SF bir
        # ölçüm OLABİLİR ama bunu söyleyen yok -> iddia edilmez.
        is_measured = None

    # Geriye dönük tek-sayı alanı: ölçüm adayı yoksa bloğun genel
    # ``safety_factor`` alanına düşülür (eski davranışın sayısı korunur).
    reported = measured
    if reported is None:
        reported = (_real_scalar(chamber.get('safety_factor_total'))
                    or _real_scalar(chamber.get('hoop_safety_factor'))
                    or _real_scalar(chamber.get('safety_factor')))
    if is_measured is True and measured_key is None:
        # Ölçüm beyanı var ama adayı yok -> yine iddia edilmez.
        is_measured = None
    return reported, is_measured, target, basis


def _chamber_wall_block(struct):
    """Yapısal sonuçtaki cidar bloğunu şema sırasına göre bulur.

    Döner: (blok_sözlüğü, as_designed_mm|None, önerilen_mm|None, blok_adı|None,
            as_designed_kesin_mi)
    """
    struct = struct or {}
    for block_name, used_key, recommended_key, as_designed_is_authoritative \
            in CHAMBER_WALL_SCHEMAS:
        block = struct.get(block_name)
        if not isinstance(block, dict):
            continue
        used_mm = _real_nested(struct, (block_name, used_key))
        recommended_mm = _real_nested(struct, (block_name, recommended_key))
        if used_mm is None and recommended_mm is None:
            continue
        return (block, used_mm, recommended_mm, block_name,
                as_designed_is_authoritative)
    return {}, None, None, None, False


def _chamber_wall_design(motor_data):
    """Kamara cidarı: ÇİZİLECEK kalınlık + yapısal öneri + hangi SF'nin geçerli olduğu.

    v2.6.26 denetimi (Y5): CAD çizimi ve 3B katı, kullanıcının girdiği cidar
    kalınlığını YOK SAYIP her zaman yapısal analizin ÖNERDİĞİ kalınlığı
    çiziyordu. Ölçüldü: kullanıcı 3 / 5 / 10 / 20 mm girse de çizim 15,92 mm
    ve kamara kütlesi 232,04 kg SABİT kalıyordu. Malzeme değişiminde sapma
    daha büyüktü: Alüminyum 6061'de çizim 49,92 mm cidar gösterirken yapısal
    panel kullanıcının 5 mm'si için SF 0,466 ("güvensiz") diyordu — yani
    ekrandaki emniyet katsayısı ÇİZİLEN parçaya ait değildi.

    Çözüm tek kurala indirgenir: **gerilmelerin hesaplandığı kalınlık çizilir.**
    ``structural_analysis.chamber_analysis`` bunu zaten ayırıyor:
      * ``design_mode == 'verify'`` -> kullanıcı bir cidar girdi; gerilmeler ve
        emniyet katsayıları O kalınlığa aittir -> ``wall_thickness_used_mm``.
      * ``design_mode == 'size'``   -> kullanıcı girmedi; yazılım boyutlandırdı
        ve ``wall_thickness_used_mm == recommended_thickness``.
    Böylece çizilen geometri ile ekrandaki emniyet katsayısı AYNI parçayı
    anlatır. Öneri ayrıca ``recommended_mm`` alanında taşınır ve ikisi
    farklıysa ``note`` alanı bunu AÇIKÇA söyler (imalatçı hangi kalınlığın
    hangi SF'ye ait olduğunu görmeden torna tezgâhına gitmemeli).

    ÖH Z2 (defter P9B2-07, kritik). Yukarıdaki "verified against the pressure
    load" künyesi bir DOĞRULAMA iddiasıdır ama iki karar tek koşula
    bağlanmıştı: ``design_mode == 'verify' or as_designed_is_authoritative``.
    ``or``ın sağ tarafı katı ve sıvı motorda HER ZAMAN doğru olduğu için
    künye, çözücü aynı blokta *"NOT a verification ... it is the INPUT read
    back"* yazarken bile basılıyordu. Ölçüldü (27 Ağustos 2026,
    ``/calculate_solid``): ``design_mode='size'`` +
    ``safety_factor_is_tautological=True`` olan bir kasa DXF'e
    *"WALL THICKNESS = 2.00 mm [structural analysis (as-designed wall
    thickness, verified against the pressure load) [case_analysis]]"*
    etiketiyle iniyordu.

    Onarım iki kararı AYIRIR:
      * HANGİ kalınlık çizilir -> değişmedi (gerilmelerin hesaplandığı cidar;
        katı/sıvıda as-designed alan yetkilidir);
      * NE İDDİA EDİLİR -> yalnız çözücünün kendi dürüstlük bayrakları
        (``design_mode`` / ``safety_factor_is_tautological`` /
        ``safety_factor_basis``) doğrulama diyorsa "verified" yazılır.
        Beyan yoksa iddia da yoktur (fail-closed).

    Döner sözlük:
        thickness_m     -> çizilecek/kütlelenecek kalınlık [m] (None olabilir)
        source          -> insan okur kaynak etiketi (yalnız gerçek
                           doğrulamada "verified against the pressure load")
        as_designed_mm  -> gerilmelerin ait olduğu kalınlık [mm] (None olabilir)
        recommended_mm  -> yapısal analizin önerdiği kalınlık [mm] (None olabilir)
        design_mode     -> 'verify' | 'size' | None
        safety_factor   -> bloğun bu cidar için yayımladığı SF sayısı. Bunun
                           bir ÖLÇÜM mü yoksa tasarım hedefinin geri okunması
                           mı olduğunu ``safety_factor_is_measured`` söyler —
                           çıktıya basmadan önce O alan okunur.
        safety_factor_is_measured -> True | False | None (beyan yok)
        safety_factor_target      -> tasarım SF hedefi [-] (yalnız kıyas)
        safety_factor_basis       -> çözücünün kendi künye cümlesi (varsa)
        verified        -> cidar basınç yüküne karşı GERÇEKTEN doğrulandı mı
        note            -> çizilen ile önerilen farklıysa uyarı metni, yoksa None
    """
    struct = (motor_data or {}).get('structural_analysis') or {}
    # Üç motor tipinin üç ayrı şeması tek yerden çözülür (A8).
    (chamber, used_mm, recommended_mm, block_name,
     as_designed_is_authoritative) = _chamber_wall_block(struct)
    design_mode = chamber.get('design_mode')
    safety_factor, sf_is_measured, sf_target, sf_basis = _wall_safety_factor(
        chamber, block_name)

    # Çizilen cidar: kullanıcının/çözücünün gerilme hesabına giren kalınlık.
    # (Bu seçim DEĞİŞMEDİ; değişen, seçimin üstüne basılan iddia.)
    verified = False
    if (used_mm is not None
            and (design_mode == 'verify' or as_designed_is_authoritative)):
        thickness_mm = used_mm
        # Sayı yine yapısal analizin çıktı alanından (wall_thickness_used_mm /
        # wall_thickness_mm / wall_thickness) gelir; bu, gerilmelerin
        # hesaplandığı as-designed cidardır.
        if sf_is_measured is True:
            verified = True
            source = ('structural analysis (as-designed wall thickness, '
                      f'verified against the pressure load) [{block_name}]')
        elif sf_is_measured is False:
            # DİKKAT: olumsuz künyeler "verified against the pressure load"
            # dizesini İÇERMEZ. İçerselerdi metin taraması yapan her araç
            # (ve bu kusuru bulan ölçüm betiği) olumsuzlamayı olumlu damga
            # sanardı — künyenin kendisi yeni bir yanlış-pozitif kaynağı olur.
            source = ('structural analysis (as-designed wall thickness, SIZED '
                      'to the design safety factor target - NOT a '
                      f'pressure-load verification) [{block_name}]')
        else:
            source = ('structural analysis (as-designed wall thickness; this '
                      'analysis does not state whether the wall was checked '
                      f'against the pressure load) [{block_name}]')
    elif recommended_mm is not None:
        thickness_mm = recommended_mm
        source = f'structural analysis (recommended thickness) [{block_name}]'
    elif used_mm is not None:
        thickness_mm = used_mm
        source = ('structural analysis (thickness used in the stress check) '
                  f'[{block_name}]')
    else:
        thickness_mm = None
        source = 'not available'

    note = None
    if (thickness_mm is not None and recommended_mm is not None
            and abs(thickness_mm - recommended_mm) > WALL_MATCH_TOLERANCE_MM):
        if sf_is_measured is True:
            sf_sentence = (f'Safety factors reported for this motor belong to '
                           f'the as-designed {thickness_mm:.2f} mm wall, NOT '
                           f'to the recommended one.')
        elif sf_is_measured is False:
            sf_sentence = ('The reported safety factor is the design target '
                           'read back (the wall was sized to it), NOT a '
                           'safety factor measured on the drawn wall.')
        else:
            sf_sentence = ('This analysis publishes no safety factor measured '
                           'on the drawn wall, so no safety margin is claimed '
                           'for it here.')
        note = (f'drawn wall is the as-designed {thickness_mm:.2f} mm; the '
                f'structural sizing recommends {recommended_mm:.2f} mm. '
                + sf_sentence)

    return {
        'thickness_m': (thickness_mm / 1000.0) if thickness_mm is not None else None,
        'source': source,
        'as_designed_mm': used_mm,
        'recommended_mm': recommended_mm,
        'design_mode': design_mode,
        'safety_factor': safety_factor,
        'safety_factor_is_measured': sf_is_measured,
        'safety_factor_target': sf_target,
        'safety_factor_basis': sf_basis,
        'verified': verified,
        'note': note,
        'schema': block_name,
    }


def _wall_sf_basis_text(design):
    """Çözücü kendi künyesini yazmadıysa ihraç katmanının dürüst cümlesi.

    Sıvı motorun ``chamber_structure`` bloğu bir ``safety_factor_basis``
    yayımlamıyor; sayı basılmadığında kullanıcı NEDEN basılmadığını okumalı.
    """
    measured = design.get('safety_factor_is_measured')
    target = design.get('safety_factor_target')
    if measured is True:
        return ('safety factor computed on the drawn (as-designed) wall '
                'thickness')
    tail = ('' if target is None else
            f' The design target was {target:g} and is reported separately '
            f'as design_safety_factor_target.')
    if measured is False:
        return ('NOT a verification: the wall was sized to the design safety '
                'factor target, so the factor reported by the structural '
                'block is that target read back.' + tail)
    return ('this analysis publishes no safety factor computed on the drawn '
            'wall, and it does not state whether the wall was checked '
            'against the pressure load.' + tail)


def _chamber_wall_thickness_m(motor_data):
    """Kamara cidar kalınlığı [m] — çizilen/kütlelenen kalınlık.

    Döner: (kalınlık_m|None, kaynak_etiketi). Ayrıntı için
    :func:`_chamber_wall_design`.
    """
    design = _chamber_wall_design(motor_data)
    return design['thickness_m'], design['source']


def _chamber_wall_effective_m(motor_data, chamber_diameter_m):
    """3B katının ve kütle dökümünün GERÇEKTEN kullandığı cidar [m].

    Yapısal sonuç yoksa CAD katmanı geometrik yedek kurala düşer; mesh, kütle
    ve zarf çapı bu TEK fonksiyondan okur ki üçü çelişmesin. Yedek kural
    kullanıldığında çizim sözlüğü yine de sayı yazmaz (bkz.
    ``_generate_technical_drawings``) — imalata giden ölçü uydurulmaz.
    """
    design = _chamber_wall_design(motor_data)
    wall_m = design['thickness_m']
    if wall_m is not None:
        return wall_m, design['source']
    d = _real_scalar(chamber_diameter_m)
    if d is None:
        return None, design['source']
    return (max(0.004, CHAMBER_WALL_FALLBACK_FRACTION * d),
            'geometric fallback (no structural result in this run)')


# ---------------------------------------------------------------------------
# ÖN (BAŞ) KAPAK — imalat katısının kapağı, TEK çözümleyici
# ---------------------------------------------------------------------------
#
# ÖH Z2 (defter P15B4-10, yüksek). Kapak kalınlığı iki üreteçte AYNI uydurma
# kuralla, ikisinde de ayrı ayrı yazılıydı:
#     step_export.py      : cap   = min(max(1.6*wall, 8.0), 0.3*rc + 8.0)   [mm]
#     cad_visualization.py: cap_t = min(max(1.6*wall, 0.008), 0.3*r + 0.008) [m]
# Sonuç ölçüldü (27 Ağustos 2026, /calculate hibrit): yapısal analiz
# ``end_cap_analysis.head_thickness_used_mm = 1,9948 mm`` derken imalata giden
# STEP kapağı üç motor tipinde de **8,0000 mm** çıkıyordu (4,01x) — aynı
# dosyada cidar yapısal analize KAPILIYKEN kapak sabitti.
#
# Artık kapak da cidar gibi tek çözümleyiciden gelir. Kapak analizi yoksa
# (katı ve sıvı sonuçlarında ``end_cap_analysis`` bloğu YOK) katı üretilmeye
# devam eder ama kalınlık ADIYLA beyan edilen bir üreteç varsayımıdır ve bu
# beyan STEP parça adına gömülür — enjektör orifis halkasındaki 'ASSUMED'
# deseninin (step_export.py) eşleniği.
CAP_FALLBACK_WALL_MULTIPLIER = 1.6      # kapak/cidar oranı (üreteç varsayımı)
CAP_FALLBACK_MIN_MM = 8.0               # asgari kapak (üreteç varsayımı)
CAP_FALLBACK_RADIUS_FRACTION = 0.3      # üst sınır: bu kesir x kamara yarıçapı
CAP_FALLBACK_BASIS = (
    'ASSUMED closure head: this analysis run produced no end-cap analysis '
    '(structural_analysis.end_cap_analysis), so the thickness is a generator '
    'geometry assumption (1.6 x wall, floor 8 mm, capped at 0.3 x bore radius '
    '+ 8 mm) and NOT a pressure-vessel head calculation')


def json_safe_cad_design(cad_data):
    """``cad_design`` bloğunun YANITA çıkabilir kopyası.

    ÖH D20 / defter P9B1-31. ÖLÇÜLDÜ (taban ``14acd1d``, ``once.json``
    bölüm C; hibrit ``/calculate`` gövdesi):

        cad_design.assembly_meshes = [
          ["Chamber",   "<trimesh.Trimesh(vertices.shape=(130, 3), faces.shape=(256, 3))>"],
          ["Nozzle",    "<trimesh.Trimesh(vertices.shape=(2688, 3), faces.shape=(5376, 3))>"],
          ["Injector",  "<trimesh.Trimesh(vertices.shape=(1090, 3), faces.shape=(2240, 3))>"],
          ["Fuel Grain","<trimesh.Trimesh(vertices.shape=(128, 3), faces.shape=(256, 3))>"],
        ]

    yani yanıt gövdesinde ``'<trimesh.'`` dizesi **4 kez** geçiyordu. Bu bir
    VERİ DEĞİLDİR: Python nesnesinin ``repr()`` METNİ, ``json.dumps(...,
    default=str)`` yolundan kaçmıştır. Tüketici ne köşe sayısını
    ayrıştırabilir (dize biçimi sözleşme değildir, trimesh sürümüyle
    değişir) ne de ağı kullanabilir; okuduğu şey sunucu belleğindeki bir
    nesnenin insan-okur betimi.

    Onarım: ağ nesneleri yanıttan çıkarılır ve yerine AYNI nesneden GERÇEKTEN
    ÖLÇÜLEN makine-okur künye konur (uydurma alan yok — hepsi trimesh'in
    kendi ölçümü). Süreç içi tüketiciler (``export_stl_files``) sözlüğün
    KENDİSİNİ okumaya devam eder: bu fonksiyon KOPYA döner, kaynağa
    dokunmaz.
    """
    if not isinstance(cad_data, dict):
        return cad_data
    if 'assembly_meshes' not in cad_data:
        return cad_data
    out = dict(cad_data)
    ozet = []
    for item in (cad_data.get('assembly_meshes') or []):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            ad, mesh = item
        else:
            ad, mesh = None, item
        kayit = {'name': (str(ad) if ad is not None else None)}
        for alan, oku in (
                ('vertex_count', lambda m: int(len(m.vertices))),
                ('face_count', lambda m: int(len(m.faces))),
                ('watertight', lambda m: bool(m.is_watertight)),
                ('volume_m3', lambda m: float(m.volume)),
                ('surface_area_m2', lambda m: float(m.area)),
        ):
            try:
                kayit[alan] = oku(mesh)
            except Exception:
                # Ölçülemeyen alan UYDURULMAZ; adı yok sayılır.
                pass
        ozet.append(kayit)
    out['assembly_mesh_summary'] = ozet
    # Ağ nesnelerinin kendisi yanıta ÇIKMAZ (repr() metni veri değildir).
    out.pop('assembly_meshes', None)
    return out


def drawable_hole_count(hole_count):
    """Çizilebilir delik sayısı (int) ya da ``None``.

    ÖH D20 / defter P9B1-26. ÖLÇÜLDÜ (``once.json`` bölüm B, taban 14acd1d,
    ``DetailedCADGenerator`` üstünde):

    | girdi | ``_create_coaxial_injector_holes`` | ``_create_impinging_injector_holes`` |
    |---|---|---|
    | ``0``   | **ZeroDivisionError** (``hole_count // rows``, ``rows=0``) | 0 iz |
    | ``0,5`` | **ZeroDivisionError** (float floor division) | **TypeError** |
    | ``-3``  | **ValueError** (``sqrt(-3)`` -> NaN -> ``int(NaN)``) | 0 iz |

    Yani iki KARDEŞ enjektör deseni aynı girdiye üç farklı hüküm veriyordu:
    biri çöküyor, öbürü sessizce boş çiziyor, üçüncü hâlde tip hatası. Delik
    sayısı bir ÖLÇÜMDÜR (enjektör çözücüsünden gelir); çözülemediyse desen
    ÇİZİLMEZ — çağıran zaten efsanede ``'Injector Face (holes not drawn: ...)'``
    diyerek bunu SÖYLER. Uydurma delik de yoktur, çökme de.

    Kabul ölçütü: sonlu, tam sayıya eşit ve ``>= 1``. Kayan nokta ``4.0``
    kabul edilir (enjektör çözücüleri sayıyı float yayımlayabiliyor),
    ``0.5`` edilmez — yarım delik delinemez.
    """
    # ÖH D31 / OH-D30-08 (P15B2-01 dağıtımı): okuma kapısı MERKEZDEN.
    # ``bool`` reddi, ``float()`` çevrimi ve sonluluk denetimi burada
    # yerel olarak yazılıydı; aynı kötü girdi modüle göre farklı kadere
    # uğramasın diye üç adım ``hrma.utils.input_guard.finite_number``a
    # bağlandı. Kabul ölçütü DEĞİŞMEDİ (tam sayıya eşit ve >= 1);
    # yalnız sayı okuma tek tanım noktasından geçiyor.
    n = finite_number(hole_count)
    if n is None or n < 1 or n != int(n):
        return None
    return int(n)


# ---------------------------------------------------------------------------
# ``cad_design`` ŞEKİL ADI (ÖH D21 / defter P15B4-05 + P9B1-31, yüksek)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (taban ``35aa279``, ``once.json`` bölüm G): ``cad_design`` adı
# altında BİRBİRİNDEN BAĞIMSIZ şekiller yayımlanıyor ve okuyucu hangisini
# aldığını soramıyordu:
#
#   /calculate_solid  -> 10 anahtar, ``schema='hrma.solid.cad_design/1'``,
#                        ``case_design`` VAR
#   /calculate        ->  6 anahtar, ``schema`` YOK, ``case_design`` YOK
#   /calculate_liquid ->  bloğun kendisi YOK
#
# Katı yarısı D18'de adlandırılmıştı (``SOLID_CAD_DESIGN_SCHEMA``); bu
# üreticinin şekli adsız kalmıştı. Adsız şekil, tüketicide ``.get('case_design',
# {})`` biçiminde SESSİZ YEDEĞE dönüşüyor: okuyucu "alan yok" ile "bu benim
# şeklim değil"i ayırt edemiyor (D17 bekçisinin ölçtüğü kusurun ta kendisi,
# ``flight_vehicle._get(...) is None``).
#
# Ad, motor TİPİNİ değil ÜRETİCİYİ anlatır: bu blok
# ``MotorCADDesigner.generate_3d_motor_assembly`` çıktısıdır ve katı/sıvı
# ihraç uçlarından da aynı şekliyle çağrılır. Uydurma alan eklenmez — eklenen
# tek şey şeklin kendi adıdır (sürümlü, katı kardeşiyle aynı kalıpta).
CAD_VISUALIZATION_SCHEMA = 'hrma.cad_visualization.motor_assembly/1'


#: :func:`_front_cap_design` ``require_analysis=True`` ile çağrıldığında
#: (imalat çıktısı) kapak analizi yoksa dönen künye. ÖH D21 / defter P9B1-17.
CAP_REFUSED_NO_ANALYSIS = (
    'closure head thickness is not available from the structural analysis '
    '(looked for structural_analysis.end_cap_analysis.flat_head_thickness); '
    'the closure head is part of the pressure boundary and is NOT sized by a '
    'generator geometry rule for a manufacturing output. Run the structural '
    'analysis first.')


def _front_cap_design(motor_data, wall_mm=None, bore_radius_mm=None,
                      require_analysis=False):
    """İmalat katısının ÖN KAPAĞI: kalınlık [mm] + künye.

    İhraç katmanı kapağı DÜZ (revolve edilmiş dikdörtgen profil) modeller,
    bu yüzden yapısal analizin *düz kapak* kalınlığı okunur
    (``end_cap_analysis.flat_head_thickness``). Analiz dişbükey (dished)
    kapak öneriyorsa bu AÇIKÇA künyeye yazılır: modellenen parça düz olduğu
    için o tipin kalınlığı kullanılamaz, ama okuyucu farkı görmelidir.

    ``require_analysis`` (ÖH D21 / defter P9B1-17) — İMALAT KAPISI.

    ÖLÇÜLDÜ (taban ``35aa279``, ``once.json`` bölüm F): kapak analizi
    OLMAYAN bir gövdede aynı dosyadaki iki basınç-sınırı parçası birbirine
    zıt davranıyordu::

        cidar  (_chamber_wall_design)  -> thickness_m = None, 'not available'
                 => step_export REDDEDER: "refusing to emit a manufacturing
                    STEP with an assumed wall. Run the structural analysis
                    first."
        kapak  (_front_cap_design)     -> thickness_mm = 8.0 mm ÜRETİLİR
                 => imalat STEP'i, hiçbir yapısal analize sorulmamış bir
                    kapakla iniyordu (künye 'ASSUMED ...' diyordu, ama
                    beyan çözüm değildir: torna tezgâhına giden sayı yine
                    üreteç kuralının kendisiydi).

    Kapak, kamara cidarıyla AYNI basınç sınırının parçasıdır ve gerilmesi
    Roark Tablo 11.2 düz plaka bağıntısıyla ``structural_analysis``te ZATEN
    hesaplanıyor (``_analyze_end_caps``). İmalat çıktısı için doğru davranış
    kardeşininkiyle aynıdır: analiz yoksa sayı UYDURULMAZ, çıktı reddedilir.

    ``require_analysis=False`` (varsayılan) önizleme/çizim yolları içindir;
    orada kalınlık üreteç varsayımı olarak çizilmeye devam eder ve künye
    (``source`` + ``from_analysis``) bunu söyler.

    DİKKAT — bu kapı BUGÜN hiçbir çağrı yerinde AÇIK DEĞİL. ``step_export``
    onu ``True`` ile çağırmayı deniyordu; ölçüldü ki katı ve sıvı motorların
    yapısal analizi kapak kalınlığı hiç yayımlamadığı için imalat STEP'i o
    iki motor tipinde tamamen kayboluyor (dört dosyada 27 bekçi kırmızı).
    Gerekçenin tamamı ``step_export.generate_step_assembly`` içindeki
    "ÖH D21 KAPANIŞ NOTU" bloğundadır; kalem DEFTERDE AÇIK
    (P9B1-17, kısmen).

    Döner sözlük:
        thickness_mm    -> çizilecek kapak kalınlığı [mm] (None olabilir)
        source          -> künye metni ('ASSUMED ...' ise analiz yok demektir)
        from_analysis   -> kalınlık yapısal analizden mi geldi
        flat_mm         -> analizin düz kapak kalınlığı [mm]
        recommended_type-> 'flat' | 'dished' | None
        used_mm         -> analizin DEĞERLENDİRDİĞİ kapak kalınlığı [mm]
        design_mode     -> 'verify' | 'size' | None
    """
    struct = (motor_data or {}).get('structural_analysis') or {}
    cap = struct.get('end_cap_analysis')
    cap = cap if isinstance(cap, dict) else {}
    flat_mm = _real_scalar(cap.get('flat_head_thickness'))
    used_mm = _real_scalar(cap.get('head_thickness_used_mm'))
    rec_type = cap.get('recommended_type')
    design_mode = cap.get('design_mode')

    if flat_mm is not None:
        source = ('structural analysis (flat closure head at chamber '
                  'pressure) [end_cap_analysis]')
        if rec_type == 'dished' and used_mm is not None:
            source += (f'; the analysis recommends a DISHED head at '
                       f'{used_mm:.2f} mm - this solid models a FLAT head, so '
                       f'the flat-head thickness is used')
        return {'thickness_mm': flat_mm, 'source': source,
                'from_analysis': True, 'flat_mm': flat_mm,
                'recommended_type': rec_type, 'used_mm': used_mm,
                'design_mode': design_mode}

    # İMALAT KAPISI (P9B1-17): analiz yoksa üreteç kuralı ÇALIŞTIRILMAZ.
    # Cidarın ``_chamber_wall_design`` içindeki davranışının eşleniği.
    if require_analysis:
        return {'thickness_mm': None, 'source': CAP_REFUSED_NO_ANALYSIS,
                'from_analysis': False, 'flat_mm': None,
                'recommended_type': rec_type, 'used_mm': used_mm,
                'design_mode': design_mode}

    # Yedek kural (kapak analizi yok): kalınlığın KENDİSİ değişmez, yalnız
    # tek yerde tanımlanır ve künyesiyle birlikte döner.
    wall_mm = _real_scalar(wall_mm) or 0.0
    bore_radius_mm = _real_scalar(bore_radius_mm)
    if bore_radius_mm is None:
        return {'thickness_mm': None, 'source': 'not available',
                'from_analysis': False, 'flat_mm': None,
                'recommended_type': rec_type, 'used_mm': used_mm,
                'design_mode': design_mode}
    thickness_mm = min(
        max(CAP_FALLBACK_WALL_MULTIPLIER * wall_mm, CAP_FALLBACK_MIN_MM),
        CAP_FALLBACK_RADIUS_FRACTION * bore_radius_mm + CAP_FALLBACK_MIN_MM)
    return {'thickness_mm': thickness_mm, 'source': CAP_FALLBACK_BASIS,
            'from_analysis': False, 'flat_mm': None,
            'recommended_type': rec_type, 'used_mm': used_mm,
            'design_mode': design_mode}


#: Kamara/kasa malzemesinin yaşadığı ÜÇ ayrı yapısal şema — cidar kalınlığı
#: için ``CHAMBER_WALL_SCHEMAS``da olan ayrım MALZEME için de gereklidir.
#:
#: ÖH D15 (defter P9B1-14). Kusur: çözümleyici yalnız
#: ``design_parameters.material`` (hibrit modülü) ve ``motor_data
#: .chamber_material`` yollarına bakıyordu. Katı motor malzemeyi
#: ``case_analysis.case_material``, sıvı motor ``chamber_structure
#: .material_key`` altında yayımlar; ikisi de bulunamıyordu. Ölçüldü
#: (31 Ağustos 2026, ``motor_liquid`` fikstürü): çözücü
#: ``material_key='inconel_718'`` / ``material='Inconel 718 (aged)'`` yazarken
#: ihraç katmanı ``chamber_material = 'NOT AVAILABLE'`` basıyor ve kütleyi
#: sessizce 7850 kg/m3 ile hesaplıyordu (Inconel 8220 kg/m3 -> %4,71 hata).
#: Her giriş: (blok_adı, anahtar_adayları...)
CHAMBER_MATERIAL_SCHEMAS = (
    ('design_parameters', ('material', 'material_key')),
    ('case_analysis', ('case_material', 'material_key', 'material')),
    ('chamber_structure', ('material_key', 'material')),
    ('chamber_analysis', ('material_key', 'material')),
)

#: Yoğunluk hiçbir yoldan çözülemediğinde kütle hesabının kullandığı kayıt.
#: ÖH D15 (defter P9B1-14): bu yedek eskiden SESSİZDİ — ``mass_basis`` alanı
#: "materials_db yoğunluğu" diyordu ama sayı seçilen malzemeden gelmiyordu.
#: Artık yedeğe düşüldüğünde ``chamber_mass_density_source`` bunu ADIYLA
#: söyler; künye "seçilen malzeme" iddia edemez.
CHAMBER_DENSITY_FALLBACK_KEY = 'steel_4130'
#: Lüle yoğunluğunun yedeği — kamaranınkiyle AYNI ilke.
#: ÖH D15 (defter P9B1-18): lüle kütlesi "AUTHORITATIVE ... same contour, wall
#: and material as the STEP/STL parts" künyesiyle yayımlanıyordu; oysa ölçüldü
#: (31 Ağustos 2026) katı ve sıvı koşularında ``nozzle_geometry`` BOŞ ve
#: ``nozzle_material`` YOK — yani künyenin dayandığı iki girdinin İKİSİ de o
#: koşuda hesaplanmamış üreteç varsayımıydı ve künye bunu söylemiyordu.
NOZZLE_DENSITY_FALLBACK_KEY = 'graphite'


def _nozzle_density_resolved(motor_data):
    """Lüle kütlesinin kullandığı yoğunluk [kg/m3] + KAYNAK künyesi.

    ÖH D15 (defter P9B1-18). Yedek eskiden SESSİZDİ: malzeme yoksa yoğunluk
    grafitten alınıyor, künye ise "same ... material as the STEP/STL parts"
    diyordu. Artık yedeğe düşüldüğü ADIYLA söylenir.
    """
    md = motor_data or {}
    key = md.get('nozzle_material') or md.get('throat_material')
    if key:
        try:
            rho = _real_scalar(get_material(str(key))['density'])
        except Exception:
            rho = None
        if rho is not None:
            return rho, f'nozzle material "{key}" as selected by this run'
    rho = get_material(NOZZLE_DENSITY_FALLBACK_KEY)['density']
    return rho, (
        'this run publishes no nozzle_material / throat_material, so the '
        f'NAMED generator fallback {NOZZLE_DENSITY_FALLBACK_KEY} '
        f'({rho:g} kg/m3) was used - NOT a material this run selected')


# ---------------------------------------------------------------------------
# Lüle et kalınlığı — üreteç kuralı (ÖH Z5S / defter P9B2-29)
# ---------------------------------------------------------------------------
#: Lüle cidarı çözücü yayımlamadığında HİÇBİR yapısal ya da termal analizden
#: gelmiyor: aşağıdaki iki sayı bir üreteç kuralıdır. Değerler v2.6.x'ten
#: beri yerinde duruyor, ÖH Z5S'te adlandırıldı ve parça adında BEYAN edilir
#: hâle geldi. ÖH V3 CAD A1: TEK tanım noktası burasıdır; ``step_export``
#: aynı adları buradan yeniden ihraç eder (bu modül build123d yüklemez).
NOZZLE_WALL_MIN_MM = 3.0
NOZZLE_WALL_THROAT_FRACTION = 0.1
#: Boğaz çapı çözülemediğinde kullanılan üreteç yedeği [m]. Bu yedek
#: ısırdığında da beyan edilir (sessiz düşüş yok).
NOZZLE_WALL_THROAT_FALLBACK_M = 0.02


def _nozzle_wall_design(motor_data):
    """Lüle et kalınlığı — STEP, STL ve kütle için TEK çözümleyici.

    Döner sözlük:
        thickness_m     -> çizilecek/kütlelenecek et [m]
        source          -> insan okur künye (parça adına ve kütle dökümüne
                           aynen basılır)
        published       -> et çözücüden mi geldi (``nozzle_geometry
                           .wall_thickness``) yoksa üreteç kuralından mı
        published_mm    -> çözücünün yayımladığı et [mm] (yoksa None)
        throat_resolved -> kural dalında boğaz çapı çözüldü mü
        safety_factor_raw / safety_factor_field -> yayımlanan etin EMNİYET
                           katsayısı (ham değer; imalat kapısı okur)

    ÖH D15 (defter P9B1-18). Ölçüldü (31 Ağustos 2026): katı ve sıvı
    sonuçlarında ``nozzle_geometry`` sözlüğü BOŞ, dolayısıyla cidar
    ``max(3 mm; 0,1 x d_bogaz)`` üreteç kuralından geliyordu (katı 3,66 mm,
    sıvı 3,08 mm) ve bu, kütlenin "AUTHORITATIVE" künyesinde HİÇ geçmiyordu.

    ÖH V3 CAD A1 · H2 (7 Eki CAD kontrolü, ÖLÇÜLDÜ): bu fonksiyon STL'in ve
    kütle dökümünün etini veriyordu ama STEP üreticisi onu ÇAĞIRMIYOR, kuralı
    kendi içinde yeniden hesaplıyordu. Hibrit örnekte çözücü
    ``nozzle_geometry.wall_thickness = 7,185 mm`` (thin_wall_hoop) yayımlarken
    STEP lülesi 3,00 mm et ile çiziliyor ve parça adına "NOT from a structural
    or thermal analysis" yazıyordu; aynı paketin iki lüle dosyası 2,53x farklı
    hacimdeydi. Artık STEP de bu sözlükten okur (tek kaynak), künye çözücünün
    kendi dayanağını (``wall_thickness_basis``) ve etin boyutlandırıldığı
    emniyet katsayısını taşır.

    Kuralın sayıları bu modülde TEK yerde tanımlıdır (yukarıda);
    ``step_export`` onları buradan ithal eder — STEP katısı ile STL/kütle
    aynı cidarı kullanmak zorundadır. Fonksiyon ``step_export``i İTHAL
    ETMEZ: imalat emniyet kapısının reddettiği istek build123d yığınını
    yüklemez (H3-B14).
    """
    md = motor_data or {}
    geo = md.get('nozzle_geometry')
    geo = geo if isinstance(geo, dict) else {}
    sf_raw = geo.get('wall_safety_factor')
    out = {'safety_factor_raw': sf_raw,
           'safety_factor_field': 'nozzle_geometry.wall_safety_factor',
           'throat_resolved': True}
    published = _real_scalar(geo.get('wall_thickness'))
    if published is not None:
        src = 'nozzle_geometry.wall_thickness published by this run'
        basis = geo.get('wall_thickness_basis')
        if isinstance(basis, str) and basis.strip():
            src += f' (basis: {basis.strip()}'
            sf = _real_scalar(sf_raw)
            if sf is not None:
                src += (f', sized to nozzle_geometry.wall_safety_factor = '
                        f'{sf:g}')
            src += ')'
        out.update(thickness_m=published / 1000.0, source=src,
                   published=True, published_mm=published)
        return out
    src = ('ASSUMED generator rule max('
           f'{NOZZLE_WALL_MIN_MM:g} mm, {NOZZLE_WALL_THROAT_FRACTION:g} x '
           'throat diameter) - this run publishes no '
           'nozzle_geometry.wall_thickness and NO structural or thermal '
           'analysis of the nozzle was performed')
    d_t = _real_scalar(md.get('throat_diameter'))
    if d_t is None:
        d_t = NOZZLE_WALL_THROAT_FALLBACK_M
        out['throat_resolved'] = False
        src += ('; the throat diameter could not be resolved either, so the '
                f'generator fallback {NOZZLE_WALL_THROAT_FALLBACK_M * 1000:.2f}'
                ' mm was used inside that rule')
    out.update(thickness_m=max(NOZZLE_WALL_MIN_MM / 1000.0,
                               NOZZLE_WALL_THROAT_FRACTION * d_t),
               source=src, published=False, published_mm=None)
    return out


def _nozzle_wall_design_m(motor_data):
    """Lüle et kalınlığı [m] + KAYNAK künyesi (``_nozzle_wall_design`` özeti).

    Eski çağıranların ``(kalınlık_m, künye)`` sözleşmesi korunur; karar
    yalnız :func:`_nozzle_wall_design`de verilir.
    """
    design = _nozzle_wall_design(motor_data)
    return design['thickness_m'], design['source']


# ---------------------------------------------------------------------------
# Lüle cidar profili — STEP, STL ve kütle için TEK kaynak (V301 bilinen C1)
# ---------------------------------------------------------------------------
#: Profil birimleri: çağıran kendi uzayında okur (STEP mm, trimesh metre).
#: Ölçek BURADA uygulanır ki iki üretici aynı sayıyı aynı işlemle alsın.
NOZZLE_PROFILE_UNITS = ('mm', 'm')


def nozzle_wall_profile(motor_data, unit='mm', require_solved_length=False):
    """Lüle cidar profili: iç kontur + et kuralı + dış kontur (TEK kaynak).

    V301 bilinen C1 (22 Eki 2026). STEP (``step_export._revolve_smooth_
    nozzle``), STL (``MotorCADDesigner._nozzle_solid``) ve kütle dökümü
    (``_estimate_component_mass('nozzle')``) lüleyi buradan okur. Eskiden
    üçü de ``sample_nozzle_inner_contour``u ve et çözümleyicisini AYRI AYRI
    çağırıp dış konturu kendi içinde yeniden kuruyordu (STEP ``(z, r + et)``,
    STL ``(r + et, z)`` ters sırayla, kütle ``r_orta + et``): et kuralı üç
    yerde yazılıydı.

    Kural: dış kontur iç konturun AYNI eksenel istasyonlarında yarıçapça
    ``et`` kadar dışarı kaydırılmışıdır (radyal ofset; her istasyonda
    et = ``wall``). Et ``_nozzle_wall_design``den gelir.

    ``unit``: ``'mm'`` ya da ``'m'``. Noktalar ölçeklenir, et
    ``thickness_m``den o birime çevrilir; dış kontur ölçeklenmiş iç kontur
    + ölçeklenmiş et ile kurulur (kayan noktada çağıranların eski
    işlemleriyle BİT-AYNI; ölçüm ``docs/scofield/raw/OH/V301/bilinen/cad``).

    ``require_solved_length``: imalat STEP'i ``True`` geçirir — ıraksak boy
    çözücüden gelmiyorsa örnekleyicinin adlı ``ValueError``u aynen yükselir
    (A5, fail-closed). STL/görünüm yolu eski davranışı korur.

    Döner sözlük:
        inner       -> [(z, r), ...] iç kontur (z = 0 yakınsak girişi)
        outer       -> [(z, r + wall), ...] AYNI istasyonlarda dış kontur
        wall        -> et (``unit`` biriminde)
        wall_design -> ``_nozzle_wall_design`` sözlüğü (künye, kaynak)
        meta        -> örnekleyicinin ``meta``sı (mm: boğaz, çıkış, tür ...)
        unit        -> ``unit``
    """
    if unit not in NOZZLE_PROFILE_UNITS:
        raise ValueError(f'nozzle profile unit must be one of '
                         f'{NOZZLE_PROFILE_UNITS}, got {unit!r}')
    pts_mm, meta = sample_nozzle_inner_contour(
        motor_data, require_solved_length=require_solved_length)
    design = _nozzle_wall_design(motor_data)
    if unit == 'mm':
        inner = [(z, r) for z, r in pts_mm]
        wall = design['thickness_m'] * 1000.0
    else:
        inner = [(z / 1000.0, r / 1000.0) for z, r in pts_mm]
        wall = design['thickness_m']
    outer = [(z, r + wall) for z, r in inner]
    return {'inner': inner, 'outer': outer, 'wall': wall,
            'wall_design': design, 'meta': meta, 'unit': unit}


def _grain_outer_radius_m(motor_data):
    """Çizilecek yakıt tanesinin DIŞ yarıçapı [m] — ÇÖZÜCÜNÜN kendi çapından.

    Döner: ``(yarıçap_m|None, künye)``.

    ÖH D15 (defter P9B1-04). Kusur: dış çap çözücüden HİÇ okunmuyordu; tane
    ``kamara_yarıçapı - liner`` ile çiziliyordu ve ``liner`` uydurma bir
    kuraldan geliyordu (``min(max(0,02.D, 1,5 mm), 5 mm)``). Ölçüldü
    (31 Ağustos 2026): hibritte çözücü 152,53 mm derken STL 146,43 mm
    (hacim −%11,9), katıda 100,00 mm derken 96,00 mm (hacim −%9,5).
    ``fuel_grain.stl`` doğrudan kalıba/imalata gidiyor; yakıtın onda biri
    kullanıcıya haber verilmeden yok ediliyordu ve hiçbir çıktı alanı bu
    "liner"ı beyan etmiyordu.

    Çözücü dış çapı yayımlamıyorsa None döner — çağıran taneyi ÇİZMEZ ve
    gerekçeyi adlandırır (uydurma bir kalınlık çıkarılmaz).
    """
    md = motor_data if isinstance(motor_data, dict) else {}
    nodes = []
    geo = md.get('motor_geometry')
    if isinstance(geo, dict):
        nodes.append((geo, 'motor_geometry'))
    nodes.append((md, 'motor result'))
    for node, label in nodes:
        gd = node.get('grain_design') if isinstance(node, dict) else None
        if not isinstance(gd, dict):
            continue
        for key in ('grain_outer_diameter_mm', 'outer_diameter_mm'):
            d_mm = _real_scalar(gd.get(key))
            if d_mm is not None:
                return (d_mm / 2000.0,
                        f'{label}.grain_design.{key} (mm, declared)')
    return None, ('this analysis run publishes no grain outer diameter '
                  '(grain_design.grain_outer_diameter_mm / outer_diameter_mm)')


# ---------------------------------------------------------------------------
# ÖH V3 CAD A1 — YERLEŞİM ÇÖZÜCÜSÜ (STEP, STL ve DXF için TEK kaynak)
# ---------------------------------------------------------------------------
#
# 7 Eki bağımsız CAD kontrolü (``docs/scofield/raw/OH/CAD/kontrol-2026-10-07``,
# FreeCAD başsız) ÖLÇTÜ: hibrit çözücü kamarayı üç kesimle kurar
# (``hybrid_rocket_engine``: L = L_ön + L_tane + L_art) ve iki sınırı
# ``pre_chamber_length`` / ``post_chamber_length`` adıyla YAYIMLAR. CAD ise
# tanenin ön yüzünü kendi ``0,35 x boş boy`` kuralıyla 33,79 mm'ye koyuyor
# (çözücü 60,34 mm; -%44) ve parça adına "NO solver publishes the axial
# position of the grain" yazıyordu — iki yanlış birden (H3). Konum artık
# çözücü yayımlıyorsa ORADAN gelir; üç üretici aynı fonksiyonu okur. Çözücü
# yayımlamıyorsa (katı motor) her üretecin beyanlı kuralı aynen sürer (o
# kuralların birleştirilmesi H7 / CAD A2 kalemidir).

#: Yayımlanan kamara düzeninin kapanış toleransı [mm]. Üç sayı (ön oda, tane,
#: art oda) AYNI çözücü koşusunun kayan noktalı çıktısıdır ve toplamları
#: yayımlanan kamara boyunu verir; fark yalnız yuvarlamadır (ölçüldü: örnek
#: hibritte 0). 10 µm imalat çözünürlüğünün altındadır; daha büyük bir fark
#: yanıtta İKİ ayrı kamara düzeni demektir ve yerleşim kazanılmamış sayılır.
GRAIN_LAYOUT_CLOSURE_TOLERANCE_MM = 0.01

#: Çözücünün ön/arka yanma odası boylarını yayımladığı alanlar (hibrit
#: çözücü ``basic_results``). Burada yeni alan adı icat edilmez.
GRAIN_LAYOUT_PRE_FIELD = 'pre_chamber_length'
GRAIN_LAYOUT_POST_FIELD = 'post_chamber_length'


class GrainLayoutError(ValueError):
    """Çözücünün yayımladığı tane yerleşimi çizilemiyor (sığmıyor/kapanmıyor).

    ``invalid_fields`` aile sözleşmesindeki biçimdedir; üreticiler bunu kendi
    ret sınıflarına (STEP 422, DXF 422) aynen taşır.
    """

    def __init__(self, message, invalid_fields=()):
        super().__init__(message)
        self.invalid_fields = [dict(k) for k in (invalid_fields or ())]


def solver_grain_front_mm(motor_data, chamber_length_mm, stack_length_mm):
    """Tane yığınının ÖN YÜZÜ [mm] — çözücü yayımlıyorsa ONDAN.

    Döner ``None``: çözücü tanenin eksenel konumunu yayımlamıyor (katı
    motor); çağıran kendi BEYANLI üreteç kuralına düşer. Aksi hâlde sözlük:
    ``front_mm`` (ön yüz), ``pre_mm``, ``post_mm`` (yayımlanmadıysa None) ve
    parça adına/çizime basılacak ``note``.

    FAIL-CLOSED (``GrainLayoutError``): yayımlanan düzen kamaraya SIĞMIYORSA
    ya da ön oda + yığın + art oda yayımlanan kamara boyunu KAPATMIYORSA
    (``GRAIN_LAYOUT_CLOSURE_TOLERANCE_MM``) imalat geometrisi üretilmez —
    hangi düzenin imalata gideceği kazanılmamıştır. Birimi
    ``motor_geometry.resolve_length_m`` çözer (tek kaynak); yanlış okunmuş
    bir birim de bu kapanış denetimine takılır.
    """
    from hrma.export.motor_geometry import resolve_length_m
    md = motor_data if isinstance(motor_data, dict) else {}
    pre_m, pre_src = resolve_length_m(md, GRAIN_LAYOUT_PRE_FIELD)
    if pre_m is None:
        return None
    pre_mm = float(pre_m) * 1000.0
    post_m, post_src = resolve_length_m(md, GRAIN_LAYOUT_POST_FIELD)
    post_mm = float(post_m) * 1000.0 if post_m is not None else None
    L = float(chamber_length_mm)
    S = float(stack_length_mm)
    tol = GRAIN_LAYOUT_CLOSURE_TOLERANCE_MM
    if pre_mm + S > L + tol:
        raise GrainLayoutError(
            f'the solver places the grain front face at {pre_mm:.2f} mm '
            f'({GRAIN_LAYOUT_PRE_FIELD}) and the grain stack is {S:.2f} mm '
            f'long, so it ends at {pre_mm + S:.2f} mm, beyond the '
            f'{L:.2f} mm chamber; the published layout does not fit and no '
            'manufacturing geometry is drawn for it.',
            invalid_fields=[{
                'field': GRAIN_LAYOUT_PRE_FIELD,
                'reason': 'grain_layout_does_not_fit',
                'pre_chamber_length_mm': round(pre_mm, 4),
                'grain_stack_mm': round(S, 4),
                'chamber_length_mm': round(L, 4)}])
    if post_mm is not None and abs(pre_mm + S + post_mm - L) > tol:
        raise GrainLayoutError(
            f'the published chamber layout does not close: '
            f'{GRAIN_LAYOUT_PRE_FIELD} {pre_mm:.4f} mm + grain stack '
            f'{S:.4f} mm + {GRAIN_LAYOUT_POST_FIELD} {post_mm:.4f} mm = '
            f'{pre_mm + S + post_mm:.4f} mm, but the chamber is {L:.4f} mm '
            f'(tolerance {tol:g} mm). The response carries two different '
            'chamber layouts, so it is not established which one goes to '
            'manufacturing; no geometry is drawn on a guess.',
            invalid_fields=[{
                'field': GRAIN_LAYOUT_POST_FIELD,
                'reason': 'grain_layout_not_closed',
                'pre_chamber_length_mm': round(pre_mm, 4),
                'grain_stack_mm': round(S, 4),
                'post_chamber_length_mm': round(post_mm, 4),
                'chamber_length_mm': round(L, 4),
                'tolerance_mm': tol}])
    note = (f'axial position from the solver layout: front face at '
            f'{pre_mm:.2f} mm from the injector face = '
            f'{GRAIN_LAYOUT_PRE_FIELD} published by this run ({pre_src})')
    if post_mm is not None:
        note += (f'; {GRAIN_LAYOUT_PRE_FIELD} {pre_mm:.2f} + grain '
                 f'{S:.2f} + {GRAIN_LAYOUT_POST_FIELD} {post_mm:.2f} = '
                 f'{L:.2f} mm closes the chamber')
    else:
        note += (f'; {GRAIN_LAYOUT_POST_FIELD} is not published, so the '
                 'layout closure against the chamber length is not checked')
    return {'front_mm': pre_mm, 'pre_mm': pre_mm, 'post_mm': post_mm,
            'pre_source': pre_src, 'post_source': post_src, 'note': note}


# ---------------------------------------------------------------------------
# ÖH V3 CAD A2 · H7 — TANE YIĞINI PLANI VE EKSENEL YERLEŞİM (tek kaynak)
# ---------------------------------------------------------------------------
# Aşağıdaki plan fonksiyonları ``step_export``ten TAŞINDI (gövdeleri
# değişmedi); gerekçe ``step_export``teki yeniden ihraç notunda.

#: Grain ön yüzünün, kamaradaki BOŞ boyun neresine oturduğu. Hiçbir
#: çözücüden gelmez — üreteç yerleşim kuralıdır ve parça adında beyan edilir.
GRAIN_AXIAL_POSITION_FRACTION = 0.35
#: Boş boy bundan küçükse bile bırakılan asgari ön boşluk [mm].
GRAIN_AXIAL_MIN_SLACK_MM = 4.0

#: Segment boyu ile yayımlanan toplam tane boyunun uyuşma toleransı [mm].
#: İkisi aynı çözücüden gelir (``L_grain`` ve ``L_grain / n``), fark yalnız
#: kayan nokta yuvarlamasıdır; daha büyük bir sapma İKİ AYRI hüküm demektir
#: ve katı üretilmez.
GRAIN_SEGMENT_LENGTH_TOLERANCE_MM = 0.01


def _grain_segment_plan(md):
    """Yakıt tanesinin segment planı — ÇÖZÜCÜNÜN YAYIMLADIĞI alanlardan.

    ÖH D35 · OH-ON-04 (ÖLÇÜLDÜ 21-22 Eylül 2026). BATES'in nötr basınç
    eğrisi ALTI uç yüzeyden gelir: çözücü ``grain_design.number_of_segments
    = 3`` yayımlar ve Kn 145,6 -> 148,4 eğrisini o altı cepheyle hesaplar.
    İhraç edilen katı ise TEK parça, kesintisiz bir boruydu — ölçüldü
    (``10_once.json`` C bölümü, FreeCAD): ``fuel_grain.step`` 1 katı,
    4 yüzey, x 36,4 -> 396,4 mm kesintisiz, hacim 1.300.902,1 mm³. Yani o
    STEP'ten imal edilen tane, analiz edilen motorun tanesi DEĞİLDİ ve künye
    segment sayısı hakkında hiçbir şey söylemiyordu.

    Döner ``None`` (plan kazanılmadı) ya da sözlük::

        n                 -> segment sayısı (>= 1)
        segment_mm        -> tek segmentin boyu [mm]
        gap_mm            -> segment arası boşluk [mm]
        gap_published     -> boşluk çözücüden mi geldi
        stack_mm          -> yığının kapladığı eksenel boy [mm]
        source            -> künyeye yazılacak kaynak metni

    UYDURMA YOK (Doktrin 1): ``number_of_segments`` ya da
    ``segment_length_mm`` yayımlanmamışsa ``None`` döner ve çağıran TEK
    parça çizip bunu künyede söyler. ``grain_gap_mm`` AYRI bir hükümdür.

    ÖH D37 A1a pdf-grafik-step · DV36-05 — BOŞLUK KÜNYESİ KAYNAĞINDAN.
    Bu docstring eskiden "bugün hiçbir katı çözücü onu yayımlamıyor"
    diyordu; D36 onemli2-kati'den beri YANLIŞTI: katı çözücü
    ``grain_design.grain_gap_mm``'i (koşunun FİİLEN kullandığı boşluk) ve
    kaynağını ``grain_gap_source`` ∈ {``user_input``,
    ``not_supplied_zero``, ``rejected_input``} ile yayımlıyor
    (``solid_rocket_engine.py`` ``grain_gap_source``). ÖLÇÜLDÜ
    (``docs/scofield/raw/OH/A1a/pdf-grafik-step/a1/once.json`` K2): gerçek
    katı örnekte ``grain_gap=0`` girildiğinde çözücü
    ``grain_gap_mm=0.0, grain_gap_source='user_input'`` yayımlıyor, plan
    ise ``_first_positive`` ile 0,0'ı "yayımlanmadı" sayıp künyeye "no
    solver publishes grain_design.grain_gap_mm" yazıyordu — yayımlanmış
    gerçek bir sıfırı yok sayan, üstelik kendi yanıtıyla çelişen bir cümle.

    Kural (``dalga_plani.md`` §0 kural 4 inceltmesi): değer SONLU ve ≥ 0
    okunur; künye ÇÖZÜCÜNÜN ``grain_gap_source``'undan kurulur. Kaynak
    yayımlıysa 0,0 ona göre okunur (``user_input`` 0,0 = kullanıcının
    girdiği gerçek sıfır, bitişik); kaynak YOKSA 0,0 = yayımlanmadı.
    Alan yanıtta hiç yoksa künye ``absent_in_response`` der. Yeni kaynak
    kodu İCAT EDİLMEZ; bilinmeyen bir kod ADIYLA aktarılır.
    """
    from hrma.export.motor_geometry import _first_positive

    for dugum, etiket in ((md, 'motor result'),
                          (md.get('motor_geometry')
                           if isinstance(md.get('motor_geometry'), dict)
                           else {}, 'motor_geometry')):
        gd = dugum.get('grain_design') if isinstance(dugum, dict) else None
        if not isinstance(gd, dict):
            continue
        n_ham = gd.get('number_of_segments')
        seg_mm = _first_positive(gd.get('segment_length_mm'))
        if seg_mm is None:
            continue
        try:
            n = int(round(float(n_ham)))
        except (TypeError, ValueError):
            continue
        if n < 1:
            continue
        gap_yayimlandi, gap, gap_kaynagi, gap_kunyesi = _grain_gap_reading(
            gd, etiket)
        kaynak = (f'{etiket}.grain_design.number_of_segments={n}, '
                  f'segment_length_mm={seg_mm:.4g}') + gap_kunyesi
        return {'n': n, 'segment_mm': float(seg_mm), 'gap_mm': gap,
                'gap_published': gap_yayimlandi,
                'gap_source': gap_kaynagi,
                'stack_mm': n * float(seg_mm) + (n - 1) * gap,
                'source': kaynak}
    return None


def _grain_segment_plan_derived(md, grain_length_mm):
    """Segment boyu YAYIMLANMAMIŞ ama segment SAYISI yayımlanmışsa plan.

    ÖH V3 CAD A1 · H3 (7 Eki CAD kontrolü, ÖLÇÜLDÜ): hibrit çözücü
    ``grain_design.number_of_segments`` (örnekte 3) yayımlıyor ama
    ``segment_length_mm`` yayımlamıyor; ``_grain_segment_plan`` bu yüzden
    planı DÜŞÜRÜYOR, STEP taneyi tek parça çizip künyesine "the analysis does
    not publish grain_design.number_of_segments" yazıyordu — yayımlanan bir
    alan için yanlış bir cümle.

    Kural (yeni sayı İCAT ETMEZ): çözücü tanenin TOPLAM boyunu
    (``grain_length_mm``) ve segment sayısını yayımlıyor; segment boyu
    ``grain_length_mm / number_of_segments``tır (eşit bölme, künyede beyan).
    Boşluk ``_grain_gap_reading`` ile aynı kaynaktan okunur; hibrit çözücü
    boşluk yayımlamaz ve kamarasını L = L_ön + L_tane + L_art diye kurar,
    yani segmentler BİTİŞİKTİR. ``n < 2`` ise plan yoktur (tek parça).
    """
    from hrma.export.motor_geometry import _first_positive

    if grain_length_mm is None or not grain_length_mm > 0:
        return None
    for dugum, etiket in ((md, 'motor result'),
                          (md.get('motor_geometry')
                           if isinstance(md.get('motor_geometry'), dict)
                           else {}, 'motor_geometry')):
        gd = dugum.get('grain_design') if isinstance(dugum, dict) else None
        if not isinstance(gd, dict) or 'number_of_segments' not in gd:
            continue
        if _first_positive(gd.get('segment_length_mm')) is not None:
            continue          # açık plan ``_grain_segment_plan``in işi
        # Sayı merkezden okunur (``input_guard.finite_number``: bool ve
        # sonlu olmayan değer None); tam sayı olmayan sayı plan kurmaz.
        n_f = finite_number(gd.get('number_of_segments'))
        if n_f is None or n_f != int(n_f) or int(n_f) < 2:
            continue
        n = int(n_f)
        gap_yayimlandi, gap, gap_kaynagi, gap_kunyesi = _grain_gap_reading(
            gd, etiket)
        seg_mm = float(grain_length_mm) / n
        kaynak = (f'{etiket}.grain_design.number_of_segments={n} published, '
                  'segment_length_mm NOT published, so each segment is '
                  f'grain_length_mm / number_of_segments = {seg_mm:.4g} mm '
                  '(equal split of the published grain length)'
                  + gap_kunyesi)
        return {'n': n, 'segment_mm': seg_mm, 'gap_mm': gap,
                'gap_published': gap_yayimlandi, 'gap_source': gap_kaynagi,
                'stack_mm': n * seg_mm + (n - 1) * gap,
                'source': kaynak, 'derived': True}
    return None


def grain_stack_plan(md, grain_length_mm):
    """Tane yığını — STEP ve STL'in TEK planı (sayı, segment, boşluk, boy).

    Sıra: açık plan (``_grain_segment_plan``: segment boyu yayımlı) ->
    türetilmiş plan (``_grain_segment_plan_derived``: yalnız sayı yayımlı)
    -> tek parça. Döner sözlük her zaman ``n``, ``segment_mm``, ``gap_mm``,
    ``stack_mm``, ``plan`` (açık/türetilmiş plan ya da None) taşır.
    """
    plan = _grain_segment_plan(md)
    if plan is not None:
        plan = dict(plan, derived=False)
    else:
        plan = _grain_segment_plan_derived(md, grain_length_mm)
    if plan is None:
        L_g = float(grain_length_mm)
        return {'n': 1, 'segment_mm': L_g, 'gap_mm': 0.0, 'stack_mm': L_g,
                'plan': None}
    return {'n': plan['n'], 'segment_mm': plan['segment_mm'],
            'gap_mm': plan['gap_mm'], 'stack_mm': plan['stack_mm'],
            'plan': plan}


#: ÖH D37 A1a · DV36-05 — katı çözücünün ``grain_gap_source`` kodları ve
#: künye cümleleri. Kodlar ÇÖZÜCÜNÜN adlarıdır (``solid_rocket_engine``
#: ``grain_gap_source``); burada yeni kod İCAT EDİLMEZ, yalnız okunur.
GRAIN_GAP_SOURCE_TEXT = {
    'user_input': 'the gap was entered by the user',
    'not_supplied_zero': 'no gap was sent and the solver used a zero gap',
    'rejected_input': ('the submitted gap was rejected (see '
                       'rejected_inputs) and the solver used a zero gap'),
}

#: Alan yanıtta HİÇ yoksa künyenin kullandığı ad (dalga_plani §0 kural 11
#: deseni: tüketici alan yoksa ``absent_in_response`` der).
GRAIN_GAP_ABSENT = 'absent_in_response'


def _grain_gap_reading(gd, etiket):
    """Segment arası boşluğu ve künyesini ÇÖZÜCÜNÜN yayımından okur.

    Döner ``(yayimlandi, gap_mm, kaynak_kodu, kunye_eki)``. ``yayimlandi``
    False ise ``gap_mm`` 0,0'dır ve segmentler bitişik yerleşir; künye
    NEDENİNİ adıyla söyler. Sayı icat edilmez (bkz. ``_grain_segment_plan``).
    """
    from hrma.utils.input_guard import finite_number

    alan = f'{etiket}.grain_design.grain_gap_mm'
    kaynak = gd.get('grain_gap_source')
    kaynak_kodu = (kaynak if isinstance(kaynak, str) and kaynak
                   else GRAIN_GAP_ABSENT)
    if 'grain_gap_mm' not in gd or gd.get('grain_gap_mm') is None:
        return (False, 0.0, kaynak_kodu,
                f'; inter-segment gap NOT modelled: {alan} is '
                f'{GRAIN_GAP_ABSENT} (the result carries no gap value), so '
                'the segments are placed flush and no gap value is invented')
    deger = finite_number(gd.get('grain_gap_mm'))
    if deger is None or deger < 0.0:
        return (False, 0.0, kaynak_kodu,
                f'; inter-segment gap NOT modelled: {alan}='
                f'{gd.get("grain_gap_mm")!r} is not a finite value >= 0, so '
                'the segments are placed flush and no gap value is invented')
    if kaynak_kodu in GRAIN_GAP_SOURCE_TEXT:
        # Kaynak yayımlı: 0,0 dâhil değer ONA göre okunur (kural 4 inceltmesi).
        aciklama = GRAIN_GAP_SOURCE_TEXT[kaynak_kodu]
        if kaynak_kodu != 'user_input' and deger != 0.0:
            # Çözücüde iki alan birlikte kurulur; ayrışmaları bir bozulma
            # işaretidir. Değer, kasa boyu zincirinin kullandığı sayıdır ve
            # aynen kullanılır, ama çelişki SESSİZ geçmez.
            aciklama += (f', yet {deger:.4g} mm is published — the pair is '
                         'inconsistent; the published value is used')
        yerlesim = ('the segments are placed flush' if deger == 0.0
                    else 'the segments are spaced by it')
        return (True, float(deger), kaynak_kodu,
                f', grain_gap_mm={deger:.4g}; inter-segment gap from '
                f'grain_gap_source={kaynak_kodu} ({aciklama}; {yerlesim})')
    # Kaynak YOK ya da tanınmayan bir kod: 0,0 "yayımlanmadı" demektir.
    kod_metni = (f'grain_gap_source is {GRAIN_GAP_ABSENT}'
                 if kaynak_kodu == GRAIN_GAP_ABSENT else
                 f'grain_gap_source={kaynak_kodu!r} is not a code the solid '
                 'solver publishes')
    if deger > 0.0:
        return (True, float(deger), kaynak_kodu,
                f', grain_gap_mm={deger:.4g}; inter-segment gap {kod_metni}')
    return (False, 0.0, kaynak_kodu,
            f'; inter-segment gap NOT modelled: {alan}=0 is published but '
            f'{kod_metni}, and a bare 0.0 is read as not published, so the '
            'segments are placed flush and no gap value is invented')


def grain_axial_layout_mm(motor_data, chamber_length_mm, stack_length_mm):
    """Tane yığınının ön yüzü [mm] — STEP, STL ve DXF'in TEK yerleşim kuralı.

    ÖH V3 CAD A2 · H7. ÖLÇÜLDÜ (7 Eki CAD kontrolü, örnek katı BATES): aynı
    istek için STEP 3 x 120 mm segmenti 2 mm aralıkla, ön yüzü 35,0 mm'de
    çiziyordu; STL ve DXF taneyi TEK parça 360 mm, ön yüzü 36,4 mm'de
    çiziyordu. Üç üretecin üç ayrı kuralı vardı: STEP
    ``min(0,35 x max(4, L - L_yığın), L - L_yığın)``, STL ``0,35 x max(0,004 m,
    L - L_tane)`` (satır içi literaller), DXF yığını görmeyen kopya sabitler.

    Sıra: çözücü konumu yayımlıyorsa (hibrit) ``solver_grain_front_mm``;
    yayımlamıyorsa (katı) STEP'in kuralı — yığın boyuyla, kamaranın sonunu
    aşmayacak biçimde. Döner ``{'front_mm', 'note', 'source'}``;
    ``source`` ∈ {``'solver'``, ``'generator_rule'``}.
    """
    yer = solver_grain_front_mm(motor_data, chamber_length_mm,
                                stack_length_mm)
    if yer is not None:
        return {'front_mm': yer['front_mm'], 'note': yer['note'],
                'source': 'solver'}
    L = float(chamber_length_mm)
    S = float(stack_length_mm)
    zg0 = min(GRAIN_AXIAL_POSITION_FRACTION
              * max(GRAIN_AXIAL_MIN_SLACK_MM, L - S), L - S)
    note = (f'axial position ASSUMED: front face at {zg0:.2f} mm from '
            f'the injector face, generator layout rule '
            f'{GRAIN_AXIAL_POSITION_FRACTION:g} x max('
            f'{GRAIN_AXIAL_MIN_SLACK_MM:g} mm, chamber length - grain stack '
            'length), kept inside the chamber; NO solver publishes the axial '
            'position of the grain')
    return {'front_mm': zg0, 'note': note, 'source': 'generator_rule'}


# ---------------------------------------------------------------------------
# ÖH V3 CAD A2 · H6 — tane ile kamara cidarı arasındaki RADYAL PAY (beyan)
# ---------------------------------------------------------------------------
#: Bir astar/yalıtım İDDİASININ okunduğu yanıt alanları (yalnız okunur; CAD
#: astar ÇİZMEZ). ÖLÇÜLDÜ (7 Eki CAD kontrolü H6, örnek katı): yanıt
#: ``thermal_barrier.liner_thickness = 2,0 mm`` ve ``inert_breakdown.liner_kg
#: = 0,267 kg``'ı kuru kütleye ekliyor; CAD'de tane dış çapı = kasa iç çapı
#: (75,0 = 75,0), astar için yer yok. Boyutlandırmanın düzeltilmesi
#: (yayımlanan sayı değişir) çözücü kulvarının işidir; CAD burada ÖLÇER ve
#: BEYAN EDER.
LINER_THICKNESS_CLAIM_FIELDS = (
    'thermal_analysis.heat_transfer.liner_thickness_mm',
    'heat_transfer_analysis.cooling_analysis.liner_thickness_mm',
    'cad_design.insulation_system.thermal_barrier.liner_thickness',
)
LINER_MASS_CLAIM_FIELD = 'design_summary.masses.inert_breakdown.liner_kg'


def grain_radial_clearance_note(motor_data, bore_radius_mm,
                                grain_outer_radius_mm):
    """Tane dış yüzü ile kamara deliği arasındaki radyal payın künyesi.

    Pay ÇİZİLEN geometriden ölçülür; yanıt bir astar kalınlığı iddia
    ediyorsa iddia ve sığıp sığmadığı yazılır. Hiçbir yalıtım/astar
    katısı çizilmez (uydurma yok).
    """
    md = motor_data if isinstance(motor_data, dict) else {}
    pay = float(bore_radius_mm) - float(grain_outer_radius_mm)
    note = (f'radial clearance between the grain outer surface and the '
            f'chamber bore {pay:.2f} mm (measured on the drawn solids); no '
            'liner, insulation or loading clearance is drawn')
    for alan in LINER_THICKNESS_CLAIM_FIELDS:
        iddia = _strict_number(_nested(md, alan))
        if iddia is None or iddia <= 0.0:
            continue
        kutle = _strict_number(_nested(md, LINER_MASS_CLAIM_FIELD))
        note += (f'; the analysis claims a {iddia:.2f} mm liner ({alan}'
                 + (f', {kutle:.3f} kg counted in the dry mass by '
                    f'{LINER_MASS_CLAIM_FIELD}' if kutle is not None else '')
                 + ') that is NOT drawn and '
                 + ('does NOT fit: it needs {:.2f} mm of radial room, this '
                    'geometry has {:.2f} mm'.format(iddia, pay)
                    if iddia > pay + WALL_MATCH_TOLERANCE_MM else
                    'would fit in the drawn clearance'))
        break
    return note


# ---------------------------------------------------------------------------
# ÖH V3 CAD A2 · H1 — TANE KESİTİ KAPISI (karar §28-21 (c))
# ---------------------------------------------------------------------------
#
# ÖLÇÜLDÜ (7 Eki CAD kontrolü H1): yıldız ve finocyl tane STEP'te ve STL'de
# düz dairesel portlu boru olarak çiziliyordu (hacim BATES ile birebir
# 1 300 902 mm³); itici kütlesi iddiası yıldızda 1,951 kg, CAD'den 2,407 kg
# (+%23,3), finocyl'de +%7,0. Üç üreteç de ``grain_type``'ı hiç okumuyordu ve
# künye yalnız "single piece" diyordu. Karar (c): doğrulanmış gerçek port
# kesiti yoksa dışa aktarım tane tipini ADIYLA söyleyen hatayla reddedilir;
# sessiz BATES borusu kalkar. Gerçek kesitin çizimi ayrı kalemdir.

#: Dışa aktarım üreteçlerinin GERÇEKTEN çizebildiği tane kesiti: TEK,
#: DAİRESEL port (halka silindir). Katı çözücünün ``'bates'`` ve hibrit
#: çözücünün ``'cylindrical_bore'`` tipi tam olarak budur. Liste çözücülerin
#: KENDİ adlarıdır; yeni ad icat edilmez.
CAD_DRAWABLE_GRAIN_TYPES = ('bates', 'cylindrical_bore')
#: Tane tipinin okunduğu alanlar (öncelik sırası).
GRAIN_TYPE_FIELDS = ('grain_design.grain_type',
                     'motor_geometry.grain_design.grain_type', 'grain_type')
#: Port sayısının okunduğu alanlar (hibrit çözücü ``port_count``).
PORT_COUNT_FIELDS = ('port_count', 'grain_design.port_count',
                     'motor_geometry.port_count')
GRAIN_GATE_STATUS = 'grain_section_not_drawable'
GRAIN_GATE_MESSAGE_KEY = 'out.export.grainGate.refused'
GRAIN_GATE_PART = 'fuel_grain'
GRAIN_GATE_PART_KEY = 'out.export.grainGate.part.fuel_grain'
GRAIN_GATE_REASON_KEYS = {
    'grain_type_not_drawable':
        'out.export.grainGate.reason.grain_type_not_drawable',
    'grain_type_conflict': 'out.export.grainGate.reason.grain_type_conflict',
    'port_count_not_one': 'out.export.grainGate.reason.port_count_not_one',
}
_GRAIN_GATE_REASON_TEXT = {
    'grain_type_not_drawable': (
        '{part}: the analysis designs a "{grain_type}" grain '
        '({grain_type_field}); the CAD generators draw only a single '
        'circular port ({drawable_types}), so the real port section is not '
        'drawn and no plain tube is substituted for it'),
    'grain_type_conflict': (
        '{part}: the export body carries conflicting grain types '
        '{grain_type} ({grain_type_field}), so which port section goes to '
        'manufacturing is not established'),
    'port_count_not_one': (
        '{part}: the analysis publishes port_count = {port_count} '
        '({port_count_field}); the CAD generators draw exactly one circular '
        'port, so a multi-port grain is not drawn as a single-port tube'),
}


def _grain_type_key(value):
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return repr(value)[:40]


# ---------------------------------------------------------------------------
# ÖH V3 CAD şart turu Ş2 (13 Eki) — ret gövdesi istek metnini HAM yansıtmaz
# ---------------------------------------------------------------------------
#
# ÖLÇÜLDÜ (12 Eki CAD denetimi, 'uyumsuz' 1): kapı gövdeleri istemcinin
# gönderdiği değeri ham taşıyordu. ``grain_type = '<img src=x
# onerror=alert(1)>'`` ``/api/export-step`` 422 gövdesinin
# ``refusals[0].grain_type`` ve ``message`` alanlarına etiketiyle iniyordu;
# aynı değer SF alanında ``safety_factor_raw``a (``repr``), port sayısında
# ``port_count``a giriyordu. Arayüz bu metni ``reject_body.js`` →
# ``showError`` yoluyla innerHTML'e taşıyordu. Temel ilke (karar §28-33):
# sunucu tarafı indirgeme; DOM kaçışı (SG-2) ek katmandır, yerine geçmez.
# Gövdeye yalnız iki biçim girer:
#   * tane tipi, çözücülerin adlandırma desenine (``^[a-z0-9_]{1,40}$``)
#     uyuyorsa AYNEN (bates, cylindrical_bore, star, finocyl ...);
#   * uymuyorsa ya da sayı olmayan bir SF / port sayısıysa yalnız Python
#     TÜR ADI (+ uzunluk), ör. ``str(len=28)``. Bu bir kod belirtecidir
#     (alan adları gibi); EN ve TR cümlede aynı okunur. Kapının HÜKMÜ
#     değişmez: yalnız gövdeye yazılan iz değişir.

#: Ret gövdesine AYNEN yazılabilen belirtecin karakterleri ve azami boyu
#: (``^[a-z0-9_]{1,40}$``; sondaki satır sonu da kabul edilmez).
REFLECTABLE_TOKEN_CHARS = frozenset('abcdefghijklmnopqrstuvwxyz0123456789_')
REFLECTABLE_TOKEN_MAX_LEN = 40
#: Desene uymayan değerin yer tutucusu (uzunluğu olan türler için).
UNREFLECTED_VALUE_FORMAT = '{kind}(len={length})'
#: Tür adı belirteç değilse (kod içi çağrıda olağan dışı bir tür) basılan ad.
UNREFLECTED_KIND_FALLBACK = 'object'


def _reflectable_token(text):
    """``text`` ret gövdesine aynen yazılabilir mi (``^[a-z0-9_]{1,40}$``)."""
    return (isinstance(text, str)
            and 1 <= len(text) <= REFLECTABLE_TOKEN_MAX_LEN
            and all(c in REFLECTABLE_TOKEN_CHARS for c in text))


def _unreflected_value(value):
    """İstek değerinin ret gövdesine giden TEK izi: tür adı (+ uzunluk)."""
    kind = type(value).__name__
    if not (kind.isascii() and kind.isidentifier()):
        kind = UNREFLECTED_KIND_FALLBACK
    try:
        length = len(value)
    except TypeError:
        return kind
    return UNREFLECTED_VALUE_FORMAT.format(kind=kind, length=length)


def _reflected_grain_type(key, value):
    """Tane tipinin ret kaydındaki yazımı: belirteçse aynen, değilse iz."""
    return key if _reflectable_token(key) else _unreflected_value(value)


def grain_section_refusals(motor_data):
    """Tane kesiti kapısının hükmü — ret kayıtları listesi (boş = çizilir).

    Kapı yalnız bir tane GERÇEKTEN çizilecekse konuşur
    (``motor_geometry.resolve_grain_m`` taneyi çözüyorsa). Tip
    yayımlanmamışsa kapı reddetmez; üreteç dairesel portu çizer ve bunu
    künyesinde söyler (``grain_section_note``).
    """
    from hrma.export.motor_geometry import resolve_grain_m
    md = motor_data if isinstance(motor_data, dict) else {}
    grain, _neden = resolve_grain_m(md)
    if grain is None:
        return []
    base = {'part': GRAIN_GATE_PART, 'part_key': GRAIN_GATE_PART_KEY,
            'drawable_types': ', '.join(CAD_DRAWABLE_GRAIN_TYPES)}

    def kayit(reason, **ek):
        r = dict(base, reason=reason,
                 reason_key=GRAIN_GATE_REASON_KEYS[reason])
        r.update(ek)
        return r

    out = []
    bulunan = [(alan, _nested(md, alan)) for alan in GRAIN_TYPE_FIELDS]
    bulunan = [(alan, v) for alan, v in bulunan if v is not None]
    tipler = []
    # Ş2: kayda giden yazım (hüküm ``tipler`` üstünden verilir, değişmedi).
    yazim = {}
    for _alan, v in bulunan:
        k = _grain_type_key(v)
        if k not in tipler:
            tipler.append(k)
            yazim[k] = _reflected_grain_type(k, v)
    if len(tipler) > 1:
        out.append(kayit('grain_type_conflict',
                         grain_type=' / '.join(yazim[t] for t in tipler),
                         grain_type_field=', '.join(a for a, _ in bulunan)))
    elif tipler and tipler[0] not in CAD_DRAWABLE_GRAIN_TYPES:
        out.append(kayit('grain_type_not_drawable',
                         grain_type=yazim[tipler[0]],
                         grain_type_field=bulunan[0][0]))
    for alan in PORT_COUNT_FIELDS:
        ham = _nested(md, alan)
        if ham is None:
            continue
        n = _strict_number(ham)
        if n is None or n != 1:
            out.append(kayit('port_count_not_one',
                             port_count=(n if n is not None
                                         else _unreflected_value(ham)),
                             port_count_field=alan))
        break
    return out


def grain_section_note(motor_data):
    """Çizilen port kesitinin künyesi (kapıdan geçen tane için)."""
    md = motor_data if isinstance(motor_data, dict) else {}
    for alan in GRAIN_TYPE_FIELDS:
        v = _nested(md, alan)
        if v is not None:
            return (f'port section: single circular port, grain_type = '
                    f'{_grain_type_key(v)} from {alan}')
    return ('port section: single circular port; this export body publishes '
            'no grain_type (' + ' / '.join(GRAIN_TYPE_FIELDS) + '), so the '
            'circular port of the published port diameter is drawn')


def grain_gate_message(refusals, artefact):
    """Kapının EN cümlesi (HTTP ``message`` ve üretici istisnası için)."""
    satirlar = []
    for r in refusals:
        params = {k: ('-' if v is None else v) for k, v in r.items()}
        satirlar.append(_GRAIN_GATE_REASON_TEXT[r['reason']].format(**params))
    return (f'{artefact} refused: the fuel grain section of this design '
            'cannot be drawn, so no file with an approximated grain is '
            'written (' + '; '.join(satirlar) + ').')


def grain_gate_body(refusals, artefact):
    """Tane kesiti kapısının HTTP 422 gövdesi (``sf_gate_body`` biçiminde)."""
    message = grain_gate_message(refusals, artefact)
    return {
        'status': GRAIN_GATE_STATUS,
        'error': message,
        'message': message,
        'message_key': GRAIN_GATE_MESSAGE_KEY,
        'message_params': {'count': len(refusals), 'artefact': artefact},
        'refusals': list(refusals),
        'invalid_fields': [
            {'field': (r.get('grain_type_field')
                       or r.get('port_count_field')),
             'reason': r['reason'], 'part': r['part']} for r in refusals],
    }


# ---------------------------------------------------------------------------
# ÖH V3 CAD A2 · H4 / H9 — TANK KABUĞU (karar §28-21 (b), tek kaynak)
# ---------------------------------------------------------------------------
#
# ÖLÇÜLDÜ (7 Eki CAD kontrolü H4, sıvı + ``max_burn_duration = 30``): tank
# boyutlandırması (``liquid_rocket_engine._design_propellant_tanks``) tankı
# DÜZ UÇLU SİLİNDİR sayar — ``dimensions.volume = π·D²·L/4``, çember
# gerilmesi P·(D/2)/σ, basınçlı kap analizi ``inner_diameter_mm = D``. STEP
# ise silindire iki TAM küre ekliyordu: CAD iç hacmi iddianın 1,225x (yakıt)
# / 1,231x (LOX) idi. Tank STL'si (H9) içi DOLU bir zarftı (156,6 L ⟷ STEP
# kabuğu 5,20 L) ve ekseni Z'ydi (STEP X). Karar (b): CAD boyutlandırmanın
# modelini çizer. D ve L tankın İÇ (itici) boşluğudur; cidar t DIŞARI
# eklenir — gövdede ve iki düz kapakta. STEP ve STL aynı meridyen
# profilinden (``tank_shell_geometry_mm``) üretilir; ikisinin ekseni +X,
# boşluk x = 0 ile x = L arasıdır.

#: Çizilen boşluk hacminin yayımlanan tank hacmiyle uyuşma toleransı
#: (bağıl). İki sayı da aynı D ve L'den gelir (π·D²·L/4); fark yalnız kayan
#: nokta yuvarlamasıdır. Daha büyük bir fark yanıtta İKİ ayrı tank demektir.
TANK_VOLUME_MATCH_REL_TOL = 1e-6
#: Düz kapak beyanı (etiket ve paket metinleri bu cümleyi okur).
#: ÖH V31 CV-0 (B1 §4.3 (c)): eski cümle "the structural adequacy of the
#: drawn flat heads was NOT computed" diyordu ve imalat dosyası yine de
#: iniyordu. ÖLÇÜLDÜ (19 Eki, ``docs/scofield/raw/OH/V31/cv0/once.json``):
#: örnek sıvı tanklarında çizilen 3 mm düz kapağın akma tabanlı SF'si
#: 0,12-0,47. Kapak artık imalat kapısında hesaplanır
#: (``tank_head_assessment``); sayı ve hüküm ``tank_head_declaration``
#: cümlesiyle bu beyanın yanına yazılır.
TANK_FLAT_HEAD_DECLARATION = (
    'flat heads idealized as the flat-ended cylinder of the sizing model; '
    'each drawn flat head is checked by the manufacturing safety gate as a '
    'simply supported flat circular plate under uniform pressure (Roark '
    'Table 11.2 case 10a) at the qualification pressure, against the '
    'material yield strength')


def tank_shell_geometry_mm(key, diameter_mm, length_mm, wall_mm,
                           volume_l=None, analysed_head_type=None):
    """Tank kabuğunun TEK geometrisi (mm) — STEP ve STL bunu okur.

    Döner sözlük: ``inner_diameter_mm``, ``inner_length_mm``, ``wall_mm``,
    ``outer_diameter_mm``, ``outer_length_mm``, ``x_min_mm``, ``x_max_mm``,
    ``inner_volume_mm3``, ``profile_xr`` (meridyen profili, (x, r) mm,
    kapalı değil), ``label``. Ölçüler girdi sırası için doğrulanmış kabul
    edilir (çağıran zarf ve cidar kapılarını uygular). ``volume_l``
    verilirse çizilen boşluk onunla sınanır; uyuşmazsa ``ValueError``
    (fail-closed: hangi tankın imal edileceği kazanılmamıştır).
    ``analysed_head_type`` (tankın basınçlı kap analizinin değerlendirdiği
    başlık tipi, ``pressure_vessel.head_type``) verilirse künye çizilen düz
    kapağın o başlık olmadığını söyler.
    """
    D, L, t = float(diameter_mm), float(length_mm), float(wall_mm)
    r, R = D / 2.0, D / 2.0 + t
    v_ic = math.pi * r * r * L
    hacim_notu = (f'cavity volume {v_ic / 1e6:.4f} L = pi D^2 L / 4 '
                  '(the tank volume of the sizing model)')
    if volume_l is not None:
        v_iddia = finite_number(volume_l)
        if v_iddia is None or v_iddia <= 0.0:
            raise ValueError(
                f'{key}.volume = {volume_l!r} is not a finite positive '
                'volume; the drawn cavity cannot be checked against it')
        sapma = abs(v_ic / 1e6 - v_iddia) / v_iddia
        if sapma > TANK_VOLUME_MATCH_REL_TOL:
            raise ValueError(
                f'{key}: the cavity diameter {D:.4f} x length {L:.4f} mm holds '
                f'{v_ic / 1e6:.6f} L but the sizing publishes '
                f'dimensions.volume = {v_iddia:.6f} L (relative difference '
                f'{sapma:.3e} > {TANK_VOLUME_MATCH_REL_TOL:g}); the response '
                'describes two different tanks, so no manufacturing file is '
                'written')
        hacim_notu += f' = {key}.dimensions.volume {v_iddia:.4f} L'
    profil = [(-t, 0.0), (-t, R), (L + t, R), (L + t, 0.0), (L, 0.0),
              (L, r), (0.0, r), (0.0, 0.0)]
    # v3.0.1: ``analysed_head_type`` istemci gövdesinden gelir
    # (``POST /export_tank_cad`` -> ``pressure_vessel.head_type``). Etikete
    # YALNIZ analizin tanıdığı başlık tipi (``pressure_vessel.HEAD_TYPES``)
    # yazılır; başka bir değer ham YANSITILMAZ (STEP metnine giren istemci
    # metni dosyayı bozabilir ya da içerik enjekte edebilir — §28-33).
    from hrma.analysis.pressure_vessel import HEAD_TYPES
    if not analysed_head_type:
        baslik_notu = ''
    elif isinstance(analysed_head_type, str) and analysed_head_type in HEAD_TYPES:
        baslik_notu = (' - the pressure-vessel analysis of this tank '
                       f'evaluates {analysed_head_type} heads '
                       '(pressure_vessel.head_type), not the drawn flat heads')
    else:
        baslik_notu = (' - pressure_vessel.head_type in the request is not a '
                       'recognised head type and is not echoed')
    label = (f'{key} (hollow shell, flat-ended cylinder = the tank sizing '
             f'model; cavity diameter {D:.2f} x length {L:.2f} mm from '
             f'{key}.diameter / '
             f'{key}.length, {hacim_notu}; wall {t:.2f} mm from '
             f'{key}.wall_thickness added OUTSIDE on the barrel and on both '
             f'heads -> overall diameter {D + 2 * t:.2f} x length '
             f'{L + 2 * t:.2f} mm, '
             f'x = {-t:.2f} to {L + t:.2f} mm; {TANK_FLAT_HEAD_DECLARATION}'
             + baslik_notu + ')')
    return {'inner_diameter_mm': D, 'inner_length_mm': L, 'wall_mm': t,
            'outer_diameter_mm': D + 2 * t, 'outer_length_mm': L + 2 * t,
            'x_min_mm': -t, 'x_max_mm': L + t, 'inner_volume_mm3': v_ic,
            'profile_xr': profil, 'label': label}


def export_axis_rotation():
    """Bellek içi +Z mesh'ini paketin +X sözleşmesine çeviren 4x4 dönme.

    ``motor_geometry.MESH_TO_EXPORT_ROTATION_DEG`` (+Y etrafında):
    (x, y, z) -> (z, y, -x). Motor STL'leri ve tank STL'si aynı matrisi
    okur (tek kaynak).
    """
    from hrma.export.motor_geometry import MESH_TO_EXPORT_ROTATION_DEG
    ac = np.deg2rad(MESH_TO_EXPORT_ROTATION_DEG)
    return np.array([[np.cos(ac), 0.0, np.sin(ac), 0.0],
                     [0.0, 1.0, 0.0, 0.0],
                     [-np.sin(ac), 0.0, np.cos(ac), 0.0],
                     [0.0, 0.0, 0.0, 1.0]], dtype=float)


def tank_shell_mesh_mm(geometry, sections):
    """``tank_shell_geometry_mm`` profilinden kapalı kabuk mesh'i (mm, +X).

    Profil STEP'in döndürdüğü meridyenin AYNISIDIR; mesh +Z'de döndürülüp
    pakete (+X) çevrilir. Kesit sayısı (``sections``) çokgen açığını belirler:
    iç hacim π·r²·L'nin (sections/2π)·sin(2π/sections) katıdır.
    """
    profil = np.array([(r, x) for x, r in geometry['profile_xr']]
                      + [(geometry['profile_xr'][0][1],
                          geometry['profile_xr'][0][0])], dtype=float)
    mesh = MotorCADDesigner._fix_solid(
        trimesh.creation.revolve(profil, sections=int(sections)))
    mesh.apply_transform(export_axis_rotation())
    return mesh


#: ÖH V3 CAD A1 · H8 — enjektör plakasının EKSENEL YERİ, iki üretecin TEK
#: kuralı. ÖLÇÜLDÜ (7 Eki CAD kontrolü, hibrit örnek): STEP plakayı
#: x = 4,0-7,0 mm'ye (``step_export.INJECTOR_PLATE_AXIAL_OFFSET_MM = 4,0``
#: "montaj boşluğu"), STL x = 0,0-3,0 mm'ye koyuyordu; paket README'si
#: "her dosya aynı eksende, döndürmeden birlikte açılır" diyordu. Hiçbir
#: çözücü plakanın eksenel yerini ya da kapakla arasında bir boşluk
#: yayımlamaz; 4 mm'lik boşluk bir üreteç sabitiydi. Plaka ön kapağın iç
#: yüzüne (x = 0, eksen sözleşmesinin "enjektör yüzü") OTURUR ve [0, t]
#: aralığını kaplar — boşluk icat edilmez. Bu konumun bedeli açıkça
#: söylenir (künye): çözücünün kamara hacmi tüm deliği ([0, L]) sayar,
#: plakayı düşmez.
INJECTOR_PLATE_SEAT_X_MM = 0.0


def injector_plate_axial_span_mm(thickness_mm):
    """Plakanın eksenel aralığı ``(x0, x1)`` [mm] ve künye cümlesi."""
    x0 = INJECTOR_PLATE_SEAT_X_MM
    x1 = x0 + float(thickness_mm)
    note = (f'plate seated on the closure-head inner face, x = {x0:.2f} to '
            f'{x1:.2f} mm (the axis convention\'s injector face is x = 0); '
            'no solver places the injector plate axially or publishes a '
            'clearance, so none is invented, and the analysis chamber '
            'volume spans the whole bore without subtracting the plate')
    return x0, x1, note


# ---------------------------------------------------------------------------
# V301 bilinen C2 — PINTLE ENJEKTÖRÜN CAD GEOMETRİSİ (STEP + STL TEK KAYNAK)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (22 Eki, ``docs/scofield/raw/OH/V301/bilinen/cad``): pintle seçilen
# koşuda STEP ve STL enjektörü "düz plaka + devrenin EŞDEĞER orifis planı"
# (hibrit 3 kN'de 3 delik) olarak çiziyordu; kanonik pintle (direk, anülüs,
# uç delik sırası) hiçbir CAD dosyasında yoktu. Çözücünün kendi beyanı
# (``injector_design.PINTLE_EQUIVALENT_ORIFICE_PLAN_BASIS``): "The pintle is
# NOT drilled this way". Artık iki üretici de aşağıdaki TEK çözümleyiciden
# okur; kanonik geometri yoksa ya da çizilemiyorsa ADLI ret (düz plakaya
# sessiz dönüş YOK).

#: Kanonik pintle geometrisinin arandığı bloklar (sıra = öncelik). Hibrit
#: çözücü özet bloğa yazar (V301/E1, ``motor.injector_design.pintle_
#: geometry``); sıvı çözücü devre ayrıntısına (``injector_design_detail``),
#: sıvı dışa aktarım gövdesi (``motor_geometry``) onu ``injector_design``
#: altına taşır (``motor_geometry.liquid_results_to_motor_geometry``).
PINTLE_GEOMETRY_BLOCKS = ('injector_design', 'injector_design_detail')
#: Enjektör tipinin okunduğu bloklar. Tip yalnız ``'pintle'`` değeriyle
#: tanınır; bloklar çelişirse (biri pintle, öteki başka tip) çizim REDDEDİLİR.
PINTLE_TYPE_BLOCKS = ('injector_design', 'injector_design_detail',
                      'injector_results')
PINTLE_TYPE_NAME = 'pintle'
#: Uç delik kipleri: radyal delikler çizilir; 'none' deliksiz direk;
#: teğetsel delikler çizilmez (aşağıdaki ret gerekçesi).
PINTLE_DRAWABLE_MODES = ('radial', 'none')
#: HRMA ÇİZİM SEÇİMİ — LİTERATÜR DEĞERİ YOK. Direğin ucu, uç delik
#: sırasının akış yönündeki kenarından bu kadar DELİK ÇAPI ötede kapanır
#: (direk ucu x = yüz + L_s + d/2 + k·d). Çözücü direğin delik sırasından
#: sonraki boyunu yayımlamaz (Dressler & Bauer AIAA 2000-3871 de sayı
#: vermez); delik kenarı ile uç arasında malzeme olsun diye seçildi.
PINTLE_CAD_TIP_BEYOND_HOLE_EDGE_PER_D = 0.5
#: HRMA KORUMASI — LİTERATÜR DEĞERİ YOK: uç delik sırası en çok bu kadar
#: delikle çizilir; üstü ADLI ret (sıra KIRPILMAZ). İstemci gövdesinden gelen
#: sınırsız bir sayı STEP/STL booleanını sınırsız işe sokmasın diye konuldu
#: (güvenlik + kararlılık ilkesi); ölçülen çizim süresi RAPOR.md'de.
PINTLE_CAD_MAX_TIP_HOLES = 512
PINTLE_CAD_MAX_TIP_HOLES_BASIS = (
    'HRMA guard, no literature value: bounds the boolean work of one '
    'drawing')
#: HRMA ÇİZİM SEÇİMİ — LİTERATÜR DEĞERİ YOK. Uç delikleri direk
#: yüzeyinden radyal olarak, komşu deliklerin birbirine değeceği yarıçapa
#: (r_c = d / (2*sin(pi/n)); tek delikte eksen) kadar olan yolun bu
#: KESRİ derinliğe delinir. Çözücü ne direğin iç besleme kanalını ne de
#: delik boyunu yayımlar. Delikleri eksene kadar indirmek ÖLÇÜLDÜ ve
#: bırakıldı (22 Eki): eşit çaplı radyal delikler eksende tek noktada teğet
#: buluşur, STL booleanı orada katı olmayan ağ veriyordu (156 vakanın 64'ü);
#: sabit L/D = 1 derinliği ise geçerli planların bir kısmında (ör. n = 4,
#: BF 0,58) delikleri direğin içinde birleştirip çizimi reddettiriyordu.
#: Yarı yol, delikleri birbirinden ve eksenden uzak tutar; çizim yalnız
#: delikler direk YÜZEYİNDE çakışırsa (geometrik olarak imkânsız plan)
#: reddedilir.
PINTLE_CAD_TIP_HOLE_DEPTH_FRACTION = 0.5
#: STL TESSELASYON SEÇİMİ (geometri DEĞİL): direk 32 kesitli çokgendir
#: (trimesh ``cylinder`` varsayılanı, STL'in öteki dönel katılarıyla aynı)
#: ve çokgen köşeleri, kesit açısının altın oran kesri kadar döndürülür.
#: ÖLÇÜLDÜ (22 Eki, 88 geçerli delik planı): köşe fazı 0'da delik eksenleri
#: çokgen köşelerinden geçiyor ve boolean sonucu 51 vakada katı olmayan ağ
#: veriyordu, yarım kesitte 46, 0,382'de 0. Delik açıları STEP ile aynıdır
#: (2*pi*i/n); dönen yalnız çokgenin köşeleridir, hacmi değişmez.
PINTLE_STL_POST_SECTIONS = 32
PINTLE_STL_POST_PHASE_FRACTION = (3.0 - math.sqrt(5.0)) / 2.0
#: Çizim kurallarının künyesi (STEP parça adına aynen basılır).
PINTLE_CAD_DRAWING_BASIS = (
    'HRMA drawing choices, no literature value: (1) the post root sits on '
    'the closure-head inner face (x = 0, the plate seat); (2) the post tip '
    f'ends {PINTLE_CAD_TIP_BEYOND_HOLE_EDGE_PER_D:g} x hole diameter beyond '
    'the downstream edge of the tip-hole row; (3) tip holes are drilled '
    'radially from the post surface '
    f'{PINTLE_CAD_TIP_HOLE_DEPTH_FRACTION:g} of the way down to the radius '
    'where neighbouring holes would meet (the axis for a single hole) - '
    'the internal feed passage of the post and the manifold behind the '
    'face are NOT published and NOT modelled')
#: Kanonik geometrinin YAYIMLADIĞI ama çizilmeyen eşdeğer orifis planı.
PINTLE_EQUIVALENT_PLAN_NOT_DRILLED = (
    'the equivalent straight-orifice plan of the injector circuit '
    '(number_of_orifices / orifice_diameter_mm) is a flow-area equivalent '
    'and is NOT drilled')


class PintleCADError(ValueError):
    """Pintle seçili ama CAD geometrisi kurulamıyor (adlı ret).

    ``invalid_fields`` ihracat ailesinin sözleşmesidir (``field`` +
    ``reason``); STEP bunu ``StepExportDataError``a taşır."""

    def __init__(self, message, invalid_fields=()):
        super().__init__(message)
        self.invalid_fields = [dict(k) for k in (invalid_fields or ())]


def _pintle_red(field, reason, message, **ek):
    kayit = {'field': field, 'reason': reason}
    kayit.update(ek)
    return PintleCADError(
        f'pintle injector not drawable ({reason}): {message}; the injector '
        'is not exported as a flat plate with equivalent holes instead',
        invalid_fields=[kayit])


def _pintle_type_claims(md):
    """``{blok: tip}`` — tipi yayımlayan her blok (küçük harf)."""
    out = {}
    for blok in PINTLE_TYPE_BLOCKS:
        b = md.get(blok)
        if isinstance(b, dict):
            tip = b.get('injector_type') or b.get('type')
            if isinstance(tip, str) and tip.strip():
                out[blok] = tip.strip().lower()
    return out


def pintle_type_claimed(motor_data):
    """Koşu enjektörü pintle olarak yayımlıyor mu (herhangi bir blokta)?

    Yalnız tip iddiasına bakar; geometri ve çelişki hükmü
    :func:`pintle_cad_geometry`dedir. Düz plaka üreticileri bunu okuyup
    pintle'da kendilerini KAPATIR (eşdeğer orifis planı delinmez)."""
    md = motor_data if isinstance(motor_data, dict) else {}
    return PINTLE_TYPE_NAME in _pintle_type_claims(md).values()


def pintle_cad_geometry(motor_data, chamber_diameter_m=None):
    """Pintle enjektörün çizim geometrisi [mm] — STEP ve STL TEK kaynak.

    Döner: koşu pintle değilse ``None``; pintle ise sözlük:
        d_post, gap, bore, mode, n_holes, d_hole, skip, plate_t, plate_r,
        x0, x_face, x_holes, x_tip, source_path, notes (künye cümleleri).
    Pintle ama kanonik geometri yok / okunamıyor / çizilemiyorsa
    ``PintleCADError`` (adlı ret). Konum sözleşmesi: x = 0 kapak iç yüzü,
    plaka [x0, x0 + t] (``injector_plate_axial_span_mm``); yüz = x_face.
    """
    md = motor_data if isinstance(motor_data, dict) else {}
    tipler = _pintle_type_claims(md)
    if PINTLE_TYPE_NAME not in tipler.values():
        return None
    diger = {b: t for b, t in tipler.items() if t != PINTLE_TYPE_NAME}
    if diger:
        raise _pintle_red(
            next(iter(diger)) + '.injector_type', 'injector_type_conflict',
            'the result names a pintle injector in '
            + ', '.join(b for b, t in tipler.items()
                        if t == PINTLE_TYPE_NAME)
            + ' but another injector type in '
            + ', '.join(f'{b} ({t})' for b, t in diger.items()),
            claims=tipler)
    pg, yol = None, None
    for blok in PINTLE_GEOMETRY_BLOCKS:
        b = md.get(blok)
        if isinstance(b, dict) and b.get('pintle_geometry') is not None:
            pg, yol = b.get('pintle_geometry'), f'{blok}.pintle_geometry'
            break
    if not isinstance(pg, dict):
        raise _pintle_red(
            yol or 'injector_design.pintle_geometry',
            'pintle_geometry_not_published' if pg is None
            else 'pintle_geometry_not_an_object',
            'the canonical pintle geometry (post diameter, annular gap, '
            'tip holes, skip distance) is not in this result (looked at: '
            + ', '.join(f'{b}.pintle_geometry'
                        for b in PINTLE_GEOMETRY_BLOCKS) + ')',
            accepted_paths=[f'{b}.pintle_geometry'
                            for b in PINTLE_GEOMETRY_BLOCKS])

    def _uzunluk(anahtar):
        v = finite_positive(pg.get(anahtar))
        if v is None:
            raise _pintle_red(
                f'{yol}.{anahtar}', 'not_a_finite_positive_length',
                f'{anahtar} = {_unreflected_value(pg.get(anahtar))} is not '
                'a finite positive length')
        return float(v)

    d_post = _uzunluk('d_pintle_mm')
    gap = _uzunluk('annulus_gap_mm')
    notes = [f'canonical geometry {yol}']
    bore_hesap = d_post + 2.0 * gap
    bore_yay = pg.get('annulus_bore_diameter_mm')
    if bore_yay is not None:
        bore = _uzunluk('annulus_bore_diameter_mm')
        if abs(bore - bore_hesap) > 1e-9 * max(1.0, bore):
            raise _pintle_red(
                f'{yol}.annulus_bore_diameter_mm', 'inconsistent_with_post',
                f'the published annulus bore {bore:.6g} mm is not '
                f'D_p + 2t = {bore_hesap:.6g} mm')
        notes.append(f'annulus bore {bore:.3f} mm = D_p + 2t ({yol}'
                     '.annulus_bore_diameter_mm)')
    else:
        bore = bore_hesap
        notes.append(f'annulus bore {bore:.3f} mm = D_p + 2t (the annulus '
                     'definition A = pi*(D_p + t)*t; the block publishes no '
                     'annulus_bore_diameter_mm)')

    mode_ham = pg.get('secondary_holes')
    n_ham = pg.get('n_radial_holes')
    if mode_ham is None:
        # Sıvı çözücünün modeli (``pintle_tip_geometry``) TANIMI gereği
        # radyal delik sırasıdır; kip alanı yayımlanmaz.
        mode = 'radial' if n_ham else 'none'
        notes.append(f'tip-hole mode {mode}: {yol} publishes no '
                     'secondary_holes; its model (pintle_tip_geometry) is a '
                     'radial hole row')
    elif isinstance(mode_ham, str):
        mode = mode_ham.strip().lower()
    else:
        mode = None
    if mode not in PINTLE_DRAWABLE_MODES:
        if mode == 'tangential':
            raise _pintle_red(
                f'{yol}.secondary_holes', 'tangential_holes_not_drawable',
                'tangential tip holes need the hole-axis offset and drilling '
                'depth, which are not published (the solver sizes them as '
                'radial holes and does not model the tangential momentum)')
        raise _pintle_red(
            f'{yol}.secondary_holes', 'unknown_tip_hole_mode',
            'tip-hole mode '
            + (mode_ham if _reflectable_token(mode_ham)
               else _unreflected_value(mode_ham))
            + ' is not '
            'one of ' + ', '.join(PINTLE_DRAWABLE_MODES))

    bore_m = _real_scalar(chamber_diameter_m)
    if bore_m is None:
        bore_m = _real_scalar(md.get('chamber_diameter'))
    if bore_m is None or not bore_m > 0.0:
        raise _pintle_red(
            'chamber_diameter', 'chamber_diameter_not_published',
            'the chamber bore that must contain the pintle is not published')
    if not bore / 2.0 < bore_m * 500.0:
        raise _pintle_red(
            f'{yol}.d_pintle_mm', 'annulus_bore_not_inside_chamber',
            f'the annulus bore {bore:.4g} mm does not fit inside the '
            f'{bore_m * 1000.0:.4g} mm chamber')
    plate = _injector_plate_design(md, chamber_diameter_m)
    if plate['thickness_m'] is None:
        # Pintle çözümleri plaka/gövde kalınlığı YAYIMLAMAZ (app.py
        # ``_plaka_kalinligi_kazanildi``). Kalınlık uydurulmaz (ÖH D15 /
        # P9B1-13): yüz plakası ve onun içindeki anülüs deliği çizilmez;
        # direk ve uç delikleri, eksen sözleşmesinin enjektör yüzünden
        # (x = 0) ölçülerek çizilir.
        plate_t = plate_r = None
        x0 = x_face = INJECTOR_PLATE_SEAT_X_MM
        plate_note = (
            'injector faceplate / body NOT modelled: ' + plate['source']
            + f'; the annulus bore d{bore:.3f} mm through it is therefore '
            'NOT drawn, and the post and its tip holes are placed from the '
            f'injector face x = {x_face:.2f} mm of the axis convention')
    else:
        if plate['radius_m'] is None:
            raise _pintle_red(
                'injector_results.plate_structural.plate_diameter_mm',
                'plate_diameter_not_published',
                'neither the plate analysis nor the chamber publishes the '
                'plate diameter')
        plate_t = plate['thickness_m'] * 1000.0
        plate_r = plate['radius_m'] * 1000.0
        if not bore / 2.0 < plate_r:
            raise _pintle_red(
                f'{yol}.d_pintle_mm', 'annulus_bore_not_inside_plate',
                f'the annulus bore {bore:.4g} mm does not fit inside the '
                f'{2.0 * plate_r:.4g} mm plate')
        if plate_r > bore_m * 500.0 + _MONTAJ_GIRISIM_TOLERANS_MM:
            raise _pintle_red(
                'injector_results.plate_structural.plate_diameter_mm',
                'plate_wider_than_chamber_bore',
                f'the {2.0 * plate_r:.4g} mm injector plate does not fit in '
                f'the {bore_m * 1000.0:.4g} mm chamber bore')
        x0, x_face, plate_note = injector_plate_axial_span_mm(plate_t)

    if mode == 'radial':
        if isinstance(n_ham, bool) or not isinstance(n_ham, (int, float)) \
                or not float(n_ham).is_integer() or int(n_ham) < 1:
            raise _pintle_red(
                f'{yol}.n_radial_holes', 'not_a_positive_integer',
                f'n_radial_holes = {_unreflected_value(n_ham)} is not a '
                'positive whole number')
        n_holes = int(n_ham)
        if n_holes > PINTLE_CAD_MAX_TIP_HOLES:
            raise _pintle_red(
                f'{yol}.n_radial_holes', 'too_many_tip_holes_to_draw',
                f'{n_holes} tip holes exceed the drawing bound of '
                f'{PINTLE_CAD_MAX_TIP_HOLES} ({PINTLE_CAD_MAX_TIP_HOLES_BASIS})'
                '; the hole row is not truncated')
        d_hole = _uzunluk('radial_hole_d_mm')
        skip = _uzunluk('skip_distance_mm')
        r_post = d_post / 2.0
        # Komşu iki deliğin birbirine değdiği yarıçap: eksen aralığı (kiriş
        # 2*r*sin(pi/n)) delik çapına eşit olduğu yer. Yüzeyde bile
        # değiyorlarsa (r_c >= r) ayrı delikli bir sıra imkânsızdır — yay
        # uzunluğuna dayalı BF < 1 bundan zayıf bir koşuldur.
        r_c = (d_hole / (2.0 * np.sin(np.pi / n_holes)) if n_holes > 1
               else 0.0)
        if not (d_hole < d_post and r_post - r_c
                > _MONTAJ_GIRISIM_TOLERANS_MM):
            raise _pintle_red(
                f'{yol}.n_radial_holes', 'tip_holes_overlap_on_post_surface',
                f'{n_holes} holes of {d_hole:.4g} mm do not fit side by side '
                f'on the {d_post:.4g} mm post (neighbouring holes would '
                'overlap on its surface)')
        hole_depth = PINTLE_CAD_TIP_HOLE_DEPTH_FRACTION * (r_post - r_c)
        if not skip > d_hole / 2.0:
            raise _pintle_red(
                f'{yol}.skip_distance_mm', 'hole_row_inside_injector_face',
                f'the tip-hole row at L_s = {skip:.4g} mm from the face would '
                f'cut into the face (hole radius {d_hole / 2.0:.4g} mm)')
        x_holes = x_face + skip
        x_tip = (x_holes + d_hole / 2.0
                 + PINTLE_CAD_TIP_BEYOND_HOLE_EDGE_PER_D * d_hole)
        notes.append(f'{n_holes} x d{d_hole:.3f} mm tip holes ({yol}'
                     f'.n_radial_holes, .radial_hole_d_mm) on a row at '
                     f'L_s = {skip:.3f} mm from the face ({yol}'
                     '.skip_distance_mm)')
    else:
        n_holes, d_hole, skip, hole_depth = 0, None, None, None
        x_holes = None
        x_tip = x_face
        notes.append('no tip holes (secondary_holes = none) and no skip '
                     'distance: the post is drawn up to the injector face')
    not_drawn = None
    if not x_tip - x0 > _MONTAJ_GIRISIM_TOLERANS_MM:
        # Deliksiz pintle + yayımlanmamış yüz plakası: direk yüze kadar
        # çizilir ama yüz x = 0'dadır; çizilecek hiçbir hacim kalmaz.
        # Parça uydurulmaz; "çizilmedi" gerekçesi adıyla taşınır (yüz
        # plakası yayımlanmamış enjektörün mevcut kanalı).
        not_drawn = (
            'pintle_not_drawable_without_faceplate: secondary_holes = none '
            'leaves no post beyond the injector face and ' + plate_note)
    notes.append(f'post d{d_post:.3f} mm ({yol}.d_pintle_mm), annular gap '
                 f'{gap:.3f} mm ({yol}.annulus_gap_mm)')
    od = finite_positive(pg.get('housing_outer_diameter_mm'))
    notes.append(
        f'injector body OD {od:.3f} mm published - represented by the '
        'faceplate, not drawn as a separate part' if od is not None
        else 'injector body OD not sized by the solver - the faceplate '
             'carries the annulus bore')
    notes.append(PINTLE_EQUIVALENT_PLAN_NOT_DRILLED)
    notes.append(PINTLE_CAD_DRAWING_BASIS)
    if plate_t is not None:
        notes.append(f'faceplate {plate_t:.2f} mm x d{2.0 * plate_r:.2f} mm '
                     f'with the annulus bore - {plate["source"]}')
    notes.append(plate_note)
    return {'d_post': d_post, 'gap': gap, 'bore': bore, 'mode': mode,
            'n_holes': n_holes, 'd_hole': d_hole, 'skip': skip,
            'hole_depth': hole_depth, 'not_drawn_reason': not_drawn,
            'plate_t': plate_t, 'plate_r': plate_r, 'x0': x0,
            'x_face': x_face, 'x_holes': x_holes, 'x_tip': x_tip,
            'source_path': yol, 'notes': notes}


def pintle_assembly_refusal(geo, chamber_length_mm, grain_front_mm=None,
                            grain_port_radius_mm=None):
    """Pintle direğinin montaj girişimi — STEP ve STL AYNI hüküm.

    Direk kamaradan taşamaz; tane varsa direk ucu tanenin ön yüzünü geçip
    direk tanenin portundan kalınsa iki katı iç içe geçer (eksenel + radyal
    örtüşme). Döner: ``None`` ya da ``PintleCADError``."""
    if geo['x_tip'] > chamber_length_mm + _MONTAJ_GIRISIM_TOLERANS_MM:
        return _pintle_red(
            'chamber_length', 'pintle_post_longer_than_chamber',
            f'the pintle post ends at x = {geo["x_tip"]:.2f} mm but the '
            f'chamber is only {chamber_length_mm:.2f} mm long')
    if (grain_front_mm is not None and grain_port_radius_mm is not None
            and geo['x_tip'] - grain_front_mm > _MONTAJ_GIRISIM_TOLERANS_MM
            and geo['d_post'] / 2.0 - grain_port_radius_mm
            > _MONTAJ_GIRISIM_TOLERANS_MM):
        return _pintle_red(
            f'{geo["source_path"]}.d_pintle_mm',
            'pintle_post_intersects_fuel_grain',
            f'the pintle post (d{geo["d_post"]:.2f} mm) reaches '
            f'x = {geo["x_tip"]:.2f} mm, past the grain front at '
            f'x = {grain_front_mm:.2f} mm, and is wider than the grain port '
            f'(d{2.0 * grain_port_radius_mm:.2f} mm)')
    return None



# ---------------------------------------------------------------------------
# ÖH V3 CAD A1 · H5 — İMALAT EMNİYET KAPISI (karar §28-21 (i), Astra)
# ---------------------------------------------------------------------------
#
# ÖLÇÜLDÜ (7 Eki CAD kontrolü, hibrit örnek 3 kN): kamara imalat STEP'i kendi
# parça adında "safety factor at this wall = 0.8267 - BELOW 1.0, THE WALL
# FAILS" yazarken HTTP 200 ile iniyordu; DXF de aynı cümleyi basıyordu. Karar
# (§28-21 (i)): dosya adı/etiket dosyayla birlikte dolaşmayı garanti etmez;
# basınç taşıyan parçada SF < 1, SF eksik, geçersiz ya da çizilen geometriyle
# eşleşmiyorsa imalat STEP'i (ve aynı paketin DXF imalat çizimi) SUNUCUDA
# reddedilir. Kapı genel bir kuraldır; kök neden (SF 0,8267) yapı SF
# kulvarındadır ve bu kapı onu değiştirmez.
#
# Kapı, dosyanın kendi künyesinin bastığı SAYIYI okur (``_chamber_wall_design``
# / ``_nozzle_wall_design`` — tek kaynak): etikette ne yazıyorsa kapı ona
# hükmeder.

#: İmalat dosyası için asgari emniyet katsayısı. 1,0 bir tasarım hedefi
#: DEĞİLDİR: hesaplanan yükte malzemenin sınırına varıldığı noktadır; altında
#: çizilen parça kendi analizine göre yükü taşımaz (karar §28-21 (i)).
MANUFACTURING_SF_MIN = 1.0

#: Çizilen cidar ile SF'nin hesaplandığı cidarın eşleşme toleransı [mm].
#: İki sayı aynı yapısal bloğun kayan noktalı çıktısıdır; ``_chamber_wall_
#: design``in "çizilen ⟷ önerilen" notu da bu eşiği okur (tek tanım).
WALL_MATCH_TOLERANCE_MM = 1e-6

#: HTTP gövdesindeki makine kodu (``status``) ve başlık i18n anahtarı.
SF_GATE_STATUS = 'manufacturing_safety_gate_closed'
SF_GATE_MESSAGE_KEY = 'out.export.sfGate.refused'

#: Ret nedeni -> i18n anahtarı (metinler i18n_common.js'te, EN = TR).
SF_GATE_REASON_KEYS = {
    'sf_below_one': 'out.export.sfGate.reason.sf_below_one',
    'sf_missing': 'out.export.sfGate.reason.sf_missing',
    'sf_not_numeric': 'out.export.sfGate.reason.sf_not_numeric',
    'outside_model_validity':
        'out.export.sfGate.reason.outside_model_validity',
    'sf_wall_mismatch': 'out.export.sfGate.reason.sf_wall_mismatch',
    'sf_wall_not_established':
        'out.export.sfGate.reason.sf_wall_not_established',
}

#: Parça adı -> i18n anahtarı.
SF_GATE_PART_KEYS = {
    'chamber': 'out.export.sfGate.part.chamber',
    'nozzle': 'out.export.sfGate.part.nozzle',
    'fuel_tank': 'out.export.sfGate.part.fuel_tank',
    'oxidizer_tank': 'out.export.sfGate.part.oxidizer_tank',
}

#: Kamara cidarının yapısal sonucunu MODEL GEÇERLİLİK SINIRI DIŞINDA ilan
#: eden, çözücünün ZATEN yayımladığı bayraklar (karar §28-24 (C): "erime
#: noktası üstünde hesaplanan dayanım, SF ve kütle geçerli tasarım çıktısı
#: gibi sunulmaz"). Her giriş: (structural_analysis'e göreli yol, ret
#: değeri, gerekçe). Kapının SF okuduğu bloğun KENDİ bayrağı
#: (``STRUCTURAL_BLOCK_VALIDITY_FLAG``) ayrıca okunur; aşağıya bakın.
STRUCTURAL_VALIDITY_MARKERS = (
    ('thermal_analysis.strength_derating.exceeds_melting_point', True,
     'the chamber wall was evaluated at or above its melting point; the '
     'strength there is an extrapolation (the derating curve is held at its '
     'last point), so the structural result is outside the model validity '
     'limit and its safety factor is not a valid design output'),
)

#: ÖH V301 / B5 (20 Eki makale ölçümleri) — SF'nin OKUNDUĞU BLOĞUN geçerlilik
#: bayrağı. Yapısal modül her üç motor için kapının SF okuduğu blokta
#: (hibrit ``chamber_analysis``, katı ``case_analysis``, sıvı
#: ``chamber_structure``) ``model_validity_limit_exceeded`` yayımlıyor
#: (``structural_analysis.structural_model_validity`` /
#: ``model_validity_publication``); kapı yalnız hibrit erime işaretini
#: okuyordu. ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/makale1/B5/once.json``):
#: radyatif soğutmalı örnek sıvıda (inconel_718 cidarı 1800 K) ve sıcak
#: kasalı katıda (aluminum_6061, kasa ~731 K) bayrak True iken STEP / STL /
#: DXF HTTP 200 ile iniyordu. True = ret; None (değerlendirilmedi) ret
#: değildir; bayrak gerçek bir mantıksal değer olmalıdır (numpy dâhil).
STRUCTURAL_BLOCK_VALIDITY_FLAG = 'model_validity_limit_exceeded'
#: Bloğun kendi künyesi (dize ise ``validity_basis`` olarak taşınır).
STRUCTURAL_BLOCK_VALIDITY_BASIS = 'model_validity_limit_exceeded_basis'
#: Blok künye yayımlamıyorsa ``validity_basis`` olarak yazılan sabit metin.
STRUCTURAL_BLOCK_VALIDITY_DEFAULT_BASIS = (
    'the structural block that publishes this safety factor declares its '
    'result outside the validity limit of the structural model, so the '
    'safety factor is not a valid design output')


def _is_true_flag(deger):
    """Kapının bayrak tanımı: gerçek ``bool`` / ``np.bool_`` ve True."""
    return isinstance(deger, (bool, np.bool_)) and bool(deger) is True


#: Kamara SF'sinin, yapısal bloğun ölçüm adayları yoksa okunduğu genel
#: alanlar — ``_wall_safety_factor``in geriye dönük tek-sayı sırasıyla AYNI.
_WALL_SF_FALLBACK_KEYS = ('safety_factor_total', 'hoop_safety_factor',
                          'safety_factor')


def _strict_number(value):
    """Kapının sayı tanımı: ``bool`` olmayan, SONLU ``int``/``float``.

    Dize ("0.83") kabul edilmez: çözücü SF'yi sayı olarak yayımlar; dizeye
    dönüşmüş bir SF bozulmuş veridir ve kapı onu "sayısal değil" diye
    reddeder (fail-closed). Sonluluk merkezden okunur
    (``input_guard.finite_number``, OH-D27-11); burada yalnız TÜR süzülür.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return finite_number(value)


def _nested(d, dotted):
    for k in dotted.split('.'):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _sf_check(part, sf_field, sf_raw, drawn_mm, sf_wall_mm, sf_wall_field,
              extra=()):
    """Tek parçanın kapı hükmü -> ret kayıtları listesi (boş = geçti)."""
    base = {'part': part, 'part_key': SF_GATE_PART_KEYS[part],
            'safety_factor_field': sf_field,
            'drawn_wall_mm': (round(drawn_mm, 4)
                              if drawn_mm is not None else None),
            'sf_wall_field': sf_wall_field,
            'sf_wall_mm': (round(sf_wall_mm, 4)
                           if sf_wall_mm is not None else None)}

    def kayit(reason, **ek):
        r = dict(base, reason=reason, reason_key=SF_GATE_REASON_KEYS[reason])
        r.update(ek)
        return r

    out = []
    if sf_raw is None:
        return [kayit('sf_missing', safety_factor=None)]
    sf = _strict_number(sf_raw)
    if sf is None:
        # Ş2: ham ``repr`` değil, yalnız tür adı (+ uzunluk).
        return [kayit('sf_not_numeric', safety_factor=None,
                      safety_factor_raw=_unreflected_value(sf_raw))]
    sf_r = round(sf, 4)
    for field, reason_text in extra:
        out.append(kayit('outside_model_validity', safety_factor=sf_r,
                         validity_field=field, validity_basis=reason_text))
    if sf_wall_mm is None:
        out.append(kayit('sf_wall_not_established', safety_factor=sf_r))
    elif (drawn_mm is not None
          and abs(drawn_mm - sf_wall_mm) > WALL_MATCH_TOLERANCE_MM):
        out.append(kayit('sf_wall_mismatch', safety_factor=sf_r))
    if sf < MANUFACTURING_SF_MIN:
        out.append(kayit('sf_below_one', safety_factor=sf_r))
    return out


def manufacturing_safety_refusals(motor_data):
    """Motor imalat dosyası (STEP / DXF) için emniyet kapısının hükmü.

    Döner: ret kayıtları listesi; boş liste = kapı açık. Her kayıt:
    ``part``, ``reason`` (``SF_GATE_REASON_KEYS``), ``safety_factor``,
    ``safety_factor_field``, ``drawn_wall_mm``, ``sf_wall_mm`` ve i18n
    anahtarları.

    Parçalar:
      * ``chamber`` — HER ZAMAN, çizilecek bir cidar çözülüyorsa. Cidar hiç
        çözülmüyorsa kapı konuşmaz: STEP üreticisi o gövdeyi zaten adıyla
        reddeder, DXF de dış profili çizmez (basınç taşıyan cidar dosyada
        yoktur).
      * ``nozzle`` — yalnız çözücü lüle için SF yayımlıyorsa: çizilen et
        ile eşleşmesi gereken iki kaynak (``nozzle_geometry`` ve yapısal
        ``nozzle_analysis``).
    Kapanış başlığı (kapak) bu kapının dışındadır: CAD düz kapak çizer,
    analiz SF'yi başka bir kapak tipinde/kalınlıkta yayımlar (CAD kontrolü
    U3); bu eşleşme CAD A2'nin kalemidir ve raporda beyan edilir.
    """
    from hrma.export.motor_geometry import normalise_export_geometry
    # Lüle kuralı boğaz çapını METRE okur; birim tek kaynaktan kazanılır
    # (yapısal bloklar mm adlıdır ve normalizeden etkilenmez).
    md, _rapor = normalise_export_geometry(
        motor_data if isinstance(motor_data, dict) else {})
    out = []

    # ---- kamara cidarı ----
    design = _chamber_wall_design(md)
    if design['thickness_m'] is not None:
        drawn_mm = design['thickness_m'] * 1000.0
        struct = md.get('structural_analysis')
        struct = struct if isinstance(struct, dict) else {}
        block_name = design['schema']
        block = struct.get(block_name) if block_name else None
        block = block if isinstance(block, dict) else {}
        schema = CHAMBER_WALL_SF_SCHEMAS.get(block_name) or {}
        adaylar = [k for k in schema.get('measured_keys', ())
                   if not _declares_input_readback(block.get(f'{k}_source'))]
        adaylar += [k for k in _WALL_SF_FALLBACK_KEYS if k not in adaylar]
        sf_key, sf_raw = None, None
        for k in adaylar:
            if block.get(k) is not None:
                sf_key, sf_raw = k, block.get(k)
                break
        sf_field = (f'structural_analysis.{block_name}.'
                    f'{sf_key or adaylar[0]}')
        used_key = next((used for name, used, _r, _a in CHAMBER_WALL_SCHEMAS
                         if name == block_name), None)
        extra = []
        for rel, bad, text in STRUCTURAL_VALIDITY_MARKERS:
            deger = _nested(struct, rel)
            # Bayrak gerçek bir mantıksal değer olmalı (numpy bool dâhil);
            # 1 / "true" gibi kaçak biçimler bayrak sayılmaz.
            if (isinstance(deger, (bool, np.bool_))
                    and bool(deger) is bad):
                extra.append((f'structural_analysis.{rel}', text))
        # ÖH V301 / B5: SF'nin okunduğu bloğun kendi bayrağı. Hibrit erime
        # işareti bu parça için kayıt ürettiyse ikinci kayıt YAZILMAZ (aynı
        # parça, aynı ret nedeni; o gövdelerin yanıtı bit-aynı kalır).
        if (not extra and block_name
                and _is_true_flag(block.get(STRUCTURAL_BLOCK_VALIDITY_FLAG))):
            kunye = block.get(STRUCTURAL_BLOCK_VALIDITY_BASIS)
            extra.append((
                f'structural_analysis.{block_name}.'
                f'{STRUCTURAL_BLOCK_VALIDITY_FLAG}',
                kunye if isinstance(kunye, str) and kunye
                else STRUCTURAL_BLOCK_VALIDITY_DEFAULT_BASIS))
        out += _sf_check(
            'chamber', sf_field, sf_raw, drawn_mm, design['as_designed_mm'],
            (f'structural_analysis.{block_name}.{used_key}'
             if used_key else None), extra)

    # ---- lüle ----
    noz = _nozzle_wall_design(md)
    drawn_noz_mm = noz['thickness_m'] * 1000.0
    if noz['safety_factor_raw'] is not None:
        out += _sf_check(
            'nozzle', noz['safety_factor_field'], noz['safety_factor_raw'],
            drawn_noz_mm, noz['published_mm'],
            'nozzle_geometry.wall_thickness')
    struct = md.get('structural_analysis')
    nozzle_analysis = (struct.get('nozzle_analysis')
                       if isinstance(struct, dict) else None)
    if (isinstance(nozzle_analysis, dict)
            and nozzle_analysis.get('safety_factor') is not None):
        # Yapısal lüle analizi SF'yi BOĞAZ cidarında yayımlar; çizilen lüle
        # tek tip ofset etle kurulduğu için boğaz cidarı çizilen ettir.
        out += _sf_check(
            'nozzle', 'structural_analysis.nozzle_analysis.safety_factor',
            nozzle_analysis.get('safety_factor'), drawn_noz_mm,
            _strict_number(nozzle_analysis.get('throat_thickness_used_mm')),
            'structural_analysis.nozzle_analysis.throat_thickness_used_mm')
    return out


def tank_manufacturing_safety_refusals(tank_data):
    """Tank imalat paketi (STEP + STL) için aynı kapı — tank SF yayımlıyorsa.

    Tank kartı SF'yi ``<tank>.structural.safety_factor`` adıyla, basınç
    kabı denetiminin koştuğu cidarı ``<tank>.pressure_vessel
    .wall_thickness_used_mm`` adıyla yayımlar; çizilen cidar
    ``<tank>.dimensions.wall_thickness``tır (``step_export
    .generate_tank_step``in okuduğu alan). Denetim bloğu yoksa SF'nin ait
    olduğu cidar aynı kayıttaki çizilen cidardır (o SF ile boyutlanır).
    """
    td_all = tank_data if isinstance(tank_data, dict) else {}
    out = []
    for part in ('fuel_tank', 'oxidizer_tank'):
        td = td_all.get(part)
        if not isinstance(td, dict):
            continue
        structural = td.get('structural')
        structural = structural if isinstance(structural, dict) else {}
        if 'safety_factor' not in structural:
            # Tank SF YAYIMLAMIYOR: karar metni tankı "SF yayımlıyorsa"
            # kapsar; yayımlamayan tank kapının dışındadır (raporda beyan).
            continue
        dims = td.get('dimensions')
        dims = dims if isinstance(dims, dict) else {}
        pv = td.get('pressure_vessel')
        pv = pv if isinstance(pv, dict) else {}
        cizilen = _strict_number(dims.get('wall_thickness'))
        if pv.get('wall_thickness_used_mm') is not None:
            # Basınç kabı denetimi kendi cidarını yayımlıyor: SF'nin ait
            # olduğu cidar odur ve çizilenle eşleşmek zorundadır.
            sf_cidar = _strict_number(pv.get('wall_thickness_used_mm'))
            sf_cidar_alani = f'{part}.pressure_vessel.wall_thickness_used_mm'
        else:
            # Denetim bloğu yoksa SF ile çizilen cidar AYNI tank kaydının
            # sözleşmesidir: ``dimensions.wall_thickness`` o kayıttaki
            # ``structural.safety_factor`` ile boyutlandırılır
            # (``wall_thickness_basis``: t = P·r / (akma / SF)).
            sf_cidar = cizilen
            sf_cidar_alani = f'{part}.dimensions.wall_thickness'
        out += _sf_check(
            part, f'{part}.structural.safety_factor',
            structural.get('safety_factor'), cizilen, sf_cidar,
            sf_cidar_alani)
        # ÖH V31 CV-0 — çizilen düz kapak (B1 §4.3 (c)). Kapak gövdeyle
        # AYNI kapsamda denetlenir: tank SF yayımlıyorsa.
        out += _tank_head_refusals(part, tank_head_assessment(part, td))
    return out


# ---------------------------------------------------------------------------
# ÖH V31 CV-0 · TANK KAPAĞI KAPISI (B1 §4.3 (c); doktrin §28-42)
# ---------------------------------------------------------------------------
#
# ÖLÇÜLDÜ (19 Eki; ``docs/scofield/raw/OH/V31/cv0/once.json``): tank STEP/STL
# düz kapakları gövde cidarı kalınlığıyla (3 mm, asgari imalat kalınlığı)
# çiziyor; kapağın yeterliliği hesaplanmıyordu ve imalat kapısı yalnız gövde
# SF'sine bakıyordu. Örnek sıvı (25 kN, 30 s) oksitleyici tankında basit
# mesnet gerilmesi 2938 MPa, akma 345 MPa: SF 0,117. Paket HTTP 200 ile
# iniyordu.
#
# SF TABANI kapıdan ÖLÇÜLDÜ, yeni tanım icat edilmedi: gövde dalının okuduğu
# ``structural.safety_factor`` = akma dayanımı / hesaplanan gerilme
# (``_design_propellant_tanks``: izin = akma / SF, t = p·r / izin; yayımdan
# geri hesap σ_akma·t_basınç/(p·r) = 2,5 = yayımlanan, once.json (A)).
# Kapak SF'si aynı tabandadır: SF_kapak = σ_akma / σ_kapak, eşik
# ``MANUFACTURING_SF_MIN``.
#
# Gerilme: Roark's Formulas for Stress and Strain, 7. baskı, Tablo 11.2,
# durum 10a (r_o → 0; dış kenar basit mesnetli, tüm yüzeyde düzgün basınç):
# σ_maks = 3(3+ν)·q·a² / (8·t²), merkezde. Sayfa doğrulanmadı (yerel kopya
# yok). Aynı bağıntı depoda ``structural_analysis`` kapak analizinde de var.
# Boyut: [Pa]·[mm²]/[mm²] = [Pa]. Çapa (B1 §4.1 girdisi, oksitleyici tankı):
# a = 170,35 mm, t = 3 mm, q = 2,6947 bar, ν = 0,33 -> 1085,0 MPa.
# q = nitelendirme basıncı = ``structural.pressure_rating`` (işletme) ×
# ``RELIEF_VALVE_SET_PRESSURE_FACTOR`` (tankın kendi emniyet vanası açılmadan
# ulaştığı basınç; basınçlı kap analizi de bu basınçta nitelendirir).
# a = boşluk yarıçapı D/2 (kapak boşluğu kapatır; cidar dışarı eklidir).
# t = çizilen kapak kalınlığı = ``dimensions.wall_thickness``
# (``tank_shell_geometry_mm`` kapağı bu kalınlıkla çizer).
# Malzeme: ``structural.material_key`` -> ``materials_db`` (akma, ν), oda
# sıcaklığı; tank kartı da ortam sıcaklığını beyan eder.

#: Kapak modelinin künyesi (ret kaydı bunu taşır).
TANK_HEAD_MODEL = (
    "Roark's Formulas for Stress and Strain, 7th ed., Table 11.2 case 10a "
    '(r_o -> 0): simply supported flat circular plate, uniform pressure q '
    'over the whole plate, sigma_max = 3 (3 + nu) q a^2 / (8 t^2) at the '
    'centre; page not verified')

#: Kapak kaydının parça adı (``sf_gate_body`` sözleşmesi).
TANK_HEAD_PART = 'tank_head'

#: Tank -> kapak parça adının i18n anahtarı.
TANK_HEAD_PART_KEYS = {
    'fuel_tank': 'out.export.sfGate.part.fuel_tank_head',
    'oxidizer_tank': 'out.export.sfGate.part.oxidizer_tank_head',
}

#: Kapak ret nedeni -> i18n anahtarı (metinler i18n_common.js'te, EN = TR).
TANK_HEAD_GATE_REASON_KEYS = {
    'head_sf_below_one': 'out.export.sfGate.reason.head_sf_below_one',
    'head_sf_not_computable':
        'out.export.sfGate.reason.head_sf_not_computable',
}

#: Kapak hesabı girdisinin kullanılamama nedenleri (kayıtta kod olarak).
TANK_HEAD_INPUT_PROBLEMS = ('missing', 'not_finite', 'not_positive',
                            'unknown_material', 'material_data_invalid',
                            'result_not_finite')

#: Kapı hükmü (etiket cümlesi bunlardan birini taşır).
TANK_HEAD_VERDICTS = ('cleared', 'refused', 'not_engaged')

#: Malzeme anahtarının kabul edilen en uzun hâli (karakter). Daha uzun dize
#: ``materials_db``ye sorulmaz (istemci metni sözlük aramasına sınırsız
#: girmez); kanonik anahtar ve takma adlar bunun çok altındadır.
TANK_HEAD_MATERIAL_KEY_MAX_LEN = 64

#: Kapak hesabının girdileri (tank kaydına göreli yol).
_TANK_HEAD_INPUT_FIELDS = ('dimensions.diameter', 'dimensions.wall_thickness',
                           'structural.pressure_rating',
                           'structural.material_key')


def tank_head_assessment(part, td):
    """Çizilen düz kapağın yapısal hükmü — TEK kaynak (kapı + künye).

    ``part``: alan yollarının öneki (``fuel_tank`` / ``oxidizer_tank``);
    ``td``: tank kaydı (``propellant_tanks.<tank>``). Döner sözlük:

    * ``engaged``: kapı bu tankı denetliyor mu (gövdeyle aynı kapsam:
      ``structural.safety_factor`` yayımlanıyorsa);
    * ``computed``: kapak SF'si hesaplandı mı; hesaplanamadıysa
      ``problem_field`` (tank kaydına göreli yol) ve ``problem``
      (``TANK_HEAD_INPUT_PROBLEMS``);
    * sayılar: ``safety_factor``, ``head_stress_mpa``,
      ``yield_strength_mpa``, ``poisson_ratio``, ``operating_pressure_bar``,
      ``qualification_pressure_bar``, ``relief_factor``, ``head_radius_mm``,
      ``drawn_head_mm``, ``required_head_thickness_mm`` (SF = 1 olan düz
      kapak kalınlığı, aynı bağıntıdan), ``material_key`` (kanonik);
    * ``verdict``: ``TANK_HEAD_VERDICTS``.

    Fail-closed: sayı ``bool`` olmayan SONLU ``int``/``float`` olmalıdır
    (dize, NaN, ±inf kabul edilmez); çap, kalınlık ve basınç > 0. Basıncı
    sıfır ya da negatif olan bir kap için kapak hükmü verilmez, kapı reddeder.
    """
    from hrma.data.materials_db import get_material_safe
    from hrma.engines.liquid_rocket_engine import (
        RELIEF_VALVE_SET_PRESSURE_FACTOR)
    td = td if isinstance(td, dict) else {}
    dims = td.get('dimensions')
    dims = dims if isinstance(dims, dict) else {}
    structural = td.get('structural')
    structural = structural if isinstance(structural, dict) else {}
    sonuc = {'part': part, 'engaged': 'safety_factor' in structural,
             'computed': False, 'problem_field': None, 'problem': None,
             'safety_factor': None, 'head_stress_mpa': None,
             'yield_strength_mpa': None, 'poisson_ratio': None,
             'operating_pressure_bar': None,
             'qualification_pressure_bar': None,
             'relief_factor': float(RELIEF_VALVE_SET_PRESSURE_FACTOR),
             'head_radius_mm': None, 'drawn_head_mm': None,
             'required_head_thickness_mm': None, 'material_key': None,
             'model': TANK_HEAD_MODEL}

    def hukum():
        if not sonuc['engaged']:
            sonuc['verdict'] = 'not_engaged'
        elif (sonuc['computed']
              and sonuc['safety_factor'] >= MANUFACTURING_SF_MIN):
            sonuc['verdict'] = 'cleared'
        else:
            sonuc['verdict'] = 'refused'
        return sonuc

    def sorun(alan, neden):
        sonuc['problem_field'], sonuc['problem'] = alan, neden
        return hukum()

    kaynak = {'dimensions.diameter': dims.get('diameter'),
              'dimensions.wall_thickness': dims.get('wall_thickness'),
              'structural.pressure_rating': structural.get('pressure_rating')}
    sayi = {}
    for alan, ham in kaynak.items():
        if ham is None:
            return sorun(alan, 'missing')
        v = _strict_number(ham)
        if v is None:
            return sorun(alan, 'not_finite')
        if v <= 0.0:
            return sorun(alan, 'not_positive')
        sayi[alan] = float(v)
    ham_mat = structural.get('material_key')
    if ham_mat is None:
        return sorun('structural.material_key', 'missing')
    if (not isinstance(ham_mat, str) or not ham_mat
            or len(ham_mat) > TANK_HEAD_MATERIAL_KEY_MAX_LEN):
        return sorun('structural.material_key', 'unknown_material')
    try:
        mat, mat_key = get_material_safe(ham_mat)
    except KeyError:
        return sorun('structural.material_key', 'unknown_material')
    sy = _strict_number(mat.get('yield_strength'))         # Pa
    nu = _strict_number(mat.get('poisson_ratio'))
    if sy is None or sy <= 0.0 or nu is None or not 0.0 < nu < 0.5:
        return sorun('structural.material_key', 'material_data_invalid')

    a = sayi['dimensions.diameter'] / 2.0                  # mm
    t = sayi['dimensions.wall_thickness']                  # mm
    p_op = sayi['structural.pressure_rating']              # bar
    q = p_op * 1e5 * float(RELIEF_VALVE_SET_PRESSURE_FACTOR)   # Pa
    katsayi = 3.0 * (3.0 + nu) / 8.0
    oran = a / t                                           # boyutsuz
    # ``**`` taşmada OverflowError fırlatır; çarpım inf verir ve aşağıdaki
    # sonluluk denetimi onu adıyla reddeder.
    sigma = katsayi * q * oran * oran                      # Pa
    t_gerekli = a * math.sqrt(katsayi * q / sy)            # mm
    sf = sy / sigma if sigma > 0.0 else None
    if not all(isinstance(x, float) and math.isfinite(x) and x > 0.0
               for x in (sigma, t_gerekli, sf)):
        return sorun('structural.pressure_rating', 'result_not_finite')
    sonuc.update({
        'computed': True, 'safety_factor': sf,
        'head_stress_mpa': sigma / 1e6, 'yield_strength_mpa': sy / 1e6,
        'poisson_ratio': nu, 'operating_pressure_bar': p_op,
        'qualification_pressure_bar': q / 1e5, 'head_radius_mm': a,
        'drawn_head_mm': t, 'required_head_thickness_mm': t_gerekli,
        'material_key': mat_key})
    return hukum()


def _tank_head_refusals(part, h):
    """Kapak hükmü -> ``sf_gate_body`` biçiminde ret kayıtları (boş = geçti)."""
    if h['verdict'] != 'refused':
        return []
    base = {'part': TANK_HEAD_PART, 'part_key': TANK_HEAD_PART_KEYS[part],
            'tank': part, 'head_model': TANK_HEAD_MODEL}
    if not h['computed']:
        alan = f"{part}.{h['problem_field']}"
        return [dict(base, reason='head_sf_not_computable',
                     reason_key=TANK_HEAD_GATE_REASON_KEYS[
                         'head_sf_not_computable'],
                     safety_factor=None, safety_factor_field=alan,
                     head_input_field=alan, head_input_problem=h['problem'])]
    return [dict(
        base, reason='head_sf_below_one',
        reason_key=TANK_HEAD_GATE_REASON_KEYS['head_sf_below_one'],
        safety_factor=round(h['safety_factor'], 4),
        # Kapının hükmettiği alan: çizilen kapak kalınlığı.
        safety_factor_field=f'{part}.dimensions.wall_thickness',
        drawn_head_mm=round(h['drawn_head_mm'], 4),
        head_stress_mpa=round(h['head_stress_mpa'], 2),
        yield_strength_mpa=round(h['yield_strength_mpa'], 2),
        poisson_ratio=h['poisson_ratio'],
        operating_pressure_bar=round(h['operating_pressure_bar'], 4),
        qualification_pressure_bar=round(h['qualification_pressure_bar'], 4),
        relief_factor=h['relief_factor'],
        head_radius_mm=round(h['head_radius_mm'], 4),
        required_head_thickness_mm=round(h['required_head_thickness_mm'], 3),
        material_key=h['material_key'])]


def tank_head_declaration(h):
    """Kapak hükmünün etiket/paket cümlesi (EN).

    ``h``: ``tank_head_assessment`` sonucu ya da ``None`` (üreteç kapı
    sonucunu almadıysa). Cümle YALNIZ sayılardan (``_strict_number``
    süzgeci) ve sabit kod listelerinden kurulur; sözlükte dize olarak ne
    gelirse gelsin etikete ham girmez.
    """
    if not isinstance(h, dict):
        return ('drawn flat head check: not supplied to this generator '
                '(the manufacturing safety gate of the tank CAD export '
                'computes it)')
    hukum = h.get('verdict')
    if hukum not in TANK_HEAD_VERDICTS:
        return 'drawn flat head check: verdict unreadable'
    kapi = {'cleared': 'manufacturing safety gate: head cleared',
            'refused': ('manufacturing safety gate: head REFUSED - this is '
                        'not a manufacturing file'),
            'not_engaged': ('manufacturing safety gate not engaged: this '
                            'tank card publishes no structural.'
                            'safety_factor')}[hukum]
    n = {k: _strict_number(h.get(k)) for k in (
        'safety_factor', 'head_stress_mpa', 'yield_strength_mpa',
        'operating_pressure_bar', 'qualification_pressure_bar',
        'relief_factor', 'drawn_head_mm', 'required_head_thickness_mm')}
    if h.get('computed') is True and None not in n.values():
        alt = n['safety_factor'] < MANUFACTURING_SF_MIN
        return (f"drawn flat head {n['drawn_head_mm']:.2f} mm: stress "
                f"{n['head_stress_mpa']:.1f} MPa at the "
                f"{n['qualification_pressure_bar']:.4f} bar qualification "
                f"pressure ({n['operating_pressure_bar']:.4f} bar x "
                f"{n['relief_factor']:g}), head safety factor "
                f"{n['safety_factor']:.3f} against the "
                f"{n['yield_strength_mpa']:.0f} MPa yield strength"
                + (f" - BELOW 1.0, a flat head of this radius needs "
                   f"{n['required_head_thickness_mm']:.2f} mm" if alt else '')
                + f' -> {kapi}')
    alan = h.get('problem_field')
    neden = h.get('problem')
    if alan not in _TANK_HEAD_INPUT_FIELDS or (
            neden not in TANK_HEAD_INPUT_PROBLEMS):
        alan, neden = 'input', 'unreadable'
    return (f'drawn flat head: safety factor NOT computable ({alan} '
            f'{neden}) -> {kapi}')


#: Ret nedeninin EN cümlesi (HTTP gövdesi ``message``; i18n karşılığı
#: ``SF_GATE_REASON_KEYS`` anahtarlarında, aynı yer tutucularla).
_SF_GATE_REASON_TEXT = {
    'sf_below_one': ('{part}: safety factor {safety_factor} is below 1.0 at '
                     'the drawn {drawn_wall_mm} mm wall '
                     '({safety_factor_field})'),
    'sf_missing': ('{part}: no safety factor is published for the drawn '
                   '{drawn_wall_mm} mm wall ({safety_factor_field})'),
    'sf_not_numeric': ('{part}: the published safety factor '
                       '{safety_factor_raw} is not a finite number '
                       '({safety_factor_field})'),
    'outside_model_validity': ('{part}: the structural result is outside the '
                               'model validity limit ({validity_field}), so '
                               'its safety factor {safety_factor} is not a '
                               'valid design output'),
    'sf_wall_mismatch': ('{part}: the safety factor {safety_factor} belongs to '
                         'a {sf_wall_mm} mm wall ({sf_wall_field}) but '
                         '{drawn_wall_mm} mm is drawn'),
    'sf_wall_not_established': ('{part}: the wall the safety factor '
                                '{safety_factor} was computed at is not '
                                'published ({sf_wall_field}), so it cannot be '
                                'matched to the drawn {drawn_wall_mm} mm '
                                'wall'),
    # ÖH V31 CV-0 — kapak dalı (anahtarlar ``TANK_HEAD_GATE_REASON_KEYS``).
    'head_sf_below_one': ('{part} ({tank}): safety factor {safety_factor} is '
                          'below 1.0 for the drawn {drawn_head_mm} mm flat '
                          'head (simply supported flat circular plate, '
                          'Roark Table 11.2 case 10a: {head_stress_mpa} MPa '
                          'at the {qualification_pressure_bar} bar '
                          'qualification pressure against the '
                          '{yield_strength_mpa} MPa yield strength); a flat '
                          'head of this radius needs at least '
                          '{required_head_thickness_mm} mm'),
    'head_sf_not_computable': ('{part} ({tank}): the structural adequacy of '
                               'the drawn flat head cannot be computed '
                               'because {head_input_field} is '
                               '{head_input_problem}'),
}


def sf_gate_body(refusals, artefact):
    """Kapının HTTP 422 gövdesi (EN cümle + i18n anahtarları + alanlar).

    ``artefact``: reddedilen çıktının adı (ör. ``'manufacturing STEP'``).
    """
    satirlar = []
    for r in refusals:
        params = {k: ('-' if v is None else v) for k, v in r.items()}
        satirlar.append(_SF_GATE_REASON_TEXT[r['reason']].format(**params))
    parts = sorted({r['part'] for r in refusals})
    message = (f'{artefact} refused by the manufacturing safety gate: no '
               'manufacturing file is written for a pressure-bearing part the '
               'analysis does not clear (' + '; '.join(satirlar) + ').')
    return {
        'status': SF_GATE_STATUS,
        'error': message,
        'message': message,
        'message_key': SF_GATE_MESSAGE_KEY,
        'message_params': {'count': len(parts), 'parts': ', '.join(parts),
                           'artefact': artefact},
        'refusals': list(refusals),
        'invalid_fields': [
            {'field': r['safety_factor_field'], 'reason': r['reason'],
             'part': r['part']} for r in refusals],
    }


# ---------------------------------------------------------------------------
# ÖH V3 CAD · CADP D-T5-3 / D-T5-5 — LÜLE KONTURU KAPISININ 422 GÖVDESİ
# ---------------------------------------------------------------------------
# Kapının kendisi ``nozzle_design.nozzle_contour_gate``tir (TEK işlev; STEP,
# DXF, çizim PDF'i, STL). ÖLÇÜLDÜ (14 Eki, CADP D-T5-3): pürüzsüz yüzey
# turunun altı ret gerekçesi yalnız İngilizce cümle + ``invalid_fields``
# taşıyordu; TR arayüzde de İngilizce basılıyordu. Gövde artık emniyet
# kapısıyla AYNI biçimdedir (``message_key`` + ``refusals[*].reason_key``),
# ``reject_body.js`` onu sözlükten basar (EN = TR). Aile sözleşmesi
# (``status: 'error'``, ``error: 'incomplete_export_inputs'``,
# ``invalid_fields``) DEĞİŞMEZ; mevcut okuyucular aynen çalışır.
CONTOUR_GATE_ERROR = 'incomplete_export_inputs'
CONTOUR_GATE_MESSAGE_KEY = 'out.export.contourGate.refused'
#: Ret nedeni -> i18n anahtarı; nedenlerin TEK listesi
#: ``nozzle_design.NOZZLE_CONTOUR_REASONS`` (anahtar adı = neden).
#: Anahtarlar LİTERAL yazılır: ölü çeviri bekçisi
#: (tests/test_i18n_common.py::python_dispatched_keys) Python kaynağındaki
#: literal anahtarları "kullanılıyor" sayar; f-string ile kurulan anahtarı
#: göremez. Küme eşitliği aşağıda içe aktarmada denetlenir (fail-closed).
CONTOUR_GATE_REASON_KEYS = {
    'non_finite_contour_point':
        'out.export.contourGate.reason.non_finite_contour_point',
    'too_few_contour_points':
        'out.export.contourGate.reason.too_few_contour_points',
    'contour_interpolation_failed':
        'out.export.contourGate.reason.contour_interpolation_failed',
    'contour_interpolation_oscillates':
        'out.export.contourGate.reason.contour_interpolation_oscillates',
    'contour_outside_point_envelope':
        'out.export.contourGate.reason.contour_outside_point_envelope',
    'contour_profile_not_closed':
        'out.export.contourGate.reason.contour_profile_not_closed',
    'contour_turns_back':
        'out.export.contourGate.reason.contour_turns_back',
    'throat_radius_curvature_not_positive':
        'out.export.contourGate.reason.throat_radius_curvature_not_positive',
    'contour_angle_not_finite':
        'out.export.contourGate.reason.contour_angle_not_finite',
}
if set(CONTOUR_GATE_REASON_KEYS) != set(NOZZLE_CONTOUR_REASONS) or any(
        _anahtar.rsplit('.', 1)[-1] != _neden
        for _neden, _anahtar in CONTOUR_GATE_REASON_KEYS.items()):
    raise RuntimeError('CONTOUR_GATE_REASON_KEYS, NOZZLE_CONTOUR_REASONS ile '
                       'birebir eşleşmiyor')
#: Kontur kapısının parçası lüledir; parça adı emniyet kapısının anahtarı.
CONTOUR_GATE_PART = 'nozzle'


def contour_gate_body(reason, message, artefact):
    """Lüle konturu kapısının HTTP 422 gövdesi.

    ``reason``: ``NOZZLE_CONTOUR_REASONS`` kodu; ``message``: kapının EN
    cümlesi (istek değerini yansıtmaz); ``artefact``: reddedilen çıktı.
    """
    kayit = {'part': CONTOUR_GATE_PART,
             'part_key': SF_GATE_PART_KEYS[CONTOUR_GATE_PART],
             'reason': reason,
             'reason_key': CONTOUR_GATE_REASON_KEYS[reason],
             'field': NOZZLE_CONTOUR_FIELD}
    return {
        'status': 'error',
        'error': CONTOUR_GATE_ERROR,
        'message': message,
        'message_key': CONTOUR_GATE_MESSAGE_KEY,
        'message_params': {'count': 1, 'artefact': artefact},
        'refusals': [kayit],
        'invalid_fields': [{'field': NOZZLE_CONTOUR_FIELD, 'reason': reason}],
    }


def contour_gate_refusal_reason(invalid_fields):
    """``invalid_fields`` TEK bir lüle konturu reddiyse nedenini döndürür.

    STEP üreticisinin ``StepExportDataError``ı aile sözleşmesiyle gelir;
    uç bu yardımcıyla gövdeyi ``contour_gate_body`` biçimine çevirir. Başka
    her ret (eksik alan, birim) ``None`` döner ve AYNEN basılır.
    """
    kayitlar = list(invalid_fields or ())
    if len(kayitlar) != 1 or not isinstance(kayitlar[0], dict):
        return None
    k = kayitlar[0]
    if (k.get('field') == NOZZLE_CONTOUR_FIELD
            and k.get('reason') in CONTOUR_GATE_REASON_KEYS):
        return k['reason']
    return None


#: Bir koşuda ENJEKTÖRÜN VAR OLDUĞUNU gösteren çözücü blokları.
#: ÖH D15 (defter P9B1-12): CAD katmanı enjektör plakasını KOŞULSUZ
#: üretiyordu. Ölçüldü (31 Ağustos 2026, ``motor_solid`` fikstürü): katı
#: motorun montajında 30 mm x Ø100 mm çelik bir plaka vardı ve bildirilen
#: kuru kütlenin **%10,96**'sı bu var olmayan parçadandı; aynı koşuda
#: ``technical_drawings.injector`` alanlarının HEPSİ 'NOT AVAILABLE' diyordu.
#: Tek süzgeç uygulama katmanındaydı (``app.py`` skip tablosu) ve
#: ``generate_3d_motor_assembly``in yedi çağrı yerinden yalnız birinde vardı;
#: kütle dökümü ise süzgeçten ÖNCE üretildiği için her yolda enjektörü
#: sayıyordu. Kapı artık grain kapısıyla simetrik biçimde CAD katmanındadır:
#: motor tipi TAHMİN EDİLMEZ, çözücünün enjektör yayımlayıp yayımlamadığına
#: bakılır (katı motor çözücüsü hiçbirini yayımlamaz).
INJECTOR_EVIDENCE_KEYS = ('injector_results', 'injector_design',
                          'injector_design_detail', 'injector_pattern',
                          'injection_system', 'injector')

#: ÖH D24 / P9B1-27 — MONTAJ GİRİŞİM TOLERANSI [mm]. İki katının eksenel
#: örtüşmesi bu değeri AŞARSA montaj reddedilir. Sıfır değildir çünkü ağlar
#: kayan noktalı: aynı düzlemde biten iki yüzey ~1e-9 mm örtüşme raporlayabilir.
#: 1 µm imalat çözünürlüğünün çok altındadır, yani gerçek bir çakışmayı
#: gizlemez ama sayısal gürültüyü de hata saymaz. TEK KAYNAK: girişim
#: denetimi yapan her yer bu sabiti okur, kendi eşiğini yazmaz.
_MONTAJ_GIRISIM_TOLERANS_MM = 1e-3


def _injector_evidence(motor_data):
    """Koşu bir enjektör yayımlıyor mu? Döner: ``(var_mı, künye)``."""
    md = motor_data if isinstance(motor_data, dict) else {}
    found = [k for k in INJECTOR_EVIDENCE_KEYS if md.get(k)]
    if found:
        return True, 'solver injector blocks: ' + ', '.join(found)
    if (md.get('design_config') or {}).get('injector'):
        return True, 'design_config.injector'
    return False, ('injector_not_in_result: this analysis run publishes no '
                   'injector (none of '
                   + ', '.join(INJECTOR_EVIDENCE_KEYS)
                   + '); no injector plate is drawn, weighed or exported')


def _injector_plate_design(motor_data, chamber_diameter_m=None, wall_m=None):
    """Enjektör plakası — mesh, kütle ve teknik çizim için TEK kaynak.

    Döner sözlük:
        thickness_m -> plaka kalınlığı [m] (None = koşu yayımlamıyor)
        radius_m    -> plaka yarıçapı [m] (None olabilir)
        mass_kg     -> enjektör çözücüsünün OTORİTATİF plaka kütlesi (varsa)
        material    -> plaka malzemesi adı (varsa)
        source      -> künye metni

    ÖH D15 (defter P9B1-13). Kusur: aynı koşuda plaka DÖRT ayrı sayıydı —
    3B katı sabit 30,00 mm x Ø(kamara deliği), teknik çizim yapısal analizin
    KAPAK kalınlığı 13,64 mm, kütle hesabı 13,64 mm x Ø(delik + 2 x cidar), ve
    kullanıcının gerçekte tasarladığı plaka (``injector_results
    .plate_structural``) 3,00 mm x Ø152,53 mm. Ölçüldü (31 Ağustos 2026,
    hibrit): mesh/çizim oranı 2,20x, mesh/gerçek oran 10,0x. STL'i açan kişi
    çizimdeki parçayı görmüyordu, çizimdeki parça da kullanıcının plakası
    değildi (kapak plakasıydı).

    FAIL-CLOSED: koşu bir enjektör plakası kalınlığı yayımlamıyorsa (sıvı
    motorun bugünkü hâli) plaka ÇİZİLMEZ, TARTILMAZ ve çizimde
    ``NOT AVAILABLE`` görünür — kamara kapağının kalınlığı ya da cidarın katı
    enjektör plakası yerine geçemez.
    """
    md = motor_data if isinstance(motor_data, dict) else {}
    panel = md.get('injector_results') or {}
    if not isinstance(panel, dict):
        panel = {}
    structural = panel.get('plate_structural')
    structural = structural if isinstance(structural, dict) else {}

    t_mm = _real_scalar(structural.get('plate_thickness_mm'))
    d_mm = _real_scalar(structural.get('plate_diameter_mm'))
    mass_kg = _real_scalar(structural.get('plate_mass_kg'))
    material = structural.get('material')
    source = ('injector plate analysis '
              '(injector_results.plate_structural)')
    if t_mm is None:
        t_mm = _real_scalar(panel.get('plate_thickness'))
        if t_mm is not None:
            source = 'injector panel (injector_results.plate_thickness, mm)'
            mass_kg = None
    if t_mm is None:
        inj = md.get('injector_design') or {}
        if isinstance(inj, dict):
            t_mm = _real_scalar(inj.get('plate_thickness_mm'))
            if t_mm is not None:
                source = 'motor result injector_design.plate_thickness_mm'
                mass_kg = None
    if t_mm is None:
        return {'thickness_m': None, 'radius_m': None, 'mass_kg': None,
                'material': None,
                'source': ('injector_plate_thickness_not_available: this '
                           'analysis run publishes no injector plate '
                           'thickness (injector_results.plate_structural '
                           '.plate_thickness_mm / injector_results'
                           '.plate_thickness); no plate thickness is invented')}

    if d_mm is None:
        bore_m = _real_scalar(chamber_diameter_m)
        if bore_m is None:
            bore_m = _real_scalar(md.get('chamber_diameter'))
        d_mm = bore_m * 1000.0 if bore_m is not None else None
    return {'thickness_m': t_mm / 1000.0,
            'radius_m': (d_mm / 2000.0) if d_mm is not None else None,
            'mass_kg': mass_kg, 'material': material, 'source': source}


def _chamber_material(motor_data):
    """Kamara malzemesi — yapısal analizde SEÇİLEN kayıt.

    Döner: (materials_db anahtarı|None, görünen_ad|None, yoğunluk|None)
    Üç motor tipinin üç ayrı şeması ``CHAMBER_MATERIAL_SCHEMAS``ta tek
    noktada yazılıdır (ÖH D15 / defter P9B1-14).
    """
    key, name, density, _src = _chamber_material_resolved(motor_data)
    return key, name, density


def _chamber_material_resolved(motor_data):
    """``_chamber_material`` + yoğunluğun NEREDEN geldiği (künye metni).

    Döner: (anahtar|None, ad|None, yoğunluk|None, yoğunluk_künyesi)
    Yoğunluk çözülemezse ``density`` None döner ve künye bunu söyler —
    çağıran sessiz bir yedeğe düşmek yerine yedeği BEYAN etmek zorundadır.
    """
    md = motor_data or {}
    struct = md.get('structural_analysis') or {}
    props = struct.get('material_properties') or {}

    key = None
    key_src = None
    for block_name, candidates in CHAMBER_MATERIAL_SCHEMAS:
        block = struct.get(block_name)
        if not isinstance(block, dict):
            continue
        for cand in candidates:
            value = block.get(cand)
            if isinstance(value, str) and value.strip():
                key, key_src = value.strip(), f'{block_name}.{cand}'
                break
        if key:
            break
    if not key:
        top = md.get('chamber_material') or md.get('case_material')
        if isinstance(top, str) and top.strip():
            key, key_src = top.strip(), 'motor result chamber_material'

    name = props.get('name')
    density = _real_scalar(props.get('density'))
    density_src = ('structural_analysis.material_properties.density'
                   if density is not None else None)
    if key and not (name and density):
        try:
            rec = get_material(str(key))
            name = name or rec.get('name')
            if density is None:
                density = _real_scalar(rec.get('density'))
                if density is not None:
                    density_src = (f'materials_db["{key}"] selected by the '
                                   f'solver ({key_src})')
        except Exception:
            pass
    if density is None:
        density_src = ('NOT RESOLVED: this analysis run names no chamber '
                       'material that materials_db knows'
                       + (f' (solver wrote {key!r} at {key_src})' if key
                          else ''))
    return key, name, density, density_src


def _drawable_length_m(motor_data, field, human, scale=1.0):
    """Çizilebilir bir uzunluk okur; yoksa ADIYLA REDDEDER (fail-closed).

    ÖH D22 / defter OH-D19-03 (Fable-D17 hüküm-7 bulgusu). OH-D16-03
    ``generate_3d_motor_assembly``ın ANA yolundaki uydurma çap
    varsayılanlarını (``motor_data.get('chamber_diameter', 0.1)`` vb.)
    söktü, ama aynı kalıp YARDIMCI üreticilerde ayakta kaldı.

    ÖLÇÜLDÜ (taban ``b84b10a``, ``once.json`` bölümü OH-D19-03) — hepsine
    BOŞ sözlük (``{}``) verildi:

        _add_fallback_3d_motor          -> 2 iz çizdi (Chamber, ...)
        _create_fallback_visualization  -> 3 iz çizdi (Chamber/Nozzle Outline)
        _add_cross_section_view         -> 3 iz çizdi (Chamber, Nozzle, Throat)
        _generate_technical_drawings    -> boğaz 20,0 mm / çıkış 40,0 mm
        generate_liquid_motor_cad       -> Ø100 x 200 mm kamara, boğaz Ø50 mm,
                                           çıkış Ø80 mm, lüle 150 mm

    Beşinin de çizdiği motor KULLANICININ MOTORU DEĞİLDİ; kaynakta kalıbın
    22 örneği sayıldı. Kural ana yolla AYNIdır: yayımlanmamış ölçü
    uydurulmaz, adıyla reddedilir; bant/eşik icat edilmez, yalnız "sonlu ve
    pozitif olarak yayımlanmış mı" sorulur (``_real_scalar``, deponun tek
    tanım noktası).

    ``scale``: kaydın kendi birimi metre değilse (``DetailedCADGenerator``
    milimetre okur) uygulanan çarpan. Dönüş her zaman ``scale`` uygulanmış
    değerdir; okuma kuralı değişmez.
    """
    value = _real_scalar((motor_data or {}).get(field))
    if value is None:
        raise ValueError(
            f'{field}_not_available: this analysis run publishes no {human} '
            f'({field}) as a finite positive number; the previous code drew '
            'a default body instead, so the drawing was not the analysed '
            'motor. No substitute dimension is invented.')
    return value * scale


class MotorCADDesigner:
    """Professional 3D CAD design for hybrid rocket motors

    ÖH D24 / P9B1-29 — ``__init__`` KALDIRILDI (kurucu gereksizdi).
    Eski kurucu iki sözlük kuruyordu:

    * ``self.materials_db`` — 8 malzeme kaydı, her biri ``_cad_material``
      üzerinden merkezi ``hrma/data/materials_db.py``'ye giden bir arama.
      ÖLÇÜLDÜ (taban 88a29d3, ``once.json`` M4, AST taraması): ürün kodunda
      **0 okuyucu**. Yani her ``MotorCADDesigner()`` kurulumu — ihraç
      uçlarının her isteğinde olur — hiç okunmayan bir sözlük için sekiz
      ``get_material`` çağrısı yapıyordu.
    * ``self.standard_dimensions`` — H..M motor sınıfı ölçüleri; ürün
      kodunda **0 okuyucu**. Üstelik bu tablo, ölçü çözülemediğinde
      dönülebilecek bir "standart" yedek gibi duruyordu; ihraç katmanının
      bugünkü sözleşmesi ise fail-closed'dır (ölçü yoksa parça çizilmez),
      dolayısıyla tablo yalnız yanlış bir davranışa davetiyeydi.

    Tabloyu kuran ``_cad_material`` yardımcısı da silindi: tablo gidince onun
    da ürün okuyucusu kalmamıştı (yalnız-test sembol). Malzeme bilgisi
    gerektiğinde tek doğruluk kaynağı DOĞRUDAN okunur —
    ``_generate_material_specifications`` zaten ``hrma.data.materials_db
    .get_material``a gider ve künyesini (``source``) oradan taşır.
    """

    def generate_3d_motor_assembly(self, motor_data: Dict) -> Dict:
        """Generate complete 3D motor assembly with all components"""

        # Yerel kopyada çalış: aşağıdaki motor_data.update(...) çağrıcının
        # motor_results sözlüğünü YERİNDE değiştiriyordu (chamber_length'i
        # kaba L* kuralıyla ezip /calculate yanıtını bozuyordu)
        #
        # Faz 5B / H4-2: kopya artık aynı zamanda BİRİM olarak normalize
        # edilir. Ölçüldü (HEAD 9d3728e): ham ``/calculate_solid`` yanıtı
        # verilince STL zarfı 126 313 × 126 313 × 174 992 mm çıkıyordu
        # (gerçek 126.31 × 126.31 × 782.68 mm) — çünkü buradaki her okuma
        # girdiyi koşulsuz METRE kabul ediyordu, katı rotası ise mm döndürür.
        from hrma.export.motor_geometry import (
            normalise_export_geometry, resolve_grain_m, unearned_unit_fields)
        _ham_girdi = motor_data if isinstance(motor_data, dict) else {}
        motor_data, _unit_report = normalise_export_geometry(motor_data)
        # ÖH D16 birleşme etkileşimi (1 Eylül 2026): normalize katmanı,
        # birimi kazanılamayan alanı kopyadan DÜŞÜRÜR (P16B4-02, fail-closed
        # ve doğru). Ama düşürülen alanın YOKLUĞU, alanın hiç verilmemiş
        # olmasıyla aynı şeye benziyor; aşağıdaki okumalar o farkı göremezse
        # kullanıcının bant dışı girdisi sessizce bir TÜRETMEYLE değiştirilir
        # (P9B1-05'in kusuru geri gelir). Ham girdi ve düşürülen alan listesi
        # bu yüzden saklanır — değer değil, VARLIK bilgisi taşınır.
        _kazanilmamis_birim = unearned_unit_fields(_unit_report)
        grain_geo, grain_reason = resolve_grain_m(motor_data)

        try:
            # ---- ÖH D17 / OH-D16-03 (+ P9B1-16 daraltılmış başlığı) ----
            # UYDURMA ÇAP VARSAYILANLARI KALDIRILDI. Eskiden burada
            # ``motor_data.get('chamber_diameter', 0.1)`` /
            # ``get('throat_diameter', 0.02)`` / ``get('exit_diameter', 0.04)``
            # duruyordu. ÖLÇÜLDÜ (taban ``2426b4d``): yalnız
            # ``{'chamber_length': 0.3}`` içeren bir gövde
            # ``POST /api/export-cad`` ucundan HTTP **200 'success'** ve ÜÇ
            # indirilebilir STL alıyordu; çizilen katı Ø100 mm'lik (cidarla
            # Ø109 mm) UYDURMA bir kamaraydı. Kardeş ``/api/export-stl`` aynı
            # gövdeyi reddediyordu, yani ürünün iki ucu aynı girdiye zıt
            # hüküm veriyordu.
            #
            # Kural, kamara boyunun P9B1-05'te aldığı kuralla AYNIdır:
            # yayımlanmamış ölçü UYDURULMAZ, adıyla reddedilir. Bant/eşik
            # İCAT EDİLMEZ — yalnız "sonlu ve pozitif olarak yayımlanmış mı"
            # sorulur (``_real_scalar``, deponun tek tanım noktası).
            def _yayimlanmis_olcu(_ad, _insan):
                _v = _real_scalar(motor_data.get(_ad))
                if _v is not None:
                    return _v
                # (a) Alan VARDI ama birimi kazanılamadı: normalize katmanı
                #     onu kopyadan düşürdü (P16B4-02). Bu "hiç verilmedi"
                #     DEĞİLDİR ve gerekçesi de aynı olamaz.
                _etiket = _kazanilmamis_birim.get(_ad)
                if _etiket is not None:
                    raise ValueError(
                        f'{_ad}_unit_unearned: {_insan} '
                        f'{_ham_girdi.get(_ad)!r} could not be read as a '
                        f'drawable length ({_etiket}: neither its metre nor '
                        'its millimetre reading lands in the validated '
                        'band). Declare length_units to resolve it; no '
                        'substitute diameter is invented.')
                # (b) Alan hiç yayımlanmamış (ya da 0 / negatif / sayı değil).
                raise ValueError(
                    f'{_ad}_not_available: this analysis run publishes no '
                    f'{_insan} ({_ad}) as a finite positive number; the '
                    'previous code drew a default body instead, so the '
                    'exported solid was not the analysed motor. No '
                    'substitute diameter is invented.')

            chamber_diameter = _yayimlanmis_olcu(
                'chamber_diameter', 'chamber diameter')      # m
            throat_diameter = _yayimlanmis_olcu(
                'throat_diameter', 'throat diameter')        # m
            exit_diameter = _yayimlanmis_olcu(
                'exit_diameter', 'nozzle exit diameter')     # m

            print(f"CAD Debug - Chamber: {chamber_diameter}, Throat: {throat_diameter}, Exit: {exit_diameter}")

            # Check for design configuration
            design_config = motor_data.get('design_config', {})
            motor_config = design_config.get('motor', {})
            injector_config = design_config.get('injector', {})

            # ---- GERÇEK ÇÖZÜCÜ GEOMETRİSİ ----
            # Önce motor_results'taki hesaplanmış değerler; anahtar yoksa eski
            # kaba kurallara düşülür. (Eski davranış: port=0.4·D, L=f(L*) gibi
            # kurallar çözücü çıktısını YOK SAYIYORDU — STL çıktısı analizle
            # tutarsızdı.)
            def _real(key, lo, hi):
                """Bandın İÇİNDE (uçlar DÂHİL) sonlu sayı; yoksa ``None``.

                ÖH D26 / OH-Z5-12: kapı ``lo < v < hi`` (keskin) idi, kardeş
                ret iletisi ise KAPALI aralık yazıyordu (``[0.02, 5] m``).
                ÖLÇÜLDÜ (taban 7751531, ``once.json`` →
                ``OH-Z5-12.sinirlar.tam_MAX_5_0``): ``chamber_length = 5.0 m``
                girdisi *"outside the band this exporter can draw
                [0.02, 5] m"* diyen bir iletiyle REDDEDİLİYORDU — ileti o
                sayıyı bandın İÇİNDE gösteriyordu. Kapı ile ileti artık aynı
                şeyi söyler: bant kapalıdır.
                """
                v = finite_number(motor_data.get(key))
                return v if (v is not None and lo <= v <= hi) else None

            def _girdi_kunyesi(alan):
                """Ret iletisi için KULLANICININ YAZDIĞI değerin künyesi.

                ÖH D26 / OH-Z5-12. Ret iletisi ÇEVRİLMİŞ sayıyı basıyordu:
                ÖLÇÜLDÜ (taban 7751531, ``once.json`` →
                ``OH-Z5-12.birim_sezgisi.5_5_mm_beyanli``) kullanıcı
                ``chamber_length = 5.5`` + ``length_units = 'mm'`` yazarken
                ileti *"chamber length 0.0055 m is outside the band"*
                diyordu; kullanıcının yazdığı **5.5** iletide HİÇ geçmiyordu
                ve hangi sayıyı düzelteceğini bilemiyordu. Künye artık
                yazılanı, beyan edilen birimi ve (çevrildiyse) okunan metre
                değerini birlikte taşır.
                """
                ham = _ham_girdi.get(alan, '<not published>')
                metin = f'{ham!r} as published'
                beyan = _ham_girdi.get('length_units')
                if beyan:
                    metin += f' (length_units={beyan!r})'
                okunan = motor_data.get(alan)
                try:
                    if (okunan is not None
                            and float(okunan) != float(ham)):
                        metin += f', read as {float(okunan):g} m'
                except (TypeError, ValueError):
                    pass
                return metin

            # ÖH Z5S (defter P9B1-05): karakteristik boy VARSAYILANI kaldırıldı.
            # ``motor_data.get('l_star', 1.0)`` kalıbı, sonuç L* yayımlamasa
            # bile 1,0 m'lik uydurma bir L* ile kamara boyu türetiyordu — yani
            # "türetilmiş" görünen sayı aslında uydurma bir sabitin sonucuydu.
            # Ölçüldü (hibrit 5 kN, chamber_length alanı kaldırılmış): sonuçta
            # l_star YOK, buna rağmen 82,3 mm'lik bir kamara "L* türetmesi"
            # diye çiziliyordu.
            l_star = motor_data.get('l_star')

            # ÖH Z5S (defter P9B1-05): kamara boyu artık SESSİZCE
            # DEĞİŞTİRİLMEZ. Üç yol da (doğrudan okuma / L* türetmesi /
            # kullanıcı override'ı) aynı kabul bandına tabidir ve bandın
            # dışına düşen boy kelepçelenmek yerine ADIYLA reddedilir.
            chamber_length = _real('chamber_length', CHAMBER_LENGTH_MIN_M,
                                   CHAMBER_LENGTH_MAX_M)
            chamber_length_source = 'solver/user chamber_length'
            if chamber_length is None:
                given = _real_scalar(motor_data.get('chamber_length'))
                if given is not None:
                    # Sonlu-pozitif ama bandın DIŞINDA: bu bir girdi hatasıdır,
                    # yerine 300 mm uydurmak kullanıcının motorunu sessizce
                    # değiştirmek olurdu (ölçüldü: 5 m, 15 mm ve "alan yok"
                    # üçü de 300 mm çiziyordu).
                    raise ValueError(
                        f'chamber_length_out_of_range: chamber length '
                        f'{_girdi_kunyesi("chamber_length")} is outside the '
                        f'band this exporter can draw '
                        f'[{CHAMBER_LENGTH_MIN_M:g}, '
                        f'{CHAMBER_LENGTH_MAX_M:g}] m (both bounds '
                        'included); no substitute length is invented')
                # ÖH D16 birleşme etkileşimi — ALAN VARDI AMA BİRİMİ
                # KAZANILMADI. Bu dal "boy hiç yayımlanmamış" dalıdır ve
                # buraya yalnız GERÇEKTEN alan yokken girilmelidir. Normalize
                # katmanı birimi kazanılamayan alanı düşürdüğü için (ÖLÇÜLDÜ:
                # chamber_length = 0,015 ve 0,001, ikisi de 'out_of_band')
                # kullanıcının girdisi buraya "alan yok" kılığında geliyordu
                # ve L* türetmesi ikisini de 62,5 mm çiziyordu — girdi ile
                # girdisizlik ayırt edilemez hâle gelmişti. Değer hâlâ
                # YAYIMLANMAZ (birim kazanılmadı); reddedilir.
                _birim_etiketi = _kazanilmamis_birim.get('chamber_length')
                if _birim_etiketi is not None:
                    raise ValueError(
                        f'chamber_length_out_of_range: chamber length '
                        f'{_girdi_kunyesi("chamber_length")} could not be '
                        f'read as a drawable length ({_birim_etiketi}: '
                        'neither its metre nor its millimetre reading lands '
                        'in the validated band), so its unit is unearned. '
                        'Declare length_units to resolve it; the value is '
                        'neither reinterpreted nor replaced by a length '
                        'derived from L*.')
                # ---- ÖH D26 / P9B1-25 ----
                # ALAN YAYIMLANMIŞ AMA ÇİZİLEBİLİR BİR BOY DEĞİL. Negatif,
                # sıfır, NaN/sonsuz ya da sayı olmayan bir boy buraya
                # "alan hiç yok" kılığında geliyordu ve L* türetmesine
                # düşüyordu. ÖLÇÜLDÜ (taban 7751531, ``once.json`` →
                # ``P9B1-25``, l_star = 1,0 m yayımlayan gövde):
                #
                #     chamber_length = -0.5   -> hata YOK, boy 229,3818 mm
                #     chamber_length = -0.25  -> hata YOK, boy 229,3818 mm
                #     chamber_length =  0.0   -> hata YOK, boy 229,3818 mm
                #     chamber_length =  NaN   -> hata YOK, boy 229,3818 mm
                #     chamber_length = 'abc'  -> hata YOK, boy 229,3818 mm
                #     alan HİÇ YOK            -> hata YOK, boy 229,3818 mm
                #
                # yani ALTI yol da BİT-AYNI katıyı çiziyordu (max çap 109,0
                # mm, künye "derived from the characteristic length"):
                # kullanıcının GİRDİĞİ boy ile GİRDİSİZLİK ayırt edilemezdi
                # ve reddin izi hiçbir künyede yoktu. P9B1-05'in kamara boyu
                # için koyduğu kural burada da geçerlidir: yayımlanmış ama
                # kullanılamaz ölçü SESSİZCE ATILMAZ, adıyla reddedilir.
                #
                # Açıkça ``None`` yazılmış alan "yayımlanmadı" demektir
                # (çözücüler alanı böyle boş bırakır) ve türetmeye düşer.
                _ham_boy = _ham_girdi.get('chamber_length',
                                          motor_data.get('chamber_length'))
                if 'chamber_length' in _ham_girdi and _ham_boy is not None:
                    raise ValueError(
                        'chamber_length_published_but_not_drawable: chamber '
                        f'length {_girdi_kunyesi("chamber_length")} is not a '
                        'finite positive length, so it cannot be drawn. The '
                        'previous code discarded it without saying so and '
                        'drew a body derived from the characteristic length '
                        '(L*) instead, which made a rejected input '
                        'indistinguishable from no input at all. No '
                        'substitute length is invented.')

                # Boy hiç yayımlanmamış: L* bağıntısından TÜRETİLİR
                # (V_c = L* x A_t  ve  V_c = A_c x L  =>  L = L* A_t / A_c).
                l_star_real = _real_scalar(l_star)
                if l_star_real is None:
                    raise ValueError(
                        'chamber_length_not_available: this analysis run '
                        'publishes neither chamber_length nor a characteristic '
                        'length (l_star) to derive it from; no chamber length '
                        'is invented')
                throat_area = np.pi * (throat_diameter / 2) ** 2
                chamber_length = ((l_star_real * throat_area)
                                  / (np.pi * (chamber_diameter / 2) ** 2))
                chamber_length_source = (
                    f'derived from the characteristic length (L* = '
                    f'{l_star_real:g} m): L = L* x A_throat / A_chamber')
                if not (np.isfinite(chamber_length)
                        and CHAMBER_LENGTH_MIN_M <= chamber_length
                        <= CHAMBER_LENGTH_MAX_M):
                    raise ValueError(
                        f'chamber_length_out_of_range: the length derived from '
                        f'L* is {chamber_length:g} m, outside the band this '
                        f'exporter can draw [{CHAMBER_LENGTH_MIN_M:g}, '
                        f'{CHAMBER_LENGTH_MAX_M:g}] m (both bounds '
                        'included); the previous code clamped it to '
                        '[0.3, 2.0] m without saying so')
            if motor_config.get('chamber_length_override'):
                override_m = _real_scalar(
                    motor_config['chamber_length_override'])
                override_m = (override_m / 1000.0) if override_m is not None \
                    else None
                if override_m is None or not (
                        CHAMBER_LENGTH_MIN_M <= override_m
                        <= CHAMBER_LENGTH_MAX_M):
                    raise ValueError(
                        'chamber_length_override_out_of_range: '
                        f'{motor_config["chamber_length_override"]!r} mm is not '
                        'a drawable chamber length in '
                        f'[{CHAMBER_LENGTH_MIN_M * 1000.0:g}, '
                        f'{CHAMBER_LENGTH_MAX_M * 1000.0:g}] mm (both '
                        'bounds included)')
                chamber_length = override_m
                chamber_length_source = (
                    'user override (design_config.motor.chamber_length_override)')

            # Nozul konturu + eti: STEP ve kütle dökümüyle TEK kaynak
            # (``nozzle_wall_profile``, V301 bilinen C1). Profil metre
            # uzayında okunur — trimesh katısı metre kurulur.
            noz_profile = nozzle_wall_profile(motor_data, unit='m')
            noz_meta = noz_profile['meta']
            nozzle_length = noz_meta['z_exit'] / 1000.0

            # Duvar kalınlıkları
            # v2.6.26 (Y5): kullanıcının cidarı ÇİZİLİR. Eski kod hem öneriye
            # sabitliydi hem de 0.12·D üst sınırıyla kırpıyordu; kırpma
            # kullanıcının tasarımını sessizce değiştirdiği için kaldırıldı
            # (çizim sözlüğü, kütle dökümü ve STL artık AYNI kalınlığı taşır).
            wall_case, _wall_src = _chamber_wall_effective_m(motor_data,
                                                             chamber_diameter)
            # TEK KAYNAK (ÖH D15 / P9B1-18): lüle cidarı üç yerde ayrı ayrı
            # yazılıydı (burada, kütle dökümünde ve ``step_export``te). Et
            # ``_nozzle_wall_design``de yaşar; dış kontur kuralı (V301
            # bilinen C1) ``nozzle_wall_profile``de — mesh, kütle ve STEP
            # katısı aynı profili kullanmak zorundadır.

            # Grain: gerçek port + gerçek boy. H4-1: yoksa GRAIN ÇİZİLMEZ.
            # Eski kod portu ``chamber_diameter * 0.4``, boyu
            # ``chamber_length - 0.05`` ile uyduruyordu; sıvı çift yakıtlı
            # motorda grain fiziksel olarak yokken STL/3B görünümde
            # Ø39.7 mm portlu bir katı yakıt bloğu görünüyordu (ölçüldü:
            # liquid fuel_grain.stl 95.22 × 95.22 × 47.96 mm).
            #
            # ÖH Z5S (defter P9B1-06): kamaradan UZUN tane sessizce
            # ``0.98 x kamara boyu``na kırpılıyordu. Ölçüldü: 3.387 mm'lik tane
            # 980 mm çiziliyordu — kullanıcı grain'inin çizildiğini sanıyor,
            # STL'de bambaşka bir parça duruyordu. Kırpma iki yönden de
            # yanlıştı: (a) tane kamaraya sığmıyorsa bu bir TASARIM ÇELİŞKİSİDİR
            # ve gizlenmemelidir; (b) tane sığıyorsa bile %2'si sessizce
            # kesiliyordu. Artık tane ya OLDUĞU GİBİ çizilir ya HİÇ çizilmez ve
            # sebebi adlandırılır.
            grain_not_drawn_reason = grain_reason
            if grain_geo is not None:
                if grain_geo['length'] > chamber_length * (1.0 + 1e-9):
                    grain_not_drawn_reason = (
                        f'grain_longer_than_chamber: the grain is '
                        f'{grain_geo["length"] * 1000.0:.1f} mm long but the '
                        f'chamber is only {chamber_length * 1000.0:.1f} mm; '
                        'the grain is NOT drawn because trimming it would '
                        'silently show a part that this analysis never '
                        f'produced (grain source: {grain_geo["source"]})')
                    print(f'CAD Debug - {grain_not_drawn_reason}')
                    grain_geo = None
            # ÖH D15 (defter P9B1-04): tanenin DIŞ çapı çözücüden okunur.
            # Eski kod ``kamara_yarıçapı - liner`` çiziyordu ve ``liner``
            # hiçbir hesaptan gelmiyordu; hacmin %9-12'si sessizce siliniyordu.
            grain_r_outer, grain_r_outer_source = _grain_outer_radius_m(
                motor_data)
            if grain_geo is not None and grain_r_outer is None:
                grain_not_drawn_reason = (
                    'grain_outer_diameter_not_available: ' +
                    grain_r_outer_source +
                    '; the grain is NOT drawn because the previous code '
                    'shrank it by an invented liner thickness instead')
                print(f'CAD Debug - {grain_not_drawn_reason}')
                grain_geo = None
            if grain_geo is not None:
                port_diameter = grain_geo['port_initial']
                grain_length = grain_geo['length']
            else:
                port_diameter = None
                grain_length = None

            # Enjektör: TEK doğruluk kaynağı (_injector_spec) — teknik çizim,
            # PDF, STEP/DXF ve bu mesh AYNI enjektörü anlatmalı.
            # v2.6.26 (K2): burası `injector_design`'ı DOĞRUDAN okuyordu;
            # çizim sözlüğü ise panel sonucunu kullanıyordu. Ölçüldü: aynı
            # koşuda mesh 11 delik x 2,457 mm delerken çizim 125 delik x
            # 0,957 mm yazıyordu. STL'i açan kişi çizimdeki parçayı GÖRMÜYORDU.
            inj_spec = _injector_spec(motor_data)
            injector_orifices_real = inj_spec['n_orifices']
            inj_circuits = list(inj_spec['circuits'])
            if not injector_orifices_real and injector_config.get('n_holes_override'):
                injector_orifices_real = int(injector_config['n_holes_override'])
            # Gerçek (kırpılmamış) sayı korunur: MESH kararlılığı için delik
            # sayısı sınırlanır ama teknik çizim/spesifikasyon çıktısı gerçek
            # sayıyı yazmalıdır (2026-07-19 denetimi: çözücü 41 orifis derken
            # çizimde 16 görünüyordu).
            if injector_orifices_real:
                # Kırpma kuralı TEK yerde: teknik çizim aynı yardımcıyı okur
                # (ÖH D19, P9B1-23) — iki yerde iki formül yazılmaz.
                injector_orifices = _mesh_orifice_count(injector_orifices_real)
            else:
                # Hiçbir çözücü delik üretmedi -> DELİK AÇILMAZ. Eski kod 8
                # delik uydurup çapını akıştan türetiyordu; kullanıcı bunun
                # hesaplanmış bir desen olduğunu sanıyordu (v2.6.26 denetimi).
                injector_orifices = 0
            ori_mm = inj_spec['orifice_diameter_mm']
            # Çap yalnız delik sayısıyla BİRLİKTE anlamlıdır; biri yoksa
            # diğeri de çizilmez.
            orifice_diameter = (max(0.0005, min(0.01, ori_mm / 1000.0))
                                if (ori_mm and injector_orifices) else 0.0)
            if not orifice_diameter:
                injector_orifices = 0
            # ÖH D33-2 / defter OH-D32-04 — DEVRE BAŞINA DELİK PLANI.
            # Sıvı motorda oksitleyici ve yakıt devrelerinin ÇAPLARI
            # farklıdır (ölçüldü: Ø2,4920 / Ø2,3217 mm); tek bir (n, d)
            # çiftine indirgemek ya bir devreyi gizler ya çap uydururdu.
            # Plaka artık STEP ile AYNI planı deler.
            if not inj_circuits and injector_orifices and orifice_diameter:
                # Devre adı yok ama sayı/çap var (``n_holes_override`` yolu):
                # tek adsız devre olarak çizilir.
                inj_circuits = [{'name': 'unidentified',
                                 'n': int(injector_orifices_real or 0),
                                 'd_mm': orifice_diameter * 1000.0}]
            mesh_circuits = _mesh_orifice_plan(inj_circuits)

            # Türetilen boyutları KOPYAYA yaz (çağıranın dict'i korunur)
            motor_data.update({
                'chamber_length': chamber_length,
                # Çizilen boyun NEREDEN geldiği sayının yanında taşınır
                # (ÖH Z5S / P9B1-05): okuyucu bunun çözücünün boyu mu, L*
                # türetmesi mi, yoksa kendi override'ı mı olduğunu görmelidir.
                'chamber_length_source': chamber_length_source,
                'grain_not_drawn_reason': grain_not_drawn_reason,
                'nozzle_length': nozzle_length,
                'port_diameter': port_diameter,
                'injector_orifices': injector_orifices,          # MESH için kırpılmış
                'injector_orifices_real': injector_orifices_real,  # gerçek sayı
                'orifice_diameter': orifice_diameter,
                # Devre başına plan (ÖH D33-2 / OH-D32-04); mesh bunu okur.
                'injector_mesh_circuits': mesh_circuits,
                'design_config': design_config
            })

            # ---- Bileşen katıları (kapalı profil revolve — boolean'sız, watertight) ----
            print("CAD Debug - Creating chamber mesh...")
            # Kapak STEP ile AYNI çözümleyiciden (P15B4-10): yapısal kapak
            # analizi varsa onun düz-kapak kalınlığı, yoksa adıyla beyan
            # edilen üreteç varsayımı. İki üreteç ayrı formül yazarsa aynı
            # motorun STL'i ile STEP'i farklı boyda kamara üretir.
            cap_design = _front_cap_design(
                motor_data, wall_mm=wall_case * 1000.0,
                bore_radius_mm=chamber_diameter * 1000.0 / 2.0)
            cap_t = ((cap_design['thickness_mm'] or 0.0) / 1000.0)
            chamber_mesh = self._chamber_solid(chamber_diameter, chamber_length, wall_case, cap_t)

            print("CAD Debug - Creating nozzle mesh...")
            nozzle_mesh = self._nozzle_solid(noz_profile)

            # ÖH D15 (defter P9B1-12): enjektör artık KOŞULSUZ üretilmiyor.
            # Çözücü enjektör yayımlamadıysa (katı motor) plaka çizilmez,
            # tartılmaz ve STL'e yazılmaz — grain kapısıyla simetrik.
            injector_present, injector_reason = _injector_evidence(motor_data)
            inj_plate = _injector_plate_design(motor_data, chamber_diameter)
            # V301 bilinen C2: pintle seçiliyse KANONİK geometri çizilir
            # (STEP ile TEK çözümleyici ``pintle_cad_geometry``); yoksa ya da
            # çizilemiyorsa adlı ret (``PintleCADError``) yukarı taşınır —
            # düz plaka + eşdeğer delik planına sessiz dönüş YOK. Yüz
            # plakası kalınlığı yayımlanmamışsa (pintle çözümleri
            # yayımlamaz) plaka çizilmez, direk ve uç delikleri çizilir.
            pintle_geo = (pintle_cad_geometry(motor_data, chamber_diameter)
                          if injector_present else None)
            if pintle_geo is not None and pintle_geo['not_drawn_reason']:
                injector_present = False
                injector_reason = pintle_geo['not_drawn_reason']
                pintle_geo = None
            if (injector_present and pintle_geo is None
                    and not inj_plate['thickness_m']):
                # ÖH D15 (defter P9B1-13): enjektör VAR ama plaka kalınlığı
                # yayımlanmamış -> plaka UYDURULMAZ (eski kod 30 mm çiziyordu).
                injector_present = False
                injector_reason = inj_plate['source']
            motor_data['injector_not_drawn_reason'] = (
                None if injector_present else injector_reason)
            motor_data['injector_source'] = (
                injector_reason if injector_present else None)
            if pintle_geo is not None:
                print("CAD Debug - Creating pintle injector mesh...")
                injector_mesh = self._create_pintle_injector(pintle_geo)
            elif injector_present:
                print("CAD Debug - Creating injector mesh...")
                injector_mesh = self._create_injector_head(chamber_diameter,
                                                           motor_data)
            else:
                print(f'CAD Debug - {injector_reason}')
                injector_mesh = None

            if grain_geo is not None:
                print("CAD Debug - Creating fuel grain mesh...")
                # ÖH V3 CAD A1 · H3 — tanenin yeri ÇÖZÜCÜ yayımlıyorsa
                # ondan (STEP ve DXF ile TEK fonksiyon). Ham girdi okunur:
                # normalize kopya ön/arka oda alanlarını çevirmez.
                # ÖH V3 CAD A2 · H7 — yayımlamıyorsa (katı) da AYNI
                # fonksiyon (``grain_axial_layout_mm``) ve AYNI yığın planı
                # (``grain_stack_plan``). ÖLÇÜLDÜ (7 Eki CAD kontrolü, örnek
                # katı BATES): bu dal eskiden ``0,35 x max(0,004, L - L_tane)``
                # satır içi kopyasıyla TEK parça 360 mm'yi 36,4 mm'ye
                # koyuyordu; aynı isteğin STEP'i 3 x 120 mm segmenti 2 mm
                # aralıkla 35,0 mm'den çiziyordu.
                _yigin = grain_stack_plan(motor_data, grain_length * 1000.0)
                _yer = grain_axial_layout_mm(
                    _ham_girdi, chamber_length * 1000.0, _yigin['stack_mm'])
                zg0 = _yer['front_mm'] / 1000.0
                # Bitişik segmentler TEK kabuk yazılır: dokunan iki kabuk
                # STL'de birleşince köşe noktaları ortaklaşır ve dosya
                # manifold olmaktan çıkar (ölçüldü: 3 bitişik segment -> 192
                # kenar ikiden fazla yüze ait). Birleşim hacmi STEP'in
                # segment katılarının toplamıdır; boşluk varsa (katı BATES)
                # her segment kendi kapalı kabuğudur.
                if _yigin['n'] > 1 and _yigin['gap_mm'] > 0.0:
                    _seg_m = _yigin['segment_mm'] / 1000.0
                    _gap_m = _yigin['gap_mm'] / 1000.0
                    fuel_grain_mesh = trimesh.util.concatenate([
                        self._grain_solid(
                            grain_r_outer, port_diameter / 2,
                            zg0 + i * (_seg_m + _gap_m),
                            zg0 + i * (_seg_m + _gap_m) + _seg_m)
                        for i in range(_yigin['n'])])
                else:
                    fuel_grain_mesh = self._grain_solid(
                        grain_r_outer, port_diameter / 2, zg0,
                        zg0 + _yigin['stack_mm'] / 1000.0)
            else:
                print("CAD Debug - no grain in the result; grain mesh skipped")
                fuel_grain_mesh = None

            # ---- Yerleşim: z=0 kapak iç yüzü, kamara [0, L], nozul [L, L+Ln] ----
            assembly_meshes = []

            chamber_mesh.visual.face_colors = [200, 200, 200, 100]
            assembly_meshes.append(('Chamber', chamber_mesh))

            nozzle_mesh.apply_translation([0, 0, chamber_length])
            nozzle_mesh.visual.face_colors = [50, 50, 50, 255]
            assembly_meshes.append(('Nozzle', nozzle_mesh))

            # ÖH D24 / P9B1-27 — PLAKANIN YERİ ARTIK GEOMETRİDEN GELİYOR VE
            # TANEYLE ÇAKIŞMA SESSİZ GEÇİLMİYOR.
            #
            # ÖLÇÜLDÜ (taban 88a29d3, ``once.json`` M3, katı koşum + 30 mm
            # plaka): plaka [6,00; 36,00] mm, tane [35,00; 485,32] mm ->
            # eksenel örtüşme **1,0000 mm**, iki katının gerçek kesişim
            # hacmi **1.810,30 mm³**. Montaj bunu HİÇBİR yerde söylemiyordu
            # (``error`` yok, çakışma alanı yok): STL'i açan imalatçı
            # birbirinin içine geçmiş iki parça görüyordu.
            #
            # Kök İKİ parçalıydı:
            #  (1) Plakanın z ofseti ``0,006 + 0,015`` SABİT LİTERALİYDİ ve
            #      hiçbir geometriden türemiyordu. Bu satırın hemen üstündeki
            #      yerleşim sözleşmesi "z=0 kapak İÇ YÜZÜ" der; plakanın
            #      doğru yeri kapak iç yüzüne DAYALI, yani [0, t]'dir. Sabit
            #      21 mm merkez, kalınlık büyüdükçe plakayı tanenin içine
            #      itiyordu (t > 28 mm'de kaçınılmaz çakışma).
            #  (2) Yerleşimden sonra hiçbir girişim (interference) denetimi
            #      yoktu.
            #
            # Artık plaka kapak iç yüzüne oturur ve tane ile eksenel
            # girişim ADIYLA reddedilir (fail-closed): çakışan bir montaj
            # imal edilemez, dolayısıyla yayımlanmaz. Beyan yeterli değildir.
            if injector_mesh is not None and pintle_geo is not None:
                # V301 bilinen C2: pintle mesh'i ZATEN montaj çerçevesinde
                # kurulur (plaka [x0, yüz], direk kökü x0). Girişim hükmü
                # STEP ile AYNI işlevden: direk kamarayı aşamaz, tanenin
                # portundan kalın direk tanenin içine giremez; plaka tanenin
                # önünde biter.
                _tane_on = _tane_port_r = None
                if fuel_grain_mesh is not None:
                    _tane_on = float(fuel_grain_mesh.bounds[0][2]) * 1000.0
                    _tane_port_r = port_diameter * 1000.0 / 2.0
                _red = pintle_assembly_refusal(
                    pintle_geo, chamber_length * 1000.0, _tane_on,
                    _tane_port_r)
                if _red is not None:
                    raise _red
                if (_tane_on is not None and pintle_geo['x_face'] - _tane_on
                        > _MONTAJ_GIRISIM_TOLERANS_MM):
                    raise ValueError(
                        'injector_plate_intersects_fuel_grain: the injector '
                        'plate ends at z = %.2f mm but the fuel grain starts '
                        'at z = %.2f mm; no assembly is exported with '
                        'interpenetrating parts.'
                        % (pintle_geo['x_face'], _tane_on))
                injector_mesh.visual.face_colors = [150, 150, 150, 200]
                assembly_meshes.append(('Injector', injector_mesh))
            elif injector_mesh is not None:
                # Mesh z-merkezli üretiliyor; STEP ile TEK kural
                # (``injector_plate_axial_span_mm``, ÖH V3 CAD A1 · H8):
                # plaka kapak iç yüzüne oturur, [x0, x0 + t].
                _x0_mm, _x1_mm, _ = injector_plate_axial_span_mm(
                    float(injector_mesh.bounds[1][2]
                          - injector_mesh.bounds[0][2]) * 1000.0)
                injector_mesh.apply_translation(
                    [0, 0, _x0_mm / 1000.0
                     - float(injector_mesh.bounds[0][2])])
                if fuel_grain_mesh is not None:
                    plaka_z1 = float(injector_mesh.bounds[1][2])
                    tane_z0 = float(fuel_grain_mesh.bounds[0][2])
                    ortusme_mm = (plaka_z1 - tane_z0) * 1000.0
                    if ortusme_mm > _MONTAJ_GIRISIM_TOLERANS_MM:
                        raise ValueError(
                            'injector_plate_intersects_fuel_grain: the '
                            'injector plate ends at z = %.2f mm but the fuel '
                            'grain starts at z = %.2f mm, so the two solids '
                            'overlap by %.2f mm. A motor whose injector is '
                            'inside its grain cannot be manufactured; no '
                            'assembly is exported with interpenetrating '
                            'parts. Shorten the plate or move the grain.'
                            % (plaka_z1 * 1000.0, tane_z0 * 1000.0,
                               ortusme_mm))
                injector_mesh.visual.face_colors = [150, 150, 150, 200]
                assembly_meshes.append(('Injector', injector_mesh))

            if fuel_grain_mesh is not None:
                fuel_grain_mesh.visual.face_colors = [139, 69, 19, 150]
                assembly_meshes.append(('Fuel Grain', fuel_grain_mesh))

            print("CAD Debug - Creating plotly visualization...")
            # Create plotly visualization
            plotly_data = self._create_plotly_visualization(assembly_meshes, motor_data)

            print("CAD Debug - Generating technical drawings...")
            # Generate technical drawings
            technical_drawings = self._generate_technical_drawings(motor_data)

            print("CAD Debug - Creating material specifications...")
            # Create material specifications
            material_specs = self._generate_material_specifications(motor_data)

            from hrma.export.motor_geometry import (
                EXPORT_AXIS, EXPORT_AXIS_NOTE, MESH_BUILD_AXIS)
            return {
                # ÖH D21 / P15B4-05 + P9B1-31: şekil KENDİNİ TANITIR.
                'schema': CAD_VISUALIZATION_SCHEMA,
                # ÖH D26 / defter P15B4-01: paketin eksen sözleşmesi ARTIK
                # yazılı. Ölçüldü (taban 7751531): STEP +X, STL +Z idi ve
                # sözlükte 'x-axis' / 'z-up' / 'orientation' sayacı 0'dı —
                # yani 90°'lik dönüklüğü söyleyen tek bir alan bile yoktu.
                'axis_convention': {
                    'export_axis': EXPORT_AXIS,
                    'mesh_build_axis': MESH_BUILD_AXIS,
                    'note': EXPORT_AXIS_NOTE,
                    'applies_to': ['STEP solids', 'STL files', 'DXF drawings'],
                    'in_memory_meshes': (
                        'assembly_meshes below are built about +'
                        + MESH_BUILD_AXIS + ' (viewer, mass breakdown and the '
                        'measured envelope read them); export_stl_files '
                        'rotates the copy it writes to +' + EXPORT_AXIS),
                },
                'assembly_meshes': assembly_meshes,
                'plotly_visualization': plotly_data,
                'technical_drawings': technical_drawings,
                'material_specifications': material_specs,
                'manufacturing_notes': self._generate_manufacturing_notes(motor_data),
                # ÖH Z5S (defter P9B1-02, kritik): zarf çapı ÜRETİLEN
                # katılardan ölçülür; bu yüzden özet katıları görmek zorunda.
                'performance_summary': self._generate_cad_performance_summary(
                    motor_data, assembly_meshes=assembly_meshes)
            }

        except Exception as e:
            print(f"CAD generation error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                # Başarısız üretim de KENDİ şeklini söyler: okuyucu 'bu benim
                # şeklim değil' ile 'benim şeklim ama üretilemedi'yi ayırır.
                'schema': CAD_VISUALIZATION_SCHEMA,
                'error': f'CAD generation failed: {str(e)}',
                'assembly_meshes': [],
                'plotly_visualization': None,
                'technical_drawings': None,
                'material_specifications': {},
                'manufacturing_notes': [],
                'performance_summary': {}
            }


    @staticmethod
    def _fix_solid(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Revolve çıktısını STL'e uygun hale getir: dejenere üçgenleri at,
        normal yönünü dışa çevir (negatif hacim = ters sarım)."""
        mesh.update_faces(mesh.nondegenerate_faces())
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
        if mesh.volume < 0:
            mesh.invert()
        return mesh

    def _chamber_solid(self, diameter: float, length: float,
                       wall: float, cap_t: float) -> trimesh.Trimesh:
        """Baş kapak + silindirik tüp tek kapalı profil revolve katısı (m)."""
        r_in = diameter / 2
        r_out = r_in + wall
        profile = np.array([
            [0.0, -cap_t],
            [r_out, -cap_t],
            [r_out, length],
            [r_in, length],
            [r_in, 0.0],
            [0.0, 0.0],
            [0.0, -cap_t],
        ])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _nozzle_solid(self, profile_m) -> trimesh.Trimesh:
        """Gerçek iç konturdan duvarlı nozul katısı.

        ``profile_m``: ``nozzle_wall_profile(..., unit='m')`` — iç ve dış
        kontur STEP ile TEK kaynaktan (V301 bilinen C1); burada yalnız
        trimesh'in (r, z) sırasına çevrilip kapalı halka profili kurulur:
        iç kontur girişten çıkışa, dış kontur çıkıştan girişe. z = 0
        konverjan başlangıcı (metre).
        """
        if profile_m.get('unit') != 'm':
            raise ValueError('the STL nozzle is built in metres; pass '
                             "nozzle_wall_profile(..., unit='m')")
        inner = [(r, z) for z, r in profile_m['inner']]
        outer = [(r, z) for z, r in reversed(profile_m['outer'])]
        profile = np.array(inner + outer + [inner[0]])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _grain_solid(self, r_outer: float, r_port: float,
                     z0: float, z1: float) -> trimesh.Trimesh:
        """Silindirik delikli yakıt grain'i — halka profil revolve (m)."""
        r_port = min(max(r_port, 1e-4), r_outer - 5e-4)
        profile = np.array([
            [r_port, z0],
            [r_outer, z0],
            [r_outer, z1],
            [r_port, z1],
            [r_port, z0],
        ])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _create_pintle_injector(self, geo) -> trimesh.Trimesh:
        """V301 bilinen C2 — pintle enjektör mesh'i (metre, montaj çerçevesi).

        ``geo``: ``pintle_cad_geometry`` (STEP ``_pintle_injector_solids`` ile
        TEK kaynak). Yüz plakası anülüs delikli disktir (kapalı profil
        revolve), direk Ø D_p silindir; uç delikleri yüzeyden
        ``hole_depth`` derinliğe radyal GERÇEK deliklerdir ve tek
        ``difference`` ile açılır. Boolean
        milimetre uzayında yapılır (ÖH D18 / OH-D16-06: küçük kesiciler metre
        uzayında geçersiz ağ veriyordu), sonra metreye ölçeklenir. Plaka ile
        direk iki ayrı kapalı kabuktur (aralarındaki anülüs boşluğu kanonik
        geometridir). Sonuç kapalı hacim değilse ADIYLA reddedilir.
        """
        x0, x1 = geo['x0'], geo['x_face']
        plaka = None
        if geo['plate_t'] is not None:
            R, rb = geo['plate_r'], geo['bore'] / 2.0
            plaka = self._fix_solid(trimesh.creation.revolve(np.array([
                [rb, x0], [R, x0], [R, x1], [rb, x1], [rb, x0]])))
        r_post = geo['d_post'] / 2.0
        boy = geo['x_tip'] - x0
        direk = trimesh.creation.cylinder(radius=r_post, height=boy,
                                          sections=PINTLE_STL_POST_SECTIONS)
        direk.apply_transform(trimesh.transformations.rotation_matrix(
            PINTLE_STL_POST_PHASE_FRACTION * 2.0 * np.pi
            / PINTLE_STL_POST_SECTIONS, [0.0, 0.0, 1.0]))
        direk.apply_translation([0.0, 0.0, x0 + boy / 2.0])
        if geo['n_holes']:
            # Kesici dipten (r_post - derinlik) başlar ve direk yüzeyini bir
            # delik çapı aşar (yalnız kesme payı; STEP
            # ``_pintle_injector_solids`` ile aynı kural).
            r_dip = r_post - geo['hole_depth']
            h = geo['hole_depth'] + geo['d_hole']
            # Delik açıları STEP'in +X çerçevesinde tanımlıdır: (y, z) =
            # (cos a, sin a). Mesh +Z ekseninde kurulur ve dosyaya
            # ``export_axis_rotation`` ile yazılır; yön o dönmenin TERSİYLE
            # mesh çerçevesine getirilir ki STL'deki delik STEP'tekiyle
            # AYNI açıda dursun (ölçüldü 22 Eki: dönüşümsüz kurulan delikler
            # dosyada 90 derece kayıyordu; 4'ün katı delik sayısında
            # görünmüyor, 31 delikli sıvı pintle'da yakalandı).
            ters = export_axis_rotation()[:3, :3].T
            kesiciler = []
            for i in range(geo['n_holes']):
                a = 2.0 * np.pi * i / geo['n_holes']
                yon = ters @ np.array([0.0, np.cos(a), np.sin(a)])
                kesici = trimesh.creation.cylinder(radius=geo['d_hole'] / 2.0,
                                                   height=h)
                donus = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], yon)
                donus[:3, 3] = yon * (r_dip + h / 2.0) + np.array(
                    [0.0, 0.0, geo['x_holes']])
                kesici.apply_transform(donus)
                kesiciler.append(kesici)
            direk = direk.difference(kesiciler)
        parcalar = [m for m in (plaka, direk) if m is not None]
        if not all(bool(getattr(m, 'is_volume', False)) for m in parcalar):
            raise ValueError(
                'pintle_injector_not_a_solid: the pintle faceplate or post '
                'mesh is not a closed volume after drilling; it cannot be '
                'manufactured and is not exported')
        mesh = (trimesh.util.concatenate(parcalar) if len(parcalar) > 1
                else parcalar[0])
        mesh.apply_scale(1.0 / 1000.0)
        return mesh

    def _create_injector_head(self, chamber_diameter: float, motor_data: Dict) -> trimesh.Trimesh:
        """Create injector head with orifices.

        ÖH D15 (defter P9B1-13): kalınlık ve yarıçap artık
        ``_injector_plate_design``den gelir — teknik çizim ve kütle dökümü
        AYNI fonksiyondan okur. Eski hâlinde burası sabit 30 mm x Ø(delik)
        çiziyor, çizim 13,64 mm yazıyor, kütle üçüncü bir parçayı tartıyordu.
        """
        try:
            # V301 bilinen C2: pintle'da bu DÜZ PLAKA yolu KAPALIDIR — devrenin
            # eşdeğer orifis planı pintle'ın delik planı değildir.
            if pintle_type_claimed(motor_data):
                raise ValueError(
                    'flat_plate_path_refused_for_pintle: the injector is a '
                    'pintle; it is drawn from its canonical geometry '
                    '(pintle_cad_geometry), never as a flat plate with the '
                    'equivalent orifice plan')
            plate = _injector_plate_design(motor_data, chamber_diameter)
            radius = plate['radius_m']
            thickness = plate['thickness_m']
            if not thickness or not radius:
                raise ValueError(plate['source'])

            # Main injector plate
            injector_plate = trimesh.creation.cylinder(radius=radius, height=thickness)

            # Create injection orifices
            # v2.6.26: sayı/çap ÇÖZÜCÜDEN gelir. Gelmiyorsa DELİK AÇILMAZ —
            # eski 8 delik x 3 mm varsayılanı çizilmiş bir tasarım gibi
            # görünüyordu ama hiçbir hesaptan çıkmıyordu (uydurma geometri).
            # ÖH D33-2 / defter OH-D32-04 — DEVRE BAŞINA HALKA.
            # Delik planı ``_injector_spec``ten gelir ve STEP üreticisiyle
            # AYNI devre listesidir; halka yarıçapı kesirleri de STEP ile
            # ortaktır (``INJECTOR_RING_RADIUS_FRACTIONS``, TEK KAYNAK).
            # Eski kod tek (sayı, çap) çifti okuyordu: sıvı motorda
            # oksitleyici Ø2,4920 / yakıt Ø2,3217 mm çiftini tek çapa
            # indirgemek imkânsız olduğu için plaka 0 DELİKLE çıkıyor,
            # aynı ZIP'teki STEP ise 12 delik taşıyordu.
            from hrma.export.step_export import INJECTOR_RING_RADIUS_FRACTIONS

            devreler = [c for c in (motor_data.get('injector_mesh_circuits')
                                    or [])
                        if c.get('n') and c.get('d_mm')]
            if not devreler:
                orifice_count = int(motor_data.get('injector_orifices') or 0)
                orifice_diameter = (
                    _real_scalar(motor_data.get('orifice_diameter')) or 0.0)
                if orifice_count <= 0 or orifice_diameter <= 0:
                    return injector_plate
                devreler = [{'name': 'unidentified', 'n': orifice_count,
                             'd_mm': orifice_diameter * 1000.0}]
            orifice_count = sum(int(c['n']) for c in devreler)
            # Ret metinlerinde (ve tek devreli motorda) kullanılan temsilî çap
            orifice_diameter = max(float(c['d_mm']) for c in devreler) / 1000.0

            # ÖH D18 / OH-D16-06 — DELİKLER MİLİMETRE UZAYINDA, TEK
            # BOOLEAN'LA açılır.
            #
            # ÖLÇÜLDÜ (taban 9071a64, ``once_ohd1606.json``): plaka
            # 20 delik x Ø1,20 mm ile sağlıklı bir katı (2.768 üçgen,
            # ``is_volume=True``) veriyordu; 120 delik x Ø0,50 mm ve
            # 319 delik x Ø0,30 mm ise ham ``ValueError: Not all meshes
            # are volumes!`` ile düşüyordu — üstelik İLK boolean'da
            # (0,00 s), yani delik SAYISINDAN önce.
            #
            # Kök ölçüldü: kusur delik sayısı değil, METRE UZAYINDAKİ
            # ÖLÇEK. ``trimesh.creation.cylinder`` yarıçap 0,00025 m ve
            # 0,00015 m'de ``is_volume=False`` (su geçirmez değil) bir ağ
            # üretiyor; 0,0006 m'de sağlıklı. İmalat bandının alt ucuna
            # kırpılan bir delik (Ø0,30 mm -> r = 0,00015 m) bu yüzden
            # boolean'a GEÇERSİZ bir kesici olarak giriyordu. Delik sayısı
            # yalnız BAĞLANTILI: çapı kırpan aynı çözüm sayıyı yükseltiyor.
            #
            # İki değişiklik:
            #   1. Boolean MİLİMETRE uzayında yapılır (x1000, sonra geri
            #      ölçeklenir) — kesiciler orada sağlıklı katılardır.
            #   2. Delikler TEK ağda birleştirilip TEK farkla açılır;
            #      319 ardışık boolean yerine bir tane (ölçüldü: 0,14 s,
            #      42.236 üçgen, ``is_volume=True``).
            # Sonuç yine de katı değilse SESSİZ geçilmez: aşağıda ADIYLA
            # reddedilir (fail-closed; ham mesh mesajı kullanıcıya suçlu
            # olarak ÜRETİCİYİ gösteriyordu).
            _S = 1000.0                       # m -> mm
            plate_mm = trimesh.creation.cylinder(
                radius=radius * _S, height=thickness * _S)
            kesiciler = []
            for index, devre in enumerate(devreler):
                frac = INJECTOR_RING_RADIUS_FRACTIONS[
                    min(index, len(INJECTOR_RING_RADIUS_FRACTIONS) - 1)]
                orifice_radius = radius * frac
                d_m = float(devre['d_mm']) / 1000.0
                sayi = int(devre['n'])
                for i in range(sayi):
                    angle = 2 * np.pi * i / sayi
                    x = orifice_radius * np.cos(angle)
                    y = orifice_radius * np.sin(angle)
                    orifice = trimesh.creation.cylinder(
                        radius=(d_m / 2) * _S,
                        height=(thickness + 0.001) * _S,
                    )
                    orifice.apply_translation([x * _S, y * _S, -0.0005 * _S])
                    kesiciler.append(orifice)
            kesici_mesh = trimesh.util.concatenate(kesiciler)
            if not bool(getattr(kesici_mesh, 'is_volume', False)):
                raise ValueError(
                    'injector_orifices_not_manufacturable: %d orifices of '
                    'diameter %.4f mm do not form a valid cutting solid '
                    '(they overlap or are degenerate at this scale), so the '
                    'injector plate cannot be drilled. No plate is exported '
                    'with the holes silently omitted.'
                    % (orifice_count, orifice_diameter * 1000.0))
            injector_plate = plate_mm.difference(kesici_mesh)
            injector_plate.apply_scale(1.0 / _S)
            if not bool(getattr(injector_plate, 'is_volume', False)):
                raise ValueError(
                    'injector_plate_not_a_solid: drilling %d orifices of '
                    'diameter %.4f mm left a mesh that is not a closed '
                    'volume; it cannot be manufactured and is not exported.'
                    % (orifice_count, orifice_diameter * 1000.0))

            return injector_plate

        except Exception as e:
            # ÖH D15 (defter P9B1-13): eski yedek burada sessizce 30 mm'lik
            # bir plaka üretiyordu — yani hata durumunda bile uydurma bir
            # parça montaja giriyordu. Artık hata YUKARIYA taşınır; montaj
            # kapısı plakayı hiç eklemez ve gerekçe adlandırılır.
            print(f"Injector creation error: {str(e)}")
            raise

    def _create_plotly_visualization(self, assembly_meshes: List, motor_data: Dict) -> str:
        """Create interactive 3D visualization with Plotly"""
        try:
            fig = make_subplots(
                rows=2, cols=2,
                specs=[[{"type": "scene", "colspan": 2}, None],
                       [{"type": "xy"}, {"type": "xy"}]],
                subplot_titles=("3D Motor Assembly", "Cross-Section View", "Performance Chart"),
                vertical_spacing=0.1
            )

            # 3D Assembly view
            colors = ['lightblue', 'darkgray', 'silver', 'brown']
            mesh_added = False

            for i, (name, mesh) in enumerate(assembly_meshes):
                try:
                    if mesh is not None and hasattr(mesh, 'vertices') and hasattr(mesh, 'faces'):
                        vertices = mesh.vertices
                        faces = mesh.faces

                        if len(vertices) > 0 and len(faces) > 0:
                            # BDATA DUZELTMESI (v2.5.2): plotly 6.x numpy
                            # dizilerini fig.to_json()'da ikili (base64
                            # 'bdata') olarak yaziyor; gomulu plotly.js
                            # 1.58.5 bu bicimi cozemez ve 3D gorunum BOS
                            # kalir. Listeye cevirerek duz JSON uretiyoruz.
                            fig.add_trace(
                                go.Mesh3d(
                                    x=vertices[:, 0].tolist(),
                                    y=vertices[:, 1].tolist(),
                                    z=vertices[:, 2].tolist(),
                                    i=faces[:, 0].tolist(),
                                    j=faces[:, 1].tolist(),
                                    k=faces[:, 2].tolist(),
                                    color=colors[i % len(colors)],
                                    opacity=0.7,
                                    name=name
                                ),
                                row=1, col=1
                            )
                            mesh_added = True
                        else:
                            print(f"Warning: Empty mesh for {name}")
                    else:
                        print(f"Warning: Invalid mesh object for {name}")
                except Exception as mesh_error:
                    print(f"Error processing mesh {name}: {str(mesh_error)}")
                    continue

            # If no meshes were added, create a simple fallback representation
            if not mesh_added:
                print("No valid meshes found, creating fallback visualization")
                self._add_fallback_3d_motor(fig, motor_data, row=1, col=1)

            # Cross-section view
            self._add_cross_section_view(fig, motor_data, row=2, col=1)

            # Performance chart
            self._add_performance_chart(fig, motor_data, row=2, col=2)

            # Update layout
            fig.update_layout(
                title="HRMA Hybrid Rocket Motor - 3D CAD Design",
                scene=dict(
                    xaxis_title="X (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Z (m)",
                    aspectmode='data'
                ),
                height=800,
                showlegend=True
            )

            return fig.to_json()

        except Exception as e:
            print(f"Plotly visualization error: {str(e)}")
            import traceback
            traceback.print_exc()
            # Return simple plot data as fallback
            return self._create_fallback_visualization(motor_data)

    def _add_fallback_3d_motor(self, fig, motor_data: Dict, row: int, col: int):
        """Add simple 3D motor representation when meshes fail"""
        try:
            # ÖH D22 / OH-D19-03: uydurma ölçü varsayılanları söküldü.
            chamber_diameter = _drawable_length_m(
                motor_data, 'chamber_diameter', 'chamber diameter')
            chamber_length = _drawable_length_m(
                motor_data, 'chamber_length', 'chamber length')
            throat_diameter = _drawable_length_m(
                motor_data, 'throat_diameter', 'throat diameter')
            exit_diameter = _drawable_length_m(
                motor_data, 'exit_diameter', 'nozzle exit diameter')
            nozzle_length = _drawable_length_m(
                motor_data, 'nozzle_length', 'nozzle length')

            # Create simple cylindrical chamber
            theta = np.linspace(0, 2*np.pi, 20)
            z_chamber = np.linspace(0, chamber_length, 10)

            # Chamber surface
            theta_mesh, z_mesh = np.meshgrid(theta, z_chamber)
            x_chamber = (chamber_diameter/2) * np.cos(theta_mesh)
            y_chamber = (chamber_diameter/2) * np.sin(theta_mesh)

            # ÖH D27 / defter P13B2-09 — BDATA DÜZELTMESİ.
            # Bu yedek yol meshgrid'den gelen numpy dizilerini ``go.Surface``a
            # DOĞRUDAN veriyordu. plotly 6.x, ``fig.to_json()`` çıktısında
            # numpy dizilerini base64 ``bdata`` bloğu olarak yazar; uygulamanın
            # paketlediği vendor plotly.js 1.58.5 bu biçimi ÇÖZEMEZ. Sonuç:
            # mesh üretimi düştüğünde devreye giren bu yedek 3B görünümü
            # sessizce BOŞ bırakıyordu (ölçüldü, ``once_p13b209.json``:
            # 2 iz / 6 bdata bloğu; kullanıcıya hiçbir uyarı çıkmıyordu).
            # Aynı düzeltme mesh yolunda 2378-2383'te zaten yapılmıştı, yedek
            # yol atlanmıştı. Diziler düz listeye çevrilir — sayı üretilmez,
            # yalnız aynı sayılar taşınabilir biçime iner.
            fig.add_trace(
                go.Surface(
                    x=x_chamber.tolist(),
                    y=y_chamber.tolist(),
                    z=z_mesh.tolist(),
                    colorscale='Greys',
                    opacity=0.7,
                    name='Chamber',
                    showscale=False
                ),
                row=row, col=col
            )

            # Simple nozzle cone
            z_nozzle = np.linspace(chamber_length, chamber_length + nozzle_length, 10)
            r_nozzle = np.linspace(throat_diameter/2, exit_diameter/2, 10)

            theta_noz, z_noz = np.meshgrid(theta, z_nozzle)
            r_noz_mesh = np.array([r_nozzle]).T
            x_nozzle = r_noz_mesh * np.cos(theta_noz)
            y_nozzle = r_noz_mesh * np.sin(theta_noz)

            # ÖH D27 / defter P13B2-09 — yukarıdaki kamara yüzeyiyle aynı
            # gerekçe: numpy dizisi -> base64 bdata -> vendor plotly.js 1.58.5
            # çözemez -> lüle yüzeyi de sessizce çizilmezdi.
            fig.add_trace(
                go.Surface(
                    x=x_nozzle.tolist(),
                    y=y_nozzle.tolist(),
                    z=z_noz.tolist(),
                    colorscale='Blues',
                    opacity=0.8,
                    name='Nozzle',
                    showscale=False
                ),
                row=row, col=col
            )

        except ValueError:
            # ÖH D22 / OH-D19-03: ADLI RET YUTULMAZ. Buradaki eski "son çare"
            # dalı 0,1 x 0,05 x 0,1 m'lik SABİT bir "Motor Outline" çiziyordu;
            # yani ölçü yayımlanmadığında bile ekrana bir motor konuyordu.
            # Kapı bir üst katmana taşınır (``generate_3d_motor_assembly``
            # gerekçeyi ``error`` alanında yayımlar).
            raise
        except Exception as e:
            print(f"Error creating fallback 3D motor: {str(e)}")
            raise

    def _create_fallback_visualization(self, motor_data: Dict) -> str:
        """Create fallback visualization when main function fails"""
        try:
            fig = go.Figure()

            # Simple 3D representation
            # ÖH D22 / OH-D19-03: uydurma ölçü varsayılanları söküldü.
            chamber_diameter = _drawable_length_m(
                motor_data, 'chamber_diameter', 'chamber diameter')
            chamber_length = _drawable_length_m(
                motor_data, 'chamber_length', 'chamber length')

            # Chamber outline
            fig.add_trace(go.Scatter3d(
                x=[0, chamber_length, chamber_length, 0, 0],
                y=[0, 0, 0, 0, 0],
                z=[chamber_diameter/2, chamber_diameter/2, -chamber_diameter/2, -chamber_diameter/2, chamber_diameter/2],
                mode='lines',
                name='Chamber Outline',
                line=dict(color='blue', width=4)
            ))

            # Nozzle outline
            nozzle_length = _drawable_length_m(
                motor_data, 'nozzle_length', 'nozzle length')
            exit_diameter = _drawable_length_m(
                motor_data, 'exit_diameter', 'nozzle exit diameter')

            fig.add_trace(go.Scatter3d(
                x=[chamber_length, chamber_length + nozzle_length],
                y=[0, 0],
                z=[chamber_diameter/2, exit_diameter/2],
                mode='lines',
                name='Nozzle Top',
                line=dict(color='red', width=3)
            ))

            fig.add_trace(go.Scatter3d(
                x=[chamber_length, chamber_length + nozzle_length],
                y=[0, 0],
                z=[-chamber_diameter/2, -exit_diameter/2],
                mode='lines',
                name='Nozzle Bottom',
                line=dict(color='red', width=3)
            ))

            fig.update_layout(
                title="HRMA Hybrid Rocket Motor - Simplified View",
                scene=dict(
                    xaxis_title="Length (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Radius (m)",
                    aspectmode='data'
                ),
                height=600,
                showlegend=True
            )

            return fig.to_json()

        except Exception as e:
            # ÖH D22 / OH-D19-03: "mutlak asgari yedek" SÖKÜLDÜ. Bu dal
            # 0,5 x 0,1 m'lik SABİT bir "Basic Motor Shape" çizip
            # yayımlıyordu — hangi motor gönderilirse gönderilsin aynı
            # şekil. Ölçü yayımlanmamışsa çizim de yayımlanmaz; gerekçe
            # çağırana taşınır.
            print(f"Fallback visualization error: {str(e)}")
            raise

    def _add_cross_section_view(self, fig, motor_data: Dict, row: int, col: int):
        """2D kesit — geometri ve açılar ÇÖZÜCÜNÜN kendi çıktısından.

        Eski sürüm açıları `motor_data.get('convergent_angle', 15.0)` /
        `('divergent_angle', 12.0)` ile okuyordu; bu anahtarlar motor
        sonucunda HİÇ YOK, dolayısıyla her motor için 15°/12° çiziliyor ve
        lejantta öyle etiketleniyordu (2026-07-19 denetimi). Gerçek değerler
        `nozzle_angles` / `nozzle_contour.divergent` altında. Ayrıca kontur
        artık sample_nozzle_inner_contour ile çizilir — 2D kesit, 3D CAD ve
        DXF ile TEK kaynak (bell lüle artık düz koni gibi görünmez).
        """

        # ÖH D22 / OH-D19-03: uydurma ölçü varsayılanları söküldü.
        chamber_diameter = _drawable_length_m(
            motor_data, 'chamber_diameter', 'chamber diameter')
        chamber_length = _drawable_length_m(
            motor_data, 'chamber_length', 'chamber length')
        throat_diameter = _drawable_length_m(
            motor_data, 'throat_diameter', 'throat diameter')
        exit_diameter = _drawable_length_m(
            motor_data, 'exit_diameter', 'nozzle exit diameter')

        conv_deg, div_deg, angle_type = _nozzle_half_angles(motor_data)

        chamber_top = chamber_diameter / 2
        chamber_bottom = -chamber_diameter / 2
        nozzle_start = chamber_length

        # Gerçek iç kontur (mm -> m); z=0 kamara çıkışı
        pts_mm, meta = sample_nozzle_inner_contour(motor_data)
        noz_x = [nozzle_start + z / 1000.0 for z, _r in pts_mm]
        noz_r = [r / 1000.0 for _z, r in pts_mm]
        throat_pos = nozzle_start + meta['z_throat'] / 1000.0
        throat_r = meta['r_throat'] / 1000.0
        nozzle_end = nozzle_start + meta['z_exit'] / 1000.0

        # Draw chamber
        fig.add_trace(
            go.Scatter(
                x=[0, chamber_length, chamber_length, 0, 0],
                y=[chamber_top, chamber_top, chamber_bottom, chamber_bottom, chamber_top],
                mode='lines',
                name='Chamber',
                line=dict(color='blue', width=2)
            ),
            row=row, col=col
        )

        # Draw nozzle profile from the solver contour
        fig.add_trace(
            go.Scatter(
                x=noz_x + noz_x[::-1],
                y=noz_r + [-r for r in noz_r[::-1]],
                fill='toself',
                name=f'Nozzle ({meta.get("noz_type", "conical")})',
                fillcolor='rgba(128,128,128,0.3)',
                line=dict(color='gray')
            ),
            row=row, col=col
        )

        # Add throat line indicator
        fig.add_trace(
            go.Scatter(
                x=[throat_pos, throat_pos],
                y=[-throat_r, throat_r],
                mode='lines',
                name='Throat',
                line=dict(color='red', width=3, dash='dash')
            ),
            row=row, col=col
        )

        annotations = []
        angle_length = 0.03  # açı göstergesi çizgi boyu [m]

        # Açı göstergeleri YALNIZ gerçek açı varsa çizilir/etiketlenir.
        if conv_deg is not None:
            conv_angle_rad = np.radians(conv_deg)
            conv_mid_x = nozzle_start + (throat_pos - nozzle_start) * 0.5
            conv_mid_r = chamber_top - (chamber_top - throat_r) * 0.5
            conv_end_x = conv_mid_x + angle_length * np.cos(np.pi - conv_angle_rad)
            conv_end_y = conv_mid_r + angle_length * np.sin(np.pi - conv_angle_rad)
            fig.add_trace(
                go.Scatter(
                    x=[conv_mid_x, conv_end_x],
                    y=[conv_mid_r, conv_end_y],
                    mode='lines',
                    name=f'Conv. {conv_deg:.1f}°',
                    line=dict(color='orange', width=2, dash='dot')
                ),
                row=row, col=col
            )
            annotations.append(dict(
                x=conv_end_x, y=conv_end_y,
                text=f'{conv_deg:.1f}°',
                showarrow=False,
                font=dict(size=9, color='orange')
            ))

        if div_deg is not None:
            div_angle_rad = np.radians(div_deg)
            div_mid_x = throat_pos + (nozzle_end - throat_pos) * 0.5
            div_mid_r = throat_r + (div_mid_x - throat_pos) * np.tan(div_angle_rad)
            div_end_x = div_mid_x + angle_length * np.cos(div_angle_rad)
            div_end_y = div_mid_r + angle_length * np.sin(div_angle_rad)
            div_label = ('Div. throat %.1f°' % div_deg if angle_type == 'bell'
                         else 'Div. %.1f°' % div_deg)
            fig.add_trace(
                go.Scatter(
                    x=[div_mid_x, div_end_x],
                    y=[div_mid_r, div_end_y],
                    mode='lines',
                    name=div_label,
                    line=dict(color='green', width=2, dash='dot')
                ),
                row=row, col=col
            )
            annotations.append(dict(
                x=div_end_x, y=div_end_y,
                text=f'{div_deg:.1f}°',
                showarrow=False,
                font=dict(size=9, color='green')
            ))

        # Chamber diameter annotation
        annotations.append(dict(
            x=-chamber_length * 0.1,
            y=0,
            text=f'D = {chamber_diameter*1000:.1f} mm',
            showarrow=False,
            font=dict(size=10),
            textangle=90
        ))

        # Throat diameter annotation
        annotations.append(dict(
            x=throat_pos,
            y=-throat_r - chamber_diameter * 0.15,
            text=f'dt = {throat_diameter*1000:.2f} mm',
            showarrow=False,
            font=dict(size=10)
        ))

        # Exit diameter annotation
        annotations.append(dict(
            x=nozzle_end,
            y=-exit_diameter/2 - chamber_diameter * 0.15,
            text=f'de = {exit_diameter*1000:.1f} mm',
            showarrow=False,
            font=dict(size=10)
        ))

        # Expansion ratio: çözücünün değeri varsa o, yoksa geometriden
        expansion_ratio = _real_scalar(motor_data.get('expansion_ratio'))
        if expansion_ratio is None:
            expansion_ratio = (exit_diameter / throat_diameter) ** 2
        annotations.append(dict(
            x=(throat_pos + nozzle_end) / 2,
            y=chamber_diameter * 0.3,
            text=f'ε = {expansion_ratio:.1f}',
            showarrow=False,
            font=dict(size=10, color='purple')
        ))

        fig.update_xaxes(title_text="Length (m)", row=row, col=col)
        fig.update_yaxes(title_text="Radius (m)", row=row, col=col)

        # Add annotations to the layout (they'll apply to the subplot)
        if hasattr(fig, 'add_annotation'):
            for ann in annotations:
                fig.add_annotation(ann, row=row, col=col)

    def _add_performance_chart(self, fig, motor_data: Dict, row: int, col: int):
        """Add performance characteristics chart.

        DUZELTME (v2.5.2): eski surum burada UYDURMA bir egri ciziyordu
        (sabit itkiye %10'luk dogrusal dusus ekleyip 'realistic thrust curve
        variation' diye etiketliyordu). Teknik cizim ciktisinda hesaplanmamis
        bir egriyi hesaplanmis gibi gostermek yanilticidir. Artik once GERCEK
        egri aranir (transient / thrust_curve / port_history); yoksa sabit
        tasarim itkisi cizilir ve etikette bunun bir VARSAYIM oldugu yazar.

        Ayrica diziler listeye cevrilir: plotly 6.x numpy'i ikili (bdata)
        yaziyor, gomulu plotly.js 1.58.5 cozemiyor ve egri BOS kaliyordu.
        """
        time_s, thrust_n, label = None, None, None

        def _cizilmedi(metin):
            """İz çizilmez; gerekçe performans alt grafiğinin ORTASINA yazılır.

            ÖH D37 A1b sahte-veri-b — ölçüldü (docs/scofield/raw/OH/A1b/
            sahte-veri-b/a1/ara_domain_ref/urun_cad_*.png): not ``xref='x domain'``
            ile ekleniyordu; ``row/col`` onu ``'x2 domain'``e çeviriyor, ama
            ürünün plotly.js'i (``static/vendor/plotly-1.58.5.min.js``) ve
            kaleido bu başvuruyu TANIMIYOR — not Kesit görünümünün VERİ
            koordinatına (0,5 m; 0,5 m) düşüyor, kesit eksenlerini o noktaya
            kadar genişletiyor ve performans alt grafiği boş kalıyordu.
            Konum artık alt grafiğin alan sınırlarından ``paper``
            koordinatında hesaplanır (her plotly.js sürümünde aynı yer);
            metin ve veri DEĞİŞMEZ.
            """
            alt = fig.get_subplot(row, col)
            xd = list(getattr(alt.xaxis, 'domain', None) or (0.0, 1.0))
            yd = list(getattr(alt.yaxis, 'domain', None) or (0.0, 1.0))
            fig.add_annotation(
                text=metin, x=(xd[0] + xd[1]) / 2.0, y=(yd[0] + yd[1]) / 2.0,
                xref='paper', yref='paper', xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=10))
            fig.update_xaxes(title_text="Time (s)", row=row, col=col)
            fig.update_yaxes(title_text="Thrust (N)", row=row, col=col)
            return metin

        transient = motor_data.get('transient') or {}
        curve = motor_data.get('thrust_curve') or {}
        if transient.get('time') and transient.get('thrust'):
            time_s = list(transient['time'])
            thrust_n = list(transient['thrust'])
            label = 'Thrust (computed transient)'
        elif curve.get('time') and curve.get('thrust'):
            time_s = list(curve['time'])
            thrust_n = list(curve['thrust'])
            label = 'Thrust (computed curve)'
        else:
            # ÖH D36 / onemli2-sivi a2 — SÜRE UYDURULMAZ. Eski satır
            # ``float(motor_data.get('burn_time', 10) or 10)`` idi; sıvı
            # çözücü süre verilmediğinde ``burn_time`` yayımlamadığı için
            # (LU-1) bu grafik 0-10 s'lik UYDURMA bir zaman ekseni çiziyordu
            # (ölçüldü, a2/once.json K6: x = [0,0; 10,0], 25 000 N). Süre
            # yoksa iz ÇİZİLMEZ ve alt grafiğin içine nedeni adıyla yazılır;
            # süre verildiğinde iz eskisiyle bit-aynıdır.
            burn_time = _real_scalar(motor_data.get('burn_time'))
            if burn_time is None:
                return _cizilmedi(PERFORMANCE_CHART_NOT_DRAWN_REASON)
            # ÖH D37 A1b sahte-veri-b · OH-D37-S7 (CAD ayağı) — İTKİ
            # UYDURULMAZ. Eski satır itki anahtarını 1000 yedeğiyle okuyordu:
            # itki yayımlanmamışsa (ya da 0 ise) grafik 1000 N düz çizgi
            # çiziyordu (ölçüldü, docs/scofield/raw/OH/A1b/sahte-veri-b/a1/
            # once/olcum.json ``sivi_sureli_itkisiz``: x = [0; 250] s,
            # y = [1000; 1000] N — çözücünün sayısı değil). Süre kolunun
            # deseni aynen: gerçek skaler yoksa iz ÇİZİLMEZ, alt grafiğe
            # nedeni adıyla yazılır; itki + süre varken iz bit-aynı. Metin EN
            # (CAD şekil metinleri EN üretilir — süre gerekçesiyle aynı).
            thrust_not_drawn_reason = (
                'Performance chart not drawn: thrust was not published by '
                'the solver and no design thrust is assumed.')
            design_thrust = _real_scalar(motor_data.get('thrust'))
            if design_thrust is None:
                return _cizilmedi(thrust_not_drawn_reason)
            time_s = [0.0, burn_time]
            thrust_n = [design_thrust, design_thrust]
            label = 'Thrust (design point, constant-thrust assumption)'

        fig.add_trace(
            go.Scatter(
                x=[float(v) for v in time_s],
                y=[float(v) for v in thrust_n],
                mode='lines',
                name=label,
                line=dict(color='red', width=2)
            ),
            row=row, col=col
        )

        fig.update_xaxes(title_text="Time (s)", row=row, col=col)
        fig.update_yaxes(title_text="Thrust (N)", row=row, col=col)

    def _generate_technical_drawings(self, motor_data: Dict) -> Dict:
        """İmalat spesifikasyonu — ÇÖZÜCÜNÜN kendi sonuçlarından.

        Eski sürümde cidar kalınlığı sabit 5.0 mm, enjektör plakası 30 mm ve
        malzemeler ('Steel 304' / 'Graphite' / 'Stainless Steel 316') motor
        sonucundan bağımsızdı; 20 kN'lik bir motorda yapısal analiz 29 mm cidar
        isterken çizim 5 mm yazıyordu (2026-07-19 denetimi). Artık:
          - cidar kalınlığı: structural_analysis.chamber_analysis
          - enjektör plakası: structural_analysis.end_cap_analysis (düz kapak)
          - malzeme: yapısal analizde seçilen materials_db kaydı
          - lüle açıları: nozzle_angles / nozzle_contour
        Değer yoksa sabit sayı yazılmaz; alan NOT_AVAILABLE_SPEC olur.
        Tolerans ve yüzey pürüzlülüğü tasarım kararı DEĞİLDİR; standart
        değerler 'basis' alanında kaynağıyla etiketlenir.
        """

        drawings = {}

        wall_design = _chamber_wall_design(motor_data)
        wall_m = wall_design['thickness_m']
        wall_source = wall_design['source']
        _mat_key, mat_name, _rho = _chamber_material(motor_data)
        conv_deg, div_deg, noz_type = _nozzle_half_angles(motor_data)
        inj = _injector_spec(motor_data)

        struct = motor_data.get('structural_analysis') or {}
        # ÖH D15 (defter P9B1-13): çizim, mesh ve kütle AYNI plakayı anlatır.
        # Eski kod buraya KAPAK kalınlığını (end_cap_analysis) yazıyordu — o
        # kamaranın ön kapağıdır, enjektör plakası değil.
        plate_design = _injector_plate_design(motor_data)
        plate_mm = ((plate_design['thickness_m'] * 1000.0)
                    if plate_design['thickness_m'] else None)
        plate_dia_mm = ((plate_design['radius_m'] * 2000.0)
                        if plate_design['radius_m'] else None)
        inj_present, inj_reason = _injector_evidence(motor_data)
        # V301 bilinen C2: pintle'da çizim sözlüğü de montajla AYNI hükmü
        # verir (iki çıktı çelişemez): pintle, yüz plakası yayımlanmasa da
        # direk + uç delikleriyle ÇİZİLİR; çizilemiyorsa gerekçe adıyla.
        pintle_cizim = None
        if inj_present and pintle_type_claimed(motor_data):
            try:
                _pg = pintle_cad_geometry(motor_data)
            except PintleCADError as _hata:
                pintle_cizim = {'drawn': False, 'not_drawn_reason': str(_hata),
                                'invalid_fields': _hata.invalid_fields}
                inj_present, inj_reason = False, str(_hata)
            else:
                pintle_cizim = {
                    'drawn': not _pg['not_drawn_reason'],
                    'not_drawn_reason': _pg['not_drawn_reason'],
                    'post_diameter_mm': _pg['d_post'],
                    'annulus_gap_mm': _pg['gap'],
                    'annulus_bore_diameter_mm': _pg['bore'],
                    'annulus_bore_drawn': _pg['plate_t'] is not None,
                    'tip_hole_mode': _pg['mode'],
                    'tip_hole_count': _pg['n_holes'],
                    'tip_hole_diameter_mm': _pg['d_hole'],
                    'skip_distance_mm': _pg['skip'],
                    'tip_hole_depth_mm': _pg['hole_depth'],
                    'post_tip_x_mm': _pg['x_tip'],
                    'source': _pg['source_path'],
                    'drawing_basis': PINTLE_CAD_DRAWING_BASIS,
                    'equivalent_orifice_plan': (
                        PINTLE_EQUIVALENT_PLAN_NOT_DRILLED),
                }
                if _pg['not_drawn_reason']:
                    inj_present, inj_reason = False, _pg['not_drawn_reason']
        if inj_present and plate_mm is None and pintle_cizim is None:
            # ÖH D15 (defter P9B1-13): enjektör var ama plakanın kalınlığı
            # yayımlanmamış -> plaka ÇİZİLMEZ; çizim sözlüğü bunu montajla
            # AYNI gerekçeyle söyler (iki çıktı çelişemez).
            inj_present = False
            inj_reason = plate_design['source']
        # ÖH D15 (defter P9B1-17): ön kapak artık ÇİZİM SÖZLÜĞÜNDE de görünür.
        # Ölçüldü (31 Ağustos 2026): ``technical_drawings.chamber`` içinde
        # cap/head/closure geçen HİÇBİR alan yoktu — basınç sınırının parçası
        # olan kapağın kalınlığını kullanıcı yalnız STL'i ölçerek öğrenebiliyordu.
        cap_design = _front_cap_design(
            motor_data,
            wall_mm=(wall_m * 1000.0) if wall_m else None,
            bore_radius_mm=((_real_scalar(motor_data.get('chamber_diameter'))
                             or 0.0) * 1000.0 / 2.0) or None)

        # Chamber drawing
        # v2.6.26 (Y3): 'outer_diameter' aslında İÇ (kamara) çapını yazıyordu,
        # hemen yanında ayrı bir 'wall_thickness' alanı varken. Ölçüldü: katı
        # modelin mesh köşelerinden okunan gerçek dış çap 184,37 mm iken ölçü
        # tablosu 152,53 mm diyordu (152,53 + 2 x 15,92 = 184,37). Atölye
        # Ø152 mm boru alıp 15,92 mm cidar bırakacak şekilde tornalasa kalan
        # delik 120,7 mm olurdu; grain'in dış çapı 146,4 mm — parça takılmaz.
        # Artık iç ve dış çap AYRI ve ikisi de katı modelin gerçeğiyle tutar.
        bore_mm = _real_scalar(motor_data.get('chamber_diameter'))
        bore_mm = bore_mm * 1000.0 if bore_mm is not None else None
        outer_mm = ((bore_mm + 2.0 * wall_m * 1000.0)
                    if (bore_mm is not None and wall_m) else None)
        length_m = _real_scalar(motor_data.get('chamber_length'))
        length_mm = length_m * 1000.0 if length_m is not None else None
        drawings['chamber'] = {
            # Kamara İÇ çapı (yanma hacmi / grain dış çapı bu ölçüye oturur)
            'inner_diameter': bore_mm if bore_mm is not None else NOT_AVAILABLE_SPEC,
            # Boru dış çapı = iç çap + 2 x cidar (katı modelle birebir aynı)
            'outer_diameter': outer_mm if outer_mm is not None else NOT_AVAILABLE_SPEC,
            'diameter_convention': ('inner_diameter is the chamber bore; '
                                    'outer_diameter = inner_diameter + 2 x '
                                    'wall_thickness and matches the CAD solid'),
            'wall_thickness': (wall_m * 1000.0) if wall_m else NOT_AVAILABLE_SPEC,
            'wall_thickness_source': wall_source,
            # Hangi kalınlık çizildi, yapısal analiz ne öneriyor, ekrandaki
            # emniyet katsayısı hangisine ait — üçü de aynı satırda.
            'wall_thickness_as_designed': (wall_design['as_designed_mm']
                                           if wall_design['as_designed_mm'] is not None
                                           else NOT_AVAILABLE_SPEC),
            'wall_thickness_recommended': (wall_design['recommended_mm']
                                           if wall_design['recommended_mm'] is not None
                                           else NOT_AVAILABLE_SPEC),
            'wall_thickness_note': wall_design['note'],
            # ÖH D30 / OH-D29-10 — AYNI GERÇEK, İKİ ADRES: YÖN TARİFİ.
            #
            # ÖLÇÜLDÜ (taban ``ab7cf68b``, ``once_taban.json`` K3; hibrit,
            # katı ve sıvı şemalarının üçünde): bu sözlüğün dört cidar
            # künyesi ile ``performance_summary.geometry_summary``nin dört
            # künyesi DEĞERCE BİREBİR AYNI (4 çift x 3 motor = 12 çiftin
            # 12'si eşit) — çünkü ikisi de TEK çözümleyiciden
            # (``_chamber_wall_design``) besleniyor. Ayrışma bugün YOK.
            # Eksik olan, okuyucunun bunu BİLMESİYDİ: iki adresin hiçbiri
            # ötekini anmıyordu (ölçüm: üç motorda da yön tarifi yok), ve
            # adlar da bire bir tutmuyor (burada ``wall_thickness``, orada
            # ``wall_thickness_mm``). Aynı yanıtta iki sayı gören okuyucu
            # ikisini bağımsız iki ölçüm sanabilirdi.
            #
            # Buraya SAYI KOPYALANMADI (D29 / P15B4-12'nin
            # ``mass_inputs_note`` deseni): yalnız birim, çözümleyicinin adı
            # ve kardeş adres yazılır. Kardeş dizini ``export-cad``
            # yanıtında bulunmadığında (bu sözlük tek başına da üretilir)
            # cümle yine doğrudur — adres tarifidir, varlık iddiası değil.
            'wall_thickness_basis': (
                'wall_thickness, wall_thickness_as_designed and '
                'wall_thickness_recommended are MILLIMETRES, resolved by the '
                'single chamber-wall resolver (cad_visualization.'
                '_chamber_wall_design) from structural_analysis. When this '
                'drawing is produced as part of a cad_design response the '
                'same four values are also published, with the same source '
                'tag, as performance_summary.geometry_summary.'
                'wall_thickness_mm / .wall_thickness_source / '
                '.wall_thickness_recommended_mm / .wall_thickness_note. '
                'They are the SAME resolver output, not a second '
                'measurement.'),
            # ÖH Z2 (defter P9B1-01, kritik): bu alan ÖLÇÜLMÜŞ emniyet
            # katsayısıdır. Eskiden bloğun ``safety_factor`` alanı koşulsuz
            # basılıyordu; sıvı motorda o alan kullanıcının SF HEDEFİNİN
            # kendisi (kardeş künye: "user input (safety factor)"), katı
            # motorun boyutlandırma modunda ise hedefin cebirsel eko'su.
            # Ölçüldü (27 Ağustos 2026): girdi 2,5 -> çizim 2,5. Artık ölçüm
            # Sayı, bloğun onu ÇİZİLEN cidarda hesapladığı hâllerde (ölçüm
            # True ya da False) yerinde kalır — gizlemek 1'in altındaki bir
            # katsayıyı da gizlerdi. Bloğun çizilen cidar için hiçbir SF
            # yayımlamadığı hâlde (``None``; sıvı motorun bugünkü durumu,
            # yayımladığı sayı kullanıcının HEDEFİ) alan boş bırakılır.
            # "Doğrulandı" iddiası ayrı alanda ve orada geri çekilir.
            'safety_factor_at_drawn_wall': (
                wall_design['safety_factor']
                if (wall_design['safety_factor_is_measured'] is not None
                    and wall_design['safety_factor'] is not None)
                else NOT_AVAILABLE_SPEC),
            'safety_factor_is_measured': wall_design['safety_factor_is_measured'],
            'design_safety_factor_target': (
                wall_design['safety_factor_target']
                if wall_design['safety_factor_target'] is not None
                else NOT_AVAILABLE_SPEC),
            'safety_factor_basis': (wall_design['safety_factor_basis']
                                    or _wall_sf_basis_text(wall_design)),
            'wall_verified_against_pressure_load': wall_design['verified'],
            'length': (length_m * 1000.0) if length_m is not None else NOT_AVAILABLE_SPEC,
            'material': mat_name or NOT_AVAILABLE_SPEC,
            'surface_finish': DRAWING_SURFACE_FINISH_CHAMBER,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS,
            # v2.6.26 (P4): tolerans artık ÖLÇÜNÜN KENDİSİNDEN aranır.
            # Öncesi: sabit '+-0.1 mm' çap ve '+-0.5 mm' boy — hem motorun
            # boyutundan bağımsızdı, hem de hemen yanındaki 'basis' alanı
            # "ISO 2768-m" diyordu ama o standardın tablosu ölçüyle DEĞİŞİR
            # (Ø100 mm için m sınıfı ±0.3 mm, f sınıfı ±0.15 mm). Yani
            # sayılar kaynağa uymuyordu: yanlış künye.
            'tolerances': _iso2768_tolerance_block(bore_mm, outer_mm,
                                                   length_mm),
            # ÖH D15 (defter P9B1-17): ÇİZİLEN ön kapak ve künyesi. Kapak
            # basınç sınırının parçasıdır; sözlükte hiç görünmemesi imalatçıya
            # ölçüsü verilmeyen bir parça bırakıyordu. Yapısal analizin
            # DEĞERLENDİRDİĞİ kalınlık ve önerdiği tip de yanında durur ki
            # okuyucu çizilenle analiz edilenin aynı parça olup olmadığını
            # görebilsin.
            'front_cap_thickness': (cap_design['thickness_mm']
                                    if cap_design['thickness_mm'] is not None
                                    else NOT_AVAILABLE_SPEC),
            'front_cap_thickness_source': cap_design['source'],
            'front_cap_from_structural_analysis': cap_design['from_analysis'],
            'front_cap_recommended_type': (cap_design['recommended_type']
                                           or NOT_AVAILABLE_SPEC),
            'front_cap_thickness_evaluated_by_analysis': (
                cap_design['used_mm'] if cap_design['used_mm'] is not None
                else NOT_AVAILABLE_SPEC),
        }

        # Nozzle drawing
        # Boy: `or 0.0` zinciri yerine açık koşul — geçersiz boy 0 mm olarak
        # yazılmaz (aynı hata geometri özetinde gerçekten 0 mm üretiyordu).
        nozzle_len_m = _nozzle_length_m(motor_data)
        drawings['nozzle'] = {
            # ÖH D22 / OH-D19-03: imalat çizimine uydurma ölçü YAZILMAZ.
            'throat_diameter': _drawable_length_m(
                motor_data, 'throat_diameter', 'throat diameter',
                scale=1000.0),  # mm
            'exit_diameter': _drawable_length_m(
                motor_data, 'exit_diameter', 'nozzle exit diameter',
                scale=1000.0),  # mm
            'length': ((nozzle_len_m * 1000.0) if nozzle_len_m is not None
                       else NOT_AVAILABLE_SPEC),  # mm
            'nozzle_type': noz_type,
            'convergence_angle': conv_deg if conv_deg is not None else NOT_AVAILABLE_SPEC,
            'divergence_angle': div_deg if div_deg is not None else NOT_AVAILABLE_SPEC,
            # ÖH D15 (defter P9B1-15): aile karşılaştırması KESİN EŞİTLİKTEN
            # ``_nozzle_family`` normalizasyonuna geçti — 'bell_80' de bell'dir.
            'divergence_angle_meaning': ('bell: throat exit angle (theta_n); the '
                                         'wall angle decreases toward the exit'
                                         if _nozzle_family(noz_type) == 'bell'
                                         else 'conical: constant half angle'),
            # ÖH D15 (defter P9B1-15): çıkış açısı YALNIZ
            # ``nozzle_contour.divergent.exit_angle`` yolundan aranıyordu; sıvı
            # çözücüsü o bloğu boş bırakıp değeri ``nozzle_angles`` altında
            # yayımlıyor. Ölçüldü: alan 'NOT AVAILABLE' derken aynı sonuçta
            # ``nozzle_angles.exit_angle_deg`` = 8,5 duruyordu.
            # TEK KAYNAK (ÖH D15 / a2): çözüm ``_nozzle_exit_angle_deg``te
            # yaşar; imalat çizimi (drawing_generator) de onu okur.
            'divergent_exit_angle': (_nozzle_exit_angle_deg(motor_data)
                                     or NOT_AVAILABLE_SPEC),
            # ÖH Z5S (defter P9B1-24): künye KAZANILIR — çözücünün kendi
            # ``angles_source`` beyanı (ör. 'conical_default_30_15') artık
            # düşürülmez, aynen taşınır ve varsayılan olduğu söylenir.
            'angle_source': _nozzle_angle_source_label(motor_data),
            'material': (motor_data.get('nozzle_material')
                         or motor_data.get('throat_material')
                         or NOT_AVAILABLE_SPEC),
            'surface_finish': DRAWING_SURFACE_FINISH_NOZZLE,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS
        }

        # Injector drawing
        drawings['injector'] = {
            'plate_diameter': (plate_dia_mm if plate_dia_mm
                               else NOT_AVAILABLE_SPEC),
            'plate_thickness': plate_mm if plate_mm else NOT_AVAILABLE_SPEC,
            'plate_thickness_source': plate_design['source'],
            'plate_material': plate_design['material'] or NOT_AVAILABLE_SPEC,
            # ÖH D15 (defter P9B1-12): koşu enjektör yayımlamıyorsa bunu ADIYLA
            # söyle — katı motorda üç çıktı "enjektör yok" derken 3B montaj
            # 30 mm'lik çelik bir plaka taşıyordu.
            'present_in_this_run': inj_present,
            'not_drawn_reason': None if inj_present else inj_reason,
            'orifice_count': inj['n_orifices'] or NOT_AVAILABLE_SPEC,
            # ÖH D19 (defter P9B1-23): BEYAN TEK YÖNLÜ KALMIŞTI. Ölçüldü
            # (docs/scofield/raw/OH/D19/ihracat/a1/once.json): çizim
            # ``orifice_count = 125`` derken STL'e giden plaka
            # ``MESH_MAX_INJECTOR_ORIFICES = 16`` ile kırpılmış plakaydı;
            # dönen sözlüğün tamamı tarandı, kırpmayı bildiren alan YOKTU
            # (``injector_orifices`` / ``injector_orifices_real`` yalnız
            # üreticinin YEREL kopyasına yazılıyor, çağırana dönmüyor).
            # STL'i açan kişi 16 delik görüp çizimdeki 125'i yanlış sanıyordu.
            # Sınır İKİNCİ KEZ YAZILMAZ: tek tanım noktası modül sabiti.
            'orifice_count_in_mesh': _mesh_orifice_count(inj['n_orifices']),
            'orifice_count_in_mesh_basis': _mesh_orifice_basis(
                inj['n_orifices']),
            # ÖH D33-2 (defter OH-D32-04): sıvı motorun oksitleyici ve
            # yakıt devreleri FARKLI çaptadır (ölçüldü: Ø2,4920 / Ø2,3217
            # mm). Tek çap alanı o koşuda NOT_AVAILABLE yazıyordu — oysa
            # çözücü çapları YAYIMLIYOR; künye gerçeği söylemiyordu. Alan
            # tek çap paylaşılıyorsa SAYI, paylaşılmıyorsa devre başına
            # özet taşır; yapısal liste ``orifice_circuits``tedir.
            'orifice_diameter': (inj['orifice_diameter_mm']
                                 or _injector_circuit_summary(inj['circuits'])
                                 or NOT_AVAILABLE_SPEC),
            'orifice_circuits': [
                {'circuit': c['name'], 'count': int(c['n']),
                 'diameter_mm': float(c['d_mm']),
                 'count_field': c.get('count_field'),
                 'diameter_field': c.get('diameter_field')}
                for c in inj['circuits']],
            'orifice_circuits_not_drilled': list(inj['missing']),
            'injector_type': inj['type'] or NOT_AVAILABLE_SPEC,
            'orifice_source': inj['source'],
            'material': motor_data.get('injector_material') or NOT_AVAILABLE_SPEC,
            'surface_finish': DRAWING_SURFACE_FINISH_INJECTOR,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS
        }
        if pintle_cizim is not None:
            drawings['injector']['pintle'] = pintle_cizim

        return drawings

    def _generate_material_specifications(self, motor_data: Dict) -> Dict:
        """Malzeme spesifikasyonları — kamara kaydı materials_db'den (gerçek).

        Kamara malzemesi yapısal analizde SEÇİLEN kayıttır; özellikleri merkezi
        materials_db'den okunur (eski sürüm kullanıcı ne seçerse seçsin
        'AISI 304' basıyordu). Lüle/enjektör için motor sonucunda malzeme
        seçimi yoksa satır 'reference design' olarak etiketlenir.
        """

        mat_key, mat_name, _rho = _chamber_material(motor_data)
        chamber_spec = None
        if mat_key:
            try:
                rec = get_material(str(mat_key))
                chamber_spec = {
                    'designation': rec.get('name', mat_name),
                    'properties': {
                        'tensile_strength': f"{rec['ultimate_strength'] / 1e6:.0f} MPa",
                        'yield_strength': f"{rec['yield_strength'] / 1e6:.0f} MPa",
                        'density': f"{rec['density'] / 1000.0:.2f} g/cm3",
                        'melting_point': f"{rec.get('melting_point', 'n/a')} K",
                        'thermal_conductivity': f"{rec.get('thermal_conductivity', 'n/a')} W/m K"
                    },
                    'source': rec.get('source', 'hrma materials_db'),
                    'selected_by': 'structural analysis material selection'
                }
            except Exception:
                chamber_spec = None

        specs = {
            'chamber_material': chamber_spec or {
                'designation': NOT_AVAILABLE_SPEC,
                'properties': {},
                'source': 'no material selected in this analysis run'
            },
            # Lüle ve enjektör malzemesi bu analiz koşusunda SEÇİLMİYOR; aşağıdaki
            # kayıtlar merkezi materials_db'den okunan REFERANS tasarımlardır ve
            # 'basis' alanıyla böyle etiketlenir (kullanıcı seçimi değildir).
            'nozzle_material': self._reference_material_spec(
                motor_data.get('nozzle_material') or motor_data.get('throat_material'),
                'graphite'),
            'injector_material': self._reference_material_spec(
                motor_data.get('injector_material'), 'ss_316')
        }

        return specs

    @staticmethod
    def _reference_material_spec(selected_key, default_key) -> Dict:
        """materials_db kaydından spesifikasyon; seçim yoksa referans etiketi."""
        key = selected_key or default_key
        try:
            rec = get_material(str(key))
        except Exception:
            return {'designation': NOT_AVAILABLE_SPEC, 'properties': {},
                    'basis': 'material not found in materials_db'}
        return {
            'designation': rec.get('name', str(key)),
            'properties': {
                'tensile_strength': f"{rec['ultimate_strength'] / 1e6:.0f} MPa",
                'yield_strength': f"{rec['yield_strength'] / 1e6:.0f} MPa",
                'density': f"{rec['density'] / 1000.0:.2f} g/cm3",
                'melting_point': f"{rec.get('melting_point', 'n/a')} K",
                'thermal_conductivity': f"{rec.get('thermal_conductivity', 'n/a')} W/m K"
            },
            'source': rec.get('source', 'hrma materials_db'),
            'basis': ('selected in this analysis run' if selected_key
                      else 'reference design - not selected in this analysis run')
        }

    def _generate_manufacturing_notes(self, motor_data: Dict) -> List[str]:
        """İmalat notları — ölçülü adımlar ÇÖZÜCÜNÜN kendi sonuçlarından.

        Eski sürüm motor_data'yı hiç okumuyordu: 500 N'lik motorla 50 kN'lik
        motorun notları birebir aynı çıkıyordu ("bore to final ID",
        "graphite blank", "1.5x operating pressure"). Komşu fonksiyonlar
        (_generate_technical_drawings, _generate_material_specifications)
        2026-07-19 denetiminde çözücüye bağlanmıştı, bu fonksiyon atlanmıştı.

        Artık gerçek sayı taşıyan adımlar:
          - kamara: gerçek iç çap + yapısal analizin cidar kalınlığı/malzemesi
          - lüle: gerçek boğaz çapı, seçilmişse gerçek lüle malzemesi
          - enjektör: _injector_spec'in delik sayısı/çapı (tek doğruluk kaynağı)
          - basınç testi: gerçek kamara basıncı + yapısal tasarım basıncı
        Değer yoksa sabit sayı yazılmaz, alan NOT_AVAILABLE_SPEC olur. Sayı
        üretilemeyen adımlar bu motora özel hesaplanmaz; sondaki BASIS bloğu
        bunu açıkça söyler (manufacturing_complexity ile aynı desen).
        """

        md = motor_data or {}
        struct = md.get('structural_analysis') or {}

        def _mm(value):
            metres = _real_scalar(value)
            return metres * 1000.0 if metres is not None else None

        chamber_id_mm = _mm(md.get('chamber_diameter'))
        wall_design = _chamber_wall_design(md)
        wall_m = wall_design['thickness_m']
        wall_source = wall_design['source']
        wall_mm = wall_m * 1000.0 if wall_m is not None else None
        _mat_key, chamber_mat, _rho = _chamber_material(md)
        throat_mm = _mm(md.get('throat_diameter'))
        nozzle_mat = md.get('nozzle_material') or md.get('throat_material')
        inj = _injector_spec(md)
        pc_bar = _real_scalar(md.get('chamber_pressure'))
        design_p_bar = _real_nested(struct, ('design_parameters', 'design_pressure'))
        design_factor = _real_nested(struct,
                                     ('design_parameters', 'design_pressure_factor'))

        # 1 - kamara: iç çap ve cidar yapısal analizden gelir
        if chamber_id_mm is not None:
            chamber_note = (
                f"1. Chamber: machine from "
                f"{chamber_mat or 'the chamber material selected in this run'} "
                f"stock; bore to {chamber_id_mm:.1f} mm ID")
            chamber_note += (f", leave {wall_mm:.1f} mm wall ({wall_source})"
                             if wall_mm is not None
                             else f"; wall thickness {NOT_AVAILABLE_SPEC}")
            # v2.6.26 (Y5): tezgâha giden not, çizilen cidar ile yapısal
            # önerinin AYNI OLMADIĞINI söylemeden geçemez. Torna başındaki
            # kişi hangi kalınlığın hangi emniyet katsayısına ait olduğunu
            # görmeden talaş kaldırmamalı.
            if wall_design['note']:
                chamber_note += f". NOTE: {wall_design['note']}"
        else:
            chamber_note = f"1. Chamber: bore diameter {NOT_AVAILABLE_SPEC}"

        # 2 - lüle: boğaz çapı çözücüden; malzeme yalnız SEÇİLDİYSE yazılır
        nozzle_note = (
            f"2. Nozzle: CNC machine from "
            f"{nozzle_mat or 'the nozzle blank material (not selected in this run)'}")
        nozzle_note += (f"; finish throat to {throat_mm:.2f} mm diameter"
                        if throat_mm is not None
                        else f"; throat diameter {NOT_AVAILABLE_SPEC}")
        nozzle_note += f"; throat finish target {DRAWING_SURFACE_FINISH_NOZZLE}"

        # 3 - enjektör: çizim/CAD ile AYNI kaynaktan (bkz. _injector_spec)
        if inj['n_orifices'] and inj['orifice_diameter_mm']:
            injector_note = (
                f"3. Injector: drill {inj['n_orifices']} orifices at "
                f"{inj['orifice_diameter_mm']:.2f} mm diameter and deburr each one; "
                f"face finish target {DRAWING_SURFACE_FINISH_INJECTOR} "
                f"(source: {inj['source']})")
        elif inj['circuits']:
            # ÖH D33-2 (defter OH-D32-04): devreler farklı çaptaysa tezgâha
            # giden not DEVRE BAŞINA yazılır. Eski hâlinde bu koşu
            # "orifice count and diameter NOT AVAILABLE" diyordu — aynı
            # koşunun STEP'i 12 deliği delmişken.
            injector_note = (
                "3. Injector: drill "
                + _injector_circuit_summary(inj['circuits'])
                + f" and deburr each one; face finish target "
                f"{DRAWING_SURFACE_FINISH_INJECTOR} (source: {inj['source']})")
            if inj['missing']:
                injector_note += '. NOTE: ' + '; '.join(inj['missing'])
        else:
            injector_note = (f"3. Injector: orifice count and diameter "
                             f"{NOT_AVAILABLE_SPEC} (source: {inj['source']})")

        # 5 - basınç testi: "1.5x" UYDURMA DEĞİL, yapısal analizin kendi
        # tasarım basıncı yazılır. Test seviyesini seçmek bu yazılımın işi
        # değildir; yalnız hesaplanan basınçlar bildirilir.
        if pc_bar is not None and design_p_bar is not None:
            factor_txt = (f", factor {design_factor:.2f}"
                          if design_factor is not None else "")
            pressure_note = (
                f"5. Pressure test: operating pressure {pc_bar:.1f} bar; the wall "
                f"was sized to {design_p_bar:.1f} bar design pressure{factor_txt} "
                f"by the structural analysis. The proof/burst test level is set by "
                f"the applicable code, not by this analysis.")
        elif pc_bar is not None:
            pressure_note = (
                f"5. Pressure test: operating pressure {pc_bar:.1f} bar; no "
                f"structural design pressure in this run and no proof factor is "
                f"computed here.")
        else:
            pressure_note = f"5. Pressure test level: {NOT_AVAILABLE_SPEC}"

        notes = [
            "MANUFACTURING INSTRUCTIONS:",
            chamber_note,
            nozzle_note,
            injector_note,
            "4. Threads: ANSI B1.1 Class 2A/2B fit",
            pressure_note,
            "",
            "ASSEMBLY SEQUENCE:",
            "1. Install fuel grain in chamber",
            "2. Mount nozzle with high-temp sealant",
            "3. Attach injector with O-ring seal",
            "4. Connect propellant feed lines",
            "5. Perform leak test with nitrogen",
            "",
            "SAFETY REQUIREMENTS:",
            "- Welding per AWS D1.1",
            "- NDT inspection of pressure boundaries",
            "- Hydrostatic test before first firing",
            "- Maintain detailed test records",
            "",
            "BASIS:",
            f"- {MANUFACTURING_NOTE_BASIS}",
            f"- {MANUFACTURING_STANDARD_BASIS}",
            f"- surface finish targets: {DRAWING_SURFACE_FINISH_BASIS}",
        ]

        return notes

    def _generate_cad_performance_summary(self, motor_data: Dict,
                                          assembly_meshes=None) -> Dict:
        """CAD kütle/geometri özeti — kütleler GERÇEK kalınlık ve malzemeden.

        ``assembly_meshes`` verilirse (``generate_3d_motor_assembly`` her zaman
        verir) zarf çapı O KATILARDAN ÖLÇÜLÜR. Verilmezse zarf alanı boş kalır
        ve neden boş olduğu ``max_diameter_basis``te yazar — formülün sonucu
        ``max_diameter_estimate`` alanında, adı tahmin olarak durur
        (ÖH Z5S / defter P9B1-02).
        """

        nozzle_mass = self._estimate_component_mass('nozzle', motor_data)
        chamber_mass = self._estimate_component_mass('chamber', motor_data)
        injector_mass = self._estimate_component_mass('injector', motor_data)
        # ÖH D15 (defter P9B1-18): lüle kütlesinin İKİ girdisi (cidar,
        # yoğunluk) kütleyi hesaplayan yerle AYNI çözümleyicilerden okunur;
        # künye artık kendi dayanaklarını adıyla söyleyebilir.
        _noz_wall_m, _noz_wall_src = _nozzle_wall_design_m(motor_data)
        _noz_rho, _noz_rho_src = _nozzle_density_resolved(motor_data)
        dry_mass = chamber_mass + nozzle_mass + injector_mass

        wall_design = _chamber_wall_design(motor_data)
        wall_m = wall_design['thickness_m']
        wall_source = wall_design['source']
        _key, mat_name, mat_rho, mat_rho_src = _chamber_material_resolved(
            motor_data)
        if mat_rho is None:
            mat_rho_used = get_material(CHAMBER_DENSITY_FALLBACK_KEY)['density']
            mat_rho_src = (f'{mat_rho_src}; the chamber mass above was computed '
                           f'with the {CHAMBER_DENSITY_FALLBACK_KEY} density '
                           f'({mat_rho_used:g} kg/m3) as a NAMED fallback, not '
                           'with a material this run selected')
        else:
            mat_rho_used = mat_rho

        # Bileşenlerden biri geçersizse (eksik/NaN) toplam uzunluk 0 mm DEĞİL
        # None'dır. Eski `or 0.0` yedeği _real_scalar'ın None'ını yutuyor,
        # geçersiz kamara boyu geometri özetinde sessizce 0 mm katkı yapıyordu:
        # kullanıcı 56 mm'lik "toplam boy" görüp bunun hesaplandığını sanıyordu.
        # 'sıfır' ile 'hesaplanamadı' bu projede aynı şey değildir.
        chamber_len_m = _real_scalar(motor_data.get('chamber_length'))
        chamber_d_m = _real_scalar(motor_data.get('chamber_diameter'))
        thrust_n = _real_scalar(motor_data.get('thrust'))
        nozzle_len_m = _nozzle_length_m(motor_data)
        total_length_mm = ((chamber_len_m + nozzle_len_m) * 1000.0
                           if (chamber_len_m is not None and nozzle_len_m is not None)
                           else None)

        # Aynı kural geometri özetinin BÜTÜN alanları için geçerlidir. Eski
        # `motor_data.get('chamber_diameter', 0.1)` kalıbı iki ayrı yoldan
        # yanlış sonuç veriyordu: anahtar hiç yoksa 100 mm çaplı / 500 mm boylu
        # UYDURMA bir motorun hacmini hesaplanmış gibi basıyor, anahtar varken
        # değeri None ise (girdi doğrulamada elenen alanlar) çarpma TypeError
        # ile patlıyordu. Artık geçersiz girdide alan None kalır.
        chamber_volume_cm3 = (
            np.pi * (chamber_d_m / 2.0) ** 2 * chamber_len_m * 1e6
            if (chamber_d_m is not None and chamber_len_m is not None)
            else None)

        # v2.6.26 (Y3): 'max_diameter' kamaranın İÇ çapını yazıyordu. Bu alan
        # gövde tüpü / yük hattı seçimine giren ZARF çapıdır; iç çap yazmak
        # aracı cidar kalınlığının iki katı kadar küçük gösteriyordu (ölçülen
        # koşuda 152,53 mm yerine gerçek 184,37 mm). Zarf, 3B katının
        # KULLANDIĞI cidarla hesaplanır ki mesh ile çelişmesin; lüle çıkışı
        # kamaradan genişse (yüksek genişleme oranı) o kazanır.
        # Zarf KAMARADAN başlar: kamara çapı geçersizse zarf hesaplanamaz ve
        # alan None kalır. (Yalnız lüle çıkışına bakıp sayı üretmek, geçersiz
        # girdide "hesaplanmış" görünen bir çap basmak olurdu.)
        #
        # ÖH Z5S (defter P9B1-02, kritik) — YUKARIDAKİ FORMÜL ARTIK ZARF DEĞİL.
        # Ölçüldü (27 Ağustos 2026): lüle cidarı sonuçta yoksa formül lüleyi
        # zarftan tamamen düşürüyor, ama 3B katı lüleyi yedek cidarla ÇİZMEYE
        # devam ediyordu; yayımlanan 187,015 mm'ye karşılık üretilen katının
        # gerçek zarfı 364,485 mm çıktı (1,949x). Bir formül ile bir katı
        # birbirini tutmadığında imalata giden sayı KATININ sayısıdır.
        # Bu yüzden ``max_diameter`` yalnız ÖLÇÜLDÜĞÜNDE basılır; formülün
        # sonucu ayrı ve adı "tahmin" olan bir alanda kalır.
        env_wall_m, env_wall_src = _chamber_wall_effective_m(motor_data, chamber_d_m)
        if chamber_d_m is None or env_wall_m is None:
            max_diameter_estimate_mm = None
        else:
            chamber_outer_mm = (chamber_d_m + 2.0 * env_wall_m) * 1000.0
            exit_d_m = _real_scalar(motor_data.get('exit_diameter'))
            noz_wall_m = _real_scalar((motor_data.get('nozzle_geometry') or {})
                                      .get('wall_thickness'))
            noz_wall_m = (noz_wall_m / 1000.0) if noz_wall_m is not None else None
            # Lülenin en geniş yeri ÇIKIŞ değil, çoğu tasarımda KONVERJAN
            # GİRİŞİdir (kamara çapında başlar). Yalnız çıkışa bakan eski
            # hesap, düşük genişleme oranlı motorlarda zarfı olduğundan küçük
            # gösteriyordu: ölçülen koşuda 162,53 mm yazıyordu, katının gerçek
            # zarfı 168,11 mm idi (lüle mesh'i kamaradan genişti). Kontur
            # örneklenebiliyorsa zarf ONDAN okunur — böylece sayı, çizilen
            # katıyla tanım gereği aynı olur.
            noz_max_r_m = None
            try:
                _pts_mm, _meta = sample_nozzle_inner_contour(motor_data)
                if _pts_mm:
                    noz_max_r_m = max(r for _z, r in _pts_mm) / 1000.0
            except Exception:
                noz_max_r_m = None
            if noz_max_r_m is None:
                _cands = [d for d in (exit_d_m, chamber_d_m) if d is not None]
                noz_max_r_m = (max(_cands) / 2.0) if _cands else None
            nozzle_outer_mm = ((noz_max_r_m + noz_wall_m) * 2.0 * 1000.0
                               if (noz_max_r_m is not None and noz_wall_m is not None)
                               else None)
            max_diameter_estimate_mm = max(
                v for v in (chamber_outer_mm, nozzle_outer_mm) if v is not None)

        max_diameter_mm, max_diameter_basis = _measured_envelope_diameter_mm(
            assembly_meshes)
        # ÖH D19 (P15B4-11): boy da zarf çapıyla AYNI kuralla yayımlanır —
        # ÖLÇÜLEN katıdan; formülün sonucu adı "tahmin" olan alanda kalır.
        measured_length_mm, total_length_basis = _measured_envelope_length_mm(
            assembly_meshes)
        # ÖH D25 / defter OH-D24-10 (zincir P15B4-11): künye ÖN KAPAĞI ANAR.
        #
        # ÖLÇÜLDÜ (taban ``cdf2106``, ``once.json`` bölüm MC): künye
        # "... including the forward closure ..." diyordu ama kapağın
        # kalınlığının NEREDEN geldiğini söylemiyordu. Aynı yanıtın
        # ``technical_drawings.chamber.front_cap_thickness_source`` alanı
        # katıda 15,18 mm'yi "structural analysis (flat closure head ...)"
        # ile, kapak analizi olmayan koşumda ise ``CAP_FALLBACK_BASIS`` ile
        # (1,6 x cidar, taban 8 mm — ÜRETEÇ VARSAYIMI) künyeliyor. Ölçülen
        # boy o kalınlığı İÇERDİĞİ için, boyun künyesi kapağın künyesini
        # anmadığında okuyucu ÖLÇÜLEN bir sayının içinde bir VARSAYIM
        # taşındığını göremiyordu (üç motorda da
        # ``basis_kapak_kaynagini_aniyor = false``).
        #
        # Kaynak METNİ üretilmez, çizim sözlüğüyle AYNI tek kaynaktan
        # (``_front_cap_design``) AYNI girdilerle okunur; iki künye
        # ayrışamaz. Kapak çözülemiyorsa ek cümle yazılmaz (uydurma yok).
        if measured_length_mm is not None:
            try:
                _cap = _front_cap_design(
                    motor_data,
                    wall_mm=(wall_m * 1000.0) if wall_m else None,
                    bore_radius_mm=((chamber_d_m or 0.0) * 1000.0 / 2.0)
                    or None)
            except Exception:
                _cap = None
            if isinstance(_cap, dict) and _cap.get('source'):
                total_length_basis += (
                    ' The forward closure included in this envelope is '
                    'drawn at the thickness published as '
                    'technical_drawings.chamber.front_cap_thickness'
                    + (' = %.4f mm' % _cap['thickness_mm']
                       if _cap.get('thickness_mm') is not None else '')
                    + ', whose basis (front_cap_thickness_source) is: '
                    + str(_cap['source']) + '.')

        return {
            'geometry_summary': {
                # mm — ÜRETİLEN KATIDAN ÖLÇÜLMÜŞ (None = katı yok).
                'total_length': measured_length_mm,
                'total_length_basis': total_length_basis,
                # Formülün sonucu KAYBOLMAZ ama adı "boy" değil "tahmin"dir.
                'total_length_estimate': total_length_mm,  # mm
                'total_length_estimate_basis': (
                    'ESTIMATE, not the axial envelope of the drawn solid: '
                    'chamber_length + nozzle length, which EXCLUDES the '
                    'forward closure (end cap) that the 3D assembly actually '
                    'draws. The motor publishes its own definitions in '
                    'design_summary.key_dimensions '
                    '(total_motor_length_chamber_nozzle_mm and '
                    'total_motor_length_with_caps_mm, see '
                    'total_motor_length_basis); this estimate is the CAD '
                    'layer\'s own sum and is not guaranteed to equal either '
                    f'of them. Chamber length from '
                    f'{motor_data.get("chamber_length_source")!r}.'),
                # ZARF (dış) çapı — ÜRETİLEN KATIDAN ÖLÇÜLMÜŞ. Katı yoksa
                # None: bu alan gövde tüpü seçimine girer, tahmin basılmaz.
                'max_diameter': max_diameter_mm,  # mm
                'max_diameter_basis': max_diameter_basis,
                # Formülün sonucu KAYBOLMAZ ama adı "zarf" değil "tahmin"dir.
                'max_diameter_estimate': max_diameter_estimate_mm,  # mm
                'max_diameter_estimate_basis': (
                    'ESTIMATE, not the envelope of the drawn solid: '
                    'max(chamber bore + 2 x wall, nozzle max contour radius x 2 '
                    '+ 2 x nozzle wall). The nozzle term is dropped entirely '
                    'when this run publishes no nozzle wall thickness, so the '
                    'estimate can fall well below the solid it accompanies; '
                    f'chamber wall from {env_wall_src}'),
                'chamber_bore_diameter': ((chamber_d_m * 1000.0)
                                          if chamber_d_m is not None else None),  # mm
                # ÖH Z5S (P9B1-05 / P9B1-06): çizilen boyun kaynağı ve
                # tanenin neden çizilmediği sayının yanında durur.
                'chamber_length_source': motor_data.get('chamber_length_source'),
                'grain_not_drawn_reason': motor_data.get('grain_not_drawn_reason'),
                'chamber_volume': chamber_volume_cm3,  # cm3
                'thrust_to_weight': (thrust_n / (dry_mass * G_0)
                                     if (thrust_n is not None and dry_mass > 0)
                                     else None),
                # ÖH D29 (defter P15B4-12): CİDAR KALINLIĞI UZUNLUKTUR.
                #
                # ÖLÇÜLDÜ (D28 fea-cfd a2, ``once_p15b412.json``; D29 ihracat
                # a1'de tabana karşı yeniden ölçüldü): adı kütle vaat eden
                # ``mass_breakdown`` sözlüğünün 9 sayısal alanının 5'i kütle
                # DEĞİLDİ — 3 uzunluk (mm) + 2 yoğunluk (kg/m3). Okuyucu
                # "kütle dökümü" başlığı altında milimetre buluyordu; sayılar
                # dürüsttü, yerleşim yanlıştı.
                #
                # Onarım: sayı ve KÜNYESİ birlikte kendi boyut sözlüğüne
                # taşındı, ``mass_breakdown``ta kopya BIRAKILMADI (tek
                # kaynak). Değerler kütleyi hesaplayan AYNI çözümleyicilerden
                # gelir (``_chamber_wall_design`` / ``_nozzle_wall_design_m``),
                # yani girdinin ta kendisidir — ikinci bir hesap değil.
                'wall_thickness_mm': (wall_m * 1000.0) if wall_m else None,
                'wall_thickness_source': wall_source,
                'wall_thickness_recommended_mm': wall_design['recommended_mm'],
                'wall_thickness_note': wall_design['note'],
                'nozzle_wall_thickness_mm': _noz_wall_m * 1000.0,
                'nozzle_wall_thickness_source': _noz_wall_src,
            },
            'mass_breakdown': {
                'chamber_mass': chamber_mass,  # kg
                'nozzle_mass': nozzle_mass,  # kg
                'injector_mass': injector_mass,  # kg
                'total_dry_mass': dry_mass,  # kg
                # H4-7: bu toplam motorun TAM kuru kütlesi DEĞİLDİR — kapaklar
                # (uç tıpalar) burada yok, yapısal analizin toplamında var.
                # Ölçüldü (2 kN hibrit): burası 13,7130 kg,
                # structural_analysis...total_weight 16,8366 kg (%22,8 fark) ve
                # ikisi de "kuru kütle" adıyla yayımlanıyordu. Kapsam artık
                # sayının yanında yazar; .eng dosyası da farkı beyan eder
                # (openrocket_integration.dry_mass_reconciliation).
                'total_dry_mass_scope': (
                    'chamber + as-drawn nozzle + injector plate. Closures / '
                    'end caps are NOT included here; the structural weight '
                    'analysis reports them and its total is what the .eng '
                    'export writes.'),
                # Lülenin OTORİTATİF kütlesi budur: çizilen katının kesik koni
                # halkası hacmi V = pi(2*t*r_ort + t^2)*L. Formül Faz 4'te Lean
                # ile ispatlandı (docs/BICIMSEL_ISPATLAR.md,
                # HRMA.frustumAnnulusVolume_eq_integral). Aynı sonuçtaki diğer
                # iki lüle kütlesi YAKLAŞIMDIR ve kaynağında öyle beyanlıdır:
                # structural %30 başparmak kuralı, nozzle_design yalnız
                # diverjan koni.
                # ÖH D15 (defter P9B1-18): "AUTHORITATIVE" sözcüğü kullanıcıya
                # bu sayıyı diğer iki tahmine TERCİH ETMESİNİ söylüyor. Cümle
                # doğruydu (STL de aynı cidarı kullanır) ama cidarın ve
                # malzemenin O KOŞUDA HESAPLANMADIĞINI söylemiyordu: ölçüldü,
                # katı ve sıvıda ``nozzle_geometry`` boş, ``nozzle_material``
                # yok -> cidar üreteç kuralından (3,66 / 3,08 mm), yoğunluk
                # sessizce grafitten geliyordu. Künye artık kendi iki
                # girdisinin kaynağını ADIYLA taşır.
                'nozzle_mass_basis': (
                    'AUTHORITATIVE for the AS-DRAWN solid: frustum-annulus '
                    'volume V = pi(2*t*r_mid + t^2)*L with the same contour, '
                    'wall and material as the STEP/STL parts; formula formally '
                    '(docs/BICIMSEL_ISPATLAR.md). The rule-of-thumb nozzle '
                    'weight in structural_analysis and the divergent-cone-only '
                    'estimate in nozzle_design are approximations, not this. '
                    f'Wall used: {_noz_wall_src}. Density used: '
                    f'{_noz_rho_src}.'),
                # Kütleler GERÇEK geometri x yoğunluk ile hesaplanır; kaba
                # oranlarla (ör. itergaç kütlesinin %25'i) DEĞİL.
                'mass_basis': ('solid geometry x material density from '
                               'materials_db (chamber: pi x L x (r_out^2 - '
                               'r_in^2); injector: plate disc minus orifices)'),
                # ÖH D29 (defter P15B4-12): bu sözlük yalnız KÜTLE taşır.
                # Kütleyi üreten uzunluk ve yoğunluk girdileri kaldırılmadı,
                # KENDİ boyut sözlüklerine taşındı; okuyucu nereye bakacağını
                # burada ADIYLA görür (kopya değil, yön tarifi).
                'mass_inputs_note': (
                    'This dictionary carries MASS ONLY (kg). The lengths and '
                    'densities these masses were computed from are published, '
                    'each with its own source, in the sibling dictionaries of '
                    'this same performance_summary: '
                    'geometry_summary.wall_thickness_mm, '
                    'geometry_summary.wall_thickness_source, '
                    'geometry_summary.wall_thickness_recommended_mm, '
                    'geometry_summary.wall_thickness_note, '
                    'geometry_summary.nozzle_wall_thickness_mm, '
                    'geometry_summary.nozzle_wall_thickness_source, '
                    'material_summary.chamber_material, '
                    'material_summary.chamber_mass_density_kg_m3, '
                    'material_summary.chamber_mass_density_source, '
                    'material_summary.nozzle_mass_density_kg_m3, '
                    'material_summary.nozzle_mass_density_source. Those are '
                    'the SAME values this computation used, not a second copy '
                    'computed elsewhere.'),
            },
            # ÖH D29 (defter P15B4-12): kütlenin GERÇEKTEN kullandığı
            # yoğunluklar ve malzeme adı. Üst düzeydeki
            # ``material_specifications`` malzeme KATALOĞUDUR (materials_db
            # kaydı, g/cm3 biçimli metin); burası o koşuda kütle hesabına
            # GİREN sayıdır ve ikisi AYRIŞABİLİR — malzeme çözülemediğinde
            # kütle adlı bir yedek yoğunlukla hesaplanır ve bunu
            # ``chamber_mass_density_source`` söyler. Bu yüzden kopya değil,
            # ayrı bir gerçektir.
            'material_summary': {
                'chamber_material': mat_name or NOT_AVAILABLE_SPEC,
                # ÖH D15 (defter P9B1-14): kütlenin gerçekten kullandığı
                # yoğunluk ve NEREDEN geldiği sayının yanında durur.
                'chamber_mass_density_kg_m3': mat_rho_used,
                'chamber_mass_density_source': mat_rho_src,
                'nozzle_mass_density_kg_m3': _noz_rho,
                'nozzle_mass_density_source': _noz_rho_src,
                'density_scope': (
                    'The densities the mass_breakdown masses were actually '
                    'computed with. material_specifications (top level of '
                    'the CAD design) is the materials_db catalogue entry and '
                    'can differ from these when this run fell back to a '
                    'NAMED default density instead of a material it '
                    'selected.'),
            },
            'manufacturing_complexity': {
                # v2.6.26 (P4) KALDIRILDI: 'machining_time': '24-48 hours' ve
                # 'assembly_time': '4-6 hours'. Bunlar TERMİNDİR ve V2.6.26
                # planı §2.2 gereği kapsam dışıdır: HRMA'nın ne tezgâh saati
                # verisi ne iş gücü modeli var; iki sayı da 500 N'lik motorla
                # 50 kN'lik motorda aynıydı. Sıvı motor tarafında aynı karar
                # MANUFACTURING_COST_STATUS ile uygulanmıştı; arayüz boş hücre
                # yerine bu durumu basabilsin diye alanın yokluğu bildirilir.
                'effort_status': MANUFACTURING_EFFORT_STATUS,
                'skill_level': 'Advanced machinist required',
                'special_tooling': 'Diamond boring bar for nozzle',
                'basis': MANUFACTURING_EFFORT_BASIS
            }
        }

    def _estimate_component_mass(self, component: str, motor_data: Dict) -> float:
        """Bileşen kütlesi — GERÇEK cidar kalınlığı ve GERÇEK malzeme yoğunluğu.

        Eski sürüm kamara kütlesini sabit 5 mm cidar + sabit 7850 kg/m^3 ile
        hesaplıyordu; aynı motor sonucunda yapısal analizin önerdiği kalınlık
        (ör. 20 kN motorda 29 mm) hazır dururken kütle 5 kata kadar sapıyor,
        buradan türeyen total_dry_mass ve thrust_to_weight de yanlış çıkıyordu
        (2026-07-19 denetimi, kritik bulgu).

        Kalınlık/yoğunluk yoksa CAD katmanının 3B meshte kullandığı AYNI
        yedek kural uygulanır (0.045·D_ch) — böylece görsel ile kütle çelişmez.
        """

        chamber_d = _real_scalar(motor_data.get('chamber_diameter')) or 0.1
        # 3B mesh, zarf çapı ve kütle TEK fonksiyondan okur (yedek kural dahil)
        wall_m, _src = _chamber_wall_effective_m(motor_data, chamber_d)
        _key, _name, density, _rho_src = _chamber_material_resolved(motor_data)
        if density is None:
            # ÖH D15 (defter P9B1-14): yedek KALIR ama artık SESSİZ değil —
            # ``mass_breakdown.chamber_mass_density_source`` hangi yoğunluğun
            # kullanıldığını ve seçilen malzemeden gelmediğini yazar.
            density = get_material(CHAMBER_DENSITY_FALLBACK_KEY)['density']

        if component == 'chamber':
            # Yapısal analizle AYNI hacim modeli: cidar iç çapın DIŞINA eklenir
            # (structural_analysis._calculate_weight ile birebir tutarlı).
            inner_r = chamber_d / 2
            outer_r = inner_r + wall_m
            length = _real_scalar(motor_data.get('chamber_length')) or 0.5
            volume = np.pi * length * (outer_r**2 - inner_r**2)
            return volume * density

        elif component == 'nozzle':
            # v2.6.26: kütle ÇİZİLEN katıdan gelir — aynı iç kontur, aynı
            # cidar, aynı malzeme (bkz. _nozzle_solid). İki ayrı kusur vardı:
            #
            # (O3) Çözücü, lüle cidar malzemesi verilmediğinde sessizce ÇELİĞE
            #      düşüyor ve kütleyi 7850 kg/m³ ile hesaplıyordu. Kullanıcı
            #      grafit seçtiğinde motor sonucunda nozzle_material='graphite'
            #      yazıyor ama kütle çelikten geliyordu (4,36 kat fazla;
            #      tungstende 2,46 kat az).
            # (kapsam) Çözücünün estimated_mass'i YALNIZ diverjan koninin
            #      yüzeyini sayar; CAD katısı konverjanı da içerir. Ölçüldü:
            #      çözücü 0,03885 kg derken katının gerçek kabuğu 0,08948 kg
            #      (2,30 kat) — yani "kütle dökümü" çizilen parçaya ait değildi.
            #
            # Kontur bu koşuda örneklenemezse (eksik geometri) çözücünün değeri
            # yoğunluk düzeltmesiyle kullanılır; o da yoksa yapısal tahmin.
            noz_geo = motor_data.get('nozzle_geometry') or {}
            selected_key = (motor_data.get('nozzle_material')
                            or motor_data.get('throat_material'))
            # TEK KAYNAK (ÖH D15 / P9B1-18): cidar ve yoğunluk artık modül
            # düzeyindeki iki çözümleyiciden gelir; künyeyi basan özet de
            # AYNI ikisini okur, böylece "AUTHORITATIVE" cümlesi kendi
            # girdilerinin kaynağını doğru söyleyebilir.
            density_noz, noz_mat_src = _nozzle_density_resolved(motor_data)
            try:
                # V301 bilinen C1: iç kontur ve et STL/STEP ile TEK
                # kaynaktan (``nozzle_wall_profile``). Halka, profilin
                # kuralıyla aynıdır (dış = iç + et, aynı istasyonda); hacim
                # doğrusal parçalarda TAM integral olarak iç kontur ve etten
                # yazılır (kayan noktada önceki hesapla BİT-AYNI).
                _noz_profile = nozzle_wall_profile(motor_data, unit='mm')
                pts_mm = _noz_profile['inner']
                wall_noz = _noz_profile['wall_design']['thickness_m']
                # Cidar iç kontura DIŞARI eklenir (``nozzle_wall_profile``:
                # `outer = [(z, r + wall) ...]`), yani halka hacmi
                # pi*((r+t)^2 - r^2)*dz = pi*(2*r*t + t^2)*dz.
                # Eski hesap kabuğu konturun ORTASINA koyup yalnız 2*pi*r*t*dz
                # sayıyordu; pi*t^2*dz terimi düşüyordu. İnce cidarda fark
                # ihmal edilebilir ama cidar kalınlaşınca büyür (oran
                # 1 + t/(2r)): ölçülen koşuda t=7,79 mm ile kütle 0,694 kg
                # çıkıyordu, çizilen katı 0,751 kg idi (%7,7 eksik).
                volume = 0.0
                for (z0, r0), (z1, r1) in zip(pts_mm[:-1], pts_mm[1:]):
                    dz = (z1 - z0) / 1000.0
                    r_mid = (r0 + r1) / 2000.0
                    volume += np.pi * ((r_mid + wall_noz) ** 2 - r_mid ** 2) * abs(dz)
                if volume > 0:
                    return volume * density_noz
            except Exception:
                pass

            mass = _real_scalar(noz_geo.get('estimated_mass'))
            if mass is not None:
                # Geometri (yüzey x kalınlık) doğru olduğundan yoğunluk
                # oranıyla ÖLÇEKLEMEK tam düzeltmedir — yeni bir sayı
                # uydurulmaz, yanlış yoğunluk düzeltilir.
                used_rho = _real_scalar(noz_geo.get('wall_material_density'))
                if used_rho is not None and abs(density_noz - used_rho) > 1.0:
                    return mass * (density_noz / used_rho)
                return mass
            struct_noz = _real_nested(motor_data.get('structural_analysis') or {},
                                      ('weight_analysis', 'nozzle_weight'))
            if struct_noz is not None:
                return struct_noz
            return 0.0

        elif component == 'injector':
            # ÖH D15 (defter P9B1-12): koşuda enjektör yoksa TARTILMAZ da.
            # Kütle dökümü eskiden süzgeçten ÖNCE üretildiği için katı motorun
            # kuru kütlesinin %10,96'sı var olmayan bir plakadandı.
            present, _reason = _injector_evidence(motor_data)
            if not present:
                return 0.0

            # ÖH D15 (defter P9B1-13): kalınlık/yarıçap mesh ile AYNI kaynaktan
            plate = _injector_plate_design(motor_data, chamber_d)
            if plate['mass_kg'] is not None:
                # Enjektör çözücüsünün kendi plaka kütlesi OTORİTATİFTİR:
                # plakanın malzemesi (ör. ss_316) kamara malzemesinden
                # farklıdır; kamara yoğunluğuyla tartmak yanlış sayı üretir.
                return plate['mass_kg']
            plate_m = plate['thickness_m']
            radius = plate['radius_m']
            if not plate_m or not radius:
                return 0.0
            # Orifis deliklerinin çıkardığı hacim GERÇEK delik sayısı/çapından
            inj = _injector_spec(motor_data)
            hole_volume = 0.0
            # ÖH D33-2 (defter OH-D32-04): devre başına çap ayrı olabilir;
            # tek çapla tartmak yanlış kütle verirdi.
            for _c in inj['circuits']:
                r_hole = float(_c['d_mm']) / 2000.0
                hole_volume += int(_c['n']) * np.pi * r_hole**2 * plate_m
            volume = max(0.0, np.pi * radius**2 * plate_m - hole_volume)
            return volume * density

        return 0.0

    #: STL dosyalarının birimi. STL formatının birim başlığı YOKTUR; CAD ve
    #: dilimleyici yazılımların fiili sözleşmesi milimetredir ve bu projenin
    #: STEP çıktısı da (AP214) mm'dir. Mesh'ler ise METRE ile kurulur, bu
    #: yüzden dışa aktarımda ölçeklenirler.
    #: Faz 4B / A1 — ölçülen kusur: aynı ZIP'te STEP zarfı 1069.62 mm iken
    #: STL zarfı 1.0696 (metre) idi; README ve ZIP manifesti "mm" diyordu.
    #: 1000× birim hatası, kapatılmış tank STEP hatasının aynı sınıfı.
    STL_UNITS_PER_METRE = 1000.0

    def export_stl_files(self, assembly_meshes: List, output_dir: str = None):
        """Export STL files for 3D printing/machining.

        BİRİM SÖZLEŞMESİ (A1): dosyalar MİLİMETRE yazılır — STEP ile aynı.
        Mesh'ler metre kurulduğu için dışa aktarımda ``STL_UNITS_PER_METRE``
        ile ölçeklenmiş bir KOPYA yazılır; çağıranın mesh nesneleri (Plotly
        görselleştirmesi ve kütle dökümü aynı nesneleri kullanır) DEĞİŞMEZ.

        YOL SÖZLEŞMESİ (A10): dönen liste MUTLAK dosya yollarıdır ve gerçekten
        yazılan dosyaları gösterir; ilk eleman varsa birleşik
        ``motor_assembly.stl``tir. Çağıran bu yolları kullanmalıdır — sabit
        bir dizinden (``cwd/cad_exports``) okumak yanlış/eski dosya sunar.

        v2.6.26 — İSTEKLER ARASI KİRLENME KAPATILDI.

        Varsayılan çıktı dizini ``./cad_exports/`` idi ve dosya adları
        sabitti (``motor_assembly.stl``, ``chamber.stl`` ...). Uç nokta
        dosyayı diskten GERİ OKUDUĞU için iki eşzamanlı istek aynı yola
        yazıyor ve biri diğerinin geometrisini indiriyordu. ÖLÇÜLDÜ: iki
        farklı motorla (Ø120/L1000 ve Ø300/L2000) altı eşzamanlı denemenin
        ikisinde A isteği HTTP 200 ile B'nin STL'ini aldı. Üretimde sunucu
        8 iş parçacığıyla çalışıyor (``packaging/launcher.py``), yani bu
        teorik bir yarış değil.

        Artık her çağrı kendi geçici dizinine yazar. Çağıran dosyayı
        okuduktan sonra dizini silmelidir (``shutil.rmtree``); silmezse
        işletim sistemi geçici dizin temizliğinde alır.

        ``output_dir`` açıkça verilirse (ör. kullanıcının seçtiği bir klasöre
        toplu dışa aktarım) o kullanılır — davranış değişmez.
        """

        import os
        from hrma.export.export_workspace import (
            atomic_produce, new_workspace, purge_stale_workspaces)
        if output_dir is None:
            purge_stale_workspaces()  # D10: çökme sonrası kalanları topla
            output_dir = new_workspace('hrma_stl_')
        else:
            os.makedirs(output_dir, exist_ok=True)
        output_dir = os.path.abspath(output_dir)

        exported_files = []
        valid_meshes = []

        from hrma.export.motor_geometry import EXPORT_AXIS, MESH_BUILD_AXIS

        #: Bellek içi +Z mesh'ini paketin +X sözleşmesine çeviren 4x4 dönme
        #: (+Y ekseni etrafında +90 derece): (x, y, z) -> (z, y, -x).
        #: ÖH V3 CAD A2: tank STL'si de aynı matrisi okur (tek kaynak).
        _EKSEN_DONMESI = export_axis_rotation()

        def _mm(mesh):
            """Mesh'in MİLİMETRE ölçekli, +X eksenine çevrilmiş KOPYASI.

            BİRİM (A1): mesh'ler metre kurulur, dosya milimetre yazılır.

            EKSEN (ÖH D26 / defter P15B4-01): mesh'ler +Z ekseninde kurulur,
            aynı paketteki STEP katıları +X ekseninde döner. ÖLÇÜLDÜ (taban
            7751531, ``raw/OH/D26/ihracat/a1/once.json`` -> ``P15B4-01``):
            üç motor tipinin BEŞ parçasında STEP ve STL zarfları birebir aynı
            sayıları TERS SIRADA taşıyordu (hibrit chamber STEP
            346,837/227,815/227,815 <-> STL 227,815/227,815/346,837); yani
            iki dosya 90° dönüktü ve paketin hiçbir künyesinde eksen adı
            geçmiyordu. Dosyaya yazılan kopya artık paketin TEK sözleşmesine
            (``motor_geometry.EXPORT_AXIS`` = +X) çevrilir.

            Kopya şart: aynı nesneler Plotly görselleştirmesinde, kütle
            dökümünde ve ``_measured_envelope_length_mm`` zarf ölçümünde
            kullanılıyor (o ölçüm kendi sözüyle "assembly axis is z"); yerinde
            ölçekleyip döndürmek onları da bozardı.
            """
            scaled = mesh.copy()
            scaled.apply_scale(self.STL_UNITS_PER_METRE)
            if EXPORT_AXIS != MESH_BUILD_AXIS:
                scaled.apply_transform(_EKSEN_DONMESI)
            return scaled

        try:
            # First export individual components
            for name, mesh in assembly_meshes:
                if mesh is not None and hasattr(mesh, 'export'):
                    filename = os.path.join(
                        output_dir, f"{name.lower().replace(' ', '_')}.stl")
                    try:
                        mesh_mm = _mm(mesh)
                        # Atomik yazma (D1): yarım STL indirilmesin.
                        atomic_produce(filename, mesh_mm.export)
                        exported_files.append(filename)
                        valid_meshes.append(mesh_mm)
                        print(f"Successfully exported: {filename}")
                    except Exception as e:
                        # OPUS DENETİM DÜZELTMESİ: eski kod hata durumunda
                        # SESSİZCE tek-üçgenlik sahte STL yazıyordu — bozuk
                        # çıktı geçerli exportmuş gibi pakete giriyordu.
                        # Artık hata yükseltilir; endpoint kullanıcıya raporlar.
                        raise RuntimeError(
                            f"{name} STL export başarısız: {e}") from e
                else:
                    print(f"Warning: Invalid mesh for {name}")

            # Create combined motor assembly STL
            if valid_meshes:
                try:
                    import trimesh.util
                    # valid_meshes ZATEN mm ölçekli kopyalardır (bkz. _mm)
                    combined_mesh = trimesh.util.concatenate(valid_meshes)
                    assembly_filename = os.path.join(output_dir,
                                                     'motor_assembly.stl')
                    atomic_produce(assembly_filename, combined_mesh.export)
                    exported_files.append(assembly_filename)
                    print(f"Successfully exported combined assembly: {assembly_filename}")
                except Exception as e:
                    # Birleşik assembly üretilemezse sahte STL YAZILMAZ —
                    # bileşen dosyaları geçerliyse onlarla devam edilir,
                    # hiçbiri yoksa hata yükseltilir (aşağıda).
                    print(f"Error creating combined assembly: {str(e)}")

        except RuntimeError:
            raise
        except Exception as e:
            # OPUS DENETİM DÜZELTMESİ: eski catch-all, tek-üçgenlik sahte
            # STL yazıp başarı gibi dönüyordu. Bozuk çıktı üretmek yasak.
            raise RuntimeError(f"STL export başarısız: {e}") from e

        if not exported_files:
            raise RuntimeError("STL export başarısız: geçerli mesh üretilemedi")

        # Ensure motor_assembly.stl is first in the list if it exists
        motor_assembly_files = [f for f in exported_files if 'motor_assembly' in f.lower()]
        other_files = [f for f in exported_files if 'motor_assembly' not in f.lower()]

        if motor_assembly_files:
            exported_files = motor_assembly_files + other_files

        return exported_files

# =============================================================================
# DetailedCADGenerator - Engineering Cross-Section Views (Plotly)
# Originally from detailed_cad_generator.py
# =============================================================================

def _cross_section_basis(motor_data):
    """Sıvı kesit görünümünün TEK doğruluk kaynağı (ÖH Z5S / P09-A).

    Kesitte çizilen üç tekrarlı büyüklük (kamara cidarı, soğutma kanalı sayısı,
    enjektör deliği sayısı) eskiden ÜÇ AYRI SABİTTEN geliyordu — sırasıyla
    ``0.008`` m, ``24`` ve ``motor_data['injector_holes']`` (arayüz sabiti,
    varsayılan 24). Ölçüldü (27 Ağustos 2026, sıvı kesit koşumu): çözücü 5 mm
    cidar / 80 kanal / 41 eleman raporlarken kesit 8 mm cidar / 24 kanal /
    24 delik çizdi; çözücü hiçbir şey üretmediği koşumda bileşen tablosu üç
    alana da "NOT AVAILABLE" derken kesit yine AYNI üç sabiti çizdi.

    Artık üçü de bu tek sözlükten okunur ve sözlük çıktıya da yayımlanır
    (``generate_liquid_motor_cad()['cross_section_basis']``), böylece
    ÇİZİLEN ile YAYIMLANAN sayı ayrışamaz.

    Anahtarlar:
        chamber_wall_thickness_m / _mm -> çizilecek cidar (None = çizilmez)
        chamber_wall_source            -> cidarın künyesi
        cooling_channels_solver        -> çözücünün kanal sayısı (None olabilir)
        cooling_channels_drawn         -> çizilen kanal sayısı (kırpılmış olabilir)
        cooling_channels_source        -> künye
        injector_holes_solver / _drawn / _source -> aynı desen
        injector_pattern / _source     -> hangi delik deseni çizildi ve neden
    """
    md = motor_data or {}

    wall_design = _chamber_wall_design(md)
    wall_m = wall_design['thickness_m']
    wall_src = (wall_design['source'] if wall_m is not None
                else 'not available: this analysis run publishes no chamber '
                     'wall thickness, so no wall is drawn')

    channels = _solver_cooling_channel_count(md)
    if channels is None:
        channels_drawn = 0
        channels_src = ('not available: this analysis run publishes no cooling '
                        'channel count (cooling_system.cooling_channels), so '
                        'no channels are drawn')
    elif channels > CROSS_SECTION_MAX_CHANNELS:
        channels_drawn = CROSS_SECTION_MAX_CHANNELS
        channels_src = (f'solver cooling_system: {channels} channels; only '
                        f'{CROSS_SECTION_MAX_CHANNELS} are DRAWN (render limit)')
    else:
        channels_drawn = channels
        channels_src = f'solver cooling_system: {channels} channels'

    holes = _solver_injector_element_count(md)
    if holes is None:
        holes_drawn = 0
        holes_src = ('not available: this analysis run publishes no injector '
                     'element count (injector_design.number_of_elements / '
                     'number_of_orifices). The interface constant '
                     '"injector_holes" is NOT a design result and is not read')
    elif holes > CROSS_SECTION_MAX_INJECTOR_HOLES:
        holes_drawn = CROSS_SECTION_MAX_INJECTOR_HOLES
        holes_src = (f'solver injector_design: {holes} elements; only '
                     f'{CROSS_SECTION_MAX_INJECTOR_HOLES} are DRAWN '
                     '(render limit)')
    else:
        holes_drawn = holes
        holes_src = f'solver injector_design: {holes} elements'

    inj_design = md.get('injector_design') or {}
    pattern = inj_design.get('injector_type') or md.get('injector_type')
    if isinstance(pattern, str) and pattern.strip():
        pattern = pattern.strip()
        pattern_src = ('solver injector_design.injector_type'
                       if inj_design.get('injector_type')
                       else 'request injector_type')
    else:
        pattern = 'unlike_impinging'
        pattern_src = ('ASSUMED unlike-impinging pattern: this analysis run '
                       'names no injector type, so the hole layout is a '
                       'drawing assumption and not a design result')

    return {
        'chamber_wall_thickness_m': wall_m,
        'chamber_wall_thickness_mm': (wall_m * 1000.0) if wall_m is not None
                                     else None,
        'chamber_wall_source': wall_src,
        'cooling_channels_solver': channels,
        'cooling_channels_drawn': channels_drawn,
        'cooling_channels_source': channels_src,
        'injector_holes_solver': holes,
        'injector_holes_drawn': holes_drawn,
        'injector_holes_source': holes_src,
        'injector_pattern': pattern,
        'injector_pattern_source': pattern_src,
    }


class DetailedCADGenerator:
    """Generate detailed engineering CAD visualizations for rocket motors.

    ÖH D37 A1a sahne-sahte-veri (CM-S2) — SABİT PARÇA ÇİZİLMEZ.
    Kusur: sıvı "Engineering CAD View" dış görünüşü hiçbir yanıt alanında
    olmayan ölçülerle beş parça grubu çiziyordu — 50 mm enjektör kafası
    (Ø+20 mm), Ø+40 mm × 0,8·L soğutma ceketi, 15/12 mm besleme hatları
    (0,3·L / 0,7·L), Ø+40 mm × 20 mm iki flanş + 16 cıvata ve iki basınç
    sensörü; dış lüle konturu %30/%70 görüntü kesriyle bölünüyor, kesitte
    kanallar 3 mm sabit derinlikte (kamara deliğinin İÇİNDE) çiziliyordu.
    Kullanıcı bunları tasarımının parçası sanıyordu (CLAUDE.md 2026-07-29
    yasağı; CAD hakem #4). Artık yalnız yanıt alanından gelen ölçüler çizilir
    (kamara Ø/L, cidar, lüle uç noktaları + çözücü konturunun boğaz konumu,
    kanal/delik SAYISI) ve çizilmeyen parçalar figürde ADIYLA beyan edilir
    (:attr:`LIQUID_NOT_DRAWN_PARTS`). Parçaların montaj planıyla geri
    dolması A6a cm-3'ün işidir; ölçü uydurularak geri eklenmez.
    """

    #: Sıvı detaylı CAD'de çizilmeyen sabit parça grupları (anahtar, etiket).
    #: Tek tanım: figür beyanı, yanıttaki ``not_drawn_parts`` ve bekçi
    #: (``tests/test_d37_sahte_veri_a1.py``) buradan okur.
    LIQUID_NOT_DRAWN_PARTS = (
        ('injector_head', 'injector head'),
        ('cooling_jacket', 'cooling jacket'),
        ('feed_lines', 'feed lines'),
        ('flanges_bolts', 'flanges/bolts'),
        ('sensors', 'sensors'),
    )
    LIQUID_NOT_DRAWN_REASON = 'no dimension is published for them'

    #: Katı taslak üretici hiçbir şey çizmez; beyan aynı biçimde.
    SOLID_NOT_DRAWN_PARTS = (
        ('grain_pattern', 'grain pattern'),
        ('inhibitor', 'inhibitor'),
        ('case_details', 'case details'),
    )
    SOLID_NOT_DRAWN_REASON = ('the detailed solid-motor generator is not '
                              'modelled')

    #: Beyan notunun figürdeki adı (bekçi bu adla bulur).
    NOT_DRAWN_ANNOTATION_NAME = 'not_drawn_declaration'

    @staticmethod
    def _not_drawn_block(parts, reason):
        """Çizilmeyen parça beyanı: yanıt sözlüğü + figür notu metni."""
        labels = [label for _key, label in parts]
        return {
            'parts': [key for key, _label in parts],
            'labels': labels,
            'reason': reason,
            'declaration': ('Parts not drawn: ' + ', '.join(labels)
                            + ' (' + reason + ')'),
        }

    def _add_not_drawn_declaration(self, fig, block):
        """Beyanı figüre not (annotation) olarak ekler — iz DEĞİL: iz sayısı
        ölçümü (``trace_count``; katı taslakta 0 → uç 501) değişmez."""
        fig.add_annotation(
            name=self.NOT_DRAWN_ANNOTATION_NAME,
            text=block['declaration'],
            xref='paper', yref='paper', x=0.5, y=0.0,
            xanchor='center', yanchor='top', yshift=-8,
            showarrow=False,
            font=dict(size=12, color='#8a93a0'),
        )
        fig.update_layout(margin=dict(b=60),
                          meta={'not_drawn_parts': block})

    def __init__(self):
        self.colors = {
            'chamber': '#2E4057',      # Dark blue-gray
            'nozzle': '#048A81',       # Teal
            'injector': '#C73E1D',     # Red
            'cooling': '#0077B6',      # Blue
            'fuel_feed': '#F77F00',    # Orange
            'ox_feed': '#FCBF49',      # Yellow
            'insulation': '#F8F9FA',   # Light gray
            'structure': '#495057',    # Gray
            'bolts': '#212529',        # Dark gray
            'seals': '#28A745',        # Green
            'sensors': '#6F42C1'       # Purple
        }

    def generate_liquid_motor_cad(self, motor_data: Dict) -> Dict:
        """Generate detailed liquid motor CAD with cross-section"""

        # Extract dimensions (mm girdisi -> m)
        # ÖH D22 / OH-D19-03: BOŞ gövde Ø100 x 200 mm'lik uydurma bir motor
        # çiziyordu (ölçüldü: dimensions = {100, 200, 50, 80, 150}); ölçü
        # yayımlanmamışsa adıyla reddedilir.
        chamber_diameter = _drawable_length_m(
            motor_data, 'chamber_diameter', 'chamber diameter', scale=1e-3)
        chamber_length = _drawable_length_m(
            motor_data, 'chamber_length', 'chamber length', scale=1e-3)
        throat_diameter = _drawable_length_m(
            motor_data, 'throat_diameter', 'throat diameter', scale=1e-3)
        exit_diameter = _drawable_length_m(
            motor_data, 'exit_diameter', 'nozzle exit diameter', scale=1e-3)
        nozzle_length = _drawable_length_m(
            motor_data, 'nozzle_length', 'nozzle length', scale=1e-3)

        # Create dual view: External + Cross-section
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('External View', 'Cross-Section View'),
            specs=[[{'type': 'scatter3d'}, {'type': 'scatter3d'}]],
            horizontal_spacing=0.05
        )

        # Generate external view components
        external_traces = self._create_external_components(
            chamber_diameter, chamber_length, throat_diameter,
            exit_diameter, nozzle_length, motor_data
        )

        # Generate cross-section components
        # ÖH Z5S (P09-A): kesitteki cidar / kanal / delik sayıları TEK
        # çözümleyiciden gelir ve aynı sözlük çıktıya da yayımlanır.
        cross_section = _cross_section_basis(motor_data)
        cross_section_traces = self._create_cross_section_components(
            chamber_diameter, chamber_length, throat_diameter,
            exit_diameter, nozzle_length, motor_data, basis=cross_section
        )

        # Add external view traces
        for trace in external_traces:
            fig.add_trace(trace, row=1, col=1)

        # Add cross-section traces
        for trace in cross_section_traces:
            fig.add_trace(trace, row=1, col=2)

        # Update layout
        fig.update_layout(
            title={
                'text': f'Engineering CAD: {motor_data.get("motor_name", "Liquid Motor")}',
                'x': 0.5,
                'font': {'size': 16}
            },
            scene=dict(
                xaxis_title='Length (m)',
                yaxis_title='Width (m)',
                zaxis_title='Height (m)',
                camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
                aspectmode='cube'
            ),
            scene2=dict(
                xaxis_title='Length (m)',
                yaxis_title='Radius (m)',
                zaxis_title='Height (m)',
                camera=dict(eye=dict(x=0.1, y=1.8, z=1.2)),
                aspectmode='cube'
            ),
            showlegend=True,
            width=1400,
            height=700
        )

        # ÖH D37 A1a (CM-S2): çizilmeyen sabit parçalar figürde ADIYLA.
        not_drawn = self._not_drawn_block(self.LIQUID_NOT_DRAWN_PARTS,
                                          self.LIQUID_NOT_DRAWN_REASON)
        self._add_not_drawn_declaration(fig, not_drawn)

        return {
            'plot_json': fig.to_json(),
            'not_drawn_parts': not_drawn,
            'component_details': self._get_component_details(motor_data),
            # Kesitte GERÇEKTEN çizilen sayılar ve künyeleri — bileşen
            # tablosuyla çelişemez, ikisi de aynı çözümleyiciden okur.
            'cross_section_basis': cross_section,
            'dimensions': {
                'chamber_diameter': chamber_diameter * 1000,
                'chamber_length': chamber_length * 1000,
                'throat_diameter': throat_diameter * 1000,
                'exit_diameter': exit_diameter * 1000,
                'nozzle_length': nozzle_length * 1000
            }
        }

    def _create_external_components(self, chamber_dia, chamber_len, throat_dia,
                                  exit_dia, nozzle_len, motor_data) -> List:
        """Create external view components"""
        traces = []

        # Main chamber body
        # ÖH D15 (defter P9B1-09): ``_create_cylinder_mesh`` silindiri
        # ``center[0]`` ETRAFINDA ortalar; kamara ``center=(0,0,0)`` ile
        # çağrıldığı için gövde x in [-L/2, +L/2] oluyordu. Komşu parçaların
        # hepsi (soğutma ceketi ``L/2``, flanş ve lüle ``L``, kesit ``[0, L]``)
        # ``[0, L]`` yerleşimini varsayar. Ölçüldü (31 Ağustos 2026):
        # gövde -150,00 ... +150,00 mm iken lüle 300,00 mm'de başlıyordu —
        # aradaki 150 mm (yarım kamara boyu) boş görünüyordu ve gövdenin arka
        # yarısı soğutma ceketinin tamamen dışında kalıyordu.
        chamber_mesh = self._create_cylinder_mesh(
            center=(chamber_len / 2.0, 0, 0),
            radius=chamber_dia/2,
            height=chamber_len,
            color=self.colors['chamber'],
            name='Chamber Body'
        )
        traces.append(chamber_mesh)

        # Nozzle — uç noktalar yanıttan, boğaz konumu çözücü konturundan
        # (kesitteki ``Nozzle Profile`` ile AYNI kaynak; bkz.
        # :meth:`_create_nozzle_mesh`).
        nozzle_mesh = self._create_nozzle_mesh(
            start_pos=(chamber_len, 0, 0),
            throat_radius=throat_dia/2,
            exit_radius=exit_dia/2,
            length=nozzle_len,
            color=self.colors['nozzle'],
            name='Nozzle',
            motor_data=motor_data,
            chamber_radius=chamber_dia/2
        )
        traces.append(nozzle_mesh)

        # ÖH D37 A1a (CM-S2): enjektör kafası (0,05 m, Ø+0,02 m), soğutma
        # ceketi (Ø+0,04 m × 0,8·L), besleme hatları (0,015 / 0,012 m boru,
        # 0,3·L / 0,7·L), iki bağlantı flanşı (Ø+0,04 m × 0,02 m, 8'er
        # cıvata) ve iki basınç sensörü BURADA ÇİZİLİYORDU — hiçbirinin
        # ölçüsü bir yanıt alanında yok. Artık çizilmez; figür notu
        # (``LIQUID_NOT_DRAWN_PARTS``) bunu adıyla söyler. Yardımcıları
        # (``_create_feed_line``, ``_create_mounting_flanges``,
        # ``_create_flange``, ``_create_sensors``) başka okuyucusu
        # olmadığı için silindi (git grep, 24 Eyl 2026).

        return traces

    def _create_cross_section_components(self, chamber_dia, chamber_len, throat_dia,
                                       exit_dia, nozzle_len, motor_data,
                                       basis=None) -> List:
        """Create cross-section view showing internal components.

        ``basis`` :meth:`_cross_section_basis` çıktısıdır. Kesitteki her
        tekrarlı öğe (cidar, kanal, delik) O sözlükten çizilir; böylece
        ÇİZİLEN ile YAYIMLANAN sayı tanım gereği aynı olur
        (ÖH Z5S / defter P9B1-19, P9B1-20, P9B1-21).
        """
        traces = []
        if basis is None:
            basis = _cross_section_basis(motor_data)

        # Chamber wall cross-section
        # ÖH Z5S (defter P9B1-19): cidar sabit 8 mm çiziliyordu. Ölçüldü
        # (27 Ağustos 2026): kullanıcı 5 mm girip yapısal analiz de 5 mm
        # derken kesit 8 mm çiziyordu. Kalınlık artık cidar çözümleyicisinden
        # gelir; çözülemezse cidar ÇİZİLMEZ (yalnız delik profili çizilir).
        chamber_profile = self._create_chamber_cross_section(
            chamber_dia, chamber_len,
            basis['chamber_wall_thickness_m'],
            wall_source=basis['chamber_wall_source']
        )
        traces.append(chamber_profile)

        # Injector internal structure
        injector_internal = self._create_injector_cross_section(
            chamber_dia, motor_data, basis=basis
        )
        traces.extend(injector_internal)

        # Cooling channels
        cooling_channels = self._create_cooling_channels_cross_section(
            chamber_dia, chamber_len, basis=basis, motor_data=motor_data
        )
        traces.extend(cooling_channels)

        # Nozzle internal profile
        # ÖH D19 (P9B1-08): konverjan KAMARA yarıçapından başlar; çap
        # buradan geçirilmezse profil boğazdan başlamak zorunda kalır.
        nozzle_profile = self._create_nozzle_cross_section(
            chamber_len, throat_dia, exit_dia, nozzle_len,
            chamber_dia=chamber_dia, motor_data=motor_data
        )
        traces.append(nozzle_profile)

        # Combustion chamber internal
        combustion_chamber = self._create_combustion_chamber_cross_section(
            chamber_dia, chamber_len
        )
        traces.append(combustion_chamber)

        # Flow visualization arrows
        flow_arrows = self._create_flow_arrows_cross_section(
            chamber_dia, chamber_len, nozzle_len
        )
        traces.extend(flow_arrows)

        return traces

    def _create_cylinder_mesh(self, center, radius, height, color, name, opacity=0.8):
        """Create a detailed cylinder mesh"""
        n_theta = 32
        n_z = 2

        theta = np.linspace(0, 2*np.pi, n_theta)
        z = np.linspace(-height/2, height/2, n_z)

        # Create mesh points
        x_cyl = []
        y_cyl = []
        z_cyl = []

        for zi in z:
            for th in theta:
                x_cyl.append(center[0] + zi)
                y_cyl.append(center[1] + radius * np.cos(th))
                z_cyl.append(center[2] + radius * np.sin(th))

        # Create faces
        i, j, k = [], [], []
        for iz in range(n_z - 1):
            for ith in range(n_theta - 1):
                # Current quad indices
                p1 = iz * n_theta + ith
                p2 = iz * n_theta + (ith + 1)
                p3 = (iz + 1) * n_theta + ith
                p4 = (iz + 1) * n_theta + (ith + 1)

                # Two triangles per quad
                i.extend([p1, p2, p1])
                j.extend([p2, p4, p3])
                k.extend([p3, p3, p4])

        return go.Mesh3d(
            x=x_cyl, y=y_cyl, z=z_cyl,
            i=i, j=j, k=k,
            color=color,
            opacity=opacity,
            name=name,
            showlegend=True
        )

    def _create_nozzle_mesh(self, start_pos, throat_radius, exit_radius,
                            length, color, name, motor_data=None,
                            chamber_radius=None):
        """Konverjan-diverjan lüle profili — UÇ NOKTALARI ÇÖZÜCÜDEN.

        ÖH D15 (defter P9B1-07). Kusur: fonksiyon kendisine verilen
        ``exit_radius`` argümanını HİÇ kullanmıyordu. Diverjanı
        ``r = r_bogaz + x*tan(div_angle)`` ile çiziyor, ``div_angle`` ise motor
        sonucunda BULUNMAYAN ``divergent_angle`` anahtarından okunduğu için
        sabit 12,0 dereceye düşüyordu. Ölçüldü (31 Ağustos 2026,
        ``/api/detailed-cad/liquid``, liquid.html'in gönderdiği gövdeyle):
        aynı yanıtın ``dimensions.exit_diameter`` alanı **217,559 mm** derken
        çizilen lülenin gerçek çıkış çapı **116,955 mm** idi (1,86 kat küçük);
        denetim 25,0 + 157,5 x tan(12 derece) = 58,48 mm ölçülenle birebir.
        Aynı kusurun 2B kesitteki ikizi ``_add_cross_section_view``te
        düzeltilmişti, ``DetailedCADGenerator``daki bu ikiz atlanmıştı.

        Artık profil UÇ NOKTALARDAN kurulur: konverjan kamara yarıçapından
        boğaza, diverjan boğazdan ÇÖZÜCÜNÜN çıkış yarıçapına iner/çıkar.
        Hiçbir açı uydurulmaz; açı çizilen konturun SONUCUDUR.

        ÖH D37 A1a sahne-sahte-veri (CM-S2). Kalan görüntü sabiti: boğaz
        lülenin HER motorda %30'una konuyordu (``conv_length = length * 0.3``,
        ``div_length = length * 0.7``). Kesitteki ikizi (``Nozzle Profile``)
        D25'te (OH-D24-09) çözücü konturuna bağlanmıştı; bu dış görünüş
        atlanmıştı, yani aynı figürün iki görünüşü boğazı iki ayrı yerde
        gösteriyordu. Bölünme artık AYNI kaynaktan
        (:func:`_solver_convergent_fraction`, aynı girdilerle) okunur;
        okunamazsa konverjan ÇİZİLMEZ ve profil boğazdan başlar (kesitin
        kuralı). Künye izin ``meta`` alanında.
        """
        n_points = 50

        # Konverjan girişi: kamara yarıçapı. Verilmediyse çözücü sonucundan.
        r_in = _real_scalar(chamber_radius)
        if r_in is None and motor_data:
            bore = _real_scalar((motor_data or {}).get('chamber_diameter'))
            r_in = (bore / 2000.0) if bore is not None else None
        if r_in is None or r_in <= throat_radius:
            # Kamara yarıçapı yoksa konverjan çizilmez (uydurma 15 derecelik
            # koni yerine boğazdan başlanır) — diverjan yine gerçektir.
            r_in = throat_radius

        r_exit = _real_scalar(exit_radius)
        if r_exit is None or r_exit <= 0:
            r_exit = throat_radius

        # Bölünme ÇÖZÜCÜ KONTURUNDAN — kesitle aynı çağrı, aynı girdiler
        # (``_create_nozzle_cross_section`` çapları metre verir; burada
        # yarıçaplar ikiyle çarpılır: ikiye bölüp çarpmak kayan noktada
        # tamdır, iki görünüş bit-aynı girdiyle okur).
        r_chamber = _real_scalar(chamber_radius)
        conv_frac, conv_basis = _solver_convergent_fraction(
            motor_data,
            (2.0 * r_chamber) if r_chamber is not None else None,
            2.0 * throat_radius, 2.0 * r_exit)
        if conv_frac is None:
            r_in = throat_radius     # boğazdan başla: bölünme bilinmiyor

        # Nozzle profile: uç noktalar arasında doğrusal. Boğaz istasyonu
        # örneklemeye AÇIKÇA girer: çözücünün boğazı lülenin %3'üne
        # koyduğu gövdede (ölçüldü, D15 sıvı paneli: 0,0308) 50 eşit adım
        # boğazın iki yanına düşüp çizilen en dar yeri boğazdan %3,4 geniş
        # bırakıyordu; yayımlanan boğaz çizimde tam görünmeli.
        progresses = np.linspace(0.0, 1.0, n_points)
        if conv_frac is not None:
            progresses = np.unique(np.append(progresses, conv_frac))
        x_profile = [float(pr) * length for pr in progresses]

        r_profile = []
        for progress in progresses:
            progress = float(progress)
            if conv_frac is not None and progress < conv_frac:
                r = r_in - (r_in - throat_radius) * (progress / conv_frac)
            else:
                div_progress = ((progress - conv_frac) / (1.0 - conv_frac)
                                if conv_frac is not None else progress)
                r = throat_radius + (r_exit - throat_radius) * div_progress
            r_profile.append(r)

        # Create revolution surface
        theta = np.linspace(0, 2*np.pi, 32)
        x_noz, y_noz, z_noz = [], [], []

        for i, x in enumerate(x_profile):
            for th in theta:
                x_noz.append(start_pos[0] + x)
                y_noz.append(start_pos[1] + r_profile[i] * np.cos(th))
                z_noz.append(start_pos[2] + r_profile[i] * np.sin(th))

        # ÖH D37 A1a sahne-sahte-veri (kural 13, görüntü kalitesi — veri
        # DEĞİŞMEZ): lüle 2 px'lik nokta bulutu (``Scatter3d`` markers)
        # olarak çiziliyordu; 32 meridyen boyunca dizilen noktalar dış
        # görünüşte yüzey yerine "diken" demeti gibi okunuyordu (ölçüldü:
        # once/sonra ``detailed_cad_liquid_*.png``). Aynı noktalar
        # (x/y/z bit-aynı) kamara gövdesiyle aynı tipte bir yüzeye
        # (``Mesh3d``) bağlanır: istasyon × meridyen ızgarasının her
        # dörtgeni iki üçgen.
        n_theta = len(theta)
        tri_i, tri_j, tri_k = [], [], []
        for ix in range(len(x_profile) - 1):
            for ith in range(n_theta - 1):
                p1 = ix * n_theta + ith
                p2 = p1 + 1
                p3 = p1 + n_theta
                p4 = p3 + 1
                tri_i.extend([p1, p2])
                tri_j.extend([p2, p4])
                tri_k.extend([p3, p3])

        return go.Mesh3d(
            x=x_noz, y=y_noz, z=z_noz,
            i=tri_i, j=tri_j, k=tri_k,
            color=color,
            opacity=0.9,
            name=name,
            meta={'convergent_fraction': conv_frac,
                  'convergent_fraction_basis': conv_basis},
            showlegend=True
        )

    def _create_injector_cross_section(self, chamber_dia, motor_data,
                                       basis=None):
        """Create detailed injector cross-section.

        ÖH Z5S (defter P9B1-21): delik sayısı ARAYÜZ SABİTİNDEN
        (``injector_holes``, varsayılan 24) okunuyordu. Artık çözücünün
        ``injector_design`` bloğundan gelir; çözücü eleman üretmediyse DELİK
        ÇİZİLMEZ — 24 uydurma delik, tablonun "NOT AVAILABLE" dediği yerde
        hesaplanmış bir desen gibi görünüyordu.
        """
        traces = []
        if basis is None:
            basis = _cross_section_basis(motor_data)

        injector_type = basis['injector_pattern']
        hole_count = basis['injector_holes_drawn']

        # ÖH D20 / P9B1-26: çağıran da AYNI kapıyı okur — ``if hole_count:``
        # 0,5 ve -3 gibi çizilemez sayıları DOĞRU sayıyordu.
        hole_count = drawable_hole_count(hole_count)
        if hole_count:
            # Create injector holes pattern
            if injector_type == 'unlike_impinging':
                holes = self._create_impinging_injector_holes(chamber_dia,
                                                              hole_count)
            else:
                holes = self._create_coaxial_injector_holes(chamber_dia,
                                                            hole_count)
            traces.extend(holes)

        # Injector face — delik çizilmediyse bunu adı SÖYLER (efsanede
        # görünen tek enjektör öğesi bu olur; sessiz kalırsa okuyucu
        # "deliksiz plaka" sanır).
        face_name = 'Injector Face'
        if not hole_count:
            face_name = (f'Injector Face (holes not drawn: '
                         f'{basis["injector_holes_source"]})')
        injector_face = go.Scatter3d(
            x=[-0.02, -0.02, -0.02, -0.02],
            y=[-chamber_dia/2, chamber_dia/2, chamber_dia/2, -chamber_dia/2],
            z=[-chamber_dia/2, -chamber_dia/2, chamber_dia/2, chamber_dia/2],
            mode='lines',
            line=dict(color=self.colors['injector'], width=6),
            name=face_name,
            showlegend=True
        )
        traces.append(injector_face)

        return traces

    def _create_cooling_channels_cross_section(self, chamber_dia, chamber_len,
                                               basis=None, motor_data=None):
        """Create cooling channel cross-section.

        ÖH Z5S (defter P9B1-20): kanal sayısı ``n_channels = 24`` sabitiydi.
        Artık çözücüden gelir; çözücü kanal üretmediyse KANAL ÇİZİLMEZ.

        ÖH D37 A1a sahne-sahte-veri (CM-S2): kanal çizgisi sabit 3 mm
        "derinlikte" (``chamber_dia/2 - 0.003``) — yani kamara deliğinin
        İÇİNDE, gazın tarafında — çiziliyordu. Kanalın cidardaki radyal
        yeri sıcak cidar kalınlığını ister ve o yayımlanmıyor; bu yüzden
        kanal yalnız SAYISI ve açısal dizilişiyle, yayımlanan tek yarıçapta
        (kamara deliği, ``chamber_diameter / 2``) çizilir. Yayımlanan kanal
        yüksekliği (``cooling_system.channel_height_mm``) varsa künyede
        adıyla durur, konum uydurulmaz.
        """
        traces = []
        if basis is None:
            basis = _cross_section_basis(motor_data)

        n_channels = basis['cooling_channels_drawn']
        if not n_channels:
            return traces

        r_station = chamber_dia / 2
        cooling = ((motor_data or {}).get('cooling_system')
                   if isinstance(motor_data, dict) else None) or {}
        height_mm = _real_scalar(cooling.get('channel_height_mm')
                                 if isinstance(cooling, dict) else None)
        if height_mm is not None and height_mm > 0:
            seat = (f'channel height {height_mm:.2f} mm is published '
                    f'(cooling_system.channel_height_mm) but its radial seat '
                    f'is not (no hot-wall thickness is published)')
        else:
            height_mm = None
            seat = 'no channel height is published, so no depth is drawn'

        for i in range(n_channels):
            angle = i * 2 * np.pi / n_channels

            # Channel path
            # ÖH D15 (defter P9B1-10): numpy dizisi Plotly'ye doğrudan
            # verildiğinde ``plot_json`` base64 ``bdata`` yazar ve sayfaya
            # gömülü plotly 1.58.5 bunu çözemez — kanalların TAMAMI
            # çizilmiyordu. Ölçüldü (31 Ağustos 2026, ham sıvı sonucu):
            # 86 izin 23'ü bdata idi (21 soğutma kanalı + 2 besleme hattı).
            x_channel = np.linspace(0, chamber_len, 20).tolist()
            y_channel = [float(r_station * np.cos(angle))] * 20
            z_channel = [float(r_station * np.sin(angle))] * 20

            channel = go.Scatter3d(
                x=x_channel,
                y=y_channel,
                z=z_channel,
                mode='lines',
                line=dict(color=self.colors['cooling'], width=3),
                # Efsane adı kısa kalır (künyenin tamamı ``meta``da).
                name=(f'Cooling Channel ({basis["cooling_channels_source"]}; '
                      'on the bore line, depth not drawn)' if i == 0
                      else None),
                meta={'radial_station_m': float(r_station),
                      'radial_station_basis': ('chamber_diameter / 2 (the '
                                               'only published radius)'),
                      'channel_height_mm': height_mm,
                      'channel_depth_basis': seat},
                showlegend=True if i == 0 else False
            )
            traces.append(channel)

        return traces

    def _create_chamber_cross_section(self, chamber_dia, chamber_len,
                                      wall_thickness, wall_source=None):
        """Create chamber wall cross-section.

        ÖH Z5S (defter P9B1-19): ``wall_thickness`` sabit 0.008 m geliyordu.
        Artık cidar çözümleyicisinden gelir ve ``None`` olabilir — o hâlde
        DIŞ profil çizilmez (uydurma bir dış hat imalatçıya yanlış boru
        ısmarlatır), yalnız kamara deliği çizilir ve izin adı sebebi söyler.
        """
        wall_source = wall_source or 'not available'

        # Inner wall (kamara deliği) — her hâlde çizilir
        x_inner = [0, chamber_len, chamber_len, 0, 0]
        y_inner = [chamber_dia/2, chamber_dia/2, -chamber_dia/2, -chamber_dia/2, chamber_dia/2]
        z_inner = [0, 0, 0, 0, 0]

        if wall_thickness is None:
            return go.Scatter3d(
                x=x_inner, y=y_inner, z=z_inner,
                mode='lines',
                line=dict(color=self.colors['chamber'], width=4),
                name=(f'Chamber Bore (wall not drawn - {NOT_AVAILABLE_SPEC}; '
                      f'thickness source: {wall_source})'),
                showlegend=True
            )

        # Outer wall
        x_outer = [0, chamber_len, chamber_len, 0, 0]
        y_outer = [chamber_dia/2 + wall_thickness, chamber_dia/2 + wall_thickness,
                  -chamber_dia/2 - wall_thickness, -chamber_dia/2 - wall_thickness,
                  chamber_dia/2 + wall_thickness]
        z_outer = [0, 0, 0, 0, 0]

        return go.Scatter3d(
            x=x_outer + x_inner,
            y=y_outer + y_inner,
            z=z_outer + z_inner,
            mode='lines',
            line=dict(color=self.colors['chamber'], width=4),
            name=f'Chamber Wall ({wall_thickness * 1000.0:.2f} mm, {wall_source})',
            showlegend=True
        )

    def _get_component_details(self, motor_data) -> Dict:
        """Sıvı motor bileşen özeti — çözücü sonucundan.

        Eski sürüm bu bloğu tamamen sabit dolduruyordu (24 kanal, 24 delik,
        'Inconel 718' / 'C-C Composite' / 'Stainless Steel 316L', 'Regenerative')
        ve kullanıcı bunu kendi tasarımının bileşen özeti sanıyordu; aynı
        oturumda çözücü 80 kanal raporluyordu (2026-07-19 denetimi).

        Beklenen sözleşme — istek gövdesinde motor sonucunun şu alanları
        bulunmalıdır: injector_design (number_of_elements / number_of_orifices),
        cooling_system (cooling_channels), cooling_type, chamber_material,
        nozzle_material, injector_material. Alan yoksa SABİT DEĞER YAZILMAZ;
        NOT_AVAILABLE_SPEC döner. (Not: yalnızca UI'nin sabit gönderdiği
        'injector_holes' anahtarı bilerek okunmaz — o bir arayüz sabitidir,
        tasarım sonucu değil.)
        """
        md = motor_data or {}
        inj_design = md.get('injector_design') or {}

        # ÖH Z5S (P09-A): tablo ile KESİT aynı çözümleyiciden okur — ikisi
        # ayrı yazıldığında tablo "NOT AVAILABLE" derken kesit 24 delik /
        # 24 kanal çiziyordu.
        holes = _solver_injector_element_count(md)
        channels = _solver_cooling_channel_count(md)
        dp = _real_scalar(inj_design.get('injection_pressure_drop_fuel_bar')
                          or inj_design.get('injection_pressure_drop_bar')
                          or md.get('injector_dp'))
        thrust = _real_scalar(md.get('thrust'))
        isp = _real_scalar(md.get('isp'))
        # P16B4-25: hazne basıncı ham ekolanmaz (aşağıdaki künyeye bak).
        from hrma.export.pdf_generator import resolve_chamber_pressure_bar
        _pc_bar, _pc_red = resolve_chamber_pressure_bar(
            _real_scalar(md.get('chamber_pressure')))

        return {
            'injector': {
                'type': (inj_design.get('injector_type') or md.get('injector_type')
                         or NOT_AVAILABLE_SPEC),
                'hole_count': int(round(holes)) if holes else NOT_AVAILABLE_SPEC,
                'pressure_drop': f"{dp:.2f} bar" if dp else NOT_AVAILABLE_SPEC,
                'source': 'solver injector_design' if holes else 'not available'
            },
            'cooling': {
                'type': md.get('cooling_type') or NOT_AVAILABLE_SPEC,
                'channel_count': int(round(channels)) if channels else NOT_AVAILABLE_SPEC,
                'coolant': md.get('fuel_type') or NOT_AVAILABLE_SPEC,
                'source': 'solver cooling_system' if channels else 'not available'
            },
            'materials': {
                'chamber': (_chamber_material(md)[1] or md.get('chamber_material')
                            or NOT_AVAILABLE_SPEC),
                'nozzle': md.get('nozzle_material') or NOT_AVAILABLE_SPEC,
                'injector': md.get('injector_material') or NOT_AVAILABLE_SPEC
            },
            'performance': {
                'thrust': f"{thrust:.0f} N" if thrust else NOT_AVAILABLE_SPEC,
                'isp': f"{isp:.1f} s" if isp else NOT_AVAILABLE_SPEC,
                # ÖH D24 / defter P16B4-25 (kardeş saha, aynı kusur sınıfı):
                # 'bar' etiketi burada da KAZANILIR. Ham eko deseni PDF
                # üreticisinde ölçüldü (2000000.0 -> "2000000.0 bar"); kural
                # tek kaynaktan gelir —
                # ``pdf_generator.resolve_chamber_pressure_bar`` bandı
                # ``validation.motor_validation.FORM_LIMITS``ten okur. Bant
                # içindeki değerde çıktı BİT-AYNIDIR; bant dışında sayı
                # yayımlanmaz ve reddin gerekçesi komşu alanda ADIYLA durur
                # (sessiz düşürme yok).
                'chamber_pressure': (f"{_pc_bar:.1f} bar" if _pc_bar
                                     else NOT_AVAILABLE_SPEC),
                **({'chamber_pressure_withheld_reason': _pc_red}
                   if _pc_red else {}),
            }
        }

    def generate_solid_motor_cad(self, motor_data: Dict) -> Dict:
        """Katı motor detaylı CAD — BU ÜRETİCİ HENÜZ TASLAKTIR.

        ÖH D19 (defter P9B1-22). Kusur: gövde yalnız ``make_subplots``
        iskeletini kuruyor, iz ekleyen tek satır yok ("Will implement grain
        patterns, inhibitor, case details" yorumu duruyordu) ve buna rağmen
        çağırana sıradan bir üretim sözlüğü döndürüyordu. Ölçüldü
        (``docs/scofield/raw/OH/D19/ihracat/a1/once.json``): üretilen figürün
        iz sayısı **0**, dönen sözlükte hata alanı **yok**.

        Tüketici ``/api/detailed-cad/solid`` bunu D16'da (P16B4-06) ÖLÇEREK
        yakalamıştı (iz sayısı 0 -> 501 ``cad_not_modelled``); ama üretici
        kendi durumunu SÖYLEMEDİĞİ için hüküm tüketicinin çıkarımına
        kalıyordu. Artık üretici kendi ölçümünü okuyup durumunu ADIYLA
        beyan eder; alan üretici gerçekten çizmeye başladığı gün
        kendiliğinden ``None`` olur (sabit bir bayrak değildir, ölçümdür).
        """

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('External View', 'Grain Cross-Section'),
            specs=[[{'type': 'scatter3d'}, {'type': 'scatter3d'}]],
            horizontal_spacing=0.05
        )

        # TODO: grain desenleri, inhibitör ve kasa ayrıntıları henüz
        # çizilmiyor. Buraya iz eklendiği anda aşağıdaki ölçüm kendiliğinden
        # değişir ve beyan düşer.

        # ÖH D37 A1a (CM-S2): sıvı eşiyle AYNI beyan biçimi. Not bir iz
        # değildir: iz sayısı 0 kalır, uç ``cad_not_modelled`` (501) hükmünü
        # ölçümden vermeye devam eder.
        not_drawn = self._not_drawn_block(self.SOLID_NOT_DRAWN_PARTS,
                                          self.SOLID_NOT_DRAWN_REASON)
        self._add_not_drawn_declaration(fig, not_drawn)

        plot_json = fig.to_json()
        try:
            iz_sayisi = len(json.loads(plot_json).get('data') or [])
        except Exception:
            iz_sayisi = 0

        sonuc = {
            'plot_json': plot_json,
            'not_drawn_parts': not_drawn,
            'component_details': self._get_solid_component_details(motor_data),
            # ÖLÇÜM, iddia değil: çizilen iz sayısı sözlükte taşınır.
            'trace_count': iz_sayisi,
        }
        if iz_sayisi == 0:
            sonuc['error'] = 'solid_detailed_cad_not_modelled'
            sonuc['error_message'] = (
                'The detailed solid-motor CAD generator is still a stub: it '
                'produced 0 plot traces (no grain pattern, inhibitor or case '
                'detail is drawn). The component_details block below is real '
                'and comes from the structural analysis, but there is no '
                'drawing to go with it.')
        return sonuc

    def _get_solid_component_details(self, motor_data) -> Dict:
        """Katı motor bileşen özeti — kasa verileri YAPISAL analizden.

        Eski sürüm kasayı sabit yazıyordu ('Steel 4130', '5mm', SF 2.5);
        emniyet katsayısı bu yazılımın en kritik çıktısı ve gerçek yapısal
        analiz zaten mevcuttu (2026-07-19 denetimi).
        """
        md = motor_data or {}
        struct = md.get('structural_analysis') or {}
        wall_m, wall_source = _chamber_wall_thickness_m(md)
        _key, mat_name, _rho = _chamber_material(md)
        sf = (_real_scalar(struct.get('safety_factor_total'))
              or _real_scalar(struct.get('safety_factor'))
              or _real_nested(struct, ('safety_analysis', 'minimum_safety_factor')))
        grain = md.get('grain_design') or {}

        return {
            'grain': {
                'type': (grain.get('grain_type') or md.get('grain_type')
                         or NOT_AVAILABLE_SPEC),
                'segments': (grain.get('number_of_segments')
                             or md.get('grain_count') or NOT_AVAILABLE_SPEC),
                'inhibitor': (grain.get('inhibitor') or md.get('inhibitor')
                              or NOT_AVAILABLE_SPEC)
            },
            'case': {
                'material': mat_name or NOT_AVAILABLE_SPEC,
                'thickness': (f"{wall_m * 1000.0:.2f} mm" if wall_m
                              else NOT_AVAILABLE_SPEC),
                'thickness_source': wall_source,
                'factor_of_safety': sf if sf else NOT_AVAILABLE_SPEC,
                'factor_of_safety_source': ('structural analysis' if sf
                                            else 'not available')
            }
        }

    def _create_impinging_injector_holes(self, chamber_dia, hole_count):
        """Create impinging injector holes pattern.

        ÖH D20 / P9B1-26: kardeş desenle AYNI kapı
        (``drawable_hole_count``) — eskiden ``0,5`` burada ``TypeError``
        yükseltirken kardeşinde ``ZeroDivisionError`` oluyordu.
        """
        n = drawable_hole_count(hole_count)
        if n is None:
            return []
        traces = []

        # Create concentric rings of holes
        inner_ring = n // 3
        middle_ring = n // 3
        outer_ring = n - inner_ring - middle_ring

        rings = [
            (inner_ring, chamber_dia * 0.15),
            (middle_ring, chamber_dia * 0.25),
            (outer_ring, chamber_dia * 0.35)
        ]

        for holes_in_ring, radius in rings:
            for i in range(holes_in_ring):
                angle = i * 2 * np.pi / holes_in_ring
                x_hole = -0.015
                y_hole = radius * np.cos(angle)
                z_hole = radius * np.sin(angle)

                hole = go.Scatter3d(
                    x=[x_hole], y=[y_hole], z=[z_hole],
                    mode='markers',
                    marker=dict(size=4, color=self.colors['fuel_feed']),
                    name='Injector Hole' if len(traces) == 0 else None,
                    showlegend=True if len(traces) == 0 else False
                )
                traces.append(hole)

        return traces

    def _create_coaxial_injector_holes(self, chamber_dia, hole_count):
        """Create coaxial injector holes pattern.

        ÖH D20 / P9B1-26: delik sayısı ortak kapıdan geçer
        (``drawable_hole_count``); çizilemeyen sayıda desen üretilmez.
        """
        n = drawable_hole_count(hole_count)
        if n is None:
            return []
        traces = []

        # Coaxial elements in grid pattern
        rows = int(np.sqrt(n))
        cols = n // rows

        for i in range(rows):
            for j in range(cols):
                y_pos = (i - rows/2) * chamber_dia * 0.1
                z_pos = (j - cols/2) * chamber_dia * 0.1

                # Central fuel hole
                fuel_hole = go.Scatter3d(
                    x=[-0.015], y=[y_pos], z=[z_pos],
                    mode='markers',
                    marker=dict(size=3, color=self.colors['fuel_feed']),
                    name='Fuel Hole' if len(traces) == 0 else None,
                    showlegend=True if len(traces) == 0 else False
                )
                traces.append(fuel_hole)

                # Surrounding oxidizer holes
                for k in range(4):
                    angle = k * np.pi / 2
                    ox_y = y_pos + 0.005 * np.cos(angle)
                    ox_z = z_pos + 0.005 * np.sin(angle)

                    ox_hole = go.Scatter3d(
                        x=[-0.015], y=[ox_y], z=[ox_z],
                        mode='markers',
                        marker=dict(size=2, color=self.colors['ox_feed']),
                        name='Oxidizer Hole' if len(traces) == 1 else None,
                        showlegend=True if len(traces) == 1 else False
                    )
                    traces.append(ox_hole)

        return traces

    def _create_nozzle_cross_section(self, chamber_len, throat_dia, exit_dia,
                                     nozzle_len, chamber_dia=None,
                                     motor_data=None):
        """Create nozzle cross-section profile.

        ÖH D19 (defter P9B1-08). Kusur: konverjan dalı
        ``r = r_t + (r_e - r_t) * (1 - ((1-progress)/0.3)**2)`` yazıyordu.
        ``progress = 0``'da ``((1-0)/0.3)**2 = 11,111`` olduğu için çarpan
        **−10,111**'e düşüyor ve yarıçap NEGATİF çıkıyordu. Ölçüldü
        (``docs/scofield/raw/OH/D19/ihracat/a1/once.json``, panelin kendi mm
        sözleşmesiyle): ``Nozzle Profile`` izinin üst yarısındaki ilk beş
        yarıçap ``[-822,10; -784,50; -747,66; -711,61; -676,33] mm``,
        **50 noktanın 15'i negatif**. Aynı motorun boğaz yarıçapı 25 mm,
        çıkış yarıçapı 108,78 mm. "Cross-Section View" panelinde kullanıcı
        motorun 8 katı büyüklükte, eksenin yanlış tarafından gelen bir eğri
        görüyor ve bunu lüle konturu sanıyordu.

        İki ayrı hata iç içeydi: (1) formül işaret koruması olmayan bir
        parabol, (2) "konverjan" dalı KAMARA yarıçapını hiç okumuyor,
        daralmayı ÇIKIŞ yarıçapı ölçeğinden kuruyordu — oysa konverjan
        kamaradan boğaza iner.

        Onarım, aynı dosyada ``_create_nozzle_mesh`` için P9B1-07'de kurulan
        kuralın ikizidir: **profil UÇ NOKTALARDAN kurulur.** Konverjan
        kamara yarıçapından boğaza iner, diverjan boğazdan ÇÖZÜCÜNÜN çıkış
        yarıçapına çıkar. Hiçbir açı uydurulmaz; yarıçap uç noktaların
        arasında kaldığı için tanım gereği negatif olamaz.

        ``chamber_dia`` verilmezse (ya da boğazdan küçükse) konverjan
        çizilmez ve profil boğazdan başlar — uydurma bir daralma çizmek
        yerine eksik olan söylenir.
        """
        n_points = 50
        r_t = throat_dia / 2.0
        r_e = exit_dia / 2.0 if (exit_dia and exit_dia > 0) else r_t
        # Konverjan girişi: KAMARA yarıçapı (uydurma ölçek değil).
        r_in = (chamber_dia / 2.0) if (chamber_dia and chamber_dia > 0) else None
        if r_in is None or r_in <= r_t:
            r_in = r_t
        if not nozzle_len or nozzle_len <= 0:
            # Boy yoksa profil çizilemez: tek noktalık dejenere bir eğri
            # yerine boğaz yarıçapında düz bir çizgi bile basılmaz.
            nozzle_len = 0.0
        x_profile = np.linspace(chamber_len, chamber_len + nozzle_len, n_points)

        # ÖH D25 (defter OH-D24-09, zincir P9B1-08): BÖLÜNME ÇÖZÜCÜDEN.
        # Eskiden burada ``CONV_FRAC = 0.3`` duruyordu — bir GÖRÜNTÜ
        # SABİTİ. Ölçüldü (``once.json`` MB): çözücünün kendi konturunda
        # boğaz hibritte lülenin %30,74'ünde, katıda %47,18'inde, sıvıda
        # %99,89'unda oturuyor; panel üçünde de %30,6 ima ediyordu. Yani
        # kesitteki boğaz konumu ile aynı motorun STL/STEP/DXF konturu
        # birbirini tutmuyordu. Kesir artık ortak kontur kaynağından okunur;
        # okunamazsa konverjan ÇİZİLMEZ (kamara çapı yokken uygulanan
        # kuralın ikizi — uydurma daralma yerine eksik olan söylenir).
        conv_frac, conv_basis = _solver_convergent_fraction(
            motor_data, chamber_dia, throat_dia, exit_dia)
        if conv_frac is None:
            r_in = r_t          # boğazdan başla: bölünme bilinmiyor
        r_profile = []
        for x in x_profile:
            progress = ((x - chamber_len) / nozzle_len) if nozzle_len else 1.0
            if conv_frac is not None and progress < conv_frac:
                r = r_in - (r_in - r_t) * (progress / conv_frac)
            else:
                div_progress = ((progress - conv_frac) / (1.0 - conv_frac)
                                if conv_frac is not None else progress)
                r = r_t + (r_e - r_t) * div_progress
            r_profile.append(r)

        # Upper and lower profiles
        return go.Scatter3d(
            x=list(x_profile) + list(x_profile),
            y=r_profile + [-r for r in r_profile],
            z=[0] * len(r_profile) * 2,
            mode='lines',
            line=dict(color=self.colors['nozzle'], width=4),
            name='Nozzle Profile',
            # Künye: bölünmenin NEREDEN geldiği izin üstünde durur (ad
            # sözleşmesi bozulmadan) — okuyucu %30'luk bir görüntü sabitiyle
            # çözücü konturunu ayırt edebilsin.
            meta={'convergent_fraction': conv_frac,
                  'convergent_fraction_basis': conv_basis},
            showlegend=True
        )

    def _create_combustion_chamber_cross_section(self, chamber_dia, chamber_len):
        """Create combustion chamber internal view"""
        return go.Scatter3d(
            x=[0, chamber_len, chamber_len, 0, 0],
            y=[chamber_dia/2, chamber_dia/2, -chamber_dia/2, -chamber_dia/2, chamber_dia/2],
            z=[0, 0, 0, 0, 0],
            mode='lines',
            line=dict(color='rgba(255, 100, 0, 0.5)', width=3, dash='dash'),
            name='Combustion Chamber',
            showlegend=True
        )

    def _create_flow_arrows_cross_section(self, chamber_dia, chamber_len, nozzle_len):
        """Create flow direction arrows"""
        traces = []

        # Flow arrows in chamber
        n_arrows = 5
        for i in range(n_arrows):
            x_pos = chamber_len * (i + 1) / (n_arrows + 1)

            arrow = go.Scatter3d(
                x=[x_pos, x_pos + 0.02],
                y=[0, 0],
                z=[0, 0],
                mode='lines+markers',
                line=dict(color='red', width=4),
                marker=dict(size=[2, 6], symbol=['circle', 'diamond']),
                name='Flow Direction' if i == 0 else None,
                showlegend=True if i == 0 else False
            )
            traces.append(arrow)

        return traces
