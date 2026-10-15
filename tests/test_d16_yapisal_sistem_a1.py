"""ÖH Dalga-16 · yapısal-sistem kulvarı · aşama 1 — onarım bekçileri.

Her sınıf TEK bir kalemi tutar ve o kalemin ÖLÇÜLEN kusurunu görür.
Ters-mutasyon kanıtı: onarım geçici olarak geri alındığında (kaynak
baytına ters-değiştirme, ``git checkout`` DEĞİL) bu testlerin kırmızıya
döndüğü ölçülmüştür; kanıt
``docs/scofield/raw/OH/D16/yapisal-sistem/a1/mutasyon.json``.

Taban ölçümü: ``.../a1/once.json`` · onarım sonrası ``.../a1/sonra.json``.
"""
import pytest

from hrma.analysis.pressure_vessel import PressureVesselAnalyzer


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


#: P16'nın kendi taban yükü (``raw/P16/H1-dogrulama-03.py``), yalnız
#: ``port_diameter`` -> ``port_diameter_initial`` (bu uç o adı okuyor;
#: takma ad D15'te adlı ret aldı).
P16_TABAN = {'burn_time': 10, 'mdot_ox': 1.9,
             'port_diameter_initial': 0.03, 'fuel_type': 'htpb'}


def _reg(istemci, **degis):
    r = istemci.post('/api/regression-analysis',
                     json={'motor_data': dict(P16_TABAN, **degis)})
    return r.status_code, r.get_json()


# =====================================================================
# P16B1-18 [YÜKSEK] — negatif süre / negatif katsayı NEGATİF port çapı ve
# NEGATİF regresyon hızı yayımlıyor; 1e9 süre 59,5 km'lik port basıyor
# =====================================================================
class TestP16B118RegresyonIsaretVeBant:

    def test_taban_govde_yesil_ve_hicbir_cap_negatif_degil(self, istemci):
        """Kontrol kolu: sağlıklı gövde 200 kalır ve eğri pozitiftir.

        ÖLÇÜLEN (once.json K6, taban): 200, port 30,0 -> 65,3035 mm,
        r_dot[0] = 2,9456191209002998 mm/s, negatif nokta 0."""
        kod, j = _reg(istemci)
        assert kod == 200, j
        rd = j['regression_data']
        assert min(rd['port_diameter']) > 0
        assert min(rd['regression_rate']) > 0
        assert min(rd['time']) >= 0

    def test_negatif_yanma_suresi_egri_yayimlatmaz(self, istemci):
        """ÖLÇÜLEN (once.json K6): ``burn_time = -10`` -> HTTP **200** ve
        ``port_diameter``ın 100 noktasından **74'ü negatif** (son değer
        −51,94392459810829 mm), ``time``ın 99 noktası negatif,
        ``warnings`` boş."""
        kod, j = _reg(istemci, burn_time=-10)
        assert kod == 422, j
        assert j['error'] == 'invalid_regression_input'
        alanlar = {k['field']: k for k in j['invalid_fields']}
        assert 'burn_time' in alanlar, alanlar
        assert alanlar['burn_time']['reason'] == 'not_positive'
        # Ret gerekçesi ALANIN KENDİ fiziğini söylemeli (tek ortak
        # "payda" cümlesi burada yanlış olurdu).
        assert 'burn time' in alanlar['burn_time']['detail'].lower()
        assert 'regression_data' not in j

    def test_sifir_yanma_suresi_de_reddedilir(self, istemci):
        """ÖLÇÜLEN: ``burn_time = 0`` -> 200, 100 nokta SABİT r_dot ve
        ``time[99] = 0,0``; sıfır süreli yanmadan eğri çıkıyordu."""
        kod, j = _reg(istemci, burn_time=0)
        assert kod == 422, j
        assert any(k['field'] == 'burn_time' and k['reason'] == 'not_positive'
                   for k in j['invalid_fields'])

    def test_negatif_regresyon_katsayisi_negatif_hiz_yayimlatmaz(
            self, istemci):
        """ÖLÇÜLEN: ``regression_a = -3,68e-5`` -> 200, ``regression_rate``
        baştan sona negatif (−2,9456191209002998 mm/s) ve aynı 74 negatif
        port çapı. r_dot = a·G**n; a <= 0 yanan bir yüzeyde olmaz."""
        kod, j = _reg(istemci, regression_a=-3.68e-5)
        assert kod == 422, j
        assert any(k['field'] == 'regression_a' and
                   k['reason'] == 'not_positive'
                   for k in j['invalid_fields']), j['invalid_fields']

    def test_bant_disi_yanma_suresi_reddedilir_ve_bant_beyan_edilir(
            self, istemci):
        """ÖLÇÜLEN: ``burn_time = 1e9`` -> 200 ve ``port_diameter[99] =
        59.508.083,5 mm`` (59,5 km). Bant İCAT EDİLMEZ: deponun kanonik
        ``motor_validator.limits['burn_time']`` bandı (300 s) okunur —
        hibrit ``/calculate`` aynı sayıyı zaten reddediyor."""
        from hrma.validation.motor_validation import motor_validator
        ust = float(motor_validator.limits['burn_time']['max'])
        kod, j = _reg(istemci, burn_time=1e9)
        assert kod == 422, j
        kayit = [k for k in j['invalid_fields'] if k['field'] == 'burn_time']
        assert kayit and kayit[0]['reason'] == 'out_of_range', j
        # ÖH D27 a2 / OH-D25-23 — BEKÇİ ÇEVRİLDİ. D26'da onarımı
        # ENGELLEYEN satır tam olarak buydu (``KeyError:
        # 'allowed_range'``); engel kardeş dalın bu dosyaya
        # dokunmasıydı, D27'de o dal birleşti ve ölçüldü ki hiçbir
        # kardeş dal burayı tutmuyor (``a2/kardes_dal.json``).
        assert kayit[0]['accepted_range'][1] == pytest.approx(ust)
        # Bandın İÇİ yeşil kalmalı — kapı yeni bir alt/üst uç doğurmaz.
        assert _reg(istemci, burn_time=ust)[0] == 200

    @pytest.mark.parametrize('alan,deger', [
        ('fuel_density', -920.0),
        ('grain_length', -0.3),
        ('chamber_length', -0.3),
        ('port_diameter_final', -0.05),
    ])
    def test_tanim_geregi_pozitif_alanlar_reddedilir(self, istemci,
                                                     alan, deger):
        """ÖLÇÜLEN (once.json K6): dördü de HTTP 200 ile eğri yayımlıyordu.
        Hiçbiri yeni bir EŞİK değildir — yoğunluk, uzunluk ve çap tanım
        gereği pozitiftir."""
        kod, j = _reg(istemci, **{alan: deger})
        assert kod == 422, (alan, j)
        assert any(k['field'] == alan and k['reason'] == 'not_positive'
                   for k in j['invalid_fields']), j['invalid_fields']

    def test_regresyon_usu_n_TANIM_bandiyla_reddedilir(self, istemci):
        """ÖH D20 / P5B4-05 — BU BEKÇİ ÇEVRİLDİ (gerekçe aşağıda).

        D16'daki hâli ``test_regresyon_usu_n_icin_bant_ICAT_EDILMEZ``
        adıyla ``assert _reg(istemci, regression_n=-0.555)[0] == 200``
        diyordu; gerekçesi "n negatifken sonuç hâlâ pozitiftir, yani
        'tanım gereği pozitif' gerekçesi n için KURULAMAZ; ona bant
        koymak yeni EŞİK icat etmek olurdu (Berke kararı)".

        NEDEN ÇEVRİLDİ. Berke kararı "yeni EŞİK icat etme"dir; (0, 1)
        bandı bir eşik değil KORELASYONUN TANIMIDIR:

        1. ``r = a·G^n`` bu modülde difüzyon-limitli hibrit regresyondur
           (modül docstring'i; Marxman & Gilbert 1963; Sutton & Biblarz
           9. baskı Böl. 16). Modelin tanımlayıcı içeriği regresyonun akı
           ile ARTMASIDIR. ``n <= 0`` bunu TERSİNE çevirir — akı arttıkça
           regresyon azalır — yani koşan artık o model değildir. Bu,
           yoğunluğun pozitifliğiyle aynı cinsten bir İŞARET koşuludur,
           kalibrasyon değil.
        2. ``n > 1`` regresyonun akıdan HIZLI büyümesidir; yayımlanmış
           hiçbir fit orada değildir (deneysel bant 0,3-0,8; bu modülün
           kendi tablosu 0,498-0,620).
        3. Uçlar ASİMETRİKTİR (ÖH D26 / OH-D25-15): alt uç DIŞLAYICI
           (işaret koşulu), üst uç KAPSAYICI. n = 1,0 akıyla TAM ORANTILI
           nötr sınırdır — d(r/G)/dG = a(n-1)G^(n-2) orada tam sıfırdır,
           yani reddedilen bölgenin içi değil KENARIDIR; kabul edilir.
           Hiçbir uç ayarlanmış bir sayı değildir.

        ÖLÇÜLDÜ (taban 14acd1d, ``docs/scofield/raw/OH/D20/yapisal-sistem/
        a1/once.json``): ``regression_n = -0,555`` -> HTTP **200**,
        ``regression_rate[0] = 0,0006564887612192 mm/s`` (sağlıklı kolda
        2,062853288585 mm/s), ``warnings`` BOŞ; ``regression_n = 12`` ->
        ``port_diameter[-1] = 4,778085645664e+35 mm``. Defter kalemi
        P5B4-05 n'i ADIYLA sayar ("a, n, rho_f, D, L için hiçbir
        işaret/aralık kapısı yok").
        """
        kod, j = _reg(istemci, regression_n=-0.555)
        assert kod == 422, j
        assert j['error'] == 'non_physical_regression_input'
        assert any(k['field'] == 'regression_n'
                   for k in j['invalid_fields']), j

    def test_n_bandinin_ici_hala_200(self, istemci):
        """Kapı yeni bir UYGULAMA eşiği doğurmaz: tablonun kendi n
        değerleri ve bandın uçlarına yakın değerler geçmeye devam eder."""
        for n in (0.498, 0.555, 0.62, 0.8, 0.999):
            assert _reg(istemci, regression_n=n)[0] == 200, n


# =====================================================================
# P16B1-06 kardeşi — ÇÖZÜCÜNÜN TÜRETTİĞİ geometri de bantlıdır
# =====================================================================
class TestP16B106TuretilenGeometriBandi:

    def test_1e9_katsayi_milyar_metrelik_port_yayimlatmaz(self, istemci):
        """ÖLÇÜLEN (once.json K5): ``regression_a = 1e9`` girdi kapısından
        geçiyor (işareti ve sonluluğu meşru) ve uç HTTP **200** ile
        ``port_diameter`` tepe değeri **11.324.403.209.369,77 mm** olan bir
        eğri yayımlıyordu. P16 hükmü: kapı GİRDİye uygulanmış, çözücünün
        TÜRETTİĞİ çapa uygulanmamış."""
        kod, j = _reg(istemci, regression_a=1e9)
        assert kod == 422, j
        assert j['error'] == 'regression_geometry_out_of_range'
        kayit = j['invalid_fields'][0]
        assert kayit['field'] == 'port_diameter'
        assert kayit['peak_value_mm'] > 1000.0
        assert 'regression_a' in j['fields_involved']

    def test_bant_kaynagi_deponun_kanonik_tablosudur(self, istemci):
        """Tek kaynak: ret gövdesindeki bant ``motor_validator.limits``
        ile BİREBİR aynı olmalı; ikinci bir sayı yazılamaz."""
        from hrma.validation.motor_validation import motor_validator
        bant = motor_validator.limits['port_diameter']
        _, j = _reg(istemci, regression_a=1e9)
        kayit = j['invalid_fields'][0]
        # ÖH D27 a2 / OH-D25-23 — kanonun ``_m`` birim kardeşi.
        assert kayit['accepted_range_m'] == [float(bant['min']),
                                             float(bant['max'])]


# =====================================================================
# P16B1-04 [YÜKSEK] — boş gövdeden tam regresyon eğrisi (D15'te kapandı;
# bekçi ÖK-05 gereği burada tutulur, kapı geri açılamasın)
# =====================================================================
class TestP16B104BosGovde:

    @pytest.mark.parametrize('govde', [{}, {'motor_data': {}},
                                       {'motor_data': {'fuel_type': 'htpb'}}])
    def test_bos_govdeden_egri_cikmaz(self, istemci, govde):
        """P16 ölçümü (raw/P16/H1-hukum.md): ``{}`` ve
        ``{"motor_data":{}}`` md5'i BİREBİR aynı 100 noktalı eğri
        veriyordu (r_dot 2,062853288584799 -> 1,006489646544747; port
        30,0 -> 57,265776718965974 mm). Bugün (taban 6fde52b) üçü de 422;
        bu bekçi o kapının geri açılmasını yakalar."""
        r = istemci.post('/api/regression-analysis', json=govde)
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        assert 'regression_data' not in (r.get_json() or {})


# =====================================================================
# OH-D15-12 [ORTA] — kriyojenik künye zincirinin ÜÇ kümesi de kanonik adla
# sorulur; takma adla çağıran kardeşiyle AYNI hükmü alır
# =====================================================================
#: (kanonik, takma ad) — ``materials_db.ALIASES`` tablosundan.
KRIYO_CIFTLER = [
    ('ss_304', 'stainless_304'), ('ss_304', 'steel_304'),
    ('ss_316', 'stainless_316'), ('ss_316', 'steel_316'),
    ('aluminum_6061', 'aluminum'), ('aluminum_6061', 'al_6061'),
    ('al_7075_t6', 'al_7075'), ('al_2024_t3', 'al_2024'),
    ('inconel_718', 'inconel'), ('inconel_718', 'in718'),
    ('inconel_625', 'in625'), ('cucrzr', 'cu_cr_zr'),
    ('brass_c360', 'brass'), ('brass_c360', 'c360'),
    ('beryllium_copper_c17200', 'becu'),
    ('beryllium_copper_c17200', 'c17200'),
    ('carbon_carbon', 'c-c'),
    ('ablative', 'silica_phenolic'), ('ablative', 'silica-phenolic'),
]

KRIYO_YUK = dict(meop_bar=60, inner_diameter_mm=150, wall_thickness_mm=5,
                 temperature_K=90)


def _kriyo_kunye(malzeme):
    r = PressureVesselAnalyzer().analyze(material=malzeme, **KRIYO_YUK)
    metin = ' '.join(w for w in r['warnings'] if 'Cryogenic service' in w)
    return {
        'muaf': 'stay ductile when cold' in metin,
        'muaf_degil': 'NOT among the' in metin,
        'her_sicaklikta_gevrek': 'BRITTLE AT EVERY TEMPERATURE' in metin,
        'dbtt': 'brittle fracture risk' in metin,
        'cozulemedi': 'could not resolve the material name' in metin,
        'status': r['status'],
    }


class TestOHD1512KriyoKunyeTakmaAd:

    @pytest.mark.parametrize('kanonik,takma', KRIYO_CIFTLER)
    def test_takma_ad_kanonikle_ayni_kriyo_hukmunu_alir(self, kanonik, takma):
        """ÖLÇÜLEN (once.json K7, 90 K LOX tankı): **19/19** çiftte künye
        AYRIŞIYORDU. P9B4-08 yalnız DBTT kümesini kanonik ada çözmüştü;
        ``CRYO_EXEMPT_MATERIALS`` ve ``ALWAYS_BRITTLE_MATERIALS`` HÂLÂ ham
        kullanıcı argümanıyla karşılaştırıldığı için her takma ad
        fail-closed "muaf DEĞİLSİN" dalına düşüyor (``muaf_degil = True``),
        kanonik kardeşi ise doğru künyeyi alıyordu."""
        assert _kriyo_kunye(kanonik) == _kriyo_kunye(takma)

    def test_muafiyet_ailesi_muaf_kunyesini_alir(self):
        """Yön kontrolü: östenitik/alüminyum/nikel ailesi UHA-51 dalına
        düşmeli (takma adla da)."""
        for ad in ('stainless_304', 'aluminum', 'in718', 'becu'):
            k = _kriyo_kunye(ad)
            assert k['muaf'] and not k['muaf_degil'], (ad, k)

    def test_her_sicaklikta_gevrek_ailesi_muafiyet_almaz(self):
        """``c-c`` ve ``silica_phenolic`` takma adları "her sıcaklıkta
        gevrek" künyesini almalı — ölçümde ikisi de o dala HİÇ
        düşmüyordu."""
        for ad in ('c-c', 'silica_phenolic'):
            k = _kriyo_kunye(ad)
            assert k['her_sicaklikta_gevrek'], (ad, k)
            assert not k['muaf'], (ad, k)

    def test_cozulemeyen_ad_hic_hukum_uretmez(self):
        """Fail-closed ters yön: tanınmayan ad muafiyet ALMAZ — bu modülde
        hüküm hiç üretilmez (``get_material`` adlı ``ValueError``)."""
        with pytest.raises(ValueError, match='Unknown material'):
            PressureVesselAnalyzer().analyze(material='peynir', **KRIYO_YUK)


# =====================================================================
# OH-Z3-02 [ORTA] — /api/advanced-analysis cidar/malzeme asimetrisi
# =====================================================================
ADV_MOTOR = {'chamber_pressure': 40, 'chamber_temperature': 3000,
             'chamber_diameter': 0.1, 'chamber_length': 0.5,
             'burn_time': 10, 'mdot_total': 1.0}


class TestOHZ302AdvancedCidarVeBeyan:

    def test_cidarsiz_tam_motor_hukum_uretmez(self, istemci):
        """ÖLÇÜLEN (once.json K8): ``wall_thickness`` HİÇ gönderilmeyen tam
        motor gövdesi HTTP **200** alıyor ve yanıt 0,005 m'lik uydurma
        cidarla (``design_parameters.wall_thickness = 5.0`` mm) tam bir ısı
        transferi hükmü basıyordu — 0,005 m GÖNDERİLEN gövdeyle birebir
        aynı yanıt. Kardeş uç aynı gövdeyi 422 ile reddediyordu."""
        r = istemci.post('/api/advanced-analysis',
                         json={'analysis_types': ['heat_transfer'],
                               'motor_data': dict(ADV_MOTOR)})
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j['error'] == 'incomplete_thermal_input'
        assert j['missing_fields'] == ['wall_thickness']

    def test_bos_govde_missing_listesi_kardesle_ayni(self, istemci):
        """ÖLÇÜLEN: boş gövdede kardeş uç 9 alan sayıyor, bu rota 8 —
        eksik olan tam da ``wall_thickness``tı."""
        a = istemci.post('/api/advanced-analysis',
                         json={'analysis_types': ['heat_transfer'],
                               'motor_data': {}}).get_json()
        b = istemci.post('/analyze_thermal_safety', json={}).get_json()
        assert a['missing_fields'] == b['missing_fields']
        assert 'wall_thickness' in a['missing_fields']

    def test_varsayilana_dusen_malzeme_ve_sogutma_BEYAN_edilir(self,
                                                              istemci):
        """ÖK-19: varsayılan kalacaksa beyan ZORUNLU. ÖLÇÜLEN: yanıtta ne
        ``defaults_applied`` ne başka bir künye alanı vardı."""
        r = istemci.post('/api/advanced-analysis',
                         json={'analysis_types': ['heat_transfer'],
                               'motor_data': dict(ADV_MOTOR),
                               'wall_thickness': 0.005})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        beyan = r.get_json()['results']['heat_transfer_defaults_applied']
        assert {k['field'] for k in beyan} == {'material_type',
                                               'cooling_type'}

    def test_tam_govde_beyan_alani_HIC_eklemez(self, istemci):
        """Sağlıklı gövde bit-aynı kalır: düşüş yoksa alan yayımlanmaz."""
        r = istemci.post('/api/advanced-analysis',
                         json={'analysis_types': ['heat_transfer'],
                               'motor_data': dict(ADV_MOTOR),
                               'wall_thickness': 0.005,
                               'material_type': 'steel',
                               'cooling_type': 'natural'})
        assert r.status_code == 200
        assert 'heat_transfer_defaults_applied' not in r.get_json()['results']

    def test_sayi_olmayan_cidar_ham_500_vermez(self, istemci):
        """Fail-closed: ``float()`` çökmesi ham 500'e düşmemeli."""
        r = istemci.post('/api/advanced-analysis',
                         json={'analysis_types': ['heat_transfer'],
                               'motor_data': dict(ADV_MOTOR),
                               'wall_thickness': 'kalin'})
        assert r.status_code == 422, r.status_code
        assert r.get_json()['invalid_fields'][0]['field'] == 'wall_thickness'
