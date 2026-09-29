import { useState } from 'react';
import { AlertCircle, Aperture } from 'lucide-react';

export default function UsageNotice({ onAccept }: { onAccept: () => Promise<void> }) {
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  return <div className="modal-backdrop usage-notice-backdrop">
    <section className="modal usage-notice" role="dialog" aria-modal="true" aria-labelledby="usage-notice-title" aria-describedby="usage-notice-description">
      <div className="usage-notice-brand"><Aperture size={28}/><span>镜迹 · Lens Atlas</span></div>
      <h1 id="usage-notice-title">使用前请先测试并备份</h1>
      <div id="usage-notice-description">
        <p><strong>建议先使用单独的测试文件夹，放入少量已备份的照片和视频；确认扫描、预览及其他功能无异常后，再添加正式数据目录。</strong></p>
        <p>使用前请独立备份重要资料。镜迹的索引、缩略图和应用数据库备份不能代替原始照片、视频的备份。</p>
        <p>NAS 部署时请将素材目录以只读方式挂载，并将应用数据目录与素材目录分开。</p>
        <div className="usage-notice-warning"><AlertCircle size={20}/><p><strong>因使用本软件导致的资料丢失、损坏或其他损失，开发者概不负责，使用风险由用户自行承担。</strong></p></div>
      </div>
      <form onSubmit={async event => {
        event.preventDefault();
        if (!checked || saving) return;
        setSaving(true); setError('');
        try { await onAccept(); }
        catch { setError('确认状态保存失败，请检查服务连接后重试。'); }
        finally { setSaving(false); }
      }}>
        <label className="usage-notice-check"><input autoFocus type="checkbox" checked={checked} disabled={saving} onChange={event => setChecked(event.target.checked)}/>我已阅读并理解测试、备份建议及风险提示</label>
        {error && <p role="alert">{error}</p>}
        <button className="primary" disabled={!checked || saving}>{saving ? '正在保存…' : '确认并进入镜迹'}</button>
      </form>
      <p className="usage-notice-footnote">仅首次使用时提醒，确认记录保存在应用数据中；保留数据升级或重启后不再弹出。此提示不暂停服务端已运行的任务。</p>
    </section>
  </div>;
}
