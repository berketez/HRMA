# -*- coding: utf-8 -*-
"""ÖH D32 — app-api-dogrulama a1 bekçileri.

Kapsanan kalemler:

* **P7B1-06** (D31 devri, ÖK-16): birim çıkarım tavanının UZUNLUK ayağı.
  ``motor_geometry.LENGTH_SI_MAX_M`` elle yazılı ``5.0`` idi ve doğrulayıcının
  kanonik ``chamber_length`` bandıyla (üst uç 20,0 m) çelişiyordu; çelişki
  bandı OLMAYAN ``nozzle_*`` boy alanlarında CANLIYDI (6 m'lik lüle 6 mm
  okunuyordu). Tavan artık kanondan türetiliyor.

Ölçüm: ``docs/scofield/raw/OH/D32/app-api-dogrulama/a1/once.json`` /
``sonra.json`` (aynı betik: ``olcum.py``).
"""
import ast
import os

import pytest

from hrma.export import motor_geometry as MG
from hrma.validation import motor_validation as MV

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GEOMETRI_KAYNAK = os.path.join(_KOK, 'hrma', 'export', 'motor_geometry.py')


def _modul_duzeyi_atama(kaynak_yolu, ad):
    """``ad = ...`` modül düzeyi atamasının AST düğümünü döndürür."""
    agac = ast.parse(open(kaynak_yolu, encoding='utf-8').read())
    for dugum in agac.body:
        if isinstance(dugum, ast.Assign) and len(dugum.targets) == 1 and \
                isinstance(dugum.targets[0], ast.Name) and \
                dugum.targets[0].id == ad:
            return dugum.value
    return None


class TestP7B106UzunlukTavani:
    """Tavan elle yazılmaz, kanondan türetilir (ÖK-16 / Doktrin 4)."""

    def test_uzunluk_tavani_elle_yazili_degil(self):
        """AST: ``LENGTH_SI_MAX_M`` bir SAYI sabiti OLAMAZ."""
        deger = _modul_duzeyi_atama(_GEOMETRI_KAYNAK, 'LENGTH_SI_MAX_M')
        assert deger is not None, (
            'LENGTH_SI_MAX_M modül düzeyinde bulunamadı')
        assert not (isinstance(deger, ast.Constant) and
                    isinstance(deger.value, (int, float))), (
            'LENGTH_SI_MAX_M yine ELLE yazılmış bir sayı; doğrulayıcının '
            'kanonik boy bandıyla ikinci (ve çelişebilen) bir zarf kurar — '
            'ÖK-16 / CLAUDE.md kural 11. Tavan '
            'motor_validation.LENGTH_UNIT_INFERENCE_MAX_M üzerinden '
            'türetilmelidir.')

    def test_tavan_kanonik_boy_bantlarinin_en_genisi(self):
        """Türetim ÜRÜNÜN KENDİ tablosundan gelir; sayı burada da yazılmaz."""
        beklenen = max(MV.CANONICAL_LIMITS[alan]['max']
                       for alan in MV.LENGTH_CANONICAL_FIELDS)
        assert MV.LENGTH_UNIT_INFERENCE_MAX_M == beklenen
        assert MG.LENGTH_SI_MAX_M == beklenen, (
            f'dışa aktarım tavanı {MG.LENGTH_SI_MAX_M}, kanonik boy '
            f'üst uçlarının en büyüğü {beklenen}')
        # Kanonik boy alanlarının HEPSİ gerçekten metre bandı taşımalı.
        for alan in MV.LENGTH_CANONICAL_FIELDS:
            assert MV.canonical_band_m(alan) is not None, (
                f'{alan} kanonik metre bandı taşımıyor; türetim dayanaksız')

    def test_kanon_ici_lule_boyu_milimetre_sayilmiyor(self):
        """CANLI kusur: bandı OLMAYAN ``nozzle_*`` alanları (once.json B3)."""
        bandsiz = [alan for alan in MG.EXPORT_LENGTH_FIELDS
                   if MG._plausible_band_m(alan) is None]
        assert bandsiz, (
            'ölçüm koşulu kayboldu: bandı olmayan boy alanı kalmamış, bu '
            'bekçinin ölçtüğü tek-eşikli yol artık kullanılmıyor olabilir')
        kanon_lo, kanon_hi = MV.canonical_band_m('chamber_length')
        for alan in bandsiz:
            tavan = MG.EXPORT_LENGTH_FIELDS[alan]
            for girdi in (6.0, 12.0, 19.0):
                assert kanon_lo <= girdi <= kanon_hi, 'vaka kanon dışı'
                metre, kaynak = MG.length_in_meters_banded(girdi, alan, tavan)
                assert kaynak == 'si' and metre == pytest.approx(girdi), (
                    f'{alan}={girdi} kanonik boy bandının İÇİNDE ama '
                    f'{metre} m ({kaynak}) olarak okundu — 1000 kat birim '
                    f'kayması, imalat paketine yanlış boy girer')

    def test_kanon_disi_boy_hala_milimetre_okunuyor(self):
        """Gerileme kalkanı: tavanın ÜSTÜ hâlâ mm (yön korunuyor)."""
        bandsiz = [alan for alan in MG.EXPORT_LENGTH_FIELDS
                   if MG._plausible_band_m(alan) is None]
        for alan in bandsiz:
            tavan = MG.EXPORT_LENGTH_FIELDS[alan]
            for girdi, beklenen in ((21.0, 0.021), (350.0, 0.35),
                                    (1200.0, 1.2)):
                metre, kaynak = MG.length_in_meters_banded(girdi, alan, tavan)
                assert kaynak == 'mm' and metre == pytest.approx(beklenen), (
                    f'{alan}={girdi} kanonik boy tavanının üstünde; mm '
                    f'okunmalıydı, {metre} m ({kaynak}) çıktı')

    def test_bantli_alanlar_birlesim_kuralinda_kaldi(self):
        """Bandı OLAN alan tavanı KULLANMAZ — tavan değişimi onları kaydırmaz.

        once.json/sonra.json B4 bu satırların bit-aynı olduğunu gösteriyor.
        """
        # TABAN AĞACINDAN ölçülmüş satırlar (once.json B4, dd1dcddc). Tavan
        # 5,0 -> 20,0 değişiminden SONRA da birebir aynı olmak zorundalar:
        # bandı olan alan si_max'ı hiç okumaz.
        beklenen = {
            'chamber_length': {0.35: (0.35, 'si'), 3.0: (3.0, 'si'),
                               6.0: (6.0, 'si'), 12.0: (12.0, 'si'),
                               19.0: (19.0, 'si'), 21.0: (None, 'out_of_band'),
                               350.0: (0.35, 'mm'), 1200.0: (1.2, 'mm')},
            'grain_length': {0.35: (0.35, 'si'), 3.0: (3.0, 'si'),
                             6.0: (6.0, 'si'), 12.0: (None, 'out_of_band'),
                             19.0: (None, 'out_of_band'),
                             21.0: (None, 'out_of_band'),
                             350.0: (0.35, 'mm'), 1200.0: (1.2, 'mm')},
            'chamber_diameter': {3.0: (3.0, 'si'), 6.0: (None, 'out_of_band'),
                                 12.0: (0.012, 'mm'), 19.0: (0.019, 'mm'),
                                 350.0: (0.35, 'mm')},
            'throat_diameter': {3.0: (0.003, 'mm'), 6.0: (0.006, 'mm'),
                                19.0: (0.019, 'mm'), 350.0: (0.35, 'mm')},
            'exit_diameter': {3.0: (None, 'ambiguous'), 6.0: (0.006, 'mm'),
                              19.0: (0.019, 'mm'), 350.0: (0.35, 'mm')},
        }
        for alan, vakalar in beklenen.items():
            tavan = MG.EXPORT_LENGTH_FIELDS[alan]
            assert MG._plausible_band_m(alan) is not None, f'{alan} bandsız'
            for girdi, (m_bek, k_bek) in vakalar.items():
                metre, kaynak = MG.length_in_meters_banded(girdi, alan, tavan)
                assert kaynak == k_bek, f'{alan}={girdi}: {kaynak} != {k_bek}'
                if m_bek is None:
                    assert metre is None, f'{alan}={girdi}: {metre} != None'
                else:
                    assert metre == pytest.approx(m_bek), f'{alan}={girdi}'

    def test_cidar_kalinligi_tavani_uydurulmadi(self):
        """KAPSAM DIŞI beyanı bekçiye bağlı: ``web_thickness``ten türetilemez.

        ``THICKNESS_SI_MAX_M`` ``wall_thickness`` içindir; kanonik tablodaki
        ``web_thickness`` katı yakıt AĞIdır (0,5 m). İkisi aynı büyüklük
        değildir; birinden diğerinin tavanı türetilirse 5 kat sessiz kayma
        olur. Kanonik kaynak yok → sayı uydurulmaz (fail-closed).
        """
        assert MV.canonical_band_m('wall_thickness') is None, (
            'wall_thickness artık kanonik bir bant taşıyor; THICKNESS_SI_MAX_M '
            'artık ondan TÜRETİLEBİLİR — bu bekçi güncellenmeli')
        assert MG.THICKNESS_SI_MAX_M != MV.canonical_band_m('web_thickness')[1], (
            'cidar kalınlığı tavanı katı yakıt AĞI bandından türetilmiş; '
            'iki ayrı büyüklük tek zarfa bağlanamaz')

    def test_baslik_iddiasi_curutulmus_kaliyor(self):
        """D31 çürütmesi duruyor: 50 'mm' sanılan çap HTTP 200 üretmiyor.

        Defter başlığı "chamber_diameter=50 -> 75 m oda, HTTP 200" diyordu;
        ürün ucu adlı ve bantlı 400 döndürüyor (once.json/sonra.json B6).
        """
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                from hrma.app import app
        app.config['TESTING'] = True
        istemci = app.test_client()
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                yanit = istemci.post('/calculate', json={
                    'motor_type': 'hybrid', 'oxidizer': 'n2o', 'fuel': 'htpb',
                    'thrust': 1000.0, 'burn_time': 10.0,
                    'chamber_pressure': 20.0, 'of_ratio': 6.0,
                    'chamber_diameter': 50.0})
        assert yanit.status_code == 400, (
            f'50 m çap HTTP {yanit.status_code} ile geçti — fail-closed kapı '
            f'kayboldu')
        govde = yanit.get_json() or {}
        alanlar = [f for f in (govde.get('invalid_fields') or [])
                   if f.get('field') == 'chamber_diameter']
        assert alanlar, 'ret alan adı taşımıyor'
        assert alanlar[0].get('reason') == 'out_of_range'
        assert alanlar[0].get('accepted_range') == [
            MV.CANONICAL_LIMITS['chamber_diameter']['min'],
            MV.CANONICAL_LIMITS['chamber_diameter']['max']], (
            'yayımlanan bant kanonik tablodan gelmiyor')


# ---------------------------------------------------------------------------
# OH-D31-01 — D31 arayuz-panel a1'in "ham dize" devri ödendi
# ---------------------------------------------------------------------------
# D31'de panel kulvarı dört YENİ etiketi sözlüğe bağlayamadı (i18n*.js kardeş
# kulvarın sahasıydı) ve metinleri ham dizeyle bastı. Ölçüm:
# ``once_ohd3101.json`` — 4 ham dizeli etiket, 4 anahtar EN'de YOK, 4 anahtar
# TR'de YOK. Bu bekçi ikisini birden ölçer: anahtar sözlükte AÇIK mı ve çağrı
# yeri gerçekten sözlükten mi geçiyor.
_JS_KOK = os.path.join(_KOK, 'hrma', 'static', 'js')
_SOZLUK_KAYNAK = os.path.join(_JS_KOK, 'i18n_common.js')

#: (anahtar, etiketi basan dosya, ham dizenin imzası)
_OHD3101_ETIKETLER = (
    ('fea.qualitySource', 'fea_panel.js',
     "'Mesh quality metrics computed by: '"),
    ('fea.limitRefineFactor', 'fea_panel.js',
     "parts.push('Each refinement round"),
    ('panel.cfd.rowThroatArea', os.path.join('panels', 'cfd_panel.js'),
     "['Throat area A_t (used for c*)',"),
    ('panel.correlation.reportText', os.path.join('panels',
                                                  'correlation_panel.js'),
     "'Full report text (' + U.num("),
)


def _dil_bloklari():
    """``i18n_common.js``in EN ve TR gövdelerini metin olarak döndürür."""
    import re
    govde = open(_SOZLUK_KAYNAK, encoding='utf-8').read()
    tr = re.search(r'^        tr:\s*\{', govde, re.M)
    assert tr, 'i18n_common.js TR dil bloğu bulunamadı'
    return govde[:tr.start()], govde[tr.start():]


class TestOHD3101HamDizeDevri:
    """Dört etiket EN+TR sözlüğe açıldı ve çağrı yerleri bağlandı."""

    @pytest.mark.parametrize('anahtar,dosya,imza', _OHD3101_ETIKETLER)
    def test_anahtar_EN_ve_TR_sozlukte(self, anahtar, dosya, imza):
        import re
        en_govde, tr_govde = _dil_bloklari()
        desen = r"'" + re.escape(anahtar) + r"'\s*:"
        assert len(re.findall(desen, en_govde)) == 1, (
            f'{anahtar} EN sözlüğünde tam olarak bir kez tanımlı değil')
        assert len(re.findall(desen, tr_govde)) == 1, (
            f'{anahtar} TR sözlüğünde tam olarak bir kez tanımlı değil — '
            f'yarım aile (EN var, TR yok) D31 arayuz-i18n dersinde gerçek '
            f'kusur sayılır')

    @pytest.mark.parametrize('anahtar,dosya,imza', _OHD3101_ETIKETLER)
    def test_cagri_yeri_sozlukten_geciyor(self, anahtar, dosya, imza):
        govde = open(os.path.join(_JS_KOK, dosya), encoding='utf-8').read()
        assert ("'" + anahtar + "'") in govde, (
            f'{dosya} etiketi hâlâ sözlüğe bağlı değil ({anahtar} geçmiyor)')
        assert imza not in govde, (
            f'{dosya} içinde ham dize hâlâ duruyor: {imza!r}')

    def test_TR_metinleri_gercekten_turkce(self):
        """TR karşılığı İngilizce kopyası olamaz (yarım çeviri kusurdur)."""
        import re
        en_govde, tr_govde = _dil_bloklari()
        for anahtar, _dosya, _imza in _OHD3101_ETIKETLER:
            desen = r"'" + re.escape(anahtar) + r"'\s*:\s*'([^']*)'"
            en = re.search(desen, en_govde).group(1)
            tr = re.search(desen, tr_govde).group(1)
            assert tr != en, f'{anahtar}: TR metni EN metninin kopyası'

    def test_yer_tutucular_iki_dilde_ayni(self):
        """``{source}`` / ``{factor}`` / ``{kb}`` iki dilde de bulunmalı."""
        import re
        en_govde, tr_govde = _dil_bloklari()
        for anahtar, _dosya, _imza in _OHD3101_ETIKETLER:
            desen = r"'" + re.escape(anahtar) + r"'\s*:\s*'([^']*)'"
            en = set(re.findall(r'\{(\w+)\}',
                                re.search(desen, en_govde).group(1)))
            tr = set(re.findall(r'\{(\w+)\}',
                                re.search(desen, tr_govde).group(1)))
            assert en == tr, (
                f'{anahtar}: yer tutucular ayrışıyor EN={sorted(en)} '
                f'TR={sorted(tr)} — TR kipinde sayı basılmaz')

    def test_p12bb407_basligi_iki_dilde_tanimli_ve_kunyesiz(self):
        """``fx.s14_1.h`` iki dilde tanımlı ve KAZANILMAMIŞ künye taşımıyor.

        ÇEVRİLDİ (ana model, 15 Eyl 2026, D32 birleşme sırası): bu iddia
        önce "(NASA SP-125)" künyesinin iki dilde DURMASINI kilitliyordu;
        aynı dalgada arayuz-panel a1 (P12bB4-07) o künyeyi kazanılmamış
        olduğu için düşürdü (yüzey SP-125'ten değil kimyasal denge
        çözücüsünden; hüküm-21). Eski hâliyle test kusuru koruyan bekçiydi
        (D31 dersi 20). Korunan iddia: anahtar iki dilde tanımlı (OH-D31-01
        ham dize devri); künye yokluğu tests/test_d32_arayuz_panel_a1.py::
        TestP12bB407KazanilmamisKunye ile birlikte kilitlenir.
        """
        import re
        govde = open(os.path.join(_JS_KOK, 'i18n_formulas.js'),
                     encoding='utf-8').read()
        metinler = re.findall(r"'fx\.s14_1\.h'\s*:\s*'([^']*)'", govde)
        assert len(metinler) == 2, (
            f'fx.s14_1.h iki dilde tanımlı olmalı, {len(metinler)} bulundu')
        for metin in metinler:
            assert 'SP-125' not in metin, (
                f'kazanılmamış künye geri gelmiş: {metin[:60]!r}')
