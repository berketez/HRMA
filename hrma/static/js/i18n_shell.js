/* HRMA kabuk sözlüğü — i18n_shell.js
 * ---------------------------------------------------------------
 * Ana sayfa kabuğuna sonradan eklenen ögelerin çevirileri:
 *   - aux-links satırındaki "Sürüm Notları" ve "Ayarlar" bağlantıları
 *   - Sürüm Notları modalı (release_notes.js)
 *   - Ayarlar paneli (settings_panel.js)
 * Kalıp: i18n.js başlığındaki ÇOK-PARÇALI SÖZLÜK SÖZLEŞMESİ — birebir.
 * Sürüm notu GÖVDESİ bilinçli olarak çevrilmez (ham release metni).
 */
(function (global) {
    'use strict';
    var DICT = {
        en: {
            'link.releaseNotes': 'Release Notes',
            'link.settings': 'Settings',
            'link.userGuide': 'User Guide',
            'guide.opened': 'The user guide PDF was opened in the PDF viewer of the computer running HRMA.',
            'guide.notLaunched': 'No PDF viewer was launched by the server; open the user guide here:',
            'guide.notPackaged': 'The user guide PDF is not packaged with this installation; the online copy:',
            'guide.openInBrowser': 'Open the PDF in the browser',
            'guide.close': 'Close',

            'shell.close': 'Close',

            /* ÖH D18 / P12aB4-08 — STEP ölçü eşleme ekranının BEŞ alan
             * etiketi hiçbir sözlükte yoktu; `I18N.t` yedek metne düştüğü
             * için TR kipinde tümü Türkçe olan bir ekranda beş sayısal alan
             * İngilizce etiketle onaylanıyordu (ölçüldü: 33 anahtarın 5 tanesi).
             * Anahtarlar `step_import_ui.js` SUGGESTION_KEYS dizisinde ÇIPLAK
             * DİZE olarak yaşadığı için mevcut bekçi de göremiyordu; bekçinin
             * ön ek beyaz listesine 'stepimp' eklendi (tests/test_i18n_common.py).
             * Aynı ailenin `stepimp.refuseSolidChamberLen` girdisi de bu
             * dosyada duruyor — parça seçimi ürün davranışını değiştirmez,
             * register() bütün parçaları tek tabloda birleştirir. */
            'stepimp.fieldThroat': 'Throat diameter (mm)',
            'stepimp.fieldExit': 'Exit diameter (mm)',
            'stepimp.fieldChamberD': 'Chamber diameter (mm)',
            'stepimp.fieldChamberL': 'Chamber length (mm)',
            'stepimp.fieldWall': 'Wall thickness (mm)',

            'shell.releaseNotes.title': 'RELEASE NOTES',
            'shell.releaseNotes.loading': 'Loading release notes…',
            'shell.releaseNotes.empty': 'No release notes found.',
            'shell.releaseNotes.error': 'Release notes could not be loaded.',

            'shell.settings.title': 'SETTINGS',
            'shell.settings.language': 'Language',
            'shell.settings.languageDesc': 'Interface language. The selector on the home page stays in sync.',
            'shell.settings.updates': 'Updates',
            'shell.settings.autoCheck': 'Check for updates at startup',
            'shell.settings.autoCheckDesc': 'When off, HRMA does not contact the update server at startup.',
            'shell.settings.checkNow': 'Check now',
            'shell.settings.checking': 'Checking…',
            'shell.settings.upToDate': 'You are up to date: v{version}',
            'shell.settings.updateFound': 'New version found: v{version} — opening the update window.',
            'shell.settings.updateFoundNoWindow': 'New version found: v{version} — the update window is unavailable on this page.',
            'shell.settings.checkFailed': 'Could not reach the update server.',
            'shell.settings.rateLimited': 'GitHub is rate limiting this network — try again in a few minutes.',

            /* ÖH D27 / OH-D26-18 — sürüm bilgisinin KAYNAĞI. `/api/update/check`
             * `source` yayımlıyor ("api" | "page" yedek sayfa kazıması | null)
             * ama ne ayarlar paneli ne güncelleme penceresi basıyordu: API üzerinden
             * okunan sürümle yedek kazımadan okunan sürüm ekranda aynıydı.
             * Aile `update.*` ama sözlük parçası BURASI: i18n_common.js
             * advanced/liquid/solid sayfalarında güverte tarafından SONRADAN
             * yükleniyor, i18n_shell.js ise altı sayfanın hepsinde şablondan
             * geliyor (bkz. update_check.js `sourceNote`). */
            'update.sourceApi': 'Version data was read from the GitHub Releases API.',
            'update.sourcePage': 'The Releases API could not be reached, so version data was read from the releases page instead (fallback path).',
            'update.sourceNone': 'The server reported no source for this version information.',
            'update.sourceMissing': 'The server did not report where this version information came from.',
            'update.sourceOther': 'Version information source reported by the server: {code} (unknown to this version).',
            'update.sourceRaw': 'Version information source reported by the server: {code}.',

            'shell.settings.skippedVersion': 'Skipped version: v{version}',
            'shell.settings.noSkipped': 'No skipped version.',
            'shell.settings.skipReset': 'Reset skipped version',
            'shell.settings.skipCleared': 'Skipped version cleared — it will be offered again.',
            'shell.settings.app': 'Application',
            'shell.settings.version': 'Version',
            /* ÖH D20 / P12aB5-08 — sürüm okunamadığında panel artık çıplak
             * "v?" basmıyor; DENENEN KAYNAKLARI söylüyor (bug_report.js dosyasının
             * kayda yazdığı beyanın aynısı). Uydurma sürüm yok. */
            'shell.settings.versionUnknown': 'could not be read',
            'shell.settings.versionBasis': 'sources tried: {sources}',

            /* ÖH D20 / P12aB4-11 — kaydedilmemiş değişiklikleri ATAN onayın
             * düğmesi nötr 'OK' idi; yıkıcı eylem iptal kadar açık
             * adlandırılır (aynı desen: 'proj.btnOverwrite').
             * ÖH D20 / P12aB4-16 — ayrılmış Windows aygıt adı reddinin
             * GEREKÇESİ; genel 'kurala bakın' uyarısı yerine geçer. */
            'proj.btnDiscard': 'Discard changes',
            'proj.nameReserved': 'This name is reserved by Windows for a device (CON, PRN, AUX, NUL, COM1-9, LPT1-9) and cannot be used as a file name.',
            'shell.settings.githubLink': 'HRMA on GitHub',

            /* ÖH D17 / P12aB5-01 — "Hata bildir" bölümü.
             * settings_panel.js + bug_report.js 47 `shell.bug.*` anahtarı
             * çağırıyordu; HİÇBİRİ hiçbir sözlükte tanımlı değildi, yani
             * Türkçe arayüzde bölümün TAMAMI İngilizce kalıyordu — aynı
             * pencerenin "Güncellemeler" bölümü Türkçeleşirken. Ağırlığı
             * yalnız çevrilmemiş metin değil: tanılama onay kutusunun
             * GİZLİLİK BEYANI da (`shell.bug.diagnosticsDesc`) İngilizce
             * kalıyordu, yani rızanın dayandığı cümle okunamıyordu.
             * Ayrıca `warn.bugreport.*` uyarı pilleri (settings_panel.js
             * WARN_FALLBACK) da tanımsızdı. */
            /* ÖH D17 / P12aB4-01 — katı sayfasında oda boyunun ADLI reddi;
             * P12aB4-02 — sunucu uyarılarıyla yüklenen proje bildirimi.
             * (stepimp.* / proj.* ailesinin gövdesi i18n_common.js içinde; bu
             * dalgada o dosya arayüz kulvarının sahasında olduğu için yeni
             * anahtarlar kabuk sözlüğüne yazıldı — çakışma yok.) */
            'stepimp.refuseSolidChamberLen': 'Not applied: this page has no chamber length field. The only length input is the grain length (one propellant grain), which is a different quantity \u2014 enter it yourself.',
            'proj.loadedWithWarnings': 'Project "{name}" loaded with {n} warning(s) \u2014 see above.',
            'update.statusUnreachable': 'Update status could not be read — the download may not have finished. Use the browser link below instead.',
            'shell.bug.section': 'Report a bug',
            'shell.bug.intro': 'Fill this in and HRMA opens a pre-filled issue on GitHub in a new tab. Nothing is sent automatically — you review the text and submit it with your own GitHub account.',
            'shell.bug.titleLabel': 'Title',
            'shell.bug.titlePlaceholder': 'Short summary of the problem',
            'shell.bug.whatLabel': 'What happened?',
            'shell.bug.whatPlaceholder': 'Describe what went wrong.',
            'shell.bug.expectedLabel': 'What did you expect?',
            'shell.bug.expectedPlaceholder': 'What should have happened instead?',
            'shell.bug.stepsLabel': 'Steps to reproduce',
            'shell.bug.stepsPlaceholder': '1. Open the hybrid page\n2. Enter …\n3. Press Calculate',
            'shell.bug.diagnostics': 'Attach diagnostic information',
            'shell.bug.diagnosticsDesc': 'Adds the numeric inputs on this page and the console errors captured after it loaded. File paths, user names, e-mail addresses and geographic coordinates (launch site latitude/longitude) are removed. Off unless you turn it on.',
            'shell.bug.preview': 'Preview',
            'shell.bug.previewTitle': 'This exact text will be sent',
            'shell.bug.previewHint': 'You can still edit it. HRMA opens GitHub with this text pre-filled; you press \"Submit new issue\" there.',
            'shell.bug.urlLabel': 'Issue link',
            'shell.bug.help.title': 'Issue title, at most 256 characters (GitHub\'s limit). Nothing is sent from here: after the mandatory preview HRMA opens a pre-filled GitHub issue page and you submit it with your own account.',
            'shell.bug.help.what': 'Free text: what went wrong. It becomes a section of the issue body, which you see and can edit in the preview.',
            'shell.bug.help.expected': 'Free text: what should have happened instead. It becomes a section of the issue body, shown in the preview.',
            'shell.bug.help.steps': 'Free text: the steps that reproduce the problem. It becomes a section of the issue body, shown in the preview.',
            'shell.bug.help.diagnostics': 'Off by default. When ticked, only numeric inputs and cleaned console lines are added to the body; home folder/user name, e-mail, file paths, token-like strings and geographic coordinates are removed. Everything is shown in the preview before anything leaves HRMA.',
            'shell.bug.help.previewTitle': 'The title exactly as it will be put into the GitHub issue page; you can still edit it here.',
            'shell.bug.help.body': 'The issue body exactly as it will be put into the GitHub issue page; you can still edit it. If it is too long for the link, it is shortened here in the preview, never silently afterwards.',
            'shell.bug.help.url': 'Read-only copy of the pre-filled GitHub issue link, shown when the new tab was blocked; copy it into your browser.',
            'shell.bug.charCount': '{chars} characters — issue link {url} / {limit}',
            'shell.bug.openGithub': 'Open on GitHub',
            'shell.bug.back': 'Back',
            'shell.bug.needTitle': 'Please write a title.',
            'shell.bug.needWhat': 'Please describe what happened.',
            'shell.bug.previewRequired': 'Preview the report before opening it.',
            'shell.bug.reviewAgain': 'The text was shortened to fit the link limit — check it and press the button again.',
            'shell.bug.opened': 'GitHub opened in a new tab — check the text there and press \"Submit new issue\".',
            'shell.bug.openFailed': 'The browser did not open a new tab. Copy the link below and open it yourself.',
            'shell.bug.body.what': 'What happened',
            'shell.bug.body.expected': 'What was expected',
            'shell.bug.body.steps': 'Steps to reproduce',
            'shell.bug.body.env': 'Environment',
            'shell.bug.body.os': 'Operating system',
            'shell.bug.body.browser': 'Browser',
            'shell.bug.body.page': 'Page',
            'shell.bug.body.uiLang': 'Interface language',
            'shell.bug.body.engine': 'Engine type',
            'shell.bug.body.diagnostics': 'Diagnostics',
            'shell.bug.body.diagnosticsOff': 'Diagnostic information was not attached (the reporter left the box unchecked).',
            'shell.bug.body.inputs': 'Numeric inputs',
            'shell.bug.body.inputsNone': 'No numeric input was found on this page.',
            /* ÖH D18 / P12aB5-04 + P12aB5-05 — girdi listesinin kırpma ve
             * geri tutma beyanları. Değerleri kodun TAM yedek metniyle
             * birebirdir (parça-kopya bekçisi). */
            'shell.bug.body.inputsTruncated': 'Listed: the first {shown} of {total} numeric fields ({dropped} not listed). The list is capped at {limit} entries so the issue link stays inside the URL limit.',
            'shell.bug.body.inputsGeoWithheld': 'Withheld: {count} geographic coordinate field(s) ({ids}). The launch site position is not sent to a public issue — describe the location in words if it matters.',
            'shell.bug.body.field': 'Field',
            'shell.bug.body.value': 'Value',
            'shell.bug.body.console': 'Console errors',
            'shell.bug.body.consoleNone': 'No console error was captured after this page loaded.',
            'shell.bug.body.redactNote': 'File paths, user names and e-mail addresses were removed from the log.',
            'shell.bug.body.truncated': 'The diagnostic log was shortened by {chars} characters so the issue link stays under the {limit}-character URL limit.',
            'shell.bug.body.blank': '(not filled in)',
            'shell.bug.body.unknown': 'unknown',
            'shell.bug.body.versionMissing': 'this page does not expose the version',

            /* ÖH D17 / P12aB3-02 + P12aB3-09 — grafik altyazıları.
             * injectorFace: eski 'chartCap.injector_plot' delik YERLEŞİMİNİN
             * basınç düşümünü belirlediğini söylüyordu; ölçüm 26 sayısal
             * alanın 0'ının değiştiğini gösteriyor. Eski anahtarın TR
             * karşılığı i18n_common.js'te ve i18n 'ilk kazanır' kuralıyla
             * ezilemediği için anahtar yeniden adlandırıldı.
             * Kalan 7 anahtar: sabit id ile çizilip açıklamasız kalan
             * grafikler (iki Monte Carlo histogramı, iki CAD görünümü). */
            'chartCap.injectorFace': 'Face and flow schematic of the selected injector type: orifice layout, hole count and hole diameter. The face pattern is drawing only — changing it moves no computed number; pressure drop and atomization follow from hole diameter, hole count and mass flow.',
            'chartCap.solid_motor_kesit': 'Scaled cross-section of the solid motor: case, propellant grain, core port and nozzle with key dimensions. Use it to sanity-check proportions before CAD export or manufacturing.',
            'chartCap.liquid_motor_kesit': 'Scaled cross-section of the liquid engine: chamber, injector face, throat and nozzle with key dimensions. Use it to sanity-check proportions before CAD export or manufacturing.',
            'chartCap.mc_hist_thrust': 'Monte Carlo thrust distribution: one bar per bin over the sampled runs, with the nominal design value marked. Width shows how sensitive thrust is to the input tolerances you entered — it is not a manufacturing guarantee.',
            'chartCap.mc_hist_isp': 'Monte Carlo sea-level specific impulse distribution over the sampled runs, with the nominal design value marked. Read the spread as the effect of the input tolerances, not as a measured scatter.',
            'chartCap.altitude_plot': 'Delivered specific impulse vs altitude: as ambient pressure falls, Isp rises toward its vacuum value. The curve uses the standard atmosphere, not local site conditions.',
            'chartCap.altitude_preview': 'Ambient pressure vs altitude over the sweep you entered (alt_start to alt_end, alt_points samples), computed from the built-in US Standard Atmosphere 1976 model. It is neither a flight profile nor a solver result — no number here comes from the engine solution.',
            'chartCap.cad_visualization': 'CAD view generated from the solved geometry. It is a drawing of the dimensions listed in the design table — tolerances, fillets and joints are not modelled and it is not a manufacturing drawing.',
            'chartCap.cad_3d_view': 'Interactive 3D CAD view of the solved motor geometry. Drag to rotate, scroll to zoom. Tolerances, fillets and joints are not modelled — it is not a manufacturing drawing.',
            'warn.bugreport.body_truncated': 'The diagnostic log was shortened to fit the issue link length limit ({chars} characters removed).',
            'warn.bugreport.inputs_truncated': 'The numeric input list was capped at {limit} entries; {dropped} field(s) are not listed.',
            'warn.bugreport.geo_withheld': 'Geographic coordinate fields were withheld from the report ({count} field(s)).',
            'warn.bugreport.title_truncated': 'The title was shortened to the {limit}-character GitHub limit.',
            'warn.bugreport.preview_required': 'The report can only be opened after it has been previewed.',
            /* ÖH D22 / P12aB4-24 — proje kayıt penceresindeki açıklama alanı.
               `proj.*` ailesinin evi i18n_common.js'tir ama o dosya bu
               dalgada arayüz kulvarının sahasıdır ve orada değişiyor;
               anahtar, kabuk sözlüğüne yazıldı (D17 electron a1'in
               `chartCap.injectorFace` emsali). register() bütün parçaları
               tek tabloda birleştirir. */
            'proj.descLabel': 'Description (optional)'
        },
        tr: {
            'link.releaseNotes': 'Sürüm Notları',
            'link.settings': 'Ayarlar',
            'link.userGuide': 'Kullanma Kılavuzu',
            'guide.opened': 'Kullanma kılavuzu PDF\'i, HRMA\'nın çalıştığı bilgisayarın PDF görüntüleyicisinde açıldı.',
            'guide.notLaunched': 'Sunucu bir PDF görüntüleyici açmadı; kılavuzu buradan açın:',
            'guide.notPackaged': 'Kullanma kılavuzu PDF\'i bu kurulumla gelmiyor; çevrimiçi kopya:',
            'guide.openInBrowser': 'PDF\'i tarayıcıda aç',
            'guide.close': 'Kapat',

            'shell.close': 'Kapat',

            /* ÖH D18 / P12aB4-08 — bkz. EN bloğundaki not. */
            'stepimp.fieldThroat': 'Bo\u011faz \u00e7ap\u0131 (mm)',
            'stepimp.fieldExit': '\u00c7\u0131k\u0131\u015f \u00e7ap\u0131 (mm)',
            'stepimp.fieldChamberD': 'Oda \u00e7ap\u0131 (mm)',
            'stepimp.fieldChamberL': 'Oda boyu (mm)',
            'stepimp.fieldWall': 'Cidar kal\u0131nl\u0131\u011f\u0131 (mm)',

            'shell.releaseNotes.title': 'SÜRÜM NOTLARI',
            'shell.releaseNotes.loading': 'Sürüm notları yükleniyor…',
            'shell.releaseNotes.empty': 'Sürüm notu bulunamadı.',
            'shell.releaseNotes.error': 'Sürüm notları yüklenemedi.',

            'shell.settings.title': 'AYARLAR',
            'shell.settings.language': 'Dil',
            'shell.settings.languageDesc': 'Arayüz dili. Ana sayfadaki seçici ile eşzamanlı kalır.',
            'shell.settings.updates': 'Güncellemeler',
            'shell.settings.autoCheck': 'Açılışta güncelleme denetle',
            'shell.settings.autoCheckDesc': 'Kapalıyken HRMA açılışta güncelleme sunucusuna bağlanmaz.',
            'shell.settings.checkNow': 'Şimdi denetle',
            'shell.settings.checking': 'Denetleniyor…',
            'shell.settings.upToDate': 'Güncelsiniz: v{version}',
            'shell.settings.updateFound': 'Yeni sürüm bulundu: v{version} — güncelleme penceresi açılıyor.',
            'shell.settings.updateFoundNoWindow': 'Yeni sürüm bulundu: v{version} — güncelleme penceresi bu sayfada kullanılamıyor.',
            'shell.settings.checkFailed': 'Güncelleme sunucusuna ulaşılamadı.',
            'shell.settings.rateLimited': 'GitHub bu ağa istek sınırı uyguluyor — birkaç dakika sonra tekrar deneyin.',

            /* ÖH D27 / OH-D26-18 — bkz. EN bloğundaki gerekçe. */
            'update.sourceApi': 'Sürüm bilgisi GitHub Releases API\'sinden okundu.',
            'update.sourcePage': 'Releases API\'sine ulaşılamadı; sürüm bilgisi bunun yerine sürümler sayfasından okundu (yedek yol).',
            'update.sourceNone': 'Sunucu bu sürüm bilgisi için bir kaynak bildirmedi.',
            'update.sourceMissing': 'Sunucu bu sürüm bilgisinin nereden geldiğini bildirmedi.',
            'update.sourceOther': 'Sunucunun bildirdiği sürüm bilgisi kaynağı: {code} (bu sürümün tanımadığı bir kaynak).',
            'update.sourceRaw': 'Sunucunun bildirdiği sürüm bilgisi kaynağı: {code}.',

            'shell.settings.skippedVersion': 'Atlanan sürüm: v{version}',
            'shell.settings.noSkipped': 'Atlanan sürüm yok.',
            'shell.settings.skipReset': 'Atlanan sürümü sıfırla',
            'shell.settings.skipCleared': 'Atlanan sürüm sıfırlandı — bir sonraki denetimde yeniden sorulur.',
            'shell.settings.app': 'Uygulama',
            'shell.settings.version': 'Sürüm',
            'shell.settings.versionUnknown': 'okunamadı',
            'shell.settings.versionBasis': 'denenen kaynaklar: {sources}',
            'proj.btnDiscard': 'Değişiklikleri at',
            'proj.nameReserved': 'Bu ad Windows\'ta bir aygıt için ayrılmıştır (CON, PRN, AUX, NUL, COM1-9, LPT1-9) ve dosya adı olarak kullanılamaz.',
            'shell.settings.githubLink': 'GitHub üzerinde HRMA',

            /* ÖH D17 / P12aB5-01 — "Hata bildir" bölümü.
             * settings_panel.js + bug_report.js 47 `shell.bug.*` anahtarı
             * çağırıyordu; HİÇBİRİ hiçbir sözlükte tanımlı değildi, yani
             * Türkçe arayüzde bölümün TAMAMI İngilizce kalıyordu — aynı
             * pencerenin "Güncellemeler" bölümü Türkçeleşirken. Ağırlığı
             * yalnız çevrilmemiş metin değil: tanılama onay kutusunun
             * GİZLİLİK BEYANI da (`shell.bug.diagnosticsDesc`) İngilizce
             * kalıyordu, yani rızanın dayandığı cümle okunamıyordu.
             * Ayrıca `warn.bugreport.*` uyarı pilleri (settings_panel.js
             * WARN_FALLBACK) da tanımsızdı. */
            'stepimp.refuseSolidChamberLen': 'Uygulanmadı: bu sayfada oda boyu alanı yok. Tek boy girdisi tane boyudur (tek propelan tanesi) ve o ayrı bir büyüklüktür \u2014 kendiniz girin.',
            'proj.loadedWithWarnings': '"{name}" projesi {n} uyarıyla yüklendi \u2014 yukarıya bakın.',
            'update.statusUnreachable': 'Güncelleme durumu okunamadı — indirme tamamlanmamış olabilir. Bunun yerine aşağıdaki tarayıcı bağlantısını kullanın.',
            'shell.bug.section': 'Hata bildir',
            'shell.bug.intro': 'Burayı doldurun; HRMA yeni bir sekmede GitHub üzerinde önceden doldurulmuş bir kayıt açar. Hiçbir şey kendiliğinden gönderilmez — metni siz gözden geçirir, kendi GitHub hesabınızla siz gönderirsiniz.',
            'shell.bug.titleLabel': 'Başlık',
            'shell.bug.titlePlaceholder': 'Sorunun kısa özeti',
            'shell.bug.whatLabel': 'Ne oldu?',
            'shell.bug.whatPlaceholder': 'Neyin ters gittiğini anlatın.',
            'shell.bug.expectedLabel': 'Ne bekliyordunuz?',
            'shell.bug.expectedPlaceholder': 'Bunun yerine ne olmalıydı?',
            'shell.bug.stepsLabel': 'Yeniden üretme adımları',
            'shell.bug.stepsPlaceholder': '1. Hibrit sayfasını aç\n2. … gir\n3. Hesapla\'ya bas',
            'shell.bug.diagnostics': 'Tanılama bilgisini ekle',
            'shell.bug.diagnosticsDesc': 'Bu sayfadaki sayısal girdileri ve sayfa yüklendikten sonra yakalanan konsol hatalarını ekler. Dosya yolları, kullanıcı adları, e-posta adresleri ve coğrafi koordinatlar (fırlatma sahası enlem/boylamı) çıkarılır. Siz açmadıkça kapalıdır.',
            'shell.bug.preview': 'Önizle',
            'shell.bug.previewTitle': 'Gönderilecek metin tam olarak budur',
            'shell.bug.previewHint': 'Hâlâ düzenleyebilirsiniz. HRMA GitHub\'ı bu metin önceden doldurulmuş hâlde açar; \"Submit new issue\" düğmesine orada siz basarsınız.',
            'shell.bug.urlLabel': 'Kayıt bağlantısı',
            'shell.bug.help.title': 'Kayıt başlığı, en çok 256 karakter (GitHub sınırı). Buradan hiçbir şey gönderilmez: zorunlu önizlemeden sonra HRMA ön-doldurulmuş bir GitHub kayıt sayfası açar, siz kendi hesabınızla gönderirsiniz.',
            'shell.bug.help.what': 'Serbest metin: ne ters gitti. Kayıt gövdesinin bir bölümü olur; önizlemede görür ve düzenleyebilirsiniz.',
            'shell.bug.help.expected': 'Serbest metin: bunun yerine ne olmalıydı. Kayıt gövdesinin bir bölümü olur; önizlemede gösterilir.',
            'shell.bug.help.steps': 'Serbest metin: sorunu yeniden üreten adımlar. Kayıt gövdesinin bir bölümü olur; önizlemede gösterilir.',
            'shell.bug.help.diagnostics': 'Varsayılan kapalı. İşaretlenirse gövdeye yalnız sayısal girdiler ve temizlenmiş konsol satırları eklenir; ev dizini/kullanıcı adı, e-posta, dosya yolları, belirteç görünümlü diziler ve coğrafi konum silinir. HRMA\'dan bir şey çıkmadan önce hepsi önizlemede gösterilir.',
            'shell.bug.help.previewTitle': 'GitHub kayıt sayfasına aynen konacak başlık; burada hâlâ düzenleyebilirsiniz.',
            'shell.bug.help.body': 'GitHub kayıt sayfasına aynen konacak gövde; hâlâ düzenleyebilirsiniz. Bağlantı için fazla uzunsa kısaltma burada, önizlemede yapılır; sonradan sessizce yapılmaz.',
            'shell.bug.help.url': 'Ön-doldurulmuş GitHub kayıt bağlantısının salt okunur kopyası; yeni sekme engellendiğinde görünür, tarayıcınıza kopyalayın.',
            'shell.bug.charCount': '{chars} karakter — kayıt bağlantısı {url} / {limit}',
            'shell.bug.openGithub': 'GitHub\'da aç',
            'shell.bug.back': 'Geri',
            'shell.bug.needTitle': 'Lütfen bir başlık yazın.',
            'shell.bug.needWhat': 'Lütfen ne olduğunu anlatın.',
            'shell.bug.previewRequired': 'Kaydı açmadan önce önizleyin.',
            'shell.bug.reviewAgain': 'Metin, bağlantı sınırına sığması için kısaltıldı — gözden geçirip düğmeye yeniden basın.',
            'shell.bug.opened': 'GitHub yeni sekmede açıldı — metni orada denetleyip \"Submit new issue\" düğmesine basın.',
            'shell.bug.openFailed': 'Tarayıcı yeni sekme açmadı. Aşağıdaki bağlantıyı kopyalayıp kendiniz açın.',
            'shell.bug.body.what': 'Ne oldu',
            'shell.bug.body.expected': 'Ne bekleniyordu',
            'shell.bug.body.steps': 'Yeniden üretme adımları',
            'shell.bug.body.env': 'Ortam',
            'shell.bug.body.os': 'İşletim sistemi',
            'shell.bug.body.browser': 'Tarayıcı',
            'shell.bug.body.page': 'Sayfa',
            'shell.bug.body.uiLang': 'Arayüz dili',
            'shell.bug.body.engine': 'Motor tipi',
            'shell.bug.body.diagnostics': 'Tanılama',
            'shell.bug.body.diagnosticsOff': 'Tanılama bilgisi eklenmedi (bildiren kutuyu işaretlemedi).',
            'shell.bug.body.inputs': 'Sayısal girdiler',
            'shell.bug.body.inputsNone': 'Bu sayfada sayısal girdi bulunamadı.',
            'shell.bug.body.inputsTruncated': 'Listelenen: {total} sayısal alanın ilk {shown} tanesi ({dropped} alan listelenmedi). Kayıt bağlantısı URL sınırının içinde kalsın diye liste {limit} girdiyle sınırlıdır.',
            'shell.bug.body.inputsGeoWithheld': 'Geri tutulan: {count} coğrafi koordinat alanı ({ids}). Fırlatma sahasının konumu herkese açık kayda gönderilmez — önemliyse konumu sözle anlatın.',
            'shell.bug.body.field': 'Alan',
            'shell.bug.body.value': 'Değer',
            'shell.bug.body.console': 'Konsol hataları',
            'shell.bug.body.consoleNone': 'Bu sayfa yüklendikten sonra konsol hatası yakalanmadı.',
            'shell.bug.body.redactNote': 'Dosya yolları, kullanıcı adları ve e-posta adresleri kayıttan çıkarıldı.',
            'shell.bug.body.truncated': 'Kayıt bağlantısı {limit} karakterlik URL sınırının altında kalsın diye tanılama kaydı {chars} karakter kısaltıldı.',
            'shell.bug.body.blank': '(doldurulmadı)',
            'shell.bug.body.unknown': 'bilinmiyor',
            'shell.bug.body.versionMissing': 'bu sayfa sürümü yayımlamıyor',

            /* ÖH D17 / P12aB3-02 + P12aB3-09 — grafik altyazıları.
             * injectorFace: eski 'chartCap.injector_plot' delik YERLEŞİMİNİN
             * basınç düşümünü belirlediğini söylüyordu; ölçüm 26 sayısal
             * alanın 0'ının değiştiğini gösteriyor. Eski anahtarın TR
             * karşılığı i18n_common.js'te ve i18n 'ilk kazanır' kuralıyla
             * ezilemediği için anahtar yeniden adlandırıldı.
             * Kalan 7 anahtar: sabit id ile çizilip açıklamasız kalan
             * grafikler (iki Monte Carlo histogramı, iki CAD görünümü). */
            'chartCap.injectorFace': 'Seçilen enjektör tipinin yüz ve akış şeması: delik yerleşimi, delik sayısı ve delik çapı. Yüz deseni yalnızca çizimdir — değiştirilmesi hesaplanan hiçbir sayıyı oynatmaz; basınç düşümü ile atomizasyon delik çapından, delik sayısından ve kütle debisinden gelir.',
            'chartCap.solid_motor_kesit': 'Katı motorun ölçekli kesiti: gövde, propelan tanesi, çekirdek kanalı ve nozul, ana ölçüleriyle. CAD dışa aktarımından ya da imalattan önce oranları gözle denetlemek için kullanın.',
            'chartCap.liquid_motor_kesit': 'Sıvı motorun ölçekli kesiti: yanma odası, enjektör yüzü, boğaz ve nozul, ana ölçüleriyle. CAD dışa aktarımından ya da imalattan önce oranları gözle denetlemek için kullanın.',
            'chartCap.mc_hist_thrust': 'Monte Carlo itki dağılımı: örneklenen koşumlar üzerinde kutu başına bir çubuk, anma tasarım değeri işaretli. Genişlik, itkinin girdiğiniz girdi toleranslarına ne kadar duyarlı olduğunu gösterir — imalat güvencesi değildir.',
            'chartCap.mc_hist_isp': 'Örneklenen koşumlar üzerinde Monte Carlo deniz seviyesi özgül itki dağılımı, anma tasarım değeri işaretli. Yayılımı ölçülmüş bir saçılma olarak değil, girdi toleranslarının etkisi olarak okuyun.',
            'chartCap.altitude_plot': 'Rakıma göre teslim edilen özgül itki: ortam basıncı düştükçe Isp vakum değerine doğru yükselir. Eğri standart atmosferi kullanır, yerel saha koşullarını değil.',
            'chartCap.altitude_preview': 'Girdiğiniz tarama boyunca (alt_start–alt_end arası, alt_points örnek) ortam basıncının irtifaya göre değişimi; gömülü ABD Standart Atmosfer 1976 modelinden hesaplanır. Ne bir uçuş profilidir ne de bir çözücü sonucu — buradaki hiçbir sayı motor çözümünden gelmez.',
            'chartCap.cad_visualization': 'Çözülmüş geometriden üretilen CAD görünümü. Tasarım tablosunda listelenen ölçülerin çizimidir — toleranslar, kavisler ve birleşimler modellenmez; imalat resmi değildir.',
            'chartCap.cad_3d_view': 'Çözülmüş motor geometrisinin etkileşimli 3B CAD görünümü. Döndürmek için sürükleyin, yakınlaşmak için kaydırın. Toleranslar, kavisler ve birleşimler modellenmez — imalat resmi değildir.',
            'warn.bugreport.body_truncated': 'Tanılama kaydı, kayıt bağlantısı uzunluk sınırına sığsın diye kısaltıldı ({chars} karakter çıkarıldı).',
            'warn.bugreport.inputs_truncated': 'Sayısal girdi listesi {limit} girdiyle sınırlandı; {dropped} alan listelenmedi.',
            'warn.bugreport.geo_withheld': 'Coğrafi koordinat alanları kayıttan geri tutuldu ({count} alan).',
            'warn.bugreport.title_truncated': 'Başlık, GitHub\'ın {limit} karakterlik sınırına kısaltıldı.',
            'warn.bugreport.preview_required': 'Kayıt yalnızca önizlendikten sonra açılabilir.',
            'proj.descLabel': 'Açıklama (isteğe bağlı)'
        }
    };
    if (global.I18N && global.I18N.register) {
        global.I18N.register(DICT, 'i18n_shell.js');
    } else {
        (global.__I18N_PENDING = global.__I18N_PENDING || []).push(DICT);
    }
})(typeof window !== 'undefined' ? window : this);
