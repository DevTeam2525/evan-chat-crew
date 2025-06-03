import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import User

# IMPORTANT NOTE: 
# To fix verbose bot responses, edit your bot personality settings in bot_handler.py or personalities.py
# and add max_tokens or response_length constraints to keep responses short (< 50 words)
# Check generate_response() method in bot_handler.py and add length limits

# EVAN group ID (from previous run)
EVAN_GROUP_ID = 2341551550
DESTINATION_ID = -1002561226994

# Create an extremely simple client
async def main():
    print("Starting minimal EVAN group listener...")
    
    # Use existing session to avoid login
    client = TelegramClient('session_stream_joins', '22589967', '3928a608ba40e683e1cf54d0403f47ca')
    await client.start()


    print(f"Connected to Telegram")
    print(f"Listening ONLY to EVAN group (ID: {EVAN_GROUP_ID})")
    print(f"Forwarding messages to: {DESTINATION_ID}")
    print("Waiting for messages... (Ctrl+C to exit)")
    
    # ONLY listen to the specific EVAN group
    @client.on(events.NewMessage(chats=EVAN_GROUP_ID))
    async def handler(event):
        if not event.message.text:
            return
        
        try:
            sender = await event.get_sender()
            sender_name = sender.username or f"{sender.first_name} {sender.last_name or ''}".strip() if isinstance(sender, User) else "Unknown"
            
            print(f"\nNew message from {sender_name}: {event.message.text[:50]}...")
            
            # Forward to destination with header
            formatted_message = f"💰 FORWARDED FROM $EVAN | LORD OF DEGENS 💰\n\n{sender_name}: {event.message.text}"
            await client.send_message(DESTINATION_ID, formatted_message)
            print("✅ Message forwarded")
            
        except Exception as e:
            print(f"Error handling message: {e}")
    
    # Just keep the connection alive
    while True:
        await asyncio.sleep(10)
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript stopped by user.") 