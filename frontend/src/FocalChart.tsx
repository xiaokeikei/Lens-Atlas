import { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';

type Value = { value:number; count:number; bytes:number };
type Bin = Value & { label:string; lower:number; upper:number|null };
export type FocalData = { bins:Bin[]; values:Value[] };
export const focalLabels=['≤20','20–40','40–80','80–100','100–120','120–150','150–200','200–300','300–400','400–600','600–1000','>1000'];
const inside=(value:number,bin:Bin)=>value>bin.lower&&(bin.upper===null||value<=bin.upper);

function Plot({rows,onPick,label}:{rows:{value:number;count:number;label:string;color:string}[];onPick:(n:number)=>void;label:string}){
  const element=useRef<HTMLDivElement>(null), choose=useRef(onPick);choose.current=onPick;
  useEffect(()=>{
    if(!element.current||!rows.length)return;
    const chart=echarts.init(element.current);
    chart.setOption({animationDuration:150,grid:{left:50,right:18,top:22,bottom:68},
      tooltip:{trigger:'axis',confine:true,renderMode:'richText',axisPointer:{type:'shadow'}},
      xAxis:{type:'category',data:rows.map(r=>r.label),axisLabel:{rotate:35,interval:0,fontSize:10,color:'#87978f'}},
      yAxis:{type:'value',min:0,minInterval:1,axisLabel:{color:'#87978f'},splitLine:{lineStyle:{color:'#87978f33'}}},
      series:[{type:'bar',barMaxWidth:24,data:rows.map(r=>({value:r.count,itemStyle:{color:r.color,borderRadius:[4,4,0,0]}}))}]
    });
    chart.on('click',(event:any)=>{const row=rows[event.dataIndex];if(row&&row.count)choose.current(row.value);});
    const observer=new ResizeObserver(()=>chart.resize());observer.observe(element.current);
    return()=>{observer.disconnect();chart.dispose();};
  },[rows]);
  return <div className="chart" ref={element} role="img" aria-label={label}/>;
}

export default function FocalChart({data,mode,bins,values,onBin,onValue}:{data:FocalData|null;mode:string;bins:number[];values:number[];onBin:(n:number)=>void;onValue:(n:number)=>void}){
  const [anchor,setAnchor]=useState<number|null>(null);
  useEffect(()=>{if(!bins.length&&!values.length)setAnchor(null);},[bins,values]);
  const active=data?.bins.find(b=>bins.includes(b.value)) || data?.bins.find(b=>values.some(v=>inside(v,b)));
  const center=anchor??values[0]??null;
  const all=data?.values||[];
  const index=center===null?-1:all.findIndex(r=>r.value===center);
  const start=Math.max(0,Math.min(Math.max(0,index-5),all.length-11));
  const nearby=index<0?[]:all.slice(start,start+11);
  const overview=useMemo(()=>data?.bins.map(b=>({...b,label:b.label+' mm',color:b.value===active?.value?'#d79e51':'#36846c'}))||[],[data,active?.value]);
  const details=nearby.map(r=>({...r,label:r.value+' mm',color:values.includes(r.value)||r.value===center?'#d79e51':active&&inside(r.value,active)?'#36846c':'#84938b'}));
  const pickBin=(n:number)=>{
    const bin=data?.bins[n];if(!bin||!bin.count)return;
    const best=all.filter(r=>inside(r.value,bin)).sort((a,b)=>b.count-a.count||a.value-b.value)[0];
    setAnchor(best.value);onBin(n);
  };
  return <section className="card chart-card focal-card"><div className="card-title"><div><h3>焦距</h3><p>{mode==='equivalent'?'35mm 等效焦距':'原生焦距'} · 点击区间展开附近具体值</p></div><span className="soft-label">12 区间</span></div>
    <Plot rows={overview} onPick={pickBin} label="焦距区间总览"/>
    <div className="chart-options focal-bins">{data?.bins.map(b=><button disabled={!b.count} key={b.value} className={b.value===active?.value?'active':''} onClick={()=>pickBin(b.value)} title={`${b.lower} < 焦距${b.upper===null?'':` ≤ ${b.upper}`} mm · ${b.count} 个文件`}>{b.label} mm<small>{b.count.toLocaleString()}</small></button>)}</div>
    <p className="helper">区间不重叠：如 20–40 表示 &gt;20 且 ≤40 mm。零值与缺失不归入区间；此图保留其他筛选条件，展示焦距上下文。</p>
    {nearby.length>0?<div className="focal-detail"><div className="card-title"><div><h3>附近具体焦距</h3><p>以 {center} mm 为中心 · 最多 11 个实际存在的值</p></div><div className="button-row"><button aria-label="前一组焦距" disabled={start===0} onClick={()=>setAnchor(all[Math.max(0,index-5)].value)}>←</button><button aria-label="后一组焦距" disabled={start+nearby.length>=all.length} onClick={()=>setAnchor(all[Math.min(all.length-1,index+5)].value)}>→</button></div></div>
      <Plot rows={details} onPick={v=>{setAnchor(v);onValue(v);}} label="附近具体焦距统计"/>
      <div className="chart-options focal-values">{nearby.map(r=><button key={r.value} className={values.includes(r.value)?'active':active&&!inside(r.value,active)?'context-value':''} onClick={()=>{setAnchor(r.value);onValue(r.value);}}>{r.value} mm<small>{r.count.toLocaleString()}</small></button>)}</div>
      <p className="helper">灰色为区间外参考值；点击任意具体值会替换焦距筛选，保留其他条件。</p>
    </div>:<p className="helper">选择一个有数据的区间，查看该区间最常用焦距及前后各 5 个实际焦距值。</p>}
  </section>;
}
