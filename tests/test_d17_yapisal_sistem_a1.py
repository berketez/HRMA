"""ÖH Dalga-17 · kulvar ``yapisal-sistem`` · aşama 1 — onarım bekçileri.

Her sınıf bir defter kalemini bekler. Ölçümler:
``docs/scofield/raw/OH/D17/yapisal-sistem/a1/once.json`` ⟷ ``sonra.json``.
Ters-mutasyon kanıtı: aynı dizinde ``mutasyon.json``.

Kullanıcıya görünen ürün metinleri İngilizce'dir; bekçi açıklamaları Türkçe.
"""
import ast
import inspect
import json

import pytest

from hrma.analysis.bolted_joint import PROOF_SF_ACCEPTANCE_LIMIT
from hrma.analysis.slosh_analysis import analyze_slosh
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.valve_feedline import analyze_valve_feedline


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


#: P5B1-06'nın ölçüldüğü motor — sıkma boyu VERİLİR, yani ön-yük modeli koşar.
_B1_MOTOR = {'chamber_pressure': 60.0, 'chamber_diameter': 0.12,
             'chamber_length': 0.5, 'wall_thickness': 0.003,
             'throat_diameter': 0.03, 'material': 'steel_4130',
             'closure_grip_length_m': 0.020}

#: P5B3-03'ün ölçüldüğü LOX hattı (a2 bekçisiyle birebir aynı).
LOX_HAT = dict(mass_flow_kg_s=40.0, density_kg_m3=1141.0, line_id_m=0.05,
               wall_thickness_m=0.002, line_length_m=6.0,
               viscosity_Pa_s=1.9e-4, inlet_pressure_Pa=60e5,
               valve_pressure_drop_Pa=3e5, fluid='lox',
               bulk_modulus_Pa=2.2e9, pipe_youngs_modulus_Pa=193e9)


def _post(istemci, yol, yuk):
    r = istemci.post(yol, json=yuk)
    try:
        j = r.get_json()
    except Exception:                              # noqa: BLE001
        j = None
    return r.status_code, (j if isinstance(j, dict) else {})


# =========================================================================
# P5B1-06 — kaynaksız 1,2 MARGINAL bandı (Fable-D15 ŞARTI)
# =========================================================================
class TestP5B106CivataBandi:
    """ŞART: "1,2 MARGINAL eşiğine kaynak yazılsın ... ya da mevcut bir depo
    sabitine bağlansın; yoksa MARGINAL bandı kaldırılıp yalnız <1,0 CRITICAL
    / >=1,0 SAFE bırakılsın."

    ÖLÇÜLDÜ (once.json K1): ``proof_SF_min`` 60 barda 1,0147389908256885 —
    yani proof sınırının ÜSTÜNDE — ama ürün ``fastener_status: 'MARGINAL'``
    yayımlıyordu; 1,2 eşiği ``structural_analysis.py`` içinde çıplak
    literaldi (satır 1911) ve ön-yük modelinin kendi tek eşiği 1,0'dı.
    Üçüncü şık uygulandı: kaynaksız bant KALDIRILDI.
    """

    def test_proof_sinirinin_ustunde_marginal_yok(self):
        fas = StructuralAnalyzer().analyze_structure(
            dict(_B1_MOTOR))['fastener_analysis']
        pre = fas['preload_analysis']
        assert pre is not None, 'ön-yük modeli koşmadı'
        assert pre['proof_SF_min'] == pytest.approx(1.0147389908256885,
                                                    rel=1e-9)
        assert pre['proof_SF_min'] >= PROOF_SF_ACCEPTANCE_LIMIT
        assert fas['fastener_status'] == 'SAFE', (
            'proof sınırının üstünde kaynaksız bir MARGINAL bandı '
            f"yayımlanıyor: {fas['fastener_status']}")

    def test_proof_ihlalinde_hala_critical(self):
        """Onarım sağlıklı YÖNÜ kapatmaz: gerçek ihlal hâlâ CRITICAL."""
        fas = StructuralAnalyzer().analyze_structure(
            dict(_B1_MOTOR, chamber_pressure=100.0, chamber_diameter=0.15),
            material='steel_4130',
            actual_wall_thickness=0.006)['fastener_analysis']
        assert fas['preload_analysis']['proof_SF_min'] < (
            PROOF_SF_ACCEPTANCE_LIMIT)
        assert fas['fastener_status'] == 'CRITICAL'

    def test_hukum_kumesi_yalniz_uc_deger(self):
        """Yayımlanabilir hüküm kümesi: NOT_EVALUATED / CRITICAL / SAFE."""
        import textwrap
        kaynak = textwrap.dedent(
            inspect.getsource(StructuralAnalyzer._analyze_fasteners))
        agac = ast.parse(kaynak)
        atananlar = set()
        for d in ast.walk(agac):
            if isinstance(d, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == 'fastener_status'
                    for t in d.targets):
                assert isinstance(d.value, ast.Constant), ast.dump(d.value)
                atananlar.add(d.value.value)
        assert atananlar == {'NOT_EVALUATED', 'CRITICAL', 'SAFE'}, atananlar
        assert 'MARGINAL' not in atananlar

    def test_esik_tek_kaynaktan_gelir(self):
        """Doktrin 4: eşik iki yerde YAZILMAZ; ön-yük modelinden okunur."""
        from hrma.analysis import bolted_joint as _bj
        assert PROOF_SF_ACCEPTANCE_LIMIT == 1.0
        # bolted_joint kendi uyarısını da AYNI sabitten kurar
        bj_kaynak = inspect.getsource(_bj)
        assert 'n_proof_min < PROOF_SF_ACCEPTANCE_LIMIT' in bj_kaynak
        assert 'n_proof_min < 1.0' not in bj_kaynak
        # structural_analysis'in hüküm dalı çıplak emniyet katsayısı
        # LİTERALİ taşımaz (yorumdaki "1.2" metni sayılmaz; AST ile ölçülür).
        #
        # ÖH D29 / arayuz-i18n a1 — OH-D19-26 (d): TEK LİTERAL KİLİDİ
        # BANDA ÇEVRİLDİ. Eski hâl yalnız ``1.2 not in literaller`` diyordu;
        # 1,25 / 1,5 / 2,0 gibi başka bir emniyet katsayısı ya da sabit
        # katlanan bir ifade (``6 / 5``) sessizce geçerdi. Artık (1,0; 4,0]
        # bandındaki HER sabit yasak ve sabit-katlanan ikili işlemler de
        # değerlendirilir. Ölçülen taban (D29): bantta 0 sabit; mevcut
        # literaller {0.0 … 0.042, 0.1, 0.2, 0.75, 1.0, 16.0, 1e3, 1e5, 1e6}
        # yani hepsi ya birim çevrimi ya geometri, hiçbiri emniyet katsayısı
        # değil.
        import textwrap
        agac = ast.parse(textwrap.dedent(
            inspect.getsource(StructuralAnalyzer._analyze_fasteners)))
        literaller = [d.value for d in ast.walk(agac)
                      if isinstance(d, ast.Constant)
                      and isinstance(d.value, float)
                      and not isinstance(d.value, bool)]
        # Sabit-katlanan ifadeler de sayıya çevrilir (``6 / 5`` -> 1.2).
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.BinOp):
                continue
            try:
                deger = ast.literal_eval(dugum)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(deger, float) and not isinstance(deger, bool):
                literaller.append(deger)
        assert 1.2 not in literaller, literaller
        sf_bandi = sorted({x for x in literaller if 1.0 < x <= 4.0})
        assert not sf_bandi, (
            'hüküm dalında çıplak emniyet katsayısı sabiti var: %s — eşik '
            'ön-yük modelinden (PROOF_SF_ACCEPTANCE_LIMIT) okunmalı'
            % sf_bandi)

    def test_onyuk_hukmu_ayni_modelden_gelir(self):
        """Hüküm, ön-yük modelinin KENDİ sayısından okunur (künye ile
        birlikte). İki üreticinin sayısal eşitliği D15 a1 bekçisinde
        (``test_iki_uretici_ayni_sayiyi_verir``) zaten kilitli."""
        fas = StructuralAnalyzer().analyze_structure(
            dict(_B1_MOTOR))['fastener_analysis']
        assert 'hrma.analysis.bolted_joint' in fas['preload_analysis_basis']
        assert fas['bolt_safety_factor_is_design_input'] is True
        assert fas['preload_analysis']['source'] is not None


# =========================================================================
# P5B3-03 — kanıt hijyeni: tablo sayıları koddan üretilebilmeli
# =========================================================================
class TestP5B303KapanmaSayilari:
    """ŞART: yorum tablosu ve test yorumu GERÇEK sayılarla yazılsın.

    ÖLÇÜLDÜ (once.json K2): D15'te yazılan a = 840,5 m/s / t_c = 14,277 ms
    / J = 171,22 bar sayıları bu koddan ÜRETİLEMİYORDU (a2/olcum.py
    ``working_pressure_Pa`` diye var olmayan bir parametre veriyordu,
    bütün kayıtlar TypeError'dı). Gerçek değerler aşağıda kilitlendi.
    """

    @pytest.fixture(scope='class')
    def wh(self):
        return analyze_valve_feedline(**LOX_HAT)['water_hammer']

    def test_dalga_hizi_ve_boru_periyodu(self, wh):
        assert wh['wave_speed_m_s'] == pytest.approx(1224.9583777985195,
                                                     rel=1e-9)
        assert wh['critical_closure_time_s'] == pytest.approx(
            0.00979625121758525, rel=1e-9)
        assert wh['flow_velocity_m_s'] == pytest.approx(17.85436697262279,
                                                        rel=1e-9)

    def test_joukowsky_yukselisi(self):
        cl = analyze_valve_feedline(
            allowable_pressure_rise_Pa=1000e5, **LOX_HAT
        )['water_hammer']['closure_time']
        assert cl['joukowsky_rise_Pa'] / 1e5 == pytest.approx(
            249.54647156283363, rel=1e-9)

    @pytest.mark.parametrize('izin_bar,beklenen', [
        (2.0, 'achievable_by_scheduling'),
        (20.0, 'achievable_by_scheduling'),
        (171.05, 'achievable_by_scheduling'),
        (171.39, 'achievable_by_scheduling'),
        (249.50, 'achievable_by_scheduling'),
        (249.60, 'no_scheduling_constraint'),
        (400.00, 'no_scheduling_constraint'),
    ])
    def test_hukum_siniri_joukowskydedir(self, izin_bar, beklenen):
        """Sınır 171,39 bar DEĞİL, J = 249,5465 bar'dır.

        D15 yorum tablosu sınırı 171,39 bar'da gösteriyordu; o sayı
        yanlış dalga hızından (840,5 m/s) geliyordu.
        """
        cl = analyze_valve_feedline(
            allowable_pressure_rise_Pa=izin_bar * 1e5, **LOX_HAT
        )['water_hammer']['closure_time']
        assert cl['status'] == beklenen

    def test_kaynak_yorumu_gercek_sayilari_tasir(self):
        """Kanıt hijyeni: koddaki 'ÖLÇÜLDÜ' tablosu koşmuş sayıları taşır."""
        from hrma.analysis import valve_feedline as _vf
        kaynak = inspect.getsource(_vf)
        for sayi in ('1224,9584', '9,7963', '249,5465'):
            assert sayi in kaynak, f'yorum tablosunda {sayi} yok'


# =========================================================================
# P5B2-09 (kalan yarı) — kardeş üretici aynı adı ters tanımla yayımlıyordu
# =========================================================================
class TestP5B209KardesUretici:
    """ÖLÇÜLDÜ (once.json K6): ``/calculate_solid`` yanıtında
    ``safety_analysis.pressure_safety.burst_margin = 4,652338212874558``
    yayımlanıyor ve YANINDA hiçbir tanım alanı yok
    (``burst_margin_definition`` 0 geçiş, ``burst_margin_vs_meop`` 0
    geçiş). Kardeş üretici (``pressure_vessel`` -> ``safety_analysis``)
    aynı adı KOPMA/GEREKEN-KOPMA olarak yayımlıyor. Sayı değişmedi;
    tanım adları eklendi.
    """

    YUK = {'motor_name': 'D17-P5B209', 'propellant_type': 'apcp',
           'grain_type': 'bates', 'chamber_pressure': 40.0,
           'thrust': 5000.0, 'burn_time': 3.0, 'chamber_diameter': 100.0,
           'grain_length': 500.0, 'core_diameter': 30.0,
           'expansion_ratio': 8.0}

    @pytest.fixture(scope='class')
    def basinc(self, istemci):
        durum, govde = _post(istemci, '/calculate_solid', dict(self.YUK))
        assert durum == 200, durum
        ps = govde['safety_analysis']['pressure_safety']
        return ps

    def test_sayi_degismedi(self, basinc):
        # ÖH KİTAP p1b (B11, §28-36 Ş-3): eski 4,652338212874558 geri
        # çözülmüş APCP dörtlüsündendi; CEA denge dörtlüsüyle ölçülen yeni
        # taban (−3·10⁻⁷ bağıl; tanım ve yön aynı).
        # V301/K-D: 4,652336825318477 -> 4,652337530766883 (+1,5·10⁻⁷ bağıl)
        # V301/N-CEA-2'den (termokimya motorun Pc'sinde CEA): CEA kapalı koşu
        # eski sayıyı BİT-AYNI veriyor (K-D/capa_olcum.json). Kasa cidarını
        # HRMA boyutladığı için oran yarıçaptan bağımsızdır (t ∝ r), K-A
        # KT-03'ün +4 mm kasası bu sayıyı değiştirmez; kayan yalnız MEOP
        # (40,0001617 -> 40,0001556 bar).
        assert basinc['burst_margin'] == pytest.approx(4.652337530766883,
                                                       rel=1e-9)

    def test_tanim_adiyla_yayimlanir(self, basinc):
        assert basinc['burst_margin_vs_meop'] == pytest.approx(
            basinc['burst_margin'], rel=1e-12)
        tanim = basinc['burst_margin_definition']
        assert 'max_operating_pressure_bar' in tanim
        assert 'burst_margin_vs_meop' in tanim

    def test_oran_gercekten_meope_karsidir(self, basinc):
        """Ad boş bir künye değil: sayı gerçekten kopma/MEOP."""
        assert basinc['burst_margin'] == pytest.approx(
            basinc['burst_pressure_bar']
            / basinc['max_operating_pressure_bar'], rel=1e-12)


# =========================================================================
# P5B1-10 (kalan yarı) — burn_time uçta canlı kapı, modülde ÖLÜ girdi
# =========================================================================
class TestP5B110BurnTimeOlu:
    """ÖLÇÜLDÜ (once.json K5) — kalemin iki iddiası da SAYIYLA sınandı:

    * ÖLÜ: ``burn_time`` 0,5 s ⟷ 10 s yanıtları BİREBİR aynı
      (sha256 4f7b32146afa7848), ``_analyze_fatigue`` imzasında
      ``burn_time`` YOK.
    * "uçta ZORUNLU-pozitif alan" iddiası KISMEN ÇÜRÜK: alan zorunlu
      DEĞİL (hiç göndermeyince HTTP 200). Canlı olan kapı yalnız
      *gönderildiğinde* işleyen pozitiflik + kanonik üst bant (D16
      P16B1-18 ailesi) — bu kapı ÖK-22 gereği GEVŞETİLMEZ.

    Bu sınıf ölü tesisatın geri gelmesini ve kapının düşmesini birlikte
    bekler.
    """

    YUK = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
           'chamber_length': 0.5, 'throat_diameter': 0.02,
           'burn_time': 10, 'material': 'steel_4130'}

    def test_yanma_suresi_yapisal_hukmu_degistirmez(self, istemci):
        d1, g1 = _post(istemci, '/analyze_structural_safety',
                       dict(self.YUK, burn_time=0.5))
        d2, g2 = _post(istemci, '/analyze_structural_safety',
                       dict(self.YUK, burn_time=10))
        assert d1 == d2 == 200
        assert json.dumps(g1, sort_keys=True) == json.dumps(g2,
                                                            sort_keys=True)

    def test_modul_imzasinda_burn_time_yok(self):
        imza = inspect.signature(StructuralAnalyzer._analyze_fatigue)
        assert 'burn_time' not in imza.parameters

    def test_sessiz_varsayilan_geri_gelmedi(self):
        kaynak = inspect.getsource(StructuralAnalyzer.analyze_structure)
        assert "get('burn_time'" not in kaynak

    @pytest.mark.parametrize('deger', [0, -5])
    def test_uc_kapisi_gevsetilmedi(self, istemci, deger):
        """ÖK-22: sağlıklı envanter gevşetilmez — pozitiflik kapısı durur."""
        durum, govde = _post(istemci, '/analyze_structural_safety',
                             dict(self.YUK, burn_time=deger))
        assert durum == 422
        assert [a['field'] for a in govde['invalid_fields']] == ['burn_time']

    def test_alan_zorunlu_degil(self, istemci):
        """Kalem başlığının "ZORUNLU alan" yarısı ÇÜRÜK — ölçüldü."""
        y = dict(self.YUK)
        y.pop('burn_time')
        durum, _ = _post(istemci, '/analyze_structural_safety', y)
        assert durum == 200


# =========================================================================
# P16B1-06 (D16 devri) — türetilen geometri bandı ayakta mı?
# =========================================================================
class TestP16B106TuretilenBantAyakta:
    """D16'da (977b860) ``/api/regression-analysis`` çıktı geometrisine
    kanonik bant bağlanmıştı. ÖLÇÜLDÜ (once.json K8, taban 2426b4d):
    ``regression_a = 1e9`` -> 422 ``regression_geometry_out_of_range``;
    sağlıklı kol 200 + port tepe 65,30350024572282 mm. Bu sınıf onarımın
    D17 tabanında hâlâ durduğunu bekler.
    """

    TABAN = {'motor_data': {'fuel_type': 'htpb', 'burn_time': 10,
                            'mdot_ox': 1.9, 'port_diameter_initial': 0.03,
                            'grain_length': 0.5, 'regression_a': 3.68e-5}}

    def test_saglikli_kol_200(self, istemci):
        durum, govde = _post(istemci, '/api/regression-analysis',
                             json.loads(json.dumps(self.TABAN)))
        assert durum == 200

    @pytest.mark.parametrize('a', [1e6, 1e9])
    def test_turetilen_geometri_bandi_disi_reddedilir(self, istemci, a):
        y = json.loads(json.dumps(self.TABAN))
        y['motor_data']['regression_a'] = a
        durum, govde = _post(istemci, '/api/regression-analysis', y)
        assert durum == 422
        assert govde['error'] == 'regression_geometry_out_of_range'

    def test_calculate_kolu_da_kapali(self, istemci):
        """Kalemin BAŞLIĞI (/calculate -> 4.176 km oda, HTTP 200) tabanda
        çürüktü; kapının geri açılmasını bu düğüm yakalar."""
        durum, _ = _post(istemci, '/calculate', {
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'regression_a': 1e9})
        assert durum in (400, 422), durum


# =========================================================================
# OH-D16-07 — fill_sweep SONUÇ dizileri form girdisiyle oynuyor mu?
# =========================================================================
class TestOHD1607FillSweep:
    """Kalem: "Slosh fill_sweep SONUÇ dizileri (hibrit 25, sıvı 50 yaprak)
    hiçbir form girdisiyle oynamıyor".

    ÖLÇÜLDÜ (once.json K7, taban 2426b4d): hibrit ``/calculate`` yanıtında
    ``fill_sweep`` altındaki 21 dizinin 21'i DE dört ayrı form
    değişikliğinde (itki x4, süre x3, O/F 6,0->2,5, Pc x2) değişiyor —
    yani başlık ÇÜRÜK. Gerçek olan daha dar bir şey: ``slosh_mass_ratio``
    yalnız h/R'nin fonksiyonudur, dolayısıyla tank en-boy oranı ile
    doluluk kesri sabit kalan HER tasarım değişikliğinde bit-aynı çıkar.
    Bu FİZİKTİR, kopuk tel değil; bu sınıf ikisini de kilitler.
    """

    def test_sonuc_egrisi_h_bolu_r_nin_fonksiyonudur(self):
        """R ve H birlikte ölçeklenince oran eğrisi DEĞİŞMEZ (analitik)."""
        egriler = [analyze_slosh(radius=R, fill_height=H, g_eff=9.80665,
                                 liquid_mass=10.0)['fill_sweep']
                   for R, H in ((0.05, 0.2), (0.1, 0.4), (0.2, 0.8))]
        for e in egriler[1:]:
            assert e['slosh_mass_ratio'] == pytest.approx(
                egriler[0]['slosh_mass_ratio'], rel=1e-12)
            assert e['fill_ratio'] == pytest.approx(egriler[0]['fill_ratio'],
                                                    rel=1e-12)
        assert egriler[0]['slosh_mass_ratio'][0] == pytest.approx(
            0.8308141711841972, rel=1e-9)
        assert egriler[0]['slosh_mass_ratio'][-1] == pytest.approx(
            0.1136233579275338, rel=1e-9)

    def test_frekans_ve_sarkac_geometriyle_oynar(self):
        """Aynı yaprak öbeğindeki BOYUTLU sonuçlar donuk DEĞİLDİR."""
        a = analyze_slosh(radius=0.1, fill_height=0.4, g_eff=9.80665,
                          liquid_mass=10.0)['fill_sweep']
        b = analyze_slosh(radius=0.2, fill_height=0.8, g_eff=9.80665,
                          liquid_mass=10.0)['fill_sweep']
        assert a['f1_hz'][0] != b['f1_hz'][0]
        assert a['pendulum_length'][0] != b['pendulum_length'][0]
        assert b['pendulum_length'][0] == pytest.approx(
            2.0 * a['pendulum_length'][0], rel=1e-12)

    def test_sivi_kutlesi_sonuca_gecer(self):
        """``slosh_mass_kg`` kütle girdisine DOĞRUDAN bağlı."""
        a = analyze_slosh(radius=0.1, fill_height=0.4, g_eff=9.80665,
                          liquid_mass=10.0)['fill_sweep']
        b = analyze_slosh(radius=0.1, fill_height=0.4, g_eff=9.80665,
                          liquid_mass=25.0)['fill_sweep']
        assert b['slosh_mass_kg'][0] == pytest.approx(
            2.5 * a['slosh_mass_kg'][0], rel=1e-12)

    def test_ivme_sonuca_gecer(self):
        a = analyze_slosh(radius=0.1, fill_height=0.4, g_eff=9.80665,
                          liquid_mass=10.0)['fill_sweep']
        b = analyze_slosh(radius=0.1, fill_height=0.4, g_eff=4.0 * 9.80665,
                          liquid_mass=10.0)['fill_sweep']
        assert b['f1_hz'][0] == pytest.approx(2.0 * a['f1_hz'][0], rel=1e-12)
        # oran eğrisi g'den BAĞIMSIZDIR (analitik) — donukluk değil, fizik
        assert b['slosh_mass_ratio'] == pytest.approx(a['slosh_mass_ratio'],
                                                      rel=1e-12)

    def test_urun_yolunda_egri_form_girdisiyle_oynar(self, istemci):
        """UÇ düzeyi: hibrit ``/calculate`` fill_sweep'i itkiyle oynar.

        Kalemin "hiçbir form girdisiyle oynamıyor" iddiasının doğrudan
        çürütmesi (once.json K7 ``hibrit_donuk``: 21/21 dizi değişti).
        """
        HIB = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
               'chamber_pressure': 20.0, 'fuel_type': 'htpb',
               'oxidizer_type': 'n2o'}
        d1, g1 = _post(istemci, '/calculate', dict(HIB))
        d2, g2 = _post(istemci, '/calculate', dict(HIB, thrust=4000))
        assert d1 == d2 == 200
        s1 = g1['motor']['oxidizer_tank_slosh']['slosh']['fill_sweep']
        s2 = g2['motor']['oxidizer_tank_slosh']['slosh']['fill_sweep']
        for anahtar in ('f1_hz', 'pendulum_length', 'slosh_mass_kg',
                        'fill_height'):
            assert s1[anahtar] != s2[anahtar], (
                f'{anahtar} itki x4 ile değişmiyor — tel kopuk')
        assert len(s1['f1_hz']) == 25
