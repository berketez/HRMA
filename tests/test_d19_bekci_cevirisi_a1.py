#!/usr/bin/env python3
"""ÖH Dalga-19 · kulvar **bekci-cevirisi** · aşama a1.

Bu dosya D19'da onarılan kalemlerin bekçisidir. Her sınıf tek bir defter
kalemine bakar ve o kalemin kusurunu TERS MUTASYONLA görür (kanıt:
``docs/scofield/raw/OH/D19/bekci-cevirisi/a1/mutasyon*.json``).

Kalemler
--------
* **P10B4-07** — ``tools/wiring_map.py``in yayımladığı "sabit çıktı yaprağı"
  sayısı ÖLÇÜM GÜCÜNE bağlı; giriş sayfası o sayıyı KAPI ÖLÇÜTÜ diye
  öneriyordu.
* **P13B3-05** — ilan edilen ``pytest.approx`` toleranslarının %86,4'ü hiç
  iş yapmıyor; gevşek eşikler bit-özdeş karşılaştırmaların üstünde duruyor.
* **P13B4-10** — kampanya kritiklerinin kapsam envanteri (D18'de kilitlendi,
  D19'da taban güncellendi).
"""
from __future__ import annotations

import ast
import importlib
import json
import pathlib
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D19' / 'bekci-cevirisi' / 'a1'


def _wiring_map():
    sys.path.insert(0, str(KOK / 'tools'))
    return importlib.import_module('wiring_map')


# ===========================================================================
# P10B4-07 — "sabit yaprak" sayısı ölçüm gücüne bağlı; kapı hükmü kazanılmalı
# ===========================================================================
class _SahteRapor:
    """``build_index``in okuduğu en küçük rapor yüzeyi."""

    def __init__(self):
        self.live_inputs = {'a': 1}
        self.dead_inputs = []
        self.echo_only_inputs = []
        self.unmeasurable = {}
        self.declared_but_live = []
        self.constant_outputs = []
        self.baseline_leaves = {}
        self.baseline_leaf_count = 0
        self.changed_paths = {}


def _index(erimeler):
    wm = _wiring_map()
    yazilan = [('solid', pathlib.Path('wiring_map_solid.html'), _SahteRapor())]
    return wm.build_index(yazilan, '2026-09-03 00:00', erimeler)


class TestP10B407KapiHukmuKazanilir:
    """ÖH D19 · P10B4-07 — ölçülmemiş eşik KAPI diye yayımlanamaz.

    ÖLÇÜLDÜ (D19, taban 60cd341, ``olcum_p10b407.py``; P10'un kendi
    ``B4-repro-09.py`` betiğinin bu ağaca çevrilmiş hâli):

        solid  : zayıf sarsımda 200 "sabit" yaprak → güçlü sarsımda
                 **200/200 (%100)** oynuyor; iki ölçümde de sabit kalan **0**.
                 Sınıflandırılmamış 30 yaprağın **30'u** eriyor.
        hybrid : 231 → **39/231 (%16,9)** eriyor, 192 kalıyor;
                 sınıflandırılmamış 54'ün 6'sı eriyor.

    Yani giriş sayfasının ÖNCEDEN yayımladığı cümle —
    *"izlenen tek sayı sınıflandırılmamış, hedefi sıfırdır"* — katı
    sayfasında tamamen artifakt bir sayıya kapı kuruyordu: kapatmanın yolu
    kusuru düzeltmek değil sarsımı zayıflatmak olurdu.

    Onarım FAIL-CLOSED: erime ölçülmediyse HÜKÜM YAYIMLANMAZ (adlı ret),
    ölçüldüyse artifakt payı sayıyla yanında durur, ve hüküm ancak erime
    sıfırken "hedefi sıfırdır" diye kurulur.
    """

    def test_olculmemis_kapi_hukmu_yayimlanmaz(self):
        """Erime ölçülmediyse eski kapı cümlesi sayfada OLMAMALI."""
        html = _index({'solid': None})
        assert 'hedefi sıfırdır' not in html, (
            'erime ölçülmeden "hedefi sıfırdır" kapı ölçütü yayımlandı — '
            'ölçüm gücüne bağlı bir sayıya kapı kuruluyor (P10B4-07)')
        assert 'Kapı ölçütü YAYIMLANMADI' in html, (
            'ölçülmemiş hüküm sessizce düşürülmüş: adlı ret yok')

    def test_eriyen_varken_kapi_hukmu_yayimlanmaz(self):
        """Ölçüldü ve eriyor → sayı yayımlanır, HÜKÜM yayımlanmaz."""
        html = _index({'solid': {'olculdu': True, 'toplam': 200,
                                 'eriyen': 200, 'kalan': 0, 'yuzde': 100.0,
                                 'deneme': 325}})
        assert 'hedefi sıfırdır' not in html, (
            '200/200 eriyen bir sayıya hâlâ kapı kuruluyor')
        assert '%100.0' in html and '200' in html, (
            'artifakt payı sayıyla yayımlanmıyor')

    def test_erime_sifirken_hukum_kazanilir(self):
        """Erime 0 ölçüldüyse kapı hükmü MEŞRUDUR ve yayımlanır."""
        html = _index({'solid': {'olculdu': True, 'toplam': 200,
                                 'eriyen': 0, 'kalan': 200, 'yuzde': 0.0,
                                 'deneme': 325}})
        assert 'hedefi sıfırdır' in html, (
            'erime sıfır ölçüldüğü hâlde hüküm yayımlanmıyor — '
            'fail-closed fail-open değil, ölçülen hükmü de bastırıyor')

    def test_detay_sayfasi_meta_satiri_erimeyi_soyler(self):
        """Detay sayfasının meta satırı ölçüm gücünü SAKLAMAZ."""
        wm = _wiring_map()
        assert wm.erime_meta(None) == wm.ERIME_OLCULMEDI
        assert 'kapı ölçütü DEĞİLDİR' in wm.ERIME_OLCULMEDI
        olculu = wm.erime_meta({'olculdu': True, 'toplam': 231, 'eriyen': 39,
                                'kalan': 192, 'yuzde': 16.9, 'deneme': 135})
        assert '39/231' in olculu and '192' in olculu

    def test_erime_olcumu_tek_kaynaktan_gelir(self):
        """``erime_olc`` kendi sarsımını YAZMAZ; kardeş aracı çağırır.

        Aynı kesişimi iki yerde hesaplamak, iki sayının ayrışmasıyla biten
        kampanya kalıbıdır (TEK KAYNAK). ``tools/sabit_tarayici.py::tara``
        bu ölçümü zaten yapıyordu ve hiçbir tüketicisi yoktu.
        """
        kaynak = (KOK / 'tools' / 'wiring_map.py').read_text(encoding='utf-8')
        agac = ast.parse(kaynak)
        fn = [d for d in ast.walk(agac)
              if isinstance(d, ast.FunctionDef) and d.name == 'erime_olc']
        assert len(fn) == 1, 'erime_olc kayboldu'
        cagrilar = {getattr(c.func, 'attr', None) for c in ast.walk(fn[0])
                    if isinstance(c, ast.Call)}
        assert 'tara' in cagrilar, (
            'erime_olc artık sabit_tarayici.tara çağırmıyor — sarsım ikinci '
            'kez yazılmışsa iki sayı ayrışır (P10B4-07 / TEK KAYNAK)')

    def test_tarayici_erime_alanlarini_yayimlar(self):
        """``sabit_tarayici.tara`` erime sayısını ADIYLA döndürür."""
        kaynak = (KOK / 'tools' / 'sabit_tarayici.py').read_text(
            encoding='utf-8')
        for alan in ("'zayif_sarsim_sabit'", "'eriyen'"):
            assert alan in kaynak, (
                f'sabit_tarayici.tara {alan} alanını yayımlamıyor — '
                'wiring_map erimeyi ölçemez')

    def test_olculen_erime_kaniti_dosyada_durur(self):
        """Kalemin sayısı raporda değil, ÖLÇÜM DOSYASINDA durur."""
        for ad, bekleyen in (('once_p10b407_solid.json', 100.0),
                             ('once_p10b407_hybrid.json', 16.9)):
            veri = json.loads((kanit_gerekli(KANIT / ad)).read_text(encoding='utf-8'))
            assert veri['eriyen_yuzde'] == pytest.approx(bekleyen, abs=0.1), (
                f'{ad}: ölçülen erime payı değişmiş')
            assert veri['zayif_sarsim_sabit'] > 0


# ===========================================================================
# P13B3-05 — ilan edilen tolerans bir kez bile sınanmamış
# ===========================================================================
#: ÖH D19 · P13B3-05 — ölçülen alt kümede "GEVŞEK EŞİK + ÖLÜ BANT" yerleri.
#: Ölçüm: ``docs/scofield/raw/OH/D19/bekci-cevirisi/a1/once_p13b305.json``
#: (7 dosya, 535 geçen karşılaştırma; %97,6 ölü+kör; beyansız 82'nin 82'si
#: bit-özdeş). Kural: bu yerlerin her biri ya KİMLİĞE çevrilir, ya bandın
#: NEDEN kalması gerektiği ÖLÇÜMLE gerekçelenir. Üçüncü seçenek — sessiz
#: gevşek eşik — kapalıdır.
GEVSEK_ESIK_OLU_BANT = {
    'tests/test_materials_db.py': {
        'hukum': 'KIMLIGE_CEVRILDI',
        'imza': "rel=1e-12), (",
        'yasak': "thermal_conductivity'], rel=0.05",
    },
    'tests/test_regen_cooling.py': {
        'hukum': 'GEREKCELENDI',
        'imza': 'Incropera Tablo A.6',
        'yasak': None,
    },
    'tests/test_structural_validation.py': {
        'hukum': 'GEREKCELENDI',
        'imza': 'eğrinin 500 °C',
        'yasak': None,
    },
    'tests/test_injector_design.py': {
        'hukum': 'GEREKCELENDI',
        'imza': 'sayısal bir kök bulucudur',
        'yasak': None,
    },
}


@pytest.fixture(scope='module')
def bant_olcumu():
    yol = KANIT / 'once_p13b305.json'
    assert kanit_gerekli(yol).exists(), (
        'P13B3-05 bant sağlığı ölçümü kayıp — envanteri olmayan bekçinin '
        'hükmü "temiz" değil "ÖLÇEMEDİM"dir (fail-closed)')
    return json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))


class TestP13B305IlanEdilenBantHesapVerir:
    """ÖH D19 · P13B3-05 — ilan edilen tolerans ya sınanır ya gerekçelenir.

    ÖLÇÜLDÜ (D19, taban 60cd341; P13'ün kendi ``p13b3_approx_probe``
    eklentisi + ``B3-repro-10`` sınıflandırması, 7 dosyalık alt küme):

        535 geçen karşılaştırma → ÖLÜ 432 · KÖR 90 · SAĞLIKLI 13
        ölü+kör = **%97,6**
        tolerans BEYANSIZ olan 82 karşılaştırmanın **82'si (%100)**
        bit-özdeş → varsayılan ``rel=1e-6`` seçilmemiş, yazılmamış.

    Kalemin çekirdeği "%97,6 kötü" değil: **ilan edilen bantların bir kez
    bile sınanmamış olması.** ``rel=0.05`` yazan bir bekçi bugün kimlik
    denetimi yapıyor, yarın sessizce %5 kaymayı kabul edecek.

    Onarım iki yönlü ve FAIL-CLOSED:
      * Karşılaştırma bir hesap değil KOPYA KİMLİĞİ ise bant kimliğe
        çevrilir (``test_materials_db.py``: ``rel=0.05`` → ``rel=1e-12``;
        ölçüldü, k_curve'lü 3 malzemenin 3'ünde de ayrışan yok).
      * Bandın kalması gerekiyorsa gerekçe ÖLÇÜMLE ve ADIYLA yazılır
        (referans tablosunun yuvarlama basamağı, eğri düğümü, kök
        bulucunun yakınsama gürültüsü).
    """

    def test_envanter_bosalmadi(self, bant_olcumu):
        """Fail-closed: ölçüm boşalırsa hüküm "temiz" olmaz."""
        assert bant_olcumu['toplam_karsilastirma'] >= 500, (
            'bant sağlığı ölçümü küçülmüş; envanter çürüdü')
        assert bant_olcumu['gevsek_esik_olu_bant_yer_sayisi'] == len(
            GEVSEK_ESIK_OLU_BANT), (
            'ölçülen "gevşek eşik + ölü bant" yer sayısı ile bu dosyadaki '
            'hüküm tablosu ayrıştı — yeni bir yer eklendiyse hükmü de '
            'yazılmalı')

    @pytest.mark.parametrize('dosya', sorted(GEVSEK_ESIK_OLU_BANT))
    def test_gevsek_esik_ya_cevrildi_ya_gerekcelendi(self, dosya):
        """Üçüncü seçenek yok: sessiz gevşek eşik kapalıdır."""
        kural = GEVSEK_ESIK_OLU_BANT[dosya]
        kaynak = (KOK / dosya).read_text(encoding='utf-8')
        assert kural['imza'] in kaynak, (
            f'{dosya}: {kural["hukum"]} imzası kayboldu — ilan edilen bant '
            'yine sınanmamış/gerekçesiz duruma döndü (P13B3-05)')
        assert 'P13B3-05' in kaynak, (
            f'{dosya}: bandın hükmü hangi kaleme bağlı olduğunu söylemiyor')
        if kural['yasak']:
            assert kural['yasak'] not in kaynak, (
                f'{dosya}: eski gevşek eşik {kural["yasak"]} geri geldi')

    def test_kopya_kimligi_bant_kabul_etmez(self):
        """``k_curve`` ⟷ ``thermal_conductivity``: iki kopya, tek sayı.

        Bu, çevirmenin ÜRÜN tarafındaki karşılığıdır: bant daralmadan önce
        de bugün de fark 0'dır; onarım bandın YARIN kabul edeceğini kapatır.
        """
        from hrma.data.materials_db import MATERIALS
        ayrisan = []
        olculen = 0
        for ad, kayit in MATERIALS.items():
            if 'k_curve' not in kayit or 'thermal_conductivity' not in kayit:
                continue
            olculen += 1
            T0 = min(kayit['k_curve'])
            if kayit['k_curve'][T0] != kayit['thermal_conductivity']:
                ayrisan.append(ad)
        assert olculen >= 3, 'k_curve taşıyan malzeme kalmamış'
        assert not ayrisan, (
            f'aynı kaydın iki kopyası ayrıştı: {ayrisan}')

    def test_beyansiz_tolerans_payi_kayitli(self, bant_olcumu):
        """Beyansız karşılaştırmaların bit-özdeşliği ADIYLA yayımlanır."""
        assert bant_olcumu['beyansiz'] > 0
        assert bant_olcumu['beyansiz_bit_ozdes_yuzde'] >= 90.0, (
            'beyansız toleransların bit-özdeşlik payı ölçümde düştüyse '
            'envanter yeniden alınmalı (kalemin sayısı bayat)')


# ===========================================================================
# P13B4-10 — "44 kritikte sembolü ANAN test yok" ölçütünün kendisi ölçülür
# ===========================================================================
import re  # noqa: E402  (kalem bloğuna yakın dursun)

_KRITIK_TABLOSU = (KOK / 'docs' / 'scofield' / 'raw' / 'P13' /
                   'B4-cikti-12-kritikler.json')
_SEMBOL = re.compile(r'`([A-Za-z_][\w./\-]{3,})`')

#: D19 ölçümü (``once_p13b410.json``): kademe dağılımı.
#: D2 küçülemez, D1x büyüyemez, GERÇEK D1 sıfırdan büyüyemez.
KADEME_TABANI = {'D2': 13, 'D1': 0, 'D1x-ÖLÇÜLEMEDİ': 30, '?dosya-yok': 11}

#: D1x kümesindeki 30 kritiğin defterde ARTIK kapalı/onarılmış olanları.
#: D18 bu kalemi "30'unun her biri BUGÜN AÇIK ürün kusuru" gerekçesiyle
#: engelli bırakmıştı; ölçüldü ki 23'ü artık açık değil.
D1X_DEFTERDE_KAPALI = 23


def _kademe_hesapla():
    veri = json.loads(kanit_gerekli(_KRITIK_TABLOSU).read_text(encoding='utf-8'))
    parca = []
    for p in sorted((KOK / 'tests').rglob('*.py')):
        if '__pycache__' in p.parts:
            continue
        parca.append(p.read_text(encoding='utf-8', errors='replace'))
    yazi = '\n'.join(parca)
    kademe = {}
    for kid, k in veri.items():
        dosya = k.get('dosya', '')
        modul = pathlib.Path(dosya).stem if dosya else ''
        semboller = [s for s in _SEMBOL.findall(k['baslik'])
                     if not s.endswith(('.py', '.js', '.html'))
                     and '/' not in s]
        if not modul:
            kademe[kid] = '?dosya-yok'
        elif modul not in yazi:
            kademe[kid] = 'D0'
        elif not semboller:
            # ÖLÇÜLEMEDİ ≠ KUSURLU (aşağıdaki testin konusu).
            kademe[kid] = 'D1x-ÖLÇÜLEMEDİ'
        elif not any(s in yazi for s in semboller):
            kademe[kid] = 'D1'
        else:
            kademe[kid] = 'D2'
    return kademe


@pytest.fixture(scope='module')
def kademeler():
    return _kademe_hesapla()


class TestP13B410OlcutunKendisiOlculur:
    """ÖH D19 · P13B4-10 — "sembolü ANAN test yok" hükmü ölçülemeyeni saymaz.

    Kalemin başlığı: *"kampanya kritiklerinin 44'ünde kusuru tanımlayan
    sembolü ANAN tek test yok"*. D17 ve D18'de ölçüm koşuldu ve kalan borç
    **D1 = 30 kritik** ("ürün dosyası anılıyor, SEMBOL anılmıyor") diye
    yayımlandı; D18 bunu "30'unun her biri BUGÜN AÇIK ürün kusuru, sembolü
    anan test ya kusuru korur ya kırmızı olur" gerekçesiyle engelli bıraktı.

    ÖLÇÜLDÜ (D19, taban 60cd341, ``olcum_p13b410.py``) — ÖLÇÜTÜN KENDİSİ
    KUSURLU:

      * D1 kümesindeki **30 kritiğin 30'unun** başlığından ÇIKARILABİLEN
        sembol YOK (ters tırnaklı tanımlayıcı hiç yok, ya da tek aday
        ``.py``/``.js``/``.html`` süzgecine takılıyor — ör. P10B4-01'in
        başlığındaki ``iddia_lint.py``).
      * ``any(s in yazi for s in [])`` HER ZAMAN ``False``tur. Yani bu 30
        kritik, deponun bekçi kapsamı ne olursa olsun D2'ye ÇIKAMAZ.
      * Dolayısıyla "sembolü anan test yok" hükmü burada bir KAPSAM ölçümü
        değil, ÖLÇÜLEMEME durumunun kusur diye yayımlanmasıdır (fail-open).

    Onarım (bu kulvarın sahasında, ölçüt tarafında): dördüncü kademe
    ``D1x-ÖLÇÜLEMEDİ`` ADIYLA ayrıldı. Ölçülemeyen ölçülemedi diye
    yayımlanır; GERÇEK D1 (sembol çıkarıldı ama testlerde geçmiyor) bugün
    **0**'dır ve büyümesi kırmızıdır.

    İkinci ölçüm — D18'in engel gerekçesi de artık dar: D1x'teki 30
    kritiğin **23'ü** defterde ``kapali``/``onarildi``. "Hepsi bugün açık
    kusur" gerekçesi 30'un 7'si için geçerli.
    """

    def test_kritik_evreni_bosalmadi(self, kademeler):
        assert len(kademeler) >= 54, (
            f'kampanya kritik tablosu küçüldü: {len(kademeler)}')

    def test_olculemeyen_kritik_D1_diye_yayimlanmaz(self, kademeler):
        """Fail-closed: sembolü çıkarılamayan kritik "sembolü anılmıyor"
        diye sayılamaz — ölçülemeyen ölçülemedi diye durur."""
        veri = json.loads(kanit_gerekli(_KRITIK_TABLOSU).read_text(encoding='utf-8'))
        for kid, kd in kademeler.items():
            if kd != 'D1':
                continue
            semboller = [s for s in _SEMBOL.findall(veri[kid]['baslik'])
                         if not s.endswith(('.py', '.js', '.html'))
                         and '/' not in s]
            assert semboller, (
                f'{kid}: sembolü ÇIKARILAMADIĞI hâlde D1 ("sembol '
                'anılmıyor") sayıldı — ölçülemeyen kusur diye yayımlanıyor')

    def test_kademe_tabani_gerilemez(self, kademeler):
        """D2 küçülemez, D1x büyüyemez, gerçek D1 sıfırdan büyüyemez."""
        sayim = {}
        for kd in kademeler.values():
            sayim[kd] = sayim.get(kd, 0) + 1
        assert sayim.get('D0', 0) == 0, (
            f"D0 (ürün dosyasını hiçbir test anmıyor) geri geldi: "
            f"{sayim.get('D0')}")
        assert sayim.get('D2', 0) >= KADEME_TABANI['D2'], (
            f"D2 (sembolü anan test var) küçüldü: {sayim.get('D2')} < "
            f"{KADEME_TABANI['D2']}")
        assert sayim.get('D1', 0) <= KADEME_TABANI['D1'], (
            f"GERÇEK D1 büyüdü: {sayim.get('D1')} — sembolü çıkarılabilen "
            'bir kritiğin bekçisi kaybolmuş')
        assert sayim.get('D1x-ÖLÇÜLEMEDİ', 0) <= (
            KADEME_TABANI['D1x-ÖLÇÜLEMEDİ']), (
            f"ölçülemeyen kritik sayısı büyüdü: "
            f"{sayim.get('D1x-ÖLÇÜLEMEDİ')}")

    def test_olculemeyenlerin_defter_durumu_kayitli(self):
        """D18'in engel gerekçesi ölçümle daraltıldı ve dosyada durur."""
        veri = json.loads(
            (kanit_gerekli(KANIT / 'once_p13b410.json')).read_text(encoding='utf-8'))
        assert veri['D1x_olculemedi'] == KADEME_TABANI['D1x-ÖLÇÜLEMEDİ']
        assert veri['D1_gercek'] == KADEME_TABANI['D1']
        assert veri['D1_defterde_kapali_veya_onarildi'] == D1X_DEFTERDE_KAPALI
        assert len(veri['D1_kapali_kimlikler']) == D1X_DEFTERDE_KAPALI
