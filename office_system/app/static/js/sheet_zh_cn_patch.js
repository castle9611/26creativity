/* x-spreadsheet Chinese localization helpers. */
(function () {
  function applyLocale() {
    if (window.x_spreadsheet && typeof window.x_spreadsheet.locale === 'function') {
      try { window.x_spreadsheet.locale('zh-cn'); } catch (e) {}
    }
  }

  var textMap = {
    'Sheet1': '工作表1',
    'Insert row': '插入行',
    'Insert column': '插入列',
    'Delete row': '删除行',
    'Delete column': '删除列',
    'Delete cell': '删除单元格',
    'Hide row': '隐藏行',
    'Hide column': '隐藏列',
    'Copy': '复制',
    'Cut': '剪切',
    'Paste': '粘贴',
    'Paste value': '粘贴数值',
    'Paste format': '粘贴格式',
    'Clear format': '清除格式',
    'Data validation': '数据验证',
    'Format': '格式',
    'Font': '字体',
    'Font size': '字号',
    'Text color': '文字颜色',
    'Fill color': '填充颜色',
    'Border': '边框',
    'Merge': '合并',
    'Align': '对齐',
    'Freeze': '冻结',
    'Filter': '筛选',
    'Sort A-Z': '升序',
    'Sort Z-A': '降序',
    'Cancel': '取消',
    'Save': '保存',
    'OK': '确定',
    'Print': '打印',
    'More': '更多'
  };

  function localizeTextNode(node) {
    var text = node.nodeValue;
    if (!text) return;
    var trimmed = text.replace(/^\s+|\s+$/g, '');
    if (textMap[trimmed]) {
      node.nodeValue = text.replace(trimmed, textMap[trimmed]);
    }
  }

  function localizeDom(root) {
    var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null, false);
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (var i = 0; i < nodes.length; i++) localizeTextNode(nodes[i]);
  }

  applyLocale();
  document.addEventListener('DOMContentLoaded', function () {
    applyLocale();
    localizeDom(document.body);
    if (window.MutationObserver) {
      var observer = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
          var m = mutations[i];
          for (var j = 0; j < m.addedNodes.length; j++) {
            var node = m.addedNodes[j];
            if (node.nodeType === 3) localizeTextNode(node);
            if (node.nodeType === 1) localizeDom(node);
          }
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }
  });
})();
