"""Analiz modulleri."""

try:
    from hrma.analysis.cfd_analysis import cfd_analyzer, CFD2DAnalyzer
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    from hrma.analysis.structural_analysis import StructuralAnalyzer
    from hrma.analysis.safety_analysis import SafetyAnalyzer
    from hrma.analysis.kinetic_analysis import kinetic_analyzer, NozzleKineticAnalyzer
    from hrma.analysis.regression_analysis import regression_analyzer, RegressionAnalyzer
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import some analysis modules: {e}")
