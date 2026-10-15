# -*- coding: utf-8 -*-
"""ÖH D22 / yapisal-sistem a1 — onarım bekçileri.

Her sınıf bir kalemin ters-mutasyonla kırmızıya döndüğü ölçülmüş kilididir.
Kanıt: ``docs/scofield/raw/OH/D22/yapisal-sistem/a1/`` (once*.json,
sonra*.json, mutasyon.json, capa_*.json).
"""
import json
import os
import re
import shutil
import tempfile

import pytest

from hrma.analysis import tile_cache
from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.analysis.structural_analysis import (NonPhysicalStructuralInput,
                                               StructuralAnalyzer)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _yapisal(client, **ek):
    yuk = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
           'chamber_length': 0.5, 'throat_diameter': 0.02,
           'material': 'steel_4130'}
    yuk.update(ek)
    r = client.post('/analyze_structural_safety', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return (r.get_json()['structural_analysis'])['safety_analysis']


# ===================================================================== P7B3-23
class TestP7B323MansetSayisi:
    """Manşete yalnız KAZANILMIŞ hüküm sayısı çıkar.

    ÖLÇÜLDÜ (once.json P7B3-23): cidar 5/15/25/35/45 mm boyunca
    ``minimum_safety_factor`` SABİT 3,9999999999999996 (hedefin geri
    okunması) iken ``minimum_earned_safety_factor`` 7,6433 -> 31,8224;
    hangisinin manşet olduğunu söyleyen alan YOKTU.
    """

    def test_manset_alani_var_ve_hukumle_ayni(self, client):
        sa = _yapisal(client, wall_thickness=0.025)
        assert 'headline_safety_factor' in sa
        assert 'headline_safety_factor_source' in sa
        assert sa['headline_safety_factor'] == sa['verdict_safety_factor']

    def test_hukum_geri_cekilmisken_manset_sayisi_yok(self, client):
        """Hedefin geri okunması manşete TERFİ ETTİRİLMEZ (fail-closed)."""
        for cidar in (0.005, 0.025, 0.045):
            sa = _yapisal(client, wall_thickness=cidar)
            if not sa['verdict_withheld']:
                continue
            assert sa['headline_safety_factor'] is None, (
                'hüküm geri çekilmişken manşet sayısı yayımlanıyor: %r'
                % sa['headline_safety_factor'])
            kaynak = sa['headline_safety_factor_source']
            assert 'withheld' in kaynak
            # Gerekçe İKİ adayı da adıyla reddetmeli.
            assert 'minimum_safety_factor' in kaynak
            assert 'minimum_earned_safety_factor' in kaynak

    def test_iki_aday_ayrisiyor_ve_ikisi_de_kunyeli(self, client):
        """4,0 ⟷ 25,46 çelişkisinin ölçümü: sayılar ayrışır, adları ayrıdır."""
        okunan = []
        for cidar in (0.005, 0.015, 0.025, 0.035, 0.045):
            sa = _yapisal(client, wall_thickness=cidar)
            okunan.append((sa['minimum_safety_factor'],
                           sa['minimum_earned_safety_factor']))
        sepet = {round(a, 9) for a, _ in okunan}
        assert len(sepet) == 1, 'sepet minimumu artık hedefin ekosu değil'
        kazanilmis = [b for _, b in okunan]
        assert kazanilmis == sorted(kazanilmis), kazanilmis
        assert kazanilmis[-1] > kazanilmis[0] * 3


# ===================================================================== OH-Z4-03
class TestOHZ403OgutOlculmusSayidan:
    """Hiçbir istasyon ölçülmemişken cidar öğüdü hedefin ekosundan çıkmaz.

    ÖLÇÜLDÜ (once.json OH-Z4-03): cidar VERİLMEDEN, SF hedefi 1,5 ve 2,0
    için dört öneri (increase_wall_thickness dâhil) basılıyordu.
    """

    @pytest.mark.parametrize('hedef', [1.5, 2.0])
    def test_olculmemis_koumda_kalinlastir_ogudu_yok(self, client, hedef):
        sa = _yapisal(client, safety_factor=hedef)
        assert sa['verdict_scope'] == []
        kodlar = [r.get('code') for r in (sa.get('recommendations') or [])]
        assert not any('increase_wall_thickness' in str(k) for k in kodlar), (
            'öğüt hedefin geri okunmasından çıkıyor: %r' % (kodlar,))
        assert not any('increase_chamber_wall' in str(k) for k in kodlar)
        assert 'recommendation_basis' in sa
        assert 'measured' in sa['recommendation_basis']

    def test_olculmus_dusuk_sf_ogudu_susturulmaz(self, client):
        """UYARI SUSTURULMAZ: gerçek cidar ölçülüp düşük çıkarsa öğüt gelir."""
        sa = _yapisal(client, wall_thickness=0.0008, safety_factor=2.0)
        olculdu = [i for i in (sa.get('verdict_scope') or [])]
        if not olculdu:
            pytest.skip('bu yükte ölçülmüş istasyon yok')
        kodlar = [r.get('code') for r in (sa.get('recommendations') or [])]
        if sa.get('minimum_earned_safety_factor') is not None and \
                sa['minimum_earned_safety_factor'] < 3.0:
            assert any('increase' in str(k) for k in kodlar), kodlar


# =========================================================== P5B1-16 / P5B1-18
class TestP5B116GirdiKapisi:
    """Modül seviyesinde fiziksel olmayan girdi reddedilir (fail-closed).

    ÖLÇÜLDÜ (once.json P5B1-16_18): -0,1 m çap sessizce -3,139994 mm cidar
    önerisi; -40 bar NaN toplam ağırlık; 0 bar ham ZeroDivisionError.
    """

    @pytest.mark.parametrize('alan,deger', [
        ('chamber_diameter', -0.1),
        ('chamber_pressure', -40.0),
        ('chamber_pressure', 0.0),
        ('chamber_length', 0.0),
        ('throat_diameter', -0.02),
    ])
    def test_fiziksel_olmayan_deger_adiyla_reddedilir(self, alan, deger):
        md = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
              'chamber_length': 0.5, 'throat_diameter': 0.02}
        md[alan] = deger
        with pytest.raises(NonPhysicalStructuralInput) as exc:
            StructuralAnalyzer().analyze_structure(md)
        adlar = [k['field'] for k in exc.value.invalid_fields]
        assert alan in adlar, exc.value.invalid_fields
        kayit = [k for k in exc.value.invalid_fields if k['field'] == alan][0]
        assert kayit['reason'] == 'not_positive'
        assert kayit['detail']

    def test_sifir_basinc_ham_zerodivision_vermez(self):
        md = {'chamber_pressure': 0, 'chamber_diameter': 0.1,
              'chamber_length': 0.5, 'throat_diameter': 0.02}
        sonuc = 'ham'
        try:
            StructuralAnalyzer().analyze_structure(md)
            sonuc = 'gecti'
        except NonPhysicalStructuralInput:
            sonuc = 'adli_ret'
        except ZeroDivisionError:                       # pragma: no cover
            pytest.fail('ham ZeroDivisionError hâlâ dışarı sızıyor')
        assert sonuc in ('adli_ret', 'gecti')  # fix-19: sonuç açıkça iddia edilir (ÖK-22 nüfus tavanı)

    def test_saglikli_girdi_gecer(self):
        r = StructuralAnalyzer().analyze_structure(
            {'chamber_pressure': 40, 'chamber_diameter': 0.1,
             'chamber_length': 0.5, 'throat_diameter': 0.02})
        assert r['chamber_analysis']['recommended_thickness'] > 0


class TestP5B118VarsayilanBeyani:
    """Boş sözlükten çıkan sayı takımı artık kaynağını söylüyor."""

    def test_bos_sozlukte_her_varsayilan_adiyla_beyan_edilir(self):
        r = StructuralAnalyzer().analyze_structure({})
        beyan = r['inputs_defaulted']
        assert set(beyan) >= {'chamber_pressure', 'chamber_diameter',
                              'chamber_length', 'throat_diameter'}
        assert beyan['chamber_pressure']['value'] == 20.0
        assert beyan['chamber_pressure']['unit'] == 'bar'
        assert beyan['chamber_diameter']['value'] == 0.1
        for k in beyan.values():
            assert k['reason']
        assert r['inputs_defaulted_basis']

    def test_tam_girdide_beyan_bos(self):
        r = StructuralAnalyzer().analyze_structure(
            {'chamber_pressure': 40, 'chamber_diameter': 0.1,
             'chamber_length': 0.5, 'throat_diameter': 0.02,
             'nozzle_type': 'conical'})
        assert r['inputs_defaulted'] == {}


# ===================================================================== P5B1-20
class TestP5B120ProofKipeBagli:
    """AIAA proof çarpanı ASME VIII kipine sızmıyor.

    ÖLÇÜLDÜ (once.json P5B1-20): her iki kipte de proof_pressure_bar 90,00
    bar (= 1,5 x 60 bar MEOP).
    """

    def test_asme_kipinde_proof_yayimlanmaz(self):
        r = PressureVesselAnalyzer().analyze(
            meop_bar=60.0, inner_diameter_mm=150.0, material='steel_4130',
            wall_thickness_mm=3.0, code_mode='asme_viii')
        assert r['proof_pressure_bar'] is None
        assert 'ASME' in r['proof_pressure_basis']
        assert 'hydrostatic_test_pressure_bar' in r['proof_pressure_basis']
        assert r['hydrostatic_test_pressure_bar'] > 0

    def test_aiaa_kipinde_proof_aynen_durur(self):
        r = PressureVesselAnalyzer().analyze(
            meop_bar=60.0, inner_diameter_mm=150.0, material='steel_4130',
            wall_thickness_mm=3.0, code_mode='aiaa_s080')
        assert r['proof_pressure_bar'] == pytest.approx(90.0, rel=1e-9)
        assert 'S-080' in r['proof_pressure_basis']


# ===================================================================== P5B4-25
class TestP5B425BozukKaroSunulmaz:
    """0 baytlık dosya / düz metin geçerli karo sayılmaz.

    ÖLÇÜLDÜ (once_p5b425.json, taban b84b10a): ikisi de
    ``ok=True, cached=True, mimetype='image/jpeg'`` ile sunuluyordu.
    """

    @pytest.fixture
    def onbellek(self, tmp_path, monkeypatch):
        kok = str(tmp_path / 'tiles')
        os.makedirs(kok, exist_ok=True)
        monkeypatch.setattr(tile_cache, 'tiles_root', lambda: kok)
        monkeypatch.setattr(
            tile_cache, '_http_bytes',
            lambda url, t: b'\xff\xd8\xff\xe0' + b'\x00' * 200 + b'\xff\xd9')
        return kok

    @pytest.mark.parametrize('bozuk', [
        b'', b'<html>404 not found</html>', b'not an image at all'])
    def test_bozuk_karo_yeniden_cekilir(self, onbellek, bozuk):
        katman = tile_cache.DEFAULT_TILE_LAYER
        cfg = tile_cache.layer_config(katman)
        tarih = '2024-01-01' if cfg['time'] else None
        yol = tile_cache._tile_path(onbellek, katman, tarih or 'default',
                                    3, 4, 2, cfg['ext'])
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, 'wb') as fh:
            fh.write(bozuk)
        r = tile_cache.resolve_tile(katman, 3, 4, 2, tarih)
        assert r['ok'] is True
        assert r['cached'] is False, 'bozuk bayt önbellek HIT olarak sunuldu'
        assert os.path.getsize(yol) > len(bozuk)
        with open(yol, 'rb') as fh:
            assert fh.read(3) == b'\xff\xd8\xff'

    def test_gecerli_karo_onbellekten_sunulmaya_devam_eder(self, onbellek):
        katman = tile_cache.DEFAULT_TILE_LAYER
        cfg = tile_cache.layer_config(katman)
        tarih = '2024-01-01' if cfg['time'] else None
        yol = tile_cache._tile_path(onbellek, katman, tarih or 'default',
                                    3, 4, 2, cfg['ext'])
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        gecerli = b'\xff\xd8\xff\xe0' + b'\x00' * 64
        with open(yol, 'wb') as fh:
            fh.write(gecerli)
        r = tile_cache.resolve_tile(katman, 3, 4, 2, tarih)
        assert r['ok'] is True and r['cached'] is True
        assert os.path.getsize(yol) == len(gecerli)


# ===================================================================== P5B4-26
class TestP5B426CapTaramasi:
    """_enforce_cap her yazımda tam os.walk yapmıyor; cap yine dayatılıyor.

    ÖLÇÜLDÜ (once.json P5B4-26): 20 çağrıda 20 tarama; 200 karo 0,7226 ms,
    2000 karo 5,374 ms.
    """

    def test_cap_altinda_tekrarli_cagri_tek_tarama_yapar(self, tmp_path,
                                                         monkeypatch):
        kok = str(tmp_path / 'tiles' / 'L' / 'd' / '3')
        os.makedirs(kok, exist_ok=True)
        for i in range(120):
            with open(os.path.join(kok, '%d.jpg' % i), 'wb') as fh:
                fh.write(b'\xff\xd8\xff\xe0' + b'\x00' * 20)
        root = str(tmp_path / 'tiles')
        tile_cache._usage_cache.pop(root, None)
        sayac = {'n': 0}
        gercek = os.walk

        def _sayan(*a, **kw):
            sayac['n'] += 1
            return gercek(*a, **kw)

        monkeypatch.setattr(os, 'walk', _sayan)
        for _ in range(20):
            tile_cache._enforce_cap(root, added_bytes=1)
        assert sayac['n'] <= 2, (
            'cap altındayken 20 yazımda %d tam tarama yapıldı' % sayac['n'])

    def test_cap_asilinca_supurme_hala_calisir(self, tmp_path, monkeypatch):
        root = str(tmp_path / 'tiles')
        ic = os.path.join(root, 'L', 'd', '3')
        os.makedirs(ic, exist_ok=True)
        for i in range(40):
            with open(os.path.join(ic, '%d.jpg' % i), 'wb') as fh:
                fh.write(b'\xff\xd8\xff\xe0' + b'\x00' * 1000)
        tile_cache._usage_cache.pop(root, None)
        monkeypatch.setattr(tile_cache, 'TILE_CACHE_MAX_BYTES', 8000)
        tile_cache._enforce_cap(root, added_bytes=0)
        kalan, _ = tile_cache._cache_usage(root)
        assert kalan <= 8000, 'cap dayatılmadı: %d bayt kaldı' % kalan

    def test_sayac_gercegi_kacirinca_tam_tarama_yakalar(self, tmp_path,
                                                       monkeypatch):
        """Sayaç yanılsa bile cap DİSKTEN doğrulanır (gevşetme yok)."""
        root = str(tmp_path / 'tiles')
        ic = os.path.join(root, 'L', 'd', '3')
        os.makedirs(ic, exist_ok=True)
        for i in range(30):
            with open(os.path.join(ic, '%d.jpg' % i), 'wb') as fh:
                fh.write(b'\xff\xd8\xff\xe0' + b'\x00' * 1000)
        monkeypatch.setattr(tile_cache, 'TILE_CACHE_MAX_BYTES', 5000)
        tile_cache._usage_cache[root] = 0          # sayaç GERÇEĞİ kaçırdı
        tile_cache._enforce_cap(root, added_bytes=6000)
        kalan, _ = tile_cache._cache_usage(root)
        assert kalan <= 5000, kalan


# =================================================================== OH-D17-17
class TestOHD1717AdliBant:
    """port_diameter_initial kendi adıyla reddedilir.

    ÖLÇÜLDÜ (once.json OH-D17-17): 1,5 m ve 2,0 m için ret
    ``field='port_diameter'``, ``reason='derived_out_of_range'`` idi —
    kullanıcının yazdığı alanın adı yanıtta hiç geçmiyordu.
    """

    @pytest.mark.parametrize('cap', [1.5, 2.0, 50.0])
    def test_bant_disi_cap_adli_reddedilir(self, client, cap):
        r = client.post('/api/regression-analysis', json={'motor_data': {
            'fuel_type': 'htpb', 'burn_time': 10.0, 'mdot_ox': 1.0,
            'port_diameter_initial': cap, 'grain_length': 0.5}})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'invalid_regression_input'
        kayit = [k for k in j['invalid_fields']
                 if k['field'] == 'port_diameter_initial']
        assert kayit, j['invalid_fields']
        assert kayit[0]['reason'] == 'out_of_range'
        # ÖH D27 a2 / OH-D25-23 — ad kanona çevrildi.
        assert kayit[0]['accepted_range'][1] > 0
        assert 'motor_validator.limits' in kayit[0]['basis']

    def test_bant_ici_cap_gecer(self, client):
        r = client.post('/api/regression-analysis', json={'motor_data': {
            'fuel_type': 'htpb', 'burn_time': 10.0, 'mdot_ox': 1.0,
            'port_diameter_initial': 0.03, 'grain_length': 0.5}})
        assert r.status_code == 200

    def test_bant_ikinci_kez_yazilmadi(self):
        """Tek kaynak: bant motor_validator.limits'ten okunur."""
        from hrma import app as app_mod
        for alan, kanonik in app_mod._REGRESSION_LIMIT_ALIASES.items():
            assert kanonik in app_mod.motor_validator.limits, alan


# =================================================================== OH-D17-18
class TestOHD1718OkunmayanYogunluk:
    """'ox' kipinde gönderilen fuel_density okunmadığını söyler.

    ÖLÇÜLDÜ (capa_once.json B3 ⟷ B8): fuel_density=1e9 ile yanıt tabanla
    BİT-AYNI (sha256 dfd1f2f7c27bd003) ve tek bir beyan alanı yoktu.
    """

    def _cagir(self, **ek):
        md = {'fuel_type': 'htpb', 'burn_time': 10.0, 'mdot_ox': 1.0,
              'port_diameter_initial': 0.03, 'grain_length': 0.5}
        md.update(ek)
        return RegressionAnalyzer().analyze_regression_vs_time(md)

    def test_yogunluk_gonderilince_beyan_dusuyor(self):
        d = self._cagir(fuel_density=1e9)
        beyan = d.get('inputs_not_used')
        assert beyan, 'okunmayan fuel_density beyansız geçiyor'
        assert beyan[0]['field'] == 'fuel_density'
        assert beyan[0]['submitted'] == pytest.approx(1e9)
        assert beyan[0]['reason'] == 'not_read_in_this_flux_mode'
        assert 'flux_mode' in beyan[0]['message']

    def test_beyanin_kendisi_olculmus(self):
        """Beyan DOĞRU: yoğunluk gerçekten eğriye girmiyor."""
        a = self._cagir()
        b = self._cagir(fuel_density=1e9)
        assert a['regression_rate'] == b['regression_rate']
        assert a['port_diameter'] == b['port_diameter']
        assert a['total_flux'] == b['total_flux']

    def test_yogunluk_gonderilmezse_govde_bit_ayni(self):
        d = self._cagir()
        assert 'inputs_not_used' not in d


# ================================================================== P14M3-05b
class TestP14M305bPanelinGonderdigiAdlar:
    """safety_panel.js'in GÖNDERDİĞİ alan adları uçta okunuyor mu?

    ÖLÇÜLDÜ (raw/P14/S1-savci.md §1.2 M3 + once.json P14M3-05b): mevcut
    bekçiler yalnız ``defaults_applied`` üstünde geziyordu; ``wall_thickness``
    ZORUNLU olduğu için o listeye hiç girmiyor, dolayısıyla panelin
    gönderdiği adın değişmesi hiçbir teste yakalanmıyordu. Bu sınıf adları
    dosyadan OKUR ve her birini uca karşı sınar.
    """

    PANEL = os.path.join(KOK, 'hrma/static/js/panels/safety_panel.js')
    #: Uçta okunduğu ÖLÇÜLEN adlar (once.json ``ad_degisince_fark``).
    OKUNAN = ('chamber_pressure', 'chamber_temperature', 'thrust',
              'burn_time', 'propellant_mass', 'propellant_type',
              'facility_type', 'chamber_diameter', 'wall_thickness',
              'material')

    @classmethod
    def _panel_alanlari(cls):
        s = open(cls.PANEL, encoding='utf-8').read()
        i = s.find('const FIELDS')
        assert i >= 0, 'safety_panel.js içinde FIELDS listesi bulunamadı'
        j = s.find('\n    ];', i)
        blok = s[i:j if j > 0 else i + 4000]
        return re.findall(r"^\s*\['([a-z_0-9]+)',", blok, re.M)

    def test_panel_okunan_adlarin_tamamini_gonderiyor(self):
        alanlar = set(self._panel_alanlari())
        eksik = [a for a in self.OKUNAN if a not in alanlar]
        assert not eksik, (
            'safety_panel.js artık bu adları göndermiyor (uç onları okuyor, '
            'yeniden adlandırma sessizce 422 üretir): %r' % eksik)

    @pytest.mark.parametrize('alan', OKUNAN)
    def test_gonderilen_ad_ucta_gercekten_okunuyor(self, client, alan):
        """Adın YENİDEN ADLANDIRILMASI yanıtı DEĞİŞTİRMELİ.

        Değiştirmiyorsa panel, ucun okumadığı bir ada yazıyor demektir.
        """
        taban = {'motor_type': 'hybrid', 'chamber_pressure': 40,
                 'chamber_temperature': 3000, 'thrust': 1000,
                 'burn_time': 10, 'propellant_mass': 5,
                 'propellant_type': 'composite',
                 'facility_type': 'test_stand', 'chamber_diameter': 0.1,
                 'wall_thickness': 0.005, 'material': 'steel_4130'}
        r0 = client.post('/analyze_safety', json=dict(taban))
        y = dict(taban)
        y[alan + '__renamed'] = y.pop(alan)
        r1 = client.post('/analyze_safety', json=y)
        farkli = (r0.status_code != r1.status_code
                  or r0.get_data(as_text=True) != r1.get_data(as_text=True))
        assert farkli, (
            "'%s' adı değişince /analyze_safety yanıtı BİT-AYNI kaldı: panel "
            'ucun okumadığı bir ada yazıyor' % alan)


# ============================================================ ÖNCEKİ KAPANIŞLAR
class TestOncekiKapanislar:
    """Ölçümle ÇÜRÜTÜLEN kalemlerin bugünkü kapanışını kilitler."""

    def test_p5b122_kapak_kunyesi_ve_kalinlik_bagi(self):
        """P5B1-22 çürütüldü: künye VAR ve kütle kalınlığı OKUYOR.

        ÖLÇÜLDÜ (once.json P5B1-22): 2 mm kapak 0,2984 kg, 50 mm kapak
        7,4601 kg (25 kat kalınlık -> 25 kat kütle); ``end_caps_weight_basis``
        yayımlanıyor (kapanış: commit f8269a5, ÖH Z5S PK6).
        """
        an = StructuralAnalyzer()
        md = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
              'chamber_length': 0.5, 'throat_diameter': 0.02}
        ince = an.analyze_structure(md, actual_wall_thickness=0.005,
                                    actual_end_cap_thickness=0.002)
        kalin = an.analyze_structure(md, actual_wall_thickness=0.005,
                                     actual_end_cap_thickness=0.050)
        w1 = ince['weight_analysis']
        w2 = kalin['weight_analysis']
        assert w1['end_caps_weight_basis']
        assert 'head_thickness_used_mm' in w1['end_caps_weight_basis']
        assert w2['end_caps_weight'] > w1['end_caps_weight'] * 10, (
            'kapak kütlesi kalınlığı yine yok sayıyor: %r ⟷ %r'
            % (w1['end_caps_weight'], w2['end_caps_weight']))
        assert ince['end_cap_analysis']['head_thickness_used_mm'] == \
            pytest.approx(2.0)
