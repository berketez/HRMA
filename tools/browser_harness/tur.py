"""Playwright etkileşimi — YALNIZ ölçer, hüküm vermez.

Bu modül sayfayı açar, hesabı tetikler, 3B sahneyi kurdurur, yanmayı
başlatır ve ham sayıları toplar. Neyin "geçtiği" burada değil
``denetimler.py``de kararlaştırılır; böylece eşikler tarayıcı açmadan
sınanabilir.

``playwright`` içe aktarımı BİLEREK fonksiyon içindedir: ``tests`` bu
modülü Playwright kurulu olmayan bir ortamda da içe aktarıp saf
yardımcılarını (veri URL çözümü, JS metinleri) sınayabilsin diye.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, List, Optional, Sequence

from tools.browser_harness import denetimler, esikler
from tools.browser_harness.sayfalar import Sayfa

# ---------------------------------------------------------------------------
# Sayfa içinde çalışan ölçüm betikleri
# ---------------------------------------------------------------------------

#: 3B sahnenin durumu. Egzozun çizilip çizilmediği sorusunun DOĞRUDAN
#: kaynağı: ``drawRange.count`` (motor_viz3d.js:1857). Ölçüm hiçbir şey
#: değiştirmez, yalnız okur.
JS_VIZ_DURUMU = """
() => {
  const M = window.MotorViz3D;
  if (!M || typeof M.get !== 'function') return { erisim: 'modul_yok' };
  let destek = null;
  try { destek = !!(M.isSupported && M.isSupported()); } catch (e) { destek = null; }
  const v = M.get();
  if (!v) return { erisim: 'sahne_kurulmadi', webgl_destegi: destek };
  const p = v._plume;
  const g = p && p.geometry;
  const dr = (g && g.drawRange) ? g.drawRange.count : null;
  const st = v.state || {};
  const info = v._plumeInfo || null;
  const say = (x) => (typeof x === 'number' && isFinite(x)) ? x : null;
  return {
    erisim: 'motorviz3d',
    webgl_destegi: destek,
    plume_nesnesi_var: !!p,
    plume_gorunur: !!(p && p.visible),
    cizim_araligi: say(dr),
    partikul_tavani: say(v._plumeN),
    plume_bilgisi_var: !!info,
    genisleme_durumu: info ? (info.expansionState || null) : null,
    cikis_hizi_ms: info ? say(info.exitVelocity) : null,
    elmas_araligi_mm: info ? say(info.diamondSpacing) : null,
    nozul_cikisi_var: !!(v.dims && v.dims.nozzleExit),
    oynatiliyor: !!st.playing,
    plume_acik: !!st.plume,
    sanal_zaman: say(st.time),
    yanma_suresi: (v.dims ? say(v.dims.burnTime) : null)
  };
}
"""

#: Tuval içeriğini PNG veri-URL'i olarak alır. ``MotorViz3D.snapshot()``
#: önce sahneyi çizip sonra okur (motor_viz3d.js:2314), bu yüzden
#: ``preserveDrawingBuffer`` olmadan da dolu bir kare verir. Sahne yoksa en
#: büyük tuvale düşülür — 2B tuvaller ``toDataURL`` ile zaten okunur.
JS_TUVAL = """
() => {
  const M = window.MotorViz3D;
  const v = (M && typeof M.get === 'function') ? M.get() : null;
  if (v && typeof v.snapshot === 'function') {
    try {
      const u = v.snapshot();
      if (u) return { kaynak: 'MotorViz3D.snapshot()', veri_url: u };
    } catch (e) { return { kaynak: 'MotorViz3D.snapshot()', hata: String(e) }; }
  }
  const adaylar = Array.from(document.querySelectorAll('canvas'))
    .filter(c => c.width >= __MIN_KENAR__ && c.height >= __MIN_KENAR__)
    .sort((a, b) => (b.width * b.height) - (a.width * a.height));
  if (!adaylar.length) return { kaynak: 'yok', hata: 'uygun boyutta tuval yok' };
  const c = adaylar[0];
  try {
    return { kaynak: 'canvas.toDataURL()', veri_url: c.toDataURL('image/png'),
             tuval_genislik: c.width, tuval_yukseklik: c.height };
  } catch (e) {
    return { kaynak: 'canvas.toDataURL()', hata: String(e) };
  }
}
""".replace('__MIN_KENAR__', str(esikler.TUVAL_MIN_KENAR_PX))

#: Görünen metin. Betik gövdeleri innerText'e girmez; aranan şey KULLANICININ
#: gördüğü sızıntıdır.
JS_SAYFA_METNI = "() => (document.body ? document.body.innerText : '')"

#: Yanmayı arayüz düğmesi olmadan başlatma yolu. ``play()`` yanma bitmişse
#: zamanı sıfırlar (motor_viz3d.js:2231), yani ölçümden hemen önce çağrılması
#: güvenlidir.
JS_OYNAT = """
() => {
  const M = window.MotorViz3D;
  const v = (M && typeof M.get === 'function') ? M.get() : null;
  if (!v || typeof v.play !== 'function') return false;
  v.play();
  return true;
}
"""

#: Sahne kuruldu mu?
JS_SAHNE_KURULDU = "() => !!(window.MotorViz3D && MotorViz3D.get && MotorViz3D.get())"


# ---------------------------------------------------------------------------
# Saf yardımcılar (tarayıcısız sınanabilir)
# ---------------------------------------------------------------------------

def veri_url_baytlari(veri_url: Optional[str]) -> Optional[bytes]:
    """``data:image/png;base64,...`` dizesini ham baytlara çevirir.

    Beklenen biçimin dışındaki her şey için ``None`` döner — bozuk veriden
    "ölçüm" üretmek, ölçüm yapmamaktan kötüdür.
    """
    if not veri_url or not isinstance(veri_url, str):
        return None
    if not veri_url.startswith('data:'):
        return None
    bas, ayrac, govde = veri_url.partition(',')
    if not ayrac or 'base64' not in bas:
        return None
    try:
        baytlar = base64.b64decode(govde, validate=False)
    except Exception:
        return None
    # ``validate=False`` bozuk gövdeyi sessizce boş dizeye çevirir; boş bayt
    # dizisinden "ölçüm" üretilmesin diye burada durdurulur.
    return baytlar or None


def _kisalt(metin: Any, uzunluk: int = 400) -> str:
    s = '' if metin is None else str(metin)
    return s if len(s) <= uzunluk else s[:uzunluk] + '…'


# ---------------------------------------------------------------------------
# Tur
# ---------------------------------------------------------------------------

class SayfaGezgini:
    """Tek bir sayfayı gezip ham ölçümleri toplar."""

    def __init__(self, tarayici_sayfasi, temel_url: str, tanim: Sayfa,
                 cikti_dizini: str):
        self.p = tarayici_sayfasi
        self.temel_url = temel_url.rstrip('/')
        self.tanim = tanim
        self.cikti_dizini = cikti_dizini
        self.kayitlar: List[Dict[str, Any]] = []
        self.http_hatalari: List[Dict[str, Any]] = []
        self.asamalar: List[str] = []
        self.hatalar: List[str] = []

    # -- olay toplayıcılar ------------------------------------------------
    def dinleyicileri_bagla(self) -> None:
        def konsol(ileti):
            self.kayitlar.append({
                'tip': ileti.type,
                'metin': _kisalt(ileti.text),
                'konum': _kisalt(getattr(ileti, 'location', None), 200),
            })

        def sayfa_hatasi(hata):
            self.kayitlar.append({'tip': 'pageerror', 'metin': _kisalt(hata),
                                  'konum': ''})

        def cevap(r):
            try:
                if r.status >= 400:
                    self.http_hatalari.append({'durum': r.status,
                                               'url': _kisalt(r.url, 200)})
            except Exception:
                pass

        self.p.on('console', konsol)
        self.p.on('pageerror', sayfa_hatasi)
        self.p.on('response', cevap)

    # -- adımlar ----------------------------------------------------------
    def gez(self) -> Dict[str, Any]:
        url = self.temel_url + self.tanim.yol
        sureler: Dict[str, float] = {}
        viz: Dict[str, Any] = {}
        tuval_ham: Dict[str, Any] = {}
        piksel: Optional[Dict[str, Any]] = None
        metin: Optional[str] = None
        plume_baslatma = 'yok'
        goruntuler: Dict[str, Optional[str]] = {'tam_sayfa': None, 'uc_boyut': None}

        self.dinleyicileri_bagla()
        try:
            t0 = time.time()
            self.p.goto(url, wait_until='domcontentloaded',
                        timeout=esikler.SAYFA_YUKLEME_ZAMAN_ASIMI_MS)
            try:
                self.p.wait_for_load_state(
                    'networkidle', timeout=esikler.SAYFA_YUKLEME_ZAMAN_ASIMI_MS)
            except Exception:
                # Harita/çokgen katmanları sürekli istek atabiliyor; sayfa
                # yine de kullanılabilir durumda. Bu bir hüküm değil, not.
                self.asamalar.append('ağ sessizliğine ulaşılamadı (devam edildi)')
            sureler['yukleme_s'] = time.time() - t0
            self.asamalar.append('sayfa açıldı: %s' % url)

            self._hesabi_tetikle(sureler)
            self._sahneyi_kurdur()
            plume_baslatma = self._yanmayi_baslat()

            viz = self.p.evaluate(JS_VIZ_DURUMU) or {}
            # Yanma ölçümden önce bittiyse egzoz zaten sönmüş olur; bu, bir
            # kusur değil zamanlama olurdu. Bir kez daha başlatıp ölçeriz ve
            # bunu raporda saklamayız.
            if viz.get('erisim') == 'motorviz3d' and not viz.get('oynatiliyor'):
                if self.p.evaluate(JS_OYNAT):
                    self.asamalar.append('yanma sönmüştü, yeniden başlatıldı')
                    self.p.wait_for_timeout(esikler.PLUME_YENIDEN_ISINMA_MS)
                    viz = self.p.evaluate(JS_VIZ_DURUMU) or {}
                    if plume_baslatma == 'yok':
                        plume_baslatma = 'api'

            tuval_ham = self.p.evaluate(JS_TUVAL) or {}
            baytlar = veri_url_baytlari(tuval_ham.get('veri_url'))
            if baytlar:
                yol = os.path.join(self.cikti_dizini, '%s_3b.png' % self.tanim.ad)
                with open(yol, 'wb') as dosya:
                    dosya.write(baytlar)
                goruntuler['uc_boyut'] = yol
            piksel = denetimler.piksel_olcumu(baytlar)

            metin = self.p.evaluate(JS_SAYFA_METNI)
        except Exception as hata:
            self.hatalar.append('%s: %s' % (type(hata).__name__, _kisalt(hata, 600)))
            self.asamalar.append('AKIŞ KESİLDİ')
        finally:
            try:
                yol = os.path.join(self.cikti_dizini, '%s_tam.png' % self.tanim.ad)
                self.p.screenshot(path=yol, full_page=True)
                goruntuler['tam_sayfa'] = yol
            except Exception as hata:
                self.hatalar.append('tam sayfa görüntüsü alınamadı: %s'
                                    % _kisalt(hata, 200))

        return self._rapor(sureler, viz, tuval_ham, piksel, metin,
                           plume_baslatma, goruntuler)

    def _hesabi_tetikle(self, sureler: Dict[str, float]) -> None:
        dugme = self.p.locator(self.tanim.hesapla_secici).first
        dugme.wait_for(state='visible', timeout=esikler.SAYFA_YUKLEME_ZAMAN_ASIMI_MS)
        t0 = time.time()
        dugme.click()
        self.asamalar.append('hesap düğmesine basıldı: %s' % self.tanim.hesapla_secici)
        self.p.wait_for_function(self.tanim.sonuc_kosulu,
                                 timeout=esikler.HESAP_ZAMAN_ASIMI_MS)
        sureler['hesap_s'] = time.time() - t0
        self.asamalar.append('sonuç nesnesi doldu (%.1f s)' % sureler['hesap_s'])

    def _sahneyi_kurdur(self) -> None:
        if self.p.evaluate(JS_SAHNE_KURULDU):
            self.asamalar.append('3B sahne kendiliğinden kuruldu')
            return
        for secici in self.tanim.viz_acma_secicileri:
            hedef = self.p.locator(secici).first
            try:
                if hedef.count() == 0 or not hedef.is_visible():
                    continue
                hedef.click()
                self.asamalar.append('3B açma düğmesine basıldı: %s' % secici)
            except Exception as hata:
                self.asamalar.append('3B açma düğmesi tıklanamadı (%s): %s'
                                     % (secici, _kisalt(hata, 160)))
                continue
            try:
                self.p.wait_for_function(
                    JS_SAHNE_KURULDU, timeout=esikler.VIZ_KURULUM_ZAMAN_ASIMI_MS)
                self.asamalar.append('3B sahne kuruldu')
                return
            except Exception:
                continue
        if not self.p.evaluate(JS_SAHNE_KURULDU):
            self.asamalar.append('3B sahne KURULMADI')

    def _yanmayi_baslat(self) -> str:
        """Önce gerçek arayüz düğmesi, olmazsa modül API'si.

        Arayüz yolu tercih edilir: kullanıcının bastığı düğme çalışmıyorsa
        bunu da öğrenmiş oluruz. Düğme yoksa/işe yaramazsa API'ye düşülür ve
        hangi yolun kullanıldığı rapora yazılır.
        """
        yol = 'yok'
        try:
            # Sayfada birden çok güverte olabilir (gömülü sekmedeki kopyalar);
            # GÖRÜNEN ilk düğme kullanıcının bastığı düğmedir.
            dugmeler = self.p.locator('button.viz-play')
            for i in range(dugmeler.count()):
                dugme = dugmeler.nth(i)
                if not dugme.is_visible():
                    continue
                dugme.click()
                yol = 'ui'
                self.asamalar.append('yanma düğmesine basıldı (button.viz-play #%d)' % i)
                break
        except Exception as hata:
            self.asamalar.append('yanma düğmesi tıklanamadı: %s' % _kisalt(hata, 160))

        try:
            durum = self.p.evaluate(JS_VIZ_DURUMU) or {}
            if durum.get('erisim') == 'motorviz3d' and not durum.get('oynatiliyor'):
                if self.p.evaluate(JS_OYNAT):
                    yol = 'api' if yol == 'yok' else 'ui+api'
                    self.asamalar.append('yanma MotorViz3D.play() ile başlatıldı')
        except Exception as hata:
            self.asamalar.append('yanma başlatılamadı: %s' % _kisalt(hata, 160))

        if yol != 'yok':
            self.p.wait_for_timeout(esikler.PLUME_ISINMA_MS)
        return yol

    # -- rapor ------------------------------------------------------------
    def _rapor(self, sureler, viz, tuval_ham, piksel, metin, plume_baslatma,
               goruntuler) -> Dict[str, Any]:
        akis_tamam = not self.hatalar
        liste = [
            denetimler.Denetim(
                ad='akis_tamam', gecti=akis_tamam,
                ozet=('gezinti akışı kesintisiz tamamlandı' if akis_tamam
                      else 'gezinti akışı kesildi: %s' % '; '.join(self.hatalar)),
                dayanak='gezinti adımlarının istisna kaydı',
                olcum={'asamalar': self.asamalar, 'hatalar': self.hatalar},
                esik={}),
            denetimler.tuval_denetimi(piksel, kaynak=tuval_ham.get('kaynak', '')),
            denetimler.plume_denetimi(viz, piksel),
            denetimler.konsol_denetimi(self.kayitlar),
            denetimler.sizinti_denetimi(metin),
        ]
        return {
            'ad': self.tanim.ad,
            'url': self.temel_url + self.tanim.yol,
            'gecti': denetimler.sayfa_hukmu(liste),
            'sureler_s': sureler,
            'ekran_goruntuleri': goruntuler,
            'olcumler': {
                'viz': viz,
                'tuval_kaynagi': tuval_ham.get('kaynak'),
                'tuval_hatasi': tuval_ham.get('hata'),
                'piksel': piksel or {},
                'plume_baslatma': plume_baslatma,
                'http_hatalari': self.http_hatalari[:esikler.RAPOR_ORNEK_UST_SINIRI],
                'http_hata_sayisi': len(self.http_hatalari),
            },
            'asamalar': self.asamalar,
            'denetimler': [d.sozluk() for d in liste],
        }


#: ``--channel auto`` verildiğinde sırayla denenen Chromium yapıları.
#: Boş dize = Playwright'ın kendi indirdiği Chromium. Depoda ``playwright
#: install`` koşulmamış bir makinede paketli Chromium yoktur ama sistemde
#: Chrome bulunur; Faz 6 denemesi de ``channel='chrome'`` ile koşmuştu.
KANAL_SIRASI = ('', 'chrome', 'msedge')

#: Paketli Chromium'un adı — künyede boş dize yerine bu yazılır.
PAKETLI_KANAL_ADI = '(paketli chromium)'


def _tarayici_ac(pw, kanal: Optional[str], basli: bool):
    """İlk açılan Chromium yapısını döner; hepsi başarısızsa istisna yükseltir.

    Hangi yapının kullanıldığı raporda saklanır: farklı sürücüler farklı
    WebGL davranışı gösterebilir, hüküm okunurken bu bilinmeli.
    """
    denemeler = [kanal] if (kanal and kanal != 'auto') else list(KANAL_SIRASI)
    hatalar: List[str] = []
    for k in denemeler:
        baslat: Dict[str, Any] = {'headless': not basli}
        if k:
            baslat['channel'] = k
        try:
            tarayici = pw.chromium.launch(**baslat)
            return tarayici, (k or PAKETLI_KANAL_ADI)
        except Exception as hata:
            hatalar.append('%s -> %s' % (k or PAKETLI_KANAL_ADI, _kisalt(hata, 160)))
    raise RuntimeError('Chromium açılamadı. Denenenler: %s' % ' | '.join(hatalar))


def turu_kos(temel_url: str, sayfa_tanimlari: Sequence[Sayfa], cikti_dizini: str,
             basli: bool = False, kanal: Optional[str] = None):
    """Verilen sayfaları sırayla gezer.

    ``(sayfa_raporlari, tarayici_kunyesi)`` döner. Her sayfa TEMİZ bir
    tarayıcı bağlamında gezilir: bir sayfanın localStorage'a yazdığı uçuş
    devri (``FlightHandoff``) bir sonrakinin ölçümünü etkilemesin.
    """
    from playwright.sync_api import sync_playwright  # yerel içe aktarım (bkz. modül notu)

    os.makedirs(cikti_dizini, exist_ok=True)
    raporlar: List[Dict[str, Any]] = []
    with sync_playwright() as pw:
        tarayici, kullanilan = _tarayici_ac(pw, kanal, basli)
        kunye = {'motor': 'chromium', 'kanal': kullanilan,
                 'surum': tarayici.version, 'basli': bool(basli),
                 '_dayanak': 'playwright Browser.version'}
        try:
            for tanim in sayfa_tanimlari:
                baglam = tarayici.new_context(viewport=esikler.GORUNTU_ALANI,
                                              locale=esikler.TARAYICI_YERELI)
                try:
                    sayfa = baglam.new_page()
                    raporlar.append(
                        SayfaGezgini(sayfa, temel_url, tanim, cikti_dizini).gez())
                finally:
                    baglam.close()
        finally:
            tarayici.close()
    return raporlar, kunye
