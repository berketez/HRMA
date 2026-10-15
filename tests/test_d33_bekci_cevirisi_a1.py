# -*- coding: utf-8 -*-
"""ÖH D33-KOLAY · kulvar ``bekci-cevirisi`` · aşama 1/1 — eksen bekçileri.

Bu dosyanın tek kalemi **P14M2-12**'dir (RET, yeniden açık). Kulvarın
öteki yedi kalemi mevcut bekçilerin GÜÇLENDİRİLMESİdir ve onarımları kendi
dosyalarında durur (aşağıdaki "kulvar haritası"); burada yeni bir bekçi
ailesi doğuyor, çünkü kusur bir bekçinin zaafı değil, bir bekçinin
YOKLUĞUdur.

Ölçüm gövdesi ``docs/scofield/raw/OH/D33/bekci-cevirisi/a1/olcum.py``
(``once.json`` ⟷ ``sonra.json``), ters-mutasyon kanıtı ``mutasyon.json``.

Kulvar haritası (onarımın nerede durduğu):
  P14M2-12   BU DOSYA — eksen merdiveni bekçileri
  P7B1-10    tests/test_d22_app_api_a1.py (denetim ŞARTI)
  P7B2-13    tests/test_d29_app_api_uc_a3.py (denetim ŞARTI)
  OH-UC-08   tests/test_d24_sivi_a1.py
  OH-D19-29  tests/test_i18n_common.py (A yarısı, kapsam: tek aile)
  OH-UC-16   tests/test_d29_arayuz_panel_a2.py
  OH-UC-18   tests/test_d23_altyapi_a2.py
  OH-UC-19   tests/test_viz3d_render_kalite.py (yorum ayıklayıcısı)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from hrma.analysis.safety_analysis import (
    SafetyAnalyzer,
    THERMAL_VERDICT_WITHHELD,
)

KOK = Path(__file__).resolve().parents[1]
GUVENLIK_PY = KOK / 'hrma' / 'analysis' / 'safety_analysis.py'


@pytest.fixture(scope='module')
def coz():
    return SafetyAnalyzer()


def _fonksiyon_kaynagi(metin: str, ad: str) -> str:
    """Kaynağı DOSYADAN, AST ile çıkarır (``inspect.getsource`` kaymaz)."""
    agac = ast.parse(metin)
    satirlar = metin.splitlines()
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == ad:
            return '\n'.join(satirlar[d.lineno - 1:d.end_lineno])
    return ''


# ===========================================================================
# P14M2-12 — termal ve yangın eksenleri 1,0'a DÜZLEŞTİRİLEBİLİYORDU
# ===========================================================================
#
# DEFTER DURUMU: RET (yeniden açık). ihracat kulvarının "bu mutasyon artık
# kırmızı" iddiası denetimde ölçümle çürütüldü.
#
# ÖLÇÜLDÜ (a1/once.json P14M2-12, taban 56f88e70):
#
#   fire   merdiven basamakları: 2,0 · 3,0 · 4,0  -> çivilenen: 2,0 · 3,0
#   thermal merdiven basamakları: 2,0 · 3,0 · 4,0 · 5,0 -> çivilenen: YOK
#   çivilenmeyen basamak sayısı: 5
#
# Yani ``_score_thermal_risk`` deponun HİÇBİR testi tarafından değeriyle
# sorulmuyordu; ``_score_fire_risk``in de yalnız iki basamağı çivilenmişti
# (``tests/test_d15_yapisal_sistem_a3.py``). P14'ün mutasyonu (soğutma şart
# iken 4,0 -> 1,0; her tutuşma sınıfı -> 1,0) bu yüzden kaçıyordu.
#
# Bandın kendisi (``1.0 <= risk <= 5.0``,
# ``test_analysis_dock_contract.py::test_individual_risks_in_band``) bu
# mutasyonu YAPISAL OLARAK göremez: 1,0 bandın alt ucudur. Saçılım iddiası
# da göremez — tek ekseni 1,0'a çakmak kalan beş ekseni birbirinden farklı
# bırakır, ``max(değerler) > min(değerler)`` yine doğrudur. Bir eksenin
# kendi değerini SORAN bir bekçi gerekiyordu; işte o bekçiler.
#
# Aşağıdaki iddialar SKOR ÇIKTILARIDIR (merdivenin kendisi), eşik değil;
# eşikler üründen okunur (``safety_margins.temperature_safety_factor``,
# ``material_melting_point_k``) ve burada YENİDEN YAZILMAZ.


class TestP14M212TermalEkseniMerdiveni:
    """``_score_thermal_risk`` her basamağı ayrı bir sayı döndürür."""

    @staticmethod
    def _taban(**ek):
        """Merdivenin en alt basamağına düşen sağlıklı girdi."""
        gv = {'estimated_wall_temperature_k': 800.0,
              'material_melting_point_k': 1705.0,
              'material_thermal_safety_factor': 2.0}
        gv.update(ek)
        return gv

    def test_saglikli_cidar_en_alt_basamak(self, coz):
        assert coz._score_thermal_risk(self._taban()) == 2.0

    def test_isil_koruma_gerekirse_yukselir(self, coz):
        assert coz._score_thermal_risk(
            self._taban(thermal_protection_required=True)) == 3.0

    def test_servis_siniri_asilirsa_dorde_cikar(self, coz):
        """Seçilen malzemenin katsayısı 1'in altında: dayanım geçersiz."""
        assert coz._score_thermal_risk(
            self._taban(material_thermal_safety_factor=0.8)) == 4.0

    def test_emniyet_payinin_altinda_da_dorde_cikar(self, coz):
        """Eşik üründen okunur; burada yeniden yazılmaz."""
        pay = coz.safety_margins.temperature_safety_factor
        assert coz._score_thermal_risk(
            self._taban(material_thermal_safety_factor=pay - 0.05)) == 4.0
        assert coz._score_thermal_risk(
            self._taban(material_thermal_safety_factor=pay + 0.05)) == 2.0

    def test_sogutma_sart_dali_eski_yolu_korur(self, coz):
        """Katsayı YOKKEN eski ``cooling_required`` dalı hâlâ 4,0 verir."""
        gv = {'estimated_wall_temperature_k': 800.0,
              'material_melting_point_k': 1705.0,
              'cooling_required': True}
        assert coz._score_thermal_risk(gv) == 4.0

    def test_erime_noktasinda_bese_cikar(self, coz):
        assert coz._score_thermal_risk(self._taban(
            estimated_wall_temperature_k=1800.0)) == 5.0

    def test_isil_gerilme_akitiyorsa_bese_cikar(self, coz):
        assert coz._score_thermal_risk(self._taban(
            thermal_stress_safety_factor=0.9)) == 5.0

    def test_olculemeyen_eksen_sayi_uydurmaz(self, coz):
        """Fail-closed: hesap yoksa DÜŞÜK RİSK değil, ``None``."""
        assert coz._score_thermal_risk({}) is None
        assert coz._score_thermal_risk(
            {'thermal_verdict': THERMAL_VERDICT_WITHHELD}) is None
        assert coz._score_thermal_risk(
            self._taban(estimated_wall_temperature_k='sicak')) is None

    def test_eksen_duzlesemez(self, coz):
        """P14'ün MUTASYONUNUN doğrudan panzehiri.

        Merdivenin her basamağı ayrı bir sayı vermeli. Gövde tek bir sabite
        (ör. 1,0) çakılırsa bu küme tek elemana düşer ve test kırmızı olur.
        """
        degerler = {
            coz._score_thermal_risk(self._taban()),
            coz._score_thermal_risk(
                self._taban(thermal_protection_required=True)),
            coz._score_thermal_risk(
                self._taban(material_thermal_safety_factor=0.8)),
            coz._score_thermal_risk(
                self._taban(estimated_wall_temperature_k=1800.0)),
        }
        assert len(degerler) == 4, (
            'termal eksen dört ayrı koşulda %d ayrı değer üretiyor (%s) — '
            'merdiven düzleşmiş' % (len(degerler), sorted(degerler)))
        assert min(degerler) >= 2.0, (
            'termal eksen bandın ALT ucuna (1,0) düşürülmüş: bu, eriyen bir '
            'cidarı "en düşük risk" ilan etmektir (P14M2-12 mutasyonu)')


class TestP14M212YanginEkseniMerdiveni:
    """``_score_fire_risk`` tutuşma sınıfına göre AYRIŞIR."""

    @staticmethod
    def _tehlike(seviye):
        return {'auto_ignition_risk': {'risk_level': seviye}}

    @pytest.mark.parametrize('seviye,beklenen', [
        ('LOW', 2.0), ('MEDIUM', 3.0), ('HIGH', 4.0),
    ])
    def test_merdiven_basamaklari(self, coz, seviye, beklenen):
        """``HIGH -> 4,0`` basamağı tabanda HİÇBİR bekçide çivili değildi."""
        assert coz._score_fire_risk(self._tehlike(seviye)) == beklenen

    def test_eksen_duzlesemez(self, coz):
        degerler = {coz._score_fire_risk(self._tehlike(s))
                    for s in ('LOW', 'MEDIUM', 'HIGH')}
        assert len(degerler) == 3, (
            'yangın ekseni üç tutuşma sınıfında %d ayrı değer üretiyor (%s) '
            '— merdiven düzleşmiş (P14M2-12)' % (len(degerler),
                                                 sorted(degerler)))
        assert min(degerler) >= 2.0, (
            'yangın ekseni bandın ALT ucuna (1,0) düşürülmüş; 1,0 "tehlike '
            'yok" demektir ve hiçbir tutuşma sınıfı bunu hak etmez')

    def test_yuksek_tutusma_dusuk_siniftan_agirdir(self, coz):
        """Sıralama iddiası: eksen monoton artmalı."""
        dusuk = coz._score_fire_risk(self._tehlike('LOW'))
        orta = coz._score_fire_risk(self._tehlike('MEDIUM'))
        yuksek = coz._score_fire_risk(self._tehlike('HIGH'))
        assert dusuk < orta < yuksek


class TestP14M212BandIddiasiTekBasinaYETMEZ:
    """Kalemin KÖK sebebi kayıt altına alınır: bant körlüğü yapısaldır.

    Bu sınıf ürünü değil, ÖLÇÜTÜ sınar. ``1.0 <= risk <= 5.0`` bandının
    neden yetmediği burada sayıyla durur, böylece bir gün "bant zaten
    kontrol ediyor" denip eksen bekçileri sökülemez.
    """

    def test_bant_iddiasi_duzlesmis_ekseni_gecirir(self):
        """Düzleştirilmiş bir eksen bandı GEÇER — mutasyonun kaçış yolu."""
        duzlesmis = 1.0
        assert 1.0 <= duzlesmis <= 5.0, 'bandın alt ucu 1,0'

    def test_sacilim_iddiasi_TEK_ekseni_kurtarmaz(self):
        """Saçılım iddiası altı eksenin hepsi çökmedikçe kırmızı vermez.

        Ölçülen taban (a2 kaydı): explosive 3,0 · fire 2,0 · pressure 2,0 ·
        structural 1,0 · thermal 2,0 · toxic 1,0. Yangın ekseni 1,0'a
        çakılsa saçılım hâlâ vardır; ``max > min`` doğrudur.
        """
        taban = {'explosive': 3.0, 'fire': 2.0, 'pressure': 2.0,
                 'structural': 1.0, 'thermal': 2.0, 'toxic': 1.0}
        mutasyonlu = dict(taban, fire=1.0, thermal=1.0)
        d = list(mutasyonlu.values())
        assert max(d) > min(d), (
            'iki eksen 1,0\'a çakılmış olmasına rağmen saçılım iddiası '
            'GEÇİYOR — bu, eksen bekçilerinin neden gerektiğinin kanıtıdır')
        assert max(d) == max(taban.values()), (
            'genel skor (en kötü eksen) da değişmiyor: mutasyon toplama '
            'kuralına bile görünmüyor')

    def test_eksenler_bekcisiz_kalmasin(self):
        """Merdivenin her basamağı bu dosyada adıyla isteniyor mu?

        Ürün yeni bir basamak eklerse (ör. yangın eksenine 5,0) bu bekçi
        kırmızıya döner ve basamağın çivilenmesini ister — kalem yeniden
        açılmasın diye.
        """
        metin = GUVENLIK_PY.read_text(encoding='utf-8')
        bu_dosya = Path(__file__).read_text(encoding='utf-8')
        for ad in ('_score_fire_risk', '_score_thermal_risk'):
            govde = _fonksiyon_kaynagi(metin, ad)
            assert govde, '%s kayıp' % ad
            basamaklar = set(re.findall(r'return\s+([\d.]+)', govde))
            civilenmeyen = sorted(
                b for b in basamaklar
                if not re.search(r'==\s*%s\b' % re.escape(b), bu_dosya)
                and not re.search(r',\s*%s\)' % re.escape(b), bu_dosya))
            assert not civilenmeyen, (
                '%s merdiveninde çivilenmemiş basamak: %s — eksen bekçisine '
                'eklenmeli (P14M2-12)' % (ad, civilenmeyen))


# ===========================================================================
# ÖH D33-3 (parti D33-3, aşama 1/1) — ÇEVRİLEN BEKÇİLERİN ÇEVRİLİ KALMASI
# ===========================================================================
# Bu bölümün konusu ürün değil BEKÇİDİR: üç bekçi çevrildi ve çevrilmiş
# hâllerinin sessizce eski hâline dönmemesi burada kilitlenir. Ölçüm gövdesi
# ``docs/scofield/raw/OH/D33-3/bekci-cevirisi/a1/olcum.py``
# (``once.json`` ⟷ ``sonra.json``), ters-mutasyon kanıtları ``mutasyon.json``
# ve ``mutasyon_ohd3332.json``.
#
# Kulvar haritası (onarımın nerede durduğu):
#   OH-D33-18  tests/test_d30_app_api_uc_a1.py — SALT METİN -> DAVRANIŞ
#   OH-D33-19  tests/test_d30_app_api_uc_a1.py — kusuru koruyan kilit söküldü
#   OH-D33-32  tests/test_i18n_common.py       — kapsam şablonlara genişledi
D30_UC = KOK / 'tests' / 'test_d30_app_api_uc_a1.py'
I18N_ORTAK = KOK / 'tests' / 'test_i18n_common.py'


def _sinif_kaynagi(metin: str, ad: str) -> str:
    """Bir sınıfın gövdesini AST konumlarıyla keser (yorum kayması yok)."""
    agac = ast.parse(metin)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.ClassDef) and dugum.name == ad:
            return ast.get_source_segment(metin, dugum) or ''
    raise AssertionError('sınıf bulunamadı: %s' % ad)


def _govde_docstringsiz(dugum) -> str:
    """Bir fonksiyonun ÇALIŞAN gövdesi — künye metni ölçüme karışmasın.

    Künye, çevrilen bekçinin ESKİ iddiasını alıntılamak zorundadır (kanıt
    orada durur); bu yüzden "eski iddia kalmadı" ölçütü yalnız yürütülen
    satırlara bakar. Aksi hâlde bekçi kendi künyesini kusur sanardı.
    """
    govde = [u for u in dugum.body
             if not (isinstance(u, ast.Expr)
                     and isinstance(u.value, ast.Constant)
                     and isinstance(u.value.value, str))]
    return '\n'.join(ast.unparse(u) for u in govde)


class TestOHD3318DavranisBekcisi:
    """ÖLÇÜLDÜ (``a1/once.json`` K1, taban ``fa7c4e1d``):
    ``TestOHD2813DeltaPKaynagi`` sınıfının 2 testinin 2'si ``hrma/app.py``
    KAYNAK METNİNDE dize arıyordu, 0'ı istek atıyordu; ``delta_P_source``
    adı ``tests/`` ağacının TAMAMINDA 1 kez geçiyordu. Ters-mutasyon M1
    (``mutasyon.json``): ``request_echo`` dalı yanlış adla yayımlandığında
    eski iki iddianın İKİSİ de YEŞİL kalıyor — bekçi kusuru göremiyordu.
    """

    SINIF = 'TestOHD2813DeltaPKaynagi'

    @classmethod
    def _testler(cls):
        metin = D30_UC.read_text(encoding='utf-8')
        agac = ast.parse(metin)
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.ClassDef) and dugum.name == cls.SINIF:
                return {u.name: _govde_docstringsiz(u)
                        for u in dugum.body
                        if isinstance(u, (ast.FunctionDef,
                                          ast.AsyncFunctionDef))
                        and u.name.startswith('test_')}
        raise AssertionError('sınıf bulunamadı: %s' % cls.SINIF)

    def test_her_test_urunu_CALISTIRIR(self):
        """Salt metin okuyan tek bir test bile kalmamalı."""
        salt_metin = [ad for ad, govde in self._testler().items()
                      if not ('istemci.post' in govde or 'istemci.get' in govde
                              or 'self._rapor(' in govde
                              or 'self._plaka(' in govde)]
        assert not salt_metin, (
            'ΔP kaynağı bekçisinde SALT METİN testi kaldı: %s — kusurun asıl '
            'dalı (istek yankısı) yine örtüsüz kalır' % salt_metin)

    def test_uc_dal_da_adiyla_olculur(self):
        """``injector_solution`` / ``request_echo`` / ``unavailable``."""
        govde = ''.join(self._testler().values())
        for dal in ('injector_solution', 'request_echo', 'unavailable'):
            assert "'%s'" % dal in govde, dal

    def test_falsy_tuzagi_ADIYLA_beyan_edildi(self):
        """Artakalan kusur künyede ADIYLA duruyor (sessiz devir yok)."""
        kaynak = _sinif_kaynagi(D30_UC.read_text(encoding='utf-8'), self.SINIF)
        assert 'falsy' in kaynak.lower(), (
            'ΔP tam 0,0 tuzağı künyede geçmiyor — devredilen kusur adsız '
            'kalırsa kaybolur')
        assert 'app-api-kapilar' in kaynak, (
            'devrin ADRESİ yazılmamış (onarım hangi kulvarın sahası?)')

    def test_tuzak_DONDURULMADI(self):
        """Devredilen kusuru sözleşmeye çeviren bir iddia OLMAMALI."""
        govde = ''.join(self._testler().values())
        assert "'pressure_drop': 0.0" not in govde, (
            'bekçi ΔP=0,0 tuzağının BUGÜNKÜ davranışını kilitliyor; '
            'onarım geldiğinde haksız kırmızı verir (Doktrin 1)')


class TestOHD3319KilitSokuldu:
    """ÖLÇÜLDÜ (``a1/once.json`` K2): ``test_ohd2908_fin_count_butceye_
    carpmiyor`` iki iddia taşıyordu ve biri ``r.status_code == 200`` idi —
    yani ÇÜRÜTÜLEN iddianın ekseni (süre/bütçe, 503/60 s) değil, "1e6 kanat
    KABUL EDİLİR" hükmü donduruluyordu. Ters-mutasyon M3: uca ADLI bir
    ``fin_count`` kapısı (400 + ``invalid_fields``) eklendiğinde eski iddia
    KIRMIZI, yeni bekçi YEŞİL; M4: 503 duvar saati geri geldiğinde yeni
    bekçi KIRMIZI. Kilit söküldü, eksen ayakta.
    """

    AD = 'test_ohd2908_fin_count_butceye_carpmiyor'

    @classmethod
    def _govde(cls):
        agac = ast.parse(D30_UC.read_text(encoding='utf-8'))
        for dugum in ast.walk(agac):
            if (isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and dugum.name == cls.AD):
                return _govde_docstringsiz(dugum)
        raise AssertionError('test bulunamadı: %s' % cls.AD)

    def test_durum_kodu_DONDURULMUYOR(self):
        govde = self._govde()
        assert 'r.status_code == 200' not in govde, (
            'kusuru koruyan kilit geri geldi: bekçi 1e6 kanadın KABUL '
            'edilmesini şart koşuyor, oysa çürütülen iddia süre eksenindeydi')

    def test_sure_ekseni_AYAKTA(self):
        govde = self._govde()
        assert 'monotonic' in govde and '30.0' in govde, govde
        for kod in ('503', '504'):
            assert kod in govde, (
                'duvar saati reddi (%s) ölçülmüyor — çürütülen iddia geri '
                'gelirse bekçi görmez' % kod)

    def test_adsiz_red_kabul_edilmiyor(self):
        """4xx serbest ama ADSIZ olamaz (fail-closed)."""
        govde = self._govde()
        assert 'invalid_fields' in govde and "'fin_count'" in govde, govde


class TestOHD3332KapsamGenisledi:
    """ÖLÇÜLDÜ (``a1/once.json`` K3, hem bu ağaçta hem ortak taban ağacında):
    ``test_every_used_key_exists_in_dictionary`` yalnız ``hrma/static/js``
    altını tarıyordu; sekiz şablonun ``data-i18n`` ile çağırdığı 1.915
    anahtar kapsam dışıydı ve bunların 5'inin hiçbir sözlükte karşılığı
    yoktu (TR kullanıcı beş "model farkı" notunu İngilizce okuyor).
    Ters-mutasyon M5: sözlüksüz bir şablon anahtarı ESKİ kapsamda
    görünmüyor (``eski_kapsamda: false``), YENİ kapsamda görünüyor ve bekçi
    KIRMIZI veriyor; M6: borç ödendiğinde envanter bekçisi KIRMIZI veriyor.
    """

    @staticmethod
    def _modul():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'd33_3_i18n_ortak', I18N_ORTAK)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return modul

    def test_sablon_data_i18n_kapsamda(self):
        m = self._modul()
        assert len(m.SABLON_DATA_I18N) > 1500, len(m.SABLON_DATA_I18N)
        assert set(m.USED) <= set(m.KULLANIM)
        assert set(m.SABLON_DATA_I18N) <= set(m.KULLANIM)

    def test_borc_ONEK_ailesi_degil_TAM_KUME(self):
        """Borç bir ön ek ailesi olarak açılmadı (D27 dersi korunuyor)."""
        m = self._modul()
        assert m.CEVIRI_BORCU_AILELERI == (), m.CEVIRI_BORCU_AILELERI
        assert isinstance(m.SABLON_CEVIRI_BORCU, tuple)
        for ad in m.SABLON_CEVIRI_BORCU:
            assert ad.count('.') >= 2 and not ad.endswith('.'), (
                '%r bir ön ek gibi duruyor; borç TAM ADLA sayılır' % ad)

    def test_borc_envanteri_ISLEK(self):
        """Envanter bugünkü ölçümle birebir (ne büyüme ne bayat kayıt)."""
        m = self._modul()
        assert set(m._sablon_kapsam_borcu()) == set(m.SABLON_CEVIRI_BORCU), (
            set(m._sablon_kapsam_borcu()) ^ set(m.SABLON_CEVIRI_BORCU))

    def test_olu_ceviri_bekcisinin_olcutu_DEGISMEDI(self):
        """Kapsam KULLANIMI büyüttü, sözlüğü değil — vakumlama yok."""
        kaynak = I18N_ORTAK.read_text(encoding='utf-8')
        govde = _fonksiyon_kaynagi(kaynak, 'test_every_dictionary_key_is_used')
        assert 'k not in USED' in govde and 'SABLON_KULLANIMI' in govde, govde
        assert 'KULLANIM)' not in govde, (
            'ölü çeviri bekçisi genişletilmiş kapsama bağlanmış — ölçütü '
            'gevşer (ÖK-22)')
