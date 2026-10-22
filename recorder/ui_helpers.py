"""Small reusable, scrollable Tk controls for high-DPI operator workspaces."""
import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


def details(parent,title,data):
    window=tk.Toplevel(parent);window.title(title)
    window.geometry(f'{min(1000,window.winfo_screenwidth()-80)}x{min(700,window.winfo_screenheight()-100)}')
    window.minsize(420,280)
    text=ScrolledText(window,wrap='word',font=('Consolas',10));text.pack(fill='both',expand=True,padx=8,pady=8)
    text.insert('1.0',data if isinstance(data,str) else json.dumps(data,indent=2));text.configure(state='disabled')
    ttk.Button(window,text='Close',command=window.destroy).pack(pady=6)
    return window


def scroll_page(parent):
    outer=ttk.Frame(parent);canvas=tk.Canvas(outer,highlightthickness=0);bar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set);canvas.pack(side='left',fill='both',expand=True);bar.pack(side='right',fill='y')
    body=ttk.Frame(canvas,padding=12);item=canvas.create_window(0,0,window=body,anchor='nw')
    body.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    return outer,body


def table(parent,columns,height=5,selectmode='browse'):
    frame=ttk.Frame(parent);tree=ttk.Treeview(frame,columns=columns,show='headings',height=height,selectmode=selectmode)
    y=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);x=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
    tree.configure(yscrollcommand=y.set,xscrollcommand=x.set);tree.grid(row=0,column=0,sticky='nsew');y.grid(row=0,column=1,sticky='ns');x.grid(row=1,column=0,sticky='ew')
    frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
    for col in columns:tree.heading(col,text=col);tree.column(col,width=110,minwidth=70)
    return frame,tree
