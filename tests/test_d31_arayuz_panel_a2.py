# -*- coding: utf-8 -*-
"""ÖH D31 · arayuz-panel · aşama 2/3 — bekçiler (ÖK-21 form katmanı).

Her sınıf, ``docs/scofield/raw/OH/D31/arayuz-panel/a2/once.json`` ile
ÖLÇÜLMÜŞ bir kusuru gördüğü ters-mutasyonla kanıtlanmıştır
(``mutasyon.py`` / ``mutasyon.json``). Sayı mandalı değil, KÜME ölçüsü.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
TPL = KOK / 'hrma' / 'templates'
JS = KOK / 'hrma' / 'static' / 'js'

SAYI = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
RE_SCRIPT = re.compile(r'<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>',
                       re.S | re.I)


def _oku(p):
    return p.read_text(encoding='utf-8')


def _satirici(metin):
    return [m.group(1) for m in RE_SCRIPT.finditer(metin)]


def _govde(metin, ad):
    """``function ad(`` gövdesini parantez sayımıyla çıkar."""
    for blok in _satirici(metin):
        i = blok.find('function %s(' % ad)
        if i < 0:
            continue
        j = blok.find('{', i)
        derinlik, k = 0, j
        while k < len(blok):
            if blok[k] == '{':
                derinlik += 1
            elif blok[k] == '}':
                derinlik -= 1
                if derinlik == 0:
                    return blok[j:k + 1]
            k += 1
    return ''


# ====================================================================
# P12bS1-06 / OH-D29-02 — süpürme aralığı sessizce ikame edilmiyor
# ====================================================================
#: D30 a1'in imi YALNIZ nesne-sabiti biçimini (``param_start:``) görüyordu.
#: Ters-mutasyon bu kör noktayı ölçtü (``mutasyon.json`` P12bS1-06-D30im ilk
#: koşumu): ikame ``data.param_start = isNaN(...) ? 1.5 : ...`` biçiminde
#: geri konursa o im YEŞİL kalıyor. Buradaki desen İKİ biçimi de yakalar.
_IKAME = re.compile(
    r'(?:data\.)?(param_(?:start|end|steps))\s*[:=]\s*isNaN\s*\([^)]*\)'
    r'\s*\?\s*(%s)\s*:' % SAYI)


class TestSupurmeSessizIkameSokuldu:
    """ÖLÇÜLDÜ (``once.json`` M4): ``1.5`` / ``4.0`` / ``10``.

    İkame kalktığı için ucun ``sweep_interval_not_supplied`` (422) kapısı
    ürün yolundan erişilebilir hâle geldi. D30 a1'in ``xfail(strict)``
    borç imi bu aşamada ÖDENDİ ve im KALDIRILDI.
    """

    def test_ikame_yok(self):
        govde = _govde(_oku(TPL / 'advanced.html'), 'runParametricAnalysis')
        assert govde, 'advanced.html::runParametricAnalysis bulunamadı'
        ikame = sorted({m.group(1) for m in _IKAME.finditer(govde)})
        assert ikame == [], (
            'süpürme aralığı istemcide sessizce ikame ediliyor: %s' % ikame)

    def test_anahtar_yoklukla_gonderiliyor(self):
        """Boş alan için anahtar KONMAZ (null de konmaz)."""
        govde = _govde(_oku(TPL / 'advanced.html'), 'runParametricAnalysis')
        for alan in ('param_start', 'param_end', 'param_steps'):
            assert re.search(r'if \(!isNaN\([^)]*\)\) \{ data\.%s =' % alan,
                             govde), (
                '%s koşullu atamayla gönderilmiyor' % alan)

    def test_sunucu_kapisi_yerinde(self):
        """Borcun karşı ayağı: uç kapısı sökülmemeli."""
        app_py = _oku(KOK / 'hrma' / 'app.py')
        assert 'sweep_interval_not_supplied' in app_py


# ====================================================================
# OH-D27-10 / OH-D26-20 — açık `null` yerine anahtar yokluğu
# ====================================================================
class TestNumByIdAnahtarDusurucusu:
    """ÖLÇÜLDÜ (``once.json`` M5_numById): 9 çağrı, boş alanda açık null."""

    #: Uç tarafı çıplak ``data.get(<ad>)`` okuyan alanlar (ölçüldü 7/7 +
    #: oxidizer_density). Anahtar düşünce sunucu davranışı BİT-AYNI kalır.
    ALANLAR = ('vehicle_mass_dry', 'vehicle_reference_area_m2',
               'drag_coefficient', 'launch_angle', 'launch_altitude',
               'wind_speed', 'wind_direction', 'oxidizer_density')

    def test_dusurucu_var(self):
        adv = _oku(TPL / 'advanced.html')
        assert 'NUMBYID_ALANLARI' in adv, 'anahtar düşürücü yok'
        assert re.search(r"if \(data\[k\] === null\) \{ delete data\[k\]; \}",
                         adv), 'null anahtar silinmiyor'

    def test_kume_tam(self):
        adv = _oku(TPL / 'advanced.html')
        m = re.search(r'const NUMBYID_ALANLARI = \[(.*?)\];', adv, re.S)
        assert m, 'NUMBYID_ALANLARI listesi bulunamadı'
        liste = set(re.findall(r"'([\w]+)'", m.group(1)))
        assert set(self.ALANLAR) <= liste, (
            'düşürücü kümesi eksik: %s' % sorted(set(self.ALANLAR) - liste))

    def test_ucun_yedeksiz_okumasi_korunuyor(self):
        """Kümedeki alanlar uçta yedeksiz okunmalı — yoksa düşürme sessiz
        bir sunucu varsayılanına düşerdi (doktrin §3)."""
        app_py = _oku(KOK / 'hrma' / 'app.py')
        for ad in self.ALANLAR:
            yedekli = re.search(r"data\.get\(\s*'%s'\s*,\s*[^)]" % ad, app_py)
            assert not yedekli, (
                "%s uçta artık yedekle okunuyor; anahtar düşürmek onu "
                'sessiz bir varsayılana çevirir' % ad)


# ====================================================================
# OH-D26-20 — flow_panel: ön-dolu varsayılan + beyan kanalı
# ====================================================================
class TestFlowPanelFormSokumu:
    """ÖLÇÜLDÜ (``once.json`` M5_flow): ``zorunlu_ama_on_dolu`` = 6/6."""

    def _alan_varsayilanlari(self):
        flow = _oku(JS / 'panels' / 'flow_panel.js')
        return {a: v for a, v in re.findall(
            r"\[\s*'([\w]+)'\s*,\s*'[^']*'\s*,\s*(%s|'')\s*," % SAYI, flow)}

    def test_zorunlu_alanlar_on_dolu_degil(self):
        app_py = _oku(KOK / 'hrma' / 'app.py')
        m = re.search(r'FLOW_REQUIRED_FIELDS\s*=\s*\((.*?)\)', app_py, re.S)
        zorunlu = set(re.findall(r"'(\w+)'", m.group(1)))
        var = self._alan_varsayilanlari()
        dolu = sorted(a for a in zorunlu if a in var and var[a] != "''")
        assert dolu == [], (
            'ucun ZORUNLU alanları formda ön-dolu: %s — kullanıcı hiçbir şey '
            'girmese bile uca motor tanımı gidiyor, ucun 422 / '
            'defaults_applied dalı üründen erişilemez' % dolu)

    def test_beyan_kanali_render_yolunda(self):
        """``defaults_applied`` ekranda: söküm ancak beyanla birlikte
        doktrine uyar (doktrin §3 (b))."""
        flow = _oku(JS / 'panels' / 'flow_panel.js')
        assert 'function defaultsBlock(' in flow
        assert '+ defaultsBlock(data.defaults_applied)' in flow, (
            'defaults_applice künyesi ana render yolundan çağrılmıyor')

    def test_beyan_metni_sunucudan(self):
        """Panel ne sayı ne gerekçe üretir — künye alanları basılır."""
        flow = _oku(JS / 'panels' / 'flow_panel.js')
        i = flow.find('function defaultsBlock(')
        govde = flow[i:flow.find('function honestyBlock(')]
        for alan in ('k.field', 'k.value', 'k.unit', 'k.message'):
            assert alan in govde, '%s künye alanı basılmıyor' % alan


class TestFlowPanelCanliBeyan:
    """Ürün koşumu: soğuk panelin gövdesi KAPIYI, dolu gövde BEYANI açar.

    ÖH D33-2 / app-api-uc a1 (OH-D32-13) — MANDAL ÇEVRİLDİ. Sınıfın eski
    tek bekçisi ``test_soguk_panel_dokuz_beyan`` idi ve soğuk panelin
    (motorun hiçbir alanını taşımayan gövdenin) **HTTP 200 + dokuz künye**
    almasını şart koşuyordu. O gün doğruydu: kapı ``if not data``
    hâlindeydi ve panel her istekte ``fidelity`` gönderdiği için 422 dalı
    ürün yolundan erişilemiyordu; künye elde kalan tek dürüstlük
    kanalıydı. Ama künye, uydurulan altı sayıyı doğru yapmıyordu
    (Doktrin 1: beyan çözüm değildir) — bekçi bu hâliyle kusuru
    KİLİTLİYORDU.

    Kapı bu dalgada alan-alan indi (ölçüm:
    ``D33-2/app-api-uc/a1/sonra_ohd3114.json`` K1 — zorunlu alanı eksik
    18/18 istek 422). İDDİA ZAYIFLATILMADI, İKİYE BÖLÜNDÜ: soğuk gövde
    artık altı alanı ADIYLA ister; beyan kanalı ise motoru TAM tarif eden
    gövdede, düşebilen üç YÖNTEM seçimi üstünde aynen sınanır.
    """

    #: Panelin soğuk hâlde gönderdiği gövde: motorun hiçbir alanı yok.
    SOGUK = {'fidelity': 'engineering', 'kinetic_fidelity': 'engineering',
             'fuel_type': 'htpb', 'oxidizer_type': 'N2O'}

    @staticmethod
    def _kos(yuk):
        # Alt süreçte: paket yüzeyi başka testin içe aktarma sırasına
        # bağlı kalmasın (D30 dersi 20).
        # Zorunlu alan listesi de ÜRÜNDEN okunur (tek kaynak): bekçi
        # kendi kopyasını tutarsa uçtaki değişikliği göremez.
        betik = (
            "import sys, json; sys.path.insert(0,'.')\n"
            'from hrma.app import app, FLOW_REQUIRED_FIELDS\n'
            "c=app.test_client()\n"
            "r=c.post('/api/flow-analysis', json=json.loads(%r))\n"
            "j=r.get_json() or {}\n"
            "print(r.status_code, len(j.get('defaults_applied') or []), "
            "','.join(sorted(j.get('missing_fields') or [])) or '-', "
            "','.join(sorted(FLOW_REQUIRED_FIELDS)))\n"
            % json.dumps(yuk))
        r = subprocess.run([sys.executable, '-c', betik], cwd=str(KOK),
                           capture_output=True, text=True, timeout=300,
                           env={'PATH': '/usr/bin:/bin', 'HRMA_HEADLESS': '1',
                                'PYTHONDONTWRITEBYTECODE': '1',
                                'VECLIB_MAXIMUM_THREADS': '3',
                                'OMP_NUM_THREADS': '3'})
        assert r.returncode == 0, r.stderr[-1500:]
        parcalar = r.stdout.strip().split('\n')[-1].split(' ')
        assert len(parcalar) == 4, r.stdout[-400:]
        eksik = [] if parcalar[2] == '-' else parcalar[2].split(',')
        return parcalar[0], int(parcalar[1]), eksik, parcalar[3].split(',')

    def test_soguk_panel_ALTI_ALANI_ADIYLA_ister(self):
        """Motoru tarif etmeyen gövde çözülmez; künye de basılmaz."""
        durum, beyan_sayisi, eksik, zorunlu = self._kos(dict(self.SOGUK))
        assert durum == '422', (
            'soğuk panel gövdesi hâlâ çözülüyor (HTTP %s) — kapı sökülmüş '
            'olabilir' % durum)
        assert len(zorunlu) == 6, zorunlu
        assert sorted(eksik) == sorted(zorunlu), (eksik, zorunlu)
        assert beyan_sayisi == 0, (
            'reddedilen istekte %d künye basıldı — iki kanal birbirini '
            'yutuyor' % beyan_sayisi)

    def test_motor_tarif_edilince_BEYAN_KANALI_acik(self):
        """Kapı beyanı öldürmedi: düşen yöntem seçimleri adıyla beyan edilir.

        Beklenen sayı ÜÇ (``n_stations``, ``separation_factor``,
        ``wall_temperature``) — eski dokuzun kalanı zorunlu altı alandı ve
        onlar artık DÜŞMÜYOR, isteniyor. Form ön-dolu hâline dönerse ya da
        beyan kanalı susarsa bu sayı oynar.
        """
        yuk = dict(self.SOGUK)
        yuk.update({'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
                    'gamma': 1.2, 'molecular_weight': 24.0,
                    'throat_diameter': 0.03, 'ambient_pressure': 101325.0,
                    'expansion_ratio': 8.0})
        durum, beyan_sayisi, eksik, _zorunlu = self._kos(yuk)
        assert durum == '200', eksik
        assert beyan_sayisi == 3, (
            'motor tam tarif edildi; beklenen 3 yöntem beyanı, gelen %d'
            % beyan_sayisi)


# ====================================================================
# OH-D17-13 — oxidizer_density statik varsayılanı
# ====================================================================
class TestOksitleyiciYogunlugu:
    """ÖLÇÜLDÜ (``once.json`` M7): ``value="1004"``, placeholder yok."""

    def test_statik_sayi_yok(self):
        adv = _oku(TPL / 'advanced.html')
        m = re.search(r'<input[^>]*id="oxidizer_density"[^>]*>', adv)
        assert m, 'oxidizer_density alanı bulunamadı'
        etiket = m.group(0)
        assert not re.search(r'\bvalue\s*=\s*"%s"' % SAYI, etiket), (
            'alan hâlâ statik bir sayıyla doğuyor: %s' % etiket)

    def test_kaynak_yazili(self):
        adv = _oku(TPL / 'advanced.html')
        m = re.search(r'<input[^>]*id="oxidizer_density"[^>]*>', adv)
        assert 'placeholder=' in m.group(0), (
            'sayı söküldü ama sayının NEREDEN geleceği yazılmadı')

    def test_uc_kendi_kaynakli_degerini_kullaniyor(self):
        """Sökümün karşı ayağı (doktrin §3 (b))."""
        app_py = _oku(KOK / 'hrma' / 'app.py')
        assert "oxidizer_density=data.get('oxidizer_density')" in app_py, (
            'uç tarafı yedekli okumaya dönmüş; söküm kullanıcıyı beyansız '
            'bırakır')


# ====================================================================
# OH-D26-11 — ölü durum düğümü
# ====================================================================
class TestOluDurumDugumu:
    """ÖLÇÜLDÜ (``once.json`` M8): ``dom_var`` = True, yazan JS = 0."""

    def test_dugum_sokuldu(self):
        adv = _oku(TPL / 'advanced.html')
        assert 'id="openrocketStatus"' not in adv, (
            'hiçbir JS yazmadığı hâlde duran boş durum kutusu geri gelmiş')

    def test_canli_kardesler_duruyor(self):
        """Söküm bir KAPI düşürmemeli (D28 a3 dersi)."""
        adv = _oku(TPL / 'advanced.html')
        for ad in ('reportStatus', 'packageStatus'):
            assert 'id="%s"' % ad in adv, '%s düğümü kayboldu' % ad
            assert adv.count(ad) >= 2, (
                '%s artık yazılmıyor — canlı kardeş öldü' % ad)


# ====================================================================
# P12bS1-01 — ÖK-21 küme ölçüsü (gerileme kilidi)
# ====================================================================
class TestOK21KumeGerilemesi:
    """advanced.html'in çift-katman kümesi BÜYÜMEMELİ.

    Sayı mandalı değil, KÜME ölçüsü: bu aşamada sökülen alanlar kümeden
    çıktı; yeni bir alan çift katmanla eklenirse bekçi kırmızıya döner.
    """

    #: ``once.json`` M1 · advanced.html · ``cift_katman`` (49 alan).
    TABAN_SAYI = 49

    def _cift_katman(self, ad):
        t = _oku(TPL / ad)
        vals = {}
        for m in re.finditer(r'<input\b[^>]*>', t):
            e = m.group(0)
            i = re.search(r'\bid\s*=\s*"([^"]+)"', e)
            v = re.search(r'\bvalue\s*=\s*"(%s)"' % SAYI, e)
            if i and v:
                vals[i.group(1)] = v.group(1)
        ic = ''.join(_satirici(t))
        orlar = set()
        for m in re.finditer(r'\|\|\s*(%s)\b' % SAYI, ic):
            onc = ic[max(0, m.start() - 160):m.start()]
            gid = re.findall(r"getElementById\(\s*['\"]([\w-]+)['\"]", onc)
            if gid:
                orlar.add(gid[-1])
        return set(vals) & orlar

    def test_kume_buyumedi(self):
        simdi = self._cift_katman('advanced.html')
        assert len(simdi) <= self.TABAN_SAYI, (
            'advanced.html çift-katman kümesi büyüdü: %d > %d — yeni alan '
            'hem value="X" hem `|| X` ile eklenmiş (ÖK-21)'
            % (len(simdi), self.TABAN_SAYI))

    def test_sokulen_alan_geri_gelmedi(self):
        simdi = self._cift_katman('advanced.html')
        assert 'oxidizer_density' not in simdi, (
            'oxidizer_density çift katmana geri döndü')
