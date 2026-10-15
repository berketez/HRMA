"""ÖH D32 · app-api-uc a1 bekçileri.

Kapsanan kalemler:

* **OH-D31-13 / P12bB1-20 (uç ayağı)** — ÖK-21: ``/calculate`` alanı
  gönderilmediğinde ucun KENDİ varsayılanını uyguluyorsa bunu
  ``defaults_applied`` künyesinde ADIYLA söyler; sayı çağrı yerinde değil
  ``_CALCULATE_UC_VARSAYILANLARI`` tablosunda tek kez durur (Doktrin 4).
* **OH-D30-11 (devir çapası)** — patlayıcı ekseninin kazanılmamış hükmü
  ÖLÇÜLDÜ ve bu aşamada ONARILMADI; kusur bekçiyle kilitlenir ki sonraki
  aşama onu sessizce kaybetmesin.
* **OH-Z1-04 / OH-D29-07 (devir çapaları)** — bu aşamanın sahasında
  ONARILMAYAN, ölçülmüş durumun kilidi.
"""
import ast
import os

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(KOK, 'hrma', 'app.py')


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


#: ``/calculate``in ÖK-21 kapsamındaki taban gövdesi: YALNIZ kullanıcının
#: gerçekten doldurduğu alanlar. Geri kalan her şey ucun varsayımıdır.
TABAN_GOVDE = {
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
    'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}


def _kunye(govde):
    return {k['field']: k for k in (govde.get('defaults_applied') or [])
            if isinstance(k, dict) and 'field' in k}


class TestOHD3113UcKapisi:
    """ÖK-21 (b) kolu: uygulanan uç varsayılanı ADIYLA beyan edilir."""

    def test_uygulanan_uc_yedegi_kunyede_adiyla_gecer(self, istemci):
        r = istemci.post('/calculate', json=TABAN_GOVDE)
        assert r.status_code == 200
        kunye = _kunye(r.get_json())
        # ÖLÇÜLDÜ (once.json K2, taban dd1dcddc): bu gövdede künyede ANILAN
        # alan sayısı 1'di (cooling_channels); l_star/expansion_ratio/
        # chamber_diameter_input/contraction_ratio/oxidizer_temp/
        # tank_pressure ve duş başlığı üçlüsü SESSİZCE uygulanıyordu.
        for alan in ('l_star', 'expansion_ratio', 'chamber_diameter_input',
                     'contraction_ratio', 'oxidizer_temp', 'tank_pressure',
                     'target_velocity', 'hole_diameter_min',
                     'hole_diameter_max'):
            assert alan in kunye, (
                "%s uygulandı ama defaults_applied künyesinde YOK" % alan)
            assert kunye[alan]['reason'] in (
                'not_supplied', 'not_supplied_solver_derives')
            assert kunye[alan].get('message')

    def test_kullanici_gonderdiyse_kunye_yazilmaz(self, istemci):
        """Beyan yalnız GERÇEKTEN düşüş olduğunda çıkar (çapa korunur)."""
        govde = dict(TABAN_GOVDE, l_star=1.4, tank_pressure=48.0)
        r = istemci.post('/calculate', json=govde)
        assert r.status_code == 200
        kunye = _kunye(r.get_json())
        assert 'l_star' not in kunye
        assert 'tank_pressure' not in kunye

    def test_kunye_degeri_ucun_KULLANDIGI_sayidir(self, istemci):
        """Tek kaynak: beyan edilen sayı tablodan gelir, elle yazılmaz."""
        from hrma.app import _CALCULATE_UC_VARSAYILANLARI
        r = istemci.post('/calculate', json=TABAN_GOVDE)
        kunye = _kunye(r.get_json())
        for alan, kayit in kunye.items():
            if alan in _CALCULATE_UC_VARSAYILANLARI:
                yedek, birim, gerekce = _CALCULATE_UC_VARSAYILANLARI[alan]
                assert kayit['value'] == yedek
                assert kayit['reason'] == gerekce

    def test_ayni_alan_iki_kez_beyan_edilmez(self, istemci):
        """Künye tekildir (``of_ratio`` gövdede iki okuma yerine sahip)."""
        r = istemci.post('/calculate', json=TABAN_GOVDE)
        assert r.status_code == 200
        adlar = [k['field'] for k in (r.get_json().get('defaults_applied')
                                      or []) if isinstance(k, dict)]
        assert len(adlar) == len(set(adlar)), adlar

    def test_sayi_cagri_yerinde_YAZILMAZ(self):
        """AST: ÖK-21 alanları ``data.get('<ad>', <sayı>)`` ile okunamaz.

        Kusuru geri getiren en olası yol, ileride birinin tabloyu atlayıp
        gövdeye yeniden sayı yazmasıdır; bu bekçi o yolu kapatır.
        """
        agac = ast.parse(open(APP_PY, encoding='utf-8').read())
        fn = [n for n in ast.walk(agac)
              if isinstance(n, ast.FunctionDef) and n.name == 'calculate'][0]
        from hrma.app import _CALCULATE_UC_VARSAYILANLARI
        ihlal = []
        for d in ast.walk(fn):
            if not (isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr == 'get' and len(d.args) == 2):
                continue
            if not (isinstance(d.args[0], ast.Constant)
                    and d.args[0].value in _CALCULATE_UC_VARSAYILANLARI):
                continue
            if isinstance(d.args[1], ast.Constant) and \
                    d.args[1].value is not None:
                ihlal.append((d.lineno, d.args[0].value))
        assert not ihlal, (
            'ÖK-21 alanı gövdede sayıyla okunuyor (tablo atlandı): %s'
            % ihlal)


class TestOHD3011DevirCapasi:
    """OH-D30-11 — ÖH D35 / OH-ON-06'DA KAPANDI; ÇAPA GEREKÇEYLE ÇEVRİLDİ.

    Kusur (ÖLÇÜLDÜ, ``once.json`` K1, taban ``dd1dcddc``): ``apcp`` (bir
    KATI yakıt) motor tipi hiç verilmeden ``hybrid_n2o`` sınıfını ve
    22,2775 kg TNT eşdeğerini alıyor; aynı istek ``motor_type='solid'`` ile
    21,0 kg veriyor. ``kndx``, ``knsu`` ve tabloda hiç bulunmayan bir ad da
    aynı sayıyı alıyor. Yani kullanıcının HİÇ vermediği bir alanın uç
    varsayılanı yayımlanan güvenlik mesafesini seçiyor.

    Bu sınıfın kendi belgesi çevrilmeyi ŞART koşuyordu ("patlayıcı ekseni
    geri çekildiğinde bu sınıf gerekçeyle ÇEVRİLİR") ve ÖH D35 /
    onemli-pdf-guvenlik a1 o ayağı ödedi: ``motor_type``ın ``'hybrid'``
    varsayılanı kalktı; kimlik kazanılmazsa TNT eşdeğeri, patlama
    mesafeleri ve QD şartları YAYIMLANMAZ (HTTP 200 korunur, eksen
    ``explosive_verdict_withheld_because`` ile adıyla geri çekilir).

    İddialar GEVŞETİLMEDİ: aşağıdaki iki bekçi artık kusurun GİTTİĞİNİ
    ve kimlik verildiğinde hükmün hâlâ KAZANILDIĞINI kilitliyor.
    Kanıt: ``docs/scofield/raw/OH/D35/onemli-pdf-guvenlik/a1/``.
    """

    TABAN = {'chamber_pressure': 40, 'propellant_mass': 50,
             'chamber_diameter': 0.1, 'wall_thickness': 0.005}

    def _tnt(self, istemci, ek):
        r = istemci.post('/analyze_safety', json=dict(self.TABAN, **ek))
        assert r.status_code == 200
        j = r.get_json()
        pat = ((j.get('safety_analysis') or {}).get('explosive_hazards')
               or {})
        return j, pat

    def test_KUSUR_GITTI_cozulemeyen_ad_hibrit_hukmu_ALMIYOR(
            self, istemci):
        """Eski iddia: ``apcp`` + motor tipi yok -> ``hybrid_n2o`` ve
        22,277508917819734 kg TNT. Artık hiçbir sınıf ve hiçbir TNT
        yayımlanmıyor."""
        j, pat = self._tnt(istemci, {'propellant_type': 'apcp'})
        assert 'motor_type' not in (j.get('defaults_applied') or []), (
            'uç, uygulamadığı bir varsayılanı künyede sayıyor')
        assert pat.get('explosive_class') is None, (
            'katı bir yakıt adı hâlâ hibrit sınıfını alıyor: %r'
            % pat.get('explosive_class'))
        assert 'tnt_equivalent_kg' not in pat, (
            'motor_type verilmeden hâlâ TNT eşdeğeri yayımlanıyor: %r'
            % pat.get('tnt_equivalent_kg'))
        assert pat.get('explosive_verdict_withheld_because'), (
            'eksen sessizce düştü — geri çekme gerekçesi yok')
        # Kardeş eksenler hüküm vermeye DEVAM ediyor (422 değil 200).
        assert j.get('status') == 'success'

    def test_cozulemeyen_ad_HIBRIT_verilince_de_uydurma_sinif_ALMAZ(
            self, istemci):
        """``motor_type='hybrid'`` verildiğinde sınıf KAZANILIR ve
        oksitleyicinin kendi türetimiyle gelir — eski kusurun sayısı
        (22,2775 kg) bu kez HAK EDİLMİŞ bir sayıdır, çünkü kullanıcı
        motorun hibrit olduğunu SÖYLEMİŞTİR."""
        _j, pat = self._tnt(istemci, {'propellant_type': 'apcp',
                                      'motor_type': 'hybrid'})
        assert pat.get('explosive_class') == 'hybrid_n2o'
        assert pat.get('tnt_equivalent_kg') == pytest.approx(
            22.277508917819734, rel=1e-9)

    def test_motor_tipi_verilince_sayi_KAZANILIR(
            self, istemci):
        """Fail-closed'ın bedeli "hiç hüküm yok" değildir: kimlik
        verildiğinde katı motor kendi sınıfını ve sayısını alır."""
        _, pat = self._tnt(istemci, {'propellant_type': 'apcp',
                                     'motor_type': 'solid'})
        assert pat.get('explosive_class') == 'composite'
        assert pat.get('tnt_equivalent_kg') == pytest.approx(21.0, rel=1e-9)


class TestOHZ104DevirCapasi:
    """OH-Z1-04 — iki akışkan ucu: künye şeması ÖDENDİ, sayı farkı DURUYOR.

    Berke/Astra hükmü (15 Eyl): 785 → 745 EŞİTLENMEZ; fark hata değil,
    DURUM farkıdır ve tek durum çözücüsü D32 ``sivi`` kulvarının işidir
    (OH-D31-11). Buradaki bekçi, bu kulvarın o sayıya DOKUNMADIĞINI ve iki
    ucun künye şemasını taşımaya devam ettiğini kilitler.
    """

    def test_iki_uc_da_durum_kunyesi_tasiyor(self, istemci):
        r1 = istemci.post('/api/oxidizer-properties',
                          json={'oxidizer_type': 'n2o', 'temperature': 298.15})
        r2 = istemci.post('/api/get-propellant-properties',
                          json={'oxidizer': 'n2o', 'fuel': 'htpb'})
        assert r1.status_code == 200 and r2.status_code == 200
        for r in (r1, r2):
            sb = (r.get_json().get('properties') or {}).get('state_basis')
            assert isinstance(sb, dict) and sb.get('basis'), (
                'D31 a2 ortak künye şeması kayboldu')

    def test_sayi_farki_DURUM_farkidir_esitlenmedi(self, istemci):
        """Berke/Astra hükmü (15 Eyl): 785 → 745 EŞİTLENMEZ.

        ÖLÇÜLDÜ (once.json K3, taban ``dd1dcddc``): AYNI uç, T istenirse
        742,93 kg/m³ (298,15 K), T'siz çağrıda 785,10 kg/m³ — fark hata
        değil DURUM farkıdır ve T'siz kolun varsayımı (293,15 K) yanıtta
        AÇIKÇA yayımlanır. Tek durum çözücüsü D32 ``sivi`` kulvarının
        kalemidir (OH-D31-11); bu kulvar sayıya DOKUNMAZ.
        """
        r_t = istemci.post('/api/oxidizer-properties',
                           json={'oxidizer_type': 'n2o',
                                 'temperature': 298.15})
        r_0 = istemci.post('/api/oxidizer-properties',
                           json={'oxidizer_type': 'n2o'})
        p_t = r_t.get_json()['properties']
        p_0 = r_0.get_json()['properties']
        # SAYI LİTERALİ BİLEREK YAZILMADI (D31 dersi 20): tek durum
        # çözücüsü D32 ``sivi`` kulvarının YETKİLİ onarımıdır ve bu iki
        # sayıyı değiştirebilir; burada sayıyı mandallamak o onarımı
        # kilitleyen bir bekçi olurdu. Ölçülen değerler kanıt dosyasında
        # durur (``D32/app-api-uc/a1/once.json`` K3: 742,9330 ⟷ 785,1040).
        # Kilitlenen ŞEY sözleşmedir: iki farklı DURUM iki farklı sayı
        # verir ve T'siz kolun varsayımı SAKLANMAZ.
        assert p_t['density'] != p_0['density'], (
            'iki durum sessizce eşitlendi (Berke/Astra 15 Eyl hükmü: '
            'eşitleme YOK, durum ADIYLA yayımlanır)')
        assert p_0['state_basis']['temperature_K'] == pytest.approx(293.15)
        assert r_0.get_json()['temperature'] == pytest.approx(293.15)
        assert p_t['state_basis']['temperature_K'] == pytest.approx(298.15)


class TestOHD2907DevirCapasi:
    """OH-D29-07 — '293.15' dizesi: ÇAPA ATEŞLENDİ, kalem KAPANDI.

    Bu kulvar (app-api-uc a1) kalemi kendi sahası dışında bulmuştu
    (``hrma/validation`` ve ``hrma/utils`` D29 kulvar bölmesiyle kapalıydı)
    ve devir çapası bırakmıştı: bekçi yalnız ÖLÇÜLEN ayrışmayı kilitliyordu
    (``/api/oxidizer-properties`` dizeyi 200 ile kabul, ``/calculate_liquid``
    400 ile ret), ki onaran kulvar sözleşmeyi tekilleştirdiğinde kırmızıya
    düşsün ve kapanışı haber versin.

    ÇAPA GÖREVİNİ YAPTI (ÖH D32 fix-35d, 15 Eylül 2026): OH-D31-10 ana model
    hükmüyle tel-biçimi reddi kanona bağlandı ve ``/api/oxidizer-properties``
    kapısı kuruldu; bu bekçi kırmızıya düştü. YÖNÜ ÇEVRİLDİ: artık ayrışmayı
    değil BİRLEŞMEYİ kilitler — aynı gövde biçimi, iki uç, aynı hüküm ve aynı
    makine-okur ad. Kardeş çapa
    ``tests/test_d31_app_api_uc_a2.py::TestOHD2907TelBicimiKuraliTekKaynak``
    da aynı hamlede çevrildi.
    """

    def test_dize_sozlesmesi_uclar_arasi_TEKILLESTI(self, istemci):
        r1 = istemci.post('/api/oxidizer-properties',
                          json={'oxidizer_type': 'n2o',
                                'temperature': '293.15'})
        r2 = istemci.post('/calculate_liquid',
                          json={'motor_name': 'K5', 'thrust': 10000.0,
                                'burn_time': 30.0, 'chamber_pressure': '30.0',
                                'mixture_ratio': 2.2, 'fuel_type': 'rp1',
                                'oxidizer_type': 'lox'})
        assert r1.status_code == 400, (
            'oxidizer-properties sayı-benzeri dizeyi yeniden kabul ediyor '
            '(OH-D31-10 kanonu geri alınmış)')
        assert r2.status_code == 400, 'calculate_liquid dizeyi reddeder'
        for yanit, yol in ((r1, '/api/oxidizer-properties'),
                           (r2, '/calculate_liquid')):
            kayitlar = [k for k in ((yanit.get_json() or {}).get(
                'invalid_fields') or []) if isinstance(k, dict)]
            assert kayitlar, (yol, yanit.get_json())
            assert kayitlar[0].get('reason') == 'not_a_json_number', (
                yol, kayitlar[0])
