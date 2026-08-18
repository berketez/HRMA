"""Alev estetiği — egzoz 'parçacık bulutu'ndan tutarlı aleve (motor_viz3d.js).

Teşhis (2026-08-04): egzoz üç motorda da gerçek çözücü verisiyle yanıyor
ama görünüm 'patlamış mısır' — sert kenarlı ayrık parlak toplar, banda
bölünmüş sabit renk, parçacıkların altında süreklilik katmanı yok.

Düzeltmenin sözleşmesi: her görsel parametre GERÇEK çıkış durumundan türer,
süs yok:
  * Sprite profili Gauss (türbülanslı jetin öz-benzer profili, Pope §5.1);
    doğuş dağılımı eksene yoğun — additive birikim çekirdeği beyaza doyurur.
  * Renk zinciri: gerçek T_c → izentropik Te (readNozzleExit) → 1/(1+3f)
    soğuma (mevcut model) → akkor rengi (Draper eşiği ~800 K, beyanlı
    parçalı doğrusal çapalar). Keyfî renk yok; Te yoksa beyanlı fallback.
  * Çekirdek koni: çıkış düzleminde r=re, açısı θ_geo + [ν(Mj) − ν(Me)]
    (Prandtl-Meyer — çözücünün gerçek Me, Mj, γ değerlerinden).
  * Şok elmasları koninin yerel yarıçapına hizalı; sürücü |1-pe/pa|
    DEĞİŞMEDİ — adapte lülede zayıf kalması fiziğin kendisidir.
  * Bütçe: +2 mesh (sınır +3), doku 128 px, parçacık bütçesi sabit,
    pixelRatio bekçisi yerinde.

Bu testler saf fonksiyonları node ile izole çalıştırıp sayısal değerlerini
sınar (kalıp: tests/test_viz3d_gorsel_kalite.py). Fizik sürücülerine
(readNozzleExit, _plumeAero) dokunulmadığı da kaynaktan doğrulanır.
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
    """`var AD = ...;` sabit bildirimlerini (tek satir ya da dizi) cikarir."""
    source = _source()
    out = []
    for name in names:
        m = re.search(r'var %s = [^;]+;' % re.escape(name), source)
        assert m, 'sabit bulunamadi: %s' % name
        out.append(m.group(0))
    return '\n'.join(out)


def _run(script):
    result = subprocess.run([NODE], input=script, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr[:800]
    return json.loads(result.stdout)


def _emit(prelude, expr):
    return _run(prelude + '\nprocess.stdout.write(JSON.stringify(%s));\n' % expr)


def _method_body(name):
    """MotorScene.prototype.<name> govdesini kaba metin olarak dondurur."""
    src = _source()
    marker = 'MotorScene.prototype.%s = function' % name
    assert marker in src, '%s yok' % marker
    tail = src.split(marker, 1)[1]
    nxt = tail.find('MotorScene.prototype.')
    return tail if nxt < 0 else tail[:nxt]


# Teşhis senaryosu: hibrit varsayılan tasarım (test_plume_physics.py'deki
# gerçek çözücü çıktısıyla aynı büyüklükler)
RE_MM = 21.6          # çıkış yarıçapı
TC_K = 3307.0         # gerçek oda sıcaklığı
TE_K = 2162.0         # izentropik çıkış statik sıcaklığı (~Tc/1.53)


# ---------------------------------------------------------------------------
# Kalem 1a — sprite dokusu: Gauss profili, tekdüze sönüm, kırpma halkası yok
# ---------------------------------------------------------------------------

class TestSpriteDokusu:

    def _prelude(self):
        return (_consts('FLAME_SPRITE_SIGMA')
                + '\n' + _extract('flameSpriteAlpha')
                + '\n' + _extract('flameSpriteStops'))

    def test_profil_tekduze_azalir(self):
        p = self._prelude()
        alphas = _emit(p, '[0, 0.2, 0.4, 0.6, 0.8, 1.0].map(flameSpriteAlpha)')
        assert alphas[0] == pytest.approx(1.0)
        assert alphas[-1] == 0
        assert all(a > b for a, b in zip(alphas, alphas[1:])), alphas

    def test_gauss_bicimi(self):
        """Profil beyan edilen Gauss'un kendisi: exp(-t²/(2σ²))."""
        p = self._prelude()
        sigma = _emit(_consts('FLAME_SPRITE_SIGMA'), 'FLAME_SPRITE_SIGMA')
        for t in (0.15, 0.5, 0.85):
            a = _emit(p, 'flameSpriteAlpha(%r)' % t)
            assert a == pytest.approx(
                math.exp(-t * t / (2 * sigma * sigma)), rel=1e-9)

    def test_kenarda_kirpma_halkasi_yok(self):
        """Sert kenar 'patlamış mısır' topunun kaynağıydı: kenara doğru
        opaklık görünmezliğe inmeli."""
        p = self._prelude()
        assert _emit(p, 'flameSpriteAlpha(0.95)') < 0.02
        assert _emit(p, 'flameSpriteAlpha(1.0)') == 0

    def test_duraklar_gecerli_ve_profili_izler(self):
        p = self._prelude()
        stops = _emit(p, 'flameSpriteStops(9)')
        ts = [s['t'] for s in stops]
        assert ts[0] == 0 and ts[-1] == 1
        assert ts == sorted(ts) and len(stops) == 9
        for s in stops:
            assert 0 <= s['alpha'] <= 1
        alphas = [s['alpha'] for s in stops]
        assert all(a > b for a, b in zip(alphas, alphas[1:])), alphas

    def test_doku_notr_ve_butcede(self):
        """Doku beyaz alfa rampası (ton vertex renginden — T sürücüsü) ve
        128 px bütçesinde; eski gömülü-turuncu egzoz dokusu gitmiş."""
        body = _extract('flameSpriteTexture')
        assert 'makeCanvas(128, 128)' in body, 'doku bütçesi 128 px değil'
        assert "rgba(255,255,255," in body
        assert '255,150,60' not in body, 'dokuda gömülü keyfi turuncu var'
        src = _source()
        assert "glowTexture('rgba(255,255,255,1)', 'rgba(255,150,60,0.6)')" \
            not in src, 'eski egzoz dokusu geri dönmüş'

    def test_parcacik_malzemesine_baglandi(self):
        """PointsMaterial yumuşak dokuyu kullanıyor ve additive blending
        bayrağı duruyor (kalem 1 sözleşmesi)."""
        body = _method_body('_buildPlume')
        assert 'map: flameSpriteTexture()' in body
        assert 'THREE.AdditiveBlending' in body
        assert 'depthWrite: false' in body


# ---------------------------------------------------------------------------
# Kalem 1b — doğuş dağılımı eksene yoğun, kenarda seyrek
# ---------------------------------------------------------------------------

class TestEksenYogunlugu:

    def _prelude(self):
        return (_consts('PLUME_SPAWN_R_FRACTION', 'PLUME_SPAWN_EXPONENT')
                + '\n' + _extract('plumeSpawnRadius'))

    def test_yaricap_sinirlari(self):
        p = self._prelude()
        assert _emit(p, 'plumeSpawnRadius(%r, 0)' % RE_MM) == 0
        assert _emit(p, 'plumeSpawnRadius(%r, 1)' % RE_MM) == \
            pytest.approx(0.75 * RE_MM)
        rs = _emit(p, '[0, 0.25, 0.5, 0.75, 1].map(function (u) {'
                      'return plumeSpawnRadius(%r, u); })' % RE_MM)
        assert rs == sorted(rs)

    def test_eksene_yogun_kenarda_seyrek(self):
        """Medyan doğuş yarıçapı alanca-eşdağılımın (eski sqrt) medyanından
        küçük olmalı: parçacıkların yarısı eksene daha yakın doğar."""
        p = self._prelude()
        median = _emit(p, 'plumeSpawnRadius(%r, 0.5)' % RE_MM)
        eski_median = 0.75 * RE_MM * math.sqrt(0.5)
        assert median < eski_median, (
            'medyan %.2f >= eski alanca-eşdağılım medyanı %.2f'
            % (median, eski_median))

    def test_us_alanca_esdagilimdan_buyuk(self):
        """Üs 0.5 = eski alanca eşdağılım; eksene yoğunluk için > 0.5 şart."""
        exp = _emit(_consts('PLUME_SPAWN_EXPONENT'), 'PLUME_SPAWN_EXPONENT')
        assert exp > 0.5

    def test_dogus_tek_yoldan(self):
        """Her iki doğuş yolu (ilk kurulum + yeniden doğuş) aynı dağılımı
        kullanır; eski sqrt kopyaları gitmiş."""
        src = _source()
        assert len(re.findall(r'\bplumeSpawnRadius\(', src)) >= 2, (
            'plumeSpawnRadius tanımlı ama sahnede çağrılmıyor')
        assert '0.75 * Math.sqrt(Math.random())' not in src
        assert 're * 0.7 * Math.sqrt' not in src


# ---------------------------------------------------------------------------
# Kalem 2 — renk sürücüsü gerçek sıcaklık: T_c → Te → soğuma → akkor rengi
# ---------------------------------------------------------------------------

class TestRenkSurucusu:

    def _prelude(self):
        return (_consts('FLAME_AMBIENT_K', 'FLAME_COLOR_ANCHORS')
                + '\n' + _extract('flameTempAt')
                + '\n' + _extract('flameColorFromT'))

    def _full(self):
        return self._prelude() + '\n' + _extract('plumeColorAt')

    def test_soguma_mevcut_modelden(self):
        """T(f) mevcut 1/(1+3f) merkez hattı sönümünü izler (Pope §5.1) —
        renk ve parlaklık TEK soğuma modelinden sürülür."""
        p = self._prelude()
        assert _emit(p, 'flameTempAt(0, %r)' % TE_K) == pytest.approx(TE_K)
        assert _emit(p, 'flameTempAt(1, %r)' % TE_K) == \
            pytest.approx(300 + (TE_K - 300) / 4)
        for f in (0.3, 0.7):
            assert _emit(p, 'flameTempAt(%r, %r)' % (f, TE_K)) == \
                pytest.approx(300 + (TE_K - 300) / (1 + 3 * f))

    def test_akkor_sirasi_kizildan_beyaza(self):
        """g/r oranı sıcaklıkla tekdüze artar: kızıl → turuncu → beyaz.
        Bantlar keyfî değil, akkor (Planck) sırasının nicelenmiş hali."""
        p = self._prelude()
        ratios = []
        for t in (1100, 1600, 2100, 2700, 3300):
            c = _emit(p, 'flameColorFromT(%r)' % t)
            ratios.append(c['g'] / c['r'])
        assert all(a < b for a, b in zip(ratios, ratios[1:])), ratios

    def test_draper_altinda_isima_yok(self):
        """~800 K altında görünür ışıma yoktur (Draper noktası) — soğumuş
        parçacık kararak kaybolur, süs rengi almaz."""
        p = self._prelude()
        for t in (700, 300, 0):
            c = _emit(p, 'flameColorFromT(%r)' % t)
            assert c['r'] == 0 and c['g'] == 0 and c['b'] == 0
        c = _emit(p, 'flameColorFromT(NaN)')
        assert c['r'] == 0 and c['g'] == 0 and c['b'] == 0

    def test_sicak_cekirdek_beyaz_soguk_kizil(self):
        p = self._prelude()
        hot = _emit(p, 'flameColorFromT(3400)')
        assert hot['r'] == pytest.approx(1.0)
        assert hot['g'] == pytest.approx(1.0)
        assert hot['b'] >= 1.0                      # eski beyaz-mavi uç korunur
        cold = _emit(p, 'flameColorFromT(1300)')
        assert cold['r'] / cold['g'] >= 3.0, 'soğuk uç kızıl değil'

    def test_renk_gercek_te_ile_degisir(self):
        """Aynı yaş, farklı GERÇEK Te → farklı renk: sürücü sıcaklıktır."""
        p = self._full()
        hot = _emit(p, 'plumeColorAt(0, 1, 2200)')
        cold = _emit(p, 'plumeColorAt(0, 1, 1200)')
        assert hot['g'] / hot['r'] > cold['g'] / cold['r'] * 2, (
            'çekirdek rengi Te ile değişmiyor')

    def test_asagi_akis_gradyani(self):
        """Tek parçacığın ömrü: sıcak çekirdek → turuncu-kızıl → görünmez
        (kalem 2 gradyanı) — hepsi Te sürücüsünden. Gerçek hibrit Te'sinde
        (2162 K) ömür sonu sıcaklığı Draper eşiğinin ALTINA iner: parçacık
        süs rengiyle uzatılmaz, fiziğin dediği gibi söner."""
        p = self._full()
        cs = _emit(p, '[0, 0.4, 0.7, 1].map(function (f) {'
                      'return plumeColorAt(f, 1, %r); })' % TE_K)
        gr = [c['g'] / c['r'] for c in cs[:3]]      # görünür bölge
        assert all(a > b for a, b in zip(gr, gr[1:])), (
            'aşağı akışta kızıla kayma yok: %s' % gr)
        # T(1) = 300 + (2162-300)/4 = 765.5 K < 800 K (Draper) → söner
        assert cs[3]['r'] == 0 and cs[3]['g'] == 0 and cs[3]['b'] == 0
        fades = [c['fade'] for c in cs]
        assert all(a > b for a, b in zip(fades, fades[1:]))

    def test_te_yoksa_beyanli_fallback(self):
        """Te verilmezse (eski kayıt / eksik Tc) eski bant paleti aynen
        sürer — mevcut testlerin sözleşmesi bozulmaz, uydurma Te yok."""
        p = self._full()
        c = _emit(p, 'plumeColorAt(0.1, 1)')
        assert c['r'] / c['g'] == pytest.approx(1.0, rel=0.05)
        c2 = _emit(p, 'plumeColorAt(0.3, 1)')
        assert c2['g'] / c2['r'] == pytest.approx(0.62, rel=1e-6)

    def test_zincir_sahneye_bagli(self):
        """_updatePlume renk çağrısı gerçek exitTemperature'ı geçiriyor;
        Te'nin Tc'den izentropik türetimi (readNozzleExit) yerinde."""
        src = _source()
        assert 'plumeColorAt(f, intensity, info.exitTemperature)' in src
        assert 'tc / (1 + 0.5 * (gamma - 1) * me * me)' in src, (
            'izentropik Te türetimi (gerçek T_c zinciri) kaybolmuş')


# ---------------------------------------------------------------------------
# Kalem 3 — çekirdek koni: açı gerçek çıkış durumundan (Prandtl-Meyer)
# ---------------------------------------------------------------------------

class TestCekirdekKonisi:

    def _prelude(self):
        return (_consts('PLUME_CORE_LEN_DE', 'FLAME_CONE_MIN_R_FRACTION')
                + '\n' + _extract('prandtlMeyerDeg')
                + '\n' + _extract('plumeConeSpec')
                + '\n' + _extract('coneRadiusAt'))

    def test_prandtl_meyer_bilinen_deger(self):
        """ν(2.0, γ=1.4) = 26.38° — gaz dinamiği tablolarındaki değer."""
        p = self._prelude()
        assert _emit(p, 'prandtlMeyerDeg(2.0, 1.4)') == \
            pytest.approx(26.38, abs=0.05)
        assert _emit(p, 'prandtlMeyerDeg(1.0, 1.4)') == 0
        vs = _emit(p, '[1.2, 1.8, 2.5, 3.5].map(function (m) {'
                      'return prandtlMeyerDeg(m, 1.2); })')
        assert vs == sorted(vs) and vs[0] > 0

    def test_koni_cikis_duzleminde_re(self):
        """Süreklilik: koni tabanı TAM çıkış yarıçapında başlar (kalem 3)."""
        p = self._prelude()
        spec = _emit(p, 'plumeConeSpec(%r, 8, 2.5, 2.5, 1.16, 0)' % RE_MM)
        assert spec['r0'] == pytest.approx(RE_MM)

    def test_adapte_lulede_geometrik_aci(self):
        """Mj = Me (pe = pa) → dönüş 0, koni açısı lülenin gerçek açısı."""
        p = self._prelude()
        spec = _emit(p, 'plumeConeSpec(%r, 8, 2.5, 2.5, 1.16, 0)' % RE_MM)
        assert spec['turnDeg'] == 0
        assert spec['halfAngleDeg'] == pytest.approx(8.0)

    def test_az_genislemis_disari_acilir(self):
        """pe > pa → Mj > Me → dudakta Prandtl-Meyer dönüşü DIŞA: koni
        açısı geometrik açıdan büyük."""
        p = self._prelude()
        spec = _emit(p, 'plumeConeSpec(%r, 8, 2.5, 3.0, 1.2, 0)' % RE_MM)
        assert spec['turnDeg'] > 0
        assert spec['halfAngleDeg'] > 8
        assert spec['r1'] > spec['r0']

    def test_asiri_genislemis_buzulur(self):
        """pe < pa → Mj < Me → dönüş negatif: jet sınırı içeri kıvrılır."""
        p = self._prelude()
        spec = _emit(p, 'plumeConeSpec(%r, 8, 2.5, 2.0, 1.2, 0)' % RE_MM)
        assert spec['turnDeg'] < 0
        assert spec['halfAngleDeg'] < 8

    def test_taban_yaricapi_cokmez(self):
        """Uç aşırı genişlemede bile görsel taban: r1 >= 0.3·re (beyanlı
        görsel emniyet, fizik iddiası değil)."""
        p = self._prelude()
        spec = _emit(p, 'plumeConeSpec(%r, 2, 3.0, 1.05, 1.4, 0)' % RE_MM)
        assert spec['r1'] >= 0.3 * RE_MM - 1e-9

    def test_boy_butceyle_sinirli(self):
        p = self._prelude()
        free = _emit(p, 'plumeConeSpec(%r, 8, 2.5, 2.5, 1.16, 0)' % RE_MM)
        assert free['lengthMm'] == pytest.approx(8 * 2 * RE_MM)
        capped = _emit(p, 'plumeConeSpec(%r, 8, 2.5, 2.5, 1.16, 100)' % RE_MM)
        assert capped['lengthMm'] == pytest.approx(100)

    def test_gecersiz_girdide_null(self):
        p = self._prelude()
        assert _emit(p, 'plumeConeSpec(0, 8, 2.5, 2.5, 1.16, 0)') is None
        assert _emit(p, 'plumeConeSpec(%r, NaN, 2.5, 2.5, 1.16, 0)'
                     % RE_MM) is None

    def test_koni_sahnede_gercek_degerlerle(self):
        """Koni kurulumu çözücünün gerçek Me/Mj/γ değerleriyle çağrılır ve
        çıkış durumu yoksa HİÇ kurulmaz (sahte veri yasağı)."""
        body = _method_body('_rebuildFlameCone')
        assert 'ex.exitMach' in body and 'ex.jetMach' in body
        assert 'ex.gamma' in body
        assert re.search(r'if \(!ex \|\| !this\._plumeInfo\) return;', body), (
            'veri-yok bekçisi kaldırılmış — koni uydurma veriyle kurulabilir')

    def test_additive_yari_saydam_katman(self):
        body = _method_body('_rebuildFlameCone')
        assert 'THREE.AdditiveBlending' in body
        assert 'transparent: true' in body
        assert 'depthWrite: false' in body

    def test_koni_rengi_te_surucusunden(self):
        body = _method_body('_rebuildFlameCone')
        assert 'flameColorFromT(ex.exitTemperature)' in body, (
            'koni rengi gerçek Te sürücüsüne bağlı değil')


# ---------------------------------------------------------------------------
# Kalem 4 — şok elmasları koni katmanıyla hizalı; sürücü |1-pe/pa| değişmedi
# ---------------------------------------------------------------------------

class TestSokElmasiHizasi:

    def test_yerel_yaricap_dogrusal(self):
        p = (_consts('PLUME_CORE_LEN_DE', 'FLAME_CONE_MIN_R_FRACTION')
             + '\n' + _extract('prandtlMeyerDeg')
             + '\n' + _extract('plumeConeSpec')
             + '\n' + _extract('coneRadiusAt'))
        spec = '{ r0: 10, r1: 20, lengthMm: 100 }'
        assert _emit(p, 'coneRadiusAt(%s, 0)' % spec) == pytest.approx(10)
        assert _emit(p, 'coneRadiusAt(%s, 50)' % spec) == pytest.approx(15)
        assert _emit(p, 'coneRadiusAt(%s, 100)' % spec) == pytest.approx(20)
        assert _emit(p, 'coneRadiusAt(%s, 250)' % spec) == pytest.approx(20)
        assert _emit(p, 'coneRadiusAt(null, 50)') is None

    def test_elmas_olcegi_koniye_hizali(self):
        body = _method_body('_updateDiamondPositions')
        assert 'coneRadiusAt(this._coneSpec' in body, (
            'elmas ölçeği koni katmanına hizalanmamış')
        src = _source()
        assert 'd.re * (1.5 - k * 0.18)' not in src, (
            'koniden bağımsız eski elmas ölçeği geri dönmüş')

    def test_fizik_surucusu_degismedi(self):
        """Aralık Prandtl-Pack'ten, şiddet |1-pe/pa| aktarımından gelmeye
        devam eder; adapte lülede zayıflık fiziğin kendisi (belgeli)."""
        src = _source()
        assert 'diamondStrength: diamondVisibility(ex.pressureRatio)' in src
        assert 'diamondSpacing: ex.cellSpacingMm' in src
        prelude = (_consts('DIAMOND_VIS_EXPONENT')
                   + '\n' + _extract('diamondVisibility'))
        assert _emit(prelude, 'diamondVisibility(1.0)') == 0   # pe=pa: hücre yok


# ---------------------------------------------------------------------------
# Kalem 5 — bütçe ve regresyon bekçileri
# ---------------------------------------------------------------------------

class TestButceVeRegresyon:

    def test_js_sozdizimi(self):
        res = subprocess.run([NODE, '--check', str(VIZ_JS)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, res.stderr

    def test_draw_call_artisi_sinirda(self):
        """Alev katmanı en fazla +3 mesh ekleyebilir (kalem 5). addCone
        çağrısı sayılır (tanım hariç)."""
        body = _method_body('_rebuildFlameCone')
        calls = body.count('addCone(') - body.count('function addCone(')
        assert 1 <= calls <= 3, 'koni katmanı %d mesh ekliyor' % calls

    def test_parcacik_butcesi_artmadi(self):
        """Parçacık yoğunluğu ve doku bütçesi aşılmadı: estetik düzeltme
        performans bütçesinden çalmaz."""
        per_unit = _emit(_consts('PLUME_PARTICLES_PER_UNIT'),
                         'PLUME_PARTICLES_PER_UNIT')
        assert per_unit <= 750
        len_per = _emit(_consts('PLUME_LEN_PER_MOTOR'), 'PLUME_LEN_PER_MOTOR')
        assert len_per <= 1.2

    def test_pixel_ratio_bekcisi_bozulmadi(self):
        src = _source()
        assert 'setPixelRatio(perf ? 1 : Math.min(window.devicePixelRatio || 1, 2))' \
            in src, 'perf modu pixelRatio düşürme bekçisi kaldırılmış'
        assert re.search(r"AUTO_PERF_DT_LIMIT\s*=\s*0\.028", src)

    def test_gorunurluk_sozlesmesi(self):
        """Koni katmanı parçacıklarla aynı sözleşmeyi izler: veri yoksa ve
        yanma yokken görünmez."""
        src = _source()
        assert 'this._flameGroup.visible = false' in src        # veri yok
        assert 'this._flameGroup.visible = this._plume.visible' in src

    def test_nrib_yok(self):
        assert 'nRib' not in _source(), (
            "sahte 8 bilezik geri gelmiş: kaynakta 'nRib' var")

    @pytest.mark.parametrize('name', [
        'flameSpriteAlpha', 'flameSpriteStops', 'flameSpriteTexture',
        'plumeSpawnRadius', 'flameTempAt', 'flameColorFromT',
        'prandtlMeyerDeg', 'plumeConeSpec', 'coneRadiusAt',
    ])
    def test_fonksiyon_tanimli_ve_kullaniliyor(self, name):
        src = _source()
        assert len(re.findall(r'\b%s\(' % name, src)) >= 2, (
            '%s tanımlı ama sahnede hiç çağrılmıyor (ölü düzeltme)' % name)

    def test_yeniden_kurulumda_dispose(self):
        """update() yolunda koni katmanı sızıntısız yeniden kurulur."""
        body = _method_body('_rebuildFlameCone')
        assert 'geometry.dispose()' in body
        assert 'material.dispose()' in body
        upd = _method_body('update')
        assert '_rebuildFlameCone()' in upd, (
            'tasarım güncellemesi koniyi bayat çıkış durumuyla bırakıyor')
