# -*- coding: utf-8 -*-
"""ÖH Dalga-30 · kulvar ``app-api-uc`` · aşama 2/3 — bekçiler.

Her sınıf BİR kaleme bağlıdır; ölçüm kanıtı
``docs/scofield/raw/OH/D30/app-api-uc/a2/once.json`` (taban: a1 commit
``0dd609b7``) ve ``sonra.json`` dosyalarındadır. Ters-mutasyon kanıtı
``mutasyon.json``.

Bu aşamanın kalemleri:
  P7B4-15  export-pdf bilinmeyen report_type   (ONARILMIŞ — D29 a2, kilit)
  P7B4-16  PDF emniyet katsayısı tautoloji bağlamı        (onarıldı)
  P7B4-17  korelasyon docstring süre iddiası              (onarıldı)
  P7B4-20  UQ n_samples / seed sessiz değişimi (ONARILMIŞ — D24 a1, kilit)
  P7B4-22  xlsx NaN/Inf hücresi                (ONARILMIŞ — D29 a2, kilit)
  P7B4-23  upload-csv satır sınırı                        (kısmen + ölçüm)
  P7B4-24  cfd/nozzle Pb_Pa vakum kapısı                  (onarıldı)
  P12aB5-13 sürüm notlarının sırası                       (onarıldı)
  P15B4-13 generate-3d reddinin SINIFI                    (onarıldı)
  P16B1-40 include_plots dize bayrağı        (ONARILMIŞ — D29 a2, kilit)
  P16B1-41 regression port_diameter_final    (ONARILMIŞ — D23 a2, kilit)
  P16B1-43 motor bloğunda nozzle_type yankısı             (onarıldı)
  P16B2-14 kasa cidarı t >= r (ilk yarı çürütüldü)        (onarıldı)
"""
import contextlib
import io
import json
import math
import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))
os.environ.setdefault('HRMA_HEADLESS', '1')

with contextlib.redirect_stdout(io.StringIO()):
    import hrma.app as HA
    from hrma.app import app

app.config['TESTING'] = True


@pytest.fixture(scope='module')
def C():
    return app.test_client()


A2_APP_KAYNAK = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')

#: Kanonik hibrit yük (a1/a2 çapa betiğinin A1 isteğiyle AYNI).
A2_HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}

#: Kanonik katı yük (çapa A2 isteğiyle AYNI; hazne Ø100 mm).
A2_KATI = {'motor_name': 'BEKCI-KATI', 'propellant_type': 'apcp',
        'grain_type': 'bates', 'chamber_pressure': 40.0, 'thrust': 5000.0,
        'burn_time': 3.0, 'chamber_diameter': 100.0, 'grain_length': 500.0,
        'core_diameter': 30.0, 'expansion_ratio': 8.0}

A2_PDF_MOTOR = {
    'motor_name': 'BEKCI', 'motor_type': 'hybrid',
    'chamber_diameter': 0.15, 'chamber_length': 0.60,
    'throat_diameter': 0.04, 'exit_diameter': 0.12,
    'port_diameter_initial': 0.05, 'thrust': 5000.0,
    'chamber_pressure': 20.0, 'burn_time': 10.0,
}

A2_GEO_3D = {'motor_type': 'hybrid', 'chamber_diameter': 0.15,
          'chamber_length': 0.60, 'throat_diameter': 0.04,
          'exit_diameter': 0.12, 'port_diameter_initial': 0.05}

A2_CFD_TABAN = {'nozzle_contour': {'points': [[0.0, 0.06], [0.10, 0.02],
                                           [0.25, 0.06]]},
             'P0_Pa': 2.0e6, 'T0_K': 3000.0, 'gamma': 1.2,
             'R_J_per_kgK': 300.0, 'P_ambient_Pa': 101325.0,
             'resolution': 'coarse', 'max_iterations': 600}


def _kati_iste(C, **ek):
    y = dict(A2_KATI)
    y.update(ek)
    with contextlib.redirect_stdout(io.StringIO()):
        r = C.post('/calculate_solid', json=y)
    return r, (r.get_json() or {})


def _case_analizi(g):
    return ((g.get('structural_analysis') or {}).get('case_analysis') or {})


# =====================================================================
# P16B2-14 — kasa cidarının İKİ kapısı
# =====================================================================
class TestP16B214KasaCidarKapisi:
    """ÖLÇÜLDÜ (once.json K13 + probe6, taban ``0dd609b7``): Ø100 mm haznede
    ``case_thickness = 100`` KABUL EDİLİYOR ve ``vessel_status = PASS`` +
    ``vessel_status_is_tautological = False`` + SF 100,1903 ile TAM,
    KAZANILMIŞ görünen bir hüküm yayımlanıyordu — 100 mm cidar, iç yarıçapın
    (50 mm) iki katı, yani iç yarıçap NEGATİF.

    Kalemin İLK yarısı ("101 -> 2,4 mm tam düşüş") ölçümle ÇÜRÜTÜLDÜ: düşen
    değer için hüküm ZATEN geri çekiliyor (``NOT_EVALUATED`` +
    ``user_value_not_applied`` + bandı adıyla söyleyen ``vessel_status_basis``;
    ÖH D24 a1 / P16B2-06). O yola ikinci bir kapı KURULMADI.
    """

    @pytest.mark.parametrize('t_mm', [50.0, 100.0])
    def test_cidar_ic_yaricapa_ulasirsa_hukum_yayimlanmaz(self, C, t_mm):
        r, g = _kati_iste(C, case_thickness=t_mm)
        assert r.status_code == 422, (
            'case_thickness=%g mm (iç yarıçap 50 mm) hâlâ HTTP %s ve emniyet '
            'katsayısı yayımlanıyor' % (t_mm, r.status_code))
        assert g.get('error') == 'invalid_case_geometry'
        kunye = (g.get('invalid_fields') or [{}])[0]
        assert kunye.get('reason') == 'case_thickness_at_or_above_inner_radius'
        assert kunye.get('chamber_inner_radius_mm') == pytest.approx(50.0)
        assert _case_analizi(g).get('safety_factor') is None

    def test_saglikli_envanter_gevsemez(self, C):
        """ÖK-22: alan yokken ve iç yarıçapın ALTINDAKİ her değerde aynı."""
        r0, g0 = _kati_iste(C)
        assert r0.status_code == 200
        assert _case_analizi(g0).get('design_mode') == 'size'
        # ÖH KİTAP p1b (B11, §28-36 Ş-3): eski 2,404567428606375 /
        # 49,99496445310755 geri çözülmüş APCP dörtlüsündendi (MEOP ve
        # tasarım noktası); CEA denge dörtlüsüyle ölçülen yeni taban.
        for t_mm, beklenen_sf in ((2.4, 2.416737508317951),
                                  (49.9, 50.24800069377741)):
            r, g = _kati_iste(C, case_thickness=t_mm)
            assert r.status_code == 200, 'meşru cidar %g reddedildi' % t_mm
            ca = _case_analizi(g)
            assert ca.get('design_mode') == 'verify'
            assert ca.get('wall_thickness_requested_mm') == pytest.approx(t_mm)
            assert ca.get('safety_factor') == pytest.approx(beklenen_sf,
                                                            rel=1e-9)

    @pytest.mark.parametrize('deger', [101, 'abc', True])
    def test_dusen_deger_yolu_bit_ayni_kalir(self, C, deger):
        """İLK YARININ ÇÜRÜTÜLMESİ: hüküm ZATEN geri çekiliyor; bu kulvar
        oraya ikinci bir kapı koymadı (D24 bekçisi + hibrit kardeş alanın
        sözleşmesi korunur)."""
        r, g = _kati_iste(C, case_thickness=deger)
        assert r.status_code == 200
        press = None
        for kok in (g.get('results'), g):
            if isinstance(kok, dict):
                aday = ((kok.get('safety_analysis') or {})
                        .get('pressure_safety'))
                if isinstance(aday, dict):
                    press = aday
                    break
        assert press is not None, 'pressure_safety bloğu yanıtta yok'
        assert press['wall_thickness_source'] == 'user_value_not_applied'
        assert press['vessel_status'] == 'NOT_EVALUATED'
        assert press['vessel_status_is_tautological'] is True

    def test_kardes_kapinin_deseni_kopyalanmadi_atifla_duruyor(self):
        """Sınır yeni bir ayar sayısı değil; kardeş kapı ADLA anılıyor."""
        assert 'wall_thickness_at_or_above_inner_radius' in A2_APP_KAYNAK
        i = A2_APP_KAYNAK.index('case_thickness_at_or_above_inner_radius')
        blok = A2_APP_KAYNAK[i - 4000:i + 2000]
        assert 'wall_thickness_at_or_above_inner_radius' in blok


# =====================================================================
# P16B1-43 — motor bloğunda lüle kimliği
# =====================================================================
class TestP16B143LuleKimligiYankisi:
    """ÖLÇÜLDÜ (once.json K12): ``nozzle_type='conical'`` ve ``'bell'``
    koşularının ikisinde de ``motor`` bloğunda ``nozzle_type`` anahtarı
    YOKTU; tek ayırt edici iz ``nozzle_angles`` sayılarıydı.
    """

    @pytest.mark.parametrize('gonderilen,beklenen',
                             [('conical', 'conical'), ('bell', 'bell'),
                              ('Bell', 'bell')])
    def test_cozulen_lule_motor_blogunda_adiyla_durur(self, C, gonderilen,
                                                      beklenen):
        y = dict(A2_HIBRIT)
        y['nozzle_type'] = gonderilen
        y['include_plots'] = False
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/calculate', json=y)
        g = r.get_json() or {}
        assert r.status_code == 200
        assert (g.get('motor') or {}).get('nozzle_type') == beklenen, (
            "motor bloğunda 'nozzle_type' yankısı yok — kullanıcının seçtiği "
            'lüle yanıtta adıyla durmuyor')

    def test_alan_gonderilmese_de_cozulen_varsayilan_yankilanir(self, C):
        y = dict(A2_HIBRIT)
        y['include_plots'] = False
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/calculate', json=y)
        g = r.get_json() or {}
        assert (g.get('motor') or {}).get('nozzle_type') == 'conical'

    def test_taninmayan_lule_hala_adli_ret_aliyor(self, C):
        """Yankı, P16B1-21'in reddini gevşetmez."""
        y = dict(A2_HIBRIT)
        y['nozzle_type'] = 'peynir'
        y['include_plots'] = False
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/calculate', json=y)
        assert r.status_code == 400
        assert (r.get_json() or {}).get('error') == 'unresolved_nozzle_type'


# =====================================================================
# P7B4-24 — aynı sınıf büyüklüğe TEK kapı
# =====================================================================
class TestP7B424SifirBasincIkiKapi:
    """ÖLÇÜLDÜ (once.json K7): ``P_ambient_Pa = 0`` (vakum) HTTP 200 + tam
    çözüm alıyordu, ``Pb_Pa = 0`` ise ``"'Pb_Pa' must be > 0"`` ile 400.
    İkisi de mutlak basınç; fark yalnız ``strict`` bayrağıydı.
    """

    def test_vakum_geri_basinci_artik_kabul(self, C):
        y = dict(A2_CFD_TABAN)
        y['Pb_Pa'] = 0.0
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/cfd/nozzle', json=y)
        assert r.status_code == 200, (
            'Pb_Pa=0 hâlâ HTTP %s: kardeş alan P_ambient_Pa=0 kabul ederken '
            'aynı sınıf büyüklük reddediliyor' % r.status_code)
        cfd = (r.get_json() or {}).get('cfd') or {}
        assert (cfd.get('outlet_bc') or {}).get('Pb_Pa') == pytest.approx(0.0)

    def test_vakum_ortam_basinci_kardes_kapida_da_kabul(self, C):
        y = dict(A2_CFD_TABAN)
        y['P_ambient_Pa'] = 0.0
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/cfd/nozzle', json=y)
        assert r.status_code == 200

    @pytest.mark.parametrize('alan', ['Pb_Pa', 'P_ambient_Pa'])
    def test_negatif_mutlak_basinc_iki_alanda_da_reddedilir(self, C, alan):
        """Gevşetme yalnız SIFIRA dair: negatif mutlak basınç yoktur."""
        y = dict(A2_CFD_TABAN)
        y[alan] = -1.0
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/cfd/nozzle', json=y)
        assert r.status_code == 400
        assert (r.get_json() or {}).get('field') == alan

    def test_pozitif_geri_basinc_bit_ayni_kalir(self, C):
        y = dict(A2_CFD_TABAN)
        y['Pb_Pa'] = 50000.0
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/cfd/nozzle', json=y)
        assert r.status_code == 200
        cfd = (r.get_json() or {}).get('cfd') or {}
        assert (cfd.get('outlet_bc') or {}).get('Pb_Pa') == pytest.approx(
            50000.0)


# =====================================================================
# P15B4-13 — reddin SINIFI (içeriği değil)
# =====================================================================
class TestP15B413Uc3DRetSinifi:
    """ÖLÇÜLDÜ (once.json K14): çizici ValueError / TypeError / ImportError
    attığında ÜÇÜNDE DE HTTP 500 dönüyordu — istemci "sunucu çöktü"
    görüyordu. Aynı ucun kardeş kapıları (eksik/tutarsız geometri) bu
    sınıfı zaten 422 ile reddediyor.
    """

    @staticmethod
    def _patlat_ile(C, istisna):
        import hrma.visualization.visualization as VIZ
        asil = VIZ.create_3d_motor_visualization
        try:
            VIZ.create_3d_motor_visualization = (
                lambda _md, _e=istisna: (_ for _ in ()).throw(_e))
            with contextlib.redirect_stdout(io.StringIO()):
                r = C.post('/api/generate-3d', json={'motor_data': A2_GEO_3D})
            return r.status_code, (r.get_json() or {})
        finally:
            VIZ.create_3d_motor_visualization = asil
            assert VIZ.create_3d_motor_visualization is asil

    def test_kullanilamayan_deger_istemci_sinifi_alir(self, C):
        kod, g = self._patlat_ile(C, ValueError('port diameter unusable'))
        assert kod == 422, (
            'çizici "verdiğiniz değer kullanılamaz" dediğinde istemci hâlâ '
            'HTTP %s (sunucu arızası) görüyor' % kod)
        kunye = (g.get('invalid_fields') or [{}])[0]
        assert kunye.get('reason') == 'unusable_geometry_for_drawing'

    @pytest.mark.parametrize('istisna', [TypeError('contract'),
                                         ImportError('plotly missing')])
    def test_sunucu_arizasi_500_kalir(self, C, istisna):
        """Sınıf GEVŞETİLMEZ: yalnız ValueError istemci sınıfıdır."""
        kod, _g = self._patlat_ile(C, istisna)
        assert kod == 500

    def test_ret_metni_ve_reason_alani_sozcugu_sozcugune_korunur(self, C):
        """Panel ``describe3dFailure`` bu alanları okuyor (OH-D23-15)."""
        kod, g = self._patlat_ile(C, ValueError('bad'))
        assert g.get('status') == 'visualization_failed'
        assert 'No placeholder body is returned' in (g.get('error') or '')
        assert (g.get('reason') or '').startswith('ValueError')

    def test_saglikli_yol_bit_ayni(self, C):
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/generate-3d', json={'motor_data': A2_GEO_3D})
        assert r.status_code == 200
        assert (r.get_json() or {}).get('status') == 'success'


# =====================================================================
# P7B4-16 — PDF emniyet katsayısı tautoloji bağlamı
# =====================================================================
class TestP7B416PdfTautolojiBaglami:
    """ÖLÇÜLDÜ (once.json K2): yalnız ``analysis_results`` gönderen istemcide
    çıktı sözlüğünde tabanı söyleyen HİÇBİR blok olmuyordu; ``pdf_generator``
    ``known=False`` dalına düşüp 'Minimum Safety Factor (all modes) 4.00'
    satırını BEYANSIZ basıyordu ('Design basis' notu hiç çıkmıyordu).
    """

    def test_tabani_bilinmeyen_katsayi_rapora_girmez(self):
        b = HA._build_pdf_analysis_sections(
            {'motor_name': 'BEKCI'},
            {'structural': {'safety_factor': 4.0, 'min_safety_factor': 4.0}})
        st = b.get('structural') or {}
        assert st.get('min_safety_factor') is None, (
            'tabanı bilinmeyen emniyet katsayısı hâlâ rapora giriyor — '
            'PDF onu "doğrulanmış pay" gibi basar')
        assert st.get('safety_factor') is None
        wh = b.get('structural_withheld') or {}
        assert wh.get('reason') == 'design_basis_unknown'
        assert sorted(wh.get('fields') or []) == ['min_safety_factor',
                                                  'safety_factor']
        # Sayı SİLİNMEZ, nereye gittiği söylenir (sessiz düşürme yok).
        assert (wh.get('submitted_values') or {}).get('safety_factor') == 4.0

    def test_cozucunun_durustluk_blogu_tasinir(self):
        b = HA._build_pdf_analysis_sections(
            {'motor_name': 'BEKCI'},
            {'structural': {'safety_factor': 4.0, 'min_safety_factor': 4.0},
             'structural_analysis': {
                 'chamber_analysis': {'design_mode': 'size',
                                      'safety_factor_is_tautological': True},
                 'safety_analysis': {'safety_factors': {'chamber': 4.0}}}})
        assert (b.get('structural') or {}).get('min_safety_factor') == 4.0
        assert b.get('structural_withheld') is None
        assert isinstance(b.get('structural_analysis'), dict)

    def test_design_basis_blogu_da_taban_sayilir(self):
        b = HA._build_pdf_analysis_sections(
            {'motor_name': 'BEKCI',
             'structural_design_basis': {'verdict': 'withheld',
                                         'is_verification': False}},
            {'structural': {'safety_factor': 4.0, 'min_safety_factor': 4.0}})
        assert b.get('structural_withheld') is None
        assert isinstance(b.get('structural_design_basis'), dict)

    def test_emniyet_katsayisi_yoksa_govde_bit_ayni(self):
        """ÖK-22: söylenecek bir şey yoksa blok da yazılmaz."""
        b = HA._build_pdf_analysis_sections(
            {'motor_name': 'BEKCI'}, {'performance': {'thrust': 1000.0}})
        assert 'structural_withheld' not in b
        assert not (b.get('structural') or {})

    def test_uc_yolu_tam_govde_ile_hala_200(self, C):
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/export-pdf/complete',
                       json={'motor_data': A2_PDF_MOTOR, 'analysis_results': {}})
        assert r.status_code == 200


# =====================================================================
# P12aB5-13 — sürüm notlarının sırası
# =====================================================================
class TestP12aB513SurumSirasi:
    """ÖLÇÜLDÜ (once.json K8): uç ``versions``ı dosyadaki SATIR SIRASIYLA
    döndürüyordu (``sort`` çağrısı 0). Bugün sıra doğru ama garanti eden
    hiçbir şey yok: yanlış satıra eklenen bir sürüm modalda yanlış yerde
    görünür ve hiçbir bekçi görmez.
    """

    def test_sira_sayisal_azalan_ve_beyanli(self, C):
        r = C.get('/api/changelog')
        g = r.get_json() or {}
        assert r.status_code == 200
        assert g.get('versions_order') == 'version_desc'
        anahtarlar = [tuple(int(p) for p in v['version'].split('.'))
                      for v in g['versions']]
        assert anahtarlar == sorted(anahtarlar, reverse=True)

    def test_dosya_sirasi_bozuksa_uc_duzeltir(self):
        """Kusurun kendisi: sıra artık dosyanın satır düzenine bağlı değil."""
        karisik = [{'version': '2.5.0'}, {'version': '2.6.27'},
                   {'version': '2.6.9'}, {'version': '2.3.0'},
                   {'version': '2.6.26'}]
        sirali, cozulemeyen = HA._changelog_sirali(karisik)
        assert [x['version'] for x in sirali] == [
            '2.6.27', '2.6.26', '2.6.9', '2.5.0', '2.3.0']
        assert cozulemeyen == []

    def test_cozulemeyen_surum_dusurulmez_soylenir(self):
        """Sessiz düşürme yok: ayrıştırılamayan kayıt listede kalır."""
        sirali, cozulemeyen = HA._changelog_sirali(
            [{'version': 'peynir'}, {'version': '2.6.27'},
             {'version': '2.7.0-rc1'}])
        assert len(sirali) == 3
        assert sirali[0]['version'] == '2.6.27'
        assert cozulemeyen == ['peynir', '2.7.0-rc1']

    def test_paketli_dosyada_kayip_yok(self, C):
        ham = json.loads(
            (KOK / 'hrma' / 'data' / 'changelog.json').read_text(
                encoding='utf-8'))
        g = C.get('/api/changelog').get_json() or {}
        assert len(g['versions']) == len(ham['versions'])
        assert ({v['version'] for v in g['versions']}
                == {v['version'] for v in ham['versions']})


# =====================================================================
# P7B4-17 — korelasyon docstring'inin süre iddiası
# =====================================================================
class TestP7B417KorelasyonSureIddiasi:
    """ÖLÇÜLDÜ (P07 bulucu koşumu): ``generated_s = 112,229`` s; docstring
    "~15-25 s" diyordu (iddianın 4,5-7,5 katı) ve 13 satır yukarıdaki yorum
    bunun yanlış olduğunu ZATEN yazıyordu.
    """

    def test_docstring_curutulmus_sureyi_iddia_etmiyor(self):
        ds = HA._correlation_report_body.__doc__ or ''
        # İDDİA biçimi aranır: "15-25" dizesi düzeltme metninde ALINTI
        # olarak geçebilir; yasak olan onu SÜRE olarak ileri sürmektir.
        for iddia in ('~15-25 s sürer', 'Koşu ~15-25', '15-25 s sürer'):
            assert iddia not in ds, (
                'docstring hâlâ ölçümle çürütülmüş süreyi iddia ediyor: %r'
                % iddia)

    def test_docstring_olculen_sureyi_ve_kaynagini_soyluyor(self):
        ds = HA._correlation_report_body.__doc__ or ''
        assert '112,2' in ds
        assert 'generated_s' in ds, (
            'süre sabit bir sayı değil; okunacağı alan yazılı olmalı')

    def test_ayni_dosyadaki_iki_metin_artik_celismiyor(self):
        """Yorum "docstring '~15-25 s' diyordu" derken docstring'de o iddia
        BULUNMAMALI (D26 dersi 3: çelişki tek dosyada kalmasın)."""
        i = A2_APP_KAYNAK.index('def _correlation_report_body')
        govde = A2_APP_KAYNAK[i:i + 2500]
        ds = govde.split('"""')[1]
        assert '~15-25 s sürer' not in ds


# =====================================================================
# P7B4-23 — upload-csv satır sınırı (KISMEN: ölçüm dondurulur)
# =====================================================================
class TestP7B423CsvSatirSiniri:
    """ÖLÇÜLDÜ (once.json K6/K15): 600 000 satır (9,6 MiB gövde) HTTP 200,
    8,2 MiB yanıt, 0,77 s — ayrıştırılan seri olduğu gibi yankılanıyor.
    Ucun KENDİ satır kapısı YOK; kaynak bağlı olduğu sınır, v2.6.2'de tam
    bu uç için konmuş ``MAX_CONTENT_LENGTH`` gövde tavanıdır.

    KALEM KISMEN: kanonik bir satır bandı depoda YOK ve SAYI UYDURULMADI
    (Doktrin 4 / ÖK-18). Band ``parse_thrust_csv``in yanında tanımlanmalıdır
    (``hrma/validation/user_data_validation.py``) — o dosya
    **app-api-dogrulama** kulvarınındır; devir raporda ilan edildi. Bu bekçi
    bugünkü sınırı DONDURUR: gövde tavanı sessizce kalkarsa kırmızı verir.
    """

    def test_govde_tavani_bu_ucun_gerekcesiyle_duruyor(self):
        assert app.config.get('MAX_CONTENT_LENGTH') == 32 * 1024 * 1024
        i = A2_APP_KAYNAK.index("app.config['MAX_CONTENT_LENGTH']")
        assert 'upload-csv' in A2_APP_KAYNAK[i - 500:i]

    def test_satir_sayisi_govde_tavaniyla_sinirli(self, C):
        """Sınır ÜCTE değil gövde tavanındadır — ölçülen bağıntı donduruldu."""
        tavan = app.config['MAX_CONTENT_LENGTH']
        satirlar = ['%.4f,%.3f' % (i * 0.001, 100.0 + (i % 50))
                    for i in range(1000)]
        govde = 'time,thrust\n' + '\n'.join(satirlar) + '\n'
        r = C.post('/api/validation/upload-csv', data=govde.encode('utf-8'),
                   content_type='text/csv')
        assert r.status_code == 200, (r.get_json() or {}).get('error')
        g = r.get_json() or {}
        assert g['parsed']['n_points'] == 1000
        # Bir satır en az bu kadar bayt; tavan satır sayısını sınırlar.
        assert tavan // (len(satirlar[0]) + 1) < 2_500_000

    def test_ayristirici_sahasi_devredildi(self):
        """Kanonik band bu dosyada TANIMLANMADI (ikinci tanım yazılmaz)."""
        assert 'csv_row_limit' not in A2_APP_KAYNAK
        assert 'MAX_CSV_ROWS' not in A2_APP_KAYNAK


# =====================================================================
# ÖNCEKİ DALGALARDA ONARILMIŞ — kilit bekçileri (yeniden gerileme yasağı)
# =====================================================================
class TestOncekiDalgaKilitleri:
    """Bu dört kalem defterde AÇIK duruyordu ama a2 ölçümü onları TABANDA
    ONARILMIŞ buldu. Çürütme DEĞİL: onarım başka bir dalgada yapılmış
    (hüküm-18 dersi). Kilit bekçisi gerilemeyi yakalar.
    """

    @pytest.mark.parametrize('tur', ['HAYALET', 'analysis'])
    def test_p7b415_bilinmeyen_rapor_turu_adiyla_reddedilir(self, C, tur):
        """D29 a2 · P16B4-20 (commit d75e23a5)."""
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/export-pdf/%s' % tur,
                       json={'motor_data': A2_PDF_MOTOR, 'analysis_results': {}})
        assert r.status_code == 400
        g = r.get_json() or {}
        assert g.get('error') == 'unknown_report_type'
        assert set(HA.PDF_REPORT_TYPES) == {'summary', 'technical', 'complete'}

    @pytest.mark.parametrize('n', [1, 10001])
    def test_p7b420_n_samples_sessizce_degismez(self, C, n):
        """D24 a1 · P16B3-08 (commit 6109d5f5)."""
        y = {'motor_type': 'hybrid', 'level': 'fast', 'n_samples': n,
             'inputs': {'thrust': 5000, 'burn_time': 10, 'of_ratio': 6.0,
                        'chamber_pressure': 20, 'fuel_type': 'htpb',
                        'oxidizer_type': 'n2o'}}
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/uncertainty-analysis', json=y)
        assert r.status_code == 400
        assert (r.get_json() or {}).get('error') == 'n_samples_out_of_range'

    def test_p7b420_kesirli_tohum_reddedilir(self, C):
        y = {'motor_type': 'hybrid', 'level': 'fast', 'seed': 3.7,
             'n_samples': 60,
             'inputs': {'thrust': 5000, 'burn_time': 10, 'of_ratio': 6.0,
                        'chamber_pressure': 20, 'fuel_type': 'htpb',
                        'oxidizer_type': 'n2o'}}
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/uncertainty-analysis', json=y)
        assert r.status_code == 400

    def test_p7b422_temsil_edilemeyen_hucre_dosya_yayimlatmaz(self, C):
        """D29 a2 · P16B4-23 (commit d75e23a5)."""
        govde = ('{"filename":"t.xlsx","sheets":[{"name":"s",'
                 '"headers":["v"],"rows":[[NaN],[Infinity],[1.5]]}]}')
        r = C.post('/api/export-xlsx', data=govde,
                   content_type='application/json')
        assert r.status_code == 422
        assert (r.get_json() or {}).get('error') == 'unrepresentable_cell'

    @pytest.mark.parametrize('deger', ['false', '0', 'no'])
    def test_p16b140_dize_bayragi_ters_calismiyor(self, C, deger):
        """D29 a2 · P7B1-20 (commit d75e23a5)."""
        y = dict(A2_HIBRIT)
        y['include_plots'] = deger
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/calculate', json=y)
        assert r.status_code == 200
        plots = (r.get_json() or {}).get('plots')
        assert not (plots and any(v for v in plots.values())), (
            'include_plots=%r figür üretiyor — bool(dize) tuzağı geri geldi'
            % deger)

    def test_p16b140_okunamayan_bayrak_adiyla_reddedilir(self, C):
        y = dict(A2_HIBRIT)
        y['include_plots'] = 'peynir'
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/calculate', json=y)
        assert r.status_code == 422
        assert (r.get_json() or {}).get('error') == 'invalid_flag'

    @pytest.mark.parametrize('final', [0.02, 0.50])
    def test_p16b141_port_diameter_final_artik_okunuyor(self, C, final):
        """D23 yapisal-sistem a2 · P5B4-11 (commit 4613081a)."""
        motor = {'burn_time': 10.0, 'mdot_ox': 2.0,
                 'port_diameter_initial': 0.10, 'grain_length': 0.5,
                 'regression_a': 0.0001, 'regression_n': 0.5,
                 'fuel_density': 920.0, 'fuel_type': 'htpb'}
        motor['port_diameter_final'] = final
        with contextlib.redirect_stdout(io.StringIO()):
            r = C.post('/api/regression-analysis', json={'motor_data': motor})
        assert r.status_code == 200
        assert 'port_diameter_final_check' in json.dumps(r.get_json() or {}), (
            'port_diameter_final yine sessizce yutuluyor')
