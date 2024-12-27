import os
import sys
import threading
import time
from typing import Optional
import discord
from discord.ext import commands
from dotenv import load_dotenv, dotenv_values, set_key, get_key
import asyncio
from top_stock import pick_top_Stock
from paper_trading import get_current_stocks_profit_loss
import subprocess
from discord import TextChannel
import datetime

# Make sure this is the only instance running if attempted to run manually
if len(sys.argv) == 2 and sys.argv[1] == "-s":
    print("Running with systemd")
else:
    result = subprocess.run(["systemctl", "is-active", "bot"], stdout=subprocess.PIPE)
    is_running_already = result.stdout == b"active\n"
    if is_running_already:
        print("Bot is already running in systemd. Please stop it first!")
        exit(1)

# Load environment variables
load_dotenv()
dotenv_path = ".env"
read_only = ["FINNHUB_API_KEY", "DISCORD_BOT_TOKEN"]

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Intents (required to interact with guilds and members)
intents = discord.Intents.all()

# Create a bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# Sync slash commands to a specific guild (faster updates) or globally (takes up to 1 hour)
GUILD_ID = os.getenv("DISCORD_GUILD_ID") 
BOT_CHANNEL_ID = os.getenv("DISCORD_BOT_CHANNEL")

# Used to prohibit simulatenous calls to get_top_stocks_now since the process can take ~ 10 minutes
full_workflow_running = False

# Used for async events
bot_loop = None

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} command(s).")
        global bot_loop
        bot_loop = asyncio.get_event_loop()
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="clear", description="Just like in a CLI ", guild=discord.Object(id=GUILD_ID))
async def clear(interaction: discord.Interaction):
    # Show the user that they need to wait
    await interaction.response.defer()

    # Fetch the channel where the command was invoked
    channel = interaction.channel
    if not channel:
        await interaction.edit_original_response(content="Could not determine the channel.")
        return

    # Notify that the deletion process is starting
    msg = "Deleting all messages in the channel..."
    await interaction.edit_original_response(content=msg)

    # Delete messages in chunks (Discord API limits batch deletions to 100 messages at a time)
    try:
        deleted_count = 0
        async for message in channel.history(limit=None):
            await message.delete()
            deleted_count += 1

            # Optionally update progress for large channels
            if deleted_count % 50 == 0:
                await interaction.edit_original_response(content=f"Deleted {deleted_count} messages...")

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Failed to delete messages: {str(e)}")

@bot.tree.command(name="get_top_stocks_today", description="Gets the top stocks today from the overnight job (much faster)", guild=discord.Object(id=GUILD_ID))
async def get_top_stocks_today(interaction: discord.Interaction):
    # Show the user that they need a wait a bit
    await interaction.response.defer()

    msg = "Running Model... [1/1]"
    await interaction.edit_original_response(content=msg)

    top_stocks = pick_top_Stock()

    # Create table rows
    header = "#\tSymbol\tCurrent Price\n"
    table_rows = [
        f"{i:<3} {row['symbol']:<6} {row['current_price']:>10.2f}"
        for i, (idx, row) in enumerate(top_stocks.iterrows(), start=1)
    ]

    # Combine header and rows into a formatted table
    table_str = "\n".join([header] + table_rows)

    # Send the message
    await interaction.edit_original_response(
        content=f"**📈 Top Stocks Today**\n```\n{table_str}\n```"
    )

@bot.tree.command(name="get_top_stocks_now", description="Gets the top stocks as of right now, running everything (takes a while!)", guild=discord.Object(id=GUILD_ID))
async def get_top_stocks_now(interaction: discord.Interaction):
    global full_workflow_running
    if full_workflow_running:
        await interaction.response.send_message(":no_entry_sign: Process already running!")
        return

    await interaction.response.defer()
    full_workflow_running = True

    # Initialize message and spinner
    msg = "Running full sequence now..."
    spinner = ["|", "/", "-", "\\\\"]
    spinner_index = 0

    # Edit the initial message
    await interaction.edit_original_response(content=msg)

    from full_workflow import progress_generator

    # Create a task to continuously update the spinner
    async def update_spinner():
        nonlocal msg, spinner_index
        while True:
            # Rotate the spinner
            spinner_index = (spinner_index + 1) % len(spinner)
            spinner_char = spinner[spinner_index]
            await interaction.edit_original_response(content=f"**{spinner_char}** {msg}")
            await asyncio.sleep(0.3)  # Adjust spinner speed as needed

    spinner_task = asyncio.create_task(update_spinner())

    try:
        # Process the progress generator
        async for progress in progress_generator():
            # Append progress to the message
            msg = f"{progress}"
    finally:
        # Stop the spinner when progress is complete
        spinner_task.cancel()
        await asyncio.sleep(0.1)  # Allow time for task cleanup

    # Fetch top stocks
    top_stocks = pick_top_Stock()

    # Create table rows
    header = "#\tSymbol\tCurrent Price\n"
    table_rows = [
        f"{i:<3} {row['symbol']:<6} {row['current_price']:>10.2f}"
        for i, (idx, row) in enumerate(top_stocks.iterrows(), start=1)
    ]

    # Combine header and rows into a formatted table
    table_str = "\n".join([header] + table_rows)

    # Send the final message
    full_workflow_running = False
    await interaction.edit_original_response(
        content=f"**📈 Top Stocks Now**\n```\n{table_str}\n```"
    )

@bot.tree.command(name="list_env_variables", description="Lists all variables from .env file", guild=discord.Object(id=GUILD_ID))
async def list_env_variables(interaction: discord.Interaction):
    env_vars = dotenv_values(dotenv_path=dotenv_path)

    embed = discord.Embed(
        title="Current Environment Variables",
        color=discord.Color.blue(),
    )

    protected_vars = {key: value for key, value in env_vars.items() if key in read_only}
    unprotected_vars = {key: value for key, value in env_vars.items() if key not in read_only}

    # Group readonly and editable into 2 groups
    # Add protected variables as a field
    if protected_vars:
        embed.add_field(
            name="🔒 Protected Variables (Read Only)",
            value="\n".join([f"**{key}**: {value}" for key, value in protected_vars.items()]) or "None",
            inline=False
        )

    # Add unprotected variables as a field
    if unprotected_vars:
        embed.add_field(
            name="🔓 Unprotected Variables (Mutable)",
            value="\n".join([f"**{key}**: {value}" for key, value in unprotected_vars.items()]) or "None",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_env_variable", description="Sets a variable from .env file (see /list_env_variables)", guild=discord.Object(id=GUILD_ID))
async def set_env_variable(interaction: discord.Interaction, key: str, new_value: str):
    env_vars = dotenv_values(dotenv_path=dotenv_path)

    # Make sure key exists
    if key not in env_vars:
        await interaction.response.send_message(content=f"The env variable **{key}** does not exist.")
        return
    
    # Make sure key isn't protected or sensitive
    if key in read_only:
        await interaction.response.send_message(content=f"The env variable **{key}** is protected and shouldn't be changed at all. Please edit the .env directly on the server if you really need to change it. Current protected environment variables: **{str(read_only)}**.")
        return
    
    set_key(dotenv_path=dotenv_path, key_to_set=key, value_to_set=new_value)
    subprocess.run(["chmod", "777", ".env"])

    await interaction.response.send_message(content=f"Environment variable **{key}** set to **{new_value}** successfully.")

@bot.tree.command(name="get_paper_portfolio", description="Gets the current paper trading portfolio with live data", guild=discord.Object(id=GUILD_ID))
async def get_paper_portfolio(interaction: discord.Interaction, tickers: Optional[str]):
    await interaction.response.defer()
    tickers = tickers.split(",") if tickers is not None else ""
    list_specific_only = tickers != "" and len(tickers) > 0
    df = get_current_stocks_profit_loss(tickers)

    if list_specific_only:
        df = df[['stock_symbol', 'quantity', 'price', 'trade_date', 'current_price', 'total_gain_loss']]
    else:
        df = df[['stock_symbol', 'current_price', 'total_gain_loss']]

    # Create the new column
    gain_loss_sum = df["total_gain_loss"].sum()
    total_movement = df["current_price"].sum()
    gain_loss_str = f"\n**Total Gain/Loss: `{gain_loss_sum:.2f}`**\n**Total Price: `{total_movement:.2f}`**" if not list_specific_only else ""
            
    header = "All" if not list_specific_only else tickers

    await interaction.edit_original_response(
        content=f"**📈 Current Paper Trading Portfolio: {header}**\n```diff\n{df}\n```{gain_loss_str}"
    )


# Cron Watching
stop_event = threading.Event()

async def send_nightly_embed(bot_channel: TextChannel):
    today_str = datetime.datetime.now().strftime("%x")
    top_n = os.getenv("TOP_N_STOCKS")
    top_stocks = pick_top_Stock()
    header = "#\tSymbol\tCurrent Price\n"
    table_rows = [
        f"{i:<3} {row['symbol']:<6} {row['current_price']:>10.2f}"
        for i, (idx, row) in enumerate(top_stocks.iterrows(), start=1)
    ]

    # Combine header and rows into a formatted table
    table_str = f"**:full_moon_with_face: {today_str} Nightly Run Results: Top {top_n} Stocks**\n```\n"
    table_str += "\n".join([header] + table_rows) + "\n```"

    await bot_channel.send(content=table_str)

async def send_paper_buy_embed(bot_channel: TextChannel):
    print("Cron Watch: Sending Paper Buy Embed")
    await bot_channel.send(content="Paper Buy Test")

async def send_paper_sell_embed(bot_channel: TextChannel):
    print("Cron Watch: Sending Paper Sell Embed")
    await bot_channel.send(content="Paper Sell Test")

def cron_watch(e):
    cron_env_path = "../cronlogs/.env.cron"
    while not stop_event.is_set():
        time.sleep(5)   
        bot_channel = bot.get_channel(int(BOT_CHANNEL_ID))
        if bot_channel is None:
            print("Incorrect BOT CHANNEL provided: ", bot, bot_channel, BOT_CHANNEL_ID)
            continue

        if bot_loop is None: 
            continue

        nightly = get_key(cron_env_path, "NIGHTLY")
        paper_buy = get_key(cron_env_path, "PAPER_BUY")
        paper_sell = get_key(cron_env_path, "PAPER_SELL")

        if nightly is not None and nightly == "1":
            asyncio.run_coroutine_threadsafe(send_nightly_embed(bot_channel), bot_loop)
            set_key(cron_env_path, "NIGHTLY", "0")
            subprocess.run(["chmod", "777", cron_env_path])

        elif paper_buy is not None and paper_buy == "1":
            asyncio.run_coroutine_threadsafe(send_paper_buy_embed(bot_channel), bot_loop)
            set_key(cron_env_path, "PAPER_BUY", "0")
            subprocess.run(["chmod", "777", cron_env_path])

        elif paper_sell is not None and paper_sell == "1":
            asyncio.run_coroutine_threadsafe(send_paper_sell_embed(bot_channel), bot_loop)
            set_key(cron_env_path, "PAPER_SELL", "0")
            subprocess.run(["chmod", "777", cron_env_path])

watch_thread = threading.Thread(target=cron_watch, args=(stop_event,))
watch_thread.start()



# Run the bot
bot.run(TOKEN)
