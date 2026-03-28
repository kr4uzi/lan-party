import os
import urllib.request
import stat
import subprocess
import shutil

def fetch_file(ver, config, filename, target_dir):
    for arch in config["search"]:
        url = f"http://repo.tinycorelinux.net/{ver}/{arch}/tcz/{filename}"
        target_path = os.path.join(target_dir, filename)
        
        if os.path.exists(target_path):
            return True

        try:
            with urllib.request.urlopen(url) as response, open(target_path, 'wb') as out_file:
                out_file.write(response.read())
            return True
        except Exception as e:
            continue
        
    return False

def process_extension(ver, config, tcz_name, target_dir, stack, files):
    print(f"{" > ".join(stack)}")

    # Download the core trio
    if not fetch_file(ver, config, tcz_name, target_dir):
        print(f"Extension {tcz_name} not found")
        return False

    fetch_file(ver, config, f"{tcz_name}.md5.txt", target_dir)
    
    dep_file = f"{tcz_name}.dep"
    if fetch_file(ver, config, dep_file, target_dir):
        dep_path = os.path.join(target_dir, dep_file)
        if os.path.exists(dep_path):
            with open(dep_path, 'r') as f:
                for line in f:
                    dep = line.strip()
                    if dep:
                        stack.append(dep)
                        success = process_extension(ver, config, dep, target_dir, stack, files)
                        stack = stack[:-1]
                        if not success:
                            return False


    files.add(f"{tcz_name}")
    files.add(f"{tcz_name}.md5.txt")
    files.add(f"{tcz_name}.dep")
    return True

def build_assets(ver, basedir, name, config):
    print(f"\n--- Starting Build for {name} ---")
    build_root = os.path.join(basedir, f"build{name}")
    # the wiki says it should be possible to put everything in /tmp/builtin
    # /tmp/builtin/optional -> *.tcz *.md5.txt *.dep files
    # /tmp/builtin/onboot.lst
    # but putting them there didn't work for me (/tmp/setup.lst permission denied errors)
    shutil.copytree(os.path.join(basedir, "ramfs"), build_root, dirs_exist_ok=True)
    tce_dir = os.path.join(build_root, "assets")
    opt_dir = os.path.join(tce_dir, "optional")
    outfile = os.path.join(basedir, config["file"])
    
    os.makedirs(opt_dir, exist_ok=True)

    with open("extensions.txt", 'r') as f:
        seeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    required_files = set()
    for seed in seeds:
        if not process_extension(ver, config, seed, opt_dir, [seed], required_files):
            print("Aborting...")
            return

    with open(os.path.join(tce_dir, "onboot.lst"), "w") as f:
        f.write('\n'.join(seeds))  

    for e in os.scandir(opt_dir):
        if e.is_file():
            if e.name in required_files: continue
            print(f"{e.name} not required, removing")
            os.remove(e.path)
    
    cmd = f"find . | cpio -o -H newc --owner=0:0 | gzip -9 > {outfile}"
    subprocess.run(cmd, shell=True, cwd=build_root)
    print(f"Successfully created {config["file"]}")

if __name__ == "__main__":
    ver = "17.x"

    config = {
        "x86": {
            "search": ["x86"],
            "file": "assets.gz"
        },
        "x64": {
            "search": ["x86_x64", "x86"],
            "file": "assets64.gz"
        }
    }
    dir = os.path.abspath(os.curdir)
    for name in config:
        build_assets(ver, dir, name, config[name])