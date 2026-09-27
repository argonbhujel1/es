import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

print("BASE_DIR:", BASE_DIR)
print("ROOT FILES:", os.listdir(BASE_DIR))

from app import create_app

app = create_app()

print("TEMPLATE FOLDER:", app.template_folder)
print("TEMPLATE EXISTS:", os.path.exists(app.template_folder))
print("PUBLIC EXISTS:", os.path.exists(os.path.join(app.template_folder, "public")))
print("INDEX EXISTS:", os.path.exists(os.path.join(app.template_folder, "public", "index.html")))