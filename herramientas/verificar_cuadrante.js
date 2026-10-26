#!/usr/bin/env node
/*
 * Verifica un cuadrante anual (.xlsx de la plantilla de la empresa) y genera:
 *   - fallos_<nombre>.pdf   hojas por trabajador (como «IMPRESIÓN C. ANUAL») con los fallos marcados
 *   - incidencias_<nombre>.csv   todas las incidencias, identificando a cada trabajador SOLO por su nº de empleado
 *   En la hoja de cada trabajador va su propio nombre (como en la hoja de la empresa) y nada más: ni otros nombres ni el del delegado.
 *
 * Uso:  node herramientas/verificar_cuadrante.js cuadrante.xlsx [opciones]
 *   --salida <carpeta>      dónde dejar los ficheros (por defecto, junto al .xlsx)
 *   --solo-fallos           limita las hojas a los trabajadores con fallos (por defecto: TODOS, porque cada trabajador debe comprobar sus vacaciones y demás)
 *   --por-trabajador        además, un PDF por trabajador (hoja_<NOMBRE_Apellidos>_<nº>.pdf) en <salida>/hojas_individuales/, para enviarlas una a una
 *   --trabajador 75002,75010   solo los PDF individuales de esos nº de empleado (tengan o no fallos)
 *   --calendarios           además, un calendario .ics por trabajador (calendario_<NOMBRE_Apellidos>_<nº>_<año>_<etapa>.ics) en <salida>/calendarios/
 *   --etapa definitivo      nombre del calendario: «Cuadrante AAAA · definitivo» (por defecto «previsión»)
 *   --alarma 60             añade un aviso N minutos antes de cada turno (por defecto, sin aviso)
 *   --limite AAAA-MM-DD     fecha que se imprime en «devolver antes del»
 *   --contacto "texto"      contacto del delegado que se imprime en la hoja
 *   --semana acum           descanso semanal acumulable en 14 días (por defecto: semana lun-dom)
 *   --fs horas              fin de semana libre por horas (por defecto: por casilla)
 *   --banda aviso|no        descanso 12-13 h como aviso o ignorado (por defecto: informativo)
 *   --formacion no          el código F no cuenta como turno
 *   --con-nombres           identifica por nombre (no solo nº) en el CSV y listados; por defecto, solo nº
 *
 * El PDF lleva el nombre de cada trabajador en su hoja: no subirlo al repositorio.
 * Requiere Playwright (ya instalado en las sesiones en la nube) y acceso a npm para bajar SheetJS una vez.
 */
const fs=require('fs'),path=require('path'),os=require('os'),cp=require('child_process');
const {chromium}=require('playwright');

const args=process.argv.slice(2);
const fichero=args.find(a=>!a.startsWith('--')&&/\.xlsx?$/i.test(a));
const opt=n=>{const i=args.indexOf('--'+n);return i<0?null:(args[i+1]&&!args[i+1].startsWith('--')?args[i+1]:true);};
if(!fichero||!fs.existsSync(fichero)){console.error('Uso: node herramientas/verificar_cuadrante.js cuadrante.xlsx [--salida carpeta] [--todos] [--limite AAAA-MM-DD] [--contacto "texto"]');process.exit(1);}
const nombre=path.basename(fichero).replace(/\.xlsx?$/i,'').replace(/[^\w.-]+/g,'_');
const salida=path.resolve(opt('salida')||path.dirname(path.resolve(fichero)));fs.mkdirSync(salida,{recursive:true});

function sheetjs(){
  const dir=path.join(os.tmpdir(),'cuadrantes-xlsx'),f=path.join(dir,'package','dist','xlsx.full.min.js');
  if(!fs.existsSync(f)){
    fs.mkdirSync(dir,{recursive:true});
    cp.execSync('npm pack xlsx@0.18.5 --silent && tar xzf xlsx-0.18.5.tgz',{cwd:dir,stdio:'pipe'});
  }
  return f;
}

(async()=>{
  const b=await chromium.launch(),p=await (await b.newContext({viewport:{width:1250,height:950},acceptDownloads:true})).newPage();
  const errs=[];p.on('pageerror',e=>errs.push(e.message));
  await p.route('**/xlsx.full.min.js',r=>r.fulfill({path:sheetjs(),contentType:'application/javascript'}));
  await p.goto('file://'+path.resolve(__dirname,'..','cuadrantes.html'));
  await p.waitForFunction(()=>typeof XLSX!=='undefined');

  // criterios opcionales (se guardan en el navegador de esta ejecución)
  const sel=(id,v)=>p.evaluate(([id,v])=>{const e=document.getElementById(id);if(e){e.value=v;}},[id,v]);
  if(opt('con-nombres'))await p.check('#c-nombres');
  await p.setInputFiles('#archivo',path.resolve(fichero));
  await p.waitForSelector('#c-res:not(.oculto), #estructura .aviso-caja.err',{timeout:240000});
  const estructura=(await p.textContent('#estructura')).replace(/\s+/g,' ').trim();
  if(await p.locator('#c-res:not(.oculto)').count()===0){
    console.log('ESTRUCTURA INCORRECTA — no se puede verificar:\n'+estructura);await b.close();process.exit(2);
  }
  const cambia=[['pm-critSem',opt('semana')==='acum'?'acum':null],['pm-critFS',opt('fs')==='horas'?'horas':null],['pm-banda',['aviso','no'].includes(opt('banda'))?opt('banda'):null],['pm-formacion',opt('formacion')==='no'?'0':null]].filter(x=>x[1]);
  if(cambia.length){
    for(const [id,v] of cambia)await sel(id,v);
    await p.click('#b-verif');await p.waitForTimeout(1500);
  }
  if(opt('etapa')==='definitivo')await sel('h-etapa','definitivo');
  if(opt('alarma')&&opt('alarma')!==true)await p.evaluate(v=>{const e=document.getElementById('h-alarma');e.value=v;e.dispatchEvent(new Event('change'));},String(opt('alarma')));
  await p.evaluate(()=>document.getElementById('h-etapa').dispatchEvent(new Event('change')));
  if(opt('limite')&&opt('limite')!==true){await p.fill('#h-limite',opt('limite'));await p.dispatchEvent('#h-limite','change');}
  if(opt('contacto')&&opt('contacto')!==true){await p.fill('#h-contacto',opt('contacto'));await p.dispatchEvent('#h-contacto','change');}

  const kpis=(await p.textContent('#kpis')).replace(/\s+/g,' ').trim();
  // CSV de incidencias
  const [dl]=await Promise.all([p.waitForEvent('download'),p.click('#b-csv')]);
  const csv=path.join(salida,'incidencias_'+nombre+'.csv');await dl.saveAs(csv);
  // PDF de hojas
  await p.evaluate(()=>{window.print=()=>{};});
  if(opt('solo-fallos'))await p.check('#lote-solo');else await p.uncheck('#lote-solo');
  await p.click('#b-lote');
  const hojas=await p.locator('#lote .hoja').count();
  let pdf=null;
  if(hojas){
    await p.emulateMedia({media:'print'});
    pdf=path.join(salida,'fallos_'+nombre+'.pdf');
    await p.pdf({path:pdf,preferCSSPageSize:true,printBackground:true});
  }
  // PDF individuales (un fichero por trabajador, nombrado solo con el nº de empleado)
  let individuales=[],calendarios=0;
  const pedidos=opt('trabajador')&&opt('trabajador')!==true?String(opt('trabajador')).split(',').map(x=>x.trim()).filter(Boolean):null;
  if(pedidos||opt('por-trabajador')||opt('calendarios')){
    const filas=await p.evaluate(()=>[...document.querySelectorAll('#t-trab tbody tr')].map(tr=>{const c=tr.querySelectorAll('td');return{etq:c[0].textContent.trim(),err:+c[8].textContent,av:+c[9].textContent};}));
    const mats=filas.map(f=>({mat:(f.etq.match(/(\d+)\)?\s*$/)||[])[1],f}));
    const lista=pedidos?pedidos:mats.filter(x=>!opt('solo-fallos')||x.f.err+x.f.av>0).map(x=>x.mat);
    const dir=path.join(salida,'hojas_individuales');if(opt('por-trabajador')||pedidos)fs.mkdirSync(dir,{recursive:true});
    const dirc=path.join(salida,'calendarios');if(opt('calendarios'))fs.mkdirSync(dirc,{recursive:true});
    await p.emulateMedia({media:'screen'});
    for(const mat of lista){
      if(!mats.some(x=>x.mat===mat)){console.error('No existe el nº de empleado '+mat);continue;}
      await p.fill('#b-emp',mat);await p.click('#b-emp-ok');
      await p.waitForSelector('#modal:not(.oculto)');
      if(opt('por-trabajador')||pedidos){
        await p.emulateMedia({media:'print'});
        const nom=await p.evaluate(()=>{const c=document.querySelector('#m-hoja .emp-cab tr:nth-child(2) td:nth-child(2)');return c?c.textContent.trim():'';});
        const f=path.join(dir,'hoja_'+(nom?nom.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^A-Za-z0-9]+/g,'_').replace(/^_|_$/g,'')+'_':'')+mat+'.pdf');
        await p.pdf({path:f,preferCSSPageSize:true,printBackground:true});
        individuales.push(f);
        await p.emulateMedia({media:'screen'});
      }
      if(opt('calendarios')){const [d]=await Promise.all([p.waitForEvent('download'),p.click('#m-ics')]);await d.saveAs(path.join(dirc,d.suggestedFilename()));calendarios++;}
      await p.click('#m-cerrar');
    }
  }
  console.log(JSON.stringify({estructura,resumen:kpis,hojas,pdf,csv,individuales:individuales.length,carpetaIndividuales:individuales.length?path.dirname(individuales[0]):null,calendarios,carpetaCalendarios:calendarios?path.join(salida,'calendarios'):null,erroresJS:errs},null,2));
  await b.close();
})().catch(e=>{console.error(e);process.exit(1);});
