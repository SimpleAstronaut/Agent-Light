"""Project-local MCP extension: orient this shell to SW's +Y up direction.

Launch without arguments to run the MCP client; --server serves the tool.
Uses the installed SolidWorks MCP runtime; does not alter its configuration.
"""
import asyncio, json, math, shutil, sys, types
from pathlib import Path
import pythoncom, win32com.client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import FastMCP

ROOT=Path(__file__).resolve().parent
TARGET=ROOT/'底壳-RevB.SLDPRT'
FEATURE='RevB_DefaultOrientation_OpeningPlusY'
server=FastMCP('agent-light-solidworks-orientation')

def prop(o,n):
 v=getattr(o,n)
 return v() if isinstance(v,types.MethodType) else v

def document():
 pythoncom.CoInitialize()
 rot=pythoncom.GetRunningObjectTable(); it=rot.EnumRunning(); ctx=pythoncom.CreateBindCtx(0)
 while True:
  rows=it.Next(1)
  if not rows: raise RuntimeError('Open RevB shell was not found in the COM running-object table.')
  name=rows[0].GetDisplayName(ctx,None)
  if name.casefold()==str(TARGET).casefold():
   doc=win32com.client.Dispatch(rot.GetObject(rows[0]).QueryInterface(pythoncom.IID_IDispatch))
   assert str(prop(doc,'GetPathName')).casefold()==str(TARGET).casefold()
   return doc

def inspect(doc):
 bodies=doc.GetBodies2(0,False); assert len(bodies)==1
 return {'path':str(prop(doc,'GetPathName')),
         'bbox_mm':[round(v*1000,6) for v in prop(bodies[0],'GetBodyBox')],
         'volume_mm3':prop(doc,'GetMassProperties')[3]*1e9,
         'face_count':len(prop(bodies[0],'GetFaces'))}

@server.tool()
def inspect_shell_orientation()->dict:
 """Read the guarded RevB shell's native coordinates without modifying it."""
 return inspect(document())

@server.tool()
def orient_shell_opening_plus_y()->dict:
 """Append a native Move/Copy Body feature, keeping source history.

 SW's first Euler rotation parameter yields a global-Z half-turn here;
 verified against all 92 exported vertices, not inferred from the argument name.
 """
 doc=document(); before=inspect(doc)
 if doc.FeatureByName(FEATURE):
  return {'already_oriented':True,'after':before}
 assert before['bbox_mm']==[-22.,-13.,-8.,22.,0.,8.], before
 assert not prop(doc.SketchManager,'ActiveSketch'), 'Exit sketch editing first.'
 checkpoint=ROOT/'底壳-RevB-调整坐标前.SLDPRT'
 if not checkpoint.exists(): shutil.copy2(TARGET,checkpoint)
 body=doc.GetBodies2(0,False)[0]; doc.ClearSelection2(True)
 selection=prop(doc.SelectionManager,'CreateSelectData'); selection.Mark=1
 assert body.Select2(False,selection), 'Could not select shell body with mark 1.'
 feature=doc.FeatureManager.InsertMoveCopyBody2(0.,0.,0.,0.,0.,0.,0.,math.pi,0.,0.,False,1)
 assert feature is not None, 'Move/Copy Body feature creation failed.'
 feature.Name=FEATURE
 assert doc.ForceRebuild3(False), 'Rebuild failed; no save performed.'
 after=inspect(doc)
 assert after['bbox_mm']==[-22.,0.,-8.,22.,13.,8.], after
 assert abs(after['volume_mm3']-before['volume_mm3'])<1e-5
 assert after['face_count']==before['face_count']
 doc.ClearSelection2(True); doc.ShowNamedView2('*Isometric',7); doc.ViewZoomtofit2()
 err=win32com.client.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
 warn=win32com.client.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
 assert doc.Save3(1,err,warn), (err.value,warn.value)
 result={'feature':FEATURE,'api_euler_angles_deg':[180,0,0],
         'actual_rotation_z_deg':180,'opening_direction':'+Y',
         'before':before,'after':after,'checkpoint':str(checkpoint),
         'saved':True,'save_errors':err.value,'save_warnings':warn.value}
 (ROOT/'orientation-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 return result

async def client():
 params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__)),'--server'])
 async with stdio_client(params) as (r,w):
  async with ClientSession(r,w) as session:
   init=await session.initialize(); print('MCP server:',init.serverInfo.name,flush=True)
   listed=await session.list_tools(); print('Tools:',[t.name for t in listed.tools],flush=True)
   for name in ['inspect_shell_orientation','orient_shell_opening_plus_y','inspect_shell_orientation']:
    result=await session.call_tool(name,{})
    print(name,result.model_dump_json(),flush=True)
    assert not result.isError, 'MCP operation failed; inspect reported error.'

if __name__=='__main__':
 if '--server' in sys.argv: server.run(transport='stdio')
 else: asyncio.run(client())
