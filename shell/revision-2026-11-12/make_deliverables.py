"""Manufacturing outline, bed-oriented mesh, and CAD-derived previews."""
from pathlib import Path
import struct
from OCP.STEPControl import STEPControl_Reader
from OCP.gp import gp_Trsf
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
import vtkmodules.all as vtk
ROOT=Path(__file__).resolve().parent
def read(n):
 r=STEPControl_Reader(); assert int(r.ReadFile(str(ROOT/n)))==1; r.TransferRoots(); return r.OneShape()
def orient(s):
 t=gp_Trsf(); t.SetValues(1,0,0,0, 0,0,1,0, 0,-1,0,0)
 return BRepBuilderAPI_Transform(s,t,True).Shape()
raw_base=read('底壳-RevB.step')
if (ROOT/'orientation-verification.json').exists():
 t=gp_Trsf(); t.SetValues(-1,0,0,0, 0,-1,0,0, 0,0,1,0)
 raw_base=BRepBuilderAPI_Transform(raw_base,t,True).Shape()
base=orient(raw_base)
BRepMesh_IncrementalMesh(base,0.03,False,0.15,True).Perform()
w=StlAPI_Writer(); w.ASCIIMode=False
# OCCT STL writer uses a legacy Windows filename encoding; write ASCII then rename.
tmp=ROOT/'base-print-tmp.stl'; assert w.Write(base,str(tmp))
tmp.replace(ROOT/'底壳-RevB-平底打印.stl')

# Millimetre DXF, one closed polyline, finished size; fabricator compensates kerf.
pairs=[(0,'SECTION'),(2,'HEADER'),(9,'$ACADVER'),(1,'AC1015'),(9,'$INSUNITS'),(70,4),(0,'ENDSEC'),(0,'SECTION'),(2,'ENTITIES'),(0,'LWPOLYLINE'),(100,'AcDbEntity'),(8,'CUT'),(100,'AcDbPolyline'),(90,4),(70,1)]
for x,y in [(0,0),(44,0),(44,16),(0,16)]: pairs.extend([(10,x),(20,y)])
pairs.extend([(0,'ENDSEC'),(0,'EOF')])
(ROOT/'亚克力顶盖-44x16-切割.dxf').write_text(''.join(f'{a}\n{b}\n' for a,b in pairs),encoding='ascii')

def poly(s):
 BRepMesh_IncrementalMesh(s,0.06,False,0.2,True).Perform()
 points=vtk.vtkPoints(); cells=vtk.vtkCellArray(); e=TopExp_Explorer(s,TopAbs_FACE)
 while e.More():
  f=TopoDS.Face(e.Current()); loc=TopLoc_Location(); tri=BRep_Tool.Triangulation_s(f,loc)
  if tri is not None:
   offset=points.GetNumberOfPoints(); t=loc.Transformation()
   for i in range(1,tri.NbNodes()+1):
    p=tri.Node(i).Transformed(t); points.InsertNextPoint(p.X(),p.Y(),p.Z())
   for i in range(1,tri.NbTriangles()+1):
    a,b,c=tri.Triangle(i).Get()
    if f.Orientation()==TopAbs_REVERSED: b,c=c,b
    cells.InsertNextCell(3)
    for v in (a,b,c): cells.InsertCellPoint(offset+v-1)
  e.Next()
 p=vtk.vtkPolyData(); p.SetPoints(points); p.SetPolys(cells); return p
def actor(p,color,opacity=1):
 m=vtk.vtkPolyDataMapper(); m.SetInputData(p); a=vtk.vtkActor(); a.SetMapper(m); a.GetProperty().SetColor(*color); a.GetProperty().SetOpacity(opacity)
 a.GetProperty().SetEdgeVisibility(False); a.GetProperty().SetAmbient(.3); a.GetProperty().SetDiffuse(.7); return a
def render(name,actors):
 r=vtk.vtkRenderer(); r.SetBackground(.96,.97,.99)
 for a in actors: r.AddActor(a)
 win=vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetSize(1400,900); win.AddRenderer(r)
 cam=r.GetActiveCamera(); cam.SetPosition(-65,-65,80); cam.SetFocalPoint(0,0,6); cam.SetViewUp(0,0,1); cam.ParallelProjectionOn(); r.ResetCamera(); cam.Zoom(1.15)
 win.Render(); img=vtk.vtkWindowToImageFilter(); img.SetInput(win); img.Update(); wr=vtk.vtkPNGWriter(); wr.SetFileName(str(ROOT/'previews'/name)); wr.SetInputConnection(img.GetOutputPort()); wr.Write(); win.Finalize()
p=poly(base)
render('RevB-open.png',[actor(p,(.64,.7,.8))])
pcb=poly(orient(read('PCB-positioned.step')))
render('RevB-PCB.png',[actor(p,(.64,.7,.8)),actor(pcb,(.1,.5,.3))])
print('Created bed-oriented STL, 1:1 DXF and CAD previews.')
