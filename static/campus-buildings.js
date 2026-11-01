/* Photo-informed architectural massing, not measured/surveyed BIM geometry.
   Positions, heights and network nodes retain the user's schematic model.
   Visual references and modelling limits: campus-sources.json. */
'use strict';
window.createCampusArchitecture = function(b) {
  const T=THREE,g=new T.Group();
  const mat=(c,r=.8,m=0)=>new T.MeshStandardMaterial({color:c,roughness:r,metalness:m});
  const wall=mat(0xe8dfca),white=mat(0xf3f0e6),stone=mat(0xa77758),glass=mat(0x334f5d,.24,.4),roof=mat(0xaaa89b),dark=mat(0x50636a),lawn=mat(0x77965e),water=mat(0x679caa,.2,.25);
  const windows=[];
  function mesh(geo,m,x,y,z){const o=new T.Mesh(geo,m);o.position.set(x,y,z);o.castShadow=true;o.receiveShadow=true;g.add(o);return o;}
  function box(w,h,d,x,y,z,m=wall){return mesh(new T.BoxGeometry(w,h,d),m,x,y,z);}
  function cylinder(r,h,x,y,z,m=white,n=32){return mesh(new T.CylinderGeometry(r,r,h,n),m,x,y,z);}
  function win(x,y,z,w,h,ry=0){windows.push({x,y,z,w,h,ry});}
  function facade(w,d,h,x,z,floors=4){
    const step=h/floors;
    for(let f=0;f<floors;f++){
      const y=step*(f+.5)+.7;
      for(let i=-w/2+2;i<w/2-1;i+=3.2){win(x+i,y,z+d/2+.06,1.65,step*.48);win(x+i,y,z-d/2-.06,1.65,step*.48);}
      for(let i=-d/2+2;i<d/2-1;i+=3.2){win(x+w/2+.06,y,z+i,1.65,step*.48,Math.PI/2);win(x-w/2-.06,y,z+i,1.65,step*.48,Math.PI/2);}
      box(w+.25,.22,d+.25,x,(f+1)*step,z,white);
    }
  }
  function block(w,d,h,x=0,z=0,f=4){box(w,h,d,x,h/2+.6,z);box(w+1,.6,d+1,x,.3,z,stone);facade(w,d,h,x,z,f);box(w+.55,.55,d+.55,x,h+.9,z,roof);}
  function portico(w,z,y=5){box(w,1,7,0,y,z,white);for(let x=-w/2+1;x<w/2;x+=3)box(.5,y,.5,x,y/2,z+2.5,white);for(let i=0;i<4;i++)box(w+2+i*.6,.25,2+i*.6,0,.15+i*.2,z+4-i*.3,stone);}
  function court(w,d){box(w,.15,d,0,.16,0,lawn);box(2,.17,d,0,.18,0,white);box(w,.17,2,0,.19,0,white);cylinder(2,.25,0,.3,0,stone);}
  const w=b.w,d=b.d,h=b.h;
  // Actual landmark: broad, light-coloured stepped wings and a central dome.
  if(b.id==='admin_block'){
    block(w,d*.42,h*.53,0,-d*.23,3);
    block(w*.28,d*.7,h*.67,-w*.35,d*.05,4);block(w*.28,d*.7,h*.67,w*.35,d*.05,4);
    block(w*.4,d*.5,h*.78,0,0,4);
    box(w*.46,.6,d*.55,0,h*.8,0,white);
    cylinder(w*.145,h*.12,0,h*.86,0,white,24);
    mesh(new T.SphereGeometry(w*.145,32,16,0,Math.PI*2,0,Math.PI/2),white,0,h*.92,0);
    cylinder(.18,1.3,0,h*.92+w*.145+.5,0,dark,8);
    portico(w*.52,d*.35,5);
    box(w*.4,.15,3,-w*.35,.1,d*.55,water);box(w*.4,.15,3,w*.35,.1,d*.55,water);
  }else if(b.id==='lhc1'||b.id==='lhc2'){
    // Curved halls inspired by published Udayagiri/Lalitgiri photos, not twin domes.
    block(w*.3,d*.55,h*.66,0,-d*.12,3);
    const r=Math.min(w*.27,d*.36),hh=h*.68;
    for(const sign of [-1,1]){
      const x=sign*w*.25;
      cylinder(r,hh,x,hh/2+.6,0,wall,40);cylinder(r+.3,.6,x,hh+1,0,white,40);
      for(let f=0;f<3;f++){
        cylinder(r+.12,.25,x,(f+1)*hh/3+.6,0,stone,40);
        for(let k=0;k<22;k++){const a=k*Math.PI*2/22;win(x+Math.sin(a)*(r+.05),(f+.5)*hh/3+.7,Math.cos(a)*(r+.05),1.4,hh/3*.5,a);}
      }
      for(let k=0;k<12;k++){const a=k*Math.PI/11;box(.28,hh*.9,.28,x+Math.cos(a)*r,hh*.5,Math.sin(a)*r,white);}
    }
    portico(w*.32,d*.35,6);box(w*.7,.12,4,0,.12,d*.58,water);
    // Light metal entrance canopy, framed rather than a hemispherical roof.
    for(let i=-3;i<=3;i++){const tr=box(.2,.2,8,i*1.4,6.7,d*.38,dark);tr.rotation.x=-.08;}
  }else if(b.archType==='quad_hostel'){
    const t=Math.min(8,w*.18,d*.18);
    block(w,t,h,0,-d/2+t/2,4);block(w,t,h,0,d/2-t/2,4);
    block(t,d-t*2,h,-w/2+t/2,0,4);block(t,d-t*2,h,w/2-t/2,0,4);
    court(w-t*2,d-t*2);
    for(let f=1;f<=4;f++){
      box(w+1,.35,1.7,0,h*f/4-.8,d/2+.5,white);
      box(w+1,.35,1.7,0,h*f/4-.8,-d/2-.5,white);
    }
    for(let x=-w/2+1;x<w/2;x+=3.5){box(.22,h,.22,x,h/2,d/2+1.2,stone);box(.22,h,.22,x,h/2,-d/2-1.2,stone);}
    portico(w*.3,d/2+2,4);
  }else if(b.id==='main_gate'){
    for(const x of [-w*.42,w*.42]){box(4,h,5,x,h/2,0,stone);box(5,.7,6,x,h+.35,0,white);}
    box(w,h*.24,3,0,h*.82,0,white);
    box(6,4,6,-w*.4,2,6,wall);win(-w*.4,2.8,9.1,4,1.3);
    const canvas=document.createElement('canvas');canvas.width=768;canvas.height=96;const c=canvas.getContext('2d');c.fillStyle='#e5dfce';c.fillRect(0,0,768,96);c.fillStyle='#333c37';c.font='bold 33px sans-serif';c.textAlign='center';c.fillText('IIT BHUBANESWAR',384,62);const sign=new T.Mesh(new T.PlaneGeometry(w*.85,2),new T.MeshBasicMaterial({map:new T.CanvasTexture(canvas)}));sign.position.set(0,h*.82,1.52);g.add(sign);
  }else if(b.id==='sac_sports'||b.archType==='high_bay'||b.archType==='sms_workshop'){
    block(w,d,h*.62,0,0,2);
    const arch=new T.Mesh(new T.CylinderGeometry(d*.52,d*.52,w,32,1,false,0,Math.PI),roof);arch.rotation.z=Math.PI/2;arch.rotation.y=Math.PI/2;arch.scale.y=.45;arch.position.y=h*.65;g.add(arch);
    box(w*.75,h*.36,1,0,h*.27,d/2+.1,dark);portico(w*.3,d/2+2,4);
  }else if(b.id==='citsc_noc'){
    // Logical NOC node is not asserted to be the physical administrative tower.
    block(w,d,h*.52,0,0,3);
    portico(w*.45,d/2+1,4);
  }else{
    // Schematic school/library massing with shaded glazing, wings and a courtyard.
    const t=Math.min(8,d*.28);
    block(w,t,h,0,-d/2+t/2,4);
    block(w*.23,d*.75,h*.86,-w*.385,d*.06,4);block(w*.23,d*.75,h*.86,w*.385,d*.06,4);
    court(w*.5,d*.55);portico(w*.35,d*.4,4.5);
    if(b.id==='library'){box(w*.43,h*.72,.4,0,h*.38,-d*.15,glass);for(let x=-w*.2;x<=w*.2;x+=2.8)box(.2,h*.74,.8,x,h*.38,-d*.13,white);}
    if(b.id==='seocs')cylinder(2,.7,w*.32,h*.88,-d*.1,dark,16);
  }
  if(windows.length){const inst=new T.InstancedMesh(new T.BoxGeometry(1,1,.12),glass,windows.length),o=new T.Object3D();windows.forEach((v,i)=>{o.position.set(v.x,v.y,v.z);o.rotation.set(0,v.ry,0);o.scale.set(v.w,v.h,1);o.updateMatrix();inst.setMatrixAt(i,o.matrix);});inst.castShadow=false;g.add(inst);}
  g.name=b.id;g.userData=b;return g;
};
