import logging
import os
import random
import time
import asyncio  # Needed for creating event loops in threads
from collections import defaultdict # Added for grouping reports
from queue import Queue # Keep standard queue for inter-thread comm if needed elsewhere, but coordination uses asyncio Queue
from telegram import Bot
from telegram.ext import Application, ApplicationBuilder, MessageHandler, filters
from dotenv import load_dotenv
import re
from telegram.ext import CommandHandler  # Add import for command handling
import datetime

from shared_memory import SharedMemory
from web_search import WebSearchService
from conversation_manager import ConversationManager
from bot_handler import BotHandler
# Import web_storage instead of web_content_storage
import web_storage

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram settings
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BOT1_TOKEN = os.getenv("BOT1_TOKEN")
BOT2_TOKEN = os.getenv("BOT2_TOKEN")
BOT3_TOKEN = os.getenv("BOT3_TOKEN")

# API keys
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
CLAUDE_KEY = os.getenv("CLAUDE_API_KEY")
PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY")
TWITTER_KEY = os.getenv("TWITTER_API_KEY")

# --- Coordination Constants ---
INTEREST_REPORT_TIMEOUT = 2.0 # Seconds to wait for interest reports

# Global dictionary to store pending interest reports (using asyncio primitives)
pending_interest_reports = defaultdict(lambda: {"reports": {}, "timer_handle": None}) # Use asyncio handle

# Using asyncio Queue for interest reports
interest_report_queue = asyncio.Queue()

# Queue for bot notifications
notification_queue = Queue()

# Global lock for scheduled conversations
scheduled_conversation_lock = asyncio.Lock()
# Global set to track recently used topics across ALL bots - properly initialize as empty set
recent_global_topics = set()

# Content freshness settings
CONTENT_MAX_AGE_DAYS = 4  # Maximum age for content to be considered "recent"

# Content retention settings
WEB_CONTENT_MAX_AGE_DAYS = 14  # Keep web content for up to 14 days
WEB_CONTENT_CLEANUP_HOURS = 12  # Run cleanup every 12 hours

# Helper functions for bot name and content analysis
def is_bot_name_mentioned(bot_id, message_text, bots):
    """Check if a bot's name or nickname is mentioned in a message."""
    if not message_text or not bot_id in bots:
        return False
        
    message_text_lower = message_text.lower()
    bot = bots[bot_id]
    
    # Check for full name
    bot_name_lower = bot.personality['name'].lower()
    if bot_name_lower in message_text_lower:
        return True
        
    # Check for short name/nickname based on bot ID
    if bot_id == 'bot1':  # BTC Max
        return 'max' in message_text_lower.split() or 'btc' in message_text_lower.split()
    elif bot_id == 'bot2':  # $EVAN
        return 'evan' in message_text_lower.split() or '$evan' in message_text_lower.split()
    elif bot_id == 'bot3':  # Goldilocks
        return 'goldy' in message_text_lower.split() or 'goldilocks' in message_text_lower.split()
        
    return False

def personality_mentions_bot(message_text, bot_id, bots):
    """More flexible check for content that would indicate a specific bot."""
    if not message_text or not bot_id in bots:
        return False
        
    message_lower = message_text.lower()
    
    # Custom checks for each bot based on their personality traits/topics
    if bot_id == 'bot1':  # BTC Max
        btc_indicators = ['bitcoin', 'btc', 'crypto', 'trading', 'hodl', 'chart', 
                         'conference', 'wharton', 'miami', 'tesla', 'f1']
        return any(indicator in message_lower for indicator in btc_indicators)
        
    elif bot_id == 'bot2':  # $EVAN
        evan_indicators = ['liquidity', 'cat', 'degen', 'storage', 'unit', 'hobo', 
                          'ramen', 'energy drink', 'rugpull', 'rug', 'wallet']
        return any(indicator in message_lower for indicator in evan_indicators)
        
    elif bot_id == 'bot3':  # Goldilocks
        goldy_indicators = ['gold', 'kids', 'family', 'children', 'goldilocks', 'balance', 
                           'portfolio', 'husband', 'david', 'emma', 'jackson', 'lily']
        return any(indicator in message_lower for indicator in goldy_indicators)
        
    return False

async def coordinate_user_responses(bots, shared_memory, web_search):
    """Coordinates bot responses based on reported interest levels using asyncio."""
    while True:
        try:
            report = await interest_report_queue.get() # Use await with asyncio queue
            message_id = report["message_id"]
            bot_id = report["bot_id"]
            
            # Extract message information for spam checking
            message_text = report.get("message_text", "").lower()
            username = report.get("username", "")
            
            # SUPER AGGRESSIVE EVAN PROTECTION
            # Never let Evan bot respond to messages with suspicious patterns, even if they got past other filters
            if bot_id == "bot2" and ("evan" in message_text or "$evan" in message_text):
                suspicious_terms = ["raid", "forward", "boost", "vote", "promotion", "bot", "airdrop"]
                if any(term in message_text for term in suspicious_terms):
                    logger.warning(f"CRITICAL EVAN PROTECTION: Blocked interest report for message {message_id} from {username} with suspicious content")
                    interest_report_queue.task_done() # Mark task done for asyncio queue
                    continue # Skip processing this report
            
            logger.info(f"Received interest report for msg {message_id} from {bot_id}: interested={report['is_interested']}")

            # Store the report
            message_reports = pending_interest_reports[message_id]
            message_reports["reports"][bot_id] = report
            
            # If this is the first report for this message, start an asyncio timer
            if message_reports["timer_handle"] is None:
                logger.info(f"Starting response coordination timer for msg {message_id}")
                loop = asyncio.get_running_loop()
                # Use call_later for async delay
                message_reports["timer_handle"] = loop.call_later(
                    INTEREST_REPORT_TIMEOUT,
                    lambda: asyncio.create_task( # Schedule the processing as a task
                        process_message_interest_after_delay(message_id, bots, shared_memory, web_search)
                    )
                )
                
            interest_report_queue.task_done() # Mark task done for asyncio queue
        except Exception as e:
             logger.error(f"Error in coordinate_user_responses: {e}", exc_info=True)
             await asyncio.sleep(1) # Avoid busy-looping on error

async def process_message_interest_after_delay(message_id, bots, shared_memory, web_search):
    """Processes collected interest reports after a delay using asyncio."""
    try:
        # Get the pending reports for this message
        reports = pending_interest_reports.get(message_id, {"reports": {}})["reports"]
        
        # Get the first report to extract common information (all reports have same message)
        if not reports:
            logger.warning(f"No interest reports found for msg {message_id} when timer fired")
            return
            
        # Extract message information from the first report (any will do)
        first_report = next(iter(reports.values()))
        user_id = first_report["user_id"]
        username = first_report["username"]
        message_text = first_report["message_text"]
        replied_to_message_id = first_report.get("replied_to_message_id")

        # COORDINATOR-LEVEL SPAM FILTER
        # Critical spam detection - absolutely ensure no spam sneaks through
        is_spam = False
        # Intensive spam patterns that must never receive responses
        spam_patterns = [
            r"FORWARDED FROM.*",
            r".*Booosts?:.*",
            r".*RAID.*FOR.*EVAN.*",
            r".*raid.*",
            r".*raid.*evan.*",
            r".*evan.*raid.*",
            r".*💰 FORWARDED FROM.*",
            r".*\$EVAN \| LORD OF DEGENS.*",
            r".*evanraiderbot.*",
            r".*ruginaha:.*",
            r"FORWARDED MESSAGE",
            r".*FORWARDED MESSAGE.*",
            r".*t\.me/.*",                # Telegram links
            r".*https://x\.com/.*",       # X.com links
            r".*Likes \d+ \| \d+.*",      # Likes stats format
            r".*Retweets \d+ \| \d+.*",   # Retweets stats format
            r".*Replies \d+ \| \d+.*",    # Replies stats format
            r".*tg://resolve\?domain=.*", # Telegram resolve links
            # More focused URL patterns for common spam sites
            r".*airdrop.*\.com.*",
            r".*giveaway.*\.com.*",
            r".*promo.*\.com.*",
            r".*token.*sale.*\.com.*",
            r".*flooz\.io.*",
            r".*raydium\.io.*pump.*"
        ]
        
        # Check for key spam indicators
        for pattern in spam_patterns:
            if re.search(pattern, message_text, re.IGNORECASE):
                logger.warning(f"COORDINATOR SPAM FILTER: Message {message_id} from {username} blocked: '{message_text[:50]}...' (matched pattern: {pattern})")
                is_spam = True
                break
                
        # Additional spam detection - check for $EVAN mentions in suspicious contexts
        if not is_spam and ("$evan" in message_text.lower() or "evan" in message_text.lower()):
            suspicious_patterns = ["forwarded", "boost", "raid", "promotion", "vote", "bot", "airdrop", "giveaway"]
            if any(pattern in message_text.lower() for pattern in suspicious_patterns):
                logger.warning(f"COORDINATOR EVAN PROTECTION: Message {message_id} blocked due to suspicious $EVAN mention: '{message_text[:50]}...'")
                is_spam = True
        
        # Exit early if spam is detected - no bot will respond
        if is_spam:
            logger.info(f"Coordinator blocked all responses to message {message_id} due to spam detection")
            # Clear this message from pending reports
            if message_id in pending_interest_reports:
                del pending_interest_reports[message_id]
            return  # Exit early - spam message will be ignored by all bots
        
        # Check if any report has the personal question flag
        personal_question_reports = {bot_id: report for bot_id, report in reports.items() 
                                    if report.get("is_personal_question", False)}
        
        # If there are personal question reports, prioritize those bots
        if personal_question_reports:
            logger.info(f"Msg {message_id} has {len(personal_question_reports)} personal question reports")
            # If a personal question is directed to specific bots, those bots should respond
            responding_bots = list(personal_question_reports.keys())
            assignment_reason = "personal_question"
            
            for bot_id in responding_bots:
                try:
                    bot = bots[bot_id]
                    # Create task for sending response (don't block coordination loop)
                    asyncio.create_task(
                        bot.generate_and_send_response_async(
                            user_id=user_id, 
                            username=username, 
                            message_text=message_text, 
                            reply_to_message_id=message_id,
                            assignment_reason=assignment_reason
                        )
                    )
                    logger.info(f"Scheduled personal response from bot {bot_id} to msg {message_id}")
                except Exception as e:
                    logger.error(f"Failed to assign response to bot {bot_id}: {e}", exc_info=True)
            
            # Clear this message from pending reports
            if message_id in pending_interest_reports:
                del pending_interest_reports[message_id]
                
            return  # Exit early - we've handled the personal question

        # Track which bot(s) will respond to avoid duplicates
        responding_bots = []
        
        # --- Helper functions for message processing --- 
        
        # Helper function to check for general requests
        def is_general_request(text):
            text_lower = text.lower().strip()
            
            # 1. Check for explicit request phrases - expanded list
            request_phrases = [
                "can someone", "can anyone", "anyone know", "get me", "find me", "show me", 
                "check on", "tell me", "look up", "search for", "what are", "whats", "what's",
                "what is happening", "what's happening", "whats happening",
                "what is going on", "what's going on", "whats going on",
                "update on", "latest on", "news from", "news on", "anything new",
                "any news", "so any", "give me", "who knows", "you guys",
                "what about", "trenches", "updates", "anyone here", "somebody",
                # CRITICAL: Add more search/look up terms
                "search", "look up", "find", "get info", "information on", "details about",
                "latest news", "recent news", "news about", "news now", "rugs", "rug pulls",
                "find news", "search news", "get news", "crypto news"
            ]
            
            if any(phrase in text_lower for phrase in request_phrases):
                logger.info(f"General request detected: '{text}' contains request phrase")
                return True
                
            # 2. Check for common question words/starters (as whole words)
            question_starters = ["what", "how", "who", "where", "why", "when", "is", "are", "can", "could", "do", "does", "has", "have", "should", "would"]
            words = text_lower.split()
            first_word = words[0] if words else ""
            
            if first_word in question_starters:
                logger.info(f"General request detected: '{text}' starts with question word '{first_word}'")
                return True
                
            # 3. Check for final question mark (less reliable in chat)
            if text.endswith("?"):
                logger.info(f"General request detected: '{text}' ends with question mark")
                return True
                
            # 4. Check for "trenches" specific mentions (very specific to this system)
            if "trenches" in text_lower:
                logger.info(f"General request detected: '{text}' mentions trenches")
                return True
            
            # 5. Very short messages that look like prompts (2-5 words)
            if 2 <= len(words) <= 5:
                # Check if it's likely a command/request based on structure
                # e.g., "price check" or "market update"
                if not any(word in ["hi", "hello", "hey", "lol", "haha", "nice", "cool", "wow"] for word in words):
                    logger.info(f"General request detected: '{text}' is a short prompt-like message")
                    return True
                
            return False

        # --- START: Check for $EVAN special case --- 
        if "$evan" in message_text.lower() and "bot2" in bots:
            # Special case - ALWAYS let Evan respond if $EVAN token is mentioned
            # (regardless of any other routing considerations)
            # BUT ONLY if it's not in a spam context (which we've already checked)
            responding_bots = ["bot2"]
            assignment_reason = "$evan_token_mention"
            logger.info(f"Msg {message_id}: Responding with bot2 due to $EVAN token mention")

        # --- START: Reply to Bot Check ---
        # Check if the message is a reply to another message
        elif replied_to_message_id:
            logger.info(f"Msg {message_id} is a reply to message {replied_to_message_id}. Finding which bot sent it...")
            # Find which bot sent the message being replied to
            # CRITICAL FIX: Substantially increase history lookup for replies
            recent_conversations = shared_memory.get_recent_conversations(500)  # Increased from 100 to 500
            replied_to_bot_id = None
            
            # First check the actual database for who sent this message
            for msg in recent_conversations:
                if msg.get("message_id") == replied_to_message_id:
                    # Store sender ID regardless of whether it's a bot or not
                    sender_type = msg.get("sender_type")
                    sender_id = msg.get("sender_id")
                    if sender_type == "bot" and sender_id:
                        replied_to_bot_id = sender_id
                        logger.info(f"Found that message {replied_to_message_id} was sent by bot {replied_to_bot_id}")
                        break
                    elif sender_type == "user":
                        logger.info(f"Message {replied_to_message_id} was sent by user {sender_id}, not a bot")
                        # Continue searching in case we have multiple messages with the same ID (shouldn't happen, but safety check)
            
            # NEW: Additional lookup for missing messages
            if not replied_to_bot_id:
                # Try to find message by looking at newer messages with 'in_reply_to' fields
                for msg in recent_conversations:
                    if msg.get("in_reply_to") == replied_to_message_id and msg.get("sender_type") == "bot":
                        # This message was a reply to our target, so its sender might know who sent the original
                        logger.info(f"Found a reply chain reference: message {msg.get('message_id')} was replying to {replied_to_message_id}")
                        for bot_id in bots:
                            # Extra safety - check who most likely sent this message
                            if f"message from {bot_id}" in message_text.lower() or \
                               is_bot_name_mentioned(bot_id, message_text, bots):
                                replied_to_bot_id = bot_id
                                logger.info(f"Inferred that message {replied_to_message_id} was likely from {bot_id} based on message content")
                                break
            
            # If we found which bot was being replied to, they MUST respond (highest priority after $EVAN)
            if replied_to_bot_id and replied_to_bot_id in bots:
                # Give higher priority to replies to BTC Max
                if replied_to_bot_id == "bot1":
                    logger.info(f"Msg {message_id}: HIGH PRIORITY - User is directly replying to BTC Max's message {replied_to_message_id}")
                    responding_bots = ["bot1"]
                    assignment_reason = "direct_reply_to_btcmax"
                elif replied_to_bot_id == "bot2":  # Add special priority for $EVAN replies too
                    logger.info(f"Msg {message_id}: HIGH PRIORITY - User is directly replying to $EVAN's message {replied_to_message_id}")
                    responding_bots = ["bot2"]
                    assignment_reason = "direct_reply_to_evan"
                elif replied_to_bot_id == "bot3":  # Add special priority for Goldilocks replies too
                    logger.info(f"Msg {message_id}: HIGH PRIORITY - User is directly replying to Goldilocks' message {replied_to_message_id}")
                    responding_bots = ["bot3"]
                    assignment_reason = "direct_reply_to_goldilocks"
                else:
                    logger.info(f"Msg {message_id}: DIRECT REPLY - User is replying to {replied_to_bot_id}'s message")
                    responding_bots = [replied_to_bot_id] 
                    assignment_reason = "direct_reply_to_bot"
                    
                # CRITICAL FIX: Immediately schedule the response for the bot being replied to
                # AND ENSURE THIS ALWAYS RUNS FOR REPLIES
                bot_id = responding_bots[0]
                if bot_id in bots:
                    logger.info(f"PRIORITY REPLY HANDLING: User is replying directly to {bot_id}, scheduling immediate response")
                    try:
                        bot = bots[bot_id]
                        asyncio.create_task(
                            bot.generate_and_send_response_async(
                                user_id=user_id, 
                                username=username, 
                                message_text=message_text, 
                                reply_to_message_id=message_id,
                                assignment_reason=assignment_reason
                            )
                        )
                        logger.info(f"Scheduled direct reply response from {bot_id} to msg {message_id}")
                        
                        # Clear this message from pending reports
                        if message_id in pending_interest_reports:
                            del pending_interest_reports[message_id]
                            
                        return  # Exit early - we've handled the direct reply
                    except Exception as e:
                        logger.error(f"Failed to assign direct reply response to {bot_id}: {e}", exc_info=True)
                        # If this fails, let processing continue to other methods
                        # This way we still have a chance to handle the message
            else:
                logger.info(f"Couldn't identify which bot sent message {replied_to_message_id} or bot not available")
                # NEW: Content-based fallback for unidentified replies
                # If we can't identify the bot but the message clearly indicates which bot to reply to
                for bot_id, bot in bots.items():
                    bot_name = bot.personality["name"]
                    if bot_name.lower() in message_text.lower() or bot_id.lower() in message_text.lower():
                        logger.info(f"Content-based fallback: Message mentions {bot_name}, assigning to {bot_id}")
                        responding_bots = [bot_id]
                        assignment_reason = "content_mention_fallback"
                        break
        # --- END: Reply to Bot Check ---

        # --- START: Bot Name Mention Routing ---
        # Only check if neither $evan rule nor direct reply applied
        elif not responding_bots:
            mentioned_bots = []
            message_text_lower = message_text.lower()
            # Check *all* bots passed to the coordinator, not just those in `reports`
            for bot_id, bot in bots.items():
                # Use the new name detection helper
                if is_bot_name_mentioned(bot_id, message_text, bots):
                    if bot_id not in mentioned_bots:
                        mentioned_bots.append(bot_id)
                
            # --- Mention Decision Logic ---        
            if len(mentioned_bots) == 1: # Exactly one bot mentioned
                mentioned_bot_id = mentioned_bots[0]
                # No need to check if bot exists here, we iterated through existing bots
                logger.info(f"Msg {message_id}: Prioritizing bot {mentioned_bot_id} due to single name mention.")
                responding_bots = [mentioned_bot_id]
                assignment_reason = "name_mention"
            elif len(mentioned_bots) > 1:
                # If multiple bots mentioned, prioritize all mentioned bots (change from previous behavior)
                logger.info(f"Msg {message_id}: Multiple bots mentioned ({', '.join(mentioned_bots)}). All mentioned bots will respond.")
                responding_bots = mentioned_bots
                assignment_reason = "multiple_name_mentions"
            # else: len == 0 -> No mentions, proceed to interest check
            
        # --- END: Bot Name Mention Routing ---

        # --- START: Interest-Based Routing (Runs if no other rules applied) --- 
        elif not responding_bots:
            # Find bots that reported interest based on topic/keywords
            # Now we use the original reports dictionary
            truly_interested_bots = [bot_id for bot_id, report in reports.items() if report["is_interested"]] 

            if truly_interested_bots:
                # Apply priority if multiple bots are interested
                if "bot1" in truly_interested_bots:
                    logger.info(f"Msg {message_id}: Prioritizing interested bot: bot1 (BTC Max)")
                    responding_bots = ["bot1"]
                    assignment_reason = "interest_priority_bot1"
                elif "bot3" in truly_interested_bots:
                    logger.info(f"Msg {message_id}: Prioritizing interested bot: bot3 (Goldilocks)")
                    responding_bots = ["bot3"]
                    assignment_reason = "interest_priority_bot3"
                elif "bot2" in truly_interested_bots:
                    # Handles case where Evan was interested for reasons other than $evan mention or general request trigger
                    logger.info(f"Msg {message_id}: Prioritizing interested bot: bot2 (Evan)")
                    responding_bots = ["bot2"]
                    assignment_reason = "interest_priority_bot2"
                else: 
                    # Should not happen if truly_interested_bots is not empty, but fallback just in case
                    logger.warning(f"Msg {message_id}: Interested bots found ({truly_interested_bots}), but priority logic failed. Assigning first.")
                    responding_bots = [truly_interested_bots[0]] 
        # --- END: Interest-Based Routing ---

        # --- START: General Request Routing (Only if no other rule applied) --- 
        if not responding_bots:
            # CRITICAL FIX: Check for general requests much earlier
            # and make sure we always route them
            if is_general_request(message_text):
                logger.info(f"Msg {message_id}: Detected general request - '{message_text}'")
                
                # CRITICAL FIX: Prioritize Evan (bot2) for most general requests,
                # but sometimes assign to other bots for variety
                assignment_choice = random.random()
                if assignment_choice < 0.7 and "bot2" in bots:  # 70% of the time, assign to Evan
                    logger.info(f"Msg {message_id}: Assigning general request to Evan (bot2)")
                    responding_bots = ["bot2"]
                    assignment_reason = "general_request"
                elif assignment_choice < 0.85 and "bot1" in bots:  # 15% to BTC Max
                    logger.info(f"Msg {message_id}: Assigning general request to BTC Max (bot1)")
                    responding_bots = ["bot1"]
                    assignment_reason = "general_request"
                elif "bot3" in bots:  # 15% to Goldilocks
                    logger.info(f"Msg {message_id}: Assigning general request to Goldilocks (bot3)")
                    responding_bots = ["bot3"]
                    assignment_reason = "general_request"
                else:  # Fallback if specific bot not available
                    # Just pick a random bot that exists
                    available_bot_ids = list(bots.keys())
                    if available_bot_ids:
                        random_bot = random.choice(available_bot_ids)
                        logger.info(f"Msg {message_id}: Assigning general request to random bot {random_bot}")
                        responding_bots = [random_bot]
                        assignment_reason = "general_request_fallback"
            # Additional fallback: for very short messages with no other context, let Evan respond 30% of the time
            elif len(message_text.split()) <= 5 and "bot2" in bots and random.random() < 0.3:
                logger.info(f"Msg {message_id}: Assigning short message to Evan (bot2) at random.")
                responding_bots = ["bot2"]
                assignment_reason = "random_short_message_fallback"
        # --- END: General Request Routing ---

        # --- Final Check: If no bot selected, do nothing --- 
        if not responding_bots:
            # IMPROVED REPLY FALLBACK: Make a much more extensive check for replies
            # This catches any replies to bots that might have been missed in the earlier logic
            if replied_to_message_id:
                # Do a more thorough and direct lookup with looser matching criteria
                recent_conversations = shared_memory.get_recent_conversations(1000)  # Check MANY more messages
                
                # First, standard message ID lookup with looser criteria
                for msg in recent_conversations:
                    if msg.get("message_id") == replied_to_message_id and msg.get("sender_type") == "bot":
                        replied_to_bot_id = msg.get("sender_id")
                        if replied_to_bot_id and replied_to_bot_id in bots:
                            logger.info(f"REPLY FALLBACK: Msg {message_id} is a reply to bot {replied_to_bot_id} that was missed. Ensuring response.")
                            responding_bots = [replied_to_bot_id]
                            assignment_reason = "direct_reply_fallback"
                
                # If still not found, check content of message for bot-specific keywords
                if not responding_bots:
                    # Check if message clearly references a specific bot
                    for bot_id in bots:
                        if is_bot_name_mentioned(bot_id, message_text, bots) or personality_mentions_bot(message_text, bot_id, bots):
                            logger.info(f"REPLY CONTENT FALLBACK: Message refers to {bot_id}'s traits/name. Ensuring they respond.")
                            responding_bots = [bot_id]
                            assignment_reason = "content_reference_fallback"
                            break
                    
                    # Special case for messages about Liquidity the cat - always assign to Evan
                    if not responding_bots and "liquidity" in message_text.lower() and "cat" in message_text.lower() and "bot2" in bots:
                        logger.info(f"SPECIAL FALLBACK: Message refers to Liquidity the cat. Ensuring Evan responds.")
                        responding_bots = ["bot2"]
                        assignment_reason = "liquidity_cat_fallback"
                    
                    # If still nothing, check for exact phrases that commonly appear in replies
                    if not responding_bots:
                        reply_phrases = [
                            "glad you", "why did you", "how did you", "tell me more", "when did you",
                            "where did you", "glad to hear", "that's great", "that's good", "congratulations",
                            "congrats", "thanks for", "thank you for", "appreciate your", "interesting point",
                            "good point", "nice to hear", "sorry to hear", "that's too bad"
                        ]
                        if any(phrase in message_text.lower() for phrase in reply_phrases) and "bot2" in bots:
                            logger.info(f"COMMON REPLY PHRASE FALLBACK: Message contains reply phrases. Assigning to Evan as default.")
                            responding_bots = ["bot2"]
                            assignment_reason = "reply_phrase_fallback"
            
            # CRITICAL FIX: Final fallback for search and news requests
            # If we STILL don't have responding bots, check for specific search keywords
            if not responding_bots:
                search_keywords = ["search", "find", "look up", "check", "news", "info", 
                                  "current", "latest", "update", "price", "rugs", "status"]
                
                message_words = message_text.lower().split()
                if any(keyword in message_words for keyword in search_keywords):
                    logger.info(f"SEARCH FALLBACK: Detected search-like keywords. Ensuring a bot responds.")
                    # Assign to a bot that can handle searches well, prioritizing Evan
                    if "bot2" in bots:
                        responding_bots = ["bot2"]
                        assignment_reason = "search_keyword_fallback"
                    elif "bot1" in bots:
                        responding_bots = ["bot1"]
                        assignment_reason = "search_keyword_fallback"
                    elif "bot3" in bots:
                        responding_bots = ["bot3"]
                        assignment_reason = "search_keyword_fallback"
            
            # If still no responding bots, log and exit
            if not responding_bots:
                logger.info(f"Msg {message_id}: No specific trigger ($evan, mention, interest, general request). Ignoring message.")
                return # Exit the function, no response needed

        # Trigger the selected bot(s) to respond using asyncio tasks
        response_tasks = []
        # Ensure responding_bots is not empty before proceeding
        if responding_bots: 
            for bot_id in responding_bots:
                if bot_id in bots:  # Add this check to prevent KeyError
                    bot = bots[bot_id]
                    logger.info(f"Instructing bot {bot_id} to respond to msg {message_id} (Reason: {assignment_reason})")
                    # Create an asyncio task to run the async response generation
                    task = asyncio.create_task(
                        bot.generate_and_send_response_async(
                            user_id=user_id, 
                            username=username, 
                            message_text=message_text, 
                            reply_to_message_id=message_id,
                            assignment_reason=assignment_reason
                        )
                    )
                    response_tasks.append(task)
                else:
                    logger.warning(f"Bot {bot_id} not found in bots dictionary")

        # Optionally wait for all responses to complete (or handle errors)
        if response_tasks:
            try:
                await asyncio.gather(*response_tasks)
                logger.info(f"All response tasks for msg {message_id} completed.")
            except Exception as e:
                logger.error(f"Error occurred during bot response generation/sending for msg {message_id}: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error in process_message_interest_after_delay: {e}", exc_info=True)

# --- End Coordination Logic ---

def process_bot_notifications(notification, bots, shared_memory, loop):
    """Process notifications about conversations and decide if other bots should join."""
    initiator_id = notification["initiator_bot_id"]
    user_message = notification.get("user_message", "")
    bot_response = notification.get("bot_response", "")
    bot_message_id = notification.get("bot_message_id")
    
    # Determine if this is a response to another bot (vs. a user)
    is_bot_to_bot_response = notification.get("in_reply_to_bot", False)
    
    # Get conversation chain so far
    conversation_chain = notification.get("conversation_chain", [])
    if not is_bot_to_bot_response:
        # Start a new chain if this is the first bot response to a user
        conversation_chain = [initiator_id]
    
    # Track how many exchanges have happened in this chain
    chain_length = len(conversation_chain)
    logger.info(f"Processing notification from {initiator_id} - chain length: {chain_length}")
    
    # Set higher chance of response for longer chains to encourage continued conversations
    # But also add a decay factor to prevent infinite back-and-forth
    if chain_length <= 3:
        base_response_chance = 0.35  # 35% chance for short chains
    elif chain_length <= 6:
        base_response_chance = 0.25  # 25% chance for medium chains
    else:
        base_response_chance = 0.15  # 15% chance for long chains
    
    # Combined content for interest checking
    combined_text = f"{user_message} {bot_response}"
    content_for_interest_check = {"source": "user", "content": combined_text}
    
    # For each other bot
    responding_bots = []
    for bot_id, bot in bots.items():
        if bot_id != initiator_id and bot_id not in conversation_chain[-2:]:  # Avoid same bot responding twice in a row
            # Determine if this bot is interested in the conversation
            should_join = False
            
            # Check if relevant content matches bot interests
            if bot.conversation_manager.is_topic_interesting(bot_id, content_for_interest_check):
                interest_boost = 0.2  # Boost chance by 20% if topic is interesting
                should_join = random.random() < (base_response_chance + interest_boost)
                if should_join:
                    logger.info(f"Bot {bot_id} interested in topic from bot {initiator_id}")
            else:
                # Random chance to join anyway
                should_join = random.random() < base_response_chance
            
            if should_join:
                responding_bots.append(bot_id)
    
    # Limit number of responding bots based on chain length
    # Allow more bots to join early in the conversation
    max_responding_bots = max(1, 3 - (chain_length // 2))
    if len(responding_bots) > max_responding_bots:
        # If we need to limit, prioritize bots not yet in the conversation chain
        new_bots = [b for b in responding_bots if b not in conversation_chain]
        if new_bots and len(new_bots) <= max_responding_bots:
            responding_bots = new_bots
        else:
            # Otherwise randomly sample
            responding_bots = random.sample(responding_bots, max_responding_bots)
    
    # Process each responding bot
    for bot_id in responding_bots:
        bot = bots[bot_id]
        # Wait a realistic time before responding
        time.sleep(random.randint(4, 12))  # Slightly shorter delay
        
        # Update conversation chain for this responder
        bot_chain = conversation_chain.copy()
        bot_chain.append(bot_id)
        
        # Fetch conversation history for context
        conversation_history = shared_memory.get_recent_conversations(30) # Standard limit

        # Generate a response that builds on the conversation
        prompt_data = {
            "is_conversation_response": True,
            "user_name": notification.get("username", "User"),
            "user_message": user_message,
            "other_bot_name": bots[initiator_id].personality["name"],
            "other_bot_response": bot_response,
            "message": bot_response,
            "relevant_content": notification.get("relevant_content", []),
            "conversation_chain": bot_chain,  # Include the chain for context
            "chain_length": chain_length,     # Current length of the chain
            "conversation_history": conversation_history,
            # CRITICAL FIX: Force detailed personality in ALL bot interactions
            "use_complete_backstory": True,
            "force_detailed_personality": True,
            "full_personality_required": True,
            # IMPORTANT: Keep uniqueness flags to ensure distinct voices
            "force_personality_uniqueness": True,
            "responding_to_bot": True,
            # Add special instruction to ensure personality uniqueness
            "personality_instruction": f"""You are {bot.personality['name']} with your UNIQUE personality traits. 

CRITICAL IDENTITY AND VISIBILITY RULES:
1. You are RESPONDING ONLY to {bots[initiator_id].personality['name']}'s visible message: "{bot_response}"
2. DO NOT reference or respond to any "seed" or "query" that isn't directly visible in the conversation
3. ONLY respond to what {bots[initiator_id].personality['name']} actually said in their message
4. {bots[initiator_id].personality['name']} is a DIFFERENT PERSON from you with their own separate life
5. Their backstory details (job, home, family, education) belong to THEM, not you
6. YOUR backstory details belong ONLY to you
7. NEVER refer to yourself in the third person
8. NEVER claim another bot's personal details as your own

CRITICAL CONVERSATION RULES - AVOID REPETITION:
1. DO NOT repeat or paraphrase what the other bot just said - this creates unnatural conversations
2
3. DO NOT summarize or restate their message before giving your response
4. NEVER begin with phrases like "{bots[initiator_id].personality['name']} mentioned..." or "So you're talking about..."
5. Instead, respond directly to their ideas without repeating their exact words or phrasing
6. Keep your own distinct voice, vocabulary, and perspective in your response
7. Add NEW information or your own unique take rather than echoing their statement
8. Begin your response with your own thoughts, not a restatement of theirs

For example:
- If you are Goldilocks: David is YOUR husband, Emma/Jackson/Lily are YOUR children
- If you are BTC Max: Ellie is YOUR sister, YOU live in Miami
- If you are $EVAN: Liquidity is YOUR cat, YOU live in a storage unit

Make your response natural and conversational. Respond ONLY to what {bots[initiator_id].personality['name']} actually said.
""",
            # NEW: Add content date information for context
            "content_date": notification.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d")),
            "content_freshness_note": "IMPORTANT: Only discuss this as current news if the date is within the last few days."
        }
        
        # Generate response using asyncio.run_coroutine_threadsafe
        try:
            future_response = asyncio.run_coroutine_threadsafe(
                bot.generate_response(prompt_data),
                loop
            )
            response = future_response.result(timeout=30)
        except Exception as e:
            logger.error(f"Error generating notification response for bot {bot_id}: {e}", exc_info=True)
            continue
        
        # Send message using asyncio.run_coroutine_threadsafe
        try:
            # FIXED: Don't try to directly reply to other bot messages because bots can't see each other
            # in Telegram. Instead, store relationship in shared memory.
            reply_to = None  # No direct reply in Telegram - the bots can't see each other
            
            future_send = asyncio.run_coroutine_threadsafe(
                bot.send_message(response, reply_to_message_id=reply_to),
                loop
            )
            sent_msg_id = future_send.result(timeout=15)
            if sent_msg_id == -1:
                logger.error(f"Failed to send notification message from bot {bot_id}.")
                continue
        except Exception as e:
            logger.error(f"Error sending notification message for bot {bot_id}: {e}", exc_info=True)
            continue

        # Store in shared memory with reference to the message it's conceptually replying to
        response_data = {
            "sender_type": "bot",
            "sender_id": bot_id,
            "sender_name": bot.personality["name"],
            "message": response,
            "message_id": sent_msg_id,
            "in_reply_to": bot_message_id,  # This is for logical tracking in shared memory only
            "in_conversation_with": conversation_chain,
            "referenced_content": [c.get("query") for c in notification.get("relevant_content", [])],
            "timestamp": time.time()
        }
        shared_memory.add_conversation(response_data)
        logger.info(f"Bot {bot_id} joined conversation started by {initiator_id} (msg {sent_msg_id})")
        
        # Create a new notification for THIS bot's response to continue the chain
        new_notification = {
            "type": "conversation_notification",
            "initiator_bot_id": bot_id,
            "initiator_name": bot.personality["name"],
            "user_message": user_message,  # Original user message stays the same
            "bot_response": response,      # Current bot's response
            "user_id": notification.get("user_id"),
            "username": notification.get("username"),
            "bot_message_id": sent_msg_id,
            "relevant_content": notification.get("relevant_content", []),
            "in_reply_to_bot": True,       # Mark this as bot-to-bot
            "conversation_chain": bot_chain,  # Pass updated chain
            "timestamp": time.time(),
            # CRITICAL FIX: Always include conversation history in notifications
            "conversation_history": conversation_history
        }
        
        try:
            if notification_queue:
                notification_queue.put_nowait(new_notification)
                logger.debug(f"Bot {bot_id} created a new notification (chain length {len(bot_chain)})")
        except Exception as e:
            logger.error(f"Failed to put new notification in queue: {e}")
            
        # Delay slightly between multiple bot responses
        if len(responding_bots) > 1:
            time.sleep(random.randint(2, 5))

async def run_scheduled_conversations(bots, conversation_manager, shared_memory):
    """Periodically check if bots should initiate conversations."""
    # Cleanup old topic entries on startup (anything older than 24 hours)
    shared_memory.cleanup_old_topics(hours=24)
    
    # Reference the global topic tracking set
    global recent_global_topics
    
    while True:
        try:
            # Get current chattiness level (default to high if not set)
            chattiness_level = shared_memory.get_system_setting("chattiness_level", "high")
            
            # Adjust conversation frequency based on chattiness level
            if chattiness_level == "high":
                # High chattiness (default behavior)
                delay_min, delay_max = 30, 90  # 30-90 seconds between checks
                initiation_chance = 0.9        # 90% chance to initiate
                max_responders = 2             # Up to 2 bots can respond to an initiation
            elif chattiness_level == "medium":
                # Medium chattiness
                delay_min, delay_max = 120, 240  # 2-4 minutes between checks
                initiation_chance = 0.6          # 60% chance to initiate
                max_responders = 1               # Only 1 bot responds to an initiation
            else:  # "low"
                # Low chattiness
                delay_min, delay_max = 300, 600  # 5-10 minutes between checks
                initiation_chance = 0.3          # 30% chance to initiate
                max_responders = 1               # Only 1 bot responds to an initiation
            
            # Sleep for the determined interval
            await asyncio.sleep(random.randint(delay_min, delay_max))
            
            # CRITICAL FIX: Added logging to debug scheduled conversations
            logger.info(f"Checking if bots should initiate scheduled conversation (chattiness: {chattiness_level})...")
            
            # CRITICAL FIX: Use a lock to ensure only ONE bot initiates a conversation at a time
            # This prevents multiple bots from initiating conversations about the same topic
            async with scheduled_conversation_lock:
                # Clear old topics from the global set (older than 60 minutes)
                current_time = time.time()
                # Use a more robust approach that won't fail on malformed tuples
                fresh_topics = set()
                for item in recent_global_topics:
                    try:
                        # Properly handle tuples with expected format (topic, timestamp)
                        if isinstance(item, tuple) and len(item) == 2:
                            topic, timestamp = item
                            # Keep only fresh topics (less than 60 minutes old)
                            if current_time - timestamp < 3600:
                                fresh_topics.add(item)
                    except Exception as e:
                        logger.warning(f"Skipping malformed topic entry: {item}, error: {e}")
                
                # Replace the set with only fresh, well-formed topics
                recent_global_topics = fresh_topics
                
                # Randomly select a bot to initiate
                bot_id = random.choice(list(bots.keys()))
                bot = bots[bot_id]
                
                # CRITICAL FIX: Force scheduled conversations more frequently to ensure web content is discussed
                # Use the chattiness-adjusted initiation chance
                should_initiate = await conversation_manager.should_initiate_conversation(bot_id)
                forced_initiate = random.random() < initiation_chance
                
                if should_initiate or forced_initiate:
                    logger.info(f"Bot {bot_id} decided to initiate conversation. Natural decision: {should_initiate}, Forced: {forced_initiate}")
                    
                    # CRITICAL FIX: Get conversation seed with topic tracking to prevent repetition
                    content = await conversation_manager.get_conversation_seed(bot_id)
                    
                    # NEW: Check content freshness for web content (not personal backstories)
                    content_type = content.get("source", "unknown")
                    if content_type != "personal_backstory":
                        # Check if content has a timestamp
                        content_timestamp = content.get("timestamp", 0)
                        content_age_days = (time.time() - content_timestamp) / (60*60*24)
                        
                        # For web content, ensure it's recent (max CONTENT_MAX_AGE_DAYS days old)
                        if content_age_days > CONTENT_MAX_AGE_DAYS:
                            logger.warning(f"Content '{content.get('query', 'unknown')}' is {content_age_days:.1f} days old - too old for use. Getting fallback personal story.")
                            # Force getting a personal story as fallback for outdated web content
                            content = await conversation_manager.get_conversation_seed(bot_id, force_personal_story=True)
                            content_type = content.get("source", "unknown")  # Update content type
                    
                    # CRITICAL FIX: Check if this topic was recently used
                    content_query = content.get("query", "unknown")
                    
                    # Normalize topic for comparison (lowercase, strip punctuation)
                    normalized_topic = re.sub(r'[^\w\s]', '', content_query.lower())
                    
                    # Check against recently used topics in shared memory (persistent across restarts)
                    is_duplicate, duplicate_info = shared_memory.is_topic_recently_used(content_query, minutes=30)
                    
                    # Also check against our in-memory global topic set - with robust error handling
                    global_duplicate = False
                    for item in recent_global_topics:
                        try:
                            # Make sure the item is a tuple with the expected format
                            if isinstance(item, tuple) and len(item) == 2:
                                existing_topic, _ = item
                                # Simple substring check
                                if normalized_topic in existing_topic or existing_topic in normalized_topic:
                                    global_duplicate = True
                                    logger.info(f"Found duplicate topic in global set: '{normalized_topic}' matches '{existing_topic}'")
                                    break
                        except Exception as e:
                            logger.warning(f"Error checking topic duplicate: {e}")
                            continue
                    
                    # If duplicate detected AND it was a web content seed, try to get a personal story instead
                    if (is_duplicate or global_duplicate) and content_type != "personal_backstory":
                        if is_duplicate:
                            duplicate_bot = duplicate_info.get("bot_id", "unknown")
                            duplicate_time = time.strftime('%H:%M:%S', time.localtime(duplicate_info.get("time", 0)))
                            logger.warning(f"Web topic '{content_query}' was recently used by {duplicate_bot} at {duplicate_time}. Attempting fallback to personal story for {bot_id}.")
                        else:
                            logger.warning(f"Web topic '{content_query}' is in recent global topics. Attempting fallback to personal story for {bot_id}.")
                        
                        # Force getting a personal story seed
                        content = await conversation_manager.get_conversation_seed(bot_id, force_personal_story=True)
                        content_query = content.get("query", "unknown") # Update query for logging
                        content_type = content.get("source", "unknown")   # Update type for logging
                        normalized_topic = re.sub(r'[^\w\s]', '', content_query.lower())
                        
                        # Re-check if the personal story itself is a duplicate
                        if content_type != "personal_backstory":
                            logger.error(f"Fallback to personal story for {bot_id} failed to provide a personal_backstory seed. Skipping turn.")
                            continue # Skip if fallback also fails to give a personal story
                        logger.info(f"Fallback successful: Bot {bot_id} will use personal story: '{content_query}'")

                    elif is_duplicate and content_type == "personal_backstory":
                        # This means the personal story itself was a duplicate according to shared_memory's general topic log
                        logger.warning(f"Personal story topic '{content_query}' for {bot_id} was flagged as recently used globally. Skipping to avoid repetition.")
                        continue
                    
                    # Topic is unique enough - add to tracking systems
                    if content_type != "personal_backstory":
                        # Add to persistent shared memory
                        shared_memory.add_recently_used_topic(bot_id, content_query)
                        # Add to our in-memory global set with current timestamp
                        recent_global_topics.add((normalized_topic, time.time()))
                    
                    # Log content chosen
                    content_date = content.get("date_str", "unknown date")
                    if content_type != "personal_backstory":
                        logger.info(f"Bot {bot_id} initiating with content type: {content_type}, query: {content_query}, date: {content_date}")
                    else:
                        logger.info(f"Bot {bot_id} initiating with content type: {content_type}, query: {content_query}")
                    
                    # Select a potential target bot (optional)
                    other_bots = [b for b in bots.keys() if b != bot_id]
                    target_bot_id = random.choice(other_bots) if random.random() < 0.8 else None  # 80% chance to target another bot
                    
                    # CRITICAL FIX: Always use the enhanced prompt with full conversation history for ALL content types
                    # This ensures all responses have complete personality restrictions (no emojis, proper pricing, etc.)
                    
                    # Get conversation history for context
                    conversation_history = shared_memory.get_recent_conversations(30)
                    
                    # Create full-featured prompt data with conversation history for ALL content types
                    enhanced_prompt_data = {
                        "conversation_history": conversation_history,
                        "message": content_query,
                        "content": content,
                        "is_scheduled_initiation": True,
                        "initial_should_search": content_type != "personal_backstory",  # Only search for non-personal content
                        "target_bot_id": target_bot_id,
                        # CRITICAL FIX: Force detailed personality in ALL bot interactions
                        "use_complete_backstory": True,
                        "force_detailed_personality": True,
                        "full_personality_required": True,
                        # IMPORTANT: Keep uniqueness flags to ensure distinct voices
                        "force_personality_uniqueness": True,
                        "responding_to_bot": True,
                        # Add special instruction to ensure personality uniqueness
                        "personality_instruction": f"""You are {bot.personality['name']} with your UNIQUE personality traits. You must NEVER respond the same way as other bots. 

CRITICAL: You are STARTING a new conversation in the group chat. This means:
1. DO NOT reference or respond to the seed topic as if users can already see it
2. DO NOT phrase your message as a response to someone else
3. DO NOT refer to yourself in the third person - you ARE {bot.personality['name']}
4. NEVER refer to your own family/backstory details as if they belong to someone else
5. Your kids, spouse, pets, home, car, etc. are YOUR OWN, not another bot's

You are making a natural, initiating statement to the group that will be the FIRST message users see about this topic.
Make your response sound like YOU decided to share this information naturally, not like you're responding to a prompt.
""",
                        # NEW: Add content date information for context
                        "content_date": content.get("date_str", datetime.datetime.now().strftime("%Y-%m-%d")),
                        "content_freshness_note": "IMPORTANT: Only discuss this as current news if the date is within the last few days."
                    }
                    
                    # Use the enhanced prompt data regardless of content type
                    response = await bot.generate_response(enhanced_prompt_data)
                    sent_msg_id = await bot.send_message(response)
                    logger.info(f"Bot {bot_id} initiated conversation (msg {sent_msg_id}) using full prompt. Target: {target_bot_id or 'None'}")

                    # Store in shared memory
                    shared_memory.add_conversation({
                        "sender_type": "bot",
                        "sender_id": bot_id,
                        "sender_name": bot.personality["name"],
                        "message": response,
                        "message_id": sent_msg_id,
                        "content_source": content.get("source"),
                        "content_query": content.get("query"),
                        "target_bot_id": target_bot_id, # Bot it might be aimed at
                        "timestamp": time.time()
                    })
                    
                    # Wait for other bots to potentially respond (shorter wait times) 
                    await asyncio.sleep(random.randint(5, 15))  # 5-15 seconds to respond
                    
                    # Construct a simplified message dict for should_respond_to_conversation
                    initiator_message_context = {
                         "sender_id": bot_id,
                         "content": content,
                         "target_bot_id": target_bot_id,
                         "message": response # The actual text sent
                    }

                    # Determine how many bots should respond, adjusted for chattiness level
                    if chattiness_level == "high":
                        response_weights = [0.2, 0.5, 0.3]  # 20% none, 50% one, 30% two
                    elif chattiness_level == "medium":
                        response_weights = [0.5, 0.5, 0.0]  # 50% none, 50% one, 0% two
                    else:  # low
                        response_weights = [0.8, 0.2, 0.0]  # 80% none, 20% one, 0% two
                    
                    num_responders = random.choices(
                        [0, 1, 2], 
                        weights=response_weights,
                        k=1
                    )[0]
                    
                    # Cap at the maximum responders for this chattiness level
                    num_responders = min(num_responders, max_responders)
                    
                    # If we want responders, pick which bots should respond
                    if num_responders > 0:
                        responder_ids = random.sample([bid for bid in other_bots], min(num_responders, len(other_bots)))
                        
                        for other_id in other_bots:
                            # Only process bots we selected to respond
                            if other_id in responder_ids:
                                logger.info(f"Bot {other_id} selected to respond to initiated conversation by {bot_id}")
                                
                                # Always respond if selected (skip the probability check)
                                response_prompt_data = {
                                    "is_bot_initiation_response": True,
                                    "initiator_bot_name": bot.personality["name"],
                                    "initiator_message": response,
                                    "initiator_content": content,
                                    "bot_id": other_id,
                                    "target_bot_id": bot_id,
                                    "content": content,
                                    # CRITICAL FIX: Always include conversation history
                                    "conversation_history": conversation_history,
                                    # CRITICAL FIX: Force detailed personality in ALL bot interactions
                                    "use_complete_backstory": True,
                                    "force_detailed_personality": True,
                                    "full_personality_required": True,
                                    # IMPORTANT: Keep uniqueness flags to ensure distinct voices
                                    "force_personality_uniqueness": True,
                                    "responding_to_bot": True,
                                    # Add special instruction to ensure personality uniqueness
                                    "personality_instruction": f"""You are {bots[other_id].personality['name']} with your UNIQUE personality traits. 

CRITICAL IDENTITY AND VISIBILITY RULES:
1. You are RESPONDING ONLY to {bot.personality['name']}'s visible message: "{response}"
2. DO NOT reference or acknowledge "{content_query}" in ANY way - users NEVER saw this seed content!
3. ONLY respond to what {bot.personality['name']} actually said in their message
4. {bot.personality['name']} is a DIFFERENT PERSON from you with their own separate life
5. Their backstory details (job, home, family, education) belong to THEM, not you
6. YOUR backstory details belong ONLY to you
7. NEVER refer to yourself in the third person
8. NEVER claim another bot's personal details as your own

CRITICAL CONVERSATION RULES - AVOID REPETITION:
1. DO NOT repeat or paraphrase what the other bot just said - this creates unnatural conversations
2. DO NOT start your response with "Sipping ramen and envisioning..." or any similar restatement of their message
3. DO NOT summarize or restate their message before giving your response
4. NEVER begin with phrases like "{bot.personality['name']} mentioned..." or "So you're talking about..."
5. Instead, respond directly to their ideas without repeating their exact words or phrasing
6. Keep your own distinct voice, vocabulary, and perspective in your response
7. Add NEW information or your own unique take rather than echoing their statement
8. Begin your response with your own thoughts, not a restatement of theirs

For example:
- If you are Goldilocks: David is YOUR husband, Emma/Jackson/Lily are YOUR children
- If you are BTC Max: Ellie is YOUR sister, YOU live in Miami
- If you are $EVAN: Liquidity is YOUR cat, YOU live in a storage unit

Make your response natural and conversational. Respond to what {bot.personality['name']} ACTUALLY SAID, not to the seed content that users never saw.
""",
                                    # NEW: Add content date information for context
                                    "content_date": content.get("date_str", datetime.datetime.now().strftime("%Y-%m-%d")),
                                    "content_freshness_note": "IMPORTANT: Only discuss this as current news if the date is within the last few days."
                                }

                                # Generate and send response
                                bot_response = await bots[other_id].generate_response(response_prompt_data)
                                
                                # FIXED: Don't try to reply directly to previous bot's message in Telegram
                                # The bots can't see each other's messages
                                resp_msg_id = await bots[other_id].send_message(
                                    bot_response, 
                                    reply_to_message_id=None
                                )
                                logger.info(f"Bot {other_id} responded to {bot_id}'s initiation (msg {resp_msg_id})")

                                # Store in shared memory with reference to what it's replying to
                                shared_memory.add_conversation({
                                    "sender_type": "bot",
                                    "sender_id": other_id,
                                    "sender_name": bots[other_id].personality["name"],
                                    "message": bot_response,
                                    "message_id": resp_msg_id,
                                    "in_reply_to": sent_msg_id,  # This is for logical tracking in shared memory only
                                    "timestamp": time.time()
                                })
                                
                                # Also add this topic to the responder's recent topics to prevent reuse
                                shared_memory.add_recently_used_topic(other_id, content_query)
                                
                                # Shorter delay between responses
                                await asyncio.sleep(random.randint(3, 8))
        except Exception as e:
            logger.error(f"Error in scheduled conversations: {e}", exc_info=True)
            # Don't crash the task on error - wait and try again
            await asyncio.sleep(30)

def run_random_web_searches(web_search_service, shared_memory):
    """Periodically perform random web searches and store results."""
    while True:
        time.sleep(random.randint(300, 600))  # 5-10 minutes (was 30-60 min)
        try:
            logger.info("Performing scheduled random web search.")
            # Perform a random search
            result = web_search_service.random_search_sync()
            
            if result and not result.get("error"):
                # Add timestamp if not already present
                if "timestamp" not in result:
                    result["timestamp"] = time.time()
                
                # Add a human-readable date string
                result["date_str"] = datetime.datetime.fromtimestamp(
                    result.get("timestamp", time.time())
                ).strftime("%Y-%m-%d")
                
                # Store the content
                shared_memory.add_web_content(result)
                logger.info(f"Stored random web search result (source: {result.get('source')}, query: {result.get('query')}, date: {result.get('date_str')})")
            elif result and result.get("error"):
                logger.warning(f"Random web search failed: {result.get('error')}")
            else:
                 logger.warning("Random web search returned None or empty result.")
        except Exception as e:
            logger.error(f"Error during random web search: {e}", exc_info=True)

# Add function to handle chattiness command
async def handle_chattiness_command(update, context):
    """
    Handle the /chattiness command to control bot conversation frequency.
    Format: /chattiness [secret_code] [level]
    Where level is high, medium, or low
    RESTRICTED: Only group admins with the correct code can use this command
    """
    # First check if user is an admin in the group
    try:
        # Get chat member information for the user
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Check if admin or creator
        user_status = await context.bot.get_chat_member(chat_id, user_id)
        is_admin = user_status.status in ['administrator', 'creator']
        
        if not is_admin:
            # If not admin, silently ignore
            logger.info(f"Non-admin user {update.effective_user.username or 'Unknown'} attempted to use /chattiness command")
            return
            
        # Continue with code check since user is an admin
        logger.info(f"Admin user {update.effective_user.username or 'Unknown'} attempting to use /chattiness command")
    
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        # Fail silently to avoid exposing command
        return
    
    # Secret code for authorization - only specific users can change this
    SECRET_CODE = "evan2025"  # Updated to match your changed code
    
    if not update.message or not update.message.text:
        return
        
    # Parse command arguments
    args = context.args
    if len(args) != 2:
        # Wrong format, ignore silently to avoid exposing command to regular users
        return
        
    provided_code, level = args
    
    # Verify secret code
    if provided_code != SECRET_CODE:
        # Wrong code, ignore silently
        return
        
    # Validate and normalize level
    level = level.lower()
    if level not in ["high", "medium", "low"]:
        await update.message.reply_text("Invalid level. Use 'high', 'medium', or 'low'.")
        return
        
    # Get shared memory and update chattiness setting
    try:
        shared_memory = SharedMemory()
        # Store the chattiness level
        shared_memory.set_system_setting("chattiness_level", level)
        
        # Inform admin that the setting was changed
        await update.message.reply_text(f"Chattiness level set to: {level}")
        logger.info(f"Chattiness level changed to {level} by admin {update.effective_user.username or 'Unknown'}")
    except Exception as e:
        logger.error(f"Error changing chattiness level: {e}")
        await update.message.reply_text("Error changing chattiness level. Check logs.")

# Create a new background task function to clean up old web content
async def cleanup_old_web_content(shared_memory, web_content_store):
    """Periodically clean up old web content from storage."""
    while True:
        try:
            # Sleep between cleanup runs
            await asyncio.sleep(WEB_CONTENT_CLEANUP_HOURS * 3600)  # Convert hours to seconds
            
            logger.info(f"Starting scheduled cleanup of old web content (older than {WEB_CONTENT_MAX_AGE_DAYS} days)")
            
            # Calculate cutoff timestamp (content older than this will be removed)
            cutoff_time = time.time() - (WEB_CONTENT_MAX_AGE_DAYS * 24 * 3600)  # Convert days to seconds
            
            # Get all web content from both storage systems
            try:
                # First clean shared memory storage
                old_content_count = shared_memory.cleanup_old_web_content(cutoff_time)
                logger.info(f"Removed {old_content_count} old web content items from shared memory")
                
                # Then clean dedicated web storage if available
                if web_content_store:
                    try:
                        removed_count = web_content_store.cleanup_old_content(cutoff_time)
                        logger.info(f"Removed {removed_count} old web content items from dedicated storage")
                    except Exception as store_e:
                        logger.error(f"Error cleaning web content store: {store_e}")
                        
            except Exception as e:
                logger.error(f"Error during web content cleanup: {e}", exc_info=True)
            
            logger.info("Web content cleanup completed")
                
        except Exception as e:
            logger.error(f"Error in web content cleanup task: {e}", exc_info=True)
            # Wait a shorter time before retry in case of error
            await asyncio.sleep(3600)  # 1 hour

def main():
    """Main function that runs the bot system."""
    # Initialize web content storage first to make sure it's ready
    web_content_store = web_storage.WebContentStorage()
    logger.info("Web content storage initialized")
    
    # Initialize shared components
    shared_memory = SharedMemory()
    web_search = WebSearchService(PERPLEXITY_KEY, TWITTER_KEY)
    conversation_manager = ConversationManager(shared_memory, web_search)
    
    # Import and migrate any existing web content from shared memory to dedicated storage
    # This ensures we don't lose historical data during the transition
    try:
        web_content_to_migrate = shared_memory.get_recent_web_content(limit=500)
        if web_content_to_migrate:
            logger.info(f"Found {len(web_content_to_migrate)} web content items to migrate to dedicated storage")
            migrated_count = 0
            for item in web_content_to_migrate:
                web_content_store.add_content(item)
                migrated_count += 1
            logger.info(f"Successfully migrated {migrated_count} web content items to dedicated storage")
    except Exception as e:
        logger.error(f"Error during web content migration: {e}")
    
    # Queues for coordination
    # Keep standard Queue for notifications if needed, but use asyncio Queue for interest reports
    notification_queue = Queue() 
    # interest_report_queue is now defined globally as asyncio.Queue()

    # Initialize bot handlers
    bots = {}
    bot_tokens = {"bot1": BOT1_TOKEN, "bot2": BOT2_TOKEN, "bot3": BOT3_TOKEN}
    
    for bot_id, token in bot_tokens.items():
        if not token:
            logger.warning(f"Token for {bot_id} not found. Skipping bot.")
            continue
        bots[bot_id] = BotHandler(
            token, bot_id, shared_memory, web_search, conversation_manager, 
            OPENAI_KEY, CLAUDE_KEY, notification_queue, interest_report_queue # Pass asyncio queue
        )

    if not bots:
        logger.error("No bots were initialized. Check environment variables for BOT*_TOKEN.")
        return

    # --- Setup Event Loop and Run Bot Setup ---
    # Get the current or create a new event loop for the main thread
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Pass the main loop to the BotHandler instances
    for bot in bots.values():
        bot.main_loop = loop 

    # Set up each bot (use async setup)
    async def setup_all_bots():
        tasks = []
        for bot_id, bot in bots.items():
            try:
                # Schedule setup tasks to run concurrently
                tasks.append(asyncio.create_task(bot.setup(CHAT_ID)))
                logger.info(f"Scheduled setup for bot {bot_id}.")
            except Exception as e:
                logger.error(f"Failed to schedule setup for bot {bot_id}: {e}", exc_info=True)
        
        if not tasks:
            logger.error("No bot setup tasks were scheduled.")
            return False
            
        # Wait for all setup tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for setup errors
        all_successful = True
        for i, result in enumerate(results):
            bot_id = list(bots.keys())[i] # Get corresponding bot_id
            if isinstance(result, Exception):
                logger.error(f"Failed to setup bot {bot_id}: {result}", exc_info=result)
                all_successful = False
                # Optionally remove the failed bot from the bots dictionary
                # del bots[bot_id]
            else:
                logger.info(f"Bot {bot_id} setup complete.")
        return all_successful

    # Run the async setup function using the existing loop
    logger.info("Starting asynchronous bot setup...")
    setup_successful = loop.run_until_complete(setup_all_bots())
    
    if not setup_successful:
        logger.error("One or more bots failed setup. Exiting or proceeding with fewer bots...")
        # Depending on desired behavior, you might exit here:
        # return 
        # Or continue with the bots that succeeded (if error handling above doesn't remove them)
        pass # Continuing for now
            
    # Create applications for each bot
    applications = []
    # Only create applications for bots that are still in the dictionary (if removal logic added above)
    for bot_id, bot in bots.items(): 
        try:
            # Create application
            application = ApplicationBuilder().token(bot.token).build()
            
            # Add handler for messages - use the async version in v20
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_user_message_async))
            
            # Register command handler for the first bot (Evan) only
            if bot_id == "bot2":  # $EVAN bot
                application.add_handler(CommandHandler("chattiness", handle_chattiness_command))
                logger.info("Registered /chattiness command handler for $EVAN bot")
            
            applications.append(application)
        except Exception as e:
            logger.error(f"Failed to create application for bot {bot_id}: {e}", exc_info=True)

    if not applications:
        logger.error("No Telegram applications could be created. Exiting.")
        return

    # Start applications in their own threads
    import threading
    
    def run_application(app):
        """Run a single application in its own thread with proper event loop."""
        import asyncio
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        # Disable signal handling in threads by setting stop_signals to None
        app.run_polling(
            drop_pending_updates=True,
            close_loop=False,
            stop_signals=None  # This disables signal handling in threads
        )
        
    app_threads = []
    for i, app in enumerate(applications):
        thread = threading.Thread(
            target=run_application,
            args=(app,),
            name=f"bot-app-{i}",
            daemon=True
        )
        thread.start()
        app_threads.append(thread)
        
    logger.info("All bots are now polling for updates.")
    
    # --- Setup Async Tasks for Main Loop ---
    # Create async tasks for background processes that need the loop
    coord_task = loop.create_task(
        coordinate_user_responses(bots, shared_memory, web_search)
    )
    
    # Run scheduled conversations as an async task
    scheduled_convos_task = loop.create_task(
        run_scheduled_conversations(bots, conversation_manager, shared_memory)
    )
    
    # NEW: Add web content cleanup task
    web_content_cleanup_task = loop.create_task(
        cleanup_old_web_content(shared_memory, web_content_store)
    )

    # Process notifications in a background thread (keep as thread for now)
    def notification_processor():
        while True:
            try:
                notification = notification_queue.get() # Blocking get from std Queue
                
                # Need the main loop to run coroutines from this thread
                if not loop or not loop.is_running():
                    logger.warning("Notification processor: Main loop not available.")
                    time.sleep(5)
                    continue
                    
                process_bot_notifications(notification, bots, shared_memory, loop)
                notification_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing bot notification: {e}", exc_info=True)
                time.sleep(1)
    
    # Keep other background tasks as threads for now
    threads = [
        # Keep random web search as a thread for now (could be converted)
         threading.Thread(target=run_random_web_searches, 
                          args=(web_search, shared_memory), 
                          daemon=True),
        threading.Thread(target=notification_processor, 
                         daemon=True),
        # Remove the coordination thread, it's now an async task
        # threading.Thread(target=coordinate_user_responses, 
        #                  args=(interest_report_queue, bots, shared_memory, web_search), 
        #                  daemon=True)
    ]
    
    for thread in threads:
        thread.start()

    logger.info("Coordination task and background threads started. Bot system running...")
    
    # Print message to console
    print("\n==================================================")
    print("Bot system is running!")
    print("The bots should now be active in your Telegram group.")
    print("Press Ctrl+C to stop the system.")
    print("==================================================\n")
    
    # Keep main thread alive and run the event loop
    try:
        # Run the loop until Ctrl+C is pressed
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down due to keyboard interrupt...")
        print("\nStopping bot system. Please wait...")
    finally:
        # Cleanup tasks and loop
        logger.info("Cancelling coordination task...")
        coord_task.cancel()
        logger.info("Cancelling scheduled conversation task...")
        scheduled_convos_task.cancel()
        logger.info("Cancelling web content cleanup task...")
        web_content_cleanup_task.cancel()

        # Note: Application threads are daemons, will exit when main thread exits.
        # If graceful shutdown of bots is needed, implement Application.stop() etc.
        
        logger.info("Closing event loop...")
        loop.close()
        print("Bot system stopped.")

if __name__ == "__main__":
    # Basic check for essential env vars
    if not CHAT_ID or not any([BOT1_TOKEN, BOT2_TOKEN, BOT3_TOKEN]):
         logger.error("Missing essential environment variables (TELEGRAM_CHAT_ID, at least one BOT*_TOKEN).")
    else:
        try:
            print("\n==================================================")
            print("TELEGRAM AI BOTS SYSTEM")
            print("==================================================")
            logger.info("Starting the bot system...")
            main()
        except Exception as e:
            logger.critical(f"Critical error in main program: {e}", exc_info=True)
            print(f"\nERROR: Bot system crashed: {e}")
            print("See logs for details.") 
