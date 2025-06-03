#!/usr/bin/env python3
import os
import subprocess
import sys
import time
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("BotSystem")

def check_env_file():
    """Check if env.txt exists and has necessary values."""
    if not os.path.exists('env.txt'):
        logger.error("env.txt file not found!")
        return False
    
    with open('env.txt', 'r') as file:
        content = file.read()
    
    # Check if TELEGRAM_CHAT_ID is set
    if 'TELEGRAM_CHAT_ID=' in content and not 'TELEGRAM_CHAT_ID=' in content.split('\n'):
        chat_id_line = [line for line in content.split('\n') if 'TELEGRAM_CHAT_ID=' in line][0]
        if not chat_id_line.split('=')[1].strip() or chat_id_line.split('=')[1].strip().startswith('#'):
            logger.warning("TELEGRAM_CHAT_ID is not set in env.txt")
            return False
    
    return True

def get_chat_id():
    """Run the get_chat_id.py script to get the chat ID."""
    logger.info("Running get_chat_id.py to retrieve the group chat ID...")
    try:
        subprocess.run([sys.executable, 'get_chat_id.py'], check=True)
        
        # Ask user for the chat ID
        chat_id = input("\nEnter the group chat ID from the list above: ").strip()
        if not chat_id:
            logger.error("No chat ID provided")
            return False
        
        # Update env.txt with the chat ID
        subprocess.run([sys.executable, 'update_env.py', chat_id], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running get_chat_id.py: {e}")
        return False

def run_main_app():
    """Run the main.py application."""
    logger.info("Starting the bot system...")
    try:
        process = subprocess.Popen([sys.executable, 'main.py'])
        
        # Print instructions
        print("\n" + "="*50)
        print("Bot system is running!")
        print("The bots should now be active in your Telegram group.")
        print("Press Ctrl+C to stop the system.")
        print("="*50 + "\n")
        
        # Wait for the process to complete or be interrupted
        process.wait()
    except KeyboardInterrupt:
        logger.info("Stopping the bot system...")
        if process.poll() is None:
            process.terminate()
            process.wait()
        logger.info("Bot system stopped")
    except Exception as e:
        logger.error(f"Error running main.py: {e}")

def main():
    """Main function to run the bot system."""
    print("\n" + "="*50)
    print("TELEGRAM AI BOTS SYSTEM")
    print("="*50)
    
    # Check if env.txt is configured
    if not check_env_file():
        print("\nYour env.txt needs to be configured before running the system.")
        choice = input("Do you want to get the chat ID now? (y/n): ").lower()
        if choice == 'y':
            if not get_chat_id():
                print("Failed to get chat ID. Please try again.")
                return
        else:
            print("Please set up your env.txt file manually and run this script again.")
            return
    
    # Run the main application
    run_main_app()

if __name__ == "__main__":
    main() 