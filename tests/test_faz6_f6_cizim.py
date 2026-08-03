"""Faz 6 / F6-cizim — kesit, güverte ve pano bulgularının bekçileri.

3 Ağustos 2026 tarayıcı denetiminin çizim tarafındaki yedi bulgusu burada
kilitlenir. Her testin kilitlediği kusur, düzeltme geri alınınca YENİDEN
ÜRETİLİR — testler "mevcut davranış" değil, ÖLÇÜLMÜŞ doğru davranış sınar:

  T06  kesitin radyal ölçüleri girdiden bağımsızdı (grain Ø60 -> Ø96 çizildi,
       kasa cidarı 2/8/30 mm için hep 4,5 mm, yalıtım 0,5/3/20 mm için ~2 mm)
  T07  'Final port Ø99,8 mm' hesap değil, (çizilen grain yarıçapı − 1 mm) idi
  T10  grain boyu 2B kesitte ve 3B güvertede sessizce %8 kırpılıyordu
  T11  'Tank' çubuğu tank basıncını hiç göstermiyordu (30/50/90 bar -> hep 24)
  T18  N2O/HTPB referans yüzeyine RP-1/LOX tasarım noktası basılıyordu
  T39  ekrandaki oda cidarı 3,0 mm, imalat çıktılarında (DXF/STEP/PDF) 5,00 mm
  T43  enjektör göstergesi hangi hızı gösterdiğini söylemiyordu, yakıt devresi
       hiç gösterilmiyordu

Fikstürler çözücü çıktılarının şemasıyla birebir aynı anahtarları taşır;
sayılar gerçek koşumlardan alınmıştır (kaynak her testin docstring'inde).
"""

import json
import math
import os
import re

import pytest

from hrma.visualization.visualization import (
    create_chamber_pressure_mixture_ratio_3d_surface,
    create_improved_motor_cross_section,
    create_performance_plots,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIZ3D_JS = os.path.join(REPO_ROOT, "hrma", "static", "js", "motor_viz3d.js")


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _fig(js):
    assert isinstance(js, str)
    return json.loads(js)


def _iz(fig, ad):
    """Adı verilen izin |y| en büyüğü ve x aralığı."""
    ymax, xmin, xmax = None, None, None
    for tr in fig["data"]:
        if tr.get("name") != ad:
            continue
        ys = [abs(v) for v in (tr.get("y") or []) if isinstance(v, (int, float))]
        xs = [v for v in (tr.get("x") or []) if isinstance(v, (int, float))]
        if ys:
            ymax = max(ys) if ymax is None else max(ymax, max(ys))
        if xs:
            xmin = min(xs) if xmin is None else min(xmin, min(xs))
            xmax = max(xs) if xmax is None else max(xmax, max(xs))
    if ymax is None and xmin is None:
        return None
    return {"ymax": ymax, "xmin": xmin, "xmax": xmax}


def _iz_adlari(fig):
    return [t.get("name") for t in fig["data"] if t.get("name")]


def _notlar(fig):
    return [a.get("text", "") for a in fig["layout"].get("annotations", [])]


def _kati_geo(**kw):
    """``solid_results_to_motor_geometry`` çıktısının şekli (uzunluklar METRE).

    Sayılar gerçek /calculate_solid koşumundan: Ø100 mm kasa deliği, 500 mm
    grain, Ø30 mm çekirdek, 2,4 mm kasa cidarı.
    """
    geo = {
        "chamber_diameter": 0.100,
        "chamber_length": 0.600,
        "throat_diameter": 0.0479,
        "exit_diameter": 0.1167,
        "grain_length": 0.500,
        "port_diameter_initial": 0.030,
        "port_diameter_final": 0.100,
        "grain_design": {
            "grain_length_mm": 500.0,
            "inner_diameter_mm": 30.0,
            "outer_diameter_mm": 100.0,
            "port_diameter_initial_mm": 30.0,
            "port_diameter_final_mm": 100.0,
            "web_thickness_mm": 35.0,
            "inhibitor_config": "outer_surface",
        },
        "structural_analysis": {
            "case_analysis": {
                "wall_thickness_mm": 2.4,
                "recommended_wall_thickness_mm": 2.4,
            }
        },
    }
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(geo.get(k), dict):
            geo[k] = dict(geo[k], **v)
        else:
            geo[k] = v
    return geo


def _sivi_geo(wall=5.0, required=2.0):
    """``liquid_results_to_motor_geometry`` şekli — gerçek koşumdan.

    Ölçüldü: oda Ø61,6228 mm, kullanıcının girdiği cidar 5,00 mm, yapısal
    analizin gerektirdiği 2,00 mm. DXF/STEP/PDF üçü de 5,00 mm basıyor.
    """
    return {
        "chamber_diameter": 0.0616228,
        "chamber_length": 0.200,
        "throat_diameter": 0.0234,
        "exit_diameter": 0.0702,
        "structural_analysis": {
            "chamber_structure": {
                "wall_thickness": wall,
                "required_wall_thickness": required,
                "wall_thickness_source": "user input (chamber wall thickness)",
            }
        },
    }


def _cizilen_cidar(fig, oda_capi_mm):
    """Kesitteki 'Chamber wall' izinin dış yarıçapı − oda yarıçapı [mm]."""
    kasa = _iz(fig, "Chamber wall")
    assert kasa is not None, "kesitte kamara duvarı izi yok"
    return kasa["ymax"] - oda_capi_mm / 2.0


# ---------------------------------------------------------------------------
# T06 — radyal ölçüler girdiyi izler
# ---------------------------------------------------------------------------

def test_t06_grain_dis_capi_cizime_yansir():
    """Grain dış çapı çözücüden okunur; ``rc − liner`` diye türetilmez.

    Ölçüldü (HEAD, /calculate_solid): 'Outer Diameter' 100 -> 60 mm
    değiştirildiğinde çözücü 100,0 ve 60,0 mm derken çizim İKİ koşuda da
    48,0 mm yarıçap (Ø96) veriyordu — %60 hata. Bu test o kırpmayı geri
    alırsan (r_go = rc - liner_t) İKİ dalda birden kırılır.
    """
    for od, beklenen_r in ((100.0, 50.0), (60.0, 30.0)):
        fig = _fig(create_improved_motor_cross_section(
            _kati_geo(grain_design={"outer_diameter_mm": od,
                                    "port_diameter_final_mm": od}),
            motor_type="solid"))
        grain = _iz(fig, "Fuel grain")
        assert grain is not None
        assert grain["ymax"] == pytest.approx(beklenen_r), (
            f"grain dış çapı Ø{od} mm iken çizilen yarıçap {grain['ymax']} mm")


def test_t06_kasa_cidari_cozucu_degerini_kirpmadan_cizer():
    """Kasa cidarı çözücüden okunur ve 0,12·D üst kırpması UYGULANMAZ.

    Ölçüldü: kullanıcı 1 / 8 / 30 mm girdi, çözücü 2,0 / 8,0 / 30,0 mm
    raporladı, çizim üçünde de 4,5 mm (= 0,045·D geometrik yedeği) çizdi.
    30 mm dalı ayrıca eski ``min(..., 0.12*D_ch)`` kırpmasını yakalar:
    Ø100 mm kasada o kırpma 30 mm'yi 12 mm'ye indiriyordu.
    """
    for t in (2.0, 8.0, 30.0):
        fig = _fig(create_improved_motor_cross_section(
            _kati_geo(structural_analysis={
                "case_analysis": {"wall_thickness_mm": t,
                                  "recommended_wall_thickness_mm": t}}),
            motor_type="solid"))
        assert _cizilen_cidar(fig, 100.0) == pytest.approx(t), (
            f"çözücü {t} mm cidar raporladı")


def test_t06_yalitim_halkasi_iki_capin_farkindan_gelir():
    """Kasa deliği ile grain arasındaki halka = (Ø_delik − Ø_grain)/2.

    Ölçüldü (/calculate_solid, yalıtım girdisi taraması): yalıtım
    0 / 0,5 / 3 / 20 mm iken kasa deliği 100 / 101 / 106 / 140 mm oluyor,
    grain 100 mm'de sabit kalıyor. Eski kod halkayı
    ``min(max(0,02·D, 1,5), 5,0)`` diye uyduruyordu; 20 mm yalıtımı 2,6 mm
    çiziyor, 0 mm yalıtımda da olmayan bir bant basıyordu.
    """
    beklenen = {100.0: 0.0, 101.0: 0.5, 106.0: 3.0, 140.0: 20.0}
    for delik_mm, halka_mm in beklenen.items():
        fig = _fig(create_improved_motor_cross_section(
            _kati_geo(chamber_diameter=delik_mm / 1000.0), motor_type="solid"))
        grain = _iz(fig, "Fuel grain")
        assert grain["ymax"] == pytest.approx(50.0), "grain dışı sabit kalmalı"
        halka = _iz(fig, "Liner / annulus")
        if halka_mm == 0.0:
            assert halka is None, "olmayan yalıtım bandı çizildi"
        else:
            assert halka is not None, f"{halka_mm} mm halka çizilmedi"
            # Bandın dış yarıçapı kasa deliğinden bir tutam içeridedir
            # (çizim payı); halka kalınlığı iki çapın farkına eşit olmalı.
            inset = min(0.2, 0.25 * halka_mm)
            assert (halka["ymax"] + inset
                    - grain["ymax"]) == pytest.approx(halka_mm)


def test_t06_cidar_cad_cizimiyle_ayni_kaynaktan_gelir():
    """Ekrandaki kesit ile imalata giden çizim AYNI kalınlığı gösterir.

    Tek kaynak ``cad_visualization._chamber_wall_design``; bu test kesitin o
    kapıyı atlayıp kendi kuralını uydurmasını engeller (üç motor tipinin üç
    ayrı yapısal şeması yalnız orada tanımlı).
    """
    from hrma.export.cad_visualization import _chamber_wall_design

    for geo, oda_mm in ((_kati_geo(), 100.0), (_sivi_geo(), 61.6228)):
        beklenen = _chamber_wall_design(geo)["thickness_m"] * 1000.0
        fig = _fig(create_improved_motor_cross_section(geo))
        assert _cizilen_cidar(fig, oda_mm) == pytest.approx(beklenen, rel=1e-9)


# ---------------------------------------------------------------------------
# T07 — son port etiketi hesap olmalı
# ---------------------------------------------------------------------------

def test_t07_son_port_etiketi_cozucunun_degeridir():
    """Efsanedeki son port çapı çözücüden gelir, çizim yarıçapından değil.

    Eski kod ``r_pf = min(r_pf, r_go - 1.0)`` yazıyordu: çizilen grain
    yarıçapı 50,88 mm iken etiket 49,88·2 = Ø99,8 mm çıkıyordu — sayı
    hesabın değil, çizimin türeviydi. Bu fikstürde eski kural Ø98,0 mm
    verirdi (grain dışı 50 mm − 1 mm), doğrusu Ø100,0 mm'dir.
    """
    fig = _fig(create_improved_motor_cross_section(_kati_geo(),
                                                   motor_type="solid"))
    adlar = [a for a in _iz_adlari(fig) if a.startswith("Final port")]
    assert adlar, "son port izi çizilmedi"
    ad = adlar[0]
    sayi = float(re.search(r"Ø([\d.]+)", ad).group(1))
    assert sayi == pytest.approx(100.0), f"efsane '{ad}'"
    assert "web fully consumed" in ad
    # İz gerçekten grain dışında duruyor (etiket ile geometri aynı şeyi der)
    assert _iz(fig, ad)["ymax"] == pytest.approx(50.0)


def test_t07_son_port_inhibitor_duzenine_duyarlidir():
    """Dış yüzey yanıyorsa son port İDDİA EDİLMEZ; iz çizilmez, gerekçe yazılır.

    Ölçüldü (/calculate_solid): ``inhibit_outer`` False iken yanma süresi
    2,1863 s -> 1,1757 s değişiyor, yani model inhibitörü tanıyor; buna
    karşın ``port_diameter_final`` iki koşuda da 100,0 mm (grain dış çapı)
    dönüyor. Dış yüzey de yanarken son port grain dış çapı OLAMAZ, çözücü
    de tükenen web'i yayımlamıyor -> sayı basılmaz.
    """
    yanan = _kati_geo(grain_design={"inhibitor_config": "none"})
    fig = _fig(create_improved_motor_cross_section(yanan, motor_type="solid"))
    assert not [a for a in _iz_adlari(fig) if a.startswith("Final port")], (
        "dış yüzey yanarken uydurma son port çizildi")
    assert any("not drawn" in n for n in _notlar(fig)), (
        "iz çizilmedi ama gerekçe de yazılmadı — sessiz atlama")

    # Karşı kanıt: inhibitörlü düzende iz ÇİZİLİR (test her şeyi susturmuyor)
    fig2 = _fig(create_improved_motor_cross_section(_kati_geo(),
                                                    motor_type="solid"))
    assert [a for a in _iz_adlari(fig2) if a.startswith("Final port")]


# ---------------------------------------------------------------------------
# T10 — grain boyu kırpılmaz
# ---------------------------------------------------------------------------

HIBRIT_GEO = {
    # Gerçek /calculate koşumu (tarayıcıda ölçüldü, 3 Ağustos 2026)
    "chamber_diameter": 0.0798694395392226,
    "chamber_length": 1.5767234530137102,
    "pre_chamber_length": 0.0399347197696113,
    "post_chamber_length": 0.0239460812919720,
    "throat_diameter": 0.0217289802,
    "exit_diameter": 0.0653,
    "grain_design": {
        "grain_length_mm": 1512.8279013823321,
        "grain_outer_diameter_mm": 79.8694395392226,
        "port_diameter_initial_mm": 37.75382701195476,
        "port_diameter_final_mm": 53.21351398216008,
        "inhibitor": "outer_surface",
    },
    "structural_analysis": {
        "chamber_analysis": {
            "design_mode": "verify",
            "wall_thickness_used_mm": 5.0,
            "recommended_thickness": 8.329071753729403,
        }
    },
}


def test_t10_grain_boyu_kirpilmadan_cizilir():
    """Çizilen grain boyu = çözücünün boyu (eski kural: 0,92 × oda boyu).

    Ölçüldü: tasarım raporu 1512,8 mm derken 2B kesit ve 3B güverte
    1451 mm gösteriyordu (%4,1 kısa). Hangisinin doğru olduğu yakıt
    kütlesiyle çapraz doğrulandı: raporun kendi yazdığı 1,54 kg ancak
    1512,8 mm ile çıkıyor (1450,6 mm -> 1,475 kg).
    """
    fig = _fig(create_improved_motor_cross_section(HIBRIT_GEO))
    grain = _iz(fig, "Fuel grain")
    boy = grain["xmax"] - grain["xmin"]
    assert boy == pytest.approx(1512.8279013823321, abs=1e-6)
    # Eski kırpma değeri açıkça dışlanır
    assert boy != pytest.approx(0.92 * 1576.7234530137102, abs=1e-3)


def test_t10_grain_konumu_cozucunun_on_odasindan_gelir():
    """Grain başlangıcı = pre_chamber_length; %35 payı yalnız yedek yoldur.

    Ölçüldü: 39,9347 + 1512,8279 + 23,9461 = 1576,7086 mm ≈ chamber_length
    (1576,7235) — yani çözücü grain'in yerini zaten söylüyor.
    """
    fig = _fig(create_improved_motor_cross_section(HIBRIT_GEO))
    grain = _iz(fig, "Fuel grain")
    assert grain["xmin"] == pytest.approx(39.9347197696113, abs=1e-6)

    # Ön oda boyu yoksa eski %35 payına düşülür (yedek yol yaşıyor)
    geo = dict(HIBRIT_GEO)
    geo.pop("pre_chamber_length")
    fig2 = _fig(create_improved_motor_cross_section(geo))
    slack = 1576.7234530137102 - 1512.8279013823321
    assert _iz(fig2, "Fuel grain")["xmin"] == pytest.approx(0.35 * slack)


def test_t10_grain_kamaraya_sigmiyorsa_celiski_bildirilir():
    """Sığmayan grain sessizce kısaltılmaz; tam boyuyla çizilir + not düşülür."""
    geo = dict(HIBRIT_GEO, chamber_length=1.000)
    geo.pop("pre_chamber_length")
    fig = _fig(create_improved_motor_cross_section(geo))
    grain = _iz(fig, "Fuel grain")
    assert grain["xmax"] - grain["xmin"] == pytest.approx(1512.8279013823321,
                                                         abs=1e-6)
    assert any("Geometry conflict" in n for n in _notlar(fig))


def test_t10_3b_guverte_de_grain_boyunu_kirpmaz():
    """motor_viz3d.js'te 0,92 kırpması KALMAMALI (2B ile aynı kusurdu)."""
    src = open(VIZ3D_JS, encoding="utf-8").read()
    kod = re.sub(r"(?m)^\s*//.*$", "", src)
    assert "0.92 * Lch" not in kod and "0.92*Lch" not in kod, (
        "3B güverte grain boyunu hâlâ %8 kırpıyor")
    # Grain dışı ve ön oda çözücüden okunuyor
    assert "grain_outer_diameter_mm" in kod
    assert "pre_chamber_length" in kod


def test_t10_3b_guverte_cidar_semalari_sunucuyla_ayni():
    """Güvertedeki cidar şema tablosu sunucudakiyle BİREBİR aynı olmalı.

    Aksi hâlde aynı motorun 3B modeli ile 2B kesiti farklı cidar çizer
    (katı/sıvı motorlarda güverte yalnız hibrit şemasını tanıyordu).
    """
    from hrma.export.cad_visualization import CHAMBER_WALL_SCHEMAS

    src = open(VIZ3D_JS, encoding="utf-8").read()
    blok = re.search(r"CASING_WALL_SCHEMAS\s*=\s*\[(.*?)\];", src, re.S)
    assert blok, "güvertede CASING_WALL_SCHEMAS tablosu yok"
    for blok_adi, used_key, rec_key, _kesin in CHAMBER_WALL_SCHEMAS:
        for alan in (blok_adi, used_key, rec_key):
            assert f"'{alan}'" in blok.group(1), f"güvertede eksik alan: {alan}"


# ---------------------------------------------------------------------------
# T11 — 'Tank' çubuğu
# ---------------------------------------------------------------------------

HIBRIT_MOTOR = {
    "mdot_total": 0.549, "mdot_ox": 0.392, "mdot_f": 0.157,
    "chamber_pressure": 20.0, "burn_time": 10.0,
}
HIBRIT_INJ = {"pressure_drop": 4.0, "exit_velocity": 20.32}


def test_t11_tank_cubugu_yalniz_gercek_tank_basinciyla_adlandirilir():
    """Ölçüldü: tank 30/50/90 bar girildi, çubuk üçünde de 24,0 bar (Pc+ΔP).

    /calculate yanıtında 'tank' geçen anahtar YOK (grep boş), yani geri-düşüş
    dalı her zaman çalışıyor. Türetilen sayı yanlış değil — adı yanlıştı:
    Pc + ΔP_enjektör, enjektörün GİRİŞ basıncıdır; tank basıncı ondan besleme
    hattı kayıpları kadar yüksektir. 30 bar girilen bir tank için 24 bar
    yazmak etiketin yanlış olduğunun tek başına kanıtıdır.
    """
    fig = _fig(create_performance_plots(HIBRIT_MOTOR, HIBRIT_INJ))
    bar = [t for t in fig["data"] if t.get("type") == "bar"][1]
    assert bar["y"] == [pytest.approx(20.0), pytest.approx(24.0),
                        pytest.approx(4.0)]
    assert "Tank" not in bar["x"], (
        "çözücü tank basıncı vermiyorken çubuk 'Tank' diye etiketlendi")
    assert bar["x"][1] == "Inj. inlet"


def test_t11_gercek_tank_basinci_varsa_tank_adi_kullanilir():
    """Karşı kanıt: değer gerçekten geldiğinde çubuk yine 'Tank' olur."""
    md = dict(HIBRIT_MOTOR, tank_pressure=50.0)
    fig = _fig(create_performance_plots(md, HIBRIT_INJ))
    bar = [t for t in fig["data"] if t.get("type") == "bar"][1]
    assert bar["x"] == ["Chamber", "Tank", "Inj. ΔP"]
    assert bar["y"][1] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# T18 — yabancı yüzeye tasarım noktası basılmaz
# ---------------------------------------------------------------------------

def test_t18_itici_kimligi_yoksa_tasarim_noktasi_cizilmez():
    """Yüzey referans çiftiyle çözüldüyse motorun tasarım noktası basılmaz.

    Ölçüldü (/liquid PERFORMANCE): sayfa RP-1/LOX sıvı motor tasarlarken
    grafiğin alt başlığı 'N2O / HTPB (reference pair — propellant identity
    not supplied)' diyor, buna rağmen aynı grafikte RP-1/LOX motorun tasarım
    noktası (Pc 100 bar, O/F 2,5) kırmızı haçla basılıyordu. İki farklı itici
    sisteminin sayıları tek 3B grafikte üst üste geliyordu.
    """
    fig = _fig(create_chamber_pressure_mixture_ratio_3d_surface({
        "base_isp": 244.9, "optimal_of_ratio": 2.5,
        "optimal_chamber_pressure": 100.0, "grid_n": 3,
    }))
    adlar = _iz_adlari(fig)
    assert "Design point (motor result)" not in adlar
    assert "reference pair" in json.dumps(fig["layout"]["title"])
    assert any("NOT drawn" in n for n in _notlar(fig)), "gerekçe yazılmadı"


def test_t18_itici_kimligi_verildiyse_tasarim_noktasi_cizilir():
    """Karşı kanıt: kimlik geldiğinde nokta yine basılır (test susturmuyor)."""
    fig = _fig(create_chamber_pressure_mixture_ratio_3d_surface({
        "base_isp": 244.9, "optimal_of_ratio": 2.5,
        "optimal_chamber_pressure": 100.0, "grid_n": 3,
        "fuel_type": "htpb", "oxidizer_type": "n2o",
    }))
    assert "Design point (motor result)" in _iz_adlari(fig)
    assert "reference pair" not in json.dumps(fig["layout"]["title"])


# ---------------------------------------------------------------------------
# T39 — sıvı oda cidarı imalat çıktısıyla aynı
# ---------------------------------------------------------------------------

def test_t39_sivi_oda_cidari_tasarim_kalinligidir():
    """Kesit 'chamber_structure' şemasını tanır; 0,045·D yedeğine düşmez.

    Ölçüldü: kullanıcı girdisi 5 mm, DXF metni 5,00 mm, STEP kamara katısı
    5,000 mm, teknik çizim PDF'i 5,00 mm; ekrandaki kesit ise 3,0 mm (oda
    Ø61,62 mm için 0,045·D = 2,773 -> 3,0 alt sınırı) çiziyordu. Sebep:
    cidar yalnız ``chamber_analysis.recommended_thickness`` yolundan
    aranıyordu, sıvı çözücü bloğu ``chamber_structure`` adını kullanıyor.
    """
    fig = _fig(create_improved_motor_cross_section(_sivi_geo(),
                                                   motor_type="liquid"))
    assert _cizilen_cidar(fig, 61.6228) == pytest.approx(5.0)
    # Eski yedek değeri açıkça dışlanır
    assert _cizilen_cidar(fig, 61.6228) != pytest.approx(3.0, abs=1e-3)


def test_t39_kunye_hangi_kalinligin_cizildigini_soyler():
    """Çizilen cidar ile yapısal önerinin farkı künyede görünür olmalı."""
    fig = _fig(create_improved_motor_cross_section(_sivi_geo(wall=5.0,
                                                             required=6.677),
                                                   motor_type="liquid"))
    hover = [t.get("hovertext") for t in fig["data"]
             if t.get("name") == "Chamber wall"][0]
    assert "5.00 mm" in hover
    assert "6.68 mm" in hover and "recommends" in hover


def test_t39_yapisal_sonuc_yoksa_kunye_tahmin_oldugunu_soyler():
    """Yedek yola düşüldüyse künye 'geometric estimate' der — sessiz sayı yok."""
    geo = _sivi_geo()
    geo.pop("structural_analysis")
    fig = _fig(create_improved_motor_cross_section(geo, motor_type="liquid"))
    hover = [t.get("hovertext") for t in fig["data"]
             if t.get("name") == "Chamber wall"][0]
    assert "geometric estimate" in hover


# ---------------------------------------------------------------------------
# T43 — enjeksiyon hızı: hangi devre, kaç m/s
# ---------------------------------------------------------------------------

SIVI_MOTOR = {
    "mixture_ratio": 2.5, "chamber_pressure": 100.0, "total_mass_flow": 4.164,
    "feed_system": {
        "mass_flow_rates": {"oxidizer": 2.975, "fuel": 1.190, "total": 4.164},
        "pressure_drops": {"tank_outlet": 0.08, "main_valve": 0.024,
                           "filters": 1.609, "feed_lines": 0.564,
                           "injector": 20.0,
                           "pump_discharge_pressure_ox": 122.277},
    },
    "injector_design": {
        "injection_pressure_drop_ox_bar": 20.0,
        # Gerçek koşumdan (Excel 'Injector' sayfasıyla da eşleşir)
        "ox_injection_velocity_m_s": 41.44334159530864,
        "fuel_injection_velocity_m_s": 49.49747468305833,
    },
}


def test_t43_enjeksiyon_hizi_iki_devreyi_de_adiyla_gosterir():
    """Gösterge hangi akışkanın hızı olduğunu söylemiyordu; yakıt hiç yoktu.

    Ölçüldü: gösterge '41,4 m/s' yazıyordu (OKSİTLEYİCİ hızı, Excel
    çıktısıyla eşleştirilerek belirlendi); YAKIT devresi 49,50 m/s ile
    kırmızı bandın hemen dibindeydi ama hiçbir yerde gösterilmiyordu.
    """
    fig = _fig(create_performance_plots(SIVI_MOTOR, None))
    basliklar = [a["text"] for a in fig["layout"].get("annotations", [])]
    assert "Injection Velocity" in basliklar
    assert "Injector Performance" not in basliklar, (
        "panel hangi büyüklüğü gösterdiğini hâlâ söylemiyor")

    bar = [t for t in fig["data"] if t.get("type") == "bar"][-1]
    assert bar["x"] == ["Oxidizer", "Fuel"]
    assert bar["y"] == [pytest.approx(41.44334159530864),
                        pytest.approx(49.49747468305833)]


def test_t43_yakit_hizi_yoksa_panel_uydurmaz():
    """Yakıt hızı gelmezse yalnız oksitleyici çubuğu kalır — sıfır uydurulmaz."""
    md = json.loads(json.dumps(SIVI_MOTOR))
    md["injector_design"].pop("fuel_injection_velocity_m_s")
    fig = _fig(create_performance_plots(md, None))
    bar = [t for t in fig["data"] if t.get("type") == "bar"][-1]
    assert bar["x"] == ["Oxidizer"]
    assert len(bar["y"]) == 1


def test_t43_hibrit_gostergesi_de_adini_tasir():
    """Hibritte enjektörden yalnız oksitleyici geçer; başlık bunu söyler."""
    fig = _fig(create_performance_plots(HIBRIT_MOTOR, HIBRIT_INJ))
    basliklar = [a["text"] for a in fig["layout"].get("annotations", [])]
    assert "Oxidizer Injection Velocity" in basliklar
    assert "Injector Performance" not in basliklar


# ---------------------------------------------------------------------------
# Genel: uydurma/çökme kalkanı
# ---------------------------------------------------------------------------

def test_eksik_geometride_kesit_cokmez():
    """Alanlar eksik/bozukken kesit hata atmadan üretilmeli."""
    for md in ({}, {"chamber_diameter": None},
               {"grain_design": {"outer_diameter_mm": "abc"}},
               {"structural_analysis": {"case_analysis": {}}}):
        for tip in ("hybrid", "solid", "liquid"):
            fig = _fig(create_improved_motor_cross_section(md, motor_type=tip))
            assert fig["data"], f"{tip}: hiç iz üretilmedi"


def test_kesit_ciktisinda_bdata_yok():
    """plotly 6 base64 blokları paketlenmiş plotly.js 1.58.5'i kırıyor."""
    for geo, tip in ((_kati_geo(), "solid"), (_sivi_geo(), "liquid"),
                     (HIBRIT_GEO, "hybrid")):
        js = create_improved_motor_cross_section(geo, motor_type=tip)
        assert '"bdata"' not in js and "base64" not in js


def test_grain_disi_kasa_deligini_asamaz():
    """Bozuk veri (grain > kasa) çizimi ters çevirmemeli."""
    fig = _fig(create_improved_motor_cross_section(
        _kati_geo(grain_design={"outer_diameter_mm": 400.0}),
        motor_type="solid"))
    grain = _iz(fig, "Fuel grain")
    assert grain["ymax"] <= 50.0 + 1e-9
    assert math.isfinite(grain["ymax"])
