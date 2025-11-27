import ttkbootstrap as ttk
from ttkbootstrap.constants import *

app = ttk.Window(themename="cosmo") # Assuming a light theme based on user image
app.geometry("800x400")

cols = ("Ticker", "Name", "Price")
tree = ttk.Treeview(app, columns=cols, show="headings", bootstyle="primary")

tree.heading("Ticker", text="Ticker")
tree.heading("Name", text="Name")
tree.heading("Price", text="Price")

tree.pack(fill=BOTH, expand=True, padx=10, pady=10)

# Attempt to fix styling
style = ttk.Style()
style.configure("Treeview.Heading", borderwidth=1, relief="solid", bordercolor="white")

app.mainloop()
