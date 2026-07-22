#!/usr/bin/env python3
"""
Canlı harici API erişim testleri (PubChem, NIST WebBook).

Bu testler GERÇEK ağ istekleri atar; amaç dış veri kaynaklarının hâlâ
erişilebilir ve beklenen içeriği döndürüyor olduğunu doğrulamaktır.
Ağ yoksa/ulaşılamıyorsa test FAIL değil SKIP olur (çevrimdışı ortamda
süit kırılmaz). Eski sürüm assert yerine True/False döndürüyordu — bu
hem PytestReturnNotNoneWarning veriyor hem de başarısızlıkta sahte
PASS üretiyordu (2026-07-16 denetim bulgusu).
"""

import json

import pytest
import requests

from hrma.data.open_source_propellant_api import propellant_api

NETWORK_TIMEOUT = 15  # s


def _get_or_skip(url: str, **kwargs) -> requests.Response:
    """GET at; ağ hatasında testi atla (çevrimdışı ortam FAIL üretmesin)."""
    try:
        return requests.get(url, timeout=NETWORK_TIMEOUT, **kwargs)
    except (requests.ConnectionError, requests.Timeout) as exc:
        pytest.skip(f"network unavailable: {exc.__class__.__name__}")


def test_pubchem_api():
    """PubChem: N2O için CID + molekül özellikleri gerçekten dönüyor."""
    compound = "nitrous oxide"

    response = _get_or_skip(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{compound}/cids/TXT"
    )
    if response.status_code >= 500:
        pytest.skip(f"PubChem server error: {response.status_code}")
    assert response.status_code == 200, f"PubChem CID sorgusu: {response.status_code}"

    cid = response.text.strip().splitlines()[0]
    assert cid.isdigit(), f"CID sayısal değil: {cid!r}"

    prop_response = _get_or_skip(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}"
        f"/property/MolecularFormula,MolecularWeight,IUPACName/JSON"
    )
    if prop_response.status_code >= 500:
        pytest.skip(f"PubChem server error: {prop_response.status_code}")
    assert prop_response.status_code == 200

    props = prop_response.json()['PropertyTable']['Properties'][0]
    assert props['MolecularFormula'] == 'N2O'
    # MW string veya sayı gelebilir; N2O ~44.01 g/mol
    assert abs(float(props['MolecularWeight']) - 44.01) < 0.5


def test_nist_webbook():
    """NIST WebBook: H2O2 CAS sorgusu gerçek içerik döndürüyor."""
    cas = "7722-84-1"  # H2O2
    response = _get_or_skip(
        f"https://webbook.nist.gov/cgi/cbook.cgi?ID={cas}&Units=SI"
    )
    if response.status_code >= 500:
        pytest.skip(f"NIST server error: {response.status_code}")
    assert response.status_code == 200, f"NIST WebBook: {response.status_code}"
    assert "Hydrogen peroxide" in response.text, "beklenen bileşik içeriği yok"


def test_comprehensive_fetch():
    """Entegre sorgu: ağ olsun olmasın dict dönmeli (fallback zinciri)."""
    for compound in ('hydrogen', 'oxygen', 'methane'):
        props = propellant_api.get_comprehensive_properties(compound)
        assert isinstance(props, dict), f"{compound}: dict bekleniyordu"


def test_ui_integration():
    """UI formatlayıcı: temel alanlar her koşulda dolu ve serileştirilebilir."""
    for ptype, name in (('hybrid_fuel', 'htpb'), ('oxidizer', 'oxygen')):
        ui_data = propellant_api.get_propellant_for_ui(ptype, name)
        assert isinstance(ui_data, dict) and ui_data, f"{ptype}/{name} boş"
        json.dumps(ui_data)  # JSON-serileştirilebilir olmalı (UI kontratı)
