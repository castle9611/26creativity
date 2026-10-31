(function() {
  var root = document.getElementById('homeSlideshow');
  if (!root) return;
  var slides = root.querySelectorAll('.home-slide');
  if (!slides.length) return;
  var counter = root.querySelector('.slide-counter');
  var pause = root.querySelector('.slide-pause');
  var index = 0;
  var stopped = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hovered = false;
  var focused = false;
  var viewer = document.getElementById('slideViewer');
  var viewing = false;
  var viewedIndex = 0;
  var previousFocus;
  var previousOverflow;
  var timer = null;
  function viewImage(next) {
    viewedIndex = (next + slides.length) % slides.length;
    var image = viewer.querySelector('.slide-viewer-image');
    image.src = slides[viewedIndex].getAttribute('data-image');
    image.alt = slides[viewedIndex].getAttribute('aria-label');
    viewer.querySelector('.slide-viewer-caption').textContent = (viewedIndex + 1) + ' / ' + slides.length + ' · ' + image.alt;
  }
  function openViewer(next) {
    previousFocus = document.activeElement;
    previousOverflow = document.body.style.overflow;
    viewing = true;
    viewImage(next);
    viewer.style.display = 'block';
    document.body.style.overflow = 'hidden';
    viewer.querySelector('.slide-viewer-close').focus();
  }
  function closeViewer() {
    viewing = false;
    viewer.style.display = 'none';
    viewer.querySelector('.slide-viewer-image').removeAttribute('src');
    document.body.style.overflow = previousOverflow;
    if (previousFocus && previousFocus.focus) previousFocus.focus();
  }
  if (viewer) {
    viewer.querySelector('.slide-viewer-close').onclick = closeViewer;
    var previous = viewer.querySelector('.slide-viewer-prev');
    var next = viewer.querySelector('.slide-viewer-next');
    if (previous) previous.onclick = function() { viewImage(viewedIndex - 1); };
    if (next) next.onclick = function() { viewImage(viewedIndex + 1); };
    viewer.onclick = function(event) { if (event.target === viewer) closeViewer(); };
    viewer.onkeydown = function(event) {
      if (event.keyCode === 27) closeViewer();
      else if (event.keyCode === 37) viewImage(viewedIndex - 1);
      else if (event.keyCode === 39) viewImage(viewedIndex + 1);
      else if (event.keyCode === 9) {
        var buttons = viewer.querySelectorAll('button');
        var target = event.shiftKey ? buttons[buttons.length - 1] : buttons[0];
        if ((!event.shiftKey && document.activeElement === buttons[buttons.length - 1]) || (event.shiftKey && document.activeElement === buttons[0])) {
          target.focus(); event.preventDefault();
        }
      }
    };
    for (var slideIndex = 0; slideIndex < slides.length; slideIndex++) {
      slides[slideIndex].setAttribute('data-index', slideIndex);
      slides[slideIndex].onclick = function() { openViewer(parseInt(this.getAttribute('data-index'), 10)); };
      slides[slideIndex].onkeydown = function(event) {
        if (event.keyCode === 13 || event.keyCode === 32) { this.onclick(); event.preventDefault(); }
      };
    }
  }
  function show(next) {
    index = (next + slides.length) % slides.length;
    var positions = {};
    positions[index] = 'front';
    if (slides.length > 1) positions[(index + slides.length - 1) % slides.length] = 'left';
    if (slides.length > 2) positions[(index + 1) % slides.length] = 'right';
    if (slides.length > 3) positions[(index + slides.length - 2) % slides.length] = 'far-left';
    if (slides.length > 4) positions[(index + 2) % slides.length] = 'far-right';
    for (var i = 0; i < slides.length; i++) {
      var position = positions[i];
      slides[i].className = 'home-slide' + (position ? ' slide-' + position : '');
      slides[i].setAttribute('aria-hidden', position ? 'false' : 'true');
      slides[i].setAttribute('tabindex', position ? '0' : '-1');
      // Keep only the visible images attached to avoid decoding an entire library.
      slides[i].style.backgroundImage = position ? 'url("' + slides[i].getAttribute('data-image') + '")' : '';
    }
    if (counter) counter.innerHTML = (index + 1) + ' / ' + slides.length;
  }
  show(0);
  function stopTimer() {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
  }
  function startTimer() {
    stopTimer();
    if (slides.length < 2) return;
    timer = window.setInterval(function() {
      if (!stopped && !hovered && !focused && !viewing && !document.hidden) show(index + 1);
    }, 5000);
  }
  window.addEventListener('pagehide', stopTimer);
  window.addEventListener('pageshow', function() {
    if (viewing) closeViewer();
    hovered = false;
    focused = false;
    for (var i = 0; i < slides.length; i++) slides[i].style.backgroundImage = '';
    show(index);
    startTimer();
  });
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden && !viewing) show(index);
  });
  if (slides.length < 2) return;
  function updatePause() {
    pause.innerHTML = stopped ? '\u64ad\u653e' : '\u6682\u505c';
    pause.setAttribute('aria-label', stopped ? '\u5f00\u59cb\u81ea\u52a8\u5c55\u64ad' : '\u6682\u505c\u81ea\u52a8\u5c55\u64ad');
  }
  root.querySelector('.slide-prev').onclick = function() { show(index - 1); };
  root.querySelector('.slide-next').onclick = function() { show(index + 1); };
  pause.onclick = function() { stopped = !stopped; updatePause(); };
  root.onmouseenter = function() { hovered = true; };
  root.onmouseleave = function() { hovered = false; };
  root.onfocusin = function() { focused = true; };
  root.onfocusout = function(event) {
    event = event || window.event;
    focused = !!(event.relatedTarget && root.contains(event.relatedTarget));
  };
  root.onkeydown = function(event) {
    event = event || window.event;
    if (event.keyCode === 37 || event.keyCode === 39) {
      show(index + (event.keyCode === 37 ? -1 : 1));
      event.preventDefault();
    }
  };
  updatePause();
  startTimer();
})();
