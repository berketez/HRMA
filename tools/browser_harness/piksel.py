"""ÖH D37 · OH-D33-45 — OLUŞMUŞ PİKSELİN ölçüm betiği.

Kör nokta (defter OH-D33-45): iskelenin denetimleri ``[object Object]`` /
``undefined`` / ``NaN`` sızıntısına, boş tuvale, konsol hatasına ve rozet
imzalarına bakıyordu. Kılavuz ekran karelerinden çıkan üç kusurun hiçbiri
bu sınıflardan değildi:

1. **Yarım çeviri** — çeviri anahtarı var, sözlük bekçisi yeşil; İngilizce
   olan şey Python'un doldurduğu yer tutucunun İÇERİĞİ.
2. **Ondalık karışıklığı** — her mesaj tek başına kusursuz; kusur ancak
   aynı paneldeki mesajlar ARASINDA tutarsızlık olarak var.
3. **Künye taşması** — tamamen geometrik; depoda geometri ölçen yoktu.

Bu modül üçünün HAM ölçümünü sayfanın içinde tek geçişte alır ve piksel
turunun gezintisini (``kombinasyonu_gez`` / ``piksel_turu_kos``) yürütür.
Piksel hükümleri burada VERİLMEZ (``denetimler.py::piksel_denetimleri``;
burada yalnız gezintinin kendi ``akis_tamam`` kaydı kurulur), eşik ve
muafiyetler burada YAZILMAZ (``esikler.py``): betik yapılandırmasını
``piksel_yapilandirmasi()``den alır. Komut satırı: ``run_piksel.py``.

Neden ``tur.py`` içinde değil: ``tests/support/sahte_sayfa.py`` ikizi
``tur`` modülündeki her ``JS_*`` sabiti için senaryoda bir cevap şart
koşar (``test_d24_altyapi_a1.py::test_turun_her_JS_sabiti_...``). Piksel
ölçümü İSTEĞE BAĞLI bir tur kipidir; varsayılan kapı turu bu betiği hiç
koşturmaz. Betik ayrı modülde durduğu için ikizin sözleşmesi bozulmaz,
varsayılan tur birebir aynı kalır.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.browser_harness import denetimler, esikler

#: Örnek projenin sayfaya YÜKLENDİĞİNİ söyleyen koşul. ``?project=<ad>``
#: ile açılan sayfada ``project_bar.js::loadIntoPage`` projeyi uçtan alır,
#: alanlara yazar ve ``state.savedName``i projenin adına çeker; ürün bu
#: durumu ``window.HRMAProjectBar._state`` kancasıyla açar
#: (project_bar.js:1233-1247). Yükleme sonuç HESAPLAMAZ — hesap düğmesine
#: yine basılır. Ad argümanla geçer, betikte sabit YOKTUR.
PROJE_YUKLENDI_KOSULU = """
(ad) => {
  const P = window.HRMAProjectBar;
  return !!(P && P._state && P._state.savedName === ad);
}
"""

#: Sayfa içi ölçüm. Tek geçişte dört şey toplanır:
#:
#: * ``metinler`` — görünür her metin BİRİMİ (a2): satır içi olmayan her
#:   öğenin BLOK METNİ — kendi metin düğümleri + satır içi torunlarının
#:   metni, belge sırasıyla (``<p>The pressure <b>is</b> …</p>`` tek
#:   cümle); satır içi olmayan çocuk, ``<br>`` ve SVG yerine dizi kesici.
#:   Birimin seçici yolu, en yakın panel kimliği (``p``), BÜTÜN panel/kart
#:   ataları (``pp``, a2 (g)), muafiyet adı ve uyarı kabında olup olmadığı.
#:   Birimin içindeki muaf satır içi parça (``<code>``, künye) ayrı bir
#:   muaf kayıt olarak sayılır. SVG ``<text>`` içerikleri (Plotly eksen/
#:   lejant) ve seçili ``<select>`` etiketi de ayrı türle girer. DİL ve
#:   ONDALIK denetiminin girdisi. Görünürlük METİN DÜĞÜMÜNÜN kendi satır
#:   kutularıyla ölçülür ve kırpma dikdörtgeniyle kesiştirilir (a2 (c)).
#: * ``tasmalar`` — metin taşıyan her blok kutusu için
#:   ``scrollWidth > clientWidth + tol``; sınıfı ``overflow-x``ten:
#:   görünür → 'tasan', gizli/kırpık → 'kesilen' (+ title/aria-label var
#:   mı), kaydırmalı → 'kaydirmali'.
#: * ``ebeveyn_asimlari`` — metin taşıyan blok/satır-içi-blok öğenin
#:   kutusunun EBEVEYN kutusunu yatayda aşması (mutlak/sabit konumlu
#:   öğeler hariç: onlar tasarım gereği akış dışıdır ve sayfa kaydırması
#:   suçlu listesinde ayrıca görünür).
#: * ``sayfa`` — ``documentElement.scrollWidth`` ⟷ ``innerWidth`` /
#:   ``clientWidth`` ve sağ kenarı görüntü alanını aşan EN DERİN öğeler
#:   (``visibility:hidden`` olanlar ayrıca işaretli: DV-TOOLTIP deseni —
#:   gizli ipucu yerleşimde yer kaplayıp kaydırma yaratır).
#:
#: Görünürlük ``JS_YERLESIM`` ile aynı ilkeyle ölçülür: ``display:none``
#: alt ağacı ve ``opacity:0`` atlanır; ``visibility:hidden`` öğenin KENDİ
#: metni atlanır ama çocuklarına inilir (CSS'te çocuk görünürlüğü geri
#: açabilir); kapalı ``<details>`` yalnız ``<summary>``sini gösterir;
#: atalardan gelen kırpma dikdörtgeni (overflow gizli/kaydırmalı) yaprak
#: kutusuyla kesiştirilir — kesişim boşsa metin EKRANDA değildir.
JS_PIKSEL = """
(c) => {
  try {
    const de = document.documentElement;
    const tol = c.tolerans_px;
    const ebTol = c.ebeveyn_tolerans_px;
    const KIRPAN = new Set(['hidden', 'clip', 'auto', 'scroll']);
    const ATLA = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'CANVAS',
                          'OPTION', 'OPTGROUP', 'DATALIST', 'IFRAME', 'VIDEO',
                          'AUDIO', 'IMG', 'INPUT', 'TEXTAREA']);
    const duz = (t) => (t || '').replace(/\\s+/g, ' ').trim();
    const KESICI = c.kesici;
    const kirp = (t, n) => (t.length > n ? t.slice(0, n) + '…' : t);
    const parca = (el) => {
      let s = el.tagName.toLowerCase();
      if (el.id) return s + '#' + el.id;
      const k = Array.from(el.classList || []).slice(0, 2);
      if (k.length) s += '.' + k.join('.');
      return s;
    };
    const yol = (el) => {
      const p = [];
      let e = el, n = 0;
      while (e && e.nodeType === 1 && e !== document.body && n < 6) {
        p.unshift(parca(e));
        if (e.id) break;
        e = e.parentElement; n++;
      }
      return p.join(' > ');
    };
    const muafAdi = (el) => {
      for (const m of c.muaf_seciciler) {
        try { if (el.closest(m[1])) return m[0]; } catch (e) { /* geçersiz seçici */ }
      }
      return '';
    };
    const panelNo = new Map();
    const panelAdi = (p) => {
      if (!panelNo.has(p)) panelNo.set(p, panelNo.size + 1);
      return 'P' + panelNo.get(p) + ' ' + yol(p);
    };
    const enYakinPanel = (el) => {
      try { return el ? el.closest(c.panel_secici) : null; } catch (e) { return null; }
    };
    const panelKimligi = (el) => {
      const p = enYakinPanel(el);
      return p ? panelAdi(p) : '';
    };
    // BÜTÜN panel/kart ataları, en yakından en uzağa (a2 (g)): ondalık
    // gruplaması her kartı AYRI değerlendirir ve bir kart kendi içindeki
    // (iç kartlar dahil) bütün sayıları görür — dış panel virgüllü, iç kart
    // noktalıysa dış panel KARIŞIKTIR.
    const panelZinciri = (el) => {
      const z = [];
      for (let p = enYakinPanel(el); p; p = enYakinPanel(p.parentElement)) z.push(panelAdi(p));
      return z;
    };
    // Bir istemci dikdörtgeninin (görüntü alanı koordinatı) kırpma
    // dikdörtgeniyle (belge koordinatı) kesişimi boş mu? Kırpma ATALARDAN
    // gelir (overflow gizli/kırpık/kaydırmalı); kesişim boşsa o parça
    // EKRANDA değildir — max-height:0 akordeon, kaydırmalı kabın görünmeyen
    // satırları.
    const kesisir = (r, k) => {
      const x1 = Math.max(r.left + scrollX, k.x1), x2 = Math.min(r.right + scrollX, k.x2);
      const y1 = Math.max(r.top + scrollY, k.y1), y2 = Math.min(r.bottom + scrollY, k.y2);
      return x2 - x1 > 0 && y2 - y1 > 0;
    };
    const uyariMi = (el) => {
      try { return !!el.closest(c.uyari_secici); } catch (e) { return false; }
    };
    // Metin düğümünün KENDİ satır kutularından biri kırpma dikdörtgeniyle
    // kesişiyor mu (öğe kutusu değil: satır içi parça kırpılabilir, kutu
    // taşabilir).
    const metinGorunur = (tn, k) => {
      const rg = document.createRange();
      rg.selectNodeContents(tn);
      for (const r of rg.getClientRects()) {
        if (r.width > 0 && r.height > 0 && kesisir(r, k)) return true;
      }
      return false;
    };
    const SVG_AD = 'http://www.w3.org/2000/svg';
    const satirIci = (d) => d === 'inline' || d === 'contents';
    // DİL/ONDALIK BİRİMİ = BLOK METNİ (a2 (b)). Satır içi olmayan her öğe
    // (blok, satır-içi-blok, tablo hücresi, esnek öğe…) bir birimdir; metni
    // kendi metin düğümleri ile SATIR İÇİ torunlarının metninin belge
    // sırasıyla birleşimidir: <p>The pressure <b>is</b> below <i>the</i>
    // limit</p> TEK cümledir ("The pressure is below the limit"). a1'de
    // yaprak öğenin yalnız kendi metin düğümleriydi; satır içi etiket cümleyi
    // parçalıyor, parçaların her biri eşiğin altında kalıyordu. Birimin
    // içindeki satır içi OLMAYAN çocuk (kendi birimi), <br> ve SVG yerine
    // dizi KESİCİ konur; görünmeyen parça (visibility:hidden, opacity:0,
    // kırpma dışı) atlanır; muaf satır içi parça (<code>, künye…) KESİCİYLE
    // değiştirilir ve ayrı bir muaf kayıt olarak SAYILIR.
    const birimMetni = (kok, kirpma, kokMuaf, kokStil) => {
      const parcalar = [];
      const muaflar = [];
      let gorunur = false;
      const yuru = (el, gizli) => {
        for (const d of el.childNodes) {
          if (d.nodeType === 3) {
            const t = (d.textContent || '').replace(/\\s+/g, ' ');
            if (!t.trim()) { parcalar.push(t); continue; }
            if (!gizli && metinGorunur(d, kirpma)) { parcalar.push(t); gorunur = true; }
            else parcalar.push(' ');
            continue;
          }
          if (d.nodeType !== 1) continue;
          if (d.namespaceURI === SVG_AD || d.tagName === 'BR') { parcalar.push(KESICI); continue; }
          if (ATLA.has(d.tagName)) { parcalar.push(' '); continue; }
          const st = getComputedStyle(d);
          if (st.display === 'none') continue;
          if (!satirIci(st.display)) { parcalar.push(KESICI); continue; }
          if (parseFloat(st.opacity || '1') === 0) { parcalar.push(' '); continue; }
          if (!kokMuaf) {
            const ma = muafAdi(d);
            if (ma) {
              const alt = birimMetni(d, kirpma, true, st);
              if (alt.metin && alt.gorunur) muaflar.push({ ad: ma, m: alt.metin, el: d });
              parcalar.push(KESICI);
              continue;
            }
          }
          yuru(d, st.visibility === 'hidden');
        }
      };
      yuru(kok, kokStil.visibility === 'hidden');
      const metin = parcalar.join('').replace(/ *\\n[\\n ]*/g, '\\n')
        .replace(/ {2,}/g, ' ').trim();
      return { metin: metin, gorunur: gorunur, muaflar: muaflar };
    };
    let kesikBirim = 0;
    const sinirla = (m) => {
      if (m.length <= c.birim_siniri) return [m, false];
      kesikBirim++;
      return [m.slice(0, c.birim_siniri) + '…', true];
    };
    const blokAtasi = (el) => {
      let e = el;
      while (e && e.nodeType === 1) {
        const d = getComputedStyle(e).display;
        if (d !== 'inline' && d !== 'contents') return e;
        e = e.parentElement;
      }
      return null;
    };

    const metinler = [];
    const bloklar = new Set();
    const ebeveynAday = [];
    let kirpildi = false;
    let muafSayisi = 0;

    const ekle = (kayit) => {
      if (metinler.length >= c.sinir) { kirpildi = true; return false; }
      metinler.push(kayit);
      return true;
    };

    const svgMetinleri = (svg, kirpma) => {
      for (const t of svg.querySelectorAll('text')) {
        if (t.closest('defs, clipPath, mask, symbol')) continue;
        const m = duz(t.textContent);
        if (!m) continue;
        const st = getComputedStyle(t);
        if (st.display === 'none' || st.visibility === 'hidden'
            || parseFloat(st.opacity || '1') === 0) continue;
        const r = t.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        const x1 = Math.max(r.left + scrollX, kirpma.x1);
        const x2 = Math.min(r.right + scrollX, kirpma.x2);
        const y1 = Math.max(r.top + scrollY, kirpma.y1);
        const y2 = Math.min(r.bottom + scrollY, kirpma.y2);
        if (x2 - x1 <= 0 || y2 - y1 <= 0) continue;
        const [sm, sk] = sinirla(m);
        if (!ekle({ tur: 'svg', m: sm, kesik: sk, s: yol(t), p: panelKimligi(svg),
                    pp: panelZinciri(svg), muaf: muafAdi(t), u: uyariMi(t) })) return;
      }
    };

    const yurut = (el, kirpma) => {
      if (!(el && el.nodeType === 1)) return;
      const ad = el.tagName;
      if (ATLA.has(ad)) return;
      const st = getComputedStyle(el);
      if (st.display === 'none') return;
      if (parseFloat(st.opacity || '1') === 0) return;
      if (el.namespaceURI === 'http://www.w3.org/2000/svg') {
        if (ad.toLowerCase() === 'svg' && st.visibility !== 'hidden') svgMetinleri(el, kirpma);
        return;
      }
      const r = el.getBoundingClientRect();
      const mx = r.left + scrollX, my = r.top + scrollY;
      if (ad === 'SELECT') {
        if (st.visibility === 'hidden' || r.width <= 0 || r.height <= 0) return;
        const s = el.selectedOptions && el.selectedOptions[0];
        const m = s ? duz(s.textContent) : '';
        if (m) ekle({ tur: 'secim', m: sinirla(m)[0], s: yol(el), p: panelKimligi(el),
                      pp: panelZinciri(el), muaf: muafAdi(el), u: uyariMi(el) });
        return;
      }
      if (KIRPAN.has(st.overflowX)) {
        kirpma = { x1: Math.max(kirpma.x1, mx), x2: Math.min(kirpma.x2, mx + r.width),
                   y1: kirpma.y1, y2: kirpma.y2 };
      }
      if (KIRPAN.has(st.overflowY)) {
        kirpma = { x1: kirpma.x1, x2: kirpma.x2,
                   y1: Math.max(kirpma.y1, my), y2: Math.min(kirpma.y2, my + r.height) };
      }
      const gorunur = st.visibility !== 'hidden';
      let oz = '';
      for (const d of el.childNodes) if (d.nodeType === 3) oz += d.textContent;
      oz = duz(oz);
      if (oz && gorunur) {
        const x1 = Math.max(mx, kirpma.x1), x2 = Math.min(mx + r.width, kirpma.x2);
        const y1 = Math.max(my, kirpma.y1), y2 = Math.min(my + r.height, kirpma.y2);
        // Satır içi öğenin kutusu 0 genişlik ölçebilir (boş satır parçası);
        // metin düğümünün kendi kutuları Range ile ölçülür — ve onlar da
        // KIRPMA dikdörtgeniyle kesiştirilir (a2 (c): a1'de yedek kırpmayı
        // görmüyordu; max-height:0 + overflow:hidden akordeondaki ya da
        // kaydırmalı kabın görünmeyen satırındaki <span>/<strong> ölçüme
        // giriyordu — canlı: katı #propellantCatalogTable strong 20-23
        // yaprak, sıvı 390 #vzd1_clock b).
        let ekranda = (x2 - x1 > 0 && y2 - y1 > 0);
        if (!ekranda && st.display === 'inline') {
          const rg = document.createRange();
          rg.selectNodeContents(el);
          for (const rr of rg.getClientRects()) {
            if (rr.width > 0 && rr.height > 0 && kesisir(rr, kirpma)) { ekranda = true; break; }
          }
        }
        if (ekranda) {
          // GEOMETRİ girdisi: metin taşıyan blok kutusu + ebeveyn adayı.
          const b = (st.display === 'inline') ? blokAtasi(el) : el;
          if (b) bloklar.add(b);
          if (st.display !== 'inline' && st.position !== 'absolute'
              && st.position !== 'fixed') ebeveynAday.push(el);
        }
      }
      // DİL/ONDALIK girdisi: satır içi olmayan her öğe BİR birim (blok metni).
      if (!satirIci(st.display)) {
        const muaf = muafAdi(el);
        const b = birimMetni(el, kirpma, !!muaf, st);
        for (const mp of b.muaflar) {
          muafSayisi++;
          const [mm, mk] = sinirla(mp.m);
          if (!ekle({ tur: 'metin', m: mm, kesik: mk, s: yol(mp.el),
                      p: panelKimligi(mp.el), pp: panelZinciri(mp.el), muaf: mp.ad,
                      u: uyariMi(mp.el) })) return;
        }
        if (b.metin && b.gorunur) {
          if (muaf) muafSayisi++;
          const [bm, bk] = sinirla(b.metin);
          if (!ekle({ tur: 'metin', m: bm, kesik: bk, s: yol(el), p: panelKimligi(el),
                      pp: panelZinciri(el), muaf: muaf, u: uyariMi(el) })) return;
        }
      }
      if (ad === 'DETAILS' && !el.open) {
        for (const cocuk of el.children) {
          if (cocuk.tagName === 'SUMMARY') yurut(cocuk, kirpma);
        }
        return;
      }
      for (const cocuk of el.children) yurut(cocuk, kirpma);
    };
    yurut(document.body, { x1: -Infinity, y1: -Infinity, x2: Infinity, y2: Infinity });

    // --- (c1) öğe taşması: metin taşıyan blok kutuları -------------------
    const tasmalar = [];
    for (const b of bloklar) {
      const sw = b.scrollWidth, cw = b.clientWidth;
      if (!(cw > 0) || sw <= cw + tol) continue;
      const st = getComputedStyle(b);
      const ox = st.overflowX;
      // Ekran okuyucu etiketi deseni (1 px kutu + overflow gizli + clip):
      // kutu BİLEREK görünmezdir, taşma kusuru değildir — ayrı sınıf.
      const erisimGizli = (cw <= c.erisim_gizli_px || b.clientHeight <= c.erisim_gizli_px);
      const sinif = erisimGizli ? 'erisim_gizli'
                  : (ox === 'visible') ? 'tasan'
                  : (ox === 'auto' || ox === 'scroll') ? 'kaydirmali' : 'kesilen';
      const baslik = !!((b.getAttribute('title') || '').trim()
                        || (b.getAttribute('aria-label') || '').trim()
                        || (b.parentElement && (b.parentElement.getAttribute('title') || '').trim()));
      tasmalar.push({ s: yol(b), m: kirp(duz(b.innerText || b.textContent), 120),
                      sw: sw, cw: cw, fazla: sw - cw, sinif: sinif, ox: ox,
                      to: st.textOverflow, ws: st.whiteSpace, baslik: baslik });
    }

    // --- (c2) ebeveyn kutusunu aşan metin öğesi -------------------------
    const ebeveyn_asimlari = [];
    for (const el of ebeveynAday) {
      let p = el.parentElement;
      while (p && getComputedStyle(p).display === 'contents') p = p.parentElement;
      if (!p || p === document.body || p === de) continue;
      const pst = getComputedStyle(p);
      if (pst.overflowX === 'auto' || pst.overflowX === 'scroll') continue;
      const r = el.getBoundingClientRect();
      const pr = p.getBoundingClientRect();
      const sag = r.right - pr.right, sol = pr.left - r.left;
      const fazla = Math.max(sag, sol);
      if (fazla <= ebTol) continue;
      ebeveyn_asimlari.push({ s: yol(el), m: kirp(duz(el.innerText || el.textContent), 120),
                              ebeveyn: yol(p), fazla: Math.round(fazla * 10) / 10,
                              yon: sag >= sol ? 'sag' : 'sol',
                              ebeveyn_ox: pst.overflowX,
                              sinif: (pst.overflowX === 'visible') ? 'tasan' : 'kirpilan',
                              genislik: Math.round(r.width), ebeveyn_genislik: Math.round(pr.width) });
    }

    // --- (c3) sayfa yatay kaydırması + suçlular (DV-TOOLTIP) ------------
    const cw = de.clientWidth, iw = window.innerWidth, sw = de.scrollWidth;
    const suclu = [];
    const kokler = [];
    let kirpilanAday = 0, sabitAday = 0;
    if (sw > Math.min(cw, iw) + c.sayfa_tolerans_px) {
      const esik = Math.min(cw, iw) + c.sayfa_tolerans_px;
      const stiller = new Map();
      const stil = (el) => {
        let s = stiller.get(el);
        if (!s) { s = getComputedStyle(el); stiller.set(el, s); }
        return s;
      };
      const adaylar = [];
      for (const el of document.body.querySelectorAll('*')) {
        const st = stil(el);
        if (st.display === 'none') continue;
        const r = el.getBoundingClientRect();
        if (r.width <= 0 && r.height <= 0) continue;
        const sagKenar = r.right + scrollX;
        if (sagKenar <= esik) continue;
        // Belge kaydırmasına KATKI VERMEYEN taşanlar suçlu değildir:
        // (i) sabit konumlu öğe ya da sabit atanın torunu (görüntü alanına
        // bağlıdır, belgenin kaydırılabilir taşmasına girmez); (ii) sağ
        // kenarı eşiğin İÇİNDE kalan ve overflow-x'i görünür OLMAYAN bir
        // ata tarafından kırpılan öğe (Plotly SVG'sinin iç düğümleri,
        // kaydırmalı tablo kabının hücreleri). İkisi ayrıca sayılır.
        let sabit = st.position === 'fixed', kirpik = false;
        for (let p = el.parentElement; p && p !== document.body && p !== de
             && !sabit && !kirpik; p = p.parentElement) {
          const ps = stil(p);
          if (ps.position === 'fixed') { sabit = true; break; }
          if (ps.overflowX !== 'visible'
              && p.getBoundingClientRect().right + scrollX <= esik) kirpik = true;
        }
        if (sabit) { sabitAday++; continue; }
        if (kirpik) { kirpilanAday++; continue; }
        adaylar.push({ el: el, sag: sagKenar, st: st });
      }
      // EN DERİN taşanlar: kendisi taşan ama taşan hiçbir torunu olmayan
      // öğe. Her adayın atalarını bir kez yürüyerek işaretlenir (O(n·derinlik)).
      const kume = new Set(adaylar.map(a => a.el));
      const derinDegil = new Set();
      for (const a of adaylar) {
        let p = a.el.parentElement;
        while (p) { if (kume.has(p)) derinDegil.add(p); p = p.parentElement; }
      }
      const kayitla = (a) => ({ s: yol(a.el), m: kirp(duz(a.el.textContent), 80),
                                sag: Math.round(a.sag),
                                fazla: Math.round(a.sag - Math.min(cw, iw)),
                                gizli: a.st.visibility === 'hidden',
                                konum: a.st.position });
      for (const a of adaylar) {
        if (derinDegil.has(a.el)) continue;
        suclu.push(kayitla(a));
      }
      suclu.sort((x, y) => y.fazla - x.fazla);
      // KÖK taşanlar: kendisi taşan ama taşan hiçbir ATASI olmayan öğe —
      // onarımın yapılacağı kutu çoğunlukla budur (en derin liste bir
      // tablonun 40 hücresini sayabilir, kökü tek bir panel olabilir).
      for (const a of adaylar) {
        let atada = false;
        for (let p = a.el.parentElement; p; p = p.parentElement) {
          if (kume.has(p)) { atada = true; break; }
        }
        if (!atada) kokler.push(kayitla(a));
      }
      kokler.sort((x, y) => y.fazla - x.fazla);
    }

    return {
      dil: (window.I18N && window.I18N.lang) || null,
      html_dil: de.lang || null,
      pencere: { ic_genislik: iw, istemci_genislik: cw, kaydirma_genisligi: sw,
                 ic_yukseklik: window.innerHeight },
      yaprak_sayisi: metinler.length,
      muaf_yaprak_sayisi: muafSayisi,
      kesik_birim_sayisi: kesikBirim,
      birim_siniri: c.birim_siniri,
      kirpildi: kirpildi,
      metinler: metinler,
      blok_sayisi: bloklar.size,
      tasmalar: tasmalar,
      ebeveyn_asimlari: ebeveyn_asimlari,
      sayfa: { kaydirma_genisligi: sw, ic_genislik: iw, istemci_genislik: cw,
               fazla_px: sw - Math.min(cw, iw),
               suclular: suclu.slice(0, c.suclu_siniri),
               suclu_sayisi: suclu.length,
               kok_suclular: kokler.slice(0, c.suclu_siniri),
               kok_suclu_sayisi: kokler.length,
               gizli_suclu_sayisi: suclu.filter(x => x.gizli).length,
               kirpilan_aday_sayisi: kirpilanAday,
               sabit_aday_sayisi: sabitAday }
    };
  } catch (hata) { return { hata: String(hata && hata.stack || hata) }; }
}
"""


def piksel_yapilandirmasi() -> Dict[str, Any]:
    """``JS_PIKSEL``e geçirilen ayar sözlüğü — eşik ve muafiyetin TEK kaynağı
    ``esikler.py``dir; betikte sayı ya da seçici YOKTUR."""
    return {
        'tolerans_px': esikler.PIKSEL_TASMA_TOLERANS_PX,
        'erisim_gizli_px': esikler.PIKSEL_ERISIM_GIZLI_KENAR_PX,
        # Sayfa kaydırması ANA TURLA AYNI toleransla ölçülür (tek kavram,
        # tek sabit): yerlesim_yatay_tasma ile piksel_yatay_kaydirma aynı
        # belgeye farklı eşikle bakmasın.
        'sayfa_tolerans_px': esikler.YATAY_TASMA_TOLERANS_PX,
        'ebeveyn_tolerans_px': esikler.PIKSEL_EBEVEYN_ASIM_TOLERANS_PX,
        'muaf_seciciler': [[ad, secici] for ad, secici, _ in
                           esikler.PIKSEL_MUAF_SECICILER],
        'panel_secici': esikler.PIKSEL_PANEL_SECICI,
        'uyari_secici': esikler.PIKSEL_UYARI_SECICI,
        'sinir': esikler.PIKSEL_YAPRAK_UST_SINIRI,
        'birim_siniri': esikler.PIKSEL_BIRIM_METIN_UST_SINIRI,
        # Birim metninde satır içi olmayan çocuğun / <br>'nin / muaf parçanın
        # yerine konan dizi kesici — dil denetiminin kesicisiyle AYNI karakter.
        'kesici': esikler.DIL_SAFLIGI_DIZI_KESICILER[0],
        'suclu_siniri': esikler.PIKSEL_SUCLU_UST_SINIRI,
    }


def piksel_olc(sayfa) -> Dict[str, Any]:
    """Canlı bir Playwright ``Page`` üzerinde ölçümü koşturur.

    İstisna yükseltmez: ölçüm alınamazsa ``hata`` anahtarlı sözlük döner,
    hüküm katmanı onu fail-closed kırmızıya çevirir.
    """
    try:
        return sayfa.evaluate(JS_PIKSEL, piksel_yapilandirmasi()) or {
            'hata': 'ölçüm betiği boş döndü'}
    except Exception as hata:  # pragma: no cover - tarayıcı hatası
        return {'hata': '%s: %s' % (type(hata).__name__, str(hata)[:300])}


# ---------------------------------------------------------------------------
# Piksel turu gezintisi — (sayfa × dil × genişlik) başına TEMİZ bağlam
# ---------------------------------------------------------------------------

#: Sayfa yüklenmeden ÖNCE ürünün dil tercihini yazan başlangıç betiği.
#: Anahtar ürünün kendi sabitinden (``esikler.URUN_DIL_DEPOLAMA_ANAHTARI``)
#: gelir; dil ARGÜMANLA geçer. Sayfanın gerçekten o dilde açıldığını
#: ``I18N.lang`` söyler (ölçümün ``dil`` alanı) — yazılan değer değil.
def dil_baslangic_betigi(dil: str) -> str:
    return ('try { window.localStorage.setItem(%s, %s); } catch (e) {}'
            % (json.dumps(esikler.URUN_DIL_DEPOLAMA_ANAHTARI), json.dumps(dil)))


#: Hesap düğmesine basılmadan önce eldeki sonuç nesnesini işaretler; bekleme
#: koşulu YENİ bir nesne ister. Böylece önceden dolu bir ``currentResults``
#: (ör. sayfanın kendi ilk hesabı) "hesap bitti" diye okunmaz.
JS_ONCEKI_SONUC_ISARETLE = """
() => { window.__pikselOncekiSonuc = window.currentResults || null; return true; }
"""
JS_YENI_SONUC = """
() => !!(window.currentResults && window.currentResults !== window.__pikselOncekiSonuc)
"""


def ornek_proje_url(temel_url: str, sayfa_adi: str, yol: str) -> str:
    """Örnek projeyle açılan sayfa adresi (``?project=<ad>``)."""
    ad = esikler.PIKSEL_ORNEK_PROJELERI[sayfa_adi]
    return '%s%s?project=%s' % (temel_url.rstrip('/'), yol, urllib.parse.quote(ad))


def kombinasyonu_gez(tarayici, temel_url: str, tanim, dil: str,
                     genislik_adi: str, cikti_dizini: Optional[str] = None,
                     goruntu: bool = False, ham: bool = False,
                     sozluk_gecikmesi_ms: int = 0) -> Dict[str, Any]:
    """Tek bir (sayfa, dil, genişlik) kombinasyonunu gezer ve hükmünü verir.

    Akış: temiz bağlam (görüntü alanı + yerel + dil başlangıç betiği) →
    ``?project=<örnek>`` → projenin yüklendiği ürün kancasıyla beklenir →
    hesap düğmesi → YENİ sonuç nesnesi → ağ sessizliği + durulma → ölçüm.
    Akış kesilirse ``akis_tamam`` KIRMIZI olur ve piksel denetimleri boş
    ölçümle fail-closed kırmızı verir — "ölçülemedi" hiçbir zaman "temiz"
    sayılmaz.
    """
    alan = esikler.PIKSEL_GORUNTU_ALANLARI[genislik_adi]
    proje = esikler.PIKSEL_ORNEK_PROJELERI.get(tanim.ad)
    asamalar: List[str] = []
    hatalar: List[str] = []
    diyaloglar: List[str] = []
    sayfa_hatalari: List[str] = []
    sureler: Dict[str, float] = {}
    olcum: Dict[str, Any] = {}
    url = None
    baglam = tarayici.new_context(viewport=dict(alan),
                                  locale=esikler.PIKSEL_DIL_YERELLERI[dil])
    try:
        baglam.add_init_script(dil_baslangic_betigi(dil))
        p = baglam.new_page()

        def diyalog(d):
            diyaloglar.append('%s: %s' % (d.type, str(d.message)[:200]))
            try:
                d.dismiss()
            except Exception:
                pass

        p.on('dialog', diyalog)
        if sozluk_gecikmesi_ms:
            # SÖZLÜK YARIŞI kipi (esikler.PIKSEL_GEC_SOZLUK_DESENI notu):
            # ortak sözlük isteği bekletilir; geç kaydolan sözlüğü yeniden
            # basmayan metinler İngilizce kalır ve dil denetimi onları görür.
            def geciktir(rota):
                time.sleep(sozluk_gecikmesi_ms / 1000.0)
                rota.continue_()

            p.route(esikler.PIKSEL_GEC_SOZLUK_DESENI, geciktir)
            asamalar.append('SÖZLÜK YARIŞI kipi: %s %d ms bekletildi'
                            % (esikler.PIKSEL_GEC_SOZLUK_DESENI, sozluk_gecikmesi_ms))
        p.on('pageerror', lambda h: sayfa_hatalari.append(str(h)[:300]))
        try:
            if not proje:
                raise RuntimeError('%r için örnek proje tanımı yok '
                                   '(esikler.PIKSEL_ORNEK_PROJELERI)' % tanim.ad)
            url = ornek_proje_url(temel_url, tanim.ad, tanim.yol)
            t0 = time.time()
            p.goto(url, wait_until='domcontentloaded',
                   timeout=esikler.SAYFA_YUKLEME_ZAMAN_ASIMI_MS)
            try:
                p.wait_for_load_state('networkidle',
                                      timeout=esikler.SAYFA_YUKLEME_ZAMAN_ASIMI_MS)
            except Exception:
                asamalar.append('ağ sessizliğine ulaşılamadı (devam edildi)')
            p.wait_for_function(PROJE_YUKLENDI_KOSULU, arg=proje,
                                timeout=esikler.PIKSEL_PROJE_YUKLEME_ZAMAN_ASIMI_MS)
            sureler['yukleme_s'] = round(time.time() - t0, 2)
            asamalar.append('örnek proje yüklendi: %s' % proje)
            p.evaluate(JS_ONCEKI_SONUC_ISARETLE)
            t0 = time.time()
            dugme = p.locator(tanim.hesapla_secici).first
            dugme.wait_for(state='visible', timeout=esikler.SAYFA_YUKLEME_ZAMAN_ASIMI_MS)
            dugme.click()
            p.wait_for_function(tanim.sonuc_kosulu, timeout=esikler.HESAP_ZAMAN_ASIMI_MS)
            p.wait_for_function(JS_YENI_SONUC, timeout=esikler.HESAP_ZAMAN_ASIMI_MS)
            sureler['hesap_s'] = round(time.time() - t0, 2)
            asamalar.append('hesap bitti: yeni sonuç nesnesi (%.1f s)' % sureler['hesap_s'])
            try:
                p.wait_for_load_state('networkidle',
                                      timeout=esikler.SAYFA_YUKLEME_ZAMAN_ASIMI_MS)
            except Exception:
                asamalar.append('hesap sonrası ağ sessizliğine ulaşılamadı')
            p.wait_for_timeout(esikler.PIKSEL_DURULMA_MS)
            t0 = time.time()
            olcum = piksel_olc(p)
            sureler['olcum_s'] = round(time.time() - t0, 2)
            if olcum.get('hata'):
                hatalar.append('ölçüm betiği: %s' % olcum['hata'][:300])
            if goruntu and cikti_dizini:
                yol = os.path.join(cikti_dizini, '%s_%s_%s.png'
                                   % (tanim.ad, dil, genislik_adi))
                p.screenshot(path=yol, full_page=False)
                asamalar.append('görüntü alanı karesi: %s' % yol)
        except Exception as hata:
            hatalar.append('%s: %s' % (type(hata).__name__, str(hata)[:400]))
            asamalar.append('AKIŞ KESİLDİ')
    finally:
        baglam.close()

    akis = denetimler.Denetim(
        ad='akis_tamam', gecti=not hatalar,
        ozet=('örnek proje yüklendi, hesap bitti, ölçüm alındı' if not hatalar
              else 'akış kesildi: %s' % '; '.join(hatalar)),
        dayanak='gezinti adımlarının istisna kaydı',
        olcum={'asamalar': asamalar, 'hatalar': hatalar}, esik={})
    liste = [akis] + denetimler.piksel_denetimleri(olcum if not hatalar else {}, dil)
    kayit: Dict[str, Any] = {
        'sayfa': tanim.ad, 'dil': dil, 'genislik': genislik_adi,
        'goruntu_alani': dict(alan), 'url': url, 'ornek_proje': proje,
        'sozluk_gecikmesi_ms': sozluk_gecikmesi_ms,
        'gecti': denetimler.sayfa_hukmu(liste), 'sureler_s': sureler,
        'asamalar': asamalar, 'diyaloglar': diyaloglar,
        'sayfa_hatasi_sayisi': len(sayfa_hatalari),
        'sayfa_hatalari': sayfa_hatalari[:5],
        'olcum_kunyesi': {k: olcum.get(k) for k in
                          ('dil', 'html_dil', 'pencere', 'yaprak_sayisi',
                           'muaf_yaprak_sayisi', 'kirpildi', 'blok_sayisi')},
        'denetimler': [d.sozluk() for d in liste],
    }
    if ham:
        kayit['ham_olcum'] = olcum
    return kayit


def piksel_turu_kos(temel_url: str, sayfa_tanimlari: Sequence[Any],
                    diller: Sequence[str], genislikler: Sequence[str],
                    cikti_dizini: Optional[str] = None, basli: bool = False,
                    kanal: Optional[str] = None, goruntu: bool = False,
                    ham: bool = False, sozluk_gecikmesi_ms: int = 0
                    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Kombinasyonları SIRAYLA gezer (sayfa → dil → genişlik).

    ``(kombinasyon_kayitlari, tarayici_kunyesi)`` döner. Tarayıcı açılışı
    ana turun ``_tarayici_ac``ını kullanır: düşüş SESSİZ değildir.
    """
    from playwright.sync_api import sync_playwright  # isteğe bağlı bağımlılık
    from tools.browser_harness import tur

    for dil in diller:
        if dil not in esikler.PIKSEL_DILLERI:
            raise ValueError('bilinmeyen dil: %s (geçerli: %s)'
                             % (dil, ', '.join(esikler.PIKSEL_DILLERI)))
    for g in genislikler:
        if g not in esikler.PIKSEL_GORUNTU_ALANLARI:
            raise ValueError('bilinmeyen genişlik: %s (geçerli: %s)'
                             % (g, ', '.join(esikler.PIKSEL_GORUNTU_ALANLARI)))
    if cikti_dizini:
        os.makedirs(cikti_dizini, exist_ok=True)
    kayitlar: List[Dict[str, Any]] = []
    with sync_playwright() as pw:
        tarayici, kullanilan, denemeler = tur._tarayici_ac(pw, kanal, basli)
        kunye = {'motor': 'chromium', 'kanal': kullanilan,
                 'surum': tarayici.version, 'basli': bool(basli),
                 'istenen_kanal': kanal or 'auto', 'denemeler': denemeler}
        try:
            for tanim in sayfa_tanimlari:
                for dil in diller:
                    for g in genislikler:
                        kayitlar.append(kombinasyonu_gez(
                            tarayici, temel_url, tanim, dil, g,
                            cikti_dizini=cikti_dizini, goruntu=goruntu, ham=ham,
                            sozluk_gecikmesi_ms=sozluk_gecikmesi_ms))
        finally:
            tarayici.close()
    return kayitlar, kunye
