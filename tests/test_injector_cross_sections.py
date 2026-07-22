# -*- coding: utf-8 -*-
"""Pintle ve swirl enjektör kesit görselleri — TODO stub'ların gerçek
figüre dönüştüğünü kalıcı doğrular (boş go.Figure regresyon koruması).

Kontroller:
- Dönen string json.loads ile çözülür (fig.to_json sözleşmesi)
- Figür boş değil: trace + shape toplamı > 3
- Parametre değişimi figürü değiştiriyor (geometri gerçekten girdiye bağlı)
- Varsayılan/eksik anahtarlarla çağrı hata fırlatmıyor
"""

import json

import pytest

from hrma.visualization.visualization import (
    create_pintle_cross_section,
    create_swirl_injector,
)

FONKSIYONLAR = [create_pintle_cross_section, create_swirl_injector]


def _parse(fn, data):
    out = fn(data)
    assert isinstance(out, str)
    return json.loads(out)


@pytest.mark.parametrize("fn", FONKSIYONLAR)
def test_json_parse_edilir(fn):
    fig = _parse(fn, {})
    assert "data" in fig
    assert "layout" in fig


@pytest.mark.parametrize("fn", FONKSIYONLAR)
def test_bos_figur_degil(fn):
    fig = _parse(fn, {})
    n_traces = len(fig.get("data", []))
    n_shapes = len(fig.get("layout", {}).get("shapes", []))
    assert n_traces + n_shapes > 3, (
        f"{fn.__name__} boş/iskelet figür döndürdü: "
        f"{n_traces} trace + {n_shapes} shape"
    )


@pytest.mark.parametrize("fn", FONKSIYONLAR)
def test_anotasyonlar_var(fn):
    # Boyut/akış anotasyonları çizimin parçası — hiç yoksa stub'a dönülmüş demektir
    fig = _parse(fn, {})
    annotations = fig.get("layout", {}).get("annotations", [])
    assert len(annotations) >= 3


def test_pintle_parametre_degisince_figur_degisir():
    a = create_pintle_cross_section({"pintle_diameter": 25})
    b = create_pintle_cross_section({"pintle_diameter": 40})
    assert a != b


def test_pintle_gap_degisince_figur_degisir():
    a = create_pintle_cross_section({"gap": 1.5})
    b = create_pintle_cross_section({"gap": 3.0})
    assert a != b


def test_swirl_parametre_degisince_figur_degisir():
    a = create_swirl_injector({"n_slots": 4})
    b = create_swirl_injector({"n_slots": 8})
    assert a != b


def test_swirl_slot_sayisi_traces_yansir():
    # Her yuva ayrı trace: n_slots artınca trace sayısı da artmalı
    a = json.loads(create_swirl_injector({"n_slots": 4}))
    b = json.loads(create_swirl_injector({"n_slots": 8}))
    assert len(b["data"]) > len(a["data"])


@pytest.mark.parametrize("fn", FONKSIYONLAR)
@pytest.mark.parametrize("data", [
    {},                                     # tüm anahtarlar eksik → varsayılanlar
    {"outer_diameter": 80},                 # kısmi girdi
    {"pintle_diameter": 60, "gap": 0.5},    # pintle özel: dar aralık
    {"n_slots": 12, "slot_width": 3.0},     # swirl özel: çok yuva
    {"n_slots": 1},                         # sınır: tek yuva
])
def test_eksik_anahtarlarla_hata_firlatmaz(fn, data):
    fig = _parse(fn, data)
    assert len(fig.get("data", [])) > 0


def test_pintle_tutarsiz_girdi_korunur():
    # Pintle + gap gövde çapını aşarsa fonksiyon çökmeden ölçek düzeltmeli
    fig = _parse(create_pintle_cross_section,
                 {"outer_diameter": 30, "pintle_diameter": 40, "gap": 5})
    assert len(fig["data"]) > 0
