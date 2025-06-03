import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import User
from dotenv import load_dotenv
from typing import List, Dict

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Telegram API settings
API_ID = os.getenv("TELEGRAM_API_ID", "22589967")
API_HASH = os.getenv("TELEGRAM_API_HASH", "3928a608ba40e683e1cf54d0403f47ca")
DESTINATION_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Hardcoded target group name
TARGET_GROUP_NAME = "$EVAN | LORD OF DEGENS"

async def find_group_by_name(client, name):
    """Simply find the group by its name"""
    print(f"Looking for group: {name}")
    
    dialogs = await client.get_dialogs(limit=None)
    
    for dialog in dialogs:
        if hasattr(dialog.entity, 'title') and name in dialog.entity.title:
            print(f"\n==== GROUP FOUND ====")
            print(f"Title: {dialog.entity.title}")
            print(f"Group ID: {dialog.entity.id}")
            print(f"For .env: TELEGRAM_CHAT_ID=-100{abs(dialog.entity.id)}")
            return dialog.entity
    
    return None

async def forward_messages(client, source_entity, dest_id):
    """Forward new messages from source to destination"""
    print(f"\n==================================================")
    print(f"🔴 NOW STREAMING: {source_entity.title}")
    print(f"Group ID: {source_entity.id}")
    print(f"For .env: TELEGRAM_CHAT_ID=-100{abs(source_entity.id)}")
    print(f"==================================================")
    print("Messages will be forwarded as they arrive.")
    print(f"Destination chat ID: {dest_id}")
    print("Press Ctrl+C to stop.")
    
    # Counter for messages
    message_count = 0
    
    @client.on(events.NewMessage(chats=source_entity))
    async def handler(event):
        nonlocal dest_id
        nonlocal message_count
        # Get message text
        message = event.message
        
        print(f"\n----- New message detected in {source_entity.title} -----")
        
        if not message.text:
            print(f"Message has no text content (might be media). Skipping.")
            logger.info("Ignoring non-text message")
            return
        
        # Get sender info
        try:
            sender = await event.get_sender()
            if isinstance(sender, User):
                sender_name = sender.username or f"{sender.first_name} {sender.last_name or ''}".strip()
            else:
                sender_name = "Unknown"
            print(f"From: {sender_name}")
            print(f"Message: {message.text[:50]}..." if len(message.text) > 50 else f"Message: {message.text}")
        except Exception as e:
            logger.error(f"Error getting sender: {e}")
            sender_name = "Unknown"
            print(f"Error getting sender: {e}")
        
        # Format forwarded message
        formatted_message = f"{sender_name}: {message.text}"
        logger.info(f"Forwarding message from {sender_name}")
        
        # Send to destination
        try:
            print(f"Forwarding to chat ID: {dest_id}")
            await client.send_message(int(dest_id), formatted_message)
            message_count += 1
            print(f"✅ Message forwarded successfully (Total: {message_count})")
            logger.info("Message forwarded successfully")
        except Exception as e:
            print(f"❌ Error forwarding message: {e}")
            logger.error(f"Error forwarding message: {e}")
            
            # Try with different format
            try:
                print("Trying alternative destination format...")
                alt_dest_id = dest_id
                if dest_id.startswith('-100'):
                    alt_dest_id = dest_id[4:]  # Remove -100 prefix
                else:
                    alt_dest_id = f"-100{dest_id}"  # Add -100 prefix
                    
                print(f"Attempting with: {alt_dest_id}")
                await client.send_message(int(alt_dest_id), formatted_message)
                print("✅ Message forwarded successfully with alternative format")
                logger.info("Message forwarded with alternative format")
                
                # Update the dest_id for future messages
                dest_id = alt_dest_id
            except Exception as alt_e:
                print(f"❌ Alternative format also failed: {alt_e}")
                logger.error(f"Alternative format also failed: {alt_e}")
    
    # Keep the script running
    while True:
        await asyncio.sleep(1)

async def main():
    # Use the existing session from this script
    session_name = 'session_stream_joins'
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.start()
    
    # Find the EVAN group
    evan_group = await find_group_by_name(client, TARGET_GROUP_NAME)
    
    if not evan_group:
        print(f"Could not find group: {TARGET_GROUP_NAME}")
        await client.disconnect()
        return
    
    print(f"\nFound the group: {evan_group.title}")
    
    # Ask if want to stream from it
    start_stream = input("\nDo you want to start streaming from this group? (y/n): ").lower().strip()
    
    if start_stream != 'y':
        print("Not streaming. Exiting.")
        await client.disconnect()
        return
    
    # Get destination chat ID
    dest_chat_id = DESTINATION_CHAT_ID
    if not dest_chat_id:
        dest_chat_id = input("Enter the destination chat ID (where you want messages sent): ")
    
    # Ensure proper ID format (in case it's missing the -100 prefix)
    try:
        numeric_id = int(dest_chat_id)
        # If it's a positive number and larger than 10000, it likely needs the -100 prefix
        if numeric_id > 0 and numeric_id > 10000:
            dest_chat_id = f"-100{numeric_id}"
            print(f"Formatted destination ID to: {dest_chat_id}")
    except ValueError:
        # Not a number, keep as is (might be a username)
        pass
    
    print(f"\nStreaming to destination: {dest_chat_id}")
    
    # Verify the destination chat exists
    try:
        dest_entity = await client.get_entity(int(dest_chat_id))
        print(f"Successfully verified destination: {getattr(dest_entity, 'title', dest_chat_id)}")
    except Exception as e:
        print(f"WARNING: Could not verify destination chat: {e}")
        retry = input("Continue anyway? (y/n): ").lower().strip()
        if retry != 'y':
            print("Aborting.")
            await client.disconnect()
            return
    
    # Start forwarding messages
    try:
        await forward_messages(client, evan_group, dest_chat_id)
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        logger.error(f"Error streaming from group: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript stopped by user.") 