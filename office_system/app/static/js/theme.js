(function() {
  function applyBlue() {
    document.documentElement.setAttribute('data-theme', 'blue');
    if (document.body) document.body.setAttribute('data-theme', 'blue');
  }

  try {
    localStorage.removeItem('prison_oa_theme');
  } catch (e) {}

  applyBlue();

  if (window.addEventListener) {
    window.addEventListener('DOMContentLoaded', applyBlue);
    window.addEventListener('DOMContentLoaded', ensureBackNavigation);
    window.addEventListener('message', function(event) {
      var data = event.data || {};
      if (data.type === 'oa-theme-change') applyBlue();
    });
  } else if (window.attachEvent) {
    window.attachEvent('onload', applyBlue);
    window.attachEvent('onload', ensureBackNavigation);
  }

  window.OATheme = {
    apply: applyBlue,
    current: function() { return 'blue'; }
  };

  function ensureBackNavigation() {
    if (!document.body) return;
    var path = window.location.pathname || '';
    if (path === '/' || path === '/login' || path === '/workbench') return;
    if (document.querySelector('.breadcrumb, .back-btn, .auto-back-nav, .detail-top')) return;

    var wrap = document.createElement('div');
    wrap.className = 'auto-back-nav';
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'back-btn';
    button.textContent = '返回上一页';
    button.addEventListener('click', function() {
      if (window.history.length > 1) {
        window.history.back();
      } else {
        window.location.href = '/workbench';
      }
    });
    wrap.appendChild(button);
    document.body.insertBefore(wrap, document.body.firstChild);
  }
})();
