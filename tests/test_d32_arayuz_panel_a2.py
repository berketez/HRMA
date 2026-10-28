# -*- coding: utf-8 -*-
"""ÖH D32 · arayuz-panel · aşama 2/2 — OH-D31-14 FORM KATMANI bekçisi.

Kalem: ``advanced.html``in çift-katman alanları, kullanıcı onlara HİÇ
dokunmasa bile gövdeye sayı gönderiyordu (``value="..."`` ön-dolusu +
toplayıcıda ``|| N`` yedeği). Uç bu sayıyı KULLANICI GİRDİSİ sayıyordu —
``tank_pressure`` için bunu harfi harfine yayımlıyordu bile
(``tank_pressure_source = 'user_input'``).

Sökülecek alan kümesi ÖLÇÜMLE seçildi (``docs/scofield/raw/OH/D32/
arayuz-panel/a2/once_ohd3114.json`` K3): alan gövdeden düşürülünce
yayımlanan mühendislik sayısı DEĞİŞMİYORSA söküm ürünün hükmünü
değiştirmez, yalnız "kullanıcı girdisi" yalanını bitirir. Sayıyı oynatan
yedi alan SÖKÜLMEDİ ve aşağıda ADIYLA kilitlendi (uç kapısı devri).

Bekçi kaynağı DOSYADAN okur (``inspect.getsource`` değil) — taban kaydı-15
dersi.
"""
import io
import os
import re

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SABLON = os.path.join(KOK, 'hrma', 'templates', 'advanced.html')
I18N = os.path.join(KOK, 'hrma', 'static', 'js', 'i18n_advanced.js')


def _oku(yol):
    return io.open(yol, encoding='utf-8').read()


#: app-api-uc a1 §1.4 "form sökümü GEREKİYOR" listesinden, ÖLÇÜMLE
#: sökülebilir bulunan alanlar -> sökülen ön-dolu değeri.
SOKULEN = {
    'l_star': '1.0',
    'contraction_ratio': '0',
    'chamber_diameter_input': '0',
    'expansion_ratio': '0',
    'tank_pressure': '50',
    'target_velocity': '30',
    'hole_diameter_min': '0.3',
    'hole_diameter_max': '2.0',
    'outer_diameter': '50',
    'pintle_diameter': '25',
    'n_slots': '6',
    # V301/E2 (Ayberk tur 1): aşağıdaki beş alanın DEVİR kilidi KAPANDI —
    # kilidin şartı (uç kanonik varsayılanı ya da 422 kapısı) artık
    # sağlanıyor: uç ``_eleman_istek_ezmeleri``/``element_clean_inputs``
    # kapısı (tel biçimi + aralık + tutarlılık 422) ve
    # ``_CALCULATE_UC_VARSAYILANLARI`` künyesi (0 = "çözücü türetir",
    # ``defaults_applied``). Ön-dolu sayılar KULLANICININ SEÇMEDİĞİ bir
    # tasarımı dayatıyordu (8 çift × 0,8 mm sabit; 1 × 2 mm yuva ile hedef
    # açı yok sayılıyordu) — ölçüm: docs/scofield/raw/OH/V301/ayberk1/
    # enjektor-genel/once.json ``form``.
    'element_pairs': '8',
    'slot_width': '1.0',
    'slot_height': '2.0',
    'swirl_chamber_diameter': '20',
    'swirl_angle': '71.2',
}

#: SÖKÜLMEYEN alanlar: ön-dolu düşürülünce yayımlanan mühendislik sayısı
#: OYNUYOR (ölçüldü, ``once_ohd3114.json`` K3). Söküm ancak uç kanonik bir
#: varsayılan ya da 422 kapısı kurduktan sonra yapılabilir; o saha
#: ``app-api-uc``dir. Bu sözlük kilidi TUTAR: biri kapısız sökerse bu
#: bekçi kırmızıya döner.
DEVIR = {
    'of_ratio': (18947, 'ucun kanonik varsayilani 1.0; alan dusurulunce '
                        'HTTP 200 -> 400 (gecerli bir O/F degil)'),
    'oxidizer_temp': (4579, 'tank_temperature kolu yedeksiz: dusurulunce '
                            'enjektor Dp 30,373 -> 30,543 bar'),
}


def _inputlar(metin, ad):
    return re.findall(r'<input\b[^>]*\bid="%s"[^>]*>' % re.escape(ad), metin)


class TestOHD3114FormSokumu:
    """Sökülen alanlar: ne ön-dolu ne toplayıcı yedeği kalmalı."""

    @pytest.mark.parametrize('ad', sorted(SOKULEN))
    def test_sablon_on_dolusu_yok(self, ad):
        metin = _oku(SABLON)
        etiketler = _inputlar(metin, ad)
        assert etiketler, '#%s alani sablondan kayboldu' % ad
        for e in etiketler:
            assert not re.search(r'\bvalue="', e), (
                '#%s hala on-dolu: kullanici dokunmasa bile govdeye sayi '
                'gider ve uc onu kullanici girdisi sayar. Etiket: %s'
                % (ad, e[:160]))

    @pytest.mark.parametrize('ad', sorted(SOKULEN))
    def test_toplayici_sayisal_yedegi_yok(self, ad):
        """``getElementById('<ad>')...|| 30`` gibi bir sayı yedeği kalmamalı.

        ``|| 0`` dahil: sıfır da uydurulmuş bir sayıdır ve uç onu
        "kullanıcı 0 verdi" diye okur (ölçüldü: ``input_warnings``
        ``'X' was supplied as 0`` kaydı).
        """
        metin = _oku(SABLON)
        kalip = (r"getElementById\('%s'\)\??\.value\s*\|\|\s*[0-9.eE+-]+"
                 % re.escape(ad))
        bulunan = re.findall(kalip, metin)
        assert not bulunan, (
            '#%s icin toplayicida hala sayi yedegi var: %s' % (ad, bulunan))

    def test_dusurme_gecisi_alanlari_kapsiyor(self):
        """Boş alanın ANAHTARI gövdeden düşmeli (açık ``null`` bile değil)."""
        metin = _oku(SABLON)
        liste = re.search(r'const NUMBYID_ALANLARI = \[(.*?)\];', metin, re.S)
        assert liste, 'NUMBYID_ALANLARI listesi bulunamadi'
        icerik = liste.group(1)
        for ad in ('l_star', 'expansion_ratio', 'chamber_diameter_input',
                   'contraction_ratio', 'tank_pressure', 'target_velocity'):
            assert "'%s'" % ad in icerik, (
                '%s dusurme listesinde yok: bos alan acik null olarak gider '
                've uc "kullanici null gonderdi" ile "hic gondermedi" '
                'ayrimini yapamaz' % ad)

    def test_enjektor_kollari_bos_alani_gondermiyor(self):
        """Enjektör kolları `enjAta` ile yazar; boş alanın anahtarı silinir."""
        metin = _oku(SABLON)
        tanim = re.search(r'const enjAta = function \(ad, tamsayi\) \{(.*?)\};',
                          metin, re.S)
        assert tanim, 'enjAta yardimcisi bulunamadi'
        assert 'delete data[ad]' in tanim.group(1), (
            'enjAta bos alanin anahtarini silmiyor')
        for ad in ('target_velocity', 'hole_diameter_min', 'hole_diameter_max',
                   'outer_diameter', 'pintle_diameter', 'n_slots'):
            assert re.search(r"enjAta\('%s'" % re.escape(ad), metin), (
                '%s enjektor kolunda hala dogrudan atanmis' % ad)

    def test_sokulen_sayi_sablonda_tekrar_etmiyor(self):
        """Doktrin 4: kanonik varsayılan yalnız uçta durur.

        Söküm sırasında sayı ``placeholder``a KOPYALANMADI — yer tutucu
        sayının NEREDEN geleceğini söyler, sayının kendisini değil.
        """
        metin = _oku(SABLON)
        yer = re.findall(r'placeholder="server default applies[^"]*"', metin)
        assert yer, 'yer tutucu konmamis'
        for y in yer:
            assert not re.search(r'\d', y), (
                'yer tutucu sayi tasiyor (tek kaynak ihlali): %s' % y)


class TestOHD3114DevirKilidi:
    """Kapısız söküm yasağı: bu yedi alanın ön-dolusu YERİNDE kalmalı."""

    @pytest.mark.parametrize('ad', sorted(DEVIR))
    def test_kapisiz_sokum_yapilmadi(self, ad):
        metin = _oku(SABLON)
        etiketler = _inputlar(metin, ad)
        assert etiketler, '#%s alani sablondan kayboldu' % ad
        _n, gerekce = DEVIR[ad]
        assert any(re.search(r'\bvalue="', e) for e in etiketler), (
            '#%s on-dolusu UC KAPISI OLMADAN sokulmus. Olculdu: alan '
            'dusurulunce %s. Once app-api-uc kanonik varsayilani/422 kapisini '
            'kurmali (OH-D31-14 uc ayagi).' % (ad, gerekce))


class TestFix35APlaceholderI18n:
    """fix-35a devri: oksitleyici yoğunluğu yer tutucusu sözlüğe bağlandı."""

    def test_sablon_placeholder_i18n_imli(self):
        metin = _oku(SABLON)
        etiket = re.search(
            r'<input\b[^>]*\bid="oxidizer_density"[^>]*>', metin)
        assert etiket, '#oxidizer_density bulunamadi'
        assert 'data-i18n-placeholder="adv.ph.autoFilledReferenceDensity"' \
            in etiket.group(0), 'placeholder i18n imi yok'

    @pytest.mark.parametrize('anahtar', [
        'adv.ph.autoFilledReferenceDensity',
        'adv.ph.serverDefaultApplies',
    ])
    def test_sozlukte_iki_dil(self, anahtar):
        metin = _oku(I18N)
        assert metin.count("'%s':" % anahtar) == 2, (
            '%s EN+TR olarak tam iki kez bulunmali' % anahtar)


# ---------------------------------------------------------------------------
# a1 DEVRİ — ÖLÜ PANEL SÖKÜMÜNÜN BIRAKTIĞI HAYALET ALANLAR (ölçüldü,
# onarılmadı, KİLİTLENDİ)
# ---------------------------------------------------------------------------
#: ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11) — DEVİR KAPANDI.
#:
#: a1 (OH-D31-05, Berke karar dosyası §7 a) `#custom_fuel_mixture` ve
#: `#custom_fuel_config` panellerini sayfadan söktü ama onları OKUYAN JS
#: fonksiyonlarını bilerek bıraktı; ölçülen sonuç, bu 14 id'nin JS'ten
#: okunup sayfada üretilmemesiydi (hayalet envanteri 11 -> 25). Bu sınıf o
#: durumu SAYISIYLA kilitliyor ve kendi künyesinde "kusur onarılıp
#: fonksiyonlar silinince de kırmızı verir (o zaman gerekçeyle
#: çevrilecektir)" diyordu.
#:
#: D33'te onarıldı: dört ölü fonksiyon (`updateMixtureDensity`,
#: `addCompositionRow`, `removeCompositionRow`, `validateComposition`) ve
#: sökülen iki panelin `getElementById` okumaları SİLİNDİ; altı yabancı
#: bekçi dosyası gerekçeleriyle çevrildi. ÖLÇÜLDÜ (raw/OH/D33/arayuz-panel/
#: a1/once.json -> sonra.json, M1): advanced hayaletleri 16 -> 2, toplam
#: 25 -> 11, yani `test_d15_sablonlar_a3`in kayıtlı tabanına geri dönüldü
#: (taban YÜKSELTİLMEDİ, ÖK-22 gevşetmesi YOK).
#:
#: Yeni sözleşme: bu 14 id ne okunur ne üretilir; hiçbiri geri gelemez.
A1_HAYALET_ALANLARI = sorted([
    'composition_rows', 'composition_validation', 'custom_fuel_config',
    'custom_fuel_mixture', 'mixture_al2o3', 'mixture_aluminum',
    'mixture_carbon', 'mixture_density_calc', 'mixture_htpb',
    'mixture_other', 'mixture_paraffin', 'mixture_regression_est',
    'mixture_total', 'mixture_warning',
])


class TestA1OluPanelDevri:
    """a1'in ölü panel sökümünün bıraktığı hayalet alanlar — DEVİR KAPANDI."""

    @pytest.mark.parametrize('ad', A1_HAYALET_ALANLARI)
    def test_hayalet_alan_ne_okunuyor_ne_uretiliyor(self, ad):
        """ÇEVRİLDİ: artık ne okuma ne üretim kalmalı (hayalet yok)."""
        metin = _oku(SABLON)
        # Künye yorumları sökülen alanların ADINI anıyor; bekçi KODU ölçer.
        kod = re.sub(r'<!--.*?-->', '', metin, flags=re.S)
        kod = re.sub(r'//[^\n]*', '', kod)
        okunuyor = ("getElementById('%s')" % ad) in kod \
            or ("querySelector('#%s')" % ad) in kod
        uretiliyor = re.search(r'\bid="%s"' % re.escape(ad), kod) is not None
        assert not okunuyor and not uretiliyor, (
            "'%s' hayalet olarak geri geldi (okunuyor=%s, uretiliyor=%s) — "
            "OH-D32-11 sokumu geri alinmis" % (ad, okunuyor, uretiliyor))

    def test_devir_listesi_buyumedi(self):
        """Liste tam 14 kalmalı: kapanan devir yeniden açılmasın."""
        assert len(A1_HAYALET_ALANLARI) == 14

    def test_hayalet_envanteri_kayitli_tabana_dondu(self):
        """Ölçüm ayağı: `test_d15_sablonlar_a3` tabanı GEVŞETİLMEDEN tutuyor.

        ÖK-22: taban sayısı yükseltilemez. D33 onarımı sayıyı yükseltmek
        yerine GERÇEĞİ tabana geri çekti (25 -> 11). ÖH D37 OH-D33-06
        (hibrit-beyan denetçi şartı 2, ana model): kalan iki parametrik
        panel hayaleti söküldü → `advanced` 2 -> 0, toplam 11 -> 9
        (SIKILAŞTIRMA; test_d15 + test_d33 mandallarıyla birlikte).
        """
        import tests.test_d15_sablonlar_a3 as t15
        h = t15._hayaletler()
        assert sum(len(v) for v in h.values()) == sum(
            t15.HAYALET_TABAN.values()), h
        assert len(h['advanced']) == t15.HAYALET_TABAN['advanced'] == 0, (
            h['advanced'])
