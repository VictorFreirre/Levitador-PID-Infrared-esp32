"""Junta corpo + marcas de cada pedaço da régua num .3mf no formato da Bambu Studio:
um objeto com 2 partes, corpo no filamento 1 e marcas (números) no filamento 2."""
import sys, uuid, zipfile, re
from pathlib import Path

VERT = re.compile(r"^\s*vertex\s+(\S+)\s+(\S+)\s+(\S+)")


def ler_stl(caminho):
    tris, verts, idx = [], [], {}
    atual = []
    for linha in open(caminho, encoding="ascii", errors="replace"):
        m = VERT.match(linha)
        if not m:
            continue
        v = tuple(round(float(c), 5) for c in m.groups())
        if v not in idx:
            idx[v] = len(verts)
            verts.append(v)
        atual.append(idx[v])
        if len(atual) == 3:
            if len(set(atual)) == 3:
                tris.append(tuple(atual))
            atual = []
    return verts, tris


def mesh_xml(oid, nome, verts, tris, dx, dy):
    vs = "\n".join(f'     <vertex x="{x - dx:.5f}" y="{y - dy:.5f}" z="{z:.5f}"/>' for x, y, z in verts)
    ts = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
    return (f'  <object id="{oid}" p:UUID="{uuid.uuid4()}" type="model" name="{nome}">\n'
            f'   <mesh>\n    <vertices>\n{vs}\n    </vertices>\n    <triangles>\n{ts}\n    </triangles>\n   </mesh>\n  </object>\n')


NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')
IDENT = "1 0 0 0 1 0 0 0 1 0 0 0"


def gerar(corpo, marcas, saida, nome, mesa=256.0):
    partes = [("corpo (azul)", *ler_stl(corpo), 1), ("numeros (branco)", *ler_stl(marcas), 2)]
    xs = [v[0] for _, vs, _, _ in partes for v in vs]
    ys = [v[1] for _, vs, _, _ in partes for v in vs]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    sub = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
           f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n')
    ids = []
    for k, (pnome, vs, ts, _) in enumerate(partes):
        oid = 2 * k + 1                      # 1, 3 (o 2 é o objeto pai)
        ids.append(oid)
        sub += mesh_xml(oid, pnome, vs, ts, cx, cy)
    sub += ' </resources>\n <build/>\n</model>\n'

    comps = "\n".join(f'    <component p:path="/3D/Objects/object_1.model" objectid="{i}" '
                      f'p:UUID="{uuid.uuid4()}" transform="{IDENT}"/>' for i in ids)
    principal = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                 f' <metadata name="Application">BambuStudio-02.02.00.85</metadata>\n'
                 f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                 f' <metadata name="Title">{nome}</metadata>\n'
                 f' <resources>\n  <object id="2" p:UUID="{uuid.uuid4()}" type="model">\n   <components>\n'
                 f'{comps}\n   </components>\n  </object>\n </resources>\n'
                 f' <build p:UUID="{uuid.uuid4()}">\n'
                 f'  <item objectid="2" p:UUID="{uuid.uuid4()}" transform="1 0 0 0 1 0 0 0 1 {mesa/2} {mesa/2} 0" printable="1"/>\n'
                 f' </build>\n</model>\n')

    parts_cfg = "".join(
        f'    <part id="{i}" subtype="normal_part">\n'
        f'      <metadata key="name" value="{pnome}"/>\n'
        f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
        f'      <metadata key="extruder" value="{ext}"/>\n'
        f'    </part>\n' for i, (pnome, _, _, ext) in zip(ids, partes))
    config = (f'<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <object id="2">\n'
              f'    <metadata key="name" value="{nome}"/>\n    <metadata key="extruder" value="1"/>\n'
              f'{parts_cfg}  </object>\n'
              f'  <plate>\n    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
              f'    <metadata key="locked" value="false"/>\n    <model_instance>\n'
              f'      <metadata key="object_id" value="2"/>\n      <metadata key="instance_id" value="0"/>\n'
              f'      <metadata key="identify_id" value="100"/>\n    </model_instance>\n  </plate>\n</config>\n')

    content_types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                     ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                     ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                     ' <Default Extension="config" ContentType="text/xml"/>\n'
                     '</Types>\n')
    rel = lambda alvo: ('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                        f' <Relationship Target="{alvo}" Id="rel-1" '
                        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')

    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rel("/3D/3dmodel.model"))
        z.writestr("3D/3dmodel.model", principal)
        z.writestr("3D/_rels/3dmodel.model.rels", rel("/3D/Objects/object_1.model"))
        z.writestr("3D/Objects/object_1.model", sub)
        z.writestr("Metadata/model_settings.config", config)
    for pnome, vs, ts, ext in partes:
        print(f"  {pnome}: {len(vs)} vertices, {len(ts)} triangulos, filamento {ext}")


if __name__ == "__main__":
    pasta = Path(sys.argv[1])
    for n in (1, 2):
        saida = pasta / f"regua_{n}.3mf"
        print(saida.name)
        gerar(pasta / f"regua_{n}_corpo.stl", pasta / f"regua_{n}_marcas.stl", saida, f"regua_{n}")
