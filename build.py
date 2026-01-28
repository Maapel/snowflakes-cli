import PyInstaller.__main__
import shutil
import os

print("❄️  Freezing Snowflakes...")

PyInstaller.__main__.run([
    'main.py',
    '--name=snowflakes',
    '--onefile',
    '--clean',
    # Hidden imports are crucial for sqlmodel/rich
    '--hidden-import=sqlmodel',
    '--hidden-import=sqlmodel.sql.expression',
    '--hidden-import=sqlmodel.engine.result', 
    '--hidden-import=rich',
    '--hidden-import=sqlite3',
    '--hidden-import=rich.columns',
    '--hidden-import=rich.panel',
    '--hidden-import=rich.text',
])

print("❄️  Build complete.")

# Optional: cleanup
if os.path.exists("build"):
    shutil.rmtree("build")
if os.path.exists("snowflakes.spec"):
    os.remove("snowflakes.spec")
    
print(f"❄️  Binary is ready at: {os.path.abspath('dist/snowflakes')}")
