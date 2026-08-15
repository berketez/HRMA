"""Analiz modulleri."""

try:
    # v2.6.27 (teknik borç §4): emekli çözücülerin (cfd_analysis,
    # kinetic_analysis) paket-düzeyi importları kaldırıldı — uçları 501
    # dönüyor, ~2100 satır her açılışta boşuna yükleniyordu. Dosyalar
    # depoda duruyor (kaldırma/legacy taşıma kararı Berke'de); ihtiyaç
    # duyan, modülü doğrudan import eder.
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    from hrma.analysis.structural_analysis import StructuralAnalyzer
    from hrma.analysis.safety_analysis import SafetyAnalyzer
    from hrma.analysis.regression_analysis import regression_analyzer, RegressionAnalyzer
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import some analysis modules: {e}")
