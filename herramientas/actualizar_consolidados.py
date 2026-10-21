#!/usr/bin/env python3
"""
Consolidados de ILUNION_Documentacion para la app de afiliados.

Genera/actualiza (de forma incremental, sin reprocesar lo ya leído):
  01_TC1_TC2_Seguridad_Social/TC2_consolidado.json  (+ TC2_resumen.csv)
  01_TC1_TC2_Seguridad_Social/TC1_consolidado.json  (+ TC1_resumen.csv)
  02_Registro_Jornada_REGJOR/REGJOR_consolidado.json (+ REGJOR_resumen.csv)

Uso:  python3 actualizar_consolidados.py [--barrer] [--forzar] [--auto]
      python3 actualizar_consolidados.py --instalar      (programa la ejecución automática en macOS)
      python3 actualizar_consolidados.py --desinstalar   (la quita; no borra ningún dato)
  --barrer  antes, mueve a su carpeta los PDF de TC1/TC2/REGJOR sueltos en Descargas. Los reconoce por el nombre y,
            si el nombre no vale, por su CONTENIDO. Si en la carpeta ya hay un archivo con ese nombre pero distinto,
            lo guarda con otro nombre en vez de saltárselo.
  --forzar  ignora lo ya procesado y lo relee todo
  --auto    modo tarea programada: barre, actualiza y avisa con una notificación solo si hay novedades
            (un solo proceso a la vez; espera a que termine de descargarse un PDF recién llegado)
Requiere: node + pdfjs-dist@3.11.174 (variable NODE_PATH o PDFJS_DIR), pdftotext/pdftoppm/tesseract (solo para escaneados).
La lectura de texto usa la MISMA lógica de orden de lectura que afiliados.html.
"""
import os, re, sys, json, csv, hashlib, subprocess, shutil, tempfile, datetime, time
try: import fcntl
except ImportError: fcntl = None
# Una tarea programada arranca con un PATH mínimo: se añaden las rutas de Homebrew (chip Apple e Intel)
os.environ['PATH'] = os.pathsep.join(['/opt/homebrew/bin', '/usr/local/bin', os.environ.get('PATH', '')])

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
DESCARGAS = os.path.dirname(BASE)
D01 = os.path.join(BASE, '01_TC1_TC2_Seguridad_Social')
D02 = os.path.join(BASE, '02_Registro_Jornada_REGJOR')
PDFTEXT = os.environ.get('PDFTEXT_JS', os.path.join(AQUI, 'pdftext.js'))
MESES = ['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE']
FORZAR = '--forzar' in sys.argv
AHORA = datetime.datetime.now().isoformat(timespec='seconds')
# Presupuesto de tiempo por ejecución (s): si se agota, se guarda lo hecho y basta con volver a lanzar.
DEADLINE = time.time() + float(os.environ.get('BUDGET', '10000'))
CACHE_OCR = os.environ.get('OCR_CACHE', os.path.join(tempfile.gettempdir(), 'ocr_cache_ilunion'))
class SinTiempo(Exception): pass
PENDIENTE = []
NOVEDADES = []   # lo nuevo de esta ejecución, para la notificación
def comprobar_tiempo():
    if time.time() > DEADLINE: raise SinTiempo()

def sha1(p):
    h = hashlib.sha1()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

def etiqueta(clave):
    a, m = clave.split('-'); return f'{MESES[int(m)-1].capitalize()} {a}'

def cargar(p, vacio):
    if os.path.exists(p) and not FORZAR:
        with open(p, encoding='utf-8') as f: return json.load(f)
    return vacio

def guardar(p, d):
    d['actualizado'] = AHORA
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)

def csv_out(p, cab, filas):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';'); w.writerow(cab); w.writerows(filas)

def paginas_texto(pdf):
    """Texto por página, con la lógica de orden de lectura de la app."""
    r = subprocess.run(['node', PDFTEXT, pdf], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines():
        if l.startswith('{"p"'): out.append(json.loads(l)['t'])
    return out

def ocr_paginas(pdf, psm):
    """OCR página a página con caché (reanudable si se agota el tiempo)."""
    h = sha1(pdf); cd = os.path.join(CACHE_OCR, f'{h}_{psm}'); os.makedirs(cd, exist_ok=True)
    n = len(__import__('pypdf').PdfReader(pdf).pages)
    res = []
    for i in range(1, n + 1):
        tf = os.path.join(cd, f'{i}.txt')
        if not os.path.exists(tf):
            comprobar_tiempo()
            tmp = tempfile.mkdtemp(prefix='ocr_')
            try:
                subprocess.run(['pdftoppm', '-r', '300', '-gray', '-png', '-f', str(i), '-l', str(i), pdf, os.path.join(tmp, 'p')], check=True)
                img = os.path.join(tmp, sorted(os.listdir(tmp))[0])
                r = subprocess.run(['tesseract', img, '-', '--psm', str(psm)], capture_output=True, text=True)
                open(tf, 'w', encoding='utf-8').write(r.stdout)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        res.append(open(tf, encoding='utf-8').read())
    return res

AUTO = '--auto' in sys.argv
MIN_EDAD = 90      # s: un PDF modificado hace menos puede estar aún descargándose
VISTOS = os.path.join(AQUI, 'barrido_visto.json')   # huellas de PDF de Descargas ya examinados y que no hay que mover

def primera_pagina(pdf, limite=120):
    """Texto de la primera página (misma lectura que la app). Corta en cuanto la tiene."""
    try: pr = subprocess.Popen(['node', PDFTEXT, pdf], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError: return ''
    t0 = time.time(); texto = ''
    try:
        for l in pr.stdout:
            if l.startswith('{"p"'): texto = json.loads(l)['t']; break
            if time.time() - t0 > limite: break
    finally:
        pr.kill(); pr.wait()
    return texto

def tipo_por_nombre(f):
    if re.match(r'^TC[12]\.', f, re.I): return f[:3].upper(), f
    if re.match(r'^REGJOR(?!_)', f, re.I): return 'REGJOR', f
    return None, f

def tipo_por_contenido(pdf):
    """(tipo, nombre canónico) leyendo la primera página, o (None, None). El nombre canónico es el que la ruta de
    proceso espera: TC2. … / REGJOR…"""
    t = primera_pagina(pdf)
    m = RE_HEAD.search(t)
    if m:
        return 'REGJOR', f'REGJOR{m.group(3).upper()}{m.group(4)}SEGURIDADSEVILLA.pdf'
    if re.search(r'NOMINAL\s+DE\s+TRABAJADORES', t, re.I):
        p = re.search(r'\b(\d{2})/(\d{4})\s*-\s*(\d{2})/(\d{4})\b', t)
        suf = f' [{MESES[int(p.group(3)) - 1].capitalize()} {p.group(4)}]' if p and 1 <= int(p.group(3)) <= 12 else ''
        return 'TC2', f'TC2. ILUNION SEGURIDAD SEVILLA{suf}.pdf'
    return None, None

def mover_sin_pisar(p, destdir, nombre):
    dst = os.path.join(destdir, nombre)
    if os.path.exists(dst):
        if sha1(dst) == sha1(p): print('  ya estaba (idéntico), se deja sin mover:', nombre); return False
        base, ext = os.path.splitext(nombre)
        dst = os.path.join(destdir, f'{base}-{sha1(p)[:8]}{ext}')     # mismo nombre, otro contenido: no se pisa ni se salta
        if os.path.exists(dst): return False
    shutil.move(p, dst); print('  movido a', os.path.basename(destdir), ':', os.path.basename(dst)); return True

def barrer():
    destinos = {'TC1': D01, 'TC2': D01, 'REGJOR': D02}
    try: visto = set(json.load(open(VISTOS, encoding='utf-8')))
    except (OSError, ValueError): visto = set()
    n, ahora = 0, time.time()
    for f in sorted(os.listdir(DESCARGAS)):
        p = os.path.join(DESCARGAS, f)
        if not (os.path.isfile(p) and f.lower().endswith('.pdf')): continue
        if ahora - os.path.getmtime(p) > 120 * 86400: continue          # solo lo reciente: Descargas puede tener de todo
        edad = time.time() - os.path.getmtime(p)
        if edad < MIN_EDAD:
            if not AUTO: print('  muy reciente, se omite (¿descargándose?):', f); continue
            time.sleep(MIN_EDAD - edad + 1)
        h = sha1(p)
        if h in visto: continue
        tipo, nombre = tipo_por_nombre(f)
        if not tipo: tipo, nombre = tipo_por_contenido(p)
        if tipo and mover_sin_pisar(p, destinos[tipo], nombre): n += 1; continue
        visto.add(h)         # no es de los nuestros, o ya estaba: no se vuelve a examinar
    json.dump(sorted(visto), open(VISTOS, 'w', encoding='utf-8'))
    print(f'barrido: {n} archivo(s)')

# ---------------- DNI ----------------
LETRAS = 'TRWAGMYFPDXBNJZSQVHLCKE'
def dni_valido(d):
    d = d.upper()
    if not re.fullmatch(r'[0-9XYZ]\d{7}[A-Z]', d): return False
    n = d[:-1].translate(str.maketrans('XYZ', '012'))
    return LETRAS[int(n) % 23] == d[-1]

# ---------------- TC2 ----------------
RE_TC2_TEXTO = re.compile(r'\b\d{12}\s+\d{2}([0-9A-Z]{8}[A-Z])\s+([A-Za-z]{2,6})\b')          # igual que la app
RE_TC2_OCR = re.compile(r'\b\d{11,13}\b\W{0,4}\d{2}([0-9XYZ]\d{7}[A-Za-z])\b(?:\W{0,4}([A-Za-z]{2,6}))?')

def procesar_tc2(pdf):
    pags = paginas_texto(pdf)
    metodo = 'texto'
    if sum(len(t) for t in pags) < 200 * max(1, len(pags)):
        metodo = 'ocr'; pags = ocr_paginas(pdf, 4)
    dnis, cafs, descartados, mes = set(), set(), 0, {}
    for t in pags:
        if metodo == 'texto':
            m = re.search(r'\b(\d{2})/(\d{4})\s*-\s*(\d{2})/(\d{4})\b', t)
            if m: mes[(m.group(4), m.group(3))] = mes.get((m.group(4), m.group(3)), 0) + 1
            for m in RE_TC2_TEXTO.finditer(t): dnis.add(m.group(1)); cafs.add(m.group(2).upper())
        else:
            for m in re.finditer(r'\b01-(\d{2})-(\d{4})\b', t): mes[(m.group(2), m.group(1))] = mes.get((m.group(2), m.group(1)), 0) + 1
            for m in RE_TC2_OCR.finditer(t):
                dn = m.group(1).upper()
                if dni_valido(dn):
                    dnis.add(dn)
                    if m.group(2): cafs.add(m.group(2).upper())
                else: descartados += 1
    if not mes or not dnis: return None
    (a, mm) = max(mes, key=mes.get)
    return {'clave': f'{a}-{mm}', 'dnis': sorted(dnis), 'cafs': sorted(cafs), 'metodo': metodo,
            'paginas': len(pags), 'descartados_ocr': descartados}

def actualizar_tc2():
    p = os.path.join(D01, 'TC2_consolidado.json')
    d = cargar(p, {'tipo': 'tc2_consolidado', 'version': 1, 'periodos': {}, 'fuentes': []})
    vistos = {f['sha1'] for f in d['fuentes']}
    try:
        for f in sorted(os.listdir(D01)):
            if not re.match(r'^TC2\.', f, re.I) or not f.lower().endswith('.pdf'): continue
            fp = os.path.join(D01, f); h = sha1(fp)
            if h in vistos: continue
            comprobar_tiempo(); print('TC2 leyendo', f, flush=True)
            r = procesar_tc2(fp)
            if not r:
                print('  !! no se ha podido leer (¿no es un TC2?):', f); d['fuentes'].append({'archivo': f, 'sha1': h, 'error': True}); NOVEDADES.append(f'TC2 no legible: {f}'); continue
            k = r['clave']; ant = d['periodos'].get(k)
            if ant and ant['metodo'] == 'texto' and r['metodo'] == 'ocr':
                print('  ya había lectura por texto de', k, '- se conserva'); d['fuentes'].append({'archivo': f, 'sha1': h, 'periodo': k, 'ignorado': 'duplicado'}); continue
            d['periodos'][k] = {'etiqueta': etiqueta(k), 'trabajadores': len(r['dnis']), 'dnis': r['dnis'], 'cafs': r['cafs'],
                                'metodo': r['metodo'], 'fiable': r['metodo'] == 'texto', 'descartados_ocr': r['descartados_ocr'], 'archivo': f, 'sha1': h}
            d['fuentes'].append({'archivo': f, 'sha1': h, 'periodo': k, 'procesado': AHORA})
            print(f'  -> {k}: {len(r["dnis"])} DNI ({r["metodo"]}, descartados {r["descartados_ocr"]})')
            NOVEDADES.append(f'TC2 {etiqueta(k)}' + ('' if r['metodo'] == 'texto' else ' (escaneado: no fiable)'))
    except SinTiempo:
        PENDIENTE.append('TC2')
    d['periodos'] = dict(sorted(d['periodos'].items()))
    guardar(p, d)
    csv_out(os.path.join(D01, 'TC2_resumen.csv'), ['periodo', 'cotizantes_DNI_distintos', 'lectura', 'descartados_OCR', 'archivo'],
            [[k, v['trabajadores'], v['metodo'], v['descartados_ocr'], v['archivo']] for k, v in d['periodos'].items()])
    return d

# ---------------- TC1 ----------------
def num(s): return float(s.replace('.', '').replace(',', '.'))
def procesar_tc1(pdf):
    pags = paginas_texto(pdf); metodo = 'texto'
    if sum(len(t) for t in pags) < 200 * max(1, len(pags)):
        metodo = 'ocr'; pags = ocr_paginas(pdf, 4)
    t = ' '.join(pags)
    m = re.search(r'P\S{1,3}odo\s+de\s+Liquidaci\S*\s*:?\s*(\d{2})\s*/\s*(\d{4})', t, re.I) or re.search(r'PERIODO:\s*(\d{2})/(\d{4})', t, re.I)
    if not m: return None
    n = re.search(r'trabajadores confirmados\S*\s*:?\s*(\d{2,4})', t, re.I)
    l = re.search(r'LIQUIDO DE TOTALES\s*([\d.]+,\d{2})', t)
    nl = re.search(r'liquidaci\S*n\s*:?\s*(\d{17})', t, re.I)
    calculado = False
    if not l:   # la casilla sombreada del total no siempre se lee por OCR: se suma de sus tres partes
        parts = [re.search(x + r'\s*([\d.]+,\d{2})', t) for x in ('LIQUIDO CONTINGENCIAS COMUNES', 'LIQUIDO DE ACCIDENTES DE TRABAJO', 'LIQUIDO DE OTRAS COTIZACIONES')]
        if all(parts): l = type('M', (), {'group': lambda self, i, v=f"{sum(num(x.group(1)) for x in parts):.2f}".replace('.', ','): v})(); calculado = True
    if l and num(l.group(1)) < 50000:   # cifra implausible (miles mal leídos por OCR): mejor vacía que falsa
        l = None
    return {'liquido_calculado': calculado, 'clave': f'{m.group(2)}-{m.group(1)}', 'trabajadores_confirmados': int(n.group(1)) if n else None,
            'liquido_totales': num(l.group(1)) if l else None, 'num_liquidacion': nl.group(1) if nl else None, 'metodo': metodo}

def actualizar_tc1():
    p = os.path.join(D01, 'TC1_consolidado.json')
    d = cargar(p, {'tipo': 'tc1_consolidado', 'version': 1, 'periodos': {}, 'fuentes': []})
    vistos = {f['sha1'] for f in d['fuentes']}
    try:
        for f in sorted(os.listdir(D01)):
            if not re.match(r'^TC1\.', f, re.I) or not f.lower().endswith('.pdf'): continue
            fp = os.path.join(D01, f); h = sha1(fp)
            if h in vistos: continue
            comprobar_tiempo(); print('TC1 leyendo', f, flush=True)
            r = procesar_tc1(fp)
            if not r: print('  !! sin periodo legible:', f); d['fuentes'].append({'archivo': f, 'sha1': h, 'error': True}); continue
            k = r.pop('clave'); r.update({'etiqueta': etiqueta(k), 'archivo': f, 'sha1': h}); d['periodos'][k] = r
            d['fuentes'].append({'archivo': f, 'sha1': h, 'periodo': k, 'procesado': AHORA}); print('  ->', k, r['trabajadores_confirmados'], r['liquido_totales']); NOVEDADES.append(f'TC1 {etiqueta(k)}')
    except SinTiempo:
        PENDIENTE.append('TC1')
    d['periodos'] = dict(sorted(d['periodos'].items()))
    guardar(p, d)
    csv_out(os.path.join(D01, 'TC1_resumen.csv'), ['periodo', 'trabajadores_confirmados', 'liquido_totales_EUR', 'num_liquidacion', 'lectura', 'archivo'],
            [[k, v['trabajadores_confirmados'], str(v['liquido_totales']).replace('.', ','), v['num_liquidacion'], v['metodo'], v['archivo']] for k, v in d['periodos'].items()])
    return d

# ---------------- REGJOR ----------------
RE_HEAD = re.compile(r'EMPLEADO:\s*([\d.]+)\s*-\s*(.+?)\s+MES\s+(\S+)\s+A[ÑN]O\s+(\d{4})')
RE_TOT = re.compile(r'FEST\.\s+[\d.]+\s+TOTAL\s+([\d.]+)')
def dias_codigo(t, cod):
    a = len(re.findall(r'\*' + cod + r'\b', t)); b = len(re.findall(r'\*' + cod + r'\s*-\s*', t)); return max(0, a - b)

def procesar_regjor(pdf):
    """{ 'YYYY-MM': {numEmpleado: {...}} } con las mismas reglas que importarJornada()."""
    res = {}
    for t in paginas_texto(pdf):
        m = RE_HEAD.search(t)
        if not m: continue
        num_emp = m.group(1).replace('.', ''); nombre = m.group(2).strip()
        try: mes = MESES.index(m.group(3).upper()) + 1
        except ValueError: continue
        k = f'{m.group(4)}-{mes:02d}'
        mt = RE_TOT.search(t); tot = mt.group(1) if mt else None
        IF, IA = dias_codigo(t, 'IF'), dias_codigo(t, 'IA')
        dm = res.setdefault(k, {}); prev = dm.get(num_emp)
        if not prev or (prev['total'] is None and tot is not None):
            dm[num_emp] = {'nombre': nombre, 'total': tot, 'bajaIF': IF, 'bajaIA': IA}
        else:
            prev['bajaIF'] = max(prev['bajaIF'], IF); prev['bajaIA'] = max(prev['bajaIA'], IA)
    return res

def actualizar_regjor():
    p = os.path.join(D02, 'REGJOR_consolidado.json')
    d = cargar(p, {'tipo': 'regjor_consolidado', 'version': 1, 'meses': {}, 'fuentes': []})
    vistos = {f['sha1'] for f in d['fuentes']}
    cand = []
    for f in os.listdir(D02):
        if not (f.upper().startswith('REGJOR') and f.lower().endswith('.pdf')): continue   # INFORME_* son informes derivados
        fp = os.path.join(D02, f); h = sha1(fp)
        if h not in vistos: cand.append((os.path.getsize(fp), f, fp, h))
    try:
        for _, f, fp, h in sorted(cand, reverse=True):     # primero los grandes (mes completo)
            comprobar_tiempo(); print('REGJOR leyendo', f, flush=True)
            r = procesar_regjor(fp)
            if not r: print('  !! sin datos de jornada:', f); d['fuentes'].append({'archivo': f, 'sha1': h, 'error': True}); continue
            mt = os.path.getmtime(fp)
            for k, trab in r.items():
                completo = len(trab) >= 100
                ex = d['meses'].get(k)
                if completo and (not ex or not ex.get('completo') or mt > ex.get('mtime', 0)):
                    parcial = ex['trabajadores'] if ex and not ex.get('completo') else {}
                    d['meses'][k] = {'etiqueta': etiqueta(k), 'completo': True, 'archivo': f, 'sha1': h, 'mtime': mt, 'trabajadores': dict(trab)}
                elif completo:
                    print('  mes', k, 'ya tenía un registro completo más reciente; se conserva')
                else:
                    ex = d['meses'].setdefault(k, {'etiqueta': etiqueta(k), 'completo': False, 'archivo': 'varios (individuales)', 'trabajadores': {}})
                    if ex.get('completo'): continue     # el registro completo del mes manda; los individuales solo rellenan meses sin registro completo
                    for n, v in trab.items():
                        if n not in ex['trabajadores'] or (ex['trabajadores'][n]['total'] is None and v['total'] is not None):
                            ex['trabajadores'][n] = v
                print(f'  -> {k}: {len(trab)} trabajadores ({"completo" if completo else "individual"})')
                if completo: NOVEDADES.append(f'REGJOR {etiqueta(k)} ({len(trab)} trabajadores)')
            d['fuentes'].append({'archivo': f, 'sha1': h, 'meses': sorted(r), 'procesado': AHORA})
    except SinTiempo:
        PENDIENTE.append('REGJOR')
    d['meses'] = dict(sorted(d['meses'].items()))
    guardar(p, d)
    csv_out(os.path.join(D02, 'REGJOR_resumen.csv'), ['mes', 'registro', 'trabajadores', 'con_horas', 'sin_horas', 'con_baja_IF', 'con_baja_IA', 'archivo'],
            [[k, 'completo' if v['completo'] else 'parcial', len(v['trabajadores']),
              sum(1 for x in v['trabajadores'].values() if x['total'] is not None), sum(1 for x in v['trabajadores'].values() if x['total'] is None),
              sum(1 for x in v['trabajadores'].values() if x['bajaIF']), sum(1 for x in v['trabajadores'].values() if x['bajaIA']), v['archivo']]
             for k, v in d['meses'].items()])
    return d

# ---------------- REGJOR DETALLE (día a día) ----------------
DETALLE_DESDE = os.environ.get('DETALLE_DESDE', '2023-01')
DETALLE_JS = os.environ.get('DETALLE_JS', os.path.join(AQUI, 'regjor_detalle.js'))

def r2(x): return round(x + 1e-9, 2)

def procesar_detalle(pdf):
    """Detalle completo del REGJOR de un mes: {'YYYY-MM': {numEmpleado: ficha}} + leyenda de códigos."""
    r = subprocess.run(['node', DETALLE_JS, pdf], capture_output=True, text=True)
    por, ley = {}, {}
    for l in r.stdout.splitlines():
        if not l.startswith('{"p"'): continue
        d = json.loads(l)['d']
        if not d or d.get('error') or 'bloques' not in d: continue
        try: mes = MESES.index(d['mes'].upper()) + 1
        except ValueError: continue
        k = f"{d['anio']}-{mes:02d}"
        f = por.setdefault(k, {}).setdefault(d['emp'], {'n': d['nombre'], 'r': d.get('resp', ''), 'sem': d.get('sem', ''), 'h': None, 'res': {}, 's': [], 'i': {}, 'pag': 0})
        f['pag'] += 1
        if d.get('resp') and not f['r']: f['r'] = d['resp']
        if d.get('horas'):
            f['h'] = d['horas'] if f['h'] is None else [r2(a + b) for a, b in zip(f['h'], d['horas'])]
        for kk, v in (d.get('resumen') or {}).items(): f['res'][kk] = r2(f['res'].get(kk, 0) + v)
        for b in d['bloques']:
            for dia, cod in (b.get('incid') or {}).items(): f['i'][dia] = cod
            if b['cliente'].startswith('999999') and not b['turnos']: continue
            s = {'c': b['cliente'], 'sv': b['servicio'], 'd': b['deleg'], 'h': b['horas'], 't': b['turnos']}
            f['s'].append(s)
        ley.update(d.get('ley') or {})
    # cierre de fichas: total y comprobación de coherencia
    for k, emp in por.items():
        for e, f in emp.items():
            h = f['h'] or []
            f['t'] = r2(sum(h))
            tot_res = f['res'].get('total')
            hs = r2(sum((s['h'] or 0) for s in f['s'] if not s['c'].startswith('999999')))
            f['ck'] = int((tot_res is None or abs(tot_res - f['t']) < 0.6) and abs(hs - f['t']) < 0.6)   # 0,6 h: redondeos de la rejilla
            if not f['s'] and not f['i'] and not h: f.pop('h')
            if not f['res']: f.pop('res')
            if not f['i']: f.pop('i')
    return por, ley


def _firma(f): return json.dumps([f.get('t'), f.get('i', {}), [(x['c'], x['sv'], x['t']) for x in f['s']]], sort_keys=True)

def moda_individuales(d):
    """Regla: ante fichas repetidas (mensual + individuales), gana la versión más repetida; en empate, la del mensual.
    Las fichas que solo existen en un individual se añaden (todo el detalle cuenta)."""
    vistos = {f['sha1'] for f in d['fuentes']}
    dd = os.path.join(D02, 'Individuales_por_trabajador')
    if not os.path.isdir(dd): return
    for f in sorted(os.listdir(dd)):
        if f.startswith('INFORME') or not f.lower().endswith('.pdf'): continue
        fp = os.path.join(dd, f); h = sha1(fp)
        if h in vistos: continue
        comprobar_tiempo(); print('DETALLE individual', f, flush=True)
        por, ley = procesar_detalle(fp); d['codigos'].update(ley)
        cambios = 0
        for k, emp in por.items():
            if k < DETALLE_DESDE: continue
            mes = d['meses'].setdefault(k, {'etiqueta': etiqueta(k), 'archivo': 'individuales', 'sha1': '', 'trabajadores': {}, 'control': {'fichas': 0, 'incoherentes': 0}})
            for e, fi in emp.items():
                ex = mes['trabajadores'].get(e)
                if ex is None: mes['trabajadores'][e] = fi; fi['veces'] = 1; cambios += 1; continue
                votos = ex.setdefault('votos', {_firma(ex): 1})
                fs = _firma(fi); votos[fs] = votos.get(fs, 0) + 1
                mejor = max(votos.values()); actual = _firma(ex)
                if votos[actual] < mejor and fs in votos and votos[fs] == mejor:
                    votos_ = votos; mes['trabajadores'][e] = fi; fi['votos'] = votos_; cambios += 1
        d['fuentes'].append({'archivo': f, 'sha1': h, 'procesado': AHORA, 'cambios': cambios})
        print('  cambios:', cambios, flush=True)


def total_real(det):
    """El total del consolidado pasa a ser el TOTAL REAL del mes (suma de delegaciones/paginas) del detalle, solo si la ficha cuadra (ck=1)."""
    pc = os.path.join(D02, 'REGJOR_consolidado.json'); c = json.load(open(pc, encoding='utf-8')); n = 0
    for k, m in det['meses'].items():
        cm = c['meses'].get(k, {}).get('trabajadores', {})
        for e, f in m['trabajadores'].items():
            x = cm.get(e)
            if not x or not f.get('ck') or not f.get('h'): continue
            tr = '%.2f' % (f.get('res', {}).get('total') if f.get('res', {}).get('total') is not None else f['t'])
            if x.get('total') != tr: x['total'] = tr; n += 1
    if n: guardar(pc, c)
    print('REGJOR_consolidado: total real aplicado en', n, 'fichas')

def actualizar_regjor_detalle():
    p = os.path.join(D02, 'REGJOR_detalle.json')
    d = cargar(p, {'tipo': 'regjor_detalle', 'version': 1, 'codigos': {}, 'meses': {}, 'fuentes': []})
    cons = json.load(open(os.path.join(D02, 'REGJOR_consolidado.json'), encoding='utf-8'))
    vistos = {f['sha1'] for f in d['fuentes']}
    try:
        for k, v in sorted(cons['meses'].items()):
            if k < DETALLE_DESDE or not v.get('completo') or v['sha1'] in vistos: continue
            comprobar_tiempo(); print('DETALLE leyendo', v['archivo'], flush=True)
            por, ley = procesar_detalle(os.path.join(D02, v['archivo']))
            d['codigos'].update(ley)
            for kk, emp in por.items():
                if kk != k: continue      # cada archivo aporta solo su mes
                mal = sum(1 for f in emp.values() if not f['ck'])
                d['meses'][kk] = {'etiqueta': etiqueta(kk), 'archivo': v['archivo'], 'sha1': v['sha1'], 'trabajadores': emp,
                                  'control': {'fichas': len(emp), 'incoherentes': mal}}
                print(f'  -> {kk}: {len(emp)} fichas, {mal} con descuadre')
                if mal: NOVEDADES.append(f'detalle {etiqueta(kk)}: {mal} ficha(s) con descuadre')
            d['fuentes'].append({'archivo': v['archivo'], 'sha1': v['sha1'], 'procesado': AHORA})
        moda_individuales(d)
    except SinTiempo:
        PENDIENTE.append('DETALLE')
    d['meses'] = dict(sorted(d['meses'].items()))
    d['actualizado'] = AHORA
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, p)
    print(f'REGJOR_detalle.json: {os.path.getsize(p)/1048576:.1f} MB')
    total_real(d)
    return d

# ---------------- TC2 DETALLE (por persona: tramos, días cotizados, bases) ----------------
RE_FILA = re.compile(r'^\s*(\d{12})\s+(\d{2})([0-9XYZ]\d{7}[A-Z])\s+([A-Za-z]{2,6})\b(.*)$')
RE_DESC = re.compile(r'(BASE DE CONTINGENCIAS COMUNES|BASE DE ACCIDENTES DE TRABAJO|BASE DE OTRAS HORAS EXTRAORDINARIAS|COMPENSACION I\.T\. ENFERMEDAD COMUN|COMPENSACION IT POR ACCID\. TRABAJO|TRAMO COTIZACION ADIC\. SOLIDARIDAD)\s+([\d.]*\d,\d{2})')
CLAVES_TC2 = {'BASE DE CONTINGENCIAS COMUNES': 'cc', 'BASE DE ACCIDENTES DE TRABAJO': 'at', 'BASE DE OTRAS HORAS EXTRAORDINARIAS': 'he',
              'COMPENSACION I.T. ENFERMEDAD COMUN': 'itec', 'COMPENSACION IT POR ACCID. TRABAJO': 'itat', 'TRAMO COTIZACION ADIC. SOLIDARIDAD': 'sol'}
def eur(x): return float(x.replace('.', '').replace(',', '.'))

def procesar_tc2_detalle(pdf):
    t = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True).stdout
    hdr = re.search(r'Número de trabajadores\s+(\d+)', t)
    personas, cur, otros = {}, None, {}
    for l in t.splitlines():
        m = RE_FILA.match(l)
        if m:
            dni, caf, resto = m.group(3), m.group(4).upper(), m.group(5)
            pe = personas.setdefault(dni, {'caf': caf, 'tr': []})
            f = re.search(r'(\d{2}-\d{2}-\d{4})\s+(\d{2}-\d{2}-\d{4})', resto)
            dd = re.search(r'\b(\d{1,3})\s*D\b', resto); hh = re.search(r'\b(\d{1,4})\s*H\b', resto)
            cur = {'d': f.group(1) if f else None, 'h': f.group(2) if f else None, 'dias': int(dd.group(1)) if dd else None, 'hor': int(hh.group(1)) if hh else None}
            pe['tr'].append(cur); l = resto
        elif cur is None or not l.strip(): continue
        for d in RE_DESC.finditer(l):
            k = CLAVES_TC2.get(re.sub(r'\s+', ' ', d.group(1)).strip())
            if k: cur[k] = eur(d.group(2))
            else: otros[d.group(1).strip()] = otros.get(d.group(1).strip(), 0) + 1
    return personas, (int(hdr.group(1)) if hdr else None), otros

def actualizar_tc2_detalle():
    p = os.path.join(D01, 'TC2_detalle.json')
    d = cargar(p, {'tipo': 'tc2_detalle', 'version': 1, 'periodos': {}, 'fuentes': []})
    cons = json.load(open(os.path.join(D01, 'TC2_consolidado.json'), encoding='utf-8'))
    vistos = {f['sha1'] for f in d['fuentes']}
    try:
        for k, v in sorted(cons['periodos'].items()):
            if k < DETALLE_DESDE or v['sha1'] in vistos: continue
            if v.get('metodo') != 'texto': print('TC2 detalle: se omite', k, '(escaneado, sin texto fiable)'); continue
            comprobar_tiempo(); print('TC2 DETALLE leyendo', v['archivo'], flush=True)
            try: per, hdr, otros = procesar_tc2_detalle(os.path.join(D01, v['archivo']))
            except FileNotFoundError:
                print('  !! falta pdftotext para el detalle del TC2: instálalo con «brew install poppler» y vuelve a ejecutar')
                aviso = os.path.join(AQUI, '.aviso_poppler')      # se avisa una sola vez, para no repetir la notificación
                if not os.path.exists(aviso):
                    open(aviso, 'w').close(); NOVEDADES.append('falta poppler (pdftotext) para el detalle del TC2: brew install poppler')
                break
            d['periodos'][k] = {'etiqueta': etiqueta(k), 'archivo': v['archivo'], 'sha1': v['sha1'], 'personas': per,
                                'control': {'personas': len(per), 'cabecera': hdr, 'coincide_con_consolidado': len(per) == v['trabajadores'],
                                            'otros_conceptos': otros}}
            print(f'  -> {k}: {len(per)} personas (cabecera {hdr}; consolidado {v["trabajadores"]})' + (f' otros conceptos: {otros}' if otros else ''))
            d['fuentes'].append({'archivo': v['archivo'], 'sha1': v['sha1'], 'procesado': AHORA})
    except SinTiempo:
        PENDIENTE.append('TC2DETALLE')
    d['periodos'] = dict(sorted(d['periodos'].items())); d['actualizado'] = AHORA
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, p); print(f'TC2_detalle.json: {os.path.getsize(p)/1048576:.1f} MB')

def notificar(msg):
    """Notificación de macOS (solo en Mac; en otros sistemas se ignora)."""
    try:
        txt = msg.replace('\\', ' ').replace('"', "'")
        subprocess.run(['osascript', '-e', f'display notification "{txt}" with title "ILUNION consolidados"'], capture_output=True, timeout=20)
    except Exception: pass

def un_solo_proceso():
    """Evita dos ejecuciones a la vez (la tarea programada puede dispararse varias veces seguidas)."""
    if fcntl is None: return None
    f = open(os.path.join(AQUI, '.bloqueo'), 'w')
    try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: print('Ya hay otra actualización en curso; se omite.'); sys.exit(0)
    return f

ETIQUETA_LAUNCHD = 'es.ccoo.ilunion.consolidados'
def ruta_plist():
    return os.path.join(os.path.expanduser('~'), 'Library', 'LaunchAgents', ETIQUETA_LAUNCHD + '.plist')

def instalar_tarea():
    """Programa (launchd) la ejecución de este script con --auto: al cambiar Descargas, cada día a las 9:30 y al iniciar sesión."""
    import plistlib
    py = sys.executable or shutil.which('python3')
    datos = {
        'Label': ETIQUETA_LAUNCHD,
        # Sin «exec»: bash sigue siendo el proceso principal y Python su hijo, así que el permiso de «Acceso total al disco» dado a /bin/bash le sirve a Python.
        'ProgramArguments': ['/bin/bash', '-c', f'cd "{AQUI}" && "{py}" actualizar_consolidados.py --auto'],
        'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
        'WatchPaths': [DESCARGAS],
        'StartCalendarInterval': {'Hour': 9, 'Minute': 30},
        'RunAtLoad': True,
        'ThrottleInterval': 60,
        'StandardOutPath': os.path.join(AQUI, 'actualizacion.log'),
        'StandardErrorPath': os.path.join(AQUI, 'actualizacion.log'),
    }
    pl = ruta_plist(); os.makedirs(os.path.dirname(pl), exist_ok=True)
    with open(pl, 'wb') as f: plistlib.dump(datos, f)
    print('Escrito', pl)
    for prog, ayuda in (('node', 'brew install node'), ('pdftotext', 'brew install poppler')):
        if not shutil.which(prog) and not shutil.which(prog, path='/opt/homebrew/bin:/usr/local/bin'):
            print(f'AVISO: no encuentro {prog} ({ayuda}).')
    if not shutil.which('launchctl'):
        print('No hay launchctl: esto solo funciona en macOS. El archivo de la tarea queda escrito, sin cargar.'); return
    uid = str(os.getuid())
    subprocess.run(['launchctl', 'bootout', f'gui/{uid}', pl], capture_output=True)
    r = subprocess.run(['launchctl', 'bootstrap', f'gui/{uid}', pl], capture_output=True, text=True)
    if r.returncode:
        print('No se ha podido cargar la tarea:', (r.stderr or r.stdout).strip()); return
    print('Instalado. Se ejecuta al iniciar sesión, cada día a las 9:30 y cuando cambia Descargas.')
    print('Para que macOS le deje leer Descargas, /bin/bash necesita «Acceso total al disco» (Ajustes del Sistema › Privacidad y seguridad).')
    print('Registro:', os.path.join(AQUI, 'actualizacion.log'))
    print('Probar ahora:  launchctl kickstart -k gui/%s/%s   y luego:  tail -20 "%s"' % (uid, ETIQUETA_LAUNCHD, os.path.join(AQUI, 'actualizacion.log')))

def desinstalar_tarea():
    pl = ruta_plist()
    if shutil.which('launchctl'):
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', pl], capture_output=True)
    if os.path.exists(pl): os.remove(pl)
    print('Tarea programada eliminada. No se ha borrado ningún dato.')

def principal():
    if '--instalar' in sys.argv: instalar_tarea(); return
    if '--desinstalar' in sys.argv: desinstalar_tarea(); return
    cerrojo = un_solo_proceso() if AUTO else None
    print('==', AHORA, '==' + (' (automático)' if AUTO else ''), flush=True)
    try:
        if AUTO or '--barrer' in sys.argv: barrer()
        solo = [a for a in sys.argv[1:] if not a.startswith('--')]
        if not solo or 'tc2' in solo: actualizar_tc2()
        if not solo or 'tc1' in solo: actualizar_tc1()
        if not solo or 'regjor' in solo: actualizar_regjor()
        if not solo or 'detalle' in solo: actualizar_regjor_detalle()
        if not solo or 'tc2detalle' in solo: actualizar_tc2_detalle()
    except Exception as e:
        print('ERROR:', repr(e)); 
        if AUTO: notificar('Error al actualizar los consolidados: ' + str(e)[:120] + '. Mira actualizacion.log en _herramientas.')
        raise
    print('PENDIENTE (vuelve a ejecutar): ' + ', '.join(PENDIENTE) if PENDIENTE else 'LISTO')
    if AUTO and (NOVEDADES or PENDIENTE):
        notificar('; '.join(NOVEDADES) + ('. Faltan por terminar: ' + ', '.join(PENDIENTE) if PENDIENTE else '') + '. Ya puedes actualizar desde la app.')
    if cerrojo: cerrojo.close()

if __name__ == '__main__':
    principal()
