"""
建材模擬 HTML 產生工具 — 圖形介面版（含即時預覽）
雙擊 START.bat 開啟
"""
import sys, os, json, threading, base64, subprocess, tempfile, webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

TOOLS_DIR = Path(__file__).parent
OUTPUT_DIR = TOOLS_DIR / "output"
CONFIG_PATH = TOOLS_DIR / "project_config.json"

# ─── 延遲載入 OpenCV（避免啟動失敗） ───────
cv2 = None
def _lazy_cv(img):
    global cv2
    if cv2 is None:
        import cv2 as _cv2
        cv2 = _cv2
    return cv2.imdecode(_cv2.imread(img) if isinstance(img, str) else img)

def _load_img(path):
    global cv2
    if cv2 is None:
        import cv2 as _cv2
        cv2 = _cv2
    if isinstance(path, str):
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    return path

np = None
def _lazy_np():
    global np
    if np is None:
        import numpy as _np
        np = _np


class PreviewRenderer:
    """即時預覽渲染器 — 把素材貼到房間照片上"""

    def __init__(self):
        _lazy_np()

    def render_preview(self, room_img, texture_img, polygon, preview_w=600):
        h, w = room_img.shape[:2]
        scale = preview_w / w
        preview_h = int(h * scale)

        room_small = cv2.resize(room_img, (preview_w, preview_h))

        poly_scaled = np.array(polygon, dtype=np.float32) * scale

        mask = np.zeros((preview_h, preview_w), dtype=np.uint8)
        pts = poly_scaled.astype(np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
        mask = cv2.GaussianBlur(mask.astype(np.float32), (5, 5), 3)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

        th, tw = texture_img.shape[:2]
        dst_pts = poly_scaled.reshape(-1, 2).astype(np.float32)
        if len(dst_pts) < 4:
            return room_small
        if len(dst_pts) > 4:
            rect = cv2.minAreaRect(dst_pts)
            dst_pts = cv2.boxPoints(rect)
        src_pts = np.array([[0, 0], [tw - 1, 0], [tw - 1, th - 1], [0, th - 1]], dtype=np.float32)

        try:
            M = cv2.getPerspectiveTransform(src_pts, dst_pts)
            warped = cv2.warpPerspective(texture_img, M, (preview_w, preview_h))
        except cv2.error:
            warped = cv2.resize(texture_img, (preview_w, preview_h))

        scene_f = room_small.astype(np.float32) / 255.0
        tex_f = warped.astype(np.float32) / 255.0
        gray = cv2.cvtColor(room_small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        lighting = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        blended = tex_f * (lighting * 0.7 + 0.3)
        blended = np.clip(blended, 0, 1) * 255
        mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR).astype(np.float32) / 255.0
        result = room_small.astype(np.float32) * (1 - mask_3ch) + blended * mask_3ch
        return np.clip(result, 0, 255).astype(np.uint8)

    def img_to_tk(self, img_bgr, max_w=600):
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        cv2.imencode(".png", rgb)[1].tofile(tmp.name)
        return tk.PhotoImage(file=tmp.name), tmp.name


class MaterialSwapApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("建材模擬 HTML 產生工具")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)

        self.room_path = tk.StringVar()
        self.project_name = tk.StringVar(value="我的專案")
        self.room_img = None
        self.regions = []
        self._preview_tmp_files = []

        self.renderer = PreviewRenderer()

        self._build_menu()
        self._build_ui()
        self._load_config()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _build_menu(self):
        mb = tk.Menu(self.root)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="載入設定檔...", command=self._load_config_dialog)
        fm.add_command(label="儲存設定檔", command=self._save_config)
        fm.add_separator()
        fm.add_command(label="結束", command=self.root.quit)
        mb.add_cascade(label="檔案", menu=fm)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label="使用說明", command=self._show_help)
        mb.add_cascade(label="說明", menu=hm)
        self.root.config(menu=mb)

    def _build_ui(self):
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        # ═══ 左側：預覽區 ═══
        left = ttk.LabelFrame(main, text="即時預覽", padding=5)
        main.add(left, weight=3)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="📷 選取房間照片", command=self._select_room).pack(side=tk.LEFT)
        self.room_label = ttk.Label(btn_frame, text="尚未選取", foreground="gray")
        self.room_label.pack(side=tk.LEFT, padx=8)

        self.preview_canvas = tk.Canvas(left, bg="#2a2a2a", highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_img_on_canvas = None

        # ═══ 右側：控制面板 ═══
        right = ttk.Frame(main)
        main.add(right, weight=2)

        # 專案名稱
        nf = ttk.Frame(right)
        nf.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(nf, text="專案名稱:").pack(side=tk.LEFT)
        ttk.Entry(nf, textvariable=self.project_name, width=25).pack(side=tk.LEFT, padx=5)

        # 區塊列表
        self.region_frame = ttk.LabelFrame(right, text="區塊", padding=5)
        self.region_frame.pack(fill=tk.X, pady=(0, 5))

        rf = ttk.Frame(self.region_frame)
        rf.pack(fill=tk.X)
        ttk.Button(rf, text="＋ 自動偵測", command=self._auto_detect).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(rf, text="✕ 刪除", command=self._delete_region).pack(side=tk.LEFT)

        self.region_listbox = tk.Listbox(self.region_frame, height=5, selectmode=tk.SINGLE)
        self.region_listbox.pack(fill=tk.X, pady=(5, 0))
        self.region_listbox.bind("<<ListboxSelect>>", self._on_region_click)

        # 區塊名稱
        nf2 = ttk.Frame(self.region_frame)
        nf2.pack(fill=tk.X, pady=(3, 0))
        ttk.Label(nf2, text="名稱:").pack(side=tk.LEFT)
        self.region_name_var = tk.StringVar()
        ttk.Entry(nf2, textvariable=self.region_name_var, width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(nf2, text="改名", command=self._rename_region, width=6).pack(side=tk.LEFT)

        # 素材列表
        self.mat_frame = ttk.LabelFrame(right, text="素材（點選下方素材可即時預覽）", padding=5)
        self.mat_frame.pack(fill=tk.BOTH, expand=True)

        mf = ttk.Frame(self.mat_frame)
        mf.pack(fill=tk.X)
        ttk.Button(mf, text="＋ 加入素材圖片", command=self._add_material).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(mf, text="✕ 移除", command=self._remove_material).pack(side=tk.LEFT)

        cols = ("name", "file")
        self.mat_tree = ttk.Treeview(self.mat_frame, columns=cols, show="headings", height=5)
        self.mat_tree.heading("name", text="素材名稱")
        self.mat_tree.heading("file", text="檔案")
        self.mat_tree.column("name", width=120)
        self.mat_tree.column("file", width=180)
        self.mat_tree.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.mat_tree.bind("<<TreeviewSelect>>", self._on_material_select)

        # ═══ 底部操作列 ═══
        bot = ttk.Frame(self.root, padding=8)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = ttk.Label(bot, text="就緒", foreground="gray")
        self.status_label.pack(side=tk.LEFT)
        ttk.Button(bot, text="🎬 產生 HTML 網頁", command=self._generate_html).pack(side=tk.RIGHT)

    # ─── 功能函式 ────────────────────────

    def _log(self, msg):
        self.status_label.config(text=msg)
        self.root.update()

    def _select_room(self):
        p = filedialog.askopenfilename(title="選擇房間照片", filetypes=[("圖片", "*.jpg *.jpeg *.png"), ("所有", "*.*")])
        if not p: return
        self.room_path.set(p)
        self.room_label.config(text=Path(p).name, foreground="black")
        global cv2
        if cv2 is None:
            import cv2 as _cv2
            cv2 = _cv2
        self.room_img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
        self._update_preview()
        self._log(f"已載入: {Path(p).name}")

    def _update_preview(self, specific_result=None):
        if self.room_img is None:
            return
        cw = self.preview_canvas.winfo_width()
        cw = max(cw, 400)
        if specific_result is not None:
            disp = specific_result
        else:
            disp = self.room_img.copy()
        h, w = disp.shape[:2]
        scale = cw / w
        new_w = int(w * scale)
        new_h = int(h * scale)
        small = cv2.resize(disp, (new_w, new_h))
        from PIL import Image as PILImage
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        pil_img = PILImage.fromarray(rgb)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        self._preview_tmp_files.append(tmp.name)
        pil_img.save(tmp.name, "PNG")
        self.preview_canvas.delete("all")
        self.preview_img_on_canvas = tk.PhotoImage(file=tmp.name)
        self.preview_canvas.config(width=new_w, height=new_h)
        self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self.preview_img_on_canvas)

        # 畫區塊邊界
        for ri, reg in enumerate(self.regions):
            if not reg.get("polygon"): continue
            pts = (np.array(reg["polygon"], dtype=np.int32) * scale).reshape(-1, 2).tolist()
            if len(pts) < 2: continue
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                self.preview_canvas.create_line(x1, y1, x2, y2, fill="#ff6b00", width=3)
            cx = int(sum(p[0] for p in pts) / len(pts))
            cy = int(sum(p[1] for p in pts) / len(pts))
            self.preview_canvas.create_text(cx, cy, text=reg["name"], fill="white",
                                            font=("Arial", 11, "bold"), tags="rlabel")

    def _auto_detect(self):
        if not self.room_path.get():
            messagebox.showwarning("", "請先選取房間照片")
            return
        self._log("正在偵測區塊，請稍候...（約 5-15 秒）")
        self.root.config(cursor="watch")
        self.root.update()

        def run():
            try:
                from generate_regions import detect_regions_from_image
                res = detect_regions_from_image(self.room_path.get())
                self.root.after(0, lambda: self._on_detect_done(res))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._log("偵測失敗"))
                self.root.after(0, lambda: self._show_detect_error(err_msg))

        threading.Thread(target=run, daemon=True).start()

    def _show_detect_error(self, msg):
        self.root.config(cursor="")
        messagebox.showerror("偵測失敗",
            f"無法自動偵測區塊:\n{msg}\n\n"
            "你可以手動在 project_config.json 中填寫區塊座標")

    def _on_detect_done(self, results):
        self.root.config(cursor="")
        self.regions.clear()
        for i, s in enumerate(results):
            self.regions.append({"name": f"區塊{i+1}", "polygon": s["polygon"], "materials": []})
        self._refresh_regions()
        if self.regions:
            self.region_listbox.selection_set(0)
            self._on_region_click()
        self._update_preview()
        if not results:
            self._log("沒有找到明顯區塊，請換一張照片試試")
        else:
            self._log(f"找到 {len(self.regions)} 個區塊")

    def _refresh_regions(self):
        self.region_listbox.delete(0, tk.END)
        for r in self.regions:
            self.region_listbox.insert(tk.END, f"{r['name']} ({len(r['materials'])} 素材)")

    def _on_region_click(self, event=None):
        sel = self.region_listbox.curselection()
        for i in self.mat_tree.get_children():
            self.mat_tree.delete(i)
        if not sel: return
        r = self.regions[sel[0]]
        self.region_name_var.set(r["name"])
        for m in r["materials"]:
            self.mat_tree.insert("", tk.END, values=(m["name"], m["file"]))
        self._update_preview()

    def _rename_region(self):
        sel = self.region_listbox.curselection()
        if not sel: return
        n = self.region_name_var.get().strip()
        if n:
            self.regions[sel[0]]["name"] = n
            self._refresh_regions()
            self.region_listbox.selection_set(sel[0])
            self._update_preview()

    def _delete_region(self):
        sel = self.region_listbox.curselection()
        if not sel: return
        if messagebox.askyesno("", f"刪除「{self.regions[sel[0]]['name']}」?"):
            del self.regions[sel[0]]
            self._refresh_regions()
            for i in self.mat_tree.get_children():
                self.mat_tree.delete(i)
            self._update_preview()

    def _add_material(self):
        sel = self.region_listbox.curselection()
        if not sel:
            messagebox.showwarning("", "請先選取一個區塊")
            return
        p = filedialog.askopenfilename(title="素材圖片", filetypes=[("圖片", "*.jpg *.jpeg *.png"), ("所有", "*.*")])
        if not p: return
        name = Path(p).stem
        rel = os.path.relpath(p, TOOLS_DIR)
        self.regions[sel[0]]["materials"].append({"name": name, "file": rel})
        self._on_region_click()
        self._refresh_regions()
        self.region_listbox.selection_set(sel[0])
        self._log(f"已加入: {name}")

        # 自動選取剛加入的素材並預覽
        items = self.mat_tree.get_children()
        if items:
            self.mat_tree.selection_set(items[-1])
            self._on_material_select()

    def _remove_material(self):
        sel = self.region_listbox.curselection()
        ms = self.mat_tree.selection()
        if not sel or not ms: return
        vals = self.mat_tree.item(ms[0], "values")
        region = self.regions[sel[0]]
        for i, m in enumerate(region["materials"]):
            if m["name"] == vals[0] and m["file"] == vals[1]:
                del region["materials"][i]
                break
        self._on_region_click()
        self._update_preview()
        self._log("已移除素材")

    def _on_material_select(self, event=None):
        """點選素材時，即時預覽貼圖效果"""
        sel = self.region_listbox.curselection()
        ms = self.mat_tree.selection()
        if not sel or not ms:
            self._update_preview()
            return
        r = self.regions[sel[0]]
        if not r.get("polygon") or not r["materials"]:
            self._update_preview()
            return
        vals = self.mat_tree.item(ms[0], "values")
        mat_file = vals[1]
        mat_path = TOOLS_DIR / mat_file
        if not mat_path.exists():
            self._log(f"找不到素材檔案: {mat_file}")
            return

        self._log("渲染預覽中...")
        def render():
            try:
                mat_img = cv2.imdecode(np.fromfile(str(mat_path), dtype=np.uint8), cv2.IMREAD_COLOR)
                if mat_img is None or self.room_img is None:
                    self.root.after(0, lambda: self._update_preview())
                    return
                res = self.renderer.render_preview(self.room_img, mat_img, r["polygon"])
                self.root.after(0, lambda: self._update_preview(res))
                self.root.after(0, lambda: self._log(f"預覽: {vals[0]}"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"預覽失敗: {e}"))
        threading.Thread(target=render, daemon=True).start()

    # ─── 載入／儲存 ─────────────────────────

    def _load_config(self):
        if not CONFIG_PATH.exists(): return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.project_name.set(d.get("project_name", "我的專案"))
            rp = d.get("room_photo", "")
            if rp:
                fp = TOOLS_DIR / rp
                if fp.exists():
                    self.room_path.set(str(fp))
                    self.room_label.config(text=fp.name, foreground="black")
                    self.room_img = cv2.imdecode(np.fromfile(str(fp), dtype=np.uint8), cv2.IMREAD_COLOR)
            self.regions = d.get("regions", [])
            self._refresh_regions()
            if self.regions:
                self.region_listbox.selection_set(0)
                self._on_region_click()
            self._update_preview()
        except: pass

    def _load_config_dialog(self):
        p = filedialog.askopenfilename(title="載入設定", filetypes=[("JSON", "*.json")])
        if not p: return
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.project_name.set(d.get("project_name", ""))
            self.regions = d.get("regions", [])
            self._refresh_regions()
            if self.regions:
                self.region_listbox.selection_set(0)
                self._on_region_click()
            self._log(f"已載入: {Path(p).name}")
        except Exception as e:
            messagebox.showerror("", f"載入失敗: {e}")

    def _save_config(self):
        rel = ""
        if self.room_path.get():
            try: rel = os.path.relpath(self.room_path.get(), TOOLS_DIR)
            except: rel = self.room_path.get()
        d = {"project_name": self.project_name.get(), "room_photo": rel, "regions": self.regions}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _generate_html(self):
        if not self.room_path.get():
            messagebox.showwarning("", "請先選取房間照片")
            return
        if not self.regions:
            messagebox.showwarning("", "請先偵測區塊")
            return
        self._save_config()
        self._log("正在產生 HTML ...")

        def run():
            try:
                r = subprocess.run(
                    [sys.executable, str(TOOLS_DIR / "generate_html.py")],
                    capture_output=True, text=True, cwd=TOOLS_DIR, timeout=300
                )
                self.root.after(0, lambda: self._on_gen_done(r))
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: messagebox.showerror("錯誤", "產生超時，可能圖片太大"))
                self.root.after(0, lambda: self._log("產生超時"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"產生失敗:\n{e}"))
                self.root.after(0, lambda: self._log("產生失敗"))
        threading.Thread(target=run, daemon=True).start()

    def _on_gen_done(self, result):
        if result.returncode != 0:
            err = result.stderr[:500] if result.stderr else "(無錯誤訊息)"
            messagebox.showerror("產生失敗", f"錯誤:\n{err}")
            self._log("產生失敗")
            return
        OUTPUT_DIR.mkdir(exist_ok=True)
        files = list(OUTPUT_DIR.glob("*.html"))
        if not files:
            messagebox.showwarning("", "完成但找不到 HTML 檔")
            return
        latest = max(files, key=os.path.getmtime)
        mb = latest.stat().st_size / (1024 * 1024)
        if messagebox.askyesno("完成", f"✅ 產出: {latest.name} ({mb:.1f} MB)\n用瀏覽器打開？"):
            webbrowser.open(str(latest))
        self._log(f"完成: {latest.name}")

    def _show_help(self):
        messagebox.showinfo("使用說明",
            "1. 選取房間照片\n"
            "2. 按「自動偵測」抓出區塊（牆/地/天花板）\n"
            "3. 點左邊區塊 → 右邊改名\n"
            "4. 點「加入素材圖片」選磁磚/木板照片\n"
            "5. 點素材名稱 → 預覽區即時顯示貼合效果\n"
            "6. 全部滿意後按「產生 HTML」\n"
            "7. 產出的 .html 可寄給客戶開")

    def _on_close(self):
        for f in self._preview_tmp_files:
            try: os.remove(f)
            except: pass
        self.root.destroy()


if __name__ == "__main__":
    _lazy_np()
    MaterialSwapApp()
