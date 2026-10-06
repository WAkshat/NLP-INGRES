"""Figures for the mid-term synopsis and PPT (numbers from experiments/)."""
import json
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
R=Path(__file__).resolve().parents[2]; F=R/"reports/midterm/fig"
NAVY="#2E3A59"; ORANGE="#E0703A"; RED="#8B2A2A"; GREY="#8A8F99"
plt.rcParams.update({"font.family":"Times New Roman","font.size":12})

# 1 architecture
fig,ax=plt.subplots(figsize=(12,6.2)); ax.axis("off"); ax.set_xlim(0,12); ax.set_ylim(0,6.2)
def box(x,y,w,h,t,c=NAVY,done=False):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.04",fc=c if done else "white",ec=c,lw=2))
    ax.text(x+w/2,y+h/2,t,ha="center",va="center",fontsize=11,color="white" if done else c,wrap=True)
def arr(x1,y1,x2,y2): ax.annotate("",(x2,y2),(x1,y1),arrowprops=dict(arrowstyle="->",lw=1.6,color=GREY))
ax.text(0.1,5.9,"Data layer (completed)",color=NAVY,fontsize=12,weight="bold")
box(0.1,4.7,2.2,1.0,"INGRES portal\n(public JSON API)",done=True); box(2.8,4.7,2.2,1.0,"Crawler + audit\n(5,299 requests)",done=True)
box(5.5,4.7,2.4,1.0,"Cross-year crosswalk\n+ canonical SQLite DB",done=True); box(8.4,4.7,3.4,1.0,"INGRES-Bench v1\n1,484 NL-SQL pairs, 4 languages",done=True)
for a,b in ((2.3,2.8),(5.0,5.5),(7.9,8.4)): arr(a,5.2,b,5.2)
ax.text(0.1,3.95,"Query pipeline (in progress)",color=ORANGE,fontsize=12,weight="bold")
steps=["User question\n(En/Hi/Hinglish/Ta)","Language &\ncode-mix analysis","Schema linking\n(learned retriever)","Geographic entity\nresolution","Text-to-SQL\n(LLM / agent)","Read-only SQL\nvalidation + run","Answer +\nnumeric grounding\ncheck"]
for i,s in enumerate(steps):
    box(0.1+i*1.7,2.5,1.5,1.25,s,c=ORANGE)
    if i: arr(0.1+i*1.7-0.2,3.12,0.1+i*1.7,3.12)
box(4.5,0.6,3.2,1.1,"Agent loop for multi-step questions:\ndecompose, sub-queries, self-correct",c=RED)
arr(8.4,2.5,7.7,1.5); arr(4.5,1.2,3.9,2.5)
ax.text(8.2,0.9,"Filled boxes = built and validated\nOutlined = planned",fontsize=10,color=GREY)
fig.tight_layout(); fig.savefig(F/"architecture.png",dpi=200); plt.close()

# 2 Gantt
tasks=[("Data-access audit & ingestion",0,2.3,True),("Canonical DB & schema",1.5,2.8,True),("INGRES-Bench construction & QC",2.3,3.0,True),
("Baselines (keyword, BM25, embeddings, LLM)",3.0,4.0,"part"),("Learned schema linking",3.7,5.0,False),("Geographic entity resolution",4.3,5.5,False),
("Tokenization / code-mixing study",5.0,6.0,False),("Numeric grounding verifier",6.0,7.2,False),("Agentic decomposition",6.8,8.3,False),
("Minimal UI",8.0,8.8,False),("Ablations, error analysis, final report",8.5,10.5,False)]
months=["Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar","Apr","May"]
fig,ax=plt.subplots(figsize=(12,5.2))
for i,(n,s,e,d) in enumerate(tasks):
    c=NAVY if d is True else ORANGE if d=="part" else "#C9CDD6"
    ax.barh(i,e-s,left=s,color=c,edgecolor="white",height=0.6)
ax.set_yticks(range(len(tasks))); ax.set_yticklabels([t[0] for t in tasks]); ax.invert_yaxis()
ax.set_xticks([m+0.5 for m in range(11)]); ax.set_xticklabels([f"{m}\n{'2026' if i<6 else '2027'}" for i,m in enumerate(months)])
ax.set_xlim(0,11); ax.axvline(2.93,color=RED,ls="--",lw=1.5); ax.text(3.0,0.6,"Mid-term (Sep 2026)",color=RED,fontsize=10)
ax.axvline(6,color=GREY,lw=1); ax.text(6.05,10.45,"Project-II",color=GREY,fontsize=10); ax.text(0.05,10.45,"Project-I",color=GREY,fontsize=10)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=NAVY,label="Completed"),Patch(color=ORANGE,label="In progress"),Patch(color="#C9CDD6",label="Planned")],loc="upper right",fontsize=10)
ax.grid(axis="x",alpha=.3); fig.tight_layout(); fig.savefig(F/"gantt.png",dpi=200); plt.close()

# 3 results: schema linking R@3 by language, baseline A EX by language
sl=json.load(open(R/"experiments/schema_linking/baselines.json"))["results"]
A=json.load(open(R/"experiments/baselines/A_keyword_template/metrics.json",encoding="utf8"))
langs=["english","hindi","hinglish","tamil"]; lab=["English","Hindi","Hinglish","Tamil"]
fig,axs=plt.subplots(1,2,figsize=(12,4.4))
w=.26
for j,(m,c,n) in enumerate((("random (no linking)",GREY,"Random"),("B_bm25",ORANGE,"BM25"),("C_multilingual_e5_small",NAVY,"mE5-small"))):
    v=[sl[m]["column"]["by_language"][l]["R@3"] for l in langs]; axs[0].bar([i+(j-1)*w for i in range(4)],v,w,color=c,label=n)
axs[0].set_xticks(range(4)); axs[0].set_xticklabels(lab); axs[0].set_ylabel("Column Recall@3"); axs[0].set_title("Schema linking baselines (B, C)"); axs[0].legend(fontsize=10); axs[0].set_ylim(0,.75)
ex={r["language"]:r for r in A["breakdowns"]["language"]}
axs[1].bar(lab,[ex[l]["correct"] for l in langs],color=[NAVY,ORANGE,RED,GREY])
axs[1].errorbar(range(4),[ex[l]["correct"] for l in langs],yerr=[[ex[l]["correct"]-ex[l]["ci95_lo"] for l in langs],[ex[l]["ci95_hi"]-ex[l]["correct"] for l in langs]],fmt="none",ecolor="black",capsize=4)
axs[1].set_ylabel("Execution accuracy"); axs[1].set_title("Baseline A (keyword/template) EX, 95% CI"); axs[1].set_ylim(0,.75)
fig.tight_layout(); fig.savefig(F/"baseline_results.png",dpi=200); plt.close()
print("ok")
