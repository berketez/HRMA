# -*- coding: utf-8 -*-
"""ÖH D19 · kulvar ARAYUZ · aşama 1 — onarım bekçileri.

Kapsanan defter kalemleri:

* **P12bB1-05** (Fable-D17 ŞARTI, kanıt hijyeni) — D17 raporunun
  "üç metin de yüzde semantiği taşıyordu" cümlesi bir ÖLÇÜM ARTEFAKTINA
  dayanıyordu: `once.json` M5 metriği metnin ham içeriğine bakıyor ve
  "in BAR — **not a percentage**" cümlesindeki `percentage` alt dizesini
  "yüzde öğretiyor" diye sayıyordu. Rapor düzeltildi, metrik olumsuzlama
  istisnasıyla yeniden tanımlandı; ürün koduna dokunulmadı.
* **P12bB1-07** (Fable-D17 ŞARTI, bekçi körlüğü) — D15 bekçisindeki iki
  iddia gevşetilmişti (`… in g or 'burn_time: tYanma' in g` ve dosya
  genelinde `'mItici / trMdot' in liquid_src`); ikincisi şablonun HTML
  yorumuyla sağlandığı için türetimi sabite çeviren mutasyon bekçiyi
  KIRMIYORDU. Daraltıldı; bu dosya daraltmanın geri alınmadığını sınar.
* **P11B3-01** — yapısal FEA rozeti motorun KENDİ hükmünü hiç okumuyordu.
  ÖLÇÜLDÜ (`docs/scofield/raw/OH/D19/arayuz/a1/once_ekran.json`, taban
  `60cd341`): tek hibrit koşumda köprü 34,28 (rozet YEŞİL/`ok`), motorun
  kendi katsayısı 0,9653 — 35,5 kat; ekranda motorun sayısı YOK.
* **P11B3-06** — aynı panel `material_key` / `yield_mpa` /
  `wall_thickness_m` / `inner_pressure_pa` skalerlerini görünüm modelinde
  kuruyor ama HİÇBİR kaba basmıyordu; üstelik ekrandaki `not_modelled`
  maddesi kullanıcıyı panelin hiç basmadığı `girdiler.yuk` bloğuna
  yolluyordu.

Yöntem: beklenen sayılar ELLE YAZILMAZ — ucun O KOŞUMDAKİ yanıtından
okunur. Panel gerçek dosyasıyla, sahte DOM içinde, node ile koşturulur.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = KOK / 'hrma' / 'static' / 'js'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D19' / 'arayuz' / 'a1'
D17KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D17' / 'arayuz' / 'a1'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Uygulama yalnız geri döngü Host başlığına yanıt verir.
HEADERS = {'Host': '127.0.0.1:8080'}

#: Kalemin ölçüldüğü hibrit koşum (P11 B3-repro-01 ile aynı gövde).
MOTOR_GOVDESI = {
    'motor_name': 'd19', 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'thrust': 2000, 'burn_time': 10, 'chamber_pressure': 30,
    'of_ratio': 6.0,
}
FEA_GOVDESI = {'n_axial0': 12, 'n_radial0': 4, 'max_rounds': 2}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def fea_yaniti(client):
    # T-ÇAPA-C2 (27 Eki): kalemin senaryosu (motorun KENDİ katsayısı akmanın
    # altında, köprü onun 35 katını yeşil basıyor) V301/H-termal (065b391dc)
    # sonrası hibritin YALNIZ fail-closed termal yolunda görülür — korunan
    # yolda kasa ortam sıcaklığında ve motor SF 4,80 (≥ 1,5, yeşil hak
    # edilmiş). Ölçüldü (27 Eki): korunan yol motor 4,80 / köprü 5,49;
    # astar boyutlandırması koşmazken motor 0,382 / köprü 19,40. Senaryo
    # adıyla kurulur (``tests.support.hibrit_termal``; gerisi ürün kodu).
    from tests.support.hibrit_termal import astar_boyutlandirmasi_kosmaz
    with astar_boyutlandirmasi_kosmaz():
        r = client.post('/calculate', json=MOTOR_GOVDESI, headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    motor = (r.get_json() or {}).get('motor')
    assert isinstance(motor, dict) and motor, 'motor sözlüğü boş'
    yuk = dict(FEA_GOVDESI, motor_results=motor)
    r2 = client.post('/api/fea/structural', json=yuk, headers=HEADERS)
    assert r2.status_code == 200, r2.get_data(as_text=True)[:400]
    j = r2.get_json()
    assert (j or {}).get('fea', {}).get('status') == 'ok', (
        'ölçüm tabanı çürüdü: yapısal koşum ok dönmüyor')
    return j


def _ekran(tmp_path, yanit, static_dir=None):
    """Paneli sahte DOM içinde koşturur; kapların METNİNİ döndürür."""
    y = tmp_path / 'yuk.json'
    y.write_text(json.dumps(yanit), encoding='utf-8')
    p = subprocess.run(
        [NODE, kanit_gerekli(str(KANIT / 'ekran_harness.js')),
         str(static_dir or STATIC_JS), str(y)],
        capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, 'node altında çöktü:\n' + p.stderr[-3000:]
    return json.loads(p.stdout)


# ===========================================================================
# P11B3-01 — motorun KENDİ hükmü rozette; yeşil kazanılmamışsa basılmaz
# ===========================================================================
@node_gerekli
class TestP11B301MotorunKendiHukmu:

    @pytest.fixture(scope='class')
    def kars(self, fea_yaniti):
        k = ((fea_yaniti['fea'].get('meta') or {})
             .get('motor_sf_karsilastirmasi'))
        assert isinstance(k, dict), (
            'ölçüm tabanı çürüdü: uç motor_sf_karsilastirmasi yayımlamıyor')
        return k

    def test_olcum_tabani_iki_sayi_ayrisiyor(self, kars):
        """Zemin: köprü ile motorun katsayıları GERÇEKTEN ayrışıyor."""
        assert isinstance(kars.get('motor_safety_factor'), float)
        assert isinstance(kars.get('kopru_min_safety_factor'), float)
        assert kars['motor_safety_factor'] < kars['kopru_min_safety_factor'], (
            'ölçüm tabanı çürüdü: motorun katsayısı köprününkinden '
            'küçük değil, kalem bu koşumda üretilmiyor')

    def test_motorun_sayisi_ekranda(self, tmp_path, fea_yaniti, kars):
        e = _ekran(tmp_path, fea_yaniti)
        beklenen = '%.2f' % kars['motor_safety_factor']
        assert beklenen in e['rozet'], (
            'motorun kendi emniyet katsayısı (' + beklenen + ') rozet '
            'satırında yok: ' + e['rozet'][:300])

    def test_kopru_yesili_kazanilmamissa_basilmaz(self, tmp_path, fea_yaniti,
                                                  kars):
        """Hüküm rengi KÖTÜMSER: yayımlanan en kötü sayıdan verilir."""
        e = _ekran(tmp_path, fea_yaniti)
        assert e['sf_rozet_turu'] is not None, 'SF rozeti bulunamadı'
        assert e['sf_rozet_turu'] != 'ok', (
            'motorun katsayısı ' + repr(kars['motor_safety_factor'])
            + ' iken köprü rozeti hâlâ YEŞİL: ' + repr(e['sf_rozet_turu']))
        assert e['motor_rozeti_turu'] is not None, (
            'motorun kendi katsayısı için ayrı rozet basılmıyor')

    def test_akmanin_niteligi_rozet_satirinda(self, tmp_path, fea_yaniti,
                                              kars):
        """Derate edilmemiş akma künyeyi açmadan görülmeli."""
        if kars.get('kopru_akma_derate_edildi') is not False:
            pytest.skip('bu koşumda akma derate edilmiş; kalem dışı dal')
        e = _ekran(tmp_path, fea_yaniti)
        assert e['rozette_akma_niteligi'], (
            'rozet satırı akmanın oda sıcaklığı değeri olduğunu '
            'söylemiyor: ' + e['rozet'][:300])

    def test_totolojik_sayi_totolojik_diye_basiliyor(
            self, tmp_path, fea_yaniti, kars):
        """Uç "bağımsız doğrulama değil" diyorsa panel bunu gizlemez."""
        mk = kars.get('motor_kaynagi')
        if not (isinstance(mk, dict)
                and mk.get('safety_factor_is_tautological') is True):
            pytest.skip('bu koşumda motor katsayısı totolojik değil')
        e = _ekran(tmp_path, fea_yaniti)
        assert re.search(r'not an independent verification|bağımsız bir '
                         r'doğrulama değildir', e['rozet']), (
            'ucun totoloji beyanı ekranda yok: ' + e['rozet'][:400])

    def test_karsilastirma_gelmezse_iddia_edilmez(self, tmp_path, fea_yaniti):
        """Fail-closed: blok yoksa panel sayı UYDURMAZ, yeşili geri alır."""
        import copy
        kopya = copy.deepcopy(fea_yaniti)
        kopya['fea']['meta'].pop('motor_sf_karsilastirmasi', None)
        e = _ekran(tmp_path, kopya)
        assert e['motor_rozeti_turu'] is None, (
            'karşılaştırma bloğu yokken motor rozeti basılıyor (uydurma)')
        assert not e['rozette_akma_niteligi'], (
            'karşılaştırma bloğu yokken akma niteliği İDDİA EDİLİYOR')


# ===========================================================================
# P11B3-06 — koşumun girdileri ekranda; ölü gönderme kalmadı
# ===========================================================================
@node_gerekli
class TestP11B306KosumGirdileriEkranda:

    @pytest.fixture(scope='class')
    def skalerler(self, fea_yaniti):
        sc = fea_yaniti['fea'].get('scalars') or {}
        for a in ('material_key', 'yield_strength_pa', 'wall_thickness_m',
                  'inner_pressure_pa'):
            assert sc.get(a) is not None, (
                'ölçüm tabanı çürüdü: uç ' + a + ' yayımlamıyor')
        return sc

    def test_dort_girdi_de_kunye_kabinda(self, tmp_path, fea_yaniti,
                                         skalerler):
        e = _ekran(tmp_path, fea_yaniti)
        k = e['kunye']
        assert str(skalerler['material_key']) in k, (
            'malzeme adı ekranda yok')
        assert ('%.1f' % (skalerler['yield_strength_pa'] / 1e6)) in k, (
            'akma dayanımı ekranda yok')
        assert ('%.2f' % (skalerler['wall_thickness_m'] * 1000)) in k, (
            'cidar kalınlığı ekranda yok')
        assert ('%.2f' % (skalerler['inner_pressure_pa'] / 1e5)) in k, (
            'iç basınç ekranda yok')

    def test_olu_gonderme_hedefi_artik_basiliyor(self, tmp_path, fea_yaniti):
        """`girdiler.yuk`a yollayan cümle varsa o blok da ekranda olmalı."""
        e = _ekran(tmp_path, fea_yaniti)
        if not e['girdiler_yuk_gondermesi']:
            pytest.skip('bu koşumda not_modelled girdiler.yuk demiyor')
        y = ((fea_yaniti['fea'].get('meta') or {})
             .get('girdiler') or {}).get('yuk') or {}
        assert isinstance(y.get('dagilim'), str) and y['dagilim'], (
            'ölçüm tabanı çürüdü: girdiler.yuk.dagilim yok')
        assert y['dagilim'][:60] in e['kunye'], (
            'ekran kullanıcıyı hâlâ basılmayan bir bloğa yolluyor')

    def test_eksik_skaler_uydurulmaz(self, tmp_path, fea_yaniti):
        """Fail-closed: alan yoksa satırda o kalem HİÇ yazılmaz."""
        import copy
        kopya = copy.deepcopy(fea_yaniti)
        kopya['fea']['scalars'].pop('material_key', None)
        e = _ekran(tmp_path, kopya)
        i = e['kunye'].find('solved with')
        j = e['kunye'].find('solved with') + 200
        satir = e['kunye'][i:j] if i >= 0 else ''
        assert 'material' not in satir, (
            'malzeme yayımlanmadığı hâlde satırda anılıyor: ' + satir)
        assert 'yield' in satir, (
            'kalan girdiler de düştü — satır tümden kayboldu: ' + satir)


# ===========================================================================
# P12bB1-05 / P12bB1-07 — Fable-D17 ŞARTLARININ kanıt hijyeni
# ===========================================================================
class TestFableD17Sartlari:

    def test_b1_05_rapor_artefakti_geri_alindi(self):
        rap = (kanit_gerekli(D17KANIT / 'rapor.md')).read_text(encoding='utf-8')
        par = re.search(r'### P12bB1-05.*?(?=\n### )', rap, re.S)
        assert par, 'P12bB1-05 paragrafı bulunamadı'
        par = par.group(0)
        # Düzeltme metni eski cümleyi ALINTILAYARAK geri alıyor; alıntı
        # iddia değildir. Tırnak içindeki bölgeler çıkarıldıktan sonra
        # cümle CANLI İDDİA olarak duruyorsa bekçi kırılır.
        canli = re.sub(r'["“”][^"“”]*'
                       r'["“”]', ' ', par)
        assert 'üç metin de yüzde semantiği taşıyordu' not in canli, (
            'ölçüm artefaktına dayanan iddia raporda CANLI duruyor')
        assert 'M5_yeniden_olcum_D19.json' in par, (
            'düzeltilmiş paragraf yeniden ölçümü anmıyor')

    def test_b1_05_yeniden_olcum_tabanin_bar_oldugunu_gosteriyor(self):
        j = json.loads((kanit_gerekli(D17KANIT / 'M5_yeniden_olcum_D19.json'))
                       .read_text(encoding='utf-8'))
        taban = j['TABAN_2426b4d']['EN']
        assert taban['ham_percentage_kelimesi'] is True, (
            'ölçüm tabanı çürüdü: eski metrik zaten yeşilmiş')
        assert taban['net_percentage_kelimesi'] is False, (
            'tabandaki "percentage" olumsuzlamadan gelmiyormuş — D19 '
            'düzeltmesinin dayanağı çürük')
        assert taban['15_25_ogretisi'] is True, (
            'D17ün gerçek katkısı (15-25 öğretisinin kaldırılması) '
            'ölçümde görünmüyor')
        simdi = j['SIMDI_calisma_agaci']['EN']
        assert simdi['15_25_ogretisi'] is False
        assert simdi['bar_var'] is True

    def test_b1_05_metrik_olumsuzlamayi_saymiyor(self):
        src = (kanit_gerekli(D17KANIT / 'olcum.py')).read_text(encoding='utf-8')
        assert 'M5_OLUMSUZLAMA' in src, (
            'M5 metriği olumsuzlama istisnası taşımıyor')
        assert 'ham_percentage_kelimesi' in src, (
            'eski ölçüm karşılaştırma için saklanmamış')

    def test_b1_07_gevsek_iddialar_geri_gelmedi(self):
        src = (KOK / 'tests' / 'test_d15_sablonlar_a1.py').read_text(
            encoding='utf-8')
        fn = re.search(
            r'def test_b1_07_yorunge_yanma_suresi_motorun_debisinden'
            r'.*?(?=\ndef )', src, re.S)
        assert fn, 'D15 bekçisi bulunamadı'
        # Yorum satırları gevşetmenin NE OLDUĞUNU anlatıyor; iddia
        # değildir. Kod satırlarına bakılır.
        kod = '\n'.join(sat for sat in fn.group(0).split('\n')
                        if not sat.strip().startswith('#'))
        assert "or 'burn_time: tYanma' in g" not in kod, (
            'gevşetilmiş "or" iddiası geri gelmiş')
        assert "'mItici / trMdot' in liquid_src" not in kod, (
            'dosya geneli araması geri gelmiş: HTML yorumu bekçiyi '
            'kör ediyor')
        assert '_yorumsuz(' in kod, 'yorumlar sökülmeden aranıyor'

    def test_b1_07_rapor_gevsetmeyi_ilan_ediyor(self):
        rap = (kanit_gerekli(D17KANIT / 'rapor.md')).read_text(encoding='utf-8')
        assert 'burada bir GEVŞETME vardı' in rap, (
            'rapor hâlâ "yalnız EKLEME" diyor')
        mut = (kanit_gerekli(D17KANIT / '04_mutasyon.txt')).read_text(encoding='utf-8')
        assert 'const tYanma = 30;' in mut, (
            'körlük mutasyonu kayda geçmemiş')


# ===========================================================================
# P11B3-07 — viskoz koşunun BÜTÇESİ rozette; Euler biçimi nitelenmiş
# ===========================================================================
#: GERÇEK viskoz koşum kaydı (71,5 s; `viskoz_uret.py` bir kez üretti).
#: Canlı koşum bekçide koşulmaz — sayılar uydurma DEĞİL, o koşumun
#: kendi yanıtıdır; bekçi paneli o yanıtla sürer.
KAYIT_VISKOZ = KANIT / 'kayit_cfd_viskoz.json'


@node_gerekli
class TestP11B307ViskozButceRozeti:

    @pytest.fixture(scope='class')
    def viskoz(self):
        assert kanit_gerekli(KAYIT_VISKOZ).exists(), 'viskoz koşum kaydı yok'
        return json.loads(kanit_gerekli(KAYIT_VISKOZ).read_text(encoding='utf-8'))

    def _cfd_ekran(self, tmp_path, yanit, static_dir=None):
        y = tmp_path / 'cfd.json'
        y.write_text(json.dumps(yanit), encoding='utf-8')
        p = subprocess.run(
            [NODE, kanit_gerekli(str(KANIT / 'cfd_ekran_harness.js')),
             str(static_dir or STATIC_JS), str(y)],
            capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, 'node altında çöktü:\n' + p.stderr[-3000:]
        return json.loads(p.stdout)

    def test_olcum_tabani_iki_sayi_mertebelerce_ayri(self, viskoz):
        b = viskoz['cfd']['budget']
        e = b.get('energy_balance_rel')
        v = b.get('viscous_energy_balance_rel')
        assert isinstance(e, float) and isinstance(v, float), (
            'ölçüm tabanı çürüdü: viskoz koşum iki bütçeyi yayımlamıyor')
        assert e / v > 1e3, (
            'ölçüm tabanı çürüdü: iki sayı artık ayrışmıyor '
            '(' + repr(e) + ' / ' + repr(v) + ')')

    def test_viskoz_butce_rozette(self, tmp_path, viskoz):
        e = self._cfd_ekran(tmp_path, viskoz)
        assert e['viskoz_butce_ekranda'] is True, (
            'ucun "viskoz koşunun bütçesi budur" dediği alan ekranda yok: '
            + e['rozet_metni'][:400])

    def test_euler_bicimi_tek_basina_okunmaz_diye_yaziliyor(self, tmp_path,
                                                            viskoz):
        e = self._cfd_ekran(tmp_path, viskoz)
        assert e['euler_bicimi_niteleniyor'] is True, (
            'Euler biçimi hâlâ nitelenmeden "ENERGY IMBALANCE" diye '
            'basılıyor: ' + e['rozet_metni'][:400])

    def test_euler_kosumunda_eski_rozet_korunur(self, tmp_path, viskoz):
        """Euler koşusunda alan None'dır — sıfır değil, YOK: uydurma yok."""
        import copy
        kopya = copy.deepcopy(viskoz)
        kopya['cfd']['budget']['viscous_energy_balance_rel'] = None
        e = self._cfd_ekran(tmp_path, kopya)
        assert e['euler_bicimi_niteleniyor'] is False, (
            'Euler koşusunda olmayan viskoz bütçe İDDİA EDİLİYOR')
        assert re.search(r'ENERGY IMBALANCE [0-9.e+-]+ \(relative\)',
                         e['rozet_metni']), (
            'Euler koşusunda eski rozet kayboldu: '
            + e['rozet_metni'][:300])
