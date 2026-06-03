@echo off
cd /d "%~dp0"
python -c "import tkinter as tk; r=tk.Tk(); r.title('TEST'); r.geometry('300x200'); tk.Label(r,text='If you see this, GUI works').pack(); r.after(3000,r.destroy); r.mainloop()"
echo done
pause
