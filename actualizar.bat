@echo off
cd /d "C:\Users\JFRodriguez\OneDrive - Autoridad del Canal de Panama\Documents\Doc Doctorado\Articulo 1\Borrador Articulo\nuevo\MareasTest\DATA\TuRepo"
python download_data.py
git add data/
git commit -m "Auto %date% %time%"
git push