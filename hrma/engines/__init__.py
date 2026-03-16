"""Motor hesaplama modulleri."""

try:
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    from hrma.engines.nozzle_design import NozzleDesigner
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import some engine modules: {e}")
