# -*- coding: utf-8 -*-
"""ÖH D27 / katı aşama-1 — OH-D25-27 + OH-D24-11 (kalan ayak, ÇİFT KALEM).

Kalem: boğaz erozyonu katsayı bandının literatüre çapalanması.

  (1) GRAFİT — depo künyesi ``'Geisler AIAA graphite band 0.05-0.25 mm/s'``
      idi. İki kusur: kaynağın yayım yeri **AIAA değil JANNAF**'tır
      (Geisler, JANNAF Rocket Nozzle Technology Subcommittee Meeting,
      Lancaster CA, 1978 — Thakre & Yang 2008 kaynakça [6]); ve bandın
      sayısı deponun KENDİ dizgesiydi. Ölçülen band (Thakre & Yang, J.
      Prop. Power 24(4) 2008, Tablo 8; BATES, bulk grafit, p_t = 6,9 MPa,
      %15..%27 Al AP/HTPB) **0,069-0,353 mm/s**'dir. Varsayılan ``a_ref``
      bandın üst ucundan türediği için depo erozyonu EKSİK tahmin
      ediyordu → itki/basınç FAZLA gösteriliyordu (güvensiz yön).

  (2) C-C — ``(0.02, 0.10)`` bandı depo-içi kestirimdi ve depodaki TEK
      atfedilebilir C-C ölçümüyle çelişiyordu (Borie ve ark., Thakre &
      Yang Tablo 5 / Şekil 18: 4,9 MPa'da 0,139 mm/s ⇒ 70 bar'da
      0,185 mm/s). Kaynaksız sayı SÖKÜLDÜ; tek nokta band vermediği için
      C-C artık band yayımlamaz, katsayısı künyeli çapadan türer.

ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/kati/a1/{once,sonra}.json):

  ölçüt                                     önce      sonra
  grafit band üst ucu ÷ ölçülen             0,708     1,000
  grafit band alt ucu ÷ ölçülen             0,725     1,000
  C-C katsayısı ÷ Borie (70 bar)            0,541     1,000
  atfedilmemiş sayı yayımlayan malzeme      1         0
  künyesi yanlış yayın yeri gösteren        1         0
  bant-dışı uyarısı yanlış alarm            2         0
  bant-dışı uyarısı kaçırma                 2         0
  rijit-boğaz uyarısı ateşleyen motor       2/4       3/4
  CAD @40 bar grafit / C-C            0,1598/0,0639  0,2256/0,1182 mm/s

Literatür notu: docs/arastirma/fizik/bogaz-erozyonu-grafit-cc-bandi.md
"""
import contextlib
import io
import math
import re

import pytest

from hrma.analysis import transient_ballistics as tb
from hrma.analysis.transient_ballistics import (
    THROAT_EROSION_MATERIALS, ThroatErosionModel)
from hrma.engines.solid_rocket_engine import (
    SolidRocketEngine, THROAT_EROSION_SIGNIFICANT_AREA_GROWTH)
from tests.support.kanit import kanit_gerekli

# --- BAĞIMSIZ literatür transkripsiyonu (üründen ithal EDİLMEZ) ------------
# Thakre & Yang 2008, Tablo 8 — Geisler [6] BATES bulk grafit, p_t = 6,9 MPa:
#   %15 Al 0,353 · %18 0,284 · %21 0,200 · %24 0,124 · %27 0,069 mm/s
GEISLER_TABLO8_MM_S = (0.069, 0.353)
# Tablo 5 / Şekil 18 — Borie ve ark. (SEP) C-C, p_t = 4,9 MPa
BORIE_CC_MM_S = 0.139
BORIE_CC_PC_BAR = 49.0


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _kodlar(a_ref):
    """Grafit boğazda kullanıcı katsayısıyla dönen uyarı kodları."""
    e = SolidRocketEngine(
        grain_type='bates', propellant_type='apcp', chamber_diameter=100,
        grain_length=500, core_diameter=30, chamber_pressure=40,
        overrides={'nozzle_material': 'graphite',
                   'throat_erosion_a_ref_mm_s': a_ref})
    r = _sessiz(e.calculate_performance)
    kodlar = set()
    for anahtar in ('warnings', 'design_warnings'):
        for w in (r.get(anahtar) or []):
            if isinstance(w, dict) and w.get('code'):
                kodlar.add(w['code'])
    return kodlar


# ------------------------------------------------- OH-D25-27 · grafit -----
class TestGrafitBandiOlculenBandaCapali:
    """Ürünün grafit bandı Tablo 8'in ÖLÇÜLEN değerleridir."""

    def test_band_ve_varsayilan_olculen_bandin_kendisi(self):
        rec = THROAT_EROSION_MATERIALS['graphite']
        band = tuple(float(x) for x in rec['a_ref_band_mm_s'])
        assert band == GEISLER_TABLO8_MM_S, (
            f'ürün bandı {band}, ölçülen band {GEISLER_TABLO8_MM_S}')
        # Varsayılan = bandın konservatif (üst) ucu — kural KOD.
        assert rec['a_ref_default_mm_s'] == pytest.approx(
            GEISLER_TABLO8_MM_S[1], rel=1e-12)

    def test_band_olculeni_kapsiyor_ve_altinda_kalmiyor(self):
        """Tabanda ölçüt: üst uç ölçülenin %70,8'i, band kapsamıyordu."""
        alt, ust = (float(x) for x in tb.GRAPHITE_A_REF_BAND_MM_S)
        assert alt <= GEISLER_TABLO8_MM_S[0]
        assert ust >= GEISLER_TABLO8_MM_S[1], (
            f'üst uç {ust} ölçülen {GEISLER_TABLO8_MM_S[1]} altında: '
            'erozyon eksik, itki/basınç fazla gösterilir (güvensiz yön)')

    def test_kunye_yayin_yerini_dogru_soyluyor(self):
        """Geisler 1978 JANNAF'ta yayımlandı; künye AIAA diyemez."""
        kunye = tb.GRAPHITE_A_REF_BAND_CITATION
        assert 'JANNAF' in kunye
        assert 'AIAA' not in kunye
        # Kayıt künyesi ve modelin yayımladığı künye aynı dizgedir.
        d = ThroatErosionModel.for_material('graphite').describe()
        assert d['band_source'] == kunye
        assert 'AIAA' not in (d['source'] or '')

    def test_band_kunyeden_okunuyor_sayi_ayri_yazilamaz(self):
        """Sayının tek tanım noktası künyedir (``_band_from_citation``)."""
        assert tb._band_from_citation(tb.GRAPHITE_A_REF_BAND_CITATION) == \
            tuple(float(x) for x in tb.GRAPHITE_A_REF_BAND_MM_S)
        kaynak = open(tb.__file__, encoding='utf-8').read()
        bantlar = set(re.findall(
            r'(\d+\.\d+)\s*-\s*(\d+\.\d+)\s*mm/s',
            kaynak.replace('–', '-')))
        assert bantlar == {('%g' % GEISLER_TABLO8_MM_S[0],
                            '%g' % GEISLER_TABLO8_MM_S[1])}, (
            f'modül metninde çelişen ikinci bant: {bantlar}')


# ------------------------------------------- OH-D24-11 (b) · C-C sınıfı ---
class TestCCKatsayisiOlcumeCapali:
    """C-C: kaynaksız band söküldü, katsayı ölçüme çapalandı."""

    def test_yayimlanmis_band_yok(self):
        rec = THROAT_EROSION_MATERIALS['carbon_carbon']
        assert rec['a_ref_band_mm_s'] is None
        assert rec['band_source'] is None
        assert rec['band_attributed'] is False

    def test_katsayi_borie_olcumunun_model_yasasiyla_tasinmisidir(self):
        """BAĞIMSIZ yeniden hesap: 0,139·(70/49)^0,8 = 0,18490 mm/s."""
        beklenen = BORIE_CC_MM_S * (
            tb.THROAT_EROSION_PC_REF_BAR / BORIE_CC_PC_BAR) ** \
            tb.THROAT_EROSION_PRESSURE_EXPONENT
        m = ThroatErosionModel.for_material('carbon_carbon')
        assert m.a_ref_mm_s == pytest.approx(beklenen, rel=1e-12)
        # ÖH D28 / OH-D27-15: kapalı-form çapa n = 0,8 iken 0,18490 idi;
        # üs künyesine bağlanınca (n = 1,0) ölçüm AYNI kalıp taşıma
        # değişti: 0,139·(70/49) = 0,19857 mm/s. Sayı elle güncellendi,
        # ilişki (Borie ölçümü × modelin kendi yasası) aynı.
        assert m.a_ref_mm_s == pytest.approx(0.19857, abs=5e-5)
        # Depo-içi eski kestirimin üst ucu (0,10) ölçülenin YARISIYDI.
        assert m.a_ref_mm_s > 1.8 * 0.10

    def test_capa_elle_yazilmaz_kunyeden_okunur(self):
        rec = THROAT_EROSION_MATERIALS['carbon_carbon']
        assert tb._anchor_from_citation(rec['anchor_source']) == \
            pytest.approx(rec['a_ref_anchor_mm_s'], rel=1e-12)
        kaynak = open(tb.__file__, encoding='utf-8').read()
        assert re.findall(r"'a_ref_anchor_mm_s':\s*([0-9.]+)", kaynak) == []

    def test_capa_atfi_yayimlaniyor(self):
        """``band_attributed False`` tek başına 'kaynaksız' demek değil."""
        d = ThroatErosionModel.for_material('carbon_carbon').describe()
        assert d['anchor_attributed'] is True
        assert 'Borie' in d['anchor_source']
        assert 'Thakre' in d['anchor_source'] and '2008' in d['anchor_source']

    def test_desteklenmeyen_siralama_iddiasi_kunyede_kalmadi(self):
        """'C-C bulk grafitten daha az erozyona uğrar' sayılarla YOK.

        Literatür notu §4: karşılaştırılabilir Al yüklemesinde atfedilen
        tek C-C noktası bulk grafitten YÜKSEK çıkıyor.
        """
        rec = THROAT_EROSION_MATERIALS['carbon_carbon']
        metin = rec['source']
        # Eski künyenin OLUMLAYAN cümlesi kalmamalı.
        assert 'dense C-C erodes measurably less than bulk ' \
               'polycrystalline graphite' not in metin
        # İddia anılıyorsa MUTLAKA desteklenmediği söylenerek anılır.
        if 'erodes measurably less' in metin:
            assert 'NOT supported' in metin, (
                'sıralama iddiası desteksiz olduğu söylenmeden anılıyor')

    def test_cc_bant_disi_denetimine_tabi_degil(self):
        """Bandı olmayan malzemede 'bant dışı' kapısı ateşlenemez."""
        e = SolidRocketEngine(
            grain_type='bates', propellant_type='apcp', chamber_diameter=100,
            grain_length=500, core_diameter=30, chamber_pressure=40,
            overrides={'nozzle_material': 'carbon_carbon',
                       'throat_erosion_a_ref_mm_s': 0.60})
        r = _sessiz(e.calculate_performance)
        kodlar = {w['code'] for w in (r.get('warnings') or [])
                  if isinstance(w, dict) and w.get('code')}
        assert 'warn.solid.throat_erosion_coeff_off_band' not in kodlar, (
            'C-C için yayımlanmış band yok; bant-dışı hükmü verilemez')


# --------------------------------------- ÜRÜN YÜZÜ · bant-dışı kapısı -----
class TestBantDisiKapisiOlculenBandaGore:
    """Kapı ölçülen bandın iki yanında da doğru karar veriyor mu?

    Tabanda 11 katsayının 4'ünde yanlış karar veriliyordu: 0,30 ve 0,353
    ölçülen bandın İÇİNDE olmasına rağmen uyarı alıyordu (yanlış alarm),
    0,05 ve 0,06 ölçülen bandın ALTINDA olmasına rağmen sessiz geçiyordu
    (kaçırma).
    """

    @pytest.mark.parametrize('a_ref', [0.069, 0.10, 0.20, 0.25, 0.30, 0.353])
    def test_olculen_bandin_icinde_uyari_yok(self, a_ref):
        assert GEISLER_TABLO8_MM_S[0] <= a_ref <= GEISLER_TABLO8_MM_S[1]
        assert 'warn.solid.throat_erosion_coeff_off_band' not in _kodlar(
            a_ref), (f'a_ref={a_ref} ölçülen bandın içinde ama uyarı basıldı')

    @pytest.mark.parametrize('a_ref', [0.001, 0.05, 0.06, 0.40, 0.60])
    def test_olculen_bandin_disinda_uyari_var(self, a_ref):
        assert not (GEISLER_TABLO8_MM_S[0] <= a_ref
                    <= GEISLER_TABLO8_MM_S[1])
        assert 'warn.solid.throat_erosion_coeff_off_band' in _kodlar(
            a_ref), (f'a_ref={a_ref} ölçülen bandın dışında ama sessiz geçti')


# ------------------------------- ÜRÜN YÜZÜ · rijit-boğaz uyarısı kapsamı --
class TestRijitBogazUyarisiEksikTahminleSusmuyor:
    """Ø200/L800/c120 motoru tabanda eşiğin HEMEN ALTINDA susuyordu.

    Kestirim %4,801 (eşik %5) — bu sessizlik motorun fiziğinden değil,
    katsayının ölçülenin %70,8'i olmasından geliyordu. Ölçülen katsayıyla
    aynı motor %6,812 veriyor ve uyarıyı hak ediyor.
    """

    GEO = dict(chamber_diameter=200, core_diameter=120, grain_length=800)

    def _kos(self):
        m = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                              chamber_pressure=40, **self.GEO)
        return m, _sessiz(m.calculate_performance)

    def test_uyari_cikiyor(self):
        _, r = self._kos()
        uyarilar = [w for w in (r.get('design_warnings') or [])
                    if w.get('code') == 'warn.solid.rigid_throat_assumption']
        assert len(uyarilar) == 1, (
            'eşiğin hemen altında susan motor, ölçülen katsayıyla uyarı '
            'almalı')

    def test_kural_bagimsiz_kuruluyor(self):
        """Uyarı ⟺ modelin KENDİ kestirimi eşiği aşıyor (iki yönlü)."""
        m, r = self._kos()
        ref = _sessiz(m._nozzle_erosion_reference)
        assert ref is not None
        egri = r.get('thrust_curve') or {}
        p = egri.get('pressure') or []
        p_ort = (sum(map(float, p)) / len(p)) if p else float(m.P_c)
        r0 = float(r['throat_diameter']) / 2.0
        buyume = ((r0 + ref.rate_mm_s(p_ort) * float(r['burn_time'])) / r0) \
            ** 2 - 1.0
        uyari = any(w.get('code') == 'warn.solid.rigid_throat_assumption'
                    for w in (r.get('design_warnings') or []))
        assert uyari == (buyume > THROAT_EROSION_SIGNIFICANT_AREA_GROWTH)
        assert buyume > THROAT_EROSION_SIGNIFICANT_AREA_GROWTH, (
            f'kestirim %{buyume * 100:.3f} eşiğin altında kaldı')


# ------------------------------------------- YAPISAL · atıfsız sayı yok ---
class TestAtifsizSayiYayimlanmiyor:
    """Bir SAYI yayımlayan her malzeme onu bir kaynağa bağlayabilmeli."""

    def test_hicbir_malzeme_kaynaksiz_katsayi_yayimlamiyor(self):
        suclu = []
        for ad, rec in THROAT_EROSION_MATERIALS.items():
            if rec.get('a_ref_default_mm_s') is None:
                continue
            if not (rec.get('band_attributed')
                    or rec.get('anchor_attributed')):
                suclu.append(ad)
        assert suclu == [], (
            f'{suclu}: varsayılan katsayı yayımlıyor ama ne bandı ne '
            'çapası atfedilmiş (Doktrin 6 — sayı uydurma)')

    def test_bandi_da_capasi_da_olmayan_malzeme_model_kuramaz(self):
        """Fail-closed: çelik/bakır a_ref'siz model kurdurmaz."""
        for mat in ('steel', 'copper'):
            assert THROAT_EROSION_MATERIALS[mat]['a_ref_default_mm_s'] is None
            with pytest.raises(ValueError):
                ThroatErosionModel.for_material(mat)


# ------------------------------------------------- BOYUT ANALİZİ ----------
class TestBoyutTutarliligi:
    """ṙ = a_ref·(Pc/Pc_ref)^n — [ṙ] = [a_ref] = L·T⁻¹, oran boyutsuz."""

    def test_hiz_katsayiyla_lineer(self):
        a = ThroatErosionModel(a_ref_mm_s=0.2)
        b = ThroatErosionModel(a_ref_mm_s=0.4)
        assert b.rate_mm_s(37.0) == pytest.approx(2.0 * a.rate_mm_s(37.0),
                                                  rel=1e-12)

    def test_basinc_orani_boyutsuz(self):
        """Pc ve Pc_ref birlikte ölçeklenirse hız DEĞİŞMEZ."""
        m1 = ThroatErosionModel(a_ref_mm_s=0.3, pc_ref_bar=70.0)
        m2 = ThroatErosionModel(a_ref_mm_s=0.3, pc_ref_bar=140.0)
        assert m1.rate_mm_s(40.0) == pytest.approx(m2.rate_mm_s(80.0),
                                                   rel=1e-12)

    def test_birim_donusumu_tutarli(self):
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_m_s(40e5) == pytest.approx(m.rate_mm_s(40.0) / 1000.0,
                                                 rel=1e-12)

    def test_capa_tasima_yasasi_modelin_kendi_yasasi(self):
        """Çapa taşıması, modelin rate_mm_s'iyle BİREBİR aynı olmalı."""
        olcum = ThroatErosionModel(a_ref_mm_s=BORIE_CC_MM_S,
                                   pc_ref_bar=BORIE_CC_PC_BAR)
        assert olcum.rate_mm_s(tb.THROAT_EROSION_PC_REF_BAR) == \
            pytest.approx(
                THROAT_EROSION_MATERIALS['carbon_carbon'][
                    'a_ref_anchor_mm_s'], rel=1e-12)


# ------------------------------------------------- ÜRÜN YÜZÜ · CAD --------
class TestCADLulePaneliCapayiIzler:
    """Yayımlanan tahmin bandın/çapanın kendisinden gelir."""

    @staticmethod
    def _est(secim):
        e = SolidRocketEngine(chamber_pressure=40,
                              overrides={'nozzle_material': secim})
        return e, _sessiz(e._design_nozzle_geometry)['performance'][
            'erosion_estimate']

    @pytest.mark.parametrize('secim', ('graphite', 'carbon_carbon', 'C-C'))
    def test_tahmin_kardes_modelle_ayrilamaz(self, secim):
        e, est = self._est(secim)
        kardes = _sessiz(e._nozzle_erosion_reference)
        assert est['rate_mm_s'] == pytest.approx(
            kardes.rate_mm_s(est['chamber_pressure_bar']), abs=1e-4)

    def test_grafit_tahmini_olculen_katsayidan_turer(self):
        """0,353·(40/70)^n = 0,2017 mm/s (D27'de 0,2256; tabanda 0,1598).

        ÖH D28 / OH-D27-15: üs elle '0,8' yazılıydı. Yayımlanan hız üssün
        tek tanım noktasını izler (n = 1,0 → 40 bar'da ölçek 0,5714).
        """
        _, est = self._est('graphite')
        beklenen = GEISLER_TABLO8_MM_S[1] * (
            40.0 / 70.0) ** tb.THROAT_EROSION_PRESSURE_EXPONENT
        assert est['rate_mm_s'] == pytest.approx(beklenen, abs=2e-4)
        assert est['rate_mm_s'] > 0.20

    def test_cc_tahmini_capadan_turer_ve_band_yayimlamaz(self):
        """0,19857·(40/70)^n = 0,1135 mm/s (D27'de 0,1182; tabanda 0,0639).

        ÖH D28 / OH-D27-15: üs elle '0,8' yazılıydı; künyeye bağlandı.
        """
        _, est = self._est('carbon_carbon')
        capa = THROAT_EROSION_MATERIALS['carbon_carbon']['a_ref_anchor_mm_s']
        assert est['rate_mm_s'] == pytest.approx(
            capa * (40.0 / 70.0) ** tb.THROAT_EROSION_PRESSURE_EXPONENT,
            abs=2e-4)
        assert est['band_mm_s'] is None, (
            'C-C için band yok; panelde band yayımlanamaz')
        assert est['anchor_attributed'] is True
        assert 'Borie' in (est['anchor_source'] or '')

    def test_kullanici_katsayisi_yolunda_da_capa_atfi_tasiniyor(self):
        e = SolidRocketEngine(
            chamber_pressure=40,
            overrides={'nozzle_material': 'carbon_carbon',
                       'throat_erosion_a_ref_mm_s': 0.20})
        d = _sessiz(e._throat_erosion_model).describe()
        assert d['a_ref_mm_s'] == pytest.approx(0.20)
        assert d['band_attributed'] is False and d['band_source'] is None
        assert d['anchor_attributed'] is True
        assert 'Borie' in d['anchor_source']


# ------------------------------------------------- LİTERATÜR NOTU ---------
class TestLiteraturNotuUrunleAyrismiyor:
    def test_notta_uygulama_bolumu_ve_sayilar_var(self):
        from pathlib import Path
        yol = (Path(tb.__file__).resolve().parents[2] / 'docs' / 'arastirma'
               / 'fizik' / 'bogaz-erozyonu-grafit-cc-bandi.md')
        assert kanit_gerekli(yol).is_file()
        m = kanit_gerekli(yol).read_text(encoding='utf-8')
        assert '6.2' in m and 'UYGULANDI' in m
        for parca in ('0,069', '0,353', '0,139', 'JANNAF', 'Borie'):
            assert parca in m, parca
        # Notun C-C ölçekleme hesabı yeniden üretilebiliyor. ÖH D28: not
        # artık İKİ sayı taşıyor — tarihsel (n = 0,8 → 0,185) ve güncel
        # (künyenin üssüyle). İkisi de burada çakılır.
        assert math.isclose(BORIE_CC_MM_S * (70.0 / 49.0) ** 0.8, 0.185,
                            abs_tol=5e-4)
        guncel = BORIE_CC_MM_S * (
            70.0 / 49.0) ** tb.THROAT_EROSION_PRESSURE_EXPONENT
        assert f'{guncel:.4f}'.replace('.', ',') in m, (
            'not, ürünün güncel C-C çapasını anmıyor')


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
