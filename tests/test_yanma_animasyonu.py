"""Katı tane yanma animasyonu GERÇEK çözücü verisiyle sürülür (v2.6.27, B5).

Kapattığı kusur (ölçüldü 2026-08-15, HEAD 09f8ca9):

  3B sahnedeki port gerilemesi katı motorda TAMAMEN uydurmaydı. İki parça
  birlikte çalışıyordu:

    1. ``motor_viz3d.js/portRadiusAt``  — çözücü serisi yoksa portu
       ``sqrt(lerp(r0^2, rF^2, t/t_b))`` ile ilerletiyordu. Ne zaman yasası
       (sabit hacimsel üretim varsayımı) ne de bitiş yarıçapı hesaptan
       geliyordu.
    2. ``solid.html/buildSolidVizData`` — o bitiş yarıçapını ÜRETİYORDU:
       ``portFinalM = grainOuterDiaM * 0.9`` ("yanma sonunda ince bir grain
       kabuğu görünsün diye 0.95 değil 0.9" yorumuyla).

  Yani kullanıcı, kendi tasarımının yanışını izlediğini sanarken ekranda
  hiçbir hesaba bağlı olmayan bir animasyon dönüyordu.

GERÇEK KAYNAK — İKİ KATMAN (ikincisi parti 26'da eklendi).

  * ASIL: çözücü artık ``thrust_curve.port_area`` (m²) yayımlıyor
    (``_published_thrust_curve``, parti 26). Dairesel portta eşdeğer
    yarıçap TÜRETMESİZ okunur: r(t) = sqrt(A_port(t)/π). Kip
    ``solid_port_area``.

  * YEDEK: alan taşımayan yanıtlarda (parti 26 öncesi kaydedilmiş sonuç
    dosyaları, bayat istemci) aşağıdaki türetme AYNEN çalışmaya devam
    eder — kip ``solid_mass_balance``. Bu dosyadaki eski bekçilerin
    tamamı o yolu kilitlemeye devam ediyor.

Yedek yolun dayanağı, çözücünün KENDİ kütle üretim özdeşliğinin tersidir:

    m_dot(t) = rho_p * A_b(t) * r_b(t)     (solid_rocket_engine.py:8420)
 -> r_b(t)   = m_dot(t) / (rho_p * A_b(t))
 -> w(t)     = integral r_b dt             (trapez)

Üç dizinin üçü de çözücü çıktısıdır ve erozif yanma artışı m_dot'un içinde
zaten vardır. Bu testin çekirdeği, türetmenin çözücüyle ÖZDEŞ olduğunu
kanıtlayan iki bağımsız ölçüttür:

  * w(t_son) ile çözücünün beyan ettiği ``web_burnout_mm`` örtüşür,
  * türetilen w ile BATES yanma alanı geri kurulunca çözücünün YAYIMLADIĞI
    ``burn_area`` dizisi çıkar.

Ölçüt her testte aynı: ANİMASYON GERÇEK SERİDEN GELİYOR MU, seri yokken
SUSUYOR MU.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
SOLID_HTML = ROOT / 'hrma/templates/solid.html'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadi')


# ----------------------------------------------------------------------
# JS izole çalıştırma altyapısı (test_plume_physics.py deseni)
# ----------------------------------------------------------------------

def _source():
    return VIZ_JS.read_text(encoding='utf-8')


def _extract(func_name, source=None):
    """motor_viz3d.js icinden tek bir fonksiyonu izole cikarir."""
    source = source if source is not None else _source()
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


def _const_block(name, source=None):
    source = source if source is not None else _source()
    m = re.search(r'var %s = \{.*?\};' % name, source, re.S)
    assert m, '%s bulunamadi' % name
    return m.group(0)


def _prelude():
    src = _source()
    return '\n'.join([
        'function lerp(a,b,t){return a+(b-a)*t;}',
        'function clamp(v,lo,hi){return Math.min(hi,Math.max(lo,v));}',
        _extract('num', src),
        _extract('sampleSeries', src),
        _const_block('RADIAL_REGRESSION_GRAINS', src),
        _extract('solidPortRadiusHistory', src),
        _extract('solidWebHistory', src),
        _extract('portRegressionMode', src),
        _extract('portRadiusAt', src),
        _extract('burnedWebAt', src),
    ])


def _run(body):
    """Prelude + verilen govdeyi node ile kosturur, JSON sonucu doner."""
    script = _prelude() + '\n' + body
    out = subprocess.run([NODE, '-e', script], capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr[:800]
    return json.loads(out.stdout)


# ----------------------------------------------------------------------
# Gerçek çözücü koşusu (öğretici varsayılanları — BATES, APCP)
# ----------------------------------------------------------------------

@pytest.fixture(scope='module')
def katilar():
    from hrma.app import app
    client = app.test_client()
    cevap = client.post('/calculate_solid', json={'use_tutorial_defaults': True})
    assert cevap.status_code == 200, cevap.status_code
    sonuc = cevap.get_json()
    assert isinstance(sonuc, dict) and 'error' not in sonuc, str(sonuc)[:400]
    return sonuc


@pytest.fixture(scope='module')
def viz_verisi(katilar):
    """solid.html/buildSolidVizData'nin animasyon icin gecirdigi alanlar."""
    return {
        'grain_design': katilar['grain_design'],
        'thrust_curve': katilar['thrust_curve'],
        'propellant_density': katilar['density'],
        'port_diameter_initial': katilar['core_diameter'] / 1000.0,
        'burn_time': katilar['burn_time'],
    }


def _dims(gd):
    return {
        'rPort0': gd['inner_diameter_mm'] / 2.0,
        'rGrainOut': gd['outer_diameter_mm'] / 2.0,
        'portHist': None,
        'burnTime': None,
    }


# ----------------------------------------------------------------------
# 1. Veri sözleşmesi: çözücü türetmenin girdilerini gerçekten yayımlıyor
# ----------------------------------------------------------------------

class TestCozucuVeriSozlesmesi:

    def test_animasyonun_bir_gercek_kaynagi_var(self, katilar):
        """Ya port gecmisi yayimlanir ya da turetmenin UC girdisi tam olur.

        Ikisi de yoksa animasyon dururdu — bu testin isi o sessiz kaybi
        yakalamak (cozucu ileride port_history yayimlarsa test yine yesil).
        """
        if katilar.get('port_history'):
            ph = katilar['port_history']
            assert ph.get('time') and ph.get('port_diameter')
            return
        tc = katilar['thrust_curve']
        for alan in ('time', 'burn_area', 'mass_flow'):
            assert isinstance(tc.get(alan), list) and len(tc[alan]) >= 3, alan
        assert len(tc['time']) == len(tc['burn_area']) == len(tc['mass_flow'])
        assert katilar['density'] > 0

    def test_tane_kimligi_yayimlaniyor(self, katilar):
        """Kip karari icin gereken tane tipi ve olculer beyanli."""
        gd = katilar['grain_design']
        assert gd['grain_type'] == 'bates'
        assert gd['inner_diameter_mm'] > 0
        assert gd['outer_diameter_mm'] > gd['inner_diameter_mm']
        assert gd['web_burnout_mm'] > 0

    def test_burn_area_dizisi_sifir_gecmiyor(self, katilar):
        """r_b = mdot/(rho*A_b) ozdesliginin tanimli oldugu gosterilir."""
        assert all(a > 0 for a in katilar['thrust_curve']['burn_area'][:-1])


# ----------------------------------------------------------------------
# 2. Türetme çözücünün KENDİ webi mi? (iki bağımsız kanıt)
# ----------------------------------------------------------------------

class TestTuretmeCozucuyleOzdes:

    def test_web_sonu_cozucunun_beyaniyla_ortusuyor(self, viz_verisi):
        """w(t_son) ~ web_burnout_mm.

        Kalan pay yayimlanan dizinin seyreltmesinden gelir (487 -> 402);
        %0,5 esigi o sayisal payi birakir, uydurma bir egriyi birakmaz.
        """
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            'const wh = solidWebHistory(md);\n'
            'process.stdout.write(JSON.stringify({var: !!wh, '
            'kaynak: wh && wh.source, webEndMm: wh && wh.webEnd * 1000, '
            'n: wh && wh.time.length}));'
        )
        assert cikti['var'], 'gercek seriden web gecmisi kurulamadi'
        assert cikti['kaynak'] == 'solid_mass_balance'
        beyan = viz_verisi['grain_design']['web_burnout_mm']
        assert cikti['webEndMm'] == pytest.approx(beyan, rel=0.005), (
            'turetilen web (%.4f mm) cozucunun beyan ettigi web_burnout_mm '
            '(%.4f) ile ortusmuyor' % (cikti['webEndMm'], beyan))

    def test_web_monoton_artiyor(self, viz_verisi):
        cikti = _run(
            'const wh = solidWebHistory(%s);\n' % json.dumps(viz_verisi) +
            'let mono = true;\n'
            'for (let i = 1; i < wh.web.length; i++) '
            '{ if (wh.web[i] < wh.web[i-1]) mono = false; }\n'
            'process.stdout.write(JSON.stringify({mono: mono, ilk: wh.web[0]}));'
        )
        assert cikti['mono'], 'web geriye gidiyor'
        assert cikti['ilk'] == 0.0

    def test_yanma_alani_geri_kuruluyor(self, katilar, viz_verisi):
        """Capraz kanit: turetilen w ile BATES yanma alani hesaplanirsa
        cozucunun YAYIMLADIGI burn_area dizisi cikar.

        A_b(w) = N * 2pi * [ (r0+w)(Ls-2w) + (R^2 - (r0+w)^2) ]
        (dis yuzey inhibe, uclar yaniyor — cozucunun kendi modeli.)
        Bu ortusme, turetilen w'nin cozucunun kendi webi oldugunu gosterir:
        bagimsiz bir egri bu kadar yakin gecemez.
        """
        cikti = _run(
            'const wh = solidWebHistory(%s);\n' % json.dumps(viz_verisi) +
            'process.stdout.write(JSON.stringify(wh.web));'
        )
        gd = katilar['grain_design']
        tc = katilar['thrust_curve']
        n = gd['number_of_segments']
        rr = gd['outer_diameter_mm'] / 2000.0
        r0 = gd['inner_diameter_mm'] / 2000.0
        ls = gd['segment_length_mm'] / 1000.0
        hatalar = []
        for w, yayimlanan in zip(cikti, tc['burn_area']):
            r = r0 + w
            ab = n * (2 * math.pi * r * max(ls - 2 * w, 0.0)
                      + 2 * math.pi * max(rr * rr - r * r, 0.0))
            hatalar.append(abs(ab - yayimlanan) / yayimlanan)
        ort = sum(hatalar) / len(hatalar)
        assert ort < 0.002, 'ortalama sapma %%%.3f' % (100 * ort)
        assert max(hatalar) < 0.01, 'en buyuk sapma %%%.3f' % (100 * max(hatalar))


# ----------------------------------------------------------------------
# 3. Animasyon gerçekten geriliyor (ve gerçek değerlerle)
# ----------------------------------------------------------------------

class TestPortGerilemesi:

    def test_port_baslangictan_web_kadar_buyuyor(self, katilar, viz_verisi):
        gd = katilar['grain_design']
        tb = katilar['burn_time']
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            'const dims = %s;\n' % json.dumps(_dims(gd)) +
            'dims.webHist = solidWebHistory(md);\n'
            'const mode = portRegressionMode({portShape: "circular", '
            'grainType: md.grain_design.grain_type, hasPortHistory: false, '
            'hasWebHistory: !!dims.webHist});\n'
            'const ts = [0, 0.25, 0.5, 0.75, 1].map(f => f * %r);\n' % tb +
            'process.stdout.write(JSON.stringify({mode: mode, '
            'r: ts.map(t => portRadiusAt(dims, t, mode)), '
            'w: ts.map(t => burnedWebAt(dims, t, mode))}));'
        )
        assert cikti['mode'] == 'solid_mass_balance'
        yaricaplar = cikti['r']
        assert yaricaplar[0] == pytest.approx(gd['inner_diameter_mm'] / 2.0)
        for onceki, simdiki in zip(yaricaplar, yaricaplar[1:]):
            assert simdiki > onceki, 'port gerilemesi durdu: %r' % (yaricaplar,)
        # Yanan web etiketi de gercek: sifirdan cozucunun webine gider
        assert cikti['w'][0] == pytest.approx(0.0, abs=1e-9)
        assert cikti['w'][-1] == pytest.approx(gd['web_burnout_mm'], rel=0.005)

    def test_gerileme_dogrusal_degil(self, katilar, viz_verisi):
        """Regresif BATES: yanma hizi Pc dustukce yavaslar.

        Uydurma sqrt yasasi ya da dogrusal ara deger bu testi gecemez —
        gercek seride ilk yarinin ilerlemesi ikinci yarininkinden buyuktur.
        """
        tb = katilar['burn_time']
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            'const dims = %s;\n' % json.dumps(_dims(katilar['grain_design'])) +
            'dims.webHist = solidWebHistory(md);\n'
            'const f = t => burnedWebAt(dims, t, "solid_mass_balance");\n'
            'process.stdout.write(JSON.stringify('
            '[f(0), f(%r), f(%r)]));' % (0.5 * tb, tb)
        )
        ilk_yari = cikti[1] - cikti[0]
        ikinci_yari = cikti[2] - cikti[1]
        assert ilk_yari > ikinci_yari * 1.05, (
            'gerileme dogrusal gorunuyor (%.3f / %.3f mm) — gercek seri '
            'yerine duz ara deger mi kullaniliyor?' % (ilk_yari, ikinci_yari))


# ----------------------------------------------------------------------
# 4. Sahte veri yasağı: eksik/bozuk veride seri UYDURULMAZ
# ----------------------------------------------------------------------

class TestSahteVeriYasagi:

    @pytest.mark.parametrize('bozma,aciklama', [
        ('delete md.propellant_density', 'yogunluk yok'),
        ('delete md.thrust_curve', 'egri yok'),
        ('md.thrust_curve.mass_flow = null', 'kutle debisi yok'),
        ('md.thrust_curve.burn_area = md.thrust_curve.burn_area.slice(0, 5)',
         'dizi boylari tutmuyor'),
        ('md.thrust_curve.time = md.thrust_curve.time.slice().reverse()',
         'zaman sirali degil'),
        ('md.thrust_curve.mass_flow = md.thrust_curve.mass_flow.map(() => 0)',
         'hic kutle uretimi yok'),
    ])
    def test_eksik_veride_null_doner(self, viz_verisi, bozma, aciklama):
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            '%s;\n' % bozma +
            'process.stdout.write(JSON.stringify(solidWebHistory(md)));'
        )
        assert cikti is None, '%s — yine de seri uretildi' % aciklama

    def test_veri_yoksa_port_donuk(self, katilar):
        """no_data kipinde port baslangic yaricapinda KALIR."""
        cikti = _run(
            'const dims = %s;\n' % json.dumps(_dims(katilar['grain_design'])) +
            'dims.webHist = null;\n'
            'const mode = portRegressionMode({portShape: "circular", '
            'grainType: "bates", hasPortHistory: false, hasWebHistory: false});\n'
            'process.stdout.write(JSON.stringify({mode: mode, '
            'r: [0, 1, 5, 50].map(t => portRadiusAt(dims, t, mode)), '
            'w: burnedWebAt(dims, 5, mode)}));'
        )
        assert cikti['mode'] == 'no_data'
        r0 = katilar['grain_design']['inner_diameter_mm'] / 2.0
        assert cikti['r'] == [r0, r0, r0, r0]
        assert cikti['w'] is None, 'veri yokken web sayisi uretildi'

    @pytest.mark.parametrize('sekil,tane', [
        ('star', 'star'),
        ('multiport', 'wagon_wheel'),
        ('finocyl', 'finocyl'),
        ('circular', 'end_burner'),
        # Guverte 'Port' dugmesi kesiti CANLI degistirir (cyclePortShape):
        # BATES tanesi yildiz kesitle izlenirken radyal buyume, ekranda
        # cozulmemis bir geometrinin gerilemesini gostermek olur.
        ('star', 'bates'),
        ('finocyl', 'bates'),
        ('multiport', 'bates'),
    ])
    def test_dairesel_olmayan_gerileme_modellenmez(self, katilar, sekil, tane):
        """Yildiz/finocyl'de gerileme yuzey normali boyunca ofsettir, uc
        yanmali tanede EKSENELDIR. Ikisini de tek yaricapi buyuterek
        gostermek uydurma olur -> kip not_modelled, port donuk.
        """
        cikti = _run(
            'const dims = %s;\n' % json.dumps(_dims(katilar['grain_design'])) +
            'dims.webHist = {time: [0, 1, 2], web: [0, 0.01, 0.02]};\n'
            'const mode = portRegressionMode({portShape: %r, grainType: %r, '
            'hasPortHistory: false, hasWebHistory: true});\n' % (sekil, tane) +
            'process.stdout.write(JSON.stringify({mode: mode, '
            'r: [0, 2].map(t => portRadiusAt(dims, t, mode))}));'
        )
        assert cikti['mode'] == 'not_modelled'
        assert cikti['r'][0] == cikti['r'][1], 'modellenmemis kesit animasyonlu'

    def test_hibrit_port_gecmisi_yolu_korundu(self, katilar):
        """Cozucu yaricapi KENDISI verdiginde (hibrit) o kullanilir."""
        cikti = _run(
            'const dims = %s;\n' % json.dumps(_dims(katilar['grain_design'])) +
            'dims.portHist = {time: [0, 5, 10], '
            'port_diameter: [0.030, 0.060, 0.080]};\n'
            'const mode = portRegressionMode({portShape: "circular", '
            'grainType: "", hasPortHistory: true, hasWebHistory: false});\n'
            'process.stdout.write(JSON.stringify({mode: mode, '
            'r: [0, 5, 10].map(t => portRadiusAt(dims, t, mode))}));'
        )
        assert cikti['mode'] == 'port_history'
        assert cikti['r'] == pytest.approx([15.0, 30.0, 40.0])


# ----------------------------------------------------------------------
# 5. Sökülen uydurma yasa geri gelmesin (kaynak sözleşmesi)
# ----------------------------------------------------------------------

class TestUydurmaYasaGeriGelmesin:

    def test_port_yaricapi_fonksiyonunda_ara_deger_yok(self):
        govde = _extract('portRadiusAt')
        assert 'rPortF' not in govde, (
            'uydurma bitis yaricapi (rPortF) portRadiusAt icine geri gelmis')
        assert 'Math.sqrt' not in govde, (
            'sabit hacimsel uretim varsayimi (sqrt ara degeri) geri gelmis')
        assert 'lerp(' not in govde, 'zaman ara degeri geri gelmis'

    def test_dims_sozlugunde_bitis_yaricapi_yok(self):
        src = _source()
        assert not re.search(r'\brPortF\s*[:=]', src), (
            'rPortF alani geri gelmis — tek kullanicisi uydurma yasaydi')

    def test_solid_sayfasi_bitis_capini_uretmiyor(self):
        html = SOLID_HTML.read_text(encoding='utf-8')
        assert 'portFinalM' not in html, (
            'solid.html yine bir bitis port capi uretiyor')
        assert not re.search(r'port_diameter_final\s*:', html), (
            'solid.html hesaptan gelmeyen port_diameter_final geciriyor')

    def test_solid_sayfasi_gercek_seriyi_geciriyor(self):
        html = SOLID_HTML.read_text(encoding='utf-8')
        assert re.search(r'thrust_curve\s*:\s*r\.thrust_curve', html), (
            'solid.html animasyonun veri yolunu (thrust_curve) gecirmiyor')
        assert re.search(r'propellant_density\s*:\s*firstNum\(r\.density\)', html), (
            'solid.html yakit yogunlugunu gecirmiyor — turetme calismaz')

    def test_turetme_ozdesligi_kaynakta_beyanli(self):
        """Kod, sayinin nereden geldigini SOYLEMEK zorunda.

        Turetmenin dayanagi (cozucunun kutle uretim ozdesligi) ve o
        ozdesligin dosya adresi yorumda durur; yoksa bir sonraki okuyucu
        bunu "bir yerden gelen formul" sanir.
        """
        src = _source()
        bas = src.index('// Tane yanma animasyonu — port gerilemesi')
        son = src.index('function portRegressionMode(')
        blok = src[bas:son]
        assert 'solid_rocket_engine.py' in blok, 'ozdesligin adresi yazilmamis'
        assert 'ρ_p' in blok, 'kutle dengesi ozdesligi yazilmamis'
        assert 'web_burnout_mm' in blok, 'dogrulama capasi yazilmamis'


# ----------------------------------------------------------------------
# 6. Beyan çipleri: kaynak-renk sözleşmesi + i18n
# ----------------------------------------------------------------------

class TestBeyanCipleri:

    def _chip_defs(self, mode, ends_burn=False):
        src = _source()
        script = '\n'.join([
            'global.window = {};',
            _extract('T', src),
            _extract('portRegressionChipDefs', src),
            'process.stdout.write(JSON.stringify('
            'portRegressionChipDefs(%r, {endsBurn: %s})));'
            % (mode, 'true' if ends_burn else 'false'),
        ])
        out = subprocess.run([NODE, '-e', script], capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr[:600]
        return json.loads(out.stdout)

    @pytest.mark.parametrize('mode,kind', [
        ('port_history', 'computed'),
        ('solid_port_area', 'computed'),
        ('solid_mass_balance', 'computed'),
        ('not_modelled', 'missing'),
        ('no_data', 'missing'),
    ])
    def test_cip_rengi_kaynagi_beyan_eder(self, mode, kind):
        """SOURCE_COLORS sozlesmesi: hesaplanan camgobegi, modellenmemis gri."""
        defs = self._chip_defs(mode)
        assert defs[0]['kind'] == kind
        renkler = _const_block('SOURCE_COLORS')
        assert "'%s'" % kind in renkler or '%s:' % kind in renkler

    def test_her_kip_bir_cip_uretir(self):
        for mode in ('port_history', 'solid_port_area', 'solid_mass_balance',
                     'not_modelled', 'no_data'):
            defs = self._chip_defs(mode)
            assert defs and defs[0]['text'].strip(), mode

    def test_uc_yuzey_sinirlamasi_beyan_edilir(self):
        """Uclar yaniyorsa (cozucu beyani) 3B blok eksenel kisalmayi
        GOSTERMEZ; bu sessiz kalmaz, ayri bir 'missing' cip soyler."""
        for mode in ('solid_mass_balance', 'solid_port_area'):
            defs = self._chip_defs(mode, ends_burn=True)
            assert len(defs) == 2, mode
            assert defs[1]['kind'] == 'missing'
            assert 'end-face' in defs[1]['text']
        # Animasyon zaten yokken ikinci cip eklenmez (gurultu yapmaz)
        assert len(self._chip_defs('no_data', ends_burn=True)) == 1

    def test_cip_metinleri_i18n_koprusunden_gecer(self):
        govde = _extract('portRegressionChipDefs')
        anahtarlar = re.findall(r"T\('([^']+)',\s*\n?\s*'([^']+)'\)", govde)
        assert len(anahtarlar) == 6, (
            'cip metinlerinden bazilari T() koprusunu atliyor: %r' % (anahtarlar,))
        assert 'viz.chip.portRegPortArea' in dict(anahtarlar), (
            'yeni kaynak (yayimlanan port alani) icin cip anahtari yok')
        for anahtar, yedek in anahtarlar:
            assert anahtar.startswith('viz.chip.'), anahtar
            assert yedek.isascii(), (
                'ingilizce yedek metin ascii degil: %r' % yedek)
            assert yedek.strip() == yedek and len(yedek) > 8, yedek

    def test_i18n_koprusu_sozluk_yokken_ingilizce_doner(self):
        src = _source()
        out = subprocess.run(
            [NODE, '-e', 'global.window = {};\n' + _extract('T', src) +
             '\nprocess.stdout.write(T("viz.chip.yok", "english fallback"));'],
            capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr[:400]
        assert out.stdout == 'english fallback'

    def test_dil_degisiminde_cipler_tazelenir(self):
        """Canvas sprite metnine i18n.js'in translateTree'si ulasamaz."""
        src = _source()
        assert "addEventListener('hrma:langchange'" in src
        assert "removeEventListener('hrma:langchange'" in src, (
            'dinleyici dispose edilmiyor — sizinti')
        assert '_refreshStatusChips' in src

    def test_kip_degisiminde_cipler_tazelenir(self):
        """Port kesiti degisince kip de degisebilir; beyan bayat kalmamali."""
        src = _source()
        govde = src[src.index('MotorScene.prototype.setPortShape'):
                    src.index('MotorScene.prototype.cyclePortShape')]
        assert '_resolvePortRegression' in govde
        assert '_refreshStatusChips' in govde


# ----------------------------------------------------------------------
# 6b. Beyan çipi GÖRÜNÜR olmalı (okunamayan beyan beyan değildir)
# ----------------------------------------------------------------------

class TestCipGorunurlugu:
    """Olculen kusur (2026-08-15, canli tarayici, /solid):

    Cipler izgara acikligi koseSine (+-0,42 * 2200 mm) konuyordu; kamera ise
    MOTORU (732 mm) cerceveliyor. Uc cipin de izdusumu NDC x = -2,05...-2,34
    cikti (gorunur sinir +-1) — yani sahte-veri yasaginin butun 'veri yok'
    beyanlari ekranda hic gorunmuyordu. Capa motor boyuna baglandi.
    """

    def _emit(self, ifade):
        src = _source()
        script = '\n'.join([
            _extract('labelScaleBase', src),
            _extract('chipAnchorMm', src),
            _extract('chipHeightMm', src),
            'process.stdout.write(JSON.stringify(%s));' % ifade,
        ])
        out = subprocess.run([NODE, '-e', script], capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr[:600]
        return json.loads(out.stdout)

    def test_capa_motor_boyundan_turer(self):
        """Izgara acikligina degil motor boyuna baglidir; model kutusunun
        icinde kalir ki kamera cercevesinden cikmasin."""
        for boy in (200.0, 732.5, 3000.0):
            capa = self._emit('chipAnchorMm(%r)' % boy)
            assert 0 < capa < boy / 2, (boy, capa)
        assert 'chipAnchorMm(this._totalLen' in _source(), (
            'capa yine izgara acikligina baglanmis')

    def test_cip_boyu_olcu_rozetiyle_ayni_olcekte(self):
        """66 mm'lik izgara-hucresi boyu geri gelmesin: uzun metinli cip
        o boyda ~530 mm genisleyip kadrajdan tasiyordu."""
        boy, cap = 732.5, 109.0
        yukseklik = self._emit('chipHeightMm(%r, %r)' % (boy, cap))
        beklenen = min(boy * 0.055, cap * 0.8) * 0.62
        assert yukseklik == pytest.approx(beklenen)
        assert yukseklik < 30.0, 'cip rozeti yine devasa'

    def test_cipler_ortak_merkezde_yigilir(self):
        """Cip basina x kaydirmak, zemin perspektifte uzaklastigi icin
        yigini ekranda karistiriyordu (dar cip genisin ustune biniyordu)."""
        src = _source()
        govde = src[src.index('MotorScene.prototype._buildStatusChips'):]
        govde = govde[:govde.index('MotorScene.prototype._rebuildGrain')]
        assert 'maxW' in govde, 'ortak merkez hesabi kaldirilmis'
        assert govde.count('position.set(') == 1, (
            'cip konumu birden fazla yerde kuruluyor')


# ----------------------------------------------------------------------
# 7. HUD: sahnenin yayinladigi sayilar gercek
# ----------------------------------------------------------------------

class TestHudYayini:

    def test_tick_gercek_web_ve_kaynagi_yayinlar(self):
        src = _source()
        tick = src[src.index('MotorScene.prototype._tick'):]
        tick = tick[:tick.index('MotorScene.prototype.setCutaway')]
        assert 'webBurnedMm: burnedWebAt(' in tick, (
            'HUD yanan web kalinligini gercek seriden almiyor')
        assert 'portRegression: this._portRegMode' in tick, (
            'HUD gerilemenin kaynagini beyan etmiyor')
        assert 'portRadiusAt(d, st.time, this._portRegMode)' in tick, (
            'port yaricapi kipten bagimsiz hesaplaniyor')


# ----------------------------------------------------------------------
# 8. ASIL KAYNAK — çözücünün YAYIMLADIĞI port akış kesiti (parti 26)
# ----------------------------------------------------------------------
#
# Kapanan borç (bulgu defteri): çözücü ``port_area`` dizisini zaman
# marşında üretiyor ama ``_published_thrust_curve`` dışarı vermiyordu;
# animasyon bu yüzden webi kütle dengesinden GERİ TÜRETMEK zorundaydı.
# Alan yayımlandı; animasyon artık türetmesiz yolu kullanır, alan yoksa
# (eski/bayat yanıt) türetme YEDEK olarak yerinde durur.


@pytest.fixture(scope='module')
def viz_verisi_eski(viz_verisi):
    """Parti 26 ÖNCESİ yanıtın taklidi: thrust_curve'de port_area yok.

    (Test altyapısı — kullanıcıya gösterilen veri değil; amaç eski sonuç
    dosyalarının kırılmadığını ÖLÇMEK.)
    """
    egri = {k: v for k, v in viz_verisi['thrust_curve'].items()
            if k not in ('port_area', 'port_area_basis')}
    return dict(viz_verisi, thrust_curve=egri)


class TestPortAlaniSozlesmesi:
    """Yayımlanan alanın kendisi: hizalı, künyeli, çizilen portla tutarlı."""

    def test_port_alani_yayimlaniyor(self, katilar):
        tc = katilar['thrust_curve']
        assert isinstance(tc.get('port_area'), list), (
            'port_area yayimlanmiyor — animasyon turetmeye geri duser')
        assert len(tc['port_area']) == len(tc['time'])
        assert all(isinstance(a, float) and a > 0 for a in tc['port_area'])

    def test_seri_cozucununki_ile_ayni_indeks_kumesinden(self, katilar):
        """Seyreltme AYNI indekslerden geçmeli; hizasiz seri okunamaz."""
        tc = katilar['thrust_curve']
        n = len(tc['time'])
        for ad in ('thrust', 'pressure', 'burn_area', 'mass_flow', 'port_area'):
            assert len(tc[ad]) == n, ad

    def test_alan_kunyeli(self, katilar):
        """Sayının birimi ve tane tipine göre ANLAMI beyan edilir."""
        temel = katilar['thrust_curve'].get('port_area_basis') or ''
        assert 'm^2' in temel, 'birim beyani yok'
        for parca in ('end_burner', 'slotted', 'equivalent circular',
                      '_port_flow_area'):
            assert parca in temel, 'kunyede eksik: %s' % parca

    def test_baslangic_yaricapi_cizilen_portla_ayni(self, katilar):
        """sqrt(A0/pi), 3B sahnenin çizdiği başlangıç yarıçapı olmalı;
        değilse animasyon t=0'da sıçrar (ölçüldü: fark tam 0,000 mm)."""
        tc = katilar['thrust_curve']
        gd = katilar['grain_design']
        r0 = math.sqrt(tc['port_area'][0] / math.pi) * 1000.0
        assert r0 == pytest.approx(gd['inner_diameter_mm'] / 2.0, abs=1e-6)


class TestPortAlaniAnimasyonu:
    """Animasyon yayımlanan seriyi KULLANIYOR mu, türetmesiz mi?"""

    def test_kip_yayimlanan_alani_tercih_eder(self, katilar, viz_verisi):
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            'const pa = solidPortRadiusHistory(md);\n'
            'const wh = solidWebHistory(md);\n'
            'const mode = portRegressionMode({portShape: "circular", '
            'grainType: md.grain_design.grain_type, hasPortHistory: false, '
            'hasPortArea: !!pa, hasWebHistory: !!wh});\n'
            'process.stdout.write(JSON.stringify({mode: mode, '
            'kaynak: pa && pa.source, n: pa && pa.radius.length, '
            'r0mm: pa && pa.r0 * 1000, rEndMm: pa && pa.rEnd * 1000}));'
        )
        assert cikti['mode'] == 'solid_port_area', (
            'yayimlanan alan varken yine turetme kullaniliyor')
        assert cikti['kaynak'] == 'solid_port_area'
        assert cikti['n'] == len(viz_verisi['thrust_curve']['time'])
        gd = katilar['grain_design']
        assert cikti['r0mm'] == pytest.approx(gd['inner_diameter_mm'] / 2.0)

    def test_yaricap_serinin_kendisinden_okunuyor(self, katilar, viz_verisi):
        """Her örnekte r = sqrt(A/pi): ara değerleme ya da yasa YOK."""
        cikti = _run(
            'const pa = solidPortRadiusHistory(%s);\n' % json.dumps(viz_verisi) +
            'process.stdout.write(JSON.stringify(pa.radius));'
        )
        alanlar = viz_verisi['thrust_curve']['port_area']
        for A, r in zip(alanlar, cikti):
            assert r == pytest.approx(math.sqrt(A / math.pi), rel=1e-12)

    def test_web_sonu_cozucunun_beyaniyla_ortusuyor(self, katilar, viz_verisi):
        """dw = r(t_son) − r(0), çözücünün beyan ettiği web_burnout_mm'ye
        oturur (ölçüldü: 34,954 mm / 35,000 mm = %0,13)."""
        gd = katilar['grain_design']
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            'const dims = %s;\n' % json.dumps(_dims(gd)) +
            'dims.portAreaHist = solidPortRadiusHistory(md);\n'
            'const tb = %r;\n' % katilar['burn_time'] +
            'process.stdout.write(JSON.stringify({'
            'w0: burnedWebAt(dims, 0, "solid_port_area"), '
            'wEnd: burnedWebAt(dims, tb, "solid_port_area")}));'
        )
        assert cikti['w0'] == pytest.approx(0.0, abs=1e-9)
        assert cikti['wEnd'] == pytest.approx(gd['web_burnout_mm'], rel=0.005)

    def test_port_geriliyor_ve_dogrusal_degil(self, katilar, viz_verisi):
        """Gerçek seri: BATES regresif, ilk yarı ikinciden hızlı geriler.
        Düz ara değer ya da sqrt yasası bu bekçiyi geçemez."""
        tb = katilar['burn_time']
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            'const dims = %s;\n' % json.dumps(_dims(katilar['grain_design'])) +
            'dims.portAreaHist = solidPortRadiusHistory(md);\n'
            'const ts = [0, 0.25, 0.5, 0.75, 1].map(f => f * %r);\n' % tb +
            'process.stdout.write(JSON.stringify('
            'ts.map(t => portRadiusAt(dims, t, "solid_port_area"))));'
        )
        for onceki, simdiki in zip(cikti, cikti[1:]):
            assert simdiki > onceki, 'port gerilemesi durdu: %r' % (cikti,)
        ilk_yari = cikti[2] - cikti[0]
        ikinci_yari = cikti[4] - cikti[2]
        assert ilk_yari > ikinci_yari * 1.05, (
            'gerileme dogrusal gorunuyor (%.3f / %.3f mm)'
            % (ilk_yari, ikinci_yari))

    def test_sahne_yayimlanan_alani_gercekten_okuyor(self):
        """Kablolama bekçisi: saf fonksiyon doğru olsa da sahneye bağlı
        değilse animasyon yine türetmeyle sürülürdü (ölü düzeltme)."""
        src = _source()
        assert 'portAreaHist: solidPortRadiusHistory(md)' in src, (
            'yayimlanan alan dims sozlugune bağlanmamış')
        govde = src[src.index('MotorScene.prototype._resolvePortRegression'):
                    src.index('function chipAnchorMm(')]
        assert 'hasPortArea: !!d.portAreaHist' in govde, (
            'kip karari yayimlanan alani hic sormuyor')

    def test_iki_yol_ayni_egriyi_veriyor(self, katilar, viz_verisi):
        """ÇAPRAZ KANIT: yayımlanan alandan okunan yarıçap ile kütle
        dengesinden türetilen yarıçap aynı eğridir (ölçüldü: fark
        ort 0,008 mm / maks 0,027 mm — kalan pay trapezin payıdır).
        Ayrışırlarsa ya yayın ya türetme bozulmuştur."""
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            'const dims = %s;\n' % json.dumps(_dims(katilar['grain_design'])) +
            'dims.portAreaHist = solidPortRadiusHistory(md);\n'
            'dims.webHist = solidWebHistory(md);\n'
            'const ts = md.thrust_curve.time;\n'
            'const out = [];\n'
            'for (let i = 0; i < ts.length; i++) {\n'
            '  out.push([portRadiusAt(dims, ts[i], "solid_port_area"),\n'
            '            portRadiusAt(dims, ts[i], "solid_mass_balance")]);\n'
            '}\n'
            'process.stdout.write(JSON.stringify(out));'
        )
        farklar = [abs(a - b) for a, b in cikti]
        ort = sum(farklar) / len(farklar)
        assert ort < 0.02, 'ortalama fark %.4f mm' % ort
        assert max(farklar) < 0.05, 'en buyuk fark %.4f mm' % max(farklar)


class TestPortAlaniYokkenYedekYol:
    """MUTASYON: yayın geri alınırsa (bayat yanıt) yedek yol devralır."""

    def test_alan_silinince_kutle_dengesine_dusuyor(self, katilar,
                                                    viz_verisi_eski):
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi_eski) +
            'const pa = solidPortRadiusHistory(md);\n'
            'const wh = solidWebHistory(md);\n'
            'const mode = portRegressionMode({portShape: "circular", '
            'grainType: md.grain_design.grain_type, hasPortHistory: false, '
            'hasPortArea: !!pa, hasWebHistory: !!wh});\n'
            'process.stdout.write(JSON.stringify({mode: mode, pa: pa, '
            'whVar: !!wh}));'
        )
        assert cikti['pa'] is None, 'alan yokken seri UYDURULDU'
        assert cikti['whVar'] is True, 'yedek turetme calismiyor'
        assert cikti['mode'] == 'solid_mass_balance', (
            'eski yanitta animasyon susuyor — bayat sonuc dosyalari kirilir')

    def test_yedek_yol_ayni_gerilemeyi_ciziyor(self, katilar, viz_verisi_eski):
        """Yedek yol donuk bir port değil, aynı gerilemeyi verir."""
        gd = katilar['grain_design']
        tb = katilar['burn_time']
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi_eski) +
            'const dims = %s;\n' % json.dumps(_dims(gd)) +
            'dims.webHist = solidWebHistory(md);\n'
            'const ts = [0, 0.5, 1].map(f => f * %r);\n' % tb +
            'process.stdout.write(JSON.stringify('
            'ts.map(t => portRadiusAt(dims, t, "solid_mass_balance"))));'
        )
        assert cikti[0] == pytest.approx(gd['inner_diameter_mm'] / 2.0)
        assert cikti[2] > cikti[1] > cikti[0]

    def test_cip_hangi_yolun_kullanildigini_soyler(self):
        """Beyan çipi iki yolu AYIRIR: kullanıcı hangi kaynağı gördüğünü
        bilir (aynı metin çıkarsa yol değişimi ekranda kaybolurdu)."""
        src = _source()
        govde = _extract('portRegressionChipDefs', src)
        assert "mode === 'solid_port_area'" in govde
        assert 'viz.chip.portRegPortArea' in govde
        assert 'viz.chip.portRegMassBalance' in govde


class TestPortAlaniSahteVeriYasagi:
    """Yarım/bozuk/sabit alandan seri UYDURULMAZ."""

    @pytest.mark.parametrize('bozma,aciklama', [
        ('delete md.thrust_curve.port_area', 'alan yok'),
        ('md.thrust_curve.port_area = null', 'alan null'),
        ('md.thrust_curve.port_area = md.thrust_curve.port_area.slice(0, 5)',
         'dizi boylari tutmuyor'),
        ('md.thrust_curve.port_area = md.thrust_curve.port_area.map(() => 0)',
         'alan sifir'),
        ('md.thrust_curve.port_area = md.thrust_curve.port_area.map(() => -1)',
         'alan negatif'),
        ('md.thrust_curve.port_area = md.thrust_curve.port_area.map(() => "x")',
         'sayisal degil'),
        ('md.thrust_curve.time = md.thrust_curve.time.slice().reverse()',
         'zaman sirali degil'),
        ('md.thrust_curve.port_area = md.thrust_curve.port_area.map(() => 1e-3)',
         'seri sabit (uc yanmali tane)'),
    ])
    def test_bozuk_alanda_null_doner(self, viz_verisi, bozma, aciklama):
        cikti = _run(
            'const md = %s;\n' % json.dumps(viz_verisi) +
            '%s;\n' % bozma +
            'process.stdout.write(JSON.stringify(solidPortRadiusHistory(md)));'
        )
        assert cikti is None, '%s — yine de seri uretildi' % aciklama

    def test_alan_varken_de_dairesel_olmayan_kesit_donuk(self, katilar,
                                                        viz_verisi):
        """Kip kapısı alan yayımlandı diye AÇILMAZ: yıldız/finocyl/çok
        portlu tanede ve uç yanmalıda port yine donuk kalır."""
        for sekil, tane in (('star', 'star'), ('finocyl', 'finocyl'),
                            ('multiport', 'wagon_wheel'),
                            ('circular', 'end_burner'),
                            ('star', 'bates')):
            cikti = _run(
                'const md = %s;\n' % json.dumps(viz_verisi) +
                'const dims = %s;\n' % json.dumps(_dims(katilar['grain_design'])) +
                'dims.portAreaHist = solidPortRadiusHistory(md);\n'
                'const mode = portRegressionMode({portShape: %r, '
                'grainType: %r, hasPortHistory: false, '
                'hasPortArea: !!dims.portAreaHist, hasWebHistory: true});\n'
                % (sekil, tane) +
                'process.stdout.write(JSON.stringify({mode: mode, '
                'r: [0, 2].map(t => portRadiusAt(dims, t, mode))}));'
            )
            assert cikti['mode'] == 'not_modelled', (sekil, tane)
            assert cikti['r'][0] == cikti['r'][1], (
                'modellenmemis kesit animasyonlu: %s/%s' % (sekil, tane))


# ----------------------------------------------------------------------
# 9. Kip kapısının ÇÖZÜCÜDEN gelen gerekçesi (Python tarafı ölçümü)
# ----------------------------------------------------------------------

class TestCozucuPortAlaniAnlami:
    """Kapı neden yalnız dairesel port ailesine açık? Çözücünün kendi
    ``_port_flow_area`` tanımı ölçülerek gösterilir — bu ölçüm, defterdeki
    'yayımlanınca BATES dışı taneler de animasyonlanır' beklentisinin
    NEDEN karşılanamadığının kanıtıdır.
    """

    TABAN = dict(propellant_type='apcp', chamber_diameter=100.0,
                 grain_length=500.0, core_diameter=30.0, chamber_pressure=40)

    @staticmethod
    def _seri(grain_type, taban):
        import numpy as np
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        m = SolidRocketEngine(grain_type=grain_type, **taban)
        c = m.calculate_thrust_curve()
        A = np.asarray(c['port_area'], dtype=float)
        t = np.asarray(c['time'], dtype=float)
        ab = np.asarray(c['burn_area'], dtype=float)
        mdot = np.asarray(c['mass_flow'], dtype=float)
        rb = np.where(ab > 0, mdot / (m.rho_p * np.maximum(ab, 1e-30)), 0.0)
        w = np.concatenate([[0.0],
                            np.cumsum(0.5 * (rb[1:] + rb[:-1]) * np.diff(t))])
        return A, w, m.D_core / 2.0

    @pytest.mark.parametrize('grain_type', ['bates', 'star', 'wagon_wheel',
                                            'finocyl'])
    def test_dairesel_esdeger_ailede_alan_webi_tekrar_eder(self, grain_type):
        """A_port = pi*(r_core+w)^2: yayımlanan alan, web geçmişinin
        taşıdığı bilgiyi tekrar eder (ölçülen sapma <= 0,031 mm, trapezin
        payı). Yıldız/finocyl'de bu bir GEOMETRİ değil AKI modelidir —
        gerçek kesit ofsetlenmiş poligondur, o yüzden kip kapalı kalır."""
        import numpy as np
        A, w, r0 = self._seri(grain_type, self.TABAN)
        dw = np.sqrt(A / np.pi) - r0
        assert float(np.max(np.abs(dw - w))) < 4e-5, grain_type

    def test_uc_yanmalida_alan_sabittir(self):
        """Port yok: tüm kasa kesiti akar. Sabit seriden animasyon
        çıkarmak, olmayan bir gerilemeyi göstermek olurdu."""
        import numpy as np
        A, _, _ = self._seri('end_burner', self.TABAN)
        assert float(A.max() - A.min()) == 0.0
        assert float(A[0]) == pytest.approx(math.pi * 0.05 ** 2, rel=1e-12)

    def test_slotted_kesiti_gercekten_dairesel_degil(self):
        """Yarıklı tanede alan GERÇEK poligon alanıdır; eşdeğer yarıçap
        r0+w'den ölçülebilir biçimde ayrışır (17,3 mm) — tek yarıçap
        büyüterek çizmek uydurma olurdu."""
        import numpy as np
        A, w, r0 = self._seri('slotted', self.TABAN)
        dw = np.sqrt(A / np.pi) - r0
        assert float(np.max(np.abs(dw - w))) > 1e-2
