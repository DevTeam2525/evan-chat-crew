import aiohttp
import asyncio
import json
import random
import requests
import time
import logging
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("WebSearchService")

# Add forbidden topic validation function
def validate_search_topic(query: str) -> bool:
    """
    Validate a search topic against a list of forbidden topics related to outdated events.
    Returns True if the topic is valid, False if it should be blocked.
    """
    query_lower = query.lower()
    
    # Define comprehensive list of outdated topics that should not be searched
    forbidden_topics = [
        # Olympics related
        "tokyo olympics", "olympic preparations", "olympic games preparations", 
        "olympics in tokyo", "tokyo 2020", "olympics 2020", "summer olympics 2020",
        "paris olympics preparations", "paris olympics 2024", 
        "olympic village", "olympic torch", "olympic opening ceremony",
        
        # COVID/Pandemic related
        "covid", "covid-19", "pandemic", "coronavirus", "lockdown", 
        "mask mandate", "vaccine mandate", "covid restrictions", 
        "social distancing", "quarantine", "stay at home order",
        
        # Past sporting events
        "fifa world cup qatar", "world cup 2022", "qatar world cup",
        "world cup preparations", "world cup qatar", "world cup qualifiers",
        "super bowl liv", "super bowl lv", "super bowl lvi",
        
        # Past political events
        "2020 election", "trump presidency", "biden inauguration",
        "2022 midterms", "brexit transition", "uk leaving eu",
        
        # Past cultural events
        "game of thrones finale", "friends reunion", "tiger king",
        "squid game", "for all mankind season 1", "wandavision",
        "no time to die", "black widow movie",
        
        # Past product releases
        "iphone 12", "iphone 13", "ps5 launch", "xbox series x launch",
        "windows 11 release", "tesla cybertruck reveal",
        
        # Other specific outdated events
        "gamestop short squeeze", "evergrande collapse", "ftx collapse",
        "queen elizabeth funeral", "prince philip death",
    ]
    
    # Check for exact matches or substring matches
    for topic in forbidden_topics:
        if topic in query_lower:
            logger.warning(f"BLOCKED OUTDATED TOPIC: '{query}' matches forbidden topic '{topic}'")
            return False
    
    # Check for time-specific phrases that suggest looking at outdated events as current
    time_phrases = [
        "upcoming", "preparations for", "getting ready for", "planning for",
        "lead up to", "countdown to", "approaching", "will be held",
        "scheduled for", "set to begin"
    ]
    
    # If query contains time-specific phrases, do deeper analysis
    for phrase in time_phrases:
        if phrase in query_lower:
            # Look for specific events near these time phrases
            event_keywords = ["olympics", "world cup", "pandemic", "election", "launch", "ceremony"]
            for event in event_keywords:
                # Look for pattern like "preparations for olympics" or "countdown to world cup"
                pattern_match = phrase in query_lower and event in query_lower
                if pattern_match:
                    logger.warning(f"BLOCKED TIME-SENSITIVE TOPIC: '{query}' suggests outdated event '{event}' as current/upcoming")
                    return False
    
    # The topic passed all validation checks
    return True

class WebSearchService:
    def __init__(self, perplexity_key, twitter_key):
        print(f"WebSearchService initialized with keys: perplexity={perplexity_key[:5]}... twitter={twitter_key[:5]}...")
        self.perplexity_key = perplexity_key
        self.twitter_key = twitter_key
        self.topics = [
            # Financial and crypto (reduced percentage compared to before)
            "cryptocurrency trends", "Bitcoin price", "Ethereum developments", 
            "gold market analysis", "silver investments", "inflation data",
            "economic indicators", "Federal Reserve announcements", 
            "stock market outlook", "blockchain technology",
            
            # Technology and innovation
            "AI breakthrough news", "quantum computing progress", "tech startup trends",
            "SpaceX developments", "renewable energy innovations", "VR technology",
            "electric vehicle advancements", "smart city initiatives", "robotics news",
            
            # Science and health
            "medical research breakthroughs", "space exploration news", "climate science updates",
            "nutrition research findings", "psychology research", "longevity science",
            
            # Entertainment and culture
            "trending movies", "viral internet trends", "popular music releases",
            "gaming industry news", "celebrity interviews", "streaming content reviews",
            "travel destination trends", "food culture innovations",
            
            # Sports and events (MODIFIED: Removed "Olympic preparations" from this list)
            "sports highlights", "major tournament results", "athlete interviews",
            "e-sports competitions", "upcoming sporting events",
            
            # Global affairs
            "international relations", "global policy changes", "diplomatic developments",
            "humanitarian initiatives", "global education trends", "cultural exchange programs"
        ]
        # Add a list to track recently searched topics
        self.recent_searches = []
        # Maximum number of recent searches to track
        self.max_recent_searches = 50
        # Time window in hours to consider a search "recent"
        self.recent_search_window_hours = 8
        logger.info(f"WebSearchService initialized with {len(self.topics)} topics")

    # --- Bot-Specific Topic Lists ---
    GOLDILOCKS_TOPICS = [
        # Traditional financial interests (reduced percentage)
        "gold price analysis", "silver market update", "precious metals outlook", 
        "inflation data today", "central bank gold purchases", "safe haven assets",
        "smart portfolio diversification", 
        
        # Family and home
        "parenting advice", "family vacation ideas", "home organization", 
        "luxury family living", "balancing work and family", "college planning",
        "children's education trends", "modern parenting challenges",
        
        # Lifestyle & wellness
        "luxury markets", "premium collectibles", "fine dining trends", "high-end fashion", 
        "travel destinations", "investment-grade art", "wellness retreats",
        "luxury home design", "sustainable luxury", "women in finance",
        "work-life balance strategies", "executive fitness routines",
        
        # Food and entertaining
        "gourmet cooking trends", "wine collection advice", "hosting elegant parties",
        "farm-to-table movement", "artisanal food trends", "healthy family meals",
        
        # Culture and leisure
        "classical music events", "art exhibitions", "literary festivals",
        "museum exhibitions", "luxury travel experiences", "family-friendly destinations"
    ]
    
    BTC_MAX_TOPICS = [
        # Bitcoin/crypto (reduced percentage)
        "Bitcoin price prediction", "Bitcoin adoption news", "Bitcoin ETF flows", 
        "crypto market sentiment", "blockchain innovation", "crypto regulations",
        
        # Technology and innovation
        "tech startup funding", "venture capital trends", "AI ethics debates",
        "innovative tech products", "tech conference highlights", "tech industry leadership",
        
        # Dating and relationships
        "modern dating apps", "relationship advice for professionals", "dating trends",
        "balancing work and dating", "high-achiever dating challenges",
        
        # Sports and activities
        "Formula 1 racing news", "luxury sports cars", "extreme sports trends",
        "sports betting trends", "crypto fantasy sports", "high-end fitness equipment",
        "competitive sports analytics", "marathon training tips",
        
        # Travel and lifestyle
        "luxury travel destinations", "bachelor pad design", "men's fashion trends",
        "high-end watches", "exotic vacation spots", "adventure travel experiences",
        "digital nomad lifestyle", "entrepreneurial mindset", "networking events",
        
        # Food and nightlife
        "whiskey tasting guides", "best steakhouses", "nightclub scene",
        "craft beer innovations", "coffee connoisseur tips", "fine dining experiences",
        "best rooftop bars", "exclusive social clubs"
    ]
    
    EVAN_TOPICS = [
        # Crypto market alerts and scam detection (greatly expanded)
        "crypto rug pull alert", "recent token scam warning", "major token price dump", 
        "$EVAN token updates", "meme coin trends", "DeFi yield strategies",
        "crypto trading psychology", "altcoin analysis", "airdrop strategies",
        "token liquidity crisis", "crypto rugpull detection", "token scam red flags",
        "wallet drainer alerts", "major crypto dumps today", "token honeypot warning",
        "crypto exit scam news", "smart contract exploit alert", "token insider selling",
        "crypto scam prevention", "wallet security alerts", "crypto phishing attempts",
        "fake airdrop warnings", "defi protocol hack", "pump and dump scheme warning",
        
        # Technology and internet culture
        "indie game development", "internet meme evolution", "content creator economy",
        "streaming platforms", "technology accessibility", "open source projects",
        "AI art generation", "coding bootcamp reviews",
        
        # Frugal living and alternatives
        "minimalist living advice", "urban camping trends", "budget travel hacks",
        "tiny house innovations", "freegan movement", "upcycling projects",
        "side hustle ideas", "van life communities", "alternative housing solutions",
        
        # Cat and pet topics
        "cat behavior research", "pet health innovations", "exotic pet care",
        "rescue animal stories", "pet friendly accommodations", "animal psychology",
        
        # Food and survival
        "instant ramen hacks", "convenience store cuisine", "energy drink reviews",
        "urban foraging", "meal prep on a budget", "24-hour diners",
        "cheap eats", "food truck innovations",
        
        # Tech and gadgets
        "DIY electronics", "affordable tech setups", "Linux distribution reviews",
        "second-hand tech markets", "blockchain gaming", "cybersecurity for beginners",
        "productivity tools", "tech repair guides"
    ]
    # --- End Bot-Specific Topic Lists ---

    def is_topic_recently_searched(self, topic):
        """
        Check if a topic has been searched recently to avoid duplication.
        
        Args:
            topic: The search topic to check
            
        Returns:
            bool: True if topic was recently searched, False otherwise
        """
        current_time = time.time()
        # STRENGTHEN PROTECTION: Increase default window from 8 to 24 hours to avoid repeats
        recent_window = 60 * 60 * 24  # 24 hours in seconds (increased from 8 hours)
        
        # Normalize the topic for comparison
        norm_topic = topic.lower().strip()
        
        # Special case for Evan: Give priority to rug/scam alerts by making them "refresh" faster
        if "bot2" in norm_topic or "evan" in norm_topic:
            alert_keywords = ["rug", "scam", "dump", "alert", "warning", "exploit", "hack", "security", "phishing"]
            # For alert topics, use a shorter window (1 hour instead of 24)
            if any(keyword in norm_topic for keyword in alert_keywords):
                recent_window = 60 * 60  # Just 1 hour for market alerts
                logger.info(f"Using shorter refresh window for Evan's market alert topic: '{norm_topic}'")
        
        # Special case for financial updates like Fed announcements - CRITICAL: use a much longer window
        if any(term in norm_topic.lower() for term in ["federal reserve", "fed", "treasury", "bond", "rate", "interest", "economic indicators"]):
            # Use 72 hour (3 day) window for financial policy topics to prevent constant repetition
            recent_window = 60 * 60 * 72  # 72 hours
            logger.info(f"Using EXTENDED 72 hour window for financial policy topic: '{norm_topic}'")
        
        # Clean up old searches that are outside the window
        self.recent_searches = [
            s for s in self.recent_searches 
            if current_time - s["timestamp"] < recent_window
        ]
        
        # STRENGTHEN: Check for more variations of similar topics
        # Check if this topic is similar to any recent searches
        for search in self.recent_searches:
            # Direct match 
            if search["topic"].lower() == norm_topic:
                logger.warning(f"DUPLICATE PREVENTION: Exact match found for topic '{topic}' with '{search['topic']}'")
                return True
            
            # More aggressive substring matching
            if len(norm_topic) > 5 and len(search["topic"]) > 5:
                # Check if either is a substring of the other
                if norm_topic in search["topic"].lower() or search["topic"].lower() in norm_topic:
                    hours_ago = (current_time - search["timestamp"]) / 3600
                    logger.warning(f"DUPLICATE PREVENTION: Substring match for '{topic}' with '{search['topic']}' from {hours_ago:.1f} hours ago")
                    return True
                
            # Check for significant word overlap
            topic_words = set(norm_topic.split())
            search_words = set(search["topic"].lower().split())
            
            # If there are meaningful words to compare
            if len(topic_words) > 0 and len(search_words) > 0:
                # Calculate overlap ratio
                common_words = topic_words.intersection(search_words)
                overlap_ratio = len(common_words) / min(len(topic_words), len(search_words))
                
                # STRENGTHEN: Lower the threshold for considering duplicates from 0.6 to 0.4
                # If over 40% of words match, consider it a duplicate (was 60%)
                if overlap_ratio > 0.4:
                    hours_ago = (current_time - search["timestamp"]) / 3600
                    logger.warning(f"DUPLICATE PREVENTION: Topic '{topic}' is similar to recent search '{search['topic']}' ({overlap_ratio:.2f} overlap, {hours_ago:.1f} hours ago)")
                    return True
                
                # CRITICAL: Special check for "finance news" type topics
                # If ANY of these words appear in BOTH searches, require a longer waiting period
                key_financial_terms = ["market", "fed", "reserve", "treasury", "bond", "stock", "economy", "financial", "rate", "interest"]
                financial_overlap = [word for word in common_words if word in key_financial_terms]
                
                if financial_overlap and (current_time - search["timestamp"]) < (60 * 60 * 48):  # 48 hours for finance topics
                    hours_ago = (current_time - search["timestamp"]) / 3600
                    logger.warning(f"DUPLICATE PREVENTION: Financial topic '{topic}' shares key terms {financial_overlap} with '{search['topic']}' from {hours_ago:.1f} hours ago")
                    return True
        
        return False
        
    def record_search_topic(self, topic, query=None, source=None):
        """
        Record a topic as recently searched to avoid duplication.
        
        Args:
            topic: The main topic searched
            query: The full query if different from topic
            source: The search source (perplexity, twitter)
        """
        current_time = time.time()
        
        search_record = {
            "topic": topic,
            "query": query or topic,
            "source": source,
            "timestamp": current_time
        }
        
        # Add to recent searches
        self.recent_searches.append(search_record)
        
        # Trim if needed
        if len(self.recent_searches) > self.max_recent_searches:
            self.recent_searches = self.recent_searches[-self.max_recent_searches:]
            
        logger.info(f"Recorded search topic: '{topic}' from source: {source}")
    
    def get_unique_topic(self, bot_id, topic_list):
        """
        Get a unique topic that hasn't been recently searched.
        Ensures regular cycling through all available topics with improved duplicate prevention.
        
        Args:
            bot_id: The bot ID requesting the topic
            topic_list: List of potential topics to choose from
            
        Returns:
            str: A topic that hasn't been recently searched
        """
        # Track last used topics by bot to ensure variety
        if not hasattr(self, 'last_topics_by_bot'):
            self.last_topics_by_bot = {}
            
        if bot_id not in self.last_topics_by_bot:
            self.last_topics_by_bot[bot_id] = []
            
        # Get recently used topics for this bot
        recent_bot_topics = self.last_topics_by_bot[bot_id]
        
        # IMPROVEMENT: Keep track of last 20 topics instead of just 10
        max_recent_topics = 20  # Increased from 10
        
        # Filter out topics that were recently used by this bot
        available_topics = [topic for topic in topic_list if topic not in recent_bot_topics]
        
        # If we've used all topics, reset the list but keep a minimum number of most recent topics
        if not available_topics or len(available_topics) < 5:
            logger.info(f"Bot {bot_id} has cycled through most topics, resetting list but keeping last 5 most recent")
            # Only keep the 5 most recently used topics as blocked
            if len(recent_bot_topics) > 5:
                recent_bot_topics = recent_bot_topics[-5:]
            # Reset available topics, excluding the 5 most recent
            available_topics = [topic for topic in topic_list if topic not in recent_bot_topics]
            self.last_topics_by_bot[bot_id] = recent_bot_topics
            
        # NEW: Shuffle available topics once for variety rather than always taking from the start
        # This prevents always running through the list in the same order
        if len(available_topics) > 3:
            import random
            random.shuffle(available_topics)
        
        # Try to find a topic that hasn't been recently searched
        # CRITICAL IMPROVEMENT: Try more topics (10 instead of 5) to find a non-duplicate
        for _ in range(min(10, len(available_topics))):
            # Pick from the available list
            topic = available_topics[0] if available_topics else topic_list[0]
            
            if not self.is_topic_recently_searched(topic):
                # Track that this topic was used
                if len(recent_bot_topics) >= max_recent_topics:  # Keep track of last 20 topics (increased from 10)
                    recent_bot_topics.pop(0)
                recent_bot_topics.append(topic)
                self.last_topics_by_bot[bot_id] = recent_bot_topics
                
                logger.info(f"Found unique topic '{topic}' for bot {bot_id}")
                return topic
            
            # If this topic was recently searched, remove it from available and try next
            if topic in available_topics:
                available_topics.remove(topic)
                
        # If we couldn't find a unique topic, use the next one in line and add timestamp
        # IMPROVEMENT: Make timestamp more distinctive and add more context
        if available_topics:
            topic = available_topics[0]
        else:
            # As a last resort, take a random topic from the original list
            import random
            topic = random.choice(topic_list)
        
        # Format with time to make it unique and clearly identify it as a fallback
        current_time = time.strftime("%H:%M:%S", time.localtime())
        unique_topic = f"{topic} (update {current_time})"
        
        # Track that this topic was used (with timestamp)
        if len(recent_bot_topics) >= max_recent_topics:
            recent_bot_topics.pop(0)
        recent_bot_topics.append(topic)  # Store original topic without timestamp
        self.last_topics_by_bot[bot_id] = recent_bot_topics
        
        logger.warning(f"DUPLICATE PREVENTION: Created forced unique topic '{unique_topic}' for bot {bot_id} after exhausting options")
        return unique_topic

    # Synchronous version of perplexity search
    def search_perplexity_sync(self, query: str) -> Dict:
        print(f"SEARCH_PERPLEXITY_SYNC CALLED with query: {query}")
        logger.info(f"Starting Perplexity search for: {query}")
        headers = {
            "Authorization": f"Bearer {self.perplexity_key}",
            "Content-Type": "application/json"
        }
        
        # Fix the API request format to include required model and messages fields
        data = {
            "model": "sonar",  # Changed from "sonar-medium-online" to "sonar" which is a valid model
            "messages": [
                {"role": "user", "content": query}
            ],
            "max_tokens": 1000
        }
        
        print(f"Perplexity request headers: {headers}")
        print(f"Perplexity request data: {data}")
        
        try:
            print(f"Making Perplexity API request...")
            response = requests.post(
                "https://api.perplexity.ai/chat/completions", 
                headers=headers, 
                json=data
            )
            
            print(f"Perplexity API response status: {response.status_code}")
            print(f"Perplexity API response headers: {response.headers}")
            
            if response.status_code == 200:
                print(f"Perplexity API success! Processing response...")
                result = response.json()
                print(f"Perplexity API response body: {result}")
                
                # Update to handle the new API response format
                content = ""
                citations = [] # Initialize citations list
                if "choices" in result and len(result["choices"]) > 0:
                    if "message" in result["choices"][0] and "content" in result["choices"][0]["message"]:
                        content = result["choices"][0]["message"]["content"]
                    elif "text" in result["choices"][0]: # Fallback for older potential formats
                        content = result["choices"][0]["text"]
                
                # Extract citations if available (Added)
                if "citations" in result and isinstance(result["citations"], list):
                    citations = result["citations"]
                    print(f"Extracted {len(citations)} citations from sync search.")
                else:
                    print("No citations found in sync Perplexity response.")

                print(f"Extracted content: {content[:100]}...")
                logger.info(f"Perplexity search successful for '{query}' - got {len(content)} chars")
                return {
                    "source": "perplexity",
                    "query": query,
                    "content": content,
                    "citations": citations, # Include citations
                    "timestamp": time.time()
                }
            
            print(f"Perplexity API failed with status {response.status_code}")
            print(f"Response body: {response.text}")
            logger.error(f"Perplexity search failed with status {response.status_code}: {response.text}")
            return {"source": "perplexity", "query": query, "content": "", "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            print(f"EXCEPTION in Perplexity search: {str(e)}")
            logger.exception(f"Exception during Perplexity search: {e}")
            return {"source": "perplexity", "query": query, "content": "", "error": str(e)}
    
    # Synchronous version of twitter search
    def search_twitter_sync(self, query: str) -> Dict:
        print(f"SEARCH_TWITTER_SYNC CALLED with query: {query}")
        logger.info(f"Starting Twitter search for: {query}")
        headers = {
            "X-RapidAPI-Key": self.twitter_key,
            "X-RapidAPI-Host": "twitter-api45.p.rapidapi.com"
        }
        
        params = {
            "query": query,
            "search_type": "Latest",
            "count": 15
        }
        
        print(f"Twitter request headers: {headers}")
        print(f"Twitter request params: {params}")
        
        try:
            print(f"Making Twitter API request...")
            response = requests.get(
                "https://twitter-api45.p.rapidapi.com/search.php", 
                headers=headers, 
                params=params
            )
            
            print(f"Twitter API response status: {response.status_code}")
            print(f"Twitter API response headers: {response.headers}")
            
            if response.status_code == 200:
                print(f"Twitter API success! Processing response...")
                try:
                    result = response.json()
                    print(f"Twitter API response JSON format: {type(result)}")
                    print(f"Twitter API response keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
                    
                    # Detailed logging of the response structure
                    if isinstance(result, dict):
                        if "data" in result:
                            print(f"Twitter API data length: {len(result['data'])}")
                            print(f"Twitter API first data item: {result['data'][0] if result['data'] else 'Empty data'}")
                        elif "timeline" in result:
                            print(f"Twitter API timeline length: {len(result['timeline'])}")
                            print(f"Twitter API first timeline item: {result['timeline'][0] if result['timeline'] else 'Empty timeline'}")
                        else:
                            print(f"Twitter API response missing expected keys. Keys: {result.keys()}")
                    
                    tweets = []
                    if isinstance(result, dict):
                        # Try to extract from data field (old format)
                        if "data" in result:
                            for tweet in result.get("data", []):
                                print(f"Processing tweet from data: {tweet}")
                                text = tweet.get("text", "")
                                username = "unknown"
                                tweet_id = tweet.get("id_str", tweet.get("id", ""))
                                tweet_url = ""
                                
                                if "user" in tweet and isinstance(tweet["user"], dict):
                                    username = tweet["user"].get("screen_name", "unknown")
                                
                                # Dump entire tweet object for debugging
                                print(f"FULL TWEET OBJECT STRUCTURE: {json.dumps(tweet, indent=2)}")
                                
                                # Try all possible locations where a tweet ID might be stored
                                possible_id_fields = [
                                    "tweet_id", "id", "id_str", "tweetId", "tweet_id_str",
                                    "status_id", "statusId", "status_id_str", "post_id",
                                    "conversation_id", "conversationId"
                                ]
                                
                                # Check if ID might be in a nested object
                                nested_paths = [
                                    ["tweet", "id"], 
                                    ["tweet", "id_str"],
                                    ["status", "id"],
                                    ["status", "id_str"]
                                ]
                                
                                # Look for ID in top-level fields
                                tweet_id = ""
                                for field in possible_id_fields:
                                    if field in tweet and tweet[field]:
                                        tweet_id = str(tweet[field])
                                        print(f"Found tweet ID in field '{field}': {tweet_id}")
                                        break
                                
                                # If not found, try nested paths
                                if not tweet_id:
                                    for path in nested_paths:
                                        try:
                                            obj = tweet
                                            for key in path:
                                                obj = obj.get(key, {})
                                            if obj and not isinstance(obj, dict):
                                                tweet_id = str(obj)
                                                print(f"Found tweet ID in nested path {path}: {tweet_id}")
                                                break
                                        except (KeyError, TypeError, AttributeError):
                                            pass

                                # Print all top-level keys in the tweet object for debugging
                                print(f"Tweet object keys: {list(tweet.keys())}")
                                
                                # If we still don't have an ID, look for any field containing 'id' in the name
                                if not tweet_id:
                                    for key in tweet.keys():
                                        if 'id' in key.lower() and tweet[key] and not isinstance(tweet[key], dict) and not isinstance(tweet[key], list):
                                            tweet_id = str(tweet[key])
                                            print(f"Found potential tweet ID in field '{key}': {tweet_id}")
                                            break
                                
                                # First try to get a direct tweet URL from the response
                                tweet_url = ""
                                
                                # Check for direct tweet URL in various possible fields
                                url_fields = ["url", "tweet_url", "link", "expanded_url", "canonical_url", "full_url", "permalink"]
                                for field in url_fields:
                                    if field in tweet and tweet[field] and "twitter.com" in str(tweet[field]):
                                        tweet_url = tweet[field]
                                        print(f"Found direct tweet URL in field '{field}': {tweet_url}")
                                        break
                                
                                # Check if URLs might be in nested objects like 'entities' -> 'urls' -> [0] -> 'expanded_url'
                                if not tweet_url and "entities" in tweet and "urls" in tweet["entities"] and len(tweet["entities"]["urls"]) > 0:
                                    if "expanded_url" in tweet["entities"]["urls"][0] and "twitter.com" in tweet["entities"]["urls"][0]["expanded_url"]:
                                        tweet_url = tweet["entities"]["urls"][0]["expanded_url"]
                                        print(f"Found direct tweet URL in entities.urls: {tweet_url}")
                                
                                # If we didn't find a direct URL, construct one using ID + username
                                if not tweet_url and tweet_id:
                                    tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
                                    print(f"Constructed URL: {tweet_url}")
                                elif not tweet_url and "id" in tweet:
                                    # Last resort - try the bare ID field
                                    direct_id = str(tweet["id"])
                                    tweet_url = f"https://twitter.com/{username}/status/{direct_id}"
                                    print(f"Constructed URL with direct ID: {tweet_url}")
                                
                                # Final fallback
                                if not tweet_url:
                                    print(f"WARNING: Could not extract or construct URL for tweet: {tweet}")
                                    tweet_url = ""
                                
                                tweets.append({
                                    "text": text,
                                    "score": 0,
                                    "username": username,
                                    "url": tweet_url,
                                    "favorites": tweet.get("favorites", 0),
                                    "retweets": tweet.get("retweets", 0),
                                    "views": int(tweet.get("views", 0) or 0)
                                })
                        # Try to extract from timeline field (new format)
                        elif "timeline" in result:
                            for tweet in result.get("timeline", []):
                                print(f"Processing tweet from timeline: {tweet}")
                                # Extract text and username based on the timeline structure
                                text = tweet.get("text", tweet.get("tweet_text", ""))
                                username = "unknown"
                                tweet_id = tweet.get("id_str", tweet.get("id", ""))
                                tweet_url = ""
                                
                                # Try to find the username in different possible locations
                                if "user" in tweet and isinstance(tweet["user"], dict):
                                    username = tweet["user"].get("screen_name", tweet["user"].get("username", "unknown"))
                                elif "username" in tweet:
                                    username = tweet.get("username")
                                elif "screen_name" in tweet:
                                    username = tweet.get("screen_name")
                                
                                # Dump entire tweet object for debugging
                                print(f"FULL TWEET OBJECT STRUCTURE: {json.dumps(tweet, indent=2)}")
                                
                                # Try all possible locations where a tweet ID might be stored
                                possible_id_fields = [
                                    "tweet_id", "id", "id_str", "tweetId", "tweet_id_str",
                                    "status_id", "statusId", "status_id_str", "post_id",
                                    "conversation_id", "conversationId"
                                ]
                                
                                # Check if ID might be in a nested object
                                nested_paths = [
                                    ["tweet", "id"], 
                                    ["tweet", "id_str"],
                                    ["status", "id"],
                                    ["status", "id_str"]
                                ]
                                
                                # Look for ID in top-level fields
                                tweet_id = ""
                                for field in possible_id_fields:
                                    if field in tweet and tweet[field]:
                                        tweet_id = str(tweet[field])
                                        print(f"Found tweet ID in field '{field}': {tweet_id}")
                                        break
                                
                                # If not found, try nested paths
                                if not tweet_id:
                                    for path in nested_paths:
                                        try:
                                            obj = tweet
                                            for key in path:
                                                obj = obj.get(key, {})
                                            if obj and not isinstance(obj, dict):
                                                tweet_id = str(obj)
                                                print(f"Found tweet ID in nested path {path}: {tweet_id}")
                                                break
                                        except (KeyError, TypeError, AttributeError):
                                            pass

                                # Print all top-level keys in the tweet object for debugging
                                print(f"Tweet object keys: {list(tweet.keys())}")
                                
                                # If we still don't have an ID, look for any field containing 'id' in the name
                                if not tweet_id:
                                    for key in tweet.keys():
                                        if 'id' in key.lower() and tweet[key] and not isinstance(tweet[key], dict) and not isinstance(tweet[key], list):
                                            tweet_id = str(tweet[key])
                                            print(f"Found potential tweet ID in field '{key}': {tweet_id}")
                                            break
                                
                                # First try to get a direct tweet URL from the response
                                tweet_url = ""
                                
                                # Check for direct tweet URL in various possible fields
                                url_fields = ["url", "tweet_url", "link", "expanded_url", "canonical_url", "full_url", "permalink"]
                                for field in url_fields:
                                    if field in tweet and tweet[field] and "twitter.com" in str(tweet[field]):
                                        tweet_url = tweet[field]
                                        print(f"Found direct tweet URL in field '{field}': {tweet_url}")
                                        break
                                
                                # Check if URLs might be in nested objects like 'entities' -> 'urls' -> [0] -> 'expanded_url'
                                if not tweet_url and "entities" in tweet and "urls" in tweet["entities"] and len(tweet["entities"]["urls"]) > 0:
                                    if "expanded_url" in tweet["entities"]["urls"][0] and "twitter.com" in tweet["entities"]["urls"][0]["expanded_url"]:
                                        tweet_url = tweet["entities"]["urls"][0]["expanded_url"]
                                        print(f"Found direct tweet URL in entities.urls: {tweet_url}")
                                
                                # If we didn't find a direct URL, construct one using ID + username
                                if not tweet_url and tweet_id:
                                    tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
                                    print(f"Constructed URL: {tweet_url}")
                                elif not tweet_url and "id" in tweet:
                                    # Last resort - try the bare ID field
                                    direct_id = str(tweet["id"])
                                    tweet_url = f"https://twitter.com/{username}/status/{direct_id}"
                                    print(f"Constructed URL with direct ID: {tweet_url}")
                                
                                # Final fallback
                                if not tweet_url:
                                    print(f"WARNING: Could not extract or construct URL for tweet: {tweet}")
                                    tweet_url = ""
                                
                                tweets.append({
                                    "text": text,
                                    "score": 0,
                                    "username": username,
                                    "url": tweet_url,
                                    "favorites": tweet.get("favorites", 0),
                                    "retweets": tweet.get("retweets", 0),
                                    "views": int(tweet.get("views", 0) or 0)
                                })
                    
                    # --- Rank Tweets by Engagement --- 
                    if tweets:
                        for tweet in tweets:
                            # Calculate score (handle potential None values just in case)
                            favs = tweet.get("favorites", 0) or 0
                            rts = tweet.get("retweets", 0) or 0
                            views_count = tweet.get("views", 0) or 0
                            tweet["score"] = favs + (rts * 2) + (views_count * 0.1)
                            
                        # Sort by score descending
                        tweets.sort(key=lambda x: x["score"], reverse=True)
                        
                        # Keep only top 5 ranked tweets
                        tweets = tweets[:5]
                        print(f"Ranked tweets. Top score: {tweets[0]['score'] if tweets else 'N/A'}")

                    print(f"Extracted {len(tweets)} tweets")
                    for i, tweet in enumerate(tweets[:3]):  # Log first 3 tweets
                        print(f"Tweet {i+1} (Score: {tweet['score']:.1f}): @{tweet['username']}: {tweet['text'][:50]}...")
                    
                    logger.info(f"Twitter search successful for '{query}' - got {len(tweets)} tweets")
                    return {
                        "source": "twitter",
                        "query": query,
                        "content": tweets,
                        "timestamp": time.time()
                    }
                except json.JSONDecodeError as e:
                    print(f"Twitter API response was not valid JSON: {e}")
                    print(f"Response text: {response.text[:500]}")
                    logger.error(f"Failed to parse Twitter API response: {e}")
            
            print(f"Twitter API failed with status {response.status_code}")
            print(f"Response body: {response.text[:500]}")
            logger.error(f"Twitter search failed with status {response.status_code}: {response.text[:100]}")
            return {"source": "twitter", "query": query, "content": [], "error": f"HTTP {response.status_code}: {response.text[:100]}"}
        except Exception as e:
            print(f"EXCEPTION in Twitter search: {str(e)}")
            logger.exception(f"Exception during Twitter search: {e}")
            return {"source": "twitter", "query": query, "content": [], "error": str(e)}
    
    async def search_perplexity(self, query: str) -> Dict:
        print(f"ASYNC SEARCH_PERPLEXITY CALLED with query: {query}")
        logger.info(f"Starting async Perplexity search for: {query}")
        headers = {
            "Authorization": f"Bearer {self.perplexity_key}",
            "Content-Type": "application/json"
        }
        
        # Fix the API request format to include required model and messages fields
        data = {
            "model": "sonar",  # Changed from "sonar-medium-online" to "sonar" which is a valid model
            "messages": [
                {"role": "user", "content": query}
            ],
            "max_tokens": 1000
        }
        
        print(f"Async Perplexity request headers: {headers}")
        print(f"Async Perplexity request data: {data}")
        
        try:
            print(f"Making async Perplexity API request...")
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.perplexity.ai/chat/completions", 
                                        headers=headers, json=data) as response:
                    print(f"Async Perplexity API response status: {response.status}")
                    print(f"Async Perplexity API response headers: {response.headers}")
                    
                    if response.status == 200:
                        print(f"Async Perplexity API success! Processing response...")
                        result = await response.json()
                        print(f"Async Perplexity API response body: {result}")
                        
                        # Update to handle the new API response format
                        content = ""
                        citations = [] # Initialize citations list
                        if "choices" in result and len(result["choices"]) > 0:
                            if "message" in result["choices"][0] and "content" in result["choices"][0]["message"]:
                                content = result["choices"][0]["message"]["content"]
                            elif "text" in result["choices"][0]: # Fallback for older potential formats
                                content = result["choices"][0]["text"]
                        
                        # Extract citations if available (Added)
                        if "citations" in result and isinstance(result["citations"], list):
                            citations = result["citations"]
                            print(f"Extracted {len(citations)} citations.")
                        else:
                             print("No citations found in Perplexity response.")

                        print(f"Extracted content: {content[:100]}...")
                        logger.info(f"Async Perplexity search successful for '{query}' - got {len(content)} chars")
                        return {
                            "source": "perplexity",
                            "query": query,
                            "content": content,
                            "citations": citations, # Include citations
                            "timestamp": time.time()
                        }
                    
                    response_text = await response.text()
                    print(f"Async Perplexity API failed with status {response.status}")
                    print(f"Response body: {response_text}")
                    logger.error(f"Async Perplexity search failed with status {response.status}: {response_text}")
                    return {"source": "perplexity", "query": query, "content": "", "error": f"HTTP {response.status}: {response_text}"}
        except Exception as e:
            print(f"EXCEPTION in async Perplexity search: {str(e)}")
            logger.exception(f"Exception during async Perplexity search: {e}")
            return {"source": "perplexity", "query": query, "content": "", "error": str(e)}
    
    async def search_twitter(self, query: str) -> Dict:
        print(f"ASYNC SEARCH_TWITTER CALLED with query: {query}")
        logger.info(f"Starting async Twitter search for: {query}")
        headers = {
            "X-RapidAPI-Key": self.twitter_key,
            "X-RapidAPI-Host": "twitter-api45.p.rapidapi.com"
        }
        
        params = {
            "query": query,
            "search_type": "Latest",
            "count": 15
        }
        
        print(f"Async Twitter request headers: {headers}")
        print(f"Async Twitter request params: {params}")
        
        try:
            print(f"Making async Twitter API request...")
            async with aiohttp.ClientSession() as session:
                async with session.get("https://twitter-api45.p.rapidapi.com/search.php", 
                                       headers=headers, params=params) as response:
                    print(f"Async Twitter API response status: {response.status}")
                    print(f"Async Twitter API response headers: {response.headers}")
                    
                    if response.status == 200:
                        print(f"Async Twitter API success! Processing response...")
                        try:
                            result = await response.json()
                            print(f"Async Twitter API response JSON format: {type(result)}")
                            print(f"Async Twitter API response keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
                            
                            # Detailed logging of the response structure
                            if isinstance(result, dict):
                                if "data" in result:
                                    print(f"Async Twitter API data length: {len(result['data'])}")
                                    print(f"Async Twitter API first data item: {result['data'][0] if result['data'] else 'Empty data'}")
                                elif "timeline" in result:
                                    print(f"Async Twitter API timeline length: {len(result['timeline'])}")
                                    print(f"Async Twitter API first timeline item: {result['timeline'][0] if result['timeline'] else 'Empty timeline'}")
                                else:
                                    print(f"Async Twitter API response missing expected keys. Keys: {result.keys()}")
                            
                            tweets = []
                            if isinstance(result, dict):
                                # Try to extract from data field (old format)
                                if "data" in result:
                                    for tweet in result.get("data", []):
                                        print(f"Processing tweet from data: {tweet}")
                                        text = tweet.get("text", "")
                                        username = "unknown"
                                        tweet_id = tweet.get("id_str", tweet.get("id", ""))
                                        tweet_url = ""
                                        
                                        if "user" in tweet and isinstance(tweet["user"], dict):
                                            username = tweet["user"].get("screen_name", "unknown")
                                        
                                        # Dump entire tweet object for debugging
                                        print(f"FULL TWEET OBJECT STRUCTURE: {json.dumps(tweet, indent=2)}")
                                        
                                        # Try all possible locations where a tweet ID might be stored
                                        possible_id_fields = [
                                            "tweet_id", "id", "id_str", "tweetId", "tweet_id_str",
                                            "status_id", "statusId", "status_id_str", "post_id",
                                            "conversation_id", "conversationId"
                                        ]
                                        
                                        # Check if ID might be in a nested object
                                        nested_paths = [
                                            ["tweet", "id"], 
                                            ["tweet", "id_str"],
                                            ["status", "id"],
                                            ["status", "id_str"]
                                        ]
                                        
                                        # Look for ID in top-level fields
                                        tweet_id = ""
                                        for field in possible_id_fields:
                                            if field in tweet and tweet[field]:
                                                tweet_id = str(tweet[field])
                                                print(f"Found tweet ID in field '{field}': {tweet_id}")
                                                break
                                        
                                        # If not found, try nested paths
                                        if not tweet_id:
                                            for path in nested_paths:
                                                try:
                                                    obj = tweet
                                                    for key in path:
                                                        obj = obj.get(key, {})
                                                    if obj and not isinstance(obj, dict):
                                                        tweet_id = str(obj)
                                                        print(f"Found tweet ID in nested path {path}: {tweet_id}")
                                                        break
                                                except (KeyError, TypeError, AttributeError):
                                                    pass

                                        # Print all top-level keys in the tweet object for debugging
                                        print(f"Tweet object keys: {list(tweet.keys())}")
                                        
                                        # If we still don't have an ID, look for any field containing 'id' in the name
                                        if not tweet_id:
                                            for key in tweet.keys():
                                                if 'id' in key.lower() and tweet[key] and not isinstance(tweet[key], dict) and not isinstance(tweet[key], list):
                                                    tweet_id = str(tweet[key])
                                                    print(f"Found potential tweet ID in field '{key}': {tweet_id}")
                                                    break
                                        
                                        # First try to get a direct tweet URL from the response
                                        tweet_url = ""
                                        
                                        # Check for direct tweet URL in various possible fields
                                        url_fields = ["url", "tweet_url", "link", "expanded_url", "canonical_url", "full_url", "permalink"]
                                        for field in url_fields:
                                            if field in tweet and tweet[field] and "twitter.com" in str(tweet[field]):
                                                tweet_url = tweet[field]
                                                print(f"Found direct tweet URL in field '{field}': {tweet_url}")
                                                break
                                        
                                        # Check if URLs might be in nested objects like 'entities' -> 'urls' -> [0] -> 'expanded_url'
                                        if not tweet_url and "entities" in tweet and "urls" in tweet["entities"] and len(tweet["entities"]["urls"]) > 0:
                                            if "expanded_url" in tweet["entities"]["urls"][0] and "twitter.com" in tweet["entities"]["urls"][0]["expanded_url"]:
                                                tweet_url = tweet["entities"]["urls"][0]["expanded_url"]
                                                print(f"Found direct tweet URL in entities.urls: {tweet_url}")
                                        
                                        # If we didn't find a direct URL, construct one using ID + username
                                        if not tweet_url and tweet_id:
                                            tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
                                            print(f"Constructed URL: {tweet_url}")
                                        elif not tweet_url and "id" in tweet:
                                            # Last resort - try the bare ID field
                                            direct_id = str(tweet["id"])
                                            tweet_url = f"https://twitter.com/{username}/status/{direct_id}"
                                            print(f"Constructed URL with direct ID: {tweet_url}")
                                        
                                        # Final fallback
                                        if not tweet_url:
                                            print(f"WARNING: Could not extract or construct URL for tweet: {tweet}")
                                            tweet_url = ""
                                        
                                        tweets.append({
                                            "text": text,
                                            "score": 0,
                                            "username": username,
                                            "url": tweet_url,
                                            "favorites": tweet.get("favorites", 0),
                                            "retweets": tweet.get("retweets", 0),
                                            "views": int(tweet.get("views", 0) or 0)
                                        })
                                # Try to extract from timeline field (new format)
                                elif "timeline" in result:
                                    for tweet in result.get("timeline", []):
                                        print(f"Processing tweet from timeline: {tweet}")
                                        # Extract text and username based on the timeline structure
                                        text = tweet.get("text", tweet.get("tweet_text", ""))
                                        username = "unknown"
                                        tweet_id = tweet.get("id_str", tweet.get("id", ""))
                                        tweet_url = ""
                                        
                                        # Try to find the username in different possible locations
                                        if "user" in tweet and isinstance(tweet["user"], dict):
                                            username = tweet["user"].get("screen_name", tweet["user"].get("username", "unknown"))
                                        elif "username" in tweet:
                                            username = tweet.get("username")
                                        elif "screen_name" in tweet:
                                            username = tweet.get("screen_name")
                                        
                                        # Dump entire tweet object for debugging
                                        print(f"FULL TWEET OBJECT STRUCTURE: {json.dumps(tweet, indent=2)}")
                                        
                                        # Try all possible locations where a tweet ID might be stored
                                        possible_id_fields = [
                                            "tweet_id", "id", "id_str", "tweetId", "tweet_id_str",
                                            "status_id", "statusId", "status_id_str", "post_id",
                                            "conversation_id", "conversationId"
                                        ]
                                        
                                        # Check if ID might be in a nested object
                                        nested_paths = [
                                            ["tweet", "id"], 
                                            ["tweet", "id_str"],
                                            ["status", "id"],
                                            ["status", "id_str"]
                                        ]
                                        
                                        # Look for ID in top-level fields
                                        tweet_id = ""
                                        for field in possible_id_fields:
                                            if field in tweet and tweet[field]:
                                                tweet_id = str(tweet[field])
                                                print(f"Found tweet ID in field '{field}': {tweet_id}")
                                                break
                                        
                                        # If not found, try nested paths
                                        if not tweet_id:
                                            for path in nested_paths:
                                                try:
                                                    obj = tweet
                                                    for key in path:
                                                        obj = obj.get(key, {})
                                                    if obj and not isinstance(obj, dict):
                                                        tweet_id = str(obj)
                                                        print(f"Found tweet ID in nested path {path}: {tweet_id}")
                                                        break
                                                except (KeyError, TypeError, AttributeError):
                                                    pass

                                # Print all top-level keys in the tweet object for debugging
                                print(f"Tweet object keys: {list(tweet.keys())}")
                                
                                # If we still don't have an ID, look for any field containing 'id' in the name
                                if not tweet_id:
                                    for key in tweet.keys():
                                        if 'id' in key.lower() and tweet[key] and not isinstance(tweet[key], dict) and not isinstance(tweet[key], list):
                                            tweet_id = str(tweet[key])
                                            print(f"Found potential tweet ID in field '{key}': {tweet_id}")
                                            break
                                
                                # First try to get a direct tweet URL from the response
                                tweet_url = ""
                                
                                # Check for direct tweet URL in various possible fields
                                url_fields = ["url", "tweet_url", "link", "expanded_url", "canonical_url", "full_url", "permalink"]
                                for field in url_fields:
                                    if field in tweet and tweet[field] and "twitter.com" in str(tweet[field]):
                                        tweet_url = tweet[field]
                                        print(f"Found direct tweet URL in field '{field}': {tweet_url}")
                                        break
                                
                                # Check if URLs might be in nested objects like 'entities' -> 'urls' -> [0] -> 'expanded_url'
                                if not tweet_url and "entities" in tweet and "urls" in tweet["entities"] and len(tweet["entities"]["urls"]) > 0:
                                    if "expanded_url" in tweet["entities"]["urls"][0] and "twitter.com" in tweet["entities"]["urls"][0]["expanded_url"]:
                                        tweet_url = tweet["entities"]["urls"][0]["expanded_url"]
                                        print(f"Found direct tweet URL in entities.urls: {tweet_url}")
                                
                                # If we didn't find a direct URL, construct one using ID + username
                                if not tweet_url and tweet_id:
                                    tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
                                    print(f"Constructed URL: {tweet_url}")
                                elif not tweet_url and "id" in tweet:
                                    # Last resort - try the bare ID field
                                    direct_id = str(tweet["id"])
                                    tweet_url = f"https://twitter.com/{username}/status/{direct_id}"
                                    print(f"Constructed URL with direct ID: {tweet_url}")
                                
                                # Final fallback
                                if not tweet_url:
                                    print(f"WARNING: Could not extract or construct URL for tweet: {tweet}")
                                    tweet_url = ""
                                
                                tweets.append({
                                    "text": text,
                                    "score": 0,
                                    "username": username,
                                    "url": tweet_url,
                                    "favorites": tweet.get("favorites", 0),
                                    "retweets": tweet.get("retweets", 0),
                                    "views": int(tweet.get("views", 0) or 0)
                                })
                            
                            # --- Rank Tweets by Engagement --- 
                            if tweets:
                                for tweet in tweets:
                                    # Calculate score (handle potential None values just in case)
                                    favs = tweet.get("favorites", 0) or 0
                                    rts = tweet.get("retweets", 0) or 0
                                    views_count = tweet.get("views", 0) or 0
                                    tweet["score"] = favs + (rts * 2) + (views_count * 0.1)
                                    
                                # Sort by score descending
                                tweets.sort(key=lambda x: x["score"], reverse=True)
                                
                                # Keep only top 5 ranked tweets
                                tweets = tweets[:5]
                                print(f"Ranked tweets. Top score: {tweets[0]['score'] if tweets else 'N/A'}")

                            print(f"Extracted {len(tweets)} tweets")
                            for i, tweet in enumerate(tweets[:3]):  # Log first 3 tweets
                                print(f"Tweet {i+1} (Score: {tweet['score']:.1f}): @{tweet['username']}: {tweet['text'][:50]}...")
                            
                            logger.info(f"Async Twitter search successful for '{query}' - got {len(tweets)} tweets")
                            return {
                                "source": "twitter",
                                "query": query,
                                "content": tweets,
                                "timestamp": time.time()
                            }
                        except json.JSONDecodeError as e:
                            response_text = await response.text()
                            print(f"Async Twitter API response was not valid JSON: {e}")
                            print(f"Response text: {response_text[:500]}")
                            logger.error(f"Failed to parse async Twitter API response: {e}")
                    
                    response_text = await response.text()
                    print(f"Async Twitter API failed with status {response.status}")
                    print(f"Response body: {response_text[:500]}")
                    logger.error(f"Async Twitter search failed with status {response.status}: {response_text[:100]}")
                    return {"source": "twitter", "query": query, "content": [], "error": f"HTTP {response.status}: {response_text[:100]}"}
        except Exception as e:
            print(f"EXCEPTION in async Twitter search: {str(e)}")
            logger.exception(f"Exception during async Twitter search: {e}")
            return {"source": "twitter", "query": query, "content": [], "error": str(e)}
    
    # Synchronous version of random search
    def random_search_sync(self) -> Dict:
        # Try multiple topics until finding a valid one
        max_attempts = 5
        
        for _ in range(max_attempts):
            # Get a unique topic instead of any random topic
            topic = self.get_unique_topic("random", self.topics)
            print(f"RANDOM_SEARCH_SYNC selected topic: {topic}")
            
            # VALIDATE TOPIC: Skip this topic if it's in the forbidden list
            if not validate_search_topic(topic):
                logger.warning(f"RANDOM_SEARCH_SYNC rejected outdated topic: {topic}, trying another")
                continue
                
            search_type = random.choice(["perplexity", "twitter"])
            print(f"RANDOM_SEARCH_SYNC selected API: {search_type}")
            
            if search_type == "perplexity":
                full_query = f"latest news about {topic}"
                print(f"RANDOM_SEARCH_SYNC calling Perplexity with: {full_query}")
                result = self.search_perplexity_sync(full_query)
                # Record this search if successful
                if result and "error" not in result:
                    self.record_search_topic(topic, full_query, "perplexity")
                return result
            else:
                print(f"RANDOM_SEARCH_SYNC calling Twitter with: {topic}")
                result = self.search_twitter_sync(topic)
                # Record this search if successful
                if result and "error" not in result:
                    self.record_search_topic(topic, topic, "twitter")
                return result
        
        # If all attempts failed, return error
        return {"source": "validation", "error": "All random topic attempts contained outdated content", "content": []}
    
    async def random_search(self) -> Dict:
        # Try multiple topics until finding a valid one
        max_attempts = 5
        
        for _ in range(max_attempts):
            # Get a unique topic instead of any random topic
            topic = self.get_unique_topic("random", self.topics)
            print(f"ASYNC RANDOM_SEARCH selected topic: {topic}")
            
            # VALIDATE TOPIC: Skip this topic if it's in the forbidden list
            if not validate_search_topic(topic):
                logger.warning(f"ASYNC RANDOM_SEARCH rejected outdated topic: {topic}, trying another")
                continue
                
            search_type = random.choice(["perplexity", "twitter"])
            print(f"ASYNC RANDOM_SEARCH selected API: {search_type}")
            
            if search_type == "perplexity":
                full_query = f"latest news about {topic}"
                print(f"ASYNC RANDOM_SEARCH calling Perplexity with: {full_query}")
                result = await self.search_perplexity(full_query)
                # Record this search if successful
                if result and "error" not in result:
                    self.record_search_topic(topic, full_query, "perplexity")
                return result
            else:
                print(f"ASYNC RANDOM_SEARCH calling Twitter with: {topic}")
                result = await self.search_twitter(topic)
                # Record this search if successful
                if result and "error" not in result:
                    self.record_search_topic(topic, topic, "twitter")
                return result
        
        # If all attempts failed, return error
        return {"source": "validation", "error": "All random topic attempts contained outdated content", "content": []}

    # Synchronous version of specific search
    def search_specific_sync(self, query: str) -> Dict:
        print(f"SEARCH_SPECIFIC_SYNC CALLED with query: {query}")
        
        # VALIDATE QUERY: Check if this is an outdated topic before proceeding
        if not validate_search_topic(query):
            logger.warning(f"SEARCH_SPECIFIC_SYNC BLOCKED OUTDATED TOPIC: {query}")
            return {
                "source": "validation", 
                "query": query, 
                "content": "", 
                "error": "This topic refers to outdated events that don't match our May 2025 timeline."
            }
            
        # Smart API selection based on query content
        query_lower = query.lower()
        
        # --- START: Force Perplexity for Video Requests --- 
        video_indicators = ["video", "clip", "show me video", "find video", "watch"]
        if any(indicator in query_lower for indicator in video_indicators):
            search_type = "perplexity"
            print(f"SEARCH_SPECIFIC_SYNC: Forcing Perplexity search due to video keyword.")
        else:
            # --- Fallback to other rules if not a video request --- 
            # --- START: Force Twitter for $EVAN Contract Address --- 
            evan_contract_address = "GFUgXbMeDnLkhZaJS3nYFqunqkFNMRo9ukhyajeXpump".lower()
            if evan_contract_address in query_lower:
                search_type = "twitter"
                print(f"SEARCH_SPECIFIC_SYNC: Forcing Twitter search due to $EVAN contract address.")
            else:
                # --- Fallback to original API selection logic --- 
                # --- START: Force Twitter for Rug Pull context --- (Keep existing rug rule)
                if "rug" in query_lower or "rug pull" in query_lower:
                    search_type = "twitter"
                    print(f"SEARCH_SPECIFIC_SYNC: Forcing Twitter search due to 'rug' keyword.")
                else:
                    # --- Original API selection logic --- 
                    twitter_indicators = [
                        "twitter", "tweet", "tweets", "tweeted", "@", 
                        "trending on twitter", "viral tweet", "twitter thread",
                        "what are people saying on twitter", "twitter discussion",
                        "twitter conversation", "twitter reactions", "twitter news",
                        "latest tweets", "recent tweets", "meme", "memes", "funny"
                    ]
                    
                    finance_indicators = [
                        "price", "market", "analysis", "chart", "report", "forecast",
                        "economic", "statistics", "data", "percentage", "metrics", 
                        "research", "study", "publication", "details", "history",
                        "compare", "explained", "theory", "how", "why", "what is"
                    ]
                    
                    twitter_score = sum(1 for indicator in twitter_indicators if indicator in query_lower)
                    finance_score = sum(1 for indicator in finance_indicators if indicator in query_lower)
                    
                    if "twitter" in query_lower or "tweet" in query_lower:
                        twitter_score += 3
                    
                    crypto_terms = ["crypto", "bitcoin", "ethereum", "token", "sol", "solana", "meme coin", "altcoin"]
                    if any(term in query_lower for term in crypto_terms) and twitter_score == 0:
                        twitter_score += 1
                    
                    if "meme" in query_lower or "funny" in query_lower:
                        twitter_score += 5
                    
                    print(f"SEARCH_SPECIFIC_SYNC score analysis - Twitter: {twitter_score}, Perplexity: {finance_score}")
                    
                    if twitter_score > finance_score:
                        search_type = "twitter"
                    elif finance_score > twitter_score:
                        search_type = "perplexity"
                    else:
                        news_terms = ["news", "latest", "recent", "update", "happening", "event", "today", "now", "breaking"]
                        has_news_terms = any(term in query_lower for term in news_terms)
                        
                        if has_news_terms:
                            search_type = "twitter"
                        else:
                            search_type = "perplexity"
                            
                        if not has_news_terms and twitter_score == 0 and finance_score == 0:
                            search_type = random.choice(["perplexity", "twitter"])
        
        print(f"SEARCH_SPECIFIC_SYNC selected API: {search_type}")
        
        if search_type == "perplexity":
            print(f"SEARCH_SPECIFIC_SYNC calling Perplexity with: {query}")
            return self.search_perplexity_sync(query)
        else:
            print(f"SEARCH_SPECIFIC_SYNC calling Twitter with: {query}")
            return self.search_twitter_sync(query)
    
    async def search_specific(self, query: str) -> Dict:
        print(f"ASYNC SEARCH_SPECIFIC CALLED with query: {query}")
        
        # VALIDATE QUERY: Check if this is an outdated topic before proceeding
        if not validate_search_topic(query):
            logger.warning(f"ASYNC SEARCH_SPECIFIC BLOCKED OUTDATED TOPIC: {query}")
            return {
                "source": "validation", 
                "query": query, 
                "content": "", 
                "error": "This topic refers to outdated events that don't match our May 2025 timeline."
            }
            
        # Smart API selection based on query content
        query_lower = query.lower()
        
        # --- START: Enhanced Evan Alert Detection --- 
        # Detect if this is a potential market alert query (rug pulls, dumps, scams)
        alert_keywords = ["rug", "scam", "dump", "crash", "exploit", "hack", "alert", "warning", 
                         "security", "phishing", "liquidity pull", "exit scam", "honeypot"]
        is_market_alert = any(keyword in query_lower for keyword in alert_keywords)
        
        # If this is a potential market alert and contains $EVAN, always use Twitter for latest info
        if is_market_alert and "$evan" in query_lower:
            search_type = "twitter"
            logger.info(f"MARKET ALERT: Forcing Twitter search for potential $EVAN related alert: '{query}'")
            
        # For general market alerts, prefer Twitter but fall through to normal logic
        elif is_market_alert:
            # Use a 70% chance of Twitter for market alerts
            if random.random() < 0.7:
                search_type = "twitter"
                logger.info(f"MARKET ALERT: Using Twitter for potential market alert: '{query}'")
            else:
                # Continue with normal search logic for the remaining 30%
                pass
        # --- END: Enhanced Evan Alert Detection --- 
                
        # --- START: Force Perplexity for Video Requests --- 
        elif any(indicator in query_lower for indicator in ["video", "clip", "show me video", "find video", "watch"]):
            search_type = "perplexity"
            print(f"ASYNC SEARCH_SPECIFIC: Forcing Perplexity search due to video keyword.")
        # --- Fallback to other rules if not a video request --- 
        
        # --- START: Force Twitter for $EVAN Contract Address --- 
        elif "GFUgXbMeDnLkhZaJS3nYFqunqkFNMRo9ukhyajeXpump".lower() in query_lower:
            search_type = "twitter"
            print(f"ASYNC SEARCH_SPECIFIC: Forcing Twitter search due to $EVAN contract address.")
        
        # --- START: Force Twitter for Rug Pull context --- (Keep existing rug rule)
        elif "rug" in query_lower or "rug pull" in query_lower:
            search_type = "twitter"
            print(f"ASYNC SEARCH_SPECIFIC: Forcing Twitter search due to 'rug' keyword.")
        
        else:
            # --- Original API selection logic --- 
            twitter_indicators = [
                "twitter", "tweet", "tweets", "tweeted", "@", 
                "trending on twitter", "viral tweet", "twitter thread",
                "what are people saying on twitter", "twitter discussion",
                "twitter conversation", "twitter reactions", "twitter news",
                "latest tweets", "recent tweets", "meme", "memes", "funny"
            ]
            
            finance_indicators = [
                "price", "market", "analysis", "chart", "report", "forecast",
                "economic", "statistics", "data", "percentage", "metrics", 
                "research", "study", "publication", "details", "history",
                "compare", "explained", "theory", "how", "why", "what is"
            ]
            
            twitter_score = sum(1 for indicator in twitter_indicators if indicator in query_lower)
            finance_score = sum(1 for indicator in finance_indicators if indicator in query_lower)
            
            if "twitter" in query_lower or "tweet" in query_lower:
                twitter_score += 3
            
            crypto_terms = ["crypto", "bitcoin", "ethereum", "token", "sol", "solana", "meme coin", "altcoin"]
            if any(term in query_lower for term in crypto_terms) and twitter_score == 0:
                twitter_score += 1
            
            if "meme" in query_lower or "funny" in query_lower:
                twitter_score += 5
            
            print(f"ASYNC SEARCH_SPECIFIC score analysis - Twitter: {twitter_score}, Perplexity: {finance_score}")
            
            if twitter_score > finance_score:
                search_type = "twitter"
            elif finance_score > twitter_score:
                search_type = "perplexity"
            else:
                news_terms = ["news", "latest", "recent", "update", "happening", "event", "today", "now", "breaking"]
                has_news_terms = any(term in query_lower for term in news_terms)
                
                if has_news_terms:
                    search_type = "twitter"
                else:
                    search_type = "perplexity"
                    
                if not has_news_terms and twitter_score == 0 and finance_score == 0:
                    search_type = random.choice(["perplexity", "twitter"])
        
        print(f"ASYNC SEARCH_SPECIFIC selected API: {search_type}")
        
        if search_type == "perplexity":
            print(f"ASYNC SEARCH_SPECIFIC calling Perplexity with: {query}")
            return await self.search_perplexity(query)
        else:
            print(f"ASYNC SEARCH_SPECIFIC calling Twitter with: {query}") 
            return await self.search_twitter(query) 

    # --- Bot-Specific Random Search --- 
    async def search_bot_specific_topic(self, bot_id: str) -> Dict:
        """Performs a search using topics tailored to the specific bot's personality, cycling through them systematically."""
        topic_list = []
        if bot_id == "bot1": # BTC Max
            topic_list = self.BTC_MAX_TOPICS
        elif bot_id == "bot2": # $EVAN
            topic_list = self.EVAN_TOPICS
        elif bot_id == "bot3": # Goldilocks
            topic_list = self.GOLDILOCKS_TOPICS
        else:
            # Fallback to the generic list if bot_id is unknown or needs generic content
            logger.warning(f"Unknown bot_id '{bot_id}' for specific search, using generic topics.")
            topic_list = self.topics

        if not topic_list: # Fallback if a specific list was empty for some reason
             logger.warning(f"Topic list for bot_id '{bot_id}' was empty, using generic topics.")
             topic_list = self.topics

        # Get a unique topic using our improved cycling method
        topic = self.get_unique_topic(bot_id, topic_list)
        
        # Alternate between search types more systematically
        # Track which search type was last used for this bot
        if not hasattr(self, 'last_search_type'):
            self.last_search_type = {}
        
        # Alternate between search types
        if self.last_search_type.get(bot_id) == "perplexity":
            search_type = "twitter"
        else:
            search_type = "perplexity"
        
        # Update the last search type
        self.last_search_type[bot_id] = search_type
        
        logger.info(f"Performing bot-specific search for {bot_id} on topic: '{topic}' via {search_type}")

        if search_type == "perplexity":
            # Use a slightly more detailed query for perplexity
            full_query = f"latest news and analysis about {topic}"
            result = await self.search_perplexity(full_query)
            # Record this search if successful
            if result and "error" not in result:
                self.record_search_topic(topic, full_query, "perplexity")
            return result
        else:
            # Twitter search usually works well with just the topic keyword(s)
            result = await self.search_twitter(topic)
            # Record this search if successful
            if result and "error" not in result:
                self.record_search_topic(topic, topic, "twitter")
            return result
    
    # Sync version for potential use in background threads if needed
    def search_bot_specific_topic_sync(self, bot_id: str) -> Dict:
        """Synchronous version of search_bot_specific_topic with systematic topic cycling."""
        topic_list = []
        if bot_id == "bot1": # BTC Max
            topic_list = self.BTC_MAX_TOPICS
        elif bot_id == "bot2": # $EVAN
            topic_list = self.EVAN_TOPICS
        elif bot_id == "bot3": # Goldilocks
            topic_list = self.GOLDILOCKS_TOPICS
        else:
            logger.warning(f"Unknown bot_id '{bot_id}' for specific sync search, using generic topics.")
            topic_list = self.topics

        if not topic_list:
             logger.warning(f"Sync topic list for bot_id '{bot_id}' was empty, using generic topics.")
             topic_list = self.topics

        # Get a unique topic using our improved cycling method
        topic = self.get_unique_topic(bot_id, topic_list)
        
        # Alternate between search types more systematically
        # Track which search type was last used for this bot
        if not hasattr(self, 'last_search_type'):
            self.last_search_type = {}
        
        # Alternate between search types
        if self.last_search_type.get(bot_id) == "perplexity":
            search_type = "twitter"
        else:
            search_type = "perplexity"
        
        # Update the last search type
        self.last_search_type[bot_id] = search_type
        
        logger.info(f"Performing sync bot-specific search for {bot_id} on topic: '{topic}' via {search_type}")

        if search_type == "perplexity":
            full_query = f"latest news and analysis about {topic}"
            result = self.search_perplexity_sync(full_query)
            # Record this search if successful
            if result and "error" not in result:
                self.record_search_topic(topic, full_query, "perplexity")
            return result
        else:
            result = self.search_twitter_sync(topic)
            # Record this search if successful
            if result and "error" not in result:
                self.record_search_topic(topic, topic, "twitter")
            return result 