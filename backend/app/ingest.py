from pathlib import Path
import pandas as pd
import fitz
from docx import Document

def extract(path:Path):
 ext=path.suffix.lower(); text=""; refs=[]; ocr=False; pages=0
 if ext==".pdf":
  doc=fitz.open(path);pages=len(doc)
  for i,p in enumerate(doc):
   t=p.get_text("text") or ""; text+=f"\n{t}"; refs.append(f"page {i+1}")
 elif ext==".docx":
  d=Document(path); text="\n".join(p.text for p in d.paragraphs)
  text+="\n"+"\n".join(" | ".join(c.text for c in row.cells) for table in d.tables for row in table.rows)
  refs=["document"]
 elif ext in {".xlsx",".xls",".csv"}:
  sheets={"csv":pd.read_csv,".csv":pd.read_csv}.get(ext)
  if sheets: df=sheets(path)
  else: df=pd.concat(pd.read_excel(path,sheet_name=None),ignore_index=False)
  text=df.to_csv(index=True);refs=["table"]
 elif ext in {".txt",".md"}:
  text=path.read_text(errors="ignore");refs=["text"]
 else:
  refs=[]
 return text,refs,ocr,pages
