# -*- coding: utf-8 -*-
"""ÖH D33-3 / ihracat-pdf a1 — onarım bekçileri.

Her sınıf ÖLÇÜLMÜŞ bir kusurun geri gelmesini görür.
Ölçümler: docs/scofield/raw/OH/D33-3/ihracat-pdf/a1/once.json ⟷ sonra.json
Ters-mutasyon kanıtı: docs/scofield/raw/OH/D33-3/ihracat-pdf/a1/mutasyon.json
"""
import contextlib
import io

import pytest


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _pdf_metni(bayt):
    from pypdf import PdfReader
    return '\n'.join((p.extract_text() or '')
                     for p in PdfReader(io.BytesIO(bayt)).pages)


def _duz(metin):
    """PDF metni SATIR SARAR: 'Submitted values' cümlesi sayfa genişliğinde
    ikiye bölünüyordu (ölçüldü). Cümle arayan bekçi boşlukları düzler."""
    return ' '.join((metin or '').split())


def _patlayici(safety):
    e = (safety or {}).get('explosive_hazards') or {}
    return e.get('explosive_class'), e.get('tnt_equivalent_kg')


# ==========================================================================
# OH-D33-17 — EKRAN HÜKMÜ ⟷ PDF GÜVENLİK HÜKMÜ AYRIŞMASI
# ==========================================================================
class TestOHD3317OksitleyiciTekKaynak:
    """ÖLÇÜLDÜ (``once.json`` K1, taban ``fa7c4e1d``): AYNI gövde iki
    tüketiciye verildiğinde patlayıcı sınıfı ve TNT eşdeğeri ayrışıyordu —

        oxidizer_type='h2o2' -> uç hybrid_h2o2 / 3,4455691215857 kg
                                PDF composite  / 2,100 kg
        oxidizer_type='n2o'  -> uç hybrid_n2o  / 2,2277508917820 kg
                                PDF composite  / 2,100 kg

    3 gövdenin 2'sinde eşitlik YOKTU ve künye bunu söylemiyordu
    (``defaults_applied`` yalnız ``material``). Kök:
    ``pdf_safety.SAFETY_CONTEXT_SOURCES`` tablosunda ``oxidizer_type``
    satırı yoktu; ``build_pdf_safety`` yalnız tablo anahtarlarını geziyor.
    """

    #: Tek sözlük, iki tüketici: uç düz alanları okur, PDF besleyicisi
    #: kendi ölçülmüş kaynak yollarını okur — İKİSİ DE AYNI MOTOR.
    @staticmethod
    def _govde(oks=None, motor_type='hybrid'):
        g = {'motor_type': motor_type,
             'propellant_type': 'composite',
             'chamber_pressure': 20.0,
             'propellant_mass': 5.0,
             'chamber_diameter': 0.1,
             'wall_thickness': 0.005,
             'material': 'steel_4130',
             'chamber_wall_policy': {'wall_thickness_m': 0.005}}
        if oks is not None:
            g['oxidizer_type'] = oks
        return g

    def _uc(self, istemci, govde):
        r = _sessiz(istemci.post, '/analyze_safety', json=dict(govde))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return _patlayici((r.get_json() or {}).get('safety_analysis') or {})

    @staticmethod
    def _pdf(govde):
        from hrma.export.pdf_safety import build_pdf_safety
        safety, kunye = build_pdf_safety(dict(govde), {})
        return _patlayici(safety), kunye

    @pytest.mark.parametrize('oks', ['h2o2', 'n2o', None])
    def test_ayni_govde_ayni_patlayici_hukmu(self, istemci, oks):
        """ŞART: aynı gövde için sınıf ve TNT eşdeğeri EŞİT."""
        govde = self._govde(oks)
        uc = self._uc(istemci, govde)
        pdf, _kunye = self._pdf(govde)
        assert uc == pdf, (
            'ekran hükmü ile belge hükmü ayrıştı (oxidizer_type=%r): '
            'uç %r, PDF %r' % (oks, uc, pdf))

    @pytest.mark.parametrize('oks,beklenen', [('h2o2', 'hybrid_h2o2'),
                                              ('n2o', 'hybrid_n2o')])
    def test_oksitleyici_adi_belgeye_gercekten_iniyor(self, oks, beklenen):
        """Eşitlik 'ikisi de composite' diye SAĞLANMAZ: belge oksitleyicinin
        kendi sınıfını alır (ölçülen kusurun ta kendisi)."""
        (sinif, tnt), _k = self._pdf(self._govde(oks))
        assert sinif == beklenen
        assert tnt != pytest.approx(2.1), (
            'TNT eşdeğeri hâlâ composite sayısında (2,100 kg)')

    def test_cozulemeyen_oksitleyici_kunyede_adiyla_anilir(self):
        """Alan çözülemezse SESSİZ geçilmez: künye ADIYLA söyler."""
        # ÖH D35 / OH-ON-06 (bekçi ÇEVRİLDİ, gerekçe): künye artık
        # "varsayılan UYGULANDI" ile "alan ÇÖZÜLEMEDİ"yi ayırıyor. Eski tek
        # kova belgede "Analyser defaults applied: motor type = None" gibi
        # bir cümle üretiyordu — uygulanmayan bir varsayılanı uygulanmış
        # gibi anlatan bir beyan. Bekçinin konusu ("SESSİZ geçilmez, künye
        # ADIYLA söyler") aynen korunur; yalnız hangi kovada arandığı
        # düzeltildi ve iddia güçlendirildi.
        _p, kunye = self._pdf(self._govde(None))
        anilan = set(kunye.get('unresolved_identity_fields') or []) | set(
            kunye.get('defaults_applied') or {})
        assert 'oxidizer_type' in anilan, (
            'çözülemeyen oksitleyici künyede anılmıyor: %r' % kunye)

    def test_cozulen_oksitleyici_varsayilan_sayilmaz(self):
        """Çözülen alan künyede 'varsayılan' diye anılmaz, KAYNAĞIYLA anılır."""
        _p, kunye = self._pdf(self._govde('h2o2'))
        assert 'oxidizer_type' not in (kunye.get('defaults_applied') or {})
        assert (kunye.get('inputs_resolved') or {}).get('oxidizer_type') \
            == 'md:oxidizer_type'

    def test_istek_alani_cozucunun_yankisindan_once_gelir(self):
        """Kullanıcının yazdığı ad, çözücünün yankıladığı addan ÖNCE."""
        from hrma.export.pdf_safety import SAFETY_CONTEXT_SOURCES
        yollar = [y for y, _b in SAFETY_CONTEXT_SOURCES['oxidizer_type']]
        assert yollar[0] == 'md:oxidizer_type', yollar

    def test_gercek_cozucu_kosumunda_yol_yasiyor(self, istemci):
        """Yollar TAHMİN değil: GERÇEK ``/calculate`` hibrit yanıtında
        ``oxidizer_type`` çözülüyor (``once.json`` K2 ile aynı koşum)."""
        from hrma.export.pdf_safety import build_pdf_safety
        r = _sessiz(istemci.post, '/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'h2o2'})
        assert r.status_code == 200
        cr = r.get_json()
        md = cr.get('motor') or {}
        _safety, kunye = build_pdf_safety(md, cr)
        assert 'oxidizer_type' not in (kunye.get('defaults_applied') or {}), (
            'gerçek hibrit koşumunda oksitleyici adı hâlâ çözülemiyor')
        assert (kunye.get('inputs_resolved') or {}).get('oxidizer_type', '') \
            .endswith('oxidizer_type')

    def test_kati_motorda_hukum_degismez(self, istemci):
        """KAPSAM: oksitleyici yalnız hibrit dalında okunur; katı motorun
        yayımlanan sayısı bu onarımdan ETKİLENMEZ."""
        govde = self._govde('h2o2', motor_type='solid')
        uc = self._uc(istemci, govde)
        pdf, _k = self._pdf(govde)
        assert uc == pdf
        assert pdf[0] == 'composite'


# ==========================================================================
# OH-D33-15 — GERİ ÇEKİLEN EMNİYET KATSAYILARI BELGEDE BEYAN EDİLİR
# ==========================================================================
class TestOHD3315GeriCekmeBeyani:
    """ÖLÇÜLDÜ (``once.json`` K3, taban ``fa7c4e1d``): ``app.py``
    ``structural_withheld`` kaydını yayımlıyor ama TÜKETİCİSİ YOKTU.
    ``safety_factor = 4,0`` + ``min_safety_factor = 4,0`` taşıyan gövdenin
    ``complete`` raporunda ``Structural Analysis`` bölümü HİÇ oluşmuyor,
    düşürülen alan adlarının / gönderilen sayıların / gerekçenin izi
    0 / 0 / 0 çıkıyordu — satırlar SESSİZCE kayboluyordu.
    """

    GOVDE = {'motor_data': {'motor_name': 'BEKCI-WH'},
             'analysis_results': {'structural': {'safety_factor': 4.0,
                                                 'min_safety_factor': 4.0}}}

    @pytest.fixture(scope='class')
    def metin(self, istemci):
        import copy
        r = _sessiz(istemci.post, '/api/export-pdf/complete',
                    json=copy.deepcopy(self.GOVDE))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return _duz(_pdf_metni(r.get_data()))

    def test_bolum_olusuyor(self, metin):
        assert 'Structural Analysis' in metin, (
            'geri çekme kaydı varken yapısal bölüm hâlâ hiç oluşmuyor')

    def test_dusurulen_alan_adlari_basiliyor(self, metin):
        for ad in ('min safety factor', 'safety factor'):
            assert ad in metin.lower(), ad

    def test_gerekce_kodu_basiliyor(self, metin):
        assert 'design_basis_unknown' in metin

    def test_gonderilen_sayi_sessizce_kaybolmuyor(self, metin):
        assert 'Submitted values' in metin
        assert '4.0' in metin

    def test_cozucunun_kendi_cumlesi_aynen_tasiniyor(self, metin):
        """Rapor katmanı gerekçeyi YENİDEN YAZMAZ (Design basis deseni)."""
        assert 'VERIFICATION of an as-built' in metin

    def test_kayit_yoksa_beyan_da_yok(self):
        """ÖK-22: söylenecek bir şey yoksa satır da yazılmaz."""
        from hrma.export.pdf_generator import PDFReportGenerator
        assert PDFReportGenerator._structural_withheld_note({}) == ''
        assert PDFReportGenerator._structural_withheld_note(
            {'structural_withheld': {}}) == ''
        assert PDFReportGenerator._structural_withheld_note(
            {'structural_withheld': {'fields': []}}) == ''

    def test_saglikli_yol_beyan_basmaz(self, istemci):
        """Tabanı BİLİNEN katsayı geri çekilmez; beyan satırı da çıkmaz."""
        r = _sessiz(istemci.post, '/api/export-pdf/complete', json={
            'motor_data': {'motor_name': 'BEKCI-WH2'},
            'analysis_results': {
                'structural': {'safety_factor': 4.0,
                               'min_safety_factor': 4.0},
                'structural_analysis': {
                    'chamber_analysis': {
                        'design_mode': 'size',
                        'safety_factor_is_tautological': True},
                    'safety_analysis': {'safety_factors': {'chamber': 4.0}}}}})
        assert r.status_code == 200
        metin = _duz(_pdf_metni(r.get_data()))
        assert 'Safety factors withheld' not in metin
