"""Güncelleme penceresi — kurulum sürerken görünen "HRMA güncelleniyor".

V307/GÜNCELLEME-EKRAN (Berke, 10 Kas 2026): güncelleme kurulurken uygulama
kapanıyor ve yeni sürüm açılana kadar ekranda hiçbir şey olmuyordu. Bu modül
yardımcı betiğin başlattığı küçük pencerenin betiklerini üretir:

- macOS: ``/usr/bin/osascript -l JavaScript`` (JXA + AppKit köprüsü),
- Windows: ``powershell.exe`` + WinForms.

İkisi de işletim sisteminin parçasıdır; kurulum sırasında silinen ya da
değiştirilen uygulama paketinin içindeki Python'a BAĞLI DEĞİLDİR. Betikler
kurulumdan ÖNCE yardımcı betiğin yanına yazılır (self_install.launch_helper).

Pencere YALNIZ yardımcı betiğin yazdığı durum dosyasını okur (sözleşme:
self_install.UPDATE_STATUS_*): adım, aşama, betiğin ``du`` ile ölçtüğü kopya
miktarı, sürümler, sonuç ve hata kodu. Zamana bağlı ya da uydurma ilerleme
YOKTUR: oran yalnız kopya adımında, ölçülen iki değer varken gösterilir;
gerisi adımın adı ve gerçek saatten geçen süredir.

Metinler tek kaynaktan gelir (self_install.UPDATE_TEXTS) ve betiğe JSON
olarak gömülür; betikler ASCII'dir (Türkçe harfler \\uXXXX kaçışıyla).

Tanı/kanıt seçenekleri (yalnız testler ve deneme paketi kullanır; ürün
betiği bunları VERMEZ):
- macOS ``--render PNG [--now EPOCH] [--alive 0|1]``: durumu tek kare çizer,
  pencere göstermez; ölçü JSON'unu stdout'a yazar.
- macOS ``--record DİZİN``: canlı pencerenin her görünüm değişimini
  ``window_states.jsonl`` + PNG olarak kaydeder; ``--offscreen`` ile pencere
  ekrana hiç gelmez (birim/uçtan uca testler).
- Windows ``-Render PNG [-Now EPOCH] [-Alive 0|1]`` ve ``-Record JSONL``.
"""

import json

from hrma.utils import self_install as si

#: Pencerede kullanılan metin anahtarları (UPDATE_TEXTS'ten süzülür).
_METIN_ONEKLERI = ("step.", "window.")
_METIN_ANAHTARLARI = ("title", "progress", "progress_total", "elapsed", "log")

#: Aşama listesi: (gösterilen adım, o aşamaya ait betik adımları).
#: macOS betiğinin adım sırası (self_install.MAC_HELPER set_step çağrıları).
MAC_STAGES = (
    ("waiting_exit", ("start", "waiting_exit")),
    ("mounting", ("mounting",)),
    ("copying", ("copying",)),
    ("verifying", ("verifying", "quarantine_check", "quarantine")),
    ("swapping", ("closing", "swapping")),
    ("opening", ("opening", "done", "restoring", "restored")),
)

#: Windows betiğinin adım sırası (self_install.WIN_HELPER).
WIN_STAGES = (
    ("waiting_exit", ("start", "waiting_exit")),
    ("installing", ("installing",)),
    ("checking_install", ("checking_install",)),
    ("opening", ("opening", "done")),
)

#: Aşama imleri: tamam / sürüyor / hata / bekliyor.
MARKS = {"done": "✓", "current": "●", "error": "✗",
         "pending": "○"}


def window_config(stages):
    """Pencere betiklerine gömülen yapılandırma (tek kaynak: self_install)."""
    metinler = {}
    for dil, tablo in si.UPDATE_TEXTS.items():
        metinler[dil] = {k: v for k, v in tablo.items()
                         if k.startswith(_METIN_ONEKLERI)
                         or k in _METIN_ANAHTARLARI}
    return {
        "header": si.UPDATE_STATUS_HEADER,
        "max_bytes": si.UPDATE_STATUS_MAX_BYTES,
        "poll_s": si.HELPER_WINDOW_POLL_S,
        "done_close_s": si.HELPER_WINDOW_DONE_CLOSE_S,
        "max_age_s": si.UPDATE_LOCK_MAX_AGE_S,
        "exit_wait_s": si.HELPER_EXIT_WAIT_S,
        "verify_s": si.HELPER_LAUNCH_VERIFY_S,
        "results": list(si.UPDATE_RESULTS),
        "actions": dict(si.UPDATE_ERROR_ACTIONS),
        "stages": [[a, list(b)] for a, b in stages],
        "marks": dict(MARKS),
        "texts": metinler,
    }


def _cfg_json(stages):
    # ensure_ascii: betik ASCII kalır (Türkçe harfler \\uXXXX); tek satır.
    return json.dumps(window_config(stages), ensure_ascii=True,
                      sort_keys=True)


# ---------------------------------------------------------------------------
# macOS — JXA (osascript -l JavaScript) + AppKit
# ---------------------------------------------------------------------------

MAC_WINDOW_JS = r"""// HRMA guncelleme penceresi (macOS) - hrma/utils/update_window.py uretir.
// /usr/bin/osascript -l JavaScript ile calisir; uygulama paketine (Python)
// BAGLI DEGILDIR. Yalniz yardimci betigin yazdigi durum dosyasini okur;
// ilerleme yalniz olculen degerden. Argumanlar: [secenekler] DURUM YARDIMCI_PID GUNLUK KURUCU
ObjC.import('Cocoa');
ObjC.import('signal');
var CFG = /*@@CFG@@*/null;

var W = 480, M = 22, TW = W - 2 * M, MARK_W = 20;

function fmt(t, o) {
    return String(t).replace(/\{(\w+)(:02d)?\}/g, function (m, k, pad) {
        if (!(k in o)) return m;
        var v = String(o[k]);
        return (pad && v.length < 2) ? ('0' + v) : v;
    });
}

function mbText(kb, lang) {
    var s = String(Math.round(kb / 1024)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return lang === 'tr' ? s.replace(/,/g, '.') : s;
}

function tilde(p) {
    if (!p) return '';
    var home = ObjC.unwrap($.NSHomeDirectory());
    return (home && p.indexOf(home + '/') === 0) ? '~' + p.substring(home.length) : p;
}

var RE_STEP = /^[a-z_]{1,32}$/, RE_CODE = /^[a-z_]{0,40}$/, RE_NUM = /^\d{1,15}$/,
    RE_VER = /^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$/;

// Durum dosyasi -> nesne; okunamaz/yarim/yabanci ise null.
function parseStatus(text) {
    if (!text) return null;
    var lines = String(text).split(/\r?\n/);
    if (lines.length < 2 || lines[0].replace(/\s+$/, '') !== CFG.header) return null;
    var f = {}, end = false;
    for (var i = 1; i < lines.length; i++) {
        var j = lines[i].indexOf('=');
        if (j <= 0) continue;
        var k = lines[i].substring(0, j), v = lines[i].substring(j + 1).replace(/\s+$/, '');
        if (k === 'end') { end = (v === '1'); continue; }
        f[k] = v;
    }
    if (!end) return null;
    var num = function (v) { return RE_NUM.test(v || '') ? parseInt(v, 10) : null; };
    var st = {
        pid: num(f.pid), started: num(f.started),
        step: RE_STEP.test(f.step || '') ? f.step : null,
        phase: f.phase || '',
        done_kb: num(f.done_kb), total_kb: num(f.total_kb),
        lang: (f.lang === 'tr' || f.lang === 'en') ? f.lang : null,
        from_version: RE_VER.test(f.from_version || '') ? f.from_version : '',
        to_version: RE_VER.test(f.to_version || '') ? f.to_version : '',
        result: CFG.results.indexOf(f.result) >= 0 ? f.result : 'running',
        error: RE_CODE.test(f.error || '') ? (f.error || '') : 'unexpected'
    };
    return st;
}

function readStatus(path) {
    var fm = $.NSFileManager.defaultManager;
    var at = fm.attributesOfItemAtPathError(path, null);
    if (!at || at.isNil()) return null;
    if (at.fileSize > CFG.max_bytes) return null;
    var s = $.NSString.stringWithContentsOfFileEncodingError(path, $.NSUTF8StringEncoding, null);
    if (!s || s.isNil()) return null;
    return parseStatus(ObjC.unwrap(s));
}

function stageIndex(step) {
    if (!step) return -1;
    for (var i = 0; i < CFG.stages.length; i++) {
        if (CFG.stages[i][1].indexOf(step) >= 0) return i;
    }
    return -1;
}

// Tek dilde gorunum: YALNIZ durum dosyasi + gercek saat.
function viewLang(L, st, ctx) {
    var t = CFG.texts[L], v = {};
    var result = st ? st.result : 'running', err = st ? st.error : '';
    if (ctx.helperGone && result === 'running') { result = 'failed'; err = 'helper_gone'; }
    v.final = result === 'ok' ? 'ok' : (result === 'running' ? 'running' : 'failed');
    v.title = v.final === 'running' ? t['title'] : t['window.title.' + v.final];
    v.heading = v.final === 'running' ? t['window.heading']
        : (v.final === 'ok' ? t['window.heading.ok'] : t['window.heading.failed']);
    var fv = st ? st.from_version : '', tv = st ? st.to_version : '';
    v.versions = (fv && tv) ? fmt(t['window.versions'], {from: fv, to: tv})
        : (tv ? fmt(t['window.version_to'], {to: tv}) : '');
    var step = st ? st.step : null, cur = stageIndex(step);
    // Geri yukleme bitince hatali asama "yeni surum aciliyor"dur; o satir
    // kendi adiyla isaretlenir (neden satiri geri yuklemeyi anlatir).
    var subOk = !(v.final !== 'running' && (step === 'restoring' || step === 'restored'));
    v.stages = [];
    for (var i = 0; i < CFG.stages.length; i++) {
        var own = CFG.stages[i][0];
        var text = (i === cur && subOk && t['step.' + step]) ? t['step.' + step] : t['step.' + own];
        var mark;
        if (v.final === 'ok') mark = 'done';
        else if (cur < 0) mark = 'pending';
        else if (i < cur) mark = 'done';
        else if (i === cur) mark = v.final === 'running' ? 'current' : 'error';
        else mark = 'pending';
        v.stages.push({mark: mark, text: text});
    }
    v.detail = '';
    v.fraction = null;
    if (v.final === 'running') {
        if (cur < 0) {
            v.detail = t['step.unknown'];
        } else if (step === 'copying' && st.total_kb) {
            if (st.done_kb !== null) {
                v.detail = fmt(t['progress'], {done: mbText(st.done_kb, L), total: mbText(st.total_kb, L)});
                if (st.done_kb >= 0 && st.done_kb <= st.total_kb) v.fraction = st.done_kb / st.total_kb;
            } else {
                v.detail = fmt(t['progress_total'], {total: mbText(st.total_kb, L)});
            }
        }
    }
    var t0 = (st && st.started !== null) ? st.started : ctx.windowStart;
    var t1 = ctx.finalAt !== null ? ctx.finalAt : ctx.now;
    var sn = Math.max(0, Math.floor(t1 - t0));
    v.elapsed = fmt(t['elapsed'], {min: Math.floor(sn / 60), sec: sn % 60});
    v.long = (v.final === 'running' && sn > CFG.max_age_s)
        ? fmt(t['window.long'], {min: Math.round(CFG.max_age_s / 60)}) : '';
    v.ok = v.final === 'ok' ? t['window.ok'] : '';
    v.reason = '';
    v.action = '';
    v.installer = '';
    if (v.final === 'failed') {
        var r = t['window.reason.' + err] || t['window.reason.unexpected'];
        v.reason = fmt(r, {exit_wait: CFG.exit_wait_s, verify: CFG.verify_s});
        v.action = t['window.action.' + (CFG.actions[err] || 'manual')];
        if (ctx.installer) v.installer = fmt(t['window.installer'], {path: tilde(ctx.installer)});
    }
    v.hint = v.final === 'running' ? t['window.hint'] : '';
    v.log = (ctx.log && v.final !== 'ok') ? fmt(t['log'], {path: tilde(ctx.log)}) : '';
    v.close = t['window.close'];
    return v;
}

// Dil bilinmiyorsa EN + TR birlikte (self_install.update_waiting_view kurali).
function view(st, ctx) {
    var L = st ? st.lang : null;
    if (L) { var one = viewLang(L, st, ctx); one.lang = L; return one; }
    var en = viewLang('en', st, ctx), tr = viewLang('tr', st, ctx), v = {};
    for (var k in en) {
        if (k === 'stages') {
            v.stages = en.stages.map(function (s, i) {
                return {mark: s.mark, text: s.text + ' / ' + tr.stages[i].text};
            });
        } else if (typeof en[k] === 'string' && k !== 'final') {
            // Iki dilde ayni olan metin (orn. surum satiri) bir kez yazilir.
            v[k] = !en[k] ? '' : (en[k] === tr[k] ? en[k]
                : (k === 'title' || k === 'close' ? en[k] + ' / ' + tr[k] : en[k] + '\n' + tr[k]));
        } else {
            v[k] = en[k];
        }
    }
    v.lang = null;
    return v;
}

// ---- Cizim (AppKit) ----
function label(size, bold, color, selectable) {
    var l = $.NSTextField.wrappingLabelWithString('');
    l.font = bold ? $.NSFont.boldSystemFontOfSize(size) : $.NSFont.systemFontOfSize(size);
    l.textColor = color;
    l.selectable = !!selectable;
    if (selectable) l.cell.lineBreakMode = $.NSLineBreakByCharWrapping;
    l.hidden = true;
    return l;
}

function needH(l, w) {
    return Math.ceil(l.cell.cellSizeForBounds($.NSMakeRect(0, 0, w, 100000)).height);
}

function UI() {
    var C = $.NSColor;
    this.win = $.NSWindow.alloc.initWithContentRectStyleMaskBackingDefer(
        $.NSMakeRect(0, 0, W, 300), $.NSWindowStyleMaskTitled | $.NSWindowStyleMaskClosable,
        $.NSBackingStoreBuffered, false);
    this.win.releasedWhenClosed = false;
    var cv = this.win.contentView;
    this.f = {
        heading: label(15, true, C.labelColor),
        versions: label(13, false, C.secondaryLabelColor),
        detail: label(13, false, C.labelColor),
        elapsed: label(12, false, C.secondaryLabelColor),
        long: label(12, false, C.systemOrangeColor),
        ok: label(13, false, C.labelColor),
        reason: label(13, true, C.systemRedColor),
        action: label(13, false, C.labelColor),
        installer: label(12, false, C.secondaryLabelColor, true),
        hint: label(12, false, C.secondaryLabelColor),
        log: label(12, false, C.tertiaryLabelColor, true)
    };
    this.marks = [];
    this.stageText = [];
    for (var i = 0; i < CFG.stages.length; i++) {
        this.marks.push(label(13, true, C.secondaryLabelColor));
        this.stageText.push(label(13, false, C.labelColor));
    }
    this.bar = $.NSProgressIndicator.alloc.initWithFrame($.NSMakeRect(0, 0, TW, 12));
    this.bar.indeterminate = false;
    this.bar.minValue = 0;
    this.bar.maxValue = 1;
    this.bar.hidden = true;
    this.button = $.NSButton.buttonWithTitleTargetAction('Close', this.win, 'performClose:');
    this.button.keyEquivalent = '\r';
    this.button.hidden = true;
    var all = [];
    for (var k in this.f) all.push(this.f[k]);
    all = all.concat(this.marks, this.stageText, [this.bar, this.button]);
    for (var a = 0; a < all.length; a++) cv.addSubview(all[a]);
    this.shownKey = null;
}

UI.prototype.apply = function (v) {
    var f = this.f, C = $.NSColor;
    this.win.title = v.title;
    var set = function (l, s) { l.stringValue = s || ''; l.hidden = !s; };
    set(f.heading, v.heading); set(f.versions, v.versions); set(f.detail, v.detail);
    set(f.elapsed, v.elapsed); set(f.long, v.long); set(f.ok, v.ok); set(f.reason, v.reason);
    set(f.action, v.action); set(f.installer, v.installer); set(f.hint, v.hint); set(f.log, v.log);
    var renk = {done: C.systemGreenColor, current: C.controlAccentColor,
                error: C.systemRedColor, pending: C.tertiaryLabelColor};
    for (var i = 0; i < this.marks.length; i++) {
        var s = v.stages[i];
        set(this.marks[i], CFG.marks[s.mark]);
        this.marks[i].textColor = renk[s.mark];
        set(this.stageText[i], s.text);
        this.stageText[i].textColor = s.mark === 'pending' ? C.secondaryLabelColor : C.labelColor;
    }
    this.bar.hidden = (v.fraction === null);
    if (v.fraction !== null) this.bar.doubleValue = v.fraction;
    this.button.title = v.close;
    this.button.hidden = (v.final !== 'failed');
    this.layout();
    this.win.level = (v.final === 'running') ? $.NSFloatingWindowLevel : $.NSNormalWindowLevel;
};

// Yukaridan asagi dizilim; her etiketin yuksekligi kendi metninden olculur.
UI.prototype.layout = function () {
    var f = this.f, rows = [], self = this;
    var add = function (name, view, gap) { if (!view.hidden) rows.push({name: name, views: [view], gap: gap}); };
    add('heading', f.heading, 0);
    add('versions', f.versions, 4);
    for (var i = 0; i < this.marks.length; i++) {
        if (!this.stageText[i].hidden) rows.push({name: 'stage' + i, views: [this.marks[i], this.stageText[i]], gap: i === 0 ? 14 : 5, stage: true});
    }
    add('detail', f.detail, 12);
    if (!this.bar.hidden) rows.push({name: 'bar', views: [this.bar], gap: 6, bar: true});
    add('ok', f.ok, 12);
    add('reason', f.reason, 14);
    add('action', f.action, 6);
    add('installer', f.installer, 8);
    add('elapsed', f.elapsed, 12);
    add('long', f.long, 4);
    add('hint', f.hint, 10);
    add('log', f.log, 6);
    if (!this.button.hidden) rows.push({name: 'button', views: [this.button], gap: 14, button: true});
    var H = M, r;
    for (var a = 0; a < rows.length; a++) {
        r = rows[a];
        if (r.stage) r.h = Math.max(needH(r.views[0], MARK_W), needH(r.views[1], TW - MARK_W));
        else if (r.bar) r.h = 12;
        else if (r.button) r.h = Math.ceil(r.views[0].fittingSize.height);
        else r.h = needH(r.views[0], TW);
        H += (a ? r.gap : 0) + r.h;
    }
    H += M;
    var y = H - M;
    this.metrics = [];
    for (var b = 0; b < rows.length; b++) {
        r = rows[b];
        y -= (b ? r.gap : 0) + r.h;
        if (r.stage) {
            r.views[0].frame = $.NSMakeRect(M, y, MARK_W, r.h);
            r.views[1].frame = $.NSMakeRect(M + MARK_W, y, TW - MARK_W, r.h);
        } else if (r.button) {
            var bw = Math.max(90, Math.ceil(r.views[0].fittingSize.width));
            r.views[0].frame = $.NSMakeRect(W - M - bw, y, bw, r.h);
        } else {
            r.views[0].frame = $.NSMakeRect(M, y, TW, r.h);
        }
        for (var c = 0; c < r.views.length; c++) {
            var fr = r.views[c].frame, isText = !r.bar && !r.button;
            self.metrics.push({name: r.name + (r.views.length > 1 ? '.' + c : ''),
                x: fr.origin.x, y: fr.origin.y, w: fr.size.width, h: fr.size.height,
                need_h: isText ? needH(r.views[c], fr.size.width) : fr.size.height,
                font_px: isText ? r.views[c].font.pointSize : null,
                text: isText ? ObjC.unwrap(r.views[c].stringValue) : null});
        }
    }
    var old = this.win.frame, top = old.origin.y + old.size.height;
    var nf = this.win.frameRectForContentRect($.NSMakeRect(0, 0, W, H));
    this.win.setFrameDisplay($.NSMakeRect(old.origin.x, top - nf.size.height, nf.size.width, nf.size.height), true);
    this.contentH = H;
};

UI.prototype.snapshot = function (path) {
    var frame = this.win.contentView.superview;
    this.win.displayIfNeeded;
    var rep = frame.bitmapImageRepForCachingDisplayInRect(frame.bounds);
    frame.cacheDisplayInRectToBitmapImageRep(frame.bounds, rep);
    var data = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $());
    data.writeToFileAtomically(path, true);
};

function appendLine(path, line) {
    var fm = $.NSFileManager.defaultManager;
    if (!fm.fileExistsAtPath(path)) fm.createFileAtPathContentsAttributes(path, $.NSData.data, $());
    var h = $.NSFileHandle.fileHandleForWritingAtPath(path);
    if (!h || h.isNil()) return;
    h.seekToEndOfFile;
    h.writeData($(line + '\n').dataUsingEncoding($.NSUTF8StringEncoding));
    h.closeFile;
}

function nowS() { return Date.now() / 1000; }

function run(argv) {
    var o = {render: null, record: null, offscreen: false, now: null, alive: null};
    var a = [];
    for (var i = 0; i < argv.length; i++) {
        var x = argv[i];
        if (x === '--render') o.render = argv[++i];
        else if (x === '--record') o.record = argv[++i];
        else if (x === '--offscreen') o.offscreen = true;
        else if (x === '--now') o.now = parseFloat(argv[++i]);
        else if (x === '--alive') o.alive = argv[++i] === '1';
        else a.push(x);
    }
    var statusPath = a[0] || '', helperPid = parseInt(a[1] || '0', 10) || 0;
    var ctx = {log: a[2] || '', installer: a[3] || '', windowStart: nowS(),
               now: nowS(), finalAt: null, helperGone: false};
    var alive = function () { return helperPid > 0 && $.kill(helperPid, 0) === 0; };

    var app = $.NSApplication.sharedApplication;
    app.setActivationPolicy((o.render || o.offscreen) ? $.NSApplicationActivationPolicyProhibited
                                                      : $.NSApplicationActivationPolicyAccessory);
    app.finishLaunching;
    var ui = new UI();

    if (o.render) {
        var st0 = readStatus(statusPath);
        ctx.now = o.now !== null ? o.now : nowS();
        ctx.windowStart = ctx.now;
        ctx.helperGone = o.alive === false;
        if (st0 && st0.result !== 'running') ctx.finalAt = ctx.now;
        var v0 = view(st0, ctx);
        ui.apply(v0);
        ui.snapshot(o.render);
        return JSON.stringify({view: v0, metrics: ui.metrics, content_w: W, content_h: ui.contentH});
    }

    var shown = false, lastKey = null, n = 0, doneAt = null, lastTick = 0;
    var mask = $.NSEventMaskAny;
    for (;;) {
        var tnow = nowS();
        if (tnow - lastTick >= CFG.poll_s || lastTick === 0) {
            lastTick = tnow;
            // Once canlilik, SONRA durum: betik sonucu olmeden once yazar;
            // olu bulunduysa okunan durum sonucunu tasir (yarisma yok).
            var isAlive = alive();
            var st = readStatus(statusPath);
            if (st && st.pid && helperPid && st.pid !== helperPid) break;  // yeni bir guncelleme basladi
            ctx.now = tnow;
            if (!isAlive && (!st || st.result === 'running')) ctx.helperGone = true;
            var v = view(st, ctx);
            if (v.final !== 'running' && ctx.finalAt === null) { ctx.finalAt = tnow; v = view(st, ctx); }
            ui.apply(v);
            if (!shown) {
                ui.win.center;
                if (!o.offscreen) { ui.win.makeKeyAndOrderFront(null); app.activateIgnoringOtherApps(true); }
                shown = true;
            }
            if (o.record) {
                var copy = JSON.parse(JSON.stringify(v));
                delete copy.elapsed;
                var key = JSON.stringify(copy);
                if (key !== lastKey) {
                    lastKey = key;
                    n += 1;
                    var png = o.record + '/window_' + ('00' + n).slice(-3) + '.png';
                    ui.snapshot(png);
                    appendLine(o.record + '/window_states.jsonl',
                               JSON.stringify({t: tnow, n: n, png: png, view: v, metrics: ui.metrics}));
                }
            }
            // Basarida pencere kendiliginden kapanir; hatada kullanici kapatir
            // (--offscreen test kipinde kapatacak kullanici yok: o da kapanir).
            if ((v.final === 'ok' || (o.offscreen && v.final !== 'running')) && doneAt === null) doneAt = tnow;
            if (doneAt !== null && tnow - doneAt >= CFG.done_close_s) break;
        }
        var ev = app.nextEventMatchingMaskUntilDateInModeDequeue(
            mask, $.NSDate.dateWithTimeIntervalSinceNow(CFG.poll_s), $.NSDefaultRunLoopMode, true);
        if (ev && !ev.isNil()) app.sendEvent(ev);
        if (shown && !o.offscreen && !ui.win.isVisible) break;   // kullanici kapatti
    }
    if (o.record) appendLine(o.record + '/window_states.jsonl', JSON.stringify({t: nowS(), exit: true}));
    ui.win.orderOut(null);
    return '';
}
"""


def build_mac_window():
    """macOS güncelleme penceresi betiği (JXA, ASCII)."""
    js = MAC_WINDOW_JS.replace("/*@@CFG@@*/null", _cfg_json(MAC_STAGES), 1)
    js.encode("ascii")
    return js


# ---------------------------------------------------------------------------
# Windows — PowerShell 5.1 + WinForms
# ---------------------------------------------------------------------------

WIN_WINDOW_PS1 = r"""# HRMA guncelleme penceresi (Windows) - hrma/utils/update_window.py uretir.
# Sistemin powershell.exe'si ile calisir; uygulama paketine (Python) BAGLI
# DEGILDIR. Yalniz yardimci betigin yazdigi durum dosyasini okur; ilerleme
# yalniz olculen degerden (Windows betigi kopya miktari olcmez: adim + gecen sure).
param(
    [string]$Status = '',
    [string]$Installer = '',
    [string]$Log = '',
    [string]$Render = '',
    [double]$Now = 0,
    [int]$Alive = 1,
    [string]$Record = ''
)
$ErrorActionPreference = 'Stop'
$CFG = @'
@@CFG@@
'@ | ConvertFrom-Json
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

function NowS { return ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0) }

function Tx([string]$L, [string]$k) {
    $v = $CFG.texts.$L.$k
    if ($null -eq $v) { return '' }
    return [string]$v
}

function Fmt([string]$s, [hashtable]$o) {
    foreach ($k in $o.Keys) {
        $s = $s.Replace('{' + $k + ':02d}', ('{0:D2}' -f [int]$o[$k]))
        $s = $s.Replace('{' + $k + '}', [string]$o[$k])
    }
    return $s
}

function Read-Status {
    if (-not $Status) { return $null }
    $txt = $null
    try {
        $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
        $fs = [System.IO.File]::Open($Status, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, $share)
        try {
            if ($fs.Length -gt [int64]$CFG.max_bytes) { return $null }
            $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::ASCII)
            $txt = $sr.ReadToEnd()
        } finally { $fs.Dispose() }
    } catch { return $null }
    $lines = $txt -split "`r?`n"
    if ($lines.Count -lt 2 -or $lines[0].Trim() -ne $CFG.header) { return $null }
    $f = @{}
    $end = $false
    for ($i = 1; $i -lt $lines.Count; $i++) {
        $j = $lines[$i].IndexOf('=')
        if ($j -le 0) { continue }
        $k = $lines[$i].Substring(0, $j).Trim()
        $v = $lines[$i].Substring($j + 1).Trim()
        if ($k -eq 'end') { $end = ($v -eq '1'); continue }
        $f[$k] = $v
    }
    if (-not $end) { return $null }
    $st = @{}
    $st.step = if ($f['step'] -match '^[a-z_]{1,32}$') { $f['step'] } else { $null }
    $st.lang = if ($f['lang'] -eq 'tr' -or $f['lang'] -eq 'en') { $f['lang'] } else { $null }
    $st.from_version = if ($f['from_version'] -match '^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$') { $f['from_version'] } else { '' }
    $st.to_version = if ($f['to_version'] -match '^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$') { $f['to_version'] } else { '' }
    $st.result = if ($CFG.results -contains $f['result']) { $f['result'] } else { 'running' }
    $st.error = if ($f['error'] -match '^[a-z_]{0,40}$') { [string]$f['error'] } else { 'unexpected' }
    return $st
}

function Stage-Index($step) {
    if (-not $step) { return -1 }
    for ($i = 0; $i -lt $CFG.stages.Count; $i++) {
        if ($CFG.stages[$i][1] -contains $step) { return $i }
    }
    return -1
}

# Tek dilde gorunum: YALNIZ durum dosyasi + gercek saat.
function View-Lang([string]$L, $st, $ctx) {
    $v = @{}
    $result = if ($st) { $st.result } else { 'running' }
    $err = if ($st) { $st.error } else { '' }
    if ($ctx.helperGone -and $result -eq 'running') { $result = 'failed'; $err = 'helper_gone' }
    $v.final = if ($result -eq 'ok') { 'ok' } elseif ($result -eq 'running') { 'running' } else { 'failed' }
    $v.title = if ($v.final -eq 'running') { Tx $L 'title' } else { Tx $L ('window.title.' + $v.final) }
    $v.heading = if ($v.final -eq 'running') { Tx $L 'window.heading' } elseif ($v.final -eq 'ok') { Tx $L 'window.heading.ok' } else { Tx $L 'window.heading.failed' }
    $fv = if ($st) { $st.from_version } else { '' }
    $tv = if ($st) { $st.to_version } else { '' }
    $v.versions = if ($fv -and $tv) { Fmt (Tx $L 'window.versions') @{ 'from' = $fv; 'to' = $tv } } elseif ($tv) { Fmt (Tx $L 'window.version_to') @{ 'to' = $tv } } else { '' }
    $step = if ($st) { $st.step } else { $null }
    $cur = Stage-Index $step
    $v.stages = @()
    for ($i = 0; $i -lt $CFG.stages.Count; $i++) {
        $own = $CFG.stages[$i][0]
        $text = if ($i -eq $cur -and (Tx $L ('step.' + $step))) { Tx $L ('step.' + $step) } else { Tx $L ('step.' + $own) }
        if ($v.final -eq 'ok') { $mark = 'done' }
        elseif ($cur -lt 0) { $mark = 'pending' }
        elseif ($i -lt $cur) { $mark = 'done' }
        elseif ($i -eq $cur) { $mark = if ($v.final -eq 'running') { 'current' } else { 'error' } }
        else { $mark = 'pending' }
        $v.stages += ,@{ 'mark' = $mark; 'text' = $text }
    }
    $v.detail = if ($v.final -eq 'running' -and $cur -lt 0) { Tx $L 'step.unknown' } else { '' }
    $t1 = if ($null -ne $ctx.finalAt) { $ctx.finalAt } else { $ctx.now }
    $sn = [int][Math]::Max(0, [Math]::Floor($t1 - $ctx.windowStart))
    $v.elapsed = Fmt (Tx $L 'elapsed') @{ 'min' = [int][Math]::Floor($sn / 60); 'sec' = ($sn % 60) }
    $v.long = if ($v.final -eq 'running' -and $sn -gt [int]$CFG.max_age_s) { Fmt (Tx $L 'window.long') @{ 'min' = [int][Math]::Round($CFG.max_age_s / 60) } } else { '' }
    $v.ok = if ($v.final -eq 'ok') { Tx $L 'window.ok' } else { '' }
    $v.reason = ''; $v.action = ''; $v.installer = ''
    if ($v.final -eq 'failed') {
        $r = Tx $L ('window.reason.' + $err)
        if (-not $r) { $r = Tx $L 'window.reason.unexpected' }
        $v.reason = Fmt $r @{ 'exit_wait' = $CFG.exit_wait_s; 'verify' = $CFG.verify_s }
        $act = $CFG.actions.$err
        if (-not $act) { $act = 'manual' }
        $v.action = Tx $L ('window.action.' + $act)
        if ($Installer) { $v.installer = Fmt (Tx $L 'window.installer') @{ 'path' = $Installer } }
    }
    $v.hint = if ($v.final -eq 'running') { Tx $L 'window.hint' } else { '' }
    $v.log = if ($Log -and $v.final -ne 'ok') { Fmt (Tx $L 'log') @{ 'path' = $Log } } else { '' }
    $v.close = Tx $L 'window.close'
    return $v
}

# Dil bilinmiyorsa EN + TR birlikte (self_install.update_waiting_view kurali).
function View($st, $ctx) {
    $L = if ($st) { $st.lang } else { $null }
    if ($L) { $one = View-Lang $L $st $ctx; $one.lang = $L; return $one }
    $en = View-Lang 'en' $st $ctx
    $tr = View-Lang 'tr' $st $ctx
    $v = @{}
    foreach ($k in $en.Keys) {
        if ($k -eq 'stages') {
            $v.stages = @()
            for ($i = 0; $i -lt $en.stages.Count; $i++) {
                $v.stages += ,@{ 'mark' = $en.stages[$i].mark; 'text' = ($en.stages[$i].text + ' / ' + $tr.stages[$i].text) }
            }
        } elseif ($k -eq 'final') { $v.final = $en.final }
        elseif ($en[$k] -and $en[$k] -eq $tr[$k]) { $v[$k] = $en[$k] }
        elseif ($en[$k]) {
            $sep = if ($k -eq 'title' -or $k -eq 'close') { ' / ' } else { "`n" }
            $v[$k] = $en[$k] + $sep + $tr[$k]
        } else { $v[$k] = '' }
    }
    $v.lang = $null
    return $v
}

# ---- Cizim (WinForms) ----
$script:W = 480
function New-Lbl([single]$pt, [bool]$bold, $color, [string]$font = 'Segoe UI') {
    $l = New-Object System.Windows.Forms.Label
    $l.AutoSize = $true
    $l.UseMnemonic = $false
    $l.MaximumSize = New-Object System.Drawing.Size(($script:W - 44), 0)
    $style = if ($bold) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
    $l.Font = New-Object System.Drawing.Font($font, $pt, $style)
    $l.ForeColor = $color
    $l.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 6)
    $l.Visible = $false
    return $l
}

$form = New-Object System.Windows.Forms.Form
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.AutoSize = $true
$form.AutoSizeMode = [System.Windows.Forms.AutoSizeMode]::GrowAndShrink
$form.ShowInTaskbar = $true
try {
    $ico = Join-Path (Split-Path (Split-Path $Status)) 'hrma.ico'
    if (Test-Path -LiteralPath $ico) {
        $ms = New-Object System.IO.MemoryStream(, [System.IO.File]::ReadAllBytes($ico))
        $form.Icon = New-Object System.Drawing.Icon($ms)
    }
} catch { }
$panel = New-Object System.Windows.Forms.FlowLayoutPanel
$panel.FlowDirection = [System.Windows.Forms.FlowDirection]::TopDown
$panel.WrapContents = $false
$panel.AutoSize = $true
$panel.AutoSizeMode = [System.Windows.Forms.AutoSizeMode]::GrowAndShrink
$panel.Padding = New-Object System.Windows.Forms.Padding(22, 18, 22, 18)
$panel.MinimumSize = New-Object System.Drawing.Size($script:W, 0)
$form.Controls.Add($panel)

$grey = [System.Drawing.SystemColors]::GrayText
$text = [System.Drawing.SystemColors]::ControlText
$F = [ordered]@{}
$F.heading = New-Lbl 12 $true $text
$F.versions = New-Lbl 10 $false $grey
$panel.Controls.Add($F.heading); $panel.Controls.Add($F.versions)
$script:marks = @(); $script:stageText = @(); $script:rows = @()
for ($i = 0; $i -lt $CFG.stages.Count; $i++) {
    $row = New-Object System.Windows.Forms.FlowLayoutPanel
    $row.FlowDirection = [System.Windows.Forms.FlowDirection]::LeftToRight
    $row.WrapContents = $false
    $row.AutoSize = $true
    $row.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 2)
    $m = New-Lbl 10 $true $grey 'Segoe UI Symbol'
    $m.MinimumSize = New-Object System.Drawing.Size(20, 0)
    $m.Visible = $true
    $t = New-Lbl 10 $false $text
    $t.MaximumSize = New-Object System.Drawing.Size(($script:W - 70), 0)
    $t.Visible = $true
    $row.Controls.Add($m); $row.Controls.Add($t)
    $panel.Controls.Add($row)
    $script:marks += $m; $script:stageText += $t; $script:rows += $row
}
foreach ($n in @('detail', 'ok', 'reason', 'action', 'installer', 'elapsed', 'long', 'hint', 'log')) {
    $pt = if ($n -in @('installer', 'elapsed', 'hint', 'log', 'long')) { 9 } else { 10 }
    $col = if ($n -eq 'reason') { [System.Drawing.Color]::Firebrick } elseif ($n -eq 'long') { [System.Drawing.Color]::DarkOrange } elseif ($n -in @('installer', 'elapsed', 'hint', 'log')) { $grey } else { $text }
    $F[$n] = New-Lbl $pt ($n -eq 'reason') $col
    $panel.Controls.Add($F[$n])
}
$btn = New-Object System.Windows.Forms.Button
$btn.AutoSize = $true
$btn.Visible = $false
$btn.Add_Click({ $form.Close() })
$panel.Controls.Add($btn)
$form.AcceptButton = $btn

function Apply($v) {
    $form.Text = $v.title
    foreach ($k in @($F.Keys)) {
        $F[$k].Text = [string]$v[$k]
        $F[$k].Visible = [bool]$v[$k]
    }
    $renk = @{ 'done' = [System.Drawing.Color]::ForestGreen; 'current' = [System.Drawing.SystemColors]::Highlight; 'error' = [System.Drawing.Color]::Firebrick; 'pending' = $grey }
    for ($i = 0; $i -lt $script:marks.Count; $i++) {
        $s = $v.stages[$i]
        $script:marks[$i].Text = [string]$CFG.marks.($s.mark)
        $script:marks[$i].ForeColor = $renk[$s.mark]
        $script:stageText[$i].Text = $s.text
        $script:stageText[$i].ForeColor = if ($s.mark -eq 'pending') { $grey } else { $text }
    }
    $btn.Text = $v.close
    $btn.Visible = ($v.final -eq 'failed')
    $form.TopMost = ($v.final -eq 'running')
}

function Metrics {
    $out = @()
    $all = @($F.Values) + $script:marks + $script:stageText + @($btn)
    foreach ($c in $all) {
        if (-not $c.Visible) { continue }
        $p = $form.PointToClient($c.PointToScreen([System.Drawing.Point]::Empty))
        $pref = $c.GetPreferredSize((New-Object System.Drawing.Size($c.Width, 0)))
        $out += @{ 'text' = $c.Text; 'x' = $p.X; 'y' = $p.Y; 'w' = $c.Width; 'h' = $c.Height; 'need_h' = $pref.Height; 'font_px' = [Math]::Round($c.Font.SizeInPoints * 96 / 72, 1) }
    }
    return $out
}

function Snap([string]$png) {
    $bmp = New-Object System.Drawing.Bitmap($form.Width, $form.Height)
    try {
        $form.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
        $bmp.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $bmp.Dispose() }
}

# Yardimci canlilik: pencereyi baslatan cmd.exe (bu surecin ebeveyni).
$script:helperPid = 0
$script:helperStart = $null
try {
    $me = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID)
    $script:helperPid = [int]$me.ParentProcessId
    $script:helperStart = (Get-Process -Id $script:helperPid -ErrorAction Stop).StartTime
} catch { $script:helperPid = 0 }
function Helper-Alive {
    if ($script:helperPid -le 0) { return $true }
    $p = Get-Process -Id $script:helperPid -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    try { return ($p.StartTime -eq $script:helperStart) } catch { return $true }
}

$script:ctx = @{ 'windowStart' = (NowS); 'now' = (NowS); 'finalAt' = $null; 'helperGone' = $false }

if ($Render) {
    $st0 = Read-Status
    $script:ctx.now = if ($Now -gt 0) { $Now } else { NowS }
    $script:ctx.windowStart = $script:ctx.now
    $script:ctx.helperGone = ($Alive -eq 0)
    if ($st0 -and $st0.result -ne 'running') { $script:ctx.finalAt = $script:ctx.now }
    $v0 = View $st0 $script:ctx
    Apply $v0
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.Location = New-Object System.Drawing.Point(-32000, -32000)
    $form.ShowInTaskbar = $false
    $form.Show()
    [System.Windows.Forms.Application]::DoEvents()
    Snap $Render
    @{ 'view' = $v0; 'metrics' = (Metrics); 'client_w' = $form.ClientSize.Width; 'client_h' = $form.ClientSize.Height } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ($Render + '.json') -Encoding UTF8
    $form.Close()
    exit 0
}

$script:lastKey = $null
$script:n = 0
$script:doneAt = $null
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = [int]([double]$CFG.poll_s * 1000)
$timer.Add_Tick({
    try {
        $isAlive = Helper-Alive
        $st = Read-Status
        $script:ctx.now = NowS
        if (-not $isAlive -and (-not $st -or $st.result -eq 'running')) { $script:ctx.helperGone = $true }
        $v = View $st $script:ctx
        if ($v.final -ne 'running' -and $null -eq $script:ctx.finalAt) { $script:ctx.finalAt = $script:ctx.now; $v = View $st $script:ctx }
        Apply $v
        if ($Record) {
            $copy = @{}; foreach ($k in $v.Keys) { if ($k -ne 'elapsed') { $copy[$k] = $v[$k] } }
            $key = $copy | ConvertTo-Json -Depth 6 -Compress
            if ($key -ne $script:lastKey) {
                $script:lastKey = $key
                $script:n += 1
                $png = $Record + ('.{0:D3}.png' -f $script:n)
                Snap $png
                $line = @{ 't' = $script:ctx.now; 'n' = $script:n; 'png' = $png; 'view' = $v; 'metrics' = (Metrics) } | ConvertTo-Json -Depth 6 -Compress
                Add-Content -LiteralPath $Record -Value $line -Encoding UTF8
            }
        }
        if ($v.final -eq 'ok' -and $null -eq $script:doneAt) { $script:doneAt = $script:ctx.now }
        if ($null -ne $script:doneAt -and ($script:ctx.now - $script:doneAt) -ge [double]$CFG.done_close_s) { $timer.Stop(); $form.Close() }
    } catch { }
})
$v1 = View (Read-Status) $script:ctx
Apply $v1
$form.Add_Shown({ $form.Activate(); $timer.Start() })
[System.Windows.Forms.Application]::Run($form)
if ($Record) { Add-Content -LiteralPath $Record -Value (@{ 't' = (NowS); 'exit' = $true } | ConvertTo-Json -Compress) -Encoding UTF8 }
"""


def build_win_window():
    """Windows güncelleme penceresi betiği (PowerShell 5.1, ASCII, CRLF)."""
    ps = WIN_WINDOW_PS1.replace("@@CFG@@", _cfg_json(WIN_STAGES), 1)
    ps.encode("ascii")
    return "\r\n".join(ps.split("\n"))
