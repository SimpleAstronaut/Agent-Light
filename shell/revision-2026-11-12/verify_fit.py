"""Read-back CAD verification. Units: mm. Requires cadquery-ocp."""
import json, hashlib
from pathlib import Path
from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.gp import gp_Trsf, gp_Vec, gp_Pnt
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepCheck import BRepCheck_Analyzer

ROOT=Path(__file__).resolve().parent
def read(p):
    r=STEPControl_Reader(); assert int(r.ReadFile(str(p)))==1; r.TransferRoots(); return r.OneShape()
def write(s,p):
    w=STEPControl_Writer(); w.Transfer(s,STEPControl_AsIs); assert int(w.Write(str(p)))==1
def bbox(s):
    b=Bnd_Box(); BRepBndLib.AddOptimal_s(s,b); a=b.CornerMin(); c=b.CornerMax()
    return [a.X(),a.Y(),a.Z(),c.X(),c.Y(),c.Z()]
def solids(s):
    e=TopExp_Explorer(s,TopAbs_SOLID); out=[]
    while e.More(): out.append(e.Current()); e.Next()
    return out
def compound(shapes):
    c=TopoDS_Compound(); b=BRep_Builder(); b.MakeCompound(c)
    for s in shapes: b.Add(c,s)
    return c
def moved(s,t): return BRepBuilderAPI_Transform(s,t,True).Shape()
def volume(s):
    p=GProp_GProps(); BRepGProp.VolumeProperties_s(s,p); return abs(p.Mass())
def common(a,b): return volume(BRepAlgoAPI_Common(a,b).Shape())

shell=read(ROOT/'底壳-RevB.step')
native_bbox=bbox(shell)
# Native model now opens along +Y. Keep the historical checking assembly frame.
if native_bbox[4]>12 and native_bbox[1]>-1e-5:
    normalize=gp_Trsf(); normalize.SetValues(-1,0,0,0, 0,-1,0,0, 0,0,1,0)
    shell=moved(shell,normalize)
old=read(ROOT/'原底壳-对照.step')
pcb=read(ROOT/'3D_PCB1_2026-11-11.step')
# Right-handed mapping: shell X = board Y-20; shell Y = -board Z-6.6;
# shell Z = 6-board X. PCB underside seats at Y=-6.6.
t=gp_Trsf(); t.SetValues(0,1,0,-20, 0,0,-1,-6.6, -1,0,0,6)
pcb=moved(pcb,t)
write(pcb,ROOT/'PCB-positioned.step')
lid=read(ROOT/'亚克力顶盖-44x16x2.step')
lt=gp_Trsf(); lt.SetTranslation(gp_Vec(0,-15.15,0)); lid=moved(lid,lt)
write(compound([shell,pcb,lid]),ROOT/'装配检查-RevB.step')
write(compound([shell,pcb]),ROOT/'开盖装配检查-RevB.step')

# Swept axis-aligned boxes over the entire 20 mm vertical insertion path.
# This is conservative: passing proves clearance even for rectangular component envelopes.
boxes=[]
for s in solids(pcb):
    a,b,c,d,e,f=bbox(s)
    if min(d-a,e-b,f-c)>1e-6:
        boxes.append(BRepPrimAPI_MakeBox(gp_Pnt(a,b-20,c),d-a,e-b+20,f-c).Shape())
print('Checking conservative insertion envelopes...',flush=True)
old_path=sum(common(old,b) for b in boxes); new_path=sum(common(shell,b) for b in boxes)
new_static=common(shell,pcb); old_static=common(old,pcb)
report={
 'units':'mm', 'pcb_to_shell_transform':[[0,1,0,-20],[0,0,-1,-6.6],[-1,0,0,6]],
 'shell_bbox':bbox(shell), 'native_shell_bbox':native_bbox,
 'assembly_frame':'Historical -Y opening frame; native SLDPRT/STEP now opens +Y.',
 'shell_solid_count':len(solids(shell)),
 'shell_valid':BRepCheck_Analyzer(shell).IsValid(),
 'lid_bbox_assembled':bbox(lid), 'pcb_bbox_assembled':bbox(pcb),
 'old_static_interference_mm3':old_static, 'new_static_interference_mm3':new_static,
 'old_vertical_path_envelope_overlap_sum_mm3':old_path,
 'new_vertical_path_envelope_overlap_sum_mm3':new_path,
 'lid_pcb_interference_mm3':common(lid,pcb),
 'original_files_unchanged':{},
 'limits':['STEP excludes hand-solder fillets and real print tolerances.',
           'Vertical path uses conservative component boxes; zero volume means touching allowed.',
           'Cable overmold dimensions not supplied; confirm plug access on prototype.',
           'Nominal glue gap 0.15 mm; no retention force or thermal test performed.']}
for n in ['零件1.SLDPRT','顶盖.SLDPRT','shell.SLDASM','零件1.STEP','3D_PCB1_2026-11-11.step']:
    h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report['original_files_unchanged'][n]=h(ROOT/n)==h(ROOT.parent/n)
(ROOT/'fit-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
assert report['shell_valid'] and report['shell_solid_count']==1
assert new_static<1e-5 and new_path<1e-5
assert all(report['original_files_unchanged'].values())
