"""KATMAN A bekçisi: arayüzdeki her alan bir toplayıcıya bağlı mı?

Bu test, arka uç testlerinin YAPISAL OLARAK göremediği bir kusur sınıfını
yakalar. v2.6.25'te hibritin ``chamber_material`` / ``wall_thickness`` /
``cooling_channels`` alanları için arka uç doğru yazılmıştı; HTTP katmanını
sınayan her test "bağlandı" derdi. Ama şablonun toplayıcısı o üç alanı hiç
göndermiyordu — kusur arka uçta değil, ŞABLON İLE PAYLOAD ARASINDAYDI.

Kural: şablondaki her form alanı ya bir toplayıcıda okunur, ya aşağıdaki
gerekçeli listede yer alır. Üçüncü seçenek yoktur. Yeni bir alan eklenip
bağlanmazsa bu test KIRMIZI olur.

Beyaz listeyi genişletmek, ölü alanı meşrulaştırmanın en kolay yoludur;
her giriş bir GEREKÇE taşımak zorundadır ve gerekçe "sonra bağlarız"
olamaz — o durumda alan arayüzden kaldırılmalıdır.
"""

import pytest

from tests.support import inventory


# ---------------------------------------------------------------------------
# 1. BAŞKA UCA GİDEN ALANLAR (meşru)
#    Bu alanlar /calculate'e değil, kendi endpoint'lerine gider.
# ---------------------------------------------------------------------------
OTHER_ENDPOINT = {
    'hybrid': {
        'traj_alt_start': '/api/trajectory-analysis',
        'traj_alt_end': '/api/trajectory-analysis',
        'traj_points': '/api/trajectory-analysis',
        'initial_mass': '/api/trajectory-analysis',
        'final_mass': '/api/trajectory-analysis',
        'reference_area': '/api/trajectory-analysis',
    },
    'solid': {
        'traj_burn_time': '/api/trajectory-analysis',
        'traj_drag_coeff': '/api/trajectory-analysis',
        'traj_final_mass': '/api/trajectory-analysis',
        'traj_initial_mass': '/api/trajectory-analysis',
        'traj_ref_area': '/api/trajectory-analysis',
    },
    'liquid': {
        'traj_burn_time': '/api/trajectory-analysis',
        'traj_drag_coeff': '/api/trajectory-analysis',
        'traj_final_mass': '/api/trajectory-analysis',
        'traj_initial_mass': '/api/trajectory-analysis',
        'traj_ref_area': '/api/trajectory-analysis',
    },
}

# ---------------------------------------------------------------------------
# 2. İSTEMCİ TARAFI ALANLAR (meşru)
#    Sunucuya hiç gitmezler; yalnız tarayıcıdaki görünümü ayarlarlar.
# ---------------------------------------------------------------------------
CLIENT_ONLY = {
    'hybrid': {
        'viz_ds_dch': '3B gorunum kaydiricisi (yalniz sahne olcegi)',
        'viz_ds_eps': '3B gorunum kaydiricisi',
        'viz_ds_lstar': '3B gorunum kaydiricisi',
    },
    'solid': {},
    'liquid': {},
}

# ---------------------------------------------------------------------------
# 3. ÇÖZÜCÜYE ULAŞMAYAN, ARKA UÇTA KARŞILIĞI OLMAYAN ALANLAR
#
#    v2.6.26'da KATMAN A ile bulundu; önceki denetim bunları GÖREMEMİŞTİ
#    çünkü yalnız /calculate'e ULAŞAN 41 alanı ölçmüştü, ulaşmayan 51'ine
#    hiç bakmamıştı.
#
#    Bunların hiçbirinin motorda ya da enjektör modülünde karşılığı yok;
#    bağlamak yeni fizik modeli yazmak demek. Kullanıcıya "bu alan sonuca
#    girmiyor" rozetiyle bildiriliyorlar (sessiz bırakmak yasak).
#
#    KALICI ÇÖZÜM: ya modellenecekler ya arayüzden kaldırılacaklar.
#    Bu liste bir BORÇ KAYDIDIR, kalıcı bir muafiyet değil.
# ---------------------------------------------------------------------------
#    2026-07-30 GÜNCELLEMESİ — bu listenin 8 kalemi KAPANDI, 2'si KALDIRILDI.
#    Bağlananlar ve ölçülen etkileri (HTTP /calculate yanıtında değişen
#    yaprak sayısı):
#      safety_factor           48   yapısal analizin tasarım SF hedefi; ayrıca
#                                   gerçek cidar geçildiği için modül artık
#                                   BOYUTLANDIRMA değil DOĞRULAMA modunda
#      chamber_length_override 88   L* ile türetilen kamara boyunu ezer
#      nozzle_material         90   boğaz termal (izin verilen sıcaklık marjı)
#                                   + erozyon (yayımlanmış bant varsa)
#      injector_material       14   plaka eğilme gerilmesi, SF, gereken
#                                   kalınlık, kütle (Roark 11.2-10b + ASME
#                                   PG-52 ligament verimi)
#      swirl_chamber_diameter   9   Giffen-Muraszew K = A_p/(D_s*d_o) icindeki D_s
#      swirl_angle             35   hedef sprey yarı açısı -> ters çözücü
#                                   (swirl_K_from_theta) K'yı ondan bulur
#    Kaldırılanlar (aynı kavramın ikinci, bağlanmamış kopyasıydılar):
#      nozzle_contour      -> nozzle_type'a katıldı (parabolik seçenek taşındı)
#      injection_velocity  -> target_velocity zaten bağlıydı; ayrıca hesap
#                             sonrası bu GİRDİ kutusuna çözücünün çıkış hızı
#                             yazılıyordu (kendini doğrulayan döngü)
DECLARED_UNMODELLED = {
    'hybrid': {
        'annular_gap': ('koaksiyel/pintle anulus araligi - cozucu bunu ic ve '
                        'dis captan TURETIR (D_avg ve hedef alandan), girdi '
                        'olarak alinsa cozumle celisirdi'),
        'skip_distance': ('pintle skip mesafesi - yayimlanmis korelasyon yok; '
                          'uydurma katsayi yasak (BORC)'),
        # 'hole_pattern' 14 Agu 2026'da BAGLANDI (form->istek->400
        # dogrulama->yanit; test_hole_pattern_baglama.py) ve bu listeden
        # cikarildi - bekci tam da bunu yakaladi (rot testi, 15 Agu).
        'pintle_spray_angle': ('pintle sprey acisi - cozucu bunu toplam '
                               'momentum oranindan HESAPLAR; sonuctaki degere '
                               'bakiniz'),
    },
    'solid': {},
    'liquid': {},
}


def _allowed(page):
    return (set(OTHER_ENDPOINT.get(page, {}))
            | set(CLIENT_ONLY.get(page, {}))
            | set(DECLARED_UNMODELLED.get(page, {})))


@pytest.fixture(scope='module')
def inventories():
    return inventory.build_all()


@pytest.mark.parametrize('page', sorted(inventory.PAGES))
def test_every_field_is_collected_or_declared(inventories, page):
    """Sablondaki her alan ya toplaniyor ya gerekceli listede."""
    data = inventories[page]
    unexplained = sorted(data.uncollected - _allowed(page))
    assert not unexplained, (
        f'{data.template}: su alanlar hicbir toplayicida okunmuyor ve '
        f'gerekceli listede de yok:\n  ' + '\n  '.join(unexplained)
        + '\n\nYa bir toplayiciya baglayin, ya arayuzden kaldirin, ya da '
          'tests/test_field_wiring_layer_a.py icindeki uygun listeye '
          'GEREKCESIYLE ekleyin.')


@pytest.mark.parametrize('page', sorted(inventory.PAGES))
def test_declared_lists_do_not_rot(inventories, page):
    """Listedeki alan sonradan baglanirsa listeden CIKARILMALI.

    Aksi halde liste zamanla anlamini yitirir ve gercekten olu olan alani
    gizlemeye baslar.
    """
    data = inventories[page]
    stale = sorted(_allowed(page) - data.uncollected - data.template_fields)
    assert not stale, (
        f'{data.template}: su alanlar artik sablonda yok, listeden '
        f'cikarilmali: {stale}')

    now_collected = sorted(
        (set(DECLARED_UNMODELLED.get(page, {})) | set(CLIENT_ONLY.get(page, {})))
        & (data.template_fields - data.uncollected))
    assert not now_collected, (
        f'{data.template}: su alanlar artik TOPLANIYOR, "modellenmiyor" '
        f'listesinden cikarilmali: {now_collected}')


@pytest.mark.parametrize('page', sorted(inventory.PAGES))
def test_collector_exists_and_reads_fields(inventories, page):
    """Toplayici bulunabilmeli ve bos olmamali."""
    data = inventories[page]
    assert len(data.collected_fields) > 10, (
        f'{data.template}: {data.collector} yalnizca '
        f'{len(data.collected_fields)} alan okuyor - toplayici bulunamamis '
        f'ya da yanlis kopya taranmis olabilir')


def test_thermal_fields_regression(inventories):
    """v2.6.25'in yarim kalan duzeltmesi bir daha yarim kalmasin."""
    collected = inventories['hybrid'].collected_fields
    for field in ('chamber_material', 'wall_thickness', 'cooling_channels'):
        assert field in collected, (
            f'{field} hibrit toplayicisinda yok - v2.6.25 hatasi geri geldi')


def test_no_duplicate_collector_shadowing():
    """Ayni ada sahip ikinci bir toplayici tanimi olmamali.

    v2.6.26'da app.js ve advanced.html'de iki ayri getFormData vardi; inline
    olan digerini golgeliyor, ikisi FARKLI varsayilanlar tasiyordu ve hangi
    kopyanin gecerli oldugu koddan anlasilmiyordu.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    js = (root / 'hrma/static/js/app.js').read_text(encoding='utf-8')
    assert 'function getFormData(' not in js, (
        'app.js icinde ikinci bir getFormData tanimi var - '
        'advanced.html inline surumunu golgeler')
