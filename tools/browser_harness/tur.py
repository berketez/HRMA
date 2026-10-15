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
import hashlib
import os
import time
import urllib.parse
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

#: ÖH D27 / OH-D25-02(a) — sayfanın BEYAN ETTİĞİ tuvalinin KİMLİĞİ
#: (``Sayfa.tuval_secici``). ``JS_TUVAL``dan farkı: "en büyük tuvali bul"
#: sezgisi YOKTUR; beyan edilen seçici neyi gösteriyorsa o ölçülür. Seçici
#: bir tuval göstermiyorsa hata döner (fail-closed) — sessizce başka bir
#: tuvale kaymak, ölçülen yüzeyin adını yalan yapardı.
#:
#: PİKSELLER BURADAN OKUNMAZ. ``canvas.toDataURL()`` bir WebGL tuvalinde
#: yalnız ``preserveDrawingBuffer: true`` verilmişse ya da çizimle AYNI
#: görevde okunuyorsa dolu gelir (motor_viz3d.js:5423 bunu adıyla anıyor;
#: launch_site_globe.js:311 bayrağı VERMİYOR). İlk denememiz tam bu tuzağa
#: düştü ve ÖLÇÜLDÜ: küre ekranda çizili dururken toDataURL 1600×946'lık
#: BOŞ bir PNG verdi (dolu_oran 0,0 / entropi 0,0 / benzersiz renk 0) ve
#: denetim "3B tuval BOŞ" diye YANLIŞ kırmızı yaktı. Ölçüm artefaktını
#: ürün kusuru diye yayımlamak, kusuru gizlemek kadar kötüdür. Piksel
#: kanıtı bu yüzden Playwright'ın ELEMAN ekran görüntüsünden alınır: o,
#: kullanıcının gördüğü BİRLEŞTİRİLMİŞ kareyi yakalar.
JS_BEYANLI_TUVAL = """
(c) => {
  const el = document.querySelector(c.secici);
  if (!el) return { hata: 'beyan edilen tuval seçicisi hiçbir şeyi göstermiyor: '
                          + c.secici };
  if (el.tagName !== 'CANVAS')
    return { hata: 'beyan edilen seçici tuval değil (' + el.tagName + '): '
                   + c.secici };
  const r = el.getBoundingClientRect();
  return { tuval_genislik: el.width, tuval_yukseklik: el.height,
           ekran_genislik: Math.round(r.width),
           ekran_yukseklik: Math.round(r.height) };
}
"""

#: Görünen metin. Betik gövdeleri innerText'e girmez; aranan şey KULLANICININ
#: gördüğü sızıntıdır.
#:
#: ÖH D22 / P17B1-12 — ÖLÇÜLEN KUSUR: gövde yalnız ``document.body.innerText``
#: idi. ``innerText`` TANIM GEREĞİ ``<input>`` / ``<select>`` / ``<textarea>``
#: DEĞERLERİNİ içermez; yani turun bütün metin taraması (sızıntı denetimi
#: dahil) ekranda duran FORM ALANLARINA yapısal olarak kördü. P17 turu üç
#: sayfada 182 dolu alan saydı, bunların ayırt edici 8 değerinin taranan
#: metinde geçme sayısı **0**du; nöbetçi değerle doğrulandı (``thrust``
#: alanına 987654321 yazıldı → metinde False).
#:
#: Onarım: görünür form denetimlerinin KULLANICININ GÖRDÜĞÜ değeri metnin
#: sonuna eklenir. Kapsam dar tutulur, çünkü amaç ekran yüzeyini ölçmektir:
#:   - görünmeyen (offsetParent yok / display:none / görünürlük kapalı),
#:     type="hidden" ve parola alanları ATLANIR,
#:   - ``<select>`` için seçili SEÇENEK METNİ alınır (kullanıcı değeri değil
#:     etiketi görür — çeviri sızıntısı da böyle yakalanır),
#:   - onay/radyo kutusunun metni yoktur, işaretli olması metin değildir:
#:     ATLANIR,
#:   - boş değer eklenmez (boşluk sızıntı taramasına gürültü katmaz).
#: Ayırıcı satır başıdır; sızıntı denetimi satır satır çalıştığı için alan
#: değeri kendi satırında durur ve komşu cümleye yapışmaz.
JS_SAYFA_METNI = """
() => {
  const govde = document.body ? document.body.innerText : '';
  const parcalar = [];
  const gorunur = (el) => {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  document.querySelectorAll('input, select, textarea').forEach((el) => {
    const etiket = el.tagName;
    const tip = (el.getAttribute('type') || '').toLowerCase();
    if (tip === 'hidden' || tip === 'password'
        || tip === 'checkbox' || tip === 'radio') return;
    if (!gorunur(el)) return;
    let deger = '';
    if (etiket === 'SELECT') {
      const s = el.selectedOptions && el.selectedOptions[0];
      deger = s ? (s.textContent || '') : '';
    } else {
      deger = el.value == null ? '' : String(el.value);
    }
    deger = deger.trim();
    if (deger) parcalar.push(deger);
  });
  return parcalar.length ? (govde + '\\n' + parcalar.join('\\n')) : govde;
}
"""

#: ÖH Faz 0 — sayfa yerleşimi ölçümü: yatay taşma + görünür metin
#: yapraklarının örtüşmesi. Metin yaprağı = DOĞRUDAN metin düğümü dolu,
#: görünür, çizim kaplarının (canvas/svg/.js-plotly-plot altı) dışında bir
#: eleman. Ata-torun çiftleri örtüşme sayılmaz (bir paragrafın kutusu kendi
#: satır içi çocuğunu meşru olarak kapsar); kalan her metin⟂metin kesişimi
#: eşiklerin üstündeyse yerleşim kusurudur. Eşikler ``esikler.py``den
#: geçirilir; burada sayı YOKTUR.
JS_YERLESIM = """
(c) => {
  const yapiskanlar = [];
  try {
    const de = document.documentElement;
    const tasma = Math.max(0, de.scrollWidth - de.clientWidth);
    // v3.0.0 (15 Eki): taşma varsa SUÇLU öğeler adıyla raporlanır (yalnız
    // ebeveyni taşmayan en dış öğeler) — 'X px taşıyor' tek başına onarım
    // yeri göstermiyordu.
    const tasanlar = [];
    if (tasma > 0) {
      const W = de.clientWidth;
      document.querySelectorAll('body *').forEach(function (e) {
        const r = e.getBoundingClientRect();
        if (!(r.width > 0 && r.right > W + 1)) return;
        const p = e.parentElement;
        if (p && p !== document.body && p.getBoundingClientRect().right > W + 1) return;
        const sinif = (typeof e.className === 'string' && e.className)
          ? '.' + e.className.trim().split(/\\s+/).slice(0, 2).join('.') : '';
        // Kimliksiz öğe için en yakın KİMLİKLİ ata da yazılır: 'table'
        // tek başına hangi panelin taştığını söylemiyordu (tur1).
        let ata = p, ata_ad = '';
        for (let k = 0; ata && ata !== document.body && k < 12; k++) {
          if (ata.id) { ata_ad = ata.tagName.toLowerCase() + '#' + ata.id; break; }
          ata = ata.parentElement;
        }
        tasanlar.push([Math.round(r.right),
                       e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + sinif,
                       ata_ad, e.outerHTML.slice(0, 160)]);
      });
      tasanlar.sort(function (a, b) { return b[0] - a[0]; });
    }
    const yapraklar = [];
    const elemanlar = [];
    let kirpildi = false;
    const KIRPAN = new Set(['hidden', 'clip', 'auto', 'scroll']);
    // ÖH D27 / OH-D26-13 — YAPIŞKAN KUTULAR.
    // ``position:sticky`` bir elemanın ``getBoundingClientRect()``i, kutu
    // YAPIŞMIŞKEN yerleşim (akış) konumunu değil BOYANDIĞI konumu döner.
    // Ölçüm sayfa koordinatına ``+ window.scrollY`` ile çevrildiği için
    // sonuç KAYDIRMAYA BAĞLI olur: aynı sayfa, aynı DOM, farklı kaydırma
    // konumunda farklı örtüşme hükmü. Ölçüldü (once_canli.json, /hybrid,
    // sistem Chrome 152): ``#ac_history_box`` scrollY=2101'de sayfa
    // konumunu 23277, scrollY=23244'te 23931 bildiriyor (654 px fark) ve
    // örtüşme sayısı 1 ⟷ 0 arasında zıplıyor — biri yanlış pozitif, öbürü
    // yanlış negatif. Kutu yürüyüşten ÖNCE ``position:static``a alınır
    // (yapışkan eleman akıştan ÇIKMAZ; static'te kutusu akıştaki yerinde
    // durur, yalnız yapışma kaydırması kalkar), ölçüm bittiğinde satır içi
    // stil AYNEN geri yazılır. Etkisizleştirilen eleman sayısı raporda
    // ADIYLA durur: sessiz düzeltme yok.
    for (const el of document.querySelectorAll('*')) {
      const yst = getComputedStyle(el);
      if (yst.position !== 'sticky' && yst.position !== '-webkit-sticky') continue;
      yapiskanlar.push({ el: el, eski: el.style.position });
      el.style.position = 'static';
    }
    // Yürüyüş, atalardan gelen KIRPMA dikdörtgenini (mutlak sayfa
    // koordinatında) taşır: max-height:0 + overflow:hidden ile katlanmış
    // bir blok, kutusu tam boy ölçülse de EKRANDA yoktur — kapalı
    // <details> gövdesi ve <select> seçenekleri de öyle. İlk canlı koşum
    // (26 Ağu, Faz 0) bu üç sınıfın sahte örtüşme ürettiğini gösterdi;
    // bu yüzden yaprak kutusu kırpma ile KESİŞTİRİLEREK ölçülür.
    const yurut = (el, kirpma) => {
      if (!(el && el.nodeType === 1)) return;
      const ad = el.tagName;
      if (ad === 'SCRIPT' || ad === 'STYLE' || ad === 'NOSCRIPT'
          || ad === 'CANVAS' || ad === 'SVG' || ad === 'svg'
          || ad === 'SELECT' || ad === 'OPTION' || ad === 'OPTGROUP'
          || ad === 'DATALIST'
          || el.namespaceURI === 'http://www.w3.org/2000/svg') return;
      if (el.classList && el.classList.contains('js-plotly-plot')) return;
      const st = getComputedStyle(el);
      if (st.display === 'none' || st.visibility === 'hidden'
          || parseFloat(st.opacity || '1') === 0) return;
      const r = el.getBoundingClientRect();
      const mx = r.left + window.scrollX, my = r.top + window.scrollY;
      if (KIRPAN.has(st.overflowX)) {
        kirpma = { x1: Math.max(kirpma.x1, mx),
                   x2: Math.min(kirpma.x2, mx + r.width),
                   y1: kirpma.y1, y2: kirpma.y2 };
      }
      if (KIRPAN.has(st.overflowY)) {
        kirpma = { x1: kirpma.x1, x2: kirpma.x2,
                   y1: Math.max(kirpma.y1, my),
                   y2: Math.min(kirpma.y2, my + r.height) };
      }
      let oz = '';
      for (const dugum of el.childNodes) {
        if (dugum.nodeType === 3) oz += dugum.textContent;
      }
      oz = oz.replace(/\\s+/g, ' ').trim();
      if (oz) {
        // Çok satıra sarılmış INLINE elemanın sınır kutusu, ilk satırın
        // önündeki komşu etiketi de kapsar (satır kutularının birleşimi) —
        // örtüşme SATIR PARÇALARI üstünden ölçülür (getClientRects), yoksa
        // '<strong>etiket</strong> <span>uzun metin</span>' deseni sahte
        // örtüşme üretir (ilk canlı koşumda ölçüldü).
        let parcalar = [r];
        if (st.display.indexOf('inline') === 0) {
          const satirlar = el.getClientRects();
          if (satirlar.length > 1) parcalar = Array.from(satirlar);
        }
        for (const parca of parcalar) {
          if (yapraklar.length >= c.sinir) { kirpildi = true; break; }
          const px = parca.left + window.scrollX;
          const py = parca.top + window.scrollY;
          const x1 = Math.max(px, kirpma.x1);
          const y1 = Math.max(py, kirpma.y1);
          const x2 = Math.min(px + parca.width, kirpma.x2);
          const y2 = Math.min(py + parca.height, kirpma.y2);
          if (x2 - x1 > 1 && y2 - y1 > 1) {
            yapraklar.push({ m: oz.slice(0, 60), x: x1, y: y1,
                             g: x2 - x1, k: y2 - y1 });
            elemanlar.push(el);
          }
        }
      }
      if (ad === 'DETAILS' && !el.open) {
        // Kapalı ayrıntı bloğunun ekrandaki tek parçası özetidir; gövdesi
        // kutu ölçse de görünmez (Chromium content-visibility davranışı
        // sürümden sürüme değişiyor — açıkça atlanır).
        for (const cocuk of el.children) {
          if (cocuk.tagName === 'SUMMARY') yurut(cocuk, kirpma);
        }
        return;
      }
      for (const cocuk of el.children) yurut(cocuk, kirpma);
    };
    yurut(document.body, { x1: -Infinity, y1: -Infinity,
                           x2: Infinity, y2: Infinity });
    // Örtüşen metnin hangi panelde olduğu: en yakın KİMLİKLİ ata.
    const kimlikliAta = function (e) {
      for (let k = 0; e && e !== document.body && k < 12; k++) {
        if (e.id) return e.tagName.toLowerCase() + '#' + e.id;
        e = e.parentElement;
      }
      return '';
    };
    const sira = yapraklar.map((v, i) => i).sort(
      (a, b) => yapraklar[a].y - yapraklar[b].y);
    const ortusmeler = [];
    for (let s = 0; s < sira.length && ortusmeler.length < c.ornek; s++) {
      const i = sira[s];
      const A = yapraklar[i];
      for (let t = s + 1; t < sira.length; t++) {
        const j = sira[t];
        const B = yapraklar[j];
        if (B.y >= A.y + A.k) break;
        const gx = Math.min(A.x + A.g, B.x + B.g) - Math.max(A.x, B.x);
        const gy = Math.min(A.y + A.k, B.y + B.k) - Math.max(A.y, B.y);
        if (gx <= 0 || gy <= 0) continue;
        const alan = gx * gy;
        const kucuk = Math.min(A.g * A.k, B.g * B.k);
        if (alan < c.min_alan || alan < c.oran * kucuk) continue;
        if (elemanlar[i].contains(elemanlar[j])
            || elemanlar[j].contains(elemanlar[i])) continue;
        ortusmeler.push({ a: A.m, b: B.m, alan: Math.round(alan),
                          konum: [Math.round(Math.max(A.x, B.x)),
                                  Math.round(Math.max(A.y, B.y))],
                          a_ata: kimlikliAta(elemanlar[i]),
                          b_ata: kimlikliAta(elemanlar[j]),
                          a_html: elemanlar[i].outerHTML.slice(0, 160),
                          b_html: elemanlar[j].outerHTML.slice(0, 160) });
        if (ortusmeler.length >= c.ornek) break;
      }
    }
    return { yatay_tasma_px: tasma, tasan_ogeler: tasanlar.slice(0, 8),
             belge_genisligi: de.scrollWidth,
             pencere_genisligi: de.clientWidth,
             yaprak_sayisi: yapraklar.length, kirpildi: kirpildi,
             yapiskan_etkisizlestirilen: yapiskanlar.length,
             ortusmeler: ortusmeler };
  } catch (hata) { return { hata: String(hata) }; }
  finally {
    // Ölçüm sayfayı DEĞİŞTİRMİŞ bırakamaz: turun sonraki adımları
    // (tam sayfa görüntüsü) aynı sayfada koşuyor.
    for (const y of yapiskanlar) y.el.style.position = y.eski;
  }
}
"""

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

#: FEA panelinin durumu. Hüküm için gereken HER ŞEY tek okumada alınır:
#: panelin görünürlüğü, panelin kendi sonuç nesnesi (``payload``), meşgul
#: göstergesi, çip metni (koşum başarısızsa gerekçe orada), rozet metinleri
#: ve beklenen çizim kaplarının hâli.
#:
#: Seçiciler KİMLİK (``id``) üstündendir, görünen metne bakılmaz: paneller
#: çevrilebilir arayüzle basılıyor. Çizim ölçütü de dizge değil DÜĞÜM
#: sayısıdır — "kap açık" ile "içine gerçekten çizilmiş" ayrı sorulardır.
JS_FEA_PANEL_DURUMU = """
(c) => {
  const gizliDegil = (el) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden';
  };
  const gorunur = (el, minKenar) => {
    if (!gizliDegil(el)) return false;
    const r = el.getBoundingClientRect();
    return r.width >= (minKenar || 1) && r.height >= (minKenar || 1);
  };
  const panel = document.getElementById(c.panel);
  if (!panel) return { panel: c.panel, panel_var: false, panel_gorunur: false };
  const api = window[c.api] || null;
  let yuk = null;
  try { yuk = api ? api.payload : null; } catch (e) { yuk = null; }
  // ÖH Faz 0 (P17 reçetesi): yükün yalnız VARLIĞI değil hüküm taşıyan
  // İÇERİĞİ de kaydedilir — rozet⟷yük çaprazı ancak bununla kurulabilir.
  // Diziler (mesh alanları, tarihçeler) atılır; yalnız skaler/hüküm
  // blokları taşınır ki rapor şişmesin.
  const yukOzeti = (function (y) {
    if (!y || typeof y !== 'object') return null;
    const kucult = function (v, derinlik) {
      if (v === null) return null;
      const t = typeof v;
      if (t === 'number' || t === 'boolean' || t === 'string') return v;
      if (Array.isArray(v) || t !== 'object' || derinlik >= 3) return undefined;
      const kopya = {};
      Object.keys(v).forEach(function (k) {
        const kv = kucult(v[k], derinlik + 1);
        if (kv !== undefined) kopya[k] = kv;
      });
      return kopya;
    };
    const secilen = {};
    ['scalars', 'convergence', 'material_limits', 'time_step', 'energy',
     'mesh_info', 'flags', 'limits', 'engine_layout', 'grain_type',
     'symmetry_fraction'].forEach(function (k) {
      if (k in y) {
        const kv = kucult(y[k], 0);
        if (kv !== undefined) secilen[k] = kv;
      }
    });
    // fea_panel.js motorKarsilastirmasi: rozet rengi FEA sayısıyla motorun
    // KENDİ emniyet katsayısının küçüğünden verilir (v3.0.0, 15 Eki).
    const mk = (y.meta && typeof y.meta === 'object')
      ? y.meta.motor_sf_karsilastirmasi : null;
    if (mk && typeof mk === 'object' && !Array.isArray(mk)) {
      const kv = kucult(mk, 0);
      if (kv !== undefined) secilen.motor_sf_karsilastirmasi = kv;
    }
    return secilen;
  })(yuk);
  const rozetKabi = document.getElementById(c.rozet);
  const rozetler = rozetKabi
    ? Array.from(rozetKabi.querySelectorAll('[data-badge]')).map(function (b) {
        return { tur: b.getAttribute('data-badge'),
                 metin: (b.textContent || '').replace(/\\s+/g, ' ').trim() };
      })
    : [];
  const cizimler = {};
  (c.cizimler || []).forEach(function (kimlik) {
    const el = document.getElementById(kimlik);
    if (!el) { cizimler[kimlik] = { mevcut: false }; return; }
    const r = el.getBoundingClientRect();
    cizimler[kimlik] = {
      mevcut: true,
      gorunur: gorunur(el, c.min_kenar),
      plotly_kabi: el.classList.contains('js-plotly-plot'),
      svg_sayisi: el.querySelectorAll('svg').length,
      canvas_sayisi: el.querySelectorAll('canvas').length,
      genislik: Math.round(r.width),
      yukseklik: Math.round(r.height)
    };
  });
  const cip = document.getElementById(c.cip);
  return {
    panel: c.panel,
    api: c.api,
    panel_var: true,
    // Panel için ölçüt yalnız "kutusu var mı": kap tam genişliktir ama
    // çizim eşiğiyle (``min_kenar``) ölçülmez — o eşik ÇİZİM kaplarınındır.
    // İkisi aynı sayıya bağlanırsa eşik değiştiğinde hüküm kayar.
    panel_gorunur: gorunur(panel, 1),
    api_var: !!api,
    yuk_var: !!yuk,
    yuk_ozeti: yukOzeti,
    mesgul: gizliDegil(document.getElementById(c.mesgul)),
    cip_metni: cip ? (cip.textContent || '').replace(/\\s+/g, ' ').trim() : null,
    rozetler: rozetler,
    rozet_sayisi: rozetler.length,
    cizimler: cizimler,
    panel_plotly_kap_sayisi: panel.querySelectorAll('.js-plotly-plot').length
  };
}
"""

#: Meşgul göstergesi açık mı? Koşumun BAŞLADIĞINI söyleyen tek sayfa içi
#: işaret budur: ``run()`` bayrağı fetch'ten önce kaldırır ve basım onu
#: görünür kılar.
JS_FEA_MESGUL = """
(c) => {
  const el = document.getElementById(c.mesgul);
  if (!el) return false;
  const s = getComputedStyle(el);
  return s.display !== 'none' && s.visibility !== 'hidden';
}
"""

#: Koşum bitti mi? Meşgul göstergesi kapandıysa panel ya yükü basmıştır ya
#: da gerekçeyi çipe yazmıştır; ikisini de sonraki okuma ayırır.
JS_FEA_BITTI = """
(c) => {
  const el = document.getElementById(c.mesgul);
  if (!el) return true;
  const s = getComputedStyle(el);
  return s.display === 'none' || s.visibility === 'hidden';
}
"""

# ---------------------------------------------------------------------------
# Analiz Merkezi (analysis_center.js) ölçüm betikleri
# ---------------------------------------------------------------------------

#: Merkez ÇERÇEVESİNİN durumu: panel kuruldu mu, üç sütun ayakta mı, bileşen
#: ağacındaki satırlar hangi durumda ve nedenleri yazılı mı?
#:
#: Satırlar METİNLE değil ÖZNİTELİKLE okunur (``data-ac-row`` /
#: ``data-ac-state`` / ``data-ac-reason``): durum adı çevrilmez, rozet metni
#: çevrilir. Nedenin METNİ ayrıca alınır çünkü ölçülen şey "neden ADIYLA
#: yazılmış mı" — boş bir gri satır tasarımın kural 1'ini ihlal eder.
JS_MERKEZ_CERCEVE = """
(c) => {
  const gorunur = (el, minKenar) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width >= (minKenar || 1) && r.height >= (minKenar || 1);
  };
  const duz = (t) => (t || '').replace(/\\s+/g, ' ').trim();
  const panel = document.getElementById(c.panel);
  if (!panel) return { panel: c.panel, panel_var: false, panel_gorunur: false };
  const sutunlar = {};
  (c.sutunlar || []).forEach(function (kimlik) {
    const el = document.getElementById(kimlik);
    sutunlar[kimlik] = { mevcut: !!el, gorunur: gorunur(el, 1) };
  });
  const satirlar = Array.from(panel.querySelectorAll('[data-ac-row]'))
    .map(function (b) {
      const n = b.querySelector('[data-ac-reason]');
      return { anahtar: b.getAttribute('data-ac-row'),
               durum: b.getAttribute('data-ac-state'),
               neden: n ? duz(n.textContent) : '',
               gorunur: gorunur(b, 1) };
    });
  const motor = document.getElementById('ac_motor');
  return {
    panel: c.panel,
    panel_var: true,
    panel_gorunur: gorunur(panel, 1),
    sutunlar: sutunlar,
    gecmis_var: !!document.getElementById(c.gecmis),
    api_var: !!(window.AnalysisCenter
                && typeof window.AnalysisCenter.history === 'function'),
    motor_metni: motor ? duz(motor.textContent) : null,
    satirlar: satirlar,
    satir_sayisi: satirlar.length,
    metin: duz(panel.innerText || '')
  };
}
"""

#: Merkez geçmişindeki kayıt sayısı — koşumun BİTTİĞİNİ söyleyen tek dürüst
#: işaret. ``pushEntry`` hem başarılı hem başarısız koşumda çalışır.
JS_MERKEZ_GECMIS_UZUNLUGU = """
() => {
  const A = window.AnalysisCenter;
  if (!A || typeof A.history !== 'function') return null;
  try { return A.history().length; } catch (e) { return null; }
}
"""

#: Koşum BAŞLADI mı? Düğmenin ``disabled`` bayrağı metinden bağımsızdır
#: (``renderStatus`` onu ``busy`` gerçek durumundan yazar).
JS_MERKEZ_MESGUL = """
(c) => {
  const b = document.getElementById(c.dugme);
  return !!(b && b.disabled);
}
"""

#: Koşum BİTTİ mi? İki dürüst çıkış vardır ve ikisi de beklenir:
#:   1. geçmişe yeni kayıt düştü (istek gönderildi ve cevaplandı/hata verdi),
#:   2. istek HİÇ gönderilmedi — eksik zorunlu alan hâlinde ``run()`` erken
#:      döner, meşgul olmaz ve durum satırına gerekçeyi yazar.
#: İkincisi olmasaydı, alanı boş kalan bir kart turu zaman aşımına kadar
#: bekletirdi ve kusur "takıldı" diye görünürdü.
JS_MERKEZ_KOSUM_BITTI = """
(c) => {
  const A = window.AnalysisCenter;
  if (A && typeof A.history === 'function') {
    try { if (A.history().length > c.gecmis_esigi) return true; } catch (e) {}
  }
  const b = document.getElementById(c.dugme);
  const s = document.getElementById(c.durum);
  const metin = s ? (s.textContent || '').trim() : '';
  return !!(b && !b.disabled && metin);
}
"""

#: Kiracının koşum SONRASI durumu: geçmiş kaydı, yanıtın kendi alanları,
#: görüntüleyici kabındaki çizimler ve rozetler.
#:
#: Yükten okunan alanlar BİLEREK dardır: hüküm için gereken beyanlar
#: (yakınsama, ayrılma güveni, bütçe uyarısı) alınır, sayısal alan blokları
#: alınmaz — rapor tanı içindir, yanıtın kopyası değil.
JS_MERKEZ_KIRACI = """
(c) => {
  const gorunur = (el, minKenar) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width >= (minKenar || 1) && r.height >= (minKenar || 1);
  };
  const duz = (t) => (t || '').replace(/\\s+/g, ' ').trim();
  const A = window.AnalysisCenter;
  let gecmis = null;
  try { gecmis = (A && typeof A.history === 'function') ? A.history() : null; }
  catch (e) { gecmis = null; }
  const son = (gecmis && gecmis.length) ? gecmis[gecmis.length - 1] : null;
  // ÖH D23 / P10B3-03 — yük okuyucusu artık BEYANA göre çalışır.
  // Eskiden bu blok CFD'nin yük anahtarına ve alan adlarına GÖMÜLÜYDÜ;
  // ikinci bir kiracı eklemek JS düzenlemeyi gerektiriyordu. Alan listesi
  // ve dönüşümler `sayfalar.MerkezKiracisi.yuk_alanlari`ndan gelir.
  const yol_izle = (kok, yol) => {
    let d = kok;
    const parcalar = String(yol).split('.');
    for (let i = 0; i < parcalar.length; i++) {
      if (d === null || d === undefined || typeof d !== 'object') return undefined;
      d = d[parcalar[i]];
    }
    return d;
  };
  const donustur = (v, tur) => {
    if (tur === 'mantiksal') return (typeof v === 'boolean') ? v : null;
    if (tur === 'bool') return !!v;
    if (tur === 'uzunluk') return Array.isArray(v) ? v.length : 0;
    if (tur === 'dolu_deger') return v || null;
    return (v === undefined) ? null : v;   // 'deger'
  };
  let yuk = null;
  const alanlar = c.yuk_alanlari || [];
  if (son && son.ok && son.data && alanlar.length) {
    const kok_yuk = c.yuk_anahtari ? son.data[c.yuk_anahtari] : son.data;
    if (kok_yuk !== null && kok_yuk !== undefined) {
      yuk = {};
      for (let i = 0; i < alanlar.length; i++) {
        const a = alanlar[i];
        yuk[a[0]] = donustur(yol_izle(kok_yuk, a[1]), a[2]);
      }
    }
  }
  const kok = document.getElementById(c.kok);
  const cizimler = kok
    ? Array.from(kok.querySelectorAll(c.cizim_secici)).map(function (el) {
        const r = el.getBoundingClientRect();
        return { kimlik: el.id,
                 gorunur: gorunur(el, c.min_kenar),
                 plotly_kabi: el.classList.contains('js-plotly-plot'),
                 svg_sayisi: el.querySelectorAll('svg').length,
                 canvas_sayisi: el.querySelectorAll('canvas').length,
                 genislik: Math.round(r.width),
                 yukseklik: Math.round(r.height) };
      })
    : [];
  // Ürünün BEYANLI YOKLUK blokları (stability_panel.js greyBlock): çizim
  // yoksa gerekçe burada basılır; denetim kiracının beyanlı_yokluklar
  // eşlemesiyle karşılaştırır.
  const gri_bloklar = kok
    ? Array.from(kok.querySelectorAll('[data-stab-grey]')).map(function (g) {
        return { ad: g.getAttribute('data-stab-grey'),
                 gorunur: gorunur(g, 1),
                 metin: duz(g.textContent).slice(0, 400) };
      })
    : [];
  const rozetler = kok
    ? Array.from(kok.querySelectorAll(c.rozet_secici)).map(function (b) {
        return { tur: b.getAttribute(c.rozet_ozniteligi),
                 metin: duz(b.textContent) };
      })
    : [];
  const durum = document.getElementById(c.durum);
  return {
    kok_var: !!kok,
    kok_gorunur: gorunur(kok, 1),
    gecmis_uzunlugu: gecmis ? gecmis.length : null,
    son_kosum: son ? { ok: !!son.ok, seconds: son.seconds,
                       satir: son.rowKey,
                       hata: son.errorText || null,
                       hukum_anahtari: son.verdict ? (son.verdict.key || null) : null,
                       hukum_sinifi: son.verdict ? (son.verdict.kind || null) : null }
                   : null,
    yuk: yuk,
    cizimler: cizimler,
    cizim_sayisi: cizimler.length,
    gri_bloklar: gri_bloklar,
    rozetler: rozetler,
    rozet_sayisi: rozetler.length,
    durum_metni: durum ? duz(durum.textContent) : null,
    metin: kok ? duz(kok.innerText || '') : ''
  };
}
"""


# ---------------------------------------------------------------------------
# Saf yardımcılar (tarayıcısız sınanabilir)
# ---------------------------------------------------------------------------

#: PNG imzası — IHDR başlığı imzadan hemen sonra gelir.
_PNG_IMZASI = b'\x89PNG\r\n\x1a\n'


def png_boyutu(yol: str) -> Optional[Dict[str, int]]:
    """PNG dosyasının piksel boyutunu IHDR'den okur (bağımlılıksız).

    ÖH D20 · P17B1-05: turun sakladığı tek insan-okur kanıt tam sayfa
    PNG'ydi ve hiçbir denetim onun YÜKSEKLİĞİNE bakmıyordu. Yükseklik
    ölçülmeden "kanıt saklandı" denemez. Okunamayan dosya için ``None``
    döner (bozuk veriden ölçüm uydurulmaz).
    """
    try:
        with open(yol, 'rb') as f:
            bas = f.read(24)
    except OSError:
        return None
    if len(bas) < 24 or not bas.startswith(_PNG_IMZASI):
        return None
    if bas[12:16] != b'IHDR':
        return None
    genislik = int.from_bytes(bas[16:20], 'big')
    yukseklik = int.from_bytes(bas[20:24], 'big')
    if genislik <= 0 or yukseklik <= 0:
        return None
    return {'genislik': genislik, 'yukseklik': yukseklik}


def dosya_sha256(yol: str) -> Optional[str]:
    """Dosya içeriğinin sha256'sı (ÖH D27 / OH-D25-02b).

    Dilimli tam-sayfa kanıtında dilimlerin BİRBİRİNDEN FARKLI olduğunu
    ölçmek için gerekir. Kalemin kökü tam buydu: ``full_page=True`` ile
    istenen dev PNG'de tavanı aşan bant üst bandın BİREBİR tekrarıydı
    (maks piksel farkı 0) ve hiçbir denetim bunu göremiyordu — dilimlerin
    yükseklik toplamı doğruyken içerikleri aynı olabilir. Okunamayan dosya
    için ``None`` döner; uydurma imza üretilmez.
    """
    h = hashlib.sha256()
    try:
        with open(yol, 'rb') as f:
            for parca in iter(lambda: f.read(1 << 20), b''):
                h.update(parca)
    except OSError:
        return None
    return h.hexdigest()


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


class _HesapsizSayfaBitti(Exception):
    """Hesapsız sayfanın gezintisi TAMAMLANDI (kusur değil, akış sonu).

    ÖH D21 / P17B1-16. ``gez()`` gövdesi tek bir ``try`` bloğudur; hesapsız
    sayfada ölçüm erken biter ve geri kalan adımlar (3B, FEA, Merkez)
    ATLANMALIDIR. ``return`` kullanılamaz: ``finally`` içindeki tam sayfa
    görüntüsü ve ``_rapor`` çağrısı kaçırılırdı. Bu istisna akışı ``finally``
    üzerinden düzgün kapatır ve ``self.hatalar``a HİÇBİR ŞEY yazmaz.
    """


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
        if self.tanim.ornek_proje:
            url += '?project=' + urllib.parse.quote(self.tanim.ornek_proje)
        sureler: Dict[str, float] = {}
        viz: Dict[str, Any] = {}
        tuval_ham: Dict[str, Any] = {}
        piksel: Optional[Dict[str, Any]] = None
        metin: Optional[str] = None
        fea: Dict[str, Any] = {}
        merkez: Dict[str, Any] = {}
        yerlesim: Dict[str, Any] = {}
        plume_baslatma = 'yok'
        goruntuler: Dict[str, Any] = {'tam_sayfa': None,
                                      'tam_sayfa_px': None,
                                      'uc_boyut': None}

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
            if self.tanim.ornek_proje:
                from tools.browser_harness.piksel import PROJE_YUKLENDI_KOSULU
                self.p.wait_for_function(
                    PROJE_YUKLENDI_KOSULU, arg=self.tanim.ornek_proje,
                    timeout=esikler.PIKSEL_PROJE_YUKLEME_ZAMAN_ASIMI_MS)
                self.asamalar.append('örnek proje yüklendi: %s'
                                     % self.tanim.ornek_proje)

            # ÖH D21 / defter P17B1-16 — HESAPSIZ SAYFA DALI.
            # ``/``, ``/formulas`` ve ``/launch-site`` sayfalarında hesap
            # düğmesi, ``currentResults`` nesnesi, 3B sahne, FEA paneli ve
            # Analiz Merkezi YOKTUR (ölçüldü). Bu dal onları aramaz —
            # aramak, olmayan bir düğmeyi bekleyip akışı kesmek olurdu ve
            # üç sayfa da "AKIŞ KESİLDİ" ile kırmızı yanardı. Geriye
            # kullanıcının o sayfada gerçekten maruz kaldığı yüzey kalır:
            # konsol, sızıntı, yerleşim, tam sayfa görüntüsü.
            if not getattr(self.tanim, 'hesap_var', True):
                self.asamalar.append(
                    'hesapsız sayfa: hesap/3B/FEA/Merkez adımları ATLANDI '
                    '(sayfada yoklar)')
                # ÖH D27 / OH-D25-02(a) — HESAPSIZ ≠ TUVALSİZ.
                # ``/launch-site``in küresi hesap akışına bağlı değildir ama
                # sayfanın ASIL yüzeyidir; eski dal onu da atlıyordu.
                if getattr(self.tanim, 'tuval_secici', ''):
                    tuval_ham, piksel = self._beyanli_tuvali_olc(goruntuler)
                metin = self.p.evaluate(JS_SAYFA_METNI)
                try:
                    yerlesim = self.p.evaluate(JS_YERLESIM, {
                        'sinir': esikler.ORTUSME_TARAMA_UST_SINIRI,
                        'min_alan': esikler.ORTUSME_MIN_KESISIM_PX2,
                        'oran': esikler.ORTUSME_MIN_KESISIM_ORANI,
                        'ornek': esikler.RAPOR_ORNEK_UST_SINIRI,
                    }) or {}
                except Exception as hata:
                    yerlesim = {'hata': '%s: %s' % (type(hata).__name__,
                                                    _kisalt(hata, 200))}
                raise _HesapsizSayfaBitti()

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

            # FEA panelleri 3B ölçümden SONRA koşturulur: koşum sayfaya
            # büyük Plotly kapları ekler ve düzeni değiştirir; tuval
            # anlık görüntüsü ondan etkilenmesin. Sayfa metni ise FEA'dan
            # SONRA okunur — böylece sızıntı taraması FEA panellerinin
            # bastığı metni de kapsar.
            fea = self._fea_panellerini_kostur()
            # Analiz Merkezi FEA panellerinden SONRA, sayfa metni
            # okunmadan ÖNCE koşturulur: kiracının bastığı her cümle
            # sızıntı taramasına da girsin (``[object Object]``/NaN
            # ekranın hangi köşesinde olursa olsun yakalansın).
            merkez = self._merkezi_kostur()

            metin = self.p.evaluate(JS_SAYFA_METNI)
            # Yerleşim en SON ölçülür: FEA/Merkez koşumları sayfaya kap
            # eklediği için taşma ve örtüşme, kullanıcının en dolu ekranda
            # göreceği hâliyle ölçülmüş olur. Ölçüm istisnası akışı KESMEZ;
            # hüküm katmanı boş ölçümü fail-closed kırmızıya çevirir.
            try:
                yerlesim = self.p.evaluate(JS_YERLESIM, {
                    'sinir': esikler.ORTUSME_TARAMA_UST_SINIRI,
                    'min_alan': esikler.ORTUSME_MIN_KESISIM_PX2,
                    'oran': esikler.ORTUSME_MIN_KESISIM_ORANI,
                    'ornek': esikler.RAPOR_ORNEK_UST_SINIRI,
                }) or {}
            except Exception as hata:
                yerlesim = {'hata': '%s: %s' % (type(hata).__name__,
                                                _kisalt(hata, 200))}
        except _HesapsizSayfaBitti:
            # Kusur değil, akışın DOĞAL sonu: hesapsız sayfanın ölçülecek
            # her şeyi ölçüldü. ``self.hatalar`` boş kalır, dolayısıyla
            # ``akis_tamam`` denetimi yeşildir.
            pass
        except Exception as hata:
            self.hatalar.append('%s: %s' % (type(hata).__name__, _kisalt(hata, 600)))
            self.asamalar.append('AKIŞ KESİLDİ')
        finally:
            try:
                self._tam_sayfa_yakala(goruntuler)
            except Exception as hata:
                self.hatalar.append('tam sayfa görüntüsü alınamadı: %s'
                                    % _kisalt(hata, 200))

        return self._rapor(sureler, viz, tuval_ham, piksel, metin,
                           plume_baslatma, goruntuler, fea, merkez, yerlesim)

    def _beyanli_tuvali_olc(self, goruntuler: Dict[str, Any]):
        """Sayfanın BEYAN ETTİĞİ tuvalini ölçer (ÖH D27 / OH-D25-02a).

        ``(tuval_ham, piksel)`` döner. Hesap akışı olmayan bir sayfanın
        tuvali de kullanıcının gördüğü yüzeydir: ``/launch-site``in küresi
        siyah/boş çıksa tur bunu HİÇ görmüyordu (ölçüldü: ``tuval_kaynagi``
        None, ``piksel`` {}).

        FAIL-CLOSED: seçici beyan edildiyse tuvalin bulunamaması, hazır
        olmaması ya da okunamaması KIRMIZIDIR — beyan edilmiş bir yüzeyin
        ölçülememesi "sorun yok" değildir. Ölçüm istisnası akışı KESMEZ,
        gerekçe ``tuval_ham['hata']``ya yazılır ve ``tuval_denetimi`` onu
        basar.
        """
        secici = self.tanim.tuval_secici
        tuval_ham: Dict[str, Any] = {'kaynak': 'beyanlı seçici: %s' % secici}
        try:
            hedef = self.p.locator(secici).first
            hedef.wait_for(state='visible',
                           timeout=esikler.VIZ_KURULUM_ZAMAN_ASIMI_MS)
            kosul = getattr(self.tanim, 'tuval_hazir_kosulu', '')
            if kosul:
                # Sabit bir uyku YOK: çizimin GERÇEKTEN başladığı, sayfanın
                # kendi ölçütüyle beklenir.
                self.p.wait_for_function(
                    kosul, timeout=esikler.VIZ_KURULUM_ZAMAN_ASIMI_MS)
                self.asamalar.append('tuval hazır ölçütü sağlandı: %s' % kosul)
            ham = self.p.evaluate(JS_BEYANLI_TUVAL, {'secici': secici}) or {}
            tuval_ham.update(ham)
            if ham.get('hata'):
                return tuval_ham, {'hata': ham['hata']}
            # Pikseller BİRLEŞTİRİLMİŞ kareden okunur (bkz. JS_BEYANLI_TUVAL
            # notu: WebGL tuvalinde toDataURL boş gelir).
            baytlar = hedef.screenshot(type='png')
            tuval_ham['kaynak'] = ('eleman ekran görüntüsü (%s), %sx%s'
                                   % (secici, ham.get('tuval_genislik'),
                                      ham.get('tuval_yukseklik')))
            self.asamalar.append(
                'beyanlı tuval ölçüldü (%s): %sx%s'
                % (secici, ham.get('tuval_genislik'), ham.get('tuval_yukseklik')))
        except Exception as hata:
            tuval_ham['hata'] = '%s: %s' % (type(hata).__name__,
                                            _kisalt(hata, 200))
            self.asamalar.append('beyanlı tuval ÖLÇÜLEMEDİ (%s): %s'
                                 % (secici, tuval_ham['hata']))
            return tuval_ham, {'hata': tuval_ham['hata']}
        if baytlar:
            yol = os.path.join(self.cikti_dizini, '%s_tuval.png' % self.tanim.ad)
            with open(yol, 'wb') as dosya:
                dosya.write(baytlar)
            goruntuler['tuval'] = yol
        return tuval_ham, denetimler.piksel_olcumu(baytlar)

    def _sayfa_olc(self):
        """(genişlik, yükseklik) — belge kaydırma boyu; okunamazsa (0, 0)."""
        try:
            olcu = self.p.evaluate(
                '() => ({ g: Math.max(document.documentElement.scrollWidth,'
                ' document.body ? document.body.scrollWidth : 0),'
                ' y: Math.max(document.documentElement.scrollHeight,'
                ' document.body ? document.body.scrollHeight : 0) })')
            return int(olcu['g']), int(olcu['y'])
        except Exception:
            return 0, 0

    def _sayfa_boyunu_durult(self):
        """Boy iki ardışık ölçümde aynı kalana dek bekler (üst sınırlı).

        Süre dolarsa son ölçüm döner; durulmayan sayfa dilim denetiminde
        zaten kırmızı çıkar — bekleme kapıyı gevşetmez, yalnız ölçümün
        hareketli bir hedefe yapılmasını önler.
        """
        g, y = self._sayfa_olc()
        bitis = time.monotonic() + esikler.SAYFA_DURULMA_UST_SINIRI_S
        while time.monotonic() < bitis:
            self.p.wait_for_timeout(esikler.SAYFA_DURULMA_ARALIGI_MS)
            g2, y2 = self._sayfa_olc()
            if (g2, y2) == (g, y):
                return g, y
            g, y = g2, y2
        return g, y

    def _tam_sayfa_yakala(self, goruntuler: Dict[str, Any]) -> None:
        """Tam sayfa kanıtı — tavanı aşan sayfada DİLİMLİ yakalama.

        ÖH D24 · OH-D21-11. ÖLÇÜLDÜ (D20 · P17B1-05 ve D21 · OH-D21-11):
        ``full_page=True`` ile istenen PNG, sayfa Chromium'un 16.384 px'lik
        tek-kare tavanını aşınca İSTENEN yükseklikte üretilir ama tavanı
        aşan bant üst bandın BİREBİR tekrarıdır (maks piksel farkı 0).
        ``/formulas`` 40.604 px: sayfanın %59,6'sı hiçbir koşumda
        görüntülenmiyordu. D20 bunu doğru biçimde SAHTE KANIT sayıp kapıyı
        kapattı; ama o gün kapı 6 sayfanın 4'ünde kırmızı kaldı ve turun
        tek insan-okur kanıtı ÜRETİLEMEZ oldu.

        Çözüm kapıyı gevşetmek değil, kanıtı GERÇEKTEN üretmektir: sayfa
        tavanı aşıyorsa görüntü, her biri tavanın altında kalan ardışık
        DİLİMLER hâlinde alınır (``clip`` sayfa koordinatlarındadır, yani
        her dilim sayfanın FARKLI bir bandıdır — tekrar yok). Dilimler
        bitişiktir ve toplamları sayfanın tamamını kaplar; denetim bunu
        ``tam_sayfa_dilimleri`` üstünden ölçer.

        Fail-closed: sayfa boyu okunamazsa dilimleme yapılmaz, tek kare
        alınır ve denetim eski yolla (yükseklik ⟷ tavan) hüküm verir.
        """
        tavan = esikler.CHROMIUM_TEK_KARE_TAVANI_PX
        # v3.0.0 (15 Eki) — sayfa boyu DURULMADAN ölçülüyordu. Ölçüldü
        # (tur1): son dilim hibritte 7491 istendi 7487 üretildi, katıda
        # 5344 → 5170, sıvıda 4111 → 3819 — panel koşumlarının ardından
        # kaplar yakalama sırasında hâlâ boy değiştiriyordu. Kapı
        # gevşetilmez: boy iki ardışık ölçümde aynı kalana dek beklenir.
        sayfa_g, sayfa_y = self._sayfa_boyunu_durult()
        goruntuler['sayfa_boyu_px'] = (
            {'genislik': sayfa_g, 'yukseklik': sayfa_y} if sayfa_y > 0 else None)

        if sayfa_y <= 0 or sayfa_y <= tavan:
            yol = os.path.join(self.cikti_dizini, '%s_tam.png' % self.tanim.ad)
            self.p.screenshot(path=yol, full_page=True)
            goruntuler['tam_sayfa'] = yol
            # P17B1-05: kanıtın KENDİSİ ölçülür, yalnız yolu yazılmaz.
            goruntuler['tam_sayfa_px'] = png_boyutu(yol)
            goruntuler['tam_sayfa_dilimleri'] = None
            return

        # Dilim adımı: tavanın altında kalsın diye tavanın kendisi değil,
        # ondan bir miktar küçük bir adım seçilir; cihaz piksel oranı 1'den
        # büyükse üretilen PNG istenen CSS yüksekliğinden BÜYÜK olur ve tam
        # tavan adımı tavanı aşardı. Ölçek `scale='css'` ile sabitlenir,
        # adım da güvenli tarafta tutulur.
        adim = tavan // 2
        # Yakalama sırasında boy yine değişirse dilim kümesi BÜTÜNÜYLE
        # yeniden alınır (en çok DILIM_DENEME_SAYISI kez); son denemenin
        # kümesi olduğu gibi denetime gider — uyuşmuyorsa kapı kırmızıdır.
        # Her deneme rapora yazılır: kaç kez, hangi boylarla.
        denemeler = []
        dilimler = []
        for _deneme in range(esikler.DILIM_DENEME_SAYISI):
            if denemeler:
                sayfa_g, sayfa_y = self._sayfa_boyunu_durult()
                goruntuler['sayfa_boyu_px'] = (
                    {'genislik': sayfa_g, 'yukseklik': sayfa_y}
                    if sayfa_y > 0 else None)
            dilimler = []
            i = 0
            y0 = 0
            while y0 < sayfa_y:
                h = min(adim, sayfa_y - y0)
                yol = os.path.join(self.cikti_dizini,
                                   '%s_tam_d%02d.png' % (self.tanim.ad, i))
                self.p.screenshot(path=yol, full_page=True, scale='css',
                                  clip={'x': 0, 'y': y0,
                                        'width': sayfa_g, 'height': h})
                dilimler.append({'yol': yol, 'y0': y0, 'istenen_yukseklik': h,
                                 'px': png_boyutu(yol),
                                 'sha256': dosya_sha256(yol)})
                y0 += h
                i += 1
            _g, sonra_y = self._sayfa_olc()
            kisa = [d['yol'] for d in dilimler
                    if (d['px'] or {}).get('yukseklik') != d['istenen_yukseklik']]
            denemeler.append({'sayfa_y_once': sayfa_y, 'sayfa_y_sonra': sonra_y,
                              'kisa_dilimler': kisa})
            if not kisa and sonra_y == sayfa_y:
                break
        goruntuler['tam_sayfa_denemeleri'] = denemeler
        goruntuler['tam_sayfa'] = dilimler[0]['yol'] if dilimler else None
        goruntuler['tam_sayfa_px'] = dilimler[0]['px'] if dilimler else None
        goruntuler['tam_sayfa_dilimleri'] = dilimler

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

    # -- FEA panelleri ----------------------------------------------------
    def _fea_yapilandirmasi(self, tanim) -> Dict[str, Any]:
        """Sayfa içi betiklere geçirilen ayar sözlüğü (tek kaynak)."""
        return {
            'panel': tanim.panel_kimligi,
            'api': tanim.api_adi,
            'mesgul': tanim.mesgul_kimligi,
            'cip': tanim.cip_kimligi,
            'rozet': tanim.rozet_kimligi,
            'cizimler': list(tanim.cizim_kimlikleri),
            'min_kenar': esikler.FEA_CIZIM_MIN_KENAR_PX,
        }

    def _fea_panellerini_kostur(self) -> Dict[str, Any]:
        """Sayfanın FEA panellerini sırayla koşturur ve ölçer.

        Bir panelin patlaması turu KESMEZ: istisna o panelin ölçümüne
        yazılır ve hüküm ``denetimler.py``de verilir. Böylece hibritte
        termal panel çökse bile yapısal panelin ölçümü elde kalır.
        """
        sonuc: Dict[str, Any] = {}
        for tanim in getattr(self.tanim, 'fea_panelleri', ()):
            try:
                sonuc[tanim.ad] = self._tek_fea_paneli(tanim)
            except Exception as hata:
                sonuc[tanim.ad] = {
                    'panel': tanim.panel_kimligi, 'api': tanim.api_adi,
                    'panel_var': None, 'yuk_var': False, 'asama': 'olcum_hatasi',
                    'ayrinti': '%s: %s' % (type(hata).__name__, _kisalt(hata, 300)),
                }
                self.asamalar.append('FEA paneli ölçülemedi (%s): %s'
                                     % (tanim.ad, _kisalt(hata, 160)))
        return sonuc

    def _tek_fea_paneli(self, tanim) -> Dict[str, Any]:
        cfg = self._fea_yapilandirmasi(tanim)
        olcum = self.p.evaluate(JS_FEA_PANEL_DURUMU, cfg) or {}
        olcum['ad'] = tanim.ad
        olcum['kosum_secicisi'] = tanim.kosum_secicisi
        olcum['zaman_asimi_ms'] = tanim.kosum_zaman_asimi_ms
        olcum['basladi'] = False
        olcum['_dayanak'] = {
            'yuk_var': 'window.%s.payload != null' % tanim.api_adi,
            'yuk_ozeti': ('payload\'ın skaler/hüküm blokları (diziler atılır) '
                          '— rozet⟷yük çaprazının ham girdisi'),
            'panel_gorunur': ('getComputedStyle(#%s).display + kutunun sıfır '
                              'olmaması' % tanim.panel_kimligi),
            'cizimler': ('kap görünürlüğü + .js-plotly-plot sınıfı + kap '
                         'içindeki svg/canvas düğüm sayısı'),
            'rozetler': '#%s içindeki [data-badge] kutuları' % tanim.rozet_kimligi,
            'kosum_s': 'düğmeye basımdan meşgul göstergesinin kapanmasına',
        }
        if not olcum.get('panel_var'):
            olcum['asama'] = 'panel_yok'
            self.asamalar.append('FEA paneli yok: #%s' % tanim.panel_kimligi)
            return olcum
        if not olcum.get('panel_gorunur'):
            olcum['asama'] = 'panel_gorunmez'
            self.asamalar.append('FEA paneli görünmüyor: #%s' % tanim.panel_kimligi)
            return olcum

        dugme = self.p.locator(tanim.kosum_secicisi).first
        if dugme.count() == 0:
            olcum['asama'] = 'dugme_yok'
            self.asamalar.append('FEA koşum düğmesi yok: %s' % tanim.kosum_secicisi)
            return olcum

        t0 = time.time()
        dugme.click()
        self.asamalar.append('FEA koşum düğmesine basıldı (%s): %s'
                             % (tanim.ad, tanim.kosum_secicisi))
        try:
            self.p.wait_for_function(JS_FEA_MESGUL, arg=cfg,
                                     timeout=esikler.FEA_BASLAMA_ZAMAN_ASIMI_MS)
            olcum['basladi'] = True
        except Exception:
            # Koşum ya hiç başlamadı (ör. sayfada motor sonucu yok) ya da
            # ölçüm penceresinden hızlı bitti. İkisi de burada AYIRT
            # EDİLMEZ; hüküm yükün yayımlanmasına bakar.
            self.asamalar.append('FEA meşgul göstergesi görülmedi (%s)' % tanim.ad)
        try:
            self.p.wait_for_function(JS_FEA_BITTI, arg=cfg,
                                     timeout=tanim.kosum_zaman_asimi_ms)
            olcum['asama'] = 'tamam'
        except Exception:
            olcum['asama'] = 'zaman_asimi'
            self.asamalar.append('FEA koşumu zaman aşımına uğradı (%s, %d ms)'
                                 % (tanim.ad, tanim.kosum_zaman_asimi_ms))
        olcum['kosum_s'] = time.time() - t0

        son = self.p.evaluate(JS_FEA_PANEL_DURUMU, cfg) or {}
        son.update({k: v for k, v in olcum.items() if k not in son})
        self.asamalar.append(
            'FEA koşumu bitti (%s): yük=%s, %d rozet, %.1f s'
            % (tanim.ad, bool(son.get('yuk_var')), son.get('rozet_sayisi', 0),
               olcum['kosum_s']))
        return son

    # -- Analiz Merkezi ---------------------------------------------------
    def _merkez_yapilandirmasi(self) -> Dict[str, Any]:
        """Çerçeve betiklerine geçirilen ayar sözlüğü (tek kaynak)."""
        return {
            'panel': esikler.MERKEZ_PANEL_KIMLIGI,
            'sutunlar': list(esikler.MERKEZ_SUTUN_KIMLIKLERI),
            'gecmis': esikler.MERKEZ_GECMIS_KIMLIGI,
            'dugme': esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI,
            'durum': esikler.MERKEZ_DURUM_KIMLIGI,
        }

    def _merkez_kiraci_yapilandirmasi(self, kiraci) -> Dict[str, Any]:
        return {
            'kok': esikler.MERKEZ_GORUNTULEYICI_KOKU,
            'cizim_secici': kiraci.cizim_secicisi,
            'rozet_secici': kiraci.rozet_secicisi,
            'rozet_ozniteligi': kiraci.rozet_ozniteligi,
            'dugme': esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI,
            'durum': esikler.MERKEZ_DURUM_KIMLIGI,
            'min_kenar': esikler.MERKEZ_CIZIM_MIN_KENAR_PX,
            # ÖH D23 / P10B3-03 — yük sözleşmesi kiracıdan gelir; JS gövdesi
            # artık hiçbir kiracının alan adını BİLMEZ.
            'yuk_anahtari': kiraci.yuk_anahtari,
            'yuk_alanlari': [list(a) for a in kiraci.yuk_alanlari],
        }

    def _merkezi_kostur(self) -> Dict[str, Any]:
        """Analiz Merkezi'ni ölçer ve kiracılarını sırayla koşturur.

        Bir kiracının patlaması turu KESMEZ: istisna o kiracının ölçümüne
        yazılır, çerçeve ölçümü elde kalır ve hüküm ``denetimler.py``de
        verilir.
        """
        if not getattr(self.tanim, 'merkez_var', False):
            return {}
        sonuc: Dict[str, Any] = {'cerceve': None, 'kiracilar': {}}
        cfg = self._merkez_yapilandirmasi()
        try:
            sonuc['cerceve'] = self.p.evaluate(JS_MERKEZ_CERCEVE, cfg) or {}
            self.asamalar.append(
                'Analiz Merkezi ölçüldü: panel=%s, %d satır'
                % (bool(sonuc['cerceve'].get('panel_var')),
                   sonuc['cerceve'].get('satir_sayisi', 0)))
        except Exception as hata:
            sonuc['cerceve'] = {'panel': esikler.MERKEZ_PANEL_KIMLIGI,
                                'panel_var': None, 'panel_gorunur': False,
                                'olcum_hatasi': '%s: %s'
                                % (type(hata).__name__, _kisalt(hata, 300))}
            self.asamalar.append('Analiz Merkezi ölçülemedi: %s'
                                 % _kisalt(hata, 160))
        for kiraci in getattr(self.tanim, 'merkez_kiracilari', ()):
            try:
                sonuc['kiracilar'][kiraci.ad] = self._tek_merkez_kiracisi(
                    kiraci, sonuc['cerceve'] or {})
            except Exception as hata:
                sonuc['kiracilar'][kiraci.ad] = {
                    'ad': kiraci.ad, 'kok_var': False,
                    'satir_anahtari': kiraci.satir_anahtari,
                    'asama': 'olcum_hatasi',
                    'ayrinti': '%s: %s' % (type(hata).__name__,
                                           _kisalt(hata, 300)),
                }
                self.asamalar.append('Merkez kiracısı ölçülemedi (%s): %s'
                                     % (kiraci.ad, _kisalt(hata, 160)))
        return sonuc

    def _tek_merkez_kiracisi(self, kiraci, cerceve: Dict[str, Any]) -> Dict[str, Any]:
        """Kiracıyı SEÇER, koşturur ve koşum sonrası ekranı ölçer.

        Alanlara DOKUNULMAZ: kart, motorun kendi sonucundan önerilen
        değerlerle ve panelin kendi çözünürlük varsayılanıyla koşar —
        kullanıcının gördüğü yol budur.
        """
        cfg = self._merkez_kiraci_yapilandirmasi(kiraci)
        olcum: Dict[str, Any] = {
            'ad': kiraci.ad,
            'satir_anahtari': kiraci.satir_anahtari,
            'satir_secicisi': kiraci.satir_secicisi,
            'zaman_asimi_ms': kiraci.kosum_zaman_asimi_ms,
            'basladi': False,
            'kok_var': False,
            '_dayanak': {
                'son_kosum': 'window.AnalysisCenter.history() son kaydı',
                'yuk': 'aynı kaydın data.cfd bloğundan okunan beyan alanları',
                'cizimler': ('#%s içindeki %s kapları: görünürlük + '
                             '.js-plotly-plot + svg düğüm sayısı'
                             % (esikler.MERKEZ_GORUNTULEYICI_KOKU,
                                kiraci.cizim_secicisi)),
                'rozetler': '%s kutularının metni ve %s değeri'
                            % (kiraci.rozet_secicisi, kiraci.rozet_ozniteligi),
                'kosum_s': 'düğmeye basımdan geçmişe kayıt düşmesine',
            },
        }
        satir = None
        for s in (cerceve.get('satirlar') or []):
            if s.get('anahtar') == kiraci.satir_anahtari:
                satir = s
                break
        if not satir:
            olcum['asama'] = 'satir_yok'
            self.asamalar.append('Merkez satırı ağaçta yok: %s'
                                 % kiraci.satir_anahtari)
            return olcum
        olcum['satir_durumu'] = satir.get('durum')
        olcum['satir_nedeni'] = satir.get('neden')
        if satir.get('durum') != 'ready':
            olcum['asama'] = 'satir_hazir_degil'
            self.asamalar.append('Merkez satırı koşuma hazır değil (%s → %s)'
                                 % (kiraci.satir_anahtari, satir.get('durum')))
            return olcum

        satir_dugmesi = self.p.locator(kiraci.satir_secicisi).first
        if satir_dugmesi.count() == 0:
            olcum['asama'] = 'satir_yok'
            return olcum
        satir_dugmesi.click()
        self.asamalar.append('Merkez satırı seçildi: %s' % kiraci.satir_secicisi)

        kosum_secici = '#' + esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI
        kosum_dugmesi = self.p.locator(kosum_secici).first
        try:
            kosum_dugmesi.wait_for(
                state='visible',
                timeout=esikler.MERKEZ_KOSUM_BASLAMA_ZAMAN_ASIMI_MS)
        except Exception:
            olcum['asama'] = 'dugme_yok'
            self.asamalar.append('Merkez koşum düğmesi kurulmadı: %s'
                                 % kosum_secici)
            return olcum

        gecmis_esigi = self.p.evaluate(JS_MERKEZ_GECMIS_UZUNLUGU)
        gecmis_esigi = gecmis_esigi if isinstance(gecmis_esigi, int) else 0
        olcum['gecmis_esigi'] = gecmis_esigi
        t0 = time.time()
        kosum_dugmesi.click()
        self.asamalar.append('Merkez koşum düğmesine basıldı (%s)' % kiraci.ad)
        try:
            self.p.wait_for_function(
                JS_MERKEZ_MESGUL, arg=cfg,
                timeout=esikler.MERKEZ_KOSUM_BASLAMA_ZAMAN_ASIMI_MS)
            olcum['basladi'] = True
        except Exception:
            # Koşum ya hiç başlamadı (eksik zorunlu alan → istek gönderilmez)
            # ya da ölçüm penceresinden hızlı bitti. İkisi burada AYIRT
            # EDİLMEZ; hüküm koşum KAYDINA bakar.
            self.asamalar.append('Merkez meşgul göstergesi görülmedi (%s)'
                                 % kiraci.ad)
        bitti_cfg = dict(cfg)
        bitti_cfg['gecmis_esigi'] = gecmis_esigi
        try:
            self.p.wait_for_function(JS_MERKEZ_KOSUM_BITTI, arg=bitti_cfg,
                                     timeout=kiraci.kosum_zaman_asimi_ms)
            olcum['asama'] = 'tamam'
        except Exception:
            olcum['asama'] = 'zaman_asimi'
            self.asamalar.append('Merkez koşumu zaman aşımına uğradı (%s, %d ms)'
                                 % (kiraci.ad, kiraci.kosum_zaman_asimi_ms))
        olcum['kosum_s'] = time.time() - t0

        son = self.p.evaluate(JS_MERKEZ_KIRACI, cfg) or {}
        son.update({k: v for k, v in olcum.items() if k not in son})
        son_kosum = son.get('son_kosum') or {}
        self.asamalar.append(
            'Merkez koşumu bitti (%s): kayıt=%s, %d çizim, %d rozet, %.1f s'
            % (kiraci.ad, son_kosum.get('ok'), son.get('cizim_sayisi', 0),
               son.get('rozet_sayisi', 0), olcum['kosum_s']))
        return son

    # -- rapor ------------------------------------------------------------
    def _rapor(self, sureler, viz, tuval_ham, piksel, metin, plume_baslatma,
               goruntuler, fea=None, merkez=None,
               yerlesim=None) -> Dict[str, Any]:
        akis_tamam = not self.hatalar
        hesap_var = getattr(self.tanim, 'hesap_var', True)
        liste = [
            denetimler.Denetim(
                ad='akis_tamam', gecti=akis_tamam,
                ozet=('gezinti akışı kesintisiz tamamlandı' if akis_tamam
                      else 'gezinti akışı kesildi: %s' % '; '.join(self.hatalar)),
                dayanak='gezinti adımlarının istisna kaydı',
                olcum={'asamalar': self.asamalar, 'hatalar': self.hatalar},
                esik={}),
        ]
        # ÖH D21 / P17B1-16: 3B tuval ve egzoz denetimleri YALNIZ hesap
        # akışı olan sayfalarda üretilir. Hesapsız sayfada bunları üretmek
        # HAYALET DENETİM olurdu: sayfada 3B sahne yok, "tuval boş" hükmü
        # kusuru olmayan sayfayı kırmızıya boyar ve kapıyı okunamaz kılar.
        # ÖH D27 / OH-D25-02(a): tuval denetimi artık "hesap akışı var mı"
        # sorusuna değil "bu sayfanın ÖLÇÜLECEK bir tuvali var mı" sorusuna
        # bağlı. ``/launch-site`` hesapsızdır ama küresi vardır; egzoz
        # (plume) denetimi ise hesap akışına bağlı kalır — orada gerçekten
        # yanma yoktur.
        if hesap_var or getattr(self.tanim, 'tuval_secici', ''):
            liste.append(denetimler.tuval_denetimi(
                piksel, kaynak=tuval_ham.get('kaynak', '')))
        if hesap_var:
            liste.append(denetimler.plume_denetimi(
                viz, piksel,
                suresiz_beyanli=getattr(self.tanim, 'suresiz_egzoz_beyanli',
                                        False)))
        liste.extend([
            denetimler.konsol_denetimi(self.kayitlar),
            denetimler.sizinti_denetimi(metin),
            denetimler.tam_sayfa_goruntusu_denetimi(goruntuler),
        ])
        liste.extend(denetimler.yerlesim_denetimleri(yerlesim))
        fea = fea or {}
        for tanim in getattr(self.tanim, 'fea_panelleri', ()):
            liste.extend(denetimler.fea_denetimleri(tanim, fea.get(tanim.ad)))
        merkez = merkez or {}
        if hesap_var:
            liste.extend(denetimler.merkez_denetimleri(self.tanim, merkez))
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
                'fea': fea,
                'merkez': merkez,
                'plume_baslatma': plume_baslatma,
                'yerlesim': yerlesim or {},
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

    ``(tarayici, kullanilan_kanal, denemeler)`` döner.

    ÖH D20 · P17B1-07 — SESSİZ DÜŞÜŞ YOK. Paketli Chromium açılamayıp tur
    sistem Chrome'una düştüğünde bu eskiden hiçbir yere yazılmıyordu: künye
    yalnız KAZANAN kanalı taşıyordu, özet ise tarayıcıyı hiç anmıyordu.
    Artık her deneme (açıldı/açılamadı + hata) kayda geçer; ``denetimler.
    tarayici_denetimi`` bu kaydın varlığını ŞART koşar (fail-closed).
    """
    sira = [kanal] if (kanal and kanal != 'auto') else list(KANAL_SIRASI)
    denemeler: List[Dict[str, Any]] = []
    hatalar: List[str] = []
    for k in sira:
        baslat: Dict[str, Any] = {'headless': not basli}
        if k:
            baslat['channel'] = k
        ad = k or PAKETLI_KANAL_ADI
        try:
            tarayici = pw.chromium.launch(**baslat)
            denemeler.append({'kanal': ad, 'acildi': True, 'hata': None})
            return tarayici, ad, denemeler
        except Exception as hata:
            metin = _kisalt(hata, 160)
            denemeler.append({'kanal': ad, 'acildi': False, 'hata': metin})
            hatalar.append('%s -> %s' % (ad, metin))
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
        tarayici, kullanilan, denemeler = _tarayici_ac(pw, kanal, basli)
        kunye = {'motor': 'chromium', 'kanal': kullanilan,
                 'surum': tarayici.version, 'basli': bool(basli),
                 'istenen_kanal': kanal or 'auto',
                 'denemeler': denemeler,
                 '_dayanak': 'playwright Browser.version + açılış denemeleri'}
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
