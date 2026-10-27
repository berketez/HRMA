# -*- coding: utf-8 -*-
"""ÖH D26 / app-api aşama-2 bekçileri — P16B1-49 **B AYAĞI** (bant kanonu).

Ölçüm gövdesi: ``docs/scofield/raw/OH/D26/app-api/a2/olcum.py``
Önce/sonra sayıları: ``.../once.json``, ``.../sonra.json``
Ters-mutasyon kanıtı: ``.../mutasyon.json``

Kalemin B ayağı iki turda (D24, D25) ölçülüp açık bırakılmıştı; engel
"hangi okumanın KANON olduğu ayrı bir birim-kanonu kararı" idi. Karar bu
turda ana modelden geldi:

    KANON = SI (``CANONICAL_LIMITS``; metre/bar/kelvin). ``FORM_LIMITS``
    yalnız form katmanının GÖRÜNTÜ birimidir, kanondan TÜRETİLİR, AYRI SAYI
    TUTAMAZ. ``_band_kaydi`` arama sırası (önce kanonik, sonra takma ad)
    tektir ve iki çağıran da aynı sözleşmeyi uygular.

Her sınıf, onarımın geri alınması hâlinde kırmızı verecek biçimde
yazılmıştır (ters-mutasyonla doğrulandı).
"""
import ast
import pathlib

import pytest

from hrma.engines.solid_rocket_engine import SOLID_INSULATION

from hrma.validation.motor_validation import (
    CANONICAL_LIMITS, FIELD_ALIASES, FORM_LIMITS, MotorDataValidator,
    _bant_kanonu_denetimi, kanon_gorunumu)

KOK = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


#: Kanonik astar kalınlığı (mm) — ürünün tek tanımı, kopyalanmaz.
_ASTAR_MM = SOLID_INSULATION['thickness_m'] * 1000.0


def _kati_taban():
    """``/calculate_solid`` taban yükü — merkezî katalogdan (tek kaynak)."""
    from tests.support import uc_katalogu
    return dict(uc_katalogu.taban_yuk('/calculate_solid'))


def _hibrit_taban():
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    g = dict(HYBRID_BASE)
    g['include_plots'] = False
    return g


def _alanlar(govde):
    return [k.get('field') for k in (govde or {}).get('invalid_fields') or []
            if isinstance(k, dict)]


# ===========================================================================
# 1) BANT KANONU — birim çelişkili form bandı ayrı sayı tutamaz
# ===========================================================================
class TestP16B149BantKanonu:
    """Aynı bandın mm görünümü üründe TEK sayı olmalı.

    ÖLÇÜLDÜ (``once.json`` K1/K2, taban ``7751531``)::

        FORM_LIMITS['solid']['chamber_diameter'] = (10, 2000, 'mm')
        CANONICAL_LIMITS['chamber_diameter']     = 0,01 - 5,0 m
                                     mm görünümü = (10, 5000)
        bolted_joint.seal_diameter_max_mm()      = 5000,0

    Yani ALT uçlar birebir örtüşüyor (türetilmişler), ÜST uçlar kopmuş:
    ``chamber_diameter``ın mm üst sınırı üründe 2000 ve 5000 diye İKİ AYRI
    sayıyla dolaşıyordu. ``grain_length`` için 5000 ⟷ 10000.
    """

    #: Kanonik adı olan ve birimi kanondan FARKLI olan form girdileri.
    BIRIM_CELISKILI = [('solid', 'chamber_diameter'), ('solid', 'grain_length')]

    def test_envanter_degismedi(self):
        """Birim çelişkili girdi kümesi ölçüldüğü gibi: iki girdi."""
        bulunan = [
            (form, alan)
            for form, alanlar in FORM_LIMITS.items()
            for alan, (_alt, _ust, birim) in alanlar.items()
            if alan in CANONICAL_LIMITS
            and CANONICAL_LIMITS[alan]['unit'] != birim]
        assert sorted(bulunan) == sorted(self.BIRIM_CELISKILI), (
            'birim çelişkili form bandı kümesi değişti; kanon denetimi '
            'yeni girdiyi de bağlamalı: %r' % (bulunan,))

    @pytest.mark.parametrize('form,alan', BIRIM_CELISKILI)
    def test_form_bandi_kanonun_salt_birim_cevrimi(self, form, alan):
        """Sayı türetilir; elle yazılan bir üst sınır kırmızı verir."""
        birim = FORM_LIMITS[form][alan][2]
        assert FORM_LIMITS[form][alan] == kanon_gorunumu(alan, birim)
        assert FORM_LIMITS[form][alan][:2] == (
            CANONICAL_LIMITS[alan]['min'] * 1000.0,
            CANONICAL_LIMITS[alan]['max'] * 1000.0)

    def test_mm_ust_siniri_urunde_tek_sayi(self):
        """Kardeş tüketici ile aynı sayı — ölçülen çelişki kapandı.

        ``bolted_joint.seal_diameter_max_mm()`` kanondan ``* 1e3`` ile
        türetiyor; form bandı 2000 diyordu. İki tüketici aynı bandın mm
        görünümü için farklı sayı söyleyemez.
        """
        from hrma.analysis.bolted_joint import seal_diameter_max_mm
        assert float(seal_diameter_max_mm()) == float(
            FORM_LIMITS['solid']['chamber_diameter'][1])

    def test_kaynakta_elle_yazilmis_sayi_kalmadi(self):
        """Kaynak denetimi: iki girdi ÇAĞRI ile üretiliyor, sabitle değil.

        Değer eşitliği yeterli değildir — birisi ``(10.0, 5000.0, 'mm')``
        yazıp aynı sayıyı ELLE sabitlerse tek kaynak yine kopar ve kanon
        değiştiğinde form bandı sessizce bayatlar.
        """
        kaynak = (KOK / 'hrma' / 'validation' /
                  'motor_validation.py').read_text(encoding='utf-8')
        agac = ast.parse(kaynak)
        form_limits = None
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Assign) and any(
                    isinstance(h, ast.Name) and h.id == 'FORM_LIMITS'
                    for h in dugum.targets):
                form_limits = dugum.value
        assert isinstance(form_limits, ast.Dict), 'FORM_LIMITS bulunamadı'
        for form_anahtar, form_deger in zip(form_limits.keys,
                                            form_limits.values):
            if getattr(form_anahtar, 'value', None) != 'solid':
                continue
            for alan_anahtar, alan_deger in zip(form_deger.keys,
                                                form_deger.values):
                if alan_anahtar.value not in ('chamber_diameter',
                                              'grain_length'):
                    continue
                assert isinstance(alan_deger, ast.Call), (
                    '%s hâlâ elle yazılmış bir demet' % alan_anahtar.value)
                assert alan_deger.func.id == 'kanon_gorunumu'

    def test_kanon_denetimi_ihlali_yakalar(self):
        """Denetimin kendisi totolojik değil: elle sayı koyunca patlar."""
        eski = FORM_LIMITS['solid']['chamber_diameter']
        FORM_LIMITS['solid']['chamber_diameter'] = (10.0, 2000.0, 'mm')
        try:
            with pytest.raises(RuntimeError, match='BANT KANONU IHLALI'):
                _bant_kanonu_denetimi()
        finally:
            FORM_LIMITS['solid']['chamber_diameter'] = eski
        _bant_kanonu_denetimi()          # geri konunca yine sessiz

    def test_arama_sirasi_belirsiz_degil(self):
        """KURAL 2 — bir ad hem kanonik hem takma ad olamaz."""
        assert set(FIELD_ALIASES) & set(CANONICAL_LIMITS) == set()
        eski = dict(FIELD_ALIASES)
        FIELD_ALIASES['thrust'] = {'kanonik': 'thrust', 'carpanlar': (1.0,),
                                   'birim': 'N', 'sifir_otomatik': False}
        try:
            with pytest.raises(RuntimeError, match='BANT KANONU IHLALI'):
                _bant_kanonu_denetimi()
        finally:
            FIELD_ALIASES.clear()
            FIELD_ALIASES.update(eski)
        _bant_kanonu_denetimi()

    def test_kanonik_ad_once_aranir(self):
        """``_band_kaydi`` kanonik adı SI okur; takma ad çarpanla gelir."""
        v = MotorDataValidator()
        kanonik = v._band_kaydi('chamber_diameter', 1.0)
        assert kanonik['takma_ad'] is None
        assert (kanonik['alt'], kanonik['ust'], kanonik['birim']) == (
            0.01, 5.0, 'm')
        takma = v._band_kaydi('chamber_diameter_input', 1.0)
        assert takma['takma_ad'] is not None
        assert takma['kanonik'] == 'chamber_diameter'
        assert takma['birim'] == 'mm'

    def test_kanon_tablosu_ornekler_arasinda_paylasilmiyor(self):
        """Modül düzeyine taşıma, bugünkü örnek-başına sözlüğü bozmadı."""
        a, b = MotorDataValidator(), MotorDataValidator()
        assert a.limits == b.limits == {
            ad: dict(band) for ad, band in CANONICAL_LIMITS.items()}
        a.limits['thrust']['max'] = 1.0
        assert b.limits['thrust']['max'] == CANONICAL_LIMITS['thrust']['max']
        assert CANONICAL_LIMITS['thrust']['max'] == 1000000


# ===========================================================================
# 2) DAVRANIŞ — kanonun kestiği yer neresi
# ===========================================================================
class TestP16B149KatiUcDavranisi:
    """``/calculate_solid`` bandı artık kanonun mm görünümünde kesiyor.

    ÖNCE (ORTAK taban ağacı ``7751531``, ``once.json`` K3)::

        chamber_diameter = 2500 / 3700 / 4999 mm -> 400 "between 10-2000"
        grain_length     = 7000 / 9999 mm        -> 400 "between 50-5000"
        Ø3700 / L9000 tutarlı katı motor gövdesi -> 400 (tasarım YOK)

    SONRA (``sonra.json`` K3): aynı gövdeler bant kapısını geçiyor; SRB
    ölçeğindeki gövde 200 ile TAM tasarım yayımlıyor. Üst uç kaybolmadı:
    5001 mm ve 10001 mm hâlâ adıyla 400 alıyor.
    """

    @pytest.mark.parametrize('alan,deger', [
        ('chamber_diameter', 2500.0),
        ('chamber_diameter', 3700.0),
        ('chamber_diameter', 4999.0),
        ('grain_length', 7000.0),
        ('grain_length', 9999.0),
    ])
    def test_kanon_ici_deger_bant_kapisindan_gecer(self, client, alan, deger):
        govde = _kati_taban()
        govde[alan] = deger
        if alan == 'chamber_diameter':
            # v3.0.1 T-ÇAPA-B: K-A kasa kapısı (``grain_does_not_fit_case``)
            # hazne ≥ tane + 2·astar ister; eskiden tane = hazne veriliyordu
            # ve 422 alan adı olarak ``chamber_diameter``i taşıyordu. Tane,
            # kanonik astar kalınlığı (SOLID_INSULATION) kadar içeri alınır.
            govde['outer_diameter'] = deger - 2.0 * _ASTAR_MM
            govde['core_diameter'] = round(deger * 0.4, 3)
        r = client.post('/calculate_solid', json=govde)
        assert r.status_code != 400, (
            '%s = %s hâlâ bant kapısında kesiliyor: %s'
            % (alan, deger, r.get_data(as_text=True)[:200]))
        assert alan not in _alanlar(r.get_json())

    @pytest.mark.parametrize('alan,deger,ust', [
        ('chamber_diameter', 5001.0, 5000.0),
        ('grain_length', 10001.0, 10000.0),
    ])
    def test_kanonun_ustu_hala_adiyla_reddedilir(self, client, alan, deger,
                                                 ust):
        govde = _kati_taban()
        govde[alan] = deger
        r = client.post('/calculate_solid', json=govde)
        assert r.status_code == 400
        kayit = [k for k in (r.get_json() or {}).get('invalid_fields') or []
                 if k.get('field') == alan]
        assert kayit, r.get_data(as_text=True)[:200]
        assert kayit[0]['accepted_range'] == [
            CANONICAL_LIMITS[alan]['min'] * 1000.0, ust]
        assert kayit[0]['unit'] == 'mm'
        assert kayit[0]['motor_form'] == 'solid'

    @pytest.mark.parametrize('alan,deger', [
        ('chamber_diameter', 5.0),
        ('grain_length', 10.0),
    ])
    def test_alt_uc_degismedi(self, client, alan, deger):
        """ÖK-22 karşı-testi: kanonun ALT ucu zaten türetilmişti, kaymadı."""
        govde = _kati_taban()
        govde[alan] = deger
        r = client.post('/calculate_solid', json=govde)
        assert r.status_code == 400
        assert alan in _alanlar(r.get_json())

    def test_saglikli_taban_yuku_hala_200(self, client):
        """ÖK-22: ürünün kendi örnek projesi etkilenmedi."""
        r = client.post('/calculate_solid', json=_kati_taban())
        assert r.status_code == 200

    def test_srb_olcegindeki_kati_motor_artik_yayimlaniyor(self, client):
        """Kalemin kullanıcı tarafındaki bedeli: ölçekli motor reddediliyordu.

        ÖNCE 400 ("between 10-2000") — geometrisi TUTARLI, kanonun İÇİNDE bir
        katı motor tasarımı bant çelişkisi yüzünden hiç hesaplanamıyordu.
        """
        govde = _kati_taban()
        # v3.0.1 T-ÇAPA-B: hazne = tane + 2·astar (K-A kasa kapısı); kalan
        # kırmızı web_thickness bandı (≤ 1000 mm) — DEVİR, test/RAPOR.md.
        govde.update({'chamber_diameter': 3700.0 + 2.0 * _ASTAR_MM,
                      'outer_diameter': 3700.0,
                      'core_diameter': 1500.0, 'web_thickness': 1100.0,
                      'grain_length': 9000.0, 'grain_count': 1})
        r = client.post('/calculate_solid', json=govde)
        assert r.status_code == 200
        govde_yanit = r.get_json() or {}
        assert govde_yanit.get('error') is None, govde_yanit.get('error')
        ozet = govde_yanit.get('design_summary') or {}
        assert ozet.get('performance', {}).get('average_thrust_N', 0) > 0


# ===========================================================================
# 3) İKİ ÇAĞIRAN, TEK SÖZLEŞME
# ===========================================================================
class TestP16B149IkiCagiranTekSozlesme:
    """Aynı bandı çağıran iki uç aynı reddi vermeli.

    ÖLÇÜLDÜ (``once.json`` K4, worktree a1 sonrası)::

        {..., chamber_diameter: 0,2}  /calculate                -> 422 adlı
                                      /api/transient-analysis   -> 200,
            yanıt alanı HİÇ göndermeyen istekle BİT-AYNI (sessizce yutuldu)

    Aynı satır ``chamber_length`` / ``port_diameter`` / ``temperature``
    için de ölçüldü: dördü de kardeş uçta sessizdi.
    """

    OKUNMAYAN = [
        ('chamber_diameter', 0.2, 'chamber_diameter_input'),
        ('chamber_length', 0.5, 'chamber_length_override'),
        ('port_diameter', 0.05, 'initial_port_diameter'),
        ('temperature', 3000.0, 'chamber_temperature'),
    ]

    @pytest.mark.parametrize('ad,deger,urun_adi', OKUNMAYAN)
    def test_kardes_ucta_da_adiyla_reddedilir(self, client, ad, deger,
                                              urun_adi):
        govde = _hibrit_taban()
        govde[ad] = deger
        r = client.post('/api/transient-analysis', json=govde)
        assert r.status_code == 422, (
            '%s hâlâ sessizce yutuluyor: %s'
            % (ad, r.get_data(as_text=True)[:200]))
        g = r.get_json() or {}
        assert g.get('error') == 'unread_canonical_field'
        kayit = [k for k in g.get('invalid_fields') or []
                 if k.get('field') == ad]
        assert kayit and kayit[0]['use_instead'] == urun_adi
        assert '/api/transient-analysis' in kayit[0]['message']

    @pytest.mark.parametrize('ad,deger,_urun', OKUNMAYAN)
    def test_iki_uc_ayni_kodu_veriyor(self, client, ad, deger, _urun):
        govde = _hibrit_taban()
        govde[ad] = deger
        a = client.post('/calculate', json=govde)
        b = client.post('/api/transient-analysis', json=govde)
        assert a.status_code == b.status_code == 422
        assert (a.get_json() or {}).get('error') == \
            (b.get_json() or {}).get('error') == 'unread_canonical_field'

    def test_saglikli_govde_iki_ucta_da_200(self, client):
        """ÖK-22 karşı-testi: kapı yalnız GÖNDERİLEN kanonik adı görür."""
        govde = _hibrit_taban()
        # ÖH D27 fix-27b — SOĞUTMA ALANI GÖVDEDEN DÜŞÜRÜLÜR (iddia AYNEN
        # kalır). Paylaşılan ``HYBRID_BASE`` gövdesi
        # ``cooling_channels='none'`` taşıyor. D27 hibrit a1 (``d198489``,
        # ara commit ``d44f9548``; defter OH-D26-05) bu alanı
        # ``/api/transient-analysis`` ucunda ADIYLA reddediyor (422
        # ``unread_field``), çünkü ölçüldü: alan yayımlanan hiçbir sayıya
        # girmiyor (dört seçim BİT-AYNI gövde, 0/3238 yaprak). Yani 422
        # DOĞRU davranıştır — gerileme değil, fail-closed onarım; kırmızı
        # bu bekçinin GÖVDESİNDEN doğuyordu.
        #
        # Bu testin iddiası KANONİK BANT kapısına aittir (kapı yalnız
        # GÖNDERİLEN kanonik adı görür, sağlıklı gövdeyi ret etmez);
        # soğutma sözleşmesiyle ilgisi yoktur ve o sözleşmenin CANLI
        # bekçisi kaldırılmadı, yerinde duruyor:
        # ``tests/test_d27_hibrit_a1.py::TestOHD2605SogutmaSecimiYutulmuyor``
        # (altı tanımlı seçimin altısı da 422; ölçüldü fix-27b M2).
        # ÖLÇÜLDÜ (fix-27b ``olcum_once.json`` B2): alan gövdedeyken
        # /calculate 200 · transient 422; alan düşünce ikisi de 200.
        govde.pop('cooling_channels', None)
        assert client.post('/calculate', json=govde).status_code == 200
        assert client.post('/api/transient-analysis',
                           json=govde).status_code == 200

    def test_bant_disi_deger_hala_400(self, client):
        """Bant kapısı kapının ÜSTÜNDE kalır: 400 sözleşmesi bozulmadı."""
        govde = _hibrit_taban()
        govde['chamber_diameter'] = 1e9
        r = client.post('/api/transient-analysis', json=govde)
        assert r.status_code == 400
        assert 'chamber_diameter' in _alanlar(r.get_json())

    def test_bant_cagiranlarinin_hepsi_ayni_kapiyi_tasiyor(self):
        """Kaynak denetimi: yeni bir çağıran eklenirse bekçi kırmızı verir.

        ``validate_motor_data_detailed`` çağıran her fonksiyon,
        ``_reject_unread_canonical_fields`` kapısını da taşımak zorundadır —
        aksi hâlde aynı bant üçüncü bir uçta yine sessiz kalır.
        """
        agac = ast.parse((KOK / 'hrma' / 'app.py').read_text(encoding='utf-8'))
        tasiyanlar, cagiranlar = set(), set()
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.FunctionDef):
                continue
            adlar = set()
            for alt in ast.walk(dugum):
                if isinstance(alt, ast.Call):
                    f = alt.func
                    ad = getattr(f, 'attr', None) or getattr(f, 'id', None)
                    if ad:
                        adlar.add(ad)
            if 'validate_motor_data_detailed' in adlar:
                cagiranlar.add(dugum.name)
                if '_reject_unread_canonical_fields' in adlar:
                    tasiyanlar.add(dugum.name)
        assert cagiranlar == {'calculate', 'transient_analysis'}, cagiranlar
        assert cagiranlar == tasiyanlar, (
            'bant kapısını çağırıp okunmayan-ad kapısını taşımayan uç: %r'
            % sorted(cagiranlar - tasiyanlar))
