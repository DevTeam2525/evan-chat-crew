import random
import json
import os
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("StoryGenerator")

class StoryGenerator:
    """
    Generates diverse stories for bots to use in conversations.
    Combines templates with variables to create thousands of unique permutations.
    """
    
    def __init__(self):
        # Story elements for each bot
        self.bot_elements = {
            "bot1": self._load_btc_max_elements(),
            "bot2": self._load_evan_elements(),
            "bot3": self._load_goldilocks_elements()
        }
        
        # Output directory
        self.output_dir = Path("generated_stories")
        self.output_dir.mkdir(exist_ok=True)
    
    def _load_btc_max_elements(self):
        """Load story elements for BTC Max"""
        return {
            "locations": [
                "Miami condo", "trading desk", "crypto conference", "Brickell high-rise", 
                "gym", "Tesla", "airport lounge", "yacht party", "rooftop bar",
                "luxury hotel", "private jet", "vacation rental", "trading floor",
                "coffee shop", "co-working space", "penthouse", "beach house",
                "ski lodge", "poker tournament", "F1 paddock", "whiskey bar",
                "steakhouse", "tech meetup", "Stanford alumni event"
            ],
            "activities": [
                "analyzing charts", "pitching Bitcoin", "setting up new monitors",
                "checking portfolio", "messaging potential dates", "arguing with nocoiners",
                "planning conference trips", "talking to family about crypto",
                "shopping for suits", "looking at sports cars", "watching F1 races",
                "attending networking events", "working out", "playing poker",
                "swiping on dating apps", "collecting whiskey", "installing mining rigs",
                "buying dips", "stacking sats", "giving financial advice",
                "interviewing for podcasts", "tweeting price predictions",
                "researching altcoins", "attending yacht parties"
            ],
            "problems": [
                "the wifi went down", "the market crashed", "my date asked if Bitcoin was 'that dog coin'",
                "my sister called me a crypto bro", "my cleaning lady unplugged my mining rig",
                "my dad still won't invest in Bitcoin", "the exchange went down during a pump",
                "I got liquidated", "I missed a major price move", "my Tesla needs charging",
                "I spilled coffee on my hardware wallet", "I confused a bartender with blockchain talk",
                "my landlord found out about my mining operation", "I lost my spot on the conference panel",
                "my trading bot malfunctioned", "my phone died during a major market move",
                "I got into an argument about Bitcoin's energy usage", "I missed my flight to a conference",
                "my date didn't know what DeFi means", "I accidentally sent crypto to the wrong address",
                "I got locked out of my exchange account", "my password manager crashed"
            ],
            "consequences": [
                "missed a 20% price pump", "had to explain crypto basics for the hundredth time",
                "spent three hours recovering wallets", "lost my temper on Twitter",
                "called my Wharton professor for advice", "drank too much whiskey",
                "stayed up all night rebuilding my strategy", "forgot an important date",
                "had to admit I was wrong (temporarily)", "rage-bought more Bitcoin",
                "gave an impromptu TED talk about blockchain", "made a $10K bet on future prices",
                "had to switch to mobile trading", "panic-sold at the bottom",
                "scheduled an emergency call with my tax advisor", "bought another monitor",
                "had to rebuild my trading desk", "started a flame war with gold bugs",
                "changed my price prediction three times in one day", "accidentally became a meme on crypto Twitter"
            ],
            "resolutions": [
                "still up 150% this year", "remembered why we're still early",
                "ended up making more money anyway", "made some great connections",
                "bought the exact bottom", "explained Bitcoin so well they're now investing",
                "recovered everything and then some", "got invited to speak at a bigger conference",
                "fixed the issue just in time for the next rally", "learned a valuable trading lesson",
                "met someone who actually understands crypto", "upgraded my entire setup as a result",
                "wrote a viral thread about the experience", "realized it was actually bullish news",
                "converted three nocoiners in the process", "found a better trading strategy",
                "got a bigger position at a better price", "became known as 'the guy who called it'",
                "used the opportunity to diversify my holdings", "turned it into a profitable arbitrage opportunity"
            ],
            "time_references": [
                "just now", "this morning", "yesterday", "last night", "this week",
                "over the weekend", "during lunch", "while traveling", "at 3 AM",
                "during the market dip", "before my workout", "after a conference call",
                "between meetings", "during my Tesla autopilot drive", "at the airport",
                "mid-trading session", "during breakfast", "after hours", "pre-market"
            ]
        }
    
    def _load_evan_elements(self):
        """Load story elements for Evan"""
        return {
            "locations": [
                "storage unit", "Planet Fitness", "parking lot with WiFi", "laundromat",
                "24-hour diner", "convenience store", "coffee shop with free refills",
                "library", "fast food restaurant", "outdoor bench", "park with outlets",
                "mall food court", "train station", "abandoned building lobby",
                "community center", "university campus", "hospital waiting room",
                "supermarket café", "bus terminal", "airport charging station",
                "cheap motel lobby", "hacker space", "crypto meetup venue", "shopping center"
            ],
            "activities": [
                "debugging code", "monitoring charts", "hunting for WiFi", "collecting cans",
                "setting up mining rigs", "feeding Liquidity", "tracking rugpulls",
                "analyzing token contracts", "charging devices", "taking shelter from rain",
                "talking to other homeless", "searching for food deals", "fixing hardware wallets",
                "showering at the gym", "doing laundry", "dumpster diving for electronics",
                "writing trading algorithms", "securing valuables", "meeting other degens",
                "developing rug detection tools", "bargaining for ramen", "stretching food stamps",
                "teaching crypto basics", "working side gigs"
            ],
            "problems": [
                "Liquidity knocked over my energy drink", "storage unit inspection tomorrow",
                "WiFi password changed", "gym staff asking questions", "phone battery died",
                "got rained on while sleeping", "laptop started glitching", "lost access to power outlet",
                "dropped my hardware wallet", "almost got discovered living in storage",
                "ran out of clean clothes", "couldn't afford food", "storage unit leaked in the storm",
                "got kicked out of my usual spot", "brother tried to stage an intervention",
                "mom called about real jobs", "lost my gym membership card", "got sick with no healthcare",
                "landlord found my mining setup", "wallet showing incorrect balance",
                "had to attend a job interview for appearance", "cat brought dead animal as gift"
            ],
            "consequences": [
                "stayed awake for 72 hours", "had to relocate temporarily", "missed major market movement",
                "got liquidated again", "ate nothing but ramen for days", "lost connection during crucial trade",
                "couldn't wash clothes for a week", "had to borrow money from brother", "drank five energy drinks",
                "wallet got compromised", "called in favor from old Accenture colleague", "slept in Tesla charging station",
                "had to walk five miles to new wifi spot", "traded technical analysis for food", "avoided family calls",
                "pretended to be night security", "had existential crisis about life choices", "sold personal belongings",
                "used McDonald's as office for three days", "lost access to trading account", "had to face harsh reality"
            ],
            "resolutions": [
                "Liquidity caught a mouse as compensation", "found even better WiFi spot",
                "made enough on a trade to eat real food", "discovered new exchange with lower fees",
                "found abandoned electronics to sell", "got free food from dumpster behind restaurant",
                "avoided rug pull that caught everyone else", "identified scam token before launch",
                "storage neighbor offered electricity access", "got free gym pass from employee",
                "found better storage unit at same price", "saved someone else from getting scammed",
                "created new system for detecting rug pulls", "made 5x return after almost losing everything",
                "brother finally stopped trying to 'save' me", "spotted pattern nobody else saw",
                "improved my setup with discarded tech", "received donation from crypto meetup friends",
                "found way to reduce living expenses further", "converted nocoiner to $EVAN believer"
            ],
            "liquidity_behaviors": [
                "knocked over my energy drink", "predicted the market crash by running in circles",
                "brought me a dead mouse as a gift", "hissed at my laptop before the dip",
                "pawed at my screen right at the bottom", "sat on my keyboard during the pump",
                "refused to eat before the market turned", "made strange noises before the recovery",
                "slept through the entire bull run", "scratched at storage door before major news",
                "stared at chart patterns with unusual focus", "attacked my phone during a scam call",
                "knocked my hardware wallet to safety", "purring intensified with rising prices",
                "meowed loudly before exchange went down", "blocked my view right before a bad trade",
                "tipped over ramen just before major alert", "walked across keyboard making perfect trade",
                "refused to enter storage before power outage", "jumped on desk during profitable trade"
            ],
            "time_references": [
                "at 3 AM", "while fighting sleep", "during storage inspection", "at peak market volatility",
                "during laundromat visit", "between WiFi sessions", "while charging devices",
                "during Planet Fitness shower time", "at midnight", "during free coffee refill",
                "while avoiding security", "during power outage", "at break of dawn",
                "during food court closing", "when WiFi was strongest", "before gym staff changeover",
                "during rush hour", "while everyone was sleeping", "between rain showers"
            ]
        }
    
    def _load_goldilocks_elements(self):
        """Load story elements for Goldilocks"""
        return {
            "locations": [
                "home office", "kitchen counter", "school pickup line", "soccer sidelines",
                "dance recital", "grocery store", "PTA meeting", "master bathroom",
                "neighborhood coffee shop", "investment club meeting", "bedroom trading desk",
                "backyard patio", "children's school events", "wine bar", "yoga studio",
                "family vacation", "charity gala", "art exhibition", "book club",
                "symphony hall", "luxury boutique", "husband's hospital", "school conference",
                "children's bedrooms"
            ],
            "activities": [
                "checking portfolios", "cooking dinner", "attending children's events",
                "managing family finances", "organizing home", "hosting dinner parties",
                "exercising", "reading market analysis", "attending book club",
                "planning family vacations", "researching investments", "managing household",
                "shopping for luxury items", "talking to other parents", "teaching children about money",
                "attending charity events", "balancing work-life", "coordinating family schedules",
                "renovating home", "networking with other professionals", "maintaining gold collection",
                "analyzing economic indicators", "helping with homework", "planning retirement"
            ],
            "children_activities": [
                "soccer game", "piano recital", "math competition", "school play",
                "science fair", "parent-teacher conference", "swim meet", "ballet lesson",
                "baseball practice", "birthday party", "school drop-off", "homework session",
                "doctor's appointment", "college tour", "summer camp registration", "playdate",
                "tennis lesson", "chess tournament", "coding class", "art exhibition"
            ],
            "problems": [
                "market crashed during school pickup", "husband found trading screen in bathroom",
                "children interrupted important call", "missed buying opportunity during dinner prep",
                "PTA meeting ran long during market volatility", "portfolio alert during family dinner",
                "son asked teacher about Bitcoin mining", "nanny questioned investment decisions",
                "in-laws criticized financial choices", "accidentally mentioned trades at book club",
                "phone died during crucial market moment", "children spent allowance on questionable investments",
                "husband questioned crypto holdings", "yoga instructor noticed trading during shavasana",
                "conflicting family and financial priorities", "neighbor asked for stock tips",
                "had to explain large purchase to husband", "trading platform crashed during family vacation",
                "children overheard market analysis call", "household emergency during market opening"
            ],
            "husband_reactions": [
                "suggested a safer investment strategy", "asked if this was 'still a phase'",
                "wanted to discuss more conservative options", "was completely oblivious",
                "wondered about college funds instead", "asked about tax implications",
                "suggested talking to his financial advisor", "was impressed but concerned",
                "joked about my 'secret financial life'", "questioned the risk level",
                "suggested taking profits", "asked for help with his own portfolio",
                "preferred not knowing the details", "worried about market volatility",
                "wondered if we should be more diversified", "thought it was taking too much time",
                "expressed concern about work-life balance", "proposed a joint investment account",
                "reminded me about past market corrections", "actually had good insight this time"
            ],
            "children_reactions": [
                "asked if they could invest allowance", "repeated market terminology at school",
                "wanted to start their own portfolio", "drew pictures of charts rising",
                "asked what a 'bull market' animal looks like", "questioned why we can't buy a Lamborghini",
                "wanted to know if money 'grows' like plants", "started tracking stock prices",
                "asked if Bitcoin is better than gold", "wondered if Roblox accepts crypto",
                "told friends mom is a 'finance wizard'", "asked why we have money in banks",
                "wanted to create a lemonade stand crypto", "questioned the Federal Reserve's role",
                "asked why we can't just 'make more money'", "wondered if we're rich or not",
                "started 'trading' Pokemon cards like stocks", "asked if their college is already paid for",
                "wondered why we still budget if investments do well", "started charging interest on sibling loans"
            ],
            "resolutions": [
                "still outperformed husband's portfolio", "balanced everything perfectly as usual",
                "taught children valuable money lesson", "made successful trade while cooking",
                "turned family event into networking opportunity", "found perfect work-life integration",
                "converted skeptical friend to precious metals", "added significant value to portfolio",
                "reorganized schedule for better efficiency", "discovered investment opportunity through children's activities",
                "improved family portfolio allocation", "created better system for trading while parenting",
                "perfectly timed market entry during school event", "expanded investment club membership",
                "identified trend before financial news reported it", "maintained composure through volatility",
                "used multitasking skills to advantage", "leveraged mother's intuition for market timing",
                "proved women can excel in finance while parenting", "balanced traditional and modern assets perfectly"
            ],
            "time_references": [
                "during dinner preparation", "while helping with homework", "at soccer practice",
                "between school drop-offs", "during piano lessons", "before the family woke up",
                "after the children's bedtime", "during carpool", "between meetings",
                "while hosting dinner party", "during grocery shopping", "at doctor's waiting room",
                "during household chores", "at children's performance", "during husband's work event",
                "while everyone was watching TV", "before David got home", "during family breakfast",
                "while multitasking"
            ]
        }
    
    def generate_stories(self, bot_id, count=1000):
        """
        Generate a specified number of unique stories for a particular bot.
        
        Args:
            bot_id: The bot ID (bot1, bot2, bot3)
            count: Number of stories to generate
            
        Returns:
            List of generated stories
        """
        if bot_id not in self.bot_elements:
            logger.error(f"Invalid bot_id: {bot_id}")
            return []
            
        elements = self.bot_elements[bot_id]
        stories = []
        
        # Define templates based on bot personality
        if bot_id == "bot1":  # BTC Max
            templates = [
                "Was {activity} at my {location} when {problem}. {consequence}. But I'm {resolution}.",
                "{time_reference}, I was {activity} and {problem}. {consequence}, but at least I'm {resolution}.",
                "You won't believe what just happened at my {location}. While {activity}, {problem}. {consequence}!",
                "Pro tip: Don't try {activity} at your {location} when {problem}. I just {consequence}.",
                "Typical day in crypto: {time_reference}, {problem} while {activity}. {consequence}, but {resolution}.",
                "Just my luck - {problem} right in the middle of {activity} at {location}. {consequence}.",
                "Who else has {problem} while {activity}? Just {consequence} and now I need a drink.",
                "Market's wild today. Was {activity} when {problem}, which meant I {consequence}.",
                "The joys of being a Bitcoin maximalist: {problem} at my {location}, {consequence}, but still {resolution}.",
                "My sister Ellie would laugh at this: {problem} during {activity}, {consequence}."
            ]
        elif bot_id == "bot2":  # Evan
            templates = [
                "Liquidity just {liquidity_behaviors} {time_reference}. Pretty sure it's a sign to check the charts.",
                "Storage unit life update: {problem} {time_reference}. Had to {consequence}, but then {resolution}.",
                "Degen alert: Was {activity} when {problem}. {consequence} but eventually {resolution}.",
                "Life hack when you're broke: If {problem}, just {consequence} and usually {resolution}.",
                "Liquidity woke me up at 3 AM by {liquidity_behaviors}. Cat definitely knows something about the market.",
                "Pro tip from a storage unit dweller: Never {activity} when {problem}. I just {consequence}.",
                "Just another day: {time_reference}, {problem} while {activity} in my {location}. Had to {consequence}.",
                "Survival mode activated: {problem} at my {location}. {consequence} but managed to {resolution}.",
                "Liquidity update: My cat {liquidity_behaviors} right before {problem}. Coincidence? I think not.",
                "When you live on the edge: {time_reference}, {problem}. {consequence}, but {resolution}."
            ]
        else:  # Goldilocks (bot3)
            templates = [
                "Mom life and trader life collide: {problem} during Emma's {children_activities}. {resolution}.",
                "Just balanced portfolio management with {children_activities} duty. {problem}, but {resolution}.",
                "Multi-tasking achievement unlocked: {activity} while monitoring gold prices. {problem}, but {resolution}.",
                "When markets and motherhood collide: {time_reference}, {problem}. {husband_reactions}, but {resolution}.",
                "Today's challenge: {children_activities} while {activity}. {problem}, but I still {resolution}.",
                "The joys of trading as a mother: {problem} during Lily's {children_activities}. {resolution}.",
                "David came home early and {husband_reactions} when he saw me {activity} during Jackson's {children_activities}.",
                "The children's reaction when {problem}: {children_reactions}. Teaching them early about finance!",
                "Perfect timing: {problem} {time_reference}. {husband_reactions}, but I {resolution} anyway.",
                "Balance is everything: {activity} while preparing for {children_activities}. {problem}, but {resolution}."
            ]
            
        # Generate unique stories by combining templates and elements
        used_stories = set()
        attempts = 0
        max_attempts = count * 10  # To prevent infinite loops
        
        while len(stories) < count and attempts < max_attempts:
            attempts += 1
            
            template = random.choice(templates)
            
            # Replace placeholders with random elements
            story = template
            for key, values in elements.items():
                if "{" + key + "}" in story:
                    story = story.replace("{" + key + "}", random.choice(values))
            
            # Check if this exact story has been generated before
            if story not in used_stories:
                used_stories.add(story)
                stories.append(story)
                
                # Log progress
                if len(stories) % 100 == 0:
                    logger.info(f"Generated {len(stories)} stories for {bot_id}")
        
        logger.info(f"Successfully generated {len(stories)} unique stories for {bot_id}")
        return stories
    
    def save_stories(self, bot_id, stories):
        """Save generated stories to a JSON file"""
        output_file = self.output_dir / f"{bot_id}_stories.json"
        
        with open(output_file, 'w') as f:
            json.dump(stories, f, indent=2)
            
        logger.info(f"Saved {len(stories)} stories to {output_file}")
        return output_file
    
    def generate_and_save_all(self, count_per_bot=1000):
        """Generate and save stories for all bots"""
        results = {}
        
        for bot_id in self.bot_elements.keys():
            logger.info(f"Generating stories for {bot_id}...")
            stories = self.generate_stories(bot_id, count=count_per_bot)
            output_file = self.save_stories(bot_id, stories)
            results[bot_id] = {
                "count": len(stories),
                "file": str(output_file)
            }
            
        return results

# Example usage
if __name__ == "__main__":
    generator = StoryGenerator()
    
    # Generate a smaller number for testing
    test_count = 10
    logger.info(f"Generating {test_count} test stories per bot...")
    
    # Generate and save stories for all bots
    results = generator.generate_and_save_all(count_per_bot=test_count)
    
    # Print results
    for bot_id, data in results.items():
        logger.info(f"Bot {bot_id}: Generated {data['count']} stories, saved to {data['file']}")
    
    # Output example stories
    for bot_id in generator.bot_elements.keys():
        logger.info(f"\nExample stories for {bot_id}:")
        example_stories = generator.generate_stories(bot_id, count=5)
        for i, story in enumerate(example_stories):
            logger.info(f"{i+1}. {story}") 