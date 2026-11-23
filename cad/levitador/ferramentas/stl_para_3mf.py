"""Junta as partes de cada cor num .3mf no formato da Bambu Studio: um objeto com várias
partes, a primeira no filamento 1, a segunda no 2 e assim por diante.

  py stl_para_3mf.py <pasta regua_a1>   -> regua_1.3mf e regua_2.3mf (corpo + números)
  py stl_para_3mf.py --tampa <pasta stl> -> tampa_sensor.3mf (azul + branco + amarelo)"""
import sys, uuid, zipfile, re, struct
from pathlib import Path

VERT = re.compile(r"^\s*vertex\s+(\S+)\s+(\S+)\s+(\S+)")


def _vertices(caminho):
    """Vértices do STL, de 3 em 3 (aceita STL em texto ou binário)."""
    dados = open(caminho, "rb").read()
    if dados[:5] == b"solid" and b"facet" in dados[:400]:
        for linha in dados.decode("ascii", errors="replace").splitlines():
            m = VERT.match(linha)
            if m:
                yield tuple(float(c) for c in m.groups())
    else:
        n = struct.unpack("<I", dados[80:84])[0]
        for i in range(n):
            for k in range(3):
                o = 84 + 50*i + 12 + 12*k
                yield struct.unpack("<3f", dados[o:o + 12])


def ler_stl(caminho):
    tris, verts, idx = [], [], {}
    atual = []
    for v in _vertices(caminho):
        v = tuple(round(c, 5) for c in v)
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
    gerar_partes([("corpo", corpo), ("numeros", marcas)], saida, nome, mesa)


def gerar_partes(lista, saida, nome, mesa=256.0):
    """lista = [(nome da parte, arquivo .stl), ...]; a parte k vai no filamento k+1."""
    partes = [(pnome, *ler_stl(arq), k + 1) for k, (pnome, arq) in enumerate(lista)]
    xs = [v[0] for _, vs, _, _ in partes for v in vs]
    ys = [v[1] for _, vs, _, _ in partes for v in vs]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    sub = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
           f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n')
    ids = []
    for k, (pnome, vs, ts, _) in enumerate(partes):
        oid = 2 * k + 1                      # 1, 3, 5... (o 2 é o objeto pai)
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
    if sys.argv[1] == "--tampa":
        pasta = Path(sys.argv[2])
        gerar_partes([("corpo (azul)", pasta / "tampa_sensor.stl"),
                      ("logo branco", pasta / "tampa_sensor_branco.stl"),
                      ("logo amarelo", pasta / "tampa_sensor_amarelo.stl")],
                     pasta / "tampa_sensor.3mf", "tampa_sensor")
        sys.exit()
    pasta = Path(sys.argv[1])
    for n in (1, 2):
        saida = pasta / f"regua_{n}.3mf"
        print(saida.name)
        gerar(pasta / f"regua_{n}_corpo.stl", pasta / f"regua_{n}_marcas.stl", saida, f"regua_{n}")
