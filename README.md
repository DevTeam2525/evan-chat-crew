# Telegram AI Bots System

A system of three AI personalities focused on cryptocurrency, economy, and precious metals that interact with users and each other in a Telegram group chat. The bots can search for information online, share interesting findings, and engage in natural conversations.

## Features

- Three distinct AI bot personalities:
  - **CryptoBot**: Enthusiastic crypto expert who loves discussing market trends and blockchain technology
  - **EconBot**: Analytical economist who provides thoughtful perspectives on financial markets and economic trends
  - **GoldBot**: Conservative investor focused on safe-haven assets and traditional stores of value

- Integrated search capabilities:
  - Perplexity API for detailed information
  - Twitter search for social media perspectives

- Shared memory system:
  - Stores conversations and content
  - Helps bots respond contextually
  - Tracks user interactions

- Natural interaction:
  - Bots initiate conversations with each other
  - Bots respond to users based on interests
  - Bots share interesting content they discover online

## Setup

1. **Create Telegram Bots**:
   - Use BotFather to create three separate bots
   - Get the API tokens for each bot

2. **Create a Telegram Group**:
   - Create a new group
   - Add all three bots to the group
   - Get the group chat ID

3. **API Keys**:
   - Get API keys for OpenAI, Claude/Anthropic, Perplexity, and Twitter (via RapidAPI)

4. **Environment Setup**:
   - Clone this repository
   - Install requirements: `pip install -r requirements.txt`
   - Edit the `.env` file with your API keys and Telegram tokens

5. **Run the System**:
   - Start the main application: `python main.py`

## Configuration

Edit the `.env` file with your actual API keys and tokens:

```
# Telegram settings
TELEGRAM_CHAT_ID=your_group_chat_id
BOT1_TOKEN=your_first_bot_token
BOT2_TOKEN=your_second_bot_token
BOT3_TOKEN=your_third_bot_token

# API keys
OPENAI_API_KEY=your_openai_key
CLAUDE_API_KEY=your_claude_key
PERPLEXITY_API_KEY=your_perplexity_key
TWITTER_API_KEY=your_twitter_rapidapi_key
```

## Customization

- Modify bot personalities in `conversation_manager.py`
- Add or change search topics in `web_search.py`
- Adjust conversation frequencies in `main.py`

## How It Works

1. **Scheduled Conversations**:
   - Every 15-30 minutes, bots may start conversations
   - They search for interesting content, then discuss it
   - Other bots may join based on their interests

2. **User Interactions**:
   - Users can mention bots by name to engage directly
   - Bots search for relevant information before responding
   - Bots share information from web searches in conversations

3. **Content Discovery**:
   - System regularly searches for new content
   - Stores interesting findings for bots to discuss later

## Dependencies

- python-telegram-bot
- openai
- anthropic
- aiohttp
- python-dotenv
- requests 