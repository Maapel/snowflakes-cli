import PyInstaller.__main__
import shutil
import os

print("❄️  Freezing Snowflakes...")

PyInstaller.__main__.run([
    'main.py',
    '--name=snowflakes',
    '--onefile',
    '--clean',
    '--add-data=static:static',
    # Hidden imports are crucial for sqlmodel/rich
    '--hidden-import=sqlmodel',
    '--hidden-import=sqlmodel.sql.expression',
    '--hidden-import=sqlmodel.engine.result', 
    '--hidden-import=rich',
    '--hidden-import=sqlite3',
    '--hidden-import=rich.columns',
    '--hidden-import=rich.panel',
    '--hidden-import=rich.text',
    '--hidden-import=uvicorn',
    '--hidden-import=fastapi',
    '--hidden-import=starlette',
    '--hidden-import=email.mime.multipart',
    '--hidden-import=email.mime.text',
    '--hidden-import=email.mime.application',
    '--collect-all=rich',
    '--collect-all=uvicorn',
    '--collect-all=fastapi',
])

print("❄️  Build complete.")

# Optional: cleanup
if os.path.exists("build"):
    shutil.rmtree("build")
if os.path.exists("snowflakes.spec"):
    os.remove("snowflakes.spec")
    
print(f"❄️  Binary is ready at: {os.path.abspath('dist/snowflakes')}")
