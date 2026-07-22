"""3D simülasyon/görselleştirme geliştirmeleri sözleşme testleri (v2.5.5).

Kapsam (2026-07-21 ARGE bulguları — motor_viz3d.js / motor_viz_deck.js /
sixdof_panel.js):

  1. Yanma animasyonu performansı: grain yeniden kurulum eşiği artık her
     karede tetiklenmez (0.05 mm sabiti gitti, GRAIN_REBUILD_* eşiği geldi);
     parıltı silindiri yeniden kurulmak yerine radyal ölçeklenir.
  2. Ortam haritası + ton eşleme: prosedürel CubeTexture scene.environment'a
     atanır, ACESFilmicToneMapping + toneMappingExposure kullanılır ve
     KULLANILAN HER Three.js API'sinin paketlenmiş r128 vendor dosyasında
     var olduğu doğrulanır (paket sürümü yükseltilmeden API kullanılamaz).
  3. Görünmezlik bekçisi: _tick, offsetParent null iken render yapmaz;
     otomatik kalite bekçisi (60 kare / 28 ms) perf moduna düşürür ve
     deck'teki HQ butonu onQualityChange kancasıyla senkron kalır.
  4. 6-DOF paneli 3B yörünge: scatter3d (Mach renkli + colorbar), apoje
     işaretçisi, zemin izdüşümü — ve scatter3d line colorbar'ının
     paketlenmiş plotly.js 1.58.5'te gerçekten destekli olduğu.
  5. PNG snapshot: MotorScene.snapshot() + deck Frame butonu.
  6. Kod sağlığı: controls.dispose, capGeoBase.dispose, setDrawRange.
  7. Hijyen: üç dosyada emoji yok; sözdizimi node --check ile geçer.

Testler dosya-sistemi sözleşmesidir (tarayıcı çalıştırmaz): amaç, bu
davranışların sessizce geri alınmasını (regresyon) yakalamaktır.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JS_DIR = REPO_ROOT / 'hrma' / 'static' / 'js'
VENDOR_DIR = REPO_ROOT / 'hrma' / 'static' / 'vendor'

VIZ3D = JS_DIR / 'motor_viz3d.js'
DECK = JS_DIR / 'motor_viz_deck.js'
SIXDOF = JS_DIR / 'sixdof_panel.js'
THREE_VENDOR = VENDOR_DIR / 'three-0.128.0.min.js'
ORBIT_VENDOR = VENDOR_DIR / 'OrbitControls-0.128.0.js'
PLOTLY_VENDOR = VENDOR_DIR / 'plotly-1.58.5.min.js'

EDITED_FILES = [VIZ3D, DECK, SIXDOF]


def _read(path):
    assert path.exists(), f'{path} bulunamadı'
    return path.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# 0) Sözdizimi + hijyen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('path', EDITED_FILES, ids=lambda p: p.name)
def test_js_syntax(path):
    node = shutil.which('node')
    if not node:
        pytest.skip('node bulunamadı — sözdizimi denetimi atlandı')
    res = subprocess.run([node, '--check', str(path)],
                         capture_output=True, text=True)
    assert res.returncode == 0, f'{path.name} sözdizimi hatası:\n{res.stderr}'


@pytest.mark.parametrize('path', EDITED_FILES, ids=lambda p: p.name)
def test_no_emoji(path):
    # Emoji yasağı (Berke 2026-07-15): temel emoji blokları taranır
    src = _read(path)
    emoji = re.compile(
        '[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F000-\U0001F0FF'
        '\U00002600-\U000026FF\U0001F900-\U0001F9FF]'
    )
    hits = emoji.findall(src)
    assert not hits, f'{path.name} emoji içeriyor: {hits[:5]}'


# ---------------------------------------------------------------------------
# 1) Yanma animasyonu performansı
# ---------------------------------------------------------------------------

def test_grain_rebuild_threshold():
    src = _read(VIZ3D)
    # Yeni eşik sabitleri tanımlı ve _rebuildGrain bunları kullanıyor
    assert re.search(r'GRAIN_REBUILD_MIN_MM\s*=\s*0\.4', src)
    assert 'GRAIN_REBUILD_FRACTION' in src
    assert re.search(
        r'Math\.max\(GRAIN_REBUILD_MIN_MM,\s*\n?\s*GRAIN_REBUILD_FRACTION', src)
    # Eski her-kare eşiği (0.05 mm) geri gelmesin
    assert not re.search(r'this\._lastPortR\)\s*<\s*0\.05', src), (
        'grain yeniden kurulum eşiği 0.05 mm sabitine geri dönmüş — '
        'oynatma sırasında her karede geometri kurulur (performans regresyonu)')


def test_glow_scaled_not_rebuilt_every_frame():
    src = _read(VIZ3D)
    # Parıltı: radyal ölçek uygulanır, taban port kaydı tutulur
    assert '_glowBuiltPort' in src
    assert re.search(r'_glowMesh\.scale\.set\(sGlow,\s*1,\s*sGlow\)', src)
    # Yanma sonunda son dilim force ile kapatılır
    assert '_grainFinal' in src


# ---------------------------------------------------------------------------
# 2) Ortam haritası + ton eşleme (vendor API doğrulamalı)
# ---------------------------------------------------------------------------

def test_env_map_and_tone_mapping_wired():
    src = _read(VIZ3D)
    assert 'makeEnvCubeTexture' in src
    assert re.search(r'this\.scene\.environment\s*=\s*this\._envTex', src)
    assert 'THREE.ACESFilmicToneMapping' in src
    assert re.search(r'toneMappingExposure\s*=\s*1\.1', src)
    assert 'envMapIntensity' in src


def test_three_vendor_supports_used_apis():
    """Kullanılan her Three.js API'si paketlenmiş r128'de var olmalı."""
    vendor = _read(THREE_VENDOR)
    for api in ('ACESFilmicToneMapping', 'toneMappingExposure', 'CubeTexture',
                'envMapIntensity', 'setDrawRange', 'sRGBEncoding', 'toneMapped'):
        assert api in vendor, f'three r128 vendor dosyasında {api} yok'
    # scene.environment MeshStandardMaterial'lara r128'de otomatik uygulanır
    assert 'this.environment=null' in vendor
    assert 'isMeshStandardMaterial?' in vendor and '.environment' in vendor


def test_orbitcontrols_vendor_has_dispose():
    vendor = _read(ORBIT_VENDOR)
    assert 'this.dispose = function' in vendor or 'dispose:' in vendor


# ---------------------------------------------------------------------------
# 3) Görünmezlik bekçisi + otomatik kalite düşüşü
# ---------------------------------------------------------------------------

def test_tick_hidden_container_guard():
    src = _read(VIZ3D)
    m = re.search(
        r'if \(!this\.container\.offsetParent\) \{\s*'
        r'this\.controls\.update\(\);\s*'
        r'return;', src)
    assert m, '_tick görünmez konteyner bekçisi (offsetParent) kaldırılmış'
    # Bekçi render çağrısından ÖNCE olmalı
    assert src.index('this.container.offsetParent') < \
        src.index('this.renderer.render(this.scene, this.camera)')


def test_auto_perf_watchdog():
    src = _read(VIZ3D)
    assert re.search(r'AUTO_PERF_FRAME_WINDOW\s*=\s*60', src)
    assert re.search(r'AUTO_PERF_DT_LIMIT\s*=\s*0\.028', src)
    assert re.search(r"this\.setQuality\('perf'\)", src)
    # setQuality kalite değişimini kancaya bildirir (deck senkronu)
    assert 'onQualityChange' in src


def test_deck_syncs_quality_button():
    src = _read(DECK)
    assert 'onQualityChange' in src
    assert '_btn_quality' in src


# ---------------------------------------------------------------------------
# 4) 6-DOF 3B yörünge grafiği
# ---------------------------------------------------------------------------

def test_sixdof_traj3d_plot_present():
    src = _read(SIXDOF)
    assert 'sd_plot_traj3d' in src, '3B yörünge konteyneri yok'
    assert "type: 'scatter3d'" in src
    # Mach renklendirme + colorbar
    assert 'color: ser.mach' in src
    assert 'showscale: true' in src
    assert "colorbar: { title: 'Mach'" in src
    # Apoje işaretçisi + zemin izdüşümü
    assert "T('sixdof.sApogee', 'Apogee')" in src
    assert "T('sixdof.sGroundProj', 'Ground projection')" in src
    assert "dash: 'dash'" in src
    # Mevcut i18n eksen anahtarları yeniden kullanılır
    for key in ('sixdof.axisEast', 'sixdof.axisNorth', 'sixdof.sAltitude'):
        assert key in src


def test_plotly_vendor_supports_scatter3d_line_colorbar():
    """Paketlenmiş plotly.js 1.58.5 scatter3d + line colorbar desteklemeli.

    scatter3d trace modülünün colorbar kaydında {container:"line"} girdisi
    bulunur — çizgi renk skalası (Mach colorbar'ı) bu sürümde gerçekten
    çalışır. Vendor dosyası değişirse bu test yeniden değerlendirilmeli.
    """
    vendor = _read(PLOTLY_VENDOR)
    assert 'scatter3d' in vendor
    assert '{container:"line",min:"cmin",max:"cmax"}' in vendor


def test_sixdof_existing_plots_untouched():
    """Regresyon kalkanı: mevcut üç grafik (irtifa/alfa/iz) yerinde durmalı."""
    src = _read(SIXDOF)
    for div in ('sd_plot_alt', 'sd_plot_alpha', 'sd_plot_track'):
        assert div in src, f'{div} kaldırılmış — panel silme yasağı ihlali'


# ---------------------------------------------------------------------------
# 5) PNG snapshot
# ---------------------------------------------------------------------------

def test_snapshot_api():
    src = _read(VIZ3D)
    assert 'MotorScene.prototype.snapshot' in src
    assert "toDataURL('image/png')" in src
    # Dışa açık API'de de var (deck ve sayfalar için)
    assert re.search(r'snapshot:\s*function \(\) \{ return viz \? viz\.snapshot\(\)', src)


def test_deck_frame_button():
    src = _read(DECK)
    assert '_btn_frame' in src
    assert 'viz.snapshot()' in src
    assert "T('viz.btnFrame', 'Frame')" in src
    assert 'a.download' in src


# ---------------------------------------------------------------------------
# 6) Kod sağlığı
# ---------------------------------------------------------------------------

def test_dispose_cleanups():
    src = _read(VIZ3D)
    assert 'this.controls.dispose()' in src
    assert 'capGeoBase.dispose()' in src
    assert 'this._envTex.dispose()' in src


def test_plume_draw_range():
    src = _read(VIZ3D)
    # Ölü partiküller çizilmez; aktif sayı büyüyünce yeni indeksler resetlenir
    assert 'setDrawRange(0, active)' in src
    assert '_plumeActive' in src


def test_plume_physics_coupling():
    src = _read(VIZ3D)
    assert '_plumeAero' in src
    assert 'PLUME_REF_EXIT_ANGLE_DEG' in src
    assert 'IDEAL_EXPANSION_EPS' in src
    # Elmas aralığı genişleme oranından türetilir
    assert 'diamondSpacing' in src and 'diamondStrength' in src


# ---------------------------------------------------------------------------
# 7) Tasarım modu bayatlamaları
# ---------------------------------------------------------------------------

def test_floor_and_grid_follow_motor_size():
    src = _read(VIZ3D)
    assert '_floorBaseLen' in src
    assert re.search(r'this\._grid\.scale\.setScalar\(fScale\)', src)
    assert re.search(r'this\._floor\.position\.y\s*=\s*floorY', src)


def test_camera_refit_uses_radius_too():
    src = _read(VIZ3D)
    assert re.search(
        r'Math\.abs\(newRad - oldRad\) / oldRad > 0\.15', src), (
        'kamera refit kriteri yarıçap değişimini içermiyor')


def test_update_preserves_transient_burn_time():
    src = _read(VIZ3D)
    assert re.search(
        r'if \(this\._transient\) this\.dims\.burnTime = this\._transient\.tEnd;',
        src), 'update() transient yanma süresini korumuyor'
