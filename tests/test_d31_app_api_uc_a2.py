# -*- coding: utf-8 -*-
"""ÖH Dalga-31 · app-api-uc **aşama 2/2** bekçileri.

Her sınıf TEK bir kalemi kilitler. Hepsi ters-mutasyonla kırmızı
kanıtlanmıştır (``docs/scofield/raw/OH/D31/app-api-uc/a2/mutasyon.json``);
ölçümler ``a2/once.json`` (taban ``326d531f`` = a1'in sonrası) ile
``a2/sonra.json`` arasındadır.

DİKKAT — bu dosya, aşama-2'nin İLK koşusunda kesilen ajanın (16:08,
commit ``7e4a6610``) HİÇ yazmadığı bekçileri taşır: o koşu dört onarımı
koda yazdı ama tek bir bekçi ya da mutasyon kanıtı bırakmadı. Buradaki
sınıflar o onarımları ve bu koşunun kendi onarımını (P7B2-03) bağlar.
"""
import ast
import io
import os

import pytest

from hrma.app import app

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(KOK, 'hrma', 'app.py')

#: ``hrma/utils/input_guard.py`` merkez kapı sembolleri (TEK KAYNAK).
MERKEZ_ADLAR = ('input_guard', 'finite_number', 'finite_positive',
                'first_finite_positive', 'is_json_number', 'mm_to_m_read',
                '_mm_to_m_read')

#: P15B2-01 dağıtımının bu kulvara düşen app.py kapıları
#: (``docs/scofield/raw/OH/D30/ana_model/p15b201_dagitim.json``).
P15_KAPILAR = ('_build_pdf_motor_data', '_cfd_required_float',
               '_export_geometry_inconsistencies', '_num', '_numeric',
               '_reject_incomplete_3d_geometry', '_reject_unflyable_vehicle',
               '_request_number', '_sayi', '_sonlu', '_tasarim_hedefi_kapisi',
               '_toplam_impuls_ns', 'val')


@pytest.fixture()
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _app_kaynagi():
    return io.open(APP_PY, encoding='utf-8').read()


def _kapi_dugumleri(kaynak, adlar):
    """``app.py``deki ``def <ad>`` düğümleri (iç içe olanlar dâhil)."""
    agac = ast.parse(kaynak)
    for dugum in ast.walk(agac):
        if isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and dugum.name in adlar:
            yield dugum


def _merkeze_bagli(dugum):
    adlar = {n.id for n in ast.walk(dugum) if isinstance(n, ast.Name)}
    adlar |= {n.attr for n in ast.walk(dugum) if isinstance(n, ast.Attribute)}
    return any(m in adlar for m in MERKEZ_ADLAR)


# ===========================================================================
# P15B2-01 + OH-D30-08 — 15 yerel değer kapısı input_guard merkezine
# ===========================================================================
class TestP15B201YerelDegerKapilariMerkezde:
    """ÖLÇÜLDÜ (``once.json`` K1): 16 kapı tanımının **16'sı** merkeze
    bağsızdı, her biri kendi ``float()`` çevrimini yapıyordu; ikisi merkezle
    ÖLÇÜLEBİLİR biçimde ayrışıyordu (``davranis_ayrisma_sayisi = 2``).
    Onarımdan sonra: bağsız **0**, ayrışma **0**.
    """

    def test_onbes_kapinin_hepsi_merkeze_bagli(self):
        """Doktrin 4 — kural ikinci kez yazılmaz."""
        kaynak = _app_kaynagi()
        bagsiz = sorted(
            '%s:%d' % (d.name, d.lineno)
            for d in _kapi_dugumleri(kaynak, P15_KAPILAR)
            if not _merkeze_bagli(d))
        assert bagsiz == [], (
            'P15B2-01 dağıtımındaki şu kapılar kendi değer kuralını yeniden '
            'yazıyor (input_guard merkezine bağlı değil): %r' % (bagsiz,))

    def test_cfd_kapisi_merkezle_ayni_kadere_uguruyor(self):
        """``numpy.bool_`` ördeği: merkez reddediyorsa kapı da reddeder.

        ÖLÇÜLDÜ (``once.json`` K1 ``davranis_ayrismasi``): bu girdi yerel
        kapıdan GEÇİYOR (``__float__`` tanımlı olduğu için), merkezin
        ``finite_number``ı ise REDDEDİYORDU — aynı kötü girdinin iki kaderi.
        """
        from hrma import app as m
        from hrma.utils.input_guard import finite_number

        class _NpBool:
            class dtype:
                kind = 'b'

            def __float__(self):
                return 1.0

        deger = _NpBool()
        assert finite_number(deger) is None, 'merkez artık kabul ediyor'
        with pytest.raises(Exception):
            m._cfd_required_float({'x': deger}, 'x', 'test')

    def test_3d_geometri_kapisi_tel_bicimini_merkezle_ayni_okur(self):
        """``False`` bir JSON sayısı DEĞİLDİR; kapı onu 'eksik' saymamalı.

        ÖLÇÜLDÜ (``once.json`` K1): kapı ``False``u tel biçimi bakımından
        sayı sayıyordu (``not_a_number`` gerekçesi ÜRETMİYORDU), merkez
        ``is_json_number`` ise ``False`` diyordu.
        """
        from hrma import app as m
        from hrma.utils.input_guard import is_json_number

        assert is_json_number(False) is False
        hedef = list(m._3D_REQUIRED_GEOMETRY_FIELDS)[0]
        yuk = {a: 100.0 for a in m._3D_REQUIRED_GEOMETRY_FIELDS}
        yuk[hedef] = False
        with app.app_context():
            red = m._reject_incomplete_3d_geometry(yuk)
        assert red is not None, '%s=False kapıdan geçiyor' % hedef
        govde = red[0].get_json()
        gerekceler = {g.get('reason') for g in (govde.get('invalid_fields')
                                                or [])
                      if g.get('field') == hedef}
        assert 'not_a_number' in gerekceler, (
            '%s=False reddediliyor ama tel-biçimi gerekçesiyle değil: %r'
            % (hedef, gerekceler))


# ===========================================================================
# OH-D29-07 — tel-biçimi kuralının SON yerel kopyası
# ===========================================================================
class TestOHD2907TelBicimiKuraliTekKaynak:
    """KAPANDI (ÖH D32 fix-35d). Her iki ayak da ödendi.

    ÖDENEN ayak (D31 app-api-uc a2): kural TEK KAYNAKTAN okunuyor.

    BAŞLIK AYAĞI (D32 fix-35d, OH-D31-10 ana model hükmü): ``'293.15'``
    dizesi ``/api/oxidizer-properties``te **200** ile kabul edilirken
    ``/calculate_liquid``te **400** ile reddediliyordu; yani aynı tel
    biçiminin bedeli kullanıcının hangi sekmede olduğuna kalıyordu. D31'de
    bu kulvar kalemi TEK TARAFLI kapatmadı ve devir çapası bıraktı: "onaran
    kulvar sözleşmeyi tekilleştirdiğinde bu test kırmızıya düşer ve kalemin
    kapandığını haber verir." ÇAPA GÖREVİNİ YAPTI — fix-35d
    ``/api/oxidizer-properties`` kapısını kurunca kırmızıya düştü.

    ÇAPA ARTIK YÖN DEĞİŞTİRDİ: aynı iki uç, aynı gövde, AYNI hüküm ve AYNI
    makine-okur ad. Geri dönüş (bir ucun tel biçimini yeniden kabul etmesi)
    bu bekçiyi kırar.
    """

    def test_yerel_isinstance_kopyasi_kalmadi(self):
        """Ters-mutasyon burada AST üstünden ölçülür ve gerekçesi vardır:

        ölçüldü ki ``bool`` bu satıra HİÇ ULAŞMIYOR (üst kolda
        ``boolean_is_not_a_number`` ile reddediliyor), ``numpy.bool_`` ve
        ``numpy.float64`` ise iki kuralda AYNI kaderi görüyor. Yani kuralın
        iki yazımı ULAŞILABİLİR hiçbir girdide ayrışmıyor: bu bir DAVRANIŞ
        onarımı değil, TEK KAYNAK onarımıdır ve bekçisi de öyle olmalıdır.
        Davranışla ölçen bir bekçi burada sahte yeşil verirdi.
        """
        kaynak = _app_kaynagi()
        govde = ''
        for dugum in _kapi_dugumleri(kaynak, ('_form_band_kapisi',)):
            govde = ast.get_source_segment(kaynak, dugum) or ''
        assert govde, '_form_band_kapisi bulunamadı'
        satirlar = [s for s in govde.splitlines()
                    if 'isinstance(deger, (int, float))' in s
                    and not s.lstrip().startswith('#')]
        kural_satiri = [s for s in satirlar if 'sayi_zorunlu' in s]
        assert kural_satiri == [], (
            'tel-biçimi kuralı yerel isinstance ile yeniden yazılmış: %r'
            % (kural_satiri,))
        assert 'is_json_number' in govde, (
            'kapı merkez kuralı (input_guard.is_json_number) okumuyor')

    def test_baslik_kusuru_kapandi_iki_uc_ayni_hukum(self, istemci):
        """ÇEVRİLDİ (ÖH D32 fix-35d): iki uç, tek sözleşme.

        Eski hâli bir DEVİR ÇAPASIYDI ve ``(200, 400)`` bekliyordu — yani
        kusuru sayıyla sabitliyordu ki onarım gelince haber versin. Onarım
        geldi (``app.py::get_live_oxidizer_properties`` tel-biçimi kapısı,
        OH-D31-10 kanonu), çapa kırmızıya düştü ve YÖNÜ çevrildi: bekçi
        artık kusuru değil ONARIMI kilitler.
        """
        r1 = istemci.post('/api/oxidizer-properties',
                          json={'oxidizer_type': 'n2o',
                                'temperature': '293.15'})
        r2 = istemci.post('/calculate_liquid',
                          json={'thrust': 10000, 'chamber_pressure': '100',
                                'mixture_ratio': 2.5, 'fuel_type': 'rp1',
                                'oxidizer_type': 'lox'})
        assert (r1.status_code, r2.status_code) == (400, 400), (
            'bir uç sayı-benzeri dizeyi yeniden kabul ediyor (%s/%s) — '
            'OH-D29-07/OH-D31-10 kanonu geri alınmış'
            % (r1.status_code, r2.status_code))

        def _kod(yanit):
            g = yanit.get_json() or {}
            kayitlar = [k for k in (g.get('invalid_fields') or [])
                        if isinstance(k, dict)]
            assert kayitlar, g
            return kayitlar[0].get('reason')

        assert _kod(r1) == _kod(r2) == 'not_a_json_number', (
            'aynı kural iki adla yayımlanıyor: %r / %r'
            % (_kod(r1), _kod(r2)))


# ===========================================================================
# P12bB1-12 — ret gövdeleri kabul bandı künyesi taşır
# ===========================================================================
class TestP12bB112RetGovdesiBandKunyesiTasir:
    """ÖLÇÜLDÜ (``once.json`` K3): yedi ret gövdesinin **4'ünde**
    ``invalid_fields`` vardı ama kabul bandı künyesi YOKTU
    (``band_kunyesi_YOK_sayisi = 4/7``). Kullanıcı neyi ihlal ettiğini
    öğreniyor, neyin kabul edildiğini öğrenemiyordu. Onarımdan sonra 0/7.
    """

    YUKLER = (
        {'thrust': 'yirmi', 'burn_time': 5, 'initial_mass': 50,
         'final_mass': 25, 'drag_coefficient': 0.5, 'reference_area': 0.1},
        {'thrust': 1000, 'burn_time': 5, 'initial_mass': -1,
         'final_mass': 25, 'drag_coefficient': 0.5, 'reference_area': 0.1},
        {'thrust': 1000, 'burn_time': 5, 'initial_mass': 50,
         'final_mass': 25, 'drag_coefficient': float('nan'),
         'reference_area': 0.1},
        {'thrust': 1000, 'burn_time': 5, 'initial_mass': 50,
         'final_mass': 25, 'drag_coefficient': 0.5, 'reference_area': 'abc'},
    )

    @pytest.mark.parametrize('yuk', YUKLER)
    def test_trajectory_reddi_bandi_beyan_eder(self, istemci, yuk):
        g = istemci.post('/api/trajectory-analysis', json=yuk).get_json()
        alanlar = (g or {}).get('invalid_fields') or []
        assert alanlar, 'ret makine-okur alan listesi taşımıyor: %r' % (g,)
        kunyesiz = [a for a in alanlar
                    if not isinstance(a, dict)
                    or ('accepted_range' not in a and 'band_yok' not in a)]
        assert kunyesiz == [], (
            'ret gövdesi kabul bandını beyan etmiyor (ne accepted_range ne '
            'band_yok): %r' % (kunyesiz,))

    def test_bandi_olmayan_alan_BANT_YOK_der_sayi_uydurmaz(self, istemci):
        """Doktrin 1+4: bandı olmayan alan için aralık İCAT EDİLMEZ."""
        g = istemci.post('/api/trajectory-analysis',
                         json=self.YUKLER[0]).get_json()
        for a in (g or {}).get('invalid_fields') or []:
            # ``band_yok`` bir BAYRAKTIR (True/False), yokluk imi değil:
            # True ise alanın kanonik bandı yoktur ve aralık YAZILAMAZ.
            if a.get('band_yok') is True:
                assert a.get('accepted_range') in (None, []), (
                    'hem band_yok hem uydurma aralık: %r' % (a,))
            elif a.get('accepted_range'):
                assert a.get('basis'), (
                    'aralık yayımlanıyor ama hangi kaynaktan olduğu '
                    'yazmıyor: %r' % (a,))


# ===========================================================================
# OH-Z1-04 — iki akışkan ucunun ORTAK künye şeması
# ===========================================================================
class TestOHZ104OrtakKunyeSemasi:
    """KISMEN. ÖDENEN ayak: künye şeması.

    ÖLÇÜLDÜ (``once.json`` K4): ``/api/oxidizer-properties`` ile
    ``/api/get-propellant-properties`` aynı büyüklüğü yayımlarken künye
    şemaları ÜÇ akışkanın ÜÇÜNDE de ayrışıyordu
    (``kunye_semasi_AYRISAN_akiskan = 3``); onarımdan sonra 1 (``lox``,
    çünkü o akışkanda birinci uç 400 verir — ayrışma değil, ret).

    ÖDENMEYEN ayak: n2o'da **%5,37** yoğunluk farkı (742,93 ⟷ 785,10).
    İki ucun aynı ρ(T, faz) çözücüsüne bağlanması YAYIMLANAN SAYIYI
    değiştirir ve ``hrma/data/propellant_database.py``ye dokunur — brief
    o dosyayı bu kulvara KAPATIR (sivi/ihracat) ve Berke onayına bağlar.
    """

    def test_iki_uc_da_durum_beyani_tasir(self, istemci):
        g1 = istemci.post('/api/oxidizer-properties',
                          json={'oxidizer_type': 'n2o'}).get_json()
        g2 = istemci.post('/api/get-propellant-properties',
                          json={'propellant_name': 'n2o',
                                'propellant_type': 'oxidizer'}).get_json()
        for ad, g in (('oxidizer-properties', g1),
                      ('get-propellant-properties', g2)):
            govde = (g or {}).get('properties') or g or {}
            assert 'state_basis' in govde, (
                '%s künyesi bu sayıların HANGİ DURUMA ait olduğunu '
                'söylemiyor' % ad)
            assert govde['state_basis'].get('basis'), (
                '%s: state_basis.basis boş' % ad)

    def test_durum_adi_UYDURULMAZ_ucun_kendi_davranisidir(self, istemci):
        """İki uç AYRI soruya cevap verir; künye bunu ADIYLA söyler."""
        g1 = istemci.post('/api/oxidizer-properties',
                          json={'oxidizer_type': 'n2o',
                                'temperature': 298.15}).get_json()
        g2 = istemci.post('/api/get-propellant-properties',
                          json={'propellant_name': 'n2o',
                                'propellant_type': 'oxidizer'}).get_json()
        govde2 = (g2 or {}).get('properties') or g2 or {}
        assert (g1['properties']['state_basis']['basis']
                == 'requested_temperature')
        assert govde2['state_basis']['basis'] == 'storage_state'

    def test_YAYIMLANAN_SAYI_FARKI_DURUYOR_devir_capasi(self, istemci):
        """DEVİR ÇAPASI — %5,37 fark kapanmadı, ölçülebilir duruyor."""
        g1 = istemci.post('/api/oxidizer-properties',
                          json={'oxidizer_type': 'n2o',
                                'temperature': 298.15}).get_json()
        g2 = istemci.post('/api/get-propellant-properties',
                          json={'propellant_name': 'n2o',
                                'propellant_type': 'oxidizer'}).get_json()
        d1 = g1['properties']['density']
        d2 = ((g2 or {}).get('properties') or g2 or {}).get('density')
        fark = abs(d1 - d2) / d2 * 100.0
        assert fark > 1.0, (
            'iki uç artık aynı yoğunluğu veriyor (%.4f ⟷ %.4f) — OH-Z1-04 '
            'sayı ayağı kapanmış olabilir, kalemi yeniden hükme bağla'
            % (d1, d2))


# ===========================================================================
# P7B2-03 — /api/oxidizer-properties 'air' bölmesi SÖKÜLDÜ
# ===========================================================================
class TestP7B203HavaBolmesiSokuldu:
    """ÖLÇÜLDÜ (``once.json`` K5 / ``sonra.json``): ``air`` bu üründe
    oksitleyici değildir — ``normalize_oxidizer('air')`` **None**,
    ``OXIDIZER_LIQUID_BAND``da kaydı yok, ``advanced.html`` seçeneği
    ``disabled``, ``/calculate`` 400, ``/api/get-propellant-properties``
    422. Buna karşın YALNIZ bu uç 293,15 K'de **200** + 1,225 kg/m³
    yayımlıyordu; TANINAN bir oksitleyici (``n2o4``) ise 400 alıyordu.

    Bölme söküldü: bant İCAT EDİLMEDİ (D24'te açık bırakılan ÜST geçerlilik
    sınırı sorunu böylece bandı yazmadan kapandı).
    """

    @pytest.mark.parametrize('sicaklik', (50.0, 293.15, 5000.0))
    def test_air_artik_kardesleriyle_ayni_sozlesmede(self, istemci,
                                                     sicaklik):
        r = istemci.post('/api/oxidizer-properties',
                         json={'oxidizer_type': 'air',
                               'temperature': sicaklik})
        assert r.status_code == 400, (
            'air %g K\'de hâlâ sayı yayımlıyor (HTTP %s)'
            % (sicaklik, r.status_code))
        g = r.get_json() or {}
        assert g.get('error_code') == 'oxidizer_type_unknown', g
        assert (g.get('properties') or {}).get('density') is None

    def test_kabul_listesi_TEK_KAYNAKTAN_air_dusmus(self, istemci):
        """``accepted_values`` ``sorted(_ox_lazy)``dir; liste elle yazılmaz."""
        g = istemci.post('/api/oxidizer-properties',
                         json={'oxidizer_type': 'air'}).get_json()
        assert 'air' not in (g.get('accepted_values') or []), (
            'bölme söküldü ama kabul listesi hâlâ air diyor: %r'
            % (g.get('accepted_values'),))

    def test_olu_yardimci_kalmadi(self):
        """D30 dersi 18 — ölü kopya sahte yeşil üretir."""
        from hrma import app as m
        assert not hasattr(m, '_compressed_air_props'), (
            'bölme söküldü ama ideal-gaz yardımcısı ölü kod olarak duruyor')

    def test_gercek_oksitleyiciler_BIT_AYNI(self, istemci):
        """ÖK-22 — sağlıklı envanter gevşetilmez/bozulmaz."""
        beklenen = {'n2o': 742.9329783382176, 'h2o2': 1438.1}
        for ad, rho in beklenen.items():
            g = istemci.post('/api/oxidizer-properties',
                             json={'oxidizer_type': ad,
                                   'temperature': 298.15}).get_json()
            assert g['properties']['density'] == rho, (
                '%s yoğunluğu değişti: %r != %r'
                % (ad, g['properties']['density'], rho))


# ===========================================================================
# P7B4-23 — upload-csv satır sınırı (DEVİR ÇAPASI)
# ===========================================================================
class TestP7B423UploadCsvSatirSiniri:
    """KISMEN — başlığın bir yarısı ÇÜRÜDÜ, öbür yarısı DURUYOR.

    ÖLÇÜLDÜ (``once.json`` K6 + 600 000 satırlık koşu):

    * "10,3 MiB yanıt üretiyor" (istekten BÜYÜK yanıt) → **çürüdü**:
      600 000 satırda 7,91 MiB istek → 7,84 MiB yanıt, kat **0,992**.
    * "satır sınırı taşımıyor" → **doğrulandı**: depoda kanonik satır bandı
      yok; tek sınır ``MAX_CONTENT_LENGTH`` (32 MiB), o da BAYT sınırıdır.
    * "ayrıştırılan seri olduğu gibi geri yankılanıyor" → doğrulandı ama
      KUSUR DEĞİL: ``validation_panel.js:432`` tam olarak bu seriyi
      (``parsed.time``/``parsed.thrust``) Plotly ile çiziyor. Yankıyı
      kesmek ürünün eğrisini kör ederdi.

    Kanonik satır bandı ``parse_thrust_csv``ın yanında
    (``hrma/validation/user_data_validation.py``) tanımlanmalıdır; o dosya
    app-api-dogrulama kulvarınındır. Sayı UYDURULMADI.

    ÖH D32 / a2 — BEKÇİ YÖNÜ ÇEVRİLDİ (D31 dersi 20). Bant D32'de geldi
    (``THRUST_CSV_ROW_BAND``), yani "bant hâlâ YOK" iddiası artık KUSURU
    KORUYAN bir mandaldır. Testin kendi hata metni zaten bunu istiyordu
    ("kalemi yeniden hükme bağla"): aşağıdaki biçim bandın VARLIĞINI ve
    ayrıştırıcının yanında durduğunu kilitler. Gerileme (bandın sessizce
    kaldırılması) yine kırmızı verir.
    """

    def test_kanonik_satir_bandi_D32de_geldi(self):
        kaynak = io.open(
            os.path.join(KOK, 'hrma', 'validation',
                         'user_data_validation.py'),
            encoding='utf-8').read()
        agac = ast.parse(kaynak)
        bant_adlari = [
            h.id for d in ast.walk(agac)
            if isinstance(d, ast.Assign)
            for h in d.targets if isinstance(h, ast.Name)
            and 'MAX' in h.id.upper() and 'ROW' in h.id.upper()]
        assert 'THRUST_CSV_MAX_ROWS' in bant_adlari, (
            'kanonik satır bandı KAYBOLMUŞ (%r) — P7B4-23/OH-D31-12 '
            'gerilemiş olabilir' % (bant_adlari,))

    def test_yanit_istekten_buyuk_DEGIL_baslik_curutuldu(self, istemci):
        """Başlığın büyütme iddiası ölçümle çürütüldü (kat < 1)."""
        govde = ('time,thrust\n'
                 + '\n'.join('%.3f,%.1f' % (i * 0.001, 100.0 + i % 7)
                             for i in range(20000))).encode()
        r = istemci.post('/api/validation/upload-csv', data=govde,
                         content_type='text/csv')
        assert r.status_code == 200
        kat = len(r.get_data()) / float(len(govde))
        assert kat < 1.0, (
            'yanıt istekten büyük (kat=%.3f) — başlığın büyütme iddiası '
            'yeniden doğrulanmış olabilir' % kat)
