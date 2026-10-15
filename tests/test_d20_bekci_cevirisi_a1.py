"""ÖH Dalga-20 / kulvar ``bekci-cevirisi`` aşama 1 — EŞİK SAĞLIĞI KİLİTLERİ.

Bu dosya ürün kodunu değil, BEKÇİLERİN KENDİSİNİ kilitler: bir eşiğin
nereden geldiği (kaynağın basamağı mı, çıktının kendisi mi), bir sabitin
kaç yerde tanımlı olduğu ve bir bandın tabanın altına inmeye hakkı olup
olmadığı.

KİLİTLENEN KALEMLER
-------------------
``P13B3-07``
    Platform gürültü tabanı (``1e-12``) ilan edilmişti ama sabit yalnız onu
    yazan dosyada duruyordu. Sabit ``tests/support/esikler.py``ye taşındı;
    tabanın ALTINA inen karşılaştırmalar iki sınıfa ayrıldı (cebirsel
    KİMLİK: meşru · dondurulmuş ÇAPA: kusur) ve çapa sınıfı fail-closed
    envanterle çivilendi.

``P13B3-08``
    ``test_stability_cekirdek`` belge değerini (0,4206, dört basamak) 16
    basamaklı bir literalle ve ``rel=1e-14`` ile kilitliyordu. Çapa artık
    kaynağının basamağında; sıkı iddia ise TANIM KİMLİĞİNE bağlandı.

``P13B3-06``
    ``test_turbopompa``nın üç eşiği docstring'inde "tolerans ölçülen sapmayı
    kapsayacak şekilde seçildi" diyordu. Sistematik sapmanın ADI (baş
    katsayısı psi / hız oranı U/C0) sayıyla çıkarıldı; bant yayımlanmış
    sayının yuvarlamasından türetiliyor.

``P13B4-12``
    ``safe_name`` bekçisi yalnız import satırının METNİNİ arıyordu.

``OH-D20-12``
    FAST bütçesi duvar saatiyle ölçülüyordu; makine hızı algoritma
    maliyetini gizliyordu.

ÖLÇÜM KAYITLARI
---------------
``docs/scofield/raw/OH/D20/bekci-cevirisi/a1/``: ``olcum.py`` (once/sonra),
``olcum_gurultu.py``, ``olcum_p13b306.py``, ``olcum_ohd2012.py``,
``olcum_supurme_maliyeti.py`` ve karşılık gelen ``once_*.json`` /
``sonra_*.json`` dosyaları.
"""

import ast
import pathlib

import pytest

from tests.support.esikler import (
    CEBIRSEL_KIMLIK_REL,
    PLATFORM_GURULTU_TABANI_REL,
)

KOK = pathlib.Path(__file__).resolve().parent.parent
TESTS = KOK / 'tests'


def _test_dosyalari():
    for yol in sorted(TESTS.rglob('*.py')):
        if '__pycache__' in yol.parts:
            continue
        yield yol


def _approx_cagrilari(yol):
    """(satır, kwarg, değer, ilk-argüman-düğümü) — approx bantları."""
    try:
        agac = ast.parse(yol.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:                                   # pragma: no cover
        return
    for d in ast.walk(agac):
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr == 'approx'):
            continue
        for k in d.keywords:
            if k.arg not in ('rel', 'abs'):
                continue
            try:
                deger = ast.literal_eval(k.value)
            except Exception:
                continue                    # adlandırılmış sabit — literal değil
            yield d.lineno, k.arg, deger, (d.args[0] if d.args else None)


def _ciplak_literal(dugum):
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value,
                                                      (int, float)):
        return True
    return (isinstance(dugum, ast.UnaryOp)
            and isinstance(dugum.op, (ast.USub, ast.UAdd))
            and isinstance(dugum.operand, ast.Constant)
            and isinstance(dugum.operand.value, (int, float)))


# ===========================================================================
# 1) P13B3-07 — GÜRÜLTÜ TABANI TEK KAYNAKTAN OKUNUR
# ===========================================================================

class TestP13B307GurultuTabaniTekKaynak:
    """Kural, yalnız onu YAZAN dosyada geçerli olamaz.

    ÖLÇÜLDÜ (``once_gurultu.json``, taban 14acd1d): taban ``1e-12`` ilan
    edilmişken tabanın ALTINDA bant ilan eden **60** karşılaştırma vardı ve
    sabit **tek dosyada** (``test_sivi_akustik_gocu.py``) tanımlıydı — yani
    hiçbiri onu okuyamazdı.

    Ayrım (``esikler.py`` docstring'i): 60'ın **54'ü** iki İFADEYİ
    karşılaştırıyor (cebirsel kimlik — meşru), **6'sı** ÇIPLAK SAYI
    LİTERALİNİ çapalıyor. Tabanın altında çapa, "bu literalin son
    basamakları her platformda aynı çıkar" demektir; ölçülmemiş iddiadır.
    """

    #: Tabanın altında ÇAPA kuran, ölçülmüş ve BİLİNEN yerler. Bu kulvarın
    #: sahası dışındaki dosyalar burada ADIYLA durur (gizlenmiyor); saha
    #: içindeki ikisi (test_stability_cekirdek 79/137) ÖH D20'de çevrildi.
    #:
    #: ÖH D26 · defter **OH-D25-05** [19]: envanter (dosya, kwarg) ÇİFTİYLE
    #: tutuluyordu ve o anahtar ÇÖZÜNÜRLÜK KAYBIYDI — bilinen bir dosyaya
    #: AYNI kwarg ile eklenen yeni bir çapa kümede zaten var göründüğü için
    #: sessizce yutuluyordu (Fable-D20 FM5b: ``test_six_dof_coriolis.py``ye
    #: ikinci bir ``abs=`` çapası eklendiğinde test 1 PASSED verdi).
    #: ÖLÇÜLDÜ (``once_ohd2505.json``, taban 7751531): ağaçta **4** taban
    #: altı çıplak-literal çapa var, çift anahtarla **3** görünüyor — yani
    #: envanterin kendisi bugün bile bir çapayı saklıyordu.
    #: Anahtar artık (dosya, kwarg, DEĞER) üçlüsü ve karşılığı ADETtir;
    #: karşılaştırma TAM EŞİTLİKTİR (büyüme de, adı konmamış daralma da
    #: kırmızı verir).
    BILINEN_CAPALAR = {
        ('tests/cfd/test_viskoz_tensor.py', 'rel', 1e-15): 1,   # cfd kulvarı
        ('tests/test_duyarlilik_e5.py', 'abs', 1e-15): 1,       # 13/14 rasyo
        ('tests/test_six_dof_coriolis.py', 'abs', 1e-18): 2,    # 0.0 ile kıyas
    }

    def test_sabit_tek_yerde_tanimli(self):
        """``PLATFORM_GURULTU_TABANI_REL`` yalnız esikler.py'de ATANIR."""
        tanimlayan = []
        for yol in _test_dosyalari():
            try:
                agac = ast.parse(yol.read_text(encoding='utf-8',
                                               errors='replace'))
            except SyntaxError:                           # pragma: no cover
                continue
            for d in ast.walk(agac):
                hedefler = []
                if isinstance(d, ast.Assign):
                    hedefler = d.targets
                elif isinstance(d, ast.AnnAssign):
                    hedefler = [d.target]
                for t in hedefler:
                    if (isinstance(t, ast.Name)
                            and t.id == 'PLATFORM_GURULTU_TABANI_REL'):
                        tanimlayan.append(str(yol.relative_to(KOK)))
        assert tanimlayan == ['tests/support/esikler.py'], (
            'gürültü tabanı ikinci kez tanımlanmış (tek kaynak kuralı): '
            f'{tanimlayan}')

    def test_ilan_eden_dosya_da_paylasilan_sabiti_okuyor(self):
        metin = (TESTS / 'test_sivi_akustik_gocu.py').read_text(
            encoding='utf-8')
        assert 'from tests.support.esikler import' in metin
        assert 'PLATFORM_GURULTU_TABANI_REL = 1e-12' not in metin, (
            'sabit yerel olarak yeniden tanımlanmış')

    def test_taban_alti_capalar_buyumuyor(self):
        """Yeni bir "tabanın altında dondurulmuş literal" eklenemez.

        ÖH D26 · **OH-D25-05** [19]: envanter ADET sayar. Eski küme
        anahtarı (dosya, kwarg) idi; bilinen bir dosyaya aynı kwarg ile
        eklenen İKİNCİ çapa kümeye hiç yansımıyordu (``bulunan`` bir
        set olduğu için). Artık sayım (dosya, kwarg, değer) üçlüsü
        başına yapılır ve envanterle TAM EŞİTLİK aranır.
        """
        bulunan = {}
        detay = []
        for yol in _test_dosyalari():
            rel = str(yol.relative_to(KOK))
            for satir, kwarg, deger, arg in _approx_cagrilari(yol):
                if not (isinstance(deger, float)
                        and 0.0 < deger < PLATFORM_GURULTU_TABANI_REL):
                    continue
                if arg is not None and _ciplak_literal(arg):
                    anahtar = (rel, kwarg, deger)
                    bulunan[anahtar] = bulunan.get(anahtar, 0) + 1
                    detay.append(f'{rel}:{satir} {kwarg}={deger}')
        eklenen = {a: n - self.BILINEN_CAPALAR.get(a, 0)
                   for a, n in bulunan.items()
                   if n > self.BILINEN_CAPALAR.get(a, 0)}
        assert not eklenen, (
            'gürültü tabanının ALTINDA yeni çıplak-literal çapası '
            f'(anahtar -> kaç TANE fazla): {sorted(eklenen.items())}\n'
            f'tüm bulgular: {detay}')
        kaybolan = {a: n - bulunan.get(a, 0)
                    for a, n in self.BILINEN_CAPALAR.items()
                    if n > bulunan.get(a, 0)}
        assert not kaybolan, (
            'envanterdeki çapa(lar) ağaçta yok — onarıldıysa BILINEN_CAPALAR '
            f'adet düşürülerek güncellensin: {sorted(kaybolan.items())}')

    def test_cevrilen_iki_capa_geri_gelmedi(self):
        """P13B3-08 onarımı: stability_cekirdek artık çapa listesinde yok."""
        rel = 'tests/test_stability_cekirdek.py'
        for _s, kwarg, deger, arg in _approx_cagrilari(TESTS /
                                                       'test_stability_cekirdek.py'):
            if (isinstance(deger, float)
                    and 0.0 < deger < PLATFORM_GURULTU_TABANI_REL
                    and arg is not None and _ciplak_literal(arg)):
                pytest.fail(f'{rel}: taban altı literal çapa geri geldi '
                            f'({kwarg}={deger})')


# ===========================================================================
# 2) P13B3-08 — BELGE ÇAPASI KAYNAĞININ BASAMAĞINDA
# ===========================================================================

class TestP13B308BelgeCapasiKaynagindan:
    """16 basamaklı literal + ``rel=1e-14`` yerine iki ayrı iddia."""

    def test_onaltı_basamakli_literal_gitti(self):
        metin = (TESTS / 'test_stability_cekirdek.py').read_text(
            encoding='utf-8')
        assert '0.4205926793776707' not in metin, (
            'belge çapası yine 16 basamaklı literale bağlanmış')
        assert 'DOC_GAMMA_SQ = 0.4206' in metin, (
            'belge değeri kaynağının basamağıyla yazılmalı')

    def test_tanim_kimligi_urunu_gercekten_baglıyor(self):
        """Γ² = γ(2/(γ+1))^((γ+1)/(γ−1)) — bağımsız yazım ürünle örtüşür."""
        from hrma.stability import gamma_function_sq
        for g in (1.14, 1.2, 1.25, 1.33):
            tanimdan = g * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0))
            assert gamma_function_sq(g) == pytest.approx(
                tanimdan, rel=CEBIRSEL_KIMLIK_REL)

    def test_belge_bandi_gercek_yuvarlamayla_uyumlu(self):
        """Bant belgenin basamağı kadar; ne daha dar ne keyfi geniş."""
        from hrma.stability import gamma_function_sq
        olculen = gamma_function_sq(1.2)
        assert abs(olculen - 0.4206) < 5e-5
        # Bandın 10 katı gevşetilirse üçüncü basamak da serbest kalırdı:
        # o zaman 0,421 gibi YANLIŞ bir belge değeri de geçerdi.
        assert abs(0.421 - olculen) > 5e-5


# ===========================================================================
# 3) P13B3-06 — TURBOPOMPA BANDI ÇIKTIDAN DEĞİL KAYNAKTAN
# ===========================================================================

class TestP13B306BandKaynaktanTuretiliyor:
    """"Tolerans bunu kapsayacak şekilde %25 seçildi" cümlesi kalkmalı."""

    #: ÖLÇÜLDÜ (once.json bölüm D): dosyada rel >= %10 olan üç bant vardı
    #: (0,15 / 0,25 / 0,15) ve üçü de docstring'inde bandın ölçülen sapmayı
    #: kapsayacak biçimde SEÇİLDİĞİNİ söylüyordu. Onarımdan sonra sıfır.
    GEVSEK_BANT_TAVANI = 0.10

    def test_fitted_bantlar_dosyada_kalmadi(self):
        """İddia METİNDE değil AĞAÇTA ölçülür (kalan gevşek bant sayısı)."""
        kalan = [(satir, kwarg, deger)
                 for satir, kwarg, deger, _arg in _approx_cagrilari(
                     TESTS / 'test_turbopompa.py')
                 if kwarg == 'rel' and isinstance(deger, float)
                 and deger >= self.GEVSEK_BANT_TAVANI]
        assert not kalan, (
            'çıktıdan seçilmiş gevşek bant hâlâ duruyor (rel >= '
            f'{self.GEVSEK_BANT_TAVANI}): {kalan}')
        metin = (TESTS / 'test_turbopompa.py').read_text(encoding='utf-8')
        assert 'psi_hw' in metin, 'sistematik sapmanın adı konmamış' 

    def test_capin_bas_katsayisina_bagimliligi_KESIN(self):
        """D ∝ psi^(-1/2): bandın türetildiği bağıntının kendisi.

        Bu kimlik tutmazsa, "sapmanın adı psi'dir" cümlesi de düşer;
        o yüzden bekçi bağıntıyı doğrudan sınar.
        """
        from hrma.analysis.turbopump_sizing import size_turbopump
        ortak = dict(mass_flow_kg_s=12.0, pressure_rise_Pa=4.0e6,
                     density_kg_m3=71.0, vapor_pressure_Pa=0.0,
                     tank_pressure_Pa=3.0e5, shaft_speed_rpm=30000.0)
        d1 = size_turbopump(head_coefficient=0.50, **ortak)['pump'][
            'impeller_diameter_m']
        d2 = size_turbopump(head_coefficient=0.60, **ortak)['pump'][
            'impeller_diameter_m']
        assert d2 / d1 == pytest.approx((0.50 / 0.60) ** 0.5,
                                        rel=PLATFORM_GURULTU_TABANI_REL)


# ===========================================================================
# 4) P13B4-12 — İMPORT SATIRI DEĞİL ÇAĞRI
# ===========================================================================

class TestP13B412SafeNameCagriliyor:
    """İçe aktarım kabloyu gösterir, kapıyı değil.

    ÖLÇÜLDÜ (``once.json`` bölüm F): elle listedeki iki dosyada gerçek
    çağrı sayısı step_export 1, drawing_generator 2. Bekçi bu sayıyı
    ölçmüyordu; import satırının METNİNİ arıyordu.
    """

    HEDEFLER = ('hrma/export/step_export.py',
                'hrma/export/drawing_generator.py')
    KAPILAR = ('safe_name', 'safe_arcname', 'is_safe_arcname')

    def test_elle_listedeki_dosyalar_kapiyi_CAGIRIYOR(self):
        for rel in self.HEDEFLER:
            agac = ast.parse((KOK / rel).read_text(encoding='utf-8'))
            cagri = [d for d in ast.walk(agac) if isinstance(d, ast.Call)
                     and (d.func.id if isinstance(d.func, ast.Name)
                          else getattr(d.func, 'attr', '')) in self.KAPILAR]
            assert cagri, f'{rel}: ad kapısı içe aktarılmış ama çağrılmamış'

    def test_bekci_artik_cagri_ariyor(self):
        metin = (TESTS / 'test_v262_release_gate.py').read_text(
            encoding='utf-8')
        assert 'hiç\n            # ÇAĞIRMIYOR' in metin or (
            'ÇAĞIRMIYOR' in metin), (
            'release-gate bekçisi yine yalnız import metnini arıyor')


# ===========================================================================
# 5) OH-D20-12 — BÜTÇE SAAT DEĞİL SAYI İLE DE ÖLÇÜLÜR
# ===========================================================================

class TestOHD2012CozumSayisiCivili:
    """Duvar saati makine hızını, çözüm sayısı algoritmayı ölçer."""

    def test_butce_testinde_makineden_bagimsiz_olcu_var(self):
        metin = (TESTS / 'test_uncertainty.py').read_text(encoding='utf-8')
        assert 'COZUM_PER_ORNEK_TAVANI' in metin, (
            'FAST bütçesi yine yalnız duvar saatine bağlı')
        assert '_SayanOnbellek' in metin
        # Tavan, ölçülen tabanın (3,015) makul bir üstünde olmalı; 4'ün
        # üstü "her örnek yeniden çözülüyor" hâlini de geçirirdi.
        from tests import test_uncertainty as U
        assert 3.015 < U.COZUM_PER_ORNEK_TAVANI <= 3.5, (
            f'tavan {U.COZUM_PER_ORNEK_TAVANI} anlamsız: ölçülen taban '
            '3,015 ve tavan onu dar sarmalı')
