# -*- coding: utf-8 -*-
"""ÖH Dalga-20 / kulvar KATI, aşama 1 — bekçiler.

Kalemler:
  OH-D19-23a  ``core_diameter`` ret künyesi kendi kapısının reddettiği iki
              ucu "kabul edilir" ilan ediyordu (accepted_range [0, D]).
  OH-D19-23b  ``_geometric_burnout_web`` her hatayı sessizce yutup radyal ete
              düşüyordu; ürün yüzü paydayı yine "yanan alanın sıfırlandığı
              kalınlık" diye anlatıyordu.
  P15B3-05    ``c_star`` ölü anahtar: ne bağlı ne beyanlı (üçüncü seçenek —
              sessizlik).
  P2B3-13     Boğaz gövdeyi aşınca boy alanları None dönüyor ama kullanıcıya
              SEBEBİNİ söyleyen tek bir uyarı yok.

Ölçüm kanıtı: docs/scofield/raw/OH/D20/kati/a1/once.json / sonra.json.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hrma.engines.solid_rocket_engine import (  # noqa: E402
    SolidGeometryError,
    SolidRocketEngine,
    _core_diameter_domain,
    _solid_geometry_gate,
)

TEMEL = dict(grain_type='bates', propellant_type='apcp', chamber_diameter=100,
             grain_length=500, core_diameter=30, chamber_pressure=40)


def _motor(**kw):
    p = dict(TEMEL)
    p.update(kw)
    return SolidRocketEngine(**p)


# ---------------------------------------------------------------------------
# OH-D19-23a — künye kendi kapısıyla çelişmez
# ---------------------------------------------------------------------------
class TestKabulKumesiKapiylaCelismez:

    @pytest.mark.parametrize('core,sebep', [
        (0.0, 'zero_port'),
        (100.0, 'core_not_inside_case'),
        (-5.0, 'negative_core'),
    ])
    def test_reddedilen_deger_kabul_kumesinin_disindadir(self, core, sebep):
        """Künyenin ilan ettiği kümede REDDEDİLEN değer bulunamaz.

        Bu testin altın değeri üründen İTHAL EDİLMEZ: kabul kümesi künyeden
        okunur ve reddedilen sayının o kümeye düşüp düşmediği burada,
        bağımsız olarak yeniden karara bağlanır.
        """
        with pytest.raises(SolidGeometryError) as ex:
            _solid_geometry_gate('bates', 100.0, 500.0, core, 40.0, 0.005)
        k = ex.value.kunye
        assert k['reason'] == sebep
        alt, ust = k['accepted_range']
        alt_acik, ust_acik = k['accepted_range_exclusive']

        def icinde(x):
            if alt is not None and (x < alt or (alt_acik and x == alt)):
                return False
            if ust is not None and (x > ust or (ust_acik and x == ust)):
                return False
            return True

        assert not icinde(core), (
            'kapı %r değerini reddetti ama künye onu kabul kümesinde '
            'gösteriyor: %r' % (core, k))

    def test_kabul_kumesindeki_deger_kapidan_gecer(self):
        """Künye tersinden de doğru: kümenin içi gerçekten geçiyor."""
        k = _core_diameter_domain('bates', 100.0)
        alt, ust = k['accepted_range']
        assert alt < ust, 'kabul kümesi boş: [%s, %s]' % (alt, ust)
        # ÖH D24 / OH-D23-01: gövde İDDİASIZDI — kapı sessizce her şeyi
        # kabul etse de test yeşildi. Kümenin İÇİ geçmeli, DIŞI geçmemeli;
        # ikisi birlikte sınanır, yoksa "geçiyor" iddiası vakumluk kalır.
        for x in (alt + 1e-6, (alt + ust) / 2.0, ust - 1e-6):
            assert _solid_geometry_gate(
                'bates', 100.0, 500.0, x, 40.0, 0.005) is None, (
                'kabul kümesindeki %s değeri kapıdan geçmedi' % x)
        for disarida in (alt - 1e-3, ust + 1e-3):
            with pytest.raises(Exception):
                _solid_geometry_gate('bates', 100.0, 500.0, disarida,
                                     40.0, 0.005)

    def test_end_burner_sifir_portu_kabul_eder_ve_bunu_soyler(self):
        """end_burner'da 0 gerçekten kabul edilir; küme onu dışlamaz."""
        _solid_geometry_gate('end_burner', 100.0, 500.0, 0.0, 40.0, 0.005)
        k = _core_diameter_domain('end_burner', 100.0)
        assert k['accepted_range_exclusive'] == [False, False]
        assert k['accepted_range'][0] == 0.0

    def test_kabul_kumesi_tek_tanim_noktasindan_gelir(self):
        """Üç künye de AYNI kaynağı taşır (kopyalanmış aralık yok)."""
        beklenen = _core_diameter_domain('bates', 100.0)
        for core in (0.0, 100.0, -5.0):
            with pytest.raises(SolidGeometryError) as ex:
                _solid_geometry_gate('bates', 100.0, 500.0, core, 40.0, 0.005)
            k = ex.value.kunye
            for alan in ('accepted_range', 'accepted_range_exclusive',
                         'accepted_range_text'):
                assert k[alan] == beklenen[alan], (core, alan)


# ---------------------------------------------------------------------------
# OH-D19-23b — geometrik tükeniş kazanılamazsa payda bunu SÖYLER
# ---------------------------------------------------------------------------
class TestPaydaKendiKaynaginiSoyler:

    def test_saglikli_poligon_geometrik_paydayi_kullanir(self):
        m = _motor(grain_type='star')
        m._available_web_thickness()
        assert m._available_web_basis['source'] == 'geometric_burnout_web'
        assert m._burnout_web_status == 'geometric'

    def test_hata_sessizce_radyal_ete_dusmez(self, monkeypatch):
        """Geometrik tükeniş patlarsa payda değişir ve DEĞİŞTİĞİNİ söyler."""
        m = _motor(grain_type='star')

        def patlat(self):
            raise RuntimeError('bekçi: zorlanmış shapely hatası')

        monkeypatch.setattr(SolidRocketEngine, '_max_web_thickness', patlat)
        m._burnout_web_memo = None
        deger = m._geometric_burnout_web()
        assert deger is None                      # sayı UYDURULMAZ
        assert m._burnout_web_status.startswith('failed: RuntimeError'), (
            m._burnout_web_status)
        w = m._available_web_thickness()
        assert m._available_web_basis['source'] == 'radial_web_fallback'
        assert m._available_web_basis['geometric_burnout_status'].startswith(
            'failed: RuntimeError')
        assert w == pytest.approx((m.D_chamber - m.D_core) / 2)

    def test_bates_paydasi_radyal_oldugunu_soyler(self):
        m = _motor(grain_type='bates')
        m._available_web_thickness()
        assert m._available_web_basis['source'] == 'radial_web'

    def test_urun_yuzu_paydanin_kaynagini_yayimliyor(self):
        m = _motor(grain_type='star')
        r = m.calculate_performance()
        gra = r['detailed_analysis']['grain_regression_analysis']
        assert 'web_consumable_basis' in gra
        assert gra['web_consumable_basis']['source'] in (
            'geometric_burnout_web', 'radial_web', 'radial_web_fallback',
            'axial_grain_length')
        # Düzyazı artık makinece okunur alana ATIF yapar; tek kaynak.
        assert 'web_consumable_basis' in gra['web_thickness_utilization_basis']


# ---------------------------------------------------------------------------
# P15B3-05 — c_star: ya bağlı ya beyanlı; sessizlik yok
# ---------------------------------------------------------------------------
class TestCstarSessizKalmiyor:

    def test_c_star_beyan_ediliyor(self):
        m = _motor()
        beyan = m.unwired_inputs()
        tum = [x for v in beyan.values() for x in v]
        assert 'c_star' in tum, (
            'c_star ne bağlı ne beyanlı: modülün kendi kuralının yasakladığı '
            'üçüncü seçenek (sessizlik). Beyan grupları: %r'
            % {k: v for k, v in beyan.items()})

    def test_beyan_gerekcesiyle_birlikte_duruyor(self):
        """Beyan bir GRUBUN içindedir; grup adı gerekçeyi taşır."""
        beyan = _motor().unwired_inputs()
        gruplar = [g for g, v in beyan.items() if 'c_star' in v]
        assert gruplar == ['result_of_catalogue_thermochemistry'], gruplar

    def test_beyan_curumemis_c_star_gercekten_olu(self):
        """Beyan çürümesi bekçisi: alan sonradan bağlanırsa bu test kırılır.

        Ürün sabitinden altın değer ithal edilmez; ölü olup olmadığı
        yayımlanan gövdenin kendisiyle ölçülür.
        """
        from hrma.app import app
        app.config['TESTING'] = True
        cli = app.test_client()
        yuk = {'motor_name': 'X', 'propellant_type': 'apcp',
               'grain_type': 'bates', 'chamber_pressure': 40.0,
               'thrust': 5000.0, 'burn_time': 3.0,
               'chamber_diameter': 100.0, 'grain_length': 500.0,
               'core_diameter': 30.0, 'expansion_ratio': 8.0}
        taban = cli.post('/calculate_solid', json=yuk).get_data(as_text=True)
        for v in (900.0, 2400.0):
            y = dict(yuk, c_star=v)
            assert cli.post('/calculate_solid', json=y).get_data(
                as_text=True) == taban, (
                'c_star artık sonucu değiştiriyor (%r): alan CANLI, '
                'unwired_inputs beyanı çürüdü — beyan kaldırılmalı.' % v)


# ---------------------------------------------------------------------------
# P2B3-13 — boğaz gövdeyi aşınca kullanıcı SEBEBİNİ görür
# ---------------------------------------------------------------------------
class TestBogazGovdeyiAsincaEkranUyarisi:

    @staticmethod
    def _asan_motor():
        return _motor(grain_length=3000, core_diameter=15,
                      chamber_pressure=10)

    def test_asim_gerceklesiyor_ve_boy_yayimlanmiyor(self):
        r = self._asan_motor().calculate_performance()
        nd = r['cad_design']['nozzle_design']
        assert nd['throat_exceeds_case'] is True
        assert nd['convergent_length'] is None
        assert nd['convergent_length_status'] == 'not_physical'

    def test_ekran_uyarisi_var(self):
        r = self._asan_motor().calculate_performance()
        kodlar = {w['code'] for w in r['warnings'] if isinstance(w, dict)}
        assert 'warn.solid.throat_exceeds_case' in kodlar, sorted(kodlar)

    def test_uyari_kritik_ve_olculen_sayilari_tasiyor(self):
        r = self._asan_motor().calculate_performance()
        uy = [w for w in r['warnings']
              if isinstance(w, dict)
              and w['code'] == 'warn.solid.throat_exceeds_case'][0]
        assert uy['severity'] == 'critical'
        p = uy['params']
        assert p['throat_diameter_mm'] > p['chamber_diameter_mm']
        assert p['ratio'] == pytest.approx(
            p['throat_diameter_mm'] / p['chamber_diameter_mm'], rel=1e-3)

    def test_saglikli_motorda_uyari_YOK(self):
        """Kapı gevşemiyor da daralmıyor da: normal motorda uyarı çıkmaz."""
        r = _motor().calculate_performance()
        kodlar = {w['code'] for w in r['warnings'] if isinstance(w, dict)}
        assert 'warn.solid.throat_exceeds_case' not in kodlar

    def test_uyari_kodu_iki_dilde_de_tanimli(self):
        """EN + TR karşılığı olmayan kod ekrana ham anahtar basar."""
        yol = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'hrma', 'static', 'js',
            'i18n_common.js')
        metin = open(yol, encoding='utf-8').read()
        assert metin.count("'warn.solid.throat_exceeds_case':") == 2, (
            'EN ve TR bloklarının ikisinde de bulunmalı')


# ---------------------------------------------------------------------------
# OH-D17-25 — 'Heat Release Rate' hangi anın gücü olduğunu SÖYLER
# ---------------------------------------------------------------------------
_SOLID_HTML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'hrma', 'templates', 'solid.html')


class TestIsilGucCalismaNoktasiEkranaIniyor:

    def test_cozucu_calisma_noktasini_yayimliyor(self):
        r = _motor(grain_type='wagon_wheel').calculate_performance()
        ct = r['thermal_analysis']['combustion_thermal']
        assert ct['heat_release_rate_status'] == 'solved'
        assert isinstance(ct['heat_release_rate_operating_point'], str)
        assert ct['heat_release_rate_operating_point']
        # Basılan sayı gerçekten TEPE; başlangıç ve ortalama ayrı alanlarda.
        assert ct['heat_release_rate_mw'] >= ct['heat_release_rate_average_mw']
        assert ct['heat_release_rate_mw'] >= ct['heat_release_rate_initial_mw']

    def test_satir_calisma_noktasini_basiyor(self):
        metin = open(_SOLID_HTML, encoding='utf-8').read()
        satir = [s for s in metin.splitlines()
                 if "'heat_release_rate_mw'" in s]
        assert len(satir) == 1, satir
        assert 'hrrOperatingPoint(combustionThermal)' in satir[0], satir[0]

    def test_calisma_noktasi_metni_ekranda_YENIDEN_YAZILMIYOR(self):
        """Tek kaynak: yardımcı, metni çözücünün alanından okur."""
        metin = open(_SOLID_HTML, encoding='utf-8').read()
        i = metin.index('function hrrOperatingPoint(ct) {')
        govde = metin[i:metin.index('\n        }', i)]
        assert 'heat_release_rate_operating_point' in govde
        for uydurma in ("'peak", '"peak', 'tepe of', 'PEAK of'):
            assert uydurma not in govde, uydurma

    def test_alan_yoksa_hicbir_sey_eklenmiyor(self):
        """Sayı uydurma yasağı: beyan gelmezse ekrana ek metin çıkmaz."""
        metin = open(_SOLID_HTML, encoding='utf-8').read()
        i = metin.index('function hrrOperatingPoint(ct) {')
        govde = metin[i:metin.index('\n        }', i)]
        assert "return '';" in govde
