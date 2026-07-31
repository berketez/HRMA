"""KATMAN B bekçisi: payload girdisi çıktıyı gerçekten değiştiriyor mu?

Katman A (``test_field_wiring_layer_a.py``) şablon ile payload arasındaki
dikişi ölçer: "her form alanı bir toplayıcıda okunuyor mu?". Bu dosya bir
sonraki dikişi ölçer: **payload ile çıktı arasındaki** dikişi.

İkisi ayrı kusur sınıfıdır ve biri diğerini yakalamaz:

* Katman A geçer, B kırılır: toplayıcı alanı gönderiyor ama çözücü okumuyor.
  (``contraction_ratio`` v2.6.26'ya kadar tam buydu — arayüz gönderiyordu,
  motora hiç geçirilmiyordu.)
* Katman B geçer, A kırılır: çözücü okuyor ama arayüz göndermiyor.
  (v2.6.25'te hibritin üç termal alanı tam buydu.)

Ölçüm tek bir matristir ve ondan İKİ hata sınıfı çıkar:

    her payload anahtarı x her çıktı yaprağı -> değişti mi?

* **Satır hiç değişmiyorsa** girdi ÖLÜDÜR.
* **Sütun hiçbir girdiyle değişmiyorsa** çıktı UYDURMA SABİTTİR.

Neden vaka listesi yetmez: ``tests/test_no_fabrication.py`` 17 BİLİNEN vakayı
sabitler. Vaka listelemek yeni uydurmayı yakalamaz; bu dosya vaka listelemez,
tarar. Nitekim ilk koşusunda yayınlanmış sürümde duran iki kusur çıktı:
``IMPINGEMENT_HALF_ANGLE_DEG`` import edilmediği için impingement yolunda
HTTP 500, ve devre modeli hata verdiğinde üretilen uydurma "12 delikli
showerhead" yedeği.

Sarsım aralıkları şablonun KENDİ ``min``/``max`` özniteliklerinden okunur
(``tests/support/inventory.field_specs_for``). Elle tutulan bir aralık
listesi çürür: yeni alan listeye girmez, değişen aralık eskir ve alan
YALANCI ÖLÜ görünür.
"""

import pytest

from tests.support import inventory, shake


# ---------------------------------------------------------------------------
# Taban motor — geçerli, tipik bir hibrit tasarım
# ---------------------------------------------------------------------------
HYBRID_BASE = {
    'motor_type': 'hybrid', 'motor_name': 'LAYER-B', 'motor_description': '',
    'thrust': 5000, 'burn_time': 10, 'chamber_pressure': 20,
    'tank_pressure': 50, 'of_ratio': 2.5, 'atmospheric_pressure': 1.013,
    'l_star': 1.0, 'expansion_ratio': 4.0, 'nozzle_type': 'conical',
    'combustion_type': 'infinite', 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'oxidizer_phase': 'liquid',
    'oxidizer_density': 1220, 'oxidizer_temp': 293,
    'oxidizer_viscosity': 0.0002, 'fuel_density': 920,
    'regression_a': 3.68e-5, 'regression_n': 0.555,
    'injector_type': 'showerhead', 'target_velocity': 30,
    'hole_diameter_min': 0.3, 'hole_diameter_max': 2.0, 'plate_thickness': 3.0,
    'chamber_material': 'steel_4130', 'wall_thickness': 5,
    'cooling_channels': 'none', 'chamber_temperature': 3000,
    'safety_factor': 4.0, 'nozzle_material': 'graphite',
    'injector_material': 'stainless_steel', 'discharge_coefficient': 0.7,
}

# Bazı alanlar yalnız kendi dalında canlıdır; o dal kurulmadan ölçülürse
# YALANCI ÖLÜ görünürler. Refakat alanları burada bildirilir.
HYBRID_CONTEXTS = {
    'outer_diameter': {'injector_type': 'pintle', 'pintle_diameter': 25,
                       'outer_diameter': 50},
    'pintle_diameter': {'injector_type': 'pintle', 'pintle_diameter': 25,
                        'outer_diameter': 50},
    'n_slots': {'injector_type': 'swirl', 'n_slots': 6},
    'slot_width': {'injector_type': 'swirl', 'n_slots': 6,
                   'slot_width': 1.0, 'slot_height': 2.0},
    'slot_height': {'injector_type': 'swirl', 'n_slots': 6,
                    'slot_width': 1.0, 'slot_height': 2.0},
    'swirl_chamber_diameter': {'injector_type': 'swirl', 'n_slots': 6,
                               'swirl_chamber_diameter': 20},
    'swirl_angle': {'injector_type': 'swirl', 'n_slots': 6,
                    'swirl_angle': 45},
    'element_pairs': {'injector_type': 'impingement', 'element_pairs': 8,
                      'impingement_angle': 60},
    'impingement_angle': {'injector_type': 'impingement', 'element_pairs': 8,
                          'impingement_angle': 60},
    'inner_diameter': {'injector_type': 'coaxial', 'inner_diameter': 5,
                       'outer_annulus_diameter': 10},
    'outer_annulus_diameter': {'injector_type': 'coaxial',
                               'inner_diameter': 5,
                               'outer_annulus_diameter': 10},
    'mass_flux_chamber': {'combustion_type': 'finite',
                          'mass_flux_chamber': 300},
    'contraction_ratio': {'combustion_type': 'finite',
                          'contraction_ratio': 4},
    # Payload birimi MİLİMETRE (app.py::_mm_to_m_optional). Metre değeri
    # vermek 3.6 mm demek olur, geometrik alt sınırın altında kalır ve alan
    # YALANCI ÖLÜ görünür — ölçüm hatası olarak bir kez yaşandı.
    'chamber_length_override': {'chamber_length_override': 3600},
    'chamber_diameter_input': {'chamber_diameter_input': 150},
    'initial_port_diameter': {'initial_port_diameter': 0.03},
    'n_holes': {'n_holes': 20},
    'pressure_drop': {'pressure_drop': 4.0},
    # --- KISIT ALANLARI: yalnız KISIT BAĞLADIĞINDA sonucu değiştirirler ---
    # İmalat bandı, çözümün doğal çapını kapsıyorsa bandı değiştirmek hiçbir
    # şeyi değiştirmez ve bu DOĞRUDUR (kısıt bağlamıyor). Alanın canlı
    # olduğunu görebilmek için sarsımın bağlayıcı bölgede kalması gerekir.
    # Ölçüldü: 0.3 -> 0.45 hiçbir şey değiştirmiyor (çözüm çapı 0.965 mm,
    # ikisinin de üstünde); 1.0 -> 1.5 on yaprak değiştiriyor.
    'hole_diameter_min': {'hole_diameter_min': 1.0, 'hole_diameter_max': 2.0},
    'hole_diameter_max': {'hole_diameter_min': 0.3, 'hole_diameter_max': 0.6},
    # Aynı gerekçe: 8 ve 12 çift, çap bandın dışına düştüğü için ikisi de
    # 15'e yeniden çözülüyordu. 16 üstü bölgede kullanıcının değeri korunur.
    'element_pairs': {'injector_type': 'impingement', 'element_pairs': 16,
                      'impingement_angle': 60},
    'orifice_diameter': {'injector_type': 'impingement', 'element_pairs': 16,
                         'impingement_angle': 60, 'orifice_diameter': 1.0},
}

#: Çözücünün "bu alanı TÜKETMİYORUM" diye AÇIKÇA beyan ettiği alanlar.
#: Beyan ``app.py`` içinde yapılır ve kullanıcıya yanıttaki ``unused_inputs``
#: ile ULAŞIR — yani sessiz değildir. Bu liste o beyanın kopyasıdır ve
#: aşağıdaki test ikisinin AYNI kaldığını doğrular; beyan kaldırılıp alan
#: bağlanmadan kalırsa bekçi kırılır.
DECLARED_UNUSED_IN_APP = {
    'impingement_distance': 'model bu mesafeyi çarpışma açısı ve delik çapından hesaplar',
    'momentum_ratio': 'benzer-akışkan doublet modeli; MR ölçütü farklı-akışkan içindir',
    'impingement_pattern': 'yalnız like_on_like/doublet modelleniyor',
    'recess_length': 'model girintiyi iç jet çapından hesaplar',
    'n_elements': 'bu yol tek koaksiyel eleman boyutlandırır',
}

# Şablon alan adı ile payload anahtarı AYRI olan alanlar. Toplayıcı bu
# dönüşümü yapar; Katman B payload anahtarını sarsar, çünkü çözücünün
# gördüğü ad odur. (Şablon adını sarsmak alanı yalancı ölü gösterirdi.)
TEMPLATE_TO_PAYLOAD = {
    'n_holes_override': 'n_holes',
    'pressure_drop_percent': 'pressure_drop',
    'single_pressure': 'atmospheric_pressure',
    'thrust_impulse': 'total_impulse',
    'burn_time_impulse': 'burn_time',
}

#: Yeniden adlandırılan alanın şablon aralığı payload BİRİMİNDE geçerli
#: OLMAYABİLİR. Örnek: ``pressure_drop_percent`` şablonda yüzdedir
#: (min 10, max 50) ama payload'a BAR olarak gider (20 bar odada 4 bar).
#: Şablon aralığını körü körüne devralmak sarsımı "aralık dışı" diye
#: engelliyor ve alan ÖLÇÜLEMEDİ görünüyordu. Birimi değişen her alan
#: burada payload birimiyle bildirilir.
PAYLOAD_RANGE = {
    'pressure_drop': (1.0, 15.0),        # bar (odanın %5-75'i)
}

# Ayrı uç noktaya giden ya da istemci tarafında kalan alanlar Katman B'nin
# konusu değildir; Katman A onları kendi gerekçeli listesinde tutar.
NOT_IN_CALCULATE = {
    'alt_start', 'alt_end', 'alt_points',        # altitude_profile alt sözlüğü
    'traj_alt_start', 'traj_alt_end', 'traj_points',
    'initial_mass', 'final_mass', 'reference_area',
    'viz_ds_dch', 'viz_ds_eps', 'viz_ds_lstar',
    'motor_name', 'motor_description',           # metin: sarsılamaz
    'total_impulse',                             # thrust/burn_time ile çelişir
    'injector_type',                             # dal seçici: refakatsiz 400
}

#: Sabit olması MEŞRU çıktı alt ağaçları. Bu liste DAR tutulmalıdır;
#: genişletmek uydurmayı gizlemenin en kolay yoludur. Her giriş bir
#: GEREKÇE taşır ve gerekçe "sonra bakarız" olamaz.
LEGITIMATE_CONSTANTS = (
    # Sabit irtifa ızgarası: standart atmosferden gelir, motordan değil.
    'altitude_performance',
    # Malzeme kaydı: veritabanı tablosu, hesap değil.
    'material_properties',
    'materials',
    # Kimyasal bileşim: HTPB/N2O'da alüminyum vb. sıfırdır (gerçek sıfır).
    'elemental_composition',
    # Sürüm/şema numaraları.
    'schema_version', 'version',
    # Fiziksel sabitler ve birim çarpanları.
    'g0', 'standard_gravity',
)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def hybrid_report(client):
    """Hibrit sarsım matrisi (bir kez koşar, testler paylaşır)."""
    template_specs = inventory.field_specs_for('hybrid')
    collected = inventory.build('hybrid').collected_fields
    specs = []
    seen = set()
    for name in sorted(collected & set(template_specs)):
        payload_key = TEMPLATE_TO_PAYLOAD.get(name, name)
        if payload_key in NOT_IN_CALCULATE or payload_key in seen:
            continue
        field = template_specs[name]
        if field.kind == 'text':
            continue
        seen.add(payload_key)
        # Birimi değişen alanlarda şablon aralığı devralınmaz (bkz. PAYLOAD_RANGE)
        lo, hi = PAYLOAD_RANGE.get(
            payload_key,
            (None, None) if payload_key != name else (field.minimum,
                                                      field.maximum))
        specs.append(shake.FieldSpec(
            name=payload_key,
            kind=field.kind,
            lo=lo,
            hi=hi,
            options=tuple(field.options or ()),
            context=HYBRID_CONTEXTS.get(payload_key, {}),
        ))
    return shake.run(client, '/calculate', HYBRID_BASE, specs,
                     declared_unwired=DECLARED_UNUSED_IN_APP)


def test_shake_covers_a_meaningful_share_of_the_form(hybrid_report):
    """Ölçüm kapsamı çökerse bu dosya sessizce anlamsızlaşır.

    Kapsam düşerse 'ölü girdi yok' sonucu güven vermez: ölçülmeyen alan
    ölü olmadığı için değil, bakılmadığı için temiz görünür.
    """
    measured = (len(hybrid_report.live_inputs)
                + len(hybrid_report.dead_inputs)
                + len(hybrid_report.echo_only_inputs))
    assert measured >= 30, hybrid_report.summary()


def test_no_dead_inputs_in_hybrid(hybrid_report):
    """Sarsılan her girdi çıktının en az bir yaprağını değiştirmeli."""
    assert not hybrid_report.dead_inputs, (
        'Su girdiler /calculate cikitisinda HICBIR sey degistirmiyor '
        '(kullanici degeri giriyor, sonuca girmiyor):\n  '
        + '\n  '.join(hybrid_report.dead_inputs)
        + '\n\nYa cozucuye baglayin, ya arayuzden kaldirin, ya da '
          'gerekcesiyle bu dosyadaki uygun listeye ekleyin.')


def test_no_echo_only_inputs_in_hybrid(hybrid_report):
    """Yalnız kendi yankısını değiştiren girdi de fiilen ölüdür.

    Bir alanı sarsınca çıktıda yalnız "girdiğiniz değer şuydu" yankısı
    değişiyorsa o alan hesaba girmiyor demektir. Yankı, ölü alanı canlı
    göstermenin en kolay yoludur; bu yüzden ayrı sınıflanır.
    """
    allowed = {
        # oxidizer_phase 'gas' secilince cozucu ayni yolu kullanir; faz
        # yalniz yogunluk/Cd gerekcesini etkiler ve o da girdi yankisidir.
        'oxidizer_phase',
    }
    unexpected = sorted(set(hybrid_report.echo_only_inputs) - allowed)
    assert not unexpected, (
        'Su girdiler yalnizca kendi yankilarini degistiriyor: %s' % unexpected)


def test_every_field_is_measurable(hybrid_report):
    """Ölçülemeyen alan sessizce kapsam dışı kalmamalı.

    'Sarsilamadi' ya da 'HTTP 400' diyen her alan ya refakat alanlarıyla
    ölçülebilir hale getirilmeli ya da gerekçesiyle listelenmeli — aksi
    hâlde ölçüm kapsamı sessizce daralır.
    """
    explained = {
        # Bu iki alan 0 = "otomatik" demektir ve sablonda min/max tasimaz;
        # baglam sozlugunde acik deger verilerek olculuyorlar.
        'chamber_diameter_input',
        'chamber_length_override',
    }
    unexplained = {k: v for k, v in hybrid_report.unmeasurable.items()
                   if k not in explained}
    assert not unexplained, (
        'Su alanlar olculemedi: %s' % unexplained)


def test_no_fabricated_constant_outputs(hybrid_report):
    """Hiçbir girdiden etkilenmeyen SAYISAL çıktı uydurma sabittir.

    ``strand_burner_tests: 5``, ``dimensional_accuracy_percent: 99.5`` ve
    ``$500-800`` bu sınıftandı ve üç ayrı elle süpürmeden sağ çıkmışlardı;
    hiçbiri bir hesabın sonucu değildi.

    Not: bu test yalnızca ÖLÇÜLEN girdi kümesi için anlamlıdır. Sarsılmayan
    bir girdinin etkilediği çıktı burada 'sabit' görünür; bu yüzden
    kapsam testi (yukarıda) bu testin ön koşuludur.
    """
    suspicious = [p for p in hybrid_report.constant_outputs
                  if not any(marker in p for marker in LEGITIMATE_CONSTANTS)]
    # Ölçüm kapsamı tam olmadığı sürece bu liste boşalmaz; eşik, kapsam
    # büyüdükçe DÜŞÜRÜLMELİDİR. Yükseltmek uydurmayı gizlemektir.
    assert len(suspicious) <= 330, (
        'Sabit sayisal cikti yapragi beklenenden fazla (%d). Yeni uydurma '
        'sabit eklenmis olabilir. Ilk 25:\n  %s'
        % (len(suspicious), '\n  '.join(suspicious[:25])))


# ---------------------------------------------------------------------------
# Katman B'nin ilk koşusunda bulduğu iki yayın hatasının gerileme bekçileri
# ---------------------------------------------------------------------------

def test_impingement_without_angle_does_not_crash(client):
    """``impingement_angle`` boş gelince /calculate çökmemeli.

    Yayınlanmış sürümde ``IMPINGEMENT_HALF_ANGLE_DEG`` app.py'de
    kullanılıyor ama import edilmiyordu; alanı temizleyen kullanıcı ya da
    bu anahtarı göndermeyen API çağrısı NameError ile HTTP 500 alıyordu.
    """
    payload = dict(HYBRID_BASE, injector_type='impingement',
                   element_pairs=8, orifice_diameter=1.0)
    payload.pop('target_velocity', None)
    resp = client.post('/calculate', json=payload, headers=shake.HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]


def test_injector_detail_never_fabricates_a_hole_plan(client):
    """Devre modeli boyutlandıramazsa delik planı UYDURULMAZ.

    Eski yedek yol her hatada ``n_orifices = 12`` ("typical showerhead
    pattern") ve ``Cd = 0.65`` üretiyor, sonucu kullanıcının seçtiği
    enjektör tipiyle etiketliyordu: 'coaxial' yazan 12 delikli bir
    showerhead. Uyarı yalnız sunucu günlüğüne gidiyordu.
    """
    payload = dict(HYBRID_BASE, injector_type='coaxial',
                   inner_diameter=5, outer_annulus_diameter=10)
    resp = client.post('/calculate', json=payload, headers=shake.HEADERS)
    assert resp.status_code == 200
    motor = resp.get_json()['motor']
    detail = motor['injector_design']
    assert detail['status'] == 'not_analyzed'
    # Uydurulan alanların hiçbiri bulunmamalı
    for fabricated in ('number_of_orifices', 'orifice_diameter_mm',
                       'manifold_diameter_mm', 'discharge_coefficient'):
        assert fabricated not in detail, fabricated
    # ve kullanıcı bunu EKRANDA görmeli
    codes = {w.get('code') for w in (motor.get('design_warnings') or [])
             if isinstance(w, dict)}
    assert 'warn.hybrid.injector_detail_unavailable' in codes


@pytest.mark.parametrize('ui_type,expect_detail', [
    ('showerhead', True),
    ('pintle', True),
    ('swirl', True),
    ('impingement', True),   # v2.6.26: like_impinging'e eşlendi
    ('coaxial', False),      # devre modeli hibritte koaksiyel desteklemiyor
])
def test_injector_type_vocabulary_is_mapped(client, ui_type, expect_detail):
    """Arayüz sözcüğü ile modül sözcüğü arasındaki eşleme çürümemeli.

    Eşleme kopunca çağrı ValueError atar ve motor yedek yola düşer; eskiden
    o yedek uydurma üretiyordu, şimdi 'not_analyzed' diyor. İki durumda da
    kullanıcı seçtiği tipin gerçek analizini KAYBEDER, bu yüzden eşleme
    bekçisi ayrıca gerekir.
    """
    extras = {
        'showerhead': {'target_velocity': 30},
        'pintle': {'outer_diameter': 50, 'pintle_diameter': 25},
        'swirl': {'n_slots': 6},
        'impingement': {'element_pairs': 8, 'impingement_angle': 60},
        'coaxial': {'inner_diameter': 5, 'outer_annulus_diameter': 10},
    }[ui_type]
    payload = dict(HYBRID_BASE, injector_type=ui_type, **extras)
    resp = client.post('/calculate', json=payload, headers=shake.HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    detail = body['motor']['injector_design']
    if expect_detail:
        assert detail.get('status') != 'not_analyzed', detail
        assert detail['number_of_orifices'] > 0
    else:
        assert detail['status'] == 'not_analyzed'
    # Kullanıcının seçtiği ad her durumda korunur (iç sözcük sızmamalı)
    assert detail['injector_type'] == ui_type
    # Enjektörün kendisi her tipte boyutlandırılır — kullanıcı sonuçsuz kalmaz
    assert body['injector']['type'] == ui_type
