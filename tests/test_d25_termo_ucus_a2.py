# -*- coding: utf-8 -*-
"""ÖH Dalga-25 · termo-ucus · aşama 2/2 — bekçi.

İki kalem:

* **P15B4-09** (Fable-D19 ŞART) — cidar-integrali çapraz doğrulamasının
  ÖNCE/SONRA kalıntı eşlemesi künye metinlerinde BİR SATIR KAYMIŞTI ve
  gamma = 1,4 çapalarındaki ``P2/P1`` sayıları ölçütün kıyasladığı
  büyüklük değildi. Ürün mantığına dokunulmadı; bu bekçi metnin ÖLÇÜLEN
  sayıyla aynı kalmasını kilitler (künye çürümesine karşı).
* **OH-D24-16** — ``/api/six-dof-analysis`` yanıtının ``series`` bloğu
  irtifa dizisinin datumunu yayımlamıyordu; tüketici datumu VARSAYIYORDU.

Ölçüm: ``docs/scofield/raw/OH/D25/termo-ucus/a2/{once,sonra}.json``
Ters-mutasyon: ``.../a2/mutasyon.json``

Koşum:
    MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest \
        tests/test_d25_termo_ucus_a2.py -v
"""
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NOZZLE_PY = os.path.join(KOK, 'hrma', 'analysis', 'nozzle_flow_1d.py')
APP_PY = os.path.join(KOK, 'hrma', 'app.py')
TEST_D15 = os.path.join(KOK, 'tests', 'test_d15_termo_ucus_a3.py')
TEST_NOZZLE = os.path.join(KOK, 'tests', 'test_nozzle_flow_1d.py')
D19_RAPOR = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D19',
                         'fizik', 'a1', 'rapor.md')
D19_JSON = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D19',
                        'oturum-devri', 'd19_raporlar', 'fizik_a1.json')

#: ÖLÇÜLEN cidar-integrali kalıntıları (LULE: P_c = 70 bar, eps = 25,
#: D_t = 100 mm, gamma = 1,2, MW = 22, T_c = 3500 K). ÖNCE = D19 öncesi
#: merdiven (Summerfield ölçütü şok dalının ARDINDA), SONRA = bugünkü.
#: Kaynak: docs/scofield/raw/OH/D25/termo-ucus/a2/once.json K2 ve K1.
KALINTI_ONCE_YUZDE = {'10 bar': 8.751, '30 bar': 129.4745, '60 bar': 231.0465}
KALINTI_SONRA_YUZDE = {'10 bar': 1.9668, '30 bar': 2.7437, '60 bar': 10.2385}

#: gamma = 1,4 çapalarının ÇIKIŞ DÜZLEMİ basınç oranları (ölçüt bunları
#: 1/k = 2,50 ile kıyaslar) ve eps = 1,10 vakasının ŞOK İSTASYONU
#: sıçraması. Kaynak: a2/once.json K3.
CIKIS_P2P1 = {'eps=4.0': 9.9188, 'eps=1.1': 2.0292}
SOK_ISTASYONU_P2P1 = 1.8105
AYRILMA_ESIGI = 2.5

ALT_DATUM = 'above_launch_site'


def _oku(yol):
    with open(yol, encoding='utf-8') as f:
        return f.read()


def _sayi(metin):
    """'%129,47' / '129,4745' gibi Türkçe ondalıklı sayıyı float'a çevirir."""
    return float(metin.replace('%', '').replace('.', '').replace(',', '.'))


# ======================================================================
# 1) P15B4-09 — KALINTI EŞLEMESİ KAYMAZ
# ======================================================================
class TestP15B409KalintiEslemesi:
    """Künye metinleri ÖLÇÜLEN eşlemeyi taşır; kaymış eşleme geri gelemez."""

    KAYMIS = (
        # (dosya, kaymış desen) — hiçbiri bulunmamalı
        (NOZZLE_PY, r'kalıntı\s*%129,47\s*/\s*%231,05\s*->\s*%1,9668'),
        (TEST_D15, r'kalıntısı\s*%129,47\s*/\s*%231,05'),
        (D19_RAPOR, r'\|\s*10 bar\s*\|\s*normal_shock\s*/\s*\*\*%129,47'),
        (D19_RAPOR, r'\|\s*30 bar\s*\|\s*normal_shock\s*/\s*\*\*%231,05'),
        (D19_JSON, r'P_a=10 bar kalıntı %129,47'),
        (D19_JSON, r'kalıntı\s*—\s*%129,47/%231,05'),
    )

    @pytest.mark.parametrize('yol,desen', KAYMIS)
    def test_kaymis_esleme_hicbir_kunyede_yok(self, yol, desen):
        assert re.search(desen, _oku(kanit_gerekli(yol))) is None, (
            f'{os.path.relpath(yol, KOK)}: cidar-integrali kalıntılarının '
            'ÖNCE eşlemesi yine bir satır kaymış. Ölçülen doğru eşleme '
            '10 bar %8,751 / 30 bar %129,47 / 60 bar %231,05 '
            '(a2/once.json K2).')

    def test_modul_kunyesi_uc_basamagi_da_adiyla_tasir(self):
        s = _oku(NOZZLE_PY)
        blok = re.search(
            r'kalıntı 10 bar (%[\d,]+) / 30 bar (%[\d,]+) / 60 bar (%[\d,]+)',
            s)
        assert blok is not None, (
            'nozzle_flow_1d.py künyesi üç geri basıncı ADIYLA eşleyen '
            'satırı kaybetmiş (P15B4-09 ŞART).')
        for bulunan, ad in zip(blok.groups(), ('10 bar', '30 bar', '60 bar')):
            assert _sayi(bulunan) == pytest.approx(
                KALINTI_ONCE_YUZDE[ad], abs=0.02), (
                f'{ad}: künyedeki ÖNCE kalıntısı {bulunan} ölçülenle '
                f'({KALINTI_ONCE_YUZDE[ad]}) uyuşmuyor.')

    def test_60_barin_hala_uyusmadigi_ilan_ediliyor(self):
        """Fail-closed: düzelmeyen vaka SUSTURULMAZ, adıyla yazılır."""
        for yol in (NOZZLE_PY, TEST_D15):
            s = _oku(yol)
            assert '%10,2385' in s, (
                f'{os.path.relpath(yol, KOK)}: 60 barın SONRA kalıntısı '
                'künyeden düşmüş.')
            assert re.search(r'60 bar\s+(HÂLÂ|hâlâ)\s+uyuşmuyor', s), (
                f'{os.path.relpath(yol, KOK)}: 60 barın hâlâ uyuşmadığı '
                'ilanı künyeden düşmüş — beyan susturulamaz.')

    def test_d19_rapor_tablosu_olculen_eslemede(self):
        s = _oku(kanit_gerekli(D19_RAPOR))
        for ad, beklenen in KALINTI_ONCE_YUZDE.items():
            satir = re.search(
                r'\|\s*' + ad + r'\s*\|\s*normal_shock\s*/\s*\*\*(%[\d,]+)\*\*',
                s)
            assert satir is not None, f'D19 rapor.md: {ad} satırı bozuk.'
            assert _sayi(satir.group(1)) == pytest.approx(beklenen, abs=0.02)


# ======================================================================
# 2) P15B4-09 — P2/P1 KÜNYELERİ ÖLÇÜTÜN BÜYÜKLÜĞÜNÜ ADLANDIRIR
# ======================================================================
class TestP15B409P2P1Kunyeleri:

    def test_eski_yanlis_sayilar_kunyelerde_yok(self):
        s = _oku(TEST_NOZZLE)
        # Şok bandı tartışmasında (yorumlarda) artık geçmiyor.
        yorumlar = '\n'.join(l for l in s.splitlines()
                             if l.lstrip().startswith('#'))
        assert 'P2/P1 = 4,50' not in yorumlar, (
            'test_nozzle_flow_1d yorumlarında "P2/P1 = 4,50" geri gelmiş: '
            'o Anderson App. B M1 = 2,0 TABLO değeridir, ayrılma ölçütünün '
            'kıyasladığı çıkış düzlemi oranı (9,92) değil.')
        assert not re.search(r'P2/P1 = 1,81 <', yorumlar), (
            '"P2/P1 = 1,81 < 2,50" geri gelmiş: 1,81 şok İSTASYONU '
            'sıçramasıdır, çıkış düzlemi oranı 2,03tür.')

    def test_iki_bandin_cikis_orani_adiyla_yazili(self):
        s = _oku(TEST_NOZZLE)
        assert '9,92' in s or '9,9188' in s, (
            'eps = 4,0 bandının çıkış düzlemi oranı (9,92) künyede yok.')
        assert '2,03' in s or '2,0292' in s, (
            'eps = 1,10 bandının çıkış düzlemi oranı (2,03) künyede yok.')
        assert '1,81' in s, (
            'şok istasyonu sıçraması (1,81) AYRI büyüklük olarak künyede '
            'kalmalı — silinmesi değil, adlandırılması istendi.')

    def test_esitsizlik_hukmu_olculen_sayilarla_da_ayni(self):
        """Künye düzeltmesi HÜKMÜ değiştirmemeli."""
        assert CIKIS_P2P1['eps=4.0'] > AYRILMA_ESIGI
        assert CIKIS_P2P1['eps=1.1'] < AYRILMA_ESIGI
        # Eski (yanlış) sayılarla da aynı yöndeydi — bu yüzden hüküm
        # dokunulmadan yalnız künye düzeltildi.
        assert 4.50 > AYRILMA_ESIGI and SOK_ISTASYONU_P2P1 < AYRILMA_ESIGI

    def test_olculen_cikis_orani_urunle_dogrulanir(self):
        """Künyedeki sayı ÜRÜNÜN kendi eşiklerinden geri okunur."""
        from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
        SEA = 101325.0
        ortak = dict(chamber_pressure=1.45 * SEA, chamber_temperature=2000.0,
                     gamma=1.4, molecular_weight=28.0, throat_diameter=0.05,
                     ambient_pressure=SEA)
        for eps, beklenen in ((1.10, CIKIS_P2P1['eps=1.1']),
                              (4.0, CIKIS_P2P1['eps=4.0'])):
            r = NozzleFlow1D(expansion_ratio=eps,
                             **ortak).solve(include_bartz=False)
            esik = r['regime']['thresholds_Pa']
            # separation_onset = p_exit_isentropic / k  (tek kaynak)
            pe_isen = esik['separation_onset_Pa'] * 0.40
            assert esik['shock_at_exit_Pa'] / pe_isen == pytest.approx(
                beklenen, rel=1e-3)

    def test_sok_istasyonu_sicramasi_urunle_dogrulanir(self):
        from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
        SEA = 101325.0
        r = NozzleFlow1D(chamber_pressure=1.45 * SEA,
                         chamber_temperature=2000.0, gamma=1.4,
                         molecular_weight=28.0, throat_diameter=0.05,
                         expansion_ratio=1.10,
                         ambient_pressure=SEA).solve(include_bartz=False)
        sh = r['regime']['normal_shock']
        assert sh is not None
        assert sh['static_pressure_jump_ratio'] == pytest.approx(
            SOK_ISTASYONU_P2P1, rel=1e-3)


# ======================================================================
# 3) P15B4-09 — ÜRÜN MANTIĞI DEĞİŞMEDİ (ŞART'ın kendi koşulu)
# ======================================================================
class TestP15B409UrunMantigiDokunulmadi:

    @pytest.mark.parametrize('ad,pa,beklenen,agrees', [
        ('10 bar', 10e5, KALINTI_SONRA_YUZDE['10 bar'], True),
        ('30 bar', 30e5, KALINTI_SONRA_YUZDE['30 bar'], True),
        ('60 bar', 60e5, KALINTI_SONRA_YUZDE['60 bar'], False),
    ])
    def test_bugunku_kalinti_kunyedeki_sayidir(self, ad, pa, beklenen,
                                               agrees):
        from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
        r = NozzleFlow1D(chamber_pressure=70e5, chamber_temperature=3500.0,
                         throat_diameter=0.10, expansion_ratio=25.0,
                         gamma=1.2, molecular_weight=22.0,
                         ambient_pressure=pa).solve()
        cc = r['performance']['wall_integral_cross_check']
        assert 100.0 * cc['residual_rel'] == pytest.approx(beklenen, abs=0.01)
        assert cc['agrees'] is agrees
        assert r['regime']['type'] == 'separated'


# ======================================================================
# 4) OH-D24-16 — SERİNİN DATUMU SÖZLEŞMEDİR
# ======================================================================
def _six_dof_yuk():
    return {
        'body_diameter': 0.10, 'body_length': 2.0, 'nose_length': 0.30,
        'nose_type': 'ogive', 'dry_mass': 20.0, 'propellant_mass': 10.0,
        'cd0': 0.5, 'fin_count': 4, 'fin_root_chord': 0.15,
        'fin_tip_chord': 0.075, 'fin_span': 0.10, 'fin_sweep': 0.05,
        'thrust': 3000.0, 'burn_time': 6.0,
        'launch_elevation_deg': 88.0, 'launch_azimuth_deg': 0.0,
        'rail_length': 5.0,
    }


class TestOHD2416SeriDatumu:

    @pytest.fixture(scope='class')
    def govde(self):
        from hrma.app import app
        with app.test_client() as c:
            r = c.post('/api/six-dof-analysis', json=_six_dof_yuk())
            assert r.status_code == 200, r.get_data(as_text=True)[:400]
            return r.get_json()

    def test_series_datumu_yayimlaniyor(self, govde):
        seri = govde['series']
        assert 'altitude_datum' in seri, (
            "/api/six-dof-analysis 'series' bloğu irtifa dizisinin datumunu "
            'yayımlamıyor; tüketici datumu VARSAYMAK zorunda kalır '
            '(OH-D24-16 / OH-D18-10).')
        assert seri['altitude_datum'] == ALT_DATUM

    def test_seri_datumu_apoje_datumuyla_ayni_sozcuk(self, govde):
        """İki datum aynı diziden gelir; ayrı sözcük = sessiz kayma."""
        assert govde['series']['altitude_datum'] == \
            govde['summary']['apogee_datum']

    def test_datum_cozucuden_okunur_uc_kendisi_YAZMAZ(self):
        """Tek kaynak: uç gövdesinde datum LİTERALİ olmamalı."""
        satirlar = _oku(APP_PY).splitlines()
        bas = next(i for i, s in enumerate(satirlar)
                   if 'def six_dof_analysis(' in s)
        son = next(i for i in range(bas + 1, len(satirlar))
                   if satirlar[i].startswith('@app.route'))
        kod = [s for s in satirlar[bas:son]
               if not s.lstrip().startswith('#')]
        for datum in (ALT_DATUM, 'mean_sea_level'):
            kacaklar = [s.strip() for s in kod if f"'{datum}'" in s
                        or f'"{datum}"' in s]
            assert not kacaklar, (
                f'/api/six-dof-analysis gövdesinde {datum!r} literali var: '
                f'{kacaklar}. Datum ÇÖZÜCÜNÜN sözleşmesidir, uçta ikinci '
                'kez yazılamaz (tek kaynak).')

    def test_datumsuz_seri_FAIL_CLOSED_reddedilir(self, monkeypatch):
        """Çözücü datumu adlandırmazsa seri YAYIMLANMAZ."""
        import hrma.app as app_mod
        from hrma.analysis import six_dof_trajectory as sdt
        gercek = sdt.SixDOFTrajectory.solve

        def datumsuz(self, *a, **kw):
            res = gercek(self, *a, **kw)
            res.pop('altitude_datum', None)
            return res

        # Uç ``SixDOFTrajectory``yi gövde içinde import ediyor, bu yüzden
        # yama KAYNAK modüle uygulanır.
        monkeypatch.setattr(sdt.SixDOFTrajectory, 'solve', datumsuz)
        with app_mod.app.test_client() as c:
            r = c.post('/api/six-dof-analysis', json=_six_dof_yuk())
        assert r.status_code == 500, (
            'Datumsuz irtifa dizisi HTTP 200 ile yayımlandı — sessiz '
            'varsayıma düşüldü (fail-closed ihlali).')
        gov = r.get_json()
        assert gov['error'] == 'six_dof_altitude_datum_missing'
        assert gov['field'] == 'series.altitude_datum'
        assert 'series' not in gov

    def test_tuketici_alani_gercekten_okuyor(self):
        """Yayımlanan alanın bir tüketicisi var (ölü alan değil)."""
        js = _oku(os.path.join(KOK, 'hrma', 'static', 'js',
                               'launch_site_globe.js'))
        assert 'series.altitude_datum' in js
        assert "_onError('flight_altitude_datum_unknown')" in js

    def test_borc_envanteri_muafiyeti_TUKETICIYI_ADIYLA_YAZIYOR(self):
        """ÖK-22: envanter gevşetilmedi, alan SINIFLANDIRILDI.

        ``test_wave4b_contract.py`` ters-yön borç envanteri yeni alanı
        gördü. Muafiyet satırı boş bir "kozmetik" etiketi DEĞİL, gerçek
        tüketiciyi adıyla göstermek zorundadır; yoksa muafiyet zamanla
        genel bir susturucuya dönüşür.
        """
        from tests.test_wave4b_contract import TERS_MUAFIYET
        _js, muafiyet = TERS_MUAFIYET['sixdof/series']
        gerekce = muafiyet.get('altitude_datum')
        assert gerekce, (
            'sixdof/series muafiyetinde altitude_datum gerekçesi yok.')
        assert 'launch_site_globe.js' in gerekce, (
            'Muafiyet gerekçesi alanı GERÇEKTEN okuyan dosyayı adıyla '
            'göstermeli (launch_site_globe.js).')
        assert 'flight_altitude_datum_unknown' in gerekce, (
            'Muafiyet gerekçesi tüketicinin FAIL-CLOSED davranışını '
            'adlandırmalı.')


# ======================================================================
# 5) KANIT ZİNCİRİ
# ======================================================================
class TestKanitZinciri:

    KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D25',
                         'termo-ucus', 'a2')

    def test_once_sonra_olcumleri_duruyor(self):
        for ad in ('once.json', 'sonra.json'):
            yol = os.path.join(self.KANIT, ad)
            assert os.path.exists(kanit_gerekli(yol)), f'{ad} yok'
            d = json.load(open(kanit_gerekli(yol), encoding='utf-8'))
            assert set(d) >= {'K1_capraz_bugun', 'K2_capraz_D19_oncesi',
                              'K3_p2p1', 'K4_kunye_envanteri',
                              'K5_six_dof_uc'}

    def test_olcum_bayt_geri_yazimini_dogruluyor(self):
        """K2 ürün dosyasını GEÇİCİ bozuyor; md5 eşitliği kanıtlanmalı."""
        for ad in ('once.json', 'sonra.json'):
            d = json.load(open(kanit_gerekli(os.path.join(self.KANIT, ad)),
                               encoding='utf-8'))
            k2 = d['K2_capraz_D19_oncesi']
            assert k2['_bayt_geri_yazildi'] is True
            assert k2['_md5_baslangic'] == k2['_md5_bitis']

    def test_once_kusuru_sonra_onarimi_gosteriyor(self):
        once = json.load(open(kanit_gerekli(os.path.join(self.KANIT, 'once.json')),
                              encoding='utf-8'))
        sonra = json.load(open(kanit_gerekli(os.path.join(self.KANIT, 'sonra.json')),
                               encoding='utf-8'))
        assert once['K5_six_dof_uc']['series_altitude_datum_VAR_MI'] is False
        assert sonra['K5_six_dof_uc']['series_altitude_datum_VAR_MI'] is True
        # Künye envanteri: ÖNCE en az dört yanlış sayı, SONRA hiç.
        assert sum(k['adet'] for k in once['K4_kunye_envanteri']) >= 4
        assert sum(k['adet'] for k in sonra['K4_kunye_envanteri']) == 0
