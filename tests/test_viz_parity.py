"""Görselleştirme paritesi — hibrit / katı / sıvı panosu aynı kalitede olmalı.

Berke şikayeti (2026-07-19): performans panosu YALNIZ hibrit sayfasında
çıkıyordu; katı ve sıvı sayfalarında hiç yoktu. create_performance_plots
hibrit alan adlarına (mdot_ox / mdot_f / port_history / injector.pressure_drop)
sertçe bağlıydı. Bu testler:

  1. Hibrit panonun YAPISININ değişmediğini (regresyon kalkanı),
  2. Katı ve sıvı için gerçek verilerden pano üretildiğini,
  3. Veri eksikse panelin UYDURULMAYIP atlandığını ve çökmediğini,
  4. Üretilen JSON'da plotly 6 'bdata' (base64) bloğu KALMADIĞINI
     (paketlenmiş plotly.js 1.58.5 çözemez → boş çizgi bugı),
  5. motor_viz_deck.js'in sözdizimi + güverte paritesini

doğrular. Fikstürler sentetiktir: çözücü modülleri paralel olarak
değiştirilirken bile bu sözleşme testleri deterministik kalsın diye.
"""

import json
import math
import os
import re
import shutil
import subprocess

import numpy as np
import pytest

from hrma.visualization.visualization import (
    _perf_grid,
    _perf_motor_type,
    create_performance_plots,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIZ_PY = os.path.join(REPO_ROOT, "hrma", "visualization", "visualization.py")
DECK_JS = os.path.join(REPO_ROOT, "hrma", "static", "js", "motor_viz_deck.js")


# ---------------------------------------------------------------------------
# Fikstürler — gerçek çözücü çıktılarının şemasıyla birebir aynı anahtarlar
# ---------------------------------------------------------------------------

HYBRID_MOTOR = {
    "mdot_total": 0.62,
    "mdot_ox": 0.53,
    "mdot_f": 0.09,
    "chamber_pressure": 30.0,
    "tank_pressure": 50.0,
    "burn_time": 10.0,
    "port_history": {
        "time": [0.0, 2.5, 5.0, 7.5, 10.0],
        "port_diameter": [0.030, 0.034, 0.038, 0.042, 0.046],
    },
}

HYBRID_INJECTOR = {"pressure_drop": 8.5, "exit_velocity": 42.0}


def _solid_motor(n=40):
    """Katı çözücünün calculate_performance() çıktısının pano ile ilgili kısmı."""
    t = np.linspace(0.0, 2.2, n)
    area = np.linspace(0.1186, 0.0490, n)          # m^2 (regresif BATES)
    mdot = np.linspace(3.1, 1.3, n)                # kg/s
    press = np.linspace(41.0, 18.0, n)             # bar
    thrust = np.linspace(10800.0, 4200.0, n)       # N
    return {
        "grain_type": "bates",
        "propellant_type": "apcp",
        "chamber_pressure": 40.0,
        "burn_time": 2.2,
        "throat_diameter": 24.5,                   # mm
        "thrust_curve": {
            "time": t.tolist(),
            "thrust": thrust.tolist(),
            "pressure": press.tolist(),
            "burn_area": area.tolist(),
            "mass_flow": mdot.tolist(),
        },
        "grain_design": {"Kn_initial": 251.5, "Kn_final": 103.9},
    }


LIQUID_MOTOR = {
    "mixture_ratio": 2.5,
    "chamber_pressure": 100.0,
    "total_mass_flow": 3.2704,
    "feed_system": {
        "mass_flow_rates": {"oxidizer": 2.336, "fuel": 0.9344, "total": 3.2704},
        "pressure_drops": {
            "tank_outlet": 0.1, "main_valve": 0.5, "filters": 0.3,
            "feed_lines": 1.2, "injector": 3.0,
            "total_ox": 5.1, "total_fuel": 5.1,
            "pump_discharge_pressure_ox": 105.1,
        },
    },
    "injector_design": {
        "injection_pressure_drop_ox_bar": 22.0,
        "ox_injection_velocity_m_s": 48.42,
    },
}


def _fig(js):
    assert isinstance(js, str), "create_performance_plots bir JSON string döndürmeli"
    return json.loads(js)


def _titles(fig):
    return [a["text"] for a in fig["layout"].get("annotations", [])]


def _trace(fig, name):
    for tr in fig["data"]:
        if tr.get("name") == name:
            return tr
    return None


# ---------------------------------------------------------------------------
# (b) Hibrit regresyon kalkanı
# ---------------------------------------------------------------------------

def test_hibrit_pano_yapisi_korunur():
    js = create_performance_plots(HYBRID_MOTOR, HYBRID_INJECTOR)
    fig = _fig(js)

    assert _titles(fig) == [
        "Mass Flow Rates",
        "Pressure Distribution",
        "Regression Rate & Port Growth",
        "Injector Performance",
    ]
    assert [t.get("type") for t in fig["data"]] == [
        "bar", "bar", "scatter", "scatter", "indicator",
    ]
    assert fig["layout"]["title"]["text"] == "Hybrid Rocket Performance Analysis"
    assert fig["layout"]["height"] == 850

    # Tank çubuğu kullanıcının girdiği GERÇEK tank basıncını gösterir
    bar_press = fig["data"][1]
    assert bar_press["x"] == ["Chamber", "Tank", "Inj. ΔP"]
    assert bar_press["y"] == [30.0, 50.0, 8.5]

    # Gösterge: enjektör çıkış hızı, 0-100 m/s tam skala (eski davranış)
    gauge = fig["data"][4]
    assert gauge["value"] == pytest.approx(42.0)
    assert gauge["gauge"]["axis"]["range"] == [0, 100]
    assert gauge["gauge"]["threshold"]["value"] == pytest.approx(50.0)


def test_hibrit_tank_basinci_yoksa_enjektorden_turetilir():
    md = dict(HYBRID_MOTOR)
    md.pop("tank_pressure")
    fig = _fig(create_performance_plots(md, HYBRID_INJECTOR))
    assert fig["data"][1]["y"] == [30.0, 38.5, 8.5]


def test_hibrit_regresyon_hizi_port_gecmisinin_turevidir():
    fig = _fig(create_performance_plots(HYBRID_MOTOR, HYBRID_INJECTOR))
    port = _trace(fig, "Port Diameter Growth")
    assert port is not None
    assert port["y"][0] == pytest.approx(30.0)     # mm
    assert port["y"][-1] == pytest.approx(46.0)
    # r = (dD/dt)/2 = (0.016 m / 10 s)/2 = 0.8 mm/s
    reg = [t for t in fig["data"] if str(t.get("name", "")).startswith("Regression Rate")]
    assert len(reg) == 1
    assert reg[0]["y"][0] == pytest.approx(0.8, rel=1e-6)


# ---------------------------------------------------------------------------
# (a) Üç motor tipi için de pano üretilir
# ---------------------------------------------------------------------------

def test_motor_tipi_alan_varligindan_tespit_edilir():
    assert _perf_motor_type(HYBRID_MOTOR) == "hybrid"
    assert _perf_motor_type(_solid_motor()) == "solid"
    assert _perf_motor_type(LIQUID_MOTOR) == "liquid"
    # Açık anahtar her zaman önceliklidir
    assert _perf_motor_type({"motor_type": "liquid", "mdot_ox": 1, "mdot_f": 1}) == "liquid"
    assert _perf_motor_type({"viz_motor_type": "solid"}) == "solid"


def test_kati_pano_uretilir():
    solid = _solid_motor()
    fig = _fig(create_performance_plots(solid, None))

    assert fig["layout"]["title"]["text"] == "Solid Rocket Performance Analysis"
    assert _titles(fig) == [
        "Propellant Mass Flow",
        "Pressure Distribution",
        "Thrust & Chamber Pressure vs Time",
        "Burn Area & Kn vs Time",
    ]

    curve = solid["thrust_curve"]
    mdot_bar = fig["data"][0]
    assert mdot_bar["x"] == ["Peak", "Average", "Burnout"]
    assert mdot_bar["y"][0] == pytest.approx(max(curve["mass_flow"]))
    assert mdot_bar["y"][2] == pytest.approx(curve["mass_flow"][-1])

    press_bar = fig["data"][1]
    assert press_bar["x"] == ["Design Pc", "Peak", "Average"]
    assert press_bar["y"][0] == pytest.approx(40.0)
    assert press_bar["y"][1] == pytest.approx(max(curve["pressure"]))

    thrust = _trace(fig, "Thrust")
    assert thrust is not None and thrust["y"][0] == pytest.approx(curve["thrust"][0])

    # Kn = A_burn / A_throat — boğaz çapı mm cinsindendir
    a_t = math.pi * (solid["throat_diameter"] / 1000.0 / 2.0) ** 2
    kn = _trace(fig, "Kn")
    assert kn is not None
    assert kn["y"][0] == pytest.approx(curve["burn_area"][0] / a_t)

    area = _trace(fig, "Burn Area")
    assert area["y"][0] == pytest.approx(curve["burn_area"][0] * 1e4)   # cm²


def test_sivi_pano_uretilir():
    fig = _fig(create_performance_plots(LIQUID_MOTOR, None))

    assert fig["layout"]["title"]["text"] == "Liquid Rocket Performance Analysis"
    assert _titles(fig) == [
        "Mass Flow Rates",
        "Pressure Distribution",
        "Feed System Pressure Budget",
        "Injector Performance",
    ]

    rates = LIQUID_MOTOR["feed_system"]["mass_flow_rates"]
    assert fig["data"][0]["y"] == [
        pytest.approx(rates["total"]),
        pytest.approx(rates["oxidizer"]),
        pytest.approx(rates["fuel"]),
    ]
    # Besleme = pompa çıkış basıncı, ΔP = enjektör tasarımından
    assert fig["data"][1]["x"] == ["Chamber", "Feed", "Inj. ΔP"]
    assert fig["data"][1]["y"] == [
        pytest.approx(100.0), pytest.approx(105.1), pytest.approx(22.0),
    ]
    # Bütçe paneli YALNIZ bileşen kayıplarını içerir (total_* hariç)
    budget = fig["data"][2]
    assert budget["x"] == ["Tank Outlet", "Main Valve", "Filters",
                           "Feed Lines", "Injector"]
    # Gösterge 100 m/s'yi aşmayan gerçek enjeksiyon hızını gösterir
    assert fig["data"][3]["value"] == pytest.approx(48.42)


def test_sivi_enjektor_hizi_tam_skalayi_asarsa_olcek_buyur():
    md = json.loads(json.dumps(LIQUID_MOTOR))
    md["injector_design"]["ox_injection_velocity_m_s"] = 130.0
    fig = _fig(create_performance_plots(md, None))
    gauge = fig["data"][-1]
    assert gauge["gauge"]["axis"]["range"] == [0, 150]
    assert gauge["gauge"]["threshold"]["value"] == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# (c) Eksik veride panel atlanır, çökme yok
# ---------------------------------------------------------------------------

def test_izgara_panel_sayisina_gore_kurulur():
    assert _perf_grid(1)[:2] == (1, 1)
    assert _perf_grid(2)[:2] == (1, 2)
    rows, cols, slots = _perf_grid(3)
    assert (rows, cols) == (2, 2)
    assert slots[2] == (2, 1, 2)          # tek kalan panel satırı kaplar
    assert _perf_grid(4)[:2] == (2, 2)


def test_eksik_veride_panel_atlanir():
    # port_history + enjektör verisi YOK → yalnız 2 çubuk paneli kalır
    md = {"mdot_total": 0.62, "mdot_ox": 0.53, "mdot_f": 0.09,
          "chamber_pressure": 30.0, "tank_pressure": 50.0}
    fig = _fig(create_performance_plots(md, None))
    assert _titles(fig) == ["Mass Flow Rates", "Pressure Distribution"]
    assert fig["layout"]["height"] == 425          # tek satır

    # Katıda itki eğrisi yoksa yalnız tasarım basıncı paneli kalır
    fig2 = _fig(create_performance_plots(
        {"grain_type": "bates", "propellant_type": "apcp",
         "chamber_pressure": 40.0}, None))
    assert _titles(fig2) == ["Pressure Distribution"]


def test_hicbir_veri_yoksa_cokmez():
    for payload in ({}, None, {"garbage": "x"}, {"mdot_ox": None, "mdot_f": None}):
        fig = _fig(create_performance_plots(payload, None))
        assert fig["data"] == []
        assert "No performance data available" in json.dumps(fig["layout"])


def test_bozuk_seriler_paneli_dusurur_hata_atmaz():
    solid = _solid_motor()
    solid["thrust_curve"]["burn_area"] = ["nan", None, 3]
    solid["thrust_curve"]["mass_flow"] = []
    fig = _fig(create_performance_plots(solid, None))
    titles = _titles(fig)
    assert "Burn Area & Kn vs Time" not in titles
    assert "Propellant Mass Flow" not in titles
    assert "Thrust & Chamber Pressure vs Time" in titles


def test_injector_data_opsiyoneldir():
    # Katı motorda enjektör yoktur; çağrı ikinci argüman olmadan da çalışır
    fig = _fig(create_performance_plots(_solid_motor()))
    assert len(fig["data"]) > 0


# ---------------------------------------------------------------------------
# (a/3) bdata süpürmesi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    ("hybrid", HYBRID_MOTOR, HYBRID_INJECTOR),
    ("solid", _solid_motor(), None),
    ("liquid", LIQUID_MOTOR, None),
])
def test_json_ciktisinda_bdata_yok(payload):
    _tag, motor, injector = payload
    js = create_performance_plots(motor, injector)
    assert '"bdata"' not in js, f"{_tag}: plotly 6 base64 bloğu sızdı"
    assert "base64" not in js


def test_numpy_dizileri_bdata_uretmez():
    """Çözücüler numpy dizisi verirse de JSON saf liste olmalı."""
    solid = _solid_motor()
    solid["thrust_curve"] = {
        k: np.asarray(v, dtype=float) for k, v in solid["thrust_curve"].items()
    }
    js = create_performance_plots(solid, None)
    assert '"bdata"' not in js
    fig = _fig(js)
    thrust = _trace(fig, "Thrust")
    assert isinstance(thrust["y"], list)
    assert all(isinstance(v, float) for v in thrust["y"])


def test_tum_figur_ureticileri_fig_json_kapisindan_gecer():
    """visualization.py'de ham fig.to_json()/to_dict() dönüşü kalmamalı.

    bdata koruması TEK kapıdadır (_fig_json). Yeni bir figür üreticisi bu
    kapıyı atlarsa katı/sıvı yolunda yine boş çizgi bugı doğar.
    """
    src = open(VIZ_PY, encoding="utf-8").read()
    assert "return fig.to_json()" not in src
    assert re.search(r"return\s+\w+\.to_json\(\)", src) is None
    # Fonksiyon sonu figür dönüşlerinin tamamı _fig_json ile sarılı
    returns = re.findall(r"return\s+(_fig_json\(fig\)|_perf_empty_figure\()", src)
    assert len(returns) >= 18, f"beklenenden az figür dönüşü: {len(returns)}"


# ---------------------------------------------------------------------------
# (d) 3D güverte paritesi
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node kurulu değil")
def test_deck_js_sozdizimi():
    r = subprocess.run(["node", "--check", DECK_JS],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_deck_js_hibrit_arac_cubugu_paritesi():
    """Katı/sıvı güvertesi hibrittekiyle aynı kontrol setini sunmalı."""
    src = open(DECK_JS, encoding="utf-8").read()
    for btn in ("_btn_cut", "_btn_dim", "_btn_plume", "_btn_exp",
                "_btn_portshape", "_btn_heat", "_btn_design", "_btn_rot",
                "_btn_cam", "_btn_quality", "_btn_speed", "_btn_reset"):
        assert btn in src, f"güvertede eksik kontrol: {btn}"
    # Hız kontrolü ve tasarım modu gerçekten kablolanmış olmalı
    assert "viz.cycleSpeed()" in src
    assert "viz.update(next)" in src


def test_deck_js_telemetri_cipleri_motor_tipine_duyarli():
    src = open(DECK_JS, encoding="utf-8").read()
    for chip in ("_port", "_web", "_of", "_isp", "_thrust", "_pc", "_eps", "_dt"):
        assert "p + '" + chip + "'" in src, f"eksik çip: {chip}"
    # Sıvıda port/web çipi basılmamalı; katıda O/F çipi basılmamalı
    assert "if (!isLiquid) {" in src
    assert "if (!isSolid &&" in src
    # O/F yalnız veri gerçekten varsa gösterilir (viz varsayılanı 2.0 uydurmasın)
    assert "isNum(md.of_ratio)" in src


def test_deck_js_kullanici_metinleri_ingilizce():
    """Kullanıcıya görünen dizgilerde Türkçe karakter olmamalı (yorumlar hariç)."""
    src = open(DECK_JS, encoding="utf-8").read()
    code = re.sub(r"/\*[\s\S]*?\*/", "", src)
    code = re.sub(r"(?m)^\s*//.*$", "", code)
    code = re.sub(r"(?m)//.*$", "", code)
    turkish = re.findall(r"['\"][^'\"\n]*[çğıİöşüÇĞÖŞÜ][^'\"\n]*['\"]", code)
    # 'MW/m²' gibi birimler serbest (² Türkçe harf değil, regex zaten almaz)
    assert not turkish, f"güvertede Türkçe kullanıcı metni: {turkish}"
