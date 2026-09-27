import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app import create_app

app = create_app()

print("BASE DIR:", BASE_DIR)
print("FILES:", os.listdir(BASE_DIR))
print("TEMPLATE:", app.template_folder)