import guide from '../../../docs/user-guide.md?raw'
import notificationSetup from '../../../docs/notification-setup.md?raw'

type Block = { kind: 'heading' | 'paragraph' | 'code' | 'list' | 'table'; level?: number; text?: string; items?: string[]; ordered?: boolean; rows?: string[][]; language?: string }

function markdownBlocks(source: string): Block[] {
  const lines = source.replace(/\r/g, '').split('\n')
  const blocks: Block[] = []
  for (let index = 0; index < lines.length;) {
    const line = lines[index]
    if (!line.trim()) { index++; continue }
    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) { blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2] }); index++; continue }
    if (line.startsWith('~~~')) {
      const language = line.slice(3).trim(); const code: string[] = []; index++
      while (index < lines.length && !lines[index].startsWith('~~~')) code.push(lines[index++])
      index++; blocks.push({ kind: 'code', text: code.join('\n'), language }); continue
    }
    if (line.trimStart().startsWith('|')) {
      const rows: string[][] = []
      while (index < lines.length && lines[index].trimStart().startsWith('|')) {
        const cells = lines[index++].trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim())
        if (!cells.every(cell => /^:?-{3,}:?$/.test(cell))) rows.push(cells)
      }
      blocks.push({ kind: 'table', rows }); continue
    }
    const list = line.match(/^\s*(-|\d+\.)\s+(.+)$/)
    if (list) {
      const ordered = list[1] !== '-'; const items: string[] = []
      while (index < lines.length) {
        const item = lines[index].match(/^\s*(-|\d+\.)\s+(.+)$/)
        if (!item || (item[1] !== '-') !== ordered) break
        items.push(item[2]); index++
      }
      blocks.push({ kind: 'list', items, ordered }); continue
    }
    const paragraph: string[] = [line]; index++
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+/.test(lines[index]) &&
      !lines[index].startsWith('~~~') && !lines[index].trimStart().startsWith('|') &&
      !/^\s*(-|\d+\.)\s+/.test(lines[index])) paragraph.push(lines[index++])
    blocks.push({ kind: 'paragraph', text: paragraph.join(' ') })
  }
  return blocks
}

function Inline({ text }: { text: string }) {
  const pattern = new RegExp('(`[^`]+`|\\*\\*[^*]+\\*\\*|\\[[^\\]]+\\]\\([^)]+\\))', 'g')
  return <>{text.split(pattern).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (link) return link[2].startsWith('http') ? <a key={index} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a> : <span key={index}>{link[1]}</span>
    return part
  })}</>
}

export default function HelpPage({ tenant = false, onSignOut }: { tenant?: boolean; onSignOut?: () => void }) {
  const setupSection = notificationSetup.replace(/^# Email and WhatsApp setup/m, '## Email and WhatsApp setup')
  const blocks = markdownBlocks(`${guide}\n\n${setupSection}`)
  const title = blocks.find(block => block.kind === 'heading' && block.level === 1)?.text ?? 'User guide'
  return <main className="content help-page">
    <div className="page-heading"><div><div className="eyebrow">HEARTH HELP</div><h1>{title}</h1><p>Instructions for getting started and using the owner and tenant features.</p></div><div className="help-page-actions"><a className="button secondary" href={tenant ? '/' : '/'}>Back to {tenant ? 'tenant portal' : 'workspace'}</a>{tenant && onSignOut && <button className="button secondary" onClick={onSignOut}>Sign out</button>}</div></div>
    <nav className="panel help-contents" aria-label="Guide contents"><b>In this guide</b><div>{blocks.filter(block => block.kind === 'heading' && block.level === 2).map(block => <a key={block.text} href={`#${block.text?.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>{block.text}</a>)}</div></nav>
    <article className="panel help-document">{blocks.filter(block => !(block.kind === 'heading' && block.level === 1)).map((block, index) => {
      if (block.kind === 'heading') {
        const id = block.text?.toLowerCase().replace(/[^a-z0-9]+/g, '-')
        return block.level === 2 ? <h2 id={id} key={index}>{block.text}</h2> : <h3 id={id} key={index}>{block.text}</h3>
      }
      if (block.kind === 'paragraph') return <p key={index}><Inline text={block.text ?? ''} /></p>
      if (block.kind === 'code') return <pre key={index}><code>{block.text}</code></pre>
      if (block.kind === 'list') {
        const List = block.ordered ? 'ol' : 'ul'
        return <List key={index}>{block.items?.map((item, itemIndex) => <li key={itemIndex}><Inline text={item} /></li>)}</List>
      }
      return <div className="help-table-wrap" key={index}><table><tbody>{block.rows?.map((row, rowIndex) => {
        const Cell = rowIndex === 0 ? 'th' : 'td'
        return <tr key={rowIndex}>{row.map((cell, cellIndex) => <Cell key={cellIndex}><Inline text={cell} /></Cell>)}</tr>
      })}</tbody></table></div>
    })}</article>
  </main>
}
