"""Faz 5B bekçileri — ``hrma/app.py`` analiz uçlarının hüküm ve iş kapıları.

Bu dosya Faz 5 avında ÖLÇÜLEN altı kusuru kilitler. Her sınıfın başında
düzeltme öncesi ham ölçüm durur; test o ölçümün geri gelmesini engeller.

* **H3-B2 (KRİTİK)** — ``/analyze_thermal_safety`` bozuk girdide güvenlik
  hükmünü TERS çeviriyordu. Aynı motor, üç girdi:
  normal → HTTP 200 ``risk_level='HIGH'``; bütün sayılar ``"NaN"`` →
  HTTP 200 ``risk_level='LOW'``; bütün sayılar ``-1`` → HTTP 200
  ``risk_level='LOW'``. Kök neden IEEE-754 NaN karşılaştırma tuzağı
  (``nan < 1.5`` ve ``nan < 2.0`` ikisi de ``False``, hiçbir risk dalı
  girmiyor, ``risk_level`` başlangıç değeri ``'LOW'``da kalıyor). Kullanıcı
  "risk düşük" görüp devam ediyordu.
* **H3-B5 / H1-B5 (KRİTİK)** — ``/api/six-dof-analysis`` fiziksel girdi
  doğrulaması yapmıyordu: ``dry_mass=-5`` ile HTTP 200, apoje 3,95e14 m
  (2637 AU), tepe hız 9,96e11 m/s (ışık hızının 3322 katı) ve
  ``stable: True``; ``cd0=-1`` ile 4277 m/s; ``thrust=-3000`` ile
  ``stable: True``; ``body_diameter=0`` ile HTTP 500 sıfıra bölme.
  Ayrıca NaN girdili tek istek 900 saniye boyunca dönmüyordu.
* **H3-B6 (CİDDİ)** — ``/analyze_structural_safety`` sıfır girdide hem
  çöküyor hem hüküm veriyordu: ``chamber_pressure=0`` ve
  ``chamber_diameter=0`` → HTTP 500 ``float division by zero``;
  ``chamber_length=0`` ve ``throat_diameter=0`` → HTTP 200 + TAM yapısal
  hüküm (sıfır boyda oda için emniyet kararı). Kapı yalnız ``None``/``''``
  bakıyordu, yani ``0`` "verildi" sayılıyordu.
* **H3-B8 (ORTA)** — ``/api/thermal-protection`` panelde sayısal bir alan
  BOŞALTILDIĞINDA 500 veriyordu; gövdede ham Python imza hatası
  (``ablative_thickness() missing 1 required positional argument``)
  kullanıcıya kadar gidiyordu.
* **H3-B12 (ORTA)** — ``/parametric-analysis`` tek istekte bloke ediyordu:
  20 adım 13,3 s, 60 adım 40,4 s, 100 adım (izin verilen en büyük tarama)
  67,8 s. İş kuyruğu ya da iptal yoktu.
* **H3-B10 (ORTA)** — ``chamber_temperature`` ``/calculate``'te ÖLÜ girdiydi
  ama yankısı yayımlanıyordu: 2500 / 3500 / 0 / −3000 gönderildiğinde sonuç
  **bit-aynı** kalıyor, yanıt yine ``chamber_temperature: 1681,73`` diyordu.
  Kullanıcının verdiği sayı atılıyor ve bu hiçbir yerde söylenmiyordu.

Not: **H3-B1** (``/api/correlation-report``'un Fortran ERROR STOP ile TÜM
süreci öldürmesi) bu turda ölçüldüğünde ARTIK ÜRETİLEMİYOR — kök neden
Dalga 1'de ``hrma/engines/cea_bridge.py`` tarafında kapatılmış. Uç tarafına
değişiklik yapılmadığı için burada bekçisi yoktur; tam koşu ~2 dakika
sürdüğünden birim testine de uygun değildir.
"""

import math

import pytest

from hrma.app import (app, _collect_unphysical_fields,
                      _declare_overridden_inputs,
                      _withhold_unevaluated_thermal_verdict,
                      _SIXDOF_WALL_CLOCK_BUDGET_S,
                      _TP_MODE_REQUIRED,
                      PARAMETRIC_TIME_BUDGET_DEFAULT_S,
                      PARAMETRIC_TIME_BUDGET_MAX_S,
                      REQUIRED_STRUCTURAL_FIELDS,
                      THERMAL_VERDICT_NOT_EVALUATED)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


#: B2 ölçümünde kullanılan referans motor (normal girdi → ``risk_level``
#: HIGH, ``melting_safety_factor`` 0,5967, ``stress_safety_factor`` 22,15).
THERMAL_BASE = {
    'chamber_pressure': 20, 'chamber_temperature': 3000,
    'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'burn_time': 10, 'mdot_total': 1.0, 'wall_thickness': 0.005,
}

#: ÖH Faz B / B4 — ``/analyze_thermal_safety``in YOKLUK ekseni. Her vaka
#: ``(etiket, gövde, bildirilmesi beklenen eksik alan adları)``. Alan listesi
#: testin kendi ölçümüdür; ürün sabiti (``_THERMAL_SAFETY_POSITIVE_FIELDS``)
#: ithal EDİLMEZ — sınanan şey tam da ürünün bu alanları uydurma hakkıdır.


def _yokluk_vakalari():
    vakalar = [('bos_govde', {}, set(THERMAL_BASE))]
    for alan in sorted(THERMAL_BASE):
        vakalar.append((
            f'eksik_{alan}',
            {k: v for k, v in THERMAL_BASE.items() if k != alan},
            {alan}))
        vakalar.append((
            f'none_{alan}', dict(THERMAL_BASE, **{alan: None}), {alan}))
        vakalar.append((
            f'bos_dize_{alan}', dict(THERMAL_BASE, **{alan: ''}), {alan}))
    return vakalar


YOKLUK_VAKALARI = _yokluk_vakalari()


def _isi_akisi(response):
    """Yanıttan gaz tarafı ısı akısını çeker (ayırt edicilik ölçümü)."""
    return (response.get_json()['thermal_analysis']['gas_side_analysis']
            ['heat_flux'])


def _bildirilen_eksikler(body):
    """``missing_fields`` alanındaki adları küme olarak verir.

    Depoda iki biçim var: düz ad listesi (``/calculate_solid``,
    ``/api/thermal-protection``) ve sözlük listesi (``invalid_fields``).
    İkisini de kabul eder; sınanan şey adın BİLDİRİLİP bildirilmediğidir.
    """
    ham = body.get('missing_fields')
    if not ham:
        return set()
    return {p.get('field') if isinstance(p, dict) else p for p in ham}


#: B6 ölçümünde kullanılan referans oda (normal girdi → HTTP 200 + hüküm).
STRUCTURAL_BASE = {
    'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
    'chamber_length': 0.5, 'throat_diameter': 0.03,
}

#: B5 ölçümünde kullanılan sağlıklı araç (0,09 s'de apoje 7512,6 m).
SIXDOF_BASE = {
    'dry_mass': 20.0, 'propellant_mass': 10.0,
    'thrust': 3000.0, 'burn_time': 5.0,
}


# ---------------------------------------------------------------------------
# Ortak kapı yardımcısı
# ---------------------------------------------------------------------------

class TestFizikselGirdiKapisi:
    """``_collect_unphysical_fields`` sözleşmesi."""

    def test_verilmeyen_alan_incelenmez(self):
        """``0`` ile 'verilmedi' ASLA karıştırılmaz (input_guard ilkesi)."""
        assert _collect_unphysical_fields(
            {'a': None, 'b': ''}, positive=('a', 'b', 'c')) == []

    def test_sifir_ve_negatif_pozitif_alanda_reddedilir(self):
        problems = _collect_unphysical_fields(
            {'a': 0, 'b': -1.0}, positive=('a', 'b'))
        assert {p['field']: p['reason'] for p in problems} == {
            'a': 'must_be_positive', 'b': 'must_be_positive'}

    # ÖH D32 fix-35d / OH-D31-10 — GEREKÇE KODU KANONU (ana model hükmü,
    # 15 Eylül 2026). Bu paylaşımlı kapı ÜÇ AYRI soruyu tek ada
    # ("not_a_number") topluyordu; kardeş kapılar
    # (``_tasarim_hedefi_kapisi``, ``_form_band_kapisi``) ayrımı zaten
    # yapıyordu, yani ürün aynı olgu için iki sözlük konuşuyordu (ölçüldü,
    # ``docs/scofield/raw/OH/D32/fix35/d/once_dort_uc.json``). Kanon:
    #
    #   * ``bool``                       -> ``boolean_is_not_a_number``
    #   * JSON SAYISI OLMAYAN değer      -> ``not_a_json_number``
    #     (sayı-benzeri DİZE dâhil: ``'NaN'``, ``'-Infinity'``, ``'20.0'``;
    #      tek kaynak ``input_guard.is_json_number``)
    #   * JSON sayısı AMA sonlu değil    -> ``not_finite``
    #
    # ``not_a_number`` bu kapıda EMEKLİDİR. Bekçi GEVŞEMEDİ: eskiden dört
    # değer tek ada düşüyordu, şimdi her biri kendi adıyla sınanıyor.
    def test_sonlu_olmayan_reddedilir(self):
        """SAYI olarak gelmiş ama sonlu olmayan değer -> ``not_finite``."""
        for bad in (float('nan'), float('inf'), float('-inf')):
            problems = _collect_unphysical_fields({'a': bad}, positive=('a',))
            assert [p['reason'] for p in problems] == ['not_finite'], bad

    def test_sonlu_olmayan_TEL_BICIMI_json_sayisi_degildir(self):
        """``'NaN'`` bir DİZEDİR: sonluluk sorusuna hiç gelmez.

        JSON'un ``NaN``/``Infinity`` diye bir sayı biçimi yoktur; istemci
        bunları ancak dize olarak gönderebilir ve o zaman sorun sonluluk
        değil TEL BİÇİMİDİR. İki soruyu ayırmak, kullanıcıya yapması
        gerekeni doğru söyler (tipi düzelt, değeri değil).

        KAPSAM (ölçülmüş, ADIYLA açık kalem — ÖH D32 fix-35d): bu PAYLAŞIMLI
        kapı sayı-benzeri dizeyi (``'20.0'``) hâlâ OKUR ve kabul eder,
        çünkü sözleşmesi ``input_guard.finite_number``dır ("bu değer sonlu
        bir sayı olarak okunabilir mi?"), istek sınırındaki
        ``is_json_number`` değil. Kardeş ``/calculate*`` uçları aynı tel
        biçimini reddediyor. Bu AYRI bir karardır (kapıyı sıkmak
        ``/analyze_thermal_safety``, ``/analyze_structural_safety`` ve
        ``/api/six-dof-analysis`` uçlarının kabul yüzeyini daraltır) ve
        ölçülmeden verilmez; burada YALNIZ gerekçe kodu kanonu sınanır,
        kabul yüzeyi DEĞİL. Kalem D33 adayıdır ve raporda adıyla durur.
        """
        for bad in ('NaN', '-Infinity', 'Infinity'):
            problems = _collect_unphysical_fields({'a': bad}, positive=('a',))
            assert [p['reason'] for p in problems] == [
                'not_a_json_number'], bad

    def test_sayi_olmayan_reddedilir(self):
        # Liste ölçülmüş vakadır: B6'da HTTP 500 "float() argument must be a
        # string or a real number, not 'list'" üretiyordu.
        for bad in ([1, 2], 'abc', {'x': 1}):
            problems = _collect_unphysical_fields({'a': bad}, positive=('a',))
            assert [p['reason'] for p in problems] == [
                'not_a_json_number'], bad

    def test_mantiksal_deger_KENDI_adiyla_reddedilir(self):
        """``True`` sayısal alanda kendi adıyla düşer.

        ``float(True) == 1.0`` olduğu için bayrak bir bandın içine sessizce
        düşebiliyordu; ayrı ad, kullanıcıya yapması gerekeni söyler.
        Kardeş kapı ``_tasarim_hedefi_kapisi`` bu adı ZATEN kullanıyordu.
        """
        problems = _collect_unphysical_fields({'a': True}, positive=('a',))
        assert [p['reason'] for p in problems] == ['boolean_is_not_a_number']

    def test_negatif_olmayan_alanda_sifir_gecerli(self):
        assert _collect_unphysical_fields({'a': 0}, non_negative=('a',)) == []
        problems = _collect_unphysical_fields({'a': -0.1},
                                              non_negative=('a',))
        assert [p['reason'] for p in problems] == ['must_be_non_negative']

    def test_aralik_disi_reddedilir_ve_aralik_bildirilir(self):
        problems = _collect_unphysical_fields({'a': 7.0},
                                              ranges={'a': (0.0, 5.0)})
        assert problems[0]['reason'] == 'out_of_range'
        # ÖH D27 a2 / OH-D25-23 — BEKÇİ ÇEVRİLDİ: bu paylaşımlı kapı
        # bandı artık deponun kanonik adıyla (``accepted_range``, 17
        # site) yayımlıyor; eski ad (4 site) tek hamlede söküldü.
        assert problems[0]['accepted_range'] == [0.0, 5.0]
        assert 'allowed_range' not in problems[0], (
            'eski ad geri geldi: aynı kavram iki adla yayımlanamaz')

    def test_finite_isaret_serbest_birakir(self):
        """Rakım eksi olabilir (Lut Gölü); yalnız sonluluk aranır."""
        assert _collect_unphysical_fields({'alt': -415.0},
                                          finite=('alt',)) == []
        problems = _collect_unphysical_fields({'alt': float('inf')},
                                              finite=('alt',))
        assert [p['reason'] for p in problems] == ['not_finite']


# ---------------------------------------------------------------------------
# B2 — termal güvenlik hükmü
# ---------------------------------------------------------------------------

class TestTermalGuvenlikHukmu:
    """H3-B2: bozuk girdi risk seviyesini DÜŞÜREMEZ.

    **ÖH Faz B / adım B4 (Tip-T) — kapsam YOKLUK eksenine genişletildi.**

    Faz 5B'de kurulan kapı yalnız BOZUK SAYIyı tutuyordu (``NaN``, ``-1``,
    ``0``). Savcı ölçümü (defter P13B2-03, **kritik**) ikinci ekseni açtı:
    ucun **yokluğu** hiç tutmadığını. 27 Ağu 2026'da (HEAD ``344714d``)
    yeniden ölçüldü:

    ==============================  ====  ============  ==================
    gövde                           HTTP  ``risk``      yanıt gövdesi
    ==============================  ====  ============  ==================
    sağlıklı taban                  200   HIGH          md5* ``0eea37ff``
    ``{}`` (boş gövde)              200   HIGH          md5* ``0eea37ff``
    tek alan eksik (7 alanın 7'si)  200   HIGH          md5* ``0eea37ff``
    alan ``None``                   500   —             ham ``float()`` metni
    alan ``""``                     500   —             ham ``float()`` metni
    ==============================  ====  ============  ==================

    (*) md5, ``json.dumps(..., sort_keys=True)`` kanonik biçimi üstünden
    alındı; savcının ``08d81e162e5c``si başka bir kanonlaştırmanın aynı
    özdeşliğidir. Aşağıdaki bekçi hash'e değil HAM BAYTA bakar.

    Yani boş gövde ile sağlıklı taban **bit birebir aynı** yanıtı veriyor:
    kullanıcının hiç vermediği bir motor için ``risk_level='HIGH'`` hükmü
    basılıyor ve bunun uydurma olduğunu söyleyen bir beyan alanı yok
    (``heat_flux`` ikisinde de 13 027 380,540100738). ``None``/``""``
    kolunda ise ham Python istisna metni kullanıcıya kadar gidiyor.

    Tüketici CANLI: ``hrma/static/js/panels/thermal_panel.js:496`` bu ucu
    çağırıp ``data.thermal_analysis``ı (``:373``) panelde çiziyor.

    Bu sınıftaki ``test_normal_girdi_hukum_uretir`` tek başına AYIRT EDEMEZ
    (aynı iddia boş gövdede de yeşil); yanına girdiye-duyarlılık ve
    boş-gövde-ayrımı bekçileri kondu. Beklenen fail-closed biçimi deponun
    kendi sağlıklı deseni: ``/calculate_solid`` (``app.py:3701-3722``,
    422 + ``missing_fields`` + ``required_fields``) ve aynı dosyadaki
    ``/api/thermal-protection`` bekçileri (``test_bos_alan_500_degil_422``).
    """

    def test_normal_girdi_hukum_uretir(self, client):
        """Düzeltme öncesi/sonrası AYNI kalması gereken taban ölçüm.

        UYARI (B4): bu iddia TEK BAŞINA ayırt edici değildir — bugün boş
        gövde de aynı 200 + ``HIGH``ı üretiyor. Ayırt eden iddialar
        ``test_hukum_gonderilen_girdiden_turer`` ve
        ``test_bos_govde_saglikli_tabanin_ciktisini_uretemez``dir.
        """
        response = client.post('/analyze_thermal_safety', json=THERMAL_BASE)
        assert response.status_code == 200
        safety = response.get_json()['thermal_analysis']['safety_analysis']
        assert safety['risk_level'] == 'HIGH'

    def test_hukum_gonderilen_girdiden_turer(self, client):
        """Hüküm GÖNDERİLEN motora bağlı olmalı (ayırt edici taban).

        Ölçülen: Pc 20 bar → ``heat_flux`` 13 027 380,54 W/m²;
        Pc 40 bar → 24 115 276,51 W/m². Uç sayısal olarak girdiye duyarlı;
        eksik olan şey duyarlılık değil, YOKLUĞU tutan kapı.
        """
        taban = client.post('/analyze_thermal_safety', json=THERMAL_BASE)
        farkli = client.post('/analyze_thermal_safety',
                             json=dict(THERMAL_BASE, chamber_pressure=40))
        assert taban.status_code == 200 and farkli.status_code == 200
        assert taban.get_data() != farkli.get_data()
        assert _isi_akisi(taban) != _isi_akisi(farkli)

    # Z3 onarımı (2026-08-27): boş gövde artık 422 + missing_fields —
    # P13B2-03 imi XPASS ile düştü.
    def test_bos_govde_saglikli_tabanin_ciktisini_uretemez(self, client):
        """Boş gövde, doldurulmuş gövdeyle AYNI hükmü üretemez.

        Bu iddia P13B2-03'ün çekirdeğidir: savcı üç bağımsız ölçümde boş
        gövde ⟷ sağlıklı taban yanıtlarını ``md5=08d81e162e5c`` ile bit
        birebir aynı buldu (bu turda yeniden ölçüldü, ham gövdeler özdeş).
        "Sağlıklı tabanla aynı çıktı" bir sağlık ölçütü DEĞİL, kusurun ta
        kendisidir — o yüzden burada TERS yönde iddia edilir.
        """
        taban = client.post('/analyze_thermal_safety', json=THERMAL_BASE)
        bos = client.post('/analyze_thermal_safety', json={})
        assert bos.get_data() != taban.get_data(), (
            'boş gövde sağlıklı tabanın yanıtını birebir üretiyor — '
            'girdisi olmayan motor için güvenlik hükmü basılıyor')

    # Z3 onarımı (2026-08-27): kapı YOKLUĞU da tutuyor (22/22 vaka 422 +
    # alan adı; missing_field_groups 'biri yeterli' beyanıyla) — im düştü.
    @pytest.mark.parametrize(
        'govde,beklenen_eksikler',
        [vaka[1:] for vaka in YOKLUK_VAKALARI],
        ids=[vaka[0] for vaka in YOKLUK_VAKALARI])
    def test_eksik_girdi_hukum_uretmez(self, client, govde,
                                       beklenen_eksikler):
        """Verilmeyen alan UYDURULMAZ: 422 + eksik alan ADIYLA.

        Kapsam (22 vaka): boş gövde · 7 alanın her biri için tek-alan
        eksikliği · ``None`` · ``""``. Bugünkü ürün ilk sekizinde 200 +
        ``HIGH`` uyduruyor, son on dördünde ham ``float()`` istisnasıyla
        500 veriyor.

        Sözleşme deponun kendi desenidir: ``/calculate_solid`` ve
        ``/api/thermal-protection`` eksik girdide 422 + ``missing_fields``
        döner ve ham Python hatasını kullanıcıya SIZDIRMAZ.
        """
        response = client.post('/analyze_thermal_safety', json=govde)
        assert response.status_code == 422, (
            f'yokluk reddedilmeli; alınan HTTP {response.status_code}: '
            f'{response.get_data(as_text=True)[:200]}')
        body = response.get_json()
        assert body['error'] == 'incomplete_thermal_input'
        # Hüküm YOK: verilmeyen girdiden risk seviyesi çıkmaz.
        assert 'thermal_analysis' not in body
        assert beklenen_eksikler <= _bildirilen_eksikler(body), (
            f'eksik alan adıyla bildirilmeli; beklenen {beklenen_eksikler}, '
            f'gelen {body.get("missing_fields")}')
        # Ham Python istisna metni kullanıcıya gitmez (aynı dosyadaki
        # ``test_bos_alan_500_degil_422`` deseninin kardeşi).
        metin = str(body)
        assert 'float() argument' not in metin
        assert 'could not convert string to float' not in metin

    def test_govde_json_null_zaten_fail_closed(self, client):
        """Gövde ``null`` iken merkezî kapı çalışıyor — TESCİL (sağlıklı).

        B4 taramasında ölçüldü: gövde-düzeyi yokluk (``null``, boş gövde,
        skaler) ``app.py:600`` ``_reject_malformed_json_body`` kapısında
        400 + makine-okur kodla kapanıyor. Bu bekçi o davranışı bu rota
        için çapalar (genel envanter genişletmesi ÖK-23'ün işi; burada
        yalnız gevşememesi kilitlenir).
        """
        response = client.post('/analyze_thermal_safety', data='null',
                               content_type='application/json')
        assert response.status_code == 400
        body = response.get_json()
        assert body['error'] == 'body_not_an_object'
        assert 'thermal_analysis' not in body

    @pytest.mark.parametrize('bozuk_deger', ['NaN', -1, 0])
    def test_bozuk_girdi_riski_dusuremez(self, client, bozuk_deger):
        """Düzeltme öncesi: HTTP 200 + ``risk_level='LOW'``."""
        payload = {key: bozuk_deger for key in THERMAL_BASE}
        response = client.post('/analyze_thermal_safety', json=payload)
        assert response.status_code == 422
        body = response.get_json()
        assert body['error'] == 'invalid_thermal_input'
        # Hüküm YOK: reddedilen istekten risk seviyesi çıkmaz.
        assert 'thermal_analysis' not in body
        assert body['invalid_fields']
        assert {p['field'] for p in body['invalid_fields']} <= set(THERMAL_BASE)

    def test_tek_bozuk_alan_da_yeter(self, client):
        payload = dict(THERMAL_BASE, chamber_temperature='NaN')
        response = client.post('/analyze_thermal_safety', json=payload)
        assert response.status_code == 422
        assert [p['field'] for p in response.get_json()['invalid_fields']] == [
            'chamber_temperature']

    def test_sonlu_olmayan_katsayida_hukum_geri_cekilir(self):
        """İKİNCİ savunma hattı: hesap içinden NaN doğarsa hüküm çekilir.

        Girdi kapısı bu vakayı uçtan artık geçirmiyor, ama ``risk_level``ın
        sonlu olmayan bir emniyet katsayısından ASLA türetilmemesi ayrı bir
        sözleşmedir ve bağımsız kilitlenir.
        """
        results = {'safety_analysis': {
            'risk_level': 'LOW',
            'temperature_safety_factor': float('nan'),
            'melting_safety_factor': None,
            'stress_safety_factor': 1e6,
        }}
        assert _withhold_unevaluated_thermal_verdict(results) == 1
        safety = results['safety_analysis']
        assert safety['risk_level'] == THERMAL_VERDICT_NOT_EVALUATED
        assert safety['unevaluated_safety_factors'] == [
            'temperature_safety_factor', 'melting_safety_factor']
        assert 'risk_level_withheld_because' in safety

    def test_saglikli_katsayilarda_hukum_dokunulmaz(self):
        results = {'safety_analysis': {
            'risk_level': 'HIGH',
            'temperature_safety_factor': 0.36,
            'melting_safety_factor': 0.60,
            'stress_safety_factor': 22.15,
        }}
        assert _withhold_unevaluated_thermal_verdict(results) == 0
        assert results['safety_analysis']['risk_level'] == 'HIGH'

    def test_not_evaluated_low_sirasina_girmez(self):
        """Nötr hüküm bir risk seviyesi adı olmamalı."""
        assert THERMAL_VERDICT_NOT_EVALUATED not in ('LOW', 'MEDIUM', 'HIGH')


# ---------------------------------------------------------------------------
# B6 — yapısal güvenlik hükmü
# ---------------------------------------------------------------------------

class TestYapisalGirdiKapisi:
    """H3-B6: sıfır/negatif boyutlu oda için hüküm üretilmez."""

    def test_normal_girdi_hukum_uretir(self, client):
        response = client.post('/analyze_structural_safety',
                               json=STRUCTURAL_BASE)
        assert response.status_code == 200
        assert 'structural_analysis' in response.get_json()

    @pytest.mark.parametrize('alan', REQUIRED_STRUCTURAL_FIELDS)
    @pytest.mark.parametrize('deger', [0, -1])
    def test_sifir_ve_negatif_reddedilir(self, client, alan, deger):
        """Düzeltme öncesi ölçüm: pressure/diameter=0 → HTTP 500,
        length/throat=0 → HTTP 200 + TAM hüküm; dördü de -1 → HTTP 200."""
        payload = dict(STRUCTURAL_BASE, **{alan: deger})
        response = client.post('/analyze_structural_safety', json=payload)
        assert response.status_code == 422
        body = response.get_json()
        assert body['error'] == 'invalid_structural_input'
        assert 'structural_analysis' not in body
        assert [p['field'] for p in body['invalid_fields']] == [alan]

    def test_liste_gonderilirse_500_degil_422(self, client):
        """Düzeltme öncesi: HTTP 500 ``float() argument ... not 'list'``."""
        payload = dict(STRUCTURAL_BASE, chamber_pressure=[1, 2])
        response = client.post('/analyze_structural_safety', json=payload)
        assert response.status_code == 422
        # ÖH D32 fix-35d / OH-D31-10: liste bir JSON SAYISI değildir; kanon
        # ad merkezin adıdır (``input_guard.is_json_number``). HTTP sınıfı
        # (422) ve kalemin özgün iddiası (500 DEĞİL) aynen duruyor.
        assert response.get_json()['invalid_fields'][0]['reason'] == \
            'not_a_json_number'

    def test_eksik_alan_kapisi_korunur(self, client):
        """Faz 4B'nin ``incomplete_structural_input`` kapısı bozulmadı."""
        payload = dict(STRUCTURAL_BASE)
        payload.pop('throat_diameter')
        response = client.post('/analyze_structural_safety', json=payload)
        assert response.status_code == 422
        assert response.get_json()['error'] == 'incomplete_structural_input'


# ---------------------------------------------------------------------------
# B5 / H1-B5 — 6DOF girdi doğrulaması ve zaman sınırı
# ---------------------------------------------------------------------------

class TestSixDofGirdiKapisi:
    """H3-B5 + H1-B5: fiziksel olarak imkânsız girdi entegre EDİLMEZ."""

    def test_saglikli_arac_cozulur(self, client):
        response = client.post('/api/six-dof-analysis', json=SIXDOF_BASE)
        assert response.status_code == 200
        body = response.get_json()
        assert body['summary']['end_reason'] == 'apogee'
        assert body['summary']['apogee'] > 0

    @pytest.mark.parametrize('alan,deger', [
        # Ölçülmüş vakalar (hepsi düzeltme öncesi HTTP 200 / 500):
        ('dry_mass', -5.0),        # apoje 3,95e14 m, hız 9,96e11 m/s, stable
        ('dry_mass', 0.0),
        ('cd0', -1.0),             # negatif sürükleme, 4277 m/s
        ('thrust', -3000.0),       # HTTP 200 + stable: True
        ('thrust', 0.0),
        ('burn_time', -5.0),
        ('body_diameter', 0.0),    # HTTP 500 float division by zero
        ('body_length', -2.0),
        ('nose_length', 0.0),
        ('propellant_mass', -10.0),
        ('rail_length', 0.0),
        ('wind_speed', -3.0),
        ('fin_count', -4),
        ('launch_elevation_deg', 120.0),
        ('latitude_deg', 991.0),
        ('cd0', 50.0),
    ])
    def test_fiziksel_olmayan_girdi_reddedilir(self, client, alan, deger):
        payload = dict(SIXDOF_BASE, **{alan: deger})
        response = client.post('/api/six-dof-analysis', json=payload)
        assert response.status_code == 422
        body = response.get_json()
        assert body['error'] == 'invalid_six_dof_input'
        # Hiçbir yörünge yayımlanmaz — "kararlı" damgası da yok.
        assert 'summary' not in body
        assert alan in {p['field'] for p in body['invalid_fields']}

    @pytest.mark.parametrize('deger', ['NaN', float('nan'), float('inf')])
    def test_sonlu_olmayan_itki_reddedilir(self, client, deger):
        """Düzeltme öncesi: tek istek 900 saniyede DÖNMÜYORDU."""
        payload = dict(SIXDOF_BASE, thrust=deger)
        response = client.post('/api/six-dof-analysis', json=payload)
        assert response.status_code == 422
        assert response.get_json()['error'] == 'invalid_six_dof_input'

    def test_cd0_sifir_mesru_idealizasyondur(self, client):
        """Sürüklemesiz uçuş bir idealleştirmedir; reddedilmemeli."""
        response = client.post('/api/six-dof-analysis',
                               json=dict(SIXDOF_BASE, cd0=0.0))
        assert response.status_code == 200

    def test_eksi_rakim_kabul_edilir(self, client):
        """Lut Gölü −415 m; işaret denetimi rakıma uygulanmaz."""
        response = client.post('/api/six-dof-analysis',
                               json=dict(SIXDOF_BASE, launch_altitude=-415.0))
        assert response.status_code == 200

    def test_olculen_cozucu_suresi_yayimlanir(self, client):
        """Uydurma değil: ``time.monotonic()`` farkı."""
        response = client.post('/api/six-dof-analysis', json=SIXDOF_BASE)
        elapsed = response.get_json()['solver_wall_time_s']
        assert 0.0 <= elapsed < _SIXDOF_WALL_CLOCK_BUDGET_S

    def test_duvar_saati_butcesi_olculen_en_kotu_halin_ustunde(self):
        """Bütçe, ölçülen en kötü meşru süreden (10,1 s) belirgin büyük."""
        assert _SIXDOF_WALL_CLOCK_BUDGET_S >= 30.0


# ---------------------------------------------------------------------------
# B8 — termal koruma zorunlu alanları
# ---------------------------------------------------------------------------

class TestTermalKorumaZorunluAlanlar:
    """H3-B8: eksik zorunlu argüman 500 değil 422 üretir."""

    def test_zorunlu_alan_listesi_modul_imzalariyla_ayni(self):
        """Liste elle yazıldı; imzadan sapması sessiz bir gerilemedir."""
        import inspect
        from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer

        beklenen = {}
        for mode, fn in (
                ('ablative', ThermalProtectionAnalyzer.ablative_thickness),
                ('heat_sink', ThermalProtectionAnalyzer.heat_sink_transient),
                ('radiation_equilibrium',
                 ThermalProtectionAnalyzer.radiation_equilibrium)):
            beklenen[mode] = tuple(
                name for name, param in inspect.signature(fn).parameters.items()
                if name != 'self'
                and param.default is inspect.Parameter.empty)
        assert dict(_TP_MODE_REQUIRED) == beklenen

    @pytest.mark.parametrize('mode,eksik', [
        ('ablative', 'q_net_W_m2'),
        ('heat_sink', 'h_gas_W_m2K'),
        ('heat_sink', 'T_recovery_K'),
        ('radiation_equilibrium', 'T_recovery_K'),
    ])
    @pytest.mark.parametrize('bosaltma', ['', None])
    def test_bos_alan_500_degil_422(self, client, mode, eksik, bosaltma):
        """Düzeltme öncesi: 500 + ham Python imza hatası gövdede."""
        tam = {
            'ablative': {'mode': 'ablative', 'q_net_W_m2': 2.0e6,
                         'burn_time_s': 10.0},
            'heat_sink': {'mode': 'heat_sink', 'h_gas_W_m2K': 5000.0,
                          'T_recovery_K': 3000.0, 'burn_time_s': 10.0,
                          'wall_thickness_m': 0.005},
            'radiation_equilibrium': {'mode': 'radiation_equilibrium',
                                      'h_gas_W_m2K': 5000.0,
                                      'T_recovery_K': 3000.0,
                                      'emissivity': 0.8},
        }[mode]
        payload = dict(tam, **{eksik: bosaltma})
        response = client.post('/api/thermal-protection', json=payload)
        assert response.status_code == 422
        body = response.get_json()
        assert body['error'] == 'incomplete_thermal_protection_input'
        assert body['missing_fields'] == [eksik]
        # Ham Python imza hatası kullanıcıya gitmez.
        assert 'positional argument' not in str(body)

    def test_bos_govde_de_422(self, client):
        """Düzeltme öncesi: ``{}`` → 500 (mod varsayılanı 'ablative')."""
        response = client.post('/api/thermal-protection', json={})
        assert response.status_code == 422
        assert response.get_json()['missing_fields'] == ['q_net_W_m2']

    def test_tam_istek_calismaya_devam_eder(self, client):
        response = client.post('/api/thermal-protection', json={
            'mode': 'ablative', 'q_net_W_m2': 2.0e6, 'burn_time_s': 10.0,
            'material': 'silica_phenolic', 'design_margin': 1.5})
        assert response.status_code == 200

    def test_sayiya_cevrilemeyen_deger_hala_400(self, client):
        """Bu bir tip hatasıdır, eksik alan değil — kod ayrışmalı."""
        response = client.post('/api/thermal-protection', json={
            'mode': 'ablative', 'q_net_W_m2': 'abc', 'burn_time_s': 10.0})
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# B12 — parametrik tarama iş bütçesi
# ---------------------------------------------------------------------------

class TestParametrikIsButcesi:
    """H3-B12: tek istek sınırsız süre bloke edemez."""

    def test_butce_sabitleri_tutarli(self):
        assert 0 < PARAMETRIC_TIME_BUDGET_DEFAULT_S \
            <= PARAMETRIC_TIME_BUDGET_MAX_S

    @pytest.mark.parametrize('gecersiz', [0, -1, 1e9, 'abc', float('nan')])
    def test_gecersiz_butce_reddedilir(self, client, gecersiz):
        response = client.post('/parametric-analysis',
                               json={'param_steps': 3,
                                     'time_budget_s': gecersiz})
        assert response.status_code == 422
        assert response.get_json()['status'] == 'invalid_input'

    def test_asiri_tarama_erken_reddedilir(self, client):
        """Düzeltme öncesi: 100 adım 67,8 saniye bloke ediyordu.

        Artık ilk noktanın ÖLÇÜLEN maliyetiyle öngörü yapılır ve istek
        bütçeyi aşacaksa saniyeler içinde reddedilir.

        ÖH D27 / P16S1-02: gövdeye ``param_start`` + ``param_end`` EKLENDİ.
        Testin iddiası değişmedi (aşırı tarama erken reddedilir); değişen,
        ucun artık süpürme ARALIĞINI uydurmamasıdır — aralık verilmeyince
        tarama hiç başlamıyor ve istek ``sweep_interval_not_supplied`` ile
        dönüyor, yani bu gövde bütçe kapısına ulaşamıyordu. Aralık,
        kalemin ölçtüğü sessiz yedeğin (``param_start`` 0,5 /
        ``param_end`` 3,0) TA KENDİSİDİR, dolayısıyla test eskisiyle
        birebir aynı taramayı ister.

        ÖH D28 a1 / OH-D27-03: aynı gerekçeyle ``param_type`` de EKLENDİ.
        Süpürme EKSENİNİN ADI da artık uydurulmuyor (gönderilmeyince 422
        ``sweep_parameter_not_supplied``), o yüzden bu gövde bütçe
        kapısına ulaşamıyordu. Yazılan ad, ucun eskiden sessizce düştüğü
        yedeğin (``'of_ratio'``) TA KENDİSİDİR — testin iddiası
        (aşırı tarama erken reddedilir) değişmedi.
        """
        response = client.post('/parametric-analysis',
                               json={'param_type': 'of_ratio',
                                     'param_steps': 100,
                                     'param_start': 0.5, 'param_end': 3.0,
                                     'time_budget_s': 0.5})
        assert response.status_code == 422
        body = response.get_json()
        assert body['error'] == 'parametric_time_budget_exceeded'
        # Öngörü UYDURMA değil, bu makinede ölçülen değer.
        assert body['measured_seconds_per_point'] > 0
        assert body['projected_seconds'] > body['budget_s']
        assert body['points_that_fit_budget'] >= 2
        # Reddedilen istek eğri yayımlamaz.
        assert not body.get('results')

    def test_kucuk_tarama_bozulmadan_calisir(self, client):
        response = client.post('/parametric-analysis',
                               json={'param_type': 'of_ratio',
                                     'param_start': 1.0, 'param_end': 3.0,
                                     'param_steps': 3})
        assert response.status_code == 200
        body = response.get_json()
        assert body['status'] == 'success'
        assert body['points_succeeded'] == 3
        # Kesilmediği için kesinti beyanı YOK.
        assert 'truncated_by_time_budget' not in body
        # Ölçülen süre yayımlanır.
        assert body['sweep_wall_time_s'] >= 0.0


# ---------------------------------------------------------------------------
# B10 — sessizce yok sayılan girdi
# ---------------------------------------------------------------------------

class TestKullanilmayanGirdiBeyani:
    """H3-B10: çözücünün üzerine yazdığı girdi BEYAN edilir."""

    def test_ezilen_girdi_beyan_edilir(self):
        beyan = _declare_overridden_inputs(
            {'chamber_temperature': 2500},
            {'chamber_temperature': 1681.7328948175289},
            ('chamber_temperature',))
        assert len(beyan) == 1
        assert beyan[0]['field'] == 'chamber_temperature'
        assert beyan[0]['submitted'] == 2500.0
        assert math.isclose(beyan[0]['used_by_model'], 1681.7328948175289)
        assert beyan[0]['reason'] == 'solved_by_model'

    def test_kullanilan_girdi_beyan_edilmez(self):
        """Alan gerçekten modele bağlıysa gürültü üretilmez."""
        assert _declare_overridden_inputs(
            {'chamber_temperature': 3000.0},
            {'chamber_temperature': 3000.0},
            ('chamber_temperature',)) == []

    def test_verilmeyen_girdi_beyan_edilmez(self):
        assert _declare_overridden_inputs(
            {}, {'chamber_temperature': 1681.73},
            ('chamber_temperature',)) == []
        assert _declare_overridden_inputs(
            {'chamber_temperature': ''}, {'chamber_temperature': 1681.73},
            ('chamber_temperature',)) == []

    def test_yuvarlama_farki_beyan_sayilmaz(self):
        assert _declare_overridden_inputs(
            {'chamber_temperature': 3000.0},
            {'chamber_temperature': 3000.0000000001},
            ('chamber_temperature',)) == []
