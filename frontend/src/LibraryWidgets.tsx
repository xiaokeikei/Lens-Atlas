import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { Camera } from 'lucide-react';
type Group = { value:string|number; count:number; bytes:number };
const num=(n:number)=>(n||0).toLocaleString('zh-CN');

export function Chart({title,subtitle,rows,selected,onSelect,type='bar',suffix=''}:{title:string;subtitle:string;rows:Group[];selected:(string|number)[];onSelect:(value:any)=>void;type?:'bar'|'line'|'column';suffix?:string}) {
  const element = useRef<HTMLDivElement>(null);
  const choose = useRef(onSelect); choose.current=onSelect;
  useEffect(()=>{
    if(!element.current || !rows.length) return;
    const chart=echarts.init(element.current,undefined,{renderer:'canvas'});
    const horizontal=type==='bar';
    const labels=rows.map(r=>String(r.value)+suffix);
    chart.setOption({animationDuration:280,grid:{left:horizontal?130:44,right:25,top:16,bottom:horizontal?24:46},tooltip:{trigger:'axis',confine:true,renderMode:'richText',axisPointer:{type:'shadow'}},
      xAxis:horizontal?{type:'value',min:0,minInterval:1,splitLine:{lineStyle:{color:'#eef0ed'}},axisLabel:{color:'#89938f',fontSize:10}}:{type:'category',data:labels,axisTick:{show:false},axisLine:{lineStyle:{color:'#e3e8e4'}},axisLabel:{color:'#718078',fontSize:10,rotate:rows.length>10?35:0}},
      yAxis:horizontal?{type:'category',data:labels,inverse:true,axisTick:{show:false},axisLine:{show:false},axisLabel:{color:'#46564d',fontSize:11,width:112,overflow:'truncate'}}:{type:'value',min:0,minInterval:1,splitLine:{lineStyle:{color:'#eef0ed'}},axisLabel:{color:'#89938f',fontSize:10}},
      dataZoom:rows.length>12?[{type:'slider',...(horizontal?{yAxisIndex:0}:{xAxisIndex:0}),start:0,end:Math.min(100,12/rows.length*100),width:horizontal?8:undefined,height:horizontal?undefined:12,showDetail:false,borderColor:'transparent'}]:[],
      series:[{type:type==='line'?'line':'bar',barMaxWidth:20,smooth:false,symbolSize:7,lineStyle:{color:'#257b64',width:2},areaStyle:type==='line'?{color:'#e0eee7'}:undefined,label:{show:horizontal,position:'right',color:'#627369',fontSize:11},data:rows.map(r=>({value:r.count,itemStyle:{color:selected.includes(r.value)?'#d79e51':'#36846c',borderRadius:horizontal?[0,4,4,0]:[4,4,0,0]}}))}]});
    chart.on('click',(event:any)=>{const row=rows[event.dataIndex];if(event.componentType==='series'&&row)choose.current(row.value);});
    const observer=new ResizeObserver(()=>chart.resize()); observer.observe(element.current);
    return ()=>{observer.disconnect();chart.dispose();};
  },[rows,selected,type,suffix]);
  return <section className="card chart-card"><div className="card-title"><div><h3>{title}</h3><p>{subtitle}</p></div><span className="soft-label">{rows.length} 类</span></div>{rows.length?<><div className="chart" ref={element} role="img" aria-label={`${title}统计图，点击分类可筛选`}/><div className="chart-options">{rows.map(r=><button className={selected.includes(r.value)?'active':''} key={r.value} onClick={()=>onSelect(r.value)} title={`${r.value}${suffix} · ${num(r.count)} 个文件`}>{String(r.value)}{suffix}<small>{num(r.count)}</small></button>)}</div></>:<div className="empty-chart">暂无可统计的{title}记录</div>}</section>;
}

export function Metric({icon:Icon,label,value,hint}:{icon:typeof Camera;label:string;value:string;hint:string}){return <section className="card metric"><div><span>{label}</span><Icon size={19}/></div><strong>{value}</strong><p>{hint}</p></section>;}
