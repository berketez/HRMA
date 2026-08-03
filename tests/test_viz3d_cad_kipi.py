"""CAD kipi + CAD veri sözleşmesi bekçileri (v2.6.27, motor_viz3d.js 2. tur).

Kapattığı kusurlar (2026-08-04):
  * B1 — SAHTE 8 BİLEZİK: her sıvı motora, veriden bağımsız 8 dekoratif
    çevresel "soğutma bileziği" çiziliyordu (var nRib = 8). Artık gerçek
    kanallar cooling_channels bloğundan gelir; veri yoksa HİÇ kanal
    çizilmez ve sahne 'soğutma kanalları: veri yok' çipiyle beyan eder.
  * B2 — enjektör deseni derinliği (çarpışma çizgileri, swirl açısı)
    YALNIZ injector_pattern verisi varsa; yoksa mevcut davranış korunur.
  * B3 — lüle konturu tek kaynaktan: nozzle_contour.points varsa ORADAN,
    yoksa yerel üretim + 'kontur: yerel üretim' beyan çipi.
  * CAD kipi — ortografik görünüş preset matematiği (front/top/side/iso).
  * Tasarım dili — kaynak-renk eşlemesi (hesaplanmış/kullanıcı/varsayım/
    veri yok) tablo olarak dışa açık ve dört durumu da içeriyor.

Veri sözleşmesi (şablon adaptörleri passthrough; savunmacı okunur):
  cooling_channels: { n_channels, channel_width_m, channel_height_m,
                      land_width_m, _basis }
  injector_pattern: { n_holes, hole_diameter_m, pattern_type,
                      impingement_angle_deg?, n_rings?, _basis }
  nozzle_contour:   { points: [[z_m, r_m], ...], _basis }

Kalıp: tests/test_plume_physics.py — saf fonksiyonlar node ile izole koşulur.
"""

import json
import math
import re
import shutil
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadi')


# ---------------------------------------------------------------------------
# Yardımcılar — fonksiyon/sabit çıkarımı ve node koşumu
# ---------------------------------------------------------------------------

def _source():
    return VIZ_JS.read_text(encoding='utf-8')


def _extract(func_name):
    """motor_viz3d.js icinden tek bir fonksiyonu izole cikarir."""
    source = _source()
    start = source.index('function %s(' % func_name)
    depth, idx = 0, start
    while idx < len(source):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                return source[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % func_name)


def _consts(*names):
    """`var AD = ...;` sabit bildirimlerini cikarir (tek/çok satır)."""
    source = _source()
    out = []
    for name in names:
        m = re.search(r'var %s = [^;]+;' % re.escape(name), source)
        assert m, 'sabit bulunamadi: %s' % name
        out.append(m.group(0))
    return '\n'.join(out)


def _run(script):
    result = subprocess.run([NODE, '-e', script], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr[:800]
    return json.loads(result.stdout)


def _emit(prelude, expr):
    return _run(prelude + '\nprocess.stdout.write(JSON.stringify(%s) '
                          '|| "null");\n' % expr)


# ---------------------------------------------------------------------------
# B1a — sahte 8 bilezik kaynaktan söküldü
# ---------------------------------------------------------------------------

class TestSahteBilezikSokumu:

    def test_nrib_kaynakta_yok(self):
        """Dekoratif 'var nRib = 8' kalıbı (ve her türlü nRib izi) gitmiş."""
        assert 'nRib' not in _source(), (
            "sahte 8 bilezik geri gelmiş: kaynakta 'nRib' var")

    def test_dekoratif_bilezik_geometrisi_yok(self):
        """Eski bileziklerin imzası TorusGeometry(d.rcOut + 1.2, 1.4, ...)."""
        assert not re.search(r'TorusGeometry\(d\.rcOut \+ 1\.2,\s*1\.4', _source()), (
            'dekoratif soğutma bileziği geometrisi geri gelmiş')

    def test_gercek_kanal_uretimi_kablolu(self):
        src = _source()
        for name in ('coolingChannelSpec', 'coolingChannelLayout'):
            assert len(re.findall(r'\b%s\(' % name, src)) >= 2, (
                '%s tanımlı ama sahnede çağrılmıyor (ölü düzeltme)' % name)


# ---------------------------------------------------------------------------
# B1b — soğutma kanalları: veri varsa n_channels adet, yoksa 0 + çip
# ---------------------------------------------------------------------------

COOLING_OK = {
    'cooling_channels': {
        'n_channels': 96,
        'channel_width_m': 0.002,
        'channel_height_m': 0.0035,
        'land_width_m': 0.0015,
        '_basis': 'hesaplandı',
    }
}


class TestSogutmaKanallari:

    def _prelude(self):
        return (_consts('TAU')
                + '\n' + _extract('num')
                + '\n' + _extract('coolingChannelSpec')
                + '\n' + _extract('coolingChannelLayout'))

    def _spec(self, md):
        return _emit(self._prelude(),
                     'coolingChannelSpec(%s)' % json.dumps(md))

    def _layout(self, md):
        return _emit(self._prelude(),
                     'coolingChannelLayout(coolingChannelSpec(%s))'
                     % json.dumps(md))

    def test_veri_varsa_kanal_sayisi_n_channels(self):
        """Sözleşme: n_channels=96 verildiyse TAM 96 kanal üretilir."""
        chans = self._layout(COOLING_OK)
        assert len(chans) == 96

    def test_kanal_olculeri_metreden_mm(self):
        chans = self._layout(COOLING_OK)
        assert chans[0]['widthMm'] == pytest.approx(2.0)
        assert chans[0]['heightMm'] == pytest.approx(3.5)
        spec = self._spec(COOLING_OK)
        assert spec['landMm'] == pytest.approx(1.5)
        assert spec['basis'] == 'hesaplandı'

    def test_kanallar_cevreye_esit_dagitilir(self):
        chans = self._layout(COOLING_OK)
        assert chans[0]['phi'] == pytest.approx(0.0)
        step = 2 * math.pi / 96
        assert chans[1]['phi'] == pytest.approx(step)
        assert chans[-1]['phi'] == pytest.approx(step * 95)

    def test_veri_yoksa_sifir_kanal(self):
        """Blok yok / null → HİÇ kanal çizilmez (uydurma yasak)."""
        assert self._layout({}) == []
        assert self._spec({}) is None
        assert self._layout({'cooling_channels': None}) == []

    def test_bozuk_veri_reddedilir(self):
        bozuk = [
            {'cooling_channels': {'n_channels': 0, 'channel_width_m': 0.002,
                                  'channel_height_m': 0.003}},
            {'cooling_channels': {'n_channels': 40, 'channel_width_m': -1,
                                  'channel_height_m': 0.003}},
            {'cooling_channels': {'n_channels': 40,
                                  'channel_width_m': 0.002}},  # yükseklik yok
            # Sözleşme DIŞI şekil (başka adlandırma) = veri yok sayılır
            {'cooling_channels': {'channel_count': 40,
                                  'channel_width_mm': 2.0}},
            {'cooling_channels': 'bir metin'},
        ]
        for md in bozuk:
            assert self._spec(md) is None, md

    def test_veri_yok_cipi_kablolu(self):
        """Veri yokken sahneye 'veri yok' çipi konur (beyan, süs değil)."""
        src = _source()
        assert 'soğutma kanalları: veri yok' in src
        assert '_coolingChip' in src
        assert '_buildStatusChips' in src


# ---------------------------------------------------------------------------
# B2 — enjektör deseni derinliği: yalnız injector_pattern verisiyle
# ---------------------------------------------------------------------------

class TestEnjektorDeseni:

    def _read(self, md):
        prelude = _extract('num') + '\n' + _extract('readInjectorPattern')
        return _emit(prelude, 'readInjectorPattern(%s)' % json.dumps(md))

    def _apex(self, r, half_deg):
        prelude = (_extract('num') + '\n' + _extract('clamp')
                   + '\n' + _extract('impingementApexZ'))
        return _emit(prelude, 'impingementApexZ(%s, %s)'
                     % (json.dumps(r), json.dumps(half_deg)))

    def test_veri_yoksa_null_mevcut_davranis_korunur(self):
        """Blok yoksa null → ek desen grafiği ÇİZİLMEZ; delik deseni zaten
        injector_results/injector_design gerçek kaynağından geliyor."""
        assert self._read({}) is None
        assert self._read({'injector_pattern': None}) is None
        assert self._read({'injector_pattern': {'pattern_type': 'swirl'}}) is None

    def test_impinging_sozlesmeden_okunur(self):
        out = self._read({'injector_pattern': {
            'n_holes': 24, 'hole_diameter_m': 0.0012,
            'pattern_type': 'impinging', 'impingement_angle_deg': 60,
            '_basis': 'hesaplandı'}})
        assert out['nHoles'] == 24
        assert out['holeDiaMm'] == pytest.approx(1.2)
        assert out['patternType'] == 'impinging'
        # Sözleşme iki jet arası TAM açı verir; çizim yarım açı kullanır
        assert out['impingeHalfDeg'] == pytest.approx(30.0)
        assert out['basis'] == 'hesaplandı'

    def test_carpisma_istasyonu_duz_geometri(self):
        """z = r / tan(θ) — uydurma katsayı yok."""
        assert self._apex(30.0, 30.0) == pytest.approx(
            30.0 / math.tan(math.radians(30.0)))
        # Dik açı → çarpışma yüzeye daha yakın
        assert self._apex(30.0, 45.0) < self._apex(30.0, 30.0)

    def test_gecersiz_girdide_cizgi_yok(self):
        assert self._apex(30.0, None) is None
        assert self._apex(0.0, 30.0) is None
        assert self._apex(-5.0, 30.0) is None

    def test_desen_kablolu(self):
        src = _source()
        assert len(re.findall(r'\bimpingementApexZ\(', src)) >= 2
        assert 'injPattern' in src
        # Swirl açı gösterimi gerçek açı değerini yazar
        assert 'sprey açısı' in src
        # Desen bloğu yalnız veri varken çalışır
        assert re.search(r'if \(pat && pat\.patternType', src)


# ---------------------------------------------------------------------------
# B3 — lüle konturu tek kaynaktan
# ---------------------------------------------------------------------------

class TestKonturSecimi:

    def _sel(self, contour):
        prelude = _extract('num') + '\n' + _extract('selectNozzleContour')
        return _emit(prelude, 'selectNozzleContour(%s)' % json.dumps(contour))

    def test_cozucu_konturu_secilir(self):
        out = self._sel({'points': [[0.0, 0.05], [0.01, 0.02],
                                    [0.02, 0.021], [0.03, 0.04]],
                         '_basis': 'çözücü örneklemesi'})
        assert out['source'] == 'solver'
        assert len(out['points']) == 4
        # Metre → mm çevrimi
        assert out['points'][0] == {'z': 0.0, 'r': 50.0}
        assert out['points'][1] == {'z': 10.0, 'r': 20.0}
        assert out['points'][-1] == {'z': 30.0, 'r': 40.0}
        assert out['basis'] == 'çözücü örneklemesi'

    def test_veri_yoksa_yerel_uretim(self):
        for contour in (None, {}, {'points': []},
                        {'points': [[0.0, 0.05], [0.01, 0.02]]}):  # < 3 nokta
            out = self._sel(contour)
            assert out['source'] == 'local', contour
            assert out['points'] is None

    def test_bozuk_nokta_dizisi_butunuyle_reddedilir(self):
        """Yarım gerçek kontur çizilmez: tek bozuk nokta diziyi düşürür."""
        bozuk = [
            {'points': [[0.0, 0.05], [None, 0.02], [0.03, 0.04]]},
            {'points': [[0.0, 0.05], [0.01, -0.2], [0.03, 0.04]]},
            # z artmıyor (örnekleme sırası bozuk)
            {'points': [[0.0, 0.05], [0.0, 0.02], [0.03, 0.04]]},
            {'points': [[0.02, 0.05], [0.01, 0.02], [0.03, 0.04]]},
        ]
        for contour in bozuk:
            assert self._sel(contour)['source'] == 'local', contour

    def test_kaynak_beyani_kablolu(self):
        """Yerel üretim sahnede saklanmaz, çiple beyan edilir."""
        src = _source()
        assert 'kontur: yerel üretim' in src
        assert 'kontur: çözücü' in src
        # nozzleInnerContour gerçekten çözücü noktalarını okuyor
        assert re.search(r'dims\.contourPoints', src)
        assert len(re.findall(r'\bselectNozzleContour\(', src)) >= 2


# ---------------------------------------------------------------------------
# CAD kipi — ortografik görünüş preset matematiği
# ---------------------------------------------------------------------------

L_HALF = 835.0
R_MAX = 65.0
ASPECT_DEFAULT = 800.0 / 520.0


def _ortho(name, half_len=L_HALF, max_r=R_MAX, aspect=ASPECT_DEFAULT):
    prelude = (_consts('ORTHO_MARGIN', 'ORTHO_PRESETS')
               + '\n' + _extract('orthoPresetFrustum'))
    return _emit(prelude, 'orthoPresetFrustum(%s, %r, %r, %r)'
                 % (json.dumps(name), half_len, max_r, aspect))


def _ortho_axes(fit):
    """orthoPresetFrustum ile ayni eksen matematigi — Python'da bagimsiz."""
    d = (fit['dir']['x'], fit['dir']['y'], fit['dir']['z'])
    up = (fit['up']['x'], fit['up']['y'], fit['up']['z'])
    cx = up[1] * d[2] - up[2] * d[1]
    cy = up[2] * d[0] - up[0] * d[2]
    cz = up[0] * d[1] - up[1] * d[0]
    n = math.sqrt(cx * cx + cy * cy + cz * cz)
    x_axis = (cx / n, cy / n, cz / n)
    y_axis = (d[1] * x_axis[2] - d[2] * x_axis[1],
              d[2] * x_axis[0] - d[0] * x_axis[2],
              d[0] * x_axis[1] - d[1] * x_axis[0])
    return x_axis, y_axis


def _ortho_project(fit, points):
    x_axis, y_axis = _ortho_axes(fit)
    return [(sum(p[i] * x_axis[i] for i in range(3)),
             sum(p[i] * y_axis[i] for i in range(3))) for p in points]


def _box_corners(half_len, max_r):
    return [(sx * half_len, sy * max_r, sz * max_r)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


class TestOrtografikPreset:

    @pytest.mark.parametrize('name', ['front', 'top', 'side', 'iso'])
    def test_kutu_her_goruniste_kadraj_icinde(self, name):
        fit = _ortho(name)
        for px, py in _ortho_project(fit, _box_corners(L_HALF, R_MAX)):
            assert abs(px) <= fit['halfW'] + 1e-9, (name, px)
            assert abs(py) <= fit['halfH'] + 1e-9, (name, py)

    @pytest.mark.parametrize('name', ['front', 'top', 'side', 'iso'])
    def test_bakis_birim_ve_eksenler_dik(self, name):
        """Bakış yönü birim; up bakışla dejenere değil (çapraz çarpımlar
        tanımlı) ve türetilen ekran eksenleri ortonormal — three.js lookAt
        ile aynı kural (up yalnız ipucudur, dikleştirme cross ile yapılır)."""
        fit = _ortho(name)
        d = (fit['dir']['x'], fit['dir']['y'], fit['dir']['z'])
        up = (fit['up']['x'], fit['up']['y'], fit['up']['z'])
        assert math.sqrt(sum(c * c for c in d)) == pytest.approx(1.0)
        dot_up = sum(d[i] * up[i] for i in range(3))
        assert abs(dot_up) < 0.99, 'up bakisla paralel (dejenere): %s' % name
        # Türetilen eksenler: birim boyda, birbirine ve bakışa dik
        (x_axis, y_axis) = _ortho_axes(fit)
        for ax in (x_axis, y_axis):
            assert math.sqrt(sum(c * c for c in ax)) == pytest.approx(1.0)
            assert abs(sum(ax[i] * d[i] for i in range(3))) < 1e-9
        assert abs(sum(x_axis[i] * y_axis[i] for i in range(3))) < 1e-9

    def test_on_gorunus_boyu_payla_kapsar(self):
        """Alın görünüşte yatay yarı-açıklık = pay x yarı boy; dikey
        en-boy oranından türer (kısıtlayıcı eksen korunur)."""
        fit = _ortho('front')
        assert fit['halfW'] == pytest.approx(1.08 * L_HALF)
        assert fit['halfH'] == pytest.approx(fit['halfW'] / ASPECT_DEFAULT)

    def test_yan_gorunus_eksen_boyu_bakis(self):
        """Eksen boyu görünüşte kutu izdüşümü yarıçap karesidir."""
        fit = _ortho('side')
        assert fit['halfH'] == pytest.approx(1.08 * R_MAX)
        assert fit['halfW'] == pytest.approx(fit['halfH'] * ASPECT_DEFAULT)

    def test_ust_gorunus_teknik_resim_upi(self):
        """Üstten bakışta up=-Z: motor ekseni ekranda yatay yatar."""
        fit = _ortho('top')
        assert fit['up'] == {'x': 0, 'y': 0, 'z': -1}
        # Eksen ucu (X) ekran yatayına düşer
        (px, py), = _ortho_project(fit, [(L_HALF, 0.0, 0.0)])
        assert abs(px) == pytest.approx(L_HALF)
        assert abs(py) < 1e-9

    def test_bilinmeyen_ad_izometrige_duser(self):
        assert _ortho('bogus') == _ortho('iso')

    def test_kamera_kutunun_disinda(self):
        for name in ('front', 'top', 'side', 'iso'):
            fit = _ortho(name)
            assert fit['dist'] > L_HALF + R_MAX

    def test_cad_kipi_kablolu(self):
        src = _source()
        assert len(re.findall(r'\borthoPresetFrustum\(', src)) >= 2
        assert 'OrthographicCamera' in src
        assert 'MotorScene.prototype.setCadMode' in src
        assert 'MotorScene.prototype.setCadPreset' in src
        # Dışa açık API (deck ve sayfalar için)
        assert re.search(r'setCadMode:\s*function', src)
        assert re.search(r'setCadPreset:\s*function', src)

    def test_kip_gecisi_durum_kaybetmez(self):
        """Girişte perspektif görünüm saklanır, çıkışta geri yüklenir;
        ölçü etiketleri kipe göre yeniden kurulur."""
        src = _source()
        assert '_cadSaved' in src
        assert re.search(r'_enterCad', src) and re.search(r'_exitCad', src)
        assert re.search(r'position\.copy\(s\.pos\)', src)
        set_cad = _extract_proto(src, 'setCadMode')
        assert 'this._buildLabels()' in set_cad
        # CAD leader ölçüleri etiket kurulumuna bağlı
        assert re.search(r'var cad = this\.state\.cadMode', src)


def _extract_proto(src, method):
    """MotorScene.prototype.<method> govdesini kabaca cikarir."""
    start = src.index('MotorScene.prototype.%s' % method)
    depth, idx, opened = 0, start, False
    while idx < len(src):
        if src[idx] == '{':
            depth += 1
            opened = True
        elif src[idx] == '}':
            depth -= 1
            if opened and depth == 0:
                return src[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % method)


# ---------------------------------------------------------------------------
# Tasarım dili — kaynak-renk eşlemesi dışa açık, dört durum
# ---------------------------------------------------------------------------

def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


class TestKaynakRenkleri:

    def _table(self):
        return _emit(_consts('SOURCE_COLORS'), 'SOURCE_COLORS')

    def test_tablo_dort_durumu_da_icerir(self):
        table = self._table()
        assert set(table.keys()) == {'computed', 'user', 'assumed', 'missing'}
        for v in table.values():
            assert re.match(r'^#[0-9a-fA-F]{6}$', v), v
        assert len(set(table.values())) == 4, 'renkler ayrışmalı'

    def test_renkler_durum_ailelerine_bagli(self):
        """Renk keyfî değil: her aile kendi durumunu kodlar."""
        t = {k: _rgb(v) for k, v in self._table().items()}
        r, g, b = t['computed']
        assert b >= g > r, 'hesaplanmış camgöbeği ailesinde olmalı'
        assert min(t['user']) >= 200, 'kullanıcı girdisi beyaz ailede olmalı'
        r, g, b = t['assumed']
        assert r > g > b, 'varsayım amber ailede olmalı'
        assert max(t['missing']) - min(t['missing']) <= 40, (
            'veri yok gri (düşük doygunluk) olmalı')

    def test_sourcecolor_eslemesi_ve_yedegi(self):
        prelude = _consts('SOURCE_COLORS') + '\n' + _extract('sourceColor')
        table = self._table()
        for kind in ('computed', 'user', 'assumed', 'missing'):
            assert _emit(prelude, 'sourceColor(%r)' % kind) == table[kind]
        # Bilinmeyen durum 'veri yok' rengine düşer (asla uydurma renk)
        assert _emit(prelude, "sourceColor('bilinmeyen')") == table['missing']

    def test_tablo_disa_acik(self):
        assert re.search(r'SOURCE_COLORS:\s*SOURCE_COLORS', _source()), (
            'kaynak-renk tablosu window.MotorViz3D üstünden dışa açık değil')

    def test_cipler_tablodan_beslenir(self):
        chip_fn = _extract('statusChip')
        assert 'sourceColor(' in chip_fn
        # Ölçü çizgileri de hesaplanmış-camgöbeğine bağlı
        assert re.search(r'sourceColor\(.computed.\)', _source())


# ---------------------------------------------------------------------------
# Kablolama + sözdizimi
# ---------------------------------------------------------------------------

class TestKablolama:

    def test_js_sozdizimi(self):
        res = subprocess.run([NODE, '--check', str(VIZ_JS)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, res.stderr

    @pytest.mark.parametrize('name', [
        'coolingChannelSpec', 'coolingChannelLayout', 'readInjectorPattern',
        'impingementApexZ', 'selectNozzleContour', 'orthoPresetFrustum',
        'sourceColor', 'statusChip',
    ])
    def test_fonksiyon_tanimli_ve_kullaniliyor(self, name):
        src = _source()
        assert len(re.findall(r'\b%s\(' % name, src)) >= 2, (
            '%s tanımlı ama sahnede hiç çağrılmıyor (ölü düzeltme)' % name)

    def test_cad_veri_sozlesmesi_extractdimste(self):
        """Savunmacı okuma extractDims'e bağlı: bloklar yoksa null/[] kalır."""
        src = _source()
        assert re.search(r'cooling:\s*coolingChannelSpec\(md\)', src)
        assert re.search(r'injPattern:\s*readInjectorPattern\(md\)', src)
        assert re.search(r'contourSource:\s*contourSel\.source', src)

    def test_arac_cubugu_cad_anahtari(self):
        """Araç çubuğunda CAD kipi + ortografik görünüş butonları var."""
        src = _source()
        assert '_buildToolbar' in src
        assert re.search(r"mkBtn\('CAD'", src)
        for label in ('ÖN', 'ÜST', 'YAN', 'İZO'):
            assert label in src, 'ortografik görünüş butonu eksik: %s' % label
