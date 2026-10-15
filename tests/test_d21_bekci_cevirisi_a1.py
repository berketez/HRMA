# -*- coding: utf-8 -*-
"""ÖH Dalga-21 · bekci-cevirisi · aşama 1 — çevrilen bekçilerin bekçisi.

Bu kulvar ÜRÜN KODUNA DOKUNMAZ: sahası yalnız ``tests/**``. Dolayısıyla
buradaki iddiaların hepsi "bekçi hakkında bekçi"dir — çevrilen/güçlendirilen
iddiaların geri sökülmediğini kilitler. Sayılar
``docs/scofield/raw/OH/D21/bekci-cevirisi/a1/{once_statik,once_dinamik}.json``
koşumundan; ters-mutasyon kanıtı aynı dizindeki ``mutasyon.json``dan gelir.

Kalemler
--------
OH-D17-28  ``test_v252_physics`` hoop bekçisi künye dalında ERKEN dönüyordu;
           ürün künyesi 'thermal' sözcüğünü içerdiği için sayısal dal HİÇ
           koşmuyordu. Ölçüldü: hoop→0 ve hoop→½ mutasyonlarında TABAN
           bekçi 6/6 YEŞİL, onarılmış bekçi 2/6 KIRMIZI.
OH-D17-08  ``test_d16_hibrit_a1`` bekçisi ``sample_nozzle_inner_contour``ı
           0 kez çağırıyordu (docstring çizim yolunu iddia ediyordu).
OH-D17-12  ``test_d16_sivi_a1``: biri anahtar YOLU sayıyordu, öbürü ürünün
           kendi kurduğu özdeşliği sınıyordu (bağıl hata tam 0,0).
OH-D19-25  ``test_d17_termo_ucus_a1:249`` ``... or True`` = boş iddia.
OH-D19-13  P6B4-01 bekçisi ayırt edici değildi (mutasyon 0/6 kırmızı);
           çizilen ≡ istenen olduğu için kilit YAPISAL yapıldı (1/7).
OH-D17-21  ``test_wave3_contract`` iki borç iminin gerekçesi bayattı.
OH-Z5-10   ``test_z5s_ucus_koprusu`` KRİTİK KİLİT olarak işaretlendi.
P13B3-09   ``test_kinetic_efficiency`` başlığı D18/F2 öncesinin sekiz
           sayısını taşıyordu; bir çapa saf totolojiydi.
"""
import ast
import inspect
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D21',
                     'bekci-cevirisi', 'a1')


def _oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as fh:
        return fh.read()


def _fonksiyon(rel, ad):
    """Adı verilen fonksiyon/metodun kaynak metnini döndürür."""
    agac = ast.parse(_oku(rel))
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == ad:
            return ast.unparse(d)
    raise AssertionError(f'{rel} içinde {ad} yok — bekçi silinmiş olabilir')


# ---------------------------------------------------------------------------
# ÖNCE ÖLÇ kuralı: kanıt dosyaları YERİNDE durmalı
# ---------------------------------------------------------------------------
class TestKanitDosyalari:

    @pytest.mark.parametrize('ad', ['once_statik.json', 'once_dinamik.json',
                                    'sonra_statik.json', 'sonra_dinamik.json',
                                    'mutasyon.json', 'olcum_statik.py',
                                    'olcum_dinamik.py', 'mutasyon.py',
                                    'rapor.md'])
    def test_kanit_yerinde(self, ad):
        yol = os.path.join(KANIT, ad)
        assert os.path.exists(kanit_gerekli(yol)), f'kanıt yok: {yol}'
        assert os.path.getsize(kanit_gerekli(yol)) > 0

    def test_mutasyon_kaydi_kirmizi_kanitini_tasiyor(self):
        import json
        with open(kanit_gerekli(os.path.join(KANIT, 'mutasyon.json')), encoding='utf-8') as f:
            m = json.load(f)
        for kimlik in ('OH-D17-28', 'OH-D17-28b', 'OH-D17-08', 'OH-D17-12',
                       'OH-D17-12b', 'OH-D19-25', 'OH-D19-13'):
            assert kimlik in m, f'{kimlik} için mutasyon kaydı yok'
            assert m[kimlik]['kirmizi'] is True, (
                f'{kimlik} mutasyonu bekçiyi kırmızıya döndürmüyor')
            assert m[kimlik]['bayt_geri_yazildi'] is True, (
                f'{kimlik} mutasyonundan sonra ürün baytı geri yazılmamış')


# ---------------------------------------------------------------------------
# OH-D17-28 — hoop künye dalı bir daha erken dönmesin
# ---------------------------------------------------------------------------
class TestOHD1728HoopKunyeDali:

    def test_kunye_dali_hoop_beyanini_ayirt_ediyor(self):
        g = _fonksiyon('tests/test_v252_physics.py',
                       'test_stress_safety_factor_carries_the_hoop_term')
        assert 'hoop_beyani' in g, (
            'künye dalı yine "metinde thermal var mı" ile yetiniyor; '
            'ürün künyesi hoop içerdiğinde sayısal dal atlanır')
        assert 'HOOP_IZLERI' in g
        # Erken 'return' YALNIZ hoop beyanı YOKKEN olabilir.
        assert re.search(r'if kunye and \(?not hoop_beyani\)?:', g), (
            'erken dönüş koşulu hoop beyanına bağlanmamış')
        assert 'pressure_hoop_stress_MPa' in g, (
            'künye hoop diyorsa yayımlanan hoop sayısı sınanmıyor')

    def test_sayisal_dal_hala_iyimserligi_yakaliyor(self):
        g = _fonksiyon('tests/test_v252_physics.py',
                       'test_stress_safety_factor_carries_the_hoop_term')
        assert 'birlesik' in g and 'yield_strength_MPa' in g


# ---------------------------------------------------------------------------
# OH-D17-08 — örnekleyici GERÇEKTEN çağrılıyor
# ---------------------------------------------------------------------------
class TestOHD1708OrnekleyiciCagriliyor:

    def test_bekci_ornekleyiciyi_cagiriyor(self):
        g = _fonksiyon('tests/test_d16_hibrit_a1.py',
                       'test_ornekleyici_ile_performans_ayni_aciyi_goruyor')
        assert len(re.findall(r'sample_nozzle_inner_contour\(', g)) >= 3, (
            'bekçi örnekleyiciyi üç koşumda çağırmıyor — iddia yine '
            'sınanmıyor olabilir')
        assert 'is not None' not in g.split('assert div', 1)[-1][:400] or \
            'exit_angle' in g
        assert 'pop(' in g, 'açı sökülmüş kontur koşumu yok'

    def test_urun_kacis_yolu_hala_8_derece(self):
        """Bekçinin gerekçesi ürüne bağlı: kaçış yolu 8,0° olmalı."""
        kaynak = _oku('hrma/engines/nozzle_design.py')
        assert "_num(div.get('exit_angle'), 8.0)" in kaynak, (
            'örnekleyicinin 8,0° kaçış yolu değişmiş; bekçinin gerekçesi '
            'güncellenmeli (bkz. OH-D17-08)')


# ---------------------------------------------------------------------------
# OH-D17-12 — yol değil DEĞER; totoloji yalnız başına kalmasın
# ---------------------------------------------------------------------------
class TestOHD1712DegerVeKaynak:

    def test_T_recovery_bekcisi_degeri_siniyor(self):
        g = _fonksiyon('tests/test_d16_sivi_a1.py',
                       'test_rejeneratif_kosumda_T_recovery_yayimlanir')
        assert 'isfinite' in g, 'bekçi yine yalnız anahtar yolunu sayıyor'
        assert '> 0.0' in g

    def test_h_g_bekcisi_bagimsiz_caprazi_tasiyor(self):
        g = _fonksiyon(
            'tests/test_d16_sivi_a1.py',
            'test_kamara_h_gas_kaynagi_ve_kunyesi_dallanmayla_uyumlu')
        assert 'cooling_system' in g, (
            'birim/kaynak çaprazı yok — bekçi yine ürünün kendi kurduğu '
            'özdeşlikten ibaret')
        assert 'NOT_PUBLISHED' in g, 'dallanma sözleşmesi kilitlenmemiş'
        assert 'recovered from' in g

    def test_urun_ozdesligi_hala_bolmeyle_kuruyor(self):
        """Totolojinin GEREKÇESİ ürüne bağlı; ürün değişirse bekçi de."""
        kaynak = _oku('hrma/engines/liquid_rocket_engine.py')
        assert 'q_chamber_kw * 1000.0 / delta' in kaynak, (
            'h_g artık bölmeyle kurulmuyor olabilir — özdeşlik iddiası '
            'yeniden değerlendirilmeli (OH-D17-12)')


# ---------------------------------------------------------------------------
# OH-D19-25 — boş iddia geri gelmesin
# ---------------------------------------------------------------------------
class TestOHD1925BosIddiaYok:

    HEDEFLER = ('tests/test_d17_termo_ucus_a1.py',
                'tests/test_d16_hibrit_a1.py',
                'tests/test_d16_sivi_a1.py',
                'tests/test_d17_sivi_a1.py',
                'tests/test_v252_physics.py',
                'tests/test_kinetic_efficiency.py',
                'tests/test_d21_bekci_cevirisi_a1.py')

    @pytest.mark.parametrize('rel', HEDEFLER)
    def test_or_true_yok(self, rel):
        bos = [(i, s.strip()) for i, s in enumerate(_oku(rel).splitlines(), 1)
               if s.strip().startswith('assert ')
               and re.search(r'\bor True\b|\bor 1\b', s)]
        assert not bos, f'{rel}: her zaman doğru iddia(lar): {bos}'

    def test_yorunge_bekcisi_egrinin_integralini_kilitliyor(self):
        g = _fonksiyon('tests/test_d17_termo_ucus_a1.py',
                       'test_yorunge_egriden_entegre_edilir')
        assert 'yamuk' in g, 'bağımsız yamuk integrali çapası sökülmüş'
        assert 'total_impulse_Ns' in g
        assert 'thrust-time curve' in g


# ---------------------------------------------------------------------------
# OH-D19-13 — P6B4-01 yapısal kilidi
# ---------------------------------------------------------------------------
class TestOHD1913YapisalKilit:

    def test_yapisal_bekci_duruyor(self):
        g = _fonksiyon('tests/test_d17_sivi_a1.py',
                       'test_p6b401_chug_cizilen_l_stari_KAYNAKTA_tuketir')
        assert 'l_star_m=l_star_achieved' in g
        assert 'self._l_star()' in g

    def test_urun_cagri_yeri_cizilen_l_stari_geciriyor(self):
        from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
        kaynak = inspect.getsource(LiquidRocketEngine)
        assert 'l_star_m=l_star_achieved' in kaynak


# ---------------------------------------------------------------------------
# OH-D17-21 — borç imi gerekçeleri ÖLÇÜMLE uyumlu kalsın
# ---------------------------------------------------------------------------
class TestOHD1721BorcImiGerekcesi:

    ALANLAR = {
        'protection/heat_sink': ('exceeds_melting', 'material_source',
                                 'model_valid', 'validity_note'),
        'protection/ablative': (
            'flux_basis', 'model_valid', 'thickness_status',
            'recession_regime', 'recession_validity_max_mm_s',
            'surface_source', 'emissivity_source', 'blockage_basis',
            'validity_note'),
    }

    @staticmethod
    def _gerekce(blok_id):
        kaynak = _oku('tests/test_wave3_contract.py')
        i = kaynak.index('TERS_BORCLU_BLOKLAR = {')
        blok = kaynak[i:i + 6000]
        j = blok.index(f"'{blok_id}': (")
        return blok[j:blok.index('),', j)]

    @pytest.mark.parametrize('blok_id', sorted(ALANLAR))
    def test_gerekce_yalniz_HALA_eksik_alanlari_sayiyor(self, blok_id):
        """Gerekçe, panelde ARTIK basılan alanı borç diye sayamaz."""
        panel = _oku('hrma/static/js/panels/protection_panel.js')
        gerekce = self._gerekce(blok_id)
        borc = re.findall(r'`([a-z_]+)`', gerekce.split('KAPANAN pay')[0])
        assert borc, f'{blok_id}: gerekçe hiçbir alan saymıyor'
        for alan in borc:
            assert len(re.findall(re.escape(alan), panel)) == 0, (
                f'{blok_id}: gerekçe `{alan}` alanını borç sayıyor ama '
                f'protection_panel.js onu basıyor — gerekçe yine bayat')

    @pytest.mark.parametrize('blok_id', sorted(ALANLAR))
    def test_im_hala_gerekli(self, blok_id):
        """Borç TAMAMEN kapandıysa im kaldırılmalı (ters-yön uyarısı)."""
        panel = _oku('hrma/static/js/panels/protection_panel.js')
        eksik = [a for a in self.ALANLAR[blok_id]
                 if len(re.findall(re.escape(a), panel)) == 0]
        assert eksik, (
            f'{blok_id}: dokuz/dört alanın hepsi artık panelde — borç imi '
            f'kaldırılmalı ve blok CANLI bekçiye çevrilmeli')


# ---------------------------------------------------------------------------
# OH-Z5-10 — kritik kilit imi
# ---------------------------------------------------------------------------
class TestOHZ510KritikKilit:

    def test_kritik_kilit_imi_var(self):
        kaynak = _oku('tests/test_z5s_ucus_koprusu.py')
        assert 'KRİTİK KİLİT' in kaynak
        assert 'KRITIK_KILIT = {' in kaynak
        assert "'kalem': 'OH-Z5-10'" in kaynak

    @pytest.mark.parametrize('rel,ad', [
        ('tests/test_six_dof_trajectory.py',
         'test_cg_verilmediginde_beyan_edilir'),
        ('tests/test_flight_vehicle.py',
         'test_inert_tank_kutlesini_icerir_ya_da_beyan_eder')])
    def test_kardes_bekciler_hala_yalniz_varlik_soruyor(self, rel, ad):
        """İm bu iki testin ZAYIF olduğu ölçümüne dayanıyor.

        ÖLÇÜLDÜ: ikisinin de KABUL hükmü bir DİSJONKSİYONDUR
        (``uyari_var or alan_var`` / ``icerir or beyan_eder``), yani "iki
        kanaldan biri VAR mı" sorusudur — varlık ayrımı.
        Künyenin İÇERİĞİ (ör. ``x_cg_source == 'assumed_length_fraction'``)
        hiçbirinde sınanmaz; onu tek başına ``test_z5s_ucus_koprusu.py``
        kilitler. Kardeşler günün birinde içeriği de sorarsa bu bekçi
        kırmızıya döner ve OH-Z5-10 gerekçesinin güncellenmesini ister.
        """
        g = _fonksiyon(rel, ad)
        assert re.search(r'assert \w+ or \w+', g), (
            f'{rel}::{ad} artık varlık-disjonksiyonu deseni kullanmıyor — '
            f'OH-Z5-10 kritik kilit gerekçesi güncellenmeli')
        icerik = re.findall(r"==\s*'[a-z_]+'", g)
        assert not icerik, (
            f'{rel}::{ad} artık künye İÇERİĞİNİ sınıyor ({icerik}) — '
            f'OH-Z5-10 kritik kilit gerekçesi güncellenmeli')


# ---------------------------------------------------------------------------
# P13B3-09 — başlık bayat değil, çapa totoloji değil
# ---------------------------------------------------------------------------
class TestP13B309CapaBagimsizligi:

    BAYAT = ('L*=1.0 m', '1.43375e-3', '0.9558333', '0.488708',
             '231.42096', '1.522992')

    def test_baslik_bayat_sayilari_tasimiyor(self):
        docstring = ast.get_docstring(
            ast.parse(_oku('tests/test_kinetic_efficiency.py'))) or ''
        kalan = [s for s in self.BAYAT if s in docstring]
        assert not kalan, (
            f'başlık D18/F2 ÖNCESİNİN sayılarını taşıyor: {kalan}')
        assert '1,7205e-3' in docstring and '231,739637' in docstring

    def test_baslik_TAU_bagimsizligini_beyan_ediyor(self):
        docstring = ast.get_docstring(
            ast.parse(_oku('tests/test_kinetic_efficiency.py'))) or ''
        assert 'TAU_CHEM_REF_S' in docstring
        assert 'BAĞIMSIZ OLMAYAN' in docstring, (
            'çapaların kapsam künyesi yok — kalem P13B3-09 tam da bunu '
            'istiyordu')

    def test_kayip_capasinda_saf_totoloji_yok(self):
        g = _fonksiyon('tests/test_kinetic_efficiency.py',
                       'test_loss_pct_hand_calc')
        assert "(235.0 - res['isp_predicted']) / 235.0" not in g, (
            'beklenen yan yine çıktıdan kuruluyor (saf totoloji)')
        assert '231.739637' in g
