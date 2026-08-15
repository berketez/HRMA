"""Fiziksel sabitlerin tek-tanım-noktası bekçisi (v2.6.27).

BULGU (15 Ağustos 2026, mimari tarama): Stefan-Boltzmann sabiti 6 ayrı
dosyada ayrı ayrı tanımlıydı (thermal_protection, heat_transfer_analysis,
solid_rocket_engine SOLID_THERMAL, safety_analysis, structural_analysis,
fea/thermal_axisym). Değerler aynıydı — yani kusur değil, kural ihlaliydi:
parametre tutarlılığı kuralı "bir kavram, bir tanım noktası" der; altı kopya,
birinin sessizce farklılaşmasına açık kapıdır.

Bu dosya iki şeyi kilitler: (1) depoda merkez dışında literal tanım yok,
(2) tüketicilerin gördüğü değer merkezle bire bir aynı.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stefan_boltzmann_tek_tanim_noktasi():
    """Literal 5.670374419e-8 yalnız hrma/constants.py'de yazılabilir.

    Yeni bir dosyaya yerel kopya eklenirse bu test kırılır; doğru hamle
    `from hrma.constants import STEFAN_BOLTZMANN` satırıdır.
    """
    sonuc = subprocess.run(
        ['git', 'grep', '-l', '5.670374419e-8', '--', 'hrma/*.py',
         'hrma/**/*.py'],
        cwd=ROOT, capture_output=True, text=True)
    dosyalar = [s for s in sonuc.stdout.splitlines() if s.strip()]
    assert dosyalar == ['hrma/constants.py'], (
        'Stefan-Boltzmann literali merkez dışında da tanımlı: %s — yerel '
        'kopya yasak, hrma.constants.STEFAN_BOLTZMANN import edilmeli.'
        % dosyalar)


def test_tuketiciler_merkezle_ayni_nesne():
    """Altı eski tanım yerinin tamamı merkez değeri görmeli."""
    from hrma.constants import STEFAN_BOLTZMANN as merkez
    import hrma.analysis.thermal_protection as tp
    import hrma.analysis.safety_analysis as sa
    import hrma.analysis.heat_transfer_analysis as ht
    import hrma.analysis.structural_analysis as st  # import hatasını yakalar
    import hrma.fea.thermal_axisym as fea
    import hrma.engines.solid_rocket_engine as se

    assert merkez == 5.670374419e-8  # CODATA 2018 — değer de kilitli
    assert tp.STEFAN_BOLTZMANN is merkez
    assert sa.SAFETY_MODEL['stefan_boltzmann'] is merkez
    assert ht.HeatTransferAnalyzer().stefan_boltzmann is merkez
    assert fea.STEFAN_BOLTZMANN_W_M2K4 is merkez
    assert se.SOLID_THERMAL['stefan_boltzmann'] is merkez
