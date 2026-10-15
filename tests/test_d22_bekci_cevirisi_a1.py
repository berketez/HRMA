"""ÖH Dalga-22 · kulvar **bekci-cevirisi**, aşama 1 — onarımların bekçileri.

Bu dosyadaki her sınıf, D22'de onarılan bir defter kalemini TERS-MUTASYONLA
kanıtlanmış biçimde kilitler: onarım geçici olarak geri alındığında ilgili
test KIRMIZI olur (kanıt ``docs/scofield/raw/OH/D22/bekci-cevirisi/a1/
mutasyon.json``), geri konduğunda YEŞİL.

Kulvarın sahası **bekçilerin kendisidir**: ürün davranışı doğruysa test
çevrilir, ürün yanlışsa kalem "engelli" bırakılır. Bu yüzden aşağıdaki
iddiaların çoğu ÜRÜN çıktısını değil, BEKÇİNİN BİÇİMİNİ sınar — çünkü
onarılan şey bekçinin kendisidir.

Kalemler:

* **P13B3-10** — ``repr(nan) == repr(nan)`` bit-özdeşlik iddiasında
  FAIL-OPEN'dı; sonluluk kapısı yoktu.
* **P13B3-12** — ``repr`` basamak ÖN KOŞULU, ürün kaynağında yuvarlarsa
  (istenen davranış) kırmızıya dönüyordu; eşik üç yerde elden yazılıydı.
* **P13B3-13** — deponun tek bıçak-sırtı bekçisi: belgede GEÇMEYEN dört
  basamaklı bir literal ±5e-5 ile kilitli, bandın %95,21'i tüketilmiş.
* **P13B2-05** — statik "NASA CEA Connected" rozeti ŞART koşuluyordu;
  kardeş şablonlarda D21'de onarılan kusuru kilitliyordu.
* **P13B2-06** — "yedek dili İngilizce" tasarım kararı üç dosyaya
  kopyalanmıştı ve yasak yalnız birinde koşuyordu.
* **P13B1-10** — sekiz "toplanan" testin yedisinde hiç ``assert`` yoktu.
* **P13B2-10 / P13B3-11** — envanter kalemleri: nüfus TAVANI (büyümeye
  karşı fail-closed), gevşetilemez.
* **P10B4-05** — ``wiring_map`` "temiz" rozeti YALNIZ girdi düzeyine
  bakıyordu; kampanyanın baskın kusur sınıfı (girdi canlı, ÖNEMLİ yaprak
  ölü) kapsam dışıydı.
"""
from __future__ import annotations

import ast
import json
import math
import pathlib
import re
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
TESTS = KOK / 'tests'


def _oku(bagil: str) -> str:
    return (KOK / bagil).read_text(encoding='utf-8')


def _agac(bagil: str) -> ast.Module:
    return ast.parse(_oku(bagil))


def _fonksiyonu_bul(agac: ast.AST, ad: str):
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and d.name == ad:
            return d
    return None


# ===========================================================================
# P13B3-10 — NaN köşesinde fail-open kapatıldı
# ===========================================================================
AKUSTIK_GOC = 'tests/test_sivi_akustik_gocu.py'


class TestP13B310NaNKosesi:
    """``repr(x) == repr(y)`` bit-özdeşlik iddiası NaN'da geçerdi."""

    def test_kusurun_kendisi_hala_gecerli(self):
        """Sınıfın var olma sebebi: dilin bu davranışı değişmedi."""
        assert repr(float('nan')) == repr(float('nan'))
        assert not (float('nan') == float('nan'))       # noqa: PLR0124
        assert repr(float('inf')) == repr(float('inf'))

    def test_her_repr_esitligi_sonluluk_kapisiyla_korunuyor(self):
        """Her ``repr(a) == repr(b)`` iddiası bir sonluluk kapısının ardında.

        TERS MUTASYON: ``math.isfinite`` döngüsü silinirse bu test kırmızı
        olur — yani kapının varlığı mekanik olarak kilitli.
        """
        agac = _agac(AKUSTIK_GOC)
        repr_satirlari = set()
        for dugum in ast.walk(agac):
            if not (isinstance(dugum, ast.Compare) and len(dugum.ops) == 1
                    and isinstance(dugum.ops[0], ast.Eq)):
                continue
            taraflar = [dugum.left] + list(dugum.comparators)
            if all(isinstance(t, ast.Call) and isinstance(t.func, ast.Name)
                   and t.func.id == 'repr' for t in taraflar):
                repr_satirlari.add(dugum.lineno)
        assert repr_satirlari, (
            'dosyada hiç repr-eşitliği kalmamış: bekçi VAKUMLUK — '
            'iddia taşındıysa bu sınıf da taşınmalı')
        kapisiz = set(repr_satirlari)
        for fn in ast.walk(agac):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            icerdigi = {d.lineno for d in ast.walk(fn)
                        if isinstance(d, ast.Compare)}
            ortak = icerdigi & repr_satirlari
            if not ortak:
                continue
            govde = ast.dump(fn)
            if 'isfinite' in govde or 'isnan' in govde:
                kapisiz -= ortak
        assert not kapisiz, (
            'sonluluk kapısı olmayan repr-eşitliği satır(lar)ı: %s '
            '(NaN köşesinde FAIL-OPEN)' % sorted(kapisiz))


# ===========================================================================
# P13B3-12 — ön koşul artık bir DÜZELTMEyi kırmızıya çevirmiyor
# ===========================================================================
F2B_SIVI = 'tests/test_faz6_f2b_sivi.py'


class TestP13B312OnKosulYonu:

    def test_esik_tek_kaynakta_ve_desen_ondan_tureniyor(self):
        kaynak = _oku(F2B_SIVI)
        assert re.search(r'^KUNYE_ONDALIK_ESIGI\s*=\s*7\s*$', kaynak, re.M), \
            'künye ondalık eşiği tek kaynakta tanımlı değil'
        assert re.search(
            r"^HAM_FLOAT_DESENI\s*=\s*r'\\d\+\\\.\\d\{%d,\}'\s*%\s*"
            r'KUNYE_ONDALIK_ESIGI', kaynak, re.M), \
            'tarama deseni eşikten türemiyor'
        elden = re.findall(r"re\.findall\(r'\\d\+\\\.\\d\{\d+,\}'", kaynak)
        assert not elden, 'elden yazılı tarama eşiği geri gelmiş: %s' % elden
        assert kaynak.count('HAM_FLOAT_DESENI') >= 4, (
            'desen üç taramada da kullanılmıyor')

    def test_onkosul_yuvarlanmis_degeri_kirmiziya_cevirmiyor(self):
        """Ürün kaynağında yuvarlarsa ön koşul GEÇER, ama sessiz geçmez."""
        sys.path.insert(0, str(KOK))
        import tests.test_faz6_f2b_sivi as mod           # noqa: PLC0415
        # (a) Kaynakta yuvarlanmış (kısa) değer: kabul, kırmızı YOK.
        assert mod._kaynak_degeri_saglikli('kisa', 3707.0) is False
        # (b) Uzun değer: kusur ön koşulu canlı.
        assert mod._kaynak_degeri_saglikli('uzun', 3706.9482716354) is True
        # (c) FAIL-CLOSED yön: silinmiş / sonsuz değer sızamaz.
        for kotu in (0.0, float('nan'), float('inf')):
            with pytest.raises(AssertionError):
                mod._kaynak_degeri_saglikli('kotu', kotu)

    def test_eski_ters_yonlu_onkosul_geri_gelmedi(self):
        """AST ile taranır: belge metni değil, KOŞAN iddia sınanır."""
        kotu = []
        for dugum in ast.walk(_agac(F2B_SIVI)):
            if not isinstance(dugum, ast.Assert):
                continue
            for alt in ast.walk(dugum.test):
                if not (isinstance(alt, ast.Compare) and len(alt.ops) == 1
                        and isinstance(alt.ops[0], ast.GtE)):
                    continue
                sag = alt.comparators[0]
                if not (isinstance(sag, ast.Constant) and sag.value == 10):
                    continue
                if 'repr' in ast.dump(alt.left):
                    kotu.append(dugum.lineno)
        assert not kotu, (
            'ters yönlü (>=10) repr ön koşulu geri gelmiş, satır(lar): %s'
            % kotu)


# ===========================================================================
# P13B3-13 — bant sağlığı: bıçak sırtı kalmadı
# ===========================================================================
KARARLILIK = 'tests/test_stability_cekirdek.py'
#: Bir ``abs`` bandının tüketilebileceği en yüksek pay. Üstü "bıçak sırtı"
#: sayılır: fiziksel olarak önemsiz bir kayma bekçiyi kırmızıya çevirir ve
#: kırmızı, bir fizik regresyonuyla karışır.
BANT_KULLANIM_TAVANI_YUZDE = 90.0


def _modul_sabitleri(agac: ast.Module):
    ortam = {}
    for dugum in agac.body:
        if (isinstance(dugum, ast.Assign) and len(dugum.targets) == 1
                and isinstance(dugum.targets[0], ast.Name)):
            try:
                ortam[dugum.targets[0].id] = ast.literal_eval(dugum.value)
            except (ValueError, TypeError, SyntaxError):
                pass
    return ortam


def _sayi(dugum, ortam):
    """Literal ya da modül düzeyi adlandırılmış sabit → sayı (yoksa None)."""
    if isinstance(dugum, ast.Constant) and isinstance(
            dugum.value, (int, float)) and not isinstance(dugum.value, bool):
        return float(dugum.value)
    if isinstance(dugum, ast.Name) and isinstance(
            ortam.get(dugum.id), (int, float)):
        return float(ortam[dugum.id])
    return None


def _abs_bantli_iddialar(bagil: str):
    agac = _agac(bagil)
    ortam = _modul_sabitleri(agac)
    for dugum in ast.walk(agac):
        if not (isinstance(dugum, ast.Call)
                and isinstance(dugum.func, ast.Attribute)
                and dugum.func.attr == 'approx' and dugum.args):
            continue
        for kw in dugum.keywords:
            if kw.arg != 'abs':
                continue
            bant = _sayi(kw.value, ortam)
            beklenen = _sayi(dugum.args[0], ortam)
            if bant is None or beklenen is None or bant <= 0:
                continue
            yield dugum.lineno, beklenen, bant


class TestP13B313BicakSirti:

    def test_belge_capasi_belgenin_kendi_basamaginda(self):
        from hrma.stability.chug import chug_neutral_tau_ratio
        import tests.test_stability_cekirdek as mod     # noqa: PLC0415
        gercek = chug_neutral_tau_ratio(0.2)
        kullanim = (abs(gercek - mod.DOC_NEUTRAL_RATIO_BELGE)
                    / mod.DOC_NEUTRAL_RATIO_YUVARLAMA)
        assert kullanim * 100.0 < BANT_KULLANIM_TAVANI_YUZDE, (
            'belge çapasının bant kullanımı %%%.2f — bıçak sırtı'
            % (kullanim * 100.0))
        # Çapa belgenin BASTIĞI sayıya bağlı olmalı (0,865), belgede hiç
        # geçmeyen dört basamaklı literale (0,8652) değil.
        assert mod.DOC_NEUTRAL_RATIO_BELGE == 0.865
        assert round(mod.DOC_NEUTRAL_RATIO, 3) == mod.DOC_NEUTRAL_RATIO_BELGE

    def test_dosyada_bicak_sirti_iddia_kalmadi(self):
        """Ölçülebilen her ``abs`` bandının payı tavanın altında.

        TERS MUTASYON: eski ``pytest.approx(0.8652, abs=5e-5)`` satırı geri
        konursa bu test kırmızı olur (ölçülen pay %95,21).
        """
        from hrma.stability.chug import chug_neutral_tau_ratio
        from hrma.stability.chamber import chamber_time_constant
        tau_c = chamber_time_constant(1.0, 1800.0, 1.2)['tau_c_s']
        oran = chug_neutral_tau_ratio(0.2)
        adaylar = (oran, tau_c * 1e3, oran * tau_c * 1e3, oran * tau_c)
        bicak = []
        olculen = 0
        for satir, beklenen, bant in _abs_bantli_iddialar(KARARLILIK):
            eslesen = [v for v in adaylar if abs(v - beklenen) <= 10 * bant]
            if not eslesen:
                continue
            olculen += 1
            pay = 100.0 * abs(eslesen[0] - beklenen) / bant
            if pay > BANT_KULLANIM_TAVANI_YUZDE:
                bicak.append((satir, beklenen, bant, round(pay, 2)))
        assert olculen >= 3, 'bant ölçümü hiçbir iddiaya bağlanamadı'
        assert not bicak, 'bıçak sırtı iddia(lar): %s' % bicak

    def test_belgede_gecmeyen_literal_geri_gelmedi(self):
        """0,8652 belgede HİÇ geçmiyor; hiçbir iddia ona bağlanamaz.

        Tarama AST üstünde yapılır — belge/yorum metninde sayının anılması
        (bu onarımın gerekçesi orada yazılı) yanlış kırmızı vermez.
        """
        for bagil in (KARARLILIK, 'tests/test_api_combustion_stability.py'):
            agac = _agac(bagil)
            ortam = _modul_sabitleri(agac)
            kotu = []
            for dugum in ast.walk(agac):
                if not (isinstance(dugum, ast.Call)
                        and isinstance(dugum.func, ast.Attribute)
                        and dugum.func.attr == 'approx' and dugum.args):
                    continue
                deger = _sayi(dugum.args[0], ortam)
                if deger is not None and abs(deger - 0.8652) < 1e-12:
                    kotu.append(dugum.lineno)
            assert not kotu, (
                '%s: belgede geçmeyen dört basamaklı çapa geri gelmiş, '
                'satır(lar): %s' % (bagil, kotu))


# ===========================================================================
# P13B2-05 — rozet kilidi çözüldü, borç ilan edildi
# ===========================================================================
LIQUID_SOZLESME = 'tests/test_liquid_page_contract.py'
#: Statik "önceden bağlandı" rozeti TAŞIMASINA bugün izin verilen şablonlar.
#: Bu bir MUAFİYET DEĞİL, bir BORÇ KAYDIDIR: küme yalnız KÜÇÜLEBİLİR.
#: hrma/templates/liquid.html ÖH D22'de sivi + arayuz kulvarlarının
#: sahasındadır; bu kulvar ürün şablonuna dokunmaz (kardeş dal ölçümü).
ROZET_BORCU = {'hrma/templates/liquid.html'}
ROZET_SABLONLARI_TARANAN = (
    'hrma/templates/liquid.html', 'hrma/templates/solid.html',
    'hrma/templates/advanced.html', 'hrma/templates/hybrid.html')


class TestP13B205RozetKilidi:

    def test_sozlesme_bekcisi_artik_yesil_rozeti_sart_kosmuyor(self):
        """TERS MUTASYON: eski satır geri konursa bu test kırmızı olur."""
        kaynak = _oku(LIQUID_SOZLESME)
        yasak = re.findall(
            r"assert\s+'class=\"database-status status-connected [^']*'"
            r"\s+in\s+html", kaynak)
        assert not yasak, (
            'sözleşme bekçisi hâlâ hiçbir denetim koşmadan YEŞİL rozeti '
            'ŞART koşuyor: %s' % yasak)
        assert 'ROZET_SINIF_METNI' in kaynak, (
            'kilit kaldırıldı ama yerine sınıf ⟷ metin tutarlılığı konmamış')

    def test_borc_kumesi_yalniz_kuculuyor(self):
        """Yeni bir şablon önceden yeşil rozet kazanamaz (fail-closed).

        Borçlu şablon ONARILIRSA küme küçülür ve bu test YEŞİL kalır —
        bekçi bir düzeltmeyi asla kırmızıya çevirmez.
        """
        bugun = set()
        for bagil in ROZET_SABLONLARI_TARANAN:
            yol = KOK / bagil
            if not yol.exists():
                continue
            govde = yol.read_text(encoding='utf-8')
            if re.search(r'<span class="database-status[^"]*status-connected',
                         govde):
                bugun.add(bagil)
        yeni = bugun - ROZET_BORCU
        assert not yeni, (
            'ilk boyada YEŞİL rozet taşıyan YENİ şablon(lar): %s '
            '(P17B2-07 kusuru geri gelmiş)' % sorted(yeni))

    def test_sinif_metin_tutarliligi_gercekten_kosuyor(self):
        """Sözleşme bekçisinin yeni iddiası ürün üstünde ölçülür."""
        html = (KOK / 'hrma/templates/liquid.html').read_text(encoding='utf-8')
        rozetler = re.findall(
            r'<span class="database-status ([^"]*)"[^>]*>([^<]*)</span>', html)
        assert rozetler, 'liquid.html rozet biçimi değişmiş'
        for siniflar, metin in rozetler:
            if 'status-connected' in siniflar:
                assert 'Connected' in metin, (siniflar, metin)
            elif 'status-unknown' in siniflar:
                assert 'not checked' in metin, (siniflar, metin)


# ===========================================================================
# P13B2-06 — yedek dili kararı tek kaynakta, kapsam simetrik
# ===========================================================================
#: ÖH D22'de ölçülen yedek nüfusu: bug_report 21 + settings_panel 10 +
#: blowdown_panel 18. Yasak artık üçünde de koşuyor (önce yalnız 21).
YEDEK_KAPSAM_TABANI = 49


class TestP13B206YedekDili:

    def test_karar_tek_kaynakta(self):
        from tests.support import yedek_dili         # noqa: PLC0415
        assert yedek_dili.YEDEK_DILI == 'en'
        # Kopyalanmış Türkçe-harf deseni kalmamalı: kural tek yerde.
        for bagil in ('tests/test_bug_report.py',
                      'tests/test_blowdown_panel.py'):
            kaynak = _oku(bagil)
            assert 'yedek_dili' in kaynak, bagil
            assert not re.search(r"re\.search\(r'\[çğıöşüÇĞİÖŞÜ\]'", kaynak), \
                '%s: Türkçe-harf deseni yeniden kopyalanmış' % bagil

    def test_yasak_uc_dosyada_da_kosuyor(self):
        from tests.support import yedek_dili         # noqa: PLC0415
        toplam = 0
        for bagil, onek in (
                ('hrma/static/js/bug_report.js', 'shell.bug.'),
                ('hrma/static/js/settings_panel.js', 'shell.bug.'),
                ('hrma/static/js/blowdown_panel.js', '')):
            ciftler = yedek_dili.yedekler(_oku(bagil), onek)
            assert ciftler, bagil
            toplam += len(ciftler)
            assert not yedek_dili.dil_kacaklari(ciftler), bagil
        assert toplam >= YEDEK_KAPSAM_TABANI, (
            'yasağın kapsadığı yedek nüfusu düştü: %d < %d'
            % (toplam, YEDEK_KAPSAM_TABANI))

    def test_blowdown_bekcisinin_adi_govdesiyle_ortusuyor(self):
        """Adı "İngilizce yedeği var" diyen test dili GERÇEKTEN sınıyor."""
        agac = _agac('tests/test_blowdown_panel.py')
        fn = _fonksiyonu_bul(agac, 'test_her_t_cagrisinin_ingilizce_yedegi_var')
        assert fn is not None
        govde = ast.dump(fn)
        assert 'dil_kacaklari' in govde, (
            'ad dil denetimi ilan ediyor ama gövde yalnız varlığa bakıyor')


# ===========================================================================
# P13B1-10 — sekiz "toplanan" testin iddiası
# ===========================================================================
#: P13 envanterinin ``assertsiz.json`` dosyasından gelen sekiz kalem.
#: Sekizincisi (``forbid_verdict_key``) ölçümde ÇÜRÜTÜLDÜ: iddiasını bir
#: yardımcıya delege ediyor, gövdesinde ``assert`` yok ama iddiası VAR.
IDDIA_YARDIMCILARI = ('forbid_verdict_key', 'json_capasi')
ASSERTSIZ_SEKIZ = (
    ('tests/test_api_combustion_stability.py',
     'test_damping_yaniti_tamamen_hukumsuz'),
    ('tests/test_hibrit_baglama_a5a8a2.py',
     'test_yeni_bloklar_json_serilestirilebilir'),
    ('tests/test_hibrit_beyan_a10.py', 'test_sonuc_json_serilestirilebilir'),
    ('tests/test_hibrit_of_kaymasi_a9.py',
     'test_yeni_alanlar_json_serilestirilebilir'),
    ('tests/test_nozzle_flow_1d.py', 'test_output_is_json_serializable'),
    ('tests/test_projects_store.py', 'test_under_limit_accepted'),
    ('tests/test_stl_cleanup_safety.py', 'test_hedefler_ayristirilabilir'),
    ('tests/test_tank_blowdown_baglama.py',
     'test_blok_json_serilestirilebilir'),
)


class TestP13B110IddiasizTestler:

    @pytest.mark.parametrize('bagil,ad', ASSERTSIZ_SEKIZ)
    def test_her_biri_bir_iddia_tasiyor(self, bagil, ad):
        fn = _fonksiyonu_bul(_agac(bagil), ad)
        assert fn is not None, '%s::%s kayboldu' % (bagil, ad)
        assertler = [d for d in ast.walk(fn) if isinstance(d, ast.Assert)]
        yardimci = [d.func for d in ast.walk(fn)
                    if isinstance(d, ast.Call)
                    and ((isinstance(d.func, ast.Name)
                          and d.func.id in IDDIA_YARDIMCILARI)
                         or (isinstance(d.func, ast.Attribute)
                             and d.func.attr in IDDIA_YARDIMCILARI))]
        assert assertler or yardimci, (
            '%s::%s hâlâ iddiasız (ne assert ne iddia yardımcısı)'
            % (bagil, ad))

    def test_ortak_serilestirme_capasi_fail_closed(self):
        """``json_capasi`` boş gövdeyi, None bloğu ve NaN'ı REDDEDER."""
        from tests.support import serilestirme       # noqa: PLC0415
        with pytest.raises(AssertionError):
            serilestirme.json_capasi({}, 'boş')
        with pytest.raises(AssertionError):
            serilestirme.json_capasi({'a': None}, 'None blok')
        with pytest.raises(ValueError):
            serilestirme.json_capasi({'a': float('nan')}, 'NaN')
        with pytest.raises(ValueError):
            serilestirme.json_capasi({'a': float('inf')}, 'Inf')
        # Sağlıklı gövde geçer ve gidiş–dönüşü sınanır.
        assert serilestirme.json_capasi({'a': [1, 2.5], 'b': 'x'}, 'iyi')


# ===========================================================================
# P13B2-10 — iddiasız test NÜFUSU tavanı (envanter kalemi, ÖK-22)
# ===========================================================================
#: ÖH D22 tabanı: 11.180 test fonksiyonunun 426'sında hiç ``assert`` yoktu
#: (%3,81). Bu kulvarın onarımından sonra 419. Tavan TABAN değeridir:
#: nüfus bu sayının üstüne çıkamaz. Gevşetmek (tavanı yükseltmek) bir
#: karardır ve gerekçesiyle yazılır — ÖK-22.
#:
#: ÖH D23 (bekci-cevirisi a1) — ÖLÇÜT DÜZELTİLDİ, tavan 426 -> 62.
#: D22 raporu bu ölçütün kör noktasını KENDİ BULMUŞTU (P13B1-10'un
#: sekizinci kalemi çürütülürken): gövdesinde ``assert`` olmayan ama
#: iddiasını ``pytest.raises`` / ``pytest.warns`` bağlamına ya da bir
#: yardımcıya (``forbid_verdict_key``) DELEGE eden test "iddiasız"
#: sayılıyordu. Sayım bu yüzden şişikti ve ef527ae tabanında tavanı
#: 1 birim aşmıştı (427 > 426) — envanter kendi ölçüt hatasından
#: kırmızıydı. Ölçüt gerçek iddia biçimlerini tanıyor; tavan yeni
#: ÖLÇÜLEN sayıya çekildi. Bu bir GEVŞETME DEĞİL daraltmadır: eski
#: ölçütle "iddiasız" sayılan 365 test artık iddialı sayılıyor
#: (ÖLÇÜLDÜ: 427 -> 62) ve tavan 364 birim DÜŞTÜ. Örneklem denetlendi
#: (6/6 doğru): ``pytest.raises`` bağlamları ve ``forbid_verdict_key``
#: delegasyonu. Kalan 62 GERÇEK iddiasız testtir.
IDDIASIZ_NUFUS_TAVANI = 0
#: ÖH D24 (bekci-cevirisi a1, OH-D23-01) — 62 -> 0. İki iş yapıldı:
#:
#: 1. ÖLÇÜT dördüncü iddia biçimini öğrendi: iddianın modül içi ya da
#:    ``tests/support`` içindeki bir YARDIMCIYA delege edilmesi. Ad
#:    ölçütü ('assert' geçiyor mu) bunu göremiyordu; ölçülen yardımcılar
#:    ``eslik_iddiasi``, ``_kontur_dogrula``, ``_sayfa_dogrula``,
#:    ``serilestirme.json_capasi`` — dördü de gerçek iddia taşıyor.
#:    Çağrılan ad tabloda varsa GÖVDESİ taranır (en fazla 3 kademe).
#: 2. Geriye kalan 9 test GERÇEKTEN iddiasızdı ve iddia KAZANDI:
#:    test_solid_rocket_validation'ın dört doğrulaması ``passed``
#:    bayrağını üretip EKRANA BASIYOR, hiç sınamıyordu ("✗ FAIL" yazan
#:    gerileme yeşil kalıyordu); JSON turları ``dumps``ı iddia sanıyordu;
#:    kapı testleri "patlamadı"yı iddia sanıyordu.
#:
#: Tavan artık SIFIRDIR: yeni bir iddiasız test EKLENEMEZ.

#: İKİNCİ, DAHA KATI KAPI (ÖH D24). Yukarıdaki sayı yardımcı çözümünün
#: kredisini içerir; o kredi bir gün fazla cömert olursa büyüme burada
#: SAKLANABİLİRDİ. Bu tavan delegasyon kredisi OLMADAN sayar (D23
#: ölçütü) ve ölçülen sayıya çekilmiştir: gövdesinde doğrudan iddia
#: olmayan test nüfusu da büyüyemez.
#:
#: ÖH D25 (bekci-cevirisi a1, OH-D24-04) — 56 -> 51. İki iş yapıldı:
#:
#: 1. ENVANTER YANLIŞ POZİTİFİ: 4 kalem pytest'in hiç TOPLAMADIĞI
#:    fonksiyondu (``SolidRocketValidationTest`` sınıfının metotları;
#:    sınıf adı ``Test`` ile başlamıyor). ``_pytest_topluyor`` bunları
#:    fail-closed elemektedir; nüfus 12618 -> 12614.
#: 2. GERÇEK DELİK: ``tests/test_d20_ihracat_a1.py::
#:    test_etkin_oksitleyicilerin_HEPSI_cozulur`` iddia kredisini KURULUM
#:    yardımcısından alıyordu ve (i) boş listede vakumlu, (ii) künyesiz /
#:    ``None`` yoğunlukta yeşil kalıyordu. İddia kazandı.
#:
#: ÖLÇÜLDÜ (D25 tabanı cdf2106): kalan 51'in HİÇBİRİ iddiasız değildir —
#: 51'i de gerçek iddia taşıyan bir yardımcıya delege ediyor ve 48'i
#: yardımcıya testin KENDİ ürettiği değeri veriyor (kanıt
#: docs/scofield/raw/OH/D25/bekci-cevirisi/a1/once_kredi_kaynagi.json).
#: Kalan 3 "kurulum kredisi" kalemi tests/test_d25_bekci_cevirisi_a1.py
#: içindeki daha keskin kapıda ADIYLA ve GEREKÇESİYLE listelenir.
#: ÖH D30 (bekci-cevirisi a1, OH-D29-12) — SAYI TAVANI KÜME ÖLÇÜSÜNE
#: ÇEVRİLDİ. fix-28a ölçümü kusuru adıyla koymuştu: tavan 51'e YAPIŞIKTI
#: (ölçülen 51, tavan 51, pay 0), yani depoya eklenecek İLK delegesiz test
#: bu kapıyı kırıyordu — ama kapı yalnız SAYI sayıyordu. Sayı kapısının iki
#: deliği ÖLÇÜLDÜ:
#:
#: 1. TAKAS KÖRLÜĞÜ: bir delegesiz test silinip yerine başkası eklenirse
#:    sayı 51'de kalır ve kapı YEŞİL geçer — yeni, denetlenmemiş test
#:    sessizce içeri girer. Küme ölçüsü bunu ADIYLA söyler.
#: 2. ENVANTER HÜKÜMSÜZLÜĞÜ: 51 kalem hiçbir yerde adlandırılmamıştı;
#:    "tavan aşıldı" diyen ileti yalnız ilk 10 adı basıyordu. Hangi testin
#:    neden kredili sayıldığı hükme bağlı DEĞİLDİ.
#:
#: Aşağıdaki envanter 51 kalemin TAMAMINI adıyla ve GEREKÇESİYLE bağlar.
#: Gerekçeler uydurulmadı, ÖLÇÜLDÜ: her kalemin kredisini veren yardımcı
#: AST ile bulundu ve o yardımcının taşıdığı iddia sayıldı (kanıt
#: docs/scofield/raw/OH/D30/bekci-cevirisi/a1/once_kredi_ailesi.json).
#: ÖLÇÜLDÜ: 51 kalemin 51'inde kredi kaynağı bulundu (kredisiz kalem 0),
#: 19 kaynak ailesi; hepsi gerçek iddia taşır ve krediyi testin KENDİ
#: ürettiği değerden alır; ikisi (``_agac_manifesti`` ve manifold çapı
#: kardeş çağrısı) D25'in KURULUM_KREDISI_IZINLERI listesinde ayrıca
#: gerekçelidir.
#:
#: ANAHTAR NİTELİKLİDİR (``dosya::Sınıf::ad``). Eski ``dosya::ad`` biçimi
#: ÖLÇÜLEN bir belirsizlik taşıyordu: ``tests/fea/
#: test_yapisal_vaka_dogrulama.py`` içinde ``TestVakaLameSI`` ve
#: ``TestVakaAnsysVM25`` sınıfları üç test adını PAYLAŞIYOR (7 kalem,
#: 4 benzersiz ad). Nitelenmemiş anahtarla tek satır iki ayrı testi
#: "kapsıyor" görünürdü ve biri silinse bayatlık kapısı susardı.
DELEGESIZ_ENVANTERI = {
    'tests/cfd/test_eksen.py::test_eksen_sagligi_izantropik':
        '_kontrol (3 iddia) eksen aynasının sağlığını ölçer — komşu '
        'parazit radyal hız, eksen basınç düzlüğü, radyal tek-çift '
        'salınım; krediyi testin KENDİ koşturduğu çözüm alanı verir',
    'tests/cfd/test_eksen.py::test_eksen_sagligi_soklu':
        '_kontrol (3 iddia) eksen aynasının sağlığını ölçer — komşu '
        'parazit radyal hız, eksen basınç düzlüğü, radyal tek-çift '
        'salınım; krediyi testin KENDİ koşturduğu çözüm alanı verir',
    'tests/cfd/test_euler_bit_ozdesligi.py::'
    'test_bugunku_kosum_referansla_bit_ozdes':
        '_alan_karsilastir (3) ve _skaler_karsilastir (4) bugünkü '
        'koşumu referansla bit düzeyinde karşılaştırır; krediyi '
        'testin KENDİ ürettiği koşum verir, referans diskten okunur',
    'tests/fea/test_bridge.py::test_basinci_eksik_motor_red':
        '_red_dogrula (4 iddia) reddin dört ayağını ölçer — status '
        'not_modelled, missing eksiği adlandırıyor, redli sonuçta '
        'çözüm alanı sızmıyor, warn.fea. önekli kod; krediyi testin '
        'kendi sonucu verir',
    'tests/fea/test_bridge.py::test_bilinmeyen_malzeme_red':
        '_red_dogrula (4 iddia) reddin dört ayağını ölçer — status '
        'not_modelled, missing eksiği adlandırıyor, redli sonuçta '
        'çözüm alanı sızmıyor, warn.fea. önekli kod; krediyi testin '
        'kendi sonucu verir',
    'tests/fea/test_bridge.py::test_konturu_eksik_motor_red':
        '_red_dogrula (4 iddia) reddin dört ayağını ölçer — status '
        'not_modelled, missing eksiği adlandırıyor, redli sonuçta '
        'çözüm alanı sızmıyor, warn.fea. önekli kod; krediyi testin '
        'kendi sonucu verir',
    'tests/fea/test_bridge.py::test_yapisal_blogu_eksik_motor_red':
        '_red_dogrula (4 iddia) reddin dört ayağını ölçer — status '
        'not_modelled, missing eksiği adlandırıyor, redli sonuçta '
        'çözüm alanı sızmıyor, warn.fea. önekli kod; krediyi testin '
        'kendi sonucu verir',
    'tests/fea/test_yapisal_vaka_dogrulama.py::TestVakaAnsysVM25::'
    'test_cember_gerilme_profili':
        '_check_profile beklenen (yarıçap → değer) sözlüğünü testin '
        'KENDİ çözdüğü FE profiliyle bağıl toleransta karşılaştırır; '
        'iddia döngü içindedir, her yarıçap anahtarı için ayrı '
        'kırılır',
    'tests/fea/test_yapisal_vaka_dogrulama.py::TestVakaAnsysVM25::'
    'test_radyal_gerilme_profili':
        '_check_profile beklenen (yarıçap → değer) sözlüğünü testin '
        'KENDİ çözdüğü FE profiliyle bağıl toleransta karşılaştırır; '
        'iddia döngü içindedir, her yarıçap anahtarı için ayrı '
        'kırılır',
    'tests/fea/test_yapisal_vaka_dogrulama.py::TestVakaAnsysVM25::'
    'test_radyal_yer_degistirme':
        '_check_profile beklenen (yarıçap → değer) sözlüğünü testin '
        'KENDİ çözdüğü FE profiliyle bağıl toleransta karşılaştırır; '
        'iddia döngü içindedir, her yarıçap anahtarı için ayrı '
        'kırılır',
    'tests/fea/test_yapisal_vaka_dogrulama.py::TestVakaLameSI::'
    'test_cember_gerilme_profili':
        '_check_profile beklenen (yarıçap → değer) sözlüğünü testin '
        'KENDİ çözdüğü FE profiliyle bağıl toleransta karşılaştırır; '
        'iddia döngü içindedir, her yarıçap anahtarı için ayrı '
        'kırılır',
    'tests/fea/test_yapisal_vaka_dogrulama.py::TestVakaLameSI::'
    'test_radyal_gerilme_profili':
        '_check_profile beklenen (yarıçap → değer) sözlüğünü testin '
        'KENDİ çözdüğü FE profiliyle bağıl toleransta karşılaştırır; '
        'iddia döngü içindedir, her yarıçap anahtarı için ayrı '
        'kırılır',
    'tests/fea/test_yapisal_vaka_dogrulama.py::TestVakaLameSI::'
    'test_radyal_yer_degistirme':
        '_check_profile beklenen (yarıçap → değer) sözlüğünü testin '
        'KENDİ çözdüğü FE profiliyle bağıl toleransta karşılaştırır; '
        'iddia döngü içindedir, her yarıçap anahtarı için ayrı '
        'kırılır',
    'tests/fea/test_yapisal_vaka_dogrulama.py::TestVakaLameSI::'
    'test_von_mises_ic_yuzey':
        '_check_profile beklenen (yarıçap → değer) sözlüğünü testin '
        'KENDİ çözdüğü FE profiliyle bağıl toleransta karşılaştırır; '
        'iddia döngü içindedir, her yarıçap anahtarı için ayrı '
        'kırılır',
    'tests/test_cfd_alan_koprusu.py::TestMetrikKimlikleri::'
    'test_guverte_sembolleri_sahneyle_ayni':
        'kume_esitligi iki kümenin eşitliğini fazla/eksik '
        'listeleyerek ölçer; krediyi testin KENDİ çıkardığı '
        'panel/güverte/sahne kümeleri verir',
    'tests/test_cfd_alan_koprusu.py::TestMetrikKimlikleri::'
    'test_panel_kimlikleri_sahneyle_ayni':
        'kume_esitligi iki kümenin eşitliğini fazla/eksik '
        'listeleyerek ölçer; krediyi testin KENDİ çıkardığı '
        'panel/güverte/sahne kümeleri verir',
    'tests/test_cfd_alan_koprusu.py::TestRedKodlari::'
    'test_guverte_kod_kumesi_sahneyle_ayni':
        'kume_esitligi iki kümenin eşitliğini fazla/eksik '
        'listeleyerek ölçer; krediyi testin KENDİ çıkardığı '
        'panel/güverte/sahne kümeleri verir',
    'tests/test_cfd_alan_koprusu.py::TestRedKodlari::'
    'test_panel_kod_kumesi_sahneyle_ayni':
        'kume_esitligi iki kümenin eşitliğini fazla/eksik '
        'listeleyerek ölçer; krediyi testin KENDİ çıkardığı '
        'panel/güverte/sahne kümeleri verir',
    'tests/test_cfd_alan_koprusu.py::TestRedKodlari::'
    'test_panel_ve_guverte_ayni_kumeyi_tutuyor':
        'kume_esitligi iki kümenin eşitliğini fazla/eksik '
        'listeleyerek ölçer; krediyi testin KENDİ çıkardığı '
        'panel/güverte/sahne kümeleri verir',
    'tests/test_cfd_alan_koprusu.py::TestYukAnahtarlari::'
    'test_panel_payload_anahtarlari_sahneyle_ayni':
        'payload_eslemesi_ayni id → payloadKey eşlemelerinin '
        'birebirliğini ölçer; krediyi testin KENDİ çıkardığı iki '
        'eşleme verir',
    'tests/test_cfd_alan_koprusu.py::TestYukAnahtarlari::'
    'test_ucun_butun_izgaralari_istemciye_bagli':
        'kume_esitligi iki kümenin eşitliğini fazla/eksik '
        'listeleyerek ölçer; krediyi testin KENDİ çıkardığı '
        'panel/güverte/sahne kümeleri verir',
    'tests/test_d21_app_api_a1.py::TestOHD1801UcBekcileri::'
    'test_firlatma_sahasi_sayfasi_acilir':
        '_sayfa_dogrula (3 iddia) sayfanın GERÇEKTEN açıldığını ölçer '
        '— 200, HTML gövdesi, 1000 bayttan uzun; boş 200 kabul '
        'edilmez, krediyi testin kendi isteği verir',
    'tests/test_d21_app_api_a1.py::TestOHD1801UcBekcileri::'
    'test_formuller_sayfasi_acilir':
        '_sayfa_dogrula (3 iddia) sayfanın GERÇEKTEN açıldığını ölçer '
        '— 200, HTML gövdesi, 1000 bayttan uzun; boş 200 kabul '
        'edilmez, krediyi testin kendi isteği verir',
    'tests/test_d21_app_api_a1.py::TestOHD1801UcBekcileri::'
    'test_hibrit_sayfasi_acilir':
        '_sayfa_dogrula (3 iddia) sayfanın GERÇEKTEN açıldığını ölçer '
        '— 200, HTML gövdesi, 1000 bayttan uzun; boş 200 kabul '
        'edilmez, krediyi testin kendi isteği verir',
    'tests/test_fazb_serilestirici_esligi.py::'
    'test_s1_korelasyon_hucresi_alan_esligi':
        'eslik_iddiasi izin sözleşmesini ve gerekçesiz düşen alan '
        'yasağını ZORLAR (2 iddia); krediyi testin KENDİ kurduğu iç '
        'nesne ile yayım gövdesi verir',
    'tests/test_fazb_serilestirici_esligi.py::'
    'test_s2_blowdown_adim_durumu_alan_esligi':
        'eslik_iddiasi izin sözleşmesini ve gerekçesiz düşen alan '
        'yasağını ZORLAR (2 iddia); krediyi testin KENDİ kurduğu iç '
        'nesne ile yayım gövdesi verir',
    'tests/test_fazb_serilestirici_esligi.py::'
    'test_s3_serilestirici_ic_nesneyi_tam_tasiyor':
        'eslik_iddiasi izin sözleşmesini ve gerekçesiz düşen alan '
        'yasağını ZORLAR (2 iddia); krediyi testin KENDİ kurduğu iç '
        'nesne ile yayım gövdesi verir',
    'tests/test_fazb_serilestirici_esligi.py::'
    'test_s4_band_serilestiricisi_ic_nesneyi_tam_tasiyor':
        'eslik_iddiasi izin sözleşmesini ve gerekçesiz düşen alan '
        'yasağını ZORLAR (2 iddia); krediyi testin KENDİ kurduğu iç '
        'nesne ile yayım gövdesi verir',
    'tests/test_fazb_serilestirici_esligi.py::test_s4_kose_satiri_alan_esligi':
        'eslik_iddiasi izin sözleşmesini ve gerekçesiz düşen alan '
        'yasağını ZORLAR (2 iddia); krediyi testin KENDİ kurduğu iç '
        'nesne ile yayım gövdesi verir',
    'tests/test_fazb_serilestirici_esligi.py::test_s4_mod_satiri_alan_esligi':
        'eslik_iddiasi izin sözleşmesini ve gerekçesiz düşen alan '
        'yasağını ZORLAR (2 iddia); krediyi testin KENDİ kurduğu iç '
        'nesne ile yayım gövdesi verir',
    'tests/test_fazb_serilestirici_esligi.py::'
    'test_s5_kayit_kunyesi_yayimlanan_govdede':
        'eslik_iddiasi izin sözleşmesini ve gerekçesiz düşen alan '
        'yasağını ZORLAR (2 iddia); krediyi testin KENDİ kurduğu iç '
        'nesne ile yayım gövdesi verir',
    'tests/test_hibrit_baglama_a5a8a2.py::'
    'test_yeni_bloklar_json_serilestirilebilir':
        'tests/support/serilestirme.json_capasi ortak iddia çekirdeği '
        '(5 iddia) gidiş-dönüş serileştirmeyi ölçer; krediyi testin '
        'KENDİ ürettiği blok verir',
    'tests/test_hibrit_beyan_a10.py::test_sonuc_json_serilestirilebilir':
        'tests/support/serilestirme.json_capasi ortak iddia çekirdeği '
        '(5 iddia) gidiş-dönüş serileştirmeyi ölçer; krediyi testin '
        'KENDİ ürettiği blok verir',
    'tests/test_hibrit_of_kaymasi_a9.py::'
    'test_yeni_alanlar_json_serilestirilebilir':
        'tests/support/serilestirme.json_capasi ortak iddia çekirdeği '
        '(5 iddia) gidiş-dönüş serileştirmeyi ölçer; krediyi testin '
        'KENDİ ürettiği blok verir',
    'tests/test_kati_ablatif_baglama.py::'
    'test_apcp_on_kapak_boyutlanmis_ve_blokaj_cozulmus':
        '_on_kapak_bekcisi (12 iddia) ön kapağın boyutlanmış ve '
        'blokajının çözülmüş olduğunu ölçer; TEK tanım noktasıdır ve '
        'aynı dosyadaki mutasyon testinin kurbanıdır (tautoloji '
        'değil)',
    'tests/test_motor_geometri_yayimi.py::TestLuleKonturuYayimi::'
    'test_hibrit_konturu':
        '_kontur_dogrula (15 iddia) şema, fiziksel tutarlılık ve '
        'orijin sözleşmesini ölçer; motor_viz3d.js '
        'selectNozzleContour RED kurallarının aynısıdır, krediyi '
        'testin kendi yanıtı verir',
    'tests/test_motor_geometri_yayimi.py::TestLuleKonturuYayimi::'
    'test_kati_konturu':
        '_kontur_dogrula (15 iddia) şema, fiziksel tutarlılık ve '
        'orijin sözleşmesini ölçer; motor_viz3d.js '
        'selectNozzleContour RED kurallarının aynısıdır, krediyi '
        'testin kendi yanıtı verir',
    'tests/test_motor_geometri_yayimi.py::TestLuleKonturuYayimi::'
    'test_sivi_konturu':
        '_kontur_dogrula (15 iddia) şema, fiziksel tutarlılık ve '
        'orijin sözleşmesini ölçer; motor_viz3d.js '
        'selectNozzleContour RED kurallarının aynısıdır, krediyi '
        'testin kendi yanıtı verir',
    'tests/test_nozzle_flow_1d.py::TestApiContract::'
    'test_output_is_json_serializable':
        'tests/support/serilestirme.json_capasi ortak iddia çekirdeği '
        '(5 iddia) gidiş-dönüş serileştirmeyi ölçer; krediyi testin '
        'KENDİ ürettiği blok verir',
    'tests/test_paket_cikti_manifesti.py::test_derlenmis_app_manifesti':
        'konu bir DEĞER değil DİSKTEKİ derleme ağacıdır; '
        '_agac_manifesti (4 iddia) sabit yolu alıp ağacı manifestle '
        'karşılaştırır, ağaç yoksa ADLI atlama yapar — D25 '
        'KURULUM_KREDISI_IZINLERI içinde gerekçeli',
    'tests/test_paket_cikti_manifesti.py::test_windows_payload_manifesti':
        'konu bir DEĞER değil DİSKTEKİ derleme ağacıdır; '
        '_agac_manifesti (4 iddia) sabit yolu alıp ağacı manifestle '
        'karşılaştırır, ağaç yoksa ADLI atlama yapar — D25 '
        'KURULUM_KREDISI_IZINLERI içinde gerekçeli',
    'tests/test_scofield_arayuz.py::'
    'test_iki_manifold_capi_celisiyorsa_ekranda_tek_deger_var':
        'iddia KARDEŞ TESTE devredilmiştir: arayüzün kaba kural '
        'değerini göstermediğini '
        'test_kaba_kural_manifold_capi_ekrana_cikmiyor sınar; bu '
        'test yalnız çelişkinin sürdüğünü ölçüp kardeşi çağırır — '
        'D25 KURULUM_KREDISI_IZINLERI içinde de gerekçeli',
    'tests/test_step_import.py::TestMotorAnalysis::'
    'test_suggestions_within_1pct':
        '_approx pytest.approx ile DIM_CHECK_REL_TOL bağıl '
        'toleransında ölçer; test beş boyut önerisini KENDİ '
        'sonucundan verir, her çağrı ayrı kırılır',
    'tests/test_tank_blowdown_baglama.py::test_blok_json_serilestirilebilir':
        'tests/support/serilestirme.json_capasi ortak iddia çekirdeği '
        '(5 iddia) gidiş-dönüş serileştirmeyi ölçer; krediyi testin '
        'KENDİ ürettiği blok verir',
    'tests/test_z5s_ham_500.py::TestHam500Envanteri::test_adli_4xx':
        '_sozlesme (6 iddia) 4xx sınıfı, alan adlı gövde ve Python iç '
        'metninin sızmadığını birden ölçer; krediyi testin kendi '
        'isteği verir',
    'tests/test_z5s_hukum_kanali.py::TestKardesKapiBirlesimi::'
    'test_iki_uc_da_AYNI_kumeyi_reddediyor':
        '_adli_ret reddin üç ayağını ölçer — 4xx sınıfı, makine-okur '
        'ALAN ADI, Python sızıntısının yokluğu; krediyi testin KENDİ '
        'gönderdiği gövde verir',
    'tests/test_z5s_kati_sivi_form.py::TestOgreticiBayragi::'
    'test_mantiksal_olmayan_deger_adli_ret_alir':
        '_adli_ret reddin üç ayağını ölçer — 4xx sınıfı, makine-okur '
        'ALAN ADI, Python sızıntısının yokluğu; krediyi testin KENDİ '
        'gönderdiği gövde verir',
    'tests/test_z5s_kati_sivi_form.py::TestSayiBenzeriDize::'
    'test_dize_adli_ret_alir_ham_python_sizmaz':
        '_adli_ret reddin üç ayağını ölçer — 4xx sınıfı, makine-okur '
        'ALAN ADI, Python sızıntısının yokluğu; krediyi testin KENDİ '
        'gönderdiği gövde verir',
    'tests/test_z5s_kati_sivi_form.py::TestUydurulanTasarimNoktasi::'
    'test_fizik_disi_hedef_adli_4xx_alir':
        '_adli_ret reddin üç ayağını ölçer — 4xx sınıfı, makine-okur '
        'ALAN ADI, Python sızıntısının yokluğu; krediyi testin KENDİ '
        'gönderdiği gövde verir',
    'tests/test_z5s_kati_sivi_form.py::TestYakitKimligiTipi::'
    'test_tipsiz_kimlik_adli_ret_alir':
        '_adli_ret reddin üç ayağını ölçer — 4xx sınıfı, makine-okur '
        'ALAN ADI, Python sızıntısının yokluğu; krediyi testin KENDİ '
        'gönderdiği gövde verir',
    'tests/test_z5s_kati_sivi_form.py::TestYutulanBool::'
    'test_sayisal_alan_bool_yutmaz':
        '_adli_ret reddin üç ayağını ölçer — 4xx sınıfı, makine-okur '
        'ALAN ADI, Python sızıntısının yokluğu; krediyi testin KENDİ '
        'gönderdiği gövde verir',
}
#: MUTLAK TAVAN — ÖK-22. Envanter bu sayının ÜSTÜNE çıkamaz: yeni bir
#: delegesiz teste yer açmak için önce bir kalem gerçek iddia kazanmalı.
#: D25'te ölçülen 51'dir, YÜKSELTİLMEZ (yalnız düşürülür).
DELEGESIZ_MUTLAK_TAVAN = 51
#: Sayı kapısı KALDIRILMADI, envanterden TÜRETİLDİ: elle yazılan bir sayı
#: artık yok, dolayısıyla "tavanı bir artır" diye sessiz gevşetme yolu da
#: yok. (D24'ün ``test_iki_tavan_da_olculen_sayiyla_hizali`` kapısı bu
#: değişkeni okumayı sürdürür.)
IDDIASIZ_DELEGESIZ_TAVANI = len(DELEGESIZ_ENVANTERI)

#: İddia sayılan çağrılar: adı ``assert`` içeren (unittest ``assertEqual``,
#: proje yardımcıları), ``forbid_``/``reject_`` ile başlayan yasak
#: yardımcıları ve ``pytest.raises``/``pytest.warns``/``pytest.fail``.
_IDDIA_CAGRISI = ('raises', 'warns', 'fail', 'deprecated_call')


_DESTEK_TABLOSU = {}


def _destek_fonksiyonlari():
    """``tests/support/*.py`` içindeki yardımcılar: ad -> düğüm (önbellekli).

    ÖH D24 / OH-D23-01: iddia yalnız MODÜL İÇİ yardımcıya değil, ortak
    destek modülüne de delege ediliyor — ölçülen örnek
    ``tests.support.serilestirme.json_capasi`` (gövdesinde 6 assert var,
    adında 'assert' yok). Bu tablo olmadan o testler "iddiasız"
    sayılıyordu.
    """
    if _DESTEK_TABLOSU:
        return _DESTEK_TABLOSU
    destek = TESTS / 'support'
    if destek.is_dir():
        for yol in sorted(destek.glob('*.py')):
            try:
                agac = ast.parse(yol.read_text(encoding='utf-8'))
            except SyntaxError:                      # pragma: no cover
                continue
            for d in ast.walk(agac):
                if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _DESTEK_TABLOSU.setdefault(d.name, d)
    return _DESTEK_TABLOSU


def _modul_fonksiyonlari(agac):
    """Modüldeki HER fonksiyon: ad -> düğüm (sınıf metotları dâhil).

    ÖH D24 / OH-D23-01: iddiasını modül içi bir YARDIMCIYA delege eden
    test, yardımcının adında 'assert' geçmiyorsa "iddiasız" sayılıyordu.
    Ölçülen örnekler: ``eslik_iddiasi``, ``_kontur_dogrula``,
    ``_sayfa_dogrula``. Bunlar gerçek iddia taşır; sayım kördü.
    """
    tablo = dict(_destek_fonksiyonlari())
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            tablo[d.name] = d
    return tablo


def _pytest_topluyor(agac, hedef) -> bool:
    """``hedef`` fonksiyonunu pytest GERÇEKTEN topluyor mu (FAIL-CLOSED).

    ÖH D25 · OH-D24-04 — envanterin ÖLÇÜLEN yanlış pozitifi: adı ``test_``
    ile başlayan her ``FunctionDef`` "test" sayılıyordu. pytest'in
    varsayılan ``python_classes = Test*`` kuralıyla, adı ``Test`` ile
    BAŞLAMAYAN bir sınıfın metodu toplanmaz. Depoda ölçülen örnek:
    ``tests/test_solid_rocket_validation.py`` içindeki
    ``SolidRocketValidationTest`` sınıfının dört ``test_*`` metodu
    (``pytest --collect-only`` o dosyada 6 test topluyor, bu dördü
    aralarında YOK; kanıt docs/scofield/raw/OH/D25/bekci-cevirisi/a1/
    collect_only_solid.txt). Bunlar "iddiasız test" değil, hiç test
    değildir; süiti çalıştıran doğrulama takımının iç metotlarıdır.

    FAIL-CLOSED: şüphede TOPLANIYOR denir. Modül düzeyi, adı ``Test`` ile
    başlayan sınıf, ``TestCase`` türevi (pytest unittest eklentisi ada
    bakmadan toplar) ve TABANI ÇÖZÜLEMEYEN sınıf hep sayılır. Yalnız
    "adı Test ile başlamıyor VE tabanı sade, TestCase değil" durumunda
    eleme yapılır.
    """
    for sinif in [x for x in ast.walk(agac) if isinstance(x, ast.ClassDef)]:
        if hedef not in sinif.body:
            continue
        if sinif.name.startswith('Test'):
            return True
        for taban in sinif.bases:
            ad = (taban.attr if isinstance(taban, ast.Attribute)
                  else getattr(taban, 'id', None))
            if ad is None or 'TestCase' in ad or ad.startswith('Test'):
                return True                  # çözülemedi ya da TestCase
        return False
    return True                              # modül düzeyi


def _sinif_haritasi(agac):
    """Fonksiyon düğümü -> gövdesinde taşındığı sınıfın adı (ÖH D30).

    OH-D29-12: ``dosya::ad`` anahtarı ÖLÇÜLEN bir belirsizlik taşıyor —
    ``tests/fea/test_yapisal_vaka_dogrulama.py`` içinde ``TestVakaLameSI``
    ve ``TestVakaAnsysVM25`` üç test adını paylaşıyor. Adlı envanterin
    anahtarı ancak sınıfla NİTELENİRSE tekil olur.
    """
    harita = {}
    for sinif in [x for x in ast.walk(agac) if isinstance(x, ast.ClassDef)]:
        for govde in sinif.body:
            harita[id(govde)] = sinif.name
    return harita


def _kredi_kaynaklari(dugum, tablo):
    """``dugum``a iddia kredisini VEREN yardımcıların adları (ölçülerek).

    ÖH D30 · OH-D29-12: envanter gerekçesinin DOLGU olmadığını mekanik
    sınamak için gerek. Gerekçe, kredinin geldiği yardımcıyı adıyla anmak
    zorundadır; anmıyorsa gerekçe o kalemi açıklamıyordur.
    """
    kaynak = []
    for x in ast.walk(dugum):
        if not isinstance(x, ast.Call):
            continue
        f = x.func
        ad = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')
        if not ad or ad in kaynak or ad not in tablo:
            continue
        if _iddia_tasiyor(tablo[ad], tablo):
            kaynak.append(ad)
    return kaynak


def _iddiasiz_test_nufusu(delegasyon=True, nitelikli=False):
    toplam = 0
    iddiasiz = []
    for yol in sorted(TESTS.rglob('test_*.py')):
        try:
            agac = ast.parse(yol.read_text(encoding='utf-8'))
        except SyntaxError:                          # pragma: no cover
            continue
        bagil = str(yol.relative_to(KOK))
        tablo = _modul_fonksiyonlari(agac) if delegasyon else {}
        harita = _sinif_haritasi(agac) if nitelikli else {}
        for d in ast.walk(agac):
            if not (isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and d.name.startswith('test_')):
                continue
            if not _pytest_topluyor(agac, d):
                continue
            toplam += 1
            if not _iddia_tasiyor(d, tablo):
                sinif = harita.get(id(d))
                iddiasiz.append('%s::%s%s' % (
                    bagil, (sinif + '::') if sinif else '', d.name))
    return toplam, iddiasiz


def _envanter_dugumu(anahtar):
    """``dosya::[Sınıf::]ad`` anahtarını (ağaç, tablo, düğüm)
    üçlüsüne çözer."""
    parcalar = anahtar.split('::')
    bagil, ad = parcalar[0], parcalar[-1]
    sinif = parcalar[1] if len(parcalar) == 3 else None
    agac = ast.parse((KOK / bagil).read_text(encoding='utf-8'))
    harita = _sinif_haritasi(agac)
    for d in ast.walk(agac):
        if not (isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))
                and d.name == ad):
            continue
        if harita.get(id(d)) == sinif:
            return agac, _modul_fonksiyonlari(agac), d
    return agac, _modul_fonksiyonlari(agac), None


def _iddia_tasiyor(dugum, tablo=None) -> bool:
    """Test gövdesi bir iddia taşıyor mu — ``ast.Assert``TEN FAZLASI.

    ÖH D23. Eski ölçüt yalnız ``ast.Assert`` arıyordu ve üç yaygın iddia
    biçimini göremiyordu:

    * ``with pytest.raises(ValueError): ...`` — bağlam yöneticisinin
      kendisi iddiadır (blok içinde ``assert`` OLMAMASI doğrudur),
    * ``pytest.warns`` / ``pytest.fail`` / ``pytest.deprecated_call``,
    * iddiayı bir yardımcıya delege eden testler
      (``forbid_verdict_key(...)``, ``assert_*(...)``, ``self.assertEqual``).

    D22 raporu üçüncüsünü ADIYLA bulmuştu (``test_damping_yaniti_tamamen_
    hukumsuz``) ve o kalemi çürütmüştü; ölçüt yine de düzeltilmemişti.
    """
    return _iddia_tasiyor_ic(dugum, tablo or {}, set())


def _iddia_tasiyor_ic(dugum, tablo, gorulen, derinlik=0):
    """``_iddia_tasiyor``ın özyinelemeli gövdesi.

    ÖH D24 / OH-D23-01 — DÖRDÜNCÜ İDDİA BİÇİMİ: iddianın modül içi bir
    yardımcıya DELEGE edilmesi. Ad ölçütü ('assert' geçiyor mu) yetmiyor;
    ölçülen yardımcı adları ``eslik_iddiasi``, ``_kontur_dogrula``,
    ``_sayfa_dogrula`` — hiçbirinde 'assert' yok ama üçü de gerçek iddia
    taşıyor. Çözüm tahmin DEĞİL çözümdür: çağrılan ad modülde tanımlıysa
    O FONKSİYONUN GÖVDESİ de taranır (en fazla 3 kademe; döngü koruması
    ``gorulen`` ile).

    Fail-closed kalır: modülde tanımlı OLMAYAN, adı da iddia gibi
    görünmeyen bir çağrı iddia sayılmaz.
    """
    for x in ast.walk(dugum):
        if isinstance(x, ast.Assert):
            return True
        if isinstance(x, ast.Call):
            f = x.func
            ad = f.attr if isinstance(f, ast.Attribute) else getattr(
                f, 'id', '')
            if not ad:
                continue
            kucuk = ad.lower()
            if 'assert' in kucuk:
                return True
            if kucuk.startswith(('forbid_', 'reject_', 'must_', 'expect_')):
                return True
            if ad in _IDDIA_CAGRISI and isinstance(f, ast.Attribute) and \
                    getattr(f.value, 'id', '') == 'pytest':
                return True
            if (derinlik < 3 and ad in tablo and ad not in gorulen):
                gorulen.add(ad)
                if _iddia_tasiyor_ic(tablo[ad], tablo, gorulen,
                                     derinlik + 1):
                    return True
    return False


class TestP13B210IddiasizNufus:

    def test_nufus_tavani_asilmadi(self):
        toplam, iddiasiz = _iddiasiz_test_nufusu()
        assert toplam > 10000, 'tarama çöktü, nüfus okunamadı: %d' % toplam
        assert len(iddiasiz) <= IDDIASIZ_NUFUS_TAVANI, (
            'hiç assert taşımayan test nüfusu tavanı aştı: %d > %d '
            '(ilk 10: %s)'
            % (len(iddiasiz), IDDIASIZ_NUFUS_TAVANI, sorted(iddiasiz)[:10]))

    def test_delegesiz_nufus_tavani_asilmadi(self):
        """ÖH D24: yardımcı KREDİSİ OLMADAN sayılan nüfus da büyüyemez.

        Delegasyon çözümü doğru ama cömert bir ölçüttür; tek kapı ona
        bağlı kalırsa, iddiasını yardımcıya taşıyan yeni testler nüfusu
        sessizce büyütebilir. Bu ikinci kapı gövdesinde DOĞRUDAN iddia
        olmayan testleri sayar.

        ÖH D30 · OH-D29-12: tavan artık elle yazılan bir sayı DEĞİL,
        ``DELEGESIZ_ENVANTERI``den türetilir. Sayı kapısı korundu ama
        asıl kapı aşağıdaki KÜME kapılarıdır.
        """
        toplam, delegesiz = _iddiasiz_test_nufusu(delegasyon=False)
        assert toplam > 10000, 'tarama çöktü: %d' % toplam
        assert len(delegesiz) <= IDDIASIZ_DELEGESIZ_TAVANI, (
            'gövdesinde doğrudan iddia olmayan test nüfusu tavanı aştı: '
            '%d > %d (ilk 10: %s)'
            % (len(delegesiz), IDDIASIZ_DELEGESIZ_TAVANI,
               sorted(delegesiz)[:10]))

    def test_delegesiz_envanterine_yeni_kalem_girmedi(self):
        """ÖH D30 · OH-D29-12 — KÜME kapısı: takas körlüğü kapandı.

        Sayı kapısı bir kalem çıkıp yerine başkası girdiğinde YEŞİL
        kalıyordu (51 - 1 + 1 = 51). Bu kapı yeni geleni ADIYLA söyler:
        envantere girmeyen hiçbir delegesiz test depoya giremez.
        """
        _, olculen = _iddiasiz_test_nufusu(delegasyon=False, nitelikli=True)
        yeni = sorted(set(olculen) - set(DELEGESIZ_ENVANTERI))
        assert not yeni, (
            'gövdesinde doğrudan iddia olmayan YENİ test(ler) envantere '
            'girmeden eklendi: %s — ya teste gerçek bir iddia koyun ya da '
            'DELEGESIZ_ENVANTERI içine kredisini veren yardımcıyı adlandıran '
            'bir gerekçeyle yazın (tavan %d, ÖK-22 gereği yükseltilemez)'
            % (yeni, DELEGESIZ_MUTLAK_TAVAN))

    def test_delegesiz_envanterinde_olu_satir_yok(self):
        """ÖK-22: iddia kazanan ya da silinen kalem envanterde kalamaz.

        Bayat satır, tavanın altında sahte pay biriktirir; o pay bir gün
        denetlenmemiş yeni bir teste yer açar.
        """
        _, olculen = _iddiasiz_test_nufusu(delegasyon=False, nitelikli=True)
        olu = sorted(set(DELEGESIZ_ENVANTERI) - set(olculen))
        assert not olu, (
            'envanter bayat: %s artık delegesiz değil (ya iddia kazandı ya '
            'silindi); satır(lar) envanterden düşülmeli — tavan böylece '
            'kendiliğinden iner' % olu)

    def test_delegesiz_envanteri_mutlak_tavani_asmadi(self):
        """ÖK-22 — SAYI YÜKSELTİLMEZ: envanter D25 ölçümünü aşamaz."""
        assert len(DELEGESIZ_ENVANTERI) <= DELEGESIZ_MUTLAK_TAVAN, (
            'delegesiz envanteri büyütülmüş: %d > %d — yeni kaleme yer '
            'açmak için önce bir kalem GERÇEK iddia kazanmalı'
            % (len(DELEGESIZ_ENVANTERI), DELEGESIZ_MUTLAK_TAVAN))

    def test_delegesiz_gerekceleri_kredi_kaynagini_adlandiriyor(self):
        """Gerekçe DOLGU olamaz: krediyi veren yardımcıyı ADIYLA anmalı.

        D25'in ``test_izin_gerekceleri_gercek`` kapısı yalnız UZUNLUK
        ölçüyordu; uzun ama konusuz bir cümle geçerdi. Bu kapı gerekçeyi
        ÖLÇÜLEN kredi kaynağıyla bağlar: metin, testin iddiasını gerçekten
        taşıyan yardımcılardan en az birinin adını içermek zorundadır.
        """
        hatalar = []
        for anahtar, gerekce in sorted(DELEGESIZ_ENVANTERI.items()):
            _, tablo, dugum = _envanter_dugumu(anahtar)
            if dugum is None:
                hatalar.append('%s: envanterdeki test bulunamadı' % anahtar)
                continue
            if len(gerekce) < 60:
                hatalar.append('%s: gerekçe çok kısa (%d)'
                               % (anahtar, len(gerekce)))
                continue
            kaynaklar = _kredi_kaynaklari(dugum, tablo)
            if not kaynaklar:
                hatalar.append('%s: kredi kaynağı ölçülemedi' % anahtar)
                continue
            if not any(ad in gerekce for ad in kaynaklar):
                hatalar.append(
                    '%s: gerekçe kredi kaynağını anmıyor (ölçülen: %s)'
                    % (anahtar, kaynaklar))
        assert not hatalar, (
            'delegesiz envanterinin gerekçeleri hükmü taşımıyor:\n  '
            + '\n  '.join(hatalar))


# ===========================================================================
# P13B3-11 — parmak izi künyelerinin YERELLİĞİ (envanter, KISMEN)
# ===========================================================================
PARMAK_IZI_ENVANTERI = 'docs/scofield/raw/P13/parmak_izi_kunye.json'
#: ÖH D22 ölçümü: 170 çapanın 136'sında (%80,0) iddianın SATIRINDA ya da
#: hemen üstünde künye yok. Bu bir TAVAN'dır: yerelsiz çapa sayısı
#: büyüyemez. Sayının SIFIRA indirilmesi 136 ayrı yerde belge yazmayı
#: gerektirir; bu aşamanın bütçesinde değildir (kalem "kısmen").
#:
#: ÖH D23 (bekci-cevirisi a1, kalemin kalan yarısı) — 136 -> 112,
#: YASTIK SİLİNDİ. D22 tavanı ÖLÇÜLEN sayının (125) 11 birim ÜSTÜNDEYDİ:
#: o yastık kadar çapa sessizce künyesizleşebilirdi ve tek yönlü tavan
#: bunu görmezdi. D23 ölçümü: kardeş dalgaların satır kaydırmasıyla 122,
#: bu aşamada test_slosh.py (7) ve test_water_hammer.py (3) çapalarına
#: yerel künye yazıldıktan sonra **112**. Tavan artık ölçülen sayının
#: KENDİSİDİR ve yastığı ayrıca ölçülür:
#: tests/test_d23_bekci_cevirisi_a1.py::TestP13B311KunyeYerelligiKalanYari.
YERELSIZ_KUNYE_TAVANI = 112


def _kunye_yerelligi():
    ham = json.loads(_oku(kanit_gerekli(PARMAK_IZI_ENVANTERI)))
    onbellek = {}
    yerelsiz, tasinmis = [], 0
    for k in ham:
        bagil = k['file']
        if bagil not in onbellek:
            yol = KOK / bagil
            onbellek[bagil] = (yol.read_text(encoding='utf-8').splitlines()
                               if yol.exists() else None)
        satirlar = onbellek[bagil]
        if satirlar is None:
            tasinmis += 1
            continue
        # Satır numarası yerine METİNLE bul: kardeş kulvarlar satır
        # kaydırırsa ölçüm kaymasın (ÖH D22 dersi).
        hedef = k['src_line'].strip()
        indisler = [i for i, s in enumerate(satirlar) if s.strip() == hedef]
        if not indisler:
            tasinmis += 1
            continue
        i = indisler[0]
        pencere = '\n'.join(satirlar[max(0, i - 2):i + 1])
        if not re.search(r'#\s*\S', pencere):
            yerelsiz.append('%s:%s' % (bagil, hedef[:60]))
    return len(ham), tasinmis, yerelsiz


class TestP13B311KunyeYerelligi:

    def test_yerelsiz_capa_sayisi_buyumuyor(self):
        toplam, tasinmis, yerelsiz = _kunye_yerelligi()
        assert toplam == 170, 'envanter değişmiş: %d' % toplam
        assert tasinmis < toplam // 2, (
            'çapaların yarısından çoğu yerinde bulunamadı (%d): ölçüm '
            'güvenilmez, envanter tazelenmeli' % tasinmis)
        assert len(yerelsiz) <= YERELSIZ_KUNYE_TAVANI, (
            'yerel künyesiz parmak izi çapası sayısı tavanı aştı: %d > %d'
            % (len(yerelsiz), YERELSIZ_KUNYE_TAVANI))


# ===========================================================================
# P10B4-05 — "temiz" rozetinin kapsamı hükmüyle eşleşiyor
# ===========================================================================
class _SahteRapor:
    """``wiring_map.build_index``in beklediği en küçük rapor yüzeyi.

    Girdi düzeyi TEMİZ (ölü/ölçülemeyen/beyan çürümesi yok) ama yaprak
    düzeyinde sınıflandırılmamış sabitler VAR — kampanyanın baskın kusur
    sınıfının ta kendisi.
    """

    def __init__(self, belirsiz_yaprak=5):
        self.constant_outputs = ['.motor.magic_%d' % i
                                 for i in range(belirsiz_yaprak)]
        self.baseline_leaves = {y: 3.14159 for y in self.constant_outputs}
        self.baseline_leaf_count = len(self.baseline_leaves)
        self.live_inputs = ['a', 'b']
        self.dead_inputs = []
        self.echo_only_inputs = []
        self.unmeasurable = []
        self.declared_but_live = []
        self.changed_paths = {'a': ['.motor.thrust_n']}
        self.secim_kapsami = {}
        self.kismen_olculdu = {}

    def summary(self):                               # pragma: no cover
        return 'sahte'


def _giris_sayfasi(rapor, erimeler=None):
    sys.path.insert(0, str(KOK / 'tools'))
    sys.path.insert(0, str(KOK))
    import wiring_map                                # noqa: PLC0415
    return wiring_map.build_index(
        [('hybrid', pathlib.Path('wiring_map_hybrid.html'), rapor)],
        '—', erimeler)


def _rozet(html_metni: str) -> str:
    m = re.search(r'<div class="badge">([^<]*)</div>', html_metni)
    assert m, 'rozet bulunamadı — giriş sayfası biçimi değişmiş'
    return m.group(1).strip()


class TestP10B405RozetKapsami:

    def test_yaprak_duzeyi_olculmemisken_temiz_denmez(self):
        """Erime ölçülmediyse "temiz" hükmü YAYIMLANMAZ (fail-closed).

        TERS MUTASYON: rozet koşulu eski hâline (``problems == 0``)
        döndürülürse bu test kırmızı olur.
        """
        rozet = _rozet(_giris_sayfasi(_SahteRapor(belirsiz_yaprak=0)))
        assert rozet != 'temiz', (
            'girdi düzeyi temiz + yaprak düzeyi ÖLÇÜLMEMİŞ iken rozet '
            '"temiz" diyor')
        assert 'ÖLÇÜLMEDİ' in rozet, rozet

    def test_siniflandirilmamis_yaprak_varken_temiz_denmez(self):
        erimeler = {'hybrid': {'olculdu': True, 'toplam': 5, 'eriyen': 0,
                               'kalan': 5, 'yuzde': 0.0, 'deneme': 1}}
        rozet = _rozet(_giris_sayfasi(_SahteRapor(belirsiz_yaprak=5),
                                      erimeler))
        assert rozet != 'temiz', (
            'girdi düzeyi temiz ama 5 sınıflandırılmamış yaprak varken '
            'rozet "temiz" diyor — kampanyanın baskın kusur sınıfı '
            'kapsam dışı kalmış')
        assert 'sınıflandırılmamış' in rozet, rozet

    def test_gercekten_temizken_temiz_diyebiliyor(self):
        """Aşırı kapanma ikizi: hüküm kazanıldıysa rozet yeşil olabilmeli."""
        erimeler = {'hybrid': {'olculdu': True, 'toplam': 0, 'eriyen': 0,
                               'kalan': 0, 'yuzde': 0.0, 'deneme': 1}}
        rozet = _rozet(_giris_sayfasi(_SahteRapor(belirsiz_yaprak=0),
                                      erimeler))
        assert rozet == 'temiz', rozet
