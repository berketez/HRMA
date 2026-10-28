# tests/fea — ÖH D37 A2-1 termal a2: uç sözleşmeleri + panel + matris + motor yaması
"""
Uç katmanı (hrma/app.py) ve motor dosyaları bu kulvarda PATCH'tir
(docs/scofield/raw/OH/A2/termal/a1/patch/app_termal.patch, motor_m2.patch);
ana model sıralı uygular. Yama uygulanmamışsa ilgili bekçiler ADIYLA atlanır
(sessiz yeşil değil: atlama gerekçesi yamanın adıdır); uygulanınca koşar.

  F-03 / CW-S5  /api/analysis/wall-profile ``motor_results`` gövdesi (katı,
                sıvı 200 + motor_input_basis; hibrit düz gövde BİT-AYNI);
                sıvı 400 s yanma süresi bandı (modele girmeyen alan).
  F-02          /api/fea/thermal: spatial_convergence + yayımlanan mesh +
                spatial_levels + max_steps 16384 (OH-DK-10).
  F-01 / B2-CP  thermal_paths_reconciliation + consumed_paths (iki uç).
  OH-DK-09      panel wall_thickness (köprü kalınlığı, metre) + motorun gazı
                (gamma/molecular_weight/c_star) + katı/sıvıda motor_results.
  matris        analysis_center.js termal satırı üç motor.
  M2 motor      hibrit/katı/sıvı lüle-künye satırları temperature_limits'ten.
  M2 davranış   denetçi 4. tur Ş1-Ş3: sıvı arayüz varsayılanı steel_304
                künyesi (yama) + ısı-yutucu satırı (dal kodu), hibrit Copper
                lüle uyarısının ekran kanalları, katı lüle izni klamp/erime
                değil (ısı-yutucu bekçisi TestIsiYutucuIzinBasamagi yamasız
                ağaçta da koşar).
"""
from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import types

import pytest

from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[2]
# Yol parçalarla; okuma YALNIZ çağrı yerinde kanit_gerekli(...) ile (a1 notu).
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'A2' / 'termal' / 'a1'
ONCE, SONRA = KANIT / 'once', KANIT / 'sonra'
#: Denetçi 3. tur (şart karşılama) ölçümleri: sart3/olcum_sart3.py SONRA
#: ağacında (dal + iki yama) koştu, T7 FEA uç yanıtları AYNEN yazıldı.
SART3_SONRA = KANIT / 'sart3' / 'sonra'
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'thermal_fea_panel.js'
CENTER_JS = KOK / 'hrma' / 'static' / 'js' / 'analysis_center.js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')
H = {'Host': '127.0.0.1:8080'}


def _q(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a, **k)


def _kanit_json(yol):
    """Çağıran yolu kanit_gerekli(...) kapısından GEÇİRMİŞ olarak verir."""
    return json.loads(yol.read_text(encoding='utf-8'))


def _app_yamali():
    from hrma import app as appmod
    return 'spatial_convergence' in inspect.getsource(appmod.api_fea_thermal)


app_yamasi = pytest.mark.skipif(
    not _app_yamali(),
    reason='hrma/app.py yaması uygulanmamış (patch/app_termal.patch) — uç '
           'bekçileri yama birleşince koşar')


@pytest.fixture(scope='module')
def client():
    os.environ.setdefault('HRMA_PROJECTS_DIR', str(
        pathlib.Path(os.environ.get('TMPDIR', '/tmp')) / 'hrma_a2_termal_proj'))
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def motorlar():
    return {ad: _kanit_json(kanit_gerekli(ONCE / f'{ad}_motor.json'))
            for ad in ('hibrit', 'kati', 'sivi')}


# ---------------------------------------------------------------------------
# F-03 — wall-profile motor_results gövdesi
# ---------------------------------------------------------------------------
@app_yamasi
class TestF03WallProfile:

    @pytest.mark.parametrize('ad,layout', [('kati', 'solid'), ('sivi', 'liquid')])
    def test_kati_sivi_200_ve_kunye(self, client, motorlar, ad, layout):
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': motorlar[ad]}, headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        g = r.get_json()
        wp = g['wall_profile']
        assert len(wp['x_mm']) >= 2 and all(v > 0 for v in wp['h_g'])
        mb = g['motor_input_basis']
        assert mb['engine_layout'] == layout and mb['motor_field'] == 'motor_results'
        assert 'material' in mb['paths_read'] and 'wall_thickness' in mb['paths_read']

    def test_sivi_400_s_yanma_suresi_reddedilmez(self, client, motorlar):
        """ÖLÇÜLDÜ (once): 400 s → 422 out_of_range; alan modele GİRMİYOR
        (inputs_not_used). Kapı ve [0,1; 300] s bandı AYNEN durur (ÖK-22);
        YALNIZ motor sözlüğünden kurulan gövdede motorun bant üstü süresi
        için kapıya bandın üst ucu konur ve gate_substitutions özgün 400 s ile
        beyan eder (denetçi Ş7: eski docstring 'üst bant koşturulmaz'
        diyordu, kod bandı tutup ikame ediyor). Negatif süre yine 422."""
        assert motorlar['sivi']['burn_time'] == 400.0
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': motorlar['sivi']}, headers=H)
        assert r.status_code == 200
        ik = r.get_json()['motor_input_basis']['gate_substitutions']
        assert [(i['field'], i['motor_value_s'], i['gate_value_s']) for i in ik] \
            == [('burn_time', 400.0, 300.0)]
        r2 = _q(client.post, '/api/analysis/wall-profile',
                json={'motor_results': dict(motorlar['sivi'], burn_time=-1.0)},
                headers=H)
        assert r2.status_code == 422

    @pytest.mark.parametrize('ad', ['hibrit', 'kati'])
    def test_bant_icindeki_motorda_kapi_ikamesi_yok(self, client, motorlar, ad):
        """Denetçi Ş2 (X10): ikame yalnız bandın ÜSTÜNDEKİ motor süresine;
        bant içindeki motorda (hibrit 10 s, katı 3 s) künye boş olmalı —
        yoksa gate_substitutions var olmayan bir ikameyi beyan eder."""
        assert 0.1 <= motorlar[ad]['burn_time'] <= 300.0
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': motorlar[ad]}, headers=H)
        assert r.status_code == 200
        assert r.get_json()['motor_input_basis']['gate_substitutions'] == []

    def test_acik_duz_alan_eksik_cekirdegi_karsilar(self, client, motorlar):
        """Denetçi Ş5 — ÖLÇÜLDÜ (denetim2 d2/acik_alan.py): katı sözlükten
        burn_time çıkarılıp gövdeye açıkça burn_time=3 konunca uç 422
        ['burn_time'] dönüyordu; belgelenen davranış 'açık düz alan kurucunun
        okuduğunu EZER'. Eksik denetimi artık birleşmiş gövdede."""
        m = json.loads(json.dumps(motorlar['kati']))
        m.pop('burn_time', None)
        r0 = _q(client.post, '/api/analysis/wall-profile',
                json={'motor_results': m}, headers=H)
        assert r0.status_code == 422
        assert r0.get_json()['missing_fields'] == ['burn_time']
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': m, 'burn_time': 3.0}, headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        mb = r.get_json()['motor_input_basis']
        assert mb['supplied_by_request'] == ['burn_time']
        assert mb['gate_substitutions'] == []

    def test_secenekli_bogaz_olcegi_acik_alanla_karsilanir(self, client, motorlar):
        """Denetçi 3. tur Ş3 (Z14): kurucunun seçenekli eksik kalemi
        ('throat_diameter or mdot_total', heat_transfer_analysis
        WALL_PROFILE_THROAT_SCALE_FIELDS) seçeneklerden BİRİ açıkça verilince
        karşılanır. Katı motor mdot yayımlamaz; boğaz çapı sözlükten
        çıkarılınca iki seçenek de yok → 422 adıyla. Motorun KENDİ boğaz çapı
        açık düz alan olarak verilince 200, künyede bileşik kalem, ve profil
        çıkarılmamış sözlüğün profiliyle BİT-AYNI (uydurma değer yok)."""
        m0 = motorlar['kati']
        d_t = m0['motor_geometry']['throat_diameter']
        assert 'mdot_total' not in m0 and d_t > 0
        m = json.loads(json.dumps(m0))
        del m['motor_geometry']['throat_diameter']
        kalem = 'throat_diameter or mdot_total'
        r0 = _q(client.post, '/api/analysis/wall-profile',
                json={'motor_results': m}, headers=H)
        assert r0.status_code == 422
        assert r0.get_json()['missing_fields'] == [kalem]
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': m, 'throat_diameter': d_t}, headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        mb = r.get_json()['motor_input_basis']
        assert mb['supplied_by_request'] == [kalem]
        tam = _q(client.post, '/api/analysis/wall-profile',
                 json={'motor_results': m0}, headers=H)
        assert tam.status_code == 200
        assert r.get_json()['wall_profile']['h_g'] == tam.get_json()['wall_profile']['h_g']
        # Öteki seçenek: hibrit sözlükten İKİ boğaz ölçeği de çıkarılır; motorun
        # KENDİ yayımladığı mdot_total açık alan olarak verilince kalem karşılanır.
        h = json.loads(json.dumps(motorlar['hibrit']))
        mdot = h.pop('mdot_total')
        h.pop('throat_diameter', None)
        del h['motor_geometry']['throat_diameter']
        assert mdot > 0
        r1 = _q(client.post, '/api/analysis/wall-profile',
                json={'motor_results': h}, headers=H)
        assert r1.status_code == 422 and r1.get_json()['missing_fields'] == [kalem]
        r2 = _q(client.post, '/api/analysis/wall-profile',
                json={'motor_results': h, 'mdot_total': mdot}, headers=H)
        assert r2.status_code == 200, r2.get_data(as_text=True)[:300]
        assert r2.get_json()['motor_input_basis']['supplied_by_request'] == [kalem]

    @pytest.mark.parametrize('bos', [None, ''])
    def test_acik_bos_alan_motor_degerini_ezmez(self, client, motorlar, bos):
        """Denetçi 3. tur Ş3 (Z18): istekteki açık null / boş dize alan
        'verilmedi' sayılır; motor sözlüğünden kurulan değeri EZMEZ
        (overridden_by_request'te görünmez) ve profil sözlüğün kendi
        profiliyle BİT-AYNI kalır."""
        tam = _q(client.post, '/api/analysis/wall-profile',
                 json={'motor_results': motorlar['kati']}, headers=H)
        assert tam.status_code == 200
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': motorlar['kati'], 'chamber_pressure': bos,
                     'throat_diameter': bos}, headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        mb = r.get_json()['motor_input_basis']
        assert 'chamber_pressure' not in mb['overridden_by_request']
        assert 'throat_diameter' not in mb['overridden_by_request']
        assert r.get_json()['wall_profile']['h_g'] == tam.get_json()['wall_profile']['h_g']

    def test_acik_burn_time_bant_disi_ikame_edilmez(self, client, motorlar):
        """Ş5 eki: çağıran burn_time'ı AÇIKÇA verdiyse kapı onu düz gövdedeki
        gibi sınar (ÖK-22) — motor sözlüğü yolunun ikamesi çağıranın sözünü
        örtmez."""
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': motorlar['sivi'], 'burn_time': 400.0},
               headers=H)
        assert r.status_code == 422

    def test_hibrit_duz_govde_bit_ayni(self, client, motorlar):
        """Düz gövdeli istek (eski panel) yamadan etkilenmez — ÖNCE kaydıyla."""
        once = _kanit_json(kanit_gerekli(ONCE / 'wall_profile_panel.json'))['wall_profile']
        m = motorlar['hibrit']
        govde = {k: m[k] for k in ('chamber_pressure', 'chamber_temperature',
                                   'burn_time', 'mdot_total', 'chamber_diameter',
                                   'chamber_length', 'throat_diameter',
                                   'expansion_ratio')}
        govde['nozzle_contour'] = m['nozzle_contour']
        govde['material'] = m['structural_analysis']['design_parameters']['material']
        r = _q(client.post, '/api/analysis/wall-profile', json=govde, headers=H)
        wp = r.get_json()['wall_profile']
        assert wp['h_g'] == once['h_g'] and wp['T_wall_eq'] == once['T_wall_eq']
        assert 'motor_input_basis' not in r.get_json()

    def test_motor_gazi_profili_degistirir_ve_motorun_kendi_dengesiyle_ortusur(
            self, client, motorlar):
        """Bartz eşleştirme hükmü: motorun γ/MW/c* geçince profil, motorun
        kendi gas_side_analysis dengesiyle ÖRTÜŞÜR (ölçüldü: T7 3368,476 K)."""
        m = motorlar['hibrit']
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': m}, headers=H)
        wp = r.get_json()['wall_profile']
        i = wp['throat_index']
        eq = m['heat_transfer_analysis']['gas_side_analysis']['estimated_wall_temperature']
        assert wp['T_wall_eq'][i] == pytest.approx(eq, rel=1e-6)
        once = _kanit_json(kanit_gerekli(ONCE / 'wall_profile_panel.json'))['wall_profile']
        assert wp['h_g'][i] != pytest.approx(once['h_g'][once['throat_index']])

    def test_imzasiz_motor_results_422_adiyla(self, client):
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': {'chamber_pressure': 20.0,
                                       'structural_analysis': {'case_analysis': {}}}},
               headers=H)
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'incomplete_wall_profile_input'
        assert 'chamber_temperature' in g['missing_fields']
        assert g['searched_paths']['chamber_temperature']


# ---------------------------------------------------------------------------
# F-02 / F-01 / B2-CP — /api/fea/thermal ve /api/fea/structural
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def hibrit_fea(client, motorlar):
    if not _app_yamali():
        pytest.skip('app yaması uygulanmamış')
    wp = _kanit_json(kanit_gerekli(ONCE / 'wall_profile_panel.json'))['wall_profile']
    r = _q(client.post, '/api/fea/thermal',
           json={'motor_results': motorlar['hibrit'], 'axial_profile': wp,
                 'ambient_temperature_K': 293.15}, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['fea']


@app_yamasi
class TestFeaThermalUc:

    def test_spatial_convergence_ve_yayimlanan_mesh(self, hibrit_fea):
        f = hibrit_fea
        sc = f['spatial_convergence']
        assert sc['checked'] is True and sc['verdict'] == 'converged'
        assert [(l['n_axial'], l['n_radial']) for l in sc['levels']] == [
            (16, 4), (32, 8), (64, 16)]
        assert f['mesh']['n_axial'] == 64 and f['limits']['n_axial'] == 16
        assert len(f['fields']['temperature_final_K']) == f['mesh']['n_nodes']
        # Ölçüldü (sonra/ozet.json): 64×16 → 1787,7209 K, p 1,995, GCI %0,0195
        assert f['scalars']['peak_wall_T_K'] == pytest.approx(1787.7209, abs=5e-3)
        assert sc['gci_fine_pct'] < 1.0 and 1.7 <= sc['observed_order_p'] <= 2.3
        assert f['limits']['spatial_levels'] == 3
        assert f['limits']['finest_level_elems'] == 16 * 4 * 16

    def test_dk10_tavan_16384(self, hibrit_fea):
        assert hibrit_fea['limits']['max_steps'] == 16384
        assert 'OH-DK-10' in hibrit_fea['limits']['_basis']

    def test_uzlastirma_ve_consumed_paths(self, hibrit_fea):
        rc = hibrit_fea['thermal_paths_reconciliation']
        for k in ('equilibrium_K', 'fea_peak_K', 'fea_time_s', 'gap_K',
                  'question_equilibrium', 'question_fea', 'threshold_ladder'):
            assert k in rc
        assert rc['gap_K'] == pytest.approx(rc['equilibrium_K'] - rc['fea_peak_K'])
        yollar = [c['path'] for c in hibrit_fea['consumed_paths']]
        assert 'burn_time' in yollar and 'chamber_pressure' in yollar
        assert 'structural_analysis.chamber_analysis.wall_thickness_used_mm' in yollar

    def test_dort_seviye_istenebilir(self, client, motorlar):
        wp = _kanit_json(kanit_gerekli(ONCE / 'wall_profile_panel.json'))['wall_profile']
        r = _q(client.post, '/api/fea/thermal',
               json={'motor_results': motorlar['hibrit'], 'axial_profile': wp,
                     'ambient_temperature_K': 293.15, 'spatial_levels': 4}, headers=H)
        f = r.get_json()['fea']
        assert len(f['spatial_convergence']['levels']) == 4
        assert f['mesh']['n_axial'] == 128 and f['limits']['spatial_levels'] == 4

    def test_yapisal_consumed_paths_sayi_bit_ayni(self, client, motorlar):
        """B2-CP: ``consumed_paths`` kaydı yapısal SAYIYI değiştirmez.

        YENİDEN ÇAPALANDI (fea-yuk 2. tur, 14 Eki; karar §28-18 (B), kart
        OH-DK-04 — dört koşul). Eski satır uç sayısını termal kulvarın
        kayıtlı ÖNCE ölçümüne (9,852939959847058) bit-aynı bağlıyordu; o sayı
        eski sabit-P_c iç yüküyle (kapalı uç kuvveti yok) ölçülmüştü ve
        fea-yuk yük modelini BİLEREK değiştirdi (ÖNEMLİ; uç sayısı artık
        10,545929181162439). Bekçinin iddiası — "yollar kaydı sayıyı
        değiştirmez, sayı zinciri bit-aynı" — iki bacakla AYNEN sınanır:

        (a) ESKİ YÜKTE BİT-AYNI: uçun son mesh'inde iki kip, skaler P_c
            (eski yük) ile doğrudan çözülür; kötümser SF kayıtlı ÖNCE
            sayısına BİT-AYNI (kâhin: termal kulvarın kayıtlı ölçümü,
            değişmedi). Yani girdi çıkarımı + consumed_paths + mesh + çözücü
            zinciri yük dışında hiçbir sayıya dokunmadı.
        (b) YENİ YÜKTE BİT-AYNI: uç sayısı, aynı mesh'te ÜRÜNÜN yük modeliyle
            (izantropik P(x) + kapalı uç) iki kipin doğrudan çözümünün
            kötümserine BİT-AYNI — uç katmanı sayı eklemez/bozmaz.
        Ters mutasyon (eski sabit P_c yükü) (b)'deki dağılım ve "yük değişti"
        bacağında KIRMIZI; consumed_paths kaydının sayıya sızması (a)'da
        KIRMIZI.
        """
        from hrma.fea.bridge import extract_structural_inputs
        from hrma.fea.mesh_axisym import build_wall_mesh
        from hrma.fea.structural_axisym import solve_pressure
        from tests.fea.yuk_modeli_araci import izantropik_yukte
        once = _kanit_json(kanit_gerekli(ONCE / 'ozet.json'))['fea_structural']
        r = _q(client.post, '/api/fea/structural',
               json={'motor_results': motorlar['hibrit'], 'n_axial0': 8,
                     'max_rounds': 0}, headers=H)
        f = r.get_json()['fea']
        assert {c['path'] for c in f['consumed_paths']} >= {
            'chamber_pressure', 'nozzle_contour.points'}
        izantropik_yukte(f)
        g = _q(extract_structural_inputs, motorlar['hibrit'])
        m = _q(build_wall_mesh, g['contour'], g['thickness_m'],
               n_axial=int(f['mesh']['n_axial']),
               n_radial=int(f['mesh']['n_radial']),
               offset_mode=g.get('offset_mode', 'normal'))

        def _kotumser(yuk):
            return min(_q(solve_pressure, m, g['material'], yuk,
                          axial_fix=k).min_safety_factor
                       for k in ('z_min', 'z_max'))

        # (a) eski yükte zincir bit-aynı (kayıtlı ÖNCE kâhini)
        assert _kotumser(g['inner_pressure_pa']) == once['min_sf']
        # (b) uç sayısı ürünün yük modelinin doğrudan çözümüne bit-aynı
        assert f['scalars']['min_safety_factor'] == _kotumser(
            g['pressure_load'])
        assert f['scalars']['min_safety_factor'] != once['min_sf'], (
            'uç sayısı eski yükün sayısı — yük modeli uygulanmıyor')

    @pytest.mark.parametrize('ad', ['kati', 'sivi'])
    def test_kati_sivi_termal_fea_ilk_kez(self, client, motorlar, ad):
        """F-03 / CW-S5: katı ve sıvıda termal FEA 'ok' — ilk kez sayı (ÖNEMLİ,
        Sunum 2); hüküm dürüst (ölçüldü: katı monoton ıraksama, sıvı salınımlı)."""
        r = _q(client.post, '/api/analysis/wall-profile',
               json={'motor_results': motorlar[ad]}, headers=H)
        wp = r.get_json()['wall_profile']
        r2 = _q(client.post, '/api/fea/thermal',
                json={'motor_results': motorlar[ad], 'axial_profile': wp,
                      'ambient_temperature_K': 293.15}, headers=H)
        assert r2.status_code == 200, r2.get_data(as_text=True)[:300]
        f = r2.get_json()['fea']
        assert f['status'] == 'ok' and f['scalars']['peak_wall_T_K'] > 293.15
        assert f['spatial_convergence']['verdict'] in (
            'converged', 'not_converged', 'degenerate', 'not_evaluated')
        assert f['engine_layout'] == {'kati': 'solid', 'sivi': 'liquid'}[ad]


# ---------------------------------------------------------------------------
# OH-DK-09 + F-03 — panel gövdesi ve rozetleri (node)
# ---------------------------------------------------------------------------
@needs_node
class TestPanel:

    def _kos(self, tmp_path, girdi, dil=None):
        """Panel node'da. ``dil`` verilirse GERÇEK sözlükler (i18n.js +
        i18n_common.js) panelden ÖNCE yüklenir ve dil seçilir — rozet metni
        o dilin anahtarından ve o dilin ondalık ayracıyla ölçülür."""
        from tests.test_thermal_fea_panel import HARNESS
        h = HARNESS
        if dil is not None:
            capa = 'require(panelPath);'
            assert h.count(capa) == 1, 'HARNESS kurulum çapası değişmiş'
            h = h.replace(capa, (
                "require(payload.i18nDir + '/i18n.js');\n"
                "require(payload.i18nDir + '/i18n_common.js');\n"
                "window.I18N.setLang(payload.lang);\n" + capa))
            girdi = dict(girdi, i18nDir=str(PANEL_JS.parent), lang=dil)
        script = tmp_path / 'kos.js'
        script.write_text(h, encoding='utf-8')
        data = tmp_path / 'girdi.json'
        data.write_text(json.dumps(girdi), encoding='utf-8')
        proc = subprocess.run([NODE, str(script), str(data), str(PANEL_JS)],
                              capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    def test_hibrit_govde_kalinlik_ve_motor_gazi(self, tmp_path, motorlar):
        out = self._kos(tmp_path, {'buildBody': [motorlar['hibrit']]})
        b = out['bodies'][0]
        assert b['via'] == 'flat' and b['missing'] == []
        m = motorlar['hibrit']
        t_mm = m['structural_analysis']['chamber_analysis']['wall_thickness_used_mm']
        assert b['body']['wall_thickness'] == pytest.approx(t_mm / 1000.0)
        for k in ('gamma', 'molecular_weight', 'c_star'):
            assert b['body'][k] == pytest.approx(m[k])

    def test_kalinlik_yoksa_gonderilmez(self, tmp_path, motorlar):
        m = json.loads(json.dumps(motorlar['hibrit']))
        del m['structural_analysis']['chamber_analysis']['wall_thickness_used_mm']
        out = self._kos(tmp_path, {'buildBody': [m]})
        assert 'wall_thickness' not in out['bodies'][0]['body']

    def test_motor_gaz_yayimlamiyorsa_anahtar_yok(self, tmp_path, motorlar):
        """Denetçi Ş2 (X13): motor γ/MW/c* yayımlamıyorsa gövdede bu ANAHTARLAR
        YOK (null bile değil — null uçta 'verildi' sayılıp varsayılanı
        ezebilir); sıfır/negatif/NaN değer de gönderilmez."""
        m = json.loads(json.dumps(motorlar['hibrit']))
        for k in ('gamma', 'molecular_weight', 'c_star'):
            m.pop(k, None)
        b = self._kos(tmp_path, {'buildBody': [m]})['bodies'][0]['body']
        for k in ('gamma', 'molecular_weight', 'c_star'):
            assert k not in b, (k, b.get(k))
        m2 = dict(json.loads(json.dumps(motorlar['hibrit'])),
                  gamma=0.0, molecular_weight=-1.0, c_star=None)
        b2 = self._kos(tmp_path, {'buildBody': [m2]})['bodies'][0]['body']
        for k in ('gamma', 'molecular_weight', 'c_star'):
            assert k not in b2, (k, b2.get(k))

    @pytest.mark.parametrize('ad', ['kati', 'sivi'])
    def test_kati_sivi_motor_results_gonderir(self, tmp_path, motorlar, ad):
        out = self._kos(tmp_path, {'buildBody': [motorlar[ad]]})
        b = out['bodies'][0]
        assert b['via'] == 'motor_results' and b['missing'] == []
        assert b['body'] == {'motor_results': motorlar[ad]}

    def test_rozet_merdiven_hukmu_sunucudan(self, tmp_path):
        fea = _kanit_json(kanit_gerekli(SONRA / 'fea_thermal_varsayilan.json'))['fea']
        out = self._kos(tmp_path, {'fea': fea})
        html = out['els']['fea_t_badges']['html']
        assert 'MESH CONVERGED' in html and 'GCI' in html
        assert 'published level 64×16' in html
        assert 'TWO THERMAL PATHS' in html
        assert 'MESH CONVERGENCE NOT CHECKED' not in html
        kunye = out['els']['fea_t_basis_text']['html']
        assert 'Spatial ladder' in kunye and 'Two thermal paths' in kunye
        assert 'Motor fields read by the FEA bridge' in kunye

    def test_rozet_not_converged_nedeniyle(self, tmp_path):
        """Denetçi Ş4 — EN ekranda neden İNGİLİZCE, iç kod YOK. ÖLÇÜLDÜ
        (sonra/kare/termal_panel_t7_1440.png): eski rozet 'p_dusuk: gözlenen
        mertebe 0.450 < 1 ...' basıyordu. Yük: sart3/sonra (T7 jenerik gaz,
        p 0,450 → reason_code observed_order_below_min)."""
        fea = _kanit_json(kanit_gerekli(SART3_SONRA / 't7_fea_jenerik_gaz.json'))['fea']
        assert fea['spatial_convergence']['reason_code'] == 'observed_order_below_min'
        out = self._kos(tmp_path, {'fea': fea})
        html = out['els']['fea_t_badges']['html']
        assert 'MESH NOT CONVERGED' in html
        assert 'observed order p = 0.450 &lt; 1.0' in html
        assert 'p_dusuk' not in html and 'gözlenen' not in html
        assert not re.search('[çğıİöşüÇĞÖŞÜ]', html), 'EN rozette Türkçe harf'
        # Ş7: p < p_min → künye dışdeğer SAYISINI basmaz, nedenini söyler
        kunye = out['els']['fea_t_basis_text']['html']
        sc = fea['spatial_convergence']
        assert sc['richardson_reliable'] is False
        ext = f"{sc['richardson_extrapolated_peak_K']:.2f}"
        assert 'Richardson extrapolation NOT shown' in kunye
        assert f'Richardson extrapolation {ext}' not in kunye
        # iç kod künyede de yok (çözücünün insan metni kodu taşımaz)
        assert 'p_dusuk' not in kunye

    def test_rozet_tr_dilinde_ve_virgullu(self, tmp_path):
        """Ş4 — TR ekranda aynı rozet Türkçe anahtardan ve ondalık VİRGÜLLE
        (§0 kural 4); merdiven künyesindeki sayılar da virgüllü. ÖNCE:
        TR ekranda 'p_dusuk' ve noktalı ondalık (toFixed) basılıyordu."""
        fea = _kanit_json(kanit_gerekli(SART3_SONRA / 't7_fea_jenerik_gaz.json'))['fea']
        out = self._kos(tmp_path, {'fea': fea}, dil='tr')
        html = out['els']['fea_t_badges']['html']
        assert 'MESH YAKINSAMADI' in html
        assert 'gözlenen mertebe p = 0,450 &lt; 1,0' in html
        assert 'p_dusuk' not in html and 'observed order' not in html
        kunye = out['els']['fea_t_basis_text']['html']
        tepe = fea['spatial_convergence']['levels'][0]['peak_wall_T_K']
        assert f'{tepe:.2f}'.replace('.', ',') + ' K' in kunye
        assert f'{tepe:.2f} K' not in kunye
        assert 'Richardson dışdeğeri GÖSTERİLMEDİ' in kunye

    def test_rozet_en_dilinde_sozlukten(self, tmp_path):
        """Ş4 — EN sözlük yüklüyken metin anahtardan gelir (yedek metinle
        aynı); ondalık nokta."""
        fea = _kanit_json(kanit_gerekli(SART3_SONRA / 't7_fea_jenerik_gaz.json'))['fea']
        out = self._kos(tmp_path, {'fea': fea}, dil='en')
        html = out['els']['fea_t_badges']['html']
        assert 'observed order p = 0.450 &lt; 1.0' in html and 'p_dusuk' not in html

    def test_rozet_monoton_iraksama_nedeni(self, tmp_path):
        """A+A (en ince + motorun gazı) T7: merdiven monoton ıraksıyor
        (sart3/sonra.json) → neden kodu non_monotonic + gci_status →
        'monotonic divergence'; dışdeğer yok (richardson_reliable None)."""
        fea = _kanit_json(kanit_gerekli(SART3_SONRA / 't7_fea_motor_gazi.json'))['fea']
        sc = fea['spatial_convergence']
        assert sc['reason_code'] == 'non_monotonic'
        assert sc['gci_status'] == 'monotonic_divergent'
        assert sc['richardson_reliable'] is None
        html = self._kos(tmp_path, {'fea': fea})['els']['fea_t_badges']['html']
        assert 'MESH NOT CONVERGED — monotonic divergence' in html
        html_tr = self._kos(tmp_path, {'fea': fea}, dil='tr')['els'][
            'fea_t_badges']['html']
        assert 'monoton ıraksama' in html_tr

    def test_kodsuz_eski_yukte_neden_uydurulmaz(self, tmp_path):
        """Ş4 fail-closed: reason_code taşımayan eski yük (sonra/
        t7_fea_thermal.json, 25 Eyl) Türkçe metni basmaz, 'makine
        biçiminde beyan edilmedi' der."""
        fea = _kanit_json(kanit_gerekli(SONRA / 't7_fea_thermal.json'))['fea']
        assert 'reason_code' not in fea['spatial_convergence']
        html = self._kos(tmp_path, {'fea': fea})['els']['fea_t_badges']['html']
        assert 'MESH NOT CONVERGED' in html
        assert 'reason not declared in machine form' in html
        assert 'p_dusuk' not in html and 'gözlenen' not in html

    def test_eski_yuk_hukum_uydurmaz(self, tmp_path):
        """Yamasız (ÖNCE) yükte spatial_convergence yok; panel çözücünün
        kendi bloğunu okur (tek inceltme, converged True) — sunucu ne
        dediyse o; blok da yoksa BEYAN EDİLMEDİ."""
        fea = _kanit_json(kanit_gerekli(ONCE / 'fea_thermal_varsayilan.json'))['fea']
        out = self._kos(tmp_path, {'fea': fea})
        html = out['els']['fea_t_badges']['html']
        assert 'single 2× refinement' in html and 'no GCI' in html
        assert 'MESH CONVERGED (3-level' not in html
        fea2 = json.loads(json.dumps(fea))
        fea2['meta']['cozucu'].pop('uzamsal_yakinsama', None)
        fea2['meta'].pop('mesh_politikasi', None)
        html2 = self._kos(tmp_path, {'fea': fea2})['els']['fea_t_badges']['html']
        assert 'NOT DECLARED' in html2

    # --- Denetçi 3. tur Ş3 (Z9, Z16): köprü → panel zinciri DAVRANIŞLA -----
    def _kopru_panel_yuku(self, monkeypatch, tepeler):
        """Köprü (bridge.run_thermal_from_motor) örnek hibrit motor + ÖNCE
        profiliyle GERÇEK koşar; yalnız çözücünün merdiven basamaklarının
        tepe değerleri sentetiktir (a1 _stub_merdiven deseni). Köprünün
        ürettiği spatial_convergence AYNEN (JSON gidiş-dönüş) panelin
        yüküne konur; taban yük sonra/fea_thermal_varsayilan.json. Böylece
        tablo eşitliği değil, köprünün kod eşlemesi + panelin render'ı
        birlikte ölçülür."""
        from hrma.fea import bridge
        from hrma.fea import thermal_axisym as ta
        gercek = ta._uzamsal_yakinsama

        class M:
            def __init__(self, na, nr):
                self.n_axial, self.n_radial = na, nr
                self.n_elems, self.n_nodes = na * nr, (na + 1) * (nr + 1)

        def sahte_merdiven(result, mesh, material, times, inner_bc, outer_bc,
                           T_initial, mesh_refiner, spatial_tol, **_):
            sira = {'i': 0}

            def sahte(mesh_, material_, times_, ibc_, obc_, T0_, keep_history=True):
                i = sira['i']
                sira['i'] += 1
                return types.SimpleNamespace(
                    peak_wall_T=float(tepeler[i]),
                    energy={'dU_J': 1.0e6 * (1 + 0.001 * i)}, T_history=None)
            asil = ta.solve_transient
            ta.solve_transient = sahte
            try:
                ilk = sahte(None, None, None, None, None, T_initial)
                blok, _, _ = gercek(ilk, M(16, 4), None, times, None, None,
                                    T_initial, lambda a, r: M(a, r), spatial_tol)
            finally:
                ta.solve_transient = asil
            return blok, result, mesh
        monkeypatch.setattr(ta, '_uzamsal_yakinsama', sahte_merdiven)
        m = _kanit_json(kanit_gerekli(ONCE / 'hibrit_motor.json'))
        wp = _kanit_json(kanit_gerekli(ONCE / 'wall_profile_panel.json'))['wall_profile']
        o = bridge.run_thermal_from_motor(m, axial_profile=wp,
                                          ambient_temperature_K=293.15)
        sc = json.loads(json.dumps(o['spatial_convergence'], default=float))
        fea = _kanit_json(kanit_gerekli(SONRA / 'fea_thermal_varsayilan.json'))['fea']
        fea['spatial_convergence'] = sc
        # Künye kanalları da AYNI köprü koşusundan (Ş4 tekrar bekçisi).
        meta = json.loads(json.dumps(o['meta'], default=float))
        fea['meta']['mesh_politikasi'] = meta['mesh_politikasi']
        fea['meta']['not_modelled'] = meta['not_modelled']
        fea['meta']['cozucu']['uzamsal_yakinsama'] = meta['cozucu']['uzamsal_yakinsama']
        return sc, fea

    def test_kunyede_uzamsal_beyan_tek_kez(self, tmp_path, monkeypatch):
        """Denetçi 3. tur Ş4: köprünün mesh_politikasi.beyan'ı çözücünün
        uzamsal beyanını GÖMÜYORDU, panel aynı paragrafı spatial.declaration
        satırında ikinci kez basıyordu (ölçüldü sart3/kare TR/EN). Beyanın
        tek yeri declaration; köprünün politika beyanı yalnız hüküm kodu +
        gönderme taşır. İki dilde künyede beyanın ilk cümlesi TAM BİR kez."""
        sc, fea = self._kopru_panel_yuku(monkeypatch, [1293.15, 1413.15, 1443.15])
        beyan = sc['declaration']
        assert beyan and fea['meta']['cozucu']['uzamsal_yakinsama']['beyan'] == beyan
        politika = fea['meta']['mesh_politikasi']['beyan']
        ilk = beyan.split('.')[0]
        assert len(ilk) > 20 and ilk not in politika
        assert 'hüküm kodu: not_converged' in politika
        # Denetçi 4. tur Ş4 (V16): çözücü beyan YAYIMLADIĞINDA politika
        # beyanı o tek yere GÖNDERİR. Koşul tersine dönerse künyede "çözücü
        # uzamsal beyan yayımlamadı" diye YANLIŞ cümle çıkar ve yukarıdaki
        # tekrar/hüküm kodu denetimleri yeşil kalır. Gerçek FEA'da da aynı
        # (ölçüldü: sart5/olcum_sonra.json 'kopru' — hibrit, converged).
        assert 'çözücünün uzamsal beyanındadır' in politika, politika
        assert 'yayımlamadı' not in politika, politika
        for dil in ('en', 'tr'):
            kunye = self._kos(tmp_path, {'fea': fea}, dil=dil)['els'][
                'fea_t_basis_text']['html']
            assert kunye.count(ilk) == 1, (dil, kunye.count(ilk))

    def test_gci_toleransi_rozeti_kopruden_en_tr(self, tmp_path, monkeypatch):
        """Z9: GCI > tolerans yolu. p = 2 ama farklar büyük (ΔT 1000 → 1120
        → 1150 K; a1 test_gci_toleransi_asilinca_gci_buyuk ile aynı dizi) →
        köprü reason_code 'gci_above_tolerance'; rozet EN/TR metni o kodun
        anahtarından ve sayıları sunucunun GCI/tolerans alanlarından. Kod iki
        tabloda TUTARLI yeniden adlandırılsa (tablo eşitliği bekçisi yeşil
        kalır) panel kodu tanımaz, 'reason not declared' basar — bu bekçi
        onu yakalar."""
        sc, fea = self._kopru_panel_yuku(monkeypatch, [1293.15, 1413.15, 1443.15])
        assert sc['verdict'] == 'not_converged'
        assert sc['reason_code'] == 'gci_above_tolerance'
        assert sc['richardson_reliable'] is True
        g, tol = sc['gci_fine_pct'], sc['gci_tolerance_pct']
        assert g > tol
        html = self._kos(tmp_path, {'fea': fea}, dil='en')['els']['fea_t_badges']['html']
        assert f'GCI {g:.3f}% above the {tol:.2f}% tolerance' in html, html[:400]
        assert 'reason not declared' not in html
        html_tr = self._kos(tmp_path, {'fea': fea}, dil='tr')['els'][
            'fea_t_badges']['html']
        g_tr, tol_tr = f'{g:.3f}'.replace('.', ','), f'{tol:.2f}'.replace('.', ',')
        assert f'GCI %{g_tr}, %{tol_tr} toleransının üstünde' in html_tr, html_tr[:400]
        assert 'beyan edilmedi' not in html_tr

    def test_monoton_olmayan_merdivende_guvenilirlik_null_neden_uydurulmaz(
            self, tmp_path, monkeypatch):
        """Z16: monoton olmayan merdivende (ΔT farkları büyüyor → monoton
        ıraksama) dışdeğer YOKTUR: köprü richardson_reliable null yayımlar
        (false değil). Panel null'ı 'mertebe asimptotik alt sınırın altında'
        diye okumaz — o neden yalnız p < p_min'e aittir."""
        sc, fea = self._kopru_panel_yuku(monkeypatch, [1300.0, 1320.0, 1360.0])
        assert sc['reason_code'] == 'non_monotonic'
        assert sc['gci_status'] == 'monotonic_divergent'
        assert sc['richardson_extrapolated_peak_K'] is None
        assert sc['richardson_reliable'] is None
        for dil, yasak in (('en', 'below the asymptotic minimum'),
                           ('tr', 'asimptotik alt sınırın altında')):
            out = self._kos(tmp_path, {'fea': fea}, dil=dil)
            kunye = out['els']['fea_t_basis_text']['html']
            rozet = out['els']['fea_t_badges']['html']
            assert yasak not in kunye and yasak not in rozet, dil
        assert 'monotonic divergence' in self._kos(tmp_path, {'fea': fea}, dil='en')[
            'els']['fea_t_badges']['html']


# ---------------------------------------------------------------------------
# Matris satırı + i18n çapaları
# ---------------------------------------------------------------------------
def test_matris_termal_satiri_uc_motor():
    src = CENTER_JS.read_text(encoding='utf-8')
    m = re.search(r"analysisId: 'thermal'.*?motorTypes: \[([^\]]*)\]", src, re.S)
    assert m, 'termal satırı bulunamadı'
    assert {"'hybrid'", "'solid'", "'liquid'"} <= set(
        x.strip() for x in m.group(1).split(','))


def test_i18n_anahtarlari_capa_icinde_en_ve_tr():
    src = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    bloklar = re.findall(r"// A2 termal \+k ↓(.*?)// A2 termal \+k ↑", src, re.S)
    assert len(bloklar) == 2
    for blok in bloklar:
        for k in ('feaT.badgeMeshConverged', 'feaT.badgeMeshNotConvergedGci',
                  'feaT.badgeMeshLegacy', 'feaT.badgeReconciliation',
                  'feaT.ladderLine', 'feaT.reconLine', 'feaT.consumedPaths',
                  # denetçi Ş4/Ş7 (3. tur)
                  'feaT.meshReasonOrderLow', 'feaT.meshReasonGciLarge',
                  'feaT.meshReasonDivergent', 'feaT.meshReasonOscillatory',
                  'feaT.meshReasonNonMonotonic', 'feaT.meshReasonUnknown',
                  'feaT.ladderLineUnreliable'):
            assert f"'{k}'" in blok, k
    # EN = TR: iki çapada aynı anahtar kümesi
    kume = [set(re.findall(r"'(feaT\.[\w.]+)'\s*:", b)) for b in bloklar]
    assert kume[0] == kume[1] and len(kume[0]) == 16


def test_neden_kodu_tablosu_kopruyle_ayni():
    """Ş4: panelin çözücü-bloğu tablosu (SOLVER_REASON_CODES) köprünün
    sözleşme tablosuyla (bridge.SPATIAL_REASON_CODES) BİREBİR — iki dilde iki
    tablo, tek bekçi."""
    from hrma.fea.bridge import SPATIAL_REASON_CODES
    src = PANEL_JS.read_text(encoding='utf-8')
    m = re.search(r'const SOLVER_REASON_CODES = \{(.*?)\};', src, re.S)
    assert m, 'SOLVER_REASON_CODES bulunamadı'
    js = dict(re.findall(r"(\w+):\s*'(\w+)'", m.group(1)))
    assert js == SPATIAL_REASON_CODES


def test_panel_rozeti_sunucu_neden_metnini_basmaz():
    """Ş4 kaynak bekçisi: rozet neden metni yalnız spatialReasonText'ten;
    sunucunun Türkçe ``reason`` alanı görünüm modeline taşınmaz."""
    src = PANEL_JS.read_text(encoding='utf-8')
    assert 'sc.reason ||' not in src and 'u.neden ||' not in src
    assert 'reason: esc(spatialReasonText(sp))' in src


# ---------------------------------------------------------------------------
# M2 motor satırları (patch/motor_m2.patch) — uygulanmamışsa atlanır
# ---------------------------------------------------------------------------
def _motor_yamali():
    src = (KOK / 'hrma/engines/liquid_rocket_engine.py').read_text(encoding='utf-8')
    return 'material_temperature_ladder_K' in src


motor_yamasi = pytest.mark.skipif(
    not _motor_yamali(),
    reason='motor M2 yaması uygulanmamış (patch/motor_m2.patch) — ana model '
           'sıralı uygular')

#: Denetçi 4. tur Ş1 (V8): test_sivi_kunye_erime_degil_izin gövdesi + ARAYÜZ
#: varsayılanı (liquid.html <select id="chamber_material"> ilk seçeneği
#: 'steel_304'; ölçüldü sart5/olcum_*.json 'arayuz'). Arayüz anahtarı
#: gönderilir: materials_db adı (ss_304) motor tarafından REDDEDİLİR ve
#: inconel_718'e düşer (4. tur Ş1-a).
SIVI_ABLATIF_STEEL_304 = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
    'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2, 'chamber_wall_thickness': 5,
    'cooling_type': 'ablative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
    'chamber_material': 'steel_304'}


#: Denetçi 4. tur Ş3 (V13): olcum_zinciri.py KATI_GOVDE ile AYNI (katı motor
#: kanıtı bu gövdeyle üretildi); lüle malzemesi testte arayüz seçeneğiyle.
KATI_GOVDE = {
    'motor_name': 'A2-termal-kati', 'propellant_type': 'apcp',
    'grain_type': 'bates', 'chamber_pressure': 40.0, 'thrust': 5000.0,
    'burn_time': 3.0, 'chamber_diameter': 100.0, 'grain_length': 500.0,
    'core_diameter': 30.0, 'expansion_ratio': 8.0,
}


@pytest.fixture(scope='module')
def sivi_steel_304_ablatif(client):
    """Tek koşu, iki bekçi: künye (motor yaması) + ısı-yutucu (dal kodu)."""
    r = _q(client.post, '/calculate_liquid', json=SIVI_ABLATIF_STEEL_304, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    g = r.get_json()
    assert 'warn.liquid.option_not_recognised' not in json.dumps(g), \
        'steel_304 arayüz anahtarı reddedildi — bekçi yanlış malzemeyi ölçerdi'
    return g


@motor_yamasi
class TestM2MotorSatirlari:

    def test_uc_motor_dosyasi_tek_eski_zincir_yok(self):
        for ad in ('hybrid', 'solid', 'liquid'):
            src = (KOK / f'hrma/engines/{ad}_rocket_engine.py').read_text(encoding='utf-8')
            assert 'temperature_limits' in src, ad
        s = (KOK / 'hrma/engines/solid_rocket_engine.py').read_text(encoding='utf-8')
        assert "or mat.get('max_service_temperature')\n" not in s

    def test_sivi_kunye_erime_degil_izin(self, client):
        """Ölçüldü (once/sonra ozet): sıvı ablatif inconel_718
        material_service_limit_K 1533 (erime) → 977 (izin)."""
        once = _kanit_json(kanit_gerekli(ONCE / 'ozet.json'))['sivi_ablatif_718']
        assert once['material_service_limit_K'][0][1] == 1533
        govde = {'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
                 'chamber_pressure': 100, 'mixture_ratio': 2.5,
                 'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
                 'combustion_efficiency': 97, 'contraction_ratio': 4,
                 'characteristic_length': 1.2, 'chamber_wall_thickness': 5,
                 'cooling_type': 'ablative', 'injector_type': 'impinging',
                 'engine_cycle': 'pressure_fed', 'safety_factor': 2.5}
        r = _q(client.post, '/calculate_liquid', json=govde, headers=H)
        assert r.status_code == 200
        g = r.get_json()
        m = g.get('motor') if isinstance(g.get('motor'), dict) else g
        tp = m['thermal_protection']
        assert tp['material_service_limit_K'] == 977.0
        assert tp['material_temperature_ladder_K']['melting_K'] == 1533.0
        assert 'allowable_K' in tp['material_service_limit_basis']

    def test_sivi_arayuz_varsayilani_kunye_izin_basamagi(self, sivi_steel_304_ablatif):
        """Denetçi 4. tur Ş1 (V8) — ÖNEMLİ satır (Sunum 2 §3 [4. tur]):
        arayüz varsayılanı steel_304'te ablatif künye 1673 (erime) → 1073 K
        (izin). Yukarıdaki inconel_718 bekçisi izin ile SERVİS basamağını
        ayırt edemez (718'de ikisi de 977); yama SERVİS basamağını yayımlasa
        steel_304'te 1143 çıkar ve o test yeşil kalırdı. steel_304'te üç
        basamak ayrık: izin 1073 < servis 1143 < erime 1673. Ölçüldü:
        sart5/olcum_once.json (main c7774a33, yamasız) 1673 ⟷
        olcum_yamasiz.json (birleşik, yamasız) 1673 ⟷ olcum_sonra.json
        (birleşik + iki yama) 1073 — künye yalnız motor yamasıyla değişir."""
        tp = sivi_steel_304_ablatif['thermal_protection']
        merd = tp['material_temperature_ladder_K']
        assert tp['material_service_limit_K'] == 1073.0
        assert merd['allowable_K'] == 1073.0
        assert merd['service_K'] == 1143.0
        assert merd['melting_K'] == 1673.0
        assert tp['material_service_limit_K'] not in (merd['service_K'],
                                                      merd['melting_K'])
        assert 'allowable_K' in tp['material_service_limit_basis']

    def test_hibrit_bakir_lule_izin_723_ve_uyari(self, client):
        """Denetçi Ş2 (X16) — hüküm DÖNEN satır. ÖLÇÜLDÜ (sart3 once ⟷ sonra,
        örnek hibrit + arayüz seçeneği nozzle_material='copper'): boğaz cidarı
        790,37 K; izin 1000 → 723 K, marj +209,6 → −67,4 K, kullanım 0,790 →
        1,093, hüküm SAFE → EXCEEDS_ALLOWABLE ve YENİ critical
        warn.hybrid.nozzle_material_over_temp (Sunum 2 §3)."""
        govde = {'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
                 'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
                 'oxidizer_type': 'n2o', 'expansion_ratio': 4.0,
                 'nozzle_type': 'conical', 'chamber_material': 'steel_4130',
                 'wall_thickness': 5, 'nozzle_material': 'copper'}
        r = _q(client.post, '/calculate', json=govde, headers=H)
        assert r.status_code == 200
        nma = r.get_json()['motor']['nozzle_material_analysis']
        tt = nma['throat_thermal']
        assert tt['allowable_temperature_K'] == 723.0
        assert tt['verdict'] == 'EXCEEDS_ALLOWABLE'
        assert tt['temperature_margin_K'] == pytest.approx(
            723.0 - tt['throat_wall_temperature_K'])
        kodlar = [w.get('code') for w in nma['warnings'] if isinstance(w, dict)]
        assert 'warn.hybrid.nozzle_material_over_temp' in kodlar
        # Denetçi 3. tur Ş3 (Z7): Sunum 2 ve bu docstring 'YENİ critical'
        # diyor — önem de ölçülür. Kod yanıtın HER yerinde (nozzle bloğu,
        # motor.warnings, motor.design_warnings) aynı önemle çıkmalı.
        onemler = []

        def gez(x):
            if isinstance(x, dict):
                if x.get('code') == 'warn.hybrid.nozzle_material_over_temp':
                    onemler.append(x.get('severity'))
                for v in x.values():
                    gez(v)
            elif isinstance(x, list):
                for v in x:
                    gez(v)
        gez(r.get_json()['motor'])
        assert onemler and set(onemler) == {'critical'}, onemler
        # Denetçi 4. tur Ş2 (V7): yukarıdaki denetim yalnız BULUNAN
        # kopyaların önemine bakar. Teslim kanalı (_critical_thermal_verdicts)
        # lüle bloğunu atlasa kod yalnız nozzle bloğunda kalır; ekran
        # katmanı yalnız motor.warnings'i okur (hibrit motorun P16S1-07
        # notu), dış tüketiciler motor.design_warnings'i — HÜKÜM DÖNEN satır
        # ekranda görünmez, bu test yeşil kalırdı. Ölçüldü
        # (sart5/olcum_sonra.json 'hibrit_copper'): $.motor.design_warnings[2]
        # ve $.motor.warnings[2] critical. Kanal başına VARLIK + önem; kimliğe
        # göre yinelenmediği için her listede TAM bir kez.
        motor = r.get_json()['motor']
        for kanal in ('design_warnings', 'warnings'):
            kayit = [w for w in (motor.get(kanal) or [])
                     if isinstance(w, dict)
                     and w.get('code') == 'warn.hybrid.nozzle_material_over_temp']
            assert len(kayit) == 1, (kanal, kayit)
            assert kayit[0].get('severity') == 'critical', (kanal, kayit)


    @pytest.mark.parametrize('malzeme, izin', [('graphite', 3300.0),
                                                ('tungsten', 2473.0)])
    def test_kati_lule_izni_klamp_ve_erime_degil(self, client, malzeme, izin):
        """Denetçi 4. tur Ş3 (V13): katı lüle izninin yalnız KAYNAK bekçisi
        vardı (test_uc_motor_dosyasi_tek_eski_zincir_yok); yama izni klamp
        basamağından okusa graphite 3300 yerine 3500 K yayımlanır, testler
        yeşil kalırdı. Davranış: /calculate_solid (arayüzün nozzle_material
        seçenekleri; graphite varsayılan, tungsten ikinci analiz edilen
        seçenek — phenolic'in materials_db kaydı yok, not_analyzed)
        yayımlanan izin == merdivenin İZİN basamağı ve klamp/erime
        basamaklarından FARKLI: graphite 3300 (klamp 3500, erime 3900),
        tungsten 2473 (klamp 3600, erime 3695). Tungstende klamp okunsa
        T_aw 3594,9 K < 3600 → hüküm EXCEEDS_ALLOWABLE → SAFE döner. Ölçüldü:
        sart5/olcum_{once,yamasiz,sonra}.json — iki malzemede üç ağaçta da
        bit-aynı (Sunum 2 'graphite 3300 bit-aynı'; yamasız ağaçta eski
        zincir de 3300 / 2473 verir). Bekçi yama sınıfında durur: V13
        çapası yamanın satırıdır."""
        from hrma.data.materials_db import get_material, temperature_limits
        r = _q(client.post, '/calculate_solid',
               json=dict(KATI_GOVDE, nozzle_material=malzeme), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        nma = r.get_json()['nozzle_material_analysis']
        assert nma['status'] == 'analyzed' and nma['material'] == malzeme
        tl = temperature_limits(get_material(malzeme))
        assert nma['allowable_temperature_k'] == izin == tl['allowable_K']
        assert izin not in (tl['clamp_K'], tl['melting_K'])
        t_aw = nma['adiabatic_wall_temperature_k']
        assert nma['thermal_margin_k'] == pytest.approx(izin - t_aw, abs=0.11)
        assert nma['verdict'] == ('SAFE' if t_aw <= izin else 'EXCEEDS_ALLOWABLE')


# ---------------------------------------------------------------------------
# Denetçi 4. tur Ş1 (ısı-yutucu satırı): DAL kodu — YAMASIZ ağaçta da koşar.
# Isı-yutucu sınırı thermal_protection.wall_temperature_history →
# temperature_limits(rec)['allowable_K'] (dalın M2 tüketicisi); motor yaması
# gerekmez (ölçüldü: sart5/olcum_yamasiz.json ⟷ olcum_sonra.json aynı).
# ---------------------------------------------------------------------------
class TestIsiYutucuIzinBasamagi:

    def test_sivi_steel_304_isi_yutucu_izin_basamagi(self, sivi_steel_304_ablatif):
        """Denetçi 4. tur Ş1 (ısı-yutucu satırı, Sunum 2 §3 [4. tur]):
        ablatif steel_304 çıplak cidar sınırı 1143 (servis) → 1073 K (izin),
        sınıra süre 0,08345 → 0,06722 s. Ölçüldü: sart5/olcum_once.json
        (main c7774a33) 1143 K / 0,083449 s ⟷ olcum_yamasiz.json ve
        olcum_sonra.json 1073 K / 0,067225 s (yamaya bağlı DEĞİL)."""
        wth = sivi_steel_304_ablatif['thermal_protection'][
            'passive_thermal_protection']['wall_temperature_history']
        assert wth['status'] == 'modelled'
        assert wth['wall_material'] == 'ss_304'
        assert wth['max_service_temp_K'] == 1073.0
        assert wth['melting_point_K'] == 1673.0
        assert wth['time_to_limit_s'] == pytest.approx(0.067225, rel=1e-3)
        assert wth['time_to_limit_s'] < wth['time_to_melting_s']


# ---------------------------------------------------------------------------
# Devralma (5. tur, 7 Eki 2026): M2 motor satırlarında İZİN basamağı ⟷ öbür
# basamaklar ve HAM kayıt alanları. Denetçinin V8'i sıvıda "izin = servis olan
# malzemede basamak karışması görünmez" açığını yakalamıştı; aynı aile katı ve
# hibrit lülede de açıktı: arayüzün lüle seçeneklerinin HEPSİNDE izin = servis
# (graphite 3300 = 3300, tungsten 2473 = 2473, copper 723 = 723) — yama SERVİS
# basamağını okusa ekran sayısı değişmez, yukarıdaki bekçiler yeşil kalırdı.
# Ayrıca HAM alan okuma (M2'nin kapattığı hata: allowable_temperature ya da
# max_service_temperature) sıvı steel_304 / inconel_718'de ve katı graphite /
# tungsten / carbon_carbon'da izinle AYNI sayıyı verir — görünmez. Uçlar
# materials_db'nin 24 kaydının hepsini kabul eder (ölçüldü:
# sart5/devralma/olcum/lule_tum_{once,sonra}.json); ayırt eden kayıtlar:
#   carbon_carbon  izin 1920 < servis 2273 < klamp 2400 < erime 3900 (dördü
#                  ayrık; lüle izni M2'den ÖNCE de 1920 — sayı bit-aynı, bekçi
#                  yalnız basamak SEÇİMİNİ kilitler; yamasız ağaçta da geçer);
#   copper         ham allowable_temperature 1000 ≠ izin 723 (= servis) ≠ klamp
#                  1358 — katı lüle izni 1000 → 723, sıvı künye (copper_c101)
#                  1358 → 723: sayı DEĞİŞİR (yalnız yamayla) → yama bekçisi.
# ---------------------------------------------------------------------------
class TestM2BasamakVeHamAlanAyrimi:

    @staticmethod
    def _merdiven(ad, beklenen):
        from hrma.data.materials_db import get_material, temperature_limits
        rec = get_material(ad)
        tl = temperature_limits(rec)
        basamak = (tl['allowable_K'], tl['service_K'], tl['clamp_K'], tl['melting_K'])
        assert basamak == beklenen, (ad, basamak)
        return rec, tl

    def test_kati_lule_izni_servis_basamagi_degil(self, client):
        """Katı: /calculate_solid (KATI_GOVDE) nozzle_material=carbon_carbon →
        allowable_temperature_k == İZİN 1920; servis 2273, klamp 2400, erime
        3900 DEĞİL. Ölçüldü: T_aw 3594,9 K, marj −1674,9 K, EXCEEDS_ALLOWABLE
        (üç ağaçta bit-aynı). Yama satırı servis basamağını okusa 2273 çıkar."""
        _, tl = self._merdiven('carbon_carbon', (1920.0, 2273.0, 2400.0, 3900.0))
        r = _q(client.post, '/calculate_solid',
               json=dict(KATI_GOVDE, nozzle_material='carbon_carbon'), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        g = r.get_json()
        assert 'option_not_recognised' not in json.dumps(g)
        nma = g['nozzle_material_analysis']
        assert nma['status'] == 'analyzed' and nma['material'] == 'carbon_carbon'
        assert nma['allowable_temperature_k'] == tl['allowable_K'] == 1920.0
        assert nma['allowable_temperature_k'] not in (tl['service_K'], tl['clamp_K'],
                                                      tl['melting_K'])
        t_aw = nma['adiabatic_wall_temperature_k']
        assert nma['thermal_margin_k'] == pytest.approx(1920.0 - t_aw, abs=0.11)
        assert nma['verdict'] == ('SAFE' if t_aw <= 1920.0 else 'EXCEEDS_ALLOWABLE')

    def test_hibrit_lule_izni_servis_basamagi_degil(self, client):
        """Hibrit: /calculate (test_hibrit_bakir_lule_izin_723_ve_uyari gövdesi)
        nozzle_material=carbon_carbon → throat_thermal.allowable_temperature_K
        == İZİN 1920; servis 2273 DEĞİL. Ölçüldü: boğaz cidarı 1885,88 K, marj
        +34,12 K, SAFE (üç ağaçta bit-aynı). Yama satırı servis basamağını
        okusa izin 2273 ve marj +387 K yayımlanır, hüküm aynı kalır — bu yüzden
        izin ve marj ölçülür, hüküm değil."""
        _, tl = self._merdiven('carbon_carbon', (1920.0, 2273.0, 2400.0, 3900.0))
        govde = {'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
                 'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
                 'oxidizer_type': 'n2o', 'expansion_ratio': 4.0,
                 'nozzle_type': 'conical', 'chamber_material': 'steel_4130',
                 'wall_thickness': 5, 'nozzle_material': 'carbon_carbon'}
        r = _q(client.post, '/calculate', json=govde, headers=H)
        assert r.status_code == 200
        g = r.get_json()
        assert 'option_not_recognised' not in json.dumps(g)
        nma = g['motor']['nozzle_material_analysis']
        assert nma['material'] == 'carbon_carbon'
        tt = nma['throat_thermal']
        assert tt['status'] == 'analyzed'
        assert tt['allowable_temperature_K'] == tl['allowable_K'] == 1920.0
        assert tt['allowable_temperature_K'] not in (tl['service_K'], tl['clamp_K'],
                                                     tl['melting_K'])
        assert tt['temperature_margin_K'] == pytest.approx(
            1920.0 - tt['throat_wall_temperature_K'])

    @motor_yamasi
    def test_kati_lule_izni_ham_allowable_temperature_degil(self, client):
        """Katı: nozzle_material=copper (uç kabul eder) → izin 723 (merdiven:
        min(allowable_temperature 1000, max_service_temp 723)); HAM
        allowable_temperature 1000 ve klamp / erime 1358 DEĞİL. Ölçüldü
        (lule_tum_{once,sonra}.json): ÖNCE 1000 → SONRA 723, marj −2594,9 →
        −2871,9 K, hüküm EXCEEDS_ALLOWABLE iki ağaçta. Yama satırı ham alanı
        okusa (graphite / tungsten / carbon_carbon'da izinle aynı sayı) 1000
        çıkar."""
        rec, tl = self._merdiven('copper', (723.0, 723.0, 1358.0, 1358.0))
        assert rec['allowable_temperature'] == 1000.0
        r = _q(client.post, '/calculate_solid',
               json=dict(KATI_GOVDE, nozzle_material='copper'), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        g = r.get_json()
        assert 'option_not_recognised' not in json.dumps(g)
        nma = g['nozzle_material_analysis']
        assert nma['status'] == 'analyzed' and nma['material'] == 'copper'
        assert nma['allowable_temperature_k'] == tl['allowable_K'] == 723.0
        assert nma['allowable_temperature_k'] not in (rec['allowable_temperature'],
                                                      tl['clamp_K'], tl['melting_K'])
        t_aw = nma['adiabatic_wall_temperature_k']
        assert nma['thermal_margin_k'] == pytest.approx(723.0 - t_aw, abs=0.11)

    @motor_yamasi
    def test_sivi_kunye_ham_allowable_temperature_degil(self, client):
        """Sıvı: arayüz anahtarı copper_c101 (liquid.html seçeneği → materials_db
        copper), ablatif → künye material_service_limit_K == İZİN 723; HAM
        allowable_temperature 1000 ve klamp / erime 1358 DEĞİL (steel_304
        bekçisi ham allowable_temperature okumasını göremez: orada 1073 =
        izin). Ölçüldü: ÖNCE 1358 → SONRA 723 (Sunum 2 §3 [4. tur] satırı);
        ısı-yutucu satırı copper'da NOT_MODELLED (iki ağaçta)."""
        rec, tl = self._merdiven('copper', (723.0, 723.0, 1358.0, 1358.0))
        govde = dict(SIVI_ABLATIF_STEEL_304, chamber_material='copper_c101')
        r = _q(client.post, '/calculate_liquid', json=govde, headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        g = r.get_json()
        assert 'warn.liquid.option_not_recognised' not in json.dumps(g)
        tp = g['thermal_protection']
        assert tp['material_service_limit_K'] == tl['allowable_K'] == 723.0
        assert tp['material_service_limit_K'] not in (rec['allowable_temperature'],
                                                      tl['clamp_K'], tl['melting_K'])
        assert tp['material_temperature_ladder_K'] == {
            'allowable_K': 723.0, 'service_K': 723.0, 'melting_K': 1358.0}


# ---------------------------------------------------------------------------
# 6. tur (yeniden denetim-5, öneri R3, 7 Eki 2026): sıvı künye ve ısı-yutucu
# satırlarının RADYATİF yarısı. Sunum 2 §3 [4. tur] künye satırı "ablatif VE
# radyatif künye; aynı sayı" der; ablatif yarısı V8 / S1d / R8 bekçileriyle
# korunuyordu, radyatif yarısı korunmuyordu: denetçinin R3 mutasyonu (yama
# satırı soğutma tipine göre ayrılır, radyatifte eski max_service_temperature
# = erime yayımlanır) a1 + a2'de YEŞİL kaldı. Gövde a2 SIVI_ABLATIF_STEEL_304,
# yalnız cooling_type='radiative'. Ölçüldü (sart6/olcum/s6_{main,yamasiz,
# birlesik}.json 'steel_304/radiative'): künye 1673 → 1673 → 1073 (yalnız
# motor yaması); ısı-yutucu 1143 K / 0,097649 s → 1073 K / 0,078666 s →
# 1073 K / 0,078666 s (dal kodu; yamasız ağaçta da koşar).
# ---------------------------------------------------------------------------
#: steel_304 → ss_304 merdiveni (izin < servis < erime; üç basamak ayrık —
#: basamak karışması bu malzemede görünür).
SIVI_STEEL_304_MERDIVEN_K = {'allowable_K': 1073.0, 'service_K': 1143.0,
                             'melting_K': 1673.0}
#: Radyatif ısı-yutucu sınıra süre (ölçüldü, birleşik ağaç; yamadan bağımsız).
SIVI_RADYATIF_STEEL_304_SINIRA_SURE_S = 0.078666


@pytest.fixture(scope='module')
def sivi_steel_304_radyatif(client):
    govde = dict(SIVI_ABLATIF_STEEL_304, cooling_type='radiative')
    r = _q(client.post, '/calculate_liquid', json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    g = r.get_json()
    assert 'warn.liquid.option_not_recognised' not in json.dumps(g), \
        'steel_304 arayüz anahtarı reddedildi — bekçi yanlış malzemeyi ölçerdi'
    return g


class TestSiviRadyatifIzinBasamagi:

    @motor_yamasi
    def test_sivi_radyatif_kunye_izin_basamagi(self, sivi_steel_304_radyatif):
        """R3: radyatif künye == İZİN basamağı (1073), servis 1143 ve erime
        1673 DEĞİL; merdiven ve dayanak ablatiftekiyle aynı."""
        from hrma.data.materials_db import get_material, temperature_limits
        tl = temperature_limits(get_material('ss_304'))
        merd = SIVI_STEEL_304_MERDIVEN_K
        assert {k: tl[k] for k in merd} == merd
        tp = sivi_steel_304_radyatif['thermal_protection']
        assert tp['material_temperature_ladder_K'] == merd
        assert tp['material_service_limit_K'] == merd['allowable_K']
        assert tp['material_service_limit_K'] not in (merd['service_K'],
                                                      merd['melting_K'])
        assert 'allowable_K' in tp['material_service_limit_basis']

    def test_sivi_radyatif_isi_yutucu_izin_basamagi(self, sivi_steel_304_radyatif):
        """Radyatif çıplak cidar (ısı-yutucu) sınırı == İZİN basamağı 1073 K
        (servis 1143 DEĞİL), sınıra süre 0,078666 s (ÖNCE 0,097649 s)."""
        merd = SIVI_STEEL_304_MERDIVEN_K
        wth = sivi_steel_304_radyatif['thermal_protection'][
            'passive_thermal_protection']['wall_temperature_history']
        assert wth['status'] == 'modelled'
        assert wth['wall_material'] == 'ss_304'
        assert wth['max_service_temp_K'] == merd['allowable_K']
        assert wth['melting_point_K'] == merd['melting_K']
        assert wth['time_to_limit_s'] == pytest.approx(
            SIVI_RADYATIF_STEEL_304_SINIRA_SURE_S, rel=1e-3)
        assert wth['time_to_limit_s'] < wth['time_to_melting_s']


# ---------------------------------------------------------------------------
# 7. tur (yeniden denetim-6 Ş2) — ISI-YUTUCU SINIR PENCERESİ: HÜKÜM DÖNER.
# Hibrit kamara steel_304 (arayüz seçeneği → ss_304), a2 hibrit gövdesi,
# yanma 20 s: iç cidarın son sıcaklığı 1085,23 K = [1073, 1143) penceresinde.
# ÖNCE (servis 1143 K) exceeds_limit False / time_to_limit null; SONRA (İZİN
# 1073 K) True / 19,5116 s. Kaynak DAL kodu (thermal_protection) — yamasız
# ağaçta da koşar. Denetçinin D3 mutasyonu (motor ısı-yutucu bloğunda
# yayımlanan sınırı servis basamağından okumak) burada KIRMIZI olmalı:
# yanıt 1143 yayımlar ama süre 1073'e göre kalır (kendi içinde tutarsız).
# ---------------------------------------------------------------------------
#: a2 hibrit gövdesi (TestM2BasamakVeHamAlanAyrimi gövdesinin kamara/lüle
#: alanları hariç aynısı; denetçi sonda_d6.py HIB).
HIBRIT_A2_GOVDE = {'motor_type': 'hybrid', 'thrust': 5000,
                   'chamber_pressure': 20, 'of_ratio': 2.5,
                   'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
                   'expansion_ratio': 4.0, 'nozzle_type': 'conical',
                   'wall_thickness': 5}
#: Pencere vakasının yanma süresi [s] ve ölçülen sınıra süre [s]
#: (sart7/olcum/s7_*.json 'pencere' hib:steel_304:20; denetim-6 sonda_d6).
#: 9. tur (yeniden denetim-8 Ş2; ana model izni ADIYLA, 12 Eki): B16
#: (main 3c774b6b, N₂O giriş entalpisi; T_c 1834,45 K) sonrası 20 s'de iç
#: cidar 1063,77 K — pencerenin ALTINDA. Çapa birleşik ağaçta yeniden
#: ölçüldü (sart9/olcum/s9_S.json hib steel_304:22): T_iç 1089,68 K
#: (kenarlara 16,68 / 53,32 K), sınıra süre 21,2604 s; rel 1e-3 AYNEN.
#: v3.0.1 (21 Eki): iki değişiklik cidarı ısıttı ve 22 s vakası pencereden
#: çıktı (a367de3d2'de T_iç 22 s'de pencerenin üstündeydi; B7 sonrası
#: 1602,97 K): (1) tane zarfı kamara çapını son port çapına indirdi (eski
#: 1,5 × D_son), (2) B7 — bu gövde O/F 2,5, dengeye katı karbon C(gr) girdi,
#: T_c 1834 → 2037 K. Pencere birleşik main'de yanma süresi taranarak
#: yeniden ölçüldü (4 s 1030,70 K; 4,5 s 1064,35 K; 5 s 1095,99 K; 5,5 s
#: 1125,80 K; 6 s 1153,93 K): 5 s'de T_iç 1095,99 K (kenarlara 22,99 /
#: 47,01 K), sınıra süre 4,7084 s; rel 1e-3 AYNEN. Bekçinin özü
#: (yayımlanan sınır İZİN 1073, servis 1143 DEĞİL) değişmedi.
HIBRIT_PENCERE_YANMA_S = 5
HIBRIT_STEEL_304_PENCERE_SINIRA_SURE_S = 4.7084
#: /api/thermal-protection ısı-yutucu çapası (denetim-6 Ş1 a) ve ss_304
#: 13 s vakasının ölçülen sınıra süresi [s].
KORUMA_ISI_YUTUCU_CAPA = {'mode': 'heat_sink', 'h_gas_W_m2K': 500,
                          'T_recovery_K': 3000, 'wall_thickness_m': 0.005}
KORUMA_SS_304_PENCERE_YANMA_S = 13
KORUMA_SS_304_PENCERE_SINIRA_SURE_S = 12.0406


@pytest.fixture(scope='module')
def hibrit_steel_304_pencere(client):
    r = _q(client.post, '/calculate',
           json=dict(HIBRIT_A2_GOVDE, chamber_material='steel_304',
                     burn_time=HIBRIT_PENCERE_YANMA_S), headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    g = r.get_json()
    assert 'option_not_recognised' not in json.dumps(g)
    return g['motor']


class TestIsiYutucuSinirPenceresi:

    def test_hibrit_steel_304_20s_hukum_doner(self, hibrit_steel_304_pencere):
        """max_service_temp_K == İZİN 1073 (servis 1143 DEĞİL); iç cidar
        pencerede; exceeds_limit True ve sınıra süre ≈ 4,7084 s (v3.0.1
        geometrisi ve C(gr) dengesiyle 5 s vakası; 21 Eki)."""
        merd = SIVI_STEEL_304_MERDIVEN_K
        w = hibrit_steel_304_pencere['thermal_protection'][
            'wall_temperature_history']
        assert w['max_service_temp_K'] == merd['allowable_K']
        assert w['max_service_temp_K'] != merd['service_K']
        assert merd['allowable_K'] <= w['T_inner_final_K'] < merd['service_K']
        assert w['exceeds_limit'] is True
        assert w['time_to_limit_s'] == pytest.approx(
            HIBRIT_STEEL_304_PENCERE_SINIRA_SURE_S, rel=1e-3)
        # Kendi içinde tutarlılık: süre yayımlanan sınırın süresidir.
        assert w['time_to_limit_s'] < HIBRIT_PENCERE_YANMA_S

    def test_koruma_ucu_ss_304_13s_hukum_doner(self, client):
        """/api/thermal-protection heat_sink ss_304 13 s: sınır 1073, aşım
        True, sınıra süre ≈ 12,0406 s (protection_panel.js rozeti EXCEEDED)."""
        merd = SIVI_STEEL_304_MERDIVEN_K
        r = _q(client.post, '/api/thermal-protection',
               json=dict(KORUMA_ISI_YUTUCU_CAPA, wall_material='ss_304',
                         burn_time_s=KORUMA_SS_304_PENCERE_YANMA_S), headers=H)
        assert r.status_code == 200
        j = r.get_json()
        j = j.get('result', j)
        assert j['max_service_temp_K'] == merd['allowable_K']
        assert merd['allowable_K'] <= j['T_inner_K'] < merd['service_K']
        assert j['exceeds_limit'] is True
        assert j['time_to_limit_s'] == pytest.approx(
            KORUMA_SS_304_PENCERE_SINIRA_SURE_S, rel=1e-3)


# ---------------------------------------------------------------------------
# 7. tur — karar §28-24 §3/§4: TERMAL PANEL TEK EŞİK (panel çelişkisi).
# Kart rengi, "Material limits … allowable" satırı ve grafik "Allowable
# limit" çizgisi sunucunun KANONİK izin basamağını
# (safety_analysis.threshold_ladder.allowable_K) okur. Pencere vakalarında
# (cidar 811-1000 K; bakırda 723-1000 K) kart YEŞİL olamaz, izin satırı ve
# çizgi kanonik sayıyı taşır, sunucu aynı yanıtta critical uyarı verir.
# Ters mutasyon: panel ham material_properties.allowable_temperature'a
# dönerse kart YEŞİL, satır 1000 → KIRMIZI.
# ---------------------------------------------------------------------------
THERMAL_PANEL_JS = 'hrma/static/js/panels/thermal_panel.js'
P11_HARNESS = KOK / 'docs' / 'scofield' / 'raw' / 'P11' / 'B4-repro-03.js'
#: Sunum 2 §3 [3.-4. tur] pencere gövdesi (rejeneratif, 10 bar, 0,5 kg/s).
PENCERE_GOVDE = {'chamber_pressure': 10, 'chamber_diameter': 0.1,
                 'chamber_length': 0.5, 'burn_time': 10, 'mdot_total': 0.5,
                 'wall_thickness': 0.005, 'cooling_type': 'regenerative'}
#: (malzeme, oda sıcaklığı [K]) — Sunum 2 §3 [4. tur] HÜKÜM DÖNER satırları.
PENCERE_VAKALARI = (('steel_4130', 1800), ('steel', 1800),
                    ('steel_4340', 1800), ('copper', 2400))
KART_YESIL = '--hd-green'


def _termal_panel_kos(govde):
    cfg = {'panelId': 'thermal', 'dataInline': govde,
           'panelFiles': [THERMAL_PANEL_JS]}
    p = subprocess.run([NODE, str(kanit_gerekli(P11_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       cwd=str(KOK), timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    o = json.loads(p.stdout)
    assert not o.get('error'), o.get('error')
    return o


@needs_node
class TestTermalPanelTekEsik:

    @pytest.mark.parametrize('malzeme,tc', PENCERE_VAKALARI)
    def test_pencere_kart_satir_cizgi_kanonik(self, client, malzeme, tc):
        r = _q(client.post, '/analyze_thermal_safety',
               json=dict(PENCERE_GOVDE, material=malzeme,
                         chamber_temperature=tc), headers=H)
        assert r.status_code == 200
        g = r.get_json()
        ta = g['thermal_analysis']
        sa = ta['safety_analysis']
        izin = sa['threshold_ladder']['allowable_K']
        ham = ta['material_properties']['allowable_temperature']
        tw = ta['wall_analysis']['inner_temperature']
        # Ön koşul: pencere — cidar kanonik ile ham eşik arasında.
        assert izin < tw <= ham, (malzeme, izin, tw, ham)
        kodlar = {(w['code'], w['severity']) for w in sa['warnings']
                  if isinstance(w, dict)}
        assert ('warn.thermal.temp_exceeds_allowable', 'critical') in kodlar
        o = _termal_panel_kos(g)
        h = o['html']
        i = h.find('T_wall inner')
        assert i >= 0
        kart = h[i:i + 400]
        assert KART_YESIL not in kart, f'{malzeme}: kart YEŞİL (çelişki)'
        assert '--hd-orange' in kart or '--hd-red' in kart
        satir = re.search(r'([0-9]+) K allowable', h)
        assert satir and float(satir.group(1)) == izin, (malzeme, satir)
        cizgiler = [s.get('y0') for pl in o['plots']
                    for s in ((pl.get('layout') or {}).get('shapes') or [])]
        assert izin in cizgiler and ham not in cizgiler, cizgiler

    def test_esik_yayimlanmadiysa_ham_alana_dusulmez(self, client):
        """Fail-closed: threshold_ladder yoksa panel ham 1000'i BASMAZ."""
        r = _q(client.post, '/analyze_thermal_safety',
               json=dict(PENCERE_GOVDE, material='steel_4130',
                         chamber_temperature=1800), headers=H)
        g = r.get_json()
        g['thermal_analysis']['safety_analysis'].pop('threshold_ladder')
        o = _termal_panel_kos(g)
        assert '1000 K allowable' not in o['html']
        assert re.search(r'— K allowable', o['html'])


# ---------------------------------------------------------------------------
# 7. tur — karar §28-24 §1 (c) ve §2 (b): OLUMLU HÜKÜM KAPISI.
# Yakınsamamış alan ("sayısal yakınsama sağlanmadı") ya da jenerik gazlı
# profil (γ / MW / c* modül varsayılanı) OLUMLU malzeme-sınırı hükmü
# (exceeds_* = False) üretmez; aşım (True) her durumda kalır.
# ---------------------------------------------------------------------------
GAZ_ALANLARI = ('gamma', 'molecular_weight', 'c_star')
#: Tepe İZİN ALTINDA kalan gerçek vaka: a2 hibrit gövdesi, yanma 0,5 s
#: (sart7/olcum 'fea' hib05 ⟷ hib05_mh0; tepe ≈ 783 / 780 K < 811 K).
KAPI_YANMA_S = 0.5


class TestOlumluHukumKapisiBirim:

    @staticmethod
    def _kapi(**k):
        from hrma.fea.bridge import _olumlu_hukum_kapisi
        return _olumlu_hukum_kapisi(**k)

    def test_yakinsamis_ve_motor_gazi_hukum_verilir(self):
        g = self._kapi(sinir={'exceeds_allowable': False, 'exceeds_melting': False},
                       uzamsal={'hukum': 'converged'},
                       zaman_adimi={'converged': True},
                       axial_profile={'gas_properties_basis': {'assumed_fields': []}})
        assert g['verdict_withheld'] is False and 'exceeds_allowable' not in g

    @pytest.mark.parametrize('uzay,zaman', [('not_converged', True),
                                            ('converged', False),
                                            ('degenerate', True),
                                            (None, True)])
    def test_yakinsamamis_alan_olumlu_hukum_uretmez(self, uzay, zaman):
        from hrma.fea.bridge import VERDICT_WITHHELD_NUMERICAL
        g = self._kapi(sinir={'exceeds_allowable': False, 'exceeds_melting': False},
                       uzamsal={'hukum': uzay}, zaman_adimi={'converged': zaman},
                       axial_profile={'gas_properties_basis': {'assumed_fields': []}})
        assert g['exceeds_allowable'] is None and g['exceeds_melting'] is None
        assert g['verdict_withheld_reasons'] == [VERDICT_WITHHELD_NUMERICAL]

    def test_asim_her_durumda_kalir(self):
        g = self._kapi(sinir={'exceeds_allowable': True, 'exceeds_melting': False},
                       uzamsal={'hukum': 'not_converged'},
                       zaman_adimi={'converged': True}, axial_profile=None)
        assert 'exceeds_allowable' not in g          # True dokunulmaz
        assert g['exceeds_melting'] is None
        assert g['gas_properties_status'] == 'not_declared_by_profile'

    def test_jenerik_gaz_olumlu_hukum_uretmez(self):
        from hrma.fea.bridge import VERDICT_WITHHELD_GAS
        gb = {'assumed_fields': ['gamma'],
              'gamma': {'value': 1.2, 'source': 'module_default'}}
        g = self._kapi(sinir={'exceeds_allowable': False, 'exceeds_melting': False},
                       uzamsal={'hukum': 'converged'},
                       zaman_adimi={'converged': True},
                       axial_profile={'gas_properties_basis': gb})
        assert g['exceeds_allowable'] is None
        assert g['verdict_withheld_reasons'] == [VERDICT_WITHHELD_GAS]
        assert g['inputs_assumed'][0]['field'] == 'gamma'
        assert g['inputs_assumed'][0]['source'] == 'module_default'

    # -- 8. tur (yeniden denetim-7 Ş4 b, R12): KISMİ varsayım ------------
    # Yalnız MW ya da yalnız c* modül varsayılanına düşen profil de olumlu
    # hüküm almaz (eski bekçi yalnız ['gamma'] ve üç alanı birden sınıyordu;
    # denetçinin R12 mutasyonu — kapı yalnız γ'ya bakar — YEŞİL kalıyordu).
    @pytest.mark.parametrize('alan', ['molecular_weight', 'c_star'])
    def test_kismi_varsayim_olumlu_hukum_uretmez(self, alan):
        from hrma.analysis.heat_transfer_analysis import (
            GAS_SOURCE_ASSUMED, GAS_SOURCE_IDEAL, MW_MODULE_DEFAULT_G_MOL)
        from hrma.fea.bridge import VERDICT_WITHHELD_GAS
        kaynak = (GAS_SOURCE_ASSUMED if alan == 'molecular_weight'
                  else GAS_SOURCE_IDEAL)
        deger = MW_MODULE_DEFAULT_G_MOL if alan == 'molecular_weight' else None
        gb = {'assumed_fields': [alan],
              alan: {'value': deger, 'source': kaynak}}
        g = self._kapi(sinir={'exceeds_allowable': False, 'exceeds_melting': False},
                       uzamsal={'hukum': 'converged'},
                       zaman_adimi={'converged': True},
                       axial_profile={'gas_properties_basis': gb})
        assert g['exceeds_allowable'] is None and g['exceeds_melting'] is None
        assert g['verdict_withheld_reasons'] == [VERDICT_WITHHELD_GAS]
        assert [a['field'] for a in g['inputs_assumed']] == [alan]
        assert g['inputs_assumed'][0]['source'] == kaynak

    # -- 8. tur (yeniden denetim-7 Ş1): gaz künyesi YOK ya da OKUNAMIYOR --
    # Blok yoksa h(z)'nin gazı bilinmez; assumed_fields bir alan adı
    # listesi değilse hangi alanın varsayıldığı okunamaz. İkisinde de olumlu
    # hüküm yok, neden 'gas_properties_not_declared' (ADIYLA).
    @pytest.mark.parametrize('profil,durum', [
        (None, 'not_declared_by_profile'),
        ({'x_mm': [0.0]}, 'not_declared_by_profile'),
        ({'gas_properties_basis': {}}, 'declaration_unreadable'),
        ({'gas_properties_basis': {'assumed_fields': 'gamma'}},
         'declaration_unreadable'),
        ({'gas_properties_basis': {'assumed_fields': [1]}},
         'declaration_unreadable')])
    def test_gaz_kunyesi_yoksa_olumlu_hukum_uretmez(self, profil, durum):
        from hrma.fea.bridge import (GAS_STATUS_NOT_DECLARED,
                                     GAS_STATUS_UNREADABLE,
                                     VERDICT_WITHHELD_GAS_UNDECLARED)
        assert durum in (GAS_STATUS_NOT_DECLARED, GAS_STATUS_UNREADABLE)
        g = self._kapi(sinir={'exceeds_allowable': False, 'exceeds_melting': False},
                       uzamsal={'hukum': 'converged'},
                       zaman_adimi={'converged': True}, axial_profile=profil)
        assert g['exceeds_allowable'] is None and g['exceeds_melting'] is None
        assert g['verdict_withheld'] is True
        assert g['verdict_withheld_reasons'] == [VERDICT_WITHHELD_GAS_UNDECLARED]
        assert g['gas_properties_status'] == durum
        assert g['inputs_assumed'] == []

    def test_gaz_kunyesi_yokken_asim_kalir(self):
        """Ş1: kapı yalnız OLUMLU bayrağı geri çeker; aşım (True) AYNEN."""
        g = self._kapi(sinir={'exceeds_allowable': True, 'exceeds_melting': True},
                       uzamsal={'hukum': 'converged'},
                       zaman_adimi={'converged': True}, axial_profile={})
        assert 'exceeds_allowable' not in g and 'exceeds_melting' not in g
        assert g['verdict_withheld'] is True


def _panel_govdesi(motor, tmp_path):
    from tests.test_thermal_fea_panel import _run_panel
    b = _run_panel(tmp_path, build_body=[motor])['bodies'][0]
    assert b['missing'] == []
    return b['body']


def _zincir(client, motor, govde, **ek):
    r1 = _q(client.post, '/api/analysis/wall-profile', json=govde, headers=H)
    assert r1.status_code == 200, r1.get_data(as_text=True)[:300]
    wp = r1.get_json()['wall_profile']
    yuk = {'motor_results': motor, 'axial_profile': wp,
           'ambient_temperature_K': 293.15}
    yuk.update(ek)
    r2 = _q(client.post, '/api/fea/thermal', json=yuk, headers=H)
    assert r2.status_code == 200, r2.get_data(as_text=True)[:300]
    return wp, r2.get_json()['fea']


@pytest.fixture(scope='module')
def kapi_motoru(client):
    r = _q(client.post, '/calculate',
           json=dict(HIBRIT_A2_GOVDE, burn_time=KAPI_YANMA_S), headers=H)
    assert r.status_code == 200
    return r.get_json()['motor']


@app_yamasi
@needs_node
class TestOlumluHukumKapisiUc:

    def test_tepe_izin_alti_yakinsamis_hukum_verilir(self, client, kapi_motoru,
                                                     tmp_path):
        wp, f = _zincir(client, kapi_motoru, _panel_govdesi(kapi_motoru, tmp_path))
        ml = f['material_limits']
        assert wp['gas_properties_basis']['assumed_fields'] == []
        assert f['scalars']['peak_wall_T_K'] < ml['allowable_temperature_K']
        assert f['spatial_convergence']['verdict'] == 'converged'
        assert f['time_step']['converged'] is True
        assert ml['exceeds_allowable'] is False and ml['verdict_withheld'] is False

    def test_zaman_yakinsamadi_olumlu_hukum_yok_ve_panel_etiketi(
            self, client, kapi_motoru, tmp_path):
        from hrma.fea.bridge import VERDICT_WITHHELD_NUMERICAL
        _, f = _zincir(client, kapi_motoru, _panel_govdesi(kapi_motoru, tmp_path),
                       max_halvings=0)
        ml = f['material_limits']
        assert f['scalars']['peak_wall_T_K'] < ml['allowable_temperature_K']
        assert f['time_step']['converged'] is not True
        assert ml['exceeds_allowable'] is None and ml['exceeds_melting'] is None
        assert ml['verdict_withheld_reasons'] == [VERDICT_WITHHELD_NUMERICAL]
        sonuc = TestPanel()._kos(tmp_path, {'fea': f, 'error': None}, dil='tr')
        rozet = sonuc['els']['fea_t_badges']['html']
        assert 'sayısal yakınsama sağlanmadı' in rozet
        assert 'GÜVENLİK HÜKMÜ YOK' in rozet
        assert 'İÇİNDE' not in rozet           # 'İZİN SINIRI … İÇİNDE' yok

    def test_jenerik_gaz_olumlu_hukum_yok(self, client, kapi_motoru, tmp_path):
        from hrma.fea.bridge import VERDICT_WITHHELD_GAS
        govde = {k: v for k, v in _panel_govdesi(kapi_motoru, tmp_path).items()
                 if k not in GAZ_ALANLARI}
        wp, f = _zincir(client, kapi_motoru, govde)
        assert sorted(wp['gas_properties_basis']['assumed_fields']) == sorted(
            GAZ_ALANLARI)
        ml = f['material_limits']
        assert ml['exceeds_allowable'] is None
        assert VERDICT_WITHHELD_GAS in ml['verdict_withheld_reasons']
        assert sorted(a['field'] for a in ml['inputs_assumed']) == sorted(
            GAZ_ALANLARI)
        sonuc = TestPanel()._kos(tmp_path, {'fea': f, 'error': None}, dil='tr')
        rozet = sonuc['els']['fea_t_badges']['html']
        assert 'gaz özellikleri varsayıldı' in rozet and 'İÇİNDE' not in rozet

    def test_dorduncu_seviye_yalniz_istekle(self, client, kapi_motoru, tmp_path):
        """§1 (b): spatial_levels verilmezse 3 seviye; 4. seviye yalnız
        istekle (limits.spatial_levels yankısı) — sonuç görüldükten sonra
        otomatik seçim yok. (a): istenen ve yayımlanan ağ AYRI alanlarda;
        tepe, yayımlanan seviyenin tepesi ve geçmişin maksimumudur."""
        govde = _panel_govdesi(kapi_motoru, tmp_path)
        for ek, n in (({}, 3), ({'spatial_levels': 4}, 4)):
            _, f = _zincir(client, kapi_motoru, govde, **ek)
            sc = f['spatial_convergence']
            assert f['limits']['spatial_levels'] == n and len(sc['levels']) == n
            yay = [l for l in sc['levels'] if l['published']]
            assert len(yay) == 1 and yay[0] is sc['levels'][-1]
            assert (f['mesh']['n_axial'], f['mesh']['n_radial']) == (
                yay[0]['n_axial'], yay[0]['n_radial'])
            assert f['limits']['n_axial'] == sc['levels'][0]['n_axial']
            ist = f['meta']['mesh_politikasi']['istenen_mesh']
            assert (ist['n_axial'], ist['n_radial']) == (
                sc['levels'][0]['n_axial'], sc['levels'][0]['n_radial'])
            assert f['scalars']['peak_wall_T_K'] == yay[0]['peak_wall_T_K']
            assert f['scalars']['peak_wall_T_K'] == max(
                f['history']['peak_wall_T_history_K'])
            assert len(f['fields']['temperature_final_K']) == f['mesh']['n_nodes']


# ---------------------------------------------------------------------------
# 7. tur — karar §28-24 §2 (a) ve (c): MOTORUN GAZI uçtan uca.
# Panel gövdesi (gerçek buildWallProfileBody) motorun γ / MW / c*'ını AYNEN
# taşır; profil künyesi üçünü 'supplied_by_caller' yazar; gaz değişince h(z)
# ve FEA tepesi değişir; aynı gövde tekrarlanınca sonuç BİT-AYNI döner
# (önbellek bayat sonuç döndürmez).
# ---------------------------------------------------------------------------
#: Gaz değişimi deneyinin γ çarpanı (yalnız deney; sayı yayımlanmaz).
GAZ_DENEY_GAMMA_CARPANI = 1.05


@app_yamasi
@needs_node
class TestMotorGaziUctanUca:

    def test_govde_motorun_gazi_ve_kunye(self, client, kapi_motoru, tmp_path):
        govde = _panel_govdesi(kapi_motoru, tmp_path)
        for k in GAZ_ALANLARI:
            assert govde[k] == kapi_motoru[k], k
        r = _q(client.post, '/api/analysis/wall-profile', json=govde, headers=H)
        gb = r.get_json()['wall_profile']['gas_properties_basis']
        for k in GAZ_ALANLARI:
            assert gb[k]['source'] == 'supplied_by_caller', k
            assert gb[k]['value'] == pytest.approx(kapi_motoru[k], rel=1e-12), k

    def test_gaz_degisince_sonuc_degisir_tekrarda_bit_ayni(
            self, client, kapi_motoru, tmp_path):
        govde = _panel_govdesi(kapi_motoru, tmp_path)
        wp1, f1 = _zincir(client, kapi_motoru, govde)
        degisik = dict(govde, gamma=govde['gamma'] * GAZ_DENEY_GAMMA_CARPANI)
        wp2, f2 = _zincir(client, kapi_motoru, degisik)
        wp3, f3 = _zincir(client, kapi_motoru, govde)
        assert wp2['h_g'] != wp1['h_g']
        assert f2['scalars']['peak_wall_T_K'] != f1['scalars']['peak_wall_T_K']
        assert wp3['h_g'] == wp1['h_g']
        assert f3['scalars']['peak_wall_T_K'] == f1['scalars']['peak_wall_T_K']
        assert f3['fields']['temperature_final_K'] == f1['fields'][
            'temperature_final_K']


# ---------------------------------------------------------------------------
# 8. tur — yeniden denetim-7 Ş1 (gaz kapısı fail-open), Ş2 (beyan kanalı),
# Ş4 (R10 / R11 bekçi açıkları) ve karar §28-31 Ş5 (a)/(b) (diğer
# tüketiciler tek eşiğe). Mevcut düğümlere ve toleranslara dokunulmadı.
# ---------------------------------------------------------------------------
GAZ_KUNYESI = 'gas_properties_basis'


def _fea_profilden(client, motor, wp):
    """Verilen h(z) profiliyle /api/fea/thermal (profil ELLE değiştirilmiş
    olabilir — örn. künye silinmiş)."""
    r = _q(client.post, '/api/fea/thermal',
           json={'motor_results': motor, 'axial_profile': wp,
                 'ambient_temperature_K': 293.15}, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['fea']


@app_yamasi
@needs_node
class TestGazKunyesiYokUc:
    """Ş1 (a): denetçinin sondası (probe_d7.py 'fea_jenerik_beyan_silinmis')
    — hibrit 0,5 s, gazsız gövdeden wall-profile (jenerik γ / MW / c*),
    profilin gaz künyesi silinerek /api/fea/thermal. ÖNCE: tepe 807,09 K <
    izin 811 K → exceeds_allowable false ("İZİN SINIRI İÇİNDE"). SONRA:
    verdict_withheld True, exceeds_* null, neden ADIYLA."""

    def _beyansiz(self, client, motor, govde):
        r = _q(client.post, '/api/analysis/wall-profile', json=govde, headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        wp = r.get_json()['wall_profile']
        assert GAZ_KUNYESI in wp
        return wp, _fea_profilden(
            client, motor, {k: v for k, v in wp.items() if k != GAZ_KUNYESI})

    def _kapali(self, f):
        from hrma.fea.bridge import (GAS_STATUS_NOT_DECLARED,
                                     VERDICT_WITHHELD_GAS_UNDECLARED)
        ml = f['material_limits']
        # Kapı olmasa olumlu hüküm verilecek vaka: tepe izin ALTINDA ve alan
        # iki eksende de yakınsamış (geri çekme nedeni yalnız künye).
        assert f['scalars']['peak_wall_T_K'] < ml['allowable_temperature_K']
        assert f['spatial_convergence']['verdict'] == 'converged'
        assert f['time_step']['converged'] is True
        assert ml['verdict_withheld'] is True
        assert ml['exceeds_allowable'] is None
        assert ml['exceeds_melting'] is None
        assert ml['verdict_withheld_reasons'] == [VERDICT_WITHHELD_GAS_UNDECLARED]
        assert ml['gas_properties_status'] == GAS_STATUS_NOT_DECLARED
        return ml

    def test_jenerik_gazli_profil_kunyesi_silinince_hukum_yok(
            self, client, kapi_motoru, tmp_path):
        govde = {k: v for k, v in _panel_govdesi(kapi_motoru, tmp_path).items()
                 if k not in GAZ_ALANLARI}
        wp, f = self._beyansiz(client, kapi_motoru, govde)
        assert sorted(wp[GAZ_KUNYESI]['assumed_fields']) == sorted(GAZ_ALANLARI)
        self._kapali(f)
        sonuc = TestPanel()._kos(tmp_path, {'fea': f, 'error': None}, dil='tr')
        rozet = sonuc['els']['fea_t_badges']['html']
        assert 'GÜVENLİK HÜKMÜ YOK' in rozet
        assert 'h(z) profili gaz özelliklerini beyan etmiyor' in rozet
        assert 'İÇİNDE' not in rozet

    def test_motor_gazli_profil_kunyesi_silinince_de_hukum_yok(
            self, client, kapi_motoru, tmp_path):
        """Künyesiz profilin gazı motorun gazı OLSA da köprü bunu bilemez."""
        wp, f = self._beyansiz(client, kapi_motoru,
                               _panel_govdesi(kapi_motoru, tmp_path))
        assert wp[GAZ_KUNYESI]['assumed_fields'] == []
        self._kapali(f)

    def test_panel_yolu_kunyeli_profil_olumlu_hukum_alir(
            self, client, kapi_motoru, tmp_path):
        """Ş1 (c): künyeli profilde (panel yolu) kapı AÇIK kalır; girdi
        künyesi gazın durumunu yazar."""
        wp, f = _zincir(client, kapi_motoru,
                        _panel_govdesi(kapi_motoru, tmp_path))
        ml = f['material_limits']
        assert ml['exceeds_allowable'] is False and ml['verdict_withheld'] is False
        assert ml['gas_properties_status'] == 'all_from_caller'
        gb = f['meta']['girdiler']['h_profili']['gaz_beyani']
        assert gb['status'] == 'all_from_caller' and gb['assumed_fields'] == []

    # -- 9. tur (yeniden denetim-8 Ş5): GİRDİ KÜNYESİ gaz_beyani bekçisi --
    # Yayımlanan meta.girdiler.h_profili.gaz_beyani yaprağı kapıyla AYNI
    # okuyucudan gelir; yalnız künyeli vaka ('all_from_caller') sınanıyordu
    # ve denetçinin N5 mutasyonu (durum hep 'all_from_caller') YEŞİL
    # kalıyordu. Künyesiz, kısmi varsayımlı ve okunamayan künyede yaprak
    # durumu ADIYLA yazmalı.
    def test_kunyesiz_profilde_girdi_kunyesi_beyan_yok(
            self, client, kapi_motoru, tmp_path):
        from hrma.fea.bridge import GAS_STATUS_NOT_DECLARED
        panel = _panel_govdesi(kapi_motoru, tmp_path)
        jenerik = {k: v for k, v in panel.items() if k not in GAZ_ALANLARI}
        for govde in (jenerik, panel):
            _, f = self._beyansiz(client, kapi_motoru, govde)
            gb = f['meta']['girdiler']['h_profili']['gaz_beyani']
            assert gb['status'] == GAS_STATUS_NOT_DECLARED
            assert gb['assumed_fields'] == []
            assert gb['status'] == f['material_limits']['gas_properties_status']

    @pytest.mark.parametrize('alan', GAZ_ALANLARI)
    def test_kismi_varsayim_uc_girdi_kunyesi(self, client, kapi_motoru,
                                             tmp_path, alan):
        """Gövdeden TEK gaz alanı çıkarılır: profil künyesi o alanı varsayar;
        girdi künyesi 'assumed' + [alan], kapı olumlu hüküm vermez."""
        from hrma.fea.bridge import GAS_STATUS_ASSUMED, VERDICT_WITHHELD_GAS
        govde = {k: v for k, v in _panel_govdesi(kapi_motoru, tmp_path).items()
                 if k != alan}
        wp, f = _zincir(client, kapi_motoru, govde)
        assert wp[GAZ_KUNYESI]['assumed_fields'] == [alan]
        gb = f['meta']['girdiler']['h_profili']['gaz_beyani']
        assert gb['status'] == GAS_STATUS_ASSUMED
        assert gb['assumed_fields'] == [alan]
        ml = f['material_limits']
        assert ml['gas_properties_status'] == GAS_STATUS_ASSUMED
        assert VERDICT_WITHHELD_GAS in ml['verdict_withheld_reasons']
        assert ml['exceeds_allowable'] is not False
        assert ml['exceeds_melting'] is not False

    @pytest.mark.parametrize('kunye,durum', [
        ({}, 'declaration_unreadable'),
        ({'assumed_fields': None}, 'declaration_unreadable'),
        ({'assumed_fields': 'gamma'}, 'declaration_unreadable'),
        ({'assumed_fields': [1]}, 'declaration_unreadable'),
        (['gamma'], 'not_declared_by_profile'),
        ('all_from_caller', 'not_declared_by_profile')])
    def test_okunamayan_kunye_birim_girdi_kunyesi(self, client, kapi_motoru,
                                                  tmp_path, kunye, durum):
        """Birim düzey: extract_thermal_inputs künyeyi okur ve durumunu
        _basis.h_profili.gaz_beyani'ye yazar (kapının okuyucusu ile AYNI)."""
        from hrma.fea import bridge
        assert durum in bridge.GAS_STATUSES_UNDECLARED
        r = _q(client.post, '/api/analysis/wall-profile',
               json=_panel_govdesi(kapi_motoru, tmp_path), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        wp = r.get_json()['wall_profile']
        saglam = bridge.extract_thermal_inputs(kapi_motoru, wp)
        assert saglam['_basis']['h_profili']['gaz_beyani']['status'] == (
            bridge.GAS_STATUS_ALL_FROM_CALLER)
        g = bridge.extract_thermal_inputs(kapi_motoru,
                                          dict(wp, **{GAZ_KUNYESI: kunye}))
        gb = g['_basis']['h_profili']['gaz_beyani']
        assert gb['status'] == durum
        assert gb['assumed_fields'] == []


class TestGazKunyesiTuketilenBeyan:
    """Ş2: gas_properties_basis köprüde OKUNUP YARGILANIR → beyan kanalında
    'consumed_by_solver' altında durur, 'supplied_by_caller' (= "çözücünün
    OKUMADIĞI") altında DEĞİL. Uç katmanının listesi köprününkinin ta
    kendisidir (``is``)."""

    def test_liste_ve_cumle_gaz_kunyesini_sayar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma import app as app_mod
        from hrma.fea import bridge
        assert GAZ_KUNYESI in bridge.THERMAL_PROFILE_CONSUMED_KEYS
        assert (app_mod._FEA_PROFILE_CONSUMED_KEYS
                is bridge.THERMAL_PROFILE_CONSUMED_KEYS)
        assert GAZ_KUNYESI in bridge.THERMAL_PROFILE_CONSUMED_BASIS
        assert 'gas_properties_not_declared' in bridge.THERMAL_PROFILE_CONSUMED_BASIS
        beyan = app_mod._fea_profil_beyanlari(
            {'x_mm': [0.0, 1.0], 'h_g': [1.0, 1.0], 'T_recovery': [1.0, 1.0],
             GAZ_KUNYESI: {'assumed_fields': []}, 'source': 'x'})
        assert GAZ_KUNYESI in beyan['consumed_by_solver']
        assert GAZ_KUNYESI not in beyan['supplied_by_caller']

    @app_yamasi
    @needs_node
    def test_uc_yaniti_gaz_kunyesini_tuketilen_basar(self, client, kapi_motoru,
                                                    tmp_path):
        _, f = _zincir(client, kapi_motoru, _panel_govdesi(kapi_motoru, tmp_path))
        beyan = f['axial_profile_declarations']
        assert GAZ_KUNYESI in beyan['consumed_by_solver']
        assert GAZ_KUNYESI not in beyan['supplied_by_caller']
        assert GAZ_KUNYESI in beyan['_basis']


#: Ş4 (a) / R10 — radyasyon dengesi sınırının İZİN ve SERVİS basamaklarını
#: AYIRT EDEN malzemeler (allowable_K != service_K). ss_316 arayüzün
#: radiation_material listesinde; carbon_carbon RADIATION_EXTENSION_MATERIALS
#: tablosundan çözülür (tablo sınırı merkezi kaydın izin basamağına eşit).
#: Mevcut a1 bekçisi yalnız allowable_K == service_K olan malzemeleri
#: (4130 / 4340 / steel / copper) ölçtüğü için iki basamağı ayırt edemiyordu.
RADYASYON_AYIRT_EDEN = ('ss_316', 'carbon_carbon')
#: Uç çağrısının girdisi (denetim-7 rad2 çapası: h 200 W/m²K, T_rec 1200 K).
RADYASYON_CAPA = {'mode': 'radiation_equilibrium', 'h_gas_W_m2K': 200,
                  'T_recovery_K': 1200}


class TestRadyasyonDengesiIzinServisAyrimi:

    @pytest.mark.parametrize('malz', RADYASYON_AYIRT_EDEN)
    def test_uc_siniri_izin_basamagi_servis_degil(self, client, malz):
        from hrma.data.materials_db import temperature_limits
        tl = temperature_limits(malz)
        assert tl['allowable_K'] != tl['service_K']      # ön şart: ayrık
        r = _q(client.post, '/api/thermal-protection',
               json=dict(RADYASYON_CAPA, material=malz), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        j = j.get('result', j)
        assert j['service_limit_K'] == tl['allowable_K']
        assert j['service_limit_K'] != tl['service_K']
        assert j['margin_K'] == pytest.approx(tl['allowable_K'] - j['T_wall_eq_K'])
        assert j['within_limit'] is (j['T_wall_eq_K'] <= tl['allowable_K'])


@app_yamasi
@needs_node
class TestKatiMotorGazSabitiKunyesi:
    """Ş4 (isteğe bağlı) / R11: katı motor MW yayımlamaz; panel gövdesi gaz
    sabitini taşır, MW ondan TÜRETİLİR. Künye bunu 'supplied_by_caller'
    diye yazarsa (R11) yalan olur."""

    def test_kati_mw_kaynagi_turetilmis(self, client, motorlar, tmp_path):
        from hrma.analysis.heat_transfer_analysis import (GAS_SOURCE_DERIVED,
                                                          GAS_SOURCE_SUPPLIED)
        r = _q(client.post, '/api/analysis/wall-profile',
               json=_panel_govdesi(motorlar['kati'], tmp_path), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        gb = r.get_json()['wall_profile'][GAZ_KUNYESI]
        assert gb['molecular_weight']['source'] == GAS_SOURCE_DERIVED
        assert gb['gamma']['source'] == GAS_SOURCE_SUPPLIED
        assert gb['assumed_fields'] == []


#: Ş5 (a) — /analyze_safety termal kolu: seçilen malzemenin sınırı kanonik
#: İZİN basamağı. Cidar sıcaklığı sözleşme yolundan (motor_data
#: wall_temperature_hot/cold) verilir; değerler izin ile servis basamağı
#: ARASINDA (pencere): ÖNCE katsayı servis/T > 1, SONRA izin/T < 1.
GUVENLIK_PENCERE_CIDAR_K = {'ss_304': 1100.0, 'ss_316': 1100.0,
                            'carbon_carbon': 2000.0}
GUVENLIK_TERMAL_GOVDE = {'chamber_pressure': 70.0, 'chamber_diameter': 0.12,
                         'wall_thickness': 0.003, 'chamber_temperature': 3000.0,
                         'burn_time': 10.0}
#: 9. tur (yeniden denetim-8 Ş4) — ham allowable_temperature'ı kanonik İZİN
#: basamağından AYRIŞAN kayıtlar (materials_db; ölçüldü: 1000 / 1000 / 1073 /
#: 1000 ⟷ 811 / 811 / 811 / 723). Ham max_service_temp'i ayrışanlar
#: GUVENLIK_PENCERE_CIDAR_K'nın anahtarlarıdır (ss_304 / ss_316 /
#: carbon_carbon).
HAM_IZIN_AYRISAN_KAYITLAR = ('steel_4130', 'steel_4340', 'steel', 'copper')


class TestGuvenlikTermalKatsayiTekEsik:

    @pytest.mark.parametrize('malz', sorted(GUVENLIK_PENCERE_CIDAR_K))
    def test_secilen_sinir_izin_basamagi(self, malz):
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        from hrma.data.materials_db import temperature_limits
        tl = temperature_limits(malz)
        sicak = GUVENLIK_PENCERE_CIDAR_K[malz]
        assert tl['allowable_K'] <= sicak < tl['service_K']   # pencere
        with contextlib.redirect_stdout(io.StringIO()):
            s = SafetyAnalyzer()._analyze_thermal_safety(
                dict(GUVENLIK_TERMAL_GOVDE, wall_temperature_hot=sicak,
                     wall_temperature_cold=sicak), malz)
        assert s['material_max_service_temp_k'] == tl['allowable_K']
        assert s['material_thermal_safety_factor'] == pytest.approx(
            tl['allowable_K'] / sicak, rel=1e-12)
        assert s['material_thermal_safety_factor'] < 1.0
        assert s['material_recommendation'] != 'Selected material acceptable'

    # -- 9. tur (yeniden denetim-8 Ş4, N7 / R10 sınıfı) --------------------
    # Yukarıdaki düğüm yalnız allowable_temperature = allowable_K olan
    # kayıtları (ss_304 / ss_316 / carbon_carbon) ölçtüğü için seçilen sınırı
    # ÖBÜR ham alandan (allowable_temperature) okuyan mutasyonu ayırt
    # edemiyordu. Bütün kayıtlar taranır; iki ham alanın ayrıştığı kayıtlar
    # (en az HAM_IZIN_AYRISAN_KAYITLAR) kapsamda olmalı. Cidar sıcaklığı
    # kaydın kendi izin basamağıdır (yeni sayı yok; sınır alanı sıcaklıktan
    # bağımsızdır, katsayı izin/T = 1).
    def test_ham_alan_ayrisan_kayitlarda_izin_basamagi(self):
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        from hrma.data.materials_db import MATERIALS, temperature_limits
        ayrisan = {m for m in MATERIALS
                   if MATERIALS[m].get('allowable_temperature')
                   != temperature_limits(m)['allowable_K']}
        assert set(HAM_IZIN_AYRISAN_KAYITLAR) <= ayrisan
        hatali = {}
        for malz in sorted(MATERIALS):
            izin = temperature_limits(malz)['allowable_K']
            with contextlib.redirect_stdout(io.StringIO()):
                s = SafetyAnalyzer()._analyze_thermal_safety(
                    dict(GUVENLIK_TERMAL_GOVDE, wall_temperature_hot=izin,
                         wall_temperature_cold=izin), malz)
            if s['material_max_service_temp_k'] != izin:
                hatali[malz] = (s['material_max_service_temp_k'], izin)
        assert hatali == {}


#: Ş5 (b) — ısı akısı şelale grafiği 'Service limit' notu: kanonik İZİN
#: basamağı. Gövde test_viz_real_fields HEAT_INPUT'unun geometrisi; 0,5 s
#: yanmada cidar 811 / 723 K'yi geçer ama 1000 K'ye ulaşmaz (ÖNCE not YOK,
#: SONRA "Service limit (811 K)" / "(723 K)"); 30 s'de ÖNCE 1000 K yazıyordu.
ISI_AKISI_GRAFIK_GOVDE = {'chamber_length': 0.5, 'nozzle_length': 0.1,
                          'throat_area': 0.001, 'expansion_ratio': 16,
                          'chamber_pressure': 30.0}
ISI_AKISI_YANMA_S = (0.5, 30.0)


class TestIsiAkisiGrafigiTekEsik:

    @pytest.mark.parametrize('malz', ['steel_4130', 'steel_4340', 'steel',
                                      'copper'])
    @pytest.mark.parametrize('yanma', ISI_AKISI_YANMA_S)
    def test_servis_notu_izin_basamagi(self, malz, yanma):
        from hrma.data.materials_db import temperature_limits
        from hrma.visualization.visualization import (
            create_wall_heat_flux_waterfall_plot)
        with contextlib.redirect_stdout(io.StringIO()):
            fig = json.loads(create_wall_heat_flux_waterfall_plot(
                dict(ISI_AKISI_GRAFIK_GOVDE, material=malz, burn_time=yanma)))
        notlar = ' '.join(a.get('text', '')
                          for a in fig['layout'].get('annotations', []))
        sinirlar = re.findall(r'Service limit \((\d+) K\) is exceeded', notlar)
        assert sinirlar == ['%.0f' % temperature_limits(malz)['allowable_K']], notlar

    # -- 9. tur (yeniden denetim-8 Ş4, N8 / R10 sınıfı) --------------------
    # Yukarıdaki düğüm yalnız max_service_temp = allowable_K olan kayıtları
    # ölçtüğü için notu ÖBÜR ham alandan (max_service_temp) okuyan mutasyonu
    # ayırt edemiyordu. İki ham alanın AYRIŞTIĞI kayıtlar (ss_304 / ss_316 /
    # carbon_carbon: izin 1073 / 1073 / 1920 ⟷ servis 1143 / 1143 / 2273 K)
    # uzun yanmada notu İZİN basamağıyla basmalı.
    @staticmethod
    def _servis_notlari(malz, yanma):
        from hrma.visualization.visualization import (
            create_wall_heat_flux_waterfall_plot)
        with contextlib.redirect_stdout(io.StringIO()):
            fig = json.loads(create_wall_heat_flux_waterfall_plot(
                dict(ISI_AKISI_GRAFIK_GOVDE, material=malz, burn_time=yanma)))
        notlar = ' '.join(a.get('text', '')
                          for a in fig['layout'].get('annotations', []))
        return re.findall(r'Service limit \((\d+) K\) is exceeded', notlar), notlar

    @pytest.mark.parametrize('malz', sorted(GUVENLIK_PENCERE_CIDAR_K))
    def test_servis_alani_ayrisan_kayitta_izin_basamagi(self, malz):
        from hrma.data.materials_db import MATERIALS, temperature_limits
        tl = temperature_limits(malz)
        assert MATERIALS[malz]['max_service_temp'] != tl['allowable_K']
        sinirlar, notlar = self._servis_notlari(malz, max(ISI_AKISI_YANMA_S))
        assert sinirlar == ['%.0f' % tl['allowable_K']], notlar

    def test_butun_kayitlarda_not_yalniz_izin_basamagi(self):
        from hrma.data.materials_db import MATERIALS, temperature_limits
        ayrisan = {m for m in MATERIALS
                   if MATERIALS[m].get('max_service_temp')
                   != temperature_limits(m)['allowable_K']}
        assert set(GUVENLIK_PENCERE_CIDAR_K) <= ayrisan
        hatali = {}
        for malz in sorted(MATERIALS):
            izin = '%.0f' % temperature_limits(malz)['allowable_K']
            sinirlar, _ = self._servis_notlari(malz, max(ISI_AKISI_YANMA_S))
            if sinirlar not in ([], [izin]):
                hatali[malz] = (sinirlar, izin)
        assert hatali == {}
