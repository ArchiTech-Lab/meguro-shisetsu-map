/* 再開発区域の多角形：描画・計量・保存（localStorage／GeoJSON書き出し・読み込み） */
const RD={drawing:false,pts:[],polys:[],sel:null,edit:false,layers:{},tmp:null,tmpLine:null,tmpMk:[],vm:[]};
const RD_KEY="meguro_redev_v1";
// --- 投影：平面直角座標系IX系（GRS80・原点139°50′E 36°N・k0=0.9999）。面積・距離はこの平面上で測る
const TM=(()=>{const a=6378137,f=1/298.257222101,n=f/(2-f),e=Math.sqrt(f*(2-f)),k0=0.9999,lon0=139+50/60;
 const A=a/(1+n)*(1+n*n/4+n**4/64),al=[n/2-2*n*n/3+5*n**3/16,13*n*n/48-3*n**3/5,61*n**3/240];
 const d=Math.PI/180;
 return(lon,lat)=>{const p=lat*d,l=(lon-lon0)*d,s=Math.sin(p);
  const t=Math.sinh(Math.atanh(s)-e*Math.atanh(e*s)),xi=Math.atan2(t,Math.cos(l)),eta=Math.atanh(Math.sin(l)/Math.sqrt(1+t*t));
  let X=xi,Y=eta;for(let j=1;j<=3;j++){X+=al[j-1]*Math.sin(2*j*xi)*Math.cosh(2*j*eta);Y+=al[j-1]*Math.cos(2*j*xi)*Math.sinh(2*j*eta)}
  return[k0*A*Y,k0*A*X]}})();
const rdArea=r=>{const q=r.map(p=>TM(p[0],p[1]));let s=0;for(let i=0;i<q.length;i++){const a=q[i],b=q[(i+1)%q.length];s+=a[0]*b[1]-b[0]*a[1]}return Math.abs(s)/2};
const rdPeri=r=>{const q=r.map(p=>TM(p[0],p[1]));let s=0;for(let i=0;i<q.length;i++){const a=q[i],b=q[(i+1)%q.length];s+=Math.hypot(a[0]-b[0],a[1]-b[1])}return s};
function pip(x,y,ring){let c=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])c=!c}return c}
function inGeom(x,y,g){const polys=g.type==="Polygon"?[g.coordinates]:g.coordinates;for(const pl of polys){if(pip(x,y,pl[0])){let hole=false;for(let k=1;k<pl.length;k++)if(pip(x,y,pl[k]))hole=true;if(!hole)return true}}return false}
const bb=g=>{let a=1e9,b=1e9,c=-1e9,d=-1e9;(g.type==="Polygon"?[g.coordinates]:g.coordinates).forEach(pl=>pl[0].forEach(p=>{a=Math.min(a,p[0]);c=Math.max(c,p[0]);b=Math.min(b,p[1]);d=Math.max(d,p[1])}));return[a,b,c,d]};
const RDCHB=D.cho.features.map(f=>({f,b:bb(f.geometry)}));
function rdMetrics(P){
 const r=P.ring,area=rdArea(r),per=rdPeri(r);
 let cx=0,cy=0;r.forEach(p=>{cx+=p[0];cy+=p[1]});cx/=r.length;cy/=r.length;
 const xs=r.map(p=>p[0]),ys=r.map(p=>p[1]),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
 const step=Math.max(2,Math.sqrt(area/12000)),dLat=step/111000,dLon=step/(111000*Math.cos(cy*Math.PI/180));
 const S=[];for(let y=y0+dLat/2;y<y1;y+=dLat)for(let x=x0+dLon/2;x<x1;x+=dLon)if(pip(x,y,r))S.push([x,y]);
 const m={area,per,cx,cy,n:S.length};
 // 町丁目ごとの面積比（標本点の割合×区域面積）
 const share={};S.forEach(([x,y])=>{for(const c of RDCHB){if(x<c.b[0]||x>c.b[2]||y<c.b[1]||y>c.b[3])continue;if(inGeom(x,y,c.f.geometry)){const k=c.f.properties.key;share[k]=(share[k]||0)+1;return}}share.out=(share.out||0)+1});
 const N=S.length||1;m.out=(share.out||0)/N*area;delete share.out;
 const tot={y20:0,u15:0,a65:0,y50:0,y100:0},chs=[];
 for(const k in share){const ar=share[k]/N*area,ha=HA[k],t=D.pop.towns[k];if(!t||!ha)continue;const fr=ar/(ha*1e4);
  tot.y20+=fr*t["2020"].total;tot.u15+=fr*t["2020"].u15;tot.a65+=fr*t["2020"].a65;tot.y50+=fr*t.mid["2050"].total;tot.y100+=fr*t.mid["2100"].total;
  const nm=D.cho.features.find(f=>f.properties.key===k).properties.name;chs.push([nm,ar,fr*t["2020"].total])}
 chs.sort((a,b)=>b[1]-a[1]);m.pop=tot;m.chs=chs;
 // 最寄り駅：重心と、区域内で最も近い点
 let b=null,bd=1e9,mb=null,md=1e9;D.stations.forEach(s=>{const d=map.distance([cy,cx],[s.lat,s.lon]);if(d<bd){bd=d;b=s}
  const pts=S.length?S:r;pts.forEach(p=>{const d=map.distance([p[1],p[0]],[s.lat,s.lon]);if(d<md){md=d;mb=s}})});
 m.st={c:[b.name,bd],min:[mb.name,md]};
 m.fac=D.fac.filter(f=>f.lon!=null&&pip(f.lon,f.lat,r));
 m.sch=D.schools.filter(s=>pip(s.lon,s.lat,r));
 m.dist=D.districts.features.filter(f=>inGeom(cx,cy,f.geometry)).map(f=>f.properties.kind+"学校区："+(f.properties.now||f.properties.name));
 return m}
const nf=v=>Math.round(v).toLocaleString();
function rdHtml(P){const m=rdMetrics(P),far=(P.far||300)/100,fl=m.fac.reduce((a,f)=>a+(f.floor_m2||0),0),st=m.fac.reduce((a,f)=>a+(f.site_m2||0),0),bv=m.fac.reduce((a,f)=>a+(f.book_value_yen||0),0);
 const t=m.pop;
 return"<b>"+P.name+"</b><br>面積 <b>"+nf(m.area)+"㎡</b>（"+(m.area/1e4).toFixed(2)+"ha・"+nf(m.area/3.30579)+"坪）　周長 "+nf(m.per)+"m　頂点"+P.ring.length+
 "<br>想定容積率 <input type='number' id='rd_far' value='"+(P.far||300)+"' step='10' min='0' style='width:60px'>% → 想定延床 <b>"+nf(m.area*far)+"㎡</b>"+
 "<br>最寄り駅（重心）："+m.st.c[0]+" 直線"+nf(m.st.c[1])+"m（徒歩約"+Math.ceil(m.st.c[1]/80)+"分）<br>区域内で最も駅に近い点："+m.st.min[0]+" "+nf(m.st.min[1])+"m（約"+Math.ceil(m.st.min[1]/80)+"分）"+
 "<br>"+(m.dist.length?m.dist.join("／"):"学区：重心が区域外")+
 "<br>人口（町丁目の平均密度で按分）：2020年 約"+nf(t.y20)+"人（"+(t.y20/(m.area/1e4)).toFixed(0)+"人/ha）・65歳以上 約"+nf(t.a65)+"・15歳未満 約"+nf(t.u15)+"<br>　2050年（中位）約"+nf(t.y50)+"人／2100年（中位）約"+nf(t.y100)+"人"+
 "<br>町丁目の内訳：".concat(m.chs.map(c=>c[0]+" "+nf(c[1])+"㎡").join("、")||"－")+(m.out>1?"（区外 "+nf(m.out)+"㎡）":"")+
 "<br><b>区有施設（点が区域内）"+m.fac.length+"棟</b>"+(m.fac.length?"：敷地計 "+nf(st)+"㎡（区域の"+(st/m.area*100).toFixed(0)+"%相当）・延床計 "+nf(fl)+"㎡・簿価計 "+(bv/1e8).toFixed(1)+"億円<br>"+m.fac.map(f=>f.name+"（"+nf(f.site_m2||0)+"㎡・"+(f.built||"－")+"年度）").join("、"):"")+
 (m.sch.length?"<br>学校（区域内）："+m.sch.map(s=>s.name).join("、"):"")+
 "<br><span class='m'>面積・周長＝平面直角座標系IX系の平面上（実測との差は0.1%未満の見込み）。人口は町丁目内の分布を一様と仮定した目安。区有施設の敷地計は区域に入った施設の敷地全体（境界をまたぐ分も全量）。</span>"}
// --- 描画・表示
map.createPane("redev").style.zIndex=450;
const RC=["#e67e22","#8e44ad","#c0392b","#16a085","#2c3e50","#d35400"];
function rdSave(){try{localStorage.setItem(RD_KEY,JSON.stringify(RD.polys))}catch(e){}}
function rdLoad(){try{RD.polys=JSON.parse(localStorage.getItem(RD_KEY)||"[]")}catch(e){RD.polys=[]}}
function rdDraw(){for(const k in RD.layers)map.removeLayer(RD.layers[k]);RD.layers={};
 RD.polys.forEach((P,i)=>{const c=RC[i%RC.length],sel=RD.sel===P.id;const L1=L.polygon(P.ring.map(p=>[p[1],p[0]]),{pane:"redev",color:c,weight:sel?4:2.5,fillColor:c,fillOpacity:sel?.3:.18}).addTo(map);
  L1.bindTooltip(P.name+"　"+nf(rdArea(P.ring))+"㎡",{permanent:true,direction:"center",className:"lab"});L1.on("click",e=>{if(RD.drawing)return;L.DomEvent.stopPropagation(e);rdSelect(P.id)});RD.layers[P.id]=L1});
 rdList();rdVerts()}
function rdList(){rd_list.innerHTML=RD.polys.map((P,i)=>"<div class='rdi"+(RD.sel===P.id?" on":"")+"' data-id='"+P.id+"'><span class='sw' style='background:"+RC[i%RC.length]+"'></span>"+P.name+" <small>"+nf(rdArea(P.ring))+"㎡</small></div>").join("")||"<small>まだありません。「多角形を描く」で地図をクリックしてください。</small>";
 rd_list.querySelectorAll(".rdi").forEach(d=>d.onclick=()=>rdSelect(d.dataset.id,true))}
function rdSelect(id,fly){RD.sel=id;const P=RD.polys.find(p=>p.id===id);rdDraw();if(!P){rd_res.innerHTML="";rd_ctl.style.display="none";return}
 rd_ctl.style.display="block";rd_name.value=P.name;rd_res.innerHTML=rdHtml(P);
 const f=document.getElementById("rd_far");if(f)f.onchange=()=>{P.far=+f.value;rdSave();rd_res.innerHTML=rdHtml(P);document.getElementById("rd_far").onchange=f.onchange};
 if(fly)map.fitBounds(RD.layers[id].getBounds().pad(.6))}
function rdVerts(){RD.vm.forEach(m=>map.removeLayer(m));RD.vm=[];if(!RD.edit||!RD.sel)return;const P=RD.polys.find(p=>p.id===RD.sel);if(!P)return;
 P.ring.forEach((p,i)=>{const m=L.marker([p[1],p[0]],{draggable:true,icon:L.divIcon({className:"",iconSize:[14,14],iconAnchor:[7,7],html:"<div style='width:12px;height:12px;border-radius:50%;background:#fff;border:3px solid #c0392b;cursor:move'></div>"})}).addTo(map);
  m.on("drag",e=>{const ll=e.target.getLatLng();P.ring[i]=[ll.lng,ll.lat];RD.layers[P.id].setLatLngs(P.ring.map(q=>[q[1],q[0]]))});
  m.on("dragend",()=>{rdSave();rdSelect(P.id);RD.edit=true;rdVerts()});
  m.on("contextmenu",()=>{if(P.ring.length>3){P.ring.splice(i,1);rdSave();rdDraw();rdSelect(P.id);RD.edit=true;rdVerts()}});RD.vm.push(m)});
 // 辺の中点＝クリックで頂点を追加
 P.ring.forEach((p,i)=>{const q=P.ring[(i+1)%P.ring.length],mid=[(p[1]+q[1])/2,(p[0]+q[0])/2];
  const m=L.marker(mid,{icon:L.divIcon({className:"",iconSize:[10,10],iconAnchor:[5,5],html:"<div style='width:8px;height:8px;border-radius:50%;background:#c0392b;opacity:.55;cursor:copy'></div>"})}).addTo(map);
  m.on("click",e=>{L.DomEvent.stopPropagation(e);P.ring.splice(i+1,0,[mid[1],mid[0]]);rdSave();rdDraw();rdSelect(P.id);RD.edit=true;rdVerts()});RD.vm.push(m)})}
function rdStart(){RD.drawing=true;RD.pts=[];map.doubleClickZoom.disable();map.getContainer().style.cursor="crosshair";rd_b_draw.textContent="描画中…";rd_draw_ctl.style.display="block";rdTmp();
 info("多角形を描いています。地図を順にクリック → 3点以上で「確定」（または最初の点をクリック／Enter）。Backspace＝1点戻す／Esc＝中止")}
function rdTmp(mouse){if(RD.tmp)map.removeLayer(RD.tmp);RD.tmpMk.forEach(m=>map.removeLayer(m));RD.tmpMk=[];if(!RD.pts.length)return;
 const ll=RD.pts.map(p=>[p[1],p[0]]);if(mouse)ll.push(mouse);RD.tmp=L.polygon(ll,{pane:"redev",color:"#e67e22",weight:2,dashArray:"5 4",fillOpacity:.12,interactive:false}).addTo(map);
 RD.pts.forEach((p,i)=>{const m=L.circleMarker([p[1],p[0]],{pane:"redev",radius:i?4:7,color:"#e67e22",fillColor:i?"#fff":"#e67e22",fillOpacity:1,weight:2}).addTo(map);if(i===0)m.on("click",e=>{L.DomEvent.stopPropagation(e);rdFinish()});RD.tmpMk.push(m)});
 if(RD.pts.length>=2){let s=0,q=RD.pts.map(p=>TM(p[0],p[1]));for(let i=1;i<q.length;i++)s+=Math.hypot(q[i][0]-q[i-1][0],q[i][1]-q[i-1][1]);rd_live.textContent=RD.pts.length+"点・辺の合計 "+nf(s)+"m"+(RD.pts.length>=3?"・面積 "+nf(rdArea(RD.pts))+"㎡":"")}else rd_live.textContent=RD.pts.length+"点"}
function rdStop(){RD.drawing=false;RD.pts=[];rdTmp();map.doubleClickZoom.enable();map.getContainer().style.cursor="";rd_b_draw.textContent="多角形を描く";rd_draw_ctl.style.display="none"}
function rdFinish(){if(RD.pts.length<3){alert("3点以上クリックしてください");return}
 const id="p"+Date.now(),n=RD.polys.length+1;RD.polys.push({id,name:"再開発区域"+n,ring:RD.pts.slice(),far:300});rdStop();rdSave();rdSelect(id);rdDraw();rdSelect(id)}
map.on("click",e=>{if(!RD.drawing)return;RD.pts.push([e.latlng.lng,e.latlng.lat]);rdTmp()});
map.on("mousemove",e=>{if(RD.drawing&&RD.pts.length)rdTmp([e.latlng.lat,e.latlng.lng])});
document.addEventListener("keydown",e=>{if(!RD.drawing||/INPUT|TEXTAREA/.test(document.activeElement.tagName))return;
 if(e.key==="Enter")rdFinish();else if(e.key==="Escape")rdStop();else if(e.key==="Backspace"){e.preventDefault();RD.pts.pop();rdTmp()}});
rd_b_draw.onclick=()=>{if(RD.drawing)return;RD.edit=false;rdStart()};
rd_b_fin.onclick=rdFinish;rd_b_undo.onclick=()=>{RD.pts.pop();rdTmp()};rd_b_cancel.onclick=rdStop;
rd_name.onchange=()=>{const P=RD.polys.find(p=>p.id===RD.sel);if(P){P.name=rd_name.value||P.name;rdSave();const s=RD.sel;rdDraw();rdSelect(s)}};
rd_b_edit.onclick=()=>{RD.edit=!RD.edit;rd_b_edit.textContent=RD.edit?"頂点の編集を終える":"頂点を編集";rdVerts()};
rd_b_del.onclick=()=>{const P=RD.polys.find(p=>p.id===RD.sel);if(!P||!confirm("「"+P.name+"」を削除しますか？"))return;RD.polys=RD.polys.filter(p=>p.id!==P.id);RD.sel=null;RD.edit=false;rd_b_edit.textContent="頂点を編集";rdSave();rdDraw();rdSelect(null)};
rd_b_exp.onclick=()=>{const fc={type:"FeatureCollection",features:RD.polys.map(P=>{const r=P.ring.concat([P.ring[0]]);return{type:"Feature",properties:{name:P.name,far_pct:P.far||300,area_m2:Math.round(rdArea(P.ring)*10)/10,perimeter_m:Math.round(rdPeri(P.ring)*10)/10},geometry:{type:"Polygon",coordinates:[r]}}})};
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(fc,null,1)],{type:"application/geo+json"}));a.download="meguro_redev_polygons.geojson";a.click()};
rd_file.onchange=e=>{const f=e.target.files[0];if(!f)return;f.text().then(t=>{try{const g=JSON.parse(t);let n=0;(g.features||[]).forEach(ft=>{const gm=ft.geometry;if(!gm||gm.type!=="Polygon")return;const r=gm.coordinates[0].slice(0,-1);RD.polys.push({id:"p"+Date.now()+"_"+(n++),name:(ft.properties&&ft.properties.name)||"読み込み"+n,ring:r,far:(ft.properties&&ft.properties.far_pct)||300})});rdSave();rdDraw();alert(n+"件を読み込みました")}catch(x){alert("GeoJSON（Polygon）を読めません")}})};
rdLoad();
// プロジェクトに保存した区域（data/manual/redev_polygons.geojson）を取り込む。内容（名前＋面積）が変わった時だけ、名前が無いものを追加する（消した区域は同じ内容では復活しない）
(function(){const sig=D.redev.features.map(f=>f.properties.name+":"+f.properties.area_m2).join("|");let seen="";try{seen=localStorage.getItem(RD_KEY+"_seed")||""}catch(e){}
 if(seen===sig)return;let n=0;D.redev.features.forEach(f=>{if(RD.polys.some(p=>p.name===f.properties.name))return;RD.polys.push({id:"s"+Date.now()+"_"+(n++),name:f.properties.name,ring:f.geometry.coordinates[0].slice(0,-1),far:f.properties.far_pct||300})});
 try{localStorage.setItem(RD_KEY+"_seed",sig)}catch(e){}if(n)rdSave()})();
rdDraw();
