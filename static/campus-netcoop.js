/* Bridge from the illustrative topology to the existing NetCoop API. */
'use strict';
function campusTelemetry(){
  const s=SCENARIOS[activeScenarioKey];
  return {schema_version:'1.0',timestamp:Date.now()/1000,
    source:'User-provided campus simulation; not live campus measurements',
    devices:CAMPUS_BUILDINGS.map(b=>{
      const o=s.overrides[b.id]||{},load=o.load||'18% CPU · 38% RAM';
      return {id:b.id,type:b.id==='citsc_noc'?'router':'switch',status:'unknown',
        cpu_pct:Number(load.match(/(\d+)% CPU/)?.[1]??18),
        mem_pct:load.match(/(\d+)% RAM/) ? Number(load.match(/(\d+)% RAM/)[1]):null,
        if_errors:null,queue_drops:null,link_util_pct:null};
    }),
    links:FIBER_LINKS.map(l=>[l.from,l.to]),
    metrics:{latency_ms:s.avgLatency,jitter_ms:null,packet_loss_pct:parseFloat(s.packetLoss),throughput_mbps:s.throughput*1000,bandwidth_mbps:null},services:{}};
}
function saveCampusJSON(data,name){const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),500);}
document.getElementById('nc-export').onclick=()=>saveCampusJSON(campusTelemetry(),'netcoop-campus-telemetry.json');
document.getElementById('nc-diagnose').onclick=async()=>{
  const button=document.getElementById('nc-diagnose'),out=document.getElementById('nc-output');
  button.disabled=true;out.textContent='Sending the current simulation snapshot to NetCoop agents through MCP…';
  try{
    const mode=document.getElementById('nc-mode').value;
    const response=await fetch('/api/diagnose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telemetry:campusTelemetry(),mode})});
    if(!response.ok)throw new Error('NetCoop API returned '+response.status+'. Open this page through your running Python server.');
    const data=await response.json(),r=data.report;
    if(!r)throw new Error('The server did not return a diagnostic report.');
    out.replaceChildren();
    const title=document.createElement('strong');title.textContent=r.suspected_root_cause;out.append(title);
    const p=document.createElement('p');p.textContent=`${r.status} · ${Math.round(r.confidence*100)}% heuristic confidence. Simulation contains missing measurements, so insufficient evidence is expected.`;out.append(p);
    const download=document.createElement('button');download.textContent='Download agent report';download.onclick=()=>saveCampusJSON(data,r.incident_id+'.json');out.append(download);
    const pre=document.createElement('pre');pre.textContent=JSON.stringify(r,null,2);out.append(pre);
  }catch(e){out.textContent=e.message;}finally{button.disabled=false;}
};
document.getElementById('nc-panel-toggle').onclick=()=>{const p=document.getElementById('nc-panel');p.hidden=!p.hidden;};
document.getElementById('nc-panel-close').onclick=()=>document.getElementById('nc-panel').hidden=true;
document.getElementById('nc-layout-toggle').onclick=()=>{const hidden=document.body.classList.toggle('campus-clean');document.getElementById('nc-layout-toggle').textContent=hidden?'Show controls':'Hide controls';};
