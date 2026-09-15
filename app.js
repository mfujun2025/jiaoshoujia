/* 脚手架.cn — 前端脚本：站内搜索 + 文章目录 */
(function () {
  'use strict';

  /* ------------------------------------------------------------------
     一、站内搜索（/search/ 页面）
     ------------------------------------------------------------------ */
  var form = document.getElementById('search-form');
  if (form) {
    var input = document.getElementById('q');
    var statusEl = document.getElementById('search-status');
    var resultsEl = document.getElementById('search-results');
    var emptyEl = document.getElementById('search-empty');
    var hintsEl = document.getElementById('hints');
    var INDEX = [];
    var loaded = false;

    function esc(s) {
      return String(s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }

    function tokenize(q) {
      return String(q || '').toLowerCase().split(/[\s,，、;；]+/).filter(function (t) {
        return t.length > 0;
      });
    }

    // 打分：标题命中权重最高，其次关键词、摘要、正文
    function score(item, tokens) {
      var t = (item.t || '').toLowerCase();
      var k = (item.k || '').toLowerCase();
      var d = (item.de || '').toLowerCase();
      var c = (item.cn || '').toLowerCase();
      var b = (item.b || '').toLowerCase();
      var total = 0;
      for (var i = 0; i < tokens.length; i++) {
        var w = tokens[i];
        var s = 0;
        if (t.indexOf(w) > -1) s += 100;
        if (k.indexOf(w) > -1) s += 45;
        if (c.indexOf(w) > -1) s += 25;
        if (d.indexOf(w) > -1) s += 20;
        if (b.indexOf(w) > -1) s += 8;
        if (s === 0) return 0;   // 所有词都须命中（AND 逻辑）
        total += s;
      }
      return total;
    }

    function highlight(text, tokens) {
      var out = esc(text);
      tokens.forEach(function (w) {
        if (!w) return;
        var re = new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        out = out.replace(re, '<mark>$1</mark>');
      });
      return out;
    }

    function snippet(item, tokens) {
      var body = item.b || '';
      var low = body.toLowerCase();
      var pos = -1;
      for (var i = 0; i < tokens.length; i++) {
        var p = low.indexOf(tokens[i]);
        if (p > -1 && (pos === -1 || p < pos)) pos = p;
      }
      if (pos === -1) return item.de || body.slice(0, 90);
      var start = Math.max(0, pos - 40);
      var end = Math.min(body.length, pos + 110);
      return (start > 0 ? '…' : '') + body.slice(start, end) + (end < body.length ? '…' : '');
    }

    function render(q) {
      var tokens = tokenize(q);
      resultsEl.innerHTML = '';
      emptyEl.hidden = true;

      if (!tokens.length) {
        statusEl.textContent = '共收录 ' + INDEX.length + ' 篇资讯，输入关键词开始检索。';
        return;
      }

      var hits = INDEX
        .map(function (it) { return { it: it, s: score(it, tokens) }; })
        .filter(function (h) { return h.s > 0; })
        .sort(function (a, b) { return b.s - a.s || (a.it.d < b.it.d ? 1 : -1); });

      statusEl.textContent = '「' + q + '」找到 ' + hits.length + ' 篇相关资讯。';

      if (!hits.length) {
        emptyEl.hidden = false;
        return;
      }

      var html = hits.map(function (h) {
        var it = h.it;
        return '' +
          '<a class="card" href="/news/' + it.s + '/">' +
            '<div class="card-top">' +
              '<span class="card-tag">' + esc(it.cn) + '</span>' +
              '<span class="card-date">' + esc(it.d) + '</span>' +
            '</div>' +
            '<h3>' + highlight(it.t, tokens) + '</h3>' +
            '<p>' + highlight(snippet(it, tokens), tokens) + '</p>' +
            '<div class="card-foot"><span>关键词：' + esc(it.k || '') + '</span>' +
            '<span class="card-more">阅读全文 →</span></div>' +
          '</a>';
      }).join('');

      resultsEl.innerHTML = html;
    }

    function runFromUrl() {
      var q = new URLSearchParams(location.search).get('q') || '';
      input.value = q;
      if (loaded) render(q);
    }

    fetch('/search-index.json', { cache: 'no-cache' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        INDEX = data || [];
        loaded = true;
        runFromUrl();
      })
      .catch(function () {
        statusEl.textContent = '索引加载失败。请刷新页面重试。';
      });

    var timer = null;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var v = input.value;
      timer = setTimeout(function () {
        var url = v ? '/search/?q=' + encodeURIComponent(v) : '/search/';
        history.replaceState(null, '', url);
        render(v);
      }, 180);
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      render(input.value.trim());
    });

    if (hintsEl) {
      hintsEl.addEventListener('click', function (e) {
        var b = e.target.closest('[data-kw]');
        if (!b) return;
        input.value = b.getAttribute('data-kw');
        history.replaceState(null, '', '/search/?q=' + encodeURIComponent(input.value));
        render(input.value);
        input.focus();
      });
    }

    window.__SCAFFOLD__ = { search: render, index: function () { return INDEX; } };
  }

  /* ------------------------------------------------------------------
     二、文章页：自动生成目录
     ------------------------------------------------------------------ */
  var body = document.getElementById('article-body');
  var toc = document.getElementById('toc');
  if (body && toc) {
    var hs = body.querySelectorAll('h2');
    if (hs.length >= 3) {
      var list = document.getElementById('toc-list');
      var items = [];
      Array.prototype.forEach.call(hs, function (h, i) {
        var id = 'sec-' + (i + 1);
        h.id = id;
        var li = document.createElement('li');
        var a = document.createElement('a');
        a.href = '#' + id;
        a.textContent = h.textContent;
        li.appendChild(a);
        items.push(li);
      });
      items.forEach(function (li) { list.appendChild(li); });
      toc.hidden = false;
    }
  }

  /* ------------------------------------------------------------------
     三、导航高亮当前栏目
     ------------------------------------------------------------------ */
  var path = location.pathname;
  Array.prototype.forEach.call(document.querySelectorAll('.nav a'), function (a) {
    var href = a.getAttribute('href');
    if (href === '/' ? path === '/' : path.indexOf(href) === 0) a.classList.add('active');
  });
})();
