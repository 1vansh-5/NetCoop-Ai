/* Additive integration: load on any existing landing/dashboard page. */
(()=>{if(document.getElementById('netcoop-campus-link'))return;
const link=document.createElement('a');link.id='netcoop-campus-link';link.href='/campus.html';link.textContent='◈  3D Campus';link.setAttribute('aria-label','Open IIT Bhubaneswar campus topology');
Object.assign(link.style,{position:'fixed',bottom:'22px',right:'22px',zIndex:'30',background:'#16392e',color:'#d1ffe5',border:'1px solid #6aaf90',borderRadius:'9px',padding:'11px 17px',font:'600 12px system-ui',textDecoration:'none',boxShadow:'0 5px 24px #0005'});document.body.append(link);})();
