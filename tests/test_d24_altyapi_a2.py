# -*- coding: utf-8 -*-
"""ÖH Dalga-24 · kulvar altyapı · aşama 2/2 — bekçiler.

Kapsanan kalemler
-----------------
``P17B1-15``   Analiz Merkezi kiracı kapsamı: ölçülen READY satır 12,
               turun koşturduğu kiracı 5 → 8. Kapsam beyanı artık TEK
               KAYNAKTAN (``sayfalar.CANLI_READY_SATIRLAR``) türetiliyor.
``OH-D23-02``  Yerel pencere menüsünde 'Settings…' ögesi ve
               ``window.hrmaShowSettings`` köprüsü.
``OH-D23-23``  CI iş bölümü: 66 uçluk canlı 200 kapısı ana koşumdan
               ayrılıp gecelik işe + yayın kapısına alındı; ayrılma ATLAMA
               değil SEÇME ile yapılıyor (atlama bütçesi kapısı bozulmasın).

P14H2-C1 ve P17B4-06 bu aşamada AÇILMADI; gerekçeleri rapor.md'de.

Sözleşme notu: bu dosya TARAYICI AÇMAZ. Canlı ölçümün kendisi
``docs/scofield/raw/OH/D24/altyapi/a2/once_p17b115.json`` dosyasındadır;
buradaki bekçiler o ölçümün ürüne/tanıma DOĞRU yansıdığını sınar.
"""
from __future__ import annotations

import ast
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tools.browser_harness import sayfalar  # noqa: E402

KANIT_DIZINI = os.path.join(ROOT, 'docs', 'scofield', 'raw', 'OH', 'D24',
                            'altyapi', 'a2')


def _oku(*parcalar):
    with open(os.path.join(ROOT, *parcalar), encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------
# P17B1-15 — Analiz Merkezi kiracı kapsamı
# ---------------------------------------------------------------------------
class TestP17B115KiraciKapsami:
    """ÖLÇÜLDÜ (5 Eylül 2026, sistem Chrome 152): üç sayfada 12 READY satır.

    D23 sonunda tur bunların 5'ini koşturuyordu (%41,67) çünkü ``/solid`` ve
    ``/liquid`` hiç canlı ölçülmemişti. Bu aşamada ölçüldü ve ölçülen üç
    satır tanıma eklendi → 8/12 (%66,67).
    """

    def test_olculen_ready_satirlar_uc_sayfa_icin_de_var(self):
        assert set(sayfalar.CANLI_READY_SATIRLAR) == {'hybrid', 'solid',
                                                      'liquid'}
        for ad, satirlar in sayfalar.CANLI_READY_SATIRLAR.items():
            assert len(satirlar) == 4, (ad, satirlar)

    def test_solid_ve_liquid_kararlilik_kiracilarini_kosturuyor(self):
        katı = {k.satir_anahtari
                for k in sayfalar.SAYFALAR['solid'].merkez_kiracilari}
        sıvı = {k.satir_anahtari
                for k in sayfalar.SAYFALAR['liquid'].merkez_kiracilari}
        assert 'chamber_acoustics.acoustic_modes' in katı
        assert 'chamber_acoustics.acoustic_modes' in sıvı
        assert 'chamber_acoustics.combustion_stability' in sıvı

    def test_katida_combustion_stability_EKLENMEDI(self):
        """Ürünün uygulanabilirlik hükmü: katıda enjektör/besleme yok.

        Canlı ölçüm satırı ``blocked`` buldu; tanıma eklenirse tur her
        koşumda 'satır hazır değil' diyip kapıyı gereksiz kapatırdı.
        """
        katı = {k.satir_anahtari
                for k in sayfalar.SAYFALAR['solid'].merkez_kiracilari}
        assert 'chamber_acoustics.combustion_stability' not in katı
        assert ('chamber_acoustics.combustion_stability'
                not in sayfalar.CANLI_READY_SATIRLAR['solid'])

    def test_kapsam_5ten_8e_cikti(self):
        k = sayfalar.merkez_kapsami()
        assert k['ready_satir'] == 12, k
        assert k['kosturulan_kiraci'] == 8, k
        assert k['kapsanmayan'] == 4, k

    def test_her_kiraci_OLCULEN_bir_satira_dayaniyor(self):
        """FAIL-CLOSED: ölçülmemiş satıra kiracı yazılamaz."""
        for ad, sayfa in sayfalar.SAYFALAR.items():
            for kiraci in (sayfa.merkez_kiracilari or ()):
                olculen = sayfalar.CANLI_READY_SATIRLAR.get(ad)
                assert olculen is not None, ad
                assert kiraci.satir_anahtari in olculen, (ad, kiraci.ad)

    def test_kapsanmayan_beyani_TURETILIYOR_elle_tutulmuyor(self):
        """Beyan listesi ikinci bir kaynak değil, ölçümün farkıdır."""
        beklenen = {s for v in sayfalar.kapsanmayan_ready().values()
                    for s in v}
        assert set(sayfalar.OLCULMEMIS_HAZIR_KIRACILAR) == beklenen
        kaynak = _oku('tools', 'browser_harness', 'sayfalar.py')
        agac = ast.parse(kaynak)
        for dugum in agac.body:
            if (isinstance(dugum, (ast.Assign, ast.AnnAssign))
                    and 'OLCULMEMIS_HAZIR_KIRACILAR' in ast.dump(dugum)):
                deger = dugum.value
                assert not isinstance(deger, (ast.Tuple, ast.List)), (
                    'beyan listesi yeniden ELLE yazılmış; ölçümden '
                    'türetilmiyor')
                break
        else:
            pytest.fail('OLCULMEMIS_HAZIR_KIRACILAR tanımı bulunamadı')

    def test_kapsanmayanlar_hala_tanima_girmemis(self):
        anahtarlar = {k.satir_anahtari
                      for s in sayfalar.SAYFALAR.values()
                      for k in s.merkez_kiracilari}
        for eksik in sayfalar.OLCULMEMIS_HAZIR_KIRACILAR:
            assert eksik not in anahtarlar, eksik

    def test_canli_olcum_kaniti_depoda(self):
        """Sayılar kaynakta değil, ölçüm dosyasında doğrulanır."""
        import json
        yol = os.path.join(KANIT_DIZINI, 'once_p17b115.json')
        assert os.path.exists(kanit_gerekli(yol)), yol
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            olcum = json.load(f)
        for ad, kayit in olcum['sayfalar'].items():
            assert kayit['asama'] == 'tamam', (ad, kayit.get('asama'))
            assert (tuple(sorted(kayit['ready_satirlar']))
                    == tuple(sorted(sayfalar.CANLI_READY_SATIRLAR[ad]))), ad
        assert olcum['ozet']['toplam_ready_satir'] == 12


# ---------------------------------------------------------------------------
# OH-D23-02 — yerel menüde 'Settings…'
# ---------------------------------------------------------------------------
def _menu_ogeleri(fonksiyon: str):
    kaynak = _oku('packaging', 'launcher.py')
    agac = ast.parse(kaynak)
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == fonksiyon:
            break
    else:
        raise AssertionError('%s bulunamadı' % fonksiyon)
    ogeler = []
    for dugum in ast.walk(d):
        if (isinstance(dugum, ast.Call)
                and isinstance(dugum.func, ast.Attribute)
                and dugum.func.attr == 'MenuAction'
                and dugum.args
                and isinstance(dugum.args[0], ast.Constant)):
            hedef = dugum.args[1] if len(dugum.args) > 1 else None
            ogeler.append((dugum.args[0].value,
                           hedef.id if isinstance(hedef, ast.Name) else None))
    return ogeler


class TestOHD2302AyarlarMenusu:
    """ÖLÇÜLDÜ: ürünün yayımladığı ``hrma*`` köprüleri arasında menüden
    çağrılmayan TEK köprü ``hrmaShowSettings`` idi (once_ohd2302.json)."""

    @pytest.mark.parametrize('fonksiyon', ['_macos_menu', '_windows_menu'])
    def test_ayarlar_ogesi_var(self, fonksiyon):
        etiketler = [e for e, _ in _menu_ogeleri(fonksiyon)]
        assert any(re.search(r'settings', e or '', re.I) for e in etiketler), \
            etiketler

    @pytest.mark.parametrize('fonksiyon', ['_macos_menu', '_windows_menu'])
    def test_ayarlar_ogesi_menu_eylemine_bagli(self, fonksiyon):
        for etiket, hedef in _menu_ogeleri(fonksiyon):
            if re.search(r'settings', etiket or '', re.I):
                assert hedef == '_menu_settings', (etiket, hedef)
                return
        pytest.fail('ayarlar ögesi yok')

    def test_menu_eylemi_urunun_koprusunu_cagiriyor(self):
        kaynak = _oku('packaging', 'launcher.py')
        agac = ast.parse(kaynak)
        for d in ast.walk(agac):
            if isinstance(d, ast.FunctionDef) and d.name == '_menu_settings':
                govde = ast.get_source_segment(kaynak, d) or ''
                break
        else:
            pytest.fail('_menu_settings yok')
        assert 'window.hrmaShowSettings' in govde
        # Kardeş ögelerle AYNI korumalı desen: köprü yoksa istisna atılmaz.
        assert '&&' in govde

    def test_urun_koprusu_gercekten_yayimlaniyor(self):
        js = _oku('hrma', 'static', 'js', 'settings_panel.js')
        assert re.search(r'window\.hrmaShowSettings\s*=', js)

    def test_menuden_cagrilmayan_urun_koprusu_KALMADI(self):
        """Ürün bir ``hrma*`` köprüsü yayımlıyorsa menü ya onu çağırır ya
        da kalem açılır — sessiz yetim köprü bırakılmaz."""
        launcher = _oku('packaging', 'launcher.py')
        cagrilan = set(re.findall(r'window\.(hrma[A-Za-z0-9_]+)', launcher))
        js_dizin = os.path.join(ROOT, 'hrma', 'static', 'js')
        yayimlanan = set()
        for dosya in os.listdir(js_dizin):
            if dosya.endswith('.js'):
                with open(os.path.join(js_dizin, dosya), encoding='utf-8',
                          errors='replace') as f:
                    yayimlanan |= set(
                        re.findall(r'window\.(hrma[A-Za-z0-9_]+)\s*=',
                                   f.read()))
        assert yayimlanan - cagrilan == set(), sorted(yayimlanan - cagrilan)


# ---------------------------------------------------------------------------
# OH-D23-23 — CI iş bölümü (ağır canlı uç kapısı)
# ---------------------------------------------------------------------------
class TestOHD2323CiIsBolumu:
    """Kapı KALDIRILMADI, TAŞINDI.

    Bu bekçilerin işi, taşımanın üç ayağının da yerinde durduğunu şart
    koşmaktır: (1) işaret tanımlı, (2) ağır test işaretli, (3) push/PR
    onu seçmiyor ama gecelik iş ve yayın kapısı koşuyor. Ayaklardan biri
    sessizce düşerse kapı ya hiç koşmaz (katalog bayatlar) ya da yine her
    push'a yapışır.
    """

    def test_isaret_pytest_ini_de_TANIMLI(self):
        """Tanımsız işaret ``--strict-markers`` altında koşumu patlatır."""
        ini = _oku('pytest.ini')
        assert 'agir_canli_uc:' in ini, ini

    def test_agir_test_isaretli(self):
        kaynak = _oku('tests', 'test_d23_altyapi_a1.py')
        agac = ast.parse(kaynak)
        bulundu = False
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.FunctionDef)
                    and dugum.name == 'test_taban_yuk_200_veriyor'):
                imler = {ast.unparse(d) for d in dugum.decorator_list}
                assert any('agir_canli_uc' in i for i in imler), imler
                bulundu = True
        assert bulundu, 'ağır test bulunamadı'

    def test_UCUZ_kardes_isaretlenmemis(self):
        """Tek-kaynak sözleşmesi her koşumda sınanmaya devam etmeli."""
        kaynak = _oku('tests', 'test_d23_altyapi_a1.py')
        agac = ast.parse(kaynak)
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.FunctionDef)
                    and dugum.name
                    == 'test_uc_motor_sayfasinin_yuku_tek_kaynaktan_gelir'):
                imler = {ast.unparse(d) for d in dugum.decorator_list}
                assert not any('agir_canli_uc' in i for i in imler), imler
                return
        pytest.fail('ucuz kardeş test bulunamadı')

    def test_push_ve_pr_kapiyi_SECMIYOR(self):
        akis = _oku('.github', 'workflows', 'tests.yml')
        assert "not agir_canli_uc" in akis, 'süzgeç yok'
        assert "github.event_name == 'push'" in akis
        assert "github.event_name == 'pull_request'" in akis

    def test_gecelik_kosum_TANIMLI(self):
        """Kapı bayatlamasın diye ayrı bir koşum ŞART."""
        import yaml
        with open(os.path.join(ROOT, '.github', 'workflows',
                               'tests.yml'), encoding='utf-8') as f:
            akis = yaml.safe_load(f)
        tetik = akis.get('on') or akis.get(True)
        assert 'schedule' in tetik, sorted(tetik)
        assert tetik['schedule'], 'schedule boş'
        cron = tetik['schedule'][0]['cron']
        # Saat başı GitHub kuyruğunun en kalabalık anıdır; kasten kaydırıldı.
        assert cron.split()[0] not in ('0', '30'), cron

    def test_yayin_kapisi_TAM_suiti_kosuyor(self):
        """release.yml'de işaret süzgeci OLMAMALI — yayın hiç uç kaçırmaz."""
        yayin = _oku('.github', 'workflows', 'release.yml')
        assert 'agir_canli_uc' not in yayin, (
            'yayın kapısı ağır ucu dışarıda bırakıyor')
        assert 'pytest tests/ -q -rs --junitxml=pytest-report.xml' in yayin

    def test_SECME_kullanildi_ATLAMA_degil(self):
        """``skip`` atlama bütçesi kapısını bozardı; ``-m`` bozmaz."""
        kaynak = _oku('tests', 'test_d23_altyapi_a1.py')
        agac = ast.parse(kaynak)
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.FunctionDef)
                    and dugum.name == 'test_taban_yuk_200_veriyor'):
                imler = {ast.unparse(d) for d in dugum.decorator_list}
                assert not any('skip' in i for i in imler), imler
                return
        pytest.fail('ağır test bulunamadı')

    def test_sure_olcumu_depoda(self):
        """Karar ölçüme dayanır: süre kanıtı dosyada durur."""
        import json
        yol = os.path.join(KANIT_DIZINI, 'once_ohd2323.json')
        assert os.path.exists(kanit_gerekli(yol)), yol
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            olcum = json.load(f)
        assert olcum['kapinin_maliyeti_s'] > 0, olcum
        assert olcum['tam']['cikis_kodu'] == 0, olcum['tam']
        assert olcum['suzgecli']['cikis_kodu'] == 0, olcum['suzgecli']
