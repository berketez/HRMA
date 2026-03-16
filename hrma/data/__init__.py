"""Veri kaynaklari ve veritabani modulleri."""

try:
    from hrma.data.propellant_database import propellant_db, PropellantDatabase
    from hrma.data.chemical_database import chemical_db, ChemicalDatabase
    from hrma.data.open_source_propellant_api import propellant_api, OpenSourcePropellantAPI
    from hrma.data.external_data_fetcher import data_fetcher, ExternalDataFetcher
    from hrma.data.database_integrations import DatabaseManager
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import some data modules: {e}")
