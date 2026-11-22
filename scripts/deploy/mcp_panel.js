/* ARL 灯塔 MCP 栏目注入脚本 v8
 * 菜单项：结构与样式完全对齐原生（SVG sprite + menu-title + scoped 属性）。
 * 管理面板：深色渐变头部 + 白底浮起卡片 + Switch 开关，antd 视觉风格。
 * 全局配置：第二个注入栏目，像任务管理一样在内容区渲染独立页面（不改灯塔前端路由），
 *   卡片式编辑灯塔 config.yaml（FOFA/GitHub/钉钉/飞书/企微/邮件/代理/第三方测绘插件），
 *   保存后重启容器生效。（漏扫补充/漏扫配置/POC添加已下线，完整实现存于 git stash）
 */
(function () {
  if (window.__ARL_MCP_PANEL__) return;
  window.__ARL_MCP_PANEL__ = true;

  var API = '/mcp_admin'; // 经灯塔 nginx 同源代理到 MCP 管理面（固定端口）

  /* ---------------- 样式 ---------------- */
  var css = [
    /* 遮罩与弹窗 */
    '.mcp-mask{position:fixed;inset:0;background:rgba(0,21,41,.5);z-index:9999;display:flex;align-items:flex-start;justify-content:center;}',
    '.mcp-modal{background:#fff;border-radius:8px;box-shadow:0 6px 24px rgba(0,21,41,.24);width:700px;max-width:94vw;max-height:86vh;overflow:auto;margin-top:7vh;animation:mcpIn .2s ease-out;}',
    '@keyframes mcpIn{from{opacity:0;transform:translateY(-14px) scale(.98)}to{opacity:1;transform:none}}',
    '@keyframes mcpToastIn{from{opacity:0;transform:translate(-50%,-12px)}to{opacity:1;transform:translate(-50%,0)}}',

    /* 深色渐变头部（呼应灯塔侧栏） */
    '.mcp-head{padding:18px 24px;display:flex;justify-content:space-between;align-items:center;background:linear-gradient(120deg,#001529 0%,#003a8c 100%);position:sticky;top:0;z-index:1;}',
    '.mcp-title{font-size:16px;font-weight:600;color:#fff;letter-spacing:.5px;}',
    '.mcp-title small{font-weight:400;font-size:12px;color:rgba(255,255,255,.55);margin-left:10px;letter-spacing:0;}',
    '.mcp-x{cursor:pointer;font-size:14px;color:rgba(255,255,255,.65);padding:2px 7px;border-radius:4px;transition:all .2s;}',
    '.mcp-x:hover{color:#fff;background:rgba(255,255,255,.14);}',

    /* 卡片栅格 */
    '.mcp-body{padding:20px;background:#f7f8fa;display:grid;grid-template-columns:1fr 1fr;gap:14px 16px;}',
    '.mcp-card{background:#fff;border-radius:8px;padding:14px 16px;min-width:0;box-shadow:0 1px 4px rgba(0,21,41,.06);transition:box-shadow .25s,transform .25s;}',
    '.mcp-card:hover{box-shadow:0 4px 14px rgba(0,21,41,.12);transform:translateY(-1px);}',
    '.mcp-card.full{grid-column:1 / -1;}',
    '.mcp-card-title{font-size:14px;font-weight:600;color:#595959;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;gap:8px;}',
    '.mcp-tick{display:inline-block;width:3px;height:13px;border-radius:2px;background:#1890ff;margin-right:8px;vertical-align:-1px;}',
    '.mcp-card-title span:first-child{display:flex;align-items:center;}',

    /* 代码条 */
    '.mcp-code{background:#f7f8fa;border:1px solid #eef0f2;border-radius:6px;padding:6px 10px;font-family:Consolas,Menlo,monospace;font-size:13px;color:rgba(0,0,0,.72);word-break:break-all;line-height:1.6;}',

    /* 按钮 */
    '.mcp-btn{display:inline-block;padding:4px 15px;border-radius:4px;border:1px solid #d9d9d9;background:#fff;color:rgba(0,0,0,.65);font-size:14px;line-height:22px;cursor:pointer;transition:all .2s;white-space:nowrap;}',
    '.mcp-btn:hover{border-color:#1890ff;color:#1890ff;}',
    '.mcp-btn:active{transform:translateY(1px) scale(.97);}',
    '.mcp-btn.primary{background:#1890ff;border-color:#1890ff;color:#fff;box-shadow:0 2px 5px rgba(24,144,255,.25);}',
    '.mcp-btn.primary:hover{background:#40a9ff;}',
    '.mcp-btn.danger:hover{border-color:#ff4d4f;color:#ff4d4f;}',
    '.mcp-btn.danger{box-shadow:none;}',
    '.mcp-btn:disabled{opacity:.5;cursor:not-allowed;}',

    /* Switch 开关（含按压/悬停反馈 + 果冻拨动动画） */
    '.mcp-sw{width:44px;height:22px;border-radius:11px;background:#c4c4c4;position:relative;cursor:pointer;transition:background .45s cubic-bezier(.4,0,.2,1),transform .15s ease,box-shadow .25s;display:inline-block;vertical-align:middle;flex:none;}',
    '.mcp-sw:active{transform:scale(.93);}',
    '.mcp-sw-row:hover .mcp-sw{box-shadow:0 0 0 3px rgba(24,144,255,.12);}',
    '.mcp-sw.loading{opacity:.45;pointer-events:none;}',
    '.mcp-sw:after{content:"";position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);}',
    '.mcp-sw.on{background:#1890ff;animation:mcpPulseOn .6s ease-out;}',
    '.mcp-sw.on:after{left:24px;transform-origin:left center;animation:mcpBallOn .55s cubic-bezier(.25,.7,.3,1);}',
    '.mcp-sw:not(.on):after{transform-origin:right center;animation:mcpBallOff .55s cubic-bezier(.25,.7,.3,1);}',
    '@keyframes mcpBallOn{0%{left:2px;transform:scaleX(1)}38%{left:21px;transform:scaleX(1.35)}62%{left:23px;transform:scaleX(.9)}82%{left:24.4px;transform:scaleX(1.05)}100%{left:24px;transform:scaleX(1)}}',
    '@keyframes mcpBallOff{0%{left:24px;transform:scaleX(1)}38%{left:5px;transform:scaleX(1.35)}62%{left:3px;transform:scaleX(.9)}82%{left:1.6px;transform:scaleX(1.05)}100%{left:2px;transform:scaleX(1)}}',
    '@keyframes mcpPulseOn{0%{box-shadow:0 0 0 0 rgba(24,144,255,.35)}100%{box-shadow:0 0 0 9px rgba(24,144,255,0)}}',
    '.mcp-sw-row{display:flex;align-items:center;gap:12px;cursor:pointer;user-select:none;}',
    '.mcp-status{font-size:14px;color:rgba(0,0,0,.75);display:inline-flex;align-items:center;}',
    '.mcp-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;}',
    '.mcp-status .mcp-dot{background:#ff4d4f;box-shadow:0 0 0 2px rgba(255,77,79,.15);}',
    '.mcp-status.on .mcp-dot{background:#52c41a;box-shadow:0 0 0 2px rgba(82,196,26,.15);}',
    '.mcp-status-sub{font-size:12px;color:#bfbfbf;margin-top:9px;line-height:1.6;}',

    /* 输入与自绘下拉 */
    '.mcp-input{border:1px solid #d9d9d9;border-radius:4px;padding:4px 11px;font-size:14px;flex:1;min-width:0;color:rgba(0,0,0,.75);transition:border-color .2s,box-shadow .2s;}',
    '.mcp-input:focus{outline:none;border-color:#1890ff;box-shadow:0 0 0 2px rgba(24,144,255,.12);}',
    '.mcp-dd{position:relative;}',
    '.mcp-dd-value{background:#fff;border:1px solid #d9d9d9;border-radius:4px;padding:4px 11px;font-size:14px;color:rgba(0,0,0,.75);cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:border-color .2s,box-shadow .2s,transform .15s;font-family:Consolas,Menlo,monospace;}',
    '.mcp-dd-value:hover{border-color:#1890ff;}',
    '.mcp-dd-value:active{transform:scale(.99);}',
    '.mcp-dd.open .mcp-dd-value{border-color:#1890ff;box-shadow:0 0 0 2px rgba(24,144,255,.12);}',
    '.mcp-dd-arrow{font-size:10px;color:#999;margin-left:8px;transition:transform .2s;}',
    '.mcp-dd.open .mcp-dd-arrow{transform:rotate(180deg);}',
    '.mcp-dd-list{position:absolute;left:0;right:0;top:calc(100% + 4px);background:#fff;border:1px solid #eef0f2;border-radius:6px;box-shadow:0 4px 14px rgba(0,21,41,.14);z-index:10001;max-height:160px;overflow:auto;margin:0;padding:4px 0;list-style:none;}',
    '.mcp-dd-list li{padding:6px 11px;font-size:14px;color:rgba(0,0,0,.75);cursor:pointer;list-style:none;font-family:Consolas,Menlo,monospace;transition:background .15s;}',
    '.mcp-dd-list li:hover{background:#f5f5f5;}',
    '.mcp-dd-list li:active{background:#e6f7ff;}',
    '.mcp-dd-list li.active{color:#1890ff;background:#e6f7ff;}',

    /* 提示与浮层 */
    '.mcp-tip{font-size:12px;color:#bfbfbf;margin-top:8px;line-height:1.65;}',
    '.mcp-toast{position:fixed;top:24px;left:50%;transform:translate(-50%,0);background:#fff;border-radius:6px;box-shadow:0 4px 14px rgba(0,21,41,.18);padding:9px 18px;font-size:14px;color:rgba(0,0,0,.75);z-index:10002;animation:mcpToastIn .2s ease-out;display:flex;align-items:center;gap:8px;}',
    '.mcp-toast:before{content:"";width:6px;height:6px;border-radius:50%;background:#52c41a;flex:none;}',

    /* 全局配置页（内容区页面切换） */
    '.mcp-page{background:#f0f2f5;min-height:calc(100vh - 64px);padding:22px;animation:mcpPageIn .45s cubic-bezier(.25,.7,.3,1);}',
    '@keyframes mcpPageIn{from{opacity:0;transform:translateX(28px)}to{opacity:1;transform:none}}',
    '.mcp-page-head{background:#fff;border-radius:8px;padding:18px 22px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,21,41,.06);display:flex;justify-content:space-between;align-items:center;}',
    '.mcp-page-title{font-size:18px;font-weight:600;color:rgba(0,0,0,.8);}',
    '.mcp-page-sub{font-size:13px;color:#8c8c8c;margin-top:0;}',
    '.mcp-note{font-size:13px;color:rgba(0,0,0,.55);margin:0 0 16px 4px;line-height:1.7;}',
    '.mcp-page-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px 18px;align-items:start;}',
    '.mcp-page .mcp-card{padding:16px 18px;box-shadow:0 1px 6px rgba(0,21,41,.08);}',
    '.mcp-page .mcp-card-title{font-size:15px;margin-bottom:14px;}',
    '.mcp-field-label{flex:none;width:160px;font-size:14px;color:rgba(0,0,0,.75);}',
    '.mcp-field-row{display:flex;align-items:center;gap:10px;margin-top:10px;}',
    '.mcp-page .mcp-input{font-size:15px;padding:6px 11px;}',
    '.mcp-page .mcp-tip{font-size:13px;}',
    '.mcp-page .mcp-btn{font-size:14px;padding:5px 16px;}',
    '.mcp-plugin-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:4px;}',
    '.mcp-plugin{border:1px solid #eef0f2;border-radius:6px;padding:12px 14px;background:#fafafa;}',
    '.mcp-plugin-name{font-size:14px;font-weight:600;color:rgba(0,0,0,.7);margin-bottom:4px;}'
  ].join('');
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  /* ---------------- 工具 ---------------- */
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  function toast(msg) {
    var t = el('div', { 'class': 'mcp-toast' }, msg);
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2000);
  }
  function copy(text, what) {
    function ok() { toast((what || '内容') + ' 已复制'); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(ok, function () { fallback(); });
    } else fallback();
    function fallback() {
      var ta = el('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); ok(); } catch (e) { toast('复制失败，请手动选择'); }
      ta.remove();
    }
  }
  function getCfg(cb) {
    fetch(API + '/config').then(function (r) { return r.json(); }).then(cb)
      .catch(function () { cb(null); });
  }
  function post(body, cb) {
    fetch(API + '/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(cb)
      .catch(function () { cb(null); });
  }
  function card(parent, title, full) {
    var c = el('div', { 'class': 'mcp-card' + (full ? ' full' : '') });
    var t = el('div', { 'class': 'mcp-card-title' });
    var tl = el('span');
    tl.appendChild(el('i', { 'class': 'mcp-tick' }));
    tl.appendChild(document.createTextNode(title));
    t.appendChild(tl);
    c.appendChild(t);
    parent.appendChild(c);
    return { card: c, titleRow: t };
  }
  function btn(text, cls, onClick) {
    var b = el('button', { 'class': 'mcp-btn' + (cls ? ' ' + cls : '') }, text);
    b.onclick = onClick;
    return b;
  }

  /* ---------------- 面板（双列卡片） ---------------- */
  function openPanel() {
    if (document.querySelector('.mcp-mask')) return;
    var mask = el('div', { 'class': 'mcp-mask' });
    var modal = el('div', { 'class': 'mcp-modal' });

    var head = el('div', { 'class': 'mcp-head' });
    var title = el('div', { 'class': 'mcp-title' }, 'MCP 服务器');
    title.appendChild(el('small', null, 'AI 通过 MCP 协议访问灯塔数据'));
    var x = el('span', { 'class': 'mcp-x' }, '✕');
    x.onclick = close;
    head.appendChild(title); head.appendChild(x);

    var body = el('div', { 'class': 'mcp-body' });
    modal.appendChild(head); modal.appendChild(body); mask.appendChild(modal);
    document.body.appendChild(mask);
    mask.onclick = function (e) { if (e.target === mask) close(); };
    document.addEventListener('keydown', escClose);
    /* 自绘下拉的全局点击关闭（事件委托，render 重建 DOM 也有效） */
    function docCloseDd(e) {
      var lists = document.querySelectorAll('.mcp-dd-list');
      for (var i = 0; i < lists.length; i++) {
        if (!lists[i].parentElement.contains(e.target)) lists[i].style.display = 'none';
      }
    }
    document.addEventListener('click', docCloseDd);
    function escClose(e) { if (e.key === 'Escape') close(); }
    function close() {
      mask.remove();
      document.removeEventListener('keydown', escClose);
      document.removeEventListener('click', docCloseDd);
    }

    var cfg = null;

    function mcpUrl() {
      return 'http://' + (cfg.ip || location.hostname) + ':' + cfg.port + '/mcp';
    }
    function clientConf() {
      return JSON.stringify({
        mcpServers: {
          arl: { url: mcpUrl(), headers: { 'X-API-Key': cfg.api_key } }
        }
      }, null, 2);
    }

    function render() {
      body.textContent = '';
      if (!cfg) {
        var err = card(body, 'MCP 管理服务', true);
        err.card.appendChild(el('div', { 'class': 'mcp-tip' },
          '加载失败：管理服务无响应，请检查服务器上 mcp-ai 服务状态'));
        return;
      }

      /* 卡 1：服务状态（Switch 开关，整行可点，点击即给 loading 反馈） */
      var c1 = card(body, '服务状态');
      var row = el('div', { 'class': 'mcp-sw-row' });
      var sw = el('span', { 'class': 'mcp-sw' + (cfg.enabled ? ' on' : '') });
      var st = el('span', { 'class': 'mcp-status' + (cfg.enabled ? ' on' : '') });
      st.innerHTML = '<span class="mcp-dot"></span>' + (cfg.enabled ? '已开启' : '已关闭');
      row.appendChild(sw);
      row.appendChild(st);
      c1.card.appendChild(row);
      c1.card.appendChild(el('div', { 'class': 'mcp-status-sub' },
        cfg.enabled ? 'AI 客户端当前可连接' : '开启后 AI 才能通过 MCP 连接灯塔'));
      row.onclick = function () {
        sw.classList.add('loading');
        post({ action: 'toggle' }, function (d) {
          if (d) { cfg = d; render(); }
          else { sw.classList.remove('loading'); }
          toast(d && d.enabled ? 'MCP 服务已开启' : d ? 'MCP 服务已关闭' : '请求失败：管理服务无响应');
        });
      };

      /* 卡 2：监听设置（自绘下拉） */
      var c2 = card(body, '监听设置');
      var selIp = cfg.ip;
      var dd = el('div', { 'class': 'mcp-dd' });
      var ddValue = el('div', { 'class': 'mcp-dd-value' });
      var ddList = el('ul', { 'class': 'mcp-dd-list' });
      ddList.style.display = 'none';
      function drawValue() {
        ddValue.textContent = '';
        ddValue.appendChild(document.createTextNode(selIp));
        ddValue.appendChild(el('span', { 'class': 'mcp-dd-arrow' }, '▾'));
      }
      function refreshActive() {
        for (var i = 0; i < ddList.children.length; i++) {
          ddList.children[i].className =
            ddList.children[i].textContent === selIp ? 'active' : '';
        }
      }
      (cfg.ips || []).forEach(function (ip) {
        var li = el('li', null, ip);
        if (ip === selIp) li.className = 'active';
        li.onclick = function (e) {
          e.stopPropagation();
          selIp = ip;
          ddList.style.display = 'none';
          dd.className = 'mcp-dd';
          drawValue();
          refreshActive();
        };
        ddList.appendChild(li);
      });
      ddValue.onclick = function (e) {
        e.stopPropagation();
        var open = ddList.style.display === 'none';
        ddList.style.display = open ? 'block' : 'none';
        dd.className = 'mcp-dd' + (open ? ' open' : '');
      };
      drawValue();
      dd.appendChild(ddValue);
      dd.appendChild(ddList);
      c2.card.appendChild(dd);
      var row2 = el('div', { style: 'display:flex;gap:8px;margin-top:9px;' });
      var portIn = el('input', { 'class': 'mcp-input', type: 'number',
        min: '1024', max: '65535' });
      portIn.value = cfg.port;
      row2.appendChild(portIn);
      var apply = btn('应用', 'primary', function () {
        apply.disabled = true;
        post({ action: 'apply', ip: selIp, port: parseInt(portIn.value, 10) },
          function (d) {
            if (!d) { toast('请求失败'); apply.disabled = false; return; }
            if (d.error) { toast(d.error); apply.disabled = false; return; }
            cfg = d; render();
            toast(d.restarting ? '已应用，服务重启中（约 2 秒）…' : '已应用');
            setTimeout(function () {
              getCfg(function (c) { if (c) { cfg = c; render(); } });
            }, 2500);
          });
      });
      row2.appendChild(apply);
      c2.card.appendChild(row2);
      c2.card.appendChild(el('div', { 'class': 'mcp-tip' },
        '选择 AI 客户端连接用的地址；改端口自动重启生效。'));

      /* 卡 3：服务地址 */
      var c3 = card(body, '服务地址');
      c3.titleRow.appendChild(btn('复制', '', function () { copy(mcpUrl(), '服务地址'); }));
      c3.card.appendChild(el('div', { 'class': 'mcp-code' }, mcpUrl()));
      c3.card.appendChild(el('div', { 'class': 'mcp-tip' },
        'AI 客户端连接的完整端点地址。'));

      /* 卡 4：调用密钥 */
      var c4 = card(body, '调用密钥');
      var b4 = el('span');
      b4.appendChild(btn('复制', '', function () { copy(cfg.api_key, '密钥'); }));
      b4.appendChild(document.createTextNode(' '));
      b4.appendChild(btn('重置', 'danger', function () {
        if (!confirm('重置后需要把新密钥更新到 AI 客户端配置，确定重置？')) return;
        post({ action: 'reset_key' }, function (d) { cfg = d; render(); toast('密钥已重置'); });
      }));
      c4.titleRow.appendChild(b4);
      c4.card.appendChild(el('div', { 'class': 'mcp-code' }, cfg.api_key));
      c4.card.appendChild(el('div', { 'class': 'mcp-tip' },
        '请求头 X-API-Key（或 Authorization: Bearer），缺失或错误一律 401。'));

      /* 卡 5：客户端配置（整行） */
      var c5 = card(body, '客户端配置', true);
      c5.titleRow.appendChild(btn('复制', '', function () { copy(clientConf(), '客户端配置'); }));
      c5.card.appendChild(el('div', { 'class': 'mcp-code' }, clientConf()));
      c5.card.appendChild(el('div', { 'class': 'mcp-tip' },
        '把地址与请求头密钥填入 ZCode / Claude 等 MCP 客户端即可访问灯塔任务与资产数据；服务关闭或密钥变更后 AI 将无法连接。'));
    }

    getCfg(function (d) { cfg = d; render(); });
  }

  /* ---------------- 导航注入（完全对齐原生项） ---------------- */
  function makeMenuItem(native, iconId, label, onClick, extraAttr) {
    var li = el('li', {
      'class': 'ant-menu-item', 'role': 'menuitem', 'data-mcp-item': '1',
      'style': 'padding-left:24px;cursor:pointer;'
    });
    if (extraAttr) for (var x in extraAttr) li.setAttribute(x, extraAttr[x]);
    for (var k in native.li) li.setAttribute(k, native.li[k]);
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'svg-icon anticon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('width', '14');
    svg.setAttribute('height', '14');
    svg.style.verticalAlign = '-0.125em';
    for (var s in native.svg) svg.setAttribute(s, native.svg[s]);
    var use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', '#' + iconId);
    svg.appendChild(use);
    var span = el('span', { 'class': 'menu-title' }, label);
    li.appendChild(svg);
    li.appendChild(span);
    li.onclick = onClick;
    return li;
  }

  function nativeItemAttrs() {
    var items = document.querySelectorAll('li.ant-menu-item:not([data-mcp-item])');
    var out = { li: {}, svg: {} };
    for (var i = 0; i < items.length; i++) {
      var li = items[i];
      for (var j = 0; j < li.attributes.length; j++) {
        var a = li.attributes[j];
        if (a.name.indexOf('data-v-') === 0) out.li[a.name] = a.value;
      }
      var svg = li.querySelector('svg');
      if (svg) {
        for (var m = 0; m < svg.attributes.length; m++) {
          var b = svg.attributes[m];
          if (b.name.indexOf('data-v-') === 0) out.svg[b.name] = b.value;
        }
      }
      if (Object.keys(out.li).length) break;
    }
    return out;
  }

  function inject() {
    var all = document.querySelectorAll('ul.ant-menu:not(.ant-menu-sub)');
    var horizontal = [], vertical = [];
    for (var i = 0; i < all.length; i++) {
      (all[i].className.indexOf('ant-menu-horizontal') >= 0
        ? horizontal : vertical).push(all[i]);
    }
    var hosts = horizontal.concat(vertical);
    for (var j = 0; j < hosts.length; j++) {
      if (hosts[j].querySelector('li[data-mcp-item="1"]')) return;
      var native = nativeItemAttrs();
      hosts[j].appendChild(makeMenuItem(native, 'compass', 'MCP服务器', openPanel));
      hosts[j].appendChild(makeMenuItem(native, 'policy', '全局配置', openGlobalPage,
        { 'data-mcp-global': '1' }));
      return;
    }
  }

  function apiJson(method, url, body, cb) {
    var opts = { method: method };
    if (body !== undefined) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    fetch(url, opts).then(function (r) { return r.json(); }).then(cb)
      .catch(function () { cb(null); });
  }

  /* ---------------- 全局配置页（内容区页面切换，像任务管理） ---------------- */
  var globalPageState = null; // { page, hidden:[], savedSel, headerTitle }

  function _headerTitleEl() {
    return document.querySelector('.ant-layout-header .page-title');
  }

  function openGlobalPage() {
    if (globalPageState) return;
    var content = document.querySelector('.ant-layout-content');
    if (!content) { toast('未找到内容区容器'); return; }

    /* 顶栏标题同步（灯塔页头显示当前栏目名） */
    var headerEl = _headerTitleEl();
    var headerTitle = headerEl ? headerEl.textContent : '';
    if (headerEl) headerEl.textContent = '全局配置';

    var page = el('div', { 'class': 'mcp-page' });

    /* 页头：标题 + 保存 / 重启按钮 */
    var head = el('div', { 'class': 'mcp-page-head' });
    var left = el('div', { style: 'display:flex;align-items:center;gap:16px;' });
    left.appendChild(el('div', { 'class': 'mcp-page-title' }, '全局配置'));
    left.appendChild(el('span', { 'class': 'mcp-page-sub' },
      '灯塔 config.yaml 辅助编辑 · 保存后需重启容器生效'));
    head.appendChild(left);
    var inputs = {};   // path → input 元素
    var right = el('div', { style: 'display:flex;gap:10px;' });
    right.appendChild(btn('保存全部改动', 'primary', function () { saveGlobal(inputs); }));
    right.appendChild(btn('重启服务生效', 'danger', function () {
      if (!confirm('重启后配置才生效；会中断进行中的扫描任务，确定重启？')) return;
      var b = right.lastChild;
      b.disabled = true; b.textContent = '重启中…';
      apiJson('POST', API + '/arlconfig', { action: 'restart' }, function (d2) {
        b.disabled = false; b.textContent = '重启服务生效';
        if (d2 && d2.error) toast(d2.error);
        else toast('重启已开始（scheduler → worker → web）');
      });
    }));
    head.appendChild(right);
    page.appendChild(head);

    /* 内容栅格（数据到达后渲染） */
    var grid = el('div', { 'class': 'mcp-page-grid' });
    page.appendChild(grid);
    var note = el('div', { 'class': 'mcp-note' });
    note.textContent = '配置加载中…';
    page.insertBefore(note, grid);

    /* 隐藏原生路由视图，挂载本页面 */
    var hidden = [];
    for (var i = 0; i < content.children.length; i++) {
      var ch = content.children[i];
      if (ch === page) continue;
      ch.style.display = 'none';
      hidden.push(ch);
    }
    content.appendChild(page);

    /* 菜单选中态接管 */
    var savedSel = document.querySelector(
      'li.ant-menu-item-selected:not([data-mcp-item])');
    if (savedSel) savedSel.className =
      savedSel.className.replace('ant-menu-item-selected', '').trim();
    var mine = document.querySelector('li[data-mcp-global="1"]');
    if (mine && mine.className.indexOf('ant-menu-item-selected') < 0)
      mine.className += ' ant-menu-item-selected';

    globalPageState = { page: page, hidden: hidden, savedSel: savedSel,
      headerEl: headerEl, headerTitle: headerTitle };

    renderGlobal(grid, note, inputs);
  }

  function closeGlobalPage() {
    if (!globalPageState) return;
    var st = globalPageState;
    globalPageState = null;
    st.page.remove();
    for (var i = 0; i < st.hidden.length; i++) st.hidden[i].style.display = '';
    var mine = document.querySelector('li[data-mcp-global="1"]');
    if (mine) mine.className =
      mine.className.replace('ant-menu-item-selected', '').trim();
    if (st.savedSel && st.savedSel.isConnected &&
        st.savedSel.className.indexOf('ant-menu-item-selected') < 0)
      st.savedSel.className += ' ant-menu-item-selected';
    /* 顶栏标题还原（原生路由切换时 Vue 也会自行更新，此处兜底） */
    if (st.headerEl && st.headerEl.isConnected && st.headerTitle)
      st.headerEl.textContent = st.headerTitle;
  }

  /* 点击原生菜单（含分组）即回到原生页面：Vue 照常导航渲染，本页撤下 */
  document.addEventListener('click', function (e) {
    if (!globalPageState || !e.target || !e.target.closest) return;
    var li = e.target.closest('li.ant-menu-item, li.ant-menu-submenu');
    if (li && !li.hasAttribute('data-mcp-item')) closeGlobalPage();
  }, true);

  /* ---------------- 全局配置页渲染 ---------------- */
  function saveGlobal(inputs) {
    var values = {};
    Object.keys(inputs).forEach(function (p) {
      var pin = inputs[p];
      if (pin && pin.value !== undefined) values[p] = pin.value;
    });
    apiJson('POST', API + '/arlconfig', { action: 'save', values: values },
      function (d2) {
        if (d2 && d2.error) { toast(d2.error); return; }
        if (!d2) { toast('请求失败：管理服务无响应'); return; }
        toast('已保存 ' + (d2.applied || []).length + ' 项（掩码跳过 ' +
          (d2.skipped || []).length + ' 项），重启后生效');
      });
  }

  function renderGlobal(grid, note, inputs) {
    var GROUPS = [
      { title: 'FOFA 资产测绘', paths: ['FOFA.EMAIL', 'FOFA.KEY', 'FOFA.URL'],
        tip: '中转站账号把接口地址改成对应 baseurl 即可；Email 留空时部分接口不可用。' },
      { title: 'GitHub 监控', paths: ['GITHUB.TOKEN'],
        tip: '填 PAT 后 GitHub 监控不再受匿名 API 限流；不填则监控任务空跑。' },
      { title: '钉钉通知', paths: ['DINGDING.ACCESS_TOKEN', 'DINGDING.SECRET'],
        tip: '加签机器人两项都必填，缺一不可。' },
      { title: '飞书通知', paths: ['FEISHU.WEBHOOK_URL', 'FEISHU.SECRET'],
        tip: 'Webhook 与加签 Secret 两项都必填。' },
      { title: '企业微信通知', paths: ['WXWORK.WEBHOOK_URL'],
        tip: '群机器人 Webhook 一项即可用。' },
      { title: '自定义 Webhook', paths: ['WEBHOOK.URL', 'WEBHOOK.TOKEN'] },
      { title: '邮件通知',
        paths: ['EMAIL.HOST', 'EMAIL.PORT', 'EMAIL.USERNAME', 'EMAIL.PASSWORD', 'EMAIL.TO'] },
      { title: '扫描代理', paths: ['PROXY.HTTP_URL'],
        tip: 'http://host:port，扫描流量出口代理。' }
    ];
    var PLUGIN_LABEL = {
      'hunter_qax': 'Hunter/奇安信', 'passivetotal': 'PassiveTotal(RiskIQ)',
      'quake_360': 'Quake/360', 'securitytrails': 'SecurityTrails',
      'virustotal': 'VirusTotal', 'zoomeye': 'ZoomEye', 'chaos': 'Chaos(ProjectDiscovery)'
    };

    function fieldRow(path, label, value, sensitive) {
      var row = el('div', { 'class': 'mcp-field-row' });
      var lb = el('span', { 'class': 'mcp-field-label' }, label);
      var pin = el('input', { 'class': 'mcp-input',
        placeholder: sensitive ? '敏感值已掩码，留原样则不修改' : '' });
      pin.value = value || '';
      row.appendChild(lb);
      row.appendChild(pin);
      inputs[path] = pin;
      return row;
    }

    apiJson('GET', API + '/arlconfig', undefined, function (d) {
      if (!globalPageState) return;          // 页面已撤下，丢弃过期响应
      grid.textContent = '';
      if (!d || !d.fields) {
        var err = card(grid, '配置读取', true);
        err.card.appendChild(el('div', { 'class': 'mcp-tip' },
          (d && d.error) ? d.error : '加载失败：管理服务无响应'));
        return;
      }
      note.textContent = '配置来源容器：' + (d.containers || []).join('、') +
        '。掩码值（含 ****）视为未修改，不会覆盖；只提交有改动的字段。';

      var byPath = {};
      (d.fields || []).forEach(function (f) { byPath[f.path] = f; });
      GROUPS.forEach(function (g) {
        var c = card(grid, g.title);
        g.paths.forEach(function (p) {
          var f = byPath[p];
          c.card.appendChild(fieldRow(p, f ? f.label : p,
            f ? f.value : '', f ? f.sensitive : false));
        });
        if (g.tip) c.card.appendChild(el('div', { 'class': 'mcp-tip' }, g.tip));
      });

      /* 第三方测绘插件（QUERY_PLUGIN 中带 key 的）整行：插件双列排布 */
      if ((d.plugins || []).length) {
        var pc = card(grid, '第三方测绘插件（域名收集）', true);
        pc.card.appendChild(el('div', { 'class': 'mcp-tip', style: 'margin-top:0;' },
          '填好 key 并将 enable 改为 true 即启用；FOFA 插件复用上方 FOFA.Key，无需重复填写。'));
        var pg = el('div', { 'class': 'mcp-plugin-grid' });
        (d.plugins || []).forEach(function (pl) {
          var box = el('div', { 'class': 'mcp-plugin' });
          box.appendChild(el('div', { 'class': 'mcp-plugin-name' },
            PLUGIN_LABEL[pl.name] || pl.name));
          pl.fields.forEach(function (f) {
            var path = 'QUERY_PLUGIN.' + pl.name + '.' + f.key;
            box.appendChild(fieldRow(path,
              f.key + (f.sensitive ? '（敏感）' : ''), f.value, f.sensitive));
          });
          pg.appendChild(box);
        });
        pc.card.appendChild(pg);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
  new MutationObserver(inject).observe(document.documentElement,
    { childList: true, subtree: true });
})();
