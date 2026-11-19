/* V307/KÜÇÜKLER (kalem 6) node düzeneği — güvenlik panelinin zorunlu alan
   kümesi şablonun <meta name="hrma-safety-required"> etiketinden okunur;
   node düzeneğinde şablon yoktur. Bu dosya panel dosyalarından ÖNCE yüklenir
   ve etiketin içeriğini ortam değişkeninden (HRMA_SAFETY_META = GERÇEK
   şablonun bastığı içerik; tests/support/guvenlik_meta.py Flask test
   istemcisiyle okur) sunar. Değişken yoksa etiket yoktur. */
(function () {
    var eski = document.querySelector;
    document.querySelector = function (sel) {
        if (sel === 'meta[name="hrma-safety-required"]') {
            var icerik = process.env.HRMA_SAFETY_META;
            if (!icerik) return null;
            return { getAttribute: function (k) { return k === 'content' ? icerik : null; } };
        }
        return eski.apply(document, arguments);
    };
})();
