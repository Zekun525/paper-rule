import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import Workbench from './Workbench';
import { initializeSession } from './api';
import './style.css';
import './workbench.css';

const root = createRoot(document.getElementById('root')!);
window.addEventListener('hashchange', () => {
  if (new URLSearchParams(window.location.hash.slice(1)).has('owner_token')) {
    window.location.reload();
  }
});
root.render(createElement('p', null, '正在连接本地 PaperRule…'));
void initializeSession().then(() => {
  root.render(createElement(Workbench));
}).catch(() => {
  root.render(createElement('main', { className: 'panel' },
    createElement('h1', null, 'PaperRule 本机访问'),
    createElement('p', null,
      '请从启动终端打开包含访问凭证的完整链接。服务重新启动后，需要使用新链接。'),
    createElement('p', null, '请保持运行 paperrule app 的终端开启。'),
  ));
});
