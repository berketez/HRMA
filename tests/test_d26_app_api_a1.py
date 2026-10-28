# -*- coding: utf-8 -*-
"""ÖH D26 / app-api aşama-1 bekçileri — OH-D25-19 + OH-D25-20.

Ölçüm gövdesi: ``docs/scofield/raw/OH/D26/app-api/a1/olcum.py``
Önce/sonra sayıları: ``.../once.json``, ``.../sonra.json``
Ters-mutasyon kanıtı: ``.../mutasyon.json``

Bu dosyadaki her sınıf, onarımın GERİ ALINMASI hâlinde kırmızı verecek
biçimde yazılmıştır (ters-mutasyonla doğrulandı).
"""
import json

import pytest
from tests.support.platform_capa import capa_rel


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _hibrit_taban():
    """Ürünün hibrit sayfasının GERÇEKTEN gönderdiği taban gövde.

    Tek kaynak: ``tests/test_field_wiring_layer_b.HYBRID_BASE`` (iki yerde
    iki farklı taban gövde tutulmaz).
    """
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    g = dict(HYBRID_BASE)
    g['include_plots'] = False
    return g


def _alanlar(govde):
    return [k.get('field') for k in (govde or {}).get('invalid_fields') or []
            if isinstance(k, dict)]


# ===========================================================================
# OH-D25-19 — /calculate'in DOĞRULADIĞI ama HİÇ OKUMADIĞI kanonik ad
# ===========================================================================
class TestOHD2519OkunmayanKanonikAd:
    """Bant ULAŞIYOR, DEĞER ULAŞMIYOR.

    ÖLÇÜLDÜ (taban ``7751531``, ``once.json`` K1/K3/K6)::

        {..., chamber_diameter: 3,0}    -> 200, D_ch = 0,15303556849392624 m
                                          (alan hiç gönderilmemiş gövdeyle
                                           BİT-AYNI), beyan yaprağı = 0
        {..., chamber_diameter: 1e9}    -> 400, invalid_fields=[chamber_diameter]

    Yani kullanıcının metre cinsinden yazdığı hazne çapı doğrulanıyor,
    sonra sessizce yutuluyor ve motor kendi çözdüğü çapı "başarılı tasarım"
    diye yayımlıyordu.
    """

    #: ``motor_validator.limits`` bandının İÇİNDE olan, yani bugüne kadar
    #: 200 alan ve sessizce düşen değerler.
    BANT_ICI = [
        ('chamber_diameter', 3.0, 'chamber_diameter_input'),
        ('chamber_diameter', 0.2, 'chamber_diameter_input'),
        ('chamber_length', 0.6, 'chamber_length_override'),
        ('port_diameter', 0.05, 'initial_port_diameter'),
        ('temperature', 3200.0, 'chamber_temperature'),
    ]

    @pytest.mark.parametrize('ad,deger,urun_adi', BANT_ICI)
    def test_okunmayan_kanonik_ad_adiyla_reddedilir(self, client, ad, deger,
                                                    urun_adi):
        r = client.post('/calculate', json=dict(_hibrit_taban(), **{ad: deger}))
        assert r.status_code == 422, (
            f'{ad}={deger} hâlâ HTTP {r.status_code} alıyor: doğrulanan alan '
            'sessizce yutuluyor. %s' % r.get_data(as_text=True)[:300])
        j = r.get_json() or {}
        assert j.get('error') == 'unread_canonical_field'
        assert ad in _alanlar(j), (
            'ret KULLANICININ alan adını söylemiyor: %s'
            % json.dumps(j, ensure_ascii=False)[:400])
        kayit = [k for k in j['invalid_fields'] if k['field'] == ad][0]
        assert kayit['reason'] == 'field_not_read'
        assert kayit['use_instead'] == urun_adi, (
            'ret, ürünün GERÇEKTEN okuduğu adı göstermiyor')
        assert kayit.get('use_instead_unit')

    @pytest.mark.parametrize('ad,deger,_urun', BANT_ICI)
    def test_sessiz_200_ve_uydurma_cap_yayimlanmiyor(self, client, ad, deger,
                                                     _urun):
        """Ret gövdesi HİÇBİR motor sayısı yayımlamaz (fail-closed)."""
        r = client.post('/calculate', json=dict(_hibrit_taban(), **{ad: deger}))
        j = r.get_json() or {}
        assert 'motor' not in j
        assert 'design_summary' not in j

    def test_bant_disi_ret_BOZULMADI(self, client):
        """Kapı, ZATEN VAR OLAN bant reddinin önüne geçmez (400 korunur).

        ``chamber_diameter = 1e9`` bugüne kadar 400 + adlı ``invalid_fields``
        alıyordu (ÖH Z5S / S3 kapısı); yeni kapı doğrulayıcıdan SONRA durur.
        """
        for deger in (1e9, -0.5):
            r = client.post('/calculate',
                            json=dict(_hibrit_taban(), chamber_diameter=deger))
            assert r.status_code == 400, (
                'bant reddi 400 olmaktan çıktı (%s): %s'
                % (r.status_code, r.get_data(as_text=True)[:200]))
            assert 'chamber_diameter' in _alanlar(r.get_json())

    @pytest.mark.parametrize('urun_adi,deger,beklenen_m', [
        ('chamber_diameter_input', 200.0, 0.2),
        ('chamber_diameter_input', 500.0, 0.5),
    ])
    def test_urunun_KENDI_adi_calismaya_devam_ediyor(self, client, urun_adi,
                                                     deger, beklenen_m):
        """ÖK-22: sağlıklı envanter daralmadı (K2, önce = sonra)."""
        r = client.post('/calculate',
                        json=dict(_hibrit_taban(), **{urun_adi: deger}))
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_json()['motor']['chamber_diameter'] == pytest.approx(
            beklenen_m, abs=1e-9)

    def test_alan_YOKKEN_gövde_bit_ayni(self, client):
        """Kapı, alanı göndermeyen (yani ürünün kendi) gövdesine dokunmaz."""
        r = client.post('/calculate', json=_hibrit_taban())
        assert r.status_code == 200
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   d_c 0,15303556849392624 -> 0,15401759407429375
        # v3.0.0 (15 Eki) — çapa darwin/arm64'te ölçüldü; CI linux/x86_64'te
        # AYNI kod 2,5e-12 mutlak bağıl sapma verdi (koşum 38770162288). Tolerans
        # referans platformda aynen; başkasında 1e-10 mutlak (tests/support/platform_capa.py).
        # ÇAPA YENİLENDİ — v3.0.1 kulvar P (ana model kararı): kaynaksız
        # D_ch = 1,5·√N·D_son kuralı söküldü; N = 1, artık et 0 iken grain
        # dış çapı = yanma sonu port çapı (Karabeyoglu ve ark. 2007 §VI.B).
        # Eski çapa 1,5 katsayısını KİLİTLİYORDU (0,15402 / 1,5 = 0,10268).
        # Ölçüm: docs/scofield/raw/OH/V301/ayberk1/port-kamara/RAPOR.md.
        #   d_c 0,15401759407429375 -> 0,10268324142272364 (= D_port_son)
        # V305/C2 (28 Eki) — ÇAPA ÖLÇÜMLE YENİLENDİ, İKİ BİLİNÇLİ KÖK
        # (main ilk-ebeveyn zincirinde aynı gövdeyle ölçüldü, docs'suz ağaç;
        # docs/scofield/raw/OH/V305/ci/C2/):
        #   1) dcb5a762e (21 Eki, B7 — Berke onaylı): hibrit dengeye yoğun faz
        #      C(gr). Bu gövde (O/F 2,5, yakıtça zengin) karbonca doymuş: c*
        #      1307,369 -> 1370,771 m/s, ṁ 2,81860 -> 2,69448 kg/s,
        #      d_c 0,10268324142272364 -> 0,10074226318866746.
        #   2) 74b55500a (26 Eki, H-PANEL — Berke 'girdi + kaynaklı
        #      varsayılan'): alan yokken N2O/HTPB c* verimi η = 0,89
        #      (26 ölçülmüş ateşlemenin ortancası). c* 1370,771 -> 1219,986
        #      m/s (= 0,89 ×), ṁ -> 3,02733 kg/s, d_c -> 0,10585066435651505.
        #   Bağımsız kontrol: bugünkü ağaçta combustion_efficiency = 100 ile
        #   d_c 0,1007422631886327 (B7 sonrası η'sız sayı, bağıl 4e-14).
        # Bu gövde alan göndermediği için kaynaklı η'yı ölçer; bekçinin
        # sorusu (alan yokken gövde ürünün kendi çözümü) ve tolerans aynı.
        m = r.get_json()['motor']
        assert m['chamber_diameter'] == pytest.approx(
            0.10585066435651505, abs=capa_rel(1e-12, 1e-10))
        assert m['chamber_diameter'] == m['port_diameter_final']

    def test_None_alan_yok_sayilir(self, client):
        """``chamber_diameter: null`` "alan gönderilmedi" demektir."""
        r = client.post('/calculate',
                        json=dict(_hibrit_taban(), chamber_diameter=None))
        assert r.status_code == 200

    def test_tablo_TEK_KAYNAKTAN_turetiliyor(self):
        """``CANONICAL_TO_PRODUCT_FIELD`` ikinci bir tablo DEĞİLDİR."""
        from hrma.validation.motor_validation import (CANONICAL_TO_PRODUCT_FIELD,
                                                      FIELD_ALIASES)
        assert set(CANONICAL_TO_PRODUCT_FIELD) == {
            t['kanonik'] for t in FIELD_ALIASES.values()}
        for urun_ad, tanim in FIELD_ALIASES.items():
            assert CANONICAL_TO_PRODUCT_FIELD[tanim['kanonik']] == (
                urun_ad, tanim['birim'])


# ===========================================================================
# OH-D25-20 — /api/advanced-analysis yanma kolu iki kabı da görür
# ===========================================================================
#: Kardeş kolların (ısı, yapısal, 3B, pano) okuduğu motor kabı.
MOTOR_DATA = {'chamber_pressure': 25, 'of_ratio': 3.5,
              'chamber_temperature': 3000, 'chamber_diameter': 0.1,
              'chamber_length': 0.5, 'burn_time': 10, 'mdot_total': 1.0}


def _yanma(govde):
    ca = ((govde or {}).get('results') or {}).get('combustion_analysis') or {}
    oda = (ca.get('conditions') or {}).get('chamber') or {}
    return oda.get('P'), ca.get('equivalence_ratio')


class TestOHD2520YanmaKoluIkiKap:
    """Aynı uçta iki istek şeması vardı.

    ÖLÇÜLDÜ (taban ``7751531``, ``once.json`` K4)::

        motor_data.chamber_pressure = 25, of_ratio = 3,5
            -> P = 20,0 bar,  φ = 8,950362345633366
               ("hiç gönderilmemiş" isteğiyle BİT-AYNI, imza e627e44ea44cb647)
               + defaults_applied: not_supplied
        üst seviye aynı iki sayı
            -> P = 25,0 bar,  φ = 2,557246384466676

    Ve en keskin hâli (``iki_kol``): tek istekte ısı kolu 25 bar'da, yanma
    kolu 20 bar'da koşuyordu — bir yanıt, iki ayrı motor.
    """

    def test_motor_data_icindeki_basinc_yanma_kolunda_kullaniliyor(self,
                                                                   client):
        r = client.post('/api/advanced-analysis', json={
            'analysis_types': ['combustion'], 'motor_data': dict(MOTOR_DATA)})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        pc, phi = _yanma(r.get_json())
        assert pc == pytest.approx(25.0), (
            'motor_data içindeki oda basıncı hâlâ düşüyor (P=%s)' % pc)
        assert phi == pytest.approx(2.557246384466676, rel=1e-9), (
            'motor_data içindeki O/F hâlâ düşüyor (φ=%s)' % phi)

    def test_motor_data_ile_ust_seviye_AYNI_sonucu_veriyor(self, client):
        """Aynı motor, iki yazım — tek hüküm."""
        a = client.post('/api/advanced-analysis', json={
            'analysis_types': ['combustion'], 'motor_data': dict(MOTOR_DATA)})
        b = client.post('/api/advanced-analysis', json={
            'analysis_types': ['combustion'], 'motor_data': {},
            'chamber_pressure': 25, 'of_ratio': 3.5})
        assert a.status_code == b.status_code == 200
        assert _yanma(a.get_json()) == _yanma(b.get_json())

    def test_iki_kol_TEK_motoru_anlatiyor(self, client):
        """Isı kolu ile yanma kolu aynı oda basıncını kullanır."""
        r = client.post('/api/advanced-analysis', json={
            'analysis_types': ['heat_transfer', 'combustion'],
            'motor_data': dict(MOTOR_DATA), 'wall_thickness': 0.005})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        pc, _phi = _yanma(r.get_json())
        assert pc == pytest.approx(25.0), (
            'yanma kolu hâlâ ısı kolundan başka bir motoru anlatıyor '
            '(P=%s, motor_data 25 bar)' % pc)

    def test_kunye_ARTIK_dogru_soyluyor(self, client):
        """``motor_data``da basınç varken "not supplied" künyesi yazılmaz."""
        r = client.post('/api/advanced-analysis', json={
            'analysis_types': ['combustion'], 'motor_data': dict(MOTOR_DATA)})
        assert not (r.get_json() or {}).get('defaults_applied'), (
            'kullanıcı 25 bar gönderdiği hâlde yanıt "not supplied" diyor')

    def test_hicbir_kapta_yokken_kunye_DURUYOR(self, client):
        """ÖK-19 beyanı kalkmadı (sağlıklı davranış bit-aynı)."""
        r = client.post('/api/advanced-analysis', json={
            'analysis_types': ['combustion'], 'motor_data': {}})
        assert r.status_code == 200
        kunye = (r.get_json() or {}).get('defaults_applied') or []
        assert [k for k in kunye if k.get('field') == 'chamber_pressure'
                and k.get('reason') == 'not_supplied']
        pc, phi = _yanma(r.get_json())
        assert pc == pytest.approx(20.0)
        assert phi == pytest.approx(8.950362345633366, rel=1e-9)

    @pytest.mark.parametrize('ad,ust,ic', [
        ('chamber_pressure', 40, 25),
        ('of_ratio', 1.0, 3.5),
    ])
    def test_celiskili_gonderim_ADIYLA_reddedilir(self, client, ad, ust, ic):
        """İki kapta iki farklı değer -> hangisi kazanır sorusu doğmaz."""
        r = client.post('/api/advanced-analysis', json={
            'analysis_types': ['combustion'],
            'motor_data': dict(MOTOR_DATA, **{ad: ic}),
            ad: ust})
        assert r.status_code == 422, (
            '%s çelişkisi hâlâ sessizce üst seviye lehine çözülüyor: %s'
            % (ad, r.get_data(as_text=True)[:300]))
        j = r.get_json() or {}
        assert j.get('error') == 'conflicting_combustion_input'
        assert ad in _alanlar(j)
        assert 'results' not in j

    def test_ayni_deger_iki_kapta_CELISKI_DEGIL(self, client):
        r = client.post('/api/advanced-analysis', json={
            'analysis_types': ['combustion'],
            'motor_data': dict(MOTOR_DATA),
            'chamber_pressure': 25, 'of_ratio': 3.5})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert _yanma(r.get_json())[0] == pytest.approx(25.0)

    def test_alan_listesi_kolun_KENDI_okumasiyla_ortusuyor(self):
        """``ADVANCED_COMBUSTION_FIELDS`` kolun gerçekten okuduğu adlardır."""
        import ast
        import inspect
        from hrma import app as app_mod
        kaynak = inspect.getsource(app_mod.advanced_analysis)
        agac = ast.parse(kaynak.lstrip())
        okunan = set()
        for d in ast.walk(agac):
            if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr == 'get'
                    and isinstance(d.func.value, ast.Name)
                    and d.func.value.id == '_yanma_kaynak'
                    and d.args and isinstance(d.args[0], ast.Constant)):
                okunan.add(d.args[0].value)
        assert okunan == set(app_mod.ADVANCED_COMBUSTION_FIELDS), (
            'yanma kolu listede olmayan bir adı okuyor ya da listedeki bir '
            'adı hiç okumuyor: %s' % sorted(okunan))


class TestOHD2520CoolingTypeBekcisi:
    """``ADVANCED_TOP_LEVEL_ONLY_FIELDS``in ÜÇÜNCÜ adı bekçisizdi.

    Fable-D21 a2 bulgusu [10]: ``cooling_type`` demette VAR ve uç onu
    ``motor_data`` içinde reddediyor, ama hiçbir bekçi bunu sınamıyordu.
    ÖLÇÜLDÜ (``once.json`` K5): üç ad da 422 alıyor — kusur ÜRÜNDE değil,
    BEKÇİDEydi. Bu sınıf borcu kapatır ve demeti TEK KAYNAK olarak sınar.
    """

    ISI_MOTOR_DATA = {'chamber_pressure': 20, 'chamber_temperature': 3000,
                      'chamber_diameter': 0.1, 'chamber_length': 0.5,
                      'burn_time': 10, 'mdot_total': 1.0}
    ORNEK = {'wall_thickness': 0.02, 'material_type': 'inconel_718',
             'cooling_type': 'regenerative'}

    def test_demetin_HER_adi_motor_data_icinde_reddedilir(self, client):
        from hrma.app import ADVANCED_TOP_LEVEL_ONLY_FIELDS
        assert set(ADVANCED_TOP_LEVEL_ONLY_FIELDS) == set(self.ORNEK), (
            'demet büyüdü/küçüldü ama bu bekçi güncellenmedi')
        for ad in ADVANCED_TOP_LEVEL_ONLY_FIELDS:
            r = client.post('/api/advanced-analysis', json={
                'analysis_types': ['heat_transfer'],
                'motor_data': dict(self.ISI_MOTOR_DATA,
                                   **{ad: self.ORNEK[ad]}),
                'wall_thickness': 0.005})
            assert r.status_code == 422, (
                '%s hâlâ motor_data içinde sessizce düşüyor' % ad)
            j = r.get_json() or {}
            assert j.get('error') == 'misplaced_thermal_input'
            assert ad in _alanlar(j)


# ===========================================================================
# BEKÇİ BORCU (P13B4-10 dağıtımı, app-api / hrma/app.py)
# ===========================================================================
class TestBekciBorcuP7B316:
    """P7B3-16 — ``/api/regression-analysis`` yakıt kimliği kanalı.

    Kalem kapalı (onarildi) ama kalemin SEMBOLÜNÜ doğrudan sınayan bekçi
    yoktu (``p13b410_dagitim.json``: "D1 DOLAYLI"). Onarımın iki yüzü:
    (a) çözülemeyen yakıt adı sessizce HTPB olmaz, (b) yakıt kimliği
    regresyon hızını GERÇEKTEN değiştirir.
    """

    TEMEL = {'burn_time': 10.0, 'mdot_ox': 2.0,
             'port_diameter_initial': 0.05, 'chamber_length': 0.5,
             'grain_length': 0.4}

    def test_cozulemeyen_yakit_sessizce_HTPB_olmuyor(self, client):
        r = client.post('/api/regression-analysis', json={
            'motor_data': dict(self.TEMEL, fuel_type='peynir')})
        assert r.status_code >= 400, (
            'tanımsız yakıt adı hâlâ hüküm üretiyor: %s'
            % r.get_data(as_text=True)[:300])
        ham = r.get_data(as_text=True)
        assert 'peynir' in ham

    def test_yakit_kimligi_regresyon_hizini_degistiriyor(self, client):
        sonuc = {}
        for yakit in ('htpb', 'paraffin'):
            r = client.post('/api/regression-analysis', json={
                'motor_data': dict(self.TEMEL, fuel_type=yakit)})
            assert r.status_code == 200, r.get_data(as_text=True)[:300]
            g = r.get_json() or {}
            dizi = ((g.get('regression_data') or g).get('regression_rate')
                    or [])
            assert dizi, 'regresyon hızı dizisi boş: %s' % list(g)[:8]
            sonuc[yakit] = dizi[0]
        assert sonuc['htpb'] != pytest.approx(sonuc['paraffin'], rel=1e-9), (
            'yakıt kimliği kanalı yine ölü: iki yakıt aynı r_dot veriyor '
            '(%s)' % sonuc)


class TestBekciBorcuP7B320:
    """P7B3-20 — ``/analyze_safety`` termal bloğu ısı zincirini besliyor.

    Kalem kapalı ama doğrudan bekçisi yoktu. Onarımın sembolü
    ``_SAFETY_THERMAL_CHAIN_FIELDS``: kullanıcı ``chamber_length`` /
    boğaz ölçeğini gönderdiğinde ısı zinciri koşar; eskiden her istekte
    ``MissingHeatTransferInput``a düşüp cidarı 293,15 K'ye sabitliyor ve
    3000 K'lik gaza "Selected material acceptable" basıyordu.
    """

    GOVDE = {'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
             'thrust': 1000.0, 'burn_time': 10.0, 'propellant_mass': 5.0,
             'chamber_diameter': 0.1, 'wall_thickness': 0.005,
             'chamber_length': 0.6, 'throat_diameter': 0.04,
             'mdot_total': 1.0}

    def test_isi_zinciri_alanlari_TEK_KAYNAKTAN_geciyor(self):
        from hrma.app import _SAFETY_THERMAL_CHAIN_FIELDS
        assert _SAFETY_THERMAL_CHAIN_FIELDS, 'ısı zinciri demeti boşaldı'
        for ad in ('chamber_length',):
            assert ad in _SAFETY_THERMAL_CHAIN_FIELDS, (
                '%s ısı zincirine artık geçmiyor — cidar yine ortam '
                'sıcaklığına sabitlenir' % ad)

    def test_cidar_ortam_sicakligina_sabitlenmiyor(self, client):
        """ÖLÇÜLDÜ (bu koşu): zincir beslenince cidar 2970,3 K çıkıyor ve
        malzeme hükmü "Insulation or a higher-temperature alloy required"
        oluyor; eskiden 293,15 K'de "Selected material acceptable"dı."""
        r = client.post('/analyze_safety', json=dict(self.GOVDE))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        ts = ((r.get_json() or {}).get('safety_analysis')
              or {}).get('thermal_safety') or {}
        cidar = ts.get('inner_wall_temperature_k')
        assert isinstance(cidar, (int, float)), (
            'ısı zinciri hiç koşmadı: cidar sıcaklığı yok (%s)' % ts.get(
                'material_recommendation'))
        assert cidar > 1000.0, (
            '3000 K gazda cidar %s K — zincir yine ortam sıcaklığına '
            'düşmüş' % cidar)
        assert 'acceptable' not in str(
            ts.get('material_recommendation', '')).lower()

    def test_zincir_alani_YOKKEN_hukum_URETILMIYOR(self, client):
        """Fail-closed: eksik zincir uydurma cidar sıcaklığı doğurmaz."""
        eksik = {k: v for k, v in self.GOVDE.items()
                 if k not in ('chamber_length', 'throat_diameter',
                              'mdot_total')}
        r = client.post('/analyze_safety', json=eksik)
        assert r.status_code == 200
        ts = ((r.get_json() or {}).get('safety_analysis')
              or {}).get('thermal_safety') or {}
        assert ts.get('inner_wall_temperature_k') is None
        assert ts.get('material_recommendation') == 'NOT_EVALUATED'
