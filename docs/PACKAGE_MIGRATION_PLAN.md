# HRMA Paket Yapisi Gecis Plani

**Tarih:** 2026-03-16
**Hazirlayan:** Architect Agent
**Durum:** PLAN -- KOD DEGISIKLIGI YAPILMADI

---

## 1. Mevcut Durum Analizi

### 1.1 Dosya Envanteri
- 39 Python dosyasi, hepsi flat (root) dizinde
- Toplam ~25,700 satir Python kodu
- app.py: 2,704 satir, 50 route
- En buyuk modul: visualization.py (2,390 satir)
- En kucuk: run.py (71 satir)

### 1.2 Internal Dependency Haritasi (Proje-ici import'lar)

```
app.py
  |-- hybrid_rocket_engine (HybridRocketEngine)
  |     |-- combustion_analysis (CombustionAnalyzer)
  |     |-- nozzle_design (NozzleDesigner)
  |     |-- heat_transfer_analysis (HeatTransferAnalyzer)
  |     |-- structural_analysis (StructuralAnalyzer)
  |     |-- external_data_fetcher (data_fetcher)
  |-- injector_design (InjectorDesign)
  |     |-- external_data_fetcher (data_fetcher)
  |-- validation_system (validator)
  |-- motor_validation (motor_validator)
  |-- regression_analysis (regression_analyzer)
  |-- common_fixes (validation, calculations, graph_fixes, fuel_mixer, export_fixes)
  |-- optimum_of_ratio (of_optimizer)
  |-- propellant_database (propellant_db)
  |-- open_source_propellant_api (propellant_api)
  |-- visualization (13 fonksiyon)
  |-- advanced_results (4 fonksiyon)
  |-- openrocket_integration (OpenRocketExporter)
  |-- database_integrations (DatabaseManager)
  |-- trajectory_analysis (TrajectoryAnalyzer)
  |-- cad_visualization (MotorCADDesigner)
  |-- solid_rocket_engine (SolidRocketEngine)
  |-- liquid_rocket_engine (LiquidRocketEngine)
  |-- safety_analysis (SafetyAnalyzer)
  |-- structural_analysis (StructuralAnalyzer)
  |-- heat_transfer_analysis (HeatTransferAnalyzer)
  |-- chemical_database (chemical_db)
  |-- experimental_validation (experimental_validator)
  |-- cfd_analysis (cfd_analyzer)
  |-- kinetic_analysis (kinetic_analyzer)
```

### 1.3 Singleton Instance'lar (module-level)

Bu moduller dosya sonunda global instance olusturuyor. Import edildiginde otomatik yaratilir:

| Modul | Degisken | Sinif |
|-------|----------|-------|
| validation_system | `validator` | ValidationSystem |
| motor_validation | `motor_validator` | MotorDataValidator |
| regression_analysis | `regression_analyzer` | RegressionAnalyzer |
| propellant_database | `propellant_db` | PropellantDatabase |
| open_source_propellant_api | `propellant_api` | OpenSourcePropellantAPI |
| optimum_of_ratio | `of_optimizer` | OptimumOFRatioFinder |
| chemical_database | `chemical_db` | ChemicalDatabase |
| experimental_validation | `experimental_validator` | ExperimentalValidation |
| cfd_analysis | `cfd_analyzer` | CFD2DAnalyzer |
| kinetic_analysis | `kinetic_analyzer` | NozzleKineticAnalyzer |
| external_data_fetcher | `data_fetcher` | ExternalDataFetcher |

### 1.4 Circular Dependency Riski

Mevcut durumda circular dependency YOK. Zincir tek yonlu:
```
app -> engines -> analysis modules -> (sadece stdlib/numpy/scipy)
```
Bu temiz yapinin korunmasi gerekiyor.

---

## 2. Hedef Dizin Yapisi

```
HRMA/
|-- run.py                          # Entry point (YERINDE KALIR)
|-- run_windows.py                  # Windows entry point (YERINDE KALIR)
|-- install.py                      # Installer (YERINDE KALIR)
|-- requirements.txt                # (varsa, YERINDE KALIR)
|-- icon.icns                       # (YERINDE KALIR)
|-- icon.jpg                        # (YERINDE KALIR)
|
|-- hrma/                           # ANA PAKET
|   |-- __init__.py                 # Paket metadata + lazy imports
|   |-- app.py                      # Flask uygulamasi
|   |
|   |-- engines/                    # Motor hesaplama modulleri
|   |   |-- __init__.py
|   |   |-- hybrid_rocket_engine.py
|   |   |-- solid_rocket_engine.py
|   |   |-- liquid_rocket_engine.py
|   |   |-- combustion_analysis.py
|   |   |-- nozzle_design.py
|   |
|   |-- analysis/                   # Analiz modulleri
|   |   |-- __init__.py
|   |   |-- cfd_analysis.py
|   |   |-- heat_transfer_analysis.py
|   |   |-- structural_analysis.py
|   |   |-- safety_analysis.py
|   |   |-- kinetic_analysis.py
|   |   |-- regression_analysis.py
|   |   |-- trajectory_analysis.py
|   |   |-- safety_limits.py
|   |
|   |-- data/                       # Veri kaynaklari ve veritabanlari
|   |   |-- __init__.py
|   |   |-- propellant_database.py
|   |   |-- chemical_database.py
|   |   |-- open_source_propellant_api.py
|   |   |-- web_propellant_api.py
|   |   |-- external_data_fetcher.py
|   |   |-- database_integrations.py
|   |   |-- nasa_realtime_validator.py
|   |
|   |-- export/                     # Cikti uretimi
|   |   |-- __init__.py
|   |   |-- cad_export.py
|   |   |-- cad_visualization.py
|   |   |-- openrocket_integration.py
|   |   |-- pdf_generator.py
|   |
|   |-- validation/                 # Dogrulama ve validasyon
|   |   |-- __init__.py
|   |   |-- validation_system.py
|   |   |-- motor_validation.py
|   |   |-- experimental_validation.py
|   |
|   |-- visualization/              # Gorsellestirme
|   |   |-- __init__.py
|   |   |-- visualization.py        # (ileride parcalanabilir)
|   |   |-- advanced_results.py
|   |
|   |-- utils/                      # Yardimci moduller
|   |   |-- __init__.py
|   |   |-- common_fixes.py
|   |   |-- optimum_of_ratio.py
|   |   |-- injector_design.py
|   |   |-- windows_compatibility.py
|   |
|   |-- templates/                  # Flask sablonlari (TASINDI)
|   |   |-- index.html
|   |   |-- advanced.html
|   |   |-- formulas.html
|   |   |-- liquid.html
|   |   |-- simple.html
|   |   |-- solid.html
|   |   |-- uzaytek.html
|   |
|   |-- static/                     # Statik dosyalar (TASINDI)
|       |-- css/
|       |   |-- style.css
|       |-- js/
|           |-- app.js
|
|-- data/                           # Runtime veri dosyalari (ROOT'ta)
|   |-- chemical_species.db
|   |-- experimental_data.db
|   |-- propellant_cache/           # Cache dizini
|
|-- cad_exports/                    # CAD ciktilari (YERINDE KALIR)
|
|-- tests/                          # Test dosyalari
|   |-- __init__.py
|   |-- test_real_api.py
|   |-- test_solid_rocket_validation.py
|
|-- docs/                           # Dokumantasyon
    |-- CLAUDE.md
    |-- PACKAGE_MIGRATION_PLAN.md   # Bu dosya
```

---

## 3. Dosya Tasima Haritasi

### 3.1 Tam Haritalama: eski_yol -> yeni_yol

```
# ROOT'TA KALANLAR (degismez)
run.py                          -> run.py
run_windows.py                  -> run_windows.py
install.py                      -> install.py

# HRMA ANA PAKET
app.py                          -> hrma/app.py

# ENGINES
hybrid_rocket_engine.py         -> hrma/engines/hybrid_rocket_engine.py
solid_rocket_engine.py          -> hrma/engines/solid_rocket_engine.py
liquid_rocket_engine.py         -> hrma/engines/liquid_rocket_engine.py
combustion_analysis.py          -> hrma/engines/combustion_analysis.py
nozzle_design.py                -> hrma/engines/nozzle_design.py

# ANALYSIS
cfd_analysis.py                 -> hrma/analysis/cfd_analysis.py
heat_transfer_analysis.py       -> hrma/analysis/heat_transfer_analysis.py
structural_analysis.py          -> hrma/analysis/structural_analysis.py
safety_analysis.py              -> hrma/analysis/safety_analysis.py
kinetic_analysis.py             -> hrma/analysis/kinetic_analysis.py
regression_analysis.py          -> hrma/analysis/regression_analysis.py
trajectory_analysis.py          -> hrma/analysis/trajectory_analysis.py
safety_limits.py                -> hrma/analysis/safety_limits.py

# DATA
propellant_database.py          -> hrma/data/propellant_database.py
chemical_database.py            -> hrma/data/chemical_database.py
open_source_propellant_api.py   -> hrma/data/open_source_propellant_api.py
web_propellant_api.py           -> hrma/data/web_propellant_api.py
external_data_fetcher.py        -> hrma/data/external_data_fetcher.py
database_integrations.py        -> hrma/data/database_integrations.py
nasa_realtime_validator.py      -> hrma/data/nasa_realtime_validator.py

# EXPORT
cad_export.py                   -> hrma/export/cad_export.py
cad_visualization.py            -> hrma/export/cad_visualization.py
openrocket_integration.py       -> hrma/export/openrocket_integration.py
pdf_generator.py                -> hrma/export/pdf_generator.py

# VALIDATION
validation_system.py            -> hrma/validation/validation_system.py
motor_validation.py             -> hrma/validation/motor_validation.py
experimental_validation.py      -> hrma/validation/experimental_validation.py

# VISUALIZATION
visualization.py                -> hrma/visualization/visualization.py
advanced_results.py             -> hrma/visualization/advanced_results.py

# UTILS
common_fixes.py                 -> hrma/utils/common_fixes.py
optimum_of_ratio.py             -> hrma/utils/optimum_of_ratio.py
injector_design.py              -> hrma/utils/injector_design.py
windows_compatibility.py        -> hrma/utils/windows_compatibility.py

# TEMPLATES VE STATIC
templates/                      -> hrma/templates/
static/                         -> hrma/static/

# DATA DOSYALARI
chemical_species.db             -> data/chemical_species.db
experimental_data.db            -> data/experimental_data.db
propellant_cache/               -> data/propellant_cache/

# TESTLER
test_real_api.py                -> tests/test_real_api.py
test_solid_rocket_validation.py -> tests/test_solid_rocket_validation.py
```

---

## 4. __init__.py Dosyalari

### 4.1 hrma/__init__.py

```python
"""
HRMA - Hybrid Rocket Motor Analysis
"""

__version__ = "1.0.0"
__author__ = "HRMA Team"
```

### 4.2 hrma/engines/__init__.py

```python
"""Motor hesaplama modulleri."""

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.nozzle_design import NozzleDesigner
```

### 4.3 hrma/analysis/__init__.py

```python
"""Analiz modulleri."""

from hrma.analysis.cfd_analysis import cfd_analyzer, CFD2DAnalyzer
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.safety_analysis import SafetyAnalyzer
from hrma.analysis.kinetic_analysis import kinetic_analyzer, NozzleKineticAnalyzer
from hrma.analysis.regression_analysis import regression_analyzer, RegressionAnalyzer
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
from hrma.analysis.safety_limits import SafetyLimits
```

### 4.4 hrma/data/__init__.py

```python
"""Veri kaynaklari ve veritabani modulleri."""

from hrma.data.propellant_database import propellant_db, PropellantDatabase
from hrma.data.chemical_database import chemical_db, ChemicalDatabase
from hrma.data.open_source_propellant_api import propellant_api, OpenSourcePropellantAPI
from hrma.data.external_data_fetcher import data_fetcher, ExternalDataFetcher
from hrma.data.database_integrations import DatabaseManager
```

### 4.5 hrma/export/__init__.py

```python
"""Cikti uretim modulleri."""

from hrma.export.cad_visualization import MotorCADDesigner
from hrma.export.openrocket_integration import OpenRocketExporter
```

### 4.6 hrma/validation/__init__.py

```python
"""Dogrulama modulleri."""

from hrma.validation.validation_system import validator, ValidationSystem
from hrma.validation.motor_validation import motor_validator, MotorDataValidator
from hrma.validation.experimental_validation import experimental_validator, ExperimentalValidation
```

### 4.7 hrma/visualization/__init__.py

```python
"""Gorsellestirme modulleri."""

from hrma.visualization.visualization import (
    create_motor_plot, create_injector_plot, create_performance_plots,
    create_heat_transfer_plots, create_combustion_analysis_plots,
    create_structural_analysis_plots, create_real_time_dashboard,
    create_3d_motor_visualization, create_comparative_analysis_plot,
    create_chamber_pressure_mixture_ratio_3d_surface,
    create_nozzle_mach_area_ratio_contour,
    create_wall_heat_flux_waterfall_plot,
    create_improved_motor_cross_section,
    create_improved_injector_design
)

from hrma.visualization.advanced_results import (
    create_cea_style_results, create_altitude_performance_plot,
    create_mass_fractions_plot, create_thrust_altitude_plot
)
```

### 4.8 hrma/utils/__init__.py

```python
"""Yardimci moduller."""

from hrma.utils.common_fixes import (
    validation, calculations, graph_fixes, fuel_mixer, export_fixes
)
from hrma.utils.optimum_of_ratio import of_optimizer, OptimumOFRatioFinder
from hrma.utils.injector_design import InjectorDesign
```

### 4.9 tests/__init__.py

```python
# Test paketi
```

---

## 5. Import Degisiklikleri

### 5.1 app.py (hrma/app.py) -- 25 import satirinin yeni hali

**ONCEKI (flat):**
```python
from hybrid_rocket_engine import HybridRocketEngine
from injector_design import InjectorDesign
from validation_system import validator
from motor_validation import motor_validator
from regression_analysis import regression_analyzer
from common_fixes import validation, calculations, graph_fixes, fuel_mixer, export_fixes
from optimum_of_ratio import of_optimizer
from propellant_database import propellant_db
from open_source_propellant_api import propellant_api
from visualization import (create_motor_plot, create_injector_plot, ...)
from advanced_results import create_cea_style_results, ...
from openrocket_integration import OpenRocketExporter
from database_integrations import DatabaseManager
from trajectory_analysis import TrajectoryAnalyzer
from cad_visualization import MotorCADDesigner
from solid_rocket_engine import SolidRocketEngine
from liquid_rocket_engine import LiquidRocketEngine
from safety_analysis import SafetyAnalyzer
from structural_analysis import StructuralAnalyzer
from heat_transfer_analysis import HeatTransferAnalyzer
from chemical_database import chemical_db
from experimental_validation import experimental_validator
from cfd_analysis import cfd_analyzer
from kinetic_analysis import kinetic_analyzer
```

**SONRAKI (paket yapisi):**
```python
# Engines
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

# Utils
from hrma.utils.injector_design import InjectorDesign
from hrma.utils.common_fixes import validation, calculations, graph_fixes, fuel_mixer, export_fixes
from hrma.utils.optimum_of_ratio import of_optimizer

# Validation
from hrma.validation.validation_system import validator
from hrma.validation.motor_validation import motor_validator
from hrma.validation.experimental_validation import experimental_validator

# Analysis
from hrma.analysis.regression_analysis import regression_analyzer
from hrma.analysis.safety_analysis import SafetyAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.cfd_analysis import cfd_analyzer
from hrma.analysis.kinetic_analysis import kinetic_analyzer
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer

# Data
from hrma.data.propellant_database import propellant_db
from hrma.data.open_source_propellant_api import propellant_api
from hrma.data.chemical_database import chemical_db
from hrma.data.database_integrations import DatabaseManager

# Visualization
from hrma.visualization.visualization import (
    create_motor_plot, create_injector_plot, create_performance_plots,
    create_heat_transfer_plots, create_combustion_analysis_plots,
    create_structural_analysis_plots, create_real_time_dashboard,
    create_3d_motor_visualization, create_comparative_analysis_plot,
    create_chamber_pressure_mixture_ratio_3d_surface,
    create_nozzle_mach_area_ratio_contour,
    create_wall_heat_flux_waterfall_plot,
    create_improved_motor_cross_section,
    create_improved_injector_design
)
from hrma.visualization.advanced_results import (
    create_cea_style_results, create_altitude_performance_plot,
    create_mass_fractions_plot, create_thrust_altitude_plot
)

# Export
from hrma.export.openrocket_integration import OpenRocketExporter
from hrma.export.cad_visualization import MotorCADDesigner
```

**Windows compatibility blogu (app.py satir 10-17):**
```python
# ONCEKI:
from windows_compatibility import windows_compat, apply_windows_fixes

# SONRAKI:
from hrma.utils.windows_compatibility import windows_compat, apply_windows_fixes
```

### 5.2 hybrid_rocket_engine.py (hrma/engines/hybrid_rocket_engine.py)

```python
# ONCEKI:
from combustion_analysis import CombustionAnalyzer
from nozzle_design import NozzleDesigner
from heat_transfer_analysis import HeatTransferAnalyzer
from structural_analysis import StructuralAnalyzer
from external_data_fetcher import data_fetcher

# SONRAKI:
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.nozzle_design import NozzleDesigner
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.data.external_data_fetcher import data_fetcher
```

### 5.3 injector_design.py (hrma/utils/injector_design.py)

```python
# ONCEKI:
from external_data_fetcher import data_fetcher

# SONRAKI:
from hrma.data.external_data_fetcher import data_fetcher
```

### 5.4 run.py (ROOT'ta kalir)

```python
# ONCEKI:
from app import app

# SONRAKI:
from hrma.app import app
```

### 5.5 run_windows.py (ROOT'ta kalir)

```python
# ONCEKI:
from app import app

# SONRAKI:
from hrma.app import app
```

### 5.6 test_real_api.py (tests/test_real_api.py)

```python
# ONCEKI:
from open_source_propellant_api import propellant_api

# SONRAKI:
from hrma.data.open_source_propellant_api import propellant_api
```

### 5.7 test_solid_rocket_validation.py (tests/test_solid_rocket_validation.py)

```python
# ONCEKI:
from solid_rocket_engine import SolidRocketEngine

# SONRAKI:
from hrma.engines.solid_rocket_engine import SolidRocketEngine
```

---

## 6. Flask template_folder ve static_folder

app.py'de Flask instance'i olusturulurken dizin yollarini guncellememiz gerekmiyor
cunku templates/ ve static/ artik hrma/ icerisinde, yani app.py ile ayni paketin altinda.

Flask varsayilan olarak app.py'nin bulundugu dizindeki `templates/` ve `static/` dizinlerini arar.
app.py hrma/ altina tasindiginda, templates/ ve static/ da hrma/ altinda oldugu icin
Flask bunlari otomatik bulur. **Ek konfigurasyon gerekmez.**

Eger sorun cikarsa explicit yol:
```python
import os
basedir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(basedir, 'templates'),
            static_folder=os.path.join(basedir, 'static'))
```

---

## 7. Database ve Cache Dosya Yollari

### 7.1 Sorun

Bazi moduller `.db` dosyalarina relative path ile erisir. Paket yapisi degistiginde
calisma dizini (CWD) degismeyecek (run.py root'tan calisir) ama dosya konumlari degisecek.

### 7.2 Etkilenen Moduller

`chemical_database.py` ve `experimental_validation.py` sqlite3 baglantisi kuruyor.
Bu dosyalardaki path referanslarinin guncellenmesi gerekiyor.

**Mevcut kodda bulunan path referanslari:**
```python
# chemical_database.py satir 30:
def __init__(self, db_path: str = "chemical_species.db"):   # CWD'ye bagli!

# experimental_validation.py satir 54:
def __init__(self, db_path: str = "experimental_data.db"):  # CWD'ye bagli!

# web_propellant_api.py satir 25:
self.cache_dir = "propellant_cache"                         # CWD'ye bagli!

# nasa_realtime_validator.py satir 18:
self.cache_file = "nasa_validation_cache.json"              # CWD'ye bagli!
```

**Her birinin yeni hali:**
```python
# chemical_database.py:
from hrma import DATA_DIR
def __init__(self, db_path: str = None):
    self.db_path = db_path or os.path.join(DATA_DIR, 'chemical_species.db')

# experimental_validation.py:
from hrma import DATA_DIR
def __init__(self, db_path: str = None):
    self.db_path = db_path or os.path.join(DATA_DIR, 'experimental_data.db')

# web_propellant_api.py:
from hrma import DATA_DIR
self.cache_dir = os.path.join(DATA_DIR, "propellant_cache")

# nasa_realtime_validator.py:
from hrma import DATA_DIR
self.cache_file = os.path.join(DATA_DIR, "nasa_validation_cache.json")
```

### 7.3 Cozum Stratejisi

Secenekler:

**A) Config sabiti (ONERILEN):**
`hrma/__init__.py` icerisine:
```python
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
```

Kullanim:
```python
from hrma import DATA_DIR
db_path = os.path.join(DATA_DIR, 'chemical_species.db')
```

**B) Ortam degiskeni:**
```python
DATA_DIR = os.environ.get('HRMA_DATA_DIR', os.path.join(PROJECT_ROOT, 'data'))
```

Secenek A yeterli ve basit. Secenek B ileride deployment icin eklenebilir.

### 7.4 propellant_cache Yolu

`web_propellant_api.py` ve `open_source_propellant_api.py` cache dosyalari kullaniyor olabilir.
Bunlarin pickle/json path'leri de DATA_DIR kullanacak sekilde guncellenmeli.

---

## 8. Uygulama Sirasi (Adim Adim)

### Faz 1: Iskelet Olusturma (Sifir Risk)
1. `hrma/` dizinini ve tum alt dizinleri olustur
2. Bos `__init__.py` dosyalarini yerlestir
3. `data/` dizinini olustur
4. `tests/` dizinini olustur

### Faz 2: Dosya Tasima (git mv)
5. Her dosyayi `git mv eski_yol yeni_yol` ile tasi
6. `.db` dosyalarini `data/` altina tasi
7. `propellant_cache/` dizinini `data/` altina tasi
8. `templates/` ve `static/` dizinlerini `hrma/` altina tasi
9. Test dosyalarini `tests/` altina tasi

### Faz 3: Import Guncelleme
10. `hrma/app.py` import satirlarini guncelle (Bolum 5.1)
11. `hrma/engines/hybrid_rocket_engine.py` import'larini guncelle (Bolum 5.2)
12. `hrma/utils/injector_design.py` import'unu guncelle (Bolum 5.3)
13. `run.py` ve `run_windows.py` import'unu guncelle (Bolum 5.4, 5.5)
14. Test dosyalari import'larini guncelle (Bolum 5.6, 5.7)

### Faz 4: Path Guncelleme
15. `hrma/__init__.py` icine PROJECT_ROOT ve DATA_DIR ekle
16. `chemical_database.py` ve `experimental_validation.py` db path'lerini guncelle
17. Cache path'lerini guncelle (propellant_cache)

### Faz 5: __init__.py Doldurmak
18. Tum `__init__.py` dosyalarini Bolum 4'teki gibi doldur

### Faz 6: Test
19. `python run.py` ile calistir
20. Tarayicida her sayfayi test et (/, /hybrid, /solid, /liquid)
21. Bir hesaplama yap (calculate endpoint'i)
22. STL export'u test et
23. Test dosyalarini calistir

---

## 9. Mimari Kararlar ve Gerekceleri

### K1: app.py hrma/ paketin ICINDE
**Karar:** app.py hrma/ altinda.
**Gerekceler:**
- Flask template_folder ve static_folder otomatik calisir (ayni dizin)
- Import'lar `hrma.engines.xxx` seklinde tutarli olur
- run.py sadece `from hrma.app import app` der, temiz ayrim

### K2: templates/ ve static/ paketin icinde
**Karar:** hrma/templates/ ve hrma/static/
**Gerekceler:**
- Flask __name__ resolution'i paketten calisiyor, sablonlari otomatik bulur
- Ileride `pip install hrma` yapildiginda templates de paketle birlikte gider
- Ayri dizinde birakma secenek olabilir ama konfigurasyon gerektirir, gereksiz karmasiklik

### K3: .db dosyalari root/data/ altinda (paketin DISINDA)
**Karar:** data/ dizini root'ta, paket disinda
**Gerekceler:**
- DB dosyalari runtime verisi, kaynak kodu degil
- 30MB+ experimental_data.db paketin icinde olmamali
- Git'te buyuk dosya yonetimi icin ayri tutmak daha iyi
- DATA_DIR sabiti ile erisim saglaniyor

### K4: Singleton instance'larin korunmasi
**Karar:** Module-level singleton instance'lari oldugu gibi birakilacak.
**Gerekceler:**
- Mevcut calisan kodu minimum degistirmek (import path disinda degisiklik yok)
- `__init__.py` bunlari re-export edecek
- Ileride factory pattern'e gecis opsiyonel

### K5: Blueprint bolunmesi bu fazda YAPILMAYACAK
**Karar:** app.py 50 route ile monolitik kalacak.
**Gerekceler:**
- Kapsam kontrolu -- once paket yapisi, sonra Blueprint
- 2704 satir tek dosyada sorun ama calistiriyor
- Blueprint bolunmesi ayri bir gorev olarak planlanabilir (Faz 2 proje)

---

## 10. Riskler ve Azaltma Stratejileri

| Risk | Olasilik | Etki | Azaltma |
|------|----------|------|---------|
| DB path kirmak | YUKSEK | Uygulama calismayi durdurur | Faz 4'te dikkatli path testi |
| Circular import | DUSUK | Import hatasi | Mevcut yapida circular yok, korunacak |
| Flask template bulamama | ORTA | Sayfa render edilemez | Flask instance'a explicit path ver |
| Cache path kirilmasi | ORTA | API sonuclari cachelenmiyor | DATA_DIR + fallback eski konuma |
| Singleton double-init | DUSUK | Bellek israfi, ama calismaya engel degil | __init__.py lazy import |
| run.py path bulamama | DUSUK | Uygulama baslamaz | sys.path.insert test et |

---

## 11. Ileride Yapilabilecek Iyilestirmeler (Bu Planda DEGIL)

1. **Blueprint Bolunmesi:** app.py'deki route'lari hybrid_routes.py, solid_routes.py, liquid_routes.py, api_routes.py gibi dosyalara ayirmak
2. **Factory Pattern:** `create_app()` fonksiyonu ile Flask app olusturmak (test edilebilirlik icin)
3. **Konfigurasi Yonetimi:** config.py ile farkli ortamlar (dev/prod/test)
4. **visualization.py Parcalama:** 2390 satirlik dosyayi engine-specific parcalara bolmek
5. **setup.py / pyproject.toml:** Paketleme ve dagitim icin
6. **Docker desteği:** Containerized calistirma

---

## 12. Kontrol Listesi (Uygulama Oncesi)

- [ ] Mevcut proje `git commit` ile yedeklenmis mi?
- [ ] Tum testler geciyormu (mevcut haliyle)?
- [ ] `python run.py` calisiyor mu?
- [ ] DB dosyalari backup'landi mi?

## 13. Kontrol Listesi (Uygulama Sonrasi)

- [ ] `python run.py` calisiyor mu?
- [ ] http://localhost:8080 aciliyor mu?
- [ ] /hybrid sayfasi render oluyor mu?
- [ ] /solid sayfasi render oluyor mu?
- [ ] /liquid sayfasi render oluyor mu?
- [ ] /formulas sayfasi render oluyor mu?
- [ ] Hybrid hesaplama calisiyor mu? (/calculate POST)
- [ ] Solid hesaplama calisiyor mu? (/calculate_solid POST)
- [ ] Liquid hesaplama calisiyor mu? (/calculate_liquid POST)
- [ ] STL export calisiyor mu? (/api/export-stl POST)
- [ ] Chemical database erisilebilir mi?
- [ ] `python -m pytest tests/` calisiyor mu?
- [ ] Propellant cache calisiyor mu?
