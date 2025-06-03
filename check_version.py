#!/usr/bin/env python3
import importlib.metadata
import sys

def get_package_version(package_name):
    try:
        version = importlib.metadata.version(package_name)
        return version
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception as e:
        return f"Error: {str(e)}"

def check_telegram_bot():
    print("Python Telegram Bot Version Check")
    print("="*40)
    
    # Check python-telegram-bot version
    ptb_version = get_package_version("python-telegram-bot")
    if ptb_version:
        print(f"python-telegram-bot version: {ptb_version}")
        
        # Determine if version is v13 or v20+
        try:
            major_version = int(ptb_version.split('.')[0])
            if major_version >= 20:
                print("You have a v20+ installation (uses httpx.AsyncClient)")
                print("This likely causes the proxy parameter error")
                print("\nSuggested fix options:")
                print("1. Run 'python fix_proxy.py' to patch the library")
                print("2. Downgrade with: pip install python-telegram-bot==13.15")
            elif major_version >= 13:
                print("You have a v13 installation (should work with proxy)")
                print("If you're seeing proxy errors, there might be a different issue")
            else:
                print(f"You have an older v{major_version} installation")
        except:
            print(f"Could not determine major version from: {ptb_version}")
    else:
        print("python-telegram-bot is not installed")
    
    # Check related packages
    print("\nRelated packages:")
    for package in ["httpx", "telegram", "urllib3", "requests"]:
        version = get_package_version(package)
        if version:
            print(f"  {package}: {version}")
        else:
            print(f"  {package}: Not installed")
    
    # Print Python version
    print(f"\nPython version: {sys.version}")

if __name__ == "__main__":
    check_telegram_bot() 