import sys
import os
sys.path.insert(0, r'd:\Inovation\TCM-QAsystem\QAsystem\src')
os.chdir(r'd:\Inovation\TCM-QAsystem\QAsystem\src')

from app import app

if __name__ == '__main__':
    print("=" * 60)
    print("Starting TCM QA System (Knowledge Graph Enhanced)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)