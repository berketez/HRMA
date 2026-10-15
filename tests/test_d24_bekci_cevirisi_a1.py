# -*- coding: utf-8 -*-
"""ÖH Dalga-24 · kulvar bekci-cevirisi · aşama 1/1 — bekçilerin bekçisi.

Bu dosya ürün davranışını değil BEKÇİLERİN KENDİSİNİ savunur: bir iddianın
kusuru gerçekten gördüğünü, bir tarayıcının kör noktasının büyümediğini,
bir envanterin gevşemediğini.

Kapsanan kalemler
-----------------
OH-D23-09  monotonluk iddiası alt-dizeyle değil YÖNÜYLE okunur
OH-D23-11  bayat metin / kanıt hijyeni demeti (kapısız 'skip' künyesi,
           saf-Python sözleşmesini yutan modül atlaması, bayat yorum,
           rapordaki ölçümle çelişen sayı)
OH-D23-12  rota tarayıcısı literal-kör değil (değişken / f-string /
           birleştirme çözülür, çözülemeyenin tavanı kilitli)
OH-D23-22  i18n anahtarı EN bloğunun İÇİNE yazılır (dosya sonuna eklenen
           anahtar bekçinin kestiği EN sözlüğünde görünmez)
OH-D23-01  iddiasız test nüfusu (ilk dilim) — tavan ölçülen sayıya çekilir
P15B3-10   sarsım matrisi üç ucun ötesine geçer (uç kataloğu sürülür)

Her iddia, savunduğu kusuru gördüğü TERS MUTASYONLA doğrulanmıştır; kanıt
``docs/scofield/raw/OH/D24/bekci-cevirisi/a1/mutasyon_*.json``.
"""

import ast
import io
import os

import pytest

import tests.test_d16_kati_a1 as d16
import tests.test_d18_bekci_cevirisi_a1 as d18
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ===========================================================================
# OH-D23-09 — monotonluk iddiasının YÖNÜ okunur
# ===========================================================================
class TestOHD2309MonotonlukYonu:
    """Eski bekçi ``'monoton' in parca`` yazıyordu; 'monoton' 'monotonic'in
    ALT DİZESİ olduğu için metin tam TERSİNİ söylese de geçiyordu."""

    def test_olumlu_iddia_OLUMSUZ_sayilmaz(self):
        olumlu, olumsuz = d16.monotonluk_iddialari(
            'but the trend is monotonic (0.11 at 10 mm)')
        assert olumlu, 'monotonluk VAAT eden cümle olumlu sayılmadı'
        assert not olumsuz

    def test_olumsuz_iddia_taninir(self):
        for metin in ('but the trend is not monotonic (0.11)',
                      'ölçülen eğilim monoton değil (0,11)',
                      'the trend is NOT MONOTONIC'):
            olumlu, olumsuz = d16.monotonluk_iddialari(metin)
            assert olumsuz, metin
            assert not olumlu, metin

    def test_alt_dize_denetimi_yeterli_olsaydi_ayirt_edemezdi(self):
        """Eski iddianın neden fail-open olduğunun kaydı."""
        ters = 'but the trend is monotonic'
        assert 'monoton' in ters          # eski iddia GEÇERDİ
        olumlu, _ = d16.monotonluk_iddialari(ters)
        assert olumlu                     # yeni iddia GEÇMEZ

    def test_bilinmeyen_baglam_OLUMLU_sayilir_fail_closed(self):
        olumlu, olumsuz = d16.monotonluk_iddialari('monotonluk gözlendi')
        assert olumlu and not olumsuz


# ===========================================================================
# OH-D23-12 — rota tarayıcısı literal-kör değil
# ===========================================================================
class TestOHD2312RotaCikarimi:

    @staticmethod
    def _ilk_cagri(kaynak):
        agac = ast.parse(kaynak)
        for d in ast.walk(agac):
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
                return d
        raise AssertionError('çağrı bulunamadı')

    def test_statik_onek_dort_bicimden_de_cikarilir(self):
        ornekler = {
            "client.post(f'/api/x/{m}', json={})": '/api/x/',
            "client.post('/api/x/' + m, json={})": '/api/x/',
            "client.post('/api/x/%s' % m, json={})": '/api/x/',
            "client.post('/api/x/{}'.format(m), json={})": '/api/x/',
        }
        for kaynak, beklenen in ornekler.items():
            cagri = self._ilk_cagri(kaynak)
            assert d18._statik_onek(cagri.args[0]) == beklenen, kaynak

    def test_somut_yol_flask_kuralina_eslenir(self):
        rotalar = {'/api/export-pdf/<report_type>', '/api/export-pdf',
                   '/api/exportx'}
        assert d18._rotaya_cevir('/api/export-pdf/summary', rotalar) == {
            '/api/export-pdf/<report_type>'}

    def test_onek_gelisiguzel_yutmaz(self):
        """``/api/export-`` öneki ``/api/export-stl-zip``i EŞLEŞTİRMEZ."""
        rotalar = {'/api/export-stl-zip', '/api/export-pdf/<report_type>'}
        assert d18._rotaya_cevir('/api/export-', rotalar) == set()

    def test_parametrize_listesinden_rota_cozulur(self):
        kaynak = (
            "import pytest\n"
            "@pytest.mark.parametrize('yol', ['/api/a', '/api/b'])\n"
            "def test_x(client, yol):\n"
            "    client.post(yol, json={})\n")
        agac = ast.parse(kaynak)
        _, kapsamlar = d18._fonksiyon_kapsamlari(agac)
        cagri = [d for d in ast.walk(agac)
                 if isinstance(d, ast.Call)
                 and isinstance(d.func, ast.Attribute)
                 and d.func.attr == 'post'][0]
        kapsam = kapsamlar[id(cagri)]
        assert kapsam['yol'] == {'/api/a', '/api/b'}

    def test_sozluk_get_cagrisi_rota_sayilmaz(self):
        """``hf.get(k, '')`` HTTP çağrısı değildir; kör-nokta sayımını
        şişirirse tavan anlamsızlaşır."""
        cagri = self._ilk_cagri("hf.get(k, '')")
        assert not d18._istemci_cagrisi_mi(cagri)

    def test_istemci_cagrisi_taninir(self):
        for kaynak in ("client.post(yol, json={})",
                       "self.c.get(yol)",
                       "s.post(yol, headers=H)"):
            assert d18._istemci_cagrisi_mi(self._ilk_cagri(kaynak)), kaynak

    def test_cozulemeyen_cagri_tavani_asilmadi(self):
        """Kör nokta BÜYÜYEMEZ (ÖK-22 yönünde sıkılaştırma)."""
        kalanlar = d18._cozulemeyen_rota_cagrilari()
        assert len(kalanlar) <= d18.COZULEMEYEN_ROTA_CAGRISI_TAVANI, (
            'çözülemeyen rota çağrısı arttı (%d > %d); ya çözücü genişletilir '
            'ya çağrı literal yazılır: %s'
            % (len(kalanlar), d18.COZULEMEYEN_ROTA_CAGRISI_TAVANI,
               kalanlar[:12]))

    def test_tavan_olculen_sayiyla_hizali(self):
        """Tavan ölçümün ÜSTÜNDE bırakılırsa sessiz af olur."""
        kalanlar = d18._cozulemeyen_rota_cagrilari()
        assert d18.COZULEMEYEN_ROTA_CAGRISI_TAVANI - len(kalanlar) <= 5, (
            'tavan ölçümden çok yüksek: %d ölçüldü, tavan %d'
            % (len(kalanlar), d18.COZULEMEYEN_ROTA_CAGRISI_TAVANI))

    def test_degiskenle_cagrilan_uc_artik_gorunuyor(self):
        """Ölçülen kazanç: literal-kör tarayıcının kaçırdığı gerçek uçlar."""
        rotalar = d18._app_rotalari()
        test = d18._testin_cagirdiklari(rotalar)
        for yol in ('/export_liquid_cad', '/export_solid_motor_cad'):
            assert yol in test, (
                '%s testte çağrılıyor ama tarayıcı görmüyor' % yol)

    def test_alias_kardesler_birlikte_sayilir(self):
        takimlar = d18._rota_takimlari()
        assert any({'/api/combustion-stability',
                    '/api/analysis/combustion-stability'} <= t
                   for t in takimlar), (
            'aynı görünüm fonksiyonunun iki rotası takım sayılmıyor')


# ===========================================================================
# OH-D23-11 — bayat metin / kanıt hijyeni demeti (dört yarı)
# ===========================================================================
_RELEASE_TEST = os.path.join(KOK, 'tests', 'test_release_notes_language.py')
_BLOWDOWN_JS = os.path.join(KOK, 'hrma', 'static', 'js', 'blowdown_panel.js')
_D18_RAPOR = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D18',
                          'kati', 'a1', 'rapor.md')
_D18_OLCUM = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D18',
                          'kati', 'a1', 'sonra.json')


def _metin(yol):
    return io.open(yol, encoding='utf-8').read()


class TestOHD2311BayatMetinDemeti:

    def test_a_kunye_olmayan_bir_kapiyi_anlatmaz(self):
        """Künye 'atlanıyor' derse ORTADA BİR KAPI OLMALI.

        Ölçülen kusur: künye "yama gelene kadar skip" diyordu, kapı ÖH D18
        ile kaldırılmıştı. Bayat künye, sınanan bir sözleşmeyi sınanmıyor
        gibi gösterir.
        """
        from hrma.utils import update_checker
        agac = ast.parse(_metin(_RELEASE_TEST))
        kunye = (ast.get_docstring(agac) or '').lower()
        yama_var = hasattr(update_checker, 'split_notes_by_language')
        vaat = ('o güne kadar skip' in kunye
                or 'o gune kadar skip' in kunye)
        assert not (vaat and yama_var), (
            'künye "yama gelene kadar atlanır" diyor ama yama ZATEN '
            'uygulanmış (split_notes_by_language var): bölüm atlanmıyor, '
            'sözleşme sınanıyor — künye bayat')
        # İkinci yarı: vaat varsa gerçekten bir kapı da olmalı.
        kapili = [d.name for d in agac.body
                  if isinstance(d, ast.FunctionDef)
                  and any('skipif' in ast.dump(s) or 'node_gerekir'
                          in ast.dump(s) for s in d.decorator_list)]
        assert not (vaat and not kapili), (
            'künye atlama vaat ediyor ama hiçbir kapı yok: %s' % kapili)

    def test_b_modul_duzeyi_node_kapisi_yok(self):
        """Node kapısı SAF-PYTHON sözleşmesini yutmamalı.

        Modül düzeyi ``pytestmark`` node yoksa dosyadaki her şeyi
        atlıyordu — P13B1-09'un 'yama geri alınamaz' bekçisi dâhil.
        Node kurulu olmayan bir makinede sunucu yaması sessizce geri
        alınabilirdi.
        """
        metin = _metin(_RELEASE_TEST)
        assert 'pytestmark = pytest.mark.skipif' not in metin, (
            'modül düzeyi skipif geri geldi: node yoksa saf-Python '
            'sözleşme testleri de atlanır (fail-open)')

    @pytest.mark.parametrize('ad', [
        'test_yayin_notu_iki_dilli_kaynak_olarak_okunabiliyor',
        'test_sunucu_dil_ayirma_yamasi_geri_alinamaz',
        'test_sunucu_dil_bolumlerini_ayri_gonderir',
        'test_gercek_surum_notu_sinira_sigar',
        'test_kirpma_satir_sinirinda_ve_beyanli',
    ])
    def test_b_saf_python_testleri_kapisiz(self, ad):
        """Bu beş test node ÇALIŞTIRMAZ; her makinede koşmalı."""
        agac = ast.parse(_metin(_RELEASE_TEST))
        bulunan = [d for d in agac.body
                   if isinstance(d, ast.FunctionDef) and d.name == ad]
        assert bulunan, '%s kayboldu' % ad
        suslemeler = ast.dump(ast.Module(body=bulunan[0].decorator_list,
                                         type_ignores=[]))
        assert 'skipif' not in suslemeler and 'node_gerekir' not in suslemeler, (
            '%s node kapısına alınmış ama node çalıştırmıyor' % ad)

    def test_c_js_yorumu_geri_cekilmis_atfi_sabitlemez(self):
        """``blowdown_panel.js`` künyeyi ikinci kez yazmamalı.

        Ürün künyeyi ``CHUG_THRESHOLD_CITATION`` tek kaynağından alır ve o
        kaynak SP-8089 atfını AÇIKÇA geri çeker. Yorumun eski atfı sabit
        yazması, bayatlayacak ikinci bir künye kopyasıdır.
        """
        assert 'chugging risk (SP-8089)' not in _metin(_BLOWDOWN_JS), (
            'blowdown_panel.js geri çekilmiş SP-8089 atfını yeniden '
            'sabitliyor')

    def test_d_rapordaki_sayilar_olcumle_celiskisiz(self):
        """Kanıt hijyeni: raporun aktardığı sayı ölçüm dosyasını tutmalı."""
        import json
        import re
        olcum = json.load(io.open(kanit_gerekli(_D18_OLCUM), encoding='utf-8'))
        beklenen = {k: v['total_kg']
                    for k, v in olcum['P2B4-04']['yogunluk'].items()}
        m = re.search(r'([\d,]+) / ([\d,]+) / ([\d,]+) kg', _metin(kanit_gerekli(_D18_RAPOR)))
        assert m, 'raporun yoğunluk satırı bulunamadı'
        for yazili, anahtar in zip(m.groups(), ('200.0', '1200.0', '3000.0')):
            sayi = float(yazili.replace(',', '.'))
            assert abs(sayi - beklenen[anahtar]) < 5e-4, (
                'rapor %s kg yazıyor, ölçüm %.6f kg (yoğunluk %s)'
                % (yazili, beklenen[anahtar], anahtar))


# ===========================================================================
# OH-D23-22 — i18n anahtarı BLOK İÇİNE yazılır; bekçi kesiti de blok kadar
# ===========================================================================
class TestOHD2322I18nBlokKesiti:
    """Dalga briefinin "electron/sivi anahtarı dosya SONUNA blok olarak
    eklenebilir" istisnası, bekçinin kesitiyle çelişiyordu: EN kesiti
    ``tr: {`` işaretinde bitiyor (sona eklenen anahtar EN'de görünmez),
    TR kesiti dosya sonuna kadar gidiyor (sözlük kapandıktan SONRA yazılan,
    tarayıcıya HİÇ ulaşmayan anahtarı 'çevirisi var' sayıyor)."""

    def test_blok_disinda_anahtar_yok(self):
        import tests.test_engine_warning_i18n as i18n
        disarida = i18n._blok_disi_anahtarlar()
        assert not disarida, (
            'i18n_common.js içinde en/tr bloklarının DIŞINDA warn.* '
            'anahtarı var; oraya yazılan anahtar ya yanlış dile düşer ya '
            'hiç yüklenmez: %s' % disarida)

    def test_sona_eklenen_anahtar_TR_sayilmaz(self):
        """Kesit sözleşmesi: TR bloğu sözlük nesnesiyle BİTER.

        Eski dilim (``js[tr_start:]``) dosya sonuna kadar gidiyordu ve
        ``I18N.register`` çağrısından sonra yazılan bir anahtarı TR
        çevirisi sayıyordu — ölçüldü (once_ohd23_22.json).
        """
        import tests.test_engine_warning_i18n as i18n
        js, (en_ara, _), (tr_ara, _) = i18n._blok_araliklari()
        assert tr_ara[1] < len(js), 'TR bloğu dosya sonuna kadar gidiyor'
        kuyruk = js[tr_ara[1]:]
        assert 'I18N.register' in kuyruk or 'register(' in kuyruk, (
            'TR bloğunun kapanışı yanlış yerde bulunmuş')
        assert not i18n.KEY_RE.findall(kuyruk), (
            'sözlük kapandıktan sonra warn.* anahtarı var (tarayıcıya '
            'ulaşmaz): %s' % i18n.KEY_RE.findall(kuyruk)[:5])

    def test_iki_dil_ayni_sayida_anahtar_tasir(self):
        """Blok kesiti doğruysa iki sözlük eşit büyüklükte olmalı."""
        import tests.test_engine_warning_i18n as i18n
        en, tr = i18n._dicts()
        assert len(en) == len(tr), (
            'EN %d, TR %d anahtar — kesit kaymış olabilir'
            % (len(en), len(tr)))
        assert len(en) >= 300, 'sözlük kesiti çöktü: %d' % len(en)

    def test_yer_tutucu_icindeki_susler_blogu_bitirmez(self):
        """``'{shown} / {total}'`` gibi metinler parantez sayımını bozmaz."""
        import tests.test_engine_warning_i18n as i18n
        _, (_, en_metin), (_, tr_metin) = i18n._blok_araliklari()
        assert '{shown}' in tr_metin or '{shown}' in en_metin, (
            'yer tutuculu satır kesitin içinde kalmadı')


# ===========================================================================
# OH-D23-01 — iddiasız test nüfusu (ilk dilim; nüfus SIFIRA indi)
# ===========================================================================
import tests.test_d22_bekci_cevirisi_a1 as d22  # noqa: E402


class TestOHD2301IddiasizNufus:
    """Kalemin başlığı 426 diyordu; o sayı D22 ölçütüyle (yalnız
    ``ast.Assert``) ölçülmüştü ve ölçüt kördü. ÖLÇÜLDÜ (once/sonra
    _ohd23_01.json): aynı ağaçta D22 ölçütü 430, D23 ölçütü 56, D24
    ölçütü (yardımcı delegasyonu çözülünce) 0."""

    def test_olcut_modul_ici_yardimciyi_cozer(self):
        kaynak = (
            'def _dogrula(x):\n'
            '    assert x > 0\n\n'
            'def test_x():\n'
            '    _dogrula(1)\n')
        agac = ast.parse(kaynak)
        tablo = d22._modul_fonksiyonlari(agac)
        test = [d for d in agac.body
                if isinstance(d, ast.FunctionDef) and d.name == 'test_x'][0]
        assert d22._iddia_tasiyor(test, tablo), (
            'iddiasını modül içi yardımcıya delege eden test iddiasız '
            'sayıldı')
        assert not d22._iddia_tasiyor(test, {}), (
            'tablo verilmeyince ölçüt yine de "iddia var" diyor — '
            'delegasyon kredisi kaynaksız veriliyor')

    def test_olcut_iddiasiz_yardimciyi_kredilendirmez(self):
        """Fail-closed: gövdesinde iddia OLMAYAN yardımcı kredi vermez."""
        kaynak = ('def _yaz(x):\n'
                  '    print(x)\n\n'
                  'def test_x():\n'
                  '    _yaz(1)\n')
        agac = ast.parse(kaynak)
        test = [d for d in agac.body
                if isinstance(d, ast.FunctionDef) and d.name == 'test_x'][0]
        assert not d22._iddia_tasiyor(test, d22._modul_fonksiyonlari(agac))

    def test_olcut_dongude_takilmaz(self):
        """Karşılıklı çağıran iki yardımcı sonsuz özyineleme yapmamalı."""
        kaynak = ('def _a(x):\n    return _b(x)\n\n'
                  'def _b(x):\n    return _a(x)\n\n'
                  'def test_x():\n    _a(1)\n')
        agac = ast.parse(kaynak)
        test = [d for d in agac.body
                if isinstance(d, ast.FunctionDef) and d.name == 'test_x'][0]
        assert not d22._iddia_tasiyor(test, d22._modul_fonksiyonlari(agac))

    def test_destek_modulu_yardimcilari_da_cozulur(self):
        """``tests/support`` içindeki ortak iddia çekirdeği görünmeli."""
        tablo = d22._destek_fonksiyonlari()
        assert 'json_capasi' in tablo, (
            'tests/support yardımcıları tabloya girmiyor')

    def test_iki_tavan_da_olculen_sayiyla_hizali(self):
        """Tavan ölçümün ÜSTÜNDE bırakılırsa sessiz af olur."""
        _, iddiasiz = d22._iddiasiz_test_nufusu()
        _, delegesiz = d22._iddiasiz_test_nufusu(delegasyon=False)
        assert d22.IDDIASIZ_NUFUS_TAVANI == 0, (
            'iddiasız nüfus tavanı sıfırdan yükseltilmiş: %d'
            % d22.IDDIASIZ_NUFUS_TAVANI)
        assert len(iddiasiz) == 0, sorted(iddiasiz)[:10]
        assert d22.IDDIASIZ_DELEGESIZ_TAVANI - len(delegesiz) <= 3, (
            'delegesiz tavan ölçümden yüksek: %d ölçüldü, tavan %d'
            % (len(delegesiz), d22.IDDIASIZ_DELEGESIZ_TAVANI))

    def test_dogrulama_bayraklari_iddiaya_bagli(self):
        """test_solid_rocket_validation artık 'passed'i SINIYOR."""
        yol = os.path.join(KOK, 'tests', 'test_solid_rocket_validation.py')
        metin = _metin(yol)
        assert metin.count('_bayraklari_dogrula(') >= 5, (
            'doğrulama bayrakları yine yalnız ekrana basılıyor')


# ===========================================================================
# P15B3-10 — sarsım matrisi üç ucun ötesine geçer (kalan yarı)
# ===========================================================================
#
# Kalemin ölçülen hâli: ``shake`` kampanyanın en verimli aracı ama tests/
# ağacında ``shake.run(...)`` YALNIZ ``/calculate`` üstünde koşuyordu (D23
# ölçümü). Engelin kökü tek bir eksiklikti — her uç için GEÇERLİ taban yük —
# ve o katalog D23'te (P10B4-16) birleşti. Bu aşamada matris FİİLEN koştu:
# ÖLÇÜLDÜ (sonra_p15b3_10.json) — katalogdaki 66 ölçülebilir ucun 66'sında
# sarsım matrisi hatasız koştu, toplam 380,6 sn, 14 ölü girdi bulundu.
#
# Bekçinin bütçesi: 380 sn bir test süiti için fazladır. Bölme SESSİZ
# DEĞİLDİR — ağır uçlar ADIYLA ve ÖLÇÜLEN SÜRESİYLE aşağıda durur, sayıları
# kilitlidir (büyümesi = kapsamın sessizce daralması).

#: ÖLÇÜLEN süresi 3 sn'yi aşan uçlar (sonra_p15b3_10.json). Bekçi bunları
#: her koşumda sarsmaz; kapsam BEYANI olarak adıyla durur ve liste
#: BÜYÜYEMEZ. Ölçüm aracı (``tools/wiring_map.measure_endpoint``) hepsini
#: koşabilir ve kampanya ölçümlerinde koştu.
AGIR_UCLAR = {
    '/api/correlation-report': 140.8,
    '/parametric-analysis': 43.0,
    '/api/transient-analysis': 42.7,
    '/api/uncertainty-analysis': 42.4,
    '/calculate': 28.9,
    '/api/quick-geometry': 22.9,
    '/calculate_liquid': 16.4,
    '/api/fea/planar-grain': 9.3,
    '/api/solid-monte-carlo': 8.1,
    '/api/find-optimum-of': 6.8,
    '/api/advanced-performance-analysis': 4.6,
    '/api/cfd/nozzle': 3.4,
}

#: ÖLÇÜLEN ölü girdiler (sarsıldığında çıktının HİÇBİR yaprağını
#: değiştirmeyen alanlar). Bu bir AF DEĞİL borç kaydıdır: liste
#: BÜYÜYEMEZ, yeni ölü girdi kırmızıdır. Küçülmesi beklenen yöndür.
#: Sahipleri kendi kulvarlarındadır (motor dosyaları), bu kulvar ölçer
#: ve kilitler.
#:
#: ÖH D26 fix-25a — ``/api/analysis/wall-profile`` satırından ``burn_time``
#: ve ``mdot_total`` DÜŞÜRÜLDÜ (4 -> 2; nüfus 14 -> 12, küçülme yönü).
#: DİKKAT: bu alanlar "canlı oldu" diye düşmedi — ölçüm aksini söylüyor.
#: Sarsıldıklarında değişen TEK yaprak kendi yankılarıdır
#: (``.inputs_not_used[0].submitted`` / ``[1].submitted``), yani ``shake``
#: onları artık ``dead_inputs`` yerine ``echo_only_inputs`` sayıyor ve
#: envanter yalnız ``dead_inputs``a bakıyordu. Sebep D25 app-api a4 /
#: P16B3-18: uç, YUTTUĞU girdiyi ARTIK ADIYLA İLAN EDİYOR
#: (``inputs_not_used``). Borç kaybolmadı, TEST tarafı defterden ÜRÜN
#: beyanına taşındı ve orada kendi ölçümlü bekçileri var
#: (``tests/test_d25_app_api_a4.py::TestP16B318YutulanGirdi``: beyanın
#: gerekçesi ``burn_time`` 1/10/300 için wall_profile'ın BİT-AYNI kaldığı
#: ölçülerek sınanıyor; ``mdot_total`` yalnız boğaz verildiğinde yutuluyor,
#: boğazsız hâlde ETKİLİ olduğu için beyan edilmiyor). Fail-closed korunur:
#: beyan sökülür de alanlar sessiz ölüye dönerse ``yeni`` kapısı kırmızı
#: verir.
OLU_GIRDI_ENVANTERI = {
    '/analyze_structural_safety': ('burn_time',),
    '/api/analysis/wall-profile': ('chamber_length', 'expansion_ratio'),
    # ``BOGUS_KEY`` katalog yükünün KASITLI sahte alanı (uç bilinmeyen
    # anahtarı yutuyor mu diye konmuş); ölü olması DOĞRU davranıştır.
    '/api/gimbal-mount': ('BOGUS_KEY',),
    '/api/solid-monte-carlo': ('chamber_diameter', 'core_diameter',
                               'expansion_ratio', 'grain_length',
                               'n_samples'),
    '/calculate': ('hole_diameter_max', 'hole_diameter_min'),
    '/calculate_liquid': ('stoichiometric_of',),
}


def _hafif_uclar():
    from tests.support import uc_katalogu
    return [y for y in uc_katalogu.olculebilir_uclar()
            if y not in AGIR_UCLAR]


class TestP15B310SarsimKapsami:

    @pytest.fixture(scope='class')
    def istemci(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    def test_katalog_ucun_otesine_gecti(self):
        """Kalemin ölçtüğü hâl: 75 POST ucundan 3-4'ü sarsılıyordu."""
        from tests.support import uc_katalogu
        olculebilir = uc_katalogu.olculebilir_uclar()
        # Adıyla kaldırılan uçlar (küme ölçüsü; SAYI değişmez): ölü takma yol
        # /api/analysis/thermal-protection D30 app-api-uc a1'de silindi (OH-D29-13 +
        # P7B1-22, 0dd609b7); kardeşi /api/thermal-protection katalogda kalır.
        ADLI_KALDIRILAN = {'/api/analysis/thermal-protection': 'OH-D29-13 (D30 uc a1 0dd609b7)'}
        assert not (set(ADLI_KALDIRILAN) & set(olculebilir)), 'kaldırıldı denen uç katalogda duruyor'
        assert '/api/thermal-protection' in olculebilir, 'kardeş uç katalogdan düştü'
        assert len(olculebilir) + len(ADLI_KALDIRILAN) >= 66, (
            'katalog daraldı: %d ölçülebilir uç (+%d adlı kaldırılan)' % (len(olculebilir), len(ADLI_KALDIRILAN)))
        # Silinen takma yol hafif uçtu; adlı kaldırılan kümesiyle birlikte sayılır (SAYI düşürülmez).
        assert len(_hafif_uclar()) + len(ADLI_KALDIRILAN) >= 54, (
            'bekçinin her koşumda sarstığı uç sayısı düştü: %d (+%d adlı kaldırılan)'
            % (len(_hafif_uclar()), len(ADLI_KALDIRILAN)))

    def test_agir_uc_listesi_buyumez(self):
        """Ağır uç listesi kapsamın DIŞINDA kalanların beyanıdır.

        Büyümesi, bekçinin sessizce daha az uç sarsması demektir.
        """
        from tests.support import uc_katalogu
        katalog = set(uc_katalogu.olculebilir_uclar())
        assert len(AGIR_UCLAR) <= 12, (
            'ağır uç listesi büyüdü: %d' % len(AGIR_UCLAR))
        yabanci = sorted(set(AGIR_UCLAR) - katalog)
        assert not yabanci, (
            'ağır uç listesi katalogda olmayan uç taşıyor (bayat): %s'
            % yabanci)

    @pytest.mark.parametrize('yol', _hafif_uclar())
    def test_ucun_sarsim_matrisi_kosuyor(self, istemci, yol):
        """Her hafif uçta matris koşar ve ÖLÜ GİRDİ envanteri aşılmaz."""
        import contextlib
        from tools import wiring_map
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            rapor = wiring_map.measure_endpoint(istemci, yol)
        beklenen = set(OLU_GIRDI_ENVANTERI.get(yol, ()))
        yeni = sorted(set(rapor.dead_inputs) - beklenen)
        assert not yeni, (
            '%s: YENİ ölü girdi (kullanıcı değeri giriyor, sonuca hiç '
            'girmiyor): %s' % (yol, yeni))
        olu_a = sorted(beklenen - set(rapor.dead_inputs))
        assert not olu_a, (
            '%s: ölü girdi envanteri ölü satır taşıyor (bu alanlar artık '
            'canlı, listeden çıkarın): %s' % (yol, olu_a))

    def test_olu_girdi_envanteri_bayat_uc_tasimaz(self):
        from tests.support import uc_katalogu
        katalog = set(uc_katalogu.olculebilir_uclar())
        yabanci = sorted(set(OLU_GIRDI_ENVANTERI) - katalog)
        assert not yabanci, (
            'ölü girdi envanteri katalogda olmayan uç taşıyor: %s' % yabanci)
        toplam = sum(len(v) for v in OLU_GIRDI_ENVANTERI.values())
        assert toplam <= 14, 'ölü girdi nüfusu büyüdü: %d' % toplam
