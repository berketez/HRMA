"""ÖH Dalga-30 · kulvar katı · aşama 1 — OH-D29-05 ve OH-Z3-04 bekçileri.

İKİ KALEM:

OH-D29-05 (OH-D28-05 zincirinin İLK ayağı) — EROZYON ÜSSÜ EKSTRAPOLASYONU
  Kusur (ölçüldü, docs/scofield/raw/OH/D30/kati/a1/once.json · K1):
  D28/OH-D27-15 erozyon yasasının basınç üssünü künyesine bağlamış ve
  "bu motor künyenin ÖLÇTÜĞÜ aralığın dışında mı" sorusunu
  ``exponent_extrapolated`` alanıyla YAYIMLAMIŞTI. Alan yalnız VERİydi:
  40 bar sınıfı bir katı motorda (apcp/bates/grafit) alan ``True``
  dönüyordu — üssün künyesi 69-450 bar ölçmüş (Thakre & Yang 2008) —
  ama yayımlanan uyarı kodları arasında karşılığı YOKTU (0 geçiş), ve
  erozyon bloğunun hiçbir panel tüketicisi olmadığı için (D29 arayuz-panel
  a1 ölçümü) kullanıcıya ulaşan tek kanal ``warnings`` dizisiydi. Yani
  uygulamanın KENDİ BİLDİĞİ bir ekstrapolasyon kullanıcı yüzünde hiçbir
  yerde görünmüyordu.

  Onarım: ``warn.solid.erosion_exponent_extrapolated`` kodu yapılı kayıt
  olarak yayımlanır (kod + params + severity) ve İngilizce yedek metnini
  ``fallback`` alanında taşır. i18n anahtarı (TR/EN sözlük) ve panel satırı
  BU dalgada YAZILMAZ — zincirin sonraki iki ayağıdır (D31: arayuz-i18n →
  arayuz-panel). Kullanıcı o ayaklar gelene kadar ``fallback`` sayesinde
  İngilizce metni görür (``displaySolidWarnings`` ``w.fallback || w.code``).

OH-Z3-04 (D29 devri, kalan ayak) — ``_warning_identity`` TEK KAYNAK
  Kusur (ölçüldü, once.json · K2): aynı gövde İKİ motor dosyasında
  yazılıydı (``tanim_toplam = 2``, ``iki_motor_ayni_nesne = False``) ve iki
  docstring "sözleşme öbürüyle BİREBİR aynıdır" diye birbirine YORUMLA
  bağlıydı. Defterin andığı üçüncü kopya (``templates/solid.html``) D29'da
  ölçülüp çürütülmüştü — şablondaki işlev ``warningIdentity`` adındadır ve
  JS aynasıdır, Python kopyası değildir.

  Onarım: ``hrma/engines/warning_records.py`` tek tanım noktasıdır; iki
  motor da onu ithal eder.
"""
import ast
import contextlib
import io
import pathlib
import re

import pytest

from hrma.analysis import transient_ballistics as tb
from hrma.engines import hybrid_rocket_engine as hib
from hrma.engines import solid_rocket_engine as kati
from hrma.engines import warning_records
from hrma.engines.solid_rocket_engine import SolidRocketEngine

KOK = pathlib.Path(kati.__file__).resolve().parents[2]
KOD = 'warn.solid.erosion_exponent_extrapolated'


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(pc_bar, **ov):
    return _sessiz(
        SolidRocketEngine, propellant_type='apcp', grain_type='bates',
        chamber_pressure=pc_bar, chamber_diameter=100.0, grain_length=500.0,
        core_diameter=30.0, overrides=ov)


def _uyarilar(motor):
    return [w for w in (_sessiz(motor.calculate_performance).get('warnings')
                        or []) if isinstance(w, dict)]


def _kayit(motor, kod=KOD):
    return [w for w in _uyarilar(motor) if w.get('code') == kod]


# --------------------------------------------------- OH-D29-05 · EKSTRAPOLASYON
class TestOHD2905EkstrapolasyonUyarisi:
    """Yayımlanan erozyon sayısının ekstrapolasyon olduğu SÖYLENİR."""

    def test_bant_disi_motorda_uyari_yayimlanir(self):
        """40 bar sınıfı motor: üssün künyesi 69-450 bar ⇒ dışarıda."""
        m = _motor(40.0)
        est = _sessiz(m._nozzle_erosion_estimate)
        assert est['exponent_extrapolated'] is True, (
            'ön koşul düştü: 40 bar artık bant dışı değil')
        kayitlar = _kayit(m)
        assert len(kayitlar) == 1, (
            'bant dışı motorda ekstrapolasyon uyarısı yayımlanmadı '
            '(yayımlananlar: %s)' % [w.get('code') for w in _uyarilar(m)])

    def test_bant_ici_motorda_uyari_YOK(self):
        """İLİŞKİ bekçisi: uyarı her koşuda değil, yalnız bant DIŞINDA çıkar.

        Sayı mandalı değil karşıtlık: 100 bar künyenin ölçtüğü aralığın
        (69-450 bar) İÇİNDEdir; orada uyarı basmak kullanıcıyı kör eder.
        """
        m = _motor(100.0)
        est = _sessiz(m._nozzle_erosion_estimate)
        assert est['exponent_extrapolated'] is False, (
            'ön koşul düştü: 100 bar artık bant içi değil')
        assert _kayit(m) == []

    def test_karar_yeniden_yazilmiyor_modelden_geliyor(self):
        """Ölçüt TEK tanım noktasındadır (Doktrin 4).

        Motor kendi basınç karşılaştırmasını yapmaz: bandı ve hükmü
        ``ThroatErosionModel.exponent_extrapolated`` verir. Bunu bandı
        MODELDEN oynatarak ölçüyoruz — motor kodunda ikinci bir eşik
        yazılıysa uyarı bandın yeni yerini izlemez.
        """
        m = _motor(40.0)
        assert len(_kayit(m)) == 1
        eski = tb.THROAT_EROSION_EXPONENT_VALID_PC_BAR
        try:
            # 40 bar'ı KAPSAYAN bir aralık: uyarı susmalı.
            tb.THROAT_EROSION_EXPONENT_VALID_PC_BAR = (10.0, 450.0)
            m2 = _motor(40.0)
            assert _sessiz(m2._nozzle_erosion_estimate)[
                'exponent_extrapolated'] is False
            assert _kayit(m2) == [], (
                'uyarı modelin bandını izlemiyor — motorda ikinci bir eşik '
                'yazılı olabilir')
        finally:
            tb.THROAT_EROSION_EXPONENT_VALID_PC_BAR = eski
        assert len(_kayit(_motor(40.0))) == 1, 'geri yazım tutmadı'

    def test_kaydin_parametreleri_yayimlanan_blokla_ayni(self):
        """Uyarıdaki sayılar, aynı yanıttaki erozyon bloğunun sayılarıdır."""
        m = _motor(40.0)
        est = _sessiz(m._nozzle_erosion_estimate)
        p = _kayit(m)[0]['params']
        assert p['chamber_pressure_bar'] == pytest.approx(
            float(est['chamber_pressure_bar']), rel=1e-9)
        assert (p['valid_low_bar'], p['valid_high_bar']) == pytest.approx(
            tuple(est['exponent_valid_pc_bar']), rel=1e-9)
        assert p['exponent'] == pytest.approx(float(est['exponent']),
                                              rel=1e-9)
        assert p['material'] == str(est['material'])

    def test_ciddiyet_ve_yapili_kayit_sozlesmesi(self):
        w = _kayit(_motor(40.0))[0]
        assert set(w) >= {'code', 'params', 'severity', 'fallback'}
        assert w['severity'] == 'warning'
        assert isinstance(w['params'], dict)

    def test_ingilizce_yedek_metin_kendi_parametreleriyle_kuruluyor(self):
        """``fallback`` yalnız KENDİ ilan ettiği alanları kullanır.

        i18n anahtarı D31'de eklenecek (OH-D28-05 zinciri); o güne kadar
        kullanıcıya görünen metin budur. Yetim yer tutucu kalırsa ekranda
        ham ``{alan}`` görünür — sahte/yarım metin yasak (Doktrin 6).
        """
        w = _kayit(_motor(40.0))[0]
        metin = w['fallback']
        assert metin and not metin.startswith('warn.')
        yer_tutucular = set(re.findall(r'\{(\w+)\}', metin))
        assert yer_tutucular, 'yedek metin hiçbir sayı taşımıyor'
        assert yer_tutucular <= set(w['params']), (
            'yedek metinde karşılığı olmayan yer tutucu: %s'
            % sorted(yer_tutucular - set(w['params'])))
        kurulan = metin
        for k, v in w['params'].items():
            kurulan = kurulan.replace('{%s}' % k, str(v))
        assert '{' not in kurulan and '}' not in kurulan

    def test_uyari_atifsiz_usle_YAYIMLANMAZ(self):
        """Üç değerli alan: atıf yoksa aralık da yoktur ⇒ HÜKÜM VERİLMEZ.

        Sessiz varsayım yasağının karşı ucu: aralık bilinmiyorken
        'ekstrapolasyon değil' demek de 'ekstrapolasyondur' demek de
        kazanılmamış bir hükümdür.
        """
        model = tb.ThroatErosionModel(0.2, exponent=0.65)
        assert model.exponent_extrapolated(40.0) is None
        assert model.exponent_attributed is False


# ------------------------------------------------------- OH-Z3-04 · TEK KAYNAK
class TestOHZ304WarningIdentityTekKaynak:
    """``_warning_identity`` tek tanım noktasındadır."""

    def _tanimlar(self):
        bulunan = {}
        for p in sorted((KOK / 'hrma').rglob('*.py')):
            agac = ast.parse(p.read_text(encoding='utf-8'))
            for n in ast.walk(agac):
                if (isinstance(n, ast.FunctionDef)
                        and n.name.lstrip('_') == 'warning_identity'):
                    bulunan.setdefault(str(p.relative_to(KOK)), []).append(
                        n.name)
        return bulunan

    def test_urun_agacinda_TEK_tanim_var(self):
        """AST ölçümü (metin taraması değil): kopya sayısı 2 ⇒ 1."""
        bulunan = self._tanimlar()
        assert bulunan == {
            'hrma/engines/warning_records.py': ['warning_identity']}, (
            'kimlik işlevi birden fazla yerde tanımlı: %s' % bulunan)

    def test_iki_motor_AYNI_nesneyi_paylasiyor(self):
        """İLİŞKİ bekçisi: eşitlik yorumla değil kimlikle korunur."""
        assert kati._warning_identity is warning_records.warning_identity
        assert hib._warning_identity is warning_records.warning_identity
        assert kati._warning_identity is hib._warning_identity

    def test_anahtar_sozlesmesi_korundu(self):
        f = warning_records.warning_identity
        assert f({'code': 'warn.x', 'severity': 'critical',
                  'params': {'b': 2, 'a': 1}}) == \
            "warn.x|critical|[('a', '1'), ('b', '2')]"
        # Parametre SIRASI kimliği değiştirmez.
        assert f({'code': 'c', 'severity': 's', 'params': {'a': 1, 'b': 2}}) \
            == f({'code': 'c', 'severity': 's', 'params': {'b': 2, 'a': 1}})
        # Düz metin kanalı.
        assert f('CRITICAL: x') == 'str:CRITICAL: x'
        # params sözlük değilse repr'i imzalanır.
        assert f({'code': 'c', 'severity': 's', 'params': None}) == \
            'c|s|None'

    def test_metin_alanlari_kimlige_GIRMEZ(self):
        """``fallback`` taşıyan kayıt, taşımayanla AYNI hükümdür.

        OH-D29-05 kaydı ``fallback`` alanı taşıyor; kimlik bu alanı
        okusaydı aynı hüküm iki kanaldan gelince kullanıcıya İKİ KEZ
        basılırdı (teslim kanalı ``_critical_thermal_verdicts``).
        """
        f = warning_records.warning_identity
        yalin = {'code': 'c', 'severity': 'critical', 'params': {'a': 1}}
        metinli = dict(yalin, fallback='English text')
        assert f(yalin) == f(metinli)

    def test_tek_kaynak_modulu_motor_ithal_ETMEZ(self):
        """Döngüsel bağımlılık kapısı: modül yalnız yaprak olmalı."""
        kaynak = (KOK / 'hrma' / 'engines' / 'warning_records.py').read_text(
            encoding='utf-8')
        agac = ast.parse(kaynak)
        ithal = [n for n in ast.walk(agac)
                 if isinstance(n, (ast.Import, ast.ImportFrom))]
        assert ithal == [], (
            'tek kaynak modülü bir şey ithal ediyor: döngü riski')

    def test_sablon_aynasi_sozlesmeyi_koruyor(self):
        """JS aynası (tek kaynak DEĞİL) parametre SIRASINDAN bağımsız mı?

        Depoda tek JS aynası ``templates/solid.html``
        ``displaySolidWarnings``tadır. Dizgesi Python'unkiyle aynı olmak
        zorunda değildir; sözleşmesi aynı olmak zorundadır — anahtarlar
        SIRALANIR ve metin alanları kimliğe girmez.
        """
        html = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(
            encoding='utf-8')
        i = html.index('function warningIdentity(w)')
        govde = html[i:i + 700]
        assert 'Object.keys(p).sort()' in govde, (
            'JS aynası parametreleri sıralamıyor — sıra kimliği değiştirir')
        for metin_alani in ('fallback', 'message', 'text'):
            assert ('w.' + metin_alani) not in govde, (
                'JS aynası %r alanını kimliğe katıyor' % metin_alani)
