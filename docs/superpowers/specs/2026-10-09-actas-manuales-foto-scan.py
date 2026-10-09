import re, html, json, time, urllib.request, sys
menu = open('menu2526.html', encoding='utf-8', errors='replace').read()
cat = None; groups = []
for m in re.finditer(r'class="category">([^<]+)<|clasificaciones\?id=(\d+)[^>]*>(.*?)</a>', menu, re.S):
    if m.group(1): cat = html.unescape(m.group(1).strip()); continue
    if cat and re.search(r'(?i)alev|infant', cat):
        groups.append((m.group(2), cat, re.sub(r'<[^>]+>|\s+', ' ', html.unescape(m.group(3))).strip()))
import subprocess
def get(url):
    for _ in range(3):
        r = subprocess.run(['curl','-s','-m','30',url],capture_output=True)
        if r.returncode == 0 and r.stdout: return r.stdout.decode('utf-8','replace')
        time.sleep(2)
    return ''
rows = []
for gid, cat, phase in groups:
    seen_rounds = set()
    for jor in range(1, 31):
        h = get(f'https://www.voleibolib.net/JSON/get_resultados.asp?id={gid}&jor={jor}')
        hd = re.search(r'<h3>JORNADA (\d+)', h)
        if not hd or int(hd.group(1)) != jor: break
        for b in h.split("class='info_partido")[1:]:
            teams = re.findall(r"class='nombreEquipo'>([^<]*)<", b)
            score = re.search(r"class='marcador'>([^<]*)<", b)
            parc = re.search(r"id='finalizado'><span class='marcador'>([^<]*)<", b)
            acta = re.search(r"href='([^']+)'[^>]*title='Ver Acta'", b)
            foto = re.search(r"href='([^']+)'[^>]*title='Ver Foto Acta'", b)
            other = re.findall(r"title='([^']+)'><i class='fa", b)
            date = re.search(r"class='fecha'>([^<]*)<", b)
            rows.append(dict(gid=gid, cat=cat, phase=phase, jor=jor, teams=teams, score=score and score.group(1),
                             parciales=parc and parc.group(1), acta=acta and acta.group(1), foto=foto and foto.group(1),
                             icons=other, fecha=date and date.group(1), raw=re.sub(r'\s+', ' ', b[-700:])))
        time.sleep(0.25)
    print(gid, cat, phase, len(rows), flush=True)
json.dump(rows, open('scan.json', 'w'))
print('DONE', len(rows))
