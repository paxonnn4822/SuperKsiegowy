"""Księgi Czarno-Złote — lokalny, demonstracyjny rejestr księgowy.
To narzędzie pomocnicze; nie jest certyfikowanym systemem FK ani poradą prawną/podatkową.
"""
from __future__ import annotations
import csv
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "Księgi Czarno-Złote"
GOLD = "#C9A227"
BLACK = "#171717"
DARK = "#242424"
PANEL = "#302A1F"
PAPER = "#F4EAD0"
INPUT = "#FFF2CC"
WHITE = "#FFFFFF"
GREEN = "#DDEBD8"
RED = "#F7D9D7"

SAMPLE_ACCOUNTS = [
    ("010", "Środki trwałe", "Bilans"), ("070", "Umorzenie środków trwałych", "Bilans"),
    ("100", "Kasa PLN", "Bilans"), ("130", "Rachunek bankowy PLN", "Bilans"),
    ("201", "Należności od odbiorców", "Bilans"), ("202", "Zobowiązania wobec dostawców", "Bilans"),
    ("221", "VAT naliczony", "Bilans"), ("222", "VAT należny", "Bilans"),
    ("231", "Rozrachunki z tytułu wynagrodzeń", "Bilans"), ("240", "Pozostałe rozrachunki", "Bilans"),
    ("300", "Rozliczenie zakupu", "Bilans"), ("310", "Materiały i towary", "Bilans"),
    ("400", "Amortyzacja", "Wynik"), ("401", "Zużycie materiałów i energii", "Wynik"),
    ("402", "Usługi obce", "Wynik"), ("403", "Podatki i opłaty", "Wynik"),
    ("404", "Wynagrodzenia", "Wynik"), ("405", "Ubezpieczenia społeczne i inne świadczenia", "Wynik"),
    ("409", "Pozostałe koszty rodzajowe", "Wynik"), ("490", "Rozliczenie kosztów", "Bilans"),
    ("700", "Przychody ze sprzedaży produktów", "Wynik"), ("701", "Przychody ze sprzedaży usług", "Wynik"),
    ("730", "Przychody ze sprzedaży towarów", "Wynik"), ("750", "Przychody finansowe", "Wynik"),
    ("751", "Koszty finansowe", "Wynik"), ("760", "Pozostałe przychody operacyjne", "Wynik"),
    ("761", "Pozostałe koszty operacyjne", "Wynik"), ("800", "Kapitał podstawowy", "Bilans"),
    ("820", "Kapitał zapasowy", "Bilans"), ("840", "Rezerwy", "Bilans"),
    ("860", "Wynik finansowy z lat ubiegłych", "Bilans"), ("870", "Podatek dochodowy", "Wynik"),
]


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
        path = base / "KsiegiCzarnoZlote"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ksiegi-czarno-zlote"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Ledger:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.executescript("""
              PRAGMA foreign_keys=ON;
              CREATE TABLE IF NOT EXISTS accounts(code TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'Bilans', active INTEGER NOT NULL DEFAULT 1);
              CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY AUTOINCREMENT, entry_date TEXT NOT NULL, doc_no TEXT NOT NULL, description TEXT NOT NULL, counterparty TEXT DEFAULT '', created_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE, account_code TEXT NOT NULL REFERENCES accounts(code), debit REAL NOT NULL DEFAULT 0, credit REAL NOT NULL DEFAULT 0, cost_center TEXT DEFAULT '');
              CREATE TABLE IF NOT EXISTS company_checks(id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL, nip TEXT NOT NULL, checked_at TEXT NOT NULL, result TEXT NOT NULL, response_json TEXT NOT NULL);
            """)
            if self.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
                self.conn.executemany("INSERT INTO accounts(code,name,kind) VALUES(?,?,?)", SAMPLE_ACCOUNTS)

    def accounts(self):
        return self.conn.execute("SELECT code,name,kind FROM accounts WHERE active=1 ORDER BY code").fetchall()

    @staticmethod
    def validate_lines(lines):
        if len(lines) < 2:
            raise ValueError("Dekret musi mieć co najmniej dwa zapisy.")
        debit = credit = 0.0
        for code, dr, cr, _cost_center in lines:
            if not code:
                raise ValueError("Każdy zapis musi mieć wybrane konto.")
            dr, cr = float(dr or 0), float(cr or 0)
            if dr < 0 or cr < 0 or (dr and cr):
                raise ValueError("Kwoty nie mogą być ujemne; pojedynczy wiersz zawiera WN albo MA.")
            if not dr and not cr:
                raise ValueError("Każdy wiersz musi mieć kwotę WN lub MA.")
            debit += dr
            credit += cr
        if round(debit, 2) != round(credit, 2):
            raise ValueError(f"Dekret niezbilansowany: WN {debit:.2f} PLN, MA {credit:.2f} PLN.")
        return round(debit, 2), round(credit, 2)

    def add_entry(self, entry_date, doc_no, description, counterparty, lines):
        datetime.strptime(entry_date, "%Y-%m-%d")
        if not doc_no.strip() or not description.strip():
            raise ValueError("Numer dowodu i opis operacji są wymagane.")
        self.validate_lines(lines)
        with self.conn:
            cur = self.conn.execute("INSERT INTO entries(entry_date,doc_no,description,counterparty,created_at) VALUES(?,?,?,?,?)", (entry_date, doc_no.strip(), description.strip(), counterparty.strip(), datetime.now().isoformat(timespec="seconds")))
            eid = cur.lastrowid
            self.conn.executemany("INSERT INTO lines(entry_id,account_code,debit,credit,cost_center) VALUES(?,?,?,?,?)", [(eid, c, float(d or 0), float(cr or 0), cc) for c,d,cr,cc in lines])
        return eid

    def entries(self):
        return self.conn.execute("""SELECT e.id,e.entry_date,e.doc_no,e.description,e.counterparty,COUNT(l.id) line_count,ROUND(SUM(l.debit),2) debit,ROUND(SUM(l.credit),2) credit
          FROM entries e JOIN lines l ON l.entry_id=e.id GROUP BY e.id ORDER BY e.entry_date DESC,e.id DESC""").fetchall()

    def trial_balance(self, through: str | None = None):
        sql = """SELECT a.code,a.name,COALESCE(SUM(l.debit),0) debit,COALESCE(SUM(l.credit),0) credit,
                 MAX(COALESCE(SUM(l.debit),0)-COALESCE(SUM(l.credit),0),0) debit_balance,
                 MAX(COALESCE(SUM(l.credit),0)-COALESCE(SUM(l.debit),0),0) credit_balance
                 FROM accounts a LEFT JOIN lines l ON l.account_code=a.code LEFT JOIN entries e ON e.id=l.entry_id"""
        args=[]
        if through:
            sql += " AND e.entry_date<=?";args.append(through)
        sql += " WHERE a.active=1 GROUP BY a.code,a.name ORDER BY a.code"
        return self.conn.execute(sql,args).fetchall()

    def profit_loss(self, start: str, end: str):
        return self.conn.execute("""SELECT a.code,a.name,SUM(l.debit) debit,SUM(l.credit) credit
          FROM accounts a JOIN lines l ON l.account_code=a.code JOIN entries e ON e.id=l.entry_id
          WHERE a.kind='Wynik' AND e.entry_date BETWEEN ? AND ? GROUP BY a.code,a.name ORDER BY a.code""",(start,end)).fetchall()

    def company_check(self, brand: str, nip: str, check_date: str):
        digits = ''.join(ch for ch in nip if ch.isdigit())
        if len(digits) != 10 or not nip_checksum_valid(digits):
            raise ValueError("NIP musi zawierać 10 cyfr i przejść kontrolę sumy kontrolnej.")
        datetime.strptime(check_date, "%Y-%m-%d")
        url = f"https://wl-api.mf.gov.pl/api/search/nip/{digits}?date={urllib.parse.quote(check_date)}"
        req = urllib.request.Request(url,headers={"User-Agent":f"{APP_NAME}/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                payload=json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Nie udało się pobrać odpowiedzi z wykazu VAT MF: {exc}") from exc
        item=payload.get("result",{}).get("subject") or {}
        result={"nip":digits,"date":check_date,"requestId":payload.get("result",{}).get("requestId"),"name":item.get("name"),"statusVat":item.get("statusVat"),"regon":item.get("regon"),"krs":item.get("krs"),"residenceAddress":item.get("residenceAddress"),"workingAddress":item.get("workingAddress"),"accountNumbers":item.get("accountNumbers",[]),"raw":payload}
        self.conn.execute("INSERT INTO company_checks(brand,nip,checked_at,result,response_json) VALUES(?,?,?,?,?)", (brand,digits,datetime.now().isoformat(timespec="seconds"),result.get("statusVat") or "brak statusu",json.dumps(result,ensure_ascii=False)))
        self.conn.commit()
        return result

    def close(self):
        self.conn.close()


def nip_checksum_valid(nip: str) -> bool:
    weights=(6,5,7,2,3,4,5,6,7)
    return len(nip) == 10 and nip.isdigit() and len(set(nip)) > 1 and sum(int(nip[i])*weights[i] for i in range(9))%11 == int(nip[9])


class App(tk.Tk):
    def __init__(self, db_path: str | Path | None = None):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1200x790")
        self.minsize(1000,650)
        self.configure(bg=BLACK)
        self.db_path=Path(db_path) if db_path else app_data_dir()/"księgi.sqlite3"
        self.ledger=Ledger(self.db_path)
        self._configure_style()
        self._build_ui()
        self.refresh_all()

    def _configure_style(self):
        st=ttk.Style(self)
        try: st.theme_use("clam")
        except tk.TclError: pass
        st.configure("TFrame",background=BLACK)
        st.configure("Panel.TFrame",background=PANEL)
        st.configure("TLabel",background=BLACK,foreground=WHITE,font=("Segoe UI",10))
        st.configure("Title.TLabel",background=BLACK,foreground=GOLD,font=("Segoe UI",19,"bold"))
        st.configure("Gold.TLabel",background=PANEL,foreground=GOLD,font=("Segoe UI",10,"bold"))
        st.configure("TButton",font=("Segoe UI",10),padding=7)
        st.configure("Gold.TButton",background=GOLD,foreground=BLACK,font=("Segoe UI",10,"bold"),padding=8)
        st.map("Gold.TButton",background=[("active","#E0B835")])
        st.configure("TNotebook",background=BLACK,borderwidth=0)
        st.configure("TNotebook.Tab",background=DARK,foreground=WHITE,padding=(14,9),font=("Segoe UI",10,"bold"))
        st.map("TNotebook.Tab",background=[("selected",GOLD)],foreground=[("selected",BLACK)])
        st.configure("Treeview",background="#222222",fieldbackground="#222222",foreground=WHITE,rowheight=27,font=("Segoe UI",9))
        st.configure("Treeview.Heading",background=GOLD,foreground=BLACK,font=("Segoe UI",9,"bold"))
        st.map("Treeview",background=[("selected", "#66531C")])
        st.configure("TEntry",fieldbackground=INPUT,foreground=BLACK)
        st.configure("TCombobox",fieldbackground=INPUT,foreground=BLACK)

    def _build_ui(self):
        top=ttk.Frame(self,padding=(18,12));top.pack(fill="x")
        ttk.Label(top,text="KSIĘGI CZARNO-ZŁOTE",style="Title.TLabel").pack(side="left")
        ttk.Label(top,text="lokalny rejestr księgowy • PLN",foreground="#D7D0C2").pack(side="right")
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill="both",expand=True,padx=12,pady=(0,12))
        self.dashboard=ttk.Frame(self.tabs,padding=16);self.tabs.add(self.dashboard,text="Dashboard")
        self.journal=ttk.Frame(self.tabs,padding=16);self.tabs.add(self.journal,text="Księgowanie")
        self.book=ttk.Frame(self.tabs,padding=16);self.tabs.add(self.book,text="Dziennik")
        self.accounts_tab=ttk.Frame(self.tabs,padding=16);self.tabs.add(self.accounts_tab,text="Plan kont")
        self.tb_tab=ttk.Frame(self.tabs,padding=16);self.tabs.add(self.tb_tab,text="Obroty i salda")
        self.pl_tab=ttk.Frame(self.tabs,padding=16);self.tabs.add(self.pl_tab,text="Rachunek wyników")
        self.bs_tab=ttk.Frame(self.tabs,padding=16);self.tabs.add(self.bs_tab,text="Bilans")
        self.company_tabs=ttk.Notebook(self.tabs);self.tabs.add(self.company_tabs,text="Weryfikacja firm")
        self._build_dashboard();self._build_journal();self._build_book();self._build_accounts();self._build_reports()
        self._build_company_tab("Deloitte","Deloitte")
        self._build_company_tab("PwC","PwC")
        footer=ttk.Frame(self,padding=(12,0,12,8));footer.pack(fill="x")
        ttk.Label(footer,text=f"Baza lokalna: {self.db_path}",foreground="#B8B0A2").pack(side="left")
        ttk.Label(footer,text="Narzędzie pomocnicze — wymaga walidacji księgowej",foreground=GOLD).pack(side="right")

    def _tree(self,parent,cols,headings,widths=None,height=14):
        frame=ttk.Frame(parent);frame.pack(fill="both",expand=True,pady=8)
        tree=ttk.Treeview(frame,columns=cols,show="headings",height=height)
        for i,c in enumerate(cols):
            tree.heading(c,text=headings[i]);tree.column(c,width=(widths[i] if widths else 130),anchor="w" if i<2 else "e")
        y=ttk.Scrollbar(frame,orient="vertical",command=tree.yview);tree.configure(yscrollcommand=y.set)
        tree.pack(side="left",fill="both",expand=True);y.pack(side="right",fill="y")
        return tree

    def _build_dashboard(self):
        ttk.Label(self.dashboard,text="Podsumowanie ksiąg",style="Title.TLabel").pack(anchor="w",pady=(0,12))
        self.kpi_frame=ttk.Frame(self.dashboard);self.kpi_frame.pack(fill="x")
        self.kpis=[]
        for label in ("Liczba dekretów","Suma obrotów WN","Suma obrotów MA","Saldo banku 130",f"Wynik {date.today().year} YTD"):
            f=ttk.Frame(self.kpi_frame,style="Panel.TFrame",padding=12);f.pack(side="left",fill="both",expand=True,padx=4)
            ttk.Label(f,text=label,style="Gold.TLabel").pack(anchor="w")
            v=ttk.Label(f,text="0",background=PANEL,foreground=WHITE,font=("Segoe UI",16,"bold"));v.pack(anchor="w",pady=(8,0));self.kpis.append(v)
        ttk.Label(self.dashboard,text="Kontrole i statusy",style="Gold.TLabel").pack(anchor="w",pady=(20,8))
        self.status=tk.Text(self.dashboard,height=8,background="#222222",foreground=WHITE,insertbackground=WHITE,relief="flat",font=("Consolas",10),padx=10,pady=10)
        self.status.pack(fill="x")
        ttk.Label(self.dashboard,text="Model przykładowy. Sprawdź kompletność dekretów i dostosuj politykę rachunkowości oraz plan kont przed użyciem.",foreground=GOLD,wraplength=1000).pack(anchor="w",pady=14)
        ttk.Button(self.dashboard,text="Odśwież raporty",style="Gold.TButton",command=self.refresh_all).pack(anchor="w")

    def _build_journal(self):
        header=ttk.Frame(self.journal);header.pack(fill="x")
        ttk.Label(header,text="Nowy dekret",style="Title.TLabel").grid(row=0,column=0,columnspan=8,sticky="w",pady=(0,10))
        self.entry_date=tk.StringVar(value=date.today().isoformat());self.doc_no=tk.StringVar();self.description=tk.StringVar();self.counterparty=tk.StringVar()
        fields=[("Data (RRRR-MM-DD)",self.entry_date),("Numer dowodu",self.doc_no),("Opis",self.description),("Kontrahent",self.counterparty)]
        for i,(label,var) in enumerate(fields):
            ttk.Label(header,text=label).grid(row=1,column=i*2,sticky="w",padx=4)
            ttk.Entry(header,textvariable=var,width=22).grid(row=2,column=i*2,sticky="ew",padx=4,pady=4)
        for c in (1,3,5,7):header.grid_columnconfigure(c,weight=1)
        ttk.Label(self.journal,text="Dodaj pozycje WN/MA. Zapis będzie możliwy po zbilansowaniu dekretu.",foreground=GOLD).pack(anchor="w",pady=8)
        cols=("konto","nazwa","wn","ma","mpk")
        self.lines_tree=self._tree(self.journal,cols,("Konto","Nazwa konta","WN PLN","MA PLN","MPK / projekt"),(110,360,140,140,160),9)
        row=ttk.Frame(self.journal);row.pack(fill="x",pady=4)
        self.line_account=tk.StringVar();self.line_debit=tk.StringVar(value="0.00");self.line_credit=tk.StringVar(value="0.00");self.line_cc=tk.StringVar()
        accounts=self.ledger.accounts();self.account_labels={f"{x['code']} — {x['name']}":x['code'] for x in accounts}
        self.account_box=ttk.Combobox(row,textvariable=self.line_account,values=list(self.account_labels),width=43,state="readonly");self.account_box.pack(side="left",padx=3)
        ttk.Entry(row,textvariable=self.line_debit,width=14).pack(side="left",padx=3);ttk.Entry(row,textvariable=self.line_credit,width=14).pack(side="left",padx=3);ttk.Entry(row,textvariable=self.line_cc,width=18).pack(side="left",padx=3)
        ttk.Button(row,text="Dodaj wiersz",command=self.add_line).pack(side="left",padx=4)
        ttk.Button(row,text="Usuń zaznaczony",command=self.remove_line).pack(side="left",padx=4)
        self.entry_total=ttk.Label(self.journal,text="WN 0,00 PLN • MA 0,00 PLN");self.entry_total.pack(anchor="e",pady=7)
        ttk.Button(self.journal,text="Zapisz zbilansowany dekret",style="Gold.TButton",command=self.save_entry).pack(anchor="e")

    def add_line(self):
        label=self.line_account.get();code=self.account_labels.get(label)
        if not code: messagebox.showerror(APP_NAME,"Wybierz konto.");return
        try:dr=float(self.line_debit.get().replace(",","."));cr=float(self.line_credit.get().replace(",","."))
        except ValueError:messagebox.showerror(APP_NAME,"Wpisz prawidłowe kwoty.");return
        if dr<0 or cr<0 or (dr and cr) or not (dr or cr):messagebox.showerror(APP_NAME,"Wpisz dodatnią kwotę WN albo MA w jednym wierszu.");return
        name=next(a['name'] for a in self.ledger.accounts() if a['code']==code)
        self.lines_tree.insert("","end",values=(code,name,f"{dr:.2f}",f"{cr:.2f}",self.line_cc.get()))
        self.line_debit.set("0.00");self.line_credit.set("0.00");self.update_total()

    def remove_line(self):
        for item in self.lines_tree.selection():self.lines_tree.delete(item)
        self.update_total()

    def update_total(self):
        rows=[self.lines_tree.item(i,"values") for i in self.lines_tree.get_children()]
        debit=sum(float(r[2]) for r in rows);credit=sum(float(r[3]) for r in rows)
        self.entry_total.configure(text=f"WN {debit:,.2f} PLN • MA {credit:,.2f} PLN • różnica {debit-credit:,.2f}")

    def save_entry(self):
        rows=[self.lines_tree.item(i,"values") for i in self.lines_tree.get_children()]
        try:
            eid=self.ledger.add_entry(self.entry_date.get(),self.doc_no.get(),self.description.get(),self.counterparty.get(),[(r[0],r[2],r[3],r[4]) for r in rows])
        except Exception as exc:messagebox.showerror("Nie zapisano dekretu",str(exc));return
        messagebox.showinfo(APP_NAME,f"Zapisano dekret nr {eid}.")
        for item in self.lines_tree.get_children():self.lines_tree.delete(item)
        self.doc_no.set("");self.description.set("");self.counterparty.set("");self.update_total();self.refresh_all()

    def _build_book(self):
        ttk.Label(self.book,text="Dziennik dekretów",style="Title.TLabel").pack(anchor="w")
        self.book_tree=self._tree(self.book,("id","date","doc","description","party","count","debit","credit","check"),("ID","Data","Dowód","Opis","Kontrahent","Wiersze","WN PLN","MA PLN","Kontrola"),(60,115,130,270,190,75,130,130,120),18)
        ttk.Button(self.book,text="Eksportuj dziennik do CSV",style="Gold.TButton",command=self.export_csv).pack(anchor="e")

    def _build_accounts(self):
        ttk.Label(self.accounts_tab,text="Plan kont",style="Title.TLabel").pack(anchor="w")
        self.accounts_tree=self._tree(self.accounts_tab,("code","name","kind"),("Konto","Nazwa","Typ"),(140,560,180),17)
        form=ttk.Frame(self.accounts_tab);form.pack(fill="x")
        self.new_code=tk.StringVar();self.new_name=tk.StringVar();self.new_kind=tk.StringVar(value="Bilans")
        ttk.Label(form,text="Numer").pack(side="left");ttk.Entry(form,textvariable=self.new_code,width=12).pack(side="left",padx=4)
        ttk.Label(form,text="Nazwa").pack(side="left");ttk.Entry(form,textvariable=self.new_name,width=34).pack(side="left",padx=4)
        ttk.Combobox(form,textvariable=self.new_kind,values=["Bilans","Wynik"],state="readonly",width=12).pack(side="left",padx=4)
        ttk.Button(form,text="Dodaj konto",command=self.add_account).pack(side="left",padx=4)

    def add_account(self):
        code=self.new_code.get().strip();name=self.new_name.get().strip();kind=self.new_kind.get()
        if not code or not name:messagebox.showerror(APP_NAME,"Numer i nazwa konta są wymagane.");return
        try:
            with self.ledger.conn:self.ledger.conn.execute("INSERT INTO accounts(code,name,kind) VALUES(?,?,?)",(code,name,kind))
        except sqlite3.IntegrityError:messagebox.showerror(APP_NAME,"Konto o takim numerze już istnieje.");return
        self.new_code.set("");self.new_name.set("");self.refresh_all()

    def _build_reports(self):
        for parent,title in [(self.tb_tab,"Obroty i salda"),(self.pl_tab,"Rachunek wyników"),(self.bs_tab,"Bilans")]:ttk.Label(parent,text=title,style="Title.TLabel").pack(anchor="w")
        self.tb_tree=self._tree(self.tb_tab,("code","name","debit","credit","db","cb"),("Konto","Nazwa","Obroty WN","Obroty MA","Saldo WN","Saldo MA"),(100,370,140,140,140,140),17)
        self.pl_tree=self._tree(self.pl_tab,("code","name","debit","credit","net"),("Konto","Nazwa","Koszty WN","Przychody MA","Wynik netto konta"),(100,420,160,160,180),16)
        self.bs_tree=self._tree(self.bs_tab,("item","amount","mapping"),("Pozycja robocza","Saldo PLN","Mapowanie"),(400,180,400),14)

    def _build_company_tab(self, brand, label):
        tab=ttk.Frame(self.company_tabs,padding=18);self.company_tabs.add(tab,text=label)
        ttk.Label(tab,text=f"Weryfikacja podmiotu — {brand}",style="Title.TLabel").pack(anchor="w",pady=(0,12))
        ttk.Label(tab,text="Wpisz NIP podmiotu prawnego z dokumentów/rejestru. Marka lub nazwa grupy nie wskazuje automatycznie konkretnej spółki.",wraplength=950,foreground=GOLD).pack(anchor="w",pady=(0,12))
        line=ttk.Frame(tab);line.pack(fill="x")
        nip=tk.StringVar();checkdate=tk.StringVar(value=date.today().isoformat())
        ttk.Label(line,text="NIP").pack(side="left");ttk.Entry(line,textvariable=nip,width=20).pack(side="left",padx=6)
        ttk.Label(line,text="Data sprawdzenia (RRRR-MM-DD)").pack(side="left",padx=(18,4));ttk.Entry(line,textvariable=checkdate,width=15).pack(side="left",padx=4)
        result=tk.Text(tab,height=10,background="#222222",foreground=WHITE,relief="flat",font=("Consolas",10),padx=10,pady=10);result.pack(fill="x",pady=14)
        def run_check():
            result.delete("1.0","end");result.insert("end","Łączenie z wykazem podatników VAT Ministerstwa Finansów…\n")
            try:
                data=self.ledger.company_check(brand,nip.get(),checkdate.get())
            except Exception as exc:
                result.delete("1.0","end");result.insert("end",f"Wynik niedostępny: {exc}\nNie oznacza to negatywnego wyniku weryfikacji. Sprawdź NIP i ponów próbę.");return
            result.delete("1.0","end")
            for key,val in [("NIP",data.get('nip')),("Data wykazu",data.get('date')),("Nazwa z wykazu",data.get('name')),("Status VAT",data.get('statusVat')),("REGON",data.get('regon')),("KRS",data.get('krs')),("Adres",data.get('residenceAddress') or data.get('workingAddress')),("Rachunki",", ".join(data.get('accountNumbers') or [])),("Identyfikator zapytania",data.get('requestId'))]:result.insert("end",f"{key}: {val or 'brak danych'}\n")
            result.insert("end","\nŹródło: wykaz podatników VAT MF. Zweryfikuj zgodność nazwy, umocowanie i dokumenty; wynik VAT nie stanowi audytu kontrahenta.")
        actions=ttk.Frame(tab);actions.pack(anchor="w")
        ttk.Button(actions,text="Sprawdź w wykazie VAT MF",style="Gold.TButton",command=run_check).pack(side="left",padx=(0,8))
        ttk.Button(actions,text="Otwórz wyszukiwarkę KRS",command=lambda:webbrowser.open("https://wyszukiwarka-krs.ms.gov.pl/")).pack(side="left",padx=4)
        ttk.Button(actions,text="Otwórz wyszukiwarkę REGON GUS",command=lambda:webbrowser.open("https://wyszukiwarkaregon.stat.gov.pl/appBIR/index.aspx")).pack(side="left",padx=4)
        ttk.Label(tab,text="Wyniki zapytań są zapisywane lokalnie w bazie aplikacji. KRS/REGON otwierają oficjalne wyszukiwarki; nie są automatycznie odpytywane.",foreground="#B8B0A2",wraplength=950).pack(anchor="w",pady=16)

    def refresh_all(self):
        if not hasattr(self,"kpis"):return
        entries=self.ledger.entries();tb=self.ledger.trial_balance()
        debit=sum(r['debit'] for r in tb);credit=sum(r['credit'] for r in tb)
        bank=next((r['debit_balance']-r['credit_balance'] for r in tb if r['code']=='130'),0)
        pl=self.ledger.profit_loss(f"{date.today().year}-01-01",f"{date.today().year}-12-31")
        pnl=sum(r['credit']-r['debit'] for r in pl)
        for label,val in zip(self.kpis,[str(len(entries)),f"{debit:,.2f} PLN",f"{credit:,.2f} PLN",f"{bank:,.2f} PLN",f"{pnl:,.2f} PLN"]):label.configure(text=val)
        self.status.delete("1.0","end")
        imbalanced=[r for r in entries if round(r['debit'],2)!=round(r['credit'],2)]
        self.status.insert("end",f"Dekrety: {len(entries)} • niezbilansowane: {len(imbalanced)}\n")
        self.status.insert("end",f"Kontrola obrotów WN = MA: {'OK' if round(debit,2)==round(credit,2) else 'BŁĄD'}\n")
        self.status.insert("end",f"Plik bazy: {self.db_path}\n")
        self.status.insert("end","Przykładowy plan kont jest do dostosowania; raporty są robocze i nie stanowią zatwierdzonych sprawozdań finansowych.\n")
        self._populate(self.book_tree,[(r['id'],r['entry_date'],r['doc_no'],r['description'],r['counterparty'],r['line_count'],f"{r['debit']:.2f}",f"{r['credit']:.2f}","OK" if round(r['debit'],2)==round(r['credit'],2) else "BŁĄD") for r in entries])
        self._populate(self.accounts_tree,[(r['code'],r['name'],r['kind']) for r in self.ledger.accounts()])
        self._populate(self.tb_tree,[(r['code'],r['name'],f"{r['debit']:.2f}",f"{r['credit']:.2f}",f"{r['debit_balance']:.2f}",f"{r['credit_balance']:.2f}") for r in tb])
        plrows=self.ledger.profit_loss(f"{date.today().year}-01-01",f"{date.today().year}-12-31")
        self._populate(self.pl_tree,[(r['code'],r['name'],f"{r['debit']:.2f}",f"{r['credit']:.2f}",f"{r['credit']-r['debit']:.2f}") for r in plrows])
        assets=sum(r['debit_balance']-r['credit_balance'] for r in tb if r['code'] in {"010","070","201","300","310","490","100","130","240"})
        liabilities=sum(r['credit_balance']-r['debit_balance'] for r in tb if r['code'] in {"202","231","221","222","840"})
        equity=sum(r['credit_balance']-r['debit_balance'] for r in tb if r['code'] in {"800","820","860"})+pnl
        self._populate(self.bs_tree,[("Aktywa według przykładowej mapy",f"{assets:.2f}","010, 070, 100, 130, 201, 240, 300, 310, 490"),("Kapitał + wynik bieżący",f"{equity:.2f}","800, 820, 860 + wynik roku"),("Rezerwy i zobowiązania",f"{liabilities:.2f}","202, 231, 221, 222, 840"),("Kontrola różnicy",f"{assets-equity-liabilities:.2f}","Aktywa minus pasywa — wymaga kontroli mapowania")])

    @staticmethod
    def _populate(tree,rows):
        for iid in tree.get_children():tree.delete(iid)
        for row in rows:tree.insert("","end",values=row)

    def export_csv(self):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="dziennik.csv")
        if not path:return
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            writer=csv.writer(f,delimiter=";");writer.writerow(["ID","Data","Dowód","Opis","Kontrahent","Liczba wierszy","WN PLN","MA PLN","Kontrola"])
            for row in self.ledger.entries():writer.writerow([row['id'],row['entry_date'],row['doc_no'],row['description'],row['counterparty'],row['line_count'],f"{row['debit']:.2f}",f"{row['credit']:.2f}","OK" if round(row['debit'],2)==round(row['credit'],2) else "BŁĄD"])
        messagebox.showinfo(APP_NAME,"Zapisano dziennik do CSV.")

    def destroy(self):
        try:self.ledger.close()
        finally:super().destroy()


def main():
    app=App()
    app.mainloop()

if __name__ == "__main__":
    main()
