"""3B sahnenin görsel kalitesi — motor_viz3d.js saf fonksiyon bekçileri.

Teşhis (ölçüldü, 2026-08-03):
  * Parçacık boyutu yalnız çıkış yarıçapından geliyordu (size=max(3, re*0.55));
    kamera L/D≈19,7 gövdeyi çerçevelerken parçacık ekranda ~4 px kalıyordu.
  * 900 sabit parçacık ~2,2·L uzunluğa yayılıp kadraj dışına taşıyordu;
    (1-f)² renk sönümü ömrün son 2/3'ünü görünmez yapıyordu.
  * Şok elması opaklığı adapte lülede |1-pe/pa| ≈ 0,06 → fiilen görünmezdi.
  * Kamera kuralı max(L·1.15, R·6) en-boy oranını hiç kullanmıyordu; motor
    kare yüksekliğinin %6,1'ini dolduruyordu.
  * Izgara hücresi L/10 (167 mm, yuvarlak değil) ve motorla ölçekleniyordu.
  * Etiket rozeti çapın %63'üne çıkıyordu; 'ic/dis' ASCII yazılıyordu.

Bu testler düzeltmelerin SAF fonksiyonlarını node ile izole çalıştırıp sayısal
değerlerini sınar (kalıp: tests/test_plume_physics.py). Fizik sürücüleri
(|1-pe/pa|, çözücü çıkış hızı) değişmedi — yalnız görsel aktarım sınanır.
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
    """Tek satirlik `var AD = ...;` sabit bildirimlerini cikarir."""
    source = _source()
    out = []
    for name in names:
        m = re.search(r'var %s = [^;]+;' % re.escape(name), source)
        assert m, 'sabit bulunamadi: %s' % name
        out.append(m.group(0))
    return '\n'.join(out)


CAMERA_CONSTS = ('CAMERA_FIT_MARGIN', 'CAMERA_SLENDER_RATIO',
                 'CAMERA_DIR_REGULAR', 'CAMERA_DIR_DIAGONAL')


def _run(script):
    # Betik argv ile DEĞİL stdin ile verilir: Linux'ta tek argümanın tavanı
    # MAX_ARG_STRLEN = 131072 bayt; büyük gömülü yükte argv biçimi OSError
    # [Errno 7] ile koşmadan ölür. Gerekçenin tamamı ve bekçisi:
    # tests/test_viz3d_cfd_alan.py::_run, tests/test_node_cagri_sozlesmesi.py
    result = subprocess.run([NODE], input=script, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr[:800]
    return json.loads(result.stdout)


def _emit(prelude, expr):
    return _run(prelude + '\nprocess.stdout.write(JSON.stringify(%s));\n' % expr)


# Varsayılan hibrit tasarımın kadraj büyüklükleri (teşhisteki senaryo):
# L≈1670 mm, dış yarıçap (rcOut+flangeLip)≈65 mm, çıkış yarıçapı≈21,6 mm,
# viewport 800x520 (varsayılan konteyner).
L_DEFAULT = 1670.0
R_DEFAULT = 65.0
RE_DEFAULT = 21.6
ASPECT_DEFAULT = 800.0 / 520.0
VH_DEFAULT = 520.0
FOV_DEG = 40.0


def _camera_fit(half_len, max_r, fov, aspect):
    prelude = _consts(*CAMERA_CONSTS) + '\n' + _extract('cameraFrameFit')
    return _emit(prelude, 'cameraFrameFit(%r, %r, %r, %r)'
                 % (half_len, max_r, fov, aspect))


def _project_corners(direction, dist, points, fov, aspect):
    """cameraFrameFit ile ayni izdusum matematigi — Python'da bagimsiz kurulur.

    (u, v) normalize ekran koordinatlari: |u|<=1 ve |v|<=1 kadraj icidir.
    """
    tv = math.tan(math.radians(fov) / 2)
    th = tv * aspect
    d = (direction['x'], direction['y'], direction['z'])
    xn = math.hypot(d[2], d[0])
    x_axis = (d[2] / xn, 0.0, -d[0] / xn)
    y_axis = (d[1] * x_axis[2],
              d[2] * x_axis[0] - d[0] * x_axis[2],
              -d[1] * x_axis[0])
    out = []
    for p in points:
        along = sum(p[i] * d[i] for i in range(3))
        cx = sum(p[i] * x_axis[i] for i in range(3))
        cy = sum(p[i] * y_axis[i] for i in range(3))
        depth = dist - along
        out.append({'u': cx / (th * depth), 'v': cy / (tv * depth),
                    'cx': cx, 'cy': cy, 'along': along, 'depth': depth})
    return out


def _box_corners(half_len, max_r):
    return [(sx * half_len, sy * max_r, sz * max_r)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def _nokta_dogru_parcasi_uzakligi(nokta, a, b):
    """(u,v) ekran duzleminde noktanin [a,b] parcasina uzakligi."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    uzunluk2 = dx * dx + dy * dy
    if uzunluk2 <= 0:
        return math.hypot(nokta[0] - a[0], nokta[1] - a[1])
    t = ((nokta[0] - a[0]) * dx + (nokta[1] - a[1]) * dy) / uzunluk2
    t = max(0.0, min(1.0, t))
    return math.hypot(nokta[0] - (a[0] + t * dx), nokta[1] - (a[1] + t * dy))


# ---------------------------------------------------------------------------
# Kalem 1 — parçacık boyutu kadraj ölçüsüne duyarlı; sayı/ömür boyla orantılı
# ---------------------------------------------------------------------------

class TestParcacikBoyutu:

    def _size(self, exit_r, cam_dist, vh):
        prelude = (_consts('PLUME_PARTICLE_TARGET_PX')
                   + '\n' + _extract('plumeParticleSize'))
        return _emit(prelude, 'plumeParticleSize(%r, %r, %r)'
                     % (exit_r, cam_dist, vh))

    def test_ekran_piksel_hedefi_her_mesafede(self):
        """px = size * (vh/2) / dist — hedefin altina dusmemeli."""
        target = _emit(_consts('PLUME_PARTICLE_TARGET_PX'),
                       'PLUME_PARTICLE_TARGET_PX')
        for dist in (500.0, 2000.0, 8000.0):
            size = self._size(RE_DEFAULT, dist, VH_DEFAULT)
            px = size * (VH_DEFAULT / 2) / dist
            assert px >= target - 0.01, (
                'dist=%s: parcacik %.1f px < hedef %s px' % (dist, px, target))

    def test_varsayilan_hibritte_noktacik_gorunumu_bitti(self):
        """Teşhisteki senaryo: L/D≈19,7 kadrajında parçacık >= 10 px olmalı
        (eski kural ~4 px veriyordu)."""
        fit = _camera_fit(L_DEFAULT / 2, R_DEFAULT, FOV_DEG, ASPECT_DEFAULT)
        size = self._size(RE_DEFAULT, fit['dist'], VH_DEFAULT)
        px = size * (VH_DEFAULT / 2) / fit['dist']
        assert px >= 10.0, 'ev kadrajinda parcacik %.1f px' % px

    def test_alt_sinirlar_korunur(self):
        # Yakın kadrajda eski re tabanlı boyuta düşülür
        assert self._size(40.0, 10.0, VH_DEFAULT) == pytest.approx(22.0)
        # Mutlak 3 mm tabanı durur
        assert self._size(2.0, 10.0, VH_DEFAULT) == pytest.approx(3.0)


class TestParcacikButcesi:

    def _prelude(self):
        return (_consts('PLUME_LEN_PER_MOTOR', 'PLUME_PARTICLES_PER_UNIT')
                + '\n' + _extract('plumeLengthMm')
                + '\n' + _extract('plumeParticleCount')
                + '\n' + _extract('plumeLifeSeconds'))

    def test_yogunluk_motor_boyundan_bagimsiz(self):
        """N / (plumeLen/L) sabit: boy bütçesi değişirse sayı orantılı değişir."""
        p = self._prelude()
        out = _emit(p, '[300, 1670, 4000].map(function (L) {'
                       'return plumeParticleCount(L) / (plumeLengthMm(L) / L); })')
        assert out[0] == pytest.approx(out[1], rel=1e-9)
        assert out[1] == pytest.approx(out[2], rel=1e-9)

    def test_omur_menzili_boy_butcesine_kilitli(self):
        """menzil = life*hız ∈ [0.75, 1.25]·plumeLen — jet başıboş uzamaz."""
        p = self._prelude()
        lo = _emit(p, 'plumeLifeSeconds(1200, 3000, 0) * 3000')
        hi = _emit(p, 'plumeLifeSeconds(1200, 3000, 1) * 3000')
        assert lo == pytest.approx(0.75 * 1200)
        assert hi == pytest.approx(1.25 * 1200)

    def test_plume_boyu_eski_tasmadan_kisa(self):
        """En uzun parçacık menzili bile eski ~2,2·L taşmasının altında."""
        p = self._prelude()
        len_per = _emit(p, 'PLUME_LEN_PER_MOTOR')
        assert len_per * 1.25 <= 1.6, (
            'plume boy butcesi %.2f·L — kadraj disina tasar' % (len_per * 1.25))

    def test_sifir_hizda_bolme_patlamaz(self):
        p = self._prelude()
        out = _emit(p, 'plumeLifeSeconds(1200, 0, 0.5)')
        assert math.isfinite(out) and out > 0


# ---------------------------------------------------------------------------
# Kalem 2 — renk sönüm eğrisi: soğuma kayması, kuyruk görünür kalır
# ---------------------------------------------------------------------------

class TestRenkSonumu:

    def _curve(self, f, intensity=1.0):
        return _emit(_extract('plumeColorAt'),
                     'plumeColorAt(%r, %r)' % (f, intensity))

    def test_omur_sonunda_hala_gorunur(self):
        """Eski (1-f)² eğrisi f=1'de 0'dı; yeni eğri seçilebilir kalmalı."""
        c = self._curve(1.0)
        assert c['fade'] >= 0.2
        assert max(c['r'], c['g'], c['b']) >= 0.15

    def test_eski_egriden_belirgin_parlak(self):
        """f=0.7'de (eskiden görünmez bölge) yeni parlaklık >= 3x eski."""
        c = self._curve(0.7)
        eski = (1 - 0.7) ** 2
        assert c['fade'] >= 3 * eski

    def test_parlaklik_tekduze_azalir(self):
        fades = [self._curve(f)['fade'] for f in (0.0, 0.2, 0.5, 0.8, 1.0)]
        assert all(a > b for a, b in zip(fades, fades[1:])), fades

    def test_soguma_renk_kaymasi(self):
        """r/g oranı yaşla artar: beyaz çekirdek → turuncu → derin kızıl."""
        r0 = self._curve(0.1)
        r1 = self._curve(0.3)
        r2 = self._curve(0.8)
        assert r0['r'] / r0['g'] == pytest.approx(1.0, rel=0.05)   # beyaz-mavi
        assert r1['r'] / r1['g'] > r0['r'] / r0['g']               # turuncu
        assert r2['r'] / r2['g'] > r1['r'] / r1['g']               # kızıl

    def test_siddetle_dogrusal_ve_sifirda_sifir(self):
        half = self._curve(0.5, 0.5)
        full = self._curve(0.5, 1.0)
        assert half['fade'] == pytest.approx(0.5 * full['fade'])
        off = self._curve(0.5, 0.0)
        assert off['r'] == off['g'] == off['b'] == 0


# ---------------------------------------------------------------------------
# Kalem 3 — şok elması görünürlük aktarımı (sürücü |1-pe/pa| korunur)
# ---------------------------------------------------------------------------

class TestSokElmasi:

    def _vis(self, pr):
        prelude = (_consts('DIAMOND_VIS_EXPONENT')
                   + '\n' + _extract('diamondVisibility'))
        return _emit(prelude, 'diamondVisibility(%r)' % pr)

    def test_adapte_lulede_secilebilir(self):
        """Teşhis senaryosu pe/pa=0,9383: eski şiddet 0,062 (görünmez);
        yeni aktarım zayıf ama seçilebilir bir değer vermeli."""
        v = self._vis(0.9383)
        assert 0.15 <= v <= 0.6, 'adapte lule gorunurlugu %.3f' % v
        assert v > abs(1 - 0.9383)      # ham sapmadan yukarı aktarılmış

    def test_ideal_genislemede_sifir(self):
        """pe=pa → hücre yapısı fiziksel olarak yok; uydurma parlaklık yasak."""
        assert self._vis(1.0) == 0

    def test_sapmayla_tekduze_artar(self):
        vs = [self._vis(pr) for pr in (0.95, 0.8, 0.6, 0.3)]
        assert all(a < b for a, b in zip(vs, vs[1:])), vs
        assert vs[-1] >= 0.6            # aşırı genleşmede belirgin

    def test_surucu_gercek_basinc_orani(self):
        """Aynı |1-pe/pa| sapması aynı görünürlüğü verir (az/aşırı genleşme)."""
        assert self._vis(0.8) == pytest.approx(self._vis(1.2))

    def test_buyuk_sapmada_bire_doyar(self):
        assert self._vis(3.0) == pytest.approx(1.0)

    def test_gecersiz_oranda_sifir(self):
        prelude = (_consts('DIAMOND_VIS_EXPONENT')
                   + '\n' + _extract('diamondVisibility'))
        assert _emit(prelude, 'diamondVisibility(NaN)') == 0


# ---------------------------------------------------------------------------
# Kalem 4 — en-boy oranına duyarlı kadraj + köşegen kompozisyon + lüle preseti
# ---------------------------------------------------------------------------

class TestKameraKadraji:

    def test_kutu_iki_fovun_da_icinde(self):
        """Her köşe hem yatay hem dikey FOV kısıtını sağlamalı."""
        for half_len, max_r in ((835.0, 65.0), (150.0, 100.0), (1200.0, 40.0)):
            for aspect in (0.8, ASPECT_DEFAULT, 2.2):
                fit = _camera_fit(half_len, max_r, FOV_DEG, aspect)
                pts = _project_corners(fit['dir'], fit['dist'],
                                       _box_corners(half_len, max_r),
                                       FOV_DEG, aspect)
                for pt in pts:
                    assert pt['depth'] > 0
                    assert abs(pt['u']) <= 1.0 + 1e-6, (half_len, aspect, pt)
                    assert abs(pt['v']) <= 1.0 + 1e-6, (half_len, aspect, pt)

    def test_dar_viewport_daha_uzaga_cekilir(self):
        """En-boy oranı hesaba girmeli: dar pencere daha uzak kadraj ister."""
        dar = _camera_fit(835.0, 65.0, FOV_DEG, 0.7)['dist']
        genis = _camera_fit(835.0, 65.0, FOV_DEG, 2.0)['dist']
        assert dar > genis * 1.2

    def test_ince_govde_kosegene_yatar(self):
        """L/D≈12,8 gövdede eksen ekranda köşegene yatmalı (>=20°);
        tıknaz gövdede klasik yatay kompozisyon (<10°) kalmalı."""
        fit = _camera_fit(835.0, 65.0, FOV_DEG, ASPECT_DEFAULT)
        assert fit['slender'] is True
        ends = _project_corners(fit['dir'], fit['dist'],
                                [(-835.0, 0, 0), (835.0, 0, 0)],
                                FOV_DEG, ASPECT_DEFAULT)
        tilt = math.degrees(math.atan2(abs(ends[1]['v'] - ends[0]['v']),
                                       abs(ends[1]['u'] - ends[0]['u'])))
        assert tilt >= 20.0, 'ince govde ekran egimi %.1f derece' % tilt

        stubby = _camera_fit(150.0, 100.0, FOV_DEG, ASPECT_DEFAULT)
        assert stubby['slender'] is False
        ends = _project_corners(stubby['dir'], stubby['dist'],
                                [(-150.0, 0, 0), (150.0, 0, 0)],
                                FOV_DEG, ASPECT_DEFAULT)
        tilt = math.degrees(math.atan2(abs(ends[1]['v'] - ends[0]['v']),
                                       abs(ends[1]['u'] - ends[0]['u'])))
        assert tilt <= 10.0

    def test_bos_kadraj_payi_dustu(self):
        """Teşhis: motor kare yüksekliğinin %6,1'iydi. Yeni kompozisyonda
        eksenin dikey ekran yayılımı kare yüksekliğinin >= %30'u olmalı;
        genel doluluk >= 0,5."""
        fit = _camera_fit(L_DEFAULT / 2, R_DEFAULT, FOV_DEG, ASPECT_DEFAULT)
        assert fit['fill'] >= 0.5
        assert fit['fill'] <= 1.01
        ends = _project_corners(fit['dir'], fit['dist'],
                                [(-L_DEFAULT / 2, 0, 0), (L_DEFAULT / 2, 0, 0)],
                                FOV_DEG, ASPECT_DEFAULT)
        dikey_pay = abs(ends[1]['v'] - ends[0]['v']) / 2.0
        assert dikey_pay >= 0.30, 'eksen dikey yayilimi %.3f' % dikey_pay

    def test_lule_preseti_yakin_kadraj(self):
        """İkincil preset lüle bölgesine odaklı: bölge kadrajı tam gövde
        kadrajından belirgin yakın olmalı."""
        prelude = (_consts(*CAMERA_CONSTS)
                   + '\n' + _extract('cameraFrameFit')
                   + '\n' + _extract('nozzleRegion'))
        out = _emit(prelude, '(function () {'
                    'var reg = nozzleRegion(%r, %r, %r);'
                    'var noz = cameraFrameFit(reg.halfLen, reg.radius, %r, %r);'
                    'var body = cameraFrameFit(%r, %r, %r, %r);'
                    'return { reg: reg, nozDist: noz.dist, bodyDist: body.dist };'
                    '})()' % (L_DEFAULT, RE_DEFAULT, R_DEFAULT,
                              FOV_DEG, ASPECT_DEFAULT,
                              L_DEFAULT / 2, R_DEFAULT, FOV_DEG, ASPECT_DEFAULT))
        assert out['nozDist'] < 0.5 * out['bodyDist']
        assert out['reg']['halfLen'] >= 3 * RE_DEFAULT
        assert out['reg']['targetOffset'] > 0


# ---------------------------------------------------------------------------
# Kalem 5 — ızgara: yuvarlak mutlak birim hücre, motorla ölçeklenmez
# ---------------------------------------------------------------------------

class TestIzgara:

    def _prelude(self):
        return (_consts('GRID_CELL_STEPS_MM')
                + '\n' + _extract('gridCellMm')
                + '\n' + _extract('gridSpanMm'))

    def test_hucre_yuvarlak_birimden(self):
        p = self._prelude()
        cells = _emit(p, '[60, 150, 300, 900, 1670, 2000, 2500, 5000]'
                         '.map(gridCellMm)')
        assert all(c in (10, 50, 100) for c in cells), cells

    def test_hucre_secim_kurali(self):
        """Motor boyunun 1/20'sini aşmayan en büyük kademe; tabanda 10 mm."""
        p = self._prelude()
        assert _emit(p, 'gridCellMm(1670)') == 50   # teşhis senaryosu: 167 değil
        assert _emit(p, 'gridCellMm(2500)') == 100
        assert _emit(p, 'gridCellMm(2000)') == 100
        assert _emit(p, 'gridCellMm(300)') == 10
        assert _emit(p, 'gridCellMm(150)') == 10    # taban

    def test_acilik_tam_kat_ve_yeterli(self):
        p = self._prelude()
        for L in (150.0, 900.0, 1670.0, 4000.0):
            out = _emit(p, '(function () { var c = gridCellMm(%r);'
                           'return { c: c, s: gridSpanMm(%r, c) }; })()' % (L, L))
            assert out['s'] % out['c'] == 0          # kesik hücre yok
            assert (out['s'] // out['c']) % 2 == 0   # merkez çizgisi eksende
            assert out['s'] >= 2.5 * L               # zemin motoru örter

    def test_izgara_motorla_olceklenmez(self):
        src = _source()
        assert re.search(r'this\._grid\.scale\.setScalar\(1\)', src), (
            'izgara mutlak olcek ataması kaldırılmış')
        assert not re.search(r'_grid\.scale\.setScalar\(fScale\)', src), (
            'izgara yine motorla ölçekleniyor — mutlak referans kayboldu')

    def test_rozet_hucre_boyunu_yazar(self):
        out = _emit(_extract('gridBadgeText'), 'gridBadgeText(50)')
        assert out == 'ızgara 50 mm'                 # UTF-8 'ı' ile
        src = _source()
        assert 'gridBadgeText(cell)' in src, 'rozet sahneye bağlanmamış'


# ---------------------------------------------------------------------------
# Kalem 5b — ızgara rozeti GÖRÜNÜR olmalı (okunamayan beyan beyan değildir)
# ---------------------------------------------------------------------------

class TestIzgaraRozetiGorunurlugu:
    """Ölçülen kusur (2026-08-16, parti 26; durum çipleriyle AYNI sınıf).

    Rozet ızgara açıklığının köşesine konuyordu (±0,42·span). Izgara ~3
    motor boyu olduğu için, kamera MOTORU çerçevelerken rozet kadrajın
    dışında kalıyordu. Katı öğretici motorunda (L = 732,5 mm, R = 54,5 mm,
    800×520 konteyner) eski konum (924 · −50,7 · 924) mm:

        NDC u = −0,979, v = +11,47, DERİNLİK = −193 mm

    yani rozet kameranın arkasındaydı — hücre boyu beyanı hiçbir varsayılan
    kadrajda okunamıyordu. Yeni konum motor boyuna bağlıdır (çip çapasıyla
    aynı gerekçe): (−307,6 · −83,6 · +73,2) mm -> u = −0,505, v = +0,045.

    Bu sınıf düzeltmenin İKİ yanını da kilitler: yeni konum kadrajın içinde
    (ve gövdenin silüetinden uzakta) durur, eski konum ise ölçülebilir
    biçimde dışarıdadır.
    """

    # (L, R) çiftleri: ince gövde (köşegen kompozisyon) ve tıknaz gövde
    OLCU_KUTULARI = ((732.5, 54.5), (1670.0, 65.0), (200.0, 25.0),
                     (400.0, 60.0), (3000.0, 40.0), (150.0, 15.0))
    EN_BOY = (0.8, 1.0, ASPECT_DEFAULT, 2.0, 2.5)

    def _prelude(self):
        return '\n'.join([
            _consts('GRID_BADGE_Z_FACTOR', 'GRID_CELL_STEPS_MM'),
            _extract('gridCellMm'), _extract('gridSpanMm'),
            _extract('labelScaleBase'), _extract('chipAnchorMm'),
            _extract('chipHeightMm'), _extract('gridBadgePositionMm'),
        ])

    def _yerlesim(self, L, R):
        """Sahnenin kurduğu rozet konumu + yüksekliği (mm)."""
        floor_y = -R * 1.9          # MotorScene._buildMotor: -(rcOut+lip)*1.9
        return _emit(self._prelude(),
                     '(function () { var h = chipHeightMm(%r, %r);'
                     'return { h: h, p: gridBadgePositionMm(%r, %r, h) }; })()'
                     % (L, 2 * R, L, floor_y))

    def _eski_yerlesim(self, L, R):
        """Düzeltme öncesi konum (ızgara köşesi) — kusur vakası."""
        return _emit(self._prelude(),
                     '(function () { var c = gridCellMm(%r), s = gridSpanMm(%r, c);'
                     'var h = Math.max(c * 1.1, s * 0.03);'
                     'return { h: h, p: { x: s * 0.42, y: %r + h * 0.8,'
                     ' z: s * 0.42 } }; })()' % (L, L, -R * 1.9))

    def _izdusum(self, nokta, L, R, aspect):
        fit = _camera_fit(L / 2, R, FOV_DEG, aspect)
        pt = _project_corners(fit['dir'], fit['dist'],
                              [(nokta['x'], nokta['y'], nokta['z'])],
                              FOV_DEG, aspect)[0]
        pt['fit'] = fit
        return pt

    def test_rozet_kadrajin_icinde(self):
        """Her gövde ve her en-boy oranında rozet ekranda kalır."""
        for L, R in self.OLCU_KUTULARI:
            yer = self._yerlesim(L, R)
            for aspect in self.EN_BOY:
                pt = self._izdusum(yer['p'], L, R, aspect)
                assert pt['depth'] > 0, (
                    'L=%s R=%s en-boy=%s: rozet kameranın ARKASINDA '
                    '(derinlik %.1f mm)' % (L, R, aspect, pt['depth']))
                assert abs(pt['u']) <= 1.0 and abs(pt['v']) <= 1.0, (
                    'L=%s R=%s en-boy=%s: rozet kadraj dışında '
                    '(u=%.3f v=%.3f)' % (L, R, aspect, pt['u'], pt['v']))

    def test_eski_izgara_kosesi_olculebilir_bicimde_disaridaydi(self):
        """Kusur vakası: düzeltilen konum GERÇEKTEN görünmezdi."""
        disarida = 0
        for L, R in self.OLCU_KUTULARI:
            eski = self._eski_yerlesim(L, R)
            pt = self._izdusum(eski['p'], L, R, ASPECT_DEFAULT)
            if pt['depth'] <= 0 or abs(pt['u']) > 1 or abs(pt['v']) > 1:
                disarida += 1
        assert disarida == len(self.OLCU_KUTULARI), (
            'eski ızgara-köşesi konumu bazı gövdelerde görünürmüş; teşhis '
            'senaryosu geçerliliğini yitirdi (%d/%d dışarıda)'
            % (disarida, len(self.OLCU_KUTULARI)))

    def test_kati_ogretici_motorunda_olculen_degerler(self):
        """Rapordaki sayılar bekçide durur: eski v=+11,47 / yeni v=+0,045."""
        L, R = 732.5, 54.5
        eski = self._izdusum(self._eski_yerlesim(L, R)['p'], L, R, ASPECT_DEFAULT)
        yeni = self._izdusum(self._yerlesim(L, R)['p'], L, R, ASPECT_DEFAULT)
        assert eski['v'] == pytest.approx(11.474, abs=0.01)
        assert eski['depth'] == pytest.approx(-192.7, abs=1.0)
        assert yeni['v'] == pytest.approx(0.045, abs=0.01)
        assert yeni['u'] == pytest.approx(-0.505, abs=0.01)

    def test_rozet_govde_siluetine_binmiyor(self):
        """Rozet önde durur ama eksenin üstüne çizilmez: ekran uzaklığı
        gövdenin izdüşüm yarıçapının en az 1,2 katı (ölçülen en dar
        vaka 1,41 — L=200 mm, R=15 mm, en-boy 2,5)."""
        for L, R in self.OLCU_KUTULARI:
            yer = self._yerlesim(L, R)
            for aspect in self.EN_BOY:
                pt = self._izdusum(yer['p'], L, R, aspect)
                fit = pt['fit']
                uclar = _project_corners(fit['dir'], fit['dist'],
                                         [(-L / 2, 0, 0), (L / 2, 0, 0)],
                                         FOV_DEG, aspect)
                merkez = _project_corners(fit['dir'], fit['dist'],
                                          [(0, 0, 0), (0, R, 0)],
                                          FOV_DEG, aspect)
                yaricap_ndc = abs(merkez[1]['v'] - merkez[0]['v'])
                d = _nokta_dogru_parcasi_uzakligi(
                    (pt['u'], pt['v']),
                    (uclar[0]['u'], uclar[0]['v']),
                    (uclar[1]['u'], uclar[1]['v']))
                assert d >= 1.2 * yaricap_ndc, (
                    'L=%s R=%s en-boy=%s: rozet gövdenin üstünde '
                    '(uzaklık %.3f, yarıçap %.3f)' % (L, R, aspect, d,
                                                      yaricap_ndc))

    def test_capa_motor_boyundan_turer(self):
        """Konum ızgara açıklığına değil MOTOR boyuna bağlıdır: boy iki
        katına çıkınca konum da iki katına çıkar, ızgara kademesi
        (10/50/100 mm) değişse bile."""
        a = self._yerlesim(1000.0, 50.0)['p']
        b = self._yerlesim(2000.0, 100.0)['p']
        assert b['x'] == pytest.approx(2 * a['x'])
        assert b['z'] == pytest.approx(2 * a['z'])
        # Konum model kutusunun içinde kalır (kadrajın türediği kutu)
        for L, R in self.OLCU_KUTULARI:
            p = self._yerlesim(L, R)['p']
            assert 0 < abs(p['x']) < L / 2 and 0 < p['z'] < L / 2, (L, R, p)
        src = _source()
        assert 'gridBadgePositionMm(this._totalLen' in src, (
            'rozet konumu yine ızgara açıklığından hesaplanıyor')
        assert not re.search(r'_gridBadge\.position\.set\(this\._gridSpan', src), (
            'ızgara açıklığına bağlı eski konum geri gelmiş')

    def test_rozet_olcegi_olcu_rozetleriyle_ayni_ailede(self):
        """Yükseklik labelScaleBase ailesinden gelir (çip düzeltmesinin
        deseni); eski span·0,03 kuralı 732 mm'lik motorda 66 mm rozet
        üretiyordu — yenisi 25,0 mm."""
        yer = self._yerlesim(732.5, 54.5)
        eski = self._eski_yerlesim(732.5, 54.5)
        assert eski['h'] == pytest.approx(66.0)
        assert yer['h'] == pytest.approx(24.99, abs=0.05)
        src = _source()
        assert re.search(r'gbH = chipHeightMm\(this\._totalLen', src), (
            'rozet yüksekliği ölçü rozeti ölçeğinden gelmiyor')
        assert 'span * 0.03' not in src, (
            'ızgara açıklığına bağlı eski rozet ölçeği geri gelmiş')

    def test_rozet_her_kurulumda_tazelenir(self):
        """Rozet yalnız IZGARA değişince yeniden kurulur; motor boyu
        değişip ızgara kademesi aynı kalabilir. Ölçek ve konum bu yüzden
        kurulum bloğunun DIŞINDA, her _buildMotor'da atanır."""
        src = _source()
        blok = src[src.index('this.scene.add(badge);'):
                   src.index('this._floorY = floorY;')]
        assert '_gridBadge.scale.set' in blok, (
            'rozet ölçeği yalnız ızgara kurulumunda atanıyor — bayatlar')
        assert '_gridBadge.position.set' in blok


# ---------------------------------------------------------------------------
# Kalem 6 — etiket ölçeği çapla sınırlı; kılavuz ofseti yarıçapa oranlı
# ---------------------------------------------------------------------------

class TestEtiketOlcegi:

    def test_rozet_cap_sinirinin_altinda(self):
        """Rozet yüksekliği (0.62·scaleBase) <= 0,5·çap — her gövdede."""
        p = _extract('labelScaleBase')
        for L, D in ((1670.0, 95.0), (1670.0, 90.0), (300.0, 150.0),
                     (5000.0, 60.0), (400.0, 40.0)):
            base = _emit(p, 'labelScaleBase(%r, %r)' % (L, D))
            hgt = 0.62 * base
            assert hgt <= 0.5 * D + 1e-9, (
                'L=%s D=%s: rozet %.1f mm = capin %%%.0f\'i'
                % (L, D, hgt, 100 * hgt / D))

    def test_tiknaz_govdede_boy_kurali_korunur(self):
        """Çap sınırı bağlamıyorsa eski L·0.055 ölçeği aynen kalır."""
        p = _extract('labelScaleBase')
        assert _emit(p, 'labelScaleBase(300, 150)') == pytest.approx(300 * 0.055)

    def test_kilavuz_ofseti_yaricapa_oranli(self):
        p = _extract('labelLeaderOffset')
        o100 = _emit(p, 'labelLeaderOffset(100, 30)')
        o200 = _emit(p, 'labelLeaderOffset(200, 30)')
        assert o200 - o100 == pytest.approx(0.45 * 100)   # oran 0,45·r
        # Taban: rozet yüksekliğinin (0.62·scaleBase) altına inmez
        assert _emit(p, 'labelLeaderOffset(1, 100)') == pytest.approx(62.0)


# ---------------------------------------------------------------------------
# Kalem 7 — sahne dili tek (Türkçe), 'iç/dış' UTF-8
# ---------------------------------------------------------------------------

HYBRID_DIMS = ("{ motorType: 'hybrid', chamberInnerMm: 85.0, "
               "chamberOuterMm: 95.5, throatMm: 23.4, exitMm: 43.2, "
               "totalMm: 1670.4, grainMm: 450.0 }")


class TestSahneDili:

    def _texts(self, dims_js=HYBRID_DIMS):
        return _emit(_extract('dimensionLabelTexts'),
                     'dimensionLabelTexts(%s)' % dims_js)

    def test_ic_dis_turkce_yazilir(self):
        ch = self._texts()['chamber']
        assert 'iç' in ch and 'dış' in ch, ch
        assert not re.search(r'\bic\b', ch), ch     # ASCII kaçışı geri gelmesin
        assert not re.search(r'\bdis\b', ch), ch

    def test_sahne_dili_tek(self):
        t = self._texts()['total']
        assert 'YAKIT' in t and 'GRAIN' not in t, t
        liq = self._texts(HYBRID_DIMS.replace("'hybrid'", "'liquid'"))['total']
        assert 'ODA' in liq and 'CHAMBER' not in liq, liq

    def test_sayilar_gercek_girdiden_gelir(self):
        """Etiketteki her sayı girdiden türer — uydurma değer yok."""
        out = self._texts()
        assert '85.0' in out['chamber'] and '95.5' in out['chamber']
        assert '23.4' in out['throat']
        assert '43.2' in out['exit']
        assert '1670' in out['total'] and '450' in out['total']

    def test_ascii_kalinti_kaynakta_yok(self):
        src = _source()
        assert "ØC ic " not in src and "/ dis " not in src, (
            "'ic/dis' ASCII etiketi kaynağa geri dönmüş")


# ---------------------------------------------------------------------------
# Kablolama — saf fonksiyonlar sahneye gerçekten bağlı, eski formüller ölü
# ---------------------------------------------------------------------------

class TestKablolama:

    def test_js_sozdizimi(self):
        res = subprocess.run([NODE, '--check', str(VIZ_JS)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, res.stderr

    @pytest.mark.parametrize('name', [
        'plumeParticleSize', 'plumeLengthMm', 'plumeParticleCount',
        'plumeLifeSeconds', 'plumeColorAt', 'diamondVisibility',
        'cameraFrameFit', 'nozzleRegion', 'gridCellMm', 'gridSpanMm',
        'gridBadgeText', 'gridBadgePositionMm', 'labelScaleBase',
        'labelLeaderOffset', 'dimensionLabelTexts',
    ])
    def test_fonksiyon_tanimli_ve_kullaniliyor(self, name):
        src = _source()
        assert len(re.findall(r'\b%s\(' % name, src)) >= 2, (
            '%s tanımlı ama sahnede hiç çağrılmıyor (ölü düzeltme)' % name)

    def test_eski_formuller_geri_donmedi(self):
        src = _source()
        assert 'Math.max(3, d.re * 0.55)' not in src          # sabit boyut
        assert 'Math.max(3, this.dims.re * 0.55)' not in src
        assert 'Math.max(L * 1.15, R * 6)' not in src         # tek eksenli kadraj
        assert '(1 - f) * (1 - f)' not in src                 # görünmez kuyruk
        assert 'this._totalLen * 0.055' not in src            # çapsız etiket ölçeği
        assert 'var N = 900' not in src                       # sabit parçacık sayısı
        assert not re.search(r'GridHelper\(this\._totalLen', src)  # ölçekli ızgara

    def test_parcacik_omru_butceden(self):
        src = _source()
        assert 'plumeLifeSeconds(' in src
        assert not re.search(r'maxLife = 0\.35 \+', src), (
            'sabit parçacık ömrü geri gelmiş — plume boy bütçesi devre dışı')
