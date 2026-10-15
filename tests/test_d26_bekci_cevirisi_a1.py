# -*- coding: utf-8 -*-
"""ÖH Dalga-26 · kulvar **bekci-cevirisi**, aşama 1 — bekçi körlükleri.

Bu dosya ürün kodu DEĞİŞTİRMEZ. Bu dalgada onarılan kusurların hepsi
BEKÇİ katmanındadır: bir bekçinin ölçtüğünü sandığı şeyi ölçmemesi.
Her sınıf, onarımın geri alınması hâlinde kırmızı verecek biçimde
yazıldı (ters-mutasyon kanıtları
``docs/scofield/raw/OH/D26/bekci-cevirisi/a1/mutasyon.json``).

Kapsanan kalemler
-----------------
* **OH-B4-03** — ``test_panel_units_v2626._js_kod_govdesi`` süzgeç
  körlüğü (13 panelin 9'u görülüyordu, Merkez kiracısı 0).
* **OH-D25-05** [19] ``BILINEN_CAPALAR`` anahtar çözünürlüğü,
  [20] ``HEAD_COEFF_DEFAULT`` kayması, [23] D0 ölçütünün alt-dize
  sınırı, [24] ``wiring_map`` süpürme maliyeti künyesi.
* **P13B3-06** (Fable-D20 ŞART) — bandın adsız ``1e-3`` tabanı.
* **OH-D20-12** (Fable-D20 ŞART) — önbellek sayacının fail-closed alt
  sınırı.
"""

import ast
import json
import math
import pathlib
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
TESTS = KOK / 'tests'
KANIT = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D26'
         / 'bekci-cevirisi' / 'a1')


def _oku(ad):
    return (TESTS / ad).read_text(encoding='utf-8')


# ===========================================================================
# 1) OH-B4-03 — JS kod gövdesi süzgeci artık kod yutmuyor
# ===========================================================================
class TestOHB403SuzgecKorlugu:
    """``_js_kod_govdesi`` iki fazlıydı ve dosyanın yarısını yutuyordu.

    ÖLÇÜLDÜ (``once_ohb403.json``, taban 7751531): ``fromResults``
    bildiren panel **9** görünüyordu (gerçekte 13), güverte kiracısı
    **9** (gerçekte 11), Analiz MERKEZİ kiracısı **0** (gerçekte 2) —
    yani ``test_panel_units_v2626``deki "Merkez kiracısı muafiyeti"
    fiilen hiç işlemiyordu, iki panel taramaya HİÇ girmiyordu.
    Sebep: satır tarayıcısı kapanmamış bir kesme işaretini (Türkçe
    yorumlardaki *"Merkez'in"*) satırda bırakıyor, sondaki ``re.S``li
    ``_STRING_RE`` o tırnaktan ileriye doğru her şeyi yutuyordu.
    ÖLÇÜLDÜ (``sonra_ohb403.json``): 13 / 11 / 2.
    """

    #: Ölçülen kapsam. Tek yönlü değil TAM eşitlik: kapsam daralırsa
    #: (süzgeç yeniden kör olursa) da, sessizce büyürse de kırmızı.
    BEKLENEN = {'fromResults': 13, 'guverte': 11, 'merkez': 2}

    @pytest.fixture(scope='class')
    def bildirimler(self):
        from tests.test_panel_units_v2626 import PANEL_BILDIRIMLERI
        return PANEL_BILDIRIMLERI

    def test_kapsam_turetmesi_13_11_2(self, bildirimler):
        fr = [a for a, (f, _d, _c) in bildirimler.items() if f]
        guv = [a for a, (f, d, _c) in bildirimler.items() if f and d]
        mrk = [a for a, (f, _d, c) in bildirimler.items() if f and c]
        olculen = {'fromResults': len(fr), 'guverte': len(guv),
                   'merkez': len(mrk)}
        assert olculen == self.BEKLENEN, (
            f'panel kapsam türetmesi değişti: {olculen} != {self.BEKLENEN}\n'
            f'fromResults={sorted(fr)}\nmerkez={sorted(mrk)}')

    def test_merkez_muafiyeti_fiilen_isliyor(self, bildirimler):
        """Muafiyet bir ADI olan kümeye uygulanmalı, boş kümeye değil."""
        mrk = sorted(a for a, (f, _d, c) in bildirimler.items() if f and c)
        assert mrk == ['cfd_panel.js', 'stability_panel.js'], (
            'Analiz MERKEZİ kiracısı kümesi boş ya da değişti: '
            f'{mrk} — muafiyet boş kümeye uygulanıyorsa hiç işlemiyordur')

    def test_suzgec_govde_yutmuyor(self):
        """Kapanmamış kesme işareti dosyanın kalanını yutmamalı."""
        from tests.test_panel_units_v2626 import _js_kod_govdesi
        ornek = ("// Merkez'in kiracısı\n"
                 "const spec = { fromResults: function (r) { return {}; } };\n")
        kod = _js_kod_govdesi(ornek)
        assert 'fromResults' in kod, (
            'yorumdaki kapanmamış kesme işareti kod gövdesini yuttu '
            '(OH-B4-03 gerilemesi)')

    def test_suzgec_yorumu_ve_dizeyi_hala_siliyor(self):
        """Onarım süzgeci gevşetmedi: yorum/dize hâlâ bildirim sayılmaz."""
        from tests.test_panel_units_v2626 import (
            _FROM_RESULTS_TANIM_RE, _js_kod_govdesi)
        ornek = ("// fromResults: burada yok\n"
                 "/* fromResults( */\n"
                 "const s = 'fromResults: yok';\n"
                 "const t = `fromResults(\n çok satırlı şablon`;\n")
        assert not _FROM_RESULTS_TANIM_RE.search(_js_kod_govdesi(ornek)), (
            'süzgeç gevşedi: yorum/dize/şablon içindeki bahis bildirim '
            'sanılıyor')

    def test_suzgec_konumu_koruyor(self):
        """Silinen karakterin yerine boşluk konur; satır sayısı sabit."""
        from tests.test_panel_units_v2626 import _js_kod_govdesi
        ornek = "a\n/* x\n y */\nb\n'c\nd'\ne\n"
        kod = _js_kod_govdesi(ornek)
        assert len(kod.split('\n')) == len(ornek.split('\n'))

    def test_borc_imi_kalkti(self):
        """OH-B4-03 borç imi (xfail) geri konmamalı."""
        metin = _oku('test_fazb_ac_kiraci_sozlesme.py')
        i = metin.index('def test_d3_yapisal_taramasi_kiracilari_goruyor')
        onceki = metin[max(0, i - 1200):i]
        assert 'xfail' not in onceki.split('def ')[-1], (
            'OH-B4-03 borç imi geri geldi: kusur onarıldıysa xfail '
            'kalkmalıdır (XPASS süiti kırar)')


# ===========================================================================
# 2) OH-D25-05 [19] — envanter anahtarının çözünürlüğü
# ===========================================================================
class TestOHD250519EnvanterCozunurlugu:
    """``BILINEN_CAPALAR`` (dosya, kwarg) çiftiyle tutulunca kör kalıyordu.

    ÖLÇÜLDÜ (``once_ohd2505.json``): ağaçta **4** taban altı
    çıplak-literal çapa var; çift anahtarla **3** görünüyor — envanter
    bugün bile bir çapayı saklıyordu. Anahtar (dosya, kwarg, DEĞER)
    üçlüsüne, karşılığı ADETe çevrildi.
    """

    def test_envanter_adet_sayiyor(self):
        from tests.test_d20_bekci_cevirisi_a1 import (
            TestP13B307GurultuTabaniTekKaynak as T)
        env = T.BILINEN_CAPALAR
        assert isinstance(env, dict), (
            'envanter yine kümeye döndü: aynı (dosya,kwarg) ile eklenen '
            'ikinci çapa sessizce yutulur')
        for anahtar, adet in env.items():
            assert len(anahtar) == 3, (
                f'envanter anahtarı üçlü değil: {anahtar}')
            assert isinstance(adet, int) and adet >= 1, (anahtar, adet)
        assert sum(env.values()) == 4, (
            'ölçülen taban altı çapa sayısı 4 idi; envanter toplamı '
            f'{sum(env.values())} — ağaç değiştiyse ölçüm yenilensin')

    def test_ayni_dosya_ayni_kwarg_ikinci_capa_gorunur(self):
        """FM5b senaryosu: aynı (dosya,kwarg) ile İKİNCİ çapa sayılmalı."""
        from tests.test_d20_bekci_cevirisi_a1 import (
            TestP13B307GurultuTabaniTekKaynak as T)
        env = T.BILINEN_CAPALAR
        coriolis = [(a, n) for a, n in env.items()
                    if a[0].endswith('test_six_dof_coriolis.py')]
        assert coriolis and coriolis[0][1] == 2, (
            'iki çapası olan dosya envanterde 1 görünüyor: çift anahtar '
            f'körlüğü geri geldi ({coriolis})')


# ===========================================================================
# 3) OH-D25-05 [20] — HEAD_COEFF_DEFAULT kaymasına körlük
# ===========================================================================
class TestOHD250520VarsayilanPsiKorlugu:
    """RL10 testleri ``HEAD_COEFF_DEFAULT`` kaymasını YAPICA göremez.

    ÖLÇÜLDÜ (``once_p13b306_d26.json``): psi0 ∈ {0,40 · 0,50 · 0,52 ·
    0,60} için geri hesaplanan psi_hw yayılımı **2,22e-16** — çünkü
    D ∝ psi0^(-1/2) ve psi_hw = psi0·(D/D_yayim)². Yani varsayılan
    kayarsa RL10 sınıfının hiçbir iddiası kırmızı vermez; Fable-D20
    ölçtü: 0,50 → 0,52 yapılınca 7/7 yeşil kalıyor.

    Sabiti KİLİTLEYEN bekçi de yoktu (``test_turbopompa.py:698`` sabiti
    kendisiyle karşılaştırıyor). Bu sınıf sabiti KENDİ KÜNYESİNE bağlar:
    ``HEAD_COEFF_SOURCE`` metni "default 0.50" diyor (Huzel & Huang,
    NASA SP-125, Böl. 6; Sutton 9. bs., Böl. 10). Sabit künyeden
    ayrışırsa kırmızı — sayı da, kaynağı da tek elden değişmek zorunda.
    """

    def test_sabit_kunyesiyle_ayni_seyi_soyluyor(self):
        from hrma.analysis.turbopump_sizing import (
            HEAD_COEFF_DEFAULT, HEAD_COEFF_SOURCE)
        m = re.search(r'default\s+([0-9]*\.?[0-9]+)', HEAD_COEFF_SOURCE)
        assert m, ('HEAD_COEFF_SOURCE artık varsayılan değeri YAZMIYOR; '
                   'sabitin kaynağa bağlanacağı çapa kalmadı')
        assert float(m.group(1)) == pytest.approx(HEAD_COEFF_DEFAULT), (
            f'HEAD_COEFF_DEFAULT={HEAD_COEFF_DEFAULT} ⟷ künye '
            f'"default {m.group(1)}" ayrıştı: sabit kaynağı olmadan '
            'değiştirilmiş (OH-D25-05 [20])')

    def test_tasarim_bandi_kunyeyle_ayni(self):
        from hrma.analysis.turbopump_sizing import (
            HEAD_COEFF_DESIGN_BAND, HEAD_COEFF_SOURCE)
        m = re.search(r'design band\s*~?([0-9.]+)\s*-\s*([0-9.]+)',
                      HEAD_COEFF_SOURCE)
        assert m, 'HEAD_COEFF_SOURCE tasarım bandını yazmıyor'
        assert (float(m.group(1)), float(m.group(2))) == pytest.approx(
            HEAD_COEFF_DESIGN_BAND), (
            f'tasarım bandı {HEAD_COEFF_DESIGN_BAND} ⟷ künye '
            f'{m.group(1)}-{m.group(2)} ayrıştı')

    def test_psi_hw_varsayilandan_bagimsiz_OLCULDU(self):
        """Körlüğün kendisi ölçüm çapası: geri hesap yapıca değişmez.

        Bu iddia bir GERİLEME bekçisi değil, kalemin zeminidir. Bir gün
        psi_hw varsayılana bağımlı hâle gelirse (model bağıntısı
        D ∝ psi^-1/2 olmaktan çıkarsa) kırmızı verir ve OH-D25-05 [20]
        yeniden ölçülür.
        """
        import tests.test_turbopompa as T
        rl10 = T._load('turbopump_rl10a33_design_point.json')
        geom = T._load('turbopump_rl10a33a_geometry.json')
        pub = geom['expected_outputs']['hardware_geometry'][
            'fuel_pump_impeller_diameter_in']['stage1']
        degerler = []
        for psi0 in (0.40, 0.50, 0.52, 0.60):
            d = T._rl10_fuel_case(rl10, head_coefficient=psi0)[
                'pump']['impeller_diameter_in']
            degerler.append(psi0 * (d / pub) ** 2)
        yayilim = max(degerler) - min(degerler)
        assert yayilim < 1e-12, (
            f'psi_hw artık varsayılana BAĞIMLI (yayılım {yayilim:.3e}); '
            'RL10 sınıfının körlük gerekçesi değişti, kalem yeniden '
            'ölçülsün')


# ===========================================================================
# 4) OH-D25-05 [23] — D0 ölçütünün alt-dize sınırı
# ===========================================================================
class TestOHD250523D0Olcutu:
    """D0 "hiç anılmıyor" ölçüsüdür; "bekçili" ölçüsü DEĞİLDİR."""

    def test_olcut_kelime_sinirinda(self):
        from tests.test_d17_bekci_cevirisi_a1 import _modul_aniliyor
        assert not _modul_aniliyor('response', 'x response_time y'), (
            'D0 ölçütü hâlâ alt-dize: modül adı başka bir adın parçası '
            'olarak geçince kritik D0 dışına düşüyor')
        assert _modul_aniliyor('response', 'from hrma import response')

    def test_olcutun_siniri_SAYIYLA_ilan_edilmis(self):
        """D0=0 iddiası yanında ithal kademesi de sayılmalı."""
        from tests.test_d17_bekci_cevirisi_a1 import (
            TestP13B410KritikBekciKademeleri as T)
        assert getattr(T, 'ITHAL_EDILMEYEN_TAVANI', None) == 17, (
            'D0 ölçütünün sınırı (ürün modülü hiçbir testte İTHAL '
            'edilmiyor = 17) artık ilan edilmiyor')


# ===========================================================================
# 5) OH-D25-05 [24] — wiring_map süpürme maliyeti künyesi
# ===========================================================================
class TestOHD250524SupurmeKunyesi:
    """Künye ÖLÇÜLEN sayıyı yazmalı, projeksiyonu ölçüm diye değil."""

    OLCUM = (KOK / 'docs/scofield/raw/OH/D20/bekci-cevirisi/a1'
             / 'once_supurme_maliyeti.json')

    @pytest.fixture(scope='class')
    def kunye(self):
        return (KOK / 'tools' / 'wiring_map.py').read_text(encoding='utf-8')

    def test_olculen_supurme_sn_kunyede(self, kunye):
        if not kanit_gerekli(self.OLCUM).is_file():                  # pragma: no cover
            pytest.skip('D20 süpürme ölçümü bu ağaçta yok')
        olcum = json.loads(kanit_gerekli(self.OLCUM).read_text(encoding='utf-8'))
        sn = olcum['fuel_type']['supurme_sn']
        yazi = f'{sn:.2f}'.replace('.', ',')          # 16,25
        assert yazi in kunye, (
            f'wiring_map künyesi ölçülen süpürme maliyetini ({yazi} sn) '
            'yazmıyor')

    def test_projeksiyon_olcum_diye_sunulmuyor(self, kunye):
        """9,3 sn bir projeksiyondu; ölçüm yerine geçemez."""
        i = kunye.find('9,3 sn')
        if i < 0:
            return
        cevre = kunye[max(0, i - 400):i + 200]
        assert 'PROJEKSİYON' in cevre.upper() or 'projeksiyon' in cevre, (
            '9,3 sn hâlâ ölçüm gibi sunuluyor; ölçülen 16,25 sn')

    def test_bir_alanlik_fark_ADLANDIRILMIS(self, kunye):
        """13 ⟷ 12 seçim alanı farkının adı künyede dursun."""
        assert 'injector_type' in kunye, (
            'süpürme projeksiyonu (13 alan) ile kapsam beyanı (12 alan) '
            'arasındaki fark adlandırılmamış')


# ===========================================================================
# 6) P13B3-06 (Fable-D20 ŞART) — bandın adsız tabanı kalktı
# ===========================================================================
class TestP13B306BandTabani:
    """``abs=max(psi_bant, 1e-3)`` → ``abs=psi_bant``.

    ÖLÇÜLDÜ (``once_p13b306_d26.json``): türetilen bant **8,5548e-4**,
    ölçülen artık **2,545e-5** (bandın %2,97'si). Adsız 1e-3 tabanı
    bandın 1,169 katıydı ve hiçbir ölçüme dayanmıyordu.
    """

    def test_yakit_capinda_adsiz_taban_yok(self):
        """KOD katmanında ölçülür (docstring bahsi tetiklemesin): hiçbir
        ``approx(..., abs=...)`` çağrısında ``max(...)`` sarmalayıcısı
        olmamalı — adsız taban tam olarak o sarmalayıcıydı."""
        agac = ast.parse(_oku('test_turbopompa.py'))
        sarmalayanlar = []
        for d in ast.walk(agac):
            if not (isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr == 'approx'):
                continue
            for k in d.keywords:
                if k.arg not in ('abs', 'rel'):
                    continue
                if (isinstance(k.value, ast.Call)
                        and isinstance(k.value.func, ast.Name)
                        and k.value.func.id == 'max'):
                    sarmalayanlar.append(f'{d.lineno}: {k.arg}=max(...)')
        assert not sarmalayanlar, (
            'bandın adsız tabanı geri geldi (Fable-D20 ŞART): '
            f'{sarmalayanlar}')

    def test_band_ve_artik_olculdu(self):
        import tests.test_turbopompa as T
        from hrma.analysis.turbopump_sizing import HEAD_COEFF_DEFAULT
        rl10 = T._load('turbopump_rl10a33_design_point.json')
        geom = T._load('turbopump_rl10a33a_geometry.json')
        pub = geom['expected_outputs']['hardware_geometry'][
            'fuel_pump_impeller_diameter_in']['stage1']
        d = T._rl10_fuel_case(rl10)['pump']['impeller_diameter_in']
        psi_hw = HEAD_COEFF_DEFAULT * (d / pub) ** 2
        bant = 2.0 * (T.PUB_ROUND_IN['fuel_pump_stage1'] / pub) * psi_hw
        artik = abs(psi_hw - 0.6048)
        assert artik < bant, (
            f'artık {artik:.3e} türetilen bandın ({bant:.3e}) dışında')
        assert artik / bant < 0.10, (
            'artık bandın %10\'unu aştı; ŞART\'ın dayandığı "taban '
            f'gereksiz" ölçümü değişti (oran {artik / bant:.3f})')

    def test_turbin_hiz_orani_ucluSU_olculdu(self):
        """ŞART'ın istediği nu_model / nu_opt / nu_hw ölçümü."""
        import tests.test_turbopompa as T
        rl10 = T._load('turbopump_rl10a33_design_point.json')
        geom = T._load('turbopump_rl10a33a_geometry.json')
        turb = rl10['expected_outputs']['turbine']
        tres = T._rl10_fuel_case(
            rl10,
            turbine_power_W=turb['horsepower'][1] * T.HP_W,
            turbine_mass_flow_kg_s=turb['flow_lb_s'][1] * T.LB_KG,
            turbine_efficiency=turb['efficiency_pct'][1] / 100.0)['turbine']
        pub_t = geom['expected_outputs']['hardware_geometry'][
            'turbine_meanline_diameter_in']
        nu_model = tres['velocity_ratio_per_stage']
        nu_opt = tres['velocity_ratio_optimum_per_stage']
        nu_hw = nu_model * pub_t / tres['mean_diameter_in']
        assert nu_hw == pytest.approx(0.4474, abs=5e-4), nu_hw
        assert nu_hw / nu_opt == pytest.approx(0.9522, abs=1e-3)
        # ÖLÇÜM NOTU (D26): nu_model ile nu_opt BİREBİR aynı çıkıyor —
        # model pitch hızını optimum orandan kuruyor, dolayısıyla
        # test_turbin_kademe_ve_cap'teki `0.90 < nu_hw/nu_opt < 1.0`
        # iddiası fiilen D_yayim/D_model oranını sınıyor, bağımsız bir
        # fizik iddiası değil. Kaleme not; bu bekçi o kimliği DONDURUR ki
        # bir gün ayrışırsa (gerçek bağımsız ölçü doğarsa) görülsün.
        assert nu_model == pytest.approx(nu_opt, rel=1e-12), (
            'nu_model artık nu_opt ile aynı değil: türbin hız oranı '
            'bağımsız bir ölçü hâline geldi, P13B3-06 notu güncellensin')


# ===========================================================================
# 7) OH-D20-12 (Fable-D20 ŞART) — sayacın fail-closed alt sınırı
# ===========================================================================
class TestOHD2012SayacAltSiniri:
    """Tavan iddiası ölçümün KOPMASINA kördü; alt sınır sıfırı ısırır."""

    def test_alt_sinir_tavandan_ONCE_geliyor(self):
        metin = _oku('test_uncertainty.py')
        alt = metin.find('_SayanOnbellek.yazim > 0')
        tavan = metin.find('cozum_per_ornek <= COZUM_PER_ORNEK_TAVANI')
        assert alt > 0, (
            'OH-D20-12 fail-closed alt sınırı yok: sayaç hiç yazım '
            'görmezse tavan iddiası 0,000 ile YEŞİL geçer')
        assert tavan > 0 and alt < tavan, (
            'alt sınır tavan iddiasından SONRA geliyor; kopuk ölçüm önce '
            'tavandan geçer')

    def test_alt_sinir_gerekcesi_kopmayi_ADIYLA_soyluyor(self):
        metin = _oku('test_uncertainty.py')
        i = metin.find('_SayanOnbellek.yazim > 0')
        gerekce = metin[i:i + 500]
        for parca in ('ölçüm kopuk', '__setitem__'):
            assert parca in gerekce, (
                f'alt sınırın gerekçesi kopma sebebini yazmıyor: {parca}')

    def test_sifir_sayac_tavani_yesil_gecirirdi(self):
        """Alt sınırın NİÇİN gerektiğinin aritmetik kanıtı."""
        FAST = 200
        tavan = 3.2
        assert 0 / float(FAST) <= tavan, (
            'bu iddia bozulduysa alt sınırın gerekçesi de değişmiştir')
        assert not math.isnan(0 / float(FAST))


# ===========================================================================
# 7b) OH-D25-06 — "yinelenen yazım" ÇÜRÜTÜLDÜ
# ===========================================================================
class TestOHD2506YinelenenYazimCurutuldu:
    """603 ⟷ 466 farkı yinelenen yazım DEĞİL, tahliye muhasebesiydi.

    İddia (Fable-D20 [21], onaranın JSON'undan ÇIKARIM — yeniden
    ölçülmemişti): "603 yazımın 137'si (%22,7) var olan anahtara; ya aynı
    anahtar yeniden çözülüyor ya da okuma anahtarı ≠ yazma anahtarı …
    gerçek yeniden çözümse FAST bütçesinde ~%23 boş maliyet."

    ÖLÇÜLDÜ (``once_ohd2506.json``, 200 örnek, iki önbellek AYRI sayıldı):

    ======================  ======  =========  =======  ========
    önbellek                yazım   benzersiz  son boy  tahliye
    ======================  ======  =========  =======  ========
    denge (max 4096)           402        402      402         0
    istasyon (max 64)          201        201       64       137
    ======================  ======  =========  =======  ========

    * hiçbir anahtara İKİ KEZ yazılmadı (``yeniden_yazim`` = **0**);
    * tahliye edilen hiçbir anahtar geri istenmedi
      (``tahliye_sonrasi_yeniden`` = **0**);
    * 603 − (402 + 64) = 137 = **istasyon tahliyesi**.

    Yani fark, toplam yazımın ömür boyu benzersiz anahtarla değil SON
    BOYla karşılaştırılmasından doğan bir muhasebe artığıdır: istasyon
    önbelleği ``EQ_STATION_CACHE_MAX`` = 64 ile FIFO sınırlıdır.
    Okuma anahtarı = yazma anahtarı; "%23 boş maliyet" YOKTUR.
    Kalem **çürütüldü**; bu sınıf çürütmeyi canlı tutar.
    """

    OLCUM = KANIT / 'once_ohd2506.json'

    def test_okuma_anahtari_yazma_anahtariyla_ayni(self):
        """Küçük koşumda bile aynı anahtara İKİNCİ yazım olmamalı."""
        import tests.test_uncertainty as U
        from hrma.analysis.uncertainty import (get_default_distributions,
                                               run_uncertainty)
        from hrma.engines.combustion_analysis import CombustionAnalyzer

        class Sayan(dict):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.yazim = 0
                self.yeniden = 0
                self.gorulen = set()

            def __setitem__(self, k, v):
                self.yazim += 1
                if k in self:
                    self.yeniden += 1
                self.gorulen.add(k)
                dict.__setitem__(self, k, v)

        shared = CombustionAnalyzer(memoize=True)
        denge = Sayan(shared._equilibrium_cache)
        istasyon = Sayan(getattr(shared, '_eq_station_cache', {}) or {})
        shared._equilibrium_cache = denge
        shared._eq_station_cache = istasyon
        dists = get_default_distributions('hybrid',
                                          overrides={'cd_injector': None})
        res = run_uncertainty(U._make_hybrid_factory(shared), dists,
                              n_samples=8, seed=42,
                              output_keys=['isp', 'c_star'])
        assert res['status'] == 'success', res.get('error')
        # FAIL-CLOSED: ölçüm kopmuşsa (sarmalayıcı devre dışı) sus.
        assert denge.yazim > 0 and istasyon.yazim > 0, (
            'sayaç hiç yazım görmedi — ölçüm kopuk, bu iddia hiçbir şey '
            'ölçmüyor')
        assert denge.yeniden == 0, (
            f'denge önbelleğinde {denge.yeniden} yeniden yazım: okuma '
            'anahtarı ile yazma anahtarı ayrışmış olabilir (OH-D25-06 '
            'çürütmesi geçersizleşti)')
        assert istasyon.yeniden == 0, (
            f'istasyon önbelleğinde {istasyon.yeniden} yeniden yazım')
        assert denge.yazim == len(denge.gorulen), (
            'denge önbelleğine yazım sayısı benzersiz anahtar sayısını '
            'aştı')

    def test_137_farki_TAHLIYE_muhasebesi(self):
        """Kayıtlı 200 örneklik ölçümün aritmetik kimliği."""
        if not kanit_gerekli(self.OLCUM).is_file():                  # pragma: no cover
            pytest.skip('OH-D25-06 ölçümü bu ağaçta yok')
        o = json.loads(kanit_gerekli(self.OLCUM).read_text(encoding='utf-8'))
        t = o['toplam']
        assert t['GERCEK_yeniden_yazim'] == 0, o['hukum']
        assert t['GERCEK_tahliye_sonrasi'] == 0, (
            'tahliye edilen anahtar geri istendi: tavan artık gerçek '
            'yeniden çözüme yol açıyor, kalem YENİDEN AÇILSIN')
        assert (t['yazim'] - t['son_boylar_toplami']
                == t['tahliye_toplam']), (
            '603 − 466 = 137 kimliği bozuldu; fark artık tahliyeyle '
            'açıklanmıyor')

    def test_istasyon_tavani_son_boyu_belirliyor(self):
        """Son boy ≠ ömür boyu benzersiz anahtar — karışıklığın kaynağı."""
        from hrma.engines.combustion_analysis import EQ_STATION_CACHE_MAX
        if not kanit_gerekli(self.OLCUM).is_file():                  # pragma: no cover
            pytest.skip('OH-D25-06 ölçümü bu ağaçta yok')
        o = json.loads(kanit_gerekli(self.OLCUM).read_text(encoding='utf-8'))
        ist = o['istasyon_onbellegi']
        assert ist['son_boy'] == EQ_STATION_CACHE_MAX, (
            f"istasyon son boyu {ist['son_boy']} ⟷ tavan "
            f'{EQ_STATION_CACHE_MAX}: ölçüm bayat')
        assert ist['benzersiz_anahtar_omur_boyu'] > ist['son_boy'], (
            'istasyon önbelleği artık tahliye etmiyor; 137 farkının '
            'açıklaması değişti')


# ===========================================================================
# 7c) P13B4-03 / -04 / -05 · P13B2-09 — ENGELLİ borçların BÜYÜMEMESİ
# ===========================================================================
class TestEngelliBorclarBuyumuyor:
    """Onarımı bu kulvarın sahası DIŞINDA olan borçların bugünkü boyu.

    Dördünün de onarımı ÜRÜN katmanındadır; bu kulvar yalnız
    ``tests/**`` yazar. Sahipleri:

    ==========  =====================================  ==================
    kalem       ürün adresi                            kulvar
    ==========  =====================================  ==================
    P13B2-09    ``cad_visualization._add_fallback_3d``  ihracat
    P13B4-03    ``solid_rocket_engine._qshod_band_..``  kati
    P13B4-04    ``analysis/tank_blowdown`` blok         hibrit
    P13B4-05    ``validation/status_report._flatten_``  (sahipsiz/ürün)
    ==========  =====================================  ==================

    Borç imleri (xfail) yerinde kalır; bu sınıf onların BÜYÜMESİNİ
    yasaklar. Sayılar ``once_p13b209.json`` ve
    ``once_serilestirici.json``dan gelir (D26 ölçümü).

    ÖH D27 GÜNCELLEMESİ — **P13B2-09 ONARILDI** (ihracat kulvarı a1,
    ``docs/scofield/raw/OH/D27/ihracat/a1/``). Ürün düzeltildi, borç imi
    ``test_fig_json_gate.BUGUN_BDATA_URETEN``den KALDIRILDI. Bu yüzden bu
    sınıftaki P13B2-09 bekçileri "borç 6'dan büyümesin" sorusundan
    "borç GERİ GELMESİN" sorusuna ÇEVRİLDİ: aşağıdaki iki test artık imin
    varlığını değil, imin YOKLUĞUNU ve ürünün 0 bdata ürettiğini sınar.
    Çeviriyi ürünü onaran kulvar yaptı (D27 kuralı); kalan üç kalem
    (P13B4-03/-04/-05) borç olarak durmaya devam eder.
    """

    def test_p13b209_borc_imi_geri_konmadi(self):
        """P13B2-09 borç imi KALKTI; geri konursa bu bekçi kırmızı verir.

        D26'da bu test ``BUGUN_BDATA_URETEN['_create_plotly_visualization']``
        değerinin hâlâ ``(6, 'P13B2-09')`` olduğunu doğruluyordu — yani
        KUSURUN DEVAM ETTİĞİNİ şart koşuyordu. Ürün onarılınca (D27 ihracat
        a1) o bekçi kusuru koruyan bir bekçiye dönüştü ve ÇEVRİLDİ.
        """
        from tests.test_fig_json_gate import BUGUN_BDATA_URETEN
        assert '_create_plotly_visualization' not in BUGUN_BDATA_URETEN, (
            'P13B2-09 borç imi geri konmuş: ürün D27 ihracat a1 ile '
            'onarıldı (bdata 6 -> 0, sonra_p13b209.json). İm ancak kusur '
            'GERÇEKTEN geri döndüyse konur — o zaman da önce ürün onarılır.')
        assert not any(defter == 'P13B2-09'
                       for _olculen, defter in BUGUN_BDATA_URETEN.values()), (
            'P13B2-09 başka bir fonksiyon adı altında borç imi olarak geri '
            'gelmiş: %r' % (BUGUN_BDATA_URETEN,))

    def test_p13b209_urun_ciktisi_bdata_uretmiyor(self):
        """Onarımın KENDİSİ: yedek 3B yol artık base64 bdata yazmıyor.

        İm kalktığı için "borç büyümesin" ölçütünün yerini ürün ölçütü alır.
        Sonda, mesh listesi BOŞ verilerek tam olarak kusurun yaşadığı yola
        (``_add_fallback_3d_motor``) sokulur.
        """
        from tests.test_fig_json_gate import (
            SONDA_MOTORU, _bdata_sayisi, _sondalar)
        cikti = _sondalar()['_create_plotly_visualization']()
        sayi, uzunluk = _bdata_sayisi(cikti)
        assert sayi == 0, (
            '_create_plotly_visualization çıktısında %d base64 bdata bloğu '
            'var (JSON %d bayt) — P13B2-09 geri gelmiş: vendor plotly.js '
            '1.58.5 bu biçimi çözemez, 3B görünüm sessizce BOŞ kalır.'
            % (sayi, uzunluk))
        # Sonda boşa koşmasın: yedek yol gerçekten çizim üretmiş olmalı.
        assert 'Chamber' in cikti and 'Nozzle' in cikti, (
            'yedek 3B yol iz üretmiyor — bdata sayısının 0 olması ölçüm '
            'değil boşluk olur (fail-closed). Sonda motoru: %r'
            % (sorted(SONDA_MOTORU),))

    def test_p13b209_adresi_duzeltildi(self):
        """Bayat onarım adresi (945-947) geri konmasın."""
        metin = _oku('test_fig_json_gate.py')
        assert '_add_fallback_3d_motor' in metin, (
            'P13B2-09 borç imi kusurun ÖLÇÜLEN adresini yazmıyor '
            '(6 bdata bloğunun tamamı _add_fallback_3d_motor çıkışında)')

    def test_p13b405_flatten_cell_dusen_alan_buyumedi(self):
        from hrma.validation.status_report import _flatten_cell
        import tests.test_fazb_serilestirici_esligi as S
        ic = S._s1_ic_hucre()
        yayim = _flatten_cell(ic, 'main')
        ic_k = set(S._anahtarlar(ic))
        ya_k = set(S._anahtarlar(yayim))
        izinli = {i.alan for i in S.S1_IZINLER}
        dusen = ic_k - ya_k
        izinsiz = dusen - izinli
        assert len(dusen) <= 11, (
            f'_flatten_cell artık {len(dusen)} alan düşürüyor (D26 ölçümü '
            f'11): {sorted(dusen)}')
        assert len(izinsiz) <= 8, (
            f'gerekçesiz düşen alan {len(izinsiz)} (D26 ölçümü 8): '
            f'{sorted(izinsiz)}')

    def test_p13b404_blok_boyu_ve_bayrak(self):
        """vapor_model_valid iç nesnede VE blokta — kapanış çapası.

        ÖH D27 / hibrit a1 — HATIRLATICI KAPANDI. D26'da bu iddia
        "bayrak blokta ise xfail imi kaldırılmalı" diye bekliyordu,
        çünkü ürün tarafı (``hybrid_rocket_engine._tank_blowdown_block``)
        hibrit kardeş dalının sahasındaydı. D27'de ürün onarıldı: blok
        40 -> 43 anahtar, bayrak yayımlanıyor ve
        ``test_fazb_serilestirici_esligi`` içindeki xfail(strict) imi
        KALDIRILDI. İddia yönü çevrildi — geri açılışı ölçer.
        """
        import tests.test_fazb_serilestirici_esligi as S
        ic = set(S._anahtarlar(S._s2_ic_durum()))
        blok = set(S._s2_yayim_blok())
        assert 'vapor_model_valid' in ic, (
            'P13B4-04 kaleminin zemini değişti: bayrak artık iç nesnede '
            'de yok')
        assert 'vapor_model_valid' in blok, (
            'P13B4-04 GERİ AÇILMIŞ: blok bayrağı yeniden yutuyor '
            '(ÖH D27 / hibrit a1 onarımı sökülmüş)')

    def test_p13b403_kayit_kunyesi_serilestiricide_var(self):
        """Künye alanları KAYIT serileştiricisinde var; ürün onu yayımlamıyor."""
        import tests.test_fazb_serilestirici_esligi as S
        d = S._s5_kayit()
        d = d.as_dict() if hasattr(d, 'as_dict') else d
        alanlar = set(S._anahtarlar(d))
        for ad in ('record_id', 'retrieved'):
            assert ad in alanlar, (
                f'kayıt serileştiricisi künye alanını yitirdi: {ad} — '
                'P13B4-03 onarım adresi (ürün gövdesini QSHODBandRecord\'e '
                'çevirmek) artık geçerli değil')
        assert any(a.startswith('record_confidence') for a in alanlar), (
            'güven derecesi alanı kayıt serileştiricisinde yok')


# ===========================================================================
# 8) Bu dosyanın kendi dürüstlüğü
# ===========================================================================
def test_bu_dosyada_iddiasiz_test_yok():
    """ÖH OH-D23-01 kuralı: her test en az bir iddia taşır."""
    agac = ast.parse(pathlib.Path(__file__).read_text(encoding='utf-8'))
    iddiasiz = []
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name.startswith('test_'):
            if not any(isinstance(x, (ast.Assert, ast.Raise))
                       for x in ast.walk(d)):
                iddiasiz.append(d.name)
    assert not iddiasiz, f'iddiasız test(ler): {iddiasiz}'
