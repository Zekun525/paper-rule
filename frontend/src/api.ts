export async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : '输入内容无效，请检查后重试。';
    throw new Error(detail);
  }
  return data as T;
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
