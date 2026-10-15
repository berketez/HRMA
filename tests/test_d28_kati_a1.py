"""ÖH Dalga-28 · kulvar katı · aşama 1 — OH-D27-15 bekçileri.

KALEM: boğaz erozyonu yasasının BASINÇ ÜSSÜ.

Kusur (ölçüldü, docs/scofield/raw/OH/D28/kati/a1/once.json):
  * üs `0.8` elle yazılmış bir literaldi; katsayının (band, tek-nokta çapa)
    künyesi D19/D27'de bağlanmışken ÜS kaynaksızdı,
  * gerekçesi erozyon literatürü değil bir ISI TRANSFERİ korelasyonuydu
    (Bartz 1957, `h_g ∝ Pc^0,8`) — o üs yasanın yalnız TAŞINIM ucudur,
  * birincil kaynak (Thakre & Yang, JPP 24(4) 2008) erozyon hızının basınçla
    LİNEER arttığını söyler; 0,8 kaynağın doğruladığı aralığın üst ucunda
    (45 MPa) lineer yasanın 0,689 katıdır, yani erozyonu %31 EKSİK gösterir
    (itki/basıncı fazla gösteren = güvensiz yön),
  * üs ürün yüzeyinde künyesiz yayımlanıyordu (`describe()` ve katı motorun
    erozyon tahmini `exponent_source` alanı taşımıyordu),
  * aynı makaleye iki dosyada Thakre'nin DOKTORA TEZİNİN başlığı veriliyor,
    grafit bandının sayısı `solid_rocket_engine.py`'de İKİNCİ KEZ (ve bayat:
    0.05-0.25 ⟷ 0.069-0.353) yazılıyordu.

Onarım: üs künyesinden okunur (`_exponent_from_citation`), `n = 1,0`,
geçerlilik aralığı (69-450 bar) künyeden gelir ve ekstrapolasyon beyan
edilir; künye ürün yüzeyinde yayımlanır; ikinci kopyalar söküldü.

Literatür notu: docs/arastirma/fizik/bogaz-erozyonu-grafit-cc-bandi.md §8
(alıntılar birincil kaynağın PDF metin katmanından doğrulandı).
"""
import contextlib
import io
import pathlib
import re

import pytest

from hrma.analysis import transient_ballistics as tb
from hrma.analysis.transient_ballistics import (
    THROAT_EROSION_MATERIALS, ThroatErosionModel)
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(tb.__file__).resolve().parents[2]
NOT = KOK / 'docs' / 'arastirma' / 'fizik' / 'bogaz-erozyonu-grafit-cc-bandi.md'

# --- BAĞIMSIZ literatür transkripsiyonu (üründen ithal EDİLMEZ) ------------
# Thakre & Yang 2008: Fig. 14 (s. 830) ve Sonuçlar (s. 832) erozyon hızını
# hazne basıncıyla LİNEER verir ⇒ n = 1,0. Tablo 2'deki altı basınç
# 6,9 / 10 / 15 / 25 / 35 / 45 MPa ⇒ geçerlilik aralığı 69-450 bar.
LINEER_US = 1.0
GECERLI_ARALIK_BAR = (69.0, 450.0)
# Mekanizmanın iki ucu: taşınım (Bartz/Chilton-Colburn) 0,8 · kinetik 1,0.
MEKANIZMA_BANDI = (0.8, 1.0)
BORIE_CC_MM_S, BORIE_CC_PC_BAR = 0.139, 49.0
GEISLER_TABLO8_UST_MM_S = 0.353


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(pc_bar, **ov):
    return _sessiz(
        SolidRocketEngine, propellant_type='apcp', grain_type='bates',
        chamber_pressure=pc_bar, chamber_diameter=100.0, grain_length=500.0,
        core_diameter=30.0, overrides=ov)


# ---------------------------------------------------------------- ÜS/KÜNYE
class TestUssunKunyesiVar:
    """Üs artık kaynaksız bir literal değil."""

    def test_us_elle_yazilmis_literal_degil(self):
        """Kaynak dosyada `THROAT_EROSION_PRESSURE_EXPONENT = <sayı>` yok."""
        kaynak = open(tb.__file__, encoding='utf-8').read()
        elle = re.findall(
            r'^THROAT_EROSION_PRESSURE_EXPONENT\s*=\s*([0-9.]+)\s*$',
            kaynak, re.MULTILINE)
        assert elle == [], (
            'üs elle yazılmış: künyeden okunmalı (_exponent_from_citation)')
        assert hasattr(tb, 'THROAT_EROSION_PRESSURE_EXPONENT_CITATION')

    def test_us_kunyeden_bagimsiz_ayristirilabiliyor(self):
        n, aralik = tb._exponent_from_citation(
            tb.THROAT_EROSION_PRESSURE_EXPONENT_CITATION)
        assert n == pytest.approx(tb.THROAT_EROSION_PRESSURE_EXPONENT,
                                  rel=1e-12)
        assert tuple(aralik) == pytest.approx(
            tb.THROAT_EROSION_EXPONENT_VALID_PC_BAR, rel=1e-12)

    def test_us_literaturun_soyledigi_sayidir(self):
        """LİNEER (n = 1,0) — Bartz'ın ısı transferi üssü (0,8) DEĞİL."""
        assert tb.THROAT_EROSION_PRESSURE_EXPONENT == pytest.approx(
            LINEER_US, rel=1e-12)
        assert tuple(tb.THROAT_EROSION_EXPONENT_VALID_PC_BAR) == \
            pytest.approx(GECERLI_ARALIK_BAR, rel=1e-12)

    def test_us_mekanizma_bandinin_icinde(self):
        """İLİŞKİ bekçisi: n, iki mekanizma ucunun arasında kalmalı.

        Taşınım ucu 0,8 (kütle akısı `g_m = h_g/(c_p·Le^{2/3})`, Bartz
        `h_g ∝ Pc^0,8`), kinetik ucu 1,0 (birinci mertebe, `p_i = X_i·Pc`).
        Bandın dışına çıkan bir üs iki uçtan hiçbiriyle açıklanamaz.
        """
        alt, ust = MEKANIZMA_BANDI
        assert alt <= tb.THROAT_EROSION_PRESSURE_EXPONENT <= ust

    def test_kunye_kaynagi_ve_lineerligi_adiyla_soyluyor(self):
        k = tb.THROAT_EROSION_PRESSURE_EXPONENT_CITATION
        for parca in ('Thakre', 'Yang', '24(4) 2008', '10.2514/1.34946',
                      'LINEARLY', 'Fig. 14', '6.9-45.0 MPa'):
            assert parca in k, f'üs künyesinde {parca!r} yok'
        # Bartz künyede AMA 'yasanın üssü değil' diye geçmeli.
        assert 'Bartz' in k and 'NOT the exponent' in k

    def test_kunyesiz_us_fail_closed(self):
        """Künyede üs/aralık yoksa sayı ÜRETİLMEZ (sessiz yedek yok)."""
        with pytest.raises(ValueError):
            tb._exponent_from_citation('kaynaksiz metin')
        with pytest.raises(ValueError):
            tb._exponent_from_citation('exponent n = 1.0, aralik yok')


# -------------------------------------------------------- ÜRÜN YÜZEYİ (API)
class TestUsUrunYuzeyindeKunyesiyleYayimlaniyor:

    def test_describe_ussun_kaynagini_ve_araligini_yayimliyor(self):
        d = ThroatErosionModel.for_material('graphite').describe()
        assert d['exponent'] == pytest.approx(LINEER_US)
        assert d['exponent_attributed'] is True
        assert 'Thakre' in d['exponent_source']
        assert d['exponent_valid_pc_bar'] == list(GECERLI_ARALIK_BAR)

    def test_kullanici_ussunde_atif_GECMEZ(self):
        """Kullanıcı üssü değiştirdiyse kaynağın atfı ona devredilemez."""
        m = ThroatErosionModel(0.2, exponent=0.65)
        d = m.describe()
        assert d['exponent'] == pytest.approx(0.65)
        assert d['exponent_attributed'] is False
        assert d['exponent_source'] is None
        assert d['exponent_valid_pc_bar'] is None

    def test_ekstrapolasyon_uc_degerli(self):
        m = ThroatErosionModel.for_material('graphite')
        assert m.exponent_extrapolated(70.0) is False
        assert m.exponent_extrapolated(GECERLI_ARALIK_BAR[0]) is False
        assert m.exponent_extrapolated(GECERLI_ARALIK_BAR[1]) is False
        assert m.exponent_extrapolated(20.0) is True
        assert m.exponent_extrapolated(500.0) is True
        # Aralığı bilinmeyen (kullanıcı) üste 'hayır' demek yanlış olurdu.
        assert ThroatErosionModel(0.2, exponent=0.65).exponent_extrapolated(
            70.0) is None

    def test_kati_motor_tahmini_ussu_ve_kunyesini_yayimliyor(self):
        e = _motor(40.0, nozzle_material='graphite')
        est = _sessiz(e._nozzle_erosion_estimate)
        assert est['status'] == 'computed'
        assert est['exponent'] == pytest.approx(LINEER_US)
        assert est['exponent_attributed'] is True
        assert 'Thakre' in est['exponent_source']
        assert est['exponent_valid_pc_bar'] == list(GECERLI_ARALIK_BAR)
        # 40 bar kaynağın ölçtüğü aralığın ALTINDA — sessizce geçilmez.
        assert est['exponent_extrapolated'] is True
        # 100 bar aralığın içinde.
        est2 = _sessiz(_motor(100.0, nozzle_material='graphite')
                       ._nozzle_erosion_estimate)
        assert est2['exponent_extrapolated'] is False

    def test_yayimlanan_model_dizgesi_ussu_izliyor(self):
        est = _sessiz(_motor(40.0, nozzle_material='graphite')
                      ._nozzle_erosion_estimate)
        assert f"^{tb.THROAT_EROSION_PRESSURE_EXPONENT:g}" in est['model']
        assert '^0.8' not in est['model']


# ------------------------------------------------------------- SAYISAL ETKİ
class TestSayisalEtkiUssuIzliyor:

    def test_cc_capasi_modelin_kendi_yasasiyla_tasiniyor(self):
        beklenen = BORIE_CC_MM_S * (
            tb.THROAT_EROSION_PC_REF_BAR / BORIE_CC_PC_BAR) ** \
            tb.THROAT_EROSION_PRESSURE_EXPONENT
        capa = THROAT_EROSION_MATERIALS['carbon_carbon']['a_ref_anchor_mm_s']
        assert capa == pytest.approx(beklenen, rel=1e-12)
        assert capa == pytest.approx(0.19857, abs=5e-5)

    def test_kaynagin_ust_ucunda_lineer_yasadan_sapma_yok(self):
        """45 MPa'da (450 bar) 0,8 üssü lineerin 0,689 katıydı."""
        m = ThroatErosionModel.for_material('graphite')
        oran = m.rate_mm_s(450.0) / (m.a_ref_mm_s * (450.0 / 70.0))
        assert oran == pytest.approx(1.0, rel=1e-12)
        # Eski üssün eksikliği (kayıt): 0,689.
        assert ((450.0 / 70.0) ** 0.8) / (450.0 / 70.0) == pytest.approx(
            0.6893, abs=5e-4)

    def test_grafit_hizi_bandin_ust_ucundan_lineer_turer(self):
        m = ThroatErosionModel.for_material('graphite')
        assert m.a_ref_mm_s == pytest.approx(GEISLER_TABLO8_UST_MM_S,
                                             rel=1e-12)
        for pc in (40.0, 100.0, 450.0):
            assert m.rate_mm_s(pc) == pytest.approx(
                GEISLER_TABLO8_UST_MM_S * pc / 70.0, rel=1e-12)

    def test_birim_tutarliligi_usten_bagimsiz(self):
        """Boyut analizi: (Pc/Pc_ref) boyutsuz ⇒ [ṙ] = [a_ref] = L·T⁻¹."""
        m = ThroatErosionModel.for_material('graphite')
        for pc in (20.0, 70.0, 300.0):
            assert m.rate_m_s(pc * 1e5) == pytest.approx(
                m.rate_mm_s(pc) * 1e-3, rel=1e-12)


# ---------------------------------------------------------------- TEK KAYNAK
class TestKunyeVeTekKaynak:

    KUNYE_HEDEF_DOSYALARI = ('hrma/analysis/transient_ballistics.py',
                'hrma/engines/solid_rocket_engine.py',
                'docs/arastirma/fizik/bogaz-erozyonu-grafit-cc-bandi.md')

    @staticmethod
    def _duzlestir(metin):
        metin = re.sub(r'\n\s*#\s*', ' ', metin)
        return re.sub(r'\s+', ' ', metin)

    @pytest.mark.parametrize('yol', KUNYE_HEDEF_DOSYALARI)
    def test_makaleye_tez_basligi_verilmiyor(self, yol):
        """JPP 24(4) 2008'in başlığı 'Carbon-Carbon/Graphite Nozzles'tır.

        'Chemical Erosion of Graphite and Refractory Metal Nozzles ...'
        Thakre'nin DOKTORA TEZİNİN başlığıdır; depoda makaleye veriliyordu.
        """
        metin = self._duzlestir((kanit_gerekli(KOK / yol)).read_text(encoding='utf-8'))
        assert not re.search(
            r'Chemical Erosion of Graphite and Refractory Metal Nozzles',
            metin, re.IGNORECASE), f'{yol}: makaleye tez başlığı verilmiş'

    def test_grafit_bandinin_ikinci_sayisal_kopyasi_yok(self):
        sre = self._duzlestir(
            (KOK / 'hrma/engines/solid_rocket_engine.py').read_text(
                encoding='utf-8'))
        kopya = re.findall(r'Geisler.{0,80}?(\d\.\d+)-(\d\.\d+)\s*mm/s', sre)
        assert kopya == [], (
            f'bandın ikinci kopyası: {kopya} — tek tanım noktası '
            'transient_ballistics.GRAPHITE_A_REF_BAND_CITATION')
        assert 'Geisler AIAA' not in sre, (
            "Geisler'in yayım yeri JANNAF'tır (D27'de düzeltildi)")

    def test_solid_motor_ussu_elle_yazmiyor(self):
        sre = (KOK / 'hrma/engines/solid_rocket_engine.py').read_text(
            encoding='utf-8')
        # Erozyon yasasının üssü bu dosyada YENİDEN YAZILMAZ.
        assert 'a_ref·(Pc/70 bar)^0.8' not in sre
        assert re.search(r'\(Pc/Pc_ref\)\^n', sre), (
            'yasanın adı (üssüz biçimi) yorumda kalmalı'
        )


# ------------------------------------------------------------- LİTERATÜR NOTU
class TestLiteraturNotuKarariTasiyor:

    def test_not_ussun_kararini_ve_alintilarini_tasiyor(self):
        m = kanit_gerekli(NOT).read_text(encoding='utf-8')
        assert 'OH-D27-15' in m
        for parca in ('linear variation of the graphite',
                      'increases linearly with the chamber pressure',
                      'remain nearly constant in the pressure range',
                      's. 830', 's. 832', '69-450 bar'):
            assert parca in m, f'literatür notunda {parca!r} yok'

    def test_notun_sayilari_urunle_ayrismiyor(self):
        m = kanit_gerekli(NOT).read_text(encoding='utf-8')
        n = tb.THROAT_EROSION_PRESSURE_EXPONENT
        capa = THROAT_EROSION_MATERIALS['carbon_carbon']['a_ref_anchor_mm_s']
        assert f'{capa:.4f}'.replace('.', ',') in m
        assert f'{n:g}'.replace('.', ',') in m
        # Mekanizmanın iki ucu da adıyla yazılı olmalı.
        assert 'Chilton-Colburn' in m and 'kinetik' in m
