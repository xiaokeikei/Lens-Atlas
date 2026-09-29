import { useState, type ReactNode } from 'react';
import { AlertCircle, Aperture } from 'lucide-react';

export default function UsageNotice({ children }: { children: ReactNode }) {
  const [accepted, setAccepted] = useState(false);
  const [checked, setChecked] = useState(false);

  if (accepted) return <>{children}</>;

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
      <form onSubmit={event => { event.preventDefault(); if (checked) setAccepted(true); }}>
        <label className="usage-notice-check"><input autoFocus type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)}/>我已阅读并理解测试、备份建议及风险提示</label>
        <button className="primary" disabled={!checked}>确认并进入镜迹</button>
      </form>
      <p className="usage-notice-footnote">每次打开或刷新界面均需确认；确认前可关闭窗口或网页退出。此提示不暂停服务端已运行的任务。</p>
    </section>
  </div>;
}
