let csrfToken = '';

export async function initializeSession(): Promise<void> {
  const token = new URLSearchParams(window.location.hash.slice(1)).get('owner_token');
  if (token) {
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
  }
  const response = await fetch('/api/session', token ? {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }),
  } : { credentials: 'same-origin' });
  if (!response.ok) throw new Error('需要打开启动终端提供的本机访问链接。');
  const session = await response.json();
  if (typeof session.csrf_token !== 'string' || !session.csrf_token) {
    throw new Error('本机访问会话无效，请重新打开启动链接。');
  }
  csrfToken = session.csrf_token;
}

export async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, body === undefined ? {
    credentials: 'same-origin',
  } : {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(body),
  }).catch(() => { throw new Error('无法连接本机服务。请确认 PaperRule 仍在运行，然后重试。'); });
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('本机访问会话已失效，请重新打开启动终端提供的完整链接。');
    }
    const data = await response.json().catch(() => null);
    const detail = typeof data?.detail === 'string' ? data.detail :
      response.status >= 500 ? '本机服务未完成这次操作，请稍后重试。' : '输入内容无效，请检查后重试。';
    throw new Error(detail);
  }
  return await response.json() as T;
}

export async function encodeFile(file: File): Promise<string> {
  if (file.size > 25 * 1024 * 1024) throw new Error('文件超过 25 MiB，请拆分后导入。');
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return btoa(binary);
}
