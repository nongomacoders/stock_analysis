import json
import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP,X,BOTH,LEFT,RIGHT,Y,END
from modules.data.research_comparisons import list_comparisons,list_learning_points,analyst_checklist

class LearningTab(ttk.Frame):
 def __init__(self,parent,ticker,async_run_bg):
  super().__init__(parent); self.ticker=ticker; self.async_run_bg=async_run_bg; self.comparisons={}; self._build()
 def _build(self):
  bar=ttk.Frame(self,padding=8); bar.pack(fill=X)
  ttk.Label(bar,text="Research Review & Learning",font=("Segoe UI",14,"bold")).pack(side=LEFT)
  ttk.Button(bar,text="Refresh",bootstyle="secondary",command=self.refresh).pack(side=RIGHT)
  pane=ttk.Panedwindow(self,orient="horizontal"); pane.pack(fill=BOTH,expand=True,padx=8,pady=(0,8))
  left=ttk.Frame(pane); right=ttk.Frame(pane); pane.add(left,weight=2); pane.add(right,weight=3)
  self.tree=ttk.Treeview(left,columns=("date","type","status","previous","current"),show="headings",height=12)
  for col,label,width in (("date","Created",130),("type","Review type",145),("status","Status",85),("previous","Previous",100),("current","Current",100)):
   self.tree.heading(col,text=label); self.tree.column(col,width=width,stretch=col in {"previous","current"})
  sy=ttk.Scrollbar(left,orient="vertical",command=self.tree.yview); self.tree.configure(yscrollcommand=sy.set)
  self.tree.pack(side=LEFT,fill=BOTH,expand=True); sy.pack(side=RIGHT,fill=Y); self.tree.bind("<<TreeviewSelect>>",self._selected)
  self.detail=ttk.Text(right,wrap="word",font=("Segoe UI",10)); ds=ttk.Scrollbar(right,orient="vertical",command=self.detail.yview); self.detail.configure(yscrollcommand=ds.set)
  self.detail.pack(side=LEFT,fill=BOTH,expand=True); ds.pack(side=RIGHT,fill=Y)
 def update_ticker(self,ticker): self.ticker=ticker; self.refresh()
 def refresh(self):
  ticker=self.ticker
  async def load():
   return await list_comparisons(ticker),await list_learning_points(ticker),await analyst_checklist(ticker)
  def loaded(data):
   if self.ticker!=ticker:return
   comparisons,points,checklist=data; self.tree.delete(*self.tree.get_children()); self.comparisons={}
   for c in comparisons:
    iid=self.tree.insert("",END,values=(str(c["created_at"])[:16],self._type_label(c.get("comparison_type")),c["status"],str(c["previous_report_id"])[:8],str(c["current_report_id"])[:8])); self.comparisons[iid]=c
   lines=["ANALYST CHECKLIST",""]
   lines += [f"[ ] {x['area']} ({x['category']}, {x['severity']}, recurrence {x['recurrence_count']})\n    {x['action']}" for x in checklist] or ["No open learning points."]
   lines += ["","OPEN / HISTORICAL LEARNING POINTS",""]
   for p in points: lines.append(f"{p['category']} | {p['scope']} | {p['severity']} | {p['status']}\n{p['area']}: {p['finding']}\nAction: {p['recommended_action']}\n")
   self._show("\n".join(lines))
  self.async_run_bg(load(),callback=loaded)
 def _selected(self,event=None):
  selection=self.tree.selection()
  if not selection:return
  c=self.comparisons.get(selection[0]);
  if not c:return
  review=c.get("qualitative_review_json"); deterministic=c.get("deterministic_summary_json")
  if isinstance(review,str): review=json.loads(review)
  if isinstance(deterministic,str): deterministic=json.loads(deterministic)
  self._show(self._type_label(c.get("comparison_type"))+"\n\nOVERALL SUMMARY\n\n"+(c.get("overall_summary") or c.get("error_message") or "No summary")+"\n\nDETERMINISTIC COMPARISON\n\n"+json.dumps(deterministic,indent=2,default=str)+"\n\nQUALITATIVE REVIEW\n\n"+json.dumps(review,indent=2,default=str))
 def _type_label(self,value):
  return {"SAME_PERIOD_REVISION":"Same-period revision | Research quality / evidence revision","NEW_REPORTING_PERIOD":"New reporting period | Outcome / forecast review","MANUAL_OTHER":"Manual / unresolved period review"}.get(value,value or "Legacy comparison")
 def _show(self,text):
  self.detail.config(state="normal"); self.detail.delete("1.0",END); self.detail.insert("1.0",text); self.detail.config(state="disabled")
