#!/usr/bin/env python3
import re
import sys

def update_chat_id(env_file_path, chat_id):
    """Update the TELEGRAM_CHAT_ID in the env file."""
    with open(env_file_path, 'r') as file:
        content = file.read()
    
    # Replace the chat ID line
    updated_content = re.sub(
        r'TELEGRAM_CHAT_ID=.*',
        f'TELEGRAM_CHAT_ID={chat_id}',
        content
    )
    
    with open(env_file_path, 'w') as file:
        file.write(updated_content)
    
    print(f"Updated {env_file_path} with chat ID: {chat_id}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_env.py CHAT_ID")
        sys.exit(1)
    
    chat_id = sys.argv[1]
    update_chat_id('env.txt', chat_id)
    print("Now you can run the main application with: python main.py") 