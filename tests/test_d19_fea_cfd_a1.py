"""ÖH Dalga-19 — kulvar fea-cfd, aşama 1/1 bekçileri.

Kapsanan kalemler
-----------------
* **OH-D16-01 / P8B2-09 / OH-D15-03 ([F4])** — yapay rijit-cisim kısıtının
  (u_z = 0) yarattığı gerilme tepesi mesh inceltmesiyle YAKINSAMIYOR ve
  hükmü ele geçiriyordu. Hüküm artık Saint-Venant bandının DIŞINDAN
  alınır; band gövdeyi yutarsa hüküm fail-closed geri çekilir.

  ÖLÇÜLEN (once_f4_hukum.json ⟷ sonra_f4_hukum.json, hibrit 2 kN/30 bar,
  eksenel bölüm 64→512, radyal 24; yayımlanan ``min_safety_factor``):

  | axial_fix | ÖNCE ilk→son | bağıl kayma | SONRA ilk→son | bağıl kayma |
  |---|---|---|---|---|
  | z_min | 41,884 → 41,735 | %0,354 | 41,884 → 41,735 | %0,354 (AYNI) |
  | z_max | 30,650 → 28,287 | **%7,709** | 39,996 → 39,676 | **%0,801** |

  En ince iki tur arası (tol = %1): z_max ÖNCE %2,880 (yakınsamıyor) →
  SONRA %0,034 (yakınsıyor). İki kip arası fark (P8B2-09/OH-D15-03)
  512×24'te 1,4754× → **1,0519×**.

* **P8B1-09 (Fable-D15 ŞART (a))** — yayımlanan kip kendi mesh
  yakınsamasını kanıtlayamadığında hüküm geri çekilmeli. Ürün zinciri
  (``yayimlanan_kip_yakinsamasi`` → ``yayimlanan_kip_yakinsamadi``)
  D18'de kuruldu ama BEKÇİSİ YOKTU: bu dosya toleransı monkeypatch edip
  ``hukum['verildi'] is False`` ölçer.

* **P11B1-05** — sıvı motorda "ODA" ölçü etiketi çözücünün oda boyunu
  değil, 0,8 katını yazıyordu (yakıt çekirdeği yedeği). Sahte sayı.
"""

import contextlib
import io
import json
import math
import pathlib
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

VIZ_JS = KOK / 'hrma/static/js/motor_viz3d.js'
I18N_COMMON_JS = KOK / 'hrma/static/js/i18n_common.js'
NODE = shutil.which('node')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


HIBRIT_GOVDE = {
    'motor_name': 'd19f4bekci', 'thrust': 2000, 'burn_time': 10,
    'of_ratio': 6.0, 'chamber_pressure': 30.0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}


#: ÖH D26 a1 — ŞART P8B2-09: TestF4 katı örnek motoru da kapsar.
#: Aynı istek ``docs/scofield/raw/OH/D26/fea-cfd/a1/_ortak.py`` ölçümüyle
#: birebir aynıdır; ölçülen sayılar oradan okunur.
KATI_GOVDE = {
    'motor_name': 'd26f1-kati', 'propellant_type': 'apcp',
    'grain_type': 'bates', 'chamber_pressure': 40.0, 'thrust': 5000.0,
    'burn_time': 3.0, 'chamber_diameter': 100.0, 'grain_length': 500.0,
    'core_diameter': 30.0, 'expansion_ratio': 8.0}


@pytest.fixture(scope='module')
def kati_motor_sozlugu(client):
    r = _sessiz(client.post, '/calculate_solid', json=KATI_GOVDE)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    md = r.get_json() or {}
    return md.get('motor', md)


@pytest.fixture(scope='module')
def yapisal_girdiler_kati(kati_motor_sozlugu):
    from hrma.fea.bridge import extract_structural_inputs
    gir = _sessiz(extract_structural_inputs, kati_motor_sozlugu)
    assert gir.get('status') == 'ok', gir.get('reason')
    return gir


#: V3.0.5 A2 — ÖLÇÜM KOŞULU AÇIKÇA SABİTLENDİ (28 Eki).
#: TestF4'ün iddiası "yayımlanan SF kısıt tekilliğinden ALINMAZ"; bunu
#: ancak kısıtlı ucun ham tepesi hükmü ele geçirebilen bir geometri
#: sınayabilir. Hibrit varsayılan geometrisi iki kez bilinçli değişti:
#:
#: * a0dca0dc0 (19 Eki, v301/port-kamara): kamara çapı yanma sonu port
#:   çapına iner (kaynaksız 1,5·√N·D_port_son ve 0,8 kırpması söküldü).
#:   Bu gövdede kamara 102,16 → ~68 mm, cidar 21,28 → 14,19 mm. Bekçi
#:   YEŞİL kaldı ama DİŞİNİ yitirdi: hükmü ham düğüm tepesine döndüren
#:   ters mutasyon (D19 öncesi kusur) 14,19 mm cidarda z_max'ı yalnız
#:   %0,286 oynatıyor, kip oranı 1,0578 — iki eşiğin de altında.
#: * 77d64c641 (26 Eki, H-termal): korunan bölgelerle boyutlandırılan cidar
#:   3,61 mm'ye indi (bugün 3,78 mm; H-PANEL 74b55500a c* verimi η=0,89).
#:   Bekçi burada KIRMIZI oldu (256→512 %3,127, kip oranı 1,2573), ama
#:   kırmızının yeri kısıt bandı DEĞİL: hüküm istasyonu boğazda
#:   (z ≈ 0,039 m, bant z > 0,072 m) ve Saint-Venant maskesi tümüyle
#:   kapatıldığında sayılar BİREBİR aynı. Sebep bu sınıfın ``_coz``
#:   aracının skaler sabit P_c yükü (kapalı uç kuvveti yok): ürün 14 Eki'den
#:   beri bu yükü çözmüyor (fea-yuk 2. tur, karar §28-18 (B)); ince cidarda
#:   o yükün yapay net eksenel kuvveti boğazı zorluyor. Aynı ince geometri
#:   ÜRÜNÜN yüküyle (``pressure_load``) yakınsıyor: z_max 256→512 %0,178,
#:   kip oranı 1,0017. Ürün gerilemesi yok.
#:
#: Bu yüzden geometri, mekanizmanın ölçülebildiği port-kamara ÖNCESİ
#: hâline sabitlenir: kamara çapı, cidar ve c* verimi açıkça verilir. Bu üç
#: alanla köprü girdisi af9e4ee37 ağacındaki varsayılan istekle BİT-AYNI
#: (cidar 0,0212843818764787 m, kontur toplamı 2,14223033; ölçüldü,
#: docs/scofield/raw/OH/V305/ci/A2/RAPOR.md). Bu fikstürde:
#:   bantlı ürün   : z_max 256→512 %0,077, kip oranı 1,0748 (YEŞİL)
#:   ham tepe hükmü: z_max 256→512 %3,769, kip oranı 1,4099 (KIRMIZI)
#: yani bekçi D19'un kapattığı kusuru yeniden yakalıyor. Toleranslar
#: (DEFAULT_REFINE_TOL, 1,10) değişmedi.
HIBRIT_GOVDE_SV = dict(HIBRIT_GOVDE,
                       combustion_efficiency=100.0,
                       wall_thickness=21.2843818764787,
                       chamber_diameter_input=102.16083061250222)


@pytest.fixture(scope='module')
def yapisal_girdiler(client):
    from hrma.fea.bridge import extract_structural_inputs
    r = _sessiz(client.post, '/calculate', json=HIBRIT_GOVDE_SV)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    gir = extract_structural_inputs(r.get_json()['motor'])
    assert gir.get('status') == 'ok', gir.get('reason')
    return gir


# ===========================================================================
# OH-D16-01 / P8B2-09 / OH-D15-03 — SAINT-VENANT HÜKÜM BANDI
# ===========================================================================
class TestF4SaintVenantHukumBandi:
    """Hüküm sayısı yapay kısıt tekilliğinden ALINMAZ."""

    def _coz(self, gir, na, nr, kip):
        from hrma.fea.mesh_axisym import build_wall_mesh
        from hrma.fea.structural_axisym import solve_pressure
        t = float(np.max(np.atleast_1d(gir['thickness_m'])))
        m = build_wall_mesh(gir['contour'], t, n_axial=na, n_radial=nr)
        return m, solve_pressure(m, gir['material'],
                                 gir['inner_pressure_pa'], axial_fix=kip)

    def test_maske_kisitlanan_ucu_disliyor(self, yapisal_girdiler):
        """Kısıtlı düğümlerin HİÇBİRİ hüküm alanında olamaz."""
        from hrma.fea.structural_axisym import saint_venant_hukum_maskesi
        m, _ = self._coz(yapisal_girdiler, 128, 24, 'z_max')
        maske, beyan = saint_venant_hukum_maskesi(m, 'z_max')
        assert beyan['gecerli'] is True, beyan
        kisitli = np.asarray(m.z_max_nodes, dtype=int).ravel()
        assert kisitli.size > 0
        assert not maske[kisitli].any(), (
            'kısıtlanan uç kesit düğümleri hüküm alanında kalmış')
        # Karşı uç (serbest) hüküm alanında KALMALI — bant gövdeyi yutmaz.
        serbest = np.asarray(m.z_min_nodes, dtype=int).ravel()
        assert maske[serbest].any(), 'serbest uç da dışlanmış'

    def test_band_boyu_sqrt_Rt_ile_olceklenir(self, yapisal_girdiler):
        """d_SV = 2,5·sqrt(R·t) — boyut analizi ve katsayı kilidi."""
        from hrma.fea.structural_axisym import (SAINT_VENANT_KAT,
                                                saint_venant_hukum_maskesi)
        m, _ = self._coz(yapisal_girdiler, 128, 24, 'z_max')
        _, beyan = saint_venant_hukum_maskesi(m, 'z_max')
        bant = beyan['bantlar'][0]
        beklenen = SAINT_VENANT_KAT * math.sqrt(bant['R_m'] * bant['t_m'])
        assert bant['d_SV_m'] == pytest.approx(beklenen, rel=1e-12)
        assert SAINT_VENANT_KAT == pytest.approx(2.5)

    def test_hukum_sayisi_HAM_tepeden_DEGIL(self, yapisal_girdiler):
        """z_max kipinde ham tepe kısıtta; hüküm ondan gelmemeli."""
        _, res = self._coz(yapisal_girdiler, 512, 24, 'z_max')
        assert res.max_von_mises_hukum is not None
        assert res.max_von_mises_hukum < res.max_von_mises_nodal, (
            'hüküm tepesi ham tepeye eşit — bant hiçbir şey dışlamamış')
        # Yayımlanan SF hüküm tepesinden türer ve alanla BİREBİR tutarlıdır.
        assert res.min_safety_factor == pytest.approx(
            float(res.material_yield) if hasattr(res, 'material_yield')
            else res.meta['malzeme']['yield_Pa'] / res.max_von_mises_hukum,
            rel=1e-12)
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): "hüküm = düğüm SF alanının
        # Saint-Venant maskesi altındaki minimumu" eşitliği artık geçerli
        # değil. Hüküm sayısı ASME BPVC VIII-2 Bölüm 5 / Ek 5-A
        # lineerleştirmesinden geliyor (max(1,5·P_m, P_L+P_b)); ham
        # düğüm tepesi ASME'nin TEPE (F) sınıfıdır, geometrik
        # süreksizlikte yakınsamaz (p ≈ 0,12) ve Tablo 5.6 onu plastik
        # çökme hükmünden dışlar. Alanın minimumu SİLİNMEDİ: ham tepeden
        # türeyen muhafazakâr katsayı olarak yayımlanıyor ve BURADA
        # sınanıyor.
        sf_alan = np.asarray(res.safety_factor_nodal, dtype=float)
        assert float(sf_alan.min()) == pytest.approx(
            res.tepe_emniyet_katsayisi, rel=1e-12)
        assert res.meta['scl_lineerlestirme']['gecerli'] is True
        # HAM tepe SİLİNMEZ (sahte veri yasağının tersi: veri gizlenmez).
        assert res.max_von_mises_nodal == pytest.approx(
            float(np.asarray(res.von_mises_nodal).max()), rel=1e-12)

    def test_z_max_kipi_merdivende_YAKINSIYOR(self, yapisal_girdiler):
        """Onarımın ölçülen sözü: yayımlanan SF artık diverjan değil.

        Taban (once_f4_hukum.json): 64→512 turlarında SF %7,709 kayıyor,
        son iki tur arası %2,880 (tol %1'in üstünde). Onarımdan sonra
        kayma %0,801, son iki tur arası %0,034.
        """
        from hrma.fea.structural_axisym import DEFAULT_REFINE_TOL
        sf = []
        for na in (256, 512):
            _, res = self._coz(yapisal_girdiler, na, 24, 'z_max')
            sf.append(float(res.min_safety_factor))
        bagil = abs(sf[-1] - sf[0]) / sf[0]
        assert bagil < DEFAULT_REFINE_TOL, (
            f'yayımlanan SF en ince iki turda %{bagil * 100:.3f} '
            f'oynuyor (tol %{DEFAULT_REFINE_TOL * 100:.1f}) — kısıt '
            'tekilliği hükmü hâlâ sürüklüyor')

    def test_iki_kip_arasindaki_fark_KAPANDI(self, yapisal_girdiler):
        """P8B2-09 / OH-D15-03: kısıt yeri hükmü 1,4754× oynatıyordu."""
        sf = {}
        for kip in ('z_min', 'z_max'):
            _, res = self._coz(yapisal_girdiler, 512, 24, kip)
            sf[kip] = float(res.min_safety_factor)
        oran = max(sf.values()) / min(sf.values())
        assert oran < 1.10, (
            f'iki axial_fix kipi arasındaki hüküm farkı {oran:.4f}× '
            f'(taban 1,4754×); Saint-Venant bandı yapay tepeyi '
            'dışlamıyor olabilir')

    # --- ÖH D26 a1: KATI FİKSTÜR (ŞART P8B2-09) ------------------------
    # Fable-D20 ŞARTI: "D19 bekçileri (TestF4) katı örnek motoru da
    # kapsasın (bugün yalnız hibrit fikstürü)." Katıda iki kip arasındaki
    # fark hibrittekinin ~11 katıdır ve bu fark mesh inceltmesiyle
    # KAPANMIYOR (ölçüldü, docs/scofield/raw/OH/D26/fea-cfd/a1/once_a1.json
    # §C: n_radial 4 → 8'de kip oranı 1,72604 → 1,72648). Bu yüzden katı
    # ayağı "fark kapandı" DEĞİL, "fark açıklanamıyorsa hüküm ADIYLA geri
    # çekiliyor" iddiasını sınar — kusuru gizleyen bir bekçi yazılmaz.

    def test_KATI_maske_kisitlanan_ucu_disliyor(self, yapisal_girdiler_kati):
        """Aynı değişmez katı geometride de tutmalı."""
        from hrma.fea.structural_axisym import saint_venant_hukum_maskesi
        m, _ = self._coz(yapisal_girdiler_kati, 128, 8, 'z_max')
        maske, beyan = saint_venant_hukum_maskesi(m, 'z_max')
        assert beyan['gecerli'] is True, beyan
        kisitli = np.asarray(m.z_max_nodes, dtype=int).ravel()
        assert kisitli.size > 0
        assert not maske[kisitli].any(), (
            'katı fikstürde kısıtlanan uç hüküm alanında kalmış')
        assert maske[np.asarray(m.z_min_nodes, dtype=int).ravel()].any()

    def test_KATI_iki_kip_farki_ACIKLANAMIYOR_hukum_ADIYLA_CEKILIYOR(
            self, kati_motor_sozlugu, yapisal_girdiler_kati):
        """P8B2-09 ŞARTI: katıda fark kapanmıyor → ADLI geri çekilme.

        ÖLÇÜLDÜ (once_a1.json): katı 5 kN/40 bar kip oranı 1,7748×
        (bağıl fark %77,5), eşik %8,04 (Saint-Venant kenar sönümünden
        türer). Hibritteki 1,0677× bandın İÇİNDE kalır — bu bekçi iki
        yakayı da ölçer, yoksa "her şeyi reddeden" bir kapı da geçerdi.
        """
        from hrma.fea import bridge
        from hrma.fea.structural_axisym import kisit_yeri_duyarlilik_esigi
        from tests.fea.yuk_modeli_araci import gamma_suz, geri_donus_yukte
        esik = kisit_yeri_duyarlilik_esigi(
            float(yapisal_girdiler_kati['material'].nu))
        # ARAÇ UYARLANDI (fea-yuk 2. tur, 14 Eki; karar §28-18 (B), kart
        # OH-DK-04): 1,7748× fark eski sabit-P_c yükünün ıraksaktaki yapay
        # net eksenel kuvvetindendi; doğru yükte (izantropik P(x) + kapalı
        # uç) katı oran 1,0182 — eşiğin altında, hüküm VERİLİYOR (doğru
        # davranış). Kapının POZİTİF yakası AYNI motorun ``gamma``sız
        # kopyasıyla kurulur: köprünün beyanlı geri dönüşü (sabit P_c +
        # kapalı uç kuvveti), oran 1,2007 (tests/fea/yuk_modeli_araci.py).
        # İddia aynı: fark eşiği aşınca hüküm ADLI gerekçeyle geri çekilir.
        s = _sessiz(bridge.run_structural_from_motor,
                    gamma_suz(kati_motor_sozlugu))
        assert s.get('status') == 'ok', s.get('reason')
        geri_donus_yukte(s)
        h = s['meta']['hukum']
        kd = s['meta']['kisit_duyarliligi']
        assert kd['oran'] - 1.0 > esik, (
            f"katı kip oranı {kd['oran']} — fark eşiğin "
            f'(%{100 * esik:.2f}) altına inmiş, kapının pozitif yakası '
            'artık ölçülmüyor')
        assert h['verildi'] is False
        gerekceler = h['geri_cekme_gerekceleri']
        assert 'kisit_yeri_duyarliligi_yuksek' in gerekceler, (
            'katıda hüküm kısıt-yeri duyarlılığı YÜZÜNDEN geri '
            f'çekilmiyor: {gerekceler}')
        # Gerekçe kök sebebi SÖYLÜYOR: yalnız 'yayimlanan_kip_yakinsamadi'
        # ile yetinilmiyor (ŞARTIN şikâyeti tam olarak buydu).
        assert h['kisit_yeri_duyarliligi']['bagil_fark'] == pytest.approx(
            kd['oran'] - 1.0, rel=1e-12)

    def test_band_govdeyi_yutarsa_FAIL_CLOSED(self, yapisal_girdiler):
        """Kısa gövde/kalın cidar: hüküm alanı yoksa hüküm VERİLMEZ."""
        from hrma.fea import structural_axisym as sa
        from hrma.fea.mesh_axisym import build_wall_mesh
        t = float(np.max(np.atleast_1d(yapisal_girdiler['thickness_m'])))
        m = build_wall_mesh(yapisal_girdiler['contour'], t,
                            n_axial=64, n_radial=12)
        # Bandı gövdeden büyük yapan katsayı: dışlama oranı tavanı aşar.
        maske, beyan = sa.saint_venant_hukum_maskesi(m, 'z_max', kat=200.0)
        assert beyan['gecerli'] is False
        assert 'red_gerekcesi' in beyan
        assert beyan['dislama_orani'] > sa.SAINT_VENANT_MAKS_DISLAMA_ORANI
        # Fail-closed: maske tümü-True'ya döner (hüküm ham tepeye düşer),
        # köprü bunu gerekçeye çevirir.
        assert maske.all()

    def test_yakinsama_OLCUTU_hukum_buyuklugunde(self, yapisal_girdiler):
        """[F4] üçüncü ayak: yakınsama, YAYIMLANAN sayının üstünde ölçülür.

        Ters mutasyon M3 (``_hedef`` ham tepeye döndürülür) bu bekçi
        olmadan YEŞİL geçiyordu: inceltme, hükmü taşımayan bir büyüklüğün
        yakınsamasını ölçüp "yakınsadı" diyordu.
        """
        from hrma.fea.structural_axisym import solve_with_refinement
        t = float(np.max(np.atleast_1d(yapisal_girdiler['thickness_m'])))
        ref = _sessiz(
            solve_with_refinement, yapisal_girdiler['contour'], t,
            yapisal_girdiler['material'],
            yapisal_girdiler['inner_pressure_pa'],
            axial_fix='z_max', n_axial0=32, n_radial0=12, max_rounds=1)
        son = ref.history[-1]
        res = ref.result
        assert res.max_von_mises_hukum is not None
        assert son['max_von_mises'] == pytest.approx(
            res.max_von_mises_hukum, rel=1e-12), (
            'yakınsama geçmişi HÜKÜM büyüklüğünü değil başka bir sayıyı '
            'izliyor')
        assert son['max_von_mises'] != pytest.approx(
            res.max_von_mises_nodal, rel=1e-12), (
            'yakınsama hedefi ham tepeye eşit — z_max kipinde hüküm '
            'bandı hiçbir şey dışlamamış olur')

    def test_kopru_gecersiz_bandi_HUKUM_GERI_CEKME_gerekcesine_cevirir(self):
        """bridge.py zinciri: gecerli=False → 'saint_venant_hukum_alani_yok'."""
        kaynak = (KOK / 'hrma/fea/bridge.py').read_text(encoding='utf-8')
        assert 'saint_venant_hukum_alani_yok' in kaynak
        # Gerekçe hüküm listesine giriyor (beyan değil, KAPI).
        blok = kaynak.split('hukum_gerekceleri = []', 1)[1][:2000]
        assert 'saint_venant_hukum_alani_yok' in blok, (
            'gerekçe hukum_gerekceleri listesine eklenmiyor — beyan '
            'kanalında kalmış')


# ===========================================================================
# P8B1-09 (Fable-D15 ŞART (a)) — yayımlanan kip yakınsamazsa HÜKÜM YOK
# ===========================================================================
class TestP8B109YayimlananKipYakinsamasiKAPI:
    """Ürün zinciri D18'de kuruldu; bu onun EKSİK OLAN bekçisidir."""

    @pytest.fixture(scope='class')
    def motor_sonucu(self, client):
        r = _sessiz(client.post, '/calculate', json=HIBRIT_GOVDE)
        assert r.status_code == 200
        return r.get_json()['motor']

    def test_tol_sifira_yaklasinca_hukum_GERI_CEKILIR(self, monkeypatch,
                                                      motor_sonucu):
        """rel ≥ tol ⇒ verildi False + gerekçe adıyla listede."""
        from hrma.fea import bridge as B
        cagri = {}
        gercek = B.solve_with_refinement

        def _sahte_tol(*a, **kw):
            # Yayımlanan kip karşıt kip olsun diye toleransı ÖLÇÜLEMEYECEK
            # kadar sıkarız: rel her zaman tol'un üstünde kalır.
            kw['tol'] = 1e-12
            cagri['tol'] = kw['tol']
            return gercek(*a, **kw)

        monkeypatch.setattr(B, 'solve_with_refinement', _sahte_tol)
        cikti = _sessiz(B.run_structural_from_motor, motor_sonucu)
        # Hüküm iki adla yayımlanır: üst düzey ``verdict`` ve
        # ``meta['hukum']`` (aynı sözlük). İkisi de sınanır.
        hukum = (cikti or {}).get('verdict') or {}
        assert hukum, 'verdict alanı yok — hüküm hiç yayımlanmıyor'
        assert ((cikti.get('meta') or {}).get('hukum') or {}) is not None
        assert cagri.get('tol') == 1e-12, 'monkeypatch uygulanmadı'
        assert hukum.get('verildi') is False, (
            'tol 1e-12 iken hüküm hâlâ VERİLİYOR — yakınsama kapısı '
            'hükmü tutmuyor')
        gerekceler = hukum.get('geri_cekme_gerekceleri') or []
        assert 'not_converged' in gerekceler
        assert hukum.get('converged') is False
        duyarlilik = (cikti.get('axial_fix_sensitivity') or {})
        yk = duyarlilik.get('yayimlanan_kip_yakinsamasi') or {}
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): tol=1e-12 birincil kipi zaten
        # düşürüyor; yayımlanan kip kapısı ise artık HÜKÜM büyüklüğünü
        # ölçüyor (ham tepeyi değil) ve bu vakada o büyüklük tol'un
        # üstünde kalmayabiliyor. P8B1-09'un kazanımı — "yayımlanan kip
        # kendi yakınsamasını KANITLAR, başka kipten DEVRALMAZ" — ölçümün
        # varlığı ve gerekçenin tutarlılığıyla sınanır.
        if yk:
            assert yk.get('olculdu') is True, yk
            assert yk.get('kapi_alani') == 'max_von_mises_hukum', yk
            if yk.get('yakinsadi') is False:
                assert 'yayimlanan_kip_yakinsamadi' in gerekceler, gerekceler
                assert hukum.get('converged_yayimlanan_kip') is False

    def test_gerekce_adi_urunde_MEVCUT(self):
        """'yayimlanan_kip_yakinsamadi' gerekçesi kapıya bağlı."""
        kaynak = (KOK / 'hrma/fea/bridge.py').read_text(encoding='utf-8')
        blok = kaynak.split('hukum_gerekceleri = []', 1)[1][:2000]
        assert 'yayimlanan_kip_yakinsamadi' in blok
        assert 'converged_yayimlanan_kip' in kaynak


# ===========================================================================
# P11B1-05 — sıvıda "ODA" etiketi çözücünün oda boyunu yazar, 0,8 katını DEĞİL
# ===========================================================================
@pytest.mark.skipif(NODE is None, reason='node bulunamadi')
class TestP11B105OdaEtiketiCOZUCUDEN:

    @staticmethod
    def _fonksiyon(ad):
        kaynak = VIZ_JS.read_text(encoding='utf-8')
        m = re.search(r'\n    function %s\(' % re.escape(ad), kaynak)
        assert m, f'{ad} bulunamadı'
        bas = m.start() + 1
        derinlik, i, basladi = 0, bas, False
        while i < len(kaynak):
            if kaynak[i] == '{':
                derinlik += 1
                basladi = True
            elif kaynak[i] == '}':
                derinlik -= 1
                if basladi and derinlik == 0:
                    return kaynak[bas:i + 1]
            i += 1
        raise AssertionError(f'{ad} gövdesi kapanmadı')

    @staticmethod
    def _sozluk(dil='tr'):
        """``i18n_common.js`` içindeki dil bloğu — ÜRÜNDEN okunur.

        ``tests/test_z5guard_panel_motor.py`` ile AYNI sökme kuralı. Kaçış
        taşıyan değerler (``\\'``, ``\\uXXXX``) atlanır: bu bekçinin
        okuduğu iki anahtar (``viz3d.label.chamber`` / ``…grain``) düz
        sözcüktür ve eksik anahtarda ürünün kendi yedeği koşar.
        """
        kaynak = I18N_COMMON_JS.read_text(encoding='utf-8')
        m = re.search(r'^\s{8}%s:\s*\{' % dil, kaynak, re.M)
        assert m, 'i18n_common.js içinde %r bloğu yok' % dil
        govde = kaynak[m.end():]
        govde = govde[:govde.index('\n        }')]
        ciftler = re.findall(r"^\s*'([\w.]+)':\s*'([^'\\]*)',?$", govde, re.M)
        assert ciftler, '%r bloğu boş okundu' % dil
        return dict(ciftler)

    def _kos(self, cagri):
        """Ürün işlevini node'da koşar — ÜRÜNÜN KENDİ ortamıyla.

        ÖH D23 fix-20: koşum ``ReferenceError: T is not defined`` ile
        ölüyordu. Kök ürün kusuru DEĞİL, ortam eksiği: ``eeee321``
        (ÖH D21 arayuz a2, P17B1-09) rozet sözcüklerini oturum diline
        bağladı ve ``dimensionLabelTexts`` artık kardeş işlev ``T``yi
        çağırıyor. Tarayıcıda ``T`` aynı IIFE içinde tanımlıdır
        (``motor_viz3d.js``); yalnız bu koşum onu kapsam dışında
        bırakıyordu.

        ÖH D24 / fix-22 — SAHNE DİLİ BAĞLANDI. D23 arayuz a2 (P17B1-09,
        ``82e2034``) sahnedeki son iki sabit Türkçe sözcüğü (ODA / YAKIT)
        i18n kanalına aldı: ürün artık ``T('viz3d.label.chamber',
        'CHAMBER')`` çağırıyor ve İNGİLİZCE yedek basıyor. Boş ``window``
        ile koşan bu düzenek o yedeği okuyup ``'ODA'`` bekleyen iki
        bekçiyi kırmızıya düşürüyordu (ölçüldü: taban kaydı-7 —
        ``L 300 mm • CHAMBER 98 mm``). Düzeltilen şey ÜRÜN DEĞİL ORTAM:
        oturum dili artık ürünün KENDİ sözlüğünden (``i18n_common.js``,
        ``tr`` bloğu) kuruluyor. Elle taklit ``T`` ya da elle yazılmış
        çeviri YOK — sözlükten anahtar düşerse ya da Türkçe karşılık
        değişirse bekçi bunu ADIYLA görür.

        ÖH V3 taban-c (14 Eki) — SAYI BİÇİMLEYİCİ KARDEŞİ DE ÜRÜNDEN.
        ``8f9313ca`` (ÖH D35 sayi-bicimi a1, OH-GT-25) ekran sayısını tek
        kaynağa bağladı: ``dimensionLabelTexts`` artık ``toFixed`` değil
        kardeş işlev ``numTxt``yi çağırıyor. Koşum yine kapsam dışında
        bıraktığı için ``ReferenceError: numTxt is not defined`` ile
        ölüyordu (12 Eki taban listesi; 14 Eki docs'suz ölçüm). Kök ürün
        kusuru DEĞİL, fix-20 ile aynı ortam eksiği: ``numTxt`` gövdesi
        ``T`` gibi ÜRÜNDEN sökülür, elle taklit yazılmaz. Bu düzenekte
        ``window.I18N.number`` yok; ürünün kendi yedek dalı koşar (ayraç
        yerelleşmez, sayı uydurulmaz — ``motor_viz3d.js`` ``numTxt``
        künyesi). Bekçilerin okuduğu sayılar tam sayı basamaklıdır
        (``d = 0``), dolayısıyla ayraç seçimi iddiaya girmez.
        """
        sozluk = json.dumps(self._sozluk('tr'), ensure_ascii=False)
        betik = ('var __SOZLUK = ' + sozluk + ';\n'
                 'var window = { I18N: { t: function (k, f) {\n'
                 '    return Object.prototype.hasOwnProperty.call('
                 '__SOZLUK, k) ? __SOZLUK[k] : f;\n'
                 '} } };\n'
                 + self._fonksiyon('T') + '\n'
                 + self._fonksiyon('numTxt') + '\n'
                 + self._fonksiyon('dimensionLabelTexts') + '\n' + cagri)
        p = subprocess.run([NODE], input=betik, capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr[:400]
        return json.loads(p.stdout)

    def test_sivi_ODA_etiketi_oda_boyunu_yazar(self):
        """Lch = 97,96 mm iken etiket 78 mm (0,8·Lch) YAZAMAZ."""
        v = ("{motorType:'liquid',chamberInnerMm:50,chamberOuterMm:60,"
             "throatMm:20,exitMm:40,totalMm:300,grainMm:78.368,"
             "chamberLengthMm:97.96,chamberLengthKaynakli:true}")
        t = self._kos('console.log(JSON.stringify('
                      'dimensionLabelTexts(%s)))' % v)
        assert 'ODA' in t['total']
        assert '98 mm' in t['total'], t['total']
        assert '78 mm' not in t['total'], (
            'etiket hâlâ yakıt çekirdeği yedeğini (0,8·Lch) yazıyor')

    def test_kaynaksiz_oda_boyu_etiketi_HIC_YAZILMAZ(self):
        """Fail-closed: çözücü oda boyu vermediyse uydurma sayı basılmaz."""
        v = ("{motorType:'liquid',chamberInnerMm:50,chamberOuterMm:60,"
             "throatMm:20,exitMm:40,totalMm:300,grainMm:78.368,"
             "chamberLengthMm:97.96,chamberLengthKaynakli:false}")
        t = self._kos('console.log(JSON.stringify('
                      'dimensionLabelTexts(%s)))' % v)
        assert 'ODA' not in t['total'], t['total']
        assert '78' not in t['total'] and '98' not in t['total'], t['total']
        assert t['total'].startswith('L 300 mm')

    def test_kati_hibrit_YAKIT_etiketi_DEGISMEDI(self):
        """Onarım yalnız sıvı dalını çevirir; katı/hibrit aynen kalır."""
        for tip in ('solid', 'hybrid'):
            v = ("{motorType:'%s',chamberInnerMm:50,chamberOuterMm:60,"
                 "throatMm:20,exitMm:40,totalMm:300,grainMm:1511.6,"
                 "chamberLengthMm:1575.5,chamberLengthKaynakli:true}" % tip)
            t = self._kos('console.log(JSON.stringify('
                          'dimensionLabelTexts(%s)))' % v)
            assert 'YAKIT 1512 mm' in t['total'], (tip, t['total'])

    def test_Lg_yedegi_sivi_dalinda_KULLANILMIYOR(self):
        """dims() kaynağı: 0,8·Lch yedeği sıvı ODA etiketine ulaşamaz."""
        kaynak = VIZ_JS.read_text(encoding='utf-8')
        assert 'chamberLengthKaynakli' in kaynak, (
            'oda boyu kaynak bayrağı yok — etiket yine yedeğe düşebilir')
        m = re.search(r'grainMm:\s*d\.Lg', kaynak)
        assert m, 'grainMm alanı bulunamadı'
        # Aynı çağrıda oda boyu ve kaynağı da geçilmeli.
        pencere = kaynak[max(0, m.start() - 700):m.end() + 300]
        assert 'chamberLengthMm: d.Lch' in pencere, pencere[-400:]
        # Bayrak SABİT true olamaz — dims()'in ölçtüğü kaynak geçilmeli
        # (ters mutasyon M8: 'chamberLengthKaynakli: true').
        assert 'chamberLengthKaynakli: d.LchKaynakli' in pencere, \
            pencere[-400:]
        assert 'LchKaynakli: LchKaynakli' in kaynak, (
            'dims() oda boyu kaynak bayrağını döndürmüyor')
        assert re.search(r'var LchKaynakli\s*=\s*isFinite\(', kaynak), (
            'LchKaynakli sabit değere bağlanmış — ölçüm yok')
