#!/usr/bin/env python3
"""
Test script to verify REAL-TIME API data fetching
"""

import requests
import json
from open_source_propellant_api import propellant_api

def test_pubchem_api():
    """Test PubChem API directly"""
    print("\n=== TESTING PUBCHEM API ===")
    
    # Test for Nitrous Oxide
    compound = "nitrous oxide"
    print(f"Fetching data for: {compound}")
    
    # Get CID
    cid_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{compound}/cids/TXT"
    response = requests.get(cid_url)
    
    if response.status_code == 200:
        cid = response.text.strip()
        print(f"CID found: {cid}")
        
        # Get properties
        prop_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,IUPACName/JSON"
        prop_response = requests.get(prop_url)
        
        if prop_response.status_code == 200:
            data = prop_response.json()
            props = data['PropertyTable']['Properties'][0]
            print(f"Formula: {props['MolecularFormula']}")
            print(f"Molecular Weight: {props['MolecularWeight']} g/mol")
            print(f"IUPAC Name: {props['IUPACName']}")
            return True
    
    print("PubChem API failed")
    return False

def test_nist_webbook():
    """Test NIST WebBook access"""
    print("\n=== TESTING NIST WEBBOOK ===")
    
    # Test for Hydrogen Peroxide
    cas = "7722-84-1"  # H2O2 CAS number
    url = f"https://webbook.nist.gov/cgi/cbook.cgi?ID={cas}&Units=SI"
    
    response = requests.get(url)
    if response.status_code == 200:
        print(f"NIST WebBook accessible")
        print(f"Data length: {len(response.text)} bytes")
        
        # Check if we got real data
        if "Hydrogen peroxide" in response.text:
            print(f"Compound data found")
            return True
    
    print("NIST WebBook failed")
    return False

def test_comprehensive_fetch():
    """Test the complete API integration"""
    print("\n=== TESTING COMPREHENSIVE API ===")
    
    compounds = ['hydrogen', 'oxygen', 'methane', 'hydrazine']
    
    for compound in compounds:
        print(f"\nFetching: {compound}")
        props = propellant_api.get_comprehensive_properties(compound)
        
        if props:
            print(f"Data retrieved:")
            print(f"  - CID: {props.get('cid', 'N/A')}")
            print(f"  - Formula: {props.get('formula', 'N/A')}")
            print(f"  - MW: {props.get('molecular_weight', 'N/A')} g/mol")
            print(f"  - Density: {props.get('density', 'N/A')} kg/m³")
            print(f"  - Source: {props.get('source', 'N/A')}")

def test_ui_integration():
    """Test UI data formatting"""
    print("\n=== TESTING UI INTEGRATION ===")
    
    # Test hybrid fuel
    print("\nHybrid Fuel - HTPB:")
    ui_data = propellant_api.get_propellant_for_ui('hybrid_fuel', 'htpb')
    print(json.dumps(ui_data, indent=2))
    
    # Test liquid oxidizer
    print("\nLiquid Oxidizer - LOX:")
    ui_data = propellant_api.get_propellant_for_ui('oxidizer', 'oxygen')
    print(json.dumps(ui_data, indent=2))

if __name__ == "__main__":
    print("="*50)
    print("REAL-TIME API VERIFICATION TEST")
    print("="*50)
    
    # Run tests
    pubchem_ok = test_pubchem_api()
    nist_ok = test_nist_webbook()
    
    test_comprehensive_fetch()
    test_ui_integration()
    
    print("\n" + "="*50)
    print("TEST RESULTS:")
    print(f"PubChem API: {'WORKING' if pubchem_ok else 'FAILED'}")
    print(f"NIST WebBook: {'WORKING' if nist_ok else 'FAILED'}")
    print("="*50)