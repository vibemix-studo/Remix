(function(){
const $=id=>document.getElementById(id);
const box=document.createElement('section');
box.innerHTML=`<h2>Import and split (server)</h2>
<div class="row"><label>Audio link or playlist (.m3u, .m3u8, .pls)<input id="sUrl" type="text" placeholder="https://example.com/track.mp3" style="background:#0c1224;color:inherit;border:1px solid var(--line);border-radius:8px;padding:6px 8px;font:inherit;width:100%"></label>
<button class="btn main" id="sImp">Import</button></div>
<div class="row" style="margin-top:10px"><label>Split vocals from a file<input id="sFile" type="file" accept="audio/*"></label>
<button class="btn ai" id="sSplit">Split vocals</button></div>
<label class="check" style="margin-top:10px"><input type="checkbox" id="sRights"> I have the rights to use this audio</label>
<p class="hint">Links must point straight to an audio file. YouTube, Spotify and similar pages are not supported. Splitting runs Demucs and can take a few minutes. The vocals and instrumental arrive as two tracks you can use in Mashup mode.</p>
<p class="hint" id="sMsg" role="status"></p>`;
document.querySelector('main .stack').prepend(box);
const msg=t=>$('sMsg').textContent=t;
function give(files){const dt=new DataTransfer();files.forEach(f=>dt.items.add(f));$('file').files=dt.files;$('file').dispatchEvent(new Event('change'))}
async function post(url,body,isForm){
  const r=await fetch(url,isForm?{method:'POST',body}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){let m='Request failed.';try{m=(await r.json()).detail||m}catch(e){}throw new Error(m)}
  return r;
}
async function getFile(u){const r=await post('/api/import',{url:u,rights:true});const b=await r.blob();return new File([b],r.headers.get('X-Filename')||'track.mp3',{type:b.type})}
$('sImp').onclick=async()=>{
  const u=$('sUrl').value.trim();
  if(!u)return msg('Paste a direct audio link first.');
  if(!$('sRights').checked)return msg('Confirm that you have the rights to use this audio.');
  $('sImp').disabled=true;
  try{
    let urls=[u];
    if(/\.(m3u8?|pls)(\?|$)/i.test(u)){msg('Reading playlist…');urls=(await(await post('/api/playlist',{url:u,rights:true})).json()).urls}
    const files=[];
    for(let i=0;i<urls.length;i++){msg('Downloading '+(i+1)+' of '+urls.length+'…');try{files.push(await getFile(urls[i]))}catch(e){msg('Skipped one link: '+e.message)}}
    if(files.length){give(files);msg('Imported '+files.length+' track(s).')}
  }catch(e){msg(e.message)}
  $('sImp').disabled=false;
};
$('sSplit').onclick=async()=>{
  const f=$('sFile').files[0];
  if(!f)return msg('Choose an audio file to split.');
  if(!$('sRights').checked)return msg('Confirm that you have the rights to use this audio.');
  $('sSplit').disabled=true;msg('Separating vocals… this can take a few minutes.');
  try{
    const fd=new FormData();fd.append('file',f);fd.append('rights','true');
    const j=await(await post('/api/separate',fd,true)).json(),out=[];
    for(const k of['vocals','instrumental']){const b=await(await fetch(j.stems[k])).blob();out.push(new File([b],j.base+' ('+k+').wav',{type:'audio/wav'}))}
    give(out);msg('Added vocals and instrumental as two tracks.');
  }catch(e){msg(e.message)}
  $('sSplit').disabled=false;
};
})();
