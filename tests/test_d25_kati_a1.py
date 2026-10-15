"""ÖH Dalga-25 · kulvar KATI · aşama 1 bekçileri.

Kapsanan kalemler
-----------------
P15B2-09  (Fable-D18 ŞARTI, KATI yarısı) Kapak/flanş cıvata birleşiminin
          varsayılan sözleşmesi katı motorda LİTERAL sözlük olarak
          yazılıydı; hibrit (D18) ve sıvı (D24) kopyaları çoktan
          ``hrma.analysis.bolted_joint``tan türetilmişti. Ölçüldü
          (once_p15b2_09.json, taban cdf2106): literal 1 / türetilmiş 2.

OH-D23-14 (D24 devir) ``/calculate_solid`` yanıtında itki eğrisi İKİ KEZ
          seriliyordu: üst seviyede ve ``motor_geometry`` bloğunda,
          sha256'ları aynı 37.521 bayt (313.020 baytlık yanıtın %11,99'u).

P2B4-09   (Fable-D19 ŞARTI) Kullanıcının kendi erozyon katsayısını verdiği
          yolda bandın künyesi/atıf durumu taşınıyordu ama BEKÇİSİZDİ —
          Fable'ın M3 mutasyonu (``band_attributed=False``) üç dosyada
          34 passed üretti, tek kırmızı yok.

OH-D24-11 (a) Rijit-boğaz uyarısının AYIRT EDİCİLİĞİ; (c) grafit bandının
          literatür notu.
"""
import ast
import contextlib
import io
import json
import math
import pathlib
import re

import pytest

from hrma.analysis import bolted_joint
from hrma.analysis import transient_ballistics as tb
from hrma.engines.solid_rocket_engine import (
    SolidRocketEngine, THROAT_EROSION_SIGNIFICANT_AREA_GROWTH)
from hrma.export import motor_geometry as mg
from hrma.export.openrocket_integration import (
    OpenRocketExporter, _thrust_curve_label)
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
KATI_KAYNAK = KOK / 'hrma' / 'engines' / 'solid_rocket_engine.py'


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def _motor(**ek):
    kw = dict(grain_type='bates', propellant_type='apcp',
              chamber_diameter=100, grain_length=500,
              core_diameter=30, chamber_pressure=40)
    kw.update(ek)
    return _sessiz(SolidRocketEngine, **kw)


@pytest.fixture(scope='module')
def kati_sonuc():
    return _sessiz(_motor().calculate_performance)


# -------------------------------------------------------------- P15B2-09 --
class TestP15B209KapakBirlesimiTuretilmis:
    """ŞART: katı kopyası da ``bolted_joint``tan türetilmiş olmalı."""

    def test_deger_tek_kaynaktan_gelir(self):
        d = SolidRocketEngine.SOLID_CLOSURE_JOINT_DEFAULTS
        ref = bolted_joint.CLOSURE_JOINT_DEFAULTS
        assert set(d) == set(ref), (
            'katı kopyası ortak sözleşmenin alan kümesinden ayrılmış')
        for k in ref:
            assert d[k] is ref[k], (
                f"'{k}' yeniden yazılmış: türetme kopyası değerin KENDİSİNİ "
                'taşımalı (eşitlik değil kimlik)')

    def test_uye_malzemesi_BILEREK_yok(self):
        """D15 / P2B2-12: üye malzemesi kasadan türetilir, buradan DEĞİL."""
        d = SolidRocketEngine.SOLID_CLOSURE_JOINT_DEFAULTS
        assert 'member_material' not in d, (
            'katı motorda üye malzemesi varsayılanı olmamalı: sessizce '
            'alüminyuma düşmek D15/P2B2-12 ile yasaklandı')

    def test_atama_literal_dict_degil(self):
        """AST: ŞARTIN asıl iddiası — sözleşme burada YAZILI olmamalı."""
        agac = ast.parse(KATI_KAYNAK.read_text(encoding='utf-8'))
        bulundu = [n.value for n in ast.walk(agac)
                   if isinstance(n, ast.Assign)
                   for t in n.targets
                   if getattr(t, 'id', None) == 'SOLID_CLOSURE_JOINT_DEFAULTS']
        assert len(bulundu) == 1, 'tek atama olmalı'
        assert not isinstance(bulundu[0], ast.Dict), (
            'SOLID_CLOSURE_JOINT_DEFAULTS literal sözlüğe geri döndü; '
            "sözleşme hrma.analysis.bolted_joint'te tek kez yazılır")
        assert isinstance(bulundu[0], ast.Call)

    def test_cıvata_sayisi_bandi_ikinci_kez_yazilmamis(self):
        """``bolt_count_range`` yalnız ortak modülde tanımlı olmalı."""
        metin = KATI_KAYNAK.read_text(encoding='utf-8')
        suclu = [ln.strip() for ln in metin.split('\n')
                 if re.search(r"'bolt_count_range'\s*:", ln)
                 and not ln.lstrip().startswith('#')]
        assert not suclu, f'katı motorda ikinci band tanımı: {suclu}'


# -------------------------------------------------------------- OH-D23-14 --
class TestOHD2314EgriYinelenmiyor:
    """Blok eğriyi TAŞIR ama çözücü sözlüğünü olduğu gibi yinelemez."""

    def test_blok_yalniz_ihracatin_okudugu_alanlari_tasir(self, kati_sonuc):
        geo = mg.solid_results_to_motor_geometry(kati_sonuc)
        tam = kati_sonuc.get('thrust_curve') or {}
        assert tam, 'çözücü zaman-çözümlü eğri yayımlamıyor'
        blok = geo.get('thrust_curve')
        assert isinstance(blok, dict) and blok, (
            'eğri bloktan tamamen düşürülmüş: paket .eng\'i sabit itkiye '
            'iner (P15B4-06 gerilemesi)')
        fazla = set(blok) - set(mg.THRUST_CURVE_EXPORT_FIELDS)
        assert not fazla, (
            f'ihracatın okumadığı alanlar blokta yineleniyor: {sorted(fazla)}')
        # Yineleme gerçekten küçüldü mü? (ölçüm: 37.521 -> 11.695 bayt)
        b_tam = len(json.dumps(tam, default=str))
        b_blok = len(json.dumps(blok, default=str))
        assert b_blok < b_tam / 2.0, (
            f'blok ({b_blok} B) çözücü sözlüğünün ({b_tam} B) yarısından '
            'küçük olmalı; kör kopya geri gelmiş olabilir')

    def test_ihracat_sozlesmesi_BIT_AYNI(self, kati_sonuc):
        """İzdüşüm, tam sözlükle AYNI .eng'i üretmeli — bilgi kaybı yok."""
        geo = mg.solid_results_to_motor_geometry(kati_sonuc)
        ex = OpenRocketExporter()
        n_tam, k_tam = _sessiz(ex.resolve_thrust_curve, kati_sonuc)
        n_blok, k_blok = _sessiz(ex.resolve_thrust_curve, geo)
        assert len(n_tam) > 4, 'ham sonuç zaman-çözümlü eğri vermiyor'
        assert k_blok == k_tam == 'thrust_curve'
        assert n_blok == n_tam, (
            'izdüşüm ihracat noktalarını değiştirdi: sözleşme bozuldu')
        # Etiket de eğrinin kendi ``basis`` beyanından gelir.
        assert (_thrust_curve_label(geo['thrust_curve'])
                == _thrust_curve_label(kati_sonuc['thrust_curve']))

    def test_egri_dusurulurse_paket_sabit_itkiye_iner(self, kati_sonuc):
        """Kalemin önerdiği çarenin ÖLÇÜLEN zararı — çare uygulanmadı."""
        geo = mg.solid_results_to_motor_geometry(kati_sonuc)
        egrisiz = {k: v for k, v in geo.items()
                   if k not in ('thrust_curve', 'transient')}
        ex = OpenRocketExporter()
        n_yok, k_yok = _sessiz(ex.resolve_thrust_curve, egrisiz)
        assert k_yok == 'constant' and len(n_yok) == 4, (
            'bu bekçi, eğriyi bloktan düşürmenin neye mal olduğunu kilitler')

    def test_tuketici_kumesi_daralmadi(self, kati_sonuc):
        """``THRUST_CURVE_EXPORT_FIELDS`` gerçekten YETİYOR mu?

        Küme bir kısaltma listesi değil, ÖLÇÜLMÜŞ tüketici kümesidir:
        izdüşümden çıkarılan her alan .eng'i değiştirmemelidir.
        """
        tam = kati_sonuc['thrust_curve']
        izdusum = {a: tam[a] for a in mg.THRUST_CURVE_EXPORT_FIELDS
                   if a in tam}
        ex = OpenRocketExporter()
        assert (_sessiz(ex.resolve_thrust_curve, {'thrust_curve': izdusum})
                == _sessiz(ex.resolve_thrust_curve,
                           {'thrust_curve': tam}))


# --------------------------------------------------------------- P2B4-09 --
class TestP2B409KullaniciKatsayisiYolu:
    """ŞART (1): kullanıcı kendi a_ref'ini verse de bandın ATFI taşınır.

    Fable-D19 ölçümü: bu yol BEKÇİSİZDİ (M3 mutasyonu 34 passed / 0 failed).

    Not (ölçüldü, D25): ŞART metni bu sözlüğü ``calculate_performance()``
    YANITINDA arıyordu; yanıtta böyle bir alan YOK — ``throat_erosion``
    bloğu çözücünün İÇ eğri sözlüğünde kalıyor, yayımlanan ``thrust_curve``
    onu taşımıyor (bu, M3'ün neden hiç kırmızı bulamadığının da cevabıdır).
    Bekçi bu yüzden ULAŞILABİLİR model sözlüğüne bağlanır:
    ``_throat_erosion_model().describe()`` — aynı sözlük ``throat_erosion``
    raporunun ``basis`` alanına da olduğu gibi girer.
    """

    def test_grafitte_atif_tasinir(self):
        m = _motor(overrides={'nozzle_material': 'graphite',
                              'throat_erosion_a_ref_mm_s': 0.20})
        d = _sessiz(m._throat_erosion_model).describe()
        assert d['a_ref_mm_s'] == pytest.approx(0.20), (
            'kullanıcı katsayısı yola girmemiş')
        assert d['band_attributed'] is True
        assert d['band_source'] == tb.GRAPHITE_A_REF_BAND_CITATION

    def test_karbon_karbonda_atif_YOK_diye_beyan_edilir(self):
        m = _motor(overrides={'nozzle_material': 'carbon_carbon',
                              'throat_erosion_a_ref_mm_s': 0.20})
        d = _sessiz(m._throat_erosion_model).describe()
        assert d['material'] == 'carbon_carbon'
        assert d['band_attributed'] is False
        assert d['band_source'] is None, (
            'C-C bandı depo-içi kestirimdir; atfedilmiş gibi gösterilemez')

    def test_bandi_olmayan_malzemede_atif_uydurulmaz(self):
        """Yayımlanmış bandı olmayan malzemede band_attributed False."""
        m = _motor(overrides={'nozzle_material': 'steel',
                              'throat_erosion_a_ref_mm_s': 0.20})
        d = _sessiz(m._throat_erosion_model).describe()
        assert d['band_attributed'] is False
        assert d['a_ref_band_mm_s'] is None
        assert d['material'] == 'user_supplied'

    def test_rapor_basisi_ayni_sozlugu_tasir(self):
        """``throat_erosion.basis`` = modelin kendi ``describe()``ı."""
        m = _motor(overrides={'nozzle_material': 'graphite',
                              'throat_erosion_a_ref_mm_s': 0.20})
        model = _sessiz(m._throat_erosion_model)
        rapor = _sessiz(m._throat_erosion_report, model, 3.0e-4, 3.2e-4)
        assert rapor['enabled'] is True
        assert rapor['basis']['band_attributed'] is True
        assert rapor['basis']['band_source'] == tb.GRAPHITE_A_REF_BAND_CITATION


# -------------------------------------------------------- OH-D24-11 (a) --
class TestOHD2411UyariAyirtEdiyor:
    """Rijit-boğaz uyarısı ANCAK VE ANCAK kestirim eşiği aşınca çıkar.

    Fable-D19 bulgusu 'ölçülen 6 BATES motorunun 6'sında ateşliyor — uyarı
    ayırt etmiyor' demişti. ÖLÇÜLDÜ (once_ohd2411.json, taban cdf2106):
    o altı motor eşiğin TEK YANINDA (küçük boğaz) kalmıştı. Boğaz çapı ve
    yanma süresi eşiğin iki yanına taşınınca 8 motorun 3'ünde uyarı çıkıyor,
    5'inde çıkmıyor ve kural 8/8 tutuyor.
    """

    ATESLEYEN = dict(chamber_diameter=50, core_diameter=15, grain_length=200)
    SESSIZ = dict(chamber_diameter=300, core_diameter=270, grain_length=1000)

    @staticmethod
    def _kestirim(m, r):
        """Modelin KENDİ kestirimi — üründen bağımsız yeniden hesap."""
        ref = _sessiz(m._nozzle_erosion_reference)
        assert ref is not None
        egri = r.get('thrust_curve') or {}
        p = egri.get('pressure') or []
        p_ort = (sum(map(float, p)) / len(p)) if p else float(m.P_c)
        t_b = float(r['burn_time'])
        r0 = float(r['throat_diameter']) / 2.0          # mm
        return ((r0 + ref.rate_mm_s(p_ort) * t_b) / r0) ** 2 - 1.0

    @staticmethod
    def _uyarilar(r):
        return [w for w in (r.get('design_warnings') or [])
                if w['code'] == 'warn.solid.rigid_throat_assumption']

    @pytest.mark.parametrize('ad,geo', [('atesleyen', ATESLEYEN),
                                        ('sessiz', SESSIZ)])
    def test_kural_iki_yonlu_tutuyor(self, ad, geo):
        m = _motor(**geo)
        r = _sessiz(m.calculate_performance)
        kestirim = self._kestirim(m, r)
        uyari = bool(self._uyarilar(r))
        assert uyari == (kestirim > THROAT_EROSION_SIGNIFICANT_AREA_GROWTH), (
            f'{ad}: kestirim %{kestirim * 100:.2f}, eşik '
            f'%{THROAT_EROSION_SIGNIFICANT_AREA_GROWTH * 100:.1f}, '
            f'uyarı={uyari} — uyarı modelin kendi kestirimini izlemiyor')

    def test_uyari_ayirt_ediyor(self):
        """İki motor AYNI cevabı vermemeli: uyarı ölü bir bayrak değil."""
        r_a = _sessiz(_motor(**self.ATESLEYEN).calculate_performance)
        r_s = _sessiz(_motor(**self.SESSIZ).calculate_performance)
        assert bool(self._uyarilar(r_a)) is True
        assert bool(self._uyarilar(r_s)) is False

    def test_yayimlanan_yuk_kendi_icinde_tutarli(self):
        m = _motor(**self.ATESLEYEN)
        r = _sessiz(m.calculate_performance)
        p = self._uyarilar(r)[0]['params']
        r0 = float(p['throat_diameter_mm']) / 2.0
        dr = float(p['erosion_rate_mm_s']) * float(p['burn_time_s'])
        beklenen = (((r0 + dr) / r0) ** 2 - 1.0) * 100.0
        assert float(p['estimated_area_growth_percent']) == pytest.approx(
            beklenen, abs=0.15)


# -------------------------------------------------------- OH-D24-11 (c) --
class TestOHD2411LiteraturNotu:
    """Grafit/C-C bandının literatür notu var ve ürünle bağlantılı."""

    NOT = (KOK / 'docs' / 'arastirma' / 'fizik'
           / 'bogaz-erozyonu-grafit-cc-bandi.md')

    def test_not_dosyasi_var(self):
        assert kanit_gerekli(self.NOT).is_file(), (
            'OH-D24-11 (c): grafit bandının literatür notu yok; künye '
            'deponun kendi dizgesi olarak kalır')

    def test_birincil_kaynak_ve_tablo_adiyla_geciyor(self):
        m = kanit_gerekli(self.NOT).read_text(encoding='utf-8')
        for parca in ('Thakre', 'Yang', 'Journal of Propulsion and Power',
                      'Tablo 8', 'JANNAF', 'Borie'):
            assert parca in m, f'literatür notunda {parca!r} yok'

    def test_urunun_bugunku_bandi_notta_adiyla_yaziyor(self):
        """Not, ürünün bandını kendi sayısıyla anmalı (sessiz ayrışma yok)."""
        m = kanit_gerekli(self.NOT).read_text(encoding='utf-8')
        alt, ust = (float(x) for x in tb.GRAPHITE_A_REF_BAND_MM_S)
        assert f'{alt:g}'.replace('.', ',') in m or f'{alt:g}' in m
        assert f'{ust:g}'.replace('.', ',') in m or f'{ust:g}' in m

    def test_cc_bandinin_atifsizligi_notta_ve_uründe_ayni(self):
        """C-C'nin BAND'ı yok; notla ürün bu konuda ayrışamaz.

        ÖH D27/OH-D24-11 (b): D25'te C-C'nin kaynaksız (0.02, 0.10) bandı
        duruyor ve atıfsızlığı yalnız BEYAN ediliyordu. Kaynaksız sayı
        söküldü: band None, katsayı Borie ölçümüne çapalı.
        """
        m = kanit_gerekli(self.NOT).read_text(encoding='utf-8')
        rec = tb.THROAT_EROSION_MATERIALS['carbon_carbon']
        assert rec['band_attributed'] is False
        assert rec['band_source'] is None
        assert rec['a_ref_band_mm_s'] is None, (
            'C-C için yayımlanmış bant yoktur; depo-içi kestirim '
            'bant diye yayımlanamaz')
        assert bool(rec.get('anchor_attributed')) is True
        assert 'band_attributed = False' in m or 'band_attributed' in m

    def test_boyut_analizi_yazili(self):
        m = kanit_gerekli(self.NOT).read_text(encoding='utf-8')
        assert 'Boyut analizi' in m or 'boyutsuz' in m

    def test_urun_bandi_olculen_banda_capalandi(self):
        """ÇEVRİLDİ (ÖH D27/OH-D25-27): borç imi ödendi.

        D25'teki hâli — ``test_olculen_bandin_ust_ucu_urunun_ustunde`` —
        ürün bandının üst ucunun ölçülenin ALTINDA kalmasını çakıyordu ve
        kendi metninde "band çapalandığı gün bu bekçi güncellenir" diyerek
        BORCU İLAN EDİYORDU. D27'de borç ödendi: ürünün bandı Tablo 8'in
        ölçülen değerlerine çapalandı. Bekçi artık aynı kapıyı TERS yönden
        kilitler — ürün bandı ölçülen banttan saparsa kırmızıya döner.
        """
        m = kanit_gerekli(self.NOT).read_text(encoding='utf-8')
        assert '0,353' in m and '0,069' in m, (
            'Tablo 8 sayıları notta yok')
        alt, ust = (float(x) for x in tb.GRAPHITE_A_REF_BAND_MM_S)
        assert (alt, ust) == (0.069, 0.353), (
            f'ürün bandı ({alt}, {ust}) literatür notunun ölçülen bandı '
            '(0,069-0,353) ile aynı değil')
        # ÇEVRİLDİ (ÖH D28 / OH-D27-15): iki satır da üssü '0.8' diye elle
        # yazıyordu. Notun §4'teki TARİHSEL hesabı (n = 0,8 → 0,185) bir
        # aritmetik kimliktir, kayıt olarak korunur; ÜRÜNÜN çapası ise
        # modelin O ANKİ yasasını izlemek zorundadır (n künyeden gelir).
        assert math.isclose(
            0.139 * (70.0 / 49.0) ** 0.8, 0.185, abs_tol=5e-4), (
            'notun tarihsel C-C ölçekleme hesabı yeniden üretilemedi')
        n = tb.THROAT_EROSION_PRESSURE_EXPONENT
        capa = tb.THROAT_EROSION_MATERIALS['carbon_carbon'][
            'a_ref_anchor_mm_s']
        assert capa == pytest.approx(0.139 * (70.0 / 49.0) ** n, rel=1e-12)
        # Notun GÜNCEL sayısı da üründen ayrışamaz (D28: 0,1986 mm/s).
        assert f'{capa:.4f}'.replace('.', ',') in m, (
            'literatür notu ürünün güncel C-C çapasını anmıyor')
