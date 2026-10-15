"""ÖH Dalga-32 · sıvı kulvarı a1 — OH-D31-11 bekçileri.

KALEM: N₂O yoğunluğu iki uçta iki sayı (defterde 742,93 ⟷ 785,10; %5,37).

ÖLÇÜLDÜ (taban ``dd1dcddc``, ``docs/scofield/raw/OH/D32/sivi/a1/once.json``)
— kalemin başlığı KISMEN ÇÜRÜDÜ ve kusur YERİNİ DEĞİŞTİRDİ:

* 742,93 ⟷ 785,10 farkı bir HATA DEĞİLDİR, DURUM farkıdır: aynı EOS
  (Lemmon & Span 2006) doymuş sıvı için 298,15 K'de 742,9330, 293,15 K'de
  785,1040 kg/m³ verir (``once.json`` K4). D31 dersi 24: iki uç aynı
  büyüklüğü farklı sayıyla yayımlıyorsa ÖNCE sıcaklık/faz aynı mı ölç.
* GERÇEK kusur ``/api/get-propellant-properties`` ucundadır ve ölçüldü
  (``once.json`` K7): aynı uç, aynı akışkan, İKİ sayı — ve ayrımı yapan
  şey sorulan büyüklükle ilgisi olmayan bir KATEGORİ ETİKETİ::

      propellant_type='hybrid_oxidizer' -> 745,0    (kataloğun 298,15 K değeri)
      propellant_type='oxidizer'        -> 785,1040 (EOS, 293,15 K)
      propellant_type='hybrid_fuel'     -> 785,1040
      propellant_type yok               -> 785,1040

  Dördünün de künyesi ``state_temperature_K = 293,15`` diyordu; yani
  745,0 dalında YAYIMLANAN SAYI KENDİ KÜNYESİNİ YALANLIYORDU (%5,383).
* Kardeş uç ``/api/oxidizer-properties`` aynı soruyu Z1'in DENETLENMİŞ
  tek kapısından çözüyordu (``n2o_saturated_liquid_density`` -> CoolProp/
  REFPROP EOS, Q=0, üçlü/kritik nokta bandı + kenetlenme denetimi).
  Aynı durumda (293,15 K) iki uç %5,108 ayrışıyordu (``once.json`` K8).

HÜKÜM (Berke -> Astra, 15 Eylül 2026,
``docs/scofield/raw/OH/D32/oturum-devri/astra/astra3_q2_cevap.md``):
785 kanıtsız biçimde 745'e EŞİTLENMEZ; iki uç AYNI ρ(T, faz) çözücüsünü
(doymuş sıvı, Q=0) kullanır; sıcaklık verilmeyen çağrıda varsayılan durum
AÇIKÇA yayımlanır; künyede uygulanan sıcaklık, faz, doyma basıncı,
model/sürüm, kaynak ve varsayımın kökeni bulunur.

Bu dosyadaki bekçiler SAYIYI İKİNCİ KEZ YAZMAZ (Doktrin 4 / CLAUDE.md
kural 11): beklenen değer, ürünün okuduğu kapının KENDİSİNDEN çözülür.
Kapı bozulursa bekçi de bozulacağı için ayrıca DURUM TUTARLILIĞI (sayı
ile künyenin aynı sıcaklığı göstermesi) ve ÇAPRAZ UÇ ÖZDEŞLİĞİ ölçülür —
bunların ikisi de kapıdan bağımsızdır.
"""

import contextlib
import io
import math
import os
import tempfile

import pytest


# --- ortak yardımcılar -----------------------------------------------------

def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_USER_DATA_DIR', tempfile.mkdtemp())
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _ozellikler(yanit):
    g = yanit.get_json() or {}
    p = g.get('properties')
    return p if isinstance(p, dict) else g


def _itici(istemci, **yuk):
    yuk.setdefault('propellant_name', 'n2o')
    r = _sessiz(istemci.post, '/api/get-propellant-properties', json=yuk)
    assert r.status_code == 200, r.status_code
    return _ozellikler(r)


def _oksitleyici(istemci, **yuk):
    yuk.setdefault('oxidizer_type', 'n2o')
    r = _sessiz(istemci.post, '/api/oxidizer-properties', json=yuk)
    assert r.status_code == 200, r.status_code
    return _ozellikler(r)


#: Ucun kendi künyesinde beyan ettiği depolama sıcaklığı buradan OKUNUR,
#: testte yazılmaz.
def _depolama_sicakligi(props):
    ss = props.get('storage_state') or {}
    T = ss.get('state_temperature_K')
    assert isinstance(T, (int, float)) and math.isfinite(float(T)), (
        'uç depolama durumunun sıcaklığını yayımlamıyor; sayının HANGİ '
        f'duruma ait olduğu künyeden okunamıyor: {ss!r}')
    return float(T)


class TestOHD3111KategoriEtiketiSayiyiBelirlemez:
    """Aynı uç + aynı akışkan -> TEK yoğunluk (``once.json`` K7)."""

    ETIKETLER = ('hybrid_oxidizer', 'oxidizer', 'hybrid_fuel', None)

    def test_dort_etikette_tek_yogunluk(self, istemci):
        olculen = {}
        for etiket in self.ETIKETLER:
            yuk = {} if etiket is None else {'propellant_type': etiket}
            props = _itici(istemci, **yuk)
            rho = props.get('density')
            assert isinstance(rho, (int, float)) and not isinstance(rho, bool), (
                f'{etiket!r} etiketinde yoğunluk yayımlanmıyor: {rho!r}')
            olculen[str(etiket)] = float(rho)
        ayri = sorted(set(olculen.values()))
        assert len(ayri) == 1, (
            'aynı uç, aynı akışkan (n2o), FARKLI yoğunluk yayımlıyor ve '
            'ayrımı yapan şey sorulan büyüklükle ilgisi olmayan bir kategori '
            f'etiketi: {olculen!r}; ayrışan değerler {ayri!r}')

    def test_etiketler_arasi_bagil_fark_sifir(self, istemci):
        """%5,383'lük ölçülmüş ayrışma (taban) kapandı mı."""
        degerler = []
        for etiket in self.ETIKETLER:
            yuk = {} if etiket is None else {'propellant_type': etiket}
            degerler.append(float(_itici(istemci, **yuk)['density']))
        en_az, en_cok = min(degerler), max(degerler)
        fark = 100.0 * (en_cok - en_az) / en_az
        assert fark == pytest.approx(0.0, abs=1e-12), (
            f'kategori etiketine bağlı yoğunluk ayrışması sürüyor: %{fark:.3f}')


class TestOHD3111SayiKunyesiyleAyniDurumu_Gosterir:
    """Yayımlanan ρ, ucun KENDİ beyan ettiği durumun EOS çözümü mü?"""

    def test_yogunluk_beyan_edilen_sicaklikta_cozulmus(self, istemci):
        from hrma.data.external_data_fetcher import (
            n2o_saturated_liquid_density)
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        T_kunye = _depolama_sicakligi(props)
        beklenen, _kaynak = n2o_saturated_liquid_density(T_kunye)
        assert props['density'] == pytest.approx(beklenen, rel=1e-12), (
            f'uç {T_kunye:.2f} K doymuş sıvı DİYE künyeliyor ama yayımladığı '
            f"sayı {props['density']!r}; aynı EOS o durumda {beklenen!r} "
            'veriyor. Sayı kendi künyesini yalanlıyor.')

    def test_katalogun_kendi_sicakligi_depolama_durumu_DEGIL(self):
        """745,0 ile 293,15 K birbirine karıştırılamaz (tek kaynak)."""
        from hrma.data import propellant_database as pdb
        T_katalog = getattr(pdb, 'N2O_LIQUID_DENSITY_SAT_25C_T_K', None)
        assert isinstance(T_katalog, (int, float)), (
            'katalog yoğunluğunun geçerli olduğu sıcaklık MAKİNE OKUR '
            'biçimde yazılı değil; bilgi yalnız sabitin adında kalırsa '
            'künye onu doğrulayamaz')
        from hrma.data.open_source_propellant_api import OpenSourcePropellantAPI
        depo = OpenSourcePropellantAPI.DEFAULT_STORAGE_STATE['NitrousOxide']
        assert float(depo['T']) != float(T_katalog), (
            'bu bekçinin varlık sebebi bu iki sıcaklığın FARKLI olmasıdır; '
            'eşitlenirlerse kusur gizlenir, ölçüm değil')

    def test_katalog_degeri_depolama_kunyesiyle_yayimlanmiyor(self, istemci):
        """745,0 (298,15 K) bir daha 293,15 K künyesiyle çıkmasın."""
        from hrma.data import propellant_database as pdb
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        T_kunye = _depolama_sicakligi(props)
        if float(T_kunye) == float(pdb.N2O_LIQUID_DENSITY_SAT_25C_T_K):
            pytest.skip('künye sıcaklığı katalog sıcaklığına eşit')
        assert props['density'] != pytest.approx(
            float(pdb.N2O_LIQUID_DENSITY_SAT_25C), rel=1e-9), (
            f'uç {T_kunye:.2f} K künyesiyle kataloğun '
            f'{pdb.N2O_LIQUID_DENSITY_SAT_25C_T_K:.2f} K değerini '
            'yayımlıyor')


class TestOHD3111IkiUcTekCozucu:
    """Aynı durum sorulduğunda iki uç BİT-AYNI sayı yayımlar."""

    def test_ayni_sicaklikta_bit_ayni(self, istemci):
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        T = _depolama_sicakligi(props)
        kardes = _oksitleyici(istemci, temperature=T)
        assert kardes['density'] == props['density'], (
            f'{T:.2f} K doymuş sıvı için iki uç iki sayı yayımlıyor: '
            f"oxidizer-properties {kardes['density']!r} ⟷ "
            f"get-propellant-properties {props['density']!r}")

    def test_farkli_sicaklik_farkli_sayi_HATA_DEGIL(self, istemci):
        """D31 dersi 24 çapası: fark durumdan geliyorsa kusur değildir."""
        a = _oksitleyici(istemci, temperature=293.15)['density']
        b = _oksitleyici(istemci, temperature=298.15)['density']
        assert a > b, (
            'doymuş sıvı yoğunluğu sıcaklıkla azalır; 293,15 K değeri '
            f'298,15 K değerinden büyük olmalı ({a!r} ⟷ {b!r})')


class TestOHD3111KunyeTamligi:
    """Astra q2 kabul paketi: künyede ne bulunmalı."""

    def test_durum_kunyesi_yayimlaniyor(self, istemci):
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        kunye = props.get('density_state')
        assert isinstance(kunye, dict), (
            'yoğunluğun DURUM künyesi yayımlanmıyor: uygulanan sıcaklık, '
            'faz, doyma basıncı, model ve varsayımın kökeni okunamıyor')

    @pytest.mark.parametrize('alan', [
        'temperature_K', 'phase', 'quality', 'saturation_pressure_Pa',
        'model', 'source', 'assumption_origin', 'resolved_at_storage_state'])
    def test_kunye_alani_var(self, istemci, alan):
        kunye = _itici(istemci, propellant_type='hybrid_oxidizer')[
            'density_state']
        assert kunye.get(alan) is not None, (
            f'künyede {alan!r} yok: {sorted(kunye)!r}')

    def test_kunye_faz_ve_kalite_doymus_sivi(self, istemci):
        kunye = _itici(istemci, propellant_type='hybrid_oxidizer')[
            'density_state']
        assert 'liquid' in str(kunye['phase']).lower(), kunye['phase']
        assert float(kunye['quality']) == 0.0, (
            'doymuş sıvı Q=0 demektir; künye bunu söylemeli')

    def test_kunye_model_surumu_adiyla(self, istemci):
        kunye = _itici(istemci, propellant_type='hybrid_oxidizer')[
            'density_state']
        metin = str(kunye['model'])
        assert 'Lemmon' in metin and '2006' in metin, (
            f'künye hangi hâl denklemiyle çözüldüğünü söylemiyor: {metin!r}')

    def test_kunye_sicakligi_beyan_edilen_durumla_ayni(self, istemci):
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        assert float(props['density_state']['temperature_K']) == pytest.approx(
            _depolama_sicakligi(props), rel=0, abs=0)

    def test_doyma_basinci_beyan_edilen_sicaklikta(self, istemci):
        """p_sat künyedeki T'nin doyma basıncı olmalı, rastgele bir sayı değil."""
        from hrma.analysis.tank_blowdown import N2OSaturation
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        kunye = props['density_state']
        beklenen = float(N2OSaturation().psat(float(kunye['temperature_K'])))
        assert float(kunye['saturation_pressure_Pa']) == pytest.approx(
            beklenen, rel=1e-9), (
            f"künyedeki doyma basıncı {kunye['saturation_pressure_Pa']!r}, "
            f'aynı sıcaklığın doyma basıncı {beklenen!r}')

    def test_sicaklik_sorulmadigi_soyleniyor(self, istemci):
        """Astra q2: T'siz sorguda varsayımın KÖKENİ açıkça yayımlanır."""
        koken = _itici(istemci, propellant_type='hybrid_oxidizer')[
            'density_state']['assumption_origin']
        metin = str(koken).lower()
        assert 'no temperature' in metin and 'storage state' in metin, (
            f'varsayımın kökeni okunamıyor: {koken!r}')

    def test_alan_kunyesi_cozucuyu_adiyla_soyluyor(self, istemci):
        """``property_sources['density']`` hangi DURUMDA çözüldüğünü taşır."""
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        kaynak = (props.get('property_sources') or {}).get('density')
        assert kaynak and 'saturated liquid' in str(kaynak), (
            f'yoğunluğun alan künyesi durumu taşımıyor: {kaynak!r}')


class TestOHD3111FailClosed:
    """Çözülemeyen durumda SAYI, DURUMU YANLIŞ künyeyle yayımlanmaz."""

    def test_eos_cozemezse_kunye_depolama_durumunu_IDDIA_ETMEZ(
            self, istemci, monkeypatch):
        import hrma.app as app_modulu
        from hrma.data.external_data_fetcher import OxidizerStateError

        def _cozemez(fluid, temperature=None):
            raise OxidizerStateError('bekçi: EOS kapısı bilerek kapatıldı')

        monkeypatch.setattr(app_modulu, 'oxidizer_reference_density', _cozemez)
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        kunye = props.get('density_state')
        if kunye is None:
            pytest.fail(
                'kapı çözemedi ama uç hiçbir durum künyesi yayımlamadı; '
                'okuyan sayının hangi duruma ait olduğunu göremez')
        assert kunye.get('resolved_at_storage_state') is False, (
            'EOS kapısı çözemediği hâlde künye depolama durumunda '
            f'çözüldüğünü iddia ediyor: {kunye!r}')
        assert 'NOT applied' in str(kunye.get('note', '')), (
            f'sınır açıkça bildirilmiyor: {kunye!r}')

    def test_eos_cozemezse_sayi_UYDURULMAZ(self, istemci, monkeypatch):
        """Fail-closed, katalog sayısı korunur; yerine tahmin konmaz."""
        import hrma.app as app_modulu
        from hrma.data import propellant_database as pdb
        from hrma.data.external_data_fetcher import OxidizerStateError

        def _cozemez(fluid, temperature=None):
            raise OxidizerStateError('bekçi: EOS kapısı bilerek kapatıldı')

        monkeypatch.setattr(app_modulu, 'oxidizer_reference_density', _cozemez)
        props = _itici(istemci, propellant_type='hybrid_oxidizer')
        assert props['density'] == pytest.approx(
            float(pdb.N2O_LIQUID_DENSITY_SAT_25C), rel=1e-9), (
            'EOS çözülemediğinde yayımlanan sayı katalog değeri olmalı; '
            f"uydurma görünüyor: {props['density']!r}")
        assert float(props['density_state']['temperature_K']) == pytest.approx(
            float(pdb.N2O_LIQUID_DENSITY_SAT_25C_T_K), rel=0, abs=0), (
            'künye, yayımlanan sayının KENDİ referans sıcaklığını söylemeli')


class TestOHD3111DarKapsam:
    """Onarım yalnız denetlenmiş kapısı olan akışkanı değiştirir."""

    def test_lox_davranisi_bit_ayni(self, istemci):
        r = _sessiz(istemci.post, '/api/get-propellant-properties',
                    json={'propellant_type': 'hybrid_oxidizer',
                          'propellant_name': 'lox'})
        props = _ozellikler(r)
        assert props.get('density_state') is None, (
            'LOX için denetlenmiş ρ(T) kapısı yok; onarım ona dokunmamalı')
        assert props['density'] == 1141, props['density']
