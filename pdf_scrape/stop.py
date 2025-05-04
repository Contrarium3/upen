import shutil
import psutil
import time
import os
import signal

# CONFIG
min_free_gb = 1  # Minimum free space in GB before stopping the process
download_folder = os.path.abspath("Files")  # Using absolute path
target_cmdline_keywords = ["pdf_scrape/selenium_pdfs.py", "selenium_pdfs.py"]  # More flexible matching

def get_free_space_gb(folder):
    total, used, free = shutil.disk_usage(folder)
    return free / (1024 ** 3)

def kill_target_processes(keywords):
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline']:  # Make sure cmdline exists and isn't empty
                cmdline = ' '.join([str(arg) for arg in proc.info['cmdline'] if arg])
                print(f"PID={proc.pid}, Cmdline={cmdline}")  # debug print
                
                # Check if any keyword matches
                if any(keyword in cmdline for keyword in keywords):
                    print(f"Killing process: PID={proc.pid}, Cmdline={cmdline}")
                    os.kill(proc.pid, signal.SIGKILL)
                    killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError):
            pass
    
    return killed_count

print(f"Monitoring disk space in {download_folder}...")
print(f"Will kill processes containing any of these keywords: {target_cmdline_keywords}")

while True:
    free_gb = get_free_space_gb(download_folder)
    print(f"Free space: {free_gb:.2f}GB (minimum required: {min_free_gb}GB)")
    
    if free_gb < min_free_gb:
        print(f"Disk space below {min_free_gb}GB ({free_gb:.2f}GB left). Stopping Selenium downloads.")
        killed = kill_target_processes(target_cmdline_keywords)
        print(f"Killed {killed} processes")
        break
    time.sleep(5)

print("Script finished monitoring")