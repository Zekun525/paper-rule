import './ScopeFiltersEditor.css';

const fields = [
  ['paper', '论文编号'], ['research_type', '研究类型'], ['venue', '投稿期刊'],
  ['article_type', '文章类型'], ['section', '章节'], ['task', '当前任务'],
] as const;

function decode(entry: string, kind: 'include' | 'exclude') {
  const separator = entry.indexOf(':');
  if (separator === -1) {
    return { field: kind === 'include' ? 'paper' : 'legacy', value: entry };
  }
  const field = entry.slice(0, separator).trim().toLowerCase();
  return fields.some(([key]) => key === field)
    ? { field, value: entry.slice(separator + 1).trim() }
    : { field: 'unknown', value: entry };
}

type Props = {
  kind: 'include' | 'exclude';
  entries: string[];
  busy: boolean;
  change: (entries: string[]) => void;
};

export function ScopeFiltersEditor({ kind, entries, busy, change }: Props) {
  const title = kind === 'include' ? '额外适用条件' : '排除条件';
  function update(index: number, field: string, value: string) {
    const encoded = field === 'legacy' || field === 'unknown' ? value : field + ':' + value;
    change(entries.map((entry, position) => position === index ? encoded : entry));
  }
  return <fieldset className="scope-filter-editor" disabled={busy}>
    <legend>{title}</legend>
    <p className="muted">{kind === 'include'
      ? '同一类型满足任一值，不同类型需同时满足；也需符合上方的适用范围。'
      : '命中任一排除条件时，不加载这条规则。'} 值需与论文档案或所选章节、任务的名称一致。</p>
    {entries.map((entry, index) => {
      const row = decode(entry, kind);
      return <div className="scope-filter-row" key={index}>
        <label>{title + ' ' + (index + 1) + ' · 条件类型'}
          <select value={row.field} onChange={event => {
            const value = row.field === 'unknown'
              ? entry.slice(entry.indexOf(':') + 1).trim() : row.value;
            update(index, event.target.value, value);
          }}>
            {fields.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            {kind === 'exclude' && <option value="legacy">论文或章节（精确名称）</option>}
            {row.field === 'unknown' && <option value="unknown">需要澄清的原条件</option>}
          </select>
        </label>
        <label>{title + ' ' + (index + 1) + ' · 条件值'}
          <input required value={row.value}
            onChange={event => update(index, row.field, event.target.value)} />
        </label>
        <button type="button" aria-label={'移除' + title + ' ' + (index + 1)}
          onClick={() => change(entries.filter((_, position) => position !== index))}>
          移除条件
        </button>
        {row.field === 'unknown' && <p className="warning">
          原条件已保留。请选择条件类型并核对值；无法识别的条件会使规则包显示需要澄清。
        </p>}
      </div>;
    })}
    <button type="button" onClick={() => change([...entries, 'paper:'])}>添加{title}</button>
  </fieldset>;
}
